"""Public club routes: slug-based lookup and inactive-club gating."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.db import Organisation, Season, Sponsor, get_db
from app.routers.organisations import _season_sort_key
from app.auth.modules import org_core_live

router = APIRouter(prefix="/clubs", tags=["clubs"])

INACTIVE_DETAIL = "This club page is currently not available. Contact your club executives to get access."


def _public_blocked(org) -> bool:
    """A club's public surfaces are hidden when it's manually inactive OR its
    BetterStats (Core) module isn't live (cancelled / expired trial / master switch
    off). org must be loaded with module_subscriptions for the Core check."""
    return (not org.is_active) or (not org_core_live(org))


@router.get("/{slug}")
async def get_club_by_slug(slug: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Organisation).where(Organisation.slug == slug.lower())
        .options(selectinload(Organisation.module_subscriptions))
    )
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Club not found")
    if _public_blocked(org):
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
        "theme_config": org.theme_config or {},
        "contact_email": org.contact_email,
        "player_name_format": org.player_name_format or "last_first",
        "website_enabled": bool(org.website_enabled),
    }


@router.get("/{slug}/sponsors")
async def get_club_sponsors(slug: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Organisation).where(Organisation.slug == slug.lower())
        .options(selectinload(Organisation.module_subscriptions))
    )
    org = result.scalar_one_or_none()
    if not org or _public_blocked(org):
        raise HTTPException(status_code=404, detail="Club not found")

    sponsors_result = await db.execute(
        select(Sponsor)
        .where(Sponsor.organisation_id == org.id)
        .order_by(Sponsor.display_order, Sponsor.created_at)
    )
    sponsors = sponsors_result.scalars().all()

    # Determine the current (most recent) season name
    seasons_result = await db.execute(
        select(Season).where(Season.organisation_id == org.id)
    )
    all_seasons = seasons_result.scalars().all()
    current_season = None
    if all_seasons:
        sorted_seasons = sorted(all_seasons, key=_season_sort_key)
        current_season = sorted_seasons[0].name if sorted_seasons else None

    return {
        "club_name": org.short_name or org.name,
        "current_season": current_season,
        "sponsors": [
            {
                "id": str(s.id),
                "name": s.name,
                "website_url": s.website_url,
                "logo_url": s.logo_url,
            }
            for s in sponsors
            if s.logo_url  # only show sponsors that have a logo
        ],
    }
