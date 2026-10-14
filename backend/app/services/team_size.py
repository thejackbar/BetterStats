"""How many players a team names (migration 330).

The club has one default (``organisations.default_team_size``, 0 = no limit).
A team may carry its own (``teams.team_size``): a women's grade picks ten, an
OD6s side twelve. ``NULL`` on the team means "use the club default", which is
what every team had before this existed, so nothing changes until a selector
sets one. Zero is a real answer on a team too (no limit), so absent and zero
are never confused.
"""
from typing import Optional

CLUB_FALLBACK = 11
MIN_TEAM_SIZE = 6
MAX_TEAM_SIZE = 15


def club_size(club) -> int:
    v = getattr(club, "default_team_size", None)
    return CLUB_FALLBACK if v is None else v


def effective_size(club, team) -> int:
    """The team's own size when it has one, else the club's."""
    v = getattr(team, "team_size", None) if team is not None else None
    return club_size(club) if v is None else v


def clean_team_size(value) -> Optional[int]:
    """A size a selector may set on a team: 0 (no limit) or a plain count.
    ``None`` clears it back to the club default. Anything else is refused."""
    if value is None:
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ValueError("Team size must be a number")
    if n != 0 and not (MIN_TEAM_SIZE <= n <= MAX_TEAM_SIZE):
        raise ValueError(f"Team size must be 0 (no limit) or between {MIN_TEAM_SIZE} and {MAX_TEAM_SIZE}")
    return n
