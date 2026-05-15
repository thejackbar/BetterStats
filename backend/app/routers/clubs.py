"""Public club routes: slug-based lookup and inactive-club gating."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.db import Organisation, get_db

router = APIRouter(prefix="/clubs", tags=["clubs"])

INACTIVE_DETAIL = "This club page is currently not available. Contact your club executives to get access."


@router.get("/{slug}")
async def get_club_by_slug(slug: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Organisation).where(Organisation.slug == slug.lower()))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Club not found")
    if not org.is_active:
        raise HTTPException(status_code=403, detail=INACTIVE_DETAIL)
    return {
        "id": str(org.id),
        "slug": org.slug,
        "name": org.name,
        "short_name": org.short_name,
        "is_active": org.is_active,
        "primary_color": org.primary_color,
        "accent_color": org.accent_color,
        "logo_url": org.logo_url,
        "hero_image_url": org.hero_image_url,
        "theme_mode": org.theme_mode,
        "contact_email": org.contact_email,
        "player_name_format": org.player_name_format or "last_first",
    }
