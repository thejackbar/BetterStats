"""Public club resolution — the AFL counterpart of cricket's routers/clubs.py.

GET /clubs/{slug} is the public site's entry point: branding + the season and
grade lists every other page's filters hang off.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Organisation, get_db

router = APIRouter(prefix="/clubs", tags=["afl-clubs"])


async def resolve_org(db: AsyncSession, slug_or_id: str) -> Organisation:
    org = None
    try:
        org = await db.get(Organisation, uuid.UUID(slug_or_id))
    except ValueError:
        pass
    if org is None:
        res = await db.execute(select(Organisation).where(Organisation.slug == slug_or_id))
        org = res.scalar_one_or_none()
    if org is None or org.archived_at is not None:
        raise HTTPException(status_code=404, detail="Club not found")
    if not org.is_active:
        raise HTTPException(status_code=403, detail={"code": "inactive", "message": "This club page is not active."})
    return org


@router.get("/{slug}")
async def get_club(slug: str, db: AsyncSession = Depends(get_db)):
    org = await resolve_org(db, slug)
    seasons = await db.execute(text("""
        SELECT s.id, s.name, s.year,
               COUNT(gr.id) AS grade_count
        FROM seasons s
        LEFT JOIN grades gr ON gr.season_id = s.id
        WHERE s.organisation_id = :org
        GROUP BY s.id, s.name, s.year
        ORDER BY s.year DESC NULLS LAST, s.name DESC
    """), {"org": str(org.id)})
    grades = await db.execute(text("""
        SELECT gr.id, gr.name, gr.display_name_override, gr.season_id
        FROM grades gr
        JOIN seasons s ON s.id = gr.season_id
        WHERE s.organisation_id = :org AND gr.is_public
        ORDER BY gr.name
    """), {"org": str(org.id)})
    return {
        "id": str(org.id),
        "name": org.name,
        "short_name": org.short_name,
        "slug": org.slug,
        "logo_url": org.logo_url,
        "primary_color": org.primary_color,
        "accent_color": org.accent_color,
        "theme_mode": org.theme_mode,
        "theme_config": org.theme_config,
        "player_name_format": org.player_name_format,
        "sport": "afl",
        "seasons": [dict(r._mapping) for r in seasons],
        "grades": [dict(r._mapping) for r in grades],
    }
