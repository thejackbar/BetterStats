"""The totals a club holds only as totals, for the record book's filtered path.

A club's history-book import, a hand-typed season adjustment, the career
"Prior Seasons & Adjustments" lump and a season CA reports with no scorecards
behind it have no per-innings rows. The record book's filtered path (the
default grade lens for any club with a junior programme, a match type, a
competition) reads per-innings rows only, so every one of those figures dropped
off the board the moment a lens applied. Kalamunda's leading run scorer and
wicket takers were exactly that: history-book players.

The Leaderboard already adds them back (`aggregations._residual_totals_cte`).
This does the same for Records, with the SAME definition of what counts
(`aggregations._RESIDUAL_SOURCES`, `summary_only_seasons_clause`, the scope's
`aggregate` clause), and reads the request's own `_club_pss` copy rather than
the view again.

It only ever raises a figure. A player with no residual row keeps exactly the
row the board already gave them; a player with one is rebuilt from their
scorecards plus the residual, and a player with a residual and no scorecard in
scope is added.

`high_score_rows` is separate and runs on the unfiltered path too: the
Highest Individual Scores board is read from per-innings rows on BOTH paths, so
a high score typed against a season (Manual Entries, Adjustments) never reached
it whether a lens applied or not.
"""
from __future__ import annotations

from typing import Callable, Iterable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.club_grades import club_game_sql
from app.services.grade_scope import GradeScope
from app.services.summary_only_seasons import held_years_cte, summary_only_seasons_clause

# Same list the profile and the Leaderboard use. Kept as a literal copy only so
# this module does not import `aggregations` (which imports a lot); the check
# `verify_records_history_under_filters` asserts the two lists are equal.
RESIDUAL_SOURCES = ("manual_aggregate", "manual_career", "import")

_OURS = club_game_sql("g", "org_id")


def _row_filter(scope: Optional[GradeScope], residual_only: bool) -> tuple[str, str]:
    """(`WITH ...` prefix, WHERE fragment) for rows that exist only as totals.

    `residual_only` is for the high-score board, which also runs with no lens:
    there is no scorecard-versus-summary question without one, so only the
    three residual sources count and no held-years CTE is built.
    """
    active = bool(scope is not None and scope.active)
    scope_sql = scope.clause("pss.grade_id", "aggregate", label_column="pss.grade_label") if active else ""
    plain = f"pss.source = ANY(:residual_sources){scope_sql}"
    if residual_only or not active:
        return "", plain
    held = held_years_cte(
        f"{_OURS}{scope.clause('g.grade_id')}",
        lambda a: f"{a}.player_id = ANY(CAST(:club_player_ids AS uuid[]))",
        rels={"bi": "_club_bi", "bs": "_club_bs", "fs": "_club_fs", "ga": "_club_ga", "games": "_club_games"},
    )
    return f"WITH {held}", f"(({plain}) OR {summary_only_seasons_clause(scope)})"


async def load_totals(db: AsyncSession, scope: Optional[GradeScope], params: dict, *,
                      season_clause: str, gender_clause: str) -> dict[str, dict]:
    """Per player, the summed residual figures in scope. `params` must already
    bind `org_id` and `club_player_ids` (and the scope's own binds)."""
    held, where = _row_filter(scope, residual_only=False)
    p = dict(params)
    p["residual_sources"] = list(RESIDUAL_SOURCES)
    rows = (await db.execute(text(f"""
        {held}
        SELECT pss.player_id::text AS player_id,
               COALESCE(p.display_name_override, p.name) AS name,
               COALESCE(SUM(pss.matches), 0)          AS games,
               COALESCE(SUM(pss.batting_innings), 0)  AS innings,
               COALESCE(SUM(pss.runs), 0)             AS runs,
               COALESCE(SUM(pss.not_outs), 0)         AS not_outs,
               MAX(pss.high_score)                    AS high_score,
               COALESCE(SUM(pss.fifties), 0)          AS fifties,
               COALESCE(SUM(pss.hundreds), 0)         AS hundreds,
               COALESCE(SUM(pss.wickets), 0)          AS wickets,
               COALESCE(SUM(pss.runs_conceded), 0)    AS runs_conceded,
               COALESCE(SUM(pss.bowling_balls), 0)    AS balls,
               COALESCE(SUM(pss.five_wicket_innings), 0) AS five_fors
        FROM _club_pss pss
        JOIN players p ON p.id = pss.player_id
        WHERE p.organisation_id = :org_id
          AND pss.player_id = ANY(CAST(:club_player_ids AS uuid[])){season_clause}{gender_clause}
          AND {where}
        GROUP BY pss.player_id, COALESCE(p.display_name_override, p.name)
    """), p)).mappings().all()
    return {r["player_id"]: dict(r) for r in rows}


async def high_score_rows(db: AsyncSession, scope: Optional[GradeScope], params: dict, *,
                          season_clause: str, gender_clause: str, limit: int) -> list[dict]:
    """One row per residual season row that carries a high score, shaped like a
    row of the per-innings Highest Individual Scores board."""
    held, where = _row_filter(scope, residual_only=True)
    p = dict(params)
    p["residual_sources"] = list(RESIDUAL_SOURCES)
    p["hs_limit"] = limit
    rows = (await db.execute(text(f"""
        {held}
        SELECT pss.player_id::text AS player_id,
               COALESCE(p.display_name_override, p.name) AS name,
               pss.high_score AS runs,
               COALESCE(pss.is_hs_not_out, FALSE) AS not_out,
               s.name AS season_name
        FROM _club_pss pss
        JOIN players p ON p.id = pss.player_id
        LEFT JOIN seasons s ON s.id = pss.season_id
        WHERE p.organisation_id = :org_id
          AND pss.player_id = ANY(CAST(:club_player_ids AS uuid[])){season_clause}{gender_clause}
          AND pss.high_score IS NOT NULL AND pss.high_score > 0
          AND {where}
        ORDER BY pss.high_score DESC LIMIT :hs_limit
    """), p)).mappings().all()
    return [dict(r) for r in rows]


def merge_high_scores(rows: list[dict], extra: list[dict], limit: int) -> list[dict]:
    """The board's rows plus the typed ones, best first. A typed score that
    repeats an innings the scorecards already hold (same player, same runs, same
    not-out) is not added twice."""
    seen = {(r.get("player_id"), int(r.get("runs") or 0), bool(r.get("not_out"))) for r in rows}
    out = list(rows)
    for r in extra:
        key = (r.get("player_id"), int(r.get("runs") or 0), bool(r.get("not_out")))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    out.sort(key=lambda r: -(int(r.get("runs") or 0)))
    return out[:limit]


def _i(v) -> int:
    return int(v or 0)


def _div(n, d, places: int = 2):
    return round(float(n) / float(d), places) if d else None


def combine(bat: dict, bowl: dict, res: dict) -> dict:
    """One player's scorecard totals plus their residual, every derived figure
    recomputed from the summed counts (never an average of averages)."""
    runs = _i(bat.get("runs")) + _i(res.get("runs"))
    innings = _i(bat.get("innings")) + _i(res.get("innings"))
    not_outs = _i(bat.get("not_outs")) + _i(res.get("not_outs"))
    hs = [h for h in (bat.get("high_score"), res.get("high_score")) if h is not None]
    wickets = _i(bowl.get("wickets")) + _i(res.get("wickets"))
    conceded = _i(bowl.get("runs")) + _i(res.get("runs_conceded"))
    balls = _i(bowl.get("balls")) + _i(res.get("balls"))
    return {
        "runs": runs, "innings": innings, "not_outs": not_outs,
        "high_score": max(hs) if hs else None,
        "average": _div(runs, innings - not_outs),
        "fifties": _i(bat.get("fifties")) + _i(res.get("fifties")),
        "hundreds": _i(bat.get("hundreds")) + _i(res.get("hundreds")),
        "bat_matches": _i(bat.get("matches")) + _i(res.get("games")),
        "wickets": wickets, "conceded": conceded, "balls": balls,
        "bowl_average": _div(conceded, wickets),
        "economy": _div(conceded * 6, balls) if balls else None,
        "five_fors": _i(bowl.get("five_fors")) + _i(res.get("five_fors")),
        "bowl_matches": _i(bowl.get("matches")) + _i(res.get("games")),
    }


def _replace(board: list[dict], rows: dict[str, dict], keep: Callable[[dict], bool],
             sort_key: Callable[[dict], object], limit: int) -> list[dict]:
    """`board` with each residual player's row swapped for their combined row
    (dropped when it no longer qualifies), re-sorted and cut."""
    out = [r for r in board if r.get("player_id") not in rows]
    out.extend(r for r in rows.values() if keep(r))
    out.sort(key=sort_key)
    return out[:limit]


def apply(boards: dict[str, list[dict]], res: dict[str, dict], bat: dict[str, dict],
          bowl: dict[str, dict], limit: int) -> dict[str, list[dict]]:
    """Rebuild the career boards for the players in `res`. `boards` maps the
    board names `top_career_runs`, `top_batting_avg`, `most_fifties`,
    `most_hundreds`, `top_career_wickets`, `top_bowling_avg`, `most_five_fors`
    and `top_allrounders` to the rows the scorecards alone produced."""
    c: dict[str, dict] = {}
    for pid, r in res.items():
        c[pid] = {"player_id": pid, "name": r["name"], **combine(bat.get(pid, {}), bowl.get(pid, {}), r)}

    def row(pid: str, **cols) -> dict:
        return {"player_id": pid, "name": c[pid]["name"], **cols}

    out = dict(boards)
    out["top_career_runs"] = _replace(
        boards["top_career_runs"],
        {p: row(p, runs=x["runs"], innings=x["innings"], not_outs=x["not_outs"],
                matches=x["bat_matches"], high_score=x["high_score"], average=x["average"])
         for p, x in c.items()},
        lambda r: _i(r["runs"]) > 0, lambda r: -_i(r["runs"]), limit)
    out["top_batting_avg"] = _replace(
        boards["top_batting_avg"],
        {p: row(p, average=x["average"], runs=x["runs"], innings=x["innings"], matches=x["bat_matches"])
         for p, x in c.items()},
        lambda r: _i(r["innings"]) - _i(c[r["player_id"]]["not_outs"]) >= 10 and r["average"] is not None,
        lambda r: -(float(r["average"] or 0)), limit)
    out["most_fifties"] = _replace(
        boards["most_fifties"],
        {p: row(p, fifties=x["fifties"], runs=x["runs"], matches=x["bat_matches"]) for p, x in c.items()},
        lambda r: _i(r["fifties"]) > 0, lambda r: -_i(r["fifties"]), limit)
    out["most_hundreds"] = _replace(
        boards["most_hundreds"],
        {p: row(p, hundreds=x["hundreds"], runs=x["runs"], matches=x["bat_matches"]) for p, x in c.items()},
        lambda r: _i(r["hundreds"]) > 0, lambda r: -_i(r["hundreds"]), limit)
    out["top_career_wickets"] = _replace(
        boards["top_career_wickets"],
        {p: row(p, wickets=x["wickets"], matches=x["bowl_matches"], five_fors=x["five_fors"],
                average=x["bowl_average"], economy=x["economy"]) for p, x in c.items()},
        lambda r: _i(r["wickets"]) > 0, lambda r: -_i(r["wickets"]), limit)
    out["top_bowling_avg"] = _replace(
        boards["top_bowling_avg"],
        {p: row(p, average=x["bowl_average"], wickets=x["wickets"], matches=x["bowl_matches"])
         for p, x in c.items()},
        lambda r: _i(r["wickets"]) >= 20 and r["average"] is not None,
        lambda r: float(r["average"] or 0), limit)
    out["most_five_fors"] = _replace(
        boards["most_five_fors"],
        {p: row(p, five_fors=x["five_fors"], wickets=x["wickets"]) for p, x in c.items()},
        lambda r: _i(r["five_fors"]) > 0, lambda r: -_i(r["five_fors"]), limit)
    out["top_allrounders"] = _replace(
        boards["top_allrounders"],
        {p: row(p, runs=x["runs"], wickets=x["wickets"],
                matches=max(x["bat_matches"], x["bowl_matches"]),
                batting_average=x["average"], bowling_average=x["bowl_average"],
                index_score=round(x["runs"] * 1.5 + x["wickets"] * 10, 2))
         for p, x in c.items()},
        lambda r: _i(r["runs"]) >= 1000 and _i(r["wickets"]) >= 100,
        lambda r: -float(r["index_score"]), limit)
    return out
