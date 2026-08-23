"""One-off diagnostic: why doesn't club X have a Twenty Lead right now?

Walks the exact gate chain _seed_and_refresh_leads uses, for one or more named
clubs, and prints where it stops (or the Lead signal it would produce).
Read-only — makes no writes, no Twenty API calls.

Usage from the backend container (name match is case-insensitive substring):
  docker exec -e PYTHONPATH=/app betterstats-backend \\
    python -m app.scripts.diagnose_club_lead "tasmania police"
"""
import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.db import MarketingClub, Organisation, async_session_maker
from app.services import platform_settings, twenty_sync
from app.services.twenty_leads_tasks import _lead_signal
from app.services.twenty_sync import (
    _all_contacts_unsubscribed, _engagement, _link_get, _module_split,
    _onboarding_signal,
)


async def diagnose(name_query: str) -> None:
    async with async_session_maker() as session:
        clubs = (await session.execute(
            select(MarketingClub).where(
                MarketingClub.name.ilike(f"%{name_query}%"),
                MarketingClub.kind == "club",
            )
        )).scalars().all()
        if not clubs:
            print(f"No club matching {name_query!r} in marketing_clubs.")
            return

        for club in clubs:
            print(f"\n=== {club.name} ({club.id}) ===")
            print(f"  utm_code: {club.utm_code!r}")
            print(f"  excluded={club.excluded} not_interested={club.not_interested} "
                  f"emailed_at={club.emailed_at} demo_status={club.demo_status} "
                  f"existing_org_id={club.existing_org_id}")
            print(f"  trial_modules={club.trial_modules} "
                  f"requested_trial_modules={club.requested_trial_modules}")

            link_row = await _link_get(session, "club", club.grassroots_guid)
            if not link_row:
                print("  -> STOP: not a Company in Twenty yet (no twenty_links 'club' row). "
                      "This is almost always why a high-traffic club shows no Lead — "
                      "raw traffic alone doesn't enrol a club, see reconcile_twenty.py's "
                      "Step 1 gate (emailed_at / synced / trial / onboarding enquiry).")
                continue
            print(f"  Company twenty_id: {link_row[0]}")

            lead_row = await _link_get(session, "lead", club.grassroots_guid)
            print(f"  Existing Lead twenty_id: {lead_row[0] if lead_row else None}")

            if club.not_interested:
                print("  -> STOP: not_interested=True forces score=0 and no Lead, "
                      "regardless of traffic.")
                continue

            org = (await session.get(
                        Organisation, club.existing_org_id,
                        options=[selectinload(Organisation.module_subscriptions)])
                   if club.existing_org_id else None)
            paid, _trial, _renewals = _module_split(org) if org is not None else ([], [], [])
            is_paying = bool(paid) or (club.demo_status or "") == "customer"
            org_slug = getattr(org, "slug", None) if org is not None else None
            print(f"  org_slug (for path-attributed traffic): {org_slug!r}")

            ob_count, ob_last = await _onboarding_signal(session, club, club.utm_code, org_slug)
            print(f"  Onboarding/contact-form requests attributed to this club: "
                  f"{ob_count} (most recent: {ob_last})")

            all_unsub = await _all_contacts_unsubscribed(session, club.id)
            if all_unsub and not is_paying:
                print("  -> STOP: every named-email officer has unsubscribed/bounced/"
                      "complained — the club is suppressed, any existing Lead gets "
                      "discarded rather than refreshed.")
                continue

            eng = await _engagement(session, club, org)
            print(f"  Computed engagement: score={eng.get('engagementScore')} "
                  f"tier={eng.get('engagementTier')} sessions30d={eng.get('sessions30d')} "
                  f"emailEngaged30d={eng.get('emailEngaged30d')} "
                  f"inSalesCycle={eng.get('inSalesCycle')}")
            print(f"    breakdown: recencyPts={eng.get('_recencyPts')} "
                  f"emailDecayPts={eng.get('_emailDecayPts')} "
                  f"webDecayPts={eng.get('_webDecayPts')} "
                  f"adDecayPts={eng.get('_adDecayPts')} (adClicks={eng.get('_adClicks')}, "
                  f"adSignup={eng.get('_adSignup')}) "
                  f"freqPts={eng.get('_freqPts')} (reach capped 24 + depth capped 40 "
                  f"= 64 max; emailDecayPts=0 with real opens/clicks sent means SES open/click "
                  f"tracking is likely OFF — see app.scripts.email_opens)")
            if eng.get('_directEnquiryHot'):
                hot_days = await platform_settings.get_direct_enquiry_hot_days(session)
                print(f"    -> score is forced to {twenty_sync.DIRECT_ENQUIRY_SCORE}/HOT: a direct onboarding enquiry within "
                      f"the last {hot_days} days (General Settings > Marketing > Direct "
                      f"enquiry hot days), not yet won (paying) or lost (not_interested).")

            synced = bool(club.existing_org_id) and not is_paying
            sig = _lead_signal(club, org, eng, synced=synced)
            if sig is None:
                print("  -> RESULT: does not currently qualify as a Lead "
                      "(no trial/interest/sync/onboarding signal, inSalesCycle=False, "
                      "and score < 45).")
            else:
                print(f"  -> RESULT: QUALIFIES as a Lead (source={sig['source']}, "
                      f"tier={sig['tier']}, score={sig['score']}). If it's still missing "
                      f"in Twenty, refresh_leads_and_tasks() (reconcile_twenty.py) simply "
                      f"hasn't been run since this became true.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m app.scripts.diagnose_club_lead \"<club name or partial>\"")
        sys.exit(1)
    asyncio.run(diagnose(sys.argv[1]))
