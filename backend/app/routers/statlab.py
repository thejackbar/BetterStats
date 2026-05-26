"""StatLab routes — flexible query engine + saved reports."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, text, func
from pydantic import BaseModel, Field
from typing import Optional, Any
import json
import re
import uuid

from app.auth.capabilities import (
    MANAGE_REPORTS, membership_has_capability, PRIVILEGED_ROLES,
)
from app.models.db import get_db, SavedReport, User, ClubMembership, Organisation
from app.routers.auth import get_current_user, get_current_club
from app.services import statlab as svc


async def _user_can_manage_reports(db: AsyncSession, user: User, club: Organisation) -> bool:
    """True when the user has the MANAGE_REPORTS capability on this club."""
    row = await db.execute(
        select(ClubMembership)
        .where(ClubMembership.user_id == user.id, ClubMembership.org_id == club.id)
    )
    m = row.scalar_one_or_none()
    if not m:
        return user.role in PRIVILEGED_ROLES
    return membership_has_capability(m.role, m.capabilities, MANAGE_REPORTS)


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


# Keys we extract from the query string into the StatLab context dict.
# Anything not in this list is silently ignored.
_CTX_KEYS_TEXT = {
    "season_id", "grade_id", "grade_name", "opposition", "date_from", "date_to",
    "result", "dismissal",
    "gender", "player_role",
    "award_category", "award_subcategory", "award_name", "office_bearer",
}
_CTX_KEYS_INT = {
    "min_year", "max_year", "position_min", "position_max",
    "first_n_matches", "milestone_runs",
}
_CTX_KEYS_BOOL = {
    "finals_only", "captain_only", "keeper_only", "on_this_day",
}


def _ctx_from_request(request: Request) -> dict:
    """Pull StatLab context filters from query-string params. Whitelist-based
    so unknown params (or stray API junk) don't leak into the SQL builder."""
    ctx: dict = {}
    qp = request.query_params
    for k in _CTX_KEYS_TEXT:
        v = qp.get(k)
        if v not in (None, ""):
            ctx[k] = v
    for k in _CTX_KEYS_INT:
        v = qp.get(k)
        if v not in (None, ""):
            try:
                ctx[k] = int(float(v))
            except (TypeError, ValueError):
                pass
    for k in _CTX_KEYS_BOOL:
        v = qp.get(k)
        if v not in (None, ""):
            ctx[k] = str(v).lower() in ("1", "true", "yes", "on")
    return ctx


@router.get("/query")
async def statlab_query(
    request: Request,
    org_id: str,
    target: str = Query("player_career"),
    sort_by: str = Query("runs"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(100, ge=1, le=500),
    page: int = Query(1, ge=1),
    filters: list[str] = Query(default=[]),
    filter_tree: Optional[str] = Query(None, description="URL-encoded JSON filter tree (overrides `filters` when present)"),
    db: AsyncSession = Depends(get_db),
):
    """Run a StatLab query against one of the registered targets.
    Context filters are read directly from the URL — see _CTX_KEYS_* whitelists."""
    if target not in svc.TARGET_DISPATCH:
        raise HTTPException(status_code=400, detail=f"Unknown query target: {target}")
    parsed_tree = None
    if filter_tree:
        try:
            parsed_tree = json.loads(filter_tree)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="filter_tree must be valid JSON")
    ctx = _ctx_from_request(request)
    try:
        result = await svc.run_query(
            db,
            org_id=org_id,
            target=target,
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=limit,
            page=page,
            metric_filters=filters,
            filter_tree=parsed_tree,
            context=ctx,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"rows": _serialise(result["rows"]), "has_more": result["has_more"], "page": result["page"]}


@router.get("/derived/{name}")
async def statlab_derived(
    name: str,
    request: Request,
    org_id: str,
    limit: int = Query(100, ge=1, le=500),
    page: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_db),
):
    if name not in svc.DERIVED_QUERIES:
        raise HTTPException(status_code=400, detail=f"Unknown derived query: {name}")
    ctx = _ctx_from_request(request)
    result = await svc.run_derived(db, name=name, org_id=org_id, limit=limit, page=page, context=ctx)
    return {"rows": _serialise(result["rows"]), "has_more": result["has_more"], "page": result["page"]}


@router.get("/picker-values")
async def picker_values(
    org_id: str,
    kind: str = Query(..., pattern="^(player_role|gender|award_category|award_subcategory|award_name|office_bearer)$"),
    search: str = Query("", max_length=80),
    db: AsyncSession = Depends(get_db),
):
    """Return distinct values for an attribute picker. Used by the StatLab
    Context panel for autocomplete dropdowns (gender, player role, awards,
    office bearers)."""
    q = (search or "").strip().lower()
    params = {"org_id": org_id, "q": f"%{q}%" if q else "%"}
    if kind == "player_role":
        sql = """
            SELECT DISTINCT player_role AS value
            FROM players
            WHERE organisation_id = CAST(:org_id AS UUID)
              AND COALESCE(player_role, '') <> ''
              AND LOWER(player_role) LIKE :q
            ORDER BY value
            LIMIT 50
        """
    elif kind == "gender":
        sql = """
            SELECT DISTINCT gender AS value
            FROM players
            WHERE organisation_id = CAST(:org_id AS UUID)
              AND COALESCE(gender, '') <> ''
              AND LOWER(gender) LIKE :q
            ORDER BY value
            LIMIT 50
        """
    elif kind == "award_category":
        sql = """
            SELECT DISTINCT category AS value
            FROM player_achievements
            WHERE org_id = CAST(:org_id AS UUID)
              AND COALESCE(category, '') <> ''
              AND LOWER(category) LIKE :q
            ORDER BY value
            LIMIT 50
        """
    elif kind == "award_subcategory":
        sql = """
            SELECT DISTINCT subcategory AS value
            FROM player_achievements
            WHERE org_id = CAST(:org_id AS UUID)
              AND COALESCE(subcategory, '') <> ''
              AND LOWER(subcategory) LIKE :q
            ORDER BY value
            LIMIT 50
        """
    elif kind == "award_name":
        sql = """
            SELECT DISTINCT achievement AS value
            FROM player_achievements
            WHERE org_id = CAST(:org_id AS UUID)
              AND COALESCE(achievement, '') <> ''
              AND LOWER(achievement) LIKE :q
            ORDER BY value
            LIMIT 50
        """
    elif kind == "office_bearer":
        sql = """
            SELECT DISTINCT achievement AS value
            FROM player_achievements
            WHERE org_id = CAST(:org_id AS UUID)
              AND LOWER(COALESCE(category, '')) = 'office bearer'
              AND COALESCE(achievement, '') <> ''
              AND LOWER(achievement) LIKE :q
            ORDER BY value
            LIMIT 50
        """
    else:
        raise HTTPException(status_code=400, detail="Unknown picker kind")
    result = await db.execute(text(sql), params)
    return [{"value": r[0]} for r in result.fetchall()]


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
        "status": r.status,
        "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
        "review_note": r.review_note,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


@router.get("/reports")
async def list_reports(
    org_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Public list of club-visible saved reports for an organisation.
    Only returns reports that have been approved by an admin."""
    rows = (await db.execute(
        select(SavedReport, User.display_name, User.username)
        .outerjoin(User, User.id == SavedReport.owner_user_id)
        .where(
            SavedReport.org_id == org_id,
            SavedReport.visibility == "club",
            SavedReport.status == "approved",
        )
        .order_by(SavedReport.view_count.desc(), SavedReport.created_at.desc())
        .limit(200)
    )).all()
    return [
        _report_to_dict(r, owner_name=(dn or un))
        for r, dn, un in rows
    ]


@router.get("/reports/pending")
async def list_pending_reports(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only list of club-visible reports awaiting approval."""
    if not await _user_can_manage_reports(db, current_user, club):
        raise HTTPException(status_code=403, detail="Missing capability: manage_reports")
    rows = (await db.execute(
        select(SavedReport, User.display_name, User.username)
        .outerjoin(User, User.id == SavedReport.owner_user_id)
        .where(
            SavedReport.org_id == club.id,
            SavedReport.visibility == "club",
            SavedReport.status == "pending",
        )
        .order_by(SavedReport.created_at.asc())
    )).all()
    return [
        _report_to_dict(r, owner_name=(dn or un))
        for r, dn, un in rows
    ]


@router.get("/reports/pending/count")
async def pending_reports_count(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Cheap count for the admin notification badge."""
    if not await _user_can_manage_reports(db, current_user, club):
        return {"count": 0}
    count = await db.scalar(
        select(func.count(SavedReport.id))
        .where(
            SavedReport.org_id == club.id,
            SavedReport.visibility == "club",
            SavedReport.status == "pending",
        )
    ) or 0
    return {"count": count}


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
    if r.status != "approved":
        # Pending/rejected reports are not publicly visible.
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

    # Club-visibility reports go to admin approval queue first unless the
    # author already has the MANAGE_REPORTS capability (admins can self-approve
    # their own saves). Private reports auto-approve since they're not listed
    # publicly anyway.
    is_admin = await _user_can_manage_reports(db, current_user, club)
    if payload.visibility == "club" and not is_admin:
        status = "pending"
    else:
        status = "approved"

    r = SavedReport(
        org_id=club.id,
        owner_user_id=current_user.id,
        slug=slug,
        title=payload.title.strip(),
        description=payload.description,
        query_json=payload.query_json,
        visibility=payload.visibility,
        status=status,
        reviewed_by_user_id=current_user.id if status == "approved" else None,
        reviewed_at=datetime.now(timezone.utc) if status == "approved" else None,
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
    is_admin = await _user_can_manage_reports(db, current_user, club)
    if payload.title is not None:
        r.title = payload.title.strip()
    if payload.description is not None:
        r.description = payload.description
    if payload.query_json is not None:
        r.query_json = payload.query_json
    # If a non-admin edits an approved club report or flips a private report
    # to club visibility, drop it back to pending so the admin re-checks.
    if payload.visibility is not None:
        flipping_to_club = (payload.visibility == "club" and r.visibility != "club")
        r.visibility = payload.visibility
        if flipping_to_club and not is_admin:
            r.status = "pending"
            r.reviewed_at = None
            r.reviewed_by_user_id = None
    elif r.visibility == "club" and payload.query_json is not None and not is_admin:
        # Query content changed — re-queue for approval.
        r.status = "pending"
        r.reviewed_at = None
        r.reviewed_by_user_id = None
    from sqlalchemy.sql import func as sql_func
    r.updated_at = sql_func.now()
    await db.commit()
    await db.refresh(r)
    return _report_to_dict(r)


class ReviewReportIn(BaseModel):
    action: str = Field(..., pattern="^(approve|reject)$")
    note: Optional[str] = Field(None, max_length=500)


@router.post("/reports/{report_id}/review")
async def review_report(
    report_id: str,
    payload: ReviewReportIn,
    club: Organisation = Depends(get_current_club),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin approval/rejection of a pending club-visibility report."""
    if not await _user_can_manage_reports(db, current_user, club):
        raise HTTPException(status_code=403, detail="Missing capability: manage_reports")
    r = await db.get(SavedReport, report_id)
    if not r or r.org_id != club.id:
        raise HTTPException(status_code=404, detail="Report not found")
    r.status = "approved" if payload.action == "approve" else "rejected"
    r.reviewed_by_user_id = current_user.id
    r.reviewed_at = datetime.now(timezone.utc)
    r.review_note = payload.note
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
