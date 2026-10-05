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
PLAYED = '[{"runs_scored": 120, "wickets": 5}]'


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
        PlayerSeasonStats, Season, Base, BowlingSpell, engine, async_session_maker,
    )
    from app.services.fees import recompute_fee_match_days

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        # Raw-SQL column (main.py lifespan, migration 233) that the shared
        # played rule reads.
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        # `games.raw_payload` is JSON on the ORM and JSONB in the migrated database;
        # the view's UNION cannot mix them, so reconcile as the neighbouring suites do.
        for tbl, col in (await conn.execute(text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND data_type = 'json'"))).all():
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb USING "{col}"::text::jsonb'))
        # The effective views the shared played rule reads, as the lifespan applies them.
        from app.services import superseded_ddl
        for stmt in superseded_ddl.STATEMENTS:
            await conn.execute(text(stmt))

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
                    home_team="Applecross", away_team="Opp", status="COMPLETED"))
        await db.flush()
        await db.execute(text("UPDATE games SET innings_totals = CAST(:t AS JSONB) WHERE id = :g"),
                         {"t": PLAYED, "g": game})
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

    # Cowcher's shape: a game whose appearance rows name the rest of the side, and
    # a bowler with a spell but NO appearance row. He must still be charged for it.
    g2game, bowler, mate, foreign_bowler = (uuid.uuid4() for _ in range(4))
    async with async_session_maker() as db:
        db.add_all([Player(id=bowler, organisation_id=org, name="Cowcher, Baxter"),
                    Player(id=mate, organisation_id=org, name="Mate, Max"),
                    Player(id=foreign_bowler, organisation_id=other, name="Foreign, Fred")])
        await db.flush()
        db.add(Game(id=g2game, grade_id=g_open, played_at=date.today() - timedelta(days=1),
                    home_team="CVPCC Colts", away_team="Applecross Colts", status="COMPLETED"))
        await db.flush()
        await db.execute(text("UPDATE games SET innings_totals = CAST(:t AS JSONB) WHERE id = :g"),
                         {"t": PLAYED, "g": g2game})
        db.add(GameAppearance(game_id=g2game, player_id=mate))
        db.add_all([BowlingSpell(game_id=g2game, player_id=bowler, innings_number=1, overs=3, runs=7, wickets=1),
                    BowlingSpell(game_id=g2game, player_id=foreign_bowler, innings_number=2, overs=2, runs=9, wickets=0)])
        await db.commit()
    await recompute_fee_match_days(str(org), str(sid))
    got4 = await enrolled()
    check("bowler with a spell and no appearance is charged the game", got4.get(bowler), 1)
    check("teammate with an appearance is charged the game", got4.get(mate), 1)
    check("another club's bowler in the same game stays out", foreign_bowler in got4, False)
    await recompute_fee_match_days(str(org), str(sid))
    check("second run does not double-charge the bowler", (await enrolled()).get(bowler), 1)

    # Named is playing, unless the game was called off. A washed-out game and a
    # completed game with an empty scorecard charge nobody; a game called off
    # AFTER play started still charges the player who has a line in it.
    washed, empty, dnp, called_off_played = (uuid.uuid4() for _ in range(4))
    pa, pb = uuid.uuid4(), uuid.uuid4()
    async with async_session_maker() as db:
        db.add_all([Player(id=pa, organisation_id=org, name="Washout, Wes"),
                    Player(id=pb, organisation_id=org, name="Bowled, Ben")])
        await db.flush()
        db.add_all([
            Game(id=washed, grade_id=g_open, played_at=date.today() - timedelta(days=9),
                 home_team="A", away_team="B", status="ABANDONED"),
            Game(id=empty, grade_id=g_open, played_at=date.today() - timedelta(days=8),
                 home_team="C", away_team="D", status="COMPLETED"),
            Game(id=called_off_played, grade_id=g_open, played_at=date.today() - timedelta(days=7),
                 home_team="E", away_team="F", status="ABANDONED"),
        ])
        await db.flush()
        db.add_all([GameAppearance(game_id=washed, player_id=pa),
                    GameAppearance(game_id=empty, player_id=pa),
                    GameAppearance(game_id=called_off_played, player_id=pa),
                    GameAppearance(game_id=called_off_played, player_id=pb),
                    BowlingSpell(game_id=called_off_played, player_id=pb, innings_number=1, overs=2, runs=5, wickets=0)])
        await db.commit()
    await recompute_fee_match_days(str(org), str(sid))
    async with async_session_maker() as db:
        rows = {r[0]: r[1] for r in (await db.execute(text("""
            SELECT md.game_id, count(*) FROM fee_match_days md
            JOIN fee_member_seasons ms ON ms.id = md.member_season_id
            JOIN fee_members fm ON fm.id = ms.member_id
            WHERE fm.player_id = :p GROUP BY md.game_id"""), {"p": pa})).all()}
        rows_b = {r[0]: r[1] for r in (await db.execute(text("""
            SELECT md.game_id, count(*) FROM fee_match_days md
            JOIN fee_member_seasons ms ON ms.id = md.member_season_id
            JOIN fee_members fm ON fm.id = ms.member_id
            WHERE fm.player_id = :p GROUP BY md.game_id"""), {"p": pb})).all()}
    check("named in an abandoned game with no play: not charged", washed in rows, False)
    check("named in a completed game with an empty scorecard: not charged", empty in rows, False)
    check("named but with no line in a game called off after play: not charged", called_off_played in rows, False)
    check("a line in a game called off after play: still charged", rows_b.get(called_off_played), 1)

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
