"""Verification: a club's own Player Dashboard modules (links, announcements, events, image banners)
and the order of the dashboard's cards.

Asked for: "allow clubs to add their own Custom Modules ... like a LinkTree section where you add your
own custom links", each one its own card on the grid, with the club arranging the cards, optional show
from / show until dates, and a simple click count.

Real HTTP through the mounted app, for the admin routes (`/player-dashboard/*`), the player's page
(`/public/availability/{token}/me/profile`), the click route and the image route.

What it pins:
  * a link opens http(s) only: `javascript:` and `data:` are refused, a bare domain gets https://
  * each kind refuses what could never show (a link without an address, an announcement without text,
    an event without a date) and Show until before Show from
  * PATCH changes only what is sent; an explicit null clears
  * a person without MANAGE_SETTINGS is refused, and another club cannot touch our module
  * the player's page carries only what shows today: switched off, not yet started, past dates, a past
    event, and an image banner without its image are all left out; an uploaded image is served
  * the grid's order: saved, cleaned of unknown ids, followed by the page; a new module joins the end,
    a removed one leaves the order
  * the dashboard switched off takes the club's own cards with it
  * a tap adds one to the count the club sees, records nobody, and only for this club's link cards

CONTROL MODE: against the previous commit the routes and the table do not exist. Every read is
presence-safe, so the control FAILS the checks instead of crashing.

Run on its own database (rule 24):
  DATABASE_URL=postgresql+asyncpg://... python verification/verify_player_dashboard_custom_modules.py
"""
from __future__ import annotations

import asyncio
import importlib
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import verify_selection_same_day as base
from app.models.db import ClubMembership, Organisation, Player, User

engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)
check = base.check

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)


def guarded(name):
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


def js(r):
    try:
        return r.json()
    except Exception:
        return {}


async def main():
    await base.build_schema()
    async with engine.begin() as conn:
        for mod in ("availability_maybe_ddl", "availability_site_link_ddl", "player_dashboard_ddl",
                    "player_registration_ddl", "player_dashboard_custom_ddl"):
            m = guarded(f"app.services.{mod}")
            for name in ("STATEMENTS", "STATEMENTS_398", "STATEMENTS_399"):
                for stmt in (getattr(m, name, None) or []) if m else []:
                    await conn.execute(text(stmt))

    import httpx
    from jose import jwt as jose_jwt
    import app.routers.public_availability as pa
    from app.config.settings import settings
    from app.main import app
    from app.routers.auth import get_current_user

    ids = {n: uuid.uuid4() for n in ("club", "other", "admin", "member", "other_admin", "sam", "olly")}
    tok = {n: "t-" + uuid.uuid4().hex for n in ("club", "other")}

    async with Session() as db:
        for n in ("club", "other"):
            db.add(Organisation(id=ids[n], name=f"{n} CC", is_active=True, slug=f"{n}-{ids[n].hex[:8]}",
                                availability_link_token=tok[n], module_overrides=[], player_dashboard_enabled=True))
        await db.flush()
        for who in ("admin", "member", "other_admin"):
            db.add(User(id=ids[who], username=f"{who}-{ids[who].hex[:6]}", email=f"{who}@x.test", password_hash="x", display_name=who))
        db.add(Player(id=ids["sam"], organisation_id=ids["club"], name="Sam Smith", phone="0400111222", status="active", is_player=True))
        db.add(Player(id=ids["olly"], organisation_id=ids["other"], name="Olly Other", phone="0400333444", status="active", is_player=True))
        await db.flush()
        db.add(ClubMembership(club_id=ids["club"], user_id=ids["admin"], role="club_admin", capabilities=[]))
        db.add(ClubMembership(club_id=ids["club"], user_id=ids["member"], role="club_member", capabilities=[]))
        db.add(ClubMembership(club_id=ids["other"], user_id=ids["other_admin"], role="club_admin", capabilities=[]))
        await db.commit()

    acting = {"who": "admin"}

    async def current_user():
        async with Session() as db:
            return await db.get(User, ids[acting["who"]])

    app.dependency_overrides[get_current_user] = current_user
    transport = httpx.ASGITransport(app=app)

    def club_header(who):
        return {"X-Club-Id": str(ids["other"] if who == "other_admin" else ids["club"])}

    async def http(method, path, who=None, **kw):
        acting["who"] = who or "admin"
        headers = {**club_header(acting["who"]), **kw.pop("headers", {})}
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            return await c.request(method, path, headers=headers, **kw)

    def cookie(club, pid):
        c = jose_jwt.encode({"club": str(ids[club]), "pid": str(ids[pid]), "typ": "avail",
                             "exp": datetime.now(timezone.utc) + timedelta(days=1)},
                            settings.secret_key, algorithm=settings.algorithm)
        return {pa.COOKIE_NAME: c}

    async def public(method, path, club="club", pid="sam"):
        async with httpx.AsyncClient(transport=transport, base_url="http://t", cookies=cookie(club, pid)) as c:
            return await c.request(method, f"/public/availability/{tok[club]}{path}")

    async def profile():
        return js(await public("GET", "/me/profile"))

    def titles(p):
        return sorted(m.get("title") for m in (p.get("custom_modules") or []))

    today = date.today()
    D = lambda n: (today + timedelta(days=n)).isoformat()  # noqa: E731

    # ── the settings payload and the gate ────────────────────────────────────────
    r = await http("GET", "/player-dashboard/settings")
    body = js(r)
    check("the settings carry the club's own modules (none yet) and the kinds on offer",
          (body.get("custom_modules"), [k.get("key") for k in body.get("custom_kinds") or []]),
          ([], ["link", "text", "event", "image"]))
    check("the settings carry the grid's order, the built-in cards in their standard order",
          [x.get("id") for x in body.get("layout") or []],
          ["availability", "selection", "cards", "fantasy", "stats", "voting", "admin"])

    r = await http("POST", "/player-dashboard/custom-modules", who="member", json={"kind": "link", "title": "Tickets", "url": "https://x.com"})
    check("a person without MANAGE_SETTINGS cannot add one", r.status_code, 403)

    # ── what can be saved ─────────────────────────────────────────────────────────
    for bad, why in (("javascript:alert(1)", "javascript:"), ("data:text/html,hi", "data:"), ("ftp://x.com/a", "ftp"), ("not a link", "spaces")):
        r = await http("POST", "/player-dashboard/custom-modules", json={"kind": "link", "title": "Bad", "url": bad})
        check(f"a {why} link is refused", r.status_code, 422)
    r = await http("POST", "/player-dashboard/custom-modules", json={"kind": "link", "title": "No address"})
    check("a link button without an address is refused", r.status_code, 422)
    r = await http("POST", "/player-dashboard/custom-modules", json={"kind": "text", "title": "No text"})
    check("an announcement without text is refused", r.status_code, 422)
    r = await http("POST", "/player-dashboard/custom-modules", json={"kind": "event", "title": "No date"})
    check("an event without a date is refused", r.status_code, 422)
    r = await http("POST", "/player-dashboard/custom-modules", json={"kind": "link", "title": "Backwards", "url": "x.com", "show_from": D(5), "show_until": D(1)})
    check("Show until before Show from is refused", r.status_code, 422)
    r = await http("POST", "/player-dashboard/custom-modules", json={"kind": "link", "title": "   ", "url": "x.com"})
    check("a blank title is refused", r.status_code, 422)
    r = await http("POST", "/player-dashboard/custom-modules", json={"kind": "poll", "title": "Poll"})
    check("an unknown kind is refused", r.status_code, 422)

    async def add(**kw):
        r = await http("POST", "/player-dashboard/custom-modules", json=kw)
        return r, js(r).get("created_id")

    r, merch = await add(kind="link", title="Club merch", url="shop.club.com.au/store", emoji="👕", body="Hoodies are in", button_label="Shop now")
    check("a link button is added", r.status_code, 200)
    mods = {m.get("id"): m for m in js(r).get("custom_modules") or []}
    check("a bare domain is saved with https:// in front", (mods.get(merch) or {}).get("url"), "https://shop.club.com.au/store")
    _, notice = await add(kind="text", title="Presentation night dress code", body="Smart casual, 14 March.")
    _, event = await add(kind="event", title="Presentation night", event_date=D(12), event_time="19:00", location="Clubrooms", url="https://tix.example.com/pn")
    _, past_event = await add(kind="event", title="Last year's dinner", event_date=D(-1))
    _, later = await add(kind="link", title="Next season rego", url="https://rego.example.com", show_from=D(3))
    _, expired = await add(kind="link", title="Old raffle", url="https://raffle.example.com", show_until=D(-1))
    _, off = await add(kind="link", title="Draft link", url="https://draft.example.com", enabled=False)
    _, banner = await add(kind="image", title="Merch poster", url="https://shop.club.com.au")

    s = js(await http("GET", "/player-dashboard/settings"))
    reasons = {m.get("title"): m.get("hidden_reason") for m in s.get("custom_modules") or []}
    check("the settings say why each hidden one is not showing",
          (reasons.get("Club merch"), reasons.get("Last year's dinner"), (reasons.get("Next season rego") or "")[:10],
           reasons.get("Old raffle"), reasons.get("Draft link"), reasons.get("Merch poster")),
          (None, "The event has been.", "Shows from", "Its dates have passed.", "Switched off.", "Add an image first."))

    # ── the player's page ─────────────────────────────────────────────────────────
    p = await profile()
    check("the player's page carries only what shows today",
          titles(p), sorted(["Club merch", "Presentation night dress code", "Presentation night"]))
    ev = next((m for m in p.get("custom_modules") or [] if m.get("id") == event), {})
    check("an event carries its date, time, place and ticket link",
          (ev.get("event_date"), ev.get("event_time"), ev.get("location"), ev.get("url")), (D(12), "19:00", "Clubrooms", "https://tix.example.com/pn"))
    check("the page gets no counts or dates the club keeps to itself",
          any(k in m for m in p.get("custom_modules") or [] for k in ("click_count", "show_from", "show_until", "enabled")), False)
    check("an event shows on the day itself", (await add(kind="event", title="Today's BBQ", event_date=D(0)))[0].status_code, 200)
    check("and is on the page", "Today's BBQ" in titles(await profile()), True)

    # The image banner shows once it has its image.
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        acting["who"] = "admin"
        r = await c.post(f"/player-dashboard/custom-modules/{banner}/image", headers=club_header("admin"),
                         files={"file": ("poster.exe", b"MZ", "application/octet-stream")})
        check("a file that is not an image is refused", r.status_code, 422)
        r = await c.post(f"/player-dashboard/custom-modules/{banner}/image", headers=club_header("admin"),
                         files={"file": ("poster.png", PNG, "image/png")})
    check("an image is uploaded", r.status_code, 200)
    p = await profile()
    img = next((m.get("image_url") for m in p.get("custom_modules") or [] if m.get("id") == banner), None)
    check("the image banner is on the page once it has its image", bool(img and img.startswith(f"/api/images/player-dashboard-modules/{banner}?v=")), True)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get((img or "/api/images/none").removeprefix("/api"))
    check("the image route serves the bytes", (r.status_code, r.content == PNG, r.headers.get("content-type")), (200, True, "image/png"))

    # ── PATCH: only what is sent ──────────────────────────────────────────────────
    r = await http("PATCH", f"/player-dashboard/custom-modules/{merch}", json={"title": "Club store"})
    m = next((x for x in js(r).get("custom_modules") or [] if x.get("id") == merch), {})
    check("a PATCH with only the title leaves the rest alone", (m.get("title"), m.get("url"), m.get("emoji"), m.get("body")),
          ("Club store", "https://shop.club.com.au/store", "👕", "Hoodies are in"))
    r = await http("PATCH", f"/player-dashboard/custom-modules/{merch}", json={"emoji": None, "body": ""})
    m = next((x for x in js(r).get("custom_modules") or [] if x.get("id") == merch), {})
    check("an explicit null or empty clears", (m.get("emoji"), m.get("body"), m.get("title")), (None, None, "Club store"))
    r = await http("PATCH", f"/player-dashboard/custom-modules/{merch}", json={"url": "javascript:alert(1)"})
    check("a PATCH cannot swap the address for script", r.status_code, 422)
    r = await http("PATCH", f"/player-dashboard/custom-modules/{merch}", json={"url": None})
    check("a PATCH cannot leave a link button without its address", r.status_code, 422)
    r = await http("PATCH", f"/player-dashboard/custom-modules/{off}", json={"enabled": True})
    check("switching one on puts it on the page", "Draft link" in titles(await profile()), True)

    # ── another club ──────────────────────────────────────────────────────────────
    r = await http("PATCH", f"/player-dashboard/custom-modules/{merch}", who="other_admin", json={"title": "Hijacked"})
    check("another club's admin cannot edit our module", r.status_code, 404)
    r = await http("DELETE", f"/player-dashboard/custom-modules/{merch}", who="other_admin")
    check("or remove it", r.status_code, 404)
    check("and it is still ours, unchanged", "Club store" in titles(await profile()), True)
    other_p = js(await public("GET", "/me/profile", club="other", pid="olly"))
    check("another club's players see none of our cards", other_p.get("custom_modules"), [])

    # ── the grid's order ──────────────────────────────────────────────────────────
    order = [f"custom:{merch}", "cards", f"custom:{event}", "stats", "nonsense", "cards", "availability",
             "selection", "fantasy", "voting", "admin", f"custom:{notice}", f"custom:{banner}"]
    r = await http("POST", "/player-dashboard/settings", json={"layout": order})
    saved = [x.get("id") for x in js(r).get("layout") or []]
    check("the order saves as given, unknown ids and repeats dropped",
          saved[:11], [f"custom:{merch}", "cards", f"custom:{event}", "stats", "availability", "selection", "fantasy", "voting", "admin", f"custom:{notice}", f"custom:{banner}"])
    check("a module left out of the list keeps a place after the rest", set(saved[11:]) >= {f"custom:{past_event}", f"custom:{later}"}, True)
    p = await profile()
    lay = p.get("layout") or []
    check("the player's page follows the club's order", lay[:4], [f"custom:{merch}", "cards", f"custom:{event}", "stats"])
    check("the page's order holds no card it does not show", any(x in lay for x in (f"custom:{past_event}", f"custom:{later}", f"custom:{expired}")), False)

    r = await http("POST", "/player-dashboard/settings", json={"require_pin": True})
    check("a settings save without the order leaves it alone", [x.get("id") for x in js(r).get("layout") or []][:2], [f"custom:{merch}", "cards"])

    _, raffle = await add(kind="link", title="Meat tray raffle", url="https://raffle2.example.com")
    async with Session() as db:
        stored = (await db.get(Organisation, ids["club"])).player_dashboard_layout if hasattr(Organisation, "player_dashboard_layout") else None
    check("a new module joins the end of an arranged order", (stored or [None])[-1], f"custom:{raffle}")
    r = await http("DELETE", f"/player-dashboard/custom-modules/{raffle}")
    check("a module is removed", (r.status_code, "Meat tray raffle" in titles(await profile())), (200, False))
    async with Session() as db:
        stored = (await db.get(Organisation, ids["club"])).player_dashboard_layout if hasattr(Organisation, "player_dashboard_layout") else "missing"
    check("and leaves the stored order", isinstance(stored, list) and f"custom:{raffle}" not in stored and f"custom:{merch}" in stored, True)

    # ── taps ──────────────────────────────────────────────────────────────────────
    r1 = await public("POST", f"/me/custom/{merch}/click")
    r2 = await public("POST", f"/me/custom/{merch}/click")
    check("a tap is counted", (r1.status_code, js(r1).get("counted"), js(r2).get("counted")), (200, True, True))
    s = js(await http("GET", "/player-dashboard/settings"))
    m = next((x for x in s.get("custom_modules") or [] if x.get("id") == merch), {})
    check("the club sees the count beside the module", (m.get("click_count"), bool(m.get("last_clicked_at"))), (2, True))
    r = await public("POST", f"/me/custom/{notice}/click")
    check("an announcement with no link counts nothing", js(r).get("counted"), False)
    r = await public("POST", f"/me/custom/{merch}/click", club="other", pid="olly")
    check("another club's player cannot add to our count", js(r).get("counted"), False)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post(f"/public/availability/{tok['club']}/me/custom/{merch}/click")
    check("a tap without the player's cookie is refused", r.status_code, 401)
    for _ in range(5):
        r = await public("POST", f"/me/custom/{merch}/click")
    check("one player tapping over and over is rate limited", r.status_code, 429)
    async with engine.connect() as conn:
        cols = [c for (c,) in (await conn.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'player_dashboard_custom_modules'"))).all()]
    check("nothing about who tapped is stored", any("player" in c for c in cols), False)

    # ── how players pay their fees ────────────────────────────────────────────────
    pay = {"payid": "treasurer@club.com.au", "account_name": "Club CC", "bsb": "062-000", "account_number": "1234 5678",
           "reference_hint": "Your surname", "pay_online_url": "club.teamapp.com/pay", "pay_online_label": "Pay on TeamApp",
           "other_instructions": "Cash at the bar on Saturdays.", "bogus": "x", "payid_name": "  "}
    r = await http("POST", "/player-dashboard/settings", json={"fees_payment": pay})
    fp = js(r).get("fees_payment") or {}
    check("fee payment details save, blanks and unknown keys dropped, the link gets https://",
          (r.status_code, sorted(fp), fp.get("pay_online_url")),
          (200, sorted(["payid", "account_name", "bsb", "account_number", "reference_hint", "pay_online_url", "pay_online_label", "other_instructions"]),
           "https://club.teamapp.com/pay"))
    r = await http("POST", "/player-dashboard/settings", json={"fees_payment": {"pay_online_url": "javascript:alert(1)"}})
    check("a pay-online link that is not a web address is refused", r.status_code, 422)
    r = await http("POST", "/player-dashboard/settings", json={"require_pin": True})
    check("a settings save without the payment details leaves them alone", (js(r).get("fees_payment") or {}).get("bsb"), "062-000")
    pdmod = guarded("app.services.player_dashboard")
    async with Session() as db:
        club = await db.get(Organisation, ids["club"])
        sam = await db.get(Player, ids["sam"])
        try:
            owing = await pdmod.fees_owing(db, club, sam)
        except Exception as e:  # noqa: BLE001
            owing = {"error": repr(e)}
    check("the player's fees carry how to pay, even with no fee record yet",
          ((owing.get("how_to_pay") or {}).get("payid"), (owing.get("how_to_pay") or {}).get("other_instructions")),
          ("treasurer@club.com.au", "Cash at the bar on Saturdays."))
    r = await http("POST", "/player-dashboard/settings", json={"fees_payment": {}})
    check("an empty set clears them", (r.status_code, js(r).get("fees_payment")), (200, {}))

    # ── the dashboard switched off ────────────────────────────────────────────────
    await http("POST", "/player-dashboard/settings", json={"enabled": False})
    async with Session() as db:
        club = await db.get(Organisation, ids["club"])
        fp = guarded("app.services.player_dashboard_custom")
        got = (await fp.for_player(db, club, today))[0] if fp else "missing"
    check("with the dashboard off, the club's own cards are not served", got, [])
    await http("POST", "/player-dashboard/settings", json={"enabled": True})

    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    for f in base.FAILURES:
        print("  -", f)
    await engine.dispose()
    sys.exit(1 if base.FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
