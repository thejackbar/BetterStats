"""BetterCricket-managed discount coupons (migration 156).

Super Admin owns the whole lifecycle — code, display name, module coverage,
redemption windows, duration, stackability, max redemptions — entirely
inside BetterCricket. Every eligibility rule is decided HERE, against our own
tables, before Stripe is ever touched; the corresponding Stripe Coupon
(services/stripe_client.sync_coupon_to_stripe) is a pure sync target with no
redeem_by/max_redemptions of its own, so there is exactly one place a
redemption is judged valid, never two systems that could disagree.

Two distinct redemption flows, both funnelled through validate_redemption:
- redeem_for_new_signup — a club with no Stripe subscription yet, entering a
  code alongside their module selection at checkout. Records a 'pending'
  redemption; stripe_billing.py's checkout.session.completed handler flips
  it to 'active' once the subscription is actually created.
- redeem_for_existing_subscription — a Primary Admin (self-serve) or a Super
  Admin (force=True, bypassing the window/max-redemption checks but never
  the "already redeemed"/"inactive" ones) applying a code to an
  already-live subscription ahead of its next renewal. Applies
  synchronously via stripe_client.attach_discount_to_subscription — no
  immediate charge, Stripe queues it for the next invoice.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.modules import BILLABLE_MODULES, STATUS_SUBSCRIBED, account_plan_status
from app.models.db import DiscountCoupon, DiscountCouponRedemption, OrgModuleSubscription
from app.services import stripe_client

# Fields locked once a coupon has a live (non-revoked) redemption — Stripe
# Coupons are themselves immutable on these after creation, and changing them
# out from under an already-redeemed club would silently rewrite what that
# club was promised.
FINANCIAL_FIELDS = {"discount_type", "discount_value", "module_keys", "duration_mode", "duration_renewals"}


class CouponError(ValueError):
    """A redemption/validation failure with a club-facing message. Routers
    turn this into a 422, never a raw 500."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def create_coupon(db: AsyncSession, *, created_by, **fields) -> DiscountCoupon:
    code = (fields.pop("code") or "").strip().upper()
    if not code:
        raise CouponError("A code is required")
    existing = (await db.execute(select(DiscountCoupon).where(DiscountCoupon.code == code))).scalar_one_or_none()
    if existing:
        raise CouponError(f"A coupon with code {code} already exists")
    if fields.get("discount_type") not in ("percent", "amount"):
        raise CouponError("discount_type must be 'percent' or 'amount'")
    if fields.get("duration_mode") not in ("once", "repeating", "forever"):
        raise CouponError("duration_mode must be 'once', 'repeating', or 'forever'")
    if fields.get("duration_mode") == "repeating" and not fields.get("duration_renewals"):
        raise CouponError("duration_renewals is required when duration_mode is 'repeating'")
    module_keys = fields.get("module_keys") or None
    if module_keys:
        bad = [k for k in module_keys if k not in BILLABLE_MODULES]
        if bad:
            raise CouponError(f"Unknown module(s): {', '.join(bad)}")
    coupon = DiscountCoupon(id=uuid.uuid4(), code=code, created_by=created_by, **fields)
    coupon.stripe_coupon_id = await stripe_client.sync_coupon_to_stripe(db, coupon)
    coupon.stripe_mode = stripe_client.stripe_mode()
    db.add(coupon)
    await db.commit()
    await db.refresh(coupon)
    return coupon


async def update_coupon(db: AsyncSession, coupon_id, **fields) -> DiscountCoupon:
    coupon = await get_coupon(db, coupon_id)
    locked = FINANCIAL_FIELDS & set(fields)
    if locked and await redemption_count(db, coupon_id) > 0:
        raise CouponError(
            f"Can't change {', '.join(sorted(locked))} — this coupon already has a redemption. "
            "Deactivate it and create a new one instead."
        )
    for field, value in fields.items():
        setattr(coupon, field, value)
    coupon.updated_at = _now()
    await db.commit()
    await db.refresh(coupon)
    return coupon


async def deactivate_coupon(db: AsyncSession, coupon_id) -> DiscountCoupon:
    return await update_coupon(db, coupon_id, active=False)


async def get_coupon(db: AsyncSession, coupon_id) -> DiscountCoupon:
    coupon = await db.get(DiscountCoupon, coupon_id)
    if not coupon:
        raise CouponError("Coupon not found")
    return coupon


async def get_coupon_by_code(db: AsyncSession, code: str) -> DiscountCoupon | None:
    code = (code or "").strip().upper()
    if not code:
        return None
    return (await db.execute(select(DiscountCoupon).where(DiscountCoupon.code == code))).scalar_one_or_none()


async def list_coupons(db: AsyncSession) -> list[DiscountCoupon]:
    rows = (await db.execute(select(DiscountCoupon).order_by(DiscountCoupon.created_at.desc()))).scalars().all()
    return list(rows)


async def list_redemptions(db: AsyncSession, coupon_id) -> list[DiscountCouponRedemption]:
    rows = (await db.execute(
        select(DiscountCouponRedemption)
        .where(DiscountCouponRedemption.coupon_id == coupon_id)
        .order_by(DiscountCouponRedemption.redeemed_at.desc())
    )).scalars().all()
    return list(rows)


async def redemption_count(db: AsyncSession, coupon_id) -> int:
    result = await db.execute(
        select(func.count()).select_from(DiscountCouponRedemption).where(
            DiscountCouponRedemption.coupon_id == coupon_id,
            DiscountCouponRedemption.status != "revoked",
        )
    )
    return result.scalar_one()


async def revoke_redemption(db: AsyncSession, redemption_id) -> DiscountCouponRedemption:
    redemption = await db.get(DiscountCouponRedemption, redemption_id)
    if not redemption:
        raise CouponError("Redemption not found")
    redemption.status = "revoked"
    await db.commit()
    await db.refresh(redemption)
    return redemption


async def mark_redemption_confirmed(db: AsyncSession, redemption_id, stripe_subscription_id: str) -> None:
    """Flips a 'pending' new-signup redemption to 'active' once
    checkout.session.completed confirms the subscription was actually
    created. Called from stripe_billing.py — redemption_id arrives as a
    plain string from Stripe metadata, so parse it explicitly rather than
    relying on the driver to coerce a bare string for a UUID PK lookup
    (matches stripe_billing._load_org's own reasoning for org_id)."""
    try:
        redemption_uuid = uuid.UUID(str(redemption_id))
    except (ValueError, TypeError, AttributeError):
        return
    redemption = await db.get(DiscountCouponRedemption, redemption_uuid)
    if not redemption:
        return
    redemption.status = "active"
    redemption.stripe_subscription_id = stripe_subscription_id


def _in_window(d: date, start: date | None, end: date | None) -> bool:
    if start and d < start:
        return False
    if end and d > end:
        return False
    return True


async def _club_original_activation(db: AsyncSession, org_id) -> date | None:
    result = await db.execute(
        select(func.min(OrgModuleSubscription.started_at)).where(
            OrgModuleSubscription.organisation_id == org_id
        )
    )
    started = result.scalar_one_or_none()
    return started.date() if started else None


async def validate_redemption(db: AsyncSession, code: str, org, *, is_new_signup: bool,
                               candidate_module_keys: list[str], force: bool = False) -> DiscountCoupon:
    """The one rule engine both redemption flows call. Raises CouponError on
    any failure; returns the coupon on success. ``force`` (Super-Admin-only)
    skips the redeem/new-signup/loyalty window checks and the max_redemptions
    cap, but NEVER the "already redeemed" or "inactive" checks, and never the
    module-coverage check — bypassing that would create a discount that
    silently discounts nothing.

    Window semantics: each of the three optional windows only restricts
    anything if at least one of its start/end bounds is set. new_signup_window
    and loyalty_window are independent — a coupon can leave either or both
    unset (no restriction from that rule for that flow)."""
    coupon = await get_coupon_by_code(db, code)
    if not coupon or not coupon.active:
        raise CouponError("That code isn't valid")

    already = (await db.execute(
        select(DiscountCouponRedemption).where(
            DiscountCouponRedemption.coupon_id == coupon.id,
            DiscountCouponRedemption.organisation_id == org.id,
            DiscountCouponRedemption.status != "revoked",
        )
    )).scalar_one_or_none()
    if already:
        raise CouponError("Your club has already used this code")

    today = _now().date()
    if not force:
        if not _in_window(today, coupon.redeem_window_start, coupon.redeem_window_end):
            raise CouponError("This code isn't available right now")
        if is_new_signup:
            if (coupon.new_signup_window_start or coupon.new_signup_window_end) and not _in_window(
                today, coupon.new_signup_window_start, coupon.new_signup_window_end
            ):
                raise CouponError("This code isn't valid for new subscriptions right now")
        else:
            if coupon.loyalty_window_start or coupon.loyalty_window_end:
                joined = await _club_original_activation(db, org.id)
                if not joined or not _in_window(joined, coupon.loyalty_window_start, coupon.loyalty_window_end):
                    raise CouponError("This code isn't valid for your club")
        if coupon.max_redemptions is not None and await redemption_count(db, coupon.id) >= coupon.max_redemptions:
            raise CouponError("This code has reached its redemption limit")

    module_keys = coupon.module_keys or None
    if module_keys and not (set(module_keys) & set(candidate_module_keys)):
        raise CouponError("This code doesn't apply to any of your selected modules")

    return coupon


async def ensure_stripe_coupon(db: AsyncSession, coupon) -> str:
    """The coupon's Stripe Coupon id for the mode the app is actually running
    in, minting it if what we hold belongs to the other one.

    A Stripe Coupon lives in exactly one mode, so an id created while the box
    ran test keys is dead the moment live keys are configured — Stripe answers
    "No such coupon ...; a similar object exists in test mode", which is what
    failed every live checkout carrying a code. Re-syncing rather than
    refusing means a coupon a club has already been given keeps working
    through a key switch, with no Super Admin re-creating the catalogue.

    Every coupon created before migration 263 has a NULL stripe_mode, which
    reads as "not this mode" and so re-syncs once, on first use."""
    mode = stripe_client.stripe_mode()
    if coupon.stripe_coupon_id and coupon.stripe_mode == mode:
        return coupon.stripe_coupon_id
    coupon.stripe_coupon_id = await stripe_client.sync_coupon_to_stripe(db, coupon)
    coupon.stripe_mode = mode
    await db.commit()
    await db.refresh(coupon)
    return coupon.stripe_coupon_id


async def redeem_for_new_signup(db: AsyncSession, code: str, org, selected_module_keys: list[str], user) -> dict:
    coupon = await validate_redemption(
        db, code, org, is_new_signup=True, candidate_module_keys=selected_module_keys,
    )
    stripe_coupon_id = await ensure_stripe_coupon(db, coupon)
    redemption = DiscountCouponRedemption(
        id=uuid.uuid4(), coupon_id=coupon.id, organisation_id=org.id,
        redeemed_by_user_id=user.id if user else None, applied_via="self_serve", status="pending",
    )
    db.add(redemption)
    await db.commit()
    await db.refresh(redemption)
    return {
        "redemption_id": str(redemption.id),
        "stripe_coupon_id": stripe_coupon_id,
        "stackable_with_bundle": coupon.stackable_with_bundle,
        "coupon": coupon,
    }


async def redeem_for_existing_subscription(db: AsyncSession, code: str, org, user, *,
                                            applied_via: str, force: bool = False) -> DiscountCouponRedemption:
    if not org.stripe_subscription_id:
        raise CouponError("Your club doesn't have an active subscription to apply this to")
    held_keys = [row["module"] for row in account_plan_status(org) if row["status"] == STATUS_SUBSCRIBED]
    coupon = await validate_redemption(
        db, code, org, is_new_signup=False, candidate_module_keys=held_keys, force=force,
    )
    stripe_coupon_id = await ensure_stripe_coupon(db, coupon)
    await stripe_client.attach_discount_to_subscription(org.stripe_subscription_id, stripe_coupon_id)
    redemption = DiscountCouponRedemption(
        id=uuid.uuid4(), coupon_id=coupon.id, organisation_id=org.id,
        redeemed_by_user_id=user.id if user else None, applied_via=applied_via, status="active",
        stripe_subscription_id=org.stripe_subscription_id,
    )
    db.add(redemption)
    await db.commit()
    await db.refresh(redemption)
    return redemption
