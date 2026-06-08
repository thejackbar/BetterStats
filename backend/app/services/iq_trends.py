"""BetterIQ — Player trends & development (master-plan Phase 3).

Read-only analytics over data the Core already holds:
- **Trajectories**: a player's season-by-season batting/bowling, oldest→newest.
- **Breakout / decline detection**: latest season vs the player's prior-career
  baseline, flagged when the swing is large enough on a meaningful sample.
- **Milestone forecasting**: who's N runs / wickets / games / catches from the
  next round milestone (reuses ``milestone_rules`` + ``get_upcoming_milestones``).

Reuses ``aggregations`` (career + season-by-season) and ``milestone_rules`` so
the numbers match the rest of the app exactly. Org-scoping for the club-wide
"movers" goes through ``seasons.organisation_id``.
"""
from __future__ import annotations

import math
import statistics

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.aggregations import (
    get_bowling_by_batter_position,
    get_bowling_dismissal_breakdown,
    get_career_batting,
    get_career_bowling,
    get_career_fielding,
    get_player_by_venue,
    get_season_by_season,
    get_upcoming_milestones_for_org,
)
from app.services import milestone_rules

# A "mover" needs enough of a recent sample to be real, and enough prior history
# to have a baseline — otherwise a hot week looks like a breakout.
_MIN_RECENT_BAT_INNS = 5
_MIN_PRIOR_BAT_INNS = 10
_MIN_RECENT_WKTS = 6
_MIN_PRIOR_WKTS = 15
# Swing thresholds (ratio of latest-season average to prior baseline).
_BAT_RISE, _BAT_FALL = 1.35, 0.70   # batting: higher avg = better
_BOWL_RISE, _BOWL_FALL = 0.75, 1.40  # bowling: lower avg = better


def _bat_avg(runs: int, inns: int, not_outs: int) -> float | None:
    outs = inns - not_outs
    return round(runs / outs, 2) if outs > 0 else None


async def _current_season_year(session: AsyncSession, org_id: str) -> int | None:
    """The most recent season year for which the club actually has stats — used
    to keep trend surfaces to *current* players only (not anyone ever active)."""
    r = await session.execute(
        text(
            "SELECT MAX(s.year) FROM seasons s "
            "JOIN player_season_stats pss ON pss.season_id = s.id "
            "WHERE s.organisation_id = CAST(:org AS UUID)"
        ),
        {"org": org_id},
    )
    return r.scalar()


def _movers_src(grade_id: str | None) -> str:
    """FROM-fragment for the mover/emerging queries, aliased ``st``. Whole-club
    reads the season-aggregate table; a grade filter reads the per-(player, season,
    grade) table for that grade NAME. Both expose batting_innings / runs /
    not_outs / wickets / runs_conceded, so the rest of the query is identical."""
    if grade_id:
        return "player_season_grade_stats st JOIN grades gr ON gr.id = st.grade_id AND gr.name = :grade"
    return "player_season_stats st"


async def _batting_movers(session: AsyncSession, org_id: str, target_year: int, grade_id: str | None = None) -> dict:
    """Players whose batting average in the TARGET season diverges sharply from
    their prior-career baseline (their record in the seasons before it)."""
    res = await session.execute(
        text(
            f"""
            WITH rows AS (
                SELECT st.player_id, s.year,
                       COALESCE(st.batting_innings, 0) AS inns,
                       COALESCE(st.runs, 0) AS runs,
                       COALESCE(st.not_outs, 0) AS not_outs
                FROM {_movers_src(grade_id)}
                JOIN seasons s ON s.id = st.season_id
                WHERE s.organisation_id = CAST(:org AS UUID)
            ),
            latest AS (
                SELECT player_id, SUM(inns) AS inns, SUM(runs) AS runs, SUM(not_outs) AS not_outs
                FROM rows WHERE year = :cur GROUP BY player_id
            ),
            prior AS (
                SELECT player_id, SUM(inns) AS inns, SUM(runs) AS runs, SUM(not_outs) AS not_outs
                FROM rows WHERE year < :cur GROUP BY player_id
            )
            SELECT p.id::text AS id, COALESCE(p.display_name_override, p.name) AS name,
                   l.inns AS latest_inns, l.runs AS latest_runs, l.not_outs AS latest_not_outs,
                   pr.inns AS prior_inns, pr.runs AS prior_runs, pr.not_outs AS prior_not_outs
            FROM latest l
            JOIN players p ON p.id = l.player_id AND p.status = 'active'
            JOIN prior pr ON pr.player_id = l.player_id
            WHERE l.inns >= :min_recent AND pr.inns >= :min_prior
            """
        ),
        {"org": org_id, "cur": target_year, "grade": grade_id,
         "min_recent": _MIN_RECENT_BAT_INNS, "min_prior": _MIN_PRIOR_BAT_INNS},
    )
    risers, fallers = [], []
    for r in res.mappings():
        latest = _bat_avg(r["latest_runs"], r["latest_inns"], r["latest_not_outs"])
        baseline = _bat_avg(r["prior_runs"], r["prior_inns"], r["prior_not_outs"])
        if not latest or not baseline:
            continue
        row = {
            "player_id": r["id"], "name": r["name"], "latest_year": target_year,
            "latest": latest, "baseline": baseline,
            "delta": round(latest - baseline, 2), "latest_inns": r["latest_inns"],
        }
        if latest >= baseline * _BAT_RISE:
            risers.append(row)
        elif latest <= baseline * _BAT_FALL:
            fallers.append(row)
    risers.sort(key=lambda x: x["delta"], reverse=True)
    fallers.sort(key=lambda x: x["delta"])
    return {"risers": risers[:6], "fallers": fallers[:6]}


async def _bowling_movers(session: AsyncSession, org_id: str, target_year: int, grade_id: str | None = None) -> dict:
    """Players whose bowling average in the TARGET season diverges sharply from
    their prior-career baseline (lower is better)."""
    res = await session.execute(
        text(
            f"""
            WITH rows AS (
                SELECT st.player_id, s.year,
                       COALESCE(st.wickets, 0) AS wkts,
                       COALESCE(st.runs_conceded, 0) AS runs
                FROM {_movers_src(grade_id)}
                JOIN seasons s ON s.id = st.season_id
                WHERE s.organisation_id = CAST(:org AS UUID)
            ),
            latest AS (SELECT player_id, SUM(wkts) AS wkts, SUM(runs) AS runs FROM rows WHERE year = :cur GROUP BY player_id),
            prior AS (SELECT player_id, SUM(wkts) AS wkts, SUM(runs) AS runs FROM rows WHERE year < :cur GROUP BY player_id)
            SELECT p.id::text AS id, COALESCE(p.display_name_override, p.name) AS name,
                   l.wkts AS latest_wkts, l.runs AS latest_runs,
                   pr.wkts AS prior_wkts, pr.runs AS prior_runs
            FROM latest l
            JOIN players p ON p.id = l.player_id AND p.status = 'active'
            JOIN prior pr ON pr.player_id = l.player_id
            WHERE l.wkts >= :min_recent AND pr.wkts >= :min_prior
            """
        ),
        {"org": org_id, "cur": target_year, "grade": grade_id,
         "min_recent": _MIN_RECENT_WKTS, "min_prior": _MIN_PRIOR_WKTS},
    )
    risers, fallers = [], []
    for r in res.mappings():
        latest = round(r["latest_runs"] / r["latest_wkts"], 2) if r["latest_wkts"] else None
        baseline = round(r["prior_runs"] / r["prior_wkts"], 2) if r["prior_wkts"] else None
        if not latest or not baseline:
            continue
        row = {
            "player_id": r["id"], "name": r["name"], "latest_year": target_year,
            "latest": latest, "baseline": baseline,
            "delta": round(latest - baseline, 2), "latest_wkts": r["latest_wkts"],
        }
        if latest <= baseline * _BOWL_RISE:
            risers.append(row)       # improving = average dropped
        elif latest >= baseline * _BOWL_FALL:
            fallers.append(row)
    risers.sort(key=lambda x: x["delta"])           # most-improved = biggest drop
    fallers.sort(key=lambda x: x["delta"], reverse=True)
    return {"risers": risers[:6], "fallers": fallers[:6]}


async def _emerging(session: AsyncSession, org_id: str, target_year: int, grade_id: str | None = None) -> list[dict]:
    """Ones to watch — players in their first few seasons (≤3) with a strong
    target season (short history + meaningful output that year)."""
    res = await session.execute(
        text(
            f"""
            WITH rows AS (
                SELECT st.player_id, s.year,
                       COALESCE(st.runs, 0) AS runs, COALESCE(st.wickets, 0) AS wkts
                FROM {_movers_src(grade_id)}
                JOIN seasons s ON s.id = st.season_id
                WHERE s.organisation_id = CAST(:org AS UUID)
            ),
            agg AS (
                SELECT player_id,
                       SUM(runs) FILTER (WHERE year = :cur) AS runs,
                       SUM(wkts) FILTER (WHERE year = :cur) AS wkts,
                       COUNT(DISTINCT year) FILTER (WHERE year <= :cur) AS seasons
                FROM rows GROUP BY player_id
            )
            SELECT p.id::text AS id, COALESCE(p.display_name_override, p.name) AS name,
                   a.runs, a.wkts, a.seasons
            FROM agg a JOIN players p ON p.id = a.player_id AND p.status = 'active'
            WHERE a.seasons <= 3 AND (a.runs >= 200 OR a.wkts >= 8)
            ORDER BY (COALESCE(a.runs, 0) + COALESCE(a.wkts, 0) * 18) DESC
            LIMIT 6
            """
        ),
        {"org": org_id, "cur": target_year, "grade": grade_id},
    )
    return [
        {"player_id": x["id"], "name": x["name"], "latest_year": target_year,
         "runs": x["runs"] or 0, "wickets": x["wkts"] or 0, "seasons": x["seasons"]}
        for x in res.mappings()
    ]


async def _player_recent(session: AsyncSession, player_id: str, n: int = 10) -> dict:
    """A player's last-N innings (runs) and spells (wickets), chronological, for sparklines."""
    bat = await session.execute(
        text(
            """
            SELECT bi.runs, bi.not_out FROM v_effective_batting_innings bi
            JOIN v_effective_games g ON g.id = bi.game_id
            WHERE bi.player_id = CAST(:pid AS UUID) AND bi.did_not_bat IS NOT TRUE AND bi.runs IS NOT NULL
            ORDER BY g.played_at DESC NULLS LAST, bi.id DESC LIMIT :n
            """
        ),
        {"pid": player_id, "n": n},
    )
    bat_rows = list(bat.mappings())[::-1]
    bowl = await session.execute(
        text(
            """
            SELECT bs.wickets FROM v_effective_bowling_spells bs
            JOIN v_effective_games g ON g.id = bs.game_id
            WHERE bs.player_id = CAST(:pid AS UUID)
            ORDER BY g.played_at DESC NULLS LAST, bs.id DESC LIMIT :n
            """
        ),
        {"pid": player_id, "n": n},
    )
    bowl_rows = list(bowl.mappings())[::-1]
    return {
        "batting": [{"runs": r["runs"], "not_out": bool(r["not_out"])} for r in bat_rows],
        "bowling": [r["wickets"] or 0 for r in bowl_rows],
    }


def _eta_games(needed: int, total: int | None, games: int | None) -> int | None:
    """Estimate games until a milestone at the player's career per-game rate."""
    if not games or not total or needed <= 0:
        return None
    per_game = total / games
    return max(1, math.ceil(needed / per_game)) if per_game > 0 else None


def _peak_and_consistency(seasons: list[dict]):
    bat_seasons = [s for s in seasons if (s.get("batting_innings") or 0) >= 3 and s.get("batting_average") is not None]
    bat_peak = max(seasons, key=lambda s: (s.get("total_runs") or 0), default=None)
    bowl_peak = max(seasons, key=lambda s: (s.get("total_wickets") or 0), default=None)
    consistency = round(statistics.pstdev([float(s["batting_average"]) for s in bat_seasons]), 1) if len(bat_seasons) >= 3 else None
    peak = {
        "batting": ({"season": bat_peak["season_name"], "runs": bat_peak.get("total_runs"), "average": bat_peak.get("batting_average")}
                    if bat_peak and (bat_peak.get("total_runs") or 0) > 0 else None),
        "bowling": ({"season": bowl_peak["season_name"], "wickets": bowl_peak.get("total_wickets"), "average": bowl_peak.get("bowling_average")}
                    if bowl_peak and (bowl_peak.get("total_wickets") or 0) > 0 else None),
    }
    return peak, consistency


def _role_evolution(seasons: list[dict]) -> str | None:
    """Bat vs bowl contribution in the first vs most-recent third of a career."""
    if len(seasons) < 4:
        return None
    third = max(1, len(seasons) // 3)

    def share(rows):
        runs = sum(s.get("total_runs") or 0 for s in rows)
        wkt_units = sum(s.get("total_wickets") or 0 for s in rows) * 20
        tot = runs + wkt_units
        return (wkt_units / tot) if tot else 0.0

    e, r = share(seasons[:third]), share(seasons[-third:])
    if r - e > 0.18:
        return "Increasingly a bowler"
    if e - r > 0.18:
        return "Increasingly a batter"
    return None


async def trends_overview(session: AsyncSession, org_id: str, season_id: str | None = None, grade_id: str | None = None) -> dict:
    """Club-wide development snapshot: breakout/decline movers + emerging for the
    SELECTED season (default: latest with stats) and optionally one grade. Movers
    compare that season to each player's prior-career baseline. (Milestones moved
    to the notification bell.)"""
    target_year = None
    if season_id:
        r = await session.execute(text("SELECT year FROM seasons WHERE id = CAST(:sid AS UUID)"), {"sid": season_id})
        target_year = r.scalar()
    if target_year is None:
        target_year = await _current_season_year(session, org_id)
    if target_year is None:
        return {"current_year": None, "season_year": None, "grade": grade_id, "milestones": [],
                "batting": {"risers": [], "fallers": []}, "bowling": {"risers": [], "fallers": []}, "emerging": []}
    milestones = await get_upcoming_milestones_for_org(session, org_id, limit=12)
    batting = await _batting_movers(session, org_id, target_year, grade_id)
    bowling = await _bowling_movers(session, org_id, target_year, grade_id)
    emerging = await _emerging(session, org_id, target_year, grade_id)
    return {
        "current_year": target_year,
        "season_year": target_year,
        "grade": grade_id,
        "milestones": milestones,
        "batting": batting,
        "bowling": bowling,
        "emerging": emerging,
    }


def _verdict(latest: float | None, baseline: float | None, *, lower_better: bool) -> str | None:
    """Coarse trend label for an individual's latest season vs prior baseline."""
    if latest is None or not baseline:
        return None
    rise, fall = (_BOWL_RISE, _BOWL_FALL) if lower_better else (_BAT_RISE, _BAT_FALL)
    if lower_better:
        if latest <= baseline * rise:
            return "rising"
        if latest >= baseline * fall:
            return "declining"
    else:
        if latest >= baseline * rise:
            return "rising"
        if latest <= baseline * fall:
            return "declining"
    return "steady"


async def player_trend(session: AsyncSession, org_id: str, player_id: str) -> dict | None:
    """One player's trajectory: season-by-season, career totals, next milestones
    and a coarse rising/declining verdict."""
    # Confirm the player is in this org (don't leak cross-club).
    prow = await session.execute(
        text(
            "SELECT COALESCE(display_name_override, name) AS name, status"
            " FROM players WHERE id = CAST(:pid AS UUID) AND organisation_id = CAST(:org AS UUID)"
        ),
        {"pid": player_id, "org": org_id},
    )
    p = prow.mappings().first()
    if not p:
        return None

    seasons_desc = await get_season_by_season(session, player_id)
    # Chronological (oldest→newest) for trajectory charts.
    seasons = list(reversed(seasons_desc))

    batting = await get_career_batting(session, player_id)
    bowling = await get_career_bowling(session, player_id)
    fielding = await get_career_fielding(session, player_id)

    # Next milestones from career totals.
    def _milestone(mt: str, category: str, current: int | None):
        cur = int(current or 0)
        target = milestone_rules.next_threshold(mt, cur)
        if not target:
            return None
        return {"type": mt, "category": category, "current": cur,
                "target": target, "needed": target - cur}

    milestones = [
        m for m in [
            _milestone("runs", "batting", (batting or {}).get("total_runs")),
            _milestone("wickets", "bowling", (bowling or {}).get("total_wickets")),
            _milestone("matches", "matches", (batting or {}).get("games")),
            _milestone("catches", "fielding", (fielding or {}).get("total_catches")),
        ] if m
    ]
    milestones.sort(key=lambda m: m["needed"])
    games = (batting or {}).get("games") or 0
    _totals = {
        "runs": (batting or {}).get("total_runs"),
        "wickets": (bowling or {}).get("total_wickets"),
        "catches": (fielding or {}).get("total_catches"),
    }
    for m in milestones:
        m["eta_games"] = m["needed"] if m["type"] == "matches" else _eta_games(m["needed"], _totals.get(m["type"]), games)

    # Verdict: latest season vs the prior-career baseline (needs ≥2 seasons).
    bat_verdict = bowl_verdict = None
    if len(seasons) >= 2:
        latest = seasons[-1]
        prior = seasons[:-1]
        # batting
        p_runs = sum(s.get("total_runs") or 0 for s in prior)
        p_inns = sum(s.get("batting_innings") or 0 for s in prior)
        p_no = sum(s.get("not_outs") or 0 for s in prior)
        base_bat = _bat_avg(p_runs, p_inns, p_no)
        if (latest.get("batting_innings") or 0) >= _MIN_RECENT_BAT_INNS and p_inns >= _MIN_PRIOR_BAT_INNS:
            bat_verdict = _verdict(latest.get("batting_average"), base_bat, lower_better=False)
        # bowling
        p_wkts = sum(s.get("total_wickets") or 0 for s in prior)
        p_conc = sum(s.get("bowling_runs_conceded") or 0 for s in prior)
        base_bowl = round(p_conc / p_wkts, 2) if p_wkts else None
        if (latest.get("total_wickets") or 0) >= _MIN_RECENT_WKTS and p_wkts >= _MIN_PRIOR_WKTS:
            bowl_verdict = _verdict(latest.get("bowling_average"), base_bowl, lower_better=True)

    recent_form = await _player_recent(session, player_id)
    peak, consistency = _peak_and_consistency(seasons)
    role_evolution = _role_evolution(seasons)

    return {
        "player": {"player_id": player_id, "name": p["name"], "active": p["status"] == "active"},
        "seasons": seasons,
        "career": {"batting": batting, "bowling": bowling, "fielding": fielding},
        "milestones": milestones,
        "verdict": {"batting": bat_verdict, "bowling": bowl_verdict},
        "recent_form": recent_form,
        "peak": peak,
        "consistency": consistency,
        "role_evolution": role_evolution,
    }


# ─── Player deep-dive (analytics brief §1.4/1.5/1.9/1.10) ─────────────────────

_DISM_MAP = {
    # Sync stores short codes ("c"/"b"/"st"); accept both short and long forms.
    "c": "caught", "caught": "caught",
    "caught behind": "caught behind", "caught keeper": "caught behind",
    "c&b": "caught & bowled", "caught and bowled": "caught & bowled", "caught & bowled": "caught & bowled",
    "b": "bowled", "bowled": "bowled",
    "lbw": "lbw", "leg before wicket": "lbw",
    "run out": "run out",
    "st": "stumped", "stumped": "stumped",
    "hit wicket": "hit wicket",
}
_POS_BUCKETS = [("Opening", 1, 2), ("First drop", 3, 3), ("Middle order", 4, 6), ("Lower order", 7, 8), ("Tail", 9, 11)]


def _dism_label(dt: str | None, caught_behind: bool | None = False) -> str | None:
    d = (dt or "").strip().lower()
    if not d or "not out" in d:
        return None
    if caught_behind and (d == "c" or d.startswith("c ") or d == "caught" or "caught behind" in d):
        return "caught behind"
    return _DISM_MAP.get(d, d)


def _percentile(sorted_vals: list[int], q: float):
    if not sorted_vals:
        return None
    idx = min(len(sorted_vals) - 1, max(0, int(round(q * (len(sorted_vals) - 1)))))
    return sorted_vals[idx]


async def _similar_players(session: AsyncSession, org_id: str, player_id: str) -> list[dict]:
    """Similar player search (brief §15.8) — club-internal nearest neighbour over
    a career stat profile (bat avg, bat SR, bowl avg, economy), z-scored across
    the squad and compared only on features both players have."""
    res = await session.execute(
        text(
            """
            SELECT p.id::text AS id, COALESCE(p.display_name_override, p.name) AS name,
                   COALESCE(SUM(pss.matches), 0) AS m,
                   COALESCE(SUM(pss.runs), 0) AS runs,
                   COALESCE(SUM(pss.balls_faced), 0) AS bf,
                   SUM(CASE WHEN pss.batting_average IS NOT NULL THEN pss.batting_average * pss.batting_innings ELSE 0 END) AS bavg_w,
                   SUM(CASE WHEN pss.batting_average IS NOT NULL THEN pss.batting_innings ELSE 0 END) AS bavg_n,
                   COALESCE(SUM(pss.wickets), 0) AS wkts,
                   COALESCE(SUM(pss.runs_conceded), 0) AS rc,
                   COALESCE(SUM(pss.bowling_balls), 0) AS bb
            FROM players p
            JOIN player_season_stats pss ON pss.player_id = p.id
            WHERE p.organisation_id = CAST(:org AS UUID)
            GROUP BY p.id, name
            HAVING COALESCE(SUM(pss.matches), 0) >= 5
            """
        ),
        {"org": org_id},
    )
    pls: dict[str, dict] = {}
    for r in res.mappings():
        f = {
            "bat_avg": float(r["bavg_w"] / r["bavg_n"]) if r["bavg_n"] else None,
            "bat_sr": float(r["runs"] * 100 / r["bf"]) if r["bf"] else None,
            "bowl_avg": float(r["rc"] / r["wkts"]) if r["wkts"] else None,
            "econ": float(r["rc"] * 6 / r["bb"]) if r["bb"] else None,
        }
        pls[r["id"]] = {
            "id": r["id"], "name": r["name"], "matches": int(r["m"] or 0),
            "bat_avg": round(f["bat_avg"], 1) if f["bat_avg"] is not None else None,
            "bowl_avg": round(f["bowl_avg"], 1) if f["bowl_avg"] is not None else None,
            "f": f,
        }
    if player_id not in pls:
        return []
    feats = ["bat_avg", "bat_sr", "bowl_avg", "econ"]
    popstats: dict[str, tuple[float, float]] = {}
    for ft in feats:
        vals = [p["f"][ft] for p in pls.values() if p["f"][ft] is not None]
        if len(vals) >= 3:
            popstats[ft] = (statistics.mean(vals), statistics.pstdev(vals) or 1.0)
    target = pls[player_id]
    out = []
    for pid, p in pls.items():
        if pid == player_id:
            continue
        shared, ss = 0, 0.0
        for ft in feats:
            if ft not in popstats:
                continue
            tv, cv = target["f"][ft], p["f"][ft]
            if tv is None or cv is None:
                continue
            mu, sd = popstats[ft]
            ss += ((tv - mu) / sd - (cv - mu) / sd) ** 2
            shared += 1
        if shared < 2:
            continue
        dist = (ss / shared) ** 0.5
        out.append({
            "player_id": pid, "name": p["name"], "matches": p["matches"],
            "bat_avg": p["bat_avg"], "bowl_avg": p["bowl_avg"],
            "similarity": round(100 / (1 + dist)),
        })
    out.sort(key=lambda x: x["similarity"], reverse=True)
    return out[:5]


async def player_deep_dive(session: AsyncSession, org_id: str, player_id: str) -> dict | None:
    """Conversion & starts, dismissal patterns, batting-by-position and
    by-opposition + a one-line scouting note — all from one innings pull."""
    prow = await session.execute(
        text(
            "SELECT COALESCE(display_name_override, name) AS name FROM players"
            " WHERE id = CAST(:pid AS UUID) AND organisation_id = CAST(:org AS UUID)"
        ),
        {"pid": player_id, "org": org_id},
    )
    p = prow.mappings().first()
    if not p:
        return None

    res = await session.execute(
        text(
            """
            SELECT bi.runs, bi.balls, bi.fours, bi.sixes, bi.not_out, bi.dismissal_type,
                   bi.caught_behind, bi.batting_position, bi.innings_number, g.result,
                   COALESCE(g.opp_org_id, g.opp_club_name) AS opp_key, g.opp_club_name AS opp_name
            FROM v_effective_batting_innings bi
            JOIN v_effective_games g ON g.id = bi.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE bi.player_id = CAST(:pid AS UUID) AND s.organisation_id = CAST(:org AS UUID)
              AND bi.did_not_bat IS NOT TRUE AND bi.runs IS NOT NULL
            """
        ),
        {"pid": player_id, "org": org_id},
    )
    inns = [dict(r) for r in res.mappings()]
    base = {"player": {"player_id": player_id, "name": p["name"]}, "innings_count": len(inns)}
    if not inns:
        return {**base, "conversion": None, "dismissals": [], "by_position": [], "by_opposition": {"best": [], "worst": []}, "batting_style": None, "context": None, "scouting_note": None}

    n = len(inns)
    starts = sum(1 for r in inns if r["runs"] >= 25)
    fifties_plus = sum(1 for r in inns if r["runs"] >= 50)
    hundreds = sum(1 for r in inns if r["runs"] >= 100)
    conversion = {
        "innings": n,
        "under_10": sum(1 for r in inns if r["runs"] < 10),
        "b10_24": sum(1 for r in inns if 10 <= r["runs"] < 25),
        "b25_49": sum(1 for r in inns if 25 <= r["runs"] < 50),
        "fifties": fifties_plus - hundreds,
        "hundreds": hundreds,
        "starts": starts,
        "double_figures_pct": round(100 * sum(1 for r in inns if r["runs"] >= 10) / n),
        "start_pct": round(100 * starts / n),
        "convert_25_to_50": round(100 * fifties_plus / starts) if starts else None,
        "convert_50_to_100": round(100 * hundreds / fifties_plus) if fifties_plus else None,
    }

    # Reliability (brief §6.1) — floor/median/ceiling, failure rate and a
    # boom-or-bust read, all from the runs distribution.
    runs_list = [r["runs"] for r in inns]
    runs_sorted = sorted(runs_list)
    mean_runs = statistics.mean(runs_list)
    cv = (statistics.pstdev(runs_list) / mean_runs) if mean_runs > 0 else None
    dismissed = [r for r in inns if not r["not_out"]]
    failures = sum(1 for r in dismissed if r["runs"] < 10)
    reliability = {
        "floor": _percentile(runs_sorted, 0.25),
        "median": _percentile(runs_sorted, 0.5),
        "ceiling": _percentile(runs_sorted, 0.9),
        "best": runs_sorted[-1],
        "failure_rate": round(100 * failures / len(dismissed)) if dismissed else None,
        "contribution_rate": round(100 * sum(1 for r in inns if r["runs"] >= 20) / n),
        "variability": round(cv, 2) if cv is not None else None,
        "profile": (
            "Boom or bust" if (cv is not None and cv > 1.1)
            else "Steady" if (cv is not None and cv < 0.7)
            else "Balanced"
        ),
    }

    # Dismissal patterns (dismissed innings only).
    dism: dict[str, int] = {}
    for r in inns:
        if r["not_out"]:
            continue
        lbl = _dism_label(r["dismissal_type"], r.get("caught_behind"))
        if lbl:
            dism[lbl] = dism.get(lbl, 0) + 1
    total_out = sum(dism.values())
    dismissals = sorted(
        [{"type": k, "count": v, "pct": round(100 * v / total_out)} for k, v in dism.items()],
        key=lambda d: d["count"], reverse=True,
    ) if total_out else []

    # Batting by position bucket.
    by_position = []
    best_pos = None
    for label, lo, hi in _POS_BUCKETS:
        rows = [r for r in inns if r["batting_position"] is not None and lo <= r["batting_position"] <= hi]
        if not rows:
            continue
        runs = sum(r["runs"] for r in rows)
        outs = sum(1 for r in rows if not r["not_out"] and _dism_label(r["dismissal_type"]))
        avg = round(runs / outs, 1) if outs else None
        entry = {"position": label, "innings": len(rows), "runs": runs, "average": avg}
        by_position.append(entry)
        if avg is not None and len(rows) >= 3 and (best_pos is None or avg > (best_pos["average"] or 0)):
            best_pos = entry

    # By opposition (min 2 innings), best & worst by average.
    opp: dict[str, dict] = {}
    for r in inns:
        if not r["opp_name"]:
            continue
        key = r["opp_key"] or r["opp_name"]
        e = opp.setdefault(key, {"name": r["opp_name"], "innings": 0, "runs": 0, "outs": 0})
        e["innings"] += 1
        e["runs"] += r["runs"]
        if not r["not_out"] and _dism_label(r["dismissal_type"]):
            e["outs"] += 1
    opp_rows = []
    for e in opp.values():
        if e["innings"] >= 2:
            e["average"] = round(e["runs"] / e["outs"], 1) if e["outs"] else None
            opp_rows.append({"name": e["name"], "innings": e["innings"], "runs": e["runs"], "average": e["average"]})
    rated = [o for o in opp_rows if o["average"] is not None]
    best_opp = sorted(rated, key=lambda o: o["average"], reverse=True)[:4]
    worst_opp = sorted([o for o in rated if o["innings"] >= 3], key=lambda o: o["average"])[:4]

    # Selection value (brief §6.2) — team win rate with vs without this player.
    sv = (await session.execute(
        text(
            """
            WITH og AS (
                SELECT g.id AS gid, g.result FROM v_effective_games g
                JOIN grades gr ON gr.id = g.grade_id JOIN seasons s ON s.id = gr.season_id
                WHERE s.organisation_id = CAST(:org AS UUID) AND g.result IN ('WIN', 'LOSS')
            ),
            pg AS (SELECT DISTINCT game_id FROM game_appearances WHERE player_id = CAST(:pid AS UUID))
            SELECT
                COUNT(*) FILTER (WHERE gid IN (SELECT game_id FROM pg)) AS with_g,
                COUNT(*) FILTER (WHERE gid IN (SELECT game_id FROM pg) AND result = 'WIN') AS with_w,
                COUNT(*) FILTER (WHERE gid NOT IN (SELECT game_id FROM pg)) AS wo_g,
                COUNT(*) FILTER (WHERE gid NOT IN (SELECT game_id FROM pg) AND result = 'WIN') AS wo_w
            FROM og
            """
        ),
        {"org": org_id, "pid": player_id},
    )).mappings().first()

    def _wp(w, g):
        return round(100 * w / g) if g else None

    selection_value = None
    if sv and (sv["with_g"] or sv["wo_g"]):
        selection_value = {
            "with": {"games": sv["with_g"], "win_pct": _wp(sv["with_w"], sv["with_g"])},
            "without": {"games": sv["wo_g"], "win_pct": _wp(sv["wo_w"], sv["wo_g"])},
        }
        wp_with, wp_wo = selection_value["with"]["win_pct"], selection_value["without"]["win_pct"]
        selection_value["swing"] = (wp_with - wp_wo) if (wp_with is not None and wp_wo is not None) else None

    similar_players = await _similar_players(session, org_id, player_id)

    # Full-profile depth (brief §1.10/§1.11): venues + how they take wickets.
    venues = await get_player_by_venue(session, player_id)
    by_venue = sorted(
        [v for v in venues if (v.get("innings") or 0) > 0 or (v.get("wickets") or 0) > 0],
        key=lambda v: (v.get("games") or 0), reverse=True,
    )[:8]
    bowling_dismissals = await get_bowling_dismissal_breakdown(session, player_id)
    # Full bowling profile (brief §2): career figures + which batting positions
    # they take their wickets at (new-ball vs middle vs tail).
    cb = await get_career_bowling(session, player_id)
    bowling_profile = cb if (cb and (cb.get("total_wickets") or 0) > 0) else None
    wickets_by_position = await get_bowling_by_batter_position(session, player_id) if bowling_profile else []

    # Batting style (brief §1.2, scorecard-reachable subset) — how they score,
    # from balls + boundaries. Dot% / SR-by-ball-range need ball-by-ball: out of reach.
    tb = sum(r["balls"] for r in inns if r["balls"])
    tfours = sum(r["fours"] or 0 for r in inns)
    tsixes = sum(r["sixes"] or 0 for r in inns)
    tboundaries = tfours + tsixes
    truns = sum(r["runs"] for r in inns)
    batting_style = None
    if tb > 0:
        bpct = round(100 * (4 * tfours + 6 * tsixes) / truns) if truns else None
        batting_style = {
            "balls": tb,
            "strike_rate": round(100 * truns / tb, 1),
            "boundary_pct": bpct,                         # share of runs in boundaries
            "balls_per_boundary": round(tb / tboundaries, 1) if tboundaries else None,
            "fours": tfours, "sixes": tsixes,
            "profile": (
                ("Boundary hitter" if bpct >= 60 else "Accumulator" if bpct <= 35 else "Balanced")
                if bpct is not None else None
            ),
        }

    # Result & innings context (brief §1.1) — average in wins/losses and when
    # batting first vs chasing (innings 1 vs 2+). g.result is our club's result.
    def _ctx(rows):
        rr = sum(x["runs"] for x in rows)
        outs = sum(1 for x in rows if not x["not_out"] and _dism_label(x["dismissal_type"]))
        return {"innings": len(rows), "runs": rr, "average": round(rr / outs, 1) if outs else None}
    wins_i = [r for r in inns if r["result"] == "WIN"]
    loss_i = [r for r in inns if r["result"] == "LOSS"]
    bf_i = [r for r in inns if r["innings_number"] == 1]
    ch_i = [r for r in inns if r["innings_number"] and r["innings_number"] >= 2]
    context = {
        "wins": _ctx(wins_i) if wins_i else None,
        "losses": _ctx(loss_i) if loss_i else None,
        "bat_first": _ctx(bf_i) if bf_i else None,
        "chasing": _ctx(ch_i) if ch_i else None,
    }
    if not any(context.values()):
        context = None

    # Scouting note (community-CricViz card §16.9).
    role = max(by_position, key=lambda x: x["innings"])["position"].lower() if by_position else "batter"
    bits = [f"Bats mostly as {('an ' if role[0] in 'aeiou' else 'a ')}{role} option."]
    if starts >= 4:
        if (conversion["convert_25_to_50"] or 0) >= 45:
            bits.append(f"Converts starts well — {fifties_plus} fifty-plus from {starts} starts.")
        else:
            bits.append(f"Gets in but gets out — only {fifties_plus} of {starts} starts went past 50.")
    if dismissals:
        bits.append(f"Most often out {dismissals[0]['type']} ({dismissals[0]['pct']}%).")
    if best_opp:
        bits.append(f"Enjoys facing {best_opp[0]['name']} (avg {best_opp[0]['average']}).")
    scouting_note = " ".join(bits)

    return {
        **base,
        "conversion": conversion,
        "dismissals": dismissals,
        "by_position": by_position,
        "best_position": best_pos["position"] if best_pos else None,
        "by_opposition": {"best": best_opp, "worst": worst_opp},
        "batting_style": batting_style,
        "context": context,
        "by_venue": by_venue,
        "bowling_dismissals": bowling_dismissals,
        "bowling_profile": bowling_profile,
        "wickets_by_position": wickets_by_position,
        "reliability": reliability,
        "selection_value": selection_value,
        "similar_players": similar_players,
        "scouting_note": scouting_note,
    }


# ─── Bowler deep-dive (analytics brief §2.5 — wicket quality) ─────────────────

# Dismissals where a fielder (not the bowler) effects the wicket.
_FIELDER_DISM = ("caught", "stumped", "run out")


async def bowler_deep_dive(session: AsyncSession, org_id: str, player_id: str) -> dict | None:
    """Wicket-quality intel for one bowler from ``bowler_wickets`` (brief §2.5):
    do they remove *set* batters or new ones, what their scalps were worth, which
    fielders hold catches for them, and their extras discipline (§2.9). The mirror
    of the batter deep-dive — complements the career bowling profile already shown
    on the player trend rather than repeating it."""
    prow = await session.execute(
        text(
            "SELECT COALESCE(display_name_override, name) AS name FROM players"
            " WHERE id = CAST(:pid AS UUID) AND organisation_id = CAST(:org AS UUID)"
        ),
        {"pid": player_id, "org": org_id},
    )
    p = prow.mappings().first()
    if not p:
        return None

    res = await session.execute(
        text(
            """
            SELECT bw.batter_position AS pos, bw.batter_runs AS runs,
                   bw.dismissal_type AS dt, bw.fielder_id::text AS fid,
                   COALESCE(f.display_name_override, f.name) AS fielder
            FROM bowler_wickets bw
            JOIN v_effective_games g ON g.id = bw.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            LEFT JOIN players f ON f.id = bw.fielder_id
            WHERE bw.bowler_id = CAST(:pid AS UUID) AND s.organisation_id = CAST(:org AS UUID)
            """
        ),
        {"pid": player_id, "org": org_id},
    )
    rows = [dict(r) for r in res.mappings()]
    base = {"player": {"player_id": player_id, "name": p["name"]}, "wickets": len(rows)}
    if not rows:
        return {**base, "quality": None, "fielders": [], "discipline": None, "scouting_note": None}

    n = len(rows)
    # Wicket quality by the dismissed batter's score — set (30+) vs new (<10).
    with_runs = [r for r in rows if r["runs"] is not None]
    kr = len(with_runs)
    set_w = sum(1 for r in with_runs if r["runs"] >= 30)
    start_w = sum(1 for r in with_runs if 10 <= r["runs"] < 30)
    new_w = sum(1 for r in with_runs if r["runs"] < 10)
    quality = {
        "with_runs": kr,
        "set": set_w, "started": start_w, "new": new_w,
        "set_pct": round(100 * set_w / kr) if kr else None,
        "new_pct": round(100 * new_w / kr) if kr else None,
        "scalp_value": round(statistics.mean([r["runs"] for r in with_runs]), 1) if kr else None,
        "ducks": sum(1 for r in with_runs if r["runs"] == 0),
    } if kr else None

    # Position split (top 1–3 / middle 4–7 / tail 8+) — for the scouting note.
    def _posbucket(lo, hi):
        return sum(1 for r in rows if r["pos"] is not None and lo <= r["pos"] <= hi)
    top, mid, tail = _posbucket(1, 3), _posbucket(4, 7), _posbucket(8, 13)
    tot_pos = top + mid + tail

    # Dismissal split — for the scouting note.
    dism: dict[str, int] = {}
    for r in rows:
        lbl = _dism_label(r["dt"])
        if lbl:
            dism[lbl] = dism.get(lbl, 0) + 1

    # Fielder combos — who holds catches / effects run-outs for this bowler
    # (caught & bowled excluded: the bowler is their own fielder there).
    fmap: dict[str, dict] = {}
    for r in rows:
        if not r["fid"] or not r["fielder"]:
            continue
        if _dism_label(r["dt"]) not in _FIELDER_DISM:
            continue
        e = fmap.setdefault(r["fid"], {"name": r["fielder"], "count": 0})
        e["count"] += 1
    fielders = sorted(
        ({"name": v["name"], "count": v["count"]} for v in fmap.values()),
        key=lambda x: x["count"], reverse=True,
    )[:5]

    # Discipline — extras per over, from this bowler's spells (brief §2.9).
    drow = (await session.execute(
        text(
            """
            SELECT
                COALESCE(SUM(FLOOR(bs.overs) * 6 + ROUND((bs.overs - FLOOR(bs.overs)) * 10)), 0)::int AS balls,
                COALESCE(SUM(bs.runs), 0) AS runs,
                COALESCE(SUM(bs.wides), 0) AS wides,
                COALESCE(SUM(bs.no_balls), 0) AS nb
            FROM v_effective_bowling_spells bs
            JOIN v_effective_games g ON g.id = bs.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE bs.player_id = CAST(:pid AS UUID) AND s.organisation_id = CAST(:org AS UUID)
              AND bs.overs IS NOT NULL
            """
        ),
        {"pid": player_id, "org": org_id},
    )).mappings().first()
    discipline = None
    if drow and int(drow["balls"] or 0) >= 60 and (int(drow["wides"] or 0) + int(drow["nb"] or 0)) > 0:
        balls = int(drow["balls"]); ov = balls / 6
        ex = int(drow["wides"]) + int(drow["nb"])
        discipline = {
            "overs": f"{balls // 6}.{balls % 6}",
            "wides": int(drow["wides"]), "no_balls": int(drow["nb"]), "extras": ex,
            "extras_per_over": round(ex / ov, 2) if ov else None,
            "wides_per_over": round(int(drow["wides"]) / ov, 2) if ov else None,
        }

    # Scouting note (community-CricViz card §16.9, bowling edition).
    bits = []
    if tot_pos >= 5:
        if top / tot_pos >= 0.5:
            bits.append(f"Top-order threat — {round(100 * top / tot_pos)}% of wickets are the top 3.")
        elif tail / tot_pos >= 0.5:
            bits.append(f"Mops up the lower order — {round(100 * tail / tot_pos)}% of wickets bat 8 or below.")
    if quality and kr >= 5:
        if (quality["set_pct"] or 0) >= 45:
            bits.append(f"Removes set batters (their scalps average {quality['scalp_value']}).")
        elif (quality["new_pct"] or 0) >= 50:
            bits.append("Strikes early — usually gets batters before they're in.")
    if dism:
        topd = max(dism.items(), key=lambda x: x[1])
        if topd[1] / n >= 0.4:
            how = {
                "bowled": "bowls them", "lbw": "traps them lbw",
                "caught": "finds the edge or catcher", "stumped": "beats them in the air",
                "caught & bowled": "catches them off his own bowling",
            }.get(topd[0], f"takes {topd[0]} wickets")
            bits.append(f"Mostly {how} ({round(100 * topd[1] / n)}%).")
    if discipline and discipline["extras_per_over"] is not None:
        if discipline["extras_per_over"] <= 0.3:
            bits.append(f"Tidy — {discipline['extras_per_over']} extras/over.")
        elif discipline["extras_per_over"] >= 0.8:
            bits.append(f"Can leak extras — {discipline['extras_per_over']}/over.")
    scouting_note = " ".join(bits) if bits else None

    return {
        **base,
        "quality": quality,
        "fielders": fielders,
        "discipline": discipline,
        "scouting_note": scouting_note,
    }


async def list_players(session: AsyncSession, org_id: str, season_id: str | None = None, grade_id: str | None = None) -> list[dict]:
    """Players (with their stats) for the trends picker, scoped to the SELECTED
    season (default: latest with stats) and optionally one grade. Historical-only
    names are excluded — the picker tracks who turned out in that season/grade."""
    target_year = None
    if season_id:
        r = await session.execute(text("SELECT year FROM seasons WHERE id = CAST(:sid AS UUID)"), {"sid": season_id})
        target_year = r.scalar()
    if target_year is None:
        target_year = await _current_season_year(session, org_id)
    if target_year is None:
        return []
    res = await session.execute(
        text(
            f"""
            SELECT p.id::text AS id, COALESCE(p.display_name_override, p.name) AS name,
                   t.id::text AS squad_id, t.name AS squad_name,
                   COALESCE(SUM(st.runs), 0) AS runs,
                   COALESCE(SUM(st.batting_innings), 0) AS inns,
                   COALESCE(SUM(st.not_outs), 0) AS not_outs,
                   COALESCE(SUM(st.wickets), 0) AS wickets,
                   COALESCE(SUM(st.runs_conceded), 0) AS conceded,
                   COALESCE(SUM(st.matches), 0) AS matches
            FROM {_movers_src(grade_id)}
            -- Scope by the SEASON's org (not player membership) — a shared-GUID
            -- player's org may be a different (first-synced) club while their
            -- stats sit under THIS org's season (the documented cross-club anti-pattern).
            JOIN seasons s ON s.id = st.season_id AND s.organisation_id = CAST(:org AS UUID) AND s.year = :cur
            JOIN players p ON p.id = st.player_id AND p.status = 'active'
            LEFT JOIN teams t ON t.id = p.squad_team_id
            GROUP BY p.id, p.display_name_override, p.name, t.id, t.name
            HAVING COALESCE(SUM(st.matches), 0) > 0
                OR COALESCE(SUM(st.batting_innings), 0) > 0
                OR COALESCE(SUM(st.wickets), 0) > 0
            ORDER BY name
            """
        ),
        {"org": org_id, "cur": target_year, "grade": grade_id},
    )
    out = []
    for r in res.mappings():
        outs = r["inns"] - r["not_outs"]
        bat_avg = round(r["runs"] / outs, 2) if outs > 0 else None
        bowl_avg = round(r["conceded"] / r["wickets"], 2) if r["wickets"] else None
        out.append({
            "player_id": r["id"], "name": r["name"], "runs": r["runs"],
            "wickets": r["wickets"], "matches": r["matches"],
            "bat_avg": bat_avg, "bowl_avg": bowl_avg,
            "squad_id": r["squad_id"], "squad_name": r["squad_name"],
        })
    return out
