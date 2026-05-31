"""Keep team_members in step with a player's single assigned squad.

`players.squad_team_id` is the one assigned selection-pool squad shown on the
Squads board (a single value). `team_members` is the multi-squad list that the
Availability and Selection screens resolve their "Squad" filter from. Mirroring
an assignment into `team_members` makes "Squad" resolve to the same set on every
BetterSelect screen.
"""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import TeamMember


async def sync_squad_membership(
    db: AsyncSession,
    organisation_id: uuid.UUID,
    player_id: uuid.UUID,
    old_team_id: Optional[uuid.UUID],
    new_team_id: Optional[uuid.UUID],
    added_by: Optional[uuid.UUID] = None,
) -> None:
    """Mirror a squad_team_id change into team_members. Does NOT commit — the
    caller owns the transaction.

    The assigned squad is authoritative for its own membership row:
      - assign / reassign  → ensure a row for ``new_team_id`` exists;
      - reassign / unassign → drop the row for ``old_team_id``.
    Manual memberships to *other* teams are left untouched, so an admin can
    still pool a player into several squads by hand.
    """
    if old_team_id == new_team_id:
        return
    if old_team_id is not None:
        stale = await db.get(TeamMember, {"team_id": old_team_id, "player_id": player_id})
        if stale is not None:
            await db.delete(stale)
    if new_team_id is not None:
        existing = await db.get(TeamMember, {"team_id": new_team_id, "player_id": player_id})
        if existing is None:
            db.add(TeamMember(
                team_id=new_team_id,
                player_id=player_id,
                organisation_id=organisation_id,
                added_by=added_by,
            ))
