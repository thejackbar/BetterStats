"""Backfill / refresh the Contact Name / Email / Mobile on CRM deals.

WHY
    Until this fix, some deal-creation paths (most notably a completed
    self-serve trial registration — crm.sync_self_serve_trial_registration)
    created the deal but never linked a CrmPerson contact, and the contact
    resolution itself has since been corrected. This re-applies the current
    resolution to EVERY deal so both the empty ones and the ones that got a
    wrong/stale contact end up pointing at the club's best-known contact.

WHAT
    For every OPEN, non-archived deal, resolve the club's best-known contact
    (crm.best_known_contact_for_deal, in priority order: the self-serve
    registering admin, else the linked org's PRIMARY admin user — the
    /admin/super/clubs club-admin details, else a contactable club officer,
    else the club's role mailbox) and set it as the deal's point of contact.
    An existing point of contact is DEMOTED (kept as a linked contact, just no
    longer the POC), never deleted — no history is lost. A deal for which no
    contact can be resolved at all is left exactly as-is.

    By default this runs over ALL deals (updating those with a wrong/missing
    contact and re-confirming the rest — idempotent, so re-runs are safe).
    Pass --only-missing to touch only deals that have no linked contact yet.
    Pass --include-closed to also process won/lost/archived deals.

USAGE (inside the backend container)
    python -m app.scripts.backfill_deal_contacts               # dry run, ALL deals
    python -m app.scripts.backfill_deal_contacts --apply       # write, ALL deals
    python -m app.scripts.backfill_deal_contacts --apply --only-missing
    python -m app.scripts.backfill_deal_contacts --apply --include-closed
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.models.db import async_session_maker, CrmDeal, CrmDealContact
from app.services import crm as crm_service


def _label(contact: dict | None) -> str:
    # `best_known_contact_for_deal` uses full_name/email/phone; the current-POC
    # dict from poc_contacts_by_deal uses name/email (no phone) — handle both.
    if not contact:
        return "—"
    name = contact.get("full_name") or contact.get("name")
    return " / ".join(
        str(v) for v in (name, contact.get("email"), contact.get("phone")) if v
    ) or "—"


async def run(apply: bool, include_closed: bool, only_missing: bool) -> None:
    async with async_session_maker() as session:
        stmt = select(CrmDeal)
        if only_missing:
            stmt = (stmt.outerjoin(CrmDealContact, CrmDealContact.deal_id == CrmDeal.id)
                    .where(CrmDealContact.id.is_(None)))
        if not include_closed:
            stmt = stmt.where(CrmDeal.status == "open", CrmDeal.archived_at.is_(None))
        stmt = stmt.order_by(CrmDeal.created_at.asc())
        deals = (await session.execute(stmt)).scalars().all()

        scope = "with no linked contact" if only_missing else "total"
        print(f"{len(deals)} deal(s) {scope}"
              + ("" if include_closed else " (open, non-archived)") + ".")
        if not deals:
            return

        # Current point of contact per deal, for the before/after report.
        poc = await crm_service.poc_contacts_by_deal(session, [d.id for d in deals])

        updated, skipped = 0, 0
        for deal in deals:
            best = await crm_service.best_known_contact_for_deal(session, deal)
            if best is None:
                skipped += 1
                print(f"  SKIP  {deal.title!r} ({deal.id}) — no contact on file")
                continue
            cur = poc.get(deal.id)
            arrow = f"{_label(cur)}  ->  {_label(best)}"
            if apply:
                await crm_service.ensure_deal_contact(session, deal, force=True)
                updated += 1
                print(f"  SET   {deal.title!r} ({deal.id}): {arrow}")
            else:
                updated += 1
                print(f"  WOULD {deal.title!r} ({deal.id}): {arrow}")

        if apply:
            await session.commit()

        verb = "Set point of contact on" if apply else "Would set point of contact on"
        print(f"\n{verb} {updated} deal(s); {skipped} had no contact on file"
              + ("" if apply else "  (dry run — pass --apply to write)."))


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Backfill / refresh the Contact Name/Email/Mobile on CRM deals.")
    ap.add_argument("--apply", action="store_true",
                    help="write the contact links (default: dry run / report only)")
    ap.add_argument("--only-missing", action="store_true",
                    help="only touch deals that have no linked contact yet "
                         "(default: re-apply to ALL deals)")
    ap.add_argument("--include-closed", action="store_true",
                    help="also process won/lost/archived deals (default: open, non-archived only)")
    args = ap.parse_args()
    asyncio.run(run(args.apply, args.include_closed, args.only_missing))


if __name__ == "__main__":
    main()
