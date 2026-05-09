from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Organisation, Season, Grade
from app.database import get_db
from app.auth import get_current_user
from app.models.db import User
from app.services.sync import sync_organisation, upsert_organisation
from app.services import playhq_client
from sqlalchemy import select
import uuid

router = APIRouter(prefix="/organisations", tags=["organisations"])


@router.get("/search")
async def search_organisations(q: str = ""):
    return await playhq_client.search_organisations(q)


@router.post("/onboard", status_code=201)
async def onboard_organisation(
    data,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    background_tasks.add_task(sync_organisation, data.org_id)
    return {
        "status": "sync_started",
        "org_id": data.org_id,
    }


@router.get("/")
async def list_organisations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Organisation))
    return [{"id": str(o.id), "name": o.name, "slug": o.slug} for o in result.scalars().all()]


@router.get("/{org_id}", response_model=None)
async def get_organisation(org_id: str, db: AsyncSession = Depends(get_db)):
    org = await db.get(Organisation, uuid.UUID(org_id))
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")
    return {"id": str(org.id), "name": org.name, "slug": org.slug, "playhq_id": org.playhq_id}


@router.get("/{org_id}/seasons")
async def get_org_seasons(org_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Season)
        .where(Season.organisation_id == uuid.UUID(org_id))
        .order_by(Season.year.desc().nullslast())
    )
    return [
        {"id": str(s.id), "name": s.name, "year": s.year, "synced_at": s.synced_at}
        for s in result.scalars().all()
    ]


@router.get("/{org_id}/seasons/{season_id}/grades")
async def get_season_grades(org_id: str, season_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Grade).where(Grade.season_id == uuid.UUID(season_id))
    )
    grades = result.scalars().all()
    return [{"id": str(g.id), "name": g.name} for g in grades]


@router.get("/{org_id}/upcoming-milestones")
async def get_upcoming_milestones(
    org_id: str,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
):
    from app.services.aggregations import get_upcoming_milestones_for_org
    rows = await get_upcoming_milestones_for_org(db, org_id, limit)
    upcoming = rows[:20]
    return upcoming


@router.get("/{org_id}/recently-achieved-milestones")
async def get_recently_achieved_milestones(
    org_id: str,
    db: AsyncSession = Depends(get_db),
):
    from app.services.aggregations import get_recently_achieved_milestones_for_org
    rows = await get_recently_achieved_milestones_for_org(db, org_id)
    return rows


@router.get("/{org_id}/summary")
async def get_org_summary(
    org_id: str,
    season_id: str = None,
    grade_id: str = None,
    db: AsyncSession = Depends(get_db),
):
    from app.services.aggregations import get_club_summary
    from app.services import playhq_partner_client

    summary = await get_club_summary(db, org_id, season_id, grade_id)
    org = await db.get(Organisation, uuid.UUID(org_id))
    if org and org.playhq_id:
        db_seasons = await db.execute(
            select(Season).where(Season.organisation_id == uuid.UUID(org_id))
        )
        db_seasons_list = [{"id": str(s.id), "name": s.name} for s in db_seasons.scalars().all()]
        all_games = await playhq_partner_client.get_org_games(org.playhq_id, org.name, db_seasons=db_seasons_list, grassroots_org_id=org_id)
        summary["recent_games"] = [g for g in all_games if g.get("status") == "FINAL"][-5:][::-1]
        summary["upcoming_games"] = [g for g in all_games if g.get("status") != "FINAL"][:5]
    return summary


@router.get("/{org_id}/fixtures")
async def get_org_fixtures(org_id: str, db: AsyncSession = Depends(get_db)):
    from app.services import playhq_partner_client
    org = await db.get(Organisation, uuid.UUID(org_id))
    if not org or not org.playhq_id:
        return []
    db_seasons = await db.execute(
        select(Season).where(Season.organisation_id == uuid.UUID(org_id))
    )
    db_seasons_list = [{"id": str(s.id), "name": s.name} for s in db_seasons.scalars().all()]
    all_games = await playhq_partner_client.get_org_games(org.playhq_id, org.name, db_seasons=db_seasons_list, grassroots_org_id=org_id)
    return all_games


async def _sync_safe(org_id: str):
    from datetime import datetime, timezone
    from app.services.sync import _record_sync_log
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        await sync_organisation(org_id)
    except Exception as exc:
        import traceback, logging
        logging.getLogger(__name__).error(f"Sync crashed for {org_id}: {exc}\n{traceback.format_exc()}")
        _record_sync_log(org_id, started_at, {}, f"Unexpected error: {exc}")


@router.post("/{org_id}/sync", status_code=202)
async def trigger_sync(org_id: str, background_tasks: BackgroundTasks):
    background_tasks.add_task(_sync_safe, org_id)
    return {"status": "sync_started", "org_id": org_id}


@router.get("/{org_id}/sync-logs")
async def get_sync_logs(org_id: str):
    from app.services.sync import _sync_log
    return _sync_log.get(org_id, [])
