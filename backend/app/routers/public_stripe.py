"""Stripe webhook — public, signature-verified (Stripe Phase 1, see
docs/self-serve-trial-onboarding-plan.md). One-way sync: Stripe is the
source of truth for what a club is actually subscribed to and charged;
this endpoint is the only place that state flows back into
org_module_subscriptions. Never the other direction — nothing here writes
to Stripe.

Checked-then-processed-then-recorded (not claimed up front): a crash or bug
partway through handling an event must be retried by Stripe's own redelivery,
not silently swallowed as "already done" — same reasoning as
trial_lifecycle.py's send-then-record dedupe.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

import stripe
from fastapi import APIRouter, Request, Response
from sqlalchemy import text
from sqlalchemy.orm import selectinload

from app.config.settings import settings
from app.models.db import Organisation, async_session_maker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public/stripe", tags=["public-stripe"])


async def _already_processed(session, event_id: str) -> bool:
    row = (await session.execute(
        text("SELECT 1 FROM stripe_webhook_events WHERE event_id = :id"), {"id": event_id}
    )).first()
    return row is not None


async def _record_processed(session, event_id: str, event_type: str) -> None:
    await session.execute(
        text("INSERT INTO stripe_webhook_events (event_id, event_type) VALUES (:id, :t) "
             "ON CONFLICT (event_id) DO NOTHING"),
        {"id": event_id, "t": event_type},
    )
    await session.commit()


async def _handle_checkout_completed(session, event: dict) -> None:
    from app.services import module_subscriptions as mod_subs
    from app.services.stripe_billing import module_key_for_price, retrieve_subscription

    obj = event["data"]["object"]
    org_id = (obj.get("metadata") or {}).get("org_id")
    subscription_id = obj.get("subscription")
    if not org_id or not subscription_id:
        logger.warning("Stripe checkout.session.completed missing org_id/subscription: %s", obj.get("id"))
        return

    org = await session.get(
        Organisation, org_id, options=[selectinload(Organisation.module_subscriptions)]
    )
    if org is None:
        logger.warning("Stripe checkout.session.completed for unknown org %s", org_id)
        return

    subscription = await retrieve_subscription(subscription_id)
    now = datetime.now(timezone.utc)
    period_end = subscription.get("current_period_end")
    renewal_date = date.fromtimestamp(period_end) if period_end else None

    for item in subscription["items"]["data"]:
        price_id = item["price"]["id"]
        module_key = module_key_for_price(price_id)
        if module_key is None:
            logger.warning("Stripe subscription item %s has an unrecognised price %s", item["id"], price_id)
            continue
        sub = mod_subs.set_status(org, module_key, mod_subs.STATUS_ACTIVE, renewal_date=renewal_date, now=now)
        sub.stripe_subscription_id = subscription["id"]
        sub.stripe_subscription_item_id = item["id"]

    await session.commit()


async def _handle_subscription_updated(session, event: dict) -> None:
    """Renewal date moves forward each period, or Stripe marks it past_due /
    unpaid on a failed charge. Dunning UX (retry emails, grace period) is a
    later phase — this just keeps the stored status/date honest."""
    from app.auth.modules import STATUS_ACTIVE, STATUS_CANCELLED
    from app.services import module_subscriptions as mod_subs

    obj = event["data"]["object"]
    org_id = (obj.get("metadata") or {}).get("org_id")
    if not org_id:
        return
    org = await session.get(
        Organisation, org_id, options=[selectinload(Organisation.module_subscriptions)]
    )
    if org is None:
        return

    stripe_status = obj.get("status")
    status_map = {"active": STATUS_ACTIVE, "past_due": "past_due",
                  "canceled": STATUS_CANCELLED, "unpaid": "past_due"}
    new_status = status_map.get(stripe_status)
    period_end = obj.get("current_period_end")
    renewal_date = date.fromtimestamp(period_end) if period_end else None
    now = datetime.now(timezone.utc)

    for sub in (org.module_subscriptions or []):
        if sub.stripe_subscription_id != obj.get("id"):
            continue
        if new_status:
            sub.status = new_status
        if renewal_date:
            sub.renewal_date = renewal_date
        sub.updated_at = now
    mod_subs.recompute_overrides_cache(org, now)
    await session.commit()


async def _handle_subscription_deleted(session, event: dict) -> None:
    from app.auth.modules import STATUS_CANCELLED
    from app.services import module_subscriptions as mod_subs

    obj = event["data"]["object"]
    org_id = (obj.get("metadata") or {}).get("org_id")
    if not org_id:
        return
    org = await session.get(
        Organisation, org_id, options=[selectinload(Organisation.module_subscriptions)]
    )
    if org is None:
        return
    now = datetime.now(timezone.utc)
    for sub in (org.module_subscriptions or []):
        if sub.stripe_subscription_id == obj.get("id"):
            sub.status = STATUS_CANCELLED
            sub.updated_at = now
    mod_subs.recompute_overrides_cache(org, now)
    await session.commit()


_HANDLERS = {
    "checkout.session.completed": _handle_checkout_completed,
    "customer.subscription.updated": _handle_subscription_updated,
    "customer.subscription.deleted": _handle_subscription_deleted,
}


@router.post("/webhook")
async def stripe_webhook(request: Request):
    if not settings.stripe_webhook_configured:
        logger.warning("Stripe webhook received but STRIPE_WEBHOOK_SECRET is not set — ignoring")
        return {"status": "ignored", "reason": "webhook not configured"}

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        logger.warning("Stripe webhook signature/payload invalid: %s", e)
        return Response(status_code=400)

    handler = _HANDLERS.get(event["type"])
    async with async_session_maker() as session:
        if await _already_processed(session, event["id"]):
            return {"status": "duplicate"}
        if handler is not None:
            try:
                await handler(session, event)
            except Exception:
                await session.rollback()
                logger.exception("Stripe webhook handler failed for event %s (%s)", event["id"], event["type"])
                # Still record + 200: an event we can't process cleanly must not
                # retry-storm forever. Logged for manual follow-up instead.
        await _record_processed(session, event["id"], event["type"])

    return {"status": "ok"}
