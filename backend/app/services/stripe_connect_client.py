"""Stripe Connect — club-to-member fee payments.

A SEPARATE Stripe integration from services/stripe_client.py (BetterCricket's
own platform billing, one Stripe account for the whole SaaS). Here each club
gets its own Stripe Express connected account, created and onboarded from
this same platform Stripe account/keys (Connect calls just pass
``stripe_account=<connected account id>`` per call — the module-level
``stripe.api_key`` stays the platform secret key throughout, mirroring
stripe_client.py's "set it fresh on every call" pattern).

Every Checkout Session created here is a DIRECT charge on the connected
account (no ``application_fee_amount``) — the money, and Stripe's own
processing fee, are entirely the club's; BetterCricket takes no cut. That's
a deliberate default, not an oversight — add ``application_fee_amount`` to
``create_fee_payment_checkout_session`` if a platform fee is ever wanted.

Connect webhook events are signed with their OWN endpoint secret in the
Stripe dashboard (Connect → Webhooks), never ``settings.stripe_webhook_secret``
(that's the platform-billing endpoint's secret) — see
``construct_connect_webhook_event`` / ``routers/public_stripe_connect.py``.
"""
from __future__ import annotations

import logging

import stripe

from app.config.settings import settings

logger = logging.getLogger(__name__)


class StripeNotConfigured(RuntimeError):
    """Raised when a Stripe Connect call is attempted without api keys
    configured. Callers should turn this into a clean 400/503, never a raw
    SDK traceback."""


def _require_configured() -> None:
    if not settings.stripe_configured:
        raise StripeNotConfigured("Stripe is not configured (STRIPE_SECRET_KEY/STRIPE_PUBLISHABLE_KEY unset)")
    stripe.api_key = settings.stripe_secret_key


async def create_connected_account(*, club_name: str, club_email: str | None, country: str = "AU") -> str:
    """Creates a new Stripe Express connected account for one club. Returns
    the account id (``acct_...``) — callers persist it as
    ``organisations.stripe_connect_account_id``. Onboarding (bank details,
    identity) happens on Stripe's hosted flow via create_account_link, not
    here — this just provisions the empty account."""
    _require_configured()
    account = await stripe.Account.create_async(
        type="express",
        country=country,
        email=club_email or None,
        business_type="non_profit",
        capabilities={
            "card_payments": {"requested": True},
            "transfers": {"requested": True},
        },
    )
    return account.id


async def create_account_link(account_id: str) -> str:
    """The one-time hosted onboarding URL for a connected account — redirect
    the club admin here to enter bank details / verify identity. Expires
    quickly (Stripe's own short TTL), so mint a fresh one per click rather
    than caching."""
    _require_configured()
    link = await stripe.AccountLink.create_async(
        account=account_id,
        refresh_url=settings.stripe_connect_refresh_url,
        return_url=settings.stripe_connect_return_url,
        type="account_onboarding",
    )
    return link.url


async def create_login_link(account_id: str) -> str:
    """A one-time link into the connected account's own (lightweight,
    Express-tier) Stripe Dashboard — only works once onboarding has actually
    completed; raises a stripe.error.InvalidRequestError otherwise, which
    callers should turn into a clean "finish connecting first" message."""
    _require_configured()
    link = await stripe.Account.create_login_link_async(account_id)
    return link.url


async def retrieve_account(account_id: str):
    """Current onboarding/capability status for a connected account — used
    to refresh organisations.stripe_connect_details_submitted/
    charges_enabled/payouts_enabled, both from the account.updated webhook
    and an on-demand admin-side refresh."""
    _require_configured()
    return await stripe.Account.retrieve_async(account_id)


async def create_fee_payment_checkout_session(*, connected_account_id: str, amount_cents: int,
                                              description: str, org_id: str, member_id: str,
                                              season_id: str, kind: str,
                                              success_url: str, cancel_url: str):
    """A one-off (mode=payment, not subscription) Checkout Session created
    DIRECTLY on the connected account — the charge, and Stripe's processing
    fee, land on the club's own Stripe balance. ``metadata`` round-trips
    (org_id, member_id, season_id, kind) so the webhook can record the
    matching fee_payments row with no extra DB lookup, the same pattern the
    platform-billing integration uses for its own Checkout Sessions."""
    _require_configured()
    if amount_cents <= 0:
        raise ValueError("amount_cents must be positive")
    return await stripe.checkout.Session.create_async(
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": settings.stripe_currency,
                "product_data": {"name": description[:250]},
                "unit_amount": amount_cents,
                "tax_behavior": "exclusive",
            },
            "quantity": 1,
        }],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={
            "purpose": "fee_payment", "org_id": str(org_id), "member_id": str(member_id),
            "season_id": str(season_id), "kind": kind,
        },
        stripe_account=connected_account_id,
    )


async def create_merch_checkout_session(*, connected_account_id: str, order_id: str, org_id: str,
                                        line_items: list[dict], success_url: str, cancel_url: str):
    """A one-off Checkout Session for a merch storefront order — one line
    item per cart line, all on the SAME connected account fee payments use
    (one club, one Stripe account, for fees and merch alike). ``line_items``
    is [{name, unit_amount_cents, quantity}]; ``metadata.order_id`` is how
    the webhook finds the pending MerchOrder row to mark paid (see
    services/merch_store.py::mark_order_paid) — the full cart isn't encoded
    in metadata (Stripe's per-value size limit), only the order id."""
    _require_configured()
    if not line_items:
        raise ValueError("line_items must not be empty")
    return await stripe.checkout.Session.create_async(
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": settings.stripe_currency,
                "product_data": {"name": li["name"][:250]},
                "unit_amount": li["unit_amount_cents"],
                "tax_behavior": "exclusive",
            },
            "quantity": li["quantity"],
        } for li in line_items],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"purpose": "merch_order", "org_id": str(org_id), "order_id": str(order_id)},
        stripe_account=connected_account_id,
    )


async def create_event_checkout_session(*, connected_account_id: str, registration_id: str, org_id: str,
                                        description: str, amount_cents: int,
                                        success_url: str, cancel_url: str):
    """A one-off Checkout Session for a priced event registration — same
    connected account fee payments and merch checkout use. ``metadata.
    registration_id`` is how the webhook finds the pending EventRegistration
    row to mark paid (see services/events.py)."""
    _require_configured()
    if amount_cents <= 0:
        raise ValueError("amount_cents must be positive")
    return await stripe.checkout.Session.create_async(
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": settings.stripe_currency,
                "product_data": {"name": description[:250]},
                "unit_amount": amount_cents,
                "tax_behavior": "exclusive",
            },
            "quantity": 1,
        }],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"purpose": "event_registration", "org_id": str(org_id), "registration_id": str(registration_id)},
        stripe_account=connected_account_id,
    )


def construct_connect_webhook_event(payload: bytes, sig_header: str):
    """Verifies the Stripe-Signature header against the Connect endpoint's
    OWN signing secret (distinct from the platform-billing webhook's
    secret). Raises stripe.error.SignatureVerificationError on a bad/missing
    signature — callers must hard-reject (400), never process unverified."""
    if not settings.stripe_connect_webhook_secret:
        raise StripeNotConfigured("Stripe Connect webhook secret not set")
    return stripe.Webhook.construct_event(payload, sig_header, settings.stripe_connect_webhook_secret)
