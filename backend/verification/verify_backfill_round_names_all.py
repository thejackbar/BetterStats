"""The all-clubs backfill: shared grades read once, a call budget, resumable, honours written. Real Postgres.

`backfill_round_names all` fills `games.round_name` for every club whose finals have none and, with
`--premierships`, writes the honours. A CA grade is competition-wide, so clubs in the same grade share
one match list; the run must read each distinct grade ONCE, stay inside `--max-grades`, finish whole clubs
only, leave a club whose names are all stored alone, and pick up where it stopped when run again.

  A  grand final in grade X (shared with B), win
  B  semi final in grade X (the same grade guid, its own grade row)
  C  grand final in grade Y, win
  D  already named (Grand Final stored): not a candidate, not touched, no CA call for its grade
  E  grade W, for which CA returns nothing (a blip): not marked done, tried again next run

CONTROL MODE. Run against a commit without the script's `Fetcher`, every check on the budget and the
shared read fails (nothing crashes: the module is read through getattr).

Run:  DATABASE_URL=postgresql+asyncpg://root@/bfn_all?host=/var/run/postgresql \
      python verification/verify_backfill_round_names_all.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text

import verify_reread_incomplete_game as h
from app.services import grassroots_scores_client as gr
from app.scripts import backfill_round_names as bfn

check, Session = h.check, h.Session
u = uuid.uuid4

ORGS = {k: u() for k in "ABCDE"}
GUID = {"X": str(u()), "Y": str(u()), "Z": str(u()), "W": str(u())}
G = {k: u() for k in ("GF_A", "SEMI_B", "GF_C", "GF_D", "GF_E")}
SEASON = {k: u() for k in "ABCDE"}
GRADE = {k: u() for k in "ABCDE"}
PL = {k: [u(), u()] for k in "ABCDE"}
RAW = {"A": GUID["X"], "B": GUID["X"], "C": GUID["Y"], "D": GUID["Z"], "E": GUID["W"]}
GAME_OF = {"A": "GF_A", "B": "SEMI_B", "C": "GF_C", "D": "GF_D", "E": "GF_E"}
LISTING = {GUID["X"]: [(G["GF_A"], "Grand Final"), (G["SEMI_B"], "Semi Final")],
           GUID["Y"]: [(G["GF_C"], "Grand Final")], GUID["Z"]: [(G["GF_D"], "Grand Final")],
           GUID["W"]: []}
CALLS: list[str] = []


async def seed() -> None:
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)
        for k, oid in ORGS.items():
            await ex("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i,:n,:s,true)",
                     i=oid, n=f"Club {k}", s=f"club-{k.lower()}")
            await ex("INSERT INTO seasons (id, organisation_id, name, year, grassroots_id) VALUES (:i,:o,'2025/26',2025,:g)",
                     i=SEASON[k], o=oid, g=str(SEASON[k]))
            await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
                     "VALUES (:i,:s,'1st Grade',:g,'senior',ARRAY['senior'])", i=GRADE[k], s=SEASON[k], g=RAW[k])
            for n, pid in enumerate(PL[k]):
                await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) VALUES (:i,:o,:n,:g,'active')",
                         i=pid, o=oid, n=f"{k} Player {n}", g=str(pid))
        for k, gname in GAME_OF.items():
            final = True
            rn = "Grand Final" if k == "D" else None
            ours = f"Club {k} 1st"
            await ex("""INSERT INTO games (id, grade_id, played_at, home_team, away_team, home_org_id, away_org_id,
                                           winning_team, is_final, status, round_name)
                        VALUES (:g,:gr,:d,:h,'Them 1st',:o,NULL,:w,:f,'COMPLETED',:rn)""",
                     g=G[gname], gr=GRADE[k], d=h.TODAY - timedelta(days=400), h=ours, o=ORGS[k],
                     w=ours if k != "B" else None, f=final, rn=rn)
            for pid in PL[k]:
                await ex("INSERT INTO game_appearances (game_id, player_id, team_name) VALUES (:g,:p,:t)",
                         g=G[gname], p=pid, t=ours)
        # B also appears on A's grand final as the opposition, the way a shared fixture is stored.
        await ex("UPDATE games SET away_org_id = :b WHERE id = :g", b=ORGS["B"], g=G["GF_A"])
        await s.commit()


async def names() -> dict:
    async with Session() as s:
        return {r[0]: r[1] for r in (await s.execute(text("SELECT id, round_name FROM games"))).all()}


async def honours(org) -> int:
    async with Session() as s:
        return (await s.execute(text("SELECT count(*) FROM player_achievements WHERE org_id = :o AND auto_created"),
                                {"o": org})).scalar()


async def main() -> None:
    await h.build_schema()
    async with h.engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS player_achievements (
                id SERIAL PRIMARY KEY, org_id UUID NOT NULL, player_id UUID, player_name TEXT NOT NULL,
                season TEXT, category TEXT NOT NULL, subcategory TEXT, achievement TEXT NOT NULL,
                detail TEXT, created_at TIMESTAMPTZ DEFAULT NOW())"""))
        await conn.execute(text("ALTER TABLE player_achievements ADD COLUMN IF NOT EXISTS season_end TEXT"))
        await conn.execute(text("ALTER TABLE player_achievements ADD COLUMN IF NOT EXISTS import_batch_id UUID"))
        await conn.execute(text("ALTER TABLE player_achievements ADD COLUMN IF NOT EXISTS club_role_id UUID"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID NOT NULL,
                canonical_name TEXT NOT NULL, alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)"""))
        from app.services.premierships_ddl import STATEMENTS
        for stmt in STATEMENTS:
            await conn.execute(text(stmt))
    await seed()

    async def fake_matches(grade_guid, *a, **k):
        CALLS.append(grade_guid)
        await asyncio.sleep(0.05)   # latency, so concurrent readers genuinely overlap
        return [{"id": str(m), "round": {"name": r}} for m, r in LISTING.get(grade_guid, [])]
    gr.get_grade_matches = fake_matches
    bfn.async_session_maker = Session

    Fetcher = getattr(bfn, "Fetcher", None)
    check("the script has the shared, budgeted fetcher", Fetcher is not None)
    if Fetcher is None:
        print(f"\n{h.PASS} passed, {h.FAIL} failed"); sys.exit(1)

    print("\n-- WHO IS A CANDIDATE --")
    async with Session() as s:
        cand = {c["name"] for c in await bfn._clubs(s, "all")}
    check("clubs with an unnamed final: A, B, C and E", cand == {"Club A", "Club B", "Club C", "Club E"}, str(cand))
    check("D, already named, is not a candidate (and could have been: a named final is not a candidate by design)",
          "Club D" not in cand)

    print("\n-- DRY RUN --")
    await bfn.run("all", apply=False, with_premierships=False, max_grades=400, pause=0)
    after_dry = await names()
    check("writes nothing", not any(after_dry.get(G[g]) for g in ("GF_A", "SEMI_B", "GF_C", "GF_E")))
    check("reads grade X once for A and B together, and Y and W once each",
          sorted(CALLS) == sorted([GUID["X"], GUID["Y"], GUID["W"]]), str(CALLS))
    check("never reads D's grade", GUID["Z"] not in CALLS)

    print("\n-- APPLY WITH A BUDGET OF ONE GRADE --")
    CALLS.clear()
    await bfn.run("all", apply=True, with_premierships=True, max_grades=1, pause=0)
    n = await names()
    check("A and B (one shared grade) are done, whole", n[G["GF_A"]] == "Grand Final" and n[G["SEMI_B"]] == "Semi Final")
    check("C is not reached: the run stopped before it would exceed the budget", n[G["GF_C"]] is None)
    check("one CA call was made", CALLS == [GUID["X"]], str(CALLS))
    check("A's grand final win gave its players the honour", await honours(ORGS["A"]) == 2, str(await honours(ORGS["A"])))
    check("a semi final earns B nothing", await honours(ORGS["B"]) == 0)
    check("D's stored name was not touched", n[G["GF_D"]] == "Grand Final")

    print("\n-- RUN AGAIN: IT CARRIES ON --")
    CALLS.clear()
    await bfn.run("all", apply=True, with_premierships=True, max_grades=400, pause=0)
    n = await names()
    check("C is named now", n[G["GF_C"]] == "Grand Final")
    check("C's players have the honour", await honours(ORGS["C"]) == 2, str(await honours(ORGS["C"])))
    check("A and B's grade is not read again", GUID["X"] not in CALLS, str(CALLS))
    check("E's grade, which returned nothing, is tried again", GUID["W"] in CALLS)
    check("and E's final stays unnamed (nothing was invented)", n[G["GF_E"]] is None)
    check("A's honours were not doubled", await honours(ORGS["A"]) == 2)

    print("\n-- RUN A THIRD TIME --")
    CALLS.clear()
    await bfn.run("all", apply=True, with_premierships=True, max_grades=400, pause=0)
    check("only the failing grade is asked for again", CALLS == [GUID["W"]], str(CALLS))
    check("no honour changes", [await honours(ORGS[k]) for k in "ABC"] == [2, 0, 2])

    print("\n-- CONCURRENT READERS --")
    # Re-arm: clear names, honours and the exclusion of E's blip, then read three grades with three workers.
    async with Session() as s:
        await s.execute(text("UPDATE games SET round_name = NULL WHERE id <> :d"), {"d": G["GF_D"]})
        await s.execute(text("DELETE FROM player_achievements"))
        await s.commit()
    CALLS.clear()
    peak = {"now": 0, "max": 0}
    inner = fake_matches

    async def counting(grade_guid, *a, **k):
        peak["now"] += 1
        peak["max"] = max(peak["max"], peak["now"])
        try:
            return await inner(grade_guid, *a, **k)
        finally:
            peak["now"] -= 1
    gr.get_grade_matches = counting
    f = Fetcher(400, 0, 3)
    await f.read_all([{"guid": g, "grade_name": "x", "season_name": "y"} for g in (GUID["X"], GUID["Y"], GUID["W"], GUID["X"])])
    check("three grades were read at the same time", peak["max"] == 3, str(peak))
    check("a grade asked for twice (X) is still one call", sorted(CALLS) == sorted([GUID["X"], GUID["Y"], GUID["W"]]), str(CALLS))
    check("and every answer is there for whoever asked", f.names.get(str(G["GF_A"])) == "Grand Final"
          and f.names.get(str(G["GF_C"])) == "Grand Final")
    peak.update(now=0, max=0)
    f1 = Fetcher(400, 0, 1)
    await f1.read_all([{"guid": g, "grade_name": "x", "season_name": "y"} for g in (GUID["X"], GUID["Y"], GUID["W"])])
    check("--concurrency 1 reads one at a time", peak["max"] == 1, str(peak))
    f9 = Fetcher(400, 0, 99)
    check("an absurd --concurrency is capped at the CA client's six", f9._slots._value == 6, str(f9._slots._value))

    print(f"\n{h.PASS} passed, {h.FAIL} failed")
    await h.engine.dispose()
    sys.exit(1 if h.FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
