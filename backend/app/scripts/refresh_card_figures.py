"""Put a club's recent games right where the stored figures are short of the card CA now calls COMPLETED. Dry run unless --apply.

A game stored while Cricket Australia still had it in play (a two-day game is read by Sunday 01:00, on
its first day) keeps the batting, bowling and fielding figures it was stored with, and Fantasy scores
those: Leederville CC, Oct 2026, a 40 odd read as 1 point and four wickets as 24. Sync now puts a
recent game right whenever it reads the card (`services/card_figures_refresh.py`); this does the same
for games already stored, which are outside every sync window now.

  * Reads the club's games of the last `--days` (default 14) that sync stored, one paced scorecard
    request each (the client caches), bounded by `--max-games`.
  * Only a card CA calls COMPLETED is believed. Only the club's own players. Figures are updated in
    place (ids kept); a missing batting or bowling row is not added here (a sync's re-read does that),
    and nothing is deleted.
  * Dry run by default: prints every figure it would change and writes nothing.
  * `--apply` needs `--expect N` (the number of changes the plan shows, so a run cannot drift from
    the plan you read) and `--by "name"`. One club per `--apply`.
  * Every change goes, in full, into one `audit_logs` entry in the same transaction.
    `--restore AUDIT_ID` puts each figure back to what it was, but only where it still holds what this
    run wrote, and takes out a fielding row this run added. An entry restores once.

After an apply, Fantasy follows on its own (the nightly job settles a round again when its points no
longer match the scorecards); to do it now: `python -m app.scripts.fantasy_round_drift <org> --apply`.

Usage, from the server:
  cd /srv/docker && export COMPOSE_PROJECT_NAME=bltbox_docker_app
  docker compose exec -T betterstats-backend python -u -m app.scripts.refresh_card_figures <org_id_or_slug_or_all> [--days 14]
  docker compose exec -T betterstats-backend python -u -m app.scripts.refresh_card_figures <org> --apply --expect N --by "your name"
  docker compose exec -T betterstats-backend python -u -m app.scripts.refresh_card_figures <org> --restore AUDIT_ID --by "your name"
"""
import argparse
import asyncio
import json
from datetime import date, timedelta

from sqlalchemy import text

from app.models.db import async_session_maker
from app.scripts.audit_twelfth_man import _all_orgs, _resolve_org, say
from app.services import card_figures_refresh as cfr, grassroots_scores_client as gr, participant_relink

ACTION = "refresh_card_figures"
RESTORE_ACTION = "refresh_card_figures_restore"


async def _games(org: str, days: int) -> list[dict]:
    """The club's synced games of the last `days` that name one of its players, newest first."""
    async with async_session_maker() as s:
        await s.execute(text("SET TRANSACTION READ ONLY"))
        rows = (await s.execute(text("""
            SELECT g.id::text AS id, g.played_at, g.home_team, g.away_team, gr.name AS grade, g.status
              FROM games g
              LEFT JOIN grades gr ON gr.id = g.grade_id
              LEFT JOIN seasons se ON se.id = gr.season_id
             WHERE g.played_at >= :since AND g.played_at <= CURRENT_DATE
               AND (g.home_org_id = CAST(:o AS UUID) OR g.away_org_id = CAST(:o AS UUID)
                    OR se.organisation_id = CAST(:o AS UUID))
               AND EXISTS (SELECT 1 FROM game_appearances ga JOIN players p ON p.id = ga.player_id
                            WHERE ga.game_id = g.id AND p.organisation_id = CAST(:o AS UUID))
             ORDER BY g.played_at DESC"""), {"o": org, "since": date.today() - timedelta(days=days)})).mappings().all()
    return [dict(r) for r in rows]


async def plan(org: str, args, budget: list[int]) -> tuple[list[dict], dict]:
    games = await _games(org, args.days)
    say(f"\n######## {org}\n{len(games)} synced game(s) in the last {args.days} days")
    out: list[dict] = []
    seen = {"read": 0, "no_card": 0, "not_final": 0, "already_right": 0, "allowance": 0}
    async with async_session_maker() as s:
        await s.execute(text("SET TRANSACTION READ ONLY"))
        by_guid, merged, _unique = await participant_relink._org_maps(s, org)

        def resolve(guid: str):
            return participant_relink._known(guid, by_guid, merged)

        for g in games:
            if budget[0] <= 0:
                seen["allowance"] += 1
                continue
            budget[0] -= 1
            card = await gr.get_match_scorecard(g["id"])
            await asyncio.sleep(args.pace)
            seen["read"] += 1
            if not card:
                seen["no_card"] += 1
                continue
            if not cfr.is_final(card):
                seen["not_final"] += 1
                continue
            changes = await cfr.plan_game(s, org, g["id"], card, resolve)
            if not changes:
                seen["already_right"] += 1
                continue
            names = {r[0]: r[1] for r in (await s.execute(text(
                "SELECT id::text, COALESCE(display_name_override, name) FROM players "
                "WHERE id = ANY(CAST(:i AS uuid[]))"), {"i": sorted({str(c['player_id']) for c in changes})})).all()}
            for c in changes:
                c["player"] = names.get(str(c["player_id"]), "?")
                c["date"] = str(g["played_at"])[:10]
                c["grade"] = g["grade"]
                c["match"] = f"{g['home_team']} v {g['away_team']}"
            out.extend(changes)
    return out, seen


def report(changes: list[dict], seen: dict, limit: int) -> None:
    say(f"read {seen['read']} card(s): {seen['already_right']} already right, {seen['not_final']} not COMPLETED, "
        f"{seen['no_card']} with no card" + (f", {seen['allowance']} left unread (--max-games)" if seen["allowance"] else ""))
    games = {(c["date"], c["match"]) for c in changes}
    players = {c["player_id"] for c in changes}
    say(f"\nwould change {len(changes)} figure(s) for {len(players)} player(s) across {len(games)} game(s)")
    shown = 0
    for c in sorted(changes, key=lambda c: (c["date"], c["match"], c["player"]), reverse=True):
        if shown >= limit:
            say(f"  ... {len(changes) - shown} more (raise --list)")
            break
        shown += 1
        what = "added a fielding row" if c["op"] == "insert" else f"{c['table']}.{c['field']} {c['old']} -> {c['new']}"
        if c["op"] == "insert":
            what += f" {c['new']}"
        inn = f" inns {c['innings']}" if c["innings"] else ""
        say(f"  {c['date']}  {c['player']:<26}{inn:<8} {what}   [{c['grade']}]")


async def apply(org: str, changes: list[dict], expect: int | None, by: str | None) -> None:
    if expect != len(changes):
        raise SystemExit(f"\nRefusing: --expect {expect} but the plan shows {len(changes)} changes. Re-read the plan.")
    if not by:
        raise SystemExit("\nRefusing: --by \"your name\" is required, it goes in the audit entry.")
    if not changes:
        print("\nNothing to apply.")
        return
    async with async_session_maker() as s:
        n = await cfr.apply_changes(s, changes)
        keep = ("op", "table", "id", "game_id", "player_id", "innings", "field", "old", "new", "inserted_id")
        slim = [{k: c.get(k) for k in keep} for c in changes]
        audit_id = (await s.execute(text(
            "INSERT INTO audit_logs (org_id, user_id, action, target_type, target_id, details) "
            "VALUES (CAST(:o AS UUID), NULL, :a, 'organisation', :o, CAST(:d AS JSONB)) RETURNING id"),
            {"o": org, "a": ACTION, "d": json.dumps({"by": by, "changes": slim}, default=str)})).scalar()
        await s.commit()
    print(f"\nAPPLIED {len(changes)} change(s) on {n} row(s). Audit entry {audit_id}. "
          f"To undo: --restore {audit_id} --by \"your name\"")
    print(f"Fantasy follows on the nightly run, or now: python -m app.scripts.fantasy_round_drift {org} --apply")


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
        done = skipped = 0
        for c in details["changes"]:
            if c["op"] == "insert":
                if c.get("inserted_id"):
                    res = await s.execute(text("DELETE FROM fielding_stats WHERE id = :id"), {"id": c["inserted_id"]})
                    done += res.rowcount
                continue
            # Only a figure still holding what this run wrote: one changed since is somebody else's.
            res = await s.execute(text(
                f"UPDATE {c['table']} SET {c['field']} = :old WHERE id = :id AND {c['field']} IS NOT DISTINCT FROM :new"),
                {"old": c["old"], "new": c["new"], "id": c["id"]})
            done += res.rowcount
            skipped += 0 if res.rowcount else 1
        details["restored_at"] = (await s.execute(text("SELECT NOW()::text"))).scalar()
        details["restored_by"] = by
        await s.execute(text("UPDATE audit_logs SET details = CAST(:d AS JSONB) WHERE id = :i"),
                        {"d": json.dumps(details, default=str), "i": audit_id})
        await s.execute(text(
            "INSERT INTO audit_logs (org_id, user_id, action, target_type, target_id, details) "
            "VALUES (CAST(:o AS UUID), NULL, :a, 'organisation', :o, CAST(:d AS JSONB))"),
            {"o": row["org"], "a": RESTORE_ACTION,
             "d": json.dumps({"by": by, "from_audit": audit_id, "restored": done, "left_as_changed_since": skipped})})
        await s.commit()
    print(f"RESTORED {done} change(s) from audit entry {audit_id}; {skipped} left alone (changed since).")


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
        changes, seen = await plan(org, args, budget)
        report(changes, seen, args.list)
        if args.apply:
            await apply(org, changes, args.expect, args.by)
        else:
            say(f"\nDRY RUN: nothing was changed. To apply:\n  ... {label} --apply --expect {len(changes)} --by \"your name\"")
    say(f"\nscorecards requested: {args.max_games - budget[0]} of {args.max_games} allowed.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("org", nargs="?", help="org id, club slug, or 'all' (dry run only)")
    ap.add_argument("--apply", action="store_true", help="make the change (default is a dry run)")
    ap.add_argument("--expect", type=int, help="the number of changes the plan shows; required with --apply")
    ap.add_argument("--by", help="who is doing this; required with --apply and --restore")
    ap.add_argument("--restore", type=int, metavar="AUDIT_ID", help="undo a previous --apply from its audit entry")
    ap.add_argument("--days", type=int, default=14, help="how far back to read games (default 14)")
    ap.add_argument("--max-games", type=int, default=120, help="most scorecards to request in the whole run")
    ap.add_argument("--pace", type=float, default=0.5, help="seconds to wait after each scorecard request")
    ap.add_argument("--list", type=int, default=60, help="changes to list")
    a = ap.parse_args()
    if not a.restore and not a.org:
        ap.error("an org is required")
    asyncio.run(main(a))
