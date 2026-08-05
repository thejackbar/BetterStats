"""AFL admin player CRUD — the club's player register.

Sport-agnostic in every way that matters: it reads/writes the shared
``players`` table (organisation_id-scoped) the exact same way cricket's
``club_admin.py`` player endpoints do. The only AFL-flavoured bit is the
per-player summary (games/goals/last played), which joins the AFL stat
tables (``afl_player_season_stats`` / ``afl_player_game_lines``) instead of
cricket's ``player_season_stats`` / ``game_appearances``.

Unlike cricket, there is deliberately no DELETE — cricket doesn't offer one
either (a player can be linked to synced game lines), only create + edit.
"""
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_PLAYERS, require_cap
from app.models.db import Organisation, Player, User, get_db
from app.routers.auth import get_current_club, get_current_user

router = APIRouter(prefix="/club-admin", tags=["afl-players-admin"])


@router.get("/players")
async def list_players(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Player).where(Player.organisation_id == club.id))
    players = sorted(result.scalars().all(), key=lambda p: (p.display_name or "").lower())

    summary_res = await db.execute(text("""
        SELECT player_id,
               COALESCE(SUM(games), 0) AS games,
               COALESCE(SUM(goals), 0) AS goals,
               COALESCE(SUM(behinds), 0) AS behinds,
               COALESCE(SUM(bog_count), 0) AS bogs
        FROM afl_player_season_stats
        WHERE organisation_id = :org AND grade_id IS NULL
        GROUP BY player_id
    """), {"org": str(club.id)})
    summary = {str(r.player_id): dict(r._mapping) for r in summary_res}

    # Historical CSV import (Import Stats) totals, added on top of the synced
    # figures — but only for a (player, season) the sync doesn't already have
    # games for, so a season covered by both never double-counts (sync wins).
    imported_res = await db.execute(text("""
        SELECT i.player_id,
               COALESCE(SUM(i.games_played), 0) AS games,
               COALESCE(SUM(i.goals), 0) AS goals,
               COALESCE(SUM(i.behinds), 0) AS behinds,
               COALESCE(SUM(i.bog_count), 0) AS bogs
        FROM afl_imported_stats i
        WHERE i.organisation_id = :org
          AND NOT EXISTS (
            SELECT 1 FROM afl_player_season_stats s
            WHERE s.player_id = i.player_id AND s.season_id = i.season_id
              AND s.grade_id IS NULL AND s.games > 0
          )
        GROUP BY i.player_id
    """), {"org": str(club.id)})
    imported = {str(r.player_id): dict(r._mapping) for r in imported_res}

    # Club/competition B&F vote tallies have no synced counterpart at all —
    # PlayHQ carries no concept of club-internal best & fairest voting, so
    # unlike games/goals/behinds/bogs there's nothing to reconcile against
    # afl_player_season_stats here, just a straight sum of every imported row.
    votes_res = await db.execute(text("""
        SELECT player_id,
               COALESCE(SUM(club_bf_votes), 0) AS club_bf_votes,
               COALESCE(SUM(comp_bf_votes), 0) AS comp_bf_votes
        FROM afl_imported_stats
        WHERE organisation_id = :org
        GROUP BY player_id
    """), {"org": str(club.id)})
    votes = {str(r.player_id): dict(r._mapping) for r in votes_res}

    last_res = await db.execute(text("""
        SELECT l.player_id, MAX(g.played_at) AS last_played
        FROM afl_player_game_lines l
        JOIN games g ON g.id = l.game_id
        WHERE l.player_id IS NOT NULL
          AND l.player_id IN (SELECT id FROM players WHERE organisation_id = :org)
        GROUP BY l.player_id
    """), {"org": str(club.id)})
    last_played = {str(r.player_id): (r.last_played.isoformat() if r.last_played else None) for r in last_res}

    return [
        {
            "id": str(p.id),
            "name": p.name,
            "display_name": p.display_name,
            "display_name_override": p.display_name_override,
            "playhq_id": p.playhq_id,
            "photo_url": p.photo_url,
            "gender": p.gender,
            "email": p.email,
            "phone": p.phone,
            "status": p.status,
            "games": summary.get(str(p.id), {}).get("games", 0) + imported.get(str(p.id), {}).get("games", 0),
            "goals": summary.get(str(p.id), {}).get("goals", 0) + imported.get(str(p.id), {}).get("goals", 0),
            "behinds": summary.get(str(p.id), {}).get("behinds", 0) + imported.get(str(p.id), {}).get("behinds", 0),
            "bogs": summary.get(str(p.id), {}).get("bogs", 0) + imported.get(str(p.id), {}).get("bogs", 0),
            "club_bf_votes": votes.get(str(p.id), {}).get("club_bf_votes", 0),
            "comp_bf_votes": votes.get(str(p.id), {}).get("comp_bf_votes", 0),
            "has_imported_stats": str(p.id) in imported,
            "last_played": last_played.get(str(p.id)),
        }
        for p in players
    ]


@router.get("/players/{player_id}")
async def get_player(
    player_id: str,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player or player.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Player not found")
    return {
        "id": str(player.id),
        "name": player.name,
        "display_name": player.display_name,
        "display_name_override": player.display_name_override,
        "playhq_id": player.playhq_id,
        "photo_url": player.photo_url,
        "gender": player.gender,
        "email": player.email,
        "phone": player.phone,
        "status": player.status,
    }


class PlayerCreate(BaseModel):
    first_name: str
    last_name: str
    playhq_id: Optional[str] = None
    display_name_override: Optional[str] = None


@router.post("/players")
async def create_player(
    data: PlayerCreate,
    current_user: User = Depends(require_cap(MANAGE_PLAYERS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    first = data.first_name.strip()
    last = data.last_name.strip()
    if not first or not last:
        raise HTTPException(status_code=422, detail="First name and last name are required")

    name = f"{last}, {first}"
    phq_id = data.playhq_id.strip() if data.playhq_id else None
    override = (data.display_name_override.strip() or None) if data.display_name_override else None

    if phq_id:
        conflict = await db.execute(select(Player).where(
            Player.organisation_id == club.id, Player.playhq_id == phq_id))
        if conflict.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Another player already has this PlayHQ ID")

    player = Player(
        id=uuid.uuid4(), name=name, organisation_id=club.id,
        playhq_id=phq_id, display_name_override=override,
    )
    db.add(player)
    await db.commit()
    return {"id": str(player.id), "name": player.name, "display_name": player.display_name}


class PlayerPatch(BaseModel):
    display_name_override: Optional[str] = None
    playhq_id: Optional[str] = None
    gender: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    status: Optional[str] = None


@router.patch("/players/{player_id}")
async def patch_player(
    player_id: str,
    data: PlayerPatch,
    current_user: User = Depends(require_cap(MANAGE_PLAYERS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player or player.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Player not found")

    if data.display_name_override is not None:
        player.display_name_override = data.display_name_override.strip() or None
    if data.playhq_id is not None:
        new_phq = data.playhq_id.strip() or None
        if new_phq and new_phq != player.playhq_id:
            conflict = await db.execute(select(Player).where(
                Player.organisation_id == club.id, Player.playhq_id == new_phq, Player.id != player.id))
            if conflict.scalar_one_or_none():
                raise HTTPException(status_code=409, detail="Another player already has this PlayHQ ID")
        player.playhq_id = new_phq
    if data.gender is not None:
        player.gender = data.gender.strip() or None
    if data.email is not None:
        player.email = data.email.strip() or None
    if data.phone is not None:
        player.phone = data.phone.strip() or None
    if data.status is not None:
        player.status = data.status.strip() or "active"

    await db.commit()
    return {
        "id": str(player.id), "display_name": player.display_name,
        "playhq_id": player.playhq_id, "gender": player.gender,
        "email": player.email, "phone": player.phone, "status": player.status,
    }


# ---------------------------------------------------------------------------
# Player photos
# ---------------------------------------------------------------------------
#
# Bytes go in the players table, not on disk, and are served back by the
# shared images router (mounted by afl_main) — same as every other image this
# platform stores, and the upload volume isn't guaranteed to survive a
# redeploy.
#
# photo_url is stored WITHOUT a leading slash or an /api prefix, unlike
# cricket's, which hardcodes "/api/images/...". Cricket is served from the
# domain root; the AFL app lives under /afl/, so an absolute /api/... path
# would 404 on betterat.football. An API-relative value lets the frontend
# resolve it against whatever base the bundle was built with (aflApi's
# mediaUrl), and leaves any absolute URL already in the column — a PlayHQ
# avatar, say — passing through untouched.

PHOTO_ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
PHOTO_MAX_BYTES = 2 * 1024 * 1024
_PHOTO_MIME = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".gif": "image/gif",
}


async def _own_player(db: AsyncSession, club: Organisation, player_id: str) -> Player:
    try:
        pid = uuid.UUID(player_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Player not found")
    player = await db.get(Player, pid)
    if not player or player.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Player not found")
    return player


@router.post("/players/{player_id}/photo")
async def upload_player_photo(
    player_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(require_cap(MANAGE_PLAYERS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    player = await _own_player(db, club, player_id)

    ext = Path(file.filename or "").suffix.lower()
    if ext not in PHOTO_ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail="Image files only (jpg, png, webp, gif)")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > PHOTO_MAX_BYTES:
        raise HTTPException(status_code=400, detail="Photo must be 2 MB or smaller")

    player.photo_data = data
    player.photo_mime = _PHOTO_MIME.get(ext, "image/png")
    # The ?v= is what gets a replacement past the images router's long
    # cache headers — without it a new photo keeps showing as the old one.
    player.photo_url = f"images/players/{player.id}/photo?v={uuid.uuid4().hex[:8]}"
    await db.commit()
    return {"photo_url": player.photo_url}


@router.delete("/players/{player_id}/photo")
async def delete_player_photo(
    player_id: str,
    current_user: User = Depends(require_cap(MANAGE_PLAYERS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    player = await _own_player(db, club, player_id)
    player.photo_data = None
    player.photo_mime = None
    player.photo_url = None
    await db.commit()
    return {"status": "cleared"}
