"""BetterSocials' data imports on the football backend (routers/afl/social.py),
against a real Postgres, through the real AFL boot path and HTTP stack.

Run:  DATABASE_URL=postgresql+asyncpg://postgres@/afl_verify?host=/tmp/pgsock&port=5544 \
      python verification/verify_afl_social.py
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
    import httpx
    from app.models.db import ClubMembership, Game, Grade, Organisation, Player, Season, User, engine, async_session_maker
    from app.models.afl import AflGameDetails, AflPlayerGameLine
    from app.afl_main import app, lifespan
    from app.routers.auth import COOKIE_NAME, create_session_token

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    async with lifespan(None):
        pass

    org, other = uuid.uuid4(), uuid.uuid4()
    u, u_other = uuid.uuid4(), uuid.uuid4()
    season, grade, oseason, ograde = (uuid.uuid4() for _ in range(4))
    p_star, p_two = uuid.uuid4(), uuid.uuid4()
    g_win, g_loss, g_next, g_old, g_theirs = (uuid.uuid4() for _ in range(5))
    today = date.today()
    now = datetime.now()

    async with async_session_maker() as db:
        db.add_all([
            Organisation(id=org, name="Curtin Uni Wesley", slug="cuw", is_active=True, module_overrides=["socials"]),
            Organisation(id=other, name="Hampton Hammers", slug="hh", is_active=True, module_overrides=[]),
            User(id=u, username="c", email="c@x.io", password_hash="x", display_name="C"),
            User(id=u_other, username="h", email="h@x.io", password_hash="x", display_name="H"),
            Season(id=season, organisation_id=org, name="2026", year=2026),
            Season(id=oseason, organisation_id=other, name="2026", year=2026),
            Player(id=p_star, organisation_id=org, name="Star, Sam"),
            Player(id=p_two, organisation_id=org, name="Two, Terry"),
        ])
        await db.flush()
        db.add_all([
            ClubMembership(user_id=u, club_id=org, role="club_admin", is_primary_admin=True),
            ClubMembership(user_id=u_other, club_id=other, role="club_admin", is_primary_admin=True),
            Grade(id=grade, season_id=season, name="Seniors"),
            Grade(id=ograde, season_id=oseason, name="Seniors"),
        ])
        await db.flush()
        db.add_all([
            Game(id=g_win, grade_id=grade, played_at=today - timedelta(days=3), home_team="Curtin Uni Wesley", away_team="Rivals Football Club"),
            Game(id=g_loss, grade_id=grade, played_at=today - timedelta(days=10), home_team="Hosts FC", away_team="Curtin Uni Wesley"),
            Game(id=g_next, grade_id=grade, played_at=today + timedelta(days=4), home_team="Curtin Uni Wesley", away_team="Next Opponents"),
            Game(id=g_old, grade_id=grade, played_at=today - timedelta(days=400), home_team="Curtin Uni Wesley", away_team="Ancient"),
            Game(id=g_theirs, grade_id=ograde, played_at=today - timedelta(days=3), home_team="Hampton", away_team="X"),
        ])
        await db.flush()
        db.add_all([
            AflGameDetails(game_id=g_win, status="FINAL", our_side="HOME", round_name="Round 5",
                           home_goals=12, home_behinds=8, home_score=80, away_goals=6, away_behinds=4, away_score=40, synced_at=now),
            AflGameDetails(game_id=g_loss, status="FINAL", our_side="AWAY", round_name="Round 4",
                           home_goals=10, home_behinds=10, home_score=70, away_goals=10, away_behinds=9, away_score=69, synced_at=now),
            AflGameDetails(game_id=g_next, status="UPCOMING", our_side="HOME", round_name="6", start_time="14:10:00", venue_name="Lwest Oval"),
            AflGameDetails(game_id=g_old, status="FINAL", our_side="HOME", home_score=50, away_score=30),
            AflGameDetails(game_id=g_theirs, status="FINAL", our_side="HOME", home_score=1, away_score=2, synced_at=now),
        ])
        await db.flush()
        db.add_all([
            AflPlayerGameLine(id=uuid.uuid4(), game_id=g_win, side="HOME", playhq_participant_id="a", player_id=p_two,
                              name="Two, Terry", jumper_number="10", goals=4, behinds=1, bog_ranking=2),
            AflPlayerGameLine(id=uuid.uuid4(), game_id=g_win, side="HOME", playhq_participant_id="b", player_id=p_star,
                              name="Star, Sam", jumper_number="2", goals=1, behinds=0, bog_ranking=1, is_captain=True),
            # The opposition kicked more and ranked first on THEIR list: never ours.
            AflPlayerGameLine(id=uuid.uuid4(), game_id=g_win, side="AWAY", playhq_participant_id="c", player_id=None,
                              name="Opp, Oscar", goals=9, behinds=0, bog_ranking=1),
        ])
        await db.commit()

    def J(r):
        # A control run (the router absent) must report, not crash on a KeyError.
        return r.json() if r.status_code < 300 else {}

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

    def client(uid):
        return httpx.AsyncClient(transport=transport, base_url="http://t",
                                 cookies={COOKIE_NAME: create_session_token(str(uid))})

    async with client(u) as c:
        print("\n── Fixtures ──")
        fx = (await c.get("/admin/social/fixtures")).json()
        rows = [f for d in fx.get("dates", []) for f in d["fixtures"]] or [{}]
        check("only the upcoming game", [f.get("opp") for f in rows], ["NEXT OPPONENTS"])
        check("  ... at home, with its time in 12-hour form", (rows[0].get("ha"), rows[0].get("time")), ("H", "2:10 PM"))
        check("  ... the round labelled", (fx.get("dates") or [{}])[0].get("round"), "ROUND 6")
        check("  ... the venue", rows[0].get("venue"), "LWEST OVAL")
        check("a link-driven pull answers as a round", (await c.get("/admin/social/fixtures?q=x")).json().get("kind"), "round")

        print("\n── Results ──")
        rr = (await c.get("/admin/social/results")).json()
        res = {r["opp"]: r for d in rr.get("dates", []) for r in d["results"]}
        E = {}
        check("recent finished games only, newest date first", [r["opp"] for d in rr.get("dates", []) for r in d["results"]],
              ["RIVALS", "HOSTS"])
        check("our score written the football way", res.get("RIVALS", E).get("us"), "12.8 (80)")
        check("  ... a win by 40 points", (res.get("RIVALS", E).get("outcome"), res.get("RIVALS", E).get("margin")), ("W", "BY 40 POINTS"))
        check("an away game reads from our side: a 1-point loss",
              (res.get("HOSTS", E).get("us"), res.get("HOSTS", E).get("them"), res.get("HOSTS", E).get("outcome"), res.get("HOSTS", E).get("margin")),
              ("10.9 (69)", "10.10 (70)", "L", "BY 1 POINT"))
        check("the other club's game is not ours", "X" not in res)

        print("\n── Match lookup ──")
        lk = (await c.get("/admin/social/match-lookup?q=")).json()
        check("an empty box offers recent games to pick", lk.get("kind"), "choose")
        check("  ... newest first", [m["opponent"] for m in lk.get("matches", [])][:2], ["Rivals", "Hosts"])
        lk2 = (await c.get(f"/admin/social/match-lookup?q=https://x/cuw/games/{g_win}")).json()
        check("a match link to one of our games goes straight to it", (lk2.get("kind"), lk2.get("match_id")), ("match", str(g_win)))
        lk3 = (await c.get(f"/admin/social/match-lookup?q={g_theirs}")).json()
        check("another club's game id is not resolved", lk3.get("kind"), "choose")

        print("\n── Best on ground ──")
        pm = (await c.get(f"/admin/social/potm/{g_win}")).json()
        pm.setdefault("players", [{}, {}]); pm.setdefault("match", {})
        check("ranked by best-on-ground votes, not goals", [p.get("last") for p in pm["players"]], ["Star", "Two"])
        check("the opposition's players are not listed", len(pm["players"]), 2)
        check("the football stat block", pm["players"][1].get("football"), {"goals": 4, "behinds": 1, "bog_ranking": 2})
        check("the name split for the post", (pm["players"][0].get("first"), pm["players"][0].get("last")), ("Sam", "Star"))
        check("the match meta", (pm["match"].get("opponent"), pm["match"].get("us"), pm["match"].get("outcome")), ("RIVALS", "12.8 (80)", "W"))
        check("another club's game is refused", (await c.get(f"/admin/social/potm/{g_theirs}")).status_code, 404)

        print("\n── Team lists ──")
        lu = (await c.get(f"/organisations/{org}/lineups?mode=upcoming&limit=20")).json()
        check("only games with a side named", [m["match_id"] for m in lu.get("matches", [])], [str(g_win)])
        ours = next((t for m in lu.get("matches", [])[:1] for t in m["teams"] if t["is_ours"]), {"players": [{}], "published": None})
        check("our side, ordered by jumper number", [p.get("name") for p in ours["players"]], ["Star, Sam", "Two, Terry"])
        check("  ... published, with the captain flagged", (ours.get("published"), ours["players"][0].get("is_captain")), (True, True))
        check("another club's id is refused", (await c.get(f"/organisations/{other}/lineups")).status_code, 404)

        print("\n── Saved post style ──")
        r = await c.patch("/club-admin/settings", json={"socials_style": {"palette": "club", "dark": False, "junk": 1}})
        check("the style saves", r.status_code, 200)
        st = (await c.get("/club-admin/settings")).json()["socials_style"]
        check("  ... cleaned by the shared sanitizer (unknown keys dropped)", st, {"palette": "club", "dark": False})

    async with client(u_other) as c:
        print("\n── Module gate ──")
        check("a club without BetterSocials gets 402", (await c.get("/admin/social/fixtures")).status_code, 402)

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        sys.exit(1)


asyncio.run(main())
