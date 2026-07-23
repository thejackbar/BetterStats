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

from app.models.db import MarketingClub, MarketingClubContact, User, async_session_maker
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


def _assignee_id_from(record: dict) -> "str | None":
    """Twenty's Opportunity/Lead "Assignee" (a WorkspaceMember relation — the
    same field family as Task.assigneeId, already used elsewhere in this
    codebase to raise a Task for a specific rep) — checked under every
    plausible key since this integration has never previously needed to READ
    this field (only ever written it, on Task). Unverified against the live
    workspace; if none of these match, _resolve_owner just returns None and
    the deal is left unassigned rather than guessing."""
    if not isinstance(record, dict):
        return None
    return (record.get("assigneeId") or (record.get("assignee") or {}).get("id")
            or record.get("assignedToId"))


async def _resolve_owner(http: httpx.AsyncClient, assignee_id: "str | None",
                         users_by_email: dict, cache: dict) -> "object | None":
    """Twenty WorkspaceMember id -> our own users.id, matched by email.
    Cached per run (a handful of reps assigned across hundreds of deals).
    Returns None (not an error) on anything unexpected — an owner Twenty
    shows correctly is a nice-to-have backfill, not something worth failing
    the whole deal import over."""
    if not assignee_id:
        return None
    if assignee_id in cache:
        return cache[assignee_id]
    owner_id = None
    try:
        member = await client.get_by_id(http, "workspaceMembers", assignee_id)
        if member:
            email = (member.get("userEmail") or member.get("email")
                     or (member.get("user") or {}).get("email") or "").strip().lower()
            if email:
                owner_id = users_by_email.get(email)
    except Exception:  # noqa: BLE001 - best-effort only
        logger.exception("twenty: failed to resolve assignee %s", assignee_id)
    cache[assignee_id] = owner_id
    return owner_id


async def _fetch_opportunity_notes(http: httpx.AsyncClient, opp_id: str) -> list:
    """Every Note attached to this Opportunity via Twenty's noteTargets join
    object — mirrors the taskTargets shape (taskId + companyId) already used
    elsewhere in this codebase for Task attachment, but for Notes this is a
    READ, never previously exercised here. Returns [] (not an error) if the
    filter/shape doesn't match live Twenty — unverified beyond the
    taskTargets pattern match."""
    try:
        payload = await client.list_page(http, "noteTargets", limit=60, filter=f"opportunityId[eq]:{opp_id}")
    except Exception:  # noqa: BLE001
        logger.exception("twenty: failed to list noteTargets for opportunity %s", opp_id)
        return []
    data = payload.get("data") if isinstance(payload, dict) else None
    targets = data.get("noteTargets") if isinstance(data, dict) else None
    notes = []
    for t in (targets or []):
        note_id = t.get("noteId") or (t.get("note") or {}).get("id")
        if not note_id:
            continue
        try:
            note = await client.get_by_id(http, "notes", note_id)
        except Exception:  # noqa: BLE001
            note = None
        if note:
            notes.append(note)
    return notes


def _note_text(note: dict) -> str:
    """Twenty's Note body may be a plain string (older workspaces) or a
    structured bodyV2 (blocknote/markdown, newer ones) — try both, fall back
    to the title so a note with no body text still leaves a trace."""
    body = note.get("body")
    if isinstance(body, str) and body.strip():
        return body.strip()
    body_v2 = note.get("bodyV2")
    if isinstance(body_v2, dict):
        md = body_v2.get("markdown")
        if isinstance(md, str) and md.strip():
            return md.strip()
    return (note.get("title") or "").strip()


async def _note_already_imported(session, deal_id, note_id: str) -> bool:
    row = (await session.execute(text(
        "SELECT 1 FROM crm_activities WHERE deal_id = :d AND meta->>'twenty_note_id' = :n LIMIT 1"),
        {"d": str(deal_id), "n": note_id})).first()
    return row is not None


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
                      club: MarketingClub, links: dict, users_by_email: dict, owner_cache: dict) -> dict:
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
        assignee_raw = _assignee_id_from(opp)
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
        assignee_raw = _assignee_id_from(lead)
        twenty_kind, twenty_id, raw_stage = "lead", lead_id, lead.get("leadStatus")
    else:
        return {"club": club.name, "skipped": "no linked opportunity or lead"}

    stage = stage_by_key.get(stage_key)
    if stage is None:
        return {"club": club.name, "skipped": f"platform pipeline has no '{stage_key}' stage"}

    if value_cents is None and modules:
        value_cents = int(round(price_for(modules)["total"] * 100))
    owner_user_id = await _resolve_owner(http, assignee_raw, users_by_email, owner_cache)

    existing = await _existing_platform_deal(session, pipeline.id, club.id)
    if existing is None:
        deal = await crm.create_deal(
            session, scope=crm.SCOPE_PLATFORM, pipeline_id=pipeline.id, stage_id=stage.id,
            title=club.name, marketing_club_id=club.id, value_cents=value_cents or 0,
            module_keys=modules, source="twenty_import", owner_user_id=owner_user_id,
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
        # Never overwrite an owner already set locally (a super admin may
        # have reassigned it directly in BetterCRM since the last run).
        if owner_user_id and not deal.owner_user_id:
            deal.owner_user_id = owner_user_id
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

    notes_imported = 0
    if opp_id:
        for tw_note in await _fetch_opportunity_notes(http, opp_id):
            note_id = tw_note.get("id")
            if not note_id or await _note_already_imported(session, deal.id, note_id):
                continue
            body_text = _note_text(tw_note)
            if not body_text:
                continue
            await crm.log_activity(
                session, deal_id=deal.id, type="note", body=body_text,
                meta={"twenty_note_id": note_id, "twenty_note_created_at": tw_note.get("createdAt")},
            )
            notes_imported += 1

    return {"club": club.name, "action": action, "stage": stage.key, "value_cents": deal.value_cents,
            "owner_matched": bool(owner_user_id), "owner_seen": bool(assignee_raw), "notes_imported": notes_imported}


async def main() -> None:
    if not client.configured:
        print("Twenty is not configured (TWENTY_API_URL / TWENTY_API_KEY) — nothing to do.")
        return

    linked = await _linked_clubs()
    print(f"=== {len(linked)} club(s) have a Twenty Opportunity and/or Lead linked ===")

    stats = {"created": 0, "updated": 0, "skipped": 0, "errors": 0, "no_local_club": 0,
             "owners_matched": 0, "owners_unmatched": 0, "notes_imported": 0}
    owner_cache: dict = {}
    async with async_session_maker() as session:
        pipeline = await crm.ensure_platform_pipeline(session)
        await session.commit()
        stage_by_key = {s.key: s for s in pipeline.stages}

        users_rows = (await session.execute(select(User.id, User.email))).all()
        users_by_email = {email.strip().lower(): uid for uid, email in users_rows if email}

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
                    result = await _import_one(http, session, pipeline, stage_by_key, club, links,
                                               users_by_email, owner_cache)
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
                    stats["notes_imported"] += result.get("notes_imported", 0)
                    if result.get("owner_seen"):
                        stats["owners_matched" if result.get("owner_matched") else "owners_unmatched"] += 1
                    logger.info("  [%d/%d] %s -> %s (stage=%s, value_cents=%s, notes=%d)",
                               idx, len(linked), club.name, result["action"],
                               result["stage"], result["value_cents"], result.get("notes_imported", 0))
                await asyncio.sleep(_PACE_SECONDS)

    print(f"\nDone. {stats}")
    if stats["skipped"]:
        print("Skipped deals need a manual look — check the log above for the reason "
              "(unrecognised stage/status, or a Twenty record that's since been deleted).")
    if stats["owners_unmatched"]:
        print(f"{stats['owners_unmatched']} deal(s) had a Twenty assignee that couldn't be matched to a "
              "BetterCricket user by email — check the log above for the assignee lookup, and that the "
              "workspaceMembers/assigneeId field names actually match this workspace's live Twenty schema "
              "(this integration never previously needed to READ that field, so it's unverified).")


if __name__ == "__main__":
    asyncio.run(main())
