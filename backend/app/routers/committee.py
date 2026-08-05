"""Committee Administration API — positions/terms, task register, documents, calendar.

Core capability (MANAGE_COMMITTEE), not a paid module — see services/committee.py.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import (
    User, Organisation, CommitteePosition, CommitteeTerm, CommitteeTask, CommitteeDocument, ClubEvent,
    AgendaTemplate, CommitteeMeeting, MeetingAgendaItem, MeetingMotion, AgmNomination, get_db,
)
from app.routers.auth import get_current_club
from app.auth.capabilities import require_cap, MANAGE_COMMITTEE
from app.services import committee as committee_service
from app.services import office_bearers

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


class PositionReorder(BaseModel):
    position_ids: List[str]


@router.post("/positions/reorder")
async def reorder_positions(data: PositionReorder, _: User = _require, club: Organisation = Depends(get_current_club),
                            db: AsyncSession = Depends(get_db)):
    ids = [uuid.UUID(x) for x in data.position_ids]
    await committee_service.reorder_positions(db, club.id, ids)
    await db.commit()
    return {"ok": True}


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
    await committee_service.load_task_dependencies(db, rows)
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
    # Migration 217 — the planning side of an action.
    objective_id: Optional[str] = None
    budget_estimate: Optional[float] = None
    actual_expenditure: Optional[float] = None
    percent_complete: Optional[int] = None
    start_date: Optional[date] = None
    outcome_notes: Optional[str] = None
    meeting_id: Optional[str] = None
    motion_id: Optional[str] = None
    # Migration 220 — raised under an agenda item, and owned by one or more
    # people. `assignee_member_ids` wins over `assigned_to_member_id` when both
    # are sent; the single column stays the primary owner.
    agenda_item_id: Optional[str] = None
    assignee_member_ids: Optional[List[str]] = None


@router.post("/tasks")
async def create_task(data: TaskCreate, _: User = _require, club: Organisation = Depends(get_current_club),
                      db: AsyncSession = Depends(get_db)):
    fields = data.model_dump()
    for key in ("position_id", "assigned_to_member_id", "objective_id", "meeting_id", "motion_id", "closed_by_member_id", "agenda_item_id"):
        if key in fields:
            fields[key] = uuid.UUID(fields[key]) if fields.get(key) else None
    assignees = fields.pop("assignee_member_ids", None)
    try:
        t = await committee_service.create_task(db, club.id, **fields)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if assignees is not None:
        await committee_service.set_task_assignees(db, t, [uuid.UUID(a) for a in assignees])
    await db.commit()
    await db.refresh(t)   # commit expires it; _task_dict would lazy-load outside the greenlet
    await committee_service.load_task_assignees(db, [t])
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
    # Migration 217 — the planning side of an action.
    objective_id: Optional[str] = None
    budget_estimate: Optional[float] = None
    actual_expenditure: Optional[float] = None
    percent_complete: Optional[int] = None
    start_date: Optional[date] = None
    outcome_notes: Optional[str] = None
    meeting_id: Optional[str] = None
    motion_id: Optional[str] = None
    # Migration 220 — raised under an agenda item, and owned by one or more
    # people. `assignee_member_ids` wins over `assigned_to_member_id` when both
    # are sent; the single column stays the primary owner.
    agenda_item_id: Optional[str] = None
    assignee_member_ids: Optional[List[str]] = None
    closed_by_member_id: Optional[str] = None


@router.patch("/tasks/{task_id}")
async def update_task(task_id: str, data: TaskPatch, _: User = _require, club: Organisation = Depends(get_current_club),
                      db: AsyncSession = Depends(get_db)):
    t = await _task_or_404(db, club, task_id)
    fields = data.model_dump(exclude_unset=True)
    for key in ("position_id", "assigned_to_member_id", "objective_id", "meeting_id", "motion_id", "closed_by_member_id", "agenda_item_id"):
        if key in fields:
            fields[key] = uuid.UUID(fields[key]) if fields[key] else None
    assignees = fields.pop("assignee_member_ids", None)
    await committee_service.update_task(db, t, **fields)
    if assignees is not None:
        await committee_service.set_task_assignees(db, t, [uuid.UUID(a) for a in assignees])
    await db.commit()
    await db.refresh(t)
    await committee_service.load_task_assignees(db, [t])
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
async def list_documents(category: Optional[str] = None, user: User = _require,
                         club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    rows = await committee_service.list_documents(db, club.id, category=category)
    # Resolve "may this reader open an upload" ONCE for the whole list rather
    # than per row — the office-bearer answer is the same for every document,
    # and it costs two queries.
    privileged = (
        not club.committee_docs_office_bearer_only
        or await committee_service.is_office_bearer(db, club.id, user)
        or await committee_service.is_club_admin(db, club.id, user)
    )
    return {
        "documents": [
            committee_service._document_dict(
                d,
                can_open=(not committee_service.has_file(d)
                          or privileged
                          or d.uploaded_by_user_id == user.id),
            )
            for d in rows
        ],
        # So the register can explain why a row is locked without the client
        # having to infer the club's rule from the rows themselves.
        "office_bearer_only": bool(club.committee_docs_office_bearer_only),
    }


class DocumentCreate(BaseModel):
    title: str
    category: str = "governance"
    url: str
    position_id: Optional[str] = None
    notes: Optional[str] = None
    # Migration 217 — what this document belongs to, so a quote hangs off the
    # action that asked for it. Both null = a club-wide governance doc.
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None


@router.post("/documents")
async def create_document(data: DocumentCreate, _: User = _require, club: Organisation = Depends(get_current_club),
                          db: AsyncSession = Depends(get_db)):
    fields = data.model_dump()
    for key in ("position_id", "entity_id"):
        if key in fields:
            fields[key] = uuid.UUID(fields[key]) if fields.get(key) else None
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
    # Migration 217 — what this document belongs to, so a quote hangs off the
    # action that asked for it. Both null = a club-wide governance doc.
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None


async def _document_writable_or_403(db: AsyncSession, club: Organisation, user: User, doc_id: str):
    """Editing or deleting an uploaded document needs the same access reading it
    does. Being able to destroy a file you are not allowed to open is not a
    lesser permission than being able to read it."""
    d = await _document_or_404(db, club, doc_id)
    if not await committee_service.can_open_document(db, club, user, d):
        raise HTTPException(
            status_code=403,
            detail="This club restricts uploaded documents to office bearers and whoever uploaded them.",
        )
    return d


@router.patch("/documents/{doc_id}")
async def update_document(doc_id: str, data: DocumentPatch, user: User = _require, club: Organisation = Depends(get_current_club),
                          db: AsyncSession = Depends(get_db)):
    d = await _document_writable_or_403(db, club, user, doc_id)
    fields = data.model_dump(exclude_unset=True)
    if "position_id" in fields:
        fields["position_id"] = uuid.UUID(fields["position_id"]) if fields["position_id"] else None
    await committee_service.update_document(db, d, **fields)
    await db.commit()
    return committee_service._document_dict(d)


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, user: User = _require, club: Organisation = Depends(get_current_club),
                          db: AsyncSession = Depends(get_db)):
    d = await _document_writable_or_403(db, club, user, doc_id)
    await committee_service.delete_document(db, d)
    await db.commit()
    return {"deleted": True}


# ─── Office Bearer awards → committee history ────────────────────────────────

@router.get("/office-bearer-awards")
async def office_bearer_award_summary(_: User = _require, club: Organisation = Depends(get_current_club),
                                      db: AsyncSession = Depends(get_db)):
    """What a club would get from adopting its BetterStats Office Bearer awards.

    Read-only, so the Committee screen can offer the import only to clubs that
    actually have something to import, and say how much.
    """
    linked = await office_bearers.backfill_achievement_roles(db, club.id)
    await db.commit()
    row = (await db.execute(text("""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE cr.is_committee) AS committee
        FROM player_achievements pa
        LEFT JOIN club_roles cr ON cr.id = pa.club_role_id
        WHERE pa.org_id = :org AND pa.category = :cat
    """), {"org": str(club.id), "cat": office_bearers.AWARD_CATEGORY})).mappings().first()
    return {"awards": row["total"] or 0, "committee_awards": row["committee"] or 0,
            "newly_linked": linked}


@router.post("/office-bearer-awards/adopt")
async def adopt_office_bearer_awards(_: User = _require, club: Organisation = Depends(get_current_club),
                                     db: AsyncSession = Depends(get_db)):
    """Create committee terms from recorded Office Bearer awards. Idempotent."""
    await office_bearers.backfill_achievement_roles(db, club.id)
    result = await office_bearers.adopt_awards_as_terms(db, club.id)
    await db.commit()
    return result


# ─── Uploaded documents ──────────────────────────────────────────────────────

# Postgres will hold whatever we give it, but a committee document is a quote,
# a letter or a policy — a cap keeps one accidental video out of the row cache
# and out of every backup from here on.
MAX_DOCUMENT_BYTES = 15 * 1024 * 1024

# Deliberately not a blanket allow. These are the formats a club actually
# attaches to a committee record; anything executable or scriptable stays out,
# since the file comes back to other members from our own domain.
ALLOWED_DOCUMENT_MIMES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/rtf",
    "text/plain",
    "text/csv",
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/heic",
}


@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    category: str = Form("governance"),
    notes: Optional[str] = Form(None),
    position_id: Optional[str] = Form(None),
    entity_type: Optional[str] = Form(None),
    entity_id: Optional[str] = Form(None),
    user: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Store a file as a committee document.

    The uploader is recorded because they are one of the two people the
    club's restricted setting always lets back in.
    """
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="That file is empty")
    if len(data) > MAX_DOCUMENT_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Files are limited to {MAX_DOCUMENT_BYTES // (1024 * 1024)}MB. "
                   "Link to it instead if it is larger.",
        )
    mime = (file.content_type or "").split(";")[0].strip().lower()
    if mime not in ALLOWED_DOCUMENT_MIMES:
        raise HTTPException(
            status_code=422,
            detail=f"{mime or 'That file type'} can't be uploaded. Use a PDF, "
                   "an Office document, a plain text file or an image, or link to it instead.",
        )
    try:
        d = await committee_service.create_document(
            db, club.id,
            title=(title or "").strip() or (file.filename or "Document"),
            category=category, notes=notes,
            position_id=uuid.UUID(position_id) if position_id else None,
            entity_type=entity_type or None,
            entity_id=uuid.UUID(entity_id) if entity_id else None,
            file_data=data, file_name=(file.filename or "document")[:300],
            file_mime=mime, file_size=len(data),
            uploaded_by_user_id=user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    await db.refresh(d)
    return committee_service._document_dict(d, can_open=True)


@router.get("/documents/{doc_id}/file")
async def download_document(
    doc_id: str, download: int = 0, user: User = _require,
    club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db),
):
    """Serve an uploaded document's bytes, access re-checked here.

    This is the enforcement point, not the list's ``can_open`` flag — that one
    only decides whether the UI draws a lock. Nothing here is cached: the
    club's rule can change between two requests for the same URL, and a
    document someone may no longer open must not be sitting in a shared proxy.
    """
    d = await _document_or_404(db, club, doc_id)
    if not committee_service.has_file(d):
        raise HTTPException(status_code=404, detail="That document is a link, not a file")
    if not await committee_service.can_open_document(db, club, user, d):
        raise HTTPException(
            status_code=403,
            detail="This club restricts uploaded documents to office bearers and whoever uploaded them.",
        )
    name = (d.file_name or "document").replace('"', "")
    disposition = "attachment" if download else "inline"
    return Response(
        content=d.file_data,
        media_type=d.file_mime or "application/octet-stream",
        headers={
            "Content-Disposition": f'{disposition}; filename="{name}"',
            "Cache-Control": "private, no-store",
        },
    )


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


# ─── The meeting room ────────────────────────────────────────────────────────

@router.get("/meetings/{meeting_id}/room")
async def meeting_room(meeting_id: str, _: User = _require, club: Organisation = Depends(get_current_club),
                       db: AsyncSession = Depends(get_db)):
    """One fetch for the live screen: the meeting, its agenda in order, motions
    with their votes, the actions raised, attendance, and who can be marked
    present. A secretary mid-meeting should not wait on six requests."""
    m = await _meeting_or_404(db, club, meeting_id)
    return await committee_service.meeting_room(db, club.id, m)


class OrderBody(BaseModel):
    ids: List[str]


@router.post("/meetings/{meeting_id}/agenda-items/reorder")
async def reorder_agenda(meeting_id: str, data: OrderBody, _: User = _require,
                         club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    m = await _meeting_or_404(db, club, meeting_id)
    await committee_service.reorder_agenda_items(db, m.id, data.ids)
    await db.commit()
    return {"ok": True}


@router.post("/meetings/{meeting_id}/motions/reorder")
async def reorder_motions(meeting_id: str, data: OrderBody, _: User = _require,
                          club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    m = await _meeting_or_404(db, club, meeting_id)
    await committee_service.reorder_motions(db, m.id, data.ids)
    await db.commit()
    return {"ok": True}


class MeetingPatch(BaseModel):
    # Minutes are circulated; these are the secretary's own (migration 220).
    private_notes: Optional[str] = None
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


# ─── Governance (migration 217) ───────────────────────────────────────────────


class MotionVote(BaseModel):
    member_id: str
    vote: str          # for | against | abstain


class MotionVotes(BaseModel):
    votes: List[MotionVote] = []


@router.put("/meetings/{meeting_id}/motions/{motion_id}/votes")
async def set_motion_votes(meeting_id: str, motion_id: str, data: MotionVotes, _: User = _require,
                           club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    """Record who voted which way. Replaces the whole list, and re-derives the
    motion's tallies from it."""
    m = await _meeting_or_404(db, club, meeting_id)
    motion = await _motion_or_404(db, club, m, motion_id)
    await committee_service.set_motion_votes(db, motion, [v.model_dump() for v in data.votes])
    await db.commit()
    # commit() expires the instance, and serialising it would then lazy-load
    # from inside the response — the MissingGreenlet trap. Refresh explicitly.
    await db.refresh(motion)
    await committee_service.load_motion_votes(db, [motion])
    return committee_service._motion_dict(motion)


class ResolutionBody(BaseModel):
    resolution_ref: Optional[str] = None
    on: bool = True


@router.post("/meetings/{meeting_id}/motions/{motion_id}/resolution")
async def set_resolution(meeting_id: str, motion_id: str, data: ResolutionBody, _: User = _require,
                         club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    """Turn a carried motion into a standing resolution, or take that back."""
    m = await _meeting_or_404(db, club, meeting_id)
    motion = await _motion_or_404(db, club, m, motion_id)
    try:
        await committee_service.make_resolution(db, motion, ref=data.resolution_ref, on=data.on)
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err))
    await db.commit()
    await db.refresh(motion)   # see the note on set_motion_votes
    return committee_service._motion_dict(motion)


@router.get("/resolutions")
async def list_resolutions(_: User = _require, club: Organisation = Depends(get_current_club),
                           db: AsyncSession = Depends(get_db)):
    """Every standing resolution the club has passed, newest first — the
    register a committee actually refers back to."""
    rows = (await db.execute(
        select(MeetingMotion, CommitteeMeeting)
        .join(CommitteeMeeting, CommitteeMeeting.id == MeetingMotion.meeting_id)
        .where(CommitteeMeeting.organisation_id == club.id, MeetingMotion.is_resolution.is_(True))
        .order_by(MeetingMotion.resolved_at.desc().nullslast())
    )).all()
    return {"resolutions": [{
        **committee_service._motion_dict(motion),
        "meeting_title": meeting.title,
        "meeting_at": meeting.scheduled_at.isoformat() if meeting.scheduled_at else None,
    } for motion, meeting in rows]}


class TaskDeps(BaseModel):
    depends_on: List[str] = []


@router.put("/tasks/{task_id}/dependencies")
async def set_task_dependencies(task_id: str, data: TaskDeps, _: User = _require,
                                club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    t = await _task_or_404(db, club, task_id)
    kept = await committee_service.set_task_dependencies(db, t.id, [uuid.UUID(d) for d in data.depends_on])
    await db.commit()
    return {"task_id": str(t.id), "depends_on": [str(k) for k in kept]}


class NoteCreate(BaseModel):
    body: str
    author_member_id: Optional[str] = None


@router.get("/notes/{entity_type}/{entity_id}")
async def list_notes(entity_type: str, entity_id: str, _: User = _require,
                     club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    return {"notes": await committee_service.list_notes(db, club.id, entity_type, uuid.UUID(entity_id))}


@router.post("/notes/{entity_type}/{entity_id}")
async def add_note(entity_type: str, entity_id: str, data: NoteCreate, current_user: User = _require,
                   club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    try:
        note = await committee_service.add_note(
            db, club.id, entity_type, uuid.UUID(entity_id), data.body,
            author_member_id=uuid.UUID(data.author_member_id) if data.author_member_id else None,
            author_user_id=current_user.id,
        )
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err))
    await db.commit()
    return note


@router.delete("/notes/{note_id}")
async def delete_note(note_id: str, _: User = _require, club: Organisation = Depends(get_current_club),
                      db: AsyncSession = Depends(get_db)):
    if not await committee_service.delete_note(db, club.id, uuid.UUID(note_id)):
        raise HTTPException(status_code=404, detail="Note not found")
    await db.commit()
    return {"deleted": True}


class ObjectiveUpsert(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    plan: Optional[str] = None
    season_year: Optional[int] = None
    status: Optional[str] = None
    sort_order: Optional[int] = None


@router.get("/objectives")
async def list_objectives(include_archived: bool = False, _: User = _require,
                          club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    return {"objectives": await committee_service.list_objectives(db, club.id, include_archived=include_archived)}


@router.get("/objectives/progress")
async def objective_progress(_: User = _require, club: Organisation = Depends(get_current_club),
                             db: AsyncSession = Depends(get_db)):
    """The club's plan, reported against the actions serving it."""
    return {"objectives": await committee_service.objective_progress(db, club.id)}


@router.post("/objectives")
async def create_objective(data: ObjectiveUpsert, _: User = _require,
                           club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    try:
        o = await committee_service.upsert_objective(db, club.id, **data.model_dump(exclude_none=True))
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err))
    await db.commit()
    return o


@router.patch("/objectives/{objective_id}")
async def update_objective(objective_id: str, data: ObjectiveUpsert, _: User = _require,
                           club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    try:
        o = await committee_service.upsert_objective(db, club.id, uuid.UUID(objective_id),
                                                     **data.model_dump(exclude_none=True))
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err))
    await db.commit()
    return o


@router.delete("/objectives/{objective_id}")
async def delete_objective(objective_id: str, _: User = _require,
                           club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    if not await committee_service.delete_objective(db, club.id, uuid.UUID(objective_id)):
        raise HTTPException(status_code=404, detail="Objective not found")
    await db.commit()
    return {"deleted": True}
