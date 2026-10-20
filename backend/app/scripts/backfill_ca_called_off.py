"""Read which COMPLETED games CA actually called off, from the scorecard. Dry run unless --apply.

`games.ca_called_off` is written by the sync for every game it reads from now on. This reads the games
already stored. CA marks some fixtures COMPLETED ("Match drawn") while both teams' resultType on the card
reads ABANDONED, and its own season totals leave a named-only player out of those (Leederville CC,
14 Nov 2020: six games, about twenty players one match over). services/game_status.card_called_off is the
rule; a genuine draw carries DREW and CA counts it.

  TRUE   both teams read ABANDONED: the matches-played rules treat it like a status of ABANDONED
  FALSE  read, and not called off
  NULL   left alone: CA returned no card, or does not call the game COMPLETED, or the card has no summary

Only games where somebody was named and recorded nothing are read: a game where every named player has a
row of their own cannot change anyone's count. Only rows still NULL are read, so a second run costs nothing.

  * Dry run by default: prints what it would write and writes nothing.
  * `--apply` needs `--expect N` (the number of rows the plan shows) and `--by "name"`. One club per `--apply`.
  * Every row it writes goes, in full, into one `audit_logs` entry in the same transaction.
    `--restore AUDIT_ID` puts every one of those rows back to NULL. An entry restores once.
  * One paced scorecard request per game (the client caches), bounded by `--max-games`.

Usage, from the server:
  cd /srv/docker && export COMPOSE_PROJECT_NAME=bltbox_docker_app
  docker compose exec -T betterstats-backend python -u -m app.scripts.backfill_ca_called_off <org_id_or_slug_or_all> [--max-games 900] [--year Y]
  docker compose exec -T betterstats-backend python -u -m app.scripts.backfill_ca_called_off <org> --apply --expect N --by "your name"
  docker compose exec -T betterstats-backend python -u -m app.scripts.backfill_ca_called_off <org> --restore AUDIT_ID --by "your name"
"""
import argparse
import asyncio
import json
from collections import Counter

from sqlalchemy import text

from app.models.db import async_session_maker
from app.scripts.audit_twelfth_man import _all_orgs, _candidates, _resolve_org, say
from app.services import grassroots_scores_client as gr
from app.services.game_status import card_called_off

ACTION = "backfill_ca_called_off"
RESTORE_ACTION = "backfill_ca_called_off_restore"


async def _unread(session, game_ids: list[str]) -> set[str]:
    """Of these games, the ones whose `ca_called_off` is still NULL and CA's status is COMPLETED."""
    found = (await session.execute(
        text("SELECT id::text FROM games WHERE id = ANY(CAST(:ids AS uuid[])) "
             "AND ca_called_off IS NULL AND status = 'COMPLETED'"),
        {"ids": game_ids})).scalars().all()
    return set(found)


async def plan(org: str, args, budget: list[int]) -> tuple[list[dict], Counter]:
    """The rows to write for one club: [{game_id, called_off, date, grade}], and a tally of why not."""
    say(f"\n######## {org}\nreading named-only appearances from the database (no upstream calls yet)...")
    async with async_session_maker() as session:
        await session.execute(text("SET TRANSACTION READ ONLY"))
        await session.execute(text(f"SET LOCAL statement_timeout = {int(args.timeout) * 1000}"))
        cands = await _candidates(session, org, args.year)
        first: dict[str, dict] = {}
        for c in cands:
            first.setdefault(c["game_id"], c)
        unread = await _unread(session, sorted(first))
    games = sorted((first[g] for g in unread), key=lambda c: str(c["played_at"]), reverse=True)
    say(f"{len(games)} COMPLETED games not yet read, of {len(first)} with a named-only player")

    rows: list[dict] = []
    left: Counter = Counter()
    for c in games:
        if budget[0] <= 0:
            left["allowance ran out"] += 1
            continue
        budget[0] -= 1
        card = await gr.get_match_scorecard(c["game_id"])
        await asyncio.sleep(args.pace)
        verdict = card_called_off(card)
        if verdict is None:
            left["CA returned no card, no summary, or does not call it COMPLETED"] += 1
            continue
        rows.append({"game_id": c["game_id"], "called_off": verdict,
                     "date": str(c["played_at"])[:10], "grade": c["grade"]})
    return rows, left


def report(rows: list[dict], left: Counter, limit: int) -> None:
    called = [r for r in rows if r["called_off"]]
    say(f"\nwould set ca_called_off TRUE  on {len(called)} games (both teams read ABANDONED)")
    say(f"would set ca_called_off FALSE on {len(rows) - len(called)} games (read, not called off)")
    for why, n in left.most_common():
        say(f"left NULL: {n}  ({why})")
    if called:
        say("\ncalled off (newest first):")
        for r in sorted(called, key=lambda r: r["date"], reverse=True)[:limit]:
            say(f"  {r['date']}  {str(r['grade']):<28} {r['game_id']}")
        if len(called) > limit:
            say(f"  ... {len(called) - limit} more (raise --list)")


async def apply(org: str, rows: list[dict], expect: int | None, by: str | None) -> None:
    if expect != len(rows):
        raise SystemExit(f"\nRefusing: --expect {expect} but the plan shows {len(rows)} rows. Re-read the plan.")
    if not by:
        raise SystemExit("\nRefusing: --by \"your name\" is required, it goes in the audit entry.")
    async with async_session_maker() as s:
        changes = [{"game_id": r["game_id"], "called_off": r["called_off"]} for r in rows]
        audit_id = (await s.execute(text(
            "INSERT INTO audit_logs (org_id, user_id, action, target_type, target_id, details) "
            "VALUES (CAST(:o AS UUID), NULL, :a, 'organisation', :o, CAST(:d AS JSONB)) RETURNING id"),
            {"o": org, "a": ACTION, "d": json.dumps({"by": by, "changes": changes})})).scalar()
        done = 0
        for r in rows:
            res = await s.execute(text(
                "UPDATE games SET ca_called_off = :v "
                "WHERE id = CAST(:g AS UUID) AND ca_called_off IS NULL"),
                {"v": r["called_off"], "g": r["game_id"]})
            done += res.rowcount
        await s.commit()
    print(f"\nAPPLIED to {done} games. Audit entry {audit_id}. To undo: --restore {audit_id} --by \"your name\"")


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
        done = 0
        for c in details["changes"]:
            # Only a game still carrying the value this run wrote: a later sync's reading is the sync's own.
            res = await s.execute(text(
                "UPDATE games SET ca_called_off = NULL "
                "WHERE id = CAST(:g AS UUID) AND ca_called_off = :v"),
                {"g": c["game_id"], "v": c["called_off"]})
            done += res.rowcount
        details["restored_at"] = (await s.execute(text("SELECT NOW()::text"))).scalar()
        details["restored_by"] = by
        await s.execute(text("UPDATE audit_logs SET details = CAST(:d AS JSONB) WHERE id = :i"),
                        {"d": json.dumps(details), "i": audit_id})
        await s.execute(text(
            "INSERT INTO audit_logs (org_id, user_id, action, target_type, target_id, details) "
            "VALUES (CAST(:o AS UUID), NULL, :a, 'organisation', :o, CAST(:d AS JSONB))"),
            {"o": row["org"], "a": RESTORE_ACTION, "d": json.dumps({"by": by, "from_audit": audit_id, "rows": done})})
        await s.commit()
    print(f"RESTORED {done} games from audit entry {audit_id}.")


async def main(args) -> None:
    if args.restore:
        return await restore(args.restore, args.by)
    if args.apply and args.org == "all":
        raise SystemExit("Refusing: --apply is one club at a time. Run the dry run on 'all', then apply club by club.")
    budget = [args.max_games]
    orgs = await _all_orgs() if args.org == "all" else [(await _resolve_org(args.org), args.org)]
    for org, label in orgs:
        if budget[0] <= 0:
            say(f"\n--max-games allowance used up; {label} and later clubs were not read")
            break
        rows, left = await plan(org, args, budget)
        report(rows, left, args.list)
        if args.apply:
            await apply(org, rows, args.expect, args.by)
        else:
            say(f"\nDRY RUN: nothing was changed. To apply:\n  ... {label} --apply --expect {len(rows)} --by \"your name\"")
    say(f"\nscorecards requested: {args.max_games - budget[0]} of {args.max_games} allowed.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("org", nargs="?", help="org id, club slug, or 'all' (dry run only)")
    ap.add_argument("--apply", action="store_true", help="make the change (default is a dry run)")
    ap.add_argument("--expect", type=int, help="the number of rows the plan shows; required with --apply")
    ap.add_argument("--by", help="who is doing this; required with --apply and --restore")
    ap.add_argument("--restore", type=int, metavar="AUDIT_ID", help="undo a previous --apply from its audit entry")
    ap.add_argument("--max-games", type=int, default=200, help="most scorecards to request in the whole run")
    ap.add_argument("--pace", type=float, default=0.5, help="seconds to wait after each scorecard request")
    ap.add_argument("--year", type=int, default=None, help="only seasons with this year")
    ap.add_argument("--list", type=int, default=40, help="called-off games to list")
    ap.add_argument("--timeout", type=int, default=120, help="seconds any one database statement may run")
    a = ap.parse_args()
    if not a.restore and not a.org:
        ap.error("an org is required")
    asyncio.run(main(a))
