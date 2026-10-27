"""Name the winner of finished games that hold a WIN or LOSS and no winning team. Dry run unless --apply.

`games.result` is WIN or LOSS from the point of view of whichever club's sync wrote it. `winning_team` is the
winning side's name and neutral, so every page works out its own club's result from it. A game with a WIN or
LOSS and no winner reads backwards to the other club (Shoalwater Bay's 2025/26 Ladies B Grade Grand Final,
stored by Secret Harbour as LOSS with no winner, showed Shoalwater's premiership as a loss). The sync now
names the winner for these and reads them again whatever their age (services/game_winner); this script fills
in the ones already stored without waiting for the next sync.

  Reads the scorecard (one paced request per game), takes the winner from CA's own flags
  (sync.winning_team_name), and writes it only when it names exactly one of the game's two stored sides, so
  the pages' name comparison can use it. Anything else is left as it is and listed.

  * Dry run by default: prints what it would write and writes nothing.
  * `--apply` needs `--expect N` (the number of rows the plan shows) and `--by "name"`. One club per `--apply`.
  * Only rows still without a winner are written. Every row goes, in full, into one `audit_logs` entry in the
    same transaction. `--restore AUDIT_ID` puts every one of those back to NULL, only where the winner is still
    the one this run wrote. An entry restores once.
  * Bounded by `--max-games`, paced by `--pace`.

Usage, from the server:
  cd /srv/docker && export COMPOSE_PROJECT_NAME=bltbox_docker_app
  docker compose exec -T betterstats-backend python -u -m app.scripts.backfill_game_winners <org_id_or_slug_or_all>
  docker compose exec -T betterstats-backend python -u -m app.scripts.backfill_game_winners <org> --apply --expect N --by "your name"
  docker compose exec -T betterstats-backend python -u -m app.scripts.backfill_game_winners <org> --restore AUDIT_ID --by "your name"
"""
import argparse
import asyncio
import json
from collections import Counter

from sqlalchemy import text

from app.models.db import async_session_maker
from app.scripts.audit_twelfth_man import _all_orgs, _resolve_org, say
from app.services import grassroots_scores_client as gr
from app.services.sync import winning_team_name

ACTION = "backfill_game_winners"
RESTORE_ACTION = "backfill_game_winners_restore"


async def _candidates(session, org: str) -> list[dict]:
    rows = (await session.execute(text("""
        SELECT g.id::text AS game_id, g.played_at, g.home_team, g.away_team, g.result,
               COALESCE(gr.name, '') AS grade
          FROM games g
          LEFT JOIN grades gr ON gr.id = g.grade_id
          LEFT JOIN seasons s ON s.id = gr.season_id
         WHERE g.result IN ('WIN', 'LOSS')
           AND g.status = 'COMPLETED'
           AND nullif(btrim(g.winning_team), '') IS NULL
           AND (g.home_org_id = CAST(:org AS UUID) OR g.away_org_id = CAST(:org AS UUID)
                OR s.organisation_id = CAST(:org AS UUID))
         ORDER BY g.played_at DESC NULLS LAST
    """), {"org": org})).mappings().all()
    return [dict(r) for r in rows]


async def plan(org: str, args, budget: list[int]) -> tuple[list[dict], Counter]:
    """The rows to write for one club: [{game_id, winner, date, grade, stored_result}], and why not."""
    say(f"\n######## {org}\nreading games with a result and no winner (no upstream calls yet)...")
    async with async_session_maker() as session:
        await session.execute(text("SET TRANSACTION READ ONLY"))
        await session.execute(text(f"SET LOCAL statement_timeout = {int(args.timeout) * 1000}"))
        games = await _candidates(session, org)
    say(f"{len(games)} games hold a WIN or LOSS and no winner")

    rows: list[dict] = []
    left: Counter = Counter()
    for c in games:
        if budget[0] <= 0:
            left["allowance ran out"] += 1
            continue
        budget[0] -= 1
        card = await gr.get_match_scorecard(c["game_id"], force=True)
        await asyncio.sleep(args.pace)
        if not card:
            left["CA returned no card"] += 1
            continue
        winner = winning_team_name(card)
        if not winner:
            left["the card names no winner"] += 1
            continue
        sides = {(c["home_team"] or "").strip(), (c["away_team"] or "").strip()}
        if winner.strip() not in sides:
            left["the card's winner is not spelled like either stored side"] += 1
            continue
        rows.append({"game_id": c["game_id"], "winner": winner.strip(), "date": str(c["played_at"])[:10],
                     "grade": c["grade"], "stored_result": c["result"]})
    return rows, left


def report(rows: list[dict], left: Counter, limit: int) -> None:
    say(f"\nwould set winning_team on {len(rows)} games")
    for why, n in left.most_common():
        say(f"left as they are: {n}  ({why})")
    for r in rows[:limit]:
        say(f"  {r['date']}  {str(r['grade']):<28} stored {r['stored_result']:<4} -> winner {r['winner']}  {r['game_id']}")
    if len(rows) > limit:
        say(f"  ... {len(rows) - limit} more (raise --list)")


async def apply(org: str, rows: list[dict], expect: int | None, by: str | None) -> None:
    if expect != len(rows):
        raise SystemExit(f"\nRefusing: --expect {expect} but the plan shows {len(rows)} rows. Re-read the plan.")
    if not by:
        raise SystemExit("\nRefusing: --by \"your name\" is required, it goes in the audit entry.")
    async with async_session_maker() as s:
        changes = [{"game_id": r["game_id"], "winner": r["winner"]} for r in rows]
        audit_id = (await s.execute(text(
            "INSERT INTO audit_logs (org_id, user_id, action, target_type, target_id, details) "
            "VALUES (CAST(:o AS UUID), NULL, :a, 'organisation', :o, CAST(:d AS JSONB)) RETURNING id"),
            {"o": org, "a": ACTION, "d": json.dumps({"by": by, "changes": changes})})).scalar()
        done = 0
        for r in rows:
            res = await s.execute(text(
                "UPDATE games SET winning_team = :w "
                "WHERE id = CAST(:g AS UUID) AND nullif(btrim(winning_team), '') IS NULL"),
                {"w": r["winner"], "g": r["game_id"]})
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
        # The audit trail is append-only: "already restored" is read from the restore entry, never by editing this one.
        done_before = (await s.execute(text(
            "SELECT created_at::text FROM audit_logs WHERE action = :a AND details->>'from_audit' = :i"),
            {"a": RESTORE_ACTION, "i": str(audit_id)})).scalar()
        if done_before:
            raise SystemExit(f"Audit entry {audit_id} was already restored ({done_before}).")
        done = 0
        for c in details["changes"]:
            # Only a game still carrying the winner this run wrote: a later sync's reading is the sync's own.
            res = await s.execute(text(
                "UPDATE games SET winning_team = NULL "
                "WHERE id = CAST(:g AS UUID) AND winning_team = :w"),
                {"g": c["game_id"], "w": c["winner"]})
            done += res.rowcount
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
    ap.add_argument("--max-games", type=int, default=100, help="most scorecards to request in the whole run")
    ap.add_argument("--pace", type=float, default=0.5, help="seconds to wait after each scorecard request")
    ap.add_argument("--list", type=int, default=40, help="games to list")
    ap.add_argument("--timeout", type=int, default=120, help="seconds any one database statement may run")
    a = ap.parse_args()
    if not a.restore and not a.org:
        ap.error("an org is required")
    asyncio.run(main(a))
