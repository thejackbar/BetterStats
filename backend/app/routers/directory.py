"""BetterClubManager Directory API — the club's people (core capability, not a
paid module). Players are owned by Stats/Core; this owns the non-player side:
add/edit/archive non-playing members + third parties, and assign roles to any
person. Gated on MANAGE_MEMBERS for writes; reads allow any of the ClubManager
people capabilities so the Directory opens for volunteer/committee/qual managers
too. See services/directory.py.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import User, Organisation, MembershipType, get_db
from app.routers.auth import get_current_club
from app.auth.capabilities import (
    require_cap, require_any_cap,
    MANAGE_MEMBERS, MANAGE_VOLUNTEERS, MANAGE_COMMITTEE, MANAGE_QUALIFICATIONS, MANAGE_FEES,
)
from app.services import directory as svc
from app.services import members as members_svc
from app.services import member_import as import_svc
from app.services import membership_types as membership_types_svc

router = APIRouter(prefix="/club-admin/directory", tags=["club-admin-directory"])
_read = Depends(require_any_cap(MANAGE_MEMBERS, MANAGE_VOLUNTEERS, MANAGE_COMMITTEE, MANAGE_QUALIFICATIONS))
_write = Depends(require_cap(MANAGE_MEMBERS))
# Importing people is a shared action — a BetterFees admin can bring in members too.
_import = Depends(require_any_cap(MANAGE_MEMBERS, MANAGE_FEES))


def _uuid(v):
    return uuid.UUID(v) if v else None


class MemberUpsert(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    mobile: Optional[str] = None
    member_category: Optional[str] = None
    notes: Optional[str] = None
    # The club's membership-type catalogue entry (Senior Player, Social Member,
    # Sponsor Contact…). Owned by the same `fee_members` row BetterFees edits;
    # "" clears it. Settable here so a club with no BetterFees can still say
    # what kind of member someone is.
    membership_type_id: Optional[str] = None


class RoleBody(BaseModel):
    role_id: str


class MemberTypesBody(BaseModel):
    """The WHOLE set the screen is showing, not a delta — see
    services/directory.set_member_types. `primary_id` is what BetterFees bills;
    omit it to leave the existing primary alone."""
    type_ids: list[str] = []
    primary_id: Optional[str] = "__keep__"


class LifeMembershipBody(BaseModel):
    is_life_member: bool
    # Omit to leave the recorded date alone; "" clears it.
    since: Optional[str] = "__keep__"


@router.get("/people")
async def list_people(include_archived: bool = False, _: User = _read, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    # The membership-type catalogue rides along with the people. Its own CRUD
    # lives in BetterFees (behind MANAGE_FEES + the fees module), which the
    # Directory's readers don't necessarily hold — so this reads the same
    # service directly rather than sending the screen to an endpoint that would
    # 403 for a volunteer or committee manager.
    return {
        "people": await svc.list_people(db, club.id, include_archived=include_archived),
        "categories": members_svc.MEMBER_CATEGORIES,
        "membership_types": await membership_types_svc.list_types(db, club.id),
    }


async def _resolved_type_id(db: AsyncSession, club: Organisation, raw: Optional[str]):
    """"" clears the type; anything else must be one of this club's own."""
    if raw in (None, ""):
        return None
    try:
        tid = uuid.UUID(raw)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=422, detail="Membership type not found")
    mt = await db.get(MembershipType, tid)
    if not mt or mt.organisation_id != club.id:
        raise HTTPException(status_code=422, detail="Membership type not found")
    return mt.id


@router.post("/people")
async def create_member(data: MemberUpsert, _: User = _write, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    try:
        mid = await members_svc.create_person(db, club.id, full_name=data.full_name, email=data.email,
                                               mobile=data.mobile, member_category=data.member_category, notes=data.notes,
                                               membership_type_id=await _resolved_type_id(db, club, data.membership_type_id))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"member_id": mid}


@router.patch("/people/{member_id}")
async def update_member(member_id: str, data: MemberUpsert, _: User = _write, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    fields = data.model_dump(exclude_unset=True)
    if "membership_type_id" in fields:
        fields["membership_type_id"] = await _resolved_type_id(db, club, fields["membership_type_id"])
    await members_svc.update_person(db, club.id, _uuid(member_id), **fields)
    await db.commit()
    return {"ok": True}


@router.post("/people/{member_id}/archive")
async def archive_member(member_id: str, _: User = _write, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    await members_svc.set_archived(db, club.id, _uuid(member_id), True)
    await db.commit()
    return {"ok": True}


@router.post("/people/{member_id}/restore")
async def restore_member(member_id: str, _: User = _write, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    await members_svc.set_archived(db, club.id, _uuid(member_id), False)
    await db.commit()
    return {"ok": True}


@router.post("/players/{player_id}/ensure-member")
async def ensure_member(player_id: str, _: User = _write, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    """Create (or find) the fee_members row for a Stats-owned player so it can be
    assigned ClubManager roles/quals. Idempotent."""
    try:
        mid = await members_svc.ensure_for_player(db, club.id, _uuid(player_id))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await db.commit()
    return {"member_id": mid}


@router.put("/people/{member_id}/membership-types")
async def set_member_types(member_id: str, data: MemberTypesBody, _: User = _write, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    try:
        res = await svc.set_member_types(db, club.id, _uuid(member_id), data.type_ids, data.primary_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return res


@router.post("/players/{player_id}/membership-types")
async def set_player_types(player_id: str, data: MemberTypesBody, _: User = _write, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    """Same, for a player who has no member row yet — mints one first.

    Membership is recorded against the person spine, and a read-through player
    has no row on it until something is recorded about them. Doing it here keeps
    ticking a box one request, the way assigning a role already is."""
    try:
        mid = await members_svc.ensure_for_player(db, club.id, _uuid(player_id))
        res = await svc.set_member_types(db, club.id, _uuid(mid), data.type_ids, data.primary_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"member_id": mid, **res}


@router.put("/people/{member_id}/life-membership")
async def set_life_membership(member_id: str, data: LifeMembershipBody, _: User = _write, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    try:
        await svc.set_life_membership(db, club.id, _uuid(member_id), data.is_life_member, data.since)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"ok": True}


@router.post("/players/{player_id}/life-membership")
async def set_player_life_membership(player_id: str, data: LifeMembershipBody, _: User = _write, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    try:
        mid = await members_svc.ensure_for_player(db, club.id, _uuid(player_id))
        await svc.set_life_membership(db, club.id, _uuid(mid), data.is_life_member, data.since)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"member_id": mid}


@router.post("/membership-types/seed")
async def seed_membership_types(_: User = _write, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    """Adopt the starter membership-type catalogue.

    Nothing seeds it automatically, so a club that has never opened BetterFees
    has no types to tick. Skip-don't-replace by name, like the starter committee
    positions and agenda templates, so pressing it twice can never overwrite a
    catalogue the club has edited."""
    seeded = await membership_types_svc.seed_starter_types(db, club.id)
    await db.commit()
    return {"seeded": seeded, "membership_types": await membership_types_svc.list_types(db, club.id)}


@router.post("/people/{member_id}/roles")
async def add_role(member_id: str, data: RoleBody, _: User = _write, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    try:
        await svc.add_role(db, club.id, _uuid(member_id), _uuid(data.role_id))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"ok": True}


@router.delete("/people/{member_id}/roles/{role_id}")
async def remove_role(member_id: str, role_id: str, _: User = _write, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    await svc.remove_role(db, club.id, _uuid(member_id), _uuid(role_id))
    await db.commit()
    return {"ok": True}


@router.get("/people/{member_id}/overlays")
async def member_overlays(member_id: str, _: User = _read, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    return await svc.member_overlays(db, club.id, _uuid(member_id))


@router.get("/committee-positions")
async def committee_positions(_: User = _read, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    return {"positions": await svc.list_positions(db, club.id)}


@router.get("/families")
async def families(_: User = _read, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    return {"families": await svc.list_families(db, club.id)}


class CommitteeBody(BaseModel):
    position_id: str


@router.post("/people/{member_id}/committee")
async def assign_committee(member_id: str, data: CommitteeBody, _: User = _write, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    try:
        await svc.assign_committee(db, club.id, _uuid(member_id), _uuid(data.position_id))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"ok": True}


@router.delete("/people/{member_id}/committee/{term_id}")
async def remove_committee(member_id: str, term_id: str, _: User = _write, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    await svc.remove_committee(db, club.id, _uuid(term_id))
    await db.commit()
    return {"ok": True}


class FamilyCreate(BaseModel):
    name: str


@router.post("/families")
async def create_family(data: FamilyCreate, _: User = _write, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    try:
        fid = await svc.create_family(db, club.id, data.name)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"family_id": fid}


class FamilyLinkBody(BaseModel):
    family_id: str
    relationship: Optional[str] = None
    is_guardian: Optional[bool] = False


@router.post("/people/{member_id}/families")
async def add_to_family(member_id: str, data: FamilyLinkBody, _: User = _write, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    try:
        await svc.add_to_family(db, club.id, _uuid(member_id), _uuid(data.family_id), relationship=data.relationship, is_guardian=data.is_guardian)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"ok": True}


@router.delete("/people/{member_id}/families/{family_id}")
async def remove_from_family(member_id: str, family_id: str, _: User = _write, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    await svc.remove_from_family(db, club.id, _uuid(member_id), _uuid(family_id))
    await db.commit()
    return {"ok": True}


# ── shared non-player CSV import (also used by BetterFees Members) ────────────
class ImportBody(BaseModel):
    csv: str


@router.post("/import/preview")
async def import_preview(data: ImportBody, _: User = _import, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    return await import_svc.preview(db, club.id, data.csv)


@router.post("/import/commit")
async def import_commit(data: ImportBody, _: User = _import, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    result = await import_svc.commit(db, club.id, data.csv)
    await db.commit()
    return result
