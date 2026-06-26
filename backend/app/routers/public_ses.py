"""BetterComms — public SES event webhook (unauthenticated).

Amazon SES publishes delivery / bounce / complaint / reject / delay events to an
SNS topic, which POSTs them here. There is no session, so the request is trusted
by **verifying the SNS message signature** (and, optionally, a shared token on the
path), not by a login. See services/ses_events.py and
docs/bettercomms-architecture.md.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.models.db import get_db
from app.services.ses_events import handle_sns_message, verify_signature

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public/ses", tags=["public-ses"])


@router.post("/events")
async def ses_events(request: Request, db: AsyncSession = Depends(get_db)):
    raw = await request.body()
    try:
        msg = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        return JSONResponse({"status": "ignored", "reason": "bad json"})
    if not isinstance(msg, dict):
        return JSONResponse({"status": "ignored", "reason": "not an object"})

    # Optional shared token on the path adds defence in depth on a public route.
    if settings.ses_event_token:
        if request.query_params.get("token") != settings.ses_event_token:
            raise HTTPException(status_code=403, detail="bad token")

    # The signature is the real gate — without it the suppression list is forgeable.
    if settings.ses_sns_verify_signatures and not await verify_signature(msg):
        raise HTTPException(status_code=400, detail="invalid SNS signature")

    result = await handle_sns_message(db, msg)
    return JSONResponse({"status": "ok", **result})
