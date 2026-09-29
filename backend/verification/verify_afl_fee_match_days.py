"""BetterFees match days on football, against a real Postgres.

Nothing on football writes ``game_appearances``; the record of who played is
``afl_player_game_lines``, for both sides of a game. So a football club
collecting match fees was charged for no games at all. This checks the
recompute reads our side's lines, never the opposition's, never another
club's player, and never charges one game twice.

Run:  DATABASE_URL=postgresql+asyncpg://postgres@/afl_verify?host=/tmp/pgsock&port=5544 \
      python verification/verify_afl_fee_match_days.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")
os.environ.setdefault("SPORT", "afl")

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
    from app.models.db import Game, GameAppearance, Grade, Organisation, Player, Season, engine, async_session_maker
    from app.models.afl import AflGameDetails, AflPlayerGameLine
    from app.afl_main import lifespan
    from app.services.fees import recompute_fee_match_days

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    async with lifespan(None):
        pass

    org, other = uuid.uuid4(), uuid.uuid4()
    s1, g1 = uuid.uuid4(), uuid.uuid4()
    ours, ours2, theirs, stranger = (uuid.uuid4() for _ in range(4))
    ga, gb = uuid.uuid4(), uuid.uuid4()
    today = date.today()
    async with async_session_maker() as db:
        db.add_all([
            Organisation(id=org, name="Curtin Uni Wesley", slug="cuw", is_active=True),
            Organisation(id=other, name="Hampton", slug="hh", is_active=True),
            Season(id=s1, organisation_id=org, name="VAFA 2026", year=2026),
        ])
        await db.flush()
        db.add_all([
            Grade(id=g1, season_id=s1, name="Seniors"),
            Player(id=ours, organisation_id=org, name="Ours, Olly"),
            Player(id=ours2, organisation_id=org, name="Ours, Two"),
            # A player row of OUR club that the away side's line happens to point
            # at: it must still not be charged, because that side is not ours.
            Player(id=theirs, organisation_id=org, name="Opp, Linked"),
            Player(id=stranger, organisation_id=other, name="Stranger, Sam"),
        ])
        await db.flush()
        db.add_all([
            Game(id=ga, grade_id=g1, played_at=today - timedelta(days=7), home_team="CUW", away_team="Opp"),
            Game(id=gb, grade_id=g1, played_at=today - timedelta(days=1), home_team="Opp", away_team="CUW"),
        ])
        await db.flush()
        db.add_all([
            AflGameDetails(game_id=ga, status="FINAL", our_side="HOME", synced_at=datetime.now()),
            AflGameDetails(game_id=gb, status="FINAL", our_side="AWAY", synced_at=datetime.now()),
        ])

        def line(game, side, pid, name):
            return AflPlayerGameLine(id=uuid.uuid4(), game_id=game, side=side,
                                     playhq_participant_id=str(uuid.uuid4()), player_id=pid, name=name)
        db.add_all([
            line(ga, "HOME", ours, "Olly"), line(ga, "HOME", ours2, "Two"),
            line(ga, "AWAY", theirs, "Linked"), line(ga, "AWAY", None, "Nobody"),
            line(gb, "AWAY", ours, "Olly"), line(gb, "AWAY", stranger, "Sam"),
            line(gb, "HOME", theirs, "Linked"),
        ])
        # A game_appearances row for a game the lines also cover must not
        # charge it twice.
        db.add(GameAppearance(game_id=ga, player_id=ours))
        await db.commit()

    res = await recompute_fee_match_days(str(org), str(s1))
    print("\n── One recompute ──")
    check("members are created for our two players", res.get("members_created"), 2)

    async def charged():
        async with async_session_maker() as db:
            rows = (await db.execute(text("""
                SELECT fm.player_id, md.game_id
                  FROM fee_match_days md
                  JOIN fee_member_seasons ms ON ms.id = md.member_season_id
                  JOIN fee_members fm ON fm.id = ms.member_id
            """))).fetchall()
        return sorted((str(p), str(g)) for p, g in rows)

    got = await charged()
    want = sorted([(str(ours), str(ga)), (str(ours2), str(ga)), (str(ours), str(gb))])
    check("a match day for each game our players played, home and away", got, want)
    check("the opposition side is never charged, even a player row of ours on it",
          any(p == str(theirs) for p, _ in got), False)
    check("another club's player is never charged or enrolled",
          any(p == str(stranger) for p, _ in got), False)
    async with async_session_maker() as db:
        enrolled = (await db.execute(text(
            "SELECT COUNT(*) FROM fee_members WHERE organisation_id = :o"), {"o": str(org)})).scalar()
    check("only our two players become members", enrolled, 2)

    res2 = await recompute_fee_match_days(str(org), str(s1))
    check("a second recompute creates nobody", res2.get("members_created"), 0)
    check("  ... and the match days are unchanged", await charged(), want)

    print("\n── The sync runs it ──")
    src = (Path(__file__).resolve().parent.parent / "app/services/afl/sync.py").read_text()
    check("the football sync recomputes match days after its rollup",
          src.index("recompute_fee_match_days") > src.index("_rollup_season_stats(session, org_pk)"))

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        sys.exit(1)


asyncio.run(main())
