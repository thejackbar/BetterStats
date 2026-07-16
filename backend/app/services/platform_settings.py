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
_INT_KEYS = {"default_trial_days", "direct_enquiry_hot_days"}

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
    "billing_checkout_enabled",
}

# How long a direct "onboard my club" website enquiry (Contact page or the quick
# CTA modal) holds a prospect at a flat Hot 100 Twenty engagement score before it
# decays back to the ordinary recency/frequency formula — see
# twenty_sync._engagement. A plain in-repo default (not an env var): this is a
# commercial/marketing parameter a super admin tunes from General Settings, not
# server configuration.
DEFAULT_DIRECT_ENQUIRY_HOT_DAYS = 30

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
