"""Match a hand-made player to their PlayCricket profile.

``GET  /club-admin/player-identity/search?q=``  people PlayCricket knows by that name
``POST /club-admin/player-identity/link``       tie an existing player to a chosen one

Creating a player with an identity goes through each creator's own route (the
Add player form, Fantasy's "new player"), which take an optional
``participant_id`` and call ``player_identity.assert_identity_free``. This router
is the search they share, and the link for a player who already exists, which is
the case the roster is in the day this ships.

Core, not module-gated: every club has players, and the duplicate this prevents
is a BetterStats problem before it is a Fantasy or BetterSelect one. Any of the
capabilities that can create a player may search and link.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import (
    MANAGE_FANTASY, MANAGE_PLAYERS, MANAGE_SELECTIONS, require_any_cap,
)
from app.models.db import Player, User, get_db
from app.routers.auth import get_current_club
from app.services import player_identity, rate_limit

router = APIRouter(prefix="/club-admin/player-identity", tags=["club-admin-player-identity"])

_allowed = require_any_cap(MANAGE_PLAYERS, MANAGE_FANTASY, MANAGE_SELECTIONS)


@router.get("/search")
async def search(
    q: str = "",
    club=Depends(get_current_club),
    user: User = Depends(_allowed),
    db: AsyncSession = Depends(get_db),
):
    # Every keystroke that survives the browser's debounce reaches Cricket
    # Australia's index, so it is capped per user like the other upstream-facing
    # searches.
    rate_limit.enforce(f"player-identity-search:{user.id}", 90, 300,
                       "Too many searches, wait a moment and try again.")
    return await player_identity.search_candidates(db, club, q)


class LinkBody(BaseModel):
    player_id: str
    participant_id: str


@router.post("/link")
async def link(
    body: LinkBody,
    club=Depends(get_current_club),
    user: User = Depends(_allowed),
    db: AsyncSession = Depends(get_db),
):
    try:
        pid = uuid.UUID(str(body.player_id))
    except ValueError:
        raise HTTPException(status_code=404, detail="Player not found")
    player = await db.get(Player, pid)
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return await player_identity.link_player(db, club, player, body.participant_id)
