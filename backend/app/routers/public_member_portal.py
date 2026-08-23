"""Member self-service portal (public, unauthenticated by necessity — a
member has no admin login). See services/member_portal_auth.py for the
magic-link + session-cookie design, and services/fees.py::
member_financial_snapshot for the fee numbers.

Every route except /status resolves the club by slug and then immediately
checks platform_settings.member_portal_enabled_for_org — per direct
instruction this whole feature is invisible/unusable until a super admin
switches it on for that club. /status stays a plain 200 (not a 404) so the
frontend can render a friendly "not available yet" message instead of a raw
error to a real member who's clicked a stale/shared link.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.models.db import Organisation, FeeMember, get_db
from app.services import fees as fee_service
from app.services import member_portal_auth as portal_auth
from app.services import platform_settings as ps
from app.services import qualifications as qual_service
from app.services import rate_limit
from app.services import stripe_connect_client

router = APIRouter(prefix="/public/member-portal", tags=["public-member-portal"])

REQUEST_LINK_LIMIT = 5
REQUEST_LINK_WINDOW_SECONDS = 3600
PAY_KINDS = ("membership", "match_day")


async def _org_or_404(db: AsyncSession, slug: str) -> Organisation:
    org = (await db.execute(select(Organisation).where(Organisation.slug == slug.lower().strip()))).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=404, detail="Club not found")
    return org


async def _org_enabled_or_404(db: AsyncSession, slug: str) -> Organisation:
    org = await _org_or_404(db, slug)
    if not await ps.member_portal_enabled_for_org(db, org):
        raise HTTPException(status_code=404, detail="Not found")
    return org


async def _current_member(request: Request, db: AsyncSession, org: Organisation) -> FeeMember:
    member_id = portal_auth.read_session(request, org.id)
    if member_id is None:
        raise HTTPException(status_code=401, detail="Please sign in again")
    member = await db.get(FeeMember, member_id)
    if member is None or member.organisation_id != org.id:
        raise HTTPException(status_code=401, detail="Please sign in again")
    return member


@router.get("/{slug}/status")
async def portal_status(slug: str, db: AsyncSession = Depends(get_db)):
    org = await _org_or_404(db, slug)
    enabled = await ps.member_portal_enabled_for_org(db, org)
    return {"enabled": enabled, "club_name": org.name, "club_slug": org.slug}


class RequestLinkIn(BaseModel):
    email: str


@router.post("/{slug}/request-link")
async def request_link(slug: str, data: RequestLinkIn, db: AsyncSession = Depends(get_db)):
    org = await _org_enabled_or_404(db, slug)
    email = (data.email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=422, detail="Email is required")
    rate_limit.enforce(f"portal:link:{org.id}:{email}", REQUEST_LINK_LIMIT, REQUEST_LINK_WINDOW_SECONDS,
                       detail="Too many requests. Try again shortly.")

    match = (await db.execute(
        select(FeeMember).where(FeeMember.organisation_id == org.id, func.lower(FeeMember.email) == email)
    )).scalars().first()
    if match is not None:
        token = portal_auth.sign_magic_link(org.id, match.id)
        try:
            await portal_auth.send_magic_link_email(
                to_email=email, member_name=match.full_name, club_name=org.name, club_slug=org.slug, token=token,
            )
        except RuntimeError:
            pass  # never reveal delivery failure — same generic response either way
    # Deliberately identical response whether or not the email matched a
    # member, so this endpoint can't be used to enumerate the roster.
    return {"sent": True}


@router.get("/{slug}/verify")
async def verify(slug: str, token: str, response: Response, db: AsyncSession = Depends(get_db)):
    org = await _org_enabled_or_404(db, slug)
    member_id = portal_auth.verify_magic_link(token, org.id)
    if member_id is None:
        raise HTTPException(status_code=422, detail="This link has expired, request a new one.")
    member = await db.get(FeeMember, member_id)
    if member is None or member.organisation_id != org.id:
        raise HTTPException(status_code=422, detail="This link has expired, request a new one.")
    portal_auth.issue_session_cookie(response, org.id, member.id)
    return {"ok": True, "full_name": member.full_name}


@router.post("/{slug}/logout")
async def logout(slug: str, response: Response, db: AsyncSession = Depends(get_db)):
    await _org_or_404(db, slug)
    portal_auth.clear_session_cookie(response)
    return {"ok": True}


@router.get("/{slug}/me")
async def me(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    org = await _org_enabled_or_404(db, slug)
    member = await _current_member(request, db, org)
    snapshot = await fee_service.member_financial_snapshot(db, org.id, member.id)
    qualifications = await qual_service.list_member_qualifications(db, org.id, member.id)
    connect_ready = bool(org.stripe_connect_account_id and org.stripe_connect_charges_enabled)
    return {
        "member": {
            "id": str(member.id), "full_name": member.full_name,
            "email": member.email, "mobile": member.mobile,
            "is_life_member": member.is_life_member, "is_honorary": member.is_honorary,
        },
        "fees": snapshot,
        "qualifications": qualifications,
        "online_payment_available": connect_ready,
    }


class MePatch(BaseModel):
    email: Optional[str] = None
    mobile: Optional[str] = None


@router.patch("/{slug}/me")
async def update_me(slug: str, data: MePatch, request: Request, db: AsyncSession = Depends(get_db)):
    org = await _org_enabled_or_404(db, slug)
    member = await _current_member(request, db, org)
    if data.email is not None:
        member.email = data.email.strip() or None
    if data.mobile is not None:
        member.mobile = data.mobile.strip() or None
    await db.commit()
    return {"id": str(member.id), "email": member.email, "mobile": member.mobile}


class PayIn(BaseModel):
    kind: str


@router.post("/{slug}/pay")
async def pay(slug: str, data: PayIn, request: Request, db: AsyncSession = Depends(get_db)):
    org = await _org_enabled_or_404(db, slug)
    member = await _current_member(request, db, org)
    if data.kind not in PAY_KINDS:
        raise HTTPException(status_code=422, detail="Invalid payment kind")
    if not org.stripe_connect_account_id or not org.stripe_connect_charges_enabled:
        raise HTTPException(status_code=422, detail="Online payment isn't set up for this club yet.")

    snapshot = await fee_service.member_financial_snapshot(db, org.id, member.id)
    if snapshot is None:
        raise HTTPException(status_code=422, detail="No fees on record yet.")
    fin = snapshot["financials"]
    outstanding = fin["membership_outstanding"] if data.kind == "membership" else fin["match_fee_outstanding"]
    if outstanding <= 0:
        raise HTTPException(status_code=422, detail="Nothing outstanding to pay.")

    label = "Membership fee" if data.kind == "membership" else "Match fees"
    success_url = f"{settings.public_base_url}/portal/{org.slug}?paid=1"
    cancel_url = f"{settings.public_base_url}/portal/{org.slug}?paid=0"
    try:
        session = await stripe_connect_client.create_fee_payment_checkout_session(
            connected_account_id=org.stripe_connect_account_id,
            amount_cents=round(outstanding * 100),
            description=f"{org.name}, {label}",
            org_id=str(org.id), member_id=str(member.id), season_id=snapshot["season_id"], kind=data.kind,
            success_url=success_url, cancel_url=cancel_url,
        )
    except stripe_connect_client.StripeNotConfigured:
        raise HTTPException(status_code=503, detail="Online payment isn't available right now.")
    return {"checkout_url": session.url}
