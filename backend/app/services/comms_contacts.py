"""Upserting a BetterComms contact — the one definition.

``comms_contacts`` is unique on (organisation_id, email), so adding someone who
is already on file lands on their existing row. That is what makes the whole
thing safe to run repeatedly, and it carries one rule that must never be
relaxed: **a suppressed address is never resurrected**. An unsubscribe, a hard
bounce or a spam complaint flips ``subscribed`` / ``bounced`` / ``complained``,
and re-adding the person must leave those exactly as they are — the Spam Act
gives them a working opt-out, and an upsert that quietly cleared it would take
it away.

Everything else FILLS rather than clobbers: a name, a player/member link or a
directory club is set only when the row does not already have one, so a value a
super admin typed by hand always wins over one derived here.

Lives in a service rather than in routers/comms.py because it is now called from
outside a request too (see services/admin_contact_list.py). The router delegates
to it, so there is one copy of the suppression rule rather than two.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import CommsContact


async def upsert_contact(session: AsyncSession, organisation_id, email: str,
                         name: Optional[str], source: str, *,
                         player_id=None, member_id=None,
                         marketing_club_id=None) -> str:
    """Insert or update a contact by (org, email). Returns 'added' | 'updated'.
    Never resurrects a suppressed address — subscribed/bounced are left as-is.
    Does not commit; the caller owns the transaction."""
    existing = (await session.execute(select(CommsContact).where(
        CommsContact.organisation_id == organisation_id, CommsContact.email == email
    ))).scalar_one_or_none()
    if existing:
        if name and not existing.name:
            existing.name = name
        if player_id and not existing.player_id:
            existing.player_id = player_id
        if member_id and not existing.member_id:
            existing.member_id = member_id
        if marketing_club_id and not existing.marketing_club_id:
            existing.marketing_club_id = marketing_club_id
        existing.updated_at = datetime.now(timezone.utc)
        return "updated"
    session.add(CommsContact(
        organisation_id=organisation_id, email=email, name=name, source=source,
        player_id=player_id, member_id=member_id, marketing_club_id=marketing_club_id,
    ))
    return "added"
