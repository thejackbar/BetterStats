"""AFL Sponsors — thin port of cricket's club_admin.py sponsor endpoints.

The ``Sponsor``/``org_sponsors`` model carries zero cricket-specific columns
and is already SQLAlchemy-mapped on the shared Base, so it's auto-created in
the AFL database by ``Base.metadata.create_all`` — no new table needed here.
Unlike cricket's version (which only requires a logged-in user), every write
here is properly capability-gated on MANAGE_SPONSORS.
"""
import time
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_SPONSORS, require_cap
from app.models.db import Organisation, Sponsor, User, get_db
from app.routers.auth import get_current_club, get_current_user

router = APIRouter(prefix="/club-admin", tags=["afl-sponsors"])


def _sponsor_dict(s: Sponsor) -> dict:
    return {
        "id": str(s.id),
        "name": s.name,
        "website_url": s.website_url,
        "logo_url": s.logo_url,
        "display_order": s.display_order,
    }


@router.get("/sponsors")
async def list_sponsors(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Sponsor).where(Sponsor.organisation_id == club.id)
                              .order_by(Sponsor.display_order, Sponsor.created_at))
    return [_sponsor_dict(s) for s in result.scalars().all()]


class SponsorCreate(BaseModel):
    name: str
    website_url: Optional[str] = None


@router.post("/sponsors")
async def create_sponsor(
    data: SponsorCreate,
    current_user: User = Depends(require_cap(MANAGE_SPONSORS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name is required")
    result = await db.execute(select(func.max(Sponsor.display_order)).where(Sponsor.organisation_id == club.id))
    max_order = result.scalar() or 0
    sponsor = Sponsor(
        organisation_id=club.id, name=name,
        website_url=data.website_url.strip() if data.website_url else None,
        display_order=max_order + 1,
    )
    db.add(sponsor)
    await db.commit()
    return _sponsor_dict(sponsor)


class SponsorPatch(BaseModel):
    name: Optional[str] = None
    website_url: Optional[str] = None


@router.patch("/sponsors/{sponsor_id}")
async def patch_sponsor(
    sponsor_id: str,
    data: SponsorPatch,
    current_user: User = Depends(require_cap(MANAGE_SPONSORS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    sponsor = await db.get(Sponsor, uuid.UUID(sponsor_id))
    if not sponsor or sponsor.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Sponsor not found")
    if data.name is not None:
        sponsor.name = data.name.strip() or sponsor.name
    if data.website_url is not None:
        sponsor.website_url = data.website_url.strip() or None
    await db.commit()
    return _sponsor_dict(sponsor)


@router.post("/sponsors/{sponsor_id}/logo")
async def upload_sponsor_logo(
    sponsor_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(require_cap(MANAGE_SPONSORS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    sponsor = await db.get(Sponsor, uuid.UUID(sponsor_id))
    if not sponsor or sponsor.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Sponsor not found")
    if file.content_type not in ("image/png", "image/jpeg", "image/svg+xml", "image/webp", "image/gif"):
        raise HTTPException(status_code=422, detail="Unsupported image type")
    data = await file.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Logo must be under 8 MB")
    sponsor.logo_data = data
    sponsor.logo_mime = file.content_type
    sponsor.logo_url = f"/images/sponsors/{sponsor_id}/logo?v={int(time.time())}"
    await db.commit()
    return _sponsor_dict(sponsor)


@router.delete("/sponsors/{sponsor_id}/logo")
async def delete_sponsor_logo(
    sponsor_id: str,
    current_user: User = Depends(require_cap(MANAGE_SPONSORS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    sponsor = await db.get(Sponsor, uuid.UUID(sponsor_id))
    if not sponsor or sponsor.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Sponsor not found")
    sponsor.logo_data = None
    sponsor.logo_mime = None
    sponsor.logo_url = None
    await db.commit()
    return _sponsor_dict(sponsor)


@router.delete("/sponsors/{sponsor_id}")
async def delete_sponsor(
    sponsor_id: str,
    current_user: User = Depends(require_cap(MANAGE_SPONSORS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    sponsor = await db.get(Sponsor, uuid.UUID(sponsor_id))
    if not sponsor or sponsor.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Sponsor not found")
    await db.delete(sponsor)
    await db.commit()
    return {"ok": True}


class SponsorReorderItem(BaseModel):
    id: str
    display_order: int


@router.put("/sponsors/reorder")
async def reorder_sponsors(
    items: list[SponsorReorderItem],
    current_user: User = Depends(require_cap(MANAGE_SPONSORS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    for item in items:
        sponsor = await db.get(Sponsor, uuid.UUID(item.id))
        if sponsor and sponsor.organisation_id == club.id:
            sponsor.display_order = item.display_order
    await db.commit()
    return {"ok": True}
