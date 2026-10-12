"""A scorecard CSV with one cell that is not a number: a message, not a 500.

Reported by Hamilton Veterans importing VOSCA 2018-19: choosing the file showed
a bare "Internal Server Error". One row (Crawford, John, game G1) had a stray
backtick in `bowling_wickets`, a mistyped number. The review step totals each
player's runs and wickets through `_parse_int`, which raised `ValueError` with
nothing to catch it, so the club had no way to tell which cell was wrong.

This drives the SHIPPED route bodies (preview, resolve, commit) against a real
Postgres:

  * RESOLVE does not raise on a bad cell. It names the row, the player, the
    game, the column and the value, and counts them.
  * COMMIT refuses with a 422 carrying the same message, and writes nothing.
  * THE SAME SHEET WITH THE CELL FIXED resolves with no bad cells and imports,
    so the check is capable of passing as well as failing.
  * Numbers that are fine are left alone: blanks, 0, "7.0", overs like "4.3".
  * A bad cell in a column the review reads elsewhere (batting_runs, which
    feeds the scorecard-pairing signature) is also reported, not a crash.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/verify_bad_cells \\
  python -m verification.verify_import_bad_cells

Control run: check out the commit before this one and run it again. It REPORTS
that resolve raised, rather than crashing on the first missing key.
"""
from __future__ import annotations

import asyncio
import csv
import io
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.services.superseded_ddl import STATEMENTS as SUPERSEDED_DDL
from app.services.manual_innings_ddl import STATEMENTS as INNINGS_DDL
from app.models.db import (
    Base, Grade, ManualBowlingSpell, ManualGame, Organisation, Player, Season, User,
)
from app.routers.manual_entries import (
    GAME_CSV_COLUMNS, GameResolveRequest, commit_manual_games,
    preview_manual_games, resolve_manual_games,
)
from app.services.game_import_staging_ddl import STATEMENTS as STAGING_DDL

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


ORG, USER = uuid.uuid4(), uuid.uuid4()
S_ID, G_ID = uuid.uuid4(), uuid.uuid4()


class FakeUpload:
    def __init__(self, text_: str, filename: str = "VOSCA_2018-19.csv"):
        self._data = text_.encode("utf-8-sig")
        self.filename = filename

    async def read(self):
        return self._data


def csv_of(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=GAME_CSV_COLUMNS, extrasaction="ignore", restval="")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


async def setup() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        for tbl, col in (await conn.execute(text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND data_type = 'json'"))).all():
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb USING "{col}"::text::jsonb'))
        for name, sql in view_statements():
            await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
            await conn.execute(text(sql.replace("OR REPLACE ", "")))
        for stmt in list(SUPERSEDED_DDL) + list(INNINGS_DDL) + list(STAGING_DDL):
            await conn.execute(text(stmt))
        # Lifespan-only tables the route bodies reach; copied from main.py.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS player_achievements (
                id SERIAL PRIMARY KEY, player_id UUID, organisation_id UUID, season TEXT)"""))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL, canonical_name TEXT NOT NULL,
                alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)"""))
    async with Session() as s:
        s.add_all([
            User(id=USER, username="admin", password_hash="x"),
            Organisation(id=ORG, name="Hamilton Veterans", slug="hamilton-vets"),
            Season(id=S_ID, organisation_id=ORG, name="Summer 2018/19", year=2018),
            Grade(id=G_ID, season_id=S_ID, name="Over 60 Mixed"),
            Player(id=uuid.uuid4(), organisation_id=ORG, name="Hutchins, Christopher"),
            Player(id=uuid.uuid4(), organisation_id=ORG, name="Oakley, Lyndon"),
            Player(id=uuid.uuid4(), organisation_id=ORG, name="Crawford, John"),
        ])
        await s.commit()


def sheet(crawford_wickets: str = "2", **crawford_extra) -> list[dict]:
    """G1 as it sits in the Hamilton file, cut to three players."""
    match = {
        "game_key": "G1", "played_at": "2018-10-21", "opposition": "Geelong Blue",
        "venue": "KFC Oval", "season_name": "Summer 2018/19",
        "grade_name": "Over 60 Mixed", "match_format": "40-over",
        "home_team": "Hamilton Over 60s", "away_team": "Geelong Blue",
        "winning_team": "Hamilton Over 60s", "result": "Won by 18 Runs",
        "innings_number": "1", "opp_innings_number": "2",
    }
    crawford = {**match, "player_name": "Crawford, John", "batting_position": "10",
                "batting_runs": "0", "batting_balls": "6", "batting_fours": "0",
                "batting_sixes": "0", "batting_not_out": "FALSE", "did_not_bat": "FALSE",
                "dismissal_type": "C Unknown B R Barrs",
                "bowling_overs": "7", "bowling_maidens": "0", "bowling_runs": "36",
                "bowling_wickets": crawford_wickets, "bowling_wides": "2",
                "bowling_no_balls": "1", "bowling_order": "6", "fielding_catches": "1"}
    crawford.update(crawford_extra)
    return [
        {**match, "player_name": "Hutchins, Christopher", "batting_position": "1",
         "batting_runs": "42", "batting_balls": "33", "batting_fours": "9",
         "batting_sixes": "0", "batting_not_out": "TRUE", "did_not_bat": "FALSE",
         "dismissal_type": "Retired Not Out", "bowling_overs": "7.0",
         "bowling_maidens": "0", "bowling_runs": "22", "bowling_wickets": "1",
         "bowling_order": "1"},
        {**match, "player_name": "Oakley, Lyndon", "batting_position": "2",
         "batting_runs": "9", "batting_balls": "14", "batting_fours": "1",
         "batting_sixes": "0", "batting_not_out": "FALSE", "did_not_bat": "FALSE",
         "dismissal_type": "C Unknown B P Cresswell", "bowling_overs": "4.3",
         "bowling_maidens": "", "bowling_runs": "29", "bowling_wickets": "0",
         "bowling_order": "2"},
        crawford,
    ]


async def run(rows: list[dict], *, commit: bool = True):
    """preview -> resolve -> commit through the shipped route bodies, each step
    reported rather than raised."""
    res = out = None
    res_err = out_err = None
    async with Session() as s:
        c, u = await s.get(Organisation, ORG), await s.get(User, USER)
        prev = await preview_manual_games(file=FakeUpload(csv_of(rows)), current_user=u, club=c, db=s)
        req = GameResolveRequest(token=prev.get("token"), rows=prev.get("rows") or [])
        try:
            res = await resolve_manual_games(req=req, current_user=u, club=c, db=s)
        except Exception as e:  # noqa: BLE001 - reported, not raised
            res_err = f"{type(e).__name__}: {getattr(e, 'detail', e)}"
        if commit:
            try:
                out = await commit_manual_games(req=req, current_user=u, club=c, db=s)
            except Exception as e:  # noqa: BLE001 - reported, not raised
                out_err = f"{type(e).__name__}: {getattr(e, 'detail', e)}"
                await s.rollback()
    return res, res_err, out, out_err


async def games_written() -> int:
    async with Session() as s:
        return len((await s.execute(select(ManualGame.id).where(
            ManualGame.organisation_id == ORG))).scalars().all())


async def crawford_wickets_written():
    async with Session() as s:
        return (await s.execute(
            select(ManualBowlingSpell.wickets).join(Player, Player.id == ManualBowlingSpell.player_id)
            .where(Player.name == "Crawford, John"))).scalars().all()


async def wipe_games() -> None:
    async with Session() as s:
        await s.execute(text("TRUNCATE manual_games CASCADE"))
        await s.commit()


async def main() -> None:
    await setup()

    print("\n-- THE HAMILTON ROW: a backtick where a wicket count belongs --")
    res, res_err, out, out_err = await run(sheet(crawford_wickets="`"))
    check("resolve does not raise on a bad cell", res_err is None, res_err or "")
    res = res or {}
    check("it counts one bad cell", res.get("bad_cell_count") == 1, str(res.get("bad_cell_count")))
    cells = res.get("bad_cells") or [{}]
    cell = cells[0]
    check("it names the column and the value",
          cell.get("column") == "bowling_wickets" and cell.get("value") == "`", str(cell))
    check("it names the player and the game",
          cell.get("player") == "Crawford, John" and cell.get("game_key") == "G1", str(cell))
    check("it gives the row (header is row 1, first data row is 2)",
          cell.get("row") == 4, str(cell.get("row")))
    warn = " ".join(res.get("warnings") or [])
    check("a warning says which cell, in words",
          "bowling_wickets" in warn and "Crawford, John" in warn and "row 4" in warn, warn)
    check("the rest of the sheet still reads (three players matched)",
          (res.get("totals") or {}).get("players_matched") == 3, str(res.get("totals")))
    check("commit refuses with a 422 naming the cell",
          out_err is not None and out_err.startswith("HTTPException")
          and "bowling_wickets" in out_err
          and "Crawford, John" in out_err, str(out_err))
    check("nothing was written", await games_written() == 0)

    print("\n-- THE SAME SHEET WITH THE CELL FIXED --")
    res, res_err, out, out_err = await run(sheet(crawford_wickets="2"))
    check("resolve raises nothing", res_err is None, res_err or "")
    check("no bad cells reported", (res or {}).get("bad_cell_count") == 0,
          str((res or {}).get("bad_cell_count")))
    check("commit goes through", out_err is None and out is not None, str(out_err))
    check("the game is written", await games_written() == 1, str(await games_written()))
    check("Crawford's wickets are the corrected figure",
          await crawford_wickets_written() == [2], str(await crawford_wickets_written()))
    await wipe_games()

    print("\n-- NUMBERS THAT ARE FINE ARE LEFT ALONE --")
    rows = sheet(crawford_wickets="0", bowling_overs="4.3", bowling_maidens="",
                 bowling_wides="2.0", fielding_catches="")
    res, res_err, out, out_err = await run(rows, commit=False)
    check("0, blanks, 7.0 and 4.3 raise no flag",
          res_err is None and (res or {}).get("bad_cell_count") == 0,
          res_err or str((res or {}).get("bad_cells")))

    print("\n-- A BAD CELL IN A COLUMN THE REVIEW READS ELSEWHERE --")
    res, res_err, out, out_err = await run(
        sheet(crawford_wickets="1", batting_runs="abc", bowling_overs="4,3"), commit=False)
    check("resolve does not raise", res_err is None, res_err or "")
    got = sorted((c.get("column"), c.get("value")) for c in (res or {}).get("bad_cells") or [])
    check("both cells are reported", got == [("batting_runs", "abc"), ("bowling_overs", "4,3")],
          str(got))

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAILURES:
        print("failed:", "; ".join(FAILURES))
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
