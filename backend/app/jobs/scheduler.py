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
    scheduler.start()
    logger.info("Scheduler started — weekly sync Sun 03:00, Square sync daily 04:00")


def stop_scheduler():
    scheduler.shutdown(wait=False)
