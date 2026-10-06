"""Linked clubs: the one place that knows which clubs belong together.

A Super Admin links two or more clubs (``club_links``, migration 322). A Club
Admin of any club in a group may then work in any other club of that group:
they keep their one home membership (an account is still linked to exactly one
club, migration 017) and choose an acted-as club through ``users.active_club_id``,
the same column a Super Admin uses. ``routers/auth.effective_club_id`` honours
that choice for a Club Admin only while ``can_switch_to`` says yes, so unlinking
two clubs, deactivating one or archiving it ends the switch on the very next
request without anybody having to clear a column.

Rules kept here:

* A club is in at most one group. Linking a club to a group extends the group;
  linking two clubs that already sit in different groups is refused rather than
  quietly merging two groups somebody built on purpose.
* A group has two or more members. Unlinking down to one removes the last row.
* Only ``club_admin`` switches. A ``club_member`` is given a few screens at their
  own club and nothing more.
* Fail closed: an unknown, unlinked, inactive or archived target is "no".
"""
from __future__ import annotations

import uuid
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class ClubLinkError(Exception):
    """A refused link or unlink. ``status`` is the HTTP code the router sends."""

    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.message = message
        self.status = status


def _uid(value) -> uuid.UUID | None:
    if value is None:
        return None
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


async def group_of(db: AsyncSession, org_id) -> uuid.UUID | None:
    row = (await db.execute(
        text("SELECT group_id FROM club_links WHERE organisation_id = :o"),
        {"o": _uid(org_id)},
    )).first()
    return row[0] if row else None


async def can_switch_to(db: AsyncSession, home_id, target_id) -> bool:
    """True when a Club Admin whose home club is ``home_id`` may act in
    ``target_id``: the two are different clubs in one group, and the target is
    active and not archived (the same bar a Club Admin passes to log in)."""
    home, target = _uid(home_id), _uid(target_id)
    if home is None or target is None or home == target:
        return False
    row = (await db.execute(
        text(
            "SELECT 1 FROM club_links a "
            "JOIN club_links b ON b.group_id = a.group_id "
            "JOIN organisations o ON o.id = b.organisation_id "
            "WHERE a.organisation_id = :home AND b.organisation_id = :target "
            "AND o.is_active IS TRUE AND o.archived_at IS NULL"
        ),
        {"home": home, "target": target},
    )).first()
    return row is not None


async def covers_club(db: AsyncSession, home_id, org_id) -> bool:
    """True when ``org_id`` is the user's home club or a club linked to it.

    For the places that ask "is this user a club admin of the club the request
    is scoped to" by looking the membership up by club id: a switched-in admin
    has no membership row there, but the link is what entitles them."""
    home, org = _uid(home_id), _uid(org_id)
    if home is None or org is None:
        return False
    if home == org:
        return True
    row = (await db.execute(
        text(
            "SELECT 1 FROM club_links a JOIN club_links b ON b.group_id = a.group_id "
            "WHERE a.organisation_id = :home AND b.organisation_id = :org"
        ),
        {"home": home, "org": org},
    )).first()
    return row is not None


async def switchable_clubs(db: AsyncSession, home_id) -> list[dict]:
    """The clubs a Club Admin of ``home_id`` can work in, the home club first
    and then the rest by name. Empty when the club is not linked to another
    club that is open for work, which is what hides the switcher."""
    home = _uid(home_id)
    if home is None:
        return []
    rows = (await db.execute(
        text(
            "SELECT o.id, o.name, o.slug, (o.id = :home) AS is_home "
            "FROM club_links a JOIN club_links b ON b.group_id = a.group_id "
            "JOIN organisations o ON o.id = b.organisation_id "
            "WHERE a.organisation_id = :home "
            "AND (o.id = :home OR (o.is_active IS TRUE AND o.archived_at IS NULL)) "
            "ORDER BY (o.id = :home) DESC, lower(o.name), o.id"
        ),
        {"home": home},
    )).all()
    if len(rows) < 2:
        return []
    return [
        {"id": str(r.id), "name": r.name, "slug": r.slug, "is_home": bool(r.is_home)}
        for r in rows
    ]


async def list_groups(db: AsyncSession) -> list[dict]:
    """Every group with its member clubs, for the Super Admin screen."""
    rows = (await db.execute(
        text(
            "SELECT l.group_id, l.created_at, o.id, o.name, o.slug, o.is_active, "
            "(o.archived_at IS NOT NULL) AS archived "
            "FROM club_links l JOIN organisations o ON o.id = l.organisation_id "
            "ORDER BY l.group_id, lower(o.name), o.id"
        )
    )).all()
    groups: dict[uuid.UUID, dict] = {}
    for r in rows:
        g = groups.setdefault(r.group_id, {"group_id": str(r.group_id), "linked_at": None, "clubs": []})
        if g["linked_at"] is None or (r.created_at and r.created_at.isoformat() < g["linked_at"]):
            g["linked_at"] = r.created_at.isoformat() if r.created_at else None
        g["clubs"].append({
            "id": str(r.id), "name": r.name, "slug": r.slug,
            "is_active": bool(r.is_active), "archived": bool(r.archived),
        })
    return sorted(groups.values(), key=lambda g: g["clubs"][0]["name"].lower())


async def _require_linkable(db: AsyncSession, org_id: uuid.UUID) -> dict:
    row = (await db.execute(
        text("SELECT id, name, archived_at FROM organisations WHERE id = :o"),
        {"o": org_id},
    )).first()
    if row is None:
        raise ClubLinkError("Club not found", 404)
    if row.archived_at is not None:
        raise ClubLinkError(f"{row.name} is archived, so it cannot be linked", 409)
    return {"id": row.id, "name": row.name}


async def link_clubs(db: AsyncSession, club_a, club_b, by_user_id=None) -> dict:
    """Link two clubs. Returns the group's id and the clubs it now holds.

    Caller commits. Raises ``ClubLinkError`` for a refusal."""
    a, b = _uid(club_a), _uid(club_b)
    if a is None or b is None:
        raise ClubLinkError("Pick two clubs to link", 422)
    if a == b:
        raise ClubLinkError("A club cannot be linked to itself", 422)
    info_a = await _require_linkable(db, a)
    info_b = await _require_linkable(db, b)
    ga, gb = await group_of(db, a), await group_of(db, b)
    if ga is not None and ga == gb:
        raise ClubLinkError(f"{info_a['name']} and {info_b['name']} are already linked", 409)
    if ga is not None and gb is not None:
        raise ClubLinkError(
            f"{info_a['name']} and {info_b['name']} are each linked to other clubs already. "
            "Unlink one of them first.", 409)
    group = ga or gb or uuid.uuid4()
    for org in (a, b):
        await db.execute(
            text(
                "INSERT INTO club_links (organisation_id, group_id, linked_by_user_id) "
                "VALUES (:o, :g, :u) ON CONFLICT (organisation_id) DO NOTHING"
            ),
            {"o": org, "g": group, "u": _uid(by_user_id)},
        )
    return {"group_id": str(group), "added": [str(a), str(b)]}


async def unlink_club(db: AsyncSession, org_id) -> list[uuid.UUID]:
    """Take a club out of its group. A group left with one club is dissolved.

    Returns the ids of every club whose link row was removed (the one asked for
    and, when the group fell to a single club, that club too). Caller commits.
    Raises ``ClubLinkError`` when the club is not linked."""
    org = _uid(org_id)
    group = await group_of(db, org)
    if group is None:
        raise ClubLinkError("That club is not linked to any other club", 404)
    removed = [org]
    await db.execute(text("DELETE FROM club_links WHERE organisation_id = :o"), {"o": org})
    rest = (await db.execute(
        text("SELECT organisation_id FROM club_links WHERE group_id = :g"), {"g": group}
    )).scalars().all()
    if len(rest) == 1:
        await db.execute(text("DELETE FROM club_links WHERE group_id = :g"), {"g": group})
        removed.append(rest[0])
    await clear_stale_switches(db)
    return removed


async def clear_stale_switches(db: AsyncSession) -> int:
    """Reset ``users.active_club_id`` for every non-super user whose chosen club
    is no longer linked to their home club. ``effective_club_id`` already
    ignores such a value, so this is tidiness: it stops a later re-link from
    silently resuming a switch the admin made long ago. Super admins are never
    touched, the column is theirs."""
    res = await db.execute(text(
        "UPDATE users u SET active_club_id = NULL FROM club_memberships cm "
        "WHERE cm.user_id = u.id AND cm.role <> 'super_admin' "
        "AND u.active_club_id IS NOT NULL AND u.active_club_id <> cm.club_id "
        "AND NOT EXISTS (SELECT 1 FROM club_links a JOIN club_links b ON b.group_id = a.group_id "
        "                WHERE a.organisation_id = cm.club_id AND b.organisation_id = u.active_club_id)"
    ))
    return res.rowcount or 0


def ids_to_str(ids: Iterable) -> list[str]:
    return [str(i) for i in ids]
