"""Verification: a Custom StatLab Report slide plays under the report's own Grade type.

Reported by Shoalwater Bay CC: a Women's runs and wickets report built in StatLab
and added to Club Room Mode played the men's figures.

Cause under test: StatLab saves "Grade type" and "Match type" in the report's
``context`` as ``categories`` / ``formats``. The live ``/statlab/query`` route turns
them into a ``GradeScope`` and hands it to the service under ``_scope``. The Club
Room slide called the service with the saved context as it stood and no scope, so
every report was read under the club's default grade types, which leaves a
women's grade out.

Runs the SHIPPED ``club_room.build_play_payload`` over the records suite's schema
and seed, plus a women's grade with its own players. Each "the women are shown"
check is paired with one proving the men could be shown (a report with no grade
type still plays the club default, and a Men's pick shows the men).

CONTROL MODE. Against the commit before the fix the Women's report plays the men
and the checks fail without crashing.

Run:  DATABASE_URL=postgresql+asyncpg://root@/room_statlab?host=/var/run/postgresql \
      python verification/verify_club_room_statlab_scope.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text

import verify_records_timing as vrt  # noqa: E402
from app.models.db import Organisation
from app.routers import club_room as cr

PASS = FAIL = 0
W_GRADE = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
W_ONE = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000002")
W_TWO = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000003")


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}{('  - ' + detail) if detail else ''}")


async def seed_womens(db) -> None:
    async def ex(sql, **kw):
        await db.execute(text(sql), kw)

    await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
             "VALUES (:i, :s, 'Womens T20', :g, 'womens', ARRAY['womens'])",
             i=W_GRADE, s=vrt.SEASON, g=str(W_GRADE))
    for pid, nm in ((W_ONE, "Wilson, Wendy"), (W_TWO, "Webb, Wanda")):
        await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) "
                 "VALUES (:i, :o, :n, :g, 'active')", i=pid, o=vrt.ORG, n=nm, g=str(pid))
    for n, runs in enumerate((51, 20)):
        gid = uuid.uuid4()
        await ex("INSERT INTO games (id, grade_id, played_at, result, home_org_id, away_org_id, "
                 " match_format, status) VALUES (:i, :g, :d, 'WIN', :o, :x, 'T20', 'COMPLETED')",
                 i=gid, g=W_GRADE, d=date(2025, 2, 2 + n), o=vrt.ORG, x=vrt.OPPONENT)
        for pid, scored in ((W_ONE, runs), (W_TWO, runs - 5)):
            await ex("INSERT INTO batting_innings (game_id, player_id, runs, balls, fours, sixes, "
                     " not_out, dismissal_type, did_not_bat, batting_position) "
                     "VALUES (:g, :p, :r, :b, 2, 0, false, 'caught', false, 3)",
                     g=gid, p=pid, r=scored, b=scored + 10)
            await ex("INSERT INTO bowling_spells (game_id, player_id, overs, maidens, runs, wickets) "
                     "VALUES (:g, :p, 4.0, 0, 20, 3)", g=gid, p=pid)
            await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=gid, p=pid)
    await ex("INSERT INTO player_season_stats (player_id, season_id, matches, batting_innings, runs, "
             " not_outs, wickets, source) VALUES (:p, :s, 2, 2, 71, 0, 6, 'api')", p=W_ONE, s=vrt.SEASON)
    await ex("INSERT INTO player_season_stats (player_id, season_id, matches, batting_innings, runs, "
             " not_outs, wickets, source) VALUES (:p, :s, 2, 2, 61, 0, 6, 'api')", p=W_TWO, s=vrt.SEASON)
    # The club's own default, as Shoalwater Bay's reads: senior only. Without it the
    # platform default already includes women's grades and the bug cannot show.
    await ex("UPDATE organisations SET stats_grade_categories = CAST('[\"senior\"]' AS jsonb) WHERE id = :o", o=vrt.ORG)
    await ex("UPDATE players SET gender = 'female' WHERE id = ANY(:ids)", ids=[W_ONE, W_TWO])
    await db.commit()


async def play(db, query_json: dict):
    """The slide's rows (player names) for one saved report, or an error string."""
    org = await db.get(Organisation, vrt.ORG)
    rid = uuid.uuid4()
    await db.execute(text("DELETE FROM club_room_slides WHERE organisation_id = :o"), {"o": vrt.ORG})
    await db.execute(text("DELETE FROM saved_reports WHERE org_id = :o"), {"o": vrt.ORG})
    await db.execute(text(
        "INSERT INTO saved_reports (id, org_id, slug, title, query_json, visibility, status) "
        "VALUES (:i, :o, :s, 'Report', CAST(:q AS jsonb), 'club', 'approved')"),
        {"i": rid, "o": vrt.ORG, "s": f"r-{rid.hex[:8]}", "q": json.dumps(query_json)})
    await db.execute(text(
        "INSERT INTO club_room_slides (id, organisation_id, slide_type, config, position, enabled) "
        "VALUES (gen_random_uuid(), :o, 'statlab_report', CAST(:c AS jsonb), 0, true)"),
        {"o": vrt.ORG, "c": json.dumps({"report_id": str(rid)})})
    await db.commit()
    try:
        payload = await cr.build_play_payload(db, org)
    except Exception as exc:  # noqa: BLE001 - the control must report, not crash
        await db.rollback()
        return None, f"{type(exc).__name__}: {exc}"
    slides = [s for s in payload.get("slides", []) if s.get("type") == "statlab_report"]
    rows = slides[0].get("rows", []) if slides else []
    return [str(r.get("player_name") or r.get("name") or "") for r in rows], None


def report(target: str, sort_by: str, **context) -> dict:
    return {"target": target, "sortBy": sort_by, "sortDir": "desc", "limit": 10, "filterTree": None,
            "context": context}


async def main() -> None:
    await vrt.build_schema()
    async with vrt.Session() as s:
        await vrt.seed(s)
        await seed_womens(s)

    async with vrt.Session() as db:
        women = ("Wilson", "Webb")
        men = ("Barker", "Baker")

        def only(names, want, other):
            names = names or []
            return any(any(w in n for w in want) for n in names) and not any(
                any(o in n for o in other) for n in names)

        print("== Women's runs")
        names, err = await play(db, report("player_career", "runs", categories="womens"))
        check("the playlist plays", err is None, str(err))
        check("a report set to Grade type Women's shows the women and not the men",
              only(names, women, men), str(names))

        print("== Women's wickets")
        names, err = await play(db, report("player_career", "wickets", categories="womens"))
        check("the wickets report shows the women and not the men", only(names, women, men), str(names))

        print("== the same report, other picks (so the men could have been shown)")
        names, err = await play(db, report("player_career", "runs"))
        check("no grade type: the club default (senior only) plays, the men and not the women",
              only(names, men, women), str(names))
        names, err = await play(db, report("player_career", "runs", categories="senior"))
        check("Grade type Senior shows the men", only(names, men, women), str(names))
        names, err = await play(db, report("player_career", "runs", categories="senior,womens"))
        check("Senior plus Women's shows both",
              any(w in n for n in names for w in women) and any(m in n for n in names for m in men), str(names))

        print("== a list value, and a saved row cannot forge the scope")
        names, err = await play(db, report("player_career", "runs", categories=["womens"]))
        check("a list-shaped pick is read the same way", only(names, women, men), str(names))
        names, err = await play(db, report("player_career", "runs", _scope="everything"))
        check("an underscore key in a saved context is ignored, not trusted",
              err is None and only(names, men, women), f"{names} {err}")

        print("== the Gender context filter still narrows the rows")
        names, err = await play(db, report("player_career", "runs", categories="senior,womens", gender="female"))
        check("Gender female shows the women and not the men", only(names, women, men), f"{names} {err}")

        print("== a derived report keeps its pick too")
        names, err = await play(db, {"derived": "highest_scores", "limit": 10,
                                     "context": {"categories": "womens"}})
        check("a derived report still plays", err is None, str(err))

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
