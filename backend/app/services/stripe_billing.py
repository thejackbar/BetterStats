"""Stripe billing — self-serve subscribe (Stripe Phase 1, see
docs/self-serve-trial-onboarding-plan.md).

Products/Prices are managed directly in the Stripe dashboard (the club
already has them set up) — this module never creates or edits them, only
references the Price IDs configured in settings. Stripe is the source of
truth for what a club is actually charged; this app is the source of truth
for entitlement (org_module_subscriptions), kept in sync one-way via the
webhook in routers/public_stripe.py. No bi-directional sync.

The `stripe` package does blocking (synchronous) HTTP under the hood, so
every call here runs through `asyncio.to_thread` to avoid stalling the
event loop.
"""
from __future__ import annotations

import asyncio
import logging

import stripe

from app.auth.modules import BILLABLE_MODULE_NAMES, BILLABLE_MODULES
from app.config.settings import settings

logger = logging.getLogger(__name__)


class StripeNotConfigured(Exception):
    pass


class ModuleNotPriced(Exception):
    """A requested module has no Stripe Price ID configured."""
    def __init__(self, module_key: str):
        self.module_key = module_key
        super().__init__(f"{BILLABLE_MODULE_NAMES.get(module_key, module_key)} isn't available to subscribe to online yet")


def _client() -> stripe:
    if not settings.stripe_configured:
        raise StripeNotConfigured("Stripe is not configured")
    stripe.api_key = settings.stripe_secret_key
    return stripe


# Billing key -> configured Price ID. Built lazily (not at import time) so a
# key added to settings without restarting nothing breaks — read fresh each
# call; these are just attribute lookups, not I/O.
def _price_id(module_key: str) -> str | None:
    return {
        "core": settings.stripe_price_core,
        "select": settings.stripe_price_select,
        "socials": settings.stripe_price_socials,
        "admin": settings.stripe_price_admin,
        "iq": settings.stripe_price_iq,
        "fantasy": settings.stripe_price_fantasy,
    }.get(module_key)


def priced_modules() -> set[str]:
    """Billing keys that currently have a Price ID configured — what the
    Account page should actually offer as subscribable via Checkout."""
    return {m for m in BILLABLE_MODULES if _price_id(m)}


async def _ensure_customer(org) -> str:
    """The club's Stripe Customer id, creating one on first use. Persists it
    onto the org — caller is responsible for committing."""
    if org.stripe_customer_id:
        return org.stripe_customer_id
    client = _client()
    customer = await asyncio.to_thread(
        client.Customer.create,
        name=org.name,
        email=org.contact_email or None,
        metadata={"org_id": str(org.id)},
    )
    org.stripe_customer_id = customer.id
    return customer.id


async def create_checkout_session(org, module_keys: list[str], *, success_url: str, cancel_url: str):
    """One Checkout Session, one Subscription, one line item per module —
    the club's whole selected bundle renews together. Raises ModuleNotPriced
    if any requested module has no configured Price ID (caller should
    validate against priced_modules() first for a clean error, this is the
    defensive backstop)."""
    client = _client()
    missing = [m for m in module_keys if not _price_id(m)]
    if missing:
        raise ModuleNotPriced(missing[0])

    customer_id = await _ensure_customer(org)
    line_items = [{"price": _price_id(m), "quantity": 1} for m in module_keys]

    session = await asyncio.to_thread(
        client.checkout.Session.create,
        customer=customer_id,
        mode="subscription",
        line_items=line_items,
        success_url=success_url,
        cancel_url=cancel_url,
        billing_address_collection="required",  # Stripe Tax needs a location to compute GST
        automatic_tax={"enabled": True},
        subscription_data={"metadata": {"org_id": str(org.id)}},
        metadata={"org_id": str(org.id), "module_keys": ",".join(module_keys)},
    )
    return session


async def retrieve_subscription(subscription_id: str):
    client = _client()
    return await asyncio.to_thread(
        client.Subscription.retrieve, subscription_id, expand=["items.data.price"]
    )


def module_key_for_price(price_id: str) -> str | None:
    """Reverse lookup — which billing module a Stripe Price ID belongs to."""
    for m in BILLABLE_MODULES:
        if _price_id(m) == price_id:
            return m
    return None
