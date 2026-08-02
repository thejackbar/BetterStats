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
               fm.is_life_member, p.photo_url
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
            "name": m["full_name"], "email": m["email"] or "", "phone": m["mobile"] or "",
            "photo": m["photo_url"], "category": cat,
            "roles": roles_by.get(mid, []),
            "total_hours": hours_by.get(mid, 0.0),
            "quals_total": q.get("total", 0), "flagged": q.get("expiring", 0),
            "segs": segs,
        })

    # Players with no member row still appear (read-through from Stats/Core).
    extra = (await db.execute(text("""
        SELECT p.id, COALESCE(p.display_name_override, p.name) AS name, p.photo_url
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
            "name": p["name"], "email": "", "phone": "", "photo": p["photo_url"], "category": None,
            "roles": [], "total_hours": 0.0, "quals_total": 0, "flagged": 0, "segs": ["Player"],
        })

    people.sort(key=lambda x: (x["name"] or "").lower())
    return people


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
