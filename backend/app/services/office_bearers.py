"""One catalogue behind two modules: BetterStats Awards of category "Office
Bearer" and BetterClubhouse's roles.

BetterStats is the core module and may be all a club ever buys. A club using
only BetterStats still records who its President was in 2019, as an achievement
with a category, a subcategory and an achievement name — three free-text
columns that describe exactly what BetterClubhouse stores properly as a role
type and a role.

Left alone, those become two parallel vocabularies, and the club that later
trials BetterClubhouse finds an empty Roles screen and a decade of office
bearers stranded in the awards table. So the awards catalogue is kept in step
with ``club_roles`` / ``club_role_types`` from the outset:

  award category     "Office Bearer"  (fixed)
  award subcategory  a club_role_type ("Executive Committee" -> Office Bearer)
  award achievement  a club_role      ("President")

The sync runs both ways and is idempotent. Definitions the club already has are
ADOPTED into the role catalogue rather than overwritten, so nothing a club typed
before this existed is lost; roles are PUBLISHED back so the awards dropdown
offers what the club actually holds. A club with no roles at all gets the
committee starter set, so the dropdown is never empty.

Nothing here needs the club to hold BetterClubhouse. That is the point — the
rows are written the Clubhouse way whether or not the module is ever paid for.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import ClubRole, ClubRoleType
from app.services.roles_activities import _get_or_create_type, seed_starter_roles

AWARD_CATEGORY = "Office Bearer"

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)

# An award subcategory names a role type. Both spellings a club might already
# have are accepted, since these strings were free text for years.
SUBCATEGORY_TO_ROLE_TYPE = {
    "executive committee": "Office Bearer",
    "executive": "Office Bearer",
    "office bearer": "Office Bearer",
    "office bearers": "Office Bearer",
    "committee": "Committee Member",
    "general committee": "Committee Member",
    "committee member": "Committee Member",
    "captains": "Captain",
    "captain": "Captain",
    "coaches": "Coach",
    "coach": "Coach",
    "other roles": "Other",
    "other": "Other",
}

# Going the other way there is one answer per role type — the label the awards
# screen has always shown. A type with no entry here (a club's own invention,
# "Life Member" say) uses its own name, which reads fine as a subcategory.
ROLE_TYPE_TO_SUBCATEGORY = {
    "office bearer": "Executive Committee",
    "committee member": "General Committee",
    "captain": "Captains",
    "coach": "Coaches",
    "other": "Other Roles",
}

# Role types whose roles belong in the awards dropdown. Committee roles always
# qualify; captains and coaches are the two non-committee kinds a club hands out
# as an honour. Ground staff, canteen and match officials deliberately do not —
# sweeping every volunteer role into the awards catalogue would bury the
# positions that matter under a list of everyone who ever ran a barbecue.
PUBLISHED_ROLE_TYPES = {"office bearer", "committee member", "captain", "coach"}

# Roles created from an award of these types are committee positions, so they
# also appear on the Committee screen. A 1st XI captain is not.
COMMITTEE_ROLE_TYPES = {"office bearer", "committee member"}


def role_type_for_subcategory(subcategory: Optional[str]) -> str:
    key = (subcategory or "").strip().lower()
    return SUBCATEGORY_TO_ROLE_TYPE.get(key) or (subcategory or "").strip() or "Other"


def subcategory_for_role_type(role_type_name: Optional[str]) -> str:
    key = (role_type_name or "").strip().lower()
    return ROLE_TYPE_TO_SUBCATEGORY.get(key) or (role_type_name or "").strip() or "Other Roles"


async def ensure_role_for_award(
    session: AsyncSession, org_id, subcategory: Optional[str], achievement: str,
) -> Optional[ClubRole]:
    """Find, or create, the club_roles row an Office Bearer award names.

    Matching is on the role title alone, case-insensitively, because
    ``club_roles`` is unique per (organisation, title) — a club cannot hold two
    roles called "President" under different types. So an award recorded under a
    subcategory that disagrees with the existing role's type reuses the role and
    leaves its type alone: the Roles screen is where a type is decided, and a
    stray award should not silently retype a position the committee set up.
    """
    title = (achievement or "").strip()
    if not title:
        return None
    existing = (await session.execute(
        select(ClubRole).where(
            ClubRole.organisation_id == org_id,
            func.lower(ClubRole.title) == title.lower(),
        )
    )).scalars().first()
    if existing is not None:
        return existing

    type_name = role_type_for_subcategory(subcategory)
    rtype = await _get_or_create_type(session, ClubRoleType, org_id, type_name)
    role = ClubRole(
        organisation_id=org_id, title=title[:120],
        role_type_id=rtype.id if rtype else None,
        is_committee=type_name.strip().lower() in COMMITTEE_ROLE_TYPES,
        sort_order=0,
    )
    session.add(role)
    await session.flush()
    return role


async def _award_space_roles(session: AsyncSession, org_id) -> list[tuple[ClubRole, Optional[str]]]:
    rows = (await session.execute(
        select(ClubRole, ClubRoleType.name)
        .outerjoin(ClubRoleType, ClubRoleType.id == ClubRole.role_type_id)
        .where(ClubRole.organisation_id == org_id, ClubRole.is_active.is_(True))
    )).all()
    return [
        (r, t) for r, t in rows
        if r.is_committee or (t or "").strip().lower() in PUBLISHED_ROLE_TYPES
    ]


async def sync_award_definitions(session: AsyncSession, org_id, *, seed_if_empty: bool = True) -> dict:
    """Reconcile the Office Bearer award definitions with the role catalogue.

    Two directions, both additive:

    · ADOPT — every Office Bearer definition the club already has, AND every
      Office Bearer award it has actually recorded, becomes a club_role if it is
      not one already. Both sources matter: the definitions are the dropdown, but
      a club's real vocabulary is what it has written down, and the two drift
      (an award imported from a spreadsheet never had a definition behind it).
      This is what makes the transition to BetterClubhouse a no-op — by the time
      they subscribe, the roles are already there.
    · PUBLISH — every committee/captain/coach role becomes an Office Bearer
      definition if it is not one already, so the awards dropdown offers what
      the club actually holds.

    Neither direction deletes or rewrites. A definition whose role was archived
    keeps working — a club still wants to record that someone was Grounds
    Officer in 2011 after the position is retired.
    """
    adopted = published = 0

    # Seeding is gated on having no ROLES, not no definitions. A club can easily
    # have one hand-typed definition and an empty role catalogue, and gating on
    # definitions left exactly that club with nothing.
    if seed_if_empty:
        has_role = (await session.execute(
            select(func.count()).select_from(ClubRole).where(ClubRole.organisation_id == org_id)
        )).scalar() or 0
        if not has_role:
            await seed_starter_roles(session, org_id, committee=True)

    defs = (await session.execute(text("""
        SELECT id, subcategory, achievement
        FROM org_award_definitions
        WHERE org_id = :org AND category = :cat AND active = TRUE
          AND achievement IS NOT NULL AND achievement <> ''
    """), {"org": str(org_id), "cat": AWARD_CATEGORY})).mappings().all()

    for row in defs:
        role = await ensure_role_for_award(session, org_id, row["subcategory"], row["achievement"])
        if role is not None:
            adopted += 1

    # The awards themselves, which is where a club's real history lives.
    adopted += await backfill_achievement_roles(session, org_id)

    existing_pairs = {
        ((r["subcategory"] or "").strip().lower(), (r["achievement"] or "").strip().lower())
        for r in defs
    }
    for role, type_name in await _award_space_roles(session, org_id):
        subcat = subcategory_for_role_type(type_name)
        if (subcat.lower(), role.title.strip().lower()) in existing_pairs:
            continue
        await session.execute(text("""
            INSERT INTO org_award_definitions
                (id, org_id, category, subcategory, achievement, sort_order, active)
            VALUES (gen_random_uuid(), :org, :cat, :sub, :ach, :sort, TRUE)
            ON CONFLICT DO NOTHING
        """), {"org": str(org_id), "cat": AWARD_CATEGORY, "sub": subcat,
               "ach": role.title, "sort": role.sort_order or 0})
        published += 1

    return {"adopted": adopted, "published": published}


async def link_achievement_role(
    session: AsyncSession, org_id, achievement_id, subcategory: Optional[str], achievement: str,
) -> Optional[str]:
    """Point a stored Office Bearer achievement at its club_roles row.

    Returns the role id so the caller can report it. The achievement keeps its
    own text columns either way — the link is an addition, not a replacement,
    so nothing that reads achievements today has to change.
    """
    role = await ensure_role_for_award(session, org_id, subcategory, achievement)
    if role is None:
        return None
    await session.execute(
        text("UPDATE player_achievements SET club_role_id = :rid WHERE id = :id AND org_id = :org"),
        {"rid": str(role.id), "id": achievement_id, "org": str(org_id)},
    )
    return str(role.id)


async def _season_year(session: AsyncSession, value: Optional[str]) -> Optional[int]:
    """The starting year of an award's season.

    ``player_achievements.season`` is free text that has held two things over
    the years: a seasons-table UUID (what the UI writes) and a plain label like
    "2025/26" (what imports write). Both resolve here; anything else is None,
    which the caller treats as "no date recorded" rather than guessing.
    """
    raw = (value or "").strip()
    if not raw:
        return None
    if _UUID_RE.match(raw):
        row = (await session.execute(
            text("SELECT year, name FROM seasons WHERE id = :id"), {"id": raw},
        )).mappings().first()
        if not row:
            return None
        if row["year"]:
            return int(row["year"])
        raw = row["name"] or ""
    m = re.search(r"(\d{4})", raw)
    return int(m.group(1)) if m else None


async def adopt_awards_as_terms(session: AsyncSession, org_id) -> dict:
    """Turn recorded Office Bearer awards into committee terms.

    The club-facing point of the whole exercise: a club that tracked its office
    bearers in BetterStats Awards for years, then subscribes to
    BetterClubhouse, should find its committee history already on the Committee
    screen rather than a blank slate beside a full awards list.

    Only awards naming a COMMITTEE role are adopted — a 1st XI Captain award is
    an honour, not a seat on the committee. Terms are inserted directly rather
    than through ``start_term``, which auto-closes the open term for a position:
    correct when a real handover happens, wrong when back-filling a decade of
    history in whatever order the rows come out.

    Idempotent on (position, holder, start date), so running it twice adds
    nothing and a club can re-run it after recording more history.
    """
    from app.services.committee import sync_committee_positions

    # Make sure every committee role has its position row before we hang terms
    # off it — a club arriving from BetterStats has roles but no positions yet.
    await sync_committee_positions(session, org_id)
    await session.flush()

    rows = (await session.execute(text("""
        SELECT pa.id, pa.player_id, pa.player_name, pa.season, pa.season_end,
               pa.club_role_id, cp.id AS position_id
        FROM player_achievements pa
        JOIN club_roles cr ON cr.id = pa.club_role_id AND cr.is_committee = TRUE
        JOIN committee_positions cp ON cp.role_id = cr.id AND cp.organisation_id = :org
        WHERE pa.org_id = :org AND pa.category = :cat
    """), {"org": str(org_id), "cat": AWARD_CATEGORY})).mappings().all()

    created = skipped = undated = 0
    for row in rows:
        start_year = await _season_year(session, row["season"])
        if start_year is None:
            undated += 1
            continue
        # Cricket seasons run winter to winter; a term recorded against 2025/26
        # starts with that season, not on 1 January.
        started = date(start_year, 7, 1)
        end_year = await _season_year(session, row["season_end"])
        # No end season means the award is open-ended ("— Present —"), which is
        # exactly what a term with no ended_at means.
        ended = date(end_year + 1, 6, 30) if end_year is not None else None

        exists = (await session.execute(text("""
            SELECT 1 FROM committee_terms
            WHERE organisation_id = :org AND position_id = :pos
              AND started_at = :started AND lower(holder_name) = lower(:holder)
            LIMIT 1
        """), {"org": str(org_id), "pos": str(row["position_id"]),
               "started": started, "holder": row["player_name"] or ""})).first()
        if exists:
            skipped += 1
            continue

        # fee_members.player_id is the one solid join between an achievement and
        # a club member; the name is only a snapshot on the term either way.
        member_id = None
        if row["player_id"]:
            member_id = (await session.execute(text("""
                SELECT id FROM fee_members
                WHERE organisation_id = :org AND player_id = :pid LIMIT 1
            """), {"org": str(org_id), "pid": str(row["player_id"])})).scalar()

        await session.execute(text("""
            INSERT INTO committee_terms
                (id, organisation_id, position_id, member_id, holder_name, started_at, ended_at)
            VALUES (gen_random_uuid(), :org, :pos, :member, :holder, :started, :ended)
        """), {"org": str(org_id), "pos": str(row["position_id"]), "member": str(member_id) if member_id else None,
               "holder": (row["player_name"] or "Unknown")[:200], "started": started, "ended": ended})
        created += 1

    return {"created": created, "already_there": skipped, "no_season_recorded": undated}


async def backfill_achievement_roles(session: AsyncSession, org_id) -> int:
    """Link the Office Bearer achievements a club recorded before this existed.

    Safe to re-run: only rows with no link are touched.
    """
    rows = (await session.execute(text("""
        SELECT id, subcategory, achievement
        FROM player_achievements
        WHERE org_id = :org AND category = :cat AND club_role_id IS NULL
          AND achievement IS NOT NULL AND achievement <> ''
    """), {"org": str(org_id), "cat": AWARD_CATEGORY})).mappings().all()
    linked = 0
    for row in rows:
        if await link_achievement_role(session, org_id, row["id"], row["subcategory"], row["achievement"]):
            linked += 1
    return linked
