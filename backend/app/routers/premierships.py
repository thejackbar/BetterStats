"""Premierships the sync spotted, for an admin to approve or ignore.

Detection is automatic and continuous — every candidate is derived on read from
the games (see ``services/premierships.py``) — but nothing reaches the honour
board until somebody says so. A wrong round label would otherwise mint eleven
wrong awards silently, and the honour board is the club's record of record.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_AWARDS, require_cap
from app.models.db import Organisation, User, get_db
from app.routers.auth import get_current_club
from app.services import premierships

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/club-admin/premierships", tags=["premierships"])

_VALID_STATUS = {"pending", "approved", "ignored", "all"}


class ApproveBody(BaseModel):
    # Which players to award. Omitted means everyone who took the field —
    # present but shortened means the admin unticked somebody (a late
    # withdrawal listed on the team sheet, say).
    player_ids: Optional[list[str]] = None


@router.get("")
async def list_detected(
    status: str = Query("pending"),
    current_user: User = Depends(require_cap(MANAGE_AWARDS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    if status not in _VALID_STATUS:
        raise HTTPException(400, f"status must be one of {sorted(_VALID_STATUS)}")
    candidates = await premierships.list_candidates(db, str(club.id), status=status)
    counts = await premierships.counts_by_status(db, str(club.id))
    return {"candidates": candidates, "counts": counts}


@router.get("/count")
async def pending_count(
    current_user: User = Depends(require_cap(MANAGE_AWARDS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Cheap badge poll — no per-game player lists."""
    return await premierships.counts_by_status(db, str(club.id))


@router.post("/{game_id}/approve")
async def approve_detected(
    game_id: str,
    body: ApproveBody = ApproveBody(),
    current_user: User = Depends(require_cap(MANAGE_AWARDS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await premierships.approve(
            db, str(club.id), game_id,
            user_id=str(current_user.id),
            player_ids=body.player_ids,
        )
    except ValueError as e:
        raise HTTPException(404 if str(e) == "not_a_candidate" else 409, str(e))


@router.post("/{game_id}/ignore")
async def ignore_detected(
    game_id: str,
    current_user: User = Depends(require_cap(MANAGE_AWARDS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await premierships.ignore(db, str(club.id), game_id, user_id=str(current_user.id))
    except ValueError as e:
        raise HTTPException(404 if str(e) == "not_a_candidate" else 409, str(e))


@router.post("/{game_id}/reset")
async def reset_detected(
    game_id: str,
    current_user: User = Depends(require_cap(MANAGE_AWARDS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Back to pending. An approved candidate also hands back exactly the
    awards that approval created."""
    return await premierships.reset(db, str(club.id), game_id)
