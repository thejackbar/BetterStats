"""Put back the Fantasy picks that a player merge used to delete.

Until the merge learned to carry the Fantasy tables (see `merge_carry`), merging a
hand-added player into their real record removed them from every team that had
picked them: the picks were `ON DELETE CASCADE`. The rows are gone, but every
scored round stores a snapshot of each squad's lineup with the player's id in it,
and the merge log says who was merged into whom and when. A squad whose latest
snapshot from before the merge names the removed player, and which does not hold
the keeper now, lost him to that merge.

Conservative on purpose: the latest snapshot before the merge, so a player the
manager had already transferred out is not put back; a captain's armband only when
the team has none; nothing is deleted. A team that is short of players with no
evidence is listed, not guessed at, so an admin can fix it by hand (Registered
players > the team > Add player).
"""
from __future__ import annotations

import json
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import FantasyPoolPlayer, FantasySeason, FantasySquadPlayer
from app.services import fantasy_engine
from app.services.fantasy_scoring import DEFAULT_RULES

logger = logging.getLogger(__name__)


async def find_lost_picks(db: AsyncSession, org_id) -> list[dict]:
    """Squads that lost a merged-away player, with the evidence for each."""
    merges = (await db.execute(text("""
        SELECT id, merged_at, removed_player_id, keep_player_id, removed_player_name
        FROM merge_logs
        WHERE org_id = CAST(:o AS UUID) AND undone_at IS NULL AND removed_player_id IS NOT NULL
        ORDER BY merged_at
    """), {"o": str(org_id)})).mappings().all()
    found: list[dict] = []
    for m in merges:
        rid, kid = str(m["removed_player_id"]), str(m["keep_player_id"])
        rows = (await db.execute(text("""
            SELECT sq.id AS squad_id, sq.team_name, sq.fantasy_season_id, r.round_number, srs.lineup
            FROM fantasy_squad_round_scores srs
            JOIN fantasy_squads sq ON sq.id = srs.squad_id
            JOIN fantasy_rounds r ON r.id = srs.round_id
            WHERE sq.organisation_id = CAST(:o AS UUID)
              AND r.scored_at IS NOT NULL AND r.scored_at <= :at
              AND srs.lineup::text <> '[]'
            ORDER BY sq.id, r.round_number
        """), {"o": str(org_id), "at": m["merged_at"]})).mappings().all()
        by_squad: dict[str, list] = {}
        for r in rows:
            by_squad.setdefault(str(r["squad_id"]), []).append(r)
        for squad_id, snaps in by_squad.items():
            latest = snaps[-1]                      # the last scored round before the merge
            entry = next((e for e in (latest["lineup"] or []) if str(e.get("player_id")) == rid), None)
            if entry is None:
                continue
            holds_keeper = (await db.execute(text(
                "SELECT 1 FROM fantasy_squad_players WHERE squad_id = CAST(:s AS UUID) AND player_id = CAST(:p AS UUID)"),
                {"s": squad_id, "p": kid})).scalar()
            if holds_keeper:
                continue
            first = next(s["round_number"] for s in snaps
                         if any(str(e.get("player_id")) == rid for e in (s["lineup"] or [])))
            found.append({
                "squad_id": squad_id, "team_name": latest["team_name"],
                "season_id": str(latest["fantasy_season_id"]),
                "merge_id": m["id"], "removed_id": rid, "keep_id": kid, "player_name": m["removed_player_name"],
                "role": entry.get("role") or "batter",
                "was_captain": bool(entry.get("is_captain")), "was_vice": bool(entry.get("is_vice")),
                "first_round": first,
            })
    return found


async def find_short_squads(db: AsyncSession, org_id, exclude_ids: set[str]) -> list[dict]:
    """Teams with fewer players than their season's rules want, that the snapshots
    do not explain."""
    out = []
    for fs in (await db.execute(
        text("SELECT id, rules FROM fantasy_seasons WHERE organisation_id = CAST(:o AS UUID)"), {"o": str(org_id)}
    )).mappings().all():
        size = (fs["rules"] or DEFAULT_RULES).get("squad_size", 12)
        for r in (await db.execute(text("""
            SELECT sq.id, sq.team_name, COUNT(sp.id) AS n
            FROM fantasy_squads sq LEFT JOIN fantasy_squad_players sp ON sp.squad_id = sq.id
            WHERE sq.fantasy_season_id = CAST(:f AS UUID)
            GROUP BY sq.id, sq.team_name HAVING COUNT(sp.id) < :size
        """), {"f": str(fs["id"]), "size": size})).mappings().all():
            if str(r["id"]) not in exclude_ids:
                out.append({"squad_id": str(r["id"]), "team_name": r["team_name"], "players": int(r["n"]), "wanted": size})
    return out


async def restore(db: AsyncSession, org_id, found: list[dict], user_id=None) -> int:
    """Put each found pick back, add the keeper to the pool if they are not in it,
    write an audit entry per team, and score the affected rounds again. The caller
    commits."""
    restored = 0
    seasons_done: dict[str, int] = {}
    for f in found:
        fs = await db.get(FantasySeason, f["season_id"])
        pool = (await db.execute(
            text("SELECT role, current_price FROM fantasy_pool_players WHERE fantasy_season_id = CAST(:f AS UUID) "
                 "AND player_id = CAST(:p AS UUID)"), {"f": f["season_id"], "p": f["keep_id"]},
        )).first()
        if pool is None:
            _role, price = await fantasy_engine.classify_and_price_one(db, fs, f["keep_id"])
            db.add(FantasyPoolPlayer(
                fantasy_season_id=fs.id, organisation_id=org_id, player_id=f["keep_id"], role=f["role"],
                role_source="admin", base_price=price, current_price=price, is_available=True))
            await db.flush()
            price_now = price
        else:
            price_now = pool[1]
        has_cap, has_vice = (await db.execute(text(
            "SELECT bool_or(is_captain), bool_or(is_vice_captain) FROM fantasy_squad_players WHERE squad_id = CAST(:s AS UUID)"),
            {"s": f["squad_id"]})).first()
        db.add(FantasySquadPlayer(
            squad_id=f["squad_id"], player_id=f["keep_id"], role=f["role"], purchase_price=price_now,
            is_captain=bool(f["was_captain"] and not has_cap), is_vice_captain=bool(f["was_vice"] and not has_vice),
            added_round=f["first_round"]))
        await db.flush()
        await db.execute(text("""
            INSERT INTO audit_logs (org_id, user_id, action, target_type, target_id, details)
            VALUES (CAST(:o AS UUID), :u, 'fantasy_restore_merged_pick', 'fantasy_squad', :s, CAST(:d AS JSONB))
        """), {"o": str(org_id), "u": str(user_id) if user_id else None, "s": f["squad_id"],
               "d": json.dumps({"player": f["player_name"], "removed_id": f["removed_id"], "keep_id": f["keep_id"],
                                "merge_id": f["merge_id"], "from_round": f["first_round"]})})
        seasons_done[f["season_id"]] = min(f["first_round"], seasons_done.get(f["season_id"], 10 ** 6))
        restored += 1
    for sid, from_round in seasons_done.items():
        await fantasy_engine.rescore_from_round(db, await db.get(FantasySeason, sid), from_round)
    return restored
