"""Detach one player's rows from synced games their id is not on. Dry run unless --apply.

For a record that holds games CA does not credit to them: rows linked by a shared hidden-participant
id (Leederville's Jonah Cumming, 36 games) or by a namesake's full name (Mulgrave's Luke Bennett, 16
games). `audit_player_games` shows the same list read only; this uses the same rule
(`services/game_attribution.classify`), so what is reported is what is repaired.

For every synced game the player holds, CA's scorecard is read. A game is WRONG when it names people
but not this player and not anyone merged into them. A game CA returns nothing for, or whose card
names nobody, is never touched.

WHAT IT CHANGES, per wrong game, for that player only:
  deleted      batting_innings, bowling_spells, fielding_stats, game_appearances, bowler_wickets (as
               bowler), milestones tied to the game. These were written by sync for this player and
               are re-created by nothing (sync no longer links these ids).
  set to NULL  partnerships batter1_id / batter2_id, fall_of_wickets.player_id, bowler_wickets
               fielder_id. The stored batter names stay, so the match page still reads.
  not touched  `player_season_stats` (CA's own totals), hand-typed games, every other player, and any
               other table that mentions the player and the game (listed, with counts, so you can see).

SAFETY
  * Dry run by default: prints the plan, writes nothing.
  * `--apply` needs `--expect N` (the number of wrong games the plan shows) and `--by "name"`. If the
    count has moved since you read the plan, it stops.
  * Everything removed or nulled is written, in full, to one `audit_logs` entry in the same
    transaction as the change. If that write fails nothing changes.
  * `--restore AUDIT_ID` puts it all back from that entry. An entry restores once.
  * Refuses a player with no CA id of their own (a hand-added record): its games cannot be judged.

Usage, from the server:
  cd /srv/docker && export COMPOSE_PROJECT_NAME=bltbox_docker_app
  docker compose exec -T betterstats-backend python -u -m app.scripts.repair_misattributed_games auto <player-id>
  docker compose exec -T betterstats-backend python -u -m app.scripts.repair_misattributed_games auto <player-id> --apply --expect N --by "your name"
  docker compose exec -T betterstats-backend python -u -m app.scripts.repair_misattributed_games auto <player-id> --restore AUDIT_ID --by "your name"

Afterwards, if the club runs BetterFantasyCricket, re-settle its recent rounds (`fantasy_round_drift`).
"""
import argparse
import asyncio
import json
import uuid

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services import game_attribution, grassroots_scores_client as gr
from app.services.club_grades import club_game_sql

ACTION = "repair_misattributed_games"
RESTORE_ACTION = "restore_misattributed_games"

# (table, where clause on the player's id and the games), in the order they are deleted. The order
# for restore is the reverse of nothing special: no foreign keys point between them.
DELETE_TABLES = (
    ("batting_innings", "player_id = CAST(:p AS UUID) AND game_id = ANY(CAST(:g AS UUID[]))"),
    ("bowling_spells", "player_id = CAST(:p AS UUID) AND game_id = ANY(CAST(:g AS UUID[]))"),
    ("fielding_stats", "player_id = CAST(:p AS UUID) AND game_id = ANY(CAST(:g AS UUID[]))"),
    ("game_appearances", "player_id = CAST(:p AS UUID) AND game_id = ANY(CAST(:g AS UUID[]))"),
    ("bowler_wickets", "bowler_id = CAST(:p AS UUID) AND game_id = ANY(CAST(:g AS UUID[]))"),
    ("milestones", "player_id = CAST(:p AS UUID) AND game_id = ANY(CAST(:g AS UUID[]))"),
)
# (table, column) pairs set to NULL where they hold the player, in the wrong games.
NULL_COLUMNS = (
    ("partnerships", "batter1_id"),
    ("partnerships", "batter2_id"),
    ("fall_of_wickets", "player_id"),
    ("bowler_wickets", "fielder_id"),
)


async def _resolve_org(org_ref: str, player_id: str) -> str:
    async with async_session_maker() as s:
        if org_ref in ("auto", "-"):
            found = (await s.execute(text(
                "SELECT organisation_id::text FROM players WHERE id = CAST(:p AS UUID)"), {"p": player_id})).scalar()
            if not found:
                raise SystemExit("No such player id")
            return found
        try:
            return str(uuid.UUID(org_ref))
        except ValueError:
            pass
        found = (await s.execute(text("SELECT id::text FROM organisations WHERE slug = :s"), {"s": org_ref})).scalar()
        if not found:
            raise SystemExit(f"No club with slug {org_ref!r}")
        return found


async def _wrong_games(s, org: str, player_id: str, limit: int, only: set | None) -> tuple[list[dict], dict]:
    me = (await s.execute(text(
        "SELECT COALESCE(display_name_override, name) AS name, grassroots_id, organisation_id::text AS org "
        "FROM players WHERE id = CAST(:p AS UUID)"), {"p": player_id})).mappings().first()
    if not me:
        raise SystemExit("No such player id")
    if me["org"] != org:
        raise SystemExit("That player belongs to a different club")
    if not me["grassroots_id"]:
        raise SystemExit("This player has no Cricket Australia id of their own (a hand-added record), "
                         "so their games cannot be judged against a scorecard. Nothing to do.")
    own = {me["grassroots_id"].lower(), player_id.lower()}
    redirects = {str(r[0]): str(r[1]) for r in (await s.execute(text(
        "SELECT removed_player_id, keep_player_id FROM merge_logs WHERE org_id = CAST(:o AS UUID) AND undone_at IS NULL"),
        {"o": org})).all()}
    merged = game_attribution.merged_into(redirects, player_id)
    games = (await s.execute(text(f"""
        WITH held AS (
            SELECT bi.game_id FROM batting_innings bi WHERE bi.player_id = CAST(:p AS UUID)
            UNION SELECT bs.game_id FROM bowling_spells bs WHERE bs.player_id = CAST(:p AS UUID)
            UNION SELECT fs.game_id FROM fielding_stats fs WHERE fs.player_id = CAST(:p AS UUID)
            UNION SELECT ga.game_id FROM game_appearances ga WHERE ga.player_id = CAST(:p AS UUID))
        SELECT g.id::text AS id, g.played_at::text AS d, gr.name AS grade
        FROM held h JOIN v_effective_games g ON g.id = h.game_id LEFT JOIN grades gr ON gr.id = g.grade_id
        WHERE {club_game_sql('g', 'org')} AND g.source = 'api'
        ORDER BY g.played_at DESC LIMIT :lim"""), {"p": player_id, "org": org, "lim": limit})).mappings().all()
    tally = {"ON": 0, "MERGE": 0, "OFF": 0, "EMPTY": 0}
    wrong = []
    for g in games:
        if only is not None and g["id"] not in only:
            continue
        sc = await gr.get_match_scorecard(g["id"])
        await asyncio.sleep(0.3)
        verdict = game_attribution.classify(sc, own, merged, uuid.UUID(org))
        tally[verdict] += 1
        if verdict == "OFF":
            wrong.append(dict(g))
    return wrong, {"name": me["name"], "checked": len(games), **tally}


async def _counts(s, player_id: str, gids: list[str]) -> dict:
    out = {}
    for table, where in DELETE_TABLES:
        out[table] = (await s.execute(text(f"SELECT COUNT(*) FROM {table} WHERE {where}"), {"p": player_id, "g": gids})).scalar()
    for table, col in NULL_COLUMNS:
        out[f"{table}.{col} (set NULL)"] = (await s.execute(text(
            f"SELECT COUNT(*) FROM {table} WHERE {col} = CAST(:p AS UUID) AND game_id = ANY(CAST(:g AS UUID[]))"),
            {"p": player_id, "g": gids})).scalar()
    return out


async def _other_references(s, player_id: str, gids: list[str]) -> dict:
    """Tables that name this player AND a game, other than the ones handled: shown, never changed."""
    handled = {t for t, _ in DELETE_TABLES} | {t for t, _ in NULL_COLUMNS}
    tables = [r[0] for r in (await s.execute(text("""
        SELECT c.table_name FROM information_schema.columns c
        JOIN information_schema.tables t ON t.table_name = c.table_name AND t.table_schema = c.table_schema
        WHERE c.table_schema = 'public' AND t.table_type = 'BASE TABLE' AND c.column_name = 'game_id'
          AND EXISTS (SELECT 1 FROM information_schema.columns c2 WHERE c2.table_schema = 'public'
                      AND c2.table_name = c.table_name AND c2.column_name = 'player_id')"""))).all()]
    out = {}
    for t in tables:
        if t in handled:
            continue
        n = (await s.execute(text(
            f'SELECT COUNT(*) FROM "{t}" WHERE player_id = CAST(:p AS UUID) AND game_id = ANY(CAST(:g AS UUID[]))'),
            {"p": player_id, "g": gids})).scalar()
        if n:
            out[t] = n
    return out


async def plan_and_maybe_apply(org_ref: str, player_id: str, apply: bool, expect: int | None, by: str | None,
                               limit: int, only: set | None) -> None:
    org = await _resolve_org(org_ref, player_id)
    async with async_session_maker() as s:
        wrong, info = await _wrong_games(s, org, player_id, limit, only)
        print(f"{info['name']}: {info['checked']} synced games held; on the card {info['ON']}, via a merge {info['MERGE']}, "
              f"nobody named (not touched) {info['EMPTY']}, WRONG {info['OFF']}")
        if not wrong:
            print("Nothing to repair.")
            return
        gids = [g["id"] for g in wrong]
        print("\nwrong games (the card does not carry this player or anyone merged into them):")
        for g in wrong:
            print(f"  {g['d']}  {str(g['grade']):<30} {g['id']}")
        counts = await _counts(s, player_id, gids)
        print("\nrows that would change:")
        for k, v in counts.items():
            print(f"  {k:<36} {v}")
        other = await _other_references(s, player_id, gids)
        if other:
            print("\nother tables that mention this player in those games (NOT changed, for your information):")
            for k, v in other.items():
                print(f"  {k:<36} {v}")

        if not apply:
            print(f"\nDRY RUN: nothing was changed. To apply:\n  ... --apply --expect {len(wrong)} --by \"your name\"")
            return
        if expect != len(wrong):
            raise SystemExit(f"\nRefusing: --expect {expect} but the plan shows {len(wrong)} wrong games. Re-read the plan.")
        if not by:
            raise SystemExit("\nRefusing: --by \"your name\" is required, it goes in the audit entry.")

        dump: dict = {"player_id": player_id, "games": gids, "tables": {}, "nulled": []}
        for table, where in DELETE_TABLES:
            rows = (await s.execute(text(
                f"SELECT COALESCE(jsonb_agg(to_jsonb(t)), '[]'::jsonb) FROM {table} t WHERE {where}"), {"p": player_id, "g": gids})).scalar()
            dump["tables"][table] = rows
        for table, col in NULL_COLUMNS:
            ids = [r[0] for r in (await s.execute(text(
                f"SELECT id FROM {table} WHERE {col} = CAST(:p AS UUID) AND game_id = ANY(CAST(:g AS UUID[]))"),
                {"p": player_id, "g": gids})).all()]
            dump["nulled"].append({"table": table, "column": col, "ids": ids})
        audit_id = (await s.execute(text(
            "INSERT INTO audit_logs (org_id, user_id, action, target_type, target_id, details) "
            "VALUES (CAST(:o AS UUID), NULL, :a, 'player', :pid, CAST(:d AS JSONB)) RETURNING id"),
            {"o": org, "a": ACTION, "pid": player_id,
             "d": json.dumps({"by": by, "player": info["name"], "counts": counts, "dump": dump}, default=str)})).scalar()
        for table, where in DELETE_TABLES:
            await s.execute(text(f"DELETE FROM {table} WHERE {where}"), {"p": player_id, "g": gids})
        for table, col in NULL_COLUMNS:
            await s.execute(text(f"UPDATE {table} SET {col} = NULL WHERE {col} = CAST(:p AS UUID) AND game_id = ANY(CAST(:g AS UUID[]))"),
                            {"p": player_id, "g": gids})
        await s.commit()
        print(f"\nAPPLIED. Audit entry {audit_id}. To undo: --restore {audit_id} --by \"your name\"")


async def restore(audit_id: int, by: str | None) -> None:
    if not by:
        raise SystemExit("Refusing: --by \"your name\" is required.")
    async with async_session_maker() as s:
        row = (await s.execute(text(
            "SELECT org_id::text AS org, details, action FROM audit_logs WHERE id = :i"), {"i": audit_id})).mappings().first()
        if not row or row["action"] != ACTION:
            raise SystemExit(f"Audit entry {audit_id} is not a {ACTION} entry.")
        details = row["details"] if isinstance(row["details"], dict) else json.loads(row["details"])
        if details.get("restored_at"):
            raise SystemExit(f"Audit entry {audit_id} was already restored ({details['restored_at']}).")
        dump = details["dump"]
        pid = dump["player_id"]
        if not (await s.execute(text("SELECT 1 FROM players WHERE id = CAST(:p AS UUID)"), {"p": pid})).scalar():
            raise SystemExit("The player no longer exists; cannot restore.")
        restored = {}
        for table, rows in dump["tables"].items():
            if not rows:
                continue
            res = await s.execute(text(
                f"INSERT INTO {table} SELECT * FROM jsonb_populate_recordset(NULL::{table}, CAST(:r AS JSONB)) ON CONFLICT DO NOTHING"),
                {"r": json.dumps(rows)})
            restored[table] = res.rowcount
        for n in dump["nulled"]:
            if not n["ids"]:
                continue
            res = await s.execute(text(
                f"UPDATE {n['table']} SET {n['column']} = CAST(:p AS UUID) WHERE id = ANY(:ids) AND {n['column']} IS NULL"),
                {"p": pid, "ids": n["ids"]})
            restored[f"{n['table']}.{n['column']}"] = res.rowcount
        details["restored_at"] = (await s.execute(text("SELECT NOW()::text"))).scalar()
        details["restored_by"] = by
        await s.execute(text("UPDATE audit_logs SET details = CAST(:d AS JSONB) WHERE id = :i"),
                        {"d": json.dumps(details, default=str), "i": audit_id})
        await s.execute(text(
            "INSERT INTO audit_logs (org_id, user_id, action, target_type, target_id, details) "
            "VALUES (CAST(:o AS UUID), NULL, :a, 'player', :pid, CAST(:d AS JSONB))"),
            {"o": row["org"], "a": RESTORE_ACTION, "pid": pid, "d": json.dumps({"by": by, "from_audit": audit_id, "restored": restored})})
        await s.commit()
        print(f"RESTORED from audit entry {audit_id}: {restored}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("org", help="club id or slug, or 'auto' for the player's own club")
    ap.add_argument("player", help="BetterStats player id")
    ap.add_argument("--apply", action="store_true", help="make the change (default is a dry run)")
    ap.add_argument("--expect", type=int, help="the number of wrong games the plan shows; required with --apply")
    ap.add_argument("--by", help="who is doing this; required with --apply and --restore")
    ap.add_argument("--restore", type=int, metavar="AUDIT_ID", help="undo a previous --apply from its audit entry")
    ap.add_argument("--limit", type=int, default=200, help="most games to check (newest first)")
    ap.add_argument("--only-games", help="comma separated game ids: restrict the repair to these")
    a = ap.parse_args()
    if a.restore:
        asyncio.run(restore(a.restore, a.by))
        return
    only = {x.strip().lower() for x in a.only_games.split(",") if x.strip()} if a.only_games else None
    asyncio.run(plan_and_maybe_apply(a.org, a.player, a.apply, a.expect, a.by, a.limit, only))


if __name__ == "__main__":
    main()
