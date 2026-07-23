"""Stripe Connect webhook (unauthenticated) — account onboarding status +
completed member fee payments for CLUB-connected Stripe accounts.

A SEPARATE endpoint from /public/stripe/webhook (BetterCricket's own platform
billing) — register this URL in the Stripe dashboard under Connect →
Webhooks (not the regular Webhooks page), signed with its own endpoint
secret (STRIPE_CONNECT_WEBHOOK_SECRET). Deploy at
https://betterat.cricket/api/public/stripe-connect/webhook (nginx strips
/api, so it resolves at /public/stripe-connect/webhook here).

Trust comes from Stripe's own request signature, verified locally — same
"verify the signature, not a login" posture as /public/stripe/webhook and
routers/public_ses.py.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from stripe import error as stripe_error

from app.models.db import get_db
from app.services import stripe_connect_billing, stripe_connect_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public/stripe-connect", tags=["public-stripe-connect"])

_HANDLERS = {
    "account.updated": stripe_connect_billing.handle_account_updated,
    "checkout.session.completed": stripe_connect_billing.handle_checkout_completed,
}


@router.post("/webhook")
async def stripe_connect_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    if not sig_header:
        raise HTTPException(status_code=400, detail="missing Stripe-Signature header")

    try:
        event = stripe_connect_client.construct_connect_webhook_event(payload, sig_header)
    except stripe_connect_client.StripeNotConfigured:
        raise HTTPException(status_code=503, detail="Stripe Connect webhook not configured")
    except stripe_error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="invalid Stripe signature")

    handler = _HANDLERS.get(event["type"])
    if handler is None:
        return JSONResponse({"status": "ignored", "type": event["type"]})

    # Connect events carry the connected account id at the top level (not
    # inside data.object) — every handler needs it to resolve which club the
    # event belongs to.
    account_id = event.get("account")
    if not account_id:
        return JSONResponse({"status": "ignored", "type": event["type"], "reason": "no account"})

    try:
        await handler(db, event["data"]["object"], account_id)
    except Exception:
        logger.exception("Stripe Connect webhook handler failed for event %s (%s)", event.get("id"), event["type"])
        raise HTTPException(status_code=500, detail="webhook handler error")

    return JSONResponse({"status": "ok", "type": event["type"]})
