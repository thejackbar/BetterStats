"""Public premiership squads and office-bearer boards for a cricket club.

Both readings come out of ``player_achievements`` — the honours a club has
already recorded against its players — via services/honours.py, which the
football silo's own router reads too. Public and unauthenticated like the
rest of a club's stats pages: this is the club's honour board, which is the
one part of its history it most wants read.
"""
import uuid

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_AWARDS, require_cap
from app.models.db import Organisation, User, get_db
from app.routers.auth import get_current_club
from app.services import honour_layout, honours, premierships

router = APIRouter(prefix="/honours", tags=["honours"])


def _same_club(club: Organisation, org_id: uuid.UUID) -> None:
    """The signed-in admin may only run this for their own club."""
    if club.id != org_id:
        raise HTTPException(status_code=403, detail="Not your club")


@router.get("/{org_id}/premierships")
async def get_premierships(org_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Every flag as the squad that won it. A card built from a grand final the
    club's scorecards hold carries ``game`` (date, opponent) and ``game_id`` so the
    page can link to the scorecard; a hand-typed flag with no match to a game has
    ``game_id: null``."""
    links = await premierships.achievement_game_links(db, org_id)
    data = await honours.premiership_squads(db, org_id, game_links=links)
    club = (await db.execute(select(Organisation).where(Organisation.id == org_id))).scalar_one_or_none()
    ids = sorted({p["game_id"] for p in data["premierships"] if p.get("game_id")})
    cards = await premierships.game_cards(db, club, ids) if club else {}
    for p in data["premierships"]:
        p["game"] = cards.get(p.get("game_id"))
    return data


@router.get("/games/{game_id}/premierships")
async def get_game_premierships(game_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """The clubs that recorded a premiership off this scorecard (empty for any other
    game). Public, like the scorecard itself; the scorecard page reads it for its banner."""
    return {"premierships": await premierships.game_premiership_info(db, game_id)}


@router.get("/{org_id}/premierships/auto")
async def preview_auto_premierships(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_cap(MANAGE_AWARDS)),
    club: Organisation = Depends(get_current_club),
):
    """What the automatic premierships would add, change or remove. Reads only."""
    _same_club(club, org_id)
    return await premierships.reconcile(db, org_id, apply=False)


@router.post("/{org_id}/premierships/auto")
async def apply_auto_premierships(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_cap(MANAGE_AWARDS)),
    club: Organisation = Depends(get_current_club),
):
    """Write them now (the sync also does this after every run)."""
    _same_club(club, org_id)
    return await premierships.reconcile(db, org_id, apply=True)


@router.get("/{org_id}/premierships/tags")
async def list_match_tags(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_cap(MANAGE_AWARDS)),
    club: Organisation = Depends(get_current_club),
):
    """The matches the club tagged as a normal game, a final or the grand final, and what each gives."""
    _same_club(club, org_id)
    return {"tags": await premierships.tagged_matches(db, club)}


@router.get("/{org_id}/premierships/tags/{game_id}")
async def get_match_tag(
    org_id: uuid.UUID,
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_cap(MANAGE_AWARDS)),
    club: Organisation = Depends(get_current_club),
):
    """How the club tagged one match, for the match page's Premiers tick. 404 for another club's match."""
    _same_club(club, org_id)
    if await premierships._club_game(db, club, game_id) is None:
        raise HTTPException(status_code=404, detail="That match is not one of this club's.")
    return await premierships.tag_state(db, club, game_id)


class MatchTagIn(BaseModel):
    # A play.cricket.com.au match link or its match ID (a game id from the match page works too).
    match: str
    # None takes the tag off.
    kind: Optional[Literal["normal", "final", "grand_final"]] = None
    won: bool = False


def _game_id_from(ref: str) -> uuid.UUID:
    from app.services.social_match_lookup import parse_reference
    parsed = parse_reference(ref)
    if parsed and parsed.get("match_id"):
        return uuid.UUID(parsed["match_id"])
    if parsed and parsed.get("playhq_code"):
        raise HTTPException(status_code=422, detail=(
            "That's a playhq.com link, which uses a different match ID. Find the same match on "
            "play.cricket.com.au and paste that link instead."))
    raise HTTPException(status_code=422, detail="Paste a match link from play.cricket.com.au, or its match ID.")


@router.put("/{org_id}/premierships/tags")
async def put_match_tag(
    org_id: uuid.UUID,
    body: MatchTagIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_cap(MANAGE_AWARDS)),
    club: Organisation = Depends(get_current_club),
):
    """Tag a match as a normal game, a final or the grand final, from a pasted match link or ID. A grand
    final the club won gives every player on the team sheet the flag, linked to the match, at once."""
    _same_club(club, org_id)
    gid = _game_id_from(body.match)
    try:
        return await premierships.set_tag(db, club, gid, body.kind, body.won, user)
    except premierships.MarkError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{org_id}/office-bearers")
async def get_office_bearers(org_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    # The club's own order, where it has saved one. A club that has not gets the
    # standard order, so this read changes nothing for it.
    stored = (await db.execute(
        select(Organisation.honour_board_layout).where(Organisation.id == org_id)
    )).scalar_one_or_none()
    return await honours.office_bearer_boards(
        db, org_id, include_life_members=True,
        layout=honour_layout.clean_layout(stored))


class SquadEdit(BaseModel):
    game_id: uuid.UUID
    action: Literal["role", "add", "remove"]
    player_id: uuid.UUID
    role: Optional[str] = None
    on: bool = True


@router.post("/{org_id}/premierships/squad")
async def edit_premiership_squad(
    org_id: uuid.UUID,
    body: SquadEdit,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_cap(MANAGE_AWARDS)),
    club: Organisation = Depends(get_current_club),
):
    """Mark Player of the Match / 12th Man / 13th Man on a premiership card, add a player the sheet missed,
    or take one off. Only for a card linked to a scorecard (a grand final the club won). 12th Man and
    13th Man also take the match off the player's games played (`games_played` in the reply says so)."""
    _same_club(club, org_id)
    try:
        out = await premierships.edit_squad(
            db, club, game_id=body.game_id, action=body.action, player_id=body.player_id,
            role=body.role, on=body.on, user_id=user.id)
    except premierships.SquadEditError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if (out.get("games_played") or {}).get("changed"):
        from app.routers.manual_entries import _recompute_milestones
        await _recompute_milestones(db, club.id, [body.player_id])
    return out
