"""With a Meta campaign selected, the on-site numbers describe THAT campaign.

    createdb verify_campaign_scope
    VERIFY_DATABASE_URL=postgresql+asyncpg://.../verify_campaign_scope \\
        python -m verification.verify_meta_ads_campaign_scope

Before this the wizard funnel counted every visitor to the registration wizard,
"Club selected" counted any Meta visitor, the club lists showed every source back
to the start of the year, and the traffic card was all traffic. Selecting a
campaign changed none of it, so the page read as overall numbers.

Runs the SHIPPED get_registration_step_funnel, get_club_selected_count,
get_selected_clubs, get_searched_clubs and get_onsite_traffic against a real
Postgres. Only the restart date is set by the test (so events can sit either side
of it whatever today's date is).

Visitors seeded, one per question:
  alpha     campaign tags, today, searched + selected + reached Terms
  bravo     campaign tags, two days ago, selected only
  charlie   campaign tags, a completed registration
  fallback  utm_source=facebook with tags that name no known campaign
  aug       the OLD campaign's tags (a visitor the selected campaign must refuse)
  organic   no tags at all
  before    campaign tags, but BEFORE the restart date
  ackonly   a Terms acknowledgement with no campaign beacon behind it

A control run on the previous code must REPORT, not crash: every read goes through
.get / getattr, and a missing feature is a failed check, not an exception.
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
from app.models.db import Base, Organisation, SelfServeAcknowledgement
from app.services import meta_ads as m

DB_URL = os.environ.get("VERIFY_DATABASE_URL", "postgresql+asyncpg://postgres@127.0.0.1:55432/verify_campaign_scope")
NEW, OLD = "120251284365570121", "120250149119070121"
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

NEW_TAGS = dict(utm_source="meta", utm_medium="paid_social", utm_campaign="BC_AU_Trial_CBO_Sep2026", utm_content="check_out_your_club_v2")
OLD_TAGS = dict(utm_source="facebook", utm_medium="paid_social", utm_campaign="bc_au_trials_cbo_aug2026", utm_content="checkout_your_club_v2")
UNKNOWN_FB = dict(utm_source="facebook", utm_medium="paid_social", utm_campaign="some_new_thing", utm_content="mystery")


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

    # The test owns the restart date so events can sit either side of it.
    m.CAMPAIGN_COUNTS_FROM[NEW] = NOW - 5 * D

    async def event(visitor, when, *, etype="page_view", route=None, tags=None, club=None, query=None, path=None):
        tags = tags or {}
        meta = {k: v for k, v in (("club_name", club), ("search_query", query)) if v}
        qs = "&".join(f"{k}={v}" for k, v in tags.items())
        async with Session() as db:
            await db.execute(text("""INSERT INTO usage_events
                (created_at, event_type, route, path, visitor_id, metadata, utm_source, utm_medium, utm_campaign, utm_content, traffic_source)
                VALUES (:at, :et, :route, :path, :v, CAST(:meta AS jsonb), :us, :um, :uc, :uco, :ts)"""),
                {"at": when, "et": etype, "route": route, "path": path or ("/trial" + (("?" + qs + "&fbclid=z") if qs else "")),
                 "v": visitor, "meta": json.dumps(meta), "us": tags.get("utm_source"), "um": tags.get("utm_medium"),
                 "uc": tags.get("utm_campaign"), "uco": tags.get("utm_content"),
                 "ts": "facebook" if tags.get("utm_source") in ("meta", "facebook") else None})
            await db.commit()

    V = {k: uuid.uuid4() for k in ("alpha", "bravo", "charlie", "fallback", "aug", "organic", "before", "ackonly")}

    async def journey(key, club, when, tags, *, through=("club_searched", "club_prepared")):
        await event(V[key], when, tags=tags)                                    # the page view carrying the tags
        for i, route in enumerate(through):
            await event(V[key], when + dt.timedelta(minutes=i), etype="self_serve_step", route=route, club=club,
                        query=club.split()[0].lower() if route == "club_searched" else None)

    await journey("alpha", "Alpha CC", NOW - H, NEW_TAGS,
                  through=("club_searched", "club_prepared", "admin_details_completed", "acknowledgements_accepted"))
    await journey("bravo", "Bravo CC", NOW - 2 * D, NEW_TAGS, through=("club_searched", "club_prepared"))
    await journey("charlie", "Charlie CC", NOW - 3 * H, NEW_TAGS,
                  through=("club_searched", "club_prepared", "registration_completed"))
    await journey("fallback", "Fallback FC", NOW - 4 * H, UNKNOWN_FB)
    await journey("aug", "Old Aug CC", NOW - 5 * H, OLD_TAGS)
    await journey("organic", "Organic CC", NOW - 6 * H, None)
    await journey("before", "Before CC", NOW - 10 * D, NEW_TAGS)                # earlier than the restart
    async with Session() as db:
        db.add(SelfServeAcknowledgement(id=uuid.uuid4(), email="alpha@x.example", club_name="Alpha CC", terms_version="x",
                                        privacy_version="x", accepted_at=NOW - H))
        db.add(SelfServeAcknowledgement(id=uuid.uuid4(), email="ack@x.example", club_name="Ack Only CC", terms_version="x",
                                        privacy_version="x", accepted_at=NOW - 2 * H))
        await db.commit()
        org = Organisation(id=uuid.uuid4(), name="Charlie CC", slug="charlie-cc", is_active=True)
        db.add(org)
        await db.flush()
        await db.execute(text("UPDATE organisations SET signup_source = 'self_serve_ad', signup_attribution = CAST(:a AS jsonb) WHERE id = :i"),
                         {"a": json.dumps(NEW_TAGS), "i": org.id})
        await db.execute(text("INSERT INTO self_serve_idempotency_keys (idempotency_key, email, status, org_id, created_at) "
                              "VALUES ('k1', 'c@x.example', 'completed', :o, :at)"), {"o": org.id, "at": NOW - 3 * H})
        await db.commit()

    async def names(rows):
        return sorted(c["name"] for c in rows["clubs"])

    async def scoped(fn, db, days, scope):
        """The shipped call; on the previous code, which takes no scope, the plain call
        (so a control run REPORTS the old behaviour instead of dying on a TypeError)."""
        try:
            return await fn(db, days, scope)
        except TypeError:
            return await fn(db, days)

    # ── the funnel ───────────────────────────────────────────────────────────
    print("wizard funnel")
    async with Session() as db:
        camp = {s["key"]: s["value"] for s in await scoped(m.get_registration_step_funnel, db, 30, "campaign")}
        allv = {s["key"]: s["value"] for s in await scoped(m.get_registration_step_funnel, db, 30, "all")}
    # alpha, bravo, charlie, fallback are the campaign's own, after the restart. aug, organic, before are not.
    check("campaign scope: the visitors who picked a club are the campaign's four, not all seven",
          camp.get("club_prepared") == 4, str(camp))
    check("all traffic: every visitor to the wizard, as it always was", allv.get("club_prepared") == 7, str(allv))
    check("campaign scope: later steps count only campaign visitors too",
          camp.get("acknowledgements_accepted") == 1 and camp.get("registration_completed") == 1, str(camp))
    async with Session() as db:
        one_day = {s["key"]: s["value"] for s in await scoped(m.get_registration_step_funnel, db, 1, "campaign")}
    check("the period narrows it: one day drops the visitor from two days ago", one_day.get("club_prepared") == 3, str(one_day))
    async with Session() as db:
        selected_count = await m.get_club_selected_count(db, 30)
    check("the funnel's own 'Club selected' count is the campaign's visitors, not any Meta visitor",
          selected_count == 4, str(selected_count))

    # ── the club lists ───────────────────────────────────────────────────────
    print("clubs selected")
    async with Session() as db:
        sel = await scoped(m.get_selected_clubs, db, 30, "campaign")
        sel_all = await scoped(m.get_selected_clubs, db, 30, "all")
        sel_1d = await scoped(m.get_selected_clubs, db, 1, "campaign")
    check("campaign scope lists only the campaign's clubs, from the restart on",
          await names(sel) == ["Alpha CC", "Bravo CC", "Charlie CC", "Fallback FC"], str(await names(sel)))
    check("a club from before the restart is not listed, though its tags match", "Before CC" not in await names(sel), str(await names(sel)))
    check("a visitor from the OLD campaign is refused", "Old Aug CC" not in await names(sel))
    check("organic traffic is not listed", "Organic CC" not in await names(sel))
    check("each club still says how far it got",
          {c["name"]: c["furthest_step"] for c in sel["clubs"]}.get("Alpha CC") == "Reached Terms & privacy"
          and {c["name"]: c["furthest_step"] for c in sel["clubs"]}.get("Charlie CC") == "Registration completed",
          str({c["name"]: c["furthest_step"] for c in sel["clubs"]}))
    check("the clubs it left out are COUNTED, not listed, so the page can say so (old campaign, organic, ack-only)",
          sel.get("outside_campaign") == 3 and "Ack Only CC" not in await names(sel), f"{sel.get('outside_campaign')}")
    check("all traffic lists everyone the old way (including the old campaign, organic and the earlier one)",
          {"Old Aug CC", "Organic CC", "Before CC", "Ack Only CC"} <= set(await names(sel_all)), str(await names(sel_all)))
    check("one day keeps only today's clubs", await names(sel_1d) == ["Alpha CC", "Charlie CC", "Fallback FC"], str(await names(sel_1d)))

    print("clubs searched")
    async with Session() as db:
        srch = await scoped(m.get_searched_clubs, db, 30, "campaign")
        srch_all = await scoped(m.get_searched_clubs, db, 30, "all")
    check("campaign scope lists only the campaign's searches",
          await names(srch) == ["Alpha CC", "Bravo CC", "Charlie CC", "Fallback FC"], str(await names(srch)))
    check("all traffic lists the rest too", {"Old Aug CC", "Organic CC", "Before CC"} <= set(await names(srch_all)), str(await names(srch_all)))

    # ── the traffic card ─────────────────────────────────────────────────────
    print("on-site traffic")
    fn = getattr(m, "get_onsite_traffic", None)
    async with Session() as db:
        card = await fn(db, 30, "campaign") if fn else {}
        card_all = await fn(db, 30, "all") if fn else {}
    check("campaign scope counts the campaign's four visitors", (card.get("meta") or {}).get("visitors") == 4, str(card.get("meta")))
    check("all-traffic scope counts every Meta visitor (campaign four + old campaign + the earlier one)",
          (card_all.get("meta") or {}).get("visitors") == 6, str(card_all.get("meta")))
    check("creatives are the campaign's own, not the old campaign's",
          {c["content"] for c in card.get("creatives", [])} == {"check_out_your_club_v2", "mystery"}, str(card.get("creatives")))
    check("landing pages are reported", bool(card.get("landing")), str(card.get("landing")))

    # ── a campaign that never restarted is not narrowed by a restart date ──────
    print("a campaign with no restart date")
    m._active_campaign.set(OLD)
    check("the old campaign has no restart date to clamp to", m._counts_from() is None)

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print("  FAILED:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
