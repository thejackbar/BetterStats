import logging
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.db import Organisation, async_session_maker
from app.services.sync import sync_organisation
from app.services.fees import recompute_fee_match_days
from app.services.square_sync import sync_all_square

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
    # BetterFantasyCricket — advance lapsed draft clocks every 15 minutes.
    scheduler.add_job(
        resolve_all_drafts,
        trigger="interval",
        minutes=15,
        id="fantasy_draft_tick",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started — weekly sync Sun 03:00, Square 04:00, fantasy settle 05:00, draft tick /15min")


def stop_scheduler():
    scheduler.shutdown(wait=False)
