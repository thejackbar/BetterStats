"""Verification of who may read and change a player through the /players routes.

Found while reading code for the privacy work, confirmed by running them:

  * `PATCH /players/{id}` renamed any player at any club for NOBODY: no login.
  * `GET` and `PATCH /players/{id}/profile` checked "is a club admin" but not "of
    THIS player's club", so any club's admin could read another club's player's
    email, phone and date of birth and overwrite them.
  * `POST /players/{id}/claim` was on the privacy allowlist, so a person who asked to
    be removed could still have their profile claimed.

Each "refused" check is paired with a check that the legitimate case still works
(an admin on their OWN club's player, a normal claim), so a route that refuses
everything cannot pass (rule 21).

Run:  DATABASE_URL=postgresql+asyncpg://root@/route_access_test?host=/var/run/postgresql \
      python verification/verify_player_route_access.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

import httpx
from jose import jwt
from sqlalchemy import text

import app.models.scout  # noqa: F401
import verify_hide_juniors as hj
from app.config.settings import settings
from app.routers.auth import COOKIE_NAME

PASS = FAIL = 0
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        FAILURES.append(label)
        print(f"  FAIL {label}{('  — ' + detail) if detail else ''}")


async def scalar(sql: str, **kw):
    async with hj.engine.connect() as cn:
        return (await cn.execute(text(sql), kw)).scalar()


async def main() -> int:
    async with hj.engine.begin() as c:
        await c.execute(text("DROP SCHEMA public CASCADE"))
        await c.execute(text("CREATE SCHEMA public"))
    await hj.build_schema()
    src = open(Path(__file__).resolve().parent / "verify_merge_carry.py").read()
    ns: dict = {}
    exec(src[src.index("EXTRA_DDL = ("):src.index("ORG = uuid.UUID")], ns)
    from app.services.player_privacy_ddl import STATEMENTS as PRIVACY_DDL
    async with hj.engine.begin() as c:
        for st in list(ns["EXTRA_DDL"]) + PRIVACY_DDL:
            await c.execute(text(st))
    async with hj.Session() as s:
        await hj.seed(s)

    mine, theirs = hj.P["S1"], hj.OPP           # S1 is club A's player, OPP is club B's
    removed = hj.P["M1"]                          # a person who asked to be removed
    await hj.engine.dispose()
    async with hj.engine.begin() as c:
        await c.execute(text("UPDATE players SET email='b.player@rival.test', phone='0400 555 666' WHERE id=:i"), {"i": theirs})
        await c.execute(text("UPDATE players SET is_public=false, privacy_hidden_at=NOW(), privacy_hidden_by='t' WHERE id=:i"), {"i": removed})

    from app.main import app
    tok = jwt.encode({"sub": str(hj.USER_ADMIN)}, settings.secret_key, algorithm=settings.algorithm)
    ck = {COOKIE_NAME: tok}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        print("rename: PATCH /players/{id}")
        before = await scalar("select name from players where id=:i", i=mine)
        r = await c.patch(f"/players/{mine}", json={"name": "Renamed By Nobody"})
        after = await scalar("select name from players where id=:i", i=mine)
        check("an anonymous rename does not rename anybody (no longer a route)", after == before and r.status_code in (404, 405), f"{r.status_code} {after}")
        r = await c.patch(f"/players/{mine}", json={"name": "Renamed By Admin"}, cookies=ck)
        check("...and not for a signed-in admin either (the club's rename path is /club-admin/players/{id})",
              await scalar("select name from players where id=:i", i=mine) == before and r.status_code in (404, 405), str(r.status_code))
        r = await c.patch(f"/club-admin/players/{mine}", json={"display_name_override": "Sam The Man"}, cookies=ck)
        check("control: the club's own rename path still works for its own player",
              r.status_code == 200 and await scalar("select display_name_override from players where id=:i", i=mine) == "Sam The Man", str(r.status_code))

        print("profile: another club's player")
        r = await c.get(f"/players/{theirs}/profile", cookies=ck)
        check("an admin of club A cannot READ club B's player's profile (404, no email or phone in it)",
              r.status_code == 404 and "rival.test" not in r.text and "0400 555" not in r.text, f"{r.status_code} {r.text[:80]}")
        r = await c.patch(f"/players/{theirs}/profile", json={"phone": "0000 CHANGED"}, cookies=ck)
        check("...and cannot CHANGE it", r.status_code == 404 and await scalar("select phone from players where id=:i", i=theirs) == "0400 555 666",
              f"{r.status_code}")
        r = await c.get(f"/players/{theirs}/aliases", cookies=ck)
        check("(the aliases routes were already scoped)", r.status_code == 404)
        r = await c.get(f"/players/{mine}/profile", cookies=ck)
        check("control: the same admin reads their OWN club's player", r.status_code == 200, str(r.status_code))
        r = await c.patch(f"/players/{mine}/profile", json={"phone": "0411 222 333"}, cookies=ck)
        check("control: ...and edits them", r.status_code == 200 and await scalar("select phone from players where id=:i", i=mine) == "0411 222 333", str(r.status_code))
        r = await c.get(f"/players/{theirs}/profile")
        check("control: with no login at all it is 401", r.status_code == 401)

        print("claim: a person who asked to be removed")
        r = await c.post(f"/players/{removed}/claim", cookies=ck)
        check("a removed person's profile cannot be claimed (404)", r.status_code == 404 and
              await scalar("select claimed from players where id=:i", i=removed) in (False, None), str(r.status_code))
        r = await c.post(f"/players/{hj.P['J1']}/claim", cookies=ck)
        check("control: an ordinary unclaimed profile can still be claimed", r.status_code == 200, f"{r.status_code} {r.text[:80]}")

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAILURES:
        print("FAILED:", *FAILURES, sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
