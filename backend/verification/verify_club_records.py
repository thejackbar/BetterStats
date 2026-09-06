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
                finals_only=False, categories="all", formats=None)
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
    check("highest total is the club's own 300, not both sides added together",
          hi["rows"] and hi["rows"][0]["value"] == 300,
          f"got {hi['rows'][0]['value'] if hi['rows'] else None}")
    check("the record total is reported as exact",
          hi["rows"] and hi["rows"][0]["exact"] is True)
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
    check("biggest win by runs is 220", wr["rows"] and wr["rows"][0]["value"] == 220,
          f"got {wr['rows'][0]['value'] if wr['rows'] else None}")
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
    check("longest win streak is 3", win["rows"] and win["rows"][0]["value"] == 3,
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
    check("summary played equals the seeded games", summ["played"] == len(GAMES),
          f"{summ['played']} vs {len(GAMES)}")
    check("summary W+L+D reconciles with played",
          summ["wins"] + summ["losses"] + summ["draws"] == summ["played"])
    cov = payload["coverage"]
    check("coverage counts exact and approximate separately",
          cov["exact_totals"] + cov["approximate_totals"] == cov["games_with_a_total"])
    check("coverage reports the two exact games", cov["exact_totals"] == 2,
          f"{cov['exact_totals']}")
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
    check("the opposition's 500 never becomes the club's highest total",
          rows[0]["value"] != 650 and rows[0]["value"] <= 300,
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
    check("finals-only returns nothing when the club has played no final",
          finals["summary"]["played"] == 0,
          f"{finals['summary']['played']}")
    check("the payload reports the grade scope it applied",
          "grade_scope" in all_seasons and "categories" in all_seasons["grade_scope"])


async def main() -> None:
    await build_schema()
    async with Session() as s:
        await seed(s)
    await run_checks()
    await run_filter_checks()
    await run_shared_fixture_check()
    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print(f"  - {f}")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
