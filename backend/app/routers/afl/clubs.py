"""Public club resolution — the AFL counterpart of cricket's routers/clubs.py.

GET /clubs/{slug} is the public site's entry point: branding + the season and
grade lists every other page's filters hang off.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Organisation, get_db
from app.services.afl.aggregations import _resolve_canonical_grade

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
    raw_grades = await db.execute(text("""
        SELECT gr.id, gr.name, gr.display_name_override, gr.season_id, gr.category
        FROM grades gr
        JOIN seasons s ON s.id = gr.season_id
        WHERE s.organisation_id = :org AND gr.is_public
        ORDER BY gr.name
    """), {"org": str(org.id)})
    logs = await db.execute(text(
        "SELECT alias_name, canonical_name FROM grade_merge_logs WHERE org_id = :org AND undone_at IS NULL"
    ), {"org": str(org.id)})
    alias_to_canonical = {r["alias_name"]: r["canonical_name"] for r in logs.mappings().all()}

    # Merging two grades (Merge Grades, admin) folds their raw rows into one
    # competition for stats purposes — the public grade filter must fold them
    # into one option too, or a merged grade still shows as N separate
    # (often sponsor-suffixed) duplicates in every filter dropdown. One
    # option per canonical name; season_ids lists every season it's fielded
    # in (a merge often spans several), so a season+grade cross filter still
    # narrows correctly. `id` is a representative member row — any one
    # works, since every grade-filtered read expands it back to the whole
    # merge group (see matching_grade_ids).
    bucket: dict[str, dict] = {}
    for row in raw_grades.mappings().all():
        canonical = _resolve_canonical_grade(alias_to_canonical, row["name"])
        slot = bucket.setdefault(canonical, {
            "id": row["id"], "name": canonical, "display_name_override": None,
            "category": None, "season_ids": [],
        })
        if row["display_name_override"] and not slot["display_name_override"]:
            slot["display_name_override"] = row["display_name_override"]
        if row["category"] and not slot["category"]:
            slot["category"] = row["category"]
        if row["season_id"] not in slot["season_ids"]:
            slot["season_ids"].append(row["season_id"])
    grades = sorted(bucket.values(), key=lambda g: (g["display_name_override"] or g["name"]).lower())

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
        "grades": grades,
    }
