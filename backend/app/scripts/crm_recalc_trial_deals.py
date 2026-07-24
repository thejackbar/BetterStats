"""One-off / rerunnable maintenance script: for every open BetterCRM
platform deal whose linked club currently has one or more modules on an
active trial, re-run "Recalculate from analytics" (the exact action behind
the Product Interest button in the deal detail modal) and then set the
deal's Value ($) to the sum of the CURRENTLY-TRIALING modules' prices
(bundle-discounted, same billing_pricing math as everywhere else).

Two distinct steps per matching deal, deliberately kept separate:
  1. recalc_product_interest — re-derives module_keys from the club's
     tracked website analytics (falls back to ['core'] if no visits are
     tracked yet), refreshing the Product Interest chips shown on the card.
  2. Overwrite value_cents to value_from_modules(<modules currently in
     trial>) — the trial set can differ from what analytics infers (a club
     might browse the IQ pages while only trialing Select, say), and the
     dollar figure on the card should reflect what they're actually
     trialing / about to be billed for once the trial converts, not just
     what their site visits suggest they're interested in.

Only touches OPEN, non-archived platform deals for a club with a live
trial — a Won/Lost/archived deal, or a club with no active trial at all
(never onboarded, or already a paying customer with no module still
trialing), is left untouched.

Usage from the backend container (matches the rest of app/scripts/*):
  docker exec -e PYTHONPATH=/app betterstats-backend \\
    python -m app.scripts.crm_recalc_trial_deals
  # preview only, no writes:
  docker exec -e PYTHONPATH=/app betterstats-backend \\
    python -m app.scripts.crm_recalc_trial_deals --dry-run
"""
import asyncio
import sys

from app.models.db import async_session_maker
from app.services import crm as crm_service


async def run(dry_run: bool = False) -> None:
    async with async_session_maker() as session:
        pipeline = await crm_service.ensure_platform_pipeline(session)
        deals = await crm_service.list_deals(session, pipeline.id, status="open")
        club_by_id = await crm_service.clubs_by_ids(session, (d.marketing_club_id for d in deals))
        trial_days = await crm_service.trial_days_remaining_by_club(session, club_by_id)

        targets = [d for d in deals if d.marketing_club_id in trial_days]
        print(f"{len(deals)} open deal(s) in the pipeline, {len(targets)} with a club currently on trial.")
        if dry_run:
            print("--dry-run: no changes will be saved.\n")

        updated = 0
        errors = 0
        for deal in targets:
            club = club_by_id.get(deal.marketing_club_id)
            club_name = club.name if club else deal.title
            trial_modules = sorted(trial_days[deal.marketing_club_id].keys())

            try:
                had_data = await crm_service.recalc_product_interest(session, deal, club)
                old_value_cents = deal.value_cents
                new_value_cents = crm_service.value_from_modules(trial_modules)
                deal.value_cents = new_value_cents

                print(
                    f"  {club_name}: trialing {trial_modules} — "
                    f"analytics {'used tracked visits' if had_data else 'no visits yet, defaulted'}, "
                    f"Product Interest now {deal.module_keys}, "
                    f"value ${old_value_cents / 100:,.0f} -> ${new_value_cents / 100:,.0f}"
                )

                if not dry_run:
                    await session.commit()
                updated += 1
            except Exception as exc:  # noqa: BLE001 - one club's failure must not abort the batch
                errors += 1
                print(f"  ! {club_name}: failed ({exc}), skipping")
                await session.rollback()

        if dry_run:
            await session.rollback()
            print(f"\nDRY RUN — nothing saved. Would have updated {updated} deal(s), {errors} error(s).")
        else:
            print(f"\nDone. Updated {updated} deal(s), {errors} error(s).")


if __name__ == "__main__":
    asyncio.run(run(dry_run="--dry-run" in sys.argv))
