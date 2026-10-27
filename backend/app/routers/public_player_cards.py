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
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import get_db
from app.routers.public_availability import _club_branding, _club_for_token, _client_ip, _player_for_session
from app.services import player_card_swaps as swaps, player_cards as cards, rate_limit
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


# ── Swaps ─────────────────────────────────────────────────────────────────────────────────────────────────────

SWAP_LIMIT = 30
SWAP_WINDOW = 60


class SwapCard(BaseModel):
    key: str
    qty: int = 1


class SwapBody(BaseModel):
    """Many cards each way: `give` and `want` are lists of `{key, qty}`. The single `give_key` / `want_key` of
    the first release are still read, so a page that was open before the change can finish what it started."""
    to_player_id: str
    give: Optional[list[SwapCard]] = None
    want: Optional[list[SwapCard]] = None
    give_key: Optional[str] = None
    want_key: Optional[str] = None


def _refuse(exc: swaps.SwapError):
    return HTTPException(status_code=exc.status, detail=exc.message)


@router.get("/{token}/me/cards/swaps")
async def get_my_swaps(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Swap requests in and out, the cards the player could offer, and who has cards to offer."""
    club, player, snap = await _ready(db, request, token)
    me = str(player.id)
    return {
        **await swaps.list_swaps(db, club, snap, me),
        "mine": await swaps.tradeable_cards(db, club, snap, me),
        "people": await swaps.swap_people(db, club, snap, me),
        "expires_days": swaps.SWAP_DAYS,
        "max_open": swaps.MAX_OUTGOING,
    }


@router.get("/{token}/me/cards/swaps/find")
async def find_swap_cards(token: str, q: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Search every card in the club for who holds a copy that could be swapped."""
    club, player, snap = await _ready(db, request, token)
    rate_limit.enforce(f"cards-find:{player.id}:{_client_ip(request)}", SWAP_LIMIT, SWAP_WINDOW,
                       detail="Slow down. Give it a few seconds and try again.")
    try:
        return await swaps.find_cards(db, club, snap, str(player.id), q[:80])
    except swaps.SwapError as exc:
        raise _refuse(exc)


@router.get("/{token}/me/cards/swaps/players/{player_id}")
async def get_swap_player(token: str, player_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """The cards one other player could offer, and nothing else of their collection."""
    club, player, snap = await _ready(db, request, token)
    if player_id == str(player.id) or player_id not in snap["people"]:
        raise HTTPException(status_code=404, detail="That player is not available to swap with.")
    return {
        "player": {"player_id": player_id, "name": snap["people"][player_id]["display_name"]},
        "cards": await swaps.tradeable_cards(db, club, snap, player_id),
    }


@router.post("/{token}/me/cards/swaps")
async def ask_for_swap(token: str, body: SwapBody, request: Request, db: AsyncSession = Depends(get_db)):
    club, player, snap = await _ready(db, request, token)
    rate_limit.enforce(f"cards-swap:{player.id}:{_client_ip(request)}", SWAP_LIMIT, SWAP_WINDOW,
                       detail="Slow down. Give it a few seconds and try again.")
    try:
        give = [c.model_dump() for c in body.give] if body.give is not None else ([{"key": body.give_key}] if body.give_key else [])
        want = [c.model_dump() for c in body.want] if body.want is not None else ([{"key": body.want_key}] if body.want_key else [])
        new_id = await swaps.create_swap(db, club, snap, str(player.id), body.to_player_id, give, want)
    except swaps.SwapError as exc:
        await db.rollback()
        raise _refuse(exc)
    await db.commit()
    return {"id": new_id, "status": "pending"}


@router.post("/{token}/me/cards/swaps/{swap_id}/{action}")
async def answer_swap(token: str, swap_id: str, action: str, request: Request, db: AsyncSession = Depends(get_db)):
    """accept (the person asked), decline (the person asked) or cancel (the person who asked)."""
    club, player, snap = await _ready(db, request, token)
    rate_limit.enforce(f"cards-swap:{player.id}:{_client_ip(request)}", SWAP_LIMIT, SWAP_WINDOW,
                       detail="Slow down. Give it a few seconds and try again.")
    try:
        status = await swaps.respond(db, club, snap, str(player.id), swap_id, action)
    except swaps.SwapError as exc:
        await db.rollback()
        raise _refuse(exc)
    await db.commit()
    return {"status": status}
