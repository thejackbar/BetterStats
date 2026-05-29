"""Capability-based authorisation.

Roles set a default tier; capabilities are the unit of permission a Main
Admin can hand out to a club member.

- super_admin / club_admin: implicitly have ALL capabilities. The
  capabilities array on their membership is ignored.
- club_member: capabilities is an explicit allowlist. Empty array means
  "logged in but can't do anything destructive" — basically view-only.

Adding a new capability: append a constant below, wire it to whichever
endpoints/UI it gates. Old memberships keep working — they'll just lack
the new cap until a Main Admin grants it.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


# ─── Capability registry ─────────────────────────────────────────────────────
# Keep in sync with frontend/src/lib/capabilities.js (labels + sections).

MANAGE_SETTINGS = "manage_settings"           # club branding, name, colours, logo
MANAGE_PLAYERS = "manage_players"             # player edit + photo
MANAGE_MERGES = "manage_merges"               # player + grade + season merges (and undo)
MANAGE_YEARBOOKS = "manage_yearbooks"         # yearbooks, sections, honour board
MANAGE_AWARDS = "manage_awards"               # awards + achievements + award defs
MANAGE_SPONSORS = "manage_sponsors"           # sponsors
MANAGE_SOCIAL = "manage_social"               # social posts
MANAGE_MILESTONES = "manage_milestones"       # milestones (definitions, manual entry)
RUN_SYNC = "run_sync"                         # Sync Now + Fix Missing Totals
RUN_HARD_REFRESH = "run_hard_refresh"         # destructive full rebuild
MANAGE_USERS = "manage_users"                 # invite/edit club members
MANAGE_REPORTS = "manage_reports"             # approve/reject saved StatLab reports
MANAGE_FAMILIES = "manage_families"           # create/edit player family groupings
MANAGE_MANUAL_ENTRIES = "manage_manual_entries"  # historical manual stat entry + edit + undo
MANAGE_FEES = "manage_fees"                   # fee tracking: members, schedule, match days
MANAGE_FIXTURES = "manage_fixtures"           # BetterSelect: fixtures (partner sync + manual create/edit)

ALL_CAPABILITIES = (
    MANAGE_SETTINGS,
    MANAGE_PLAYERS,
    MANAGE_MERGES,
    MANAGE_YEARBOOKS,
    MANAGE_AWARDS,
    MANAGE_SPONSORS,
    MANAGE_SOCIAL,
    MANAGE_MILESTONES,
    RUN_SYNC,
    RUN_HARD_REFRESH,
    MANAGE_USERS,
    MANAGE_REPORTS,
    MANAGE_FAMILIES,
    MANAGE_MANUAL_ENTRIES,
    MANAGE_FEES,
    MANAGE_FIXTURES,
)


# ─── Role helpers ────────────────────────────────────────────────────────────

PRIVILEGED_ROLES = ("super_admin", "club_admin")  # roles that imply all caps


def membership_has_capability(role: str, caps: list[str] | None, capability: str) -> bool:
    if role in PRIVILEGED_ROLES:
        return True
    return capability in (caps or [])


def effective_capabilities(role: str, caps: list[str] | None) -> list[str]:
    """Return the full set of caps this membership effectively holds."""
    if role in PRIVILEGED_ROLES:
        return list(ALL_CAPABILITIES)
    return list(caps or [])


# ─── FastAPI dependency factory ──────────────────────────────────────────────

def require_cap(capability: str):
    """Use as:
        @router.post("/foo", dependencies=[Depends(require_cap(MANAGE_MERGES))])
    Or as a named dep when you also need the user:
        current_user = Depends(require_cap(MANAGE_MERGES))
    """
    # Imports kept inside the closure to avoid a circular import — auth.py
    # imports from models.db, which would otherwise re-import this module
    # at startup.
    from app.routers.auth import get_current_user
    from app.models.db import ClubMembership, User, get_db

    async def _dep(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        row = await db.execute(
            select(ClubMembership).where(ClubMembership.user_id == current_user.id)
        )
        membership = row.scalar_one_or_none()
        if not membership:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No club membership found")
        if not membership_has_capability(membership.role, membership.capabilities, capability):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing capability: {capability}",
            )
        return current_user

    return _dep
