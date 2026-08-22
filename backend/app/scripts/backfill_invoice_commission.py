"""Fill in the commissionable columns on invoices recorded before migration 278.

``billing_invoices`` has mirrored every Stripe invoice for a while, but only
since 278 does it record the two things sales commission needs: Stripe's
``billing_reason`` (which separates new business from a renewal) and the
amount NET OF GST. Neither can be derived from what was already stored, so
this re-reads each invoice from Stripe and stamps them.

Commission itself is then recomputed through the SAME
``sales_commissions.record_payment_commission`` the webhook uses, so a
backfilled payment and a live one are stamped by one piece of code. The rate
applied is the rep's CURRENT rate — the rate that applied on the day of a
past payment was never recorded, and inventing one would be worse than saying
so. Already-stamped invoices are left alone.

    python -m app.scripts.backfill_invoice_commission            # dry run
    python -m app.scripts.backfill_invoice_commission --apply
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.models.db import BillingInvoice, async_session_maker
from app.services import sales_commissions as sc
from app.services import stripe_client


async def run(apply: bool) -> int:
    async with async_session_maker() as session:
        rows = (await session.execute(
            select(BillingInvoice).where(BillingInvoice.billing_reason.is_(None))
            .order_by(BillingInvoice.created_at)
        )).scalars().all()
        if not rows:
            print("Every recorded invoice already carries its billing reason.")
            return 0

        print(f"{len(rows)} invoice(s) to look up in Stripe:\n")
        done = 0
        for row in rows:
            try:
                invoice = await stripe_client.retrieve_invoice(row.stripe_invoice_id)
            except Exception as exc:  # noqa: BLE001 - one bad id can't stop the rest
                print(f"  {row.stripe_invoice_id}  could not be read from Stripe: {exc}")
                continue
            row.billing_reason = invoice.get("billing_reason")
            row.amount_ex_tax_cents = sc.invoice_ex_tax_cents(invoice)
            await sc.record_payment_commission(session, row)
            earns = (f"{row.commission_kind} -> ${(row.commission_cents or 0) / 100:,.2f}"
                     if row.commission_kind else "earns nothing")
            print(f"  {row.stripe_invoice_id}  {row.billing_reason or '?':<22}"
                  f"  ex-GST ${(row.amount_ex_tax_cents or 0) / 100:>9,.2f}  {earns}")
            done += 1

        if apply:
            await session.commit()
            print(f"\nStamped {done} invoice(s).")
        else:
            print(f"\nDry run — nothing written. Re-run with --apply to stamp these {done}.")
    return done


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the stamped values")
    args = parser.parse_args()
    asyncio.run(run(args.apply))


if __name__ == "__main__":
    main()
