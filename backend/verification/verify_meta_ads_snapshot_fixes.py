"""Four figures on Meta Ads HQ that were wrong after the 10 Nov 2026 restart.

    createdb verify_snapshot_fixes
    VERIFY_DATABASE_URL=postgresql+asyncpg://.../verify_snapshot_fixes \\
        python -m verification.verify_meta_ads_snapshot_fixes

  1. STALE ROWS. A counting-since or restart date narrows Meta's window, and an ad with
     no delivery in it gets no insights row, so the EARLIER pull the same day (lifetime
     figures) stayed and was summed into the stream totals, the funnel, the ad list and
     the creative table beside a campaign row that had moved on. Read from Meta on
     10 Nov: the live ad had A$1.60 since midnight, the three removed video ads A$0;
     HQ showed "(untagged) A$217.72", exactly their lifetime spend.
  2. DOUBLED LEADS. `_parse_row` added the aggregate `lead` to its own components.
     HQ showed 550 against a lifetime `lead` total of 275.
  3. FUNNEL ORDER. Meta's Lead fires when a club is picked, the same moment as our
     `club_prepared` beacon, but it was drawn as the NEXT stage ("23200% continued").
  4. PAUSED HEADLINE. "Most efficient ad, shift budget its way" could name a paused ad.

Runs the SHIPPED run_snapshot, get_latest_summary, _parse_row, compute_stream_funnel and
build_insights against a real Postgres; only Meta's HTTP fetches are replaced. A control run
on the previous code must REPORT, not crash.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models.db as mdb
from app.models.db import Base
from app.services import meta_ads as m
from app.services import webinar_ddl
from verification.verify_meta_ads_new_tags_e2e import SNAPSHOT_DDL, USAGE_DDL

DB_URL = os.environ.get("VERIFY_DATABASE_URL", "postgresql+asyncpg://postgres@127.0.0.1:55432/verify_snapshot_fixes")
NEW = "120251284365570121"
LIVE = "120251342626760121"
PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} — {detail}")
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  ({detail})'}")


# Read from Meta on 10 Nov 2026: ad id -> (name, lifetime spend, lifetime `lead`)
LIFETIME = {
    LIVE: ("Ad_CheckOutYourClub_v2_Relaunch", 282.25, 44),
    "120251460370820121": ("Ad_Video_V5_MatchSocials_1x1_Sep2026", 164.93, 12),
    "120251460370810121": ("Ad_Video_V3_Availability_1x1_Sep2026", 29.86, 0),
    "120251460069150121": ("Ad_Video_V1_ClubRecords_1x1_Sep2026", 22.93, 0),
    "120251550833470121": ("Ad_ClubSearch_Static_Sep2026", 1042.94, 211),
    "120251301631290121": ("Ad_Trial_Spreadsheet_Sep2026_v3", 137.68, 8),
    "120251284367910121": ("Ad_Trial_Spreadsheet_Sep2026", 21.5, 0),
}
WINDOW = {LIVE: (1.60, 1)}   # since 10 Nov: only the live ad delivered


def graph_row(ad_id, name, spend, leads):
    """A Graph insights row, shaped as Meta returns it: the aggregate `lead` AND the pixel's share of it."""
    acts = [{"action_type": "landing_page_view", "value": "5"}]
    if leads:
        acts += [{"action_type": "lead", "value": str(leads)},
                 {"action_type": "offsite_conversion.fb_pixel_lead", "value": str(leads)}]
    return {"ad_id": ad_id, "ad_name": name, "spend": str(spend), "impressions": "1000",
            "inline_link_clicks": "10", "inline_link_click_ctr": "1", "actions": acts}


async def main() -> int:
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(USAGE_DDL))
        for col, typ in (("utm_source", "TEXT"), ("utm_medium", "TEXT"), ("utm_campaign", "TEXT"), ("utm_content", "TEXT"),
                         ("utm_id", "TEXT"), ("click_id", "TEXT"), ("traffic_source", "TEXT"), ("landing_path", "TEXT")):
            await conn.execute(text(f"ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS {col} {typ}"))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "pgcrypto"'))
        for stmt in webinar_ddl.STATEMENTS:
            await conn.execute(text(stmt))
        for stmt in SNAPSHOT_DDL:
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

    # ── 2. doubled leads ─────────────────────────────────────────────────────
    print("the lead total")
    parse = m._parse_row
    both = parse(graph_row("a", "x", 10, 44))
    check("the aggregate `lead` is used, not added to the pixel's share of the same events", both["leads"] == 44.0, str(both["leads"]))
    components_only = m._parse_row({"spend": "1", "actions": [
        {"action_type": "offsite_conversion.fb_pixel_lead", "value": "7"}, {"action_type": "onsite_conversion.lead_grouped", "value": "3"}]})
    check("with no aggregate, the components (different sources) are summed", components_only["leads"] == 10.0, str(components_only["leads"]))
    check("no lead actions is zero", parse(graph_row("a", "x", 10, 0))["leads"] == 0.0)
    check("a lifetime total of 275 stays 275 across the live ads (it read 550)",
          sum(parse(graph_row(k, n, sp, ld))["leads"] for k, (n, sp, ld) in LIFETIME.items()) == 275.0)

    # ── 3. the funnel ────────────────────────────────────────────────────────
    print("the trial funnel")
    bucket = {"impressions": 1000, "link_clicks": 50, "landing_page_views": 40, "leads": 275, "result_label": "Free trial signups"}
    stages = m.compute_stream_funnel(bucket, 3, club_selected=20)
    keys = [x["key"] for x in stages]
    check("Meta's Lead is not a stage of its own any more", "leads" not in keys, str(keys))
    check("the stages are impressions, clicks, landing views, club selected, signups",
          keys == ["impressions", "link_clicks", "landing_page_views", "club_selected", "results"], str(keys))
    cs = next((x for x in stages if x["key"] == "club_selected"), {})
    check("Club selected carries Meta's lead count as a note on the same step", cs.get("meta_leads") == 275 and "275" in (cs.get("note") or ""), str(cs))
    res = next((x for x in stages if x["key"] == "results"), {})
    check("signups are measured against Club selected, so no 23200% appears", res.get("pct_of_prev") == 15.0 and all(x["pct_of_prev"] <= 100 for x in stages), str([x["pct_of_prev"] for x in stages]))
    check("the webinar funnel (no club-selected step) is unchanged",
          [x["key"] for x in m.compute_stream_funnel(bucket, 3)] == ["impressions", "link_clicks", "landing_page_views", "results"])

    # ── 4. the headline ──────────────────────────────────────────────────────
    print("the efficiency headline")
    def ad(i, name, status, cost_per_lpv):
        return {"ad_id": i, "name": name, "spend": 100.0, "cost_per_lpv": cost_per_lpv, "delivery_status": status,
                "link_ctr": 1.0, "landing_page_views": 50, "stream": "trial"}
    ads = [ad("p", "Paused_Best", "PAUSED", 0.5), ad("a1", "Live_Good", "ACTIVE", 1.0), ad("a2", "Live_Poor", "ACTIVE", 3.0)]
    campaign = {"spend": 300.0, "impressions": 3000, "link_clicks": 30, "landing_page_views": 150, "cost_per_lpv": 2.0, "leads": 0, "registrations": 0}
    insights = m.build_insights(campaign, ads, [], 450.0, 30, streams=[])
    eff = [i for i in insights if "most efficient" in i["title"]]
    check("the most efficient ad named is one that is running", bool(eff) and "Live_Good" in eff[0]["title"] and "Paused_Best" not in eff[0]["title"], str([i["title"] for i in insights]))
    only_paused_best = m.build_insights(campaign, [ad("p", "Paused_Best", "PAUSED", 0.5), ad("a2", "Live_Poor", "ACTIVE", 3.0)], [], 450.0, 30, streams=[])
    check("with only one running ad there is nothing to compare, so no 'shift budget' advice",
          not any("most efficient" in i["title"] for i in only_paused_best))

    # ── 1. stale rows ────────────────────────────────────────────────────────
    print("a mid-day window change")
    def make_fetches(window):
        async def camp():
            rows = WINDOW if window else {k: (v[1], v[2]) for k, v in LIFETIME.items()}
            return m._parse_row(graph_row(None, None, sum(r[0] for r in rows.values()), sum(r[1] for r in rows.values())))
        async def per_ad():
            out = []
            for k, (n, sp, ld) in LIFETIME.items():
                if window and k not in WINDOW:
                    continue                       # Meta returns no row for an ad with no delivery in the window
                sp, ld = (WINDOW[k] if window else (sp, ld))
                r = m._parse_row(graph_row(k, n, sp, ld))
                meta = m.AD_DESTINATIONS.get(k, {})
                r.update(name=n, destination=meta.get("destination"), utm_content=meta.get("utm_content"),
                         utm_campaign=meta.get("utm_campaign"), stream=m.stream_for_ad(k, n), ends_on=None, delivery_status="ACTIVE")
                out.append(r)
            return out
        async def none(*a, **k):
            return []
        return camp, per_ad, none

    for label, window in (("morning (lifetime)", False), ("after the restart (window only)", True)):
        camp, per_ad, none = make_fetches(window)
        m.fetch_campaign_totals, m.fetch_per_ad, m.fetch_daily_trend, m.fetch_ad_daily_trend = camp, per_ad, none, none
        async with Session() as db:
            await m.run_snapshot(db)
    async with Session() as db:
        summary = await m.get_latest_summary(db)
    trial = next((s for s in summary.get("streams", []) if s["stream"] == "trial"), {})
    ads_shown = {a["ad_id"] for a in summary.get("ads", [])}
    creatives = {c["utm_content"]: c for c in summary.get("creatives", [])}
    check("only the ad that delivered since the restart is listed", ads_shown == {LIVE}, str(sorted(ads_shown)))
    check("the trial stream's spend is the campaign's own A$1.60 (it read A$1,421.44)", trial.get("spend") == 1.6, str(trial.get("spend")))
    check("so cost per trial is not charged with the earlier run's spend",
          (trial.get("cost_per_result") is None) or trial["cost_per_result"] < 5, str(trial.get("cost_per_result")))
    check("no '(untagged)' row of lifetime spend is left (it read A$217.72)", "(untagged)" not in creatives, str(list(creatives)))
    check("the funnel's impressions are this window's, not lifetime", next((s["value"] for s in trial.get("funnel", []) if s["key"] == "impressions"), None) == 1000.0,
          str([(s["key"], s["value"]) for s in trial.get("funnel", [])]))
    check("the unattributed-spend gap is not negative (stream spend never exceeds the campaign's)", summary.get("unattributed_spend", 0) >= -0.5, str(summary.get("unattributed_spend")))
    async with Session() as db:
        rows_left = (await db.execute(text("SELECT COUNT(*) FROM meta_ad_snapshots WHERE level='ad' AND campaign_id=:c"), {"c": NEW})).scalar()
    check("the table itself holds one ad row for today", rows_left == 1, str(rows_left))

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print("  FAILED:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
