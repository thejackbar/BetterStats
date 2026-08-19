"""Who a club has hidden from its public site (``players.is_public``).

A club can opt one player out of every PUBLIC surface — the roster, the
navbar search, their own profile page, the leaderboards and the club
records. The case this was built for is a junior who does not want to be
findable by name. It is a display rule and nothing else: the player's
appearances, innings and season aggregates are untouched, they still count
towards the club's own totals, and every admin surface (selection, fees,
BetterIQ, reports) still shows them, because the club plainly needs them
there.

The escape is the same one hidden grades already use
(``routers/auth.user_can_view_org_private``): a signed-in club admin, or
Better staff, sees their own club whole. So the callers here take a
``public_only`` flag rather than deciding for themselves.

Filtering happens on the way OUT, per endpoint, rather than inside the
leaderboard SQL. Those builders have a dozen branches each (finals, captain,
per-grade, the aggregate/per-innings split) and threading an exclusion
through every one of them is how one branch quietly ends up without it.
Every row a public endpoint returns already carries its ``player_id``, so
one filter at the endpoint covers every branch at once. The cost is that a
top-20 board with a hidden player in it returns 19 rows, which is the honest
answer.
"""
from __future__ import annotations

import uuid
from typing import Any, Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Player

# The keys a row might carry a player's id under, across the leaderboard,
# records, partnership and milestone payloads. A partnership names TWO people
# and hiding either one has to remove the stand — a record naming a hidden
# junior alongside a teammate still names them.
_ID_KEYS = (
    "player_id", "id", "playerId",
    "batter1_id", "batter2_id", "bowler_id", "fielder_id",
)


async def hidden_player_ids(session: AsyncSession, org_id) -> set[str]:
    """Every player this club has hidden, as lowercase id strings.

    Empty for the overwhelming majority of clubs, which is what lets every
    caller skip the filter entirely rather than walking its rows.
    """
    try:
        oid = org_id if isinstance(org_id, uuid.UUID) else uuid.UUID(str(org_id))
    except (ValueError, TypeError, AttributeError):
        return set()
    rows = (await session.execute(
        select(Player.id).where(
            Player.organisation_id == oid,
            Player.is_public.is_(False),
        )
    )).scalars().all()
    return {str(pid).lower() for pid in rows}


def _row_names_hidden(row: Any, hidden: set[str]) -> bool:
    """Does this row name anybody the club has hidden?

    Every id key the row carries is checked, not just the first: a
    partnership names two people, and a stand has to go if either of them is
    hidden. A row with no recognisable id is never hidden — an aggregate or
    an import residual we cannot attribute is not a row we know to hide, the
    same rule ``grade_scope.clause`` follows for a grade it cannot
    categorise.
    """
    if not isinstance(row, dict):
        return False
    for key in _ID_KEYS:
        val = row.get(key)
        if val and str(val).lower() in hidden:
            return True
    return False


def drop_hidden(rows: Iterable[Any], hidden: set[str]) -> list:
    """``rows`` without any row naming a hidden player."""
    rows = list(rows or [])
    if not hidden:
        return rows
    return [r for r in rows if not _row_names_hidden(r, hidden)]


def prune_hidden(payload: Any, hidden: set[str]) -> Any:
    """``drop_hidden`` applied through a whole nested response payload.

    The club records page answers with one deep dict — batting, bowling,
    fielding and partnerships, each holding a dozen boards plus a by_grade
    map of more boards. Walking it once beats naming forty keys and beats
    threading an exclusion through every builder underneath, and a board that
    gains a new key later is covered without anyone remembering to add it.

    A dict is only ever pruned as a member of a LIST, never replaced where it
    sits — so a top-level object that happens to carry a ``player_id`` (a
    single "best ever" record, say) keeps its place in the shape the frontend
    expects rather than vanishing and reading as a missing field.
    """
    if not hidden:
        return payload
    if isinstance(payload, dict):
        return {k: prune_hidden(v, hidden) for k, v in payload.items()}
    if isinstance(payload, list):
        kept = [r for r in payload if not _row_names_hidden(r, hidden)]
        return [prune_hidden(r, hidden) for r in kept]
    return payload


async def filter_public_rows(
    session: AsyncSession, org_id, rows: Iterable[Any], public_only: bool
) -> list:
    """``drop_hidden`` with the lookup folded in, for a one-line call site."""
    rows = list(rows or [])
    if not public_only or not rows:
        return rows
    return drop_hidden(rows, await hidden_player_ids(session, org_id))


async def is_hidden_from(
    session: AsyncSession, player: Player, public_only: bool
) -> bool:
    """Should this viewer be refused this player's own profile page?"""
    return bool(public_only and player is not None and player.is_public is False)
