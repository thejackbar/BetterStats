"""The CSV import pairs a sheet match to the synced game of ITS grade.

Reported (Oct 2026, Shoalwater Bay): on a day the club played A, B and C grade
against the same opposition, the importer recognised an existing synced game by
the date and ONE shared opposition word, ignored grade, and linked the B grade
card (locked, import's copy preferred) to the A grade synced game. The real B
grade game stayed unlinked and counted, so the match was held twice, once under
One Day and once under Two Day.

Everything here runs against a real Postgres through the SHIPPED route bodies
(preview, resolve, commit in overwrite mode), reads the links back out of
`manual_games`, and drives these shapes:

  1  three grades, cards on both sides          every card on its own game
  1b the same, synced games with no grade name  the cards alone decide
  2  three grades, synced games with no cards   the grade alone decides
  3  nothing separates two games                the card stays UNLINKED, reported
  4  only the A game is synced, a B card        a contradicting card is never linked
  5  only one game, its grade named differently still linked (nothing competes)
  6  a two-day match dated days apart          the second look picks the right grade
  7  a junior card, only a senior game          a different competition is not linked

Run (under the pinned stack: a python 3.11 venv with requirements.txt installed):
  DATABASE_URL=postgresql+asyncpg://root@/v_grade?host=/var/run/postgresql \\
  python verification/verify_import_grade_pairing.py

CONTROL RUN: check out the commit before the grade-aware matcher, copy this file
in and run it. The checks that read a key the old code does not write are read
through presence-safe accessors, so the old code REPORTS the wrong link (the B
card on the A game) as failed checks rather than crashing.
"""
from __future__ import annotations

import asyncio
import csv
import io
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
from app.services.superseded_ddl import STATEMENTS as SUPERSEDED_DDL
from app.models.db import (
    Base, BattingInnings, Game, Grade, Organisation, Player, Season, User,
)
from app.routers.manual_entries import (
    GAME_CSV_COLUMNS, GameResolveRequest, commit_manual_games, preview_manual_games,
    resolve_manual_games,
)
from app.services.game_import_staging_ddl import STATEMENTS as STAGING_DDL

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


ORG = uuid.uuid4()
USER = uuid.uuid4()
SEASON = uuid.uuid4()
DAY = date(2004, 12, 11)

# Fixed ids so the control run is deterministic: the old matcher takes the
# first game in the index; the old second look breaks a tie on the LARGER id.
G_A = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000001")
G_B = uuid.UUID("bbbbbbbb-0000-4000-8000-000000000002")
G_C = uuid.UUID("cccccccc-0000-4000-8000-000000000003")
G_A_LATE = uuid.UUID("ffffffff-0000-4000-8000-0000000000a1")   # larger id than G_B_LATE
G_B_LATE = uuid.UUID("00000000-0000-4000-8000-0000000000b1")

# Six batters a side, one set per grade, every one a synced player.
NAMES = {
    "A": ["Adams, Al", "Archer, Ben", "Avery, Cal", "Ayres, Dan", "Aston, Eli", "Alden, Fin"],
    "B": ["Baker, Gus", "Barnes, Hal", "Bell, Ivan", "Boyd, Jed", "Bruce, Kit", "Burke, Lou"],
    "C": ["Cole, Max", "Cook, Ned", "Cross, Oli", "Cruz, Pat", "Cobb, Quin", "Cato, Ray"],
    "J": ["Junior, Abe", "Junior, Bo", "Junior, Cy", "Junior, Di"],
}
RUNS = {"A": [41, 12, 33, 5, 18, 27], "B": [22, 61, 8, 15, 30, 3],
        "C": [9, 44, 17, 26, 2, 36], "J": [10, 20, 30, 40]}
PLAYER_ID = {n: uuid.uuid4() for names in NAMES.values() for n in names}
GRADE_ID = {k: uuid.uuid4() for k in ("A", "B", "C", "1st", "U14")}
GRADE_NAME = {"A": "A Grade", "B": "B Grade: McIntosh Cup", "C": "C Grade",
              "1st": "1st Grade", "U14": "Under 14s"}


class FakeUpload:
    def __init__(self, text_: str):
        self._data = text_.encode("utf-8-sig")
        self.filename = "manual_games_scorecards.csv"

    async def read(self):
        return self._data


def csv_text(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=GAME_CSV_COLUMNS, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


def sheet_match(tag: str, grade: str, batters: str, *, day: str = "2004-12-11",
                opposition: str = "Safety Bay") -> list[dict]:
    """One sheet match. `venue` carries the tag so the links can be read back."""
    rows = []
    for i, (name, runs) in enumerate(zip(NAMES[batters], RUNS[batters]), start=1):
        row = {c: "" for c in GAME_CSV_COLUMNS}
        row.update(game_key=tag, played_at=day, opposition=opposition, venue=tag,
                   season_name="2004/05", grade_name=grade, player_name=name,
                   innings_number="1", batting_position=str(i),
                   batting_runs=str(runs), did_not_bat="false")
        rows.append(row)
    return rows


async def reset(session) -> None:
    for tbl in ("manual_fielding_stats", "manual_bowling_spells", "manual_batting_innings",
                "manual_games", "manual_edit_logs", "games", "grades", "seasons", "players",
                "club_memberships", "organisations", "users"):
        await session.execute(text(f"TRUNCATE {tbl} CASCADE"))
    await session.commit()


async def seed(session, grades: tuple) -> None:
    session.add_all([
        User(id=USER, username="admin", password_hash="x"),
        Organisation(id=ORG, name="Shoalwater Bay", slug="shoalwater"),
        Season(id=SEASON, organisation_id=ORG, name="2004/05", year=2004),
    ])
    session.add_all([Grade(id=GRADE_ID[k], season_id=SEASON, name=GRADE_NAME[k])
                     for k in grades])
    # grassroots_id: these are synced players, which is what lets a card argue.
    session.add_all([Player(id=pid, organisation_id=ORG, name=name,
                            grassroots_id=str(uuid.uuid4()))
                     for name, pid in PLAYER_ID.items()])
    await session.commit()


async def add_game(session, gid: uuid.UUID, grade: str | None, batters: str | None,
                   *, day: date = DAY) -> None:
    session.add(Game(id=gid, grade_id=GRADE_ID[grade] if grade else None, played_at=day,
                     home_team="Shoalwater Bay", away_team="Safety Bay",
                     opp_club_name="Safety Bay",
                     # ours by the fixture, so a game with no grade (no season
                     # to name the club) is still the club's, as `club_game_sql` reads it
                     home_org_id=ORG))
    await session.flush()
    if batters:
        for name, runs in zip(NAMES[batters], RUNS[batters]):
            session.add(BattingInnings(game_id=gid, player_id=PLAYER_ID[name],
                                       innings_number=1, runs=runs))
    await session.commit()


async def run_import(session, rows: list[dict]):
    """Preview, resolve and commit in overwrite mode, through the route bodies."""
    club = await session.get(Organisation, ORG)
    user = await session.get(User, USER)
    prev = await preview_manual_games(file=FakeUpload(csv_text(rows)),
                                      current_user=user, club=club, db=session)
    res = await resolve_manual_games(req=GameResolveRequest(token=prev["token"]),
                                     current_user=user, club=club, db=session)
    out = await commit_manual_games(
        req=GameResolveRequest(token=prev["token"], duplicate_mode="overwrite"),
        current_user=user, club=club, db=session)
    return res, out


async def links(session) -> dict:
    """venue tag -> the synced game its card is linked to (None when unlinked)."""
    rows = (await session.execute(text(
        "SELECT venue, superseded_by_game_id::text, pair_prefers_import "
        "FROM manual_games WHERE organisation_id = :o"), {"o": str(ORG)})).all()
    return {v: g for v, g, _p in rows}


async def counted(session) -> int:
    """Matches the club counts on this day: the effective view, as every page reads it."""
    return (await session.execute(text(
        "SELECT count(*) FROM v_effective_games WHERE played_at BETWEEN :a AND :b "
        "AND (organisation_id = :o OR home_org_id = :o OR away_org_id = :o)"),
        {"a": date(2004, 12, 1), "b": date(2004, 12, 31), "o": str(ORG)})).scalar()


def dups(res: dict) -> dict:
    return res.get("duplicates") or {}


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        json_cols = (await conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type = 'json'"))).all()
        for tbl, col in json_cols:
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb '
                f'USING "{col}"::text::jsonb'))
        for name, sql in view_statements():
            await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
            await conn.execute(text(sql.replace("OR REPLACE ", "")))
        for stmt in SUPERSEDED_DDL:
            await conn.execute(text(stmt))
        await conn.execute(text("""CREATE TABLE IF NOT EXISTS player_achievements (
            id SERIAL PRIMARY KEY, player_id UUID, organisation_id UUID, season TEXT)"""))
        await conn.execute(text("""CREATE TABLE IF NOT EXISTS grade_merge_logs (
            id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
            org_id UUID NOT NULL, canonical_name TEXT NOT NULL,
            alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)"""))
        for stmt in STAGING_DDL:
            await conn.execute(text(stmt))

    # The old matcher took the first game it met for the shared word, so which
    # card landed where depended on the order of the sheet against the order the
    # database returned the games in. Every order of the three matches is run, so
    # no ordering can make the old code look right by luck.
    from itertools import permutations
    CARDS = {k: sheet_match(k, f"{k} grade", k) for k in "ABC"}
    WANT = {"A": str(G_A), "B": str(G_B), "C": str(G_C)}
    GAMES = ((G_A, "A", "A"), (G_B, "B", "B"), (G_C, "C", "C"))

    async def three_grades(title: str, *, grade_names: bool, cards: bool) -> None:
        print(title)
        for order in permutations("ABC"):
            async with Session() as s:
                await reset(s); await seed(s, ("A", "B", "C"))
                for gid, g, b in GAMES:
                    await add_game(s, gid, g if grade_names else None, b if cards else None)
                rows = [r for k in order for r in CARDS[k]]
                res, out = await run_import(s, rows)
                got = await links(s)
                check(f"sheet order {''.join(order)}: every card is on its own grade's game",
                      all(got.get(k) == WANT[k] for k in "ABC"), str(got))
                if order == ("B", "A", "C"):
                    check("the review recognises all three as games already synced",
                          dups(res).get("synced") == 3, str(dups(res)))
                    check("the club counts three matches on the day, not four or five",
                          await counted(s) == 3, str(await counted(s)))
                    check("and the review reports nothing left undecided",
                          dups(res).get("undecided", 0) == 0, str(dups(res)))

    await three_grades("\n-- 1. THE REPORTED CASE: A, B and C grade v one opposition, one day --",
                       grade_names=True, cards=True)
    await three_grades("\n-- 1b. THE SYNCED GAMES CARRY NO GRADE NAME: THE CARDS DECIDE --",
                       grade_names=False, cards=True)
    await three_grades("\n-- 2. THE SYNCED GAMES HOLD NO CARDS: THE GRADE DECIDES --",
                       grade_names=True, cards=False)

    print("\n-- 3. NOTHING SEPARATES TWO GAMES: LEFT UNLINKED, AND SAID SO --")
    async with Session() as s:
        await reset(s); await seed(s, ("A", "B", "C"))
        await add_game(s, G_A, None, None)
        await add_game(s, G_B, None, None)
        res, out = await run_import(s, sheet_match("B", "B grade", "B"))
        got = await links(s)
        check("the card is NOT linked to either game", got.get("B") is None, str(got))
        check("so no synced game is hidden behind it", await counted(s) == 3,
              f"counted {await counted(s)} (2 synced + the card)")
        check("the review says one match could not be placed",
              dups(res).get("undecided") == 1, str(dups(res)))
        check("and explains it in a warning",
              any("neither the scorecard nor the grade" in w for w in res.get("warnings", [])),
              str(res.get("warnings")))
        check("the match still imports, as a new one",
              out.get("games_created") == 1, str(out))

    print("\n-- 4. ONLY THE A GAME IS SYNCED; THE CARD IS A DIFFERENT TEAM'S --")
    async with Session() as s:
        await reset(s); await seed(s, ("A", "B", "C"))
        await add_game(s, G_A, "A", "A")
        res, out = await run_import(s, sheet_match("B", "B grade", "B"))
        got = await links(s)
        check("a card that contradicts the game is not linked to it", got.get("B") is None, str(got))
        check("the A grade game stays counted beside the new B grade match",
              await counted(s) == 2, str(await counted(s)))
        check("and the review does not claim the B match is a duplicate",
              dups(res).get("total", 0) == 0, str(dups(res)))
        check("or call it undecided: the card settles that it is new",
              dups(res).get("undecided", 0) == 0, str(dups(res)))

    print("\n-- 5. ONE GAME, ONE CARD, THE GRADE NAMED DIFFERENTLY: STILL LINKED --")
    async with Session() as s:
        await reset(s); await seed(s, ("1st",))
        await add_game(s, G_A, "1st", None)
        res, out = await run_import(s, sheet_match("A", "A grade", "A"))
        got = await links(s)
        check("nothing else competes, so a club whose sheet says 'A grade' and "
              "Cricket Australia says '1st Grade' still pairs",
              got.get("A") == str(G_A), str(got))
        check("and the club counts the match once", await counted(s) == 1, str(await counted(s)))

    print("\n-- 6. A TWO-DAY MATCH DATED DAYS APART: THE SECOND LOOK IS GRADE-AWARE --")
    async with Session() as s:
        await reset(s); await seed(s, ("A", "B", "C"))
        await add_game(s, G_A_LATE, "A", None)
        await add_game(s, G_B_LATE, "B", None)
        res, out = await run_import(
            s, sheet_match("B", "B grade", "B", day="2004-12-13", opposition="Safety Bay"))
        got = await links(s)
        check("the review matched it on the scorecard rules, not the date",
              dups(res).get("matched_on_scores") == 1, str(dups(res)))
        check("the B grade card is linked to the B grade game",
              got.get("B") == str(G_B_LATE), str(got))
        check("and not to the A grade game that sorts first",
              got.get("B") != str(G_A_LATE), str(got))

    print("\n-- 7. A JUNIOR CARD AND ONLY A SENIOR GAME: A DIFFERENT COMPETITION --")
    async with Session() as s:
        await reset(s); await seed(s, ("A", "U14"))
        await add_game(s, G_A, "A", None)
        res, out = await run_import(s, sheet_match("J", "Under 14s", "J"))
        got = await links(s)
        check("an Under 14s card is not linked to the A grade game", got.get("J") is None, str(got))
        check("both are counted", await counted(s) == 2, str(await counted(s)))

    print("\n-- A RE-IMPORT OF THE SAME SHEET STILL REPLACES ITS OWN MATCHES IN PLACE --")
    async with Session() as s:
        await reset(s); await seed(s, ("A", "B", "C"))
        for gid, g, b in ((G_A, "A", "A"), (G_B, "B", "B"), (G_C, "C", "C")):
            await add_game(s, gid, g, b)
        THREE = [r for k in "BAC" for r in CARDS[k]]
        await run_import(s, THREE)
        res, out = await run_import(s, THREE)
        got = await links(s)
        check("the second run sees three matches already held",
              dups(res).get("manual") == 3, str(dups(res)))
        check("replaces them in place", out.get("games_overwritten") == 3, str(out))
        check("and every card is still on its own game",
              all(got.get(k) == WANT[k] for k in "ABC"), str(got))
        n = (await s.execute(text(
            "SELECT count(*) FROM manual_games WHERE organisation_id = :o"),
            {"o": str(ORG)})).scalar()
        check("with no extra copies made", n == 3, str(n))

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
