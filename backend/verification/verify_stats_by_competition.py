"""Verification for stats by competition, against a real Postgres.

Asked for after two real PlayHQ screenshots:

  * **Applecross** plays Summer 2025/26 across THREE associations at once —
    WASTCA, the Perth Scorchers Women's League and the WA Integrated Cricket
    League — with a dozen grades under the first of them.
  * **Hamilton Veterans** field ONE side in several competitions of the SAME
    association (Veterans Cricket Victoria) in one season: the Border Cup and
    the VCV Over 60s competition, plus the Echuca divisions.

Neither could be separated. The stats layer scoped to a season, a grade, a
grade CATEGORY and a match FORMAT, and to nothing about who ran the
competition.

What was checked against the live Grassroots API before any of this was built,
and what it settled:

  * ``grade.owningOrganisation`` — the ASSOCIATION — is on every grade in
    ``/fixturesladders/organisations/{org}/teams?seasonId=``, which is the
    payload sync already fetches and was discarding. Present back to Summer
    1975/76, so a club's whole history is reachable for one call per season.
  * The COMPETITION is in none of it — not the seasons list, the teams list,
    the grade record, the grade's match list or the full match record — and
    every plausible competition endpoint on the proxy answers 403. So a
    competition here is the club's own named group of grades, seeded from the
    association.

Runs the SHIPPED services and route bodies — never a re-implementation — over
the ``v_effective_*`` views pulled straight out of the migrations that define
them.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5433 \
  python verification/verify_stats_by_competition.py
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
from app.models.db import Base, Organisation
from app.services import grade_scope
from app.routers.games import list_games
from app.routers.leaderboard import batting_leaderboard
from app.routers.organisations import get_org_grade_categories
from app.routers.players import get_player_stats

# Everything this change adds is imported behind a guard, so a CONTROL RUN
# against the previous commit reports each missing piece as a failed check
# rather than dying on an ImportError before a single one runs. Same posture
# `verify_audience_clubs` takes for the JavaScript half it compares against.
MISSING: list[str] = []
try:
    from app.services import competitions as comp_svc
    from app.services.competition_ddl import DOWNGRADE, STATEMENTS
    from app.routers.admin import (
        CompetitionAssign, CompetitionCreate, CompetitionRename,
        CompetitionReorder, assign_grade_to_competition,
        create_club_competition, delete_club_competition,
        list_club_competitions, rename_club_competition,
        reorder_club_competitions, seed_club_competitions,
    )
    from app.routers.organisations import get_org_competitions
    from app.routers.players import get_player_competitions
    HAVE_COMPETITIONS = True
except ImportError as exc:  # pragma: no cover - control run only
    HAVE_COMPETITIONS = False
    MISSING.append(str(exc))
    comp_svc = None
    DOWNGRADE = STATEMENTS = []

# The in-app grouping job is its own guard, so a control run against the
# commit that shipped the filter but not the button still runs every check
# above and reports only this half as missing.
try:
    from app.services import competition_grouping as grouping
    from app.routers.admin import (
        competition_grouping_state, start_competition_grouping,
    )
    HAVE_GROUPING = True
except ImportError as exc:  # pragma: no cover - control run only
    HAVE_GROUPING = False
    MISSING.append(str(exc))
    grouping = None

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
        print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")


# -- the two reported clubs --------------------------------------------------
ACC = uuid.uuid4()        # Applecross - three associations in one season
HVCC = uuid.uuid4()       # Hamilton Veterans - three competitions, one association
OTHER = uuid.uuid4()      # a third club, to prove nothing leaks between them
# The opposition every fixture is played against. Deliberately NOT `OTHER`: a
# club recorded as one of the two sides IS a participant by the app's own
# `home_org_id`/`away_org_id` rule, so using the control club as the opponent
# would have made every fixture genuinely its own and the cross-club check
# would have been measuring the harness.
OPPONENT = uuid.uuid4()

A_WASTCA = "wastca00-0000-0000-0000-000000000001"
A_PSWL = "pswl0000-0000-0000-0000-000000000002"
A_ICL = "icl00000-0000-0000-0000-000000000003"
A_VCV = "17bceba5-87d8-eb11-a7ad-2818780da0cc"

S_ACC = uuid.uuid4()      # Applecross Summer 2025/26
S_ACC_OLD = uuid.uuid4()  # Applecross Summer 2024/25
S_HVCC = uuid.uuid4()     # Hamilton Summer 2024/25
S_OTHER = uuid.uuid4()

G_1ST = uuid.uuid4()          # WASTCA "1st Grade"
G_OD2 = uuid.uuid4()          # WASTCA "One Day Grade 2"  - the 7th XI plays...
G_OD3 = uuid.uuid4()          # WASTCA "One Day Grade 3"  - ...both in one season
G_PSWL = uuid.uuid4()         # PSWL "PSWL South A"
G_ICL = uuid.uuid4()          # WA ICL "Belt Up WA ICL A Grade"
G_1ST_OLD = uuid.uuid4()      # the same grade, previous season
G_UNGROUPED = uuid.uuid4()    # a grade CA never gave us an association for

G_BORDER = uuid.uuid4()       # Hamilton "Border Cup"
G_O60 = uuid.uuid4()          # Hamilton "Over 60 Mixed"
G_ECHUCA = uuid.uuid4()       # Hamilton "Echuca Division 3 Goulburn"

G_OTHER = uuid.uuid4()

PLAYER = uuid.uuid4()         # our Applecross all-rounder
HAMMER = uuid.uuid4()         # the Hamilton Over 60 Man in two competitions
IMPORTED = uuid.uuid4()       # a BetterImport career with no grade at all
STRANGER = uuid.uuid4()       # the control club's own player


async def build_schema() -> None:
    """The pre-283 schema, exactly as a live database would hold it."""
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)
        # Roll the schema BACK to pre-283 so the migration has real work to do
        # against a populated table, which is the state production is in.
        for stmt in DOWNGRADE:
            await conn.execute(text(stmt))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL, canonical_name TEXT NOT NULL,
                alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)
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
            CREATE TABLE IF NOT EXISTS org_merge_logs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                source_org_id UUID, source_org_name TEXT NOT NULL,
                target_org_id UUID NOT NULL,
                performed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
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
        # Copied from the lifespan's own DDL, column for column. A harness
        # table that merely looks right is worse than none: `audit_log`
        # swallows its own failure, so a wrong column name leaves the caller's
        # transaction ABORTED and the write it was auditing silently lost.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id SERIAL PRIMARY KEY,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL,
                user_id UUID,
                action TEXT NOT NULL,
                target_type TEXT,
                target_id TEXT,
                details JSONB DEFAULT '{}'
            )
        """))
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


async def seed_pre_283(session) -> None:
    async def ex(sql, **kw):
        await session.execute(text(sql), kw)

    for oid, name, slug in (
        (ACC, "Applecross Cricket Club", "applecross"),
        (HVCC, "Hamilton Veterans Cricket Club", "hamilton-veterans"),
        (OTHER, "Somebody Else CC", "other"),
    ):
        await ex("INSERT INTO organisations (id, name, slug, is_active) "
                 "VALUES (:i, :n, :s, true)", i=oid, n=name, s=slug)

    for sid, org, nm, yr in (
        (S_ACC, ACC, "Summer 2025/26", 2025),
        (S_ACC_OLD, ACC, "Summer 2024/25", 2024),
        (S_HVCC, HVCC, "Summer 2024/25", 2024),
        (S_OTHER, OTHER, "Summer 2025/26", 2025),
    ):
        await ex("INSERT INTO seasons (id, organisation_id, name, year) "
                 "VALUES (:i, :o, :n, :y)", i=sid, o=org, n=nm, y=yr)

    grades = [
        (G_1ST, S_ACC, "1st Grade", "senior"),
        (G_OD2, S_ACC, "One Day Grade 2", "senior"),
        (G_OD3, S_ACC, "One Day Grade 3", "senior"),
        (G_PSWL, S_ACC, "PSWL South A", "womens"),
        (G_ICL, S_ACC, "Belt Up WA ICL A Grade", "mixed"),
        (G_1ST_OLD, S_ACC_OLD, "1st Grade", "senior"),
        (G_UNGROUPED, S_ACC_OLD, "Old Colts Cup", "senior"),
        (G_BORDER, S_HVCC, "Border Cup", "masters"),
        (G_O60, S_HVCC, "Over 60 Mixed", "masters"),
        (G_ECHUCA, S_HVCC, "Echuca Division 3 Goulburn", "masters"),
        (G_OTHER, S_OTHER, "1st Grade", "senior"),
    ]
    for gid, sid, nm, cat in grades:
        await ex(
            "INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
            "VALUES (:i, :s, :n, :g, :c, ARRAY[:c])",
            i=gid, s=sid, n=nm, g=str(gid), c=cat)

    for pid, org, nm in (
        (PLAYER, ACC, "Barendse, Jack"),
        (HAMMER, HVCC, "Kain, Graham"),
        (IMPORTED, ACC, "Ancient, Arthur"),
        (STRANGER, OTHER, "Nobody, Ivan"),
    ):
        await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) "
                 "VALUES (:i, :o, :n, :g, 'active')", i=pid, o=org, n=nm, g=str(pid))


# How many games each grade gets, and how they went. The counts are what every
# assertion below is written against, so they are declared once here.
GAMES = {
    G_1ST: [("WIN", 60), ("WIN", 40), ("LOSS", 10)],       # 3 games, 110 runs
    G_OD2: [("WIN", 25), ("LOSS", 5)],                     # 2 games,  30 runs
    G_OD3: [("LOSS", 15)],                                 # 1 game,   15 runs
    G_PSWL: [("WIN", 70)],                                 # 1 game,   70 runs
    G_ICL: [("DRAW", 20), ("WIN", 30)],                    # 2 games,  50 runs
    G_1ST_OLD: [("WIN", 12)],                              # 1 game,   12 runs
    G_UNGROUPED: [("LOSS", 8)],                            # 1 game,    8 runs
}
HAMILTON_GAMES = {
    G_BORDER: [("WIN", 45), ("WIN", 33)],                  # 2 games,  78 runs
    G_O60: [("LOSS", 11)],                                 # 1 game,   11 runs
    G_ECHUCA: [("WIN", 22)],                               # 1 game,   22 runs
}
OTHER_GAMES = {
    G_OTHER: [("WIN", 5)],                                 # 1 game, the control
}


async def seed_games(session) -> None:
    async def ex(sql, **kw):
        await session.execute(text(sql), kw)

    day = 1
    for owner, table, player in ((ACC, GAMES, PLAYER),
                                 (HVCC, HAMILTON_GAMES, HAMMER),
                                 (OTHER, OTHER_GAMES, STRANGER)):
        for grade_id, plays in table.items():
            for result, runs in plays:
                gid = uuid.uuid4()
                # `games` has no organisation_id of its own — the effective
                # view derives it through the grade's season. home_org_id is
                # what makes the game read as ours on a shared fixture.
                await ex(
                    "INSERT INTO games (id, grade_id, played_at, result, "
                    " home_org_id, away_org_id, match_format, status) "
                    "VALUES (:i, :g, :d, :r, :o, :x, 'One Day', 'COMPLETED')",
                    i=gid, g=grade_id, d=date(2025, 1, 1 + (day % 27)), r=result,
                    o=owner, x=OPPONENT)
                day += 1
                await ex(
                    "INSERT INTO batting_innings (game_id, player_id, runs, balls, "
                    " fours, sixes, not_out, dismissal_type, did_not_bat) "
                    "VALUES (:g, :p, :r, :b, 2, 1, false, 'caught', false)",
                    g=gid, p=player, r=runs, b=runs + 10)
                await ex(
                    "INSERT INTO bowling_spells (game_id, player_id, overs, maidens, "
                    " runs, wickets) VALUES (:g, :p, 5.0, 1, 20, 2)",
                    g=gid, p=player)
                await ex(
                    "INSERT INTO fielding_stats (game_id, player_id, catches, "
                    " catches_wk, stumpings, run_outs) VALUES (:g, :p, 1, 0, 0, 0)",
                    g=gid, p=player)
                await ex(
                    "INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)",
                    g=gid, p=player)

    # Cricket Australia's own season aggregates, which is what an UNFILTERED
    # leaderboard reads — the per-innings rows above are only reached once a
    # scope is active. Seeded to match the games above so the two agree.
    for sid, player, matches, runs in (
        (S_ACC, PLAYER, 9, 275),      # 110 + 30 + 15 + 70 + 50
        (S_ACC_OLD, PLAYER, 2, 20),   # 12 + 8
        (S_HVCC, HAMMER, 4, 111),     # 78 + 11 + 22
    ):
        await ex(
            "INSERT INTO player_season_stats (player_id, season_id, matches, "
            " batting_innings, runs, not_outs, wickets, source) "
            "VALUES (:p, :s, :m, :m, :r, 0, 0, 'api')",
            p=player, s=sid, m=matches, r=runs)

    # A grade-less manual game: the career residual case. It belongs to no
    # competition and must drop out of every competition figure while still
    # counting towards the unfiltered career.
    manual = uuid.uuid4()
    await ex(
        "INSERT INTO manual_games (id, organisation_id, season_id, played_at, result, "
        " home_team, away_team) "
        "VALUES (:i, :o, :s, :d, 'WIN', 'Us', 'Them')",
        i=manual, o=ACC, s=S_ACC, d=date(2025, 3, 1))
    await ex(
        "INSERT INTO manual_batting_innings (manual_game_id, player_id, runs, "
        " not_out, did_not_bat) VALUES (:g, :p, 99, false, false)",
        g=manual, p=IMPORTED)
    # No `game_appearances` row: that table FKs to `games`, and a manual game
    # is not one. The appearance union picks it up through the effective
    # batting-innings view instead, which is how the app itself sees it.


async def main() -> None:
    if not HAVE_COMPETITIONS:
        # A control run. Every check below depends on the feature existing, so
        # report that once rather than 80 identical import errors.
        check("stats by competition is built at all", False, "; ".join(MISSING))
        print(f"\n{PASS} passed, {FAIL} failed")
        for f in FAILURES:
            print("  FAILED:", f)
        await engine.dispose()
        sys.exit(1)
    await build_schema()

    print("\n-- one copy of the DDL, run by both alembic and the lifespan --")
    root = Path(__file__).resolve().parent.parent
    mig = (root / "alembic" / "versions" / "283_stats_by_competition.py").read_text()
    main_py = (root / "app" / "main.py").read_text()
    check("alembic's 283 imports the shared list rather than retyping it",
          "from app.services.competition_ddl import" in mig
          and "STATEMENTS" in mig and "CREATE TABLE" not in mig)
    check("and the lifespan mirror runs that same list",
          "from app.services.competition_ddl import STATEMENTS" in main_py)
    check("the downgrade drops the table the upgrade created",
          "club_competitions" in " ".join(DOWNGRADE))

    print("\n-- migration 283, against a populated pre-283 schema --")
    async with Session() as session:
        await seed_pre_283(session)
        await session.commit()
    async with engine.begin() as conn:
        cols = (await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'grades' AND column_name = 'competition_id'"))).all()
        check("pre-283: grades has no competition_id", not cols)
        # Applied three times, the way the lifespan re-runs it on every boot.
        for _ in range(3):
            for stmt in STATEMENTS:
                await conn.execute(text(stmt))
        cols = {r[0] for r in (await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'grades'"))).all()}
        for col in ("association_id", "association_name",
                    "association_short_name", "competition_id"):
            check(f"283 added grades.{col}", col in cols)
        n = (await conn.execute(text("SELECT COUNT(*) FROM club_competitions"))).scalar()
        check("applied three times, club_competitions is not duplicated", n == 0, str(n))
        grades = (await conn.execute(text("SELECT COUNT(*) FROM grades"))).scalar()
        check("every grade survived the migration", grades == 11, str(grades))
        fk = (await conn.execute(text(
            "SELECT confdeltype::text FROM pg_constraint "
            "WHERE conname = 'grades_competition_id_fkey'"))).scalar()
        check("deleting a competition SETs NULL rather than deleting a grade",
              fk == "n", str(fk))

    async with Session() as session:
        await seed_games(session)
        await session.commit()

    print("\n-- the association, as CA reports it (sync writes this now) --")
    async with Session() as session:
        for gid, assoc, name, short in (
            (G_1ST, A_WASTCA, "West Australian Suburban Turf Cricket Assoc.", "WASTCA"),
            (G_OD2, A_WASTCA, "West Australian Suburban Turf Cricket Assoc.", "WASTCA"),
            (G_OD3, A_WASTCA, "West Australian Suburban Turf Cricket Assoc.", "WASTCA"),
            (G_1ST_OLD, A_WASTCA, "West Australian Suburban Turf Cricket Assoc.", "WASTCA"),
            (G_PSWL, A_PSWL, "Perth Scorchers Women's League", "PSWL"),
            (G_ICL, A_ICL, "WA Integrated Cricket League", "ICL"),
            (G_BORDER, A_VCV, "Veterans Cricket Victoria", "VCV"),
            (G_O60, A_VCV, "Veterans Cricket Victoria", "VCV"),
            (G_ECHUCA, A_VCV, "Veterans Cricket Victoria", "VCV"),
            (G_OTHER, A_WASTCA, "West Australian Suburban Turf Cricket Assoc.", "WASTCA"),
        ):
            await session.execute(text(
                "UPDATE grades SET association_id = :a, association_name = :n, "
                "association_short_name = :s WHERE id = :i"),
                {"a": assoc, "n": name, "s": short, "i": gid})
        await session.commit()

        assocs = await comp_svc.org_associations(session, ACC)
        names = [a["name"] for a in assocs]
        check("Applecross reads as three associations in one club",
              len(assocs) == 3, str(names))
        check("WASTCA is its biggest, by grade count",
              assocs[0]["name"].startswith("West Australian"), str(names))
        check("an association we were never told is not invented",
              all(a["association_id"] for a in assocs))
        hv = await comp_svc.org_associations(session, HVCC)
        check("Hamilton reads as ONE association -- which is why the "
              "association alone cannot answer the report",
              len(hv) == 1 and hv[0]["short_name"] == "VCV", str(hv))

    print("\n-- what SYNC itself writes, through the shipped _resolve_org_grade --")
    async with Session() as session:
        from app.services.sync import _resolve_org_grade
        payload = {
            "id": "17bceba5-87d8-eb11-a7ad-2818780da0cc",
            "name": "Veterans Cricket Victoria",
            "shortName": "VCV",
        }
        # A brand-new grade, exactly as the teams payload delivers it.
        fresh_guid = str(uuid.uuid4())
        gid = await _resolve_org_grade(
            session, HVCC, {}, fresh_guid, "Over 70 Mixed", S_HVCC,
            association=payload)
        await session.commit()
        row = (await session.execute(text(
            "SELECT association_id, association_name, association_short_name "
            "FROM grades WHERE id = :i"), {"i": gid})).first()
        check("a newly synced grade is created carrying its association",
              row == (payload["id"], payload["name"], payload["shortName"]), str(row))

        # An EXISTING grade, which is what a plain Sync Now hits — without this
        # a club's current seasons would need a Full Rebuild to fill in.
        await session.execute(text(
            "UPDATE grades SET association_id = NULL, association_name = NULL, "
            "association_short_name = NULL WHERE id = :i"), {"i": G_ECHUCA})
        await session.commit()
        again = await _resolve_org_grade(
            session, HVCC, {str(G_ECHUCA): G_ECHUCA}, str(G_ECHUCA),
            "Echuca Division 3 Goulburn", S_HVCC, association=payload)
        await session.commit()
        row = (await session.execute(text(
            "SELECT association_id FROM grades WHERE id = :i"), {"i": G_ECHUCA})).first()
        check("and an existing grade is filled in on a plain Sync Now",
              again == G_ECHUCA and row[0] == payload["id"], str(row))

        # CA occasionally omits the owning organisation. A blank must never
        # erase an association we already hold.
        await _resolve_org_grade(
            session, HVCC, {str(G_ECHUCA): G_ECHUCA}, str(G_ECHUCA),
            "Echuca Division 3 Goulburn", S_HVCC,
            association={"id": "", "name": "", "shortName": ""})
        await session.commit()
        row = (await session.execute(text(
            "SELECT association_id FROM grades WHERE id = :i"), {"i": G_ECHUCA})).first()
        check("an association CA omits does not erase the one we hold",
              row[0] == payload["id"], str(row))

        # And a sync that reports none at all is a plain no-op.
        before = (await session.execute(text(
            "SELECT association_id FROM grades WHERE id = :i"), {"i": G_ECHUCA})).scalar()
        await _resolve_org_grade(
            session, HVCC, {str(G_ECHUCA): G_ECHUCA}, str(G_ECHUCA),
            "Echuca Division 3 Goulburn", S_HVCC, association=None)
        await session.commit()
        after = (await session.execute(text(
            "SELECT association_id FROM grades WHERE id = :i"), {"i": G_ECHUCA})).scalar()
        check("a sync carrying no association at all changes nothing",
              before == after == payload["id"], f"{before} -> {after}")

        # Tidy up: the extra grade would otherwise change every count below.
        await session.execute(text("DELETE FROM grades WHERE id = :i"), {"i": gid})
        await session.commit()

    print("\n-- seeding: one competition per association, skip never replace --")
    async with Session() as session:
        first = await comp_svc.seed_competitions_for_org(session, ACC)
        await session.commit()
        check("Applecross seeds three competitions",
              first["competitions_created"] == 3, str(first))
        check("and groups its six associated grades",
              first["grades_assigned"] == 6, str(first))

        again = await comp_svc.seed_competitions_for_org(session, ACC)
        await session.commit()
        check("re-seeding creates nothing and moves nothing",
              again == {"competitions_created": 0, "grades_assigned": 0}, str(again))

        rows = await comp_svc.list_competitions(session, ACC)
        by_name = {r["name"]: r for r in rows}
        check("the competitions are named for their associations",
              set(by_name) == {
                  "West Australian Suburban Turf Cricket Assoc.",
                  "Perth Scorchers Women's League",
                  "WA Integrated Cricket League"}, str(list(by_name)))
        wastca = by_name["West Australian Suburban Turf Cricket Assoc."]
        check("WASTCA holds four grade rows across two seasons",
              wastca["grade_count"] == 4 and wastca["season_count"] == 2,
              str(wastca))
        check("a seeded competition is marked as seeded", wastca["is_seeded"])

        grades = {g["name"]: g for g in await comp_svc.competition_grades(session, ACC)}
        check("the grade CA gave no association for is left un-grouped",
              grades["Old Colts Cup"]["competition_id"] is None,
              str(grades["Old Colts Cup"]))

        hv_seed = await comp_svc.seed_competitions_for_org(session, HVCC)
        await session.commit()
        check("Hamilton seeds ONE competition from its one association",
              hv_seed["competitions_created"] == 1, str(hv_seed))
        hv_rows = await comp_svc.list_competitions(session, HVCC)
        check("and all three of its grades land in it",
              hv_rows[0]["grade_count"] == 3, str(hv_rows))

    print("\n-- the reported case: splitting one association into its competitions --")
    async with Session() as session:
        hv_rows = await comp_svc.list_competitions(session, HVCC)
        vcv = hv_rows[0]["id"]
        await comp_svc.rename_competition(session, HVCC, vcv, "Echuca Divisions")
        border = await comp_svc.create_competition(session, HVCC, "Border Cup", A_VCV)
        over60 = await comp_svc.create_competition(
            session, HVCC, "VCV Over 60s Competition", A_VCV)
        await comp_svc.assign_grade(session, HVCC, "Border Cup", border["id"])
        await comp_svc.assign_grade(session, HVCC, "Over 60 Mixed", over60["id"])
        await session.commit()

        rows = {r["name"]: r for r in await comp_svc.list_competitions(session, HVCC)}
        check("Hamilton now reads as three competitions",
              set(rows) == {"Echuca Divisions", "Border Cup",
                            "VCV Over 60s Competition"}, str(list(rows)))
        check("each holding its own grade",
              all(rows[n]["grade_count"] == 1 for n in rows),
              str({n: rows[n]["grade_count"] for n in rows}))
        check("a renamed competition stops being marked as seeded",
              rows["Echuca Divisions"]["is_seeded"] is False)

        after = await comp_svc.seed_competitions_for_org(session, HVCC)
        await session.commit()
        rows2 = {r["name"] for r in await comp_svc.list_competitions(session, HVCC)}
        check("a later sync leaves the club's own naming alone",
              rows2 == set(rows) and after["competitions_created"] == 0,
              f"{rows2} {after}")

    print("\n-- the club's record, per competition --")
    async with Session() as session:
        club = await get_org_competitions(str(ACC), None, session)
        rows = {r["competition_name"]: r for r in club["rows"]}
        check("Applecross reports a row per competition, plus the un-grouped one",
              set(rows) == {
                  "West Australian Suburban Turf Cricket Assoc.",
                  "Perth Scorchers Women's League",
                  "WA Integrated Cricket League",
                  comp_svc.UNGROUPED_LABEL}, str(list(rows)))
        wastca = rows["West Australian Suburban Turf Cricket Assoc."]
        check("WASTCA counts 7 matches (3 + 2 + 1 + 1)",
              wastca["matches"] == 7, str(wastca["matches"]))
        check("with the right W/L/D (4/3/0 -> 57.1%) — the draw is the ICL's",
              (wastca["won"], wastca["lost"], wastca["drawn"]) == (4, 3, 0)
              and wastca["win_pct"] == 57.1, str(wastca))
        check("and its runs (110 + 30 + 15 + 12)",
              wastca["runs"] == 167, str(wastca["runs"]))
        check("the PSWL row is the women's grade alone",
              rows["Perth Scorchers Women's League"]["matches"] == 1
              and rows["Perth Scorchers Women's League"]["runs"] == 70,
              str(rows["Perth Scorchers Women's League"]))
        check("a grade in no competition is SHOWN, not dropped",
              rows[comp_svc.UNGROUPED_LABEL]["matches"] == 1,
              str(rows[comp_svc.UNGROUPED_LABEL]))
        check("the competitions add up to the club's own game count",
              club["total_matches"] == 11, str(club["total_matches"]))
        check("a match count is not multiplied by its innings rows",
              all(r["matches"] <= 7 for r in club["rows"]),
              str([(r["competition_name"], r["matches"]) for r in club["rows"]]))

        grades = club["grades"]
        wastca_grades = {g["grade_name"] for g in grades
                         if g["competition_name"].startswith("West Australian")}
        check("the TEAM half lists each grade under its competition",
              wastca_grades == {"1st Grade", "One Day Grade 2", "One Day Grade 3"},
              str(wastca_grades))
        od2 = next(g for g in grades if g["grade_name"] == "One Day Grade 2")
        od3 = next(g for g in grades if g["grade_name"] == "One Day Grade 3")
        check("a side playing two grades in one season is two separate rows",
              od2["matches"] == 2 and od3["matches"] == 1,
              f"{od2['matches']} / {od3['matches']}")

        hv = await get_org_competitions(str(HVCC), None, session)
        hv_rows = {r["competition_name"]: r for r in hv["rows"]}
        check("Hamilton's Border Cup is its own row of 2 matches",
              hv_rows.get("Border Cup", {}).get("matches") == 2, str(list(hv_rows)))
        check("and the Over 60s competition its own row of 1",
              hv_rows.get("VCV Over 60s Competition", {}).get("matches") == 1,
              str(list(hv_rows)))
        check("which is the reported case: one association, told apart",
              len(hv_rows) == 3, str(list(hv_rows)))

    print("\n-- a player's own record, per competition --")
    async with Session() as session:
        me = await get_player_competitions(str(PLAYER), None, session)
        rows = {r["competition_name"]: r for r in me["rows"]}
        wastca = rows["West Australian Suburban Turf Cricket Assoc."]
        check("the player's WASTCA row counts 7 matches",
              wastca["matches"] == 7, str(wastca["matches"]))
        check("batting: 167 runs off 7 innings, high score 60",
              wastca["batting"]["runs"] == 167
              and wastca["batting"]["innings"] == 7
              and wastca["batting"]["high_score"] == 60, str(wastca["batting"]))
        check("the average is recomputed from THIS competition's own counts",
              wastca["batting"]["average"] == round(167 / 7, 2),
              str(wastca["batting"]["average"]))
        check("bowling: 14 wickets, and overs converted to balls before dividing",
              wastca["bowling"]["wickets"] == 14
              and wastca["bowling"]["balls"] == 7 * 30
              and wastca["bowling"]["economy"] == 4.0, str(wastca["bowling"]))
        check("fielding: 7 catches, and the keeper split reported",
              wastca["fielding"]["catches"] == 7
              and wastca["fielding"]["catches_non_wk"] == 7,
              str(wastca["fielding"]))
        check("the ICL row is its own two matches, not folded into WASTCA",
              rows["WA Integrated Cricket League"]["matches"] == 2,
              str(rows["WA Integrated Cricket League"]))

        hammer = await get_player_competitions(str(HAMMER), None, session)
        hrows = {r["competition_name"]: r["matches"] for r in hammer["rows"]}
        check("the Hamilton player's two competitions read separately",
              hrows.get("Border Cup") == 2
              and hrows.get("VCV Over 60s Competition") == 1, str(hrows))

        ghost = await get_player_competitions(str(IMPORTED), None, session)
        check("an import residual is reported as unattributed, never invented "
              "into a competition",
              ghost["unattributed"] == 1 and not ghost["rows"], str(ghost))

    print("\n-- the filter: one competition, everywhere --")
    async with Session() as session:
        comps = {r["name"]: r["id"]
                 for r in await comp_svc.list_competitions(session, ACC)}
        wastca_id = comps["West Australian Suburban Turf Cricket Assoc."]
        pswl_id = comps["Perth Scorchers Women's League"]

        scope = await grade_scope.resolve_scope(
            session, str(ACC), "all", competitions=wastca_id)
        check("a competition filter is active", scope.competition_active)
        check("and reports the name it resolved, for a page to label with",
              scope.competition_names[0].startswith("West Australian"),
              str(scope.competition_names))
        check("it survives formats_only(), the picked-grade path",
              scope.formats_only().competition_active)

        board = await batting_leaderboard(
            str(ACC), season_id=None, grade_id=None, grade_name=None,
            sort_by="total_runs", limit=20, min_runs=0, finals_only=None,
            captain_only=None, gender=None, overseas=None, categories="all",
            formats=None, competitions=wastca_id, db=session, viewer=None)
        runs = {r["name"]: int(r["total_runs"]) for r in board}
        check("the batting leaderboard scoped to WASTCA reads 167",
              runs.get("Barendse, Jack") == 167, str(runs))

        board_all = await batting_leaderboard(
            str(ACC), season_id=None, grade_id=None, grade_name=None,
            sort_by="total_runs", limit=20, min_runs=0, finals_only=None,
            captain_only=None, gender=None, overseas=None, categories="all",
            formats=None, competitions=None, db=session, viewer=None)
        runs_all = {r["name"]: int(r["total_runs"]) for r in board_all}
        check("unfiltered it reads the whole 295, so the filter really narrows",
              runs_all.get("Barendse, Jack") == 295, str(runs_all))

        board_pswl = await batting_leaderboard(
            str(ACC), season_id=None, grade_id=None, grade_name=None,
            sort_by="total_runs", limit=20, min_runs=0, finals_only=None,
            captain_only=None, gender=None, overseas=None, categories="all",
            formats=None, competitions=pswl_id, db=session, viewer=None)
        check("the PSWL board is that competition's 70 alone",
              len(board_pswl) == 1 and int(board_pswl[0]["total_runs"]) == 70,
              str(board_pswl))

        both = await batting_leaderboard(
            str(ACC), season_id=None, grade_id=None, grade_name=None,
            sort_by="total_runs", limit=20, min_runs=0, finals_only=None,
            captain_only=None, gender=None, overseas=None, categories="all",
            formats=None, competitions=f"{wastca_id},{pswl_id}",
            db=session, viewer=None)
        check("two competitions at once add up (167 + 70)",
              int(both[0]["total_runs"]) == 237, str(both))

        games = await list_games(
            str(ACC), season_id=None, grade_id=None, limit=100,
            finals_only=None, categories="all", formats=None,
            competitions=wastca_id, db=session)
        rows = games["games"] if isinstance(games, dict) else games
        check("the games list narrows to that competition's 7 fixtures",
              len(rows) == 7, str(len(rows)))

        profile = await get_player_stats(
            str(PLAYER), season_id=None, grade_id=None, last_n_games=None,
            start_date=None, end_date=None, categories="all", formats=None,
            competitions=wastca_id, db=session)
        check("the player profile's career totals narrow too",
              int(profile["career_batting"]["total_runs"]) == 167,
              str(profile["career_batting"].get("total_runs")))
        check("and the profile offers the club's competitions to filter by",
              len(profile["grade_scope"]["available_competitions"]) == 3,
              str(profile["grade_scope"]["available_competitions"]))

    print("\n-- an import residual never inflates a competition figure --")
    async with Session() as session:
        # A BetterImport career: a season aggregate with no per-game rows and no
        # grade behind it. It must count in the UNFILTERED career and in no
        # competition — the alternative is a figure invented rather than
        # filtered, and per-competition rows that do not add up.
        await session.execute(text(
            "INSERT INTO player_season_stats (player_id, season_id, matches, "
            " batting_innings, runs, not_outs, wickets, source) "
            "VALUES (:p, :s, 40, 38, 900, 4, 0, 'import')"),
            {"p": IMPORTED, "s": S_ACC})
        await session.commit()

        comps = {r["name"]: r["id"]
                 for r in await comp_svc.list_competitions(session, ACC)}
        wastca_id = comps["West Australian Suburban Turf Cricket Assoc."]

        unfiltered = await batting_leaderboard(
            str(ACC), season_id=None, grade_id=None, grade_name=None,
            sort_by="total_runs", limit=20, min_runs=0, finals_only=None,
            captain_only=None, gender=None, overseas=None, categories="all",
            formats=None, competitions=None, db=session, viewer=None)
        names = {r["name"]: int(r["total_runs"]) for r in unfiltered}
        # 900 from the import aggregate plus the 99 of the grade-less manual
        # game — two different residual branches of the effective view, not one
        # figure counted twice.
        check("the import career counts in the unfiltered leaderboard",
              names.get("Ancient, Arthur") == 999, str(names))

        scoped = await batting_leaderboard(
            str(ACC), season_id=None, grade_id=None, grade_name=None,
            sort_by="total_runs", limit=20, min_runs=0, finals_only=None,
            captain_only=None, gender=None, overseas=None, categories="all",
            formats=None, competitions=wastca_id, db=session, viewer=None)
        scoped_names = {r["name"]: int(r["total_runs"]) for r in scoped}
        check("and in NO competition, because it has no grade to place it by",
              "Ancient, Arthur" not in scoped_names, str(scoped_names))
        check("while the real career is unaffected by it",
              scoped_names.get("Barendse, Jack") == 167, str(scoped_names))

    print("\n-- failing closed, and cross-club --")
    async with Session() as session:
        await comp_svc.seed_competitions_for_org(session, OTHER)
        await session.commit()
        other = (await comp_svc.list_competitions(session, OTHER))[0]["id"]

        junk = await grade_scope.resolve_scope(
            session, str(ACC), "all", competitions=str(uuid.uuid4()))
        check("an unknown competition id matches NOTHING, never everything",
              junk.competition_active and junk.competitions == (),
              str(junk.competitions))
        board = await batting_leaderboard(
            str(ACC), season_id=None, grade_id=None, grade_name=None,
            sort_by="total_runs", limit=20, min_runs=0, finals_only=None,
            captain_only=None, gender=None, overseas=None, categories="all",
            formats=None, competitions=str(uuid.uuid4()), db=session, viewer=None)
        check("so a bad id empties the board rather than widening it",
              not board, str(board))

        foreign = await grade_scope.resolve_scope(
            session, str(ACC), "all", competitions=other)
        check("another club's competition id is dropped before it reaches SQL",
              foreign.competitions == (), str(foreign.competitions))

        nonsense = await grade_scope.resolve_scope(
            session, str(ACC), "all", competitions="not-a-uuid")
        check("junk that is not even a uuid is refused the same way",
              nonsense.competitions == (), str(nonsense.competitions))

        none_asked = await grade_scope.resolve_scope(session, str(ACC), "all")
        check("no competition asked for emits no competition clause",
              not none_asked.competition_active
              and not none_asked.competition_clause())
        every = await grade_scope.resolve_scope(
            session, str(ACC), "all", competitions="all")
        check("'all' means no filter, matching the category axis",
              not every.competition_active)

        acc_club = await get_org_competitions(str(OTHER), None, session)
        check("another club's breakdown holds only its own game, not our 15",
              acc_club["total_matches"] == 1, str(acc_club["total_matches"]))

    print("\n-- the state a club is in BEFORE any of this runs --")
    async with Session() as session:
        # Exactly what every existing club's database holds today: grades with
        # no association and no competition. This is the reported bug, replayed
        # — one undifferentiated lump where the club plays three competitions.
        await session.execute(text(
            "UPDATE grades gr SET competition_id = NULL, association_id = NULL "
            "FROM seasons s WHERE s.id = gr.season_id AND s.organisation_id = :o"),
            {"o": HVCC})
        await session.commit()
        before = await get_org_competitions(str(HVCC), None, session)
        rows = {r["competition_name"]: r["matches"] for r in before["rows"]}
        check("ungrouped, Hamilton's three competitions read as ONE row — "
              "which is the reported bug",
              list(rows) == [comp_svc.UNGROUPED_LABEL] and rows[comp_svc.UNGROUPED_LABEL] == 4,
              str(rows))
        check("and the club is offered no competition filter at all",
              await grade_scope.org_available_competitions(session, HVCC) == [])
        check("nothing is LOST by being ungrouped — the games still all count",
              before["total_matches"] == 4, str(before["total_matches"]))

    print("\n-- the admin screen's own route bodies --")
    async with Session() as session:
        club = await session.get(Organisation, ACC)
        user = type("U", (), {"id": uuid.uuid4()})()

        payload = await list_club_competitions(session, user, club)
        check("the manage screen gets competitions, grades and associations in one call",
              {"competitions", "grades", "associations"} <= set(payload),
              str(list(payload)))

        made = await create_club_competition(
            CompetitionCreate(name="  Colts  Cup  "), session, user, club)
        check("a name is trimmed and its whitespace collapsed",
              made["name"] == "Colts Cup", str(made))

        try:
            await create_club_competition(
                CompetitionCreate(name="colts cup"), session, user, club)
            check("a duplicate name is refused, case-folded", False)
        except Exception as e:
            check("a duplicate name is refused, case-folded",
                  getattr(e, "status_code", None) == 422, str(e))

        moved = await assign_grade_to_competition(
            CompetitionAssign(grade_name="Old Colts Cup",
                              competition_id=made["id"]), session, user, club)
        check("assigning a grade moves all of its season rows",
              moved["season_rows"] == 1, str(moved))

        try:
            await assign_grade_to_competition(
                CompetitionAssign(grade_name="1st Grade",
                                  competition_id=other), session, user, club)
            check("a grade cannot be put in another club's competition", False)
        except Exception as e:
            check("a grade cannot be put in another club's competition",
                  getattr(e, "status_code", None) == 422, str(e))

        await assign_grade_to_competition(
            CompetitionAssign(grade_name="Old Colts Cup", competition_id=None),
            session, user, club)
        grades = {g["name"]: g for g in await comp_svc.competition_grades(session, ACC)}
        check("and can be un-grouped again",
              grades["Old Colts Cup"]["competition_id"] is None)

        ids = [c["id"] for c in await comp_svc.list_competitions(session, ACC)]
        await reorder_club_competitions(
            CompetitionReorder(competition_ids=[ids[-1], str(uuid.uuid4()), ids[0]]),
            session, user, club)
        ordered = await comp_svc.list_competitions(session, ACC)
        check("reordering skips a foreign id without leaving a gap",
              ordered[0]["id"] == ids[-1] and ordered[0]["display_order"] == 0
              and ordered[1]["id"] == ids[0] and ordered[1]["display_order"] == 1,
              str([(o["display_order"], o["name"]) for o in ordered]))

        before = (await session.execute(text(
            "SELECT COUNT(*) FROM grades gr JOIN seasons s ON s.id = gr.season_id "
            "WHERE s.organisation_id = :o"), {"o": ACC})).scalar()
        await delete_club_competition(made["id"], session, user, club)
        after = (await session.execute(text(
            "SELECT COUNT(*) FROM grades gr JOIN seasons s ON s.id = gr.season_id "
            "WHERE s.organisation_id = :o"), {"o": ACC})).scalar()
        check("deleting a competition never deletes a grade",
              before == after == 7, f"{before} -> {after}")

        try:
            await rename_club_competition(
                other, CompetitionRename(name="Nice Try"), session, user, club)
            check("another club's competition cannot be renamed", False)
        except Exception as e:
            check("another club's competition cannot be renamed",
                  getattr(e, "status_code", None) == 422, str(e))
        try:
            await delete_club_competition(other, session, user, club)
            check("nor deleted", False)
        except Exception as e:
            check("nor deleted", getattr(e, "status_code", None) == 422, str(e))

        seeded = await seed_club_competitions(session, user, club)
        check("the seed button is the same skip-don't-replace pass",
              seeded["competitions_created"] == 0, str(seeded))

        meta = await get_org_grade_categories(str(ACC), session)
        check("the public filter payload carries the club's competitions",
              len(meta["available_competitions"]) == 3,
              str(meta["available_competitions"]))
        empty = await get_org_grade_categories(str(uuid.uuid4()), session)
        check("a club with no competitions is offered no filter at all",
              empty["available_competitions"] == [], str(empty))

    # ------------------------------------------------------------------
    # The in-app grouping job.
    #
    # An incremental sync only scans the seasons that could still have been in
    # play, so an established club's older seasons carry grades with no
    # association at all — and a grade with no association cannot be put in a
    # competition. This is the club's own way to close that, and the command
    # line runs the same function, so both are checked here at once.
    # ------------------------------------------------------------------
    print("\n-- the in-app grouping job --")
    if not HAVE_GROUPING:
        check("the grouping job is built at all", False, "; ".join(MISSING))
    else:
        # A team carries its grade as `grade` and/or `grades`, so both shapes
        # are read. A grade CA reports with no owning organisation is skipped
        # rather than stored blank.
        found = grouping._associations_from_teams([
            {"grade": {"id": "g1", "owningOrganisation": {"id": A_WASTCA, "name": "WASTCA"}}},
            {"grades": [{"id": "g2", "owningOrganisation": {"id": A_PSWL, "name": "PSWL"}}]},
            {"grade": {"id": "g3"}},
            {"grade": None},
            {},
        ])
        check("a team's association is read from `grade` and from `grades`",
              found.get("g1", {}).get("id") == A_WASTCA
              and found.get("g2", {}).get("id") == A_PSWL, str(found))
        check("a grade CA gives no owning organisation for is skipped, not blanked",
              "g3" not in found, str(found))

        # The kind this job writes must never read as the full historical sync
        # the Setup Wizard waits on, and must not be resumed behind an admin's
        # back by the restart self-heal.
        root = Path(__file__).resolve().parent.parent
        ca_py = (root / "app" / "routers" / "club_admin.py").read_text()
        main_py = (root / "app" / "main.py").read_text()
        check("its sync_runs kind is not one the Setup Wizard reads as a full sync",
              f'"{grouping.RUN_KIND}"' not in ca_py.split("_FULL_SYNC_KINDS = ")[1].split(")")[0])
        check("and the restart self-heal never resumes it",
              grouping.RUN_KIND not in main_py)

        async with Session() as session:
            # Put the club back where a real one is: one grade Cricket
            # Australia has never told us the association for.
            await session.execute(text(
                "UPDATE grades SET association_id = NULL, association_name = NULL,"
                " competition_id = NULL WHERE id = :g"), {"g": G_UNGROUPED})
            await session.commit()

            gap = await grouping.grouping_gap(session, ACC)
            check("the gap names the season holding a grade with no association",
                  gap["seasons_missing"] >= 1, str(gap))
            check("so the club is offered the job",
                  gap["needs_grouping"] is True, str(gap))
            check("and the wider un-grouped grade count is reported for context",
                  gap["grades_ungrouped"] >= 1, str(gap))
            check("no run in flight reads as none",
                  await grouping.running_run_id(session, ACC) is None)

        # Cricket Australia, stubbed. The real call is one per season; what
        # matters here is what the walk does with what comes back.
        real_get_teams = grouping.playhq_client.get_teams
        guid = str(G_UNGROUPED)
        async with Session() as session:
            guid = (await session.execute(text(
                "SELECT COALESCE(grassroots_id, CAST(id AS TEXT)) FROM grades WHERE id = :g"
            ), {"g": G_UNGROUPED})).scalar()

        async def teams_ok(org_id, season_guid):
            return [{"grade": {"id": guid, "owningOrganisation": {
                "id": A_WASTCA, "name": "WA Suburban Turf Cricket Association",
                "shortName": "WASTCA"}}}]

        calls: list[tuple] = []

        async def progress(done, total, phase):
            calls.append((done, total, phase))

        grouping.playhq_client.get_teams = teams_ok
        try:
            # --no-group / group=False: fill the associations in and stop, for
            # an operator who does not want to touch a club's own naming.
            res = await grouping.run_grouping(ACC, progress=progress, group=False)
            check("the association is fetched and filled in",
                  res["grades_filled"] == 1, str(res))
            check("group=False leaves the club's competitions alone",
                  res["competitions_created"] == 0 and res["grades_assigned"] == 0,
                  str(res))
            check("the progress callback starts at 0 and ends at the total",
                  calls and calls[0][0] == 0 and calls[-1][0] == calls[-1][1],
                  str(calls))
            async with Session() as session:
                row = (await session.execute(text(
                    "SELECT association_id, association_short_name, competition_id"
                    " FROM grades WHERE id = :g"), {"g": G_UNGROUPED})).mappings().first()
                check("the association and its short name are both stored",
                      row["association_id"] == A_WASTCA
                      and row["association_short_name"] == "WASTCA", str(dict(row)))
                check("and the grade is still in no competition, as asked",
                      row["competition_id"] is None, str(dict(row)))

            # The button's own path: fill, then group what that unlocks.
            res = await grouping.run_grouping(ACC)
            check("grouping then puts the newly-filled grade in a competition",
                  res["grades_assigned"] >= 1, str(res))
            async with Session() as session:
                after = await grouping.grouping_gap(session, ACC)
                check("and the club is no longer offered the job",
                      after["needs_grouping"] is False, str(after))

            # Safe to run twice, which is what lets the button carry no warning.
            again = await grouping.run_grouping(ACC)
            check("a second run over a finished club writes nothing at all",
                  again["grades_filled"] == 0
                  and again["competitions_created"] == 0
                  and again["grades_assigned"] == 0, str(again))

            # An association CA omits must never erase one we already hold.
            async def teams_blank(org_id, season_guid):
                return [{"grade": {"id": guid, "owningOrganisation": {}}}]

            async with Session() as session:
                await session.execute(text(
                    "UPDATE grades SET association_id = NULL WHERE id = :g"),
                    {"g": G_UNGROUPED})
                await session.commit()
            grouping.playhq_client.get_teams = teams_blank
            res = await grouping.run_grouping(ACC)
            check("an association CA omits is skipped rather than stored blank",
                  res["grades_filled"] == 0, str(res))

            # One season's upstream hiccup is not the job.
            async def teams_fail(org_id, season_guid):
                raise RuntimeError("CA said no")

            grouping.playhq_client.get_teams = teams_fail
            res = await grouping.run_grouping(ACC)
            check("a season Cricket Australia will not answer for is counted, not raised",
                  res["seasons_failed"] == res["seasons_checked"] >= 1, str(res))

            # A dry run reads the same gap the screen does and writes nothing.
            grouping.playhq_client.get_teams = teams_ok
            res = await grouping.run_grouping(ACC, apply=False)
            check("a dry run reports the seasons and writes nothing",
                  res["seasons_checked"] >= 1 and res["grades_filled"] == 0, str(res))
            async with Session() as session:
                still = (await session.execute(text(
                    "SELECT association_id FROM grades WHERE id = :g"),
                    {"g": G_UNGROUPED})).scalar()
                check("so the grade is still exactly where the dry run found it",
                      still is None, str(still))

            # ---- the two route bodies -------------------------------------
            async with Session() as session:
                club = await session.get(Organisation, ACC)
                # A real row: sync_runs.triggered_by_user_id is a foreign key,
                # so a stand-in object with an invented id cannot start a run.
                admin_id = uuid.uuid4()
                await session.execute(text(
                    "INSERT INTO users (id, username, failed_login_count)"
                    " VALUES (:i, :u, 0)"),
                    {"i": admin_id, "u": f"grouping-{admin_id.hex[:8]}"})
                await session.commit()
                user = type("U", (), {"id": admin_id})()
                state = await competition_grouping_state(session, user, club)
                check("the state endpoint carries the gap and the live run together",
                      "needs_grouping" in state and "running_run_id" in state,
                      str(state))
                check("and says there is work again, now the association is gone",
                      state["needs_grouping"] is True, str(state))

                from fastapi import BackgroundTasks
                bg = BackgroundTasks()
                started = await start_competition_grouping(bg, session, user, club)
                check("starting the job hands back a run id to poll",
                      started["status"] == "started" and started["run_id"],
                      str(started))
                check("and queues exactly one background task to do it",
                      len(bg.tasks) == 1, str(bg.tasks))

                second = await start_competition_grouping(BackgroundTasks(), session, user, club)
                check("a club with one in flight is handed THAT run, never a second",
                      second["status"] == "already_running"
                      and second["run_id"] == started["run_id"], str(second))

                live = await competition_grouping_state(session, user, club)
                check("so a screen reloading mid-run rejoins the same job",
                      live["running_run_id"] == started["run_id"], str(live))

                await session.execute(text(
                    "UPDATE sync_runs SET status = 'success' WHERE id = CAST(:r AS UUID)"),
                    {"r": started["run_id"]})
                await session.commit()
                check("and a finished run stops being offered as live",
                      await grouping.running_run_id(session, ACC) is None)

                other_club = await session.get(Organisation, OTHER)
                check("another club's run is never picked up as this club's",
                      await grouping.running_run_id(session, other_club.id) is None)

            # ---- it groups itself, without anybody pressing the button -----
            print("\n— an established club is grouped automatically —")
            new_season = uuid.uuid4()
            new_grade = uuid.uuid4()

            async def _auto(org):
                # Reported, never crashed: a control run against code without
                # the automatic path must say so and keep going.
                fn = getattr(grouping, "maybe_group_club", None)
                if fn is None:
                    return {"ran": None, "reason": "maybe_group_club is absent"}
                return await fn(org)

            async def reset(clear_runs=True):
                async with Session() as session:
                    if clear_runs:
                        await session.execute(text(
                            "DELETE FROM sync_runs WHERE org_id = :o AND kind = :k"),
                            {"o": ACC, "k": grouping.RUN_KIND})
                    await session.execute(text(
                        "UPDATE grades SET association_id = NULL,"
                        " association_name = NULL, competition_id = NULL"
                        " WHERE id = :g"), {"g": G_UNGROUPED})
                    await session.commit()

            # Cricket Australia has no association for this club's old seasons.
            # The job must still run once, and then STOP running.
            grouping.playhq_client.get_teams = teams_blank
            await reset()
            first = await _auto(ACC)
            check("a club whose seasons carry no association is grouped on sync,"
                  " with no button pressed",
                  first.get("ran") is True, str(first))
            check("and it records what Cricket Australia could not answer",
                  first.get("seasons_unresolved", 0) >= 1, str(first))

            second = await _auto(ACC)
            check("a second sync does not re-fetch what CA has no answer for",
                  second.get("ran") is False
                  and second.get("reason") == "no_new_seasons", str(second))

            async with Session() as session:
                await session.execute(text(
                    "INSERT INTO seasons (id, organisation_id, name, year)"
                    " VALUES (:i, :o, 'Summer 2099/00', 2099)"),
                    {"i": new_season, "o": ACC})
                await session.execute(text(
                    "INSERT INTO grades (id, season_id, name) "
                    "VALUES (:i, :s, 'Brand New Grade')"),
                    {"i": new_grade, "s": new_season})
                await session.commit()
            third = await _auto(ACC)
            check("but a season that turns up later does bring it back",
                  third.get("ran") is True, str(third))

            # And once CA does answer, the club ends up grouped and it stops.
            # The 2099 season goes first — the stub only answers for the one
            # grade, so leaving it in would keep the club legitimately unfinished
            # and prove nothing about the job settling.
            async with Session() as session:
                await session.execute(text("DELETE FROM grades WHERE id = :g"),
                                      {"g": new_grade})
                await session.execute(text("DELETE FROM seasons WHERE id = :s"),
                                      {"s": new_season})
                await session.commit()
            grouping.playhq_client.get_teams = teams_ok
            await reset()
            fourth = await _auto(ACC)
            check("once CA answers, the grade is filled in and grouped",
                  fourth.get("ran") is True and fourth.get("grades_filled", 0) >= 1,
                  str(fourth))
            async with Session() as session:
                gap = await grouping.grouping_gap(session, ACC)
                check("leaving nothing for it to act on",
                      gap["seasons_missing"] == 0, str(gap))
            fifth = await _auto(ACC)
            check("so the next sync skips it outright",
                  fifth.get("ran") is False
                  and fifth.get("reason") == "nothing_missing", str(fifth))

            # A job already in flight is never doubled up by a sync.
            await reset()
            async with Session() as session:
                await session.execute(text(
                    "INSERT INTO sync_runs (id, org_id, kind, status, stats,"
                    " started_at) VALUES (gen_random_uuid(), :o, :k, 'running',"
                    " '{}'::jsonb, NOW())"), {"o": ACC, "k": grouping.RUN_KIND})
                await session.commit()
            busy = await _auto(ACC)
            check("and a run already in flight is never doubled up",
                  busy.get("ran") is False
                  and busy.get("reason") == "already_running", str(busy))
            async with Session() as session:
                await session.execute(text(
                    "UPDATE sync_runs SET status = 'success' WHERE org_id = :o"
                    " AND kind = :k AND status = 'running'"),
                    {"o": ACC, "k": grouping.RUN_KIND})
                await session.commit()
            # It must be a job of its own, NOT part of the sync: a club that
            # played nothing in the window never reaches sync_organisation, so
            # an off-season club would never be grouped.
            sched = (Path(__file__).resolve().parent.parent
                     / "app" / "jobs" / "scheduler.py").read_text()
            check("a scheduled pass calls it, so no club waits on a sync",
                  "maybe_group_club" in sched
                  and "group_all_organisations" in sched)
            check("and it is registered as its own nightly job",
                  "nightly_competition_grouping" in sched)
            sync_src = (Path(__file__).resolve().parent.parent
                        / "app" / "services" / "sync.py").read_text()
            check("the sync itself does not carry it",
                  "maybe_group_club" not in sync_src)

            # A NIGHTLY PASS IS NOT SOON ENOUGH FOR A BRAND-NEW CLUB. A club
            # that has just self-served, or that a super admin has just
            # created, opens Manage Grades on "not in a competition" and waits
            # until 02:30 for the platform to do a job it could have done the
            # moment the first sync landed. Both onboarding paths go through
            # `_onboard_club_core`, which queues `_sync_safe`, so hooking that
            # one function covers registration, New Club, the restart
            # self-heal and every later full sync.
            root = Path(__file__).resolve().parent.parent
            orgs_src = (root / "app" / "routers" / "organisations.py").read_text()
            body = orgs_src[orgs_src.index("async def _sync_safe("):]
            body = body[:body.index("@router.post(")]
            # Matched on the CALL, never the bare word: every one of these
            # sites carries a comment naming the function, so a check written
            # against the word passes with the call itself renamed away.
            CALL = "competition_grouping.maybe_group_club("

            def ordered(src: str, *parts: str) -> bool:
                """True when every part is present, in this order.

                Returns False for an absent part rather than raising, so a
                CONTROL RUN reports the check instead of dying on it and
                saying nothing about the ones after it.
                """
                at = -1
                for part in parts:
                    nxt = src.find(part, at + 1)
                    if nxt < 0:
                        return False
                    at = nxt
                return True

            check("the first full sync groups the club itself", CALL in body)
            # Order matters: before `finish_sync_run` the run is still open and
            # `start_sync_run` for the grouping would sit beside an unfinished
            # one; after the `except` clauses it would fire on a paused,
            # cancelled or crashed sync, when the associations it reads have
            # not all been written.
            check("ON THE SUCCESS PATH ONLY — after the run is finished, and "
                  "above the pause/cancel and crash handlers, so a sync that "
                  "did not complete never triggers it",
                  ordered(body, "finish_sync_run(run_id, stats", CALL,
                          "except SyncControlSignal"))
            check("and in its own try/except, so a grouping failure can never "
                  "read as a sync failure — the run is already recorded as a "
                  "success by this point",
                  "Competition grouping after full sync failed" in body)
            check("self-serve registration reaches it through _onboard_club_core",
                  "_onboard_club_core" in
                  (root / "app" / "routers" / "self_serve_trial.py").read_text())
            admin_src = (root / "app" / "routers" / "club_admin.py").read_text()
            check("and so does a super admin creating a club",
                  "_onboard_club_core" in admin_src)
            check("_onboard_club_core is what queues the sync both of them wait on",
                  "background_tasks.add_task(_sync_safe" in orgs_src)
            hr = admin_src[admin_src.index("async def hard_refresh_org("):]
            hr = hr[:hr.index("\n@router.", 1)] if "\n@router." in hr[1:] else hr
            check("a Full Rebuild groups the club too — it rewrites every "
                  "grade, so that is when the associations are freshest",
                  CALL in hr)
            check("and only on ITS true-success branch, after the yearbooks",
                  ordered(hr, "yearbook auto-generate failed", CALL))
        finally:
            grouping.playhq_client.get_teams = real_get_teams

    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  FAILED:", f)
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
