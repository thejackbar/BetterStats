"""AFL admin — Seasons management (list / rename / delete).

There was no way to see or manage a club's seasons directly before this —
only indirectly, through whichever picker happened to need one (the Import
Stats wizard, the leaderboard's season filter). A season minted through that
wizard (or synced from PlayHQ) still needed a normal place to fix a typo or
tidy up a display name. Mirrors cricket's season endpoints in
routers/manual_entries.py, trimmed to just seasons — grade rename/merge
already has its own AFL admin surface (routers/afl/merge.py).
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_MANUAL_ENTRIES, require_cap
from app.models.db import Organisation, Season, User, get_db
from app.routers.auth import get_current_club
from app.services.audit_log import log_activity

router = APIRouter(prefix="/club-admin/seasons", tags=["afl-seasons-admin"])


@router.get("")
async def list_seasons(
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    # Each count is its own correlated subquery rather than a JOIN — grades
    # and afl_player_season_stats can both have many rows per season, and
    # joining both into one query would fan them out against each other and
    # inflate every SUM.
    rows = await db.execute(text("""
        SELECT s.id, s.name, s.year, (s.grassroots_id IS NOT NULL) AS synced,
               (SELECT COUNT(*) FROM grades gr WHERE gr.season_id = s.id) AS grades,
               COALESCE((SELECT SUM(pss.games) FROM afl_player_season_stats pss
                         WHERE pss.season_id = s.id AND pss.grade_id IS NULL), 0) AS synced_games,
               COALESCE((SELECT SUM(i.games_played) FROM afl_imported_stats i
                         WHERE i.season_id = s.id), 0) AS imported_games,
               COALESCE((SELECT SUM(m.games_played) FROM afl_manual_adjustments m
                         WHERE m.season_id = s.id), 0) AS adjustment_games,
               (SELECT COUNT(*) FROM afl_manual_adjustments m
                WHERE m.season_id = s.id) AS adjustments
        FROM seasons s
        WHERE s.organisation_id = :org
        ORDER BY s.year DESC NULLS LAST, s.name
    """), {"org": str(club.id)})
    return [dict(r._mapping) for r in rows]


class SeasonPatch(BaseModel):
    name: Optional[str] = None
    year: Optional[int] = None


@router.patch("/{season_id}")
async def rename_season(
    season_id: str,
    data: SeasonPatch,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    try:
        sid = uuid.UUID(season_id)
    except ValueError:
        raise HTTPException(422, "Invalid season id")
    season = await db.get(Season, sid)
    if not season or season.organisation_id != club.id:
        raise HTTPException(404, "Season not found")

    before = {"name": season.name, "year": season.year}
    if data.name is not None:
        name = data.name.strip()
        if not name:
            raise HTTPException(422, "Season name is required")
        existing = await db.execute(select(Season).where(
            Season.organisation_id == club.id, Season.id != season.id,
            func.lower(Season.name) == name.lower(),
        ))
        if existing.scalar_one_or_none():
            raise HTTPException(409, f"A season named '{name}' already exists.")
        season.name = name
    if data.year is not None:
        season.year = data.year

    await log_activity(
        db, org_id=club.id, user_id=current_user.id, action="rename_season",
        target_type="season", target_id=season_id,
        details={"before": before, "after": {"name": season.name, "year": season.year}},
    )
    await db.commit()
    return {"id": str(season.id), "name": season.name, "year": season.year}


async def _season_in_use(db: AsyncSession, season_id: uuid.UUID) -> bool:
    res = await db.execute(text("""
        SELECT
            EXISTS(SELECT 1 FROM grades WHERE season_id = :sid) AS has_grades,
            EXISTS(SELECT 1 FROM afl_player_season_stats WHERE season_id = :sid) AS has_synced_stats,
            EXISTS(SELECT 1 FROM afl_imported_stats WHERE season_id = :sid) AS has_imported_stats,
            EXISTS(SELECT 1 FROM afl_manual_adjustments WHERE season_id = :sid) AS has_adjustments
    """), {"sid": str(season_id)})
    row = res.mappings().first()
    return bool(row and any(row.values()))


@router.delete("/{season_id}")
async def delete_season(
    season_id: str,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Guarded to only ever touch a season with no PlayHQ origin and nothing
    recorded against it yet — a synced season, or one with real data, has to
    have that removed (or reassigned) first, same posture as cricket's
    delete_manual_season."""
    try:
        sid = uuid.UUID(season_id)
    except ValueError:
        raise HTTPException(422, "Invalid season id")
    season = await db.get(Season, sid)
    if not season or season.organisation_id != club.id:
        raise HTTPException(404, "Season not found")
    if season.grassroots_id is not None:
        raise HTTPException(400, "This season came from the PlayHQ sync — it can't be deleted here.")
    if await _season_in_use(db, season.id):
        raise HTTPException(400, "This season has data recorded against it — remove that first.")

    await db.delete(season)
    await log_activity(
        db, org_id=club.id, user_id=current_user.id, action="delete_season",
        target_type="season", target_id=season_id, details={"name": season.name},
    )
    await db.commit()
    return {"deleted": True}
