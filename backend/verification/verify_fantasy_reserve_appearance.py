"""A 12th man who never took the field does not get the Fantasy appearance point, against a real Postgres.

Found while checking Sunbury CC's Fantasy scores against their scorecards (Nov 2026). The engine reads
`game_appearances` for the +4 "took the field" point and ignored `is_reserve`, the flag the rest of the
platform uses (match counts, fees, StatLab: `services/reserve_players.py`, `game_status`) for a name on
the team sheet who is not on the card at all. A late withdrawal carries the same flag with no sheet slot
(`services/withdrawn_appearances.py`). Both scored 4 points for sitting out.

A reserve who DID do something (a substitute fielder who took a catch) has a row of their own and keeps the
appearance, as everywhere else. NULL (not judged) reads as played.

Drives the shipped `fantasy_engine._round_player_scores`. CONTROL: on the previous commit the two
reserves who did nothing are scored 4 each, so those checks fail.

Run, on its own database:
  DATABASE_URL=postgresql+asyncpg://root@/fantasy_v?host=/tmp/pgsock python verification/verify_fantasy_reserve_appearance.py
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

import verify_fantasy_live_sync as V
from app.models.db import FantasyRound, FantasySeason
from app.services import fantasy_engine

ORG, SEASON, GRADE, GAME = (uuid.uuid4() for _ in range(4))
FS, RND = uuid.uuid4(), uuid.uuid4()
DAY = date(2026, 11, 7)
PLAYED, DNB, RESERVE, WITHDRAWN, UNJUDGED, SUB_CATCH = (uuid.uuid4() for _ in range(6))
NAMES = {PLAYED: "Opener", DNB: "Did Not Bat", RESERVE: "Twelfth Man", WITHDRAWN: "Pulled Out",
         UNJUDGED: "Not Judged", SUB_CATCH: "Sub Fielder"}


async def main() -> None:
    await V.build_schema()
    async with V.Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)
        await ex("INSERT INTO organisations (id, name, slug, is_active, state) VALUES (:i,'Club','club',true,'VIC')", i=ORG)
        await ex("INSERT INTO seasons (id, organisation_id, name, year, grassroots_id) VALUES (:i,:o,'S',2026,:g)",
                 i=SEASON, o=ORG, g=str(SEASON))
        await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
                 "VALUES (:i,:s,'3rd XI',:g,'senior',ARRAY['senior'])", i=GRADE, s=SEASON, g=str(GRADE))
        for pid, nm in NAMES.items():
            await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) VALUES (:i,:o,:n,:g,'active')",
                     i=pid, o=ORG, n=nm, g=str(pid))
        await ex("INSERT INTO games (id, grade_id, played_at, home_team, away_team, home_org_id, status) "
                 "VALUES (:g,:gr,:d,'Club 3rd XI','Them 3rd XI',:o,'COMPLETED')", g=GAME, gr=GRADE, d=DAY, o=ORG)
        # (player, is_reserve, sheet_slot)
        for pid, flag, slot in ((PLAYED, False, 1), (DNB, False, 11), (RESERVE, True, 12), (WITHDRAWN, True, None),
                                (UNJUDGED, None, 12), (SUB_CATCH, True, 12)):
            await ex("INSERT INTO game_appearances (game_id, player_id, team_name, is_reserve, sheet_slot) "
                     "VALUES (:g,:p,'Club 3rd XI',:r,:s)", g=GAME, p=pid, r=flag, s=slot)
        await ex("INSERT INTO batting_innings (game_id, player_id, innings_number, batting_position, runs, balls, fours, sixes, "
                 "not_out, dismissal_type, did_not_bat) VALUES (:g,:p,1,1,30,40,2,0,false,'bowled',false)", g=GAME, p=PLAYED)
        await ex("INSERT INTO batting_innings (game_id, player_id, innings_number, batting_position, not_out, did_not_bat) "
                 "VALUES (:g,:p,1,9,false,true)", g=GAME, p=DNB)
        await ex("INSERT INTO fielding_stats (game_id, player_id, catches, catches_wk, run_outs, stumpings) "
                 "VALUES (:g,:p,1,0,0,0)", g=GAME, p=SUB_CATCH)
        await s.commit()
    async with V.Session() as s:
        s.add(FantasySeason(id=FS, organisation_id=ORG, season_year=2026, name="Fantasy", status="active", scoring={}, rules={}))
        await s.flush()
        s.add(FantasyRound(id=RND, fantasy_season_id=FS, organisation_id=ORG, round_number=1, name="Round 1",
                           start_date=date(2026, 11, 6), end_date=date(2026, 11, 9)))
        await s.commit()
    async with V.Session() as s:
        fs, rnd = await s.get(FantasySeason, FS), await s.get(FantasyRound, RND)
        got = await fantasy_engine._round_player_scores(s, fs, rnd)

    def pts(p):
        r = got.get(str(p))
        return None if r is None else float(r["total"])

    V.check("the batter is scored: 30 runs + 2 fours + 4 for playing", pts(PLAYED) == 36.0, str(pts(PLAYED)))
    V.check("a player who was in the side and did not bat still gets the appearance point", pts(DNB) == 4.0, str(pts(DNB)))
    V.check("a 12th man named on the sheet and nowhere else scores nothing", pts(RESERVE) is None, str(pts(RESERVE)))
    V.check("a late withdrawal (reserve flag, no sheet slot) scores nothing", pts(WITHDRAWN) is None, str(pts(WITHDRAWN)))
    V.check("a player nobody has judged yet reads as played: 4", pts(UNJUDGED) == 4.0, str(pts(UNJUDGED)))
    V.check("a reserve who took a catch has a row of their own: catch 8 + appearance 4", pts(SUB_CATCH) == 12.0, str(pts(SUB_CATCH)))
    print(f"\n{V.PASS} passed, {V.FAIL} failed")
    sys.exit(1 if V.FAIL else 0)


asyncio.run(main())
