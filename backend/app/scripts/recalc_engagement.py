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


async def recalc(*, dry_run: bool = False, name: str | None = None) -> dict:
    tiers: Counter = Counter()
    promoted = 0
    errors = 0
    processed = 0

    async with async_session_maker() as session:
        q = select(MarketingClub).order_by(MarketingClub.id)  # stable lock order
        if name:
            q = q.where(func.lower(MarketingClub.name).like(f"%{name.lower()}%"))
        # Load the full set up front rather than streaming: we commit in batches
        # below, and a mid-stream commit would invalidate an async server-side
        # cursor. Mirrors refresh_engagement's own .scalars().all() load.
        clubs = (await session.execute(q)).scalars().all()
        total = len(clubs)
        print(f"Recomputing engagement for {total} club(s)"
              + (f" matching {name!r}" if name else "")
              + (" [DRY RUN — nothing will be saved]" if dry_run else "")
              + " ...")

        for club in clubs:
            try:
                org = await _load_org(session, club.existing_org_id)
                deal = await crm_service.sync_engagement_promotion(session, club, org)
                tiers[club.engagement_tier or "UNKNOWN"] += 1
                if deal is not None:
                    promoted += 1
                processed += 1
                if not dry_run and processed % COMMIT_EVERY == 0:
                    await session.commit()
                    print(f"  ... {processed}/{total} committed")
            except Exception:  # noqa: BLE001 — one bad club must not abort the sweep
                errors += 1
                logger.exception("recalc failed for club id=%s name=%r",
                                 getattr(club, "id", "?"), getattr(club, "name", "?"))
                await session.rollback()

        if dry_run:
            await session.rollback()
            print("DRY RUN — rolled back, no changes saved.")
        else:
            await session.commit()

    print("\nDone.")
    print(f"  processed: {processed}")
    print(f"  deals promoted this run: {promoted}")
    if errors:
        print(f"  errors (skipped, see log): {errors}")
    print("  tier distribution:")
    for tier, n in sorted(tiers.items(), key=lambda kv: -kv[1]):
        print(f"    {tier:16} {n}")
    return {"processed": processed, "promoted": promoted, "errors": errors,
            "tiers": dict(tiers)}


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
