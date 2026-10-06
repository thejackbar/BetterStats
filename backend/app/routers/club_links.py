"""Super Admin: link clubs together (migration 322).

Once two clubs are linked, a Club Admin of either can switch between them from
the admin app (``/auth/switch-club``, ``/auth/me.linked_clubs``). Everything
that decides who may do what lives in ``services/club_links.py``; this router
is the Super Admin's way to build and take apart the groups.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import User, get_db
from app.routers.auth import require_super_admin
from app.services import club_links
from app.services.audit_log import log_activity

router = APIRouter(prefix="/club-admin/super/club-links", tags=["club-links"])


class LinkRequest(BaseModel):
    club_a_id: str
    club_b_id: str


def _club_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="Invalid club id")


@router.get("")
async def list_links(
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    return {"groups": await club_links.list_groups(db)}


@router.post("", status_code=201)
async def link(
    body: LinkRequest,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    a, b = _club_uuid(body.club_a_id), _club_uuid(body.club_b_id)
    try:
        result = await club_links.link_clubs(db, a, b, by_user_id=current_user.id)
    except club_links.ClubLinkError as e:
        await db.rollback()
        raise HTTPException(status_code=e.status, detail=e.message)
    # One audit row per club, so each club's own activity log shows it.
    for org, other in ((a, b), (b, a)):
        await log_activity(
            db, org_id=org, user_id=current_user.id, action="link_club",
            target_type="organisation", target_id=str(other),
            details={"group_id": result["group_id"], "linked_with": str(other)},
        )
    await db.commit()
    groups = await club_links.list_groups(db)
    return {"group_id": result["group_id"],
            "group": next((g for g in groups if g["group_id"] == result["group_id"]), None)}


@router.delete("/{club_id}")
async def unlink(
    club_id: str,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Take one club out of its group. When that leaves a single club the group
    is dissolved. Club Admins who were working in a club that is no longer
    linked to theirs are back at their home club on their next request."""
    org = _club_uuid(club_id)
    try:
        removed = await club_links.unlink_club(db, org)
    except club_links.ClubLinkError as e:
        await db.rollback()
        raise HTTPException(status_code=e.status, detail=e.message)
    for removed_org in removed:
        await log_activity(
            db, org_id=removed_org, user_id=current_user.id, action="unlink_club",
            target_type="organisation", target_id=str(org),
            details={"unlinked": str(org), "dissolved_group": len(removed) > 1},
        )
    await db.commit()
    return {"status": "unlinked", "removed": club_links.ids_to_str(removed)}
