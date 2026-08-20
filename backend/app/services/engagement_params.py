"""Super-admin editable parameters for the engagement score.

Every number that decides a club's engagement score, and whether that club
appears on the CRM sales pipeline at all, used to be a constant in
``services/twenty_sync.py`` and ``services/trial_engagement.py``. This module is
the one place they are defined, validated, resolved and cached, so a Super Admin
can tune them from Better HQ > CRM > Engagement Score Parameters without a
deploy.

THREE THINGS TO KNOW BEFORE CHANGING ANYTHING HERE.

1. **The catalogue lives in code, the OVERRIDES live in the database.** A club
   never stores a full snapshot of every value. ``platform_settings``'s
   ``engagement_weights`` key holds only the keys a Super Admin has actually
   changed, so a later change to a ``default`` below still flows through for
   every untouched knob. The constants these replaced were tuned several times
   (the removed saturating caps, the linear reach/depth scaling), and they will
   be tuned again; a full stored snapshot would silently freeze the platform on
   whatever the defaults happened to be the day someone first opened the page.

2. **The DEFAULTS REPRODUCE THE PREVIOUS HARDCODED BEHAVIOUR EXACTLY.** That is
   what made it safe to ship. Including the two known defects, which are exposed
   as opt-in booleans (``ENQUIRY_OVERRIDE_IS_FLOOR``, ``COUNT_ONLY_PAGE_VIEWS``)
   defaulting to the old behaviour rather than being fixed silently: both change
   real scores, so they are a decision to take with the page's preview open, not
   a side effect of a deploy. See docs/engagement-score-parameters.md sections 8a
   and 9c for what each one is.

3. **Resolve ONCE per call chain and pass the dict down.** ``_engagement`` runs
   from the write path of every page view and email open (debounced 20s per club
   in crm.check_web_signal_promotion), and a full recalc calls it thousands of
   times in a loop. Never call ``get_params`` per club inside a sweep: resolve at
   the top and inject, the same way ``web_stats``/``email_stats`` already are.
   Every club in one sweep must be scored with the same values even if someone
   saves a change halfway through.

Values reaching SQL are coerced to a real ``float``/``int``/``bool`` by
``_coerce`` before they are ever interpolated, so a stored value cannot carry
anything but a number into a query string.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

SETTINGS_KEY = "engagement_weights"

# Group key -> (label, blurb). Order here is the order the page renders, and it
# is deliberate: what most visits are actually about comes first, the bulk of
# the weights last.
GROUPS: list[tuple[str, str, str]] = [
    ("membership", "Pipeline membership",
     "Whether a club appears on the sales pipeline at all. The highest-leverage "
     "settings on this page."),
    ("tiers", "Tier bands and thresholds",
     "Where Cold becomes Warm becomes Hot, and the score that raises a Twenty "
     "Opportunity."),
    ("overrides", "Overrides",
     "Rules that replace the ordinary calculation for a club, rather than "
     "contributing to it."),
    ("intent", "Buying-intent bonuses",
     "Flat points for a club doing something that shows intent, added on top of "
     "recency and frequency."),
    ("recency", "Recency",
     "Points for how recently the club was last seen, of any kind. A smooth "
     "exponential decay, not day buckets."),
    ("frequency", "Frequency scaling",
     "How reach (distinct visitors) and depth (age-decayed events) convert into "
     "points."),
    ("web", "Web activity decay",
     "Points per ordinary page view or API call, by how old it is. Beyond the "
     "last tier an event scores nothing."),
    ("ad", "Paid ad-click decay",
     "The richer curve for a Meta or paid ad landing, which is higher intent "
     "than an organic page view."),
    ("email", "Email activity decay",
     "Points per email open or click, by age. A click outweighs an open, which "
     "Apple Mail Privacy Protection can fire without anyone reading."),
    ("customer", "Customer account health",
     "A paying club is scored on account health and expansion instead of lead "
     "heat. None of the prospect settings above apply to it."),
    ("trial_depth", "Trial setup depth",
     "How far a self-serve or onboarded prospect has gone in setting "
     "BetterCricket up. Acts as a floor under the ordinary score."),
    ("counting", "What counts as activity",
     "Which recorded events feed the calculation at all."),
]

# key -> spec. ``kind`` drives both validation and how the page renders the
# input: points / multiplier / days / threshold / bool.
PARAMS: dict[str, dict[str, Any]] = {}


def _p(key, group, label, help, default, kind="points", min=0.0, max=1000.0):
    PARAMS[key] = {"key": key, "group": group, "label": label, "help": help,
                   "default": default, "kind": kind, "min": min, "max": max}


# ─── Pipeline membership ─────────────────────────────────────────────────────
# crm.sync_pipeline_membership used to hardcode "score > 0" to add a club and
# "score == 0" to archive it. Expressed as two thresholds, both defaulting to 1,
# which is byte-for-byte that behaviour (>= 1 is > 0; < 1 is == 0).
#
# They are TWO numbers rather than one on purpose. At zero the boundary is
# naturally sticky, because a zero score means no attributed activity at all.
# Anywhere mid-range it is not, and a club drifting across it repeatedly does not
# just flap a log line: re-entry creates a NEW deal row, because the "already has
# a deal" guard excludes archived deals. The gap between these two is the
# deadband that stops that.
_p("PIPELINE_ADD_MIN", "membership", "Add to the pipeline at",
   "A club scoring at least this is auto-added to the pipeline as a Target deal. "
   "Raise it to keep incidental traffic off the board: at the default of 1, a "
   "single anonymous page view or one auto-fired email open is enough to create "
   "a card.",
   1, kind="threshold", min=0, max=100)
_p("PIPELINE_REMOVE_BELOW", "membership", "Remove from the pipeline below",
   "An auto-added deal still sitting at Target is archived off the board when "
   "its club drops below this. Keep it below the add threshold so a club near "
   "the boundary is not repeatedly added and removed. Never touches a "
   "hand-added deal, a hand-moved one, or anything past Target.",
   1, kind="threshold", min=0, max=100)

# ─── Tier bands ──────────────────────────────────────────────────────────────
_p("TIER_WARM_MIN", "tiers", "Warm starts at",
   "Below this a club reads Cold.", 30, kind="threshold", min=0, max=100)
_p("TIER_HOT_MIN", "tiers", "Hot starts at",
   "At or above this a club reads Hot.", 60, kind="threshold", min=0, max=100)
_p("OPPORTUNITY_AUTO_THRESHOLD", "tiers", "Raise a Twenty Opportunity at",
   "A Lead scoring at least this has a real Opportunity created for it in "
   "Twenty automatically. Lowering it can mass-create Opportunities on the next "
   "Twenty refresh, so check the preview first.",
   90, kind="threshold", min=0, max=100)

# ─── Overrides ───────────────────────────────────────────────────────────────
_p("DIRECT_ENQUIRY_SCORE", "overrides", "Score for a recent direct enquiry",
   "A club that submitted the public Contact-Us or \"onboard my club\" form is "
   "held at this score for the window set in General Settings. The window "
   "itself is edited there, not here.",
   80, kind="threshold", min=0, max=100)
_p("ENQUIRY_OVERRIDE_IS_FLOOR", "overrides", "Treat the enquiry score as a floor",
   "OFF (the original behaviour) assigns the score above outright, so a club "
   "that was already scoring higher is pushed DOWN when it gets in touch: a busy "
   "prospect on 100 drops to 80 by filling in the contact form. ON raises a club "
   "to that score without ever lowering one, which is what the rule was "
   "described as doing. Recommended ON.",
   False, kind="bool")

# ─── Buying-intent bonuses ───────────────────────────────────────────────────
_p("BONUS_REQUESTED_TRIAL", "intent", "Requested a trial",
   "A trial has been asked for but not yet started.", 12)
_p("BONUS_IN_TRIAL", "intent", "Currently in a trial", "", 10)
_p("BONUS_ONBOARDING", "intent", "Asked to be onboarded",
   "Submitted the public Contact-Us or quick enquiry form.", 20)
_p("BONUS_CONTACT_PAGE", "intent", "Visited the contact page",
   "A real \"get in touch\" signal rather than plain browsing.", 10)
_p("BONUS_VISIT_TRIAL", "intent", "Visited the trial signup page",
   "The strongest pre-enquiry buying signal: someone actively looking to start.",
   20)
_p("BONUS_AD_SIGNUP", "intent", "Registered from a paid ad",
   "The club's account was created from a Meta or paid click.", 10)

# ─── Recency ─────────────────────────────────────────────────────────────────
_p("RECENCY_FULL", "recency", "Points for a touch today",
   "Awarded in full for activity right now and halving with age. This is a flat "
   "amount regardless of how MUCH activity there was, so it is most of what a "
   "club with a single stale page view scores.",
   10.0, kind="points", min=0, max=100)
_p("RECENCY_HALFLIFE_DAYS", "recency", "Halves every (days)",
   "A touch this many days old is worth half the amount above; twice that, a "
   "quarter.", 21.0, kind="days", min=1, max=365)

# ─── Frequency scaling ───────────────────────────────────────────────────────
_p("REACH_PER_VISITOR", "frequency", "Points per distinct visitor (30 days)",
   "Reach. Visitors are deduped by IP first and only then by browser id, since a "
   "privacy browser or an automated fetch gets a fresh browser id per request.",
   2.5, kind="points", min=0, max=100)
_p("DEPTH_SCALE", "frequency", "Multiplier on decayed event points",
   "Depth. Applied to the sum of the web, ad and email decay points below.",
   0.6, kind="multiplier", min=0, max=100)
_p("DEPTH_PER_VISITOR_CAP", "frequency", "Cap depth points per club (0 = no cap)",
   "Bounds how much the depth half can contribute, so one source of repeated "
   "requests (an open tab sending heartbeats, or a mail-security scanner "
   "prefetching every link in an email) cannot run the score away on its own. "
   "0 keeps the original uncapped behaviour.",
   0.0, kind="points", min=0, max=1000)

# ─── Decay curves ────────────────────────────────────────────────────────────
_DECAY_TIERS = [("D7", "0 to 7 days old", 7), ("D14", "7 to 14 days", 14),
                ("D21", "14 to 21 days", 21), ("D28", "21 to 28 days", 28),
                ("D90", "28 to 90 days", 90)]
_DECAY_DEFAULTS = {
    "WEB_DECAY": ("web", "Page view or API call", [2.0, 1.5, 1.0, 0.5, 0.25]),
    "AD_DECAY": ("ad", "Paid ad landing", [5.0, 3.5, 2.0, 1.0, 0.5]),
    "EMAIL_CLICK_DECAY": ("email", "Email click", [10.0, 7.5, 5.0, 2.0, 1.0]),
    "EMAIL_OPEN_DECAY": ("email", "Email open", [4.0, 3.0, 2.0, 1.0, 1.0]),
}
for _base, (_group, _what, _vals) in _DECAY_DEFAULTS.items():
    for (_suffix, _age, _), _val in zip(_DECAY_TIERS, _vals):
        _p(f"{_base}_{_suffix}", _group, f"{_what}, {_age}",
           "Anything older than the last tier scores nothing, which is what "
           "gives every club's history a 90-day outer window."
           if _suffix == "D90" else "",
           _val, kind="points", min=0, max=100)

# ─── Customer account health ─────────────────────────────────────────────────
_p("CUSTOMER_BASE", "customer", "Base score for a paying club",
   "A paying club starts here and is never Cold. Note this sits at or above the "
   "Hot threshold by default, so every customer outranks every prospect below "
   "it on the same board.",
   60, kind="threshold", min=0, max=100)
_p("CUSTOMER_UPSELL_BONUS", "customer", "Has an open upsell", "", 15)
_p("CUSTOMER_ONBOARDING_BONUS", "customer", "Asked to onboard something else", "", 10)
_p("CUSTOMER_RECENCY_SCALE", "customer", "Multiplier on recency points",
   "", 0.5, kind="multiplier", min=0, max=10)
_p("CUSTOMER_FREQ_SCALE", "customer", "Multiplier on frequency points",
   "", 0.5, kind="multiplier", min=0, max=10)
_p("CUSTOMER_FREQ_CAP", "customer", "Most frequency points a customer can earn",
   "", 20, kind="points", min=0, max=100)

# ─── Trial setup depth ───────────────────────────────────────────────────────
_p("REGISTRATION_CLUB_ADMIN", "trial_depth", "The club registered itself",
   "", 70, kind="points", min=0, max=100)
_p("REGISTRATION_SUPER_ADMIN", "trial_depth", "BetterCricket staff registered it",
   "Deliberately lower: staff setting a club up is a weaker signal of the club's "
   "own interest than the club doing it.",
   40, kind="points", min=0, max=100)
_p("SUPER_ADMIN_ACTOR_FRACTION", "trial_depth", "Credit for a staff-performed step",
   "The fraction of the points below awarded when BetterCricket staff did the "
   "work on the club's behalf rather than the club doing it.",
   0.3, kind="multiplier", min=0, max=1)
_p("MERGE_BONUS", "trial_depth", "Merged players or grades", "", 10)
_p("IMPORT_STATS_BONUS", "trial_depth", "Imported historical stats", "", 15)
_p("MODULE_GROUP_BONUS", "trial_depth", "Per paid module actually set up", "", 2)
_p("MODULE_GROUP_CAP", "trial_depth", "Most points from module setup", "", 15)
_p("ADMIN_POLISH_BONUS", "trial_depth", "Branding, sponsors or invited an admin",
   "", 2)

# ─── What counts ─────────────────────────────────────────────────────────────
_p("COUNT_ONLY_PAGE_VIEWS", "counting", "Count page views only",
   "OFF (the original behaviour) counts every recorded event towards the depth "
   "half: page views, the dwell-time event fired when each one ends, server-side "
   "API calls, AND the heartbeat the site sends every 25 seconds while a page is "
   "open. One forgotten open tab therefore scores about 29 points in ten minutes "
   "and maxes the score in an hour. ON counts page views only. Recommended ON.",
   False, kind="bool")

DEFAULTS: dict[str, Any] = {k: v["default"] for k, v in PARAMS.items()}


def _coerce(key: str, value: Any) -> Any:
    """Validate and coerce one value to a real number/bool, or raise ValueError.
    Everything that reaches SQL passes through here first, so a stored value can
    never carry anything but a number into an interpolated query."""
    spec = PARAMS.get(key)
    if spec is None:
        raise ValueError(f"Unknown engagement parameter: {key}")
    if spec["kind"] == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"{spec['label']} must be true or false")
        return value
    try:
        num = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{spec['label']} must be a number")
    if num != num or num in (float("inf"), float("-inf")):
        raise ValueError(f"{spec['label']} must be a real number")
    if num < spec["min"] or num > spec["max"]:
        raise ValueError(
            f"{spec['label']} must be between {spec['min']:g} and {spec['max']:g}")
    # threshold/days are whole numbers; points/multipliers keep one decimal.
    return int(round(num)) if spec["kind"] in ("threshold", "days") else float(num)


# In-process cache. Single-uvicorn deploy, the same assumption the rate limiter
# and crm._LAST_SCORE_RECOMPUTE already make. The TTL is the backstop; a save
# invalidates explicitly, so an edit is live immediately for the process that
# made it and within the TTL anywhere else.
_CACHE: dict[str, Any] = {"values": None, "at": 0.0}
_CACHE_TTL_S = 30.0


def invalidate_cache() -> None:
    _CACHE["values"] = None
    _CACHE["at"] = 0.0


def defaults() -> dict[str, Any]:
    """Every parameter at its code default. Safe to use where no session is in
    hand; scoring with it is exactly the pre-parameterisation behaviour."""
    return dict(DEFAULTS)


async def stored_overrides(db: AsyncSession) -> dict[str, Any]:
    """Only the keys a Super Admin has actually changed."""
    from app.services import platform_settings

    settings = await platform_settings.get_settings(db)
    raw = settings.get(SETTINGS_KEY)
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for key, value in raw.items():
        try:
            out[key] = _coerce(key, value)
        except ValueError:
            # A stored value that no longer validates (a renamed key, a range
            # that has since tightened) falls back to the default rather than
            # taking scoring down with it.
            logger.warning("engagement_params: dropping unusable stored value %s=%r",
                           key, value)
    return out


async def get_params(db: AsyncSession, *, use_cache: bool = True) -> dict[str, Any]:
    """Code defaults with the stored overrides applied. Resolve this ONCE per
    call chain and pass the result down; never call it per club in a sweep."""
    if use_cache:
        cached = _CACHE["values"]
        if cached is not None and (time.monotonic() - _CACHE["at"]) < _CACHE_TTL_S:
            return dict(cached)
    values = dict(DEFAULTS)
    values.update(await stored_overrides(db))
    _CACHE["values"] = dict(values)
    _CACHE["at"] = time.monotonic()
    return values


async def update_params(db: AsyncSession, patch: dict, *, actor_user_id=None,
                        note: Optional[str] = None) -> dict[str, Any]:
    """Apply a partial change. A key set to its own default, or explicitly to
    None, is REMOVED from the override set rather than stored, so it keeps
    tracking the code default. Records a revision snapshot. Commits."""
    from app.services import platform_settings

    overrides = await stored_overrides(db)
    for key, value in (patch or {}).items():
        if key not in PARAMS:
            raise ValueError(f"Unknown engagement parameter: {key}")
        if value is None:
            overrides.pop(key, None)
            continue
        coerced = _coerce(key, value)
        if coerced == DEFAULTS[key]:
            overrides.pop(key, None)
        else:
            overrides[key] = coerced

    settings = await platform_settings.get_settings(db)
    merged = dict(settings)
    if overrides:
        merged[SETTINGS_KEY] = overrides
    else:
        merged.pop(SETTINGS_KEY, None)
    await db.execute(
        text("UPDATE platform_settings SET settings = CAST(:s AS jsonb), "
             "updated_at = NOW() WHERE id = 1"),
        {"s": json.dumps(merged)},
    )

    resolved = dict(DEFAULTS)
    resolved.update(overrides)
    await db.execute(
        text("INSERT INTO engagement_parameter_revisions "
             "(values_json, overrides_json, changed_by_user_id, note) "
             "VALUES (CAST(:v AS jsonb), CAST(:o AS jsonb), :u, :n)"),
        {"v": json.dumps(resolved), "o": json.dumps(overrides),
         "u": str(actor_user_id) if actor_user_id else None,
         "n": (note or None)},
    )
    await db.commit()
    invalidate_cache()
    return resolved


async def list_revisions(db: AsyncSession, limit: int = 25) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT r.id, r.values_json, r.overrides_json, r.changed_by_user_id,
               r.note, r.created_at, r.recalc_summary,
               COALESCE(u.display_name, u.username) AS changed_by
        FROM engagement_parameter_revisions r
        LEFT JOIN users u ON u.id = r.changed_by_user_id
        ORDER BY r.created_at DESC
        LIMIT :lim
    """), {"lim": max(1, min(int(limit or 25), 200))})).mappings().all()
    return [dict(r) for r in rows]


async def record_recalc_summary(db: AsyncSession, revision_id, summary: dict) -> None:
    """Stamp what a parameter change actually did to the platform onto the
    revision that caused it, so "who changed this and what happened" is one
    lookup. Best effort; never raises into the caller's flow."""
    try:
        await db.execute(
            text("UPDATE engagement_parameter_revisions "
                 "SET recalc_summary = CAST(:s AS jsonb) WHERE id = :id"),
            {"s": json.dumps(summary or {}), "id": str(revision_id)},
        )
        await db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("engagement_params: could not record recalc summary")


def catalogue() -> list[dict]:
    """The catalogue as the page renders it: groups in order, each carrying its
    parameters in definition order. Served from the API rather than mirrored by
    hand in JS — there are too many entries with real explanatory copy for a
    hand-kept mirror not to drift."""
    by_group: dict[str, list] = {}
    for spec in PARAMS.values():
        by_group.setdefault(spec["group"], []).append(dict(spec))
    return [{"key": key, "label": label, "blurb": blurb,
             "params": by_group.get(key, [])}
            for key, label, blurb in GROUPS]
