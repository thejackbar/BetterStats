"""BetterCricket-managed discount coupons (migration 156).

Super-Admin CRUD over the coupon catalogue, plus the club-facing "redeem a
code ahead of your renewal" action. The new-signup redemption path doesn't
live here — it's folded into billing.py's existing /quote and
/checkout-session (see QuoteIn.coupon_code), since redeeming a code at
signup is one step of that flow, not a separate action.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import ClubMembership, Organisation, User, get_db
from app.routers.auth import get_current_club, get_current_user, require_super_admin
from app.services import discount_coupons
from app.services.platform_settings import require_billing_checkout_enabled

router = APIRouter(prefix="/club-admin/coupons", tags=["discount-coupons"])


def _serialize(c) -> dict:
    return {
        "id": str(c.id),
        "code": c.code,
        "display_name": c.display_name,
        "discount_type": c.discount_type,
        "discount_value": float(c.discount_value),
        "module_keys": c.module_keys,
        "redeem_window_start": c.redeem_window_start,
        "redeem_window_end": c.redeem_window_end,
        "new_signup_window_start": c.new_signup_window_start,
        "new_signup_window_end": c.new_signup_window_end,
        "loyalty_window_start": c.loyalty_window_start,
        "loyalty_window_end": c.loyalty_window_end,
        "duration_mode": c.duration_mode,
        "duration_renewals": c.duration_renewals,
        "stackable_with_bundle": c.stackable_with_bundle,
        "max_redemptions": c.max_redemptions,
        "active": c.active,
        "stripe_coupon_id": c.stripe_coupon_id,
        "created_at": c.created_at,
    }


class CouponCreate(BaseModel):
    code: str
    display_name: str
    discount_type: str
    discount_value: float
    module_keys: Optional[List[str]] = None
    redeem_window_start: Optional[date] = None
    redeem_window_end: Optional[date] = None
    new_signup_window_start: Optional[date] = None
    new_signup_window_end: Optional[date] = None
    loyalty_window_start: Optional[date] = None
    loyalty_window_end: Optional[date] = None
    duration_mode: str = "once"
    duration_renewals: Optional[int] = None
    stackable_with_bundle: bool = False
    max_redemptions: Optional[int] = None


class CouponUpdate(BaseModel):
    display_name: Optional[str] = None
    discount_type: Optional[str] = None
    discount_value: Optional[float] = None
    module_keys: Optional[List[str]] = None
    redeem_window_start: Optional[date] = None
    redeem_window_end: Optional[date] = None
    new_signup_window_start: Optional[date] = None
    new_signup_window_end: Optional[date] = None
    loyalty_window_start: Optional[date] = None
    loyalty_window_end: Optional[date] = None
    duration_mode: Optional[str] = None
    duration_renewals: Optional[int] = None
    stackable_with_bundle: Optional[bool] = None
    max_redemptions: Optional[int] = None
    active: Optional[bool] = None


@router.get("", dependencies=[Depends(require_super_admin)])
async def list_coupons(db: AsyncSession = Depends(get_db)):
    coupons = await discount_coupons.list_coupons(db)
    out = []
    for c in coupons:
        row = _serialize(c)
        row["redemption_count"] = await discount_coupons.redemption_count(db, c.id)
        out.append(row)
    return out


@router.post("")
async def create_coupon(
    body: CouponCreate,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        coupon = await discount_coupons.create_coupon(db, created_by=current_user.id, **body.model_dump())
    except discount_coupons.CouponError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _serialize(coupon)


@router.patch("/{coupon_id}", dependencies=[Depends(require_super_admin)])
async def update_coupon(coupon_id: str, body: CouponUpdate, db: AsyncSession = Depends(get_db)):
    fields = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    try:
        coupon = await discount_coupons.update_coupon(db, coupon_id, **fields)
    except discount_coupons.CouponError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _serialize(coupon)


@router.post("/{coupon_id}/deactivate", dependencies=[Depends(require_super_admin)])
async def deactivate_coupon(coupon_id: str, db: AsyncSession = Depends(get_db)):
    coupon = await discount_coupons.deactivate_coupon(db, coupon_id)
    return _serialize(coupon)


@router.get("/{coupon_id}/redemptions", dependencies=[Depends(require_super_admin)])
async def get_redemptions(coupon_id: str, db: AsyncSession = Depends(get_db)):
    rows = await discount_coupons.list_redemptions(db, coupon_id)
    orgs = {}
    if rows:
        org_ids = {r.organisation_id for r in rows}
        result = await db.execute(select(Organisation.id, Organisation.name).where(Organisation.id.in_(org_ids)))
        orgs = {row[0]: row[1] for row in result.all()}
    return [
        {
            "id": str(r.id),
            "organisation_id": str(r.organisation_id),
            "organisation_name": orgs.get(r.organisation_id, "Unknown club"),
            "applied_via": r.applied_via,
            "status": r.status,
            "redeemed_at": r.redeemed_at,
        }
        for r in rows
    ]


@router.post("/{coupon_id}/revoke/{redemption_id}", dependencies=[Depends(require_super_admin)])
async def revoke_redemption(coupon_id: str, redemption_id: str, db: AsyncSession = Depends(get_db)):
    try:
        redemption = await discount_coupons.revoke_redemption(db, redemption_id)
    except discount_coupons.CouponError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"id": str(redemption.id), "status": redemption.status}


class ForceApplyIn(BaseModel):
    organisation_id: str
    code: str


@router.post("/force-apply")
async def force_apply(
    body: ForceApplyIn,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    org = await db.get(Organisation, body.organisation_id)
    if not org:
        raise HTTPException(status_code=404, detail="Club not found")
    try:
        redemption = await discount_coupons.redeem_for_existing_subscription(
            db, body.code, org, current_user, applied_via="super_admin", force=True,
        )
    except discount_coupons.CouponError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:  # Stripe errors etc.
        raise HTTPException(status_code=502, detail=str(e) or "Could not apply this code")
    return {"id": str(redemption.id), "status": redemption.status}


class RedeemIn(BaseModel):
    code: str


@router.post("/redeem", dependencies=[Depends(require_billing_checkout_enabled)])
async def redeem(
    body: RedeemIn,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Applies a code to the club's already-live subscription, ahead of its
    next renewal — the self-serve mirror of force_apply above. Same
    primary-admin gate billing.py's /checkout-session already enforces."""
    m = (await db.execute(
        select(ClubMembership).where(ClubMembership.user_id == current_user.id)
    )).scalar_one_or_none()
    is_super = bool(m and m.role == "super_admin")
    if not is_super and not (m and m.club_id == club.id and m.role == "club_admin" and m.is_primary_admin):
        raise HTTPException(status_code=403, detail="Only the club's primary admin can redeem a discount code")
    try:
        redemption = await discount_coupons.redeem_for_existing_subscription(
            db, body.code, club, current_user, applied_via="self_serve",
        )
    except discount_coupons.CouponError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e) or "Could not apply this code")
    return {"id": str(redemption.id), "status": redemption.status}
