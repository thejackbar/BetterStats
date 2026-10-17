"""Verification for `app.scripts.diagnose_partnership`, against a real Postgres.

A club reported two big stands (204 and 153) that the match page shows but the
records page does not. The diagnostic has to name WHY a stand is dropped, so the
check that matters is that its verdict agrees with the SHIPPED records route
for every stand: INCLUDED when the route lists it, DROPPED when it does not.
Seeded stands, each differing in one thing from the control:

  control   both batters have a player row in the club      -> on the board
  name-only batter 2 has no player id, only a stored name   -> dropped
  opp-innings stored as the opposition's innings            -> dropped
  other-org batter 2's player row belongs to another club   -> dropped

Run:  DATABASE_URL=postgresql+asyncpg://root@/diagpart?host=/var/run/postgresql \
      python verification/verify_diagnose_partnership.py
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
import uuid
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import verify_club_records as base   # its engine, schema and views; main() is guarded
from app.scripts import diagnose_partnership as diag
from app.routers.records import get_records

engine = base.engine
Session = base.Session
OURS, THEIRS = base.OURS, base.THEIRS

S = uuid.uuid4(); G = uuid.uuid4()
ME, MATE, GHOST_OTHER = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
GAMES = {k: uuid.uuid4() for k in ("control", "nameonly", "oppinn", "otherorg")}
RUNS = {"control": 204, "nameonly": 153, "oppinn": 177, "otherorg": 131}


async def seed() -> None:
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)
        await ex("INSERT INTO organisations (id, name, is_active) VALUES (:i, 'Our Club', true)", i=OURS)
        await ex("INSERT INTO organisations (id, name, is_active) VALUES (:i, 'Their Club', true)", i=THEIRS)
        await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, 'Summer 2017/18', 2017)",
                 i=S, o=OURS)
        await ex("INSERT INTO grades (id, season_id, name, category) VALUES (:i, :s, 'Grade D', 'senior')",
                 i=G, s=S)
        for pid, org, nm in ((ME, OURS, "Me"), (MATE, OURS, "Mate"), (GHOST_OTHER, THEIRS, "Other Club Man")):
            await ex("INSERT INTO players (id, organisation_id, name) VALUES (:i, :o, :n)", i=pid, o=org, n=nm)
        for n, gid in GAMES.items():
            await ex(
                "INSERT INTO games (id, grade_id, played_at, home_team, away_team, home_club, away_club, "
                " opp_club_name, result, home_org_id, away_org_id, venue, match_format, is_final) "
                "VALUES (:i, :g, :d, 'Our Club', 'Opp', 'Our Club', 'Opp', 'Opp', 'WIN', :ho, NULL, 'Oval', "
                " 'One Day', false)",
                i=gid, g=G, d=date(2017, 12, 16), ho=OURS)
        stands = {
            "control":  dict(b1=ME, b2=MATE, n2=None, club=True),
            "nameonly": dict(b1=ME, b2=None, n2="R Ward", club=True),
            "oppinn":   dict(b1=ME, b2=MATE, n2=None, club=False),
            "otherorg": dict(b1=ME, b2=GHOST_OTHER, n2=None, club=True),
        }
        for n, st in stands.items():
            await ex(
                "INSERT INTO partnerships (game_id, innings_number, wicket_number, batter1_id, batter2_id, "
                " runs, is_club_innings, batter2_name) VALUES (:g, 1, 3, :b1, :b2, :r, :c, :n2)",
                g=GAMES[n], b1=st["b1"], b2=st["b2"], r=RUNS[n], c=st["club"], n2=st["n2"])
        await s.commit()


def check(label, ok, detail=""):
    base.check(label, ok, detail)


async def main() -> None:
    await base.build_schema()
    await seed()

    async with Session() as s:
        payload = await get_records(
            str(OURS), season_id=None, grade_id=None, grade_name=None, finals_only=False,
            captain_only=False, gender=None, categories="all", formats=None, competitions=None,
            debug_timing=False, db=s, viewer=None)
    board = {r["runs"] for r in payload["partnerships"]["top_partnerships"]}

    buf = io.StringIO()
    with redirect_stdout(buf):
        # Same code path the script runs, pointed at the verification database.
        diag.async_session_maker = Session
        await diag.diagnose(str(OURS), date(2017, 12, 16), None, 1)
    out = buf.getvalue()
    blocks = {}
    for n, r in RUNS.items():
        i = out.find(f"{r} runs")
        blocks[n] = out[i:out.find("\n\n", i) if out.find("\n\n", i) != -1 else None] if i != -1 else ""

    for n, r in RUNS.items():
        on_board = r in board
        said = "INCLUDED" if "INCLUDED" in blocks[n] else ("DROPPED" if "DROPPED" in blocks[n] else "NO VERDICT")
        check(f"{n}: records route {'lists' if on_board else 'omits'} {r}; diagnostic says {said}",
              (on_board and said == "INCLUDED") or (not on_board and said == "DROPPED"),
              blocks[n])
    # The control must be on the board, or "dropped" above proves nothing.
    check("control stand is on the shipped records board", RUNS["control"] in board, str(sorted(board)))
    check("name-only reason names the stored name", "R Ward" in blocks["nameonly"], blocks["nameonly"])
    check("opposition-innings reason is named", "is_club_innings is FALSE" in blocks["oppinn"], blocks["oppinn"])
    check("other-org reason is named", "belongs to org" in blocks["otherorg"], blocks["otherorg"])

    # A slug resolves to the same club; an unknown slug stops the run.
    async with Session() as s:
        await s.execute(text("UPDATE organisations SET slug = 'our-club' WHERE id = :i"), {"i": OURS})
        await s.commit()
    buf2 = io.StringIO()
    with redirect_stdout(buf2):
        await diag.diagnose("our-club", date(2017, 12, 16), 204, 1)
    check("slug resolves to the club and finds the control stand", "INCLUDED" in buf2.getvalue(), buf2.getvalue())
    try:
        await diag.diagnose("no-such-club", date(2017, 12, 16), None, 1)
        check("unknown slug stops the run", False)
    except SystemExit:
        check("unknown slug stops the run", True)

    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    for f in base.FAILURES:
        print(f"  - {f}")
    await engine.dispose()
    sys.exit(1 if base.FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
