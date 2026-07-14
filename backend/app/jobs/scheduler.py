import logging
import asyncio
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.db import Organisation, async_session_maker
from app.services.sync import sync_organisation
from app.services.fees import recompute_fee_match_days
from app.services.square_sync import sync_all_square
from app.config.settings import settings

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def sync_all_organisations():
    logger.info("Starting scheduled sync for all organisations")
    async with async_session_maker() as session:
        result = await session.execute(select(Organisation))
        orgs = result.scalars().all()

    for org in orgs:
        try:
            logger.info(f"Syncing org: {org.name} ({org.id})")
            await sync_organisation(str(org.id))
        except Exception as e:
            logger.error(f"Sync failed for org {org.id}: {e}")
        # Refresh auto-derived fee match-days off the freshly synced games.
        # Isolated from the sync above so a fee error never fails the sync.
        try:
            await recompute_fee_match_days(str(org.id))
        except Exception as e:
            logger.error(f"Fee recompute failed for org {org.id}: {e}")


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


async def refresh_twenty_engagement():
    """Recompute each exported club's engagement rollup (usage breadcrumbs move
    daily, so the score/tier drifts even when nothing else about the club does)
    and PATCH it onto its Twenty Company. Skipped unless Twenty is configured."""
    if not settings.twenty_configured:
        return
    from app.services import twenty_sync
    logger.info("Starting scheduled Twenty engagement refresh")
    try:
        stats = await twenty_sync.refresh_engagement()
        logger.info(f"Twenty engagement refresh done: {stats}")
    except Exception as e:
        logger.error(f"Twenty engagement refresh failed: {e}")


async def refresh_twenty_leads_tasks():
    """Seed/refresh Leads from telemetry, mirror outstanding module requests to Tasks,
    and scan trials + renewals into follow-up Tasks. Idempotent; the first run also
    backfills whatever already qualifies. Skipped unless Twenty is configured."""
    if not settings.twenty_configured:
        return
    from app.services import twenty_leads_tasks
    logger.info("Starting scheduled Twenty leads/tasks refresh")
    try:
        stats = await twenty_leads_tasks.refresh_leads_and_tasks()
        logger.info(f"Twenty leads/tasks refresh done: {stats}")
    except Exception as e:
        logger.error(f"Twenty leads/tasks refresh failed: {e}")


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
    # Weekly sync every Sunday at 3am
    scheduler.add_job(
        sync_all_organisations,
        trigger="cron",
        day_of_week="sun",
        hour=3,
        minute=0,
        id="weekly_sync",
        replace_existing=True,
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
    # BetterCricket CRM — refresh each exported club's engagement score daily
    # (usage breadcrumbs move even when the club record doesn't). No-op when
    # Twenty isn't configured.
    scheduler.add_job(
        refresh_twenty_engagement,
        trigger="cron",
        hour=6,
        minute=0,
        id="daily_twenty_engagement",
        replace_existing=True,
    )
    # BetterCricket CRM — seed/refresh Leads from telemetry and raise follow-up Tasks
    # (outstanding module requests, expiring trials, upcoming renewals) daily. No-op
    # when Twenty isn't configured.
    scheduler.add_job(
        refresh_twenty_leads_tasks,
        trigger="cron",
        hour=7,
        minute=0,
        id="daily_twenty_leads_tasks",
        replace_existing=True,
    )
    # Self-serve trial onboarding, Phase 16 — daily scan for trial lifecycle
    # events and onboarding nudges, emailed straight to the club's own admin.
    # Right after the Twenty scan since it's conceptually adjacent (both read
    # org_module_subscriptions). No-op unless a super admin has turned it on.
    scheduler.add_job(
        send_trial_lifecycle_nudges,
        trigger="cron",
        hour=8,
        minute=0,
        id="daily_trial_lifecycle_nudges",
        replace_existing=True,
    )
    # Meta Ads HQ dashboard — daily campaign/ad snapshot at 09:00 Perth time (the
    # spec's "refreshed by a daily 9am job"). No-op when the token isn't set.
    scheduler.add_job(
        snapshot_meta_ads,
        trigger="cron",
        hour=9,
        minute=0,
        timezone=ZoneInfo("Australia/Perth"),
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
    logger.info("Scheduler started — marketing crawl %s, weekly sync Sun 03:00, "
                "Square 04:00, fantasy settle 05:00, Twenty engagement 06:00, "
                "trial lifecycle nudges 08:00, Meta Ads snapshot 09:00 Perth, "
                "draft tick /15min", marketing_mode)


def stop_scheduler():
    if _marketing_continuous_task is not None:
        _marketing_continuous_task.cancel()
    scheduler.shutdown(wait=False)
