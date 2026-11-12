"""Where each club on Meta Ads HQ came from, read from its UTMs, ad click id and referrer.

    createdb verify_club_origin
    VERIFY_DATABASE_URL=postgresql+asyncpg://.../verify_club_origin \\
        python -m verification.verify_meta_ads_club_origin

The report that prompted it: five clubs finished registering in a week, the list called every
one of them "Other", and "Free trial signups" read 0, so there was no cost per trial. Nobody
could tell whether a link was being shared, an email had gone out, or something else. They were
"Other" because the only question the page asked was "is it this Meta campaign?".

Two things are measured:
  * `classify_origin` and the shipped get_selected_clubs / get_searched_clubs, against a real
    Postgres: a completed registration is classified from its stored attribution, a club that
    only searched or selected from its visitor's first page view that carried a signal.
  * `get_registrations_outside_campaign`: the finished-but-not-this-campaign count that makes
    "5 finished, 0 counted" explain itself.

The five seeded completions are exactly the shape of that report: none is from the selected
campaign. A control run on the previous code must REPORT, not crash.
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
from app.models.db import Base, Organisation
from app.services import meta_ads as m
from app.services import webinar_ddl
from verification.verify_meta_ads_new_tags_e2e import SNAPSHOT_DDL

DB_URL = os.environ.get("VERIFY_DATABASE_URL", "postgresql+asyncpg://postgres@127.0.0.1:55432/verify_club_origin")
NEW = "120251284365570121"
NOW = dt.datetime.now(dt.timezone.utc)
H, D = dt.timedelta(hours=1), dt.timedelta(days=1)
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
    traffic_source TEXT, landing_path TEXT)"""

CAMPAIGN_TAGS = {"utm_source": "meta", "utm_medium": "paid_social", "utm_campaign": "BC_AU_Trial_CBO_Sep2026",
                 "utm_content": "check_out_your_club_v2", "click_source": "facebook", "has_signal": True}

# (club, attribution stored on the registration, finished how long ago) -- the five from the report first
REGISTRATIONS = [
    ("Piara CC", {"utm_source": "bettercricket", "utm_medium": "email", "utm_campaign": "rediscover_nov", "has_signal": True,
                  "landing_path": "/trial?utm_id=PIARA1&utm_source=bettercricket&utm_medium=email"}, 5 * H),
    ("Eastern CC", None, 4 * H),
    ("Cowara CC", {"landing_path": "/trial", "landing_referrer": "https://l.facebook.com/l.php?u=betterat.cricket", "has_signal": False}, 3 * H),
    ("Telugu CC", {"landing_path": "/trial", "landing_referrer": "https://www.google.com.au/", "has_signal": False}, 2 * H),
    ("Old Aug CC", {"utm_source": "facebook", "utm_medium": "paid_social", "utm_campaign": "bc_au_trials_cbo_aug2026",
                    "utm_content": "checkout_your_club_v2", "click_source": "facebook", "has_signal": True}, 1 * H),
    ("Ultima CC", dict(CAMPAIGN_TAGS), 6 * H),                                  # this campaign's own: counted
    ("Before CC", dict(CAMPAIGN_TAGS), 10 * D),                                 # before the restart
]


async def main() -> int:
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("DROP TABLE IF EXISTS usage_events"))
        await conn.execute(text(USAGE_DDL))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "pgcrypto"'))
        for col, typ in (("country", "TEXT"), ("time_on_page_ms", "INTEGER")):
            await conn.execute(text(f"ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS {col} {typ}"))
        for stmt in webinar_ddl.STATEMENTS + SNAPSHOT_DDL:
            await conn.execute(text(stmt))
        await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_meta_ad_snapshots_date_level_ad_campaign "
                                "ON meta_ad_snapshots(snapshot_date, level, COALESCE(ad_id, ''), COALESCE(campaign_id, ''))"))
        await conn.execute(text("""CREATE TABLE IF NOT EXISTS platform_settings (
            id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1), settings JSONB NOT NULL DEFAULT '{}',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"""))
        await conn.execute(text("INSERT INTO platform_settings (id, settings) VALUES (1, CAST(:s AS jsonb))"),
                           {"s": json.dumps({"meta_campaign_id": NEW})})
    Session = async_sessionmaker(engine, expire_on_commit=False)
    mdb.async_session_maker = Session
    m.CAMPAIGN_COUNTS_FROM[NEW] = NOW - 5 * D          # the test owns the restart date

    # ── pure: the classifier ─────────────────────────────────────────────────
    print("the classifier")
    classify = getattr(m, "classify_origin", None)
    def ch(**kw):
        return (classify(**kw) if classify else {}).get("channel")
    check("our outreach email is recognised by its per-club code even when the UTM fields dropped it",
          ch(utm_source="bettercricket", landing_path="/trial?utm_id=ABC123") == "email")
    check("an EDM send is email", ch(utm_campaign="edm") == "email")
    check("a Meta ad is Meta, by UTM or by click id", ch(utm_source="meta") == "meta" and ch(click_source="facebook") == "meta" and ch(landing_path="/trial?fbclid=x") == "meta")
    check("a link shared on Facebook (a referrer, no ad tags) is a shared link", ch(referrer="https://l.facebook.com/l.php?u=x") == "social")
    check("a link shared on WhatsApp is a shared link", ch(referrer="https://wa.me/") == "social")
    check("a Google referrer is Google", ch(referrer="https://www.google.com.au/") == "google")
    check("an AI assistant referrer is its own channel", ch(referrer="https://chatgpt.com/") == "ai")
    check("another site's link is a referral", ch(referrer="https://www.playhq.com/club") == "referral")
    check("a referrer that is our own site is not evidence of anything", ch(referrer="https://betterat.cricket/pricing") == "direct")
    check("an unknown campaign tag is its own channel", ch(utm_source="clubnews", utm_campaign="spring") == "campaign_other")
    check("nothing at all is direct", ch() == "direct")
    # The report: Meta ad clicks were labelled "Email (our outreach)". The Meta ad's own link carries
    # utm_id (the campaign id), and a bare utm_id was read as our per-club email code.
    check("the reported click is Meta: utm_source=meta, paid_social, campaign id in utm_id, Facebook referrer",
          ch(utm_source="meta", utm_medium="paid_social", utm_campaign="BC_AU_Trial_CBO_Sep2026",
             utm_id="120251284365570121", referrer="https://m.facebook.com/") == "meta")
    check("a Meta ad whose utm_id is a club code (the teaser ad pack) is Meta, not email",
          ch(landing_path="/club-preview/abc?utm_source=meta&utm_medium=paid_social&utm_id=alpha-cricket-club") == "meta")
    check("paid_social alone, with no source, is Meta", ch(utm_medium="paid_social", utm_id="X1") == "meta")
    check("Meta stays Meta with no utm_id at all", ch(utm_source="meta", utm_medium="paid_social") == "meta")
    # The other half of each pair: email must still be email, or the fix just moved the bug.
    check("our outreach email (club code in utm_id, no Meta tag) is still email",
          ch(utm_source="ALPHA1", utm_medium="sales_email", utm_id="ALPHA1") == "email")
    check("an email link with a club code and a Facebook click id is still email (in-app browsers add fbclid)",
          ch(utm_id="ABC123", landing_path="/trial?utm_id=ABC123&fbclid=zz") == "email")
    check("sales_email as a medium is email even with no club code", ch(utm_source="sales", utm_medium="sales_email") == "email")
    check("the stored-registration path agrees: a Meta first touch with utm_id in its landing path is Meta",
          (m.origin_from_attribution({"utm_source": "meta", "utm_medium": "paid_social",
                                      "landing_path": "/trial?utm_source=meta&utm_id=1202&utm_medium=paid_social"}) or {}).get("channel") == "meta")

    # ── the registrations: five finished, none of them this campaign ─────────
    async with Session() as db:
        for name, attribution, ago in REGISTRATIONS:
            org = Organisation(id=uuid.uuid4(), name=name, slug=name.lower().replace(" ", "-"), is_active=True)
            db.add(org)
            await db.flush()
            await db.execute(text("UPDATE organisations SET signup_source = :src, signup_attribution = CAST(:a AS jsonb) WHERE id = :i"),
                             {"src": "self_serve_ad" if (attribution or {}).get("has_signal") else "self_serve_organic",
                              "a": json.dumps(attribution) if attribution is not None else None, "i": org.id})
            await db.execute(text("INSERT INTO self_serve_idempotency_keys (idempotency_key, email, status, org_id, created_at) "
                                  "VALUES (:k, :e, 'completed', :o, :at)"),
                             {"k": f"k-{name}", "e": f"{name}@x.example", "o": org.id, "at": NOW - ago})
        await db.commit()

    # ── beacon-only clubs: selected a club, never registered ─────────────────
    async def visit(club, *, page_view=None, route="club_prepared"):
        v = uuid.uuid4()
        async with Session() as db:
            if page_view is not None:
                await db.execute(text("""INSERT INTO usage_events (created_at, event_type, path, visitor_id, utm_source, utm_medium, utm_campaign,
                    utm_id, traffic_source, referer) VALUES (:at, 'page_view', :path, :v, :us, :um, :uc, :ui, :ts, :ref)"""),
                    {"at": NOW - 3 * H, "path": page_view.get("path", "/trial"), "v": v, "us": page_view.get("utm_source"),
                     "um": page_view.get("utm_medium"), "uc": page_view.get("utm_campaign"), "ui": page_view.get("utm_id"),
                     "ts": page_view.get("traffic_source"), "ref": page_view.get("referer")})
            await db.execute(text("""INSERT INTO usage_events (created_at, event_type, route, path, visitor_id, metadata)
                VALUES (:at, 'self_serve_step', :r, '/trial', :v, CAST(:meta AS jsonb))"""),
                {"at": NOW - 2 * H, "r": route, "v": v, "meta": json.dumps({"club_name": club, "search_query": club.split()[0].lower()})})
            await db.commit()

    await visit("Email Visitor FC", page_view={"utm_source": "bettercricket", "utm_medium": "email", "utm_id": "CODE9"})
    await visit("Referral FC", page_view={"referer": "https://www.playhq.com/x"})
    await visit("Plain FC", page_view={})
    await visit("No View FC", page_view=None)
    await visit("Searched Google FC", page_view={"referer": "https://www.google.com/"}, route="club_searched")

    async def scoped(fn, db, days, scope):
        try:
            return await fn(db, days, scope)
        except TypeError:
            return await fn(db, days)

    print("clubs that finished registering")
    async with Session() as db:
        sel = await scoped(m.get_selected_clubs, db, 30, "all")
    by = {c["name"]: c for c in sel["clubs"]}
    chan = lambda n: ((by.get(n) or {}).get("origin") or {}).get("channel")  # noqa: E731
    check("an email-driven registration is Email (the per-club code was only in the landing URL)", chan("Piara CC") == "email", str(chan("Piara CC")))
    check("a registration with no tags and no referrer is Direct", chan("Eastern CC") == "direct", str(chan("Eastern CC")))
    check("a registration whose visitor came from a Facebook share says so", chan("Cowara CC") == "social", str(chan("Cowara CC")))
    check("a registration that arrived from Google says so", chan("Telugu CC") == "google", str(chan("Telugu CC")))
    check("an old campaign's ad is Meta (it is not THIS campaign's, which is a separate question)", chan("Old Aug CC") == "meta", str(chan("Old Aug CC")))
    check("the detail carries the raw evidence so it can be checked",
          "utm_id=PIARA1" in ((by.get("Piara CC") or {}).get("origin") or {}).get("detail", "")
          and "referrer=l.facebook.com" in ((by.get("Cowara CC") or {}).get("origin") or {}).get("detail", ""),
          str(((by.get("Piara CC") or {}).get("origin") or {}).get("detail")))

    print("clubs that only searched or selected")
    check("a selection from our outreach email is Email, from the visitor's first page view", chan("Email Visitor FC") == "email", str(chan("Email Visitor FC")))
    check("a visitor who came from another site is a referral", chan("Referral FC") == "referral", str(chan("Referral FC")))
    check("a visitor with nothing to go on is Direct", chan("Plain FC") == "direct", str(chan("Plain FC")))
    check("a visitor with no page view on record has NO origin, not a guess", "No View FC" in by and (by["No View FC"].get("origin") is None), str(by.get("No View FC", {}).get("origin")))
    async with Session() as db:
        srch = await scoped(m.get_searched_clubs, db, 30, "all")
    sby = {c["name"]: c for c in srch["clubs"]}
    check("a searched club carries its visitor's origin too", ((sby.get("Searched Google FC") or {}).get("origin") or {}).get("channel") == "google",
          str((sby.get("Searched Google FC") or {}).get("origin")))

    print("why 5 finished and the trial count says 0")
    outside_fn = getattr(m, "get_registrations_outside_campaign", None)
    async with Session() as db:
        await m._use_active_campaign(db)
        outside = await outside_fn(db) if outside_fn else None
        counted = await m.get_registration_count(db)
    check("the five that finished from outside the campaign are counted as such", outside == 5, str(outside))
    check("this campaign's own registration is the only one in its count", counted == 1, str(counted))
    check("the one from before the restart is in neither", outside == 5 and counted == 1)
    async with Session() as db:
        await db.execute(text("""INSERT INTO meta_ad_snapshots (snapshot_date, level, spend, impressions, link_clicks, link_ctr,
            landing_page_views, leads, campaign_id, updated_at) VALUES (:d, 'campaign', 28.75, 2469, 29, 1.2, 24, 4, :c, NOW())"""),
            {"d": NOW.date(), "c": NEW})
        await db.commit()
    async with Session() as db:
        summary = await m.get_latest_summary(db)
    check("the summary says so, for the page to print", ((summary.get("registrations_excluded") or {}).get("other_traffic")) == 5, str(summary.get("registrations_excluded")))

    m._active_campaign.set("120250149119070121")
    async with Session() as db:
        old_outside = await outside_fn(db) if outside_fn else None
    check("a campaign that never restarted has no outside count to report", old_outside == 0, str(old_outside))

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print("  FAILED:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
