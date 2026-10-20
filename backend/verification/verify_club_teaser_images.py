"""Teaser pictures (slice 3): the renderer, where files live, the public image
route, the share card, and the {{teaser_url}} / {{teaser_image_url}} merge
variables with the BetterComms path that carries them.

Runs the SHIPPED services and route bodies against a real Postgres. Drawing is
checked twice: with a scripted stand-in renderer (the bookkeeping: what is due,
what a failure leaves behind, a snapshot that moves mid-draw), and with the REAL
headless Chromium against a tiny local web server (the mechanics: exact pixel
sizes, a card that never becomes ready, a card that does not fit its frame).
The Chromium section is reported as skipped, not passed, if no Chromium is found.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \
  python verification/verify_club_teaser_images.py
"""
from __future__ import annotations

import asyncio
import glob
import io
import os
import re
import sys
import tempfile
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")
# Set BEFORE the settings module is imported: pydantic-settings reads env once.
TMP = tempfile.mkdtemp(prefix="teaser-images-")
os.environ["TEASER_IMAGE_DIR"] = TMP
os.environ["PUBLIC_BASE_URL"] = "https://site.test"

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import Base

MISSING: list[str] = []
try:
    from fastapi import BackgroundTasks, HTTPException
    from app.services import club_teaser_images as ti
    from app.services.club_teaser_ddl import STATEMENTS
    from app.routers import comms, marketing, og_preview as og, public_teaser as pt
    from app.services import comms_segments as seg
    from app.models.db import Organisation, MarketingClub
    for name in ("FORMATS", "render_pending", "vars_by_marketing_club", "image_path", "due_clubs"):
        if not hasattr(ti, name):
            MISSING.append(f"club_teaser_images.{name} is missing")
    for name in ("OUTREACH_STARTER_TEMPLATES", "seed_outreach_templates"):
        if not hasattr(comms, name):
            MISSING.append(f"comms.{name} is missing")
except ImportError as exc:  # pragma: no cover - control run only
    ti = None
    MISSING.append(str(exc))

DB = os.environ["DATABASE_URL"]
if "verify" not in (make_url(DB).database or "").lower():
    print("REFUSING to run: not a verification database. These checks delete and drop tables.")
    sys.exit(2)
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)
PASS = FAIL = SKIP = 0
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


def skip(label: str, why: str) -> None:
    global SKIP
    SKIP += 1
    print(f"  SKIP {label}  -- {why}")


def g() -> str:
    return str(uuid.uuid4())


def png(w: int, h: int) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (10, 20, 30)).save(buf, "PNG")
    return buf.getvalue()


class StubRenderer:
    """Stands in for Chromium: returns a real PNG of the format's size. ``fail``
    is a set of tokens that raise; ``on_shoot`` runs first for each picture."""

    def __init__(self, fail=(), on_shoot=None, gate=None):
        self.fail, self.on_shoot, self.gate, self.shots = set(fail), on_shoot, gate, []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def shoot(self, url, width, height):
        token = url.split("/preview/")[1].split("/")[0]
        self.shots.append((token, width, height))
        if self.gate is not None:
            await self.gate.wait()
        if self.on_shoot:
            await self.on_shoot(token)
        if token in self.fail:
            raise RuntimeError("boom")
        return png(width, height)


class BrokenRenderer:
    async def __aenter__(self):
        raise RuntimeError("no chromium here")

    async def __aexit__(self, *exc):
        return False


SNAP = {"schema": 2, "club": {"name": "Test CC", "state": "VIC", "ca_org_id": "o"},
        "season": {"name": "Summer 2025/26", "year": 2025}, "totals": {"matches": 12, "wins": 8, "losses": 4, "win_rate": 66},
        "batting": [{"name": "A. Bat", "runs": 400, "average": 40.0}] * 3, "bowling": [{"name": "B. Bowl", "wickets": 20}] * 3}


async def main() -> None:
    if MISSING:
        check("the teaser pictures backend is present", False, "; ".join(MISSING))
        print(f"\n{PASS} passed, {FAIL} failed")
        sys.exit(1)

    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
        for s in STATEMENTS:
            await c.execute(text(s))
        await c.execute(text("DELETE FROM comms_contacts"))
        await c.execute(text("DELETE FROM comms_templates"))
        await c.execute(text("DELETE FROM club_teaser_snapshots"))
        await c.execute(text("DELETE FROM marketing_clubs"))
        await c.execute(text("DELETE FROM organisations WHERE slug LIKE 'timg-%'"))

    import json
    async with Session() as s:
        outreach_id, club_org_id = g(), g()
        for oid, slug, flag in ((outreach_id, "timg-outreach", True), (club_org_id, "timg-club", False)):
            await s.execute(text("INSERT INTO organisations (id, name, slug, is_marketing_outreach, is_active) "
                                 "VALUES (CAST(:i AS uuid), :n, :s, :f, true)"), {"i": oid, "n": slug.title(), "s": slug, "f": flag})

        async def club(name, status=None, *, image_version=None, version=1, registered=False):
            cid = g()
            await s.execute(text("""INSERT INTO marketing_clubs (id, grassroots_guid, name, kind, excluded, not_interested,
                trial_modules, status, source, existing_org_id) VALUES (CAST(:id AS uuid), :g, :n, 'club', false, false,
                '[]'::jsonb, 'new', 'grassroots_api', CAST(:org AS uuid))"""),
                {"id": cid, "g": g(), "n": name, "org": club_org_id if registered else None})
            tok = None
            if status:
                tok = "tk" + uuid.uuid4().hex[:14]
                snap = dict(SNAP, club=dict(SNAP["club"], name=name)) if status == "ok" else None
                await s.execute(text("""INSERT INTO club_teaser_snapshots (marketing_club_id, org_guid, token, status, snapshot,
                    version, image_version) VALUES (CAST(:id AS uuid), 'g', :t, :st, CAST(:sn AS jsonb), :v, :iv)"""),
                    {"id": cid, "t": tok, "st": status, "sn": json.dumps(snap) if snap else None, "v": version, "iv": image_version})
            return {"id": cid, "token": tok, "name": name}

        def put_file(token, fmt="card"):
            p = ti.image_path(token, fmt)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(png(ti.FORMATS[fmt]["width"], ti.FORMATS[fmt]["height"]))

        A = await club("Alpha CC", "ok")                                  # good, never drawn
        B = await club("Bravo CC", "ok", image_version=1)                 # drawn, file present
        C = await club("Charlie CC", "junior_only")                       # no snapshot to show
        D = await club("Delta CC")                                        # no snapshot row at all
        E = await club("Echo CC", "ok", image_version=1)                  # marked drawn, file gone
        F = await club("Foxtrot CC", "ok", registered=True)               # already a customer
        for fmt in ti.FORMATS:
            put_file(B["token"], fmt)
        await s.commit()

    # ------------------------------------------------------------------ vars
    print("the merge variables")
    async with Session() as s:
        mcs = {k: await s.get(MarketingClub, v["id"]) for k, v in dict(A=A, B=B, C=C, D=D, E=E).items()}
        v = await ti.vars_by_marketing_club(s, list(mcs.values()))
    va, vb = v[mcs["A"].id], v[mcs["B"].id]
    check("every club gets both keys, so no template goes out with a raw {{teaser_url}}",
          all(set(x) == {"teaser_url", "teaser_image_url"} for x in v.values()) and len(v) == 5)
    check("a club with a good snapshot gets its own page address",
          va["teaser_url"] == f"https://site.test/preview/{A['token']}", va["teaser_url"])
    check("and no picture address until one has been drawn", va["teaser_image_url"] == "")
    check("a drawn club gets the picture address with the draw number on it",
          vb["teaser_image_url"] == f"https://site.test/api/public/teaser/{B['token']}/image/card.png?v=1", vb["teaser_image_url"])
    check("a club marked drawn whose file is gone gets NO picture address (no broken box in an email)",
          v[mcs["E"].id]["teaser_image_url"] == "" and v[mcs["E"].id]["teaser_url"] != "")
    check("a junior-only club and a club with no snapshot get both blank",
          v[mcs["C"].id] == ti.BLANK_TEASER_VARS and v[mcs["D"].id] == ti.BLANK_TEASER_VARS)
    check("the two addresses carry different clubs' tokens (A's page is not B's)",
          A["token"] in va["teaser_url"] and B["token"] not in va["teaser_url"])

    print("the BetterComms path")
    check("both are listed in the editor reference, outreach only",
          {m["name"]: m["marketing_only"] for m in comms.MERGE_VARIABLES if m["name"].startswith("teaser_")}
          == {"teaser_url": True, "teaser_image_url": True})
    outreach = Organisation(id=uuid.UUID(outreach_id), name="BetterCricket", slug="timg-outreach", is_marketing_outreach=True)
    plain = Organisation(id=uuid.UUID(club_org_id), name="A Club", slug="timg-club", is_marketing_outreach=False)
    check("the outreach org sees them in its variable list and a normal club does not",
          {"teaser_url", "teaser_image_url"} <= set(comms._context_var_keys(outreach))
          and not ({"teaser_url", "teaser_image_url"} & set(comms._context_var_keys(plain))))
    check("they cannot be overridden per contact (a typed token would point at another club)",
          "teaser_url" not in comms.EDITABLE_MERGE_KEYS and "teaser_image_url" not in comms.EDITABLE_MERGE_KEYS
          and comms._contact_vars(mcs["B"], {"teaser_url": "https://evil.test", "teaser_image_url": "x"}, vb)["teaser_url"]
          == vb["teaser_url"])
    async with Session() as s:
        tv = await comms._trial_vars(s, mcs["B"])
        none = await comms._trial_vars(s, None)
    check("the preview and test-send path (_trial_vars) carries them alongside the trial figures",
          tv.get("teaser_url") == vb["teaser_url"] and tv.get("teaser_image_url") == vb["teaser_image_url"]
          and "trial_days_left" in tv)
    check("a contact with no directory club has none of it", none == {})

    tpl = comms.OUTREACH_STARTER_TEMPLATES[0]
    ctx = {**comms._marketing_vars(mcs["B"]), **vb}
    _, html, plain_text = comms._render_parts(
        outreach, subject="s", body_html=tpl["html"], utm={"utm_source": "email", "utm_campaign": "teaser"},
        email="x@y.test", name="Sam", unsub_url="https://site.test/api/public/comms/unsubscribe/t", footer="f", extra_vars=ctx)
    check("the template puts the club's picture in a link to its page, with alt text",
          f'src="{vb["teaser_image_url"]}"' in html and 'alt="Bravo CC: your season so far' in html
          and re.search(r'<a href="https://site\.test/preview/%s[^"]*"[^>]*>\s*<img' % B["token"], html) is not None)
    check("the link gets the campaign's UTM tags like any other outbound link",
          "utm_source=email" in html and f"/preview/{B['token']}?utm_source" in html)
    check("no merge token is left unresolved", "{{" not in html and "{{" not in plain_text)
    check("the plain-text part still carries the page address (it has no images or buttons)",
          f"https://site.test/preview/{B['token']}" in plain_text)

    print("the audience rule")
    async with Session() as s:
        for k, mc in (("A", A), ("B", B), ("C", C), ("D", D)):
            await s.execute(text("INSERT INTO comms_contacts (id, organisation_id, email, marketing_club_id, source) "
                                 "VALUES (gen_random_uuid(), CAST(:o AS uuid), :e, CAST(:m AS uuid), 'import')"),
                            {"o": outreach_id, "e": f"{k.lower()}@t.test", "m": mc["id"]})
        await s.commit()

        async def who(states):
            from sqlalchemy import select
            from app.models.db import CommsContact
            clause = seg._teaser_clause(states)
            rows = (await s.execute(select(CommsContact.email).where(CommsContact.organisation_id == uuid.UUID(outreach_id), clause))).scalars().all()
            return sorted(r[0].upper() for r in rows)
        check("'snapshot and picture ready' picks drawn clubs only (A has a snapshot but no picture)",
              await who(["image_ready"]) == ["B"], str(await who(["image_ready"])))
        check("'snapshot ready' still picks both (the old meaning is unchanged)", await who(["ok"]) == ["A", "B"])
        check("an unknown state still drops the rule rather than widening it", seg._teaser_clause(["nonsense"]) is None)

    print("the starter template")
    async with engine.begin() as conn:
        n1 = await comms.seed_outreach_templates(conn)
        n2 = await comms.seed_outreach_templates(conn)
    async with Session() as s:
        rows = (await s.execute(text("SELECT o.slug, count(*) FROM comms_templates t JOIN organisations o ON o.id = t.organisation_id "
                                     "WHERE t.name = :n GROUP BY o.slug"), {"n": tpl["name"]})).all()
    check("it is seeded into the outreach org only", {r[0] for r in rows if r[0].startswith("timg-")} == {"timg-outreach"}, str(rows))
    check("seeding twice adds nothing the second time", n2 == 0 and n1 >= 1, f"{n1} then {n2}")

    # -------------------------------------------------------------- what is due
    print("what is due")
    async with Session() as s:
        due = await ti.due_clubs(s, 50)
        prog = await ti.images_progress(s)
        miss = await ti.due_clubs(s, 50, missing_files=True)
        forced = await ti.due_clubs(s, 50, force=True)
    names = {d["name"] for d in due}
    check("a good, undrawn club is due", "Alpha CC" in names)
    check("a drawn club that is up to date is not", "Bravo CC" not in names and "Echo CC" not in names)
    check("a junior-only club, a club with no snapshot, and a registered customer are never due",
          not ({"Charlie CC", "Delta CC", "Foxtrot CC"} & names), str(names))
    check("the panel counts agree with the list (1 waiting, 2 drawn)", prog["pending"] == len(due) == 1 and prog["ready"] == 2, str(prog))
    check("--missing finds the club marked drawn whose file is gone, and not the one whose file is there",
          {d["name"] for d in miss} == {"Echo CC"}, str({d["name"] for d in miss}))
    check("--force lists up-to-date clubs too (and still never a customer)",
          {"Alpha CC", "Bravo CC", "Echo CC"} <= {d["name"] for d in forced} and "Foxtrot CC" not in {d["name"] for d in forced})
    async with Session() as s:
        check("a limit of zero or less draws nothing, and a huge one is capped",
              await ti.due_clubs(s, 0) == [] and len(await ti.due_clubs(s, 10**9)) <= ti.MAX_BATCH)

    # ----------------------------------------------------------------- drawing
    print("drawing (stand-in renderer)")
    before = sorted(Path(TMP).rglob("*.png"))
    dry = await ti.render_pending(Session, limit=10, apply=False)
    check("a dry run lists what it would draw and writes nothing",
          dry["due"] == 1 and dry["drawn"] == 0 and sorted(Path(TMP).rglob("*.png")) == before)
    stub = StubRenderer()
    out = await ti.render_pending(lambda: Session(), limit=10, renderer_factory=lambda: stub)
    check("it draws the due club in all three formats at their sizes",
          out["drawn"] == 1 and sorted(w for _, w, _ in stub.shots) == sorted(f["width"] for f in ti.FORMATS.values())
          and all(ti.image_path(A["token"], f).is_file() for f in ti.FORMATS), str(out))
    async with Session() as s:
        iv = await s.scalar(text("SELECT image_version FROM club_teaser_snapshots WHERE token = :t"), {"t": A["token"]})
        v2 = await ti.vars_for_marketing_club(s, await s.get(MarketingClub, A["id"]))
    check("the club is marked drawn at the snapshot's version, and its email variable fills in",
          iv == 1 and v2["teaser_image_url"].endswith("image/card.png?v=1"), f"{iv} {v2}")
    check("a second run finds nothing to do", (await ti.render_pending(Session, limit=10, renderer_factory=lambda: StubRenderer()))["due"] == 0)
    check("no half-written temporary file is left behind", not list(Path(TMP).rglob(".*.tmp")))

    async with Session() as s:
        await s.execute(text("UPDATE club_teaser_snapshots SET version = 2 WHERE token = :t"), {"t": A["token"]})
        await s.commit()
        due = await ti.due_clubs(s, 10)
    check("when the figures change (version moves on) the club is due again", [d["name"] for d in due] == ["Alpha CC"])
    check("and until it is redrawn the old picture is still on disk to serve", ti.image_path(A["token"], "card").is_file())

    print("drawing: failure and races")
    G = None
    async with Session() as s:
        for nm in ("Golf CC", "Hotel CC", "India CC"):
            c = await s.execute(text("SELECT 1"))
        await s.commit()
    async with Session() as s:
        extra = []
        for nm in ("Golf CC", "Hotel CC", "India CC"):
            cid = g()
            await s.execute(text("""INSERT INTO marketing_clubs (id, grassroots_guid, name, kind, excluded, not_interested,
                trial_modules, status, source) VALUES (CAST(:id AS uuid), :g, :n, 'club', false, false, '[]'::jsonb, 'new', 'grassroots_api')"""),
                {"id": cid, "g": g(), "n": nm})
            tok = "tk" + uuid.uuid4().hex[:14]
            await s.execute(text("""INSERT INTO club_teaser_snapshots (marketing_club_id, org_guid, token, status, snapshot, version)
                VALUES (CAST(:id AS uuid), 'g', :t, 'ok', CAST(:sn AS jsonb), 1)"""), {"id": cid, "t": tok, "sn": json.dumps(SNAP)})
            extra.append((nm, tok))
        await s.commit()
    tokens = dict(extra)
    stub = StubRenderer(fail={tokens["Hotel CC"]})
    out = await ti.render_pending(Session, limit=20, renderer_factory=lambda: stub, club_id=None)
    check("one club failing does not stop the others in the batch",
          out["status"] == "ok" and len(out["failed"]) == 1 and out["failed"][0]["name"] == "Hotel CC"
          and ti.image_path(tokens["Golf CC"], "card").is_file() and ti.image_path(tokens["India CC"], "card").is_file(), str(out))
    async with Session() as s:
        still = {d["name"] for d in await ti.due_clubs(s, 50)}
    check("the failed club is marked as not drawn and stays due", "Hotel CC" in still and "Golf CC" not in still, str(still))

    async def move_on(token):
        if token == tokens["Hotel CC"]:
            async with Session() as s2:
                await s2.execute(text("UPDATE club_teaser_snapshots SET version = version + 1 WHERE token = :t"), {"t": token})
                await s2.commit()
    await ti.render_pending(Session, limit=20, renderer_factory=lambda: StubRenderer(on_shoot=move_on))
    async with Session() as s:
        row = (await s.execute(text("SELECT version, image_version FROM club_teaser_snapshots WHERE token = :t"),
                               {"t": tokens["Hotel CC"]})).first()
        due_now = {d["name"] for d in await ti.due_clubs(s, 50)}
    check("a snapshot that changes WHILE it is drawn is marked at the older version, so it stays due",
          row[0] > row[1] == 1 and "Hotel CC" in due_now, f"{row} {due_now}")

    gate = asyncio.Event()
    slow = StubRenderer(gate=gate)
    first = asyncio.create_task(ti.render_pending(Session, limit=20, renderer_factory=lambda: slow))
    for _ in range(100):
        if ti.RUN_STATE.get("running"):
            break
        await asyncio.sleep(0.02)
    second = await ti.render_pending(Session, limit=20, renderer_factory=lambda: StubRenderer())
    check("a second batch while one is running is turned away, not run beside it",
          second == {"status": "busy"} and ti.RUN_STATE["running"] is True)
    gate.set()
    await first
    check("and the flag clears when the first finishes", ti.RUN_STATE["running"] is False)

    bad = await ti.render_pending(Session, limit=20, force=True, renderer_factory=lambda: BrokenRenderer())
    check("no Chromium at all is reported as an error the panel can show, never raised",
          bad["status"] == "error" and "no chromium" in bad["error"] and ti.RUN_STATE["running"] is False, str(bad))

    # ------------------------------------------------------------------ routes
    print("the public image route")
    async with Session() as s:
        r = await pt.get_teaser_image(B["token"], "card", s)
        check("a drawn club's picture is served as a PNG, cacheable, not indexable",
              str(r.path) == str(ti.image_path(B["token"], "card")) and r.media_type == "image/png"
              and "max-age" in r.headers["cache-control"] and r.headers["x-robots-tag"] == "noindex")

        async def code(token, fmt):
            try:
                await pt.get_teaser_image(token, fmt, s)
                return 200
            except HTTPException as e:
                return e.status_code
        check("an unknown format is a 404", await code(B["token"], "huge") == 404)
        check("a path-walking format or token is a 404 and never reaches the disk",
              await code(B["token"], "..") == 404 and await code("../../etc/passwd", "card") == 404 and await code("a.b.c.d.e.f.g.h", "card") == 404)
        check("a token that does not exist is a 404", await code("tk" + "z" * 14, "card") == 404)
        put_file(C["token"])
        await s.execute(text("UPDATE club_teaser_snapshots SET image_version = 1 WHERE token = :t"), {"t": C["token"]})
        await s.commit()
        check("a club that is not good (junior-only) is not served even if a file is there", await code(C["token"], "card") == 404)
        check("a club marked drawn whose file is gone is a 404, not a 500", await code(E["token"], "card") == 404)
        put_file(F["token"])
        check("a snapshot never drawn is a 404 even if a stray file exists",
              await code(F["token"], "card") == 404)
        check("a path-shaped format is refused by the path builder as well",
              all(_raises(lambda a=a: ti.image_path(*a)) for a in (("../x", "card"), (B["token"], "../card"), ("", "card"))))

    print("the share card")
    async with Session() as s:
        html_b = await og._teaser_html(B["token"], f"https://site.test/preview/{B['token']}", "https://site.test", s)
        html_a = await og._teaser_html(F["token"], f"https://site.test/preview/{F['token']}", "https://site.test", s)   # F was never drawn
    check("a drawn club shares its own picture, 1200 by 630",
          f"https://site.test/api/public/teaser/{B['token']}/image/card.png?v=1" in html_b
          and 'og:image:width" content="1200"' in html_b and 'og:image:height" content="630"' in html_b)
    check("a club not drawn yet shares the branded cover instead, with no broken image link",
          "/teaser/" not in html_a and "image/card.png" in html_b, re.findall(r'og:image" content="([^"]+)', html_a)[0])
    check("both stay out of search results", 'name="robots" content="noindex' in html_b and 'name="robots" content="noindex' in html_a)

    print("the panel API")
    async with Session() as s:
        blk = await marketing._images_block(s)
    check("the status carries drawn, waiting, running and what the last batch did",
          {"ready", "pending", "stale", "running", "last"} <= set(blk) and blk["running"] is False
          and blk["last"]["status"] == "error", str(blk))
    bt = BackgroundTasks()
    async with Session() as s:
        r = await marketing.teaser_render(marketing.RenderBody(limit=9999), bt, s, None)
    check("starting a batch queues it after the response and caps it at 200",
          r == {"started": True, "limit": 200} and len(bt.tasks) == 1 and bt.tasks[0].args == (200,), str(r))
    ti.RUN_STATE["running"] = True
    bt = BackgroundTasks()
    async with Session() as s:
        r = await marketing.teaser_render(marketing.RenderBody(limit=5), bt, s, None)
    ti.RUN_STATE["running"] = False
    check("pressing it while a batch runs queues nothing", r["started"] is False and not bt.tasks)

    print("the card page and the renderer agree")
    jsx = (Path(__file__).resolve().parents[2] / "frontend/src/pages/marketing/TeaserCard.jsx").read_text()
    m = re.search(r"export const CARD_FORMATS = \{(.*?)\n\}", jsx, re.S)
    front = {k: (int(w), int(h), n == "true") for k, w, h, n in
             re.findall(r"(\w+): \{ width: (\d+), height: (\d+), names: (true|false) \}", m.group(1))} if m else {}
    check("the three formats, their sizes and the names flag are the same on both sides",
          front == {k: (f["width"], f["height"], f["names"]) for k, f in ti.FORMATS.items()}, str(front))
    check("only the email card may print a player's name; both ad sizes leave it off",
          [k for k, f in ti.FORMATS.items() if f["names"]] == ["card"])

    # ---------------------------------------------------------------- Chromium
    print("drawing (real Chromium)")
    exe = os.environ.get("TEASER_CHROMIUM_PATH") or next(iter(sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))), "")
    try:
        import playwright  # noqa: F401
    except ImportError:
        exe = ""
    if not exe:
        skip("real Chromium checks", "no Chromium or Playwright found (set TEASER_CHROMIUM_PATH)")
    else:
        await chromium_checks(exe)

    async with engine.begin() as c:
        await c.execute(text("DELETE FROM comms_contacts WHERE organisation_id = CAST(:o AS uuid)"), {"o": outreach_id})
        await c.execute(text("DELETE FROM comms_templates WHERE organisation_id = CAST(:o AS uuid)"), {"o": outreach_id})
    print(f"\n{PASS} passed, {FAIL} failed, {SKIP} skipped")
    if FAILURES:
        print("FAILED:", *FAILURES, sep="\n  ")
    sys.exit(1 if FAIL else 0)


def _raises(fn) -> bool:
    try:
        fn()
    except ValueError:
        return True
    return False


PAGES = {}


class H(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = PAGES.get(self.path.split("?")[0])
        if body is None:
            self.send_response(404); self.end_headers(); return
        self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *a):  # noqa: D401
        pass


def card_page(w, h, *, ready=True, content_h=None):
    inner = f'<div style="height:{content_h}px;background:#123"></div>' if content_h else ""
    return (f'<!doctype html><body style="margin:0"><div data-card data-card-ready="{1 if ready else 0}" '
            f'style="width:{w}px;height:{h}px;overflow:hidden;background:#0a8">{inner}</div></body>')


async def chromium_checks(exe: str) -> None:
    from PIL import Image
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    tok = "tk" + uuid.uuid4().hex[:14]
    for fmt, f in ti.FORMATS.items():
        PAGES[f"/preview/{tok}/card/{fmt}"] = card_page(f["width"], f["height"])
    try:
        async with ti.ChromiumRenderer(executable_path=exe) as r:
            sizes = await ti.render_club(r, tok, base=base)
        im = {fmt: Image.open(ti.image_path(tok, fmt)) for fmt in ti.FORMATS}
        check("Chromium draws each format to exactly its size",
              all(im[k].size == (f["width"], f["height"]) for k, f in ti.FORMATS.items()), str({k: v.size for k, v in im.items()}))
        check("the files are real PNGs, written under the club's token", all(v.format == "PNG" for v in im.values()) and set(sizes) == set(ti.FORMATS))
        check("and the picture is the card's own colour, not a blank page", im["card"].convert("RGB").getpixel((5, 5)) == (0, 170, 136))

        bad = "tk" + uuid.uuid4().hex[:14]
        PAGES[f"/preview/{bad}/card/card"] = card_page(1200, 630, ready=False)
        old = ti.RENDER_TIMEOUT_MS
        ti.RENDER_TIMEOUT_MS = 2500
        try:
            async with ti.ChromiumRenderer(executable_path=exe) as r:
                try:
                    await ti.render_club(r, bad, base=base, formats=("card",))
                    waited = False
                except Exception:  # noqa: BLE001
                    waited = True
        finally:
            ti.RENDER_TIMEOUT_MS = old
        check("a card that never says it is ready is not saved", waited and not ti.image_path(bad, "card").exists())

        big = "tk" + uuid.uuid4().hex[:14]
        PAGES[f"/preview/{big}/card/card"] = card_page(1200, 630, content_h=900)
        try:
            async with ti.ChromiumRenderer(executable_path=exe) as r:
                await ti.render_club(r, big, base=base, formats=("card",))
            msg = ""
        except RuntimeError as e:
            msg = str(e)
        check("a card whose content does not fit its frame is refused, not saved with the bottom cut off",
              "does not fit" in msg and not ti.image_path(big, "card").exists(), msg)
        check("no temporary files are left in the image directory", not list(Path(TMP).rglob(".*.tmp")))
    finally:
        srv.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
