"""Capability-based authorisation.

Roles set a default tier; capabilities are the unit of permission a Main
Admin can hand out to a club member.

- super_admin / club_admin: implicitly have ALL capabilities. The
  capabilities array on their membership is ignored.
- club_member: capabilities is an explicit allowlist. Empty array means
  "logged in but can't do anything destructive" — basically view-only.
  `view_only_caps` marks the capabilities in that list held at VIEW level
  (services/access.py): a route that needs one answers a read (GET) and refuses
  a write.

Adding a new capability: append a constant below, wire it to whichever
endpoints/UI it gates. Old memberships keep working — they'll just lack
the new cap until a Main Admin grants it.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
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
MANAGE_WEBSITE = "manage_website"             # public club website: news, pages, honours, committee, galleries
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
MANAGE_SELECTIONS = "manage_selections"       # BetterSelect: every item below at once (the umbrella a module lock grants)
SELECT_SQUADS = "select_squads"               # BetterSelect: squads and ladders
SELECT_AVAILABILITY = "select_availability"   # BetterSelect: who can play each weekend
SELECT_SELECTION = "select_selection"         # BetterSelect: naming the side, and the whiteboard
SELECT_NETS = "select_nets"                   # BetterSelect: training and net sessions
SELECT_ROTATION = "select_rotation"           # BetterSelect: Junior Rotation (batting order and fielding rotation)
SELECT_FINES = "select_fines"                 # BetterSelect: the post-game fines session and pot
SELECT_RULES = "select_rules"                 # BetterSelect: settings and selection rules
SELECT_AUDIT = "select_audit"                 # BetterSelect: who changed what in selection and availability
MANAGE_VOTES = "manage_votes"                 # BetterSelect: vote collection — config, ballots, lock/reopen
VIEW_VOTE_RESULTS = "view_vote_results"       # BetterSelect: see vote tallies + the season leaderboard
MANAGE_IQ = "manage_iq"                       # BetterIQ: opposition analysis + scouting dossiers
MANAGE_COMMS = "manage_comms"                 # BetterComms: contacts + bulk email campaigns
MANAGE_MERCH = "manage_merch"                 # BetterMerch: stock register (apparel, equipment, food/drink)
MANAGE_FANTASY = "manage_fantasy"             # BetterFantasyCricket: fantasy season setup, leagues, settlement
MANAGE_CRM = "manage_crm"                     # BetterCRM: deals/pipeline, contacts, activities
MANAGE_COMMITTEE = "manage_committee"         # Committee positions/terms, task register, documents, club calendar
MANAGE_MEMBERS = "manage_members"             # ClubManager Directory: add/edit/import non-player people + third parties
MANAGE_VOLUNTEERS = "manage_volunteers"       # Volunteer profiles + hours ledger
MANAGE_QUALIFICATIONS = "manage_qualifications"  # Qualification types + member qualifications/expiry
MANAGE_ASSETS = "manage_assets"               # Club assets, facilities, bookings, maintenance logs
MANAGE_CLUB_DIARY = "manage_club_diary"       # Annual/recurring compliance & maintenance task calendar
MANAGE_CLUB_ROOM = "manage_club_room"         # Club Room Mode: playlist + slides + custom images

ALL_CAPABILITIES = (
    MANAGE_SETTINGS,
    MANAGE_PLAYERS,
    MANAGE_MERGES,
    MANAGE_YEARBOOKS,
    MANAGE_AWARDS,
    MANAGE_SPONSORS,
    MANAGE_WEBSITE,
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
    MANAGE_SELECTIONS,
    SELECT_SQUADS,
    SELECT_AVAILABILITY,
    SELECT_SELECTION,
    SELECT_NETS,
    SELECT_ROTATION,
    SELECT_FINES,
    SELECT_RULES,
    SELECT_AUDIT,
    MANAGE_VOTES,
    VIEW_VOTE_RESULTS,
    MANAGE_IQ,
    MANAGE_COMMS,
    MANAGE_MERCH,
    MANAGE_FANTASY,
    MANAGE_CRM,
    MANAGE_COMMITTEE,
    MANAGE_MEMBERS,
    MANAGE_VOLUNTEERS,
    MANAGE_QUALIFICATIONS,
    MANAGE_ASSETS,
    MANAGE_CLUB_DIARY,
    MANAGE_CLUB_ROOM,
)


# BetterSelect's items each have a capability of their own, and MANAGE_SELECTIONS
# is the umbrella that satisfies any of them (full admins, a person locked to the
# whole module, and the legacy allowlists all hold it). A route gates on
# `require_any_cap(SELECT_<ITEM>, MANAGE_SELECTIONS)`.
SELECT_ITEM_CAPS = (
    SELECT_SQUADS, SELECT_AVAILABILITY, SELECT_SELECTION, SELECT_NETS, SELECT_ROTATION,
    SELECT_FINES, SELECT_RULES, SELECT_AUDIT,
)
# Shared reads every BetterSelect screen leans on (squad lists, the availability
# config, the rules, who is already picked): open to a holder of any BetterSelect
# item, so switching one item on does not need the others.
SELECT_ANY = (MANAGE_SELECTIONS, MANAGE_FIXTURES) + SELECT_ITEM_CAPS


# ─── Role helpers ────────────────────────────────────────────────────────────

PRIVILEGED_ROLES = ("super_admin", "club_admin")  # roles that imply all caps

SAFE_METHODS = ("GET", "HEAD", "OPTIONS")
VIEW_ONLY_MESSAGE = "You have view-only access to this. Ask your Primary Admin for edit access."


def _is_read(request) -> bool:
    """True for a read. A missing request counts as a write: fail closed."""
    return request is not None and getattr(request, "method", None) in SAFE_METHODS


def membership_can_write(role: str, caps: list[str] | None, view_only: list[str] | None, capability: str) -> bool:
    """Holds the capability AND not only at view level."""
    if role in PRIVILEGED_ROLES:
        return True
    return capability in (caps or []) and capability not in (view_only or [])


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
        request: Request = None,
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
        if not _is_read(request) and not membership_can_write(
                membership.role, membership.capabilities, getattr(membership, "view_only_caps", None), capability):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=VIEW_ONLY_MESSAGE)
        return current_user

    # Read by verification/audit_route_access.py, which fails on a club route
    # that declares no capability. Not used at request time.
    _dep.required_caps = (capability,)
    return _dep


def require_any_cap(*capabilities: str):
    """Like require_cap, but passes if the membership holds ANY of the given
    capabilities — e.g. a page a manager or a designated viewer can both open."""
    from app.routers.auth import get_current_user
    from app.models.db import ClubMembership, User, get_db

    async def _dep(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
        request: Request = None,
    ) -> User:
        row = await db.execute(
            select(ClubMembership).where(ClubMembership.user_id == current_user.id)
        )
        membership = row.scalar_one_or_none()
        if not membership:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No club membership found")
        held = [
            cap for cap in capabilities
            if membership_has_capability(membership.role, membership.capabilities, cap)
        ]
        if not held:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing capability: one of {', '.join(capabilities)}",
            )
        if not _is_read(request) and not any(
            membership_can_write(membership.role, membership.capabilities,
                                 getattr(membership, "view_only_caps", None), cap)
            for cap in held
        ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=VIEW_ONLY_MESSAGE)
        return current_user

    _dep.required_caps = tuple(capabilities)
    return _dep


def require_full_admin():
    """Passes only for a Club Admin or Super Admin: not for a person a Primary
    Admin locked to one module. For club-wide screens that belong to no module
    (Plan & Billing, the setup wizard), which `membership_has_capability` cannot
    express because no capability stands for them."""
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
        if membership.role not in PRIVILEGED_ROLES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only a full club admin can do this",
            )
        return current_user

    _dep.full_admin_only = True
    return _dep
