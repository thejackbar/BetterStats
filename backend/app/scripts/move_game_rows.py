"""Move one player's rows for named games to another player of the same club. Dry run unless --apply.

For a game synced AFTER a merge was undone: the rows were credited to the player the id used to be
merged into, and nothing moves them back. This hands them to the right player, for the games you name
and nothing else. It never deletes a row.

WHAT IT MOVES (rows for the named games only, from one player to the other):
  game_appearances, batting_innings, bowling_spells, fielding_stats, fall_of_wickets, bowler_wickets
  (as bowler and as fielder), partnerships (batter 1 and 2), milestones tied to the game.
NOT TOUCHED: player_season_stats and player_season_grade_stats (a sync of the season rewrites them from
  Cricket Australia's totals), hand-typed games, and any other table. Check the season afterwards.

SAFETY
  * Both players must be the club's. Dry run by default: prints what would move.
  * Refuses a game where the receiving player already has any row, so nothing can collide.
  * `--apply` needs `--by "name"`. The ids of everything moved are written to one `audit_logs` entry
    in the same transaction as the change; if that write fails nothing changes.
  * `--restore AUDIT_ID` moves it all back from that entry. An entry restores once.

Usage, from the server:
  cd /srv/docker && export COMPOSE_PROJECT_NAME=bltbox_docker_app
  docker compose exec -T betterstats-backend python -m app.scripts.move_game_rows <club> <from-player-id> <to-player-id> <game-id> [<game-id> ...]
  ... add --apply --by "name" to move; --restore AUDIT_ID --by "name" to undo.
"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid

from sqlalchemy import text

from app.models.db import async_session_maker

ACTION = "move_game_rows"
RESTORE_ACTION = "restore_game_rows"

# (table, column holding the player, has an id column)
PLACES = (
    ("game_appearances", "player_id", False),
    ("batting_innings", "player_id", True),
    ("bowling_spells", "player_id", True),
    ("fielding_stats", "player_id", True),
    ("fall_of_wickets", "player_id", True),
    ("bowler_wickets", "bowler_id", True),
    ("bowler_wickets", "fielder_id", True),
    ("partnerships", "batter1_id", True),
    ("partnerships", "batter2_id", True),
    ("milestones", "player_id", True),
)


async def _club(db, ref: str):
    row = (await db.execute(text("SELECT id, name FROM organisations WHERE id::text = :o OR slug = :o"), {"o": ref})).first()
    if not row:
        raise SystemExit(f"no club matches {ref!r}")
    return row


async def _player_ok(db, club_id, pid) -> bool:
    return (await db.execute(text("SELECT 1 FROM players WHERE id = :p AND organisation_id = :o"),
                             {"p": pid, "o": club_id})).first() is not None


async def _rows(db, table, col, has_id, player, games) -> list:
    key = "id" if has_id else "game_id"
    res = await db.execute(
        text(f"SELECT {key} FROM {table} WHERE {col} = :p AND game_id = ANY(CAST(:g AS uuid[]))"),
        {"p": player, "g": games})
    return [r[0] for r in res.fetchall()]


async def plan(db, src, dst, games) -> tuple[dict, int]:
    """What would move, and how many rows the receiver already holds for these games."""
    moves, clash = {}, 0
    for table, col, has_id in PLACES:
        mine = await _rows(db, table, col, has_id, src, games)
        theirs = await _rows(db, table, col, has_id, dst, games)
        clash += len(theirs)
        if mine:
            moves[f"{table}.{col}"] = [str(x) if not isinstance(x, int) else x for x in mine]
    return moves, clash


async def run(club_ref, src, dst, games, apply, by) -> int:
    for g in games + [src, dst]:
        uuid.UUID(g)
    async with async_session_maker() as db:
        club_id, club_name = await _club(db, club_ref)
        if not await _player_ok(db, club_id, src) or not await _player_ok(db, club_id, dst):
            print("STOP: both players must be players of this club.")
            return 1
        moves, clash = await plan(db, src, dst, games)
    print(f"{club_name}: {'APPLY' if apply else 'dry run'}")
    print(f"  from {src}\n    to {dst}")
    for k, v in moves.items():
        print(f"  {k}: {len(v)} row(s)")
    if not moves:
        print("  nothing to move: the first player holds no rows for these games.")
        return 1
    if clash:
        print(f"  STOP: the receiving player already has {clash} row(s) in these games. Nothing moved.")
        return 1
    print("  not touched: player_season_stats and player_season_grade_stats (the next sync of the season rewrites them).")
    if not apply:
        print("\nDry run: nothing changed. Run again with --apply --by \"name\".")
        return 0
    if not by:
        print("STOP: --apply needs --by \"name\".")
        return 1
    async with async_session_maker() as db:
        for key, ids in moves.items():
            table, col = key.split(".")
            if table == "game_appearances":
                await db.execute(text("UPDATE game_appearances SET player_id = :d WHERE player_id = :s AND game_id = ANY(CAST(:g AS uuid[]))"),
                                 {"d": dst, "s": src, "g": ids})
            else:
                await db.execute(text(f"UPDATE {table} SET {col} = :d WHERE id = ANY(:ids)"), {"d": dst, "ids": ids})
        await db.execute(
            text("INSERT INTO audit_logs (org_id, action, target_type, target_id, details) "
                 "VALUES (:o, :a, 'player', :t, CAST(:d AS JSONB))"),
            {"o": club_id, "a": ACTION, "t": dst,
             "d": json.dumps({"from": src, "to": dst, "games": games, "moved": moves, "by": by})})
        await db.commit()
    print("  MOVED. The audit entry id is in audit_logs (action move_game_rows); restore with --restore AUDIT_ID.")
    return 0


async def restore(club_ref, audit_id, by) -> int:
    async with async_session_maker() as db:
        club_id, club_name = await _club(db, club_ref)
        row = (await db.execute(text("SELECT details FROM audit_logs WHERE id = :i AND org_id = :o AND action = :a"),
                                {"i": audit_id, "o": club_id, "a": ACTION})).first()
        if not row:
            print("STOP: no such move for this club.")
            return 1
        done = (await db.execute(text("SELECT 1 FROM audit_logs WHERE org_id = :o AND action = :a AND details->>'restored_id' = :i"),
                                 {"o": club_id, "a": RESTORE_ACTION, "i": str(audit_id)})).first()
        if done:
            print("STOP: that move was already restored.")
            return 1
        d = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        for key, ids in d["moved"].items():
            table, col = key.split(".")
            if table == "game_appearances":
                await db.execute(text("UPDATE game_appearances SET player_id = :s WHERE player_id = :d AND game_id = ANY(CAST(:g AS uuid[]))"),
                                 {"s": d["from"], "d": d["to"], "g": ids})
            else:
                await db.execute(text(f"UPDATE {table} SET {col} = :s WHERE id = ANY(:ids) AND {col} = :d"),
                                 {"s": d["from"], "d": d["to"], "ids": ids})
        await db.execute(
            text("INSERT INTO audit_logs (org_id, action, target_type, target_id, details) "
                 "VALUES (:o, :a, 'player', :t, CAST(:d AS JSONB))"),
            {"o": club_id, "a": RESTORE_ACTION, "t": d["from"], "d": json.dumps({"restored_id": str(audit_id), "by": by})})
        await db.commit()
    print(f"{club_name}: restored audit entry {audit_id}.")
    return 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    by = ""
    if "--by" in argv:
        i = argv.index("--by")
        by = argv[i + 1] if i + 1 < len(argv) else ""
        del argv[i:i + 2]
    if "--restore" in argv:
        i = argv.index("--restore")
        aid = int(argv[i + 1])
        del argv[i:i + 2]
        if len(argv) != 1 or not by:
            raise SystemExit(__doc__)
        sys.exit(asyncio.run(restore(argv[0], aid, by)))
    pos = [a for a in argv if not a.startswith("--")]
    if len(pos) < 4:
        raise SystemExit(__doc__)
    sys.exit(asyncio.run(run(pos[0], pos[1], pos[2], pos[3:], "--apply" in argv, by)))
