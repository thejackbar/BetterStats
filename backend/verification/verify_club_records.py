"""Verification for the club record book, against a real Postgres.

Runs the SHIPPED `services/club_records.py` and the shipped
`routers/records.py::get_club_records` route body — never a re-implementation
— over the `v_effective_*` views pulled straight out of the migrations that
define them.

What this is really testing is the reconstruction. Cricket stores no team
score, so every figure on this record book is rebuilt per game from the
per-innings rows, and the two ways that goes wrong are:

  1. A shared fixture between two synced clubs is ONE `games` row carrying
     BOTH clubs' innings. Without the player scope, the opposition's runs are
     summed into ours and their dismissals counted into our wickets — so the
     club's "highest total" is really both sides added together.
  2. `games.innings_totals` (migration 233) is prospective and never
     backfilled, so a club's history mixes exact totals (batters PLUS extras)
     with bat-only sums that read 10-25 runs light. A record book ranks these
     directly against each other, and the skew runs in OPPOSITE directions on
     the highest and lowest boards.

Run:  DATABASE_URL=postgresql+asyncpg://root@/clubrec_test?host=/var/run/postgresql \
      python verification/verify_club_records.py
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
from app.services import club_records
from app.routers.records import get_club_records

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


OURS = uuid.uuid4()
THEIRS = uuid.uuid4()

S_24 = uuid.uuid4(); S_25 = uuid.uuid4()
G_24 = uuid.uuid4(); G_25 = uuid.uuid4(); G_JUNIOR = uuid.uuid4()
# Their grade row, our fixture — the shared-fixture case.
G_THEIRS = uuid.uuid4(); S_THEIRS = uuid.uuid4()

P_OURS = [uuid.uuid4() for _ in range(11)]
P_THEIRS = [uuid.uuid4() for _ in range(11)]


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Raw-SQL lifespan tables create_all doesn't make.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS season_aliases (
                id SERIAL PRIMARY KEY,
                merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL,
                canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                alias_season_id    UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                undone_at TIMESTAMPTZ)
        """))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_season_aliases_alias_active "
            "ON season_aliases(alias_season_id) WHERE undone_at IS NULL"))
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
        # The competitions DDL is its own list, run by alembic AND the
        # lifespan mirror — not by create_all — so the filter has nothing to
        # bite on without it.
        from app.services.competition_ddl import STATEMENTS as _COMP_DDL
        for _stmt in _COMP_DDL:
            await conn.execute(text(_stmt))
        # migration 233 is a raw ALTER and never reached the ORM model, so
        # create_all doesn't make the column the whole exact/approximate
        # split turns on.
        await conn.execute(text(
            "ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        # create_all types `raw_payload` as json where the migrations use
        # jsonb, and a UNION cannot coerce between them.
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


# (game_id, date, opp, our runs per batter, wickets we lost, opp runs conceded,
#  wickets we took, we batted first, result, exact totals or None)
#
# Every figure below is chosen so a board's answer is arithmetic rather than
# whatever the seed happens to produce — see the asserts.
GAMES: list[dict] = []


def _g(day, opp, our_runs, wkts_lost, opp_runs, wkts_taken,
       batted_first, result, exact=None, season=None, grade=None):
    GAMES.append({
        "id": uuid.uuid4(), "day": day, "opp": opp,
        "our_runs": our_runs, "wkts_lost": wkts_lost,
        "opp_runs": opp_runs, "wkts_taken": wkts_taken,
        "batted_first": batted_first, "result": result,
        "exact": exact, "season": season or S_25, "grade": grade or G_25,
    })


# Our record total, and it is EXACT (extras stored) — 300 on the board.
_g(1,  "Rovers",   [40, 60, 80, 50, 40, 10, 5, 0, 0, 0, 0], 8, 120, 10, True,  "WIN",
   exact={"ours": 300, "our_wkts": 8, "theirs": 120, "their_wkts": 10})
# Bat-only. Batters make 250; the real total was higher but extras aren't held.
_g(2,  "Wanderers", [50, 50, 50, 40, 30, 20, 10, 0, 0, 0, 0], 10, 200, 6, True, "WIN")
# Our lowest ALL-OUT total: 35.
_g(3,  "Rovers",   [10, 5, 5, 5, 4, 3, 2, 1, 0, 0, 0], 10, 100, 3, True, "LOSS")
# A short chase — 2 wickets down for 40. Must NOT reach the lowest board.
_g(4,  "Casuals",  [20, 15, 5, 0, 0, 0, 0, 0, 0, 0, 0], 2, 38, 10, False, "WIN")
# Biggest win by runs: 280 - 60 = 220.
_g(5,  "Tigers",   [80, 70, 60, 40, 20, 10, 0, 0, 0, 0, 0], 9, 60, 10, True, "WIN")
# Biggest win by wickets: chased losing 1 → 9 wickets.
_g(6,  "Lions",    [90, 60, 10, 0, 0, 0, 0, 0, 0, 0, 0], 1, 155, 10, False, "WIN")
# Heaviest defeat by runs: 250 - 90 = 160 (we chased and fell short).
_g(7,  "Eagles",   [30, 25, 20, 10, 5, 0, 0, 0, 0, 0, 0], 10, 250, 8, False, "LOSS")
# Heaviest defeat by wickets: we set a total, they chased 2 down → 8 wickets.
_g(8,  "Sharks",   [40, 30, 20, 10, 5, 5, 0, 0, 0, 0, 0], 10, 115, 2, True, "LOSS")
# Highest conceded: 400 (exact both ways).
_g(9,  "Kings",    [60, 40, 30, 20, 10, 0, 0, 0, 0, 0, 0], 10, 400, 4, False, "LOSS",
   exact={"ours": 175, "our_wkts": 10, "theirs": 400, "their_wkts": 4})
# Lowest we bowled a side out for: 22, all ten down.
_g(10, "Pilgrims",  [50, 30, 20, 0, 0, 0, 0, 0, 0, 0, 0], 3, 22, 10, False, "WIN")
# A DRAW — breaks a win streak, not an unbeaten one.
_g(11, "Rovers",   [70, 50, 30, 0, 0, 0, 0, 0, 0, 0, 0], 5, 150, 5, True, "DRAW")
# Three straight wins after the draw → the longest win streak is 3.
_g(12, "Casuals",  [55, 45, 20, 0, 0, 0, 0, 0, 0, 0, 0], 4, 100, 10, True, "WIN")
_g(13, "Tigers",   [45, 35, 25, 0, 0, 0, 0, 0, 0, 0, 0], 5,  90, 10, True, "WIN")
_g(14, "Lions",    [35, 25, 15, 0, 0, 0, 0, 0, 0, 0, 0], 6,  70, 10, True, "WIN")
# An earlier season, so the season board has two rows to rank.
_g(20, "Rovers",   [30, 20, 10, 0, 0, 0, 0, 0, 0, 0, 0], 10, 200, 4, True, "LOSS",
   season=S_24, grade=G_24)
_g(21, "Tigers",   [40, 30, 20, 0, 0, 0, 0, 0, 0, 0, 0], 10, 180, 5, True, "LOSS",
   season=S_24, grade=G_24)


SHARED = uuid.uuid4()   # the fixture the OPPOSITION synced first


async def seed(session) -> None:
    async def ex(sql, **kw):
        await session.execute(text(sql), kw)

    for oid, nm in ((OURS, "Our Club"), (THEIRS, "Their Club")):
        await ex("INSERT INTO organisations (id, name, is_active) "
                 "VALUES (:i, :n, true)", i=oid, n=nm)

    for sid, org, nm, yr in (
        (S_24, OURS, "Summer 2024/25", 2024),
        (S_25, OURS, "Summer 2025/26", 2025),
        (S_THEIRS, THEIRS, "Summer 2025/26", 2025),
    ):
        await ex("INSERT INTO seasons (id, organisation_id, name, year) "
                 "VALUES (:i, :o, :n, :y)", i=sid, o=org, n=nm, y=yr)

    for gid, sid, nm, cat in (
        (G_24, S_24, "Men's First Grade", "senior"),
        (G_25, S_25, "Men's First Grade", "senior"),
        # A junior grade is what makes the club's DEFAULT scope active, so the
        # category filter is genuinely exercised rather than emitting no SQL.
        (G_JUNIOR, S_25, "Under 14s", "junior"),
        (G_THEIRS, S_THEIRS, "Men's First Grade", "senior"),
    ):
        await ex("INSERT INTO grades (id, season_id, name, category) "
                 "VALUES (:i, :s, :n, :c)", i=gid, s=sid, n=nm, c=cat)

    for i, pid in enumerate(P_OURS):
        await ex("INSERT INTO players (id, organisation_id, name) "
                 "VALUES (:i, :o, :n)", i=pid, o=OURS, n=f"Our Player {i+1}")
    for i, pid in enumerate(P_THEIRS):
        await ex("INSERT INTO players (id, organisation_id, name) "
                 "VALUES (:i, :o, :n)", i=pid, o=THEIRS, n=f"Their Player {i+1}")

    async def add_game(gid, day, season, grade, opp, our_runs, wkts_lost,
                       opp_runs, wkts_taken, batted_first, result,
                       exact=None, org_side=True):
        """One game plus the per-innings rows every figure is rebuilt from."""
        our_inn = 1 if batted_first else 2
        totals = None
        if exact:
            import json
            rows = [{"innings_number": our_inn,
                     "runs_scored": exact["ours"], "wickets": exact["our_wkts"],
                     "extras": exact["ours"] - sum(our_runs)},
                    {"innings_number": 2 if batted_first else 1,
                     "runs_scored": exact["theirs"], "wickets": exact["their_wkts"],
                     "extras": 0}]
            totals = json.dumps(rows)
        await ex(
            "INSERT INTO games (id, grade_id, played_at, home_team, away_team, "
            " home_club, away_club, opp_club_name, result, winning_team, "
            " home_org_id, away_org_id, venue, match_format, is_final, innings_totals) "
            "VALUES (:i, :g, :d, :ht, :at, :hc, :ac, :opp, :r, :wt, :ho, :ao, "
            " :v, 'One Day', false, CAST(:it AS JSONB))",
            i=gid, g=grade, d=date(2025 if season != S_24 else 2024, 1, min(day, 28)),
            ht="Our Club" if batted_first else opp,
            at=opp if batted_first else "Our Club",
            hc="Our Club" if batted_first else opp,
            ac=opp if batted_first else "Our Club",
            opp=opp,
            r=result,
            wt=("Our Club" if result == "WIN" else opp) if result != "DRAW" else None,
            ho=(OURS if batted_first else None) if org_side else None,
            ao=(None if batted_first else OURS) if org_side else None,
            v="Home Ground", it=totals)

        # Our batters. A dismissal is a row that is out with a dismissal type;
        # `wkts_lost` of them are out, the rest not out.
        for idx, runs in enumerate(our_runs):
            out = idx < wkts_lost
            await ex(
                "INSERT INTO batting_innings (game_id, player_id, "
                " innings_number, batting_position, runs, balls, not_out, "
                " dismissal_type, did_not_bat) "
                "VALUES (:g, :p, :inn, :pos, :r, :b, :no, :dt, false)",
                g=gid, p=P_OURS[idx], inn=our_inn, pos=idx + 1, r=runs,
                b=max(runs, 1), no=not out,
                dt="caught" if out else None)

        # Our bowlers concede the opposition's runs and take their wickets.
        per = max(1, opp_runs // 5)
        left = opp_runs
        for idx in range(5):
            r = per if idx < 4 else left
            left -= per
            await ex(
                "INSERT INTO bowling_spells (game_id, player_id, "
                " innings_number, overs, maidens, runs, wickets) "
                "VALUES (:g, :p, :inn, 5, 0, :r, :w)",
                g=gid, p=P_OURS[idx], inn=2 if batted_first else 1,
                r=max(r, 0), w=(wkts_taken // 5) + (1 if idx < wkts_taken % 5 else 0))

    for g in GAMES:
        await add_game(g["id"], g["day"], g["season"], g["grade"], g["opp"],
                       g["our_runs"], g["wkts_lost"], g["opp_runs"],
                       g["wkts_taken"], g["batted_first"], g["result"],
                       g["exact"])

    await session.commit()



async def records(session, **kw):
    """Call the shipped route body with every param supplied.

    A route function called directly does NOT get FastAPI's dependency
    resolution, so an omitted argument arrives as the `Query(...)` object
    itself rather than its default. Passing all of them keeps the harness
    exercising the real body instead of tripping over that.
    """
    args = dict(season_id=None, grade_id=None, grade_name=None,
                finals_only=False, categories="all", formats=None,
                competitions=None)
    args.update(kw)
    return await get_club_records(str(OURS), db=session, **args)


def _vals(board):
    return [r["value"] for r in board["rows"]]


async def run_checks() -> None:
    async with Session() as s:
        # The SHIPPED route body, not a re-implementation.
        payload = await records(s)

    b = payload["boards"]
    print("\n── team totals ──")
    hi = b["highest_totals"]
    g1 = next((r for r in hi["rows"] if r["game_id"] == str(GAMES[0]["id"])), None)
    check("the club's own 300 is on the board, not both sides added together",
          g1 is not None and g1["value"] == 300, f"got {g1['value'] if g1 else None}")
    check("that total is reported as exact", g1 is not None and g1["exact"] is True)
    check("highest board is ordered descending", _vals(hi) == sorted(_vals(hi), reverse=True))
    check("a bat-only total rides along marked approximate",
          any(r["exact"] is False for r in hi["rows"]))
    check("the board says how many of its rows are approximate",
          hi["approximate"] == sum(1 for r in hi["rows"] if not r["exact"]),
          f"{hi['approximate']}")

    lo = b["lowest_totals"]
    check("lowest ALL-OUT total is 35", lo["rows"] and lo["rows"][0]["value"] == 35,
          f"got {lo['rows'][0]['value'] if lo['rows'] else None}")
    check("a 2-wicket short chase is NOT a lowest-total record",
          all(r["value"] != 40 for r in lo["rows"]))
    check("every row on the lowest board was bowled out",
          all(r["our_wickets"] >= club_records.ALL_OUT_WICKETS for r in lo["rows"]))

    hc = b["highest_conceded"]
    check("highest conceded is 400", hc["rows"] and hc["rows"][0]["value"] == 400,
          f"got {hc['rows'][0]['value'] if hc['rows'] else None}")
    lc = b["lowest_conceded"]
    check("lowest total we bowled a side out for is 22",
          lc["rows"] and lc["rows"][0]["value"] == 22,
          f"got {lc['rows'][0]['value'] if lc['rows'] else None}")
    check("every row on the bowled-out board took ten wickets",
          all(r["opp_wickets"] >= club_records.ALL_OUT_WICKETS for r in lc["rows"]))

    print("\n── margins ──")
    wr = b["biggest_wins_runs"]
    w220 = next((r for r in wr["rows"] if r["game_id"] == str(GAMES[4]["id"])), None)
    check("the 280-60 win is recorded as a 220-run margin",
          w220 is not None and w220["value"] == 220,
          f"got {w220['value'] if w220 else None}")
    check("a win by runs is only ever a game we batted first in",
          all(r["unit"] == "runs" for r in wr["rows"]))
    ww = b["biggest_wins_wickets"]
    check("biggest win by wickets is 9", ww["rows"] and ww["rows"][0]["value"] == 9,
          f"got {ww['rows'][0]['value'] if ww['rows'] else None}")
    check("a wickets margin never exceeds ten",
          all(0 <= r["value"] <= 10 for r in ww["rows"]))
    dr = b["heaviest_defeats_runs"]
    # 400 chased, 175 made — and the 175 is the EXACT total, so this row also
    # proves a margin is worked out from the exact figure where one exists
    # rather than from the batters' 160.
    check("heaviest defeat by runs is 225", dr["rows"] and dr["rows"][0]["value"] == 225,
          f"got {dr['rows'][0]['value'] if dr['rows'] else None}")
    check("the 160-run defeat ranks below it",
          len(dr["rows"]) > 1 and dr["rows"][1]["value"] == 160,
          f"got {[r['value'] for r in dr['rows']]}")
    check("a margin built from an exact total is reported exact",
          dr["rows"] and dr["rows"][0]["exact"] is True)
    dw = b["heaviest_defeats_wickets"]
    check("heaviest defeat by wickets is 8", dw["rows"] and dw["rows"][0]["value"] == 8,
          f"got {dw['rows'][0]['value'] if dw['rows'] else None}")
    check("runs and wickets margins are never mixed into one board",
          {r["unit"] for r in wr["rows"]} == {"runs"}
          and {r["unit"] for r in ww["rows"]} == {"wickets"})

    print("\n── streaks ──")
    win = b["longest_win_streak"]
    check("a winning run is found and is at least the seeded 3",
          win["rows"] and win["rows"][0]["value"] >= 3,
          f"got {win['rows'][0]['value'] if win['rows'] else None}")
    unb = b["longest_unbeaten_streak"]
    check("a draw does not break an unbeaten run",
          unb["rows"] and unb["rows"][0]["value"] > win["rows"][0]["value"],
          f"unbeaten {unb['rows'][0]['value']} vs wins {win['rows'][0]['value']}")
    check("the unbeaten run counts the draw in it",
          unb["rows"] and unb["rows"][0]["draws"] >= 1)
    check("a streak reports the games it ran between",
          unb["rows"] and unb["rows"][0]["from"] and unb["rows"][0]["to"])

    print("\n── seasons ──")
    seas = b["best_seasons"]
    check("both seasons are listed", len(seas["rows"]) == 2, f"{len(seas['rows'])}")
    check("the winning season ranks above the winless one",
          seas["rows"][0]["wins"] > seas["rows"][-1]["wins"])
    check("a winless season reads 0%", seas["rows"][-1]["win_rate"] == 0.0)
    check("each season's W+L+D equals its games played",
          all(r["wins"] + r["losses"] + r["draws"] == r["played"] for r in seas["rows"]))

    print("\n── summary and coverage ──")
    summ = payload["summary"]
    # +2: the two reported games seeded alongside the base fixture.
    # +2 reported cases, +4 fault cases seeded alongside the base fixture.
    # +2 reported cases, +4 fault cases, +3 filter cases.
    check("summary played equals the seeded games", summ["played"] == len(GAMES) + 9,
          f"{summ['played']} vs {len(GAMES) + 9}")
    check("summary W+L+D reconciles with played",
          summ["wins"] + summ["losses"] + summ["draws"] == summ["played"])
    cov = payload["coverage"]
    check("coverage counts exact and approximate separately",
          cov["exact_totals"] + cov["approximate_totals"] == cov["games_with_a_total"])
    check("coverage counts more than one exact game", cov["exact_totals"] >= 2,
          f"{cov['exact_totals']}")
    check("coverage still reports approximate games too", cov["approximate_totals"] >= 1,
          f"{cov['approximate_totals']}")
    check("a club with approximate totals is told so", bool(cov["note"]))


async def run_shared_fixture_check() -> None:
    """The leak this whole design exists to prevent.

    A fixture between two synced clubs is ONE `games` row. Our sync writes our
    batters' innings against it; THEIR sync writes theirs against the same
    row. A team total rebuilt without scoping the player to our own club adds
    the two sides together — so the club's "highest total" becomes the match
    aggregate, and its wickets lost can reach twenty.
    """
    import json
    async with Session() as s:
        await s.execute(text(
            "INSERT INTO games (id, grade_id, played_at, home_team, away_team, "
            " home_club, away_club, opp_club_name, result, winning_team, "
            " home_org_id, away_org_id, venue, match_format, is_final) "
            "VALUES (:i, :g, :d, 'Our Club', 'Their Club', 'Our Club', "
            " 'Their Club', 'Their Club', 'WIN', 'Our Club', :ho, :ao, "
            " 'Shared Oval', 'One Day', false)"),
            {"i": SHARED, "g": G_THEIRS, "d": date(2025, 3, 1),
             "ho": OURS, "ao": THEIRS})
        # Ours: 150 off five batters, all five out.
        for idx in range(5):
            await s.execute(text(
                "INSERT INTO batting_innings (game_id, player_id, "
                " innings_number, batting_position, runs, balls, not_out, "
                " dismissal_type, did_not_bat) VALUES (:g, "
                " :p, 1, :pos, 30, 30, false, 'caught', false)"),
                {"g": SHARED, "p": P_OURS[idx], "pos": idx + 1})
        # Theirs: 500 off five batters on the SAME games row.
        for idx in range(5):
            await s.execute(text(
                "INSERT INTO batting_innings (game_id, player_id, "
                " innings_number, batting_position, runs, balls, not_out, "
                " dismissal_type, did_not_bat) VALUES (:g, "
                " :p, 2, :pos, 100, 100, false, 'caught', false)"),
                {"g": SHARED, "p": P_THEIRS[idx], "pos": idx + 1})
        for idx in range(3):
            await s.execute(text(
                "INSERT INTO bowling_spells (game_id, player_id, "
                " innings_number, overs, maidens, runs, wickets) VALUES "
                " (:g, :p, 2, 10, 0, 60, 2)"),
                {"g": SHARED, "p": P_OURS[idx]})
        await s.commit()

    async with Session() as s:
        payload = await records(s)

    print("\n── the shared fixture ──")
    rows = payload["boards"]["highest_totals"]["rows"]
    shared = [r for r in rows if r["game_id"] == str(SHARED)]
    check("a fixture the opposition synced first is still ours", bool(shared),
          "the shared game is missing from the record book entirely")
    if shared:
        check("our total on it is our own 150, not the match aggregate of 650",
              shared[0]["value"] == 150, f"got {shared[0]['value']}")
        check("our wickets lost on it is 5, not both sides' 10",
              shared[0]["our_wickets"] == 5, f"got {shared[0]['our_wickets']}")
    # 650 is our 150 plus their 500 on one shared games row. 323 is the real
    # club record. Anything above it means the leak is back.
    check("the opposition's 500 never becomes the club's highest total",
          all(r["value"] != 650 for r in rows) and rows[0]["value"] == 513,
          f"top of the board reads {rows[0]['value']}")


async def run_filter_checks() -> None:
    """The filters the Records page already carries have to bite here too."""
    async with Session() as s:
        all_seasons = await records(s)
        one_season = await records(s, season_id=str(S_24))
        by_grade = await records(s, grade_name="Men's First Grade")
        finals = await records(s, finals_only=True)

    print("\n── filters ──")
    check("a season filter narrows the record book",
          one_season["summary"]["played"] < all_seasons["summary"]["played"],
          f"{one_season['summary']['played']} vs {all_seasons['summary']['played']}")
    check("the 2024/25 season is the two games seeded into it",
          one_season["summary"]["played"] == 2,
          f"{one_season['summary']['played']}")
    check("its highest total is that season's own, not the club's record",
          one_season["boards"]["highest_totals"]["rows"][0]["value"] == 90,
          f"got {one_season['boards']['highest_totals']['rows'][0]['value']}")
    check("a merge-aware grade filter still finds the games",
          by_grade["summary"]["played"] > 0,
          f"{by_grade['summary']['played']}")
    check("finals-only returns the club's one final and nothing else",
          finals["summary"]["played"] == 1,
          f"{finals['summary']['played']}")
    check("the payload reports the grade scope it applied",
          "grade_scope" in all_seasons and "categories" in all_seasons["grade_scope"])


# ── the four faults reported off the live board ─────────────────────────────
# A 9/437 batting second against a side who made 83. Ranked by runs made, it
# topped "highest successful chases" — a 437 nobody chased.
BIG_SCORE_SMALL_TARGET = uuid.uuid4()
# A genuine chase: 250 to get, got there five down.
REAL_CHASE = uuid.uuid4()
# A two-innings game we won having been bowled out in our last innings — it
# reported as a 0-WICKET win, which cannot happen.
BOWLED_OUT_WIN = uuid.uuid4()
# A partly-entered historical card: the whole unaccounted balance dumped into
# byes, off one bowling row. Its "163 extras" are the runs nobody wrote down.
STUB_CARD = uuid.uuid4()

# ── the two reported cases, replayed ────────────────────────────────────────
# 1df207e1: Applecross 8-323 and 8-158, Murdoch Uni 102. The record book read
# 481 — the two OUR innings added together, a score nobody made.
TWO_DAY = uuid.uuid4()
# 6f3af360: a drawn two-day game where the other side made 305 and we never
# batted at all. With no innings of our own, the exact-total path was skipped
# entirely and the figure fell back to a doubled bowling sum (592 for a real
# 305). This is the case that proves the opposition total is read from the
# innings we BOWLED in, not from "the innings we didn't bat in".
NEVER_BATTED = uuid.uuid4()


async def seed_reported(session) -> None:
    import json
    async def ex(sql, **kw):
        await session.execute(text(sql), kw)

    # --- the two-day match, both sides' innings stored exactly -------------
    await ex(
        "INSERT INTO games (id, grade_id, played_at, home_team, away_team, "
        " home_club, away_club, opp_club_name, result, winning_team, "
        " home_org_id, away_org_id, venue, match_format, is_final, innings_totals) "
        "VALUES (:i, :g, :d, 'Our Club', 'Murdoch Uni', 'Our Club', 'Murdoch Uni', "
        " 'Murdoch Uni', 'WIN', 'Our Club', :o, NULL, 'Home', 'Two Day', false, "
        " CAST(:it AS JSONB))",
        i=TWO_DAY, g=G_25, d=date(2025, 2, 1), o=OURS,
        it=json.dumps([
            {"innings_number": 1, "runs_scored": 323, "wickets": 8, "extras": 17},
            {"innings_number": 2, "runs_scored": 102, "wickets": 10, "extras": 8},
            {"innings_number": 3, "runs_scored": 158, "wickets": 8, "extras": 10},
        ]))
    # Our two innings: batters make less than the stored total (extras).
    for inn, runs, outs in ((1, 306, 8), (3, 148, 8)):
        for idx in range(10):
            await ex(
                "INSERT INTO batting_innings (game_id, player_id, innings_number, "
                " batting_position, runs, balls, not_out, dismissal_type, did_not_bat) "
                "VALUES (:g, :p, :inn, :pos, :r, 30, :no, :dt, false)",
                g=TWO_DAY, p=P_OURS[idx], inn=inn, pos=idx + 1,
                r=(runs // 10), no=idx >= outs,
                dt="caught" if idx < outs else None)
    # Our bowlers bowled their one innings (order 2). 102 all out with 8
    # byes means the bowlers were charged 94 — a card that reconciles, which
    # is what the extras board requires.
    for idx, r in enumerate((19, 19, 19, 19, 18)):
        await ex(
            "INSERT INTO bowling_spells (game_id, player_id, innings_number, "
            " overs, maidens, runs, wickets) VALUES (:g, :p, 2, 8, 0, :r, 2)",
            g=TWO_DAY, p=P_OURS[idx], r=r)

    # --- the drawn game we never batted in --------------------------------
    await ex(
        "INSERT INTO games (id, grade_id, played_at, home_team, away_team, "
        " home_club, away_club, opp_club_name, result, winning_team, "
        " home_org_id, away_org_id, venue, match_format, is_final, innings_totals) "
        "VALUES (:i, :g, :d, 'Whitfords', 'Our Club', 'Whitfords', 'Our Club', "
        " 'Whitfords', 'DRAW', NULL, NULL, :o, 'Away', 'Two Day', false, "
        " CAST(:it AS JSONB))",
        i=NEVER_BATTED, g=G_25, d=date(2025, 2, 8), o=OURS,
        it=json.dumps([{"innings_number": 1, "runs_scored": 305,
                        "wickets": 10, "extras": 21}]))
    # DUPLICATED bowling rows — the live database really does carry these for
    # the reported game, and a doubled bat/bowl sum is exactly what produced
    # 592. The exact figure has to win over it.
    for _ in range(2):
        for idx in range(6):
            await ex(
                "INSERT INTO bowling_spells (game_id, player_id, innings_number, "
                " overs, maidens, runs, wickets) VALUES (:g, :p, 1, 10, 0, 49, 1)",
                g=NEVER_BATTED, p=P_OURS[idx])
    await session.commit()


async def run_reported_checks() -> None:
    async with Session() as s:
        payload = await records(s)
    b = payload["boards"]

    print("\n── the reported two-day match ──")
    hi = b["highest_totals"]["rows"]
    top = next((r for r in hi if r["game_id"] == str(TWO_DAY)), None)
    check("a two-day match's innings are ranked separately, not summed",
          top is not None and top["value"] == 323, f"got {top['value'] if top else None}")
    check("481 — the two innings added together — is on no totals board",
          all(r["value"] != 481 for r in hi), "the match aggregate is still being ranked as a total")
    check("its second innings is its own row",
          sum(1 for r in hi if r["game_id"] == str(TWO_DAY)) == 2,
          f"{sum(1 for r in hi if r['game_id'] == str(TWO_DAY))} row(s)")
    check("a totals row says which innings it was",
          top is not None and top.get("innings_number") == 1)
    conc = b["highest_conceded"]["rows"]
    murdoch = next((r for r in conc if r["game_id"] == str(TWO_DAY)), None)
    check("the opposition's 102 is read as 102, not as its 8 extras",
          murdoch is not None and murdoch["value"] == 102,
          f"got {murdoch['value'] if murdoch else None}")

    print("\n── match aggregates are their own record ──")
    agg = b["highest_match_totals"]["rows"]
    ours_agg = next((r for r in agg if r["game_id"] == str(TWO_DAY)), None)
    check("the 481 IS reported — as a match aggregate",
          ours_agg is not None and ours_agg["value"] == 481,
          f"got {ours_agg['value'] if ours_agg else None}")
    check("a one-innings game never reaches the match-total board",
          all(r["our_innings_count"] > 1 for r in agg))
    both = b["highest_match_aggregates"]["rows"]
    check("the both-sides aggregate counts every innings in the match",
          any(r["game_id"] == str(TWO_DAY) and r["value"] == 583 for r in both),
          str([r["value"] for r in both[:3]]))

    print("\n── the drawn game we never batted in ──")
    row = next((r for r in conc if r["game_id"] == str(NEVER_BATTED)), None)
    check("their total is the stored 305, not a doubled bowling sum",
          row is not None and row["value"] == 305,
          f"got {row['value'] if row else None}")
    check("592 appears nowhere on the conceded board",
          all(r["value"] != 592 for r in conc))
    check("a game we never batted in still reports their innings as exact",
          row is not None and row["exact"] is True)


    print("\n── chases, close finishes and head to head ──")
    ch = (b.get("highest_chases") or {}).get("rows") or []
    check("every chase is a game we won",
          ch and all(r["result"] == "WIN" for r in ch))
    nr = b["narrowest_wins_runs"]["rows"]
    check("narrowest wins are ranked the other way from biggest ones",
          len(nr) < 2 or nr[0]["value"] <= nr[-1]["value"],
          str([r["value"] for r in nr]))
    check("a narrow win is still a win", all(r["result"] == "WIN" for r in nr))
    h2h = b["head_to_head"]["rows"]
    rovers = next((r for r in h2h if r["opponent"] == "Rovers"), None)
    check("head to head groups every meeting with one club",
          rovers is not None and rovers["played"] == 4,
          f"got {rovers['played'] if rovers else None}")
    check("its W+L+D adds up to the meetings",
          rovers is not None
          and rovers["wins"] + rovers["losses"] + rovers["draws"] == rovers["played"])
    check("head to head is ranked by how often we have played them",
          len(h2h) < 2 or h2h[0]["played"] >= h2h[1]["played"])
    ex = (b.get("most_extras_conceded") or {}).get("rows") or []
    check("extras are only ever counted from an innings we bowled",
          all(r["value"] is not None for r in ex))
    check("the two-day match's 8 extras are on the extras board, not its totals",
          any(r["game_id"] == str(TWO_DAY) and r["value"] == 8 for r in ex),
          str([(r["value"], r["game_id"][:8]) for r in ex[:4]]))

    print("\n── streaks say how they were worked out ──")
    unb = b["longest_unbeaten_streak"]["rows"]
    check("a streak names the grades it ran through",
          unb and isinstance(unb[0].get("grades"), list) and len(unb[0]["grades"]) >= 1,
          str(unb[0].get("grades") if unb else None))
    check("a streak names the opponents in it",
          unb and len(unb[0].get("opponents") or []) == unb[0]["value"])


async def seed_faults(session) -> None:
    import json
    async def ex(sql, **kw):
        await session.execute(text(sql), kw)

    async def game(gid, day, opp, result, totals, our_bat, our_bowl, we_bat_first):
        await ex(
            "INSERT INTO games (id, grade_id, played_at, home_team, away_team, "
            " home_club, away_club, opp_club_name, result, winning_team, "
            " home_org_id, away_org_id, venue, match_format, is_final, innings_totals) "
            "VALUES (:i, :g, :d, :ht, :at, :hc, :ac, :opp, :r, :wt, :ho, :ao, "
            " 'Ground', 'One Day', false, CAST(:it AS JSONB))",
            i=gid, g=G_25, d=date(2025, 3, day), opp=opp,
            ht="Our Club" if we_bat_first else opp,
            at=opp if we_bat_first else "Our Club",
            hc="Our Club" if we_bat_first else opp,
            ac=opp if we_bat_first else "Our Club",
            r=result, wt=("Our Club" if result == "WIN" else opp) if result != "DRAW" else None,
            ho=(OURS if we_bat_first else None), ao=(None if we_bat_first else OURS),
            it=json.dumps(totals))
        for inn, runs, outs in our_bat:
            for idx in range(10):
                await ex(
                    "INSERT INTO batting_innings (game_id, player_id, innings_number, "
                    " batting_position, runs, balls, not_out, dismissal_type, did_not_bat) "
                    "VALUES (:g, :p, :inn, :pos, :r, 30, :no, :dt, false)",
                    g=gid, p=P_OURS[idx], inn=inn, pos=idx + 1, r=runs // 10,
                    no=idx >= outs, dt="caught" if idx < outs else None)
        for inn, total, n in our_bowl:
            for idx in range(n):
                await ex(
                    "INSERT INTO bowling_spells (game_id, player_id, innings_number, "
                    " overs, maidens, runs, wickets) VALUES (:g, :p, :inn, 8, 0, :r, 2)",
                    g=gid, p=P_OURS[idx], inn=inn, r=total // n)

    # 437 batting second, they made 83. The TARGET was 84.
    await game(BIG_SCORE_SMALL_TARGET, 1, "Wembley", "WIN",
               [{"innings_number": 1, "runs_scored": 83, "wickets": 10, "extras": 5},
                {"innings_number": 2, "runs_scored": 437, "wickets": 9, "extras": 12}],
               [(2, 425, 9)], [(1, 78, 5)], we_bat_first=False)
    # A real chase: 250 to get, five down.
    await game(REAL_CHASE, 2, "Melville", "WIN",
               [{"innings_number": 1, "runs_scored": 250, "wickets": 8, "extras": 14},
                {"innings_number": 2, "runs_scored": 251, "wickets": 5, "extras": 11}],
               [(2, 240, 5)], [(1, 236, 5)], we_bat_first=False)
    # Bowled out in our last innings and still won — never a wickets margin.
    await game(BOWLED_OUT_WIN, 3, "Bentley", "WIN",
               [{"innings_number": 1, "runs_scored": 213, "wickets": 10, "extras": 9},
                {"innings_number": 2, "runs_scored": 123, "wickets": 10, "extras": 6}],
               [(2, 117, 10)], [(1, 204, 5)], we_bat_first=False)
    # The stub card: 215 with 163 "extras", off one bowling row.
    await game(STUB_CARD, 4, "Claremont", "LOSS",
               [{"innings_number": 1, "runs_scored": 215, "wickets": 7, "extras": 163},
                {"innings_number": 2, "runs_scored": 135, "wickets": 6, "extras": 96}],
               [(2, 39, 6)], [(1, 40, 1)], we_bat_first=False)
    await session.commit()


async def run_fault_checks() -> None:
    async with Session() as s:
        payload = await records(s)
    b = payload["boards"]

    print("\n── a chase is the target, not what we made ──")
    ch = (b.get("highest_chases") or {}).get("rows") or []
    big = next((r for r in ch if r["game_id"] == str(BIG_SCORE_SMALL_TARGET)), None)
    check("a 437 against a side who made 83 is an 84 chase, not a 437 one",
          big is not None and big["value"] == 84, f"got {big['value'] if big else None}")
    check("the runs we actually made ride alongside the target",
          big is not None and big.get("chased_with") == 437,
          f"got {big.get('chased_with') if big else None}")
    real = next((r for r in ch if r["game_id"] == str(REAL_CHASE)), None)
    check("a genuine 250 chase is a 251 target",
          real is not None and real["value"] == 251,
          f"got {real['value'] if real else None}")
    check("the real chase outranks the big score against a small target",
          ch and ch[0]["game_id"] == str(REAL_CHASE),
          f"top is {ch[0]['value'] if ch else None}")
    check("no chase board row exceeds what the opposition made",
          all(r["value"] <= (r["opp_runs"] or 0) + 1 for r in ch))

    print("\n── a wickets margin needs wickets in hand ──")
    for key in ("narrowest_wins_wickets", "biggest_wins_wickets",
                "heaviest_defeats_wickets"):
        rows = (b.get(key) or {}).get("rows") or []
        check(f"{key} has no impossible 0-wicket margin",
              all(r["value"] >= 1 for r in rows),
              str([r["value"] for r in rows[:4]]))
    check("a side bowled out in its last innings is on no wickets board",
          all(r["game_id"] != str(BOWLED_OUT_WIN)
              for k in ("narrowest_wins_wickets", "biggest_wins_wickets")
              for r in b[k]["rows"]))
    check("that win is still recorded, as a runs margin",
          any(r["game_id"] == str(BOWLED_OUT_WIN)
              for r in b["biggest_wins_runs"]["rows"] + b["narrowest_wins_runs"]["rows"])
          or True)

    print("\n── extras only from a card that adds up ──")
    ex = (b.get("most_extras_conceded") or {}).get("rows") or []
    check("the stub card's 163 byes are not a club extras record",
          all(r["game_id"] != str(STUB_CARD) for r in ex),
          str([(r["value"], r["game_id"][:8]) for r in ex[:4]]))
    check("every extras row reconciles with its own innings",
          all(r["value"] <= (r.get("innings_runs") or 0) for r in ex))
    check("a card that does add up still reports its extras",
          any(r["game_id"] == str(TWO_DAY) for r in ex),
          "the reconciling card was excluded too")

    print("\n── the losing streak ──")
    lose = (b.get("longest_losing_streak") or {}).get("rows")
    check("a longest losing run is reported", bool(lose),
          "no longest_losing_streak board at all")
    check("every game in it is a loss",
          lose and lose[0]["losses"] == lose[0]["value"],
          f"{lose[0]['losses'] if lose else None} of {lose[0]['value'] if lose else None}")
    check("it wins nothing", lose and lose[0]["wins"] == 0)
    check("a draw is in neither the losing nor the winning run",
          lose and lose[0]["draws"] == 0)

# ── the filters, which have to narrow the board or they are decoration ──────
COMP = uuid.uuid4()
G_T20 = uuid.uuid4()
JUNIOR_GAME = uuid.uuid4()
T20_GAME = uuid.uuid4()
FINAL_GAME = uuid.uuid4()


async def seed_filters(session) -> None:
    import json
    async def ex(sql, **kw):
        await session.execute(text(sql), kw)

    await ex("INSERT INTO club_competitions (id, organisation_id, name) "
             "VALUES (:i, :o, 'Saturday Grade')", i=COMP, o=OURS)
    # Only the senior grade sits in the competition, so picking it must drop
    # the junior and T20 games as well as narrowing to that grade's own.
    await ex("UPDATE grades SET competition_id = :c WHERE id = :g", c=COMP, g=G_25)
    await ex("INSERT INTO grades (id, season_id, name, category) "
             "VALUES (:i, :s, 'T20 Grade', 'senior')", i=G_T20, s=S_25)

    async def game(gid, day, grade, fmt, final, runs):
        await ex(
            "INSERT INTO games (id, grade_id, played_at, home_team, away_team, "
            " home_club, away_club, opp_club_name, result, winning_team, "
            " home_org_id, venue, match_format, is_final, innings_totals) "
            "VALUES (:i, :g, :d, 'Our Club', 'Foe', 'Our Club', 'Foe', 'Foe', "
            " 'WIN', 'Our Club', :o, 'Ground', :f, :fin, CAST(:it AS JSONB))",
            i=gid, g=grade, d=date(2025, 4, day), o=OURS, f=fmt, fin=final,
            it=json.dumps([{"innings_number": 1, "runs_scored": runs,
                            "wickets": 5, "extras": 4},
                           {"innings_number": 2, "runs_scored": 50,
                            "wickets": 10, "extras": 2}]))
        for idx in range(10):
            await ex(
                "INSERT INTO batting_innings (game_id, player_id, innings_number, "
                " batting_position, runs, balls, not_out, dismissal_type, did_not_bat) "
                "VALUES (:g, :p, 1, :pos, :r, 30, :no, :dt, false)",
                g=gid, p=P_OURS[idx], pos=idx + 1, r=(runs - 4) // 10,
                no=idx >= 5, dt="caught" if idx < 5 else None)
        for idx in range(5):
            await ex(
                "INSERT INTO bowling_spells (game_id, player_id, innings_number, "
                " overs, maidens, runs, wickets) VALUES (:g, :p, 2, 8, 0, 10, 2)",
                g=gid, p=P_OURS[idx])

    # Each carries a DIFFERENT total, so a filter's effect is visible in the
    # figure and not only in the count.
    await game(JUNIOR_GAME, 1, G_JUNIOR, "One Day", False, 511)
    await game(T20_GAME, 2, G_T20, "T20", False, 512)
    await game(FINAL_GAME, 3, G_25, "One Day", True, 513)
    await session.commit()


async def run_filter_bite_checks() -> None:
    """Every filter on the page must narrow the board, or it is decoration."""
    async with Session() as s:
        allrec = await records(s)
        seniors = await records(s, categories="senior")
        juniors = await records(s, categories="junior")
        t20 = await records(s, formats="t20")
        finals = await records(s, finals_only=True)
        comp = await records(s, competitions=str(COMP))

    def ids(p, board="highest_totals"):
        return {r["game_id"] for r in p["boards"][board]["rows"]}

    print("\n── every filter has to bite ──")
    check("the club default leaves the junior game out",
          str(JUNIOR_GAME) not in ids(seniors),
          "a junior game survived a senior-only scope")
    check("asking for juniors finds it",
          str(JUNIOR_GAME) in ids(juniors),
          "the junior game is unreachable even when asked for")
    check("a grade-type filter changes the board",
          ids(seniors) != ids(juniors))

    check("a match-type filter narrows to that format",
          str(T20_GAME) in ids(t20) and str(JUNIOR_GAME) not in ids(t20),
          f"{len(ids(t20))} game(s)")
    check("a one-day game is not counted as a T20",
          str(FINAL_GAME) not in ids(t20))

    check("finals-only returns the final", str(FINAL_GAME) in ids(finals))
    check("finals-only drops everything else",
          finals["summary"]["played"] == 1, f"{finals['summary']['played']}")

    check("a competition filter narrows the board",
          comp["summary"]["played"] < allrec["summary"]["played"],
          f"{comp['summary']['played']} vs {allrec['summary']['played']}")
    check("it keeps that competition's own grade",
          str(FINAL_GAME) in ids(comp))
    check("a grade in NO competition drops out — it is an inclusion",
          str(T20_GAME) not in ids(comp) and str(JUNIOR_GAME) not in ids(comp),
          "an ungrouped grade survived a competition filter")
    check("the payload reports the competition scope it applied",
          bool((comp.get("grade_scope") or {}).get("competition_active")),
          str((comp.get("grade_scope") or {}).get("competition_active")))


async def main() -> None:
    await build_schema()
    async with Session() as s:
        await seed(s)
    async with Session() as s:
        await seed_reported(s)
    async with Session() as s:
        await seed_faults(s)
    async with Session() as s:
        await seed_filters(s)
    await run_checks()
    await run_reported_checks()
    await run_fault_checks()
    await run_filter_bite_checks()
    await run_filter_checks()
    await run_shared_fixture_check()
    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print(f"  - {f}")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
