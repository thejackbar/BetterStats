"""BetterCRM API — People/Contacts + the internal & club-facing Deal pipeline.

Two routers sharing one service layer (``services/crm.py``):
  - ``router`` (``/club-admin/crm``) — the club-facing CRM module, gated by
    MANAGE_CRM (the whole router is also module-gated by require_module
    ("crm") at include time — see main.py). Club-scope pipelines are opt-in
    "trackers" (a club adds zero or more from a preset catalogue, or builds a
    fully custom one) rather than one auto-seeded default — see
    services/crm.py's PIPELINE_TEMPLATES for why.
  - ``super_router`` (``/club-admin/super/crm``) — BetterCricket's own
    internal sales pipeline, cross-club platform tooling gated by
    require_super_admin (same posture as marketing.py), NOT a per-club
    capability. Exactly one pipeline always exists here (not optional).
"""
from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Organisation, MarketingClub, CrmStage, CrmPipeline, get_db
from app.routers.auth import get_current_user, get_current_club, require_super_admin
from app.auth.capabilities import require_cap, MANAGE_CRM
from app.services import crm as crm_service
from app.services import crm_targets
from app.services import crm_rules
from app.services import stripe_client

logger = logging.getLogger(__name__)

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
    onboarding_method: Optional[str] = None
    lead_source: Optional[str] = None


class DealUpdate(BaseModel):
    title: Optional[str] = None
    value_cents: Optional[int] = None
    currency: Optional[str] = None
    probability: Optional[int] = None
    module_keys: Optional[List[str]] = None
    expected_close_date: Optional[date] = None
    owner_user_id: Optional[str] = None
    onboarding_method: Optional[str] = None
    lead_source: Optional[str] = None
    discount_amount_cents: Optional[int] = None
    discount_percent: Optional[int] = None
    discount_reason: Optional[str] = None


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
    stage_key: str = "engaged"
    module_keys: List[str] = []
    value_cents: Optional[int] = None
    title: Optional[str] = None


class AddTrackerBody(BaseModel):
    template_key: Optional[str] = None
    name: Optional[str] = None  # required when template_key is omitted (a custom tracker)


class TargetUpsert(BaseModel):
    period_type: str  # month | quarter | fiscal_year
    period_key: str   # '2026-07' | '2026-Q3' | 'FY2026'
    target_clubs_won: Optional[int] = None
    target_arr_cents: Optional[int] = None
    target_revenue_cents: Optional[int] = None
    target_trials: Optional[int] = None
    target_conversion_rate: Optional[int] = None
    notes: Optional[str] = None


class StageCreate(BaseModel):
    name: str
    default_probability: int = 0
    is_won: bool = False
    is_lost: bool = False
    hidden_from_board: bool = False


class StageUpdate(BaseModel):
    name: Optional[str] = None
    default_probability: Optional[int] = None
    is_won: Optional[bool] = None
    is_lost: Optional[bool] = None
    position: Optional[int] = None
    hidden_from_board: Optional[bool] = None


# ─── Shared helpers ───────────────────────────────────────────────────────────

def _uuid_or_404(raw: str):
    try:
        return uuid.UUID(str(raw))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=422, detail="Invalid id")


async def _deal_or_404(db: AsyncSession, scope: str, organisation_id, deal_id: str):
    deal = await crm_service.get_deal(db, _uuid_or_404(deal_id), scope, organisation_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    return deal


async def _serialize_deal(db: AsyncSession, deal) -> dict:
    # move_stage/update_deal/close_deal all set deal.updated_at = func.now() —
    # assigning a raw SQL expression to a mapped column always marks it
    # expired after flush (SQLAlchemy has no Python-side value for it), not
    # just on commit. Every caller here runs this right after `await
    # db.commit()`, so without an explicit async refresh the plain attribute
    # access below (deal.updated_at, deal.marketing_club_id, …) would try to
    # lazy-load outside an awaited context and raise MissingGreenlet — the
    # write itself already succeeded, only this response serialization step
    # was failing (confirmed via a live "moved but 500'd" report + traceback,
    # 2026-07-24).
    await db.refresh(deal)
    pipeline = await crm_service.get_deal_pipeline(db, deal)
    stage = next((s for s in (pipeline.stages if pipeline else []) if s.id == deal.stage_id), None)
    club = await db.get(MarketingClub, deal.marketing_club_id) if deal.marketing_club_id else None
    row = crm_service._deal_dict(deal, stage, club)
    trial_days, subscribed = None, None
    if club is not None:
        try:
            by_club = await crm_service.trial_days_remaining_by_club(db, {club.id: club})
            trial_days = by_club.get(club.id)
        except Exception:  # noqa: BLE001 - a nice-to-have display field, never worth failing the deal fetch
            logger.exception("_serialize_deal: trial_days_remaining_by_club failed")
        try:
            by_club_subs = await crm_service.subscribed_modules_by_club(db, {club.id: club})
            subscribed = by_club_subs.get(club.id)
        except Exception:  # noqa: BLE001
            logger.exception("_serialize_deal: subscribed_modules_by_club failed")
    row["trial_days_remaining"] = trial_days
    row["min_trial_days_remaining"] = min(trial_days.values()) if trial_days else None
    row["subscribed_modules"] = subscribed or []
    return row


async def _deal_stage_or_404(db: AsyncSession, deal, stage_id: str):
    pipeline = await crm_service.get_deal_pipeline(db, deal)
    stage = next((s for s in (pipeline.stages if pipeline else []) if str(s.id) == str(stage_id)), None)
    if pipeline is None or stage is None:
        raise HTTPException(status_code=404, detail="Stage not found")
    return pipeline, stage


async def _list_deals_response(db: AsyncSession, pipeline: CrmPipeline,
                               status: Optional[str], include_archived: bool) -> dict:
    stage_by_id = {s.id: s for s in pipeline.stages}
    deals = await crm_service.list_deals(db, pipeline.id, status=status, include_archived=include_archived)
    club_by_id = await crm_service.clubs_by_ids(db, (d.marketing_club_id for d in deals))
    return {"deals": [crm_service._deal_dict(d, stage_by_id.get(d.stage_id), club_by_id.get(d.marketing_club_id))
                      for d in deals]}


async def _create_deal_in_pipeline(db: AsyncSession, pipeline: CrmPipeline, scope: str,
                                   organisation_id, marketing_club_id, body: DealCreate) -> dict:
    stage = None
    if body.stage_id:
        stage = next((s for s in pipeline.stages if str(s.id) == body.stage_id), None)
    elif body.stage_key:
        stage = next((s for s in pipeline.stages if s.key == body.stage_key), None)
    if stage is None:
        stage = pipeline.stages[0]
    deal = await crm_service.create_deal(
        db, scope=scope, pipeline_id=pipeline.id, stage_id=stage.id, title=body.title,
        organisation_id=organisation_id, marketing_club_id=marketing_club_id,
        value_cents=body.value_cents, currency=body.currency, probability=body.probability,
        module_keys=body.module_keys, expected_close_date=body.expected_close_date,
        owner_user_id=_uuid_or_404(body.owner_user_id) if body.owner_user_id else None,
        source="manual", onboarding_method=body.onboarding_method, lead_source=body.lead_source,
    )
    await db.commit()
    return await _serialize_deal(db, deal)


async def _update_deal_or_422(db: AsyncSession, deal, **fields) -> None:
    try:
        await crm_service.update_deal(db, deal, **fields)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


async def _resolve_contact_person(db: AsyncSession, body: DealContactBody, *,
                                  organisation_id=None, marketing_club_id=None):
    if body.person_id:
        person = await crm_service.get_person(db, _uuid_or_404(body.person_id))
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
# Club-scope router (BetterAdmin CRM module) — opt-in trackers
# ═══════════════════════════════════════════════════════════════════════════

async def _pipeline_or_404(db: AsyncSession, organisation_id, pipeline_id: str) -> CrmPipeline:
    pipeline = await crm_service.get_pipeline_for_org(db, _uuid_or_404(pipeline_id), organisation_id)
    if pipeline is None:
        raise HTTPException(status_code=404, detail="Tracker not found")
    return pipeline


async def _club_stage_or_404(db: AsyncSession, organisation_id, stage_id: str) -> CrmStage:
    stage = await db.get(CrmStage, _uuid_or_404(stage_id))
    if stage is None:
        raise HTTPException(status_code=404, detail="Stage not found")
    pipeline = await db.get(CrmPipeline, stage.pipeline_id)
    if (pipeline is None or pipeline.scope != crm_service.SCOPE_CLUB
            or str(pipeline.organisation_id) != str(organisation_id)):
        raise HTTPException(status_code=404, detail="Stage not found")
    return stage


async def _platform_stage_or_404(db: AsyncSession, stage_id: str) -> CrmStage:
    stage = await db.get(CrmStage, _uuid_or_404(stage_id))
    if stage is None:
        raise HTTPException(status_code=404, detail="Stage not found")
    pipeline = await db.get(CrmPipeline, stage.pipeline_id)
    if pipeline is None or pipeline.scope != crm_service.SCOPE_PLATFORM:
        raise HTTPException(status_code=404, detail="Stage not found")
    return stage


@router.get("/trackers", dependencies=[_require])
async def club_tracker_catalogue(club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    return await crm_service.tracker_catalogue(db, club.id)


@router.get("/trackers/active", dependencies=[_require])
async def club_active_trackers(club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    return {"trackers": await crm_service.active_trackers(db, club.id)}


@router.post("/trackers", dependencies=[_require])
async def club_add_tracker(body: AddTrackerBody, club: Organisation = Depends(get_current_club),
                           db: AsyncSession = Depends(get_db)):
    try:
        pipeline = await crm_service.add_tracker(db, club.id, template_key=body.template_key, name=body.name)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": str(pipeline.id), "name": pipeline.name, "template_key": pipeline.template_key,
            "terms": crm_service.terms_for_pipeline(pipeline)}


@router.delete("/trackers/{pipeline_id}", dependencies=[_require])
async def club_remove_tracker(pipeline_id: str, club: Organisation = Depends(get_current_club),
                              db: AsyncSession = Depends(get_db)):
    pipeline = await _pipeline_or_404(db, club.id, pipeline_id)
    await crm_service.deactivate_tracker(db, pipeline)
    await db.commit()
    return {"deactivated": True}


@router.post("/trackers/{pipeline_id}/reactivate", dependencies=[_require])
async def club_reactivate_tracker(pipeline_id: str, club: Organisation = Depends(get_current_club),
                                  db: AsyncSession = Depends(get_db)):
    pipeline = await _pipeline_or_404(db, club.id, pipeline_id)
    await crm_service.reactivate_tracker(db, pipeline)
    await db.commit()
    return {"id": str(pipeline.id), "name": pipeline.name, "template_key": pipeline.template_key,
            "terms": crm_service.terms_for_pipeline(pipeline)}


@router.get("/pipelines/{pipeline_id}/board", dependencies=[_require])
async def club_pipeline_board(pipeline_id: str, club: Organisation = Depends(get_current_club),
                              db: AsyncSession = Depends(get_db)):
    pipeline = await _pipeline_or_404(db, club.id, pipeline_id)
    deals = await crm_service.list_deals(db, pipeline.id)
    return crm_service.pipeline_board(pipeline, deals)


@router.get("/pipelines/{pipeline_id}/stages", dependencies=[_require])
async def club_stages(pipeline_id: str, club: Organisation = Depends(get_current_club),
                      db: AsyncSession = Depends(get_db)):
    pipeline = await _pipeline_or_404(db, club.id, pipeline_id)
    return {"stages": crm_service.stage_dicts(pipeline)}


@router.post("/pipelines/{pipeline_id}/stages", dependencies=[_require])
async def club_add_stage(pipeline_id: str, body: StageCreate, club: Organisation = Depends(get_current_club),
                         db: AsyncSession = Depends(get_db)):
    pipeline = await _pipeline_or_404(db, club.id, pipeline_id)
    await crm_service.add_stage(db, pipeline, name=body.name, default_probability=body.default_probability,
                                is_won=body.is_won, is_lost=body.is_lost, hidden_from_board=body.hidden_from_board)
    await db.commit()
    pipeline = await _pipeline_or_404(db, club.id, pipeline_id)
    return {"stages": crm_service.stage_dicts(pipeline)}


@router.patch("/stages/{stage_id}", dependencies=[_require])
async def club_update_stage(stage_id: str, body: StageUpdate, club: Organisation = Depends(get_current_club),
                            db: AsyncSession = Depends(get_db)):
    stage = await _club_stage_or_404(db, club.id, stage_id)
    await crm_service.update_stage(db, stage, **body.model_dump(exclude_unset=True))
    await db.commit()
    return {"id": str(stage.id), "key": stage.key, "name": stage.name, "position": stage.position,
            "default_probability": stage.default_probability, "is_won": stage.is_won, "is_lost": stage.is_lost,
            "hidden_from_board": stage.hidden_from_board}


@router.delete("/stages/{stage_id}", dependencies=[_require])
async def club_delete_stage(stage_id: str, club: Organisation = Depends(get_current_club),
                            db: AsyncSession = Depends(get_db)):
    stage = await _club_stage_or_404(db, club.id, stage_id)
    try:
        await crm_service.delete_stage(db, stage)
        await db.commit()
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(e))
    except IntegrityError:
        # The empty-check and the actual DELETE aren't atomic — a deal can
        # land in this exact stage in between (e.g. a background CRM-sync
        # write from a live self-serve trial signup), which only shows up as
        # a DB-level FK violation at commit time, not the ValueError above.
        await db.rollback()
        raise HTTPException(status_code=409,
                           detail="A new record was just added to this stage — move or archive it, then try again")
    return {"deleted": True}


@router.get("/pipelines/{pipeline_id}/deals", dependencies=[_require])
async def club_list_deals(pipeline_id: str, status: Optional[str] = None, include_archived: bool = False,
                          club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    pipeline = await _pipeline_or_404(db, club.id, pipeline_id)
    return await _list_deals_response(db, pipeline, status, include_archived)


@router.post("/pipelines/{pipeline_id}/deals", dependencies=[_require])
async def club_create_deal(pipeline_id: str, body: DealCreate, club: Organisation = Depends(get_current_club),
                           db: AsyncSession = Depends(get_db)):
    pipeline = await _pipeline_or_404(db, club.id, pipeline_id)
    return await _create_deal_in_pipeline(db, pipeline, crm_service.SCOPE_CLUB, club.id, None, body)


@router.get("/deals/{deal_id}", dependencies=[_require])
async def club_get_deal(deal_id: str, club: Organisation = Depends(get_current_club),
                        db: AsyncSession = Depends(get_db)):
    deal = await _deal_or_404(db, crm_service.SCOPE_CLUB, club.id, deal_id)
    return await _serialize_deal(db, deal)


@router.patch("/deals/{deal_id}", dependencies=[_require])
async def club_update_deal(deal_id: str, body: DealUpdate, club: Organisation = Depends(get_current_club),
                           db: AsyncSession = Depends(get_db)):
    deal = await _deal_or_404(db, crm_service.SCOPE_CLUB, club.id, deal_id)
    await _update_deal_or_422(db, deal, **body.model_dump(exclude_unset=True))
    await db.commit()
    return await _serialize_deal(db, deal)


@router.post("/deals/{deal_id}/stage", dependencies=[_require])
async def club_move_stage(deal_id: str, body: StageMoveBody, club: Organisation = Depends(get_current_club),
                          db: AsyncSession = Depends(get_db)):
    deal = await _deal_or_404(db, crm_service.SCOPE_CLUB, club.id, deal_id)
    _, stage = await _deal_stage_or_404(db, deal, body.stage_id)
    await crm_service.move_stage(db, deal, stage, probability=body.probability)
    await db.commit()
    return await _serialize_deal(db, deal)


@router.post("/deals/{deal_id}/close", dependencies=[_require])
async def club_close_deal(deal_id: str, body: CloseBody, club: Organisation = Depends(get_current_club),
                          db: AsyncSession = Depends(get_db)):
    if body.status not in ("won", "lost"):
        raise HTTPException(status_code=422, detail="status must be 'won' or 'lost'")
    deal = await _deal_or_404(db, crm_service.SCOPE_CLUB, club.id, deal_id)
    pipeline = await crm_service.get_deal_pipeline(db, deal)
    await crm_service.close_deal(db, deal, pipeline, status=body.status, lost_reason=body.lost_reason)
    await db.commit()
    return await _serialize_deal(db, deal)


@router.delete("/deals/{deal_id}", dependencies=[_require])
async def club_archive_deal(deal_id: str, club: Organisation = Depends(get_current_club),
                            db: AsyncSession = Depends(get_db)):
    deal = await _deal_or_404(db, crm_service.SCOPE_CLUB, club.id, deal_id)
    await crm_service.archive_deal(db, deal)
    await db.commit()
    return {"archived": True}


@router.delete("/deals/{deal_id}/permanent", dependencies=[_require])
async def club_delete_deal_permanent(deal_id: str, club: Organisation = Depends(get_current_club),
                                     db: AsyncSession = Depends(get_db)):
    deal = await _deal_or_404(db, crm_service.SCOPE_CLUB, club.id, deal_id)
    await crm_service.delete_deal(db, deal)
    await db.commit()
    return {"deleted": True}


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
    await db.refresh(person, attribute_names=["roles"])
    return crm_service._person_dict(person)


@router.delete("/deals/{deal_id}/contacts/{person_id}", dependencies=[_require])
async def club_unlink_contact(deal_id: str, person_id: str, club: Organisation = Depends(get_current_club),
                              db: AsyncSession = Depends(get_db)):
    deal = await _deal_or_404(db, crm_service.SCOPE_CLUB, club.id, deal_id)
    ok = await crm_service.unlink_deal_contact(db, deal.id, _uuid_or_404(person_id))
    await db.commit()
    return {"unlinked": ok}


@router.post("/deals/{deal_id}/point-of-contact", dependencies=[_require])
async def club_set_point_of_contact(deal_id: str, body: DealContactBody, club: Organisation = Depends(get_current_club),
                                    db: AsyncSession = Depends(get_db)):
    deal = await _deal_or_404(db, crm_service.SCOPE_CLUB, club.id, deal_id)
    person = await _resolve_contact_person(db, body, organisation_id=club.id)
    await crm_service.set_point_of_contact(db, deal.id, person.id)
    await db.commit()
    return {"contacts": await crm_service.list_deal_contacts(db, deal.id)}


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
    await db.refresh(person, attribute_names=["roles"])
    return crm_service._person_dict(person)


@router.patch("/people/{person_id}", dependencies=[_require])
async def club_update_person(person_id: str, body: PersonUpdate, club: Organisation = Depends(get_current_club),
                             db: AsyncSession = Depends(get_db)):
    person = await crm_service.get_person(db, _uuid_or_404(person_id))
    if person is None or str(person.organisation_id) != str(club.id):
        raise HTTPException(status_code=404, detail="Person not found")
    for field in ("full_name", "email", "phone", "notes"):
        val = getattr(body, field)
        if val is not None:
            setattr(person, field, val)
    await db.commit()
    await db.refresh(person, attribute_names=["roles"])
    return crm_service._person_dict(person)


@router.post("/people/{person_id}/roles", dependencies=[_require])
async def club_add_person_role(person_id: str, body: RoleCreate, club: Organisation = Depends(get_current_club),
                               db: AsyncSession = Depends(get_db)):
    person = await crm_service.get_person(db, _uuid_or_404(person_id))
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
    pipeline = await crm_service.ensure_platform_pipeline(db)
    deals = await crm_service.list_deals(db, pipeline.id)
    club_by_id = await crm_service.clubs_by_ids(db, (d.marketing_club_id for d in deals))
    return crm_service.pipeline_board(pipeline, deals, club_by_id)


@super_router.get("/stages", dependencies=[_super])
async def super_stages(db: AsyncSession = Depends(get_db)):
    pipeline = await crm_service.ensure_platform_pipeline(db)
    return {"stages": crm_service.stage_dicts(pipeline)}


@super_router.post("/stages", dependencies=[_super])
async def super_add_stage(body: StageCreate, db: AsyncSession = Depends(get_db)):
    pipeline = await crm_service.ensure_platform_pipeline(db)
    await crm_service.add_stage(db, pipeline, name=body.name, default_probability=body.default_probability,
                                is_won=body.is_won, is_lost=body.is_lost, hidden_from_board=body.hidden_from_board)
    await db.commit()
    pipeline = await crm_service.ensure_platform_pipeline(db)
    return {"stages": crm_service.stage_dicts(pipeline)}


@super_router.patch("/stages/{stage_id}", dependencies=[_super])
async def super_update_stage(stage_id: str, body: StageUpdate, db: AsyncSession = Depends(get_db)):
    stage = await _platform_stage_or_404(db, stage_id)
    await crm_service.update_stage(db, stage, **body.model_dump(exclude_unset=True))
    await db.commit()
    return {"id": str(stage.id), "key": stage.key, "name": stage.name, "position": stage.position,
            "default_probability": stage.default_probability, "is_won": stage.is_won, "is_lost": stage.is_lost,
            "hidden_from_board": stage.hidden_from_board}


@super_router.delete("/stages/{stage_id}", dependencies=[_super])
async def super_delete_stage(stage_id: str, db: AsyncSession = Depends(get_db)):
    stage = await _platform_stage_or_404(db, stage_id)
    try:
        await crm_service.delete_stage(db, stage)
        await db.commit()
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(e))
    except IntegrityError:
        # The empty-check and the actual DELETE aren't atomic — a deal can
        # land in this exact stage in between (e.g. a background CRM-sync
        # write from a live self-serve trial signup), which only shows up as
        # a DB-level FK violation at commit time, not the ValueError above.
        await db.rollback()
        raise HTTPException(status_code=409,
                           detail="A new record was just added to this stage — move or archive it, then try again")
    return {"deleted": True}


@super_router.get("/deals", dependencies=[_super])
async def super_list_deals(status: Optional[str] = None, include_archived: bool = False,
                           db: AsyncSession = Depends(get_db)):
    """Every field the CRM's search/filter bar needs, in one call — the
    filtering itself happens client-side (the platform pipeline is small
    enough that a per-keystroke round trip isn't worth the complexity a
    fully server-side filter would add). `point_of_contact_name`,
    `marketing_club_state`/`_association`, and `acquisition_channel` are
    batch-computed (no N+1) alongside the existing engagement fields."""
    pipeline = await crm_service.ensure_platform_pipeline(db)
    stage_by_id = {s.id: s for s in pipeline.stages}
    deals = await crm_service.list_deals(db, pipeline.id, status=status, include_archived=include_archived)
    club_by_id = await crm_service.clubs_by_ids(db, (d.marketing_club_id for d in deals))

    # Each enrichment pass is optional relative to the base deal list — one
    # failing (a large club_by_email IN-list, a since-deleted org, whatever)
    # must never 500 the whole board/list; it just degrades to a blank
    # column for that one field, same posture as iq_team._safe elsewhere in
    # this codebase.
    try:
        poc_by_deal = await crm_service.poc_names_by_deal(db, (d.id for d in deals))
    except Exception:  # noqa: BLE001
        logger.exception("super_list_deals: poc_names_by_deal failed")
        poc_by_deal = {}
    try:
        channel_by_club = await crm_service.acquisition_channels_by_club(db, club_by_id)
    except Exception:  # noqa: BLE001
        logger.exception("super_list_deals: acquisition_channels_by_club failed")
        channel_by_club = {}
    try:
        trial_days_by_club = await crm_service.trial_days_remaining_by_club(db, club_by_id)
    except Exception:  # noqa: BLE001
        logger.exception("super_list_deals: trial_days_remaining_by_club failed")
        trial_days_by_club = {}
    try:
        subscribed_by_club = await crm_service.subscribed_modules_by_club(db, club_by_id)
    except Exception:  # noqa: BLE001
        logger.exception("super_list_deals: subscribed_modules_by_club failed")
        subscribed_by_club = {}
    try:
        stats_by_club = await crm_service.club_stats_by_club(db, club_by_id)
    except Exception:  # noqa: BLE001
        logger.exception("super_list_deals: club_stats_by_club failed")
        stats_by_club = {}

    out = []
    for d in deals:
        club = club_by_id.get(d.marketing_club_id)
        row = crm_service._deal_dict(d, stage_by_id.get(d.stage_id), club)
        row["point_of_contact_name"] = poc_by_deal.get(d.id)
        row["marketing_club_state"] = club.state if club else None
        row["marketing_club_association"] = club.association_name if club else None
        row["acquisition_channel"] = (channel_by_club.get(d.marketing_club_id) if d.marketing_club_id else None) or d.source
        trial_days = trial_days_by_club.get(d.marketing_club_id) if d.marketing_club_id else None
        row["trial_days_remaining"] = trial_days
        row["min_trial_days_remaining"] = min(trial_days.values()) if trial_days else None
        row["subscribed_modules"] = (subscribed_by_club.get(d.marketing_club_id) if d.marketing_club_id else None) or []
        # Onboarded-club facts (seasons/grades/players/setup/active-since) for
        # the Kanban card's state line — only present for a linked, onboarded
        # club (a subscriber or trialing club); absent for a bare prospect.
        row["club_stats"] = stats_by_club.get(d.marketing_club_id) if d.marketing_club_id else None
        out.append(row)
    return {"deals": out}


@super_router.post("/deals", dependencies=[_super])
async def super_create_deal(body: DealCreate, db: AsyncSession = Depends(get_db)):
    pipeline = await crm_service.ensure_platform_pipeline(db)
    marketing_club_id = _uuid_or_404(body.marketing_club_id) if body.marketing_club_id else None
    return await _create_deal_in_pipeline(db, pipeline, crm_service.SCOPE_PLATFORM, None, marketing_club_id, body)


@super_router.get("/deals/{deal_id}", dependencies=[_super])
async def super_get_deal(deal_id: str, db: AsyncSession = Depends(get_db)):
    deal = await _deal_or_404(db, crm_service.SCOPE_PLATFORM, None, deal_id)
    return await _serialize_deal(db, deal)


@super_router.post("/deals/{deal_id}/recalc-product-interest", dependencies=[_super])
async def super_recalc_product_interest(deal_id: str, db: AsyncSession = Depends(get_db)):
    """Re-derive this deal's Product Interest from the linked club's tracked
    website visits, overwriting any manual override — the counterpart to the
    Product Interest chips' manual toggle."""
    deal = await _deal_or_404(db, crm_service.SCOPE_PLATFORM, None, deal_id)
    club = await db.get(MarketingClub, deal.marketing_club_id) if deal.marketing_club_id else None
    had_data = await crm_service.recalc_product_interest(db, deal, club)
    await db.commit()
    result = await _serialize_deal(db, deal)
    # Not a stored deal field — just tells the UI whether this recalc found
    # real tracked visits (vs "no analytics yet, defaulted to Stats"), which
    # otherwise look identical if the deal was already just ['core'].
    result["recalc_had_data"] = had_data
    return result


@super_router.patch("/deals/{deal_id}", dependencies=[_super])
async def super_update_deal(deal_id: str, body: DealUpdate, db: AsyncSession = Depends(get_db)):
    deal = await _deal_or_404(db, crm_service.SCOPE_PLATFORM, None, deal_id)
    await _update_deal_or_422(db, deal, **body.model_dump(exclude_unset=True))
    await db.commit()
    return await _serialize_deal(db, deal)


@super_router.post("/deals/{deal_id}/stage", dependencies=[_super])
async def super_move_stage(deal_id: str, body: StageMoveBody, db: AsyncSession = Depends(get_db)):
    deal = await _deal_or_404(db, crm_service.SCOPE_PLATFORM, None, deal_id)
    _, stage = await _deal_stage_or_404(db, deal, body.stage_id)
    await crm_service.move_stage(db, deal, stage, probability=body.probability)
    # A super admin deliberately choosing a stage here — as opposed to the
    # automatic engine's Contact-Us-count/engagement-score promotions — locks
    # the deal out of further auto-promotion (see
    # crm_service.sync_platform_deal_for_club/maybe_promote_by_engagement_score).
    deal.stage_auto_locked = True
    await db.commit()
    return await _serialize_deal(db, deal)


@super_router.post("/deals/{deal_id}/close", dependencies=[_super])
async def super_close_deal(deal_id: str, body: CloseBody, db: AsyncSession = Depends(get_db)):
    if body.status not in ("won", "lost"):
        raise HTTPException(status_code=422, detail="status must be 'won' or 'lost'")
    deal = await _deal_or_404(db, crm_service.SCOPE_PLATFORM, None, deal_id)
    pipeline = await crm_service.get_deal_pipeline(db, deal)
    await crm_service.close_deal(db, deal, pipeline, status=body.status, lost_reason=body.lost_reason)
    await db.commit()
    return await _serialize_deal(db, deal)


@super_router.delete("/deals/{deal_id}", dependencies=[_super])
async def super_archive_deal(deal_id: str, db: AsyncSession = Depends(get_db)):
    deal = await _deal_or_404(db, crm_service.SCOPE_PLATFORM, None, deal_id)
    await crm_service.archive_deal(db, deal)
    await db.commit()
    return {"archived": True}


@super_router.delete("/deals/{deal_id}/permanent", dependencies=[_super])
async def super_delete_deal_permanent(deal_id: str, reset_club: bool = False,
                                      db: AsyncSession = Depends(get_db)):
    """Permanently removes a platform deal. Two modes:

    - `reset_club=false` (default): just deletes the deal — for tidying a real
      Lead/Opportunity out of the pipeline without touching the club. (Archive
      is the reversible option; this is the permanent one.)
    - `reset_club=true` (the "this was test activity" checkbox): a FULL test-data
      PURGE. It deletes the deal AND, when the deal is linked to a registered
      club, HARD-DELETES that club from All Clubs (its seasons/games/players/
      stats/memberships/module subscriptions), deletes the club's own admin user
      login(s) (only those whose sole membership was this club — never a super
      admin, never a user who also belongs to another club), and deletes the
      club's Stripe customer (which cancels any subscription). The club's Club
      Directory (marketing_clubs) row is KEPT — its engagement/trial/demo state
      is reset so a genuine future enquiry starts fresh, but the directory entry
      itself is NEVER removed. The All-Clubs Archive flow is untouched by this.
    """
    deal = await _deal_or_404(db, crm_service.SCOPE_PLATFORM, None, deal_id)
    club = await db.get(MarketingClub, deal.marketing_club_id) if deal.marketing_club_id else None
    org_id = deal.organisation_id or (club.existing_org_id if club is not None else None)

    if reset_club and club is not None:
        await crm_service.reset_marketing_club_engagement(db, club)

    # Delete the deal explicitly and flush it, so the club hard-delete below
    # (which cascade-deletes deals via crm_deals.organisation_id ON DELETE
    # CASCADE) can't race its own cascade against this row.
    await crm_service.delete_deal(db, deal)
    await db.flush()

    purged_org = False
    if reset_club and org_id is not None:
        org = await db.get(Organisation, org_id)
        # Stripe is external — do it first (while we still hold the id) and never
        # let it block the DB purge; a missing/already-deleted customer is fine.
        if org is not None and org.stripe_customer_id:
            try:
                await stripe_client.delete_customer(org.stripe_customer_id)
            except Exception:  # noqa: BLE001
                logger.exception("crm purge: could not delete Stripe customer for org %s", org_id)
        await crm_service.hard_delete_registered_club(db, org_id)
        purged_org = True

    await db.commit()
    return {"deleted": True, "club_reset": bool(reset_club and club is not None),
            "club_purged": purged_org}


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
    await db.refresh(person, attribute_names=["roles"])
    return crm_service._person_dict(person)


@super_router.delete("/deals/{deal_id}/contacts/{person_id}", dependencies=[_super])
async def super_unlink_contact(deal_id: str, person_id: str, db: AsyncSession = Depends(get_db)):
    deal = await _deal_or_404(db, crm_service.SCOPE_PLATFORM, None, deal_id)
    ok = await crm_service.unlink_deal_contact(db, deal.id, _uuid_or_404(person_id))
    await db.commit()
    return {"unlinked": ok}


@super_router.post("/deals/{deal_id}/point-of-contact", dependencies=[_super])
async def super_set_point_of_contact(deal_id: str, body: DealContactBody, db: AsyncSession = Depends(get_db)):
    deal = await _deal_or_404(db, crm_service.SCOPE_PLATFORM, None, deal_id)
    person = await _resolve_contact_person(db, body, marketing_club_id=deal.marketing_club_id)
    await crm_service.set_point_of_contact(db, deal.id, person.id)
    await db.commit()
    return {"contacts": await crm_service.list_deal_contacts(db, deal.id)}


@super_router.get("/owners", dependencies=[_super])
async def super_list_owners(db: AsyncSession = Depends(get_db)):
    return {"owners": await crm_service.list_platform_owners(db)}


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
    await db.refresh(person, attribute_names=["roles"])
    return crm_service._person_dict(person)


@super_router.patch("/people/{person_id}", dependencies=[_super])
async def super_update_person(person_id: str, body: PersonUpdate, db: AsyncSession = Depends(get_db)):
    person = await crm_service.get_person(db, _uuid_or_404(person_id))
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    for field in ("full_name", "email", "phone", "notes"):
        val = getattr(body, field)
        if val is not None:
            setattr(person, field, val)
    await db.commit()
    await db.refresh(person, attribute_names=["roles"])
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
    return await _serialize_deal(db, deal)


# ─── Sales targets (Dashboard + dedicated Targets page) ──────────────────────

@super_router.get("/targets", dependencies=[_super])
async def super_list_targets(period_type: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    rows = await crm_targets.list_targets(db, period_type=period_type)
    return {"targets": [crm_targets.target_dict(t) for t in rows]}


@super_router.post("/targets", dependencies=[_super])
async def super_upsert_target(body: TargetUpsert, current_user=Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    try:
        target = await crm_targets.upsert_target(
            db, period_type=body.period_type, period_key=body.period_key, created_by=current_user.id,
            target_clubs_won=body.target_clubs_won, target_arr_cents=body.target_arr_cents,
            target_revenue_cents=body.target_revenue_cents, target_trials=body.target_trials,
            target_conversion_rate=body.target_conversion_rate, notes=body.notes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return crm_targets.target_dict(target)


@super_router.delete("/targets/{target_id}", dependencies=[_super])
async def super_delete_target(target_id: str, db: AsyncSession = Depends(get_db)):
    ok = await crm_targets.delete_target(db, _uuid_or_404(target_id))
    await db.commit()
    return {"deleted": ok}


@super_router.get("/targets/actuals", dependencies=[_super])
async def super_target_actuals(period_type: str, period_key: str, db: AsyncSession = Depends(get_db)):
    """Computed actuals for ANY period (whether or not a target row exists
    for it yet) — see services/crm_targets.py's module docstring for which
    figures are exact vs best-effort proxies (no stage-history table)."""
    try:
        return await crm_targets.compute_actuals(db, period_type, period_key)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ─── Automation rules (services/crm_rules.py) ────────────────────────────────
# Configurable, persistent criteria for the platform pipeline's automatic
# deal creation/stage-promotion — managed at /admin/super/crm-automation.

class AutomationRuleCreate(BaseModel):
    trigger: str
    label: str
    target_stage_key: str
    params: dict = {}
    force: bool = False
    enabled: bool = True


class AutomationRuleUpdate(BaseModel):
    label: Optional[str] = None
    target_stage_key: Optional[str] = None
    params: Optional[dict] = None
    force: Optional[bool] = None
    enabled: Optional[bool] = None


@super_router.get("/automation", dependencies=[_super])
async def super_list_automation(db: AsyncSession = Depends(get_db)):
    """Every configured rule, plus the trigger catalogue (crm_rules.TRIGGERS)
    and the platform pipeline's current stages — everything the Super Admin
    automation-rules page needs in one call."""
    rules = await crm_rules.list_rules(db)
    pipeline = await crm_service.ensure_platform_pipeline(db)
    return {
        "rules": [crm_rules.rule_dict(r) for r in rules],
        "triggers": [
            {"key": key, **spec} for key, spec in crm_rules.TRIGGERS.items()
        ],
        "stages": crm_service.stage_dicts(pipeline),
    }


@super_router.post("/automation", dependencies=[_super])
async def super_create_automation(body: AutomationRuleCreate, db: AsyncSession = Depends(get_db)):
    try:
        rule = await crm_rules.create_rule(
            db, trigger=body.trigger, label=body.label, target_stage_key=body.target_stage_key,
            params=body.params, force=body.force, enabled=body.enabled)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    await db.refresh(rule)
    return crm_rules.rule_dict(rule)


@super_router.patch("/automation/{rule_id}", dependencies=[_super])
async def super_update_automation(rule_id: str, body: AutomationRuleUpdate, db: AsyncSession = Depends(get_db)):
    rule = await crm_rules.get_rule(db, _uuid_or_404(rule_id))
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    try:
        await crm_rules.update_rule(db, rule, **body.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    await db.refresh(rule)
    return crm_rules.rule_dict(rule)


@super_router.delete("/automation/{rule_id}", dependencies=[_super])
async def super_delete_automation(rule_id: str, db: AsyncSession = Depends(get_db)):
    rule = await crm_rules.get_rule(db, _uuid_or_404(rule_id))
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    await crm_rules.delete_rule(db, rule)
    await db.commit()
    return {"deleted": True}
