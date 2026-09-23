"""The pay link in an invoice email (unauthenticated, migration 308).

``GET /public/billing/pay/{token}`` resolves the invoice from its unguessable
``pay_token`` and redirects to Stripe's hosted payment page for it, where the
club pays with whatever payment methods the Stripe account offers. No login:
the person paying is often the club treasurer reading the email on a phone,
and the token only ever unlocks the chance to PAY one invoice, which is not
something worth protecting from the person holding the email.

Why a redirect rather than putting Stripe's own URL in the email: it always
lands on the invoice's CURRENT page, it asks Stripe (not our row) whether the
invoice is still payable — so a webhook that has not landed yet can never send
somebody to pay twice — and once the invoice is settled or voided the link
lands on the club's Account page saying so, instead of on a dead Stripe page.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.models.db import BillingInvoice, get_db
from app.services import stripe_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public/billing", tags=["public-billing"])


def _account(state: str) -> RedirectResponse:
    return RedirectResponse(f"{settings.public_base_url}/admin/account?invoice={state}", status_code=303)


@router.get("/pay/{token}")
async def pay_invoice(token: str, db: AsyncSession = Depends(get_db)):
    row = None
    if token and len(token) <= 128:
        row = (await db.execute(
            select(BillingInvoice).where(BillingInvoice.pay_token == token)
        )).scalar_one_or_none()
    if row is None:
        return _account("not-found")
    if row.status in ("paid", "void", "uncollectible"):
        return _account("paid" if row.status == "paid" else "void")

    url = row.hosted_invoice_url
    try:
        invoice = await stripe_client.retrieve_invoice(row.stripe_invoice_id)
        status = invoice.get("status")
        if status == "paid":
            return _account("paid")
        if status in ("void", "uncollectible"):
            return _account("void")
        url = invoice.get("hosted_invoice_url") or url
    except Exception:
        # Stripe unreachable: the stored page is still the right place to pay,
        # and Stripe's own page refuses a second payment regardless.
        logger.exception("pay link: could not refresh Stripe invoice %s", row.stripe_invoice_id)
    if not url:
        return _account("unavailable")
    return RedirectResponse(url, status_code=303)
