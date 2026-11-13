"""Backfill `bowler_wickets` for an organisation without doing a full rebuild.

Use after a parser change (new dismissalText format, etc) to repopulate
the table without wiping games / batting_innings / bowling_spells / etc.
Re-fetches each game's scorecard from CA and re-runs the bowler-wickets
extractor.

Also the way to back-fill `bowler_wickets.caught_behind` (migration 076) — the
extractor now records whether each caught wicket was off the keeper.

By default it only rebuilds games not yet rebuilt with the caught_behind flag, which is
almost none on a club that has already been through it. Two flags choose games for a parser
change that the default skips (e.g. naming a bowler or keeper the card's text left blank,
v9.143.8.2):
  --short  only games where the stored fielding totals exceed the catches and stumpings
           paired to a fielder (a caught-and-bowled is allowed for), or where a catch or
           stumping has no fielder. The cheap one: the games that can actually change.
  --force  every game of the club.

Usage from the backend container:
  # one club:
  docker exec -e PYTHONPATH=/app betterstats-backend \\
    python -m app.scripts.rebuild_bowler_wickets <org_id>
  # one club, only the games that are short (--force instead: every game):
  docker exec -e PYTHONPATH=/app betterstats-backend \\
    python -m app.scripts.rebuild_bowler_wickets <org_id> --short
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
from app.services.grassroots_scores_client import _scorecard_looks_incomplete, get_match_scorecard


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


# Games whose stored fielding totals are more than the pairings held: the ones a better parse
# can add to. A caught-and-bowled sits in the bowler's own fielding row and pairs to no fielder,
# so it is allowed for.
_SHORT_GAMES_SQL = (
    "SELECT DISTINCT g.id FROM games g "
    "JOIN grades gr ON gr.id = g.grade_id "
    "JOIN seasons s ON s.id = gr.season_id "
    "WHERE s.organisation_id = :org_id AND ("
    "  EXISTS (SELECT 1 FROM bowler_wickets bw WHERE bw.game_id = g.id "
    "          AND bw.fielder_id IS NULL AND bw.dismissal_type IN ('caught', 'stumped')) "
    "  OR COALESCE((SELECT SUM(COALESCE(fs.stumpings, 0) + COALESCE(fs.catches, 0)) "
    "               FROM fielding_stats fs WHERE fs.game_id = g.id), 0) "
    "     > (SELECT COUNT(*) FROM bowler_wickets bw WHERE bw.game_id = g.id "
    "        AND bw.dismissal_type IN ('caught', 'stumped') AND bw.fielder_id IS NOT NULL) "
    "     + (SELECT COUNT(*) FROM bowler_wickets bw WHERE bw.game_id = g.id "
    "        AND bw.dismissal_type = 'caught and bowled')"
    ") ORDER BY g.id"
)
_ALL_GAMES_SQL = (
    "SELECT DISTINCT g.id FROM games g "
    "JOIN grades gr ON gr.id = g.grade_id "
    "JOIN seasons s ON s.id = gr.season_id "
    "WHERE s.organisation_id = :org_id ORDER BY g.id"
)


async def rebuild_for_org(org_id_str: str, mode: str = "default") -> None:
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
        if mode == "short":
            games = await session.execute(sql_text(_SHORT_GAMES_SQL), {"org_id": str(org_id)})
        elif mode == "force":
            games = await session.execute(sql_text(_ALL_GAMES_SQL), {"org_id": str(org_id)})
        else:
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
    skipped_incomplete = 0
    skipped_fewer = 0
    org_id_str_lower = org_id_str.lower()
    for i, gid in enumerate(game_ids, start=1):
        try:
            scorecard = await get_match_scorecard(str(gid))
            if not scorecard:
                continue
            # CA sometimes returns a card with innings totals and no batting rows (a scorer
            # mid-edit, or a match CA only holds the scoreline of). The client still hands it
            # back, but it holds no dismissals, so rebuilding from it would wipe the pairings
            # already stored for the game and write none. Leave the game as it is.
            if _scorecard_looks_incomplete(scorecard):
                skipped_incomplete += 1
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
                if mode != "default":
                    # A targeted rebuild exists to ADD links, so it never replaces a game with
                    # fewer rows than it holds: that is a degraded card, not a correction.
                    held = (await session.execute(
                        sql_text("SELECT COUNT(*) FROM bowler_wickets WHERE game_id = :gid"),
                        {"gid": gid})).scalar() or 0
                    if len(rows) < held:
                        skipped_fewer += 1
                        continue
                await session.execute(
                    sql_text("DELETE FROM bowler_wickets WHERE game_id = :gid"),
                    {"gid": gid},
                )
                for r in rows:
                    session.add(r)
                await session.commit()
            inserted_total += len(rows)
            # One fetch a game, politely paced: a whole club is a few thousand requests to CA.
            await asyncio.sleep(0.25)
        except Exception as exc:
            errors += 1
            print(f"  err on {gid}: {exc}")
        if i % 100 == 0:
            print(f"  [{i}/{len(game_ids)}] inserted {inserted_total} so far ({errors} errors)")

    print(
        f"Done. Inserted {inserted_total} bowler_wickets across "
        f"{len(game_ids)} games ({errors} errors). "
        f"Left alone: {skipped_incomplete} games whose card CA returned incomplete, "
        f"{skipped_fewer} games where the card gave fewer rows than are stored."
    )


async def rebuild_all(mode: str = "default") -> None:
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
            await rebuild_for_org(str(oid), mode)
        except Exception as exc:
            failed.append(f"{name} ({oid}): {exc}")
            print(f"  !! org failed: {exc}")
    print(f"\nAll organisations done. {len(failed)} failed.")
    for f in failed:
        print(f"  - {f}")


if __name__ == "__main__":
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    positional = [a for a in sys.argv[1:] if not a.startswith("--")]
    mode = "force" if "--force" in flags else ("short" if "--short" in flags else "default")
    arg = positional[0] if positional else "all"
    if arg.lower() == "all":
        asyncio.run(rebuild_all(mode))
    else:
        asyncio.run(rebuild_for_org(arg, mode))
