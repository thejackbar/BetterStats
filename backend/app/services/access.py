"""Module-locked club users: the one place that knows what "locked to a module" means.

A Primary Admin can lock a colleague to ONE module. The person then has every
capability that module's menu needs, and nothing outside it: not another
module, not Settings, not Users, not billing. `user_access` (migration 344) is
the source of truth. The account's `club_memberships` row is set to role
`club_member`, whose `capabilities` list the existing engine
(auth/capabilities.py) already treats as an explicit allowlist, so every reader
of that list (the route gates, `/auth/me`, notification routing) works unchanged.

That list is a CACHE derived from `MODULE_ACCESS` below. It is rewritten when a
person is locked, and `resync_module_caps` rewrites every locked person's list on
each boot, so adding a capability to a module here reaches existing users on the
next deploy without anyone editing them.

Rules kept here:

* No row means no restriction. Only `club_admin` accounts with no `user_access`
  row have every capability.
* The Primary Admin and a Super Admin are never locked.
* Fail closed: an unknown module key is refused, and a locked person whose
  module has no capabilities holds none.
* A locked person stays in their own club. `auth.effective_club_id` lets only a
  `club_admin` act in a linked club, and a locked person is a `club_member`.
* Clearing a lock puts the person back to a full `club_admin`, but only when a
  `user_access` row said they were locked. A legacy `club_member` with an
  explicit allowlist and no row is never touched here.
"""
from __future__ import annotations

import json
import uuid
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import capabilities as C


MODE_MODULE = "module"
LOCKED_ROLE = "club_member"
FULL_ROLE = "club_admin"


class AccessError(Exception):
    """A refused change. ``status`` is the HTTP code the router sends."""

    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.message = message
        self.status = status


# Module -> the capabilities its menu needs. Built from each module's own
# navigation (BetterStatsLayout, BetterSelectLayout, BetterClubhouseLayout,
# IQLayout and the rest), so a locked person sees every item of their module and
# none of another. Order here is the order the Users screen lists them in.
#
# Capabilities in NO module are never given to a locked person: manage_settings,
# manage_users and run_hard_refresh. They belong to the club's own Primary Admin.
# `manage_players` sits in both BetterStats and BetterSelect because BetterSelect's
# Players page needs it; it edits the same club player register either way.
MODULE_ACCESS: dict[str, dict] = {
    "stats": {
        "name": "BetterStats",
        "blurb": "Matches, players, imports, awards, yearbooks, sponsors, Club Room and the public site.",
        "caps": (
            C.MANAGE_PLAYERS, C.MANAGE_FAMILIES, C.RUN_SYNC, C.MANAGE_MANUAL_ENTRIES,
            C.MANAGE_MILESTONES, C.MANAGE_AWARDS, C.MANAGE_MERGES, C.MANAGE_YEARBOOKS,
            C.MANAGE_REPORTS, C.MANAGE_SPONSORS, C.MANAGE_CLUB_ROOM, C.MANAGE_WEBSITE,
        ),
    },
    "select": {
        "name": "BetterSelect",
        "blurb": "Squads, fixtures, availability, selection, nets, votes, ladders and fines.",
        "caps": (
            C.MANAGE_PLAYERS, C.MANAGE_FIXTURES, C.MANAGE_SELECTIONS,
            C.MANAGE_VOTES, C.VIEW_VOTE_RESULTS,
        ),
    },
    "socials": {
        "name": "BetterSocials",
        "blurb": "The social post designer.",
        "caps": (C.MANAGE_SOCIAL,),
    },
    "iq": {
        "name": "BetterIQ",
        "blurb": "Opposition scouting and selection analysis.",
        "caps": (C.MANAGE_IQ,),
    },
    "fantasy": {
        "name": "BetterFantasyCricket",
        "blurb": "Fantasy seasons, leagues and round settlement.",
        "caps": (C.MANAGE_FANTASY,),
    },
    "admin": {
        "name": "BetterAdmin",
        "blurb": "Directory, roster, committee, fees, emails, stock, contacts, assets and the diary.",
        "caps": (
            C.MANAGE_MEMBERS, C.MANAGE_VOLUNTEERS, C.MANAGE_QUALIFICATIONS, C.MANAGE_COMMITTEE,
            C.MANAGE_FEES, C.MANAGE_COMMS, C.MANAGE_MERCH, C.MANAGE_CRM,
            C.MANAGE_ASSETS, C.MANAGE_CLUB_DIARY,
        ),
    },
}

# Capabilities no locked person is ever given.
NEVER_LOCKED = (C.MANAGE_SETTINGS, C.MANAGE_USERS, C.RUN_HARD_REFRESH)


def module_choices() -> list[dict]:
    """The modules a Primary Admin can lock someone to, for the Users screen."""
    return [
        {"key": key, "name": spec["name"], "blurb": spec["blurb"]}
        for key, spec in MODULE_ACCESS.items()
    ]


def caps_for_module(module_key: str | None) -> list[str]:
    """The capabilities a person locked to ``module_key`` holds, in the order the
    capability registry lists them. Empty for an unknown key (fail closed)."""
    spec = MODULE_ACCESS.get(module_key or "")
    if spec is None:
        return []
    wanted = set(spec["caps"])
    return [c for c in C.ALL_CAPABILITIES if c in wanted]


def _uid(value) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


async def get_access(db: AsyncSession, user_id, club_id) -> dict | None:
    """The lock on this person at this club, or None when they are not locked."""
    row = (await db.execute(
        text("SELECT mode, module_key FROM user_access WHERE user_id = :u AND club_id = :c"),
        {"u": _uid(user_id), "c": _uid(club_id)},
    )).first()
    if row is None:
        return None
    return {"mode": row.mode, "module_key": row.module_key}


async def access_for_club(db: AsyncSession, club_id) -> dict[str, dict]:
    """Every locked person at a club, keyed by user id, for the Users list."""
    rows = (await db.execute(
        text("SELECT user_id, mode, module_key FROM user_access WHERE club_id = :c"),
        {"c": _uid(club_id)},
    )).all()
    return {str(r.user_id): {"mode": r.mode, "module_key": r.module_key} for r in rows}


async def _membership(db: AsyncSession, user_id, club_id):
    return (await db.execute(
        text("SELECT id, role, is_primary_admin FROM club_memberships "
             "WHERE user_id = :u AND club_id = :c"),
        {"u": _uid(user_id), "c": _uid(club_id)},
    )).first()


async def lock_to_module(db: AsyncSession, *, user_id, club_id, module_key: str, by_user_id=None) -> list[str]:
    """Lock a person to one module. Returns the capabilities they now hold.

    Caller commits. Raises ``AccessError`` for a refusal."""
    if module_key not in MODULE_ACCESS:
        raise AccessError("Pick one of the listed modules", 422)
    m = await _membership(db, user_id, club_id)
    if m is None:
        raise AccessError("That person is not a user of this club", 404)
    if m.role == "super_admin":
        raise AccessError("A Super Admin's access is not set here", 409)
    if m.is_primary_admin:
        raise AccessError(
            "The Primary Admin always has full access. Transfer the Primary Admin to someone else first.", 409)
    if m.role not in (FULL_ROLE, LOCKED_ROLE):
        raise AccessError("That account's access is not set here", 409)
    caps = caps_for_module(module_key)
    await db.execute(
        text(
            "INSERT INTO user_access (user_id, club_id, mode, module_key, updated_by_user_id) "
            "VALUES (:u, :c, :mode, :mod, :by) "
            "ON CONFLICT (user_id, club_id) DO UPDATE SET mode = EXCLUDED.mode, "
            "module_key = EXCLUDED.module_key, updated_by_user_id = EXCLUDED.updated_by_user_id, "
            "updated_at = NOW()"
        ),
        {"u": _uid(user_id), "c": _uid(club_id), "mode": MODE_MODULE, "mod": module_key,
         "by": _uid(by_user_id) if by_user_id else None},
    )
    await db.execute(
        text("UPDATE club_memberships SET role = :role, capabilities = CAST(:caps AS JSONB) "
             "WHERE user_id = :u AND club_id = :c"),
        {"role": LOCKED_ROLE, "caps": json.dumps(caps), "u": _uid(user_id), "c": _uid(club_id)},
    )
    return caps


async def unlock(db: AsyncSession, *, user_id, club_id) -> bool:
    """Take the lock off: back to a full Club Admin. True when there was a lock.

    Caller commits. A person with no ``user_access`` row is left exactly as they
    are, so a legacy `club_member` allowlist is never widened by this."""
    res = await db.execute(
        text("DELETE FROM user_access WHERE user_id = :u AND club_id = :c RETURNING 1"),
        {"u": _uid(user_id), "c": _uid(club_id)},
    )
    if res.first() is None:
        return False
    await db.execute(
        text("UPDATE club_memberships SET role = :role, capabilities = '[]'::jsonb "
             "WHERE user_id = :u AND club_id = :c AND role = :locked"),
        {"role": FULL_ROLE, "locked": LOCKED_ROLE, "u": _uid(user_id), "c": _uid(club_id)},
    )
    return True


async def resync_module_caps(db: AsyncSession) -> int:
    """Rewrite the cached capability list of every locked person from
    ``MODULE_ACCESS``. Runs on every boot. Idempotent: it only writes a row whose
    list differs. Returns the number of rows rewritten."""
    rows = (await db.execute(
        text(
            "SELECT ua.user_id, ua.club_id, ua.module_key, cm.capabilities, cm.role "
            "FROM user_access ua JOIN club_memberships cm "
            "ON cm.user_id = ua.user_id AND cm.club_id = ua.club_id "
            "WHERE ua.mode = :mode"
        ),
        {"mode": MODE_MODULE},
    )).all()
    changed = 0
    for r in rows:
        want = caps_for_module(r.module_key)
        if r.role == LOCKED_ROLE and list(r.capabilities or []) == want:
            continue
        await db.execute(
            text("UPDATE club_memberships SET role = :role, capabilities = CAST(:caps AS JSONB) "
                 "WHERE user_id = :u AND club_id = :c"),
            {"role": LOCKED_ROLE, "caps": json.dumps(want), "u": r.user_id, "c": r.club_id},
        )
        changed += 1
    return changed


def describe(access: dict | None) -> dict:
    """The shape the API and the Users screen use for one person's access."""
    if not access:
        return {"mode": "full", "module_key": None, "module_name": None}
    spec = MODULE_ACCESS.get(access.get("module_key") or "")
    return {
        "mode": access["mode"],
        "module_key": access.get("module_key"),
        "module_name": spec["name"] if spec else None,
    }


def known_module_keys() -> Iterable[str]:
    return MODULE_ACCESS.keys()
