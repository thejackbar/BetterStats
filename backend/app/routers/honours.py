"""Public premiership squads and office-bearer boards for a cricket club.

Both readings come out of ``player_achievements`` — the honours a club has
already recorded against its players — via services/honours.py, which the
football silo's own router reads too. Public and unauthenticated like the
rest of a club's stats pages: this is the club's honour board, which is the
one part of its history it most wants read.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
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
