"""The club's own record book — team records, not a player's.

Cricket stores no team score anywhere. `games` carries a result and a winning
team and nothing else; AFL's equivalent feature can read `afl_game_details.
home_score` straight off the row, and there is no cricket analogue. So every
figure here is RECONSTRUCTED per game, and the reconstruction is the one
`iq_team._per_game` already uses rather than a second copy of it:

- our total  = GR's own per-innings `runs_scored` where we hold it, else
  `SUM(v_effective_batting_innings.runs)`;
- their total = the same, read off the innings we did NOT bat in, else
  `SUM(v_effective_bowling_spells.runs)` — the runs our bowlers conceded.

EVERY BOARD IS DERIVED FROM ONE PER-GAME PULL, in Python, deliberately. Ten
separate ranking queries is how "biggest win by runs" and "highest total"
start disagreeing about what a game's score was; and a streak is sequential,
so it wants the ordered list anyway.

THE EXACT/APPROXIMATE SPLIT IS THE ONE THING TO UNDERSTAND HERE.
`games.innings_totals` (migration 233) holds the true total — batters' runs
PLUS extras — but it was added prospectively with no backfill, so a game
synced before it shipped carries NULL and falls back to a bat-only sum that
understates the real total by roughly 10-25 runs. That is harmless for
BetterIQ's averages, where it is a small consistent bias, and NOT harmless
for a record book, where figures are ranked directly against each other:

- a HIGHEST-total board under-ranks every approximate game, so an old record
  can be beaten by a smaller modern score;
- a LOWEST-total board does the opposite and over-ranks them.

So every row carries `exact`, each board reports how many of its rows are
approximate, and the payload's `coverage` block says so for the whole club.
Nothing here silently presents the two as the same kind of figure.
`python -m app.scripts.backfill_innings_totals <org>` is the fix.
"""
from __future__ import annotations

import datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# How many rows a board carries. Matches routers/records.py's own `_LIMIT`.
BOARD_LIMIT = 25

# A side is "bowled out" at ten wickets. Used to keep a LOW-total board
# honest: 2/45 chasing a small target is not a low score, it is a short
# innings, and ranking it as one would put a routine win at the top of the
# club's worst-ever list. A side genuinely all out for fewer than ten (a
# player absent hurt, a short-handed team) is MISSED rather than guessed at,
# which is the conservative direction — this board never claims a record
# that isn't one.
ALL_OUT_WICKETS = 10


def _fmt_date(d: Any) -> Optional[str]:
    if d is None:
        return None
    if isinstance(d, (datetime.date, datetime.datetime)):
        return d.isoformat()
    return str(d)


_GAMES_SQL = """
WITH our_games AS (
    -- Ownership mirrors aggregations._club_results and iq_team._per_game: a
    -- game is ours through the per-club org sides (migration 167), the
    -- view's own organisation_id (169, which is what covers a grade-less
    -- manual game), the season's org, or an appearance by one of our
    -- players — so a shared fixture the OPPONENT synced first is still ours.
    -- Grades are LEFT JOINed for that same reason.
    --
    -- g.result is written relative to whichever club's sync got there
    -- first, so it is re-derived from the neutral winning_team against OUR
    -- side, falling back to g.result only when winning_team is NULL.
    SELECT g.id, g.played_at, g.venue, g.opp_club_name, g.match_format,
           g.home_team, g.away_team, g.is_final,
           gr.id AS grade_id,
           COALESCE(gr.display_name_override, gr.name) AS grade_name,
           s.id AS season_id, s.name AS season_name, s.year AS season_year,
           CASE
               WHEN g.winning_team IS NULL THEN g.result
               WHEN g.home_org_id = CAST(:org AS UUID) AND g.winning_team = g.home_team THEN 'WIN'
               WHEN g.home_org_id = CAST(:org AS UUID) AND g.winning_team = g.away_team THEN 'LOSS'
               WHEN g.away_org_id = CAST(:org AS UUID) AND g.winning_team = g.away_team THEN 'WIN'
               WHEN g.away_org_id = CAST(:org AS UUID) AND g.winning_team = g.home_team THEN 'LOSS'
               ELSE g.result
           END AS result,
           CASE WHEN g.away_club = g.opp_club_name THEN 'HOME'
                WHEN g.home_club = g.opp_club_name THEN 'AWAY' ELSE NULL END AS our_venue,
           gg.innings_totals
    FROM v_effective_games g
    LEFT JOIN grades gr ON gr.id = g.grade_id
    LEFT JOIN seasons s ON s.id = g.season_id
    -- migration 233's true per-innings totals live on the base `games` table
    -- only (a raw ALTER, never added to the view — a manual game can't have
    -- one). LEFT JOIN so a manual-sourced effective row simply carries NULL,
    -- which is the same fall-back-to-the-bat-sum case as a pre-233 game.
    LEFT JOIN games gg ON gg.id = g.id
    WHERE (
        g.organisation_id = CAST(:org AS UUID)
        OR g.home_org_id = CAST(:org AS UUID)
        OR g.away_org_id = CAST(:org AS UUID)
        OR s.organisation_id = CAST(:org AS UUID)
        OR EXISTS (
            SELECT 1 FROM game_appearances ga
            JOIN players gp ON gp.id = ga.player_id
            WHERE ga.game_id = g.id AND gp.organisation_id = CAST(:org AS UUID)
        )
    )
    -- A washout or an abandoned fixture has no team total to record and no
    -- result to streak on, so it never reaches a record book.
    AND g.result IS NOT NULL
    {season_clause}{grade_clause}{finals_clause}
),
bat AS (
    -- OUR rows only. A both-synced fixture is ONE games row carrying BOTH
    -- clubs' innings, so without the player scope this sums the opposition's
    -- runs into ours, counts their dismissals into wkts_lost (up to 20), and
    -- makes batted_first true for everyone.
    SELECT bi.game_id,
           SUM(bi.runs) AS our_runs,
           COUNT(*) FILTER (
               WHERE bi.did_not_bat IS NOT TRUE
                 AND NOT bi.not_out
                 AND bi.dismissal_type IS NOT NULL
           ) AS wkts_lost,
           BOOL_OR(bi.innings_number = 1) AS batted_first,
           ARRAY_AGG(DISTINCT bi.innings_number) AS our_innings_nums
    FROM v_effective_batting_innings bi
    JOIN our_games og ON og.id = bi.game_id
    JOIN players p ON p.id = bi.player_id AND p.organisation_id = CAST(:org AS UUID)
    WHERE bi.did_not_bat IS NOT TRUE
    GROUP BY bi.game_id
),
bowl AS (
    -- Same scope on the bowler: opp_runs = the runs OUR bowlers conceded.
    SELECT bs.game_id,
           SUM(bs.runs) AS opp_runs,
           SUM(bs.wickets) AS wkts_taken
    FROM v_effective_bowling_spells bs
    JOIN our_games og ON og.id = bs.game_id
    JOIN players p ON p.id = bs.player_id AND p.organisation_id = CAST(:org AS UUID)
    GROUP BY bs.game_id
)
SELECT og.id::text AS game_id, og.played_at, og.venue, og.opp_club_name,
       og.match_format, og.home_team, og.away_team, og.is_final,
       og.grade_id::text AS grade_id, og.grade_name,
       og.season_id::text AS season_id, og.season_name, og.season_year,
       og.result, og.our_venue,
       b.our_runs, b.wkts_lost, b.batted_first,
       bw.opp_runs, bw.wkts_taken,
       ours.exact_runs AS our_exact_runs, ours.exact_wkts AS our_exact_wkts,
       ours.ok AS our_exact_ok,
       theirs.exact_runs AS opp_exact_runs, theirs.exact_wkts AS opp_exact_wkts,
       theirs.ok AS opp_exact_ok
FROM our_games og
LEFT JOIN bat b ON b.game_id = og.id
LEFT JOIN bowl bw ON bw.game_id = og.id
-- Prefer GR's own true per-innings total (bat runs PLUS extras) over the
-- bat-only sum, but only when EVERY innings on our side of the match has a
-- stored, non-null runs_scored. A partial match — a two-day game with one
-- innings backfilled and one not — would add an exact figure to an
-- approximate one and reconcile with neither, so it is all or nothing.
LEFT JOIN LATERAL (
    SELECT SUM((elem->>'runs_scored')::numeric) AS exact_runs,
           SUM((elem->>'wickets')::numeric) AS exact_wkts,
           (COUNT(*) = COALESCE(array_length(b.our_innings_nums, 1), 0)
            AND BOOL_AND(elem->>'runs_scored' IS NOT NULL)) AS ok
    FROM jsonb_array_elements(og.innings_totals) elem
    WHERE (elem->>'innings_number')::int = ANY(b.our_innings_nums)
) ours ON og.innings_totals IS NOT NULL AND b.our_innings_nums IS NOT NULL
-- The opposition's own true total is the mirror image: the innings we did
-- NOT bat in. Same all-or-nothing rule, and it needs at least one such
-- innings to exist or a one-innings-a-side game we batted both halves of
-- would report a 0 total for them.
LEFT JOIN LATERAL (
    SELECT SUM((elem->>'runs_scored')::numeric) AS exact_runs,
           SUM((elem->>'wickets')::numeric) AS exact_wkts,
           (COUNT(*) > 0 AND BOOL_AND(elem->>'runs_scored' IS NOT NULL)) AS ok
    FROM jsonb_array_elements(og.innings_totals) elem
    WHERE NOT ((elem->>'innings_number')::int = ANY(b.our_innings_nums))
) theirs ON og.innings_totals IS NOT NULL AND b.our_innings_nums IS NOT NULL
ORDER BY og.played_at ASC, og.id ASC
"""


async def per_game(
    db: AsyncSession,
    org_id: str,
    *,
    season_ids: Optional[list] = None,
    grade_id: Optional[str] = None,
    grade_name_clause: str = "",
    finals_only: bool = False,
    scope_clause: str = "",
    extra_params: Optional[dict] = None,
) -> list[dict]:
    """One row per game the club played, with both sides' totals resolved.

    `grade_name_clause` is passed in rather than rebuilt because the caller
    (routers/records.py) already owns the merge-aware grade match — a second
    copy here is how the record book and the rest of the page start
    disagreeing about which games a renamed grade covers.
    """
    params: dict = {"org": org_id}
    if extra_params:
        params.update(extra_params)

    season_clause = ""
    if season_ids:
        # The season is already LEFT JOINed as `s` inside our_games, so the
        # filter goes against that alias rather than joining seasons twice.
        season_clause = " AND s.id = ANY(:season_ids)"
        params["season_ids"] = season_ids

    grade_clause = ""
    if grade_name_clause:
        grade_clause = grade_name_clause
    elif grade_id:
        grade_clause = " AND g.grade_id = CAST(:grade_id AS UUID)"
        params["grade_id"] = grade_id
    grade_clause += scope_clause

    sql = _GAMES_SQL.format(
        season_clause=season_clause,
        grade_clause=grade_clause,
        finals_clause=" AND g.is_final IS TRUE" if finals_only else "",
    )
    res = await db.execute(text(sql), params)

    out: list[dict] = []
    for r in res.mappings():
        d = dict(r)

        # Our total: the true figure when we hold every innings of it, else
        # the bat-only sum. `exact` rides along on the row because a record
        # book ranks these against each other and the two are not the same
        # kind of number — see the module docstring.
        our_exact = d.pop("our_exact_runs", None)
        our_ok = d.pop("our_exact_ok", None)
        our_exact_wkts = d.pop("our_exact_wkts", None)
        if our_ok and our_exact is not None:
            d["our_runs"] = int(our_exact)
            d["our_exact"] = True
            if our_exact_wkts is not None:
                d["wkts_lost"] = int(our_exact_wkts)
        else:
            d["our_runs"] = int(d["our_runs"]) if d.get("our_runs") is not None else None
            d["our_exact"] = False
            d["wkts_lost"] = int(d["wkts_lost"]) if d.get("wkts_lost") is not None else None

        opp_exact = d.pop("opp_exact_runs", None)
        opp_ok = d.pop("opp_exact_ok", None)
        opp_exact_wkts = d.pop("opp_exact_wkts", None)
        if opp_ok and opp_exact is not None:
            d["opp_runs"] = int(opp_exact)
            d["opp_exact"] = True
            d["wkts_taken"] = (
                int(opp_exact_wkts) if opp_exact_wkts is not None
                else (int(d["wkts_taken"]) if d.get("wkts_taken") is not None else None)
            )
        else:
            d["opp_runs"] = int(d["opp_runs"]) if d.get("opp_runs") is not None else None
            d["opp_exact"] = False
            d["wkts_taken"] = int(d["wkts_taken"]) if d.get("wkts_taken") is not None else None

        d["played_at"] = _fmt_date(d.get("played_at"))
        d["batted_first"] = bool(d.get("batted_first"))
        out.append(d)
    return out


def _row(g: dict, **extra) -> dict:
    """The shared shape every board's rows carry.

    One shape for all of them so the frontend renders a board without
    knowing which one it is, and so a game links the same way everywhere.
    """
    base = {
        "game_id": g.get("game_id"),
        "played_at": g.get("played_at"),
        "opponent": g.get("opp_club_name"),
        "venue": g.get("venue"),
        "our_venue": g.get("our_venue"),
        "season_name": g.get("season_name"),
        "grade_name": g.get("grade_name"),
        "is_final": bool(g.get("is_final")),
        "result": g.get("result"),
        "our_runs": g.get("our_runs"),
        "our_wickets": g.get("wkts_lost"),
        "opp_runs": g.get("opp_runs"),
        "opp_wickets": g.get("wkts_taken"),
    }
    base.update(extra)
    return base


def _board(rows: list[dict], *, exact_key: str = "exact") -> dict:
    """A board plus an honest count of how much of it is approximate.

    `approximate` is what lets the screen say "3 of these 25 are bat-only
    figures" instead of presenting two different kinds of number as one
    ranking. See the module docstring for why that matters here and not in
    BetterIQ.
    """
    kept = rows[:BOARD_LIMIT]
    return {
        "rows": kept,
        "approximate": sum(1 for r in kept if not r.get(exact_key, True)),
    }


def _is_win(g: dict) -> bool:
    return (g.get("result") or "").upper() in ("WIN", "W")


def _is_loss(g: dict) -> bool:
    return (g.get("result") or "").upper() in ("LOSS", "LOSE", "L")


def _totals_boards(games: list[dict]) -> dict:
    """Highest and lowest, for and against."""
    ours = [g for g in games if g.get("our_runs") is not None]
    theirs = [g for g in games if g.get("opp_runs") is not None]

    highest = sorted(ours, key=lambda g: (-g["our_runs"], g["played_at"] or ""))
    conceded = sorted(theirs, key=lambda g: (-g["opp_runs"], g["played_at"] or ""))

    # A low-total board only takes completed innings — see ALL_OUT_WICKETS.
    # Without it, every short chase is a club record low.
    lowest = sorted(
        [g for g in ours if (g.get("wkts_lost") or 0) >= ALL_OUT_WICKETS],
        key=lambda g: (g["our_runs"], g["played_at"] or ""),
    )
    bowled_out = sorted(
        [g for g in theirs if (g.get("wkts_taken") or 0) >= ALL_OUT_WICKETS],
        key=lambda g: (g["opp_runs"], g["played_at"] or ""),
    )

    return {
        "highest_totals": _board(
            [_row(g, value=g["our_runs"], exact=g["our_exact"]) for g in highest]
        ),
        "lowest_totals": _board(
            [_row(g, value=g["our_runs"], exact=g["our_exact"]) for g in lowest]
        ),
        "highest_conceded": _board(
            [_row(g, value=g["opp_runs"], exact=g["opp_exact"]) for g in conceded]
        ),
        "lowest_conceded": _board(
            [_row(g, value=g["opp_runs"], exact=g["opp_exact"]) for g in bowled_out]
        ),
    }


def _margin_boards(games: list[dict]) -> dict:
    """Winning and losing margins.

    A cricket margin is TWO different units and they are not comparable, so
    they are two boards rather than one mixed ranking: a side that bats
    first and defends wins BY RUNS, a side that chases wins BY WICKETS. Ten
    wickets and ten runs are not the same size of win, and ordering them
    together would put a nervy two-wicket win above a 200-run thrashing.
    """
    by_runs, by_wickets, defeats_runs, defeats_wickets = [], [], [], []

    for g in games:
        our, opp = g.get("our_runs"), g.get("opp_runs")
        if our is None or opp is None:
            continue
        won, lost = _is_win(g), _is_loss(g)
        if not won and not lost:
            continue

        # Who batted first decides which unit the margin is in. `batted_first`
        # is read off our own innings numbers, so it is right for a shared
        # fixture whichever club synced it.
        if g.get("batted_first"):
            if won and our > opp:
                by_runs.append(_row(
                    g, value=our - opp, unit="runs",
                    exact=bool(g["our_exact"] and g["opp_exact"]),
                ))
            elif lost:
                # We set a total and they passed it — we lost by their
                # wickets in hand, which is what the scoreboard says.
                wkts = g.get("wkts_taken")
                if wkts is not None and wkts <= ALL_OUT_WICKETS:
                    defeats_wickets.append(_row(
                        g, value=ALL_OUT_WICKETS - wkts, unit="wickets",
                        exact=bool(g["our_exact"] and g["opp_exact"]),
                    ))
        else:
            if won:
                wkts = g.get("wkts_lost")
                if wkts is not None and wkts <= ALL_OUT_WICKETS:
                    by_wickets.append(_row(
                        g, value=ALL_OUT_WICKETS - wkts, unit="wickets",
                        exact=bool(g["our_exact"] and g["opp_exact"]),
                    ))
            elif lost and opp > our:
                defeats_runs.append(_row(
                    g, value=opp - our, unit="runs",
                    exact=bool(g["our_exact"] and g["opp_exact"]),
                ))

    def _desc(rows):
        return sorted(rows, key=lambda r: (-r["value"], r["played_at"] or ""))

    return {
        "biggest_wins_runs": _board(_desc(by_runs)),
        "biggest_wins_wickets": _board(_desc(by_wickets)),
        "heaviest_defeats_runs": _board(_desc(defeats_runs)),
        "heaviest_defeats_wickets": _board(_desc(defeats_wickets)),
    }


def _streak_boards(games: list[dict]) -> dict:
    """Longest runs of wins, and of matches unbeaten.

    Games arrive in played order, which is why the pull is ordered rather
    than each board sorting for itself — a streak is the one record here
    that is about sequence rather than size.

    A DRAW BREAKS A WINNING STREAK BUT NOT AN UNBEATEN ONE, which is what
    makes the two boards different questions rather than one under two
    names. A washed-out fixture never reaches here at all (it has no result,
    so `our_games` drops it): it is not a match the club failed to win, and
    letting it end a streak would punish a club for the weather.
    """
    def _runs(keep) -> list[dict]:
        found, start = [], None
        for i, g in enumerate(games):
            if keep(g):
                if start is None:
                    start = i
            else:
                if start is not None:
                    found.append((start, i - 1))
                start = None
        if start is not None:
            found.append((start, len(games) - 1))

        out = []
        for a, b in found:
            span = games[a:b + 1]
            out.append({
                "value": len(span),
                "from": span[0].get("played_at"),
                "to": span[-1].get("played_at"),
                "from_season": span[0].get("season_name"),
                "to_season": span[-1].get("season_name"),
                "first_game_id": span[0].get("game_id"),
                "last_game_id": span[-1].get("game_id"),
                "wins": sum(1 for g in span if _is_win(g)),
                "draws": sum(1 for g in span if not _is_win(g) and not _is_loss(g)),
                # A streak is a span of games, not one figure read off a
                # scorecard, so it is exact whatever the totals were.
                "exact": True,
            })
        return sorted(out, key=lambda r: (-r["value"], r["from"] or ""))

    return {
        "longest_win_streak": _board(_runs(_is_win)),
        "longest_unbeaten_streak": _board(_runs(lambda g: not _is_loss(g))),
    }


def _season_boards(games: list[dict]) -> dict:
    """Per-season club performance.

    Win RATE is deliberately not ranked on its own board. A club that played
    two games and won both would top it forever, which says nothing about
    the season; the ranking is on wins, with the rate carried alongside so a
    reader can judge it.
    """
    by_season: dict[str, dict] = {}
    for g in games:
        sid = g.get("season_id")
        if not sid:
            continue
        s = by_season.setdefault(sid, {
            "season_id": sid,
            "season_name": g.get("season_name"),
            "season_year": g.get("season_year"),
            "played": 0, "wins": 0, "losses": 0, "draws": 0,
            "runs_for": 0, "runs_against": 0,
            "exact": True,
        })
        s["played"] += 1
        if _is_win(g):
            s["wins"] += 1
        elif _is_loss(g):
            s["losses"] += 1
        else:
            s["draws"] += 1
        if g.get("our_runs") is not None:
            s["runs_for"] += g["our_runs"]
            s["exact"] = s["exact"] and g["our_exact"]
        if g.get("opp_runs") is not None:
            s["runs_against"] += g["opp_runs"]
            s["exact"] = s["exact"] and g["opp_exact"]

    rows = []
    for s in by_season.values():
        s["win_rate"] = round(100.0 * s["wins"] / s["played"], 1) if s["played"] else 0.0
        rows.append(s)

    return {
        "best_seasons": _board(
            sorted(rows, key=lambda r: (-r["wins"], -r["win_rate"], r["season_name"] or ""))
        ),
    }


def assemble(games: list[dict]) -> dict:
    """Every board, plus what the club should know about the figures.

    `coverage` is not decoration. A club whose history is mostly bat-only
    sums is reading a record book whose totals are each 10-25 runs light,
    and the highest/lowest boards are skewed in OPPOSITE directions by it.
    Saying so — with the number of games and the fix — is the difference
    between a record book and a plausible-looking one.
    """
    scored = [g for g in games if g.get("our_runs") is not None]
    exact_games = sum(1 for g in scored if g.get("our_exact"))

    boards: dict = {}
    boards.update(_totals_boards(games))
    boards.update(_margin_boards(games))
    boards.update(_streak_boards(games))
    boards.update(_season_boards(games))

    return {
        "boards": boards,
        "summary": {
            "played": len(games),
            "wins": sum(1 for g in games if _is_win(g)),
            "losses": sum(1 for g in games if _is_loss(g)),
            "draws": sum(1 for g in games if not _is_win(g) and not _is_loss(g)),
            "seasons": len({g.get("season_id") for g in games if g.get("season_id")}),
        },
        "coverage": {
            "games_with_a_total": len(scored),
            "exact_totals": exact_games,
            "approximate_totals": len(scored) - exact_games,
            # Said in full rather than left to the reader to infer from two
            # counts: an approximate total is the batters' runs only, so it
            # sits BELOW the real score by however many extras were bowled.
            "note": (
                "A total is exact when the club holds the scorecard's own innings "
                "figure, which counts extras. Where it doesn't, the total is the "
                "batters' runs alone and so reads low by however many extras were "
                "bowled — which flatters a lowest-total record and undersells a "
                "highest one."
            ) if exact_games < len(scored) else None,
        },
    }


async def club_records(
    db: AsyncSession,
    org_id: str,
    *,
    season_ids: Optional[list] = None,
    grade_id: Optional[str] = None,
    grade_name_clause: str = "",
    finals_only: bool = False,
    scope_clause: str = "",
    extra_params: Optional[dict] = None,
) -> dict:
    """The club record book, from one per-game pull."""
    games = await per_game(
        db, org_id,
        season_ids=season_ids,
        grade_id=grade_id,
        grade_name_clause=grade_name_clause,
        finals_only=finals_only,
        scope_clause=scope_clause,
        extra_params=extra_params,
    )
    return assemble(games)
