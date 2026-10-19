"""Verification: Fantasy counts a player's fielding from EVERY innings of a game, not the last. Real Postgres.

Reported (Leederville, Oct 2026): after a round that held a two-day game, points looked
short for fielders, e.g. a player with three catches reading 21. Sync writes one
`fielding_stats` row per innings the player fielded in, so a two-day game gives a fielder
up to two rows. `fantasy_engine._round_player_scores` assigned each row's catches, run outs
and stumpings onto the game's cell (`=`), so the last row replaced the first and only one
innings was scored. Batting and bowling were already appended per innings.

Runs the SHIPPED `fantasy_engine._round_player_scores` over the `v_effective_*` views.

Run:  DATABASE_URL=postgresql+asyncpg://postgres:pw@127.0.0.1:5432/betterstats_verify \
      python verification/verify_fantasy_multi_innings_fielding.py
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import text

import verify_fantasy_unsettle as base
from app.models.db import FantasyRound, FantasySeason
from app.services import fantasy_engine

Session, check = base.Session, base.check


async def main() -> int:
    await base.build_schema()
    await base.seed()
    async with Session() as s:
        # The running round's game (A scored 30 in it): two innings of fielding for A, one for B.
        gid = (await s.execute(text(
            "SELECT g.id FROM games g JOIN game_appearances ga ON ga.game_id = g.id "
            "WHERE ga.player_id = :a AND g.played_at = (SELECT MAX(played_at) FROM games)"), {"a": base.A})).scalar()
        for pid, c, wk, ro, st in ((base.A, 2, 0, 0, 0), (base.A, 1, 0, 1, 0),
                                   (base.B, 1, 0, 0, 0)):
            await s.execute(text(
                "INSERT INTO fielding_stats (game_id, player_id, catches, catches_wk, run_outs, stumpings) "
                "VALUES (:g, :p, :c, :wk, :ro, :st)"), {"g": gid, "p": pid, "c": c, "wk": wk, "ro": ro, "st": st})
        await s.execute(text("INSERT INTO game_appearances (game_id, player_id, team_name) "
                             "SELECT :g, :b, 'Alpha' WHERE NOT EXISTS (SELECT 1 FROM game_appearances "
                             "WHERE game_id = :g AND player_id = :b)"), {"g": gid, "b": base.B})
        await s.commit()
        fs = await s.get(FantasySeason, base.FS_ID)
        rnd = await s.get(FantasyRound, base.R2)
        scores = await fantasy_engine._round_player_scores(s, fs, rnd)

    a = scores.get(str(base.A)) or {}
    b = scores.get(str(base.B)) or {}
    bd_a = a.get("breakdown") or {}
    print("\n-- a two-innings fielder --")
    # 3 catches (8 each) and 1 run out (12) across two innings.
    check("A's fielding is every innings: 3 catches and a run out = 36",
          bd_a.get("fielding") == 36, f"got {bd_a.get('fielding')}")
    print("\n-- a one-innings fielder is unchanged --")
    check("B's single catch is 8", (b.get("breakdown") or {}).get("fielding") == 8,
          f"got {(b.get('breakdown') or {}).get('fielding')}")
    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    return 1 if base.FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
