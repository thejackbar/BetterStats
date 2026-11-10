"""A club whose free trial ran out is shown, and registered, like a club we have never seen.

Before: its public page said "Club page paused" and /trial sent it to a
"request more trial time" form. Now: the public club route answers 404 (the
"not on BetterCricket yet" page, the same as an unknown slug), /trial search no
longer calls it registered or paused, and registering again is allowed, which
re-trials the same club row and leaves its old admins in place.

What does NOT change, and is checked beside it so the rule cannot widen: a club
staff switched off, a cancelled or paused BetterStats, a club with a Stripe
subscription or a paying module, and an org-level master switch that is off all
stay paused and stay "already registered".

Runs the SHIPPED route bodies (`clubs.get_club_by_slug`, `self_serve_trial.search_clubs`,
`prepare_club`, `submit`) against a real Postgres. Only outbound edges are stubbed:
the Cricket Australia lookups, the club onboarding sync kick-off (the same row is
returned, as the real upsert does), the address lookup, the email-verification
table and the admin-list queue. Run it against the previous commit and the checks
fail on exactly what did not exist.

    python -m verification.verify_lapsed_trial_is_new
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload
from starlette.requests import Request

from app.models.db import (
    Base, ClubMembership, Organisation, OrgModuleSubscription, SelfServeAcknowledgement, User,
)
from app.routers import clubs as clubs_router
from app.routers import organisations as orgs_router
from app.routers import self_serve_trial as sst

DB_URL = os.environ.get(
    "VERIFY_DATABASE_URL",
    "postgresql+asyncpg://postgres@127.0.0.1:55432/verify_lapsed",
)

PASS: list[str] = []
FAIL: list[str] = []
NOW = dt.datetime.now(dt.timezone.utc)
DAY = dt.timedelta(days=1)


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} — {detail}")
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  ({detail})'}")


def fake_request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "query_string": b"",
                    "headers": [(b"user-agent", b"verify")], "client": ("203.0.113.9", 1234)})


async def outcome(coro):
    """('ok', value) or ('http', status): a control run that raises reports, it does not crash."""
    try:
        return "ok", await coro
    except HTTPException as e:
        return "http", e.status_code


# slug -> (name, is_active, org-level fields, [(module, status, trial_ends_at)])
SPEC = {
    "live":       ("Live CC",        True,  {}, [("core", "trial", NOW + 5 * DAY)]),
    "ended":      ("Ended CC",       True,  {}, [("core", "trial", NOW - 9 * DAY)]),
    "ended2":     ("Second Ended CC", True, {}, [("core", "trial", NOW - 3 * DAY), ("select", "trial", NOW - 3 * DAY)]),
    "open":       ("Open Trial CC",  True,  {}, [("core", "trial", None)]),
    "inactive":   ("Inactive CC",    False, {}, [("core", "active", None)]),
    "ended_off":  ("Ended Off CC",   False, {}, [("core", "trial", NOW - 9 * DAY)]),
    "cancelled":  ("Cancelled CC",   True,  {}, [("core", "cancelled", None)]),
    "ended_paid": ("Ended Paid CC",  True,  {}, [("core", "trial", NOW - 9 * DAY), ("select", "active", None)]),
    "ended_stripe": ("Ended Stripe CC", True, {"stripe_subscription_id": "sub_test_1"},
                     [("core", "trial", NOW - 9 * DAY)]),
    "ended_master": ("Ended Master CC", True, {"subscription_status": "paused"},
                     [("core", "trial", NOW - 9 * DAY)]),
}
# Registered clubs that must keep reading as "registered and paused" to /trial.
STILL_PAUSED = ("inactive", "ended_off", "cancelled", "ended_paid", "ended_stripe", "ended_master")
LAPSED = ("ended", "ended2")


async def main() -> int:
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        # The lifespan's raw-SQL table (main.py), copied column for column.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS platform_settings (
                id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
                settings JSONB NOT NULL DEFAULT '{}',
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "INSERT INTO platform_settings (id, settings) VALUES (1, '{\"default_trial_days\": 14}') "
            "ON CONFLICT (id) DO NOTHING"))
    Session = async_sessionmaker(engine, expire_on_commit=False)

    ids ={k: uuid.uuid4() for k in list(SPEC) + ["new"]}
    slug_of = {k: SPEC[k][0].lower().replace(" ", "-") for k in SPEC}
    async with Session() as db:
        for key, (name, active, extra, subs) in SPEC.items():
            db.add(Organisation(id=ids[key], name=name, slug=slug_of[key], is_active=active, **extra))
            await db.flush()
            for mod, status, ends in subs:
                db.add(OrgModuleSubscription(
                    id=uuid.uuid4(), organisation_id=ids[key], module_key=mod, status=status,
                    trial_started_at=NOW - 30 * DAY, trial_ends_at=ends))
            admin = User(id=uuid.uuid4(), email=f"admin-{key}@example.com", display_name="Ann Admin",
                         password_hash="x", username=f"admin-{key}")
            db.add(admin)
            await db.flush()
            db.add(ClubMembership(id=uuid.uuid4(), user_id=admin.id, club_id=ids[key], role="club_admin",
                                  is_primary_admin=True))
        await db.commit()

    # ── outbound edges ────────────────────────────────────────────────────────
    async def fake_ca_search(q):
        rows = [{"id": str(ids[k]), "name": SPEC[k][0]} for k in SPEC]
        return rows + [{"id": str(ids["new"]), "name": "Brand New CC"}]
    sst.playhq_client.search_organisations = fake_ca_search

    async def fake_ca_org(org_id):
        return {"id": org_id, "name": "x"}
    sst.playhq_client.get_organisation = fake_ca_org

    async def no_address(db, *, org_id, name):
        return None
    sst._resolve_club_address = no_address

    async def always_verified(db, email):
        return True
    sst.verification.is_verified = always_verified

    import app.services.admin_contact_list as acl
    acl.queue_sync = lambda *_a, **_k: None

    async def reuse_row(db, background_tasks, org_id, org_name="", auto_yearbooks=False):
        # What upsert_organisation does for an id that already has a row: hand it back.
        org = (await db.execute(select(Organisation).where(Organisation.id == uuid.UUID(org_id)))).scalar_one()
        return org, uuid.uuid4(), org_name or org.name
    orgs_router._onboard_club_core = reuse_row

    # ── 1. the public club page ───────────────────────────────────────────────
    print("public club page")

    async def page(key):
        async with Session() as db:
            return await outcome(clubs_router.get_club_by_slug(slug_of[key], fake_request(), db))

    kind, val = await page("live")
    check("control: a live trial's page renders (404 below can be absent)",
          kind == "ok" and val.get("slug") == slug_of["live"], f"{kind} {val}")
    kind, val = await page("open")
    check("control: an open-ended trial's page renders", kind == "ok", f"{kind} {val}")
    for key in LAPSED:
        kind, val = await page(key)
        check(f"{key}: expired trial answers 404, the 'not on BetterCricket yet' page, not 403 'paused'",
              (kind, val) == ("http", 404), f"{kind} {val}")
    for key, why in (("inactive", "switched off by staff"), ("ended_off", "expired trial AND switched off by staff"),
                     ("cancelled", "BetterStats cancelled"), ("ended_paid", "expired Core trial but a paying module"),
                     ("ended_stripe", "expired trial but a Stripe subscription"),
                     ("ended_master", "expired trial but the org-level switch is paused")):
        kind, val = await page(key)
        check(f"{key} ({why}): still 403 paused", (kind, val) == ("http", 403), f"{kind} {val}")

    # ── 2. /trial club search ─────────────────────────────────────────────────
    print("/trial club search")
    async with Session() as db:
        out = {r["name"]: r for r in await sst.search_clubs(q="cc", db=db)}
    flag = lambda n, k: out[n].get(k, "MISSING")
    for key in LAPSED:
        n = SPEC[key][0]
        check(f"{key}: not 'already registered', not paused (so /trial goes to the register wizard)",
              flag(n, "already_registered") is False and flag(n, "already_registered_paused") is False,
              f"registered={flag(n, 'already_registered')} paused={flag(n, 'already_registered_paused')}")
        check(f"{key}: no slug handed back to link to",
              flag(n, "already_registered_slug") is None, str(flag(n, "already_registered_slug")))
    for key in STILL_PAUSED:
        n = SPEC[key][0]
        check(f"{key}: still registered and paused",
              flag(n, "already_registered") is True and flag(n, "already_registered_paused") is True,
              f"registered={flag(n, 'already_registered')} paused={flag(n, 'already_registered_paused')}")
    check("live trial: registered and NOT paused",
          flag("Live CC", "already_registered") is True and flag("Live CC", "already_registered_paused") is False)
    check("never-seen club: not registered",
          flag("Brand New CC", "already_registered") is False)

    # ── 3. step 1 of the wizard (prepare) ─────────────────────────────────────
    print("registration gate (prepare)")

    async def prepare(key):
        async with Session() as db:
            return await outcome(sst.prepare_club(
                sst.PrepareClubRequest(org_id=str(ids[key]), name=SPEC[key][0] if key in SPEC else "Brand New CC"), db))

    for key in LAPSED:
        kind, val = await prepare(key)
        check(f"{key}: may register again (no 'already registered' 409)",
              kind == "ok" and val.get("org_id") == str(ids[key]), f"{kind} {val}")
    kind, val = await prepare("new")
    check("control: a never-seen club may register", kind == "ok", f"{kind} {val}")
    for key in ("live",) + STILL_PAUSED:
        kind, val = await prepare(key)
        check(f"{key}: still refused as already registered", (kind, val) == ("http", 409), f"{kind} {val}")

    # ── 4. registering again onto the same club row ───────────────────────────
    print("submit (register again)")
    async with Session() as db:
        db.add(SelfServeAcknowledgement(id=uuid.uuid4(), email="new.admin@example.com", club_name="Ended CC",
                                        terms_version="x", privacy_version="x", accepted_at=NOW))
        await db.commit()

    def submit_body(key, key_suffix):
        return sst.SubmitRequest(
            idempotency_key=f"verify-{key}-{key_suffix}", org_id=str(ids[key]), name=SPEC[key][0],
            first_name="Nina", last_name="Newadmin", display_name="Nina Newadmin",
            username=f"nina-{key}", email=f"nina-{key}@example.com", mobile_number="0412345678",
            password="Str0ng!Passw0rd#1", confirm_password="Str0ng!Passw0rd#1", modules=["select"])

    async def run_submit(key):
        async with Session() as db:
            # the acknowledgement lookup is by email: give this registrant one
            db.add(SelfServeAcknowledgement(id=uuid.uuid4(), email=f"nina-{key}@example.com",
                                            club_name=SPEC[key][0], terms_version="x", privacy_version="x",
                                            accepted_at=NOW))
            await db.commit()
        async with Session() as db:
            return await outcome(sst.submit(submit_body(key, "1"), BackgroundTasks(), db))

    kind, val = await run_submit("ended")
    check("ended: the registration goes through", kind == "ok" and val.get("status") == "completed", f"{kind} {val}")

    async with Session() as db:
        org = (await db.execute(
            select(Organisation).where(Organisation.id == ids["ended"])
            .options(selectinload(Organisation.module_subscriptions)))).scalar_one()
        subs = {s.module_key: s for s in org.module_subscriptions}
        core = subs.get("core")
        check("same club row, not a duplicate",
              (await db.execute(select(text("count(*)")).select_from(Organisation).where(
                  Organisation.slug.like("ended-cc%")))).scalar() == 1)
        check("BetterStats trial restarted and runs into the future",
              core is not None and core.status == "trial" and core.trial_ends_at and core.trial_ends_at > NOW + 10 * DAY,
              f"{core and (core.status, core.trial_ends_at)}")
        check("the module picked on the form is trialling too",
              subs.get("select") is not None and subs["select"].status == "trial"
              and subs["select"].trial_ends_at > NOW + 10 * DAY, str(subs.get("select")))
        check("its public page is live again",
              clubs_router._public_blocked(org) is False)
        members = (await db.execute(select(ClubMembership).where(ClubMembership.club_id == ids["ended"]))).scalars().all()
        old_admin = next((m for m in members if m.user_id and str(m.user_id) != ""
                          and m.is_primary_admin), None)
        check("the earlier admin keeps their membership and stays primary (nothing of theirs removed)",
              old_admin is not None and len(members) == 2, f"{len(members)} memberships")
    kind, val = await page("ended")
    check("route now renders the page", kind == "ok", f"{kind} {val}")

    for key in ("inactive", "ended_stripe"):
        async with Session() as db:
            db.add(SelfServeAcknowledgement(id=uuid.uuid4(), email=f"nina-{key}@example.com",
                                            club_name=SPEC[key][0], terms_version="x", privacy_version="x",
                                            accepted_at=NOW))
            await db.commit()
        async with Session() as db:
            kind, val = await outcome(sst.submit(submit_body(key, "1"), BackgroundTasks(), db))
        check(f"{key}: a registration is still refused (409), nothing created",
              (kind, val) == ("http", 409), f"{kind} {val}")
        async with Session() as db:
            made = (await db.execute(select(User).where(User.username == f"nina-{key}"))).scalars().all()
        check(f"{key}: no user was created by the refused registration", not made, str(made))

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print("  FAILED:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
