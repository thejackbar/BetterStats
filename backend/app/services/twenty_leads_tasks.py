"""Twenty CRM — Lead lane + Task lane (push side).

Telemetry identifies *interest*, not a deal. So this module keeps two feeds
into Twenty fresh, both scoped to the exported subset (a ``twenty_links`` row):

- **Leads** (custom object, see bootstrap_twenty). One Lead per targeted club that
  currently shows a qualifying signal (requested a trial, in a trial, or in the
  engagement-derived sales cycle). A Lead is a passive triage item; a human converts
  it into an Opportunity by setting its ``modulesToPursue`` in Twenty. We only ever
  write the *signal* fields on refresh; ``leadStatus`` and ``modulesToPursue`` are
  human-owned (set once at create, never overwritten) so a re-run never clobbers a
  triage decision.

- **Tasks** (native Twenty object). A must-do, must-confirm action. Three sources:
  (1) an outstanding ``module_action_requests`` row (a real trial/subscribe request),
  (2) a trial about to expire, (3) a paid subscription about to renew. Each Task is
  deduped by a deterministic external ref recorded in ``twenty_links`` (entity_type
  ``task``), so the daily scan never re-raises the same one.

Manual trigger: ``refresh_leads_and_tasks`` runs all three, and is wired to a
daily 07:00 job and the on-demand ``POST /club-admin/marketing/refresh-twenty-leads-tasks``
endpoint (the twin of Refresh Twenty Scores).

NOTE: the Twenty Task shape (``status`` value ``TODO``, ``dueAt``, ``assigneeId``,
and linking via a ``taskTargets`` join record) is version-sensitive, like the rest
of the Twenty integration. Run bootstrap_twenty first (it creates the Lead object)
and verify the Task field paths against the live workspace on first run.
"""
from __future__ import annotations

import datetime
import logging
from collections import defaultdict
from typing import Optional

import httpx
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from app.models.db import MarketingClub, Organisation, async_session_maker
from app.services.twenty_client import client
from app.services.twenty_sync import (
    OPPORTUNITY_AUTO_THRESHOLD, _all_contacts_unsubscribed, _billing_modules, _engagement,
    _lifecycle, _link_get, _link_put, _module_split, _raise_task, _twenty_modules, _upsert,
)

logger = logging.getLogger(__name__)

# Look-ahead windows for the time-based Task sources (tunable).
TRIAL_REMINDER_DAYS = 7      # a trial expiring within this many days raises a Task
RENEWAL_REMINDER_DAYS = 30   # a paid renewal due within this many days raises a Task
TRIAL_TASK_LEAD_DAYS = 2     # due date this many days before the trial ends
RENEWAL_TASK_LEAD_DAYS = 14  # due date this many days before the renewal


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


# ── Lead lane ────────────────────────────────────────────────────────────────

def _lead_signal(club: MarketingClub, org: "Optional[Organisation]", eng: dict,
                 synced: bool = False):
    """Does this club qualify as a Lead right now, and if so with what source and
    modules of interest? Returns None when there's no qualifying signal (a merely
    contacted / emailed club is NOT a Lead — that would flood the inbox). Mirrors the
    trigger table: requested a trial, in a trial, in the engagement sales cycle,
    synced (an organisations row exists but the club isn't paying yet), a direct
    "onboard my club" website enquiry, or the engagement score has crossed into Hot
    territory (score >= 45)."""
    if getattr(club, "not_interested", False):
        return None
    interested = _billing_modules(club.requested_trial_modules or [])
    trial_mods = _billing_modules(club.trial_modules or [])
    trialing = (club.demo_status or "") == "in_trial" or bool(trial_mods)
    in_cycle = bool(eng.get("inSalesCycle"))
    hot_score = (eng.get("engagementScore") or 0) >= 45
    onboarding_requested = bool(eng.get("_onboardingRequested"))
    if not (interested or trialing or in_cycle or synced or hot_score or onboarding_requested):
        return None
    # Modules of interest = wanted-or-trialing, plus anything the rollup flagged as an
    # upsell (already in Twenty MULTI_SELECT form).
    wanted = sorted(interested | trial_mods)
    modules = sorted(set(_twenty_modules(wanted)) | set(eng.get("upsellModules") or []))
    # Source: pick the strongest concrete channel, else the outbound default. A direct
    # enquiry (the "Get your club" modal or the /contact "Request access" form) is the
    # single strongest signal, so it wins even over an admin-set trial flag.
    if onboarding_requested:
        source = "CONTACT_US"
    elif interested or trialing:
        source = "WEBSITE"
    elif eng.get("emailEngaged30d"):
        source = "EMAIL_ENGAGEMENT"
    else:
        source = "OUTBOUND_CAMPAIGN"
    tier = eng.get("engagementTier") or "COLD"
    summary = (f"Tier {tier.title()}; sessions30d={eng.get('sessions30d', 0)}, "
               f"emailEng30d={eng.get('emailEngaged30d', 0)}"
               + (f"; interested={wanted}" if wanted else "")
               + ("; club synced, no paid module yet" if synced else "")
               + ("; asked to be onboarded via the website" if onboarding_requested else ""))
    # Working if a trial is already live, else New — set once at create only.
    status = "WORKING" if trialing else "NEW"
    return {"source": source, "modules": modules, "tier": tier,
            "score": eng.get("engagementScore") or 0,
            "summary": summary[:400], "status": status}


def _lead_values(sig: dict, lifecycle_stage: str) -> dict:
    """The refreshable signal fields written on every run."""
    return {
        "leadSource": sig["source"],
        "signalSummary": sig["summary"],
        "engagementScore": sig["score"],         # mirrors company.engagementScore
        "lifecycleStage": lifecycle_stage,       # mirrors company.lifecycleStage
        "engagementTier": sig["tier"],           # same option values as company.engagementTier
        "modulesOfInterest": sig["modules"],
    }


async def upsert_lead_for_club(session, http, club: MarketingClub, org: "Optional[Organisation]",
                               company_tid: str, eng: dict,
                               lifecycle_override: "Optional[str]" = None) -> "Optional[str]":
    """Create or refresh the Lead for ONE club, given an already-computed engagement
    rollup and the Company's Twenty id. The single-club counterpart to
    ``_seed_and_refresh_leads``'s daily batch sweep (which only ever looks at clubs
    already in ``twenty_links``) — used for an immediate push where the caller
    already has the Company upsert's result in hand and can't wait for tomorrow's
    07:00 refresh to notice the signal (see ``twenty_sync.push_onboarding_enquiry``,
    for a direct "onboard my club" enquiry). Returns the Lead's Twenty id, or None
    if it doesn't currently qualify (see ``_lead_signal``) or every contact has
    opted out.

    ``lifecycle_override`` (used by ``push_self_serve_registration``) forces the
    Lead's ``lifecycleStage`` — e.g. "SELF_SERVE_TRIAL" — via ``create_extra``, so
    it wins over the normally-computed value ONLY at creation (``_upsert`` merges
    ``create_extra`` over ``values`` on create, never on update — see its
    docstring). Note this is a creation-moment marker, not a permanent one: the
    next daily Lead refresh (``_seed_and_refresh_leads``) recomputes
    ``lifecycleStage`` from the ordinary engagement model like any other Lead and
    will overwrite it, the same way every other field here behaves."""
    paid, _trial, _renewals = _module_split(org) if org is not None else ([], [], [])
    is_paying = bool(paid) or (club.demo_status or "") == "customer"
    all_unsub = await _all_contacts_unsubscribed(session, club.id)
    if all_unsub and not is_paying:
        return None
    synced = bool(club.existing_org_id) and not is_paying
    sig = _lead_signal(club, org, eng, synced=synced)
    if sig is None:
        return None
    values = _lead_values(sig, _lifecycle(club, is_paying, all_unsub))
    values["name"] = club.name
    create_extra = {"bcLeadKey": club.grassroots_guid, "leadStatus": sig["status"],
                    "companyId": company_tid}
    if lifecycle_override:
        create_extra["lifecycleStage"] = lifecycle_override
    lid, _act = await _upsert(
        session, http, "lead", club.grassroots_guid, "leads", "bcLeadKey", values,
        create_extra=create_extra)
    return lid


async def _seed_and_refresh_leads(session, http, stats) -> None:
    """Create or refresh a Lead for every exported club that qualifies now. Snapshot
    the ORM data before the IO loop (same greenlet-safety pattern as the export)."""
    rows = (await session.execute(text(
        "SELECT bc_id, twenty_id FROM twenty_links WHERE entity_type = 'club'"))).all()
    tid_by_guid = {r[0]: r[1] for r in rows}
    guids = list(tid_by_guid)
    if not guids:
        return
    # Ordered by id so this bulk UPDATE always locks marketing_clubs rows in the
    # same sequence as refresh_engagement's equivalent bulk load — two unordered
    # loads over an overlapping row set can lock in opposite order when run
    # concurrently (the two Refresh buttons, or the daily 06:00/07:00 jobs
    # overlapping this), which is a textbook Postgres deadlock. Consistent lock
    # order rules that out.
    clubs = {c.grassroots_guid: c for c in (await session.execute(
        select(MarketingClub).where(MarketingClub.grassroots_guid.in_(guids))
        .order_by(MarketingClub.id))).scalars().all()}

    snaps = []
    scanned = 0
    for guid in guids:
        club = clubs.get(guid)
        if club is None:
            continue
        scanned += 1
        org = (await session.get(
                    Organisation, club.existing_org_id,
                    options=[selectinload(Organisation.module_subscriptions)])
               if club.existing_org_id else None)
        paid, _trial, _renewals = _module_split(org) if org is not None else ([], [], [])
        is_paying = bool(paid) or (club.demo_status or "") == "customer"
        all_unsub = await _all_contacts_unsubscribed(session, club.id)
        if all_unsub and not is_paying:
            # Every officer has opted out — discard any existing Lead instead of
            # (re)qualifying one for a fully-suppressed club.
            lead_row = await _link_get(session, "lead", guid)
            if lead_row:
                try:
                    await client.update(http, "leads", lead_row[0], {"leadStatus": "DISCARDED"})
                    stats["leads_discarded"] += 1
                except Exception:  # noqa: BLE001
                    logger.exception("twenty lead discard failed for suppressed club %s", guid)
            continue
        eng = await _engagement(session, club, org)
        # "We sync the club" (an organisations row exists) is itself a qualifying
        # Lead signal while it isn't yet paying — a customer already in the
        # engagement sales cycle qualifies through in_cycle/upsell instead.
        synced = bool(club.existing_org_id) and not is_paying
        sig = _lead_signal(club, org, eng, synced=synced)
        if sig is None:
            continue
        values = _lead_values(sig, _lifecycle(club, is_paying, all_unsub))
        values["name"] = club.name          # the Lead's display name = the club name
        # "Top performer" auto-promotion: a prospect (never a paying customer —
        # those already have a real deal) whose engagement score has crossed
        # OPPORTUNITY_AUTO_THRESHOLD earns an Opportunity automatically on
        # whichever refresh first notices it, rather than waiting on a human to
        # flip Twenty's own createOpportunity cascade field. Checked here so a
        # self-serve trial club that keeps digging into the product (historical
        # import, merges, module trial usage — services/trial_engagement.py)
        # gets promoted the moment it earns it, not just at registration.
        auto_opportunity = not is_paying and org is not None and (eng.get("engagementScore") or 0) >= OPPORTUNITY_AUTO_THRESHOLD
        snaps.append((guid, tid_by_guid[guid], values, sig["status"], club, auto_opportunity))
    # Diagnostics so the caller/UI can see WHY the result is what it is — a cold list
    # with no interest signals reads 0 qualified, which is correct, not a failure.
    stats["clubs_scanned"] += scanned
    stats["leads_qualified"] += len(snaps)

    # _engagement() above (called on EVERY scanned club, not just qualifying ones)
    # now caches engagement_score/.engagement_tier onto each club row. Commit here,
    # before the loop below — which only runs `snaps` times — so a run that
    # qualifies zero Leads doesn't silently discard every cache write.
    await session.commit()

    for guid, company_tid, values, status, club, auto_opportunity in snaps:
        try:
            _, act = await _upsert(
                session, http, "lead", guid, "leads", "bcLeadKey", values,
                create_extra={"bcLeadKey": guid, "leadStatus": status,
                              "companyId": company_tid})
            stats["leads_" + act] += 1
        except Exception:  # noqa: BLE001 — one bad lead can't stop the rest
            stats["leads_errored"] += 1
            logger.exception("twenty lead upsert failed for club %s", guid)
        if auto_opportunity:
            try:
                # Once only — an existing Opportunity is the human's deal to
                # manage from here, never overwritten by a later refresh.
                existing = await _link_get(session, "opportunity", guid)
                if not existing:
                    from app.services import twenty_opportunity
                    modules = twenty_opportunity._default_modules(club)
                    await twenty_opportunity._upsert_opportunity(
                        session, http, club, company_tid, modules, stage="SELF_SERVE_TRIAL")
                    stats["opportunities_auto_created"] += 1
            except Exception:  # noqa: BLE001 — one bad opportunity can't stop the rest
                stats["opportunities_errored"] += 1
                logger.exception("twenty auto-opportunity failed for club %s", guid)
        await session.commit()


# ── Task lane ────────────────────────────────────────────────────────────────

async def _create_task(session, http, ext_ref: str, title: str,
                       company_tid: Optional[str], due_at, stats, kind: str) -> None:
    """Create one Twenty Task, deduped on ``ext_ref`` via twenty_links (delegates to
    the shared ``twenty_sync._raise_task``). No-op if a Task for this ref already
    exists, so the daily scan never doubles up."""
    already = await _link_get(session, "task", ext_ref)
    tid = await _raise_task(session, http, ext_ref, title, company_tid, due_at)
    if tid is None and not already:
        stats["tasks_errored"] += 1
        return
    if tid is not None:
        stats["tasks_" + kind] += 1


async def _company_tid(session, guid: Optional[str]) -> Optional[str]:
    if not guid:
        return None
    row = await _link_get(session, "club", guid)
    return row[0] if row else None


async def _mirror_requests_to_tasks(session, http, stats) -> None:
    """Mirror every OUTSTANDING module_action_request to a Twenty Task, so a pending
    trial/subscribe request surfaces in the CRM action queue. Only for clubs already
    in the CRM (a twenty_links club row)."""
    rows = (await session.execute(text("""
        SELECT r.id, r.module_key, r.kind, o.subscription_status, mc.grassroots_guid, mc.name
        FROM module_action_requests r
        JOIN organisations o ON o.id = r.organisation_id
        JOIN marketing_clubs mc ON mc.existing_org_id = o.id
        JOIN twenty_links tl ON tl.entity_type = 'club' AND tl.bc_id = mc.grassroots_guid
        WHERE r.status = 'outstanding'
    """))).all()
    stats["requests_outstanding"] += len(rows)
    for req_id, module_key, kind, sub_status, guid, name in rows:
        ext_ref = f"req:{req_id}"
        # A brand-new club (no live subscription yet) needs a sync + BetterStats trial
        # first; an existing club just needs the module enabling.
        established = (sub_status or "").lower() in ("active", "trial", "past_due")
        mod = (module_key or "").upper()
        if not established:
            title = f"Set up {name}: initiate sync + start BetterStats trial ({mod} requested)"
        else:
            title = f"Enable {mod} {kind} for {name}"
        due = _now() + datetime.timedelta(days=3)
        await _create_task(session, http, ext_ref, title,
                           await _company_tid(session, guid), due, stats, "request")
        await session.commit()


async def _scan_trials_and_renewals(session, http, stats) -> None:
    """Time-based Task sources: trials about to expire and paid renewals coming due.
    Deduped per (subscription, date) so a daily run raises each reminder once."""
    now = _now()
    # 1. Expiring trials.
    trial_rows = (await session.execute(text("""
        SELECT s.id, s.module_key, s.trial_ends_at, mc.grassroots_guid, mc.name
        FROM org_module_subscriptions s
        JOIN marketing_clubs mc ON mc.existing_org_id = s.organisation_id
        JOIN twenty_links tl ON tl.entity_type = 'club' AND tl.bc_id = mc.grassroots_guid
        WHERE s.status = 'trial' AND s.trial_ends_at IS NOT NULL
          AND s.trial_ends_at BETWEEN :now AND :horizon
    """), {"now": now, "horizon": now + datetime.timedelta(days=TRIAL_REMINDER_DAYS)})).all()
    stats["trials_in_window"] += len(trial_rows)
    for sub_id, module_key, ends_at, guid, name in trial_rows:
        ext_ref = f"trial_end:{sub_id}:{ends_at.date()}"
        title = (f"Trial ending {ends_at.date()}: {(module_key or '').upper()} for {name} "
                 f"— follow up to convert")
        due = ends_at - datetime.timedelta(days=TRIAL_TASK_LEAD_DAYS)
        await _create_task(session, http, ext_ref, title,
                           await _company_tid(session, guid), due, stats, "trial_expiry")
        await session.commit()

    # 2. Upcoming paid renewals (per-module renewal date).
    renewal_rows = (await session.execute(text("""
        SELECT s.id, s.module_key, s.renewal_date, mc.grassroots_guid, mc.name
        FROM org_module_subscriptions s
        JOIN marketing_clubs mc ON mc.existing_org_id = s.organisation_id
        JOIN twenty_links tl ON tl.entity_type = 'club' AND tl.bc_id = mc.grassroots_guid
        WHERE s.status IN ('active', 'past_due') AND s.renewal_date IS NOT NULL
          AND s.renewal_date BETWEEN :today AND :horizon
    """), {"today": now.date(),
           "horizon": (now + datetime.timedelta(days=RENEWAL_REMINDER_DAYS)).date()})).all()
    stats["renewals_in_window"] += len(renewal_rows)
    for sub_id, module_key, renewal_date, guid, name in renewal_rows:
        ext_ref = f"renewal:{sub_id}:{renewal_date}"
        title = (f"Renewal due {renewal_date}: {(module_key or '').upper()} for {name} "
                 f"— confirm renewal")
        due = datetime.datetime.combine(
            renewal_date - datetime.timedelta(days=RENEWAL_TASK_LEAD_DAYS),
            datetime.time.min, tzinfo=datetime.timezone.utc)
        await _create_task(session, http, ext_ref, title,
                           await _company_tid(session, guid), due, stats, "renewal")
        await session.commit()


# ── Orchestrator (manual trigger + daily job) ────────────────────────────────

async def refresh_leads_and_tasks() -> dict:
    """Run all three feeds: seed/refresh Leads, mirror outstanding requests to Tasks,
    and scan trials + renewals. Idempotent (every write is keyed), so it's safe to
    press on demand or run daily. Never raises: failures are counted and logged.

    This is the go-live seed AND the steady-state refresh in one — the first run
    backfills whatever already qualifies; later runs only add what's new."""
    if not client.configured:
        return {"error": "Twenty is not configured."}
    stats: dict = defaultdict(int)
    try:
        async with async_session_maker() as session:
            session.sync_session.expire_on_commit = False
            async with httpx.AsyncClient() as http:
                await _seed_and_refresh_leads(session, http, stats)
                await _mirror_requests_to_tasks(session, http, stats)
                await _scan_trials_and_renewals(session, http, stats)
    except Exception as e:  # noqa: BLE001 — never bubble a 500 to the UI/scheduler
        logger.exception("twenty refresh_leads_and_tasks top-level failure")
        return {"error": f"refresh failed: {e}", **stats}
    return {**stats}
