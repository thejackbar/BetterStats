"""A season-totals import and the same matches typed in as games are counted once.

Reported by Hamilton Veterans (Oct 2026): 26 player-seasons in 2016/17 to 2022/23 read
EXACTLY double (games, innings, runs, overs, wickets). A season-by-season sheet was
committed in August; every game was typed in from the same records in September and
October. The reconciler worked out what the sheet adds by subtracting Cricket
Australia's record only, never the club's own games, so both counted. Seasons with
games and no runs (2010/11 to 2017/18) read "additional games with no detail" beside
the typed ones.

Runs the SHIPPED `reconcile_imported_totals` over the app's own view DDL
(`superseded_ddl.STATEMENTS`), the shipped `_refresh_import_deltas` the games routes call,
and the pure helpers the preview shares with the commit.

THE CONTROL RUN is this file against the previous commit. `with_typed`,
`fetch_typed_by_player` and `_refresh_import_deltas` do not exist there, so they are read
through `getattr` and report instead of crashing: the totals checks fail on exactly the
doubling (14 games and 348 runs where there are 7 and 174).

Run:
  DATABASE_URL=postgresql+asyncpg://postgres:pw@127.0.0.1:5432/bstest \
  python verification/verify_import_typed_games.py
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
from app.models.db import ImportBatch, ImportedStat, async_session_maker
from app.routers import manual_entries
from app.services import import_reconcile as recon
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


ORG = uuid.UUID("c1000000-0000-0000-0000-000000000001")
S18, S11, S13, S23 = (uuid.UUID(f"c2000000-0000-0000-0000-00000000000{n}") for n in (1, 2, 3, 4))
G_MIXED, G_BORDER, G_MIXED11, G_BORDER13, G_MIXED23 = (
    uuid.UUID(f"c3000000-0000-0000-0000-00000000000{n}") for n in (1, 2, 3, 4, 5))
P_FULL, P_SHORT, P_ONLY, P_OUT, P_LATE = (
    uuid.UUID(f"c4000000-0000-0000-0000-00000000000{n}") for n in (1, 2, 3, 4, 5))


async def ex(session, sql, **kw):
    await session.execute(text(sql), kw)


async def type_games(session, player, season, grade, n, runs_each, start=date(2019, 1, 5)):
    """`n` hand-entered games for a player, each a single batting innings."""
    for i in range(n):
        mg = uuid.uuid4()
        await ex(session,
                 "INSERT INTO manual_games (id, organisation_id, season_id, grade_id, played_at, "
                 " match_format) VALUES (:i, :o, :s, :g, :d, 'One Day')",
                 i=mg, o=ORG, s=season, g=grade, d=date.fromordinal(start.toordinal() + 7 * i))
        await ex(session,
                 "INSERT INTO manual_batting_innings (manual_game_id, player_id, innings_number, "
                 " batting_position, runs, balls, not_out, did_not_bat) "
                 "VALUES (:g, :p, 1, 3, :r, 30, false, false)", g=mg, p=player, r=runs_each)


def import_row(batch, player, season, label, games, runs, innings):
    return ImportedStat(organisation_id=ORG, import_batch_id=batch, player_id=player, scope="season",
                        season_id=season, season_label=label, grade_label=GRADE_LABELS[label],
                        games_played=games, batting_innings=innings, batting_runs=runs,
                        is_prior_bucket=False)


GRADE_LABELS = {"2018/19 mixed": "Over 60 Mixed", "2018/19 border": "Border Cup",
                "2011/12": "Over 60 Mixed", "2013/14": "Border Cup", "2013/14b": "Border Cup"}


async def totals(player):
    async with base.Session() as s:
        r = (await s.execute(text(
            "SELECT COALESCE(SUM(matches), 0), COALESCE(SUM(batting_innings), 0), COALESCE(SUM(runs), 0) "
            "FROM v_effective_player_season_stats WHERE player_id = :p"), {"p": player})).one()
    return tuple(int(x) for x in r)


async def main() -> None:
    await base.build_schema()
    async with base.engine.begin() as conn:
        for stmt in superseded_ddl.STATEMENTS:
            await conn.execute(text(stmt))
    async with base.Session() as s:
        await ex(s, "INSERT INTO organisations (id, name, slug, is_active) "
                    "VALUES (:i, 'Hamilton Veterans Cricket Club', 'hvcc', true)", i=ORG)
        for sid, nm, yr in ((S18, "Summer 2018/19", 2018), (S11, "Summer 2011/12", 2011),
                            (S13, "Summer 2013/14", 2013), (S23, "Summer 2023/24", 2023)):
            await ex(s, "INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, :n, :y)",
                     i=sid, o=ORG, n=nm, y=yr)
        for gid, sid, nm in ((G_MIXED, S18, "Over 60 Mixed"), (G_BORDER, S18, "Border Cup"),
                             (G_MIXED11, S11, "Over 60 Mixed"), (G_BORDER13, S13, "Border Cup"),
                             (G_MIXED23, S23, "Over 60 Mixed")):
            await ex(s, "INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
                        "VALUES (:i, :s, :n, :g, 'senior', ARRAY['senior'])", i=gid, s=sid, n=nm, g=str(gid))
        for pid, nm in ((P_FULL, "Full, Fred"), (P_SHORT, "Short, Sam"), (P_ONLY, "Only, Olly"),
                        (P_OUT, "Out, Ozzy"), (P_LATE, "Late, Larry")):
            await ex(s, "INSERT INTO players (id, organisation_id, name, grassroots_id, status) "
                        "VALUES (:i, :o, :n, :g, 'active')", i=pid, o=ORG, n=nm, g=str(pid))
        batch = uuid.uuid4()
        s.add(ImportBatch(id=batch, organisation_id=ORG, status="committed"))
        await s.flush()
        # FULL: the sheet and the typed games hold the very same 7 games.
        s.add(import_row(batch, P_FULL, S18, "2018/19 mixed", 3, 78, 3))
        s.add(import_row(batch, P_FULL, S18, "2018/19 border", 4, 96, 4))
        await type_games(s, P_FULL, S18, G_MIXED, 3, 26)
        await type_games(s, P_FULL, S18, G_BORDER, 4, 24, start=date(2019, 3, 2))
        # SHORT: the sheet says 3 games for 11 runs, the club typed one of them (11 runs).
        s.add(import_row(batch, P_SHORT, S11, "2011/12", 3, 11, 1))
        await type_games(s, P_SHORT, S11, G_MIXED11, 1, 11, start=date(2012, 1, 7))
        # ONLY: a games-only line nobody typed anything for.
        s.add(import_row(batch, P_ONLY, S13, "2013/14", 1, 0, 0))
        # OUT: two sheet games in 2013/14 nobody typed; 5 games typed in a season the sheet never names.
        s.add(import_row(batch, P_OUT, S13, "2013/14b", 2, 0, 0))
        await type_games(s, P_OUT, S23, G_MIXED23, 5, 10, start=date(2024, 1, 6))
        # LATE: the sheet first; the games are typed afterwards (the refresh case).
        s.add(import_row(batch, P_LATE, S18, "2018/19 mixed", 2, 40, 2))
        await s.commit()

    await recon.reconcile_imported_totals(str(ORG))

    print("\n-- the club's own games are taken off what the sheet adds --")
    full = await totals(P_FULL)
    check("FULL: 7 games, not 14", full[0] == 7, f"{full}")
    check("FULL: 174 runs, not 348", full[2] == 174, f"{full}")
    check("FULL: 7 innings, not 14", full[1] == 7, f"{full}")

    print("\n-- what the sheet holds beyond the games stays, and is not made up --")
    short = await totals(P_SHORT)
    check("SHORT: the two games nobody typed stay (3 in all), not 4", short[0] == 3, f"{short}")
    check("SHORT: runs are the typed 11, not 22", short[2] == 11, f"{short}")
    only = await totals(P_ONLY)
    check("ONLY: a games-only line nobody typed for is kept (1 game)", only[0] == 1, f"{only}")
    out = await totals(P_OUT)
    check("OUT: games typed in a season the sheet never names do not absorb the sheet's (2 + 5)",
          out[0] == 7, f"{out}")

    print("\n-- typing the games AFTER the import moves the figures (the refresh) --")
    late_before = await totals(P_LATE)
    check("LATE before: the sheet alone gives 2 games", late_before[0] == 2, f"{late_before}")
    async with base.Session() as s:
        await type_games(s, P_LATE, S18, G_MIXED, 2, 20, start=date(2019, 5, 4))
        await s.commit()
    stale = await totals(P_LATE)
    check("LATE: until something rebuilds the import, the sheet and the games add (4)", stale[0] == 4, f"{stale}")
    refresh = getattr(manual_entries, "_refresh_import_deltas", None)
    async with base.Session() as s:
        if refresh:
            await refresh(s, ORG)
    late_after = await totals(P_LATE)
    check("LATE: the games routes' refresh brings it back to 2", refresh is not None and late_after[0] == 2,
          f"{late_after} (refresh {'present' if refresh else 'ABSENT'})")
    check("LATE: and to the typed 40 runs", late_after[2] == 40, f"{late_after}")

    print("\n-- the pure helpers the preview shares --")
    with_typed = getattr(recon, "with_typed", None)
    a, b = uuid.uuid4(), uuid.uuid4()
    gr = recon._blank()
    typed = {a: recon.accumulate(None, {"matches": 5, "runs": 50})}
    if with_typed:
        t, cov = with_typed(gr, set(), [(a, {"matches": 5})], typed, {a: 2018})
        check("a typed season in the sheet is held and covered", t["matches"] == 5 and a in cov, f"{t['matches']} {cov}")
        t2, cov2 = with_typed(gr, set(), [(b, {"matches": 5})], typed, {a: 2018, b: 2019})
        check("a typed season the sheet never names is not held", t2["matches"] == 0 and a not in cov2,
              f"{t2['matches']} {cov2}")
        t3, _ = with_typed(gr, set(), [(a, {"matches": 5})], typed, {a: 2018})
        check("the caller's own totals are not mutated", gr["matches"] == 0 and t3 is not gr, f"{gr['matches']}")
        club = {**recon._blank(), "matches": 7, "runs": 87}
        held, cov3 = with_typed(gr, set(), [(a, {"matches": 7})], {a: recon.accumulate(None, {"matches": 7, "runs": 87})}, {a: 2018})
        summary = recon.summarize(club, held, [(a, {"matches": 7, "runs": 87})], cov3)
        check("summarize (the preview) reads the sheet as already held: final 7, not 14",
              summary["final"]["matches"] == 7 and summary["season_delta_count"] == 0,
              f"{summary['final']['matches']} / {summary['season_delta_count']}")
    else:
        check("with_typed exists", False, "ABSENT")

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        for f in FAILURES:
            print("  -", f)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
