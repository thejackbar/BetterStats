"""Support chat endpoints (Chatwoot). Logic lives in services/support_chat.py.

  GET  /club-admin/support-chat/identity           signed in: who to open the widget as
  POST /public/support-chat/webhook/{secret}       Chatwoot's agent bot calls this

The webhook has no login. The secret in its path is the credential, compared in
constant time; a wrong or unset secret is a 404, so the route does not announce
that it exists. Work runs after the 200 goes back, because Chatwoot retries a
slow webhook and a model call takes a few seconds.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import ClubMembership, Organisation, User, get_db
from app.routers.auth import get_current_club, get_current_user
from app.services import support_chat

logger = logging.getLogger(__name__)

admin_router = APIRouter(prefix="/club-admin/support-chat", tags=["support-chat"])
public_router = APIRouter(prefix="/public/support-chat", tags=["support-chat"])

# A Chatwoot payload with a long conversation is still small. Anything bigger is not Chatwoot.
MAX_BODY_BYTES = 256 * 1024


@admin_router.get("/identity")
async def get_identity(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Who the help window opens as. ``{"enabled": false}`` when it is not set up.

    Open to every signed-in admin: asking for help needs no capability, and the
    answer is only the caller's own name, email and club."""
    membership = (await db.execute(
        select(ClubMembership).where(ClubMembership.user_id == current_user.id)
    )).scalar_one_or_none()
    return support_chat.identity(current_user, club, membership.role if membership else None)


@public_router.post("/webhook/{secret}")
async def chatwoot_webhook(secret: str, request: Request, background: BackgroundTasks):
    if not support_chat.webhook_secret_ok(secret):
        raise HTTPException(status_code=404, detail="Not found")
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Too large")
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Not JSON")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Not an object")
    background.add_task(support_chat.handle_webhook, payload)
    return {"status": "ok"}
