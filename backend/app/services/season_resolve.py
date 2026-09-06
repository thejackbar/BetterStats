"""Which season a match date belongs to, and getting that season on file.

Reported off a live club: a scorecard uploaded from a 1974 PDF was filed
under Summer 1999/00, because the season dropdown only offers seasons the
club already has and the club's own list starts at 1996/97. There was no
way to pick 1974/75, so the game went in under whatever was on the list and
then could not be found by any filter.

Nothing here invents a new rule. The season boundary is the one the rest of
the app already uses (`votes.season_year_for`, and `selection_rules`'
default `start_month` of 7), and the canonical name is the one
`scripts/cleanup_seasons` already tidies a club's list into. This is the
single place both are defined, so an uploaded card and a tidied season list
cannot disagree about what 1974/75 is called.
"""

from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Grade, Season
from app.services.grade_labels import suggest_categories, suggest_category

# Jul → Jun. October 2025 and February 2026 are both season 2025. Deliberately
# NOT the Sep–Dec boundary the upload page used to apply on its own: two
# definitions disagree for a July or August fixture, and the rest of the app
# has always counted a club year from July.
SEASON_START_MONTH = 7

# "1968/69", "1968-69", "1968/1969" — anywhere in the name, so the synced
# "Summer 1968/69" parses too.
_TOKEN = re.compile(r"(\d{4})\s*[/\-–]\s*(\d{2}|\d{4})")


def season_year_for_date(d: Optional[date]) -> Optional[int]:
    """The starting year of the season a date falls in, or None."""
    if not d:
        return None
    return d.year if d.month >= SEASON_START_MONTH else d.year - 1


def season_start_year(name: str) -> Optional[int]:
    """The starting year a season NAME refers to, or None.

    Only a consecutive pair counts ("1968/69", "1968/1969") — a name like
    "1968/72" is somebody's own labelling, not a season token we understand.
    """
    m = _TOKEN.search(name or "")
    if not m:
        return None
    start = int(m.group(1))
    end_raw = m.group(2)
    expected = (start + 1) % 100 if len(end_raw) == 2 else start + 1
    return start if int(end_raw) == expected else None


def canonical_name(start: int) -> str:
    """What this club's season list calls that year: "Summer 1974/75"."""
    return f"Summer {start}/{(start + 1) % 100:02d}"


def season_of(season: Season) -> Optional[int]:
    """A stored season's start year — its NAME first, then its `year` column.

    Name first because a manually-created season can carry a NULL year (that
    is one of the states `cleanup_seasons` exists to repair), and because a
    club's own naming is the thing an admin reads off the dropdown.
    """
    return season_start_year(season.name or "") or season.year


async def find_season_for_year(
    db: AsyncSession, org_id: uuid.UUID, year: int
) -> Optional[Season]:
    """The club's own season row for that year, if it has one.

    A year can legitimately hold several rows — Summer and Winter, or a
    masters competition under its own CA season id — so the canonically
    named one wins, then a synced one, then whatever is left. Picking
    arbitrarily among them is how a game lands in the wrong competition.
    """
    rows = (await db.execute(
        select(Season).where(Season.organisation_id == org_id)
    )).scalars().all()
    matches = [s for s in rows if season_of(s) == year]
    if not matches:
        return None
    want = canonical_name(year).lower()
    for s in matches:
        if (s.name or "").strip().lower() == want:
            return s
    for s in matches:
        if s.grassroots_id:
            return s
    return matches[0]


async def ensure_season_for_year(
    db: AsyncSession, org_id: uuid.UUID, year: int
) -> tuple[Season, bool]:
    """That year's season, creating it when the club has none.

    `grassroots_id` stays NULL, which is itself the "not from a sync" marker
    every other reader already uses. Flushes but never commits — the caller
    owns the transaction, so a season is never left behind by a game
    creation that then failed.
    """
    found = await find_season_for_year(db, org_id, year)
    if found:
        return found, False
    season = Season(
        id=uuid.uuid4(),
        organisation_id=org_id,
        grassroots_id=None,
        name=canonical_name(year),
        year=year,
    )
    db.add(season)
    await db.flush()
    return season, True


async def ensure_grade(
    db: AsyncSession, season: Season, name: str
) -> tuple[Optional[Grade], bool]:
    """That season's grade of the given name, creating it when absent.

    A season minted for a 1974 card has no grades at all, so without this an
    admin has a season they cannot file the game under. `category` AND
    `categories` are both written, per the rule that a site setting one must
    set the other or a "Girls Under 16" grade lands as junior alone and
    loses its women's half.
    """
    name = (name or "").strip()
    if not name:
        return None, False
    found = (await db.execute(
        select(Grade).where(
            Grade.season_id == season.id,
            func.lower(Grade.name) == name.lower(),
        )
    )).scalar_one_or_none()
    if found:
        return found, False
    grade = Grade(
        id=uuid.uuid4(),
        season_id=season.id,
        grassroots_id=None,
        name=name,
        category=suggest_category(name),
        categories=list(suggest_categories(name)),
    )
    db.add(grade)
    await db.flush()
    return grade, True


async def resolve_for_date(
    db: AsyncSession,
    org_id: uuid.UUID,
    played_at: Optional[date],
    grade_name: Optional[str] = None,
    create: bool = False,
) -> dict:
    """What season (and grade) a match on this date belongs to.

    With `create` false this reports only — which is what the upload screen
    asks before an admin has committed to importing anything.
    """
    year = season_year_for_date(played_at)
    if year is None:
        return {"year": None, "expected_name": None, "season": None,
                "season_created": False, "grade": None, "grade_created": False}

    season = await find_season_for_year(db, org_id, year)
    season_created = False
    if season is None and create:
        season, season_created = await ensure_season_for_year(db, org_id, year)

    grade, grade_created = None, False
    if season is not None and grade_name and create:
        grade, grade_created = await ensure_grade(db, season, grade_name)

    return {
        "year": year,
        "expected_name": canonical_name(year),
        "season": ({"id": str(season.id), "name": season.name, "year": season.year}
                   if season else None),
        "season_created": season_created,
        "grade": ({"id": str(grade.id), "name": grade.name} if grade else None),
        "grade_created": grade_created,
    }


def season_matches_date(season: Season, played_at: Optional[date]) -> bool:
    """Whether a game on this date belongs in this season.

    True when we cannot tell — a season whose name carries no year token and
    no `year` column says nothing, and reporting a mismatch we cannot stand
    behind is worse than saying nothing.
    """
    year = season_year_for_date(played_at)
    stored = season_of(season)
    if year is None or stored is None:
        return True
    return stored == year
