"""A prospect's season page takes the club's colours: accent and light or dark, from its logo.

Covers the colour rules on synthetic logos (pure), storing the theme (its own
column; the snapshot, its hash, its version and its drawn pictures must not
move), when a logo is read and when it is not, the backfill script (dry run,
paced apply, the Stop switch, --ignore-stop), the pull path, the fetch guard and
what the public page endpoint returns.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \
  python verification/verify_club_teaser_theme.py
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")
os.environ["TEASER_IMAGE_DIR"] = tempfile.mkdtemp(prefix="theme-")

import httpx
from PIL import Image, ImageDraw
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

from app.models.db import Base
from app.routers import public_teaser as pt
from app.scripts import backfill_club_teaser_themes as bf
from app.services import club_teaser as ct, club_teaser_theme as tt
from app.services.club_teaser_ddl import STATEMENTS

DB = os.environ["DATABASE_URL"]
if "verify" not in (make_url(DB).database or "").lower():
    print("REFUSING to run: not a verification database. These checks delete rows.")
    sys.exit(2)
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)
PASS = FAIL = 0


def check(label, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")


def g():
    return str(uuid.uuid4())


def _raises(fn) -> bool:
    try:
        fn()
    except ValueError:
        return True
    return False


def png(draw_fn, size=(120, 120), bg=(0, 0, 0, 0)) -> bytes:
    im = Image.new("RGBA", size, bg)
    draw_fn(ImageDraw.Draw(im))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def hue(h: str) -> float:
    import colorsys
    r, g_, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return colorsys.rgb_to_hsv(r, g_, b)[0] * 360


def contrast(h: str, mode: str) -> float:
    rgb = tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))
    return tt._contrast(rgb, tt.PAGE_BG[mode])


def req(ip="10.9.9.9"):
    return Request({"type": "http", "method": "GET", "path": "/", "headers": [(b"x-forwarded-for", ip.encode())], "client": (ip, 1)})


async def main():
    print("the colour rules")
    red_crest = png(lambda d: (d.ellipse((10, 10, 110, 110), fill=(200, 30, 30, 255)), d.ellipse((45, 45, 75, 75), fill=(255, 255, 255, 255))))
    t = tt.theme_from_image(red_crest)
    check("a red crest on a transparent logo gives a red accent on a dark page",
          t and t["mode"] == "dark" and t["accent"] and (hue(t["accent"]) < 12 or hue(t["accent"]) > 348), str(t))
    navy_gold = png(lambda d: (d.ellipse((10, 10, 110, 110), fill=(12, 20, 60, 255)), d.rectangle((50, 50, 70, 70), fill=(220, 170, 20, 255))))
    t = tt.theme_from_image(navy_gold)
    check("dark navy artwork on a transparent logo needs a LIGHT page", t and t["mode"] == "light", str(t))
    blue_on_white = png(lambda d: d.ellipse((20, 20, 100, 100), fill=(20, 80, 200, 255)), bg=(255, 255, 255, 255))
    t = tt.theme_from_image(blue_on_white)
    check("a blue logo on a white background gives a blue accent on a light page",
          t and t["mode"] == "light" and 205 < hue(t["accent"]) < 235, str(t))
    yellow_on_black = png(lambda d: d.ellipse((20, 20, 100, 100), fill=(250, 200, 0, 255)), bg=(8, 8, 8, 255))
    t = tt.theme_from_image(yellow_on_black)
    check("a yellow logo on a black background gives a yellow accent on a dark page, not the black",
          t and t["mode"] == "dark" and 35 < hue(t["accent"]) < 60, str(t))
    grey = png(lambda d: d.ellipse((10, 10, 110, 110), fill=(120, 120, 120, 255)))
    t = tt.theme_from_image(grey)
    check("a logo with no colour has no accent (the page keeps BetterCricket's)", t and t["accent"] is None and t["on_accent"] is None, str(t))
    check("bytes that are not an image give nothing", tt.theme_from_image(b"not an image") is None)
    check("an empty transparent picture gives nothing", tt.theme_from_image(png(lambda d: None)) is None)
    dark_blue = png(lambda d: d.ellipse((10, 10, 110, 110), fill=(10, 20, 90, 255)), bg=(8, 8, 8, 255))
    t = tt.theme_from_image(dark_blue)
    check("a dark accent is lifted until it can be read on a dark page (about 3:1)",
          t and t["mode"] == "dark" and contrast(t["accent"], "dark") >= tt.MIN_CONTRAST, str(t))
    pale = png(lambda d: d.ellipse((20, 20, 100, 100), fill=(255, 235, 120, 255)), bg=(255, 255, 255, 255))
    t = tt.theme_from_image(pale)
    check("a pale accent is deepened until it can be read on a light page",
          t and t["mode"] == "light" and contrast(t["accent"], "light") >= tt.MIN_CONTRAST, str(t))
    check("the text on the accent is black or white, whichever reads better",
          all(tt.theme_from_image(b)["on_accent"] in ("#000000", "#ffffff") for b in (red_crest, blue_on_white, yellow_on_black)))
    check("a hue is not split in two where red wraps around the colour wheel",
          (lambda x: x and (hue(x["accent"]) < 15 or hue(x["accent"]) > 345))(tt.theme_from_image(
              png(lambda d: (d.rectangle((0, 0, 60, 119), fill=(210, 20, 40, 255)), d.rectangle((60, 0, 119, 119), fill=(220, 30, 10, 255)))))))

    print("the secondary colour")
    red_blue = png(lambda d: (d.ellipse((10, 10, 110, 110), fill=(200, 30, 30, 255)), d.rectangle((40, 40, 80, 80), fill=(20, 60, 200, 255))))
    t = tt.theme_from_image(red_blue)
    check("a red and blue crest gives red as the primary and blue as the secondary",
          t and (hue(t["accent"]) < 12 or hue(t["accent"]) > 348) and t["accent2"] and 205 < hue(t["accent2"]) < 235, str(t))
    check("a one-colour crest has no secondary", tt.theme_from_image(red_crest)["accent2"] is None and tt.theme_from_image(blue_on_white)["accent2"] is None)
    red_orange = png(lambda d: (d.rectangle((0, 0, 79, 119), fill=(210, 20, 40, 255)), d.rectangle((80, 0, 119, 119), fill=(225, 60, 20, 255))))
    check("two reds of nearly the same hue are one colour, not a primary and a secondary", tt.theme_from_image(red_orange)["accent2"] is None, str(tt.theme_from_image(red_orange)))
    speck = png(lambda d: (d.ellipse((10, 10, 110, 110), fill=(200, 30, 30, 255)), d.rectangle((0, 0, 3, 3), fill=(20, 60, 200, 255))))
    check("a speck of another colour is not a secondary", tt.theme_from_image(speck)["accent2"] is None, str(tt.theme_from_image(speck)))
    check("a logo with no colour has neither", (lambda x: x["accent"] is None and x["accent2"] is None)(tt.theme_from_image(grey)))
    swapped = png(lambda d: (d.ellipse((10, 10, 110, 110), fill=(20, 60, 200, 255)), d.rectangle((40, 40, 80, 80), fill=(200, 30, 30, 255))))
    t2 = tt.theme_from_image(swapped)
    check("the bigger colour is the primary whichever colour it is", t2 and 205 < hue(t2["accent"]) < 235 and bool(t2.get("accent2")) and (hue(t2["accent2"]) < 12 or hue(t2["accent2"]) > 348), str(t2))

    print("the fetch guard")
    def handler(request):
        if "good" in request.url.host:
            return httpx.Response(200, content=red_crest, headers={"content-type": "image/png"})
        if "html" in request.url.host:
            return httpx.Response(200, content=b"<html>", headers={"content-type": "text/html"})
        if "big" in request.url.host:
            return httpx.Response(200, content=b"x" * (tt.MAX_LOGO_BYTES + 1), headers={"content-type": "image/png"})
        return httpx.Response(404)
    real_host = tt._public_host
    tt._public_host = lambda h: True
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        ok = await tt.fetch_logo("https://good.example/logo.png", client=c)
        html = await tt.fetch_logo("https://html.example/logo.png", client=c)
        big = await tt.fetch_logo("https://big.example/logo.png", client=c)
        missing = await tt.fetch_logo("https://gone.example/logo.png", client=c)
        scheme = await tt.fetch_logo("file:///etc/passwd", client=c)
    tt._public_host = real_host
    check("an image is fetched", ok == red_crest)
    check("a page that is not an image, an oversize file, a 404 and a non-web address give nothing",
          html is None and big is None and missing is None and scheme is None)
    check("an address on our own network is refused", await tt.fetch_logo("http://127.0.0.1:8000/x.png") is None
          and await tt.fetch_logo("http://localhost/x.png") is None)

    print("storing the theme")
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
        for s in STATEMENTS:
            await c.execute(text(s))
        await c.execute(text("DELETE FROM club_teaser_snapshots"))
        await c.execute(text("DELETE FROM marketing_clubs"))
    K = {}

    async def add_club(key, name, logo, *, status="ok"):
        cid, tok, guid = g(), "th" + uuid.uuid4().hex[:14], g()
        body = {"schema": ct.SCHEMA_VERSION, "club": {"name": name, "ca_org_id": g(), "logo_url": logo}, "season": {"name": "S", "year": 2026},
                "totals": {"matches": 12, "wins": 9, "losses": 3, "win_rate": 75}, "history": {"seasons_listed": 5, "first_year": 1975},
                "batting": [{"name": "A. Bat", "runs": 100}], "bowling": [{"name": "B. Bowl", "wickets": 9}]}
        async with Session() as s:
            await s.execute(text("INSERT INTO marketing_clubs (id, grassroots_guid, name, kind, excluded, not_interested, trial_modules, status, source, logo_url) "
                                 "VALUES (CAST(:i AS uuid), :g, :n, 'club', false, false, '[]'::jsonb, 'new', 'grassroots_api', :l)"),
                            {"i": cid, "g": guid, "n": name, "l": logo})
            await s.execute(text("INSERT INTO club_teaser_snapshots (marketing_club_id, org_guid, token, status, snapshot, data_hash, version, image_version, next_pull_at) "
                                 "VALUES (CAST(:i AS uuid), :g, :t, :st, CAST(:sn AS jsonb), 'h1', 3, 3, now() + interval '30 days')"),
                            {"i": cid, "g": guid, "t": tok, "st": status, "sn": json.dumps(body)})
            await s.commit()
        K[key] = {"id": cid, "token": tok, "name": name, "logo": logo}

    await add_club("a", "Crest Red CC", "https://good.example/red.png")
    await add_club("b", "No Logo CC", None)
    await add_club("c", "Broken Logo CC", "https://gone.example/x.png")
    await add_club("d", "Second Red CC", "https://good.example/two.png")

    fetched: list[str] = []

    async def stub_fetch(url):
        fetched.append(url)
        return {"https://good.example/red.png": red_crest, "https://good.example/two.png": blue_on_white,
                "https://good.example/new.png": yellow_on_black}.get(url)

    async def snap_state(key):
        async with Session() as s:
            r = (await s.execute(text("SELECT snapshot, data_hash, version, image_version, theme FROM club_teaser_snapshots "
                                      "WHERE marketing_club_id = CAST(:i AS uuid)"), {"i": K[key]["id"]})).mappings().first()
        return dict(r)

    before = await snap_state("a")
    async with Session() as s:
        th = await tt.store_theme(s, K["a"]["id"], K["a"]["logo"], fetch=stub_fetch)
    after = await snap_state("a")
    check("the theme is stored for the club", th and after["theme"] and after["theme"]["src"] == K["a"]["logo"] and after["theme"]["mode"] == "dark", str(after["theme"]))
    check("the snapshot, its hash, its version and its drawn pictures did not move",
          before["snapshot"] == after["snapshot"] and before["data_hash"] == after["data_hash"]
          and before["version"] == after["version"] == 3 and after["image_version"] == 3)
    n = len(fetched)
    async with Session() as s:
        await tt.store_theme(s, K["a"]["id"], K["a"]["logo"], fetch=stub_fetch)
    check("a club that already has a theme for this logo is not read again", len(fetched) == n)
    async with Session() as s:
        await tt.store_theme(s, K["a"]["id"], "https://good.example/new.png", fetch=stub_fetch)
    st = await snap_state("a")
    check("a changed logo address is read again and the theme follows it",
          st["theme"]["src"] == "https://good.example/new.png" and 35 < hue(st["theme"]["accent"]) < 60, str(st["theme"]))
    async with Session() as s:
        await tt.store_theme(s, K["a"]["id"], "https://gone.example/x.png", fetch=stub_fetch)
    st = await snap_state("a")
    check("a logo that cannot be fetched leaves the stored theme alone", st["theme"]["src"] == "https://good.example/new.png")
    async with Session() as s:
        await tt.store_theme(s, K["a"]["id"], None, fetch=stub_fetch)
    check("a club left with no logo address loses its theme", (await snap_state("a"))["theme"] is None)

    print("the backfill script")
    fetched.clear()
    lines: list[str] = []
    searched: list[str] = []

    async def finder(name, guid):
        searched.append(name)
        return "https://good.example/two.png" if name == "No Logo CC" else None

    out = await bf.run(Session, apply=False, fetch=stub_fetch, finder=finder, out=lines.append)
    check("the dry run lists clubs with a crest and no theme, and clubs with no crest address yet, and fetches and searches nothing",
          out["due"] == 4 and not fetched and not searched and any("Crest Red CC" in l for l in lines)
          and any("No Logo CC" in l and "will be searched for" in l for l in lines), f"{out} {lines}")

    class Pacer:
        calls = 0

        async def wait(self):
            Pacer.calls += 1

    out = await bf.run(Session, apply=True, fetch=stub_fetch, finder=finder, pacer=Pacer(), out=lines.append)
    check("--apply searches only for the club with no crest address, and reads each logo once, every outbound call paced",
          searched == ["No Logo CC"] and out["found"] == 1 and out["read"] == 3 and out["unreadable"] == 1 and Pacer.calls == 5 and len(fetched) == 4,
          f"{out} {searched} {fetched} {Pacer.calls}")
    async with Session() as s:
        crest = (await s.execute(text("SELECT logo_url FROM marketing_clubs WHERE id = CAST(:i AS uuid)"), {"i": K["b"]["id"]})).scalar()
    check("the crest address it found is stored on the directory row", crest == "https://good.example/two.png", str(crest))
    s_a = await snap_state("a")
    check("the clubs with readable logos now have themes; the broken one still has none",
          s_a["theme"] and (await snap_state("d"))["theme"]["mode"] == "light" and (await snap_state("b"))["theme"] and (await snap_state("c"))["theme"] is None)
    check("no snapshot or picture was touched", s_a["version"] == 3 and s_a["image_version"] == 3 and (await snap_state("d"))["image_version"] == 3)
    fetched.clear()
    searched.clear()
    out = await bf.run(Session, apply=True, fetch=stub_fetch, finder=finder, pacer=Pacer(), out=lines.append)
    check("a second run only retries the club that could not be read, and searches for nobody",
          out["due"] == 1 and fetched == ["https://gone.example/x.png"] and searched == [], f"{out} {fetched} {searched}")
    fetched.clear()
    out = await bf.run(Session, apply=True, redo=True, fetch=stub_fetch, finder=finder, pacer=Pacer(), out=lines.append)
    check("--redo reads every club that has a crest address again", out["due"] == 4, str(out))
    async with Session() as s:
        await s.execute(text("UPDATE club_teaser_snapshots SET theme = jsonb_set(theme, '{v}', '1') WHERE marketing_club_id = CAST(:i AS uuid)"), {"i": K["a"]["id"]})
        await s.commit()
    searched.clear()
    old = await bf.run(Session, apply=False, fetch=stub_fetch, finder=finder, out=lines.append)
    check("a theme made under an older set of colour rules is due again (one with both colours is not)", old["due"] >= 1 and any("Crest Red CC" in l for l in lines[-5:]), f"{old} {lines[-3:]}")
    async def slow_finder(name, guid):
        await asyncio.sleep(5)
        return "https://good.example/two.png"
    real_timeout, real_every = bf.CALL_TIMEOUT, bf.PROGRESS_EVERY
    bf.CALL_TIMEOUT = 0.05
    async with Session() as s:
        await s.execute(text("UPDATE marketing_clubs SET logo_url = NULL WHERE id = CAST(:i AS uuid)"), {"i": K["c"]["id"]})
        await s.commit()
    hung = await bf.run(Session, apply=True, club="Broken Logo", fetch=stub_fetch, finder=slow_finder, pacer=Pacer(), out=lines.append)
    bf.CALL_TIMEOUT = real_timeout
    check("a search that hangs is given up on, counted as no crest, and the run carries on", hung["no_logo"] == 1 and hung["found"] == 0, str(hung))
    async with Session() as s:
        await s.execute(text("UPDATE marketing_clubs SET logo_url = 'https://gone.example/x.png' WHERE id = CAST(:i AS uuid)"), {"i": K["c"]["id"]})
        await s.commit()
    bf.PROGRESS_EVERY = 2
    progress: list[str] = []
    await bf.run(Session, apply=True, redo=True, fetch=stub_fetch, finder=finder, pacer=Pacer(), out=progress.append)
    bf.PROGRESS_EVERY = real_every
    check("a long run says how far it has got every so many clubs, not only at the end", sum("clubs done" in l for l in progress) >= 1, str(progress))
    unfound = await bf.run(Session, apply=True, club="Nothing Like This", fetch=stub_fetch, finder=finder, pacer=Pacer(), out=lines.append)
    check("a club whose crest cannot be found is counted and left alone",
          unfound["due"] == 0)
    async with Session() as s:
        await s.execute(text("UPDATE marketing_clubs SET logo_url = NULL WHERE id = CAST(:i AS uuid)"), {"i": K["c"]["id"]})
        await s.commit()
    out = await bf.run(Session, apply=True, club="Broken Logo", fetch=stub_fetch, finder=finder, pacer=Pacer(), out=lines.append)
    check("a club the search cannot place is counted as having no crest, not as an error", out["no_logo"] == 1 and out["read"] == 0, str(out))
    async with Session() as s:
        await s.execute(text("UPDATE marketing_clubs SET logo_url = 'https://gone.example/x.png' WHERE id = CAST(:i AS uuid)"), {"i": K["c"]["id"]})
        await s.commit()

    async with Session() as s:
        await s.execute(text("DELETE FROM club_teaser_snapshots WHERE marketing_club_id = CAST(:i AS uuid)"), {"i": K["d"]["id"]})
        await s.commit()
    await add_club("d", "Second Red CC", "https://good.example/two.png")
    from app.services import club_directory
    real_paused = club_directory.is_crawl_paused

    async def paused(_s):
        return True
    club_directory.is_crawl_paused = paused
    fetched.clear()
    out = await bf.run(Session, apply=True, fetch=stub_fetch, pacer=Pacer(), out=lines.append)
    check("the operator's Stop switch halts it before any club is read", out["stopped"] and fetched == [])
    out = await bf.run(Session, apply=True, ignore_stop=True, fetch=stub_fetch, pacer=Pacer(), out=lines.append)
    check("--ignore-stop reads them anyway", not out["stopped"] and out["read"] >= 1, str(out))
    club_directory.is_crawl_paused = real_paused

    print("the pull path")
    async with Session() as s:
        await s.execute(text("DELETE FROM club_teaser_snapshots WHERE marketing_club_id = CAST(:i AS uuid)"), {"i": K["b"]["id"]})
        await s.execute(text("UPDATE marketing_clubs SET logo_url = 'https://good.example/red.png' WHERE id = CAST(:i AS uuid)"), {"i": K["b"]["id"]})
        await s.commit()
    real_store = tt.store_theme
    seen = {}

    async def spy(session, club_id, logo_url, **kw):
        seen["logo"] = logo_url
        return await real_store(session, club_id, logo_url, fetch=stub_fetch, **kw)
    tt.store_theme = spy
    async with Session() as s:
        res = {"status": "ok", "snapshot": {"schema": ct.SCHEMA_VERSION, "club": {"name": "No Logo CC"}, "season": {"name": "S"},
                                            "totals": {"matches": 12}, "batting": [{"name": "A", "runs": 1}], "bowling": []}, "calls": 3}
        await ct.save_result(s, {"id": K["b"]["id"], "guid": g(), "logo_url": "https://good.example/red.png"}, res)
    tt.store_theme = real_store
    sb = await snap_state("b")
    check("a club pulled for the first time gets its theme as part of the pull",
          seen.get("logo") == "https://good.example/red.png" and sb["theme"] and sb["theme"]["accent"], f"{seen} {sb['theme']}")
    async with Session() as s:
        res["status"] = "error"
        res["error"] = "boom"
        r2 = await ct.save_result(s, {"id": K["b"]["id"], "guid": g(), "logo_url": "https://x"}, {"status": "error", "error": "boom", "calls": 1})
    check("a failed pull neither reads a logo nor loses the theme", r2["status"] == "error" and (await snap_state("b"))["theme"]["accent"])


    print("the crest from the crawl's own search")
    class FakePH:
        @staticmethod
        async def search_organisations(name):
            return [{"id": "ca-other", "playHQId": "ph-other", "name": "Other", "logoURL": "https://cdn.example/other.png"},
                    {"id": "ca-1", "organisationGuid": "ca-1", "playHQId": "ph-1", "name": name, "logoURL": "https://cdn.example/mine.png"}]
    api = ct.LiveAPI()
    api._ph = FakePH
    club_dict = {"name": "Mine CC"}
    got = await api.resolve_org(club_dict, "ph-1")
    check("resolving a club for the pull keeps its crest from the same search result, at no extra call",
          got == "ca-1" and club_dict.get("logo_url") == "https://cdn.example/mine.png" and api.calls == 1, f"{got} {club_dict} {api.calls}")
    other = {"name": "Mine CC"}
    check("a club the search does not confirm on its id gets no crest", await api.resolve_org(other, "ph-nope") is None and "logo_url" not in other)
    check("only an http(s) address is kept as a crest",
          tt.logo_from_result({"logoURL": "javascript:alert(1)"}) is None and tt.logo_from_result({"logoURL": "https://a/b.png"}) == "https://a/b.png"
          and tt.logo_from_result({"logo": {"url": "https://a/c.png"}}) == "https://a/c.png")
    check("find_logo confirms the club on its id, as the crawl does",
          await tt.find_logo("Mine CC", "ph-1", search=FakePH.search_organisations) == "https://cdn.example/mine.png"
          and await tt.find_logo("Mine CC", "ph-zzz", search=FakePH.search_organisations) is None)
    async with Session() as s:
        b_before = (await s.execute(text("SELECT logo_url FROM marketing_clubs WHERE id = CAST(:i AS uuid)"), {"i": K["b"]["id"]})).scalar()
        await tt.remember_logo(s, K["d"]["id"], "https://cdn.example/should-not-replace.png")
        await tt.remember_logo(s, K["b"]["id"], "https://cdn.example/should-not-replace-either.png")
        d_logo = (await s.execute(text("SELECT logo_url FROM marketing_clubs WHERE id = CAST(:i AS uuid)"), {"i": K["d"]["id"]})).scalar()
        b_logo = (await s.execute(text("SELECT logo_url FROM marketing_clubs WHERE id = CAST(:i AS uuid)"), {"i": K["b"]["id"]})).scalar()
    check("an address already on the directory row is never replaced", d_logo == "https://good.example/two.png" and b_logo == b_before and b_before, f"{d_logo} {b_logo} {b_before}")
    async with Session() as s:
        await s.execute(text("UPDATE marketing_clubs SET logo_url = NULL WHERE id = CAST(:i AS uuid)"), {"i": K["d"]["id"]})
        await s.commit()
        await tt.remember_logo(s, K["d"]["id"], "https://cdn.example/filled.png")
        d_logo = (await s.execute(text("SELECT logo_url FROM marketing_clubs WHERE id = CAST(:i AS uuid)"), {"i": K["d"]["id"]})).scalar()
    check("an empty one is filled", d_logo == "https://cdn.example/filled.png", str(d_logo))
    async with Session() as s:
        res = {"status": "ok", "snapshot": {"schema": ct.SCHEMA_VERSION, "club": {"name": "Mine CC", "logo_url": "https://cdn.example/mine.png"}, "season": {"name": "S"},
                                            "totals": {"matches": 12}, "batting": [{"name": "A", "runs": 1}], "bowling": []}, "calls": 3}
        await s.execute(text("UPDATE marketing_clubs SET logo_url = NULL WHERE id = CAST(:i AS uuid)"), {"i": K["c"]["id"]})
        await s.commit()
        await ct.save_result(s, {"id": K["c"]["id"], "guid": g(), "logo_url": "https://cdn.example/mine.png"}, res)
        c_logo = (await s.execute(text("SELECT logo_url FROM marketing_clubs WHERE id = CAST(:i AS uuid)"), {"i": K["c"]["id"]})).scalar()
    check("a pull records the crest it found on the directory row", c_logo == "https://cdn.example/mine.png", str(c_logo))


    print("the crest kept on our volume")
    big = png(lambda d: d.ellipse((20, 20, 780, 480), fill=(200, 30, 30, 255)), size=(800, 500))
    kept = tt.crest_png(big)
    from PIL import Image as _I
    kim = _I.open(io.BytesIO(kept)) if kept else None
    check("a large logo is kept as a PNG no bigger than 256 pixels on its longest side",
          kim is not None and kim.format == "PNG" and max(kim.size) <= tt.CREST_EDGE and kim.size[0] > kim.size[1], str(kim and (kim.format, kim.size)))
    check("an SVG (which can carry script) and bytes that are not an image are not kept",
          tt.crest_png(b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>') is None and tt.crest_png(b"junk") is None)
    check("a path is never built from a token that is not one",
          all(_raises(lambda t=t: tt.crest_path(t)) for t in ("../etc/passwd", "a/b", "", "short", "x" * 100)))
    await add_club("e", "Crest Keeper CC", "https://good.example/big.png")

    async def crest_fetch(url):
        return {"https://good.example/big.png": big, "https://good.example/svg.png": b"<svg/>"}.get(url)

    async with Session() as s:
        th = await tt.store_theme(s, K["e"]["id"], "https://good.example/big.png", fetch=crest_fetch)
    st = await snap_state("e")
    path_e = tt.crest_path(K["e"]["token"])
    check("reading a logo stores the theme and keeps the crest, with a fingerprint in the theme",
          th and st["theme"].get("crest") and path_e.is_file() and path_e.stat().st_size < 200_000, str(st["theme"]))
    check("the kept crest is a decodable PNG within the size limit", _I.open(path_e).format == "PNG" and max(_I.open(path_e).size) <= tt.CREST_EDGE)
    url_e = tt.crest_url(K["e"]["token"], st["theme"])
    check("the public address carries the token and the fingerprint", url_e == f"/api/public/teaser/{K['e']['token']}/crest.png?v={st['theme']['crest']}", str(url_e))
    check("the snapshot, hash, version and drawn pictures did not move when the crest was kept",
          st["version"] == 3 and st["image_version"] == 3 and st["data_hash"] == "h1")
    check("a club with no theme, or a theme with no crest, has no kept crest address",
          tt.crest_url(K["e"]["token"], None) is None and tt.crest_url(K["e"]["token"], {"v": 2, "mode": "dark"}) is None)
    fetched_e: list[str] = []

    async def counting_fetch(url):
        fetched_e.append(url)
        return await crest_fetch(url)
    async with Session() as s:
        await tt.store_theme(s, K["e"]["id"], "https://good.example/big.png", fetch=counting_fetch)
    check("a club that already has its theme and its kept crest is not read again", fetched_e == [])
    async with Session() as s:
        page_kept = await pt.get_teaser(K["e"]["token"], req("10.8.8.1"), s)
        crest_resp = await pt.get_teaser_crest(K["e"]["token"], s)
    check("the page uses the crest on our own server, not the host it came from",
          page_kept["club"]["logo_url"] == url_e and not page_kept["club"]["logo_url"].startswith("http"), str(page_kept["club"]))
    check("the crest route serves the file as an image that can be cached", str(getattr(crest_resp, "path", "")) == str(path_e)
          and crest_resp.media_type == "image/png" and "max-age" in crest_resp.headers.get("cache-control", ""), str(getattr(crest_resp, "path", None)))
    from fastapi import HTTPException as _HE
    async with Session() as s:
        try:
            await pt.get_teaser_crest("NoSuchTokenAtAll123", s)
            unknown_ok = False
        except _HE as e:
            unknown_ok = e.status_code == 404
        try:
            await pt.get_teaser_crest("../../etc/passwd", s)
            bad_ok = False
        except _HE as e:
            bad_ok = e.status_code == 404
    check("an unknown or malformed token gets a 404 from the crest route", unknown_ok and bad_ok)
    path_e.unlink()
    async with Session() as s:
        page_gone = await pt.get_teaser(K["e"]["token"], req("10.8.8.2"), s)
    check("if the file has gone from the volume the page falls back to the original address (never a broken image)",
          page_gone["club"]["logo_url"] != url_e and tt.crest_url(K["e"]["token"], st["theme"]) is None, str(page_gone["club"]))
    fetched_e.clear()
    async with Session() as s:
        await tt.store_theme(s, K["e"]["id"], "https://good.example/big.png", fetch=counting_fetch)
    check("and the next read keeps the crest again", fetched_e == ["https://good.example/big.png"] and path_e.is_file())
    await add_club("f", "Svg Crest CC", "https://good.example/svg.png")
    async with Session() as s:
        thf = await tt.store_theme(s, K["f"]["id"], "https://good.example/svg.png", fetch=crest_fetch)
    check("a logo that cannot be decoded keeps no crest and leaves no file behind", thf is None and not tt.crest_path(K["f"]["token"]).exists())
    async with Session() as s:
        await s.execute(text("UPDATE club_teaser_snapshots SET theme = theme - 'crest' WHERE marketing_club_id = CAST(:i AS uuid)"), {"i": K["e"]["id"]})
        await s.commit()
    tt.crest_path(K["e"]["token"]).unlink()
    searched.clear()
    out = await bf.run(Session, apply=False, club="Crest Keeper", fetch=crest_fetch, finder=finder, out=lines.append)
    check("the backfill treats a club with a theme but no kept crest as due", out["due"] == 1, str(out))
    await bf.run(Session, apply=True, club="Crest Keeper", fetch=crest_fetch, finder=finder, pacer=Pacer(), out=lines.append)
    check("and keeps the crest for it", tt.crest_path(K["e"]["token"]).is_file() and (await snap_state("e"))["theme"].get("crest"))

    print("the public page")
    async with Session() as s:
        page = await pt.get_teaser(K["d"]["token"], req(), s)
        await s.execute(text("UPDATE club_teaser_snapshots SET theme = CAST(:t AS jsonb) WHERE marketing_club_id = CAST(:i AS uuid)"),
                        {"t": json.dumps({"v": 2, "mode": "neon", "accent": "red;}</style><script>", "accent2": "#12", "on_accent": "#fff"}), "i": K["a"]["id"]})
        await s.commit()
        bad = await pt.get_teaser(K["a"]["token"], req("10.9.9.8"), s)
    check("the page gets the club's theme", page["theme"] and page["theme"]["mode"] == "light" and page["theme"]["accent"].startswith("#"), str(page.get("theme")))
    check("a stored colour that is not #rrggbb never reaches the page (it goes into a style), and an unknown mode is dark",
          bad["theme"] == {"mode": "dark", "accent": None, "accent2": None, "on_accent": None}, str(bad.get("theme")))
    check("the page no longer carries a first year (it was Play-Cricket's, not what we mean)", "history" not in page and "first_year" not in json.dumps(page))
    async with Session() as s:
        await s.execute(text("UPDATE club_teaser_snapshots SET theme = CAST(:t AS jsonb) WHERE marketing_club_id = CAST(:i AS uuid)"),
                        {"t": json.dumps({"v": 2, "mode": "dark", "accent": "#d02020", "accent2": "url(x)", "on_accent": "#ffffff"}), "i": K["a"]["id"]})
        await s.commit()
        half = await pt.get_teaser(K["a"]["token"], req("10.9.9.5"), s)
        await s.execute(text("UPDATE club_teaser_snapshots SET theme = CAST(:t AS jsonb) WHERE marketing_club_id = CAST(:i AS uuid)"),
                        {"t": json.dumps({"v": 2, "mode": "dark", "accent": "#d02020", "accent2": "#1040c0", "on_accent": "#ffffff"}), "i": K["a"]["id"]})
        await s.commit()
        both = await pt.get_teaser(K["a"]["token"], req("10.9.9.4"), s)
    check("a well formed secondary colour reaches the page and a malformed one never does",
          both["theme"]["accent2"] == "#1040c0" and half["theme"]["accent"] == "#d02020" and half["theme"]["accent2"] is None, f"{both['theme']} {half['theme']}")
    async with Session() as s:
        none_page = await pt.get_teaser(K["c"]["token"], req("10.9.9.7"), s)
    check("a club with no theme gets none (the page keeps BetterCricket's look)", none_page["theme"] is None)
    async with Session() as s:
        await s.execute(text("UPDATE club_teaser_snapshots SET snapshot = jsonb_set(snapshot, '{club,logo_url}', 'null'::jsonb) WHERE marketing_club_id = CAST(:i AS uuid)"), {"i": K["d"]["id"]})
        await s.execute(text("UPDATE marketing_clubs SET logo_url = 'https://cdn.example/dir.png' WHERE id = CAST(:i AS uuid)"), {"i": K["d"]["id"]})
        await s.commit()
        tt.crest_path(K["d"]["token"]).unlink(missing_ok=True)   # no kept copy: the fallback is what is being tested
        overlay = await pt.get_teaser(K["d"]["token"], req("10.9.9.6"), s)
    check("a snapshot pulled before the crest was captured shows the directory row's crest, with no re-pull",
          (overlay.get("club") or {}).get("logo_url") == "https://cdn.example/dir.png", str(overlay["club"]))

    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
