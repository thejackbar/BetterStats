"""BetterMerch API — the club stock register (BetterAdmin module).

One engine, three category templates: apparel (sized/coloured variants),
equipment (quantity OR individual assets), food/drink (canteen stock with
expiry). Stock lives on a variant as a running balance; every change writes a
movement. A sale or issue can be linked to a player with a paid/unpaid flag, so
merch owings are tracked here, separate from BetterFees.

Everything is scoped to the caller's club (get_current_club) and gated by the
MANAGE_MERCH capability. The whole router is module-gated by require_module
("merch") at include time (main.py).
"""
from __future__ import annotations

import csv
import io
import uuid
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from jose import jwt

from app.config.settings import settings
from app.models.db import (
    User, Organisation, Player,
    MerchProduct, MerchVariant, MerchMovement, MerchAsset, MerchSquareConnection, MerchCategory,
    MerchOrder, MERCH_ORDER_STATUSES,
    MERCH_CATEGORIES, MERCH_MOVEMENT_KINDS, MERCH_ASSET_CONDITIONS, MERCH_ASSET_STATUSES,
    MERCH_MAX_CATEGORY_DEPTH,
    get_db,
)
from app.routers.auth import get_current_user, get_current_club
from app.auth.capabilities import require_cap, MANAGE_MERCH
from app.services import merch as merch_service
from app.services import merch_store as merch_store_service
from app.services import square_client, square_sync

# Signed state for the Square OAuth handshake — ties the callback back to the
# club + user that started it, and self-expires.
SQUARE_STATE_TYP = "square_oauth"


def sign_square_state(org_id, user_id) -> str:
    payload = {
        "org": str(org_id),
        "uid": str(user_id),
        "typ": SQUARE_STATE_TYP,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=20),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)

router = APIRouter(prefix="/club-admin/merch", tags=["club-admin-merch"])

_require = Depends(require_cap(MANAGE_MERCH))


# ── helpers ──────────────────────────────────────────────────────────────────

def _f(x) -> Optional[float]:
    return float(x) if x is not None else None


def _money(raw) -> Optional[Decimal]:
    if raw is None or raw == "":
        return None
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Invalid amount")


def _parse_date(raw) -> Optional[date]:
    if not raw:
        return None
    if isinstance(raw, date):
        return raw
    try:
        return date.fromisoformat(str(raw)[:10])
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail=f"Invalid date: {raw}")


async def _product_or_404(db: AsyncSession, club: Organisation, pid: str) -> MerchProduct:
    try:
        p = await db.get(MerchProduct, uuid.UUID(str(pid)))
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="Invalid product id")
    if not p or p.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Product not found")
    return p


async def _variant_or_404(db: AsyncSession, club: Organisation, vid: str) -> MerchVariant:
    try:
        v = await db.get(MerchVariant, uuid.UUID(str(vid)))
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="Invalid variant id")
    if not v or v.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Variant not found")
    return v


async def _asset_or_404(db: AsyncSession, club: Organisation, aid: str) -> MerchAsset:
    try:
        a = await db.get(MerchAsset, uuid.UUID(str(aid)))
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="Invalid asset id")
    if not a or a.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Asset not found")
    return a


def _eff_cost(v: MerchVariant, p: MerchProduct | None):
    return v.unit_cost if v.unit_cost is not None else (p.unit_cost if p else None)


def _eff_price(v: MerchVariant, p: MerchProduct | None):
    return v.unit_price if v.unit_price is not None else (p.unit_price if p else None)


def _variant_out(v: MerchVariant, p: MerchProduct | None = None) -> dict:
    return {
        "id": str(v.id),
        "product_id": str(v.product_id),
        "label": v.label,
        "size": v.size,
        "colour": v.colour,
        "sku": v.sku,
        "unit_cost": _f(v.unit_cost),
        "unit_price": _f(v.unit_price),
        "eff_cost": _f(_eff_cost(v, p)),
        "eff_price": _f(_eff_price(v, p)),
        "quantity": v.quantity,
        "low_stock_threshold": v.low_stock_threshold,
        "threshold": merch_service.variant_threshold(v, p) if p else v.low_stock_threshold,
        "low_stock": merch_service.is_low_stock(v, p) if p else False,
        "expiry_date": v.expiry_date.isoformat() if v.expiry_date else None,
        "is_active": v.is_active,
    }


def _product_out(p: MerchProduct, variants: list[MerchVariant] | None = None) -> dict:
    out = {
        "id": str(p.id),
        "category": p.category,
        "category_id": str(p.category_id) if p.category_id else None,
        "name": p.name,
        "description": p.description,
        "for_resale": p.for_resale,
        "unit_cost": _f(p.unit_cost),
        "unit_price": _f(p.unit_price),
        "low_stock_threshold": p.low_stock_threshold,
        "supplier": p.supplier,
        "notes": p.notes,
        "is_active": p.is_active,
        "show_in_storefront": p.show_in_storefront,
        "source": p.source,
    }
    if variants is not None:
        active = [v for v in variants if v.is_active]
        out["variants"] = [_variant_out(v, p) for v in active]
        out["on_hand"] = sum((v.quantity or 0) for v in active)
        out["variant_count"] = len(active)
        out["low_stock"] = any(merch_service.is_low_stock(v, p) for v in active)
    return out


def _asset_out(a: MerchAsset) -> dict:
    return {
        "id": str(a.id),
        "name": a.name,
        "asset_tag": a.asset_tag,
        "purchase_cost": _f(a.purchase_cost),
        "purchase_date": a.purchase_date.isoformat() if a.purchase_date else None,
        "condition": a.condition,
        "service_due_date": a.service_due_date.isoformat() if a.service_due_date else None,
        "replace_due_date": a.replace_due_date.isoformat() if a.replace_due_date else None,
        "status": a.status,
        "notes": a.notes,
        "is_active": a.is_active,
    }


def _player_name(p: Player | None) -> Optional[str]:
    if p is None:
        return None
    return getattr(p, "display_name_override", None) or p.name


# ───────────────────────────────────────────────────────────────────────────
# Overview + alerts
# ───────────────────────────────────────────────────────────────────────────

@router.get("/overview", dependencies=[_require])
async def get_overview(
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    summary = await merch_service.stock_summary(db, club.id)
    alerts = await merch_service.merch_alerts(db, club.id)
    summary["alerts"] = alerts
    return summary


@router.get("/alerts", dependencies=[_require])
async def get_alerts(
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    return await merch_service.merch_alerts(db, club.id)


# ───────────────────────────────────────────────────────────────────────────
# Category tree (club-defined, nested under the fixed top type)
# ───────────────────────────────────────────────────────────────────────────

async def _categories_for_org(db: AsyncSession, org_id) -> list:
    rows = await db.execute(
        select(MerchCategory).where(MerchCategory.organisation_id == org_id)
        .order_by(MerchCategory.sort_order, MerchCategory.name)
    )
    return list(rows.scalars().all())


def _category_index(cats: list):
    by_id = {c.id: c for c in cats}
    children: dict = {}
    for c in cats:
        children.setdefault(c.parent_id, []).append(c)
    return by_id, children


def _category_path(cat, by_id) -> list[str]:
    names, node, guard = [], cat, 0
    while node is not None and guard < 8:
        names.append(node.name)
        node = by_id.get(node.parent_id) if node.parent_id else None
        guard += 1
    return list(reversed(names))


def _descendant_ids(node_id, children) -> list:
    out, stack = [], [node_id]
    while stack:
        nid = stack.pop()
        out.append(nid)
        for ch in children.get(nid, []):
            stack.append(ch.id)
    return out


def _cat_out(c, by_id) -> dict:
    path = _category_path(c, by_id)
    return {
        "id": str(c.id),
        "parent_id": str(c.parent_id) if c.parent_id else None,
        "top_category": c.top_category,
        "name": c.name,
        "sort_order": c.sort_order,
        "depth": len(path),
        "path": path,
    }


# Generic starter categories that fit most clubs (one level, kept simple).
MERCH_DEFAULT_CATEGORIES = {
    "apparel": ["Match attire", "Training attire", "Caps", "Club clothing"],
    "equipment": ["Balls", "Bats", "Protective gear", "Training equipment", "Ground equipment"],
    "food_drink": ["Canteen", "Bar"],
}


class CategoryIn(BaseModel):
    top_category: str
    parent_id: Optional[str] = None
    name: str


class CategoryPatch(BaseModel):
    name: Optional[str] = None
    sort_order: Optional[int] = None


@router.get("/categories", dependencies=[_require])
async def list_categories(
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    cats = await _categories_for_org(db, club.id)
    by_id, _ = _category_index(cats)
    return {"categories": [_cat_out(c, by_id) for c in cats]}


@router.post("/categories", dependencies=[_require])
async def create_category(
    body: CategoryIn,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    if body.top_category not in MERCH_CATEGORIES:
        raise HTTPException(status_code=422, detail=f"Unknown type: {body.top_category}")
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name is required")
    cats = await _categories_for_org(db, club.id)
    by_id, children = _category_index(cats)
    parent = None
    if body.parent_id:
        parent = await _category_or_404(db, club, body.parent_id)
        if parent.top_category != body.top_category:
            raise HTTPException(status_code=422, detail="Parent is under a different type")
        if len(_category_path(parent, by_id)) >= MERCH_MAX_CATEGORY_DEPTH:
            raise HTTPException(status_code=422, detail="Categories nest at most three levels")
    pid = parent.id if parent else None
    # Reuse an existing sibling with the same name (created-as-you-go dedupe).
    for c in children.get(pid, []):
        if c.top_category == body.top_category and c.name.strip().lower() == name.lower():
            return _cat_out(c, by_id)
    node = MerchCategory(organisation_id=club.id, parent_id=pid, top_category=body.top_category, name=name)
    db.add(node)
    await db.commit()
    await db.refresh(node)
    by_id[node.id] = node
    return _cat_out(node, by_id)


@router.post("/categories/seed-defaults", dependencies=[_require])
async def seed_default_categories(
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Add a generic starter set of top-level categories. Idempotent — skips any
    that already exist for the club."""
    existing = await _categories_for_org(db, club.id)
    have = {(c.top_category, c.name.strip().lower()) for c in existing if c.parent_id is None}
    created = 0
    for top, names in MERCH_DEFAULT_CATEGORIES.items():
        for i, name in enumerate(names):
            if (top, name.lower()) in have:
                continue
            db.add(MerchCategory(organisation_id=club.id, top_category=top, name=name, sort_order=i))
            created += 1
    await db.commit()
    cats = await _categories_for_org(db, club.id)
    by_id, _ = _category_index(cats)
    return {"created": created, "categories": [_cat_out(c, by_id) for c in cats]}


async def _category_or_404(db: AsyncSession, club: Organisation, cid: str) -> MerchCategory:
    try:
        c = await db.get(MerchCategory, uuid.UUID(str(cid)))
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="Invalid category id")
    if not c or c.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Category not found")
    return c


async def _resolve_category(db: AsyncSession, club: Organisation, category_id, top_category):
    """Validate a category id belongs to the club and sits under the product's
    type. Returns the UUID, or None for uncategorised."""
    if not category_id:
        return None
    c = await _category_or_404(db, club, category_id)
    if c.top_category != top_category:
        raise HTTPException(status_code=422, detail="Category is under a different type")
    return c.id


@router.patch("/categories/{category_id}", dependencies=[_require])
async def update_category(
    category_id: str,
    body: CategoryPatch,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    c = await _category_or_404(db, club, category_id)
    if body.name is not None and body.name.strip():
        c.name = body.name.strip()
    if body.sort_order is not None:
        c.sort_order = body.sort_order
    await db.commit()
    cats = await _categories_for_org(db, club.id)
    by_id, _ = _category_index(cats)
    return _cat_out(c, by_id)


@router.delete("/categories/{category_id}", dependencies=[_require])
async def delete_category(
    category_id: str,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Delete a node: its children move up to its parent, and any products filed
    under it fall back to uncategorised (FK SET NULL)."""
    c = await _category_or_404(db, club, category_id)
    await db.execute(
        MerchCategory.__table__.update()
        .where(MerchCategory.parent_id == c.id)
        .values(parent_id=c.parent_id)
    )
    await db.delete(c)
    await db.commit()
    return {"ok": True}


# ───────────────────────────────────────────────────────────────────────────
# Products + variants
# ───────────────────────────────────────────────────────────────────────────

class VariantIn(BaseModel):
    label: Optional[str] = None
    size: Optional[str] = None
    colour: Optional[str] = None
    sku: Optional[str] = None
    unit_cost: Optional[float] = None
    unit_price: Optional[float] = None
    quantity: Optional[int] = None
    low_stock_threshold: Optional[int] = None
    expiry_date: Optional[str] = None


class ProductIn(BaseModel):
    category: str = "apparel"
    category_id: Optional[str] = None
    name: str
    description: Optional[str] = None
    for_resale: bool = True
    unit_cost: Optional[float] = None
    unit_price: Optional[float] = None
    low_stock_threshold: Optional[int] = None
    supplier: Optional[str] = None
    notes: Optional[str] = None
    show_in_storefront: bool = True
    variants: Optional[List[VariantIn]] = None  # optional initial variants


class ProductPatch(BaseModel):
    category: Optional[str] = None
    category_id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    for_resale: Optional[bool] = None
    unit_cost: Optional[float] = None
    unit_price: Optional[float] = None
    low_stock_threshold: Optional[int] = None
    supplier: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None
    show_in_storefront: Optional[bool] = None


class VariantPatch(BaseModel):
    label: Optional[str] = None
    size: Optional[str] = None
    colour: Optional[str] = None
    sku: Optional[str] = None
    unit_cost: Optional[float] = None
    unit_price: Optional[float] = None
    low_stock_threshold: Optional[int] = None
    expiry_date: Optional[str] = None
    is_active: Optional[bool] = None


def _variant_label(vi: VariantIn) -> str:
    if vi.label:
        return vi.label
    parts = [p for p in (vi.size, vi.colour) if p]
    return " / ".join(parts) if parts else "Standard"


@router.get("/products", dependencies=[_require])
async def list_products(
    category: Optional[str] = None,
    category_id: Optional[str] = None,
    q: Optional[str] = None,
    include_inactive: bool = False,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    pq = select(MerchProduct).where(MerchProduct.organisation_id == club.id)
    if not include_inactive:
        pq = pq.where(MerchProduct.is_active.is_(True))
    if category:
        pq = pq.where(MerchProduct.category == category)
    if category_id:
        cats = await _categories_for_org(db, club.id)
        _, children = _category_index(cats)
        try:
            target = uuid.UUID(category_id)
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail="Invalid category id")
        pq = pq.where(MerchProduct.category_id.in_(_descendant_ids(target, children)))
    if q:
        pq = pq.where(MerchProduct.name.ilike(f"%{q}%"))
    pq = pq.order_by(MerchProduct.category, MerchProduct.name)
    products = (await db.execute(pq)).scalars().all()
    if not products:
        return {"products": []}

    pids = [p.id for p in products]
    vq = select(MerchVariant).where(MerchVariant.product_id.in_(pids))
    if not include_inactive:
        vq = vq.where(MerchVariant.is_active.is_(True))
    vq = vq.order_by(MerchVariant.label)
    variants = (await db.execute(vq)).scalars().all()
    by_product: dict = {}
    for v in variants:
        by_product.setdefault(v.product_id, []).append(v)
    return {"products": [_product_out(p, by_product.get(p.id, [])) for p in products]}


@router.post("/products", dependencies=[_require])
async def create_product(
    body: ProductIn,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    if body.category not in MERCH_CATEGORIES:
        raise HTTPException(status_code=422, detail=f"Unknown category: {body.category}")
    if not (body.name or "").strip():
        raise HTTPException(status_code=422, detail="Name is required")
    cat_id = await _resolve_category(db, club, body.category_id, body.category)
    p = MerchProduct(
        organisation_id=club.id,
        category=body.category,
        category_id=cat_id,
        name=body.name.strip(),
        description=body.description,
        for_resale=body.for_resale,
        unit_cost=_money(body.unit_cost),
        unit_price=_money(body.unit_price),
        low_stock_threshold=body.low_stock_threshold,
        supplier=body.supplier,
        notes=body.notes,
        show_in_storefront=body.show_in_storefront,
    )
    db.add(p)
    await db.flush()

    initial = body.variants if body.variants else [VariantIn(label="Standard")]
    for vi in initial:
        v = MerchVariant(
            product_id=p.id,
            organisation_id=club.id,
            label=_variant_label(vi),
            size=vi.size,
            colour=vi.colour,
            sku=vi.sku,
            unit_cost=_money(vi.unit_cost),
            unit_price=_money(vi.unit_price),
            quantity=int(vi.quantity or 0),
            low_stock_threshold=vi.low_stock_threshold,
            expiry_date=_parse_date(vi.expiry_date),
        )
        db.add(v)
    await db.commit()
    await db.refresh(p)
    vs = (await db.execute(
        select(MerchVariant).where(MerchVariant.product_id == p.id, MerchVariant.is_active.is_(True))
    )).scalars().all()
    return _product_out(p, vs)


@router.get("/products/{product_id}", dependencies=[_require])
async def get_product(
    product_id: str,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    p = await _product_or_404(db, club, product_id)
    vs = (await db.execute(
        select(MerchVariant).where(MerchVariant.product_id == p.id).order_by(MerchVariant.label)
    )).scalars().all()
    out = _product_out(p, vs)
    out["variants"] = [_variant_out(v, p) for v in vs]  # include inactive on detail
    return out


@router.patch("/products/{product_id}", dependencies=[_require])
async def update_product(
    product_id: str,
    body: ProductPatch,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    p = await _product_or_404(db, club, product_id)
    data = body.model_dump(exclude_unset=True)
    if "category" in data and data["category"] not in MERCH_CATEGORIES:
        raise HTTPException(status_code=422, detail=f"Unknown category: {data['category']}")
    for field in ("category", "name", "description", "for_resale", "low_stock_threshold", "supplier", "notes",
                  "is_active", "show_in_storefront"):
        if field in data:
            setattr(p, field, data[field])
    if "category_id" in data:
        p.category_id = await _resolve_category(db, club, data["category_id"], p.category) if data["category_id"] else None
    if "unit_cost" in data:
        p.unit_cost = _money(data["unit_cost"])
    if "unit_price" in data:
        p.unit_price = _money(data["unit_price"])
    p.updated_at = func.now()
    await db.commit()
    await db.refresh(p)
    return _product_out(p)


@router.delete("/products/{product_id}", dependencies=[_require])
async def delete_product(
    product_id: str,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete: hides the product and its variants but keeps the movement
    history intact."""
    p = await _product_or_404(db, club, product_id)
    p.is_active = False
    await db.execute(
        MerchVariant.__table__.update()
        .where(MerchVariant.product_id == p.id)
        .values(is_active=False)
    )
    await db.commit()
    return {"ok": True}


@router.post("/products/{product_id}/variants", dependencies=[_require])
async def add_variant(
    product_id: str,
    body: VariantIn,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    p = await _product_or_404(db, club, product_id)
    v = MerchVariant(
        product_id=p.id,
        organisation_id=club.id,
        label=_variant_label(body),
        size=body.size,
        colour=body.colour,
        sku=body.sku,
        unit_cost=_money(body.unit_cost),
        unit_price=_money(body.unit_price),
        quantity=int(body.quantity or 0),
        low_stock_threshold=body.low_stock_threshold,
        expiry_date=_parse_date(body.expiry_date),
    )
    db.add(v)
    await db.commit()
    await db.refresh(v)
    return _variant_out(v, p)


@router.patch("/variants/{variant_id}", dependencies=[_require])
async def update_variant(
    variant_id: str,
    body: VariantPatch,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    v = await _variant_or_404(db, club, variant_id)
    data = body.model_dump(exclude_unset=True)
    for field in ("label", "size", "colour", "sku", "low_stock_threshold", "is_active"):
        if field in data:
            setattr(v, field, data[field])
    if "unit_cost" in data:
        v.unit_cost = _money(data["unit_cost"])
    if "unit_price" in data:
        v.unit_price = _money(data["unit_price"])
    if "expiry_date" in data:
        v.expiry_date = _parse_date(data["expiry_date"])
    v.updated_at = func.now()
    await db.commit()
    await db.refresh(v)
    p = await db.get(MerchProduct, v.product_id)
    return _variant_out(v, p)


@router.delete("/variants/{variant_id}", dependencies=[_require])
async def delete_variant(
    variant_id: str,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    v = await _variant_or_404(db, club, variant_id)
    v.is_active = False
    await db.commit()
    return {"ok": True}


# ───────────────────────────────────────────────────────────────────────────
# Stock movements (in / out)
# ───────────────────────────────────────────────────────────────────────────

class MovementIn(BaseModel):
    variant_id: str
    kind: str                         # received | sold | issued | used | adjustment | stocktake | write_off
    quantity: Optional[int] = None    # magnitude for received/sold/issued/used/write_off
    delta: Optional[int] = None       # signed, for 'adjustment'
    new_quantity: Optional[int] = None  # absolute target, for 'stocktake'
    unit_cost: Optional[float] = None
    unit_price: Optional[float] = None
    player_id: Optional[str] = None
    amount: Optional[float] = None
    paid: Optional[bool] = None
    paid_at: Optional[str] = None
    payment_method: Optional[str] = None
    note: Optional[str] = None
    occurred_on: Optional[str] = None
    allow_negative: bool = False


class MovementPatch(BaseModel):
    paid: Optional[bool] = None
    paid_at: Optional[str] = None
    payment_method: Optional[str] = None
    amount: Optional[float] = None
    note: Optional[str] = None


async def _movement_rows(db, club, *, variant_id=None, product_id=None, player_id=None,
                         kind=None, unpaid_only=False, limit=200):
    q = (
        select(MerchMovement, MerchProduct, MerchVariant, Player)
        .join(MerchVariant, MerchVariant.id == MerchMovement.variant_id)
        .join(MerchProduct, MerchProduct.id == MerchVariant.product_id)
        .outerjoin(Player, Player.id == MerchMovement.player_id)
        .where(MerchMovement.organisation_id == club.id)
    )
    if variant_id:
        q = q.where(MerchMovement.variant_id == uuid.UUID(str(variant_id)))
    if product_id:
        q = q.where(MerchVariant.product_id == uuid.UUID(str(product_id)))
    if player_id:
        q = q.where(MerchMovement.player_id == uuid.UUID(str(player_id)))
    if kind:
        q = q.where(MerchMovement.kind == kind)
    if unpaid_only:
        q = q.where(MerchMovement.paid.is_(False))
    q = q.order_by(MerchMovement.created_at.desc()).limit(limit)
    rows = (await db.execute(q)).all()
    return rows


def _movement_out(mv: MerchMovement, p: MerchProduct, v: MerchVariant, pl: Player | None) -> dict:
    return {
        "id": str(mv.id),
        "variant_id": str(mv.variant_id),
        "product_id": str(p.id),
        "category": p.category,
        "product_name": p.name,
        "variant_label": v.label,
        "kind": mv.kind,
        "delta": mv.delta,
        "quantity_after": mv.quantity_after,
        "unit_cost": _f(mv.unit_cost),
        "unit_price": _f(mv.unit_price),
        "player_id": str(mv.player_id) if mv.player_id else None,
        "player_name": _player_name(pl),
        "amount": _f(mv.amount),
        "paid": mv.paid,
        "paid_at": mv.paid_at.isoformat() if mv.paid_at else None,
        "payment_method": mv.payment_method,
        "note": mv.note,
        "occurred_on": mv.occurred_on.isoformat() if mv.occurred_on else None,
        "created_at": mv.created_at.isoformat() if mv.created_at else None,
    }


@router.get("/movements", dependencies=[_require])
async def list_movements(
    variant_id: Optional[str] = None,
    product_id: Optional[str] = None,
    player_id: Optional[str] = None,
    kind: Optional[str] = None,
    unpaid_only: bool = False,
    limit: int = 200,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    try:
        rows = await _movement_rows(
            db, club, variant_id=variant_id, product_id=product_id,
            player_id=player_id, kind=kind, unpaid_only=unpaid_only,
            limit=min(max(limit, 1), 500),
        )
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="Invalid filter id")
    return {"movements": [_movement_out(mv, p, v, pl) for mv, p, v, pl in rows]}


@router.post("/movements")
async def create_movement(
    body: MovementIn,
    current_user: User = Depends(require_cap(MANAGE_MERCH)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    if body.kind not in MERCH_MOVEMENT_KINDS:
        raise HTTPException(status_code=422, detail=f"Unknown movement kind: {body.kind}")
    v = await _variant_or_404(db, club, body.variant_id)
    p = await db.get(MerchProduct, v.product_id)

    # Work out the signed delta from the kind.
    if body.kind == "stocktake":
        if body.new_quantity is None:
            raise HTTPException(status_code=422, detail="stocktake needs new_quantity")
        delta = int(body.new_quantity) - int(v.quantity or 0)
    elif body.kind == "adjustment":
        if body.delta is None:
            raise HTTPException(status_code=422, detail="adjustment needs a signed delta")
        delta = int(body.delta)
    elif body.kind == "received":
        qty = int(body.quantity or 0)
        if qty <= 0:
            raise HTTPException(status_code=422, detail="quantity must be positive")
        delta = qty
    else:  # sold | issued | used | write_off — stock out
        qty = int(body.quantity or 0)
        if qty <= 0:
            raise HTTPException(status_code=422, detail="quantity must be positive")
        delta = -qty

    if delta < 0 and not body.allow_negative and (v.quantity or 0) + delta < 0:
        raise HTTPException(
            status_code=422,
            detail=f"Only {v.quantity or 0} on hand — can't remove {abs(delta)}.",
        )

    # Player link + money: only meaningful on a sale or issue.
    player_id = None
    if body.player_id and body.kind in merch_service.MONEY_KINDS + ("used",):
        try:
            pl = await db.get(Player, uuid.UUID(str(body.player_id)))
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail="Invalid player id")
        if not pl or pl.organisation_id != club.id:
            raise HTTPException(status_code=404, detail="Player not found")
        player_id = pl.id

    unit_price = _money(body.unit_price)
    if unit_price is None:
        unit_price = _eff_price(v, p)
    unit_cost = _money(body.unit_cost)
    if unit_cost is None and body.kind == "received":
        unit_cost = _eff_cost(v, p)

    amount = _money(body.amount)
    if amount is None and body.kind in merch_service.MONEY_KINDS and unit_price is not None:
        amount = (Decimal(unit_price) * abs(delta)).quantize(Decimal("0.01"))

    # paid defaults: a money movement is unpaid unless told otherwise; everything
    # else is "paid" (no money involved) so it never shows as an owing.
    if body.paid is not None:
        paid = body.paid
    else:
        paid = not (body.kind in merch_service.MONEY_KINDS and amount and amount > 0)

    mv = merch_service.record_movement(
        db, v,
        kind=body.kind,
        delta=delta,
        unit_cost=unit_cost,
        unit_price=unit_price,
        player_id=player_id,
        amount=amount,
        paid=paid,
        paid_at=_parse_date(body.paid_at) or (date.today() if paid and amount else None),
        payment_method=body.payment_method,
        note=body.note,
        occurred_on=_parse_date(body.occurred_on) or date.today(),
        created_by_user_id=current_user.id,
    )
    await db.commit()
    await db.refresh(mv)
    pl = await db.get(Player, mv.player_id) if mv.player_id else None
    return _movement_out(mv, p, v, pl)


async def _movement_or_404(db, club, mid) -> MerchMovement:
    try:
        mv = await db.get(MerchMovement, uuid.UUID(str(mid)))
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="Invalid movement id")
    if not mv or mv.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Movement not found")
    return mv


@router.patch("/movements/{movement_id}", dependencies=[_require])
async def update_movement(
    movement_id: str,
    body: MovementPatch,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Edit the money side of a movement (mark paid/unpaid, amount, method,
    note). The stock delta is never changed here — delete + re-record to fix a
    quantity, so the running balance stays honest."""
    mv = await _movement_or_404(db, club, movement_id)
    data = body.model_dump(exclude_unset=True)
    if "paid" in data:
        mv.paid = data["paid"]
        if data["paid"] and mv.paid_at is None:
            mv.paid_at = date.today()
    if "paid_at" in data:
        mv.paid_at = _parse_date(data["paid_at"])
    if "payment_method" in data:
        mv.payment_method = data["payment_method"]
    if "amount" in data:
        mv.amount = _money(data["amount"])
    if "note" in data:
        mv.note = data["note"]
    await db.commit()
    await db.refresh(mv)
    v = await db.get(MerchVariant, mv.variant_id)
    p = await db.get(MerchProduct, v.product_id)
    pl = await db.get(Player, mv.player_id) if mv.player_id else None
    return _movement_out(mv, p, v, pl)


@router.delete("/movements/{movement_id}", dependencies=[_require])
async def delete_movement(
    movement_id: str,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Undo a movement: reverse its stock effect on the variant, then delete the
    row."""
    mv = await _movement_or_404(db, club, movement_id)
    v = await db.get(MerchVariant, mv.variant_id)
    if v is not None:
        v.quantity = (v.quantity or 0) - (mv.delta or 0)
    await db.delete(mv)
    await db.commit()
    return {"ok": True}


# ───────────────────────────────────────────────────────────────────────────
# Individual equipment assets
# ───────────────────────────────────────────────────────────────────────────

class AssetIn(BaseModel):
    name: str
    asset_tag: Optional[str] = None
    purchase_cost: Optional[float] = None
    purchase_date: Optional[str] = None
    condition: Optional[str] = "good"
    service_due_date: Optional[str] = None
    replace_due_date: Optional[str] = None
    status: Optional[str] = "in_service"
    notes: Optional[str] = None


class AssetPatch(BaseModel):
    name: Optional[str] = None
    asset_tag: Optional[str] = None
    purchase_cost: Optional[float] = None
    purchase_date: Optional[str] = None
    condition: Optional[str] = None
    service_due_date: Optional[str] = None
    replace_due_date: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("/assets", dependencies=[_require])
async def list_assets(
    include_inactive: bool = False,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    q = select(MerchAsset).where(MerchAsset.organisation_id == club.id)
    if not include_inactive:
        q = q.where(MerchAsset.is_active.is_(True))
    q = q.order_by(
        func.coalesce(MerchAsset.service_due_date, MerchAsset.replace_due_date).asc().nullslast(),
        MerchAsset.name,
    )
    assets = (await db.execute(q)).scalars().all()
    return {"assets": [_asset_out(a) for a in assets]}


@router.post("/assets", dependencies=[_require])
async def create_asset(
    body: AssetIn,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    if not (body.name or "").strip():
        raise HTTPException(status_code=422, detail="Name is required")
    if body.condition and body.condition not in MERCH_ASSET_CONDITIONS:
        raise HTTPException(status_code=422, detail=f"Unknown condition: {body.condition}")
    if body.status and body.status not in MERCH_ASSET_STATUSES:
        raise HTTPException(status_code=422, detail=f"Unknown status: {body.status}")
    a = MerchAsset(
        organisation_id=club.id,
        name=body.name.strip(),
        asset_tag=body.asset_tag,
        purchase_cost=_money(body.purchase_cost),
        purchase_date=_parse_date(body.purchase_date),
        condition=body.condition or "good",
        service_due_date=_parse_date(body.service_due_date),
        replace_due_date=_parse_date(body.replace_due_date),
        status=body.status or "in_service",
        notes=body.notes,
    )
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return _asset_out(a)


@router.patch("/assets/{asset_id}", dependencies=[_require])
async def update_asset(
    asset_id: str,
    body: AssetPatch,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    a = await _asset_or_404(db, club, asset_id)
    data = body.model_dump(exclude_unset=True)
    if "condition" in data and data["condition"] and data["condition"] not in MERCH_ASSET_CONDITIONS:
        raise HTTPException(status_code=422, detail=f"Unknown condition: {data['condition']}")
    if "status" in data and data["status"] and data["status"] not in MERCH_ASSET_STATUSES:
        raise HTTPException(status_code=422, detail=f"Unknown status: {data['status']}")
    for field in ("name", "asset_tag", "condition", "status", "notes", "is_active"):
        if field in data:
            setattr(a, field, data[field])
    if "purchase_cost" in data:
        a.purchase_cost = _money(data["purchase_cost"])
    for dfield in ("purchase_date", "service_due_date", "replace_due_date"):
        if dfield in data:
            setattr(a, dfield, _parse_date(data[dfield]))
    a.updated_at = func.now()
    await db.commit()
    await db.refresh(a)
    return _asset_out(a)


@router.delete("/assets/{asset_id}", dependencies=[_require])
async def delete_asset(
    asset_id: str,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    a = await _asset_or_404(db, club, asset_id)
    a.is_active = False
    await db.commit()
    return {"ok": True}


# ───────────────────────────────────────────────────────────────────────────
# Player merch (admin-only view — what a player holds + owes)
# ───────────────────────────────────────────────────────────────────────────

@router.get("/players", dependencies=[_require])
async def search_players(
    q: Optional[str] = None,
    limit: int = 20,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Lightweight roster picker for the 'issued to' field."""
    pq = select(Player).where(Player.organisation_id == club.id)
    if q:
        pq = pq.where(Player.name.ilike(f"%{q}%"))
    pq = pq.order_by(Player.name).limit(min(max(limit, 1), 50))
    players = (await db.execute(pq)).scalars().all()
    return {"players": [{"id": str(p.id), "name": _player_name(p)} for p in players]}


@router.get("/players/{player_id}/merch", dependencies=[_require])
async def player_merch(
    player_id: str,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    try:
        pl = await db.get(Player, uuid.UUID(str(player_id)))
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="Invalid player id")
    if not pl or pl.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Player not found")
    rows = await _movement_rows(db, club, player_id=player_id, limit=200)
    movements = [_movement_out(mv, p, v, plr) for mv, p, v, plr in rows]
    outstanding = sum(
        (m["amount"] or 0) for m in movements if not m["paid"] and m["amount"]
    )
    return {
        "player_id": str(pl.id),
        "player_name": _player_name(pl),
        "movements": movements,
        "outstanding": round(outstanding, 2),
    }


# ───────────────────────────────────────────────────────────────────────────
# Reports
# ───────────────────────────────────────────────────────────────────────────

@router.get("/reports/summary", dependencies=[_require])
async def report_summary(
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    summary = await merch_service.stock_summary(db, club.id)

    # Stock value by category.
    cost_expr = func.coalesce(MerchVariant.unit_cost, MerchProduct.unit_cost)
    price_expr = func.coalesce(MerchVariant.unit_price, MerchProduct.unit_price)
    cat_q = (
        select(
            MerchProduct.category,
            func.coalesce(func.sum(MerchVariant.quantity * cost_expr), 0),
            func.coalesce(func.sum(MerchVariant.quantity * price_expr), 0),
            func.coalesce(func.sum(MerchVariant.quantity), 0),
        )
        .join(MerchProduct, MerchProduct.id == MerchVariant.product_id)
        .where(
            MerchVariant.organisation_id == club.id,
            MerchVariant.is_active.is_(True),
            MerchProduct.is_active.is_(True),
        )
        .group_by(MerchProduct.category)
    )
    by_category = [
        {
            "category": cat,
            "stock_value_cost": float(cost or 0),
            "stock_value_retail": float(retail or 0),
            "units_on_hand": int(units or 0),
        }
        for cat, cost, retail, units in (await db.execute(cat_q)).all()
    ]

    # Stock value by item (each product, across its variants).
    item_q = (
        select(
            MerchProduct.id, MerchProduct.name, MerchProduct.category, MerchProduct.category_id, MerchProduct.for_resale,
            func.coalesce(func.sum(MerchVariant.quantity), 0),
            func.coalesce(func.sum(MerchVariant.quantity * cost_expr), 0),
            func.coalesce(func.sum(MerchVariant.quantity * price_expr), 0),
        )
        .join(MerchVariant, MerchVariant.product_id == MerchProduct.id)
        .where(
            MerchProduct.organisation_id == club.id,
            MerchProduct.is_active.is_(True),
            MerchVariant.is_active.is_(True),
        )
        .group_by(MerchProduct.id, MerchProduct.name, MerchProduct.category, MerchProduct.category_id, MerchProduct.for_resale)
        .order_by(MerchProduct.category, MerchProduct.name)
    )
    by_item = [
        {
            "product_id": str(pid),
            "name": name,
            "category": cat,
            "category_id": str(catid) if catid else None,
            "for_resale": resale,
            "units_on_hand": int(units or 0),
            "stock_value_cost": float(cost or 0),
            "stock_value_retail": float(retail or 0),
        }
        for pid, name, cat, catid, resale, units, cost, retail in (await db.execute(item_q)).all()
    ]

    # Roll item totals up the category tree so each node carries its own subtree.
    cats = await _categories_for_org(db, club.id)
    by_id, _children = _category_index(cats)
    node_tot = {str(c.id): {"units": 0, "cost": 0.0, "retail": 0.0} for c in cats}
    for it in by_item:
        cid, guard = it["category_id"], 0
        while cid and cid in node_tot and guard < 8:
            node_tot[cid]["units"] += it["units_on_hand"]
            node_tot[cid]["cost"] += it["stock_value_cost"]
            node_tot[cid]["retail"] += it["stock_value_retail"]
            parent = by_id[uuid.UUID(cid)].parent_id
            cid = str(parent) if parent else None
            guard += 1
    by_category_node = []
    for c in cats:
        t = node_tot[str(c.id)]
        node = _cat_out(c, by_id)
        node.update({
            "units_on_hand": t["units"],
            "stock_value_cost": round(t["cost"], 2),
            "stock_value_retail": round(t["retail"], 2),
        })
        by_category_node.append(node)
    by_category_node.sort(key=lambda n: (n["top_category"], n["path"]))

    # Outstanding merch money by player (unpaid sales / issues).
    owed_q = (
        select(
            Player.id, Player.name,
            func.coalesce(func.sum(MerchMovement.amount), 0),
        )
        .join(Player, Player.id == MerchMovement.player_id)
        .where(
            MerchMovement.organisation_id == club.id,
            MerchMovement.paid.is_(False),
            MerchMovement.amount.isnot(None),
        )
        .group_by(Player.id, Player.name)
        .order_by(func.coalesce(func.sum(MerchMovement.amount), 0).desc())
    )
    owed_by_player = [
        {"player_id": str(pid), "player_name": name, "owed": float(amt or 0)}
        for pid, name, amt in (await db.execute(owed_q)).all()
    ]

    summary["by_category"] = by_category
    summary["by_category_node"] = by_category_node
    summary["by_item"] = by_item
    summary["owed_by_player"] = owed_by_player
    return summary


@router.get("/reports/export", dependencies=[_require])
async def export_stock(
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """CSV of stock on hand at cost + retail."""
    q = (
        select(MerchProduct, MerchVariant)
        .join(MerchVariant, MerchVariant.product_id == MerchProduct.id)
        .where(
            MerchProduct.organisation_id == club.id,
            MerchProduct.is_active.is_(True),
            MerchVariant.is_active.is_(True),
        )
        .order_by(MerchProduct.category, MerchProduct.name, MerchVariant.label)
    )
    rows = (await db.execute(q)).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Category", "Product", "Variant", "SKU", "On hand",
                "Unit cost", "Unit price", "Stock value (cost)", "Stock value (retail)",
                "Low stock threshold", "Expiry"])
    for p, v in rows:
        cost = _eff_cost(v, p)
        price = _eff_price(v, p)
        qty = v.quantity or 0
        w.writerow([
            p.category, p.name, v.label, v.sku or "", qty,
            f"{float(cost):.2f}" if cost is not None else "",
            f"{float(price):.2f}" if price is not None else "",
            f"{qty * float(cost):.2f}" if cost is not None else "",
            f"{qty * float(price):.2f}" if price is not None else "",
            merch_service.variant_threshold(v, p) if merch_service.variant_threshold(v, p) is not None else "",
            v.expiry_date.isoformat() if v.expiry_date else "",
        ])
    csv_text = buf.getvalue()
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=merch-stock.csv"},
    )


# ───────────────────────────────────────────────────────────────────────────
# Square POS integration (canteen/bar stock + sales)
# ───────────────────────────────────────────────────────────────────────────

def _square_status(conn: MerchSquareConnection | None) -> dict:
    return {
        "configured": settings.square_configured,
        # What has to be registered as an Authorized Redirect URL on the Square
        # application, and under which environment. Served rather than hardcoded
        # on the screen so the instructions can never drift from what we send.
        "redirect_url": settings.square_oauth_redirect,
        "server_environment": settings.square_environment,
        "config_error": settings.square_config_error if settings.square_configured else None,
        "connected": bool(conn and conn.access_token),
        "merchant_id": conn.merchant_id if conn else None,
        "environment": conn.environment if conn else settings.square_environment,
        "location_id": conn.location_id if conn else None,
        "location_name": conn.location_name if conn else None,
        "sync_enabled": conn.sync_enabled if conn else True,
        "sync_sales": conn.sync_sales if conn else True,
        "needs_location": bool(conn and conn.access_token and not conn.location_id),
        "last_sync_at": conn.last_sync_at.isoformat() if conn and conn.last_sync_at else None,
        "last_sync_status": conn.last_sync_status if conn else None,
        "last_sync_error": conn.last_sync_error if conn else None,
    }


@router.get("/square/status", dependencies=[_require])
async def square_status(
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    conn = await square_sync.get_connection(db, club.id)
    return _square_status(conn)


@router.get("/square/connect-url", dependencies=[_require])
async def square_connect_url(
    current_user: User = Depends(require_cap(MANAGE_MERCH)),
    club: Organisation = Depends(get_current_club),
):
    # Catch a server-side misconfiguration here rather than letting the admin
    # sign in to Square and hit Square's own error page, which they can do
    # nothing about and which names no cause.
    problem = settings.square_config_error
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    state = sign_square_state(club.id, current_user.id)
    return {"url": square_client.authorize_url(state)}


@router.get("/square/locations", dependencies=[_require])
async def square_locations(
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    conn = await square_sync.get_connection(db, club.id)
    if not conn or not conn.access_token:
        raise HTTPException(status_code=400, detail="Connect Square first")
    try:
        token = await square_sync.ensure_fresh_token(db, conn)
        locs = await square_client.list_locations(token)
    except square_client.SquareError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"locations": [
        {"id": l.get("id"), "name": l.get("name"), "status": l.get("status")} for l in locs
    ]}


class SquareLocationIn(BaseModel):
    location_id: str
    location_name: Optional[str] = None


@router.post("/square/location", dependencies=[_require])
async def square_set_location(
    body: SquareLocationIn,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    conn = await square_sync.get_connection(db, club.id)
    if not conn or not conn.access_token:
        raise HTTPException(status_code=400, detail="Connect Square first")
    conn.location_id = body.location_id
    conn.location_name = body.location_name
    await db.commit()
    return _square_status(conn)


class SquareSettingsIn(BaseModel):
    sync_enabled: Optional[bool] = None
    sync_sales: Optional[bool] = None


@router.post("/square/settings", dependencies=[_require])
async def square_settings(
    body: SquareSettingsIn,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    conn = await square_sync.get_connection(db, club.id)
    if not conn:
        raise HTTPException(status_code=400, detail="Connect Square first")
    if body.sync_enabled is not None:
        conn.sync_enabled = body.sync_enabled
    if body.sync_sales is not None:
        conn.sync_sales = body.sync_sales
    await db.commit()
    return _square_status(conn)


@router.post("/square/sync", dependencies=[_require])
async def square_sync_now(
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await square_sync.sync_square(db, club.id)
    except square_client.SquareError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/square/disconnect", dependencies=[_require])
async def square_disconnect(
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    conn = await square_sync.get_connection(db, club.id)
    if conn:
        if conn.access_token:
            try:
                await square_client.revoke_token(conn.access_token)
            except Exception:
                pass  # best-effort; still drop our stored copy
        await db.delete(conn)
        await db.commit()
    return {"ok": True}


# ─── Online store orders (merch storefront, migration 179) ──────────────────
# The catalogue/checkout side is public (routers/public_merch_store.py) and
# flag-gated (platform_settings.merch_storefront_enabled_for_org); this is
# just the admin's fulfilment queue — always reachable once a club holds the
# merch module, same as every other tab on this router.

@router.get("/storefront-status", dependencies=[_require])
async def storefront_status(club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    """Whether the public merch storefront is switched on for this club —
    every MANAGE_MERCH holder already reaches this router, so no separate
    uncapped nav-visibility endpoint is needed (unlike the member portal,
    whose nav item sits in the general admin nav where a user might not
    hold MANAGE_FEES at all)."""
    from app.services import platform_settings as ps
    return {"enabled": await ps.merch_storefront_enabled_for_org(db, club)}


@router.get("/orders", dependencies=[_require])
async def list_orders(
    status: Optional[str] = None,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    if status is not None and status not in MERCH_ORDER_STATUSES:
        raise HTTPException(status_code=422, detail=f"Unknown status: {status}")
    orders = await merch_store_service.list_orders(db, club.id, status=status)
    return {"orders": [merch_store_service._order_dict(o) for o in orders]}


class OrderStatusPatch(BaseModel):
    status: str


@router.patch("/orders/{order_id}", dependencies=[_require])
async def update_order(
    order_id: str,
    body: OrderStatusPatch,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    if body.status not in MERCH_ORDER_STATUSES:
        raise HTTPException(status_code=422, detail=f"Unknown status: {body.status}")
    order = await db.get(MerchOrder, uuid.UUID(order_id))
    if not order or order.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Order not found")
    await merch_store_service.update_order_status(db, order, body.status)
    await db.commit()
    return {"id": str(order.id), "status": order.status}
