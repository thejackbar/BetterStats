"""BetterComms — public unsubscribe (unauthenticated).

The recipient-facing half of BetterComms. Every campaign email carries a signed
one-click unsubscribe link to here. Per the Spam Act 2003 this must work with no
login and no extra information, so the token alone identifies the contact.

Not gated by ``require_module`` — the recipient has no session. The token is a
signed JWT ({org, cid}); we resolve the contact from it and flip ``subscribed``
false. Unknown / malformed / already-handled tokens still return a friendly
page (we never leak why a link is inert), so a test-send link works too.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.models.db import CommsContact, Organisation, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public/comms", tags=["public-comms"])

UNSUB_TYP = "comms_unsub"


def _page(title: str, body: str, accent: str = "#243352") -> str:
    return f"""\
<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{title}</title></head>
<body style="margin:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background:#f3f4f6;color:#1f2937;">
<div style="max-width:480px;margin:12vh auto;background:#fff;border-radius:12px;padding:32px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,.1);">
<div style="height:6px;width:48px;background:{accent};border-radius:999px;margin:0 auto 20px;"></div>
<h1 style="font-size:20px;margin:0 0 10px;">{title}</h1>
<p style="color:#6b7280;font-size:15px;line-height:1.6;margin:0;">{body}</p>
</div></body></html>"""


async def _unsubscribe(token: str, db: AsyncSession) -> tuple[str, str, str]:
    """Returns (title, body, accent). Idempotent + tolerant of bad tokens."""
    accent = "#243352"
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return ("Link expired", "This unsubscribe link is no longer valid. If you keep getting emails, reply and ask to be removed.", accent)
    if payload.get("typ") != UNSUB_TYP:
        return ("Link expired", "This unsubscribe link is no longer valid.", accent)

    org = None
    try:
        org = await db.get(Organisation, uuid.UUID(str(payload.get("org"))))
    except (ValueError, TypeError):
        org = None
    if org and org.accent_color:
        accent = org.accent_color
    club_name = org.name if org else "the club"

    try:
        contact = await db.get(CommsContact, uuid.UUID(str(payload.get("cid"))))
    except (ValueError, TypeError):
        contact = None
    if contact and (not org or contact.organisation_id == org.id):
        if contact.subscribed:
            contact.subscribed = False
            contact.unsubscribed_at = datetime.now(timezone.utc)
            await db.commit()
        return ("You're unsubscribed",
                f"You won't receive any more emails from {club_name}. Changed your mind? Just let them know.",
                accent)
    # Token valid but no live contact (e.g. a test-send link) — report success
    # rather than reveal that nothing happened.
    return ("You're unsubscribed", f"You won't receive any more emails from {club_name}.", accent)


@router.get("/unsubscribe/{token}", response_class=HTMLResponse)
async def unsubscribe_get(token: str, db: AsyncSession = Depends(get_db)):
    title, body, accent = await _unsubscribe(token, db)
    return HTMLResponse(_page(title, body, accent))


@router.post("/unsubscribe/{token}")
async def unsubscribe_post(token: str, db: AsyncSession = Depends(get_db)):
    """One-click endpoint for the List-Unsubscribe-Post header (Gmail/Apple)."""
    await _unsubscribe(token, db)
    return JSONResponse({"status": "ok"})
