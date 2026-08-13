"""Set a Scout Org's pricing tier. The one place a tier actually changes —
there's no self-serve upgrade in the app, since BetterScout has no Stripe
checkout wired up yet (see services/scout_billing.py). Run inside the normal
betterstats-backend container:

    docker compose exec betterstats-backend python -m app.scripts.scout_set_tier <org-name-or-id> <starter|growth|unlimited>

e.g.  docker compose exec betterstats-backend python -m app.scripts.scout_set_tier "Jack's Scouting" growth
"""
import asyncio
import sys
import uuid

from sqlalchemy import select

from app.models.db import async_session_maker
from app.models.scout import ScoutOrg
from app.services import scout_billing


async def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    org_ref, tier = sys.argv[1:3]
    if tier not in scout_billing.TIER_LIMITS:
        print(f"Unknown tier {tier!r} — must be one of: {', '.join(scout_billing.TIER_LIMITS)}")
        sys.exit(1)

    async with async_session_maker() as session:
        org = None
        try:
            org = await session.get(ScoutOrg, uuid.UUID(org_ref))
        except ValueError:
            pass
        if org is None:
            res = await session.execute(select(ScoutOrg).where(ScoutOrg.name == org_ref))
            org = res.scalar_one_or_none()
        if org is None:
            print(f"No scout org found matching {org_ref!r} (tried as an id, then as a name).")
            sys.exit(1)

        old_tier = org.tier
        org.tier = tier
        await session.commit()
        cap = scout_billing.cap_for(tier)
        print(
            f"{org.name} ({org.id}): {old_tier} -> {tier} "
            f"({'unlimited' if cap is None else f'{cap} players'})"
        )


if __name__ == "__main__":
    asyncio.run(main())
