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
from app.services import billing_pricing, discount_coupons, module_subscriptions, platform_settings, stripe_client
from app.services.platform_settings import require_billing_checkout_enabled

router = APIRouter(prefix="/club-admin/billing", tags=["club-admin-billing"])
logger = logging.getLogger(__name__)


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


def _stripe_address(club: Organisation) -> dict:
    """Stripe's Address shape ({"line1","city","state","postal_code","country"})
    from the club's resolved address (see self_serve_trial._resolve_club_address).
    Country is always "AU": every club on this platform is an Australian
    Cricket Australia club (source data is always AU-tenant-filtered), and
    PlayHQ's own country field is a full name ("Australia"), not the
    ISO-3166 alpha-2 code Stripe requires.

    ALWAYS returns at least {"country": "AU"}, even when the club has no
    street address on file — that country alone is what makes both of these
    work from the very first checkout attempt:
      * automatic_tax has an AU jurisdiction to apply 10% GST against (a
        country-level tax; postcode/state refine it but AU country is enough
        for GST to calculate), instead of $0 with no country set; and
      * Stripe offers the AU-only recurring payment methods (PayTo, BECS
        Direct Debit) — both are filtered out of Checkout entirely when the
        Customer's country is unknown, leaving only the globally-available
        ones (Card, Klarna).
    Returning None here (the old behaviour when no street address was on
    file) left the Customer with no country at all, which broke both — see
    the report that surfaced this. Street-level fields are added only when
    present."""
    addr = {"country": "AU"}
    if club.address_line1:
        addr["line1"] = club.address_line1
    if club.suburb:
        addr["city"] = club.suburb
    if club.state:
        addr["state"] = club.state
    if club.postcode:
        addr["postal_code"] = club.postcode
    return addr


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
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            logger.info(
                "billing add-on: entitlement for %s already granted concurrently (likely the invoice.paid "
                "webhook winning the race) — treating as success", addon_keys,
            )
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
