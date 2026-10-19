"""Verification: `python -m app.scripts.move_game_rows`, against a real Postgres.

A game synced after an undone merge sits on the wrong player. The script hands the rows for the
NAMED games to the right player and nothing else:

  * a dry run reports the rows and changes nothing
  * --apply moves every row for the named game (all ten places) and leaves another game alone
  * a receiver that already has a row in the game is refused; so is a player of another club
  * the audit entry restores it exactly, once

CONTROL: with the move disabled, the moved and restored checks fail while the dry-run ones pass.

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_move_game_rows_script.py
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

from app.models.db import Base, async_session_maker, engine
import verify_merge_carry as mc
from app.scripts import move_game_rows as script

PASS = FAIL = 0


def check(label, got, want=True):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}: got {got!r}, want {want!r}")


async def one(sql, **kw):
    async with async_session_maker() as db:
        return (await db.execute(text(sql), kw)).scalar()


async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for ddl in mc.EXTRA_DDL:
            await conn.execute(text(ddl))
    org, other, season, grade = (uuid.uuid4() for _ in range(4))
    src, dst, foreign, mate = (uuid.uuid4() for _ in range(4))
    g1, g2, g3, g4 = (uuid.uuid4() for _ in range(4))
    async with async_session_maker() as db:
        await db.execute(text("INSERT INTO organisations (id,name,slug,is_active) VALUES (:o,'Mv','mv-t',true),(:p,'Mv2','mv-t2',true)"), {"o": str(org), "p": str(other)})
        await db.execute(text("INSERT INTO seasons (id,organisation_id,name,year) VALUES (:s,:o,'S',2026)"), {"s": str(season), "o": str(org)})
        await db.execute(text("INSERT INTO grades (id,season_id,name) VALUES (:g,:s,'G')"), {"g": str(grade), "s": str(season)})
        for pid, o in ((src, org), (dst, org), (mate, org), (foreign, other)):
            await db.execute(text("INSERT INTO players (id,organisation_id,name,grassroots_id) VALUES (:i,:o,'p',:i2)"), {"i": str(pid), "o": str(o), "i2": str(pid)})
        for gid, d in ((g1, date(2026, 10, 17)), (g2, date(2026, 10, 10)), (g3, date(2026, 10, 3)), (g4, date(2026, 9, 26))):
            await db.execute(text("INSERT INTO games (id,grade_id,played_at) VALUES (:g,:gr,:d)"), {"g": str(gid), "gr": str(grade), "d": d})
        s = str(src)
        for g in (g1, g2):
            gs = str(g)
            await db.execute(text("INSERT INTO game_appearances (game_id,player_id,team_name) VALUES (:g,:p,'x')"), {"g": gs, "p": s})
            await db.execute(text("INSERT INTO batting_innings (game_id,innings_number,player_id) VALUES (:g,1,:p)"), {"g": gs, "p": s})
            await db.execute(text("INSERT INTO bowling_spells (game_id,innings_number,player_id) VALUES (:g,1,:p)"), {"g": gs, "p": s})
            await db.execute(text("INSERT INTO fielding_stats (game_id,player_id) VALUES (:g,:p)"), {"g": gs, "p": s})
            await db.execute(text("INSERT INTO fall_of_wickets (game_id,innings_number,wicket_number,player_id) VALUES (:g,1,1,:p)"), {"g": gs, "p": s})
            await db.execute(text("INSERT INTO bowler_wickets (game_id,innings_number,bowler_id,fielder_id,dismissal_type) VALUES (:g,1,:p,:m,'caught')"), {"g": gs, "p": s, "m": str(mate)})
            await db.execute(text("INSERT INTO partnerships (game_id,innings_number,wicket_number,batter1_id,batter2_id) VALUES (:g,1,1,:p,:m)"), {"g": gs, "p": s, "m": str(mate)})
            await db.execute(text("INSERT INTO milestones (player_id,game_id,milestone_type,milestone_value) VALUES (:p,:g,'fifty',50)"), {"g": gs, "p": s})
        # the receiver has rows in a different game only
        await db.execute(text("INSERT INTO game_appearances (game_id,player_id,team_name) VALUES (:g,:p,'x')"), {"g": str(g3), "p": str(dst)})
        # one game both players hold a row in
        for pl in (src, dst):
            await db.execute(text("INSERT INTO game_appearances (game_id,player_id,team_name) VALUES (:g,:p,'x')"), {"g": str(g4), "p": str(pl)})
        await db.commit()

    async def total(player):
        n = 0
        for sql in ("SELECT COUNT(*) FROM game_appearances WHERE player_id=:p", "SELECT COUNT(*) FROM batting_innings WHERE player_id=:p",
                    "SELECT COUNT(*) FROM bowling_spells WHERE player_id=:p", "SELECT COUNT(*) FROM fielding_stats WHERE player_id=:p",
                    "SELECT COUNT(*) FROM fall_of_wickets WHERE player_id=:p", "SELECT COUNT(*) FROM bowler_wickets WHERE bowler_id=:p",
                    "SELECT COUNT(*) FROM partnerships WHERE batter1_id=:p", "SELECT COUNT(*) FROM milestones WHERE player_id=:p"):
            n += await one(sql, p=str(player))
        return n

    print("\n# A. Dry run and refusals")
    before = await total(src)
    code = await script.run(str(org), str(src), str(dst), [str(g1)], apply=False, by="")
    check("dry run exits clean", code, 0)
    check("...and moves nothing", await total(src), before)
    check("a player of another club is refused", await script.run(str(org), str(src), str(foreign), [str(g1)], True, "t"), 1)
    check("--apply without --by is refused", await script.run(str(org), str(src), str(dst), [str(g1)], True, ""), 1)
    check("a game the source has no rows in moves nothing (non-zero exit)", await script.run(str(org), str(src), str(dst), [str(g3)], False, ""), 1)
    check("a receiver that already has a row in the game is refused", await script.run(str(org), str(src), str(dst), [str(g4)], True, "t"), 1)
    check("...and the source still has that row", await one("SELECT COUNT(*) FROM game_appearances WHERE player_id=:p AND game_id=:g", p=str(src), g=str(g4)), 1)

    print("\n# B. Apply")
    code = await script.run(str(org), str(src), str(dst), [str(g1)], apply=True, by="jack")
    check("apply exits clean", code, 0)
    d = str(dst)
    check("the receiver holds the game's rows in all ten places",
          (await one("SELECT COUNT(*) FROM game_appearances WHERE player_id=:p AND game_id=:g", p=d, g=str(g1)),
           await one("SELECT COUNT(*) FROM batting_innings WHERE player_id=:p AND game_id=:g", p=d, g=str(g1)),
           await one("SELECT COUNT(*) FROM bowling_spells WHERE player_id=:p AND game_id=:g", p=d, g=str(g1)),
           await one("SELECT COUNT(*) FROM fielding_stats WHERE player_id=:p AND game_id=:g", p=d, g=str(g1)),
           await one("SELECT COUNT(*) FROM fall_of_wickets WHERE player_id=:p AND game_id=:g", p=d, g=str(g1)),
           await one("SELECT COUNT(*) FROM bowler_wickets WHERE bowler_id=:p AND game_id=:g", p=d, g=str(g1)),
           await one("SELECT COUNT(*) FROM partnerships WHERE batter1_id=:p AND game_id=:g", p=d, g=str(g1)),
           await one("SELECT COUNT(*) FROM milestones WHERE player_id=:p AND game_id=:g", p=d, g=str(g1))), (1,) * 8)
    check("the other game stays with the source", await one("SELECT COUNT(*) FROM batting_innings WHERE player_id=:p AND game_id=:g", p=str(src), g=str(g2)), 1)
    check("the receiver's own game is untouched", await one("SELECT COUNT(*) FROM game_appearances WHERE player_id=:p AND game_id=:g", p=d, g=str(g3)), 1)
    check("the fielder in bowler_wickets and batter 2 in partnerships are unchanged",
          await one("SELECT COUNT(*) FROM partnerships WHERE batter2_id=:m AND game_id=:g", m=str(mate), g=str(g1)), 1)
    aid = await one("SELECT id FROM audit_logs WHERE org_id=:o AND action='move_game_rows'", o=str(org))
    check("one audit entry names who moved it", await one("SELECT details->>'by' FROM audit_logs WHERE id=:i", i=aid), "jack")

    print("\n# C. Restore")
    check("another club cannot restore it", await script.restore(str(other), aid, "t"), 1)
    code = await script.restore(str(org), aid, "jack")
    check("restore exits clean", code, 0)
    check("the source has its rows back", await total(src), before)
    check("a second restore is refused", await script.restore(str(org), aid, "jack"), 1)

    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
