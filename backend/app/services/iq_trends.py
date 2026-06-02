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
    get_career_batting,
    get_career_bowling,
    get_career_fielding,
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


async def _batting_movers(session: AsyncSession, org_id: str) -> dict:
    """Active players whose latest season's batting average diverges sharply
    from their prior-career baseline."""
    res = await session.execute(
        text(
            """
            WITH ranked AS (
                SELECT pss.player_id, s.year,
                       COALESCE(pss.batting_innings, 0) AS inns,
                       COALESCE(pss.runs, 0) AS runs,
                       COALESCE(pss.not_outs, 0) AS not_outs,
                       pss.batting_average AS avg,
                       ROW_NUMBER() OVER (
                           PARTITION BY pss.player_id ORDER BY s.year DESC NULLS LAST
                       ) AS rn
                FROM player_season_stats pss
                JOIN seasons s ON s.id = pss.season_id
                WHERE s.organisation_id = CAST(:org AS UUID)
            ),
            latest AS (SELECT * FROM ranked WHERE rn = 1),
            prior AS (
                SELECT player_id, SUM(inns) AS inns, SUM(runs) AS runs, SUM(not_outs) AS not_outs
                FROM ranked WHERE rn > 1 GROUP BY player_id
            )
            SELECT p.id::text AS id, COALESCE(p.display_name_override, p.name) AS name,
                   l.year AS latest_year, l.inns AS latest_inns,
                   l.runs AS latest_runs, l.avg AS latest_avg,
                   pr.inns AS prior_inns, pr.runs AS prior_runs, pr.not_outs AS prior_not_outs
            FROM latest l
            JOIN players p ON p.id = l.player_id AND p.status = 'active'
            JOIN prior pr ON pr.player_id = l.player_id
            WHERE l.inns >= :min_recent AND pr.inns >= :min_prior AND l.avg IS NOT NULL
            """
        ),
        {"org": org_id, "min_recent": _MIN_RECENT_BAT_INNS, "min_prior": _MIN_PRIOR_BAT_INNS},
    )
    risers, fallers = [], []
    for r in res.mappings():
        latest = float(r["latest_avg"])
        baseline = _bat_avg(r["prior_runs"], r["prior_inns"], r["prior_not_outs"])
        if not baseline:
            continue
        row = {
            "player_id": r["id"], "name": r["name"], "latest_year": r["latest_year"],
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


async def _bowling_movers(session: AsyncSession, org_id: str) -> dict:
    """Active players whose latest season's bowling average diverges sharply
    from their prior-career baseline (lower is better)."""
    res = await session.execute(
        text(
            """
            WITH ranked AS (
                SELECT pss.player_id, s.year,
                       COALESCE(pss.wickets, 0) AS wkts,
                       COALESCE(pss.runs_conceded, 0) AS runs,
                       pss.bowling_average AS avg,
                       ROW_NUMBER() OVER (
                           PARTITION BY pss.player_id ORDER BY s.year DESC NULLS LAST
                       ) AS rn
                FROM player_season_stats pss
                JOIN seasons s ON s.id = pss.season_id
                WHERE s.organisation_id = CAST(:org AS UUID)
            ),
            latest AS (SELECT * FROM ranked WHERE rn = 1),
            prior AS (
                SELECT player_id, SUM(wkts) AS wkts, SUM(runs) AS runs
                FROM ranked WHERE rn > 1 GROUP BY player_id
            )
            SELECT p.id::text AS id, COALESCE(p.display_name_override, p.name) AS name,
                   l.year AS latest_year, l.wkts AS latest_wkts, l.avg AS latest_avg,
                   pr.wkts AS prior_wkts, pr.runs AS prior_runs
            FROM latest l
            JOIN players p ON p.id = l.player_id AND p.status = 'active'
            JOIN prior pr ON pr.player_id = l.player_id
            WHERE l.wkts >= :min_recent AND pr.wkts >= :min_prior AND l.avg IS NOT NULL
            """
        ),
        {"org": org_id, "min_recent": _MIN_RECENT_WKTS, "min_prior": _MIN_PRIOR_WKTS},
    )
    risers, fallers = [], []
    for r in res.mappings():
        latest = float(r["latest_avg"])
        baseline = round(r["prior_runs"] / r["prior_wkts"], 2) if r["prior_wkts"] else None
        if not baseline:
            continue
        row = {
            "player_id": r["id"], "name": r["name"], "latest_year": r["latest_year"],
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


async def _emerging(session: AsyncSession, org_id: str) -> list[dict]:
    """Ones to watch — active players in their first few seasons with a strong
    latest season (short history + meaningful recent output)."""
    res = await session.execute(
        text(
            """
            WITH ranked AS (
                SELECT pss.player_id, s.year,
                       COALESCE(pss.runs, 0) AS runs, COALESCE(pss.wickets, 0) AS wkts,
                       ROW_NUMBER() OVER (PARTITION BY pss.player_id ORDER BY s.year DESC NULLS LAST) AS rn,
                       COUNT(*) OVER (PARTITION BY pss.player_id) AS seasons
                FROM player_season_stats pss JOIN seasons s ON s.id = pss.season_id
                WHERE s.organisation_id = CAST(:org AS UUID)
            )
            SELECT p.id::text AS id, COALESCE(p.display_name_override, p.name) AS name,
                   r.year, r.runs, r.wkts, r.seasons
            FROM ranked r JOIN players p ON p.id = r.player_id AND p.status = 'active'
            WHERE r.rn = 1 AND r.seasons <= 3 AND (r.runs >= 200 OR r.wkts >= 8)
            ORDER BY (r.runs + r.wkts * 18) DESC
            LIMIT 6
            """
        ),
        {"org": org_id},
    )
    return [
        {"player_id": x["id"], "name": x["name"], "latest_year": x["year"],
         "runs": x["runs"], "wickets": x["wkts"], "seasons": x["seasons"]}
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


async def trends_overview(session: AsyncSession, org_id: str) -> dict:
    """Club-wide development snapshot: milestone watch + breakout/decline movers + emerging."""
    milestones = await get_upcoming_milestones_for_org(session, org_id, limit=12)
    batting = await _batting_movers(session, org_id)
    bowling = await _bowling_movers(session, org_id)
    emerging = await _emerging(session, org_id)
    return {
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


async def list_players(session: AsyncSession, org_id: str) -> list[dict]:
    """Active players (with a little career context) for the trends picker."""
    res = await session.execute(
        text(
            """
            SELECT p.id::text AS id, COALESCE(p.display_name_override, p.name) AS name,
                   COALESCE(SUM(pss.runs), 0) AS runs,
                   COALESCE(SUM(pss.wickets), 0) AS wickets,
                   COALESCE(SUM(pss.matches), 0) AS matches,
                   COUNT(pss.season_id) AS seasons
            FROM players p
            LEFT JOIN player_season_stats pss ON pss.player_id = p.id
            WHERE p.organisation_id = CAST(:org AS UUID) AND p.status = 'active'
            GROUP BY p.id, name
            HAVING COUNT(pss.season_id) > 0
            ORDER BY name
            """
        ),
        {"org": org_id},
    )
    return [
        {"player_id": r["id"], "name": r["name"], "runs": r["runs"],
         "wickets": r["wickets"], "matches": r["matches"], "seasons": r["seasons"]}
        for r in res.mappings()
    ]
