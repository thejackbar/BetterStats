"""Committee Administration API — positions/terms, task register, documents, calendar.

Core capability (MANAGE_COMMITTEE), not a paid module — see services/committee.py.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import User, Organisation, CommitteePosition, CommitteeTerm, CommitteeTask, CommitteeDocument, ClubEvent, get_db
from app.routers.auth import get_current_club
from app.auth.capabilities import require_cap, MANAGE_COMMITTEE
from app.services import committee as committee_service

router = APIRouter(prefix="/club-admin/committee", tags=["club-admin-committee"])
_require = Depends(require_cap(MANAGE_COMMITTEE))


async def _position_or_404(db: AsyncSession, club: Organisation, position_id: str) -> CommitteePosition:
    p = await db.get(CommitteePosition, uuid.UUID(position_id))
    if not p or p.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Position not found")
    return p


async def _term_or_404(db: AsyncSession, club: Organisation, term_id: str) -> CommitteeTerm:
    t = await db.get(CommitteeTerm, uuid.UUID(term_id))
    if not t or t.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Term not found")
    return t


async def _task_or_404(db: AsyncSession, club: Organisation, task_id: str) -> CommitteeTask:
    t = await db.get(CommitteeTask, uuid.UUID(task_id))
    if not t or t.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Task not found")
    return t


async def _document_or_404(db: AsyncSession, club: Organisation, doc_id: str) -> CommitteeDocument:
    d = await db.get(CommitteeDocument, uuid.UUID(doc_id))
    if not d or d.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Document not found")
    return d


async def _event_or_404(db: AsyncSession, club: Organisation, event_id: str) -> ClubEvent:
    e = await db.get(ClubEvent, uuid.UUID(event_id))
    if not e or e.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Event not found")
    return e


# ─── Positions ────────────────────────────────────────────────────────────────

@router.get("/positions")
async def list_positions(include_inactive: bool = False, _: User = _require,
                         club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    rows = await committee_service.list_positions(db, club.id, include_inactive=include_inactive)
    return {"positions": [committee_service._position_dict(p) for p in rows]}


@router.get("/positions/current")
async def positions_current(_: User = _require, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    return await committee_service.current_holders(db, club.id)


class PositionCreate(BaseModel):
    name: str
    responsibilities: Optional[str] = None
    sort_order: int = 0


@router.post("/positions")
async def create_position(data: PositionCreate, _: User = _require, club: Organisation = Depends(get_current_club),
                          db: AsyncSession = Depends(get_db)):
    try:
        p = await committee_service.create_position(db, club.id, **data.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return committee_service._position_dict(p)


class PositionPatch(BaseModel):
    name: Optional[str] = None
    responsibilities: Optional[str] = None
    sort_order: Optional[int] = None


@router.patch("/positions/{position_id}")
async def update_position(position_id: str, data: PositionPatch, _: User = _require,
                          club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    p = await _position_or_404(db, club, position_id)
    await committee_service.update_position(db, p, **data.model_dump(exclude_unset=True))
    await db.commit()
    return committee_service._position_dict(p)


@router.delete("/positions/{position_id}")
async def archive_position(position_id: str, _: User = _require, club: Organisation = Depends(get_current_club),
                           db: AsyncSession = Depends(get_db)):
    p = await _position_or_404(db, club, position_id)
    await committee_service.archive_position(db, p)
    await db.commit()
    return {"archived": True}


@router.post("/positions/seed-starter")
async def seed_starter_positions(_: User = _require, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    seeded = await committee_service.seed_starter_positions(db, club.id)
    await db.commit()
    return {"seeded": seeded}


# ─── Terms ────────────────────────────────────────────────────────────────────

@router.get("/positions/{position_id}/history")
async def position_history(position_id: str, _: User = _require, club: Organisation = Depends(get_current_club),
                           db: AsyncSession = Depends(get_db)):
    await _position_or_404(db, club, position_id)
    return {"terms": await committee_service.position_history(db, club.id, uuid.UUID(position_id))}


class TermStart(BaseModel):
    member_id: Optional[str] = None
    holder_name: str
    started_at: Optional[date] = None


@router.post("/positions/{position_id}/terms")
async def start_term(position_id: str, data: TermStart, _: User = _require, club: Organisation = Depends(get_current_club),
                     db: AsyncSession = Depends(get_db)):
    await _position_or_404(db, club, position_id)
    try:
        term = await committee_service.start_term(
            db, club.id, uuid.UUID(position_id),
            member_id=uuid.UUID(data.member_id) if data.member_id else None,
            holder_name=data.holder_name, started_at=data.started_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return committee_service._term_dict(term)


class TermPatch(BaseModel):
    holder_name: Optional[str] = None
    started_at: Optional[date] = None
    ended_at: Optional[date] = None
    handover_notes: Optional[str] = None


@router.patch("/terms/{term_id}")
async def update_term(term_id: str, data: TermPatch, _: User = _require, club: Organisation = Depends(get_current_club),
                      db: AsyncSession = Depends(get_db)):
    t = await _term_or_404(db, club, term_id)
    await committee_service.update_term(db, t, **data.model_dump(exclude_unset=True))
    await db.commit()
    return committee_service._term_dict(t)


class TermEnd(BaseModel):
    ended_at: Optional[date] = None
    handover_notes: Optional[str] = None


@router.post("/terms/{term_id}/end")
async def end_term(term_id: str, data: TermEnd, _: User = _require, club: Organisation = Depends(get_current_club),
                   db: AsyncSession = Depends(get_db)):
    t = await _term_or_404(db, club, term_id)
    await committee_service.end_term(db, t, ended_at=data.ended_at, handover_notes=data.handover_notes)
    await db.commit()
    return committee_service._term_dict(t)


# ─── Tasks ────────────────────────────────────────────────────────────────────

@router.get("/tasks")
async def list_tasks(status: Optional[str] = None, category: Optional[str] = None, _: User = _require,
                     club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    rows = await committee_service.list_tasks(db, club.id, status=status, category=category)
    return {"tasks": [committee_service._task_dict(t) for t in rows]}


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    category: str = "operational"
    position_id: Optional[str] = None
    assigned_to_member_id: Optional[str] = None
    due_date: Optional[date] = None
    is_recurring: bool = False
    recurrence_note: Optional[str] = None


@router.post("/tasks")
async def create_task(data: TaskCreate, _: User = _require, club: Organisation = Depends(get_current_club),
                      db: AsyncSession = Depends(get_db)):
    fields = data.model_dump()
    fields["position_id"] = uuid.UUID(fields["position_id"]) if fields.get("position_id") else None
    fields["assigned_to_member_id"] = uuid.UUID(fields["assigned_to_member_id"]) if fields.get("assigned_to_member_id") else None
    try:
        t = await committee_service.create_task(db, club.id, **fields)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return committee_service._task_dict(t)


class TaskPatch(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    position_id: Optional[str] = None
    assigned_to_member_id: Optional[str] = None
    due_date: Optional[date] = None
    status: Optional[str] = None
    is_recurring: Optional[bool] = None
    recurrence_note: Optional[str] = None


@router.patch("/tasks/{task_id}")
async def update_task(task_id: str, data: TaskPatch, _: User = _require, club: Organisation = Depends(get_current_club),
                      db: AsyncSession = Depends(get_db)):
    t = await _task_or_404(db, club, task_id)
    fields = data.model_dump(exclude_unset=True)
    if "position_id" in fields:
        fields["position_id"] = uuid.UUID(fields["position_id"]) if fields["position_id"] else None
    if "assigned_to_member_id" in fields:
        fields["assigned_to_member_id"] = uuid.UUID(fields["assigned_to_member_id"]) if fields["assigned_to_member_id"] else None
    await committee_service.update_task(db, t, **fields)
    await db.commit()
    return committee_service._task_dict(t)


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str, _: User = _require, club: Organisation = Depends(get_current_club),
                      db: AsyncSession = Depends(get_db)):
    t = await _task_or_404(db, club, task_id)
    await committee_service.delete_task(db, t)
    await db.commit()
    return {"deleted": True}


# ─── Documents ────────────────────────────────────────────────────────────────

@router.get("/documents")
async def list_documents(category: Optional[str] = None, _: User = _require,
                         club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    rows = await committee_service.list_documents(db, club.id, category=category)
    return {"documents": [committee_service._document_dict(d) for d in rows]}


class DocumentCreate(BaseModel):
    title: str
    category: str = "governance"
    url: str
    position_id: Optional[str] = None
    notes: Optional[str] = None


@router.post("/documents")
async def create_document(data: DocumentCreate, _: User = _require, club: Organisation = Depends(get_current_club),
                          db: AsyncSession = Depends(get_db)):
    fields = data.model_dump()
    fields["position_id"] = uuid.UUID(fields["position_id"]) if fields.get("position_id") else None
    try:
        d = await committee_service.create_document(db, club.id, **fields)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return committee_service._document_dict(d)


class DocumentPatch(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    url: Optional[str] = None
    position_id: Optional[str] = None
    notes: Optional[str] = None


@router.patch("/documents/{doc_id}")
async def update_document(doc_id: str, data: DocumentPatch, _: User = _require, club: Organisation = Depends(get_current_club),
                          db: AsyncSession = Depends(get_db)):
    d = await _document_or_404(db, club, doc_id)
    fields = data.model_dump(exclude_unset=True)
    if "position_id" in fields:
        fields["position_id"] = uuid.UUID(fields["position_id"]) if fields["position_id"] else None
    await committee_service.update_document(db, d, **fields)
    await db.commit()
    return committee_service._document_dict(d)


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, _: User = _require, club: Organisation = Depends(get_current_club),
                          db: AsyncSession = Depends(get_db)):
    d = await _document_or_404(db, club, doc_id)
    await committee_service.delete_document(db, d)
    await db.commit()
    return {"deleted": True}


# ─── Club calendar ────────────────────────────────────────────────────────────

@router.get("/events")
async def list_events(upcoming_only: bool = False, _: User = _require, club: Organisation = Depends(get_current_club),
                      db: AsyncSession = Depends(get_db)):
    rows = await committee_service.list_events(db, club.id, upcoming_only=upcoming_only)
    return {"events": [committee_service._event_dict(e) for e in rows]}


class EventCreate(BaseModel):
    title: str
    event_type: str = "other"
    starts_at: datetime
    ends_at: Optional[datetime] = None
    location: Optional[str] = None
    description: Optional[str] = None


@router.post("/events")
async def create_event(data: EventCreate, _: User = _require, club: Organisation = Depends(get_current_club),
                       db: AsyncSession = Depends(get_db)):
    try:
        e = await committee_service.create_event(db, club.id, **data.model_dump())
    except ValueError as e2:
        raise HTTPException(status_code=422, detail=str(e2))
    await db.commit()
    return committee_service._event_dict(e)


class EventPatch(BaseModel):
    title: Optional[str] = None
    event_type: Optional[str] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    location: Optional[str] = None
    description: Optional[str] = None


@router.patch("/events/{event_id}")
async def update_event(event_id: str, data: EventPatch, _: User = _require, club: Organisation = Depends(get_current_club),
                       db: AsyncSession = Depends(get_db)):
    e = await _event_or_404(db, club, event_id)
    await committee_service.update_event(db, e, **data.model_dump(exclude_unset=True))
    await db.commit()
    return committee_service._event_dict(e)


@router.delete("/events/{event_id}")
async def delete_event(event_id: str, _: User = _require, club: Organisation = Depends(get_current_club),
                       db: AsyncSession = Depends(get_db)):
    e = await _event_or_404(db, club, event_id)
    await committee_service.delete_event(db, e)
    await db.commit()
    return {"deleted": True}
