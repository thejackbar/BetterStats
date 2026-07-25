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

2. **No active trial anywhere, but Stats is the deal's Product Interest** —
   either explicitly (module_keys contains billing key "core") OR because
   module_keys is EMPTY. An empty module_keys is deliberately included:
   the deal detail modal's own Product Interest chips (DealDetailModal.jsx)
   default an empty list to showing Stats selected — "a club with no
   Product Interest set at all is always assumed to want at least Stats"
   — but that default is display-only and is never written back to the
   row, so a plain `"core" in module_keys` check misses every deal that
   looks like it has Stats selected in the UI but has never actually had
   its Product Interest touched. Matching the UI's own convention here is
   what "Stats already flagged as a Product Interest in the CRM" means in
   practice for the bulk of deals. Still worth re-running the analytics
   recalc to keep the chips current, and Value ($) is set to just the
   Stats module's own price (not a bundle — there's nothing else to
   bundle with here since no other module is in play).

A deal that's neither — no active trial AND Product Interest explicitly
holds some OTHER module set that doesn't include Stats — is left
untouched; there's no trial or Stats interest to price against.

v4 — deal discovery is no longer pipeline_id-scoped. Earlier versions
fetched deals via `list_deals(session, pipeline.id, status="open")`, tying
the whole batch to whatever single pipeline row `ensure_platform_pipeline()`
resolves to. If production ever ended up with more than one `crm_pipelines`
row with `scope='platform'` (a real historical risk — a past bug in
`ensure_platform_pipeline`'s pipeline-creation branch, fixed earlier in the
same work as migration 188, could plausibly have left a stray duplicate
pipeline row from before that fix was live), a deal sitting under a
different/stale platform pipeline_id than the one currently resolved as
canonical would be silently invisible to this script — even though it
displays completely normally in the web UI (which resolves the exact same
single pipeline.id the script used to). v4 instead queries
`CrmDeal.scope == 'platform'` directly, across every platform pipeline row,
and prints a warning if it finds more than one platform pipeline and/or
deals spanning more than one distinct pipeline_id — so a run's own output
tells you whether this was ever actually the cause of a "why isn't this
deal matching" gap.

Usage from the backend container (matches the rest of app/scripts/*):
  docker exec -e PYTHONPATH=/app betterstats-backend \\
    python -m app.scripts.crm_recalc_trial_deals
  # preview only, no writes:
  docker exec -e PYTHONPATH=/app betterstats-backend \\
    python -m app.scripts.crm_recalc_trial_deals --dry-run
"""
import asyncio
import sys

from sqlalchemy import select

from app.models.db import async_session_maker, CrmDeal, CrmPipeline
from app.services import crm as crm_service

STATS_KEY = "core"  # billing_pricing / value_from_modules key for BetterStats

# Bumped whenever the script's behaviour changes — printed at the top of every
# run so a stale container image (docker compose exec runs whatever code was
# baked into the image at last build, NOT the latest git commit) is obvious
# from the output rather than silently only doing the older subset of work.
SCRIPT_VERSION = 4  # v4: fetch deals by scope='platform' directly instead of
                    # a single resolved pipeline_id, and warn if more than one
                    # platform pipeline row exists — a deal sitting under a
                    # DIFFERENT (stale/duplicate) pipeline id than the one
                    # ensure_platform_pipeline() currently resolves to would
                    # otherwise be silently invisible to this script (and to
                    # the web UI's own board/list, which resolves the SAME
                    # single pipeline.id) even though its Product Interest
                    # and stage look completely normal.


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
    print(f"crm_recalc_trial_deals v{SCRIPT_VERSION} (trial-branch + stats-only-branch)")
    async with async_session_maker() as session:
        # Runs the usual get-or-create/reconcile so stages exist — but the
        # deal query below deliberately does NOT filter by this pipeline's
        # id (see v4 note above).
        pipeline = await crm_service.ensure_platform_pipeline(session)

        all_platform_pipeline_ids = (await session.execute(
            select(CrmPipeline.id).where(CrmPipeline.scope == crm_service.SCOPE_PLATFORM)
        )).scalars().all()
        if len(all_platform_pipeline_ids) > 1:
            print(
                f"  ! WARNING: {len(all_platform_pipeline_ids)} platform pipeline rows exist "
                f"(expected exactly 1) — ids: {[str(i) for i in all_platform_pipeline_ids]}. "
                f"Querying deals by scope='platform' across all of them, not just "
                f"the one ensure_platform_pipeline() resolved to ({pipeline.id})."
            )

        deals = (await session.execute(
            select(CrmDeal).where(
                CrmDeal.scope == crm_service.SCOPE_PLATFORM,
                CrmDeal.archived_at.is_(None),
                CrmDeal.status == "open",
            )
        )).scalars().all()
        distinct_pipeline_ids = {d.pipeline_id for d in deals}
        if len(distinct_pipeline_ids) > 1:
            print(f"  ! {len(deals)} open platform deal(s) span {len(distinct_pipeline_ids)} "
                 f"different pipeline_id values: {[str(i) for i in distinct_pipeline_ids]}")

        club_by_id = await crm_service.clubs_by_ids(session, (d.marketing_club_id for d in deals))
        trial_days = await crm_service.trial_days_remaining_by_club(session, club_by_id)

        trial_targets = [d for d in deals if d.marketing_club_id in trial_days]
        # No active trial anywhere for this club, and Stats is the deal's
        # Product Interest — either explicitly, or because module_keys is
        # empty (matches the deal detail modal's own "no Product Interest
        # set at all defaults to Stats" display convention — see the
        # module docstring above).
        stats_targets = [
            d for d in deals
            if d.marketing_club_id not in trial_days
            and (not d.module_keys or STATS_KEY in d.module_keys)
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
