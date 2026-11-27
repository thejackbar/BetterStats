"""Teamwear ordering: the shop range, campaigns, member orders, triage, approval and payments.

How a round runs (see the Concept of Operations the module was built from):

1. SHOP SETUP. The range is the BetterMerch stock register: a teamwear product is a
   ``merch_products`` row whose sizes are ``merch_variants``; ``teamwear_products`` adds the
   supplier code, RRP, made-to-order flag, personalisation and minimum order. Price is the RRP
   (inc GST) plus the club's markup, rounded UP to the club's step, unless the coordinator sets
   a price for that product.
2. ANNOUNCE. A campaign picks made-to-order products and dates; launching it opens ordering
   and can email the club's players.
3. ORDER. Members order from their Player Dashboard. One order covers several wearers
   (themselves, their family, or a typed name). A personalised garment is one line each.
4. TRIAGE. After close the coordinator decides include, cut or hold per product, and tops up
   sizes to reach the supplier's minimum (top-ups become club stock). A product whose top-ups
   would be ``cut_ratio`` or more per member unit is flagged Suggested cut.
5. CONFIRM. The coordinator records the committee's approval of the whole plan. Recording it
   cuts the lines of every cut product (the member sees Not available this round), and any
   later change to the plan clears the approval and puts those lines back.
6. PAY. Payment requests go to every order with something left in it. Payments are recorded by
   hand, matched from a bank CSV, or taken by card (Stripe Connect or a Square payment link).
   An unpaid order is never cancelled by the system: the coordinator decides case by case.
7. EXPORT. Once every order is paid or decided, the order locks and the supplier form is built.
8. RECEIVE. Top-ups go into club stock, orders are packed and the arrival email goes out.

Derived, never stored: an order's total, what has been paid, the balance, whether ordering is
open, and the whole triage table.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import MerchProduct, MerchVariant, Organisation, Player
from app.services import merch as merch_service
from app.services.player_kit import clean_shirt_number

logger = logging.getLogger(__name__)

TZ = ZoneInfo("Australia/Perth")

STAGES = ("draft", "open", "triage", "payment", "exported", "received", "closed", "cancelled")
DECISIONS = ("include", "cut", "hold")
PERSONALISATION = ("none", "number_name", "number_initials")
PERSONALISATION_LABEL = {"none": None, "number_name": "Name", "number_initials": "Initials"}
PAYMENT_METHODS = ("bank", "card", "cash", "other")
UNPAID_DECISIONS = ("proceed",)
CENT = Decimal("0.01")
MAX_LINES = 60
MAX_QTY = 50


class TeamwearError(Exception):
    """A refusal the person can read. ``status`` is the HTTP status the router answers with."""

    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


# ── small helpers ───────────────────────────────────────────────────────────

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def today_local() -> date:
    return datetime.now(TZ).date()


def _uuid(v, what: str = "id") -> uuid.UUID:
    try:
        return uuid.UUID(str(v))
    except (TypeError, ValueError):
        raise TeamwearError(f"Invalid {what}")


def money(v) -> Optional[Decimal]:
    if v is None or v == "":
        return None
    try:
        d = Decimal(str(v)).quantize(CENT)
    except (InvalidOperation, TypeError, ValueError):
        raise TeamwearError("Invalid amount")
    return d


def f2(v) -> Optional[float]:
    return float(v) if v is not None else None


def iso(v) -> Optional[str]:
    return v.isoformat() if v is not None else None


def caps(v) -> Optional[str]:
    """Personalisation text is stored in capitals, trimmed, inner spaces collapsed. No length limit."""
    if v is None:
        return None
    s = re.sub(r"\s+", " ", str(v)).strip().upper()
    return s or None


def parse_offsets(raw) -> list[int]:
    """Reminder days relative to the due date ("-3,0,3"), each once, sorted. Junk is dropped."""
    out: list[int] = []
    if raw is None:
        return out
    parts = raw if isinstance(raw, (list, tuple)) else str(raw).split(",")
    for p in parts:
        try:
            n = int(str(p).strip())
        except (TypeError, ValueError):
            continue
        if -60 <= n <= 60 and n not in out:
            out.append(n)
    return sorted(out)


def price_for(rrp, override, markup_pct, round_to) -> Optional[Decimal]:
    """RRP inc GST plus the markup, rounded UP to the club's step. An override wins."""
    if override is not None:
        return Decimal(str(override)).quantize(CENT)
    if rrp is None:
        return None
    raw = Decimal(str(rrp)) * (Decimal(1) + Decimal(str(markup_pct or 0)) / Decimal(100))
    step = Decimal(str(round_to or 0))
    if step <= 0:
        return raw.quantize(CENT, rounding=ROUND_CEILING)
    return ((raw / step).to_integral_value(rounding=ROUND_CEILING) * step).quantize(CENT)


def surname_of(name: str) -> str:
    """The surname a bank reference is built from. "Smith, Jo" and "Jo Smith" both give SMITH."""
    s = (name or "").strip()
    if "," in s:
        s = s.split(",", 1)[0]
    else:
        parts = s.split()
        s = parts[-1] if parts else ""
    s = re.sub(r"[^A-Za-z]", "", s).upper()
    return s or "MEMBER"


def ref_key(s: str) -> str:
    """A reference as a bank statement carries it: letters and digits only, capitals."""
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


# ── settings ────────────────────────────────────────────────────────────────

SETTINGS_FIELDS = (
    "markup_pct", "round_to", "default_moq", "cut_ratio", "supplier_name", "bank_account_name",
    "bank_bsb", "bank_account_number", "reference_suffix", "coordinator_name", "coordinator_email",
    "pay_days", "reminder_offsets", "card_stripe", "card_square",
)
SETTINGS_DEFAULTS = {
    "markup_pct": Decimal(10), "round_to": Decimal(1), "default_moq": 10, "cut_ratio": 9,
    "supplier_name": "Masuri", "bank_account_name": None, "bank_bsb": None, "bank_account_number": None,
    "reference_suffix": "TEAMWEAR", "coordinator_name": None, "coordinator_email": None,
    "pay_days": 14, "reminder_offsets": "-3,0,3", "card_stripe": True, "card_square": True,
}


async def get_settings(db: AsyncSession, org_id) -> dict:
    r = (await db.execute(text(
        f"SELECT {', '.join(SETTINGS_FIELDS)} FROM teamwear_settings WHERE organisation_id = CAST(:o AS UUID)"),
        {"o": str(org_id)})).mappings().first()
    return dict(r) if r else dict(SETTINGS_DEFAULTS)


def settings_out(s: dict) -> dict:
    out = dict(s)
    out["markup_pct"] = f2(s.get("markup_pct"))
    out["round_to"] = f2(s.get("round_to"))
    out["reminder_offsets"] = parse_offsets(s.get("reminder_offsets"))
    return out


async def save_settings(db: AsyncSession, org_id, patch: dict) -> dict:
    """Only the keys sent change (an absent key is not a clear)."""
    cur = await get_settings(db, org_id)
    for k, v in patch.items():
        if k not in SETTINGS_FIELDS:
            continue
        if k in ("markup_pct", "round_to"):
            d = money(v)
            if d is None or d < 0 or d > 1000:
                raise TeamwearError("Markup and rounding must be zero or more.")
            cur[k] = d
        elif k in ("default_moq", "cut_ratio", "pay_days"):
            try:
                n = int(v)
            except (TypeError, ValueError):
                raise TeamwearError(f"{k.replace('_', ' ').capitalize()} must be a whole number.")
            if n < 0 or n > 1000:
                raise TeamwearError(f"{k.replace('_', ' ').capitalize()} is out of range.")
            cur[k] = n
        elif k == "reminder_offsets":
            cur[k] = ",".join(str(n) for n in parse_offsets(v))
        elif k in ("card_stripe", "card_square"):
            cur[k] = bool(v)
        elif k == "reference_suffix":
            cur[k] = (re.sub(r"[^A-Za-z0-9 ]", "", str(v or "")).strip().upper() or "TEAMWEAR")[:20]
        else:
            cur[k] = (str(v).strip() or None) if v is not None else None
    cols = ", ".join(SETTINGS_FIELDS)
    vals = ", ".join(f":{k}" for k in SETTINGS_FIELDS)
    upd = ", ".join(f"{k} = EXCLUDED.{k}" for k in SETTINGS_FIELDS)
    await db.execute(text(
        f"INSERT INTO teamwear_settings (organisation_id, {cols}) VALUES (CAST(:o AS UUID), {vals}) "
        f"ON CONFLICT (organisation_id) DO UPDATE SET {upd}, updated_at = NOW()"),
        {"o": str(org_id), **{k: cur[k] for k in SETTINGS_FIELDS}})
    return cur


# ── the shop range ──────────────────────────────────────────────────────────

async def _range_rows(db: AsyncSession, org_id, product_ids: Optional[list] = None) -> list[dict]:
    q = (
        "SELECT p.id, p.name, p.description, p.is_active, p.unit_price, "
        "t.supplier_code, t.rrp, t.price_override, t.made_to_order, t.personalisation, t.moq, t.in_shop, t.sort_order "
        "FROM teamwear_products t JOIN merch_products p ON p.id = t.product_id "
        "WHERE t.organisation_id = CAST(:o AS UUID)"
    )
    params = {"o": str(org_id)}
    if product_ids is not None:
        q += " AND t.product_id = ANY(CAST(:ids AS UUID[]))"
        params["ids"] = [str(i) for i in product_ids]
    q += " ORDER BY t.sort_order, p.name"
    return [dict(r) for r in (await db.execute(text(q), params)).mappings().all()]


async def _variants_for(db: AsyncSession, product_ids: list) -> dict:
    if not product_ids:
        return {}
    rows = (await db.execute(text(
        "SELECT id, product_id, label, size, sku, quantity, is_active, created_at FROM merch_variants "
        "WHERE product_id = ANY(CAST(:ids AS UUID[])) ORDER BY created_at, label"),
        {"ids": [str(i) for i in product_ids]})).mappings().all()
    out: dict = {}
    for r in rows:
        out.setdefault(r["product_id"], []).append(dict(r))
    return out


async def _images_for(db: AsyncSession, product_ids: list) -> dict:
    if not product_ids:
        return {}
    rows = (await db.execute(text(
        "SELECT id, product_id FROM teamwear_images WHERE product_id = ANY(CAST(:ids AS UUID[])) "
        "ORDER BY sort_order, created_at"), {"ids": [str(i) for i in product_ids]})).mappings().all()
    out: dict = {}
    for r in rows:
        out.setdefault(r["product_id"], []).append(str(r["id"]))
    return out


async def reserved_stock(db: AsyncSession, org_id) -> dict:
    """Units of each variant already promised to a shop order that has not been handed over."""
    rows = (await db.execute(text(
        "SELECT l.variant_id, SUM(l.qty) AS n FROM teamwear_order_lines l "
        "JOIN teamwear_orders o ON o.id = l.order_id "
        "WHERE o.organisation_id = CAST(:o AS UUID) AND o.status <> 'cancelled' AND l.from_stock "
        "AND l.state = 'active' AND l.issued_at IS NULL AND l.variant_id IS NOT NULL GROUP BY l.variant_id"),
        {"o": str(org_id)})).mappings().all()
    return {r["variant_id"]: int(r["n"] or 0) for r in rows}


def image_url(image_id: str) -> str:
    return f"/api/public/teamwear/images/{image_id}"


async def list_range(db: AsyncSession, org_id, *, only_shop: bool = False, product_ids=None) -> list[dict]:
    s = await get_settings(db, org_id)
    rows = await _range_rows(db, org_id, product_ids)
    if only_shop:
        rows = [r for r in rows if r["in_shop"] and r["is_active"]]
    ids = [r["id"] for r in rows]
    variants = await _variants_for(db, ids)
    images = await _images_for(db, ids)
    held = await reserved_stock(db, org_id)
    out = []
    for r in rows:
        price = price_for(r["rrp"], r["price_override"], s["markup_pct"], s["round_to"])
        if price is None and r["unit_price"] is not None:
            price = Decimal(str(r["unit_price"])).quantize(CENT)
        sizes = []
        for v in variants.get(r["id"], []):
            if not v["is_active"]:
                continue
            avail = max(0, int(v["quantity"] or 0) - held.get(v["id"], 0))
            sizes.append({"variant_id": str(v["id"]), "label": v["size"] or v["label"], "sku": v["sku"],
                          "on_hand": int(v["quantity"] or 0), "available": avail})
        out.append({
            "product_id": str(r["id"]), "name": r["name"], "description": r["description"],
            "active": bool(r["is_active"]), "supplier_code": r["supplier_code"], "rrp": f2(r["rrp"]),
            "price_override": f2(r["price_override"]), "price": f2(price),
            "made_to_order": bool(r["made_to_order"]), "personalisation": r["personalisation"],
            "personal_label": PERSONALISATION_LABEL.get(r["personalisation"]),
            "moq": r["moq"], "in_shop": bool(r["in_shop"]), "sort_order": r["sort_order"],
            "sizes": sizes, "images": [image_url(i) for i in images.get(r["id"], [])],
            "image_ids": images.get(r["id"], []),
            "in_stock": sum(x["available"] for x in sizes),
        })
    return out


def _clean_sizes(raw) -> list[str]:
    out: list[str] = []
    parts = raw if isinstance(raw, (list, tuple)) else str(raw or "").split(",")
    for p in parts:
        s = re.sub(r"\s+", " ", str(p)).strip()[:24]
        if s and s.lower() not in [o.lower() for o in out]:
            out.append(s)
    return out


async def save_range_product(db: AsyncSession, org_id, data: dict, product_id=None, user_id=None) -> str:
    """Create or edit a shop product. ``data`` holds only the keys that change. Sizes are added as
    variants; a size taken off the list is switched off (never deleted: stock and history hang off it)."""
    fields = set(data.keys())
    if product_id is None:
        name = (data.get("name") or "").strip()
        if not name:
            raise TeamwearError("Give the product a name.")
        p = MerchProduct(organisation_id=org_id, category="apparel", name=name,
                         description=(data.get("description") or None), for_resale=True,
                         show_in_storefront=False, supplier=(data.get("supplier") or None))
        db.add(p)
        await db.flush()
        product_id = p.id
        await db.execute(text(
            "INSERT INTO teamwear_products (product_id, organisation_id) VALUES (CAST(:p AS UUID), CAST(:o AS UUID)) "
            "ON CONFLICT (product_id) DO NOTHING"), {"p": str(product_id), "o": str(org_id)})
        fields.discard("name")
        fields.discard("description")
    else:
        p = await db.get(MerchProduct, _uuid(product_id, "product id"))
        if p is None or p.organisation_id != org_id:
            raise TeamwearError("Product not found", 404)
        await db.execute(text(
            "INSERT INTO teamwear_products (product_id, organisation_id) VALUES (CAST(:p AS UUID), CAST(:o AS UUID)) "
            "ON CONFLICT (product_id) DO NOTHING"), {"p": str(p.id), "o": str(org_id)})
        if "name" in fields:
            nm = (data.get("name") or "").strip()
            if not nm:
                raise TeamwearError("Give the product a name.")
            p.name = nm
        if "description" in fields:
            p.description = data.get("description") or None
        if "active" in fields:
            p.is_active = bool(data.get("active"))

    sets, params = [], {"p": str(product_id)}
    if "supplier_code" in fields:
        sets.append("supplier_code = :code")
        params["code"] = (str(data.get("supplier_code") or "").strip() or None)
    if "rrp" in fields:
        sets.append("rrp = :rrp")
        params["rrp"] = money(data.get("rrp"))
    if "price_override" in fields:
        sets.append("price_override = :po")
        params["po"] = money(data.get("price_override"))
    if "made_to_order" in fields:
        sets.append("made_to_order = :mto")
        params["mto"] = bool(data.get("made_to_order"))
    if "personalisation" in fields:
        v = data.get("personalisation") or "none"
        if v not in PERSONALISATION:
            raise TeamwearError("Personalisation is none, number and name, or number and initials.")
        sets.append("personalisation = :pers")
        params["pers"] = v
    if "moq" in fields:
        v = data.get("moq")
        if v in (None, ""):
            params["moq"] = None
        else:
            try:
                params["moq"] = max(0, int(v))
            except (TypeError, ValueError):
                raise TeamwearError("Minimum order must be a whole number.")
        sets.append("moq = :moq")
    if "in_shop" in fields:
        sets.append("in_shop = :shop")
        params["shop"] = bool(data.get("in_shop"))
    if "sort_order" in fields:
        sets.append("sort_order = :so")
        params["so"] = int(data.get("sort_order") or 0)
    if sets:
        await db.execute(text(
            f"UPDATE teamwear_products SET {', '.join(sets)}, updated_at = NOW() WHERE product_id = CAST(:p AS UUID)"),
            params)

    if "sizes" in fields:
        wanted = _clean_sizes(data.get("sizes"))
        existing = (await db.execute(select(MerchVariant).where(MerchVariant.product_id == product_id))).scalars().all()
        by_label = {((v.size or v.label) or "").lower(): v for v in existing}
        stamp = now_utc()
        for n, label in enumerate(wanted):
            v = by_label.get(label.lower())
            if v is None:
                # Sizes read back in the order they were typed (S, M, L, XL), so each gets its own moment.
                db.add(MerchVariant(product_id=product_id, organisation_id=org_id, label=label, size=label, quantity=0,
                                    created_at=stamp + timedelta(microseconds=n)))
            elif not v.is_active:
                v.is_active = True
        keep = {w.lower() for w in wanted}
        for v in existing:
            if ((v.size or v.label) or "").lower() not in keep and v.is_active:
                v.is_active = False
        if not wanted and not existing:
            db.add(MerchVariant(product_id=product_id, organisation_id=org_id, label="Standard", quantity=0))
    await db.flush()
    return str(product_id)


async def add_existing_product(db: AsyncSession, org_id, product_id) -> str:
    """Bring a product already in the stock register into the shop range (in stock, not made to order)."""
    p = await db.get(MerchProduct, _uuid(product_id, "product id"))
    if p is None or p.organisation_id != org_id:
        raise TeamwearError("Product not found", 404)
    await db.execute(text(
        "INSERT INTO teamwear_products (product_id, organisation_id, made_to_order, rrp) "
        "VALUES (CAST(:p AS UUID), CAST(:o AS UUID), false, :price) ON CONFLICT (product_id) DO NOTHING"),
        {"p": str(p.id), "o": str(org_id), "price": None})
    if p.unit_price is not None:
        await db.execute(text(
            "UPDATE teamwear_products SET price_override = COALESCE(price_override, :pr) WHERE product_id = CAST(:p AS UUID)"),
            {"p": str(p.id), "pr": Decimal(str(p.unit_price)).quantize(CENT)})
    return str(p.id)


async def remove_from_range(db: AsyncSession, org_id, product_id) -> None:
    """Take a product out of the shop. The stock-register product and its history stay."""
    pid = _uuid(product_id, "product id")
    used = (await db.execute(text(
        "SELECT 1 FROM teamwear_campaign_items i JOIN teamwear_campaigns c ON c.id = i.campaign_id "
        "WHERE i.product_id = CAST(:p AS UUID) AND c.stage NOT IN ('closed', 'cancelled') LIMIT 1"),
        {"p": str(pid)})).first()
    if used:
        raise TeamwearError("This product is in a campaign that is still running. Hide it from the shop instead.", 409)
    await db.execute(text(
        "DELETE FROM teamwear_products WHERE product_id = CAST(:p AS UUID) AND organisation_id = CAST(:o AS UUID)"),
        {"p": str(pid), "o": str(org_id)})


# ── campaigns ───────────────────────────────────────────────────────────────

CAMPAIGN_COLS = (
    "id, organisation_id, name, intro, stage, opens_on, closes_at, pay_due_on, reminder_offsets, moq, launched_at, "
    "approved_on, approval_note, approval_recorded_by, approval_recorded_at, approved_plan, payment_requested_at, "
    "exported_at, deposit_paid_on, balance_paid_on, received_at, arrival_emailed_at, closed_at, created_at"
)


def ordering_open(c: dict, at: Optional[datetime] = None) -> bool:
    """Members may order: the campaign is open, has started and has not closed. Derived on read."""
    if c["stage"] != "open":
        return False
    at = at or now_utc()
    if c.get("opens_on") and at.astimezone(TZ).date() < c["opens_on"]:
        return False
    if c.get("closes_at") and at >= c["closes_at"]:
        return False
    return True


async def get_campaign(db: AsyncSession, org_id, campaign_id) -> dict:
    r = (await db.execute(text(
        f"SELECT {CAMPAIGN_COLS} FROM teamwear_campaigns WHERE id = CAST(:c AS UUID) AND organisation_id = CAST(:o AS UUID)"),
        {"c": str(_uuid(campaign_id, "campaign id")), "o": str(org_id)})).mappings().first()
    if not r:
        raise TeamwearError("Campaign not found", 404)
    return dict(r)


async def campaign_items(db: AsyncSession, campaign_id) -> list[dict]:
    rows = (await db.execute(text(
        "SELECT i.product_id, i.price, i.decision, i.decision_note, i.sort_order, p.name, t.supplier_code, "
        "t.personalisation, t.moq FROM teamwear_campaign_items i JOIN merch_products p ON p.id = i.product_id "
        "LEFT JOIN teamwear_products t ON t.product_id = i.product_id "
        "WHERE i.campaign_id = CAST(:c AS UUID) ORDER BY i.sort_order, p.name"),
        {"c": str(campaign_id)})).mappings().all()
    return [dict(r) for r in rows]


def campaign_out(c: dict, *, settings: Optional[dict] = None) -> dict:
    s = settings or SETTINGS_DEFAULTS
    offsets = parse_offsets(c.get("reminder_offsets")) if c.get("reminder_offsets") is not None else parse_offsets(s.get("reminder_offsets"))
    return {
        "id": str(c["id"]), "name": c["name"], "intro": c["intro"], "stage": c["stage"],
        "opens_on": iso(c["opens_on"]), "closes_at": iso(c["closes_at"]), "pay_due_on": iso(c["pay_due_on"]),
        "reminder_offsets": offsets, "reminder_offsets_own": c.get("reminder_offsets") is not None,
        "moq": c["moq"] if c["moq"] is not None else s.get("default_moq"),
        "launched_at": iso(c["launched_at"]), "ordering_open": ordering_open(c),
        "approved": c["approved_on"] is not None, "approved_on": iso(c["approved_on"]),
        "approval_note": c["approval_note"], "approval_recorded_at": iso(c["approval_recorded_at"]),
        "payment_requested_at": iso(c["payment_requested_at"]), "exported_at": iso(c["exported_at"]),
        "deposit_paid_on": iso(c["deposit_paid_on"]), "balance_paid_on": iso(c["balance_paid_on"]),
        "received_at": iso(c["received_at"]), "arrival_emailed_at": iso(c["arrival_emailed_at"]),
        "closed_at": iso(c["closed_at"]), "created_at": iso(c["created_at"]),
    }


def _parse_dt(v) -> Optional[datetime]:
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=TZ)
    s = str(v)
    try:
        if len(s) == 10:
            # A bare date closes at the end of that day, club time.
            d = date.fromisoformat(s)
            return datetime(d.year, d.month, d.day, 23, 59, tzinfo=TZ)
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        raise TeamwearError(f"Invalid date and time: {s}")
    return dt if dt.tzinfo else dt.replace(tzinfo=TZ)


def _parse_date(v) -> Optional[date]:
    if v in (None, ""):
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise TeamwearError(f"Invalid date: {v}")


async def list_campaigns(db: AsyncSession, org_id) -> list[dict]:
    s = await get_settings(db, org_id)
    rows = (await db.execute(text(
        f"SELECT {CAMPAIGN_COLS} FROM teamwear_campaigns WHERE organisation_id = CAST(:o AS UUID) "
        "ORDER BY created_at DESC"), {"o": str(org_id)})).mappings().all()
    counts = {r["campaign_id"]: r for r in (await db.execute(text(
        "SELECT o.campaign_id, COUNT(DISTINCT o.id) AS orders, COALESCE(SUM(l.qty), 0) AS units "
        "FROM teamwear_orders o LEFT JOIN teamwear_order_lines l ON l.order_id = o.id AND l.state = 'active' "
        "WHERE o.organisation_id = CAST(:o AS UUID) AND o.status <> 'cancelled' AND o.campaign_id IS NOT NULL "
        "GROUP BY o.campaign_id"), {"o": str(org_id)})).mappings().all()}
    out = []
    for r in rows:
        c = campaign_out(dict(r), settings=s)
        k = counts.get(r["id"])
        c["orders"] = int(k["orders"]) if k else 0
        c["units"] = int(k["units"]) if k else 0
        out.append(c)
    return out


async def create_campaign(db: AsyncSession, org_id, data: dict, user_id=None) -> str:
    name = (data.get("name") or "").strip()
    if not name:
        raise TeamwearError("Give the campaign a name.")
    cid = uuid.uuid4()
    await db.execute(text(
        "INSERT INTO teamwear_campaigns (id, organisation_id, name, intro, opens_on, closes_at, pay_due_on, created_by) "
        "VALUES (CAST(:id AS UUID), CAST(:o AS UUID), :n, :intro, :opens, :closes, :due, CAST(:u AS UUID))"),
        {"id": str(cid), "o": str(org_id), "n": name, "intro": data.get("intro") or None,
         "opens": _parse_date(data.get("opens_on")), "closes": _parse_dt(data.get("closes_at")),
         "due": _parse_date(data.get("pay_due_on")), "u": str(user_id) if user_id else None})
    if data.get("product_ids") is not None:
        await set_campaign_items(db, org_id, cid, data.get("product_ids") or [])
    return str(cid)


async def update_campaign(db: AsyncSession, org_id, campaign_id, data: dict) -> None:
    c = await get_campaign(db, org_id, campaign_id)
    if c["stage"] in ("closed", "cancelled"):
        raise TeamwearError("This campaign is finished.", 409)
    sets, params = [], {"c": str(c["id"])}
    if "name" in data:
        nm = (data.get("name") or "").strip()
        if not nm:
            raise TeamwearError("Give the campaign a name.")
        sets.append("name = :name")
        params["name"] = nm
    if "intro" in data:
        sets.append("intro = :intro")
        params["intro"] = data.get("intro") or None
    if "opens_on" in data:
        sets.append("opens_on = :opens")
        params["opens"] = _parse_date(data.get("opens_on"))
    if "closes_at" in data:
        sets.append("closes_at = :closes")
        params["closes"] = _parse_dt(data.get("closes_at"))
    if "pay_due_on" in data:
        sets.append("pay_due_on = :due")
        params["due"] = _parse_date(data.get("pay_due_on"))
    if "reminder_offsets" in data:
        sets.append("reminder_offsets = :rem")
        v = data.get("reminder_offsets")
        params["rem"] = None if v is None else ",".join(str(n) for n in parse_offsets(v))
    if "moq" in data:
        v = data.get("moq")
        sets.append("moq = :moq")
        try:
            params["moq"] = None if v in (None, "") else max(0, int(v))
        except (TypeError, ValueError):
            raise TeamwearError("Minimum order must be a whole number.")
    if "deposit_paid_on" in data:
        sets.append("deposit_paid_on = :dep")
        params["dep"] = _parse_date(data.get("deposit_paid_on"))
    if "balance_paid_on" in data:
        sets.append("balance_paid_on = :bal")
        params["bal"] = _parse_date(data.get("balance_paid_on"))
    if sets:
        await db.execute(text(
            f"UPDATE teamwear_campaigns SET {', '.join(sets)}, updated_at = NOW() WHERE id = CAST(:c AS UUID)"), params)
    if "product_ids" in data:
        await set_campaign_items(db, org_id, c["id"], data.get("product_ids") or [])


async def set_campaign_items(db: AsyncSession, org_id, campaign_id, product_ids: Iterable) -> None:
    """Which made-to-order products a campaign offers. Prices are snapshotted when a product is added
    (and refreshed while the campaign is still a draft). A product someone has ordered cannot leave."""
    c = await get_campaign(db, org_id, campaign_id)
    if c["stage"] not in ("draft", "open"):
        raise TeamwearError("The range is fixed once ordering has closed.", 409)
    ids = [str(_uuid(p, "product id")) for p in product_ids]
    rng = {r["product_id"]: r for r in await list_range(db, org_id, product_ids=ids)}
    missing = [i for i in ids if i not in rng]
    if missing:
        raise TeamwearError("One of those products is not in the shop range.")
    nopr = [rng[i]["name"] for i in ids if rng[i]["price"] is None]
    if nopr:
        raise TeamwearError(f"Set an RRP or a price for {', '.join(nopr)} first.")
    current = {str(r["product_id"]) for r in await campaign_items(db, c["id"])}
    gone = current - set(ids)
    if gone:
        used = (await db.execute(text(
            "SELECT DISTINCT p.name FROM teamwear_order_lines l JOIN teamwear_orders o ON o.id = l.order_id "
            "JOIN merch_products p ON p.id = l.product_id WHERE o.campaign_id = CAST(:c AS UUID) "
            "AND o.status <> 'cancelled' AND l.state = 'active' AND l.product_id = ANY(CAST(:ids AS UUID[]))"),
            {"c": str(c["id"]), "ids": list(gone)})).scalars().all()
        if used:
            raise TeamwearError(f"Members have already ordered {', '.join(used)}. Cut it at triage instead.", 409)
        await db.execute(text(
            "DELETE FROM teamwear_campaign_items WHERE campaign_id = CAST(:c AS UUID) AND product_id = ANY(CAST(:ids AS UUID[]))"),
            {"c": str(c["id"]), "ids": list(gone)})
    for n, pid in enumerate(ids):
        price = Decimal(str(rng[pid]["price"])).quantize(CENT)
        refresh = "price = EXCLUDED.price, " if c["stage"] == "draft" else ""
        await db.execute(text(
            "INSERT INTO teamwear_campaign_items (campaign_id, product_id, price, sort_order) "
            "VALUES (CAST(:c AS UUID), CAST(:p AS UUID), :price, :so) "
            f"ON CONFLICT (campaign_id, product_id) DO UPDATE SET {refresh}sort_order = EXCLUDED.sort_order"),
            {"c": str(c["id"]), "p": pid, "price": price, "so": n})


async def set_item_price(db: AsyncSession, org_id, campaign_id, product_id, price) -> None:
    """Change one product's price in a campaign. Lines not yet asked to pay follow the new price."""
    c = await get_campaign(db, org_id, campaign_id)
    if c["stage"] not in ("draft", "open", "triage") or c["payment_requested_at"]:
        raise TeamwearError("Prices are fixed once payment requests have gone.", 409)
    pr = money(price)
    if pr is None or pr < 0:
        raise TeamwearError("Enter a price.")
    await db.execute(text(
        "UPDATE teamwear_campaign_items SET price = :pr WHERE campaign_id = CAST(:c AS UUID) AND product_id = CAST(:p AS UUID)"),
        {"pr": pr, "c": str(c["id"]), "p": str(_uuid(product_id))})
    await db.execute(text(
        "UPDATE teamwear_order_lines l SET unit_price = :pr, updated_at = NOW() FROM teamwear_orders o "
        "WHERE o.id = l.order_id AND o.campaign_id = CAST(:c AS UUID) AND l.product_id = CAST(:p AS UUID)"),
        {"pr": pr, "c": str(c["id"]), "p": str(_uuid(product_id))})


async def set_stage(db: AsyncSession, campaign_id, stage: str, **stamps) -> None:
    sets = ["stage = :s", "updated_at = NOW()"] + [f"{k} = :{k}" for k in stamps]
    await db.execute(text(f"UPDATE teamwear_campaigns SET {', '.join(sets)} WHERE id = CAST(:c AS UUID)"),
                     {"s": stage, "c": str(campaign_id), **stamps})


async def launch_campaign(db: AsyncSession, org_id, campaign_id) -> dict:
    c = await get_campaign(db, org_id, campaign_id)
    if c["stage"] not in ("draft", "open"):
        raise TeamwearError("Only a draft campaign can be launched.", 409)
    if not await campaign_items(db, c["id"]):
        raise TeamwearError("Add at least one product before launching.")
    if c["closes_at"] is None:
        raise TeamwearError("Set the date ordering closes before launching.")
    if c["closes_at"] <= now_utc():
        raise TeamwearError("The close date has already passed.")
    await set_stage(db, c["id"], "open", launched_at=c["launched_at"] or now_utc())
    return await get_campaign(db, org_id, c["id"])


async def close_ordering(db: AsyncSession, org_id, campaign_id) -> None:
    """Move to triage. Ordering stops whether or not the close date has passed."""
    c = await get_campaign(db, org_id, campaign_id)
    if c["stage"] != "open":
        raise TeamwearError("Ordering is not open.", 409)
    stamps = {}
    if c["closes_at"] is None or c["closes_at"] > now_utc():
        stamps["closes_at"] = now_utc()
    await set_stage(db, c["id"], "triage", **stamps)


async def reopen_ordering(db: AsyncSession, org_id, campaign_id, closes_at) -> None:
    c = await get_campaign(db, org_id, campaign_id)
    if c["stage"] not in ("open", "triage") or c["payment_requested_at"]:
        raise TeamwearError("Ordering can only reopen before payment requests go.", 409)
    new_close = _parse_dt(closes_at)
    if new_close is None or new_close <= now_utc():
        raise TeamwearError("Pick a close date in the future.")
    await _clear_approval(db, c)
    await set_stage(db, c["id"], "open", closes_at=new_close)


async def cancel_campaign(db: AsyncSession, org_id, campaign_id, user_id=None) -> None:
    c = await get_campaign(db, org_id, campaign_id)
    if c["stage"] in ("exported", "received", "closed"):
        raise TeamwearError("This campaign has gone to the supplier and cannot be cancelled.", 409)
    paid = (await db.execute(text(
        "SELECT COUNT(*) FROM teamwear_payments p JOIN teamwear_orders o ON o.id = p.order_id "
        "WHERE o.campaign_id = CAST(:c AS UUID) AND p.voided_at IS NULL"), {"c": str(c["id"])})).scalar() or 0
    if paid:
        raise TeamwearError("Members have paid into this campaign. Refund and void those payments first.", 409)
    await db.execute(text(
        "UPDATE teamwear_orders SET status = 'cancelled', cancelled_reason = 'Campaign cancelled', updated_at = NOW() "
        "WHERE campaign_id = CAST(:c AS UUID) AND status <> 'cancelled'"), {"c": str(c["id"])})
    await set_stage(db, c["id"], "cancelled", closed_at=now_utc())


async def complete_campaign(db: AsyncSession, org_id, campaign_id) -> None:
    c = await get_campaign(db, org_id, campaign_id)
    if c["stage"] != "received":
        raise TeamwearError("Mark the kit received first.", 409)
    await set_stage(db, c["id"], "closed", closed_at=now_utc())


# ── orders ──────────────────────────────────────────────────────────────────

ORDER_COLS = (
    "o.id, o.organisation_id, o.campaign_id, o.placed_by_player_id, o.contact_name, o.contact_email, o.contact_phone, "
    "o.reference, o.status, o.source, o.notes, o.payment_requested_at, o.due_on, o.unpaid_decision, o.unpaid_note, "
    "o.packed_at, o.collected_at, o.cancelled_reason, o.created_at, o.updated_at"
)
LINE_COLS = (
    "id, order_id, product_id, variant_id, product_name, supplier_code, size_label, unit_price, qty, wearer_player_id, "
    "wearer_name, personal_number, personal_text, number_status, number_note, state, cut_by_triage, club_covered, "
    "covered_reason, from_stock, issued_at, created_at"
)


def line_charge(l: dict) -> Decimal:
    if l["state"] != "active" or l["club_covered"]:
        return Decimal(0)
    return (Decimal(str(l["unit_price"])) * int(l["qty"])).quantize(CENT)


async def _lines_for(db: AsyncSession, order_ids: list) -> dict:
    if not order_ids:
        return {}
    rows = (await db.execute(text(
        f"SELECT {LINE_COLS} FROM teamwear_order_lines WHERE order_id = ANY(CAST(:ids AS UUID[])) ORDER BY created_at, id"),
        {"ids": [str(i) for i in order_ids]})).mappings().all()
    out: dict = {}
    for r in rows:
        out.setdefault(r["order_id"], []).append(dict(r))
    return out


async def _paid_for(db: AsyncSession, order_ids: list) -> dict:
    if not order_ids:
        return {}
    rows = (await db.execute(text(
        "SELECT order_id, SUM(amount) AS paid FROM teamwear_payments WHERE voided_at IS NULL "
        "AND order_id = ANY(CAST(:ids AS UUID[])) GROUP BY order_id"),
        {"ids": [str(i) for i in order_ids]})).mappings().all()
    return {r["order_id"]: Decimal(str(r["paid"] or 0)).quantize(CENT) for r in rows}


def line_out(l: dict) -> dict:
    return {
        "id": str(l["id"]), "product_id": str(l["product_id"]) if l["product_id"] else None,
        "variant_id": str(l["variant_id"]) if l["variant_id"] else None,
        "product_name": l["product_name"], "supplier_code": l["supplier_code"], "size": l["size_label"],
        "unit_price": f2(l["unit_price"]), "qty": l["qty"],
        "wearer_player_id": str(l["wearer_player_id"]) if l["wearer_player_id"] else None,
        "wearer_name": l["wearer_name"], "number": l["personal_number"], "text": l["personal_text"],
        "number_status": l["number_status"], "number_note": l["number_note"],
        "state": l["state"], "cut_by_triage": l["cut_by_triage"],
        "club_covered": l["club_covered"], "covered_reason": l["covered_reason"],
        "from_stock": l["from_stock"], "issued_at": iso(l["issued_at"]),
        "charge": f2(line_charge(l)),
    }


def order_phase(o: dict, c: Optional[dict]) -> str:
    """Where the order is, read from the order and its campaign.

    editable: the member can still change it. waiting: ordering closed, triage under way.
    payment: asked to pay; changes by request. locked: gone to the supplier.
    """
    if o["status"] == "cancelled":
        return "cancelled"
    if o["collected_at"]:
        return "collected"
    if c is None:
        return "payment"
    if c["stage"] in ("exported", "received", "closed"):
        return "locked"
    if o["payment_requested_at"]:
        return "payment"
    if ordering_open(c):
        return "editable"
    return "waiting"


def order_out(o: dict, lines: list, paid: Decimal, campaign: Optional[dict] = None) -> dict:
    total = sum((line_charge(l) for l in lines), Decimal(0)).quantize(CENT)
    balance = (total - paid).quantize(CENT)
    return {
        "id": str(o["id"]), "campaign_id": str(o["campaign_id"]) if o["campaign_id"] else None,
        "campaign_name": campaign["name"] if campaign else None,
        "placed_by_player_id": str(o["placed_by_player_id"]) if o["placed_by_player_id"] else None,
        "contact_name": o["contact_name"], "contact_email": o["contact_email"], "contact_phone": o["contact_phone"],
        "reference": o["reference"], "status": o["status"], "source": o["source"], "notes": o["notes"],
        "payment_requested_at": iso(o["payment_requested_at"]), "due_on": iso(o["due_on"]),
        "unpaid_decision": o["unpaid_decision"], "unpaid_note": o["unpaid_note"],
        "packed_at": iso(o["packed_at"]), "collected_at": iso(o["collected_at"]),
        "cancelled_reason": o["cancelled_reason"], "created_at": iso(o["created_at"]),
        "phase": order_phase(o, campaign),
        "lines": [line_out(l) for l in lines],
        "units": sum(int(l["qty"]) for l in lines if l["state"] == "active"),
        "total": f2(total), "paid": f2(paid), "balance": f2(balance),
        "overdue": bool(o["due_on"] and balance > 0 and o["due_on"] < today_local() and o["status"] != "cancelled"),
    }


async def load_orders(db: AsyncSession, org_id, *, campaign_id=None, order_ids=None, placed_by=None,
                      stock_only: bool = False) -> list[dict]:
    q = f"SELECT {ORDER_COLS} FROM teamwear_orders o WHERE o.organisation_id = CAST(:o AS UUID)"
    params: dict = {"o": str(org_id)}
    if campaign_id is not None:
        q += " AND o.campaign_id = CAST(:c AS UUID)"
        params["c"] = str(campaign_id)
    if stock_only:
        q += " AND o.campaign_id IS NULL"
    if order_ids is not None:
        q += " AND o.id = ANY(CAST(:ids AS UUID[]))"
        params["ids"] = [str(i) for i in order_ids]
    if placed_by is not None:
        q += " AND o.placed_by_player_id = CAST(:pb AS UUID)"
        params["pb"] = str(placed_by)
    q += " ORDER BY o.created_at"
    rows = [dict(r) for r in (await db.execute(text(q), params)).mappings().all()]
    ids = [r["id"] for r in rows]
    lines = await _lines_for(db, ids)
    paid = await _paid_for(db, ids)
    camps: dict = {}
    for cid in {r["campaign_id"] for r in rows if r["campaign_id"]}:
        camps[cid] = await get_campaign(db, org_id, cid)
    return [order_out(r, lines.get(r["id"], []), paid.get(r["id"], Decimal(0)), camps.get(r["campaign_id"])) for r in rows]


async def get_order(db: AsyncSession, org_id, order_id) -> dict:
    rows = await load_orders(db, org_id, order_ids=[_uuid(order_id, "order id")])
    if not rows:
        raise TeamwearError("Order not found", 404)
    return rows[0]


async def _order_row(db: AsyncSession, org_id, order_id) -> dict:
    r = (await db.execute(text(
        f"SELECT {ORDER_COLS} FROM teamwear_orders o WHERE o.id = CAST(:i AS UUID) AND o.organisation_id = CAST(:o AS UUID)"),
        {"i": str(_uuid(order_id, "order id")), "o": str(org_id)})).mappings().first()
    if not r:
        raise TeamwearError("Order not found", 404)
    return dict(r)


async def next_reference(db: AsyncSession, org_id, campaign_id, contact_name: str, suffix: str,
                         exclude_order=None) -> str:
    """SURNAME TEAMWEAR, made unique in the campaign (SMITH2 TEAMWEAR for a second Smith family)."""
    base = surname_of(contact_name)
    taken = set((await db.execute(text(
        "SELECT reference FROM teamwear_orders WHERE organisation_id = CAST(:o AS UUID) "
        "AND campaign_id IS NOT DISTINCT FROM CAST(:c AS UUID) AND status <> 'cancelled' "
        "AND id IS DISTINCT FROM CAST(:x AS UUID)"),
        {"o": str(org_id), "c": str(campaign_id) if campaign_id else None,
         "x": str(exclude_order) if exclude_order else None})).scalars().all())
    taken_keys = {ref_key(t) for t in taken}
    n = 1
    while True:
        cand = f"{base}{'' if n == 1 else n} {suffix}".strip()
        if ref_key(cand) not in taken_keys:
            return cand
        n += 1


# Who may be named as a wearer from a member's page: themselves and their family.

async def family_of(db: AsyncSession, org_id, player_id) -> list[dict]:
    """The player and everyone in a family with them (players only: a non-player is a typed name)."""
    rows = (await db.execute(text(
        "SELECT DISTINCT p.id, p.name, p.display_name_override, p.shirt_number FROM players p "
        "WHERE p.organisation_id = CAST(:o AS UUID) AND (p.id = CAST(:me AS UUID) OR p.id IN ("
        "  SELECT fm2.player_id FROM family_members fm1 JOIN family_members fm2 ON fm2.family_id = fm1.family_id "
        "  JOIN families f ON f.id = fm1.family_id "
        "  WHERE fm1.player_id = CAST(:me AS UUID) AND f.organisation_id = CAST(:o AS UUID) AND fm2.player_id IS NOT NULL))"),
        {"o": str(org_id), "me": str(player_id)})).mappings().all()
    out = []
    for r in rows:
        out.append({"player_id": str(r["id"]), "name": r["display_name_override"] or r["name"],
                    "shirt_number": r["shirt_number"], "me": str(r["id"]) == str(player_id)})
    out.sort(key=lambda x: (not x["me"], x["name"] or ""))
    return out


async def number_check(db: AsyncSession, org_id, number: Optional[str], wearer_player_id=None,
                       campaign_id=None, exclude_line_ids: Iterable = ()) -> dict:
    """Check a requested shirt number against the club's register (``players.shirt_number``) and
    against the other numbers asked for in the same campaign. Warns; never refuses."""
    num = clean_shirt_number(number)
    if not num:
        return {"status": None, "note": None}
    holders = (await db.execute(text(
        "SELECT id, COALESCE(display_name_override, name) AS name FROM players "
        "WHERE organisation_id = CAST(:o AS UUID) AND shirt_number = :n AND COALESCE(status, 'active') = 'active' "
        "AND id IS DISTINCT FROM CAST(:w AS UUID) ORDER BY name LIMIT 3"),
        {"o": str(org_id), "n": num, "w": str(wearer_player_id) if wearer_player_id else None})).mappings().all()
    if holders:
        return {"status": "clash", "note": f"#{num} is held by {', '.join(h['name'] for h in holders)} on the club register."}
    if wearer_player_id:
        own = (await db.execute(text("SELECT shirt_number FROM players WHERE id = CAST(:w AS UUID)"),
                                {"w": str(wearer_player_id)})).scalar()
        if own and own != num:
            return {"status": "clash", "note": f"The club register has #{own} for this player."}
    if campaign_id:
        others = (await db.execute(text(
            "SELECT DISTINCT COALESCE(l.wearer_name, '') FROM teamwear_order_lines l "
            "JOIN teamwear_orders o ON o.id = l.order_id WHERE o.campaign_id = CAST(:c AS UUID) "
            "AND o.status <> 'cancelled' AND l.state = 'active' AND l.personal_number = :n "
            "AND l.wearer_player_id IS DISTINCT FROM CAST(:w AS UUID) AND NOT (l.id = ANY(CAST(:ex AS UUID[])))"),
            {"c": str(campaign_id), "n": num, "w": str(wearer_player_id) if wearer_player_id else None,
             "ex": [str(x) for x in exclude_line_ids]})).scalars().all()
        others = [o for o in others if o]
        if others:
            return {"status": "clash", "note": f"#{num} is also asked for by {', '.join(others[:3])} this round."}
    if wearer_player_id:
        own = (await db.execute(text("SELECT shirt_number FROM players WHERE id = CAST(:w AS UUID)"),
                                {"w": str(wearer_player_id)})).scalar()
        if own == num:
            return {"status": "ok", "note": None}
    return {"status": "new", "note": f"#{num} is free on the club register."}


async def _build_lines(db: AsyncSession, org_id, campaign: Optional[dict], raw_lines: list,
                       allowed_wearers: Optional[dict], existing_ids: Iterable = ()) -> list[dict]:
    """Validate the lines a member or the coordinator sent and expand them (a personalised garment
    becomes one line per unit). ``allowed_wearers`` None means any club player may be named (the
    coordinator); otherwise only those ids."""
    if not raw_lines:
        raise TeamwearError("Add at least one item.")
    if len(raw_lines) > MAX_LINES:
        raise TeamwearError("That is too many lines for one order.")
    if campaign is not None:
        items = {str(i["product_id"]): i for i in await campaign_items(db, campaign["id"])}
        rng = {r["product_id"]: r for r in await list_range(db, org_id, product_ids=list(items.keys()))}
    else:
        rng = {r["product_id"]: r for r in await list_range(db, org_id, only_shop=True)}
        items = None
    out: list[dict] = []
    stock_need: dict = {}
    for raw in raw_lines:
        pid = str(_uuid(raw.get("product_id"), "product id"))
        prod = rng.get(pid)
        if prod is None or (items is not None and pid not in items):
            raise TeamwearError("One of those items is not on offer.")
        if items is None and prod["made_to_order"]:
            raise TeamwearError(f"{prod['name']} is made to order and can only be ordered in a campaign.")
        vid = str(_uuid(raw.get("variant_id"), "size"))
        size = next((s for s in prod["sizes"] if s["variant_id"] == vid), None)
        if size is None:
            raise TeamwearError(f"Pick a size for {prod['name']}.")
        try:
            qty = int(raw.get("qty") or 1)
        except (TypeError, ValueError):
            raise TeamwearError("Quantity must be a whole number.")
        if qty < 1 or qty > MAX_QTY:
            raise TeamwearError(f"Quantity for {prod['name']} must be between 1 and {MAX_QTY}.")
        wearer_id = raw.get("wearer_player_id") or None
        wearer_name = (re.sub(r"\s+", " ", str(raw.get("wearer_name") or "")).strip() or None)
        if wearer_id:
            wearer_id = str(_uuid(wearer_id, "wearer"))
            if allowed_wearers is not None:
                if wearer_id not in allowed_wearers:
                    raise TeamwearError("You can order for yourself and your family. Type any other name instead.")
                wearer_name = allowed_wearers[wearer_id]
            else:
                pl = (await db.execute(text(
                    "SELECT COALESCE(display_name_override, name) FROM players WHERE id = CAST(:p AS UUID) "
                    "AND organisation_id = CAST(:o AS UUID)"), {"p": wearer_id, "o": str(org_id)})).scalar()
                if pl is None:
                    raise TeamwearError("That wearer is not one of the club's players.")
                wearer_name = pl
        if not wearer_name:
            raise TeamwearError(f"Say who the {prod['name']} is for.")
        pers = prod["personalisation"]
        number = clean_shirt_number(raw.get("number")) if pers != "none" else None
        ptext = caps(raw.get("text")) if pers != "none" else None
        if pers == "number_initials" and ptext:
            ptext = re.sub(r"[^A-Z]", "", ptext) or None
        unit_price = Decimal(str(items[pid]["price"] if items is not None else prod["price"])).quantize(CENT)
        if items is None:
            stock_need[vid] = stock_need.get(vid, 0) + qty
            if stock_need[vid] > size["available"]:
                raise TeamwearError(f"Only {size['available']} of {prod['name']} ({size['label']}) left in stock.")
        base = {
            "product_id": pid, "variant_id": vid, "product_name": prod["name"], "supplier_code": prod["supplier_code"],
            "size_label": size["label"], "unit_price": unit_price, "wearer_player_id": wearer_id,
            "wearer_name": wearer_name, "personal_number": number, "personal_text": ptext,
            "from_stock": items is None,
        }
        if pers != "none":
            for _ in range(qty):
                out.append({**base, "qty": 1})
        else:
            out.append({**base, "qty": qty})
    for l in out:
        chk = await number_check(db, org_id, l["personal_number"], l["wearer_player_id"],
                                 campaign["id"] if campaign else None, exclude_line_ids=existing_ids)
        l["number_status"], l["number_note"] = chk["status"], chk["note"]
    return out


async def _insert_lines(db: AsyncSession, order_id, lines: list[dict]) -> None:
    for l in lines:
        await db.execute(text(
            "INSERT INTO teamwear_order_lines (order_id, product_id, variant_id, product_name, supplier_code, size_label, "
            "unit_price, qty, wearer_player_id, wearer_name, personal_number, personal_text, number_status, number_note, "
            "from_stock, created_at) VALUES (CAST(:o AS UUID), CAST(:p AS UUID), CAST(:v AS UUID), :pn, :code, :size, :price, "
            ":qty, CAST(:w AS UUID), :wn, :num, :txt, :ns, :nn, :fs, clock_timestamp())"),
            {"o": str(order_id), "p": l["product_id"], "v": l["variant_id"], "pn": l["product_name"],
             "code": l["supplier_code"], "size": l["size_label"], "price": l["unit_price"], "qty": l["qty"],
             "w": l["wearer_player_id"], "wn": l["wearer_name"], "num": l["personal_number"],
             "txt": l["personal_text"], "ns": l["number_status"], "nn": l["number_note"], "fs": l["from_stock"]})


def _clean_contact(data: dict, fallback: dict) -> tuple[str, Optional[str], Optional[str]]:
    name = (re.sub(r"\s+", " ", str(data.get("contact_name") or fallback.get("name") or "")).strip())
    email = (str(data.get("contact_email") or fallback.get("email") or "").strip() or None)
    phone = (str(data.get("contact_phone") or fallback.get("phone") or "").strip() or None)
    if not name:
        raise TeamwearError("Give a contact name for the order.")
    if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise TeamwearError("That email address does not look right.")
    if not email:
        raise TeamwearError("Give an email address so the club can send the payment details.")
    return name, email, phone


async def place_order(db: AsyncSession, club: Organisation, *, campaign_id, lines: list, data: dict,
                      placed_by: Optional[Player] = None, allowed_wearers: Optional[dict] = None,
                      user_id=None) -> str:
    """A new order, from a member's page (``placed_by``) or entered by the coordinator (``user_id``).
    A campaign order waits for triage; a shop order of in-stock items is asked to pay straight away."""
    s = await get_settings(db, club.id)
    campaign = None
    if campaign_id:
        campaign = await get_campaign(db, club.id, campaign_id)
        if placed_by is not None and not ordering_open(campaign):
            raise TeamwearError("Ordering for this campaign is closed.", 409)
        if placed_by is None and campaign["stage"] not in ("draft", "open", "triage"):
            raise TeamwearError("The plan is confirmed. Add to an existing order through a change instead.", 409)
    built = await _build_lines(db, club.id, campaign, lines, allowed_wearers)
    fallback = {}
    if placed_by is not None:
        fallback = {"name": placed_by.display_name, "email": placed_by.email, "phone": placed_by.phone}
    name, email, phone = _clean_contact(data, fallback)
    ref = await next_reference(db, club.id, campaign["id"] if campaign else None, name, s["reference_suffix"])
    oid = uuid.uuid4()
    stock = campaign is None
    await db.execute(text(
        "INSERT INTO teamwear_orders (id, organisation_id, campaign_id, placed_by_player_id, contact_name, contact_email, "
        "contact_phone, reference, status, source, notes, payment_requested_at, due_on, created_by) VALUES ("
        "CAST(:id AS UUID), CAST(:o AS UUID), CAST(:c AS UUID), CAST(:pb AS UUID), :n, :e, :ph, :ref, :st, :src, :notes, "
        ":pr, :due, CAST(:u AS UUID))"),
        {"id": str(oid), "o": str(club.id), "c": str(campaign["id"]) if campaign else None,
         "pb": str(placed_by.id) if placed_by is not None else None, "n": name, "e": email, "ph": phone,
         "ref": ref, "st": "confirmed" if stock else "submitted", "src": "member" if placed_by is not None else "coordinator",
         "notes": (data.get("notes") or None), "pr": now_utc() if stock else None,
         "due": today_local() + timedelta(days=int(s["pay_days"] or 14)) if stock else None,
         "u": str(user_id) if user_id else None})
    await _insert_lines(db, oid, built)
    return str(oid)


async def replace_member_lines(db: AsyncSession, club: Organisation, order_id, *, lines: list, data: dict,
                               player: Player, allowed_wearers: dict) -> None:
    """The member edits their order while ordering is open: the lines are replaced whole."""
    o = await _order_row(db, club.id, order_id)
    if str(o["placed_by_player_id"]) != str(player.id):
        raise TeamwearError("Order not found", 404)
    c = await get_campaign(db, club.id, o["campaign_id"]) if o["campaign_id"] else None
    if c is None or order_phase(o, c) != "editable":
        raise TeamwearError("This order can no longer be changed here. Ask for a change instead.", 409)
    existing = [r for r in (await db.execute(text(
        "SELECT id FROM teamwear_order_lines WHERE order_id = CAST(:o AS UUID)"), {"o": str(o["id"])})).scalars().all()]
    built = await _build_lines(db, club.id, c, lines, allowed_wearers, existing_ids=existing)
    s = await get_settings(db, club.id)
    name, email, phone = _clean_contact(data, {"name": o["contact_name"], "email": o["contact_email"], "phone": o["contact_phone"]})
    ref = o["reference"]
    if surname_of(name) != surname_of(o["contact_name"]):
        ref = await next_reference(db, club.id, c["id"], name, s["reference_suffix"], exclude_order=o["id"])
    await db.execute(text("DELETE FROM teamwear_order_lines WHERE order_id = CAST(:o AS UUID)"), {"o": str(o["id"])})
    await _insert_lines(db, o["id"], built)
    await db.execute(text(
        "UPDATE teamwear_orders SET contact_name = :n, contact_email = :e, contact_phone = :ph, reference = :ref, "
        "notes = :notes, updated_at = NOW() WHERE id = CAST(:o AS UUID)"),
        {"n": name, "e": email, "ph": phone, "ref": ref, "notes": data.get("notes") if "notes" in data else o["notes"],
         "o": str(o["id"])})


async def member_cancel(db: AsyncSession, club: Organisation, order_id, player: Player) -> None:
    o = await _order_row(db, club.id, order_id)
    if str(o["placed_by_player_id"]) != str(player.id):
        raise TeamwearError("Order not found", 404)
    c = await get_campaign(db, club.id, o["campaign_id"]) if o["campaign_id"] else None
    if c is None:
        paid = (await _paid_for(db, [o["id"]])).get(o["id"], Decimal(0))
        if paid > 0 or o["collected_at"]:
            raise TeamwearError("This order has been paid. Ask the club to cancel it.", 409)
    elif order_phase(o, c) != "editable":
        raise TeamwearError("Ordering has closed. Ask the club for a change instead.", 409)
    await db.execute(text(
        "UPDATE teamwear_orders SET status = 'cancelled', cancelled_reason = 'Cancelled by the member', "
        "updated_at = NOW() WHERE id = CAST(:o AS UUID)"), {"o": str(o["id"])})


# ── coordinator edits on an order ───────────────────────────────────────────

async def _editable_by_coordinator(db: AsyncSession, org_id, o: dict) -> Optional[dict]:
    c = await get_campaign(db, org_id, o["campaign_id"]) if o["campaign_id"] else None
    if c is not None and c["stage"] in ("exported", "received", "closed", "cancelled"):
        raise TeamwearError("This order has gone to the supplier and is locked.", 409)
    if o["status"] == "cancelled":
        raise TeamwearError("This order is cancelled.", 409)
    return c


async def coordinator_add_lines(db: AsyncSession, club: Organisation, order_id, lines: list) -> None:
    o = await _order_row(db, club.id, order_id)
    c = await _editable_by_coordinator(db, club.id, o)
    existing = (await db.execute(text(
        "SELECT id FROM teamwear_order_lines WHERE order_id = CAST(:o AS UUID)"), {"o": str(o["id"])})).scalars().all()
    built = await _build_lines(db, club.id, c, lines, None, existing_ids=existing)
    if c is not None:
        cut = {str(i["product_id"]) for i in await campaign_items(db, c["id"]) if i["decision"] == "cut" and c["approved_on"]}
        if any(l["product_id"] in cut for l in built):
            raise TeamwearError("That product was cut this round.", 409)
    await _insert_lines(db, o["id"], built)


async def update_line(db: AsyncSession, club: Organisation, line_id, data: dict, user_id=None) -> dict:
    """The coordinator changes a line: size, number, name text, cover it for the club, remove it,
    or approve a flagged number (which writes the number back to the player's record)."""
    l = (await db.execute(text(
        f"SELECT {LINE_COLS} FROM teamwear_order_lines WHERE id = CAST(:i AS UUID)"),
        {"i": str(_uuid(line_id, "line id"))})).mappings().first()
    if not l:
        raise TeamwearError("Line not found", 404)
    l = dict(l)
    o = await _order_row(db, club.id, l["order_id"])
    c = await _editable_by_coordinator(db, club.id, o)
    sets, params = [], {"i": str(l["id"])}
    wrote_back = None
    if "variant_id" in data:
        vid = str(_uuid(data["variant_id"], "size"))
        v = (await db.execute(text(
            "SELECT id, COALESCE(size, label) AS label FROM merch_variants WHERE id = CAST(:v AS UUID) "
            "AND product_id = CAST(:p AS UUID) AND is_active"), {"v": vid, "p": str(l["product_id"])})).mappings().first()
        if not v:
            raise TeamwearError("That size is not offered for this product.")
        sets += ["variant_id = CAST(:v AS UUID)", "size_label = :sl"]
        params.update(v=vid, sl=v["label"])
    if "qty" in data:
        try:
            q = int(data["qty"])
        except (TypeError, ValueError):
            raise TeamwearError("Quantity must be a whole number.")
        if q < 1 or q > MAX_QTY:
            raise TeamwearError("Quantity is out of range.")
        if l["personal_number"] or l["personal_text"]:
            q = 1
        sets.append("qty = :q")
        params["q"] = q
    if "text" in data:
        sets.append("personal_text = :t")
        params["t"] = caps(data.get("text"))
    if "wearer_name" in data:
        wn = re.sub(r"\s+", " ", str(data.get("wearer_name") or "")).strip()
        if not wn:
            raise TeamwearError("Say who the item is for.")
        sets.append("wearer_name = :wn")
        params["wn"] = wn
    if "number" in data:
        num = clean_shirt_number(data.get("number"))
        chk = await number_check(db, club.id, num, l["wearer_player_id"], c["id"] if c else None, exclude_line_ids=[l["id"]])
        sets += ["personal_number = :n", "number_status = :ns", "number_note = :nn"]
        params.update(n=num, ns=chk["status"], nn=chk["note"])
    if data.get("approve_number"):
        num = params.get("n", l["personal_number"])
        if not num:
            raise TeamwearError("There is no number to approve.")
        sets += ["number_status = 'approved'", "number_note = NULL"]
        sets = [s for s in sets if not s.startswith("number_status = :") and not s.startswith("number_note = :")]
        params.pop("ns", None)
        params.pop("nn", None)
        if l["wearer_player_id"]:
            before = (await db.execute(text("SELECT shirt_number FROM players WHERE id = CAST(:p AS UUID)"),
                                       {"p": str(l["wearer_player_id"])})).scalar()
            if before != num:
                await db.execute(text("UPDATE players SET shirt_number = :n WHERE id = CAST(:p AS UUID)"),
                                 {"n": num, "p": str(l["wearer_player_id"])})
                wrote_back = {"player_id": str(l["wearer_player_id"]), "from": before, "to": num}
    if "club_covered" in data:
        cov = bool(data.get("club_covered"))
        reason = (str(data.get("covered_reason") or "").strip() or None)
        if cov and not reason:
            raise TeamwearError("Give a reason the club is covering this item.")
        sets += ["club_covered = :cov", "covered_reason = :cr"]
        params.update(cov=cov, cr=reason if cov else None)
    if "removed" in data:
        if data.get("removed"):
            sets.append("state = 'removed'")
        elif l["state"] == "removed":
            sets.append("state = 'active'")
    if not sets:
        return line_out(l)
    await db.execute(text(
        f"UPDATE teamwear_order_lines SET {', '.join(sets)}, updated_at = NOW() WHERE id = CAST(:i AS UUID)"), params)
    if wrote_back:
        from app.services.audit_log import log_activity
        await log_activity(db, org_id=club.id, user_id=user_id, action="teamwear_number_approved",
                           target_type="player", target_id=wrote_back["player_id"], details=wrote_back)
    r = (await db.execute(text(f"SELECT {LINE_COLS} FROM teamwear_order_lines WHERE id = CAST(:i AS UUID)"),
                          {"i": str(l["id"])})).mappings().first()
    return line_out(dict(r))


async def update_order(db: AsyncSession, club: Organisation, order_id, data: dict, user_id=None) -> None:
    """Coordinator edits on the order itself: contact details, notes, the unpaid decision, cancel,
    packed and collected."""
    o = await _order_row(db, club.id, order_id)
    sets, params = [], {"o": str(o["id"])}
    for k in ("contact_name", "contact_email", "contact_phone", "notes"):
        if k in data:
            v = (str(data.get(k) or "").strip() or None)
            if k == "contact_name" and not v:
                raise TeamwearError("Give a contact name.")
            sets.append(f"{k} = :{k}")
            params[k] = v
    if "due_on" in data:
        sets.append("due_on = :due")
        params["due"] = _parse_date(data.get("due_on"))
    if "unpaid_decision" in data:
        v = data.get("unpaid_decision") or None
        if v is not None and v not in UNPAID_DECISIONS:
            raise TeamwearError("Unknown decision.")
        sets += ["unpaid_decision = :ud", "unpaid_note = :un"]
        params.update(ud=v, un=(str(data.get("unpaid_note") or "").strip() or None) if v else None)
    if data.get("cancel"):
        c = await get_campaign(db, club.id, o["campaign_id"]) if o["campaign_id"] else None
        if c is not None and c["stage"] in ("exported", "received", "closed"):
            raise TeamwearError("This order has gone to the supplier and cannot be cancelled.", 409)
        reason = (str(data.get("cancelled_reason") or "").strip() or "Cancelled by the club")
        sets += ["status = 'cancelled'", "cancelled_reason = :cr"]
        params["cr"] = reason
    if data.get("restore") and o["status"] == "cancelled":
        c = await get_campaign(db, club.id, o["campaign_id"]) if o["campaign_id"] else None
        if c is not None and c["stage"] in ("exported", "received", "closed", "cancelled"):
            raise TeamwearError("This campaign has moved on; the order cannot come back.", 409)
        sets += ["status = :rs", "cancelled_reason = NULL"]
        params["rs"] = "confirmed" if o["payment_requested_at"] else "submitted"
    if "packed" in data:
        sets.append("packed_at = :pk")
        params["pk"] = now_utc() if data.get("packed") else None
    if "collected" in data:
        sets.append("collected_at = :col")
        params["col"] = now_utc() if data.get("collected") else None
    if sets:
        await db.execute(text(
            f"UPDATE teamwear_orders SET {', '.join(sets)}, updated_at = NOW() WHERE id = CAST(:o AS UUID)"), params)
    if data.get("collected") and o["campaign_id"] is None:
        await issue_stock_lines(db, club, o["id"], user_id)


async def issue_stock_lines(db: AsyncSession, club: Organisation, order_id, user_id=None) -> int:
    """A shop order of in-stock items is handed over: each line leaves club stock as a sale."""
    rows = (await db.execute(text(
        f"SELECT {LINE_COLS} FROM teamwear_order_lines WHERE order_id = CAST(:o AS UUID) AND from_stock "
        "AND state = 'active' AND issued_at IS NULL"), {"o": str(order_id)})).mappings().all()
    o = await _order_row(db, club.id, order_id)
    n = 0
    for l in rows:
        if not l["variant_id"]:
            continue
        v = await db.get(MerchVariant, l["variant_id"])
        if v is None:
            continue
        merch_service.record_movement(
            db, v, kind="sold", delta=-int(l["qty"]), unit_price=Decimal(str(l["unit_price"])),
            player_id=l["wearer_player_id"], amount=line_charge(dict(l)), paid=True,
            note=f"Teamwear shop order {o['reference']}", occurred_on=today_local(),
            created_by_user_id=user_id, source="teamwear", external_ref=f"teamwear:{l['id']}")
        await db.execute(text("UPDATE teamwear_order_lines SET issued_at = NOW() WHERE id = CAST(:i AS UUID)"),
                         {"i": str(l["id"])})
        n += 1
    await db.flush()
    return n


# ── change requests ─────────────────────────────────────────────────────────

async def request_change(db: AsyncSession, club: Organisation, order_id, player: Player, message: str) -> str:
    o = await _order_row(db, club.id, order_id)
    if str(o["placed_by_player_id"]) != str(player.id):
        raise TeamwearError("Order not found", 404)
    c = await get_campaign(db, club.id, o["campaign_id"]) if o["campaign_id"] else None
    phase = order_phase(o, c)
    if phase not in ("waiting", "payment"):
        raise TeamwearError("Changes can be asked for after ordering closes and until the order goes to the supplier.", 409)
    msg = (message or "").strip()
    if not msg:
        raise TeamwearError("Say what you would like changed.")
    rid = uuid.uuid4()
    await db.execute(text(
        "INSERT INTO teamwear_change_requests (id, organisation_id, order_id, requested_by_player_id, message) "
        "VALUES (CAST(:id AS UUID), CAST(:o AS UUID), CAST(:ord AS UUID), CAST(:p AS UUID), :m)"),
        {"id": str(rid), "o": str(club.id), "ord": str(o["id"]), "p": str(player.id), "m": msg[:2000]})
    return str(rid)


async def list_changes(db: AsyncSession, org_id, *, campaign_id=None, order_ids=None) -> list[dict]:
    q = ("SELECT r.id, r.order_id, r.message, r.status, r.response, r.created_at, r.resolved_at, o.contact_name, "
         "o.reference FROM teamwear_change_requests r JOIN teamwear_orders o ON o.id = r.order_id "
         "WHERE r.organisation_id = CAST(:o AS UUID)")
    params: dict = {"o": str(org_id)}
    if campaign_id is not None:
        q += " AND o.campaign_id = CAST(:c AS UUID)"
        params["c"] = str(campaign_id)
    if order_ids is not None:
        q += " AND r.order_id = ANY(CAST(:ids AS UUID[]))"
        params["ids"] = [str(i) for i in order_ids]
    q += " ORDER BY r.created_at DESC"
    return [{
        "id": str(r["id"]), "order_id": str(r["order_id"]), "message": r["message"], "status": r["status"],
        "response": r["response"], "created_at": iso(r["created_at"]), "resolved_at": iso(r["resolved_at"]),
        "contact_name": r["contact_name"], "reference": r["reference"],
    } for r in (await db.execute(text(q), params)).mappings().all()]


async def resolve_change(db: AsyncSession, org_id, request_id, status: str, response: Optional[str], user_id=None) -> dict:
    if status not in ("done", "declined"):
        raise TeamwearError("A change is done or declined.")
    r = (await db.execute(text(
        "UPDATE teamwear_change_requests SET status = :s, response = :resp, resolved_by = CAST(:u AS UUID), "
        "resolved_at = NOW() WHERE id = CAST(:i AS UUID) AND organisation_id = CAST(:o AS UUID) RETURNING order_id"),
        {"s": status, "resp": (response or "").strip() or None, "u": str(user_id) if user_id else None,
         "i": str(_uuid(request_id)), "o": str(org_id)})).first()
    if not r:
        raise TeamwearError("Change request not found", 404)
    return {"order_id": str(r[0])}


# ── triage ──────────────────────────────────────────────────────────────────

async def triage(db: AsyncSession, org_id, campaign_id) -> dict:
    """The live triage table: for each product, member units by size, top-ups by size, the minimum,
    the shortfall and whether it is a Suggested cut. Read fresh every time."""
    c = await get_campaign(db, org_id, campaign_id)
    s = await get_settings(db, org_id)
    default_moq = c["moq"] if c["moq"] is not None else int(s["default_moq"] or 10)
    ratio = int(s["cut_ratio"] or 9)
    items = await campaign_items(db, c["id"])
    pids = [i["product_id"] for i in items]
    variants = await _variants_for(db, pids)
    demand = {(r["product_id"], r["variant_id"]): int(r["n"] or 0) for r in (await db.execute(text(
        "SELECT l.product_id, l.variant_id, SUM(l.qty) AS n FROM teamwear_order_lines l "
        "JOIN teamwear_orders o ON o.id = l.order_id WHERE o.campaign_id = CAST(:c AS UUID) AND o.status <> 'cancelled' "
        "AND (l.state = 'active' OR (l.state = 'cut' AND l.cut_by_triage)) GROUP BY l.product_id, l.variant_id"),
        {"c": str(c["id"])})).mappings().all()}
    orders_by = {r["product_id"]: int(r["n"]) for r in (await db.execute(text(
        "SELECT l.product_id, COUNT(DISTINCT o.id) AS n FROM teamwear_order_lines l JOIN teamwear_orders o ON o.id = l.order_id "
        "WHERE o.campaign_id = CAST(:c AS UUID) AND o.status <> 'cancelled' "
        "AND (l.state = 'active' OR (l.state = 'cut' AND l.cut_by_triage)) GROUP BY l.product_id"),
        {"c": str(c["id"])})).mappings().all()}
    tops = {r["variant_id"]: int(r["qty"]) for r in (await db.execute(text(
        "SELECT variant_id, qty FROM teamwear_topups WHERE campaign_id = CAST(:c AS UUID)"),
        {"c": str(c["id"])})).mappings().all()}
    rows = []
    totals = {"member_units": 0, "topup_units": 0, "included_units": 0, "value": Decimal(0)}
    for i in items:
        moq = i["moq"] if i["moq"] is not None else default_moq
        sizes = []
        m_total = t_total = 0
        for v in variants.get(i["product_id"], []):
            m = demand.get((i["product_id"], v["id"]), 0)
            t = tops.get(v["id"], 0)
            if not v["is_active"] and not m and not t:
                continue
            sizes.append({"variant_id": str(v["id"]), "label": v["size"] or v["label"], "member": m, "topup": t})
            m_total += m
            t_total += t
        needed = max(0, moq - m_total)
        shortfall = max(0, moq - m_total - t_total)
        suggested_cut = m_total == 0 or (needed > 0 and needed >= ratio * m_total)
        rows.append({
            "product_id": str(i["product_id"]), "name": i["name"], "supplier_code": i["supplier_code"],
            "personalisation": i["personalisation"], "price": f2(i["price"]), "decision": i["decision"],
            "decision_note": i["decision_note"], "moq": moq, "member_units": m_total, "topup_units": t_total,
            "total_units": m_total + t_total, "orders": orders_by.get(i["product_id"], 0),
            "needed_topups": needed, "shortfall": shortfall,
            "ratio": f"1:{round(needed / m_total, 1) if m_total else '∞'}" if needed else None,
            "suggested_cut": suggested_cut, "sizes": sizes,
        })
        totals["member_units"] += m_total
        totals["topup_units"] += t_total
        if i["decision"] == "include":
            totals["included_units"] += m_total + t_total
            totals["value"] += Decimal(str(i["price"])) * m_total
    plan = plan_fingerprint(rows)
    return {
        "campaign": campaign_out(c, settings=s), "items": rows, "cut_ratio": ratio, "default_moq": default_moq,
        "totals": {**totals, "value": f2(totals["value"])},
        "holds": [r["name"] for r in rows if r["decision"] == "hold" and r["member_units"] > 0],
        "below_minimum": [r["name"] for r in rows if r["decision"] == "include" and r["shortfall"] > 0],
        "approval_current": bool(c["approved_on"]) and c["approved_plan"] == plan,
        "plan": plan,
    }


def plan_fingerprint(rows: list[dict]) -> str:
    """What the committee approved: every product's decision and the top-ups by size."""
    parts = []
    for r in sorted(rows, key=lambda x: x["product_id"]):
        tops = ",".join(f"{s['variant_id']}={s['topup']}" for s in sorted(r["sizes"], key=lambda s: s["variant_id"]) if s["topup"])
        parts.append(f"{r['product_id']}:{r['decision']}:{tops}")
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:24]


def _require_triage(c: dict) -> None:
    if c["stage"] != "triage":
        if c["stage"] == "open":
            raise TeamwearError("Close ordering before triage.", 409)
        raise TeamwearError("The plan is confirmed and payment requests have gone. It can no longer change.", 409)


async def _clear_approval(db: AsyncSession, c: dict) -> None:
    """A changed plan is not the plan the committee approved: clear it and put back what it cut."""
    if not c["approved_on"]:
        return
    await db.execute(text(
        "UPDATE teamwear_campaigns SET approved_on = NULL, approval_note = NULL, approval_recorded_by = NULL, "
        "approval_recorded_at = NULL, approved_plan = NULL, updated_at = NOW() WHERE id = CAST(:c AS UUID)"),
        {"c": str(c["id"])})
    await db.execute(text(
        "UPDATE teamwear_order_lines l SET state = 'active', cut_by_triage = false, updated_at = NOW() "
        "FROM teamwear_orders o WHERE o.id = l.order_id AND o.campaign_id = CAST(:c AS UUID) AND l.cut_by_triage"),
        {"c": str(c["id"])})
    c["approved_on"] = None


async def set_decision(db: AsyncSession, org_id, campaign_id, product_id, decision: str, note=None) -> bool:
    if decision not in DECISIONS:
        raise TeamwearError("A decision is include, cut or hold.")
    c = await get_campaign(db, org_id, campaign_id)
    _require_triage(c)
    r = await db.execute(text(
        "UPDATE teamwear_campaign_items SET decision = :d, decision_note = :n WHERE campaign_id = CAST(:c AS UUID) "
        "AND product_id = CAST(:p AS UUID) AND (decision <> :d OR decision_note IS DISTINCT FROM :n)"),
        {"d": decision, "n": (note or None), "c": str(c["id"]), "p": str(_uuid(product_id))})
    cleared = False
    if r.rowcount:
        cleared = bool(c["approved_on"])
        await _clear_approval(db, c)
    return cleared


async def set_topups(db: AsyncSession, org_id, campaign_id, product_id, by_variant: dict) -> bool:
    c = await get_campaign(db, org_id, campaign_id)
    _require_triage(c)
    pid = str(_uuid(product_id))
    valid = {str(v["id"]) for v in (await _variants_for(db, [pid])).get(uuid.UUID(pid), [])}
    changed = False
    for vid, qty in (by_variant or {}).items():
        if vid not in valid:
            raise TeamwearError("That size is not offered for this product.")
        try:
            q = max(0, int(qty or 0))
        except (TypeError, ValueError):
            raise TeamwearError("Top-ups must be whole numbers.")
        before = (await db.execute(text(
            "SELECT qty FROM teamwear_topups WHERE campaign_id = CAST(:c AS UUID) AND variant_id = CAST(:v AS UUID)"),
            {"c": str(c["id"]), "v": vid})).scalar() or 0
        if before == q:
            continue
        changed = True
        if q == 0:
            await db.execute(text(
                "DELETE FROM teamwear_topups WHERE campaign_id = CAST(:c AS UUID) AND variant_id = CAST(:v AS UUID)"),
                {"c": str(c["id"]), "v": vid})
        else:
            await db.execute(text(
                "INSERT INTO teamwear_topups (campaign_id, variant_id, product_id, qty) VALUES (CAST(:c AS UUID), "
                "CAST(:v AS UUID), CAST(:p AS UUID), :q) ON CONFLICT (campaign_id, variant_id) DO UPDATE SET qty = EXCLUDED.qty"),
                {"c": str(c["id"]), "v": vid, "p": pid, "q": q})
    cleared = False
    if changed:
        cleared = bool(c["approved_on"])
        await _clear_approval(db, c)
    return cleared


def suggest_topups(sizes: list[dict], needed: int) -> dict:
    """Spread the units needed to reach the minimum over the sizes members ordered most, one at a
    time to the size with the most demand per unit already added. Sizes nobody ordered get none
    unless nobody ordered anything."""
    if needed <= 0 or not sizes:
        return {}
    pool = [s for s in sizes if s["member"] > 0] or sizes
    add = {s["variant_id"]: 0 for s in pool}
    for _ in range(needed):
        best = max(pool, key=lambda s: ((s["member"] or 1) / (1 + s["topup"] + add[s["variant_id"]]), -pool.index(s)))
        add[best["variant_id"]] += 1
    return {s["variant_id"]: s["topup"] + add[s["variant_id"]] for s in pool if add[s["variant_id"]]}


async def apply_suggested_topups(db: AsyncSession, org_id, campaign_id, product_id) -> bool:
    t = await triage(db, org_id, campaign_id)
    row = next((r for r in t["items"] if r["product_id"] == str(_uuid(product_id))), None)
    if row is None:
        raise TeamwearError("Product not in this campaign", 404)
    plan = suggest_topups(row["sizes"], row["shortfall"])
    if not plan:
        return False
    return await set_topups(db, org_id, campaign_id, product_id, plan)


async def record_approval(db: AsyncSession, org_id, campaign_id, approved_on, note: Optional[str], user_id=None) -> dict:
    """The coordinator records the committee's sign-off of the whole plan. Every product someone
    ordered must be included or cut (nothing on hold). Recording it cuts the lines of cut products
    in every order; a product with no orders left on hold is simply not ordered."""
    c = await get_campaign(db, org_id, campaign_id)
    _require_triage(c)
    t = await triage(db, org_id, c["id"])
    if t["holds"]:
        raise TeamwearError(f"Decide include or cut for {', '.join(t['holds'])} first.", 409)
    if not any(r["decision"] == "include" for r in t["items"]):
        raise TeamwearError("Nothing is included. Cancel the campaign instead.", 409)
    d = _parse_date(approved_on) or today_local()
    cut_ids = [r["product_id"] for r in t["items"] if r["decision"] != "include"]
    await db.execute(text(
        "UPDATE teamwear_order_lines l SET state = 'cut', cut_by_triage = true, updated_at = NOW() "
        "FROM teamwear_orders o WHERE o.id = l.order_id AND o.campaign_id = CAST(:c AS UUID) "
        "AND l.state = 'active' AND l.product_id = ANY(CAST(:ids AS UUID[]))"),
        {"c": str(c["id"]), "ids": cut_ids})
    await db.execute(text(
        "UPDATE teamwear_campaigns SET approved_on = :d, approval_note = :n, approval_recorded_by = CAST(:u AS UUID), "
        "approval_recorded_at = NOW(), approved_plan = :plan, updated_at = NOW() WHERE id = CAST(:c AS UUID)"),
        {"d": d, "n": (note or "").strip() or None, "u": str(user_id) if user_id else None, "plan": t["plan"],
         "c": str(c["id"])})
    from app.services.audit_log import log_activity
    await log_activity(db, org_id=org_id, user_id=user_id, action="teamwear_plan_approved",
                       target_type="teamwear_campaign", target_id=str(c["id"]),
                       details={"approved_on": d.isoformat(), "note": note, "cut": cut_ids,
                                "below_minimum": t["below_minimum"]})
    return {"below_minimum": t["below_minimum"]}


async def revoke_approval(db: AsyncSession, org_id, campaign_id, user_id=None) -> None:
    c = await get_campaign(db, org_id, campaign_id)
    _require_triage(c)
    await _clear_approval(db, c)


async def payment_request_targets(db: AsyncSession, org_id, campaign_id) -> list[dict]:
    """Orders that will be asked to pay, and the ones left with nothing after the cuts."""
    return [o for o in await load_orders(db, org_id, campaign_id=campaign_id) if o["status"] != "cancelled"]


async def confirm_and_request_payment(db: AsyncSession, org_id, campaign_id, user_id=None) -> dict:
    """Move an approved plan to payment: every order with lines left is confirmed with a due date;
    an order left with nothing is closed with the reason. Emails are sent by the caller after commit."""
    c = await get_campaign(db, org_id, campaign_id)
    _require_triage(c)
    t = await triage(db, org_id, c["id"])
    if not t["approval_current"]:
        raise TeamwearError("Record the committee's approval of this plan first.", 409)
    s = await get_settings(db, org_id)
    due = c["pay_due_on"] or (today_local() + timedelta(days=int(s["pay_days"] or 14)))
    asked, emptied = [], []
    for o in await payment_request_targets(db, org_id, c["id"]):
        if o["units"] == 0:
            await db.execute(text(
                "UPDATE teamwear_orders SET status = 'cancelled', cancelled_reason = 'Nothing in this order is being made this round', "
                "updated_at = NOW() WHERE id = CAST(:o AS UUID)"), {"o": o["id"]})
            emptied.append(o["id"])
        else:
            await db.execute(text(
                "UPDATE teamwear_orders SET status = 'confirmed', payment_requested_at = NOW(), due_on = :due, "
                "updated_at = NOW() WHERE id = CAST(:o AS UUID)"), {"o": o["id"], "due": due})
            asked.append(o["id"])
    await set_stage(db, c["id"], "payment", payment_requested_at=now_utc(), pay_due_on=due)
    return {"asked": asked, "emptied": emptied, "due_on": due.isoformat()}


# ── payments ────────────────────────────────────────────────────────────────

async def record_payment(db: AsyncSession, org_id, order_id, *, amount, method: str = "bank", paid_on=None,
                         reference: Optional[str] = None, note: Optional[str] = None, source: str = "manual",
                         external_ref: Optional[str] = None, user_id=None) -> Optional[str]:
    """One payment against an order. With an ``external_ref`` already recorded, nothing is added
    (a bank row imported twice, a webhook delivered twice) and None comes back."""
    o = await _order_row(db, org_id, order_id)
    amt = money(amount)
    if amt is None or amt == 0:
        raise TeamwearError("Enter the amount paid.")
    if method not in PAYMENT_METHODS:
        raise TeamwearError("Method is bank, card, cash or other.")
    if external_ref:
        dup = (await db.execute(text(
            "SELECT 1 FROM teamwear_payments WHERE organisation_id = CAST(:o AS UUID) AND external_ref = :x "
            "AND voided_at IS NULL"), {"o": str(org_id), "x": external_ref})).first()
        if dup:
            return None
    pid = uuid.uuid4()
    await db.execute(text(
        "INSERT INTO teamwear_payments (id, organisation_id, order_id, amount, method, source, paid_on, reference, "
        "external_ref, note, recorded_by) VALUES (CAST(:id AS UUID), CAST(:o AS UUID), CAST(:ord AS UUID), :a, :m, :src, "
        ":d, :ref, :x, :n, CAST(:u AS UUID))"),
        {"id": str(pid), "o": str(org_id), "ord": str(o["id"]), "a": amt, "m": method, "src": source,
         "d": _parse_date(paid_on) or today_local(), "ref": reference, "x": external_ref, "n": note,
         "u": str(user_id) if user_id else None})
    return str(pid)


async def void_payment(db: AsyncSession, org_id, payment_id, reason: Optional[str], user_id=None) -> None:
    r = await db.execute(text(
        "UPDATE teamwear_payments SET voided_at = NOW(), void_reason = :r WHERE id = CAST(:i AS UUID) "
        "AND organisation_id = CAST(:o AS UUID) AND voided_at IS NULL"),
        {"r": (reason or "").strip() or None, "i": str(_uuid(payment_id)), "o": str(org_id)})
    if not r.rowcount:
        raise TeamwearError("Payment not found", 404)
    from app.services.audit_log import log_activity
    await log_activity(db, org_id=org_id, user_id=user_id, action="teamwear_payment_voided",
                       target_type="teamwear_payment", target_id=str(payment_id), details={"reason": reason})


async def list_payments(db: AsyncSession, org_id, *, campaign_id=None, order_id=None) -> list[dict]:
    q = ("SELECT p.id, p.order_id, p.amount, p.method, p.source, p.paid_on, p.reference, p.note, p.voided_at, "
         "p.void_reason, p.created_at, o.contact_name, o.reference AS order_ref FROM teamwear_payments p "
         "JOIN teamwear_orders o ON o.id = p.order_id WHERE p.organisation_id = CAST(:o AS UUID)")
    params: dict = {"o": str(org_id)}
    if campaign_id is not None:
        q += " AND o.campaign_id = CAST(:c AS UUID)"
        params["c"] = str(campaign_id)
    if order_id is not None:
        q += " AND p.order_id = CAST(:ord AS UUID)"
        params["ord"] = str(order_id)
    q += " ORDER BY p.paid_on DESC, p.created_at DESC"
    return [{
        "id": str(r["id"]), "order_id": str(r["order_id"]), "amount": f2(r["amount"]), "method": r["method"],
        "source": r["source"], "paid_on": iso(r["paid_on"]), "reference": r["reference"], "note": r["note"],
        "voided": r["voided_at"] is not None, "void_reason": r["void_reason"], "created_at": iso(r["created_at"]),
        "contact_name": r["contact_name"], "order_reference": r["order_ref"],
    } for r in (await db.execute(text(q), params)).mappings().all()]


# ── export readiness, receive and pack ──────────────────────────────────────

async def export_blockers(db: AsyncSession, org_id, campaign_id) -> dict:
    c = await get_campaign(db, org_id, campaign_id)
    orders = [o for o in await load_orders(db, org_id, campaign_id=c["id"]) if o["status"] != "cancelled"]
    unpaid = [o for o in orders if o["balance"] > 0 and o["unpaid_decision"] != "proceed"]
    open_changes = [r for r in await list_changes(db, org_id, campaign_id=c["id"]) if r["status"] == "open"]
    return {
        "stage": c["stage"],
        "unpaid": [{"id": o["id"], "contact_name": o["contact_name"], "reference": o["reference"],
                    "balance": o["balance"]} for o in unpaid],
        "open_changes": len(open_changes),
        "ready": c["stage"] == "payment" and not unpaid,
    }


async def mark_exported(db: AsyncSession, org_id, campaign_id, user_id=None) -> None:
    b = await export_blockers(db, org_id, campaign_id)
    if b["stage"] != "payment":
        raise TeamwearError("Payment requests have to go before the order can be exported.", 409)
    if b["unpaid"]:
        names = ", ".join(u["contact_name"] for u in b["unpaid"][:5])
        raise TeamwearError(f"{len(b['unpaid'])} orders are unpaid ({names}). Record their payments, or decide each one.", 409)
    await set_stage(db, campaign_id, "exported", exported_at=now_utc(), exported_by=str(user_id) if user_id else None)


async def mark_received(db: AsyncSession, club: Organisation, campaign_id, user_id=None) -> int:
    """The kit has arrived: top-ups go into club stock (once each)."""
    c = await get_campaign(db, club.id, campaign_id)
    if c["stage"] != "exported":
        raise TeamwearError("Export the order first.", 409)
    rows = (await db.execute(text(
        "SELECT t.variant_id, t.qty FROM teamwear_topups t JOIN teamwear_campaign_items i "
        "ON i.campaign_id = t.campaign_id AND i.product_id = t.product_id "
        "WHERE t.campaign_id = CAST(:c AS UUID) AND t.qty > 0 AND t.received_to_stock_at IS NULL AND i.decision = 'include'"),
        {"c": str(c["id"])})).mappings().all()
    n = 0
    for r in rows:
        v = await db.get(MerchVariant, r["variant_id"])
        if v is None:
            continue
        merch_service.record_movement(
            db, v, kind="received", delta=int(r["qty"]), note=f"Teamwear top-up: {c['name']}",
            occurred_on=today_local(), created_by_user_id=user_id, source="teamwear",
            external_ref=f"teamwear-topup:{c['id']}:{v.id}")
        await db.execute(text(
            "UPDATE teamwear_topups SET received_to_stock_at = NOW() WHERE campaign_id = CAST(:c AS UUID) "
            "AND variant_id = CAST(:v AS UUID)"), {"c": str(c["id"]), "v": str(v.id)})
        n += int(r["qty"])
    await db.flush()
    await set_stage(db, c["id"], "received", received_at=now_utc())
    return n


# ── member-facing view ──────────────────────────────────────────────────────

async def shop_for_member(db: AsyncSession, club: Organisation, player: Player) -> dict:
    s = await get_settings(db, club.id)
    camps = []
    rows = (await db.execute(text(
        f"SELECT {CAMPAIGN_COLS} FROM teamwear_campaigns WHERE organisation_id = CAST(:o AS UUID) AND stage = 'open' "
        "ORDER BY closes_at NULLS LAST"), {"o": str(club.id)})).mappings().all()
    for r in rows:
        c = dict(r)
        if not ordering_open(c):
            continue
        items = await campaign_items(db, c["id"])
        rng = {x["product_id"]: x for x in await list_range(db, club.id, product_ids=[i["product_id"] for i in items])}
        products = []
        for i in items:
            p = rng.get(str(i["product_id"]))
            if not p:
                continue
            products.append({**{k: p[k] for k in ("product_id", "name", "description", "supplier_code", "personalisation",
                                                  "personal_label", "images")},
                             "price": f2(i["price"]), "sizes": [{"variant_id": z["variant_id"], "label": z["label"]} for z in p["sizes"]]})
        camps.append({"id": str(c["id"]), "name": c["name"], "intro": c["intro"], "closes_at": iso(c["closes_at"]),
                      "products": products})
    stock = []
    for p in await list_range(db, club.id, only_shop=True):
        if p["made_to_order"] or p["price"] is None:
            continue
        sizes = [{"variant_id": z["variant_id"], "label": z["label"], "available": z["available"]} for z in p["sizes"] if z["available"] > 0]
        if not sizes:
            continue
        stock.append({**{k: p[k] for k in ("product_id", "name", "description", "personalisation", "personal_label",
                                           "images", "price")}, "sizes": sizes})
    orders = await load_orders(db, club.id, placed_by=player.id)
    changes = await list_changes(db, club.id, order_ids=[o["id"] for o in orders]) if orders else []
    for o in orders:
        o["changes"] = [ch for ch in changes if ch["order_id"] == o["id"]]
    return {
        "campaigns": camps, "stock": stock, "orders": list(reversed(orders)),
        "family": await family_of(db, club.id, player.id),
        "contact": {"name": player.display_name, "email": player.email, "phone": player.phone},
        "bank": {"account_name": s["bank_account_name"], "bsb": s["bank_bsb"], "account_number": s["bank_account_number"]}
        if s["bank_bsb"] and s["bank_account_number"] else None,
        "coordinator": {"name": s["coordinator_name"], "email": s["coordinator_email"]},
    }


async def dashboard_summary(db: AsyncSession, club: Organisation, player: Player) -> Optional[dict]:
    """What the Player Dashboard card says: an open campaign, what this person owes. None when
    there is nothing to show (no open campaign, no in-stock kit, no order)."""
    open_c = (await db.execute(text(
        f"SELECT {CAMPAIGN_COLS} FROM teamwear_campaigns WHERE organisation_id = CAST(:o AS UUID) AND stage = 'open' "
        "ORDER BY closes_at NULLS LAST"), {"o": str(club.id)})).mappings().all()
    live = [dict(c) for c in open_c if ordering_open(dict(c))]
    orders = [o for o in await load_orders(db, club.id, placed_by=player.id) if o["status"] != "cancelled"]
    stock = (await db.execute(text(
        "SELECT COUNT(*) FROM teamwear_products t JOIN merch_products p ON p.id = t.product_id "
        "JOIN merch_variants v ON v.product_id = p.id WHERE t.organisation_id = CAST(:o AS UUID) AND t.in_shop "
        "AND NOT t.made_to_order AND p.is_active AND v.is_active AND v.quantity > 0"), {"o": str(club.id)})).scalar() or 0
    if not live and not orders and not stock:
        return None
    owing = sum(Decimal(str(o["balance"])) for o in orders if o["payment_requested_at"] and o["balance"] > 0)
    return {
        "open": [{"name": c["name"], "closes_at": iso(c["closes_at"])} for c in live],
        "orders": len(orders), "owing": f2(owing), "stock": bool(stock),
        "active": [{"reference": o["reference"], "phase": o["phase"], "balance": o["balance"],
                    "campaign_name": o["campaign_name"]} for o in orders if o["phase"] not in ("collected",)][:3],
    }


# ── bank CSV matching ───────────────────────────────────────────────────────

_DATE_HEADERS = ("date", "transaction date", "posted date", "processed date")
_AMOUNT_HEADERS = ("amount", "credit", "credit amount", "deposit", "value")
_DEBIT_HEADERS = ("debit", "withdrawal", "debit amount")
_DESC_HEADERS = ("description", "narrative", "details", "transaction", "reference", "memo")
_DATE_RE = re.compile(r"^\s*(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\s*$|^\s*(\d{4})-(\d{2})-(\d{2})")


def _detect_col(headers, candidates):
    lower = [str(h or "").strip().lower() for h in headers]
    for i, h in enumerate(lower):
        if h in candidates:
            return i
    for i, h in enumerate(lower):
        if any(c in h for c in candidates):
            return i
    return None


def _bank_date(raw: str) -> Optional[date]:
    m = _DATE_RE.match(raw or "")
    if not m:
        return None
    try:
        if m.group(4):
            return date(int(m.group(4)), int(m.group(5)), int(m.group(6)))
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        return date(y, mo, d)  # Australian banks write day first
    except ValueError:
        return None


def _amount(raw: str) -> Optional[Decimal]:
    s = (raw or "").strip().replace(",", "").replace("$", "")
    if not s:
        return None
    try:
        return Decimal(s).quantize(CENT)
    except InvalidOperation:
        return None


def parse_bank_csv(raw: str) -> list[dict]:
    """Credits from a bank statement CSV: [{row, date, amount, description, key}]. Works with a
    header row (NAB, ANZ, Westpac) or without one (CommBank: date, amount, description, balance).
    Debits are dropped. ``key`` identifies the row so importing the same file twice records nothing new."""
    import csv
    import io
    rows = [r for r in csv.reader(io.StringIO(raw or "")) if r and any((c or "").strip() for c in r)]
    if not rows:
        raise TeamwearError("That file is empty.")
    header_idx = None
    for i, r in enumerate(rows[:10]):
        if _detect_col(r, _DATE_HEADERS) is not None and _detect_col(r, _DESC_HEADERS) is not None:
            header_idx = i
            break
    out = []
    if header_idx is not None:
        h = rows[header_idx]
        dc, sc = _detect_col(h, _DATE_HEADERS), _detect_col(h, _DESC_HEADERS)
        ac, bc = _detect_col(h, _AMOUNT_HEADERS), _detect_col(h, _DEBIT_HEADERS)
        if ac is None:
            raise TeamwearError("Could not find an amount or credit column.")
        body = rows[header_idx + 1:]
    else:
        # Headerless: the first cell is a date, then the first number is the amount, the first text the description.
        if _bank_date(rows[0][0]) is None:
            raise TeamwearError("Could not find the date and description columns in that file.")
        dc, ac, sc, bc = 0, 1, 2, None
        body = rows
    for n, r in enumerate(body):
        def cell(i):
            return (r[i] if i is not None and i < len(r) else "") or ""
        amt = _amount(cell(ac))
        if amt is None or amt <= 0:
            continue
        if bc is not None and cell(bc).strip() and _amount(cell(bc)):
            continue
        d = _bank_date(cell(dc))
        desc = cell(sc).strip()
        key = hashlib.sha1(f"{cell(dc).strip()}|{amt}|{desc}|{n if not desc else ''}".encode()).hexdigest()[:20]
        out.append({"row": n, "date": d, "amount": amt, "description": desc, "key": f"bank:{key}"})
    return out


async def bank_preview(db: AsyncSession, org_id, raw: str, campaign_id=None) -> dict:
    """Propose an order for each credit. A row carrying an order's reference (SMITH TEAMWEAR, spacing
    and case ignored) is a sure match; otherwise the contact's name and the amount owing suggest one."""
    from app.services.fees import clean_description, match_score
    credits = parse_bank_csv(raw)
    orders = [o for o in await load_orders(db, org_id, campaign_id=campaign_id)
              if o["status"] != "cancelled" and o["payment_requested_at"]]
    done = set((await db.execute(text(
        "SELECT external_ref FROM teamwear_payments WHERE organisation_id = CAST(:o AS UUID) AND external_ref LIKE 'bank:%' "
        "AND voided_at IS NULL"), {"o": str(org_id)})).scalars().all())
    by_ref = {ref_key(o["reference"]): o for o in orders}
    out = []
    for cr in credits:
        if cr["key"] in done:
            out.append({**_cr_out(cr), "status": "already_imported", "suggestions": []})
            continue
        dk = ref_key(cr["description"])
        sure = next((o for k, o in by_ref.items() if k and k in dk), None)
        sugg = []
        if sure:
            sugg = [{"order_id": sure["id"], "reference": sure["reference"], "contact_name": sure["contact_name"],
                     "balance": sure["balance"], "confidence": 1.0, "why": "reference"}]
        else:
            cleaned = clean_description(cr["description"])
            scored = []
            for o in orders:
                sc = match_score(cleaned, o["contact_name"])
                if o["balance"] > 0 and abs(Decimal(str(o["balance"])) - cr["amount"]) < Decimal("0.01"):
                    sc = min(1.0, sc + 0.25)
                if sc > 0.35:
                    scored.append((sc, o))
            scored.sort(key=lambda x: -x[0])
            sugg = [{"order_id": o["id"], "reference": o["reference"], "contact_name": o["contact_name"],
                     "balance": o["balance"], "confidence": round(sc, 2), "why": "name"} for sc, o in scored[:3]]
        out.append({**_cr_out(cr), "status": "matched" if sure else ("suggested" if sugg else "unmatched"),
                    "suggestions": sugg})
    return {"rows": out}


def _cr_out(cr: dict) -> dict:
    return {"key": cr["key"], "date": iso(cr["date"]), "amount": f2(cr["amount"]), "description": cr["description"]}


async def bank_commit(db: AsyncSession, org_id, rows: list[dict], user_id=None) -> dict:
    """Record the rows the coordinator confirmed: [{key, order_id, amount, date, description}]."""
    recorded = skipped = 0
    for r in rows:
        if not r.get("order_id") or not str(r.get("key") or "").startswith("bank:"):
            continue
        pid = await record_payment(db, org_id, r["order_id"], amount=r.get("amount"), method="bank",
                                   paid_on=r.get("date"), reference=(r.get("description") or "")[:200],
                                   source="bank_csv", external_ref=r["key"], user_id=user_id)
        if pid:
            recorded += 1
        else:
            skipped += 1
    return {"recorded": recorded, "skipped": skipped}
