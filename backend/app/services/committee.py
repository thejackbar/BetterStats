"""Committee Administration — positions/terms, task register, documents, calendar.

Nothing is auto-seeded (a club adopts the starter 14 positions, or builds its
own — see seed_starter_positions). A position's "current holder" is the term
row with ``ended_at IS NULL``; starting a new term auto-closes whatever term
was previously open for that position, so a position can never show two
"current" holders at once.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from sqlalchemy import select, func, delete
from sqlalchemy.orm import defer
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import (
    CommitteePosition, CommitteeTerm, CommitteeTask, CommitteeDocument, ClubEvent,
    AgendaTemplate, CommitteeMeeting, MeetingAttendance, MeetingAgendaItem, MeetingMotion,
    AgmNomination, FeeMember, ClubRole, ClubRoleType, ClubMembership,
    CommitteeTaskAssignee,
)

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
        "role_id": str(p.role_id) if p.role_id else None,
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
        # Migration 217 — the planning side of an action.
        "objective_id": str(t.objective_id) if t.objective_id else None,
        "budget_estimate": float(t.budget_estimate) if t.budget_estimate is not None else None,
        "actual_expenditure": float(t.actual_expenditure) if t.actual_expenditure is not None else None,
        "percent_complete": t.percent_complete or 0,
        "start_date": t.start_date.isoformat() if t.start_date else None,
        "closed_by_member_id": str(t.closed_by_member_id) if t.closed_by_member_id else None,
        "outcome_notes": t.outcome_notes,
        "meeting_id": str(t.meeting_id) if t.meeting_id else None,
        "motion_id": str(t.motion_id) if t.motion_id else None,
        "agenda_item_id": str(t.agenda_item_id) if t.agenda_item_id else None,
        "assignee_member_ids": [str(a) for a in (getattr(t, "_assignees", None) or [])],
        "depends_on": [str(d) for d in (getattr(t, "_depends_on", None) or [])],
    }


def has_file(d: CommitteeDocument) -> bool:
    """Whether this row is an upload rather than a link.

    Reads file_size, never file_data — the bytes are deferred on the list query
    and touching them there would fire a lazy load outside the async greenlet.
    Both are written together by the upload path, so size is a faithful stand-in.
    """
    return d.file_size is not None


def _document_dict(d: CommitteeDocument, *, can_open: bool = True) -> dict:
    # `file_data` is never serialised — the bytes come from the download route,
    # which re-checks access. `can_open` is what the caller resolved for THIS
    # reader, so the register can show a locked row rather than a dead link.
    return {
        "id": str(d.id), "title": d.title, "category": d.category, "url": d.url,
        "position_id": str(d.position_id) if d.position_id else None, "notes": d.notes,
        "entity_type": d.entity_type, "entity_id": str(d.entity_id) if d.entity_id else None,
        "has_file": has_file(d), "file_name": d.file_name,
        "file_mime": d.file_mime, "file_size": d.file_size,
        "uploaded_by_user_id": str(d.uploaded_by_user_id) if d.uploaded_by_user_id else None,
        "can_open": can_open,
    }


def _event_dict(e: ClubEvent) -> dict:
    return {
        "id": str(e.id), "title": e.title, "event_type": e.event_type,
        "event_type_id": str(e.event_type_id) if e.event_type_id else None,
        "organiser_member_id": str(e.organiser_member_id) if e.organiser_member_id else None,
        "organiser_name": e.organiser_name,
        "starts_at": e.starts_at.isoformat() if e.starts_at else None,
        "ends_at": e.ends_at.isoformat() if e.ends_at else None,
        "location": e.location, "description": e.description,
        "is_ticketed": e.is_ticketed, "ticket_price_cents": e.ticket_price_cents,
        "capacity": e.capacity,
        "registration_deadline": e.registration_deadline.isoformat() if e.registration_deadline else None,
        "registration_open": e.registration_open,
    }


def _agenda_template_dict(t: AgendaTemplate) -> dict:
    return {"id": str(t.id), "name": t.name, "items": t.items or []}


def _meeting_dict(m: CommitteeMeeting) -> dict:
    return {
        "id": str(m.id), "title": m.title, "meeting_type": m.meeting_type,
        "scheduled_at": m.scheduled_at.isoformat() if m.scheduled_at else None,
        "location": m.location, "status": m.status, "minutes": m.minutes,
        "private_notes": m.private_notes,
        "agenda_template_id": str(m.agenda_template_id) if m.agenda_template_id else None,
    }


def _attendance_dict(a: MeetingAttendance) -> dict:
    return {"id": str(a.id), "meeting_id": str(a.meeting_id), "member_id": str(a.member_id), "status": a.status}


def _agenda_item_dict(i: MeetingAgendaItem) -> dict:
    return {
        "id": str(i.id), "meeting_id": str(i.meeting_id), "title": i.title, "description": i.description,
        "proposed_by_member_id": str(i.proposed_by_member_id) if i.proposed_by_member_id else None,
        "position": i.position, "status": i.status, "outcome_notes": i.outcome_notes,
        "section": i.section,
    }


def _motion_dict(m: MeetingMotion) -> dict:
    return {
        "id": str(m.id), "meeting_id": str(m.meeting_id),
        "agenda_item_id": str(m.agenda_item_id) if m.agenda_item_id else None,
        "position": m.position or 0,
        "motion_type": m.motion_type, "description": m.description,
        "proposed_by_member_id": str(m.proposed_by_member_id) if m.proposed_by_member_id else None,
        "seconded_by_member_id": str(m.seconded_by_member_id) if m.seconded_by_member_id else None,
        "votes_for": m.votes_for, "votes_against": m.votes_against, "votes_abstain": m.votes_abstain,
        "outcome": m.outcome, "notes": m.notes,
        # Migration 217 — a carried motion recorded as a standing decision, and
        # the named votes behind the tallies when a club records them.
        "is_resolution": bool(m.is_resolution),
        "resolution_ref": m.resolution_ref,
        "resolved_at": m.resolved_at.isoformat() if m.resolved_at else None,
        # Migration 230 — the objective this motion serves.
        "objective_id": str(m.objective_id) if m.objective_id else None,
        "votes": [{"member_id": str(v.member_id), "vote": v.vote} for v in (getattr(m, "_votes", None) or [])],
    }


def _nomination_dict(n: AgmNomination) -> dict:
    return {
        "id": str(n.id), "meeting_id": str(n.meeting_id), "position_id": str(n.position_id),
        "candidate_member_id": str(n.candidate_member_id),
        "nominated_by_member_id": str(n.nominated_by_member_id) if n.nominated_by_member_id else None,
        "seconded_by_member_id": str(n.seconded_by_member_id) if n.seconded_by_member_id else None,
        "votes_for": n.votes_for, "status": n.status, "notes": n.notes,
    }


# ─── Positions ────────────────────────────────────────────────────────────────

# The executive/legal office bearers, matched by position name. Only used for a
# role that carries no type — the role's TYPE is the real signal (see below).
_OFFICE_BEARER_NAMES = {"president", "vice president", "vice-president", "treasurer", "secretary"}


def _is_office_bearer_name(name: str) -> bool:
    return (name or "").strip().lower() in _OFFICE_BEARER_NAMES


def _role_is_office_bearer(title: str, role_type_name: Optional[str]) -> bool:
    """Whether a committee role carries legal/fiduciary responsibility.

    The role's TYPE decides it, so a club that renames President to Chairperson
    keeps the responsibility and a club that invents its own office-bearer
    position gets it. Falling back to the name matters only for a role with no
    type set — without that fallback, retyping would silently strip access from
    documents restricted to office bearers.
    """
    if role_type_name:
        return role_type_name.strip().lower() == OFFICE_BEARER_ROLE_TYPE.lower()
    return _is_office_bearer_name(title)


async def sync_committee_positions(session: AsyncSession, org_id) -> None:
    """A committee position IS a committee-flagged club_role (migration 198).
    The catalogue is edited in Roles; this keeps a committee_position row per
    committee role (the term/task/doc/AGM FK anchor) in sync with it. Called
    before any positions read/seed. Positions whose role is archived/removed
    are deactivated but keep their term history."""
    role_rows = (await session.execute(
        select(ClubRole, ClubRoleType.name)
        .outerjoin(ClubRoleType, ClubRoleType.id == ClubRole.role_type_id)
        .where(ClubRole.organisation_id == org_id,
               ClubRole.is_committee.is_(True), ClubRole.is_active.is_(True))
    )).all()
    roles = [r for r, _ in role_rows]
    office_bearer_by_role = {
        r.id: _role_is_office_bearer(r.title, type_name) for r, type_name in role_rows
    }
    positions = (await session.execute(
        select(CommitteePosition).where(CommitteePosition.organisation_id == org_id)
    )).scalars().all()
    by_role = {p.role_id: p for p in positions if p.role_id}
    by_name = {p.name.lower(): p for p in positions}
    live_role_ids = set()
    changed = False
    for role in roles:
        live_role_ids.add(role.id)
        pos = by_role.get(role.id) or by_name.get(role.title.lower())
        is_ob = office_bearer_by_role.get(role.id, False)
        if pos is None:
            pos = CommitteePosition(organisation_id=org_id, name=role.title[:120],
                                    responsibilities=role.description, role_id=role.id, sort_order=role.sort_order,
                                    is_office_bearer=is_ob)
            session.add(pos)
            changed = True
            continue
        # Link + resync display fields from the role (the source of truth).
        if pos.role_id != role.id:
            pos.role_id = role.id; changed = True
        if pos.name != role.title[:120]:
            pos.name = role.title[:120]; changed = True
        if pos.responsibilities != role.description:
            pos.responsibilities = role.description; changed = True
        if pos.sort_order != role.sort_order:
            pos.sort_order = role.sort_order; changed = True
        # Office-bearer status is resynced, not just set on first create. It now
        # gates who can open a restricted document, so a role retyped in the
        # Roles catalogue has to move the position with it — otherwise the two
        # answers drift and access follows a stale name match.
        if pos.is_office_bearer != is_ob:
            pos.is_office_bearer = is_ob; changed = True
        if not pos.is_active:
            pos.is_active = True; changed = True
    # Deactivate positions whose committee role no longer exists/active.
    for pos in positions:
        if pos.role_id and pos.role_id not in live_role_ids and pos.is_active:
            pos.is_active = False; changed = True
    if changed:
        await session.flush()


async def list_positions(session: AsyncSession, org_id, *, include_inactive: bool = False) -> list[CommitteePosition]:
    await sync_committee_positions(session, org_id)
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


async def reorder_positions(session: AsyncSession, org_id, position_ids) -> None:
    """Set the display order of the committee roles. Writes the new index onto
    BOTH the committee_position AND its linked committee role's sort_order, so
    the order survives the position↔role sync and matches the Roles page."""
    for idx, pid in enumerate(position_ids):
        p = await session.get(CommitteePosition, pid)
        if p is None or p.organisation_id != org_id:
            continue
        p.sort_order = idx
        if p.role_id:
            role = await session.get(ClubRole, p.role_id)
            if role is not None and role.organisation_id == org_id:
                role.sort_order = idx
    await session.flush()


async def seed_starter_positions(session: AsyncSession, org_id) -> int:
    """Seeds the COMMITTEE roles into the shared Roles catalogue, then ensures a
    committee_position exists per role. The catalogue is Roles; this just makes
    the committee roles available and holdable."""
    from app.services import roles_activities as roles_service
    seeded = await roles_service.seed_starter_roles(session, org_id, committee=True)
    await sync_committee_positions(session, org_id)
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


# Columns on an action that are nullable, so sending an explicit null means
# "clear it" rather than "not sent". The caller passes exclude_unset fields, so
# a key being present IS the intent. Without this an action could be given a
# budget, an objective or a due date and never have one taken away again.
_TASK_CLEARABLE = (
    "description", "position_id", "assigned_to_member_id", "due_date", "recurrence_note",
    "objective_id", "budget_estimate", "actual_expenditure", "start_date",
    "closed_by_member_id", "outcome_notes", "meeting_id", "motion_id",
)


async def update_task(session: AsyncSession, t: CommitteeTask, **fields) -> CommitteeTask:
    for f in ("title", "category", "status", "is_recurring", "percent_complete"):
        if f in fields and fields[f] is not None:
            setattr(t, f, fields[f])
    for f in _TASK_CLEARABLE:
        if f in fields:
            setattr(t, f, fields[f])
    if "status" in fields and fields["status"] is not None:
        done = fields["status"] == "done"
        t.completed_at = func.now() if done else None
        # Closing an action means it is finished, so say so rather than leaving
        # a 60%-complete row sitting in the register marked done.
        if done and (t.percent_complete or 0) < 100:
            t.percent_complete = 100
    t.updated_at = func.now()
    return t


async def delete_task(session: AsyncSession, t: CommitteeTask) -> None:
    await session.delete(t)


# ─── Documents ────────────────────────────────────────────────────────────────

async def list_documents(session: AsyncSession, org_id, *, category: Optional[str] = None) -> list[CommitteeDocument]:
    # file_data is deferred: a register of twenty uploads would otherwise pull
    # every one of their payloads into memory just to render a list of titles.
    # Nothing on the list path reads the bytes — `has_file` comes from
    # file_size, and the download route loads the row again in full.
    stmt = (select(CommitteeDocument)
            .where(CommitteeDocument.organisation_id == org_id)
            .options(defer(CommitteeDocument.file_data)))
    if category:
        stmt = stmt.where(CommitteeDocument.category == category)
    stmt = stmt.order_by(CommitteeDocument.category, func.lower(CommitteeDocument.title))
    return (await session.execute(stmt)).scalars().all()


async def create_document(session: AsyncSession, org_id, **fields) -> CommitteeDocument:
    title = (fields.get("title") or "").strip()
    url = (fields.get("url") or "").strip()
    file_data = fields.get("file_data")
    if not title:
        raise ValueError("A title is required")
    # A row is either a link to a document or the document itself (migration
    # 218). One of the two has to be there or the entry points at nothing.
    if not url and not file_data:
        raise ValueError("Add a link or upload a file")
    d = CommitteeDocument(organisation_id=org_id, title=title[:300], url=url[:2000] or None,
                          category=fields.get("category") or "governance",
                          position_id=fields.get("position_id"), notes=fields.get("notes"),
                          entity_type=fields.get("entity_type"), entity_id=fields.get("entity_id"),
                          file_data=file_data, file_name=fields.get("file_name"),
                          file_mime=fields.get("file_mime"), file_size=fields.get("file_size"),
                          uploaded_by_user_id=fields.get("uploaded_by_user_id"))
    session.add(d)
    await session.flush()
    return d


async def update_document(session: AsyncSession, d: CommitteeDocument, **fields) -> CommitteeDocument:
    for f in ("title", "category", "url", "position_id", "notes", "entity_type", "entity_id"):
        if f in fields and fields[f] is not None:
            setattr(d, f, fields[f])
    return d


async def delete_document(session: AsyncSession, d: CommitteeDocument) -> None:
    await session.delete(d)


# ─── Who may open an uploaded document ───────────────────────────────────────
#
# Reaching this router at all already requires MANAGE_COMMITTEE. The rule below
# is a second, narrower gate over UPLOADED FILES only, because a club asked to
# be able to put a legal letter somewhere without every committee member seeing
# it. It does not — and cannot — apply to a link: the URL is right there in the
# register and it points at someone else's Drive.

# The role type carrying legal/fiduciary responsibility. Named to match
# roles_activities.STARTER_ROLE_TYPES, which is the catalogue clubs seed from.
OFFICE_BEARER_ROLE_TYPE = "Office Bearer"


async def member_for_user(session: AsyncSession, org_id, user) -> Optional[FeeMember]:
    """The club member a login belongs to, matched on email.

    There is no users -> fee_members foreign key: a member is a person the club
    records, a user is someone who can sign in, and most members never get a
    login. Email is the only honest join, so a member with no email recorded, or
    one recorded under a different address from the one they log in with, simply
    does not resolve — which the callers below treat as "not an office bearer"
    rather than as an error.
    """
    email = (getattr(user, "email", "") or "").strip().lower()
    if not email:
        return None
    return (await session.execute(
        select(FeeMember).where(
            FeeMember.organisation_id == org_id,
            func.lower(FeeMember.email) == email,
        ).limit(1)
    )).scalars().first()


async def is_office_bearer(session: AsyncSession, org_id, user) -> bool:
    """Does this login currently hold an Office Bearer position?

    Current means a term with no end date. The role TYPE is what decides it,
    not the position's name — a club that renames "President" to "Chairperson"
    keeps the responsibility, and a club that invents its own office-bearer
    position gets it too. ``committee_positions.is_office_bearer`` is accepted
    as well, for positions created before roles carried a type.
    """
    member = await member_for_user(session, org_id, user)
    if member is None:
        return False
    rows = (await session.execute(
        select(CommitteePosition.is_office_bearer, ClubRoleType.name)
        .select_from(CommitteeTerm)
        .join(CommitteePosition, CommitteePosition.id == CommitteeTerm.position_id)
        .outerjoin(ClubRole, ClubRole.id == CommitteePosition.role_id)
        .outerjoin(ClubRoleType, ClubRoleType.id == ClubRole.role_type_id)
        .where(
            CommitteeTerm.organisation_id == org_id,
            CommitteeTerm.member_id == member.id,
            CommitteeTerm.ended_at.is_(None),
        )
    )).all()
    return any(
        flag or (name or "").strip().lower() == OFFICE_BEARER_ROLE_TYPE.lower()
        for flag, name in rows
    )


async def is_club_admin(session: AsyncSession, org_id, user) -> bool:
    role = (await session.execute(
        select(ClubMembership.role).where(
            ClubMembership.user_id == user.id, ClubMembership.club_id == org_id,
        )
    )).scalars().first()
    return role == "club_admin"


async def can_open_document(session: AsyncSession, club, user, doc: CommitteeDocument) -> bool:
    """Whether this login may read an uploaded document's bytes.

    A link-only row is always openable — see the note above. For an uploaded
    file with the club's restricted setting on, three people get in: whoever
    uploaded it, a current Office Bearer, and the club's Main Admin.

    The Main Admin is on that list deliberately. They own the club's data and
    they are the one who can flip this setting, so excluding them would look
    like a guarantee while being one click from untrue. Better to say plainly
    who can read a document than to imply a wall that is not there.
    """
    if not has_file(doc):
        return True
    if not getattr(club, "committee_docs_office_bearer_only", True):
        return True
    if doc.uploaded_by_user_id and doc.uploaded_by_user_id == user.id:
        return True
    if await is_office_bearer(session, club.id, user):
        return True
    return await is_club_admin(session, club.id, user)


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
    e = ClubEvent(
        organisation_id=org_id, title=title[:300], event_type=fields.get("event_type") or "other",
        event_type_id=fields.get("event_type_id"),
        organiser_member_id=fields.get("organiser_member_id"), organiser_name=fields.get("organiser_name"),
        starts_at=fields["starts_at"], ends_at=fields.get("ends_at"),
        location=fields.get("location"), description=fields.get("description"),
        is_ticketed=fields.get("is_ticketed") or False,
        ticket_price_cents=fields.get("ticket_price_cents") or 0,
        capacity=fields.get("capacity"),
        registration_deadline=fields.get("registration_deadline"),
        registration_open=fields.get("registration_open", True),
    )
    session.add(e)
    await session.flush()
    return e


async def update_event(session: AsyncSession, e: ClubEvent, **fields) -> ClubEvent:
    # organiser_* + event_type_id are nullable and may be cleared explicitly,
    # so they use "present in the payload" rather than "not None".
    for f in ("title", "event_type", "starts_at", "ends_at", "location", "description",
              "is_ticketed", "ticket_price_cents", "capacity", "registration_deadline", "registration_open"):
        if f in fields and fields[f] is not None:
            setattr(e, f, fields[f])
    for f in ("event_type_id", "organiser_member_id", "organiser_name"):
        if f in fields:
            setattr(e, f, fields[f])
    return e


async def delete_event(session: AsyncSession, e: ClubEvent) -> None:
    await session.delete(e)


# ─── The order of business ────────────────────────────────────────────────────
#
# A club's agenda is grouped, not flat: formalities, then reports, then
# elections, then general business, then closing. `section` is the heading an
# item sits under, and it is deliberately a plain label — the agenda stays ONE
# ordered sequence, so dragging works as it always did and the screen draws a
# heading wherever the section changes.

def _clean_section(value) -> Optional[str]:
    """A blank section means "not under any heading", not an empty heading."""
    return (str(value).strip()[:120] or None) if value else None


# The two agendas nearly every community club runs, so a committee starts from
# something to edit rather than an empty page. Nothing is auto-seeded: a club
# adopts these, or writes its own.
STARTER_AGENDA_TEMPLATES = [
    ("Annual General Meeting", [
        ("Opening formalities", "Welcome & attendance", "Open the meeting and record members present."),
        ("Opening formalities", "Acknowledgement of Country", "Respect traditional owners of the land."),
        ("Opening formalities", "Apologies", "Record members who sent apologies for absence."),
        ("Opening formalities", "Minutes of previous AGM", "Read and confirm the minutes from the last AGM."),
        ("Opening formalities", "Business arising from previous minutes", "Any unresolved items from those minutes."),
        ("Annual reports", "President's report", "The club's on-field and off-field season."),
        ("Annual reports", "Treasurer's report & financial statements", "Profit and loss and balance sheet for the financial year."),
        ("Annual reports", "Registrar / Secretary report", "Registration numbers, team nominations, association updates."),
        ("Annual reports", "Junior & coaching coordinator report", "Junior development, Blast programs, coaching."),
        ("Elections and appointments", "Declaration of all positions vacant", "The current committee steps down."),
        ("Elections and appointments", "Election of executive committee", "President, Vice-President, Secretary, Treasurer."),
        ("Elections and appointments", "Election of general committee", "Registrar, junior coordinator, social coordinator, gear steward."),
        ("Elections and appointments", "Appointment of auditor / reviewer", "If your state's incorporation rules require one."),
        ("General business & special motions", "Life memberships & awards", "Vote on or announce new life memberships and club recognitions."),
        ("General business & special motions", "Constitution or rule amendments", "Vote on proposed changes to the constitution or by-laws."),
        ("General business & special motions", "General business", "Member questions, next season's fees, facility proposals."),
        ("Closing", "Date of next meeting", "Set a first date for the incoming committee."),
        ("Closing", "Close of meeting", "Formal close of the AGM."),
    ]),
    ("Committee meeting", [
        ("Opening formalities", "Welcome & attendance", None),
        ("Opening formalities", "Apologies", None),
        ("Opening formalities", "Minutes of previous meeting", "Confirm the last meeting's minutes."),
        ("Opening formalities", "Business arising / action list", "Work through the actions still open."),
        ("Reports", "President's report", None),
        ("Reports", "Treasurer's report", "Accounts, outstanding fees, budget against actual."),
        ("Reports", "Cricket operations / registrar report", "Registrations, teams, selection, association matters."),
        ("Reports", "Junior coordinator report", None),
        ("General business", "Grounds & facilities", None),
        ("General business", "Sponsorship & fundraising", None),
        ("General business", "Social & events", None),
        ("General business", "Volunteers & rosters", None),
        ("Closing", "Other business", None),
        ("Closing", "Date of next meeting", None),
    ]),
]


async def seed_starter_agenda_templates(session: AsyncSession, org_id) -> list[AgendaTemplate]:
    """Add the standard AGM and committee agendas.

    Skips a template the club already has by that name rather than replacing
    it, so pressing the button twice never overwrites an agenda somebody has
    since edited.
    """
    have = {(t.name or "").strip().lower() for t in await list_agenda_templates(session, org_id)}
    made = []
    for name, rows in STARTER_AGENDA_TEMPLATES:
        if name.strip().lower() in have:
            continue
        t = AgendaTemplate(
            organisation_id=org_id, name=name,
            items=[{"section": s, "title": title, "description": desc} for s, title, desc in rows],
        )
        session.add(t)
        made.append(t)
    await session.flush()
    return made


# ─── Agenda templates ─────────────────────────────────────────────────────────

async def list_agenda_templates(session: AsyncSession, org_id) -> list[AgendaTemplate]:
    stmt = select(AgendaTemplate).where(AgendaTemplate.organisation_id == org_id).order_by(func.lower(AgendaTemplate.name))
    return (await session.execute(stmt)).scalars().all()


async def create_agenda_template(session: AsyncSession, org_id, *, name: str, items: Optional[list] = None) -> AgendaTemplate:
    name = (name or "").strip()
    if not name:
        raise ValueError("Name is required")
    existing = (await session.execute(
        select(AgendaTemplate).where(AgendaTemplate.organisation_id == org_id, func.lower(AgendaTemplate.name) == name.lower())
    )).scalars().first()
    if existing is not None:
        raise ValueError(f'A template called "{name}" already exists')
    t = AgendaTemplate(organisation_id=org_id, name=name[:200], items=items or [])
    session.add(t)
    await session.flush()
    return t


async def update_agenda_template(session: AsyncSession, t: AgendaTemplate, **fields) -> AgendaTemplate:
    for f in ("name", "items"):
        if f in fields and fields[f] is not None:
            setattr(t, f, fields[f])
    return t


async def delete_agenda_template(session: AsyncSession, t: AgendaTemplate) -> None:
    await session.delete(t)


# ─── Committee Meeting Assistant: meetings, attendance, agenda, motions ──────

async def list_meetings(session: AsyncSession, org_id, *, meeting_type: Optional[str] = None) -> list[CommitteeMeeting]:
    stmt = select(CommitteeMeeting).where(CommitteeMeeting.organisation_id == org_id)
    if meeting_type:
        stmt = stmt.where(CommitteeMeeting.meeting_type == meeting_type)
    stmt = stmt.order_by(CommitteeMeeting.scheduled_at.desc())
    return (await session.execute(stmt)).scalars().all()


async def _apply_agenda_template(session: AsyncSession, meeting: CommitteeMeeting, template: AgendaTemplate) -> None:
    for pos, item in enumerate(template.items or []):
        if not isinstance(item, dict) or not (item.get("title") or "").strip():
            continue
        session.add(MeetingAgendaItem(
            meeting_id=meeting.id, title=str(item["title"])[:300],
            description=item.get("description"), position=pos,
            # A template written before sections existed simply has none, and
            # its items land under no heading, which is what they always did.
            section=_clean_section(item.get("section")),
        ))


async def create_meeting(session: AsyncSession, org_id, **fields) -> CommitteeMeeting:
    title = (fields.get("title") or "").strip()
    if not title or not fields.get("scheduled_at"):
        raise ValueError("Title and scheduled time are required")
    m = CommitteeMeeting(
        organisation_id=org_id, title=title[:300], meeting_type=fields.get("meeting_type") or "committee",
        scheduled_at=fields["scheduled_at"], location=fields.get("location"),
        agenda_template_id=fields.get("agenda_template_id"),
    )
    session.add(m)
    await session.flush()
    if fields.get("agenda_template_id"):
        template = await session.get(AgendaTemplate, fields["agenda_template_id"])
        if template is not None and template.organisation_id == org_id:
            await _apply_agenda_template(session, m, template)
            await session.flush()
    return m


async def update_meeting(session: AsyncSession, m: CommitteeMeeting, **fields) -> CommitteeMeeting:
    for f in ("title", "meeting_type", "scheduled_at", "location", "status", "minutes",
              "private_notes", "agenda_template_id"):
        # `is not None` rather than presence: a caller clearing minutes sends ""
        # (which sets), while an untouched field is absent from the patch.
        if f in fields and fields[f] is not None:
            setattr(m, f, fields[f])
    m.updated_at = func.now()
    return m


async def delete_meeting(session: AsyncSession, m: CommitteeMeeting) -> None:
    await session.delete(m)


async def meeting_detail(session: AsyncSession, org_id, meeting_id) -> dict:
    """Everything the Committee Meeting Assistant needs for one meeting:
    agenda, motions, attendance and (for an AGM) nominations — one fetch."""
    agenda = (await session.execute(
        select(MeetingAgendaItem).where(MeetingAgendaItem.meeting_id == meeting_id).order_by(MeetingAgendaItem.position)
    )).scalars().all()
    motions = (await session.execute(
        select(MeetingMotion).where(MeetingMotion.meeting_id == meeting_id)
        .order_by(MeetingMotion.position, MeetingMotion.created_at)
    )).scalars().all()
    attendance = (await session.execute(
        select(MeetingAttendance, FeeMember.full_name)
        .join(FeeMember, FeeMember.id == MeetingAttendance.member_id)
        .where(MeetingAttendance.meeting_id == meeting_id)
    )).all()
    nominations = (await session.execute(
        select(AgmNomination).where(AgmNomination.meeting_id == meeting_id).order_by(AgmNomination.created_at)
    )).scalars().all()
    # The actions the meeting raised. They hang off an agenda item, so a viewer
    # can show what each item produced without a second request per item.
    tasks = (await session.execute(
        select(CommitteeTask).where(CommitteeTask.meeting_id == meeting_id)
        .order_by(CommitteeTask.created_at)
    )).scalars().all()
    await load_motion_votes(session, motions)
    return {
        "agenda_items": [_agenda_item_dict(i) for i in agenda],
        "motions": [_motion_dict(mo) for mo in motions],
        "actions": [_task_dict(t) for t in tasks],
        "attendance": [{**_attendance_dict(a), "full_name": name} for a, name in attendance],
        "nominations": [_nomination_dict(n) for n in nominations],
    }


# ─── Attendance ───────────────────────────────────────────────────────────────

async def set_attendance(session: AsyncSession, meeting_id, entries: list[dict]) -> list[MeetingAttendance]:
    """Bulk upsert — ``entries`` is [{member_id, status}]. Replaces the whole
    attendance list for the meeting each call (the UI always sends the full set)."""
    existing = (await session.execute(
        select(MeetingAttendance).where(MeetingAttendance.meeting_id == meeting_id)
    )).scalars().all()
    by_member = {a.member_id: a for a in existing}
    out = []
    seen = set()
    for entry in entries:
        member_id = entry["member_id"]
        seen.add(member_id)
        row = by_member.get(member_id)
        if row is None:
            row = MeetingAttendance(meeting_id=meeting_id, member_id=member_id, status=entry.get("status") or "present")
            session.add(row)
        else:
            row.status = entry.get("status") or "present"
        out.append(row)
    for member_id, row in by_member.items():
        if member_id not in seen:
            await session.delete(row)
    await session.flush()
    return out


# ─── Agenda items ─────────────────────────────────────────────────────────────

async def create_agenda_item(session: AsyncSession, meeting_id, **fields) -> MeetingAgendaItem:
    title = (fields.get("title") or "").strip()
    if not title:
        raise ValueError("Title is required")
    i = MeetingAgendaItem(
        meeting_id=meeting_id, title=title[:300], description=fields.get("description"),
        proposed_by_member_id=fields.get("proposed_by_member_id"), position=fields.get("position") or 0,
        section=_clean_section(fields.get("section")),
    )
    session.add(i)
    await session.flush()
    return i


async def update_agenda_item(session: AsyncSession, i: MeetingAgendaItem, **fields) -> MeetingAgendaItem:
    for f in ("title", "description", "proposed_by_member_id", "position", "status", "outcome_notes"):
        if f in fields and fields[f] is not None:
            setattr(i, f, fields[f])
    # Nullable, so an explicit null takes the item back out of every section.
    if "section" in fields:
        i.section = _clean_section(fields["section"])
    return i


async def delete_agenda_item(session: AsyncSession, i: MeetingAgendaItem) -> None:
    await session.delete(i)


# ─── Motions ──────────────────────────────────────────────────────────────────

async def create_motion(session: AsyncSession, meeting_id, **fields) -> MeetingMotion:
    description = (fields.get("description") or "").strip()
    if not description:
        raise ValueError("Description is required")
    m = MeetingMotion(
        meeting_id=meeting_id, agenda_item_id=fields.get("agenda_item_id"),
        motion_type=fields.get("motion_type") or "motion", description=description[:2000],
        proposed_by_member_id=fields.get("proposed_by_member_id"),
        seconded_by_member_id=fields.get("seconded_by_member_id"),
        objective_id=fields.get("objective_id"),
    )
    session.add(m)
    await session.flush()
    return m


async def update_motion(session: AsyncSession, m: MeetingMotion, **fields) -> MeetingMotion:
    for f in ("agenda_item_id", "motion_type", "description", "proposed_by_member_id", "seconded_by_member_id",
              "votes_for", "votes_against", "votes_abstain", "outcome", "notes"):
        if f in fields and fields[f] is not None:
            setattr(m, f, fields[f])
    # The link to the plan is separate because it has to be CLEARABLE — picking
    # "no objective" is a real choice, and the loop above reads a null as "not
    # sent" so it could never be unset.
    if "objective_id" in fields:
        m.objective_id = fields["objective_id"]
    return m


async def delete_motion(session: AsyncSession, m: MeetingMotion) -> None:
    await session.delete(m)


# ─── AGM nominations ──────────────────────────────────────────────────────────

async def create_nomination(session: AsyncSession, org_id, meeting_id, **fields) -> AgmNomination:
    if not fields.get("position_id") or not fields.get("candidate_member_id"):
        raise ValueError("Position and candidate are required")
    n = AgmNomination(
        organisation_id=org_id, meeting_id=meeting_id, position_id=fields["position_id"],
        candidate_member_id=fields["candidate_member_id"],
        nominated_by_member_id=fields.get("nominated_by_member_id"),
        seconded_by_member_id=fields.get("seconded_by_member_id"),
        notes=fields.get("notes"),
    )
    session.add(n)
    await session.flush()
    return n


async def update_nomination(session: AsyncSession, org_id, n: AgmNomination, *, meeting: Optional[CommitteeMeeting] = None,
                            **fields) -> AgmNomination:
    """Marking a nomination ``elected`` writes a real committee_terms row via
    start_term() — auto-closing whoever held the position — so the AGM result
    and the Positions tab's succession history are the same data, not two."""
    prior_status = n.status
    for f in ("nominated_by_member_id", "seconded_by_member_id", "votes_for", "status", "notes"):
        if f in fields and fields[f] is not None:
            setattr(n, f, fields[f])
    if n.status == "elected" and prior_status != "elected":
        candidate = await session.get(FeeMember, n.candidate_member_id)
        holder_name = candidate.full_name if candidate is not None else "Unknown"
        started = meeting.scheduled_at.date() if meeting is not None and meeting.scheduled_at else None
        await start_term(session, org_id, n.position_id, member_id=n.candidate_member_id,
                         holder_name=holder_name, started_at=started)
    return n


async def delete_nomination(session: AsyncSession, n: AgmNomination) -> None:
    await session.delete(n)


# ─── Governance (migration 217) ───────────────────────────────────────────────
#
# The layer above a meeting: a carried motion recorded as a resolution, who
# voted which way, what an action costs and waits on, the plan it serves, and
# the notes and documents hung off any of it.

_VOTES = ("for", "against", "abstain")
_ENTITIES = ("task", "motion", "meeting", "objective", "plan")


async def set_motion_votes(session: AsyncSession, motion: MeetingMotion, votes: list[dict]) -> MeetingMotion:
    """Replace the named votes on a motion and re-derive its tallies.

    The tallies stay the stored summary because a club that counts hands has
    nothing else. Once names ARE recorded they become the truth, so they are
    what the tallies are computed from — two numbers that could disagree with
    the list beside them would be worse than one.
    """
    from app.models.db import MeetingMotionVote

    await session.execute(delete(MeetingMotionVote).where(MeetingMotionVote.motion_id == motion.id))
    tally = {"for": 0, "against": 0, "abstain": 0}
    for v in votes:
        choice = (v.get("vote") or "").strip().lower()
        member_id = v.get("member_id")
        if choice not in _VOTES or not member_id:
            continue
        session.add(MeetingMotionVote(motion_id=motion.id, member_id=member_id, vote=choice))
        tally[choice] += 1
    if votes:
        motion.votes_for, motion.votes_against, motion.votes_abstain = (
            tally["for"], tally["against"], tally["abstain"])
    await session.flush()
    return motion


async def load_motion_votes(session: AsyncSession, motions: list[MeetingMotion]) -> None:
    """Attach each motion's named votes for serialisation. One query for the
    whole meeting rather than one per motion."""
    from app.models.db import MeetingMotionVote

    ids = [m.id for m in motions]
    if not ids:
        return
    rows = (await session.execute(
        select(MeetingMotionVote).where(MeetingMotionVote.motion_id.in_(ids))
    )).scalars().all()
    by_motion: dict = {}
    for r in rows:
        by_motion.setdefault(r.motion_id, []).append(r)
    for m in motions:
        m._votes = by_motion.get(m.id, [])


async def make_resolution(session: AsyncSession, motion: MeetingMotion, *,
                          ref: Optional[str] = None, on: bool = True) -> MeetingMotion:
    """Record a carried motion as a standing resolution, or take that back.

    Only a carried motion can become one: a resolution the meeting did not pass
    is not a resolution, and letting one be recorded anyway would quietly
    corrupt the minutes.
    """
    if on and (motion.outcome or "").lower() not in ("carried", "passed"):
        raise ValueError("Only a carried motion can be recorded as a resolution")
    motion.is_resolution = bool(on)
    motion.resolution_ref = (ref or "").strip()[:60] or None if on else None
    motion.resolved_at = func.now() if on else None
    await session.flush()
    return motion


async def set_task_dependencies(session: AsyncSession, task_id, depends_on: list) -> list:
    """Replace what an action waits on. Self-dependency is dropped rather than
    rejected — it is a slip, not a decision worth an error."""
    from app.models.db import CommitteeTaskDependency

    await session.execute(delete(CommitteeTaskDependency).where(CommitteeTaskDependency.task_id == task_id))
    kept = []
    for dep in dict.fromkeys(depends_on or []):
        if str(dep) == str(task_id):
            continue
        session.add(CommitteeTaskDependency(task_id=task_id, depends_on_task_id=dep))
        kept.append(dep)
    await session.flush()
    return kept


async def load_task_dependencies(session: AsyncSession, tasks: list[CommitteeTask]) -> None:
    from app.models.db import CommitteeTaskDependency

    ids = [t.id for t in tasks]
    if not ids:
        return
    rows = (await session.execute(
        select(CommitteeTaskDependency).where(CommitteeTaskDependency.task_id.in_(ids))
    )).scalars().all()
    by_task: dict = {}
    for r in rows:
        by_task.setdefault(r.task_id, []).append(r.depends_on_task_id)
    for t in tasks:
        t._depends_on = by_task.get(t.id, [])


async def list_notes(session: AsyncSession, org_id, entity_type: str, entity_id) -> list[dict]:
    from app.models.db import CommitteeNote

    rows = (await session.execute(
        select(CommitteeNote).where(
            CommitteeNote.organisation_id == org_id,
            CommitteeNote.entity_type == entity_type,
            CommitteeNote.entity_id == entity_id,
        ).order_by(CommitteeNote.created_at.desc())
    )).scalars().all()
    return [{
        "id": str(n.id), "body": n.body,
        "author_member_id": str(n.author_member_id) if n.author_member_id else None,
        "author_user_id": str(n.author_user_id) if n.author_user_id else None,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    } for n in rows]


async def add_note(session: AsyncSession, org_id, entity_type: str, entity_id, body: str, *,
                   author_member_id=None, author_user_id=None) -> dict:
    from app.models.db import CommitteeNote

    if entity_type not in _ENTITIES:
        raise ValueError(f"entity_type must be one of {', '.join(_ENTITIES)}")
    text_body = (body or "").strip()
    if not text_body:
        raise ValueError("A note needs some text")
    n = CommitteeNote(organisation_id=org_id, entity_type=entity_type, entity_id=entity_id,
                      body=text_body, author_member_id=author_member_id, author_user_id=author_user_id)
    session.add(n)
    await session.flush()
    return {"id": str(n.id), "body": n.body,
            "author_member_id": str(n.author_member_id) if n.author_member_id else None,
            "author_user_id": str(n.author_user_id) if n.author_user_id else None,
            "created_at": None}


async def delete_note(session: AsyncSession, org_id, note_id) -> bool:
    from app.models.db import CommitteeNote

    n = (await session.execute(
        select(CommitteeNote).where(CommitteeNote.id == note_id, CommitteeNote.organisation_id == org_id)
    )).scalar_one_or_none()
    if not n:
        return False
    await session.delete(n)
    return True


# ─── Strategic plans → objectives → actions and motions (migration 230) ──────
#
# Three levels, each one owning the one below it. A plan is the club's strategic
# or business plan; an objective is a line in it; an action or a motion is the
# work that serves it. Notes hang off any of them.
#
# The rollups below are all DERIVED from the register the committee already
# keeps, never stored — so correcting an action's spend or closing it moves the
# objective and the plan in the same breath, and there is no second set of
# figures to keep in step.

def _pillar_dict(p) -> dict:
    return {
        "id": str(p.id), "name": p.name, "description": p.description,
        "sort_order": p.sort_order, "is_active": p.is_active,
    }


async def list_pillars(session: AsyncSession, org_id, *, include_inactive: bool = False) -> list[dict]:
    from app.models.db import ClubStrategicPillar

    stmt = select(ClubStrategicPillar).where(ClubStrategicPillar.organisation_id == org_id)
    if not include_inactive:
        stmt = stmt.where(ClubStrategicPillar.is_active.is_(True))
    stmt = stmt.order_by(ClubStrategicPillar.sort_order, ClubStrategicPillar.name)
    return [_pillar_dict(p) for p in (await session.execute(stmt)).scalars().all()]


async def upsert_pillar(session: AsyncSession, org_id, pillar_id=None, **fields) -> dict:
    from app.models.db import ClubStrategicPillar

    if pillar_id:
        p = (await session.execute(
            select(ClubStrategicPillar).where(ClubStrategicPillar.id == pillar_id,
                                              ClubStrategicPillar.organisation_id == org_id)
        )).scalar_one_or_none()
        if not p:
            raise ValueError("Pillar not found")
        if "name" in fields and not (fields["name"] or "").strip():
            raise ValueError("A pillar needs a name")
    else:
        name = (fields.get("name") or "").strip()
        if not name:
            raise ValueError("A pillar needs a name")
        p = ClubStrategicPillar(organisation_id=org_id, name=name[:120])
        session.add(p)
    if fields.get("name"):
        p.name = fields["name"].strip()[:120]
    for f in ("sort_order", "is_active"):
        if f in fields and fields[f] is not None:
            setattr(p, f, fields[f])
    if "description" in fields:
        p.description = fields["description"]
    p.updated_at = func.now()
    await session.flush()
    return _pillar_dict(p)


async def delete_pillar(session: AsyncSession, org_id, pillar_id) -> bool:
    """Delete a pillar. Its objectives survive and simply stop being grouped
    under it (FK SET NULL) — a theme being dropped from the plan is not a reason
    to bin the work that was filed under it."""
    from app.models.db import ClubStrategicPillar

    p = (await session.execute(
        select(ClubStrategicPillar).where(ClubStrategicPillar.id == pillar_id,
                                          ClubStrategicPillar.organisation_id == org_id)
    )).scalar_one_or_none()
    if not p:
        return False
    await session.delete(p)
    return True


def _plan_dict(p) -> dict:
    return {
        "id": str(p.id), "name": p.name, "description": p.description,
        "start_year": p.start_year, "end_year": p.end_year,
        "status": p.status, "sort_order": p.sort_order,
    }


async def list_plans(session: AsyncSession, org_id, *, include_archived: bool = False) -> list[dict]:
    from app.models.db import ClubStrategicPlan

    stmt = select(ClubStrategicPlan).where(ClubStrategicPlan.organisation_id == org_id)
    if not include_archived:
        stmt = stmt.where(ClubStrategicPlan.status != "archived")
    stmt = stmt.order_by(ClubStrategicPlan.sort_order,
                         ClubStrategicPlan.start_year.desc().nullslast(),
                         ClubStrategicPlan.name)
    return [_plan_dict(p) for p in (await session.execute(stmt)).scalars().all()]


async def upsert_plan(session: AsyncSession, org_id, plan_id=None, **fields) -> dict:
    from app.models.db import ClubStrategicPlan

    if plan_id:
        p = (await session.execute(
            select(ClubStrategicPlan).where(ClubStrategicPlan.id == plan_id,
                                            ClubStrategicPlan.organisation_id == org_id)
        )).scalar_one_or_none()
        if not p:
            raise ValueError("Plan not found")
        if "name" in fields and not (fields["name"] or "").strip():
            raise ValueError("A plan needs a name")
    else:
        name = (fields.get("name") or "").strip()
        if not name:
            raise ValueError("A plan needs a name")
        p = ClubStrategicPlan(organisation_id=org_id, name=name[:300])
        session.add(p)
    if "name" in fields and fields["name"]:
        p.name = fields["name"].strip()[:300]
    for f in ("status", "sort_order"):
        if f in fields and fields[f] is not None:
            setattr(p, f, fields[f])
    # Nullable, so an explicit null clears it — the caller only sends what was
    # actually edited.
    for f in ("description", "start_year", "end_year"):
        if f in fields:
            setattr(p, f, fields[f])
    p.updated_at = func.now()
    await session.flush()
    return _plan_dict(p)


async def delete_plan(session: AsyncSession, org_id, plan_id) -> bool:
    """Delete a plan. Its objectives survive and fall back to belonging to no
    plan (FK SET NULL) — an objective is real work the club committed to, and
    binning it because the document it was written in was deleted would lose
    every action and motion serving it too."""
    from app.models.db import ClubStrategicPlan

    p = (await session.execute(
        select(ClubStrategicPlan).where(ClubStrategicPlan.id == plan_id,
                                        ClubStrategicPlan.organisation_id == org_id)
    )).scalar_one_or_none()
    if not p:
        return False
    await session.delete(p)
    return True


def _objective_dict(o, *, plan_name: Optional[str] = None, pillar_name: Optional[str] = None,
                    owner_position_name: Optional[str] = None) -> dict:
    return {
        "id": str(o.id), "title": o.title, "description": o.description,
        "season_year": o.season_year, "status": o.status, "sort_order": o.sort_order,
        # Migration 230 — the plan it belongs to and what it is planned with.
        "plan_id": str(o.plan_id) if o.plan_id else None,
        "plan_name": plan_name,
        "due_date": o.due_date.isoformat() if o.due_date else None,
        "owner_member_id": str(o.owner_member_id) if o.owner_member_id else None,
        "budget": float(o.budget) if o.budget is not None else None,
        # Migration 232 — the theme it groups under, and a seat that owns it.
        "pillar_id": str(o.pillar_id) if o.pillar_id else None,
        "pillar_name": pillar_name,
        "owner_position_id": str(o.owner_position_id) if o.owner_position_id else None,
        "owner_position_name": owner_position_name,
    }


async def _plan_names(session: AsyncSession, org_id) -> dict:
    from app.models.db import ClubStrategicPlan

    rows = (await session.execute(
        select(ClubStrategicPlan.id, ClubStrategicPlan.name)
        .where(ClubStrategicPlan.organisation_id == org_id)
    )).all()
    return {str(i): n for i, n in rows}


async def _objective_labels(session: AsyncSession, org_id) -> tuple[dict, dict, dict]:
    """The names behind an objective's three foreign keys, looked up once for a
    whole list rather than a join per row."""
    from app.models.db import ClubStrategicPillar

    plans = await _plan_names(session, org_id)
    pillars = {str(i): n for i, n in (await session.execute(
        select(ClubStrategicPillar.id, ClubStrategicPillar.name)
        .where(ClubStrategicPillar.organisation_id == org_id)
    )).all()}
    positions = {str(i): n for i, n in (await session.execute(
        select(CommitteePosition.id, CommitteePosition.name)
        .where(CommitteePosition.organisation_id == org_id)
    )).all()}
    return plans, pillars, positions


async def list_objectives(session: AsyncSession, org_id, *, include_archived: bool = False,
                          plan_id=None) -> list[dict]:
    from app.models.db import ClubObjective

    stmt = select(ClubObjective).where(ClubObjective.organisation_id == org_id)
    if not include_archived:
        stmt = stmt.where(ClubObjective.status != "archived")
    if plan_id:
        stmt = stmt.where(ClubObjective.plan_id == plan_id)
    stmt = stmt.order_by(ClubObjective.sort_order, ClubObjective.title)
    plans, pillars, positions = await _objective_labels(session, org_id)
    return [_objective_dict(o, plan_name=plans.get(str(o.plan_id)),
                            pillar_name=pillars.get(str(o.pillar_id)),
                            owner_position_name=positions.get(str(o.owner_position_id)))
            for o in (await session.execute(stmt)).scalars().all()]


async def upsert_objective(session: AsyncSession, org_id, objective_id=None, **fields) -> dict:
    from app.models.db import ClubObjective, ClubStrategicPlan

    if objective_id:
        o = (await session.execute(
            select(ClubObjective).where(ClubObjective.id == objective_id,
                                        ClubObjective.organisation_id == org_id)
        )).scalar_one_or_none()
        if not o:
            raise ValueError("Objective not found")
        if "title" in fields and not (fields["title"] or "").strip():
            raise ValueError("Title is required")
    else:
        title = (fields.get("title") or "").strip()
        if not title:
            raise ValueError("Title is required")
        o = ClubObjective(organisation_id=org_id, title=title[:300])
        session.add(o)
    # A plan, pillar or position from another club would file this objective
    # under someone else's, so each is checked rather than trusted — the ids
    # come from a browser.
    from app.models.db import ClubStrategicPillar
    for field, model, label in (
        ("plan_id", ClubStrategicPlan, "plan"),
        ("pillar_id", ClubStrategicPillar, "pillar"),
        ("owner_position_id", CommitteePosition, "committee position"),
    ):
        if fields.get(field):
            owned = (await session.execute(
                select(model.id).where(model.id == fields[field],
                                       model.organisation_id == org_id)
            )).scalar_one_or_none()
            if not owned:
                raise ValueError(f"That {label} does not belong to this club")
    if "title" in fields and fields["title"]:
        o.title = fields["title"].strip()[:300]
    for f in ("status", "sort_order"):
        if f in fields and fields[f] is not None:
            setattr(o, f, fields[f])
    for f in ("description", "season_year", "plan_id", "due_date", "owner_member_id", "budget",
              "pillar_id", "owner_position_id"):
        if f in fields:
            setattr(o, f, fields[f])
    o.updated_at = func.now()
    await session.flush()
    plans, pillars, positions = await _objective_labels(session, org_id)
    return _objective_dict(o, plan_name=plans.get(str(o.plan_id)),
                           pillar_name=pillars.get(str(o.pillar_id)),
                           owner_position_name=positions.get(str(o.owner_position_id)))


async def delete_objective(session: AsyncSession, org_id, objective_id) -> bool:
    from app.models.db import ClubObjective

    o = (await session.execute(
        select(ClubObjective).where(ClubObjective.id == objective_id,
                                    ClubObjective.organisation_id == org_id)
    )).scalar_one_or_none()
    if not o:
        return False
    await session.delete(o)   # actions and motions fall back to no objective (FK SET NULL)
    return True


def _delivery(tasks: list, *, own_budget=None, own_due=None, today: Optional[date] = None) -> dict:
    """Roll a set of actions up into how the thing they serve is going.

    Two rules worth keeping. Progress is the mean of the actions' own
    percentages, so an objective with one action half done reads 50%, not 0% —
    "done or not done" is not how a season of work looks. And the budget is the
    objective's OWN allocation when it has one, falling back to the sum of what
    its actions were budgeted; a club that sets a figure at the plan level and
    a club that only budgets per action both get a percentage that means
    something.
    """
    today = today or date.today()
    done = [t for t in tasks if (t.status or "") == "done"]
    spent = float(sum(t.actual_expenditure or 0 for t in tasks))
    action_budget = float(sum(t.budget_estimate or 0 for t in tasks))
    budget = float(own_budget) if own_budget is not None else action_budget
    percent = round(sum(t.percent_complete or 0 for t in tasks) / len(tasks)) if tasks else 0
    overdue = [t for t in tasks if t.due_date and t.due_date < today and (t.status or "") != "done"]
    # Late means the deadline has gone by with work outstanding. An objective
    # past its own due date is late even with no actions against it — nothing
    # was done, which is the worst version of late, not an excuse from it.
    own_late = bool(own_due and own_due < today and percent < 100)
    return {
        "actions": len(tasks),
        "actions_done": len(done),
        "actions_overdue": len(overdue),
        "percent_complete": percent,
        "budget": budget,
        "budget_from_actions": action_budget,
        "spent": spent,
        "percent_spent": round(spent / budget * 100) if budget else None,
        "over_budget": bool(budget and spent > budget),
        "is_late": bool(own_late or overdue),
    }


async def objective_progress(session: AsyncSession, org_id, *, include_archived: bool = False) -> list[dict]:
    """Each objective with the actions serving it rolled up: how many are done,
    what they were budgeted and what they have cost. This is the club's plan
    reported against itself, from the same action register the committee already
    keeps rather than a second spreadsheet."""
    objectives = await list_objectives(session, org_id, include_archived=include_archived)
    rows = (await session.execute(
        select(CommitteeTask).where(CommitteeTask.organisation_id == org_id,
                                    CommitteeTask.objective_id.isnot(None))
    )).scalars().all()
    by_obj: dict = {}
    for t in rows:
        by_obj.setdefault(str(t.objective_id), []).append(t)
    today = date.today()
    # `budget` comes back as the EFFECTIVE figure (the objective's own
    # allocation, or the sum of its actions'), so `own_budget` keeps what the
    # club actually allocated. Without it a rolled-up 0 is indistinguishable
    # from "nothing allocated", and the screen says "allocated $0" about an
    # objective nobody has budgeted — and its edit form seeds a 0 the club
    # never typed.
    return [{
        **o,
        "own_budget": o["budget"],
        **_delivery(by_obj.get(o["id"], []),
                    own_budget=o["budget"],
                    own_due=date.fromisoformat(o["due_date"]) if o["due_date"] else None,
                    today=today),
    } for o in objectives]


# The four themes nearly every community club's plan comes down to, and one
# recognisable objective under each. A committee that opens a filled-in plan and
# deletes what does not apply will finish; one that opens an empty page will not.
STARTER_PILLARS = [
    ("On-field & participation", "Player numbers, pathways, coaching and results.",
     "Grow player registrations across juniors and seniors"),
    ("Finances & fundraising", "Revenue, sponsorship, grants and the club's reserves.",
     "Secure three new local sponsors"),
    ("Volunteers & governance", "Committee workload, compliance and club administration.",
     "Every coach and team manager holds a current WWCC"),
    ("Facilities & community", "Grounds, nets, equipment and the club's place locally.",
     "Improve the training nets"),
]


def _season_label(start_month: int, today: Optional[date] = None) -> str:
    """The club's own year, e.g. "2026/27" for a July start. Uses the diary
    year the club already configured rather than inventing a second idea of
    when a season runs."""
    today = today or date.today()
    start = today.year if today.month >= (start_month or 7) else today.year - 1
    return f"{start}/{str(start + 1)[-2:]}"


async def seed_starter_plan(session: AsyncSession, org_id) -> dict:
    """Give a club a plan to edit instead of an empty page.

    Adds the four pillars, a plan for the club's current year, and one example
    objective per pillar. Skips a pillar the club already has by name, and only
    creates the plan (and its examples) when there is no plan by that name — so
    pressing the button twice never duplicates anything or overwrites work.
    """
    from app.models.db import ClubObjective, ClubStrategicPillar, ClubStrategicPlan, Organisation

    org = await session.get(Organisation, org_id)
    label = _season_label(getattr(org, "diary_start_month", 7) or 7)
    plan_name = f"Club Plan {label}"

    have_pillars = {p["name"].strip().lower(): p["id"]
                    for p in await list_pillars(session, org_id, include_inactive=True)}
    pillar_ids: dict = {}
    made_pillars = []
    for order, (name, desc, _objective) in enumerate(STARTER_PILLARS):
        existing = have_pillars.get(name.strip().lower())
        if existing:
            pillar_ids[name] = uuid.UUID(existing)
            continue
        p = ClubStrategicPillar(organisation_id=org_id, name=name, description=desc, sort_order=order)
        session.add(p)
        await session.flush()
        pillar_ids[name] = p.id
        made_pillars.append(_pillar_dict(p))

    existing_plan = (await session.execute(
        select(ClubStrategicPlan).where(ClubStrategicPlan.organisation_id == org_id,
                                        func.lower(ClubStrategicPlan.name) == plan_name.lower())
    )).scalars().first()
    if existing_plan is not None:
        return {"plan": _plan_dict(existing_plan), "pillars": made_pillars,
                "objectives": [], "created_plan": False}

    year = int(label.split("/")[0])
    plan = ClubStrategicPlan(
        organisation_id=org_id, name=plan_name, start_year=year, end_year=year + 1,
        description="What the club is setting out to do this year. Edit anything here, "
                    "or delete what does not apply.",
    )
    session.add(plan)
    await session.flush()

    objectives = []
    for order, (name, _desc, title) in enumerate(STARTER_PILLARS):
        o = ClubObjective(organisation_id=org_id, title=title, plan_id=plan.id,
                          pillar_id=pillar_ids[name], sort_order=order)
        session.add(o)
        objectives.append(o)
    await session.flush()
    return {
        "plan": _plan_dict(plan), "pillars": made_pillars,
        "objectives": [{"id": str(o.id), "title": o.title} for o in objectives],
        "created_plan": True,
    }


async def plan_report(session: AsyncSession, org_id, *, include_archived: bool = False) -> dict:
    """The whole plan, top to bottom: every strategic plan, its objectives, and
    the actions and motions serving each one.

    One fetch rather than a request per level. The screen that reads this is
    asking "how is the plan going", and a plan whose progress arrives in six
    round trips is a plan nobody looks at.
    """
    from app.models.db import ClubObjective

    plans = await list_plans(session, org_id, include_archived=include_archived)
    objectives = await objective_progress(session, org_id, include_archived=include_archived)

    obj_ids = [uuid.UUID(o["id"]) for o in objectives]
    tasks = (await session.execute(
        select(CommitteeTask)
        .where(CommitteeTask.organisation_id == org_id, CommitteeTask.objective_id.isnot(None))
        .order_by(CommitteeTask.due_date.asc().nullslast(), CommitteeTask.created_at)
    )).scalars().all()
    await load_task_assignees(session, tasks)

    # Motions are scoped through their MEETING's org, not the objective's —
    # meeting_motions has no organisation_id of its own, and an objective id
    # arriving from another club must not be able to pull that club's motions
    # into this report.
    motion_rows = []
    if obj_ids:
        motion_rows = (await session.execute(
            select(MeetingMotion, CommitteeMeeting.title, CommitteeMeeting.scheduled_at)
            .join(CommitteeMeeting, CommitteeMeeting.id == MeetingMotion.meeting_id)
            .where(CommitteeMeeting.organisation_id == org_id,
                   MeetingMotion.objective_id.in_(obj_ids))
            .order_by(CommitteeMeeting.scheduled_at.desc().nullslast())
        )).all()

    # Where each piece of work was raised. An action carries the meeting it came
    # out of, and one raised under a motion inherits that motion's meeting when
    # it has none of its own — "we agreed this in March" is the context that
    # makes a line of the plan mean something, and it is a lookup on data we
    # already hold rather than another request from the screen.
    meetings: dict = {}
    meeting_ids = {t.meeting_id for t in tasks if t.meeting_id}
    motion_meeting: dict = {str(m.id): m.meeting_id for m, _t, _s in motion_rows}
    meeting_ids |= {motion_meeting[str(t.motion_id)]
                    for t in tasks if t.motion_id and str(t.motion_id) in motion_meeting}
    if meeting_ids:
        # Org-scoped: a meeting id reached through a task must still belong to
        # this club before its title is served back.
        rows = (await session.execute(
            select(CommitteeMeeting.id, CommitteeMeeting.title, CommitteeMeeting.scheduled_at)
            .where(CommitteeMeeting.organisation_id == org_id,
                   CommitteeMeeting.id.in_(meeting_ids))
        )).all()
        meetings = {str(i): (t, s) for i, t, s in rows}

    def _raised_at(t) -> dict:
        mid = str(t.meeting_id) if t.meeting_id else None
        if not mid and t.motion_id:
            via = motion_meeting.get(str(t.motion_id))
            mid = str(via) if via else None
        title, when = meetings.get(mid or "", (None, None))
        # Deliberately NOT `meeting_id` — that key already means the action's own
        # column, and overwriting it with a meeting reached through the motion
        # would have the row claim a link it does not hold.
        return {
            "raised_meeting_id": mid,
            "meeting_title": title,
            "meeting_date": when.isoformat() if when else None,
        }

    tasks_by_obj: dict = {}
    for t in tasks:
        tasks_by_obj.setdefault(str(t.objective_id), []).append(t)
    motions_by_obj: dict = {}
    for m, meeting_title, scheduled_at in motion_rows:
        motions_by_obj.setdefault(str(m.objective_id), []).append({
            **_motion_dict(m),
            "meeting_title": meeting_title,
            "meeting_date": scheduled_at.isoformat() if scheduled_at else None,
        })

    filled = [{
        **o,
        "action_list": [{**_task_dict(t), **_raised_at(t)} for t in tasks_by_obj.get(o["id"], [])],
        "motion_list": motions_by_obj.get(o["id"], []),
    } for o in objectives]

    by_plan: dict = {}
    for o in filled:
        by_plan.setdefault(o["plan_id"] or "", []).append(o)

    def roll(group: list[dict]) -> dict:
        """A plan's own figures are the sum of its objectives', not a second
        pass over the actions — otherwise an objective with its own budget and
        an objective budgeted through its actions would be added up two
        different ways in the same total."""
        budget = sum(o["budget"] or 0 for o in group)
        spent = sum(o["spent"] or 0 for o in group)
        return {
            "objectives": len(group),
            "objectives_done": sum(1 for o in group if o["percent_complete"] >= 100),
            "actions": sum(o["actions"] for o in group),
            "actions_done": sum(o["actions_done"] for o in group),
            "motions": sum(len(o["motion_list"]) for o in group),
            "percent_complete": round(sum(o["percent_complete"] for o in group) / len(group)) if group else 0,
            "budget": budget,
            "spent": spent,
            "percent_spent": round(spent / budget * 100) if budget else None,
            "over_budget": bool(budget and spent > budget),
            "late_objectives": sum(1 for o in group if o["is_late"]),
        }

    return {
        # The club's themes, so the screen can group and filter objectives by
        # one without a second request.
        "pillars": await list_pillars(session, org_id),
        "plans": [{**p, "objective_list": by_plan.get(p["id"], []), **roll(by_plan.get(p["id"], []))}
                  for p in plans],
        # An objective can sit outside every plan — either because the club has
        # not written one down yet, or because the plan it belonged to was
        # deleted. It is still real work, so it is reported rather than hidden.
        "unassigned": {"objective_list": by_plan.get("", []), **roll(by_plan.get("", []))},
    }


# ─── The meeting room ─────────────────────────────────────────────────────────
#
# One screen a secretary runs a meeting from: work down the agenda, record who
# is there, take motions and votes, raise actions, keep minutes. Everything
# below exists so that screen can be driven from one fetch and a handful of
# small writes, rather than a dozen round trips per agenda item.


async def reorder_agenda_items(session: AsyncSession, meeting_id, item_ids: list,
                               sections: Optional[list] = None) -> None:
    """Persist a dragged agenda order, and optionally which section each item
    now sits in.

    Order and section move together in one write because dragging an item under
    a different heading is one action to the person doing it. Two requests could
    half-succeed and leave an item sitting under a heading it is not in.

    Ids not belonging to this meeting are ignored rather than trusted — the list
    comes from a browser.
    """
    rows = (await session.execute(
        select(MeetingAgendaItem).where(MeetingAgendaItem.meeting_id == meeting_id)
    )).scalars().all()
    by_id = {str(r.id): r for r in rows}
    # Only honoured when it lines up with the ids, so a mismatched pair of
    # arrays cannot shuffle sections onto the wrong items.
    aligned = sections if sections is not None and len(sections) == len(item_ids) else None
    for i, raw in enumerate(item_ids):
        row = by_id.get(str(raw))
        if row is None:
            continue
        row.position = i
        if aligned is not None:
            row.section = _clean_section(aligned[i])
    await session.flush()


async def reorder_motions(session: AsyncSession, meeting_id, motion_ids: list) -> None:
    rows = (await session.execute(
        select(MeetingMotion).where(MeetingMotion.meeting_id == meeting_id)
    )).scalars().all()
    by_id = {str(r.id): r for r in rows}
    for i, raw in enumerate(motion_ids):
        row = by_id.get(str(raw))
        if row is not None:
            row.position = i
    await session.flush()


async def set_task_assignees(session: AsyncSession, task: CommitteeTask, member_ids: list) -> list:
    """Replace who owns an action.

    The first id also becomes ``assigned_to_member_id``. That column predates
    this table and is what the board, the timeline and every existing report
    read, so it has to keep meaning "the person this sits with".
    """
    await session.execute(
        delete(CommitteeTaskAssignee).where(CommitteeTaskAssignee.task_id == task.id)
    )
    kept = []
    for mid in dict.fromkeys(member_ids or []):
        session.add(CommitteeTaskAssignee(task_id=task.id, member_id=mid))
        kept.append(mid)
    task.assigned_to_member_id = kept[0] if kept else None
    await session.flush()
    return kept


async def load_task_assignees(session: AsyncSession, tasks: list) -> None:
    ids = [t.id for t in tasks]
    if not ids:
        return
    rows = (await session.execute(
        select(CommitteeTaskAssignee).where(CommitteeTaskAssignee.task_id.in_(ids))
    )).scalars().all()
    by_task: dict = {}
    for r in rows:
        by_task.setdefault(r.task_id, []).append(r.member_id)
    for t in tasks:
        # Fall back to the single owner for an action created before this table,
        # so an old action still shows someone rather than nobody.
        t._assignees = by_task.get(t.id) or ([t.assigned_to_member_id] if t.assigned_to_member_id else [])


async def meeting_attendee_pool(session: AsyncSession, org_id) -> list[dict]:
    """Who to offer for attendance and votes.

    Committee members come first and are flagged, because they are who is
    normally in the room; scrolling a 300-name membership to tick six people is
    the thing this replaces. Everyone else is still returned so a guest or a
    late co-opted member can be found by typing, without a second request.
    """
    # The position each current committee member holds, so the screen can show
    # "President" beside a name and default the chair to whoever that is.
    held = (await session.execute(
        select(CommitteeTerm.member_id, CommitteePosition.name, CommitteePosition.is_office_bearer)
        .join(CommitteePosition, CommitteePosition.id == CommitteeTerm.position_id)
        .where(
            CommitteeTerm.organisation_id == org_id,
            CommitteeTerm.ended_at.is_(None),
            CommitteeTerm.member_id.isnot(None),
        )
    )).all()
    position_by = {}
    for _mid, _name, _is_ob in held:
        # An office-bearer title wins when someone holds more than one seat:
        # "President" is what belongs next to their name, not "Bar Manager".
        if _mid not in position_by or (_is_ob and not position_by[_mid][1]):
            position_by[_mid] = (_name, bool(_is_ob))
    on_committee = set(position_by)
    rows = (await session.execute(
        select(FeeMember.id, FeeMember.full_name)
        .where(FeeMember.organisation_id == org_id)
        .order_by(func.lower(FeeMember.full_name))
    )).all()
    out = [{
        "member_id": str(mid), "full_name": name,
        "on_committee": mid in on_committee,
        "position": position_by.get(mid, (None, False))[0],
    } for mid, name in rows]
    out.sort(key=lambda r: (not r["on_committee"], r["full_name"].lower()))
    return out


async def previous_meeting_attendance(session: AsyncSession, org_id, meeting: CommitteeMeeting) -> Optional[dict]:
    """Who was present at the last meeting of this kind.

    Committee attendance is largely the same people every month, so retyping it
    is the sort of chore that gets skipped and then the record is wrong. This
    finds the most recent EARLIER meeting of the same type that actually
    recorded someone present, and hands back that list for the screen to offer.

    Only the people marked present come back. An apology is about one evening —
    carrying it forward would assert something nobody said.
    """
    prior = (await session.execute(
        select(CommitteeMeeting)
        .where(
            CommitteeMeeting.organisation_id == org_id,
            CommitteeMeeting.meeting_type == meeting.meeting_type,
            CommitteeMeeting.id != meeting.id,
            CommitteeMeeting.scheduled_at < meeting.scheduled_at,
        )
        .order_by(CommitteeMeeting.scheduled_at.desc())
        .limit(10)
    )).scalars().all()
    for p in prior:
        rows = (await session.execute(
            select(MeetingAttendance.member_id)
            .where(MeetingAttendance.meeting_id == p.id, MeetingAttendance.status == "present")
        )).scalars().all()
        if rows:
            return {
                "meeting_id": str(p.id), "title": p.title,
                "scheduled_at": p.scheduled_at.isoformat() if p.scheduled_at else None,
                "present_member_ids": [str(m) for m in rows],
            }
    return None


async def meeting_room(session: AsyncSession, org_id, meeting: CommitteeMeeting) -> dict:
    """Everything the live screen needs, in one fetch."""
    detail = await meeting_detail(session, org_id, meeting.id)
    tasks = (await session.execute(
        select(CommitteeTask)
        .where(CommitteeTask.organisation_id == org_id, CommitteeTask.meeting_id == meeting.id)
        .order_by(CommitteeTask.created_at)
    )).scalars().all()
    await load_task_assignees(session, tasks)
    return {
        "meeting": _meeting_dict(meeting),
        **detail,
        "actions": [_task_dict(t) for t in tasks],
        "attendee_pool": await meeting_attendee_pool(session, org_id),
        "previous_attendance": await previous_meeting_attendance(session, org_id, meeting),
    }
