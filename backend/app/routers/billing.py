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

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from stripe import error as stripe_error

from app.auth.modules import BILLABLE_MODULES, STATUS_ACTIVE, account_plan_status
from app.models.db import BillingInvoice, ClubMembership, Organisation, User, get_db
from app.routers.auth import get_current_user, get_current_club
from app.services import billing_pricing, discount_coupons, module_subscriptions, platform_settings, stripe_client
from app.services.platform_settings import require_billing_checkout_enabled

router = APIRouter(prefix="/club-admin/billing", tags=["club-admin-billing"])


class QuoteIn(BaseModel):
    module_keys: List[str] = []
    coupon_code: Optional[str] = None


def _apply_coupon_to_quote(quote: dict, coupon) -> dict:
    """Folds a validated discount-coupon into a new_subscription price_for()
    quote — pure local math for the preview (no Stripe call, matching /quote's
    existing no-Stripe-call design); the real Checkout Session's own discounts
    array is Stripe's own authoritative number at actual checkout. A
    non-stackable coupon REPLACES the bundle discount rather than combining
    with it, mirroring stripe_client.create_checkout_session's own rule.

    A STACKING coupon is calculated on top of the bundle discount, not
    alongside it — mirrors Stripe's own behaviour: create_checkout_session
    passes both coupons in a `discounts` list (bundle first, then the
    stacking coupon), and Stripe applies multiple discounts sequentially in
    that order, so the real checkout already charges bundle-then-coupon.
    Computing the coupon off the raw pre-bundle subtotal here would show a
    preview total that doesn't match what Stripe actually charges. The
    bundle discount itself is a flat dollar amount across the whole
    selection, not itemised per module, so when a coupon is scoped to only
    some modules its share of the bundle discount is allocated
    proportionally to its slice of the full subtotal."""
    covered = set(coupon.module_keys) if coupon.module_keys else {li["key"] for li in quote["line_items"]}
    covered_subtotal = sum(li["price"] for li in quote["line_items"] if li["key"] in covered)

    if not coupon.stackable_with_bundle and quote["discount"] > 0:
        # Replaces the bundle discount outright — computed against the plain
        # covered subtotal, since there's no bundle reduction left in play.
        if coupon.discount_type == "percent":
            coupon_off = round(covered_subtotal * float(coupon.discount_value) / 100, 2)
        else:
            coupon_off = min(float(coupon.discount_value), covered_subtotal)
        quote["discount"] = 0
        quote["total"] = quote["subtotal"] - coupon_off
    else:
        bundle_share = (
            quote["discount"] * covered_subtotal / quote["subtotal"] if quote["subtotal"] else 0
        )
        covered_after_bundle = covered_subtotal - bundle_share
        if coupon.discount_type == "percent":
            coupon_off = round(covered_after_bundle * float(coupon.discount_value) / 100, 2)
        else:
            coupon_off = min(float(coupon.discount_value), covered_after_bundle)
        quote["total"] = round(quote["total"] - coupon_off, 2)
    quote["coupon"] = {
        "code": coupon.code,
        "display_name": coupon.display_name,
        "discount_type": coupon.discount_type,
        "discount_value": float(coupon.discount_value),
        "amount_off": coupon_off,
        "stackable_with_bundle": coupon.stackable_with_bundle,
    }
    return quote


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
            raise HTTPException(status_code=502, detail=str(e) or "Could not add the module(s)")

        # No Checkout Session happened for this path, so there's no
        # checkout.session.completed webhook to grant entitlement — do it
        # synchronously here, same renewal_date Stripe just reported back
        # (the invoice.paid webhook that follows moments later re-applies the
        # same state — harmless, entitlement writes are idempotent).
        renewal_date = stripe_client.epoch_to_date(sub.get("current_period_end"))
        now = datetime.now(timezone.utc)
        for key in addon_keys:
            module_subscriptions.set_status_billing(club, key, STATUS_ACTIVE, renewal_date=renewal_date, now=now)
        await db.commit()
        return {"added": True, "modules": addon_keys}

    schedule = await platform_settings.get_bundle_discount_schedule(db)

    redemption_id = None
    extra_coupon_id = None
    extra_stackable = False
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
        if extra_stackable:
            # Checkout Session can carry at most one discount, so a stacking
            # coupon can't ride alongside the bundle coupon — stripe_client
            # combines them into a single ad-hoc coupon instead, and needs
            # the coupon's own dollar contribution to do that. Computed with
            # the SAME math /quote's preview uses (_apply_coupon_to_quote),
            # so what gets charged matches what was previewed.
            preview_quote = billing_pricing.price_for(keys, schedule=schedule)
            extra_coupon_off = _apply_coupon_to_quote(preview_quote, redeemed["coupon"])["coupon"]["amount_off"]

    try:
        session = await stripe_client.create_checkout_session(
            db,
            org_id=club.id,
            billing_keys=keys,
            customer_id=club.stripe_customer_id,
            customer_email=current_user.email,
            discount_schedule=schedule,
            extra_coupon_id=extra_coupon_id,
            extra_stackable=extra_stackable,
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
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
