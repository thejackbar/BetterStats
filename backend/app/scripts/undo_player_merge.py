"""Undo one or more player merges for a club, from the merge log.

The Admin screen's Undo button, for when you want to see first what it would move
or to undo several in one go. It runs the SHIPPED undo (`routers/admin.undo_merge`),
so it moves back exactly what the merge recorded and no more.

A merge moves records and never deletes them: undoing it re-creates the removed
player (same id, same Cricket Australia id) and hands back the rows the merge
recorded. Games that synced AFTER the merge are not in the log; they stay on the kept
player until the next sync.

Dry run by default: it reports each merge and changes nothing.

    python -m app.scripts.undo_player_merge <org-id-or-slug> <merge-log-id> [<merge-log-id> ...] [--apply] [--by "name"]

Undo the NEWEST merge first when several touch the same player; they are run in the
order given. Every undo is in `audit_logs` (`undo_merge_players`, plus one
`undo_merge_players_script` entry saying who asked), and the merge can be redone.

From the server:

    cd /srv/docker && export COMPOSE_PROJECT_NAME=bltbox_docker_app
    docker compose exec -T betterstats-backend python -m app.scripts.undo_player_merge \
        gisborne-cricket-club 8107
"""
from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import text

from app.models.db import async_session_maker

# The id lists a merge records, as they are named in merge_logs.
RECORDED = (
    "moved_season_stat_ids", "batting_innings_ids", "bowling_spell_ids", "fielding_stat_ids",
    "fall_of_wicket_ids", "batter1_partnership_ids", "batter2_partnership_ids", "milestone_ids",
    "bowler_wicket_ids", "fielder_wicket_ids", "grade_stat_ids", "appearance_game_ids",
)


def _size(value) -> int:
    return len(value) if isinstance(value, list) else 0


async def _club(db, target: str):
    row = (await db.execute(
        text("SELECT id, name FROM organisations WHERE id::text = :o OR slug = :o"), {"o": target}
    )).first()
    if not row:
        raise SystemExit(f"no club matches {target!r}")
    return row


async def describe(db, club_id, log_id: int) -> dict | None:
    """What this undo would do, read only. None when the log is not this club's."""
    log = (await db.execute(
        text("SELECT * FROM merge_logs WHERE id = :id AND org_id = :org"), {"id": log_id, "org": club_id}
    )).mappings().first()
    if not log:
        return None
    keep_id, removed_id = log["keep_player_id"], log["removed_player_id"]
    keep = (await db.execute(
        text("SELECT id, status FROM players WHERE id = :id"), {"id": keep_id})).first()
    removed_exists = (await db.execute(
        text("SELECT 1 FROM players WHERE id = :id"), {"id": removed_id})).first() is not None
    # Appearances the merge moved that still sit on the kept player.
    appear = log.get("appearance_game_ids") or []
    still_on_keep = 0
    span = (None, None)
    if appear:
        row = (await db.execute(
            text("SELECT COUNT(*), MIN(g.played_at), MAX(g.played_at) FROM game_appearances ga "
                 "JOIN games g ON g.id = ga.game_id "
                 "WHERE ga.player_id = :k AND ga.game_id::text = ANY(:ids)"),
            {"k": keep_id, "ids": appear})).first()
        still_on_keep, span = row[0], (row[1], row[2])
    # A later live merge that used either player is the thing to undo first.
    later = (await db.execute(
        text("SELECT id FROM merge_logs WHERE org_id = :org AND undone_at IS NULL AND id > :id "
             "AND (keep_player_id IN (:k, :r) OR removed_player_id IN (:k, :r)) ORDER BY id"),
        {"org": club_id, "id": log_id, "k": keep_id, "r": removed_id})).scalars().all()
    return {
        "log_id": log_id, "merged_at": log["merged_at"], "undone_at": log["undone_at"],
        "keep_id": keep_id, "keep_exists": keep is not None, "keep_status": keep[1] if keep else None,
        "removed_id": removed_id, "removed_exists": removed_exists,
        "recorded": {k: _size(log.get(k)) for k in RECORDED if _size(log.get(k))},
        "appearances_on_keep": still_on_keep, "span": span, "later_merges": list(later),
    }


def _print(d: dict) -> None:
    print(f"\nmerge {d['log_id']}  ({d['merged_at']:%Y-%m-%d %H:%M})")
    print(f"  removed {d['removed_id']}  ->  kept {d['keep_id']} (status {d['keep_status']})")
    if d["undone_at"]:
        print(f"  ALREADY UNDONE at {d['undone_at']:%Y-%m-%d %H:%M}; nothing to do")
        return
    if not d["keep_exists"]:
        print("  REFUSED: the kept player no longer exists")
    if d["removed_exists"]:
        print("  note: a player with the removed id already exists; undo leaves it as it is and moves the rows to it")
    rec = ", ".join(f"{k.replace('_ids', '')}={n}" for k, n in d["recorded"].items()) or "nothing recorded"
    print(f"  rows recorded by the merge: {rec}")
    if d["appearances_on_keep"]:
        a, b = d["span"]
        print(f"  games to move back: {d['appearances_on_keep']} ({a} to {b})")
    if d["later_merges"]:
        print(f"  WARNING: newer live merge(s) {d['later_merges']} use these players. Undo those first.")


async def run(target: str, log_ids: list[int], apply: bool, by: str) -> int:
    from app.routers.admin import UndoMergeRequest, undo_merge
    from app.services.audit_log import log_activity

    async with async_session_maker() as db:
        club_id, club_name = await _club(db, target)
    print(f"{club_name}: {'APPLY' if apply else 'dry run'}")
    failed = 0
    for log_id in log_ids:
        async with async_session_maker() as db:
            d = await describe(db, club_id, log_id)
        if d is None:
            print(f"\nmerge {log_id}: not found for this club")
            failed += 1
            continue
        _print(d)
        if d["undone_at"]:
            continue
        if not apply:
            continue
        if d["later_merges"]:
            print("  SKIPPED: undo the newer merge(s) first")
            failed += 1
            continue
        async with async_session_maker() as db:
            try:
                res = await undo_merge(
                    UndoMergeRequest(merge_log_id=log_id, org_id=str(club_id)),
                    db=db, current_user=SimpleNamespace(id=None),
                )
            except HTTPException as e:
                await db.rollback()
                print(f"  FAILED: {e.detail}")
                failed += 1
                continue
            await log_activity(
                db, org_id=club_id, action="undo_merge_players_script", target_type="player",
                target_id=str(d["removed_id"]), details={"merge_log_id": log_id, "by": by}, commit=True,
            )
        print(f"  UNDONE: restored player {res['restored_player_id']}")
    if not apply:
        print("\nDry run: nothing changed. Run again with --apply.")
    return 1 if failed else 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    by = "script"
    if "--by" in argv:
        i = argv.index("--by")
        by = argv[i + 1] if i + 1 < len(argv) else by
        del argv[i:i + 2]
    pos = [a for a in argv if not a.startswith("--")]
    if len(pos) < 2 or not all(p.isdigit() for p in pos[1:]):
        raise SystemExit(__doc__)
    sys.exit(asyncio.run(run(pos[0], [int(p) for p in pos[1:]], "--apply" in argv, by)))
