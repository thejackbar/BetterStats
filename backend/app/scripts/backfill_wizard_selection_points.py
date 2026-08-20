"""Apply the wizard-selection points to selections that already happened.

WHY THIS EXISTS
    A registration-wizard club selection is worth BONUS_CLUB_SELECTED points on
    the club's engagement score (twenty_sync). The signal is computed on read
    from usage_events, all-time, so historical selections count the moment a
    club is next scored — but nothing rescores a club on its own. Until then the
    CRM board and BetterComms segments keep reading the cached
    marketing_clubs.engagement_score, which was written before these points
    existed. This walks the clubs that HAVE historical selections and rescores
    exactly those, reporting what each one gained.

    Every other club is untouched, which is what separates this from
    ``recalc_engagement`` (the whole-directory sweep, correct but heavier and
    silent about where the movement came from). Run this after deploying the
    scoring change; run recalc_engagement when the weights themselves change.

WHAT IT DOES PER CLUB
    crm.sync_engagement_promotion(session, club, org) — the same call
    recalc_engagement makes, so the recomputed score is cached onto the club row
    AND the CRM auto-promotion rules are re-applied to its deal. It does NOT
    push to Twenty; that has its own jobs / the "Refresh Twenty scores" button.

WHAT IT WILL NOT DO
    Selections a super admin flagged as test noise on the Meta Ads page are
    excluded, exactly as they are in live scoring. A club whose score is pinned
    by a rule that outranks the ordinary formula (a direct enquiry inside the
    hot window, "not interested", a customer's account-health floor) can show a
    smaller gain than its selections alone suggest, or none — that is the
    scoring working, not a miscount.

USAGE (inside the backend container — see the deploy notes in CLAUDE.md)
    # what WOULD change, nothing written (default)
    python -m app.scripts.backfill_wizard_selection_points
    # actually rescore and persist
    python -m app.scripts.backfill_wizard_selection_points --apply
    # one club, for a spot check first
    python -m app.scripts.backfill_wizard_selection_points --name warnbro

    On the server:
      cd /srv/docker && COMPOSE_PROJECT_NAME=bltbox_docker_app \
        docker compose exec betterstats-backend \
        python -m app.scripts.backfill_wizard_selection_points --apply
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.db import MarketingClub, Organisation, async_session_maker
from app.services import crm as crm_service
from app.services import twenty_sync

logger = logging.getLogger("backfill_wizard_selection_points")

COMMIT_EVERY = 100


def _uuids(keys) -> list:
    """The batch map is keyed by club id as TEXT (it comes back from SQL); the
    column is a real uuid, so a junk key is skipped rather than failing the run."""
    out = []
    for k in keys:
        try:
            out.append(uuid.UUID(str(k)))
        except (ValueError, AttributeError, TypeError):
            logger.warning("skipping unparseable club id %r from the batch map", k)
    return out


async def _load_org(session, org_id):
    """Load the linked org with its module subscriptions eagerly, so _engagement
    scores a paying club on account-health. Mirrors recalc_engagement's loader."""
    if not org_id:
        return None
    return await session.get(
        Organisation, org_id,
        options=[selectinload(Organisation.module_subscriptions)],
    )


async def backfill(*, apply: bool = False, name: str | None = None) -> dict:
    changed = errors = processed = 0
    total_selections = 0
    moved_tier: list = []

    async with async_session_maker() as session:
        # One pass over the selection beacons resolves every club at once, so
        # this costs one query rather than one per club.
        wizard_map = await twenty_sync.batch_wizard_selection_stats(session)
        if not wizard_map:
            print("No wizard club selections on record — nothing to back-calculate.")
            return {"processed": 0, "changed": 0, "errors": 0}

        # Plain (id, name) tuples, never ORM instances: a failed recompute
        # expires every attached object, and touching one afterwards fires a
        # lazy load mid-failed-transaction (MissingGreenlet). Same reason
        # recalc_engagement does it this way.
        rows = (await session.execute(
            select(MarketingClub.id, MarketingClub.name)
            .where(MarketingClub.id.in_(_uuids(wizard_map)))
            .order_by(MarketingClub.name)
        )).all()
        if name:
            rows = [r for r in rows if name.lower() in (r[1] or "").lower()]

        print(f"{len(rows)} club(s) have wizard selections on record"
              + (f" matching {name!r}" if name else "")
              + (" — APPLYING" if apply else " [DRY RUN — nothing will be saved]"))
        print(f"  {twenty_sync.BONUS_CLUB_SELECTED} points per distinct visitor "
              f"who picked the club\n")

        if apply:
            # Get the pipeline's own get-or-create (and its commit) out of the
            # way before any club has an unsaved score pending, so the first
            # club through the loop isn't committed on a different boundary
            # from the rest.
            await crm_service.ensure_platform_pipeline(session)
            await session.commit()
        print(f"  {'club':<44} {'picks':>5}  {'score':>13}  tier")
        print(f"  {'-' * 44} {'-' * 5}  {'-' * 13}  ----")

        for cid, cname in rows:
            try:
                club = await session.get(MarketingClub, cid)
                if club is None:
                    continue
                before_score = club.engagement_score
                before_tier = club.engagement_tier
                org = await _load_org(session, club.existing_org_id)
                if apply:
                    await crm_service.sync_engagement_promotion(
                        session, club, org, wizard_stats=wizard_map)
                else:
                    # Score only. sync_engagement_promotion also re-applies the
                    # CRM promotion rules, and the pipeline bootstrap inside
                    # those COMMITS when it has anything to reconcile — which
                    # would sweep the pending score of whichever club is being
                    # processed at the time into the database, so a "dry run"
                    # silently persisted its first club. A dry run has no reason
                    # to touch the write path at all.
                    await twenty_sync._engagement(
                        session, club, org, wizard_stats=wizard_map)
                picks = (wizard_map.get(str(cid)) or {}).get("selections", 0)
                total_selections += picks
                after_score = club.engagement_score
                after_tier = club.engagement_tier
                processed += 1
                if before_score != after_score or before_tier != after_tier:
                    changed += 1
                if before_tier != after_tier:
                    moved_tier.append((cname, before_tier, after_tier))
                delta = ((after_score or 0) - (before_score or 0))
                print(f"  {(cname or '?')[:44]:<44} {picks:>5}  "
                      f"{str(before_score):>4} -> {str(after_score):<4} "
                      f"({delta:+d})  {before_tier or '-'} -> {after_tier or '-'}")

                if apply and processed % COMMIT_EVERY == 0:
                    await session.commit()
            except Exception:  # noqa: BLE001
                errors += 1
                await session.rollback()
                logger.exception("backfill failed for club %s (%s)", cname, cid)

        if apply:
            await session.commit()
            print("\nSaved.")
        else:
            await session.rollback()
            print("\nDry run — nothing saved. Re-run with --apply to persist.")

    print(f"\n{processed} club(s) rescored, {total_selections} selection(s) counted, "
          f"{changed} score/tier change(s), {errors} error(s)")
    if moved_tier:
        print("\n  tier changes:")
        for cname, was, now in moved_tier:
            print(f"    {(cname or '?')[:50]:<50} {was or '-'} -> {now or '-'}")
    return {"processed": processed, "changed": changed, "errors": errors,
            "selections": total_selections}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true",
                    help="persist the rescored values (default is a dry run)")
    ap.add_argument("--name", help="only clubs whose name contains this substring")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    asyncio.run(backfill(apply=args.apply, name=args.name))


if __name__ == "__main__":
    main()
