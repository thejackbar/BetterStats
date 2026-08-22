"""Re-price OPEN platform deals whose value has drifted from their modules.

A platform deal's ``value_cents`` is the price of its ``module_keys``
(``crm.value_from_modules``). ``sync_platform_deal_for_club`` used to keep
whichever figure was HIGHER when it merged a new signal in, so a deal once
valued at the full bundle held that price after its modules were narrowed —
reported live as a deal reading "Stats" beside $998, the all-six-modules
price. That ratchet is gone, and each affected deal repairs itself the next
time any signal touches it; this repairs the ones sitting there now.

WON and LOST deals are deliberately left alone. A closed deal's value is the
historical record of what was actually sold, not a live estimate, and
re-pricing it would rewrite the commission earned on it.

A deal with no modules at all is skipped rather than zeroed: an empty
selection is "nobody has said yet", not "this is worth nothing".

    python -m app.scripts.repair_deal_values            # dry run, every club
    python -m app.scripts.repair_deal_values --apply
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.models.db import CrmDeal, MarketingClub, async_session_maker
from app.services import crm as crm_service


async def run(apply: bool) -> int:
    async with async_session_maker() as session:
        pipeline = await crm_service.ensure_platform_pipeline(session)
        deals = (await session.execute(
            select(CrmDeal).where(
                CrmDeal.pipeline_id == pipeline.id,
                CrmDeal.status == "open",
                CrmDeal.archived_at.is_(None),
            )
        )).scalars().all()
        club_by_id = await crm_service.clubs_by_ids(session, (d.marketing_club_id for d in deals))

        drifted = []
        for d in deals:
            keys = sorted(set(d.module_keys or []))
            if not keys:
                continue
            correct = crm_service.value_from_modules(keys)
            if correct != (d.value_cents or 0):
                drifted.append((d, keys, correct))

        if not drifted:
            print("Every open deal's value already matches its modules.")
            return 0

        print(f"{len(drifted)} open deal(s) priced differently from their modules:\n")
        for d, keys, correct in drifted:
            club: MarketingClub | None = club_by_id.get(d.marketing_club_id)
            name = (club.name if club else None) or d.title or "Untitled"
            print(f"  {name[:44]:<44} {', '.join(keys):<38} "
                  f"${(d.value_cents or 0) / 100:>8,.0f} -> ${correct / 100:>8,.0f}")
            if apply:
                d.value_cents = correct

        if apply:
            await session.commit()
            print(f"\nRe-priced {len(drifted)} deal(s).")
        else:
            print(f"\nDry run — nothing written. Re-run with --apply to re-price these "
                  f"{len(drifted)} deal(s).")
    return len(drifted)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the corrected values")
    args = parser.parse_args()
    asyncio.run(run(args.apply))


if __name__ == "__main__":
    main()
