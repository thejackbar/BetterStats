"""Backfill marketing_clubs.existing_org_id for onboarded clubs left unlinked.

WHY
    A self-serve registration links a club's directory row to its onboarded
    Organisation at signup (twenty_sync._resolve_self_serve_club). A club a
    super admin onboards/syncs and then trials does NOT get that link, so its
    marketing_clubs.existing_org_id stays NULL. Everything the CRM card reads
    about the org's subscription flows through that link
    (crm.trial_days_remaining_by_club / subscribed_modules_by_club), so an
    unlinked club shows neither its expired-trial state nor the trial
    hourglass on its deal, even though the org is really trialing. (Reported
    for Baden Powell Cricket Club — org had a status='trial' core subscription,
    the marketing_club had existing_org_id = NULL.)

WHAT
    For every marketing_club with existing_org_id IS NULL, run the SAME match
    the directory crawl uses (club_directory._link_existing_org: PlayHQ
    routingCode, then the CA org guid, then an exact case-insensitive name) and
    stamp existing_org_id when a matching Organisation is found. Only touches
    NULL rows, so it never repoints an already-linked club; idempotent and
    resumable.

USAGE (inside the backend container)
    python -m app.scripts.backfill_marketing_club_org_links            # dry run
    python -m app.scripts.backfill_marketing_club_org_links --apply     # write
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.models.db import async_session_maker, MarketingClub
from app.services.club_directory import _link_existing_org


async def run(apply: bool) -> None:
    async with async_session_maker() as session:
        clubs = (await session.execute(
            select(MarketingClub)
            .where(MarketingClub.existing_org_id.is_(None))
            .order_by(MarketingClub.name.asc())
        )).scalars().all()

        print(f"{len(clubs)} marketing_club(s) with no linked org.")
        linked = 0
        for club in clubs:
            before = club.existing_org_id
            await _link_existing_org(session, club)
            if club.existing_org_id and club.existing_org_id != before:
                linked += 1
                verb = "LINK " if apply else "WOULD"
                print(f"  {verb} {club.name!r} ({club.id}) -> org {club.existing_org_id}")
            elif not apply:
                # Leave NULL rows exactly as they were on a dry run.
                club.existing_org_id = before

        if apply:
            await session.commit()

        verb = "Linked" if apply else "Would link"
        print(f"\n{verb} {linked} club(s)"
              + ("" if apply else "  (dry run — pass --apply to write)."))


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Link marketing_clubs to their onboarded Organisation (existing_org_id).")
    ap.add_argument("--apply", action="store_true",
                    help="write the links (default: dry run / report only)")
    args = ap.parse_args()
    asyncio.run(run(args.apply))


if __name__ == "__main__":
    main()
