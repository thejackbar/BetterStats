"""Player Dashboard: the club's settings (BetterStats, no module needed).

The player's own page (`/playerdash/:token`) holds their cards and season, so it belongs to
BetterStats. These routes are where a club switches the DASHBOARD on, hides the button on its public
site, sets the PIN, picks the modules and shares the link. They are NOT behind `require_module("select")`
like `/availability/self-service`.

The dashboard switch is its own (`organisations.player_dashboard_enabled`) and never touches the
BetterSelect availability switch, which keeps owning availability, votes and the BetterSelect sections
of the same link (`services/player_dashboard.availability_live` / `dashboard_live`). Gated on
MANAGE_SETTINGS, the club-wide settings capability. A key that is not sent leaves its setting alone.
"""
from __future__ import annotations

import secrets
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_SETTINGS, require_cap
from app.auth.modules import MODULE_SELECT, org_has_module
from app.models.db import Organisation, User, get_db
from app.routers.auth import get_current_club
from app.routers.availability import active_self_service_players, phone_last4
from app.services import player_dashboard

router = APIRouter(prefix="/player-dashboard", tags=["player-dashboard"])


class SettingsBody(BaseModel):
    enabled: Optional[bool] = None
    require_pin: Optional[bool] = None
    show_on_site: Optional[bool] = None
    # An empty list is a real choice (everything off); only None means "not sent".
    dashboard_modules: Optional[list[str]] = None


async def _payload(db: AsyncSession, club: Organisation) -> dict:
    players = await active_self_service_players(db, club)
    with_phone = sum(1 for p in players if phone_last4(p.phone))
    return {
        "enabled": player_dashboard.dashboard_live(club),
        # With BetterSelect the same link also carries availability and votes, on their own switch.
        "has_select": org_has_module(club, MODULE_SELECT),
        "availability_enabled": player_dashboard.availability_live(club),
        "require_pin": bool(club.availability_require_pin),
        "show_on_site": club.availability_show_on_site is not False,
        "dashboard_modules": player_dashboard.catalogue_for(club),
        "token": club.availability_link_token,
        "path": f"/playerdash/{club.availability_link_token}" if club.availability_link_token else None,
        "phone_coverage": {"with_phone": with_phone, "total": len(players)},
    }


@router.get("/settings")
async def get_settings(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SETTINGS)),
):
    """The page's switches plus a phone-coverage count (a player signs in with the last four
    digits of their mobile, so a player with none cannot open their page)."""
    return await _payload(db, club)


@router.post("/settings")
async def update_settings(
    body: SettingsBody,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SETTINGS)),
):
    if body.require_pin is not None:
        club.availability_require_pin = bool(body.require_pin)
    if body.show_on_site is not None:
        club.availability_show_on_site = bool(body.show_on_site)
    if body.dashboard_modules is not None:
        club.player_dashboard_modules = player_dashboard.store(body.dashboard_modules)
    if body.enabled is not None:
        player_dashboard.set_dashboard_live(club, body.enabled)
    await db.commit()
    await db.refresh(club)
    return await _payload(db, club)


@router.post("/regenerate")
async def regenerate_link(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SETTINGS)),
):
    """Rotate the token: the old link and QR stop working at once."""
    club.availability_link_token = secrets.token_urlsafe(24)
    await db.commit()
    await db.refresh(club)
    return await _payload(db, club)
