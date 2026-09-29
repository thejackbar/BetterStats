"""Football admin — competitions, at the same /admin/competitions paths cricket
serves, so the shared CompetitionManager works against either backend.

Every write is cricket's own service function (services/competitions.py), so
naming, the case-folded clash check, "a grade is assigned by NAME across every
season" and "deleting un-groups, never deletes" are one rule on both sites.
Only the seed differs; see services/afl/competitions.py.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_MERGES, require_cap
from app.models.db import Organisation, User, get_db
from app.routers.auth import get_current_club, get_current_user
from app.services import competitions as comp_svc
from app.services.afl import competitions as afl_comp
from app.services.audit_log import log_activity

router = APIRouter(prefix="/admin/competitions", tags=["afl-competitions"])


class CompetitionCreate(BaseModel):
    name: str
    association_id: str | None = None


class CompetitionRename(BaseModel):
    name: str


class CompetitionAssign(BaseModel):
    grade_name: str
    competition_id: str | None = None


class CompetitionReorder(BaseModel):
    competition_ids: list[str]


@router.get("")
async def list_competitions(
    _: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    return {
        "competitions": await comp_svc.list_competitions(db, club.id),
        "grades": await comp_svc.competition_grades(db, club.id),
        # The competitions the season names imply. Filling the slot cricket
        # fills with associations is what lets the shared screen offer
        # "Group my grades" when nothing is grouped yet.
        "associations": await afl_comp.season_competitions(db, club.id),
    }


@router.get("/grouping")
async def grouping_state(
    _: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
):
    """Nothing to fetch on football: the seed reads data already held, so there
    is no background job to offer. Answered so the shared screen asks and
    draws nothing, rather than logging a 404 on every visit."""
    return {"needs_grouping": False, "running_run_id": None, "seasons_missing": 0}


@router.post("/seed")
async def seed_competitions(
    current_user: User = Depends(require_cap(MANAGE_MERGES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    result = await afl_comp.seed_from_seasons(db, club.id)
    await db.commit()
    return result


@router.post("")
async def create_competition(
    req: CompetitionCreate,
    current_user: User = Depends(require_cap(MANAGE_MERGES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    try:
        created = await comp_svc.create_competition(db, club.id, req.name, req.association_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await log_activity(db, org_id=str(club.id), user_id=current_user.id,
                       action="create_competition", target_type="competition",
                       target_id=created["id"], details={"name": created["name"]})
    await db.commit()
    return created


@router.post("/assign")
async def assign_grade(
    req: CompetitionAssign,
    current_user: User = Depends(require_cap(MANAGE_MERGES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    try:
        moved = await comp_svc.assign_grade(db, club.id, req.grade_name, req.competition_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"status": "assigned", "season_rows": moved}


@router.post("/reorder")
async def reorder_competitions(
    req: CompetitionReorder,
    current_user: User = Depends(require_cap(MANAGE_MERGES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    await comp_svc.reorder_competitions(db, club.id, req.competition_ids)
    await db.commit()
    return {"status": "reordered"}


@router.patch("/{competition_id}")
async def rename_competition(
    competition_id: str,
    req: CompetitionRename,
    current_user: User = Depends(require_cap(MANAGE_MERGES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    try:
        await comp_svc.rename_competition(db, club.id, competition_id, req.name)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await log_activity(db, org_id=str(club.id), user_id=current_user.id,
                       action="rename_competition", target_type="competition",
                       target_id=competition_id, details={"name": req.name})
    await db.commit()
    return {"status": "renamed"}


@router.delete("/{competition_id}")
async def delete_competition(
    competition_id: str,
    current_user: User = Depends(require_cap(MANAGE_MERGES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    try:
        await comp_svc.delete_competition(db, club.id, competition_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await log_activity(db, org_id=str(club.id), user_id=current_user.id,
                       action="delete_competition", target_type="competition",
                       target_id=competition_id, details={})
    await db.commit()
    return {"status": "deleted"}
