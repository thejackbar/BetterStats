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
    """Authenticate an inbound Twenty webhook against the shared secret (the value
    set in the webhook's Secret field).

    Twenty's real scheme (confirmed both against docs.twenty.com/developers/
    extend/capabilities/webhooks and a live capture of its headers —
    ``x-twenty-webhook-timestamp`` / ``x-twenty-webhook-signature`` /
    ``x-twenty-webhook-nonce``): HMAC-SHA256 of ``f"{timestamp}:{raw body}"``,
    hex-encoded, in ``X-Twenty-Webhook-Signature``, timestamp in
    ``X-Twenty-Webhook-Timestamp``. An EARLIER version of this function guessed
    at a generic "HMAC of the raw body alone, try every header" scheme, which
    never matched — Twenty mixes the timestamp into the signed string, so it
    silently 401'd every real delivery. A plain bearer header
    (``X-Webhook-Secret``) equal to the secret is also accepted, for a manual
    curl test or the Manual Trigger Workflow path (twenty-opportunity), where
    hand-computing the real signature isn't practical. All comparisons are
    constant-time."""
    secret = settings.twenty_webhook_secret
    if not secret:
        return False
    bearer = request.headers.get("x-webhook-secret") or ""
    if bearer and hmac.compare_digest(bearer, secret):
        return True
    timestamp = request.headers.get("x-twenty-webhook-timestamp")
    signature = request.headers.get("x-twenty-webhook-signature")
    if not (timestamp and signature):
        return False
    to_sign = f"{timestamp}:".encode() + raw
    expected = hmac.new(secret.encode(), to_sign, hashlib.sha256).hexdigest()
    try:
        return hmac.compare_digest(signature.strip().lower(), expected)
    except (TypeError, ValueError):
        return False


@router.post("/twenty")
async def receive_twenty_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Inbound Twenty record-update webhook (see services/twenty_inbound). A no-op
    when the webhook secret isn't configured, so it's safe to leave unwired. Always
    returns 200 (after auth) so Twenty doesn't retry-storm on a benign payload."""
    if not settings.twenty_webhook_configured:
        # Logged at WARNING (not silent): a request reaching here with no secret
        # configured is otherwise completely invisible in the logs — no line at
        # all — which reads identically to "the request never arrived" and
        # wastes a diagnosis cycle telling the two apart.
        logger.warning("Twenty webhook received but TWENTY_WEBHOOK_SECRET is not set — ignoring")
        return {"status": "ignored", "reason": "webhook not configured"}
    raw = await request.body()
    if not _verify_twenty(request, raw):
        # Self-diagnosing: log the header names (not values) so we can match Twenty's
        # actual signature header if the secret/format ever drifts.
        logger.warning("Twenty webhook signature mismatch; header names=%s",
                       list(request.headers.keys()))
        return Response(status_code=401)
    try:
        import json
        payload = json.loads(raw or b"{}")
    except Exception:
        return Response(status_code=400)
    # First-contact diagnostics: the exact shape of a real Twenty webhook payload
    # (eventName, and which top-level keys the record carries) has never been
    # confirmed against a live workspace — every field path in twenty_inbound is
    # a documented best guess. Log it (keys only, not values, to avoid dumping
    # PII) so a "the flag was Yes but nothing happened" report is diagnosable
    # from the container logs alone, no reproduction needed.
    try:
        _rec = payload.get("record") if isinstance(payload, dict) else None
        logger.info("Twenty webhook received: eventName=%r top_keys=%s record_keys=%s",
                   (payload or {}).get("eventName") or (payload or {}).get("event"),
                   sorted((payload or {}).keys()) if isinstance(payload, dict) else None,
                   sorted(_rec.keys()) if isinstance(_rec, dict) else None)
    except Exception:  # noqa: BLE001 - diagnostics must never break the real dispatch
        pass
    try:
        from app.services import twenty_inbound
        result = await twenty_inbound.dispatch_webhook(db, payload)
        if result.get("created") or result.get("event") == "create_opportunity":
            logger.info(f"Twenty webhook result: {result}")
        return {"status": "ok", **result}
    except Exception:
        logger.exception("Twenty webhook dispatch failed")
        # Swallow so Twenty doesn't retry-storm; we logged it.
        return {"status": "error"}


@router.post("/twenty-opportunity")
async def receive_twenty_opportunity_trigger(request: Request):
    """Alternate Opportunity-cascade entry point for a Manual Trigger Workflow's
    "Send Webhook" step (one per object — Lead / Company / Person), posting
    ``{"source": "lead"|"company"|"person", "recordId": "{{record.id}}"}``. NOT
    the day-to-day path — the primary trigger is the ``createOpportunity``
    field on Company/Person/Lead, dispatched through the plain ``/twenty``
    route below (see docs/twenty-crm-integration.md §19a/§19b). Same
    shared-secret auth as ``/twenty`` (the bearer ``X-Webhook-Secret`` header
    is the simplest to hand-type into a Workflow's custom headers). Always 200
    after auth so a misconfigured payload doesn't retry-storm."""
    if not settings.twenty_webhook_configured:
        return {"status": "ignored", "reason": "webhook not configured"}
    raw = await request.body()
    if not _verify_twenty(request, raw):
        logger.warning("Twenty opportunity webhook signature mismatch; header names=%s",
                       list(request.headers.keys()))
        return Response(status_code=401)
    try:
        import json
        payload = json.loads(raw or b"{}")
    except Exception:
        return Response(status_code=400)
    source = str(payload.get("source") or "").strip().lower()
    record_id = str(payload.get("recordId") or payload.get("record_id") or "").strip()
    from app.services.twenty_opportunity import run_cascade
    result = await run_cascade(source, record_id)
    if result.get("error"):
        logger.warning("Twenty opportunity cascade (source=%s, id=%s): %s", source, record_id, result["error"])
    return {"status": "ok" if not result.get("error") else "error", **result}
