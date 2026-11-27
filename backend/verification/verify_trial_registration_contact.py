"""A /trial registration puts the new club admin on BetterCricket's internal Comms contact list.

Asked for: when someone signs up for a trial (a Meta ad click or a website visit) they become the
club's admin, and we know which club. If they are not already a Contact on the Super Admin internal
BetterAdmin Comms list, they must be added as part of a successful registration, so they show up in
the Segment and Static lists in BetterComms.

The hook that does this already exists (`admin_contact_list.queue_sync`, called by
`self_serve_trial.submit` after its commit), but nothing exercised it on the real registration path:
`verify_trial_two_field_signup` stubs it out. So this runs the SHIPPED public `submit` (the route
body, then `self_serve_trial.submit`) against a real Postgres with the hook LIVE, runs the
background tasks the response would have started (the CRM sync that creates the club's Directory
row), and then reads back what BetterComms holds.

The case that matters most is a club that is NOT in the Clubs Directory yet. Onboarding links an
existing Directory row, but a club the crawl never found only gets its row from the CRM background
task, which runs AFTER the admin-list sync. The contact was therefore filed with no club, and
nothing ever linked it, so `{{club}}` / `{{trial_days_left}}` rendered blank and a "named club"
segment never matched them.

Only outbound edges are stubbed (Cricket Australia, the address lookup, the email verification
table, the usage beacon, the sync kick-off inside onboarding).

    python -m verification.verify_trial_registration_contact
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_URL = os.environ.get(
    "VERIFY_DATABASE_URL", "postgresql+asyncpg://postgres@127.0.0.1:55432/verify_trial_reg_contact")
# Set before app.models.db is imported: run_sync and the CRM task open their own sessions
# through async_session_maker, which is built from settings at import time.
os.environ["DATABASE_URL"] = DB_URL

from fastapi import BackgroundTasks, HTTPException, Response  # noqa: E402
from sqlalchemy import func, select, text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from starlette.requests import Request  # noqa: E402

import app.models.db as mdb  # noqa: E402
from app.models.db import (  # noqa: E402
    Base, ClubMembership, CommsContact, CommsSegment, CommsSegmentMember, MarketingClub,
    MarketingClubContact, Organisation, SelfServeAcknowledgement, User,
)
from app.routers import organisations as orgs_router  # noqa: E402
from app.routers import public_self_serve as pss  # noqa: E402
from app.routers import self_serve_trial as sst  # noqa: E402
from app.services import admin_contact_list as acl  # noqa: E402
from app.services import comms_segments, crm_rules  # noqa: E402

PASS: list[str] = []
FAIL: list[str] = []
NOW = dt.datetime.now(dt.timezone.utc)
PW = "Str0ng!Passw0rd#1"


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} — {detail}")
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  ({detail})'}")


def fake_request(ip: str) -> Request:
    return Request({"type": "http", "method": "POST", "path": "/", "query_string": b"",
                    "headers": [(b"user-agent", b"verify"), (b"x-real-ip", ip.encode())],
                    "client": (ip, 1234)})


async def safe(coro):
    """The reply, or a marker when the route refuses: a control run REPORTS, it does not crash."""
    try:
        return await coro
    except HTTPException as e:
        return {"_http": e.status_code, "_detail": e.detail}
    except Exception as e:  # noqa: BLE001 - a control run must report, not crash
        return {"_error": f"{type(e).__name__}: {e}"[:200]}


USAGE_DDL = """CREATE TABLE IF NOT EXISTS usage_events (
    id BIGSERIAL PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), event_type TEXT NOT NULL DEFAULT 'api',
    method TEXT NOT NULL, path TEXT NOT NULL, route TEXT, status INTEGER NOT NULL DEFAULT 0, duration_ms INTEGER,
    user_id UUID, org_id UUID, ip_hash TEXT, user_agent TEXT, referer TEXT, metadata JSONB DEFAULT '{}',
    visitor_id UUID)"""


async def main() -> int:
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(USAGE_DDL))
        await conn.execute(text("""CREATE TABLE IF NOT EXISTS platform_settings (
            id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1), settings JSONB NOT NULL DEFAULT '{}',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"""))
        await conn.execute(text("INSERT INTO platform_settings (id, settings) "
                                "VALUES (1, '{\"default_trial_days\": 14}') ON CONFLICT (id) DO NOTHING"))
        # Lifespan DDL (main.py), not on the ORM model: the shared "not played" predicate reads it.
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as db:
        await crm_rules.seed_defaults(db)
        await db.commit()
    mdb.async_session_maker = Session

    # ── outbound edges only ──────────────────────────────────────────────────
    async def ca_org(org_id):
        return {"id": org_id, "name": "x"}
    sst.playhq_client.get_organisation = ca_org

    async def no_address(db, *, org_id, name):
        return None
    sst._resolve_club_address = no_address

    async def is_verified(db, email):
        return True
    sst.verification.is_verified = is_verified
    pss.record_event_bg = lambda **_k: None

    async def onboard(db, background_tasks, org_id, org_name="", auto_yearbooks=False):
        """`_onboard_club_core` minus the Cricket Australia sync: same org row, and the same
        best-effort link back to an existing Directory row by name (organisations.py)."""
        org = Organisation(id=uuid.UUID(org_id), name=org_name, slug=f"c-{org_id[:8]}", is_active=True)
        db.add(org)
        await db.flush()
        mc = await db.scalar(select(MarketingClub).where(
            MarketingClub.existing_org_id.is_(None), func.lower(MarketingClub.name) == org_name.lower()))
        if mc is not None:
            mc.existing_org_id = org.id
        await db.commit()
        return org, uuid.uuid4(), org_name
    orgs_router._onboard_club_core = onboard

    # ── BetterCricket's own outreach org, and a club that IS in the Directory ─
    async with Session() as db:
        outreach = Organisation(id=uuid.uuid4(), name="BetterCricket", slug="bc-outreach",
                                is_active=True, is_marketing_outreach=True)
        db.add(outreach)
        known = MarketingClub(grassroots_guid=f"g-{uuid.uuid4()}", name="Known CC", kind="club",
                              status="target", source="api")
        db.add(known)
        await db.commit()
        outreach_id, known_mc_id = outreach.id, known.id

    async def register(name: str, email: str, first="Sam", mobile=None, ip="198.51.100.40", key=None):
        """Run the public submit, then everything it queued. Returns (reply, org_id)."""
        org_id = str(uuid.uuid4())
        async with Session() as db:
            db.add(SelfServeAcknowledgement(id=uuid.uuid4(), email=email, club_name=name,
                                            terms_version="x", privacy_version="x", accepted_at=NOW))
            await db.commit()
        kw = dict(idempotency_key=key or f"k-{uuid.uuid4()}", org_id=org_id, name=name, first_name=first,
                  email=email, password=PW, confirm_password=PW, modules=[], visitorId=str(uuid.uuid4()))
        if mobile:
            kw["mobile_number"] = mobile
        bg = BackgroundTasks()
        async with Session() as db:
            res = await safe(pss.submit(pss.PublicSubmitRequest(**kw), fake_request(ip), Response(), bg, db))
        # What the response would have started afterwards: background tasks in order, then the
        # fire-and-forget admin-list sync.
        try:
            await bg()
        except Exception as e:  # noqa: BLE001
            print(f"    (background task raised: {type(e).__name__}: {e})")
        if acl._tasks:
            await asyncio.gather(*list(acl._tasks), return_exceptions=True)
        return res, org_id

    async def contact_rows(email: str):
        async with Session() as db:
            return (await db.execute(select(CommsContact).where(
                CommsContact.organisation_id == outreach_id, CommsContact.email == email))).scalars().all()

    async def on_admin_segment(contact_id) -> bool:
        async with Session() as db:
            seg = (await db.execute(select(CommsSegment).where(
                CommsSegment.organisation_id == outreach_id, CommsSegment.name == acl.LIST_NAME))).scalar_one_or_none()
            if seg is None:
                return False
            return (await db.scalar(select(func.count(CommsSegmentMember.id)).where(
                CommsSegmentMember.segment_id == seg.id, CommsSegmentMember.contact_id == contact_id))) == 1

    async def segment_audience() -> set:
        """What BetterComms resolves that segment to when somebody sends to it."""
        async with Session() as db:
            seg = (await db.execute(select(CommsSegment).where(
                CommsSegment.organisation_id == outreach_id, CommsSegment.name == acl.LIST_NAME))).scalar_one_or_none()
            if seg is None:
                return set()
            outreach = await db.get(Organisation, outreach_id)
            static = list((await db.execute(select(CommsSegmentMember.contact_id).where(
                CommsSegmentMember.segment_id == seg.id))).scalars().all())
            rows = await comms_segments.resolve_contacts(db, outreach, seg.definition or {}, static_ids=static)
            return {c.email for c in rows}

    # ── 1. a club already in the Directory ───────────────────────────────────
    print("club already in the Clubs Directory")
    res, org1 = await register("Known CC", "sam@known.example", mobile="0412 345 678")
    check("the registration completes", res.get("status") == "completed", str(res)[:300])
    rows = await contact_rows("sam@known.example")
    check("the new admin is a contact on the internal list", len(rows) == 1, f"{len(rows)} rows")
    c = rows[0] if rows else None
    check("...named as they signed up", c is not None and c.name == "Sam", str(c and c.name))
    check("...tied to their club's Directory row", c is not None and c.marketing_club_id == known_mc_id,
          str(c and c.marketing_club_id))
    check("...on the Super Admin User Contact List segment", c is not None and await on_admin_segment(c.id))
    check("...and BetterComms resolves that segment to them", "sam@known.example" in await segment_audience(),
          str(await segment_audience()))
    async with Session() as db:
        dc = (await db.execute(select(MarketingClubContact).where(
            MarketingClubContact.marketing_club_id == known_mc_id,
            func.lower(MarketingClubContact.email) == "sam@known.example"))).scalars().all()
    check("the club's Directory contact carries the mobile they typed",
          len(dc) == 1 and dc[0].mobile == "0412 345 678", str([(d.full_name, d.mobile) for d in dc]))

    # ── 2. a club the Directory has never heard of ───────────────────────────
    print("club NOT in the Clubs Directory")
    res, org2 = await register("Brand New CC", "alex@brandnew.example", first="Alex", ip="198.51.100.41")
    check("the registration completes", res.get("status") == "completed", str(res)[:300])
    rows = await contact_rows("alex@brandnew.example")
    check("the new admin is a contact on the internal list", len(rows) == 1, f"{len(rows)} rows")
    c = rows[0] if rows else None
    async with Session() as db:
        mc2 = await db.scalar(select(MarketingClub).where(MarketingClub.existing_org_id == uuid.UUID(org2)))
    check("the registration gave the club a Directory row", mc2 is not None)
    check("the contact is tied to THAT club (so {{club}} and the trial figures resolve)",
          c is not None and mc2 is not None and c.marketing_club_id == mc2.id,
          f"contact.marketing_club_id={c and c.marketing_club_id} club={mc2 and mc2.id}")
    check("...and is on the Super Admin User Contact List segment", c is not None and await on_admin_segment(c.id))

    # ── 3. already a contact: no duplicate, nothing overwritten ──────────────
    print("already a contact")
    async with Session() as db:
        db.add(CommsContact(organisation_id=outreach_id, email="pat@known.example", name="Pat Secretary",
                            source="import", marketing_club_id=known_mc_id, role="Secretary"))
        await db.commit()
    # A second club under the SAME existing Directory name is not possible, so use a fresh known club.
    async with Session() as db:
        mc3 = MarketingClub(grassroots_guid=f"g-{uuid.uuid4()}", name="Pat CC", kind="club", status="target", source="api")
        db.add(mc3)
        await db.flush()
        db.add(CommsContact(organisation_id=outreach_id, email="pat@patcc.example", name="Pat Secretary",
                            source="import", marketing_club_id=mc3.id, role="Secretary"))
        await db.commit()
        mc3_id = mc3.id
    res, _ = await register("Pat CC", "pat@patcc.example", first="Pat", ip="198.51.100.42")
    check("the registration completes", res.get("status") == "completed", str(res)[:300])
    rows = await contact_rows("pat@patcc.example")
    check("one contact, not two", len(rows) == 1, f"{len(rows)} rows")
    c = rows[0] if rows else None
    check("the name a person already had on file is kept", c is not None and c.name == "Pat Secretary", str(c and c.name))
    check("the role from the committee is kept", c is not None and c.role == "Secretary", str(c and c.role))
    check("they are on the segment now", c is not None and await on_admin_segment(c.id))
    check("they stay tied to their club", c is not None and c.marketing_club_id == mc3_id, str(c and c.marketing_club_id))

    # ── 4. an opt-out is never overridden ────────────────────────────────────
    print("opt-out")
    async with Session() as db:
        mc4 = MarketingClub(grassroots_guid=f"g-{uuid.uuid4()}", name="Optout CC", kind="club", status="target", source="api")
        db.add(mc4)
        await db.flush()
        db.add(CommsContact(organisation_id=outreach_id, email="quit@optout.example", name="Quinn", source="import",
                            marketing_club_id=mc4.id, subscribed=False, unsubscribed_at=NOW))
        await db.commit()
    res, _ = await register("Optout CC", "quit@optout.example", first="Quinn", ip="198.51.100.43")
    check("the registration completes", res.get("status") == "completed", str(res)[:300])
    rows = await contact_rows("quit@optout.example")
    check("the unsubscribed contact is still unsubscribed", len(rows) == 1 and rows[0].subscribed is False,
          str([(r.subscribed) for r in rows]))
    check("...and is not put on the segment", rows and not await on_admin_segment(rows[0].id))
    check("...and the segment still resolves to the others", {"sam@known.example", "alex@brandnew.example",
                                                              "pat@patcc.example"} <= await segment_audience(),
          str(await segment_audience()))
    check("...and not to them", "quit@optout.example" not in await segment_audience())

    # ── 5. nowhere to put it is not a failure ────────────────────────────────
    print("no outreach org designated")
    async with Session() as db:
        o = await db.get(Organisation, outreach_id)
        o.is_marketing_outreach = False
        o.slug = "not-the-outreach-org"
        await db.commit()
    res, _ = await register("Lonely CC", "lone@lonely.example", first="Lou", ip="198.51.100.44")
    check("the registration still completes", res.get("status") == "completed", str(res)[:300])
    check("and files no contact", len(await contact_rows("lone@lonely.example")) == 0)

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print(f"  FAILED: {f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
