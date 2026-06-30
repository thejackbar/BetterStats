"""Global platform settings (migration 120).

A single JSONB row a super admin manages from the All Clubs page. Kept deliberately
small and generic so new platform-wide settings slot in without a migration. First
field: ``default_trial_days`` — the trial length used when a module trial is created.
"""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.modules import DEFAULT_TRIAL_DAYS

# The whitelist of keys the General Settings UI can set, with validators. Add to this
# as new settings are introduced.
_INT_KEYS = {"default_trial_days"}


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
