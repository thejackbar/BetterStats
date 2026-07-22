"""BetterCRM API — People/Contacts + the internal & club-facing Deal pipeline.

Two routers sharing one service layer (``services/crm.py``):
  - ``router`` (``/club-admin/crm``) — the club-facing CRM module, gated by
    MANAGE_CRM (the whole router is also module-gated by require_module
    ("crm") at include time — see main.py).
  - ``super_router`` (``/club-admin/super/crm``) — BetterCricket's own
    internal sales pipeline, cross-club platform tooling gated by
    require_super_admin (same posture as marketing.py), NOT a per-club
    capability.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Organisation, MarketingClub, get_db
from app.routers.auth import get_current_user, get_current_club, require_super_admin
from app.auth.capabilities import require_cap, MANAGE_CRM
from app.services import crm as crm_service

router = APIRouter(prefix="/club-admin/crm", tags=["crm"])
super_router = APIRouter(prefix="/club-admin/super/crm", tags=["crm-platform"])

_require = Depends(require_cap(MANAGE_CRM))
_super = Depends(require_super_admin)


# ─── Bodies ───────────────────────────────────────────────────────────────────

class DealCreate(BaseModel):
    title: str
    stage_key: Optional[str] = None
    stage_id: Optional[str] = None
    value_cents: int = 0
    currency: str = "AUD"
    probability: Optional[int] = None
    module_keys: List[str] = []
    expected_close_date: Optional[date] = None
    owner_user_id: Optional[str] = None
    marketing_club_id: Optional[str] = None  # platform scope only


class DealUpdate(BaseModel):
    title: Optional[str] = None
    value_cents: Optional[int] = None
    currency: Optional[str] = None
    probability: Optional[int] = None
    module_keys: Optional[List[str]] = None
    expected_close_date: Optional[date] = None
    owner_user_id: Optional[str] = None


class StageMoveBody(BaseModel):
    stage_id: str
    probability: Optional[int] = None


class CloseBody(BaseModel):
    status: str  # won | lost
    lost_reason: Optional[str] = None


class ActivityCreate(BaseModel):
    type: str = "note"
    body: Optional[str] = None


class PersonCreate(BaseModel):
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None


class PersonUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None


class RoleCreate(BaseModel):
    role: str
    title: Optional[str] = None
    started_at: Optional[date] = None
    ended_at: Optional[date] = None
    notes: Optional[str] = None


class DealContactBody(BaseModel):
    person_id: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    role_on_deal: Optional[str] = None


class ConvertToDealBody(BaseModel):
    stage_key: str = "qualified"
    module_keys: List[str] = []
    value_cents: Optional[int] = None
    title: Optional[str] = None


# ─── Shared helpers (parameterised by scope/org) ─────────────────────────────

def _uuid_or_404(raw: str):
    try:
        return uuid.UUID(str(raw))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=422, detail="Invalid id")


async def _stage_or_404(db: AsyncSession, scope: str, organisation_id, stage_id: str):
    pipeline = await crm_service.ensure_pipeline(db, scope, organisation_id)
    stage = next((s for s in pipeline.stages if str(s.id) == str(stage_id)), None)
    if stage is None:
        raise HTTPException(status_code=404, detail="Stage not found")
    return pipeline, stage


async def _deal_or_404(db: AsyncSession, scope: str, organisation_id, deal_id: str):
    deal = await crm_service.get_deal(db, _uuid_or_404(deal_id), scope, organisation_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    return deal


async def _serialize_deal(db: AsyncSession, deal, scope: str, organisation_id) -> dict:
    pipeline = await crm_service.ensure_pipeline(db, scope, organisation_id)
    stage = next((s for s in pipeline.stages if s.id == deal.stage_id), None)
    return crm_service._deal_dict(deal, stage)


async def _list_deals_response(db: AsyncSession, scope: str, organisation_id,
                               status: Optional[str], include_archived: bool) -> dict:
    pipeline = await crm_service.ensure_pipeline(db, scope, organisation_id)
    stage_by_id = {s.id: s for s in pipeline.stages}
    deals = await crm_service.list_deals(db, scope, organisation_id, status=status,
                                        include_archived=include_archived)
    return {"deals": [crm_service._deal_dict(d, stage_by_id.get(d.stage_id)) for d in deals]}


async def _create_deal(db: AsyncSession, scope: str, organisation_id, body: DealCreate,
                       marketing_club_id=None) -> dict:
    pipeline = await crm_service.ensure_pipeline(db, scope, organisation_id)
    stage = None
    if body.stage_id:
        stage = next((s for s in pipeline.stages if str(s.id) == body.stage_id), None)
    elif body.stage_key:
        stage = next((s for s in pipeline.stages if s.key == body.stage_key), None)
    if stage is None:
        stage = pipeline.stages[0]  # default: first stage
    deal = await crm_service.create_deal(
        db, scope=scope, pipeline_id=pipeline.id, stage_id=stage.id, title=body.title,
        organisation_id=organisation_id, marketing_club_id=marketing_club_id,
        value_cents=body.value_cents, currency=body.currency, probability=body.probability,
        module_keys=body.module_keys, expected_close_date=body.expected_close_date,
        owner_user_id=_uuid_or_404(body.owner_user_id) if body.owner_user_id else None,
        source="manual",
    )
    await db.commit()
    return await _serialize_deal(db, deal, scope, organisation_id)


async def _resolve_contact_person(db: AsyncSession, body: DealContactBody, *,
                                  organisation_id=None, marketing_club_id=None):
    if body.person_id:
        from app.models.db import CrmPerson
        person = await db.get(CrmPerson, _uuid_or_404(body.person_id))
        if person is None:
            raise HTTPException(status_code=404, detail="Person not found")
        return person
    if not body.full_name:
        raise HTTPException(status_code=422, detail="person_id or full_name is required")
    return await crm_service.resolve_person(
        db, full_name=body.full_name, organisation_id=organisation_id,
        marketing_club_id=marketing_club_id, email=body.email, phone=body.phone,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Club-scope router (BetterAdmin CRM module)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/pipeline", dependencies=[_require])
async def club_pipeline(club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    return await crm_service.pipeline_board(db, crm_service.SCOPE_CLUB, club.id)


@router.get("/stages", dependencies=[_require])
async def club_stages(club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    return {"stages": await crm_service.list_stages(db, crm_service.SCOPE_CLUB, club.id)}


@router.get("/deals", dependencies=[_require])
async def club_list_deals(status: Optional[str] = None, include_archived: bool = False,
                          club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    return await _list_deals_response(db, crm_service.SCOPE_CLUB, club.id, status, include_archived)


@router.post("/deals", dependencies=[_require])
async def club_create_deal(body: DealCreate, club: Organisation = Depends(get_current_club),
                           db: AsyncSession = Depends(get_db)):
    return await _create_deal(db, crm_service.SCOPE_CLUB, club.id, body)


@router.get("/deals/{deal_id}", dependencies=[_require])
async def club_get_deal(deal_id: str, club: Organisation = Depends(get_current_club),
                        db: AsyncSession = Depends(get_db)):
    deal = await _deal_or_404(db, crm_service.SCOPE_CLUB, club.id, deal_id)
    return await _serialize_deal(db, deal, crm_service.SCOPE_CLUB, club.id)


@router.patch("/deals/{deal_id}", dependencies=[_require])
async def club_update_deal(deal_id: str, body: DealUpdate, club: Organisation = Depends(get_current_club),
                           db: AsyncSession = Depends(get_db)):
    deal = await _deal_or_404(db, crm_service.SCOPE_CLUB, club.id, deal_id)
    await crm_service.update_deal(db, deal, **body.model_dump(exclude_unset=True))
    await db.commit()
    return await _serialize_deal(db, deal, crm_service.SCOPE_CLUB, club.id)


@router.post("/deals/{deal_id}/stage", dependencies=[_require])
async def club_move_stage(deal_id: str, body: StageMoveBody, club: Organisation = Depends(get_current_club),
                          db: AsyncSession = Depends(get_db)):
    deal = await _deal_or_404(db, crm_service.SCOPE_CLUB, club.id, deal_id)
    _, stage = await _stage_or_404(db, crm_service.SCOPE_CLUB, club.id, body.stage_id)
    await crm_service.move_stage(db, deal, stage, probability=body.probability)
    await db.commit()
    return await _serialize_deal(db, deal, crm_service.SCOPE_CLUB, club.id)


@router.post("/deals/{deal_id}/close", dependencies=[_require])
async def club_close_deal(deal_id: str, body: CloseBody, club: Organisation = Depends(get_current_club),
                          db: AsyncSession = Depends(get_db)):
    if body.status not in ("won", "lost"):
        raise HTTPException(status_code=422, detail="status must be 'won' or 'lost'")
    deal = await _deal_or_404(db, crm_service.SCOPE_CLUB, club.id, deal_id)
    pipeline = await crm_service.ensure_pipeline(db, crm_service.SCOPE_CLUB, club.id)
    await crm_service.close_deal(db, deal, pipeline, status=body.status, lost_reason=body.lost_reason)
    await db.commit()
    return await _serialize_deal(db, deal, crm_service.SCOPE_CLUB, club.id)


@router.delete("/deals/{deal_id}", dependencies=[_require])
async def club_archive_deal(deal_id: str, club: Organisation = Depends(get_current_club),
                            db: AsyncSession = Depends(get_db)):
    deal = await _deal_or_404(db, crm_service.SCOPE_CLUB, club.id, deal_id)
    await crm_service.archive_deal(db, deal)
    await db.commit()
    return {"archived": True}


@router.get("/deals/{deal_id}/activities", dependencies=[_require])
async def club_list_activities(deal_id: str, club: Organisation = Depends(get_current_club),
                               db: AsyncSession = Depends(get_db)):
    deal = await _deal_or_404(db, crm_service.SCOPE_CLUB, club.id, deal_id)
    rows = await crm_service.list_activities(db, deal_id=deal.id)
    return {"activities": [crm_service._activity_dict(a) for a in rows]}


@router.post("/deals/{deal_id}/activities", dependencies=[_require])
async def club_log_activity(deal_id: str, body: ActivityCreate, club: Organisation = Depends(get_current_club),
                            current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    deal = await _deal_or_404(db, crm_service.SCOPE_CLUB, club.id, deal_id)
    activity = await crm_service.log_activity(
        db, deal_id=deal.id, organisation_id=club.id, type=body.type, body=body.body,
        created_by_user_id=current_user.id)
    await db.commit()
    return crm_service._activity_dict(activity)


@router.get("/deals/{deal_id}/contacts", dependencies=[_require])
async def club_list_contacts(deal_id: str, club: Organisation = Depends(get_current_club),
                             db: AsyncSession = Depends(get_db)):
    deal = await _deal_or_404(db, crm_service.SCOPE_CLUB, club.id, deal_id)
    return {"contacts": await crm_service.list_deal_contacts(db, deal.id)}


@router.post("/deals/{deal_id}/contacts", dependencies=[_require])
async def club_link_contact(deal_id: str, body: DealContactBody, club: Organisation = Depends(get_current_club),
                            db: AsyncSession = Depends(get_db)):
    deal = await _deal_or_404(db, crm_service.SCOPE_CLUB, club.id, deal_id)
    person = await _resolve_contact_person(db, body, organisation_id=club.id)
    await crm_service.link_deal_contact(db, deal.id, person.id, body.role_on_deal)
    await db.commit()
    return crm_service._person_dict(person)


@router.delete("/deals/{deal_id}/contacts/{person_id}", dependencies=[_require])
async def club_unlink_contact(deal_id: str, person_id: str, club: Organisation = Depends(get_current_club),
                              db: AsyncSession = Depends(get_db)):
    deal = await _deal_or_404(db, crm_service.SCOPE_CLUB, club.id, deal_id)
    ok = await crm_service.unlink_deal_contact(db, deal.id, _uuid_or_404(person_id))
    await db.commit()
    return {"unlinked": ok}


@router.get("/people", dependencies=[_require])
async def club_list_people(q: Optional[str] = None, club: Organisation = Depends(get_current_club),
                           db: AsyncSession = Depends(get_db)):
    rows = await crm_service.list_people(db, organisation_id=club.id, q=q)
    return {"people": [crm_service._person_dict(p) for p in rows]}


@router.post("/people", dependencies=[_require])
async def club_create_person(body: PersonCreate, club: Organisation = Depends(get_current_club),
                             db: AsyncSession = Depends(get_db)):
    person = await crm_service.resolve_person(
        db, full_name=body.full_name, organisation_id=club.id, email=body.email, phone=body.phone)
    if body.notes:
        person.notes = body.notes
    await db.commit()
    return crm_service._person_dict(person)


@router.patch("/people/{person_id}", dependencies=[_require])
async def club_update_person(person_id: str, body: PersonUpdate, club: Organisation = Depends(get_current_club),
                             db: AsyncSession = Depends(get_db)):
    from app.models.db import CrmPerson
    person = await db.get(CrmPerson, _uuid_or_404(person_id))
    if person is None or str(person.organisation_id) != str(club.id):
        raise HTTPException(status_code=404, detail="Person not found")
    for field in ("full_name", "email", "phone", "notes"):
        val = getattr(body, field)
        if val is not None:
            setattr(person, field, val)
    await db.commit()
    return crm_service._person_dict(person)


@router.post("/people/{person_id}/roles", dependencies=[_require])
async def club_add_person_role(person_id: str, body: RoleCreate, club: Organisation = Depends(get_current_club),
                               db: AsyncSession = Depends(get_db)):
    from app.models.db import CrmPerson
    person = await db.get(CrmPerson, _uuid_or_404(person_id))
    if person is None or str(person.organisation_id) != str(club.id):
        raise HTTPException(status_code=404, detail="Person not found")
    await crm_service.add_person_role(
        db, person.id, role=body.role, organisation_id=club.id, title=body.title,
        started_at=body.started_at, ended_at=body.ended_at, notes=body.notes)
    await db.commit()
    await db.refresh(person, attribute_names=["roles"])
    return crm_service._person_dict(person)


# ═══════════════════════════════════════════════════════════════════════════
# Platform-scope router (BetterCricket's own internal sales pipeline)
# ═══════════════════════════════════════════════════════════════════════════

@super_router.get("/pipeline", dependencies=[_super])
async def super_pipeline(db: AsyncSession = Depends(get_db)):
    return await crm_service.pipeline_board(db, crm_service.SCOPE_PLATFORM)


@super_router.get("/stages", dependencies=[_super])
async def super_stages(db: AsyncSession = Depends(get_db)):
    return {"stages": await crm_service.list_stages(db, crm_service.SCOPE_PLATFORM)}


@super_router.get("/deals", dependencies=[_super])
async def super_list_deals(status: Optional[str] = None, include_archived: bool = False,
                           db: AsyncSession = Depends(get_db)):
    return await _list_deals_response(db, crm_service.SCOPE_PLATFORM, None, status, include_archived)


@super_router.post("/deals", dependencies=[_super])
async def super_create_deal(body: DealCreate, db: AsyncSession = Depends(get_db)):
    marketing_club_id = _uuid_or_404(body.marketing_club_id) if body.marketing_club_id else None
    return await _create_deal(db, crm_service.SCOPE_PLATFORM, None, body, marketing_club_id=marketing_club_id)


@super_router.get("/deals/{deal_id}", dependencies=[_super])
async def super_get_deal(deal_id: str, db: AsyncSession = Depends(get_db)):
    deal = await _deal_or_404(db, crm_service.SCOPE_PLATFORM, None, deal_id)
    return await _serialize_deal(db, deal, crm_service.SCOPE_PLATFORM, None)


@super_router.patch("/deals/{deal_id}", dependencies=[_super])
async def super_update_deal(deal_id: str, body: DealUpdate, db: AsyncSession = Depends(get_db)):
    deal = await _deal_or_404(db, crm_service.SCOPE_PLATFORM, None, deal_id)
    await crm_service.update_deal(db, deal, **body.model_dump(exclude_unset=True))
    await db.commit()
    return await _serialize_deal(db, deal, crm_service.SCOPE_PLATFORM, None)


@super_router.post("/deals/{deal_id}/stage", dependencies=[_super])
async def super_move_stage(deal_id: str, body: StageMoveBody, db: AsyncSession = Depends(get_db)):
    deal = await _deal_or_404(db, crm_service.SCOPE_PLATFORM, None, deal_id)
    _, stage = await _stage_or_404(db, crm_service.SCOPE_PLATFORM, None, body.stage_id)
    await crm_service.move_stage(db, deal, stage, probability=body.probability)
    await db.commit()
    return await _serialize_deal(db, deal, crm_service.SCOPE_PLATFORM, None)


@super_router.post("/deals/{deal_id}/close", dependencies=[_super])
async def super_close_deal(deal_id: str, body: CloseBody, db: AsyncSession = Depends(get_db)):
    if body.status not in ("won", "lost"):
        raise HTTPException(status_code=422, detail="status must be 'won' or 'lost'")
    deal = await _deal_or_404(db, crm_service.SCOPE_PLATFORM, None, deal_id)
    pipeline = await crm_service.ensure_pipeline(db, crm_service.SCOPE_PLATFORM)
    await crm_service.close_deal(db, deal, pipeline, status=body.status, lost_reason=body.lost_reason)
    await db.commit()
    return await _serialize_deal(db, deal, crm_service.SCOPE_PLATFORM, None)


@super_router.delete("/deals/{deal_id}", dependencies=[_super])
async def super_archive_deal(deal_id: str, db: AsyncSession = Depends(get_db)):
    deal = await _deal_or_404(db, crm_service.SCOPE_PLATFORM, None, deal_id)
    await crm_service.archive_deal(db, deal)
    await db.commit()
    return {"archived": True}


@super_router.get("/deals/{deal_id}/activities", dependencies=[_super])
async def super_list_activities(deal_id: str, db: AsyncSession = Depends(get_db)):
    deal = await _deal_or_404(db, crm_service.SCOPE_PLATFORM, None, deal_id)
    rows = await crm_service.list_activities(db, deal_id=deal.id)
    return {"activities": [crm_service._activity_dict(a) for a in rows]}


@super_router.post("/deals/{deal_id}/activities", dependencies=[_super])
async def super_log_activity(deal_id: str, body: ActivityCreate, current_user=Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    deal = await _deal_or_404(db, crm_service.SCOPE_PLATFORM, None, deal_id)
    activity = await crm_service.log_activity(
        db, deal_id=deal.id, type=body.type, body=body.body, created_by_user_id=current_user.id)
    await db.commit()
    return crm_service._activity_dict(activity)


@super_router.get("/deals/{deal_id}/contacts", dependencies=[_super])
async def super_list_contacts(deal_id: str, db: AsyncSession = Depends(get_db)):
    deal = await _deal_or_404(db, crm_service.SCOPE_PLATFORM, None, deal_id)
    return {"contacts": await crm_service.list_deal_contacts(db, deal.id)}


@super_router.post("/deals/{deal_id}/contacts", dependencies=[_super])
async def super_link_contact(deal_id: str, body: DealContactBody, db: AsyncSession = Depends(get_db)):
    deal = await _deal_or_404(db, crm_service.SCOPE_PLATFORM, None, deal_id)
    person = await _resolve_contact_person(db, body, marketing_club_id=deal.marketing_club_id)
    await crm_service.link_deal_contact(db, deal.id, person.id, body.role_on_deal)
    await db.commit()
    return crm_service._person_dict(person)


@super_router.delete("/deals/{deal_id}/contacts/{person_id}", dependencies=[_super])
async def super_unlink_contact(deal_id: str, person_id: str, db: AsyncSession = Depends(get_db)):
    deal = await _deal_or_404(db, crm_service.SCOPE_PLATFORM, None, deal_id)
    ok = await crm_service.unlink_deal_contact(db, deal.id, _uuid_or_404(person_id))
    await db.commit()
    return {"unlinked": ok}


@super_router.get("/people", dependencies=[_super])
async def super_list_people(q: Optional[str] = None, marketing_club_id: Optional[str] = None,
                            db: AsyncSession = Depends(get_db)):
    rows = await crm_service.list_people(
        db, marketing_club_id=_uuid_or_404(marketing_club_id) if marketing_club_id else None, q=q)
    return {"people": [crm_service._person_dict(p) for p in rows]}


@super_router.post("/people", dependencies=[_super])
async def super_create_person(body: PersonCreate, marketing_club_id: Optional[str] = None,
                              db: AsyncSession = Depends(get_db)):
    person = await crm_service.resolve_person(
        db, full_name=body.full_name,
        marketing_club_id=_uuid_or_404(marketing_club_id) if marketing_club_id else None,
        email=body.email, phone=body.phone)
    if body.notes:
        person.notes = body.notes
    await db.commit()
    return crm_service._person_dict(person)


@super_router.patch("/people/{person_id}", dependencies=[_super])
async def super_update_person(person_id: str, body: PersonUpdate, db: AsyncSession = Depends(get_db)):
    from app.models.db import CrmPerson
    person = await db.get(CrmPerson, _uuid_or_404(person_id))
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    for field in ("full_name", "email", "phone", "notes"):
        val = getattr(body, field)
        if val is not None:
            setattr(person, field, val)
    await db.commit()
    return crm_service._person_dict(person)


@super_router.post("/from-club/{marketing_club_id}", dependencies=[_super])
async def super_convert_club_to_deal(marketing_club_id: str, body: ConvertToDealBody,
                                     db: AsyncSession = Depends(get_db)):
    """Manually turn a prospect Club/Lead into a Deal — the "Super Admin
    elects to" path (auto-creation from an enquiry/trial is the other one,
    see services/crm.py's sync_platform_deal_for_club)."""
    club = await db.get(MarketingClub, _uuid_or_404(marketing_club_id))
    if club is None:
        raise HTTPException(status_code=404, detail="Club not found")
    deal = await crm_service.sync_platform_deal_for_club(
        db, club, stage_key=body.stage_key, source="manual", module_keys=body.module_keys,
        advance_only=False)
    if body.value_cents is not None:
        deal.value_cents = body.value_cents
    if body.title:
        deal.title = body.title
    await db.commit()
    return await _serialize_deal(db, deal, crm_service.SCOPE_PLATFORM, None)
