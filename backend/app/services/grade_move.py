"""A team that Cricket Australia moves to another grade keeps what it had.

An association moves a side up or down mid-season (Applecross 8th XI, One Day
Grade 6 to Grade 5). Everything the club did for that side hangs off a fixture row
(the picked XI, the unconfirmed draft, votes, notes) or off a vote medal that
counts a list of grades by name. Three things lost it:

  * the fixtures sync could only re-key a game inside ONE grade, so the
    Grade 6 row CA dropped was cancelled or removed and the Grade 5 one was
    created empty beside it (``fixtures_reconcile.find_moved``);
  * a medal ticked for Grade 6 never counted a vote cast in Grade 5, so a
    season of votes for the side stopped adding up the day it moved
    (``extend_medals``);
  * a side the sync could not pair row to row (the old row kept as CANCELLED,
    the new grade's game beside it) never widened the medal at all
    (``extend_medals_for_dropped_games``).

Nothing here moves a played game: its stats belong to the grade it was played in
and stay there (derive on read).
"""
from __future__ import annotations

import logging
import uuid
from typing import Iterable, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import VoteMedal
from app.services.grade_labels import grade_key

logger = logging.getLogger(__name__)


async def _grade_names(db: AsyncSession, org_id, ids: Iterable) -> dict[str, str]:
    ids = [uuid.UUID(str(i)) for i in ids if i]
    if not ids:
        return {}
    res = await db.execute(
        text(
            "SELECT gr.id, gr.name FROM grades gr JOIN seasons s ON s.id = gr.season_id "
            "WHERE s.organisation_id = :org AND gr.id = ANY(CAST(:ids AS uuid[]))"
        ),
        {"org": org_id, "ids": ids},
    )
    return {str(gid): name for gid, name in res.fetchall()}


async def extend_medals(db: AsyncSession, org_id, old_grade_id, new_grade_id) -> list[str]:
    """Make every vote medal that counts the old grade count the new one too.

    Only a medal that is restricted to chosen grades (an empty list already means
    every grade) and counts the old grade by NAME but not the new one is touched,
    and only by ADDING the new grade: a tick is never taken away. Returns the
    names of the medals changed. Does not commit.
    """
    if not old_grade_id or not new_grade_id or str(old_grade_id) == str(new_grade_id):
        return []
    from app.services import votes as vote_svc

    names = await _grade_names(db, org_id, [old_grade_id, new_grade_id])
    old_name, new_name = names.get(str(old_grade_id)), names.get(str(new_grade_id))
    if not old_name or not new_name or grade_key(old_name) == grade_key(new_name):
        return []
    old_key, new_key = grade_key(old_name), grade_key(new_name)

    medals = (await db.execute(
        select(VoteMedal).where(VoteMedal.organisation_id == org_id)
    )).scalars().all()
    changed: list[str] = []
    for m in medals:
        if not vote_svc.clean_grade_ids(m.grade_ids):
            continue
        allowed = await vote_svc.medal_grade_ids(db, org_id, m) or set()
        allowed_names = await _grade_names(db, org_id, allowed)
        keys = {grade_key(n) for n in allowed_names.values()}
        if old_key in keys and new_key not in keys:
            m.grade_ids = vote_svc.clean_grade_ids(list(m.grade_ids or []) + [str(new_grade_id)])
            changed.append(m.name)
    if changed:
        await db.flush()
    return changed


async def extend_medals_for_dropped_games(db: AsyncSession, org_id) -> list[str]:
    """Widen vote medals for a move the sync could not pair row to row.

    ``fixtures_reconcile`` follows a moved side only when exactly one stale row and
    one new game share the day and the team name. Otherwise the old row is kept as
    CANCELLED (the club had picked an XI on it) and the new grade's game sits beside
    it as its own row, and ``extend_medals`` never runs: a medal ticked for the old
    grade then drops the team's real games, and its voters are offered nothing.

    The signal is the same one a person would use. A team has a CANCELLED synced
    game in grade A and, on the same day, a live synced game in grade B, and it has
    no live game left in A on a later day (a squad that still plays A and had one
    game washed out is not a move). Every grade-limited medal that counts A by name
    then counts B too, through ``extend_medals``: ticks are only ever added, an
    all-grades medal is untouched, and running it again changes nothing. Any date,
    because the sync's own move logic ignores a day once it has passed. Does not
    commit. Returns the names of the medals changed.
    """
    rows = (await db.execute(
        text(
            "SELECT DISTINCT c.grade_id, l.grade_id "
            "FROM fixtures c "
            "JOIN fixtures l ON l.organisation_id = c.organisation_id AND l.team_id = c.team_id "
            "  AND l.played_on = c.played_on AND l.id <> c.id AND l.grade_id <> c.grade_id "
            "WHERE c.organisation_id = :org AND c.source = 'grassroots' "
            "  AND UPPER(COALESCE(c.status, '')) = 'CANCELLED' "
            "  AND c.team_id IS NOT NULL AND c.grade_id IS NOT NULL "
            "  AND l.source = 'grassroots' AND l.grade_id IS NOT NULL "
            "  AND UPPER(COALESCE(l.status, '')) NOT IN ('CANCELLED', 'BYE') "
            "  AND NOT EXISTS ("
            "    SELECT 1 FROM fixtures x WHERE x.organisation_id = c.organisation_id "
            "      AND x.team_id = c.team_id AND x.grade_id = c.grade_id AND x.source = 'grassroots' "
            "      AND x.played_on > c.played_on AND UPPER(COALESCE(x.status, '')) NOT IN ('CANCELLED', 'BYE'))"
        ),
        {"org": org_id},
    )).fetchall()
    changed: list[str] = []
    for old_grade, new_grade in rows:
        for name in await extend_medals(db, org_id, old_grade, new_grade):
            if name not in changed:
                changed.append(name)
    return changed


def our_side_name(home_away: Optional[str], home_team: Optional[str], away_team: Optional[str]) -> str:
    """The club's own team name in a fixture, lower-cased and space-collapsed."""
    name = home_team if home_away == "HOME" else away_team if home_away == "AWAY" else None
    return " ".join((name or "").lower().split())
