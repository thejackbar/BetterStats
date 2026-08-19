"""What Cricket Australia's match status means to us (migration 266).

`games.status` holds CA's own string for a fixture, verbatim. There is exactly
one question this codebase asks of it: **was this fixture actually played**.

That question could not be answered before the column existed. `games.result`
is NULL for a washout, and equally NULL for a fixture still to be played, one
in progress, and one whose result we could not classify — so no read-side rule
built on a null result can tell a rained-off Saturday from next Saturday.

Keeping the vocabulary here rather than inlining the two strings means the
sync, the season-stats view, the read paths and the backfill script cannot
drift into disagreeing about what counts as a game.
"""

# A fixture that appears on the card and never happened. Both come straight
# from CA (`status` on /scores/grades/{id}/matches and /scores/matches/{id}).
#
# NO RESULT (statusId 5) is deliberately NOT here. A no-result match is one
# that started and could not be finished, which is a game the players turned
# up to and the club counts. Only a fixture called off outright is excluded.
NOT_PLAYED_STATUSES = ("ABANDONED", "CANCELLED")

# Ready to interpolate into a WHERE clause. Bound values would be tidier, but
# this fragment goes into the view definition in migration 266 as well as into
# ordinary queries, and a view cannot carry bind parameters.
NOT_PLAYED_SQL_LIST = ", ".join(f"'{s}'" for s in NOT_PLAYED_STATUSES)


def is_not_played(status: str | None) -> bool:
    """True when CA says this fixture was called off rather than played."""
    return (status or "").strip().upper() in NOT_PLAYED_STATUSES
