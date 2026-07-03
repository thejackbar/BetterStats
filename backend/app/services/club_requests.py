"""Club → BetterCricket request telemetry, and the automated Twenty CRM task.

Every time a club asks BetterCricket for something that a human needs to action
— a BetterComms sandbox→production tier lift, a module trial/subscribe, and
future asks — it should leave one durable telemetry row (``club_request_events``)
AND raise a task in the Twenty CRM so the back office sees it. This is the single
place both happen, so callers across the app stay uniform.

Two steps, kept apart so the CRM push never blocks the request:

  * ``add_request_event(session, …)`` — writes the telemetry row in the caller's
    transaction (no commit; the caller commits alongside its own domain row).
  * ``fire_twenty_task(event_id)`` — call AFTER the caller commits. Spawns a
    detached, best-effort coroutine that creates the Twenty task, links it to the
    club's CRM company when one exists, and stamps the event's
    ``twenty_task_status``. Never raises into the request path (mirrors the
    fire-and-forget CRM mirror in services/ses_events.py).

Twenty not configured ⇒ the event is still recorded, marked ``skipped``.
"""
from __future__ import annotations

import asyncio
import datetime
import logging
import uuid as _uuid
from typing import Optional

import httpx
from sqlalchemy import select, text

from app.config.settings import settings
from app.models.db import ClubRequestEvent, MarketingClub, async_session_maker
from app.services.twenty_client import client
from app.services.twenty_sync import _link_get, _link_put

logger = logging.getLogger(__name__)

# Hold detached CRM-push tasks so they aren't garbage-collected mid-flight (same
# pattern as the comms send loop / dossier builders).
_TASKS: set[asyncio.Task] = set()

# Default due-date lead time for the raised task.
_TASK_DUE_DAYS = 2


async def add_request_event(session, *, org_id, request_type: str,
                            summary: Optional[str] = None, detail: Optional[dict] = None,
                            source: str = "app", requested_by=None,
                            ref_table: Optional[str] = None, ref_id=None) -> ClubRequestEvent:
    """Record one club→BetterCricket request in the caller's session (no commit).
    Flushes so the row gets its id, which ``fire_twenty_task`` needs."""
    ev = ClubRequestEvent(
        organisation_id=org_id, request_type=request_type, summary=(summary or "")[:1000],
        detail=detail or None, source=source, requested_by=requested_by,
        ref_table=ref_table, ref_id=ref_id,
        twenty_task_status=("pending" if client.configured else "skipped"),
    )
    session.add(ev)
    await session.flush()
    return ev


def fire_twenty_task(event_id) -> None:
    """Kick the detached CRM push for a recorded event. Safe to call always — a
    no-op when Twenty isn't configured. Call after the caller has committed."""
    if not client.configured:
        return
    task = asyncio.create_task(_dispatch(str(event_id)))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)


async def _company_tid(session, org_id) -> Optional[str]:
    """Best-effort Twenty company id for a real club org: the club's marketing
    directory row carries the CRM link key (grassroots_guid → twenty_links)."""
    try:
        guid = (await session.execute(
            select(MarketingClub.grassroots_guid).where(
                MarketingClub.existing_org_id == org_id))).scalars().first()
        if not guid:
            return None
        row = await _link_get(session, "club", guid)
        return row[0] if row else None
    except Exception:  # noqa: BLE001 — linking is optional, never fatal
        return None


async def _dispatch(event_id: str) -> None:
    """Create the Twenty task for one event and stamp the result. Best-effort."""
    try:
        async with async_session_maker() as session:
            ev = await session.get(ClubRequestEvent, _uuid.UUID(event_id))
            if ev is None:
                return
            ext_ref = f"club_request:{ev.id}"
            # Dedupe: if we've already raised this one, don't double up.
            if await _link_get(session, "task", ext_ref):
                ev.twenty_task_status = "created"
                await session.commit()
                return
            title = (ev.summary or f"Club request: {ev.request_type}")[:255]
            due = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=_TASK_DUE_DAYS)
            values: dict = {"title": title, "status": "TODO", "dueAt": due.isoformat()}
            if settings.twenty_task_assignee_id:
                values["assigneeId"] = settings.twenty_task_assignee_id
            company_tid = await _company_tid(session, ev.organisation_id)
            async with httpx.AsyncClient() as http:
                try:
                    task = await client.create(http, "tasks", values)
                except Exception:  # noqa: BLE001
                    ev.twenty_task_status = "failed"
                    await session.commit()
                    logger.exception("twenty task create failed for club request %s", ev.id)
                    return
                tid = task.get("id")
                if not tid:
                    ev.twenty_task_status = "failed"
                    await session.commit()
                    return
                await _link_put(session, "task", ext_ref, tid, "")
                if company_tid:
                    try:
                        await client.create(http, "taskTargets",
                                            {"taskId": tid, "companyId": company_tid})
                    except Exception:  # noqa: BLE001 — task still exists, just unlinked
                        logger.warning("twenty taskTarget link failed for task %s", tid)
            ev.twenty_task_id = tid
            ev.twenty_task_status = "created"
            await session.commit()
    except Exception as e:  # never let the detached task die noisily
        logger.error("club_requests CRM dispatch failed for %s: %s", event_id, e, exc_info=True)
