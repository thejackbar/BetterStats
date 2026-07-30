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

from app.models.db import (
    User, Organisation, CommitteePosition, CommitteeTerm, CommitteeTask, CommitteeDocument, ClubEvent,
    AgendaTemplate, CommitteeMeeting, MeetingAgendaItem, MeetingMotion, AgmNomination, get_db,
)
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


async def _agenda_template_or_404(db: AsyncSession, club: Organisation, template_id: str) -> AgendaTemplate:
    t = await db.get(AgendaTemplate, uuid.UUID(template_id))
    if not t or t.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Agenda template not found")
    return t


async def _meeting_or_404(db: AsyncSession, club: Organisation, meeting_id: str) -> CommitteeMeeting:
    m = await db.get(CommitteeMeeting, uuid.UUID(meeting_id))
    if not m or m.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return m


async def _agenda_item_or_404(db: AsyncSession, club: Organisation, meeting: CommitteeMeeting, item_id: str) -> MeetingAgendaItem:
    i = await db.get(MeetingAgendaItem, uuid.UUID(item_id))
    if not i or i.meeting_id != meeting.id:
        raise HTTPException(status_code=404, detail="Agenda item not found")
    return i


async def _motion_or_404(db: AsyncSession, club: Organisation, meeting: CommitteeMeeting, motion_id: str) -> MeetingMotion:
    m = await db.get(MeetingMotion, uuid.UUID(motion_id))
    if not m or m.meeting_id != meeting.id:
        raise HTTPException(status_code=404, detail="Motion not found")
    return m


async def _nomination_or_404(db: AsyncSession, club: Organisation, meeting: CommitteeMeeting, nomination_id: str) -> AgmNomination:
    n = await db.get(AgmNomination, uuid.UUID(nomination_id))
    if not n or n.meeting_id != meeting.id:
        raise HTTPException(status_code=404, detail="Nomination not found")
    return n


# ─── Positions ────────────────────────────────────────────────────────────────

@router.get("/positions")
async def list_positions(include_inactive: bool = False, _: User = _require,
                         club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    rows = await committee_service.list_positions(db, club.id, include_inactive=include_inactive)
    # list_positions ensures/syncs a committee_position per committee role;
    # persist that so the ids returned here are real anchors for a later term.
    await db.commit()
    return {"positions": [committee_service._position_dict(p) for p in rows]}


@router.get("/positions/current")
async def positions_current(_: User = _require, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    result = await committee_service.current_holders(db, club.id)
    await db.commit()  # persists positions ensured by the sync (see list_positions)
    return result


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
    event_type_id: Optional[uuid.UUID] = None
    organiser_member_id: Optional[uuid.UUID] = None
    organiser_name: Optional[str] = None
    starts_at: datetime
    ends_at: Optional[datetime] = None
    location: Optional[str] = None
    description: Optional[str] = None
    is_ticketed: bool = False
    ticket_price_cents: int = 0
    capacity: Optional[int] = None
    registration_deadline: Optional[datetime] = None
    registration_open: bool = True


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
    event_type_id: Optional[uuid.UUID] = None
    organiser_member_id: Optional[uuid.UUID] = None
    organiser_name: Optional[str] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    location: Optional[str] = None
    description: Optional[str] = None
    is_ticketed: Optional[bool] = None
    ticket_price_cents: Optional[int] = None
    capacity: Optional[int] = None
    registration_deadline: Optional[datetime] = None
    registration_open: Optional[bool] = None


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


# ─── Agenda templates ─────────────────────────────────────────────────────────

@router.get("/agenda-templates")
async def list_agenda_templates(_: User = _require, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    rows = await committee_service.list_agenda_templates(db, club.id)
    return {"templates": [committee_service._agenda_template_dict(t) for t in rows]}


class AgendaTemplateCreate(BaseModel):
    name: str
    items: List[dict] = []


@router.post("/agenda-templates")
async def create_agenda_template(data: AgendaTemplateCreate, _: User = _require, club: Organisation = Depends(get_current_club),
                                 db: AsyncSession = Depends(get_db)):
    try:
        t = await committee_service.create_agenda_template(db, club.id, **data.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return committee_service._agenda_template_dict(t)


class AgendaTemplatePatch(BaseModel):
    name: Optional[str] = None
    items: Optional[List[dict]] = None


@router.patch("/agenda-templates/{template_id}")
async def update_agenda_template(template_id: str, data: AgendaTemplatePatch, _: User = _require,
                                 club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    t = await _agenda_template_or_404(db, club, template_id)
    await committee_service.update_agenda_template(db, t, **data.model_dump(exclude_unset=True))
    await db.commit()
    return committee_service._agenda_template_dict(t)


@router.delete("/agenda-templates/{template_id}")
async def delete_agenda_template(template_id: str, _: User = _require, club: Organisation = Depends(get_current_club),
                                 db: AsyncSession = Depends(get_db)):
    t = await _agenda_template_or_404(db, club, template_id)
    await committee_service.delete_agenda_template(db, t)
    await db.commit()
    return {"deleted": True}


# ─── Committee Meeting Assistant: meetings, attendance, agenda, motions ──────

@router.get("/meetings")
async def list_meetings(meeting_type: Optional[str] = None, _: User = _require,
                        club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    rows = await committee_service.list_meetings(db, club.id, meeting_type=meeting_type)
    return {"meetings": [committee_service._meeting_dict(m) for m in rows]}


class MeetingCreate(BaseModel):
    title: str
    meeting_type: str = "committee"
    scheduled_at: datetime
    location: Optional[str] = None
    agenda_template_id: Optional[str] = None


@router.post("/meetings")
async def create_meeting(data: MeetingCreate, _: User = _require, club: Organisation = Depends(get_current_club),
                         db: AsyncSession = Depends(get_db)):
    fields = data.model_dump()
    fields["agenda_template_id"] = uuid.UUID(fields["agenda_template_id"]) if fields.get("agenda_template_id") else None
    try:
        m = await committee_service.create_meeting(db, club.id, **fields)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return committee_service._meeting_dict(m)


@router.get("/meetings/{meeting_id}")
async def get_meeting(meeting_id: str, _: User = _require, club: Organisation = Depends(get_current_club),
                      db: AsyncSession = Depends(get_db)):
    m = await _meeting_or_404(db, club, meeting_id)
    detail = await committee_service.meeting_detail(db, club.id, m.id)
    return {**committee_service._meeting_dict(m), **detail}


class MeetingPatch(BaseModel):
    title: Optional[str] = None
    meeting_type: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    location: Optional[str] = None
    status: Optional[str] = None
    minutes: Optional[str] = None
    agenda_template_id: Optional[str] = None


@router.patch("/meetings/{meeting_id}")
async def update_meeting(meeting_id: str, data: MeetingPatch, _: User = _require, club: Organisation = Depends(get_current_club),
                         db: AsyncSession = Depends(get_db)):
    m = await _meeting_or_404(db, club, meeting_id)
    fields = data.model_dump(exclude_unset=True)
    if "agenda_template_id" in fields:
        fields["agenda_template_id"] = uuid.UUID(fields["agenda_template_id"]) if fields["agenda_template_id"] else None
    await committee_service.update_meeting(db, m, **fields)
    await db.commit()
    return committee_service._meeting_dict(m)


@router.delete("/meetings/{meeting_id}")
async def delete_meeting(meeting_id: str, _: User = _require, club: Organisation = Depends(get_current_club),
                         db: AsyncSession = Depends(get_db)):
    m = await _meeting_or_404(db, club, meeting_id)
    await committee_service.delete_meeting(db, m)
    await db.commit()
    return {"deleted": True}


class AttendanceEntry(BaseModel):
    member_id: str
    status: str = "present"


class AttendanceSet(BaseModel):
    entries: List[AttendanceEntry]


@router.put("/meetings/{meeting_id}/attendance")
async def set_attendance(meeting_id: str, data: AttendanceSet, _: User = _require, club: Organisation = Depends(get_current_club),
                         db: AsyncSession = Depends(get_db)):
    m = await _meeting_or_404(db, club, meeting_id)
    rows = await committee_service.set_attendance(
        db, m.id, [{"member_id": uuid.UUID(e.member_id), "status": e.status} for e in data.entries]
    )
    await db.commit()
    return {"attendance": [committee_service._attendance_dict(a) for a in rows]}


# ─── Agenda items ─────────────────────────────────────────────────────────────

class AgendaItemCreate(BaseModel):
    title: str
    description: Optional[str] = None
    proposed_by_member_id: Optional[str] = None
    position: int = 0


@router.post("/meetings/{meeting_id}/agenda-items")
async def create_agenda_item(meeting_id: str, data: AgendaItemCreate, _: User = _require,
                             club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    m = await _meeting_or_404(db, club, meeting_id)
    fields = data.model_dump()
    fields["proposed_by_member_id"] = uuid.UUID(fields["proposed_by_member_id"]) if fields.get("proposed_by_member_id") else None
    try:
        i = await committee_service.create_agenda_item(db, m.id, **fields)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return committee_service._agenda_item_dict(i)


class AgendaItemPatch(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    proposed_by_member_id: Optional[str] = None
    position: Optional[int] = None
    status: Optional[str] = None
    outcome_notes: Optional[str] = None


@router.patch("/meetings/{meeting_id}/agenda-items/{item_id}")
async def update_agenda_item(meeting_id: str, item_id: str, data: AgendaItemPatch, _: User = _require,
                             club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    m = await _meeting_or_404(db, club, meeting_id)
    i = await _agenda_item_or_404(db, club, m, item_id)
    fields = data.model_dump(exclude_unset=True)
    if "proposed_by_member_id" in fields:
        fields["proposed_by_member_id"] = uuid.UUID(fields["proposed_by_member_id"]) if fields["proposed_by_member_id"] else None
    await committee_service.update_agenda_item(db, i, **fields)
    await db.commit()
    return committee_service._agenda_item_dict(i)


@router.delete("/meetings/{meeting_id}/agenda-items/{item_id}")
async def delete_agenda_item(meeting_id: str, item_id: str, _: User = _require, club: Organisation = Depends(get_current_club),
                             db: AsyncSession = Depends(get_db)):
    m = await _meeting_or_404(db, club, meeting_id)
    i = await _agenda_item_or_404(db, club, m, item_id)
    await committee_service.delete_agenda_item(db, i)
    await db.commit()
    return {"deleted": True}


# ─── Motions ──────────────────────────────────────────────────────────────────

class MotionCreate(BaseModel):
    agenda_item_id: Optional[str] = None
    motion_type: str = "motion"
    description: str
    proposed_by_member_id: Optional[str] = None
    seconded_by_member_id: Optional[str] = None


@router.post("/meetings/{meeting_id}/motions")
async def create_motion(meeting_id: str, data: MotionCreate, _: User = _require, club: Organisation = Depends(get_current_club),
                        db: AsyncSession = Depends(get_db)):
    m = await _meeting_or_404(db, club, meeting_id)
    fields = data.model_dump()
    for f in ("agenda_item_id", "proposed_by_member_id", "seconded_by_member_id"):
        fields[f] = uuid.UUID(fields[f]) if fields.get(f) else None
    try:
        motion = await committee_service.create_motion(db, m.id, **fields)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return committee_service._motion_dict(motion)


class MotionPatch(BaseModel):
    agenda_item_id: Optional[str] = None
    motion_type: Optional[str] = None
    description: Optional[str] = None
    proposed_by_member_id: Optional[str] = None
    seconded_by_member_id: Optional[str] = None
    votes_for: Optional[int] = None
    votes_against: Optional[int] = None
    votes_abstain: Optional[int] = None
    outcome: Optional[str] = None
    notes: Optional[str] = None


@router.patch("/meetings/{meeting_id}/motions/{motion_id}")
async def update_motion(meeting_id: str, motion_id: str, data: MotionPatch, _: User = _require,
                        club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    m = await _meeting_or_404(db, club, meeting_id)
    motion = await _motion_or_404(db, club, m, motion_id)
    fields = data.model_dump(exclude_unset=True)
    for f in ("agenda_item_id", "proposed_by_member_id", "seconded_by_member_id"):
        if f in fields:
            fields[f] = uuid.UUID(fields[f]) if fields[f] else None
    await committee_service.update_motion(db, motion, **fields)
    await db.commit()
    return committee_service._motion_dict(motion)


@router.delete("/meetings/{meeting_id}/motions/{motion_id}")
async def delete_motion(meeting_id: str, motion_id: str, _: User = _require, club: Organisation = Depends(get_current_club),
                        db: AsyncSession = Depends(get_db)):
    m = await _meeting_or_404(db, club, meeting_id)
    motion = await _motion_or_404(db, club, m, motion_id)
    await committee_service.delete_motion(db, motion)
    await db.commit()
    return {"deleted": True}


# ─── AGM nominations ──────────────────────────────────────────────────────────

class NominationCreate(BaseModel):
    position_id: str
    candidate_member_id: str
    nominated_by_member_id: Optional[str] = None
    seconded_by_member_id: Optional[str] = None
    notes: Optional[str] = None


@router.post("/meetings/{meeting_id}/nominations")
async def create_nomination(meeting_id: str, data: NominationCreate, _: User = _require,
                            club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    m = await _meeting_or_404(db, club, meeting_id)
    await _position_or_404(db, club, data.position_id)
    fields = data.model_dump()
    fields["position_id"] = uuid.UUID(fields["position_id"])
    fields["candidate_member_id"] = uuid.UUID(fields["candidate_member_id"])
    for f in ("nominated_by_member_id", "seconded_by_member_id"):
        fields[f] = uuid.UUID(fields[f]) if fields.get(f) else None
    try:
        n = await committee_service.create_nomination(db, club.id, m.id, **fields)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return committee_service._nomination_dict(n)


class NominationPatch(BaseModel):
    nominated_by_member_id: Optional[str] = None
    seconded_by_member_id: Optional[str] = None
    votes_for: Optional[int] = None
    status: Optional[str] = None
    notes: Optional[str] = None


@router.patch("/meetings/{meeting_id}/nominations/{nomination_id}")
async def update_nomination(meeting_id: str, nomination_id: str, data: NominationPatch, _: User = _require,
                            club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    m = await _meeting_or_404(db, club, meeting_id)
    n = await _nomination_or_404(db, club, m, nomination_id)
    fields = data.model_dump(exclude_unset=True)
    for f in ("nominated_by_member_id", "seconded_by_member_id"):
        if f in fields:
            fields[f] = uuid.UUID(fields[f]) if fields[f] else None
    try:
        await committee_service.update_nomination(db, club.id, n, meeting=m, **fields)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return committee_service._nomination_dict(n)


@router.delete("/meetings/{meeting_id}/nominations/{nomination_id}")
async def delete_nomination(meeting_id: str, nomination_id: str, _: User = _require, club: Organisation = Depends(get_current_club),
                            db: AsyncSession = Depends(get_db)):
    m = await _meeting_or_404(db, club, meeting_id)
    n = await _nomination_or_404(db, club, m, nomination_id)
    await committee_service.delete_nomination(db, n)
    await db.commit()
    return {"deleted": True}
