"""Verification: ops/gisborne-brook-fix.sh, against a real Postgres and the shipped scripts.

Builds Gisborne's shape with the SHIPPED merge: five redacted junior ids merged into a new
profile, that into another player, one more merge into that player, a game synced after the
merge, then runs every stage of the shell script:

  * merge before the undo is refused (merges still live)
  * preview changes nothing; undo reverses all seven; the other player's own career stays
  * the junior ids come back as their own players, each with its own games
  * merge refuses a new profile that holds old junior games, and one that shares a game
  * merge (dry) changes nothing; merge --apply moves the new profile's games to the old one
  * verify reports the leftover post-merge game on the other player

CONTROL: with the gate in the script removed, the two refusal checks fail.

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_gisborne_brook_fix_script.py
"""
from __future__ import annotations

import asyncio
import os
import subprocess
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

PASS = FAIL = 0
SCRIPT = Path(__file__).resolve().parents[2] / "ops" / "gisborne-brook-fix.sh"
U = uuid.UUID
KEEP, NEW, OTHER = (U("ed4e36cf-28cd-4012-b00c-2baf021cba9b"), U("331ef65c-d93d-4bd2-afc5-dd720b90bd66"),
                    U("80f4940d-6e90-4f02-942f-63c4f06e81d1"))
JUN = [U(x) for x in ("23ad6501-41e6-4222-8077-221888c26b56", "ce68ebe3-38dd-4b0d-bfe5-4f3ebc39d463",
                      "d3835185-8775-43eb-99dd-2c3fae74ac57", "19a0e927-f51f-49bb-964a-b9d21ba681ac",
                      "62cac645-bc45-4c1b-8055-f0b61c879919")]
EXTRA = U("d412f328-881f-41d2-94d0-56752ff72f5e")


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


def sh(step, *args):
    env = dict(os.environ, BACKEND_CMD=f"{sys.executable} -m", CLUB="gis-fix", ORG=str(ORG),
               DB_CMD="psql " + os.environ["DATABASE_URL"].replace("+asyncpg", ""))
    r = subprocess.run(["bash", str(SCRIPT), step, *args], env=env, capture_output=True, text=True,
                       cwd=Path(__file__).resolve().parent.parent)
    return r.returncode, r.stdout + r.stderr


ORG = uuid.uuid4()


async def build():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for ddl in mc.EXTRA_DDL:
            await conn.execute(text(ddl))
    season, grade = uuid.uuid4(), uuid.uuid4()
    async with async_session_maker() as db:
        await db.execute(text("INSERT INTO organisations (id,name,slug,is_active) VALUES (:o,'Gis Fix','gis-fix',true)"), {"o": str(ORG)})
        await db.execute(text("INSERT INTO seasons (id,organisation_id,name,year) VALUES (:s,:o,'S',2026)"), {"s": str(season), "o": str(ORG)})
        await db.execute(text("INSERT INTO grades (id,season_id,name) VALUES (:g,:s,'G')"), {"g": str(grade), "s": str(season)})
        for pid in [KEEP, NEW, OTHER, EXTRA] + JUN:
            name = "Grumont, Brook" if pid == KEEP else "********"
            status = "inactive" if pid == OTHER else "active"
            await db.execute(text("INSERT INTO players (id,organisation_id,name,status,grassroots_id) VALUES (:i,:o,:n,:s,:g)"),
                             {"i": str(pid), "o": str(ORG), "n": name, "s": status, "g": str(pid)})

        async def games(pid, years):
            for y in years:
                gid = uuid.uuid4()
                await db.execute(text("INSERT INTO games (id,grade_id,played_at) VALUES (:g,:gr,CAST(:d AS date))"),
                                 {"g": str(gid), "gr": str(grade), "d": date(y[0], y[1], y[2])})
                await db.execute(text("INSERT INTO game_appearances (game_id,player_id,team_name) VALUES (:g,:p,'x')"), {"g": str(gid), "p": str(pid)})
        await games(KEEP, [(2003, 11, 1), (2019, 12, 7), (2023, 2, 4)])             # the old profile
        await games(NEW, [(2026, 1, 31), (2026, 2, 14)])                            # his own recent games
        await games(OTHER, [(2018, 11, 3), (2021, 12, 4), (2023, 1, 14)])           # another player's career
        for i, j in enumerate(JUN):
            await games(j, [(2021 + i % 3, 11, 1 + i), (2022 + i % 3, 12, 2 + i)])  # juniors
        await games(EXTRA, [])
        await db.commit()
    for keep, rem in [(NEW, JUN[0]), (NEW, JUN[1]), (NEW, JUN[2]), (NEW, JUN[3]), (NEW, JUN[4]), (OTHER, NEW), (OTHER, EXTRA)]:
        async with async_session_maker() as db:
            await _merge_players_core(db, keep, rem, ORG, mc.FakeUser())
            await db.commit()
    async with async_session_maker() as db:     # the log ids the script expects
        await db.execute(text("UPDATE merge_logs SET id = id + 100000 WHERE org_id = :o"), {"o": str(ORG)})
        for n, lid in enumerate((await db.execute(text("SELECT id FROM merge_logs WHERE org_id=:o ORDER BY id"), {"o": str(ORG)})).scalars().all()):
            await db.execute(text("UPDATE merge_logs SET id = :n WHERE id = :i"), {"n": 8102 + n, "i": lid})
        # a game that synced after the merge: credited to the other player through the redirect
        gid = uuid.uuid4()
        await db.execute(text("INSERT INTO games (id,grade_id,played_at) VALUES (:g,:gr,CAST('2026-10-17' AS date))"), {"g": str(gid), "gr": str(grade)})
        await db.execute(text("INSERT INTO game_appearances (game_id,player_id,team_name) VALUES (:g,:p,'x')"), {"g": str(gid), "p": str(OTHER)})
        await db.commit()


async def main():
    await build()
    print("\n# A. Before the undo")
    code, out = sh("merge")
    check("merge is refused while the merges are live", code != 0 and "still live" in out, True)

    print("\n# B. Preview, then undo")
    code, out = sh("preview")
    check("preview runs clean", code, 0)
    check("...and changes nothing", await one("SELECT COUNT(*) FROM merge_logs WHERE org_id=:o AND undone_at IS NULL", o=str(ORG)), 7)
    code, out = sh("undo")
    check("undo runs clean", code, 0)
    check("all seven merges are undone", await one("SELECT COUNT(*) FROM merge_logs WHERE org_id=:o AND undone_at IS NOT NULL", o=str(ORG)), 7)
    check("the five juniors are separate players again", await one("SELECT COUNT(*) FROM players WHERE id = ANY(CAST(:i AS uuid[]))", i=JUN), 5)
    check("...each with its own two games", await one("SELECT COUNT(*) FROM game_appearances WHERE player_id = ANY(CAST(:i AS uuid[]))", i=JUN), 10)
    check("the new profile is back with his two recent games", await one("SELECT COUNT(*) FROM game_appearances WHERE player_id=:i", i=str(NEW)), 2)
    check("the other player keeps their own career (3) and the post-merge game (1)",
          await one("SELECT COUNT(*) FROM game_appearances WHERE player_id=:i", i=str(OTHER)), 4)

    print("\n# C. The gate in front of the merge")
    gid = uuid.uuid4()
    async with async_session_maker() as db:
        await db.execute(text("INSERT INTO games (id,grade_id,played_at) SELECT :g, grade_id, CAST('2022-01-01' AS date) FROM games LIMIT 1"), {"g": str(gid)})
        await db.execute(text("INSERT INTO game_appearances (game_id,player_id,team_name) VALUES (:g,:p,'x')"), {"g": str(gid), "p": str(NEW)})
        await db.commit()
    code, out = sh("merge", "--apply")
    check("a new profile with old junior games is refused", code != 0 and "Not merging" in out, True)
    check("...and nothing merged", await one("SELECT COUNT(*) FROM players WHERE id=:i", i=str(NEW)), 1)
    async with async_session_maker() as db:
        await db.execute(text("DELETE FROM game_appearances WHERE game_id=:g"), {"g": str(gid)})
        await db.execute(text("INSERT INTO game_appearances (game_id,player_id,team_name) SELECT game_id, :k, 'x' FROM game_appearances WHERE player_id=:n LIMIT 1"), {"k": str(KEEP), "n": str(NEW)})
        await db.commit()
    code, out = sh("merge", "--apply")
    check("a pair that shares a game is refused", code != 0 and "same game" in out, True)
    async with async_session_maker() as db:
        await db.execute(text("DELETE FROM game_appearances WHERE player_id=:k AND game_id IN (SELECT game_id FROM game_appearances WHERE player_id=:n)"), {"k": str(KEEP), "n": str(NEW)})
        await db.commit()

    print("\n# D. The merge")
    code, out = sh("merge")
    check("the dry run is clean", code, 0)
    check("...and changes nothing", await one("SELECT COUNT(*) FROM players WHERE id=:i", i=str(NEW)), 1)
    code, out = sh("merge", "--apply")
    check("the merge runs clean", code, 0)
    check("the new profile is gone", await one("SELECT COUNT(*) FROM players WHERE id=:i", i=str(NEW)), 0)
    check("the old profile now has his old and recent games", await one("SELECT COUNT(*) FROM game_appearances WHERE player_id=:i", i=str(KEEP)), 5)
    check("...and is still named and active", await one("SELECT name || '|' || status FROM players WHERE id=:i", i=str(KEEP)), "Grumont, Brook|active")

    print("\n# E. Verify")
    code, out = sh("verify")
    check("verify runs", code, 0)
    check("it reports the game that synced after the merge", "2026-10-17" in out, True)

    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
