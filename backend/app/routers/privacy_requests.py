"""Super Admin: handling a person's privacy request.

``GET /players``                       find a person across every club.
``GET /players/{id}/data-report.pdf``  the PDF of what we hold about them
                                       (services/player_data_report.py).

Super Admin only. The PDF holds a person's contact details, so the download is
never cached and every one is written to the audit log of the person's club.
Hiding a person at their request is still done with
``python -m app.scripts.hide_player_at_request`` (see services/player_privacy.py).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Player, User, get_db
from app.routers.auth import require_super_admin
from app.services import player_data_report, player_privacy
from app.services.audit_log import log_activity

router = APIRouter(prefix="/club-admin/super/privacy", tags=["privacy-requests"])


@router.get("/players")
async def find_players(
    q: str = Query("", max_length=120),
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Players matching a name (any order) or an id, at any club, with where each stands."""
    term = " ".join((q or "").split())
    if len(term) < 3:
        return {"players": [], "note": "Type at least three characters of a name, or paste a player id."}
    words = [w for w in term.replace(",", " ").split() if w]
    clauses = " AND ".join(f"(p.name ILIKE :w{i} OR p.display_name_override ILIKE :w{i})" for i in range(len(words)))
    params = {f"w{i}": f"%{w}%" for i, w in enumerate(words)}
    params.update({"idq": term.lower(), "lim": 25})
    rows = (await db.execute(text(f"""
        SELECT p.id::text AS id, p.name, p.grassroots_id, p.is_public, p.privacy_hidden_at, p.privacy_hidden_by,
               o.name AS club
          FROM players p LEFT JOIN organisations o ON o.id = p.organisation_id
         WHERE ({clauses}) OR LOWER(p.id::text) = :idq OR LOWER(COALESCE(p.grassroots_id, '')) = :idq
         ORDER BY p.name, o.name
         LIMIT :lim
    """), params)).mappings().all()
    return {"players": [{
        "id": r["id"], "name": r["name"], "club": r["club"],
        "has_participant_id": bool(r["grassroots_id"]),
        "status": ("removed_at_request" if r["privacy_hidden_at"] and r["privacy_hidden_by"] != player_privacy.NAME_MATCH
                   else "name_match_hold" if r["privacy_hidden_at"]
                   else "hidden_by_club" if r["is_public"] is False else "public"),
    } for r in rows]}


@router.get("/players/{player_id}/data-report.pdf")
async def data_report(
    player_id: str,
    user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        pid = uuid.UUID(player_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="Invalid player id")
    player = await db.get(Player, pid)
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")
    data = await player_data_report.gather(db, player)
    pdf = player_data_report.render_pdf(data)
    if player.organisation_id:
        await log_activity(
            db, org_id=player.organisation_id, user_id=user.id, action="privacy_data_report",
            target_type="player", target_id=str(player.id),
            details={"records": len(data["records"]), "matches": len(data["matches"])},
            commit=True,
        )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{player_data_report.filename_for(player.name)}"',
            "Cache-Control": "no-store",
            "X-Robots-Tag": "noindex",
        },
    )
