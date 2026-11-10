"""The restarted BC_AU_Trial_CBO_Sep2026 campaign, end to end: a registration that
came through the ad is stored with the ad's tags and Meta Ads HQ counts it under
the right campaign and the right creative row.

    python -m verification.verify_meta_ads_new_tags_e2e

Needs the attribution records the REAL browser produced, so run the browser leg first:

    npx vite --port 5204 &
    ATTR_OUT=/tmp/attr node frontend/verification/verify_ad_attribution_capture_browser.mjs
    ATTR_DIR=/tmp/attr VERIFY_DATABASE_URL=postgresql+asyncpg://.../verify_ad_attr \\
        python -m verification.verify_meta_ads_new_tags_e2e

Runs the SHIPPED public `submit` (so `signup_attribution` is written by the real
`_clean_attribution` path), the SHIPPED `get_latest_summary`, `get_registration_count`
and the `/ad-signups` route body, against a real Postgres. Only outbound edges are stubbed
(Cricket Australia, the sync kick-off, the address lookup, the verification table, the admin
list queue, the email provider, the usage beacon).

Four registrations, one per question:
  new        the ad as it is now: bare URL + Meta's appended tags.
  dupes      the shape BEFORE the fix (tags baked in AND appended; the first value wins).
  returning  a visitor already holding an older first-touch record who clicks the new ad.
  organic    no attribution at all.

A control run on the previous registry must REPORT, not crash: every read goes through
.get / presence-safe helpers.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import BackgroundTasks, HTTPException, Response
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

import app.models.db as mdb
from app.models.db import (
    Base, ClubMembership, Organisation, OrgModuleSubscription, SelfServeAcknowledgement, User,
)
from app.routers import meta_ads as meta_router
from app.routers import organisations as orgs_router
from app.routers import public_self_serve as pss
from app.routers import self_serve_trial as sst
from app.services import crm, crm_rules, email_service, meta_ads, webinar_ddl
from app.services import returning_club_followup as rcf

DB_URL = os.environ.get("VERIFY_DATABASE_URL", "postgresql+asyncpg://postgres@127.0.0.1:55432/verify_ad_attr")
ATTR_DIR = Path(os.environ.get("ATTR_DIR", "/tmp/attr"))
NEW, OLD = "120251284365570121", "120250149119070121"
LIVE_AD = "120251342626760121"
NOW = dt.datetime.now(dt.timezone.utc)
DAY = dt.timedelta(days=1)
PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} — {detail}")
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  ({detail})'}")


class FakeProvider:
    def __init__(self):
        self.name, self.sent = "brevo", []

    async def send(self, msg):
        self.sent.append(msg)
        return email_service.SendResult(ok=True, error=None)


def fake_request(ip: str) -> Request:
    return Request({"type": "http", "method": "POST", "path": "/", "query_string": b"",
                    "headers": [(b"user-agent", b"verify"), (b"x-real-ip", ip.encode())], "client": (ip, 1234)})


async def safe(coro):
    try:
        return await coro
    except HTTPException as e:
        return {"_http": e.status_code, "_detail": str(e.detail)[:80]}


USAGE_DDL = """CREATE TABLE IF NOT EXISTS usage_events (
    id BIGSERIAL PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), event_type TEXT NOT NULL DEFAULT 'api',
    method TEXT NOT NULL, path TEXT NOT NULL, route TEXT, status INTEGER NOT NULL DEFAULT 0, duration_ms INTEGER,
    user_id UUID, org_id UUID, ip_hash TEXT, user_agent TEXT, referer TEXT, metadata JSONB DEFAULT '{}',
    visitor_id UUID)"""

SNAPSHOT_DDL = [
    """CREATE TABLE IF NOT EXISTS meta_ad_snapshots (
        id BIGSERIAL PRIMARY KEY, snapshot_date DATE NOT NULL, level TEXT NOT NULL, ad_id TEXT, ad_name TEXT,
        spend NUMERIC NOT NULL DEFAULT 0, impressions NUMERIC NOT NULL DEFAULT 0, link_clicks NUMERIC NOT NULL DEFAULT 0,
        link_ctr NUMERIC NOT NULL DEFAULT 0, landing_page_views NUMERIC NOT NULL DEFAULT 0, cost_per_lpv NUMERIC,
        leads NUMERIC NOT NULL DEFAULT 0, recommendation TEXT, recommendation_status TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""",
    "ALTER TABLE meta_ad_snapshots ADD COLUMN IF NOT EXISTS campaign_id TEXT",
    "ALTER TABLE meta_ad_snapshots ADD COLUMN IF NOT EXISTS delivery_status TEXT",
    "ALTER TABLE meta_ad_snapshots ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ",
    # As main.py's lifespan builds it, including the later campaign_id ALTER.
    """CREATE TABLE IF NOT EXISTS meta_lead_adjustments (
        id BIGSERIAL PRIMARY KEY, delta INTEGER NOT NULL, note TEXT, created_by_email TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""",
    "ALTER TABLE meta_lead_adjustments ADD COLUMN IF NOT EXISTS campaign_id TEXT",
]


def load(name: str) -> dict | None:
    p = ATTR_DIR / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else None


async def main() -> int:
    records = {k: load(k) for k in ("new", "dupes", "returning")}
    missing = [k for k, v in records.items() if v is None]
    if missing:
        print(f"FAIL  the browser leg has not been run: no {missing} in {ATTR_DIR}")
        return 2

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(USAGE_DDL))
        # The columns main.py's lifespan adds to usage_events afterwards (the funnel reads them).
        for col, typ in (("country", "TEXT"), ("utm_source", "TEXT"), ("utm_medium", "TEXT"), ("utm_campaign", "TEXT"),
                         ("utm_content", "TEXT"), ("utm_id", "TEXT"), ("click_id", "TEXT"), ("traffic_source", "TEXT"),
                         ("landing_path", "TEXT"), ("time_on_page_ms", "INTEGER")):
            await conn.execute(text(f"ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS {col} {typ}"))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "pgcrypto"'))
        for stmt in webinar_ddl.STATEMENTS:
            await conn.execute(text(stmt))
        for stmt in SNAPSHOT_DDL:
            await conn.execute(text(stmt))
        await conn.execute(text("""CREATE TABLE IF NOT EXISTS platform_settings (
            id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1), settings JSONB NOT NULL DEFAULT '{}',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"""))
        # The key the shipped reader uses (platform_settings.get_active_meta_campaign_id).
        await conn.execute(text("INSERT INTO platform_settings (id, settings) VALUES (1, CAST(:s AS jsonb))"),
                           {"s": json.dumps({"default_trial_days": 14, "meta_campaign_id": NEW})})
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

    async def is_verified(db, email):
        return True
    sst.verification.is_verified = is_verified
    import app.services.admin_contact_list as acl
    acl.queue_sync = lambda *_a, **_k: None
    pss.record_event_bg = lambda **_k: None

    async def reuse(db, background_tasks, org_id, org_name="", auto_yearbooks=False):
        org = (await db.execute(select(Organisation).where(Organisation.id == uuid.UUID(org_id)))).scalar_one()
        return org, uuid.uuid4(), org_name or org.name
    orgs_router._onboard_club_core = reuse
    email_service.get_email_provider = lambda: FakeProvider()

    clubs: dict = {}

    async def make_club(label: str, name: str):
        oid = uuid.uuid4()
        async with Session() as db:
            db.add(Organisation(id=oid, name=name, slug=name.lower().replace(" ", "-"), is_active=True))
            await db.flush()
            for mod in ("core", "select"):
                db.add(OrgModuleSubscription(id=uuid.uuid4(), organisation_id=oid, module_key=mod, status="trial",
                                             trial_started_at=NOW - 30 * DAY, trial_ends_at=NOW - 9 * DAY))
            ann = User(id=uuid.uuid4(), email=f"ann@{label}.example", username=f"ann-{label}", display_name="Ann Admin",
                       password_hash="x", mobile_number="0400000001")
            db.add(ann)
            await db.flush()
            db.add(ClubMembership(id=uuid.uuid4(), user_id=ann.id, club_id=oid, role="club_admin", is_primary_admin=True))
            await db.commit()
        clubs[label] = {"id": oid, "name": name}
        await crm.sync_self_serve_trial_registration(org_id=oid, org_name=name, contact_name="Ann Admin",
                                                     email=f"ann@{label}.example", phone=None)

    async def register(label: str, attribution: dict | None, ip: str):
        """The PUBLIC route body, exactly as the wizard posts it."""
        c = clubs[label]
        email = f"new@{label}.example"
        async with Session() as db:
            db.add(SelfServeAcknowledgement(id=uuid.uuid4(), email=email, club_name=c["name"], terms_version="x",
                                            privacy_version="x", accepted_at=NOW))
            await db.commit()
        body = pss.PublicSubmitRequest(
            idempotency_key=f"k-{label}", org_id=str(c["id"]), name=c["name"], first_name="Nina", last_name="New",
            display_name="Nina New", username=f"nina-{label}", email=email, mobile_number="0412 999 888",
            password="Str0ng!Passw0rd#1", confirm_password="Str0ng!Passw0rd#1", modules=[],
            visitorId=str(uuid.uuid4()), attribution=attribution)
        async with Session() as db:
            return await safe(pss.submit(body, fake_request(ip), Response(), BackgroundTasks(), db))

    for label, name in (("new", "New Ad CC"), ("dupes", "Dupes CC"), ("ret", "Returning CC"), ("org", "Organic CC"),
                        ("sep", "September CC"), ("nodate", "Undated CC")):
        await make_club(label, name)

    print("registering through the public route")
    results = {
        "new": await register("new", records["new"], "198.51.100.31"),
        "dupes": await register("dupes", records["dupes"], "198.51.100.32"),
        "ret": await register("ret", records["returning"], "198.51.100.33"),
        "org": await register("org", None, "198.51.100.34"),
        # Same tags as the live ad, so by tag alone both belong to the campaign. The first is then
        # backdated to September (a registration from the earlier run), the second loses its timestamp.
        "sep": await register("sep", records["new"], "198.51.100.35"),
        "nodate": await register("nodate", records["new"], "198.51.100.36"),
    }
    async with Session() as db:
        await db.execute(text("UPDATE self_serve_idempotency_keys SET created_at = :at WHERE idempotency_key = 'k-sep'"),
                         {"at": dt.datetime(2026, 9, 20, 3, 0, tzinfo=dt.timezone.utc)})
        await db.execute(text("DELETE FROM self_serve_idempotency_keys WHERE idempotency_key = 'k-nodate'"))
        # Manual +/- corrections: one made in September (the earlier run), one after the restart.
        for delta, at in ((5, dt.datetime(2026, 9, 22, 3, 0, tzinfo=dt.timezone.utc)), (1, NOW)):
            await db.execute(text("INSERT INTO meta_lead_adjustments (delta, note, campaign_id, created_at) VALUES (:d, 'x', :c, :at)"),
                             {"d": delta, "c": NEW, "at": at})
        await db.commit()
    check("all six registrations completed", all(r.get("status") == "completed" for r in results.values()),
          str({k: v.get("status") or v for k, v in results.items()}))

    async def stored(label):
        async with Session() as db:
            o = (await db.execute(select(Organisation).where(Organisation.id == clubs[label]["id"]))).scalar_one()
            return o.signup_source, o.signup_attribution

    print("what was stored on the registration")
    src, attr = await stored("new")
    attr = attr or {}
    check("new: filed as an ad signup", src == "self_serve_ad", str(src))
    check("new: the tags are stored exactly as the browser captured them",
          (attr.get("utm_source"), attr.get("utm_medium"), attr.get("utm_campaign"), attr.get("utm_content"))
          == ("meta", "paid_social", "BC_AU_Trial_CBO_Sep2026", "check_out_your_club_v2"), str(attr))
    check("new: the click id and its source are stored", attr.get("click_id") == "IwAR_new_click" and attr.get("click_source") == "facebook", str(attr))
    src, attr = await stored("org")
    check("organic: filed as organic with nothing stored", src == "self_serve_organic" and not attr, f"{src} {attr}")
    check("the CRM files the new registration's lead source as Meta ads",
          crm.lead_source_from_attribution(records["new"]) == "meta_ads", str(crm.lead_source_from_attribution(records["new"])))

    print("what Meta Ads HQ counts under the NEW campaign")
    async with Session() as db:
        await meta_ads._use_active_campaign(db)
        count_new = await meta_ads.get_registration_count(db)
        rows_new = (await meta_router.ad_signups(db=db, _=None)).get("rows", [])
    names_new = sorted(r["name"] for r in rows_new)
    check("HQ resolved the new campaign as the active one", meta_ads._campaign_id() == NEW, meta_ads._campaign_id())
    check("the registration through the live ad IS counted", "New Ad CC" in names_new, str(names_new))
    check("the old-tag registrations are NOT (the restart counts from zero)",
          "Dupes CC" not in names_new and "Returning CC" not in names_new, str(names_new))
    check("an organic registration is not counted", "Organic CC" not in names_new, str(names_new))
    check("so the headline count is exactly one", count_new == 1 and len(rows_new) == 1, f"{count_new} / {len(rows_new)}")

    print("a registration from BEFORE the restart, carrying the same tags, is not this campaign's")
    check("the September registration is NOT counted, though its tags match", "September CC" not in names_new, str(names_new))
    check("the registration with no timestamp is NOT counted either (cannot be placed)", "Undated CC" not in names_new, str(names_new))
    scope_fn = getattr(meta_ads, "get_registration_scope", None)
    async with Session() as db:
        scope = await scope_fn(db) if scope_fn else {}
    check("both are REPORTED as left out, one each", (scope.get("before"), scope.get("undated")) == (1, 1), str(scope))
    check("the count itself is the one that belongs", scope.get("count") == 1, str(scope))
    live = next((r for r in rows_new if r["name"] == "New Ad CC"), {})
    check("its row carries the campaign and creative tags", (live.get("utm_campaign"), live.get("utm_content")) == ("BC_AU_Trial_CBO_Sep2026", "check_out_your_club_v2"), str(live))

    print("the full summary the page reads (spend from a stored snapshot)")
    today = dt.date.today()
    async with Session() as db:
        for level, ad_id, ad_name in (("campaign", None, None), ("ad", LIVE_AD, "Ad_CheckOutYourClub_v2_Relaunch")):
            await db.execute(text("""INSERT INTO meta_ad_snapshots
                (snapshot_date, level, ad_id, ad_name, spend, impressions, link_clicks, link_ctr, landing_page_views,
                 cost_per_lpv, leads, campaign_id, delivery_status, updated_at)
                VALUES (:d, :l, :a, :n, 1.57, 400, 9, 2.25, 6, 0.26, 1, :c, 'ACTIVE', NOW())"""),
                {"d": today, "l": level, "a": ad_id, "n": ad_name, "c": NEW})
        await db.commit()
    async with Session() as db:
        summary = await safe(meta_ads.get_latest_summary(db))
    trial = next((s for s in (summary.get("streams") or []) if s.get("stream") == "trial"), {})
    creatives = {c.get("utm_content"): c for c in (summary.get("creatives") or [])}
    # 1 counted registration + the 1 manual adjustment made after the restart (the September +5 is not in it).
    check("summary: the trial stream's result is the 1 counted registration plus the 1 counted adjustment",
          trial.get("results") == 2, str(trial.get("results") or summary))
    check("summary: from its own A$1.57 of spend", trial.get("spend") == 1.57, str(trial.get("spend")))
    row = creatives.get("check_out_your_club_v2", {})
    check("summary: a check_out_your_club_v2 creative row exists with the spend AND the signup on the same row",
          row.get("spend") == 1.57 and row.get("trial_signups") == 1, str(row))
    check("summary: the live ad has a utm_content on record", next((a.get("utm_content") for a in summary.get("ads", []) if a.get("ad_id") == LIVE_AD), None) == "check_out_your_club_v2")
    check("summary: nothing spent lands in an (untagged) row", "(untagged)" not in creatives, str(list(creatives)))
    check("summary: the plan is A$450 and the fresh start is marked on 10 Nov",
          summary.get("campaign_budget") == 450.0 and any(a.get("date") == "2026-11-10" for a in summary.get("annotations", [])),
          f"{summary.get('campaign_budget')} {summary.get('annotations')}")

    print("the restart date also drives Meta's window, adjustments and the summary")
    check("the summary says where counting starts and what it left out",
          summary.get("counts_from") and summary.get("counts_from", "").startswith("2026-11-10")
          and (summary.get("registrations_excluded") or {}) == {"before_restart": 1, "undated": 1}, str(summary.get("registrations_excluded")))
    window = getattr(meta_ads, "_window_start", None)
    check("Meta's window starts at the restart date with no manual cutoff set",
          bool(window) and window() is not None and window().date().isoformat() == "2026-11-10", str(window and window()))
    tr = meta_ads._date_range_params().get("time_range", "")
    check("so Meta's insights are asked for from 10 Nov (not the lifetime preset)", '"since": "2026-11-10"' in tr, tr or str(meta_ads._date_range_params()))
    meta_ads._counting_since.set(dt.datetime(2026, 11, 12, tzinfo=dt.timezone.utc))
    check("a LATER manual counting-since still wins",
          bool(window) and window() is not None and window().date().isoformat() == "2026-11-12", str(window and window()))
    meta_ads._counting_since.set(None)
    async with Session() as db:
        adj_total = await meta_ads.get_leads_adjustment_total(db)
        adj_rows = await meta_ads.get_lead_adjustments(db)
    check("a manual adjustment from September is not in the total, the one after the restart is", adj_total == 1, str(adj_total))
    check("the September adjustment stays in the audit trail, marked not counted",
          sorted((a["delta"], a.get("counted")) for a in adj_rows) == [(1, True), (5, False)], str(adj_rows))
    check("the headline lead figure is the counted registration plus only the counted adjustment",
          (summary.get("campaign") or {}).get("leads_effective") == 2, str((summary.get("campaign") or {}).get("leads_effective")))

    print("what the OLD campaign counts (so the checks above can fail)")
    async with Session() as db:
        await meta_ads._use_active_campaign(db)
    meta_ads._active_campaign.set(OLD)
    async with Session() as db:
        found = (await db.execute(text("SELECT name, signup_attribution FROM organisations WHERE signup_attribution IS NOT NULL"))).all()
    old_names = sorted(n for n, a in found if meta_ads._attribution_matches_campaign(a))
    check("the old campaign claims the old-tag registrations and refuses the new one",
          "Dupes CC" in old_names and "Returning CC" in old_names and "New Ad CC" not in old_names, str(old_names))

    meta_ads._active_campaign.set(OLD)
    rs = getattr(meta_ads, "registration_scope", None)
    check("a campaign that never restarted keeps every registration (scope is always counted)",
          bool(rs) and rs(None) == "counted" and rs(dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc)) == "counted")
    check("and has no window start of its own", bool(getattr(meta_ads, "_window_start", None)) and meta_ads._window_start() is None)

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print("  FAILED:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
