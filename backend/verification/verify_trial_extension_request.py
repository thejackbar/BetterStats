"""/trial: a registered club with a paused page asks for a trial extension.

Two things. The club search flags a registered club whose public page shows
"Club page paused" (`already_registered_paused`), so /trial can open the
request modal instead of the dead-end page. And POST
/public/self-serve/request-trial-extension stores the request and emails
jack@ and elton@bettersports.com.au.

Runs the SHIPPED route bodies against a real Postgres; only the Cricket
Australia search and the email provider (outbound edges) are stubbed. Run it
against the previous commit and the checks fail on exactly what did not exist.

    python -m verification.verify_trial_extension_request
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import sys
import uuid
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

from app.models.db import Base, ClubMembership, ClubOnboardingRequest, Organisation, OrgModuleSubscription, User
from app.routers import public_self_serve as pss
from app.routers import self_serve_trial as sst
from app.services import email_service

DB_URL = os.environ.get(
    "VERIFY_DATABASE_URL",
    "postgresql+asyncpg://postgres@127.0.0.1:55432/verify_trial_ext",
)

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} — {detail}")
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  ({detail})'}")


NOW = dt.datetime.now(dt.timezone.utc)


_ip_counter = iter(range(1, 10_000))


def fake_request(ip: str | None = None) -> Request:
    ip = ip or f"203.0.{next(_ip_counter) // 250}.{next(_ip_counter) % 250 + 1}"
    return Request({"type": "http", "method": "POST", "path": "/", "query_string": b"",
                    "headers": [(b"user-agent", b"verify"), (b"x-real-ip", ip.encode())],
                    "client": (ip, 1234)})


class FakeProvider:
    def __init__(self, name="brevo", ok=True):
        self.name, self.ok, self.sent = name, ok, []

    async def send(self, msg):
        self.sent.append(msg)
        return email_service.SendResult(ok=self.ok, error=None if self.ok else "boom")


GOOD = dict(club_name="Paused CC", club_slug="paused-cc", name="Sam Smith",
            email="Sam@Example.com", phone="0412 345 678", role="Secretary",
            message="We ran out of time before our AGM.")


async def post(db, provider, ip=None, **over):
    email_service.get_email_provider = lambda: provider
    return await pss.request_trial_extension(
        pss.TrialExtensionRequest(**{**GOOD, **over}), fake_request(ip), db)


async def expect_422(db, provider, label, **over):
    before = len((await db.execute(select(ClubOnboardingRequest))).scalars().all())
    try:
        await post(db, provider, **over)
        check(label, False, "no error raised")
    except HTTPException as e:
        after = len((await db.execute(select(ClubOnboardingRequest))).scalars().all())
        check(label, e.status_code == 422 and after == before, f"status={e.status_code} rows {before}->{after}")


async def main() -> int:
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    ids = {k: uuid.uuid4() for k in ("live", "ended", "inactive", "new")}
    async with Session() as db:
        spec = {
            "live": ("Live CC", "live-cc", True, [("core", "trial", NOW + dt.timedelta(days=5))]),
            "ended": ("Ended CC", "ended-cc", True, [("core", "trial", NOW - dt.timedelta(days=9))]),
            "inactive": ("Inactive CC", "inactive-cc", False, [("core", "active", None)]),
        }
        for key, (name, slug, active, subs) in spec.items():
            db.add(Organisation(id=ids[key], name=name, slug=slug, is_active=active))
            await db.flush()
            for mod, status, ends in subs:
                db.add(OrgModuleSubscription(
                    id=uuid.uuid4(), organisation_id=ids[key], module_key=mod, status=status,
                    trial_started_at=NOW - dt.timedelta(days=30), trial_ends_at=ends))
            admin = User(id=uuid.uuid4(), email=f"admin-{key}@example.com", display_name="Ann Admin",
                         password_hash="x")
            db.add(admin)
            await db.flush()
            db.add(ClubMembership(id=uuid.uuid4(), user_id=admin.id, club_id=ids[key], role="club_admin"))
        await db.commit()

    async def fake_ca_search(q):
        return [{"id": str(ids[k]), "name": n} for k, n in
                (("live", "Live CC"), ("ended", "Ended CC"), ("inactive", "Inactive CC"), ("new", "Brand New CC"))]
    sst.playhq_client.search_organisations = fake_ca_search

    print("club search flag")
    async with Session() as db:
        out = {r["name"]: r for r in await sst.search_clubs(q="cc", db=db)}
    paused = lambda n: out[n].get("already_registered_paused", "MISSING")
    check("ended trial is registered + paused", out["Ended CC"]["already_registered"] and paused("Ended CC") is True,
          f"paused={paused('Ended CC')}")
    check("inactive club is paused", paused("Inactive CC") is True, f"paused={paused('Inactive CC')}")
    check("live trial is registered and NOT paused", out["Live CC"]["already_registered"] and paused("Live CC") is False,
          f"paused={paused('Live CC')}")
    check("unregistered club is not paused", not out["Brand New CC"]["already_registered"] and paused("Brand New CC") is False,
          f"paused={paused('Brand New CC')}")

    print("extension request")
    if not hasattr(pss, "request_trial_extension"):
        check("endpoint exists", False, "request_trial_extension is not defined")
        await engine.dispose()
        print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
        return 1
    async with Session() as db:
        provider = FakeProvider()
        res = await post(db, provider, club_org_id=str(ids["ended"]), message="<b>hi</b> & thanks")
        check("returns ok", res == {"ok": True}, str(res))
        check("emails jack and elton", sorted(m.to_email for m in provider.sent) ==
              ["elton@bettersports.com.au", "jack@bettersports.com.au"], str([m.to_email for m in provider.sent]))
        m = provider.sent[0] if provider.sent else SimpleNamespace(subject="", html="", text="", reply_to=None)
        check("subject names the club", "Paused CC" in m.subject, m.subject)
        check("reply-to is the requester", m.reply_to == "sam@example.com", str(m.reply_to))
        check("body carries name, email, phone, role, message",
              all(x in m.text for x in ("Sam Smith", "sam@example.com", "0412 345 678", "Secretary", "<b>hi</b> & thanks")))
        check("html body escapes the message", "&lt;b&gt;hi&lt;/b&gt; &amp; thanks" in m.html and "<b>hi</b>" not in m.html)
        rows = (await db.execute(select(ClubOnboardingRequest))).scalars().all()
        r = rows[0] if rows else None
        check("stored one row with every field", len(rows) == 1 and r.source == "trial_extension_request"
              and (r.name, r.email, r.phone, r.role, r.club) == ("Sam Smith", "sam@example.com", "0412 345 678", "Secretary", "Paused CC")
              and r.message == "<b>hi</b> & thanks" and r.club_org_id == str(ids["ended"]), str(r and r.__dict__))

        print("required fields")
        for field, bad in (("name", " "), ("email", "nope"), ("phone", "123"), ("role", ""), ("message", "  "), ("club_name", "")):
            await expect_422(db, provider, f"{field} missing/invalid -> 422, nothing stored", **{field: bad})

        print("no live provider")
        before = len((await db.execute(select(ClubOnboardingRequest))).scalars().all())
        console = FakeProvider(name="console")
        try:
            await post(db, console)
            check("console provider is a readable failure, not a thank-you", False, "returned ok")
        except HTTPException as e:
            check("console provider is a readable failure, not a thank-you",
                  e.status_code == 503 and "support@bettersports.com.au" in str(e.detail) and not console.sent, str(e.detail))
        after = len((await db.execute(select(ClubOnboardingRequest))).scalars().all())
        check("request still stored when email cannot go", after == before + 1, f"{before}->{after}")
        try:
            await post(db, FakeProvider(ok=False))
            check("provider rejecting every send is a failure", False, "returned ok")
        except HTTPException as e:
            check("provider rejecting every send is a failure", e.status_code == 503, str(e.status_code))

        print("rate limit")
        try:
            for _ in range(pss.EXTENSION_LIMIT + 1):
                await post(db, FakeProvider(), ip="198.51.100.7")
            check("per-IP cap applies", False, "never limited")
        except HTTPException as e:
            check("per-IP cap applies", e.status_code == 429, str(e.status_code))

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print("  FAILED:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
