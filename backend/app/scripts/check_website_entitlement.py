"""Which clubs would lose their public website when the CMS moves behind BetterSocials.

The stats site at /{slug} is Core and is not affected. The CMS half (news,
pages, honour rolls, committee, galleries at /{slug}/website) is BetterSocials
now, so a club that has ``website_enabled`` ticked WITHOUT holding the socials
module stops having those pages served.

``org_has_module`` does not fail open the way ``org_core_live`` does: a club
whose ``module_overrides`` is empty or NULL reads as holding nothing. So run
this against production BEFORE deploying the gate, and either sell those clubs
the module or add 'socials' to their overrides.

Read-only. It writes nothing and takes no arguments.

    python -m app.scripts.check_website_entitlement
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.auth.modules import MODULE_SOCIALS, org_has_module
from app.models.db import Organisation, async_session_maker


async def run() -> int:
    async with async_session_maker() as db:
        orgs = (await db.execute(
            select(Organisation)
            .where(Organisation.website_enabled.is_(True))
            .options(selectinload(Organisation.module_subscriptions))
            .order_by(Organisation.name)
        )).scalars().all()

    if not orgs:
        print("No club has website_enabled set. Nothing to do.")
        return 0

    losing = [o for o in orgs if not org_has_module(o, MODULE_SOCIALS)]
    print(f"{len(orgs)} club(s) have a published website.")
    print(f"{len(losing)} of them do NOT hold BetterSocials and would lose it.\n")
    for o in losing:
        held = ", ".join(sorted(o.module_overrides or [])) or "(none)"
        archived = " [archived]" if getattr(o, "archived_at", None) else ""
        active = "" if o.is_active else " [inactive]"
        print(f"  {o.name}{archived}{active}")
        print(f"    slug={o.slug}  id={o.id}")
        print(f"    modules held: {held}")
    if losing:
        print("\nEither add 'socials' to those clubs' module_overrides, or accept")
        print("that /{slug}/website 404s for them once the gate ships.")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(run()))


if __name__ == "__main__":
    main()
