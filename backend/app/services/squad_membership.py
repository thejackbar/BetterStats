"""Squad membership: team_members is authoritative, squad_team_id is derived.

A player can sit in several squads at once — a fringe 1st XI player who is also
a Colt and plays T20 belongs to the 1st XI, 2nd XI, Colts and T20 squads. The
full set lives in ``team_members`` (a composite-PK ``(team_id, player_id)`` M2M
that has always been able to hold several rows per player).

``players.squad_team_id`` is kept, but it is now a DERIVED "primary squad" — the
player's top member team (lowest positive ``sequence``; an unranked squad is
ranked last; the name breaks a tie). It is recomputed on every membership change
by ``recompute_primary_squad`` so the ~15 readers of the single column (BetterComms
segments, Fantasy, BetterIQ, onboarding, the clone script, the Directory panel)
keep working with no change — a player still has one well-defined headline squad.

Every squad write goes through the helpers here, so the derived invariant
(``squad_team_id`` == the primary of ``team_members``) can never drift. The write
paths are pure ``text()`` SQL so they behave the same whether the caller reached
them from the ORM or from raw SQL (services/directory.py stays out of the ORM
graph), and so a stale ORM copy of ``squad_team_id`` is never the source of truth.
"""
from __future__ import annotations

import uuid
from typing import Iterable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# The primary squad is the member team with the best rank: a ranked team
# (sequence > 0) beats an unranked one, then the lowest sequence wins, then the
# name settles it so the choice is deterministic. NULL when the player is in no
# squad. One statement so it works from every write path.
_RECOMPUTE_PRIMARY_SQL = text(
    "UPDATE players SET squad_team_id = ("
    "  SELECT tm.team_id FROM team_members tm"
    "  JOIN teams t ON t.id = tm.team_id"
    "  WHERE tm.player_id = :pid AND tm.organisation_id = :org"
    "  ORDER BY (CASE WHEN COALESCE(t.sequence, 0) > 0 THEN 0 ELSE 1 END),"
    "           COALESCE(t.sequence, 0), lower(t.name)"
    "  LIMIT 1"
    ") WHERE id = :pid AND organisation_id = :org"
)


async def recompute_primary_squad(
    db: AsyncSession, organisation_id: uuid.UUID, player_id: uuid.UUID
) -> None:
    """Set ``players.squad_team_id`` to the player's top member squad (or NULL).

    Does NOT commit — the caller owns the transaction. Autoflushes any pending
    ORM change to the row first, so this always wins as the final value."""
    await db.execute(_RECOMPUTE_PRIMARY_SQL, {"pid": player_id, "org": organisation_id})


async def member_team_ids(
    db: AsyncSession, organisation_id: uuid.UUID, player_id: uuid.UUID
) -> list[uuid.UUID]:
    """Every squad the player is a member of, top-ranked first."""
    rows = (await db.execute(
        text(
            "SELECT tm.team_id FROM team_members tm "
            "JOIN teams t ON t.id = tm.team_id "
            "WHERE tm.player_id = :pid AND tm.organisation_id = :org "
            "ORDER BY (CASE WHEN COALESCE(t.sequence, 0) > 0 THEN 0 ELSE 1 END), "
            "COALESCE(t.sequence, 0), lower(t.name)"
        ),
        {"pid": player_id, "org": organisation_id},
    )).all()
    return [r[0] for r in rows]


async def _delete_membership(db, organisation_id, player_id, team_id) -> None:
    await db.execute(
        text(
            "DELETE FROM team_members "
            "WHERE team_id = :t AND player_id = :pid AND organisation_id = :org"
        ),
        {"t": team_id, "pid": player_id, "org": organisation_id},
    )


async def _add_membership(db, organisation_id, player_id, team_id, added_by) -> None:
    await db.execute(
        text(
            "INSERT INTO team_members (team_id, player_id, organisation_id, added_by) "
            "VALUES (:t, :pid, :org, :by) ON CONFLICT DO NOTHING"
        ),
        {"t": team_id, "pid": player_id, "org": organisation_id, "by": added_by},
    )


async def add_squad_memberships(
    db: AsyncSession,
    organisation_id: uuid.UUID,
    player_id: uuid.UUID,
    team_ids: Iterable[uuid.UUID],
    added_by: Optional[uuid.UUID] = None,
) -> None:
    """Add the player to each squad, keeping every squad they are already in.

    Additive — this is how a player is pooled into a SECOND squad (the per-squad
    "Add players" button, the card's "+ Add to squad" control, and auto-assign).
    Does NOT commit."""
    added = False
    for tid in team_ids:
        if tid is None:
            continue
        await _add_membership(db, organisation_id, player_id, tid, added_by)
        added = True
    if added:
        await recompute_primary_squad(db, organisation_id, player_id)


async def remove_squad_memberships(
    db: AsyncSession,
    organisation_id: uuid.UUID,
    player_id: uuid.UUID,
    team_ids: Iterable[uuid.UUID],
) -> None:
    """Remove the player from each named squad, leaving the rest. Does NOT commit."""
    removed = False
    for tid in team_ids:
        if tid is None:
            continue
        await _delete_membership(db, organisation_id, player_id, tid)
        removed = True
    if removed:
        await recompute_primary_squad(db, organisation_id, player_id)


async def move_squad_membership(
    db: AsyncSession,
    organisation_id: uuid.UUID,
    player_id: uuid.UUID,
    from_team_id: Optional[uuid.UUID],
    to_team_id: Optional[uuid.UUID],
    added_by: Optional[uuid.UUID] = None,
) -> None:
    """Move the player from one squad to another (the board's drag). Removes the
    source membership and adds the target, leaving every OTHER squad untouched.
    A None source is a plain add; a None target is a plain remove. Does NOT commit."""
    if from_team_id == to_team_id:
        return
    if from_team_id is not None:
        await _delete_membership(db, organisation_id, player_id, from_team_id)
    if to_team_id is not None:
        await _add_membership(db, organisation_id, player_id, to_team_id, added_by)
    await recompute_primary_squad(db, organisation_id, player_id)


async def set_squad_memberships(
    db: AsyncSession,
    organisation_id: uuid.UUID,
    player_id: uuid.UUID,
    team_ids: Iterable[uuid.UUID],
    added_by: Optional[uuid.UUID] = None,
) -> None:
    """Replace the player's whole set of squads with exactly ``team_ids``.

    Backs the profile editor's squad multi-select. Does NOT commit."""
    want = {t for t in team_ids if t is not None}
    have = set(await member_team_ids(db, organisation_id, player_id))
    for tid in have - want:
        await _delete_membership(db, organisation_id, player_id, tid)
    for tid in want - have:
        await _add_membership(db, organisation_id, player_id, tid, added_by)
    await recompute_primary_squad(db, organisation_id, player_id)


async def clear_all_squad_memberships(
    db: AsyncSession, organisation_id: uuid.UUID, player_id: uuid.UUID
) -> None:
    """Take the player out of every squad. Used when a player is marked inactive —
    an inactive player is not in this season's pool, so leaving them filed in any
    squad is what makes the Squads board disagree with the roster. Does NOT commit."""
    await db.execute(
        text("DELETE FROM team_members WHERE player_id = :pid AND organisation_id = :org"),
        {"pid": player_id, "org": organisation_id},
    )
    await db.execute(
        text("UPDATE players SET squad_team_id = NULL WHERE id = :pid AND organisation_id = :org"),
        {"pid": player_id, "org": organisation_id},
    )


async def sync_squad_membership(
    db: AsyncSession,
    organisation_id: uuid.UUID,
    player_id: uuid.UUID,
    old_team_id: Optional[uuid.UUID],
    new_team_id: Optional[uuid.UUID],
    added_by: Optional[uuid.UUID] = None,
) -> None:
    """Back-compat shim for the single-squad writers (the profile importer).

    Applies the old→new delta to ``team_members`` and recomputes the primary, so
    a caller that still thinks in one squad keeps the derived invariant. New code
    should call the add/move/remove/set helpers directly."""
    await move_squad_membership(
        db, organisation_id, player_id, old_team_id, new_team_id, added_by
    )
