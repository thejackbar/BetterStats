"""The Fantasy health check names each cause and says nothing about a healthy season, against a real Postgres.

`services/fantasy_audit.audit_season` (and `python -m app.scripts.fantasy_audit`) was written after Sunbury CC
(Nov 2026): four players scored nothing and the rounds did not follow the draw, with causes that look alike
from the member screens. It must find: a round longer than two weeks, a game dated outside every round, a round
that ended unconfirmed while a later one started (members see the first unscored round as the live one), and a
player whose stored points differ from the scorecards. A season with none of those reports nothing, and a
pair of weeks bridged by a two day game (8 days) is NOT called a long round. No Cricket Australia calls
(`check_draw=False`).

Run, on its own database:
  DATABASE_URL=postgresql+asyncpg://root@/fantasy_v?host=/tmp/pgsock python verification/verify_fantasy_audit.py
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
from app.models.db import FantasySeason

ORG, SEASON, GRADE, G_IN, G_OUT = (uuid.uuid4() for _ in range(5))
FS = uuid.uuid4()
PLAYER = uuid.uuid4()
TODAY = date(2026, 11, 10)


async def add_round(s, n, start, end, status):
    await s.execute(text("""INSERT INTO fantasy_rounds (fantasy_season_id, organisation_id, round_number, name, start_date, end_date, status)
        VALUES (:f,:o,:n,:nm,:s,:e,:st)"""), {"f": FS, "o": ORG, "n": n, "nm": f"Round {n}", "s": start, "e": end, "st": status})


async def main() -> None:
    try:
        from app.services import fantasy_audit
    except ImportError:   # control run on the commit before the module existed
        fantasy_audit = None
    await V.build_schema()
    async with V.Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)
        await ex("INSERT INTO organisations (id, name, slug, is_active, state) VALUES (:i,'Club','club',true,'VIC')", i=ORG)
        await ex("INSERT INTO seasons (id, organisation_id, name, year, grassroots_id) VALUES (:i,:o,'S',2026,:g)", i=SEASON, o=ORG, g=str(SEASON))
        await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) VALUES (:i,:s,'3rd XI',:g,'senior',ARRAY['senior'])",
                 i=GRADE, s=SEASON, g=str(GRADE))
        await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) VALUES (:i,:o,'Sam Fisher',:g,'active')", i=PLAYER, o=ORG, g=str(PLAYER))
        for gid, day in ((G_IN, date(2026, 11, 7)), (G_OUT, date(2027, 1, 30))):
            await ex("INSERT INTO games (id, grade_id, played_at, home_team, away_team, home_org_id, status) "
                     "VALUES (:g,:gr,:d,'Club 3rd XI','Them 3rd XI',:o,'COMPLETED')", g=gid, gr=GRADE, d=day, o=ORG)
            await ex("INSERT INTO game_appearances (game_id, player_id, team_name) VALUES (:g,:p,'Club 3rd XI')", g=gid, p=PLAYER)
        await ex("INSERT INTO batting_innings (game_id, player_id, innings_number, batting_position, runs, balls, fours, sixes, not_out, dismissal_type, did_not_bat) "
                 "VALUES (:g,:p,1,3,73,106,8,0,false,'run out',false)", g=G_IN, p=PLAYER)
        await s.commit()
    async with V.Session() as s:
        s.add(FantasySeason(id=FS, organisation_id=ORG, season_year=2026, name="Fantasy", status="active", scoring={}, rules={}))
        await s.flush()
        # 1: a normal pair of weeks bridged by a two day game, confirmed.  2: 51 days, ended, unconfirmed.  3: has started.
        await add_round(s, 1, date(2026, 10, 17), date(2026, 10, 25), "scored")
        await add_round(s, 2, date(2026, 10, 30), date(2026, 11, 5), "upcoming")
        await add_round(s, 3, date(2026, 11, 6), date(2026, 11, 9), "upcoming")
        await add_round(s, 4, date(2026, 11, 10), date(2026, 12, 30), "upcoming")
        await s.commit()
    async with V.Session() as s:
        fs = await s.get(FantasySeason, FS)
        res = await fantasy_audit.audit_season(s, fs, check_draw=False, today=TODAY) if fantasy_audit else {}
        probs = fantasy_audit.problems(res) if fantasy_audit else []
    text_ = " | ".join(probs)
    V.check("the module exists", fantasy_audit is not None)
    V.check("a round longer than two weeks is named, with its dates",
            any(r.get("round") == 4 and r.get("days") == 50 for r in res.get("long_rounds", [])) and "2026-11-10 to 2026-12-30" in text_, text_)
    V.check("the 8 day pair of weeks is not called a long round",
            not any(r.get("round") == 1 for r in res.get("long_rounds", [])), str(res.get("long_rounds")))
    unc = res.get("uncovered_games", [])
    V.check("a game dated outside every round (30 Jan, after round 4 ends) is named, and one inside a round is not",
            [g["date"] for g in unc] == ["2027-01-30"] and "fall in no round" in text_, str(unc))
    b = res.get("blocking_round") or {}
    V.check("a round that ended unconfirmed while later rounds started is named as hiding them",
            b.get("round") == 2 and b.get("hides") == [3, 4], str(b))
    d = {x["round"]: x for x in res.get("drift", [])}
    V.check("Sam Fisher's 73 is in the scorecards and not in the stored points: round 3 drifts by name",
            3 in d and any("Sam Fisher 0 -> " in n for n in d[3]["names"]), str(res.get("drift")))
    V.check("a running round's drift is marked running, a confirmed one is not",
            d.get(3, {}).get("running") is True and 1 not in d, str(d))

    # a healthy season: one normal round, scored, matching its scorecards, nothing else
    async with V.Session() as s:
        await s.execute(text("DELETE FROM fantasy_rounds WHERE fantasy_season_id = :f"), {"f": FS})
        await s.execute(text("DELETE FROM games WHERE id = :g"), {"g": G_OUT})
        await s.commit()
        await add_round(s, 1, date(2026, 11, 6), date(2026, 11, 9), "upcoming")
        await s.commit()
    async with V.Session() as s:
        fs = await s.get(FantasySeason, FS)
        from app.models.db import FantasyRound
        from app.services import fantasy_engine
        rnd = (await s.execute(text("SELECT id FROM fantasy_rounds WHERE fantasy_season_id = :f"), {"f": FS})).scalar()
        await fantasy_engine.settle_round(s, fs, await s.get(FantasyRound, rnd))
        await s.commit()
    async with V.Session() as s:
        fs = await s.get(FantasySeason, FS)
        res = await fantasy_audit.audit_season(s, fs, check_draw=False, today=TODAY)
        probs = fantasy_audit.problems(res)
    V.check("a healthy season reports nothing at all", probs == [], " | ".join(probs))
    print(f"\n{V.PASS} passed, {V.FAIL} failed")
    sys.exit(1 if V.FAIL else 0)


asyncio.run(main())
