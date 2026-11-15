"""BetterMerch insights: the numbers behind the stock dashboard and the exports.

Everything here is read-only and derived on read. Stock lives on a variant as a
running `quantity`; every change writes a `merch_movements` row. So history is
not stored, it is walked back from today's balance:

    balance at the end of day D  =  quantity now  -  sum(delta of movements after D)

A variant did not exist before it was created, so it counts as nothing before
that date. That is also why a freshly entered stocktake shows a flat, short
history: the opening count was typed in, it is not a movement, and the chart
says so rather than inventing a past.

Sales are `sold` movements (hand-entered, Square, and paid online-store orders
all land there). `issued` (kit given to a player) is shown beside them but is
not counted as selling, and `used` / `write_off` are shown as stock lost.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import (
    MerchCategory, MerchMovement, MerchProduct, MerchVariant, Player,
)
from app.services import merch as merch_service

# Kinds that count as demand, supply and loss on the charts.
SOLD = "sold"
ISSUED = "issued"
RECEIVED = "received"
LOST_KINDS = ("used", "write_off")

# A product with this many weeks of stock left at its recent selling rate is
# flagged as running low, even when it is above its reorder point.
RUNNING_LOW_WEEKS = 4.0
# A product has to have been on the books this long before "no sales" means
# anything. Entered this afternoon, it has had no chance to sell.
NOT_SELLING_MIN_AGE_DAYS = 30
# The selling rate never divides by less than a week, so one sale in the first
# hour does not read as a rate of seven a day.
MIN_RATE_DAYS = 7

ALLOWED_WINDOWS = (30, 90, 180, 365)

_SIZE_ORDER = ["XXXS", "XXS", "XS", "S", "M", "L", "XL", "XXL", "2XL", "3XL", "XXXL", "4XL", "5XL", "6XL", "7XL"]


def clamp_days(days) -> int:
    """The window is one of a few fixed spans; anything else snaps to 90."""
    try:
        d = int(days)
    except (TypeError, ValueError):
        return 90
    return d if d in ALLOWED_WINDOWS else 90


def eff(variant_value, product_value):
    """A variant's own cost or price, else its product's."""
    return variant_value if variant_value is not None else product_value


def _f(x) -> float | None:
    return float(x) if x is not None else None


def _movement_date_expr():
    """The business date of a movement: the typed date, else the day it was made."""
    return func.coalesce(MerchMovement.occurred_on, func.date(MerchMovement.created_at))


def size_sort_key(label: str):
    """Letter sizes in wearing order, then numbers (kids sizes) ascending, then the rest."""
    s = (label or "").strip().upper().replace(" ", "")
    if s in _SIZE_ORDER:
        return (0, _SIZE_ORDER.index(s), s)
    m = re.match(r"^(\d+(?:\.\d+)?)", s)
    if m:
        return (1, float(m.group(1)), s)
    return (2, 0, s)


def _norm_size(raw) -> str | None:
    s = (raw or "").strip()
    return s.upper() if s else None


def _norm_colour(raw) -> str | None:
    s = (raw or "").strip()
    return s.title() if s else None


def _bucket_plan(days: int) -> tuple[int, int]:
    """(step in days, bucket count). Daily for a month, weekly beyond. Buckets
    are counted back from today, so the last one ends today and the first is
    cut short at the window start when the window is not a whole number of weeks."""
    step = 1 if days <= 31 else 7
    return step, int(math.ceil(days / step))


async def stock_dashboard(session: AsyncSession, org_id, *, days: int = 90, today: date | None = None) -> dict:
    days = clamp_days(days)
    today = today or date.today()
    window_start = today - timedelta(days=days - 1)
    step, n_buckets = _bucket_plan(days)

    # ── Current stock: every active variant of an active product ─────────────
    vq = (
        select(MerchVariant, MerchProduct, MerchCategory.name)
        .join(MerchProduct, MerchProduct.id == MerchVariant.product_id)
        .outerjoin(MerchCategory, MerchCategory.id == MerchProduct.category_id)
        .where(
            MerchVariant.organisation_id == org_id,
            MerchVariant.is_active.is_(True),
            MerchProduct.is_active.is_(True),
        )
        .order_by(MerchProduct.category, MerchProduct.name, MerchVariant.label)
    )
    vrows = (await session.execute(vq)).all()

    # ── Movements inside the window, for every variant (inactive ones too: a
    # product retired last month still sold well last month). ────────────────
    date_expr = _movement_date_expr().label("d")
    mq = (
        select(
            MerchMovement.variant_id, MerchMovement.kind, MerchMovement.delta,
            MerchMovement.amount, MerchMovement.unit_price, MerchMovement.source,
            date_expr,
            MerchProduct.id, MerchProduct.name, MerchProduct.category, MerchProduct.is_active,
            MerchProduct.unit_cost, MerchVariant.unit_cost, MerchVariant.size, MerchVariant.colour,
        )
        .join(MerchVariant, MerchVariant.id == MerchMovement.variant_id)
        .join(MerchProduct, MerchProduct.id == MerchVariant.product_id)
        .where(MerchMovement.organisation_id == org_id, _movement_date_expr() >= window_start)
    )
    mrows = (await session.execute(mq)).all()

    last_sold_rows = (await session.execute(
        select(MerchMovement.variant_id, func.max(_movement_date_expr()))
        .where(MerchMovement.organisation_id == org_id, MerchMovement.kind == SOLD)
        .group_by(MerchMovement.variant_id)
    )).all()
    last_sold_by_variant = {vid: d for vid, d in last_sold_rows}

    # ── Per-variant and per-product accumulators ─────────────────────────────
    products: dict = {}
    variant_index: dict = {}
    for v, p, cat_name in vrows:
        cost = eff(v.unit_cost, p.unit_cost)
        price = eff(v.unit_price, p.unit_price)
        qty = int(v.quantity or 0)
        thr = merch_service.variant_threshold(v, p)
        created = _as_date(v.created_at)
        rec = products.get(p.id)
        if rec is None:
            rec = products[p.id] = {
                "product_id": str(p.id), "name": p.name, "category": p.category,
                "category_name": cat_name, "for_resale": bool(p.for_resale), "supplier": p.supplier,
                "created": _as_date(p.created_at), "variants": [],
                "on_hand": 0, "value_cost": 0.0, "value_retail": 0.0,
                "sold": 0, "issued": 0, "received": 0, "lost": 0, "revenue": 0.0,
                "last_sold": None, "low": False, "out_variants": 0,
            }
        vd = {
            "variant_id": str(v.id), "label": v.label, "size": v.size, "colour": v.colour, "sku": v.sku,
            "quantity": qty, "eff_cost": _f(cost), "eff_price": _f(price), "threshold": thr,
            "low_stock": merch_service.is_low_stock(v, p), "sold": 0, "issued": 0,
            "last_sold": last_sold_by_variant.get(v.id),
        }
        rec["variants"].append(vd)
        rec["on_hand"] += qty
        if cost is not None:
            rec["value_cost"] += qty * float(cost)
        if price is not None:
            rec["value_retail"] += qty * float(price)
        rec["low"] = rec["low"] or vd["low_stock"]
        if qty <= 0:
            rec["out_variants"] += 1
        ls = vd["last_sold"]
        if ls and (rec["last_sold"] is None or ls > rec["last_sold"]):
            rec["last_sold"] = ls
        variant_index[v.id] = {
            "qty": qty, "cost": _f(cost), "created": created, "pid": p.id, "vd": vd,
            "size": _norm_size(v.size), "colour": _norm_colour(v.colour), "category": p.category,
        }

    # ── Walk the movements ───────────────────────────────────────────────────
    zero_bucket = lambda: {"sold": 0, "issued": 0, "received": 0, "lost": 0, "revenue": 0.0}  # noqa: E731
    buckets = [zero_bucket() for _ in range(n_buckets)]
    delta_by_variant_bucket: dict = defaultdict(lambda: defaultdict(int))
    sold_units = issued_units = received_units = lost_units = 0
    revenue = cogs = revenue_costed = 0.0
    unpriced_sold_units = 0
    by_source: dict = defaultdict(lambda: {"units": 0, "revenue": 0.0})
    by_type_sales: dict = defaultdict(lambda: {"units": 0, "revenue": 0.0})
    # Sales of retired products: reported in the totals, named in a bucket of their own.
    retired_sales: dict = {}
    size_sold: dict = defaultdict(int)
    colour_sold: dict = defaultdict(int)

    for (vid, kind, delta, amount, unit_price, source, d, pid, pname, pcat, p_active,
         p_cost, v_cost, m_size, m_colour) in mrows:
        d = _as_date(d)
        if d is None:
            continue
        if d < window_start:
            continue
        idx = max(n_buckets - 1 - (today - d).days // step, 0) if d <= today else n_buckets - 1
        delta = int(delta or 0)
        delta_by_variant_bucket[vid][idx] += delta
        units = abs(delta)
        b = buckets[idx]
        if kind == SOLD:
            sold_units += units
            b["sold"] += units
            rev = float(amount) if amount is not None else (float(unit_price) * units if unit_price is not None else None)
            if rev is None:
                unpriced_sold_units += units
                rev = 0.0
            revenue += rev
            b["revenue"] += rev
            src = source or "manual"
            by_source[src]["units"] += units
            by_source[src]["revenue"] += rev
            by_type_sales[pcat]["units"] += units
            by_type_sales[pcat]["revenue"] += rev
            cost = eff(v_cost, p_cost)
            if cost is not None and (amount is not None or unit_price is not None):
                cogs += units * float(cost)
                revenue_costed += rev
            vi = variant_index.get(vid)
            if vi is not None:
                prod = products[vi["pid"]]
                prod["sold"] += units
                prod["revenue"] += rev
                vi["vd"]["sold"] += units
                if prod["category"] == "apparel":
                    if vi["size"]:
                        size_sold[vi["size"]] += units
                    if vi["colour"]:
                        colour_sold[vi["colour"]] += units
            else:
                r = retired_sales.setdefault(pid, {"name": pname, "category": pcat, "units": 0, "revenue": 0.0})
                r["units"] += units
                r["revenue"] += rev
        elif kind == ISSUED:
            issued_units += units
            b["issued"] += units
            vi = variant_index.get(vid)
            if vi is not None:
                products[vi["pid"]]["issued"] += units
                vi["vd"]["issued"] += units
        elif kind == RECEIVED:
            received_units += units
            b["received"] += units
            vi = variant_index.get(vid)
            if vi is not None:
                products[vi["pid"]]["received"] += units
        elif kind in LOST_KINDS:
            lost_units += units
            b["lost"] += units
            vi = variant_index.get(vid)
            if vi is not None:
                products[vi["pid"]]["lost"] += units

    # ── Stock over time: walk each variant's balance back from today ─────────
    ends = [today - timedelta(days=step * (n_buckets - 1 - i)) for i in range(n_buckets)]
    units_series = [0] * n_buckets
    value_series = [0.0] * n_buckets
    tracked_from: date | None = None
    for vid, vi in variant_index.items():
        bal = vi["qty"]
        per = delta_by_variant_bucket.get(vid, {})
        created = vi["created"]
        if tracked_from is None or (created and created < tracked_from):
            tracked_from = created
        for i in range(n_buckets - 1, -1, -1):
            # `bal` is the balance at the end of bucket i
            if created is None or created <= ends[i]:
                units_series[i] += bal
                if vi["cost"] is not None:
                    value_series[i] += bal * vi["cost"]
            bal -= per.get(i, 0)

    series = []
    for i, b in enumerate(buckets):
        series.append({
            "start": max(ends[i] - timedelta(days=step - 1), window_start).isoformat(),
            "end": ends[i].isoformat(),
            "sold": b["sold"], "issued": b["issued"], "received": b["received"], "lost": b["lost"],
            "revenue": round(b["revenue"], 2),
            "stock_units": units_series[i],
            "stock_value_cost": round(value_series[i], 2),
        })

    # ── Product status, selling rate, weeks of cover ─────────────────────────
    weeks_in_window = days / 7.0
    prod_out = []
    for rec in products.values():
        age_days = (today - rec["created"]).days if rec["created"] else None
        basis_days = max(MIN_RATE_DAYS, min(days, (age_days or 0) + 1))
        per_week = rec["sold"] / (basis_days / 7.0) if rec["sold"] else 0.0
        cover = (rec["on_hand"] / per_week) if per_week > 0 and rec["on_hand"] > 0 else None
        if rec["on_hand"] <= 0:
            status = "out"
        elif rec["low"]:
            status = "low"
        elif cover is not None and cover < RUNNING_LOW_WEEKS:
            status = "running_low"
        elif (rec["for_resale"] and rec["sold"] == 0 and age_days is not None
              and age_days >= NOT_SELLING_MIN_AGE_DAYS):
            status = "not_selling"
        else:
            status = "ok"
        prod_out.append({
            "product_id": rec["product_id"], "name": rec["name"], "category": rec["category"],
            "category_name": rec["category_name"], "for_resale": rec["for_resale"],
            "supplier": rec["supplier"],
            "on_hand": rec["on_hand"], "variant_count": len(rec["variants"]),
            "out_variants": rec["out_variants"],
            "value_cost": round(rec["value_cost"], 2), "value_retail": round(rec["value_retail"], 2),
            "sold": rec["sold"], "issued": rec["issued"], "received": rec["received"], "lost": rec["lost"],
            "revenue": round(rec["revenue"], 2),
            "per_week": round(per_week, 2),
            "weeks_cover": round(cover, 1) if cover is not None else None,
            "last_sold": rec["last_sold"].isoformat() if rec["last_sold"] else None,
            "age_days": age_days, "status": status,
            "variants": [
                {**vd, "last_sold": vd["last_sold"].isoformat() if vd["last_sold"] else None}
                for vd in rec["variants"]
            ],
        })
    prod_out.sort(key=lambda r: (-r["sold"], r["name"].lower()))

    # ── Breakdowns of what is on the shelf ───────────────────────────────────
    by_type: dict = {}
    for r in prod_out:
        t = by_type.setdefault(r["category"], {
            "category": r["category"], "products": 0, "units_on_hand": 0,
            "value_cost": 0.0, "value_retail": 0.0, "sold": 0, "revenue": 0.0,
        })
        t["products"] += 1
        t["units_on_hand"] += r["on_hand"]
        t["value_cost"] += r["value_cost"]
        t["value_retail"] += r["value_retail"]
    for cat, s in by_type_sales.items():
        t = by_type.setdefault(cat, {
            "category": cat, "products": 0, "units_on_hand": 0, "value_cost": 0.0, "value_retail": 0.0,
            "sold": 0, "revenue": 0.0,
        })
        t["sold"] = s["units"]
        t["revenue"] = round(s["revenue"], 2)
    for t in by_type.values():
        t["value_cost"] = round(t["value_cost"], 2)
        t["value_retail"] = round(t["value_retail"], 2)

    by_group: dict = {}
    for r in prod_out:
        key = (r["category"], r["category_name"] or "Uncategorised")
        g = by_group.setdefault(key, {
            "category": key[0], "name": key[1], "products": 0, "units_on_hand": 0, "value_cost": 0.0, "sold": 0,
        })
        g["products"] += 1
        g["units_on_hand"] += r["on_hand"]
        g["value_cost"] += r["value_cost"]
        g["sold"] += r["sold"]
    for g in by_group.values():
        g["value_cost"] = round(g["value_cost"], 2)

    size_stock: dict = defaultdict(lambda: {"on_hand": 0, "lines": 0})
    colour_stock: dict = defaultdict(lambda: {"on_hand": 0, "lines": 0})
    for vi in variant_index.values():
        if vi["category"] != "apparel":
            continue
        if vi["size"]:
            size_stock[vi["size"]]["on_hand"] += vi["qty"]
            size_stock[vi["size"]]["lines"] += 1
        if vi["colour"]:
            colour_stock[vi["colour"]]["on_hand"] += vi["qty"]
            colour_stock[vi["colour"]]["lines"] += 1
    sizes = sorted(set(size_stock) | set(size_sold), key=size_sort_key)
    by_size = [{"size": s, "on_hand": size_stock[s]["on_hand"], "lines": size_stock[s]["lines"],
                "sold": size_sold.get(s, 0)} for s in sizes]
    colours = sorted(set(colour_stock) | set(colour_sold), key=lambda c: (-(colour_stock[c]["on_hand"] + colour_sold.get(c, 0)), c))
    by_colour = [{"colour": c, "on_hand": colour_stock[c]["on_hand"], "lines": colour_stock[c]["lines"],
                  "sold": colour_sold.get(c, 0)} for c in colours]

    # ── Headline numbers ─────────────────────────────────────────────────────
    units_on_hand = sum(r["on_hand"] for r in prod_out)
    value_cost = round(sum(r["value_cost"] for r in prod_out), 2)
    value_retail = round(sum(r["value_retail"] for r in prod_out), 2)
    priced_cost = 0.0
    for r in prod_out:
        for vd in r["variants"]:
            if vd["eff_price"] is not None and vd["eff_cost"] is not None:
                priced_cost += vd["quantity"] * vd["eff_cost"]
    priced_retail = sum(
        vd["quantity"] * vd["eff_price"] for r in prod_out for vd in r["variants"]
        if vd["eff_price"] is not None and vd["eff_cost"] is not None
    )

    variants_total = sum(len(r["variants"]) for r in prod_out)
    no_cost = sum(1 for r in prod_out for vd in r["variants"] if vd["eff_cost"] is None)
    no_price = sum(1 for r in prod_out if r["for_resale"] for vd in r["variants"] if vd["eff_price"] is None)
    status_counts = defaultdict(int)
    for r in prod_out:
        status_counts[r["status"]] += 1

    history_note = None
    if tracked_from is not None and tracked_from > window_start:
        history_note = (
            f"Stock history starts on {tracked_from.isoformat()}, the day the earliest item was entered. "
            "Before that there is nothing to chart."
        )

    return {
        "window_days": days,
        "today": today.isoformat(),
        "bucket": "day" if step == 1 else "week",
        "kpis": {
            "units_on_hand": units_on_hand,
            "stock_value_cost": value_cost,
            "stock_value_retail": value_retail,
            "potential_margin": round(priced_retail - priced_cost, 2),
            "product_count": len(prod_out),
            "variant_count": variants_total,
            "out_of_stock": status_counts["out"],
            "low_stock": status_counts["low"],
            "running_low": status_counts["running_low"],
            "not_selling": status_counts["not_selling"],
            "units_sold": sold_units,
            "revenue": round(revenue, 2),
            "est_margin": round(revenue_costed - cogs, 2),
            "units_issued": issued_units,
            "units_received": received_units,
            "units_lost": lost_units,
            "sell_per_week": round(sold_units / weeks_in_window, 1) if weeks_in_window else 0,
        },
        "series": series,
        "products": prod_out,
        "by_type": sorted(by_type.values(), key=lambda t: -t["value_cost"]),
        "by_category": sorted(by_group.values(), key=lambda g: (-g["value_cost"], g["name"])),
        "by_size": by_size,
        "by_colour": by_colour,
        "sales_by_source": [
            {"source": s, "units": v["units"], "revenue": round(v["revenue"], 2)}
            for s, v in sorted(by_source.items(), key=lambda kv: -kv[1]["units"])
        ],
        "retired_sales": sorted(retired_sales.values(), key=lambda r: -r["units"]),
        "notes": {
            "history": history_note,
            "variants_without_cost": no_cost,
            "variants_without_price": no_price,
            "sold_units_without_price": unpriced_sold_units,
            "has_sales": sold_units > 0,
            "has_stock": units_on_hand > 0 or bool(prod_out),
        },
    }


def _as_date(x) -> date | None:
    if x is None:
        return None
    if isinstance(x, datetime):
        return x.date()
    return x


# ───────────────────────────────────────────────────────────────────────────
# Export helpers
# ───────────────────────────────────────────────────────────────────────────

async def movement_export_rows(session: AsyncSession, org_id, *, days: int | None = None, limit: int = 50000) -> list[dict]:
    """Every movement in the window (all time when `days` is None), newest first,
    named for a spreadsheet. Capped so one request cannot pull an unbounded table."""
    d_expr = _movement_date_expr().label("d")
    q = (
        select(MerchMovement, MerchProduct, MerchVariant, Player, d_expr)
        .join(MerchVariant, MerchVariant.id == MerchMovement.variant_id)
        .join(MerchProduct, MerchProduct.id == MerchVariant.product_id)
        .outerjoin(Player, Player.id == MerchMovement.player_id)
        .where(MerchMovement.organisation_id == org_id)
        .order_by(_movement_date_expr().desc(), MerchMovement.created_at.desc())
        .limit(limit)
    )
    if days:
        q = q.where(_movement_date_expr() >= date.today() - timedelta(days=days - 1))
    out = []
    for mv, p, v, pl, d in (await session.execute(q)).all():
        out.append({
            "date": _as_date(d).isoformat() if d else "",
            "category": p.category, "product": p.name, "variant": v.label,
            "size": v.size or "", "colour": v.colour or "", "sku": v.sku or "",
            "kind": mv.kind, "change": mv.delta, "balance_after": mv.quantity_after,
            "unit_price": _f(mv.unit_price), "amount": _f(mv.amount),
            "paid": mv.paid, "payment_method": mv.payment_method or "",
            "player": (getattr(pl, "display_name_override", None) or pl.name) if pl is not None else "",
            "source": mv.source or "manual", "note": mv.note or "",
            "retired": not (p.is_active and v.is_active),
        })
    return out


STATUS_LABELS = {
    "out": "Out of stock", "low": "Low stock", "running_low": "Running low",
    "not_selling": "Not selling", "ok": "OK",
}
TYPE_LABELS = {"apparel": "Apparel", "equipment": "Equipment", "food_drink": "Food & Drink"}


def csv_text(value) -> str:
    """A text cell for a CSV a club will open in a spreadsheet: a leading = + - or @
    is read as a formula there, so it gets a quote in front."""
    s = "" if value is None else str(value)
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s


def build_workbook(club_name: str, dash: dict, movements: list[dict]) -> bytes:
    """One .xlsx with a sheet per view of the same data the dashboard shows."""
    import io
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    head_font = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="1F2937")
    money_fmt = '"$"#,##0.00'

    def sheet(title, headers, rows, money_cols=(), widths=None, first=False):
        ws = wb.active if first else wb.create_sheet()
        ws.title = title
        ws.append(headers)
        for c in ws[1]:
            c.font = head_font
            c.fill = head_fill
            c.alignment = Alignment(vertical="center", wrap_text=True)
        for r in rows:
            ws.append(list(r))
            for cell in ws[ws.max_row]:
                # openpyxl turns any string starting with "=" into a formula.
                if isinstance(cell.value, str) and cell.value[:1] == "=":
                    cell.data_type = "s"
        for col in money_cols:
            for row in ws.iter_rows(min_row=2, min_col=col, max_col=col):
                for cell in row:
                    cell.number_format = money_fmt
        ws.freeze_panes = "A2"
        if rows:
            ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{ws.max_row}"
        for i, h in enumerate(headers, start=1):
            longest = max([len(str(h))] + [len(str(r[i - 1])) for r in rows[:300] if r[i - 1] is not None])
            ws.column_dimensions[get_column_letter(i)].width = (widths or {}).get(i, min(max(10, longest + 2), 44))
        return ws

    k = dash["kpis"]
    days = dash["window_days"]
    summary = [
        ("Club", club_name), ("Report date", dash["today"]), ("Sales window", f"Last {days} days"),
        ("", ""),
        ("Units on hand", k["units_on_hand"]), ("Stock value (cost)", k["stock_value_cost"]),
        ("Stock value (retail)", k["stock_value_retail"]),
        ("Potential margin (items with a cost and a price)", k["potential_margin"]),
        ("Products", k["product_count"]), ("Stock lines (size/colour)", k["variant_count"]),
        ("Out of stock (products)", k["out_of_stock"]), ("Low stock (products)", k["low_stock"]),
        ("Running low at current selling rate (products)", k["running_low"]),
        ("Not selling (products)", k["not_selling"]),
        ("", ""),
        (f"Units sold, last {days} days", k["units_sold"]), (f"Revenue, last {days} days", k["revenue"]),
        ("Estimated margin on those sales (at today's cost)", k["est_margin"]),
        (f"Units issued to players, last {days} days", k["units_issued"]),
        (f"Units received, last {days} days", k["units_received"]),
        (f"Units used or written off, last {days} days", k["units_lost"]),
    ]
    ws = sheet("Summary", ["Measure", "Value"], summary, widths={1: 52, 2: 28}, first=True)
    for r in range(2, ws.max_row + 1):
        label = str(ws.cell(r, 1).value or "")
        if any(w in label for w in ("value", "Revenue", "margin", "Margin")) and isinstance(ws.cell(r, 2).value, (int, float)):
            ws.cell(r, 2).number_format = money_fmt
    ws.auto_filter.ref = None

    stock_rows = []
    for p in dash["products"]:
        for v in p["variants"]:
            q = v["quantity"]
            stock_rows.append((
                TYPE_LABELS.get(p["category"], p["category"]), p["category_name"] or "", p["name"], v["label"],
                v["size"] or "", v["colour"] or "", v["sku"] or "", p["supplier"] or "",
                q, v["eff_cost"], v["eff_price"],
                q * v["eff_cost"] if v["eff_cost"] is not None else None,
                q * v["eff_price"] if v["eff_price"] is not None else None,
                v["threshold"], v["sold"], v["issued"], v["last_sold"] or "",
                "Club use" if not p["for_resale"] else "For sale",
                STATUS_LABELS.get(p["status"], p["status"]),
            ))
    sheet("Stock", ["Type", "Category", "Product", "Variant", "Size", "Colour", "SKU", "Supplier", "On hand",
                    "Unit cost", "Unit price", "Value at cost", "Value at retail", "Reorder at",
                    f"Sold ({days}d)", f"Issued ({days}d)", "Last sold", "Use", "Product status"],
          stock_rows, money_cols=(10, 11, 12, 13))

    sales_rows = [(
        p["name"], TYPE_LABELS.get(p["category"], p["category"]), p["on_hand"], p["sold"], p["revenue"],
        p["issued"], p["received"], p["lost"], p["per_week"], p["weeks_cover"] if p["weeks_cover"] is not None else "",
        p["last_sold"] or "", STATUS_LABELS.get(p["status"], p["status"]),
    ) for p in dash["products"]]
    sheet("Sales by item", ["Product", "Type", "On hand", f"Sold ({days}d)", f"Revenue ({days}d)", "Issued",
                            "Received", "Used / written off", "Sold per week", "Weeks of cover", "Last sold", "Status"],
          sales_rows, money_cols=(5,))

    sheet("By size", ["Size", "On hand", "Stock lines", f"Sold ({days}d)"],
          [(s["size"], s["on_hand"], s["lines"], s["sold"]) for s in dash["by_size"]])
    sheet("By colour", ["Colour", "On hand", "Stock lines", f"Sold ({days}d)"],
          [(c["colour"], c["on_hand"], c["lines"], c["sold"]) for c in dash["by_colour"]])

    unit = "Day" if dash["bucket"] == "day" else "Week"
    sheet("Over time", [f"{unit} from", f"{unit} to", "Units on hand (end)", "Stock value at cost (end)",
                        "Sold", "Revenue", "Issued", "Received", "Used / written off"],
          [(s["start"], s["end"], s["stock_units"], s["stock_value_cost"], s["sold"], s["revenue"],
            s["issued"], s["received"], s["lost"]) for s in dash["series"]], money_cols=(4, 6))

    sheet("Movements", ["Date", "Type", "Product", "Variant", "Size", "Colour", "SKU", "Movement", "Change",
                        "Balance after", "Unit price", "Amount", "Paid", "Payment method", "Player", "Source", "Note"],
          [(m["date"], TYPE_LABELS.get(m["category"], m["category"]), m["product"], m["variant"], m["size"],
            m["colour"], m["sku"], m["kind"], m["change"], m["balance_after"], m["unit_price"], m["amount"],
            "Yes" if m["paid"] else "No", m["payment_method"], m["player"], m["source"], m["note"])
           for m in movements], money_cols=(11, 12))

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
