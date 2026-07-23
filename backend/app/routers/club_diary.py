"""Club Diary API — annual/recurring compliance & maintenance task calendar.

Core capability (MANAGE_CLUB_DIARY), not a paid module — see
services/club_diary.py for why this is a NEW definition/occurrence schema
rather than a retrofit of Committee Administration's committee_tasks.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import User, Organisation, DiaryCategory, DiaryTaskDefinition, DiaryTaskOccurrence, get_db
from app.routers.auth import get_current_club
from app.auth.capabilities import require_cap, MANAGE_CLUB_DIARY
from app.services import club_diary as diary_service

router = APIRouter(prefix="/club-admin/club-diary", tags=["club-admin-club-diary"])
_require = Depends(require_cap(MANAGE_CLUB_DIARY))


async def _category_or_404(db: AsyncSession, club: Organisation, category_id: str) -> DiaryCategory:
    c = await db.get(DiaryCategory, uuid.UUID(category_id))
    if not c or c.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Category not found")
    return c


async def _definition_or_404(db: AsyncSession, club: Organisation, definition_id: str) -> DiaryTaskDefinition:
    d = await db.get(DiaryTaskDefinition, uuid.UUID(definition_id))
    if not d or d.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Task not found")
    return d


async def _occurrence_or_404(db: AsyncSession, club: Organisation, occurrence_id: str) -> DiaryTaskOccurrence:
    o = await db.get(DiaryTaskOccurrence, uuid.UUID(occurrence_id))
    if not o or o.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Occurrence not found")
    return o


# ─── Categories ───────────────────────────────────────────────────────────────

@router.get("/categories")
async def list_categories(_: User = _require, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    rows = await diary_service.list_categories(db, club.id)
    return {"categories": [diary_service._category_dict(c) for c in rows]}


class CategoryCreate(BaseModel):
    name: str


@router.post("/categories")
async def create_category(data: CategoryCreate, _: User = _require, club: Organisation = Depends(get_current_club),
                          db: AsyncSession = Depends(get_db)):
    try:
        c = await diary_service.get_or_create_category(db, club.id, data.name)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return diary_service._category_dict(c)


class CategoryPatch(BaseModel):
    name: Optional[str] = None
    sort_order: Optional[int] = None


@router.patch("/categories/{category_id}")
async def update_category(category_id: str, data: CategoryPatch, _: User = _require,
                          club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    c = await _category_or_404(db, club, category_id)
    await diary_service.update_category(db, c, **data.model_dump(exclude_unset=True))
    await db.commit()
    return diary_service._category_dict(c)


@router.delete("/categories/{category_id}")
async def delete_category(category_id: str, _: User = _require, club: Organisation = Depends(get_current_club),
                          db: AsyncSession = Depends(get_db)):
    c = await _category_or_404(db, club, category_id)
    await diary_service.delete_category(db, c)
    await db.commit()
    return {"deleted": True}


# ─── Task definitions ─────────────────────────────────────────────────────────

@router.get("/definitions")
async def list_definitions(include_inactive: bool = False, _: User = _require,
                           club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    rows = await diary_service.list_definitions(db, club.id, include_inactive=include_inactive)
    return {"definitions": [diary_service._definition_dict(d) for d in rows]}


class DefinitionCreate(BaseModel):
    title: str
    description: Optional[str] = None
    frequency: str = "annual"
    default_month: Optional[int] = None
    category_id: Optional[str] = None
    default_assignee_position_id: Optional[str] = None
    default_assignee_member_id: Optional[str] = None
    reminder_enabled: bool = False
    reminder_days_before: int = 14


@router.post("/definitions")
async def create_definition(data: DefinitionCreate, _: User = _require, club: Organisation = Depends(get_current_club),
                            db: AsyncSession = Depends(get_db)):
    fields = data.model_dump()
    for f in ("category_id", "default_assignee_position_id", "default_assignee_member_id"):
        fields[f] = uuid.UUID(fields[f]) if fields.get(f) else None
    try:
        d = await diary_service.create_definition(db, club.id, **fields)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return diary_service._definition_dict(d)


class DefinitionPatch(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    frequency: Optional[str] = None
    default_month: Optional[int] = None
    category_id: Optional[str] = None
    default_assignee_position_id: Optional[str] = None
    default_assignee_member_id: Optional[str] = None
    is_active: Optional[bool] = None
    reminder_enabled: Optional[bool] = None
    reminder_days_before: Optional[int] = None


@router.patch("/definitions/{definition_id}")
async def update_definition(definition_id: str, data: DefinitionPatch, _: User = _require,
                            club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    d = await _definition_or_404(db, club, definition_id)
    fields = data.model_dump(exclude_unset=True)
    for f in ("category_id", "default_assignee_position_id", "default_assignee_member_id"):
        if f in fields:
            fields[f] = uuid.UUID(fields[f]) if fields[f] else None
    await diary_service.update_definition(db, d, **fields)
    await db.commit()
    return diary_service._definition_dict(d)


@router.delete("/definitions/{definition_id}")
async def archive_definition(definition_id: str, _: User = _require, club: Organisation = Depends(get_current_club),
                             db: AsyncSession = Depends(get_db)):
    d = await _definition_or_404(db, club, definition_id)
    await diary_service.archive_definition(db, d)
    await db.commit()
    return {"archived": True}


@router.post("/definitions/seed-starter")
async def seed_starter_definitions(_: User = _require, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    seeded = await diary_service.seed_starter_definitions(db, club.id)
    await db.commit()
    return {"seeded": seeded}


@router.get("/definitions/{definition_id}/history")
async def definition_history(definition_id: str, _: User = _require, club: Organisation = Depends(get_current_club),
                             db: AsyncSession = Depends(get_db)):
    d = await _definition_or_404(db, club, definition_id)
    return {"history": await diary_service.history(db, d.id)}


# ─── Board + occurrences ──────────────────────────────────────────────────────

@router.get("/board")
async def board(_: User = _require, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    rows = await diary_service.board(db, club.id)
    await db.commit()  # persists any occurrences lazily created for this period
    return {"tasks": rows}


class OccurrencePatch(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    assigned_to_member_id: Optional[str] = None
    due_date: Optional[date] = None


@router.patch("/occurrences/{occurrence_id}")
async def update_occurrence(occurrence_id: str, data: OccurrencePatch, _: User = _require,
                            club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    o = await _occurrence_or_404(db, club, occurrence_id)
    fields = data.model_dump(exclude_unset=True)
    if "assigned_to_member_id" in fields:
        fields["assigned_to_member_id"] = uuid.UUID(fields["assigned_to_member_id"]) if fields["assigned_to_member_id"] else None
    await diary_service.update_occurrence(db, o, **fields)
    await db.commit()
    return diary_service._occurrence_dict(o)
