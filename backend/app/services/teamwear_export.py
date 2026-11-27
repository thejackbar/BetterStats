"""The supplier order form for a teamwear campaign, built fresh from the orders every time.

A generic layout for now (the club's supplier template can be mapped later):

* ``Order``: one row per included product (code, name), one column per size, quantities
  = member units + the club's top-ups, a total per row and per size.
* ``Names <code>``: one sheet per personalised product, the names block the supplier prints
  from: name (or initials), size, number, sorted name, then size, then number. No member
  contact details anywhere in the file.

Text that starts with ``=`` ``+`` ``-`` or ``@`` is written as a string cell so a spreadsheet
never reads a typed name as a formula.
"""
from __future__ import annotations

import io
import re
from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import teamwear as tw


def _safe(v):
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@"):
        return "'" + v
    return v


def _sheet_title(s: str, used: set) -> str:
    t = re.sub(r"[\[\]\*\?/\\:]", " ", s).strip()[:31] or "Sheet"
    base, n = t, 2
    while t.lower() in used:
        suffix = f" {n}"
        t = base[: 31 - len(suffix)] + suffix
        n += 1
    used.add(t.lower())
    return t


async def build_rows(db: AsyncSession, org_id, campaign_id) -> dict:
    """The numbers the form holds, as data (the tests read this, the xlsx is drawn from it)."""
    c = await tw.get_campaign(db, org_id, campaign_id)
    items = [i for i in await tw.campaign_items(db, c["id"]) if i["decision"] == "include"]
    variants = await tw._variants_for(db, [i["product_id"] for i in items])
    member = defaultdict(int)
    names: dict = defaultdict(list)
    rows = (await db.execute(text(
        "SELECT l.product_id, l.variant_id, l.size_label, l.qty, l.wearer_name, l.personal_number, l.personal_text "
        "FROM teamwear_order_lines l JOIN teamwear_orders o ON o.id = l.order_id "
        "WHERE o.campaign_id = CAST(:c AS UUID) AND o.status <> 'cancelled' AND l.state = 'active'"),
        {"c": str(c["id"])})).mappings().all()
    for r in rows:
        member[(r["product_id"], r["variant_id"])] += int(r["qty"])
        if r["personal_number"] or r["personal_text"]:
            names[r["product_id"]].append({
                "text": r["personal_text"] or "", "size": r["size_label"] or "", "number": r["personal_number"] or "",
            })
    tops = {r["variant_id"]: int(r["qty"]) for r in (await db.execute(text(
        "SELECT variant_id, qty FROM teamwear_topups WHERE campaign_id = CAST(:c AS UUID)"),
        {"c": str(c["id"])})).mappings().all()}

    size_cols: list[str] = []
    products = []
    for i in items:
        by_size = {}
        for v in variants.get(i["product_id"], []):
            label = v["size"] or v["label"]
            q = member[(i["product_id"], v["id"])] + tops.get(v["id"], 0)
            if q or v["is_active"]:
                if label not in size_cols:
                    size_cols.append(label)
            if q:
                by_size[label] = by_size.get(label, 0) + q
        products.append({"product_id": str(i["product_id"]), "code": i["supplier_code"] or "", "name": i["name"],
                         "personalisation": i["personalisation"], "sizes": by_size, "total": sum(by_size.values())})

    size_rank = {s: n for n, s in enumerate(size_cols)}

    def num_key(n):
        return (0, int(n), n) if n.isdigit() else (1, 0, n)

    name_blocks = []
    for p in products:
        lst = names.get(_uuid(p["product_id"]), [])
        lst.sort(key=lambda x: (x["text"], size_rank.get(x["size"], 999), num_key(x["number"])))
        if p["personalisation"] != "none":
            name_blocks.append({"code": p["code"], "name": p["name"], "personalisation": p["personalisation"], "rows": lst})
    return {"campaign": c, "sizes": size_cols, "products": products, "names": name_blocks}


def _uuid(s):
    import uuid
    return uuid.UUID(str(s))


async def build_xlsx(db: AsyncSession, club, campaign_id) -> tuple[bytes, str]:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    data = await build_rows(db, club.id, campaign_id)
    s = await tw.get_settings(db, club.id)
    c = data["campaign"]
    wb = Workbook()
    ws = wb.active
    used: set = set()
    ws.title = _sheet_title("Order", used)
    bold = Font(bold=True)
    head_fill = PatternFill("solid", fgColor="E8E8E8")
    ws.append([_safe(club.name)])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([_safe(f"{s['supplier_name'] or 'Supplier'} order: {c['name']}")])
    ws.append([f"Quantities include the club's top-ups. Generated {tw.today_local().isoformat()}."])
    ws.append([])
    header = ["Code", "Product"] + data["sizes"] + ["Total"]
    ws.append(header)
    hr = ws.max_row
    for cell in ws[hr]:
        cell.font = bold
        cell.fill = head_fill
        cell.alignment = Alignment(horizontal="center")
    col_tot = [0] * len(data["sizes"])
    for p in data["products"]:
        row = [_safe(p["code"]), _safe(p["name"])]
        for n, sz in enumerate(data["sizes"]):
            q = p["sizes"].get(sz, 0)
            col_tot[n] += q
            row.append(q or None)
        row.append(p["total"])
        ws.append(row)
    ws.append(["", "Total"] + [t or None for t in col_tot] + [sum(col_tot)])
    for cell in ws[ws.max_row]:
        cell.font = bold
    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 36

    for block in data["names"]:
        title = _sheet_title(f"Names {block['code'] or block['name']}", used)
        sh = wb.create_sheet(title)
        sh.append([_safe(f"{block['code']} {block['name']}".strip())])
        sh["A1"].font = bold
        label = "Initials" if block["personalisation"] == "number_initials" else "Name"
        sh.append([label, "Size", "Number"])
        for cell in sh[2]:
            cell.font = bold
            cell.fill = head_fill
        for r in block["rows"]:
            sh.append([_safe(r["text"]), _safe(r["size"]), _safe(r["number"])])
        sh.column_dimensions["A"].width = 28
    buf = io.BytesIO()
    wb.save(buf)
    fname = re.sub(r"[^A-Za-z0-9]+", "-", f"{club.short_name or club.name}-{c['name']}").strip("-")[:80] + ".xlsx"
    return buf.getvalue(), fname
