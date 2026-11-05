"""Clubs for the "Trusted by clubs at" strip on the public site (unauthenticated).

The strip on the home page and /trial used to be a hand-kept list. This is the
live version of it: every club that is paying for BetterStats, so a club that
signs up appears without anyone editing the front end. The front end still
carries its curated list as the fallback and the first entries.

A club is listed only when ALL of these hold:
  * it is live (``is_active``), not archived, and has a public slug;
  * its BetterStats (Core) row is genuinely ``active``, i.e. paying. A trial,
    a lapsed trial, a paused or cancelled club, and a ``past_due`` grace period
    are all left out, as is any club whose whole-account master switch is off;
  * it is not behind an access PIN (a locked club has chosen not to be public);
  * it is not the marketing-outreach org;
  * it has an uploaded crest (the strip shows a logo, and a club without one
    would be an empty box);
  * its slug is not in ``settings.trusted_clubs_exclude``.

Honest limit: "active" cannot tell a paid subscription from one a Super Admin
set Active by hand (a bank transfer, or a free grant), because both are an
``active`` Core row. Use ``TRUSTED_CLUBS_EXCLUDE`` to keep a club off.

Only the public club page's name, slug and crest path come back. Nothing about
the club's people, plan, billing or dates leaves this route.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.modules import ACTIVE_STATUSES, DEFAULT_STATUS, MODULE_CORE, STATUS_ACTIVE
from app.config.settings import settings
from app.models.db import Organisation, OrgModuleSubscription, get_db

router = APIRouter(prefix="/public", tags=["public-trusted-clubs"])

# A marquee of more than this many logos stops reading as a strip.
MAX_CLUBS = 60


def _excluded() -> set[str]:
    raw = getattr(settings, "trusted_clubs_exclude", "") or ""
    return {s.strip().lower() for s in raw.split(",") if s.strip()}


@router.get("/trusted-clubs")
async def trusted_clubs(response: Response, db: AsyncSession = Depends(get_db)):
    core = (
        select(OrgModuleSubscription.organisation_id, OrgModuleSubscription.started_at)
        .where(OrgModuleSubscription.module_key == MODULE_CORE)
        .where(OrgModuleSubscription.status == STATUS_ACTIVE)
        .subquery()
    )
    stmt = (
        select(Organisation.id, Organisation.name, Organisation.slug)
        .join(core, core.c.organisation_id == Organisation.id)
        .where(Organisation.is_active.is_(True))
        .where(Organisation.archived_at.is_(None))
        .where(Organisation.slug.isnot(None), Organisation.slug != "")
        .where(Organisation.access_pin_hash.is_(None))
        .where(Organisation.is_marketing_outreach.is_(False))
        .where(func.coalesce(Organisation.subscription_status, DEFAULT_STATUS).in_(ACTIVE_STATUSES))
        # length() reads the crest's size without loading the image itself
        .where(func.length(Organisation.logo_data) > 0)
        .order_by(desc(core.c.started_at).nulls_last(), Organisation.name)
    )
    rows = (await db.execute(stmt)).all()
    skip = _excluded()
    clubs = [
        {"slug": r.slug, "name": r.name, "logo": f"/api/images/organisations/{r.id}/logo"}
        for r in rows
        if (r.slug or "").lower() not in skip
    ][:MAX_CLUBS]
    # The list changes when a club signs up, not by the minute.
    response.headers["Cache-Control"] = "public, max-age=900"
    return {"clubs": clubs}
