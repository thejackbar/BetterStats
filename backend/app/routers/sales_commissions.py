"""Sales Commissions — forecast on the open book, earned on the won one.

Super-admin only. Commission rates and payouts are management data about
staff pay, which is a different thing from the Sales Workspace's per-rep view
of their own clubs; nothing here is exposed to a 'sales'-role account, and the
service still takes a pin (``rep_user_id``) so opening it up later is a route
change rather than a rewrite.

Every figure comes from services/sales_commissions.py, which reads a deal's
value and likelihood through services/crm.py's own definitions — so a rep's
forecast and the Sales Pipeline board can never disagree about the same deal.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import User, get_db
from app.routers.auth import require_super_admin
from app.services import crm as crm_service
from app.services import sales_commissions as sc

router = APIRouter(prefix="/club-admin/sales-commissions", tags=["sales-commissions"])


def _uuid_or_422(value: str):
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=422, detail="Invalid id")


@router.get("")
async def overview(
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """The screen in one request: the per-rep table, the rates behind it, and
    the recent payouts. A commission screen that needed four round trips to
    say what one rep is owed would be four chances for two of them to
    disagree about the rate."""
    report = await sc.commission_report(db)
    rates = await sc.load_rates(db)
    reps = await crm_service.list_platform_owners(db, roles=("sales",))
    return {
        "rows": report["rows"],
        "totals": report["totals"],
        "default_rate_percent": report["default_rate_percent"],
        "rate_set": report["rate_set"],
        "reps": [{
            "id": r["id"],
            "name": r["name"],
            "rate_percent": float(sc.rate_for(rates, r.get("ids") or [r["id"]])),
            "has_own_rate": any(a in rates["by_account"] for a in (r.get("ids") or [r["id"]])),
        } for r in reps],
        "payments": await sc.list_payments(db),
    }


@router.get("/periods")
async def periods(
    period_type: str = "quarter",
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Commission earned and paid per quarter or per financial year. Periods
    are ``crm_targets``' own — a calendar quarter, and a 1 Jul to 30 Jun
    financial year named for the year it ends in — so a commission period and
    a sales target period mean the same thing."""
    if period_type not in ("quarter", "fiscal_year"):
        raise HTTPException(status_code=422, detail="Unknown period type")
    return await sc.period_summary(db, period_type=period_type)


@router.get("/deals")
async def deals(
    rep_user_id: str,
    status: str = "open",
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """The deals behind one figure on the table — the forecast pipeline for a
    rep, or the deals they have won."""
    try:
        return await sc.rep_deals(db, rep_user_id=rep_user_id, status=status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


class RateBody(BaseModel):
    # None means the platform default — the rate a rep with no rate of their
    # own is paid at. An explicit key, rather than a magic id, so "set the
    # default" can never be confused with "set this person's".
    user_id: Optional[str] = None
    rate_percent: float


@router.put("/rate")
async def set_rate(
    body: RateBody,
    actor: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Set a rep's commission rate, or the platform default.

    Changing a rate never rewrites commission already earned: a deal carries
    the rate that applied when it was won (``crm_deals.commission_rate_percent``).
    It does move every forecast figure, which is the point — a forecast is
    about what is still to come."""
    user_id = _uuid_or_422(body.user_id) if body.user_id else None
    try:
        rate = await sc.set_rate(db, user_id=user_id, rate_percent=body.rate_percent,
                                actor_user_id=actor.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return {"user_id": body.user_id, "rate_percent": float(rate)}


@router.delete("/rate/{user_id}")
async def clear_rate(
    user_id: str,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Drop a rep's own rate so they fall back to the platform default. The
    default row itself is never deletable — every rep would then have no rate
    at all."""
    from sqlalchemy import delete as _delete

    from app.models.db import SalesCommissionRate
    uid = _uuid_or_422(user_id)
    await db.execute(_delete(SalesCommissionRate).where(SalesCommissionRate.user_id == uid))
    await db.commit()
    return {"cleared": True}


class PaymentBody(BaseModel):
    rep_user_id: str
    amount_cents: int
    paid_on: date
    reference: Optional[str] = None
    note: Optional[str] = None


@router.post("/payments")
async def add_payment(
    body: PaymentBody,
    actor: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Record a commission payout. It reduces what that rep is owed by
    exactly its amount — commission due is earned minus paid, so nothing else
    moves the figure."""
    rep_id = _uuid_or_422(body.rep_user_id)
    try:
        payment = await sc.record_payment(
            db, rep_user_id=rep_id, amount_cents=body.amount_cents, paid_on=body.paid_on,
            reference=body.reference, note=body.note, actor_user_id=actor.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return {"id": str(payment.id)}


@router.delete("/payments/{payment_id}")
async def remove_payment(
    payment_id: str,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a payout recorded by mistake. A payment that really happened and
    was entered WRONGLY is better corrected with an offsetting negative entry,
    which leaves both in the ledger — this is for one that never happened."""
    if not await sc.delete_payment(db, _uuid_or_422(payment_id)):
        raise HTTPException(status_code=404, detail="Payment not found")
    await db.commit()
    return {"deleted": True}
