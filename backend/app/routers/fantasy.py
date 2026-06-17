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

router = APIRouter(prefix="/club-admin/fantasy", tags=["club-admin-fantasy"])

_require = Depends(require_cap(MANAGE_FANTASY))


# ── Default season config ─────────────────────────────────────────────────────
# Seeded into a fantasy_season at setup, then editable per club. Kept here as the
# canonical defaults so the frontend can read them before a season exists.

DEFAULT_SCORING = {
    # batting
    "run": 1, "four": 1, "six": 2, "fifty": 16, "hundred": 32, "duck": -4,
    # bowling
    "wicket": 25, "three_wickets": 8, "five_wickets": 16, "maiden": 8,
    # fielding
    "catch": 8, "stumping": 12, "run_out": 12,
    # appearance + multipliers
    "appearance": 4,
    "off_role_multiplier": 1.5,
    "captain_multiplier": 2,
    "triple_captain_multiplier": 3,
}

DEFAULT_RULES = {
    "squad_size": 12,
    "count_best_n": 11,
    "role_quota": {"keeper": 1, "batter": 4, "allrounder": 3, "bowler": 4},
    "budget": 100.0,
    "free_transfers_per_round": 1,
    "max_banked_transfers": 2,
    "transfer_hit": 4,
    "wildcards_per_half": 1,
    "triple_captains_per_half": 1,
}

FANTASY_ROLES = ("keeper", "batter", "allrounder", "bowler")


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
