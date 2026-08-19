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

import asyncio
import logging
import uuid
from datetime import date, datetime, timezone
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
    product_interest_source: Optional[str] = None
    expected_close_date: Optional[date] = None
    owner_user_id: Optional[str] = None
    onboarding_method: Optional[str] = None
    lead_source: Optional[str] = None
    discount_amount_cents: Optional[int] = None
    discount_percent: Optional[int] = None
    discount_reason: Optional[str] = None
    # Answered the "this club has been attributed to X" prompt — see the
    # commission note in services/sales_workspace.py. Only read when this
    # PATCH changes owner_user_id on an attributed deal.
    confirm_reassign: bool = False


class StageMoveBody(BaseModel):
    stage_id: str
    probability: Optional[int] = None


class CloseBody(BaseModel):
    status: str  # won | lost
    lost_reason: Optional[str] = None


class ActivityCreate(BaseModel):
    type: str = "note"
    body: Optional[str] = None


class EventCreate(BaseModel):
    event_type: str = "meeting"          # call | demo | meeting | review_deal | follow_up | other
    starts_at: datetime                  # future date & time (ISO)
    title: Optional[str] = None
    location: Optional[str] = None
    body: Optional[str] = None           # the free-text note
    owner_user_id: Optional[str] = None  # a super-admin User
    contact_person_id: Optional[str] = None
    marketing_club_id: Optional[str] = None  # standalone events only; deal events copy it from the deal
    first_alert: Optional[str] = None    # at_time | 5m | 10m | 15m | 30m | 1h | 2h | 1d | 2d | 1w
    second_alert: Optional[str] = None


class EventUpdate(BaseModel):
    event_type: Optional[str] = None
    starts_at: Optional[datetime] = None
    title: Optional[str] = None
    location: Optional[str] = None
    body: Optional[str] = None
    owner_user_id: Optional[str] = None
    contact_person_id: Optional[str] = None
    marketing_club_id: Optional[str] = None
    first_alert: Optional[str] = None
    second_alert: Optional[str] = None


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
    minimized: bool = False


class StageUpdate(BaseModel):
    name: Optional[str] = None
    default_probability: Optional[int] = None
    is_won: Optional[bool] = None
    is_lost: Optional[bool] = None
    position: Optional[int] = None
    hidden_from_board: Optional[bool] = None
    minimized: Optional[bool] = None


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
                                is_won=body.is_won, is_lost=body.is_lost, hidden_from_board=body.hidden_from_board,
                                minimized=body.minimized)
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
            "hidden_from_board": stage.hidden_from_board, "minimized": stage.minimized}


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
                                is_won=body.is_won, is_lost=body.is_lost, hidden_from_board=body.hidden_from_board,
                                minimized=body.minimized)
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
            "hidden_from_board": stage.hidden_from_board, "minimized": stage.minimized}


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
        poc_by_deal = await crm_service.poc_contacts_by_deal(db, (d.id for d in deals))
    except Exception:  # noqa: BLE001
        logger.exception("super_list_deals: poc_contacts_by_deal failed")
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
    try:
        activity_by_deal = await crm_service.last_activity_at_by_deal(db, deals, club_by_id)
    except Exception:  # noqa: BLE001
        logger.exception("super_list_deals: last_activity_at_by_deal failed")
        activity_by_deal = {}
    try:
        next_event_by_deal = await crm_service.next_events_by_deal(db, (d.id for d in deals))
    except Exception:  # noqa: BLE001
        logger.exception("super_list_deals: next_events_by_deal failed")
        next_event_by_deal = {}

    out = []
    for d in deals:
        club = club_by_id.get(d.marketing_club_id)
        row = crm_service._deal_dict(d, stage_by_id.get(d.stage_id), club)
        poc = poc_by_deal.get(d.id) or {}
        row["point_of_contact_name"] = poc.get("name")
        row["point_of_contact_email"] = poc.get("email")
        # marketing_club_state / _suburb / _association / _associations are
        # now set by _deal_dict itself (club is already passed in above).
        row["acquisition_channel"] = (channel_by_club.get(d.marketing_club_id) if d.marketing_club_id else None) or d.source
        trial_days = trial_days_by_club.get(d.marketing_club_id) if d.marketing_club_id else None
        row["trial_days_remaining"] = trial_days
        row["min_trial_days_remaining"] = min(trial_days.values()) if trial_days else None
        row["subscribed_modules"] = (subscribed_by_club.get(d.marketing_club_id) if d.marketing_club_id else None) or []
        # A super-admin-registered trial set in the Club Directory sales-state
        # (marketing_clubs.trial_modules / demo_status='in_trial') — no
        # automated source, so it's always staff-set. Unlike an onboarded
        # module trial it has no OrgModuleSubscription countdown, so
        # min_trial_days_remaining is null and it would otherwise show no trial
        # badge at all. Surfaced so the card can still flag it as on-trial.
        row["prospect_trial"] = bool(
            club and ((club.trial_modules or []) or club.demo_status == "in_trial"))
        # Onboarded-club facts (seasons/grades/players/setup/active-since) for
        # the Kanban card's state line — only present for a linked, onboarded
        # club (a subscriber or trialing club); absent for a bare prospect.
        row["club_stats"] = stats_by_club.get(d.marketing_club_id) if d.marketing_club_id else None
        # Latest activity of any tracked kind (deal edit, subscription change,
        # onboarding step, page view) — powers the "New Deal Activity" filter.
        act = activity_by_deal.get(d.id)
        row["last_activity_at"] = act.isoformat() if act else None
        # Soonest upcoming (else most recent) scheduled event — the calendar
        # summary line at the bottom of the Kanban card.
        row["next_event"] = next_event_by_deal.get(d.id)
        out.append(row)
    return {"deals": out}


# ─── Create a BetterComms List from the current deal result set ────────────────
# The board/list "Create List" button turns the visible (filtered) deals into an
# auto-generated BetterComms List in the marketing-outreach org, one contact per
# deal. Two steps: /list-export/prepare resolves + matches each deal's contact
# and returns anything the operator must resolve by hand; /list-export/commit
# creates the list and populates it. See services/crm_list_export.py.
class ListExportPrepareBody(BaseModel):
    deal_ids: List[str] = []


class ListExportResolution(BaseModel):
    club_id: Optional[str] = None
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    name: Optional[str] = None


class ListExportCommitBody(BaseModel):
    name: str
    matched_contact_ids: List[str] = []
    resolutions: List[ListExportResolution] = []


@super_router.post("/list-export/prepare", dependencies=[_super])
async def super_list_export_prepare(body: ListExportPrepareBody,
                                    db: AsyncSession = Depends(get_db)):
    from app.services import crm_list_export
    result = await crm_list_export.prepare_list_from_deals(db, body.deal_ids)
    if result.get("error"):
        raise HTTPException(status_code=409, detail=result.get("detail") or result["error"])
    return result


@super_router.post("/list-export/commit", dependencies=[_super])
async def super_list_export_commit(body: ListExportCommitBody,
                                   db: AsyncSession = Depends(get_db)):
    from app.services import crm_list_export
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="A list name is required")
    result = await crm_list_export.commit_list_from_deals(
        db, name=name,
        matched_contact_ids=body.matched_contact_ids,
        resolutions=[r.model_dump() for r in body.resolutions],
    )
    if result.get("error"):
        raise HTTPException(status_code=409, detail=result.get("detail") or result["error"])
    return result


# ─── Clubs searched or selected in the registration wizard ────────────────────
# The Meta Ads page reports these as two separate read-only tables; this is the
# outreach surface over both of them merged — match each club to the Club
# Directory, turn a filtered set into an auto-generated BetterComms list of that
# club's contacts, and report which clubs have since been emailed through one of
# those lists. See services/wizard_club_lists.py.
WIZARD_DAYS_DEFAULT = 365
WIZARD_DAYS_MAX = 730


class WizardListCreateBody(BaseModel):
    name: str
    club_keys: List[str] = []


@super_router.get("/wizard-clubs", dependencies=[_super])
async def super_wizard_clubs(
    days: int = WIZARD_DAYS_DEFAULT,
    db: AsyncSession = Depends(get_db),
):
    from app.services import wizard_club_lists
    days = max(1, min(int(days or WIZARD_DAYS_DEFAULT), WIZARD_DAYS_MAX))
    return await wizard_club_lists.list_wizard_clubs(db, days)


@super_router.post("/wizard-clubs/create-list", dependencies=[_super])
async def super_wizard_clubs_create_list(
    body: WizardListCreateBody,
    days: int = WIZARD_DAYS_DEFAULT,
    db: AsyncSession = Depends(get_db),
    user: "object" = Depends(get_current_user),
):
    from app.services import wizard_club_lists
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="A list name is required")
    days = max(1, min(int(days or WIZARD_DAYS_DEFAULT), WIZARD_DAYS_MAX))
    result = await wizard_club_lists.create_list_from_clubs(
        db, name=name, days=days, club_keys=body.club_keys,
        created_by=getattr(user, "id", None))
    if result.get("error"):
        raise HTTPException(status_code=409, detail=result.get("detail") or result["error"])
    return result


# ─── Manual full engagement recompute (the "Recalculate" board button) ────────
# Runs the SAME logic as `python -m app.scripts.recalc_engagement`: recompute and
# re-cache every club's engagement score (twenty_sync._engagement, a local
# read/compute — no Twenty calls) and re-run the score-based CRM auto-promotion,
# so the board reflects the current scoring rules immediately instead of waiting
# on the nightly (Twenty-gated) refresh or lazy per-event recomputes. A full
# sweep takes minutes, well past nginx's 60s proxy timeout, so it runs as a
# detached background task with a status the button polls — same pattern as the
# marketing page's "Refresh Twenty" buttons.
_engagement_recalc: dict = {
    "running": False, "started_at": None, "finished_at": None, "result": None, "error": None,
}
_recalc_tasks: set = set()


async def _run_engagement_recalc() -> None:
    from app.scripts.recalc_engagement import recalc
    try:
        _engagement_recalc["result"] = await recalc()
        _engagement_recalc["error"] = None
    except Exception as e:  # noqa: BLE001 - background task; surface via status, never crash
        logger.exception("manual engagement recalc failed")
        _engagement_recalc["error"] = str(e) or "Recalculation failed"
    finally:
        _engagement_recalc["running"] = False
        _engagement_recalc["finished_at"] = datetime.now(timezone.utc).isoformat()


@super_router.post("/recalc-engagement", dependencies=[_super])
async def super_recalc_engagement():
    """Kick off a full engagement recompute across every club in the background
    and return immediately. A no-op (returns the live state) if one is already
    running, so a double-click can't launch two concurrent sweeps."""
    if _engagement_recalc["running"]:
        return {"status": "already_running", **_engagement_recalc}
    _engagement_recalc.update(
        running=True, started_at=datetime.now(timezone.utc).isoformat(),
        finished_at=None, result=None, error=None)
    task = asyncio.create_task(_run_engagement_recalc())
    _recalc_tasks.add(task)
    task.add_done_callback(_recalc_tasks.discard)
    return {"status": "started"}


@super_router.get("/recalc-engagement/status", dependencies=[_super])
async def super_recalc_engagement_status():
    return {"status": "running" if _engagement_recalc["running"] else "idle", **_engagement_recalc}


# ─── CRM auto-recompute cadence settings (Tier 2 / Tier 3) ────────────────────

class CrmSweepSettings(BaseModel):
    incremental_sweep_seconds: Optional[int] = None
    global_sweep_minutes: Optional[int] = None
    event_stale_hours: Optional[int] = None
    show_past_events: Optional[bool] = None


@super_router.get("/settings", dependencies=[_super])
async def super_crm_settings(db: AsyncSession = Depends(get_db)):
    """The super-admin-tunable pipeline auto-recompute cadences, with their
    allowed bounds so the Settings UI can validate/label them."""
    from app.services import platform_settings as ps
    return {
        "incremental_sweep_seconds": await ps.get_crm_incremental_sweep_seconds(db),
        "global_sweep_minutes": await ps.get_crm_global_sweep_minutes(db),
        "event_stale_hours": await ps.get_crm_event_stale_hours(db),
        "show_past_events": await ps.get_crm_show_past_events(db),
        # When each sweep last actually ran and what it did — so "the cadence
        # says hourly" is something a super admin can verify rather than
        # trust, if a score still looks stale.
        "sweep_status": await ps.get_crm_sweep_status(db),
        "bounds": {
            "incremental_seconds": {"min": ps.CRM_INCREMENTAL_SWEEP_MIN_SECONDS,
                                    "max": ps.CRM_INCREMENTAL_SWEEP_MAX_SECONDS},
            "global_minutes": {"min": ps.CRM_GLOBAL_SWEEP_MIN_MINUTES,
                               "max": ps.CRM_GLOBAL_SWEEP_MAX_MINUTES},
            "event_stale_hours": {"min": ps.CRM_EVENT_STALE_MIN_HOURS,
                                  "max": ps.CRM_EVENT_STALE_MAX_HOURS},
        },
    }


@super_router.patch("/settings", dependencies=[_super])
async def super_update_crm_settings(body: CrmSweepSettings, db: AsyncSession = Depends(get_db)):
    """Save new Tier-2 / Tier-3 cadences and apply them to the running scheduler
    immediately (no restart). Each is range-checked before saving."""
    from app.services import platform_settings as ps
    patch: dict = {}
    if body.incremental_sweep_seconds is not None:
        v = body.incremental_sweep_seconds
        if not (ps.CRM_INCREMENTAL_SWEEP_MIN_SECONDS <= v <= ps.CRM_INCREMENTAL_SWEEP_MAX_SECONDS):
            raise HTTPException(status_code=422, detail=(
                f"incremental_sweep_seconds must be {ps.CRM_INCREMENTAL_SWEEP_MIN_SECONDS}"
                f"–{ps.CRM_INCREMENTAL_SWEEP_MAX_SECONDS}"))
        patch["crm_incremental_sweep_seconds"] = v
    if body.global_sweep_minutes is not None:
        v = body.global_sweep_minutes
        if not (ps.CRM_GLOBAL_SWEEP_MIN_MINUTES <= v <= ps.CRM_GLOBAL_SWEEP_MAX_MINUTES):
            raise HTTPException(status_code=422, detail=(
                f"global_sweep_minutes must be {ps.CRM_GLOBAL_SWEEP_MIN_MINUTES}"
                f"–{ps.CRM_GLOBAL_SWEEP_MAX_MINUTES}"))
        patch["crm_global_sweep_minutes"] = v
    if body.event_stale_hours is not None:
        v = body.event_stale_hours
        if not (ps.CRM_EVENT_STALE_MIN_HOURS <= v <= ps.CRM_EVENT_STALE_MAX_HOURS):
            raise HTTPException(status_code=422, detail=(
                f"event_stale_hours must be {ps.CRM_EVENT_STALE_MIN_HOURS}"
                f"–{ps.CRM_EVENT_STALE_MAX_HOURS}"))
        patch["crm_event_stale_hours"] = v
    if body.show_past_events is not None:
        patch["crm_show_past_events"] = body.show_past_events
    if patch:
        try:
            await ps.update_settings(db, patch)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
    inc = await ps.get_crm_incremental_sweep_seconds(db)
    glob = await ps.get_crm_global_sweep_minutes(db)
    try:
        from app.jobs.scheduler import reschedule_crm_sweeps
        reschedule_crm_sweeps(incremental_seconds=inc, global_minutes=glob)
    except Exception:  # noqa: BLE001
        logger.exception("could not reschedule CRM sweeps after settings update")
    return {"incremental_sweep_seconds": inc, "global_sweep_minutes": glob,
            "event_stale_hours": await ps.get_crm_event_stale_hours(db),
            "show_past_events": await ps.get_crm_show_past_events(db)}


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
    from app.services import sales_workspace as sw

    deal = await _deal_or_404(db, crm_service.SCOPE_PLATFORM, None, deal_id)
    fields = body.model_dump(exclude_unset=True)
    confirm = bool(fields.pop("confirm_reassign", False))
    # The Sales Pipeline's own Owner picker changes assignment too, so it
    # needs the same commission guard the Sales Workspace's assign endpoints
    # carry — otherwise the deal detail card is simply the way around it.
    if "owner_user_id" in fields and not confirm:
        new_owner = _uuid_or_404(fields["owner_user_id"]) if fields["owner_user_id"] else None
        if sw.commission_reassign_blocked(deal, new_owner):
            rep_name = (await sw.commission_rep_names(db, [deal])).get(deal.commission_rep_user_id)
            raise HTTPException(status_code=409, detail={
                "code": "commission_attributed",
                "message": sw.commission_confirm_message(rep_name),
                "commission_rep_user_id": str(deal.commission_rep_user_id),
                "commission_rep_name": rep_name,
            })
    await _update_deal_or_422(db, deal, **fields)
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


# ─── Calendar events ──────────────────────────────────────────────────────────

def _event_fields(body, *, is_update: bool) -> dict:
    """Shared field-mapping for create/update — resolves the string ids to
    UUIDs (a bad id is a 404, matching the rest of this router)."""
    out = {}
    src = body.model_dump(exclude_unset=True) if is_update else body.model_dump()
    for f in ("event_type", "title", "location", "body", "first_alert", "second_alert", "starts_at"):
        if f in src:
            out[f] = src[f]
    for f in ("owner_user_id", "contact_person_id", "marketing_club_id"):
        if f in src:
            out[f] = _uuid_or_404(src[f]) if src[f] else None
    return out


@super_router.get("/deals/{deal_id}/events", dependencies=[_super])
async def super_list_deal_events(deal_id: str, db: AsyncSession = Depends(get_db)):
    deal = await _deal_or_404(db, crm_service.SCOPE_PLATFORM, None, deal_id)
    return {"events": await crm_service.list_events(db, deal_id=deal.id)}


@super_router.post("/deals/{deal_id}/events", dependencies=[_super])
async def super_create_deal_event(deal_id: str, body: EventCreate, current_user=Depends(get_current_user),
                                  db: AsyncSession = Depends(get_db)):
    deal = await _deal_or_404(db, crm_service.SCOPE_PLATFORM, None, deal_id)
    fields = _event_fields(body, is_update=False)
    # A deal event is automatically linked to the deal's own club — the body's
    # marketing_club_id (only meaningful for a standalone event) is ignored.
    fields["marketing_club_id"] = deal.marketing_club_id
    event = await crm_service.create_event(
        db, deal_id=deal.id, created_by_user_id=current_user.id, **fields)
    await db.commit()
    return await _event_response(db, event)


@super_router.get("/events", dependencies=[_super])
async def super_list_events(q: Optional[str] = None, owner_user_id: Optional[str] = None,
                            created_by_user_id: Optional[str] = None, marketing_club_id: Optional[str] = None,
                            date_from: Optional[datetime] = None, date_to: Optional[datetime] = None,
                            db: AsyncSession = Depends(get_db)):
    events = await crm_service.list_events(
        db, q=q,
        owner_user_id=_uuid_or_404(owner_user_id) if owner_user_id else None,
        created_by_user_id=_uuid_or_404(created_by_user_id) if created_by_user_id else None,
        marketing_club_id=_uuid_or_404(marketing_club_id) if marketing_club_id else None,
        date_from=date_from, date_to=date_to)
    return {"events": events}


@super_router.post("/events", dependencies=[_super])
async def super_create_event(body: EventCreate, current_user=Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    event = await crm_service.create_event(
        db, created_by_user_id=current_user.id, **_event_fields(body, is_update=False))
    await db.commit()
    return await _event_response(db, event)


@super_router.patch("/events/{event_id}", dependencies=[_super])
async def super_update_event(event_id: str, body: EventUpdate, db: AsyncSession = Depends(get_db)):
    event = await crm_service.get_event(db, _uuid_or_404(event_id))
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    await crm_service.update_event(db, event, **_event_fields(body, is_update=True))
    await db.commit()
    return await _event_response(db, event)


@super_router.delete("/events/{event_id}", dependencies=[_super])
async def super_delete_event(event_id: str, db: AsyncSession = Depends(get_db)):
    event = await crm_service.get_event(db, _uuid_or_404(event_id))
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    await crm_service.delete_event(db, event)
    await db.commit()
    return {"deleted": True}


async def _event_response(db: AsyncSession, event) -> dict:
    await db.refresh(event)
    return await crm_service.serialize_event(db, event)


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
