"""A lapsed club registers again: the registrant is picked up, the last 24 hours are read, and
Jack and Elton are told (email) with the same text saved as a note on the club's deal.

Runs the SHIPPED `self_serve_trial.submit` against a real Postgres, then runs the background
tasks it queued in order, the way the server does after the response. Only outbound edges are
stubbed: the Cricket Australia lookups, the club onboarding sync kick-off (the same row is
returned, as the real upsert does), the address lookup, the verification table, the admin-list
queue and the email provider. The CRM deal sync and the follow-up itself are the real code.
Run it against the previous commit and the checks fail on exactly what did not exist.

    python -m verification.verify_returning_club_followup
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import BackgroundTasks
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models.db as mdb
from app.models.db import (
    Base, ClubMembership, ClubOnboardingRequest, CrmActivity, CrmDeal, CrmDealContact, CrmPerson,
    EmailEvent, MarketingClub, Organisation, OrgModuleSubscription, SelfServeAcknowledgement, SelfServeIdempotencyKey, User,
)
from app.routers import organisations as orgs_router
from app.routers import public_self_serve as pss
from app.routers import self_serve_trial as sst
from app.services import crm, email_service
from app.services import returning_club_followup as rcf  # present in the control run too (untracked)

DB_URL = os.environ.get("VERIFY_DATABASE_URL", "postgresql+asyncpg://postgres@127.0.0.1:55432/verify_returning")
PASS: list[str] = []
FAIL: list[str] = []
NOW = dt.datetime.now(dt.timezone.utc)
H, DAY = dt.timedelta(hours=1), dt.timedelta(days=1)


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} — {detail}")
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  ({detail})'}")


class FakeProvider:
    def __init__(self, name="brevo", ok=True):
        self.name, self.ok, self.sent = name, ok, []

    async def send(self, msg):
        self.sent.append(msg)
        return email_service.SendResult(ok=self.ok, error=None if self.ok else "boom")


USAGE_DDL = """
CREATE TABLE IF NOT EXISTS usage_events (
    id BIGSERIAL PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_type TEXT NOT NULL DEFAULT 'api', method TEXT NOT NULL, path TEXT NOT NULL, route TEXT,
    status INTEGER NOT NULL DEFAULT 0, duration_ms INTEGER, user_id UUID, org_id UUID, ip_hash TEXT,
    user_agent TEXT, referer TEXT, metadata JSONB DEFAULT '{}',
    country TEXT, region TEXT, city TEXT, lat DOUBLE PRECISION, lng DOUBLE PRECISION,
    visitor_id UUID, utm_source TEXT, utm_medium TEXT, utm_campaign TEXT, utm_content TEXT, utm_id TEXT,
    click_id TEXT, traffic_source TEXT, landing_path TEXT, time_on_page_ms INTEGER,
    resolved_marketing_club_id UUID
)"""


async def deal_of(Session, oid):
    """The club's platform deal: it hangs off the directory row, not the organisation."""
    async with Session() as db:
        return (await db.execute(
            select(CrmDeal).join(MarketingClub, MarketingClub.id == CrmDeal.marketing_club_id)
            .where(MarketingClub.existing_org_id == oid))).scalars().first()


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
        from app.services import crm_rules
        await crm_rules.seed_defaults(db)   # the lifespan seeds the automation rules the deal sync reads
        await db.commit()
    mdb.async_session_maker = Session      # the CRM sync opens its own session
    rcf.async_session_maker = Session      # so does the follow-up

    # ── outbound edges ────────────────────────────────────────────────────────
    async def ca_org(org_id):
        return {"id": org_id, "name": "x"}
    sst.playhq_client.get_organisation = ca_org
    async def no_address(db, *, org_id, name):
        return None
    sst._resolve_club_address = no_address
    async def verified(db, email):
        return True
    sst.verification.is_verified = verified
    import app.services.admin_contact_list as acl
    acl.queue_sync = lambda *_a, **_k: None

    async def reuse_or_make(db, background_tasks, org_id, org_name="", auto_yearbooks=False):
        oid = uuid.UUID(org_id)
        org = (await db.execute(select(Organisation).where(Organisation.id == oid))).scalar_one_or_none()
        if org is None:
            org = Organisation(id=oid, name=org_name)
            db.add(org)
            await db.commit()
        return org, uuid.uuid4(), org_name or org.name
    orgs_router._onboard_club_core = reuse_or_make

    provider = FakeProvider()
    email_service.get_email_provider = lambda: provider

    # ── the club that lapsed, with two admins and a deal from its first registration ──
    other = uuid.uuid4()
    clubs = {}

    async def make_lapsed(label, name):
        oid = uuid.uuid4()
        clubs[label] = {"id": oid, "name": name, "slug": name.lower().replace(" ", "-")}
        async with Session() as db:
            db.add(Organisation(id=oid, name=name, slug=clubs[label]["slug"], is_active=True))
            await db.flush()
            for mod in ("core", "select"):
                db.add(OrgModuleSubscription(id=uuid.uuid4(), organisation_id=oid, module_key=mod, status="trial",
                                             trial_started_at=NOW - 30 * DAY, trial_ends_at=NOW - 9 * DAY))
            ann = User(id=uuid.uuid4(), email=f"ann@{label}.example", username=f"ann-{label}", display_name="Ann Admin", password_hash="x")
            bob = User(id=uuid.uuid4(), email=f"bob@{label}.example", username=f"bob-{label}", display_name="Bob Admin", password_hash="x")
            db.add_all([ann, bob])
            await db.flush()
            db.add(ClubMembership(id=uuid.uuid4(), user_id=ann.id, club_id=oid, role="club_admin", is_primary_admin=True))
            db.add(ClubMembership(id=uuid.uuid4(), user_id=bob.id, club_id=oid, role="club_admin"))
            db.add(SelfServeIdempotencyKey(idempotency_key=f"first-{label}", email=ann.email, status="completed",
                                           org_id=oid, user_id=ann.id, created_at=NOW - 30 * DAY))
            await db.commit()
            clubs[label]["ann"] = ann.id
        sync_result = await crm.sync_self_serve_trial_registration(org_id=oid, org_name=name, contact_name="Ann Admin",
                                                     email=f"ann@{label}.example", phone=None)
        print("  crm sync:", sync_result)

    await make_lapsed("lapsed", "Lapsed CC")
    org = clubs["lapsed"]["id"]
    deal = await deal_of(Session, org)
    check("setup: the club's first registration left a deal with Ann as its contact", deal is not None,
          "no deal: the CRM sync did not create one")
    if deal is None:
        print("cannot continue without a deal")
        return 1
    visitor, rival = uuid.uuid4(), uuid.uuid4()

    async def usage(created, *, etype="page_view", path="/x", route=None, user=None, org_id=None, visitor_id=None, meta=None):
        async with Session() as db:
            await db.execute(text("""INSERT INTO usage_events (created_at, event_type, method, path, route, user_id, org_id, visitor_id, metadata)
                VALUES (:c, :t, 'GET', :p, :r, CAST(:u AS uuid), CAST(:o AS uuid), CAST(:v AS uuid), CAST(:m AS jsonb))"""),
                {"c": created, "t": etype, "p": path, "r": route or path, "u": str(user) if user else None,
                 "o": str(org_id) if org_id else None, "v": str(visitor_id) if visitor_id else None,
                 "m": json.dumps(meta or {})})
            await db.commit()

    for _ in range(3):
        await usage(NOW - 2 * H, path="/trial", visitor_id=visitor)
    await usage(NOW - 2 * H, etype="self_serve_step", route="club_prepared", path="/public/self-serve/track-step",
                visitor_id=visitor, meta={"club_org_id": str(org), "club_name": "Lapsed CC"})
    await usage(NOW - 3 * H, etype="self_serve_step", route="club_searched", path="/public/self-serve/track-step",
                visitor_id=rival, meta={"club_org_id": str(org)})
    await usage(NOW - 4 * H, path="/lapsed-cc", org_id=org, visitor_id=rival)
    await usage(NOW - 4 * H, path="/lapsed-cc", org_id=org, visitor_id=visitor)
    await usage(NOW - 5 * H, etype="api", path="/api/admin/players", user=clubs["lapsed"]["ann"], org_id=org)
    # must NOT show: too old, after the registration, another club, a beacon that says nothing
    await usage(NOW - 3 * DAY, path="/old-page", visitor_id=visitor)
    await usage(NOW + 1 * H, path="/future-page", visitor_id=visitor)
    await usage(NOW - 1 * H, path="/other-club-page", org_id=other)
    await usage(NOW - 1 * H, etype="heartbeat", path="/heartbeat-noise", visitor_id=visitor)
    async with Session() as db:
        db.add_all([
            EmailEvent(id=uuid.uuid4(), email="ann@lapsed.example", event_type="open", ses_message_id="m1", created_at=NOW - 2 * H),
            EmailEvent(id=uuid.uuid4(), email="stranger@example.com", event_type="open", ses_message_id="m2", created_at=NOW - 2 * H),
            EmailEvent(id=uuid.uuid4(), email="ann@lapsed.example", event_type="open", ses_message_id="m3", created_at=NOW - 3 * DAY),
            ClubOnboardingRequest(id=uuid.uuid4(), name="Dana Contact", club="Lapsed CC", email="dana@lapsed.example",
                                  source="contact_form", club_org_id=str(org), created_at=NOW - 6 * H),
            ClubOnboardingRequest(id=uuid.uuid4(), name="Other Person", club="Some Other Club", email="o@example.com",
                                  source="contact_form", club_org_id=str(other), created_at=NOW - 6 * H),
            CrmActivity(id=uuid.uuid4(), deal_id=deal.id, organisation_id=org, type="call", outcome="no_answer",
                        body="Rang Ann, left a message", occurred_at=NOW - 7 * H),
        ])
        await db.commit()

    def body(label, email, key):
        c = clubs[label]
        return sst.SubmitRequest(
            idempotency_key=key, org_id=str(c["id"]), name=c["name"], first_name="Nina", last_name="Newadmin",
            display_name="Nina Newadmin", username=f"nina-{label}", email=email, mobile_number="0412345678",
            password="Str0ng!Passw0rd#1", confirm_password="Str0ng!Passw0rd#1", modules=[])

    async def register(label, email, key="k1", vis=None):
        async with Session() as db:
            db.add(SelfServeAcknowledgement(id=uuid.uuid4(), email=email, club_name=clubs[label]["name"],
                                            terms_version="x", privacy_version="x", accepted_at=NOW))
            await db.commit()
        bt = BackgroundTasks()
        data = body(label, email, key)
        if vis:   # the public flow's own request model carries the visitor id, as the wrapper passes it on
            data = pss.PublicSubmitRequest(**data.model_dump(), visitorId=str(vis))
        async with Session() as db:
            res = await sst.submit(data, bt, db)
        names = [getattr(t.func, "__name__", "?") for t in bt.tasks]
        for t in bt.tasks:
            await t()
        return res, names

    # ── 1. a lapsed club registers again, by a new person ─────────────────────
    print("lapsed club registers again")
    provider.sent.clear()
    res, names = await register("lapsed", "nina@new.example", vis=visitor)
    check("registration completes", res.get("status") == "completed", str(res))
    check("the follow-up was queued after the CRM sync", names[-1:] == ["run"] and "sync_self_serve_trial_registration" in names
          and names.index("run") > names.index("sync_self_serve_trial_registration"), str(names))
    check("Jack and Elton were each emailed, with the registrant as reply-to",
          sorted(m.to_email for m in provider.sent) == ["elton@bettersports.com.au", "jack@bettersports.com.au"]
          and all(m.reply_to == "nina@new.example" for m in provider.sent), str([(m.to_email, m.reply_to) for m in provider.sent]))
    t = provider.sent[0].text if provider.sent else ""
    check("subject names the club", provider.sent and provider.sent[0].subject == "Returning club registered again: Lapsed CC",
          provider.sent[0].subject if provider.sent else "no email")
    check("says to follow up personally", "Follow up personally" in t)
    check("registrant's details are in it", "nina@new.example" in t and "0412345678" in t and "Nina Newadmin" in t)
    check("says it is a new person", "A new person" in t)
    check("both earlier admins are listed, the primary marked, and told they keep access",
          "ann@lapsed.example" in t and "bob@lapsed.example" in t and "primary admin" in t and "keep their access" in t)
    check("history: first registered, trial ended, modules",
          (NOW - 30 * DAY).strftime("%d %b %Y") in t and (NOW - 9 * DAY).strftime("%d %b %Y") in t and "select" in t)
    check("registrant's own visits are counted", "/trial (page_view): 3" in t, t[:0])
    check("picks and searches for the club are counted",
          "Picked the club: 1 time(s)" in t and "Searched for the club: 1 time(s)" in t)
    check("the club's own page views are counted", "/lapsed-cc (page_view): 2" in t)
    check("an earlier admin's activity is counted", "/api/admin/players (api): 1" in t)
    check("an email opened by an earlier admin is listed", "ann@lapsed.example: open x1" in t)
    check("a contact form for the club is listed", "Dana Contact" in t)
    check("our own call is listed", "Rang Ann" in t)
    for needle, why in (("/old-page", "older than 24 hours"), ("/future-page", "after the registration"),
                        ("/other-club-page", "another club"), ("stranger@example.com", "an unrelated address"),
                        ("/heartbeat-noise", "a beacon that says nothing"), ("Other Person", "another club's enquiry")):
        check(f"left out: {why}", needle not in t, needle)

    async with Session() as db:
        notes = (await db.execute(select(CrmActivity).where(CrmActivity.deal_id == deal.id, CrmActivity.type == "note"))).scalars().all()
        mine = [n for n in notes if (n.meta or {}).get("kind") == "returning_club_registered"]
        links = (await db.execute(select(CrmDealContact, CrmPerson).join(CrmPerson, CrmPerson.id == CrmDealContact.person_id)
                                  .where(CrmDealContact.deal_id == deal.id))).all()
    check("a note was saved on the deal, with the same text", len(mine) == 1 and "Follow up personally" in (mine[0].body or "")
          and "Staff emailed (2 of 2)." in (mine[0].body or ""), str([(n.meta, (n.body or "")[:60]) for n in notes]))
    poc = [p.email for l, p in links if l.role_on_deal == crm.POINT_OF_CONTACT_ROLE]
    check("the new person is the deal's point of contact", poc == ["nina@new.example"], str(poc))
    check("Ann is still linked, only no longer the point of contact",
          any(p.email == "ann@lapsed.example" and l.role_on_deal != crm.POINT_OF_CONTACT_ROLE for l, p in links),
          str([(p.email, l.role_on_deal) for l, p in links]))

    # ── 2. nothing doubles up, and ordinary registrations are left alone ──────
    print("no double notification, ordinary registrations untouched")
    provider.sent.clear()
    res2, names2 = await register("lapsed", "nina@new.example", key="k1", vis=visitor)
    check("a replayed submit queues nothing and emails nobody", res2.get("replayed") is True and "run" not in names2 and not provider.sent,
          f"{res2} {names2} {len(provider.sent)}")
    new_id = uuid.uuid4()
    clubs["fresh"] = {"id": new_id, "name": "Brand New CC", "slug": None}
    provider.sent.clear()
    res3, names3 = await register("fresh", "fresh@new.example", key="kf")
    async with Session() as db:
        fresh_notes = (await db.execute(select(CrmActivity).where(CrmActivity.organisation_id == new_id,
                                                                   CrmActivity.type == "note"))).scalars().all()
    check("control: a brand new club registers with no follow-up queued, no email, no note",
          res3.get("status") == "completed" and "run" not in names3 and not provider.sent
          and not [n for n in fresh_notes if (n.meta or {}).get("kind") == "returning_club_registered"], f"{names3} {len(provider.sent)}")

    # ── 3. no live email provider, and a read that fails ──────────────────────
    print("no live provider; a failed read")
    await make_lapsed("two", "Lapsed Two")
    provider.sent.clear()
    console = FakeProvider(name="console")
    email_service.get_email_provider = lambda: console
    await register("two", "nina2@new.example", key="k2")
    async with Session() as db:
        deal2 = await deal_of(Session, clubs["two"]["id"])
        n2 = (await db.execute(select(CrmActivity).where(CrmActivity.deal_id == deal2.id, CrmActivity.type == "note"))).scalars().all()
    n2 = [n for n in n2 if (n.meta or {}).get("kind") == "returning_club_registered"]
    check("console provider is not a send: nothing goes out and the note says so",
          not console.sent and len(n2) == 1 and "Staff email NOT sent: no live email provider" in (n2[0].body or ""),
          str([(n.body or "")[-90:] for n in n2]))

    await make_lapsed("three", "Lapsed Three")
    email_service.get_email_provider = lambda: provider
    provider.sent.clear()
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE email_events RENAME TO email_events_x"))
    try:
        await register("three", "nina3@new.example", key="k3")
    finally:
        async with engine.begin() as conn:
            await conn.execute(text("ALTER TABLE email_events_x RENAME TO email_events"))
    t3 = provider.sent[0].text if provider.sent else ""
    deal3 = await deal_of(Session, clubs["three"]["id"])
    async with Session() as db:
        n3 = [n for n in (await db.execute(select(CrmActivity).where(CrmActivity.deal_id == deal3.id, CrmActivity.type == "note"))).scalars().all()
              if (n.meta or {}).get("kind") == "returning_club_registered"]
        poc3 = [p.email for l, p in (await db.execute(select(CrmDealContact, CrmPerson).join(CrmPerson, CrmPerson.id == CrmDealContact.person_id)
                                                      .where(CrmDealContact.deal_id == deal3.id))).all()
                if l.role_on_deal == crm.POINT_OF_CONTACT_ROLE]
    check("after a failed read the note is still written and the new person still linked",
          len(n3) == 1 and "Could not be read" in (n3[0].body or "") and poc3 == ["nina3@new.example"],
          f"notes={len(n3)} poc={poc3}")
    check("one failed read is reported as unreadable, and the email still goes out",
          len(provider.sent) == 2 and "Could not be read" in t3 and "Follow up personally" in t3, t3[:120])

    # ── 4. the wording rules for a person we already know ─────────────────────
    print("wording")
    snap = {"org_id": org, "club_name": "Lapsed CC", "slug": "lapsed-cc", "first_registered_at": NOW - 30 * DAY,
            "trial_ended_at": NOW - 9 * DAY, "modules": ["core"],
            "admins": [{"user_id": uuid.uuid4(), "name": "Ann Admin", "email": "ann@lapsed.example", "primary": True}]}
    _, same_text, _ = rcf.compose(snapshot=snap, registrant={"name": "Ann Admin", "email": "ann@lapsed.example"}, new_person=False,
                                  trial_ends_at=NOW + 14 * DAY, attribution=None, activity=[], deal_found=False, until=NOW)
    check("the same email as an earlier admin is said, without the 'check this' warning",
          "same email as one of the club's earlier admins" in same_text and "keep their access" not in same_text)
    check("a missing deal is said, not skipped", "No CRM deal was found" in same_text)
    check("no em or en dashes in what staff read", "—" not in t and "–" not in t)

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print("  FAILED:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
