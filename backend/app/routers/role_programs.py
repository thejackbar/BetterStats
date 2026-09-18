"""Role Programs API — what a role entails, and its measurable handover.

Core capability, not a paid module. A role program spans both volunteer roles
and committee seats (both are club_roles), so it accepts EITHER MANAGE_VOLUNTEERS
or MANAGE_COMMITTEE — the two managers who between them own succession. See
services/role_programs.py. There is no MANAGE_ROLES capability in this codebase;
the roles catalogue itself is gated the same any-of way.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import User, Organisation, get_db
from app.routers.auth import get_current_club
from app.auth.capabilities import require_any_cap, MANAGE_VOLUNTEERS, MANAGE_COMMITTEE
from app.services import role_programs as svc

router = APIRouter(prefix="/club-admin/role-programs", tags=["club-admin-role-programs"])
_require = Depends(require_any_cap(MANAGE_VOLUNTEERS, MANAGE_COMMITTEE))


def _uuid(s) -> Optional[uuid.UUID]:
    if s in (None, ""):
        return None
    try:
        return uuid.UUID(str(s))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Bad id")


def _parse_date(s) -> Optional[date]:
    if s in (None, ""):
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        raise HTTPException(status_code=400, detail="Bad date")


# ─── Program (read) ──────────────────────────────────────────────────────────

@router.get("/roles/{role_id}/program")
async def get_program(role_id: str, _: User = _require, club: Organisation = Depends(get_current_club),
                      db: AsyncSession = Depends(get_db)):
    program = await svc.assemble_program(db, club.id, _uuid(role_id))
    if program is None:
        raise HTTPException(status_code=404, detail="Role not found")
    return program


# ─── Handovers ───────────────────────────────────────────────────────────────

@router.get("/handovers")
async def list_handovers(role_id: Optional[str] = None, status: Optional[str] = None,
                         _: User = _require, club: Organisation = Depends(get_current_club),
                         db: AsyncSession = Depends(get_db)):
    return {"handovers": await svc.list_handovers(db, club.id, role_id=_uuid(role_id), status=status)}


class HandoverCreate(BaseModel):
    role_id: str
    incoming_member_id: Optional[str] = None
    incoming_name: Optional[str] = None
    outgoing_member_id: Optional[str] = None
    outgoing_name: Optional[str] = None
    target_date: Optional[str] = None
    notes: Optional[str] = None


@router.post("/handovers")
async def create_handover(data: HandoverCreate, current: User = _require,
                          club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    try:
        h = await svc.create_handover(
            db, club.id, role_id=_uuid(data.role_id),
            incoming_member_id=_uuid(data.incoming_member_id), incoming_name=data.incoming_name,
            outgoing_member_id=_uuid(data.outgoing_member_id), outgoing_name=data.outgoing_name,
            target_date=_parse_date(data.target_date), notes=data.notes, created_by=current.id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return await svc.get_handover(db, club.id, h.id)


@router.get("/handovers/{handover_id}")
async def get_handover(handover_id: str, _: User = _require, club: Organisation = Depends(get_current_club),
                       db: AsyncSession = Depends(get_db)):
    out = await svc.get_handover(db, club.id, _uuid(handover_id))
    if out is None:
        raise HTTPException(status_code=404, detail="Handover not found")
    return out


class HandoverPatch(BaseModel):
    status: Optional[str] = None
    incoming_member_id: Optional[str] = None
    incoming_name: Optional[str] = None
    outgoing_member_id: Optional[str] = None
    outgoing_name: Optional[str] = None
    target_date: Optional[str] = None
    notes: Optional[str] = None


@router.patch("/handovers/{handover_id}")
async def update_handover(handover_id: str, data: HandoverPatch, _: User = _require,
                          club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    h = await svc.load_handover(db, club.id, _uuid(handover_id))
    if h is None:
        raise HTTPException(status_code=404, detail="Handover not found")
    fields = data.model_dump(exclude_unset=True)
    for f in ("incoming_member_id", "outgoing_member_id"):
        if f in fields:
            fields[f] = _uuid(fields[f])
    if "target_date" in fields:
        fields["target_date"] = _parse_date(fields["target_date"])
    try:
        await svc.update_handover(db, club.id, h, **fields)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return await svc.get_handover(db, club.id, h.id)


@router.post("/handovers/{handover_id}/reseed")
async def reseed_handover(handover_id: str, _: User = _require, club: Organisation = Depends(get_current_club),
                          db: AsyncSession = Depends(get_db)):
    h = await svc.load_handover(db, club.id, _uuid(handover_id))
    if h is None:
        raise HTTPException(status_code=404, detail="Handover not found")
    added = await svc.reseed_handover(db, club.id, h)
    await db.commit()
    out = await svc.get_handover(db, club.id, h.id)
    out["added"] = added
    return out


@router.delete("/handovers/{handover_id}")
async def delete_handover(handover_id: str, _: User = _require, club: Organisation = Depends(get_current_club),
                          db: AsyncSession = Depends(get_db)):
    h = await svc.load_handover(db, club.id, _uuid(handover_id))
    if h is None:
        raise HTTPException(status_code=404, detail="Handover not found")
    await svc.delete_handover(db, h)
    await db.commit()
    return {"deleted": True}


# ─── Handover items ──────────────────────────────────────────────────────────

class ItemCreate(BaseModel):
    label: str
    detail: Optional[str] = None
    target_date: Optional[str] = None
    note: Optional[str] = None


@router.post("/handovers/{handover_id}/items")
async def add_item(handover_id: str, data: ItemCreate, _: User = _require,
                   club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    h = await svc.load_handover(db, club.id, _uuid(handover_id))
    if h is None:
        raise HTTPException(status_code=404, detail="Handover not found")
    try:
        await svc.add_item(db, club.id, h, label=data.label, detail=data.detail,
                           target_date=_parse_date(data.target_date), note=data.note)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return await svc.get_handover(db, club.id, h.id)


class ItemPatch(BaseModel):
    status: Optional[str] = None
    label: Optional[str] = None
    detail: Optional[str] = None
    target_date: Optional[str] = None
    note: Optional[str] = None


@router.patch("/handovers/{handover_id}/items/{item_id}")
async def update_item(handover_id: str, item_id: str, data: ItemPatch, current: User = _require,
                      club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    it = await svc.load_item(db, club.id, _uuid(handover_id), _uuid(item_id))
    if it is None:
        raise HTTPException(status_code=404, detail="Item not found")
    fields = data.model_dump(exclude_unset=True)
    if "target_date" in fields:
        fields["target_date"] = _parse_date(fields["target_date"])
    try:
        await svc.update_item(db, it, updated_by=current.id, **fields)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return await svc.get_handover(db, club.id, _uuid(handover_id))


@router.delete("/handovers/{handover_id}/items/{item_id}")
async def delete_item(handover_id: str, item_id: str, _: User = _require,
                      club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    it = await svc.load_item(db, club.id, _uuid(handover_id), _uuid(item_id))
    if it is None:
        raise HTTPException(status_code=404, detail="Item not found")
    await svc.delete_item(db, it)
    await db.commit()
    return await svc.get_handover(db, club.id, _uuid(handover_id))
