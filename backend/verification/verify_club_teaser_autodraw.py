"""Drawing every club's pictures in advance, and finding a club's page from /trial.

Covers: the public lookup /trial uses once a visitor picks a club; only clubs the
crawl has finished with (current schema) being drawn; a bounded amount of
Chromium at once; the always-on drawer (off until switched on, skips a club that
just failed, survives a cycle that raises, carries on from the database after a
restart); and the on/off setting and the numbers the panel reads.

Runs the SHIPPED services and route bodies against a real Postgres, with a
scripted stand-in for Chromium.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \
  python verification/verify_club_teaser_autodraw.py
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")
TMP = tempfile.mkdtemp(prefix="autodraw-")
os.environ["TEASER_IMAGE_DIR"] = TMP
os.environ["PUBLIC_BASE_URL"] = "https://site.test"

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import Base

MISSING: list[str] = []
try:
    from fastapi import HTTPException
    from starlette.requests import Request
    from app.services import club_teaser, club_teaser_images as ti
    from app.services import platform_settings as ps
    from app.services.club_teaser_ddl import STATEMENTS
    from app.routers import public_teaser as pt, marketing, club_admin
    for name in ("run_forever", "AUTO_BATCH", "PAGES_AT_ONCE", "CLUBS_AT_ONCE"):
        if not hasattr(ti, name):
            MISSING.append(f"club_teaser_images.{name} is missing")
    if not hasattr(pt, "teaser_for_club"):
        MISSING.append("public_teaser.teaser_for_club is missing")
    if not hasattr(ps, "get_club_teaser_auto_draw"):
        MISSING.append("platform_settings.get_club_teaser_auto_draw is missing")
except ImportError as exc:  # pragma: no cover - control run only
    ti = None
    MISSING.append(str(exc))

DB = os.environ["DATABASE_URL"]
if "verify" not in (make_url(DB).database or "").lower():
    print("REFUSING to run: not a verification database. These checks delete and drop tables.")
    sys.exit(2)
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)
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
        print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")


def g() -> str:
    return str(uuid.uuid4())


def png(w: int, h: int) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (10, 20, 30)).save(buf, "PNG")
    return buf.getvalue()


class Stub:
    """Stands in for Chromium. Tracks how many pictures are being taken at once."""

    def __init__(self, fail=(), hold=0.0):
        self.fail, self.hold, self.active, self.peak, self.shots = set(fail), hold, 0, 0, []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def shoot(self, url, width, height):
        token = url.split("/preview/")[1].split("/")[0]
        self.shots.append(token)
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(self.hold)
            if token in self.fail:
                raise RuntimeError("the card content does not fit its frame")
            return png(width, height)
        finally:
            self.active -= 1


def req(ip="10.1.1.1"):
    return Request({"type": "http", "method": "GET", "path": "/", "headers": [(b"x-forwarded-for", ip.encode())], "client": (ip, 1)})


async def main() -> None:
    if MISSING:
        check("the autodraw backend is present", False, "; ".join(MISSING))
        print(f"\n{PASS} passed, {FAIL} failed")
        sys.exit(1)

    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
        for s in STATEMENTS:
            await c.execute(text(s))
        await c.execute(text("CREATE TABLE IF NOT EXISTS platform_settings (id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1), "
                             "settings JSONB NOT NULL DEFAULT '{}', updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"))
        await c.execute(text("INSERT INTO platform_settings (id, settings) VALUES (1, '{}') ON CONFLICT (id) DO UPDATE SET settings = '{}'"))
        await c.execute(text("DELETE FROM club_teaser_snapshots"))
        await c.execute(text("DELETE FROM marketing_clubs"))
        await c.execute(text("DELETE FROM organisations WHERE slug = 'adr-customer'"))

    cust = g()
    K: dict[str, dict] = {}
    async with Session() as s:
        await s.execute(text("INSERT INTO organisations (id, name, slug, is_active) VALUES (CAST(:i AS uuid), 'Cust', 'adr-customer', true)"), {"i": cust})
        cur = club_teaser.SCHEMA_VERSION

        async def club(key, name, *, schema=None, status="ok", registered=False, ca=None, guid=None, version=1, image_version=None):
            schema = cur if schema is None else schema
            cid, tok = g(), "tk" + uuid.uuid4().hex[:14]
            guid = guid or g()
            ca = ca or g()
            await s.execute(text("""INSERT INTO marketing_clubs (id, grassroots_guid, name, kind, excluded, not_interested, trial_modules,
                status, source, existing_org_id) VALUES (CAST(:id AS uuid), :g, :n, 'club', false, false, '[]'::jsonb, 'new',
                'grassroots_api', CAST(:org AS uuid))"""), {"id": cid, "g": guid, "n": name, "org": cust if registered else None})
            body = {"schema": schema, "club": {"name": name, "ca_org_id": ca}, "season": {"name": "S"}} if status == "ok" else None
            await s.execute(text("""INSERT INTO club_teaser_snapshots (marketing_club_id, org_guid, token, status, snapshot, version, image_version)
                VALUES (CAST(:id AS uuid), :g, :t, :st, CAST(:sn AS jsonb), :v, :iv)"""),
                {"id": cid, "g": guid, "t": tok, "st": status, "sn": json.dumps(body) if body else None, "v": version, "iv": image_version})
            K[key] = {"id": cid, "token": tok, "name": name, "ca": ca, "guid": guid}

        for i in range(6):
            await club(f"cur{i}", f"Current {i} CC")
        await club("old1", "Old Schema One CC", schema=1)
        await club("old2", "Old Schema Two CC", schema=1)
        await club("none", "No Schema CC", schema=0)
        await club("drawn", "Already Drawn CC", image_version=1)
        await club("cust", "Customer CC", registered=True)
        await club("junior", "Junior CC", status="junior_only")
        await s.commit()

    # --------------------------------------------------- the /trial lookup
    print("the lookup /trial makes once a club is picked")

    async def by_club(ids, ip="10.2.2.2"):
        async with Session() as s2:
            return await pt.teaser_for_club(req(ip), ids, s2)
    r1 = await by_club([K["cur0"]["ca"], g()])
    r2 = await by_club([K["cur1"]["guid"]])
    check("the Cricket Australia id the picker gives finds the club's page", r1 == {"found": True, "token": K["cur0"]["token"]}, str(r1))
    check("PlayHQ's own id (the directory guid) finds it too", r2 == {"found": True, "token": K["cur1"]["token"]}, str(r2))
    r3 = await by_club([g(), K["cur3"]["guid"], K["cur3"]["ca"]])
    check("the matching id can be any of those sent, not just the first (the picker's own id order is not ours to rely on)",
          r3 == {"found": True, "token": K["cur3"]["token"]}, str(r3))
    check("a club a visitor may have picked on an old snapshot is still found (the page works at any schema)",
          (await by_club([K["old1"]["ca"]])).get("found") is True)
    nf = [await by_club(x) for x in ([], [g()], ["not-an-id!"], ["' OR 1=1 --"], [K["cust"]["ca"]], [K["junior"]["guid"]])]
    check("no ids, an unknown id, junk, a customer and a junior-only club are not found",
          all(x == {"found": False} for x in nf), str(nf))
    check("the answer carries only the token (no player or figure is exposed by the search)", set(r1) == {"found", "token"})
    codes = []
    for _ in range(pt.READ_LIMIT + 3):
        try:
            await by_club([K["cur0"]["ca"]], ip="10.3.3.3")
            codes.append(200)
        except HTTPException as e:
            codes.append(e.status_code)
    check("it is rate limited per address like the page (120 an hour)", codes[:pt.READ_LIMIT] == [200] * pt.READ_LIMIT and codes[pt.READ_LIMIT:] == [429] * 3)

    # ---------------------------------------- only settled clubs are drawn
    print("which clubs are drawn")
    async with Session() as s:
        due = await ti.due_clubs(s, 100)
        prog = await ti.images_progress(s)
        named = await ti.due_clubs(s, 100, club_id=K["old1"]["id"])
        skipped = await ti.due_clubs(s, 100, skip=[K["cur0"]["token"], K["cur1"]["token"]])
    names = {d["name"] for d in due}
    check("clubs the crawl has finished with (current schema) and not yet drawn are due",
          {f"Current {i} CC" for i in range(6)} <= names)
    check("clubs still on an older schema are NOT drawn (the crawl is about to replace them)",
          not ({"Old Schema One CC", "Old Schema Two CC", "No Schema CC"} & names), str(names))
    check("a drawn club, a customer and a junior-only club are not due", not ({"Already Drawn CC", "Customer CC", "Junior CC"} & names))
    check("naming an old-schema club on purpose still draws it (the operator asked)", [d["name"] for d in named] == ["Old Schema One CC"])
    check("tokens in the skip set are left out", {d["name"] for d in skipped} == names - {"Current 0 CC", "Current 1 CC"})
    check("the panel's numbers agree: 6 to draw, 3 waiting on the crawl, 1 drawn",
          prog["pending"] == 6 and prog["waiting"] == 3 and prog["ready"] == 1 and prog["pending"] == len(due), str(prog))

    # --------------------------------------------- a bounded amount at once
    print("how much runs at once")
    r = ti.ChromiumRenderer(executable_path="/nonexistent")
    state = {"active": 0, "peak": 0}

    async def fake(url, w, h):
        state["active"] += 1
        state["peak"] = max(state["peak"], state["active"])
        await asyncio.sleep(0.05)
        state["active"] -= 1
        return b"x"
    r._shoot = fake
    await asyncio.gather(*(r.shoot(f"u{i}", 1, 1) for i in range(20)))
    check("however many pictures are asked for, no more than PAGES_AT_ONCE pages are open together",
          2 <= state["peak"] <= ti.PAGES_AT_ONCE, str(state))
    stub = Stub(hold=0.05)
    sizes = await ti.render_club(stub, K["cur0"]["token"], base="http://x")
    check("one club's three formats are taken at the same time, not one after another", stub.peak == 3 and len(sizes) == 3, str(stub.peak))
    stub = Stub(hold=0.05)
    out = await ti.render_pending(Session, limit=6, renderer_factory=lambda: stub)
    check("a batch draws several clubs at once, but only CLUBS_AT_ONCE of them",
          out["drawn"] == 6 and 3 < stub.peak <= ti.CLUBS_AT_ONCE * 3, f"{out['drawn']} drawn, peak {stub.peak}")
    check("every club got its three files", all(ti.image_path(K[f"cur{i}"]["token"], f).is_file() for i in range(6) for f in ti.FORMATS))
    async with Session() as s:
        iv = (await s.execute(text("SELECT count(*) FROM club_teaser_snapshots WHERE image_version = version"))).scalar()
    check("and each is marked drawn at its version", iv == 7, str(iv))   # 6 + the one already drawn

    # ------------------------------------------------- the always-on drawer
    print("the always-on drawer")
    async with engine.begin() as c:
        await c.execute(text("UPDATE club_teaser_snapshots SET image_version = NULL WHERE token = ANY(:t)"),
                        {"t": [K[f"cur{i}"]["token"] for i in range(6)]})
    sleeps: list = []

    async def fake_sleep(n):
        sleeps.append(n)

    stub = Stub()
    flag = {"on": False}

    async def enabled():
        return flag["on"]
    await ti.run_forever(session_maker=Session, enabled_fn=enabled, renderer_factory=lambda: stub,
                         sleep=fake_sleep, max_cycles=2)
    check("switched off, it draws nothing and just waits", stub.shots == [] and sleeps == [60, 60], f"{stub.shots} {sleeps}")

    flag["on"] = True
    sleeps.clear()
    stub = Stub(fail={K["cur2"]["token"]})
    await ti.run_forever(session_maker=Session, enabled_fn=enabled, renderer_factory=lambda: stub,
                         sleep=fake_sleep, max_cycles=1, batch=25)
    async with Session() as s:
        left = {d["name"] for d in await ti.due_clubs(s, 100)}
    check("switched on, one cycle draws what is due, and the club that failed stays due", left == {"Current 2 CC"}, str(left))
    check("it does not wait long between cycles while there is work (2 seconds)", sleeps == [2], str(sleeps))

    # One long-lived loop, with a clock the test controls, so the loop's own
    # memory of the failure is what is under test: cycle 1 tries cur2 and fails,
    # cycle 2 (an hour later) must leave it alone, cycle 3 (past the hold-off)
    # must try it again, and this time it succeeds.
    sleeps.clear()
    FAIL_AFTER = 6 * 3600 + 5.0
    # clock calls: cycle 1 reads it (0) and stamps the failure (0); cycle 2 reads it (1h); cycle 3 reads it (past the hold-off)
    times = iter([0.0, 0.0, 3600.0, FAIL_AFTER])
    # (a cycle with nothing due never opens a renderer, so only two are used)
    stubs = [Stub(fail={K["cur2"]["token"]}), Stub()]
    made = iter(stubs)
    opened: list = []     # the cycle (0, 1, 2) each renderer was opened in

    def factory():
        opened.append(len(sleeps))
        return next(made)
    await ti.run_forever(session_maker=Session, enabled_fn=enabled, renderer_factory=factory,
                         sleep=fake_sleep, max_cycles=3, batch=25, clock=lambda: next(times, FAIL_AFTER))
    tried = [st.shots.count(K["cur2"]["token"]) for st in stubs]
    check("a club that failed is tried in cycle 1, NOT in cycle 2 an hour later, and tried again in cycle 3 past the hold-off",
          tried == [3, 3] and opened == [0, 2], f"{tried} opened in cycles {opened}")
    async with Session() as s:
        left = await ti.due_clubs(s, 100)
    check("and once it can be drawn it is: nothing is left due (all the state is in the database)", left == [], str(left))

    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("settings read failed")
        return False
    sleeps.clear()
    await ti.run_forever(session_maker=Session, enabled_fn=flaky, sleep=fake_sleep, max_cycles=3)
    check("a cycle that raises is logged and the loop carries on (it is never ended by an error)",
          calls["n"] == 3 and sleeps == [60, 60, 60], f"{calls} {sleeps}")

    async def boom():
        return True

    class NoChromium:
        async def __aenter__(self):
            raise RuntimeError("no chromium here")

        async def __aexit__(self, *e):
            return False
    async with engine.begin() as c:
        await c.execute(text("UPDATE club_teaser_snapshots SET image_version = NULL WHERE token = :t"), {"t": K["cur3"]["token"]})
    sleeps.clear()
    await ti.run_forever(session_maker=Session, enabled_fn=boom, renderer_factory=NoChromium, sleep=fake_sleep, max_cycles=1)
    check("no Chromium backs off for 15 minutes rather than spinning", sleeps == [900], str(sleeps))

    # ------------------------------------------------------ the setting
    print("the on/off setting and the panel")
    async with Session() as s:
        before = await ps.get_club_teaser_auto_draw(s)
        await ps.update_settings(s, {"club_teaser_auto_draw_enabled": True})
        on = await ps.get_club_teaser_auto_draw(s)
        try:
            await ps.update_settings(s, {"club_teaser_auto_draw_enabled": "yes"})
            bad = False
        except ValueError:
            bad = True
        still = await ps.get_club_teaser_auto_draw(s)
        await ps.update_settings(s, {"club_teaser_auto_draw_enabled": None})
        cleared = await ps.get_club_teaser_auto_draw(s)
    check("it is off by default, turns on, refuses a non-boolean, and a null clears it back to off",
          before is False and on is True and bad and still is True and cleared is False, f"{before} {on} {bad} {still} {cleared}")
    upd = club_admin.GeneralSettingsUpdate(club_teaser_auto_draw_enabled=True).model_dump(exclude_unset=True)
    check("the settings PATCH accepts it, and an absent key is not a clear", upd == {"club_teaser_auto_draw_enabled": True}
          and club_admin.GeneralSettingsUpdate().model_dump(exclude_unset=True) == {})
    async with Session() as s:
        gs = await club_admin._teaser_crawl_settings(s)
        blk = await marketing._images_block(s)
    check("the settings payload and the panel status both carry it", gs["club_teaser_auto_draw_enabled"] is False
          and blk["auto"] is False and {"ready", "pending", "waiting", "stale", "running", "auto", "last"} <= set(blk), str(blk))

    async with engine.begin() as c:
        await c.execute(text("DELETE FROM club_teaser_snapshots"))
        await c.execute(text("DELETE FROM marketing_clubs"))
        await c.execute(text("DELETE FROM organisations WHERE slug = 'adr-customer'"))
        await c.execute(text("UPDATE platform_settings SET settings = '{}' WHERE id = 1"))
    print(f"\n{PASS} passed, {FAIL} failed")
    if FAILURES:
        print("FAILED:", *FAILURES, sep="\n  ")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
