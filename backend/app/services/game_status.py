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


def appearance_counts_as_match(ga: str = "ga") -> str:
    """SQL predicate: does this `game_appearances` row count as a match played?

    Being named in a side is what makes a match a match, EXCEPT for a fixture
    that was called off — a club names a team for a game that is then washed
    out, and a Saturday nobody played is not a match. A game abandoned after
    play started IS one, so the rule is "called off AND this player recorded
    nothing at all in it", never "called off".

    Exists because the same test is needed in five separate queries, and the
    migration 266 view expresses it a sixth time in its own SQL. Five hand-typed
    copies of a five-line predicate is how one of them ends up subtly different
    and one screen quietly disagrees with the rest.

    `ga` is the alias of the `game_appearances` row being tested; it must expose
    both `game_id` and `player_id`. The three EXISTS branches are redundant
    inside a UNION that already has batting/bowling/fielding branches of its own
    (a game with a recorded contribution arrives there anyway) and load-bearing
    where this is the only source of the count, as in StatLab's `appear` CTE.
    They are kept in both cases so there is one predicate rather than two.
    """
    return f"""(
                NOT EXISTS (
                    SELECT 1 FROM games _co
                    WHERE _co.id = {ga}.game_id
                      AND _co.status IN ({NOT_PLAYED_SQL_LIST})
                )
                OR EXISTS (
                    SELECT 1 FROM v_effective_batting_innings _cb
                    WHERE _cb.game_id = {ga}.game_id AND _cb.player_id = {ga}.player_id
                )
                OR EXISTS (
                    SELECT 1 FROM v_effective_bowling_spells _cw
                    WHERE _cw.game_id = {ga}.game_id AND _cw.player_id = {ga}.player_id
                )
                OR EXISTS (
                    SELECT 1 FROM v_effective_fielding_stats _cf
                    WHERE _cf.game_id = {ga}.game_id AND _cf.player_id = {ga}.player_id
                )
            )"""
