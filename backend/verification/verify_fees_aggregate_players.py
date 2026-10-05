"""BetterFees enrols a player who only exists in Cricket Australia's season totals.

A player first seen through the season aggregates has a ``players`` row and a
``player_season_stats`` row but no ``game_appearances`` row until a scorecard
syncs, and a match CA counts can stay without one for good. The recompute used
to enrol from appearances only, so that player never reached Fees and
"Rebuild" could not add them. This checks they are enrolled with no match days,
that an Exclude grade, a zero-match row and another club's player stay out, and
that a scored player is still charged exactly once.

Run:  DATABASE_URL=postgresql+asyncpg://postgres@/fees_verify?host=/tmp/pgsock&port=5544 \
      python verification/verify_fees_aggregate_players.py
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
        Game, GameAppearance, Grade, Organisation, Player, PlayerSeasonGradeStats,
        PlayerSeasonStats, Season, Base, engine, async_session_maker,
    )
    from app.services.fees import recompute_fee_match_days

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)

    org, other = uuid.uuid4(), uuid.uuid4()
    sid, g_open, g_excl = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    scored, agg_only, agg_noGrade, agg_excl, agg_zero, stranger = (uuid.uuid4() for _ in range(6))
    game = uuid.uuid4()
    async with async_session_maker() as db:
        db.add_all([
            Organisation(id=org, name="Applecross", slug="apple-x", is_active=True),
            Organisation(id=other, name="Payneham", slug="payneham-x", is_active=True),
            Season(id=sid, organisation_id=org, name="2026/27", year=2026),
        ])
        await db.flush()
        db.add_all([
            Grade(id=g_open, season_id=sid, name="1st XI"),
            Grade(id=g_excl, season_id=sid, name="Juniors", fee_format="exclude"),
            Player(id=scored, organisation_id=org, name="Scored, Sam"),
            Player(id=agg_only, organisation_id=org, name="Cowcher, Baxter"),
            Player(id=agg_noGrade, organisation_id=org, name="Season, Only"),
            Player(id=agg_excl, organisation_id=org, name="Junior, Jo"),
            Player(id=agg_zero, organisation_id=org, name="Zero, Zac"),
            Player(id=stranger, organisation_id=other, name="Stranger, Sam"),
        ])
        await db.flush()
        db.add(Game(id=game, grade_id=g_open, played_at=date.today() - timedelta(days=3),
                    home_team="Applecross", away_team="Opp"))
        await db.flush()
        db.add(GameAppearance(game_id=game, player_id=scored))
        db.add_all([
            PlayerSeasonGradeStats(player_id=agg_only, season_id=sid, grade_id=g_open, matches=1),
            PlayerSeasonGradeStats(player_id=agg_excl, season_id=sid, grade_id=g_excl, matches=5),
            PlayerSeasonGradeStats(player_id=agg_zero, season_id=sid, grade_id=g_open, matches=0),
            PlayerSeasonGradeStats(player_id=stranger, season_id=sid, grade_id=g_open, matches=4),
            PlayerSeasonStats(player_id=agg_only, season_id=sid, matches=1),
            PlayerSeasonStats(player_id=agg_noGrade, season_id=sid, matches=3),
            PlayerSeasonStats(player_id=agg_excl, season_id=sid, matches=5),
            PlayerSeasonStats(player_id=agg_zero, season_id=sid, matches=0),
            PlayerSeasonStats(player_id=stranger, season_id=sid, matches=4),
        ])
        await db.commit()

    async def enrolled():
        async with async_session_maker() as db:
            rows = (await db.execute(text("""
                SELECT fm.player_id, count(md.id) AS days
                FROM fee_member_seasons ms
                JOIN fee_members fm ON fm.id = ms.member_id
                LEFT JOIN fee_match_days md ON md.member_season_id = ms.id
                WHERE ms.season_id = :s GROUP BY fm.player_id
            """), {"s": sid})).all()
        return {r[0]: r[1] for r in rows}

    r = await recompute_fee_match_days(str(org), str(sid))
    got = await enrolled()
    print(r)
    check("scored player enrolled with their one game", got.get(scored), 1)
    check("aggregate-only player (the reported case) is enrolled", agg_only in got)
    check("aggregate-only player has no match days", got.get(agg_only), 0)
    check("player with a season total and no grade rows is enrolled", agg_noGrade in got)
    check("player only in an Exclude grade stays out", agg_excl in got, False)
    check("player with zero matches stays out", agg_zero in got, False)
    check("another club's player stays out", stranger in got, False)

    await recompute_fee_match_days(str(org), str(sid))
    got2 = await enrolled()
    check("second run changes nothing", got2, got)
    check("still one match day for the scored player", got2.get(scored), 1)

    # Once their scorecard arrives the aggregate-only player is charged for it.
    async with async_session_maker() as db:
        db.add(GameAppearance(game_id=game, player_id=agg_only))
        await db.commit()
    await recompute_fee_match_days(str(org), str(sid))
    got3 = await enrolled()
    check("scorecard later charges the same member, no duplicate", got3.get(agg_only), 1)
    async with async_session_maker() as db:
        n = (await db.execute(text(
            "SELECT count(*) FROM fee_members WHERE organisation_id=:o AND player_id=:p"),
            {"o": org, "p": agg_only})).scalar()
    check("one fee member row for that player", n, 1)

    # A season with no scored game at all (a new season before any scorecard).
    sid2, g2, fresh = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with async_session_maker() as db:
        db.add(Season(id=sid2, organisation_id=org, name="2027/28", year=2027))
        await db.flush()
        db.add_all([Grade(id=g2, season_id=sid2, name="1st XI"),
                    Player(id=fresh, organisation_id=org, name="Fresh, Finn")])
        await db.flush()
        db.add(PlayerSeasonStats(player_id=fresh, season_id=sid2, matches=2))
        await db.commit()
    r2 = await recompute_fee_match_days(str(org), str(sid2))
    async with async_session_maker() as db:
        n = (await db.execute(text(
            "SELECT count(*) FROM fee_member_seasons WHERE season_id=:s"), {"s": sid2})).scalar()
    check("season with no scored games still enrols the season-total player", n, 1)

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
