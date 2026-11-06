"""render_club_teasers --returning-only draws just the archived and lapsed-trial clubs.

After the returning-clubs re-crawl, the pictures for those clubs were still
undrawn because the render script took "whatever is due" in no set order and had
no way to name the group. ``returning_only`` narrows the picture queue to clubs
behind an archived or expired-trial BetterCricket club, through the same
constant the crawl uses. Runs the shipped ``due_clubs``, ``render_pending`` and
the script's own ``main`` against a real Postgres, with the browser swapped for a
stub that records which tokens it was asked to draw.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \
  python verification/verify_render_returning_only.py
"""
from __future__ import annotations

import asyncio
import contextlib
import io
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")
os.environ["TEASER_IMAGE_DIR"] = tempfile.mkdtemp(prefix="retonly-")

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import Base
from app.services import club_teaser as ct, club_teaser_images as ti
from app.services.club_teaser_ddl import STATEMENTS

DB = os.environ["DATABASE_URL"]
if "verify" not in (make_url(DB).database or "").lower():
    print("REFUSING to run: not a verification database. These checks delete rows.")
    sys.exit(2)
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)
PASS = FAIL = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")


def g() -> str:
    return str(uuid.uuid4())


async def main() -> None:
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
        for s in STATEMENTS:
            await c.execute(text(s))
        await c.execute(text("DELETE FROM club_teaser_snapshots"))
        await c.execute(text("DELETE FROM marketing_clubs"))
        await c.execute(text("DELETE FROM org_module_subscriptions WHERE organisation_id IN "
                             "(SELECT id FROM organisations WHERE slug LIKE 'ro-%')"))
        await c.execute(text("DELETE FROM organisations WHERE slug LIKE 'ro-%'"))

    tokens: dict[str, str] = {}
    async with Session() as s:
        async def org(key, *, archived=False, rows=(), stripe=False):
            oid = g()
            await s.execute(text(
                "INSERT INTO organisations (id, name, slug, is_active, archived_at, stripe_subscription_id) "
                "VALUES (CAST(:i AS uuid), :n, :s, true, CASE WHEN :a THEN now() ELSE NULL END, :st)"),
                {"i": oid, "n": key, "s": f"ro-{key}", "a": archived, "st": "sub_1" if stripe else None})
            for i, (status, days) in enumerate(rows):
                await s.execute(text(
                    "INSERT INTO org_module_subscriptions (id, organisation_id, module_key, status, trial_ends_at) "
                    "VALUES (gen_random_uuid(), CAST(:o AS uuid), :m, :st, "
                    "CASE WHEN CAST(:d AS int) IS NULL THEN NULL ELSE now() + (CAST(:d AS int) * interval '1 day') END)"),
                    {"o": oid, "m": f"mod{i}", "st": status, "d": days})
            return oid

        async def club(key, name, org_id=None):
            cid, tok, guid = g(), "tk" + uuid.uuid4().hex[:14], g()
            await s.execute(text(
                "INSERT INTO marketing_clubs (id, grassroots_guid, name, kind, excluded, not_interested, trial_modules, "
                "status, source, existing_org_id) VALUES (CAST(:id AS uuid), :g, :n, 'club', false, false, '[]'::jsonb, "
                "'new', 'grassroots_api', CAST(:o AS uuid))"), {"id": cid, "g": guid, "n": name, "o": org_id})
            body = {"schema": ct.SCHEMA_VERSION, "club": {"name": name, "ca_org_id": g()}, "season": {"name": "S"},
                    "totals": {"matches": 12}, "batting": [{"name": "A. Bat", "runs": 100}], "bowling": []}
            await s.execute(text(
                "INSERT INTO club_teaser_snapshots (marketing_club_id, org_guid, token, status, snapshot, version, "
                "image_version, next_pull_at) VALUES (CAST(:id AS uuid), :g, :t, 'ok', CAST(:sn AS jsonb), 1, NULL, "
                "now() + interval '30 days')"), {"id": cid, "g": guid, "t": tok, "sn": json.dumps(body)})
            tokens[name] = tok

        await club("p", "Plain Prospect CC")
        await club("a", "Archived CC", await org("arch", archived=True, rows=[("trial", -5)]))
        await club("l", "Lapsed CC", await org("lapsed", rows=[("trial", -10), ("trial", -3)]))
        await club("t", "Trialling CC", await org("trialling", rows=[("trial", 5)]))
        await club("pay", "Paying CC", await org("paying", rows=[("active", None)]))
        await club("pl", "Plain Two CC")
        await s.commit()

    by_token = {v: k for k, v in tokens.items()}

    print("which clubs are due")
    async with Session() as s:
        everyone = {d["name"] for d in await ti.due_clubs(s, 100)}
        group = {d["name"] for d in await ti.due_clubs(s, 100, returning_only=True)}
    check("with no option, the plain prospects are due as well (the baseline: the queue is mixed)",
          {"Plain Prospect CC", "Plain Two CC", "Archived CC", "Lapsed CC"} <= everyone, str(everyone))
    check("a live customer is never due", not ({"Trialling CC", "Paying CC"} & everyone), str(everyone))
    check("returning_only keeps exactly the archived and the lapsed-trial club", group == {"Archived CC", "Lapsed CC"}, str(group))

    print("drawing")
    drawn: list[str] = []

    async def fake_render_club(renderer, token, base=None):
        drawn.append(by_token[token])
        return {"card": 10, "feed": 10, "story": 10}

    class FakeRenderer:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    real = ti.render_club
    ti.render_club = fake_render_club
    try:
        dry = await ti.render_pending(Session, limit=50, apply=False, returning_only=True)
        check("a dry run lists the group and draws nothing", {c["name"] for c in dry["clubs"]} == {"Archived CC", "Lapsed CC"} and not drawn)
        out = await ti.render_pending(Session, limit=50, apply=True, returning_only=True, renderer_factory=FakeRenderer)
        check("drawing with returning_only draws the archived and the lapsed club, and nobody else",
              set(drawn) == {"Archived CC", "Lapsed CC"} and out["drawn"] == 2, f"{drawn} {out}")
        async with Session() as s:
            iv = {r[0]: r[1] for r in (await s.execute(text(
                "SELECT mc.name, t.image_version FROM club_teaser_snapshots t JOIN marketing_clubs mc "
                "ON mc.id = t.marketing_club_id"))).all()}
        check("only those two are marked drawn; the plain prospects are still waiting",
              iv["Archived CC"] == 1 and iv["Lapsed CC"] == 1 and iv["Plain Prospect CC"] is None and iv["Plain Two CC"] is None, str(iv))

        # The script itself.
        from app.scripts import render_club_teasers as script
        async with Session() as s:
            await s.execute(text("UPDATE club_teaser_snapshots SET image_version = NULL"))
            await s.commit()
        drawn.clear()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = await script.main(["--returning-only"])
        dry_out = buf.getvalue()
        check("the script's dry run with --returning-only names the two clubs and no others",
              rc == 0 and "2 club(s) due" in dry_out and "Archived CC" in dry_out and "Lapsed CC" in dry_out
              and "Plain" not in dry_out, dry_out)
        buf = io.StringIO()
        ti_factory = ti.ChromiumRenderer
        ti.ChromiumRenderer = FakeRenderer
        try:
            with contextlib.redirect_stdout(buf):
                rc = await script.main(["--returning-only", "--apply"])
        finally:
            ti.ChromiumRenderer = ti_factory
        check("--apply with --returning-only draws just those two", rc == 0 and set(drawn) == {"Archived CC", "Lapsed CC"}, f"{drawn} {buf.getvalue()}")
        drawn.clear()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            await script.main([])
        check("without the option the script's queue still includes the plain prospects (nothing else changed)",
              "Plain Prospect CC" in buf.getvalue() or "4 club(s) due" in buf.getvalue(), buf.getvalue())
    finally:
        ti.render_club = real

    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
