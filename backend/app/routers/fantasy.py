"""BetterFantasyCricket API — an internal club fantasy cricket league.

Players are the club's own playing list; matches are the club's own fixtures
across every grade. Fantasy points are computed from the per-innings stats we
already hold (batting, bowling, fielding, dismissals), so no new data feed is
needed. Full design: docs/betterfantasycricket.md.

Everything is scoped to the caller's club (get_current_club) and gated by the
MANAGE_FANTASY capability. The whole router is module-gated by
require_module("fantasy") at include time (main.py).

This is the phase-1 scaffold: the engines, scoring and surfaces land in later
phases per the spec's phase plan. The defaults below are the single source of
truth the season setup will seed from.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.routers.auth import get_current_club
from app.auth.capabilities import require_cap, MANAGE_FANTASY
from app.models.db import FANTASY_ROLES
from app.services.fantasy_scoring import DEFAULT_SCORING, DEFAULT_RULES

router = APIRouter(prefix="/club-admin/fantasy", tags=["club-admin-fantasy"])

_require = Depends(require_cap(MANAGE_FANTASY))


@router.get("/config")
async def get_config(club=Depends(get_current_club), _=_require):
    """Module status + the default season config the setup screen seeds from.

    `season` is null until a club creates its first fantasy season (phase 4).
    """
    return {
        "module": "fantasy",
        "club_id": str(club.id),
        "roles": list(FANTASY_ROLES),
        "defaults": {"scoring": DEFAULT_SCORING, "rules": DEFAULT_RULES},
        "season": None,
    }
