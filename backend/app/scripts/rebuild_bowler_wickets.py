"""Backfill `bowler_wickets` for an organisation without doing a full rebuild.

Use after a parser change (new dismissalText format, etc) to repopulate
the table without wiping games / batting_innings / bowling_spells / etc.
Re-fetches each game's scorecard from CA and re-runs the bowler-wickets
extractor.

Usage from the backend container:
  docker exec -e PYTHONPATH=/app betterstats-backend \\
    python -m app.scripts.rebuild_bowler_wickets <org_id>

Roughly the same network cost as a Full Rebuild (one scorecard fetch per
game) but only touches `bowler_wickets`, so it's noticeably faster and
the blast radius is contained.
"""

import asyncio
import sys
import uuid

from sqlalchemy import select, text as sql_text

from app.models.db import Player, async_session_maker
from app.services.sync import extract_bowler_wickets
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


async def rebuild_for_org(org_id_str: str) -> None:
    org_id = uuid.UUID(org_id_str)

    async with async_session_maker() as session:
        players = await session.execute(
            select(Player.id).where(Player.organisation_id == org_id)
        )
        known_player_ids = {r[0] for r in players.all()}

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

        if game_ids:
            await session.execute(
                sql_text("DELETE FROM bowler_wickets WHERE game_id = ANY(:gids)"),
                {"gids": game_ids},
            )
            await session.commit()

    print(
        f"Loaded {len(known_player_ids)} players, "
        f"{len(merged_away)} active merges. "
        f"Wiped bowler_wickets for {len(game_ids)} games. Re-parsing..."
    )

    inserted_total = 0
    errors = 0
    for i, gid in enumerate(game_ids, start=1):
        try:
            scorecard = await get_match_scorecard(str(gid))
            if not scorecard:
                continue
            rows = extract_bowler_wickets(scorecard, gid, known_player_ids, merged_away)
            if rows:
                async with async_session_maker() as session:
                    for r in rows:
                        session.add(r)
                    await session.commit()
                inserted_total += len(rows)
        except Exception as exc:
            errors += 1
            print(f"  err on {gid}: {exc}")
        if i % 100 == 0:
            print(f"  [{i}/{len(game_ids)}] inserted {inserted_total} so far ({errors} errors)")

    print(
        f"Done. Inserted {inserted_total} bowler_wickets across "
        f"{len(game_ids)} games ({errors} errors)."
    )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m app.scripts.rebuild_bowler_wickets <org_id>")
        sys.exit(1)
    asyncio.run(rebuild_for_org(sys.argv[1]))
