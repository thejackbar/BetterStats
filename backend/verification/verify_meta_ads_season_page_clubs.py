"""Clubs whose season page (/preview/<token>) a visitor opened, on the Meta Ads club list.

    createdb verify_season_page
    VERIFY_DATABASE_URL=postgresql+asyncpg://.../verify_season_page \\
        python -m verification.verify_meta_ads_season_page_clubs

The report: the Usage feed showed a Melbourne visitor on a club's season page, tracked to that
club by our outreach email's code, and the Meta Ads club list did not have the club in any view.
The list was built only from the /trial search and click beacons; the season page's own `view`
beacon (event_type 'teaser') was read by nothing on that page.

Measured through the shipped `meta_ads.get_season_page_clubs` against a real Postgres. A control
run on the previous commit has no such function and must REPORT every check as failing, not crash.
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

import app.models.db as mdb
from app.models.db import Base
from app.services import meta_ads as m

DB_URL = os.environ.get("VERIFY_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/verify_season_page")
NEW = "120251284365570121"
NOW = dt.datetime.now(dt.timezone.utc)
H, D = dt.timedelta(hours=1), dt.timedelta(days=1)
PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} — {detail}")
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  ({detail})'}")


# Column for column with main.py's usage_events, including the later ALTERs these reads touch.
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
        await conn.execute(text("""CREATE TABLE IF NOT EXISTS platform_settings (
            id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1), settings JSONB NOT NULL DEFAULT '{}',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"""))
        await conn.execute(text("INSERT INTO platform_settings (id, settings) VALUES (1, CAST(:s AS jsonb))"),
                           {"s": json.dumps({"meta_campaign_id": NEW})})
    Session = async_sessionmaker(engine, expire_on_commit=False)
    mdb.async_session_maker = Session

    async with Session() as db:
        async def club(name, org=None):
            cid = uuid.uuid4()
            await db.execute(text("INSERT INTO marketing_clubs (id, grassroots_guid, name, existing_org_id) VALUES (:i, :g, :n, :o)"),
                             {"i": cid, "g": f"guid-{name}", "n": name, "o": org})
            return cid

        async def org(name, sub=None):
            oid = uuid.uuid4()
            await db.execute(text("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, :n, :s, true)"),
                             {"i": oid, "n": name, "s": name.lower().replace(" ", "-")})
            if sub:
                await db.execute(text("INSERT INTO org_module_subscriptions (id, organisation_id, module_key, status, trial_ends_at) "
                                      "VALUES (:i, :o, 'select', :st, :end)"),
                                 {"i": uuid.uuid4(), "o": oid, "st": sub[0], "end": sub[1]})
            return oid

        async def visit(cid, *, ago=2 * H, page_view=None, routes=("view",), visitor=None, user=None):
            v = visitor or uuid.uuid4()
            if page_view is not None:
                await db.execute(text("""INSERT INTO usage_events (created_at, event_type, path, visitor_id, user_id, utm_source,
                    utm_medium, utm_campaign, utm_content, utm_id) VALUES (:at, 'page_view', :p, :v, :u, :us, :um, :uc, :ucn, :ui)"""),
                    {"at": NOW - ago - H, "p": page_view.get("path", "/preview/tok"), "v": v, "u": user,
                     "us": page_view.get("utm_source"), "um": page_view.get("utm_medium"), "uc": page_view.get("utm_campaign"),
                     "ucn": page_view.get("utm_content"), "ui": page_view.get("utm_id")})
            for r in routes:
                await db.execute(text("""INSERT INTO usage_events (created_at, event_type, method, path, route, status, visitor_id, metadata)
                    VALUES (:at, 'teaser', 'POST', '/public/teaser/event', :r, 200, :v, CAST(:meta AS jsonb))"""),
                    {"at": NOW - ago, "r": r, "v": v, "meta": json.dumps({"marketing_club_id": str(cid), "version": 1})})
            return v

        email_club = await club("Melbourne Crickeroos")
        await visit(email_club, page_view={"utm_id": "MELB1"})          # the report: outreach code only, "Direct" on Usage
        claim_club = await club("Claimer CC")
        await visit(claim_club, page_view={"utm_id": "CLM1"}, routes=("view", "claim_go"))
        meta_club = await club("Meta Ad CC")
        await visit(meta_club, page_view={"utm_source": "meta", "utm_medium": "paid_social",
                                          "utm_campaign": "BC_AU_Trial_CBO_Sep2026", "utm_content": "feed", "utm_id": "META1"})
        old_club = await club("Old View CC")
        await visit(old_club, ago=10 * D, page_view={"utm_id": "OLD1"})

        # A super admin's browser: signed in on one page view, then opened a club's season page.
        admin = uuid.uuid4()
        await db.execute(text("INSERT INTO users (id, username, email, password_hash, failed_login_count) VALUES (:i, 'sa', 'sa@x.example', 'x', 0)"), {"i": admin})
        admin_org = await org("HQ")
        await db.execute(text("INSERT INTO club_memberships (id, user_id, club_id, role) VALUES (:i, :u, :c, 'super_admin')"),
                         {"i": uuid.uuid4(), "u": admin, "c": admin_org})
        staff_club = await club("Staff Looked CC")
        await visit(staff_club, page_view={"path": "/admin/directory"}, user=admin)
        # A signed-in club admin (not staff) is still counted.
        member = uuid.uuid4()
        await db.execute(text("INSERT INTO users (id, username, email, password_hash, failed_login_count) VALUES (:i, 'ca', 'ca@x.example', 'x', 0)"), {"i": member})
        await db.execute(text("INSERT INTO club_memberships (id, user_id, club_id, role) VALUES (:i, :u, :c, 'club_admin')"),
                         {"i": uuid.uuid4(), "u": member, "c": admin_org})
        member_club = await club("Member Looked CC")
        await visit(member_club, page_view={"path": "/admin"}, user=member)

        live = await club("Live Customer CC", await org("Live Customer CC", ("trial", NOW + 5 * D)))
        await visit(live, page_view={})
        lapsed = await club("Lapsed Trial CC", await org("Lapsed Trial CC", ("trial", NOW - 5 * D)))
        await visit(lapsed, page_view={})
        await db.commit()

    fn = getattr(m, "get_season_page_clubs", None)

    async def call(days, scope):
        if fn is None:
            return {}
        async with Session() as db:
            return await fn(db, days, scope)

    def names(res, key="clubs"):
        return {c.get("name") for c in (res or {}).get(key, [])}

    def row(res, name):
        return next((c for c in (res or {}).get("clubs", []) if c.get("name") == name), {})

    every = await call(7, "all")
    print("all traffic, 7 days")
    check("the reported club is listed: season page opened from an outreach email, no /trial search",
          "Melbourne Crickeroos" in names(every), str(names(every)))
    check("its origin is our outreach email (the club code on the visit)",
          (row(every, "Melbourne Crickeroos").get("origin") or {}).get("channel") == "email", str(row(every, "Melbourne Crickeroos")))
    check("a press of the claim button is reported", row(every, "Claimer CC").get("pressed_claim") is True)
    check("a plain view is not reported as a claim press", row(every, "Melbourne Crickeroos").get("pressed_claim") is False)
    check("a Meta teaser ad visit is listed and tagged Meta", row(every, "Meta Ad CC").get("via_meta") is True)
    check("a view by a browser a super admin signed in on is left out", "Staff Looked CC" not in names(every), str(names(every)))
    check("...while a view by a signed-in club admin (not staff) is kept", "Member Looked CC" in names(every), str(names(every)))
    check("a live customer's own season page is left out", "Live Customer CC" not in names(every))
    check("...while a club whose trial lapsed is a lead again", "Lapsed Trial CC" in names(every))
    check("a view outside the period is left out", "Old View CC" not in names(every))
    month = await call(30, "all")
    check("...and comes back with a longer period", "Old View CC" in names(month), str(names(month)))

    print("this campaign")
    camp = await call(7, "campaign")
    check("campaign scope keeps the campaign's own ad visit", "Meta Ad CC" in names(camp), str(names(camp)))
    check("campaign scope leaves the outreach email visit out", "Melbourne Crickeroos" not in names(camp))
    check("...and counts what it left out", (camp or {}).get("outside_campaign", 0) >= 3, str((camp or {}).get("outside_campaign")))

    print("flag as test")
    if fn is not None:
        from app.services import platform_settings
        async with Session() as db:
            await platform_settings.hide_meta_selection(db, "Melbourne Crickeroos")
            await db.commit()
    hid = await call(7, "all")
    check("a club flagged as test moves to the hidden list",
          "Melbourne Crickeroos" in names(hid, "hidden_clubs") and "Melbourne Crickeroos" not in names(hid))

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
