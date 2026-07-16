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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.modules import BILLABLE_MODULES, STATUS_ACTIVE, STATUS_PAST_DUE
from app.config.settings import settings
from app.models.db import BillingInvoice, ClubMembership, ModuleActionRequest, Organisation, User
from app.services import discount_coupons, email_service, module_subscriptions, stripe_client
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


def _push_to_twenty(org_id) -> None:
    # Best-effort, mirrors every other subscription-change call site (see
    # club_admin.py::approve_module_request) — never let a Twenty hiccup fail
    # a webhook Stripe expects a fast 2xx from.
    try:
        from app.routers.club_admin import _push_club_to_twenty
        _push_club_to_twenty(org_id)
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
    _push_to_twenty(org.id)


async def handle_invoice_paid(db: AsyncSession, invoice: dict) -> None:
    """invoice.paid — covers both the very first invoice and every renewal.
    Rolls each subscribed module's renewal_date forward, reactivates a module
    that had gone past_due, and records the invoice for the club's own Billing
    history (idempotent on stripe_invoice_id — a replayed event just re-upserts
    the same row)."""
    subscription_id = invoice.get("subscription")
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

    now = datetime.now(timezone.utc)
    for key in billing_keys:
        module_subscriptions.set_status_billing(org, key, STATUS_ACTIVE, renewal_date=renewal_date, now=now)
    await _upsert_invoice(db, org, invoice, now)
    await db.commit()

    # Best-effort receipt to the club's primary admin — covers the first
    # invoice on a brand new subscribe, an add-on purchase, and every
    # renewal alike, since they all land here. Never allowed to fail the
    # webhook itself (entitlement above has already committed): a
    # deliverability hiccup should show up in logs, not roll back a payment
    # Stripe has already collected.
    try:
        await _send_invoice_receipt(db, org, invoice)
    except Exception:
        logger.exception("Stripe invoice.paid: receipt email failed for org %s, invoice %s", org.id, invoice.get("id"))


async def _primary_admin(db: AsyncSession, org_id) -> User | None:
    return (await db.execute(
        select(User)
        .join(ClubMembership, ClubMembership.user_id == User.id)
        .where(
            ClubMembership.club_id == org_id,
            ClubMembership.role == "club_admin",
            ClubMembership.is_primary_admin.is_(True),
        )
        .limit(1)
    )).scalar_one_or_none()


def _receipt_email_body(club_name: str, amount: str, currency: str,
                         line_descriptions: list[str], hosted_invoice_url: str | None) -> tuple[str, str]:
    """Plain inline-styled HTML (matches trial_lifecycle.py's _shell pattern —
    a system-level transactional send, not a BetterComms campaign, so no
    club-shell/unsubscribe wrapper)."""
    items_html = "".join(f'<li style="margin:0 0 4px">{d}</li>' for d in line_descriptions) or ""
    items_block = (
        f'<ul style="font-size:14px;line-height:1.5;margin:0 0 14px;padding-left:18px">{items_html}</ul>'
        if items_html else ""
    )
    cta = (
        f'<p style="margin:24px 0"><a href="{hosted_invoice_url}" '
        'style="display:inline-block;background:#16c784;color:#fff;text-decoration:none;'
        'padding:10px 20px;border-radius:6px;font-size:14px;font-weight:bold">View invoice</a></p>'
        if hosted_invoice_url else ""
    )
    html = f"""
    <div style="font-family:Arial,Helvetica,sans-serif;max-width:480px;margin:0 auto;padding:24px;color:#1a1a1a">
      <p style="font-size:14px;color:#555">BetterCricket</p>
      <p style="font-size:14px;line-height:1.5;margin:0 0 14px">
        Payment received for {club_name} — <strong>{currency} ${amount}</strong>.
      </p>
      {items_block}
      {cta}
      <p style="font-size:12px;color:#888;margin-top:24px">
        You're getting this as {club_name}'s primary admin. Your full billing history is always
        available on the Account page in BetterCricket.
      </p>
    </div>
    """
    text_lines = [f"Payment received for {club_name} — {currency} ${amount}.", *line_descriptions]
    if hosted_invoice_url:
        text_lines.append(f"View invoice: {hosted_invoice_url}")
    return html, "\n\n".join(text_lines)


async def _send_invoice_receipt(db: AsyncSession, org: Organisation, invoice: dict) -> None:
    """Emails the club's primary admin a receipt for a Stripe invoice that
    was just paid — the only feedback a club gets for the add-on-to-
    existing-subscription flow, which charges synchronously with no Stripe
    redirect at all (routers/billing.py), and a welcome confirmation for a
    brand new subscribe or a routine renewal alike. Silently no-ops when the
    club has no primary admin on record (shouldn't happen in practice —
    every club gets one at registration — but this is a best-effort extra,
    not something to error out over)."""
    admin = await _primary_admin(db, org.id)
    if not admin or not admin.email:
        return
    amount_paid = (invoice.get("amount_paid") or 0) / 100
    currency = (invoice.get("currency") or "aud").upper()
    hosted_url = invoice.get("hosted_invoice_url")
    lines = (invoice.get("lines") or {}).get("data") or []
    descriptions = [ln.get("description") for ln in lines if ln.get("description")]
    html, text_body = _receipt_email_body(org.name, f"{amount_paid:.2f}", currency, descriptions, hosted_url)
    msg = email_service.EmailMessage(
        to_email=admin.email,
        to_name=admin.display_name or admin.username,
        subject=f"Payment received — {currency} ${amount_paid:.2f}",
        html=html,
        text=text_body,
        from_email=settings.email_from_address,
        from_name=settings.email_from_name,
        reply_to=settings.email_reply_to,
        configuration_set=(settings.ses_configuration_set_transactional or "").strip() or None,
    )
    result = await email_service.get_email_provider().send(msg)
    if not result.ok:
        logger.warning("Stripe billing: receipt email failed for org %s: %s", org.id, result.error)


async def handle_invoice_payment_failed(db: AsyncSession, invoice: dict) -> None:
    """invoice.payment_failed — a grace-period signal, not an instant cutoff:
    moves the affected modules to past_due (see ACTIVE_STATUSES in
    auth/modules.py — past_due still keeps them live) rather than cutting the
    club off immediately, giving them a chance to update their card before
    Stripe's own dunning schedule gives up and fires
    customer.subscription.deleted."""
    subscription_id = invoice.get("subscription")
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
    await _upsert_invoice(db, org, invoice, now)
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
    _push_to_twenty(org.id)


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


async def _upsert_invoice(db: AsyncSession, org: Organisation, invoice: dict, now: datetime) -> None:
    """Records ONE Stripe invoice event for the club's Billing History.
    line_items is read straight off Stripe's own invoice lines, not
    recomputed from our pricing tables — a renewal invoice bills every
    currently-held module, but an add-on invoice (adding a module to an
    already-live subscription, see stripe_client.add_modules_to_subscription)
    only bills the newly-added one(s), so re-deriving "what's on this
    invoice" from the subscription's full held-module set would misrepresent
    a partial invoice as a full one."""
    stripe_invoice_id = invoice.get("id")
    if not stripe_invoice_id:
        return
    row = (await db.execute(
        select(BillingInvoice).where(BillingInvoice.stripe_invoice_id == stripe_invoice_id)
    )).scalar_one_or_none()
    if row is None:
        row = BillingInvoice(organisation_id=org.id, stripe_invoice_id=stripe_invoice_id)
        db.add(row)
    row.stripe_subscription_id = invoice.get("subscription")
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
    row.updated_at = now
