"""BetterMerch service layer — stock movements, alerts and reporting.

Stock lives on a variant as a running `quantity`. Every change goes through
`record_movement`, which updates the balance and writes a MerchMovement audit
row in one go. Alerts (low stock / expiring / service due) are computed on read,
so there is no alert table to keep in sync.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import MerchProduct, MerchVariant, MerchMovement, MerchAsset


DEFAULT_ALERT_HORIZON_DAYS = 30

# Movement kinds that move stock OUT (a signed delta is still passed in, but
# these are the ones a stock-on-hand check guards against overselling).
OUTFLOW_KINDS = ("sold", "issued", "used", "write_off")
# Kinds that can carry money owed to the club (a player sale / kit issue).
MONEY_KINDS = ("sold", "issued")


def variant_threshold(variant: MerchVariant, product: MerchProduct | None) -> int | None:
    """The reorder point in force for a variant: its own override, else the
    product default, else None (no low-stock alert)."""
    if variant.low_stock_threshold is not None:
        return variant.low_stock_threshold
    if product is not None and product.low_stock_threshold is not None:
        return product.low_stock_threshold
    return None


def is_low_stock(variant: MerchVariant, product: MerchProduct | None) -> bool:
    thresh = variant_threshold(variant, product)
    return thresh is not None and (variant.quantity or 0) <= thresh


def record_movement(
    session: AsyncSession,
    variant: MerchVariant,
    *,
    kind: str,
    delta: int,
    unit_cost: Decimal | None = None,
    unit_price: Decimal | None = None,
    player_id=None,
    amount: Decimal | None = None,
    paid: bool = True,
    paid_at: date | None = None,
    payment_method: str | None = None,
    note: str | None = None,
    occurred_on: date | None = None,
    created_by_user_id=None,
    source: str = "manual",
    external_ref: str | None = None,
) -> MerchMovement:
    """Apply a stock change: bump the variant's running balance and write the
    audit row. Does NOT commit — the caller owns the transaction."""
    new_qty = (variant.quantity or 0) + int(delta)
    variant.quantity = new_qty
    mv = MerchMovement(
        variant_id=variant.id,
        organisation_id=variant.organisation_id,
        kind=kind,
        delta=int(delta),
        quantity_after=new_qty,
        unit_cost=unit_cost,
        unit_price=unit_price,
        player_id=player_id,
        amount=amount,
        paid=paid,
        paid_at=paid_at,
        payment_method=payment_method,
        note=note,
        occurred_on=occurred_on,
        created_by_user_id=created_by_user_id,
        source=source,
        external_ref=external_ref,
    )
    session.add(mv)
    return mv


async def merch_alerts(
    session: AsyncSession, org_id, *, horizon_days: int = DEFAULT_ALERT_HORIZON_DAYS
) -> dict:
    """Everything that needs attention right now, ready to render on the
    BetterMerch home and feed the notification bell.

    Returns three lists: low_stock, expiring, service_due.
    """
    today = date.today()
    horizon = today + timedelta(days=horizon_days)

    # ── Low stock ────────────────────────────────────────────────────────────
    thresh = func.coalesce(MerchVariant.low_stock_threshold, MerchProduct.low_stock_threshold)
    low_q = (
        select(MerchVariant, MerchProduct)
        .join(MerchProduct, MerchProduct.id == MerchVariant.product_id)
        .where(
            MerchVariant.organisation_id == org_id,
            MerchVariant.is_active.is_(True),
            MerchProduct.is_active.is_(True),
            thresh.isnot(None),
            MerchVariant.quantity <= thresh,
        )
        .order_by(MerchVariant.quantity.asc())
    )
    low_rows = (await session.execute(low_q)).all()
    low_stock = [
        {
            "variant_id": str(v.id),
            "product_id": str(p.id),
            "category": p.category,
            "product_name": p.name,
            "variant_label": v.label,
            "quantity": v.quantity,
            "threshold": variant_threshold(v, p),
        }
        for v, p in low_rows
    ]

    # ── Expiring food / drink ────────────────────────────────────────────────
    exp_q = (
        select(MerchVariant, MerchProduct)
        .join(MerchProduct, MerchProduct.id == MerchVariant.product_id)
        .where(
            MerchVariant.organisation_id == org_id,
            MerchVariant.is_active.is_(True),
            MerchProduct.is_active.is_(True),
            MerchVariant.expiry_date.isnot(None),
            MerchVariant.expiry_date <= horizon,
            MerchVariant.quantity > 0,
        )
        .order_by(MerchVariant.expiry_date.asc())
    )
    exp_rows = (await session.execute(exp_q)).all()
    expiring = [
        {
            "variant_id": str(v.id),
            "product_id": str(p.id),
            "category": p.category,
            "product_name": p.name,
            "variant_label": v.label,
            "quantity": v.quantity,
            "expiry_date": v.expiry_date.isoformat() if v.expiry_date else None,
            "expired": bool(v.expiry_date and v.expiry_date < today),
        }
        for v, p in exp_rows
    ]

    # ── Service / replace due (individual assets) ────────────────────────────
    asset_q = (
        select(MerchAsset)
        .where(
            MerchAsset.organisation_id == org_id,
            MerchAsset.is_active.is_(True),
            MerchAsset.status != "retired",
            (
                (MerchAsset.service_due_date.isnot(None) & (MerchAsset.service_due_date <= horizon))
                | (MerchAsset.replace_due_date.isnot(None) & (MerchAsset.replace_due_date <= horizon))
            ),
        )
        .order_by(func.coalesce(MerchAsset.service_due_date, MerchAsset.replace_due_date).asc())
    )
    assets = (await session.execute(asset_q)).scalars().all()
    service_due = []
    for a in assets:
        service_soon = a.service_due_date is not None and a.service_due_date <= horizon
        replace_soon = a.replace_due_date is not None and a.replace_due_date <= horizon
        service_due.append(
            {
                "asset_id": str(a.id),
                "name": a.name,
                "condition": a.condition,
                "service_due_date": a.service_due_date.isoformat() if a.service_due_date else None,
                "replace_due_date": a.replace_due_date.isoformat() if a.replace_due_date else None,
                "service_due": service_soon,
                "replace_due": replace_soon,
                "service_overdue": bool(a.service_due_date and a.service_due_date < today),
                "replace_overdue": bool(a.replace_due_date and a.replace_due_date < today),
            }
        )

    return {
        "low_stock": low_stock,
        "expiring": expiring,
        "service_due": service_due,
        "total": len(low_stock) + len(expiring) + len(service_due),
    }


async def count_merch_alerts(
    session: AsyncSession, org_id, *, horizon_days: int = DEFAULT_ALERT_HORIZON_DAYS
) -> int:
    """Cheap-ish total alert count for the notification badge."""
    alerts = await merch_alerts(session, org_id, horizon_days=horizon_days)
    return alerts["total"]


async def stock_summary(session: AsyncSession, org_id) -> dict:
    """Headline numbers for the BetterMerch overview: stock-on-hand at cost and
    at retail, the implied margin, and outstanding merch money (unpaid sales /
    issues to players)."""
    cost_expr = func.coalesce(MerchVariant.unit_cost, MerchProduct.unit_cost)
    price_expr = func.coalesce(MerchVariant.unit_price, MerchProduct.unit_price)
    val_q = (
        select(
            func.coalesce(func.sum(MerchVariant.quantity * cost_expr), 0),
            func.coalesce(func.sum(MerchVariant.quantity * price_expr), 0),
            func.coalesce(func.sum(MerchVariant.quantity), 0),
            func.count(MerchVariant.id),
        )
        .join(MerchProduct, MerchProduct.id == MerchVariant.product_id)
        .where(
            MerchVariant.organisation_id == org_id,
            MerchVariant.is_active.is_(True),
            MerchProduct.is_active.is_(True),
        )
    )
    cost_value, retail_value, units, variant_count = (await session.execute(val_q)).one()

    owed = await session.scalar(
        select(func.coalesce(func.sum(MerchMovement.amount), 0)).where(
            MerchMovement.organisation_id == org_id,
            MerchMovement.paid.is_(False),
            MerchMovement.amount.isnot(None),
        )
    ) or 0

    product_count = await session.scalar(
        select(func.count(MerchProduct.id)).where(
            MerchProduct.organisation_id == org_id,
            MerchProduct.is_active.is_(True),
        )
    ) or 0

    asset_count = await session.scalar(
        select(func.count(MerchAsset.id)).where(
            MerchAsset.organisation_id == org_id,
            MerchAsset.is_active.is_(True),
        )
    ) or 0

    return {
        "stock_value_cost": float(cost_value or 0),
        "stock_value_retail": float(retail_value or 0),
        "stock_margin": float((retail_value or 0) - (cost_value or 0)),
        "units_on_hand": int(units or 0),
        "variant_count": int(variant_count or 0),
        "product_count": int(product_count or 0),
        "asset_count": int(asset_count or 0),
        "outstanding_owed": float(owed or 0),
    }
