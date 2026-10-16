"""Which of a club's fixtures are junior cricket, for BetterSelect screens.

Manage Grades already says whether a grade is senior, junior, women's, masters
or mixed (``grades.categories``, with a name-based suggestion when nobody has
classified it). This reads that answer and applies it to fixtures, so a club
that runs senior selection in BetterSelect can leave its juniors out of the
availability matrix, the squads board's next-game column and the fixtures list
without a second setting to keep in step.

Derived on read, never stored: a grade reclassified in Manage Grades changes
the answer on the next request.

Fails open. A fixture with no grade and a team whose name does not read as
junior is NOT junior, because hiding a real senior game on a guess is the worse
mistake.
"""
from __future__ import annotations

from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Grade, Team
from app.services.grade_labels import categories_for_name, org_grade_category_sets


async def junior_fixture_ids(db: AsyncSession, club_id, fixtures: Iterable) -> set[str]:
    """Ids (as strings) of the given Fixture rows that are junior cricket."""
    fixtures = list(fixtures)
    if not fixtures:
        return set()

    team_ids = {f.team_id for f in fixtures if f.team_id}
    team_info: dict = {}
    if team_ids:
        for tid, tname, tgrade in (await db.execute(
            select(Team.id, Team.name, Team.grade_id).where(Team.id.in_(team_ids))
        )).fetchall():
            team_info[tid] = (tname, tgrade)

    def grade_of(f):
        return f.grade_id or (team_info.get(f.team_id) or (None, None))[1]

    grade_ids = {g for g in (grade_of(f) for f in fixtures) if g}
    grade_names: dict = {}
    if grade_ids:
        for gid, gname in (await db.execute(
            select(Grade.id, Grade.name).where(Grade.id.in_(grade_ids))
        )).fetchall():
            grade_names[gid] = gname

    categories = await org_grade_category_sets(db, club_id)
    out: set[str] = set()
    for f in fixtures:
        gid = grade_of(f)
        name = grade_names.get(gid) if gid else None
        if not name and f.team_id in team_info:
            name = team_info[f.team_id][0]
        if name and "junior" in categories_for_name(categories, name):
            out.add(str(f.id))
    return out
