"""Super Admin: the daily product update.

The 9am post itself is a scheduled job (jobs/scheduler.py, services/product_blast.py).
This is the control room around it: the Stop switch, a preview of what would go out
next, the log of every attempt with what the model wrote, Run now, and Take down for a
post that should not have gone. Cross-club platform tooling, so every route is
``require_super_admin``.
"""
from __future__ import annotations

import asyncio

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
        "backfill": {**product_blast.BACKFILL_STATE,
                     "stored": await product_blast.backfill_summary(db)},
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


# A reference to the running task, so it is not collected part way through.
_backfill_task: "asyncio.Task | None" = None


@router.post("/backfill")
async def backfill(_=Depends(require_super_admin)):
    """Write a note for every past day in the release history. Sends nothing to
    anybody; the notes appear on What's New. Runs in the background (it makes one
    model call per day), so poll the overview for progress."""
    global _backfill_task
    if product_blast.BACKFILL_STATE.get("running"):
        raise HTTPException(409, "A backfill is already running.")
    _backfill_task = asyncio.create_task(product_blast.backfill_history())
    return {"started": True}
