"""BetterIQ — player radar profiles.

A 6-axis batting and/or bowling shape for one of our players, normalised so the
**squad average sits on the 50 ring** (ratio-to-mean × 50, clamped 0–100;
lower-is-better bowling metrics inverted). Computed over season's-org-scoped
``player_season_stats`` (career by default, or one season). Opposition radars
are built client-side from the live dossier instead (their per-innings rows
aren't in our DB).
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.iq_filters import season_member_clause

MIN_BAT_INN = 3      # ignore tiny samples when building the squad baseline
MIN_BOWL_INN = 3

BAT_AXES = ["Volume", "Average", "Strike rate", "Consistency", "Conversion", "Impact"]
BOWL_AXES = ["Wickets", "Average", "Economy", "Strike rate", "Penetration", "Workload"]


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _bat_metrics(r):
    binn = _num(r["binn"])
    if binn <= 0:
        return None
    outs = max(binn - _num(r["no"]), 1)
    bf = _num(r["bf"])
    matches = max(_num(r["matches"]), 1)
    return {
        "Volume": _num(r["runs"]),
        "Average": _num(r["runs"]) / outs,
        "Strike rate": (100 * _num(r["runs"]) / bf) if bf else 0.0,
        "Consistency": 1 - (_num(r["ducks"]) / binn),
        "Conversion": (_num(r["f50"]) + _num(r["f100"])) / binn,
        "Impact": _num(r["runs"]) / matches,
        "_inn": binn,
    }


def _bowl_metrics(r):
    binn = _num(r["bowlinn"])
    wkts = _num(r["wkts"])
    if binn <= 0 or wkts <= 0:
        return None
    bballs = _num(r["bballs"])
    conceded = _num(r["conceded"])
    return {
        "Wickets": wkts,
        "Average": (conceded / wkts) if wkts else 0.0,
        "Economy": (6 * conceded / bballs) if bballs else 0.0,
        "Strike rate": (bballs / wkts) if wkts else 0.0,
        "Penetration": wkts / binn,
        "Workload": bballs / 6,
        "_inn": binn,
    }


# Bowling metrics where a LOWER raw value is better (so we invert the ratio).
_LOWER_BETTER = {"Average", "Economy", "Strike rate"}


def _normalise(player, peers, axes, lower_better=()):
    """player: {axis: value}; peers: list of those dicts. Returns 0–100 values
    where the peer mean maps to 50 (or inverted for lower-better axes)."""
    values = []
    for ax in axes:
        mean = 0.0
        vals = [p[ax] for p in peers if p.get(ax) is not None]
        if vals:
            mean = sum(vals) / len(vals)
        v = player.get(ax, 0.0)
        if ax in lower_better:
            score = (mean / v) * 50 if v else 100.0
        else:
            score = (v / mean) * 50 if mean else 50.0
        values.append(round(max(0.0, min(100.0, score)), 1))
    return values


async def player_radar(session: AsyncSession, org_id: str, player_id: str, season_id: str | None = None) -> dict:
    clause = season_member_clause("pss.season_id", season_id)
    rows = (await session.execute(text(f"""
        SELECT pss.player_id::text AS pid,
               SUM(pss.runs) AS runs, SUM(pss.batting_innings) AS binn, SUM(pss.not_outs) AS no,
               SUM(pss.matches) AS matches, SUM(pss.fifties) AS f50, SUM(pss.hundreds) AS f100,
               SUM(pss.ducks) AS ducks, SUM(pss.balls_faced) AS bf,
               SUM(pss.wickets) AS wkts, SUM(pss.bowling_innings) AS bowlinn,
               SUM(pss.bowling_balls) AS bballs, SUM(pss.runs_conceded) AS conceded
        FROM player_season_stats pss
        JOIN seasons s ON s.id = pss.season_id
        WHERE s.organisation_id = CAST(:org AS UUID) {clause}
        GROUP BY pss.player_id
    """), {"org": org_id, "season": season_id})).mappings().all()

    target_id = str(player_id)
    bat_all, bowl_all, bat_me, bowl_me = [], [], None, None
    for r in rows:
        bm = _bat_metrics(r)
        wm = _bowl_metrics(r)
        if bm and bm["_inn"] >= MIN_BAT_INN:
            bat_all.append(bm)
        if wm and wm["_inn"] >= MIN_BOWL_INN:
            bowl_all.append(wm)
        if r["pid"] == target_id:
            bat_me, bowl_me = bm, wm

    out = {"player_id": target_id, "bat": None, "bowl": None}
    if bat_me and bat_all:
        out["bat"] = {
            "axes": BAT_AXES,
            "values": _normalise(bat_me, bat_all, BAT_AXES),
            "baseline": [50] * len(BAT_AXES),
        }
    if bowl_me and bowl_all:
        out["bowl"] = {
            "axes": BOWL_AXES,
            "values": _normalise(bowl_me, bowl_all, BOWL_AXES, lower_better=_LOWER_BETTER),
            "baseline": [50] * len(BOWL_AXES),
        }
    return out
