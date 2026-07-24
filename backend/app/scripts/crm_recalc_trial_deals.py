"""One-off / rerunnable maintenance script: keeps BetterCRM platform deals'
Product Interest and Value ($) honest against what a club is actually
trialing (or, failing that, has already shown analytics interest in).

Two passes over every OPEN, non-archived platform deal, in priority order:

1. **Club currently has one or more modules on an active trial** — re-run
   "Recalculate from analytics" (the exact action behind the Product
   Interest button in the deal detail modal) to refresh the Product
   Interest chips, then set Value ($) to the bundle-discounted sum of the
   CURRENTLY-TRIALING modules' prices specifically. The trial set can
   differ from what analytics infers (a club might browse the IQ pages
   while only trialing Select, say), and the dollar figure on the card
   should reflect what they're actually trialing / about to be billed for
   once the trial converts.

2. **No active trial anywhere, but Stats (billing key "core") is already
   flagged as a Product Interest on the deal** — a club can show up here
   with no trial history at all (a manually-added prospect) or a lapsed
   one that never converted. Still worth re-running the analytics recalc
   to keep the chips current, and Value ($) is set to just the Stats
   module's own price (not a bundle — there's nothing else to bundle with
   here since no other module is in play).

A deal that's neither — no active trial AND Stats isn't already flagged —
is left untouched; there's no trial or expressed interest to price against.

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

STATS_KEY = "core"  # billing_pricing / value_from_modules key for BetterStats


async def _apply(session, deal, club, target_module_keys: list, reason: str, dry_run: bool) -> bool:
    """Recalc Product Interest from analytics, then pin Value ($) to
    value_from_modules(target_module_keys). Returns True on success (and
    commits, unless dry_run)."""
    club_name = club.name if club else deal.title
    try:
        had_data = await crm_service.recalc_product_interest(session, deal, club)
        old_value_cents = deal.value_cents
        new_value_cents = crm_service.value_from_modules(target_module_keys)
        deal.value_cents = new_value_cents
        print(
            f"  {club_name}: {reason} — "
            f"analytics {'used tracked visits' if had_data else 'no visits yet, defaulted'}, "
            f"Product Interest now {deal.module_keys}, "
            f"value ${old_value_cents / 100:,.0f} -> ${new_value_cents / 100:,.0f}"
        )
        if not dry_run:
            await session.commit()
        return True
    except Exception as exc:  # noqa: BLE001 - one club's failure must not abort the batch
        print(f"  ! {club_name}: failed ({exc}), skipping")
        await session.rollback()
        return False


async def run(dry_run: bool = False) -> None:
    async with async_session_maker() as session:
        pipeline = await crm_service.ensure_platform_pipeline(session)
        deals = await crm_service.list_deals(session, pipeline.id, status="open")
        club_by_id = await crm_service.clubs_by_ids(session, (d.marketing_club_id for d in deals))
        trial_days = await crm_service.trial_days_remaining_by_club(session, club_by_id)

        trial_targets = [d for d in deals if d.marketing_club_id in trial_days]
        # No active trial anywhere for this club, but Stats is already on
        # the deal's Product Interest — priced on just the Stats module.
        stats_targets = [
            d for d in deals
            if d.marketing_club_id not in trial_days and STATS_KEY in (d.module_keys or [])
        ]

        print(
            f"{len(deals)} open deal(s) in the pipeline: "
            f"{len(trial_targets)} with a club currently on trial, "
            f"{len(stats_targets)} with no trial but Stats already flagged as Product Interest."
        )
        if dry_run:
            print("--dry-run: no changes will be saved.\n")

        updated = 0
        errors = 0

        for deal in trial_targets:
            club = club_by_id.get(deal.marketing_club_id)
            trial_modules = sorted(trial_days[deal.marketing_club_id].keys())
            ok = await _apply(session, deal, club, trial_modules,
                              f"trialing {trial_modules}", dry_run)
            updated += ok
            errors += not ok

        for deal in stats_targets:
            club = club_by_id.get(deal.marketing_club_id)
            ok = await _apply(session, deal, club, [STATS_KEY],
                              "no active trial, Stats flagged as interest", dry_run)
            updated += ok
            errors += not ok

        if dry_run:
            await session.rollback()
            print(f"\nDRY RUN — nothing saved. Would have updated {updated} deal(s), {errors} error(s).")
        else:
            print(f"\nDone. Updated {updated} deal(s), {errors} error(s).")


if __name__ == "__main__":
    asyncio.run(run(dry_run="--dry-run" in sys.argv))
