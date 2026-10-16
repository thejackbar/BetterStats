"""The days a fixture is played on, and one availability answer across them.

Availability is keyed on a playing DATE. A one-day game has one date; a two-day
game has two (`played_on` = week 1, `end_on` = week 2), and a player can be free
for one and not the other. Selection needs both, so a two-day side reads every
day and takes the least favourable answer.

Pure on purpose: no database, so the board, the overview and the checks share
one definition.
"""
from __future__ import annotations

from datetime import date
from typing import Iterable, Optional

# Least favourable first, the reverse of the app's own order (available, maybe,
# no response, unavailable; `lib/availability.js` rank): a player is only
# AVAILABLE for the game when every day is, and one UNAVAILABLE day rules them out.
_ORDER = ("UNAVAILABLE", "NO_RESPONSE", "MAYBE", "AVAILABLE")


def fixture_days(played_on: Optional[date], end_on: Optional[date]) -> list[date]:
    """[played_on] for a one-day game, [played_on, end_on] for a two-day one.
    An end date on or before the start is bad data and reads as one day."""
    if not played_on:
        return []
    if end_on and end_on > played_on:
        return [played_on, end_on]
    return [played_on]


def combine_status(statuses: Iterable[Optional[str]]) -> str:
    """One status for a game played over several days: the least favourable."""
    seen = {(s or "NO_RESPONSE") for s in statuses}
    for s in _ORDER:
        if s in seen:
            return s
    return "NO_RESPONSE"
