import hashlib
import hmac
import logging

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.models.db import get_db

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)


@router.post("/playhq")
async def receive_webhook(request: Request):
    try:
        payload = await request.json()
    except Exception:
        logger.warning("Webhook received non-JSON payload")
        return Response(status_code=400)

    event_type = payload.get("type", "")
    logger.info(f"Webhook received: {event_type} (no handler registered)")

    # Always return 200 to PlayHQ so it doesn't retry
    return {"status": "ok"}


def _verify_twenty(request: Request, raw: bytes) -> bool:
    """Authenticate an inbound Twenty webhook against the shared secret. Accepts
    either an HMAC-SHA256 signature over the raw body (``X-Twenty-Webhook-Signature``)
    or a plain bearer match (``X-Webhook-Secret``) — whichever the workspace is set up
    to send. Both compared in constant time."""
    secret = settings.twenty_webhook_secret
    if not secret:
        return False
    bearer = request.headers.get("x-webhook-secret") or ""
    if bearer and hmac.compare_digest(bearer, secret):
        return True
    sig = (request.headers.get("x-twenty-webhook-signature")
           or request.headers.get("x-webhook-signature") or "")
    if sig:
        expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        # Tolerate a "sha256=" prefix some senders add.
        sig = sig.split("=", 1)[-1] if "=" in sig else sig
        if hmac.compare_digest(sig, expected):
            return True
    return False


@router.post("/twenty")
async def receive_twenty_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Inbound Twenty record-update webhook (see services/twenty_inbound). A no-op
    when the webhook secret isn't configured, so it's safe to leave unwired. Always
    returns 200 (after auth) so Twenty doesn't retry-storm on a benign payload."""
    if not settings.twenty_webhook_configured:
        return {"status": "ignored", "reason": "webhook not configured"}
    raw = await request.body()
    if not _verify_twenty(request, raw):
        return Response(status_code=401)
    try:
        import json
        payload = json.loads(raw or b"{}")
    except Exception:
        return Response(status_code=400)
    try:
        from app.services import twenty_inbound
        result = await twenty_inbound.dispatch_webhook(db, payload)
        if result.get("created"):
            logger.info(f"Twenty webhook queued module request(s): {result}")
        return {"status": "ok", **result}
    except Exception:
        logger.exception("Twenty webhook dispatch failed")
        # Swallow so Twenty doesn't retry-storm; we logged it.
        return {"status": "error"}
