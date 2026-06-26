"""Global email suppression + the BetterComms send gate.

``email_suppressions`` is the one cross-club table: a hard bounce or complaint is
a fact about the mailbox, so it blocks the address everywhere. These helpers are
the single point the rest of the app calls before sending, and the bulk audience
query in routers/comms.py applies the same rules in SQL.

See services/comms_policy.py for the category policy and
docs/bettercomms-architecture.md for the model.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select, func, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import EmailSuppression, CommsContact
from app.services import comms_policy


def _norm(email: str) -> str:
    return (email or "").strip().lower()


async def suppression_reason(session: AsyncSession, email: str) -> Optional[str]:
    """The global suppression reason for an address (hard_bounce | complaint |
    manual), or None if not suppressed."""
    e = _norm(email)
    if not e:
        return None
    return await session.scalar(
        select(EmailSuppression.reason).where(func.lower(EmailSuppression.email) == e))


async def is_suppressed(session: AsyncSession, email: str) -> bool:
    return (await suppression_reason(session, email)) is not None


async def add_suppression(session: AsyncSession, email: str, reason: str,
                          source: str | None = None, detail: str | None = None) -> bool:
    """Idempotent upsert into the global list. Returns True if a NEW row was
    added. Does not commit (caller owns the transaction)."""
    e = _norm(email)
    if not e:
        return False
    stmt = (
        pg_insert(EmailSuppression)
        .values(email=e, reason=reason, source=source, detail=detail)
        .on_conflict_do_nothing(index_elements=["email"])
        .returning(EmailSuppression.id)
    )
    new_id = (await session.execute(stmt)).scalar_one_or_none()
    return new_id is not None


async def remove_suppression(session: AsyncSession, email: str) -> int:
    """Manual un-suppress (e.g. the member fixed their mailbox). Returns rows
    removed. Does not commit."""
    e = _norm(email)
    if not e:
        return 0
    res = await session.execute(
        delete(EmailSuppression).where(func.lower(EmailSuppression.email) == e))
    return res.rowcount or 0


async def deliverable(session: AsyncSession, *, email: str, organisation_id,
                      category: str) -> tuple[bool, Optional[str]]:
    """The send gate. Returns (ok, blocked_reason). Reusable by transactional /
    operational senders, not just campaigns.

    Order: global suppression (hard bounce blocks all; complaint blocks all but
    transactional), then the per-club comms_contact state (unsubscribed, bounced,
    complained, excluded), then the per-person preference for the category.
    """
    e = _norm(email)
    if not e:
        return False, "no_email"
    cat = comms_policy.normalise_category(category)

    reason = await suppression_reason(session, e)
    if reason == "hard_bounce" and comms_policy.blocks_hard_bounce(cat):
        return False, "hard_bounce"
    if reason == "complaint" and comms_policy.blocks_on_complaint(cat):
        return False, "complaint"
    if reason == "manual":
        return False, "suppressed"

    contact = await session.scalar(select(CommsContact).where(
        CommsContact.organisation_id == organisation_id,
        func.lower(CommsContact.email) == e))
    if contact is not None:
        if contact.bounced:
            return False, "bounced"
        if contact.complained and comms_policy.blocks_on_complaint(cat):
            return False, "complaint"
        if contact.excluded:
            return False, "excluded"
        if not contact.subscribed and comms_policy.blocks_on_optout(cat):
            return False, "unsubscribed"
        if not comms_policy.preference_allows(contact.preferences, cat):
            return False, "preference_off"
    return True, None
