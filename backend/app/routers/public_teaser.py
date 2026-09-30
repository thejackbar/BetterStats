"""The public page behind a club's teaser link (``/preview/{token}``).

A prospect club is emailed (or shown an ad that lands on) a page built from its
own public Cricket Australia figures. Anything on the page opens the same
invitation to claim the club through the trial wizard. Two unauthenticated
routes:

  GET  /public/teaser/{token}        the snapshot and what the page leads with
  POST /public/teaser/{token}/event  a view / tile tap / claim beacon

Nothing here needs the self-serve registration flag: the page is an
introduction, and the wizard it hands over to has its own gate. The token is
the whole credential (16 random bytes, made once and never rotated, so a link
already sent keeps working); an unknown, malformed or not-yet-good snapshot is
a plain 404 that tells nothing about which case it was.

Only the ``ok`` snapshots are served. ``empty``, ``junior_only`` and ``error``
have nothing to show, and an unsuitable club must never get a page.
"""
from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import get_db
from app.services import club_teaser, rate_limit
from app.services.login_audit import client_ip
from app.services.usage_tracker import record_event_bg

router = APIRouter(prefix="/public/teaser", tags=["public-teaser"])

TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
READ_LIMIT, READ_WINDOW = 120, 3600
EVENT_LIMIT, EVENT_WINDOW = 120, 3600
# What a page may report. An allowlist, so this cannot be used to write
# arbitrary strings into usage_events.
EVENT_KINDS = {"view", "tile", "claim_open", "claim_go"}


async def _row(db: AsyncSession, token: str):
    if not TOKEN_RE.match(token or ""):
        raise HTTPException(status_code=404, detail="Not found")
    row = (await db.execute(text("""
        SELECT t.snapshot, t.version, mc.id AS club_id, mc.existing_org_id,
               (SELECT o.slug FROM organisations o
                 WHERE o.id = mc.existing_org_id AND o.archived_at IS NULL) AS registered_slug
        FROM club_teaser_snapshots t
        JOIN marketing_clubs mc ON mc.id = t.marketing_club_id
        WHERE t.token = :t AND t.status = 'ok' AND t.snapshot IS NOT NULL
    """), {"t": token})).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return row


@router.get("/{token}")
async def get_teaser(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    rate_limit.enforce(f"teaser:read:{client_ip(request)}", READ_LIMIT, READ_WINDOW,
                       detail="Too many requests.")
    row = await _row(db, token)
    snap = row["snapshot"]
    view = club_teaser.presentation(snap)
    club = snap.get("club") or {}
    return {
        **view,
        "version": row["version"],
        # The full leaders lists (the page shows five of each); the record and
        # ladder are only what presentation() chose to show.
        "batting": snap.get("batting") or [],
        "bowling": snap.get("bowling") or [],
        "fielding": snap.get("fielding") or [],
        "records": snap.get("records") or [],
        "claim": {"ca_org_id": club.get("ca_org_id"), "name": club.get("name")},
        # A club that is already on BetterCricket is sent to its own site
        # rather than to a trial it cannot start.
        "registered": {"slug": row["registered_slug"]} if row["registered_slug"] else None,
    }


class TeaserEvent(BaseModel):
    kind: str
    section: Optional[str] = None
    visitor_id: Optional[str] = None


@router.post("/{token}/event")
async def teaser_event(token: str, body: TeaserEvent, request: Request,
                       db: AsyncSession = Depends(get_db)):
    key = (body.visitor_id or "").strip()[:64] or client_ip(request)
    rate_limit.enforce(f"teaser:event:{key}", EVENT_LIMIT, EVENT_WINDOW, detail="Too many requests.")
    kind = (body.kind or "").strip()
    if kind not in EVENT_KINDS:
        raise HTTPException(status_code=422, detail="Unknown event")
    row = await _row(db, token)
    meta = {"marketing_club_id": str(row["club_id"]), "version": row["version"]}
    section = (body.section or "").strip()[:40]
    if section:
        meta["section"] = section
    record_event_bg(
        event_type="teaser", method="POST", path="/public/teaser/event", route=kind, status=200,
        ip=client_ip(request), user_agent=request.headers.get("user-agent"),
        visitor_id=(body.visitor_id or "").strip()[:64] or None, metadata=meta,
    )
    return {"ok": True}
