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


def _scored_innings_sql(g: str) -> str:
    """SQL count of innings in `g.innings_totals` where anything was scored.

    `innings_totals` is a JSONB list written once from CA's own `innings[]`
    (`sync._extract_innings_totals`) and is NULL for a game CA sent no innings
    for. A placeholder innings that never started reads 0 runs, 0 wickets and
    does not count. The digits are stripped before the cast so an odd value in
    a stored payload can never raise inside a read query.
    """
    runs = ("COALESCE(NULLIF(left(regexp_replace(_it.v->>'runs_scored', "
            "'[^0-9]', '', 'g'), 9), ''), '0')::int")
    wkts = ("COALESCE(NULLIF(left(regexp_replace(_it.v->>'wickets', "
            "'[^0-9]', '', 'g'), 9), ''), '0')::int")
    return f"""(
                    SELECT COUNT(*) FROM jsonb_array_elements(
                        CASE WHEN jsonb_typeof({g}.innings_totals) = 'array'
                             THEN {g}.innings_totals ELSE '[]'::jsonb END) AS _it(v)
                    WHERE jsonb_typeof(_it.v) = 'object'
                      AND ({runs} > 0 OR {wkts} > 0)
                )"""


def looks_unplayed_sql(g: str) -> str:
    """SQL predicate: a game CA calls COMPLETED that has nothing in its scorecard.

    CA's `status` is the first word on whether a fixture went ahead, but it is
    not the last. A completed fixture can carry a result with no cricket behind
    it: a forfeit or a walkover entered as a result, or a scorecard never filled
    in. Cricket Australia's own season totals leave these out of a player's
    matches, so counting the named side here put a club's figure above PlayHQ's
    (Jonathon Seen, 202 against 197: the gap was games like this).

    The test is deliberately only "nothing was recorded". A synced game CA does
    not call live or called off is treated as not played when no innings scored
    a run or lost a wicket AND nobody has a real batting line AND nobody has a
    bowling spell. A game that STARTED and was then stopped (rain after a few
    overs, a result of any kind) has an innings or a spell behind it, so it still
    counts, exactly as an abandoned game with play does. Whether the recorded
    result "matches" the play is NOT judged: a drawn game with 4.4 overs bowled
    is a game Cricket Australia counts, and an earlier draft that dropped it
    over-reached.

    `g` is the alias of a `games` row exposing `id`, `status` and
    `innings_totals`. A hand-typed game is never a `games` row, so it is never
    inferred away: it has no upstream to re-pull from.

    This only ever decides whether a NAMED player with no real line of their own
    counts the match. A player who batted, bowled or fielded in the game keeps
    it, exactly as for an abandoned one (see `appearance_counts_as_match`).
    """
    real_bat = (f"EXISTS (SELECT 1 FROM batting_innings _rb WHERE _rb.game_id = {g}.id "
                f"AND NOT COALESCE(_rb.did_not_bat, FALSE))")
    bowl = f"EXISTS (SELECT 1 FROM bowling_spells _rw WHERE _rw.game_id = {g}.id)"
    return f"""(
                ({g}.status IS NULL OR {g}.status = 'COMPLETED')
                AND {_scored_innings_sql(g)} = 0
                AND NOT {real_bat}
                AND NOT {bowl}
            )"""


def not_played_game_sql(g: str) -> str:
    """SQL predicate, never NULL: this game was not played.

    CA says so (`NOT_PLAYED_STATUSES`) or the scorecard is empty (`looks_unplayed_sql`).
    `g` is the alias of a `games` row. COALESCE so `NOT` over it can never turn a
    NULL status into a row that silently drops out of a WHERE.
    """
    return (f"COALESCE(({g}.status IN ({NOT_PLAYED_SQL_LIST}) "
            f"OR {looks_unplayed_sql(g)}), FALSE)")


def appearance_counts_as_match(ga: str = "ga") -> str:
    """SQL predicate: does this `game_appearances` row count as a match played?

    Being named in a side is what makes a match a match, EXCEPT for a fixture
    that was called off — a club names a team for a game that is then washed
    out, and a Saturday nobody played is not a match. A game abandoned after
    play started IS one, so the rule is "called off AND this player recorded
    nothing at all in it", never "called off".

    "Called off" is CA's status OR a scorecard that shows no cricket was played
    (`not_played_game_sql`): CA marks some games COMPLETED with a result and an
    empty scorecard, and its own season totals leave those out of a match count.

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
                      AND {not_played_game_sql("_co")}
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
