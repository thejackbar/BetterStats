"""Super Admin: the daily product update.

The 9am post itself is a scheduled job (jobs/scheduler.py, services/product_blast.py).
This is the control room around it: the Stop switch, a preview of what would go out
next, the log of every attempt with what the model wrote, Run now, and Take down for a
post that should not have gone. Cross-club platform tooling, so every route is
``require_super_admin``.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import get_db
from app.routers.auth import require_super_admin
from app.services import product_blast

router = APIRouter(prefix="/club-admin/super/product-updates", tags=["product-updates"])


class ControlBody(BaseModel):
    paused: bool


@router.get("")
async def overview(db: AsyncSession = Depends(get_db), _=Depends(require_super_admin)):
    return {
        "paused": await product_blast.is_paused(db),
        "blasts": await product_blast.recent_blasts(db),
        "max_age_days": product_blast.MAX_AGE_DAYS,
    }


@router.post("/control")
async def control(body: ControlBody, db: AsyncSession = Depends(get_db),
                  _=Depends(require_super_admin)):
    return await product_blast.set_paused(db, body.paused)


@router.post("/preview")
async def preview(_=Depends(require_super_admin)):
    """What the next post would say, without posting or recording anything. Works
    while stopped, which is the point: read it, then press Start."""
    return await product_blast.run_daily(dry_run=True)


@router.post("/run")
async def run_now(_=Depends(require_super_admin)):
    """The same attempt the 9am job makes. Refuses while stopped, and a day that
    already has a post does not get a second."""
    result = await product_blast.run_daily()
    if result.get("status") == "paused":
        raise HTTPException(409, "The daily update is stopped. Start it first.")
    return result


@router.delete("/{blast_id}")
async def take_down(blast_id: str, db: AsyncSession = Depends(get_db),
                    _=Depends(require_super_admin)):
    """Mark a posted update retracted and remove the notifications it raised."""
    try:
        result = await product_blast.retract(db, blast_id)
    except Exception:
        await db.rollback()
        raise HTTPException(400, "Invalid update id")
    if result is None:
        raise HTTPException(404, "No posted update with that id")
    return result
