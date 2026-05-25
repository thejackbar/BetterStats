"""Audit-log helper.

Append-only record of sensitive admin actions (merges, undo merges,
settings changes, destructive ops). Read via /club-admin/activity-log
in the admin UI; not user-editable from anywhere — only INSERTs.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def log_activity(
    session: AsyncSession,
    *,
    org_id,
    user_id=None,
    action: str,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    details: Optional[dict] = None,
    commit: bool = False,
) -> None:
    """Record one entry. Caller should already have an open session.

    Set commit=True only when the audit row needs to be persisted
    independently of the caller's transaction (rare — usually you want it
    to roll back with the action if the action fails).

    Never raises — audit-log failures should never block the actual
    business operation, just log a warning.
    """
    try:
        await session.execute(
            text(
                "INSERT INTO audit_logs (org_id, user_id, action, target_type, target_id, details) "
                "VALUES (:org, :uid, :action, :ttype, :tid, CAST(:details AS JSONB))"
            ),
            {
                "org": str(org_id),
                "uid": str(user_id) if user_id else None,
                "action": action,
                "ttype": target_type,
                "tid": str(target_id) if target_id else None,
                "details": json.dumps(details or {}),
            },
        )
        if commit:
            await session.commit()
    except Exception as e:
        logger.warning(f"audit_log: failed to record action={action} org={org_id}: {e}")
