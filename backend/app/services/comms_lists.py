"""BetterComms — static-list membership helpers shared across the app.

A contact's presence on a static list lives in ``comms_list_members``. When a
recipient opts out (one-click unsubscribe) or a mailbox is hard-bounced / marks
an email as spam, the send gate already skips the address (see
services/email_suppression.py). These helpers additionally *drop the list
membership itself* so a suppressed contact stops showing up on any list.

  * ``auto_remove_from_all_lists`` — the automatic path (unsubscribe / bounce /
    complaint). It only touches contacts whose organisation has
    ``comms_auto_remove_unsubscribed`` enabled (the Settings checkbox, default
    on). Targets contacts by explicit ids OR by email address.
  * ``remove_from_all_lists`` — the manual, unconditional path (the Contacts
    page "Remove from all lists" bulk action). Org-scoped, ignores the flag.

Neither commits — the caller owns the transaction.
"""
from __future__ import annotations

import uuid
from typing import Iterable, Optional

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import CommsContact, CommsListMember, Organisation


def _uuids(raw_ids: Iterable) -> list:
    out = []
    for raw in (raw_ids or []):
        try:
            out.append(uuid.UUID(str(raw)))
        except (ValueError, TypeError):
            continue
    return out


async def auto_remove_from_all_lists(
    session: AsyncSession,
    *,
    contact_ids: Optional[Iterable] = None,
    email: Optional[str] = None,
    organisation_id=None,
) -> int:
    """Drop matching contacts from every static list, but ONLY for contacts whose
    organisation has ``comms_auto_remove_unsubscribed`` enabled. Set-based; does
    not commit. Returns the number of membership rows removed.

    Provide either ``contact_ids`` (explicit) or ``email`` (every contact holding
    that address, optionally narrowed to one ``organisation_id`` — e.g. a
    complaint attributed to a known sending club). A hard bounce is a fact about
    the mailbox, so it passes ``email`` with no ``organisation_id`` to reach every
    club that holds it.
    """
    sub = (
        select(CommsContact.id)
        .join(Organisation, Organisation.id == CommsContact.organisation_id)
        .where(Organisation.comms_auto_remove_unsubscribed.is_(True))
    )
    if contact_ids is not None:
        ids = _uuids(contact_ids)
        if not ids:
            return 0
        sub = sub.where(CommsContact.id.in_(ids))
    elif email is not None:
        e = (email or "").strip().lower()
        if not e:
            return 0
        sub = sub.where(func.lower(CommsContact.email) == e)
        if organisation_id is not None:
            sub = sub.where(CommsContact.organisation_id == organisation_id)
    else:
        return 0

    res = await session.execute(
        delete(CommsListMember).where(CommsListMember.contact_id.in_(sub)))
    return res.rowcount or 0


async def remove_from_all_lists(
    session: AsyncSession, contact_ids: Iterable, organisation_id
) -> tuple[int, int]:
    """Unconditionally drop the given contacts from every static list they're in
    (the manual Contacts-page action). Org-scoped so a stray id from another club
    is ignored. Does not commit. Returns (contacts_touched, memberships_removed).
    """
    ids = _uuids(contact_ids)
    if not ids:
        return 0, 0
    valid = set((await session.execute(
        select(CommsContact.id).where(
            CommsContact.organisation_id == organisation_id,
            CommsContact.id.in_(ids),
        ))).scalars().all())
    if not valid:
        return 0, 0
    res = await session.execute(
        delete(CommsListMember).where(CommsListMember.contact_id.in_(valid)))
    return len(valid), (res.rowcount or 0)
