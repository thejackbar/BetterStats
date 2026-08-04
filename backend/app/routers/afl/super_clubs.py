"""Better HQ — All Clubs (AFL). Super-admin club management.

Deliberately trimmed relative to cricket's SuperClubs surface: AFL has no
billing/module-marketplace/CRM/coupon system yet, so this only manages what
actually exists here — club identity/branding, active/archived state, sync
control and primary-admin assignment. All fields used
(``Organisation.archived_at``/``is_active``/branding, ``ClubMembership.
is_primary_admin``) are plain ORM columns already shared with cricket, so
nothing here needed a new table.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import ClubMembership, Organisation, SyncRun, User, get_db
from app.routers.afl.club_admin import _has_running_sync, _run_sync, _spawn
from app.routers.auth import require_super_admin
from app.services.afl import sync as afl_sync
from app.services.memberships import set_primary_admin

router = APIRouter(prefix="/club-admin/super", tags=["afl-super-clubs"])


async def _club_payload(db: AsyncSession, org: Organisation) -> dict:
    admin_res = await db.execute(text("""
        SELECT u.display_name, u.username, u.email
        FROM club_memberships cm JOIN users u ON u.id = cm.user_id
        WHERE cm.club_id = :org
        ORDER BY cm.is_primary_admin DESC, cm.created_at ASC LIMIT 1
    """), {"org": str(org.id)})
    admin = admin_res.mappings().first()

    last_sync_res = await db.execute(select(SyncRun).where(SyncRun.org_id == org.id)
                                     .order_by(SyncRun.started_at.desc()).limit(1))
    last_sync = last_sync_res.scalar_one_or_none()

    return {
        "id": str(org.id),
        "name": org.name,
        "short_name": org.short_name,
        "slug": org.slug,
        "playhq_id": org.playhq_id,
        "is_active": org.is_active,
        "archived": org.archived_at is not None,
        "archived_at": org.archived_at.isoformat() if org.archived_at else None,
        "primary_color": org.primary_color,
        "accent_color": org.accent_color,
        "logo_url": org.logo_url,
        "admin_name": (admin["display_name"] or admin["username"]) if admin else None,
        "admin_email": admin["email"] if admin else None,
        "last_sync_status": last_sync.status if last_sync else None,
        "last_sync_at": last_sync.started_at.isoformat() if last_sync and last_sync.started_at else None,
    }


@router.get("/clubs")
async def list_clubs(
    q: Optional[str] = None,
    include_archived: bool = False,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Organisation)
    if not include_archived:
        stmt = stmt.where(Organisation.archived_at.is_(None))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(Organisation.name.ilike(like))
    stmt = stmt.order_by(Organisation.name)
    result = await db.execute(stmt)
    orgs = result.scalars().all()
    return {"clubs": [await _club_payload(db, o) for o in orgs], "total": len(orgs)}


class RegisterClubRequest(BaseModel):
    playhq_org_id: str
    sync_now: bool = True


@router.post("/clubs")
async def create_club(
    body: RegisterClubRequest,
    user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Register a new club by its PlayHQ org code — the hex code in a
    playhq.com/afl/org/.../CODE URL. This is the one club-creation path
    (also used by the plain sync page's "Register a club" box)."""
    org = await afl_sync.register_organisation(db, body.playhq_org_id.strip())
    run_id = None
    if body.sync_now and not await _has_running_sync(db, org.id):
        run_id = await afl_sync.start_sync_run(org.id, "afl_full", triggered_by_user_id=user.id)
        _spawn(_run_sync(org.id, run_id, full=True))
    return {"organisation_id": str(org.id), "slug": org.slug, "name": org.name,
            "run_id": str(run_id) if run_id else None}


class ClubPatch(BaseModel):
    name: Optional[str] = None
    short_name: Optional[str] = None
    slug: Optional[str] = None
    primary_color: Optional[str] = None
    accent_color: Optional[str] = None
    is_active: Optional[bool] = None


@router.patch("/clubs/{club_id}")
async def patch_club(
    club_id: str, body: ClubPatch,
    _: User = Depends(require_super_admin), db: AsyncSession = Depends(get_db),
):
    org = await db.get(Organisation, uuid.UUID(club_id))
    if not org:
        raise HTTPException(status_code=404, detail="Club not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "slug" and value:
            value = value.strip().lower()
        setattr(org, field, value)
    await db.commit()
    return await _club_payload(db, org)


@router.post("/clubs/{club_id}/archive")
async def archive_club(
    club_id: str, _: User = Depends(require_super_admin), db: AsyncSession = Depends(get_db),
):
    org = await db.get(Organisation, uuid.UUID(club_id))
    if not org:
        raise HTTPException(status_code=404, detail="Club not found")
    org.archived_at = datetime.now(timezone.utc)
    await db.commit()
    return await _club_payload(db, org)


@router.post("/clubs/{club_id}/restore")
async def restore_club(
    club_id: str, _: User = Depends(require_super_admin), db: AsyncSession = Depends(get_db),
):
    org = await db.get(Organisation, uuid.UUID(club_id))
    if not org:
        raise HTTPException(status_code=404, detail="Club not found")
    org.archived_at = None
    await db.commit()
    return await _club_payload(db, org)


@router.post("/clubs/{club_id}/sync")
async def sync_club(
    club_id: str, user: User = Depends(require_super_admin), db: AsyncSession = Depends(get_db),
):
    org = await db.get(Organisation, uuid.UUID(club_id))
    if not org:
        raise HTTPException(status_code=404, detail="Club not found")
    if await _has_running_sync(db, org.id):
        raise HTTPException(status_code=409, detail="A sync is already running")
    run_id = await afl_sync.start_sync_run(org.id, "afl_sync", triggered_by_user_id=user.id)
    _spawn(_run_sync(org.id, run_id, full=False))
    return {"status": "started", "run_id": str(run_id)}


@router.get("/clubs/{club_id}/admins")
async def list_club_admins(
    club_id: str, _: User = Depends(require_super_admin), db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ClubMembership, User)
                              .join(User, User.id == ClubMembership.user_id)
                              .where(ClubMembership.club_id == uuid.UUID(club_id))
                              .order_by(ClubMembership.is_primary_admin.desc(), ClubMembership.created_at.asc()))
    return [
        {"user_id": str(m.user_id), "display_name": u.display_name or u.username,
         "email": u.email, "is_primary_admin": bool(m.is_primary_admin)}
        for m, u in result.all()
    ]


class PrimaryAdminBody(BaseModel):
    user_id: str


@router.put("/clubs/{club_id}/primary-admin")
async def set_club_primary_admin(
    club_id: str, body: PrimaryAdminBody,
    _: User = Depends(require_super_admin), db: AsyncSession = Depends(get_db),
):
    try:
        await set_primary_admin(db, uuid.UUID(club_id), uuid.UUID(body.user_id))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return {"status": "ok"}
