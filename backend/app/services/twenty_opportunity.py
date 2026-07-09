"""Twenty CRM — Opportunity cascade (Lead / Company / Contact -> Opportunity).

Twenty has no "button" field type reachable through the metadata API this
integration uses (TEXT / NUMBER / BOOLEAN / SELECT / MULTI_SELECT / DATE_TIME /
CURRENCY / LINKS / FULL_NAME / EMAILS / ARRAY — see twenty_client.py's module
docstring). The nearest first-class "click to fire an action" affordance Twenty
ships is a Workflow's Manual Trigger, which renders as a "Run workflow" button
on a record's detail page. So the intended wiring — one single-step Manual
Trigger Workflow per object (Lead / Company / Person), each doing nothing but a
"Send Webhook" call to ``POST /webhooks/twenty-opportunity`` — keeps the actual
cascade logic here in BetterStats rather than Twenty's no-code builder (see
docs/twenty-crm-integration.md §19 for the exact workflow steps to configure).

Three entry points, one shared outcome: an Opportunity for the club, upserted
(never duplicated) on ``bcOpportunityKey = club.grassroots_guid`` — a re-trigger
refreshes the same deal rather than spawning a second one.

  * lead    -> the club is already known (Lead.bcLeadKey); upsert the Opportunity
               directly and mark the Lead Converted.
  * company -> force-upsert the club's Lead first (regardless of whether it
               would organically qualify — a human explicitly asked for a deal),
               then upsert the Opportunity, per the user's own spec: "if we
               request an Opportunity from a Club or Contact record, a Lead
               record should be upserted first, then an Opportunity".
  * person  -> same as company, PLUS the Opportunity's pointOfContact is set to
               this Person — the contact who triggered it becomes the deal's
               point of contact, refreshed on every trigger (not just at
               create), since a re-trigger is a deliberate re-assignment.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import MarketingClub, MarketingClubContact, async_session_maker
from app.services.twenty_client import client
from app.services.twenty_sync import _link_get, _twenty_modules, _upsert

logger = logging.getLogger(__name__)

# The pipeline stage a freshly-cascaded Opportunity opens at — a human just
# actively asked for this deal to exist, so it starts past "Target".
_DEFAULT_STAGE = "CONTACTED"


async def _club_by_guid(session: AsyncSession, guid: str) -> Optional[MarketingClub]:
    return (await session.execute(
        select(MarketingClub).where(MarketingClub.grassroots_guid == guid)
    )).scalar_one_or_none()


async def _club_by_company_id(session: AsyncSession, company_tid: str) -> Optional[MarketingClub]:
    """Reverse-map a Twenty Company id back to its club via twenty_links (the
    same table only ever indexed bc_id -> twenty_id elsewhere; idx_twenty_links_twenty
    exists specifically for this direction)."""
    row = (await session.execute(text(
        "SELECT bc_id FROM twenty_links WHERE entity_type = 'club' AND twenty_id = :t"),
        {"t": company_tid})).first()
    return await _club_by_guid(session, row[0]) if row else None


async def _company_tid_for(session: AsyncSession, club: MarketingClub) -> Optional[str]:
    link_row = await _link_get(session, "club", club.grassroots_guid)
    return link_row[0] if link_row else None


def _default_modules(club: MarketingClub) -> list:
    """A starting guess at modulesInScope for a Company/Person-origin cascade
    (which has no explicit "modules to pursue" signal the way a Lead does):
    whatever the club has already shown interest in or is trialing. The human
    refines it in Twenty afterwards — this just saves them starting from blank."""
    return _twenty_modules(list(club.requested_trial_modules or []) + list(club.trial_modules or []))


async def _force_upsert_lead(session: AsyncSession, http: httpx.AsyncClient, club: MarketingClub,
                             company_tid: str, modules: list) -> Optional[str]:
    """Create-or-refresh the club's Lead unconditionally — no _lead_signal gate.
    A human explicitly asked for a deal to start, so a Lead must exist to have
    been "converted" from, even if the club's own engagement wouldn't
    organically qualify one today. Goes straight to Converted, since the
    Opportunity this feeds is created in the same action."""
    values = {
        "name": club.name,
        "leadSource": "OUTBOUND_CAMPAIGN",
        "signalSummary": "Opportunity requested directly from the CRM.",
        "modulesOfInterest": modules,
    }
    lid, _act = await _upsert(
        session, http, "lead", club.grassroots_guid, "leads", "bcLeadKey", values,
        create_extra={"bcLeadKey": club.grassroots_guid, "leadStatus": "CONVERTED",
                      "companyId": company_tid})
    return lid


async def _upsert_opportunity(session: AsyncSession, http: httpx.AsyncClient, club: MarketingClub,
                              company_tid: str, modules: list,
                              point_of_contact_id: Optional[str] = None) -> tuple:
    values: dict = {"name": f"{club.name} — Better Cricket"}
    if modules:
        values["modulesInScope"] = modules
    if point_of_contact_id:
        # In `values` (not create_extra) so a re-trigger REASSIGNS the point of
        # contact even onto an already-existing Opportunity — a deliberate
        # "this person is now the contact" action, not a set-once default.
        values["pointOfContactId"] = point_of_contact_id
    create_extra = {"bcOpportunityKey": club.grassroots_guid, "companyId": company_tid,
                    "stage": _DEFAULT_STAGE}
    return await _upsert(
        session, http, "opportunity", club.grassroots_guid, "opportunities",
        "bcOpportunityKey", values, create_extra=create_extra)


async def create_opportunity_from_lead(session: AsyncSession, http: httpx.AsyncClient,
                                       lead_tid: str) -> dict:
    lead = await client.get_by_id(http, "leads", lead_tid)
    if lead is None:
        return {"error": "lead not found in Twenty"}
    club_guid = lead.get("bcLeadKey")
    if not club_guid:
        return {"error": "lead has no bcLeadKey"}
    club = await _club_by_guid(session, club_guid)
    if club is None:
        return {"error": "no matching BetterCricket club for this lead"}
    company_tid = lead.get("companyId") or await _company_tid_for(session, club)
    if not company_tid:
        return {"error": "lead's club has no linked Company in Twenty"}
    modules = lead.get("modulesToPursue") or lead.get("modulesOfInterest") or []
    oid, act = await _upsert_opportunity(session, http, club, company_tid, modules)
    if oid:
        try:
            await client.update(http, "leads", lead_tid, {"leadStatus": "CONVERTED"})
        except Exception:  # noqa: BLE001 - the opportunity exists either way
            logger.exception("twenty: failed to mark lead %s Converted after cascade", lead_tid)
    await session.commit()
    return {"ok": True, "club": club.name, "opportunity": oid, "action": act}


async def create_opportunity_from_company(session: AsyncSession, http: httpx.AsyncClient,
                                          company_tid: str) -> dict:
    company = await client.get_by_id(http, "companies", company_tid)
    if company is None:
        return {"error": "company not found in Twenty"}
    club_guid = company.get("bcClubId")
    if not club_guid:
        return {"error": "company has no bcClubId"}
    club = await _club_by_guid(session, club_guid)
    if club is None:
        return {"error": "no matching BetterCricket club for this company"}
    modules = _default_modules(club)
    await _force_upsert_lead(session, http, club, company_tid, modules)
    oid, act = await _upsert_opportunity(session, http, club, company_tid, modules)
    await session.commit()
    return {"ok": True, "club": club.name, "opportunity": oid, "action": act}


async def create_opportunity_from_person(session: AsyncSession, http: httpx.AsyncClient,
                                         person_tid: str) -> dict:
    person = await client.get_by_id(http, "people", person_tid)
    if person is None:
        return {"error": "person not found in Twenty"}
    club = None
    bc_contact_id = person.get("bcContactId")
    if bc_contact_id:
        try:
            ct = await session.get(MarketingClubContact, bc_contact_id)
        except Exception:  # noqa: BLE001 - a malformed id string, treat as unresolved
            ct = None
        if ct is not None:
            club = await session.get(MarketingClub, ct.marketing_club_id)
    company_tid = person.get("companyId")
    if club is None and company_tid:
        club = await _club_by_company_id(session, company_tid)
    if club is None:
        return {"error": "could not resolve this contact's club"}
    if not company_tid:
        company_tid = await _company_tid_for(session, club)
    if not company_tid:
        return {"error": "contact's club has no linked Company in Twenty"}
    modules = _default_modules(club)
    await _force_upsert_lead(session, http, club, company_tid, modules)
    oid, act = await _upsert_opportunity(session, http, club, company_tid, modules,
                                         point_of_contact_id=person_tid)
    await session.commit()
    return {"ok": True, "club": club.name, "opportunity": oid, "action": act,
            "point_of_contact": person_tid}


_HANDLERS = {
    "lead": create_opportunity_from_lead,
    "company": create_opportunity_from_company,
    "person": create_opportunity_from_person,
}


async def run_cascade(source: str, record_id: str) -> dict:
    """Entry point for the public webhook route. Opens its own session + http
    client (mirrors twenty_sync.push_club_and_contacts); never raises — a CRM
    hiccup must never surface as a 500 to Twenty's retry logic."""
    source = (source or "").strip().lower()
    handler = _HANDLERS.get(source)
    if handler is None:
        return {"error": f"unknown source '{source}' — must be lead, company, or person"}
    if not client.configured:
        return {"error": "Twenty is not configured."}
    if not record_id:
        return {"error": "missing recordId"}
    try:
        async with async_session_maker() as session:
            session.sync_session.expire_on_commit = False
            async with httpx.AsyncClient() as http:
                return await handler(session, http, record_id)
    except Exception as e:  # noqa: BLE001 - never let a CRM error bubble to the caller
        logger.exception("twenty opportunity cascade failed (source=%s, id=%s)", source, record_id)
        return {"error": str(e)}
