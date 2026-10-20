"""Audit History: every change to a player in selection, availability and squads.

Reads ``audit_events`` (written by services/player_audit from the places the changes
happen). Searchable, filterable by area, action, who, squad and date, and
exportable as CSV with the same filters. Read-only: nothing here edits the trail.
"""
from __future__ import annotations

import csv
import io
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import (
    MANAGE_SELECTIONS, SELECT_AUDIT, require_any_cap,
)  # BetterSelect item permissions
from app.auth.capabilities import MANAGE_SELECTIONS, require_cap
from app.models.db import Organisation, User, get_db
from app.routers.auth import get_current_club
from app.services import player_audit

router = APIRouter(prefix="/audit", tags=["audit"])


def _date(v: Optional[str], name: str) -> Optional[date]:
    if not v:
        return None
    try:
        return date.fromisoformat(v[:10])
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{name} is not a date")


def _filters(q, area, action, user, player_id, team, date_from, date_to, tz) -> dict:
    if area and area not in player_audit.AREAS:
        raise HTTPException(status_code=400, detail="Unknown area")
    return dict(q=q, area=area, action=action, user=user, player_id=player_id, team=team,
                date_from=_date(date_from, "From"), date_to=_date(date_to, "To"), tz=tz)


@router.get("/facets")
async def audit_facets(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _user: User = Depends(require_any_cap(SELECT_AUDIT, MANAGE_SELECTIONS)),
):
    return await player_audit.facets(db, club.id)


@router.get("/events")
async def audit_events(
    q: Optional[str] = None, area: Optional[str] = None, action: Optional[str] = None,
    user: Optional[str] = None, player_id: Optional[str] = None, team: Optional[str] = None,
    date_from: Optional[str] = None, date_to: Optional[str] = None, tz: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _user: User = Depends(require_any_cap(SELECT_AUDIT, MANAGE_SELECTIONS)),
):
    f = _filters(q, area, action, user, player_id, team, date_from, date_to, tz)
    return await player_audit.search(db, club.id, limit=limit, offset=offset, **f)


@router.get("/export.csv")
async def audit_export(
    q: Optional[str] = None, area: Optional[str] = None, action: Optional[str] = None,
    user: Optional[str] = None, player_id: Optional[str] = None, team: Optional[str] = None,
    date_from: Optional[str] = None, date_to: Optional[str] = None, tz: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _user: User = Depends(require_any_cap(SELECT_AUDIT, MANAGE_SELECTIONS)),
):
    """The same rows the list shows for these filters, as a spreadsheet."""
    f = _filters(q, area, action, user, player_id, team, date_from, date_to, tz)
    rows = await player_audit.export_rows(db, club.id, **f)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(["Date", "Time", "Area", "Action", "Player", "Squad or team", "Game", "What changed", "Changed by", "Via"])
    for r in rows:
        w.writerow([r["local_date"], r["local_time"], r["area"].capitalize(), r["action_label"], r["player"] or "",
                    r["team"] or "", r["game"] or "", r["summary"], r["by"], r["via"]])
    # BOM so Excel reads names with accents as UTF-8.
    body = "﻿" + buf.getvalue()
    name = f"{(club.short_name or club.name or 'club').strip().replace(' ', '-')}-audit-history.csv"
    return Response(content=body, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
