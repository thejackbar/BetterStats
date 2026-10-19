"""Who counts as dormant, in one place.

A player is dormant when they have played before but not since the club's
dormancy window opened (``Organisation.dormancy_months``). A club can say a
dormant player is back (``players.dormancy_cleared_on``, migration 348), so they
turn up in availability, the squads board and selection in the weeks before
their first game back.

The cleared date counts as a last-active date for THIS test only. The player's
real last-played date is never changed (records, the "Hasn't played" filter and
the card badge still tell the truth), and the mark lapses by itself: a player
who is cleared and then never plays goes dormant again once the window has
passed from the day they were cleared. Playing a game does the rest.

Derived on read: nothing here stores "is dormant".
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def activity_date(last_played: Optional[date], cleared_on: Optional[date]) -> Optional[date]:
    """The later of the last game and the day the club said the player is back."""
    dates = [d for d in (last_played, cleared_on) if d]
    return max(dates) if dates else None


def is_dormant(last_played: Optional[date], cleared_on: Optional[date], cutoff: date) -> bool:
    """Played before, and nothing (a game or a "back" mark) since the cutoff.

    A player with no game and no mark is NOT dormant: a name added last week has
    no history to be old.
    """
    if not last_played:
        return False
    return activity_date(last_played, cleared_on) < cutoff


async def cleared_map(db: AsyncSession, club_id) -> dict[uuid.UUID, date]:
    """``{player id: dormancy_cleared_on}`` for the club's players who have one."""
    res = await db.execute(
        text("SELECT id, dormancy_cleared_on FROM players "
             "WHERE organisation_id = :org AND dormancy_cleared_on IS NOT NULL"),
        {"org": club_id},
    )
    return {pid: d for pid, d in res.fetchall()}
