"""How a club wants its derived rates qualified.

A strike rate worked out from three innings is a real figure, and it is not the
same kind of figure as one worked out from thirty. A leaderboard that ranks the
two together is the thing this qualification exists to stop.

The number is the club's, not ours. A minimum applied platform-wide would drop
players off every club's own board the day it shipped without anybody choosing
it, and a figure we invented would be quoted back at us — so the platform
default is 0 (no qualification, exactly what every board did before this) and a
club sets its own from Club Settings. A viewer can always raise it for one look
with the pills above the board, the same way the Yearbook's own minimums work.

The bar is counted on COVERED innings and spells, never on innings played. A
player with ten innings and three ball counts has a three-innings strike rate,
and letting that clear a ten-innings bar is exactly what the bar is for.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Nothing has ever qualified these boards. Turning a number on for everyone is
# a product decision a club makes, not a default we pick for them.
DEFAULT_MIN_RATE_INNINGS = 0
DEFAULT_MIN_RATE_SPELLS = 0

# What the pills above a board offer. "Any" is 0.
RATE_MINIMUM_OPTIONS = (0, 3, 5, 10, 20)

MAX_RATE_MINIMUM = 200


def clean_minimum(value) -> Optional[int]:
    """Normalise a stored or submitted minimum.

    None means "no club preference". Anything unusable, negative, or past the
    cap reads as 0 rather than being refused: a club typing junk into this box
    should end up with an unqualified board, never with an empty one.
    """
    if value is None:
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 0
    if n <= 0:
        return 0
    return min(n, MAX_RATE_MINIMUM)


async def club_rate_minimums(session: AsyncSession, org_id) -> dict:
    """The club's own defaults, falling back to the platform's."""
    row = (await session.execute(
        text("SELECT stats_min_rate_innings, stats_min_rate_spells "
             "FROM organisations WHERE id = CAST(:o AS UUID)"),
        {"o": str(org_id)},
    )).mappings().first()
    innings = clean_minimum((row or {}).get("stats_min_rate_innings"))
    spells = clean_minimum((row or {}).get("stats_min_rate_spells"))
    return {
        "min_rate_innings": DEFAULT_MIN_RATE_INNINGS if innings is None else innings,
        "min_rate_spells": DEFAULT_MIN_RATE_SPELLS if spells is None else spells,
    }


async def resolve_min_rate_innings(session: AsyncSession, org_id, asked) -> int:
    """A viewer's explicit pick wins; omitting it uses the club's own number.

    0 is a real answer here, not an absence — it is how a viewer switches the
    qualification off — so this tests for None rather than falsiness.
    """
    if asked is not None:
        return clean_minimum(asked) or 0
    return (await club_rate_minimums(session, org_id))["min_rate_innings"]


async def resolve_min_rate_spells(session: AsyncSession, org_id, asked) -> int:
    if asked is not None:
        return clean_minimum(asked) or 0
    return (await club_rate_minimums(session, org_id))["min_rate_spells"]
