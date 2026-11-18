"""Better HQ > Reporting > Trial Summary, through the shipped service against a real Postgres.

    createdb verify_trial_summary
    VERIFY_DATABASE_URL=postgresql+asyncpg://.../verify_trial_summary \\
        python -m verification.verify_trial_summary

The ask: one table of every club that signed up, showing when, what it is trialling, how much it
has used the platform and when its trial ends, so new sign-ups and trials about to end can be
followed up. A control run on the previous commit has no service and must REPORT, not crash.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth import modules as mods
from app.models.db import (Base, ClubMembership, MarketingClubContact, Organisation, OrgModuleSubscription,
                           Player, SyncRun, User)

try:
    from app.services import trial_summary as ts
except ImportError:  # the control run: the previous commit has no such module
    ts = None

DB_URL = os.environ.get("VERIFY_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/verify_trial_summary")
NOW = dt.datetime.now(dt.timezone.utc)
D = dt.timedelta(days=1)
PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} — {detail}")
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  ({detail})'}")


USAGE_DDL = """CREATE TABLE IF NOT EXISTS usage_events (
    id BIGSERIAL PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), event_type TEXT NOT NULL DEFAULT 'api',
    method TEXT NOT NULL DEFAULT 'GET', path TEXT NOT NULL DEFAULT '/', route TEXT, status INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER, user_id UUID, org_id UUID, ip_hash TEXT, user_agent TEXT, referer TEXT, metadata JSONB DEFAULT '{}',
    visitor_id UUID, utm_source TEXT, utm_medium TEXT, utm_campaign TEXT, utm_content TEXT, utm_id TEXT, click_id TEXT,
    traffic_source TEXT, landing_path TEXT, country TEXT, time_on_page_ms INTEGER)"""


async def main() -> int:
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("DROP TABLE IF EXISTS usage_events"))
        await conn.execute(text(USAGE_DDL))
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        def org(name, **kw):
            o = Organisation(id=uuid.uuid4(), name=name, slug=name.lower().replace(" ", "-"), is_active=True, **kw)
            db.add(o)
            return o

        def sub(o, module, status, *, started=None, ends=None):
            db.add(OrgModuleSubscription(id=uuid.uuid4(), organisation_id=o.id, module_key=module, status=status,
                                         trial_started_at=started, trial_ends_at=ends))

        def user(name, email, last_login=None):
            u = User(id=uuid.uuid4(), username=name, email=email, password_hash="x", display_name=name.title(),
                     failed_login_count=0, last_login_at=last_login)
            db.add(u)
            return u

        def member(u, o, role="club_admin", primary=False):
            db.add(ClubMembership(id=uuid.uuid4(), user_id=u.id, club_id=o.id, role=role, is_primary_admin=primary))

        soon = org("Soon CC", signup_source="self_serve_ad",
                   signup_attribution={"utm_source": "bettercricket", "utm_medium": "email", "utm_id": "SOON1", "has_signal": True})
        later = org("Later CC")                                           # put on a trial by us
        lapsed = org("Lapsed CC", signup_source="self_serve_organic")
        paying = org("Paying CC", stripe_subscription_id="sub_x")
        archived = org("Archived CC", archived_at=NOW - 2 * D)
        open_ended = org("Open CC")
        never = org("Never Trialled CC")                                  # not a sign-up, not a trial
        quiet = org("Quiet CC", signup_source="self_serve_organic")       # no member with an email
        await db.flush()

        sub(soon, "core", "trial", started=NOW - 12 * D, ends=NOW + 2 * D)
        sub(soon, "select", "trial", started=NOW - 12 * D, ends=NOW + 2 * D)
        sub(later, "core", "trial", started=NOW - 4 * D, ends=NOW + 10 * D)
        sub(lapsed, "core", "trial", started=NOW - 30 * D, ends=NOW - 16 * D)
        sub(paying, "core", "active", started=NOW - 60 * D, ends=NOW - 46 * D)
        sub(paying, "iq", "trial", started=NOW - 3 * D, ends=NOW + 11 * D)
        sub(archived, "core", "trial", started=NOW - 10 * D, ends=NOW + 4 * D)
        sub(open_ended, "core", "trial", started=NOW - 1 * D, ends=None)
        sub(never, "core", "active")
        sub(quiet, "core", "trial", started=NOW - 2 * D, ends=NOW + 12 * D)
        for name, o, at in (("k-soon", soon, NOW - 12 * D), ("k-lapsed", lapsed, NOW - 30 * D), ("k-quiet", quiet, NOW - 2 * D)):
            await db.execute(text("INSERT INTO self_serve_idempotency_keys (idempotency_key, email, status, org_id, created_at) "
                                  "VALUES (:k, 'x@x.example', 'completed', :o, :at)"), {"k": name, "o": o.id, "at": at})

        admin = user("soonadmin", "admin@soon.example", NOW - 1 * D)
        helper = user("soonhelper", "helper@soon.example", NOW - 3 * D)
        staff = user("hq", "hq@bettersports.example", NOW)
        hq = org("HQ")
        await db.flush()
        member(admin, soon, primary=True)
        member(helper, soon, role="selector")
        member(staff, hq, role="super_admin")
        staff.active_club_id = soon.id                                    # a super admin looking at the club
        quiet_user = User(id=uuid.uuid4(), username="quietone", email=None, password_hash="x", failed_login_count=0)
        db.add(quiet_user)
        await db.flush()
        member(quiet_user, quiet)
        mc = await db.execute(text("INSERT INTO marketing_clubs (id, grassroots_guid, name, existing_org_id) VALUES (:i, 'g-q', 'Quiet CC', :o) RETURNING id"),
                              {"i": uuid.uuid4(), "o": quiet.id})
        db.add(MarketingClubContact(id=uuid.uuid4(), marketing_club_id=mc.scalar(), full_name="Quiet Secretary",
                                    email="sec@quiet.example", role_rank=1, source="playhq"))

        # Activity: the admin on three days (two inside the last 7), mostly selection; the helper once;
        # the super admin a lot (must not count).
        for who, ago, path in ((admin, 9 * D, "/admin/selection"), (admin, 2 * D, "/admin/selection/board"),
                               (admin, 2 * D, "/admin/players"), (admin, 1 * D, "/admin/selection?x=1"),
                               (helper, 1 * D, "/admin/availability")) + tuple((staff, 1 * D, "/admin/fees") for _ in range(20)):
            await db.execute(text("INSERT INTO usage_events (created_at, event_type, path, user_id) VALUES (:at, 'page_view', :p, :u)"),
                             {"at": NOW - ago, "p": path, "u": who.id})
        for i in range(3):
            db.add(Player(id=uuid.uuid4(), name=f"P{i}", organisation_id=soon.id))
        db.add(SyncRun(id=uuid.uuid4(), org_id=soon.id, kind="full", status="success", completed_at=NOW - 11 * D, stats={}))
        await db.commit()

    async with Session() as db:
        res = await ts.build_summary(db, NOW) if ts else {}
    rows = {c.get("name"): c for c in (res or {}).get("clubs", [])}

    def r(name):
        return rows.get(name, {})

    print("who is listed")
    check("a self-serve sign-up is listed", "Soon CC" in rows, str(sorted(rows)))
    check("a club we put on a trial ourselves is listed", "Later CC" in rows)
    check("a club that never signed up or trialled is not", "Never Trialled CC" not in rows and len(rows) >= 7, str(sorted(rows)))
    check("newest sign-up first", list(rows)[:1] == ["Open CC"], str(list(rows)))

    print("status and trial end")
    check("a trial ending in 2 days is on trial and ending soon",
          r("Soon CC").get("status") == "on_trial" and r("Soon CC").get("ending_soon") is True and r("Soon CC").get("days_left") == 2,
          str({k: r("Soon CC").get(k) for k in ("status", "ending_soon", "days_left")}))
    check("a trial ending in 10 days is not ending soon",
          r("Later CC").get("status") == "on_trial" and r("Later CC").get("ending_soon") is False and r("Later CC").get("days_left") == 10)
    check("a lapsed trial reads as ended, with its end date",
          r("Lapsed CC").get("status") == "trial_ended" and (r("Lapsed CC").get("trial_ended_at") or "")[:10] == (NOW - 16 * D).date().isoformat())
    check("a club paying for one module and trialling another is paying, with the trial's end shown",
          r("Paying CC").get("status") == "paying" and (r("Paying CC").get("trial_ends_at") or "")[:10] == (NOW + 11 * D).date().isoformat())
    check("an archived club says so", r("Archived CC").get("status") == "archived")
    check("an open-ended trial has no end date and says so",
          r("Open CC").get("trial_ends_at") is None and r("Open CC").get("trial_open_ended") is True)

    print("what they are trialling")
    names = {m.get("name"): m.get("status") for m in r("Soon CC").get("modules", [])}
    check("both trial modules are named as the club's Account page names them",
          names == {"BetterStats": "trial", "BetterSelect": "trial"}, str(names))
    if ts:
        async with Session() as db:
            from sqlalchemy import select
            from sqlalchemy.orm import selectinload
            o = (await db.execute(select(Organisation).options(selectinload(Organisation.module_subscriptions))
                                  .where(Organisation.name == "Paying CC"))).scalar_one()
            account = {p["name"]: p["status"] for p in mods.account_plan_status(o, NOW) if p["status"] != "never_trialed"}
        check("the module statuses match account_plan_status exactly",
              {m["name"]: m["status"] for m in r("Paying CC").get("modules", [])} == account, str(account))
    else:
        check("the module statuses match account_plan_status exactly", False, "no service")

    print("sign-up")
    check("the sign-up date is the registration's own timestamp",
          (r("Soon CC").get("signed_up_at") or "")[:10] == (NOW - 12 * D).date().isoformat() and r("Soon CC").get("signed_up_from") == "registration")
    check("a club set up by us dates from its first trial start, and says so",
          r("Later CC").get("signed_up_from") == "trial_start" and r("Later CC").get("signup_channel") == "Set up by us")
    check("where a self-serve sign-up came from is read from its stored attribution",
          (r("Soon CC").get("origin") or {}).get("channel") == "email", str(r("Soon CC").get("origin")))

    print("activity: the club's own people only")
    act = r("Soon CC").get("activity") or {}
    check("page views count the club's people and not the super admin", act.get("views") == 5, str(act))
    check("active days are counted across the whole trial", act.get("active_days") == 3, str(act))
    check("...and in the last 7 days", act.get("active_days_recent") == 2 and act.get("views_recent") == 4, str(act))
    check("two people used it", act.get("active_people") == 2, str(act))
    check("the most-used area is first", (act.get("top_areas") or [{}])[0].get("area") == "selection", str(act.get("top_areas")))
    check("the super admin's own area never appears", all(a.get("area") != "fees" for a in act.get("top_areas") or []))
    check("members exclude the super admin", r("Soon CC").get("members") == 2, str(r("Soon CC").get("members")))
    check("last sign-in is the club's, not the super admin's (who signed in today)",
          (r("Soon CC").get("last_login_at") or "")[:10] == (NOW - 1 * D).date().isoformat(), str(r("Soon CC").get("last_login_at")))
    check("a club with no activity reads zero, not missing", (r("Later CC").get("activity") or {}).get("views") == 0)
    check("players and the last good sync are reported",
          (r("Soon CC").get("data") or {}).get("players") == 3 and ((r("Soon CC").get("data") or {}).get("last_sync_at") or "")[:10] == (NOW - 11 * D).date().isoformat())

    print("contact")
    check("the primary admin is the contact", r("Soon CC").get("admin_email") == "admin@soon.example"
          and r("Soon CC").get("contact_source") == "club_admin")
    check("a club with no member email falls back to the Club Directory, and says so",
          r("Quiet CC").get("admin_email") == "sec@quiet.example" and r("Quiet CC").get("contact_source") == "club_directory",
          str({k: r("Quiet CC").get(k) for k in ("admin_email", "contact_source")}))

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
