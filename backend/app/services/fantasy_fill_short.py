"""Fill Fantasy teams that are short of players with the top scorers in the pool.

For a club that has lost picks it cannot recover (see `fantasy_merge_repair`). Each
short team gets, for every place it is missing, the pool player with the most
season points that it does not already hold, taking the role the team is short of
first so the role quota is met. Ties (the season has often barely started, so many
players are on the same points) go to the higher priced player, then by name. The
lock and the budget are ignored, as in the admin team editor.

``only_merged`` limits the choice to players who were merged (see
``merged_player_ids``), still by most season points.
"""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import FantasySeason, FantasySquadPlayer
from app.services import fantasy_engine
from app.services.fantasy_scoring import DEFAULT_RULES

ROLE_ORDER = ["keeper", "batter", "allrounder", "bowler"]


async def merged_player_ids(db: AsyncSession, org_id, since=None) -> set[str]:
    """The live records of players the club merged since Fantasy began (or since
    ``since``, a date). A merge's kept profile is always live; the merged-away
    record is live only if the merge was undone, and then both are the same person,
    so both are eligible."""
    rows = (await db.execute(text("""
        SELECT removed_player_id, keep_player_id, undone_at FROM merge_logs
        WHERE org_id = CAST(:o AS UUID)
          AND merged_at >= COALESCE(CAST(:since AS TIMESTAMPTZ),
                (SELECT MIN(created_at) FROM fantasy_seasons WHERE organisation_id = CAST(:o AS UUID)))
    """), {"o": str(org_id), "since": since})).all()
    ids: set[str] = set()
    for removed, keep, undone in rows:
        if keep:
            ids.add(str(keep))
        if removed and undone:
            ids.add(str(removed))
    return ids


async def plan_fill(db: AsyncSession, org_id, only_merged: bool = False, merged_since=None) -> list[dict]:
    season = (await db.execute(text("""
        SELECT id, rules FROM fantasy_seasons WHERE organisation_id = CAST(:o AS UUID)
        ORDER BY season_year DESC LIMIT 1"""), {"o": str(org_id)})).first()
    if season is None:
        return []
    fs_id, rules = season
    rules = rules or DEFAULT_RULES
    size = rules.get("squad_size", 12)
    quota = rules.get("role_quota", DEFAULT_RULES["role_quota"])
    pool = [dict(r) for r in (await db.execute(text("""
        SELECT pp.player_id, p.name, pp.role, pp.total_points, pp.current_price
        FROM fantasy_pool_players pp JOIN players p ON p.id = pp.player_id
        WHERE pp.fantasy_season_id = :f AND pp.is_available"""), {"f": fs_id})).mappings().all()]
    if only_merged:
        eligible = await merged_player_ids(db, org_id, merged_since)
        pool = [r for r in pool if str(r["player_id"]) in eligible]
    pool.sort(key=lambda r: (-float(r["total_points"]), -float(r["current_price"]), r["name"] or ""))
    plans = []
    for sq in (await db.execute(text("""
        SELECT id, team_name FROM fantasy_squads WHERE fantasy_season_id = :f ORDER BY team_name"""), {"f": fs_id})).mappings().all():
        picks = (await db.execute(text(
            "SELECT player_id, role FROM fantasy_squad_players WHERE squad_id = :s"), {"s": sq["id"]})).all()
        if len(picks) >= size:
            continue
        held = {str(p[0]) for p in picks}
        have: dict[str, int] = {}
        for _pid, role in picks:
            have[role] = have.get(role, 0) + 1
        chosen = []
        for _ in range(size - len(picks)):
            deficits = {r: quota.get(r, 0) - have.get(r, 0) for r in ROLE_ORDER}
            want = max((r for r in ROLE_ORDER if deficits[r] > 0), key=lambda r: deficits[r], default=None)
            cands = [c for c in pool if str(c["player_id"]) not in held]
            pick = next((c for c in cands if c["role"] == want), None) if want else None
            pick = pick or (cands[0] if cands else None)
            if pick is None:
                break
            chosen.append(pick)
            held.add(str(pick["player_id"]))
            have[pick["role"]] = have.get(pick["role"], 0) + 1
        plans.append({"squad_id": str(sq["id"]), "team_name": sq["team_name"], "season_id": str(fs_id),
                      "has": len(picks), "size": size, "adds": chosen})
    return plans


async def apply_fill(db: AsyncSession, org_id, plans: list[dict], user_id=None, from_round: int = 1) -> int:
    """Insert the planned picks, write an audit entry per team and score the rounds
    again. The caller commits."""
    n = 0
    for plan in plans:
        for c in plan["adds"]:
            db.add(FantasySquadPlayer(squad_id=plan["squad_id"], player_id=c["player_id"], role=c["role"],
                                      purchase_price=c["current_price"], added_round=from_round))
            n += 1
        await db.flush()
        await db.execute(text("""
            INSERT INTO audit_logs (org_id, user_id, action, target_type, target_id, details)
            VALUES (CAST(:o AS UUID), :u, 'fantasy_fill_short_team', 'fantasy_squad', :s, CAST(:d AS JSONB))
        """), {"o": str(org_id), "u": str(user_id) if user_id else None, "s": plan["squad_id"],
               "d": json.dumps({"added": [{"player_id": str(c["player_id"]), "name": c["name"], "points": float(c["total_points"])}
                                          for c in plan["adds"]], "from_round": from_round})})
    for sid in {p["season_id"] for p in plans}:
        await fantasy_engine.rescore_from_round(db, await db.get(FantasySeason, sid), from_round)
    return n
