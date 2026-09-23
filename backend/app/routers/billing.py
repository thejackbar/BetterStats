"""Club-facing Stripe Checkout billing (Account page).

Two things a Primary Admin does here: preview what they're about to buy
(``/quote`` — no charge made) and actually buy it (``/checkout-session`` —
either creates a real Stripe Checkout Session, or adds items directly to an
existing subscription, see below). Both depend on
``require_billing_checkout_enabled`` — see platform_settings.py — so neither
does anything reachable by a real club until a super admin switches the flag
on, no matter how long this router has been merged. ``/invoices`` (billing
history) is deliberately NOT gated by the flag — a club that has already paid
should always be able to see its own invoices, even if the flag is later
switched off for new signups.

Two distinct paths, chosen by whether the club already has a live Stripe
subscription (``club.stripe_subscription_id``):

- **No subscription yet** — a normal Checkout Session (``price_for``: Core +
  selected modules, the bundle discount applies, redirects to Stripe to
  collect payment details).
- **Already subscribed** — adding module(s) to the EXISTING subscription
  (``price_for_addon``: no Core line — already covered — and no bundle
  discount, per direct instruction: the discount is an initial-subscribe
  incentive, not something a later add-on should also get). There's nothing
  new to collect (the card is already on file), so this never redirects to
  Stripe — it charges the prorated amount for whatever's left of the current
  billing period immediately, synchronously, and returns the club straight to
  Subscribed with no round-trip through Stripe's hosted page. See
  stripe_client.preview_add_modules / add_modules_to_subscription — the
  proration math is Stripe's own, not something we compute ourselves.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from stripe import error as stripe_error

from app.auth.modules import BILLABLE_MODULES, STATUS_ACTIVE, account_plan_status
from app.models.db import BillingInvoice, ClubMembership, Organisation, User, get_db
from app.routers.auth import get_current_user, get_current_club, require_super_admin
from app.services import billing_address, billing_pricing, discount_coupons, invoice_billing, module_subscriptions, platform_settings, stripe_client
from app.services.platform_settings import require_billing_checkout_enabled

router = APIRouter(prefix="/club-admin/billing", tags=["club-admin-billing"])
logger = logging.getLogger(__name__)


class QuoteIn(BaseModel):
    module_keys: List[str] = []
    coupon_code: Optional[str] = None


# The ONE copy of the coupon maths now lives in billing_pricing, shared with the
# invoice-billing path (services/invoice_billing.py) so an emailed invoice and a
# Checkout Session discount the same selection identically.
_apply_coupon_to_quote = billing_pricing.apply_coupon_to_quote


# Moved to services/billing_address.py so the invoice-billing job (which has no
# request) can build the same Stripe Customer address. Aliased so nothing that
# reached for the router's names breaks.
_country_iso = billing_address.country_iso
_stripe_address = billing_address.stripe_address


def _validate_keys(module_keys: List[str]) -> list[str]:
    keys = sorted(set(module_keys or []))
    bad = [k for k in keys if k not in billing_pricing.CHECKOUT_MODULE_NAMES]
    if bad:
        raise HTTPException(status_code=422, detail=f"Unknown module(s): {', '.join(bad)}")
    return keys


def _addon_keys(keys: list[str]) -> list[str]:
    # 'core' is never a real add-on selection — it's always already covered
    # once a club has a live subscription (the very first checkout always
    # included it), and the frontend stops showing its checkbox once
    # subscribed anyway. Filtered defensively here too.
    return [k for k in keys if k != "core"]


async def _require_primary_or_super_admin(db: AsyncSession, current_user: User, club: Organisation) -> None:
    """Same gate /checkout-session already enforces inline — factored out
    here since payment-method management needs it across three routes."""
    m = (await db.execute(
        select(ClubMembership).where(ClubMembership.user_id == current_user.id)
    )).scalar_one_or_none()
    is_super = bool(m and m.role == "super_admin")
    if not is_super and not (m and m.club_id == club.id and m.role == "club_admin" and m.is_primary_admin):
        raise HTTPException(status_code=403, detail="Only the club's primary admin can manage payment methods")


def _with_core(keys: list[str]) -> list[str]:
    # billing_pricing.price_for always force-includes Core as a line item
    # regardless of whether the frontend's checkbox for it was ticked (a
    # never-subscribed club is always buying Core alongside anything else) —
    # a coupon's module-coverage check needs to see the same set that's
    # actually being priced, not just the raw selection.
    return keys if "core" in keys else [*keys, "core"]


@router.post("/quote", dependencies=[Depends(require_billing_checkout_enabled)])
async def get_quote(
    body: QuoteIn,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """The invoice preview shown before a Primary Admin commits to checkout.
    Any club admin can preview; only the primary admin can actually check out
    (see /checkout-session)."""
    keys = _validate_keys(body.module_keys)
    if (club.billing_method or invoice_billing.METHOD_CARD) == invoice_billing.METHOD_INVOICE:
        # The same numbers the invoice will carry — see invoice_billing.plan_invoice.
        try:
            plan = await invoice_billing.plan_invoice(db, club, keys, body.coupon_code)
        except invoice_billing.InvoiceBillingError as e:
            raise HTTPException(status_code=e.status, detail=str(e))
        return invoice_billing.plan_out(plan)
    if club.stripe_subscription_id:
        try:
            preview = await stripe_client.preview_add_modules(db, club.stripe_subscription_id, _addon_keys(keys))
        except stripe_client.StripeNotConfigured:
            raise HTTPException(status_code=503, detail="Online billing isn't configured yet.")
        except stripe_error.StripeError as e:
            raise HTTPException(status_code=502, detail=str(e) or "Could not price this change")
        return {"mode": "add_to_existing", **preview}
    schedule = await platform_settings.get_bundle_discount_schedule(db)
    quote = billing_pricing.price_for(keys, schedule=schedule)
    if body.coupon_code:
        try:
            coupon = await discount_coupons.validate_redemption(
                db, body.coupon_code, club, is_new_signup=True, candidate_module_keys=_with_core(keys),
            )
        except discount_coupons.CouponError as e:
            raise HTTPException(status_code=422, detail=str(e))
        quote = _apply_coupon_to_quote(quote, coupon)
    return {"mode": "new_subscription", **quote}


@router.post("/checkout-session", dependencies=[Depends(require_billing_checkout_enabled)])
async def create_checkout_session(
    body: QuoteIn,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    keys = _validate_keys(body.module_keys)
    if not keys:
        raise HTTPException(status_code=422, detail="Select at least one module")

    m = (await db.execute(
        select(ClubMembership).where(ClubMembership.user_id == current_user.id)
    )).scalar_one_or_none()
    is_super = bool(m and m.role == "super_admin")
    if not is_super and not (m and m.club_id == club.id and m.role == "club_admin" and m.is_primary_admin):
        raise HTTPException(status_code=403, detail="Only the club's primary admin can subscribe")

    if (club.billing_method or invoice_billing.METHOD_CARD) == invoice_billing.METHOD_INVOICE:
        # A club that elected to be invoiced must not also end up on a card
        # subscription — the two would bill the same modules twice.
        raise HTTPException(
            status_code=409,
            detail="This club pays by invoice. Request an invoice instead, or switch the club back to card payments.",
        )

    # Never let a checkout re-buy something the club already pays for — the
    # quote/UI should already prevent this, but it's cheap to enforce here too.
    plan_by_key = {row["module"]: row for row in account_plan_status(club)}
    already_subscribed = [k for k in keys if not plan_by_key.get(k, {}).get("can_subscribe", True)]
    if already_subscribed:
        raise HTTPException(
            status_code=409,
            detail=f"Already subscribed: {', '.join(already_subscribed)}",
        )

    if club.stripe_subscription_id:
        addon_keys = _addon_keys(keys)
        if not addon_keys:
            raise HTTPException(status_code=422, detail="Select at least one module to add")
        existing_keys = [k for k in BILLABLE_MODULES if plan_by_key.get(k, {}).get("status") == "subscribed"]
        try:
            sub = await stripe_client.add_modules_to_subscription(
                db, club.stripe_subscription_id, existing_keys, addon_keys,
            )
        except stripe_client.StripeNotConfigured:
            raise HTTPException(status_code=503, detail="Online billing isn't configured yet. Contact the BetterCricket team to subscribe.")
        except stripe_error.StripeError as e:
            if stripe_client.is_missing_payment_method_error(e):
                # No dead end: bounce the club to a Stripe-hosted setup-mode
                # Checkout Session to add a card (no charge), then redirect
                # back to retry this same add-on purchase — see
                # stripe_client.create_setup_session's docstring.
                setup = await stripe_client.create_setup_session(club.stripe_customer_id)
                return {"needs_payment_method": True, "url": setup.url}
            raise HTTPException(status_code=502, detail=str(e) or "Could not add the module(s)")

        # No Checkout Session happened for this path, so there's no
        # checkout.session.completed webhook to grant entitlement — do it
        # synchronously here, same renewal_date Stripe just reported back.
        # The invoice.paid webhook for this SAME charge can genuinely race
        # this request (found live: it can land, and commit, before this
        # handler's own commit does) — when the module already holds a row,
        # both writers just UPDATE it with the same values, harmless. But
        # for a module with NO row yet, both racing writers see "nothing
        # there" and both try to INSERT, and the DB's uq_org_module
        # constraint lets only one through — Postgres itself is the
        # correctness backstop here, not application logic. The loser isn't
        # wrong, just late: the winner (whichever request it was) already
        # wrote the identical end state from the same Stripe data, so this
        # is a benign double-write, not a real conflict — no retry needed.
        renewal_date = stripe_client.epoch_to_date(sub.get("current_period_end"))
        now = datetime.now(timezone.utc)
        for key in addon_keys:
            module_subscriptions.set_status_billing(club, key, STATUS_ACTIVE, renewal_date=renewal_date, now=now)
            module_subscriptions.set_billing_source(club, key, invoice_billing.SOURCE_STRIPE, now=now)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            logger.info(
                "billing add-on: entitlement for %s already granted concurrently (likely the invoice.paid "
                "webhook winning the race) — treating as success", addon_keys,
            )
        # An existing club buying more modules is a win, and this path never
        # touches Stripe Checkout — so there is no checkout.session.completed
        # webhook behind it to move the CRM deal for us. Fired here, with the
        # modules just paid for, so the deal is recorded at what was bought
        # rather than at everything the club now holds; the rep who earned the
        # club is carried onto the new deal (see
        # crm.sync_platform_deal_for_club) so an upsell pays commission.
        from app.routers.club_admin import _sync_club_to_crm
        _sync_club_to_crm(club.id, crm_trigger="subscription_won",
                          won_module_keys=list(addon_keys))
        return {"added": True, "modules": addon_keys}

    schedule = await platform_settings.get_bundle_discount_schedule(db)

    redemption_id = None
    extra_coupon_id = None
    extra_stackable = False
    extra_coupon_code = None
    extra_coupon_off = None
    if body.coupon_code:
        try:
            redeemed = await discount_coupons.redeem_for_new_signup(
                db, body.coupon_code, club, _with_core(keys), current_user,
            )
        except discount_coupons.CouponError as e:
            raise HTTPException(status_code=422, detail=str(e))
        redemption_id = redeemed["redemption_id"]
        extra_coupon_id = redeemed["stripe_coupon_id"]
        extra_stackable = redeemed["stackable_with_bundle"]
        extra_coupon_code = redeemed["coupon"].code
        # Always computed (not just when stacking) — needed to combine with
        # the bundle discount when stacking, and either way it's what gets
        # recorded on our own billing_invoices row for reporting (see
        # stripe_billing._upsert_invoice). Same math /quote's preview uses
        # (_apply_coupon_to_quote), so what gets charged matches what was
        # previewed.
        preview_quote = billing_pricing.price_for(keys, schedule=schedule)
        extra_coupon_off = _apply_coupon_to_quote(preview_quote, redeemed["coupon"])["coupon"]["amount_off"]

    try:
        session = await stripe_client.create_checkout_session(
            db,
            org_id=club.id,
            billing_keys=keys,
            club_name=club.name,
            customer_id=club.stripe_customer_id,
            # The club's own contact address when it has one, so the Stripe
            # Customer represents the club rather than whichever admin
            # happened to run the checkout — falls back to the submitting
            # admin's email for a brand new self-serve club, which rarely
            # has contact_email set yet.
            customer_email=club.contact_email or current_user.email,
            customer_address=_stripe_address(club),
            discount_schedule=schedule,
            extra_coupon_id=extra_coupon_id,
            extra_stackable=extra_stackable,
            extra_coupon_code=extra_coupon_code,
            extra_coupon_off_dollars=extra_coupon_off,
            coupon_redemption_id=redemption_id,
        )
    except stripe_client.StripeNotConfigured:
        if redemption_id:
            # The redemption was recorded before this Stripe call — free the
            # club's one-time slot back up so a config issue on our side
            # doesn't permanently burn their code.
            await discount_coupons.revoke_redemption(db, redemption_id)
        raise HTTPException(status_code=503, detail="Online billing isn't configured yet. Contact the BetterCricket team to subscribe.")
    except stripe_error.StripeError as e:
        if redemption_id:
            await discount_coupons.revoke_redemption(db, redemption_id)
        # Mirrors the square_client.SquareError handling elsewhere (merch.py) —
        # a bad Stripe response is an upstream failure, not ours, and its raw
        # SDK exception shouldn't leak to the client as an unhandled 500.
        raise HTTPException(status_code=502, detail=str(e) or "Stripe checkout could not be started")

    return {"url": session["url"]}


@router.get("/invoices")
async def list_invoices(
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(BillingInvoice)
        .where(BillingInvoice.organisation_id == club.id)
        .order_by(BillingInvoice.created_at.desc())
    )).scalars().all()
    return [
        {
            "id": str(r.id),
            "status": r.status,
            "amount_due": r.amount_due,
            "amount_paid": r.amount_paid,
            "currency": r.currency,
            "period_start": r.period_start.isoformat() if r.period_start else None,
            "period_end": r.period_end.isoformat() if r.period_end else None,
            "hosted_invoice_url": r.hosted_invoice_url,
            "invoice_pdf": r.invoice_pdf,
            "line_items": r.line_items,
            "bundle_discount_cents": r.bundle_discount_cents,
            "coupon_code": r.coupon_code,
            "coupon_discount_cents": r.coupon_discount_cents,
            "payment_method_type": r.payment_method_type,
            "payment_method_summary": r.payment_method_summary,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            # Pay by invoice (migration 308) — NULL/None on a card invoice.
            "billing_method": r.billing_method,
            "invoice_kind": r.invoice_kind,
            "invoice_number": r.invoice_number,
            "amount_total_cents": r.amount_total_cents,
            "due_at": r.due_at.isoformat() if r.due_at else None,
            "service_start_date": r.service_start_date.isoformat() if r.service_start_date else None,
            "service_end_date": r.service_end_date.isoformat() if r.service_end_date else None,
            "pay_url": invoice_billing.pay_url(r) if (r.pay_token and r.status == "open") else None,
        }
        for r in rows
    ]


async def _get_club_or_404(db: AsyncSession, org_id: str) -> Organisation:
    club = await db.get(Organisation, org_id)
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")
    return club


def _serialize_payment_methods(data: dict) -> dict:
    default_id = data["default_payment_method_id"]
    return {
        "default_payment_method_id": default_id,
        "payment_methods": [
            {
                "id": pm["id"],
                "type": pm.get("type"),
                "summary": stripe_client.describe_payment_method(pm)[1],
                "is_default": pm["id"] == default_id,
            }
            for pm in data["payment_methods"]
        ],
    }


async def _load_payment_methods(club: Organisation) -> dict:
    if not club.stripe_customer_id:
        return {"default_payment_method_id": None, "payment_methods": []}
    try:
        data = await stripe_client.list_payment_methods(club.stripe_customer_id)
    except stripe_client.StripeNotConfigured:
        raise HTTPException(status_code=503, detail="Online billing isn't configured yet.")
    except stripe_error.StripeError as e:
        raise HTTPException(status_code=502, detail=str(e) or "Could not load payment methods")
    return _serialize_payment_methods(data)


def _require_customer_id(club: Organisation) -> str:
    if not club.stripe_customer_id:
        raise HTTPException(status_code=422, detail="This club has no billing account yet — subscribe to a module first.")
    return club.stripe_customer_id


async def _setup_session_for(club: Organisation) -> dict:
    customer_id = _require_customer_id(club)
    try:
        session = await stripe_client.create_setup_session(customer_id)
    except stripe_client.StripeNotConfigured:
        raise HTTPException(status_code=503, detail="Online billing isn't configured yet.")
    except stripe_error.StripeError as e:
        raise HTTPException(status_code=502, detail=str(e) or "Could not start the payment method setup")
    return {"url": session["url"]}


async def _set_default_payment_method_for(club: Organisation, pm_id: str) -> dict:
    customer_id = _require_customer_id(club)
    try:
        await stripe_client.set_default_payment_method(customer_id, pm_id)
    except stripe_client.StripeNotConfigured:
        raise HTTPException(status_code=503, detail="Online billing isn't configured yet.")
    except stripe_error.StripeError as e:
        raise HTTPException(status_code=502, detail=str(e) or "Could not set the default payment method")
    return await _load_payment_methods(club)


async def _remove_payment_method_for(club: Organisation, pm_id: str) -> dict:
    """Detaches a payment method — refuses when it's the only one on file
    (per direct instruction), and if it happened to be the default,
    auto-promotes another remaining one so the club is never left without a
    default payment method for its next renewal or add-on charge."""
    customer_id = _require_customer_id(club)
    current = await _load_payment_methods(club)
    if len(current["payment_methods"]) <= 1:
        raise HTTPException(status_code=422, detail="Can't remove the only payment method on file — add another one first.")
    was_default = pm_id == current["default_payment_method_id"]
    try:
        await stripe_client.detach_payment_method(pm_id)
        if was_default:
            remaining = [pm for pm in current["payment_methods"] if pm["id"] != pm_id]
            if remaining:
                await stripe_client.set_default_payment_method(customer_id, remaining[0]["id"])
    except stripe_client.StripeNotConfigured:
        raise HTTPException(status_code=503, detail="Online billing isn't configured yet.")
    except stripe_error.StripeError as e:
        raise HTTPException(status_code=502, detail=str(e) or "Could not remove this payment method")
    return await _load_payment_methods(club)


@router.get("/payment-methods")
async def list_payment_methods(
    club: Organisation = Depends(get_current_club),
):
    """Any club member can view (matches /invoices — Billing History is
    already visible to the whole admin team); only the primary admin (or a
    super admin) can add/change/remove one, enforced on the three routes
    below."""
    return await _load_payment_methods(club)


@router.post("/payment-methods/setup-session")
async def create_payment_method_setup_session(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Returns a Stripe-hosted setup-mode Checkout Session URL to add a new
    card (or other saved payment method) — no charge involved. Reuses the
    same create_setup_session Stripe already calls for the add-on
    no-payment-method recovery flow; this is just a direct entry point to it
    from the Account page's own payment-methods panel."""
    await _require_primary_or_super_admin(db, current_user, club)
    return await _setup_session_for(club)


@router.post("/payment-methods/{pm_id}/default")
async def set_default_payment_method(
    pm_id: str,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    await _require_primary_or_super_admin(db, current_user, club)
    return await _set_default_payment_method_for(club, pm_id)


@router.delete("/payment-methods/{pm_id}")
async def remove_payment_method(
    pm_id: str,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    await _require_primary_or_super_admin(db, current_user, club)
    return await _remove_payment_method_for(club, pm_id)


# ─── Super Admin equivalents — any club by id, no "acting as" needed ────────

@router.get("/super/clubs/{org_id}/payment-methods", dependencies=[Depends(require_super_admin)])
async def super_list_payment_methods(org_id: str, db: AsyncSession = Depends(get_db)):
    club = await _get_club_or_404(db, org_id)
    return await _load_payment_methods(club)


@router.post("/super/clubs/{org_id}/payment-methods/setup-session", dependencies=[Depends(require_super_admin)])
async def super_create_payment_method_setup_session(org_id: str, db: AsyncSession = Depends(get_db)):
    club = await _get_club_or_404(db, org_id)
    return await _setup_session_for(club)


@router.post("/super/clubs/{org_id}/payment-methods/{pm_id}/default", dependencies=[Depends(require_super_admin)])
async def super_set_default_payment_method(org_id: str, pm_id: str, db: AsyncSession = Depends(get_db)):
    club = await _get_club_or_404(db, org_id)
    return await _set_default_payment_method_for(club, pm_id)


@router.delete("/super/clubs/{org_id}/payment-methods/{pm_id}", dependencies=[Depends(require_super_admin)])
async def super_remove_payment_method(org_id: str, pm_id: str, db: AsyncSession = Depends(get_db)):
    club = await _get_club_or_404(db, org_id)
    return await _remove_payment_method_for(club, pm_id)


# ─── Pay by invoice (migration 308) ────────────────────────────────────────
# See services/invoice_billing.py. Any club admin may elect invoice billing and
# ask for an invoice — per direct instruction the club should never need a
# Super Admin to do it for them — and the invoice itself always goes to the
# Primary Club Admin, whoever asked. A Super Admin can do every one of these
# for any club by id, with no "acting as" round trip.

class BillingMethodIn(BaseModel):
    method: str


class InvoiceRequestIn(BaseModel):
    module_keys: List[str] = []
    coupon_code: Optional[str] = None


async def _require_club_admin_or_super(db: AsyncSession, current_user: User, club: Organisation) -> bool:
    """A club admin of THIS club (primary or not) or a super admin. A plain
    club_member — somebody given access to a few screens — does not decide how
    the club pays. Returns whether the caller is a super admin."""
    m = (await db.execute(
        select(ClubMembership).where(ClubMembership.user_id == current_user.id)
    )).scalar_one_or_none()
    if m and m.role == "super_admin":
        return True
    if m and m.club_id == club.id and m.role == "club_admin":
        return False
    raise HTTPException(status_code=403, detail="Only a club admin can manage how the club pays")


async def _club_with_modules(db: AsyncSession, org_id: str) -> Organisation:
    from sqlalchemy.orm import selectinload
    import uuid as _uuid
    try:
        oid = _uuid.UUID(str(org_id))
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="Club not found")
    club = await db.get(Organisation, oid, options=[selectinload(Organisation.module_subscriptions)])
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")
    return club


async def _invoice_call(coro):
    """One translation of every way raising an invoice can fail, so the club
    route and the Super Admin route answer identically."""
    try:
        return await coro
    except invoice_billing.InvoiceBillingError as e:
        raise HTTPException(status_code=e.status, detail=str(e))
    except stripe_client.StripeNotConfigured:
        raise HTTPException(status_code=503, detail="Online billing isn't configured yet.")
    except stripe_error.StripeError as e:
        raise HTTPException(status_code=502, detail=str(e) or "Stripe could not create the invoice")


async def _request_invoice(db, club, body: InvoiceRequestIn, user, *, applied_via: str) -> dict:
    keys = _validate_keys(body.module_keys)
    plan = await _invoice_call(invoice_billing.plan_invoice(db, club, keys, body.coupon_code))
    row = await _invoice_call(invoice_billing.issue_invoice(db, club, plan, issued_by=user, applied_via=applied_via))
    return {"invoice": invoice_billing.invoice_out(row), "emailed": bool(row.emailed_at),
            "email_error": row.email_error}


async def _load_invoice_row(db, club, invoice_id: str) -> BillingInvoice:
    import uuid as _uuid
    try:
        iid = _uuid.UUID(str(invoice_id))
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="Invoice not found")
    row = await db.get(BillingInvoice, iid)
    if row is None or row.organisation_id != club.id or row.billing_method != invoice_billing.METHOD_INVOICE:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return row


async def _resend(db, club, invoice_id: str) -> dict:
    row = await _load_invoice_row(db, club, invoice_id)
    if row.status != "open":
        raise HTTPException(status_code=409, detail=f"This invoice is {row.status}, so there is nothing to pay.")
    result = await invoice_billing.send_invoice_email(db, club, row)
    return {**result, "invoice": invoice_billing.invoice_out(row)}


@router.get("/invoice-billing")
async def get_invoice_billing(
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    return await invoice_billing.overview(db, club)


@router.put("/billing-method", dependencies=[Depends(require_billing_checkout_enabled)])
async def set_billing_method(
    body: BillingMethodIn,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    await _require_club_admin_or_super(db, current_user, club)
    await _invoice_call(invoice_billing.set_billing_method(db, club, body.method, user=current_user))
    return await invoice_billing.overview(db, club)


@router.post("/invoices/request", dependencies=[Depends(require_billing_checkout_enabled)])
async def request_invoice(
    body: InvoiceRequestIn,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    is_super = await _require_club_admin_or_super(db, current_user, club)
    if not club.invoice_billing_enabled:
        raise HTTPException(status_code=403, detail="Invoicing isn't available for this club.")
    if (club.billing_method or invoice_billing.METHOD_CARD) != invoice_billing.METHOD_INVOICE:
        raise HTTPException(status_code=409, detail="Switch the club to invoice billing first.")
    return await _request_invoice(db, club, body, current_user,
                                  applied_via="super_admin" if is_super else "self_serve")


@router.post("/invoices/{invoice_id}/resend")
async def resend_invoice(
    invoice_id: str,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    await _require_club_admin_or_super(db, current_user, club)
    return await _resend(db, club, invoice_id)


@router.get("/super/clubs/{org_id}/invoice-billing", dependencies=[Depends(require_super_admin)])
async def super_get_invoice_billing(org_id: str, db: AsyncSession = Depends(get_db)):
    club = await _club_with_modules(db, org_id)
    return {
        **await invoice_billing.overview(db, club),
        "modules": account_plan_status(club),
    }


@router.put("/super/clubs/{org_id}/billing-method")
async def super_set_billing_method(
    org_id: str, body: BillingMethodIn,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    club = await _club_with_modules(db, org_id)
    await _invoice_call(invoice_billing.set_billing_method(db, club, body.method, user=current_user))
    return await super_get_invoice_billing(org_id, db)


@router.post("/super/clubs/{org_id}/invoice-quote", dependencies=[Depends(require_super_admin)])
async def super_invoice_quote(org_id: str, body: InvoiceRequestIn, db: AsyncSession = Depends(get_db)):
    club = await _club_with_modules(db, org_id)
    keys = _validate_keys(body.module_keys)
    plan = await _invoice_call(invoice_billing.plan_invoice(db, club, keys, body.coupon_code))
    return invoice_billing.plan_out(plan)


@router.post("/super/clubs/{org_id}/invoices")
async def super_request_invoice(
    org_id: str, body: InvoiceRequestIn,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """A Super Admin raising the invoice on the club's behalf. Deliberately NOT
    behind require_billing_checkout_enabled — that flag keeps an unfinished flow
    away from clubs, and a Super Admin helping a club is the deliberate case.
    The club is moved to invoice billing if it was not already, since raising an
    invoice for a card club would leave it with two ways of paying. Invoicing
    has to have been switched ON for the club first (All Clubs), so a Super
    Admin raising one is always a deliberate second step, never a side effect."""
    club = await _club_with_modules(db, org_id)
    if not club.invoice_billing_enabled:
        raise HTTPException(status_code=409, detail="Switch invoicing on for this club first.")
    if (club.billing_method or invoice_billing.METHOD_CARD) != invoice_billing.METHOD_INVOICE:
        await _invoice_call(invoice_billing.set_billing_method(
            db, club, invoice_billing.METHOD_INVOICE, user=current_user))
    return await _request_invoice(db, club, body, current_user, applied_via="super_admin")


@router.post("/super/clubs/{org_id}/renewal-invoice")
async def super_issue_renewal(
    org_id: str,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Raise this period's renewal invoice NOW rather than waiting for the
    daily job to reach the 14-day mark. Returns the existing one if it has
    already gone out, so pressing it twice sends nothing twice."""
    club = await _club_with_modules(db, org_id)
    plan = await _invoice_call(invoice_billing.plan_renewal(db, club))
    if plan is None:
        raise HTTPException(status_code=422, detail="This club holds no invoice-billed period to renew.")
    row = await _invoice_call(invoice_billing.issue_invoice(db, club, plan, issued_by=current_user,
                                                            applied_via="super_admin"))
    return {"invoice": invoice_billing.invoice_out(row), "emailed": bool(row.emailed_at),
            "email_error": row.email_error}


@router.post("/super/clubs/{org_id}/invoices/{invoice_id}/resend", dependencies=[Depends(require_super_admin)])
async def super_resend_invoice(org_id: str, invoice_id: str, db: AsyncSession = Depends(get_db)):
    club = await _club_with_modules(db, org_id)
    return await _resend(db, club, invoice_id)


@router.post("/super/clubs/{org_id}/invoices/{invoice_id}/void", dependencies=[Depends(require_super_admin)])
async def super_void_invoice(org_id: str, invoice_id: str, db: AsyncSession = Depends(get_db)):
    """Cancel an invoice nobody should pay. Nothing it would have granted is
    touched — a void only stops the payment, it does not remove a module."""
    club = await _club_with_modules(db, org_id)
    row = await _load_invoice_row(db, club, invoice_id)
    if row.status != "open":
        raise HTTPException(status_code=409, detail=f"This invoice is already {row.status}.")
    from datetime import datetime as _dt, timezone as _tz
    await _invoice_call(invoice_billing._void_row(db, row, _dt.now(_tz.utc)))
    await db.commit()
    return {"invoice": invoice_billing.invoice_out(row)}


@router.get("/discount-report", dependencies=[Depends(require_super_admin)])
async def discount_report(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
):
    """Super-Admin-only rollup of every discount actually paid out, sourced
    from billing_invoices (the amount that really landed on a Stripe invoice)
    rather than discount_coupons_redemptions (which records that a code was
    *applied*, not what it was worth in dollars on any given invoice — a
    club can hold one live redemption across several renewal invoices under
    a repeating coupon). Bundle and coupon discounts are reported separately
    since they're independent, optionally-stacking things: (a)/(b) per-club
    and platform-wide bundle discount totals, (c)/(d) per-club-per-code and
    per-code-across-all-clubs coupon totals, both filterable by the invoice's
    created_at date."""
    clauses = []
    if date_from:
        clauses.append(BillingInvoice.created_at >= datetime.combine(date_from, time.min))
    if date_to:
        clauses.append(BillingInvoice.created_at < datetime.combine(date_to + timedelta(days=1), time.min))

    bundle_rows = (await db.execute(
        select(
            BillingInvoice.organisation_id,
            Organisation.name,
            func.sum(BillingInvoice.bundle_discount_cents).label("total_cents"),
            func.count(BillingInvoice.id).label("count"),
        )
        .join(Organisation, Organisation.id == BillingInvoice.organisation_id)
        .where(BillingInvoice.bundle_discount_cents > 0, *clauses)
        .group_by(BillingInvoice.organisation_id, Organisation.name)
        .order_by(func.sum(BillingInvoice.bundle_discount_cents).desc())
    )).all()
    bundle_by_club = [
        {"organisation_id": str(r.organisation_id), "organisation_name": r.name, "total_cents": int(r.total_cents), "count": r.count}
        for r in bundle_rows
    ]

    coupon_club_rows = (await db.execute(
        select(
            BillingInvoice.organisation_id,
            Organisation.name,
            BillingInvoice.coupon_code,
            func.sum(BillingInvoice.coupon_discount_cents).label("total_cents"),
            func.count(BillingInvoice.id).label("count"),
        )
        .join(Organisation, Organisation.id == BillingInvoice.organisation_id)
        .where(BillingInvoice.coupon_discount_cents > 0, BillingInvoice.coupon_code.isnot(None), *clauses)
        .group_by(BillingInvoice.organisation_id, Organisation.name, BillingInvoice.coupon_code)
        .order_by(func.sum(BillingInvoice.coupon_discount_cents).desc())
    )).all()
    coupon_by_club = [
        {
            "organisation_id": str(r.organisation_id),
            "organisation_name": r.name,
            "coupon_code": r.coupon_code,
            "total_cents": int(r.total_cents),
            "count": r.count,
        }
        for r in coupon_club_rows
    ]

    coupon_code_rows = (await db.execute(
        select(
            BillingInvoice.coupon_code,
            func.sum(BillingInvoice.coupon_discount_cents).label("total_cents"),
            func.count(BillingInvoice.id).label("count"),
            func.count(func.distinct(BillingInvoice.organisation_id)).label("club_count"),
        )
        .where(BillingInvoice.coupon_discount_cents > 0, BillingInvoice.coupon_code.isnot(None), *clauses)
        .group_by(BillingInvoice.coupon_code)
        .order_by(func.sum(BillingInvoice.coupon_discount_cents).desc())
    )).all()
    coupon_by_code = [
        {"coupon_code": r.coupon_code, "total_cents": int(r.total_cents), "count": r.count, "club_count": r.club_count}
        for r in coupon_code_rows
    ]

    return {
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "bundle": {
            "by_club": bundle_by_club,
            "total_cents": sum(r["total_cents"] for r in bundle_by_club),
            "total_count": sum(r["count"] for r in bundle_by_club),
        },
        "coupons": {
            "by_club": coupon_by_club,
            "by_code": coupon_by_code,
            "total_cents": sum(r["total_cents"] for r in coupon_by_code),
            "total_count": sum(r["count"] for r in coupon_by_code),
        },
    }
