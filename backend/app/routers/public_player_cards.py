"""Player Cards on the player's own page (public, behind the same PIN cookie as the page).

A player sees their own collection and opens their own packs. Nothing here takes a player id:
the verified cookie names the player, so one player cannot open another's packs or read their
collection. The cards themselves carry only what the club already shows publicly (a name, a
photo and career figures); nothing about contact details, fees or availability.

Unauthenticated routers are not under `require_module` (the caller has no session): the club comes
from the link token and `_club_for_token(need_select=False)` decides if the link works, so a
club without BetterSelect still has cards.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import get_db
from app.routers.public_availability import _club_branding, _club_for_token, _client_ip, _player_for_session
from app.services import player_cards as cards, rate_limit
from app.services.session_safety import rollback_keeping

router = APIRouter(prefix="/public/availability", tags=["public-player-cards"])

logger = logging.getLogger(__name__)

OPEN_LIMIT = 40
OPEN_WINDOW = 60


async def _ready(db: AsyncSession, request: Request, token: str):
    """(club, player, snapshot) for a verified player of a club with cards on, else 404 / 401."""
    club = await _club_for_token(db, token, need_select=False)
    player = await _player_for_session(db, request, club)
    snap = await cards.club_snapshot(db, club)
    if not snap["settings"]["enabled"] or str(player.id) not in snap["people"]:
        raise HTTPException(status_code=404, detail="Player Cards are not available")
    return club, player, snap


@router.get("/{token}/me/cards")
async def get_my_cards(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    """The player's collection and the packs they can open now."""
    club, player, snap = await _ready(db, request, token)
    pid = str(player.id)
    # Special cards for events in the club's history, made once and kept up to date. A failure
    # here must not stop the player opening what they have.
    try:
        await cards.refresh_specials(db, club)
        await db.commit()
    except Exception:
        logger.exception("player cards: special card refresh failed for %s", club.id)
        await rollback_keeping(db, club, player)
    await cards.ensure_grants(db, club, pid, snap)
    await db.commit()
    packs = await cards.available_packs(db, pid, snap)
    collection = await cards.collection(db, club, player, snap)
    return {
        "club": _club_branding(club),
        "week_resets_at": cards.week_ends_at(snap["settings"]).isoformat(),
        "packs": packs,
        "pack_size": cards.PACK_SIZE,
        "season": snap["season_label"],
        **collection,
    }


@router.post("/{token}/me/cards/packs/{pack_id}/open")
async def open_my_pack(token: str, pack_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Open one pack. The pack is locked while it is drawn, so two taps cannot open it twice."""
    club, player, snap = await _ready(db, request, token)
    rate_limit.enforce(f"cards-open:{player.id}:{_client_ip(request)}", OPEN_LIMIT, OPEN_WINDOW,
                       detail="Slow down. Give it a few seconds and try again.")
    try:
        got = await cards.open_pack(db, club, player, pack_id, snap)
    except ValueError:
        got = None
    if got is None:
        await db.rollback()
        raise HTTPException(status_code=409, detail="That pack is not available to open.")
    await db.commit()
    packs = await cards.available_packs(db, str(player.id), snap)
    return {"cards": got, "packs_left": len(packs)}


@router.post("/{token}/me/cards/open-all")
async def open_all_my_packs(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Open every pack that is ready, up to a sensible number, and report what came out."""
    club, player, snap = await _ready(db, request, token)
    rate_limit.enforce(f"cards-open-all:{player.id}:{_client_ip(request)}", 6, OPEN_WINDOW,
                       detail="Slow down. Give it a few seconds and try again.")
    result = await cards.open_many(db, club, player, snap)
    await db.commit()
    packs = await cards.available_packs(db, str(player.id), snap)
    return {**result, "packs_left": len(packs)}
