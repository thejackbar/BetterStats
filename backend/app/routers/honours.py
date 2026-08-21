"""Public premiership squads and office-bearer boards for a cricket club.

Both readings come out of ``player_achievements`` — the honours a club has
already recorded against its players — via services/honours.py, which the
football silo's own router reads too. Public and unauthenticated like the
rest of a club's stats pages: this is the club's honour board, which is the
one part of its history it most wants read.
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import get_db
from app.services import honours

router = APIRouter(prefix="/honours", tags=["honours"])


@router.get("/{org_id}/premierships")
async def get_premierships(org_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await honours.premiership_squads(db, org_id)


@router.get("/{org_id}/office-bearers")
async def get_office_bearers(org_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await honours.office_bearer_boards(db, org_id)
