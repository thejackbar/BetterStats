"""BetterClubManager Roster API — the weekly volunteer roster (core capability,
not a paid module). Operational areas + shift patterns are the config; a roster
week materialises shifts from the patterns, and assignments run through the
rules engine in services/roster.py. Gated on MANAGE_VOLUNTEERS.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import User, Organisation, get_db
from app.routers.auth import get_current_club
from app.auth.capabilities import require_cap, MANAGE_VOLUNTEERS
from app.services import roster as svc

router = APIRouter(prefix="/club-admin/roster", tags=["club-admin-roster"])
_cap = Depends(require_cap(MANAGE_VOLUNTEERS))


def _cand_api(c: dict) -> dict:
    return {**c, "role_ids": sorted(c["role_ids"]), "qual_type_ids": sorted(c["qual_type_ids"])}


class AreaUpsert(BaseModel):
    name: str
    department: Optional[str] = None
    color: Optional[str] = None
    required_role_id: Optional[str] = None
    required_qualification_type_id: Optional[str] = None
    sort_order: Optional[int] = None


class PatternCreate(BaseModel):
    day_of_week: int
    start_time: float
    end_time: float
    headcount: int = 1


class AssignBody(BaseModel):
    shift_id: str
    member_id: Optional[str] = None


class SettingsBody(BaseModel):
    enforce_qualifications: Optional[bool] = None
    weekly_shift_cap: Optional[int] = None


# ── areas + patterns ────────────────────────────────────────────────────────
@router.get("/areas")
async def get_areas(_: User = _cap, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    return {"areas": await svc.list_areas(db, club.id)}


@router.post("/areas")
async def create_area(data: AreaUpsert, _: User = _cap, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    aid = await svc.create_area(db, club.id, name=data.name, department=data.department, color=data.color,
                                required_role_id=data.required_role_id, required_qualification_type_id=data.required_qualification_type_id)
    await db.commit()
    return {"id": aid}


@router.patch("/areas/{area_id}")
async def update_area(area_id: str, data: AreaUpsert, _: User = _cap, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    await svc.update_area(db, club.id, area_id, **data.model_dump(exclude_unset=True))
    await db.commit()
    return {"ok": True}


@router.delete("/areas/{area_id}")
async def delete_area(area_id: str, _: User = _cap, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    await svc.delete_area(db, club.id, area_id)
    await db.commit()
    return {"ok": True}


class ReorderBody(BaseModel):
    area_ids: list[str]


@router.post("/areas/reorder")
async def reorder_areas(data: ReorderBody, _: User = _cap, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    await svc.reorder_areas(db, club.id, data.area_ids)
    await db.commit()
    return {"ok": True}


@router.post("/areas/seed-starter")
async def seed_starter(_: User = _cap, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    seeded = await svc.seed_starter_areas(db, club.id)
    await db.commit()
    return {"seeded": seeded}


# ── departments (managed catalogue feeding the area form's dropdown) ─────────
class DepartmentUpsert(BaseModel):
    name: Optional[str] = None
    sort_order: Optional[int] = None


class DeptReorderBody(BaseModel):
    department_ids: list[str]


@router.get("/departments")
async def get_departments(_: User = _cap, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    return {"departments": await svc.list_departments(db, club.id)}


@router.post("/departments")
async def create_department(data: DepartmentUpsert, _: User = _cap, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    try:
        did = await svc.create_department(db, club.id, name=data.name)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": did}


@router.patch("/departments/{dept_id}")
async def update_department(dept_id: str, data: DepartmentUpsert, _: User = _cap, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    await svc.update_department(db, club.id, dept_id, **data.model_dump(exclude_unset=True))
    await db.commit()
    return {"ok": True}


@router.delete("/departments/{dept_id}")
async def delete_department(dept_id: str, _: User = _cap, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    await svc.delete_department(db, club.id, dept_id)
    await db.commit()
    return {"ok": True}


@router.post("/departments/reorder")
async def reorder_departments(data: DeptReorderBody, _: User = _cap, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    await svc.reorder_departments(db, club.id, data.department_ids)
    await db.commit()
    return {"ok": True}


@router.post("/departments/seed-starter")
async def seed_departments(_: User = _cap, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    seeded = await svc.seed_starter_departments(db, club.id)
    await db.commit()
    return {"seeded": seeded}


@router.post("/areas/{area_id}/patterns")
async def add_pattern(area_id: str, data: PatternCreate, _: User = _cap, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    pid = await svc.add_pattern(db, club.id, area_id, day_of_week=data.day_of_week, start_time=data.start_time, end_time=data.end_time, headcount=data.headcount)
    await db.commit()
    return {"id": pid}


@router.delete("/patterns/{pattern_id}")
async def delete_pattern(pattern_id: str, _: User = _cap, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    await svc.delete_pattern(db, club.id, pattern_id)
    await db.commit()
    return {"ok": True}


# ── settings ────────────────────────────────────────────────────────────────
@router.get("/settings")
async def get_settings(_: User = _cap, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    return await svc.get_settings(db, club.id)


@router.patch("/settings")
async def patch_settings(data: SettingsBody, _: User = _cap, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    out = await svc.set_settings(db, club.id, enforce_qualifications=data.enforce_qualifications, weekly_shift_cap=data.weekly_shift_cap)
    await db.commit()
    return out


# ── the week ────────────────────────────────────────────────────────────────
@router.get("/week")
async def get_week(week_start: Optional[str] = Query(None), _: User = _cap, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    try:
        ws = date.fromisoformat(week_start) if week_start else date.today()
    except ValueError:
        raise HTTPException(status_code=422, detail="week_start must be YYYY-MM-DD")
    week = await svc.get_or_create_week(db, club.id, ws)
    await db.commit()  # persists a freshly-created week + its generated shifts
    return {
        "week": week,
        "areas": await svc.list_areas(db, club.id),
        "candidates": [_cand_api(c) for c in await svc.candidates(db, club.id)],
        "settings": await svc.get_settings(db, club.id),
    }


@router.get("/contacts")
async def rostered_contacts(
    scope: str = Query("week", pattern="^(day|week|month)$"),
    on: Optional[str] = Query(None, description="Any date inside the period; defaults to today"),
    _: User = _cap, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db),
):
    """Everyone rostered on for a day, week or month — the set behind
    "email everyone rostered this week"."""
    try:
        anchor_day = date.fromisoformat(on) if on else date.today()
    except ValueError:
        raise HTTPException(status_code=422, detail="`on` must be YYYY-MM-DD")
    if scope == "day":
        start = end = anchor_day
    elif scope == "month":
        start = anchor_day.replace(day=1)
        end = (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    else:
        start = anchor_day - timedelta(days=anchor_day.weekday())
        end = start + timedelta(days=6)
    return {"scope": scope, **await svc.rostered_contacts(db, club.id, start, end)}


@router.post("/week/{week_id}/assign")
async def assign(week_id: str, data: AssignBody, _: User = _cap, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    res = await svc.assign(db, club.id, week_id, data.shift_id, data.member_id)
    if res.get("ok"):
        await db.commit()
    return res


@router.post("/week/{week_id}/autofill")
async def autofill(week_id: str, _: User = _cap, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    res = await svc.autofill(db, club.id, week_id)
    await db.commit()
    res["shifts"] = await svc._shift_rows(db, week_id)
    return res


@router.post("/week/{week_id}/publish")
async def publish(week_id: str, _: User = _cap, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    res = await svc.publish(db, club.id, week_id)
    await db.commit()
    return res


@router.post("/week/{week_id}/reset")
async def reset(week_id: str, _: User = _cap, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    await svc.reset_week(db, club.id, week_id)
    await db.commit()
    return {"shifts": await svc._shift_rows(db, week_id)}


@router.post("/clear-config")
async def clear_config(_: User = _cap, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    """Testing reset — wipe this club's roster areas/patterns/weeks."""
    await svc.clear_config(db, club.id)
    await db.commit()
    return {"ok": True}
