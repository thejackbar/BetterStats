"""BC_AU_Trial_CBO_Sep2026 (120251284365570121): its tags, its plan and its fresh start.

    cd backend && python verification/verify_meta_ads_new_campaign.py

Pure functions of the shipped service module, so no database is needed.

What a reader can be misled by, and so what is measured:
  * A registration through the new ads must be RECOGNISED as the new campaign's
    own. Asserting only that it "matches" proves nothing, because an unknown tag
    with utm_source=meta already matches by the loosest fallback. The two checks
    that can fail are: the tag is in the campaign's own set, and the same signup
    is NOT swept into the OLD campaign's count (a known tag of another campaign
    is refused by the fallback).
  * The old campaign's tags must still belong to the old campaign and not leak
    into the new one (the restart is meant to start from zero).
  * The plan is the new one, not the A$750 / 30 day fallback, and pacing starts
    at the restart date rather than reaching back across A$1,700 of history.

Control runs must REPORT, not crash: every read of something this change adds
goes through .get / presence-safe helpers.
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import meta_ads as m  # noqa: E402

NEW = "120251284365570121"
OLD = "120250149119070121"
NEW_TAG = "BC_AU_Trial_CBO_Sep2026"
RESTART = date(2026, 11, 10)

pass_n = fail_n = 0


def ck(name, cond, extra=""):
    global pass_n, fail_n
    if cond:
        pass_n += 1
        print(f"PASS {name}")
    else:
        fail_n += 1
        print(f"FAIL {name}  {extra}")


def using(cid):
    m._active_campaign.set(cid)


def signup(content, campaign=NEW_TAG, source="meta"):
    return {"utm_source": source, "utm_medium": "paid_social",
            "utm_campaign": campaign, "utm_content": content, "click_source": "facebook"}


# The one ad delivering when this was written, and the tag Ads Manager must carry.
LIVE_AD = "120251342626760121"
LIVE_CONTENT = "check_out_your_club_v2"

# ── tags ─────────────────────────────────────────────────────────────────────
own_tags = {t.lower() for t in (m.CAMPAIGN_UTM_CAMPAIGNS.get(NEW) or set())}
ck("the new campaign has its own utm_campaign set", NEW_TAG.lower() in own_tags, str(own_tags))

using(NEW)
ck("a signup through the live ad is counted for the new campaign", m._attribution_matches_campaign(signup(LIVE_CONTENT)))
using(OLD)
ck("the same signup is NOT swept into the old campaign (known tag of another campaign)",
   not m._attribution_matches_campaign(signup(LIVE_CONTENT)))

using(NEW)
old_trial = signup("spreadsheet_hero", campaign="trial_evergreen_sep2026")
old_aug = signup("club_history_hero", campaign="BC_AU_Trials_CBO_Aug2026")
ck("the old campaign's tags do not count for the new one (fresh start)",
   not m._attribution_matches_campaign(old_trial) and not m._attribution_matches_campaign(old_aug))
using(OLD)
ck("and they still count for the old one (paired, so the check above can fail)",
   m._attribution_matches_campaign(old_trial) and m._attribution_matches_campaign(old_aug))

# ── ads ──────────────────────────────────────────────────────────────────────
entry = m.AD_DESTINATIONS.get(LIVE_AD) or {}
ck("the live ad is mapped to the new campaign", entry.get("campaign_id") == NEW, str(entry))
ck("with the utm_content the ad must carry", entry.get("utm_content") == LIVE_CONTENT, str(entry.get("utm_content")))
ck("and it sells the trial", m.stream_for_ad(LIVE_AD, "Ad_CheckOutYourClub_v2_Relaunch") == m.STREAM_TRIAL)
using(NEW)
mine = m._current_campaign_utm_contents()
ck("the new campaign's own utm_contents include the live ad's", LIVE_CONTENT in mine, str(mine))

mapped = {k: v for k, v in m.AD_DESTINATIONS.items() if v.get("campaign_id") == NEW}
contents = [v.get("utm_content") for v in mapped.values() if v.get("utm_content")]
ck("every new-campaign ad that is mapped carries a utm_content", bool(mapped) and len(contents) == len(mapped), str(mapped.keys()))
ck("no two new-campaign ads share a utm_content", len(contents) == len(set(contents)), str(contents))
others = {v.get("utm_content") for v in m.AD_DESTINATIONS.values()
          if v.get("campaign_id") != NEW and v.get("utm_content")}
ck("none of them reuses another campaign's tag", bool(contents) and not (set(contents) & others), str(set(contents) & others))

# ── plan and fresh start ─────────────────────────────────────────────────────
using(NEW)
ck("the plan is A$450 over 30 days, not the A$750 fallback", m._campaign_plan() == (450.0, 30), str(m._campaign_plan()))
ck("the restart is recorded as a deliberate change", m._last_change_date() == RESTART, str(m._last_change_date()))
notes = m.campaign_annotations()
ck("and it is on the chart with a label", bool(notes) and bool(notes[-1].get("label")) and bool(notes[-1].get("detail")), str(notes))
using(OLD)
ck("the old campaign's plan and markers are untouched", m._campaign_plan() == (900.0, 30) and m._last_change_date() == date(2026, 9, 8),
   f"{m._campaign_plan()} {m._last_change_date()}")

print(f"\n{pass_n} passed, {fail_n} failed")
sys.exit(1 if fail_n else 0)
