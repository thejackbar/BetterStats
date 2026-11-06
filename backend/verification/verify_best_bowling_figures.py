"""Best bowling reads as `5/18`, not as a bare "5 wickets", for hand-entered bowling.

Reported by Hamilton Veterans (Oct 2026): on a profile the best bowling showed only
a wicket count ("5 wickets") where it should read wickets and runs. The profile
prints `best_bowling_figures` and falls back to the bare count only when that string
is missing. `v_effective_player_season_stats` hard-coded `NULL::text` for it in two
branches, the roll-up of hand-entered games (`manual_game`) and the roll-up of the
synced games of a re-sourced season (`api_scorecard`), so a club whose bowling is
hand-entered NEVER had figures, whatever it typed.

Second half: the career reader chose the figures from the rows that HAD figures, so a
career best of 6 wickets typed as an adjustment (no figures) printed the figures of
a 5-wicket season beside it. It must take them from the row that holds the best
wicket count, or print none.

Runs the SHIPPED `get_career_bowling` over the app's own view DDL
(`superseded_ddl.STATEMENTS`, which the lifespan re-applies on every boot).

THE CONTROL RUN is this file against the previous commit: it must FAIL on the
reported behaviour (no figures on either branch) and not crash; every new name is
read through `.get`.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres:pw@127.0.0.1:5432/bstest \
  python verification/verify_best_bowling_figures.py
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

import verify_records_timing as base
from app.services import aggregations as agg
from app.services import superseded_ddl

PASS = FAIL = 0
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        FAILURES.append(label + (f" -- {detail}" if detail else ""))
        print(f"  FAIL {label}" + (f" -- {detail}" if detail else ""))


BOWLER = uuid.UUID("a1000000-0000-0000-0000-000000000001")      # hand-entered 3/20, 5/18, 5/25
TRAP = uuid.UUID("a1000000-0000-0000-0000-000000000002")        # 5/18 by hand, 6 wickets as an adjustment, no figures
TYPED = uuid.UUID("a1000000-0000-0000-0000-000000000003")       # 5/18 by hand, 6-12 typed as an adjustment
WICKETLESS = uuid.UUID("a1000000-0000-0000-0000-000000000004")  # bowled, took none
RESOURCED = uuid.UUID("a1000000-0000-0000-0000-000000000005")   # synced games of a re-sourced season
PORTLAND = uuid.UUID("a1000000-0000-0000-0000-000000000006")    # on the other side of a hand-entered game
SEASON_B = uuid.UUID("a2000000-0000-0000-0000-000000000001")
GRADE_B = uuid.UUID("a2000000-0000-0000-0000-000000000002")
SEASON_C = uuid.UUID("a2000000-0000-0000-0000-000000000003")


async def seed_extra(session) -> None:
    async def ex(sql, **kw):
        await session.execute(text(sql), kw)

    await ex("INSERT INTO seasons (id, organisation_id, name, year) "
             "VALUES (:i, :o, 'Summer 2023/24', 2023)", i=SEASON_B, o=base.ORG)
    await ex("INSERT INTO seasons (id, organisation_id, name, year, import_authoritative) "
             "VALUES (:i, :o, 'Summer 2022/23', 2022, true)", i=SEASON_C, o=base.ORG)
    await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
             "VALUES (:i, :s, '1st Grade', :g, 'senior', ARRAY['senior'])",
             i=GRADE_B, s=SEASON_C, g=str(GRADE_B))
    for pid, nm in ((BOWLER, "Bowler, Ben"), (TRAP, "Trap, Tom"), (TYPED, "Typed, Tim"),
                    (WICKETLESS, "Nowicket, Nick"), (RESOURCED, "Resourced, Rob"),
                    (PORTLAND, "Portland, Pat")):
        await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) "
                 "VALUES (:i, :o, :n, :g, 'active')", i=pid, o=base.ORG, n=nm, g=str(pid))

    async def manual_game(day: int, spells: list[tuple[uuid.UUID, int, int]], inn: int = 1) -> uuid.UUID:
        mg = uuid.uuid4()
        await ex("INSERT INTO manual_games (id, organisation_id, season_id, grade_id, played_at, "
                 " result, match_format) VALUES (:i, :o, :s, :g, :d, 'WIN', 'One Day')",
                 i=mg, o=base.ORG, s=base.SEASON, g=base.GRADE, d=date(2025, 2, day))
        for pid, wkts, runs in spells:
            await ex("INSERT INTO manual_bowling_spells (manual_game_id, player_id, innings_number, "
                     " overs, maidens, runs, wickets) VALUES (:g, :p, :n, 6.0, 0, :r, :w)",
                     g=mg, p=pid, n=inn, r=runs, w=wkts)
        return mg

    await manual_game(1, [(BOWLER, 3, 20), (TRAP, 5, 18), (TYPED, 5, 18), (WICKETLESS, 0, 20)])
    await manual_game(2, [(BOWLER, 5, 18)])
    await manual_game(3, [(BOWLER, 5, 25)])

    # A typed adjustment for another season: 6 wickets and NO figures for TRAP; 6-12 for TYPED.
    for pid, figs in ((TRAP, None), (TYPED, "6-12")):
        await ex("INSERT INTO manual_season_adjustments (organisation_id, player_id, season_id, "
                 " bowling_best_wickets, bowling_best_figures, bowling_wickets, bowling_innings) "
                 "VALUES (:o, :p, :s, 6, :f, 6, 1)", o=base.ORG, p=pid, s=SEASON_B, f=figs)


async def seed_resourced(session) -> None:
    async def ex(sql, **kw):
        await session.execute(text(sql), kw)

    for n, (wk, rn) in enumerate(((4, 22), (4, 15), (2, 9))):
        gid = uuid.uuid4()
        await ex("INSERT INTO games (id, grade_id, played_at, result, home_org_id, away_org_id, "
                 " match_format, status) VALUES (:i, :g, :d, 'WIN', :o, :x, 'One Day', 'COMPLETED')",
                 i=gid, g=GRADE_B, d=date(2023, 1, 7 + n), o=base.ORG, x=base.OPPONENT)
        await ex("INSERT INTO bowling_spells (game_id, player_id, overs, maidens, runs, wickets) "
                 "VALUES (:g, :p, 6.0, 0, :r, :w)", g=gid, p=RESOURCED, r=rn, w=wk)


async def view_rows(session, pid: uuid.UUID):
    rows = (await session.execute(text(
        "SELECT source, best_bowling_wickets, best_bowling_figures, matches "
        "FROM v_effective_player_season_stats WHERE player_id = :p"), {"p": pid})).mappings().all()
    return [dict(r) for r in rows]


def by_source(rows, source):
    return next((r for r in rows if r.get("source") == source), {})


async def main() -> None:
    await base.build_schema()
    async with base.engine.begin() as conn:
        for stmt in superseded_ddl.STATEMENTS:
            await conn.execute(text(stmt))
    async with base.Session() as session:
        await base.seed(session)
        await seed_extra(session)
        await seed_resourced(session)
        # A hand-entered game with a player from BOTH sides on the card (the Portland v Hamilton
        # one-off): innings 1 Hamilton bat, innings 2 Portland bat. Both are club players here.
        both = uuid.uuid4()
        await session.execute(text(
            "INSERT INTO manual_games (id, organisation_id, season_id, grade_id, played_at, result, "
            " match_format) VALUES (:i, :o, :s, :g, DATE '2025-02-20', 'WIN', 'One Day')"),
            {"i": both, "o": base.ORG, "s": base.SEASON, "g": base.GRADE})
        for pid, inn, runs in ((BOWLER, 1, 31), (PORTLAND, 2, 44)):
            await session.execute(text(
                "INSERT INTO manual_batting_innings (manual_game_id, player_id, innings_number, "
                " batting_position, runs, balls, not_out, did_not_bat) "
                "VALUES (:g, :p, :n, 1, :r, 40, false, false)"), {"g": both, "p": pid, "n": inn, "r": runs})
        await session.commit()

    async with base.Session() as session:
        print("\n-- hand-entered spells carry their best figures --")
        rows = await view_rows(session, BOWLER)
        manual = by_source(rows, "manual_game")
        check("the manual roll-up holds the best spell's wickets", manual.get("best_bowling_wickets") == 5,
              f"{manual}")
        check("and its figures, fewest runs winning a tie on wickets (5-18, not 5-25)",
              manual.get("best_bowling_figures") == "5-18", f"{manual.get('best_bowling_figures')!r}")
        w = by_source(await view_rows(session, WICKETLESS), "manual_game")
        check("a bowler who took no wicket has a row to speak of",
              w.get("best_bowling_wickets") == 0, f"{w}")
        check("and gets no figures (0-20 is not a best)", w.get("best_bowling_figures") is None,
              f"{w.get('best_bowling_figures')!r}")

        print("\n-- the synced games of a re-sourced season carry them too --")
        rs = by_source(await view_rows(session, RESOURCED), "api_scorecard")
        check("the re-sourced roll-up holds 4 wickets", rs.get("best_bowling_wickets") == 4, f"{rs}")
        check("and the better of the two 4-wicket spells (4-15)",
              rs.get("best_bowling_figures") == "4-15", f"{rs.get('best_bowling_figures')!r}")

        print("\n-- the career reader (what the profile prints) --")
        career = await agg.get_career_bowling(session, str(BOWLER)) or {}
        check("career best figures are 5-18", career.get("best_bowling_figures") == "5-18",
              f"{career.get('best_bowling_figures')!r} (wickets {career.get('best_figures_wickets')!r})")
        check("career best wickets are 5", career.get("best_figures_wickets") == 5)

        trap = await agg.get_career_bowling(session, str(TRAP)) or {}
        check("TRAP: the best is the typed 6 wickets", trap.get("best_figures_wickets") == 6,
              f"{trap.get('best_figures_wickets')!r}")
        check("TRAP: figures of a 5-wicket spell are NOT printed beside a best of 6",
              trap.get("best_bowling_figures") is None, f"{trap.get('best_bowling_figures')!r}")
        typed = await agg.get_career_bowling(session, str(TYPED)) or {}
        check("TYPED: figures typed with the 6 wickets are the ones printed",
              typed.get("best_bowling_figures") == "6-12", f"{typed.get('best_bowling_figures')!r}")
        none = await agg.get_career_bowling(session, str(WICKETLESS)) or {}
        check("a bowler with no wicket prints no figures", none.get("best_bowling_figures") is None,
              f"{none.get('best_bowling_figures')!r}")

        print("\n-- a hand-entered game with players from both sides counts for both --")
        for label, pid, runs in (("Hamilton batter", BOWLER, 31), ("Portland batter", PORTLAND, 44)):
            row = by_source(await view_rows(session, pid), "manual_game")
            check(f"{label} has the match", (row.get("matches") or 0) >= 1, f"{row}")
        pc = await agg.get_career_batting(session, str(PORTLAND)) or {}
        check("Portland batter's runs are in their career", pc.get("total_runs") == 44, f"{pc.get('total_runs')!r}")

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        for f in FAILURES:
            print("  -", f)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
