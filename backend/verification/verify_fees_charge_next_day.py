"""A match is charged from the day after its match day, not on it.

Clubs changed the date of a game after players had been billed for it. The fee
recompute now leaves a game out until its match day is behind us, so a late
change of date cannot leave a player charged for the wrong day. Checks, against
a real Postgres through ``recompute_fee_match_days``:

  * a game played today and one dated tomorrow carry no match day,
  * a game played yesterday is charged,
  * an unpaid auto row made for a game that is then moved to tomorrow is withdrawn,
  * a PAID row for a game that is moved is left alone,
  * a game with no date is still charged (nothing to compare).

A game moved onto "today" is the reported case: it was charged the moment the
sync saw it. The control run (``--control``) neuters ``fee_settled_before`` to
the day after tomorrow so the old behaviour is reproduced, and the checks that
describe the fix must fail while the unchanged-behaviour checks still pass.

Run:  DATABASE_URL=postgresql+asyncpg://postgres@/fees_verify?host=/tmp/pgsock&port=5544 \
      python verification/verify_fees_charge_next_day.py [--control]
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
CONTROL = "--control" in sys.argv


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
        Game, GameAppearance, Grade, Organisation, Player, Season, Base,
        engine, async_session_maker,
    )
    from app.services import fees
    from app.services.fees import recompute_fee_match_days

    if CONTROL:
        # The previous behaviour: every dated game is charged straight away.
        fees.fee_settled_before = lambda now=None: date.today() + timedelta(days=2)

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        for tbl, col in (await conn.execute(text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND data_type = 'json'"))).all():
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb USING "{col}"::text::jsonb'))
        from app.services import superseded_ddl
        for stmt in superseded_ddl.STATEMENTS:
            await conn.execute(text(stmt))

    # Perth's date is what the rule uses; derive the days from it so the check
    # does not wobble across midnight UTC.
    today = fees.datetime.now(fees.FEE_TZ).date()
    org, sid, gid, pid = (uuid.uuid4() for _ in range(4))
    g_today, g_tomorrow, g_yesterday, g_undated, g_moved, g_paid = (uuid.uuid4() for _ in range(6))
    async with async_session_maker() as db:
        db.add_all([
            Organisation(id=org, name="Applecross", slug="apple-nd", is_active=True),
            Season(id=sid, organisation_id=org, name="2026/27", year=2026),
        ])
        await db.flush()
        db.add_all([
            Grade(id=gid, season_id=sid, name="1st XI"),
            Player(id=pid, organisation_id=org, name="Sam, Scored"),
        ])
        await db.flush()
        for g, when in ((g_today, today), (g_tomorrow, today + timedelta(days=1)),
                        (g_yesterday, today - timedelta(days=1)), (g_undated, None),
                        (g_moved, today - timedelta(days=2)), (g_paid, today - timedelta(days=3))):
            db.add(Game(id=g, grade_id=gid, played_at=when, home_team="Applecross",
                        away_team="Opp", status="COMPLETED"))
        await db.flush()
        await db.execute(text("UPDATE games SET innings_totals = CAST(:t AS JSONB)"), {"t": PLAYED})
        for g in (g_today, g_tomorrow, g_yesterday, g_undated, g_moved, g_paid):
            db.add(GameAppearance(game_id=g, player_id=pid))
        await db.commit()

    async def charged():
        async with async_session_maker() as db:
            rows = (await db.execute(text("""
                SELECT md.game_id FROM fee_match_days md
                  JOIN fee_member_seasons ms ON ms.id = md.member_season_id
                 WHERE ms.season_id = :s
            """), {"s": sid})).all()
        return {r[0] for r in rows}

    await recompute_fee_match_days(str(org), str(sid))
    got = await charged()
    check("game played yesterday is charged", g_yesterday in got)
    check("game with no date is still charged", g_undated in got)
    check("game played today is not charged yet", g_today in got, False)
    check("game dated tomorrow is not charged yet", g_tomorrow in got, False)

    # A late change: the already-charged unpaid game moves to tomorrow, and the
    # paid game moves too. The unpaid row goes, the paid row stays.
    check("moved game starts out charged", g_moved in got)
    check("to-be-paid game starts out charged", g_paid in got)
    paid_id = uuid.uuid4()
    async with async_session_maker() as db:
        await db.execute(text("""
            INSERT INTO fee_payments (id, organisation_id, member_season_id, amount, paid_at, kind)
            SELECT :pid, ms.organisation_id, ms.id, 20, CURRENT_DATE, 'match_day'
              FROM fee_member_seasons ms WHERE ms.season_id = :s LIMIT 1
        """), {"pid": paid_id, "s": sid})
        await db.execute(text("UPDATE fee_match_days SET paid_payment_id = :pid WHERE game_id = :g"),
                         {"pid": paid_id, "g": g_paid})
        for g in (g_moved, g_paid):
            await db.execute(text("UPDATE games SET played_at = :d WHERE id = :g"),
                             {"d": today + timedelta(days=1), "g": g})
        await db.commit()
    await recompute_fee_match_days(str(org), str(sid))
    got2 = await charged()
    check("unpaid charge is withdrawn when its game moves to tomorrow", g_moved in got2, False)
    check("a paid charge is left alone when its game moves", g_paid in got2)
    check("games that did not move keep their charge", {g_yesterday, g_undated} <= got2)

    # The backfill's dry run reports what it would withdraw and changes nothing.
    async with async_session_maker() as db:
        await db.execute(text("UPDATE games SET played_at = :d WHERE id = :g"),
                         {"d": today + timedelta(days=1), "g": g_yesterday})
        await db.commit()
    before = await charged()
    dry = await recompute_fee_match_days(str(org), str(sid), dry_run=True)
    check("dry run reports the unpaid row it would remove", dry["entries_deleted"], 1)
    check("dry run names that row's game", [r["game_id"] for r in dry["removed"]], [str(g_yesterday)])
    check("dry run changes nothing", await charged(), before)
    real = await recompute_fee_match_days(str(org), str(sid))
    check("the real run removes the same row", real["entries_deleted"], 1)
    check("the removed row is gone after the real run", g_yesterday in await charged(), False)
    async with async_session_maker() as db:
        await db.execute(text("UPDATE games SET played_at = :d WHERE id = :g"),
                         {"d": today - timedelta(days=1), "g": g_yesterday})
        await db.commit()
    await recompute_fee_match_days(str(org), str(sid))

    # And it comes back once the new match day is behind us.
    async with async_session_maker() as db:
        await db.execute(text("UPDATE games SET played_at = :d WHERE id = :g"),
                         {"d": today - timedelta(days=1), "g": g_moved})
        await db.commit()
    await recompute_fee_match_days(str(org), str(sid))
    check("moved game is charged again once its day has passed", g_moved in await charged())

    print(f"\n{PASS} passed, {FAIL} failed" + (" (control run)" if CONTROL else ""))
    sys.exit(0 if (FAIL == 0 or CONTROL) else 1)


if __name__ == "__main__":
    asyncio.run(main())
