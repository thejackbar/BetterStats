"""Where a club's engagement score came from, and how much each source gave it.

``twenty_sync._engagement()`` is the only place a point is ever awarded. It
records what it awarded into ``_sourcePoints`` (``{source_key: points}``) and
which signals it saw but did NOT pay for into ``_sourcePresent`` as it goes,
so this module never re-derives a number — it labels, groups and orders the
ones already decided. Two copies of "how many points is a Meta ad click
worth" is how the CRM's chart and the score itself start disagreeing.

The keys are the CRM's own vocabulary. They are cached per club
(``marketing_clubs.engagement_sources``, migration 270) so the pipeline can
be filtered by source without recomputing a per-club scan, and they are what
the deal detail card and the Sales Workspace drawer draw their chart from.
**A key here is permanent** — renaming one silently drops every saved filter
that names it, and orphans the cached maps until the next full recalc.

A source can be PRESENT with zero points. A club whose score is pinned by a
direct enquiry, or held up by the registration floor, still clicked those ads
— the activity just is not what the number is made of today. Reporting it as
absent would answer "has this club come to us through Meta ads?" with a flat
no, which is the question the source filter exists to ask.
"""
from __future__ import annotations

# Category → how the CRM groups and colours a source. Order is the order the
# chart and the itemised list draw in.
CATEGORIES = (
    ("engagement", "Engagement signals"),
    ("intent", "Buying intent"),
    ("setup", "Setup & registration"),
    ("account", "Customer account"),
)
CATEGORY_ORDER = [c for c, _ in CATEGORIES]

# key, label, category, what it means in one line for the CRM's own tooltip.
SOURCES = (
    ("visitors", "Distinct site visitors", "engagement",
     "People who reached this club's pages or an outreach link in the last 30 days."),
    ("page_views", "Website page views", "engagement",
     "How much of the site those visits actually read, weighted so recent views count for more."),
    ("meta_ads", "Meta / paid ad clicks", "engagement",
     "Arrivals carrying a Facebook or Instagram ad click, scored higher than an organic visit."),
    ("email_clicks", "Email clicks", "engagement",
     "Clicks on a link in an outreach email — the strongest email signal there is."),
    ("email_opens", "Email opens", "engagement",
     "Opens of an outreach email. Worth less than a click, since a mail client can fire one on its own."),
    ("recency", "Recency of last activity", "engagement",
     "How recently this club last did anything at all, halving as it ages."),
    ("contact_enquiry", "'Contact us' enquiry", "intent",
     "Somebody asked, on the public site, to have this club onboarded."),
    ("contact_page", "Visited the contact page", "intent",
     "An attributed visit reached /contact — looking for a way to get in touch, not just browsing."),
    ("trial_page", "Visited the trial signup page", "intent",
     "An attributed visit reached /trial, where a club picks itself and starts a self-serve trial."),
    ("trial_requested", "Requested a trial", "intent",
     "Modules this club has asked to try, recorded in the Club Directory's sales panel."),
    ("in_trial", "Currently in a trial", "intent",
     "The Club Directory has this club flagged as trialing right now."),
    ("ad_signup", "Registered from a paid ad", "intent",
     "A paid ad click carried all the way through to a real registration."),
    ("self_serve_registration", "Registered themselves (self-serve)", "setup",
     "The club signed itself up through /trial rather than being set up by us."),
    ("staff_registration", "Registered by BetterCricket (Super Admin)", "setup",
     "We created this club. Real setup, but a weaker signal of the club's own interest, so it scores lower."),
    ("import_stats", "Imported historical stats", "setup",
     "Ran the historical-import wizard — real work a club only does if it means to stay."),
    ("merges", "Merged players or grades", "setup",
     "Tidied duplicate players or grades, which means somebody is actually using the data."),
    ("module_setup", "Set up paid-module features", "setup",
     "Fee schedules, Square/Xero, squads, fixtures and the like — using what they are trialing."),
    ("admin_polish", "Branding, sponsors and invites", "setup",
     "Colours, crest, sponsors, inviting other admins — making it their own."),
    ("customer_base", "Paying customer baseline", "account",
     "A club paying for at least one module starts engaged; its score is account health, not lead heat."),
    ("upsell", "Open upsell opportunity", "account",
     "Modules this customer wants but does not pay for yet."),
)

_BY_KEY = {k: {"key": k, "label": lab, "category": cat, "description": desc}
           for k, lab, cat, desc in SOURCES}
SOURCE_ORDER = [k for k, _, _, _ in SOURCES]
_POSITION = {k: i for i, k in enumerate(SOURCE_ORDER)}

# A driver is what the score IS, not merely what fed it. Only one applies.
DRIVER_ACTIVITY = "activity"
DRIVER_SETUP_FLOOR = "setup_floor"
DRIVER_DIRECT_ENQUIRY = "direct_enquiry"
DRIVER_CUSTOMER = "customer"


def source_meta(key: str) -> dict:
    """Label/category/description for one key. An unknown key (a cached map
    written by an older build, or a key since retired) still renders as
    itself rather than vanishing from a club's chart."""
    return _BY_KEY.get(key) or {
        "key": key,
        "label": key.replace("_", " ").capitalize(),
        "category": "engagement",
        "description": "",
    }


def catalogue() -> list[dict]:
    """The whole vocabulary, in draw order — what the CRM's source filter
    offers, so the pickable options and the scorer can't drift apart."""
    return [dict(_BY_KEY[k]) for k in SOURCE_ORDER]


def _plural(n, one, many=None):
    return f"{n} {one if n == 1 else (many or one + 's')}"


def _detail(key: str, eng: dict) -> str:
    """The counts behind a source, phrased for the person reading the card.
    Formatting only — every number here is one the scorer already recorded."""
    if key == "visitors":
        n = eng.get("sessions30d") or 0
        return (f"{_plural(n, 'distinct visitor')} in the last 30 days, "
                "deduped by IP so one person reloading is still one visitor.")
    if key == "page_views":
        return (f"{_plural(eng.get('_events30d') or 0, 'page view or API call')} in 30 days. "
                "Older views are worth less, and nothing past 90 days counts.")
    if key == "meta_ads":
        return f"{_plural(eng.get('_adClicks') or 0, 'ad-click landing')} all-time."
    if key == "email_clicks":
        return (f"{_plural(eng.get('_emailClicks') or 0, 'click')} all-time, "
                f"{eng.get('_emailClicks30d') or 0} in 30 days.")
    if key == "email_opens":
        opens, clicks = eng.get("_emailOpens") or 0, eng.get("_emailClicks") or 0
        base = f"{_plural(opens, 'open')} all-time, {eng.get('_emailOpens30d') or 0} in 30 days"
        if not opens and not clicks:
            return base + ". Open and click tracking may be off, so 0 means no data rather than no interest."
        return base + "."
    if key == "recency":
        return "The most recent web, email or enquiry touch of any kind, halving every three weeks."
    if key == "contact_enquiry":
        n = eng.get("_onboardingCount") or 0
        if eng.get("_directEnquiryHot"):
            return (f"{_plural(n, 'enquiry', 'enquiries')} on file. A recent one holds the score here "
                    "outright for a set window instead of adding to a tally.")
        return f"{_plural(n, 'enquiry', 'enquiries')} on file."
    if key == "staff_registration":
        return "Set up by us, so it earns less than a club that registered itself."
    if key == "self_serve_registration":
        return "The club registered itself, which is the strongest setup signal there is."
    return _BY_KEY.get(key, {}).get("description", "")


def _customer_note(eng: dict) -> str:
    return ("Site and email activity is folded into one product-use term for a paying customer, "
            "capped at 20 points, and split here in proportion to what each signal contributed.")


def build(eng: dict) -> dict:
    """Turn one ``_engagement()`` result into the CRM's breakdown: an ordered,
    categorised contribution list, the per-source point map to cache, and a
    sentence saying what the score actually is.

    Reads only the ``_source*`` fields the scorer recorded, so this never has
    an opinion about what a signal is worth."""
    points = dict(eng.get("_sourcePoints") or {})
    present = list(eng.get("_sourcePresent") or [])
    driver = eng.get("_driver") or DRIVER_ACTIVITY
    score = eng.get("engagementScore") or 0
    raw_total = float(eng.get("_sourceTotal") or 0.0)

    contributions = []
    for key in sorted(set(points) | set(present), key=lambda k: _POSITION.get(k, 999)):
        pts = round(float(points.get(key) or 0.0), 1)
        meta = source_meta(key)
        if pts == 0 and key not in present:
            continue
        contributions.append({
            "key": key,
            "label": meta["label"],
            "category": meta["category"],
            "points": pts,
            # Present but not paying: the club really did this, it just is not
            # what the number is made of under the current driver.
            "present_only": pts == 0,
            "detail": _detail(key, eng),
        })

    scoring = [c for c in contributions if not c["present_only"]]
    scored_total = round(sum(c["points"] for c in scoring), 1)

    if driver == DRIVER_DIRECT_ENQUIRY:
        explanation = (f"A recent 'onboard my club' enquiry holds this club at {score} for a set window. "
                       "Everything else it has done is listed below, but the enquiry is the score.")
    elif driver == DRIVER_SETUP_FLOOR:
        explanation = (f"Setting the club up in BetterStats sets a floor of {score}, which is higher than "
                       f"the ~{round(raw_total)} its activity has earned, so the floor is the score.")
    elif driver == DRIVER_CUSTOMER:
        explanation = ("This club pays for at least one module, so the score is account health rather than "
                       "lead heat: a baseline, plus how recently and how much they use it. " + _customer_note(eng))
    else:
        explanation = f"These signals add up to {round(raw_total)}, and that is the score."
        floor = float(eng.get("_setupFloor") or 0.0)
        if floor:
            explanation += (f" A registration floor of {round(floor)} also applies, but the club's own "
                            "activity is already above it.")
    if raw_total > 100 and driver in (DRIVER_ACTIVITY, DRIVER_CUSTOMER):
        explanation += " The total is capped at 100."

    return {
        "driver": driver,
        "explanation": explanation,
        "contributions": contributions,
        # Cached per club: every source seen, whether it paid or not, so the
        # pipeline's source filter can answer "came to us through X" and the
        # chart can answer "how much of the score is X" off the one map.
        "sources": {c["key"]: c["points"] for c in contributions},
        "scored_total": scored_total,
        "raw_total": round(raw_total, 1),
    }
