"""Football season merge and order, against a real Postgres, through the real
AFL boot path and HTTP stack.

A football season is one PlayHQ competition's season, so one playing year can
arrive as two rows ("VAFA 2026" and "VAFA Juniors 2026"). Merging them must read
as one year on the leaderboard, the results list, the player's season table,
the season records and the public season picker, and undoing must put both back.

Run:  DATABASE_URL=postgresql+asyncpg://postgres@/afl_verify?host=/tmp/pgsock&port=5544 \
      python verification/verify_afl_seasons.py
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
    from app.models.afl import AflGameDetails, AflPlayerSeasonStats
    from app.afl_main import app, lifespan
    from app.routers.auth import COOKIE_NAME, create_session_token

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    async with lifespan(None):
        pass

    org, other, u = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    s_sen, s_jun, s_old, s_other = (uuid.uuid4() for _ in range(4))
    g_sen, g_jun, g_other = (uuid.uuid4() for _ in range(3))
    p1 = uuid.uuid4()
    today = date.today()
    async with async_session_maker() as db:
        db.add_all([
            Organisation(id=org, name="Curtin Uni Wesley", slug="cuw", is_active=True),
            Organisation(id=other, name="Hampton", slug="hh", is_active=True),
            User(id=u, username="a", email="a@x.io", password_hash="x"),
            Season(id=s_sen, organisation_id=org, name="VAFA 2026", year=2026, grassroots_id="phq-1"),
            Season(id=s_jun, organisation_id=org, name="VAFA Juniors 2026", year=2026, grassroots_id="phq-2"),
            Season(id=s_old, organisation_id=org, name="VAFA 2025", year=2025),
            Season(id=s_other, organisation_id=other, name="Other 2026", year=2026),
            Player(id=p1, organisation_id=org, name="Kick, Kim"),
        ])
        await db.flush()
        db.add_all([
            ClubMembership(user_id=u, club_id=org, role="club_admin", is_primary_admin=True),
            Grade(id=g_sen, season_id=s_sen, name="Seniors"),
            Grade(id=g_jun, season_id=s_jun, name="Under 19s"),
            Grade(id=g_other, season_id=s_other, name="Seniors"),
        ])
        await db.flush()
        db.add_all([
            AflPlayerSeasonStats(id=uuid.uuid4(), organisation_id=org, player_id=p1, season_id=s_sen, games=10, goals=20),
            AflPlayerSeasonStats(id=uuid.uuid4(), organisation_id=org, player_id=p1, season_id=s_jun, games=5, goals=15),
            AflPlayerSeasonStats(id=uuid.uuid4(), organisation_id=org, player_id=p1, season_id=s_old, games=8, goals=4),
        ])
        ga, gb = uuid.uuid4(), uuid.uuid4()
        db.add_all([
            Game(id=ga, grade_id=g_sen, played_at=today - timedelta(days=3), home_team="CUW", away_team="Rivals"),
            Game(id=gb, grade_id=g_jun, played_at=today - timedelta(days=4), home_team="CUW", away_team="Kids"),
        ])
        await db.flush()
        db.add_all([
            AflGameDetails(game_id=ga, status="FINAL", our_side="HOME", home_score=80, away_score=40, synced_at=datetime.now()),
            AflGameDetails(game_id=gb, status="FINAL", our_side="HOME", home_score=50, away_score=60, synced_at=datetime.now()),
        ])
        await db.commit()

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    c = httpx.AsyncClient(transport=transport, base_url="http://t",
                          cookies={COOKIE_NAME: create_session_token(str(u))})

    def J(r):
        return r.json() if r.status_code < 300 else {}

    async def lb(season):
        rows = J(await c.get(f"/afl-leaderboard/{org}?stat=goals&season_id={season}")).get("rows", [])
        return rows[0]["value"] if rows else None

    async def results(season):
        d = J(await c.get(f"/organisations/{org}/results?season_id={season}"))
        return sorted(g.get("away_team") for g in (d.get("games") or d.get("results") or []))

    async def profile_seasons():
        d = J(await c.get(f"/afl-players/{p1}"))
        return [(r["season_name"], r["goals"]) for r in d.get("seasons", []) if r.get("grade_id") is None]

    print("\n── Before any merge ──")
    check("the senior season's leaderboard counts its own goals", await lb(s_sen), 20)
    check("the profile draws the two 2026 seasons apart",
          sorted(await profile_seasons()), [("VAFA 2025", 4), ("VAFA 2026", 20), ("VAFA Juniors 2026", 15)])

    print("\n── Merging the juniors' 2026 into the seniors' ──")
    r = await c.post("/club-admin/seasons/merges", json={"canonical_season_id": str(s_sen), "alias_season_id": str(s_jun)})
    check("the merge is accepted", r.status_code, 200)
    check("the leaderboard for 2026 counts both competitions", await lb(s_sen), 35)
    check("  ... and a bookmarked link to the merged-away season shows the whole year", await lb(s_jun), 35)
    check("another year is untouched", await lb(s_old), 4)
    check("the results list for 2026 carries both competitions' games", await results(s_sen), ["Kids", "Rivals"])
    check("the profile draws 2026 once, summed, under the season kept",
          sorted(await profile_seasons()), [("VAFA 2025", 4), ("VAFA 2026", 35)])
    rec = J(await c.get(f"/afl-records/{org}"))
    top = (rec.get("most_goals_in_a_season") or [{}])[0]
    check("the season record reads the merged year as one", (top.get("goals"), top.get("season_name")), (35, "VAFA 2026"))
    club = J(await c.get("/clubs/cuw"))
    names = [s["name"] for s in club.get("seasons", [])]
    check("the public picker no longer offers the merged-away season", "VAFA Juniors 2026" in names, False)
    u19 = next((g for g in club.get("grades", []) if g["name"] == "Under 19s"), {})
    check("  ... and the juniors' grade is offered under the year kept", [str(x) for x in u19.get("season_ids", [])], [str(s_sen)])
    adm = J(await c.get("/club-admin/seasons"))
    jun = next((s for s in adm if s["name"] == "VAFA Juniors 2026"), {})
    check("the admin list says which season it was merged into", str(jun.get("alias_of")), str(s_sen))

    print("\n── Refusals ──")
    check("a season cannot merge into itself",
          (await c.post("/club-admin/seasons/merges", json={"canonical_season_id": str(s_old), "alias_season_id": str(s_old)})).status_code, 400)
    check("another club's season cannot be merged in",
          (await c.post("/club-admin/seasons/merges", json={"canonical_season_id": str(s_sen), "alias_season_id": str(s_other)})).status_code, 404)

    print("\n── Undo ──")
    merges = J(await c.get("/club-admin/seasons/merges"))
    active = [m for m in merges if not m.get("undone")] if isinstance(merges, list) else []
    r = await c.post(f"/club-admin/seasons/merges/{active[0]['id']}/undo") if active else None
    check("the merge can be undone", r.status_code if r else None, 200)
    check("  ... and the two seasons are two again", await lb(s_sen), 20)
    check("  ... on the profile too",
          sorted(await profile_seasons()), [("VAFA 2025", 4), ("VAFA 2026", 20), ("VAFA Juniors 2026", 15)])

    print("\n── Order ──")
    r = await c.put("/club-admin/seasons/reorder", json=[
        {"id": str(s_old), "display_order": 0}, {"id": str(s_jun), "display_order": 1},
        {"id": str(s_sen), "display_order": 2}, {"id": str(s_other), "display_order": 3}])
    check("the club's order saves", r.status_code, 200)
    names = [s["name"] for s in J(await c.get("/clubs/cuw")).get("seasons", [])]
    check("the public picker follows it", names, ["VAFA 2025", "VAFA Juniors 2026", "VAFA 2026"])
    async with async_session_maker() as db:
        oth = (await db.execute(text("SELECT display_order FROM seasons WHERE id = :s"), {"s": str(s_other)})).scalar()
    check("another club's season is not reordered", oth, None)

    print("\n── The sync keeps a club's own season name ──")
    src = (Path(__file__).resolve().parent.parent / "app/services/afl/sync.py").read_text()
    block = src[src.index("row = Season("):src.index("row.synced_at")]
    check("an existing season's name is not overwritten by the sync", "row.name = display" in block, False)

    await c.aclose()
    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        sys.exit(1)


asyncio.run(main())
