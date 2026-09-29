"""Football competitions, against a real Postgres, through the real AFL boot
path and HTTP stack.

A club playing in two leagues groups its grades into competitions on Merge
Grades, then reads each league on its own through the Competition filter on
the leaderboard and records.

Run:  DATABASE_URL=postgresql+asyncpg://postgres@/afl_verify?host=/tmp/pgsock&port=5544 \
      python verification/verify_afl_competitions.py
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
    from app.models.db import ClubMembership, Grade, Organisation, Player, Season, User, engine, async_session_maker
    from app.models.afl import AflPlayerSeasonStats
    from app.afl_main import app, lifespan
    from app.routers.auth import COOKIE_NAME, create_session_token

    try:
        from app.services.afl import competitions as afl_comp
    except ImportError:
        afl_comp = None
    check("the football competitions service exists", afl_comp is not None)

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    async with lifespan(None):
        pass

    if afl_comp is not None:
        print("\n── A competition read off a season's name ──")
        for raw, want in [("VAFA 2026", "VAFA"), ("2025/26 Southern League Season", "Southern League"),
                          ("VAFA Juniors 2026", "VAFA Juniors"), ("2026", "2026"),
                          ("EFL 2024-25", "EFL")]:
            check(f"{raw!r} -> {want!r}", afl_comp.competition_from_season_name(raw), want)

    org, other, u = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    s_v26, s_v25, s_j26, s_oth = (uuid.uuid4() for _ in range(4))
    g_sen26, g_sen25, g_u19, g_oth = (uuid.uuid4() for _ in range(4))
    p1, p2 = uuid.uuid4(), uuid.uuid4()
    async with async_session_maker() as db:
        db.add_all([
            Organisation(id=org, name="Curtin Uni Wesley", slug="cuw", is_active=True),
            Organisation(id=other, name="Hampton", slug="hh", is_active=True),
            User(id=u, username="a", email="a@x.io", password_hash="x"),
            Season(id=s_v26, organisation_id=org, name="VAFA 2026", year=2026),
            Season(id=s_v25, organisation_id=org, name="VAFA 2025", year=2025),
            Season(id=s_j26, organisation_id=org, name="Juniors League 2026", year=2026),
            Season(id=s_oth, organisation_id=other, name="VAFA 2026", year=2026),
            Player(id=p1, organisation_id=org, name="Senior, Sam"),
            Player(id=p2, organisation_id=org, name="Junior, Jo"),
        ])
        await db.flush()
        db.add_all([
            ClubMembership(user_id=u, club_id=org, role="club_admin", is_primary_admin=True),
            Grade(id=g_sen26, season_id=s_v26, name="Seniors", is_public=True),
            Grade(id=g_sen25, season_id=s_v25, name="Seniors", is_public=True),
            Grade(id=g_u19, season_id=s_j26, name="Under 19s", is_public=True),
            Grade(id=g_oth, season_id=s_oth, name="Seniors", is_public=True),
        ])
        await db.flush()
        rows = [
            (p1, s_v26, g_sen26, 10, 30), (p1, s_v25, g_sen25, 8, 10),
            (p2, s_j26, g_u19, 6, 50),
        ]
        for pid, sid, gid, games, goals in rows:
            # a whole-season row and the per-grade row it sums, as the sync writes both
            db.add(AflPlayerSeasonStats(id=uuid.uuid4(), organisation_id=org, player_id=pid,
                                        season_id=sid, grade_id=None, games=games, goals=goals))
            db.add(AflPlayerSeasonStats(id=uuid.uuid4(), organisation_id=org, player_id=pid,
                                        season_id=sid, grade_id=gid, games=games, goals=goals))
        await db.commit()

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    c = httpx.AsyncClient(transport=transport, base_url="http://t",
                          cookies={COOKIE_NAME: create_session_token(str(u))})

    def J(r):
        return r.json() if r.status_code < 300 else {}

    print("\n── The admin screen before anything is grouped ──")
    d = J(await c.get("/admin/competitions"))
    check("no competitions yet", d.get("competitions"), [])
    check("the season names point at two competitions",
          sorted(a["name"] for a in d.get("associations", [])), ["Juniors League", "VAFA"])
    g = J(await c.get("/admin/competitions/grouping"))
    check("there is no background job to offer on football", g.get("needs_grouping"), False)

    print("\n── Group my grades ──")
    r = await c.post("/admin/competitions/seed")
    check("the seed runs", r.status_code, 200)
    check("  ... and creates the two competitions", J(r).get("created"), 2)
    d = J(await c.get("/admin/competitions"))
    comps = {x["name"]: x for x in d.get("competitions", [])}
    check("VAFA holds both seasons of Seniors", (comps.get("VAFA") or {}).get("grade_count"), 2)
    check("the Juniors League holds the Under 19s", (comps.get("Juniors League") or {}).get("grade_count"), 1)
    r2 = await c.post("/admin/competitions/seed")
    check("a second seed creates nothing", J(r2).get("created"), 0)
    check("  ... and moves nothing", J(r2).get("grades_assigned"), 0)
    async with async_session_maker() as db:
        oth = (await db.execute(text("SELECT competition_id FROM grades WHERE id = :g"), {"g": str(g_oth)})).scalar()
    check("another club's grades are never grouped by our seed", oth, None)

    vafa = (comps.get("VAFA") or {}).get("id")
    jun = (comps.get("Juniors League") or {}).get("id")

    print("\n── The public filter ──")
    club = J(await c.get("/clubs/cuw"))
    check("the club payload lists its competitions in order",
          [x["name"] for x in club.get("stat_competitions", [])], ["Juniors League", "VAFA"])
    sen = next((x for x in club.get("grades", []) if x["name"] == "Seniors"), {})
    check("a grade carries the competition it was played in", sen.get("competition_ids"), [vafa])

    async def goals(**q):
        qs = "&".join(f"{k}={v}" for k, v in q.items() if v)
        rows = J(await c.get(f"/afl-leaderboard/{org}?stat=goals&{qs}")).get("rows", [])
        return {r["name"]: r["value"] for r in rows}

    check("unfiltered, both players count", await goals(), {"Senior, Sam": 40, "Junior, Jo": 50})
    check("VAFA alone counts the senior's two seasons", await goals(competition_id=vafa), {"Senior, Sam": 40})
    check("the Juniors League alone counts the junior", await goals(competition_id=jun), {"Junior, Jo": 50})
    check("a competition and a season intersect",
          await goals(competition_id=vafa, season_id=s_v25), {"Senior, Sam": 10})
    check("a grade inside the wrong competition finds nothing",
          await goals(competition_id=jun, grade_id=g_sen26), {})
    check("a junk competition fails closed rather than showing everyone",
          await goals(competition_id="not-a-uuid"), {})
    async with async_session_maker() as db:
        foreign = (await db.execute(text(
            "INSERT INTO club_competitions (organisation_id, name) VALUES (:o, 'Theirs') RETURNING id"),
            {"o": str(other)})).scalar()
        await db.execute(text("UPDATE grades SET competition_id = :c WHERE id = :g"), {"c": str(foreign), "g": str(g_oth)})
        await db.commit()
    check("another club's competition finds nothing here", await goals(competition_id=str(foreign)), {})

    rec = J(await c.get(f"/afl-records/{org}?competition_id={jun}"))
    top = (rec.get("most_goals_in_a_season") or [{}])[0]
    check("the records honour the competition", (top.get("goals"), top.get("season_name")), (50, "Juniors League 2026"))
    rec = J(await c.get(f"/afl-records/{org}?competition_id={vafa}"))
    top = (rec.get("most_goals_in_a_season") or [{}])[0]
    check("  ... and the other competition's records are its own", top.get("goals"), 30)

    print("\n── Editing ──")
    r = await c.post("/admin/competitions", json={"name": "Night Series"})
    check("a club can add its own competition", r.status_code, 200)
    ns = J(r).get("id")
    check("a second one under the same name is refused",
          (await c.post("/admin/competitions", json={"name": "night series"})).status_code, 422)
    r = await c.post("/admin/competitions/assign", json={"grade_name": "Under 19s", "competition_id": ns})
    check("a grade can be moved into it", J(r).get("season_rows"), 1)
    check("  ... and the filter follows", await goals(competition_id=ns), {"Junior, Jo": 50})
    r = await c.patch(f"/admin/competitions/{vafa}", json={"name": "Amateurs"})
    check("a competition can be renamed", r.status_code, 200)
    r = await c.post("/admin/competitions/reorder", json={"competition_ids": [vafa, ns, jun]})
    check("the order saves", r.status_code, 200)
    names = [x["name"] for x in J(await c.get("/clubs/cuw")).get("stat_competitions", [])]
    check("the public filter follows the order, and drops a competition holding nothing",
          names, ["Amateurs", "Night Series"])
    r = await c.delete(f"/admin/competitions/{ns}")
    check("a competition can be deleted", r.status_code, 200)
    async with async_session_maker() as db:
        still = (await db.execute(text("SELECT competition_id FROM grades WHERE id = :g"), {"g": str(g_u19)})).first()
    check("  ... its grade survives, un-grouped", (still is not None, still[0] if still else "gone"), (True, None))
    check("another club's competition cannot be renamed from here",
          (await c.patch(f"/admin/competitions/{foreign}", json={"name": "Mine"})).status_code, 422)

    await c.aclose()
    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        sys.exit(1)


asyncio.run(main())
