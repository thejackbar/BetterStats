"""Backfill missing Contact Name / Email / Mobile on CRM deals.

WHY
    Until this fix, some deal-creation paths (most notably a completed
    self-serve trial registration — crm.sync_self_serve_trial_registration)
    created the deal but never linked a CrmPerson contact, so the deal card's
    Contact Name / Email / Mobile came up empty even though the registration
    supplied all three. Those paths now seed the contact via
    crm.ensure_deal_contact; this script fixes the deals that were created
    before the fix landed.

WHAT
    For every OPEN, non-archived deal that has NO linked contact, resolve the
    club's best-known contact (crm.best_known_contact_for_deal, in priority
    order: the self-serve registering admin, else the linked org's PRIMARY
    admin user — the /admin/super/clubs club-admin details, else any other
    directory contact, else the club's role mailbox) and link it as the point
    of contact.
    Idempotent and resumable: a deal that already has a contact is skipped, so
    a re-run only touches the ones still missing one. Deals a super admin
    closed (won/lost) or archived are left alone — the pipeline only shows the
    open ones, and back-writing a contact onto historical rows adds no value.

    Pass --include-closed to also fill won/lost/archived deals if ever needed.

USAGE (inside the backend container)
    python -m app.scripts.backfill_deal_contacts            # dry run (report only)
    python -m app.scripts.backfill_deal_contacts --apply    # write the links
    python -m app.scripts.backfill_deal_contacts --apply --include-closed
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.models.db import async_session_maker, CrmDeal, CrmDealContact
from app.services import crm as crm_service


async def run(apply: bool, include_closed: bool) -> None:
    async with async_session_maker() as session:
        stmt = (
            select(CrmDeal)
            .outerjoin(CrmDealContact, CrmDealContact.deal_id == CrmDeal.id)
            .where(CrmDealContact.id.is_(None))
            .order_by(CrmDeal.created_at.asc())
        )
        if not include_closed:
            stmt = stmt.where(CrmDeal.status == "open", CrmDeal.archived_at.is_(None))
        deals = (await session.execute(stmt)).scalars().all()

        print(f"{len(deals)} deal(s) with no linked contact"
              + ("" if include_closed else " (open, non-archived)") + ".")
        if not deals:
            return

        linked, skipped = 0, 0
        for deal in deals:
            best = await crm_service.best_known_contact_for_deal(session, deal)
            if best is None:
                skipped += 1
                print(f"  SKIP  {deal.title!r} ({deal.id}) — no contact on file")
                continue
            label = " / ".join(
                str(v) for v in (best.get("full_name"), best.get("email"), best.get("phone")) if v)
            if apply:
                await crm_service.ensure_deal_contact(session, deal)
                linked += 1
                print(f"  LINK  {deal.title!r} ({deal.id}) -> {label}")
            else:
                linked += 1
                print(f"  WOULD {deal.title!r} ({deal.id}) -> {label}")

        if apply:
            await session.commit()

        verb = "Linked" if apply else "Would link"
        print(f"\n{verb} {linked} deal(s); {skipped} had no contact on file"
              + ("" if apply else "  (dry run — pass --apply to write)."))


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Backfill missing Contact Name/Email/Mobile on CRM deals.")
    ap.add_argument("--apply", action="store_true",
                    help="write the contact links (default: dry run / report only)")
    ap.add_argument("--include-closed", action="store_true",
                    help="also fill won/lost/archived deals (default: open, non-archived only)")
    args = ap.parse_args()
    asyncio.run(run(args.apply, args.include_closed))


if __name__ == "__main__":
    main()
