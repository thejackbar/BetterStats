"""The Meta ad pack (slice 4): which clubs go in, what the words say, what the
manifest and the zip hold, and the two admin routes.

Runs the SHIPPED service and route bodies against a real Postgres, with real
picture files on disk. Nothing here (or in the code under test) talks to Meta.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \
  python verification/verify_club_teaser_adpack.py
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import re
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")
TMP = tempfile.mkdtemp(prefix="adpack-")
os.environ["TEASER_IMAGE_DIR"] = TMP
os.environ["PUBLIC_BASE_URL"] = "https://site.test"

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import Base

MISSING: list[str] = []
try:
    from fastapi import HTTPException
    from app.services import club_teaser, club_teaser_images as ti
    from app.services import club_teaser_adpack as ap
    from app.services.club_teaser_ddl import STATEMENTS
    from app.routers import marketing
    for name in ("select_clubs", "build_zip", "ad_copy", "manifest_rows", "clean_campaign"):
        if not hasattr(ap, name):
            MISSING.append(f"club_teaser_adpack.{name} is missing")
    if not hasattr(marketing, "ad_pack_zip"):
        MISSING.append("marketing.ad_pack_zip is missing")
except ImportError as exc:  # pragma: no cover - control run only
    ap = None
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


def png(w: int, h: int, shade: int = 10) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (shade, 20, 30)).save(buf, "PNG")
    return buf.getvalue()


SECRET_NAMES = ["Zed Secretname", "Quentin Hushhush"]


def snap(name, *, kind="runs", value=565, season="Summer 2025/26"):
    s = {"schema": 2, "club": {"name": name, "state": "VIC", "ca_org_id": "o"},
         "season": {"name": season, "year": 2025},
         "totals": {"matches": 20, "wins": 14, "losses": 6, "win_rate": 70},
         "batting": [{"name": SECRET_NAMES[0], "runs": value if kind == "runs" else 120, "average": 40.0, "high_score": 90, "hs_not_out": False, "fifties": 2, "hundreds": 0}] * 3,
         "bowling": [{"name": SECRET_NAMES[1], "wickets": value if kind == "wickets" else 8, "average": 15.0, "best": "4-20", "economy": 4.2}] * 3,
         "ladders": [], "records": [], "fielding": [], "history": {}}
    return s


async def main() -> None:
    if MISSING:
        check("the ad pack backend is present", False, "; ".join(MISSING))
        print(f"\n{PASS} passed, {FAIL} failed")
        sys.exit(1)

    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
        for s in STATEMENTS:
            await c.execute(text(s))
        await c.execute(text("DELETE FROM club_teaser_snapshots"))
        await c.execute(text("DELETE FROM marketing_clubs"))
        await c.execute(text("DELETE FROM organisations WHERE slug = 'adpk-customer'"))

    cust_org = g()
    clubs: dict[str, dict] = {}
    async with Session() as s:
        await s.execute(text("INSERT INTO organisations (id, name, slug, is_active) VALUES (CAST(:i AS uuid), 'Cust', 'adpk-customer', true)"),
                        {"i": cust_org})

        async def club(key, name, *, state="VIC", lat=-37.8, lng=144.9, status="ok", image_version=1, pictures=True,
                       registered=False, excluded=False, not_interested=False, hero="runs", value=565, utm=None, season="Summer 2025/26"):
            cid, tok = g(), "tk" + uuid.uuid4().hex[:14]
            await s.execute(text("""INSERT INTO marketing_clubs (id, grassroots_guid, name, kind, excluded, not_interested, trial_modules,
                status, source, state, suburb, postcode, latitude, longitude, utm_code, existing_org_id, association_name)
                VALUES (CAST(:id AS uuid), :g, :n, 'club', :ex, :ni, '[]'::jsonb, 'new', 'grassroots_api', :st, 'Suburbia', '3000',
                :lat, :lng, :utm, CAST(:org AS uuid), 'Test Association')"""),
                {"id": cid, "g": g(), "n": name, "ex": excluded, "ni": not_interested, "st": state, "lat": lat, "lng": lng,
                 "utm": utm, "org": cust_org if registered else None})
            body = snap(name, kind=hero, value=value, season=season) if status == "ok" else None
            await s.execute(text("""INSERT INTO club_teaser_snapshots (marketing_club_id, org_guid, token, status, snapshot, version, image_version)
                VALUES (CAST(:id AS uuid), 'g', :t, :st, CAST(:sn AS jsonb), 1, :iv)"""),
                {"id": cid, "t": tok, "st": status, "sn": json.dumps(body) if body else None, "iv": image_version})
            if pictures:
                for fmt, f in ti.FORMATS.items():
                    p = ti.image_path(tok, fmt)
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(png(f["width"], f["height"], shade=len(key) * 7))
            clubs[key] = {"id": cid, "token": tok, "name": name}

        await club("alpha", "Alpha Cricket Club", utm="alpha-cricket-club")
        await club("bravo", "Bravo Cricket Club", hero="wickets", value=34)
        await club("charlie", "Charlie CC", state="NSW")
        await club("delta", "Delta Cricket Club", lat=None, lng=None)                 # no location
        await club("echo", "Echo Cricket Club", registered=True)                      # a customer
        await club("foxtrot", "Foxtrot Cricket Club", excluded=True)
        await club("golf", "Golf Cricket Club", not_interested=True)
        await club("hotel", "Hotel Cricket Club", pictures=False)                     # marked drawn, files gone
        await club("india", "India Cricket Club", image_version=None, pictures=False) # never drawn
        await club("juliet", "Juliet Cricket Club", status="junior_only")
        await club("kilo", "Kilo Cricket Club")
        await club("twin1", "Twin Cricket Club")
        await club("twin2", "Twin Cricket Club")                                      # same name as twin1
        await club("longname", "Brisbane Masters Cricket Incorporated Seniors and Veterans Association", hero="wickets", value=1234)
        await s.commit()

    def filt(**kw):
        return marketing._filter_kwargs(kw.get("q"), kw.get("state"), None, None, None, None, None)

    # ---------------------------------------------------------------- selection
    print("which clubs go in")
    async with Session() as s:
        sel = await ap.select_clubs(s, filt(), limit=100)
        names = [c["name"] for c in sel["clubs"]]
        sel_vic = await ap.select_clubs(s, filt(state="VIC"), limit=100)
    want = {"Alpha Cricket Club", "Bravo Cricket Club", "Charlie CC", "Delta Cricket Club", "Kilo Cricket Club",
            "Twin Cricket Club", "Brisbane Masters Cricket Incorporated Seniors and Veterans Association"}
    check("a good club with its pictures on disk is in", want <= set(names), str(sorted(set(names) ^ want)))
    check("a customer, an excluded club and a not-interested club are never in",
          not ({"Echo Cricket Club", "Foxtrot Cricket Club", "Golf Cricket Club"} & set(names)))
    check("a club marked drawn whose files are gone, one never drawn, and a junior-only club are not in",
          not ({"Hotel Cricket Club", "India Cricket Club", "Juliet Cricket Club"} & set(names)))
    check("the directory filters narrow it (VIC only drops the NSW club)",
          "Charlie CC" not in {c["name"] for c in sel_vic["clubs"]} and "Alpha Cricket Club" in {c["name"] for c in sel_vic["clubs"]})
    check("matching counts every club the filters match, eligible only those that can go in",
          sel["matching"] == 14 and sel["eligible"] == len(want) + 1 and sel["eligible"] < sel["matching"], str((sel["matching"], sel["eligible"])))
    check("a club with no location is counted, not dropped", sel["without_location"] == 1 and "Delta Cricket Club" in names)
    check("the order is by name, so a pack is the same every time", names == sorted(names))
    async with Session() as s:
        p1 = await ap.select_clubs(s, filt(), limit=3, offset=0)
        p2 = await ap.select_clubs(s, filt(), limit=3, offset=3)
        huge = await ap.select_clubs(s, filt(), limit=10**6)
        past = await ap.select_clubs(s, filt(), limit=5, offset=500)
    check("a limit takes the first N and an offset carries on from there, with no overlap",
          len(p1["clubs"]) == 3 and not ({c["id"] for c in p1["clubs"]} & {c["id"] for c in p2["clubs"]})
          and [c["name"] for c in p1["clubs"] + p2["clubs"]] == names[:6])
    check("a huge limit is capped", len(huge["clubs"]) <= ap.MAX_LIMIT and huge["limit"] == ap.MAX_LIMIT)
    check("an offset past the end is an empty pack, not an error", past["clubs"] == [] and past["eligible"] == sel["eligible"])
    async with Session() as s:
        empty = await ap.select_clubs(s, filt(q="no-such-club-anywhere"), limit=5)
    check("filters that match nothing give an empty pack and zero counts", empty["clubs"] == [] and empty["matching"] == 0)

    # -------------------------------------------------------------------- words
    print("the ad words")
    by_name = {c["name"]: c for c in sel["clubs"]}
    rows = ap.manifest_rows(sel["clubs"], campaign="spring-push", radius_km=15)
    r = {x["club"]: x for x in rows}
    a, b, lg = r["Alpha Cricket Club"], r["Bravo Cricket Club"], r["Brisbane Masters Cricket Incorporated Seniors and Veterans Association"]
    check("a run-scorer lead reads as one, with the figure and the season, third person",
          a["primary_text"].startswith("The club's top run-scorer made 565 runs in Summer 2025/26."), a["primary_text"])
    check("a wicket-taker lead reads as one", b["primary_text"].startswith("The club's leading wicket-taker took 34 wickets"), b["primary_text"])
    check("every headline, primary text and description is inside Meta's recommended length",
          all(len(x["headline"]) <= ap.HEADLINE_MAX and len(x["primary_text"]) <= ap.PRIMARY_MAX and len(x["description"]) <= ap.DESCRIPTION_MAX
              for x in rows), str([(x["club"], len(x["headline"]), len(x["primary_text"])) for x in rows if len(x["primary_text"]) > 125 or len(x["headline"]) > 40]))
    check("a headline that would be too long falls back to a short one with no club name",
          lg["headline"] == "Club season, ready to claim" and a["headline"] == "Club season, ready to claim"
          and r["Kilo Cricket Club"]["headline"] == "Kilo Cricket Club season, ready to claim"
          and r["Charlie CC"]["headline"] == "Charlie CC season, ready to claim")
    long_season = ap.ad_copy("X", {"hero": {"kind": "wickets", "value": 1234, "unit": "wickets"}, "season": {"name": "Summer 2025/26 Premier Women's Twenty20 Championship"}})
    check("a primary text that would be too long drops the season rather than being cut mid-sentence",
          len(long_season["primary_text"]) <= ap.PRIMARY_MAX and "Championship" not in long_season["primary_text"], long_season["primary_text"])
    no_hero = ap.ad_copy("X", {"hero": None, "season": {}})
    check("a club with no lead figure still gets sensible words", "already on BetterCricket" in no_hero["primary_text"])
    blob = json.dumps(rows) + ap.README
    check("no player's name is anywhere in the manifest or the README", not any(n.split()[0] in blob or n.split()[1] in blob for n in SECRET_NAMES))
    check("the words never speak to the viewer ('you', 'your') or assume they belong to the club",
          not any(re.search(r"\b(you|your|you're)\b", x["headline"] + " " + x["primary_text"] + " " + x["description"], re.I) for x in rows))
    check("no em or en dashes in the words", not re.search("[—–]", blob))

    # ----------------------------------------------------------------- manifest
    print("the manifest")
    check("a club with a location carries it with the radius, and is geo ready",
          a["latitude"] == "-37.800000" and a["longitude"] == "144.900000" and a["radius_km"] == 15 and a["geo_ready"] == "yes")
    d = r["Delta Cricket Club"]
    check("a club with no location has blanks and says geo ready no (no 0,0 pin)",
          d["latitude"] == "" and d["longitude"] == "" and d["radius_km"] == "" and d["geo_ready"] == "no")
    q = parse_qs(urlparse(a["landing_url_feed"]).query)
    check("the feed link goes to the club's own page with meta tracking and the club's UTM as utm_id",
          a["landing_url_feed"].startswith(f"https://site.test/preview/{by_name['Alpha Cricket Club']['token']}?")
          and q["utm_source"] == ["meta"] and q["utm_medium"] == ["paid_social"] and q["utm_campaign"] == ["spring-push"]
          and q["utm_content"] == ["feed"] and q["utm_id"] == ["alpha-cricket-club"], str(q))
    check("the story link differs only in utm_content",
          parse_qs(urlparse(a["landing_url_story"]).query)["utm_content"] == ["story"]
          and a["landing_url_story"].replace("utm_content=story", "utm_content=feed") == a["landing_url_feed"])
    check("a club with no UTM code gets the directory's default one, never a blank utm_id",
          parse_qs(urlparse(b["landing_url_feed"]).query)["utm_id"] == ["bravo-cricket-club"])
    check("every row's link carries that row's own token (no club points at another's page)",
          all(by_name[x["club"]]["token"] in x["landing_url_feed"] and by_name[x["club"]]["token"] in x["landing_url_story"] for x in rows if x["club"] != "Twin Cricket Club"))
    check("campaign names are made link-safe", ap.clean_campaign("Spring Push! 2026 & more") == "spring-push-2026-more"
          and ap.clean_campaign("   ") == ap.DEFAULT_CAMPAIGN and ap.clean_campaign(None) == ap.DEFAULT_CAMPAIGN
          and "&" not in ap.clean_campaign("a&b=c"))
    check("the radius is kept between 2 and 80 km, and a bad value is the default",
          [ap.clamp_radius(x) for x in (1, 500, "9", "x", None)] == [2, 80, 9, 15, 15])
    check("the lead figure column reads as the picture does", a["lead_figure"] == "565 runs" and b["lead_figure"] == "34 wickets")
    tw = [x for x in rows if x["club"] == "Twin Cricket Club"]
    check("two clubs with the same name get different file names",
          len(tw) == 2 and tw[0]["feed_image"] != tw[1]["feed_image"] and tw[0]["story_image"] != tw[1]["story_image"])

    # --------------------------------------------------------------------- zip
    print("the zip")
    path = ap.build_zip(sel["clubs"][:4], campaign="spring-push", radius_km=15)
    try:
        z = zipfile.ZipFile(path)
        listing = z.namelist()
        mrows = list(csv.DictReader(io.StringIO(z.read("manifest.csv").decode())))
        check("it holds a README, a manifest, and a feed and a story picture for each club",
              "README.txt" in listing and "manifest.csv" in listing
              and len([n for n in listing if n.startswith("feed/")]) == 4 and len([n for n in listing if n.startswith("story/")]) == 4, str(listing))
        check("the manifest reads back with every column and one row per club",
              list(mrows[0].keys()) == ap.MANIFEST_COLUMNS and len(mrows) == 4)
        check("every picture a manifest row names is in the zip",
              all(m["feed_image"] in listing and m["story_image"] in listing for m in mrows))
        first = sel["clubs"][0]
        fn = f"feed/{ap.file_name(first['name'], first['token'])}"
        check("the picture in the zip is byte for byte the file on disk",
              z.read(fn) == ti.image_path(first["token"], "feed").read_bytes())
        from PIL import Image
        check("feed pictures are 1080 by 1350 and story pictures 1080 by 1920",
              Image.open(io.BytesIO(z.read(fn))).size == (1080, 1350)
              and Image.open(io.BytesIO(z.read(fn.replace("feed/", "story/")))).size == (1080, 1920))
        check("the zip is not corrupt", z.testzip() is None)
        check("the README says nothing is sent to Meta and nothing is spent",
              "Nothing here has been sent to Meta" in z.read("README.txt").decode() and "nothing is spent" in z.read("README.txt").decode())
    finally:
        path.unlink(missing_ok=True)

    # ------------------------------------------------------------------- routes
    print("the admin routes")
    async with Session() as s:
        summ = await marketing.ad_pack_summary(limit=5, offset=0, filters=filt(), db=s, _=None)
    check("the summary says what the filters match, what can go in, and how many this pack takes",
          summ["matching"] == 14 and summ["eligible"] == 8 and summ["in_pack"] == 5 and summ["without_location"] == 1
          and summ["max_limit"] == 100 and summ["default_radius_km"] == 15, str(summ))
    async with Session() as s:
        resp = await marketing.ad_pack_zip(limit=3, offset=0, campaign="Spring Push", radius_km=999, filters=filt(), db=s, _=None)
    p = Path(resp.path)
    check("the zip route returns a zip with a dated name, built from the same selection",
          resp.media_type == "application/zip" and re.match(r"bettercricket-ad-pack-\d{8}\.zip", resp.filename or "") and p.is_file()
          and len([n for n in zipfile.ZipFile(p).namelist() if n.startswith("feed/")]) == 3)
    m0 = list(csv.DictReader(io.StringIO(zipfile.ZipFile(p).read("manifest.csv").decode())))[0]
    check("the campaign name and radius from the request are cleaned and applied",
          "utm_campaign=spring-push" in m0["landing_url_feed"] and m0["radius_km"] == "80", str(m0["landing_url_feed"]))
    await resp.background()
    check("the temporary file is deleted once it has been sent", not p.exists())
    async with Session() as s:
        try:
            await marketing.ad_pack_zip(limit=5, offset=0, campaign="x", radius_km=15, filters=filt(q="no-such-club-anywhere"), db=s, _=None)
            code = 200
        except HTTPException as e:
            code = e.status_code
    check("a pack with no clubs is a clear 404, not an empty zip", code == 404)
    src = Path(ap.__file__).read_text()
    check("the ad pack code never talks to Meta (no Graph API, no meta_ads module, no HTTP client)",
          not re.search(r"graph\.facebook|meta_ads|httpx|requests\.|aiohttp|urllib\.request", src))

    async with engine.begin() as c:
        await c.execute(text("DELETE FROM club_teaser_snapshots"))
        await c.execute(text("DELETE FROM marketing_clubs"))
        await c.execute(text("DELETE FROM organisations WHERE slug = 'adpk-customer'"))
    print(f"\n{PASS} passed, {FAIL} failed")
    if FAILURES:
        print("FAILED:", *FAILURES, sep="\n  ")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
