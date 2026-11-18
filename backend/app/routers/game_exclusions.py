"""A club marks a player as named for a synced game but not having played it (12th man, 13th man,
late withdrawal), from the match page or the player's Adjustments screen, and works through the
"Games to check" list. See `services/game_exclusions.py` for where the mark lives and why.

Gated by MANAGE_MANUAL_ENTRIES, the same capability as every other hand-typed correction, and
logged on the Manual entries audit trail, where each change can be undone.

    GET    /games/{id}/team-list                              the club's players named in the game
    GET    /games/{id}/not-played/{player}/adjustments        a -1 season adjustment the mark could replace
    POST   /games/{id}/not-played                             mark a player as not having played
    DELETE /games/{id}/not-played/{player}                    take the mark off
    GET    /club-admin/game-exclusions/players/{player}/games every synced game the player was named in
    GET    /club-admin/game-exclusions/suggestions            the "Games to check" list
    POST   /club-admin/game-exclusions/suggestions/dismiss    keep a suggestion as played
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_MANUAL_ENTRIES, require_cap
from app.models.db import Organisation, Player, User, get_db
from app.routers.auth import get_current_club
from app.routers.manual_entries import _log_edit, _recompute_milestones
from app.services import game_exclusions as gx

router = APIRouter(tags=["games"])

TABLE = "game_exclusions"


class NotPlayedIn(BaseModel):
    player_id: str
    reason: str
    note: Optional[str] = Field(default=None, max_length=300)
    # A season adjustment of -1 the club typed for this game before it could pick the game itself.
    swap_adjustment_id: Optional[int] = None


class DismissIn(BaseModel):
    game_id: str
    player_id: str


def _uuid(v: str, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(v))
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail=f"That is not a valid {what} id.")


def _summary(row: dict, what: str) -> str:
    """"Marsh, Roy marked as 13th man: East Fremantle v Piara Waters on 7 Mar 2015"."""
    when = ""
    if row.get("played_at"):
        d = date.fromisoformat(row["played_at"])
        when = f" on {d.day} {d.strftime('%b %Y')}"
    match = f"{row.get('home_team') or ''} v {row.get('away_team') or ''}".strip()
    return f"{row['player_name']} {what}: {match}{when}"


@router.get("/games/{game_id}/not-played")
async def public_not_played(game_id: str, db: AsyncSession = Depends(get_db)):
    """Public: who a club marked as named for this match but not playing it, and why, so the
    scorecard can say so. A player hidden for privacy is left out."""
    return {"players": await gx.public_marks(db, _uuid(game_id, "match"))}


@router.get("/games/{game_id}/team-list")
async def team_list(
    game_id: str,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    gid = _uuid(game_id, "match")
    return {"game_id": str(gid), "players": await gx.team_list(db, club.id, gid),
            "reasons": [{"key": k, "label": v} for k, v in gx.REASONS.items()]}


@router.get("/games/{game_id}/not-played/{player_id}/adjustments")
async def swap_candidates(
    game_id: str,
    player_id: str,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    return {"adjustments": await gx.adjustments_to_swap(
        db, club.id, _uuid(player_id, "player"), _uuid(game_id, "match"))}


@router.post("/games/{game_id}/not-played")
async def mark_not_played(
    game_id: str,
    data: NotPlayedIn,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    gid, pid = _uuid(game_id, "match"), _uuid(data.player_id, "player")
    try:
        snap = await gx.mark(db, club.id, current_user.id, gid, pid, data.reason, data.note,
                             data.swap_adjustment_id)
    except gx.MarkRefused as e:
        raise HTTPException(status_code=e.status, detail=str(e))
    row = await gx.one(db, club.id, gid, pid)
    summary = _summary(row, "marked as not having played" if data.reason == "other"
                       else f"marked as {gx.REASONS[data.reason].lower()}")
    if snap.get("swapped_adjustment_id"):
        summary += " (a -1 season adjustment was moved onto this game)"
    await _log_edit(db, org_id=club.id, user_id=current_user.id, action="create", target_table=TABLE,
                    target_id=str(snap["id"]), summary=summary, before=None, after=snap)
    await db.commit()
    await _recompute_milestones(db, club.id, [pid])
    return {"player": await gx.one(db, club.id, gid, pid), "summary": summary}


@router.delete("/games/{game_id}/not-played/{player_id}")
async def unmark_not_played(
    game_id: str,
    player_id: str,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    gid, pid = _uuid(game_id, "match"), _uuid(player_id, "player")
    ex_id = await gx.find(db, club.id, gid, pid)
    if ex_id is None:
        raise HTTPException(status_code=404, detail="That player is not marked as not having played this game.")
    row = await gx.one(db, club.id, gid, pid)
    snap = await gx.unmark(db, club.id, ex_id)
    summary = _summary(row, "counted as playing again")
    if snap.get("swapped_adjustment_id"):
        summary += " (the -1 season adjustment it replaced is back)"
    await _log_edit(db, org_id=club.id, user_id=current_user.id, action="delete", target_table=TABLE,
                    target_id=str(ex_id), summary=summary, before=snap, after=None)
    await db.commit()
    await _recompute_milestones(db, club.id, [pid])
    return {"player": await gx.one(db, club.id, gid, pid), "summary": summary}


@router.get("/club-admin/game-exclusions/players/{player_id}/games")
async def player_games(
    player_id: str,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    pid = _uuid(player_id, "player")
    player = await db.get(Player, pid)
    if player is None or player.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="That player is not one of this club's.")
    return {"player_id": str(pid), "games": await gx.player_games(db, club.id, pid),
            "reasons": [{"key": k, "label": v} for k, v in gx.REASONS.items()]}


@router.get("/club-admin/game-exclusions/suggestions")
async def suggestions(
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    out = await gx.suggestions(db, club.id)
    return {**out, "reasons": [{"key": k, "label": v} for k, v in gx.REASONS.items()]}


@router.post("/club-admin/game-exclusions/suggestions/dismiss")
async def dismiss(
    data: DismissIn,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    gid, pid = _uuid(data.game_id, "match"), _uuid(data.player_id, "player")
    if await gx.one(db, club.id, gid, pid) is None:
        raise HTTPException(status_code=404, detail="That player is not on this club's team sheet for that match.")
    await gx.dismiss(db, club.id, current_user.id, gid, pid)
    await db.commit()
    return {"dismissed": True}
