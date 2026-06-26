"""Resolve the BetterCricket marketing-outreach organisation.

BetterCricket sends its own BetterComms campaigns to the Clubs Directory through a
normal ``organisations`` row (the "outreach org"), kept separate from any real
club so an opt-out on the directory list never touches a club's own audience.

Which row is the outreach org is designated in the DB
(``organisations.is_marketing_outreach``, set by a super admin from the BetterComms
UI) and, as a fallback, named by the ``marketing_outreach_org_slug`` setting. The
DB flag wins, so designation needs no env change or redeploy.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.models.db import Organisation


def _slug() -> str:
    return (settings.marketing_outreach_org_slug or "").strip()


async def get_outreach_org(session: AsyncSession) -> Optional[Organisation]:
    """The designated BetterCricket marketing-outreach org, or None if unset."""
    org = await session.scalar(
        select(Organisation).where(Organisation.is_marketing_outreach.is_(True)))
    if org:
        return org
    slug = _slug()
    if slug:
        return await session.scalar(
            select(Organisation).where(Organisation.slug == slug))
    return None


def org_is_outreach(org: Optional[Organisation]) -> bool:
    """True if this org is the BetterCricket marketing-outreach org (flag or slug)."""
    if org is None:
        return False
    if getattr(org, "is_marketing_outreach", False):
        return True
    slug = _slug()
    return bool(slug and org.slug == slug)
