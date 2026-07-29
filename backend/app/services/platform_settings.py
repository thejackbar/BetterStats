"""Global platform settings (migration 120).

A single JSONB row a super admin manages from the All Clubs page. Kept deliberately
small and generic so new platform-wide settings slot in without a migration. First
field: ``default_trial_days`` — the trial length used when a module trial is created.
"""
from __future__ import annotations

import json
import logging

from fastapi import Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.modules import DEFAULT_TRIAL_DAYS
from app.config.settings import settings as app_settings
from app.models.db import Organisation, get_db
from app.routers.auth import get_current_club

logger = logging.getLogger(__name__)

# The whitelist of keys the General Settings UI can set, with validators. Add to this
# as new settings are introduced.
_INT_KEYS = {"default_trial_days", "direct_enquiry_hot_days",
             "crm_incremental_sweep_seconds", "crm_global_sweep_minutes"}

# Boolean feature flags, off by default until a super admin turns them on from
# General Settings. Each new self-serve-trial-onboarding surface (see
# docs/self-serve-trial-onboarding-plan.md) is built behind one of these so it stays
# inert in production until explicitly enabled — there is no staging environment, so
# this is the only safety net between "merged" and "live".
#
# billing_checkout_enabled gates the in-progress invoicing / Stripe checkout build
# (Account page SUBSCRIBE flow): off keeps a Primary Admin on the existing "not
# connected yet" stub notice no matter how much of the real flow has been merged,
# so half-built billing code can land on main without ever being reachable by a
# real club until a super admin deliberately switches it on for testing/launch.
_BOOL_KEYS = {
    "self_serve_registration_enabled", "onboarding_wizard_enabled", "trial_nudges_enabled",
    "billing_checkout_enabled", "member_portal_enabled", "merch_storefront_enabled",
}

# How long a direct "onboard my club" website enquiry (Contact page or the quick
# CTA modal) holds a prospect at a flat Hot 100 Twenty engagement score before it
# decays back to the ordinary recency/frequency formula — see
# twenty_sync._engagement. A plain in-repo default (not an env var): this is a
# commercial/marketing parameter a super admin tunes from General Settings, not
# server configuration.
DEFAULT_DIRECT_ENQUIRY_HOT_DAYS = 60

# CRM Sales Pipeline auto-recompute cadences, super-admin tunable from the
# pipeline's Settings modal (not General Settings). Tier 2: the frequent
# incremental sweep that re-scores only the clubs that already have a deal card
# AND had new telemetry since the last run (cheap — reuses the fast_web indexed
# path). Tier 3: the periodic full sweep over every Club Directory club (the
# recalc_engagement logic), which catches slow time-decay drift and anything the
# incremental job missed. Clamped in the getters so a bad/extreme value can't
# hammer the DB or silently disable a sweep.
DEFAULT_CRM_INCREMENTAL_SWEEP_SECONDS = 60
CRM_INCREMENTAL_SWEEP_MIN_SECONDS = 15
CRM_INCREMENTAL_SWEEP_MAX_SECONDS = 3600
DEFAULT_CRM_GLOBAL_SWEEP_MINUTES = 60
CRM_GLOBAL_SWEEP_MIN_MINUTES = 5
CRM_GLOBAL_SWEEP_MAX_MINUTES = 1440

# ─── SES send-rate settings (super-admin managed, migration 120 blob) ─────────
# Two live values a super admin controls from the BetterComms limits page:
#   ses_aws_max_send_rate — AWS's granted per-second ceiling (14 today), bumped
#                           when AWS raises the account's rate.
#   ses_send_rate         — our own pacing rate, ALWAYS kept strictly below the
#                           AWS ceiling so normal jitter never brushes it.
# The env values (settings.ses_aws_max_send_rate / ses_max_send_rate) are the
# seed defaults used until a super admin sets them. The send loop reads the send
# rate through a warm in-memory cache (cached_send_rate) so the hot path never
# touches the DB.
_send_rate_cache: "int | None" = None


def default_aws_rate() -> int:
    try:
        return int(getattr(app_settings, "ses_aws_max_send_rate", 14)) or 14
    except (TypeError, ValueError):
        return 14


def default_send_rate() -> int:
    try:
        return int(getattr(app_settings, "ses_max_send_rate", 13)) or 13
    except (TypeError, ValueError):
        return 13


def default_aws_daily_quota() -> int:
    try:
        return int(getattr(app_settings, "ses_daily_quota", 50000)) or 50000
    except (TypeError, ValueError):
        return 50000


def default_daily_send_limit() -> int:
    try:
        return int(getattr(app_settings, "ses_daily_send_limit", 45000)) or 45000
    except (TypeError, ValueError):
        return 45000


def default_sandbox_daily() -> int:
    try:
        return int(getattr(app_settings, "comms_sandbox_daily_cap", 50)) or 50
    except (TypeError, ValueError):
        return 50


def default_production_daily() -> int:
    try:
        return int(getattr(app_settings, "comms_production_daily_cap", 2000)) or 2000
    except (TypeError, ValueError):
        return 2000


def default_monthly() -> int:
    try:
        return int(getattr(app_settings, "comms_monthly_send_default", 10000)) or 10000
    except (TypeError, ValueError):
        return 10000


async def get_comms_tier_defaults(db: AsyncSession) -> dict:
    """The super-admin-managed per-club tier defaults (sandbox daily, production
    daily, monthly), falling back to the env seed defaults when unset. These are
    the defaults a club uses when it has no per-club override."""
    s = await get_settings(db)
    return {
        "sandbox_daily": _as_int(s.get("comms_sandbox_daily"), default_sandbox_daily()),
        "production_daily": _as_int(s.get("comms_production_daily"), default_production_daily()),
        "monthly": _as_int(s.get("comms_monthly_default"), default_monthly()),
        "default_sandbox_daily": default_sandbox_daily(),
        "default_production_daily": default_production_daily(),
        "default_monthly": default_monthly(),
    }


async def update_comms_tier_defaults(db: AsyncSession, *, sandbox_daily=None,
                                     production_daily=None, monthly=None) -> dict:
    """Set any of the per-club tier defaults. Each is a positive whole number.
    Commits. Returns the resulting defaults."""
    s = await get_settings(db)
    out = dict(s)
    if sandbox_daily is not None:
        out["comms_sandbox_daily"] = _pos_int(sandbox_daily, "sandbox_daily")
    if production_daily is not None:
        out["comms_production_daily"] = _pos_int(production_daily, "production_daily")
    if monthly is not None:
        out["comms_monthly_default"] = _pos_int(monthly, "monthly")
    await db.execute(
        text("UPDATE platform_settings SET settings = CAST(:s AS jsonb), updated_at = NOW() WHERE id = 1"),
        {"s": json.dumps(out)},
    )
    await db.commit()
    return await get_comms_tier_defaults(db)


async def get_settings(db: AsyncSession) -> dict:
    """The platform settings blob (ensures the singleton row exists)."""
    row = (await db.execute(
        text("SELECT settings FROM platform_settings WHERE id = 1")
    )).first()
    if row is None:
        await db.execute(text(
            "INSERT INTO platform_settings (id, settings) VALUES (1, '{}') ON CONFLICT (id) DO NOTHING"
        ))
        await db.commit()
        return {}
    return dict(row[0] or {})


async def get_default_trial_days(db: AsyncSession) -> int:
    """The configured default trial length, or 14 when unset/invalid."""
    settings = await get_settings(db)
    try:
        days = int(settings.get("default_trial_days"))
        return days if days > 0 else DEFAULT_TRIAL_DAYS
    except (TypeError, ValueError):
        return DEFAULT_TRIAL_DAYS


async def get_direct_enquiry_hot_days(db: AsyncSession) -> int:
    """How many days a direct onboarding enquiry holds a prospect at Hot 100 in
    Twenty, or DEFAULT_DIRECT_ENQUIRY_HOT_DAYS when unset/invalid."""
    settings = await get_settings(db)
    try:
        days = int(settings.get("direct_enquiry_hot_days"))
        return days if days > 0 else DEFAULT_DIRECT_ENQUIRY_HOT_DAYS
    except (TypeError, ValueError):
        return DEFAULT_DIRECT_ENQUIRY_HOT_DAYS


async def get_crm_incremental_sweep_seconds(db: AsyncSession) -> int:
    """Tier 2 cadence: how often (seconds) the incremental pipeline-card sweep
    runs, clamped to [MIN, MAX], falling back to the default when unset/invalid."""
    settings = await get_settings(db)
    try:
        v = int(settings.get("crm_incremental_sweep_seconds"))
    except (TypeError, ValueError):
        return DEFAULT_CRM_INCREMENTAL_SWEEP_SECONDS
    return max(CRM_INCREMENTAL_SWEEP_MIN_SECONDS, min(CRM_INCREMENTAL_SWEEP_MAX_SECONDS, v))


async def get_crm_global_sweep_minutes(db: AsyncSession) -> int:
    """Tier 3 cadence: how often (minutes) the full Club-Directory engagement
    sweep runs, clamped to [MIN, MAX], falling back to the default when
    unset/invalid."""
    settings = await get_settings(db)
    try:
        v = int(settings.get("crm_global_sweep_minutes"))
    except (TypeError, ValueError):
        return DEFAULT_CRM_GLOBAL_SWEEP_MINUTES
    return max(CRM_GLOBAL_SWEEP_MIN_MINUTES, min(CRM_GLOBAL_SWEEP_MAX_MINUTES, v))


async def get_active_meta_campaign_id(db: AsyncSession) -> str:
    """The super-admin-selected active Meta campaign id for the Meta Ads HQ
    dashboard, falling back to the env seed default (settings.meta_campaign_id)
    when unset — so switching which campaign the dashboard tracks is a dropdown
    in the UI, not a .env edit plus a redeploy."""
    settings = await get_settings(db)
    cid = str(settings.get("meta_campaign_id") or "").strip()
    return cid or app_settings.meta_campaign_id


async def set_active_meta_campaign_id(db: AsyncSession, campaign_id: str) -> str:
    """Set the active Meta campaign id (a numeric Meta campaign id). Commits.
    Returns the stored id. Raises ValueError on a malformed id."""
    cid = str(campaign_id or "").strip()
    if not cid.isdigit():
        raise ValueError("campaign_id must be a numeric Meta campaign id")
    current = await get_settings(db)
    out = dict(current)
    out["meta_campaign_id"] = cid
    await db.execute(
        text("UPDATE platform_settings SET settings = CAST(:s AS jsonb), updated_at = NOW() WHERE id = 1"),
        {"s": json.dumps(out)},
    )
    await db.commit()
    return cid


_HIDDEN_META_SELECTIONS_KEY = "meta_ads_hidden_selections"


def _selection_key(name: str) -> str:
    """The normalised club-name key the Meta Ads wizard-selection table groups
    by (meta_ads.get_selected_clubs uses the same ``strip().lower()``), so a
    hidden entry lines up with the row it hides."""
    return (name or "").strip().lower()


async def get_hidden_meta_selections(db: AsyncSession) -> set[str]:
    """The set of normalised club-name keys a super admin has flagged as test
    noise on the Meta Ads dashboard, so the wizard-selection table can filter
    them out. Table-only tidy-up — never touches the Sales Pipeline."""
    settings = await get_settings(db)
    raw = settings.get(_HIDDEN_META_SELECTIONS_KEY) or []
    if not isinstance(raw, list):
        return set()
    return {_selection_key(x) for x in raw if isinstance(x, str) and _selection_key(x)}


async def _write_hidden_meta_selections(db: AsyncSession, keys: set[str]) -> list[str]:
    current = await get_settings(db)
    out = dict(current)
    out[_HIDDEN_META_SELECTIONS_KEY] = sorted(keys)
    await db.execute(
        text("UPDATE platform_settings SET settings = CAST(:s AS jsonb), updated_at = NOW() WHERE id = 1"),
        {"s": json.dumps(out)},
    )
    await db.commit()
    return out[_HIDDEN_META_SELECTIONS_KEY]


async def hide_meta_selection(db: AsyncSession, name: str) -> list[str]:
    """Flag a wizard-selected club as test noise (hidden from the Meta Ads
    table). Idempotent. Returns the full hidden list. Commits."""
    key = _selection_key(name)
    if not key:
        raise ValueError("name is required")
    keys = await get_hidden_meta_selections(db)
    keys.add(key)
    return await _write_hidden_meta_selections(db, keys)


async def unhide_meta_selection(db: AsyncSession, name: str) -> list[str]:
    """Un-flag a previously-hidden wizard selection. Idempotent. Returns the
    full hidden list. Commits."""
    key = _selection_key(name)
    keys = await get_hidden_meta_selections(db)
    keys.discard(key)
    return await _write_hidden_meta_selections(db, keys)


async def update_settings(db: AsyncSession, patch: dict) -> dict:
    """Merge ``patch`` into the settings blob. Validates known keys; ignores unknown
    ones. Returns the full updated blob. Commits."""
    current = await get_settings(db)
    out = dict(current)
    for key, value in (patch or {}).items():
        if key in _INT_KEYS:
            if value is None:
                out.pop(key, None)
                continue
            try:
                ival = int(value)
            except (TypeError, ValueError):
                raise ValueError(f"{key} must be a positive integer")
            if ival <= 0:
                raise ValueError(f"{key} must be a positive integer")
            out[key] = ival
        elif key in _BOOL_KEYS:
            if value is None:
                out.pop(key, None)
                continue
            if not isinstance(value, bool):
                raise ValueError(f"{key} must be true or false")
            out[key] = value
        # Unknown keys are ignored (forward-compatible).
    await db.execute(
        text("UPDATE platform_settings SET settings = CAST(:s AS jsonb), updated_at = NOW() WHERE id = 1"),
        {"s": json.dumps(out)},
    )
    await db.commit()
    return out


async def get_feature_flag(db: AsyncSession, key: str) -> bool:
    """A boolean feature flag from the settings blob, off (False) when unset. Only
    keys in ``_BOOL_KEYS`` are meaningful here."""
    settings = await get_settings(db)
    return bool(settings.get(key) is True)


async def get_self_serve_registration_enabled(db: AsyncSession) -> bool:
    """Whether the internal self-serve club trial registration flow (Super
    Admin-only in this phase — see docs/self-serve-trial-onboarding-plan.md) is
    switched on. Off by default."""
    return await get_feature_flag(db, "self_serve_registration_enabled")


async def get_onboarding_wizard_enabled(db: AsyncSession) -> bool:
    """Whether the club onboarding wizard is switched on. Off by default."""
    return await get_feature_flag(db, "onboarding_wizard_enabled")


async def get_trial_nudges_enabled(db: AsyncSession) -> bool:
    """Whether the daily trial-lifecycle nudge scan (Phase 16) sends real
    outbound email. Off by default — see app/services/trial_lifecycle.py."""
    return await get_feature_flag(db, "trial_nudges_enabled")


async def get_billing_checkout_enabled(db: AsyncSession) -> bool:
    """The PLATFORM DEFAULT for whether a Primary Admin can proceed past the
    Account page's SUBSCRIBE button into the real invoicing / Stripe checkout
    flow. Off by default. A club can override this individually — see
    billing_checkout_enabled_for_org, which is what routes should actually
    check; this raw platform default is mainly for the General Settings page
    itself and as the fallback that function reads."""
    return await get_feature_flag(db, "billing_checkout_enabled")


async def billing_checkout_enabled_for_org(db: AsyncSession, org: Organisation) -> bool:
    """The EFFECTIVE billing-checkout switch for one club: its own
    ``organisations.billing_checkout_override`` wins when set (True forces it
    on for this club even while the platform default is off — e.g. a super
    admin testing the real Stripe flow against one club before going live;
    False forces it off even once the platform default is on), else falls
    back to the platform default (get_billing_checkout_enabled)."""
    override = getattr(org, "billing_checkout_override", None)
    if override is not None:
        return bool(override)
    return await get_billing_checkout_enabled(db)


async def require_billing_checkout_enabled(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
) -> None:
    """FastAPI dependency: 403s a route while billing/checkout is switched off
    for the CALLER'S CLUB specifically (platform default, unless that club has
    its own override — see billing_checkout_enabled_for_org). Add
    ``Depends(require_billing_checkout_enabled)`` to every invoicing /
    Stripe-checkout route as it's built — the frontend gate on the Account
    page is UX only, this is the real block, so a direct API call (or a
    half-wired frontend) can't reach real payment processing before it's
    switched on for that club."""
    if not await billing_checkout_enabled_for_org(db, club):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Online billing isn't switched on for your club yet. Contact the BetterCricket team to subscribe.",
        )


async def get_member_portal_enabled(db: AsyncSession) -> bool:
    """The PLATFORM DEFAULT for whether the member self-service portal
    (login, fee view, qualifications, online fee payment via Stripe Connect)
    is reachable at all. Off by default — per direct instruction this whole
    feature stays invisible to every club admin, and unusable by any real
    member, until deliberately switched on. A club can override this
    individually — see member_portal_enabled_for_org, which is what routes
    and the admin nav should actually check."""
    return await get_feature_flag(db, "member_portal_enabled")


async def member_portal_enabled_for_org(db: AsyncSession, org: Organisation) -> bool:
    """The EFFECTIVE member-portal switch for one club — mirrors
    billing_checkout_enabled_for_org exactly. ``organisations.
    member_portal_override`` wins when set (True lets a super admin switch
    the portal on for ONE test club while the platform default stays off for
    everyone else; False forces it off even once the platform default is
    on), else falls back to the platform default."""
    override = getattr(org, "member_portal_override", None)
    if override is not None:
        return bool(override)
    return await get_member_portal_enabled(db)


async def require_member_portal_enabled(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
) -> None:
    """FastAPI dependency: 404s an authenticated club-admin route while the
    member portal is switched off for the caller's club — a 404 (not 403)
    since, per direct instruction, the whole feature should read as if it
    doesn't exist yet to an ordinary club admin, the same "doesn't exist"
    convention used by require_self_serve_registration_enabled."""
    if not await member_portal_enabled_for_org(db, club):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


async def get_merch_storefront_enabled(db: AsyncSession) -> bool:
    """The PLATFORM DEFAULT for whether the public merch storefront
    (browsing + online checkout against a club's BetterMerch catalogue) is
    reachable at all. Off by default — same "invisible until switched on"
    posture as the member portal. See merch_storefront_enabled_for_org."""
    return await get_feature_flag(db, "merch_storefront_enabled")


async def merch_storefront_enabled_for_org(db: AsyncSession, org: Organisation) -> bool:
    """The EFFECTIVE merch-storefront switch for one club — mirrors
    member_portal_enabled_for_org exactly. ``organisations.
    merch_storefront_override`` wins when set, else falls back to the
    platform default."""
    override = getattr(org, "merch_storefront_override", None)
    if override is not None:
        return bool(override)
    return await get_merch_storefront_enabled(db)


async def require_merch_storefront_enabled(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
) -> None:
    """FastAPI dependency: 404s an authenticated club-admin route while the
    merch storefront is switched off for the caller's club — same "doesn't
    exist" convention as require_member_portal_enabled."""
    if not await merch_storefront_enabled_for_org(db, club):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


# ─── Bundle discount schedule (module-count -> whole-dollar discount) ─────────
# Was a hardcoded constant (billing_pricing.BUNDLE_DISCOUNT); moved here per
# direct instruction so a super admin can change or extend it without a code
# deploy. That constant is now only the SEED DEFAULT, used until a super admin
# saves their own schedule from General Settings.

async def get_bundle_discount_schedule(db: AsyncSession) -> dict[int, int]:
    """The live bundle-discount table, module-count -> whole-dollar discount.
    Falls back to billing_pricing.BUNDLE_DISCOUNT (the seed default) when
    unset or malformed — imported lazily to dodge a services-importing-
    services cycle at module load time."""
    from app.services.billing_pricing import BUNDLE_DISCOUNT

    settings = await get_settings(db)
    raw = settings.get("bundle_discount_schedule")
    if not isinstance(raw, dict) or not raw:
        return dict(BUNDLE_DISCOUNT)
    try:
        return {int(k): int(v) for k, v in raw.items()}
    except (TypeError, ValueError):
        logger.warning("platform_settings: malformed bundle_discount_schedule, using seed default")
        return dict(BUNDLE_DISCOUNT)


async def update_bundle_discount_schedule(db: AsyncSession, schedule: dict) -> dict[int, int]:
    """Replaces the whole schedule (not a merge — the UI always sends the full
    table). Each key is a module count (>= 0), each value a non-negative
    whole-dollar discount. Commits. Raises ValueError on a bad request."""
    out: dict[str, int] = {}
    for k, v in (schedule or {}).items():
        try:
            count = int(k)
            amount = int(v)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid bundle discount entry: {k!r}={v!r}")
        if count < 0:
            raise ValueError(f"Module count must be >= 0, got {count}")
        if amount < 0:
            raise ValueError(f"Discount for {count} modules must be >= 0, got {amount}")
        out[str(count)] = amount
    s = await get_settings(db)
    merged = dict(s)
    merged["bundle_discount_schedule"] = out
    await db.execute(
        text("UPDATE platform_settings SET settings = CAST(:s AS jsonb), updated_at = NOW() WHERE id = 1"),
        {"s": json.dumps(merged)},
    )
    await db.commit()
    return await get_bundle_discount_schedule(db)


# ─── Backup schedule (daily automated backup — host systemd timer reads this) ─
# The host-level backup script has no UI of its own; it reads its schedule and
# retention window from here on every tick (see ops/backup/backup.sh) so a
# super admin can change either without touching the server. hour/minute can
# legitimately be 0, so this can't reuse the generic _INT_KEYS validator
# (which treats 0 as "unset") — same reasoning as the bundle discount schedule
# above having its own dedicated getter/setter.
#
# Stored and enforced here (and by backup.sh, which reads the host's clock) in
# UTC — the General Settings UI is what converts to/from Perth, WA time
# (AWST, UTC+8, no daylight saving) for display, since that's what a super
# admin actually thinks in. DEFAULT_BACKUP_HOUR = 19 UTC = 03:00 Perth, an
# off-peak default for a club's admin activity.

DEFAULT_BACKUP_HOUR = 19
DEFAULT_BACKUP_MINUTE = 0
DEFAULT_BACKUP_RETENTION_DAYS = 30


async def get_backup_schedule(db: AsyncSession) -> dict:
    """The configured daily backup time (24h, UTC — the General Settings UI
    converts to/from Perth, WA time for display) and retention window in
    days. Falls back to 19:00 UTC (03:00 Perth) / 30 days when unset or
    malformed."""
    settings = await get_settings(db)
    raw = settings.get("backup_schedule")
    raw = raw if isinstance(raw, dict) else {}
    try:
        hour = int(raw.get("hour", DEFAULT_BACKUP_HOUR))
        hour = hour if 0 <= hour <= 23 else DEFAULT_BACKUP_HOUR
    except (TypeError, ValueError):
        hour = DEFAULT_BACKUP_HOUR
    try:
        minute = int(raw.get("minute", DEFAULT_BACKUP_MINUTE))
        minute = minute if 0 <= minute <= 59 else DEFAULT_BACKUP_MINUTE
    except (TypeError, ValueError):
        minute = DEFAULT_BACKUP_MINUTE
    try:
        retention_days = int(raw.get("retention_days", DEFAULT_BACKUP_RETENTION_DAYS))
        retention_days = retention_days if retention_days > 0 else DEFAULT_BACKUP_RETENTION_DAYS
    except (TypeError, ValueError):
        retention_days = DEFAULT_BACKUP_RETENTION_DAYS
    return {"hour": hour, "minute": minute, "retention_days": retention_days}


async def update_backup_schedule(db: AsyncSession, *, hour=None, minute=None,
                                  retention_days=None) -> dict:
    """Set any of the backup schedule fields. Commits. Raises ValueError on a
    bad request."""
    current = await get_backup_schedule(db)
    out = dict(current)
    if hour is not None:
        try:
            h = int(hour)
        except (TypeError, ValueError):
            raise ValueError("hour must be an integer 0-23")
        if not (0 <= h <= 23):
            raise ValueError("hour must be between 0 and 23")
        out["hour"] = h
    if minute is not None:
        try:
            m = int(minute)
        except (TypeError, ValueError):
            raise ValueError("minute must be an integer 0-59")
        if not (0 <= m <= 59):
            raise ValueError("minute must be between 0 and 59")
        out["minute"] = m
    if retention_days is not None:
        out["retention_days"] = _pos_int(retention_days, "retention_days")
    s = await get_settings(db)
    merged = dict(s)
    merged["backup_schedule"] = out
    await db.execute(
        text("UPDATE platform_settings SET settings = CAST(:s AS jsonb), updated_at = NOW() WHERE id = 1"),
        {"s": json.dumps(merged)},
    )
    await db.commit()
    return await get_backup_schedule(db)


# ─── SES send rates ──────────────────────────────────────────────────────────

def _as_int(value, fallback: int) -> int:
    try:
        v = int(value)
        return v if v > 0 else fallback
    except (TypeError, ValueError):
        return fallback


async def get_ses_rates(db: AsyncSession) -> dict:
    """The live SES send limits (per-second rate + daily quota), falling back to
    the env seed defaults when unset. Refreshes the in-memory send-rate cache as a
    side effect (so a GET after startup warms it)."""
    s = await get_settings(db)
    aws = _as_int(s.get("ses_aws_max_send_rate"), default_aws_rate())
    send = _as_int(s.get("ses_send_rate"), default_send_rate())
    aws_daily = _as_int(s.get("ses_aws_daily_quota"), default_aws_daily_quota())
    daily = _as_int(s.get("ses_daily_send_limit"), default_daily_send_limit())
    global _send_rate_cache
    _send_rate_cache = send
    return {
        "aws_max_send_rate": aws,
        "send_rate": send,
        "aws_daily_quota": aws_daily,
        "daily_send_limit": daily,
        # Surfaced so the UI can show what the defaults are if never set.
        "default_aws_max_send_rate": default_aws_rate(),
        "default_send_rate": default_send_rate(),
        "default_aws_daily_quota": default_aws_daily_quota(),
        "default_daily_send_limit": default_daily_send_limit(),
    }


async def update_ses_rates(db: AsyncSession, *, aws_max_send_rate=None, send_rate=None,
                           aws_daily_quota=None, daily_send_limit=None) -> dict:
    """Set any of the SES send limits. Enforces two invariants on the resulting
    combined state (so a lone change to one field can't break a rule): our send
    rate stays STRICTLY BELOW the AWS per-second ceiling, and our daily send limit
    stays AT OR BELOW the AWS daily ceiling. Commits and refreshes the cache.
    Raises ValueError on a bad request."""
    current = await get_ses_rates(db)
    new_aws = current["aws_max_send_rate"] if aws_max_send_rate is None else _pos_int(aws_max_send_rate, "aws_max_send_rate")
    new_send = current["send_rate"] if send_rate is None else _pos_int(send_rate, "send_rate")
    new_aws_daily = current["aws_daily_quota"] if aws_daily_quota is None else _pos_int(aws_daily_quota, "aws_daily_quota")
    new_daily = current["daily_send_limit"] if daily_send_limit is None else _pos_int(daily_send_limit, "daily_send_limit")
    if new_send >= new_aws:
        raise ValueError(
            f"The send rate ({new_send}/s) must be lower than the AWS limit ({new_aws}/s).")
    if new_daily > new_aws_daily:
        raise ValueError(
            f"The daily send limit ({new_daily:,}) can't exceed the AWS daily limit ({new_aws_daily:,}).")
    s = await get_settings(db)
    out = dict(s)
    out.update({"ses_aws_max_send_rate": new_aws, "ses_send_rate": new_send,
                "ses_aws_daily_quota": new_aws_daily, "ses_daily_send_limit": new_daily})
    await db.execute(
        text("UPDATE platform_settings SET settings = CAST(:s AS jsonb), updated_at = NOW() WHERE id = 1"),
        {"s": json.dumps(out)},
    )
    await db.commit()
    global _send_rate_cache
    _send_rate_cache = new_send
    return {"aws_max_send_rate": new_aws, "send_rate": new_send,
            "aws_daily_quota": new_aws_daily, "daily_send_limit": new_daily}


async def get_daily_send_limit(db: AsyncSession) -> int:
    """Our practical daily send ceiling (super-admin managed, env seed default)."""
    s = await get_settings(db)
    return _as_int(s.get("ses_daily_send_limit"), default_daily_send_limit())


def _pos_int(value, name: str) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a positive whole number")
    if v <= 0:
        raise ValueError(f"{name} must be a positive whole number")
    return v


def cached_send_rate() -> int:
    """The current send rate for the hot send path (sync, no DB). Falls back to
    the env seed default until the cache is warmed (startup / first read)."""
    return _send_rate_cache if _send_rate_cache is not None else default_send_rate()


async def warm_send_rate_cache(db: AsyncSession) -> None:
    """Load the configured send rate into the in-memory cache at startup, so a
    DB-set rate takes effect immediately after a restart (not only once a super
    admin opens the settings page)."""
    try:
        await get_ses_rates(db)
    except Exception as e:  # never block startup on this
        logger.warning("Could not warm SES send-rate cache: %s", e)
