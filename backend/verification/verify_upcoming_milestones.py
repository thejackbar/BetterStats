"""Verification for the dashboard's empty MILESTONES IN REACH panel.

Reported off https://betterat.cricket/hoxton-park-tigers-cricket-club: the
home page's MILESTONES IN REACH panel spun and then said "No upcoming
milestones", while /admin/milestones listed 23 for the same club.

Measured against production before touching a line of it:

    GET /organisations/{hptcc}/upcoming-milestones  → 503 after 60.9s
    GET /records/{hptcc}/milestones                 → 200 in 1.3s, 23 upcoming
    GET /organisations/{applecross}/upcoming-milestones → 200 in 3.4s

So the panel was not empty, it was FAILING: nginx's `/api/` location has no
`proxy_read_timeout` override, so 60s becomes a 504, `error_page 502 503 504
= @backend_down` turns that into a 503, and `Dashboard.jsx`'s
`.catch(() => setMilestones([]))` renders it as an empty club.

Two things are asserted here. That the three surfaces now agree, because they
read ONE definition (`services/milestone_scan`); and that the definition they
share is the fast base-table one, not the `v_effective_player_season_stats`
scan the dashboard used to run.

Runs the SHIPPED functions and route bodies — never a re-implementation.

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_upcoming_milestones.py
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
from app.models.db import Base, Organisation, User
from app.services import milestone_scan
from app.services.aggregations import get_upcoming_milestones_for_org
from app.routers.records import get_records_milestones
from app.routers.club_admin import list_milestones_report

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
OURS = uuid.uuid4()
THEIRS = uuid.uuid4()            # a second synced club sharing a participant

YEAR = date.today().year
S_NOW = uuid.uuid4()             # current season — active
S_OLD = uuid.uuid4()             # outside the three-year active window
S_THEIRS = uuid.uuid4()          # their season, same shared player
G_NOW = uuid.uuid4(); G_OLD = uuid.uuid4(); G_THEIRS = uuid.uuid4()

# The reported shapes. Every one of these is a real row on the admin report.
P_MATCHES = uuid.uuid4()   # 49 club games, no runs and no wickets at all
P_CATCHES = uuid.uuid4()   # 48 catches, likewise
P_RUNS = uuid.uuid4()      # 493 runs
P_WICKETS = uuid.uuid4()   # 48 wickets
P_SHARED = uuid.uuid4()    # plays for both clubs under one CA participant GUID
P_DORMANT = uuid.uuid4()   # 499 runs, but stopped playing years ago
P_NOT_PLAYER = uuid.uuid4()  # is_player = FALSE (a coach, a scorer)
P_MILES_AWAY = uuid.uuid4()  # 12 runs — nowhere near anything


async def build_schema() -> None:
    async with engine.begin() as conn:
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
        json_cols = (await conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type = 'json'"))).all()
        for tbl, col in json_cols:
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb '
                f'USING "{col}"::text::jsonb'))
        # The views the PREVIOUS implementation read — present so the control
        # run (this suite against the old code) exercises real SQL.
        stmts = view_statements()
        for _ in range(2):
            for name, sql in stmts:
                await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
                await conn.execute(text(sql.replace("OR REPLACE ", "")))


async def seed(session) -> None:
    async def ex(sql, **kw):
        await session.execute(text(sql), kw)

    for oid, name in ((OURS, "Our Club"), (THEIRS, "Their Club")):
        await ex("INSERT INTO organisations (id, name, is_active) "
                 "VALUES (:i, :n, true)", i=oid, n=name)

    for sid, org, nm, yr in (
        (S_NOW, OURS, f"Summer {YEAR}/{str(YEAR + 1)[2:]}", YEAR),
        (S_OLD, OURS, "Summer 2014/15", 2014),
        (S_THEIRS, THEIRS, f"Summer {YEAR}/{str(YEAR + 1)[2:]}", YEAR),
    ):
        await ex("INSERT INTO seasons (id, organisation_id, name, year) "
                 "VALUES (:i, :o, :n, :y)", i=sid, o=org, n=nm, y=yr)

    for gid, sid in ((G_NOW, S_NOW), (G_OLD, S_OLD), (G_THEIRS, S_THEIRS)):
        await ex("INSERT INTO grades (id, season_id, name, category) "
                 "VALUES (:i, :s, 'Men''s First Grade', 'senior')", i=gid, s=sid)

    players = [
        (P_MATCHES, OURS, "Awan, Muhammad Ali Mehdi", True),
        (P_CATCHES, OURS, "Nandwani, Reyansh", True),
        (P_RUNS, OURS, "Bellach, Luke", True),
        (P_WICKETS, OURS, "Bhat, Aman", True),
        (P_SHARED, OURS, "Shared, Participant", True),
        (P_DORMANT, OURS, "Gone, Fishing", True),
        (P_NOT_PLAYER, OURS, "Scorer, The", False),
        (P_MILES_AWAY, OURS, "Newcomer, A", True),
    ]
    for pid, org, nm, is_player in players:
        await ex("INSERT INTO players (id, organisation_id, name, is_player, status) "
                 "VALUES (:i, :o, :n, :p, 'active')",
                 i=pid, o=org, n=nm, p=is_player)

    async def stats(pid, sid, *, matches=0, runs=0, wickets=0, catches=0):
        await ex("""INSERT INTO player_season_stats
                    (player_id, season_id, matches, runs, wickets, catches)
                    VALUES (:p, :s, :m, :r, :w, :c)""",
                 p=pid, s=sid, m=matches, r=runs, w=wickets, c=catches)

    # Current season — every one of these is in reach of its next threshold.
    await stats(P_MATCHES, S_NOW, matches=49)
    await stats(P_CATCHES, S_NOW, matches=30, catches=48)
    await stats(P_RUNS, S_NOW, matches=20, runs=493)
    await stats(P_WICKETS, S_NOW, matches=20, wickets=48)
    await stats(P_NOT_PLAYER, S_NOW, matches=49)
    await stats(P_MILES_AWAY, S_NOW, matches=3, runs=12)

    # Dormant: 499 runs, last seen 2014.
    await stats(P_DORMANT, S_OLD, matches=40, runs=499)

    # The shared participant: 493 runs with us this season, and 470 more with
    # the OTHER club under the same CA participant GUID. Their rows must not be
    # summed into our career total, or he reads as 963 and is chasing 1,000
    # instead of the 500 he is genuinely 7 short of.
    await stats(P_SHARED, S_NOW, matches=10, runs=493)
    await stats(P_SHARED, S_THEIRS, matches=25, runs=470)

    await session.commit()


def by_player(rows, name_key):
    """{(player_id, type): row} for whichever name key this payload uses."""
    return {(r["player_id"], r["type"]): r for r in rows}


async def main() -> None:
    await build_schema()
    async with Session() as s:
        await seed(s)

    org_id = str(OURS)

    async with Session() as s:
        dash = await get_upcoming_milestones_for_org(s, org_id, 200)
        recs = await get_records_milestones(org_id, None, s, None)
        club = await s.get(Organisation, OURS)
        admin = await list_milestones_report(User(id=uuid.uuid4(), username="a"), club, s)

    print("\n── the reported case: the dashboard panel is not empty ──")
    check("dashboard returns milestones at all", len(dash) > 0,
          f"got {len(dash)}")

    d = by_player(dash, "name")
    r = by_player(recs["upcoming"], "player_name")
    a = by_player(admin["upcoming"], "player_name")

    check("the 49-club-games player is on the dashboard",
          (str(P_MATCHES), "matches") in d)
    check("  …at 49 of 50, 1 to go",
          d.get((str(P_MATCHES), "matches"), {}).get("current") == 49
          and d.get((str(P_MATCHES), "matches"), {}).get("target") == 50
          and d.get((str(P_MATCHES), "matches"), {}).get("needed") == 1,
          str(d.get((str(P_MATCHES), "matches"))))
    check("the 48-catches player is on the dashboard",
          (str(P_CATCHES), "catches") in d)
    check("the 493-runs player is on the dashboard",
          (str(P_RUNS), "runs") in d)
    check("the 48-wickets player is on the dashboard",
          (str(P_WICKETS), "wickets") in d)

    print("\n── all three surfaces read one definition ──")
    check("dashboard and Records name the same set",
          set(d) == set(r), f"dash={sorted(set(d) - set(r))} recs={sorted(set(r) - set(d))}")
    check("dashboard and the admin report name the same set",
          set(d) == set(a), f"dash={sorted(set(d) - set(a))} admin={sorted(set(a) - set(d))}")
    # Compared over the keys they share, so a control run against the old
    # code reports the disagreement rather than dying on a KeyError.
    shared_keys = set(d) & set(r) & set(a)
    check("…and agree on current/target/needed for every one",
          bool(shared_keys) and all(
              (d[k]["current"], d[k]["target"], d[k]["needed"])
              == (r[k]["current"], r[k]["target"], r[k]["needed"])
              == (a[k]["current"], a[k]["target"], a[k]["needed"])
              for k in shared_keys))
    check("the dashboard still names the player under `name`",
          all("name" in row for row in dash))
    check("…and the reports still under `player_name`",
          all("player_name" in row for row in recs["upcoming"]))

    print("\n── who is left out, and why ──")
    check("a dormant player on 499 runs is not in reach",
          (str(P_DORMANT), "runs") not in d)
    check("a non-player on 49 games is not in reach",
          (str(P_NOT_PLAYER), "matches") not in d)
    check("a player 488 runs away is not in reach",
          (str(P_MILES_AWAY), "runs") not in d)
    check("…but that player's 3 games are, at 3 of 50? no — out of window",
          (str(P_MILES_AWAY), "matches") not in d)

    print("\n── the cross-club guard (migration 060, on the base table) ──")
    shared = d.get((str(P_SHARED), "runs"))
    check("the shared participant is on the dashboard at all", shared is not None)
    check("…counted on OUR 493 runs, not 963 across both clubs",
          shared is not None and shared["current"] == 493, str(shared))
    check("…so he is 7 short of 500, not chasing 1,000",
          shared is not None and shared["target"] == 500
          and shared["needed"] == 7, str(shared))

    print("\n── ordering and caps ──")
    scores = [row["score"] for row in dash]
    check("the dashboard is sorted biggest-milestone first",
          scores == sorted(scores, reverse=True))
    check("every row carries a score", all(row.get("score") for row in dash))
    async with Session() as s:
        capped = await get_upcoming_milestones_for_org(s, org_id, 2)
    check("`limit` is honoured rather than ignored", len(capped) == 2,
          f"got {len(capped)}")
    check("…and takes the highest-scoring rows",
          [x["player_id"] for x in capped] == [x["player_id"] for x in dash[:2]])

    print("\n── the query the dashboard now runs ──")
    async with Session() as s:
        plan = (await s.execute(
            text("EXPLAIN (FORMAT TEXT) " + str(milestone_scan._TOTALS_SQL)),
            {"org_id": org_id, "cutoff": YEAR - 2},
        )).scalars().all()
    joined = "\n".join(plan)
    check("it does not touch v_effective_player_season_stats",
          "player_season_stats" in joined and "unplayed" not in joined.lower(),
          joined[:200])

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAILURES:
        print("failed:")
        for f in FAILURES:
            print("  -", f)
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
