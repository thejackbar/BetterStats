"""BetterScout — the Milestones screen ("who is close, who just got there").

Reuses ``services/milestone_rules.py`` verbatim — the thresholds and reach
windows must never drift from the club product's own scheme, since this
screen's copy quotes them straight from there. This module's only job is
applying that scheme to ``ScoutedPlayer.stats_payload`` (built by
``scout_discovery``/``scout_internal_link``) instead of a club's own tables,
and tracking per-org "seen" state on top.

Two-tier dating, the load-bearing honesty rule from the design brief:
  - a player who resolved via services/scout_internal_link.py (their club is
    already an onboarded BetterCricket club) gets crossings dated to a real
    match, via internal_match_log's game-by-game log — "MATCH DATED".
  - everyone else only has Cricket Australia's public season-aggregate feed
    behind them, so a crossing can only be pinned to a season — "SEASON
    ONLY". Same simulate-cumulative-totals technique
    aggregations.get_recently_achieved_milestones_for_org uses, just walking
    ScoutedPlayer.stats_payload's seasons instead of DB rows.

Both the career-threshold "reached" list AND the "recent notable
performances" list (100+ / 5-fors within the last N seasons) read from the
SAME per-player source rows (`_player_source`) — one internal_match_log
fetch or one stats_payload.seasons read per player, not two.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Organisation
from app.models.scout import ScoutMilestoneSeen, ScoutWatchlist, ScoutWatchlistCard, ScoutedPlayer
from app.services import scout_internal_link
from app.services.milestone_rules import crossed_thresholds, is_displayable, next_threshold, reach_window

CATEGORY_MAP = {"runs": "batting", "wickets": "bowling", "matches": "matches", "catches": "fielding"}
STATS = ("runs", "wickets", "matches", "catches")

DEFAULT_SEASONS_WINDOW = 2
CENTURY_RUNS = 100
FIVE_FOR_WICKETS = 5


async def _tracked_players(session: AsyncSession, scout_org_id: str) -> list[ScoutedPlayer]:
    res = await session.execute(
        select(ScoutedPlayer)
        .join(ScoutWatchlistCard, ScoutWatchlistCard.scouted_player_id == ScoutedPlayer.id)
        .join(ScoutWatchlist, ScoutWatchlist.id == ScoutWatchlistCard.watchlist_id)
        .where(ScoutWatchlist.scout_org_id == scout_org_id, ScoutedPlayer.stats_payload.isnot(None))
        .distinct()
    )
    return res.scalars().all()


def _in_reach_for(player: ScoutedPlayer) -> list[dict]:
    totals = (player.stats_payload or {}).get("totals") or {}
    out = []
    for stat in STATS:
        current = int(totals.get(stat) or 0)
        target = next_threshold(stat, current)
        if target is None:
            continue
        needed = target - current
        if needed <= 0 or needed > reach_window(stat, target):
            continue
        out.append({
            "player_id": str(player.id),
            "name": player.name,
            "club_name": player.club_name,
            "category": CATEGORY_MAP[stat],
            "type": stat,
            "current": current,
            "target": target,
            "needed": needed,
            "internal_link": player.internal_player_id is not None,
        })
    return out


async def _player_source(session: AsyncSession, player: ScoutedPlayer) -> tuple[str, list[dict]]:
    """The one per-player fetch both the reached-thresholds simulation and
    the recent-performances scan read from. 'match' = internal_match_log's
    real per-game rows (bat_runs/bowl_wickets/played_at/year/grade_name),
    oldest first. 'season' = stats_payload.seasons (year/grade/hundreds/
    five_fors/…), oldest first — the public season-aggregate fallback."""
    if player.internal_player_id and player.internal_org_id:
        org = await session.get(Organisation, player.internal_org_id)
        if org and org.is_active and org.archived_at is None:
            log = await scout_internal_link.internal_match_log(session, org, player.internal_player_id)
            if log:
                return "match", log
    seasons = sorted((player.stats_payload or {}).get("seasons") or [], key=lambda s: s.get("year") or 0)
    return "season", seasons


def _reached_from_rows(dated: str, rows: list[dict]) -> dict[str, list[dict]]:
    """Simulate cumulative totals oldest→newest over `rows` (either source)
    to find which row first carried each stat past a threshold."""
    running = dict.fromkeys(STATS, 0)
    out: dict[str, list[dict]] = {s: [] for s in STATS}
    for row in rows:
        if dated == "match":
            deltas = {
                "runs": int(row.get("bat_runs") or 0),
                "wickets": int(row.get("bowl_wickets") or 0),
                "matches": 1,
                "catches": int(row.get("fielding_catches") or 0),
            }
            achieved_at = row.get("played_at")
            achieved_at = achieved_at.isoformat() if achieved_at else None
        else:
            deltas = {stat: int(row.get(stat) or 0) for stat in STATS}
            achieved_at = None
        for stat in STATS:
            before = running[stat]
            after = before + deltas[stat]
            newly = set(crossed_thresholds(stat, after)) - set(crossed_thresholds(stat, before))
            for value in sorted(newly):
                out[stat].append({
                    "value": value,
                    "achieved_at": achieved_at,
                    "season_year": row.get("year"),
                    "grade_name": row.get("grade_name") if dated == "match" else row.get("grade"),
                })
            running[stat] = after
    return out


def _flatten(per_stat: dict[str, list[dict]], player: ScoutedPlayer, dated: str, seen: set) -> list[dict]:
    out = []
    for stat, crossings in per_stat.items():
        for c in crossings:
            if not is_displayable(stat, c["value"]):
                continue
            out.append({
                "player_id": str(player.id),
                "name": player.name,
                "club_name": player.club_name,
                "category": CATEGORY_MAP[stat],
                "type": stat,
                "milestone_value": c["value"],
                "achieved_at": c.get("achieved_at"),
                "season_year": c.get("season_year"),
                "grade_name": c.get("grade_name"),
                "dated": dated,  # 'match' | 'season'
                "seen": (str(player.id), stat, c["value"]) in seen,
            })
    return out


def _recent_years(rows: list[dict], seasons_window: int) -> set:
    years = sorted({r.get("year") for r in rows if r.get("year") is not None}, reverse=True)
    return set(years[:seasons_window])


def _recent_performances_from_rows(player: ScoutedPlayer, dated: str, rows: list[dict], seasons_window: int) -> list[dict]:
    """Individual big performances — 100+ runs / 5+ wickets — within the
    player's most recent `seasons_window` active seasons. Distinct from the
    "reached" list above: that's a cumulative CAREER crossing, this is a
    single innings or spell being notable on its own. 'match' dating lists
    each qualifying game exactly; 'season' dating can only report the
    season's own hundreds/five_fors COUNT (CA's aggregate feed has no
    per-innings detail), so an external player's row reads "N centuries"
    rather than naming a specific game."""
    recent_years = _recent_years(rows, seasons_window)
    out = []
    for row in rows:
        yr = row.get("year")
        if yr not in recent_years:
            continue
        if dated == "match":
            runs = int(row.get("bat_runs") or 0)
            wkts = int(row.get("bowl_wickets") or 0)
            played_at = row.get("played_at")
            achieved_at = played_at.isoformat() if played_at else None
            grade_name = row.get("grade_name")
            if runs >= CENTURY_RUNS:
                out.append({"type": "century", "value": runs, "achieved_at": achieved_at, "season_year": yr, "grade_name": grade_name, "dated": "match"})
            if wkts >= FIVE_FOR_WICKETS:
                out.append({"type": "five_for", "value": wkts, "achieved_at": achieved_at, "season_year": yr, "grade_name": grade_name, "dated": "match"})
        else:
            hundreds = int(row.get("hundreds") or 0)
            five_fors = int(row.get("five_fors") or 0)
            grade_name = row.get("grade")
            if hundreds > 0:
                out.append({"type": "century", "value": hundreds, "achieved_at": None, "season_year": yr, "grade_name": grade_name, "dated": "season"})
            if five_fors > 0:
                out.append({"type": "five_for", "value": five_fors, "achieved_at": None, "season_year": yr, "grade_name": grade_name, "dated": "season"})
    return [
        {
            "player_id": str(player.id),
            "name": player.name,
            "club_name": player.club_name,
            "category": "batting" if p["type"] == "century" else "bowling",
            **p,
        }
        for p in out
    ]


def _season_counters(players: list[ScoutedPlayer], in_reach: list[dict]) -> dict:
    """Straight sums off each player's latest active season — no new
    computation, per the build note."""
    fifties = hundreds = five_fors = 0
    for p in players:
        seasons = sorted((p.stats_payload or {}).get("seasons") or [], key=lambda s: s.get("year") or 0, reverse=True)
        latest = next((s for s in seasons if (s.get("matches") or 0) > 0), None)
        if not latest:
            continue
        fifties += int(latest.get("fifties") or 0)
        hundreds += int(latest.get("hundreds") or 0)
        five_fors += int(latest.get("five_fors") or 0)
    return {
        "fifties_this_season": fifties,
        "hundreds_this_season": hundreds,
        "five_fors_this_season": five_fors,
        "in_reach_count": len(in_reach),
    }


async def unseen_reached_count(session: AsyncSession, scout_org_id: str) -> int:
    """Cheap version of `build_milestones` for the sidebar badge — same
    reached-list logic, just returns the count."""
    data = await build_milestones(session, scout_org_id)
    return sum(1 for r in data["reached"] if not r["seen"])


async def build_milestones(session: AsyncSession, scout_org_id: str, seasons_window: int = DEFAULT_SEASONS_WINDOW) -> dict:
    players = await _tracked_players(session, scout_org_id)
    seen_rows = (await session.execute(
        select(ScoutMilestoneSeen).where(ScoutMilestoneSeen.scout_org_id == scout_org_id)
    )).scalars().all()
    seen = {(str(r.scouted_player_id), r.milestone_type, r.milestone_value) for r in seen_rows}

    in_reach: list[dict] = []
    reached: list[dict] = []
    recent_performances: list[dict] = []
    for p in players:
        in_reach.extend(_in_reach_for(p))
        dated, rows = await _player_source(session, p)
        reached.extend(_flatten(_reached_from_rows(dated, rows), p, dated, seen))
        recent_performances.extend(_recent_performances_from_rows(p, dated, rows, seasons_window))

    in_reach.sort(key=lambda r: r["needed"])
    reached.sort(key=lambda r: (r["achieved_at"] or "", r["season_year"] or 0), reverse=True)
    recent_performances.sort(key=lambda r: (r["achieved_at"] or "", r["season_year"] or 0), reverse=True)

    return {
        "season_counters": _season_counters(players, in_reach),
        "in_reach": in_reach,
        "reached": reached,
        "recent_performances": recent_performances,
        "seasons_window": seasons_window,
    }


async def mark_seen(session: AsyncSession, scout_org_id: str, scouted_player_id: str, milestone_type: str, milestone_value: int) -> None:
    if milestone_type not in STATS:
        raise ValueError("Unknown milestone type.")
    existing = (await session.execute(
        select(ScoutMilestoneSeen).where(
            ScoutMilestoneSeen.scout_org_id == scout_org_id,
            ScoutMilestoneSeen.scouted_player_id == scouted_player_id,
            ScoutMilestoneSeen.milestone_type == milestone_type,
            ScoutMilestoneSeen.milestone_value == milestone_value,
        )
    )).scalar_one_or_none()
    if existing:
        return
    session.add(ScoutMilestoneSeen(
        scout_org_id=scout_org_id, scouted_player_id=scouted_player_id,
        milestone_type=milestone_type, milestone_value=milestone_value,
    ))
    await session.commit()


async def mark_all_seen(session: AsyncSession, scout_org_id: str) -> int:
    data = await build_milestones(session, scout_org_id)
    n = 0
    for r in data["reached"]:
        if r["seen"]:
            continue
        await mark_seen(session, scout_org_id, r["player_id"], r["type"], r["milestone_value"])
        n += 1
    return n
