"""Group EVERY club's grades into competitions, now, in one pass.

Why this exists
---------------
A grade can only sit in a competition once we know which association ran it.
The sync writes that as it goes, but only for the seasons it scans, so every
club onboarded before migration 283 carries a history with none — and doing it
club by club is one Cricket Australia call per club per season.

Three phases of PLAIN SQL over our own data do most of the work first
(``services/association_backfill.py`` explains all three): a CA grade guid is
competition-wide, so an association any club holds is the answer for every
club's row carrying that guid; a club's own grade NAME is its own competition,
so one recent sync propagates backwards across every season of that name; and
a club the Club Directory shows playing in exactly one association can have
its WHOLE gap filled from that alone, matched by name since the Directory's
own ids are a different namespace from Grassroots'.

Only what is left after that is fetched, and every answer is applied across
EVERY club immediately — so the first club processed in an association
resolves the grade guids for all the others and their seasons drop off the
list before they are ever called.

Usage
-----
    python -m app.scripts.backfill_all_associations                  # dry run
    python -m app.scripts.backfill_all_associations --apply
    python -m app.scripts.backfill_all_associations --apply --no-api # SQL only
    python -m app.scripts.backfill_all_associations --apply --org <id-or-slug>
    python -m app.scripts.backfill_all_associations --apply --concurrency 8

Dry run by default, per the house rule. A dry run does the SQL phases inside a
transaction it rolls back, so it reports exactly what would be filled without
writing anything, and makes no API calls at all.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services import association_backfill as ab
from app.services import playhq_client
from app.services.competition_grouping import _associations_from_teams
from app.services.competitions import seed_competitions_for_org

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")


async def _resolve_org(db, value: str):
    res = await db.execute(text(
        "SELECT id, name FROM organisations WHERE CAST(id AS TEXT) = :v OR slug = :v"
    ), {"v": value})
    row = res.first()
    if not row:
        sys.exit(f"No club matches {value!r}")
    return row[0], row[1]


async def _gap(db, org_id=None) -> tuple[int, int]:
    clause = " AND s.organisation_id = CAST(:org AS UUID)" if org_id else ""
    res = await db.execute(text(
        f"""
        SELECT COUNT(*) FILTER (WHERE gr.association_id IS NULL) AS no_assoc,
               COUNT(*) AS total
          FROM grades gr JOIN seasons s ON s.id = gr.season_id
         WHERE TRUE{clause}
        """
    ), ({"org": str(org_id)} if org_id else {}))
    row = res.mappings().first()
    return int(row["no_assoc"]), int(row["total"])


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write the changes")
    ap.add_argument("--no-api", action="store_true",
                    help="the two SQL phases only, no Cricket Australia calls")
    ap.add_argument("--org", help="one club (id or slug); default is every club")
    ap.add_argument("--concurrency", type=int, default=6,
                    help="parallel CA calls (default 6, the client's own limit)")
    args = ap.parse_args()

    started = time.perf_counter()
    org_id = org_name = None
    async with async_session_maker() as db:
        if args.org:
            org_id, org_name = await _resolve_org(db, args.org)
        before, total = await _gap(db, org_id)
        scope = f"{org_name}" if org_id else "every club"
        print(f"{scope}: {before} of {total} grade rows have no association")
        if not before:
            print("Nothing to do.")
            return

        # ---- phases 1 + 2: our own data, no API ----------------------------
        if args.apply:
            sql = await ab.propagate_all(db)
            mid, _ = await _gap(db, org_id)
        else:
            # Fill inside the open transaction, measure the residual gap while
            # the writes are still visible, THEN roll back — measuring after
            # the rollback would report the gap we started with.
            sql = await ab.propagate_all(db, commit=False)
            mid, _ = await _gap(db, org_id)
            # NOT rolled back here: the plan below has to be measured while the
            # fill is still visible, or it counts calls for seasons our own
            # data has already answered.

        print(f"  from another club's row for the same CA grade: "
              f"{sql['filled_by_grade_guid']}")
        print(f"  from the club's own other seasons of that grade: "
              f"{sql['filled_by_club_grade_name']}")
        print(f"  from the Club Directory, for a club playing in exactly one: "
              f"{sql['filled_by_directory']}")
        print(f"  still missing after our own data: {mid}")

        # THE NUMBER THAT DECIDES HOW LONG THIS TAKES is not the grade rows
        # left, it is how many Cricket Australia calls they cost — and one
        # fetched season resolves grades other clubs share, so the two are a
        # long way apart. Worked out from our own data, no request made.
        if not args.apply or args.no_api:
            plan = await ab.plan_api_phase(db, org_id)
            print(f"  seasons still holding one: {plan['seasons_outstanding']}")
            print(f"  Cricket Australia calls that would need: "
                  f"~{plan['projected_calls']} "
                  f"({plan['resolved_by_another_club']} season(s) resolved by "
                  f"another club's answer before being asked)")
            if not args.apply:
                await db.rollback()

    if args.no_api or not args.apply:
        if not args.apply:
            print("\nDry run — nothing written, no API calls made. "
                  "Re-run with --apply.")
        else:
            await _seed(org_id)
        _done(started)
        return

    # ---- phase 3: fetch only what our own data could not answer ------------
    fetched = calls = skipped = failed = 0
    sem = asyncio.Semaphore(max(1, args.concurrency))

    while True:
        async with async_session_maker() as db:
            todo = await ab.outstanding_seasons(db, org_id)
        if not todo:
            break

        async def one(job):
            nonlocal fetched, calls, skipped, failed
            async with async_session_maker() as db:
                # Re-checked here, not only when the list was built: another
                # club's answer may have resolved this season in the meantime.
                still = await ab.outstanding_seasons(db, job["org_id"])
                if not any(j["season_guid"] == job["season_guid"] for j in still):
                    skipped += 1
                    return
            async with sem:
                try:
                    teams = await playhq_client.get_teams(
                        str(job["org_id"]), job["season_guid"])
                except Exception as e:
                    failed += 1
                    logging.warning("teams failed for %s / %s: %s",
                                    job["org_id"], job["season_name"], e)
                    return
            calls += 1
            found = _associations_from_teams(teams)
            if not found:
                return
            async with async_session_maker() as db:
                fetched += await ab.apply_associations(db, found)
                await db.commit()

        await asyncio.gather(*(one(j) for j in todo))
        # One pass only: everything the calls could resolve is resolved, and a
        # second lap would re-ask for the seasons CA has no answer for.
        break

    async with async_session_maker() as db:
        sql2 = await ab.propagate_all(db)
        after, _ = await _gap(db, org_id)

    print(f"  fetched from Cricket Australia: {calls} call(s), "
          f"{fetched} grade row(s) filled ({skipped} season(s) already resolved "
          f"by another club, {failed} failed)")
    print(f"  a second pass over our own data filled "
          f"{sql2['filled_by_grade_guid'] + sql2['filled_by_club_grade_name'] + sql2['filled_by_directory']} more")
    print(f"  still without an association: {after} "
          f"(Cricket Australia has none for these)")

    await _seed(org_id)
    _done(started)


async def _seed(org_id=None) -> None:
    """Group what the fill unlocked, club by club. Skip-don't-replace, so a
    competition a club has renamed or split keeps its own naming."""
    async with async_session_maker() as db:
        res = await db.execute(text(
            "SELECT id, name FROM organisations"
            + (" WHERE id = CAST(:org AS UUID)" if org_id else "")
            + " ORDER BY name"
        ), ({"org": str(org_id)} if org_id else {}))
        rows = res.all()
    created = assigned = 0
    for oid, _name in rows:
        async with async_session_maker() as db:
            try:
                out = await seed_competitions_for_org(db, oid)
                await db.commit()
            except Exception as e:
                await db.rollback()
                logging.warning("seeding failed for %s: %s", _name, e)
                continue
        created += out.get("competitions_created", 0)
        assigned += out.get("grades_assigned", 0)
    print(f"  grouped: {created} competition(s) created, "
          f"{assigned} grade(s) assigned")


def _done(started: float) -> None:
    print(f"Finished in {time.perf_counter() - started:.1f}s")


if __name__ == "__main__":
    asyncio.run(main())
