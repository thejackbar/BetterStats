"""Committee Administration — positions/terms, task register, documents, calendar.

Nothing is auto-seeded (a club adopts the starter 14 positions, or builds its
own — see seed_starter_positions). A position's "current holder" is the term
row with ``ended_at IS NULL``; starting a new term auto-closes whatever term
was previously open for that position, so a position can never show two
"current" holders at once.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import CommitteePosition, CommitteeTerm, CommitteeTask, CommitteeDocument, ClubEvent

# (name, responsibilities)
STARTER_POSITIONS = [
    ("President", "Overall leadership, chairs meetings, primary club spokesperson."),
    ("Vice President", "Deputises for the President; often leads a portfolio area."),
    ("Treasurer", "Club finances, budgets, membership fee oversight, financial reporting."),
    ("Secretary", "Meeting minutes, correspondence, statutory/association paperwork."),
    ("Junior Coordinator", "Junior program — registrations, coaching, grading."),
    ("Senior Coordinator", "Senior teams — registrations, grading, team management."),
    ("Selection Chair", "Chairs the selection panel across grades."),
    ("Coach Coordinator", "Coaching appointments, accreditation, development."),
    ("Grounds Manager", "Ground/wicket preparation and maintenance liaison."),
    ("Equipment Manager", "Club kit, balls, training equipment."),
    ("Bar Manager", "Bar operations, licensing compliance, RSA rostering."),
    ("Volunteer Coordinator", "Recruits and rosters club volunteers."),
    ("Sponsorship Manager", "Sponsor relationships and obligations."),
    ("Social Media Officer", "Club social media and website content."),
]


def _position_dict(p: CommitteePosition) -> dict:
    return {
        "id": str(p.id), "name": p.name, "responsibilities": p.responsibilities,
        "sort_order": p.sort_order, "is_active": p.is_active,
    }


def _term_dict(t: CommitteeTerm) -> dict:
    return {
        "id": str(t.id), "position_id": str(t.position_id),
        "member_id": str(t.member_id) if t.member_id else None,
        "holder_name": t.holder_name,
        "started_at": t.started_at.isoformat() if t.started_at else None,
        "ended_at": t.ended_at.isoformat() if t.ended_at else None,
        "handover_notes": t.handover_notes,
        "is_current": t.ended_at is None,
    }


def _task_dict(t: CommitteeTask) -> dict:
    return {
        "id": str(t.id), "title": t.title, "description": t.description, "category": t.category,
        "position_id": str(t.position_id) if t.position_id else None,
        "assigned_to_member_id": str(t.assigned_to_member_id) if t.assigned_to_member_id else None,
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "status": t.status, "is_recurring": t.is_recurring, "recurrence_note": t.recurrence_note,
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
    }


def _document_dict(d: CommitteeDocument) -> dict:
    return {
        "id": str(d.id), "title": d.title, "category": d.category, "url": d.url,
        "position_id": str(d.position_id) if d.position_id else None, "notes": d.notes,
    }


def _event_dict(e: ClubEvent) -> dict:
    return {
        "id": str(e.id), "title": e.title, "event_type": e.event_type,
        "starts_at": e.starts_at.isoformat() if e.starts_at else None,
        "ends_at": e.ends_at.isoformat() if e.ends_at else None,
        "location": e.location, "description": e.description,
    }


# ─── Positions ────────────────────────────────────────────────────────────────

async def list_positions(session: AsyncSession, org_id, *, include_inactive: bool = False) -> list[CommitteePosition]:
    stmt = select(CommitteePosition).where(CommitteePosition.organisation_id == org_id)
    if not include_inactive:
        stmt = stmt.where(CommitteePosition.is_active.is_(True))
    stmt = stmt.order_by(CommitteePosition.sort_order, func.lower(CommitteePosition.name))
    return (await session.execute(stmt)).scalars().all()


async def create_position(session: AsyncSession, org_id, *, name: str, responsibilities: Optional[str] = None,
                          sort_order: int = 0) -> CommitteePosition:
    name = (name or "").strip()
    if not name:
        raise ValueError("Name is required")
    existing = (await session.execute(
        select(CommitteePosition).where(CommitteePosition.organisation_id == org_id,
                                        func.lower(CommitteePosition.name) == name.lower())
    )).scalars().first()
    if existing is not None:
        if not existing.is_active:
            existing.is_active = True
            return existing
        raise ValueError(f'A position called "{name}" already exists')
    p = CommitteePosition(organisation_id=org_id, name=name[:120], responsibilities=responsibilities, sort_order=sort_order)
    session.add(p)
    await session.flush()
    return p


async def update_position(session: AsyncSession, p: CommitteePosition, **fields) -> CommitteePosition:
    for f in ("name", "responsibilities", "sort_order"):
        if f in fields and fields[f] is not None:
            setattr(p, f, fields[f])
    return p


async def archive_position(session: AsyncSession, p: CommitteePosition) -> None:
    p.is_active = False


async def seed_starter_positions(session: AsyncSession, org_id) -> int:
    existing_names = {n.lower() for n in (await session.execute(
        select(CommitteePosition.name).where(CommitteePosition.organisation_id == org_id)
    )).scalars().all()}
    seeded = 0
    for position, (name, resp) in enumerate(STARTER_POSITIONS):
        if name.lower() in existing_names:
            continue
        session.add(CommitteePosition(organisation_id=org_id, name=name, responsibilities=resp, sort_order=position))
        seeded += 1
    if seeded:
        await session.flush()
    return seeded


# ─── Terms (who's held a position, when) ─────────────────────────────────────

async def current_holders(session: AsyncSession, org_id) -> dict:
    """Every active position with its current term (or None) — the
    Committee Directory's one fetch."""
    positions = await list_positions(session, org_id)
    terms = (await session.execute(
        select(CommitteeTerm).where(CommitteeTerm.organisation_id == org_id, CommitteeTerm.ended_at.is_(None))
    )).scalars().all()
    by_position = {t.position_id: t for t in terms}
    return {
        "positions": [
            {**_position_dict(p), "current_term": _term_dict(by_position[p.id]) if p.id in by_position else None}
            for p in positions
        ],
    }


async def position_history(session: AsyncSession, org_id, position_id) -> list[dict]:
    rows = (await session.execute(
        select(CommitteeTerm).where(CommitteeTerm.organisation_id == org_id, CommitteeTerm.position_id == position_id)
        .order_by(CommitteeTerm.started_at.desc())
    )).scalars().all()
    return [_term_dict(t) for t in rows]


async def start_term(session: AsyncSession, org_id, position_id, *, member_id=None, holder_name: str,
                     started_at: Optional[date] = None) -> CommitteeTerm:
    """Auto-closes whatever term is currently open for this position (its
    ended_at is set to the new term's start date, i.e. a clean handover)
    before opening the new one."""
    holder_name = (holder_name or "").strip()
    if not holder_name:
        raise ValueError("Holder name is required")
    started = started_at or date.today()
    open_term = (await session.execute(
        select(CommitteeTerm).where(CommitteeTerm.position_id == position_id, CommitteeTerm.ended_at.is_(None))
    )).scalars().first()
    if open_term is not None:
        open_term.ended_at = started
    term = CommitteeTerm(
        organisation_id=org_id, position_id=position_id, member_id=member_id,
        holder_name=holder_name[:200], started_at=started,
    )
    session.add(term)
    await session.flush()
    return term


async def update_term(session: AsyncSession, term: CommitteeTerm, **fields) -> CommitteeTerm:
    for f in ("holder_name", "started_at", "ended_at", "handover_notes"):
        if f in fields and fields[f] is not None:
            setattr(term, f, fields[f])
    return term


async def end_term(session: AsyncSession, term: CommitteeTerm, *, ended_at: Optional[date] = None,
                   handover_notes: Optional[str] = None) -> CommitteeTerm:
    term.ended_at = ended_at or date.today()
    if handover_notes is not None:
        term.handover_notes = handover_notes
    return term


# ─── Tasks (Task Register + Annual Task Calendar) ────────────────────────────

async def list_tasks(session: AsyncSession, org_id, *, status: Optional[str] = None,
                     category: Optional[str] = None) -> list[CommitteeTask]:
    stmt = select(CommitteeTask).where(CommitteeTask.organisation_id == org_id)
    if status:
        stmt = stmt.where(CommitteeTask.status == status)
    if category:
        stmt = stmt.where(CommitteeTask.category == category)
    stmt = stmt.order_by(CommitteeTask.due_date.asc().nullslast(), CommitteeTask.created_at.desc())
    return (await session.execute(stmt)).scalars().all()


async def create_task(session: AsyncSession, org_id, **fields) -> CommitteeTask:
    title = (fields.get("title") or "").strip()
    if not title:
        raise ValueError("Title is required")
    t = CommitteeTask(organisation_id=org_id, title=title[:300], **{k: v for k, v in fields.items() if k != "title"})
    session.add(t)
    await session.flush()
    return t


async def update_task(session: AsyncSession, t: CommitteeTask, **fields) -> CommitteeTask:
    for f in ("title", "description", "category", "position_id", "assigned_to_member_id",
              "due_date", "status", "is_recurring", "recurrence_note"):
        if f in fields and fields[f] is not None:
            setattr(t, f, fields[f])
    if "status" in fields and fields["status"] is not None:
        t.completed_at = func.now() if fields["status"] == "done" else None
    t.updated_at = func.now()
    return t


async def delete_task(session: AsyncSession, t: CommitteeTask) -> None:
    await session.delete(t)


# ─── Documents ────────────────────────────────────────────────────────────────

async def list_documents(session: AsyncSession, org_id, *, category: Optional[str] = None) -> list[CommitteeDocument]:
    stmt = select(CommitteeDocument).where(CommitteeDocument.organisation_id == org_id)
    if category:
        stmt = stmt.where(CommitteeDocument.category == category)
    stmt = stmt.order_by(CommitteeDocument.category, func.lower(CommitteeDocument.title))
    return (await session.execute(stmt)).scalars().all()


async def create_document(session: AsyncSession, org_id, **fields) -> CommitteeDocument:
    title = (fields.get("title") or "").strip()
    url = (fields.get("url") or "").strip()
    if not title or not url:
        raise ValueError("Title and URL are required")
    d = CommitteeDocument(organisation_id=org_id, title=title[:300], url=url[:2000],
                          category=fields.get("category") or "governance",
                          position_id=fields.get("position_id"), notes=fields.get("notes"))
    session.add(d)
    await session.flush()
    return d


async def update_document(session: AsyncSession, d: CommitteeDocument, **fields) -> CommitteeDocument:
    for f in ("title", "category", "url", "position_id", "notes"):
        if f in fields and fields[f] is not None:
            setattr(d, f, fields[f])
    return d


async def delete_document(session: AsyncSession, d: CommitteeDocument) -> None:
    await session.delete(d)


# ─── Club calendar (events) ──────────────────────────────────────────────────

async def list_events(session: AsyncSession, org_id, *, upcoming_only: bool = False) -> list[ClubEvent]:
    from datetime import datetime, timezone
    stmt = select(ClubEvent).where(ClubEvent.organisation_id == org_id)
    if upcoming_only:
        stmt = stmt.where(ClubEvent.starts_at >= datetime.now(timezone.utc))
    stmt = stmt.order_by(ClubEvent.starts_at)
    return (await session.execute(stmt)).scalars().all()


async def create_event(session: AsyncSession, org_id, **fields) -> ClubEvent:
    title = (fields.get("title") or "").strip()
    if not title or not fields.get("starts_at"):
        raise ValueError("Title and start time are required")
    e = ClubEvent(organisation_id=org_id, title=title[:300], event_type=fields.get("event_type") or "other",
                 starts_at=fields["starts_at"], ends_at=fields.get("ends_at"),
                 location=fields.get("location"), description=fields.get("description"))
    session.add(e)
    await session.flush()
    return e


async def update_event(session: AsyncSession, e: ClubEvent, **fields) -> ClubEvent:
    for f in ("title", "event_type", "starts_at", "ends_at", "location", "description"):
        if f in fields and fields[f] is not None:
            setattr(e, f, fields[f])
    return e


async def delete_event(session: AsyncSession, e: ClubEvent) -> None:
    await session.delete(e)
