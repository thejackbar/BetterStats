"""Primary / owner admin helpers (migration 118).

Each club has at most one primary admin (partial unique index uq_membership_primary).
The first club_admin created for a club becomes primary; it's reassignable to another
club_admin (by the current primary or a super admin). Only the primary may request a
paid module subscription.
"""
from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import ClubMembership


async def has_primary_admin(db: AsyncSession, club_id) -> bool:
    row = await db.execute(
        select(ClubMembership.id).where(
            ClubMembership.club_id == club_id,
            ClubMembership.is_primary_admin.is_(True),
        ).limit(1)
    )
    return row.first() is not None


async def ensure_primary_admin(db: AsyncSession, club_id) -> None:
    """Mark the earliest club_admin as primary when the club has none yet. No-op if a
    primary already exists. Call after creating a club_admin membership."""
    if await has_primary_admin(db, club_id):
        return
    row = await db.execute(
        select(ClubMembership).where(
            ClubMembership.club_id == club_id,
            ClubMembership.role == "club_admin",
        ).order_by(ClubMembership.created_at.asc(), ClubMembership.id.asc()).limit(1)
    )
    m = row.scalar_one_or_none()
    if m is not None:
        m.is_primary_admin = True


async def set_primary_admin(db: AsyncSession, club_id, user_id):
    """Transfer the primary flag to ``user_id`` (must be a club_admin of this club).
    Clears every other primary first so the one-per-club index can't be violated.
    Returns the new primary membership. Raises ValueError if the target isn't eligible."""
    target = (await db.execute(
        select(ClubMembership).where(
            ClubMembership.club_id == club_id,
            ClubMembership.user_id == user_id,
        )
    )).scalar_one_or_none()
    if target is None:
        raise ValueError("That user is not a member of this club")
    if target.role != "club_admin":
        raise ValueError("Only a club admin can be the primary admin")
    # Clear all primaries on this club in a single statement (≤1 true at every step),
    # then set the target — keeps the partial unique index satisfied.
    await db.execute(
        update(ClubMembership)
        .where(ClubMembership.club_id == club_id, ClubMembership.is_primary_admin.is_(True))
        .values(is_primary_admin=False)
    )
    target.is_primary_admin = True
    return target
