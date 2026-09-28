"""Verification for the football Activity Log, Milestones and Matches admin
endpoints (routers/afl/admin_extras.py), against a real Postgres, through the
shipped AFL boot path and the shipped route bodies.

Run:  DATABASE_URL=postgresql+asyncpg://postgres@/afl_verify?host=/tmp/pgsock&port=5544 \
      python verification/verify_afl_admin_extras.py
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
    from app.models.db import Grade, Organisation, Player, Season, User, Game, engine, async_session_maker
    from app.models.afl import AflGameDetails, AflPlayerGameLine, AflPlayerSeasonStats
    from app.afl_main import lifespan
    try:
        from app.routers.afl import admin_extras as ax
    except ImportError as e:
        check("admin_extras router exists", str(e), "present")
        print(f"\n{PASS} passed, {FAIL} failed")
        return

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    async with lifespan(None):
        pass

    org, other = uuid.uuid4(), uuid.uuid4()
    uid = uuid.uuid4()
    season, gsen = uuid.uuid4(), uuid.uuid4()
    oseason, ograde = uuid.uuid4(), uuid.uuid4()
    p_near, p_hit, p_far, p_other = (uuid.uuid4() for _ in range(4))
    today = date.today()

    async with async_session_maker() as db:
        db.add_all([
            Organisation(id=org, name="Curtin Uni Wesley", slug="cuw", is_active=True),
            Organisation(id=other, name="Hampton Hammers", slug="hh", is_active=True),
            User(id=uid, username="admin", email="a@b.c", password_hash="x", display_name="Alex Admin"),
            Season(id=season, organisation_id=org, name="2026", year=2026),
            Season(id=oseason, organisation_id=other, name="2026", year=2026),
            Player(id=p_near, organisation_id=org, name="Near, Nat"),
            Player(id=p_hit, organisation_id=org, name="Hit, Harry"),
            Player(id=p_far, organisation_id=org, name="Far, Fred"),
            Player(id=p_other, organisation_id=other, name="Other, Oscar"),
        ])
        await db.flush()
        db.add_all([
            Grade(id=gsen, season_id=season, name="Seniors"),
            Grade(id=ograde, season_id=oseason, name="Seniors"),
        ])
        await db.flush()
        # Career rollups: Near is 48 games (2 short of 50), Hit is on 101
        # goals and kicked 3 in a recent game (so crossed 100), Far is nowhere.
        db.add_all([
            AflPlayerSeasonStats(id=uuid.uuid4(), organisation_id=org, player_id=p_near, season_id=season, games=48, goals=5),
            AflPlayerSeasonStats(id=uuid.uuid4(), organisation_id=org, player_id=p_hit, season_id=season, games=20, goals=101),
            AflPlayerSeasonStats(id=uuid.uuid4(), organisation_id=org, player_id=p_far, season_id=season, games=7, goals=1),
            AflPlayerSeasonStats(id=uuid.uuid4(), organisation_id=other, player_id=p_other, season_id=oseason, games=49, goals=0),
        ])
        g_recent, g_old, g_pending, g_import, g_other = (uuid.uuid4() for _ in range(5))
        db.add_all([
            Game(id=g_recent, grade_id=gsen, played_at=today - timedelta(days=5), home_team="CUW", away_team="Rivals"),
            Game(id=g_old, grade_id=gsen, played_at=today - timedelta(days=200), home_team="CUW", away_team="Oldies"),
            Game(id=g_pending, grade_id=gsen, played_at=today - timedelta(days=2), home_team="Hosts", away_team="CUW"),
            Game(id=g_import, grade_id=gsen, played_at=date(1975, 5, 3), home_team="CUW", away_team="History FC"),
            Game(id=g_other, grade_id=ograde, played_at=today, home_team="HH", away_team="X"),
        ])
        await db.flush()
        db.add_all([
            AflGameDetails(game_id=g_recent, status="FINAL", our_side="HOME", home_score=80, away_score=40, synced_at=__import__("datetime").datetime.now()),
            AflGameDetails(game_id=g_old, status="FINAL", our_side="HOME", home_score=60, away_score=70, synced_at=__import__("datetime").datetime.now()),
            AflGameDetails(game_id=g_pending, status="FINAL", our_side="AWAY"),
            AflGameDetails(game_id=g_import, status="FINAL", our_side="HOME", home_score=90, away_score=10),
            AflGameDetails(game_id=g_other, status="FINAL", our_side="HOME", synced_at=__import__("datetime").datetime.now()),
        ])
        await db.flush()
        await db.execute(text("UPDATE afl_game_details SET source='import' WHERE game_id=:g"), {"g": str(g_import)})
        db.add_all([
            AflPlayerGameLine(id=uuid.uuid4(), game_id=g_recent, side="HOME", playhq_participant_id="a", player_id=p_hit, name="Hit", goals=3, behinds=0),
            AflPlayerGameLine(id=uuid.uuid4(), game_id=g_recent, side="HOME", playhq_participant_id="b", player_id=p_near, name="Near", goals=0, behinds=0),
            # Opposition line on the same game: never ours.
            AflPlayerGameLine(id=uuid.uuid4(), game_id=g_recent, side="AWAY", playhq_participant_id="c", player_id=None, name="Opp", goals=9, behinds=0),
            AflPlayerGameLine(id=uuid.uuid4(), game_id=g_old, side="HOME", playhq_participant_id="a", player_id=p_hit, name="Hit", goals=4, behinds=0),
        ])
        await db.execute(text("""
            INSERT INTO audit_logs (org_id, user_id, action, target_type, details)
            VALUES (:o, :u, 'merge.players', 'player', '{"kept": "Hit, Harry"}'),
                   (:x, NULL, 'import.commit', 'batch', '{}')
        """), {"o": str(org), "u": str(uid), "x": str(other)})
        await db.commit()

    club = type("C", (), {"id": org})()
    async with async_session_maker() as db:
        print("\n── Activity Log ──")
        log = await ax.list_activity_log(limit=100, _=None, club=club, db=db)
        check("the club's own action is listed", [r["action"] for r in log], ["merge.players"])
        check("  ... naming who did it", log[0]["user_name"], "Alex Admin")
        check("  ... with its details", log[0]["details"].get("kept"), "Hit, Harry")

        print("\n── Milestones ──")
        ms = await ax.list_milestones(days=60, _=None, club=club, db=db)
        up = {(m["name"], m["type"], m["target"]) for m in ms["upcoming"]}
        check("48 games is 2 short of 50", ("Near, Nat", "games", 50) in up)
        check("a player nowhere near is not listed", not any(m["name"] == "Far, Fred" for m in ms["upcoming"]))
        check("another club's player is not listed", not any(m["name"] == "Other, Oscar" for m in ms["upcoming"]))
        reached = {(m["name"], m["type"], m["target"]) for m in ms["reached"]}
        check("101 goals after kicking 3 recently reads as reaching 100", ("Hit, Harry", "goals", 100) in reached)
        check("nothing reached for a player who crossed no line", not any(m["name"] == "Near, Nat" for m in ms["reached"]))
        wide = await ax.list_milestones(days=365, _=None, club=club, db=db)
        # With a year's window the 4-goal game from 200 days ago comes in too:
        # 101 - 7 = 94, still one crossing of 100, never two.
        check("a wider window still counts the crossing once",
              [m for m in wide["reached"] if m["name"] == "Hit, Harry" and m["type"] == "goals"].__len__(), 1)

        print("\n── Matches ──")
        games = await ax.list_games(season_id=None, source=None, q=None, limit=200, offset=0, _=None, club=club, db=db)
        check("every game of this club, none of the other's", games["total"], 4)
        by_away = {g["away_team"]: g for g in games["games"]}
        check("newest first", games["games"][0]["away_team"], "CUW")
        check("a finished synced game with no stats pull is pending", by_away["CUW"]["stats_pending"], True)
        check("a synced game with stats is not pending", by_away["Rivals"]["stats_pending"], False)
        check("  ... and counts only our side's lines", by_away["Rivals"]["our_lines"], 2)
        check("an imported game reads as imported", by_away["History FC"]["source"], "import")
        check("  ... and is never pending", by_away["History FC"]["stats_pending"], False)
        imp = await ax.list_games(season_id=None, source="import", q=None, limit=200, offset=0, _=None, club=club, db=db)
        check("the source filter narrows", imp["total"], 1)
        srch = await ax.list_games(season_id=None, source=None, q="oldies", limit=200, offset=0, _=None, club=club, db=db)
        check("the search finds a team case-insensitively", [g["away_team"] for g in srch["games"]], ["Oldies"])
        page = await ax.list_games(season_id=None, source=None, q=None, limit=2, offset=2, _=None, club=club, db=db)
        check("paging keeps the whole total", (len(page["games"]), page["total"]), (2, 4))

    print("\n── Club logo and the Settings permission ──")
    import httpx
    from app.afl_main import app
    from app.models.db import ClubMembership
    from app.routers.auth import COOKIE_NAME, create_session_token
    u_admin, u_member, u_setter = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with async_session_maker() as db:
        db.add_all([
            User(id=u_admin, username="ladmin", email="la@x.io", password_hash="x"),
            User(id=u_member, username="lmember", email="lm@x.io", password_hash="x"),
            User(id=u_setter, username="lsetter", email="ls@x.io", password_hash="x"),
        ])
        await db.flush()
        db.add_all([
            ClubMembership(user_id=u_admin, club_id=org, role="club_admin", is_primary_admin=True),
            ClubMembership(user_id=u_member, club_id=org, role="club_member", capabilities=["manage_players"]),
            ClubMembership(user_id=u_setter, club_id=org, role="club_member", capabilities=["manage_settings"]),
        ])
        await db.execute(text("UPDATE organisations SET logo_url = 'https://cdn.playhq.com/crest.png' WHERE id = :o"), {"o": str(org)})
        await db.commit()
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

    def client(u):
        return httpx.AsyncClient(transport=transport, base_url="http://t",
                                 cookies={COOKIE_NAME: create_session_token(str(u))})

    png = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63f8ffff3f0005fe02fea7d69ea40000000049454e44ae426082")
    async with client(u_admin) as c:
        r = await c.post("/club-admin/logo", files={"file": ("crest.png", png, "image/png")})
        check("a club admin uploads a logo", r.status_code, 200)
        url = (r.json() if r.status_code < 300 else {}).get("logo_url") or ""
        check("  ... stored API-relative, not under /api (which is cricket's backend)",
              url.startswith("images/organisations/"), True)
        img = await c.get("/" + url.split("?")[0]) if url else None
        check("  ... and the images router serves it", (img.status_code, img.content[:4]) if img else None, (200, png[:4]))
        s = (await c.get("/club-admin/settings")).json()
        check("  ... the settings read carries it", s.get("logo_url"), url)
        r = await c.post("/club-admin/logo", files={"file": ("crest.exe", b"MZ", "application/octet-stream")})
        check("a non-image is refused", r.status_code, 400)
        r = await c.delete("/club-admin/logo")
        check("removing it clears the column", (r.status_code, (await c.get("/club-admin/settings")).json().get("logo_url")), (200, None))
    async with client(u_member) as c:
        check("a member without the Settings permission cannot save settings",
              (await c.patch("/club-admin/settings", json={"short_name": "X"})).status_code, 403)
        check("  ... nor upload a logo",
              (await c.post("/club-admin/logo", files={"file": ("c.png", png, "image/png")})).status_code, 403)
    async with client(u_setter) as c:
        check("a member holding the Settings permission can",
              (await c.patch("/club-admin/settings", json={"short_name": "CUW"})).status_code, 200)

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        sys.exit(1)


asyncio.run(main())
