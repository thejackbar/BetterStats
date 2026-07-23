"""Stripe Connect webhook handlers — the write side behind
routers/public_stripe_connect.py. Mirrors services/stripe_billing.py's shape
(same "verify the signature, trust the event" posture) but for the SEPARATE
Connect integration — never touches organisations.stripe_customer_id/
stripe_subscription_id or the billing_invoices table, which belong to
BetterCricket's own platform billing.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.db import Organisation, FeeMemberSeason, FeePayment, MerchOrder, EventRegistration
from app.services import merch_store

logger = logging.getLogger(__name__)


async def _load_org_by_account(db: AsyncSession, account_id: str) -> Organisation | None:
    return (await db.execute(
        select(Organisation).where(Organisation.stripe_connect_account_id == account_id)
    )).scalar_one_or_none()


async def handle_account_updated(db: AsyncSession, data_object, account_id: str) -> None:
    """Keeps organisations.stripe_connect_{details_submitted,charges_enabled,
    payouts_enabled} in step with Stripe's own view of the connected
    account, so the admin status page reflects reality without needing to
    click "Refresh" after every onboarding step."""
    org = await _load_org_by_account(db, account_id)
    if org is None:
        logger.info("stripe_connect account.updated for unknown account %s", account_id)
        return
    org.stripe_connect_details_submitted = bool(data_object.get("details_submitted"))
    org.stripe_connect_charges_enabled = bool(data_object.get("charges_enabled"))
    org.stripe_connect_payouts_enabled = bool(data_object.get("payouts_enabled"))
    await db.commit()


async def handle_checkout_completed(db: AsyncSession, data_object, account_id: str) -> None:
    """Dispatches by metadata.purpose — the SAME Connect Checkout Session
    shape (fees vs merch) both land on checkout.session.completed, so this
    is the one place that tells them apart. Older sessions created before
    the purpose tag existed have none — treated as a fee payment (the only
    kind that existed before merch storefront shipped)."""
    metadata = data_object.get("metadata") or {}
    purpose = metadata.get("purpose") or "fee_payment"
    if purpose == "merch_order":
        await _handle_merch_checkout_completed(db, data_object, account_id)
    elif purpose == "event_registration":
        await _handle_event_checkout_completed(db, data_object, account_id)
    else:
        await _handle_fee_checkout_completed(db, data_object, account_id)


async def _handle_event_checkout_completed(db: AsyncSession, data_object, account_id: str) -> None:
    """Marks the matching EventRegistration paid. Idempotent — a replayed
    webhook for an already-paid registration is a no-op."""
    metadata = data_object.get("metadata") or {}
    registration_id = metadata.get("registration_id")
    org_id = metadata.get("org_id")
    payment_intent_id = data_object.get("payment_intent")
    if not (registration_id and org_id):
        logger.warning("stripe_connect event checkout.session.completed missing metadata: %s", metadata)
        return

    org = await _load_org_by_account(db, account_id)
    if org is None or str(org.id) != str(org_id):
        logger.warning("stripe_connect event checkout for account %s doesn't match org %s", account_id, org_id)
        return

    registration = await db.get(EventRegistration, uuid.UUID(registration_id))
    if registration is None or registration.organisation_id != org.id:
        logger.warning("stripe_connect event checkout: registration %s not found for org %s", registration_id, org_id)
        return
    if registration.payment_status == "paid":
        return

    registration.payment_status = "paid"
    registration.stripe_checkout_session_id = data_object.get("id")
    registration.stripe_payment_intent_id = payment_intent_id
    await db.commit()


async def _handle_merch_checkout_completed(db: AsyncSession, data_object, account_id: str) -> None:
    """Marks the matching pending MerchOrder paid and turns its line items
    into ordinary 'sold' stock movements — see
    services/merch_store.py::mark_order_paid, which is itself idempotent
    (a no-op if the order isn't still pending_payment)."""
    metadata = data_object.get("metadata") or {}
    order_id = metadata.get("order_id")
    org_id = metadata.get("org_id")
    payment_intent_id = data_object.get("payment_intent")
    if not (order_id and org_id):
        logger.warning("stripe_connect merch checkout.session.completed missing metadata: %s", metadata)
        return

    org = await _load_org_by_account(db, account_id)
    if org is None or str(org.id) != str(org_id):
        logger.warning("stripe_connect merch checkout for account %s doesn't match org %s", account_id, org_id)
        return

    order = (await db.execute(
        select(MerchOrder).where(MerchOrder.id == uuid.UUID(order_id)).options(selectinload(MerchOrder.items))
    )).scalar_one_or_none()
    if order is None or order.organisation_id != org.id:
        logger.warning("stripe_connect merch checkout: order %s not found for org %s", order_id, org_id)
        return

    order.stripe_checkout_session_id = data_object.get("id")
    await merch_store.mark_order_paid(db, order, payment_intent_id=payment_intent_id)
    await db.commit()


async def _handle_fee_checkout_completed(db: AsyncSession, data_object, account_id: str) -> None:
    """Records a member's completed online fee payment as an ordinary
    fee_payments row (source='stripe_connect') so it flows straight into the
    SAME allocate_match_days()/_financials() math every other payment already
    does — no separate ledger. Idempotent on external_ref (the existing
    uq_fee_payment_external_ref unique index from the platform-billing work),
    so a replayed webhook can't double-credit a member."""
    metadata = data_object.get("metadata") or {}
    member_id = metadata.get("member_id")
    season_id = metadata.get("season_id")
    kind = metadata.get("kind") or "membership"
    org_id = metadata.get("org_id")
    payment_intent_id = data_object.get("payment_intent")
    if not (member_id and season_id and org_id and payment_intent_id):
        logger.warning("stripe_connect checkout.session.completed missing metadata: %s", metadata)
        return

    org = await _load_org_by_account(db, account_id)
    if org is None or str(org.id) != str(org_id):
        logger.warning("stripe_connect checkout for account %s doesn't match org %s", account_id, org_id)
        return

    ms = (await db.execute(
        select(FeeMemberSeason).where(
            FeeMemberSeason.member_id == uuid.UUID(member_id),
            FeeMemberSeason.season_id == uuid.UUID(season_id),
        )
    )).scalar_one_or_none()
    if ms is None:
        logger.warning("stripe_connect checkout: no fee_member_season for member %s season %s", member_id, season_id)
        return

    amount_total = data_object.get("amount_total") or 0
    payment = FeePayment(
        member_season_id=ms.id,
        organisation_id=org.id,
        amount=Decimal(amount_total) / Decimal(100),
        paid_at=date.today(),
        kind=kind if kind in ("membership", "match_day") else "membership",
        method="Stripe",
        source="stripe_connect",
        external_ref=f"stripe:{payment_intent_id}",
        notes="Paid online via the member portal",
    )
    db.add(payment)
    try:
        await db.commit()
    except IntegrityError:
        # Already recorded (a replayed webhook hitting uq_fee_payment_external_ref)
        # — not an error, just a no-op.
        await db.rollback()
