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
-- ONE ROW PER INNINGS, NOT PER GAME, and that is the whole correction here.
-- A two-day match bats each side twice, so grouping by game alone reported a
-- club's "highest total" as its two innings ADDED TOGETHER — the reported
-- 8-323 and 8-158 reading as a 481 that was never scored. A total is an
-- innings; a match aggregate is a different record and gets its own board.
our_bat AS (
    -- OUR rows only. A both-synced fixture is ONE games row carrying BOTH
    -- clubs' innings, so without the player scope this sums the opposition's
    -- runs into ours and counts their dismissals as our wickets.
    SELECT bi.game_id, bi.innings_number,
           SUM(bi.runs) AS bat_runs,
           COUNT(*) FILTER (
               WHERE bi.did_not_bat IS NOT TRUE
                 AND NOT bi.not_out
                 AND bi.dismissal_type IS NOT NULL
           ) AS wkts_lost
    FROM v_effective_batting_innings bi
    JOIN our_games og ON og.id = bi.game_id
    JOIN players p ON p.id = bi.player_id AND p.organisation_id = CAST(:org AS UUID)
    WHERE bi.did_not_bat IS NOT TRUE
    GROUP BY bi.game_id, bi.innings_number
),
their_bat AS (
    -- The innings our bowlers bowled in — which is the opposition batting,
    -- and is knowable even in a match we never batted in at all. That case
    -- is exactly why this is its own CTE rather than "the innings we didn't
    -- bat in": a drawn two-day game where the other side batted once and we
    -- never got in had NO our-side innings to subtract from, so the whole
    -- exact-total path was skipped and the figure fell back to a bat sum.
    SELECT bs.game_id, bs.innings_number,
           SUM(bs.runs) AS bowl_runs,
           SUM(bs.wickets) AS wkts_taken
    FROM v_effective_bowling_spells bs
    JOIN our_games og ON og.id = bs.game_id
    JOIN players p ON p.id = bs.player_id AND p.organisation_id = CAST(:org AS UUID)
    GROUP BY bs.game_id, bs.innings_number
),
stored AS (
    -- GR's own per-innings figure: the batters' runs PLUS extras. Keyed on
    -- `innings_number`, which sync writes from GR's `inningsOrder` for BOTH
    -- this column and batting_innings/bowling_spells — so the three line up.
    SELECT og.id AS game_id,
           (elem->>'innings_number')::int AS innings_number,
           NULLIF(elem->>'runs_scored', '')::numeric AS runs_scored,
           NULLIF(elem->>'wickets', '')::numeric AS wickets,
           NULLIF(elem->>'extras', '')::numeric AS extras
    FROM our_games og,
         LATERAL jsonb_array_elements(COALESCE(og.innings_totals, '[]'::jsonb)) elem
)
SELECT og.id::text AS game_id, og.played_at, og.venue, og.opp_club_name,
       og.match_format, og.home_team, og.away_team, og.is_final,
       og.grade_id::text AS grade_id, og.grade_name,
       og.season_id::text AS season_id, og.season_name, og.season_year,
       og.result, og.our_venue,
       inn.side, inn.innings_number,
       inn.bat_runs, inn.stored_runs, inn.wkts, inn.stored_wkts, inn.extras
FROM our_games og
JOIN LATERAL (
    SELECT 'us'::text AS side, b.innings_number,
           b.bat_runs, st.runs_scored AS stored_runs,
           b.wkts_lost AS wkts, st.wickets AS stored_wkts, st.extras
    FROM our_bat b
    LEFT JOIN stored st ON st.game_id = b.game_id
                       AND st.innings_number = b.innings_number
    WHERE b.game_id = og.id
    UNION ALL
    SELECT 'them'::text, t.innings_number,
           t.bowl_runs, st.runs_scored,
           t.wkts_taken, st.wickets, st.extras
    FROM their_bat t
    LEFT JOIN stored st ON st.game_id = t.game_id
                       AND st.innings_number = t.innings_number
    WHERE t.game_id = og.id
) inn ON TRUE
ORDER BY og.played_at ASC, og.id ASC, inn.innings_number ASC
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
    """One row per game, each carrying its innings on both sides.

    The SQL returns one row per INNINGS; this folds them back into games.
    Doing the fold here rather than in SQL is what lets a match-level figure
    (a margin, a match aggregate) and an innings-level one (a total) come
    from the same read without either being re-derived.

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

    games: dict[str, dict] = {}
    order: list[str] = []
    for r in res.mappings():
        gid = r["game_id"]
        g = games.get(gid)
        if g is None:
            g = {
                "game_id": gid,
                "played_at": _fmt_date(r["played_at"]),
                "venue": r["venue"], "opp_club_name": r["opp_club_name"],
                "match_format": r["match_format"],
                "home_team": r["home_team"], "away_team": r["away_team"],
                "is_final": r["is_final"], "grade_id": r["grade_id"],
                "grade_name": r["grade_name"], "season_id": r["season_id"],
                "season_name": r["season_name"], "season_year": r["season_year"],
                "result": r["result"], "our_venue": r["our_venue"],
                "our_innings": [], "their_innings": [],
            }
            games[gid] = g
            order.append(gid)

        # The true figure where GR holds it, the bat/bowl sum where it does
        # not. `exact` rides on each INNINGS, because a match can genuinely
        # have one of each — a two-day game with only its first innings
        # backfilled — and a record book must never present the two as one
        # kind of number. See the module docstring.
        stored, wkts_stored = r["stored_runs"], r["stored_wkts"]
        exact = stored is not None
        runs = int(stored) if exact else (
            int(r["bat_runs"]) if r["bat_runs"] is not None else None)
        wkts = (int(wkts_stored) if exact and wkts_stored is not None
                else (int(r["wkts"]) if r["wkts"] is not None else None))
        if runs is None:
            continue
        # `bat_runs` is our batting sum on our side and our BOWLING sum on
        # theirs — the raw figure before the stored total is preferred. Kept
        # because the extras board needs to know whether the card reconciles,
        # which is a question about the rows we hold, not about the total.
        raw = int(r["bat_runs"]) if r["bat_runs"] is not None else None
        entry = {"innings_number": r["innings_number"], "runs": runs,
                 "wickets": wkts, "exact": exact,
                 "bowl_runs": raw if r["side"] != "us" else None,
                 "bat_runs": raw if r["side"] == "us" else None,
                 "extras": int(r["extras"]) if r["extras"] is not None else None}
        (g["our_innings"] if r["side"] == "us" else g["their_innings"]).append(entry)

    out: list[dict] = []
    for gid in order:
        g = games[gid]
        ours, theirs = g["our_innings"], g["their_innings"]
        # `batted_first` is read off our own lowest innings number, so it is
        # right for a shared fixture whichever club synced it.
        first_ours = min((i["innings_number"] for i in ours), default=None)
        first_theirs = min((i["innings_number"] for i in theirs), default=None)
        g["batted_first"] = (
            first_ours is not None
            and (first_theirs is None or first_ours < first_theirs))
        # Match-level sums, for the margin and match-aggregate boards. A
        # margin is a MATCH figure — in a two-innings game a side wins by the
        # difference of its two totals against the other's two, not of one
        # innings against one.
        g["our_runs"] = sum(i["runs"] for i in ours) if ours else None
        g["opp_runs"] = sum(i["runs"] for i in theirs) if theirs else None
        g["wkts_lost"] = (sum(i["wickets"] or 0 for i in ours) if ours else None)
        g["wkts_taken"] = (sum(i["wickets"] or 0 for i in theirs) if theirs else None)
        g["our_exact"] = bool(ours) and all(i["exact"] for i in ours)
        g["opp_exact"] = bool(theirs) and all(i["exact"] for i in theirs)
        out.append(g)
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
        # The MATCH figures, always — what the scoreboard read at the end.
        # An innings board additionally carries its own `value`,
        # `innings_number` and `innings_wickets`.
        "our_runs": g.get("our_runs"),
        "our_wickets": g.get("wkts_lost"),
        "opp_runs": g.get("opp_runs"),
        "opp_wickets": g.get("wkts_taken"),
        "our_innings_count": len(g.get("our_innings") or []),
        "their_innings_count": len(g.get("their_innings") or []),
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
    """Highest and lowest, for and against — PER INNINGS.

    A total is one innings. The reported bug was this ranking a two-day
    match's two innings added together (8-323 and 8-158 reading as 481), a
    score nobody made. The match aggregate is a real record too, and it is
    its own board below rather than being confused with this one.
    """
    ours, theirs = [], []
    for g in games:
        for i in g["our_innings"]:
            ours.append((g, i))
        for i in g["their_innings"]:
            theirs.append((g, i))

    def _row_of(g, i, **extra):
        return _row(g, value=i["runs"], exact=i["exact"],
                    innings_number=i["innings_number"],
                    innings_wickets=i["wickets"], **extra)

    def _desc(pairs):
        return sorted(pairs, key=lambda p: (-p[1]["runs"], p[0]["played_at"] or ""))

    def _asc(pairs):
        return sorted(pairs, key=lambda p: (p[1]["runs"], p[0]["played_at"] or ""))

    # A low-total board only takes completed innings — see ALL_OUT_WICKETS.
    # Without it, every short chase is a club record low.
    lowest = [p for p in ours if (p[1]["wickets"] or 0) >= ALL_OUT_WICKETS]
    bowled_out = [p for p in theirs if (p[1]["wickets"] or 0) >= ALL_OUT_WICKETS]

    return {
        "highest_totals": _board([_row_of(g, i) for g, i in _desc(ours)]),
        "lowest_totals": _board([_row_of(g, i) for g, i in _asc(lowest)]),
        "highest_conceded": _board([_row_of(g, i) for g, i in _desc(theirs)]),
        "lowest_conceded": _board([_row_of(g, i) for g, i in _asc(bowled_out)]),
    }


def _aggregate_boards(games: list[dict]) -> dict:
    """Match aggregates — the record the innings boards must not be.

    Asked for directly once the highest-total board was found to be summing
    a two-day match's innings: that IS a real record, it is just a different
    one. Two of them, because they answer different questions — the biggest
    total ONE side made across a match, and the most runs scored by BOTH
    sides in a match (the high-scoring-game record).
    """
    ours = [g for g in games if g.get("our_runs") is not None]
    both = [g for g in games
            if g.get("our_runs") is not None and g.get("opp_runs") is not None]

    # Only worth drawing where a match genuinely had more than one innings a
    # side — in a one-day competition the aggregate IS the total, and two
    # boards showing the same number twice is noise.
    multi = [g for g in ours if len(g["our_innings"]) > 1]

    by_ours = sorted(multi, key=lambda g: (-g["our_runs"], g["played_at"] or ""))
    by_match = sorted(both, key=lambda g: (-(g["our_runs"] + g["opp_runs"]),
                                           g["played_at"] or ""))
    return {
        "highest_match_totals": _board([
            _row(g, value=g["our_runs"], exact=g["our_exact"],
                 innings_count=len(g["our_innings"])) for g in by_ours]),
        "highest_match_aggregates": _board([
            _row(g, value=g["our_runs"] + g["opp_runs"],
                 exact=bool(g["our_exact"] and g["opp_exact"])) for g in by_match]),
    }


def _margin_boards(games: list[dict]) -> dict:
    """Winning and losing margins.

    A cricket margin is TWO different units and they are not comparable, so
    they are two boards rather than one mixed ranking: a side that bats
    first and defends wins BY RUNS, a side that chases wins BY WICKETS. Ten
    wickets and ten runs are not the same size of win, and ordering them
    together would put a nervy two-wicket win above a 200-run thrashing.

    A RUNS margin is a MATCH figure — in a two-innings game a side wins by
    the difference of its two totals against the other's two. A WICKETS
    margin is not: it is ten minus the wickets the chasing side lost in the
    innings it chased in, so it reads that LAST innings alone. Summing
    wickets across a two-day match gives up to twenty and a nonsense margin.
    """
    by_runs, by_wickets, defeats_runs, defeats_wickets = [], [], [], []

    def _last(innings):
        return max(innings, key=lambda i: i["innings_number"]) if innings else None

    for g in games:
        our, opp = g.get("our_runs"), g.get("opp_runs")
        if our is None or opp is None:
            continue
        won, lost = _is_win(g), _is_loss(g)
        if not won and not lost:
            continue
        exact = bool(g["our_exact"] and g["opp_exact"])

        if g.get("batted_first"):
            if won and our > opp:
                by_runs.append(_row(g, value=our - opp, unit="runs", exact=exact))
            elif lost:
                # We set a total and they passed it — the margin is their
                # wickets in hand at the end, which is what the scoreboard
                # says, so it reads their LAST innings.
                last = _last(g["their_innings"])
                w = last["wickets"] if last else None
                if w is not None and 0 <= w < ALL_OUT_WICKETS:
                    defeats_wickets.append(
                        _row(g, value=ALL_OUT_WICKETS - w, unit="wickets", exact=exact))
        else:
            if won:
                last = _last(g["our_innings"])
                w = last["wickets"] if last else None
                if w is not None and 0 <= w < ALL_OUT_WICKETS:
                    by_wickets.append(
                        _row(g, value=ALL_OUT_WICKETS - w, unit="wickets", exact=exact))
            elif lost and opp > our:
                defeats_runs.append(_row(g, value=opp - our, unit="runs", exact=exact))

    def _desc(rows):
        return sorted(rows, key=lambda r: (-r["value"], r["played_at"] or ""))

    return {
        "biggest_wins_runs": _board(_desc(by_runs)),
        "biggest_wins_wickets": _board(_desc(by_wickets)),
        "heaviest_defeats_runs": _board(_desc(defeats_runs)),
        "heaviest_defeats_wickets": _board(_desc(defeats_wickets)),
    }


def _chase_and_close_boards(games: list[dict]) -> dict:
    """The records a close finish makes, and the run chases.

    CricketStatz carries narrowest-margin and highest-successful-chase boards
    and they are among the most read of its match records; both fall out of
    the margin arithmetic already done above, so they cost one more pass
    rather than one more query.
    """
    narrow_runs, narrow_wkts, chases = [], [], []

    def _last(innings):
        return max(innings, key=lambda i: i["innings_number"]) if innings else None

    for g in games:
        our, opp = g.get("our_runs"), g.get("opp_runs")
        if our is None or opp is None or not _is_win(g):
            continue
        exact = bool(g["our_exact"] and g["opp_exact"])
        if g.get("batted_first"):
            if our > opp:
                narrow_runs.append(_row(g, value=our - opp, unit="runs", exact=exact))
        else:
            last = _last(g["our_innings"])
            w = last["wickets"] if last else None
            if w is not None and 0 <= w < ALL_OUT_WICKETS:
                narrow_wkts.append(
                    _row(g, value=ALL_OUT_WICKETS - w, unit="wickets", exact=exact))
            # A CHASE IS THE TARGET, NOT WHAT WE HAPPENED TO MAKE.
            # Ranking the runs scored batting last put a 9/437 against a
            # side who made 83 at the top of this board — a 437 nobody
            # chased. The record is the total we had to overhaul: their
            # whole match total, less anything we had already made before
            # the innings we chased in, plus the one run that wins it.
            if last is not None:
                before = sum(i["runs"] for i in g["our_innings"]
                             if i["innings_number"] < last["innings_number"])
                target = opp - before + 1
                if target > 0:
                    chases.append(_row(
                        g, value=target, exact=exact,
                        innings_number=last["innings_number"],
                        chased_with=last["runs"],
                        innings_wickets=last["wickets"]))

    return {
        "narrowest_wins_runs": _board(
            sorted(narrow_runs, key=lambda r: (r["value"], r["played_at"] or ""))),
        "narrowest_wins_wickets": _board(
            sorted(narrow_wkts, key=lambda r: (r["value"], r["played_at"] or ""))),
        "highest_chases": _board(
            sorted(chases, key=lambda r: (-r["value"], r["played_at"] or ""))),
    }


def _extras_board(games: list[dict]) -> dict:
    """Most extras in an innings we bowled — from cards that reconcile.

    Only OUR bowling innings: extras we gave away is a record about this
    club. What the opposition's bowlers sprayed is their business, and
    ranking the two together would make a club's worst discipline record
    depend on who it happened to play.

    THE RECONCILIATION TEST IS THE WHOLE BOARD. A partly-entered historical
    card carries the innings total and almost no individual rows, and
    whoever typed it in put the entire unaccounted balance into BYES — so
    `totalExtras` on those innings is not extras at all, it is the runs
    nobody wrote down. The reported case is a 215 with "163 extras", all
    byes, off ONE stored bowling row.

    A bowler is charged everything except byes, leg byes and penalties, so
    a complete card satisfies `bowlers' runs + extras >= the innings
    total`. A stub fails it by however much was never entered. That is a
    fact about the card rather than a threshold somebody picked, which is
    why it is the test rather than a cap on how big an extras figure may be.

    Silent where the club holds no stored innings figure at all — extras
    live only on GR's own innings total, so a bat-only history genuinely
    cannot answer this, and an empty board says so better than a wrong one.
    """
    rows = []
    for g in games:
        for i in g["their_innings"]:
            extras, runs, bowled = i.get("extras"), i.get("runs"), i.get("bowl_runs")
            if extras is None or runs is None or bowled is None:
                continue
            if bowled + extras < runs:
                continue  # the card does not add up; see above
            rows.append(_row(g, value=extras, exact=True,
                             innings_number=i["innings_number"],
                             innings_runs=runs))
    return {"most_extras_conceded": _board(
        sorted(rows, key=lambda r: (-r["value"], r["played_at"] or "")))}


def _opposition_board(games: list[dict]) -> dict:
    """Head to head, one row per club we have played.

    CricketStatz's single best team report, and the one thing on this page a
    club will actually go looking for by name. Ranked by matches played —
    who we play most is the question; win rate rides alongside so a reader
    can judge it without a second board that would rank a one-off 100%.
    """
    by_opp: dict[str, dict] = {}
    for g in games:
        opp = g.get("opp_club_name")
        if not opp:
            continue
        o = by_opp.setdefault(opp, {
            "opponent": opp, "played": 0, "wins": 0, "losses": 0, "draws": 0,
            "runs_for": 0, "runs_against": 0, "exact": True,
            "first": g.get("played_at"), "last": g.get("played_at"),
        })
        o["played"] += 1
        if _is_win(g):
            o["wins"] += 1
        elif _is_loss(g):
            o["losses"] += 1
        else:
            o["draws"] += 1
        if g.get("our_runs") is not None:
            o["runs_for"] += g["our_runs"]
            o["exact"] = o["exact"] and g["our_exact"]
        if g.get("opp_runs") is not None:
            o["runs_against"] += g["opp_runs"]
            o["exact"] = o["exact"] and g["opp_exact"]
        if g.get("played_at"):
            o["last"] = g["played_at"]

    rows = []
    for o in by_opp.values():
        o["win_rate"] = round(100.0 * o["wins"] / o["played"], 1) if o["played"] else 0.0
        rows.append(o)
    return {"head_to_head": _board(
        sorted(rows, key=lambda r: (-r["played"], -r["wins"], r["opponent"])))}


def _streak_boards(games: list[dict]) -> dict:
    """Longest runs of wins, and of matches unbeaten.

    Games arrive in played order, which is why the pull is ordered rather
    than each board sorting for itself — a streak is the one record here
    that is about sequence rather than size.

    A DRAW BREAKS A WINNING STREAK BUT NOT AN UNBEATEN ONE, and it breaks a
    LOSING streak too — a side that did not lose did not lose, however
    little it won. That is what makes these three different questions
    rather than one under three names. A washed-out fixture never reaches here at all (it has no result,
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
            grades = []
            for gm in span:
                gn = gm.get("grade_name")
                if gn and gn not in grades:
                    grades.append(gn)
            out.append({
                "value": len(span),
                "from": span[0].get("played_at"),
                "to": span[-1].get("played_at"),
                # WHICH GRADES THE RUN CROSSED. Unfiltered, a streak is the
                # club's whole fixture list in date order, so a run can hop
                # between grades on the same weekend and read as a mystery.
                # Naming them makes it checkable, and the grade filter above
                # the board narrows it to one when that is the question.
                "grades": grades,
                "opponents": [gm.get("opp_club_name") for gm in span],
                "from_season": span[0].get("season_name"),
                "to_season": span[-1].get("season_name"),
                "first_game_id": span[0].get("game_id"),
                "last_game_id": span[-1].get("game_id"),
                "wins": sum(1 for g in span if _is_win(g)),
                "losses": sum(1 for g in span if _is_loss(g)),
                "draws": sum(1 for g in span if not _is_win(g) and not _is_loss(g)),
                # A streak is a span of games, not one figure read off a
                # scorecard, so it is exact whatever the totals were.
                "exact": True,
            })
        return sorted(out, key=lambda r: (-r["value"], r["from"] or ""))

    return {
        "longest_win_streak": _board(_runs(_is_win)),
        "longest_unbeaten_streak": _board(_runs(lambda g: not _is_loss(g))),
        # Asked for alongside the other two. A club's worst run is a record
        # it will happily quote, and leaving it out while showing the best
        # one reads as the record book flattering the club.
        "longest_losing_streak": _board(_runs(_is_loss)),
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
    boards.update(_aggregate_boards(games))
    boards.update(_margin_boards(games))
    boards.update(_chase_and_close_boards(games))
    boards.update(_extras_board(games))
    boards.update(_opposition_board(games))
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
