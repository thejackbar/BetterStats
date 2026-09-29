"""Football Settings: draft mode (the public site behind a PIN), typography and
the primary admin transfer, against a real Postgres, through the real AFL boot
path and HTTP stack.

Run:  DATABASE_URL=postgresql+asyncpg://postgres@/afl_verify?host=/tmp/pgsock&port=5544 \
      python verification/verify_afl_settings.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")
os.environ.setdefault("SPORT", "afl")

from sqlalchemy import text  # noqa: E402

PASS = FAIL = 0
FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


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
    from app.models.db import ClubMembership, Organisation, User, engine, async_session_maker
    from app.afl_main import app, lifespan
    from app.routers.auth import COOKIE_NAME, create_session_token

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    async with lifespan(None):
        pass

    org = uuid.uuid4()
    u_primary, u_second, u_member = (uuid.uuid4() for _ in range(3))
    async with async_session_maker() as db:
        db.add_all([
            Organisation(id=org, name="Curtin Uni Wesley", slug="cuw", is_active=True),
            User(id=u_primary, username="prim", email="p@x.io", password_hash="x", display_name="Pat Primary"),
            User(id=u_second, username="sec", email="s@x.io", password_hash="x", display_name="Sam Second"),
            User(id=u_member, username="mem", email="m@x.io", password_hash="x"),
        ])
        await db.flush()
        db.add_all([
            ClubMembership(user_id=u_primary, club_id=org, role="club_admin", is_primary_admin=True),
            ClubMembership(user_id=u_second, club_id=org, role="club_admin", is_primary_admin=False),
            ClubMembership(user_id=u_member, club_id=org, role="club_member", capabilities=["manage_players"]),
        ])
        await db.commit()

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

    def client(u=None):
        return httpx.AsyncClient(transport=transport, base_url="http://t",
                                 cookies={COOKIE_NAME: create_session_token(str(u))} if u else {})

    def J(r):
        return r.json() if r.status_code < 300 else {}

    admin = client(u_primary)
    public = client()

    print("\n── Draft mode ──")
    check("the public site is open to start with", (await public.get("/clubs/cuw")).status_code, 200)
    r = await admin.patch("/club-admin/settings", json={"password_protected": True})
    check("draft mode needs a PIN first", r.status_code, 422)
    check("a PIN must be four digits", (await admin.patch("/club-admin/settings", json={"access_pin": "12a4"})).status_code, 422)
    r = await admin.patch("/club-admin/settings", json={"access_pin": "2468", "password_protected": True})
    check("with a PIN, draft mode turns on", r.status_code, 200)
    s = J(await admin.get("/club-admin/settings"))
    check("  ... and the settings say so, without ever returning the PIN",
          (s.get("password_protected"), s.get("has_pin"), "access_pin" in s, "access_pin_hash" in s), (True, True, False, False))
    r = await public.get("/clubs/cuw")
    check("a visitor without the PIN gets the lock (423)", r.status_code, 423)
    det = r.json().get("detail", {}) if r.status_code == 423 else {}
    check("  ... carrying the club's name for the PIN screen", det.get("name"), "Curtin Uni Wesley")
    check("a wrong PIN is refused", (await public.post("/clubs/cuw/unlock", json={"pin": "1111"})).status_code, 401)
    r = await public.post("/clubs/cuw/unlock", json={"pin": "2468"})
    check("the right PIN unlocks", r.status_code, 200)
    if r.status_code == 200:
        for k, v in r.cookies.items():
            public.cookies.set(k, v)
    check("  ... and that browser now reaches the site", (await public.get("/clubs/cuw")).status_code, 200)
    r = await admin.patch("/club-admin/settings", json={"password_protected": False})
    check("turning it off makes the site public again",
          (r.status_code, (await client().get("/clubs/cuw")).status_code), (200, 200))
    async with async_session_maker() as db:
        await db.execute(text("UPDATE organisations SET password_protected = TRUE, password_protect_reason = 'trial_ended' WHERE id = :o"), {"o": str(org)})
        await db.commit()
    await admin.patch("/club-admin/settings", json={"password_protected": False})
    s = J(await admin.get("/club-admin/settings"))
    check("a lock BetterFootball put on a lapsed trial is not the club's to lift",
          (s.get("password_protected"), s.get("password_protect_reason")), (True, "trial_ended"))
    async with async_session_maker() as db:
        await db.execute(text("UPDATE organisations SET password_protected = FALSE, password_protect_reason = NULL WHERE id = :o"), {"o": str(org)})
        await db.commit()
    check("a member without the Settings permission cannot turn draft mode on",
          (await client(u_member).patch("/club-admin/settings", json={"password_protected": True})).status_code, 403)

    print("\n── Typography ──")
    r = await admin.post("/club-admin/font/display", files={"file": ("DejaVuSans.ttf", FONT.read_bytes(), "font/ttf")},
                         data={"family": "Club Sans"})
    check("a heading font uploads", r.status_code, 200)
    up = J(r)
    check("  ... named as the club asked", ((up.get("font_config") or {}).get("display") or {}).get("family"), "Club Sans")
    pub = J(await client().get("/clubs/cuw"))
    url = pub.get("font_display_url") or ""
    check("the public club payload carries the font", url.startswith(f"/api/images/organisations/{org}/font/display"), True)
    f = await client().get(url.replace("/api", "", 1).split("?")[0]) if url else None
    check("  ... and the images router serves it", f.status_code if f else None, 200)
    r = await admin.patch("/club-admin/settings", json={"font_config": {
        "body": {"source": "preset", "preset": "no-such-font"},
        "mono": {"source": "upload", "family": "Injected"},
        "display": {"source": "upload"}}})
    cfg = J(await admin.get("/club-admin/settings")).get("font_config") or {}
    check("a preset that does not exist is dropped", "body" in cfg, False)
    check("an upload the club never made cannot be claimed", "mono" in cfg, False)
    check("the real upload survives a save", (cfg.get("display") or {}).get("family"), "Club Sans")
    check("a non-font file is refused",
          (await admin.post("/club-admin/font/body", files={"file": ("x.exe", b"MZ", "x/y")})).status_code, 400)
    r = await admin.delete("/club-admin/font/display")
    check("a font can be removed", (r.status_code, J(await client().get("/clubs/cuw")).get("font_display_url")), (200, None))

    print("\n── Primary admin ──")
    info = J(await admin.get("/club-admin/primary-admin"))
    check("the primary admin may hand it over", info.get("can_transfer"), True)
    check("  ... and both club admins are listed",
          sorted(a["username"] for a in info.get("admins", [])), ["prim", "sec"])
    sec = client(u_second)
    check("a club admin who is not the primary cannot transfer it",
          (await sec.post("/club-admin/primary-admin/transfer", json={"user_id": str(u_second)})).status_code, 403)
    check("a club member cannot be made primary",
          (await admin.post("/club-admin/primary-admin/transfer", json={"user_id": str(u_member)})).status_code, 422)
    r = await admin.post("/club-admin/primary-admin/transfer", json={"user_id": str(u_second)})
    check("the primary hands it to another club admin", r.status_code, 200)
    async with async_session_maker() as db:
        prims = (await db.execute(text(
            "SELECT u.username FROM club_memberships m JOIN users u ON u.id = m.user_id "
            "WHERE m.club_id = :o AND m.is_primary_admin"), {"o": str(org)})).scalars().all()
    check("  ... and there is exactly one primary afterwards", prims, ["sec"])

    print("\n── Stats by grade ──")
    from app.models.db import Grade, Player, Season
    from app.models.afl import AflPlayerSeasonStats
    sea, g_sen, g_col, pl = (uuid.uuid4() for _ in range(4))
    async with async_session_maker() as db:
        db.add_all([Season(id=sea, organisation_id=org, name="VAFA 2026", year=2026),
                    Player(id=pl, organisation_id=org, name="Both, Bo")])
        await db.flush()
        db.add_all([Grade(id=g_sen, season_id=sea, name="Seniors"), Grade(id=g_col, season_id=sea, name="Under 19s")])
        await db.flush()
        db.add_all([
            AflPlayerSeasonStats(id=uuid.uuid4(), organisation_id=org, player_id=pl, season_id=sea, grade_id=None, games=15, goals=30),
            AflPlayerSeasonStats(id=uuid.uuid4(), organisation_id=org, player_id=pl, season_id=sea, grade_id=g_sen, games=10, goals=12),
            AflPlayerSeasonStats(id=uuid.uuid4(), organisation_id=org, player_id=pl, season_id=sea, grade_id=g_col, games=5, goals=18),
        ])
        await db.commit()
    boss = client(u_second)  # the primary admin now
    s_ = J(await boss.get("/club-admin/settings"))
    check("Settings offers the categories the club fields",
          [c["key"] for c in s_.get("grade_categories", [])], ["senior", "colts"])
    check("  ... and counts every one by default", s_.get("stats_grade_categories"), None)

    async def lb(grade=None):
        q = f"&grade_id={grade}" if grade else ""
        rows = J(await client().get(f"/afl-leaderboard/{org}?stat=goals{q}")).get("rows", [])
        return rows[0]["value"] if rows else None

    async def career():
        return (J(await client().get(f"/afl-players/{pl}")).get("career") or {}).get("goals")

    check("by default the leaderboard counts both grades", await lb(), 30)
    check("  ... and so does the player's career", await career(), 30)
    r = await boss.patch("/club-admin/settings", json={"stats_grade_categories": ["senior"]})
    check("the club leaves its colts out", r.status_code, 200)
    check("the leaderboard now counts the seniors only", await lb(), 12)
    check("  ... and so does the player's career", await career(), 12)
    top = (J(await client().get(f"/organisations/{org}/summary")).get("top_goal_kickers") or [{}])
    check("  ... and the dashboard's top goal kickers", (top[0] or {}).get("goals"), 12)
    rec = J(await client().get(f"/afl-records/{org}"))
    check("  ... and the records", ((rec.get("most_goals_career") or [{}])[0]).get("goals"), 12)
    check("picking the colts grade still shows it", await lb(g_col), 18)
    check("the public payload says what is left out", J(await client().get("/clubs/cuw")).get("stats_left_out"), ["Colts"])
    await boss.patch("/club-admin/settings", json={"stats_grade_categories": ["senior", "colts", "womens", "masters", "integrated"]})
    check("ticking every category back stores 'every one' (NULL)",
          J(await boss.get("/club-admin/settings")).get("stats_grade_categories"), None)
    check("  ... and the figures are whole again", await lb(), 30)

    for c in (admin, public, sec, boss):
        await c.aclose()
    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        sys.exit(1)


asyncio.run(main())
