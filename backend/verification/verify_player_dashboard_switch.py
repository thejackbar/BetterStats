"""Verification: the Player Dashboard is switched on from BetterStats settings, not BetterSelect.

Asked for: "to turn on the Player Dashboard you need BetterSelect, but really this should be turned
on through club settings, as cards and stats only need BetterStats."

The player's page already opened for a club without BetterSelect, but every control for it (on/off,
the club site button, the PIN, which modules show, the link and QR) lived under `/availability/self-service`,
which is behind `require_module("select")`. This pins the new module-free admin route and the one rule
that the public link and the club site button now share (`link_live`, `availability_live`, `dashboard_live`).

Real HTTP through the mounted app for the gate (a BetterStats-only club reaches the new route; the old
route still answers 402 for it), and the shipped route bodies for the rest.

What it pins:
  * the old route is still BetterSelect-only (402), the new one is not
  * a club with no BetterSelect: an untouched club is still live (no link breaks), Off closes the link and
    the site button, On reopens it with the SAME token, hiding the button leaves the link working
  * a club that had hidden the page before (legacy NULL + hidden) stays closed until it chooses
  * a club WITH BetterSelect has two switches, one per side of the link: BetterSelect's self-service switch
    for availability, votes and its sections, and the dashboard switch from BetterStats for cards, season and
    the club site button. Neither moves the other; until the club chooses, the dashboard follows the old switch
  * availability answers stay refused without BetterSelect (`need_select=True` still 404)
  * a key that is not sent leaves its setting alone; an empty module list is a real choice; unknown keys drop
  * a person without MANAGE_SETTINGS gets 403 and nothing changes
  * regenerating the link kills the old token

CONTROL MODE: against the previous commit the router, the column and `link_live` do not exist. Every read is
presence-safe, so the control FAILS the checks instead of crashing.

Run on its own database (rule 24):
  DATABASE_URL=postgresql+asyncpg://... python verification/verify_player_dashboard_switch.py
"""
from __future__ import annotations

import asyncio
import importlib
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import verify_selection_same_day as base
from app.models.db import ClubMembership, Organisation, User

engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)
check = base.check

HAS_COLUMN = "player_dashboard_enabled" in Organisation.__table__.columns


def guarded(name):
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


async def main():
    await base.build_schema()
    async with engine.begin() as conn:
        for mod in ("availability_maybe_ddl", "availability_site_link_ddl", "player_dashboard_ddl"):
            m = guarded(f"app.services.{mod}")
            for stmt in (m.STATEMENTS if m else []):
                await conn.execute(text(stmt))

    import httpx
    from fastapi import HTTPException
    import app.routers.public_availability as pa
    import app.routers.clubs as clubs
    from app.main import app
    from app.routers.auth import get_current_user
    pdash = guarded("app.services.player_dashboard")
    pda = guarded("app.routers.player_dashboard_admin")

    ids = {n: uuid.uuid4() for n in ("plain", "hidden", "sel_off", "sel_on", "other", "admin", "member")}
    tok = {n: "t-" + uuid.uuid4().hex for n in ("plain", "hidden", "sel_off", "sel_on", "other")}

    def mk(n, **kw):
        return Organisation(id=ids[n], name=f"{n} CC", is_active=True, slug=f"{n}-{ids[n].hex[:8]}",
                            availability_link_token=tok.get(n), **kw)

    async with Session() as db:
        db.add(mk("plain", module_overrides=[]))
        db.add(mk("hidden", module_overrides=[], availability_show_on_site=False))
        db.add(mk("sel_off", module_overrides=["select"], availability_self_service_enabled=False))
        db.add(mk("sel_on", module_overrides=["select"], availability_self_service_enabled=True))
        db.add(mk("other", module_overrides=[]))
        await db.flush()
        for who, club, caps in (("admin", "plain", []), ("member", "plain", [])):
            db.add(User(id=ids[who], username=f"{who}-{ids[who].hex[:6]}", email=f"{who}@x.test", password_hash="x", display_name=who))
        await db.flush()
        db.add(ClubMembership(club_id=ids["plain"], user_id=ids["admin"], role="club_admin", capabilities=[]))
        db.add(ClubMembership(club_id=ids["plain"], user_id=ids["member"], role="club_member", capabilities=[]))
        await db.commit()

    async def org(n):
        async with Session() as db:
            return await db.get(Organisation, ids[n])

    async def opens(n, need_select=False, token=None, need_dashboard=False):
        async with Session() as db:
            try:
                kw = {"need_dashboard": True} if need_dashboard else {}
                await pa._club_for_token(db, token or tok[n], need_select=need_select, **kw)
                return True
            except TypeError:
                return "unsupported"  # the previous commit has no dashboard side to ask for
            except HTTPException as e:
                return False if e.status_code == 404 else f"status {e.status_code}"

    async def button(n):
        return clubs._player_page_path(await org(n))

    acting = {"who": "admin"}

    async def current_user():
        async with Session() as db:
            return await db.get(User, ids[acting["who"]])

    app.dependency_overrides[get_current_user] = current_user
    transport = httpx.ASGITransport(app=app)

    async def http(method, path, **kw):
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            return await c.request(method, path, **kw)

    # ── the gate: the whole reason for this change ────────────────────────────────
    r_old = await http("GET", "/availability/self-service")
    check("the BetterSelect screen's route still answers 402 for a club without BetterSelect", r_old.status_code, 402)
    r_new = await http("GET", "/player-dashboard/settings")
    check("a club without BetterSelect reads the Player Dashboard settings", r_new.status_code, 200)
    body = r_new.json() if r_new.status_code == 200 else {}
    check("an untouched club without BetterSelect reads as ON", body.get("enabled"), True)
    check("the payload carries the link, PIN, site button and module list",
          (body.get("path"), body.get("require_pin"), body.get("show_on_site"), isinstance(body.get("dashboard_modules"), list)),
          (f"/playerdash/{tok['plain']}", True, True, True))
    check("has_select is false for it", body.get("has_select"), False)
    check("every Select-only module is listed but blocked for it, cards and season are not",
          sorted(m["key"] for m in body.get("dashboard_modules") or [] if m.get("blocked") and "BetterSelect" in m["blocked"]),
          ["fines", "ladder", "selected", "squad", "training"])

    acting["who"] = "member"
    r_member = await http("POST", "/player-dashboard/settings", json={"enabled": False})
    check("a person without MANAGE_SETTINGS is refused", r_member.status_code, 403)
    check("and nothing changed", await opens("plain"), True)
    acting["who"] = "admin"

    # ── a club without BetterSelect ────────────────────────────────────────────────
    check("an untouched club's link opens (no existing link breaks)", await opens("plain"), True)
    check("its club site button is shown", await button("plain"), f"/playerdash/{tok['plain']}")
    check("the availability answers are still refused without BetterSelect", await opens("plain", need_select=True), False)

    r = await http("POST", "/player-dashboard/settings", json={"enabled": False})
    check("Off is accepted", r.status_code, 200)
    check("Off closes the link", await opens("plain"), False)
    check("Off takes the button off the club site", await button("plain"), None)
    check("the payload says off", (r.json() if r.status_code == 200 else {}).get("enabled"), False)
    check("it is the club's own column that changed, not the BetterSelect one",
          ((await org("plain")).availability_self_service_enabled, getattr(await org("plain"), "player_dashboard_enabled", "missing")), (False, False))

    r = await http("POST", "/player-dashboard/settings", json={"enabled": True})
    check("On reopens the link with the same token", (await opens("plain"), (r.json() if r.status_code == 200 else {}).get("token")), (True, tok["plain"]))
    check("On shows the button again", await button("plain"), f"/playerdash/{tok['plain']}")

    r = await http("POST", "/player-dashboard/settings", json={"show_on_site": False})
    check("hiding the button leaves the link working", (await opens("plain"), await button("plain")), (True, None))
    check("and the payload says hidden but on", ((r.json() if r.status_code == 200 else {}).get("show_on_site"), (r.json() if r.status_code == 200 else {}).get("enabled")), (False, True))
    await http("POST", "/player-dashboard/settings", json={"show_on_site": True})

    # An absent key is not a clear.
    await http("POST", "/player-dashboard/settings", json={"require_pin": False})
    await http("POST", "/player-dashboard/settings", json={"enabled": True})
    o = await org("plain")
    check("a body that does not send the PIN leaves it as it was", o.availability_require_pin, False)
    await http("POST", "/player-dashboard/settings", json={"require_pin": True})

    # Modules: a real choice, an empty list is not "not sent".
    r = await http("POST", "/player-dashboard/settings", json={"dashboard_modules": ["season", "cards", "nonsense", "season"]})
    on = [m["key"] for m in (r.json() if r.status_code == 200 else {}).get("dashboard_modules", []) if m.get("enabled")]
    check("modules save in the order given, once each, unknown keys dropped", on, ["season", "cards"])
    await http("POST", "/player-dashboard/settings", json={"enabled": True})
    check("a body without modules leaves the choice alone",
          [m["key"] for m in (await http("GET", "/player-dashboard/settings")).json().get("dashboard_modules", []) if m.get("enabled")], ["season", "cards"])
    r = await http("POST", "/player-dashboard/settings", json={"dashboard_modules": []})
    check("an empty list switches every module off", [m for m in (r.json() if r.status_code == 200 else {}).get("dashboard_modules", []) if m.get("enabled")], [])

    # ── legacy: a club that had hidden the page before this switch existed ─────────
    check("a club without BetterSelect that had hidden the page stays closed", await opens("hidden"), False)
    async with Session() as db:
        club = await db.get(Organisation, ids["hidden"])
        if pdash and hasattr(pdash, "link_live"):
            check("link_live reads that club as off", pdash.link_live(club), False)
        else:
            check("link_live exists", False)
        if pda is not None:
            payload = await pda._payload(db, club)
            check("its settings screen says Off, hidden", (payload["enabled"], payload["show_on_site"]), (False, False))
            await pda.update_settings(pda.SettingsBody(enabled=True), db, club, None)
        else:
            check("the settings route exists", False)
    check("switching it on opens the link", await opens("hidden"), True)
    check("but the button stays hidden, as the club chose", await button("hidden"), None)

    # ── a club WITH BetterSelect: two switches, one for each side of the link ───────
    async def served(n):
        return pdash.served_modules(await org(n)) if pdash else []

    async def has_availability(n):
        async with Session() as db:
            try:
                return (await pa.get_landing(tok[n], db))["has_availability"]
            except HTTPException:
                return "link closed"

    check("BetterSelect club, nothing chosen, self-service off: link closed", await opens("sel_off"), False)
    async with Session() as db:
        club = await db.get(Organisation, ids["sel_off"])
        if pda is not None:
            payload = await pda._payload(db, club)
            check("its dashboard settings read Off, with BetterSelect and availability off",
                  (payload["enabled"], payload["has_select"], payload.get("availability_enabled")), (False, True, False))
            await pda.update_settings(pda.SettingsBody(enabled=True), db, club, None)
        else:
            check("the settings route exists", False)
    o = await org("sel_off")
    check("turning the dashboard on from BetterStats writes its own column", getattr(o, "player_dashboard_enabled", "missing"), True)
    check("and does not touch the BetterSelect availability switch", o.availability_self_service_enabled, False)
    check("the link opens for the dashboard", await opens("sel_off"), True)
    check("the availability side stays closed: answers and votes are refused", await opens("sel_off", need_select=True), False)
    check("the landing says there is no availability", await has_availability("sel_off"), False)
    check("Player Cards are open to it", await opens("sel_off", need_dashboard=True), True)
    sv = await served("sel_off")
    check("the page serves the dashboard modules and none of BetterSelect's", ("cards" in sv, "squad" in sv, "votes" in sv), (True, False, False))
    check("the club site button follows the dashboard", await button("sel_off"), f"/playerdash/{tok['sel_off']}")
    async with Session() as db:
        blocked = {m["key"]: m["blocked"] for m in pdash.catalogue_for(await db.get(Organisation, ids["sel_off"]))} if pdash else {}
    check("the module list says squad needs the availability link turned on", "availability link" in (blocked.get("squad") or ""), True)

    check("BetterSelect club, self-service on and dashboard never chosen: the dashboard follows it", (await opens("sel_on", need_dashboard=True), await opens("sel_on", need_select=True)), (True, True))
    async with Session() as db:
        club = await db.get(Organisation, ids["sel_on"])
        if pda is not None:
            await pda.update_settings(pda.SettingsBody(enabled=False), db, club, None)
    o = await org("sel_on")
    check("dashboard Off from BetterStats writes its own column", (getattr(o, "player_dashboard_enabled", "missing"), o.availability_self_service_enabled), (False, True))
    check("availability and votes keep their link", (await opens("sel_on", need_select=True), await has_availability("sel_on")), (True, True))
    check("Player Cards are closed", await opens("sel_on", need_dashboard=True), False)
    sv = await served("sel_on")
    check("the page serves BetterSelect's modules and none of the dashboard's", ("cards" in sv, "squad" in sv, "votes" in sv), (False, True, True))
    check("the club site button is gone", await button("sel_on"), None)
    async with Session() as db:
        club = await db.get(Organisation, ids["sel_on"])
        club.availability_self_service_enabled = False
        await db.commit()
    check("both sides off: the link closes", await opens("sel_on"), False)

    # ── the link ───────────────────────────────────────────────────────────────────
    r = await http("POST", "/player-dashboard/regenerate")
    new = (r.json() if r.status_code == 200 else {}).get("token")
    check("regenerate gives a new token", bool(new) and new != tok["plain"], True)
    check("the old link stops working at once", await opens("plain", token=tok["plain"]), False)
    check("the new link works", await opens("plain", token=new), True)

    async with Session() as db:
        club = await db.get(Organisation, ids["other"])
        club.availability_link_token = None
        await db.commit()
    async with Session() as db:
        club = await db.get(Organisation, ids["other"])
        if pdash and hasattr(pdash, "set_dashboard_live"):
            pdash.set_dashboard_live(club, True)
            await db.commit()
    o = await org("other")
    check("turning it on for a club with no link mints one", bool(o.availability_link_token), True)
    check("another club was never touched by any of this", ((await org("other")).availability_self_service_enabled, (await org("sel_on")).availability_require_pin), (False, True))

    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    await engine.dispose()
    sys.exit(1 if base.FAIL else 0)


asyncio.run(main())
