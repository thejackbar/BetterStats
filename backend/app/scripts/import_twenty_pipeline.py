"""One-time backfill: pull each club's CURRENT Twenty pipeline position
(Opportunity stage/amount, or Lead status if no Opportunity exists yet) into
BetterCRM's own platform pipeline (services/crm.py), so the new Kanban
doesn't start from zero when it takes over from Twenty's Opportunity board.

Engagement score is deliberately NOT part of this backfill — it was never
Twenty's number to begin with. ``marketing_clubs.engagement_score`` /
``.engagement_tier`` are computed locally by ``twenty_sync._engagement()``
and only ever pushed OUT to Twenty as a mirrored field, so BetterCRM already
has every club's current score with no import needed. The one thing that
only lives in Twenty is where a human sales rep has manually dragged a deal
card to (stage, dollar amount, lost reason) — that's what this script reads
back.

Source: ``twenty_links`` (entity_type IN ('opportunity', 'lead')), which is
the same membership ledger every other Twenty integration point already
relies on for id mapping — no separate full paginated scan of Twenty's
Opportunity/Lead lists is needed. Per club, the Opportunity (if one exists)
wins over the Lead: it's the more progressed state, and reaching Opportunity
already implies the Lead was converted.

This is a ONE-TIME backfill, not an ongoing sync — going forward,
``crm.sync_platform_deal_for_club`` already keeps the local pipeline moving
off the same signals (enquiry, trial request/start) that used to only push
into Twenty. Pulling from Twenty on a recurring basis would just create two
masters for the same deal; run this once during cutover, then the local
pipeline is the source of truth.

Safe to re-run: every write is get-or-create keyed on
(club, platform pipeline), and only ever moves a deal FORWARD relative to
what's already recorded locally (see ``_should_move``) — a deal already
further along locally (e.g. from a fresh enquiry landing after this script's
first run) is never dragged backward by a stale Twenty snapshot.

Usage from the backend container:
  docker exec -e PYTHONPATH=/app betterstats-backend \\
    python -m app.scripts.import_twenty_pipeline
"""
from __future__ import annotations

import asyncio
import logging
import re

import httpx
from sqlalchemy import select, text

from app.models.db import MarketingClub, MarketingClubContact, async_session_maker
from app.services import crm
from app.services.billing_pricing import price_for
from app.services.twenty_client import client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Politeness gap between per-club API round-trips — twenty_client's own
# rate limiter is the real throttle; this just spaces out session churn,
# same posture as reconcile_twenty.py's _PACE_SECONDS.
_PACE_SECONDS = 0.05

# Twenty's Opportunity pipeline (bootstrap_twenty.PIPELINE) -> our own
# crm_stage.key (services/crm.py PLATFORM_DEFAULT_STAGES) — a straight 1:1
# now that the platform pipeline mirrors Twenty's exact stage set (including
# its own distinct "Self-Serve Trial" column, no longer collapsed onto Trial).
_OPPORTUNITY_STAGE_MAP = {
    "TARGET": "target",
    "CONTACTED": "contacted",
    "ENGAGED": "engaged",
    "TRIAL": "trial",
    "SELF_SERVE_TRIAL": "self_serve_trial",
    "PROPOSAL": "proposal",
    "WON": "won",
    "LOST_DORMANT": "lost_dormant",
}

# Twenty's Lead.leadStatus (bootstrap_twenty.py) -> our stage key, used only
# when a club has a Lead but no Opportunity yet. CONVERTED shouldn't
# normally reach here (converting a Lead creates the Opportunity in the same
# action — see twenty_opportunity.py), but a Lead can outlive a since-deleted
# Opportunity, so it's mapped defensively rather than skipped.
_LEAD_STATUS_MAP = {
    "NEW": "target",
    "WORKING": "contacted",
    "CONVERTED": "engaged",
    "DISCARDED": "lost_dormant",
}

# Position of each stage key in the default pipeline, for the "never move
# backward from a stale snapshot" guard (_should_move) — mirrors
# crm.sync_platform_deal_for_club's own advance_only default, just keyed on
# stage KEY (stable across a renamed stage) rather than position on the
# possibly-since-reordered live pipeline.
_STAGE_ORDER = {key: i for i, (key, *_r) in enumerate(crm.PLATFORM_DEFAULT_STAGES)}


def _normalize_option(value) -> str:
    """A Twenty SELECT value, tolerant of either the stored option VALUE
    ('WON') or its display LABEL ('Won') — bootstrap_twenty.py's own
    _downgrade_lead_and_opportunities compares against labels in one place
    and values in another (flagged there as unverified against the live
    workspace), so this backfill doesn't assume which one the REST API
    actually returns and just normalises both to the same shape."""
    return re.sub(r"[^A-Z0-9]+", "_", str(value or "").upper()).strip("_")


def _modules_from_twenty(value) -> list[str]:
    """Twenty's MULTI_SELECT modulesInScope/modulesToPursue/modulesOfInterest
    values are our uppercase billing keys (CORE/SELECT/SOCIALS/ADMIN/IQ/
    FANTASY — bootstrap_twenty.MODULE_OPTS) -> lowercase for price_for()."""
    if not value:
        return []
    if isinstance(value, str):
        parts = [p.strip() for p in value.replace(",", " ").split()]
    elif isinstance(value, (list, tuple)):
        parts = [str(p).strip() for p in value]
    else:
        return []
    return sorted({p.lower() for p in parts if p})


def _amount_to_cents(amount) -> "int | None":
    """Twenty's CURRENCY shape: {"amountMicros": int, "currencyCode": ...}.
    None if no real amount was ever entered (a human didn't fill it in)."""
    if not isinstance(amount, dict):
        return None
    micros = amount.get("amountMicros")
    if micros is None:
        return None
    try:
        return int(round(float(micros) / 10_000))  # micros/1e6 dollars -> cents
    except (TypeError, ValueError):
        return None


def _clean_label(value) -> "str | None":
    """A free-text field (lostReason, oppSource) — stored as-is, whichever
    shape Twenty hands back, since our own column is unstructured text."""
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _should_move(current_stage_key: "str | None", target_stage_key: str) -> bool:
    """Never drag a deal BACKWARD relative to what's already recorded
    locally — a deal that progressed further after this script's first run
    (e.g. a fresh enquiry, or a super admin working it directly in
    BetterCRM) must not be demoted by a now-stale Twenty snapshot on a
    re-run."""
    if current_stage_key is None:
        return True
    cur = _STAGE_ORDER.get(current_stage_key)
    tgt = _STAGE_ORDER.get(target_stage_key)
    if cur is None or tgt is None:
        return True
    return tgt > cur


async def _linked_clubs() -> dict:
    """Every club with a Twenty Opportunity and/or Lead, keyed on
    marketing_clubs.grassroots_guid -> {"opportunity": twenty_id, "lead": twenty_id}."""
    async with async_session_maker() as session:
        rows = (await session.execute(text(
            "SELECT entity_type, bc_id, twenty_id FROM twenty_links "
            "WHERE entity_type IN ('opportunity', 'lead')"
        ))).all()
    out: dict = {}
    for entity_type, bc_id, twenty_id in rows:
        out.setdefault(bc_id, {})[entity_type] = twenty_id
    return out


async def _primary_contact(session, marketing_club_id):
    return (await session.execute(
        select(MarketingClubContact)
        .where(MarketingClubContact.marketing_club_id == marketing_club_id)
        .order_by(MarketingClubContact.role_rank, MarketingClubContact.created_at)
    )).scalars().first()


async def _existing_platform_deal(session, pipeline_id, marketing_club_id):
    """The club's one platform deal, any status — NOT filtered to 'open' the
    way crm.sync_platform_deal_for_club's own lookup is. That function wants a
    churned-then-returning club to start a fresh deal cycle; this backfill
    wants exactly one deal per club mirroring Twenty's single Opportunity, so
    a re-run after a deal has closed Won/Lost must find and update it rather
    than minting a duplicate open deal alongside it."""
    return (await session.execute(
        select(crm.CrmDeal).where(
            crm.CrmDeal.pipeline_id == pipeline_id,
            crm.CrmDeal.marketing_club_id == marketing_club_id,
            crm.CrmDeal.archived_at.is_(None),
        ).order_by(crm.CrmDeal.created_at.desc())
    )).scalars().first()


async def _import_one(http: httpx.AsyncClient, session, pipeline, stage_by_key: dict,
                      club: MarketingClub, links: dict) -> dict:
    opp_id = links.get("opportunity")
    lead_id = links.get("lead")

    if opp_id:
        opp = await client.get_by_id(http, "opportunities", opp_id)
        if opp is None:
            return {"club": club.name, "skipped": "linked opportunity no longer exists in Twenty"}
        stage_key = _OPPORTUNITY_STAGE_MAP.get(_normalize_option(opp.get("stage")))
        if stage_key is None:
            return {"club": club.name, "skipped": f"unrecognised opportunity stage {opp.get('stage')!r}"}
        modules = _modules_from_twenty(opp.get("modulesInScope"))
        value_cents = _amount_to_cents(opp.get("amount"))
        lost_reason = _clean_label(opp.get("lostReason")) if stage_key == "lost_dormant" else None
        twenty_kind, twenty_id, raw_stage = "opportunity", opp_id, opp.get("stage")
    elif lead_id:
        lead = await client.get_by_id(http, "leads", lead_id)
        if lead is None:
            return {"club": club.name, "skipped": "linked lead no longer exists in Twenty"}
        stage_key = _LEAD_STATUS_MAP.get(_normalize_option(lead.get("leadStatus")))
        if stage_key is None:
            return {"club": club.name, "skipped": f"unrecognised lead status {lead.get('leadStatus')!r}"}
        modules = _modules_from_twenty(lead.get("modulesToPursue") or lead.get("modulesOfInterest"))
        value_cents = None
        lost_reason = None
        twenty_kind, twenty_id, raw_stage = "lead", lead_id, lead.get("leadStatus")
    else:
        return {"club": club.name, "skipped": "no linked opportunity or lead"}

    stage = stage_by_key.get(stage_key)
    if stage is None:
        return {"club": club.name, "skipped": f"platform pipeline has no '{stage_key}' stage"}

    if value_cents is None and modules:
        value_cents = int(round(price_for(modules)["total"] * 100))

    existing = await _existing_platform_deal(session, pipeline.id, club.id)
    if existing is None:
        deal = await crm.create_deal(
            session, scope=crm.SCOPE_PLATFORM, pipeline_id=pipeline.id, stage_id=stage.id,
            title=club.name, marketing_club_id=club.id, value_cents=value_cents or 0,
            module_keys=modules, source="twenty_import",
        )
        if stage.is_won or stage.is_lost:
            await crm.move_stage(session, deal, stage)
        action = "created"
    else:
        deal = existing
        current_stage_key = next(
            (s.key for s in pipeline.stages if s.id == deal.stage_id), None)
        if _should_move(current_stage_key, stage_key):
            await crm.move_stage(session, deal, stage)
        deal.module_keys = sorted(set(deal.module_keys or []) | set(modules))
        if value_cents and value_cents > (deal.value_cents or 0):
            deal.value_cents = value_cents
        action = "updated"
    if lost_reason:
        deal.lost_reason = lost_reason

    contact = await _primary_contact(session, club.id)
    if contact is not None and (contact.full_name or contact.email):
        person = await crm.resolve_person(
            session, marketing_club_id=club.id,
            full_name=contact.full_name or contact.email, email=contact.email, phone=contact.mobile,
        )
        await crm.link_deal_contact(session, deal.id, person.id)

    note = f"Imported from Twenty ({twenty_kind}): stage={stage.name} (raw: {raw_stage!r})"
    if value_cents:
        note += f", amount=${value_cents / 100:,.2f}"
    await crm.log_activity(
        session, deal_id=deal.id, type="system", body=note,
        meta={"twenty_kind": twenty_kind, "twenty_id": twenty_id, "twenty_raw_stage": raw_stage},
    )
    return {"club": club.name, "action": action, "stage": stage.key, "value_cents": deal.value_cents}


async def main() -> None:
    if not client.configured:
        print("Twenty is not configured (TWENTY_API_URL / TWENTY_API_KEY) — nothing to do.")
        return

    linked = await _linked_clubs()
    print(f"=== {len(linked)} club(s) have a Twenty Opportunity and/or Lead linked ===")

    stats = {"created": 0, "updated": 0, "skipped": 0, "errors": 0, "no_local_club": 0}
    async with async_session_maker() as session:
        pipeline = await crm.ensure_platform_pipeline(session)
        await session.commit()
        stage_by_key = {s.key: s for s in pipeline.stages}

        async with httpx.AsyncClient() as http:
            for idx, (guid, links) in enumerate(sorted(linked.items()), start=1):
                club = (await session.execute(
                    select(MarketingClub).where(MarketingClub.grassroots_guid == guid)
                )).scalar_one_or_none()
                if club is None:
                    stats["no_local_club"] += 1
                    logger.warning("  [%d/%d] %s -> no matching marketing_clubs row", idx, len(linked), guid)
                    await asyncio.sleep(_PACE_SECONDS)
                    continue
                try:
                    result = await _import_one(http, session, pipeline, stage_by_key, club, links)
                    await session.commit()
                except Exception:  # noqa: BLE001 - one bad club can't stop the rest
                    await session.rollback()
                    stats["errors"] += 1
                    logger.exception("  [%d/%d] %s -> import failed", idx, len(linked), club.name)
                    await asyncio.sleep(_PACE_SECONDS)
                    continue

                if "skipped" in result:
                    stats["skipped"] += 1
                    logger.info("  [%d/%d] %s -> skipped: %s", idx, len(linked), club.name, result["skipped"])
                else:
                    stats[result["action"]] += 1
                    logger.info("  [%d/%d] %s -> %s (stage=%s, value_cents=%s)",
                               idx, len(linked), club.name, result["action"],
                               result["stage"], result["value_cents"])
                await asyncio.sleep(_PACE_SECONDS)

    print(f"\nDone. {stats}")
    if stats["skipped"]:
        print("Skipped deals need a manual look — check the log above for the reason "
              "(unrecognised stage/status, or a Twenty record that's since been deleted).")


if __name__ == "__main__":
    asyncio.run(main())
