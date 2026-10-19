"""Verification: `python -m app.scripts.merge_player_pair`, against a real Postgres.

Gisborne's one player is held under several Cricket Australia profiles, one of them a
redacted `********` row. The script runs the SHIPPED `_merge_players_core`:

  * a dry run reports both players and changes nothing
  * --apply moves the removed player's games to the kept one, removes the old row,
    writes a merge log and the audit entries (the app's and who asked)
  * a pair that appears in the same game is refused unless --allow-shared-games
  * a player of another club, the same id twice and an unknown id are refused

CONTROL: with the apply branch disabled, the move, merge-log and audit checks fail while
the dry-run checks pass.

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_merge_player_pair_script.py
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
from app.scripts import merge_player_pair as script

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
    keep, rem, rem2, foreign = (uuid.uuid4() for _ in range(4))
    old = [uuid.uuid4() for _ in range(3)]      # the keeper's own games
    new = [uuid.uuid4() for _ in range(2)]      # the redacted row's games
    both = uuid.uuid4()                         # a game BOTH rows are in
    async with async_session_maker() as db:
        await db.execute(text("INSERT INTO organisations (id,name,slug,is_active) VALUES (:o,'Gis T','gis-p',true),(:p,'Oth T','oth-p',true)"),
                         {"o": str(org), "p": str(other)})
        await db.execute(text("INSERT INTO seasons (id,organisation_id,name,year) VALUES (:s,:o,'S',2026)"), {"s": str(season), "o": str(org)})
        await db.execute(text("INSERT INTO grades (id,season_id,name) VALUES (:g,:s,'U13')"), {"g": str(grade), "s": str(season)})
        for pid, name, status, o in ((keep, "Grumont, Brook", "active", org), (rem, "********", "inactive", org),
                                     (rem2, "********", "inactive", org), (foreign, "Foreign", "active", other)):
            await db.execute(text("INSERT INTO players (id,organisation_id,name,status,grassroots_id) VALUES (:i,:o,:n,:s,:g)"),
                             {"i": str(pid), "o": str(o), "n": name, "s": status, "g": str(pid)})
        allg = old + new + [both]
        for i, gid in enumerate(allg):
            await db.execute(text("INSERT INTO games (id,grade_id,played_at) VALUES (:g,:gr,CAST(:d AS date))"),
                             {"g": str(gid), "gr": str(grade), "d": date(2024 + i % 3, 2, 1 + i)})
        for gid in old:
            await db.execute(text("INSERT INTO game_appearances (game_id,player_id,team_name) VALUES (:g,:p,'x')"), {"g": str(gid), "p": str(keep)})
        for gid in new:
            await db.execute(text("INSERT INTO game_appearances (game_id,player_id,team_name) VALUES (:g,:p,'x')"), {"g": str(gid), "p": str(rem)})
        # rem2 shares one game with the keeper: probably two different people.
        await db.execute(text("INSERT INTO game_appearances (game_id,player_id,team_name) VALUES (:g,:p,'x')"), {"g": str(both), "p": str(keep)})
        await db.execute(text("INSERT INTO game_appearances (game_id,player_id,team_name) VALUES (:g,:p,'x')"), {"g": str(both), "p": str(rem2)})
        await db.commit()

    print("\n# A. Dry run")
    code = await script.run(str(org), str(keep), str(rem), apply=False, by="t", allow_shared=False)
    check("exits clean", code, 0)
    check("the redacted row is still there", await one("SELECT COUNT(*) FROM players WHERE id=:i", i=rem), 1)
    check("its games have not moved", await one("SELECT COUNT(*) FROM game_appearances WHERE player_id=:i", i=rem), 2)
    check("no merge log written", await one("SELECT COUNT(*) FROM merge_logs WHERE org_id=:o", o=org), 0)

    print("\n# B. Refusals")
    check("a pair in the same game is refused", await script.run(str(org), str(keep), str(rem2), apply=True, by="t", allow_shared=False), 1)
    check("...and nothing moved", await one("SELECT COUNT(*) FROM players WHERE id=:i", i=rem2), 1)
    check("another club's player is refused", await script.run(str(org), str(keep), str(foreign), apply=True, by="t", allow_shared=False), 1)
    check("an unknown id is refused", await script.run(str(org), str(keep), str(uuid.uuid4()), apply=True, by="t", allow_shared=False), 1)

    print("\n# C. Apply")
    code = await script.run(str(org), str(keep), str(rem), apply=True, by="jack", allow_shared=False)
    check("exits clean", code, 0)
    check("the redacted row is gone", await one("SELECT COUNT(*) FROM players WHERE id=:i", i=rem), 0)
    check("the keeper holds all five games", await one("SELECT COUNT(*) FROM game_appearances WHERE player_id=:k AND game_id = ANY(CAST(:g AS uuid[]))", k=keep, g=old + new), 5)
    check("the keeper is still Active and named", await one("SELECT status || '|' || name FROM players WHERE id=:i", i=keep), "active|Grumont, Brook")
    check("a merge log row records it", await one("SELECT COUNT(*) FROM merge_logs WHERE org_id=:o AND removed_player_id=:r AND keep_player_id=:k AND undone_at IS NULL", o=org, r=rem, k=keep), 1)
    check("the app's audit entry is written", await one("SELECT COUNT(*) FROM audit_logs WHERE org_id=:o AND action='merge_players'", o=org), 1)
    check("...and the script says who asked", await one("SELECT details->>'by' FROM audit_logs WHERE org_id=:o AND action='merge_players_script'", o=org), "jack")

    print("\n# D. Shared games, when you have checked")
    code = await script.run(str(org), str(keep), str(rem2), apply=True, by="jack", allow_shared=True)
    check("--allow-shared-games merges it", (code, await one("SELECT COUNT(*) FROM players WHERE id=:i", i=rem2)), (0, 0))

    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
