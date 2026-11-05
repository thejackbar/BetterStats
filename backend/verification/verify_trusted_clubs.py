"""Verification for the public "Trusted by clubs at" list, against a real Postgres.

The strip on the home page and /trial is a customer list on a public marketing
page, so the checks that matter most are about who must NOT be on it: a club
still on a trial, a lapsed or cancelled one, one behind an access PIN, an
archived one, the marketing-outreach org, a club with no crest. A paying club
that is wrongly left off is a small miss. A club that never agreed to be named
and is, is the failure this guards.

Every "X is absent" check is paired with a check that a club which should be
present IS present, so a route that returns nothing at all cannot pass.

Runs the SHIPPED route body; never a re-implementation.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/verify_trusted?host=/tmp&port=5439 \
  python verification/verify_trusted_clubs.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Behind a guard so a CONTROL RUN against a build without the route REPORTS it
# instead of dying on the first ImportError.
MISSING: list[str] = []
try:
    from app.routers.public_trusted_clubs import trusted_clubs
except ImportError as exc:  # pragma: no cover - control run only
    trusted_clubs = None
    MISSING.append(f"public_trusted_clubs route body ({exc})")

from app.config.settings import settings
from app.models.db import Base, Organisation, OrgModuleSubscription

DB = os.environ["DATABASE_URL"]
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


class FakeResponse:
    def __init__(self):
        self.headers = {}


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32   # any non-empty bytes: the route only checks length


async def club(session, *, name, slug, core="active", logo=PNG, pin=None, archived=False,
               active=True, outreach=False, master="active", started_days_ago=10, modules=None):
    """One club, with its BetterStats (Core) row in the given state."""
    org = Organisation(
        id=uuid.uuid4(), name=name, slug=slug, is_active=active,
        archived_at=datetime.now(timezone.utc) if archived else None,
        access_pin_hash=pin, is_marketing_outreach=outreach, subscription_status=master,
        logo_data=logo, logo_mime="image/png" if logo else None,
    )
    session.add(org)
    await session.flush()
    rows = modules if modules is not None else ([("core", core)] if core else [])
    for key, status in rows:
        session.add(OrgModuleSubscription(
            organisation_id=org.id, module_key=key, status=status,
            started_at=datetime.now(timezone.utc) - timedelta(days=started_days_ago),
        ))
    await session.flush()
    return org


async def call() -> tuple[dict, FakeResponse]:
    resp = FakeResponse()
    async with Session() as s:
        body = await trusted_clubs(resp, s)
    return body, resp


async def main() -> None:
    print("=== trusted clubs list ===")
    if MISSING:
        for item in MISSING:
            check(f"the feature is present: {item}", False, "not importable")
        print(f"\n{PASS} passed, {FAIL} failed")
        sys.exit(1)

    # The whole ORM schema: organisations points at users, and a harness table
    # that merely looks right is worse than none.
    # (organisations and users point at each other, which create_all can build
    # but drop_all cannot order, so the schema is reset directly.)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)

    settings.trusted_clubs_exclude = ""
    async with Session() as s:
        newest = await club(s, name="Newest Paying CC", slug="newest-paying", started_days_ago=2)
        older = await club(s, name="Older Paying CC", slug="older-paying", started_days_ago=200)
        await club(s, name="On Trial CC", slug="on-trial", core="trial")
        await club(s, name="Lapsed CC", slug="lapsed", core="paused")
        await club(s, name="Cancelled CC", slug="cancelled", core="cancelled")
        await club(s, name="Past Due CC", slug="past-due", core="past_due")
        await club(s, name="Addon Only CC", slug="addon-only", modules=[("select", "active"), ("core", "trial")])
        await club(s, name="No Core Row CC", slug="no-core-row", core=None)
        await club(s, name="No Crest CC", slug="no-crest", logo=None)
        await club(s, name="Empty Crest CC", slug="empty-crest", logo=b"")
        await club(s, name="Locked CC", slug="locked", pin="$2b$12$abcdefghijklmnopqrstuv")
        await club(s, name="Archived CC", slug="archived", archived=True)
        await club(s, name="Inactive CC", slug="inactive", active=False)
        await club(s, name="Outreach Org", slug="outreach", outreach=True)
        await club(s, name="Switched Off CC", slug="switched-off", master="paused")
        await club(s, name="No Slug CC", slug=None)
        await club(s, name="Excluded By Setting CC", slug="excluded-by-setting", started_days_ago=250)
        await s.commit()

    body, resp = await call()
    slugs = [c["slug"] for c in body["clubs"]]
    print(f"  (route returned: {slugs})")

    print("-- who is on it")
    check("a paying club IS listed (newest)", "newest-paying" in slugs)
    check("a second paying club IS listed (older)", "older-paying" in slugs)
    check("newest subscriber first", slugs[:2] == ["newest-paying", "older-paying"], str(slugs))

    print("-- who must not be on it")
    check("a club on a trial is not listed", "on-trial" not in slugs)
    check("a paused club is not listed", "lapsed" not in slugs)
    check("a cancelled club is not listed", "cancelled" not in slugs)
    check("a past_due club is not listed (grace period, not clearly paying)", "past-due" not in slugs)
    check("a club paying only for an add-on, with Core on trial, is not listed", "addon-only" not in slugs)
    check("a club with no Core row is not listed", "no-core-row" not in slugs)
    check("a club with no crest is not listed", "no-crest" not in slugs)
    check("a club with an empty crest is not listed", "empty-crest" not in slugs)
    check("a PIN-locked club is not listed", "locked" not in slugs)
    check("an archived club is not listed", "archived" not in slugs)
    check("an inactive club is not listed", "inactive" not in slugs)
    check("the marketing-outreach org is not listed", "outreach" not in slugs)
    check("a club whose whole-account switch is off is not listed", "switched-off" not in slugs)
    check("a club with no public slug is not listed", None not in slugs and "" not in slugs)

    print("-- the exclusion setting")
    check("a club not yet excluded IS listed", "excluded-by-setting" in slugs)
    settings.trusted_clubs_exclude = " Excluded-By-Setting , some-other "
    body2, _ = await call()
    slugs2 = [c["slug"] for c in body2["clubs"]]
    check("an excluded club is dropped (case and spaces ignored)", "excluded-by-setting" not in slugs2, str(slugs2))
    check("excluding one club leaves the paying ones", "newest-paying" in slugs2 and "older-paying" in slugs2)
    settings.trusted_clubs_exclude = ""

    print("-- what leaves the route")
    first = body["clubs"][0]
    check("only slug, name and logo come back", set(first) == {"slug", "name", "logo"}, str(set(first)))
    check("the logo is the club's own crest path", first["logo"] == f"/api/images/organisations/{newest.id}/logo", first["logo"])
    check("the club's name is the public name", first["name"] == "Newest Paying CC")
    check("the response says it may be cached", "max-age" in resp.headers.get("Cache-Control", ""), str(resp.headers))
    check("the list is capped", len(body["clubs"]) <= 60)

    print("-- the cap")
    async with Session() as s:
        for i in range(70):
            await club(s, name=f"Bulk {i:02d} CC", slug=f"bulk-{i:02d}", started_days_ago=300 + i)
        await s.commit()
    body3, _ = await call()
    check("with 70 more paying clubs the list stops at 60", len(body3["clubs"]) == 60, str(len(body3["clubs"])))
    kept = [c["slug"] for c in body3["clubs"]]
    check("the newest are the ones kept", kept[:2] == ["newest-paying", "older-paying"], str(kept[:3]))
    check("a long-standing club inside the cap is kept (it could be present)", "bulk-00" in kept)
    check("the oldest subscriber is the one dropped", "bulk-69" not in kept)

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await engine.dispose()

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        print("FAILED:", *FAILURES, sep="\n  - ")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
