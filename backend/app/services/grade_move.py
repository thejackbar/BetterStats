"""A team that Cricket Australia moves to another grade keeps what it had.

An association moves a side up or down mid-season (Applecross 8th XI, One Day
Grade 6 to Grade 5). Everything the club did for that side hangs off a fixture row
(the picked XI, the unconfirmed draft, votes, notes) or off a vote medal that
counts a list of grades by name. Two things lost it:

  * the fixtures sync could only re-key a game inside ONE grade, so the
    Grade 6 row CA dropped was cancelled or removed and the Grade 5 one was
    created empty beside it (``fixtures_reconcile.find_moved``);
  * a medal ticked for Grade 6 never counted a vote cast in Grade 5, so a
    season of votes for the side stopped adding up the day it moved
    (``extend_medals``).

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


def our_side_name(home_away: Optional[str], home_team: Optional[str], away_team: Optional[str]) -> str:
    """The club's own team name in a fixture, lower-cased and space-collapsed."""
    name = home_team if home_away == "HOME" else away_team if home_away == "AWAY" else None
    return " ".join((name or "").lower().split())
