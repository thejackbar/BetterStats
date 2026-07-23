"""Stripe Connect admin flow — a club connecting its own Stripe account so
member fee payments land directly in the club's own bank account.

Gated by BOTH the existing MANAGE_FEES capability and
require_member_portal_enabled — per direct instruction this whole feature
(member portal + online fee payment) is invisible to an ordinary club admin
until a super admin switches the platform flag on, globally or for this one
club specifically (see platform_settings.member_portal_enabled_for_org).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import User, Organisation, get_db
from app.routers.auth import get_current_club
from app.auth.capabilities import require_cap, MANAGE_FEES
from app.services import platform_settings as ps
from app.services import stripe_connect_client

router = APIRouter(prefix="/club-admin/stripe-connect", tags=["club-admin-stripe-connect"])
_require = Depends(require_cap(MANAGE_FEES))
_require_flag = Depends(ps.require_member_portal_enabled)


def _status_dict(club: Organisation) -> dict:
    return {
        "connected": bool(club.stripe_connect_account_id),
        "details_submitted": club.stripe_connect_details_submitted,
        "charges_enabled": club.stripe_connect_charges_enabled,
        "payouts_enabled": club.stripe_connect_payouts_enabled,
    }


@router.get("/status")
async def get_status(_: User = _require, __: None = _require_flag,
                     club: Organisation = Depends(get_current_club)):
    return _status_dict(club)


@router.post("/connect")
async def connect(_: User = _require, __: None = _require_flag,
                  club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    """Creates the connected account on first call (idempotent — re-uses the
    existing one on a later call), then always returns a fresh onboarding
    link (Stripe's account-link URLs expire quickly, so never cache one)."""
    try:
        if not club.stripe_connect_account_id:
            account_id = await stripe_connect_client.create_connected_account(
                club_name=club.name, club_email=club.contact_email,
            )
            club.stripe_connect_account_id = account_id
            await db.commit()
        url = await stripe_connect_client.create_account_link(club.stripe_connect_account_id)
    except stripe_connect_client.StripeNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {"url": url}


@router.post("/refresh")
async def refresh(_: User = _require, __: None = _require_flag,
                  club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    """Re-fetches the connected account's onboarding status from Stripe —
    useful right after the admin returns from the hosted onboarding flow,
    ahead of whatever the account.updated webhook delivers."""
    if not club.stripe_connect_account_id:
        raise HTTPException(status_code=422, detail="No connected account yet")
    try:
        account = await stripe_connect_client.retrieve_account(club.stripe_connect_account_id)
    except stripe_connect_client.StripeNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))
    club.stripe_connect_details_submitted = bool(account.details_submitted)
    club.stripe_connect_charges_enabled = bool(account.charges_enabled)
    club.stripe_connect_payouts_enabled = bool(account.payouts_enabled)
    await db.commit()
    return _status_dict(club)


@router.post("/dashboard-link")
async def dashboard_link(_: User = _require, __: None = _require_flag,
                         club: Organisation = Depends(get_current_club)):
    if not club.stripe_connect_account_id or not club.stripe_connect_details_submitted:
        raise HTTPException(status_code=422, detail="Finish connecting Stripe first")
    try:
        url = await stripe_connect_client.create_login_link(club.stripe_connect_account_id)
    except stripe_connect_client.StripeNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {"url": url}


@router.post("/disconnect")
async def disconnect(_: User = _require, __: None = _require_flag,
                     club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    """Unlinks the connected account from this club's row. Does NOT delete
    the Stripe account itself (a club may still have real payout history on
    it) — reconnecting later mints a fresh account, since Stripe doesn't
    support "re-attaching" a detached account id here."""
    club.stripe_connect_account_id = None
    club.stripe_connect_details_submitted = False
    club.stripe_connect_charges_enabled = False
    club.stripe_connect_payouts_enabled = False
    await db.commit()
    return {"disconnected": True}
