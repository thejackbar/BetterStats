"""The public trial's details step asks for first name and email only (v9.144.2).

Before: six fields (first, last, display name, username, email, mobile) were all required, and the
wizard lost about 9 in 10 visitors at that step. Now the server fills the display name (the name as
typed) and the username (the email itself, since login is by username, so they sign in with the
address they just verified), and last name and mobile are optional. Those details are offered later
on the dashboard through the person's own profile (GET/PATCH /club-admin/account/profile), never as
a gate.

Kept and checked beside it so the change cannot widen: first name and a valid email are still
required, a mobile that IS sent is still checked, a taken email is still refused, the password is
still required, the session cookie and the server-side CompleteRegistration still happen, and the
funnel's new "Sign-up form opened" step is on all three step lists.

Runs the SHIPPED `validate_admin`, `submit`, public `submit` and the profile routes against a real
Postgres. Only outbound edges are stubbed (Cricket Australia, the sync kick-off, the address lookup,
the verification table, the admin-list queue, the usage beacon).

    python -m verification.verify_trial_two_field_signup
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import BackgroundTasks, HTTPException, Response
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

import app.models.db as mdb
from app.models.db import Base, Organisation, SelfServeAcknowledgement, User
from app.routers import organisations as orgs_router
from app.routers import public_self_serve as pss
from app.routers import self_serve_trial as sst
from app.services import crm_rules

DB_URL = os.environ.get("VERIFY_DATABASE_URL", "postgresql+asyncpg://postgres@127.0.0.1:55432/verify_two_field_signup")
PASS: list[str] = []
FAIL: list[str] = []
NOW = dt.datetime.now(dt.timezone.utc)
PW = "Str0ng!Passw0rd#1"


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} — {detail}")
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  ({detail})'}")


def fake_request(ip="203.0.113.5") -> Request:
    return Request({"type": "http", "method": "POST", "path": "/", "query_string": b"",
                    "headers": [(b"user-agent", b"verify"), (b"x-real-ip", ip.encode())], "client": (ip, 1234)})


async def safe(coro):
    """The reply, or {'_http': status} when the route refuses: a control run REPORTS, it does not crash."""
    try:
        return await coro
    except HTTPException as e:
        return {"_http": e.status_code, "_detail": e.detail}
    except Exception as e:  # noqa: BLE001 - a control run must report, not crash
        return {"_error": f"{type(e).__name__}: {e}"[:160]}


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

    async def ca_org(org_id):
        return {"id": org_id, "name": "x"}
    sst.playhq_client.get_organisation = ca_org
    async def no_address(db, *, org_id, name):
        return None
    sst._resolve_club_address = no_address
    async def is_verified(db, email):
        return True
    sst.verification.is_verified = is_verified
    import app.services.admin_contact_list as acl
    acl.queue_sync = lambda *_a, **_k: None
    pss.record_event_bg = lambda **_k: None
    async def onboard(db, background_tasks, org_id, org_name="", auto_yearbooks=False):
        org = Organisation(id=uuid.UUID(org_id), name=org_name, slug=f"c-{org_id[:8]}", is_active=True)
        db.add(org)
        await db.commit()
        return org, uuid.uuid4(), org_name
    orgs_router._onboard_club_core = onboard

    # Someone whose USERNAME is an email address that is not their email: the default username
    # must step around it. And someone whose email is taken outright.
    async with Session() as db:
        db.add(User(id=uuid.uuid4(), email="other@else.example", username="clash@club.example", password_hash="x"))
        db.add(User(id=uuid.uuid4(), email="taken@club.example", username="takenperson", password_hash="x"))
        db.add(User(id=uuid.uuid4(), email="z@else.example", username="clash", password_hash="x"))
        await db.commit()

    async def validate(**kw):
        async with Session() as db:
            return await safe(sst.validate_admin(sst.ValidateAdminRequest(**kw), db))

    # ── 1. the details check with two fields ─────────────────────────────────
    print("details check")
    r = await validate(first_name="Sam", email="sam@club.example")
    check("first name + email alone are valid", r.get("valid") is True and not r.get("errors"), str(r))
    check("the username it will use is the email", (r.get("normalised") or {}).get("username") == "sam@club.example", str(r))
    r = await validate(first_name="", email="sam@club.example")
    check("first name is still required", r.get("valid") is False and "first_name" in (r.get("errors") or {}), str(r))
    r = await validate(first_name="Sam", email="not-an-email")
    check("a valid email is still required", r.get("valid") is False and "email" in (r.get("errors") or {}), str(r))
    r = await validate(first_name="Sam", email="taken@club.example")
    check("a taken email is still refused", r.get("valid") is False and "email" in (r.get("errors") or {}), str(r))
    r = await validate(first_name="Sam", email="sam@club.example", mobile_number="12")
    check("a mobile that is sent is still checked", r.get("valid") is False and "mobile_number" in (r.get("errors") or {}), str(r))
    r = await validate(first_name="Sam", email="clash@club.example")
    u = (r.get("normalised") or {}).get("username")
    check("an email already used as someone's username falls back to a free one",
          r.get("valid") is True and u not in ("clash@club.example", "clash") and (u or "").startswith("clash"), str(r))
    long_mail = ("a" * 40) + "@club.example"
    r = await validate(first_name="Sam", email=long_mail)
    check("a long email still works as the username (over the 32 character limit)", r.get("valid") is True, str(r))
    r = await validate(first_name="Sam", email="sam@club.example", username="ab")
    check("control: a username that IS sent is still judged (too short)", "username" in (r.get("errors") or {}), str(r))

    # ── 2. the public submit with two fields ─────────────────────────────────
    print("public submit")
    org_id = str(uuid.uuid4())
    async with Session() as db:
        db.add(SelfServeAcknowledgement(id=uuid.uuid4(), email="sam@club.example", club_name="Sam CC",
                                        terms_version="x", privacy_version="x", accepted_at=NOW))
        await db.commit()

    def pub(key, **kw):
        base = dict(idempotency_key=key, org_id=org_id, name="Sam CC", first_name="Sam", email="sam@club.example",
                    password=PW, confirm_password=PW, modules=[], visitorId=str(uuid.uuid4()))
        base.update(kw)
        return pss.PublicSubmitRequest(**base)

    bg0 = BackgroundTasks()
    async with Session() as db:
        nopw = await safe(pss.submit(pub("k0", password="", confirm_password=""), fake_request("198.51.100.30"), Response(), bg0, db))
    check("the password is still required", nopw.get("_http") == 422, str(nopw)[:200])

    response = Response()
    bg = BackgroundTasks()
    async with Session() as db:
        res = await safe(pss.submit(pub("k1"), fake_request("198.51.100.31"), response, bg, db))
    check("registration completes with first name, email and password only", res.get("status") == "completed", str(res)[:300])
    check("the reply says what they sign in with", res.get("username") == "sam@club.example", str(res)[:300])
    check("they are signed in (session cookie)", "set-cookie" in response.headers, str(dict(response.headers)))
    task_names = [getattr(t.func, "__name__", "") for t in bg.tasks]
    check("the server-side CompleteRegistration is still queued", "send_complete_registration_event" in task_names, str(task_names))
    async with Session() as db:
        user = (await db.execute(select(User).where(User.email == "sam@club.example"))).scalars().first()
    check("account: username is the email", user is not None and user.username == "sam@club.example", str(user and user.username))
    check("account: display name is the first name", user is not None and user.display_name == "Sam", str(user and user.display_name))
    check("account: no surname or mobile invented", user is not None and user.last_name is None and user.mobile_number is None,
          str(user and (user.last_name, user.mobile_number)))
    check("account: the dashboard profile prompt is pending",
          user is not None and (user.ui_preferences or {}).get("profile_nudge") == "pending", str(user and user.ui_preferences))

    # ── 3. the profile prompt on the dashboard ───────────────────────────────
    print("profile prompt")
    from app.routers import club_admin as ca
    if not hasattr(ca, "get_own_profile"):
        check("the profile routes exist", False, "club_admin has no get_own_profile")
    else:
        p = await ca.get_own_profile(current_user=user)
        check("the prompt shows, with the sign-in name", p.get("nudge") is True and p.get("username") == "sam@club.example", str(p))
        async with Session() as db:
            me = await db.get(User, user.id)
            bad = await safe(ca.patch_own_profile(ca.OwnProfilePatch(mobile_number="12"), current_user=me, db=db))
        check("a bad mobile is refused", bad.get("_http") == 422, str(bad))
        async with Session() as db:
            me = await db.get(User, user.id)
            ok = await safe(ca.patch_own_profile(ca.OwnProfilePatch(last_name="Smith", mobile_number="0412 345 678"),
                                                 current_user=me, db=db))
        check("saving fills the details and retires the prompt",
              ok.get("last_name") == "Smith" and ok.get("mobile_number") == "0412 345 678" and ok.get("nudge") is False, str(ok))
        check("a field not sent is left alone (display name)", ok.get("display_name") == "Sam", str(ok))
        async with Session() as db:
            me = await db.get(User, user.id)
            ok2 = await safe(ca.patch_own_profile(ca.OwnProfilePatch(last_name=""), current_user=me, db=db))
        check("an explicit blank clears (surname)", ok2.get("last_name") == "" and ok2.get("mobile_number") == "0412 345 678", str(ok2))
        async with Session() as db:
            other = (await db.execute(select(User).where(User.username == "takenperson"))).scalars().first()
            other.ui_preferences = {"profile_nudge": "pending", "keep": 1}
            await db.commit()
            other = await db.get(User, other.id)
            d = await safe(ca.patch_own_profile(ca.OwnProfilePatch(dismiss_nudge=True), current_user=other, db=db))
            other = await db.get(User, other.id)
        check("closing retires the prompt and keeps other preferences",
              d.get("nudge") is False and other.ui_preferences == {"keep": 1}, str((d, other.ui_preferences)))
        async with Session() as db:
            plain = (await db.execute(select(User).where(User.username == "clash"))).scalars().first()
        check("control: an account not made by the trial gets no prompt",
              (await ca.get_own_profile(current_user=plain)).get("nudge") is False)

    # ── 4. the funnel step lists ─────────────────────────────────────────────
    print("funnel")
    from app.routers import usage
    from app.services import meta_ads
    check("the beacon allowlist takes signup_form_opened", "signup_form_opened" in pss.FUNNEL_STEPS)
    keys = [k for k, _ in meta_ads.REGISTRATION_STEP_ORDER]
    check("the Meta Ads funnel has it between Club selected and Admin details",
          "signup_form_opened" in keys and keys.index("club_prepared") < keys.index("signup_form_opened") < keys.index("admin_details_completed"), str(keys))
    check("every Meta Ads funnel step is on the allowlist", all(k in pss.FUNNEL_STEPS for k in keys))
    ukeys = [k for k, _ in usage._REG_STEP_ORDER]
    check("the Usage page step list matches", ukeys == keys[1:], str(ukeys))

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print(f"  FAILED: {f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
