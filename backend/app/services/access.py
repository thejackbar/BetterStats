"""What a club user can open: the one place that knows what a limit means.

Everyone starts with full access. A Primary Admin can limit a colleague in one of
two ways, both stored in `user_access` (migration 344):

* ``module``: locked to ONE module. They hold every capability that module's menu
  needs, at Manage, and nothing outside it.
* ``items``: a choice of menu items across any modules, each at View or Manage.
  An item that needs another to work switches it on too (`needs`).

The account's `club_memberships` row is set to role `club_member`, whose
`capabilities` list the existing engine (auth/capabilities.py) already treats as
an explicit allowlist, so every reader of that list (the route gates, `/auth/me`,
notification routing) works unchanged. A second list, `view_only_caps`, marks the
capabilities held at VIEW: a route that needs one answers a read and refuses a
write (`require_cap`), and the screens read it to draw as read only.

Both lists are a CACHE derived from the rows here and the catalogue below. They
are rewritten when a person is limited, and `resync_module_caps` rewrites every
limited person's lists on each boot, so a change to the catalogue reaches existing
users on the next deploy without anyone editing them.

Rules kept here:

* No row means no restriction. Only `club_admin` accounts with no `user_access`
  row have every capability.
* The Primary Admin and a Super Admin are never limited.
* Fail closed: an unknown module, item or level is refused, and a limited person
  whose grants name nothing known holds nothing.
* A limited person stays in their own club. `auth.effective_club_id` lets only a
  `club_admin` act in a linked club, and a limited person is a `club_member`.
* Clearing a limit puts the person back to a full `club_admin`, but only when a
  `user_access` row said they were limited. A legacy `club_member` with an
  explicit allowlist and no row is never touched here.
* Several menu items can share one capability (the three fee screens, the four
  email screens). They are ONE switch until the capability is split, and the
  switch names every screen it opens.
"""
from __future__ import annotations

import json
import uuid
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import capabilities as C


MODE_MODULE = "module"
MODE_ITEMS = "items"
LOCKED_ROLE = "club_member"
FULL_ROLE = "club_admin"

LEVEL_VIEW = "view"
LEVEL_MANAGE = "manage"
LEVELS = (LEVEL_VIEW, LEVEL_MANAGE)


class AccessError(Exception):
    """A refused change. ``status`` is the HTTP code the router sends."""

    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.message = message
        self.status = status


# Module -> the capabilities its menu needs (a person locked to the whole module).
# Built from each module's own navigation (BetterStatsLayout, BetterSelectLayout,
# BetterClubhouseLayout, IQLayout and the rest). Order here is the order the Users
# screen lists them in.
#
# Capabilities in NO module are never given to a limited person: manage_settings,
# manage_users and run_hard_refresh. They belong to the club's own Primary Admin.
# `manage_players` sits in both BetterStats and BetterSelect because BetterSelect's
# Players page needs it; it edits the same club player register either way.
# `manage_selections` is BetterSelect's umbrella: it satisfies every BetterSelect
# item, which is why a whole-module lock holds it and an item grant does not.
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
            C.MANAGE_PLAYERS, C.MANAGE_FIXTURES, C.MANAGE_SELECTIONS, *C.SELECT_ITEM_CAPS,
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

# Capabilities no limited person is ever given.
NEVER_LOCKED = (C.MANAGE_SETTINGS, C.MANAGE_USERS, C.RUN_HARD_REFRESH)

# Capabilities that only satisfy other capabilities and are never an item's own.
UMBRELLA_CAPS = (C.MANAGE_SELECTIONS,)


def _item(id, module, name, menu, caps, needs=(), view_caps=()):
    return {
        "id": id, "module": module, "name": name, "menu": menu,
        "caps": tuple(caps), "needs": tuple(needs), "view_caps": tuple(view_caps),
    }


# The menu items a Primary Admin can switch, in the order the Users screen lists
# them. `caps` are what Manage grants. At View the same capabilities are held and
# marked view only, unless the item has `view_caps` of its own (votes: seeing the
# results is a capability in its own right). `needs` are items that must be on for
# this one to work, as (item id, minimum level).
ITEMS: tuple[dict, ...] = (
    # BetterStats
    _item("stats.players", "stats", "Players", "Players, Import Players, and the Players page in BetterSelect", (C.MANAGE_PLAYERS,)),
    _item("stats.families", "stats", "Families", "Families", (C.MANAGE_FAMILIES,)),
    _item("stats.sync", "stats", "Data Sync", "Data Sync", (C.RUN_SYNC,)),
    _item("stats.imports", "stats", "Imports and manual entries", "Import Stats, Upload Scorecard, Manual Entries", (C.MANAGE_MANUAL_ENTRIES,)),
    _item("stats.milestones", "stats", "Milestones", "Milestones", (C.MANAGE_MILESTONES,)),
    _item("stats.cleanup", "stats", "Merge players and grades", "Merge Players, Grades & Competitions", (C.MANAGE_MERGES,)),
    _item("stats.awards", "stats", "Awards and records", "Awards, Award Types, Partnership Records", (C.MANAGE_AWARDS,)),
    _item("stats.yearbooks", "stats", "Yearbooks", "Yearbooks", (C.MANAGE_YEARBOOKS,)),
    _item("stats.reports", "stats", "Saved reports", "Saved Reports", (C.MANAGE_REPORTS,)),
    _item("stats.sponsors", "stats", "Sponsors", "Sponsors", (C.MANAGE_SPONSORS,)),
    _item("stats.clubroom", "stats", "Club Room Mode", "Club Room Mode", (C.MANAGE_CLUB_ROOM,)),
    _item("stats.website", "stats", "Public website", "Public club website content", (C.MANAGE_WEBSITE,)),
    # BetterSelect
    _item("select.fixtures", "select", "Fixtures", "Fixtures", (C.MANAGE_FIXTURES,)),
    _item("select.squads", "select", "Squads and ladders", "Squads, Ladders", (C.SELECT_SQUADS,)),
    _item("select.availability", "select", "Availability", "Availability", (C.SELECT_AVAILABILITY,)),
    _item("select.selection", "select", "Selection", "Selection, Selection Whiteboard", (C.SELECT_SELECTION,),
          needs=(("select.availability", LEVEL_VIEW),)),
    _item("select.nets", "select", "Nets", "Nets", (C.SELECT_NETS,)),
    _item("select.rotation", "select", "Junior Rotation", "Junior Rotation", (C.SELECT_ROTATION,)),
    _item("select.fines", "select", "Fines", "Fines", (C.SELECT_FINES,)),
    _item("select.rules", "select", "Settings and selection rules", "Settings, Selection rules", (C.SELECT_RULES,)),
    _item("select.audit", "select", "Audit history", "Audit History", (C.SELECT_AUDIT,)),
    _item("select.votes", "select", "Votes", "Votes", (C.MANAGE_VOTES, C.VIEW_VOTE_RESULTS), view_caps=(C.VIEW_VOTE_RESULTS,)),
    # BetterSocials, BetterIQ, BetterFantasyCricket
    _item("socials.designer", "socials", "Post designer", "Post Designer", (C.MANAGE_SOCIAL,)),
    _item("iq.all", "iq", "BetterIQ", "Every BetterIQ screen", (C.MANAGE_IQ,)),
    _item("fantasy.all", "fantasy", "BetterFantasyCricket", "Every fantasy admin screen", (C.MANAGE_FANTASY,)),
    # BetterAdmin
    _item("admin.directory", "admin", "Directory", "Directory", (C.MANAGE_MEMBERS,)),
    _item("admin.roster", "admin", "Roster and volunteers", "Roster, Roles, Activities, Role programs", (C.MANAGE_VOLUNTEERS,)),
    _item("admin.qualifications", "admin", "Qualifications", "Qualifications", (C.MANAGE_QUALIFICATIONS,)),
    _item("admin.committee", "admin", "Committee and events", "Committee, Events", (C.MANAGE_COMMITTEE,)),
    _item("admin.fees", "admin", "Fees", "Accounts, Payments, Membership tiers", (C.MANAGE_FEES,)),
    _item("admin.comms", "admin", "Emails", "Emails, Segments, Templates, Email settings", (C.MANAGE_COMMS,)),
    _item("admin.merch", "admin", "Stock", "Inventory, Online store", (C.MANAGE_MERCH,)),
    _item("admin.crm", "admin", "Sponsor and relationship tracker", "BetterCRM", (C.MANAGE_CRM,)),
    _item("admin.assets", "admin", "Facilities and assets", "Facilities & Assets", (C.MANAGE_ASSETS,)),
    _item("admin.diary", "admin", "Club diary", "Diary", (C.MANAGE_CLUB_DIARY,)),
)
ITEM_BY_ID: dict[str, dict] = {i["id"]: i for i in ITEMS}


def module_choices() -> list[dict]:
    """The modules a Primary Admin can lock someone to, for the Users screen."""
    return [
        {"key": key, "name": spec["name"], "blurb": spec["blurb"]}
        for key, spec in MODULE_ACCESS.items()
    ]


def item_catalogue() -> list[dict]:
    """Every module with its menu items, for the per-item screen. `needs` is what
    switching an item on also switches on, so the screen can say so before saving.
    `has_view` is false for an item whose View would equal Manage."""
    out = []
    for key, spec in MODULE_ACCESS.items():
        items = [
            {
                "id": i["id"], "name": i["name"], "menu": i["menu"],
                "needs": [{"item": n, "level": lv, "name": ITEM_BY_ID[n]["name"]} for n, lv in i["needs"]],
                "has_view": True,
            }
            for i in ITEMS if i["module"] == key
        ]
        out.append({"key": key, "name": spec["name"], "blurb": spec["blurb"], "items": items})
    return out


def caps_for_module(module_key: str | None) -> list[str]:
    """The capabilities a person locked to ``module_key`` holds, in the order the
    capability registry lists them. Empty for an unknown key (fail closed)."""
    spec = MODULE_ACCESS.get(module_key or "")
    if spec is None:
        return []
    wanted = set(spec["caps"])
    return [c for c in C.ALL_CAPABILITIES if c in wanted]


def resolve_grants(grants: dict | None) -> tuple[dict, list[dict]]:
    """Validate ``{item id: level}`` and add what each item needs.

    Returns (the grants to store, what was added). Raises ``AccessError`` for an
    unknown item or level. An item that needs another at a level the person has
    set lower (or not at all) raises it to that level, and says so in the second
    value so the screen can tell the Primary Admin."""
    final: dict[str, str] = {}
    for item_id, level in (grants or {}).items():
        if item_id not in ITEM_BY_ID:
            raise AccessError(f"Unknown menu item: {item_id}", 422)
        if level not in LEVELS:
            raise AccessError("Each item is View or Manage", 422)
        final[item_id] = level
    added: list[dict] = []
    changed = True
    while changed:
        changed = False
        for item_id in list(final):
            for need_id, need_level in ITEM_BY_ID[item_id]["needs"]:
                have = final.get(need_id)
                if have is None or (have == LEVEL_VIEW and need_level == LEVEL_MANAGE):
                    final[need_id] = need_level
                    added.append({
                        "item": need_id, "name": ITEM_BY_ID[need_id]["name"], "level": need_level,
                        "because": ITEM_BY_ID[item_id]["name"],
                    })
                    changed = True
    return final, added


def derive_caps(grants: dict | None) -> tuple[list[str], list[str]]:
    """(capabilities held, the subset held at view level only) for item grants,
    in the registry's order. Unknown items and levels grant nothing (fail closed)."""
    manage: set[str] = set()
    view: set[str] = set()
    inherent: set[str] = set()
    for item_id, level in (grants or {}).items():
        spec = ITEM_BY_ID.get(item_id)
        if spec is None:
            continue
        if level == LEVEL_MANAGE:
            manage |= set(spec["caps"])
        elif level == LEVEL_VIEW:
            if spec["view_caps"]:
                inherent |= set(spec["view_caps"])
            else:
                view |= set(spec["caps"])
    view_only = view - manage - inherent
    held = manage | view | inherent
    order = [c for c in C.ALL_CAPABILITIES]
    return [c for c in order if c in held], [c for c in order if c in view_only]


def _uid(value) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _grants_of(row_value) -> dict:
    if isinstance(row_value, str):
        try:
            row_value = json.loads(row_value)
        except ValueError:
            return {}
    return dict(row_value or {})


async def get_access(db: AsyncSession, user_id, club_id) -> dict | None:
    """The limit on this person at this club, or None when they are not limited."""
    row = (await db.execute(
        text("SELECT mode, module_key, grants FROM user_access WHERE user_id = :u AND club_id = :c"),
        {"u": _uid(user_id), "c": _uid(club_id)},
    )).first()
    if row is None:
        return None
    return {"mode": row.mode, "module_key": row.module_key, "grants": _grants_of(row.grants)}


async def access_for_club(db: AsyncSession, club_id) -> dict[str, dict]:
    """Every limited person at a club, keyed by user id, for the Users list."""
    rows = (await db.execute(
        text("SELECT user_id, mode, module_key, grants FROM user_access WHERE club_id = :c"),
        {"c": _uid(club_id)},
    )).all()
    return {
        str(r.user_id): {"mode": r.mode, "module_key": r.module_key, "grants": _grants_of(r.grants)}
        for r in rows
    }


async def _membership(db: AsyncSession, user_id, club_id):
    return (await db.execute(
        text("SELECT id, role, is_primary_admin FROM club_memberships "
             "WHERE user_id = :u AND club_id = :c"),
        {"u": _uid(user_id), "c": _uid(club_id)},
    )).first()


async def _limit_target(db: AsyncSession, user_id, club_id):
    """The membership of a person who may be limited, or a refusal."""
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
    return m


async def _write(db: AsyncSession, *, user_id, club_id, mode, module_key, grants, caps, view_only, by_user_id):
    await db.execute(
        text(
            "INSERT INTO user_access (user_id, club_id, mode, module_key, grants, updated_by_user_id) "
            "VALUES (:u, :c, :mode, :mod, CAST(:grants AS JSONB), :by) "
            "ON CONFLICT (user_id, club_id) DO UPDATE SET mode = EXCLUDED.mode, "
            "module_key = EXCLUDED.module_key, grants = EXCLUDED.grants, "
            "updated_by_user_id = EXCLUDED.updated_by_user_id, updated_at = NOW()"
        ),
        {"u": _uid(user_id), "c": _uid(club_id), "mode": mode, "mod": module_key,
         "grants": json.dumps(grants), "by": _uid(by_user_id) if by_user_id else None},
    )
    await db.execute(
        text("UPDATE club_memberships SET role = :role, capabilities = CAST(:caps AS JSONB), "
             "view_only_caps = CAST(:view AS JSONB) WHERE user_id = :u AND club_id = :c"),
        {"role": LOCKED_ROLE, "caps": json.dumps(caps), "view": json.dumps(view_only),
         "u": _uid(user_id), "c": _uid(club_id)},
    )


async def lock_to_module(db: AsyncSession, *, user_id, club_id, module_key: str, by_user_id=None) -> list[str]:
    """Lock a person to one module. Returns the capabilities they now hold.

    Caller commits. Raises ``AccessError`` for a refusal."""
    if module_key not in MODULE_ACCESS:
        raise AccessError("Pick one of the listed modules", 422)
    await _limit_target(db, user_id, club_id)
    caps = caps_for_module(module_key)
    await _write(db, user_id=user_id, club_id=club_id, mode=MODE_MODULE, module_key=module_key,
                 grants={}, caps=caps, view_only=[], by_user_id=by_user_id)
    return caps


async def set_item_access(db: AsyncSession, *, user_id, club_id, grants: dict, by_user_id=None) -> dict:
    """Give a person a choice of menu items, each at View or Manage.

    Returns {"grants": what was stored, "added": prerequisites switched on,
    "capabilities": [...], "view_only": [...]}. Caller commits. Raises
    ``AccessError`` for a refusal, including an empty choice (a person who can
    open nothing is a mistake: choose Everything or one item)."""
    final, added = resolve_grants(grants)
    if not final:
        raise AccessError("Pick at least one menu item, or choose Everything", 422)
    await _limit_target(db, user_id, club_id)
    caps, view_only = derive_caps(final)
    await _write(db, user_id=user_id, club_id=club_id, mode=MODE_ITEMS, module_key=None,
                 grants=final, caps=caps, view_only=view_only, by_user_id=by_user_id)
    return {"grants": final, "added": added, "capabilities": caps, "view_only": view_only}


async def unlock(db: AsyncSession, *, user_id, club_id) -> bool:
    """Take the limit off: back to a full Club Admin. True when there was one.

    Caller commits. A person with no ``user_access`` row is left exactly as they
    are, so a legacy `club_member` allowlist is never widened by this."""
    res = await db.execute(
        text("DELETE FROM user_access WHERE user_id = :u AND club_id = :c RETURNING 1"),
        {"u": _uid(user_id), "c": _uid(club_id)},
    )
    if res.first() is None:
        return False
    await db.execute(
        text("UPDATE club_memberships SET role = :role, capabilities = '[]'::jsonb, "
             "view_only_caps = '[]'::jsonb WHERE user_id = :u AND club_id = :c AND role = :locked"),
        {"role": FULL_ROLE, "locked": LOCKED_ROLE, "u": _uid(user_id), "c": _uid(club_id)},
    )
    return True


def caps_for_access(access: dict) -> tuple[list[str], list[str]]:
    """The two cached lists for one stored access row, from today's catalogue."""
    if access.get("mode") == MODE_ITEMS:
        final, _ = _safe_resolve(access.get("grants"))
        return derive_caps(final)
    return caps_for_module(access.get("module_key")), []


def _safe_resolve(grants) -> tuple[dict, list]:
    """Like resolve_grants for a stored row: an item the catalogue no longer has is
    dropped instead of refused, so a removed item cannot stop the boot."""
    known = {k: v for k, v in (grants or {}).items() if k in ITEM_BY_ID and v in LEVELS}
    return resolve_grants(known)


async def resync_module_caps(db: AsyncSession) -> int:
    """Rewrite the cached capability lists of every limited person from the
    catalogue. Runs on every boot. Idempotent: it only writes a row whose lists
    differ. Returns the number of rows rewritten."""
    rows = (await db.execute(
        text(
            "SELECT ua.user_id, ua.club_id, ua.mode, ua.module_key, ua.grants, "
            "cm.capabilities, cm.view_only_caps, cm.role "
            "FROM user_access ua JOIN club_memberships cm "
            "ON cm.user_id = ua.user_id AND cm.club_id = ua.club_id "
            "WHERE ua.mode IN (:m1, :m2)"
        ),
        {"m1": MODE_MODULE, "m2": MODE_ITEMS},
    )).all()
    changed = 0
    for r in rows:
        caps, view_only = caps_for_access({"mode": r.mode, "module_key": r.module_key, "grants": _grants_of(r.grants)})
        if (r.role == LOCKED_ROLE and list(r.capabilities or []) == caps
                and list(r.view_only_caps or []) == view_only):
            continue
        await db.execute(
            text("UPDATE club_memberships SET role = :role, capabilities = CAST(:caps AS JSONB), "
                 "view_only_caps = CAST(:view AS JSONB) WHERE user_id = :u AND club_id = :c"),
            {"role": LOCKED_ROLE, "caps": json.dumps(caps), "view": json.dumps(view_only),
             "u": r.user_id, "c": r.club_id},
        )
        changed += 1
    return changed


def describe(access: dict | None) -> dict:
    """The shape the API and the Users screen use for one person's access.

    `modules` lists the modules the person can open anything in, for the
    dashboard, and is None for full access."""
    if not access:
        return {"mode": "full", "module_key": None, "module_name": None, "grants": {}, "modules": None, "item_count": None}
    if access.get("mode") == MODE_ITEMS:
        grants = {k: v for k, v in (access.get("grants") or {}).items() if k in ITEM_BY_ID}
        modules = []
        for item_id in grants:
            m = ITEM_BY_ID[item_id]["module"]
            if m not in modules:
                modules.append(m)
        return {"mode": MODE_ITEMS, "module_key": None, "module_name": None, "grants": grants,
                "modules": modules, "item_count": len(grants)}
    spec = MODULE_ACCESS.get(access.get("module_key") or "")
    return {
        "mode": access["mode"],
        "module_key": access.get("module_key"),
        "module_name": spec["name"] if spec else None,
        "grants": {},
        "modules": [access.get("module_key")] if spec else [],
        "item_count": None,
    }


def known_module_keys() -> Iterable[str]:
    return MODULE_ACCESS.keys()
