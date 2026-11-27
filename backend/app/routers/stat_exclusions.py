"""A club leaves a whole match out of its players' stats, and counts it again. See
`services/stat_exclusions.py` for how every figure follows and whose figures change.

Gated by MANAGE_MANUAL_ENTRIES, the capability every other hand-made stats correction uses, and
logged on the Manual entries audit trail, where each change can be undone.

    GET    /club-admin/stat-exclusions                 the matches the club has left out
    GET    /club-admin/stat-exclusions/lookup?link=    a pasted link: the match and what it takes away
    POST   /club-admin/stat-exclusions                 leave a match out
    DELETE /club-admin/stat-exclusions/{id}            count it again

The public scorecard says so too: `get_scorecard` carries `stats_excluded` for the club the card is
read from.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_MANUAL_ENTRIES, require_cap
from app.models.db import Organisation, User, get_db
from app.routers.auth import get_current_club
from app.routers.manual_entries import _log_edit, _recompute_milestones
from app.services import stat_exclusions as sx

router = APIRouter(tags=["games"])


class ExcludeIn(BaseModel):
    # A pasted link or a bare match id: the match page sends the id, the admin screen the link.
    link: str = Field(max_length=2000)
    note: Optional[str] = Field(default=None, max_length=300)


async def _info(db: AsyncSession, club_id, raw: str) -> dict:
    try:
        return await sx.match_info(db, club_id, sx.parse_link(raw))
    except sx.Refused as e:
        raise HTTPException(status_code=e.status, detail=str(e))


@router.get("/club-admin/stat-exclusions")
async def list_exclusions(
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    return {"exclusions": await sx.list_for_org(db, club.id)}


@router.get("/club-admin/stat-exclusions/lookup")
async def lookup(
    link: str = Query(..., max_length=2000),
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Read only, so a GET (a capability held at View may read it)."""
    return await _info(db, club.id, link)


@router.post("/club-admin/stat-exclusions")
async def exclude(
    data: ExcludeIn,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    info = await _info(db, club.id, data.link)
    gid = uuid.UUID(info["game_id"])
    try:
        snap = await sx.exclude(db, club.id, current_user.id, gid, info["source"], data.note)
    except sx.Refused as e:
        raise HTTPException(status_code=e.status, detail=str(e))
    summary = sx.summary(info, "left out of career stats")
    await _log_edit(db, org_id=club.id, user_id=current_user.id, action="create", target_table=sx.TABLE,
                    target_id=str(snap["id"]), summary=summary, before=None, after=snap)
    await db.commit()
    await _recompute_milestones(db, club.id, [uuid.UUID(p["player_id"]) for p in info["players"]])
    return {"exclusion": snap, "match": await sx.match_info(db, club.id, gid), "summary": summary}


@router.delete("/club-admin/stat-exclusions/{exclusion_id}")
async def restore(
    exclusion_id: int,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    snap = await sx.restore(db, club.id, current_user.id, exclusion_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="That match is already counted in your stats.")
    gid = uuid.UUID(snap["game_id"])
    try:
        info = await sx.match_info(db, club.id, gid)
    except sx.Refused:
        info = {"game_id": snap["game_id"], "players": []}
    summary = sx.summary(info, "counted in career stats again")
    await _log_edit(db, org_id=club.id, user_id=current_user.id, action="delete", target_table=sx.TABLE,
                    target_id=str(exclusion_id), summary=summary, before=snap, after=None)
    await db.commit()
    await _recompute_milestones(db, club.id, [uuid.UUID(p["player_id"]) for p in info.get("players", [])])
    return {"restored": snap, "summary": summary}
