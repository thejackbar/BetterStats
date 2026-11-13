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
from app.services import merge_redirects, participant_names
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


def _parse_guid(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def club_roster(scorecard: dict, org_id_lower: str, pid_by_guid: dict, merged_away: dict,
                unique_names: dict) -> tuple[set, dict]:
    """The club's players in this game and the participant-id map to resolve them, as sync reads them.

    Returns ``(our_team_pids, pid_by_guid_for_this_game)``. The same four rules sync applies
    when it first stores a game, so a rebuild never sees FEWER of the club's players than the
    sync did (which made it write fewer rows, and the loop leave the game alone):
      * every team the club owns in the fixture, not just the first (a club playing itself
        has two sides);
      * CA's placeholder participant ids belong to nobody;
      * a participant id followed through a merge redirect, as `sync._team_pid` does;
      * a rostered player whose id was never stored, whose full name matches exactly one of
        the club's players, is attached to that player (CA issues a new participant id per
        registration for some players): `participant_names.resolve_roster_by_name`.
    """
    def team_pid(g):
        if g is None or participant_names.is_placeholder_id(str(g)):
            return None
        p = pid_by_guid.get(g)
        if p is None:
            p = merged_away.get(g)
            if p is None:
                return None
        return merged_away.get(p, p)

    our_teams = [t for t in (scorecard.get("teams") or [])
                 if ((t.get("owningOrganisation") or {}).get("id") or "").lower() == org_id_lower]
    sheet = [rp for t in our_teams for rp in (t.get("players") or [])]
    known: dict = {}
    for rp in sheet:
        raw = rp.get("participantId") or ""
        kp = team_pid(_parse_guid(raw)) if raw else None
        if kp is not None:
            known[raw] = kp
    pids = set(known.values())
    game_map = dict(pid_by_guid)
    for raw, kp in participant_names.resolve_roster_by_name(sheet, known, unique_names).items():
        g = _parse_guid(raw)
        if g is not None:
            game_map[g] = kp
            pids.add(kp)
    return pids, game_map


async def rebuild_for_org(org_id_str: str, mode: str = "default") -> None:
    org_id = uuid.UUID(org_id_str)

    async with async_session_maker() as session:
        players = await session.execute(
            select(Player.id, Player.grassroots_id, Player.name, Player.display_name_override, Player.is_player)
            .where(Player.organisation_id == org_id)
        )
        known_player_ids = set()
        pid_by_guid: dict = {}  # raw CA participant GUID -> this org's player id (identity for legacy)
        name_pairs: list = []
        for _pid, _gid, _pname, _pover, _is_player in players.all():
            known_player_ids.add(_pid)
            g = _parse_guid(_gid) if _gid else None
            if g is not None and not participant_names.is_placeholder_id(str(g)):
                pid_by_guid[g] = _pid
            if _is_player is not False:
                name_pairs.append((_pid, _pover or _pname))
        unique_names = participant_names.unique_by_full_name(name_pairs)

        merged_away = await _build_merge_map(session, org_id)
        # A redirect to a player who no longer exists reads as an unknown id, as in sync.
        merged_away, _dangling = await merge_redirects.drop_dangling(session, merged_away)

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
                print(f"  left alone {gid}: CA returned an incomplete card")
                continue
            # Restrict to bowlers and fielders on OUR side in this specific game, resolved the way
            # sync resolves them (club_roster). A current club player who bowled AGAINST us in this
            # game would otherwise have their dismissals credited to our team.
            our_team_pids, game_pid_by_guid = club_roster(
                scorecard, org_id_str_lower, pid_by_guid, merged_away, unique_names)
            rows = extract_bowler_wickets(scorecard, gid, our_team_pids, game_pid_by_guid, merged_away)
            # Per-game wipe + reinsert in ONE transaction, only now that the
            # fetch above succeeded — a failed fetch `continue`d and left the
            # game's existing rows intact. An empty `rows` correctly clears a
            # game that now yields no wickets.
            async with async_session_maker() as session:
                if mode != "default":
                    # A targeted rebuild exists to ADD links, so it never replaces a game with
                    # fewer rows, or with fewer rows that name a fielder, than it holds: that is a
                    # card (or a club roster) that reads worse than the sync did, not a correction.
                    # Counting rows alone is not enough: a fielder the rebuild cannot place leaves
                    # the row, and loses the link.
                    held, held_fielder = (await session.execute(
                        sql_text("SELECT COUNT(*), COUNT(fielder_id) FROM bowler_wickets WHERE game_id = :gid"),
                        {"gid": gid})).one()
                    new_fielder = sum(1 for r in rows if r.fielder_id is not None)
                    if len(rows) < held or new_fielder < held_fielder:
                        skipped_fewer += 1
                        print(f"  left alone {gid}: the card gives {len(rows)} rows ({new_fielder} with a fielder), "
                              f"{held} are stored ({held_fielder} with a fielder)")
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
        f"{skipped_fewer} games where the card gave fewer rows, or fewer fielder links, than are stored."
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
