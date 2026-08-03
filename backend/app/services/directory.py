"""BetterClubManager Directory — the club's people, on the shared fee_members
spine.

Players belong to Stats/Core (synced from Grassroots/PlayHQ, or added/imported
in Stats). ClubManager owns the NON-player side: it can add/import non-playing
members and third parties (a fee_members row with player_id NULL, tagged with a
member_category) and assign them roles. A player appears here read-through and
gets a member row lazily the first time ClubManager assigns them anything, so
"one record per person" holds without ClubManager ever creating players.

Raw SQL throughout (same posture as services/roster.py) so this stays out of the
ORM/Alembic graph; it only ever writes fee_members / volunteer_roles.
"""
from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Person-spine CRUD lives in services/members.py (shared with BetterFees). This
# module keeps only the Directory-specific reads/writes (the people list with
# segments, and role assignment).
from app.services.members import MEMBER_CATEGORIES  # noqa: F401  (re-exported for the router)


async def list_people(db: AsyncSession, org_id) -> list[dict]:
    """One row per person: every active fee_members row, unioned with the club's
    players that don't yet have a member row. Each person carries its computed
    segments (Player / Volunteer / Committee / Parent / Third party / Life
    member), assigned roles, hours and a quals-to-renew count."""
    members = (await db.execute(text("""
        SELECT fm.id, fm.full_name, fm.email, fm.mobile, fm.player_id, fm.member_category,
               fm.is_life_member, p.photo_url, p.email AS player_email, p.phone AS player_phone
        FROM fee_members fm
        LEFT JOIN players p ON p.id = fm.player_id
        WHERE fm.organisation_id = :org AND fm.archived_at IS NULL
    """), {"org": org_id})).mappings().all()

    roles_rows = (await db.execute(text("""
        SELECT vr.member_id, cr.id AS role_id, cr.title
        FROM volunteer_roles vr JOIN club_roles cr ON cr.id = vr.role_id
        WHERE vr.organisation_id = :org
        ORDER BY lower(cr.title)
    """), {"org": org_id})).mappings().all()
    roles_by = {}
    for r in roles_rows:
        roles_by.setdefault(str(r["member_id"]), []).append({"id": str(r["role_id"]), "title": r["title"]})

    vol_profiles = {str(m) for m in (await db.execute(text(
        "SELECT member_id FROM volunteer_profiles WHERE organisation_id = :org"
    ), {"org": org_id})).scalars().all()}

    committee = {str(m) for m in (await db.execute(text("""
        SELECT DISTINCT member_id FROM committee_terms
        WHERE organisation_id = :org AND member_id IS NOT NULL AND ended_at IS NULL
    """), {"org": org_id})).scalars().all()}
    office_bearers = {str(m) for m in (await db.execute(text("""
        SELECT DISTINCT ct.member_id FROM committee_terms ct JOIN committee_positions cp ON cp.id = ct.position_id
        WHERE ct.organisation_id = :org AND ct.member_id IS NOT NULL AND ct.ended_at IS NULL AND cp.is_office_bearer = TRUE
    """), {"org": org_id})).scalars().all()}

    guardians = {str(m) for m in (await db.execute(text("""
        SELECT DISTINCT fmb.fee_member_id
        FROM family_members fmb JOIN families f ON f.id = fmb.family_id
        WHERE f.organisation_id = :org AND fmb.fee_member_id IS NOT NULL
          AND (fmb.is_guardian = TRUE OR lower(coalesce(fmb.relationship, '')) LIKE '%parent%')
    """), {"org": org_id})).scalars().all()}

    hours_by = {str(k): float(v or 0) for k, v in (await db.execute(text(
        "SELECT member_id, COALESCE(SUM(hours), 0) FROM volunteer_hours WHERE organisation_id = :org GROUP BY member_id"
    ), {"org": org_id})).all()}

    quals_by = {}
    for r in (await db.execute(text("""
        SELECT member_id,
               COUNT(*) AS total,
               COUNT(*) FILTER (WHERE expires_at IS NOT NULL AND expires_at <= CURRENT_DATE + INTERVAL '60 days') AS expiring
        FROM member_qualifications WHERE organisation_id = :org GROUP BY member_id
    """), {"org": org_id})).mappings().all():
        quals_by[str(r["member_id"])] = {"total": r["total"], "expiring": r["expiring"]}

    people = []
    seen_players = set()
    for m in members:
        mid = str(m["id"])
        cat = m["member_category"]
        if m["player_id"]:
            seen_players.add(str(m["player_id"]))
        segs = []
        if m["player_id"]:
            segs.append("Player")
        if mid in vol_profiles or roles_by.get(mid):
            segs.append("Volunteer")
        if mid in office_bearers:
            segs.append("Office Bearer")
        if mid in committee or cat == "committee":
            segs.append("Committee")
        if cat == "parent" or mid in guardians:
            segs.append("Parent")
        if cat == "third_party":
            segs.append("Third party")
        if m["is_life_member"] or cat == "life_member":
            segs.append("Life member")
        if cat == "official":
            segs.append("Official")
        q = quals_by.get(mid, {})
        people.append({
            "key": mid, "member_id": mid, "player_id": str(m["player_id"]) if m["player_id"] else None,
            # Fall back to the linked player's Stats contact when the member row
            # has none, so a player's email/phone show through in ClubManager.
            "name": m["full_name"], "email": m["email"] or m["player_email"] or "",
            "phone": m["mobile"] or m["player_phone"] or "",
            "photo": m["photo_url"], "category": cat,
            "roles": roles_by.get(mid, []),
            "total_hours": hours_by.get(mid, 0.0),
            "quals_total": q.get("total", 0), "flagged": q.get("expiring", 0),
            "segs": segs,
        })

    # Players with no member row still appear (read-through from Stats/Core).
    extra = (await db.execute(text("""
        SELECT p.id, COALESCE(p.display_name_override, p.name) AS name, p.photo_url, p.email, p.phone
        FROM players p
        WHERE p.organisation_id = :org
          AND NOT EXISTS (SELECT 1 FROM fee_members fm WHERE fm.player_id = p.id AND fm.organisation_id = :org)
    """), {"org": org_id})).mappings().all()
    for p in extra:
        pid = str(p["id"])
        if pid in seen_players:
            continue
        people.append({
            "key": "player:" + pid, "member_id": None, "player_id": pid,
            "name": p["name"], "email": p["email"] or "", "phone": p["phone"] or "", "photo": p["photo_url"], "category": None,
            "roles": [], "total_hours": 0.0, "quals_total": 0, "flagged": 0, "segs": ["Player"],
        })

    people.sort(key=lambda x: (x["name"] or "").lower())
    return people


async def member_overlays(db: AsyncSession, org_id, member_id) -> dict:
    """A member's current committee positions and family links, for the detail
    pane. (Roles/quals/hours are fetched separately.)"""
    committee = (await db.execute(text("""
        SELECT ct.id AS term_id, cp.id AS position_id, cp.name, cp.is_office_bearer
        FROM committee_terms ct JOIN committee_positions cp ON cp.id = ct.position_id
        WHERE ct.organisation_id = :org AND ct.member_id = :mid AND ct.ended_at IS NULL
        ORDER BY cp.is_office_bearer DESC, cp.sort_order, lower(cp.name)
    """), {"org": org_id, "mid": member_id})).mappings().all()
    families = (await db.execute(text("""
        SELECT f.id AS family_id, f.name, fm.relationship, fm.is_guardian
        FROM family_members fm JOIN families f ON f.id = fm.family_id
        WHERE f.organisation_id = :org AND fm.fee_member_id = :mid
        ORDER BY lower(f.name)
    """), {"org": org_id, "mid": member_id})).mappings().all()
    # This week's roster shifts assigned to the member (roster weeks anchor on
    # Monday, matching date_trunc('week', …)).
    shifts_this_week = (await db.execute(text("""
        SELECT COUNT(*) FROM roster_shifts rs JOIN roster_weeks rw ON rw.id = rs.roster_week_id
        WHERE rs.organisation_id = :org AND rs.assignee_member_id = :mid
          AND rw.week_start = date_trunc('week', CURRENT_DATE)::date
    """), {"org": org_id, "mid": member_id})).scalar() or 0
    # Open club-diary tasks the member owns directly or through a role they hold.
    diary_open = (await db.execute(text("""
        SELECT COUNT(*) FROM club_diary_task_occurrences o
        WHERE o.organisation_id = :org AND o.completed_at IS NULL
          AND o.status NOT IN ('completed', 'done', 'cancelled')
          AND (o.assigned_to_member_id = :mid
               OR o.assigned_to_role_id IN (SELECT role_id FROM volunteer_roles WHERE organisation_id = :org AND member_id = :mid))
    """), {"org": org_id, "mid": member_id})).scalar() or 0
    return {
        "committee": [{"term_id": str(c["term_id"]), "position_id": str(c["position_id"]), "name": c["name"], "is_office_bearer": c["is_office_bearer"]} for c in committee],
        "families": [{"family_id": str(x["family_id"]), "name": x["name"], "relationship": x["relationship"], "is_guardian": x["is_guardian"]} for x in families],
        "shifts_this_week": int(shifts_this_week),
        "diary_open": int(diary_open),
    }


async def list_positions(db: AsyncSession, org_id) -> list[dict]:
    rows = (await db.execute(text(
        "SELECT id, name, is_office_bearer FROM committee_positions WHERE organisation_id = :org AND is_active = TRUE ORDER BY is_office_bearer DESC, sort_order, lower(name)"
    ), {"org": org_id})).mappings().all()
    return [{"id": str(r["id"]), "name": r["name"], "is_office_bearer": r["is_office_bearer"]} for r in rows]


async def list_families(db: AsyncSession, org_id) -> list[dict]:
    rows = (await db.execute(text(
        "SELECT id, name FROM families WHERE organisation_id = :org ORDER BY lower(name)"
    ), {"org": org_id})).mappings().all()
    return [{"id": str(r["id"]), "name": r["name"]} for r in rows]


async def assign_committee(db: AsyncSession, org_id, member_id, position_id) -> None:
    name = (await db.execute(text(
        "SELECT full_name FROM fee_members WHERE id = :mid AND organisation_id = :org"
    ), {"mid": member_id, "org": org_id})).scalar()
    if not name:
        raise ValueError("Member not found")
    pos = (await db.execute(text(
        "SELECT 1 FROM committee_positions WHERE id = :pid AND organisation_id = :org"
    ), {"pid": position_id, "org": org_id})).scalar()
    if not pos:
        raise ValueError("Position not found")
    dup = (await db.execute(text(
        "SELECT 1 FROM committee_terms WHERE organisation_id = :org AND position_id = :pid AND member_id = :mid AND ended_at IS NULL"
    ), {"org": org_id, "pid": position_id, "mid": member_id})).scalar()
    if dup:
        return
    await db.execute(text("""
        INSERT INTO committee_terms (id, organisation_id, position_id, member_id, holder_name, started_at)
        VALUES (gen_random_uuid(), :org, :pid, :mid, :name, CURRENT_DATE)
    """), {"org": org_id, "pid": position_id, "mid": member_id, "name": name[:200]})


async def remove_committee(db: AsyncSession, org_id, term_id) -> None:
    await db.execute(text(
        "UPDATE committee_terms SET ended_at = CURRENT_DATE WHERE id = :tid AND organisation_id = :org AND ended_at IS NULL"
    ), {"tid": term_id, "org": org_id})


async def create_family(db: AsyncSession, org_id, name) -> str:
    name = (name or "").strip()
    if not name:
        raise ValueError("Name is required")
    await db.execute(text(
        "INSERT INTO families (id, organisation_id, name) VALUES (gen_random_uuid(), :org, :name) ON CONFLICT (organisation_id, name) DO NOTHING"
    ), {"org": org_id, "name": name[:200]})
    row = (await db.execute(text(
        "SELECT id FROM families WHERE organisation_id = :org AND name = :name"
    ), {"org": org_id, "name": name[:200]})).scalar()
    return str(row)


async def add_to_family(db: AsyncSession, org_id, member_id, family_id, relationship=None, is_guardian=False) -> None:
    fam = (await db.execute(text(
        "SELECT 1 FROM families WHERE id = :fid AND organisation_id = :org"
    ), {"fid": family_id, "org": org_id})).scalar()
    if not fam:
        raise ValueError("Family not found")
    dup = (await db.execute(text(
        "SELECT 1 FROM family_members WHERE family_id = :fid AND fee_member_id = :mid"
    ), {"fid": family_id, "mid": member_id})).scalar()
    if dup:
        return
    await db.execute(text("""
        INSERT INTO family_members (id, family_id, fee_member_id, is_guardian, relationship)
        VALUES (gen_random_uuid(), :fid, :mid, :guard, :rel)
    """), {"fid": family_id, "mid": member_id, "guard": bool(is_guardian), "rel": (relationship or None)})


async def remove_from_family(db: AsyncSession, org_id, member_id, family_id) -> None:
    await db.execute(text("""
        DELETE FROM family_members
        WHERE family_id = :fid AND fee_member_id = :mid
          AND EXISTS (SELECT 1 FROM families f WHERE f.id = :fid AND f.organisation_id = :org)
    """), {"fid": family_id, "mid": member_id, "org": org_id})


async def add_role(db: AsyncSession, org_id, member_id, role_id) -> None:
    role = (await db.execute(text(
        "SELECT 1 FROM club_roles WHERE id = :rid AND organisation_id = :org"
    ), {"rid": role_id, "org": org_id})).scalar()
    if not role:
        raise ValueError("Role not found")
    member = (await db.execute(text(
        "SELECT 1 FROM fee_members WHERE id = :mid AND organisation_id = :org"
    ), {"mid": member_id, "org": org_id})).scalar()
    if not member:
        raise ValueError("Member not found")
    await db.execute(text("""
        INSERT INTO volunteer_roles (id, organisation_id, member_id, role_id)
        VALUES (:id, :org, :mid, :rid)
        ON CONFLICT (member_id, role_id) DO NOTHING
    """), {"id": uuid.uuid4(), "org": org_id, "mid": member_id, "rid": role_id})


async def remove_role(db: AsyncSession, org_id, member_id, role_id) -> None:
    await db.execute(text(
        "DELETE FROM volunteer_roles WHERE organisation_id = :org AND member_id = :mid AND role_id = :rid"
    ), {"org": org_id, "mid": member_id, "rid": role_id})
