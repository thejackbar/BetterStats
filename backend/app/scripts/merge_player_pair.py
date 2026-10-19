"""Merge ONE named pair of players for a club: the same person held under two profiles.

The Admin Manual Merge, with the two ids typed in and a report first. It runs the
SHIPPED merge (`routers/admin._merge_players_core`), so everything a merge moves, it
moves: games, stats, squads, availability, the profile, and the rest of
`services/merge_carry.CARRIED`. Nothing is deleted that a person wrote; the removed
player is in the merge log and the merge can be undone (`undo_player_merge`).

Why a script: a Cricket Australia-redacted junior is named `********`, so the Manual
Merge screen cannot find him by name, and its choice of which record to keep is a
guess. Here you say which one stays.

Dry run by default: it reports both players and changes nothing.

    python -m app.scripts.merge_player_pair <org-id-or-slug> <keep-player-id> <remove-player-id> [--apply] [--by "name"] [--allow-shared-games]

The two players must be in the club. If both rows appear in the SAME game they are
almost certainly two people (nobody is in one XI twice) and it refuses unless you
pass --allow-shared-games.

From the server:

    cd /srv/docker && export COMPOSE_PROJECT_NAME=bltbox_docker_app
    docker compose exec -T betterstats-backend python -m app.scripts.merge_player_pair \
        gisborne-cricket-club <keep-id> <remove-id>
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import text

from app.models.db import async_session_maker


async def _club(db, target: str):
    row = (await db.execute(
        text("SELECT id, name FROM organisations WHERE id::text = :o OR slug = :o"), {"o": target}
    )).first()
    if not row:
        raise SystemExit(f"no club matches {target!r}")
    return row


async def describe(db, club_id, player_id) -> dict | None:
    """Read only: what we hold against one player. None when not this club's."""
    p = (await db.execute(
        text("SELECT id, name, status, is_player, grassroots_id FROM players "
             "WHERE id = :id AND organisation_id = :org"), {"id": player_id, "org": club_id})).first()
    if not p:
        return None
    g = (await db.execute(
        text("SELECT COUNT(*), MIN(g.played_at), MAX(g.played_at) FROM game_appearances ga "
             "JOIN games g ON g.id = ga.game_id WHERE ga.player_id = :id"), {"id": player_id})).first()
    live_into = (await db.execute(
        text("SELECT COUNT(*) FROM merge_logs WHERE org_id = :org AND keep_player_id = :id AND undone_at IS NULL"),
        {"org": club_id, "id": player_id})).scalar()
    squads = (await db.execute(
        text("SELECT COUNT(*) FROM team_members WHERE player_id = :id"), {"id": player_id})).scalar()
    avail = (await db.execute(
        text("SELECT COUNT(*) FROM player_availability WHERE player_id = :id"), {"id": player_id})).scalar()
    return {
        "id": p[0], "name": p[1], "status": p[2], "is_player": p[3], "grassroots_id": p[4],
        "games": g[0], "first": g[1], "last": g[2], "merged_into_it": live_into,
        "squads": squads, "availability_rows": avail,
    }


async def shared_games(db, a, b) -> int:
    return (await db.execute(
        text("SELECT COUNT(*) FROM game_appearances x JOIN game_appearances y ON y.game_id = x.game_id "
             "WHERE x.player_id = :a AND y.player_id = :b"), {"a": a, "b": b})).scalar()


def _print(role: str, d: dict) -> None:
    span = f"{d['first']} to {d['last']}" if d["games"] else "no games"
    print(f"  {role}: {d['id']}  name={d['name']!r}  status={d['status']}  is_player={d['is_player']}")
    print(f"        {d['games']} games ({span}); {d['merged_into_it']} live merge(s) already into it; "
          f"{d['squads']} squad row(s), {d['availability_rows']} availability row(s)")


async def run(target: str, keep: str, remove: str, apply: bool, by: str, allow_shared: bool) -> int:
    from app.routers.admin import _merge_players_core
    from app.services.audit_log import log_activity

    try:
        keep_id, remove_id = uuid.UUID(keep), uuid.UUID(remove)
    except ValueError:
        raise SystemExit("keep and remove must be player ids (uuids)")
    if keep_id == remove_id:
        raise SystemExit("keep and remove are the same player")
    async with async_session_maker() as db:
        club_id, club_name = await _club(db, target)
        k = await describe(db, club_id, keep_id)
        r = await describe(db, club_id, remove_id)
        shared = await shared_games(db, keep_id, remove_id) if k and r else 0
    print(f"{club_name}: {'APPLY' if apply else 'dry run'}")
    for role, who, pid in (("KEEP  ", k, keep_id), ("REMOVE", r, remove_id)):
        if who is None:
            print(f"  {role}: {pid} is not a player of this club")
    if k is None or r is None:
        return 1
    _print("KEEP  ", k)
    _print("REMOVE", r)
    print(f"  games both appear in: {shared}")
    if shared and not allow_shared:
        print("  REFUSED: both rows are in the same game, so they are probably two different people. "
              "Pass --allow-shared-games only if you have checked.")
        return 1
    if k["status"] == "inactive":
        print("  note: the kept player is inactive; set it Active after the merge if they play now")
    if not apply:
        print("\nDry run: nothing changed. Run again with --apply.")
        return 0
    async with async_session_maker() as db:
        try:
            res = await _merge_players_core(db, keep_id, remove_id, club_id, SimpleNamespace(id=None))
        except HTTPException as e:
            await db.rollback()
            print(f"  FAILED: {e.detail}")
            return 1
        await log_activity(
            db, org_id=club_id, action="merge_players_script", target_type="player", target_id=str(keep_id),
            details={"removed_player_id": str(remove_id), "by": by}, commit=True,
        )
    print(f"  MERGED: {remove_id} into {res['kept_player_id']}. Undo with undo_player_merge "
          "(the merge log id is in Admin merge history).")
    return 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    by = "script"
    if "--by" in argv:
        i = argv.index("--by")
        by = argv[i + 1] if i + 1 < len(argv) else by
        del argv[i:i + 2]
    pos = [a for a in argv if not a.startswith("--")]
    if len(pos) != 3:
        raise SystemExit(__doc__)
    sys.exit(asyncio.run(run(pos[0], pos[1], pos[2], "--apply" in argv, by, "--allow-shared-games" in argv)))
