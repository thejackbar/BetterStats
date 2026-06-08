"""Backfill `batting_innings.caught_behind` for an organisation.

The wicketkeeper-catch ("caught behind") signal lives only as a dagger (†)
before the catcher's name in CA's scorecard `dismissalText`. Sync now captures
it going forward (migration 075), but existing rows have `caught_behind = NULL`.
This re-fetches each game's scorecard, re-parses the keeper marker for our
batters' *caught* dismissals, and updates the flag in place — WITHOUT touching
runs/balls/dismissal_type or any other table.

Roughly the same network cost as a Full Rebuild (one scorecard fetch per game)
but only updates `batting_innings.caught_behind`, so it's far faster and the
blast radius is contained. Re-runnable (idempotent).

Usage from the backend container:
  docker exec -e PYTHONPATH=/app betterstats-backend \\
    python -m app.scripts.backfill_caught_behind <org_id>
"""

import asyncio
import sys
import uuid

from sqlalchemy import select, text as sql_text

from app.models.db import Player, async_session_maker
from app.services.sync import _caught_by_keeper
from app.services.grassroots_scores_client import get_match_scorecard


async def _build_merge_map(session, org_id: uuid.UUID) -> dict:
    """alias→canonical map, transitively resolved, matching sync.py behavior."""
    result = await session.execute(
        sql_text(
            "SELECT removed_player_id, keep_player_id FROM merge_logs "
            "WHERE org_id = :org_id AND undone_at IS NULL"
        ),
        {"org_id": str(org_id)},
    )
    raw = {r[0]: r[1] for r in result.all()}
    resolved: dict = {}
    for removed in raw:
        target = raw[removed]
        seen = {removed}
        while target in raw and target not in seen:
            seen.add(target)
            target = raw[target]
        resolved[removed] = target
    return resolved


async def backfill_for_org(org_id_str: str) -> None:
    org_id = uuid.UUID(org_id_str)
    org_id_str_lower = org_id_str.lower()

    async with async_session_maker() as session:
        players = await session.execute(
            select(Player.id, Player.grassroots_id).where(Player.organisation_id == org_id)
        )
        pid_by_guid: dict = {}  # raw CA participant GUID -> this org's player id
        for _pid, _gid in players.all():
            if _gid:
                try:
                    pid_by_guid[uuid.UUID(str(_gid))] = _pid
                except (ValueError, TypeError):
                    pass

        merged_away = await _build_merge_map(session, org_id)

        games = await session.execute(
            sql_text(
                "SELECT DISTINCT g.id FROM games g "
                "JOIN grades gr ON gr.id = g.grade_id "
                "JOIN seasons s ON s.id = gr.season_id "
                "WHERE s.organisation_id = :org_id "
                "ORDER BY g.id"
            ),
            {"org_id": str(org_id)},
        )
        game_ids = [r[0] for r in games.all()]

    print(
        f"Loaded {len(pid_by_guid)} players, {len(merged_away)} active merges. "
        f"Re-parsing {len(game_ids)} games for caught-behind..."
    )

    def _team_pid(guid: uuid.UUID | None):
        """raw CA participant GUID -> this org's player id (identity for legacy
        single-club rows), following active merges. None if not one of ours."""
        if guid is None:
            return None
        p = pid_by_guid.get(guid)
        if p is None:
            p = merged_away.get(guid)
            if p is None:
                return None
        else:
            p = merged_away.get(p, p)
        return p

    updated_total = 0
    errors = 0
    for i, gid in enumerate(game_ids, start=1):
        try:
            scorecard = await get_match_scorecard(str(gid))
            if not scorecard:
                continue
            updates: list[dict] = []
            for inn in (scorecard.get("innings") or []):
                inn_num = inn.get("inningsOrder") or inn.get("inningsNumber") or 1
                for row in (inn.get("batting") or []):
                    if (row.get("dismissalType") or "") != "Caught":
                        continue  # flag only meaningful for catches
                    try:
                        pid = _team_pid(uuid.UUID(row.get("participantId") or ""))
                    except ValueError:
                        pid = None
                    if pid is None:
                        continue  # opposition / unknown batter — not our row
                    updates.append({
                        "gid": gid, "inn": inn_num, "pid": pid,
                        "cb": _caught_by_keeper(row.get("dismissalText") or ""),
                    })
            if updates:
                async with async_session_maker() as session:
                    for u in updates:
                        await session.execute(
                            sql_text(
                                "UPDATE batting_innings SET caught_behind = :cb "
                                "WHERE game_id = :gid AND innings_number = :inn "
                                "AND player_id = :pid"
                            ),
                            u,
                        )
                    await session.commit()
                updated_total += len(updates)
        except Exception as exc:
            errors += 1
            print(f"  err on {gid}: {exc}")
        if i % 100 == 0:
            print(f"  [{i}/{len(game_ids)}] updated {updated_total} so far ({errors} errors)")

    print(
        f"Done. Set caught_behind on {updated_total} caught dismissals across "
        f"{len(game_ids)} games ({errors} errors)."
    )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m app.scripts.backfill_caught_behind <org_id>")
        sys.exit(1)
    asyncio.run(backfill_for_org(sys.argv[1]))
