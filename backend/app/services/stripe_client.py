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
from datetime import datetime, timezone

import stripe
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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


def epoch_to_date(ts):
    """A Stripe unix timestamp (e.g. subscription.current_period_end) as a
    plain date, or None. Shared by stripe_billing.py's webhook handlers and
    the add-to-existing-subscription flow below so there's one conversion,
    not two copies drifting apart."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).date() if ts else None


def epoch_to_datetime(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None


async def create_checkout_session(*, org_id: str, billing_keys: list[str],
                                   customer_id: str | None, customer_email: str | None,
                                   discount_schedule: dict | None = None):
    """A Stripe Checkout Session in subscription mode, priced from
    billing_pricing.price_for (dynamic price_data line items, so no Stripe
    Price objects need pre-creating in the dashboard for every module
    combination). The bundle discount, if any, is applied as a forever coupon
    created alongside the session so it recurs on every renewal, not just the
    first invoice. ``discount_schedule`` is the LIVE, super-admin-configured
    bundle-discount table (platform_settings.get_bundle_discount_schedule) —
    the caller fetches it (this module has no DB access of its own) and
    passes it straight through; omitted, price_for falls back to its
    hardcoded seed default.

    org_id + the selected billing_keys are round-tripped through BOTH the
    session's own metadata/client_reference_id AND the subscription's metadata
    — the webhook only ever needs to read one of these depending on which
    event fired, never a second lookup against our own DB to know what was
    bought."""
    _require_configured()
    quote = billing_pricing.price_for(billing_keys, schedule=discount_schedule)

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
    else:
        # Stripe rejects a session that sets BOTH discounts and
        # allow_promotion_codes, so only offer the customer-enterable
        # promotion-code field when our own bundle discount isn't already
        # applying — real promotional codes are created/managed directly in
        # the Stripe Dashboard (Product catalogue → Coupons), no admin UI of
        # our own needed for that.
        params["allow_promotion_codes"] = True

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


# ─── Adding modules to an ALREADY-LIVE subscription ────────────────────────
# Unlike create_checkout_session's line items (which support an inline ad-hoc
# product via price_data.product_data), Stripe's SubscriptionItem.create and
# Invoice.create_preview require a real Product id when using price_data —
# there's no inline product creation on those two endpoints. _ensure_product
# creates each billable module's Product exactly once (migration 152 caches
# the id in our own DB) rather than re-creating it — or searching for it — on
# every add-on checkout.

async def _ensure_product(db: AsyncSession, billing_key: str) -> str:
    row = (await db.execute(
        text("SELECT stripe_product_id FROM stripe_products WHERE billing_key = :k"),
        {"k": billing_key},
    )).first()
    if row:
        return row[0]
    _require_configured()
    name = billing_pricing.CHECKOUT_MODULE_NAMES.get(billing_key, billing_key)
    product = await stripe.Product.create_async(
        name=f"BetterCricket — {name}", metadata={"billing_key": billing_key},
    )
    # A concurrent request could race this and create a second, orphaned
    # Product in Stripe — harmless (an unused Product sitting in the
    # dashboard) and not worth locking for on a low-frequency admin action.
    await db.execute(
        text(
            "INSERT INTO stripe_products (billing_key, stripe_product_id) VALUES (:k, :p) "
            "ON CONFLICT (billing_key) DO NOTHING"
        ),
        {"k": billing_key, "p": product["id"]},
    )
    await db.commit()
    return product["id"]


async def _addon_price_data_items(db: AsyncSession, billing_keys: list[str]) -> list[dict]:
    quote = billing_pricing.price_for_addon(billing_keys)
    items = []
    for item in quote["line_items"]:
        product_id = await _ensure_product(db, item["key"])
        items.append({
            "price_data": {
                "currency": settings.stripe_currency,
                "product": product_id,
                "unit_amount": item["price"] * 100,
                "recurring": {"interval": "year"},
            },
            "quantity": 1,
        })
    return items


async def preview_add_modules(db: AsyncSession, subscription_id: str, billing_keys: list[str]) -> dict:
    """Stripe's own invoice preview for adding new items to an existing
    subscription — the EXACT prorated amount Stripe would charge today, not
    an approximation we compute from day-counts ourselves. No bundle discount
    (see billing_pricing.price_for_addon — that only applies to the initial
    all-at-once subscribe)."""
    _require_configured()
    items = await _addon_price_data_items(db, billing_keys)
    if not items:
        return {"line_items": [], "total": 0, "currency": settings.stripe_currency}
    preview = await stripe.Invoice.create_preview_async(
        subscription=subscription_id,
        subscription_details={"items": items, "proration_behavior": "always_invoice"},
    )
    lines = [
        {"name": ln.get("description") or "", "amount": (ln.get("amount") or 0) / 100}
        for ln in (preview.get("lines") or {}).get("data", [])
    ]
    return {
        "line_items": lines,
        "total": (preview.get("total") or 0) / 100,
        "currency": preview.get("currency") or settings.stripe_currency,
    }


async def add_modules_to_subscription(db: AsyncSession, subscription_id: str,
                                       existing_billing_keys: list[str], new_billing_keys: list[str]):
    """Adds new_billing_keys as items on an already-live subscription,
    charging the prorated amount immediately (proration_behavior=
    always_invoice) against the payment method already on file — there's
    nothing new to collect, so this never redirects to a Checkout Session.
    Updates the subscription's own metadata.billing_keys to the union of
    old+new so future invoice.paid renewals (stripe_billing.py) keep
    including the newly added module. Returns the updated Subscription
    (current_period_end drives the renewal_date the caller grants with)."""
    _require_configured()
    items = await _addon_price_data_items(db, new_billing_keys)
    for item in items:
        await stripe.SubscriptionItem.create_async(
            subscription=subscription_id,
            proration_behavior="always_invoice",
            **item,
        )
    all_keys = sorted(set(existing_billing_keys) | set(new_billing_keys))
    return await stripe.Subscription.modify_async(
        subscription_id, metadata={"billing_keys": ",".join(all_keys)},
    )
