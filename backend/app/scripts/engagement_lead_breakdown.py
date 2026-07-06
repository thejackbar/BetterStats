"""Full engagement-score breakdown for every club that currently has a Twenty
Lead — one row per component (recency, email decay, web decay, frequency,
bonuses) so a score can be audited/explained, not just observed.

Walks the exact same code path _engagement()/_lead_signal() use (twenty_sync,
twenty_leads_tasks) — this is a report, not a separate scoring implementation,
so it can never drift from what Twenty actually gets pushed. Read-only —
makes no writes, no Twenty API calls.

Usage from the backend container:
  docker exec -e PYTHONPATH=/app betterstats-backend \\
    python -m app.scripts.engagement_lead_breakdown

  # also write a CSV (inside the container; docker cp it out afterwards):
  docker exec -e PYTHONPATH=/app betterstats-backend \\
    python -m app.scripts.engagement_lead_breakdown --csv /tmp/lead_breakdown.csv
  docker cp betterstats-backend:/tmp/lead_breakdown.csv ./lead_breakdown.csv

Sorted by engagementScore descending — highest-priority Leads first.
"""
import asyncio
import csv
import sys

from sqlalchemy import text

from app.models.db import MarketingClub, Organisation, async_session_maker
from app.services.twenty_leads_tasks import _lead_signal
from app.services.twenty_sync import (
    _all_contacts_unsubscribed, _engagement, _lifecycle, _link_get, _module_split,
)

_CSV_FIELDS = [
    "club_name", "lead_twenty_id", "company_twenty_id",
    "engagement_score", "engagement_tier", "lifecycle_stage",
    "recency_pts", "email_decay_pts", "web_decay_pts", "freq_pts",
    "sessions_30d", "email_engaged_30d", "in_sales_cycle",
    "is_customer", "synced_not_paying", "upsell_modules",
    "requested_trial_modules", "demo_status", "onboarding_requested",
    "lead_source", "lead_status", "last_seen_at",
]


async def _leads() -> list:
    """(club_id, lead_twenty_id) for every club with a Lead in Twenty right now,
    ordered by name — the source list this report walks."""
    async with async_session_maker() as session:
        rows = (await session.execute(text("""
            SELECT mc.id, tl.twenty_id
            FROM twenty_links tl
            JOIN marketing_clubs mc ON mc.grassroots_guid = tl.bc_id AND mc.kind = 'club'
            WHERE tl.entity_type = 'lead'
            ORDER BY mc.name
        """))).all()
        return [(r[0], r[1]) for r in rows]


async def _row_for(club_id, lead_tid: str) -> "dict | None":
    async with async_session_maker() as session:
        club = await session.get(MarketingClub, club_id)
        if club is None:
            return None
        company_row = await _link_get(session, "club", club.grassroots_guid)
        company_tid = company_row[0] if company_row else None

        org = (await session.get(Organisation, club.existing_org_id)
               if club.existing_org_id else None)
        paid, _trial, _renewals = _module_split(org) if org is not None else ([], [], [])
        is_paying = bool(paid) or (club.demo_status or "") == "customer"
        all_unsub = await _all_contacts_unsubscribed(session, club.id)

        eng = await _engagement(session, club, org)
        synced = bool(club.existing_org_id) and not is_paying
        sig = _lead_signal(club, org, eng, synced=synced)
        lifecycle = _lifecycle(club, is_paying, all_unsub)

        return {
            "club_name": club.name,
            "lead_twenty_id": lead_tid,
            "company_twenty_id": company_tid,
            "engagement_score": eng.get("engagementScore"),
            "engagement_tier": eng.get("engagementTier"),
            "lifecycle_stage": lifecycle,
            "recency_pts": eng.get("_recencyPts"),
            "email_decay_pts": eng.get("_emailDecayPts"),
            "web_decay_pts": eng.get("_webDecayPts"),
            "freq_pts": eng.get("_freqPts"),
            "sessions_30d": eng.get("sessions30d"),
            "email_engaged_30d": eng.get("emailEngaged30d"),
            "in_sales_cycle": eng.get("inSalesCycle"),
            "is_customer": is_paying,
            "synced_not_paying": synced,
            "upsell_modules": ",".join(eng.get("upsellModules") or []),
            "requested_trial_modules": ",".join(club.requested_trial_modules or []),
            "demo_status": club.demo_status,
            "onboarding_requested": bool(eng.get("_onboardingRequested")),
            "lead_source": sig["source"] if sig else None,
            "lead_status": sig["status"] if sig else None,
            "last_seen_at": eng.get("lastSeenAt"),
        }


def _print_row(r: dict) -> None:
    print(f"\n=== {r['club_name']} ===")
    print(f"  Lead: {r['lead_twenty_id']}   Company: {r['company_twenty_id']}")
    print(f"  engagementScore={r['engagement_score']}  tier={r['engagement_tier']}  "
          f"lifecycleStage={r['lifecycle_stage']}  leadStatus={r['lead_status']}  "
          f"leadSource={r['lead_source']}")
    print(f"  Breakdown: recencyPts={r['recency_pts']}  emailDecayPts={r['email_decay_pts']}  "
          f"webDecayPts={r['web_decay_pts']}  freqPts={r['freq_pts']} (capped at 60)")
    print(f"  Volume:    sessions30d={r['sessions_30d']}  emailEngaged30d={r['email_engaged_30d']}  "
          f"inSalesCycle={r['in_sales_cycle']}  lastSeenAt={r['last_seen_at']}")
    print(f"  Account:   isCustomer={r['is_customer']}  syncedNotPaying={r['synced_not_paying']}  "
          f"upsellModules={r['upsell_modules'] or '-'}")
    print(f"  Intent:    requestedTrialModules={r['requested_trial_modules'] or '-'}  "
          f"demoStatus={r['demo_status'] or '-'}  onboardingRequested={r['onboarding_requested']}")


async def main() -> None:
    csv_path = None
    if "--csv" in sys.argv:
        idx = sys.argv.index("--csv")
        if idx + 1 >= len(sys.argv):
            print("Usage: --csv <path>")
            sys.exit(1)
        csv_path = sys.argv[idx + 1]

    leads = await _leads()
    print(f"{len(leads)} club(s) currently have a Twenty Lead. Computing breakdown for each "
          f"(read-only, no writes)...")

    rows = []
    for club_id, lead_tid in leads:
        row = await _row_for(club_id, lead_tid)
        if row is not None:
            rows.append(row)

    rows.sort(key=lambda r: (r["engagement_score"] if r["engagement_score"] is not None else -1),
              reverse=True)

    for r in rows:
        _print_row(r)

    print(f"\n{len(rows)} Lead(s) reported, sorted by engagementScore descending.")

    if csv_path:
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        print(f"CSV written to {csv_path}")


if __name__ == "__main__":
    asyncio.run(main())
