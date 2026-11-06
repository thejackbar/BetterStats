"""The Merge Duplicates cards count a scorebook-only player's games, runs and span of years.

Reported off Payneham: a pair "Zia, MYB" / "Zia, M" showed 0 seasons, 0 runs, 0 wickets and 0 innings on
both cards, while the profile of MYB Zia reads 20 matches over two seasons. The cards counted only
Cricket Australia's season rows and the synced batting innings, so every player who exists only in the
club's scorebook (a CricketStatz import, a typed card) looked empty and the person deciding had nothing
to go on.

Reads `get_merge_candidates` and `get_player_info` through their route bodies against a real Postgres,
with the production views. The same file against the previous commit is the control: it fails on the
numbers and reads the new keys through `.get` so absence is reported, not a crash.

Run:
  DATABASE_URL=postgresql+asyncpg://root@/pl_m?host=/var/run/postgresql python verification/verify_merge_card_figures.py
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

from verify_board_games_match_profile import build_schema
from app.routers.admin import get_merge_candidates, get_player_info
from app.services import superseded_ddl

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
SEASONS = {2019: uuid.uuid4(), 2020: uuid.uuid4()}
GRADE = {2019: uuid.uuid4(), 2020: uuid.uuid4()}
P = {k: uuid.uuid4() for k in ("MYB", "M", "CA_FULL", "CA_INIT")}
NAMES = {"MYB": "Zia, MYB", "M": "Zia, M", "CA_FULL": "Fenwick, Callum", "CA_INIT": "Fenwick, C"}


async def seed() -> None:
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)

        await ex("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, 'Merge Club', 'merge-club', true)", i=ORG)
        for y, sid in SEASONS.items():
            await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, :n, :y)", i=sid, o=ORG,
                     n=f"Summer {y}/{str(y + 1)[2:]}", y=y)
            await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
                     "VALUES (:i, :s, 'U/12', :g, 'junior', ARRAY['junior'])", i=GRADE[y], s=sid, g=str(GRADE[y]))
        for k, pid in P.items():
            await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) VALUES (:i, :o, :n, :g, 'active')",
                     i=pid, o=ORG, n=NAMES[k], g=(str(pid) if k == "CA_FULL" else None))

        async def card(key, y, day, runs):
            mid = uuid.uuid4()
            await ex("INSERT INTO manual_games (id, organisation_id, season_id, grade_id, played_at, opposition, result, match_format, "
                     " pair_prefers_import, pairing_locked) VALUES (:m, :o, :s, :g, :d, 'Opposition', 'WIN', 'One Day', false, false)",
                     m=mid, o=ORG, s=SEASONS[y], g=GRADE[y], d=date(y, 11, day))
            await ex("INSERT INTO manual_batting_innings (manual_game_id, player_id, innings_number, batting_position, runs, balls, "
                     " dismissal_type, not_out, did_not_bat) VALUES (:m, :p, 1, 3, :r, NULL, 'bowled', false, false)",
                     m=mid, p=P[key], r=runs)

        # MYB: scorebook only, three cards over two seasons. M: a record with nothing at all.
        await card("MYB", 2019, 3, 4)
        await card("MYB", 2019, 10, 10)
        await card("MYB", 2020, 7, 41)
        # CA_INIT: one scorebook card. CA_FULL: the Cricket Australia record, a season aggregate and no scorecards.
        await card("CA_INIT", 2020, 14, 22)
        await ex("INSERT INTO player_season_stats (player_id, season_id, matches, batting_innings, runs, not_outs, wickets, "
                 " catches, source) VALUES (:p, :s, 9, 0, 150, 0, 6, 0, 'api')", p=P["CA_FULL"], s=SEASONS[2019])
        await s.commit()


def pair_of(rows, a, b):
    ids = {str(a), str(b)}
    for r in rows:
        if {r["player_a"]["id"], r["player_b"]["id"]} == ids:
            return r
    return None


async def main() -> None:
    await build_schema()
    async with engine.begin() as conn:
        for stmt in superseded_ddl.STATEMENTS:
            await conn.execute(text(stmt))
        # The same shape main.py's lifespan creates; the harness schema is built from the models alone.
        await conn.execute(text("""CREATE TABLE IF NOT EXISTS merge_pair_ignores (
            id SERIAL PRIMARY KEY, org_id UUID NOT NULL, player_a_id UUID NOT NULL,
            player_b_id UUID NOT NULL, created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (org_id, player_a_id, player_b_id))"""))
    await seed()

    async with Session() as s:
        rows = await get_merge_candidates(org_id=str(ORG), db=s, _=None)
    print("\n-- A SCOREBOOK-ONLY PLAYER IS NOT EMPTY --")
    r = pair_of(rows, P["MYB"], P["M"])
    check("the pair 'Zia, MYB' / 'Zia, M' is listed (a name variant)", r is not None and r["kind"] == "name_variant",
          str([x["kind"] for x in rows]))
    cards = {c["id"]: c for c in (r["player_a"], r["player_b"])} if r else {}
    myb, m = cards.get(str(P["MYB"]), {}), cards.get(str(P["M"]), {})
    check("MYB reads 3 games", myb.get("games_held") == 3, str(myb))
    check("MYB reads 2 seasons", myb.get("seasons_count") == 2, str(myb.get("seasons_count")))
    check("MYB reads 55 runs", myb.get("total_runs") == 55, str(myb.get("total_runs")))
    check("MYB reads 3 innings", myb.get("game_level_innings") == 3, str(myb.get("game_level_innings")))
    check("MYB's span runs from the first card to the last",
          myb.get("first_game") == "2019-11-03" and myb.get("last_game") == "2020-11-07",
          f"{myb.get('first_game')} {myb.get('last_game')}")
    check("a record with nothing at all still reads 0 and no span (the zero is a true one)",
          m.get("games_held") == 0 and m.get("total_runs") == 0 and m.get("first_game") is None, str(m))

    print("\n-- A CRICKET AUSTRALIA RECORD KEEPS ITS SEASON FIGURES --")
    r2 = pair_of(rows, P["CA_FULL"], P["CA_INIT"])
    check("'Fenwick, C' beside 'Fenwick, Callum' is listed", r2 is not None, str([(x["player_a"]["name"], x["player_b"]["name"]) for x in rows]))
    cards2 = {c["id"]: c for c in (r2["player_a"], r2["player_b"])} if r2 else {}
    full, init = cards2.get(str(P["CA_FULL"]), {}), cards2.get(str(P["CA_INIT"]), {})
    check("the Cricket Australia record reads its aggregate: 150 runs, 6 wickets, 1 season",
          (full.get("total_runs"), full.get("total_wickets"), full.get("seasons_count")) == (150, 6, 1), str(full))
    check("the initials record reads its one scorebook game and 22 runs",
          (init.get("games_held"), init.get("total_runs")) == (1, 22), str(init))

    print("\n-- THE SINGLE-PLAYER READ AGREES --")
    async with Session() as s:
        one = await get_player_info(player_id=str(P["MYB"]), org_id=str(ORG), db=s, _=None)
    check("player-info reads the same figures as the list", (one.get("games_held"), one.get("total_runs")) == (3, 55), str(one))

    await engine.dispose()
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
