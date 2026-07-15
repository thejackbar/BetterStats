"""Stripe webhook (unauthenticated) — the SOURCE OF TRUTH for granting/removing
billing entitlement after a Checkout Session.

Not gated by require_billing_checkout_enabled: once a club has a real Stripe
subscription, its renewals/failures/cancellations must keep being processed
even if the flag is later switched off for NEW checkouts. Trust here comes
from Stripe's own request signature (the Stripe-Signature header, verified
locally against STRIPE_WEBHOOK_SECRET — see services/stripe_client.py), the
same "verify the signature, not a login" posture routers/public_ses.py uses
for inbound SNS events.

Deploy note: register this endpoint in the Stripe dashboard (Developers →
Webhooks) as https://betterat.cricket/api/public/stripe/webhook (nginx strips
the /api prefix, so it resolves at /public/stripe/webhook here) — subscribed
to at least checkout.session.completed, invoice.paid, invoice.payment_failed,
customer.subscription.deleted.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from stripe import error as stripe_error

from app.models.db import get_db
from app.services import stripe_billing, stripe_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public/stripe", tags=["public-stripe"])

_HANDLERS = {
    "checkout.session.completed": stripe_billing.handle_checkout_completed,
    "invoice.paid": stripe_billing.handle_invoice_paid,
    "invoice.payment_failed": stripe_billing.handle_invoice_payment_failed,
    "customer.subscription.deleted": stripe_billing.handle_subscription_deleted,
}


@router.post("/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    if not sig_header:
        raise HTTPException(status_code=400, detail="missing Stripe-Signature header")

    try:
        event = stripe_client.construct_webhook_event(payload, sig_header)
    except stripe_client.StripeNotConfigured:
        # A webhook secret was never set — reject rather than trust an
        # unverifiable payload.
        raise HTTPException(status_code=503, detail="Stripe webhook not configured")
    except stripe_error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="invalid Stripe signature")

    handler = _HANDLERS.get(event["type"])
    if handler is None:
        return JSONResponse({"status": "ignored", "type": event["type"]})

    try:
        await handler(db, event["data"]["object"])
    except Exception:
        logger.exception("Stripe webhook handler failed for event %s (%s)", event.get("id"), event["type"])
        # A 500 tells Stripe to retry — the right outcome for a transient DB/
        # network failure on our side, vs. swallowing it and silently losing
        # the entitlement change.
        raise HTTPException(status_code=500, detail="webhook handler error")

    return JSONResponse({"status": "ok", "type": event["type"]})
