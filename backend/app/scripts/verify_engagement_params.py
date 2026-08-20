"""Assert that the engagement-score PARAMETERS, left at their defaults, score
exactly as the hardcoded constants they replaced did.

This is the guard on the parameterisation itself: the values, the generated SQL
(byte-for-byte against the ladders that used to be written out by hand at four
separate sites), the two defect fixes staying off until someone turns them on,
and the fact that no stored value can reach a query as anything but a number.

Run it after touching services/engagement_params.py or any of the weights:

    python -m app.scripts.verify_engagement_params

Needs no database. Stubs the auth import chain, which platform_settings pulls in
for an unrelated dependency and nothing under test touches."""
import sys, types
_auth = types.ModuleType("app.routers.auth")
_auth.get_current_club = lambda *a, **k: None
sys.modules["app.routers.auth"] = _auth

from app.services import twenty_sync as ts
from app.services import trial_engagement as te
from app.services import engagement_params as ep

fails = []
def check(label, got, want):
    ok = got == want
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        print(f"          got  {got!r}\n          want {want!r}")
        fails.append(label)

print("\n1. Module constants match the values that were hardcoded before")
check("WEB_DECAY", ts.WEB_DECAY, {"d7":2.0,"d14":1.5,"d21":1.0,"d28":0.5,"d90":0.25})
check("AD_DECAY", ts.AD_DECAY, {"d7":5.0,"d14":3.5,"d21":2.0,"d28":1.0,"d90":0.5})
check("EMAIL_CLICK_DECAY", ts.EMAIL_CLICK_DECAY, {"d7":10.0,"d14":7.5,"d21":5.0,"d28":2.0,"d90":1.0})
check("EMAIL_OPEN_DECAY", ts.EMAIL_OPEN_DECAY, {"d7":4.0,"d14":3.0,"d21":2.0,"d28":1.0,"d90":1.0})
check("REACH_PER_VISITOR", ts.REACH_PER_VISITOR, 2.5)
check("DEPTH_SCALE", ts.DEPTH_SCALE, 0.6)
check("RECENCY_FULL", ts.RECENCY_FULL, 10.0)
check("RECENCY_HALFLIFE_DAYS", ts.RECENCY_HALFLIFE_DAYS, 21.0)
check("BONUS_REQUESTED_TRIAL", ts.BONUS_REQUESTED_TRIAL, 12)
check("BONUS_IN_TRIAL", ts.BONUS_IN_TRIAL, 10)
check("BONUS_ONBOARDING", ts.BONUS_ONBOARDING, 20)
check("BONUS_CONTACT_PAGE", ts.BONUS_CONTACT_PAGE, 10)
check("BONUS_VISIT_TRIAL", ts.BONUS_VISIT_TRIAL, 20)
check("BONUS_AD_SIGNUP", ts.BONUS_AD_SIGNUP, 10)
check("CUSTOMER_BASE", ts.CUSTOMER_BASE, 60)
check("CUSTOMER_UPSELL_BONUS", ts.CUSTOMER_UPSELL_BONUS, 15)
check("CUSTOMER_ONBOARDING_BONUS", ts.CUSTOMER_ONBOARDING_BONUS, 10)
check("TIER_WARM_MIN", ts.TIER_WARM_MIN, 30)
check("TIER_HOT_MIN", ts.TIER_HOT_MIN, 60)
check("DIRECT_ENQUIRY_SCORE", ts.DIRECT_ENQUIRY_SCORE, 80)
check("OPPORTUNITY_AUTO_THRESHOLD", ts.OPPORTUNITY_AUTO_THRESHOLD, 90)
check("trial: REGISTRATION_CLUB_ADMIN", te.REGISTRATION_CLUB_ADMIN, 70)
check("trial: REGISTRATION_SUPER_ADMIN", te.REGISTRATION_SUPER_ADMIN, 40)
check("trial: SUPER_ADMIN_ACTOR_FRACTION", te.SUPER_ADMIN_ACTOR_FRACTION, 0.3)
check("trial: MERGE_BONUS", te.MERGE_BONUS, 10)
check("trial: IMPORT_STATS_BONUS", te.IMPORT_STATS_BONUS, 15)
check("trial: MODULE_GROUP_BONUS", te.MODULE_GROUP_BONUS, 2)
check("trial: MODULE_GROUP_CAP", te.MODULE_GROUP_CAP, 15)
check("trial: ADMIN_POLISH_BONUS", te.ADMIN_POLISH_BONUS, 2)

print("\n2. Generated SQL is identical to the hand-written ladder it replaced")
old_web = """WHEN ue.created_at > NOW() - INTERVAL '7 days' THEN 2.0
                   WHEN ue.created_at > NOW() - INTERVAL '14 days' THEN 1.5
                   WHEN ue.created_at > NOW() - INTERVAL '21 days' THEN 1.0
                   WHEN ue.created_at > NOW() - INTERVAL '28 days' THEN 0.5
                   WHEN ue.created_at > NOW() - INTERVAL '90 days' THEN 0.25"""
check("web decay arms (per-club alias)", ts._decay_arms(ts.WEB_DECAY, 'ue.created_at'), old_web)
old_ad = """WHEN created_at > NOW() - INTERVAL '7 days' THEN 5.0
                   WHEN created_at > NOW() - INTERVAL '14 days' THEN 3.5
                   WHEN created_at > NOW() - INTERVAL '21 days' THEN 2.0
                   WHEN created_at > NOW() - INTERVAL '28 days' THEN 1.0
                   WHEN created_at > NOW() - INTERVAL '90 days' THEN 0.5"""
check("ad decay arms (batch alias)", ts._decay_arms(ts.AD_DECAY, 'created_at'), old_ad)
old_click = """WHEN event_type = 'click' AND created_at > NOW() - INTERVAL '7 days' THEN 10.0
                   WHEN event_type = 'click' AND created_at > NOW() - INTERVAL '14 days' THEN 7.5
                   WHEN event_type = 'click' AND created_at > NOW() - INTERVAL '21 days' THEN 5.0
                   WHEN event_type = 'click' AND created_at > NOW() - INTERVAL '28 days' THEN 2.0
                   WHEN event_type = 'click' AND created_at > NOW() - INTERVAL '90 days' THEN 1.0"""
check("email click arms", ts._decay_arms(ts.EMAIL_CLICK_DECAY, 'created_at', "event_type = 'click'"), old_click)

print("\n3. Defaults change nothing else")
check("page-view-only arm is empty by default", ts._non_page_view_arm(ep.DEFAULTS), "")
check("page-view-only arm appears when switched on",
      ts._non_page_view_arm({**ep.DEFAULTS, "COUNT_ONLY_PAGE_VIEWS": True}, "ue.").strip(),
      "WHEN ue.event_type <> 'page_view' THEN 0.0")
check("tier bands", [ts._tier_for(s) for s in (0, 29, 30, 59, 60, 100)],
      ["COLD","COLD","WARM","WARM","HOT","HOT"])
check("membership floor defaults reproduce '> 0'",
      (ep.DEFAULTS["PIPELINE_ADD_MIN"], ep.DEFAULTS["PIPELINE_REMOVE_BELOW"]), (1, 1))
check("both defect fixes default OFF",
      (ep.DEFAULTS["ENQUIRY_OVERRIDE_IS_FLOOR"], ep.DEFAULTS["COUNT_ONLY_PAGE_VIEWS"]), (False, False))
check("depth cap off by default", ep.DEFAULTS["DEPTH_PER_VISITOR_CAP"], 0.0)

print("\n4. Injected values actually reach the SQL")
tuned = {**ep.DEFAULTS, "WEB_DECAY_D7": 9.5}
check("a changed weight renders", "THEN 9.5" in ts._decay_arms(ts._curve("WEB_DECAY", tuned), 'ue.created_at'), True)
import datetime as _dt
_21d = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=21)
check("recency default: one half-life old is half of full", round(ts._recency_pts(_21d), 2), 5.0)
check("recency honours an injected half-life",
      round(ts._recency_pts(_21d, {**ep.DEFAULTS, "RECENCY_HALFLIFE_DAYS": 42.0}), 2), 7.07)
check("recency honours an injected full value",
      round(ts._recency_pts(_21d, {**ep.DEFAULTS, "RECENCY_FULL": 40.0}), 2), 20.0)

print("\n5. No value can reach SQL as anything but a number")
for bad in ("1); DROP TABLE usage_events;--", None, float("inf")):
    try:
        ep._coerce("WEB_DECAY_D7", bad)
        print(f"  FAIL  accepted {bad!r}"); fails.append("injection")
    except ValueError:
        print(f"  PASS  rejected {bad!r}")

print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILURES: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
