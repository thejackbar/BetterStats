import logging
import asyncio
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.models.db import async_session_maker
from app.services.sync import sync_organisation
from app.services.fees import recompute_fee_match_days
from app.services.square_sync import sync_all_square
from app.config.settings import settings

logger = logging.getLogger(__name__)

# The club-facing jobs run on the clubs' own clock. Everything already
# timezone-pinned in this file uses Perth; the sync jobs used to be the
# exception and silently ran on UTC.
PERTH = ZoneInfo("Australia/Perth")

scheduler = AsyncIOScheduler()

# How many clubs the nightly competition-grouping pass will work through.
#
# THE PLATFORM'S BACKLOG IS NOT THIS JOB'S TO DRAIN — that is what
# `app.scripts.backfill_all_associations` is for, and it clears it in one run
# because it fills most associations from our own database rather than from
# Cricket Australia. So this pass is the ongoing trickle: a season that has
# just started, or a club that has just onboarded. A club whose remaining gap
# is CA's own is skipped BEFORE any call is made, so a settled platform costs
# nothing here. The cap is only a bound on a burst.
GROUP_CLUBS_PER_RUN = 40


async def group_all_organisations():
    """Fill in the missing grade associations and group them, club by club.

    A competition is a named group of a club's grades, and a grade can only be
    put in one once Cricket Australia has told us which association ran it.
    The sync writes that as it goes, but an incremental run only scans the
    seasons that could still have been in play — so an ESTABLISHED club opens
    Manage Grades and finds fifty seasons of its own history sitting outside
    every competition, with a button as the only way to close it.

    **Deliberately NOT part of the sync.** A club that played nothing in the
    window never reaches ``sync_organisation`` (the scheduler records an idle
    run instead, see ``_record_idle_run``), so an off-season club would never
    be reached. It is also not a re-sync of anything: it pulls one cheap teams
    payload per un-associated season and touches no game, scorecard or player
    row.

    ``maybe_group_club`` owns the decision, and the reason this can be a plain
    nightly pass is that it settles: a club whose remaining gap is CA's own is
    skipped from then on. The platform's existing backlog is cleared in one go
    by ``app.scripts.backfill_all_associations``, so what reaches this job is
    the trickle — a new season, or a club that has just onboarded.
    """
    from app.services import auto_sync, competition_grouping

    async with async_session_maker() as session:
        orgs, _skipped = await auto_sync.eligible_clubs(session)

    done = 0
    for org in orgs:
        if done >= GROUP_CLUBS_PER_RUN:
            logger.info(
                "Competition grouping: reached the %d-club cap for this run",
                GROUP_CLUBS_PER_RUN)
            break
        try:
            result = await competition_grouping.maybe_group_club(org.id)
        except Exception as e:  # one club is never the whole pass
            logger.warning("Competition grouping failed for %s: %s", org.name, e)
            continue
        if result.get("ran"):
            done += 1
            logger.info(
                "Competition grouping: %s — %d season(s) checked, %d grade(s) "
                "filled, %d still unresolved",
                org.name, result.get("seasons_checked", 0),
                result.get("grades_filled", 0),
                result.get("seasons_unresolved", 0))
    logger.info("Competition grouping: grouped %d club(s) this run", done)


async def pair_all_imported_matches():
    """Re-derive which imported match is a synced match, club by club.

    A club that syncs from Cricket Australia and has also imported its
    CricketStatz history holds many of the same matches twice, and the pairing
    is what counts each one once. It runs as an import goes, after a full sync
    and once at boot — but a pass that fails, or a boot that never reached it,
    leaves the club counting both sources with nothing on screen to say so, and
    that is exactly what a club reported. This is the retry that gets them out
    of it without anybody noticing first.

    Costs nothing on a platform where it has already run: the pass re-derives
    from the data as it stands and writes only what changed, and a club holding
    no import never appears in the list at all.
    """
    from app.services import match_pairing

    async with async_session_maker() as session:
        orgs = (await session.execute(text("""
            SELECT DISTINCT organisation_id FROM manual_games
             WHERE cricketstatz_import_id IS NOT NULL
        """))).scalars().all()

    if not orgs:
        return
    changed = 0
    for org_id in orgs:
        try:
            async with async_session_maker() as session:
                result = await match_pairing.reconcile_org(session, org_id)
        except Exception as e:  # one club is never the whole pass
            logger.warning("Match pairing failed for %s: %s", org_id, e,
                           exc_info=True)
            continue
        if result.get("changed"):
            changed += 1
            logger.info("Match pairing: %s — %s", org_id, result)
    logger.info("Match pairing: %d of %d club(s) changed this run",
                changed, len(orgs))


async def repair_effective_views():
    """Put back any effective view that has lost its source clause.

    THE PAIRING IS ONLY WORTH ANYTHING IF THE VIEWS CAN ACT ON IT. Reported
    live: `v_effective_games` and `v_effective_player_season_stats` were the
    pre-pairing definitions while the other six were current, so every
    imported match was correctly paired, correctly dropped from the innings
    list, and STILL counted in the season aggregate — a career reading 15,333
    runs and 28 hundreds against the club's own 10,444 and 16.

    The boot applies all eight in one transaction and verifies them; that boot
    logged 8 of 8 and two were stale again minutes later. Postgres's own log
    named the shape of it: something outside this codebase issuing an OLDER
    definition of `v_effective_games` — a pre-266 one fails loudly with
    "cannot drop columns from view", a 266-era one has the same column list as
    ours and so REPLACES it silently, taking the pairing clause with it.

    So this is not a substitute for finding that process. It is what stops a
    club's figures doubling in the meantime, because the cost of waiting is
    paid by whoever reads their own career total. Idempotent — the same
    statements the boot runs — and it writes nothing when nothing is wrong.
    """
    from app.services import superseded_ddl

    async with async_session_maker() as session:
        missing = [v for v, ok in
                   (await superseded_ddl.verify(session)).items() if not ok]
        if not missing:
            logger.info("Effective views: 8 of 8 carry their source clause")
            return
        logger.error(
            "Effective views: %s had lost their source clause — a club "
            "holding both a CricketStatz import and a Cricket Australia sync "
            "was counting the same match twice. Re-applying.",
            ", ".join(missing))
        for stmt in superseded_ddl.STATEMENTS:
            await session.execute(text(stmt))
        await session.commit()
        still = [v for v, ok in
                 (await superseded_ddl.verify(session)).items() if not ok]
    if still:
        logger.error("Effective views STILL missing after re-applying: %s",
                     ", ".join(still))
    else:
        logger.info("Effective views: repaired %s", ", ".join(missing))


async def sync_all_organisations():
    """Pull each eligible club's recent results.

    Runs Sunday and Monday at 03:00 Perth time. Both firings do the same
    thing — fetch the fixtures played since this club's last successful sync —
    so Sunday picks up the weekend and Monday picks up anything entered
    during Sunday, without either needing to know which day it is. See
    services/auto_sync.py for the eligibility rule and the window.

    A club with no history yet, or one far enough behind that the window
    would be a full pull anyway, gets a full sync instead. That is decided
    per club by auto_sync.plan_run, not by the schedule.

    Clubs are synced one at a time, and a club with a sync already in flight
    (a manual Sync Now, a Full Rebuild, a self-heal resumed at boot) is
    skipped rather than raced — the in-memory guard the manual endpoints
    already share.
    """
    from app.services import auto_sync
    from app.routers.organisations import _org_sync_running
    from app.routers.club_admin import _hard_refresh_running

    async with async_session_maker() as session:
        orgs, skipped = await auto_sync.eligible_clubs(session)

    if skipped:
        by_reason: dict[str, int] = {}
        for _org, reason in skipped:
            by_reason[reason] = by_reason.get(reason, 0) + 1
        logger.info("Scheduled sync: skipping %d club(s) — %s", len(skipped),
                    ", ".join(f"{n} {r}" for r, n in sorted(by_reason.items())))
    logger.info(f"Starting scheduled sync for {len(orgs)} eligible organisation(s)")

    for org in orgs:
        org_id = str(org.id)
        if org_id in _org_sync_running or org_id in _hard_refresh_running:
            logger.info(f"Scheduled sync: {org.name} already has a sync in flight, skipping")
            continue
        synced = False
        try:
            async with async_session_maker() as session:
                plan = await auto_sync.plan_run(session, org.id)
            if plan["mode"] == "full":
                logger.info(f"Syncing org (full — {plan['reason']}): {org.name} ({org.id})")
                await sync_organisation(org_id, kind="org_full")
                synced = True
            else:
                # Did anything get played in this period? An empty period is
                # ordinary — the off-season, the Christmas break, a bye, a
                # washed-out round — and all of them mean there is nothing to
                # pull. Running the sync machinery to find that out would cost
                # a season-aggregate pass per club twice a week.
                probe = await auto_sync.fixtures_in_window(org_id, plan["since"])
                if not probe["sync"]:
                    logger.info("Nothing played for %s since %s (%s) — skipping",
                                org.name, plan["since"], probe["reason"])
                    await _record_idle_run(org.id, plan["since"], probe["reason"])
                    continue
                logger.info(f"Syncing org ({probe['fixtures']} fixture(s) since {plan['since']}): "
                            f"{org.name} ({org.id})")
                await sync_organisation(org_id, kind=auto_sync.RECENT_KIND, since=plan["since"])
                synced = True
        except Exception as e:
            logger.error(f"Sync failed for org {org.id}: {e}")
        if not synced:
            continue
        # Refresh auto-derived fee match-days off the freshly synced games.
        # Isolated from the sync above so a fee error never fails the sync.
        try:
            await recompute_fee_match_days(org_id)
        except Exception as e:
            logger.error(f"Fee recompute failed for org {org.id}: {e}")


async def _record_idle_run(org_id, since, reason: str) -> None:
    """Record that a club was checked and had nothing to pull.

    This is not bookkeeping for its own sake — it is what moves the club's
    watermark. Without it, a club that plays nothing for a stretch has its
    window grow every run until it crosses MAX_LOOKBACK_DAYS, at which point
    it is judged "too far behind" and handed a full historical rebuild,
    quarterly, forever, for having done nothing wrong.

    The run is genuinely successful: it asked the question and got an answer.
    Never raises — a club must not be skipped from the sync loop because its
    bookkeeping row failed to write.
    """
    from app.services.sync import start_sync_run, finish_sync_run
    from app.services import auto_sync
    try:
        run_id = await start_sync_run(org_id, auto_sync.RECENT_KIND)
        await finish_sync_run(run_id, {
            "incremental_since": since.isoformat(),
            "no_fixtures_in_window": True,
            "skip_reason": reason,
            "progress_phase": "No fixtures played in this period",
            "progress_pct": 100,
        })
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Could not record idle sync run for org {org_id}: {e}")


async def check_all_organisations_drift():
    """Ask whether Cricket Australia has revised a season we already hold.

    The counterpart to the incremental sync above: that job never looks at a
    fixture older than its window, so an upstream correction to a past season
    would otherwise sit undetected forever. This reads season aggregates only
    (three calls per season, no scorecards) for a slice of each club's
    history, and records a finding an admin acts on with Full Rebuild — see
    services/sync_drift.py. It never writes to a club's stats itself.

    Same eligibility rule as the sync, so a club we have stopped syncing is
    not one we keep checking.
    """
    from app.services import auto_sync, sync_drift

    async with async_session_maker() as session:
        orgs, _skipped = await auto_sync.eligible_clubs(session)
    logger.info(f"Starting monthly drift check for {len(orgs)} club(s)")

    flagged: list[str] = []
    for org in orgs:
        try:
            summary = await sync_drift.check_org(str(org.id))
        except Exception as e:
            logger.error(f"Drift check failed for org {org.id}: {e}")
            continue
        if summary["drifted"]:
            flagged.append(f"{org.name} ({summary['drifted']}/{summary['checked']} seasons)")
    if flagged:
        logger.warning("Drift check: historical data has changed upstream for %d club(s): %s",
                       len(flagged), "; ".join(flagged))
    else:
        logger.info("Drift check: no club's stored history disagrees with Cricket Australia")


async def settle_all_fantasy():
    """Settle any due fantasy rounds for every club running a fantasy season.

    Runs daily after the weekly sync, so a weekend's scorecards turn into fantasy
    points (and ladders) without an admin pressing a button. Idempotent — a round
    already scored is skipped, and re-running over a corrected scorecard
    recomputes in place. Each season is isolated so one failure can't stop the
    rest. Imports are local to keep the fantasy engine off the startup path.
    """
    from datetime import date
    from app.models.db import FantasySeason, FantasyRound
    from app.services import fantasy_engine

    logger.info("Starting scheduled fantasy settlement")
    async with async_session_maker() as session:
        seasons = (await session.execute(select(FantasySeason))).scalars().all()
    for fs in seasons:
        async with async_session_maker() as session:
            try:
                fs = await session.get(FantasySeason, fs.id)
                rounds = (await session.execute(
                    select(FantasyRound).where(
                        FantasyRound.fantasy_season_id == fs.id,
                        FantasyRound.status != "scored",
                        FantasyRound.end_date <= date.today(),
                    ).order_by(FantasyRound.round_number)
                )).scalars().all()
                for rnd in rounds:
                    await fantasy_engine.settle_round(session, fs, rnd)
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f"Fantasy settlement failed for season {fs.id}: {e}")


async def resolve_all_drafts():
    """Advance any in-progress draft whose pick clock has lapsed, so auto-picks
    happen even if nobody is watching the board."""
    from app.models.db import FantasyDraft, FantasyLeague, FantasySeason
    from app.services import fantasy_draft

    async with async_session_maker() as session:
        drafts = (await session.execute(
            select(FantasyDraft).where(FantasyDraft.status == "in_progress")
        )).scalars().all()
    for d in drafts:
        async with async_session_maker() as session:
            try:
                d = await session.get(FantasyDraft, d.id)
                lg = await session.get(FantasyLeague, d.league_id)
                fs = await session.get(FantasySeason, lg.fantasy_season_id)
                await fantasy_draft.resolve_overdue(session, d, fs)
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f"Draft auto-resolve failed for draft {d.id}: {e}")


async def refresh_engagement_scores():
    """Rescore EVERY club nightly and re-run the pipeline promotion.

    Usage breadcrumbs move daily, so a club's score and tier drift even when
    nothing else about it does — and the Club Directory, BetterComms
    Lists/Segments and the CRM board all read the cached number rather than
    recomputing it themselves. This is what keeps that number honest.

    No external CRM in it. This job used to push to the retired external CRM
    and returned immediately when that was not configured, only ever touching
    clubs already exported to it — so once it was retired the platform-wide
    refresh silently stopped and every cached score froze wherever it was last
    individually touched. ``crm.recalc_all_engagement`` is a local
    read/compute over our own tables with no external call in it at all."""
    from app.models.db import async_session_maker
    from app.services import crm as crm_service
    logger.info("Starting scheduled engagement rescore")
    try:
        async with async_session_maker() as session:
            stats = await crm_service.recalc_all_engagement(session)
        logger.info(f"Engagement rescore done: {stats}")
    except Exception as e:
        logger.error(f"Engagement rescore failed: {e}")


# ─── CRM Sales Pipeline auto-recompute (Tier 2 incremental + Tier 3 global) ────
# Both cadences are super-admin tunable from the pipeline's Settings modal
# (platform_settings); the intervals are applied at boot and rescheduled live on
# any change via reschedule_crm_sweeps(). max_instances=1 + coalesce keep a slow
# run from stacking on the next tick.
CRM_INCREMENTAL_JOB_ID = "crm_incremental_pipeline_sweep"
CRM_GLOBAL_JOB_ID = "crm_global_engagement_sweep"


async def crm_incremental_pipeline_sweep():
    """Tier 2 — re-score only the pipeline's OWN cards whose club had new
    telemetry since the last run (crm.recalc_pipeline_cards). The lookback is
    2x the current interval (a floor of 120s) so a delayed/coalesced tick can't
    leave a gap."""
    from app.services import crm as crm_service
    from app.services import platform_settings
    result = {"error": "did not run"}
    try:
        async with async_session_maker() as session:
            interval = await platform_settings.get_crm_incremental_sweep_seconds(session)
        result = await crm_service.recalc_pipeline_cards(lookback_seconds=max(2 * interval, 120))
        if result.get("processed") or result.get("promoted") or result.get("error"):
            logger.info(f"CRM incremental pipeline sweep: {result}")
    except Exception as e:  # noqa: BLE001
        logger.error(f"CRM incremental pipeline sweep failed: {e}")
        result = {"error": str(e)}
    finally:
        try:
            async with async_session_maker() as session:
                await platform_settings.set_crm_sweep_status(session, "incremental", result)
        except Exception:  # noqa: BLE001
            logger.exception("could not record incremental sweep status")


async def crm_global_engagement_sweep():
    """Tier 3 — the full Club-Directory recompute (app.scripts.recalc_engagement),
    the backstop that catches slow time-decay drift (a club whose score should
    have DECAYED from pure inactivity — e.g. an expired direct-enquiry Hot-100
    floor — which Tier 2 above can never catch, since it only re-scores a club
    with NEW telemetry) and anything the incremental sweep missed."""
    from app.scripts.recalc_engagement import recalc
    from app.services import platform_settings
    logger.info("Starting scheduled CRM global engagement sweep")
    stats = {"error": "did not run"}
    try:
        stats = await recalc()
        logger.info(f"CRM global engagement sweep done: {stats}")
    except Exception as e:  # noqa: BLE001
        logger.error(f"CRM global engagement sweep failed: {e}")
        stats = {"error": str(e)}
    finally:
        try:
            async with async_session_maker() as session:
                await platform_settings.set_crm_sweep_status(session, "global", stats)
        except Exception:  # noqa: BLE001
            logger.exception("could not record global sweep status")


def reschedule_crm_sweeps(*, incremental_seconds=None, global_minutes=None) -> None:
    """Apply new Tier-2 / Tier-3 cadences to the running scheduler immediately
    (no restart). Called at boot with the persisted values and again whenever a
    super admin edits them. Safe to call before the jobs exist (logs + skips)."""
    try:
        if incremental_seconds is not None:
            scheduler.reschedule_job(CRM_INCREMENTAL_JOB_ID, trigger="interval",
                                     seconds=int(incremental_seconds))
        if global_minutes is not None:
            scheduler.reschedule_job(CRM_GLOBAL_JOB_ID, trigger="interval",
                                     minutes=int(global_minutes))
    except Exception as e:  # noqa: BLE001 - job may not be registered yet
        logger.warning(f"reschedule_crm_sweeps skipped: {e}")


async def crawl_marketing_clubs():
    """Detail the next slice of the marketing club directory frontier. Off-peak,
    small nightly cap, opt-in (marketing_crawl_enabled). Resumable through the
    table, so this just walks the next batch each night until the universe is
    covered, then keeps it fresh as new clubs appear."""
    if not settings.marketing_crawl_enabled:
        return
    from app.services import club_directory
    logger.info("Starting nightly marketing club crawl")
    async with async_session_maker() as session:
        try:
            stats = await club_directory.crawl_batch(session)
            logger.info(f"Marketing club crawl batch done: {stats}")
        except Exception as e:
            logger.error(f"Marketing club crawl failed: {e}")


async def snapshot_meta_ads():
    """Pull the Meta Ads campaign/ad totals and store today's snapshot, so the HQ
    dashboard reads instantly without hitting Meta on every page load. No-op
    (logged, not raised) when the token isn't configured or Meta is unreachable —
    a bad snapshot day must never take the scheduler down."""
    if not settings.meta_ads_configured:
        return
    from app.services import meta_ads
    logger.info("Starting scheduled Meta Ads snapshot")
    async with async_session_maker() as session:
        try:
            await meta_ads.run_snapshot(session)
            logger.info("Meta Ads snapshot done")
        except Exception as e:
            await session.rollback()
            logger.error(f"Meta Ads snapshot failed: {e}")


async def sweep_module_trials():
    """Refresh the held-modules cache for any club whose module trial has passed
    its end, so the synchronous gate drops it even where the per-module rows aren't
    eager-loaded (the loaded gate already expires it read-time). Idempotent."""
    from app.services import module_subscriptions
    async with async_session_maker() as session:
        try:
            affected = await module_subscriptions.sweep_expired_trials(session)
            if affected:
                logger.info(f"Module trial sweep: refreshed {len(affected)} club(s)")
        except Exception as e:
            await session.rollback()
            logger.error(f"Module trial sweep failed: {e}")


async def send_trial_lifecycle_nudges():
    """Phase 16 (docs/self-serve-trial-onboarding-plan.md) — scan every club's
    module trials for lifecycle events (started/ending soon/ended/converted)
    and onboarding nudges (no historical data imported, a trialled module
    never opened), and email the club's own admin. Off by default —
    platform_settings.trial_nudges_enabled, checked here since it's a
    super-admin-managed flag, not an env var."""
    from app.services import platform_settings as ps
    from app.services import trial_lifecycle
    async with async_session_maker() as session:
        try:
            if not await ps.get_trial_nudges_enabled(session):
                return
            stats = await trial_lifecycle.scan_and_send(session)
            logger.info(f"Trial lifecycle nudge scan done: {stats}")
        except Exception as e:
            await session.rollback()
            logger.error(f"Trial lifecycle nudge scan failed: {e}")


async def send_member_reminders():
    """Daily qualification-expiry and fee-owing reminder emails to members,
    via the self-service portal. Gated per-club by
    platform_settings.member_portal_enabled_for_org inside
    member_reminders.send_all_reminders itself (a club with the flag off
    gets no reminders, same as the portal being invisible/unusable there)."""
    from app.services import member_reminders
    try:
        stats = await member_reminders.send_all_reminders()
        logger.info(f"Member reminder scan done: {stats}")
    except Exception as e:
        logger.error(f"Member reminder scan failed: {e}")


async def run_notification_scan():
    """Daily configurable-notification pass across every eligible club.

    Two halves in one job (see services/notification_scan.py): ask every enabled
    source what it can see and record what is new, then send each admin ONE
    digest of everything still pending for them. A club with notifications
    switched off is skipped before any query runs, and the email half is skipped
    on a club set to weekly except on its chosen day.

    Placed at the end of the daily reminder cluster, deliberately AFTER the
    results sync (01:00) and the trial/member/diary reminders: a milestone can
    only be noticed once the scorecard carrying it has landed.
    """
    from app.services import notification_scan
    try:
        stats = await notification_scan.run_all()
        logger.info(f"Notification scan done: {stats}")
    except Exception as e:
        logger.error(f"Notification scan failed: {e}")


async def send_diary_reminders():
    """Daily Club Diary reminder scan — opt-in per task definition (off by
    default), not gated by any platform flag since Club Diary is an
    always-on core feature."""
    from app.services import club_diary_reminders
    try:
        stats = await club_diary_reminders.send_all_diary_reminders()
        logger.info(f"Club Diary reminder scan done: {stats}")
    except Exception as e:
        logger.error(f"Club Diary reminder scan failed: {e}")


async def refresh_scout_players():
    """BetterScout — the actual engine behind org.refresh_cadence (a Scout
    Org setting that otherwise does nothing on its own: every refresh today
    is user-triggered via POST /scout/players/{id}/refresh). Every tracked
    au_grassroots player whose cached stats_payload is older than their own
    org's cadence gets rebuilt. Scoped to TRACKED players only — never a
    country-wide crawl, per the redesign's own "Deliberately NOT built"
    table. cadence='manual' orgs are never swept.

    Batched per CLUB, not per player or per org: due players are collected
    across EVERY org first, grouped by club_org_guid, so a club several
    orgs/scouts are tracking players at costs one rebuild for this whole
    run, not one per org or one per player (services.scout_discovery.
    refresh_club_and_apply's own docstring explains why calling
    refresh_player() N times would be wasteful here).

    Swept per ScoutedPlayerClub row, not per ScoutedPlayer — a player can
    be linked to several clubs (see models/scout.py's ScoutedPlayerClub),
    and each stint has its own staleness clock. Bucketing off ScoutedPlayer's
    own (primary-only) club_org_guid/stats_built_at, as this used to, would
    silently never refresh a player's secondary/non-primary clubs."""
    from datetime import datetime, timedelta, timezone
    from app.models.scout import ScoutedPlayer, ScoutedPlayerClub, ScoutOrg, ScoutWatchlist, ScoutWatchlistCard
    from app.services import scout_discovery
    from app.services.scout_overview import _CADENCE_DAYS

    logger.info("Starting scheduled BetterScout player refresh")
    now = datetime.now(timezone.utc)

    async with async_session_maker() as session:
        orgs = (await session.execute(select(ScoutOrg).where(ScoutOrg.is_active.is_(True)))).scalars().all()

    due_by_club: dict[str, dict] = {}
    for org in orgs:
        cadence = org.refresh_cadence or "weekly"
        if cadence == "manual":
            continue
        max_age = timedelta(days=_CADENCE_DAYS.get(cadence, 7))
        async with async_session_maker() as session:
            club_rows = (await session.execute(
                select(ScoutedPlayerClub)
                .join(ScoutedPlayer, ScoutedPlayer.id == ScoutedPlayerClub.scouted_player_id)
                .join(ScoutWatchlistCard, ScoutWatchlistCard.scouted_player_id == ScoutedPlayer.id)
                .join(ScoutWatchlist, ScoutWatchlist.id == ScoutWatchlistCard.watchlist_id)
                .where(
                    ScoutWatchlist.scout_org_id == org.id,
                    ScoutedPlayer.source == "au_grassroots",
                    ScoutedPlayerClub.grassroots_participant_id.isnot(None),
                )
                .distinct()
            )).scalars().all()
        for c in club_rows:
            built_at = c.stats_built_at
            if built_at is not None and built_at.tzinfo is None:
                built_at = built_at.replace(tzinfo=timezone.utc)
            stale = built_at is None or (now - built_at) >= max_age
            if not stale:
                continue
            bucket = due_by_club.setdefault(c.club_org_guid, {"club_name": c.club_name, "player_ids": set()})
            bucket["player_ids"].add(str(c.scouted_player_id))

    if not due_by_club:
        logger.info("BetterScout refresh: nothing due")
        return

    total_players = sum(len(b["player_ids"]) for b in due_by_club.values())
    logger.info(f"BetterScout refresh: {len(due_by_club)} club(s) due, {total_players} player(s)")

    for org_guid, bucket in due_by_club.items():
        try:
            n = await scout_discovery.refresh_club_and_apply(org_guid, bucket["club_name"], list(bucket["player_ids"]))
            logger.info(f"BetterScout refresh: {org_guid} -> {n} player(s) updated")
        except Exception as e:
            logger.error(f"BetterScout refresh failed for club {org_guid}: {e}")


async def webinar_upkeep():
    """Keep the webinar's two lists in step, then remind on the day.

    Two jobs in one hourly pass because they answer one question — is every
    registrant where they should be, and have they been told:

      1. Push anyone StreamYard does not have yet. The register route pushes
         each one as it arrives, so this only ever catches up registrations
         taken before that existed and pushes that failed on a wobble at their
         end. Bounded, and it writes nothing once everybody is across.
      2. Send the reminder, if the event's own send window is open.

    HOURLY RATHER THAN A CRON PINNED TO THE RIGHT MOMENT, and the window is
    what decides — `webinar.send_reminders` returns immediately outside it. A
    one-shot cron has to be moved by hand for the next event and misses
    entirely if the app happens to be restarting; a cheap hourly check that
    reads the event's own constant does not.
    """
    from app.models.db import async_session_maker
    from app.services import webinar

    # Nothing to keep in step once the event has been and gone.
    if not webinar.EVENT.is_past():
        try:
            async with async_session_maker() as session:
                synced = await webinar.sync_streamyard(session)
            if synced.get("considered"):
                logger.info("Webinar StreamYard sync: %s", synced)
        except Exception as e:
            logger.error(f"Webinar StreamYard sync failed: {e}")

    if not webinar.reminder_window_open():
        return
    try:
        async with async_session_maker() as session:
            result = await webinar.send_reminders(session)
        if result.get("claimed"):
            logger.info("Webinar reminders: %s", result)
    except Exception as e:
        logger.error(f"Webinar reminder sweep failed: {e}")


async def comms_daily_maintenance():
    """BetterComms daily housekeeping, run just after the AWS quota window rolls
    over (midnight UTC): (1) trip the bounce/complaint circuit breaker on any
    club over the danger line, then (2) resume campaigns whose overflow was
    deferred, now that every club has a fresh daily allowance."""
    from app.services import comms_limits
    from app.routers.comms import resume_deferred_campaigns
    try:
        summary = await comms_limits.sweep_breaker()
        if summary.get("suspended"):
            logger.warning("BetterComms breaker suspended %d club(s): %s",
                           len(summary["suspended"]),
                           ", ".join(s["name"] for s in summary["suspended"]))
    except Exception as e:
        logger.error(f"BetterComms breaker sweep failed: {e}")
    try:
        await resume_deferred_campaigns()
    except Exception as e:
        logger.error(f"BetterComms deferred resume failed: {e}")


# Hold a reference to the continuous-crawl task so it isn't garbage-collected.
_marketing_continuous_task: "asyncio.Task | None" = None


async def _run_marketing_continuous():
    """Supervisor for the continuous crawl: restart it on an unexpected crash
    (after a cool-off) so a transient blow-up doesn't silently end the backfill."""
    from app.services import club_directory
    while True:
        try:
            await club_directory.run_continuous(async_session_maker)
            return  # clean completion (refresh daemon off, frontier empty)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Marketing continuous crawl crashed, retrying in 10min: {e}")
            await asyncio.sleep(600)


def start_scheduler():
    # Results sync, Sunday and Monday at 01:00 PERTH time — the club's own
    # small hours, not UTC. Untimezoned this fired at 03:00 UTC, which is
    # 11:00 Sunday morning in WA, so a club's weekend results landed most of a
    # day after they were played. Sunday covers the weekend's fixtures, Monday
    # catches anything a scorer entered during Sunday.
    #
    # Neither run pulls the club's whole history any more; each asks only for
    # the fixtures played since that club's last successful sync. Same job for
    # both days, same id prefix, replace_existing so the old UTC "weekly_sync"
    # job is retired on deploy.
    for _day, _job_id in (("sun", "weekly_sync"), ("mon", "monday_results_sync")):
        scheduler.add_job(
            sync_all_organisations,
            trigger="cron",
            day_of_week=_day,
            hour=1,
            minute=0,
            timezone=PERTH,
            id=_job_id,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
    # Historical drift check — monthly, and it pulls nothing but season
    # aggregates. Detects that Cricket Australia has revised a past season
    # since we last synced it and flags the club for a Full Rebuild, instead
    # of blindly re-pulling every club's whole history on a timer.
    scheduler.add_job(
        check_all_organisations_drift,
        trigger="cron",
        day="1-7",
        day_of_week="sun",
        hour=5,
        minute=0,
        timezone=PERTH,
        id="monthly_drift_check",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    # Group each club's grades into the competitions they were played in.
    # Nightly, and it settles: a club with nothing left to resolve is skipped,
    # so this costs one cheap query per club once the platform has caught up.
    scheduler.add_job(
        group_all_organisations,
        trigger="cron",
        hour=2,
        minute=30,
        timezone=PERTH,
        id="nightly_competition_grouping",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    # Re-derive the CricketStatz match pairing for the clubs that hold an
    # import. The pass runs as an import goes and after a full sync; this is
    # the retry, so a boot that never reached it cannot leave a club counting
    # both its sources indefinitely.
    scheduler.add_job(
        pair_all_imported_matches,
        trigger="cron",
        hour=2,
        minute=50,
        timezone=PERTH,
        id="nightly_match_pairing",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    # A view that has lost its source clause counts a club's matches twice, so
    # the check that already runs at boot runs hourly as well. It writes
    # nothing when nothing is wrong; see repair_effective_views for why this
    # exists rather than trusting one pass through a long startup block.
    scheduler.add_job(
        repair_effective_views,
        trigger="cron",
        minute=20,
        id="hourly_effective_view_repair",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    # BetterMerch — pull Square canteen/bar stock + sales daily for connected clubs.
    scheduler.add_job(
        sync_all_square,
        trigger="cron",
        hour=4,
        minute=0,
        id="daily_square_sync",
        replace_existing=True,
    )
    # BetterFantasyCricket — settle due fantasy rounds daily (after the weekly
    # sync, and to pick up any mid-week scorecard corrections).
    scheduler.add_job(
        settle_all_fantasy,
        trigger="cron",
        hour=5,
        minute=0,
        id="daily_fantasy_settle",
        replace_existing=True,
    )
    # BetterCricket CRM — rescore EVERY club daily (usage breadcrumbs move even
    # when the club record doesn't), and re-run the pipeline promotion. Runs
    # whether or not any external CRM is configured: the score is computed from
    # our own tables and cached on the club row, which is what the Club
    # Directory, BetterComms Lists/Segments and the CRM board read.
    scheduler.add_job(
        refresh_engagement_scores,
        trigger="cron",
        hour=6,
        minute=0,
        id="daily_engagement_rescore",
        replace_existing=True,
    )
    # Self-serve trial onboarding, Phase 16 — daily scan for trial lifecycle
    # events and onboarding nudges, emailed straight to the club's own admin.
    # Right after the engagement rescore since it's conceptually adjacent (both read
    # org_module_subscriptions). No-op unless a super admin has turned it on.
    scheduler.add_job(
        send_trial_lifecycle_nudges,
        trigger="cron",
        hour=8,
        minute=0,
        id="daily_trial_lifecycle_nudges",
        replace_existing=True,
    )
    # Member self-service portal — daily qualification-expiry + fee-owing
    # reminder emails. Right after the trial nudge job for the same reason
    # (adjacent, low-traffic scans); no-op for every club until a super
    # admin switches platform_settings.member_portal_enabled on.
    scheduler.add_job(
        send_member_reminders,
        trigger="cron",
        hour=8,
        minute=30,
        id="daily_member_reminders",
        replace_existing=True,
    )
    # Club Diary — optional per-task reminder emails. Off unless an admin
    # has switched a specific task's reminder on, so this is a cheap no-op
    # scan for most clubs.
    scheduler.add_job(
        send_diary_reminders,
        trigger="cron",
        hour=8,
        minute=15,
        id="daily_club_diary_reminders",
        replace_existing=True,
    )
    # Configurable club notifications (migration 287) — raise what each club has
    # subscribed to, then send one digest per admin. 08:45 Perth, after the
    # other daily reminder scans and well after the 01:00 results sync, so a
    # milestone reached at the weekend is noticed the same morning.
    scheduler.add_job(
        run_notification_scan,
        trigger="cron",
        hour=8,
        minute=45,
        timezone=PERTH,
        id="daily_notification_scan",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    # Meta Ads HQ dashboard — hourly campaign/ad snapshot (was daily 09:00
    # Perth; hourly per direct request for the self-serve campaign launch, so
    # the dashboard tracks the live campaign through the day). Three insight
    # calls an hour is nowhere near Meta's rate limits. No-op when the token
    # isn't set. Same job id as the old daily job so replace_existing retires
    # it on deploy.
    scheduler.add_job(
        snapshot_meta_ads,
        trigger="cron",
        minute=5,
        timezone=PERTH,
        id="daily_meta_ads_snapshot",
        replace_existing=True,
    )
    # BetterFantasyCricket — advance lapsed draft clocks every 15 minutes.
    scheduler.add_job(
        resolve_all_drafts,
        trigger="interval",
        minutes=15,
        id="fantasy_draft_tick",
        replace_existing=True,
    )
    # BetterCricket CRM — Tier 1 is event-driven (crm.check_web_signal_promotion
    # fires from usage_tracker.record_event on every web/API event and from
    # ses_events on every email open/click), so a threshold-cross or a new trial
    # lands a card instantly. These two jobs are the Tier-2/Tier-3 backstops; the
    # intervals seed from the defaults here and are reconciled to the persisted,
    # super-admin-set values right after scheduler.start() (see the lifespan),
    # then rescheduled live via reschedule_crm_sweeps on any edit.
    from app.services.platform_settings import (
        DEFAULT_CRM_INCREMENTAL_SWEEP_SECONDS, DEFAULT_CRM_GLOBAL_SWEEP_MINUTES,
    )
    scheduler.add_job(
        crm_incremental_pipeline_sweep,
        trigger="interval",
        seconds=DEFAULT_CRM_INCREMENTAL_SWEEP_SECONDS,
        id=CRM_INCREMENTAL_JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        crm_global_engagement_sweep,
        trigger="interval",
        minutes=DEFAULT_CRM_GLOBAL_SWEEP_MINUTES,
        id=CRM_GLOBAL_JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    # Per-module subscriptions — sweep expired trials daily so the held-modules
    # cache drops a lapsed trial for the synchronous gate too.
    scheduler.add_job(
        sweep_module_trials,
        trigger="cron",
        hour=1,
        minute=30,
        id="daily_module_trial_sweep",
        replace_existing=True,
    )
    # BetterScout — sweep tracked players due for a refresh under their org's
    # own refresh_cadence setting. Right after the daily admin-reminder
    # cluster; batched per club so this stays cheap even as orgs grow.
    scheduler.add_job(
        refresh_scout_players,
        trigger="cron",
        hour=9,
        minute=0,
        id="daily_scout_refresh",
        replace_existing=True,
    )
    # Webinar upkeep — hourly at :20. Pushes any registrant StreamYard does not
    # have, then sends the reminder if the event's own window is open (see
    # webinar_upkeep for why hourly rather than one pinned cron). Off the hour
    # so it never lands in the same minute as the Meta Ads snapshot at :05.
    scheduler.add_job(
        webinar_upkeep,
        trigger="cron",
        minute=20,
        id="webinar_reminders",
        replace_existing=True,
    )
    # BetterComms daily maintenance — 00:15 UTC, just after AWS's daily send
    # quota resets at midnight UTC: trip the bounce/complaint breaker, then resume
    # any campaigns whose overflow was deferred to today's fresh allowance.
    scheduler.add_job(
        comms_daily_maintenance,
        trigger="cron",
        hour=0,
        minute=15,
        timezone="UTC",
        id="comms_daily_maintenance",
        replace_existing=True,
    )
    # BetterCricket outreach — crawl the national club directory. Two modes, both
    # opt-in via marketing_crawl_enabled:
    #  • continuous (marketing_crawl_continuous): a long-lived background runner
    #    that walks the whole backfill within the daily active window with
    #    organic-looking pacing. Launched as an asyncio task; nightly cron skipped.
    #  • nightly batch (default): one small capped batch at 02:00, off-peak.
    global _marketing_continuous_task
    if settings.marketing_crawl_enabled and settings.marketing_crawl_continuous:
        _marketing_continuous_task = asyncio.create_task(_run_marketing_continuous())
        marketing_mode = "continuous (windowed background runner)"
    else:
        scheduler.add_job(
            crawl_marketing_clubs,
            trigger="cron",
            hour=2,
            minute=0,
            id="nightly_marketing_crawl",
            replace_existing=True,
        )
        marketing_mode = "nightly batch 02:00"
    scheduler.start()
    logger.info("Scheduler started — marketing crawl %s, results sync Sun+Mon 01:00 Perth, "
                "drift check first Sun 05:00 Perth, Square 04:00, fantasy settle 05:00, "
                "engagement rescore 06:00, trial lifecycle nudges 08:00, notifications 08:45, "
                "BetterScout refresh 09:00, Meta Ads snapshot hourly at :05, "
                "draft tick /15min", marketing_mode)


def stop_scheduler():
    if _marketing_continuous_task is not None:
        _marketing_continuous_task.cancel()
    scheduler.shutdown(wait=False)
