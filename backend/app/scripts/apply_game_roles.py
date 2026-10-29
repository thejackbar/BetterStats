"""Add captain and wicket keeper to matches a club has ALREADY imported, from a roles file. Dry run unless --apply.

The CSFW converter (tools/csfw_extract.py) now reads who captained and who kept wicket in each match, and writes
them on `manual_games_scorecards.csv` for a club that has not imported yet. A club that HAS imported (Shoalwater
Bay's 903 matches) should not have to load its scorecards again, so the converter also writes
`manual_game_roles.csv`: one row per player who held a role, with the match's season, grade, date and opposition.
This reads that file and adds the roles to the matches already in BetterCricket.

  * A match is found the way the scorecard import finds an existing one: date and opposition, with the grade
    deciding between two games on one day (`manual_entries._match_existing`). Each match is taken once. A match
    that is a Cricket Australia game (not a hand-entered or imported one) is left alone, because its roles come
    from Cricket Australia's own team sheet.
  * A player is found by name among the players on THAT match's card only (batting, bowling or fielding), never
    across the club, so a common name cannot reach the wrong person. A name that is not on the card, or fits two
    people on it, is listed and skipped.
  * It only ADDS. A match that already has a captain (or a keeper), however it got there, keeps it: the role was
    set by somebody, and a file cannot overrule that. Both are listed.
  * Dry run by default: prints what it would write and writes nothing.
  * `--apply` needs `--expect N` (the number of matches the plan changes) and `--by "name"`. One club per run.
  * Every match it writes goes, in full, into one `audit_logs` entry in the same transaction. `--restore AUDIT_ID`
    takes exactly those roles back off, only where they are still what this run wrote. An entry restores once.
  * Database only: no call to Cricket Australia.

Usage, from the server (the file has to be inside the container, for example `docker compose cp`):
  cd /srv/docker && export COMPOSE_PROJECT_NAME=bltbox_docker_app
  docker compose cp manual_game_roles.csv betterstats-backend:/tmp/manual_game_roles.csv
  docker compose exec -T betterstats-backend python -u -m app.scripts.apply_game_roles <org_id_or_slug> /tmp/manual_game_roles.csv
  docker compose exec -T betterstats-backend python -u -m app.scripts.apply_game_roles <org> /tmp/manual_game_roles.csv --apply --expect N --by "your name"
  docker compose exec -T betterstats-backend python -u -m app.scripts.apply_game_roles <org> --restore AUDIT_ID --by "your name"
"""
import argparse
import asyncio
import csv
import json
import re
import uuid
from collections import Counter, defaultdict
from pathlib import Path

from sqlalchemy import text

from app.models.db import async_session_maker
from app.scripts.audit_twelfth_man import _resolve_org, say

ACTION = "apply_game_roles"
RESTORE_ACTION = "apply_game_roles_restore"


def _truthy(v) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "y", "t"}


def _name_keys(*names) -> set[str]:
    """Lower-cased spellings a name goes by: as written, and 'Smith, John' with 'John Smith'."""
    keys: set[str] = set()
    for raw in names:
        n = re.sub(r"\s+", " ", (raw or "").strip().lower())
        if not n:
            continue
        keys.add(n)
        if "," in n:
            last, first = [x.strip() for x in n.split(",", 1)]
            if last and first:
                keys.add(f"{first} {last}")
        else:
            parts = n.split()
            if len(parts) >= 2:
                keys.add(f"{parts[-1]}, {' '.join(parts[:-1])}")
    return keys


def read_roles(path: Path) -> dict[str, dict]:
    """The roles file as {game_key: {match fields, 'captains': [names], 'keepers': [names]}}."""
    games: dict[str, dict] = {}
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        need = {"game_key", "played_at", "opposition", "player_name", "is_captain", "is_wicketkeeper"}
        missing = need - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"{path} is not a roles file: missing column(s) {', '.join(sorted(missing))}.")
        for row in reader:
            g = games.setdefault(row["game_key"], {
                "played_at": (row.get("played_at") or "").strip(),
                "opposition": (row.get("opposition") or "").strip(),
                "grade": (row.get("grade_name") or "").strip(),
                "season": (row.get("season_name") or "").strip(),
                "captains": [], "keepers": []})
            name = (row.get("player_name") or "").strip()
            if name and _truthy(row.get("is_captain")) and name not in g["captains"]:
                g["captains"].append(name)
            if name and _truthy(row.get("is_wicketkeeper")) and name not in g["keepers"]:
                g["keepers"].append(name)
    return games


async def _card_players(session, game_id: str) -> list[dict]:
    """The players on a manual game's card: a batting, bowling or fielding row."""
    rows = (await session.execute(text("""
        SELECT DISTINCT p.id::text AS id, p.name, p.display_name_override
          FROM (SELECT player_id FROM manual_batting_innings WHERE manual_game_id = CAST(:g AS UUID)
                UNION SELECT player_id FROM manual_bowling_spells WHERE manual_game_id = CAST(:g AS UUID)
                UNION SELECT player_id FROM manual_fielding_stats WHERE manual_game_id = CAST(:g AS UUID)) c
          JOIN players p ON p.id = c.player_id
    """), {"g": game_id})).mappings().all()
    return [dict(r) for r in rows]


def _resolve(name: str, card: list[dict]) -> tuple[str | None, str | None]:
    """(player id, None) when exactly one player on the card goes by this name, else (None, why)."""
    want = _name_keys(name)
    hits = [p for p in card if want & _name_keys(p["name"], p["display_name_override"])]
    if len(hits) == 1:
        return hits[0]["id"], None
    return None, ("not on that match's card" if not hits else "fits more than one player on that match's card")


async def plan(org: str, games: dict[str, dict]) -> tuple[list[dict], Counter, list[dict]]:
    """The matches to change: [{game_id, date, grade, opposition, add_captains, add_keepers}], why-not tallies,
    and the names that could not be placed."""
    from app.routers.manual_entries import _existing_game_index, _match_existing
    left: Counter = Counter()
    unplaced: list[dict] = []
    rows: list[dict] = []
    async with async_session_maker() as session:
        await session.execute(text("SET TRANSACTION READ ONLY"))
        index = await _existing_game_index(session, uuid.UUID(org))
        consumed: set = set()
        for key, g in sorted(games.items(), key=lambda kv: (kv[1]["played_at"], kv[0])):
            found = _match_existing(index, g["played_at"], (g["opposition"], "", ""), consumed, g["grade"])
            if not found:
                left["no match in BetterCricket for this one"] += 1
                continue
            if found["source"] != "manual":
                left["a Cricket Australia game: its roles come from the team sheet"] += 1
                continue
            card = await _card_players(session, found["id"])
            held = (await session.execute(text(
                "SELECT bool_or(is_captain), bool_or(is_wicket_keeper) FROM manual_game_roles "
                "WHERE manual_game_id = CAST(:g AS UUID)"), {"g": found["id"]})).one()
            add_c: list[str] = []
            add_k: list[str] = []
            for kind, names, already, bucket in (("captain", g["captains"], held[0], add_c),
                                                 ("wicket keeper", g["keepers"], held[1], add_k)):
                if not names:
                    continue
                if already:
                    left[f"already has a {kind}: left as it is"] += 1
                    continue
                for nm in names:
                    pid, why = _resolve(nm, card)
                    if pid is None:
                        unplaced.append({"date": g["played_at"], "grade": g["grade"], "opposition": g["opposition"],
                                         "role": kind, "name": nm, "why": why})
                        left[f"{kind} not placed ({why})"] += 1
                    elif pid not in bucket:
                        bucket.append(pid)
            if add_c or add_k:
                rows.append({"game_id": found["id"], "date": g["played_at"], "grade": g["grade"],
                             "opposition": g["opposition"], "add_captains": add_c, "add_keepers": add_k})
    return rows, left, unplaced


def report(rows: list[dict], left: Counter, unplaced: list[dict], limit: int) -> None:
    say(f"\nwould add a captain to {sum(1 for r in rows if r['add_captains'])} matches "
        f"and a wicket keeper to {sum(1 for r in rows if r['add_keepers'])}, across {len(rows)} matches")
    for why, n in left.most_common():
        say(f"left as they are: {n}  ({why})")
    for r in rows[:limit]:
        say(f"  {r['date']}  {r['grade']:<10} v {r['opposition']:<22} "
            f"captain {len(r['add_captains'])}  keeper {len(r['add_keepers'])}  {r['game_id']}")
    if len(rows) > limit:
        say(f"  ... {len(rows) - limit} more (raise --list)")
    if unplaced:
        say(f"\nnames that could not be placed ({len(unplaced)}); set these by hand with Details on the match:")
        for u in unplaced[:limit]:
            say(f"  {u['date']} {u['grade']} v {u['opposition']}: {u['role']} {u['name']!r} ({u['why']})")
        if len(unplaced) > limit:
            say(f"  ... {len(unplaced) - limit} more")


async def apply(org: str, rows: list[dict], expect: int | None, by: str | None) -> None:
    if expect != len(rows):
        raise SystemExit(f"\nRefusing: --expect {expect} but the plan shows {len(rows)} matches. Re-read the plan.")
    if not by:
        raise SystemExit("\nRefusing: --by \"your name\" is required, it goes in the audit entry.")
    async with async_session_maker() as s:
        audit_id = (await s.execute(text(
            "INSERT INTO audit_logs (org_id, user_id, action, target_type, target_id, details) "
            "VALUES (CAST(:o AS UUID), NULL, :a, 'organisation', :o, CAST(:d AS JSONB)) RETURNING id"),
            {"o": org, "a": ACTION, "d": json.dumps({"by": by, "changes": rows})})).scalar()
        done = 0
        for r in rows:
            for kind, col, ids in (("captain", "is_captain", r["add_captains"]),
                                   ("keeper", "is_wicket_keeper", r["add_keepers"])):
                for pid in ids:
                    await s.execute(text(
                        f"INSERT INTO manual_game_roles (manual_game_id, player_id, {col}) "
                        f"VALUES (CAST(:g AS UUID), CAST(:p AS UUID), TRUE) "
                        f"ON CONFLICT (manual_game_id, player_id) DO UPDATE SET {col} = TRUE"),
                        {"g": r["game_id"], "p": pid})
                    done += 1
        await s.commit()
    print(f"\nAPPLIED {done} role(s) on {len(rows)} matches. Audit entry {audit_id}. "
          f"To undo: --restore {audit_id} --by \"your name\"")
    await _premiership_follow_up(org)


async def restore(audit_id: int, by: str | None) -> None:
    if not by:
        raise SystemExit("Refusing: --by \"your name\" is required.")
    async with async_session_maker() as s:
        row = (await s.execute(text(
            "SELECT org_id::text AS org, details, action FROM audit_logs WHERE id = :i"), {"i": audit_id})).mappings().first()
        if not row or row["action"] != ACTION:
            raise SystemExit(f"Audit entry {audit_id} is not a {ACTION} entry.")
        details = row["details"] if isinstance(row["details"], dict) else json.loads(row["details"])
        # The audit trail is append-only: "already restored" is read from the restore entry.
        again = (await s.execute(text(
            "SELECT created_at::text FROM audit_logs WHERE action = :a AND details->>'from_audit' = :i"),
            {"a": RESTORE_ACTION, "i": str(audit_id)})).scalar()
        if again:
            raise SystemExit(f"Audit entry {audit_id} was already restored ({again}).")
        removed = 0
        for r in details["changes"]:
            for col, ids in (("is_captain", r["add_captains"]), ("is_wicket_keeper", r["add_keepers"])):
                for pid in ids:
                    res = await s.execute(text(
                        f"UPDATE manual_game_roles SET {col} = FALSE "
                        f"WHERE manual_game_id = CAST(:g AS UUID) AND player_id = CAST(:p AS UUID) AND {col}"),
                        {"g": r["game_id"], "p": pid})
                    removed += res.rowcount
        # A row left holding neither role is no row at all (only on the matches this entry touched).
        await s.execute(text(
            "DELETE FROM manual_game_roles WHERE NOT is_captain AND NOT is_wicket_keeper "
            "AND manual_game_id = ANY(CAST(:ids AS uuid[]))"),
            {"ids": [r["game_id"] for r in details["changes"]]})
        await s.execute(text(
            "INSERT INTO audit_logs (org_id, user_id, action, target_type, target_id, details) "
            "VALUES (CAST(:o AS UUID), NULL, :a, 'organisation', :o, CAST(:d AS JSONB))"),
            {"o": row["org"], "a": RESTORE_ACTION, "d": json.dumps({"by": by, "from_audit": audit_id, "roles": removed})})
        await s.commit()
    print(f"RESTORED: took {removed} role(s) off from audit entry {audit_id}.")
    await _premiership_follow_up(row["org"])


async def _premiership_follow_up(org: str) -> None:
    """A captain earns the premiership honour its 'Captain' detail: bring the honours in line (never raises)."""
    from app.services import premierships
    await premierships.maybe_reconcile(uuid.UUID(org))


async def main(args) -> None:
    if args.restore:
        return await restore(args.restore, args.by)
    org = await _resolve_org(args.org)
    games = read_roles(Path(args.csv))
    say(f"{len(games)} matches in {args.csv}")
    rows, left, unplaced = await plan(org, games)
    report(rows, left, unplaced, args.list)
    if args.apply:
        await apply(org, rows, args.expect, args.by)
    else:
        say(f"\nDRY RUN: nothing was changed. To apply:\n  ... {args.org} {args.csv} --apply --expect {len(rows)} --by \"your name\"")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("org", nargs="?", help="org id or club slug")
    ap.add_argument("csv", nargs="?", help="the roles file the converter wrote (manual_game_roles.csv)")
    ap.add_argument("--apply", action="store_true", help="make the change (default is a dry run)")
    ap.add_argument("--expect", type=int, help="the number of matches the plan changes; required with --apply")
    ap.add_argument("--by", help="who is doing this; required with --apply and --restore")
    ap.add_argument("--restore", type=int, metavar="AUDIT_ID", help="undo a previous --apply from its audit entry")
    ap.add_argument("--list", type=int, default=30, help="matches and names to list")
    a = ap.parse_args()
    if not a.restore and not (a.org and a.csv):
        ap.error("an org and the roles file are required")
    asyncio.run(main(a))
