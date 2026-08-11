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


async def list_people(db: AsyncSession, org_id, include_archived: bool = False) -> list[dict]:
    """One row per person: every active fee_members row, unioned with the club's
    players that don't yet have a member row. Each person carries its computed
    segments (Player / Volunteer / Committee / Parent / External contact / Life
    member / Official), assigned roles, hours and a quals-to-renew count.

    Segments are derived from what the club has actually recorded, not just the
    member_category tag: Official = holds a role whose TYPE is Official
    (umpires, scorers…); Parent = recorded as a parent/guardian in any family
    (whether the family links them as a member or as a player); Life member =
    the fee_members flag OR a recorded Life Membership award. The category tag
    still counts towards each, so a hand-tagged person is never dropped.

    A person's KIND is three separate things, and all three are returned rather
    than flattened into one: `membership_type` (the club's own cross-season
    catalogue — Senior Player, Social Member, Sponsor Contact…, set in
    BetterFees or here), `category` (what this module tags a non-player as) and
    `player_status` ('active' | 'inactive' from Stats, NULL for a non-player).
    A club may use any, all or none of them, so the Directory reads whichever
    are populated instead of assuming one is authoritative.

    With include_archived, archived people are included too, each flagged
    `archived`."""
    # The join to `players` is org-scoped as well as keyed on the link. A member
    # row can point at a player owned by ANOTHER club (a shared fixture between
    # two synced clubs used to enrol the opposition here), and without the extra
    # condition this read-through would serve that club's photo, email and phone
    # inside our Directory.
    #
    # `our_player_id` is what the rest of this function uses, NOT `fm.player_id`:
    # a link that did not resolve belongs to another club, so that person is not
    # tagged Player and carries no link to someone else's profile.
    # `membership_types` is the club's cross-season catalogue (Senior Player,
    # Social Member, Sponsor Contact…) — a different axis from member_category
    # (what this module tags a non-player as) and from players.status (whether
    # they are currently playing). All three are carried per person so the
    # Directory can say which kind of member someone is, not just "Player".
    members = (await db.execute(text(f"""
        SELECT fm.id, fm.full_name, fm.email, fm.mobile, fm.player_id, fm.member_category,
               fm.is_life_member, fm.is_honorary, fm.honorary_expires_at, fm.archived_at,
               mt.id AS membership_type_id, mt.name AS membership_type_name, mt.is_playing AS membership_type_playing,
               p.id AS our_player_id, p.photo_url, p.email AS player_email, p.phone AS player_phone,
               p.status AS player_status
        FROM fee_members fm
        LEFT JOIN players p ON p.id = fm.player_id AND p.organisation_id = fm.organisation_id
        LEFT JOIN membership_types mt ON mt.id = fm.membership_type_id AND mt.organisation_id = fm.organisation_id
        WHERE fm.organisation_id = :org {'' if include_archived else 'AND fm.archived_at IS NULL'}
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

    # "Recorded as a parent" in any family: the guardian flag, or a relationship
    # that names them one. Family rows link a person EITHER as a member
    # (fee_member_id — what the Directory writes) OR as a player (player_id —
    # what the Families editor has always written for players), so both links
    # are read or a parent recorded against their player record never shows.
    _parentish = """(fmb.is_guardian = TRUE
          OR lower(coalesce(fmb.relationship, '')) LIKE '%parent%'
          OR lower(coalesce(fmb.relationship, '')) IN
              ('mother', 'father', 'mum', 'dad', 'mom', 'guardian', 'stepmother', 'stepfather'))"""
    guardians = {str(m) for m in (await db.execute(text(f"""
        SELECT DISTINCT fmb.fee_member_id
        FROM family_members fmb JOIN families f ON f.id = fmb.family_id
        WHERE f.organisation_id = :org AND fmb.fee_member_id IS NOT NULL
          AND {_parentish}
    """), {"org": org_id})).scalars().all()}
    guardian_players = {str(m) for m in (await db.execute(text(f"""
        SELECT DISTINCT fmb.player_id
        FROM family_members fmb JOIN families f ON f.id = fmb.family_id
        WHERE f.organisation_id = :org AND fmb.player_id IS NOT NULL
          AND {_parentish}
    """), {"org": org_id})).scalars().all()}

    # Holds a role whose TYPE is Official (umpire, scorer…). The type's own
    # category is the signal, with the type NAME as a fallback for a club that
    # made an "Official" type by hand without categorising it.
    officials = {str(m) for m in (await db.execute(text("""
        SELECT DISTINCT vr.member_id
        FROM volunteer_roles vr
        JOIN club_roles cr ON cr.id = vr.role_id AND cr.organisation_id = vr.organisation_id
        LEFT JOIN club_role_types t ON t.id = cr.role_type_id AND t.organisation_id = cr.organisation_id
        WHERE vr.organisation_id = :org
          AND (lower(coalesce(t.category, '')) = 'official' OR lower(coalesce(t.name, '')) = 'official')
    """), {"org": org_id})).scalars().all()}

    # Awarded Life Membership on the honour board. The players join is
    # org-scoped on both sides (the shared-game rule) so an award row can never
    # tag another club's player through a stray id.
    life_award_players = {str(m) for m in (await db.execute(text("""
        SELECT DISTINCT pa.player_id
        FROM player_achievements pa
        JOIN players p ON p.id = pa.player_id AND p.organisation_id = pa.org_id
        WHERE pa.org_id = :org AND pa.player_id IS NOT NULL
          AND (lower(pa.category) = 'life membership' OR lower(pa.achievement) LIKE 'life member%')
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
        our_pid = str(m["our_player_id"]) if m["our_player_id"] else None
        if our_pid:
            seen_players.add(our_pid)
        segs = []
        if our_pid:
            segs.append("Player")
        if mid in vol_profiles or roles_by.get(mid):
            segs.append("Volunteer")
        if mid in office_bearers:
            segs.append("Office Bearer")
        if mid in committee or cat == "committee":
            segs.append("Committee")
        if cat == "parent" or mid in guardians or (our_pid and our_pid in guardian_players):
            segs.append("Parent")
        if cat == "third_party":
            segs.append("External contact")
        if m["is_life_member"] or cat == "life_member" or (our_pid and our_pid in life_award_players):
            segs.append("Life member")
        if cat == "official" or mid in officials:
            segs.append("Official")
        if m["is_honorary"]:
            segs.append("Honorary")
        q = quals_by.get(mid, {})
        # NULL only when nobody's linked player — a linked player always carries
        # a status, so None here reads as "not a player" rather than "unknown".
        pstatus = (m["player_status"] or "active") if our_pid else None
        people.append({
            "key": mid, "member_id": mid, "player_id": our_pid,
            # Fall back to the linked player's Stats contact when the member row
            # has none, so a player's email/phone show through in ClubManager.
            "name": m["full_name"], "email": m["email"] or m["player_email"] or "",
            "phone": m["mobile"] or m["player_phone"] or "",
            "photo": m["photo_url"], "category": cat, "archived": m["archived_at"] is not None,
            "player_status": pstatus,
            "membership_type_id": str(m["membership_type_id"]) if m["membership_type_id"] else None,
            "membership_type": m["membership_type_name"],
            "membership_type_playing": m["membership_type_playing"],
            "is_life_member": bool(m["is_life_member"]),
            "is_honorary": bool(m["is_honorary"]),
            "honorary_expires_at": m["honorary_expires_at"].isoformat() if m["honorary_expires_at"] else None,
            "roles": roles_by.get(mid, []),
            "total_hours": hours_by.get(mid, 0.0),
            "quals_total": q.get("total", 0), "flagged": q.get("expiring", 0),
            "segs": segs,
        })

    # Players with no member row still appear (read-through from Stats/Core).
    extra = (await db.execute(text("""
        SELECT p.id, COALESCE(p.display_name_override, p.name) AS name, p.photo_url, p.email, p.phone, p.status
        FROM players p
        WHERE p.organisation_id = :org
          AND NOT EXISTS (SELECT 1 FROM fee_members fm WHERE fm.player_id = p.id AND fm.organisation_id = :org)
    """), {"org": org_id})).mappings().all()
    for p in extra:
        pid = str(p["id"])
        if pid in seen_players:
            continue
        # A player-linked family row or a Life Membership award belongs to the
        # person, member row or not — a read-through player carries those
        # segments the same way a member does.
        psegs = ["Player"]
        if pid in guardian_players:
            psegs.append("Parent")
        if pid in life_award_players:
            psegs.append("Life member")
        people.append({
            "key": "player:" + pid, "member_id": None, "player_id": pid,
            "name": p["name"], "email": p["email"] or "", "phone": p["phone"] or "", "photo": p["photo_url"], "category": None, "archived": False,
            "player_status": p["status"] or "active",
            "membership_type_id": None, "membership_type": None, "membership_type_playing": None,
            "is_life_member": False, "is_honorary": False, "honorary_expires_at": None,
            "roles": [], "total_hours": 0.0, "quals_total": 0, "flagged": 0, "segs": psegs,
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
