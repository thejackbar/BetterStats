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

THREE AXES, kept apart on purpose (migration 235). They were one single-valued
`member_category` whose vocabulary mixed all three, so a person could only ever
be one thing and "Volunteer" competed with "Parent" for the same slot:

  1. MEMBERSHIP TYPE — what kind of member. The club's own `membership_types`
     catalogue, held MULTI-valued through `member_membership_types` (a dad who
     plays and whose kid plays is a Senior Player AND a Parent), and scoped
     internal vs external. `fee_members.membership_type_id` remains the PRIMARY
     one, because BetterFees bills a single tier.
  2. ROLES — what they DO. Volunteer / Committee / Official, through
     volunteer_roles + committee_terms, already several at once. An Official is
     the case that proves these are independent: a panel umpire may hold the
     role and no membership at all.
  3. HONOURS — Life Membership, bestowed on a member of any type. On the person
     spine (`is_life_member` + `life_member_since`), corroborated by a Life
     Membership award on the honour board.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Person-spine CRUD lives in services/members.py (shared with BetterFees). This
# module keeps only the Directory-specific reads/writes (the people list with
# segments, and role assignment).
from app.services.members import MEMBER_CATEGORIES  # noqa: F401  (re-exported for the router)

# A membership type contributes a segment prefixed `type:`, so the club naming a
# type "Volunteer" (every club that adopted the pre-235 starter set has one) can
# never collide with the Volunteer ROLE segment. Roles and honours stay bare.
TYPE_SEG_PREFIX = "type:"
SEG_EXTERNAL = "External"
SEG_PLAYER = "Player"
SEG_LIFE_MEMBER = "Life member"


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
               fm.is_life_member, fm.life_member_since, fm.is_honorary, fm.honorary_expires_at, fm.archived_at,
               mt.id AS membership_type_id, mt.name AS membership_type_name, mt.is_playing AS membership_type_playing,
               p.id AS our_player_id, p.photo_url, p.email AS player_email, p.phone AS player_phone,
               p.status AS player_status
        FROM fee_members fm
        LEFT JOIN players p ON p.id = fm.player_id AND p.organisation_id = fm.organisation_id
        LEFT JOIN membership_types mt ON mt.id = fm.membership_type_id AND mt.organisation_id = fm.organisation_id
        WHERE fm.organisation_id = :org {'' if include_archived else 'AND fm.archived_at IS NULL'}
    """), {"org": org_id})).mappings().all()

    # Every membership type a person holds (migration 235), not just the primary
    # one on fee_members. The catalogue join is org-scoped on both sides, same
    # rule as the players join above: a stray row must not pull another club's
    # type name into this club's Directory.
    types_by = {}
    for r in (await db.execute(text("""
        SELECT mmt.member_id, t.id, t.name, t.scope, t.is_playing
        FROM member_membership_types mmt
        JOIN membership_types t ON t.id = mmt.membership_type_id AND t.organisation_id = mmt.organisation_id
        WHERE mmt.organisation_id = :org
        ORDER BY t.sort_order, lower(t.name)
    """), {"org": org_id})).mappings().all():
        types_by.setdefault(str(r["member_id"]), []).append({
            "id": str(r["id"]), "name": r["name"],
            "scope": r["scope"] or "internal", "is_playing": bool(r["is_playing"]),
        })

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

    # Holds a role that is actually VOLUNTEERING. Not every role is: an Official
    # is a distinct role of its own (and a panel umpire may be nobody's member,
    # let alone a volunteer), a committee role is a seat, and a `paid` role is
    # employment — calling the club's paid bar manager a volunteer would put
    # their hours in a grant application. Same PAID_CATEGORY rule the roster
    # already applies.
    volunteer_roles = {str(m) for m in (await db.execute(text("""
        SELECT DISTINCT vr.member_id
        FROM volunteer_roles vr
        JOIN club_roles cr ON cr.id = vr.role_id AND cr.organisation_id = vr.organisation_id
        LEFT JOIN club_role_types t ON t.id = cr.role_type_id AND t.organisation_id = cr.organisation_id
        WHERE vr.organisation_id = :org
          AND lower(coalesce(t.category, '')) NOT IN ('official', 'committee', 'paid')
          AND lower(coalesce(t.name, '')) <> 'official'
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
        # ── AXIS 1: membership type. Several at once, and scoped.
        my_types = types_by.get(mid, [])
        segs = [TYPE_SEG_PREFIX + t["name"] for t in my_types]
        # Holding ONLY external types means the club records this person but has
        # not gained them as a member. Emitted as its own segment so a
        # membership count never has to re-derive the rule.
        if my_types and all(t["scope"] == "external" for t in my_types):
            segs.append(SEG_EXTERNAL)
        # Playing is a STATS fact, not a club classification: the record says
        # they play, not whether the club calls them a Senior or a Junior
        # Player. Deriving it keeps the Players filter working for a club that
        # has adopted no catalogue at all.
        if our_pid:
            segs.append(SEG_PLAYER)

        # ── AXIS 2: roles — what they DO, independent of membership. An
        # Official is the case that proves the axes are separate: a panel umpire
        # may hold the role and no membership whatsoever. member_category is
        # read as a fallback for anyone tagged before 235 split the axes, so no
        # club loses a filter on upgrade.
        if mid in vol_profiles or mid in volunteer_roles:
            segs.append("Volunteer")
        if mid in office_bearers:
            segs.append("Office Bearer")
        if mid in committee or cat == "committee":
            segs.append("Committee")
        if cat == "official" or mid in officials:
            segs.append("Official")

        # ── AXIS 3: honours. Bestowed on a member of any type, so neither a
        # type nor a role. The flag is the club's own record and the honour
        # board award corroborates it; either alone is enough, since a
        # stats-first club will have the award and no flag.
        life_award = bool(our_pid and our_pid in life_award_players)
        is_life = bool(m["is_life_member"]) or life_award or cat == "life_member"
        if is_life:
            segs.append(SEG_LIFE_MEMBER)
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
            # The PRIMARY type (what BetterFees bills) stays exactly where it
            # was, so every existing reader is untouched. `membership_types` is
            # the full set this person holds.
            "membership_type_id": str(m["membership_type_id"]) if m["membership_type_id"] else None,
            "membership_type": m["membership_type_name"],
            "membership_type_playing": m["membership_type_playing"],
            "membership_types": my_types,
            "is_external": bool(my_types) and all(t["scope"] == "external" for t in my_types),
            # Honours.
            "is_life_member": is_life,
            # Whether the flag itself is set, as opposed to life membership
            # being inferred from the honour board. The toggle reads this, or it
            # would show itself as already on for an awarded player and do
            # nothing visible when switched off.
            "life_member_flag": bool(m["is_life_member"]),
            "life_member_award": life_award,
            "life_member_since": m["life_member_since"].isoformat() if m["life_member_since"] else None,
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
        # A Life Membership award belongs to the person whether or not anyone
        # has made them a member row, so a read-through player carries it the
        # same way a member does. They hold no membership TYPES, since a type is
        # recorded against the person spine and they have no row on it yet —
        # ticking one mints the row (see set_member_types).
        psegs = [SEG_PLAYER]
        life_award = pid in life_award_players
        if life_award:
            psegs.append(SEG_LIFE_MEMBER)
        people.append({
            "key": "player:" + pid, "member_id": None, "player_id": pid,
            "name": p["name"], "email": p["email"] or "", "phone": p["phone"] or "", "photo": p["photo_url"], "category": None, "archived": False,
            "player_status": p["status"] or "active",
            "membership_type_id": None, "membership_type": None, "membership_type_playing": None,
            "membership_types": [], "is_external": False,
            "is_life_member": life_award, "life_member_flag": False,
            "life_member_award": life_award, "life_member_since": None,
            "is_honorary": False, "honorary_expires_at": None,
            "roles": [], "total_hours": 0.0, "quals_total": 0, "flagged": 0, "segs": psegs,
        })

    people.sort(key=lambda x: (x["name"] or "").lower())
    return people


async def set_member_types(db: AsyncSession, org_id, member_id, type_ids, primary_id="__keep__") -> dict:
    """Replace the membership types a person holds.

    A full replace, not add/remove calls: the screen shows one set of tick boxes
    and sends the whole set, so a type left out is one that was unticked. Two
    requests could half-succeed and leave someone holding a type nobody chose.

    Every id must be one of THIS club's own types — they arrive from a browser,
    and a foreign id would put another club's classification on our person.

    `primary_id` is the one BetterFees bills. Left alone unless passed; if the
    type it names is dropped from the set, it falls back to the first remaining
    type rather than pointing at one the person no longer holds.
    """
    member = (await db.execute(text(
        "SELECT 1 FROM fee_members WHERE id = :mid AND organisation_id = :org"
    ), {"mid": member_id, "org": org_id})).scalar()
    if not member:
        raise ValueError("Member not found")

    wanted = []
    for raw in (type_ids or []):
        try:
            tid = uuid.UUID(str(raw))
        except (ValueError, AttributeError, TypeError):
            raise ValueError("Membership type not found")
        if tid not in wanted:
            wanted.append(tid)
    if wanted:
        ours = {r for r in (await db.execute(text(
            "SELECT id FROM membership_types WHERE organisation_id = :org AND id = ANY(:ids)"
        ), {"org": org_id, "ids": wanted})).scalars().all()}
        missing = [t for t in wanted if t not in ours]
        if missing:
            raise ValueError("Membership type not found")

    await db.execute(text(
        "DELETE FROM member_membership_types WHERE organisation_id = :org AND member_id = :mid"
        " AND NOT (membership_type_id = ANY(:keep))"
    ), {"org": org_id, "mid": member_id, "keep": wanted})
    for tid in wanted:
        await db.execute(text("""
            INSERT INTO member_membership_types (id, organisation_id, member_id, membership_type_id)
            VALUES (gen_random_uuid(), :org, :mid, :tid)
            ON CONFLICT (member_id, membership_type_id) DO NOTHING
        """), {"org": org_id, "mid": member_id, "tid": tid})

    current_primary = (await db.execute(text(
        "SELECT membership_type_id FROM fee_members WHERE id = :mid"
    ), {"mid": member_id})).scalar()
    if primary_id == "__keep__":
        new_primary = current_primary
    elif primary_id in (None, ""):
        new_primary = None
    else:
        try:
            new_primary = uuid.UUID(str(primary_id))
        except (ValueError, AttributeError, TypeError):
            raise ValueError("Membership type not found")
    # The primary must be one they actually hold. Falling back to the first
    # remaining type keeps BetterFees pointing at something real rather than
    # leaving a billing tier attached to a type that was just removed.
    if new_primary is not None and new_primary not in wanted:
        new_primary = wanted[0] if wanted else None
    if new_primary is None and wanted:
        new_primary = wanted[0]
    if new_primary != current_primary:
        await db.execute(text(
            "UPDATE fee_members SET membership_type_id = :tid, updated_at = NOW()"
            " WHERE id = :mid AND organisation_id = :org"
        ), {"tid": new_primary, "mid": member_id, "org": org_id})
    return {"type_ids": [str(t) for t in wanted], "primary_id": str(new_primary) if new_primary else None}


def _as_date(v):
    """"" / None clears; an ISO date is parsed; anything else is rejected."""
    if v in (None, ""):
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise ValueError("Invalid date")


async def set_life_membership(db: AsyncSession, org_id, member_id, is_life_member, since="__keep__") -> None:
    """Record (or clear) the life-membership honour on the person spine.

    Deliberately NOT written to `player_achievements`: that table keys on
    player_id, so a life member who never played could not be held there at all.
    The honour board stays the ceremonial record and the Directory reads both,
    which is why clearing this flag does not remove an award someone was
    genuinely given — the award still shows them as a life member, and it is
    removed on the Awards screen that owns it."""
    sets = ["is_life_member = :flag"]
    params = {"flag": bool(is_life_member), "mid": member_id, "org": org_id}
    if since != "__keep__":
        # Parsed here rather than handed to the driver as a string: the value
        # arrives from a browser as JSON text and asyncpg will not coerce it
        # into a DATE, so a raw string fails at execute time with a driver
        # error instead of a readable one.
        sets.append("life_member_since = :since")
        params["since"] = _as_date(since)
    # Clearing the honour clears its date too — a date for something that did
    # not happen is worse than no date.
    elif not is_life_member:
        sets.append("life_member_since = NULL")
    await db.execute(text(
        f"UPDATE fee_members SET {', '.join(sets)}, updated_at = NOW()"
        " WHERE id = :mid AND organisation_id = :org"
    ), params)


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
