from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
import uuid

from app.models.db import Organisation, Season, Grade, get_db
from app.services import playhq_client
from app.services.sync import sync_organisation, upsert_organisation

router = APIRouter(prefix="/organisations", tags=["organisations"])


class OnboardRequest(BaseModel):
    org_id: str


class OrganisationOut(BaseModel):
    id: uuid.UUID
    name: str
    short_name: str | None

    class Config:
        from_attributes = True


@router.post("/onboard", status_code=202)
async def onboard_organisation(
    data: OnboardRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    # Validate org exists in PlayHQ
    org_data = await playhq_client.get_organisation(data.org_id)
    if not org_data:
        raise HTTPException(status_code=404, detail="Organisation not found in PlayHQ")

    # Upsert into DB
    await upsert_organisation(db, org_data)

    # Kick off background sync
    background_tasks.add_task(sync_organisation, data.org_id)

    return {
        "status": "sync_started",
        "org_id": data.org_id,
        "name": org_data.get("name"),
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
        .order_by(Season.year.desc())
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


@router.post("/{org_id}/sync", status_code=202)
async def trigger_sync(org_id: str, background_tasks: BackgroundTasks):
    background_tasks.add_task(sync_organisation, org_id)
    return {"status": "sync_started", "org_id": org_id}
