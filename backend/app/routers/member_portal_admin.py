"""A single, deliberately-uncapped status check the admin frontend uses to
decide whether to show ANY member-portal / Stripe Connect nav at all.

No capability requirement (any authenticated club user can call it) since
its only job is telling the nav whether to render a link — the real gates
(MANAGE_FEES + require_member_portal_enabled) sit on the actual
stripe_connect.py / fee endpoints underneath. Kept in its own tiny router
rather than folded into stripe_connect.py or fees.py, since "is this feature
visible yet" is a distinct, capability-free question from either of those.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import User, Organisation, get_db
from app.routers.auth import get_current_user, get_current_club
from app.services import platform_settings as ps

router = APIRouter(prefix="/club-admin/member-portal", tags=["club-admin-member-portal"])


@router.get("/status")
async def member_portal_status(
    _: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    return {"enabled": await ps.member_portal_enabled_for_org(db, club)}
