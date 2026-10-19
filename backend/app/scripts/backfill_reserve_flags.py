"""Judge which named-only appearances were a 12th man or substitute, from CA's scorecard. Dry run unless --apply.

`game_appearances.is_reserve` is written by the sync for games it stores from now on. This reads the
games already stored (services/reserve_players.py is the rule, `app.scripts.audit_twelfth_man` is the
evidence for it) and sets the flag on every named-only appearance it can judge. A player with a batting,
bowling or fielding row of their own is never touched: the flag cannot change what they count.

  TRUE   a reserve: the side batted, the player is not on its card, no bowling or fielding, slot 12 or later
  FALSE  judged and not a reserve (on the card as Did Not Bat, the side never batted, inside the XI, ...)
  NULL   left alone: CA returned nothing, the id is not on the sheet, or CA does not call the game COMPLETED

Only rows still NULL are read, so a second run costs nothing, and a flag a person set is never replaced.

  * Dry run by default: prints what it would write and writes nothing.
  * `--apply` needs `--expect N` (the number of rows the plan shows, so a run cannot drift from the plan you
    read) and `--by "name"`. One club per `--apply`.
  * Every row it writes goes, in full, into one `audit_logs` entry in the same transaction.
    `--restore AUDIT_ID` puts every one of those rows back to NULL. An entry restores once.
  * One paced scorecard request per game (the client caches), bounded by `--max-games`.

Usage, from the server:
  cd /srv/docker && export COMPOSE_PROJECT_NAME=bltbox_docker_app
  docker compose exec -T betterstats-backend python -u -m app.scripts.backfill_reserve_flags <org_id_or_slug_or_all> [--max-games 900] [--year Y]
  docker compose exec -T betterstats-backend python -u -m app.scripts.backfill_reserve_flags <org> --apply --expect N --by "your name"
  docker compose exec -T betterstats-backend python -u -m app.scripts.backfill_reserve_flags <org> --restore AUDIT_ID --by "your name"
"""
import argparse
import asyncio
import json
from collections import Counter

from sqlalchemy import text

from app.models.db import async_session_maker
from app.scripts.audit_twelfth_man import _all_orgs, _candidates, _merged_guids, _resolve_org, say
from app.services import grassroots_scores_client as gr
from app.services.reserve_players import TWELFTH_MAN, classify

ACTION = "backfill_reserve_flags"
RESTORE_ACTION = "backfill_reserve_flags_restore"
# Judged, and not a reserve. NO_CARD and NOT_ON_SHEET are left NULL: nothing can be said.
_NOT_RESERVE = {"ON_CARD_DNB", "SIDE_DID_NOT_BAT", "INSIDE_XI", "HAS_STATS"}


async def plan(org: str, args, budget: list[int]) -> tuple[list[dict], Counter]:
    """The rows to write for one club: [{game_id, player_id, is_reserve, slot}], and a tally of why not."""
    say(f"\n######## {org}\nreading named-only appearances from the database (no upstream calls yet)...")
    async with async_session_maker() as session:
        await session.execute(text("SET TRANSACTION READ ONLY"))
        await session.execute(text(f"SET LOCAL statement_timeout = {int(args.timeout) * 1000}"))
        cands = [c for c in await _candidates(session, org, args.year) if c["stored_reserve"] is None]
        merged = await _merged_guids(session, sorted({c["player_id"] for c in cands}))
    say(f"{len(cands)} appearances not yet judged across {len({c['game_id'] for c in cands})} games")

    cards: dict[str, dict | None] = {}
    rows: list[dict] = []
    left: Counter = Counter()
    for c in cands:
        gid = c["game_id"]
        if gid not in cards:
            if budget[0] <= 0:
                left["allowance ran out"] += 1
                continue
            budget[0] -= 1
            cards[gid] = await gr.get_match_scorecard(gid)
            await asyncio.sleep(args.pace)
        card = cards[gid]
        if not card or (card.get("status") or "").upper() != "COMPLETED":
            left["CA does not call it COMPLETED, or returned no card"] += 1
            continue
        guids = {str(c["raw_guid"]).lower(), str(c["player_id"]).lower()} | merged.get(c["player_id"], set())
        res = classify(card, guids)
        if res["code"] == TWELFTH_MAN:
            rows.append({"game_id": gid, "player_id": c["player_id"], "is_reserve": True, "slot": res["slot"],
                         "name": c["player_name"], "date": str(c["played_at"])[:10], "grade": c["grade"]})
        elif res["code"] in _NOT_RESERVE:
            rows.append({"game_id": gid, "player_id": c["player_id"], "is_reserve": False, "slot": res["slot"],
                         "name": c["player_name"], "date": str(c["played_at"])[:10], "grade": c["grade"]})
        else:
            left[res["code"]] += 1
    return rows, left


def report(rows: list[dict], left: Counter, limit: int) -> None:
    flagged = [r for r in rows if r["is_reserve"]]
    say(f"\nwould set is_reserve TRUE  on {len(flagged)} appearances (12th man, no row of their own)")
    say(f"would set is_reserve FALSE on {len(rows) - len(flagged)} appearances (judged, played or not a reserve)")
    for why, n in left.most_common():
        say(f"left NULL: {n}  ({why})")
    if flagged:
        say("\nreserves (newest first):")
        for r in sorted(flagged, key=lambda r: r["date"], reverse=True)[:limit]:
            say(f"  {r['date']}  {r['name']:<28} slot {r['slot']!s:<3} {str(r['grade']):<24} {r['game_id']}")
        if len(flagged) > limit:
            say(f"  ... {len(flagged) - limit} more (raise --list)")


async def apply(org: str, rows: list[dict], expect: int | None, by: str | None) -> None:
    if expect != len(rows):
        raise SystemExit(f"\nRefusing: --expect {expect} but the plan shows {len(rows)} rows. Re-read the plan.")
    if not by:
        raise SystemExit("\nRefusing: --by \"your name\" is required, it goes in the audit entry.")
    async with async_session_maker() as s:
        changes = [{"game_id": r["game_id"], "player_id": r["player_id"], "is_reserve": r["is_reserve"],
                    "slot": r["slot"]} for r in rows]
        audit_id = (await s.execute(text(
            "INSERT INTO audit_logs (org_id, user_id, action, target_type, target_id, details) "
            "VALUES (CAST(:o AS UUID), NULL, :a, 'organisation', :o, CAST(:d AS JSONB)) RETURNING id"),
            {"o": org, "a": ACTION, "d": json.dumps({"by": by, "changes": changes})})).scalar()
        done = 0
        for r in rows:
            res = await s.execute(text(
                "UPDATE game_appearances SET is_reserve = :v, sheet_slot = :slot "
                "WHERE game_id = CAST(:g AS UUID) AND player_id = CAST(:p AS UUID) AND is_reserve IS NULL"),
                {"v": r["is_reserve"], "slot": r["slot"], "g": r["game_id"], "p": r["player_id"]})
            done += res.rowcount
        await s.commit()
    print(f"\nAPPLIED to {done} rows. Audit entry {audit_id}. To undo: --restore {audit_id} --by \"your name\"")


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
            # Only a row still carrying the value this run wrote: a flag set since is somebody else's.
            res = await s.execute(text(
                "UPDATE game_appearances SET is_reserve = NULL, sheet_slot = NULL "
                "WHERE game_id = CAST(:g AS UUID) AND player_id = CAST(:p AS UUID) AND is_reserve = :v"),
                {"g": c["game_id"], "p": c["player_id"], "v": c["is_reserve"]})
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
    print(f"RESTORED {done} rows from audit entry {audit_id}.")


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
    ap.add_argument("--list", type=int, default=40, help="reserves to list")
    ap.add_argument("--timeout", type=int, default=120, help="seconds any one database statement may run")
    a = ap.parse_args()
    if not a.restore and not a.org:
        ap.error("an org is required")
    asyncio.run(main(a))
