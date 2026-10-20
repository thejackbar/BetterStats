"""Verification for the admin "view as a team" mode on the public Fantasy pages,
against a real Postgres.

Request: an admin wants to open the public page (/fantasy/<token>) as any team and
see every page as that team.

Runs the SHIPPED `routers/fantasy.start_view_as` and the public routes
(`landing`, `me`, `ladder`, `view_as_*`) with real signed cookies on real
`starlette` Requests, plus the router's write guard exactly as FastAPI runs it.
Only the club entitlement check is stubbed.

CONTROL (`--control`): the public router at git HEAD. It must fail on the missing
behaviour (no view-as in `landing`, no guard), read through presence-safe accessors.

Run:  DATABASE_URL=postgresql+asyncpg://root@/fantasy_test?host=/var/run/postgresql \
      python verification/verify_fantasy_view_as.py [--control]
"""
from __future__ import annotations

import asyncio
import importlib.util
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import HTTPException, Response
from jose import jwt
from starlette.requests import Request
from sqlalchemy import text

import verify_fantasy_unsettle as base          # same seed: club ORG, managers X and Y, squads, season
from app.config.settings import settings
from app.models.db import Organisation, FantasyManager
from app.routers import fantasy as fantasy_router
from app.routers import public_fantasy as pub

Session, check, ORG, MGR_X, MGR_Y, SQ_X = base.Session, base.check, base.ORG, base.MGR_X, base.MGR_Y, base.SQ_X
REPO = Path(__file__).resolve().parent.parent.parent
TOKEN = "tok-view-as"
ADMIN = uuid.uuid4()


def req(method="GET", path="/api/public/fantasy/x", cookies: dict | None = None) -> Request:
    headers = []
    if cookies:
        headers.append((b"cookie", "; ".join(f"{k}={v}" for k, v in cookies.items()).encode()))
    return Request({"type": "http", "method": method, "path": path, "headers": headers, "query_string": b"",
                    "server": ("t", 80), "client": ("1.2.3.4", 1), "scheme": "http"})


def cookie_of(resp: Response, name: str) -> str | None:
    for k, v in resp.raw_headers:
        if k == b"set-cookie" and v.decode().startswith(name + "="):
            val = v.decode().split(";", 1)[0].split("=", 1)[1]
            return None if val in ('""', "") else val
    return None


def deleted(resp: Response, name: str) -> bool:
    return any(k == b"set-cookie" and v.decode().startswith(name + "=") and "Max-Age=0" in v.decode()
               for k, v in resp.raw_headers)


async def guard(r: Request) -> int | None:
    try:
        await pub._block_writes_while_viewing(r)
        return None
    except HTTPException as e:
        return e.status_code


async def checks(module=pub) -> None:
    pub.org_has_module = lambda *a, **k: True        # entitlement is not under test
    async with Session() as s:
        org = await s.get(Organisation, ORG)
        org.fantasy_link_token = TOKEN
        await s.commit()
        club = await s.get(Organisation, ORG)

    print("1. Starting a view as a team (admin route)")
    resp = Response()
    async with Session() as s:
        out = await fantasy_router.start_view_as(
            fantasy_router.ViewAsBody(manager_id=str(MGR_X)), resp, club=club, user=type("U", (), {"id": ADMIN})(), db=s, _=None)
    va = cookie_of(resp, pub.VIEW_AS_COOKIE)
    check("it returns the public link and sets the view-as cookie", out["url"] == f"/fantasy/{TOKEN}" and bool(va), repr(out))
    # A manager from another club is refused.
    other = uuid.uuid4()
    async with Session() as s:
        s.add(Organisation(id=other, name="Other CC", slug="other", is_active=True))
        await s.flush()
        s.add(FantasyManager(id=uuid.uuid4(), organisation_id=other, display_name="Stranger"))
        await s.commit()
        stranger = (await s.execute(text("SELECT id FROM fantasy_managers WHERE organisation_id=:o"), {"o": other})).scalar()
    try:
        async with Session() as s:
            await fantasy_router.start_view_as(
                fantasy_router.ViewAsBody(manager_id=str(stranger)), Response(), club=club, user=type("U", (), {"id": ADMIN})(), db=s, _=None)
        check("another club's manager is refused", False, "no error")
    except HTTPException as e:
        check("another club's manager is refused", e.status_code == 404, str(e.status_code))

    print("2. The public pages show that team")
    cx = req(cookies={pub.VIEW_AS_COOKIE: va})
    async with Session() as s:
        land = await pub.landing(TOKEN, cx, s)
        me = await pub.me(TOKEN, cx, s)
        lad = await pub.ladder(TOKEN, cx, s)
    check("landing signs the browser in as X, and says it is an admin view",
          (land.get("me") or {}).get("id") == str(MGR_X) and (land.get("view_as") or {}).get("display_name") == "Xavier", repr(land.get("view_as", "<no view_as key>")))
    check("my team is X's squad", (me.get("squad") or {}).get("id") == str(SQ_X) or (me.get("squad") or {}).get("team_name") == "X Team", repr((me.get("squad") or {}).get("team_name")))
    check("the ladder marks X as 'you'", [r["team_name"] for r in lad["ladder"] if r.get("you")] == ["X Team"], repr(lad["ladder"]))
    async with Session() as s:
        plain = await pub.landing(TOKEN, req(), s)
    check("with no cookie nothing changes (not signed in, no view_as)", plain.get("me") is None and plain.get("view_as") in (None, "<absent>"), repr(plain.get("view_as", "<absent>")))
    tampered = req(cookies={pub.VIEW_AS_COOKIE: va[:-3] + "abc"})
    async with Session() as s:
        t = await pub.landing(TOKEN, tampered, s)
    check("a tampered cookie is ignored", t.get("me") is None, repr(t.get("me")))
    forged = jwt.encode({"club": str(ORG), "mgr": str(MGR_X), "typ": "fantasy", "exp": 9999999999}, settings.secret_key, algorithm=settings.algorithm)
    async with Session() as s:
        f = await pub.landing(TOKEN, req(cookies={pub.VIEW_AS_COOKIE: forged}), s)
    check("a member-session token is not accepted as a view-as", f.get("view_as") in (None, "<absent>"), repr(f.get("view_as", "<absent>")))
    wrong_club = jwt.encode({"club": str(other), "mgr": str(MGR_X), "by": str(ADMIN), "typ": "fantasy_viewas", "exp": 9999999999}, settings.secret_key, algorithm=settings.algorithm)
    async with Session() as s:
        w = await pub.landing(TOKEN, req(cookies={pub.VIEW_AS_COOKIE: wrong_club}), s)
    check("a view-as for another club does nothing here", w.get("me") is None, repr(w.get("me")))

    print("3. Read only")
    check("a GET goes through", await guard(req("GET", cookies={pub.VIEW_AS_COOKIE: va})) is None)
    for method, path in (("POST", "/api/public/fantasy/t/transfer"), ("POST", "/api/public/fantasy/t/squad"),
                         ("POST", "/api/public/fantasy/t/chip"), ("POST", "/api/public/fantasy/t/logout"),
                         ("DELETE", "/api/public/fantasy/t/leagues/1"), ("POST", "/api/public/fantasy/t/profile")):
        check(f"{method} {path.split('/t/')[1]} is refused", await guard(req(method, path, {pub.VIEW_AS_COOKIE: va})) == 403)
    check("a normal member's POST is untouched", await guard(req("POST", "/api/public/fantasy/t/transfer", {})) is None)
    check("exit and switch are let through", await guard(req("POST", "/api/public/fantasy/t/view-as/exit", {pub.VIEW_AS_COOKIE: va})) is None
          and await guard(req("POST", "/api/public/fantasy/t/view-as/switch", {pub.VIEW_AS_COOKIE: va})) is None)
    wired = any(d.dependency is pub._block_writes_while_viewing for d in pub.router.dependencies)
    check("the guard is wired onto the public router", wired)

    # Through a real FastAPI app: the dependency on the router, as the server runs it.
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.models.db import get_db
    app = FastAPI()
    app.include_router(pub.router)
    class _NoDb:                       # the guard is under test, so no real connection (another event loop)
        async def execute(self, *a, **k): raise RuntimeError("reached the endpoint")
    async def _db():
        yield _NoDb()
    app.dependency_overrides[get_db] = _db
    with TestClient(app, raise_server_exceptions=False) as tc:
        r = tc.post(f"/public/fantasy/{TOKEN}/chip", json={"chip": "wildcard"}, cookies={pub.VIEW_AS_COOKIE: va})
        check("over HTTP a chip play is refused with the reason", r.status_code == 403 and "changes are switched off" in r.text, f"{r.status_code} {r.text[:80]}")
        r = tc.post(f"/public/fantasy/{TOKEN}/view-as/exit", cookies={pub.VIEW_AS_COOKIE: va})
        check("over HTTP exit works and clears the cookie", r.status_code == 200 and pub.VIEW_AS_COOKIE in r.headers.get("set-cookie", ""), f"{r.status_code} {r.headers.get('set-cookie')}")
        r = tc.post(f"/public/fantasy/{TOKEN}/chip", json={"chip": "wildcard"})
        check("over HTTP without a view-as the same call is not blocked by the guard", r.status_code != 403 or "switched off" not in r.text, f"{r.status_code} {r.text[:80]}")

    print("4. Switch team and exit")
    async with Session() as s:
        teams = await pub.view_as_managers(TOKEN, cx, s)
    check("the switcher lists every team, ranked", [t["display_name"] for t in teams["teams"]][:2] in (["Xavier", "Yara"], ["Yara", "Xavier"]) and len(teams["teams"]) == 2, repr(teams))
    try:
        async with Session() as s:
            await pub.view_as_managers(TOKEN, req(), s)
        check("the team list is closed without a view-as", False, "no error")
    except HTTPException as e:
        check("the team list is closed without a view-as", e.status_code == 403, str(e.status_code))
    r2 = Response()
    async with Session() as s:
        await pub.view_as_switch(TOKEN, pub.ViewAsSwitch(manager_id=str(MGR_Y)), cx, r2, s)
    va2 = cookie_of(r2, pub.VIEW_AS_COOKIE)
    async with Session() as s:
        land2 = await pub.landing(TOKEN, req(cookies={pub.VIEW_AS_COOKIE: va2}), s)
    check("switching moves the view to Y", (land2["me"] or {}).get("id") == str(MGR_Y), repr(land2["me"]))
    check("the switch keeps who started it", jwt.decode(va2, settings.secret_key, algorithms=[settings.algorithm]).get("by") == str(ADMIN))
    try:
        async with Session() as s:
            await pub.view_as_switch(TOKEN, pub.ViewAsSwitch(manager_id=str(stranger)), cx, Response(), s)
        check("switching to another club's manager is refused", False, "no error")
    except HTTPException as e:
        check("switching to another club's manager is refused", e.status_code == 404, str(e.status_code))
    r3 = Response()
    await pub.view_as_exit(TOKEN, r3)
    check("exit clears the cookie", deleted(r3, pub.VIEW_AS_COOKIE))
    async with Session() as s:
        row = (await s.execute(text("SELECT total_points, free_transfers FROM fantasy_squads WHERE id=:i"), {"i": SQ_X})).first()
        cred = (await s.execute(text("SELECT credential_hash FROM fantasy_managers WHERE id=:i"), {"i": MGR_X})).scalar()
    check("X's squad and sign-in were never touched", row is not None and cred is None, repr((row, cred)))


async def run_control() -> int:
    src = subprocess.check_output(["git", "show", "HEAD:backend/app/routers/public_fantasy.py"], cwd=REPO, text=True)
    tmp = Path(__file__).resolve().parent / "_public_fantasy_control.py"
    tmp.write_text(src)
    try:
        spec = importlib.util.spec_from_file_location("public_fantasy_control", tmp)
        old = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(old)
        check("HEAD has a view-as", hasattr(old, "issue_view_as") and hasattr(old, "view_as_exit"), "no view-as in the public router")
        check("HEAD guards writes while viewing", hasattr(old, "_block_writes_while_viewing"), "no write guard")
        async with Session() as s:
            org = await s.get(Organisation, ORG)
            org.fantasy_link_token = TOKEN
            await s.commit()
        old.org_has_module = lambda *a, **k: True
        async with Session() as s:
            land = await old.landing(TOKEN, req(), s)
        check("HEAD's landing reports a view_as key", "view_as" in land, f"keys: {sorted(land)}")
    finally:
        tmp.unlink(missing_ok=True)
    return base.FAIL


async def main() -> int:
    await base.build_schema()
    await base.seed()
    if "--control" in sys.argv:
        return await run_control()
    await checks()
    return base.FAIL


if __name__ == "__main__":
    failed = asyncio.run(main())
    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    sys.exit(1 if failed else 0)
