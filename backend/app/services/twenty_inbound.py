"""Twenty INBOUND — turn a CRM record-update webhook into a BetterCricket request.

Twenty is otherwise an export-only sink (twenty_sync). This is the one path data
flows the other way: when a salesperson marks a club interested in a module, or
adds one to Trial Modules, on the Twenty Company, the webhook lands here and we
queue a module trial request (``module_action_requests``, source=twenty) for a
super admin to action. It never changes entitlement directly.

A club that isn't synced yet (no ``organisations`` row — ``ModuleActionRequest``
requires one) can't be queued that way: instead we raise a Twenty Task asking for
the club to be synced first, so the trial request can follow once it is.

The dispatcher is deliberately generic — keyed on ``eventName`` — so future
Twenty-origin request types plug into the same entrypoint. Verified against a real
Twenty payload may need the field paths below tweaked; they follow the shape we
export in twenty_sync (``bcClubId``, ``interestedModules``/``trialModules`` as
uppercase keys).
"""
from __future__ import annotations

import logging

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.modules import BILLABLE_MODULES, billing_key_for
from app.models.db import (
    MarketingClub, ModuleActionRequest, Organisation, OrgModuleSubscription,
)

logger = logging.getLogger(__name__)


def _record_from(payload: dict) -> dict:
    """Twenty wraps the changed row under ``record`` (create/update events). Be
    tolerant of a flat payload too."""
    if not isinstance(payload, dict):
        return {}
    rec = payload.get("record")
    return rec if isinstance(rec, dict) else payload


def _modules_from(value) -> list[str]:
    """Normalise a Twenty modules multiselect value (uppercase keys, or a comma
    string) to our lowercase module keys."""
    if value is None:
        return []
    if isinstance(value, str):
        parts = [p.strip() for p in value.replace(",", " ").split()]
    elif isinstance(value, (list, tuple)):
        parts = [str(p).strip() for p in value]
    else:
        return []
    # Billable module keys (BetterAdmin = 'admin'), matching what we export.
    return [p.lower() for p in parts if p and p.lower() in BILLABLE_MODULES]


async def _resolve_club_and_org(db: AsyncSession, record: dict):
    """Map a Twenty Company back to its marketing-directory row and (if synced) its
    BetterCricket org, via the bcClubId we export (= marketing_clubs.grassroots_guid
    -> existing_org_id). Returns (mc, org) — org is None for a club not yet synced."""
    bc_club_id = record.get("bcClubId") or record.get("bcclubid")
    if not bc_club_id:
        return None, None
    mc = (await db.execute(
        select(MarketingClub).where(MarketingClub.grassroots_guid == str(bc_club_id))
    )).scalar_one_or_none()
    if mc is None:
        return None, None
    org = await db.get(Organisation, mc.existing_org_id) if mc.existing_org_id else None
    return mc, org


async def _queue_presync_task(db: AsyncSession, mc: MarketingClub, module_keys: list[str]) -> list[str]:
    """The club hasn't been synced yet (no organisations row), so a trial can't be
    queued as a ModuleActionRequest. Raise a Twenty Task per requested module instead
    — deduped forever on a deterministic ext_ref, so re-saving the same modules in
    Twenty never re-raises it."""
    from app.services.twenty_sync import _link_get, _raise_task  # deferred: avoid a cycle
    created = []
    link_row = await _link_get(db, "club", mc.grassroots_guid)
    company_tid = link_row[0] if link_row else None
    async with httpx.AsyncClient() as http:
        for module_key in module_keys:
            ext_ref = f"presync:{mc.grassroots_guid}:{module_key}"
            title = (f"Sync {mc.name}: needed before the {module_key.upper()} trial "
                     f"requested in the CRM can be created")
            tid = await _raise_task(db, http, ext_ref, title, company_tid)
            if tid:
                created.append(module_key)
                await db.commit()  # persist the twenty_links dedupe row immediately
    return created


async def request_trial_modules(db: AsyncSession, mc: MarketingClub, org: "Organisation | None",
                                module_keys: list[str], *, source: str,
                                ext_key: "str | None" = None) -> dict:
    """Queue a trial for each of ``module_keys`` on ``mc``: a real, actionable
    ``ModuleActionRequest`` when the club is already synced (an org exists), else a
    Twenty Task asking for the club to be synced first (see ``_queue_presync_task``).
    Shared by the Twenty webhook (a salesperson edits Trial/Interested Modules on the
    Company) and the Club Directory (a super admin edits Trial Modules directly) —
    both funnel through the same super-admin action queue either way.

    Deduped: an org-side request skips a module already held or already outstanding;
    a pre-sync Task is deduped forever on ``(club, module)`` via twenty_links. Also
    raises the Twenty Task for each newly-queued request immediately (rather than
    waiting for the daily ``_mirror_requests_to_tasks`` sweep in
    twenty_leads_tasks.py) — same ``req:{id}`` ext_ref, so that sweep's own dedupe
    check simply no-ops on it next run instead of ever double-raising."""
    module_keys = sorted(set(module_keys))
    if not module_keys:
        return {"created": []}
    if org is None:
        created = await _queue_presync_task(db, mc, module_keys)
        return {"club": mc.name, "sync_required": True, "created": created}

    held = {
        billing_key_for(k) for k in (await db.execute(
            select(OrgModuleSubscription.module_key)
            .where(OrgModuleSubscription.organisation_id == org.id)
        )).scalars().all()
    }
    established = (org.subscription_status or "").lower() in ("active", "trial", "past_due")
    new_reqs = []
    for module_key in module_keys:
        if module_key in held:
            continue
        ext_ref = f"{ext_key}:{module_key}" if ext_key else None
        existing_q = select(ModuleActionRequest.id).where(
            ModuleActionRequest.organisation_id == org.id,
            ModuleActionRequest.module_key == module_key,
            ModuleActionRequest.kind == "trial",
            ModuleActionRequest.status == "outstanding",
        )
        if (await db.execute(existing_q)).first():
            continue
        if ext_ref and (await db.execute(
            select(ModuleActionRequest.id).where(ModuleActionRequest.external_ref == ext_ref)
        )).first():
            continue
        req = ModuleActionRequest(
            organisation_id=org.id,
            module_key=module_key,
            kind="trial",
            status="outstanding",
            source=source,
            note="Trial requested in the CRM" if source == "twenty" else "Trial modules updated in the Club Directory",
            external_ref=ext_ref,
        )
        db.add(req)
        new_reqs.append((req, module_key))
    if not new_reqs:
        return {"club": org.name, "created": []}
    await db.flush()  # populate req.id for the Task ext_ref below
    await db.commit()
    created = [module_key for _req, module_key in new_reqs]
    try:
        from app.services.twenty_sync import _link_get, _raise_task
        link_row = await _link_get(db, "club", mc.grassroots_guid)
        company_tid = link_row[0] if link_row else None
        async with httpx.AsyncClient() as http:
            for req, module_key in new_reqs:
                mod = (module_key or "").upper()
                title = (f"Enable {mod} trial for {org.name}" if established
                         else f"Set up {org.name}: initiate sync + start BetterStats trial "
                              f"({mod} requested)")
                await _raise_task(db, http, f"req:{req.id}", title, company_tid)
                await db.commit()
    except Exception:  # noqa: BLE001 - the ModuleActionRequest is already saved; the
        # daily mirror sweep will still raise the Task if this best-effort push fails
        logger.exception("twenty_inbound: failed to raise immediate Task for %s trial request(s)",
                         org.name)
    return {"club": org.name, "created": created}


async def dispatch_webhook(db: AsyncSession, payload: dict) -> dict:
    """Route a verified Twenty webhook. Returns a small summary for the response/log.
    Only company create/update events carrying interested or trial modules do
    anything today."""
    event = str((payload or {}).get("eventName") or (payload or {}).get("event") or "").lower()
    record = _record_from(payload)
    # Only act on company events (ignore people/associations/etc).
    if "company" not in event and "bcClubId" not in record and "bcclubid" not in record:
        return {"handled": False, "reason": "not a company event"}

    interested = _modules_from(record.get("interestedModules") or record.get("interestedmodules"))
    trialing = _modules_from(record.get("trialModules") or record.get("trialmodules"))
    wanted = sorted(set(interested) | set(trialing))
    if not wanted:
        return {"handled": False, "reason": "no interested/trial modules"}

    mc, org = await _resolve_club_and_org(db, record)
    if mc is None:
        return {"handled": False, "reason": "no linked club"}

    record_id = str(record.get("id") or "")
    result = await request_trial_modules(db, mc, org, wanted, source="twenty",
                                         ext_key=f"twenty:{record_id}" if record_id else None)
    return {"handled": True, **result}
