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


def _reached_via_seasons(player: ScoutedPlayer) -> dict[str, list[dict]]:
    """SEASON ONLY dating — simulate cumulative career totals oldest to
    newest across the player's stats_payload seasons, and record which
    season's step first carried each stat past a threshold."""
    seasons = sorted((player.stats_payload or {}).get("seasons") or [], key=lambda s: s.get("year") or 0)
    running = dict.fromkeys(STATS, 0)
    out: dict[str, list[dict]] = {s: [] for s in STATS}
    for season in seasons:
        for stat in STATS:
            before = running[stat]
            after = before + int(season.get(stat) or 0)
            newly = set(crossed_thresholds(stat, after)) - set(crossed_thresholds(stat, before))
            for value in sorted(newly):
                out[stat].append({
                    "value": value,
                    "achieved_at": None,
                    "season_year": season.get("year"),
                    "grade_name": season.get("grade"),
                })
            running[stat] = after
    return out


async def _reached_via_match_log(session: AsyncSession, org: Organisation, player: ScoutedPlayer) -> dict[str, list[dict]]:
    """MATCH DATED — walk the real per-game log (services/
    scout_internal_link.internal_match_log) in order and record the exact
    game each threshold was first crossed on."""
    log = await scout_internal_link.internal_match_log(session, org, player.internal_player_id)
    running = dict.fromkeys(STATS, 0)
    out: dict[str, list[dict]] = {s: [] for s in STATS}
    for row in log:
        deltas = {
            "runs": int(row.get("bat_runs") or 0),
            "wickets": int(row.get("bowl_wickets") or 0),
            "matches": 1,
            "catches": int(row.get("fielding_catches") or 0),
        }
        played_at = row.get("played_at")
        for stat in STATS:
            before = running[stat]
            after = before + deltas[stat]
            newly = set(crossed_thresholds(stat, after)) - set(crossed_thresholds(stat, before))
            for value in sorted(newly):
                out[stat].append({
                    "value": value,
                    "achieved_at": played_at.isoformat() if played_at else None,
                    "season_year": row.get("year"),
                    "grade_name": row.get("grade_name"),
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


async def _reached_for(session: AsyncSession, player: ScoutedPlayer, seen: set) -> list[dict]:
    if player.internal_player_id and player.internal_org_id:
        org = await session.get(Organisation, player.internal_org_id)
        if org and org.is_active and org.archived_at is None:
            per_stat = await _reached_via_match_log(session, org, player)
            if any(per_stat.values()):
                return _flatten(per_stat, player, "match", seen)
    per_stat = _reached_via_seasons(player)
    return _flatten(per_stat, player, "season", seen)


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


async def build_milestones(session: AsyncSession, scout_org_id: str) -> dict:
    players = await _tracked_players(session, scout_org_id)
    seen_rows = (await session.execute(
        select(ScoutMilestoneSeen).where(ScoutMilestoneSeen.scout_org_id == scout_org_id)
    )).scalars().all()
    seen = {(str(r.scouted_player_id), r.milestone_type, r.milestone_value) for r in seen_rows}

    in_reach: list[dict] = []
    reached: list[dict] = []
    for p in players:
        in_reach.extend(_in_reach_for(p))
        reached.extend(await _reached_for(session, p, seen))

    in_reach.sort(key=lambda r: r["needed"])
    reached.sort(key=lambda r: (r["achieved_at"] or "", r["season_year"] or 0), reverse=True)

    return {
        "season_counters": _season_counters(players, in_reach),
        "in_reach": in_reach,
        "reached": reached,
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
