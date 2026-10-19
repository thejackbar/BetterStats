"""Verification: `python -m app.scripts.undo_player_merge`, against a real Postgres.

Gisborne's redacted juniors were merged on 14 Oct; one merge may need reversing. The
script runs the SHIPPED `undo_merge` body (the Admin Undo button), so this drives a real
merge with the shipped `_merge_players_core` and then the script's `run`:

  * a dry run reports the games it would move back and changes nothing
  * --apply re-creates the removed player (same id, same Cricket Australia id), moves
    back exactly the games the merge moved, marks the log undone and audits who asked
  * a game that synced AFTER the merge is not in the log and stays on the kept player
  * a second run finds it already undone and changes nothing
  * another club's merge log id is refused, not undone
  * a newer live merge on the same player blocks the undo and says so

CONTROL: run with the script's apply branch skipped (`--apply` ignored): the restore,
undone and audit checks fail while the dry-run checks still pass.

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_undo_player_merge_script.py
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
from app.routers.admin import _merge_players_core
import verify_merge_carry as mc
from app.scripts import undo_player_merge as script

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
    org, other_org, season, grade = (uuid.uuid4() for _ in range(4))
    keep, rem, third = (uuid.uuid4() for _ in range(3))
    games = [uuid.uuid4() for _ in range(3)]
    late = uuid.uuid4()
    async with async_session_maker() as db:
        await db.execute(text("INSERT INTO organisations (id,name,slug,is_active) VALUES (:o,'Gisborne T','gis-t',true),(:p,'Other T','oth-t',true)"),
                         {"o": str(org), "p": str(other_org)})
        await db.execute(text("INSERT INTO seasons (id,organisation_id,name,year) VALUES (:s,:o,'S',2026)"), {"s": str(season), "o": str(org)})
        await db.execute(text("INSERT INTO grades (id,season_id,name) VALUES (:g,:s,'U13')"), {"g": str(grade), "s": str(season)})
        for pid, name in ((keep, "********"), (rem, "********"), (third, "Bystander")):
            await db.execute(text("INSERT INTO players (id,organisation_id,name,grassroots_id) VALUES (:i,:o,:n,:g)"),
                             {"i": str(pid), "o": str(org), "n": name, "g": str(pid)})
        for i, gid in enumerate(games + [late]):
            await db.execute(text("INSERT INTO games (id,grade_id,played_at) VALUES (:g,:gr,CAST(:d AS date))"),
                             {"g": str(gid), "gr": str(grade), "d": date(2026, 2, 1 + i)})
        # keep has game 0; the removed player has games 1 and 2.
        for gid, pid in ((games[0], keep), (games[1], rem), (games[2], rem)):
            await db.execute(text("INSERT INTO game_appearances (game_id,player_id,team_name) VALUES (:g,:p,'U13')"),
                             {"g": str(gid), "p": str(pid)})
        await db.commit()
    async with async_session_maker() as db:
        await _merge_players_core(db, keep, rem, org, mc.FakeUser())
        await db.commit()
    # A game that synced after the merge lands on the keeper (redirect), and is not in the log.
    async with async_session_maker() as db:
        await db.execute(text("INSERT INTO game_appearances (game_id,player_id,team_name) VALUES (:g,:p,'U13')"),
                         {"g": str(late), "p": str(keep)})
        await db.commit()
    log_id = await one("SELECT id FROM merge_logs WHERE org_id=:o AND removed_player_id=:r", o=org, r=rem)

    print("\n# A. The merge, before any undo")
    check("the removed player is gone", await one("SELECT COUNT(*) FROM players WHERE id=:i", i=rem), 0)
    check("the keeper holds all four games", await one("SELECT COUNT(*) FROM game_appearances WHERE player_id=:k", k=keep), 4)

    print("\n# B. Dry run")
    code = await script.run(str(org), [log_id], apply=False, by="test")
    check("a dry run changes nothing: player still gone", await one("SELECT COUNT(*) FROM players WHERE id=:i", i=rem), 0)
    check("...and the log is not undone", await one("SELECT undone_at IS NULL FROM merge_logs WHERE id=:i", i=log_id), True)
    check("...and exits clean", code, 0)
    async with async_session_maker() as db:
        d = await script.describe(db, org, log_id)
    check("it reports the two games it would move back", (d or {}).get("appearances_on_keep"), 2)

    print("\n# C. Apply")
    code = await script.run(str(org), [log_id], apply=True, by="jack")
    check("the removed player is back with its Cricket Australia id",
          await one("SELECT grassroots_id FROM players WHERE id=:i", i=rem), str(rem))
    check("it has the two games the merge moved", await one("SELECT COUNT(*) FROM game_appearances WHERE player_id=:i", i=rem), 2)
    check("the keeper keeps its own game and the post-merge game",
          sorted(r for r in [await one("SELECT COUNT(*) FROM game_appearances WHERE player_id=:k", k=keep)]), [2])
    check("the post-merge game stayed on the keeper",
          await one("SELECT player_id::text FROM game_appearances WHERE game_id=:g AND player_id=:k", g=late, k=keep), str(keep))
    check("the log is marked undone", await one("SELECT undone_at IS NOT NULL FROM merge_logs WHERE id=:i", i=log_id), True)
    check("the app's own audit entry is written",
          await one("SELECT COUNT(*) FROM audit_logs WHERE org_id=:o AND action='undo_merge_players'", o=org), 1)
    check("...and the script says who asked",
          await one("SELECT details->>'by' FROM audit_logs WHERE org_id=:o AND action='undo_merge_players_script'", o=org), "jack")
    check("exits clean", code, 0)

    print("\n# D. Run again, and the wrong club")
    await script.run(str(org), [log_id], apply=True, by="jack")
    check("a second run adds no second audit entry",
          await one("SELECT COUNT(*) FROM audit_logs WHERE org_id=:o AND action='undo_merge_players'", o=org), 1)
    code = await script.run(str(other_org), [log_id], apply=True, by="jack")
    check("another club's run cannot reach this log (non-zero exit)", code, 1)

    print("\n# E. A newer live merge blocks the undo")
    again = uuid.uuid4()
    async with async_session_maker() as db:
        await db.execute(text("INSERT INTO players (id,organisation_id,name,grassroots_id) VALUES (:i,:o,'********',:g)"), {"i": str(again), "g": str(again), "o": str(org)})
        await db.commit()
    async with async_session_maker() as db:
        await _merge_players_core(db, keep, again, org, mc.FakeUser())     # older merge, then...
        await db.commit()
    async with async_session_maker() as db:
        await _merge_players_core(db, third, keep, org, mc.FakeUser())     # ...a newer one involving the keeper
        await db.commit()
    older = await one("SELECT id FROM merge_logs WHERE org_id=:o AND removed_player_id=:r", o=org, r=again)
    code = await script.run(str(org), [older], apply=True, by="jack")
    check("the older merge is not undone while a newer one uses the same player",
          await one("SELECT undone_at IS NULL FROM merge_logs WHERE id=:i", i=older), True)
    check("...and the exit says something was skipped", code, 1)

    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
