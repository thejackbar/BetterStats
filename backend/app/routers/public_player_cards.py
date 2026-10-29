"""Player Cards on the player's own page (public, behind the same PIN cookie as the page).

A player sees their own collection and opens their own packs. Nothing here takes a player id:
the verified cookie names the player, so one player cannot open another's packs or read their
collection. The cards themselves carry only what the club already shows publicly (a name, a
photo and career figures); nothing about contact details, fees or availability.

Unauthenticated routers are not under `require_module` (the caller has no session): the club comes
from the link token and `_club_for_token(need_dashboard=True)` decides if the link works, so a
club without BetterSelect still has cards, and a club whose Player Dashboard is off has none.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import get_db
from app.routers.public_availability import _club_branding, _club_for_token, _client_ip, _player_for_session
from app.services import player_card_alerts as alerts, player_card_catalogue as catalogue, player_card_community as community, player_card_designs as pack_designs, player_card_sets as card_sets, player_card_social as social, player_card_swaps as swaps, player_cards as cards, rate_limit
from app.services.session_safety import rollback_keeping

router = APIRouter(prefix="/public/availability", tags=["public-player-cards"])

logger = logging.getLogger(__name__)

OPEN_LIMIT = 40
OPEN_WINDOW = 60


async def _ready(db: AsyncSession, request: Request, token: str):
    """(club, player, snapshot) for a verified player of a club with cards on, else 404 / 401."""
    club = await _club_for_token(db, token, need_select=False, need_dashboard=True)
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
        # Every design the club made, by target, for the "how packs arrive" screen (each pack also carries its own).
        "pack_designs": await pack_designs.load_all(db, club.id),
        "pack_size": cards.PACK_SIZE,
        "season": snap["season_label"],
        "features": _features(snap),
        **collection,
    }


FEATURES = ("sets", "showcase", "board", "feed")


def _features(snap: dict) -> dict:
    """Which of the club's optional parts are switched on (all are, until a club switches one off)."""
    return {k: snap["settings"].get(f"{k}_enabled", True) is not False for k in FEATURES}


def _need(snap: dict, feature: str) -> None:
    if not _features(snap)[feature]:
        raise HTTPException(status_code=404, detail="That is not switched on for your club.")


@router.post("/{token}/me/cards/packs/{pack_id}/open")
async def open_my_pack(token: str, pack_id: str, request: Request, db: AsyncSession = Depends(get_db), background_tasks: BackgroundTasks = None):
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
    if background_tasks is not None:   # a wish list may now have a card someone could swap
        background_tasks.add_task(alerts.scan_wants, club.id, [c["key"] for c in got if c.get("key")])
    packs = await cards.available_packs(db, str(player.id), snap)
    return {"cards": got, "packs_left": len(packs)}


@router.post("/{token}/me/cards/open-all")
async def open_all_my_packs(token: str, request: Request, db: AsyncSession = Depends(get_db), background_tasks: BackgroundTasks = None):
    """Open every pack that is ready, up to a sensible number, and report what came out."""
    club, player, snap = await _ready(db, request, token)
    rate_limit.enforce(f"cards-open-all:{player.id}:{_client_ip(request)}", 6, OPEN_WINDOW,
                       detail="Slow down. Give it a few seconds and try again.")
    result = await cards.open_many(db, club, player, snap)
    await db.commit()
    if background_tasks is not None:
        background_tasks.add_task(alerts.scan_wants, club.id, None)
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
    note: Optional[str] = None


class CounterBody(BaseModel):
    give: list[SwapCard]
    want: list[SwapCard]
    note: Optional[str] = None


def _refuse(exc: swaps.SwapError):
    return HTTPException(status_code=exc.status, detail=exc.message)


@router.get("/{token}/me/cards/swaps")
async def get_my_swaps(token: str, request: Request, db: AsyncSession = Depends(get_db), history: bool = False):
    """Swap requests in and out, the cards the player could offer, and who has cards to offer."""
    club, player, snap = await _ready(db, request, token)
    me = str(player.id)
    return {
        **await swaps.list_swaps(db, club, snap, me, history=history),
        "mine": await swaps.tradeable_cards(db, club, snap, me),
        "people": await swaps.swap_people(db, club, snap, me),
        "expires_days": swaps.SWAP_DAYS,
        "max_open": swaps.MAX_OUTGOING,
    }


@router.get("/{token}/me/cards/catalogue")
async def get_catalogue(token: str, request: Request, filter: str = "all", sort: str = "rarity", q: str = "", offset: int = 0, limit: int = 12, have: str = "all",
                        set: str = "", db: AsyncSession = Depends(get_db)):
    """The club's whole set, a window at a time, laid out like the player's own book (players, then special cards in
    stacks). Nothing needs to be held, and nothing about anyone's collection is shown beyond whether a copy could be swapped."""
    club, player, snap = await _ready(db, request, token)
    rate_limit.enforce(f"cards-catalogue:{player.id}:{_client_ip(request)}", SWAP_LIMIT * 2, SWAP_WINDOW,
                       detail="Slow down. Give it a few seconds and try again.")
    if sort not in catalogue.SORTS:
        sort = "rarity"
    return await catalogue.page(db, club, snap, str(player.id), filter=filter[:20], sort=sort, q=q[:80], offset=offset, limit=limit, have=have[:12], set_key=(set[:60] or None))


@router.get("/{token}/me/cards/catalogue/holders")
async def get_catalogue_holders(token: str, key: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Who could swap a copy of one card."""
    club, player, snap = await _ready(db, request, token)
    try:
        return await catalogue.holders_of(db, club, snap, str(player.id), key[:60])
    except swaps.SwapError as exc:
        raise _refuse(exc)


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
async def ask_for_swap(token: str, body: SwapBody, request: Request, db: AsyncSession = Depends(get_db), background_tasks: BackgroundTasks = None):
    club, player, snap = await _ready(db, request, token)
    rate_limit.enforce(f"cards-swap:{player.id}:{_client_ip(request)}", SWAP_LIMIT, SWAP_WINDOW,
                       detail="Slow down. Give it a few seconds and try again.")
    try:
        give = [c.model_dump() for c in body.give] if body.give is not None else ([{"key": body.give_key}] if body.give_key else [])
        want = [c.model_dump() for c in body.want] if body.want is not None else ([{"key": body.want_key}] if body.want_key else [])
        new_id = await swaps.create_swap(db, club, snap, str(player.id), body.to_player_id, give, want, note=body.note)
    except swaps.SwapError as exc:
        await db.rollback()
        raise _refuse(exc)
    await db.commit()
    if background_tasks is not None:
        background_tasks.add_task(alerts.swap_asked, club.id, new_id)
    return {"id": new_id, "status": "pending"}


@router.post("/{token}/me/cards/swaps/{swap_id}/counter")
async def counter_swap(token: str, swap_id: str, body: CounterBody, request: Request, db: AsyncSession = Depends(get_db), background_tasks: BackgroundTasks = None):
    """Answer a request with a changed one: a new request back to the person who asked, and the old one ends as countered."""
    club, player, snap = await _ready(db, request, token)
    rate_limit.enforce(f"cards-swap:{player.id}:{_client_ip(request)}", SWAP_LIMIT, SWAP_WINDOW,
                       detail="Slow down. Give it a few seconds and try again.")
    try:
        new_id = await swaps.counter_swap(db, club, snap, str(player.id), swap_id, [c.model_dump() for c in body.give],
                                          [c.model_dump() for c in body.want], note=body.note)
    except swaps.SwapError as exc:
        await db.rollback()
        raise _refuse(exc)
    await db.commit()
    if background_tasks is not None:
        background_tasks.add_task(alerts.swap_asked, club.id, new_id)
    return {"id": new_id, "status": "pending"}


@router.post("/{token}/me/cards/swaps/{swap_id}/{action}")
async def answer_swap(token: str, swap_id: str, action: str, request: Request, db: AsyncSession = Depends(get_db), background_tasks: BackgroundTasks = None):
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
    if status == "accepted" and background_tasks is not None:   # the cards moved: someone's wish may now be met, or lost
        sides = (await swaps._items_of(db, [swap_id]))[swap_id]
        background_tasks.add_task(alerts.scan_wants, club.id, [swaps.key_of(*c) for side in sides.values() for c, _ in side])
    return {"status": status}


# ── Wish list, spares, one card, alert settings ───────────────────────────────────────────────────────────────

class KeyBody(BaseModel):
    key: str


class OpenBody(BaseModel):
    key: str
    open: bool


class PrefsBody(BaseModel):
    alert_swaps: Optional[bool] = None
    alert_wants: Optional[bool] = None
    board_hidden: Optional[bool] = None
    feed_hidden: Optional[bool] = None


class ShowcaseBody(BaseModel):
    keys: list[str]


@router.get("/{token}/me/cards/wants")
async def get_wants(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    """The player's wish list, each card with who could swap one now."""
    club, player, snap = await _ready(db, request, token)
    return await social.list_wants(db, club, snap, str(player.id))


@router.post("/{token}/me/cards/wants")
async def add_want(token: str, body: KeyBody, request: Request, db: AsyncSession = Depends(get_db)):
    club, player, snap = await _ready(db, request, token)
    rate_limit.enforce(f"cards-want:{player.id}:{_client_ip(request)}", SWAP_LIMIT * 2, SWAP_WINDOW,
                       detail="Slow down. Give it a few seconds and try again.")
    try:
        await social.add_want(db, club, snap, str(player.id), body.key)
    except swaps.SwapError as exc:
        await db.rollback()
        raise _refuse(exc)
    await db.commit()
    return {"ok": True}


@router.delete("/{token}/me/cards/wants")
async def remove_want(token: str, key: str, request: Request, db: AsyncSession = Depends(get_db)):
    club, player, snap = await _ready(db, request, token)
    try:
        await social.remove_want(db, club, str(player.id), key)
    except swaps.SwapError as exc:
        await db.rollback()
        raise _refuse(exc)
    await db.commit()
    return {"ok": True}


@router.get("/{token}/me/cards/spares")
async def get_spares(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    """The cards the player holds more of than they keep, and whether they are open to offers on each."""
    club, player, snap = await _ready(db, request, token)
    return await social.spares(db, club, snap, str(player.id))


@router.post("/{token}/me/cards/spares/open")
async def set_spare_open(token: str, body: OpenBody, request: Request, db: AsyncSession = Depends(get_db)):
    club, player, snap = await _ready(db, request, token)
    try:
        await social.set_open(db, club, snap, str(player.id), body.key, body.open)
    except swaps.SwapError as exc:
        await db.rollback()
        raise _refuse(exc)
    await db.commit()
    return {"ok": True}


@router.get("/{token}/me/cards/card")
async def get_card(token: str, key: str, request: Request, db: AsyncSession = Depends(get_db)):
    """One card in full: the card, who could swap one, how many the asker holds, whether it is on their wish list."""
    club, player, snap = await _ready(db, request, token)
    try:
        return await social.card_detail(db, club, snap, str(player.id), key[:60])
    except swaps.SwapError as exc:
        raise _refuse(exc)


@router.get("/{token}/me/cards/prefs")
async def get_prefs(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    club, player, snap = await _ready(db, request, token)
    return {**await social.load_prefs(db, str(player.id)), "club_alerts": snap["settings"].get("alerts_enabled", True) is not False,
            "email_on_file": bool((getattr(player, "email", None) or "").strip()), "features": _features(snap)}


@router.put("/{token}/me/cards/prefs")
async def put_prefs(token: str, body: PrefsBody, request: Request, db: AsyncSession = Depends(get_db)):
    """Only the settings sent are changed."""
    club, player, snap = await _ready(db, request, token)
    patch = {k: getattr(body, k) for k in body.model_fields_set}
    out = await social.save_prefs(db, club, str(player.id), patch)
    await db.commit()
    return {**out, "club_alerts": snap["settings"].get("alerts_enabled", True) is not False,
            "email_on_file": bool((getattr(player, "email", None) or "").strip()), "features": _features(snap)}


# ── Sets, showcase, the collectors board and the club feed ───────────────────────────────────────────────────

@router.get("/{token}/me/cards/sets")
async def get_sets(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Every set the club has, with how far through each the player is."""
    club, player, snap = await _ready(db, request, token)
    _need(snap, "sets")
    return await card_sets.overview(db, club, snap, str(player.id))


@router.get("/{token}/me/cards/sets/{set_key}")
async def get_set(token: str, set_key: str, request: Request, db: AsyncSession = Depends(get_db)):
    """One set's heading and progress. Its cards are read through the catalogue with `set=`."""
    club, player, snap = await _ready(db, request, token)
    _need(snap, "sets")
    found = await card_sets.members(db, club, snap, set_key[:60])
    if not found:
        raise HTTPException(status_code=404, detail="That set could not be found.")
    mine = await card_sets.held_keys(db, club, str(player.id))
    keys = {f"p:{p}" for p in found[0]} | {f"s:{x}" for x in found[1]}
    return {**found[2], "total": len(keys), "owned": len(keys & mine), "complete": len(keys & mine) >= len(keys)}


@router.get("/{token}/me/cards/showcase")
async def get_showcase(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    club, player, snap = await _ready(db, request, token)
    _need(snap, "showcase")
    return await community.get_showcase(db, club, snap, str(player.id))


@router.put("/{token}/me/cards/showcase")
async def put_showcase(token: str, body: ShowcaseBody, request: Request, db: AsyncSession = Depends(get_db)):
    """Replace the showcase: up to six cards the player holds, in order."""
    club, player, snap = await _ready(db, request, token)
    _need(snap, "showcase")
    try:
        await community.set_showcase(db, club, snap, str(player.id), body.keys)
    except swaps.SwapError as exc:
        await db.rollback()
        raise _refuse(exc)
    await db.commit()
    return await community.get_showcase(db, club, snap, str(player.id))


@router.get("/{token}/me/cards/board")
async def get_board(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    """The collectors board: every player in the pool who has not left it, by share of the set held."""
    club, player, snap = await _ready(db, request, token)
    _need(snap, "board")
    return await community.board(db, club, snap, str(player.id))


@router.get("/{token}/me/cards/feed")
async def get_feed(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    """What has happened in the club's cards this week."""
    club, player, snap = await _ready(db, request, token)
    _need(snap, "feed")
    return await community.feed(db, club, snap, str(player.id))
