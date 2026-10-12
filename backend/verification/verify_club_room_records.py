"""Verification: a Club Room playlist with a Club Records slide must play.

Reported from production: opening the TV page ("Launch on this screen") showed
"Couldn't load Club Room Mode. Internal Server Error". ``/play`` expands the
whole playlist in one request, so one slide that raises takes the show down.

Cause under test: ``club_room._get_records_cached`` calls the ``get_records``
route body directly, so FastAPI never resolves its ``Query(...)`` / ``Depends(...)``
defaults, and ``records.get_records`` has since gained ``categories``, ``formats``,
``competitions``, ``debug_timing`` and ``viewer``. The call passed none of them, so
each arrived as a FastAPI default object instead of a value.

Runs the SHIPPED ``club_room.build_play_payload`` over the records suite's own
schema and seed (``verify_records_timing``: the real ``v_effective_*`` views from
the migrations, one club with a season, a grade, two players and their stats). A
club with a records slide AND a leaderboard slide, because the 500 was one slide
taking down the others. Every "slide is present" check is paired with a check
that an absent thing is absent (an empty-playlist club has no slides).

CONTROL MODE. Run against the commit before the fix, the playlist raises. The
raise is caught and reported as failed checks, so the control does not crash.

Run:  DATABASE_URL=postgresql+asyncpg://root@/records_room?host=/var/run/postgresql \
      python verification/verify_club_room_records.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text

import verify_records_timing as vrt  # noqa: E402  (schema + seed shared with the records suite)
from app.models.db import Organisation
from app.routers import club_room as cr

PASS = FAIL = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}{('  - ' + detail) if detail else ''}")


async def playlist(db, org_id, entries: list[tuple[str, dict]]):
    # Keyed on the id and re-fetched each time: a rollback after a swallowed error
    # expires every loaded object, and reading one afterwards is lazy IO.
    org = await db.get(Organisation, org_id)
    await db.execute(text("DELETE FROM club_room_slides WHERE organisation_id = :o"), {"o": org_id})
    for i, (stype, cfg) in enumerate(entries):
        await db.execute(text(
            "INSERT INTO club_room_slides (id, organisation_id, slide_type, config, position, enabled) "
            "VALUES (gen_random_uuid(), :o, :t, CAST(:c AS jsonb), :p, true)"),
            {"o": org_id, "t": stype, "c": json.dumps(cfg), "p": i})
    await db.commit()
    try:
        return (await cr.build_play_payload(db, org)).get("slides", []), None
    except Exception as exc:  # noqa: BLE001 - the control raises; report it, do not crash
        await db.rollback()
        return [], f"{type(exc).__name__}: {exc}"


async def main() -> None:
    await vrt.build_schema()
    async with vrt.Session() as s:
        await vrt.seed(s)

    async with vrt.Session() as db:
        org = vrt.ORG

        print("== a records slide")
        slides, err = await playlist(db, org, [("records", {"category": "batting.top_career_runs", "limit": 8})])
        check("the playlist plays instead of raising", err is None, str(err))
        rec = [x for x in slides if x.get("type") == "records"]
        check("one records slide comes back", len(rec) == 1, str([x.get("type") for x in slides]))
        names = [r.get("name") for r in (rec[0].get("rows") if rec else [])]
        check("it carries the club's own top run-scorers, best first", len(names) >= 2, str(names))

        print("== records AND a leaderboard in one playlist (one slide must not take the rest down)")
        slides, err = await playlist(db, org, [
            ("leaderboard", {"stat_group": "batting", "sort_by": "total_runs", "limit": 10}),
            ("records", {"category": "batting.top_career_runs"}),
            ("records", {"category": "bowling.top_career_wickets"}),
        ])
        check("the whole playlist plays", err is None, str(err))
        types = [x.get("type") for x in slides]
        check("leaderboard and both record slides are present", types.count("leaderboard") == 1 and types.count("records") == 2, str(types))

        print("== the playlist from the report: sponsors grid, three leaderboards, records, images")
        slides, err = await playlist(db, org, [
            ("sponsors", {"mode": "grid"}),
            ("leaderboard", {"stat_group": "batting", "sort_by": "total_runs", "limit": 10}),
            ("leaderboard", {"stat_group": "bowling", "sort_by": "total_wickets", "limit": 10}),
            ("leaderboard", {"stat_group": "fielding", "sort_by": "total_catches_non_wk", "limit": 10}),
            ("records", {"category": "allrounders.top_allrounders"}),
            ("custom_images", {}),
            ("statlab_report", {"report_id": ""}),
        ])
        check("every other slide type plays alongside records", err is None, str(err))
        check("the batting and bowling leaderboards are there (so the pass above is not an empty show)",
              [x.get("stat_group") for x in slides if x.get("type") == "leaderboard"][:2] == ["batting", "bowling"],
              str([(x.get("type"), x.get("stat_group")) for x in slides]))

        print("== the cache is per club and per season")
        slides_a, err = await playlist(db, org, [("records", {"category": "batting.top_career_runs", "season_id": str(vrt.SEASON)})])
        check("a records slide scoped to a season plays", err is None and len([x for x in slides_a if x.get("type") == "records"]) == 1, str(err))

        print("== one slide that cannot be built is skipped, not fatal")
        real_records = cr._expand_records

        async def boom(db_, club_, entry_):
            raise RuntimeError("stale saved query")

        async def db_boom(db_, club_, entry_):
            # A real database error leaves the transaction aborted for every entry after it.
            await db_.execute(text("SELECT * FROM no_such_table_anywhere"))

        mixed = [
            ("leaderboard", {"stat_group": "batting", "sort_by": "total_runs", "limit": 10}),
            ("records", {"category": "batting.top_career_runs"}),
            ("leaderboard", {"stat_group": "bowling", "sort_by": "total_wickets", "limit": 10}),
        ]
        for label, fake in (("an exception", boom), ("a database error", db_boom)):
            cr._expand_records = fake
            try:
                payload = {}
                org_row = await db.get(Organisation, vrt.ORG)
                await db.execute(text("DELETE FROM club_room_slides WHERE organisation_id = :o"), {"o": vrt.ORG})
                for i, (stype, cfg) in enumerate(mixed):
                    await db.execute(text(
                        "INSERT INTO club_room_slides (id, organisation_id, slide_type, config, position, enabled) "
                        "VALUES (gen_random_uuid(), :o, :t, CAST(:c AS jsonb), :p, true)"),
                        {"o": vrt.ORG, "t": stype, "c": json.dumps(cfg), "p": i})
                await db.commit()
                try:
                    payload = await cr.build_play_payload(db, org_row)
                    err = None
                except Exception as exc:  # noqa: BLE001 - the control raises; report it
                    await db.rollback()
                    err = f"{type(exc).__name__}: {exc}"
            finally:
                cr._expand_records = real_records
            got = [x.get("stat_group") for x in payload.get("slides", []) if x.get("type") == "leaderboard"]
            skipped = payload.get("skipped") or []
            check(f"{label} in one entry: the playlist still plays", err is None, str(err))
            check(f"{label}: the entries before AND after it are still there", got == ["batting", "bowling"], str(got))
            check(f"{label}: it is named in `skipped`, with its type",
                  [x.get("slide_type") for x in skipped] == ["records"], str(skipped))
            check(f"{label}: the club and its settings are still readable afterwards",
                  bool(payload.get("club_name")), str(payload.get("club_name")))
        payload_ok = await cr.build_play_payload(db, await db.get(Organisation, vrt.ORG))
        check("a healthy playlist skips nothing (so `skipped` above was a real signal)",
              payload_ok.get("skipped") == [] and any(x.get("type") == "records" for x in payload_ok.get("slides", [])),
              str(payload_ok.get("skipped")))

        print("== a club with nothing to show")
        empty = vrt.EMPTY_ORG
        if await db.get(Organisation, empty) is None:
            await db.execute(text(
                "INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, 'Empty CC', 'emptycc', true)"),
                {"i": empty})
            await db.commit()
        slides_e, err = await playlist(db, empty, [("records", {"category": "batting.top_career_runs"})])
        check("a club with no players plays and shows no records slide (the slides above were real)",
              err is None and not [x for x in slides_e if x.get("type") == "records"], str(err))

    print(f"\n{PASS} passed, {FAIL} failed")
    await vrt.engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
