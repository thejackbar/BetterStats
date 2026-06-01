"""BetterIQ router — analytics + AI module (Best tier).

Module entitlement is applied where this router is mounted (``main.py``:
``include_router(iq.router, dependencies=[Depends(require_module("iq"))])``).
Here we additionally gate on the ``MANAGE_IQ`` capability — opposition scouting
is selector-grade intel, so it's treated like the other admin tools rather than
open to every club member. ``club_admin`` / ``super_admin`` hold all caps.

Phase 1 surface: Opposition analysis (read-only over held data). Selection
analysis, player trends and NL Q&A are later phases.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_IQ, require_cap
from app.models.db import Organisation, get_db
from app.routers.auth import get_current_club
from app.services import iq as iq_service
from app.services import iq_opponent
from app.services import iq_selection
from app.services import iq_trends

# Every BetterIQ route requires the MANAGE_IQ capability.
router = APIRouter(prefix="/iq", tags=["iq"], dependencies=[Depends(require_cap(MANAGE_IQ))])


@router.get("/opposition/opponents")
async def opposition_opponents(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Opponents we have history against, plus upcoming fixtures to scout."""
    return await iq_service.list_opponents(db, str(club.id))


@router.get("/opposition/report")
async def opposition_report(
    opponent: str | None = Query(None, description="opp_key from the opponents list"),
    fixture_id: str | None = Query(None, description="resolve the opponent from an upcoming fixture"),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Full scouting report for one opponent (head-to-head, our record vs them,
    their danger batters, and their roster when that club is synced)."""
    return await iq_service.opposition_report(
        db, str(club.id), opponent=opponent, fixture_id=fixture_id
    )


@router.get("/opposition/dossier")
async def opposition_dossier(
    opponent: str | None = Query(None, description="opp_key from the opponents list"),
    fixture_id: str | None = Query(None, description="resolve the opponent (and grade) from a fixture"),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Live opponent dossier (squad + form pulled from the grade, plus deep
    head-to-head vs us). Built on demand in the background; this returns
    ``{status: 'building'}`` until ready, then the assembled payload. Poll it."""
    opp_key, name, grade_id = await iq_service.resolve_opponent(
        db, str(club.id), opponent=opponent, fixture_id=fixture_id
    )
    # A never-before-played opponent has no opp_key — but if a fixture gives us
    # their grade + name we can still scout them live (key the cache on name).
    key = opp_key or (name if grade_id else None)
    if not key:
        return {
            "status": "unavailable",
            "opponent": {"opp_key": None, "name": name},
            "message": (
                f"No identity to scout for {name} yet — we build a dossier once you've"
                " played them, or from the fixture's grade." if name
                else "Opponent not found."
            ),
        }
    return await iq_opponent.get_or_start_dossier(
        db, str(club.id), key, opp_name=name, grade_id=grade_id
    )


@router.post("/opposition/dossier/refresh")
async def refresh_opposition_dossier(
    opponent: str | None = Query(None),
    fixture_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Force a rebuild of the dossier (Refresh button), bypassing the cache TTL."""
    opp_key, name, grade_id = await iq_service.resolve_opponent(
        db, str(club.id), opponent=opponent, fixture_id=fixture_id
    )
    key = opp_key or (name if grade_id else None)
    if not key:
        return {"status": "unavailable", "opponent": {"opp_key": None, "name": name}}
    return await iq_opponent.get_or_start_dossier(
        db, str(club.id), key, opp_name=name, grade_id=grade_id, force=True
    )


# ─── Selection analysis (Phase 2) ────────────────────────────────────────────


@router.get("/selection/lineups")
async def selection_lineups(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Fixtures with a saved BetterSelect lineup, ready to analyse."""
    return await iq_selection.list_lineups(db, str(club.id))


@router.get("/selection/analysis")
async def selection_analysis(
    fixture_id: str = Query(..., description="fixture whose saved XI to analyse"),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Balance, form, warnings, promote/rest and fairness for a fixture's XI."""
    result = await iq_selection.selection_analysis(db, str(club.id), fixture_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Fixture not found")
    return result


# ─── Player trends & development (Phase 3) ───────────────────────────────────


@router.get("/trends/overview")
async def trends_overview(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Club-wide development: milestone watch + breakout/decline movers."""
    return await iq_trends.trends_overview(db, str(club.id))


@router.get("/trends/players")
async def trends_players(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Active players (with career context) for the trends picker."""
    return await iq_trends.list_players(db, str(club.id))


@router.get("/trends/player/{player_id}")
async def trends_player(
    player_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """One player's trajectory, career totals, next milestones and verdict."""
    result = await iq_trends.player_trend(db, str(club.id), player_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return result
