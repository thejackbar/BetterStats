"""Backfill `bowler_wickets` for an organisation without doing a full rebuild.

Use after a parser change (new dismissalText format, etc) to repopulate
the table without wiping games / batting_innings / bowling_spells / etc.
Re-fetches each game's scorecard from CA and re-runs the bowler-wickets
extractor.

Also the way to back-fill `bowler_wickets.caught_behind` (migration 076) — the
extractor now records whether each caught wicket was off the keeper.

Usage from the backend container:
  # one club:
  docker exec -e PYTHONPATH=/app betterstats-backend \\
    python -m app.scripts.rebuild_bowler_wickets <org_id>
  # every club (no arg, or "all"):
  docker exec -e PYTHONPATH=/app betterstats-backend \\
    python -m app.scripts.rebuild_bowler_wickets all

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
            select(Player.id, Player.grassroots_id).where(Player.organisation_id == org_id)
        )
        known_player_ids = set()
        pid_by_guid: dict = {}  # raw CA participant GUID -> this org's player id (identity for legacy)
        for _pid, _gid in players.all():
            known_player_ids.add(_pid)
            if _gid:
                try:
                    pid_by_guid[uuid.UUID(str(_gid))] = _pid
                except (ValueError, TypeError):
                    pass

        merged_away = await _build_merge_map(session, org_id)

        # Resume-friendly + crash-safe: only games not yet rebuilt with the
        # caught_behind flag (legacy rows are all-NULL; a rebuilt game has ≥1
        # non-NULL). The wipe is now PER GAME, done only AFTER a successful
        # scorecard fetch (in the loop below), so a dropped connection can never
        # leave a game's bowler_wickets deleted-and-not-restored.
        games = await session.execute(
            sql_text(
                "SELECT DISTINCT g.id FROM games g "
                "JOIN grades gr ON gr.id = g.grade_id "
                "JOIN seasons s ON s.id = gr.season_id "
                "WHERE s.organisation_id = :org_id "
                "  AND NOT EXISTS (SELECT 1 FROM bowler_wickets bw "
                "                 WHERE bw.game_id = g.id AND bw.caught_behind IS NOT NULL) "
                "ORDER BY g.id"
            ),
            {"org_id": str(org_id)},
        )
        game_ids = [r[0] for r in games.all()]

    print(
        f"Loaded {len(known_player_ids)} players, "
        f"{len(merged_away)} active merges. "
        f"{len(game_ids)} games to (re)build. Re-parsing..."
    )

    inserted_total = 0
    errors = 0
    org_id_str_lower = org_id_str.lower()
    for i, gid in enumerate(game_ids, start=1):
        try:
            scorecard = await get_match_scorecard(str(gid))
            if not scorecard:
                continue
            # Restrict to bowlers on OUR team in this specific game.
            # A current club player who bowled AGAINST us in this game would
            # otherwise have their dismissals credited to our team.
            our_team = next(
                (t for t in (scorecard.get("teams") or [])
                 if ((t.get("owningOrganisation") or {}).get("id") or "").lower() == org_id_str_lower),
                None,
            )
            our_team_pids: set = set()
            if our_team:
                for roster_p in (our_team.get("players") or []):
                    rpid_str = roster_p.get("participantId")
                    if not rpid_str:
                        continue
                    try:
                        g = uuid.UUID(rpid_str)
                    except ValueError:
                        continue
                    # raw participant GUID -> this org's player id (identity for legacy)
                    p = pid_by_guid.get(g)
                    if p is None:
                        p = merged_away.get(g)
                        if p is None:
                            continue
                    else:
                        p = merged_away.get(p, p)
                    our_team_pids.add(p)
            rows = extract_bowler_wickets(scorecard, gid, our_team_pids, pid_by_guid, merged_away)
            # Per-game wipe + reinsert in ONE transaction, only now that the
            # fetch above succeeded — a failed fetch `continue`d and left the
            # game's existing rows intact. An empty `rows` correctly clears a
            # game that now yields no wickets.
            async with async_session_maker() as session:
                await session.execute(
                    sql_text("DELETE FROM bowler_wickets WHERE game_id = :gid"),
                    {"gid": gid},
                )
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


async def rebuild_all() -> None:
    """Rebuild every organisation, sequentially, so one run repopulates the whole
    site (e.g. after adding bowler_wickets.caught_behind). One club's failure must
    not abort the rest."""
    async with async_session_maker() as session:
        rows = await session.execute(
            sql_text("SELECT id, name FROM organisations ORDER BY name")
        )
        orgs = [(r[0], r[1]) for r in rows.all()]
    print(f"Rebuilding bowler_wickets for {len(orgs)} organisations...\n")
    failed: list[str] = []
    for idx, (oid, name) in enumerate(orgs, start=1):
        print(f"=== [{idx}/{len(orgs)}] {name} ({oid}) ===")
        try:
            await rebuild_for_org(str(oid))
        except Exception as exc:
            failed.append(f"{name} ({oid}): {exc}")
            print(f"  !! org failed: {exc}")
    print(f"\nAll organisations done. {len(failed)} failed.")
    for f in failed:
        print(f"  - {f}")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    if arg.lower() == "all":
        asyncio.run(rebuild_all())
    else:
        asyncio.run(rebuild_for_org(arg))
