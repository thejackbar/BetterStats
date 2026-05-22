"""StatLab routes — flexible query engine + saved reports."""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from pydantic import BaseModel, Field
from typing import Optional, Any
import json
import re
import uuid

from app.models.db import get_db, SavedReport, User, ClubMembership, Organisation
from app.routers.auth import get_current_user, get_current_club
from app.services import statlab as svc


router = APIRouter(prefix="/statlab", tags=["statlab"])


# ─── Schema ─────────────────────────────────────────────────────────────────────

@router.get("/schema")
async def get_schema():
    """Return the catalogue of query targets, metrics, context filters, operators
    and derived queries available to the StatLab UI."""
    return svc.schema()


# ─── Main query ────────────────────────────────────────────────────────────────

def _serialise(rows: list[dict]) -> list[dict]:
    def clean(v: Any):
        if v is None:
            return None
        t = type(v).__name__
        if t in ("Decimal", "UUID"):
            return str(v)
        if t == "date":
            return v.isoformat()
        return v
    return [{k: clean(v) for k, v in row.items()} for row in rows]


def _ctx_from_query(
    season_id: Optional[str],
    grade_id: Optional[str],
    grade_name: Optional[str],
    opposition: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
    min_year: Optional[int],
    max_year: Optional[int],
    finals_only: Optional[bool],
    captain_only: Optional[bool],
    keeper_only: Optional[bool],
    result: Optional[str],
    dismissal: Optional[str],
    position_min: Optional[int],
    position_max: Optional[int],
) -> dict:
    ctx = {}
    if season_id:    ctx["season_id"] = season_id
    if grade_id:     ctx["grade_id"] = grade_id
    if grade_name:   ctx["grade_name"] = grade_name
    if opposition:   ctx["opposition"] = opposition
    if date_from:    ctx["date_from"] = date_from
    if date_to:      ctx["date_to"] = date_to
    if min_year is not None: ctx["min_year"] = min_year
    if max_year is not None: ctx["max_year"] = max_year
    if finals_only:  ctx["finals_only"] = True
    if captain_only: ctx["captain_only"] = True
    if keeper_only:  ctx["keeper_only"] = True
    if result:       ctx["result"] = result
    if dismissal:    ctx["dismissal"] = dismissal
    if position_min is not None: ctx["position_min"] = position_min
    if position_max is not None: ctx["position_max"] = position_max
    return ctx


@router.get("/query")
async def statlab_query(
    org_id: str,
    target: str = Query("player_career"),
    sort_by: str = Query("runs"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(100, ge=1, le=500),
    filters: list[str] = Query(default=[]),
    filter_tree: Optional[str] = Query(None, description="URL-encoded JSON filter tree (overrides `filters` when present)"),
    # Context filters as flat query params (easier on the URL than nested JSON)
    season_id: Optional[str] = Query(None),
    grade_id: Optional[str] = Query(None),
    grade_name: Optional[str] = Query(None),
    opposition: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    min_year: Optional[int] = Query(None),
    max_year: Optional[int] = Query(None),
    finals_only: Optional[bool] = Query(None),
    captain_only: Optional[bool] = Query(None),
    keeper_only: Optional[bool] = Query(None),
    result: Optional[str] = Query(None),
    dismissal: Optional[str] = Query(None),
    position_min: Optional[int] = Query(None),
    position_max: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Run a StatLab query against one of the registered targets."""
    if target not in svc.TARGET_DISPATCH:
        raise HTTPException(status_code=400, detail=f"Unknown query target: {target}")
    parsed_tree = None
    if filter_tree:
        try:
            parsed_tree = json.loads(filter_tree)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="filter_tree must be valid JSON")
    ctx = _ctx_from_query(
        season_id, grade_id, grade_name, opposition, date_from, date_to,
        min_year, max_year, finals_only, captain_only, keeper_only, result,
        dismissal, position_min, position_max,
    )
    try:
        rows = await svc.run_query(
            db,
            org_id=org_id,
            target=target,
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=limit,
            metric_filters=filters,
            filter_tree=parsed_tree,
            context=ctx,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _serialise(rows)


@router.get("/derived/{name}")
async def statlab_derived(
    name: str,
    org_id: str,
    limit: int = Query(100, ge=1, le=200),
    season_id: Optional[str] = Query(None),
    grade_id: Optional[str] = Query(None),
    grade_name: Optional[str] = Query(None),
    opposition: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    min_year: Optional[int] = Query(None),
    max_year: Optional[int] = Query(None),
    finals_only: Optional[bool] = Query(None),
    captain_only: Optional[bool] = Query(None),
    keeper_only: Optional[bool] = Query(None),
    result: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    if name not in svc.DERIVED_QUERIES:
        raise HTTPException(status_code=400, detail=f"Unknown derived query: {name}")
    ctx = _ctx_from_query(
        season_id, grade_id, grade_name, opposition, date_from, date_to,
        min_year, max_year, finals_only, captain_only, keeper_only, result,
        None, None, None,
    )
    rows = await svc.run_derived(db, name=name, org_id=org_id, limit=limit, context=ctx)
    return _serialise(rows)


# ─── Saved Reports ─────────────────────────────────────────────────────────────

class SaveReportIn(BaseModel):
    title: str = Field(..., min_length=2, max_length=120)
    description: Optional[str] = Field(None, max_length=500)
    query_json: dict
    visibility: str = Field("club", pattern="^(club|private)$")
    slug: Optional[str] = Field(None, max_length=80)


class UpdateReportIn(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=120)
    description: Optional[str] = Field(None, max_length=500)
    query_json: Optional[dict] = None
    visibility: Optional[str] = Field(None, pattern="^(club|private)$")


def _slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:80] or "report"


async def _unique_slug(db: AsyncSession, org_id: uuid.UUID, base: str, existing_id: Optional[uuid.UUID] = None) -> str:
    candidate = base
    n = 2
    while True:
        q = select(SavedReport.id).where(SavedReport.org_id == org_id, SavedReport.slug == candidate)
        if existing_id is not None:
            q = q.where(SavedReport.id != existing_id)
        existing = (await db.execute(q)).scalar_one_or_none()
        if existing is None:
            return candidate
        candidate = f"{base}-{n}"
        n += 1


def _report_to_dict(r: SavedReport, owner_name: Optional[str] = None) -> dict:
    return {
        "id": str(r.id),
        "org_id": str(r.org_id),
        "owner_user_id": str(r.owner_user_id) if r.owner_user_id else None,
        "owner_name": owner_name,
        "slug": r.slug,
        "title": r.title,
        "description": r.description,
        "query_json": r.query_json,
        "visibility": r.visibility,
        "view_count": r.view_count,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


@router.get("/reports")
async def list_reports(
    org_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Public list of club-visible saved reports for an organisation."""
    rows = (await db.execute(
        select(SavedReport, User.display_name, User.username)
        .outerjoin(User, User.id == SavedReport.owner_user_id)
        .where(SavedReport.org_id == org_id, SavedReport.visibility == "club")
        .order_by(SavedReport.view_count.desc(), SavedReport.created_at.desc())
        .limit(200)
    )).all()
    return [
        _report_to_dict(r, owner_name=(dn or un))
        for r, dn, un in rows
    ]


@router.get("/reports/{slug}")
async def get_report(
    slug: str,
    org_id: str,
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(
        select(SavedReport, User.display_name, User.username)
        .outerjoin(User, User.id == SavedReport.owner_user_id)
        .where(SavedReport.org_id == org_id, SavedReport.slug == slug)
    )).first()
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")
    r, dn, un = row
    if r.visibility == "private":
        # Private reports require auth and ownership — defer to a separate route
        # path. Keeping it simple: 404 to avoid leaking existence.
        raise HTTPException(status_code=404, detail="Report not found")
    await db.execute(
        update(SavedReport).where(SavedReport.id == r.id).values(view_count=SavedReport.view_count + 1)
    )
    await db.commit()
    return _report_to_dict(r, owner_name=(dn or un))


@router.post("/reports")
async def create_report(
    payload: SaveReportIn,
    club: Organisation = Depends(get_current_club),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    base = _slugify(payload.slug or payload.title)
    slug = await _unique_slug(db, club.id, base)
    r = SavedReport(
        org_id=club.id,
        owner_user_id=current_user.id,
        slug=slug,
        title=payload.title.strip(),
        description=payload.description,
        query_json=payload.query_json,
        visibility=payload.visibility,
    )
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return _report_to_dict(r)


@router.patch("/reports/{report_id}")
async def patch_report(
    report_id: str,
    payload: UpdateReportIn,
    club: Organisation = Depends(get_current_club),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = await db.get(SavedReport, report_id)
    if not r or r.org_id != club.id:
        raise HTTPException(status_code=404, detail="Report not found")
    if payload.title is not None:
        r.title = payload.title.strip()
    if payload.description is not None:
        r.description = payload.description
    if payload.query_json is not None:
        r.query_json = payload.query_json
    if payload.visibility is not None:
        r.visibility = payload.visibility
    from sqlalchemy.sql import func as sql_func
    r.updated_at = sql_func.now()
    await db.commit()
    await db.refresh(r)
    return _report_to_dict(r)


@router.delete("/reports/{report_id}")
async def delete_report(
    report_id: str,
    club: Organisation = Depends(get_current_club),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = await db.get(SavedReport, report_id)
    if not r or r.org_id != club.id:
        raise HTTPException(status_code=404, detail="Report not found")
    await db.delete(r)
    await db.commit()
    return {"ok": True}


# ─── Back-compat ────────────────────────────────────────────────────────────────
# The original /statlab/fields endpoint is preserved so any old bookmarks /
# external pages continue to work; new UI should use /statlab/schema.

@router.get("/fields")
async def get_fields():
    return {
        "player": list(svc.PLAYER_AGG_METRICS.keys()),
        "grade": list(svc.PLAYER_AGG_METRICS.keys()),
        "team": list(svc.PLAYER_AGG_METRICS.keys()),
        "operators": list(svc.OPERATOR_MAP.keys()),
    }
