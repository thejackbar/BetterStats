"""BetterClubManager Facilities — booking-requests approval queue API
(core capability, not a paid module). Gated on MANAGE_ASSETS.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import User, Organisation, get_db
from app.routers.auth import get_current_club
from app.auth.capabilities import require_cap, MANAGE_ASSETS
from app.services import facility_requests as svc

router = APIRouter(prefix="/club-admin/facility-requests", tags=["club-admin-facility-requests"])
_cap = Depends(require_cap(MANAGE_ASSETS))


class RequestCreate(BaseModel):
    facility_id: str
    title: str
    starts_at: datetime
    ends_at: datetime
    requester_name: Optional[str] = None
    requester_email: Optional[str] = None
    note: Optional[str] = None


@router.get("")
async def list_requests(_: User = _cap, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    return {"requests": await svc.list_pending(db, club.id)}


@router.post("")
async def create_request(data: RequestCreate, _: User = _cap, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    rid = await svc.create(db, club.id, facility_id=data.facility_id, title=data.title, starts_at=data.starts_at,
                           ends_at=data.ends_at, requester_name=data.requester_name, requester_email=data.requester_email, note=data.note)
    await db.commit()
    return {"id": rid}


@router.post("/{req_id}/approve")
async def approve_request(req_id: str, force: bool = False, _: User = _cap, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    res = await svc.approve(db, club.id, req_id, force=force)
    if res.get("ok"):
        await db.commit()
    return res


@router.post("/{req_id}/decline")
async def decline_request(req_id: str, _: User = _cap, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    res = await svc.decline(db, club.id, req_id)
    await db.commit()
    return res


@router.post("/clear")
async def clear_requests(_: User = _cap, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    n = await svc.clear_all(db, club.id)
    await db.commit()
    return {"cleared": n}
