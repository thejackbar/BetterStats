"""BetterScout — player discovery routes. Every route requires a signed-in
Scout Org user; there is no club/entitlement concept to gate on here, unlike
every other Better module. Reads (search/roster/list/get) are open to either
role; anything that WRITES an org's own tracked-player state (add, refresh,
notes, photo) requires 'owner' — see routers/scout/auth.py's
require_scout_owner docstring for why 'viewer' stops at read-only."""
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import get_db
from app.models.scout import ScoutedPlayer, ScoutOrg, ScoutUser
from app.routers.scout.auth import get_current_scout_user, require_scout_owner
from app.services import playhq_client, scout_discovery, scout_notes, scout_overview, scout_watchlist

router = APIRouter(prefix="/scout", tags=["scout-discovery"])


@router.get("/clubs/search")
async def search_clubs(
    q: str = "", current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
):
    if not q or len(q.strip()) < 2:
        return []
    results = await playhq_client.search_organisations(q.strip())
    return [
        {"id": org.get("id"), "name": org.get("name")}
        for org in results
        if org.get("id") and org.get("name")
    ]


@router.get("/clubs/{org_guid}/roster")
async def get_club_roster(
    org_guid: str, club_name: str | None = None,
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    _, org = current
    roster = await scout_discovery.get_or_start_club_roster(db, org_guid, club_name=club_name)
    await scout_overview.upsert_club_view(db, org.id, org_guid, club_name or (roster.get("org") or {}).get("name"))
    return await scout_discovery.annotate_tracking(db, org.id, roster)


@router.post("/clubs/{org_guid}/roster/refresh")
async def refresh_club_roster(
    org_guid: str, club_name: str | None = None,
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    _, org = current
    roster = await scout_discovery.get_or_start_club_roster(db, org_guid, club_name=club_name, force=True)
    await scout_overview.upsert_club_view(db, org.id, org_guid, club_name or (roster.get("org") or {}).get("name"))
    return await scout_discovery.annotate_tracking(db, org.id, roster)


@router.get("/overview")
async def get_overview(
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    _, org = current
    return await scout_overview.build_overview(db, org)


class AddPlayerRequest(BaseModel):
    org_guid: str
    player_id: str
    club_name: str | None = None
    watchlist_id: str | None = None


@router.post("/players/add")
async def add_player(
    data: AddPlayerRequest,
    current: tuple[ScoutUser, ScoutOrg] = Depends(require_scout_owner),
    db: AsyncSession = Depends(get_db),
):
    _, org = current
    try:
        return await scout_discovery.add_player(
            db, org.id, data.org_guid, data.player_id, data.club_name, data.watchlist_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class AddManualPlayerRequest(BaseModel):
    name: str
    club_name: str | None = None
    notes: str | None = None
    watchlist_id: str | None = None


@router.post("/players/manual")
async def add_manual_player(
    data: AddManualPlayerRequest,
    current: tuple[ScoutUser, ScoutOrg] = Depends(require_scout_owner),
    db: AsyncSession = Depends(get_db),
):
    if not (data.name or "").strip():
        raise HTTPException(status_code=400, detail="Name is required.")
    _, org = current
    try:
        return await scout_discovery.add_manual_player(
            db, org.id, data.name.strip(), data.club_name, data.notes, data.watchlist_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/players")
async def list_players(
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    _, org = current
    return await scout_discovery.list_tracked_players(db, org.id)


@router.get("/players/{player_id}")
async def get_player(
    player_id: str, q: str | None = None,
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    _, org = current
    player = await db.get(ScoutedPlayer, player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found.")
    out = await scout_discovery.player_out(db, player)
    out["cards"] = await scout_watchlist.cards_for_player(db, org.id, player_id)
    await scout_overview.upsert_player_search_view(db, org.id, player.id, player.name, query_text=q)
    return out


@router.post("/players/{player_id}/refresh")
async def refresh_player(
    player_id: str,
    current: tuple[ScoutUser, ScoutOrg] = Depends(require_scout_owner),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await scout_discovery.refresh_player(db, player_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── cross-club linking (a player who plays for several clubs) ─────────────

@router.get("/players/{player_id}/other-clubs")
async def get_other_club_candidates(
    player_id: str,
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    player = await db.get(ScoutedPlayer, player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found.")
    return {
        "candidates": player.other_club_candidates or [],
        "checked_at": player.other_club_candidates_checked_at.isoformat() if player.other_club_candidates_checked_at else None,
    }


@router.post("/players/{player_id}/other-clubs/scan")
async def rescan_other_clubs(
    player_id: str,
    current: tuple[ScoutUser, ScoutOrg] = Depends(require_scout_owner),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await scout_discovery.suggest_other_clubs(db, player_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class SearchOtherClubRequest(BaseModel):
    org_guid: str
    club_name: str | None = None


@router.post("/players/{player_id}/other-clubs/search-club")
async def search_other_club(
    player_id: str, data: SearchOtherClubRequest,
    current: tuple[ScoutUser, ScoutOrg] = Depends(require_scout_owner),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await scout_discovery.search_other_club(db, player_id, data.org_guid, data.club_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class LinkPlayerClubRequest(BaseModel):
    org_guid: str
    player_id: str
    is_primary: bool = False


@router.post("/players/{player_id}/clubs/link")
async def link_player_club(
    player_id: str, data: LinkPlayerClubRequest,
    current: tuple[ScoutUser, ScoutOrg] = Depends(require_scout_owner),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await scout_discovery.link_player_club(
            db, player_id, data.org_guid, data.player_id, is_primary=data.is_primary,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/players/{player_id}/clubs/{club_row_id}")
async def unlink_player_club(
    player_id: str, club_row_id: str,
    current: tuple[ScoutUser, ScoutOrg] = Depends(require_scout_owner),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await scout_discovery.unlink_player_club(db, player_id, club_row_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/players/{player_id}/tracking")
async def remove_player_tracking(
    player_id: str,
    current: tuple[ScoutUser, ScoutOrg] = Depends(require_scout_owner),
    db: AsyncSession = Depends(get_db),
):
    """The "My Players" remove action — untracks this player from every one
    of this org's watchlists. See scout_watchlist.remove_player_everywhere's
    own docstring on why this never touches the shared ScoutedPlayer row."""
    _, org = current
    try:
        n = await scout_watchlist.remove_player_everywhere(db, org.id, player_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "removed", "cards_removed": n}


# ─── scouting notes ─────────────────────────────────────────────────────────

@router.get("/players/{player_id}/notes")
async def list_notes(
    player_id: str,
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    _, org = current
    return await scout_notes.list_notes(db, org.id, player_id)


class CreateNoteRequest(BaseModel):
    body: str
    kind: str = "other"


@router.post("/players/{player_id}/notes")
async def create_note(
    player_id: str, data: CreateNoteRequest,
    current: tuple[ScoutUser, ScoutOrg] = Depends(require_scout_owner),
    db: AsyncSession = Depends(get_db),
):
    user, org = current
    try:
        return await scout_notes.create_note(db, org.id, player_id, user.id, data.body, data.kind)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class UpdateNoteRequest(BaseModel):
    body: str | None = None
    kind: str | None = None


@router.patch("/players/notes/{note_id}")
async def update_note(
    note_id: str, data: UpdateNoteRequest,
    current: tuple[ScoutUser, ScoutOrg] = Depends(require_scout_owner),
    db: AsyncSession = Depends(get_db),
):
    _, org = current
    try:
        return await scout_notes.update_note(db, note_id, org.id, data.body, data.kind)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/players/notes/{note_id}")
async def delete_note(
    note_id: str,
    current: tuple[ScoutUser, ScoutOrg] = Depends(require_scout_owner),
    db: AsyncSession = Depends(get_db),
):
    _, org = current
    try:
        await scout_notes.delete_note(db, note_id, org.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "ok"}


# ─── photo (scout-uploaded fallback — see scout_discovery.player_out) ──────

PHOTO_ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
PHOTO_MAX_BYTES = 8 * 1024 * 1024
_IMAGE_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}


@router.post("/players/{player_id}/photo")
async def upload_player_photo(
    player_id: str,
    file: UploadFile = File(...),
    current: tuple[ScoutUser, ScoutOrg] = Depends(require_scout_owner),
    db: AsyncSession = Depends(get_db),
):
    player = await db.get(ScoutedPlayer, player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found.")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in PHOTO_ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail="Image files only (jpg, png, webp, gif)")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > PHOTO_MAX_BYTES:
        raise HTTPException(status_code=400, detail="Photo must be 8 MB or smaller")
    player.photo_data = data
    player.photo_mime = _IMAGE_MIME.get(ext, "image/png")
    await db.commit()
    out = await scout_discovery.player_out(db, player)
    return {"photo_url": out["photo_url"]}


@router.delete("/players/{player_id}/photo")
async def delete_player_photo(
    player_id: str,
    current: tuple[ScoutUser, ScoutOrg] = Depends(require_scout_owner),
    db: AsyncSession = Depends(get_db),
):
    player = await db.get(ScoutedPlayer, player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found.")
    player.photo_data = None
    player.photo_mime = None
    await db.commit()
    return {"status": "cleared"}
