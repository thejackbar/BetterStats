"""Stripe webhook business logic — the write-side counterpart to
services/billing_pricing.py's read-only quote math.

Split out of routers/public_stripe.py (a thin HTTP + signature-verification
layer) the same way services/ses_events.py sits under routers/public_ses.py.
Every handler here is idempotent (safe to replay the exact same Stripe event,
which Stripe's own retry behaviour guarantees will happen sooner or later) and
ends in the SAME write module.set_status_billing/remove_billing calls the
existing super-admin "approve a subscribe/cancel request" flow already makes
(see routers/club_admin.py::approve_module_request) — a paid Stripe
subscription is just another way of reaching that same end state, not a
separate entitlement path.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.modules import BILLABLE_MODULES, STATUS_ACTIVE, STATUS_PAST_DUE
from app.models.db import BillingInvoice, ModuleActionRequest, Organisation
from app.services import discount_coupons, module_subscriptions, stripe_client
from app.services.stripe_client import epoch_to_date, epoch_to_datetime

logger = logging.getLogger(__name__)


async def _load_org(db: AsyncSession, org_id) -> Organisation | None:
    """org_id arrives as a plain string from Stripe's client_reference_id /
    metadata — parse it to a real uuid.UUID before handing it to db.get()
    rather than relying on the ORM/driver to coerce a bare string for a UUID
    PK column (untested against a live DB; explicit is cheap and matches the
    pattern routers/public_square.py already uses for the same situation)."""
    if not org_id:
        return None
    try:
        org_uuid = uuid.UUID(str(org_id))
    except (ValueError, TypeError, AttributeError):
        logger.warning("Stripe billing: invalid org_id=%r", org_id)
        return None
    try:
        return await db.get(
            Organisation, org_uuid,
            options=[selectinload(Organisation.module_subscriptions)],
        )
    except Exception:
        logger.exception("Stripe billing: could not load org_id=%s", org_uuid)
        return None


def _invoice_subscription_id(invoice: dict) -> str | None:
    """The subscription an invoice belongs to. Newer Stripe API versions
    (found live — the account's configured default is newer than this SDK's
    2024-06-20) nest this under invoice.parent.subscription_details.subscription
    and the top-level invoice.subscription field is simply absent (None, not
    missing-but-falsy in some other way) — every invoice.paid /
    invoice.payment_failed webhook was silently no-op'ing ("unknown
    subscription=None") because of this, including the receipt email these
    handlers send. Checks both shapes so it works regardless of which API
    version the Stripe account is actually sending webhooks at."""
    direct = invoice.get("subscription")
    if direct:
        return direct
    parent = invoice.get("parent") or {}
    return ((parent.get("subscription_details") or {}).get("subscription"))


async def _load_org_by_subscription(db: AsyncSession, subscription_id: str | None) -> Organisation | None:
    if not subscription_id:
        return None
    return (await db.execute(
        select(Organisation)
        .where(Organisation.stripe_subscription_id == subscription_id)
        .options(selectinload(Organisation.module_subscriptions))
    )).scalar_one_or_none()


async def _resolve_org_for_subscription(db: AsyncSession, subscription_id: str | None):
    """Loads the org owning a subscription, preferring our own indexed
    stripe_subscription_id (no Stripe call needed) but falling back to
    fetching the subscription and reading its own metadata.org_id. Stripe
    doesn't guarantee webhook delivery order — invoice.paid for the very
    first invoice can arrive before checkout.session.completed has had a
    chance to stamp stripe_subscription_id onto the org, which would
    otherwise silently drop that invoice. Self-heals by stamping it here too.
    Returns (org, subscription_or_None) — the subscription is returned when
    already fetched here so the caller doesn't fetch it twice."""
    org = await _load_org_by_subscription(db, subscription_id)
    if org is not None or not subscription_id:
        return org, None
    try:
        sub = await stripe_client.retrieve_subscription(subscription_id)
    except Exception:
        logger.exception("Stripe: could not retrieve subscription %s", subscription_id)
        return None, None
    org = await _load_org(db, (sub.get("metadata") or {}).get("org_id"))
    if org is not None:
        org.stripe_subscription_id = subscription_id
    return org, sub


def _parse_billing_keys(metadata) -> list[str]:
    raw = (metadata or {}).get("billing_keys") or ""
    return [k for k in raw.split(",") if k in BILLABLE_MODULES]


def _push_to_twenty(org_id, crm_trigger: Optional[str] = None) -> None:
    # Best-effort, mirrors every other subscription-change call site (see
    # club_admin.py::approve_module_request) — never let a Twenty hiccup fail
    # a webhook Stripe expects a fast 2xx from. ``crm_trigger`` threads
    # through to _push_club_to_twenty (one of crm_rules.TRIGGERS' subscription
    # keys) so a real Stripe payment event keeps BetterCricket's own
    # (super-admin-configurable) CRM pipeline in lockstep too, not just Twenty.
    try:
        from app.routers.club_admin import _push_club_to_twenty
        _push_club_to_twenty(org_id, crm_trigger=crm_trigger)
    except Exception:
        logger.exception("Stripe billing: Twenty push failed")


async def _record_action(db: AsyncSession, org: Organisation, module_key: str, kind: str, note: str, now: datetime) -> None:
    db.add(ModuleActionRequest(
        organisation_id=org.id, module_key=module_key, kind=kind, status="completed",
        source="stripe", note=note, completed_at=now,
    ))


async def handle_checkout_completed(db: AsyncSession, session: dict) -> None:
    """checkout.session.completed, mode=subscription — the moment a Primary
    Admin has actually paid. Grants entitlement immediately, using the
    freshly-created subscription's current period end as the renewal date,
    rather than waiting on the invoice.paid event that follows moments later."""
    if session.get("mode") != "subscription":
        return
    org_id = session.get("client_reference_id") or (session.get("metadata") or {}).get("org_id")
    org = await _load_org(db, org_id)
    if org is None:
        logger.warning("Stripe checkout.session.completed: unknown org_id=%r", org_id)
        return

    billing_keys = _parse_billing_keys(session.get("metadata"))
    if session.get("customer"):
        org.stripe_customer_id = session["customer"]
    subscription_id = session.get("subscription")
    if subscription_id:
        org.stripe_subscription_id = subscription_id

    renewal_date = None
    if subscription_id:
        try:
            sub = await stripe_client.retrieve_subscription(subscription_id)
            renewal_date = epoch_to_date(sub.get("current_period_end"))
        except Exception:
            logger.exception("Stripe: could not retrieve subscription %s for renewal date", subscription_id)

    now = datetime.now(timezone.utc)
    for key in billing_keys:
        module_subscriptions.set_status_billing(org, key, STATUS_ACTIVE, renewal_date=renewal_date, now=now)
        await _record_action(db, org, key, "subscribe", "Paid via Stripe Checkout", now)

    # A discount-coupon redeemed alongside this signup (see
    # discount_coupons.redeem_for_new_signup) was recorded 'pending' at
    # Checkout Session creation — this is the confirmation that the
    # subscription it was meant for actually got created.
    redemption_id = (session.get("metadata") or {}).get("coupon_redemption_id")
    if redemption_id and subscription_id:
        await discount_coupons.mark_redemption_confirmed(db, redemption_id, subscription_id)

    await db.commit()
    # A completed Stripe Checkout is a genuine conversion — the strongest
    # possible "became a customer" signal, so the CRM deal moves to Won
    # immediately rather than waiting on any periodic refresh.
    _push_to_twenty(org.id, crm_trigger="subscription_won")


async def handle_invoice_paid(db: AsyncSession, invoice: dict) -> None:
    """invoice.paid — covers both the very first invoice and every renewal.
    Rolls each subscribed module's renewal_date forward, reactivates a module
    that had gone past_due, and records the invoice for the club's own Billing
    history (idempotent on stripe_invoice_id — a replayed event just re-upserts
    the same row)."""
    subscription_id = _invoice_subscription_id(invoice)
    org, sub = await _resolve_org_for_subscription(db, subscription_id)
    if org is None:
        logger.warning("Stripe invoice.paid: unknown subscription=%r", subscription_id)
        return

    billing_keys: list[str] = []
    renewal_date = epoch_to_date(invoice.get("period_end"))
    try:
        if sub is None:
            sub = await stripe_client.retrieve_subscription(subscription_id)
        billing_keys = _parse_billing_keys(sub.get("metadata"))
        renewal_date = epoch_to_date(sub.get("current_period_end")) or renewal_date
    except Exception:
        logger.exception("Stripe: could not retrieve subscription %s for invoice %s", subscription_id, invoice.get("id"))

    org_id = org.id
    now = datetime.now(timezone.utc)
    for key in billing_keys:
        module_subscriptions.set_status_billing(org, key, STATUS_ACTIVE, renewal_date=renewal_date, now=now)
    await _upsert_invoice(db, org, invoice, now, sub=sub)
    try:
        await db.commit()
    except IntegrityError:
        # The synchronous add-on-purchase request (routers/billing.py) can
        # race this SAME invoice event and win — found live. Both write the
        # identical entitlement from the same Stripe data, so losing this
        # race is benign, but a bare rollback would also lose the
        # BillingInvoice write for Billing History, which nothing else
        # redoes. Re-fetch a fresh org (the rolled-back one's attributes
        # aren't safe to touch — SQLAlchemy expires objects on rollback) and
        # record just the invoice; module_subscriptions needs no retry, the
        # winner already wrote it.
        await db.rollback()
        logger.info(
            "Stripe invoice.paid: entitlement for org %s already granted concurrently — "
            "re-recording the invoice only", org_id,
        )
        org = await _load_org(db, org_id)
        if org is None:
            return
        await _upsert_invoice(db, org, invoice, now, sub=sub)
        await db.commit()


async def handle_invoice_payment_failed(db: AsyncSession, invoice: dict) -> None:
    """invoice.payment_failed — a grace-period signal, not an instant cutoff:
    moves the affected modules to past_due (see ACTIVE_STATUSES in
    auth/modules.py — past_due still keeps them live) rather than cutting the
    club off immediately, giving them a chance to update their card before
    Stripe's own dunning schedule gives up and fires
    customer.subscription.deleted."""
    subscription_id = _invoice_subscription_id(invoice)
    org, sub = await _resolve_org_for_subscription(db, subscription_id)
    if org is None:
        logger.warning("Stripe invoice.payment_failed: unknown subscription=%r", subscription_id)
        return

    billing_keys: list[str] = []
    try:
        if sub is None:
            sub = await stripe_client.retrieve_subscription(subscription_id)
        billing_keys = _parse_billing_keys(sub.get("metadata"))
    except Exception:
        logger.exception("Stripe: could not retrieve subscription %s for failed invoice %s", subscription_id, invoice.get("id"))

    now = datetime.now(timezone.utc)
    for key in billing_keys:
        module_subscriptions.set_status_billing(org, key, STATUS_PAST_DUE, now=now)
    await _upsert_invoice(db, org, invoice, now, sub=sub)
    await db.commit()
    _push_to_twenty(org.id)


async def handle_subscription_deleted(db: AsyncSession, subscription: dict) -> None:
    """customer.subscription.deleted — Stripe's own dunning gave up, or the
    subscription was cancelled directly in Stripe (outside our own in-app
    cancel flow). Drops every module the subscription covered, same end state
    as the self-service /modules/{key}/cancel route."""
    org = await _load_org_by_subscription(db, subscription.get("id"))
    if org is None:
        logger.warning("Stripe customer.subscription.deleted: unknown subscription=%r", subscription.get("id"))
        return

    billing_keys = _parse_billing_keys(subscription.get("metadata"))
    now = datetime.now(timezone.utc)
    for key in billing_keys:
        module_subscriptions.remove_billing(org, key, now=now)
        await _record_action(db, org, key, "cancel", "Subscription cancelled in Stripe", now)
    org.stripe_subscription_id = None
    await db.commit()
    # 'subscription_cancelled' only fires (per the configured automation rule)
    # if the org is left holding nothing billable at all (a still-trialing or
    # otherwise granted module elsewhere means the deal stays exactly where it is).
    _push_to_twenty(org.id, crm_trigger="subscription_cancelled")


async def sweep_dangling_stripe_subscriptions(db: AsyncSession) -> list[str]:
    """One-off repair, run on API boot: before this module's cancel paths
    started clearing stripe_subscription_id themselves (see
    routers/club_admin.py::_cancel_stripe_subscription_if_nothing_held),
    module_subscriptions.remove_billing was DB-only — a club that cancelled
    every module it held kept a stale stripe_subscription_id, which routed
    its Account page into the coupon-free "add modules to an already-live
    subscription" checkout branch forever instead of falling back to a
    normal new-signup checkout. Self-heals any club already stuck in that
    state; idempotent (a no-op once nothing is left to fix). Returns the
    affected org ids."""
    from stripe import error as stripe_error

    from app.auth.modules import account_plan_status

    orgs = (await db.execute(
        select(Organisation)
        .where(Organisation.stripe_subscription_id.isnot(None))
        .options(selectinload(Organisation.module_subscriptions))
    )).scalars().all()
    affected: list[str] = []
    for org in orgs:
        if any(r["status"] == "subscribed" for r in account_plan_status(org)):
            continue
        try:
            await stripe_client.cancel_subscription(org.stripe_subscription_id)
        except (stripe_client.StripeNotConfigured, stripe_error.InvalidRequestError):
            pass  # nothing configured, or Stripe already considers it gone — either way, clear our side
        except stripe_error.StripeError:
            logger.exception(
                "Stripe subscription sweep: could not cancel %s for org %s", org.stripe_subscription_id, org.id
            )
            continue
        org.stripe_subscription_id = None
        affected.append(str(org.id))
    if affected:
        await db.commit()
    return affected


async def _upsert_invoice(db: AsyncSession, org: Organisation, invoice: dict, now: datetime,
                           sub: dict | None = None) -> None:
    """Records ONE Stripe invoice event for the club's Billing History.
    line_items is read straight off Stripe's own invoice lines, not
    recomputed from our pricing tables — a renewal invoice bills every
    currently-held module, but an add-on invoice (adding a module to an
    already-live subscription, see stripe_client.add_modules_to_subscription)
    only bills the newly-added one(s), so re-deriving "what's on this
    invoice" from the subscription's full held-module set would misrepresent
    a partial invoice as a full one.

    ``sub`` (the subscription dict, when the caller already has it) is
    where the discount breakdown lives — stripe_client.create_checkout_session
    stamps bundle_discount_cents/coupon_code/coupon_discount_cents onto the
    subscription's metadata at checkout time. Only copied onto THIS invoice
    when total_discount_amounts shows it actually had a discount applied —
    the bundle discount and a duration=once coupon only ever apply to the
    first invoice, and the subscription's metadata still mentioning them
    doesn't mean a later renewal invoice got them too."""
    stripe_invoice_id = invoice.get("id")
    if not stripe_invoice_id:
        return
    row = (await db.execute(
        select(BillingInvoice).where(BillingInvoice.stripe_invoice_id == stripe_invoice_id)
    )).scalar_one_or_none()
    if row is None:
        row = BillingInvoice(organisation_id=org.id, stripe_invoice_id=stripe_invoice_id)
        db.add(row)
    row.stripe_subscription_id = _invoice_subscription_id(invoice)
    row.status = invoice.get("status") or "open"
    row.amount_due = invoice.get("amount_due") or 0
    row.amount_paid = invoice.get("amount_paid") or 0
    row.currency = invoice.get("currency") or "aud"
    row.period_start = epoch_to_datetime(invoice.get("period_start"))
    row.period_end = epoch_to_datetime(invoice.get("period_end"))
    row.hosted_invoice_url = invoice.get("hosted_invoice_url")
    row.invoice_pdf = invoice.get("invoice_pdf")
    lines = (invoice.get("lines") or {}).get("data") or []
    if lines:
        row.line_items = [
            {"name": ln.get("description") or "", "price": (ln.get("amount") or 0) / 100}
            for ln in lines
        ]

    if invoice.get("total_discount_amounts") and sub:
        meta = sub.get("metadata") or {}
        try:
            row.bundle_discount_cents = int(meta.get("bundle_discount_cents") or 0)
        except (TypeError, ValueError):
            row.bundle_discount_cents = 0
        row.coupon_code = meta.get("coupon_code") or None
        try:
            row.coupon_discount_cents = int(meta.get("coupon_discount_cents") or 0)
        except (TypeError, ValueError):
            row.coupon_discount_cents = 0

    # Best-effort — never allowed to block recording the invoice itself.
    pi_id = stripe_client.invoice_payment_intent_id(invoice)
    if pi_id:
        try:
            pi = await stripe_client.retrieve_payment_intent(pi_id)
            pm = pi.get("payment_method")
            if isinstance(pm, dict):
                row.payment_method_type, row.payment_method_summary = stripe_client.describe_payment_method(pm)
        except Exception:
            logger.exception("Stripe billing: could not fetch payment method for invoice %s", stripe_invoice_id)

    row.updated_at = now
