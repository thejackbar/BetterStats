"""Global platform settings (migration 120).

A single JSONB row a super admin manages from the All Clubs page. Kept deliberately
small and generic so new platform-wide settings slot in without a migration. First
field: ``default_trial_days`` — the trial length used when a module trial is created.
"""
from __future__ import annotations

import json
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.modules import DEFAULT_TRIAL_DAYS
from app.config.settings import settings as app_settings

logger = logging.getLogger(__name__)

# The whitelist of keys the General Settings UI can set, with validators. Add to this
# as new settings are introduced.
_INT_KEYS = {"default_trial_days"}

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
        # Unknown keys are ignored (forward-compatible).
    await db.execute(
        text("UPDATE platform_settings SET settings = CAST(:s AS jsonb), updated_at = NOW() WHERE id = 1"),
        {"s": json.dumps(out)},
    )
    await db.commit()
    return out


# ─── SES send rates ──────────────────────────────────────────────────────────

def _as_int(value, fallback: int) -> int:
    try:
        v = int(value)
        return v if v > 0 else fallback
    except (TypeError, ValueError):
        return fallback


async def get_ses_rates(db: AsyncSession) -> dict:
    """The live AWS ceiling + our send rate, falling back to the env seed
    defaults when unset. Refreshes the in-memory send-rate cache as a side
    effect (so a GET after startup warms it)."""
    s = await get_settings(db)
    aws = _as_int(s.get("ses_aws_max_send_rate"), default_aws_rate())
    send = _as_int(s.get("ses_send_rate"), default_send_rate())
    global _send_rate_cache
    _send_rate_cache = send
    return {
        "aws_max_send_rate": aws,
        "send_rate": send,
        # Surfaced so the UI can show what the defaults are if never set.
        "default_aws_max_send_rate": default_aws_rate(),
        "default_send_rate": default_send_rate(),
    }


async def update_ses_rates(db: AsyncSession, *, aws_max_send_rate=None, send_rate=None) -> dict:
    """Set either or both SES rates. Enforces the invariant that our send rate is
    ALWAYS strictly below the AWS ceiling (the resulting combined state is what's
    validated, so a lone change to either can't break the rule). Commits and
    refreshes the cache. Raises ValueError on a bad request."""
    current = await get_ses_rates(db)
    new_aws = current["aws_max_send_rate"] if aws_max_send_rate is None else _pos_int(aws_max_send_rate, "aws_max_send_rate")
    new_send = current["send_rate"] if send_rate is None else _pos_int(send_rate, "send_rate")
    if new_send >= new_aws:
        raise ValueError(
            f"The send rate ({new_send}/s) must be lower than the AWS limit ({new_aws}/s).")
    patch = {"ses_aws_max_send_rate": new_aws, "ses_send_rate": new_send}
    s = await get_settings(db)
    out = dict(s)
    out.update(patch)
    await db.execute(
        text("UPDATE platform_settings SET settings = CAST(:s AS jsonb), updated_at = NOW() WHERE id = 1"),
        {"s": json.dumps(out)},
    )
    await db.commit()
    global _send_rate_cache
    _send_rate_cache = new_send
    return {"aws_max_send_rate": new_aws, "send_rate": new_send}


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
