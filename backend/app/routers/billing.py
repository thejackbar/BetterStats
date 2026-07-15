"""Club-facing Stripe Checkout billing (Account page).

Two things a Primary Admin does here: preview what they're about to buy
(``/quote`` — pure math, no Stripe call) and actually buy it
(``/checkout-session`` — creates a real Stripe Checkout Session and hands back
its URL for the frontend to redirect to). Both depend on
``require_billing_checkout_enabled`` — see platform_settings.py — so neither
does anything reachable by a real club until a super admin switches the flag
on, no matter how long this router has been merged. ``/invoices`` (billing
history) is deliberately NOT gated by the flag — a club that has already paid
should always be able to see its own invoices, even if the flag is later
switched off for new signups.
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.modules import account_plan_status
from app.models.db import BillingInvoice, ClubMembership, Organisation, User, get_db
from app.routers.auth import get_current_user, get_current_club
from app.services import billing_pricing, stripe_client
from app.services.platform_settings import require_billing_checkout_enabled

router = APIRouter(prefix="/club-admin/billing", tags=["club-admin-billing"])


class QuoteIn(BaseModel):
    module_keys: List[str] = []


def _validate_keys(module_keys: List[str]) -> list[str]:
    keys = sorted(set(module_keys or []))
    bad = [k for k in keys if k not in billing_pricing.CHECKOUT_MODULE_NAMES]
    if bad:
        raise HTTPException(status_code=422, detail=f"Unknown module(s): {', '.join(bad)}")
    return keys


@router.post("/quote", dependencies=[Depends(require_billing_checkout_enabled)])
async def get_quote(
    body: QuoteIn,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """The invoice preview shown before a Primary Admin commits to checkout —
    exactly what price_for() would compute for a real Stripe Checkout Session,
    with no Stripe call made. Any club admin can preview; only the primary
    admin can actually check out (see /checkout-session)."""
    keys = _validate_keys(body.module_keys)
    return billing_pricing.price_for(keys)


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

    try:
        session = await stripe_client.create_checkout_session(
            org_id=club.id,
            billing_keys=keys,
            customer_id=club.stripe_customer_id,
            customer_email=current_user.email,
        )
    except stripe_client.StripeNotConfigured:
        raise HTTPException(status_code=503, detail="Online billing isn't configured yet. Contact the BetterCricket team to subscribe.")

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
