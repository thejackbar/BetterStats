"""Raise a season total to the scorecards we hold, when CA's total has not caught up.

The profile header and the season table read Cricket Australia's own season
totals (`v_effective_player_season_stats`), which CA updates after the fact: a
game can show in "matches" and "recent matches" while its runs are still missing
from the total (reported: 453 runs beside a held innings of 3, which makes 456).
The scorecard is in our database the whole time.

So, per player and per season, where the scorecards we hold are a SUPERSET of
CA's batting (or bowling) block, the block is raised to what the scorecards add
up to. Never lowered: a club holds fewer scorecards than CA counted for most
seasons, and that must keep reading CA's figure.

A block is raised only when it is a superset, because the two sources can
disagree in other ways (a card with a stat line CA scored differently):
    batting  held innings >= CA's AND held runs >= CA's, one of them more
    bowling  held spells >= CA's AND wickets >= CA's AND runs conceded >= CA's, one more
Fielding has no such coupling (a catch is a catch), so each figure is raised on
its own.

Seasons are matched through the same fold the season table uses
(`aggregations._SEASON_FOLD_CTE`: winter and summer apart unless the club
amalgamates, a merge honoured, a shared fixture's foreign season folded onto the
club's own), so a figure lands on the row the player sees it under. Only seasons
the player's own club owns are considered: a held game filed under another
club's season that cannot be folded onto ours is not ours to add.

Only the unscoped path calls this. A grade/format/competition scope already reads
the scorecards.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.club_grades import club_game_sql

_NOT_AN_INNINGS = "LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent', 'did not bat', 'dnb')"

BAT_FIELDS = ("innings", "runs", "not_outs", "fifties", "hundreds", "ducks", "fours", "sixes")
BOWL_FIELDS = ("innings", "wickets", "runs", "maidens", "balls", "five_fors")
FIELD_FIELDS = ("catches", "catches_wk", "run_outs", "stumpings")


def _i(v) -> int:
    return int(v or 0)


async def season_topups(
    session: AsyncSession,
    player_id: str,
    org_id,
    season_ids: Optional[list] = None,
) -> dict[str, dict]:
    """Cached on the session for the life of a request: the profile asks three
    times (batting, bowling, fielding) and the answer cannot change in between.

    """
    cache = session.info.setdefault("_held_topups", {})
    key = (str(player_id), str(org_id), tuple(sorted(str(s) for s in season_ids)) if season_ids else None)
    if key not in cache:
        cache[key] = await _season_topups(session, player_id, org_id, season_ids)
    return cache[key]


async def _season_topups(
    session: AsyncSession,
    player_id: str,
    org_id,
    season_ids: Optional[list] = None,
) -> dict[str, dict]:
    """`{fold season id -> {bat, bowl, field, season_name, year}}` for seasons that need raising.

    Each of `bat` / `bowl` / `field` is a dict of non-negative deltas (and, for
    batting, the held `high_score`), or absent when that block needs nothing.
    Empty when nothing does, which is the common case.
    """
    if not org_id:
        return {}
    from app.services.aggregations import _SEASON_FOLD_CTE  # lazy: aggregations imports this module

    params = {"pid": str(player_id), "fold_org": str(org_id), "club_org": str(org_id)}
    fold = "WITH" + _SEASON_FOLD_CTE.rstrip()

    async def rows(sql: str):
        res = await session.execute(text(fold + "\n" + sql), params)
        return {str(r["sid"]): dict(r) for r in res.mappings()}

    ca_bat = await rows("""
        SELECT COALESCE(sf.fold_id, pss.season_id) AS sid,
               COALESCE(SUM(pss.batting_innings), 0) AS innings, COALESCE(SUM(pss.runs), 0) AS runs,
               COALESCE(SUM(pss.not_outs), 0) AS not_outs, COALESCE(SUM(pss.fifties), 0) AS fifties,
               COALESCE(SUM(pss.hundreds), 0) AS hundreds, COALESCE(SUM(pss.ducks), 0) AS ducks,
               COALESCE(SUM(pss.fours), 0) AS fours, COALESCE(SUM(pss.sixes), 0) AS sixes
        FROM v_effective_player_season_stats pss
        LEFT JOIN season_fold sf ON sf.raw_id = pss.season_id
        WHERE pss.player_id = CAST(:pid AS UUID) AND pss.season_id IS NOT NULL
        GROUP BY 1
    """)
    ca_bowl = await rows("""
        SELECT COALESCE(sf.fold_id, pss.season_id) AS sid,
               COALESCE(SUM(pss.bowling_innings), 0) AS innings, COALESCE(SUM(pss.wickets), 0) AS wickets,
               COALESCE(SUM(pss.runs_conceded), 0) AS runs, COALESCE(SUM(pss.maidens), 0) AS maidens,
               COALESCE(SUM(pss.bowling_balls), 0) AS balls,
               COALESCE(SUM(pss.five_wicket_innings), 0) AS five_fors
        FROM v_effective_player_season_stats pss
        LEFT JOIN season_fold sf ON sf.raw_id = pss.season_id
        WHERE pss.player_id = CAST(:pid AS UUID) AND pss.season_id IS NOT NULL
        GROUP BY 1
    """)
    ca_field = await rows("""
        SELECT COALESCE(sf.fold_id, pss.season_id) AS sid,
               COALESCE(SUM(pss.catches), 0) AS catches, COALESCE(SUM(pss.catches_wk), 0) AS catches_wk,
               COALESCE(SUM(pss.run_outs), 0) AS run_outs, COALESCE(SUM(pss.stumpings), 0) AS stumpings
        FROM v_effective_player_season_stats pss
        LEFT JOIN season_fold sf ON sf.raw_id = pss.season_id
        WHERE pss.player_id = CAST(:pid AS UUID) AND pss.season_id IS NOT NULL
        GROUP BY 1
    """)
    held_bat = await rows(f"""
        SELECT COALESCE(sf.fold_id, g.season_id) AS sid,
               COUNT(*) AS innings, COALESCE(SUM(bi.runs), 0) AS runs,
               COUNT(*) FILTER (WHERE bi.not_out) AS not_outs,
               COUNT(*) FILTER (WHERE bi.runs >= 50 AND bi.runs < 100) AS fifties,
               COUNT(*) FILTER (WHERE bi.runs >= 100) AS hundreds,
               COUNT(*) FILTER (WHERE bi.runs = 0 AND NOT COALESCE(bi.not_out, FALSE)) AS ducks,
               COALESCE(SUM(bi.fours), 0) AS fours, COALESCE(SUM(bi.sixes), 0) AS sixes,
               MAX(bi.runs) AS high_score
        FROM v_effective_batting_innings bi
        JOIN v_effective_games g ON g.id = bi.game_id
        LEFT JOIN season_fold sf ON sf.raw_id = g.season_id
        WHERE bi.player_id = CAST(:pid AS UUID) AND g.season_id IS NOT NULL
          AND bi.did_not_bat IS NOT TRUE AND {_NOT_AN_INNINGS}
          AND {club_game_sql('g')}
        GROUP BY 1
    """)
    held_bowl = await rows(f"""
        SELECT COALESCE(sf.fold_id, g.season_id) AS sid,
               COUNT(*) AS innings, COALESCE(SUM(bs.wickets), 0) AS wickets,
               COALESCE(SUM(bs.runs), 0) AS runs, COALESCE(SUM(bs.maidens), 0) AS maidens,
               COALESCE(SUM(FLOOR(bs.overs)::integer * 6
                            + ROUND((bs.overs - FLOOR(bs.overs)) * 10)::integer), 0) AS balls,
               COUNT(*) FILTER (WHERE bs.wickets >= 5) AS five_fors
        FROM v_effective_bowling_spells bs
        JOIN v_effective_games g ON g.id = bs.game_id
        LEFT JOIN season_fold sf ON sf.raw_id = g.season_id
        WHERE bs.player_id = CAST(:pid AS UUID) AND g.season_id IS NOT NULL
          AND {club_game_sql('g')}
        GROUP BY 1
    """)
    held_field = await rows(f"""
        SELECT COALESCE(sf.fold_id, g.season_id) AS sid,
               COALESCE(SUM(fs.catches), 0) AS catches, COALESCE(SUM(fs.catches_wk), 0) AS catches_wk,
               COALESCE(SUM(fs.run_outs), 0) AS run_outs, COALESCE(SUM(fs.stumpings), 0) AS stumpings
        FROM v_effective_fielding_stats fs
        JOIN v_effective_games g ON g.id = fs.game_id
        LEFT JOIN season_fold sf ON sf.raw_id = g.season_id
        WHERE fs.player_id = CAST(:pid AS UUID) AND g.season_id IS NOT NULL
          AND {club_game_sql('g')}
        GROUP BY 1
    """)

    held_games = await rows(f"""
        SELECT COALESCE(sf.fold_id, g.season_id) AS sid, COUNT(DISTINCT g.id) AS matches
        FROM v_effective_games g
        LEFT JOIN season_fold sf ON sf.raw_id = g.season_id
        WHERE g.season_id IS NOT NULL AND {club_game_sql('g')}
          AND g.id IN (
              SELECT bi.game_id FROM v_effective_batting_innings bi WHERE bi.player_id = CAST(:pid AS UUID)
              UNION
              SELECT bs.game_id FROM v_effective_bowling_spells bs WHERE bs.player_id = CAST(:pid AS UUID)
              UNION
              SELECT fs.game_id FROM v_effective_fielding_stats fs WHERE fs.player_id = CAST(:pid AS UUID))
        GROUP BY 1
    """)

    out: dict[str, dict] = {}
    for sid, h in held_bat.items():
        c = ca_bat.get(sid, {})
        if (_i(h["innings"]) >= _i(c.get("innings")) and _i(h["runs"]) >= _i(c.get("runs"))
                and (_i(h["innings"]) > _i(c.get("innings")) or _i(h["runs"]) > _i(c.get("runs")))):
            d = {f: max(_i(h[f]) - _i(c.get(f)), 0) for f in BAT_FIELDS}
            d["high_score"] = h["high_score"]
            out.setdefault(sid, {})["bat"] = d
    for sid, h in held_bowl.items():
        c = ca_bowl.get(sid, {})
        if (_i(h["innings"]) >= _i(c.get("innings")) and _i(h["wickets"]) >= _i(c.get("wickets"))
                and _i(h["runs"]) >= _i(c.get("runs"))
                and (_i(h["innings"]) > _i(c.get("innings")) or _i(h["wickets"]) > _i(c.get("wickets"))
                     or _i(h["runs"]) > _i(c.get("runs")))):
            out.setdefault(sid, {})["bowl"] = {f: max(_i(h[f]) - _i(c.get(f)), 0) for f in BOWL_FIELDS}
    for sid, h in held_field.items():
        c = ca_field.get(sid, {})
        d = {f: max(_i(h[f]) - _i(c.get(f)), 0) for f in FIELD_FIELDS}
        if any(d.values()):
            out.setdefault(sid, {})["field"] = d
    if not out:
        return {}

    # Only seasons the player's own club owns (see the module docstring), with
    # the name and year the season table needs to draw a row that is not there yet.
    meta = await session.execute(
        text("SELECT id::text AS id, name, year, organisation_id::text AS org FROM seasons"
             " WHERE id = ANY(CAST(:ids AS UUID[]))"),
        {"ids": list(out)},
    )
    own = {}
    for r in meta.mappings():
        if r["org"] == str(org_id):
            own[r["id"]] = r
    out = {sid: {**v, "season_name": own[sid]["name"], "year": own[sid]["year"],
                 "held_matches": _i(held_games.get(sid, {}).get("matches")),
                 "ca_has_row": sid in ca_bat or sid in ca_bowl or sid in ca_field}
           for sid, v in out.items() if sid in own}

    if season_ids:
        wanted = await session.execute(
            text(fold + "\nSELECT DISTINCT fold_id::text AS sid FROM season_fold"
                 " WHERE raw_id = ANY(CAST(:ids AS UUID[]))"),
            {**params, "ids": [str(s) for s in season_ids]},
        )
        keep = {r["sid"] for r in wanted.mappings()} | {str(s) for s in season_ids}
        out = {sid: v for sid, v in out.items() if sid in keep}
    return out


def _balls_of(overs) -> int:
    """Cricket-notation overs (10.2) to balls."""
    if overs is None:
        return 0
    whole = int(overs)
    return whole * 6 + int(round((float(overs) - whole) * 10))


def _overs_of(balls: int) -> float:
    return (balls // 6) + (balls % 6) / 10.0


def add_to_batting(career: dict, topups: dict) -> Optional[dict]:
    """Add the batting deltas to a career-batting dict in place; returns what was added."""
    total = {f: 0 for f in BAT_FIELDS}
    highs = []
    hit = False
    for t in topups.values():
        d = t.get("bat")
        if not d:
            continue
        hit = True
        for f in BAT_FIELDS:
            total[f] += d[f]
        if d.get("high_score") is not None:
            highs.append(d["high_score"])
    if not hit or not career:
        return None
    career["innings"] = _i(career.get("innings")) + total["innings"]
    career["total_runs"] = _i(career.get("total_runs")) + total["runs"]
    career["fifties"] = _i(career.get("fifties")) + total["fifties"]
    career["hundreds"] = _i(career.get("hundreds")) + total["hundreds"]
    career["ducks"] = _i(career.get("ducks")) + total["ducks"]
    career["total_fours"] = _i(career.get("total_fours")) + total["fours"]
    career["total_sixes"] = _i(career.get("total_sixes")) + total["sixes"]
    not_outs = _i(career.get("not_outs")) + total["not_outs"]
    career["not_outs"] = not_outs
    if highs:
        current = career.get("high_score")
        career["high_score"] = max([h for h in highs] + ([current] if current is not None else []))
    dismissals = career["innings"] - not_outs
    career["average"] = round(career["total_runs"] / dismissals, 2) if dismissals > 0 else None
    return {"innings": total["innings"], "runs": total["runs"]}


def add_to_bowling(career: dict, topups: dict) -> Optional[dict]:
    total = {f: 0 for f in BOWL_FIELDS}
    hit = False
    for t in topups.values():
        d = t.get("bowl")
        if not d:
            continue
        hit = True
        for f in BOWL_FIELDS:
            total[f] += d[f]
    if not hit or not career:
        return None
    career["total_wickets"] = _i(career.get("total_wickets")) + total["wickets"]
    career["total_runs"] = _i(career.get("total_runs")) + total["runs"]
    career["total_maidens"] = _i(career.get("total_maidens")) + total["maidens"]
    career["five_fors"] = _i(career.get("five_fors")) + total["five_fors"]
    career["bowling_innings"] = _i(career.get("bowling_innings")) + total["innings"]
    balls = _balls_of(career.get("total_overs")) + total["balls"]
    career["total_overs"] = _overs_of(balls)
    wk = career["total_wickets"]
    career["average"] = round(career["total_runs"] / wk, 2) if wk > 0 else None
    career["bowling_strike_rate"] = round(balls / wk, 2) if wk > 0 else None
    return {"spells": total["innings"], "wickets": total["wickets"]}


def add_to_fielding(career: dict, topups: dict) -> Optional[dict]:
    total = {f: 0 for f in FIELD_FIELDS}
    hit = False
    for t in topups.values():
        d = t.get("field")
        if not d:
            continue
        hit = True
        for f in FIELD_FIELDS:
            total[f] += d[f]
    if not hit or not career:
        return None
    career["total_catches"] = _i(career.get("total_catches")) + total["catches"]
    career["total_catches_wk"] = _i(career.get("total_catches_wk")) + total["catches_wk"]
    career["total_catches_non_wk"] = max(career["total_catches"] - career["total_catches_wk"], 0)
    career["total_run_outs"] = _i(career.get("total_run_outs")) + total["run_outs"]
    career["total_stumpings"] = _i(career.get("total_stumpings")) + total["stumpings"]
    career["total_dismissals"] = (career["total_catches"] + career["total_run_outs"]
                                  + career["total_stumpings"])
    return {"catches": total["catches"], "run_outs": total["run_outs"], "stumpings": total["stumpings"]}


def add_to_season_row(row: dict, t: dict) -> None:
    """Add one season's deltas to a season-by-season row (the keys `get_season_by_season` selects)."""
    d = t.get("bat")
    if d:
        row["batting_innings"] = _i(row.get("batting_innings")) + d["innings"]
        row["total_runs"] = _i(row.get("total_runs")) + d["runs"]
        row["not_outs"] = _i(row.get("not_outs")) + d["not_outs"]
        row["fifties"] = _i(row.get("fifties")) + d["fifties"]
        row["hundreds"] = _i(row.get("hundreds")) + d["hundreds"]
        row["ducks"] = _i(row.get("ducks")) + d["ducks"]
        row["total_fours"] = _i(row.get("total_fours")) + d["fours"]
        row["total_sixes"] = _i(row.get("total_sixes")) + d["sixes"]
        if d.get("high_score") is not None:
            row["high_score"] = max(d["high_score"], row["high_score"]) if row.get("high_score") is not None else d["high_score"]
        dismissals = row["batting_innings"] - row["not_outs"]
        row["batting_average"] = round(row["total_runs"] / dismissals, 2) if dismissals > 0 else None
        row["sr_of"] = row["batting_innings"]
    d = t.get("bowl")
    if d:
        row["econ_of"] = _i(row.get("econ_of")) + d["innings"]
        row["total_wickets"] = _i(row.get("total_wickets")) + d["wickets"]
        row["bowling_runs_conceded"] = _i(row.get("bowling_runs_conceded")) + d["runs"]
        row["total_maidens"] = _i(row.get("total_maidens")) + d["maidens"]
        row["five_fors"] = _i(row.get("five_fors")) + d["five_fors"]
        row["total_overs"] = _overs_of(_balls_of(row.get("total_overs")) + d["balls"])
        wk = row["total_wickets"]
        row["bowling_average"] = round(row["bowling_runs_conceded"] / wk, 2) if wk > 0 else None
    d = t.get("field")
    if d:
        row["total_catches"] = _i(row.get("total_catches")) + d["catches"]
        row["total_catches_wk"] = _i(row.get("total_catches_wk")) + d["catches_wk"]
        row["total_catches_non_wk"] = max(row["total_catches"] - row["total_catches_wk"], 0)
        row["total_run_outs"] = _i(row.get("total_run_outs")) + d["run_outs"]
        row["total_stumpings"] = _i(row.get("total_stumpings")) + d["stumpings"]
