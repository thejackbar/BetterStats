"""Verification: a Club Room Leaderboard or Records slide can be narrowed to one grade type.

Asked for by Shoalwater Bay CC: batting, bowling and fielding legends for men's,
ladies' and juniors without building a StatLab report. The slide gets a Grade type
pick (`config.categories`: a grade category key, "all", or not set for the club default).

Runs the SHIPPED `club_room.build_play_payload` and `list_grade_types` on a real
Postgres over the records suite's schema and seed, plus a women's grade, a junior
grade and their players. Every "only the women" check is paired with one proving the
men COULD have been shown (a Men's pick shows them), and a pick that does not
exist must not widen anything.

Two behaviours worth knowing, both checked:
* A leaderboard slide with NO pick now counts the club default and leaves out a junior
  grade the club hides from the public, like every other public stats screen. It
  used to count every grade with no scope at all.
* The records cache is keyed on the pick, so a Women's records slide and a Men's one
  in the same playlist cannot serve each other's rows.

CONTROL MODE. Against the commit before the change the pick is ignored and the
checks fail without crashing (new names are read through presence-safe accessors).

Run:  DATABASE_URL=postgresql+asyncpg://root@/room_grade_type?host=/var/run/postgresql \
      python verification/verify_club_room_grade_type.py
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
from app.services import junior_hiding

PASS = FAIL = 0
W_GRADE = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
W_ONE = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000002")
W_TWO = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000003")
J_GRADE = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")
J_ONE = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")
WOMEN, MEN, JUNIOR = ("Wilson", "Webb"), ("Barker", "Baker"), ("Junior",)


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}{('  - ' + detail) if detail else ''}")


async def seed_extra(db) -> None:
    async def ex(sql, **kw):
        await db.execute(text(sql), kw)

    for gid, name, cat in ((W_GRADE, "Womens T20", "womens"), (J_GRADE, "Under 14s", "junior")):
        await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
                 "VALUES (:i, :s, :n, :g, :c, ARRAY[CAST(:c AS text)])", i=gid, s=vrt.SEASON, n=name, g=str(gid), c=cat)
    people = ((W_ONE, "Wilson, Wendy", W_GRADE, 51), (W_TWO, "Webb, Wanda", W_GRADE, 20), (J_ONE, "Junior, Jess", J_GRADE, 99))
    for pid, nm, grade, runs in people:
        await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) "
                 "VALUES (:i, :o, :n, :g, 'active')", i=pid, o=vrt.ORG, n=nm, g=str(pid))
        gid = uuid.uuid4()
        await ex("INSERT INTO games (id, grade_id, played_at, result, home_org_id, away_org_id, match_format, status) "
                 "VALUES (:i, :g, :d, 'WIN', :o, :x, 'T20', 'COMPLETED')",
                 i=gid, g=grade, d=date(2025, 2, 2), o=vrt.ORG, x=vrt.OPPONENT)
        await ex("INSERT INTO batting_innings (game_id, player_id, runs, balls, fours, sixes, not_out, dismissal_type, "
                 " did_not_bat, batting_position) VALUES (:g, :p, :r, :b, 2, 0, false, 'caught', false, 3)",
                 g=gid, p=pid, r=runs, b=runs + 10)
        await ex("INSERT INTO bowling_spells (game_id, player_id, overs, maidens, runs, wickets) "
                 "VALUES (:g, :p, 4.0, 0, 20, 3)", g=gid, p=pid)
        await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=gid, p=pid)
        await ex("INSERT INTO player_season_stats (player_id, season_id, matches, batting_innings, runs, not_outs, "
                 " wickets, source) VALUES (:p, :s, 1, 1, :r, 0, 3, 'api')", p=pid, s=vrt.SEASON, r=runs)
    # Cricket Australia lists the grades each player played in a season. The scoped
    # boards read it to keep a player with no scorecard in scope out of a category
    # they never played (a season total has no grade of its own). Without these
    # rows the seed is not a real club and a Women's board would count the men's totals.
    for pid, grade in ((vrt.PLAYER, vrt.GRADE), (vrt.MATE, vrt.GRADE), (W_ONE, W_GRADE), (W_TWO, W_GRADE), (J_ONE, J_GRADE)):
        await ex("INSERT INTO player_season_grade_stats (player_id, season_id, grade_id, matches, runs) "
                 "VALUES (:p, :s, :g, 1, 1)", p=pid, s=vrt.SEASON, g=grade)
    # A junior grade is hidden from the public only when it sits in a competition the
    # club tags as junior (services/junior_hiding). Lifespan DDL, so added here.
    await ex("ALTER TABLE club_competitions ADD COLUMN IF NOT EXISTS is_junior BOOLEAN")
    comp = uuid.uuid4()
    await ex("INSERT INTO club_competitions (id, organisation_id, name, is_junior) VALUES (:c, :o, 'Junior Cup', true)", c=comp, o=vrt.ORG)
    await ex("UPDATE grades SET competition_id = :c WHERE id = :g", c=comp, g=J_GRADE)
    # Senior only: the platform default also counts women's, which would hide the bug.
    await ex("UPDATE organisations SET stats_grade_categories = CAST('[\"senior\"]' AS jsonb) WHERE id = :o", o=vrt.ORG)
    await db.commit()


async def play(db, entries):
    org = await db.get(Organisation, vrt.ORG)
    await db.execute(text("DELETE FROM club_room_slides WHERE organisation_id = :o"), {"o": vrt.ORG})
    for i, (stype, cfg) in enumerate(entries):
        await db.execute(text(
            "INSERT INTO club_room_slides (id, organisation_id, slide_type, config, position, enabled) "
            "VALUES (gen_random_uuid(), :o, :t, CAST(:c AS jsonb), :p, true)"),
            {"o": vrt.ORG, "t": stype, "c": json.dumps(cfg), "p": i})
    await db.commit()
    try:
        return (await cr.build_play_payload(db, org)).get("slides", []), None
    except Exception as exc:  # noqa: BLE001 - the control must report, not crash
        await db.rollback()
        return [], f"{type(exc).__name__}: {exc}"


def names(slide):
    return [str(r.get("name") or "") for r in ((slide or {}).get("rows") or [])]


def only(got, want, other):
    return any(any(w in n for w in want) for n in got) and not any(any(o in n for o in other) for n in got)


async def lb(db, cfg):
    slides, err = await play(db, [("leaderboard", {"stat_group": "batting", "sort_by": "total_runs", "limit": 20, **cfg})])
    return ([s for s in slides if s.get("type") == "leaderboard"] or [None])[0], err


async def main() -> None:
    await vrt.build_schema()
    async with vrt.Session() as s:
        await vrt.seed(s)
        await seed_extra(s)

    async with vrt.Session() as db:
        print("== leaderboard")
        slide, err = await lb(db, {"categories": "womens"})
        check("a Women's leaderboard plays", err is None and slide is not None, str(err))
        check("it shows the women, not the men or the juniors", only(names(slide), WOMEN, MEN + JUNIOR), str(names(slide)))
        check("and says so on the slide", (slide or {}).get("grade_type_label") == "Women's", str((slide or {}).get("grade_type_label")))
        slide, _ = await lb(db, {"categories": "senior"})
        check("Men's shows the men, not the women (so the women could have been shown)", only(names(slide), MEN, WOMEN + JUNIOR), str(names(slide)))
        check("labelled Men's", (slide or {}).get("grade_type_label") == "Men's")
        slide, _ = await lb(db, {"categories": "junior"})
        check("Juniors shows the junior, not the adults", only(names(slide), JUNIOR, MEN + WOMEN), str(names(slide)))
        slide, _ = await lb(db, {})
        check("no pick counts the club default (senior only here): the men", only(names(slide), MEN, WOMEN + JUNIOR), str(names(slide)))
        check("and carries no grade label, so an untouched slide looks as before", (slide or {}).get("grade_type_label") in (None, ""), str((slide or {}).get("grade_type_label")))
        slide, _ = await lb(db, {"categories": "all"})
        got = names(slide)
        check("All grades shows men, women and juniors", all(any(w in n for n in got) for w in ("Barker", "Wilson", "Junior")), str(got))
        check("labelled All grades", (slide or {}).get("grade_type_label") == "All grades")
        slide, _ = await lb(db, {"categories": "martians"})
        check("a pick that does not exist is read as not set, never as everything",
              only(names(slide), MEN, WOMEN + JUNIOR), str(names(slide)))

        print("== bowling and fielding take the pick too")
        slides, err = await play(db, [("leaderboard", {"stat_group": "bowling", "sort_by": "total_wickets", "categories": "womens"}),
                                      ("leaderboard", {"stat_group": "fielding", "sort_by": "total_catches_non_wk", "categories": "womens"})])
        bowl = [x for x in slides if x.get("stat_group") == "bowling"]
        check("a Women's bowling leaderboard shows the women only", err is None and bool(bowl) and only(names(bowl[0]), WOMEN, MEN + JUNIOR), f"{err} {[names(b) for b in bowl]}")
        # fielding: no catches seeded for the women, so an absent slide is right; the control for
        # "it ran" is that the whole playlist still played.
        check("the playlist with a fielding slide still plays", err is None, str(err))

        print("== a club that hides its juniors from the public")
        await db.execute(text("UPDATE organisations SET hide_juniors = true WHERE id = :o"), {"o": vrt.ORG})
        await db.commit()
        junior_hiding.forget(str(vrt.ORG))
        slide, _ = await lb(db, {"categories": "all"})
        got = names(slide)
        check("All grades leaves the hidden junior grade off the TV",
              not any("Junior" in n for n in got) and any("Barker" in n for n in got), str(got))
        await db.execute(text("UPDATE organisations SET hide_juniors = false WHERE id = :o"), {"o": vrt.ORG})
        await db.commit()
        junior_hiding.forget(str(vrt.ORG))
        slide, _ = await lb(db, {"categories": "all"})
        check("with the switch off the same pick shows the junior (so the check above could fail)",
              any("Junior" in n for n in names(slide)), str(names(slide)))

        print("== records")
        slides, err = await play(db, [
            ("records", {"category": "batting.top_career_runs", "categories": "womens"}),
            ("records", {"category": "batting.top_career_runs", "categories": "senior"}),
            ("records", {"category": "batting.top_career_runs"})])
        recs = [x for x in slides if x.get("type") == "records"]
        check("three records slides play", err is None and len(recs) == 3, f"{err} {len(recs)}")
        if len(recs) == 3:
            check("Women's records show the women only", only(names(recs[0]), WOMEN, MEN + JUNIOR), str(names(recs[0])))
            check("Men's records right beside it show the men only (the cache did not serve the women's rows)",
                  only(names(recs[1]), MEN, WOMEN + JUNIOR), str(names(recs[1])))
            check("with no pick, the club default (men)", only(names(recs[2]), MEN, WOMEN + JUNIOR), str(names(recs[2])))
            check("the Women's slide is labelled", recs[0].get("grade_type_label") == "Women's" and not recs[2].get("grade_type_label"),
                  f"{recs[0].get('grade_type_label')} / {recs[2].get('grade_type_label')}")

        print("== the editor's picker and a row's description")
        org = await db.get(Organisation, vrt.ORG)
        listing = getattr(cr, "list_grade_types", None)
        got = None
        if listing:
            try:
                got = await listing(current_user=None, club=org, db=db)
            except Exception as exc:  # noqa: BLE001
                got = {"error": str(exc)}
        keys = [a["key"] for a in (got or {}).get("available", [])]
        check("the picker offers the grade types the club has (senior, junior, womens), and not masters",
              keys == ["senior", "junior", "womens"], str(got))
        check("and says which the default counts", (got or {}).get("default") == ["senior"], str(got))

        class _E:
            def __init__(self, t, c): self.slide_type, self.config = t, c
        describe = getattr(cr, "_entry_summary", lambda e: None)
        check("a row says its grade type", describe(_E("leaderboard", {"stat_group": "bowling", "categories": "womens"})) == "Leaderboard · bowling · Women's"
              and describe(_E("records", {"category": "bowling.most_five_fors", "categories": "all"})) == "Club Records · Most Five Fors · All grades",
              f"{describe(_E('leaderboard', {'stat_group': 'bowling', 'categories': 'womens'}))}")
        check("and a row with no pick reads as it always did", describe(_E("leaderboard", {"stat_group": "bowling"})) == "Leaderboard · bowling")

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
