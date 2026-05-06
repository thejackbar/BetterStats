from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
import uuid
from datetime import date

from app.models.db import Organisation, Season, Grade, get_db
from app.services import playhq_client
from app.services.sync import sync_organisation, upsert_organisation
from app.services.aggregations import get_upcoming_milestones_for_org, get_recently_achieved_milestones_for_org, get_club_summary

router = APIRouter(prefix="/organisations", tags=["organisations"])


class OnboardRequest(BaseModel):
    org_id: str
    org_name: str = ""


class OrganisationOut(BaseModel):
    id: uuid.UUID
    name: str
    short_name: str | None

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

    await upsert_organisation(db, org_data)
    background_tasks.add_task(sync_organisation, data.org_id)

    return {
        "status": "sync_started",
        "org_id": data.org_id,
        "name": name,
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
        .order_by(Season.year.desc().nullslast(), Season.name.desc())
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
    return [{"id": str(g.id), "name": g.name} for g in grades]


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
    return await get_club_summary(db, org_id, season_id, grade_id)


@router.get("/{org_id}/fixtures")
async def get_org_fixtures(org_id: str, db: AsyncSession = Depends(get_db)):
    """Fetch upcoming fixtures from PlayHQ for the org's most recent season."""
    result = await db.execute(
        select(Season)
        .where(Season.organisation_id == uuid.UUID(org_id))
        .order_by(Season.year.desc().nullslast(), Season.name.desc())
        .limit(2)
    )
    seasons = result.scalars().all()
    if not seasons:
        return []

    today = date.today()
    upcoming = []

    for season in seasons:
        grades_result = await db.execute(
            select(Grade).where(Grade.season_id == season.id)
        )
        grades = grades_result.scalars().all()

        for grade in grades:
            try:
                fixtures = await playhq_client.get_fixtures(str(grade.id))
                for f in fixtures:
                    dt_raw = f.get("dateTime") or f.get("date") or f.get("scheduledDate")
                    if not dt_raw:
                        continue
                    try:
                        from datetime import datetime
                        fixture_date = datetime.fromisoformat(
                            dt_raw.replace("Z", "+00:00")
                        ).date()
                    except ValueError:
                        continue
                    if fixture_date >= today:
                        upcoming.append({
                            "id": f.get("id"),
                            "home_team": (f.get("homeTeam") or {}).get("name", ""),
                            "away_team": (f.get("awayTeam") or {}).get("name", ""),
                            "date": fixture_date.isoformat(),
                            "grade": grade.name,
                            "season": season.name,
                            "venue": (f.get("venue") or {}).get("name", ""),
                        })
            except Exception:
                continue

    upcoming.sort(key=lambda x: x["date"])
    return upcoming[:20]


@router.post("/{org_id}/sync", status_code=202)
async def trigger_sync(org_id: str, background_tasks: BackgroundTasks):
    background_tasks.add_task(sync_organisation, org_id)
    return {"status": "sync_started", "org_id": org_id}
