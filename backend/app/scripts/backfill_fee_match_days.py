"""Re-derive a club's match fees from the games each player actually appeared in. Dry run unless --apply.

WHY
---
Match fees are charged from `fee_match_days`, one row per (member-season, game). Those rows are
written by `services.fees.recompute_fee_match_days`, which reads real appearances: named in a game
that was played (`game_status.appearance_counts_as_match`, so a called-off or empty game charges
nobody, and a 12th man who did not play is not charged), or a batting, bowling or fielding row.
Since v9.126.1 a game is also charged only from the day after its match day.

Rows made under the older rules can still be sitting there: a fee for a game that was later moved
to a future date, for a game that was called off, or for a player who was named and never played.
This runs the same recompute over a club's seasons so those rows are corrected in one go, and it
adds the match days for appearances that arrived after the last rebuild.

WHAT IT TOUCHES
---------------
Only auto-derived, UNPAID `fee_match_days` rows (and the fee members and member-seasons that a
real appearance calls for). A paid row, a waived row and a row an admin overrode are never
changed or removed. Nobody's payments are touched.

  * Dry run by default: does the whole recompute, rolls it back, and prints what it would do,
    including every unpaid row it would remove.
  * `--apply` needs `--expect N` (members created + rows added or changed + rows removed, as the
    dry run shows, so a run cannot drift from the plan you read) and `--by "name"`.
  * One club per `--apply`. `all` is a dry run only.
  * Every removed row goes, in full, into one `audit_logs` entry. The rows are derived, so a
    rebuild would write one back if the appearance is still real; the entry is there for the
    club to see exactly what went.
  * No calls to Cricket Australia or anyone else: it only reads what is already stored.

Seasons: every season that has fee rows, plus the club's latest. `--year 2026` limits it to one.

Usage, from the server:
  cd /srv/docker && export COMPOSE_PROJECT_NAME=bltbox_docker_app
  docker compose exec -T betterstats-backend python -u -m app.scripts.backfill_fee_match_days <org_id_or_slug_or_all> [--year Y]
  docker compose exec -T betterstats-backend python -u -m app.scripts.backfill_fee_match_days <org> --apply --expect N --by "your name"
"""
import argparse
import asyncio
import json

from sqlalchemy import text

from app.models.db import async_session_maker
from app.scripts.audit_twelfth_man import _all_orgs, _resolve_org, say
from app.services.fees import recompute_fee_match_days

ACTION = "backfill_fee_match_days"


async def seasons_for(org: str, year: int | None) -> list[dict]:
    """Seasons that carry fee rows, plus the latest, newest first."""
    async with async_session_maker() as s:
        rows = (await s.execute(text("""
            SELECT se.id::text AS id, se.name, se.year
              FROM seasons se
             WHERE se.organisation_id = CAST(:o AS UUID)
               AND (CAST(:y AS INTEGER) IS NULL OR se.year = CAST(:y AS INTEGER))
               AND (EXISTS (SELECT 1 FROM fee_member_seasons ms WHERE ms.season_id = se.id)
                    OR se.id = (SELECT id FROM seasons WHERE organisation_id = CAST(:o AS UUID)
                                 ORDER BY year DESC NULLS LAST, name DESC LIMIT 1))
             ORDER BY se.year DESC NULLS LAST, se.name DESC
        """), {"o": org, "y": year})).mappings().all()
    return [dict(r) for r in rows]


async def names_for(removed: list[dict]) -> dict:
    """member_season_id -> player name, and game_id -> 'Home v Away', for the removed-rows listing."""
    if not removed:
        return {}
    async with async_session_maker() as s:
        ms = (await s.execute(text("""
            SELECT ms.id::text AS id, fm.full_name FROM fee_member_seasons ms
              JOIN fee_members fm ON fm.id = ms.member_id
             WHERE ms.id = ANY(CAST(:ids AS uuid[]))"""),
            {"ids": sorted({r["member_season_id"] for r in removed})})).mappings().all()
        gm = (await s.execute(text("""
            SELECT id::text AS id, home_team, away_team, status FROM games
             WHERE id = ANY(CAST(:ids AS uuid[]))"""),
            {"ids": sorted({r["game_id"] for r in removed})})).mappings().all()
    return {**{r["id"]: r["full_name"] for r in ms},
            **{r["id"]: f"{r['home_team']} v {r['away_team']} ({r['status'] or 'no status'})" for r in gm}}


def changes_in(res: dict) -> int:
    return res["members_created"] + res["entries_upserted"] + res["entries_deleted"]


async def one_club(org: str, label: str, args) -> None:
    say(f"\n######## {label}")
    seasons = await seasons_for(org, args.year)
    if not seasons:
        say("no seasons to read")
        return
    plan = []
    for se in seasons:
        res = await recompute_fee_match_days(org, se["id"], dry_run=True)
        plan.append((se, res))
        say(f"  {se['name']}: +{res['members_created']} members, {res['entries_upserted']} rows added or "
            f"changed, {res['entries_deleted']} unpaid rows removed")
    total = sum(changes_in(r) for _, r in plan)
    removed = [dict(r, season=se["name"]) for se, res in plan for r in res["removed"]]
    names = await names_for(removed)
    if removed:
        say(f"\nunpaid rows that would be removed ({len(removed)}), no real appearance behind them:")
        for r in removed[: args.list]:
            say(f"  {r['season']}  {names.get(r['member_season_id'], '?'):<28} {r['played_at'] or 'undated':<11} "
                f"{r['days_played']:g}d  {names.get(r['game_id'], r['game_id'])}")
        if len(removed) > args.list:
            say(f"  ... {len(removed) - args.list} more (raise --list)")
    say(f"\ntotal changes: {total}")

    if not args.apply:
        say(f"\nDRY RUN: nothing was changed. To apply:\n  ... {org} --apply --expect {total} --by \"your name\"")
        return
    if args.expect != total:
        raise SystemExit(f"\nRefusing: --expect {args.expect} but the plan shows {total}. Re-read the plan.")
    if not args.by:
        raise SystemExit("\nRefusing: --by \"your name\" is required, it goes in the audit entry.")
    done = []
    for se, _ in plan:
        res = await recompute_fee_match_days(org, se["id"])
        done.append({"season": se["name"], "season_id": se["id"], "members_created": res["members_created"],
                     "entries_upserted": res["entries_upserted"], "entries_deleted": res["entries_deleted"],
                     "removed": res["removed"]})
    async with async_session_maker() as s:
        audit_id = (await s.execute(text(
            "INSERT INTO audit_logs (org_id, user_id, action, target_type, target_id, details) "
            "VALUES (CAST(:o AS UUID), NULL, :a, 'organisation', :o, CAST(:d AS JSONB)) RETURNING id"),
            {"o": org, "a": ACTION, "d": json.dumps({"by": args.by, "seasons": done})})).scalar()
        await s.commit()
    say(f"\nAPPLIED. Changes: {sum(d['members_created'] + d['entries_upserted'] + d['entries_deleted'] for d in done)}. "
        f"Audit entry {audit_id}.")


async def main(args) -> None:
    if args.org == "all":
        if args.apply:
            raise SystemExit("'all' is a dry run only. Name one club to --apply.")
        targets = await _all_orgs()
    else:
        org = await _resolve_org(args.org)
        targets = [(org, args.org)]
    for org, label in targets:
        await one_club(org, label, args)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("org", help="org id, club slug, or 'all' (dry run only)")
    ap.add_argument("--apply", action="store_true", help="make the change (default is a dry run)")
    ap.add_argument("--expect", type=int, help="the total the dry run shows; required with --apply")
    ap.add_argument("--by", help="who is doing this; required with --apply")
    ap.add_argument("--year", type=int, default=None, help="only the season with this year")
    ap.add_argument("--list", type=int, default=60, help="removed rows to list")
    asyncio.run(main(ap.parse_args()))
