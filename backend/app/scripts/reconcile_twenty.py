"""One-time reconciliation: bring Twenty CRM up to date with the current
BetterComms <-> Twenty business rules.

This is a backfill, not a new sync path — every rule it applies is the same code
the ongoing sync already runs (twenty_sync / twenty_leads_tasks / twenty_inbound),
so this script just makes sure every club the rules already say should be in
Twenty actually is, right now, and that every already-linked club's lifecycle
stage / engagement tier / Lead / suppression state reflects the corrected rules:

  - a club that's ever been emailed, synced (an organisations row exists), had a
    trial requested/started, has a demo status set, or is the target of an
    attributable "Get your club on BetterCricket" / "Request access" website
    enquiry should already be a Company in Twenty (Target by default; Prospect
    once synced or a trial's been asked for) — Step 1 enrols any club matching
    that but missing from twenty_links.
  - engagement score/tier (Warm 30-45, Hot >45) and lifecycle stage (synced alone
    is never Customer; only a genuinely paid module is) — Step 2 recomputes both
    for every already-linked club. The score itself now also accounts for: real
    per-module trial subscriptions a super admin started (not just the directory's
    aspirational trial_modules flag), raw page-view/API volume on a club's UTM
    code or org (not just distinct-visitor count), and a direct onboarding
    enquiry (the single strongest prospect signal — scores above requested-trial).
  - a club whose every named-email officer has unsubscribed/bounced/complained is
    Suppressed, with its Lead discarded and any open Opportunity marked Lost /
    Dormant — folded into Step 2's refresh_engagement pass.
  - a Lead exists for every club that requested a trial, is trialing, is synced
    but not yet paying, is in the engagement sales cycle, submitted a direct
    onboarding enquiry (sourced "Contact us"), or has crossed a score of 45 —
    Step 3 seeds/refreshes Leads, mirrors outstanding module trial requests to
    Tasks, and scans trials/renewals coming due.
  - syncing a club (organisations.py::onboard_organisation) and starting a real
    module trial (club_admin.py::start_module_trial) now both push to Twenty
    immediately in addition to this backfill — this script is for everything
    that happened before those hooks existed, or while Twenty was unreachable.

Usage from the backend container:
  docker exec -e PYTHONPATH=/app betterstats-backend \\
    python -m app.scripts.reconcile_twenty

Safe to re-run: every write here is idempotent/keyed (twenty_links + Twenty's own
external-key upserts), so running it twice just confirms nothing has drifted.
"""
import asyncio
import logging

from sqlalchemy import select, text

from app.models.db import MarketingClub, MarketingClubContact, async_session_maker
from app.services import twenty_leads_tasks, twenty_sync
from app.services.twenty_client import client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Politeness gap between per-club pushes in step 1 (twenty_client's own rate
# limiter is the real throttle; this just spaces out the session/http churn).
_PACE_SECONDS = 0.05


async def _clubs_missing_from_crm() -> list:
    """Every club the rules already say belongs in Twenty (ever emailed, synced,
    trialing/requested a trial, carrying a demo status, or the target of an
    attributable "onboard my club" website enquiry) but with no ``twenty_links``
    row yet — i.e. a club BetterComms/BetterCricket has already interacted with in
    a way that should have enrolled it, but hasn't.

    The onboarding-enquiry match is deliberately narrower here than the one
    ``twenty_sync._onboarding_signal`` uses for scoring (email-against-known-officer
    only, no UTM/name fallback) — this gate decides whether to enrol a WHOLE club
    into the CRM, so it stays on the highest-precision signal; the scoring signal
    just needs to be directionally right, not this strict."""
    async with async_session_maker() as session:
        rows = (await session.execute(text("""
            SELECT mc.id
            FROM marketing_clubs mc
            WHERE mc.excluded = false AND mc.kind = 'club'
              AND (
                mc.emailed_at IS NOT NULL
                OR mc.existing_org_id IS NOT NULL
                OR mc.demo_status IS NOT NULL
                OR jsonb_array_length(COALESCE(mc.trial_modules, '[]'::jsonb)) > 0
                OR jsonb_array_length(COALESCE(mc.requested_trial_modules, '[]'::jsonb)) > 0
                OR EXISTS (
                  SELECT 1 FROM club_onboarding_requests cor
                  WHERE cor.email IS NOT NULL AND cor.email <> ''
                    AND lower(cor.email) IN (
                      SELECT lower(email) FROM marketing_club_contacts
                      WHERE marketing_club_id = mc.id AND email IS NOT NULL AND email <> '')
                )
              )
              AND NOT EXISTS (
                SELECT 1 FROM twenty_links tl
                WHERE tl.entity_type = 'club' AND tl.bc_id = mc.grassroots_guid
              )
            ORDER BY mc.name
        """))).all()
        return [r[0] for r in rows]


async def _named_contact_ids(club_id) -> list:
    """Every contact of this club with a usable email — the full backfill set,
    not just the forward-looking ``outreach_selected`` tick (a club that was
    emailed via an older flow may never have had that flag set)."""
    async with async_session_maker() as session:
        rows = (await session.execute(
            select(MarketingClubContact.id).where(
                MarketingClubContact.marketing_club_id == club_id,
                MarketingClubContact.email.isnot(None),
                MarketingClubContact.email != "",
            )
        )).all()
        return [r[0] for r in rows]


async def step1_enrol_missing_clubs() -> dict:
    club_ids = await _clubs_missing_from_crm()
    logger.info("Step 1: %d club(s) qualify for Twenty but aren't linked yet", len(club_ids))
    ok = errors = 0
    for idx, club_id in enumerate(club_ids, start=1):
        contact_ids = await _named_contact_ids(club_id)
        result = await twenty_sync.push_club_and_contacts(club_id, contact_ids or None)
        if result.get("error"):
            errors += 1
            logger.warning("  [%d/%d] %s -> error: %s", idx, len(club_ids), club_id, result["error"])
        else:
            ok += 1
            logger.info("  [%d/%d] %s -> %s", idx, len(club_ids), club_id, result.get("club") or result)
        await asyncio.sleep(_PACE_SECONDS)
    return {"candidates": len(club_ids), "enrolled": ok, "errors": errors}


async def main() -> None:
    if not client.configured:
        print("Twenty is not configured (TWENTY_API_URL / TWENTY_API_KEY) — nothing to do.")
        return

    print("=== Step 1: enrol clubs the rules say should already be in Twenty ===")
    step1 = await step1_enrol_missing_clubs()
    print(f"  {step1}")

    print("\n=== Step 2: recompute engagement / lifecycle / suppression for every linked club ===")
    step2 = await twenty_sync.refresh_engagement()
    print(f"  {step2}")

    print("\n=== Step 3: seed/refresh Leads, mirror trial requests + renewals to Tasks ===")
    step3 = await twenty_leads_tasks.refresh_leads_and_tasks()
    print(f"  {step3}")

    print("\nDone. Twenty should now reflect every club/contact the current rules "
          "cover. Re-run any time — every step is idempotent.")


if __name__ == "__main__":
    asyncio.run(main())
