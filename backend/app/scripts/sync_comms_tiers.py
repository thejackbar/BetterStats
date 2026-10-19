"""Lift paying BetterAdmin clubs from the Sandbox sending limit to Production.

WHY
---
A club's BetterComms sending tier now follows its BetterComms subscription
(services/comms_limits.apply_comms_subscription_tier, called from
services/module_subscriptions on every status write). That only fires on a
CHANGE of status, so a club that was already active before it shipped is still
on Sandbox, capped at 50 emails a day. This is the one-off backfill for them.

WHAT IT DOES
------------
For every club whose BetterComms module is ``active`` and whose tier is
``sandbox``, sets the tier to ``production``. Dry run by default.

WHAT IT WILL NOT DO
-------------------
It never DEMOTES. A Production club with no active subscription is listed so a
person can decide (a super admin may have lifted it by hand for a good reason).
A suspended club stays suspended, and the marketing-outreach org is skipped.

USAGE
-----
    python -m app.scripts.sync_comms_tiers all             # dry run, every club
    python -m app.scripts.sync_comms_tiers all --apply
    python -m app.scripts.sync_comms_tiers <org-id-or-slug> [--apply]
"""
from __future__ import annotations

import asyncio
import sys
import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.auth.modules import MODULE_COMMS, STATUS_ACTIVE
from app.models.db import Organisation, async_session_maker
from app.services import comms_limits


async def _resolve_club(session, raw: str):
    """A club by id or slug, so the one-club form can be typed either way."""
    try:
        return await session.get(Organisation, uuid.UUID(raw))
    except (ValueError, AttributeError):
        return (await session.execute(
            select(Organisation).where(Organisation.slug == raw))).scalar_one_or_none()


def _comms_status(org) -> str | None:
    sub = next((s for s in (org.module_subscriptions or []) if s.module_key == MODULE_COMMS), None)
    return sub.status if sub is not None else None


def plan(orgs) -> tuple[list, list]:
    """(clubs to lift, production clubs with no active subscription). Pure, so
    the dry run and the apply read the same decision."""
    lift, unsubscribed = [], []
    for org in orgs:
        if comms_limits.org_is_outreach(org):
            continue
        status = _comms_status(org)
        # previous_status=None: ask the same question the live hook asks for a
        # club that has just become active.
        if comms_limits.tier_after_comms_status(org.comms_tier, None, status) == comms_limits.TIER_PRODUCTION:
            lift.append(org)
        elif (comms_limits.normalise_tier(org.comms_tier) == comms_limits.TIER_PRODUCTION
              and status != STATUS_ACTIVE):
            unsubscribed.append((org, status))
    return lift, unsubscribed


async def run(target: str, apply: bool) -> int:
    async with async_session_maker() as session:
        if target == "all":
            orgs = (await session.execute(
                select(Organisation).options(selectinload(Organisation.module_subscriptions))
                .order_by(Organisation.name))).scalars().all()
        else:
            club = await _resolve_club(session, target)
            if club is None:
                print(f"No club found for {target!r}")
                return 1
            orgs = [(await session.execute(
                select(Organisation).options(selectinload(Organisation.module_subscriptions))
                .where(Organisation.id == club.id))).scalar_one()]

        lift, unsubscribed = plan(orgs)
        print(f"{'APPLY' if apply else 'DRY RUN'}: {len(orgs)} club(s) read")
        print(f"\nSandbox with an active BetterComms subscription -> production ({len(lift)}):")
        for org in lift:
            print(f"  {org.name} ({org.slug})   undo: UPDATE organisations SET comms_tier = 'sandbox' "
                  f"WHERE id = '{org.id}';")
        print(f"\nProduction with no active BetterComms subscription, left alone ({len(unsubscribed)}):")
        for org, status in unsubscribed:
            print(f"  {org.name} ({org.slug})  comms module: {status or 'none'}")

        if apply and lift:
            for org in lift:
                org.comms_tier = comms_limits.TIER_PRODUCTION
            await session.commit()
            print(f"\nLifted {len(lift)} club(s). Deferred emails go out at the next 00:15 UTC run.")
        elif not apply and lift:
            print("\nNothing written. Re-run with --apply.")
    return 0


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    apply = "--apply" in argv
    if len(args) != 1:
        print(__doc__)
        return 2
    return asyncio.run(run(args[0], apply))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
