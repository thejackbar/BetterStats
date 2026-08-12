"""BetterScout — watchlist (Kanban board) routes. Every route requires a
signed-in Scout Org user; ownership of every watchlist/column/card id is
re-checked in services/scout_watchlist.py on every call, never trusted from
the URL alone."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import get_db
from app.models.scout import ScoutOrg, ScoutUser
from app.routers.scout.auth import get_current_scout_user
from app.services import scout_watchlist

router = APIRouter(prefix="/scout/watchlists", tags=["scout-watchlists"])


def _current_org(current: tuple[ScoutUser, ScoutOrg]) -> ScoutOrg:
    return current[1]


@router.get("")
async def list_watchlists(
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    return await scout_watchlist.list_watchlists(db, _current_org(current).id)


class CreateWatchlistRequest(BaseModel):
    name: str


@router.post("")
async def create_watchlist(
    data: CreateWatchlistRequest,
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    if not (data.name or "").strip():
        raise HTTPException(status_code=400, detail="Name is required.")
    wl = await scout_watchlist.create_watchlist(db, _current_org(current).id, data.name.strip())
    return {"id": str(wl.id), "name": wl.name}


@router.get("/{watchlist_id}/board")
async def get_board(
    watchlist_id: str,
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await scout_watchlist.get_board(db, watchlist_id, _current_org(current).id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


class CreateColumnRequest(BaseModel):
    name: str


@router.post("/{watchlist_id}/columns")
async def create_column(
    watchlist_id: str, data: CreateColumnRequest,
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    if not (data.name or "").strip():
        raise HTTPException(status_code=400, detail="Name is required.")
    try:
        return await scout_watchlist.create_column(db, watchlist_id, _current_org(current).id, data.name.strip())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


class ReorderColumnsRequest(BaseModel):
    column_ids: list[str]


@router.post("/{watchlist_id}/columns/reorder")
async def reorder_columns(
    watchlist_id: str, data: ReorderColumnsRequest,
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await scout_watchlist.reorder_columns(db, watchlist_id, _current_org(current).id, data.column_ids)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "ok"}


class RenameColumnRequest(BaseModel):
    name: str


@router.patch("/columns/{column_id}")
async def rename_column(
    column_id: str, data: RenameColumnRequest,
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    if not (data.name or "").strip():
        raise HTTPException(status_code=400, detail="Name is required.")
    try:
        return await scout_watchlist.rename_column(db, column_id, _current_org(current).id, data.name.strip())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/columns/{column_id}")
async def delete_column(
    column_id: str,
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await scout_watchlist.delete_column(db, column_id, _current_org(current).id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok"}


class MoveCardRequest(BaseModel):
    column_id: str
    position: int


@router.post("/cards/{card_id}/move")
async def move_card(
    card_id: str, data: MoveCardRequest,
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await scout_watchlist.move_card(db, card_id, _current_org(current).id, data.column_id, data.position)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


class UpdateCardRequest(BaseModel):
    tags: list[str] | None = None
    role: str | None = None
    batting_hand: str | None = None
    bowling_action: str | None = None
    bowling_type: str | None = None
    region: str | None = None
    level: str | None = None
    transfer_preference: str | None = None
    visa_status: str | None = None
    agent_contact: str | None = None
    availability_window: str | None = None
    fee_expectations: str | None = None
    notes: str | None = None


@router.patch("/cards/{card_id}")
async def update_card(
    card_id: str, data: UpdateCardRequest,
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await scout_watchlist.update_card(
            db, card_id, _current_org(current).id, **data.model_dump(exclude_unset=True)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/cards/{card_id}")
async def remove_card(
    card_id: str,
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await scout_watchlist.remove_card(db, card_id, _current_org(current).id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "ok"}


@router.post("/cards/{card_id}/share")
async def create_share_link(
    card_id: str,
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await scout_watchlist.create_share_link(db, card_id, _current_org(current).id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/cards/{card_id}/share")
async def revoke_share_link(
    card_id: str,
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await scout_watchlist.revoke_share_link(db, card_id, _current_org(current).id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "ok"}
