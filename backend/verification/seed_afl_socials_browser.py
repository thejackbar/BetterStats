"""Seed a football database for the BetterSocials browser suite.

Login coach / pass1234, club slug ``cuw``, BetterSocials switched on, a Seniors
side with a win over Rivals (12.8 (80) to 6.4 (40)), best-on-ground rankings
where the top-voted player is not the top goal kicker, the opposition's own
ranked player on the same game, and the side named for it.

The same fixture the backend suite (verify_afl_social.py) builds, lifted out
so the browser suite can be re-run from scratch.

Run:  DATABASE_URL=postgresql+asyncpg://postgres@/afl_browser?host=/tmp/pgsock&port=5544 \
      python verification/seed_afl_socials_browser.py
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


async def main():
    from app.models.db import (ClubMembership, Game, Grade, Organisation, Player, Season, User,
                               engine, async_session_maker)
    from app.models.afl import AflGameDetails, AflPlayerGameLine
    from app.afl_main import lifespan
    from app.routers.auth import _hash_password as hash_password

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    async with lifespan(None):
        pass

    org, u = uuid.uuid4(), uuid.uuid4()
    season, grade = uuid.uuid4(), uuid.uuid4()
    p_star, p_two = uuid.uuid4(), uuid.uuid4()
    g_win, g_loss, g_next = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    today = date.today()
    now = datetime.now()

    async with async_session_maker() as db:
        db.add_all([
            Organisation(id=org, name="Curtin Uni Wesley", slug="cuw", is_active=True,
                         module_overrides=["socials"], subscription_status="active"),
            User(id=u, username="coach", email="coach@x.io", password_hash=hash_password("pass1234")),
            Season(id=season, organisation_id=org, name="VAFA 2026", year=today.year),
            Player(id=p_star, organisation_id=org, name="Star, Sam"),
            Player(id=p_two, organisation_id=org, name="Two, Terry"),
        ])
        await db.flush()
        db.add_all([
            ClubMembership(user_id=u, club_id=org, role="club_admin", is_primary_admin=True),
            Grade(id=grade, season_id=season, name="Seniors"),
        ])
        await db.flush()
        db.add_all([
            Game(id=g_win, grade_id=grade, played_at=today - timedelta(days=3),
                 home_team="Curtin Uni Wesley", away_team="Rivals Football Club"),
            Game(id=g_loss, grade_id=grade, played_at=today - timedelta(days=10),
                 home_team="Hosts FC", away_team="Curtin Uni Wesley"),
            Game(id=g_next, grade_id=grade, played_at=today + timedelta(days=4),
                 home_team="Curtin Uni Wesley", away_team="Next Opponents"),
        ])
        await db.flush()
        db.add_all([
            AflGameDetails(game_id=g_win, status="FINAL", our_side="HOME", round_name="Round 5",
                           home_goals=12, home_behinds=8, home_score=80,
                           away_goals=6, away_behinds=4, away_score=40,
                           publish_lineup=True, synced_at=now),
            AflGameDetails(game_id=g_loss, status="FINAL", our_side="AWAY", round_name="Round 4",
                           home_goals=10, home_behinds=10, home_score=70,
                           away_goals=10, away_behinds=9, away_score=69, synced_at=now),
            AflGameDetails(game_id=g_next, status="UPCOMING", our_side="HOME", round_name="6",
                           start_time="14:10:00", venue_name="Wesley Oval"),
        ])
        await db.flush()
        db.add_all([
            AflPlayerGameLine(id=uuid.uuid4(), game_id=g_win, side="HOME", playhq_participant_id="a",
                              player_id=p_two, name="Two, Terry", jumper_number="10",
                              goals=4, behinds=1, bog_ranking=2),
            AflPlayerGameLine(id=uuid.uuid4(), game_id=g_win, side="HOME", playhq_participant_id="b",
                              player_id=p_star, name="Star, Sam", jumper_number="2",
                              goals=1, behinds=0, bog_ranking=1, is_captain=True),
            # The opposition kicked more and ranked first on THEIR list: never ours.
            AflPlayerGameLine(id=uuid.uuid4(), game_id=g_win, side="AWAY", playhq_participant_id="c",
                              player_id=None, name="Opp, Oscar", goals=9, behinds=0, bog_ranking=1),
        ])
        await db.commit()
    await engine.dispose()
    print("seeded")


if __name__ == "__main__":
    asyncio.run(main())
