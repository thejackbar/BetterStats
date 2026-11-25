"""Free trial signups count a registration the campaign's ad brought in, even when its stored
first touch says otherwise (v9.152.3).

    VERIFY_DATABASE_URL=postgresql+asyncpg://postgres:pg@127.0.0.1:5432/verify_visit_attr \\
        python verification/verify_meta_ads_visit_attribution.py

Reported: since the 10 Nov restart the club list showed at least 12 completed clubs whose
"Where from" was "Meta ad", while Free trial signups said 6. The club list reads the visitors'
own page views; the count read only `signup_attribution`, the browser's FIRST touch. So a browser
first brought by an earlier campaign's ad, or an ad clicked in Facebook's in-app browser and
finished in Safari, was a Meta club on the list and not a trial signup.

Real Postgres, shipped service functions and the shipped /ad-signups route body. Every new key
is read presence-safe so a control run on the previous commit REPORTS, not crashes. Each
"left out" check is paired with one that the same data could be counted.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

import app.models.db as mdb  # noqa: E402
from app.models.db import Base, Organisation  # noqa: E402
from app.services import meta_ads as m  # noqa: E402

DB_URL = os.environ.get("VERIFY_DATABASE_URL", "postgresql+asyncpg://postgres:pg@127.0.0.1:5432/verify_visit_attr")
NEW = "120251284365570121"
NOW = dt.datetime.now(dt.timezone.utc)
D, H = dt.timedelta(days=1), dt.timedelta(hours=1)
PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))


# Copied from the lifespan DDL column for column (CLAUDE.md rule 24).
USAGE_DDL = """CREATE TABLE IF NOT EXISTS usage_events (
    id BIGSERIAL PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), event_type TEXT NOT NULL DEFAULT 'api',
    method TEXT NOT NULL DEFAULT 'GET', path TEXT NOT NULL DEFAULT '/', route TEXT, status INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER, user_id UUID, org_id UUID, ip_hash TEXT, user_agent TEXT, referer TEXT, metadata JSONB DEFAULT '{}',
    visitor_id UUID, utm_source TEXT, utm_medium TEXT, utm_campaign TEXT, utm_content TEXT, utm_id TEXT, click_id TEXT,
    traffic_source TEXT, landing_path TEXT, country TEXT, region TEXT, city TEXT, lat DOUBLE PRECISION,
    lng DOUBLE PRECISION, time_on_page_ms INTEGER, resolved_marketing_club_id UUID)"""

NEW_TAGS = dict(utm_source="meta", utm_medium="paid_social", utm_campaign="BC_AU_Trial_CBO_Sep2026",
                utm_content="check_out_your_club_v2", has_signal=True)
OLD_TAGS = dict(utm_source="facebook", utm_medium="paid_social", utm_campaign="trial_evergreen_sep2026",
                utm_content="club_history_hero", has_signal=True)
EMAIL_ATTR = dict(landing_path="/trial?utm_id=ABC123", has_signal=True)


async def main() -> int:
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("DROP TABLE IF EXISTS usage_events"))
        await conn.execute(text(USAGE_DDL))
        from app.services.webinar_ddl import STATEMENTS as WEBINAR_DDL  # the shipped list, as the lifespan runs it
        for stmt in WEBINAR_DDL:
            await conn.execute(text(stmt))
        await conn.execute(text("""CREATE TABLE IF NOT EXISTS platform_settings (
            id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1), settings JSONB NOT NULL DEFAULT '{}',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"""))
        await conn.execute(text("INSERT INTO platform_settings (id, settings) VALUES (1, CAST(:s AS jsonb))"),
                           {"s": json.dumps({"meta_campaign_id": NEW})})
    Session = async_sessionmaker(engine, expire_on_commit=False)
    mdb.async_session_maker = Session
    m.CAMPAIGN_COUNTS_FROM[NEW] = NOW - 5 * D

    async def page_view(visitor, when, tags=None):
        tags = {k: v for k, v in (tags or {}).items() if k.startswith("utm_")}
        qs = "&".join(f"{k}={v}" for k, v in tags.items())
        async with Session() as db:
            await db.execute(text("""INSERT INTO usage_events
                (created_at, event_type, path, visitor_id, utm_source, utm_medium, utm_campaign, utm_content, traffic_source)
                VALUES (:at, 'page_view', :path, :v, :us, :um, :uc, :uco, :ts)"""),
                {"at": when, "path": "/trial" + (("?" + qs) if qs else ""), "v": visitor,
                 "us": tags.get("utm_source"), "um": tags.get("utm_medium"), "uc": tags.get("utm_campaign"),
                 "uco": tags.get("utm_content"),
                 "ts": "facebook" if tags.get("utm_source") in ("meta", "facebook") else None})
            await db.commit()

    async def picked(visitor, when, club):
        async with Session() as db:
            await db.execute(text("""INSERT INTO usage_events (created_at, event_type, route, path, visitor_id, metadata)
                VALUES (:at, 'self_serve_step', 'club_prepared', '/trial', :v, CAST(:m AS jsonb))"""),
                {"at": when, "v": visitor, "m": json.dumps({"club_name": club})})
            await db.commit()

    async def registered(club, when, attribution, visitor):
        async with Session() as db:
            org = Organisation(id=uuid.uuid4(), name=club, slug=club.lower().replace(" ", "-"), is_active=True)
            db.add(org)
            await db.flush()
            await db.execute(text("UPDATE organisations SET signup_source = 'self_serve_ad', "
                                  "signup_attribution = CAST(:a AS jsonb) WHERE id = :i"),
                             {"a": json.dumps(attribution) if attribution is not None else None, "i": org.id})
            await db.execute(text("INSERT INTO self_serve_idempotency_keys (idempotency_key, email, status, org_id, created_at) "
                                  "VALUES (:k, 'x@x.example', 'completed', :o, :at)"),
                             {"k": str(uuid.uuid4()), "o": org.id, "at": when})
            # The submit's own breadcrumb: visitor and org (public_self_serve.submit).
            await db.execute(text("""INSERT INTO usage_events (created_at, event_type, method, path, route, status, visitor_id, org_id)
                VALUES (:at, 'conversion', 'POST', '/public/self-serve/submit', '/public/self-serve/submit', 200, :v, :o)"""),
                             {"at": when, "v": visitor, "o": org.id})
            await db.commit()
            return str(org.id)

    V = {k: uuid.uuid4() for k in ("tagged", "oldfirst", "inapp", "safari", "email", "organic", "later", "oldonly")}

    # 1. Baseline: stored attribution is this campaign's. Counted before and after the change.
    await page_view(V["tagged"], NOW - 2 * D, NEW_TAGS)
    await registered("Tagged CC", NOW - 2 * D + H, NEW_TAGS, V["tagged"])
    # 2. First came through the OLD campaign's ad in October, then this campaign's ad after the restart.
    await page_view(V["oldfirst"], NOW - 40 * D, OLD_TAGS)
    await page_view(V["oldfirst"], NOW - 1 * D, NEW_TAGS)
    await registered("Old First CC", NOW - 1 * D + H, OLD_TAGS, V["oldfirst"])
    # 3. Clicked in the in-app browser and picked the club there, finished in Safari with no signal.
    await page_view(V["inapp"], NOW - 3 * D, NEW_TAGS)
    await picked(V["inapp"], NOW - 3 * D + 0.1 * H, "Handoff CC")
    await page_view(V["safari"], NOW - 3 * D + 2 * H)
    await registered("Handoff CC", NOW - 3 * D + 3 * H, {"has_signal": False, "landing_path": "/trial"}, V["safari"])
    # 4. Our outreach email first, then an ad view: stays email, as "Where from" ranks it.
    await page_view(V["email"], NOW - 2 * D, NEW_TAGS)
    await registered("Email CC", NOW - 2 * D + H, EMAIL_ATTR, V["email"])
    # 5. Organic, no ad anywhere.
    await page_view(V["organic"], NOW - 2 * D)
    await registered("Organic CC", NOW - 2 * D + H, None, V["organic"])
    # 6. Only saw the ad AFTER registering: the ad did not bring the registration.
    await page_view(V["later"], NOW - 2 * D)
    await registered("Later Ad CC", NOW - 2 * D + H, None, V["later"])
    await page_view(V["later"], NOW - 1 * D, NEW_TAGS)
    # 7. Only ever the old campaign's ad.
    await page_view(V["oldonly"], NOW - 2 * D, OLD_TAGS)
    await registered("Old Only CC", NOW - 2 * D + H, OLD_TAGS, V["oldonly"])

    counted_expected = {"Tagged CC", "Old First CC", "Handoff CC"}

    async with Session() as db:
        count = await m.get_registration_count(db)
        outside = await m.get_registrations_outside_campaign(db)
        since = await m.get_registration_count_since(db, (NOW - 5 * D).date())
        sel = await m.get_selected_clubs(db, 30, "all")
        regs = await m.attributed_registrations(db)
    via = {c["name"]: c.get("via_campaign") for c in sel["clubs"]}

    print("the headline count")
    check("Free trial signups counts the three the campaign's ad brought in", count == 3, f"count={count}")
    check("the baseline (own tags) still counts", via.get("Tagged CC") is True, str(via))
    check("first touch was the old campaign, then this campaign's ad: counted",
          via.get("Old First CC") is True, str(via))
    check("ad clicked in the in-app browser, finished elsewhere: counted",
          via.get("Handoff CC") is True, str(via))
    check("the outside-campaign note counts the other four", outside == 4, f"outside={outside}")
    check("the since-the-change count agrees with the headline", since.get("count") == 3, str(since))

    print("what stays out")
    check("our outreach email stays email even with an ad view", via.get("Email CC") is False, str(via))
    fn = getattr(m, "campaign_visit_touches", None)
    async with Session() as db:
        touched = await fn(db) if fn else {}
        email_id = (await db.execute(text("SELECT id::text FROM organisations WHERE name = 'Email CC'"))).scalar()
    check("but its visitor DID reach /trial through the campaign's ad (so the check above could fail)",
          email_id in touched, str(sorted(touched)))
    check("organic stays out", via.get("Organic CC") is False, str(via))
    check("an ad seen only AFTER registering does not count", via.get("Later Ad CC") is False, str(via))
    check("only the old campaign's ad: stays out", via.get("Old Only CC") is False, str(via))
    check("every one of the seven is on the club list as completed",
          {c["name"] for c in sel["clubs"] if c["furthest_step"] == "Registration completed"}
          >= counted_expected | {"Email CC", "Organic CC", "Later Ad CC", "Old Only CC"},
          str({c["name"]: c["furthest_step"] for c in sel["clubs"]}))

    print("credit goes to the ad that brought the visit")
    tags = {r.get("org_id"): r.get("campaign_tags") for r in regs}
    names = {r.get("org_id"): None for r in regs}
    async with Session() as db:
        for oid in list(names):
            names[oid] = (await db.execute(text("SELECT name FROM organisations WHERE id = CAST(:i AS uuid)"),
                                           {"i": oid})).scalar() if oid else None
    by_name = {names[k]: v for k, v in tags.items() if k}
    check("Old First CC is credited to this campaign's creative, not the October one",
          (by_name.get("Old First CC") or {}).get("utm_content") == "check_out_your_club_v2", str(by_name.get("Old First CC")))
    async with Session() as db:
        creatives = await m.get_creative_performance(db, [])
    signups = {c["utm_content"]: c["trial_signups"] for c in creatives}
    check("the creative table credits all three to check_out_your_club_v2",
          signups.get("check_out_your_club_v2") == 3, str(signups))

    print("the signups table (shipped /ad-signups route body)")
    from app.routers import meta_ads as r
    async with Session() as db:
        try:
            table = await r.ad_signups(db=db, _=None)
        except Exception as e:  # report, not crash
            table = {"error": repr(e)}
    rows = table.get("signups") or table.get("rows") or (table if isinstance(table, list) else [])
    listed = {(x.get("club_name") or x.get("name") or "") for x in rows} if isinstance(rows, list) else set()
    check("the signups table lists the same three", listed == counted_expected, f"{listed} {str(table)[:300]}")

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
