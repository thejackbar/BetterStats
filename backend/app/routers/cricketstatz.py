"""Import a club's history from its own public CricketStatz site.

A club that keeps its records in CricketStatz pastes the address of its own
club page; this walks every season, every match and every scorecard behind it,
plus the record book CricketStatz has already computed, and writes it into the
manual-game tables so it reaches every existing read path.

    POST /inspect          — what that address holds, before anything is written
    POST /import           — start the pull (a background task; the screen polls)
    GET  /status           — the running or most recent import
    GET  /imports          — past imports
    POST /imports/{id}/undo— remove everything one import wrote
    GET  /records          — the imported record book

Gated by MANAGE_MANUAL_ENTRIES, the same core onboarding capability the
historical CSV importer and the scorecard uploader use — bringing a club's own
history in is onboarding, not a paid add-on.

This is a data-portability path a club runs against its OWN records: one club
at a time, on demand, at the club's instruction. The client keeps a low
concurrency ceiling and identifies itself.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_MANUAL_ENTRIES, require_cap
from app.models.db import Organisation, User, get_db
from app.routers.auth import get_current_club, get_current_user
from app.services import cricketstatz_import as importer
from app.services.cricketstatz_client import CricketStatzUnavailable
from app.services.cricketstatz_parse import CricketStatzError, parse_club_url

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/club-admin/cricketstatz",
    tags=["cricketstatz"],
    dependencies=[Depends(require_cap(MANAGE_MANUAL_ENTRIES))],
)


# Detached import tasks, held so they are not garbage-collected mid-run.
_RUNNING: dict[str, asyncio.Task] = {}


class ClubUrl(BaseModel):
    url: str


def _handle(exc: Exception) -> HTTPException:
    if isinstance(exc, CricketStatzError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, CricketStatzUnavailable):
        return HTTPException(status_code=503, detail=str(exc))
    logger.exception("CricketStatz request failed")
    return HTTPException(status_code=500, detail="Could not read that CricketStatz site.")


@router.post("/inspect")
async def inspect(body: ClubUrl, club: Organisation = Depends(get_current_club)):
    """What the club's CricketStatz site holds — shown before anything runs."""
    try:
        return await importer.inspect_club(body.url)
    except Exception as exc:
        raise _handle(exc)


@router.post("/import")
async def start_import(
    body: ClubUrl,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(get_current_user),
):
    """Start the full pull. Returns immediately; the screen polls /status."""
    club_id = parse_club_url(body.url)
    if not club_id:
        raise HTTPException(
            status_code=422,
            detail="Paste the link to your club's CricketStatz stats page.",
        )

    running = (await db.execute(text("""
        SELECT id FROM cricketstatz_imports
         WHERE organisation_id = :org AND status = 'running'
         ORDER BY started_at DESC LIMIT 1
    """), {"org": str(club.id)})).first()
    if running:
        raise HTTPException(
            status_code=409,
            detail="An import is already running for this club.",
        )

    import_id = uuid.uuid4()
    await db.execute(text("""
        INSERT INTO cricketstatz_imports
            (id, organisation_id, club_id, source_url, status, phase,
             created_by_user_id)
        VALUES (:id, :org, :club, :url, 'running', 'starting', :user)
    """), {
        "id": str(import_id), "org": str(club.id), "club": club_id,
        "url": body.url, "user": str(user.id) if user else None,
    })
    await db.commit()

    from app.models.db import async_session_maker

    # Detached, and held so it is not garbage-collected mid-run — the same
    # pattern the opposition-dossier builder uses.
    task = asyncio.create_task(
        importer.run_import(async_session_maker, club.id, import_id, club_id))
    _RUNNING[str(import_id)] = task
    task.add_done_callback(lambda _t: _RUNNING.pop(str(import_id), None))

    return {"import_id": str(import_id), "status": "running"}


@router.get("/status")
async def status(db: AsyncSession = Depends(get_db),
                 club: Organisation = Depends(get_current_club)):
    """The running import, or the most recent one."""
    row = (await db.execute(text("""
        SELECT id, club_id, club_name, source_url, status, phase, progress,
               stats, error, started_at, finished_at, undone_at
          FROM cricketstatz_imports
         WHERE organisation_id = :org
         ORDER BY started_at DESC LIMIT 1
    """), {"org": str(club.id)})).mappings().first()
    if not row:
        return {"import": None,
                "club_id": getattr(club, "cricketstatz_club_id", None)}
    return {"import": dict(row),
            "club_id": getattr(club, "cricketstatz_club_id", None)}


@router.get("/imports")
async def list_imports(db: AsyncSession = Depends(get_db),
                       club: Organisation = Depends(get_current_club)):
    rows = (await db.execute(text("""
        SELECT i.id, i.club_id, i.club_name, i.status, i.phase, i.stats,
               i.error, i.started_at, i.finished_at, i.undone_at,
               (SELECT COUNT(*) FROM manual_games g
                 WHERE g.cricketstatz_import_id = i.id) AS matches
          FROM cricketstatz_imports i
         WHERE i.organisation_id = :org
         ORDER BY i.started_at DESC LIMIT 25
    """), {"org": str(club.id)})).mappings().all()
    return {"imports": [dict(r) for r in rows]}


@router.post("/imports/{import_id}/undo")
async def undo(import_id: uuid.UUID,
               db: AsyncSession = Depends(get_db),
               club: Organisation = Depends(get_current_club)):
    """Remove every match and record one import wrote."""
    owned = (await db.execute(text("""
        SELECT status FROM cricketstatz_imports
         WHERE id = :id AND organisation_id = :org
    """), {"id": str(import_id), "org": str(club.id)})).first()
    if not owned:
        raise HTTPException(status_code=404, detail="No such import.")
    if owned[0] == "running":
        raise HTTPException(
            status_code=409,
            detail="That import is still running — wait for it to finish first.",
        )
    return await importer.undo_import(db, club.id, import_id)


@router.get("/records")
async def records(db: AsyncSession = Depends(get_db),
                  club: Organisation = Depends(get_current_club)):
    """The club's CricketStatz record book, as captured."""
    rows = (await db.execute(text("""
        SELECT mode, section, title, scope, headers, rows, row_count, captured_at
          FROM cricketstatz_records
         WHERE organisation_id = :org
         ORDER BY section, title
    """), {"org": str(club.id)})).mappings().all()
    return {"records": [dict(r) for r in rows]}
