"""Public premiership squads and office-bearer boards for a football club.

A thin twin of cricket's routers/honours.py: both read the SAME
services/honours.py, because ``player_achievements`` carries no sport-specific
column and the two categories this reads use one vocabulary across both codes.
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import get_db
from app.services import honours

router = APIRouter(prefix="/afl-honours", tags=["afl-honours"])


@router.get("/{org_id}/premierships")
async def get_premierships(org_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await honours.premiership_squads(db, org_id)


@router.get("/{org_id}/office-bearers")
async def get_office_bearers(org_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await honours.office_bearer_boards(db, org_id)
