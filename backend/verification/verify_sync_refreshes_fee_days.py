"""Every sync ends with the club's fee match days rebuilt, against a real Postgres.

Fee match days used to be rebuilt only after the SCHEDULED sync. A game pulled
in by Sync Now, Full Rebuild or a hard refresh left the player on the fee list
with no match day until someone pressed Rebuild match days. The Cricket
Australia pull is stubbed (it needs the live proxy); everything from
`sync_organisation` onward is the shipped code.

Run:  DATABASE_URL=postgresql+asyncpg://postgres@/fees_verify?host=/tmp/pgsock&port=5544 \
      python verification/verify_sync_refreshes_fee_days.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text  # noqa: E402

PASS = FAIL = 0


def check(label, got, want=True):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}: got {got!r}, want {want!r}")


async def main():
    from app.models.db import (
        Game, GameAppearance, Grade, Organisation, Player, Season, Base, engine, async_session_maker,
    )
    from app.services import sync as sync_mod

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)

    org, sid, gid, pid, game = (uuid.uuid4() for _ in range(5))
    async with async_session_maker() as db:
        db.add_all([Organisation(id=org, name="Applecross", slug="apple-s", is_active=True),
                    Season(id=sid, organisation_id=org, name="Summer 2026/27", year=2026)])
        await db.flush()
        db.add_all([Grade(id=gid, season_id=sid, name="Colts T20"),
                    Player(id=pid, organisation_id=org, name="Cowcher, Baxter")])
        await db.commit()

    calls = []

    async def fake_impl(org_id_str, run_id=None, kind="org_full", since=None):
        calls.append(kind)
        async with async_session_maker() as db:
            if not await db.get(Game, game):
                db.add(Game(id=game, grade_id=gid, played_at=date.today() - timedelta(days=2),
                            home_team="CVPCC Colts", away_team="Applecross Colts"))
                await db.flush()
                db.add(GameAppearance(game_id=game, player_id=pid))
            await db.commit()
        return {"gr_games_new": 1}

    sync_mod._sync_organisation_impl = fake_impl

    async def days():
        async with async_session_maker() as db:
            return (await db.execute(text(
                "SELECT count(*) FROM fee_match_days md JOIN fee_member_seasons ms "
                "ON ms.id = md.member_season_id WHERE ms.season_id = :s"), {"s": sid})).scalar()

    check("no match days before any sync", await days(), 0)
    res = await sync_mod.sync_organisation(str(org), kind="org_full")
    check("sync result is passed through", res, {"gr_games_new": 1})
    check("a manual-style sync leaves the match day behind", await days(), 1)

    # A fee failure never fails the sync.
    import app.services.fees as fees_mod
    real = fees_mod.recompute_fee_match_days

    async def boom(*a, **k):
        raise RuntimeError("fee error")
    fees_mod.recompute_fee_match_days = boom
    try:
        res = await sync_mod.sync_organisation(str(org), kind="org_hard_refresh")
        check("a fee error does not fail the sync", res, {"gr_games_new": 1})
    except Exception as e:
        check("a fee error does not fail the sync", repr(e), "no exception")
    fees_mod.recompute_fee_match_days = real

    # The deep per-player run adds no games, so it does not trigger a rebuild.
    async def counting(*a, **k):
        calls.append("recompute")
        return await real(*a, **k)
    fees_mod.recompute_fee_match_days = counting
    calls.clear()
    await sync_mod.sync_organisation(str(org), kind="player_deep")
    check("player_deep does not rebuild fee days", "recompute" in calls, False)
    await sync_mod.sync_organisation(str(org), kind="org_full")
    check("org_full does rebuild fee days", "recompute" in calls)

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
