"""One definition of how a manual adjustment reads as season stats.

``afl_manual_adjustments`` is the third source of a player's totals, beside
the synced rollup (``afl_player_season_stats``) and a historical upload
(``afl_imported_stats``). Every AFL read that combines the first two now
combines all three, and the branch they paste in is built here rather than
retyped per query — thirteen hand-written copies of the same UNION arm is how
the leaderboard and the record book start disagreeing about a player's career.

Two rules, and they are the whole reason this branch looks different from the
imported one sitting next to it:

* **A manual row is ADDITIVE.** It carries no ``NOT EXISTS`` gate against the
  synced rollup. An imported row is a club's own record of a season and only
  ever fills a gap the sync hasn't covered; an adjustment is a correction an
  admin typed *because* of what the sync holds, so suppressing it wherever the
  sync already has that player-season would silently do nothing in exactly the
  case it was entered for.

* **A row with no season is career-only.** Nothing here excludes it — the
  callers do, and they do it for free: a season-scoped read binds
  ``m.season_id = :season`` and a season-keyed one INNER JOINs ``seasons``,
  both of which drop a NULL season without a special case. What that leaves is
  the career reads, which is exactly where a career-only row belongs.
"""

# The manual column behind each name the AFL reads use. Anything not in here
# has no equivalent on an adjustment and can't be selected through this branch.
_COLS = {
    "player_id": "m.player_id",
    "season_id": "m.season_id",
    "grade_id": "m.grade_id",
    "games": "m.games_played",
    "goals": "m.goals",
    "behinds": "m.behinds",
    "bog_count": "m.bog_count",
    "bogs": "m.bog_count",
    "captain_games": "m.captain_games",
    "club_bf_votes": "m.club_bf_votes",
    "comp_bf_votes": "m.comp_bf_votes",
}


def manual_branch(columns, *, where: str = "", joins: str = "",
                  org_param: str = "org") -> str:
    """A ``SELECT`` over the org's adjustments, shaped to match the branch it
    is unioned with.

    Each entry in ``columns`` is either a name from the map above — aliased to
    that name, so the arm lines up with the synced/imported arms without the
    caller thinking about which column an adjustment stores it in — or a raw
    SQL expression, passed through untouched for anything off a joined table.
    A UNION matches by POSITION, so the two kinds interleave in whatever order
    the branch above uses.

    ``where`` is appended to the org scope and must start with ``AND``;
    ``joins`` carries any table the raw expressions read from.
    """
    select = ", ".join(
        (_COLS[c] if _COLS[c] == f"m.{c}" else f"{_COLS[c]} AS {c}")
        if c in _COLS else c
        for c in columns
    )
    return f"""
            SELECT {select}
            FROM afl_manual_adjustments m
            {joins}
            WHERE m.organisation_id = :{org_param} {where}
    """.strip()
