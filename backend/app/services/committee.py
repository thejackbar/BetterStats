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

from sqlalchemy import select, func, delete
from sqlalchemy.orm import defer
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import (
    CommitteePosition, CommitteeTerm, CommitteeTask, CommitteeDocument, ClubEvent,
    AgendaTemplate, CommitteeMeeting, MeetingAttendance, MeetingAgendaItem, MeetingMotion,
    AgmNomination, FeeMember, ClubRole, ClubRoleType, ClubMembership,
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
        "agenda_template_id": str(m.agenda_template_id) if m.agenda_template_id else None,
    }


def _attendance_dict(a: MeetingAttendance) -> dict:
    return {"id": str(a.id), "meeting_id": str(a.meeting_id), "member_id": str(a.member_id), "status": a.status}


def _agenda_item_dict(i: MeetingAgendaItem) -> dict:
    return {
        "id": str(i.id), "meeting_id": str(i.meeting_id), "title": i.title, "description": i.description,
        "proposed_by_member_id": str(i.proposed_by_member_id) if i.proposed_by_member_id else None,
        "position": i.position, "status": i.status, "outcome_notes": i.outcome_notes,
    }


def _motion_dict(m: MeetingMotion) -> dict:
    return {
        "id": str(m.id), "meeting_id": str(m.meeting_id),
        "agenda_item_id": str(m.agenda_item_id) if m.agenda_item_id else None,
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


async def update_task(session: AsyncSession, t: CommitteeTask, **fields) -> CommitteeTask:
    for f in ("title", "description", "category", "position_id", "assigned_to_member_id",
              "due_date", "status", "is_recurring", "recurrence_note",
              "objective_id", "budget_estimate", "actual_expenditure", "percent_complete",
              "start_date", "closed_by_member_id", "outcome_notes", "meeting_id", "motion_id"):
        if f in fields and fields[f] is not None:
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
    for f in ("title", "meeting_type", "scheduled_at", "location", "status", "minutes", "agenda_template_id"):
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
        select(MeetingMotion).where(MeetingMotion.meeting_id == meeting_id).order_by(MeetingMotion.created_at)
    )).scalars().all()
    attendance = (await session.execute(
        select(MeetingAttendance, FeeMember.full_name)
        .join(FeeMember, FeeMember.id == MeetingAttendance.member_id)
        .where(MeetingAttendance.meeting_id == meeting_id)
    )).all()
    nominations = (await session.execute(
        select(AgmNomination).where(AgmNomination.meeting_id == meeting_id).order_by(AgmNomination.created_at)
    )).scalars().all()
    await load_motion_votes(session, motions)
    return {
        "agenda_items": [_agenda_item_dict(i) for i in agenda],
        "motions": [_motion_dict(mo) for mo in motions],
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
    )
    session.add(i)
    await session.flush()
    return i


async def update_agenda_item(session: AsyncSession, i: MeetingAgendaItem, **fields) -> MeetingAgendaItem:
    for f in ("title", "description", "proposed_by_member_id", "position", "status", "outcome_notes"):
        if f in fields and fields[f] is not None:
            setattr(i, f, fields[f])
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
    )
    session.add(m)
    await session.flush()
    return m


async def update_motion(session: AsyncSession, m: MeetingMotion, **fields) -> MeetingMotion:
    for f in ("agenda_item_id", "motion_type", "description", "proposed_by_member_id", "seconded_by_member_id",
              "votes_for", "votes_against", "votes_abstain", "outcome", "notes"):
        if f in fields and fields[f] is not None:
            setattr(m, f, fields[f])
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
_ENTITIES = ("task", "motion", "meeting", "objective")


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


def _objective_dict(o) -> dict:
    return {
        "id": str(o.id), "title": o.title, "description": o.description, "plan": o.plan,
        "season_year": o.season_year, "status": o.status, "sort_order": o.sort_order,
    }


async def list_objectives(session: AsyncSession, org_id, *, include_archived: bool = False) -> list[dict]:
    from app.models.db import ClubObjective

    stmt = select(ClubObjective).where(ClubObjective.organisation_id == org_id)
    if not include_archived:
        stmt = stmt.where(ClubObjective.status != "archived")
    stmt = stmt.order_by(ClubObjective.sort_order, ClubObjective.title)
    return [_objective_dict(o) for o in (await session.execute(stmt)).scalars().all()]


async def upsert_objective(session: AsyncSession, org_id, objective_id=None, **fields) -> dict:
    from app.models.db import ClubObjective

    if objective_id:
        o = (await session.execute(
            select(ClubObjective).where(ClubObjective.id == objective_id,
                                        ClubObjective.organisation_id == org_id)
        )).scalar_one_or_none()
        if not o:
            raise ValueError("Objective not found")
    else:
        title = (fields.get("title") or "").strip()
        if not title:
            raise ValueError("Title is required")
        o = ClubObjective(organisation_id=org_id, title=title[:300])
        session.add(o)
    for f in ("title", "description", "plan", "season_year", "status", "sort_order"):
        if f in fields and fields[f] is not None:
            setattr(o, f, fields[f])
    o.updated_at = func.now()
    await session.flush()
    return _objective_dict(o)


async def delete_objective(session: AsyncSession, org_id, objective_id) -> bool:
    from app.models.db import ClubObjective

    o = (await session.execute(
        select(ClubObjective).where(ClubObjective.id == objective_id,
                                    ClubObjective.organisation_id == org_id)
    )).scalar_one_or_none()
    if not o:
        return False
    await session.delete(o)   # actions fall back to no objective (FK SET NULL)
    return True


async def objective_progress(session: AsyncSession, org_id) -> list[dict]:
    """Each objective with the actions serving it rolled up: how many are done,
    what they were budgeted and what they have cost. This is the club's plan
    reported against itself, from the same action register the committee already
    keeps rather than a second spreadsheet."""
    objectives = await list_objectives(session, org_id)
    rows = (await session.execute(
        select(CommitteeTask).where(CommitteeTask.organisation_id == org_id,
                                    CommitteeTask.objective_id.isnot(None))
    )).scalars().all()
    by_obj: dict = {}
    for t in rows:
        by_obj.setdefault(str(t.objective_id), []).append(t)
    out = []
    for o in objectives:
        tasks = by_obj.get(o["id"], [])
        done = [t for t in tasks if (t.status or "") == "done"]
        out.append({
            **o,
            "actions": len(tasks),
            "actions_done": len(done),
            "percent_complete": round(sum(t.percent_complete or 0 for t in tasks) / len(tasks)) if tasks else 0,
            "budget": float(sum(t.budget_estimate or 0 for t in tasks)),
            "spent": float(sum(t.actual_expenditure or 0 for t in tasks)),
        })
    return out
