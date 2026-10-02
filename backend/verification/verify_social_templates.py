"""BetterSocials saved templates, one row each (migration 313).

Runs the SHIPPED route bodies (imported, nothing retyped) against a real
Postgres: a template saved, updated in place and deleted on its own, two admins
saving at once not overwriting each other (the reported loss), one club never
seeing or touching another's, every refusal, the size and count limits, and the
import that carries older browser-only templates across without overwriting.

    python -m verification.verify_social_templates
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_URL = os.environ.get(
    "VERIFY_DATABASE_URL",
    "postgresql+asyncpg://postgres:x@127.0.0.1:5432/verify_social_templates",
)
os.environ["DATABASE_URL"] = DB_URL

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.models.db import Base, Organisation, User  # noqa: E402

try:
    from app.routers import social_media as sm  # noqa: E402
    from app.services import social_template_ddl as ddl  # noqa: E402
    HAVE = hasattr(sm, "save_template") and hasattr(sm, "import_templates")
except Exception as exc:  # pragma: no cover - control run
    print(f"!! the feature is not importable: {exc}")
    sm = ddl = None
    HAVE = False

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} — {detail}")
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  ({detail})'}")


class Req:
    """The one thing the routes read off a Request: its body."""
    def __init__(self, payload):
        self._b = payload if isinstance(payload, (bytes, bytearray)) else json.dumps(payload).encode()

    async def body(self):
        return self._b


def tpl(name="Match day", template_id="T1", **extra):
    return {"name": name, "templateId": template_id, "custom": False,
            "style": {"palette": "club", "dark": True, "font": "barlow", "bg": "none"},
            "blank": None, "layers": None, **extra}


async def refused(coro, status):
    try:
        await coro
    except HTTPException as e:
        return e.status_code == status, e.status_code
    except Exception as e:  # noqa: BLE001
        return False, repr(e)
    return False, "no error raised"


async def main() -> int:
    if not HAVE:
        check("the feature exists", False, "save_template / import_templates not found")
        return 1

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        # Lifespan DDL (main.py), not on the ORM model: the shared "not played" predicate reads it.
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        for _ in range(3):
            for st in ddl.STATEMENTS:
                await conn.execute(text(st))
    check("the DDL applies three times over", True)

    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        A = Organisation(id=uuid.uuid4(), name="Alpha CC", slug="alpha")
        B = Organisation(id=uuid.uuid4(), name="Bravo CC", slug="bravo")
        u1 = User(id=uuid.uuid4(), username="one", display_name="One")
        u2 = User(id=uuid.uuid4(), username="two", display_name="Two")
        db.add_all([A, B, u1, u2])
        await db.commit()
    A_id, B_id = A.id, B.id

    async def call(fn, *args, org=A, user=u1, **kw):
        async with Session() as db:
            return await fn(*args, current_user=user, club=org, db=db, **kw)

    async def listed(org=A):
        return await call(sm.list_templates, org=org)

    # ── save, list, update in place ───────────────────────────────────────
    check("a new club has no templates", await listed() == [])
    out = await call(sm.save_template, "tpl_a1", Req(tpl("Match day", key="tpl_a1")))
    check("saving returns the template under its own key and name",
          out["key"] == "tpl_a1" and out["name"] == "Match day" and out["templateId"] == "T1", str(out))
    check("its Style rides along", (out.get("style") or {}).get("palette") == "club")
    rows = await listed()
    check("a fresh session lists it", [r["key"] for r in rows] == ["tpl_a1"])

    out = await call(sm.save_template, "tpl_a1", Req(tpl("Match day v2", template_id="T3")))
    rows = await listed()
    check("saving the same key updates it in place, no duplicate", len(rows) == 1, str(len(rows)))
    check("the name and layout changed", rows[0]["name"] == "Match day v2" and rows[0]["templateId"] == "T3")

    blank = [{"id": "b1", "type": "text", "text": "Hello", "x": 10, "y": 20}]
    out = await call(sm.save_template, "tpl_blank", Req(tpl("Canvas", template_id="BL1", blank=blank,
                                                            layers={"order": ["t:div#1"], "hidden": []})))
    got = next(r for r in await listed() if r["key"] == "tpl_blank")
    check("a Blank Canvas layout comes back whole", got["blank"] == blank)
    check("the layer order comes back whole", got["layers"] == {"order": ["t:div#1"], "hidden": []})

    # ── the reported loss: two admins saving at once ──────────────────────
    await call(sm.save_template, "tpl_u1", Req(tpl("From admin one")), user=u1)
    await call(sm.save_template, "tpl_u2", Req(tpl("From admin two")), user=u2)
    keys = {r["key"] for r in await listed()}
    check("two admins' templates both survive, neither overwrites the other",
          {"tpl_u1", "tpl_u2"} <= keys, str(keys))
    await call(sm.save_template, "tpl_u1", Req(tpl("Admin one, edited")), user=u1)
    check("editing one leaves the other exactly as it was",
          next(r for r in await listed() if r["key"] == "tpl_u2")["name"] == "From admin two")

    ev = {"facts": {"title": "SEASON LAUNCH"}, "preset": "curry", "motif": "star", "bg": None, "bgOpacity": 0.85}
    await call(sm.save_template, "tpl_event", Req(tpl("Season launch", template_id="EV1", event=ev)))
    got = next(r for r in await listed() if r["key"] == "tpl_event")
    check("an event poster's wording, motif and photo come back whole", got.get("event") == ev, str(got.get("event")))
    ok, got_status = await refused(call(sm.save_template, "tpl_x", Req(tpl("x", event=["no"]))), 422)
    check("refused: event content that is not an object", ok, str(got_status))

    # ── club isolation ────────────────────────────────────────────────────
    check("another club sees none of them", await listed(B) == [])
    await call(sm.save_template, "tpl_a1", Req(tpl("Bravo's own")), org=B)
    check("the same key in another club is its own template",
          next(r for r in await listed(B) if r["key"] == "tpl_a1")["name"] == "Bravo's own"
          and next(r for r in await listed() if r["key"] == "tpl_a1")["name"] == "Match day v2")
    res = await call(sm.delete_template, "tpl_u2", org=B)
    check("another club cannot delete it", res["removed"] == 0
          and any(r["key"] == "tpl_u2" for r in await listed()))

    # ── delete ────────────────────────────────────────────────────────────
    before = len(await listed())
    res = await call(sm.delete_template, "tpl_u2")
    check("delete removes exactly that one", res["removed"] == 1 and len(await listed()) == before - 1)
    res = await call(sm.delete_template, "tpl_u2")
    check("deleting it again is a quiet no-op", res["removed"] == 0)

    # ── sanitising ────────────────────────────────────────────────────────
    out = await call(sm.save_template, "tpl_clean",
                     Req(tpl("  A   very    spaced   name  ", evil="<script>", updated_at="x")))
    check("whitespace in a name is collapsed", out["name"] == "A very spaced name", out["name"])
    check("fields the editor does not own are dropped", "evil" not in out)
    out = await call(sm.save_template, "tpl_long", Req(tpl("N" * 200)))
    check("a long name is cut to the limit", len(out["name"]) == sm.TEMPLATE_NAME_MAX, str(len(out["name"])))

    # ── refusals ──────────────────────────────────────────────────────────
    async def put(key, body):
        return await refused(call(sm.save_template, key, Req(body)), 422)

    for label, key, body in [
        ("no name", "tpl_x", tpl("")),
        ("a blank name", "tpl_x", tpl("   ")),
        ("no base layout", "tpl_x", {"name": "x"}),
        ("a key with a slash", "a/b", tpl("x")),
        ("a key that does not match the address", "tpl_x", tpl("x", key="tpl_other")),
        ("style that is not an object", "tpl_x", tpl("x", style=[1])),
        ("blocks that are not a list", "tpl_x", tpl("x", blank="nope")),
        ("layers that are not an object", "tpl_x", tpl("x", layers=[1])),
        ("a body that is not an object", "tpl_x", ["x"]),
    ]:
        ok, got_status = await put(key, body)
        check(f"refused: {label}", ok, str(got_status))
    ok, got_status = await refused(call(sm.save_template, "tpl_x", Req(b"{not json")), 422)
    check("refused: a body that is not JSON", ok, str(got_status))
    big = tpl("Big", blank=[{"id": str(i), "type": "text", "text": "x" * 500} for i in range(700)])
    ok, got_status = await refused(call(sm.save_template, "tpl_big", Req(big)), 413)
    check("refused: a template past 256 KB", ok, str(got_status))
    check("a refused save stored nothing", not any(r["key"] in ("tpl_x", "tpl_big") for r in await listed()))

    # ── count limit ───────────────────────────────────────────────────────
    async with engine.begin() as conn:
        n = (await conn.execute(text("SELECT COUNT(*) FROM social_templates WHERE organisation_id=:o"),
                                {"o": A_id})).scalar_one()
        for i in range(sm.TEMPLATE_MAX_PER_CLUB - n):
            await conn.execute(text(
                "INSERT INTO social_templates (organisation_id, key, name, data) VALUES (:o, :k, 'fill', '{\"templateId\":\"T1\"}')"),
                {"o": A_id, "k": f"fill_{i}"})
    ok, got_status = await refused(call(sm.save_template, "tpl_over", Req(tpl("One too many"))), 409)
    check("a club at its limit cannot add another", ok, str(got_status))
    out = await call(sm.save_template, "tpl_a1", Req(tpl("Still editable at the limit")))
    check("but can still update one it already has", out["name"] == "Still editable at the limit")

    # ── import of older, browser-only templates ───────────────────────────
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM social_templates WHERE organisation_id=:o AND key LIKE 'fill_%'"), {"o": A_id})
    await call(sm.save_template, "tpl_kept", Req(tpl("Edited on the server")))
    legacy = {"templates": [
        {**tpl("Old local copy"), "key": "tpl_kept"},
        {**tpl("Brought across"), "key": "tpl_old1"},
        {**tpl("Also brought"), "key": "tpl_old2", "blank": [{"id": "z", "type": "shape"}]},
        {"key": "tpl_bad"},                                   # no name / layout
        {**tpl("Bad key"), "key": "no spaces allowed"},
    ]}
    res = await call(sm.import_templates, Req(legacy))
    check("import adds the templates the club does not have", sorted(res["added"]) == ["tpl_old1", "tpl_old2"], str(res))
    check("import never overwrites one already saved",
          next(r for r in await listed() if r["key"] == "tpl_kept")["name"] == "Edited on the server")
    check("import reports what it skipped and why",
          {s["key"] for s in res["skipped"]} >= {"tpl_kept", "tpl_bad"} and all(s["reason"] for s in res["skipped"]), str(res["skipped"]))
    check("an imported Blank Canvas layout survives",
          next(r for r in await listed() if r["key"] == "tpl_old2")["blank"] == [{"id": "z", "type": "shape"}])
    res = await call(sm.import_templates, Req(legacy))
    check("sending the import twice adds nothing", res["added"] == [], str(res))
    ok, got_status = await refused(call(sm.import_templates, Req({"nope": 1})), 422)
    check("import refuses a body with no template list", ok, str(got_status))

    # ── wiring ────────────────────────────────────────────────────────────
    root = Path(__file__).resolve().parents[1]
    mig = (root / "alembic/versions/313_social_templates.py").read_text()
    check("migration 313 follows 312 and runs the shared statements",
          'down_revision = "312"' in mig and "social_template_ddl import STATEMENTS" in mig)
    check("the lifespan mirror runs the same statements",
          "social_template_ddl import STATEMENTS" in (root / "app/main.py").read_text())
    check("the football schema mirror replays it too",
          "social_template_ddl" in (root / "app/services/afl/cricket_schema_mirror.py").read_text())
    routes = {(m, r.path) for r in sm.router.routes for m in getattr(r, "methods", [])}
    check("every template route is on the socials-gated router",
          {("GET", "/admin/social/templates"), ("PUT", "/admin/social/templates/{key}"),
           ("DELETE", "/admin/social/templates/{key}"), ("POST", "/admin/social/templates/import")} <= routes)
    gated = [r for r in sm.router.routes if "/templates" in getattr(r, "path", "")]
    check("each one requires the BetterSocials module", all(r.dependencies for r in gated))

    # a deleted club takes its templates with it
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM organisations WHERE id=:o"), {"o": B_id})
        left = (await conn.execute(text("SELECT COUNT(*) FROM social_templates WHERE organisation_id=:o"), {"o": B_id})).scalar_one()
    check("a deleted club's templates go with it", left == 0)

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print("  FAILED:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
