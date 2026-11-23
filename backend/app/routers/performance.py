"""Performance Tracker (Association Socials): a round across every competition an
association follows, read from one pasted match link per competition.

Routes, all under the association workspace the caller is acting in:

  GET    /admin/performance/pull?q=<link>       one competition's round (services/performance_round)
  GET    /admin/performance/rounds              tracked rounds, newest first
  POST   /admin/performance/rounds              a new round (carries the last one's competitions)
  GET    /admin/performance/rounds/{id}         one round
  PATCH  /admin/performance/rounds/{id}         save; an absent key is left alone
  POST   /admin/performance/rounds/{id}/archive
  GET    /admin/performance/rounds/{id}/season  leaderboards and milestones (services/performance_season)

Only an association socials workspace has a tracker (services/social_competition
.is_association); a club gets 404. Every read and write is scoped by
``organisation_id = club.id``. A round is archived, never deleted: it holds what
people typed.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_SOCIAL, require_cap
from app.auth.modules import require_module
from app.models.db import get_db
from app.routers.auth import get_current_club, get_current_user

log = logging.getLogger(__name__)


async def require_association(club=Depends(get_current_club)):
    """The tracker lives in an association socials workspace only."""
    from app.services.social_competition import is_association
    if not is_association(club):
        raise HTTPException(404, "The Performance Tracker is part of Association Socials.")
    return club


router = APIRouter(
    prefix="/admin/performance",
    tags=["performance"],
    dependencies=[
        Depends(require_cap(MANAGE_SOCIAL)), Depends(require_module("socials")), Depends(require_association),
    ],
)

# Three competitions' pulls are well under this; the cap only stops a runaway
# client filling a row.
MAX_DATA_BYTES = 2_000_000


def _row(r) -> dict:
    return {
        "id": str(r.id),
        "round_label": r.round_label or "",
        "round_date": r.round_date.isoformat() if r.round_date else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _data(r) -> dict:
    return r.data if isinstance(r.data, dict) else json.loads(r.data or "{}")


async def _load(db: AsyncSession, club_id, round_id: str):
    try:
        uuid.UUID(round_id)
    except ValueError:
        raise HTTPException(404, "Round not found")
    r = (await db.execute(text(
        "SELECT * FROM performance_rounds WHERE id = CAST(:id AS uuid) "
        "AND organisation_id = CAST(:org AS uuid) AND archived_at IS NULL"
    ), {"id": round_id, "org": str(club_id)})).first()
    if r is None:
        raise HTTPException(404, "Round not found")
    return r


def _full(r) -> dict:
    return {**_row(r), "data": _data(r)}


@router.get("/pull")
async def pull(q: str = "", db: AsyncSession = Depends(get_db), club=Depends(get_current_club)):
    """One competition's round from a pasted match link. Read only."""
    from app.services.performance_round import pull_competition
    if not q.strip():
        return {"kind": "invalid", "message": "Paste a play.cricket.com.au match link from the round."}
    try:
        return await pull_competition(db, club, q)
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("performance pull failed for %s", getattr(club, "id", "?"))
        raise HTTPException(500, f"Could not read that round: {exc}") from exc


@router.get("/rounds")
async def list_rounds(db: AsyncSession = Depends(get_db), club=Depends(get_current_club)):
    rows = (await db.execute(text(
        "SELECT id, round_label, round_date, created_at, updated_at "
        "FROM performance_rounds WHERE organisation_id = CAST(:org AS uuid) AND archived_at IS NULL "
        "ORDER BY created_at DESC"
    ), {"org": str(club.id)})).all()
    return {"rounds": [_row(r) for r in rows]}


@router.post("/rounds")
async def create_round(db: AsyncSession = Depends(get_db), club=Depends(get_current_club),
                       user=Depends(get_current_user)):
    """A new round, carrying the last round's competitions (each name and link,
    never its figures) so next week is a paste and a Pull away."""
    last = (await db.execute(text(
        "SELECT data FROM performance_rounds WHERE organisation_id = CAST(:org AS uuid) "
        "AND archived_at IS NULL ORDER BY created_at DESC LIMIT 1"
    ), {"org": str(club.id)})).first()
    data: dict = {}
    if last is not None:
        prev = _data(last)
        if isinstance(prev.get("competitions"), list):
            data["competitions"] = [
                {"key": c.get("key"), "name": c.get("name"), "link": c.get("link") or ""}
                for c in prev["competitions"] if isinstance(c, dict)
            ]
    rid = str(uuid.uuid4())
    await db.execute(text(
        "INSERT INTO performance_rounds (id, organisation_id, data, updated_by) "
        "VALUES (CAST(:id AS uuid), CAST(:org AS uuid), CAST(:data AS jsonb), CAST(:by AS uuid))"
    ), {"id": rid, "org": str(club.id), "data": json.dumps(data), "by": str(user.id)})
    await db.commit()
    return _full(await _load(db, club.id, rid))


@router.get("/rounds/{round_id}")
async def get_round(round_id: str, db: AsyncSession = Depends(get_db), club=Depends(get_current_club)):
    return _full(await _load(db, club.id, round_id))


class RoundPatch(BaseModel):
    round_label: str | None = None
    round_date: date | None = None
    data: dict | None = None


@router.patch("/rounds/{round_id}")
async def save_round(round_id: str, body: RoundPatch, db: AsyncSession = Depends(get_db),
                     club=Depends(get_current_club), user=Depends(get_current_user)):
    """Save what was sent. A key that is absent is left alone; an explicit null
    clears it (``data`` cannot be cleared, only replaced)."""
    await _load(db, club.id, round_id)
    sent = body.model_fields_set
    sets, params = [], {"id": round_id, "org": str(club.id), "by": str(user.id)}
    if "round_label" in sent:
        sets.append("round_label = :rl")
        params["rl"] = (body.round_label or "").strip()[:200] or None
    if "round_date" in sent:
        sets.append("round_date = :rd")
        params["rd"] = body.round_date
    if "data" in sent and body.data is not None:
        blob = json.dumps(body.data)
        if len(blob.encode()) > MAX_DATA_BYTES:
            raise HTTPException(413, "That round is too large to save.")
        sets.append("data = CAST(:data AS jsonb)")
        params["data"] = blob
    if sets:
        await db.execute(text(
            f"UPDATE performance_rounds SET {', '.join(sets)}, updated_at = NOW(), "
            "updated_by = CAST(:by AS uuid) "
            "WHERE id = CAST(:id AS uuid) AND organisation_id = CAST(:org AS uuid)"
        ), params)
        await db.commit()
    return _full(await _load(db, club.id, round_id))


@router.get("/rounds/{round_id}/season")
async def round_season(round_id: str, db: AsyncSession = Depends(get_db), club=Depends(get_current_club)):
    """Season leaderboards (each competition, and all of them together), and the
    season and career milestones crossed this round. Reads Cricket Australia's
    published totals; a club's career totals are read in the background the
    first time, so ``career.pending`` names clubs still being read."""
    from app.services.performance_season import round_season as build
    r = await _load(db, club.id, round_id)
    try:
        return await build(db, _data(r))
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("performance season failed for %s", round_id)
        raise HTTPException(500, f"Could not read the season: {exc}") from exc


@router.post("/rounds/{round_id}/archive")
async def archive_round(round_id: str, db: AsyncSession = Depends(get_db), club=Depends(get_current_club)):
    await _load(db, club.id, round_id)
    await db.execute(text(
        "UPDATE performance_rounds SET archived_at = NOW() "
        "WHERE id = CAST(:id AS uuid) AND organisation_id = CAST(:org AS uuid)"
    ), {"id": round_id, "org": str(club.id)})
    await db.commit()
    return {"ok": True}
