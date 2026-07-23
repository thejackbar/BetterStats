"""Merch storefront — public online ordering against the existing BetterMerch
catalogue (merch_products/merch_variants). See the migration 179 docstring
for why Square-synced products are excluded and why orders are their own
tables rather than a repurposing of merch_movements.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import MerchCategory, MerchProduct, MerchVariant, MerchOrder, MerchOrderItem
from app.services import merch as merch_service


def _eff_price_cents(variant: MerchVariant, product: MerchProduct) -> int:
    price = variant.unit_price if variant.unit_price is not None else product.unit_price
    return round(float(price or 0) * 100)


def _order_dict(order: MerchOrder) -> dict:
    return {
        "id": str(order.id), "customer_name": order.customer_name, "email": order.email, "phone": order.phone,
        "status": order.status, "total_cents": order.total_cents,
        "notes": order.notes, "created_at": order.created_at.isoformat() if order.created_at else None,
        "items": [_order_item_dict(i) for i in order.items],
    }


def _order_item_dict(item: MerchOrderItem) -> dict:
    return {
        "id": str(item.id), "variant_id": str(item.variant_id) if item.variant_id else None,
        "product_name": item.product_name, "variant_label": item.variant_label,
        "unit_price_cents": item.unit_price_cents, "quantity": item.quantity,
    }


async def storefront_catalogue(session: AsyncSession, org_id) -> list[dict]:
    """Every storefront-eligible product with its variants — for_resale,
    active, show_in_storefront, and NOT Square-synced. One flat list; the
    frontend groups by category client-side (the same category tree the
    admin Stock page already knows how to render)."""
    products = (await session.execute(
        select(MerchProduct).where(
            MerchProduct.organisation_id == org_id, MerchProduct.for_resale.is_(True),
            MerchProduct.is_active.is_(True), MerchProduct.show_in_storefront.is_(True),
            MerchProduct.source == "manual",
        ).order_by(MerchProduct.category, MerchProduct.name)
    )).scalars().all()
    if not products:
        return []

    category_ids = {p.category_id for p in products if p.category_id}
    category_names = {}
    if category_ids:
        rows = (await session.execute(select(MerchCategory).where(MerchCategory.id.in_(category_ids)))).scalars().all()
        category_names = {c.id: c.name for c in rows}

    product_ids = [p.id for p in products]
    variants = (await session.execute(
        select(MerchVariant).where(MerchVariant.product_id.in_(product_ids), MerchVariant.is_active.is_(True))
        .order_by(MerchVariant.label)
    )).scalars().all()
    by_product: dict = {}
    for v in variants:
        by_product.setdefault(v.product_id, []).append(v)

    out = []
    for p in products:
        vs = by_product.get(p.id, [])
        if not vs:
            continue
        out.append({
            "id": str(p.id), "name": p.name, "description": p.description,
            "category": p.category, "category_name": category_names.get(p.category_id),
            "variants": [{
                "id": str(v.id), "label": v.label, "size": v.size, "colour": v.colour,
                "price_cents": _eff_price_cents(v, p), "in_stock": max(0, v.quantity or 0),
            } for v in vs],
        })
    return out


async def create_order(session: AsyncSession, org_id, *, customer_name: str, email: Optional[str],
                       phone: Optional[str], member_id, items: list[dict]) -> MerchOrder:
    """Validates stock against the CURRENT balance (not reserved — a race
    between two simultaneous buyers can still oversell; acceptable at club
    scale, not a locking system), snapshots product/variant name and price,
    and creates the order at status='pending_payment'. Caller commits."""
    customer_name = (customer_name or "").strip()
    if not customer_name:
        raise ValueError("Name is required")
    if not items:
        raise ValueError("Your cart is empty")

    order = MerchOrder(
        organisation_id=org_id, customer_name=customer_name[:200],
        email=(email or None), phone=(phone or None), member_id=member_id,
        status="pending_payment", total_cents=0,
    )
    session.add(order)
    total_cents = 0
    for entry in items:
        variant_id = entry.get("variant_id")
        quantity = max(1, int(entry.get("quantity") or 1))
        variant = await session.get(MerchVariant, variant_id)
        if variant is None or variant.organisation_id != org_id:
            raise ValueError("One of the items in your cart is no longer available")
        product = await session.get(MerchProduct, variant.product_id)
        if product is None or not product.is_active or not product.show_in_storefront or product.source != "manual":
            raise ValueError(f"{variant.label} is no longer available")
        if (variant.quantity or 0) < quantity:
            raise ValueError(f"Only {max(0, variant.quantity or 0)} of {product.name} ({variant.label}) left")
        unit_price_cents = _eff_price_cents(variant, product)
        total_cents += unit_price_cents * quantity
        session.add(MerchOrderItem(
            order=order, variant_id=variant.id, product_name=product.name,
            variant_label=None if variant.label == "Standard" else variant.label,
            unit_price_cents=unit_price_cents, quantity=quantity,
        ))
    if total_cents <= 0:
        raise ValueError("Your cart total must be greater than zero")
    order.total_cents = total_cents
    await session.flush()
    return order


async def mark_order_paid(session: AsyncSession, order: MerchOrder, *, payment_intent_id: Optional[str]) -> None:
    """Idempotent — a replayed webhook for an already-paid order is a no-op.
    Records each line item as an ordinary 'sold' stock movement so it flows
    through the SAME accounting the admin Stock page and Square sync use."""
    if order.status != "pending_payment":
        return
    order.status = "paid"
    order.stripe_payment_intent_id = payment_intent_id
    for item in order.items:
        if item.variant_id is None:
            continue
        variant = await session.get(MerchVariant, item.variant_id)
        if variant is None:
            continue
        merch_service.record_movement(
            session, variant, kind="sold", delta=-item.quantity,
            unit_price=Decimal(item.unit_price_cents) / Decimal(100),
            amount=Decimal(item.unit_price_cents * item.quantity) / Decimal(100),
            paid=True, source="online_store", external_ref=f"online-order:{order.id}:{item.id}",
            note=f"Online store order {order.id}",
        )
    await session.flush()


async def list_orders(session: AsyncSession, org_id, *, status: Optional[str] = None) -> list[MerchOrder]:
    from sqlalchemy.orm import selectinload
    stmt = (
        select(MerchOrder).where(MerchOrder.organisation_id == org_id)
        .options(selectinload(MerchOrder.items))
        .order_by(MerchOrder.created_at.desc())
    )
    if status:
        stmt = stmt.where(MerchOrder.status == status)
    return (await session.execute(stmt)).scalars().all()


async def update_order_status(session: AsyncSession, order: MerchOrder, status: str) -> MerchOrder:
    order.status = status
    return order
