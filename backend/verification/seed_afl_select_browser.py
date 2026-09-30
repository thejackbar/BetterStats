"""Seed a football database for the BetterSelect browser suite.

Login coach / pass1234, club slug ``cuw``, BetterSelect switched on, two sides
seeded from PlayHQ's teams, a senior game and a reserves game this Saturday,
a grand final later, and a squad of 26 seniors with positions.

Run:  DATABASE_URL=postgresql+asyncpg://postgres@/afl_browser?host=/tmp/pgsock&port=5544 \
      python verification/seed_afl_select_browser.py
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

POS = ["FB", "FB", "FB", "HB", "HB", "HB", "W", "C", "W", "HF", "HF", "HF", "FF", "FF", "FF",
       "RUCK", "MID", "MID", "UTIL", "MID", "HB", "FF", "RUCK", "W", "C", "HF"]


async def main():
    from app.models.db import (ClubMembership, Game, Grade, Organisation, Player, Season, User,
                               engine, async_session_maker)
    from app.models.afl import AflGameDetails, AflPlayerGameLine, AflTeam
    from app.afl_main import lifespan
    from app.routers.auth import _hash_password as hash_password
    from app.services.afl import select as svc

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    async with lifespan(None):
        pass

    today = date.today()
    sat = today + timedelta(days=(5 - today.weekday()) % 7 or 7)
    org, u = uuid.uuid4(), uuid.uuid4()
    season, g_sen, g_res = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with async_session_maker() as db:
        db.add_all([
            Organisation(id=org, name="Curtin Uni Wesley", slug="cuw", is_active=True,
                         module_overrides=["select"], subscription_status="active", playhq_id="d14445c4"),
            User(id=u, username="coach", email="coach@x.io", password_hash=hash_password("pass1234")),
            Season(id=season, organisation_id=org, name="VAFA 2026", year=today.year),
        ])
        await db.flush()
        db.add_all([
            ClubMembership(user_id=u, club_id=org, role="club_admin", is_primary_admin=True),
            Grade(id=g_sen, season_id=season, name="Premier C Seniors"),
            Grade(id=g_res, season_id=season, name="Premier C Reserves"),
        ])
        await db.flush()
        players = []
        for i, pos in enumerate(POS):
            pid = uuid.uuid4()
            players.append(pid)
            db.add(Player(id=pid, organisation_id=org, name=f"Senior, Player{i + 1:02d}",
                          skill_positions=[pos], shirt_number=str(i + 1),
                          phone=f"0400 000 {i:03d}"))
        db.add_all([
            AflTeam(id=uuid.uuid4(), organisation_id=org, season_id=season, grade_id=g_res,
                    playhq_id="t-res", name="Curtin Uni Wesley Reserves"),
            AflTeam(id=uuid.uuid4(), organisation_id=org, season_id=season, grade_id=g_sen,
                    playhq_id="t-sen", name="Curtin Uni Wesley Seniors"),
        ])
        await db.flush()
        details = []

        def game(gid, grade, day, final=False, status="FINAL", rnd="Round 1"):
            db.add(Game(id=gid, grade_id=grade, played_at=day, is_final=final,
                        home_team="Curtin Uni Wesley Seniors" if grade == g_sen else "Curtin Uni Wesley Reserves",
                        away_team="Old Trinity", opp_club_name="Old Trinity", venue="Wesley Oval"))
            details.append(AflGameDetails(game_id=gid, playhq_id=f"phq-{gid}", status=status, our_side="HOME",
                                          round_name=rnd, start_time="14:10:00",
                                          synced_at=datetime.now() if status == "FINAL" else None))

        past = [uuid.uuid4() for _ in range(3)]
        for i, gid in enumerate(past):
            game(gid, g_sen, today - timedelta(days=21 - 7 * i), rnd=f"Round {i + 6}")
        game(uuid.uuid4(), g_sen, sat, status="UPCOMING", rnd="Round 9")
        game(uuid.uuid4(), g_res, sat, status="UPCOMING", rnd="Round 9")
        game(uuid.uuid4(), g_sen, sat + timedelta(days=35), final=True, status="UPCOMING", rnd="Grand Final")
        await db.flush()
        db.add_all(details)
        await db.flush()
        for gid in past:
            for n, pid in enumerate(players[:22]):
                db.add(AflPlayerGameLine(id=uuid.uuid4(), game_id=gid, side="HOME", player_id=pid,
                                         name="x", playhq_participant_id=str(uuid.uuid4()),
                                         goals=2 if POS[n] == "FF" else 0, bog_ranking=1 if n == 16 else None))
        await db.commit()
        await svc.seed_teams(db, org)
        await svc.sync_fixtures(db, org)
        await svc.auto_assign(db, org)
        await db.commit()
    print("seeded", sat)


asyncio.run(main())
