"""Recompute every club's engagement score with the current scoring rules and
re-cache it onto marketing_clubs, then re-run the CRM auto-promotion so the
Super Admin CRM board (/admin/super/crm) reflects the new scores.

WHY THIS EXISTS
    twenty_sync._engagement() caches its result onto the club row itself
    (marketing_clubs.engagement_score / .engagement_tier / .engagement_scored_at
    — see _apply_engagement_cache), and the CRM board reads that cached number
    (crm.py builds each deal's "engagement_score" straight from the club row).
    Scores are normally refreshed lazily — the nightly job, a BetterComms send,
    a manual "Refresh Twenty scores" — and the built-in refresh_engagement()
    only touches clubs already exported to Twenty. After a change to the scoring
    weights, every cached number is stale until its club is next touched. This
    script forces a full, immediate recompute across ALL marketing_clubs so the
    board is correct straight away.

WHAT IT DOES PER CLUB
    crm.sync_engagement_promotion(session, club, org):
      1. _engagement() — recomputes and re-caches score + tier (a handful of
         indexed reads over usage_events / email_events / etc; no Twenty calls,
         so it works whether or not Twenty is configured).
      2. maybe_promote_by_engagement_score() — re-applies the configured
         'engagement_score' CRM automation rules, promoting a club's deal to the
         right stage for its new score (forward-only; a no-op when no rule
         qualifies or the club has no deal yet).

    It does NOT push to Twenty — that is the external CRM and is refreshed by its
    own jobs / the "Refresh Twenty scores" button. This script is only about the
    internal board's cached numbers.

USAGE (inside the backend container — see the deploy notes in CLAUDE.md)
    # every club
    python -m app.scripts.recalc_engagement
    # dry run — compute and report, roll back without persisting
    python -m app.scripts.recalc_engagement --dry-run
    # only clubs whose name matches a substring (handy for a spot check first)
    python -m app.scripts.recalc_engagement --name applecross

    On the server the invocation is:
      cd /srv/docker && COMPOSE_PROJECT_NAME=bltbox_docker_app \
        docker compose exec betterstats-backend python -m app.scripts.recalc_engagement
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.models.db import MarketingClub, Organisation, async_session_maker
from app.services import crm as crm_service

logger = logging.getLogger("recalc_engagement")

COMMIT_EVERY = 100


async def _load_org(session, org_id):
    """Load the linked org with its module subscriptions eagerly, so _engagement
    scores a paying club on account-health (it inspects module_subscriptions to
    tell paid from trial). Mirrors refresh_engagement's own loader."""
    if not org_id:
        return None
    return await session.get(
        Organisation, org_id,
        options=[selectinload(Organisation.module_subscriptions)],
    )


def _percentile(sorted_vals, pct):
    if not sorted_vals:
        return 0
    k = (len(sorted_vals) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = k - lo
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac


def _print_histogram(scores: list) -> None:
    """A text histogram + percentiles of the score spread, so the distribution
    can be eyeballed straight from the run without a dashboard."""
    if not scores:
        print("  (no scores)")
        return
    s = sorted(scores)
    n = len(s)
    print("\n  score distribution (bins of 5):")
    peak = 0
    counts = []
    for lo in range(0, 100, 5):
        hi = lo + 5
        # Top bin is inclusive of 100.
        c = sum(1 for v in s if (lo <= v < hi) or (hi == 100 and v == 100))
        counts.append((lo, hi, c))
        peak = max(peak, c)
    for lo, hi, c in counts:
        bar = "#" * int(round(40 * c / peak)) if peak else ""
        print(f"    {lo:3d}-{hi:<3d} {c:5d}  {bar}")
    print(f"\n  n={n}  min={s[0]:.0f}  p25={_percentile(s,25):.0f}  "
          f"median={_percentile(s,50):.0f}  p75={_percentile(s,75):.0f}  "
          f"p90={_percentile(s,90):.0f}  max={s[-1]:.0f}  mean={sum(s)/n:.1f}")


async def recalc(*, dry_run: bool = False, name: str | None = None) -> dict:
    tiers: Counter = Counter()
    tiers_linked: Counter = Counter()   # clubs with a linked org (onboarded/customer)
    tiers_prospect: Counter = Counter()  # directory-only prospects
    scores: list = []
    scores_prospect: list = []
    promoted = 0
    errors = 0
    processed = 0
    linked_count = 0

    async with async_session_maker() as session:
        # Pre-load a lightweight list of (id, name) as PLAIN values, not ORM
        # instances. If a club's recompute errors, the failed transaction expires
        # every attached ORM object, so touching one afterwards (even to read its
        # id for a log line) fires a lazy reload — which, mid-failed-async-txn,
        # raises MissingGreenlet and takes the whole sweep down. Plain tuples are
        # immune, and re-fetching each club fresh inside the loop means a rollback
        # fully resets the session before the next club.
        idq = select(MarketingClub.id, MarketingClub.name).order_by(MarketingClub.id)
        if name:
            idq = idq.where(func.lower(MarketingClub.name).like(f"%{name.lower()}%"))
        rows = (await session.execute(idq)).all()
        total = len(rows)
        print(f"Recomputing engagement for {total} club(s)"
              + (f" matching {name!r}" if name else "")
              + (" [DRY RUN — nothing will be saved]" if dry_run else "")
              + " ...")

        batch = 0
        for cid, cname in rows:
            try:
                club = await session.get(MarketingClub, cid)
                if club is None:
                    continue
                org = await _load_org(session, club.existing_org_id)
                deal = await crm_service.sync_engagement_promotion(session, club, org)
                tier = club.engagement_tier or "UNKNOWN"
                tiers[tier] += 1
                # "Linked" = has an Organisation row (an onboarded club: a trial
                # or a paying customer). These are the ones the account-health /
                # trial-depth floors push high, vs a directory-only prospect
                # scored purely on lead heat. Matches the CRM deal's is_customer
                # flag (bool(existing_org_id)), so the split lines up with the
                # dashboard chart.
                is_linked = bool(club.existing_org_id)
                if is_linked:
                    linked_count += 1
                    tiers_linked[tier] += 1
                else:
                    tiers_prospect[tier] += 1
                if club.engagement_score is not None:
                    scores.append(club.engagement_score)
                    if not is_linked:
                        scores_prospect.append(club.engagement_score)
                if deal is not None:
                    promoted += 1
                processed += 1
                batch += 1
                if batch >= COMMIT_EVERY:
                    # Roll a dry run back so nothing persists; commit a real run.
                    await (session.rollback() if dry_run else session.commit())
                    batch = 0
                    print(f"  ... {processed}/{total}")
            except Exception:  # noqa: BLE001 — one bad club must not abort the sweep
                errors += 1
                await session.rollback()   # reset the session BEFORE any logging
                batch = 0
                logger.exception("recalc failed for club id=%s name=%r", cid, cname)

        # Flush the tail of the final partial batch.
        await (session.rollback() if dry_run else session.commit())
        if dry_run:
            print("DRY RUN — rolled back, no changes saved.")

    print("\nDone.")
    print(f"  processed: {processed}")
    print(f"  deals promoted this run: {promoted}")
    if errors:
        print(f"  errors (skipped, see log): {errors}")
    prospect_count = processed - linked_count
    print(f"  makeup: {prospect_count} directory-only prospects, "
          f"{linked_count} linked clubs (onboarded trials/customers)")
    print(f"  tier distribution (total | prospect | linked):")
    for tier in sorted(tiers, key=lambda t: -tiers[t]):
        print(f"    {tier:16} {tiers[tier]:6}  |  {tiers_prospect.get(tier, 0):6}  |  "
              f"{tiers_linked.get(tier, 0):6}")

    print("\n=== ALL clubs ===")
    _print_histogram(scores)
    print("\n=== PROSPECTS ONLY (directory-only, the true lead-heat view) ===")
    _print_histogram(scores_prospect)
    return {"processed": processed, "promoted": promoted, "errors": errors,
            "linked": linked_count, "prospects": prospect_count, "tiers": dict(tiers)}


def main() -> None:
    ap = argparse.ArgumentParser(description="Recalculate all engagement scores.")
    ap.add_argument("--dry-run", action="store_true",
                    help="compute and report a tier distribution, then roll back")
    ap.add_argument("--name", default=None,
                    help="only clubs whose name contains this substring")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(recalc(dry_run=args.dry_run, name=args.name))


if __name__ == "__main__":
    main()
