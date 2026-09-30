"""A hand-entered game's two sides, and the order its bowlers are listed in.

Reported by Hamilton Veterans, who play as "Portland Over 60s":

  * Whenever the opposition batted first, the scorecard header drew each
    side's score under the other side's name. Our innings was labelled with
    the CLUB's name ("Hamilton Veterans Cricket Club"), a name the match does
    not use, so the page could not place it under the home or away team the
    match records. The scorecard now names our innings for the side the MATCH
    calls ours (`games._manual_side_names`). The header half is a frontend
    fix, driven in `frontend/verification/verify_manual_scorecard_sides_browser.mjs`.
  * A CSV import listed our bowlers in batting order, because a sheet's rows
    follow the batting order and the spells were written as the rows came.
    `bowling_order` now says the order they bowled in, the import writes the
    spells in that order, and the scorecard, the edit form and an undo all
    read them back in it.

Drives the SHIPPED route bodies against a real Postgres.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/verify_side_names \\
  python -m verification.verify_manual_side_names

Control run: check out the previous commit and run it again. It REPORTS the
missing parts rather than crashing on the first absent name.
"""
from __future__ import annotations

import asyncio
import csv
import io
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.services.superseded_ddl import STATEMENTS as SUPERSEDED_DDL
from app.services.manual_innings_ddl import STATEMENTS as INNINGS_DDL
from app.services.game_import_staging_ddl import STATEMENTS as STAGING_DDL
from app.models.db import (
    Base, Grade, ManualBowlingSpell, ManualEditLog, ManualGame, Organisation, Player,
    Season, User,
)
from app.routers import games as games_router
from app.routers.manual_entries import (
    GAME_CSV_COLUMNS, GameResolveRequest, ManualGameIn, commit_manual_games,
    games_template, get_manual_game, preview_manual_games, resolve_manual_games,
    update_manual_game,
)
from app.routers.games import get_scorecard

DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

PASS = FAIL = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")


ORG, USER = uuid.uuid4(), uuid.uuid4()
S_ID, G_ID = uuid.uuid4(), uuid.uuid4()
CLUB = "Hamilton Veterans Cricket Club"
TEAM = "Portland Over 60s"
OPP = "Mt Gambier Over 60s"
BATTING_ORDER = ["Saunders, Kevin", "Ray, C", "Tonkin, John", "Barr, Daryl"]


class FakeUpload:
    def __init__(self, text_: str):
        self._data = text_.encode("utf-8-sig")
        self.filename = "sheet.csv"

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
            Organisation(id=ORG, name=CLUB, slug="hamilton-vets"),
            Season(id=S_ID, organisation_id=ORG, name="Summer 2010/11", year=2010),
            Grade(id=G_ID, season_id=S_ID, name="One Off 40 overs"),
        ] + [Player(id=uuid.uuid4(), organisation_id=ORG, name=n)
              for n in BATTING_ORDER + ["Smith, John", "Brown, Tom"]])
        await s.commit()


async def run_import(rows: list[dict]):
    async with Session() as s:
        c, u = await s.get(Organisation, ORG), await s.get(User, USER)
        prev = await preview_manual_games(file=FakeUpload(csv_of(rows)), current_user=u, club=c, db=s)
        req = GameResolveRequest(token=prev.get("token"), rows=prev.get("rows") or [])
        await resolve_manual_games(req=req, current_user=u, club=c, db=s)
        try:
            return await commit_manual_games(req=req, current_user=u, club=c, db=s), None
        except Exception as e:  # noqa: BLE001 - reported, not raised
            return None, f"{type(e).__name__}: {getattr(e, 'detail', e)}"


async def game_ids() -> list[str]:
    async with Session() as s:
        return [str(i) for i in (await s.execute(select(ManualGame.id).where(
            ManualGame.organisation_id == ORG).order_by(ManualGame.played_at))).scalars().all()]


async def wipe() -> None:
    async with Session() as s:
        await s.execute(text("TRUNCATE manual_games CASCADE"))
        await s.execute(text("TRUNCATE manual_edit_logs"))
        await s.commit()


def match_rows(date: str, *, bowling_order: dict | None, opp_batted_first: bool = True,
               opposition: str = "Mt. Gambier Over 60s") -> list[dict]:
    """The 20 Feb 2011 shape: Mt Gambier batted first, so our innings is 2."""
    ours, theirs = (2, 1) if opp_batted_first else (1, 2)
    base = {
        "game_key": date, "played_at": date, "opposition": opposition,
        "season_name": "Summer 2010/11", "grade_name": "One Off 40 overs",
        "home_team": TEAM, "away_team": OPP, "winning_team": OPP, "result": "Lost by 30 runs",
        "innings_number": ours, "opp_innings_number": theirs,
    }
    rows = []
    for i, name in enumerate(BATTING_ORDER, 1):
        r = {**base, "player_name": name, "batting_position": i, "batting_runs": 10 + i,
             "bowling_overs": 6, "bowling_runs": 20 + i, "bowling_wickets": i % 2}
        if bowling_order:
            r["bowling_order"] = bowling_order[name]
        if i == 1:
            r.update({"innings_total": 98, "innings_wickets": 8,
                      "opp_total": 128, "opp_wickets": 7})
        rows.append(r)
    return rows


async def main() -> None:
    await setup()

    print("\n-- WHICH NAME IS OURS --")
    side_names = getattr(games_router, "_manual_side_names", None)
    check("the scorecard has one rule for naming a hand-entered game's two sides",
          side_names is not None)
    if side_names:
        org = SimpleNamespace(name=CLUB)
        g = lambda **k: SimpleNamespace(**{"home_team": None, "away_team": None, "opposition": None, **k})
        check("home is ours when the opposition is the away side",
              side_names(g(home_team=TEAM, away_team=OPP, opposition=OPP), org) == (TEAM, OPP))
        check("away is ours when the opposition is the home side",
              side_names(g(home_team=OPP, away_team=TEAM, opposition=OPP), org) == (TEAM, OPP))
        check("the opposition is matched however it is punctuated",
              side_names(g(home_team=TEAM, away_team=OPP, opposition="Mt. Gambier Over 60s"), org)
              == (TEAM, OPP))
        check("with no opposition recorded, the side sharing the club's name is ours",
              side_names(g(home_team="Bayswater", away_team="Applecross 2nd XI"),
                         SimpleNamespace(name="Applecross Cricket Club"))
              == ("Applecross 2nd XI", "Bayswater"))
        check("a word every club shares ('cricket') does not decide it",
              side_names(g(home_team="Bayswater Cricket Club", away_team="Cricket Kings"),
                         SimpleNamespace(name="Applecross Cricket Club"))[0] == "Applecross Cricket Club")
        check("one named side that is not the opposition is ours",
              side_names(g(home_team=TEAM, opposition=OPP), org) == (TEAM, OPP))
        check("nothing to go on falls back to the club's name, as before",
              side_names(g(opposition=OPP), org) == (CLUB, OPP))
        check("and a game with no names at all still reads as two sides",
              side_names(g(), org) == (CLUB, "Opposition"))

    print("\n-- THE REPORTED MATCH, IMPORTED --")
    out, err = await run_import(match_rows("2011-02-20",
                                           bowling_order={"Saunders, Kevin": 4, "Ray, C": 2,
                                                          "Tonkin, John": 3, "Barr, Daryl": 1}))
    check("it imports as one match", err is None and (out or {}).get("games_created") == 1,
          str(err or out))
    gid = (await game_ids() or [None])[0]
    card = None
    if gid:
        async with Session() as s:
            card = await get_scorecard(gid, s)
    t = (card or {}).get("innings_totals") or {}
    t1, t2 = t.get(1) or {}, t.get(2) or {}
    check("our innings is named for the side the match calls ours, not the club",
          t2.get("batting_team") == TEAM, str(t2.get("batting_team")))
    check("theirs is named as the match names it", t1.get("batting_team") == OPP,
          str(t1.get("batting_team")))
    check("the club's own name is on neither innings",
          CLUB not in {t1.get("batting_team"), t2.get("batting_team")})
    check("the header's two sides are the two names the innings carry",
          {card and card.get("home_team"), card and card.get("away_team")}
          == {t1.get("batting_team"), t2.get("batting_team")},
          str((card or {}).get("home_team")) + " / " + str((card or {}).get("away_team")))
    check("each innings keeps its own total (98/8 ours, 128/7 theirs)",
          (t2.get("runs", 0) + t2.get("extras", 0), t2.get("wickets"),
           t1.get("runs", 0) + t1.get("extras", 0), t1.get("wickets")) == (98, 8, 128, 7), str(t))

    print("\n-- OUR BOWLERS, IN THE ORDER THEY BOWLED --")
    want = ["Barr, Daryl", "Ray, C", "Tonkin, John", "Saunders, Kevin"]
    got = [r["player_name"] for r in (card or {}).get("bowling") or []]
    check("the template has a bowling_order column", "bowling_order" in GAME_CSV_COLUMNS)
    check("the scorecard lists them by bowling_order, not batting order", got == want, str(got))
    check("they bowled in the opposition's innings", {r["innings_number"] for r in (card or {}).get("bowling") or []} == {1})
    edit_got = []
    if gid:
        async with Session() as s:
            c, u = await s.get(Organisation, ORG), await s.get(User, USER)
            full = await get_manual_game(game_id=gid, current_user=u, club=c, db=s)
            edit_got = [r.get("player_name") for r in full.get("bowling_spells") or []]
    check("the edit form reads them back in that order", edit_got == want, str(edit_got))
    if gid:
        async with Session() as s:
            c, u = await s.get(Organisation, ORG), await s.get(User, USER)
            full = await get_manual_game(game_id=gid, current_user=u, club=c, db=s)
            payload = {k: v for k, v in full.items() if k in ManualGameIn.model_fields}
            await update_manual_game(game_id=gid, data=ManualGameIn(**payload),
                                     current_user=u, club=c, db=s)
        async with Session() as s:
            card2 = await get_scorecard(gid, s)
        check("saving the game from the edit form keeps the order",
              [r["player_name"] for r in card2.get("bowling") or []] == want,
              str([r["player_name"] for r in card2.get("bowling") or []]))

    print("\n-- A SHEET WITH NO bowling_order --")
    await wipe()
    out, err = await run_import(match_rows("2011-03-20", bowling_order=None, opp_batted_first=False))
    gid = (await game_ids() or [None])[0]
    card = None
    if gid:
        async with Session() as s:
            card = await get_scorecard(gid, s)
    got = [r["player_name"] for r in (card or {}).get("bowling") or []]
    check("an older sheet keeps its own row order", got == BATTING_ORDER, str(got))
    t = (card or {}).get("innings_totals") or {}
    check("and Portland batting first is still named Portland",
          (t.get(1) or {}).get("batting_team") == TEAM, str(t.get(1)))

    print("\n-- THE TEMPLATE A CLUB DOWNLOADS --")
    async with Session() as s:
        resp = await games_template(current_user=await s.get(User, USER),
                                    club=await s.get(Organisation, ORG))
        body = b"".join([chunk async for chunk in resp.body_iterator]).decode("utf-8-sig")
    lines = list(csv.reader(io.StringIO(body)))
    tpl = [dict(zip(lines[0], r)) for r in lines[1:]]
    check("its example numbers the bowlers, and not in batting order",
          [r.get("bowling_order") for r in tpl] == ["2", "1"], str([r.get("bowling_order") for r in tpl]))
    await wipe()
    out, err = await run_import(tpl)
    gid = (await game_ids() or [None])[0]
    card = None
    if gid:
        async with Session() as s:
            card = await get_scorecard(gid, s)
    got = [r["player_name"] for r in (card or {}).get("bowling") or []]
    check("imported, the example lists Brown (who opened) before Smith",
          got == ["Brown, Tom", "Smith, John"], str(err or got))

    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
