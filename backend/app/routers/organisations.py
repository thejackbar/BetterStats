from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from pydantic import BaseModel
import uuid
from datetime import date

from app.models.db import Organisation, Season, Grade, get_db
from app.services import playhq_client
from app.services.sync import sync_organisation, upsert_organisation
from app.services.aggregations import get_upcoming_milestones_for_org, get_recently_achieved_milestones_for_org, get_club_summary
from app.services import playhq_partner_client

router = APIRouter(prefix="/organisations", tags=["organisations"])

_org_sync_running: set = set()


def _filter_by_season(games: list, season_obj) -> list:
    name = (season_obj.name or "").strip().lower()
    by_name = [g for g in games if g.get("season", "").strip().lower() == name]
    if by_name:
        return by_name
    year = season_obj.year
    if year:
        return [g for g in games if g.get("played_at", "")[:4] in (str(year), str(year + 1))]
    return []


class OnboardRequest(BaseModel):
    org_id: str
    org_name: str = ""


class OrganisationOut(BaseModel):
    id: uuid.UUID
    name: str
    short_name: str | None
    slug: str | None = None
    primary_color: str | None = None
    accent_color: str | None = None
    logo_url: str | None = None
    hero_image_url: str | None = None

    class Config:
        from_attributes = True


@router.get("/search")
async def search_organisations(q: str = ""):
    if not q or len(q.strip()) < 2:
        return []
    results = await playhq_client.search_organisations(q.strip())
    return results


@router.post("/onboard", status_code=202)
async def onboard_organisation(
    data: OnboardRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    org_data = await playhq_client.get_organisation(data.org_id)
    if not org_data:
        raise HTTPException(status_code=404, detail="Organisation not found")

    name = data.org_name.strip() or org_data.get("name") or data.org_id
    org_data["name"] = name

    from app.services.sync import start_sync_run
    org = await upsert_organisation(db, org_data)
    run_id = await start_sync_run(org.id, "org_full")
    background_tasks.add_task(_sync_safe, data.org_id, run_id, "org_full")

    return {
        "status": "sync_started",
        "org_id": data.org_id,
        "name": name,
        "run_id": str(run_id),
    }


@router.get("", response_model=list[OrganisationOut])
async def list_organisations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Organisation).order_by(Organisation.name))
    return result.scalars().all()


@router.get("/{org_id}", response_model=OrganisationOut)
async def get_organisation(org_id: str, db: AsyncSession = Depends(get_db)):
    org = await db.get(Organisation, uuid.UUID(org_id))
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")
    return org


@router.get("/{org_id}/seasons")
async def get_org_seasons(org_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Season)
        .where(Season.organisation_id == uuid.UUID(org_id))
        .order_by(
            Season.display_order.asc().nullslast(),
            text("CAST(SUBSTRING(seasons.name FROM '\\d{4}') AS INTEGER) DESC NULLS LAST"),
            Season.name.desc(),
        )
    )
    seasons = result.scalars().all()
    return [
        {"id": str(s.id), "name": s.name, "year": s.year, "synced_at": s.synced_at}
        for s in seasons
    ]


@router.get("/{org_id}/seasons/{season_id}/grades")
async def get_season_grades(org_id: str, season_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Grade)
        .where(Grade.season_id == uuid.UUID(season_id))
        .order_by(Grade.name)
    )
    grades = result.scalars().all()
    if grades:
        seen: set[str] = set()
        out = []
        for g in grades:
            if g.name not in seen:
                seen.add(g.name)
                out.append({"id": str(g.id), "name": g.name})
        return out

    # No grades in DB — try the cheap per-season PlayHQ endpoint (single call per season)
    try:
        api_grades = await playhq_partner_client.get_season_grades(season_id)
        if api_grades:
            return sorted(
                [{"id": g["id"], "name": g.get("name", "")} for g in api_grades if g.get("id")],
                key=lambda x: x["name"],
            )
    except Exception:
        pass
    return []


@router.get("/{org_id}/upcoming-milestones")
async def get_upcoming_milestones(
    org_id: str,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    rows = await get_upcoming_milestones_for_org(db, org_id, limit)
    return rows


@router.get("/{org_id}/recently-achieved-milestones")
async def get_recently_achieved_milestones(
    org_id: str,
    db: AsyncSession = Depends(get_db),
):
    rows = await get_recently_achieved_milestones_for_org(db, org_id)
    return rows


@router.get("/{org_id}/summary")
async def get_org_summary(
    org_id: str,
    season_id: str | None = None,
    grade_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    summary = await get_club_summary(db, org_id, season_id, grade_id)
    org = await db.get(Organisation, uuid.UUID(org_id))
    if org and org.playhq_id:
        db_seasons_res = await db.execute(
            select(Season).where(Season.organisation_id == uuid.UUID(org_id))
        )
        db_seasons = [{"id": str(s.id), "name": s.name} for s in db_seasons_res.scalars().all()]
        all_games = await playhq_partner_client.get_org_games(org.playhq_id, org.name, db_seasons=db_seasons, grassroots_org_id=str(org.id))
        final = [g for g in all_games if g.get("status") == "FINAL" and g.get("result")]
        if season_id:
            season_obj = await db.get(Season, uuid.UUID(season_id))
            if season_obj:
                final = _filter_by_season(final, season_obj)
        if grade_id:
            grade_obj = await db.get(Grade, uuid.UUID(grade_id))
            if grade_obj:
                final = [g for g in final if (g.get("grade") or {}).get("name", "").strip().lower() == grade_obj.name.strip().lower()]
        wins = sum(1 for g in final if g.get("result") == "WIN")
        losses = sum(1 for g in final if g.get("result") == "LOSS")
        draws = sum(1 for g in final if g.get("result") in ("DRAW", "TIE"))
        total = len(final)
        summary["total_games"] = total
        summary["wins"] = wins
        summary["losses"] = losses
        summary["draws"] = draws
        summary["win_rate"] = round(wins / total * 100, 1) if total > 0 else 0
    return summary


@router.get("/{org_id}/fixtures")
async def get_org_fixtures(org_id: str, db: AsyncSession = Depends(get_db)):
    """Fetch upcoming fixtures from the PlayHQ partner API."""
    org = await db.get(Organisation, uuid.UUID(org_id))
    if not org or not org.playhq_id:
        return []

    db_seasons_res = await db.execute(
        select(Season).where(Season.organisation_id == uuid.UUID(org_id))
    )
    db_seasons = [{"id": str(s.id), "name": s.name} for s in db_seasons_res.scalars().all()]
    all_games = await playhq_partner_client.get_org_games(org.playhq_id, org.name, db_seasons=db_seasons, grassroots_org_id=str(org.id))
    today = date.today()

    upcoming = [
        {
            "id": g["id"],
            "home_team": g["home_team"],
            "away_team": g["away_team"],
            "date": g["played_at"],
            "time": g.get("time"),
            "grade": (g.get("grade") or {}).get("name", ""),
            "season": g.get("season", ""),
            "round": g.get("round"),
            "venue": g.get("venue"),
        }
        for g in all_games
        if g.get("status") != "FINAL" and g.get("played_at") and g["played_at"] >= today.isoformat()
    ]
    upcoming.sort(key=lambda x: (x["date"], x.get("time") or ""))
    return upcoming[:20]


async def _sync_safe(org_id: str, run_id: uuid.UUID, kind: str = "org_full"):
    from app.services.sync import finish_sync_run
    import logging
    try:
        await sync_organisation(org_id, run_id=run_id, kind=kind)
    except Exception as exc:
        import traceback
        logging.getLogger(__name__).error(f"Sync crashed for {org_id}: {exc}\n{traceback.format_exc()}")
        await finish_sync_run(run_id, {}, f"Unexpected error: {exc}")
    finally:
        _org_sync_running.discard(org_id)


@router.post("/{org_id}/sync", status_code=202)
async def trigger_sync(org_id: str, background_tasks: BackgroundTasks):
    from app.services.sync import start_sync_run
    if org_id in _org_sync_running:
        return {"status": "already_running", "org_id": org_id}
    org_uuid = uuid.UUID(org_id)
    run_id = await start_sync_run(org_uuid, "org_full")
    _org_sync_running.add(org_id)
    background_tasks.add_task(_sync_safe, org_id, run_id, "org_full")
    return {"status": "sync_started", "org_id": org_id, "run_id": str(run_id)}


@router.get("/{org_id}/sync-logs")
async def get_sync_logs(org_id: str, db: AsyncSession = Depends(get_db)):
    from app.models.db import SyncRun
    org_uuid = uuid.UUID(org_id)
    res = await db.execute(
        select(SyncRun)
        .where(SyncRun.org_id == org_uuid)
        .order_by(SyncRun.started_at.desc())
        .limit(30)
    )
    runs = res.scalars().all()
    return [
        {
            "id": str(r.id),
            "kind": r.kind,
            "status": r.status,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "stats": r.stats or {},
            "error": r.error,
        }
        for r in runs
    ]
