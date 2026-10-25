"""A match held as a linked pair counts once in the by-grade grid, whatever each source calls its grade.

Reported off Payneham: a junior's profile read 148 matches where his scorecards hold 76. His club (CSFW)
cards and the Cricket Australia games are the same matches, linked, with the club card shown. The grid
counts Cricket Australia's per-grade claim ("NEJCA - U/14 Division 3": 15 in 2025/26) AND the games we
hold, and it reconciles them with `max(held, claimed)` per (season, grade NAME). The shown copy was the
club card, filed under the club's own grade name ("U14 Knights": 14), so the two never met in one cell and
the season read 29. Every season where the sources name a grade differently doubled the same way.

The fix files a linked card under its Cricket Australia twin's grade, so a linked pair is one match in
one cell. A card with no twin keeps the grade it was typed under.

Reads every figure through the shipped route bodies with the production views, against a real Postgres.
The same file run against the previous commit is the control.

Run:
  DATABASE_URL=postgresql+asyncpg://root@/pl_g?host=/var/run/postgresql python verification/verify_grid_linked_card_grade.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from verify_board_games_match_profile import build_schema
from app.routers.players import get_player_stats
from app.services import superseded_ddl
from app.services.aggregations import get_player_team_breakdown, grid_matches_for_players

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


ORG, OPP = uuid.uuid4(), uuid.uuid4()
SEASON = uuid.uuid4()
CA_GRADE, CLUB_GRADE = uuid.uuid4(), uuid.uuid4()
P = {k: uuid.uuid4() for k in ("LINKED", "CARDONLY", "UNLINKED", "MIXED", "SHADOW", "WRONG", "OTHER", "STRANGER")}
WOMEN_GRADE = uuid.uuid4()
NAMES = {"LINKED": "Linked, Lee", "CARDONLY": "Cardonly, Cam", "UNLINKED": "Unlinked, Uma", "MIXED": "Mixed, Max",
         "SHADOW": "Shadow, Sam", "WRONG": "Wrong, Wes", "OTHER": "Other, Ola", "STRANGER": "Stranger, Stu"}
CA_NAME, CLUB_NAME = "NEJCA - U/14 Division 3", "U14 Knights"
_day = 0


async def seed() -> None:
    global _day
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)

        for oid, nm, slug in ((ORG, "Linked Club", "linked"), (OPP, "Opposition CC", "opp")):
            await ex("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, :n, :s, true)", i=oid, n=nm, s=slug)
        await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, 'Summer 2025/26', 2025)", i=SEASON, o=ORG)
        for gid, nm in ((CA_GRADE, CA_NAME), (CLUB_GRADE, CLUB_NAME), (WOMEN_GRADE, "Women 1st Grade")):
            await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
                     "VALUES (:i, :s, :n, :g, 'junior', ARRAY['junior'])", i=gid, s=SEASON, n=nm, g=str(gid))
        for k, pid in P.items():
            await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) VALUES (:i, :o, :n, :g, 'active')",
                     i=pid, o=ORG, n=NAMES[k], g=str(pid))

        async def synced_game(grade=CA_GRADE, day=None) -> uuid.UUID:
            global _day
            _day += 7
            gid = uuid.uuid4()
            day = _day if day is None else day
            await ex("INSERT INTO games (id, grade_id, played_at, result, home_org_id, away_org_id, match_format, status) "
                     "VALUES (:i, :g, :d, 'WIN', :o, :x, 'One Day', 'COMPLETED')",
                     i=gid, g=grade, d=date(2025, 10, 4) + timedelta(days=day), o=ORG, x=OPP)
            return gid

        async def card(key, link=None, played_at=None) -> uuid.UUID:
            global _day
            mid = uuid.uuid4()
            if played_at is None:
                _day += 7
                played_at = date(2025, 10, 4) + timedelta(days=_day)
            await ex("INSERT INTO manual_games (id, organisation_id, season_id, grade_id, played_at, opposition, result, match_format, "
                     " superseded_by_game_id, pair_prefers_import, pairing_locked) "
                     "VALUES (:m, :o, :s, :g, :d, 'Opposition', 'WIN', 'One Day', CAST(:lk AS UUID), :pf, :pf)",
                     m=mid, o=ORG, s=SEASON, g=CLUB_GRADE, d=played_at, lk=str(link) if link else None, pf=link is not None)
            await ex("INSERT INTO manual_batting_innings (manual_game_id, player_id, innings_number, batting_position, runs, balls, "
                     " dismissal_type, not_out, did_not_bat) VALUES (:m, :p, 1, 3, 20, NULL, 'bowled', false, false)", m=mid, p=P[key])
            return mid

        async def ca_claim(key, n):
            await ex("INSERT INTO player_season_stats (player_id, season_id, matches, batting_innings, runs, not_outs, wickets, "
                     " catches, source) VALUES (:p, :s, :m, 0, 0, 0, 0, 0, 'api')", p=P[key], s=SEASON, m=n)
            await ex("INSERT INTO player_season_grade_stats (player_id, season_id, grade_id, matches) VALUES (:p, :s, :g, :m)",
                     p=P[key], s=SEASON, g=CA_GRADE, m=n)

        async def named(key, gid):
            await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=gid, p=P[key])

        # LINKED: 3 matches, each a Cricket Australia game (no scorecard of its own, the player only named) linked to
        # the club's card, which is the copy shown. CA claims the 3 under its own grade name.
        for _ in range(3):
            g = await synced_game()
            await named("LINKED", g)
            await card("LINKED", link=g)
        await ca_claim("LINKED", 3)
        # CARDONLY: 2 matches only the club's book holds. No twin, no claim: filed under the club's own grade.
        for _ in range(2):
            await card("CARDONLY")
        # UNLINKED: a card and a Cricket Australia game for the same match that nothing has linked yet. Two copies
        # are held and both are counted, which is what Card review's Possible doubles is for.
        g = await synced_game()
        await named("UNLINKED", g)
        await card("UNLINKED", played_at=date(2025, 10, 4) + timedelta(days=_day))
        await ca_claim("UNLINKED", 1)
        # MIXED: 2 linked matches and 1 match only the book holds.
        for _ in range(2):
            g = await synced_game()
            await named("MIXED", g)
            await card("MIXED", link=g)
        await card("MIXED")
        await ca_claim("MIXED", 2)

        # A fixture between two sides of the same club: ONE synced game, the club holds a card for each side. Only one
        # card can link to it, so the other side's player has no game to link to.
        async def same_club_fixture(key, d_link_to=None):
            g = await synced_game()
            day = _day
            await named("OTHER", g)
            await named(key, g)
            await card("OTHER", link=g, played_at=date(2025, 10, 4) + timedelta(days=day))
            return await card(key, link=d_link_to, played_at=date(2025, 10, 4) + timedelta(days=day + 1))

        # SHADOW: 2 ordinary linked matches and the player's side of a same-club fixture, left with no link.
        for _ in range(2):
            g = await synced_game()
            await named("SHADOW", g)
            await card("SHADOW", link=g)
        await same_club_fixture("SHADOW")
        await ca_claim("SHADOW", 3)
        # WRONG: the same, but the side's card was linked to an unrelated Women's game.
        for _ in range(2):
            g = await synced_game()
            await named("WRONG", g)
            await card("WRONG", link=g)
        wrong = await synced_game(grade=WOMEN_GRADE)
        await named("WRONG", wrong)
        await same_club_fixture("WRONG", d_link_to=wrong)
        await ca_claim("WRONG", 3)
        # STRANGER: an unlinked card on the same day, but not named in the hidden game. Nothing ties it to it.
        await card("STRANGER", played_at=date(2025, 10, 4) + timedelta(days=_day))
        await s.commit()


async def header(key) -> int | None:
    async with Session() as s:
        d = await get_player_stats(player_id=str(P[key]), db=s, season_id=None, grade_id=None, last_n_games=None,
                                   start_date=None, end_date=None, categories=None, formats=None, competitions=None, grades=None)
    return (d["career_batting"] or {}).get("games")


async def grid(key) -> dict:
    async with Session() as s:
        return await get_player_team_breakdown(s, str(P[key]), str(ORG), None)


async def board(key) -> int | None:
    """The M a leaderboard row reads: the same call the boards make for the players they return.
    (The batting board itself only lists players with a batting row, and LINKED has none.)"""
    async with Session() as s:
        got = await grid_matches_for_players(s, str(ORG), [str(P[key])])
    return got.get(str(P[key]))


async def main() -> None:
    await build_schema()
    async with engine.begin() as conn:
        for stmt in superseded_ddl.STATEMENTS:
            await conn.execute(text(stmt))
    await seed()

    print("\n-- A LINKED PAIR IS ONE MATCH IN ONE CELL --")
    g = await grid("LINKED")
    check("3 linked matches read 3 in the grid, not 6 (the club card under its own grade plus CA's claim)",
          g["grid_matches"] == 3, str(g["grid_matches"]))
    check("they sit under Cricket Australia's grade name, the one CA's claim is filed under",
          g["season_rows"][0]["grades"] == {CA_NAME: 3}, str(g["season_rows"][0]["grades"]))
    check("the by-grade table names one grade, not the club's name beside the competition's",
          [r["grade_name"] for r in g["rows"]] == [CA_NAME], str([(r["grade_name"], r["matches"]) for r in g["rows"]]))
    check("the profile header reads 3", await header("LINKED") == 3, str(await header("LINKED")))
    check("the batting board agrees", await board("LINKED") == 3, str(await board("LINKED")))

    print("\n-- A CARD NO ONE ELSE HOLDS KEEPS THE GRADE IT WAS TYPED UNDER --")
    g = await grid("CARDONLY")
    check("2 card-only matches read 2 under the club's grade name", g["grid_matches"] == 2
          and g["season_rows"][0]["grades"] == {CLUB_NAME: 2}, str(g["season_rows"][0]["grades"]))
    check("the header reads 2", await header("CARDONLY") == 2, str(await header("CARDONLY")))

    print("\n-- LINKED AND CARD-ONLY MATCHES SIT SIDE BY SIDE --")
    g = await grid("MIXED")
    check("2 linked and 1 card-only read 3: the linked pair under CA's grade, the book's own match under the club's",
          g["grid_matches"] == 3 and g["season_rows"][0]["grades"] == {CA_NAME: 2, CLUB_NAME: 1}, str(g["season_rows"][0]["grades"]))

    print("\n-- AN UNLINKED PAIR IS STILL TWO COPIES, until a person links it --")
    g = await grid("UNLINKED")
    check("a card and a CA game nothing links count twice (Card review's Possible doubles finds them)", g["grid_matches"] == 2, str(g["grid_matches"]))

    print("\n-- A SAME-CLUB FIXTURE: THE SIDE WITHOUT A LINK IS THE GAME THE OTHER SIDE'S CARD HIDES --")
    for key, what in (("SHADOW", "no link"), ("WRONG", "a link to an unrelated Women's game")):
        g = await grid(key)
        check(f"{key} ({what}): 3 matches in one CA cell, not 4", g["grid_matches"] == 3
              and g["season_rows"][0]["grades"] == {CA_NAME: 3}, f"{g['grid_matches']} {g['season_rows'][0]['grades']}")
        # The profile header's own base also adds a card nothing links onto the season total CA gave (the view's
        # `manual_game` branch), which is a separate rule this suite leaves alone, so only the linked-to-wrong
        # case is read through the header here.
        check(f"{key}: the board reads the same 3", await board(key) == 3, str(await board(key)))
        if key == "WRONG":
            check("WRONG: the profile header reads 3", await header(key) == 3, str(await header(key)))
    g = await grid("OTHER")
    check("the other side's player (the card that hides the game holds them) reads 2 (one per fixture) under CA's grade",
          g["grid_matches"] == 2 and g["season_rows"][0]["grades"] == {CA_NAME: 2}, str(g["season_rows"][0]["grades"]))
    g = await grid("STRANGER")
    check("a card on that day for a player the hidden game does not name keeps its own grade",
          g["grid_matches"] == 1 and g["season_rows"][0]["grades"] == {CLUB_NAME: 1}, str(g["season_rows"][0]["grades"]))

    await engine.dispose()
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
