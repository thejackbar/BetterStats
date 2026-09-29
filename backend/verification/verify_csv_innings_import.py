"""The manual-games CSV template, a single sundries figure, and edit undo.

Reported by Hamilton Veterans, who were entering old scorecards: the template
they downloaded came back as an error, and once that was fixed the question was
whether a club holding its sundries and the opposition's totals in a
spreadsheet could put them in the CSV rather than retyping them on screen.

The CSV already takes each innings' total and itemised sundries for both sides
(`innings_*` / `opp_*`, the scorebook import). Three things were still wrong,
and this drives the SHIPPED route bodies against a real Postgres for each:

  * THE TEMPLATE. Its example rows were positional lists that drifted a column
    when batting_caught_behind was added and went on drifting as the innings
    columns arrived: 53 columns, 32 values, bowling overs under caught-behind,
    and not one innings or opposition column filled in. The template a club
    downloads now imports cleanly end to end and draws the scorecard it
    describes, to the run.
  * ONE SUNDRIES FIGURE. A book that never itemised its sundries had no column
    for them — the hand-entry form's "Or total" box had no CSV twin.
    `innings_extras` / `opp_extras` now carry it, and itemised figures still
    win where both are given.
  * EDIT UNDO. Delete and overwrite undo kept a game's innings figures, fall of
    wickets and partnerships; undoing an EDIT did not, so it left the edited
    innings figures in place. It restores them now, and an edit logged before
    they were snapshotted is left exactly as it is rather than having its fall
    of wickets deleted.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/verify_csv_innings \\
  python -m verification.verify_csv_innings_import

Control run: check out the previous commit and run it again. It REPORTS the
missing parts rather than crashing on the first absent column.
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
    Base, Grade, ManualBowlingSpell, ManualEditLog, ManualFallOfWicket, ManualGame,
    ManualInnings, ManualPartnership, Organisation, Player, Season, User,
)
from app.routers.manual_entries import (
    GAME_CSV_COLUMNS, GameResolveRequest, ManualGameIn, commit_manual_games,
    delete_manual_game, games_template, get_manual_game, preview_manual_games,
    resolve_manual_games, undo_edit, update_manual_game,
)
from app.routers.games import get_scorecard
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
CLUB_NAME = "Hamilton Veterans"


class FakeUpload:
    def __init__(self, text_: str, filename: str = "sheet.csv"):
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
            Organisation(id=ORG, name=CLUB_NAME, slug="hamilton-vets"),
            Season(id=S_ID, organisation_id=ORG, name="Summer 2010/11", year=2010),
            Grade(id=G_ID, season_id=S_ID, name="1st Grade"),
            Player(id=uuid.uuid4(), organisation_id=ORG, name="Smith, John"),
            Player(id=uuid.uuid4(), organisation_id=ORG, name="Brown, Tom"),
        ])
        await s.commit()


async def run_import(rows: list[dict], *, mode: str = "skip"):
    """preview -> resolve -> commit through the shipped route bodies."""
    async with Session() as s:
        c, u = await s.get(Organisation, ORG), await s.get(User, USER)
        prev = await preview_manual_games(file=FakeUpload(csv_of(rows)), current_user=u, club=c, db=s)
        req = GameResolveRequest(token=prev.get("token"), rows=prev.get("rows") or [],
                                 duplicate_mode=mode)
        res = await resolve_manual_games(req=req, current_user=u, club=c, db=s)
        try:
            out = await commit_manual_games(req=req, current_user=u, club=c, db=s)
            return res, out, None
        except Exception as e:  # noqa: BLE001 - reported, not raised
            return res, None, f"{type(e).__name__}: {getattr(e, 'detail', e)}"


async def children(game_id) -> dict:
    """The game's innings (by number), fall of wickets and partnerships."""
    if not game_id:
        return {"innings": {}, "fow": 0, "stands": []}
    gid = uuid.UUID(str(game_id))
    async with Session() as s:
        inns = (await s.execute(select(ManualInnings).where(
            ManualInnings.manual_game_id == gid))).scalars().all()
        fow = (await s.execute(select(ManualFallOfWicket).where(
            ManualFallOfWicket.manual_game_id == gid))).scalars().all()
        stands = (await s.execute(select(ManualPartnership).where(
            ManualPartnership.manual_game_id == gid))).scalars().all()
    return {"innings": {r.innings_number: r for r in inns}, "fow": len(fow),
            "stands": sorted(p.runs for p in stands)}


async def only_game_id() -> str | None:
    async with Session() as s:
        ids = (await s.execute(select(ManualGame.id).where(
            ManualGame.organisation_id == ORG))).scalars().all()
        return str(ids[0]) if len(ids) == 1 else None


async def latest_log(action: str) -> ManualEditLog | None:
    async with Session() as s:
        return (await s.execute(select(ManualEditLog).where(
            ManualEditLog.organisation_id == ORG, ManualEditLog.action == action)
            .order_by(ManualEditLog.id.desc()).limit(1))).scalar()


async def undo(log_id: int) -> str | None:
    try:
        async with Session() as s:
            await undo_edit(log_id=log_id, current_user=await s.get(User, USER),
                            club=await s.get(Organisation, ORG), db=s)
        return None
    except Exception as e:  # noqa: BLE001 - reported, not raised
        return f"{type(e).__name__}: {getattr(e, 'detail', e)}"


async def edit_clearing_innings(gid: str) -> None:
    """Edit the game through the shipped route, sending no innings rows."""
    async with Session() as s:
        c, u = await s.get(Organisation, ORG), await s.get(User, USER)
        full = await get_manual_game(game_id=gid, current_user=u, club=c, db=s)
        payload = {k: v for k, v in full.items() if k in ManualGameIn.model_fields}
        payload["innings"] = []
        await update_manual_game(game_id=gid, data=ManualGameIn(**payload),
                                 current_user=u, club=c, db=s)


async def wipe_games() -> None:
    async with Session() as s:
        await s.execute(text("TRUNCATE manual_games CASCADE"))
        await s.execute(text("TRUNCATE manual_edit_logs"))
        await s.commit()


async def main() -> None:
    await setup()

    print("\n-- THE TEMPLATE A CLUB DOWNLOADS --")
    async with Session() as s:
        resp = await games_template(current_user=await s.get(User, USER),
                                    club=await s.get(Organisation, ORG))
        body = b"".join([chunk async for chunk in resp.body_iterator]).decode("utf-8-sig")
    lines = list(csv.reader(io.StringIO(body)))
    header, data = lines[0], lines[1:]
    check("the header is the column list the import reads", header == GAME_CSV_COLUMNS)
    check("it has a single-figure sundries column for each side",
          "innings_extras" in header and "opp_extras" in header)
    check("every example row has exactly one value per column (nothing drifted)",
          bool(data) and all(len(r) == len(header) for r in data),
          str([len(r) for r in data]) + f" vs {len(header)}")
    tpl = [dict(zip(header, r)) for r in data]
    check("the example's bowling overs sit under bowling_overs, not caught-behind",
          any(r.get("bowling_overs") == "8.2" for r in tpl)
          and all(r.get("batting_caught_behind") in ("", "true", "false") for r in tpl),
          str([(r.get("batting_caught_behind"), r.get("bowling_overs")) for r in tpl]))
    bowlers = [r for r in tpl if r.get("bowling_overs")]
    check("every example row that bowls names the opposition's innings to file it under",
          bool(bowlers) and all(r.get("opp_innings_number")
                                and r.get("opp_innings_number") != r.get("innings_number")
                                for r in bowlers),
          str([(r.get("innings_number"), r.get("opp_innings_number")) for r in bowlers]))
    check("the example fills in our innings' sundries and total",
          any(r.get("innings_total") and r.get("innings_byes") for r in tpl))
    check("and the opposition's total, with a single sundries figure",
          any(r.get("opp_total") and r.get("opp_extras") for r in tpl))
    check("the example names the downloading club as the home side",
          bool(tpl) and tpl[0].get("home_team") == CLUB_NAME, str(tpl[:1]))

    print("\n-- THE TEMPLATE'S OWN EXAMPLE, IMPORTED END TO END --")
    res, out, err = await run_import(tpl)
    check("the review raises no warning about the example", not res.get("warnings"),
          str(res.get("warnings")))
    check("the example imports as one match", err is None and (out or {}).get("games_created") == 1
          and not (out or {}).get("errors"), str(err or out))
    gid = await only_game_id()
    ch = await children(gid)
    i1, i2 = ch["innings"].get(1), ch["innings"].get(2)
    check("innings 1 is stored as ours with its itemised sundries and total",
          i1 is not None and i1.batting_side == "us"
          and (i1.byes, i1.leg_byes, i1.wides, i1.no_balls, i1.penalty) == (4, 2, 3, 1, 0)
          and (i1.total_runs, i1.total_wickets) == (67, 1),
          str(i1 and (i1.batting_side, i1.byes, i1.leg_byes, i1.wides, i1.no_balls,
                      i1.penalty, i1.total_runs, i1.total_wickets)))
    check("innings 2 is stored as the opposition's, with its single sundries figure",
          i2 is not None and i2.batting_side == "opposition"
          and (i2.total_runs, i2.total_wickets, float(i2.overs or 0), i2.extras_total) == (137, 10, 38.4, 9),
          str(i2 and (i2.batting_side, i2.total_runs, i2.total_wickets, i2.overs,
                      getattr(i2, "extras_total", None))))
    async with Session() as s:
        bowl = (await s.execute(select(ManualBowlingSpell).where(
            ManualBowlingSpell.manual_game_id == uuid.UUID(gid)))).scalars().all() if gid else []
    check("our bowlers are filed against innings 2, the opposition's",
          bool(bowl) and {b.innings_number for b in bowl} == {2},
          str([b.innings_number for b in bowl]))
    check("the fall of wickets and the partnerships it implies are stored",
          ch["fow"] == 1 and ch["stands"] == [60], str((ch["fow"], ch["stands"])))

    print("\n-- THE SCORECARD IT DRAWS --")
    card = None
    if gid:
        async with Session() as s:
            card = await get_scorecard(gid, s)
    t = (card or {}).get("innings_totals") or {}
    t1, t2 = t.get(1) or {}, t.get(2) or {}
    check("innings 1 reads as ours", t1.get("batting_team") == CLUB_NAME, str(t1))
    check("innings 1 draws 57 off the bat plus 10 sundries = 67",
          (t1.get("runs"), t1.get("extras")) == (57, 10), str(t1))
    check("its byes and leg byes reach the card, not only wides and no-balls",
          (t1.get("extras_breakdown") or {}).get("byes") == 4
          and (t1.get("extras_breakdown") or {}).get("leg_byes") == 2, str(t1.get("extras_breakdown")))
    check("innings 2 reads as the opposition's", t2.get("batting_team") == "Bayswater", str(t2))
    check("the opposition draws as 137 with 9 sundries, not 137 plus its sundries again",
          (t2.get("runs") or 0) + (t2.get("extras") or 0) == 137 and t2.get("extras") == 9, str(t2))
    check("with its 10 wickets and 38.4 overs",
          t2.get("wickets") == 10 and t2.get("overs") == 38.4, str(t2))

    print("\n-- UNDO PUTS THE INNINGS FIGURES BACK --")
    if gid:
        async with Session() as s:
            await delete_manual_game(game_id=gid, current_user=await s.get(User, USER),
                                     club=await s.get(Organisation, ORG), db=s)
        log = await latest_log("delete")
        err = await undo(log.id) if log else "no delete log"
        back = await children(gid)
        check("undoing a delete brings back the innings, fall of wickets and stands",
              err is None and set(back["innings"]) == {1, 2} and back["fow"] == 1
              and back["stands"] == [60], str(err or back))

        await edit_clearing_innings(gid)
        mid = await children(gid)
        check("an edit that sends no innings rows clears them (and leaves the fall of wickets)",
              mid["innings"] == {} and mid["fow"] == 1, str(mid))
        log = await latest_log("update")
        err = await undo(log.id) if log else "no update log"
        back = await children(gid)
        check("undoing that EDIT brings the innings figures back",
              err is None and set(back["innings"]) == {1, 2}
              and back["innings"][2].total_runs == 137 and back["innings"][1].byes == 4,
              str(err or {k: (v.batting_side, v.total_runs) for k, v in back["innings"].items()}))
        check("and leaves the fall of wickets and stands exactly as they were",
              back["fow"] == 1 and back["stands"] == [60], str(back))

        # An edit logged before these were snapshotted: its `before` carries no
        # innings / fall_of_wickets / partnerships keys. Undoing it must not
        # read that absence as "there were none" and delete what is there.
        await edit_clearing_innings(gid)
        log = await latest_log("update")
        if log:
            async with Session() as s:
                row = await s.get(ManualEditLog, log.id)
                before = dict(row.before_json or {})
                ch_ = dict(before.get("children") or {})
                for k in ("innings", "fall_of_wickets", "partnerships"):
                    ch_.pop(k, None)
                before["children"] = ch_
                row.before_json = before
                await s.commit()
        err = await undo(log.id) if log else "no update log"
        back = await children(gid)
        check("undoing an edit logged before this keeps a scorebook's fall of wickets and stands",
              err is None and back["fow"] == 1 and back["stands"] == [60], str(err or back))

    # From a fresh import: the old-style-log case above leaves the game with no
    # innings rows on purpose, which is not the state this one starts from.
    await wipe_games()
    await run_import(tpl)
    changed = [dict(r, opp_extras="11") if r.get("opp_extras") else r for r in tpl]
    _res, out, err = await run_import(changed, mode="overwrite")
    now = await children(await only_game_id())
    check("an overwrite import replaces the match with the sheet's new sundries",
          err is None and (now["innings"].get(2) and now["innings"][2].extras_total) == 11,
          str(err or {k: v.extras_total for k, v in now["innings"].items()}))
    log = await latest_log("import")
    err = await undo(log.id) if log else "no import log"
    orig = await children(await only_game_id())
    check("undoing the overwrite restores the original innings figures",
          err is None and (orig["innings"].get(2) and orig["innings"][2].total_runs) == 137,
          str(err or orig))

    print("\n-- A SINGLE SUNDRIES FIGURE, AND ITEMISED FIGURES STILL WINNING --")
    await wipe_games()
    base = {"game_key": "G2", "played_at": "2011-01-08", "opposition": "Rivals",
            "season_name": "Summer 2010/11", "grade_name": "1st Grade",
            "home_team": CLUB_NAME, "away_team": "Rivals"}
    one_figure = [dict(base, player_name="Smith, John", innings_number="1",
                       opp_innings_number="2", batting_position="1", batting_runs="50",
                       innings_extras="14", opp_total="120", opp_wickets="9",
                       opp_extras="6")]
    _res, out, err = await run_import(one_figure)
    gid = await only_game_id()
    card = None
    if gid:
        async with Session() as s:
            card = await get_scorecard(gid, s)
    t = (card or {}).get("innings_totals") or {}
    check("innings_extras alone draws our sundries as that one figure",
          err is None and (t.get(1) or {}).get("extras") == 14
          and (t.get(1) or {}).get("runs") == 50, str(err or t.get(1)))
    check("opp_extras alone does the same for theirs, without double counting",
          (t.get(2) or {}).get("extras") == 6
          and ((t.get(2) or {}).get("runs") or 0) + ((t.get(2) or {}).get("extras") or 0) == 120,
          str(t.get(2)))

    await wipe_games()
    both = [dict(one_figure[0], innings_byes="3", innings_wides="2", innings_extras="99")]
    _res, out, err = await run_import(both)
    gid = await only_game_id()
    card = None
    if gid:
        async with Session() as s:
            card = await get_scorecard(gid, s)
    t1 = ((card or {}).get("innings_totals") or {}).get(1) or {}
    check("where a sheet gives both, the itemised sundries win over the single figure",
          err is None and t1.get("extras") == 5, str(err or t1))

    await wipe_games()
    plain = [dict(base, player_name="Smith, John", innings_number="1", batting_runs="30")]
    _res, out, err = await run_import(plain)
    gid = await only_game_id()
    check("a sheet with none of the innings columns imports exactly as before",
          err is None and gid is not None and (await children(gid))["innings"] == {}, str(err))

    await engine.dispose()
    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  FAILED:", f)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
