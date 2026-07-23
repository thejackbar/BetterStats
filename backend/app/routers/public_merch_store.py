"""Merch storefront (public, unauthenticated) — browse a club's BetterMerch
catalogue and pay online via the club's own Stripe Connect account (the same
one the member portal uses for fee payments).

NOT wrapped in require_module the way an authenticated club route would be —
a customer has no session — instead every route resolves the club by slug
and checks BOTH org_has_module(club, "merch") (no BetterMerch, no
storefront) AND platform_settings.merch_storefront_enabled_for_org (off by
default; a super admin switches it on globally or for one test club first,
same posture as the member portal).
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.modules import MODULE_MERCH, org_has_module
from app.config.settings import settings
from app.models.db import Organisation, get_db
from app.services import merch_store
from app.services import platform_settings as ps
from app.services import stripe_connect_client

router = APIRouter(prefix="/public/merch-store", tags=["public-merch-store"])


async def _org_or_404(db: AsyncSession, slug: str) -> Organisation:
    org = (await db.execute(select(Organisation).where(Organisation.slug == slug.lower().strip()))).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=404, detail="Club not found")
    return org


async def _storefront_ready_org(db: AsyncSession, slug: str) -> Organisation:
    org = await _org_or_404(db, slug)
    if not org_has_module(org, MODULE_MERCH) or not await ps.merch_storefront_enabled_for_org(db, org):
        raise HTTPException(status_code=404, detail="Not found")
    return org


@router.get("/{slug}/status")
async def store_status(slug: str, db: AsyncSession = Depends(get_db)):
    org = await _org_or_404(db, slug)
    visible = org_has_module(org, MODULE_MERCH) and await ps.merch_storefront_enabled_for_org(db, org)
    return {
        "enabled": visible,
        "checkout_ready": visible and bool(org.stripe_connect_account_id and org.stripe_connect_charges_enabled),
        "club_name": org.name, "club_slug": org.slug,
    }


@router.get("/{slug}/catalogue")
async def catalogue(slug: str, db: AsyncSession = Depends(get_db)):
    org = await _storefront_ready_org(db, slug)
    return {"products": await merch_store.storefront_catalogue(db, org.id)}


class CheckoutItem(BaseModel):
    variant_id: str
    quantity: int = 1


class CheckoutIn(BaseModel):
    customer_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    items: list[CheckoutItem]


@router.post("/{slug}/checkout")
async def checkout(slug: str, data: CheckoutIn, db: AsyncSession = Depends(get_db)):
    """Creates the pending order and the Stripe Checkout Session, then
    commits EXACTLY ONCE at the end — reading order.items (or any other
    attribute) after a commit would hit the async "expired attribute" trap
    this codebase has hit before (a lazy-load after commit needs a fresh
    await, which plain attribute access can't provide). A ValueError/Stripe
    failure rolls back the flushed-but-uncommitted order, so nothing is left
    behind."""
    org = await _storefront_ready_org(db, slug)
    if not org.stripe_connect_account_id or not org.stripe_connect_charges_enabled:
        raise HTTPException(status_code=422, detail="Online payment isn't set up for this club yet.")

    try:
        order = await merch_store.create_order(
            db, org.id, customer_name=data.customer_name, email=data.email, phone=data.phone, member_id=None,
            items=[{"variant_id": uuid.UUID(i.variant_id), "quantity": i.quantity} for i in data.items],
        )
        line_items = [{"name": i.product_name + (f" ({i.variant_label})" if i.variant_label else ""),
                       "unit_amount_cents": i.unit_price_cents, "quantity": i.quantity} for i in order.items]
        order_id = order.id
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(e))

    success_url = f"{settings.public_base_url}/shop/{org.slug}?order=1"
    cancel_url = f"{settings.public_base_url}/shop/{org.slug}?order=0"
    try:
        checkout_session = await stripe_connect_client.create_merch_checkout_session(
            connected_account_id=org.stripe_connect_account_id, order_id=str(order_id), org_id=str(org.id),
            line_items=line_items, success_url=success_url, cancel_url=cancel_url,
        )
    except stripe_connect_client.StripeNotConfigured:
        await db.rollback()
        raise HTTPException(status_code=503, detail="Online payment isn't available right now.")

    order.stripe_checkout_session_id = checkout_session.id
    await db.commit()
    return {"checkout_url": checkout_session.url}
