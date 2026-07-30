"""Club → BetterCricket request telemetry.

Every time a club asks BetterCricket for something that a human needs to action
— a BetterComms sandbox→production tier lift, a module trial/subscribe, and
future asks — it leaves one durable telemetry row (``club_request_events``).
This is the single place that happens, so callers across the app stay uniform.

  * ``add_request_event(session, …)`` — writes the telemetry row in the caller's
    transaction (no commit; the caller commits alongside its own domain row).
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
    Flushes so the row gets its id."""
    ev = ClubRequestEvent(
        organisation_id=org_id, request_type=request_type, summary=(summary or "")[:1000],
        detail=detail or None, source=source, requested_by=requested_by,
        ref_table=ref_table, ref_id=ref_id,
    )
    session.add(ev)
    await session.flush()
    return ev
