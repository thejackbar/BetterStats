"""Club → BetterCricket request telemetry.

Every time a club asks BetterCricket for something a human needs to action — a
BetterComms sandbox→production tier lift, a module trial/subscribe, and future
asks — it leaves one durable row (``club_request_events``), so every ask is
tracked and the CRM action queue can surface it.

``add_request_event(session, …)`` writes the row in the caller's transaction (no
commit; the caller commits alongside its own domain row).

HISTORY: this also raised a task in the Twenty CRM, via a detached
``fire_twenty_task(event_id)`` the caller ran after committing. Twenty was
retired in Sep 2026 and that half is gone; the telemetry row, which is what the
internal queue reads, is unchanged. ``club_request_events.twenty_task_id`` /
``.twenty_task_status`` are left on the table as history and are no longer
written — a row recorded from here on carries neither.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.models.db import ClubRequestEvent

logger = logging.getLogger(__name__)


async def add_request_event(session, *, org_id, request_type: str,
                            summary: Optional[str] = None, detail: Optional[dict] = None,
                            source: str = "app", requested_by=None,
                            ref_table: Optional[str] = None, ref_id=None) -> ClubRequestEvent:
    """Record one club→BetterCricket request in the caller's session (no commit).
    Flushes so the row gets its id, which a caller may want to reference."""
    ev = ClubRequestEvent(
        organisation_id=org_id, request_type=request_type, summary=(summary or "")[:1000],
        detail=detail or None, source=source, requested_by=requested_by,
        ref_table=ref_table, ref_id=ref_id,
    )
    session.add(ev)
    await session.flush()
    return ev
