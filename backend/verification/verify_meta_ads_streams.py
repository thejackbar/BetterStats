"""The Meta ad account was restructured 8-9 Sep 2026: ONE campaign now sells
TWO products, and both landing pages fire the SAME pixel event
(CompleteRegistration) on the same dataset, told apart only by
`content_category` — /trial sends 'self_serve_trial', /demo sends 'webinar'.

    createdb bs_meta_verify
    DATABASE_URL=postgresql+asyncpg://.../bs_meta_verify \\
        python -m verification.verify_meta_ads_streams

Run through the SHIPPED functions in services/meta_ads.py against a real
Postgres, never a replay of their logic. What is measured:

  * spend is split PER STREAM from the per-ad rows, so a cost per result is a
    stream's own spend over its own results — the whole point, since the
    pre-split figure charged every trial signup with the webinar's spend;
  * only the trial carries value, so nothing invents revenue from a form fill;
  * a webinar registration is counted from OUR OWN table, and the untagged ones
    (the ad's plain-text link carries no UTMs) are reported rather than either
    claimed or hidden;
  * both new utm_campaign taxonomies are recognised — a single-valued map would
    have failed CLOSED, reading as "the new ads produced nothing";
  * an ad classified by NAME alone, so a creative added in Ads Manager tomorrow
    is filed correctly with no code change;
  * pacing is measured from the last deliberate change, never across it;
  * nothing divides by zero on an ad that has ended or never spent.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/bs_meta_verify",
)

PASS = FAIL = 0


def ck(name: str, cond: bool, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS {name}")
    else:
        FAIL += 1
        print(f"FAIL {name}" + (f"  {extra}" if extra else ""))


# A CONTROL RUN THAT CRASHES IS NOT A CONTROL RUN. The whole feature is
# imported through here so a build without it REPORTS each part by name rather
# than dying on the first ImportError and saying nothing about the rest.
try:
    from app.services import meta_ads as m
    HAVE = True
except Exception as exc:  # pragma: no cover - control-run path
    HAVE = False
    print(f"FAIL the meta_ads service imports  {exc}")

CAMPAIGN_ID = "120250149119070121"
WEBINAR_AD = "120251267760560121"
TRIAL_AD = "120250150859240121"
NEW_AD = "120251268385660121"


def missing(names: list[str]) -> bool:
    """Report the parts of the feature that are absent by NAME. A control run
    has to say what is missing, not stop at the first one."""
    gone = [n for n in names if not hasattr(m, n)]
    for n in gone:
        ck(f"meta_ads.{n} exists", False, "not defined")
    return bool(gone)


async def setup(session_maker) -> None:
    """Only the tables the shipped queries actually read. `webinar_registrations`
    is lifespan-created raw SQL and invisible to create_all, so its DDL is taken
    from the ONE shipped copy (services/webinar_ddl) rather than retyped — a
    table that merely LOOKS right is worse than none."""
    from app.services import webinar_ddl

    async with session_maker() as db:
        await db.execute(text("DROP TABLE IF EXISTS webinar_registrations"))
        await db.execute(text("DROP TABLE IF EXISTS organisations"))
        await db.execute(text("DROP TABLE IF EXISTS platform_settings"))
        await db.execute(text("DROP TABLE IF EXISTS self_serve_idempotency_keys"))
        await db.execute(text("DROP TABLE IF EXISTS meta_ad_snapshots"))
        await db.execute(text('CREATE EXTENSION IF NOT EXISTS "pgcrypto"'))
        for stmt in webinar_ddl.STATEMENTS:
            await db.execute(text(stmt))
        # Just the columns get_creative_performance / get_registration_count read.
        await db.execute(text("""
            CREATE TABLE organisations (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name TEXT,
                signup_source TEXT,
                signup_attribution JSONB,
                archived_at TIMESTAMPTZ
            )
        """))
        # The signup timestamp lives here, not on the org (orgs carry no
        # created_at) — it is what places a registration either side of the
        # change. Columns as main.py's lifespan creates them.
        await db.execute(text("""
            CREATE TABLE self_serve_idempotency_keys (
                idempotency_key TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'validated',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                org_id UUID,
                user_id UUID
            )
        """))
        # meta_ad_snapshots as the lifespan builds it: the CREATE plus every
        # column added since in its own later ALTER (campaign_id, delivery_status,
        # updated_at). A table that merely LOOKS right is worse than none.
        await db.execute(text("""
            CREATE TABLE meta_ad_snapshots (
                id BIGSERIAL PRIMARY KEY,
                snapshot_date DATE NOT NULL,
                level TEXT NOT NULL,
                ad_id TEXT,
                ad_name TEXT,
                spend NUMERIC NOT NULL DEFAULT 0,
                impressions NUMERIC NOT NULL DEFAULT 0,
                link_clicks NUMERIC NOT NULL DEFAULT 0,
                link_ctr NUMERIC NOT NULL DEFAULT 0,
                landing_page_views NUMERIC NOT NULL DEFAULT 0,
                cost_per_lpv NUMERIC,
                leads NUMERIC NOT NULL DEFAULT 0,
                recommendation TEXT,
                recommendation_status TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        for stmt in (
            "ALTER TABLE meta_ad_snapshots ADD COLUMN IF NOT EXISTS campaign_id TEXT",
            "ALTER TABLE meta_ad_snapshots ADD COLUMN IF NOT EXISTS delivery_status TEXT",
            "ALTER TABLE meta_ad_snapshots ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ",
        ):
            await db.execute(text(stmt))
        await db.execute(text("""
            CREATE TABLE platform_settings (
                id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
                settings JSONB NOT NULL DEFAULT '{}',
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await db.execute(text(
            "INSERT INTO platform_settings (id, settings) VALUES (1, CAST(:s AS jsonb))"
        ), {"s": json.dumps({"active_meta_campaign_id": CAMPAIGN_ID})})
        await db.commit()


async def seed(session_maker) -> None:
    from app.services import webinar

    async with session_maker() as db:
        # Trial signups: two through this campaign's own creative, one through
        # the new evergreen taxonomy, one from an EDM that must NOT count.
        for name, attribution in [
            ("Alpha CC", {"utm_campaign": "BC_AU_Trials_CBO_Aug2026", "utm_content": "club_history_hero", "utm_source": "fb"}),
            ("Bravo CC", {"utm_campaign": "BC_AU_Trials_CBO_Aug2026", "utm_content": "club_history_hero", "utm_source": "fb"}),
            ("Charlie CC", {"utm_campaign": "trial_evergreen_sep2026", "utm_content": "spreadsheet_hero", "utm_source": "fb"}),
            ("Delta CC", {"utm_campaign": "spring_edm_2026", "utm_source": "email"}),
        ]:
            await db.execute(text(
                "INSERT INTO organisations (name, signup_source, signup_attribution) "
                "VALUES (:n, 'self_serve_ad', CAST(:a AS jsonb))"
            ), {"n": name, "a": json.dumps(attribution)})
        # An archived test signup — excluded, same rule as the Club Directory.
        await db.execute(text(
            "INSERT INTO organisations (name, signup_source, signup_attribution, archived_at) "
            "VALUES ('Test CC', 'self_serve_ad', CAST(:a AS jsonb), NOW())"
        ), {"a": json.dumps({"utm_campaign": "webinar_21sep2026"})})

        rows = [
            # Tagged, through the webinar ad — these are ours.
            ("a@x.com", "fb", "webinar_21sep2026", "live_demo_hero", None),
            ("b@x.com", "fb", "webinar_21sep2026", "live_demo_hero", None),
            ("c@x.com", "fb", "webinar_21sep2026", "live_demo_hero", None),
            # The ad's plain-text link carries no UTMs, so a real ad-driven
            # registration can arrive carrying nothing at all. Indistinguishable
            # from organic — reported, never claimed.
            ("d@x.com", None, None, None, None),
            ("e@x.com", None, None, None, None),
            # Genuinely somebody else's traffic.
            ("f@x.com", "email", "spring_edm_2026", "newsletter", None),
        ]
        for email, src, camp, content, click in rows:
            await db.execute(text("""
                INSERT INTO webinar_registrations
                    (event_key, name, email, club, utm_source, utm_campaign, utm_content, click_source)
                VALUES (:k, 'Someone', :e, 'A Club', :s, :c, :ct, :cl)
            """), {"k": webinar.EVENT.key, "e": email, "s": src, "c": camp, "ct": content, "cl": click})
        await db.commit()


async def seed_since(session_maker, change: date) -> None:
    """Dates either side of the last deliberate change.

    The trial ran for weeks BEFORE the restructure and the webinar has no
    pre-change history at all, so the two lifetime cost-per-result figures
    describe different campaigns. This fixture is what makes that measurable:
    the trial's daily rows straddle the change, the webinar's start at it.
    """
    async with session_maker() as db:
        # Trial signups placed either side. One matching org gets NO key row at
        # all — a real possibility, and it must be reported as undated rather
        # than silently counted or silently dropped.
        await db.execute(text(
            "INSERT INTO organisations (name, signup_source, signup_attribution) "
            "VALUES ('Echo CC', 'self_serve_ad', CAST(:a AS jsonb))"
        ), {"a": json.dumps({"utm_campaign": "trial_evergreen_sep2026",
                             "utm_content": "spreadsheet_hero", "utm_source": "fb"})})
        for name, at in [
            ("Alpha CC", change - timedelta(days=5)),   # before the change
            ("Bravo CC", change),                        # the day of it
            ("Charlie CC", change + timedelta(days=1)),  # after
            ("Delta CC", change + timedelta(days=1)),    # after, but an EDM
        ]:
            await db.execute(text("""
                INSERT INTO self_serve_idempotency_keys (idempotency_key, email, org_id, created_at)
                SELECT :k, :e, o.id, :at FROM organisations o WHERE o.name = :n
            """), {"k": f"key-{name}", "e": f"{name}@x.com", "n": name, "at": at})

        # A webinar registration from before the ad launched — /demo has been
        # live since v9.71.1, so an organic one is ordinary. It must fall
        # outside the since-the-change window.
        await db.execute(text(
            "UPDATE webinar_registrations SET created_at = :at WHERE email = 'a@x.com'"
        ), {"at": change - timedelta(days=2)})

        # TRUE daily per-ad rows (level='ad_daily'). The trial's straddle the
        # change; the webinar's begin at it.
        rows: list[tuple] = []
        for i in range(1, 11):
            rows.append((change - timedelta(days=i), TRIAL_AD,
                         "Ad_ClubHistory_Trial_Hero_v3", 176.40))
        for d in (change, change + timedelta(days=1)):
            rows.append((d, TRIAL_AD, "Ad_ClubHistory_Trial_Hero_v3", 18.0))
            rows.append((d, WEBINAR_AD, "Ad_Webinar_LiveDemo_21Sep2026_v2", 60.0))
        for snapshot_date, ad_id, ad_name, spend in rows:
            await db.execute(text("""
                INSERT INTO meta_ad_snapshots
                    (snapshot_date, level, campaign_id, ad_id, ad_name, spend,
                     impressions, link_clicks, landing_page_views, leads)
                VALUES (:d, 'ad_daily', :c, :a, :n, :s, 1000, 20, 15, 0)
            """), {"d": snapshot_date, "c": CAMPAIGN_ID, "a": ad_id, "n": ad_name, "s": spend})
        await db.commit()


ADS = [
    {"ad_id": WEBINAR_AD, "ad_name": "Ad_Webinar_LiveDemo_21Sep2026_v2", "name": "Ad_Webinar_LiveDemo_21Sep2026_v2",
     "spend": 120.0, "impressions": 9000, "link_clicks": 200, "landing_page_views": 150,
     "leads": 0, "delivery_status": "ACTIVE", "utm_content": "live_demo_hero"},
    {"ad_id": TRIAL_AD, "ad_name": "Ad_ClubHistory_Trial_Hero_v3", "name": "Ad_ClubHistory_Trial_Hero_v3",
     "spend": 1800.0, "impressions": 220000, "link_clicks": 1760, "landing_page_views": 1600,
     "leads": 20, "delivery_status": "PAUSED", "utm_content": "club_history_hero"},
    # Paused, live from 22 Sep — nothing recorded. Must not divide by zero.
    {"ad_id": NEW_AD, "ad_name": "Ad_Trial_Spreadsheet_Sep2026", "name": "Ad_Trial_Spreadsheet_Sep2026",
     "spend": 0.0, "impressions": 0, "link_clicks": 0, "landing_page_views": 0,
     "leads": 0, "delivery_status": "PAUSED", "utm_content": "spreadsheet_hero"},
]


async def main() -> int:
    if not HAVE:
        print("\nThe meta_ads service is absent — reporting the feature rather than crashing.")
        return 1
    if missing(["stream_for_ad", "stream_for_attribution", "stream_totals", "build_streams",
                "compute_stream_funnel", "get_webinar_registration_counts",
                "get_creative_performance", "campaign_annotations", "CAMPAIGN_UTM_CAMPAIGNS",
                "ATTRIBUTION_WINDOW_DAYS"]):
        print("\nThe conversion split is not present — reporting it rather than "
              "reading past it into checks that cannot mean anything.")
        return 1

    engine = create_async_engine(DB_URL, future=True)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    await setup(session_maker)
    await seed(session_maker)

    m._active_campaign.set(CAMPAIGN_ID)
    change_date = m._last_change_date()
    if change_date:
        await seed_since(session_maker, change_date)
    for ad in ADS:
        ad["stream"] = m.stream_for_ad(ad["ad_id"], ad["ad_name"])

    # ── Classification ──────────────────────────────────────────────────────
    ck("the webinar ad is classified as the webinar stream",
       m.stream_for_ad(WEBINAR_AD) == "webinar")
    ck("the trial ads are classified as the trial stream",
       m.stream_for_ad(TRIAL_AD) == "trial" and m.stream_for_ad(NEW_AD) == "trial")
    ck("an ad NOT in the map at all is classified by its name",
       m.stream_for_ad("nope", "Ad_Webinar_LiveDemo_Oct2026_v1") == "webinar")
    ck("an ad with no webinar in its name sells the trial, as every ad did before",
       m.stream_for_ad("nope2", "Ad_SomethingBrandNew") == "trial")
    ck("the superseded webinar ad is still a webinar ad",
       m.stream_for_ad("120251267750770121") == "webinar")

    # ── Attribution: the set-valued map is what stops it failing closed ─────
    for tag in ("webinar_21sep2026", "trial_evergreen_sep2026", "BC_AU_Trials_CBO_Aug2026"):
        ck(f"a registration tagged {tag} counts for this campaign",
           m._attribution_matches_campaign({"utm_campaign": tag}))
    ck("a registration from an unrelated campaign does not",
       not m._attribution_matches_campaign({"utm_campaign": "spring_edm_2026", "utm_source": "email"}))
    ck("a registration with no attribution at all does not",
       not m._attribution_matches_campaign({}) and not m._attribution_matches_campaign(None))

    # ── Webinar counts from our own table ───────────────────────────────────
    async with session_maker() as db:
        counts = await m.get_webinar_registration_counts(db)
    ck("webinar registrations tagged to this campaign are counted",
       counts["attributed"] == 3, str(counts))
    ck("the untagged ones are reported separately, neither claimed nor hidden",
       counts["unattributed"] == 2, str(counts))
    ck("somebody else's tagged registration is counted as neither",
       counts["total"] == 6 and counts["attributed"] + counts["unattributed"] == 5, str(counts))

    async with session_maker() as db:
        trial_results = await m.get_registration_count(db)
    # Four attributed: three dated either side of the change plus Echo CC,
    # which carries no signup timestamp at all. The EDM signup and the archived
    # test one are excluded.
    ck("trial signups count this campaign's own, and not an EDM's",
       trial_results == 4, f"got {trial_results}")

    # ── The split itself ────────────────────────────────────────────────────
    campaign = {"spend": 1920.29}
    streams, unattributed_spend = m.build_streams(
        ADS, campaign, trial_results=trial_results,
        webinar_counts=counts, club_selected=25)
    by = {s["stream"]: s for s in streams}
    t, w = by["trial"], by["webinar"]

    ck("each stream carries its OWN spend, summed from its own ads",
       t["spend"] == 1800.0 and w["spend"] == 120.0, f"{t['spend']} / {w['spend']}")
    ck("cost per trial signup is trial spend over trial signups",
       t["cost_per_result"] == round(1800.0 / trial_results, 2), str(t["cost_per_result"]))
    ck("cost per webinar registration is webinar spend over webinar registrations",
       w["cost_per_result"] == round(120.0 / 3, 2), str(w["cost_per_result"]))
    # The figure the page used to show: whole-campaign spend over trial signups.
    old_figure = round(campaign["spend"] / trial_results, 2)
    ck("the pre-split figure charged the trial with the webinar's spend",
       old_figure > t["cost_per_result"],
       f"was A${old_figure}, now A${t['cost_per_result']}")
    ck("spend no ad accounts for is surfaced, not folded into a stream",
       unattributed_spend == round(1920.29 - 1920.0, 2), str(unattributed_spend))

    # ── Value ───────────────────────────────────────────────────────────────
    ck("only the trial carries a value", t["carries_value"] and not w["carries_value"])
    ck("the trial's attributed value is its signups at the Core annual price",
       t["attributed_value_aud"] == trial_results * 399.0, str(t["attributed_value_aud"]))
    ck("a webinar registration contributes nothing to revenue",
       w["attributed_value_aud"] == 0.0 and w["roas"] is None)
    ck("the trial has a ROAS and it divides by the trial's own spend",
       t["roas"] == round(trial_results * 399.0 / 1800.0, 2), str(t["roas"]))

    # ── Funnels ─────────────────────────────────────────────────────────────
    ck("each funnel ends in its own stream's result",
       t["funnel"][-1]["value"] == trial_results and w["funnel"][-1]["value"] == counts["attributed"])
    ck("the trial funnel keeps the wizard's Club selected step",
       any(s["key"] == "club_selected" for s in t["funnel"]))
    ck("the webinar funnel has no Club selected step — there is no wizard on /demo",
       not any(s["key"] == "club_selected" for s in w["funnel"]))
    ck("each funnel's top is its own stream's impressions",
       t["funnel"][0]["value"] == 220000 and w["funnel"][0]["value"] == 9000)

    # ── Creatives ───────────────────────────────────────────────────────────
    async with session_maker() as db:
        creatives = await m.get_creative_performance(db, ADS)
    by_tag = {c["utm_content"]: c for c in creatives}
    ck("every creative is keyed on its utm_content",
       {"club_history_hero", "live_demo_hero", "spreadsheet_hero"} <= set(by_tag), str(list(by_tag)))
    ck("a creative's spend is its own ad's",
       by_tag["club_history_hero"]["spend"] == 1800.0 and by_tag["live_demo_hero"]["spend"] == 120.0)
    ck("a creative keeps its two result counts apart",
       by_tag["club_history_hero"]["trial_signups"] == 2
       and by_tag["club_history_hero"]["webinar_registrations"] == 0
       and by_tag["live_demo_hero"]["webinar_registrations"] == 3
       and by_tag["live_demo_hero"]["trial_signups"] == 0,
       str({k: (v["trial_signups"], v["webinar_registrations"]) for k, v in by_tag.items()}))
    ck("a creative that has never spent has no cost per result rather than a zero",
       by_tag["spreadsheet_hero"]["cost_per_result"] is None)
    ck("the EDM signup reaches no creative row",
       sum(c["trial_signups"] for c in creatives) == trial_results,
       str(sum(c["trial_signups"] for c in creatives)))

    # ── Nothing divides by zero ─────────────────────────────────────────────
    empty, gap = m.build_streams([], {"spend": 0.0}, trial_results=0,
                                 webinar_counts={"attributed": 0, "unattributed": 0, "total": 0})
    ck("a campaign with no ads at all reports no cost per result and no ROAS",
       all(s["cost_per_result"] is None and s["roas"] is None for s in empty))
    ck("and no phantom unattributed spend", gap == 0.0)

    # ── Change annotations and pacing ───────────────────────────────────────
    ann = m.campaign_annotations()
    ck("the 8 Sep restructure is recorded as a change marker",
       len(ann) == 1 and ann[0]["date"] == "2026-09-08", str(ann))
    ck("it says what actually changed",
       "A$50" in ann[0]["detail"] and "A$30" in ann[0]["detail"], ann[0]["detail"] if ann else "")

    today = date.today()

    def day(n: int) -> str:
        return (today - timedelta(days=n)).isoformat()

    # $50/day before a change 10 days ago, $30/day after it.
    history = ([{"date": day(n), "spend": 50.0} for n in range(30, 10, -1)]
               + [{"date": day(n), "spend": 30.0} for n in range(10, -1, -1)])
    saved = m.CAMPAIGN_ANNOTATIONS.get(CAMPAIGN_ID)
    m.CAMPAIGN_ANNOTATIONS[CAMPAIGN_ID] = [
        {"date": day(10), "label": "Campaign restructured", "detail": "…"}]
    ins = m.build_insights({"spend": 1920.0, "impressions": 231168, "link_clicks": 1962,
                            "landing_page_views": 1753, "leads": 20, "registrations": 3},
                           [], history, 600.0, 30, streams=streams)
    pacing = [i for i in ins if "pac" in i["title"].lower()]
    ck("pacing is measured from the last deliberate change", bool(pacing), str([i["title"] for i in ins]))
    if pacing:
        # The post-change rate is $30/day -> $900 over 30 days. The pre-change
        # rate would have projected $1500 and shouted much louder.
        ck("it projects the POST-change rate, not the pre-change one or a blend",
           "~$900" in pacing[0]["detail"] and "1500" not in pacing[0]["detail"], pacing[0]["detail"])
        ck("and it says which period it measured", "since the" in pacing[0]["detail"])

    # A change younger than the attribution window: results are still filling in,
    # so a zero-result stream must not be reported as failing.
    m.CAMPAIGN_ANNOTATIONS[CAMPAIGN_ID] = [
        {"date": day(1), "label": "Campaign restructured", "detail": "…"}]
    zero = [dict(w, results=0, cost_per_result=None, spend=120.0, landing_page_views=150)]
    fresh = m.build_insights({"spend": 120.0, "impressions": 9000, "link_clicks": 200,
                              "landing_page_views": 150, "leads": 0, "registrations": 0},
                             [], history, 600.0, 30, streams=zero)
    ck("a change inside the attribution window is called out as still settling",
       any("still settling" in i["title"] for i in fresh), str([i["title"] for i in fresh]))
    ck("and a zero-result stream is NOT reported as failing while it settles",
       not any(i["title"].startswith("No ") for i in fresh), str([i["title"] for i in fresh]))

    # Once settled, the same shape does fire.
    m.CAMPAIGN_ANNOTATIONS[CAMPAIGN_ID] = [
        {"date": day(20), "label": "Campaign restructured", "detail": "…"}]
    settled = m.build_insights({"spend": 120.0, "impressions": 9000, "link_clicks": 200,
                                "landing_page_views": 150, "leads": 0, "registrations": 0},
                               [], history, 600.0, 30, streams=zero)
    ck("once settled, a stream that spent and produced nothing IS reported",
       any(i["title"].startswith("No ") for i in settled), str([i["title"] for i in settled]))
    if saved is not None:
        m.CAMPAIGN_ANNOTATIONS[CAMPAIGN_ID] = saved

    ck("the attribution window is Meta's 7-day click window",
       m.ATTRIBUTION_WINDOW_DAYS == 7, str(m.ATTRIBUTION_WINDOW_DAYS))

    # ── Since the change, measured on its own ───────────────────────────────
    # A lifetime cost per result answers "what has this cost in all". It cannot
    # answer "what are we paying NOW", and for the trial the two are far apart:
    # its lifetime spend is mostly the campaign that ran before the restructure,
    # while the webinar has no pre-change history to dilute it.
    if missing(["stream_totals_since", "get_registration_count_since",
                "get_webinar_registration_count_since", "_since_change_block"]):
        print("\nThe since-the-change split is not present — reporting it rather "
              "than reading past it.")
    elif not change_date:
        ck("there is a change to measure from", False, "no annotation")
    else:
        async with session_maker() as db:
            since_spend = await m.stream_totals_since(db, change_date)
            trial_since = await m.get_registration_count_since(db, change_date)
            webinar_since = await m.get_webinar_registration_count_since(db, change_date)

        st = since_spend["totals"]
        ck("the trial's spend since the change is its own post-change spend only",
           st["trial"]["spend"] == 36.0, str(st["trial"]["spend"]))
        ck("and that is a fraction of its lifetime spend, which is the point",
           st["trial"]["spend"] < t["spend"] / 10,
           f"{st['trial']['spend']} vs {t['spend']}")
        ck("the webinar's since-the-change spend IS its lifetime spend — it has no history before it",
           st["webinar"]["spend"] == w["spend"] == 120.0, str(st["webinar"]["spend"]))
        ck("a complete window is not reported as partial",
           since_spend["partial"] is False, str(since_spend))

        ck("a trial signup from before the change is not counted since it",
           trial_since["count"] == 2, str(trial_since))
        ck("a signup we hold no date for is reported, neither counted nor dropped",
           trial_since["undated"] == 1, str(trial_since))
        ck("an EDM signup is excluded from the windowed count too",
           trial_since["count"] + trial_since["undated"] == 3, str(trial_since))
        ck("a webinar registration from before the ad launched falls outside the window",
           webinar_since == 2, str(webinar_since))

        since_ctx = {
            "since": change_date, "totals": st, "partial": since_spend["partial"],
            "results": {"trial": trial_since["count"], "webinar": webinar_since},
        }
        streams2, _ = m.build_streams(
            ADS, campaign, trial_results=trial_results,
            webinar_counts=counts, club_selected=25, since_change=since_ctx)
        by2 = {s["stream"]: s for s in streams2}
        t2, w2 = by2["trial"]["since_change"], by2["webinar"]["since_change"]

        ck("each stream carries a since-the-change block",
           t2 is not None and w2 is not None)
        ck("cost per trial signup since the change is its own spend over its own results",
           t2["cost_per_result"] == round(36.0 / 2, 2), str(t2["cost_per_result"]))
        ck("cost per webinar registration since the change likewise",
           w2["cost_per_result"] == round(120.0 / 2, 2), str(w2["cost_per_result"]))
        ck("the trial's since figure is NOT its lifetime figure",
           t2["cost_per_result"] != by2["trial"]["cost_per_result"],
           f"{t2['cost_per_result']} vs {by2['trial']['cost_per_result']}")
        ck("and it is far lower, because the lifetime one carries the old campaign",
           t2["cost_per_result"] < by2["trial"]["cost_per_result"] / 10,
           f"{t2['cost_per_result']} vs {by2['trial']['cost_per_result']}")
        ck("the block says which date it measures from",
           t2["since"] == change_date.isoformat(), str(t2["since"]))
        ck("results still arriving inside the 7-day window are marked provisional",
           t2["provisional"] is True, str(t2))

        # ── The guards, driven directly ─────────────────────────────────────
        base = {"since": change_date, "partial": False,
                "totals": {"trial": {"spend": 100.0}}, "results": {"trial": 4}}
        ck("a complete window with results divides",
           m._since_change_block("trial", base)["cost_per_result"] == 25.0)

        part = dict(base, partial=True)
        blk = m._since_change_block("trial", part)
        ck("a PARTIAL window withholds the figure rather than understating it",
           blk["cost_per_result"] is None, str(blk))
        ck("and says why, so silence doesn't read as a bug",
           blk["withheld_reason"] == "partial_window", str(blk))
        ck("its spend is still reported, so the window isn't simply blank",
           blk["spend"] == 100.0, str(blk))

        none_yet = dict(base, results={"trial": 0})
        blk = m._since_change_block("trial", none_yet)
        ck("no results yet divides by nothing rather than by zero",
           blk["cost_per_result"] is None and blk["withheld_reason"] == "no_results_yet",
           str(blk))

        no_spend = dict(base, totals={"trial": {"spend": 0.0}})
        blk = m._since_change_block("trial", no_spend)
        ck("no spend yet is reported as that, not as a free result",
           blk["cost_per_result"] is None and blk["withheld_reason"] == "no_spend_yet",
           str(blk))

        settled = dict(base, since=date.today() - timedelta(days=m.ATTRIBUTION_WINDOW_DAYS + 1))
        blk = m._since_change_block("trial", settled)
        ck("a change older than the attribution window is no longer provisional",
           blk["provisional"] is False, str(blk))

        ck("a campaign with no change to measure from carries no block at all",
           m._since_change_block("trial", None) is None)

        # A stream nothing spent on must not invent a figure here either.
        empty2, _ = m.build_streams([], {"spend": 0.0}, trial_results=0,
                                    webinar_counts={"attributed": 0, "unattributed": 0, "total": 0},
                                    since_change=since_ctx)
        ck("a campaign with no ads still reports a block without dividing by zero",
           all(s["since_change"] is not None and s["since_change"]["cost_per_result"] is not None
               or s["since_change"]["withheld_reason"] for s in empty2))

    await engine.dispose()
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
