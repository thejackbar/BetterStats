"""Podcast run sheet (BetterSocials): plan a round-review episode from match links.

Routes, all under the club (or association workspace) the caller is acting in:

  GET    /admin/podcast/pull?q=<link>        one competition's round (services/podcast_round)
  GET    /admin/podcast/episodes             the episode list, newest first
  POST   /admin/podcast/episodes             a new episode (carries the last one's set-up)
  GET    /admin/podcast/episodes/{id}        one episode
  PATCH  /admin/podcast/episodes/{id}        save; an absent key is left alone
  POST   /admin/podcast/episodes/{id}/archive

Only an association socials workspace has a run sheet (services/social_competition
.is_association); a club gets 404. Every episode read and write is scoped by
``organisation_id = club.id``. An
episode is archived, never deleted: it holds what the hosts typed.
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
    """The run sheet lives in an association socials workspace only."""
    from app.services.social_competition import is_association
    if not is_association(club):
        raise HTTPException(404, "The podcast run sheet is part of Association Socials.")
    return club


router = APIRouter(
    prefix="/admin/podcast",
    tags=["podcast"],
    dependencies=[
        Depends(require_cap(MANAGE_SOCIAL)), Depends(require_module("socials")), Depends(require_association),
    ],
)

# A run sheet with three competitions' pulls is well under this; the cap only
# stops a runaway client filling a row.
MAX_DATA_BYTES = 2_000_000

# What a new episode carries over from the one before it: the set-up, never the
# round's figures or notes.
CARRY_KEYS = ("competitions", "hosts", "durations", "target_minutes")


def _row(r) -> dict:
    return {
        "id": str(r.id),
        "episode_no": r.episode_no,
        "recording_date": r.recording_date.isoformat() if r.recording_date else None,
        "round_label": r.round_label or "",
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


async def _load(db: AsyncSession, club_id, episode_id: str):
    try:
        uuid.UUID(episode_id)
    except ValueError:
        raise HTTPException(404, "Episode not found")
    r = (await db.execute(text(
        "SELECT * FROM podcast_episodes WHERE id = CAST(:id AS uuid) "
        "AND organisation_id = CAST(:org AS uuid) AND archived_at IS NULL"
    ), {"id": episode_id, "org": str(club_id)})).first()
    if r is None:
        raise HTTPException(404, "Episode not found")
    return r


def _full(r) -> dict:
    data = r.data if isinstance(r.data, dict) else json.loads(r.data or "{}")
    return {**_row(r), "data": data}


@router.get("/pull")
async def pull(q: str = "", db: AsyncSession = Depends(get_db), club=Depends(get_current_club)):
    """One competition's round from a pasted match link. Read only."""
    from app.services.podcast_round import pull_competition
    if not q.strip():
        return {"kind": "invalid", "message": "Paste a play.cricket.com.au match link from the round."}
    try:
        return await pull_competition(db, club, q)
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("podcast pull failed for %s", getattr(club, "id", "?"))
        raise HTTPException(500, f"Could not read that round: {exc}") from exc


@router.get("/episodes")
async def list_episodes(db: AsyncSession = Depends(get_db), club=Depends(get_current_club)):
    rows = (await db.execute(text(
        "SELECT id, episode_no, recording_date, round_label, created_at, updated_at "
        "FROM podcast_episodes WHERE organisation_id = CAST(:org AS uuid) AND archived_at IS NULL "
        "ORDER BY episode_no DESC NULLS LAST, created_at DESC"
    ), {"org": str(club.id)})).all()
    return {"episodes": [_row(r) for r in rows]}


@router.post("/episodes")
async def create_episode(db: AsyncSession = Depends(get_db), club=Depends(get_current_club),
                         user=Depends(get_current_user)):
    """A new episode, numbered one past the highest so far, carrying the last
    episode's competitions (names and links), hosts and timings."""
    last = (await db.execute(text(
        "SELECT episode_no, data FROM podcast_episodes WHERE organisation_id = CAST(:org AS uuid) "
        "AND archived_at IS NULL ORDER BY episode_no DESC NULLS LAST, created_at DESC LIMIT 1"
    ), {"org": str(club.id)})).first()
    data: dict = {}
    if last is not None:
        prev = last.data if isinstance(last.data, dict) else json.loads(last.data or "{}")
        for k in CARRY_KEYS:
            if k in prev:
                data[k] = prev[k]
        # Keep each competition's name and link; the figures belong to last round.
        if isinstance(data.get("competitions"), list):
            data["competitions"] = [
                {"key": c.get("key"), "name": c.get("name"), "link": c.get("link") or ""}
                for c in data["competitions"] if isinstance(c, dict)
            ]
    nxt = ((last.episode_no or 0) + 1) if last is not None else 1
    eid = str(uuid.uuid4())
    await db.execute(text(
        "INSERT INTO podcast_episodes (id, organisation_id, episode_no, data, updated_by) "
        "VALUES (CAST(:id AS uuid), CAST(:org AS uuid), :no, CAST(:data AS jsonb), CAST(:by AS uuid))"
    ), {"id": eid, "org": str(club.id), "no": nxt, "data": json.dumps(data), "by": str(user.id)})
    await db.commit()
    return _full(await _load(db, club.id, eid))


@router.get("/episodes/{episode_id}")
async def get_episode(episode_id: str, db: AsyncSession = Depends(get_db), club=Depends(get_current_club)):
    return _full(await _load(db, club.id, episode_id))


class EpisodePatch(BaseModel):
    episode_no: int | None = None
    recording_date: date | None = None
    round_label: str | None = None
    data: dict | None = None


@router.patch("/episodes/{episode_id}")
async def save_episode(episode_id: str, body: EpisodePatch, db: AsyncSession = Depends(get_db),
                       club=Depends(get_current_club), user=Depends(get_current_user)):
    """Save what was sent. A key that is absent is left alone; an explicit null
    clears it (``data`` cannot be cleared, only replaced)."""
    await _load(db, club.id, episode_id)
    sent = body.model_fields_set
    sets, params = [], {"id": episode_id, "org": str(club.id), "by": str(user.id)}
    if "episode_no" in sent:
        sets.append("episode_no = :no")
        params["no"] = body.episode_no
    if "recording_date" in sent:
        sets.append("recording_date = :rd")
        params["rd"] = body.recording_date
    if "round_label" in sent:
        sets.append("round_label = :rl")
        params["rl"] = (body.round_label or "").strip()[:200] or None
    if "data" in sent and body.data is not None:
        blob = json.dumps(body.data)
        if len(blob.encode()) > MAX_DATA_BYTES:
            raise HTTPException(413, "That run sheet is too large to save.")
        sets.append("data = CAST(:data AS jsonb)")
        params["data"] = blob
    if sets:
        await db.execute(text(
            f"UPDATE podcast_episodes SET {', '.join(sets)}, updated_at = NOW(), "
            "updated_by = CAST(:by AS uuid) "
            "WHERE id = CAST(:id AS uuid) AND organisation_id = CAST(:org AS uuid)"
        ), params)
        await db.commit()
    return _full(await _load(db, club.id, episode_id))


@router.post("/episodes/{episode_id}/archive")
async def archive_episode(episode_id: str, db: AsyncSession = Depends(get_db), club=Depends(get_current_club)):
    await _load(db, club.id, episode_id)
    await db.execute(text(
        "UPDATE podcast_episodes SET archived_at = NOW() "
        "WHERE id = CAST(:id AS uuid) AND organisation_id = CAST(:org AS uuid)"
    ), {"id": episode_id, "org": str(club.id)})
    await db.commit()
    return {"ok": True}
