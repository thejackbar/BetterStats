"""BetterMerch ← Square sync.

One-way mirror: Square is the source of truth for canteen/bar stock. We import
its catalog into food_drink products, import completed sales as 'sold' movements
(revenue + stock down, deduped), then reconcile each variant's quantity to
Square's current inventory count so the numbers never drift.

Token handling: code-flow refresh tokens don't expire; the access token is
refreshed when it is within a week of its 30-day expiry.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import (
    Organisation, MerchProduct, MerchVariant, MerchMovement, MerchSquareConnection,
    async_session_maker,
)
from app.services import square_client
from app.services import merch as merch_service

logger = logging.getLogger(__name__)

REFRESH_WINDOW = timedelta(days=7)
FIRST_SALES_LOOKBACK = timedelta(days=30)


def _parse_dt(s: str | None):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


async def get_connection(session: AsyncSession, org_id) -> MerchSquareConnection | None:
    return (await session.execute(
        select(MerchSquareConnection).where(MerchSquareConnection.organisation_id == org_id)
    )).scalar_one_or_none()


async def ensure_fresh_token(session: AsyncSession, conn: MerchSquareConnection) -> str:
    """Return a usable access token, refreshing first if it is missing or close
    to expiry. Commits the refreshed token."""
    if not conn.refresh_token and not conn.access_token:
        raise square_client.SquareError("Square account is not connected")
    now = datetime.now(timezone.utc)
    needs = conn.token_expires_at is None or conn.token_expires_at <= now + REFRESH_WINDOW
    if needs and conn.refresh_token:
        data = await square_client.refresh_token(conn.refresh_token)
        conn.access_token = data.get("access_token", conn.access_token)
        if data.get("refresh_token"):
            conn.refresh_token = data["refresh_token"]
        conn.token_expires_at = _parse_dt(data.get("expires_at"))
        conn.merchant_id = data.get("merchant_id", conn.merchant_id)
        await session.commit()
    return conn.access_token


async def _sync_catalog(session, org_id, token) -> tuple[dict, int, int]:
    """Upsert Square ITEMs/variations into food_drink products. Returns the
    square-variation-id -> MerchVariant map plus created counts."""
    items = await square_client.list_catalog_items(token)
    # Existing maps so re-syncs update in place.
    products = (await session.execute(
        select(MerchProduct).where(
            MerchProduct.organisation_id == org_id, MerchProduct.square_object_id.isnot(None)
        )
    )).scalars().all()
    prod_by_sq = {p.square_object_id: p for p in products}
    variants = (await session.execute(
        select(MerchVariant).where(
            MerchVariant.organisation_id == org_id, MerchVariant.square_object_id.isnot(None)
        )
    )).scalars().all()
    var_by_sq = {v.square_object_id: v for v in variants}

    new_products = new_variants = 0
    for obj in items:
        if obj.get("type") != "ITEM":
            continue
        item_id = obj.get("id")
        idata = obj.get("item_data", {}) or {}
        name = (idata.get("name") or "Square item").strip()
        p = prod_by_sq.get(item_id)
        if p is None:
            p = MerchProduct(
                organisation_id=org_id, category="food_drink", name=name,
                source="square", square_object_id=item_id,
            )
            session.add(p)
            await session.flush()
            prod_by_sq[item_id] = p
            new_products += 1
        else:
            p.name = name
        for v in idata.get("variations", []) or []:
            if v.get("type") != "ITEM_VARIATION":
                continue
            var_id = v.get("id")
            vdata = v.get("item_variation_data", {}) or {}
            label = (vdata.get("name") or "Standard").strip() or "Standard"
            sku = vdata.get("sku")
            price = (vdata.get("price_money") or {}).get("amount")
            unit_price = (Decimal(price) / 100).quantize(Decimal("0.01")) if price is not None else None
            mv = var_by_sq.get(var_id)
            if mv is None:
                mv = MerchVariant(
                    product_id=p.id, organisation_id=org_id, label=label, sku=sku,
                    unit_price=unit_price, square_object_id=var_id,
                )
                session.add(mv)
                var_by_sq[var_id] = mv
                new_variants += 1
            else:
                mv.label = label
                mv.sku = sku
                if unit_price is not None:
                    mv.unit_price = unit_price
    # Flush (not commit) so new variants get ids for later movements, while the
    # ORM objects stay live across the rest of the sync (one commit at the end).
    await session.flush()
    return var_by_sq, new_products, new_variants


async def _sync_sales(session, org_id, conn, token, var_by_sq) -> int:
    if not conn.sync_sales:
        return 0
    start = conn.sales_cursor
    if start is None:
        start = datetime.now(timezone.utc) - FIRST_SALES_LOOKBACK
    start_iso = start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    orders = await square_client.search_completed_orders(token, conn.location_id, start_iso)

    # Existing external refs so a re-run never double-imports a sale.
    existing = set((await session.execute(
        select(MerchMovement.external_ref).where(
            MerchMovement.organisation_id == org_id,
            MerchMovement.source == "square",
            MerchMovement.external_ref.isnot(None),
        )
    )).scalars().all())

    imported = 0
    latest_closed = conn.sales_cursor
    for order in orders:
        closed = _parse_dt(order.get("closed_at"))
        if closed and (latest_closed is None or closed > latest_closed):
            latest_closed = closed
        oid = order.get("id")
        for li in order.get("line_items", []) or []:
            sq_var = li.get("catalog_object_id")
            variant = var_by_sq.get(sq_var)
            if variant is None:
                continue
            uid = li.get("uid") or sq_var
            ref = f"square:{oid}:{uid}"
            if ref in existing:
                continue
            try:
                qty = int(float(li.get("quantity", "0")))
            except (ValueError, TypeError):
                qty = 0
            if qty <= 0:
                continue
            total = (li.get("total_money") or li.get("gross_sales_money") or {}).get("amount")
            amount = (Decimal(total) / 100).quantize(Decimal("0.01")) if total is not None else None
            merch_service.record_movement(
                session, variant,
                kind="sold", delta=-qty, amount=amount, paid=True,
                payment_method="Square", note=li.get("name") or None,
                occurred_on=closed.date() if closed else None,
                source="square", external_ref=ref,
            )
            existing.add(ref)
            imported += 1
    if latest_closed:
        conn.sales_cursor = latest_closed
    await session.flush()
    return imported


async def _reconcile_inventory(session, org_id, conn, token, var_by_sq) -> int:
    ids = list(var_by_sq.keys())
    counts = await square_client.inventory_counts(token, ids, conn.location_id)
    updated = 0
    for sq_id, target in counts.items():
        variant = var_by_sq.get(sq_id)
        if variant is None:
            continue
        delta = int(target) - int(variant.quantity or 0)
        if delta != 0:
            merch_service.record_movement(
                session, variant, kind="stocktake", delta=delta,
                note="Square inventory sync", source="square",
            )
            updated += 1
    await session.flush()
    return updated


async def sync_square(session: AsyncSession, org_id) -> dict:
    """Run a full Square → BetterMerch sync for one club. Catalog, then sales,
    then reconcile inventory to Square's current counts."""
    conn = await get_connection(session, org_id)
    if conn is None or not conn.access_token:
        raise square_client.SquareError("Square account is not connected")
    if not conn.location_id:
        raise square_client.SquareError("Pick a Square location to sync first")
    try:
        token = await ensure_fresh_token(session, conn)
        # ensure_fresh_token may have committed the refreshed token, which expires
        # conn — reload it live before the single end-of-sync commit.
        await session.refresh(conn)
        var_by_sq, new_p, new_v = await _sync_catalog(session, org_id, token)
        sales = await _sync_sales(session, org_id, conn, token, var_by_sq)
        inv = await _reconcile_inventory(session, org_id, conn, token, var_by_sq)
        conn.last_sync_at = datetime.now(timezone.utc)
        conn.last_sync_status = "ok"
        conn.last_sync_error = None
        await session.commit()
        return {
            "products_added": new_p, "variants_added": new_v,
            "sales_imported": sales, "inventory_updated": inv,
            "variants_tracked": len(var_by_sq),
        }
    except Exception as e:
        await session.rollback()
        conn = await get_connection(session, org_id)
        if conn is not None:
            conn.last_sync_at = datetime.now(timezone.utc)
            conn.last_sync_status = "error"
            conn.last_sync_error = str(e)[:500]
            await session.commit()
        raise


async def sync_all_square():
    """Scheduled poll — sync every club with an enabled Square connection."""
    async with async_session_maker() as session:
        conns = (await session.execute(
            select(MerchSquareConnection).where(
                MerchSquareConnection.sync_enabled.is_(True),
                MerchSquareConnection.access_token.isnot(None),
                MerchSquareConnection.location_id.isnot(None),
            )
        )).scalars().all()
        org_ids = [c.organisation_id for c in conns]
    for org_id in org_ids:
        try:
            async with async_session_maker() as session:
                await sync_square(session, org_id)
        except Exception as e:
            logger.error(f"Square sync failed for org {org_id}: {e}")
