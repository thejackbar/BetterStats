"""Thin wrapper around the Stripe SDK — Checkout Session creation, subscription
lookups, and webhook signature verification.

Mirrors the shape of services/square_client.py (BetterMerch's Square wrapper):
plain module functions, no persistent client object held between calls. Unlike
Square, this is a SINGLE platform-owned Stripe account (not per-club OAuth) —
every club is billed through the one BetterCricket Stripe account, so there's
no per-org token to look up, just the one api key from settings.

Uses stripe-python's `*_async` methods (httpx-backed) throughout so a Stripe
API call never blocks the event loop — this is an async FastAPI app.
"""
from __future__ import annotations

import logging

import stripe

from app.config.settings import settings
from app.services import billing_pricing

logger = logging.getLogger(__name__)


class StripeNotConfigured(RuntimeError):
    """Raised when a Stripe call is attempted without api keys configured.
    Callers should turn this into a clean 400/503, never a raw SDK traceback."""


def _require_configured() -> None:
    if not settings.stripe_configured:
        raise StripeNotConfigured("Stripe is not configured (STRIPE_SECRET_KEY/STRIPE_PUBLISHABLE_KEY unset)")
    # stripe-python's api_key is a module-level attribute — safe to set on every
    # call since this process only ever talks to one Stripe account.
    stripe.api_key = settings.stripe_secret_key


async def create_checkout_session(*, org_id: str, billing_keys: list[str],
                                   customer_id: str | None, customer_email: str | None):
    """A Stripe Checkout Session in subscription mode, priced from
    billing_pricing.price_for (dynamic price_data line items, so no Stripe
    Price objects need pre-creating in the dashboard for every module
    combination). The bundle discount, if any, is applied as a forever coupon
    created alongside the session so it recurs on every renewal, not just the
    first invoice.

    org_id + the selected billing_keys are round-tripped through BOTH the
    session's own metadata/client_reference_id AND the subscription's metadata
    — the webhook only ever needs to read one of these depending on which
    event fired, never a second lookup against our own DB to know what was
    bought."""
    _require_configured()
    quote = billing_pricing.price_for(billing_keys)

    line_items = [
        {
            "price_data": {
                "currency": settings.stripe_currency,
                "unit_amount": item["price"] * 100,
                "recurring": {"interval": "year"},
                "product_data": {"name": f"BetterCricket — {item['name']}"},
            },
            "quantity": 1,
        }
        for item in quote["line_items"]
    ]

    metadata = {"org_id": str(org_id), "billing_keys": ",".join(sorted(billing_keys))}
    params = {
        "mode": "subscription",
        "line_items": line_items,
        "client_reference_id": str(org_id),
        "metadata": metadata,
        "subscription_data": {"metadata": metadata},
        "success_url": settings.stripe_checkout_success_url,
        "cancel_url": settings.stripe_checkout_cancel_url,
    }

    if quote["discount"] > 0:
        coupon = await stripe.Coupon.create_async(
            amount_off=quote["discount"] * 100,
            currency=settings.stripe_currency,
            duration="forever",
            name=f"Bundle discount ({quote['module_count']} modules)",
        )
        params["discounts"] = [{"coupon": coupon["id"]}]

    if customer_id:
        params["customer"] = customer_id
    elif customer_email:
        params["customer_email"] = customer_email

    return await stripe.checkout.Session.create_async(**params)


async def retrieve_subscription(subscription_id: str):
    _require_configured()
    return await stripe.Subscription.retrieve_async(subscription_id)


def construct_webhook_event(payload: bytes, sig_header: str):
    """Verifies the Stripe-Signature header (local HMAC check, no network call)
    and returns the parsed Event. Raises stripe.error.SignatureVerificationError
    on a bad/missing signature — callers must treat that as a hard reject
    (400), never process the payload unverified."""
    if not settings.stripe_webhook_secret:
        raise StripeNotConfigured("Stripe webhook secret not set")
    return stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
