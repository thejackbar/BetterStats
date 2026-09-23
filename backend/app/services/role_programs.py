"""Role Programs — what a role entails, and the measurable handover of it.

TWO HALVES, ONE ANCHOR (club_roles).

  1. The PROGRAM is assembled on read (assemble_program) — it has no storage.
     A role's purpose is its club_roles.description; its recurring / seasonal /
     matchday duties are the Club Diary tasks whose responsibility_role_id is
     this role (grouped by the cadence set widened for this feature); the
     operational areas it covers are its roster_areas; a committee role also
     carries its position's responsibilities and current holder. So a club that
     has already built a diary and a roster gets a role program for free, and a
     club that has done nothing still gets a role with a title. Progressive, not
     mandatory — the club's stated requirement.

  2. The HANDOVER is the measurable half (create_handover / the item writers).
     When a role changes hands, a responsible person works a checklist SEEDED
     from the program — one line per duty, per covered area, plus the position's
     responsibilities — and records, per line, whether the incoming volunteer
     has been walked through it and has understood and accepted it. The club
     then SEES the onboarding status and exactly where the gaps are. Each line
     is a SNAPSHOT (label/detail/cadence copied at seed time), so editing a diary
     task later never rewrites what a past handover recorded — the discipline
     committee_terms.holder_name already keeps.

Nothing here measures the quality of the job a volunteer does during their
tenure; the club asked for onboarding visibility, not performance review.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import (
    ClubRole, ClubRoleType, CommitteePosition, CommitteeTerm, VolunteerRole, FeeMember,
    DiaryTaskDefinition, DiaryCategory,
    RoleProgramHandover, RoleProgramHandoverItem,
    ROLE_HANDOVER_STATUSES, ROLE_HANDOVER_ITEM_STATUSES,
)

# Display order + labels for the cadence a duty recurs on — operational
# (matchday/weekly) first, seasonal in the middle, standing responsibilities
# last. Mirrors the model's DIARY_TASK_FREQUENCIES; a cadence not listed sorts
# last under its own raw value.
CADENCE_LABELS = {
    "matchday": "Match day",
    "weekly": "Weekly",
    "monthly": "Monthly",
    "quarterly": "Quarterly",
    "season_start": "Season start",
    "season_end": "Season end",
    "annual": "Annual",
    "once": "One-off",
    "ongoing": "Ongoing responsibility",
}
CADENCE_ORDER = ["matchday", "weekly", "monthly", "quarterly",
                 "season_start", "season_end", "annual", "once", "ongoing"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _cadence_rank(freq: Optional[str]) -> int:
    try:
        return CADENCE_ORDER.index(freq)
    except (ValueError, TypeError):
        return len(CADENCE_ORDER)


# ─── Progress roll-up ────────────────────────────────────────────────────────

def _progress_from_counts(counts: dict) -> dict:
    """Onboarding progress from a {status: count} map. 'applicable' excludes the
    N/A items, and percent is share of the applicable that are understood &
    accepted — so a handover where every real element is accepted reads 100%
    even if some elements were marked not applicable. Gaps are what is left."""
    total = sum(counts.values())
    na = counts.get("na", 0)
    accepted = counts.get("accepted", 0)
    walked = counts.get("walked_through", 0)
    pending = counts.get("pending", 0)
    applicable = total - na
    percent = round(accepted / applicable * 100) if applicable else 0
    return {
        "total": total, "na": na, "applicable": applicable,
        "accepted": accepted, "walked_through": walked, "pending": pending,
        "gaps": walked + pending, "percent": percent,
        "complete": applicable > 0 and accepted == applicable,
    }


def _progress_of_items(items) -> dict:
    counts: dict = {}
    for it in items:
        counts[it.status] = counts.get(it.status, 0) + 1
    return _progress_from_counts(counts)


# ─── Serialisers ─────────────────────────────────────────────────────────────

def _item_dict(it: RoleProgramHandoverItem) -> dict:
    return {
        "id": str(it.id), "source_kind": it.source_kind, "source_key": it.source_key,
        "source_definition_id": str(it.source_definition_id) if it.source_definition_id else None,
        "label": it.label, "detail": it.detail, "cadence": it.cadence,
        "cadence_label": CADENCE_LABELS.get(it.cadence) if it.cadence else None,
        "status": it.status, "target_date": it.target_date.isoformat() if it.target_date else None,
        "note": it.note, "sort_order": it.sort_order,
    }


def _handover_dict(h: RoleProgramHandover, *, progress: Optional[dict] = None,
                   items: Optional[list] = None) -> dict:
    d = {
        "id": str(h.id), "role_id": str(h.role_id) if h.role_id else None,
        "role_title": h.role_title,
        "committee_position_id": str(h.committee_position_id) if h.committee_position_id else None,
        "incoming_member_id": str(h.incoming_member_id) if h.incoming_member_id else None,
        "incoming_name": h.incoming_name,
        "outgoing_member_id": str(h.outgoing_member_id) if h.outgoing_member_id else None,
        "outgoing_name": h.outgoing_name,
        "status": h.status,
        "started_on": h.started_on.isoformat() if h.started_on else None,
        "target_date": h.target_date.isoformat() if h.target_date else None,
        "completed_at": h.completed_at.isoformat() if h.completed_at else None,
        "notes": h.notes,
    }
    if progress is not None:
        d["progress"] = progress
    if items is not None:
        d["items"] = [_item_dict(i) for i in items]
    return d


# ─── Program assembly (read-only) ────────────────────────────────────────────

async def _role_or_none(session: AsyncSession, org_id, role_id) -> Optional[ClubRole]:
    role = await session.get(ClubRole, role_id)
    if role is None or role.organisation_id != org_id:
        return None
    return role


async def _role_duties(session: AsyncSession, org_id, role_id) -> list[dict]:
    """The role's Club Diary tasks (its recurring/seasonal/matchday duties and
    ongoing responsibilities), grouped nowhere — returned flat, cadence-sorted,
    so the frontend can group them however it likes."""
    rows = (await session.execute(
        select(DiaryTaskDefinition, DiaryCategory)
        .outerjoin(DiaryCategory, DiaryCategory.id == DiaryTaskDefinition.category_id)
        .where(DiaryTaskDefinition.organisation_id == org_id,
               DiaryTaskDefinition.responsibility_role_id == role_id,
               DiaryTaskDefinition.is_active.is_(True))
    )).all()
    duties = []
    for d, cat in rows:
        duties.append({
            "definition_id": str(d.id), "title": d.title, "description": d.description,
            "cadence": d.frequency, "cadence_label": CADENCE_LABELS.get(d.frequency, d.frequency),
            "category_name": cat.name if cat else None,
            "category_color": (cat.color if cat else None) or "#8b7cf6",
        })
    duties.sort(key=lambda x: (_cadence_rank(x["cadence"]), x["title"].lower()))
    return duties


async def _role_areas(session: AsyncSession, org_id, role_id) -> list[dict]:
    """Operational roster areas this role covers. Reads the role PALETTE
    (roster_area_roles, migration 306) rather than the deprecated single
    roster_areas.required_role_id, so an area that lists this role among several
    is found and the role's own gating qualification comes across. Both are
    raw-SQL tables (services/roster.py's posture); guarded so an older schema
    without the palette simply reports no areas rather than raising."""
    try:
        rows = (await session.execute(text("""
            SELECT a.id AS id, a.name AS name, qt.name AS qual_name
            FROM roster_area_roles ar
            JOIN roster_areas a ON a.id = ar.area_id
            LEFT JOIN qualification_types qt ON qt.id = ar.required_qualification_type_id
            WHERE ar.organisation_id = :org AND ar.role_id = :role
            ORDER BY lower(a.name)
        """), {"org": org_id, "role": role_id})).mappings().all()
    except Exception:
        return []
    return [{"area_id": str(r["id"]), "name": r["name"], "required_qualification": r["qual_name"]}
            for r in rows]


async def _committee_context(session: AsyncSession, org_id, role: ClubRole) -> Optional[dict]:
    if not role.is_committee:
        return None
    pos = (await session.execute(
        select(CommitteePosition).where(CommitteePosition.organisation_id == org_id,
                                        CommitteePosition.role_id == role.id,
                                        CommitteePosition.is_active.is_(True))
    )).scalars().first()
    if pos is None:
        return None
    term = (await session.execute(
        select(CommitteeTerm).where(CommitteeTerm.position_id == pos.id,
                                    CommitteeTerm.ended_at.is_(None))
        .order_by(CommitteeTerm.started_at.desc())
    )).scalars().first()
    return {
        "position_id": str(pos.id), "responsibilities": pos.responsibilities,
        "is_office_bearer": pos.is_office_bearer,
        "current_holder": term.holder_name if term else None,
        "handover_notes": term.handover_notes if term else None,
    }


async def _current_holders(session: AsyncSession, org_id, role: ClubRole,
                           committee: Optional[dict]) -> list[str]:
    if role.is_committee:
        return [committee["current_holder"]] if committee and committee.get("current_holder") else []
    rows = (await session.execute(
        select(FeeMember.full_name)
        .join(VolunteerRole, VolunteerRole.member_id == FeeMember.id)
        .where(VolunteerRole.organisation_id == org_id, VolunteerRole.role_id == role.id)
        .order_by(func.lower(FeeMember.full_name))
    )).scalars().all()
    return list(rows)


async def _handover_progress_map(session: AsyncSession, handover_ids: list) -> dict:
    """handover_id(str) -> progress dict, via one grouped count over items."""
    if not handover_ids:
        return {}
    rows = (await session.execute(
        select(RoleProgramHandoverItem.handover_id, RoleProgramHandoverItem.status, func.count())
        .where(RoleProgramHandoverItem.handover_id.in_(handover_ids))
        .group_by(RoleProgramHandoverItem.handover_id, RoleProgramHandoverItem.status)
    )).all()
    counts: dict = {}
    for hid, status, n in rows:
        counts.setdefault(str(hid), {})[status] = n
    return {str(hid): _progress_from_counts(counts.get(str(hid), {})) for hid in handover_ids}


async def list_handovers(session: AsyncSession, org_id, *, role_id=None,
                         status: Optional[str] = None) -> list[dict]:
    stmt = select(RoleProgramHandover).where(RoleProgramHandover.organisation_id == org_id)
    if role_id is not None:
        stmt = stmt.where(RoleProgramHandover.role_id == role_id)
    if status:
        stmt = stmt.where(RoleProgramHandover.status == status)
    stmt = stmt.order_by(RoleProgramHandover.started_on.desc(), RoleProgramHandover.created_at.desc())
    rows = (await session.execute(stmt)).scalars().all()
    prog = await _handover_progress_map(session, [h.id for h in rows])
    return [_handover_dict(h, progress=prog.get(str(h.id))) for h in rows]


async def assemble_program(session: AsyncSession, org_id, role_id) -> Optional[dict]:
    role = await _role_or_none(session, org_id, role_id)
    if role is None:
        return None
    rtype = await session.get(ClubRoleType, role.role_type_id) if role.role_type_id else None
    committee = await _committee_context(session, org_id, role)
    duties = await _role_duties(session, org_id, role.id)
    areas = await _role_areas(session, org_id, role.id)
    holders = await _current_holders(session, org_id, role, committee)
    handovers = await list_handovers(session, org_id, role_id=role.id)
    active = next((h for h in handovers if h["status"] == "in_progress"), None)
    return {
        "role": {
            "id": str(role.id), "title": role.title, "description": role.description,
            "is_committee": role.is_committee, "is_active": role.is_active,
            "role_type_id": str(role.role_type_id) if role.role_type_id else None,
            "role_type_name": rtype.name if rtype else None,
            "role_type_category": rtype.category if rtype else None,
        },
        "committee": committee,
        "current_holders": holders,
        "duties": duties,
        "areas": areas,
        "handovers": handovers,
        "active_handover_id": active["id"] if active else None,
    }


# ─── Handover checklist seeding ──────────────────────────────────────────────

async def _program_elements(session: AsyncSession, org_id, role: ClubRole,
                            committee: Optional[dict]) -> list[dict]:
    """Every element a fresh handover should list, in checklist order. Each is a
    (source_kind, source_key, label, detail, cadence, source_definition_id)
    snapshot. source_key is the dedupe key for a reseed; a duty keys on its
    definition id, an area on its id, the position responsibilities on a fixed
    synthetic key."""
    elements: list[dict] = []
    if committee and (committee.get("responsibilities") or "").strip():
        elements.append({
            "source_kind": "responsibility", "source_key": "position:responsibilities",
            "label": "Position responsibilities", "detail": committee["responsibilities"],
            "cadence": None, "source_definition_id": None,
        })
    for d in await _role_duties(session, org_id, role.id):
        kind = "responsibility" if d["cadence"] == "ongoing" else "duty"
        elements.append({
            "source_kind": kind, "source_key": d["definition_id"],
            "label": d["title"], "detail": d["description"], "cadence": d["cadence"],
            "source_definition_id": d["definition_id"],
        })
    for a in await _role_areas(session, org_id, role.id):
        qual = a.get("required_qualification")
        detail = "Roster area" + (f" — needs {qual}" if qual else "")
        elements.append({
            "source_kind": "area", "source_key": f"area:{a['area_id']}",
            "label": f'Cover the "{a["name"]}" roster', "detail": detail,
            "cadence": None, "source_definition_id": None,
        })
    return elements


async def _seed_items(session: AsyncSession, org_id, handover: RoleProgramHandover,
                      role: ClubRole, committee: Optional[dict], *,
                      skip_keys: Optional[set] = None, start_order: int = 0) -> int:
    """Insert one item per program element not already present. Dedupe is on
    (source_kind, source_key); custom items (no source_key) are never seeded
    here and so are never touched by a reseed."""
    skip = skip_keys or set()
    order = start_order
    added = 0
    for el in await _program_elements(session, org_id, role, committee):
        key = (el["source_kind"], el["source_key"])
        if key in skip:
            continue
        session.add(RoleProgramHandoverItem(
            organisation_id=org_id, handover_id=handover.id,
            source_kind=el["source_kind"], source_key=el["source_key"],
            source_definition_id=el["source_definition_id"],
            label=el["label"][:400], detail=el["detail"], cadence=el["cadence"],
            sort_order=order,
        ))
        skip.add(key)
        order += 1
        added += 1
    if added:
        await session.flush()
    return added


async def _resolve_member(session: AsyncSession, org_id, member_id) -> Optional[FeeMember]:
    if not member_id:
        return None
    m = await session.get(FeeMember, member_id)
    if m is None or m.organisation_id != org_id:
        raise ValueError("That member is not in this club")
    return m


async def create_handover(session: AsyncSession, org_id, *, role_id,
                          incoming_member_id=None, incoming_name=None,
                          outgoing_member_id=None, outgoing_name=None,
                          target_date=None, notes=None, created_by=None) -> RoleProgramHandover:
    role = await _role_or_none(session, org_id, role_id)
    if role is None:
        raise ValueError("Role not found")
    incoming = await _resolve_member(session, org_id, incoming_member_id)
    outgoing = await _resolve_member(session, org_id, outgoing_member_id)
    committee = await _committee_context(session, org_id, role)
    handover = RoleProgramHandover(
        organisation_id=org_id, role_id=role.id, role_title=role.title[:300],
        committee_position_id=(committee["position_id"] if committee else None),
        incoming_member_id=incoming.id if incoming else None,
        incoming_name=(incoming_name or (incoming.full_name if incoming else None)),
        outgoing_member_id=outgoing.id if outgoing else None,
        outgoing_name=(outgoing_name or (outgoing.full_name if outgoing else None)),
        target_date=target_date, notes=notes, created_by_user_id=created_by,
        started_on=date.today(),
    )
    session.add(handover)
    await session.flush()
    await _seed_items(session, org_id, handover, role, committee)
    return handover


async def reseed_handover(session: AsyncSession, org_id, handover: RoleProgramHandover) -> int:
    """Pull in program elements added since the handover started, without
    touching any existing item's status/note. Returns how many were added."""
    if handover.role_id is None:
        return 0
    role = await _role_or_none(session, org_id, handover.role_id)
    if role is None:
        return 0
    committee = await _committee_context(session, org_id, role)
    existing = (await session.execute(
        select(RoleProgramHandoverItem.source_kind, RoleProgramHandoverItem.source_key)
        .where(RoleProgramHandoverItem.handover_id == handover.id,
               RoleProgramHandoverItem.source_key.isnot(None))
    )).all()
    skip = {(k, v) for k, v in existing}
    max_order = (await session.execute(
        select(func.coalesce(func.max(RoleProgramHandoverItem.sort_order), -1))
        .where(RoleProgramHandoverItem.handover_id == handover.id)
    )).scalar_one()
    return await _seed_items(session, org_id, handover, role, committee,
                             skip_keys=skip, start_order=int(max_order) + 1)


async def get_handover(session: AsyncSession, org_id, handover_id) -> Optional[dict]:
    h = await session.get(RoleProgramHandover, handover_id)
    if h is None or h.organisation_id != org_id:
        return None
    items = (await session.execute(
        select(RoleProgramHandoverItem).where(RoleProgramHandoverItem.handover_id == h.id)
        .order_by(RoleProgramHandoverItem.sort_order, RoleProgramHandoverItem.created_at)
    )).scalars().all()
    return _handover_dict(h, progress=_progress_of_items(items), items=items)


async def load_handover(session: AsyncSession, org_id, handover_id) -> Optional[RoleProgramHandover]:
    h = await session.get(RoleProgramHandover, handover_id)
    if h is None or h.organisation_id != org_id:
        return None
    return h


async def update_handover(session: AsyncSession, org_id, h: RoleProgramHandover, **fields) -> RoleProgramHandover:
    if fields.get("status") and fields["status"] not in ROLE_HANDOVER_STATUSES:
        raise ValueError("Invalid status")
    if "incoming_member_id" in fields:
        m = await _resolve_member(session, org_id, fields["incoming_member_id"])
        h.incoming_member_id = m.id if m else None
        if m and not fields.get("incoming_name"):
            h.incoming_name = m.full_name
    if "outgoing_member_id" in fields:
        m = await _resolve_member(session, org_id, fields["outgoing_member_id"])
        h.outgoing_member_id = m.id if m else None
        if m and not fields.get("outgoing_name"):
            h.outgoing_name = m.full_name
    for f in ("incoming_name", "outgoing_name", "target_date", "notes"):
        if f in fields:
            setattr(h, f, fields[f])
    if fields.get("status"):
        h.status = fields["status"]
        h.completed_at = _now() if fields["status"] == "completed" else None
    h.updated_at = _now()
    return h


async def add_item(session: AsyncSession, org_id, h: RoleProgramHandover, *,
                   label, detail=None, target_date=None, note=None) -> RoleProgramHandoverItem:
    """A custom checklist line — a piece of tribal knowledge the responsible
    person types in. No source_key, so a reseed never touches or duplicates it."""
    label = (label or "").strip()
    if not label:
        raise ValueError("A label is required")
    max_order = (await session.execute(
        select(func.coalesce(func.max(RoleProgramHandoverItem.sort_order), -1))
        .where(RoleProgramHandoverItem.handover_id == h.id)
    )).scalar_one()
    item = RoleProgramHandoverItem(
        organisation_id=org_id, handover_id=h.id, source_kind="custom", source_key=None,
        label=label[:400], detail=detail, target_date=target_date, note=note,
        sort_order=int(max_order) + 1,
    )
    session.add(item)
    await session.flush()
    return item


async def load_item(session: AsyncSession, org_id, handover_id, item_id) -> Optional[RoleProgramHandoverItem]:
    it = await session.get(RoleProgramHandoverItem, item_id)
    if it is None or it.organisation_id != org_id or str(it.handover_id) != str(handover_id):
        return None
    return it


async def update_item(session: AsyncSession, it: RoleProgramHandoverItem, *, updated_by=None, **fields) -> RoleProgramHandoverItem:
    if fields.get("status") and fields["status"] not in ROLE_HANDOVER_ITEM_STATUSES:
        raise ValueError("Invalid status")
    if fields.get("status"):
        it.status = fields["status"]
    if "label" in fields and (fields["label"] or "").strip():
        it.label = fields["label"].strip()[:400]
    for f in ("detail", "target_date", "note"):
        if f in fields:
            setattr(it, f, fields[f])
    it.updated_by_user_id = updated_by
    it.updated_at = _now()
    return it


async def delete_item(session: AsyncSession, it: RoleProgramHandoverItem) -> None:
    await session.delete(it)


async def delete_handover(session: AsyncSession, h: RoleProgramHandover) -> None:
    await session.delete(h)
