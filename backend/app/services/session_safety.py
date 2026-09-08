"""Rolling back a best-effort read without stranding the request's ORM objects.

``rollback()`` EXPIRES everything the session has loaded, whatever
``expire_on_commit`` says. So a swallowed failure leaves the instances the
request's own dependencies loaded — ``club`` from ``get_current_club``,
``current_user`` from ``get_current_user`` — expired, and the next plain
attribute read on one of them is a lazy refresh. A lazy refresh inside an async
request raises ``greenlet_spawn has not been called``, which is then what the
caller reports instead of the read that actually failed. That exact confusion
cost a day on the scorecard endpoint (see the v9.53.5.1 note).

Lifted out of ``routers/admin.py``, which now delegates, so there is ONE
definition of the rule rather than a copy per router waiting to drift.
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def rollback_keeping(db: AsyncSession, *instances) -> None:
    """Roll back, then hand back objects the rest of the request can read."""
    await db.rollback()
    for inst in instances:
        if inst is None:
            continue
        try:
            await db.refresh(inst)
        except Exception:
            logger.exception("post-rollback refresh failed for %r", type(inst).__name__)
