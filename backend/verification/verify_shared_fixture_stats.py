"""A fixture between two synced clubs belongs to BOTH of them.

Reported by Shoalwater Bay Cricket Club: a player's Players-list figure read
106 matches, his own profile read 150, and asking the profile for JUNIOR
cricket came back with 28 senior Peel Cricket Association matches — the very
matches the senior filter also returned.

One cause, two opposite symptoms. A CA match between two clubs that both sync
is ONE `games` row, and its `grade_id` — and so its `season_id` — points at
whichever club synced it first. Neither club owns it:

  * every board that scoped by `seasons.organisation_id` DROPPED the other
    club's own matches, and
  * `grade_scope` could not classify a grade row it did not own, and its
    category filter is an EXCLUSION, so an unclassifiable grade was KEPT by
    every category at once.

Runs the SHIPPED functions and route bodies — never a re-implementation — over
the views pulled straight out of the migrations that define them.

Run:  DATABASE_URL=postgresql+asyncpg://postgres:pg@localhost/bsverify \
      python verification/verify_shared_fixture_stats.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.models.db import Base
from app.services import aggregations as agg
from app.services import competition_stats, grade_scope
from app.services.competition_ddl import STATEMENTS as COMP_DDL
from app.routers.records import get_records

DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

PASS = FAIL = 0
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        FAILURES.append(label)
        print(f"  FAIL {label}{('  — ' + detail) if detail else ''}")


# ── ids ──────────────────────────────────────────────────────────────────────
OURS = uuid.uuid4()      # Shoalwater Bay
THEIRS = uuid.uuid4()    # the other Peel club, which synced first
US_PLAYER = uuid.uuid4()
THEIR_PLAYER = uuid.uuid4()

ASSOC = "peel-assoc-guid"
ASSOC_JNR = "peel-junior-assoc-guid"

S_OURS = uuid.uuid4(); S_THEIRS = uuid.uuid4()
# Their row for the same real season under a name and with no year of its own —
# only the CA season GUID both clubs' rows carry can match it.
S_THEIRS_GUID = uuid.uuid4()
CA_SEASON = "ca-season-2025-26"
C_PEEL = uuid.uuid4()          # our own competition, seeded from the association
C_PEEL_JNR = uuid.uuid4()      # and the juniors', a second association

G_OURS_F = uuid.uuid4()        # our "F Grade"
G_THEIRS_F = uuid.uuid4()      # their "F Grade" — where our shared fixtures sit
G_THEIRS_ALIAS = uuid.uuid4()  # their older spelling, which we merged away
G_OURS_U14 = uuid.uuid4()      # our juniors: what makes the club default ACTIVE
G_THEIRS_U14 = uuid.uuid4()    # THEIR juniors — must still be excluded
G_OURS_E = uuid.uuid4()        # a grade of ours nobody has grouped yet
G_THEIRS_E = uuid.uuid4()      # and their row for it


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY,
                merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL,
                canonical_name TEXT NOT NULL,
                alias_name TEXT NOT NULL,
                undone_at TIMESTAMPTZ)
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS season_aliases (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL,
                canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                alias_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                undone_at TIMESTAMPTZ)
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS import_effective_deltas (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id uuid, player_id uuid, season_id uuid,
                scope text, matches int, batting_innings int, runs int,
                not_outs int, balls_faced int, fifties int, hundreds int,
                ducks int, high_score int, is_hs_not_out boolean,
                fours int, sixes int, batting_minutes int,
                bowling_innings int, wickets int, overs numeric,
                bowling_balls int, runs_conceded int, maidens int,
                best_bowling_wickets int, best_bowling_figures text,
                five_wicket_innings int, wides int, no_balls int,
                catches int, catches_wk int, catches_non_wk int,
                run_outs int, assisted_run_outs int, unassisted_run_outs int,
                stumpings int)
        """))
        for stmt in COMP_DDL:
            await conn.execute(text(stmt))
        json_cols = (await conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type = 'json'"))).all()
        for tbl, col in json_cols:
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb '
                f'USING "{col}"::text::jsonb'))
        stmts = view_statements()
        for _ in range(2):
            for name, sql in stmts:
                await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
                await conn.execute(text(sql.replace("OR REPLACE ", "")))


async def seed(session) -> None:
    async def ex(sql, **kw):
        await session.execute(text(sql), kw)

    for oid, nm in ((OURS, "Shoalwater Bay CC"), (THEIRS, "Warnbro Swans CC")):
        await ex("INSERT INTO organisations (id, name, is_active) "
                 "VALUES (:i, :n, true)", i=oid, n=nm)
    for sid, org in ((S_OURS, OURS), (S_THEIRS, THEIRS)):
        await ex("INSERT INTO seasons (id, organisation_id, name, year,"
                 " grassroots_id) VALUES (:i, :o, 'Summer 2025/26', 2025, :g)",
                 i=sid, o=org, g=CA_SEASON)
    await ex("INSERT INTO seasons (id, organisation_id, name, year,"
             " grassroots_id) VALUES (:i, :o, 'Peel Summer', NULL, :g)",
             i=S_THEIRS_GUID, o=THEIRS, g=CA_SEASON)

    for cid, nm, assoc in ((C_PEEL, "Peel Cricket Association Inc.", ASSOC),
                           (C_PEEL_JNR, "Peel Junior Cricket Association", ASSOC_JNR)):
        await ex("INSERT INTO club_competitions (id, organisation_id, name,"
                 " association_id, association_name, is_seeded)"
                 " VALUES (:i, :o, :n, :a, :n, true)",
                 i=cid, o=OURS, n=nm, a=assoc)

    grades = [
        # id, season, name, category, competition, association
        (G_OURS_F,       S_OURS,   "F Grade",           "senior", C_PEEL, ASSOC),
        (G_OURS_E,       S_OURS,   "E Grade",           "senior", None,   ASSOC),
        (G_OURS_U14,     S_OURS,   "Under 14s",         "junior", C_PEEL_JNR, ASSOC_JNR),
        (G_THEIRS_F,     S_THEIRS, "F Grade",            None,    None,   ASSOC),
        (G_THEIRS_ALIAS, S_THEIRS, "F Grade Colts Cup",  None,    None,   ASSOC),
        (G_THEIRS_E,     S_THEIRS_GUID, "E Grade",       None,    None,   ASSOC),
        (G_THEIRS_U14,   S_THEIRS, "Under 14s",          None,    None,   ASSOC_JNR),
    ]
    for gid, sid, nm, cat, comp, assoc in grades:
        await ex(
            "INSERT INTO grades (id, season_id, name, category, categories,"
            " competition_id, association_id)"
            " VALUES (:i, :s, :n, :c, :cs, :comp, :a)",
            i=gid, s=sid, n=nm, c=cat, cs=[cat] if cat else None,
            comp=comp, a=assoc)

    # The club merged CA's older spelling into the name it kept.
    # The club merged CA's older spelling into the name it kept. That spelling
    # would read as JUNIOR on its own ("Colts Cup"), which is what makes this a
    # real test of the fold rather than of the name suggestion.
    await ex("INSERT INTO grade_merge_logs (org_id, canonical_name, alias_name)"
             " VALUES (:o, 'F Grade', 'F Grade Colts Cup')", o=OURS)

    await ex("INSERT INTO players (id, organisation_id, name) "
             "VALUES (:i, :o, 'Hind, Darren')", i=US_PLAYER, o=OURS)
    await ex("INSERT INTO players (id, organisation_id, name) "
             "VALUES (:i, :o, 'Swan, Sam')", i=THEIR_PLAYER, o=THEIRS)

    async def game(grade, *, home_org=None, away_org=None, fmt="One Day",
                   day=1, players=()):
        gid = uuid.uuid4()
        await ex(
            "INSERT INTO games (id, grade_id, played_at, venue, result,"
            " match_format, home_org_id, away_org_id, status)"
            " VALUES (:i, :g, :d, 'Shoalwater Oval', 'WIN', :f, :h, :a,"
            " 'COMPLETED')",
            i=gid, g=grade, d=date(2026, 1, day), f=fmt, h=home_org, a=away_org)
        for pid, runs in players:
            await ex("INSERT INTO game_appearances (game_id, player_id)"
                     " VALUES (:g, :p)", g=gid, p=pid)
            await ex(
                "INSERT INTO batting_innings (game_id, player_id, runs, balls,"
                " not_out, fours, sixes, innings_number, batting_position)"
                " VALUES (:g, :p, :r, 40, false, 2, 0, 1, 3)",
                g=gid, p=pid, r=runs)
            await ex(
                "INSERT INTO bowling_spells (game_id, player_id, overs, runs,"
                " wickets, maidens, innings_number)"
                " VALUES (:g, :p, 4.0, 20, 1, 0, 2)", g=gid, p=pid)
            await ex(
                "INSERT INTO fielding_stats (game_id, player_id, catches,"
                " catches_wk, run_outs, stumpings)"
                " VALUES (:g, :p, 1, 0, 0, 0)", g=gid, p=pid)
        return gid

    # Three ordinary matches in our OWN F Grade.
    for d in (1, 2, 3):
        await game(G_OURS_F, home_org=OURS, away_org=THEIRS, day=d,
                   players=[(US_PLAYER, 30)])
    # A SHARED fixture: their grade row, our club one of the two sides, and
    # BOTH clubs' players scoring on the one row.
    await game(G_THEIRS_F, home_org=THEIRS, away_org=OURS, day=4,
               players=[(US_PLAYER, 40), (THEIR_PLAYER, 55)])
    # A second one, in the grade whose older name we merged away.
    await game(G_THEIRS_ALIAS, home_org=THEIRS, away_org=OURS, day=5,
               players=[(US_PLAYER, 40)])
    # A junior match of ours, and one in THEIR junior grade that we also played.
    await game(G_OURS_U14, home_org=OURS, away_org=THEIRS, day=6,
               players=[(US_PLAYER, 12)])
    await game(G_THEIRS_U14, home_org=THEIRS, away_org=OURS, day=7,
               players=[(US_PLAYER, 9)])
    # A shared fixture in a grade NEITHER club has grouped into a competition.
    await game(G_THEIRS_E, home_org=THEIRS, away_org=OURS, day=10,
               players=[(US_PLAYER, 5)])
    # A match in their grade that we were NOT in: never ours, on any reading.
    await game(G_THEIRS_F, day=8, players=[(THEIR_PLAYER, 77)])
    # A T20 in their grade that we played, for the format axis.
    await game(G_THEIRS_F, home_org=THEIRS, away_org=OURS, fmt="T20", day=9,
               players=[(US_PLAYER, 20)])
    # CA's own season aggregate for the club, which is what every UNFILTERED
    # board reads. It counts the shared fixtures too — CA has no notion of one
    # club owning a match — so it is the yardstick the filtered figures are
    # checked against.
    await ex(
        "INSERT INTO player_season_stats (player_id, season_id, matches,"
        " batting_innings, runs, not_outs, balls_faced, fifties, hundreds,"
        " ducks, fours, sixes, wickets)"
        " VALUES (:p, :s, 9, 9, 216, 0, 360, 0, 0, 0, 18, 0, 9)",
        p=US_PLAYER, s=S_OURS)
    await session.commit()


def _row(rows, name):
    return next((r for r in rows if r.get("name") == name), {}) or {}


async def main() -> None:
    await build_schema()
    async with Session() as session:
        await seed(session)

        print("\n— the reported case: a senior fixture read as junior —")
        scope_j, _ = await grade_scope.resolve_scope_for_player(
            session, OURS, str(US_PLAYER), "junior")
        bat_j = await agg.get_career_batting(session, str(US_PLAYER), scope=scope_j)
        check("asking for JUNIORS returns only the two real junior matches",
              bat_j["innings"] == 2, f"innings {bat_j['innings']}")
        check("and none of the shared senior fixtures' runs (12 + 9 = 21)",
              bat_j["total_runs"] == 21, f"runs {bat_j['total_runs']}")

        by_grade_j = await agg.get_batting_by_grade(
            session, str(US_PLAYER), str(OURS), scope=scope_j)
        senior_named = [r for r in by_grade_j if "F Grade" in (r["grade_name"] or "")]
        check("no senior grade appears under the Juniors filter",
              not senior_named, str([r["grade_name"] for r in by_grade_j]))

        print("\n— a shared fixture counts for the club that did not sync it —")
        scope_d, _ = await grade_scope.resolve_scope_for_player(
            session, OURS, str(US_PLAYER), None)
        bat_d = await agg.get_career_batting(session, str(US_PLAYER), scope=scope_d)
        check("the club default counts all seven senior matches",
              bat_d["innings"] == 7, f"innings {bat_d['innings']}")
        check("junior + senior = every match the player has (7 + 2)",
              bat_d["innings"] + bat_j["innings"] == 9,
              f"{bat_d['innings']} + {bat_j['innings']}")

        board = await agg.get_batting_leaderboard_extended(
            session, str(OURS), scope=await grade_scope.resolve_scope(session, OURS))
        me = _row(board, "Hind, Darren")
        check("the Players list reads the same 7, not 3",
              me.get("innings") == 7, f"innings {me.get('innings')}")
        check("the Players list and the profile agree on runs",
              me.get("total_runs") == bat_d["total_runs"],
              f"{me.get('total_runs')} vs {bat_d['total_runs']}")

        bowl = await agg.get_bowling_leaderboard_extended(
            session, str(OURS), scope=await grade_scope.resolve_scope(session, OURS))
        check("the bowling board counts the shared fixtures too",
              _row(bowl, "Hind, Darren").get("games") == 7,
              str(_row(bowl, "Hind, Darren").get("games")))
        field = await agg.get_fielding_leaderboard(
            session, str(OURS), scope=await grade_scope.resolve_scope(session, OURS))
        check("the fielding board counts the shared fixtures too",
              _row(field, "Hind, Darren").get("games") == 7,
              str(_row(field, "Hind, Darren").get("games")))

        print("\n— and for the club that DID sync it, unchanged —")
        their_scope = await grade_scope.resolve_scope(session, THEIRS)
        their_board = await agg.get_batting_leaderboard_extended(
            session, str(THEIRS), scope=their_scope)
        them = _row(their_board, "Swan, Sam")
        check("their own player still has both of their matches",
              them.get("innings") == 2, f"innings {them.get('innings')}")
        check("including the fixture they share with us, counted for them too",
              them.get("total_runs") == 55 + 77,
              str(them.get("total_runs")))
        check("our player never appears on their board",
              not _row(their_board, "Hind, Darren"))
        check("their match we were not in is not ours",
              not any(r.get("name") == "Swan, Sam" for r in board))

        print("\n— the season filter reaches the other club's season row —")
        bat_s = await agg.get_career_batting(
            session, str(US_PLAYER), season_id=str(S_OURS), scope=scope_d)
        check("picking our own 2025/26 still counts the shared fixtures",
              bat_s["innings"] == 7, f"innings {bat_s['innings']}")
        board_s = await agg.get_batting_leaderboard_extended(
            session, str(OURS), season_id=str(S_OURS),
            scope=await grade_scope.resolve_scope(session, OURS))
        innings_s = await agg.get_player_batting_innings(
            session, str(US_PLAYER), season_id=str(S_OURS), scope=scope_d)
        check("including one on a season row with no year, matched on the CA"
              " season id both clubs' rows carry",
              any((i.get("grade_name") or "") == "E Grade" for i in innings_s),
              str([i.get("grade_name") for i in innings_s]))
        check("so does the season-filtered Players list",
              _row(board_s, "Hind, Darren").get("innings") == 7,
              str(_row(board_s, "Hind, Darren").get("innings")))

        print("\n— a foreign grade is judged, not waved through —")
        scope_all = await grade_scope.resolve_scope(session, OURS, "all")
        check("'all categories' is still an inactive scope",
              not scope_all.category_active)
        excluded = set(str(x) for x in scope_d.excluded_ids)
        check("their junior grade is excluded by our default",
              str(G_THEIRS_U14) in excluded)
        check("their senior grade is not",
              str(G_THEIRS_F) not in excluded)
        check("their older spelling reads as our merged grade's category,"
              " not as the juniors its own name suggests",
              str(G_THEIRS_ALIAS) not in excluded)
        check("and the Juniors filter does not claim it either",
              str(G_THEIRS_ALIAS) in set(str(x) for x in scope_j.excluded_ids))

        print("\n— the match type axis, on a grade we do not own —")
        scope_t20, _ = await grade_scope.resolve_scope_for_player(
            session, OURS, str(US_PLAYER), None, formats="t20")
        bat_t = await agg.get_career_batting(session, str(US_PLAYER), scope=scope_t20)
        check("T20 finds the one T20 played in their grade",
              bat_t["innings"] == 1, f"innings {bat_t['innings']}")
        scope_1d, _ = await grade_scope.resolve_scope_for_player(
            session, OURS, str(US_PLAYER), None, formats="one_day")
        bat_1 = await agg.get_career_batting(session, str(US_PLAYER), scope=scope_1d)
        check("and one-day the other six",
              bat_1["innings"] == 6, f"innings {bat_1['innings']}")

        print("\n— the competition a shared fixture was played in —")
        comp = await competition_stats.player_competition_breakdown(
            session, str(US_PLAYER), OURS)
        peel = next((r for r in comp["rows"]
                     if r["competition_name"] == "Peel Cricket Association Inc."), {})
        other = next((r for r in comp["rows"]
                      if r["competition_name"] == "Other grades"), None)
        jnr = next((r for r in comp["rows"]
                    if r["competition_name"] == "Peel Junior Cricket Association"), {})
        check("the six grouped senior matches are filed under our Peel competition",
              peel.get("matches") == 6, str(peel.get("matches")))
        check("both junior matches are filed under our junior competition",
              jnr.get("matches") == 2, str(jnr.get("matches")))
        check("the ungrouped grade stays ungrouped rather than being guessed",
              (other or {}).get("matches") == 1, str(other and other.get("matches")))

        scope_comp = await grade_scope.resolve_scope(
            session, OURS, competitions=str(C_PEEL))
        bat_c = await agg.get_career_batting(
            session, str(US_PLAYER), scope=scope_comp)
        check("filtering to that competition keeps the shared fixtures",
              bat_c["innings"] == 6, f"innings {bat_c['innings']}")

        club = await competition_stats.club_competition_breakdown(session, OURS)
        cpeel = next((r for r in club["rows"]
                      if r["competition_name"] == "Peel Cricket Association Inc."), {})
        check("the club's own competition record counts them as well",
              cpeel.get("matches") == 6, str(cpeel.get("matches")))

        print("\n— the competitions page reads the club's own grades —")
        grades = await competition_stats.competition_grade_breakdown(session, OURS)
        peel_grades = [r for r in grades
                       if r["competition_name"] == "Peel Cricket Association Inc."]
        names = sorted(r["grade_name"] for r in peel_grades)
        check("the merged-away spelling is not drawn as a grade of its own",
              names == ["F Grade"], str(names))
        check("and that one row holds every match played in it",
              peel_grades and peel_grades[0]["matches"] == 6,
              str(peel_grades and peel_grades[0]["matches"]))
        check("its season count is the real season, not one row per club",
              peel_grades and peel_grades[0]["seasons"] == 1,
              str(peel_grades and peel_grades[0]["seasons"]))
        check("the competition header counts one season and one grade",
              cpeel.get("seasons") == 1 and cpeel.get("grades") == 1,
              f"seasons {cpeel.get('seasons')} grades {cpeel.get('grades')}")
        check("and the player's own row says the same",
              peel.get("seasons") == 1 and peel.get("grades") == 1,
              f"seasons {peel.get('seasons')} grades {peel.get('grades')}")

        print("\n— the club's records —")
        recs = await get_records(
            str(OURS), season_id=None, grade_id=None, grade_name=None,
            finals_only=False, captain_only=False, gender=None,
            categories=None, formats=None, db=session, viewer=None)
        mm = _row((recs.get("team") or {}).get("most_matches") or [], "Hind, Darren")
        check("most matches counts the shared fixtures (7 senior)",
              mm.get("matches") == 7, str(mm.get("matches")))
        recs_all = await get_records(
            str(OURS), season_id=None, grade_id=None, grade_name=None,
            finals_only=False, captain_only=False, gender=None,
            categories="all", formats=None, db=session, viewer=None)
        mm_all = _row((recs_all.get("team") or {}).get("most_matches") or [],
                      "Hind, Darren")
        check("and every category counts all nine, from CA's own totals",
              mm_all.get("matches") == 9, str(mm_all.get("matches")))
        check("the filtered senior runs plus the junior ones equal CA's total",
              bat_d["total_runs"] + bat_j["total_runs"] == 216,
              f"{bat_d['total_runs']} + {bat_j['total_runs']}")

    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  FAILED:", f)
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
