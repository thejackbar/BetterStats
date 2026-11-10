"""An earlier admin of a lapsed club registers again with their OWN email.

Before: the wizard stopped them ("This email already belongs to a BetterCricket account") and a
logged-in admin could not start a trial while Core was off, so the people most likely to come
back could not. Now: that one case is allowed. The trial restarts on the same club row, no second
account is made, their password, username and profile are NOT touched, and they are NOT signed in
(a 4-digit email code proves the address for registering but is too weak to open an existing
account), so the public route sends them to the sign-in page.

Everything else stays refused and is checked beside it so the rule cannot widen: an email on any
other account, an admin of a different club, an admin of a club that is not a lapsed trial, a
member who is not an admin, an unverified email, and a missing Terms acceptance.

Runs the SHIPPED `validate_admin`, `submit` and the public `submit` against a real Postgres.
Only outbound edges are stubbed (Cricket Australia, the sync kick-off, the address lookup, the
verification table, the admin-list queue, the email provider, the usage beacon).

    python -m verification.verify_returning_admin_reregister
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import BackgroundTasks, HTTPException, Response
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload
from starlette.requests import Request

import app.models.db as mdb
from app.models.db import (
    Base, ClubMembership, CrmDeal, CrmDealContact, CrmPerson, MarketingClub, Organisation,
    OrgModuleSubscription, SelfServeAcknowledgement, SelfServeIdempotencyKey, User,
)
from app.routers import organisations as orgs_router
from app.routers import public_self_serve as pss
from app.routers import self_serve_trial as sst
from app.services import admin_identity, crm, crm_rules, email_service
from app.services import returning_club_followup as rcf

DB_URL = os.environ.get("VERIFY_DATABASE_URL", "postgresql+asyncpg://postgres@127.0.0.1:55432/verify_returning_admin")
PASS: list[str] = []
FAIL: list[str] = []
NOW = dt.datetime.now(dt.timezone.utc)
DAY = dt.timedelta(days=1)


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} — {detail}")
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  ({detail})'}")


class FakeProvider:
    def __init__(self):
        self.name, self.sent = "brevo", []

    async def send(self, msg):
        self.sent.append(msg)
        return email_service.SendResult(ok=True, error=None)


def fake_request(ip="203.0.113.5") -> Request:
    return Request({"type": "http", "method": "POST", "path": "/", "query_string": b"",
                    "headers": [(b"user-agent", b"verify"), (b"x-real-ip", ip.encode())], "client": (ip, 1234)})


async def safe(coro):
    """The reply, or {'_http': status} when the route refuses: a control run REPORTS, it does not crash."""
    try:
        return await coro
    except HTTPException as e:
        return {"_http": e.status_code, "_detail": str(e.detail)[:80]}


async def outcome(coro):
    try:
        return "ok", await coro
    except HTTPException as e:
        return "http", e.status_code, e.detail


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
        await conn.execute(text("INSERT INTO platform_settings (id, settings) VALUES (1, '{\"default_trial_days\": 14}') ON CONFLICT (id) DO NOTHING"))
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as db:
        await crm_rules.seed_defaults(db)
        await db.commit()
    mdb.async_session_maker = Session
    rcf.async_session_maker = Session

    async def ca_org(org_id):
        return {"id": org_id, "name": "x"}
    sst.playhq_client.get_organisation = ca_org
    async def no_address(db, *, org_id, name):
        return None
    sst._resolve_club_address = no_address
    verified = {"yes": True}
    async def is_verified(db, email):
        return verified["yes"]
    sst.verification.is_verified = is_verified
    import app.services.admin_contact_list as acl
    acl.queue_sync = lambda *_a, **_k: None
    pss.record_event_bg = lambda **_k: None
    async def reuse(db, background_tasks, org_id, org_name="", auto_yearbooks=False):
        org = (await db.execute(select(Organisation).where(Organisation.id == uuid.UUID(org_id)))).scalar_one()
        return org, uuid.uuid4(), org_name or org.name
    orgs_router._onboard_club_core = reuse
    provider = FakeProvider()
    email_service.get_email_provider = lambda: provider

    clubs: dict = {}

    async def make_club(label, name, *, lapsed=True):
        oid = uuid.uuid4()
        ends = NOW - 9 * DAY if lapsed else NOW + 5 * DAY
        async with Session() as db:
            db.add(Organisation(id=oid, name=name, slug=name.lower().replace(" ", "-"), is_active=True))
            await db.flush()
            for mod in ("core", "select"):
                db.add(OrgModuleSubscription(id=uuid.uuid4(), organisation_id=oid, module_key=mod, status="trial",
                                             trial_started_at=NOW - 30 * DAY, trial_ends_at=ends))
            ann = User(id=uuid.uuid4(), email=f"ann@{label}.example", username=f"ann-{label}", display_name="Ann Admin",
                       password_hash="ANN-ORIGINAL-HASH", mobile_number="0400000001")
            bob = User(id=uuid.uuid4(), email=f"bob@{label}.example", username=f"bob-{label}", display_name="Bob Admin", password_hash="x")
            member = User(id=uuid.uuid4(), email=f"mem@{label}.example", username=f"mem-{label}", display_name="Mem Ber", password_hash="x")
            db.add_all([ann, bob, member])
            await db.flush()
            db.add(ClubMembership(id=uuid.uuid4(), user_id=ann.id, club_id=oid, role="club_admin", is_primary_admin=True))
            db.add(ClubMembership(id=uuid.uuid4(), user_id=bob.id, club_id=oid, role="club_admin"))
            db.add(ClubMembership(id=uuid.uuid4(), user_id=member.id, club_id=oid, role="member"))
            await db.commit()
        clubs[label] = {"id": oid, "name": name, "ann": ann.id}
        await crm.sync_self_serve_trial_registration(org_id=oid, org_name=name, contact_name="Ann Admin",
                                                     email=f"ann@{label}.example", phone=None)

    await make_club("alpha", "Alpha CC")
    await make_club("beta", "Beta CC")
    await make_club("live", "Live CC", lapsed=False)

    def vreq(label, email, *, username="", mobile="0412345678", on=None):
        c = clubs[on or label]
        return sst.ValidateAdminRequest(first_name="Ann", last_name="Admin", display_name="Ann A", username=username,
                                        email=email, mobile_number=mobile, org_id=str(c["id"]), club_name=c["name"])

    async def validate(req):
        async with Session() as db:
            return await sst.validate_admin(req, db)

    # ── 1. the wizard's as-you-type check ─────────────────────────────────────
    print("admin details check")
    r = await validate(vreq("alpha", "ann@alpha.example", username="ann-alpha"))
    check("an earlier admin's own email is accepted for their lapsed club (even with their own username)",
          r.get("valid") is True and r.get("returning_admin") is True and not r.get("errors"), str(r))
    r = await validate(vreq("alpha", "bob@alpha.example"))
    check("a second earlier admin is accepted too", r.get("valid") is True and r.get("returning_admin") is True, str(r))
    r = await validate(vreq("alpha", "ann@alpha.example", mobile=""))
    check("other problems are still reported for a returning admin (no mobile)",
          r.get("valid") is False and "mobile_number" in (r.get("errors") or {}) and r.get("returning_admin") is True, str(r))
    bare = sst.ValidateAdminRequest(first_name="Ann", last_name="Admin", display_name="Ann A", username="x1",
                                    email="ann@alpha.example", mobile_number="0412345678")
    r = await validate(bare)
    check("control: with no club in the request the email is still refused as taken",
          r.get("valid") is False and r["errors"].get("email") == admin_identity.EMAIL_TAKEN_MESSAGE and not r.get("returning_admin"), str(r))
    r = await validate(vreq("alpha", "ann@alpha.example", on="beta"))
    check("an admin of a DIFFERENT club is still refused", r.get("valid") is False and not r.get("returning_admin"), str(r))
    r = await validate(vreq("alpha", "mem@alpha.example"))
    check("a member who is not an admin is still refused", r.get("valid") is False and not r.get("returning_admin"), str(r))
    r = await validate(vreq("live", "ann@live.example"))
    check("an admin of a club that is NOT a lapsed trial is still refused", r.get("valid") is False and not r.get("returning_admin"), str(r))
    r = await validate(vreq("alpha", "fresh@elsewhere.example", username="fresh-1"))
    check("control: a brand new email is valid and is not flagged returning", r.get("valid") is True and r.get("returning_admin") is False, str(r))

    # ── 2. the registration itself ────────────────────────────────────────────
    print("registering again")

    def body(label, email, key, *, password="", username=""):
        c = clubs[label]
        return sst.SubmitRequest(idempotency_key=key, org_id=str(c["id"]), name=c["name"], first_name="Ann", last_name="Admin",
                                 display_name="Ann Admin", username=username, email=email, mobile_number="0412 999 888",
                                 password=password, confirm_password=password, modules=[])

    async def ack(label, email):
        async with Session() as db:
            db.add(SelfServeAcknowledgement(id=uuid.uuid4(), email=email, club_name=clubs[label]["name"],
                                            terms_version="x", privacy_version="x", accepted_at=NOW))
            await db.commit()

    async def counts(label):
        async with Session() as db:
            users = (await db.execute(select(func.count()).select_from(User))).scalar()
            members = (await db.execute(select(func.count()).select_from(ClubMembership).where(ClubMembership.club_id == clubs[label]["id"]))).scalar()
        return users, members

    async def user_row(email):
        async with Session() as db:
            u = (await db.execute(select(User).where(User.email == email))).scalar_one()
            return u.password_hash, u.username, u.display_name, u.mobile_number

    await ack("alpha", "ann@alpha.example")
    before_users, before_members = await counts("alpha")
    before_user = await user_row("ann@alpha.example")
    provider.sent.clear()
    bt = BackgroundTasks()
    async with Session() as db:
        res = await safe(sst.submit(body("alpha", "ann@alpha.example", "ra-1"), bt, db))   # no password sent
    names = [getattr(t.func, "__name__", "?") for t in bt.tasks]
    for t in bt.tasks:
        await t()
    check("the registration completes with no password and no username", res.get("status") == "completed", str(res))
    check("it says returning admin and hands back NO user id (nothing to sign in by)",
          res.get("returning_admin") is True and res.get("user_id") is None, str(res))
    after_users, after_members = await counts("alpha")
    check("no second account and no extra membership were made", (after_users, after_members) == (before_users, before_members),
          f"{(before_users, before_members)} -> {(after_users, after_members)}")
    check("their password, username, name and phone are exactly as before", await user_row("ann@alpha.example") == before_user,
          f"{before_user} -> {await user_row('ann@alpha.example')}")
    async with Session() as db:
        org = (await db.execute(select(Organisation).where(Organisation.id == clubs["alpha"]["id"])
                                .options(selectinload(Organisation.module_subscriptions)))).scalar_one()
        core = next((s for s in org.module_subscriptions if s.module_key == "core"), None)
        key_row = await db.get(SelfServeIdempotencyKey, "ra-1")
        from app.routers import clubs as clubs_router
        page = await outcome(clubs_router.get_club_by_slug(org.slug, fake_request(), db))
    check("the trial restarted on the same club", core is not None and core.status == "trial" and core.trial_ends_at > NOW + 10 * DAY,
          str(core and (core.status, core.trial_ends_at)))
    check("the club page is live again", page[0] == "ok", str(page))
    check("the key records the club but no user, so a replay cannot sign anyone in",
          key_row is not None and key_row.user_id is None and key_row.org_id == clubs["alpha"]["id"], str(key_row and (key_row.user_id, key_row.org_id)))
    async with Session() as db:
        replay = await safe(sst.submit(body("alpha", "ann@alpha.example", "ra-1"), BackgroundTasks(), db))
    check("a replay says returning admin and still has no user id", replay.get("replayed") is True and replay.get("returning_admin") is True
          and replay.get("user_id") is None, str(replay))

    check("follow-up: staff were emailed and it says this is the club's own admin coming back, not signed in",
          len(provider.sent) == 2 and "club's own admin coming back" in provider.sent[0].text and "not signed in" in provider.sent[0].text
          and "0412 999 888" in provider.sent[0].text, provider.sent[0].text[:200] if provider.sent else "no email")
    check("follow-up queued after the CRM sync", names[-1:] == ["run"] and names.index("run") > names.index("sync_self_serve_trial_registration"), str(names))
    async with Session() as db:
        deal = (await db.execute(select(CrmDeal).join(MarketingClub, MarketingClub.id == CrmDeal.marketing_club_id)
                                 .where(MarketingClub.existing_org_id == clubs["alpha"]["id"]))).scalars().first()
        links = (await db.execute(select(CrmDealContact, CrmPerson).join(CrmPerson, CrmPerson.id == CrmDealContact.person_id)
                                  .where(CrmDealContact.deal_id == deal.id))).all()
    poc = [p.email for l, p in links if l.role_on_deal == crm.POINT_OF_CONTACT_ROLE]
    check("the deal's point of contact is still Ann (the same person), not duplicated", poc == ["ann@alpha.example"] and len(links) == 1, str(poc))

    # a password sent anyway is ignored
    await ack("beta", "ann@beta.example")
    before_beta = await user_row("ann@beta.example")
    async with Session() as db:
        res2 = await safe(sst.submit(body("beta", "ann@beta.example", "rb-1", password="Str0ng!Passw0rd#1", username="hijack"), BackgroundTasks(), db))
    check("a password and username sent anyway are ignored", res2.get("returning_admin") is True and await user_row("ann@beta.example") == before_beta,
          f"{res2} {await user_row('ann@beta.example')}")

    # ── 3. the public route: no session, to the sign-in page ──────────────────
    print("public route")
    await make_club("gamma", "Gamma CC")
    await ack("gamma", "ann@gamma.example")
    pub = pss.PublicSubmitRequest(**body("gamma", "ann@gamma.example", "rg-1").model_dump(), visitorId=str(uuid.uuid4()))
    response = Response()
    async with Session() as db:
        pres = await safe(pss.submit(pub, fake_request("198.51.100.20"), response, BackgroundTasks(), db))
    cookie = response.headers.get("set-cookie", "")
    check("returning admin: no session cookie is set", "bs_session" not in cookie and not cookie, cookie[:60])
    check("returning admin: sent to the sign-in page", pres.get("redirect") == "/login" and pres.get("returning_admin") is True, str(pres))

    await make_club("delta", "Delta CC")
    await ack("delta", "nina@new.example")
    pub2 = pss.PublicSubmitRequest(**body("delta", "nina@new.example", "rd-1", password="Str0ng!Passw0rd#1", username="nina-delta").model_dump(),
                                   visitorId=str(uuid.uuid4()))
    response2 = Response()
    async with Session() as db:
        pres2 = await safe(pss.submit(pub2, fake_request("198.51.100.21"), response2, BackgroundTasks(), db))
    check("control: a new person on a lapsed club IS signed in and goes to /admin",
          "set-cookie" in response2.headers and pres2.get("redirect") == "/admin" and pres2.get("returning_admin") is False
          and bool(pres2.get("user_id")), f"{dict(response2.headers)} {pres2}")

    # ── 4. what must still stop it ────────────────────────────────────────────
    print("still refused")
    await make_club("eps", "Epsilon CC")
    verified["yes"] = False
    await ack("eps", "ann@eps.example")
    async with Session() as db:
        k, v = (await outcome(sst.submit(body("eps", "ann@eps.example", "re-1"), BackgroundTasks(), db)))[:2]
    verified["yes"] = True
    async with Session() as db:
        core_e = (await db.execute(select(OrgModuleSubscription).where(OrgModuleSubscription.organisation_id == clubs["eps"]["id"],
                                                                         OrgModuleSubscription.module_key == "core"))).scalar_one()
    check("an unverified email is refused and the trial is NOT restarted", (k, v) == ("http", 422) and core_e.trial_ends_at < NOW,
          f"{k} {v} {core_e.trial_ends_at}")

    await make_club("zeta", "Zeta CC")      # no Terms acceptance recorded for this email
    async with Session() as db:
        r = await outcome(sst.submit(body("zeta", "ann@zeta.example", "rz-1"), BackgroundTasks(), db))
    check("a missing Terms acceptance is refused", r[:2] == ("http", 422), str(r[:2]))

    await make_club("eta", "Eta CC")
    await ack("eta", "ann@beta.example")
    async with Session() as db:
        r = await outcome(sst.submit(body("eta", "ann@beta.example", "rx-1", password="Str0ng!Passw0rd#1", username="x2"), BackgroundTasks(), db))
    check("another club's admin cannot register onto a lapsed club with their email (refused as taken, nothing restarted)",
          r[:2] == ("http", 422) and admin_identity.EMAIL_TAKEN_MESSAGE in str(r[2]), str(r[:3]))
    async with Session() as db:
        r = await outcome(sst.submit(body("live", "ann@live.example", "rl-1", password="Str0ng!Passw0rd#1", username="x3"), BackgroundTasks(), db))
    check("a live club is still refused as already registered", r[:2] == ("http", 409), str(r[:2]))

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print("  FAILED:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
