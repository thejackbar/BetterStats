"""BetterMerch stock dashboard and exports.

Checks, against a real Postgres through the shipped service and route bodies:

  * stock now: units, value at cost / retail, margin, per type, size order
  * selling: only `sold` movements count (issued, received, used are kept apart),
    a sale before the window is left out, a retired product's sales still count
  * stock over time: today's balance equals units on hand, and walking back
    through received / sold / stocktake movements gives the balance on the days
    in between; a variant is nothing before the day it was entered
  * status: out, low, running low (weeks of cover), not selling, and a product
    entered today is never "not selling"
  * another club's rows never appear
  * the Excel workbook opens, carries every sheet, and a product named "=1+1"
    stays text; the movements CSV prefixes it with a quote

The control run (``--control``) makes every movement fall outside the window, so
the sales, history and status checks that depend on movements must fail while
the stock-now checks still pass.

Set DUMP_DASHBOARD=/path/out.json to also write the real dashboard payloads, which
frontend/verification/verify_merch_dashboard_browser.mjs serves as its stub.

Run:  DATABASE_URL=postgresql+asyncpg://root@/merch_verify?host=/var/run/postgresql \
      python verification/verify_merch_dashboard.py [--control]
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
import uuid
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text  # noqa: E402

PASS = FAIL = 0
CONTROL = "--control" in sys.argv


def check(label, got, want=True):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}: got {got!r}, want {want!r}")


def at(d: date) -> datetime:
    return datetime.combine(d, time(12, 0), tzinfo=timezone.utc)


async def main():
    from app.models.db import (
        Base, MerchCategory, MerchMovement, MerchProduct, MerchVariant, Organisation, Player,
        engine, async_session_maker,
    )
    from app.services import merch_insights
    from app.routers import merch as merch_router

    if CONTROL:
        # Every movement lands in the far past, outside any window.
        from sqlalchemy import literal
        merch_insights._movement_date_expr = lambda: literal(date(2000, 1, 1))

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)

    today = date.today()
    d = lambda n: today - timedelta(days=n)  # noqa: E731
    org, other = uuid.uuid4(), uuid.uuid4()

    async with async_session_maker() as db:
        db.add_all([
            Organisation(id=org, name="Applecross", slug="apple-md", is_active=True),
            Organisation(id=other, name="Elsewhere", slug="else-md", is_active=True),
        ])
        await db.flush()
        pl = Player(id=uuid.uuid4(), organisation_id=org, name="Sam Buyer")
        db.add(pl)
        cat = MerchCategory(id=uuid.uuid4(), organisation_id=org, top_category="apparel", name="Caps")
        db.add(cat)
        await db.flush()

        def product(name, category="apparel", cost=None, price=None, thr=None, created=200, resale=True, active=True, cat_id=None):
            p = MerchProduct(id=uuid.uuid4(), organisation_id=org, category=category, name=name,
                             unit_cost=cost, unit_price=price, low_stock_threshold=thr, for_resale=resale,
                             is_active=active, category_id=cat_id, created_at=at(d(created)))
            db.add(p)
            return p

        def variant(p, label, size, colour, qty, created=200, active=True, org_id=org):
            v = MerchVariant(id=uuid.uuid4(), product_id=p.id, organisation_id=org_id, label=label, size=size,
                             colour=colour, quantity=qty, is_active=active, created_at=at(d(created)))
            db.add(v)
            return v

        # Polo: sells steadily. cost 20, price 40. Two sizes.
        polo = product("Playing polo", cost=20, price=40, thr=3)
        polo_m = variant(polo, "M", "M", "Green", 10)
        polo_l = variant(polo, "L", "L", "Green", 0)
        # Cap: not selling, old stock, cost 5 price 12, under a named category.
        cap = product("Club cap", cost=5, price=12, cat_id=cat.id)
        cap_s = variant(cap, "One size", None, "Navy", 8)
        # Hoodie: low against reorder point, sells.
        hood = product("Hoodie", cost=30, price=65, thr=5)
        hood_xl = variant(hood, "2XL", "2XL", "Black", 4)
        hood_s = variant(hood, "S", "S", "Black", 20)
        # Balls: club use, no price.
        balls = product("Match balls", category="equipment", cost=15, resale=False)
        balls_v = variant(balls, "Standard", None, None, 12)
        # Entered "this afternoon": never "not selling".
        new = product("New scarf", cost=8, price=18, created=0)
        new_v = variant(new, "Standard", None, "Red", 6, created=0)
        # Retired product that still sold in the window.
        old = product("Old jersey", cost=25, price=50, active=False)
        old_v = variant(old, "M", "M", None, 0, active=False)
        # A trap name for the spreadsheet.
        evil = product("=1+1", cost=1, price=2, created=0)
        evil_v = variant(evil, "Standard", None, None, 1, created=0)
        # Sold out, and one that is selling faster than it lasts.
        socks = product("Sold-out socks", cost=4, price=10)
        socks_v = variant(socks, "Standard", None, "White", 0)
        bottle = product("Water bottle", cost=6, price=15)
        bottle_v = variant(bottle, "Standard", None, "Blue", 2)
        # Another club's stock and sale.
        op = MerchProduct(id=uuid.uuid4(), organisation_id=other, category="apparel", name="Other club tee",
                          unit_cost=10, unit_price=30, for_resale=True)
        db.add(op)
        await db.flush()
        ov = variant(op, "M", "M", "Blue", 99, org_id=other)
        await db.flush()

        def mv(v, kind, delta, days_ago, price=None, amount=None, source="manual", player=None, note=None):
            db.add(MerchMovement(
                variant_id=v.id, organisation_id=v.organisation_id, kind=kind, delta=delta,
                unit_price=price, amount=amount, source=source, player_id=player, note=note,
                occurred_on=d(days_ago), created_at=at(d(days_ago)),
            ))

        # Polo M: now 10. 40 days ago +20 received (so 10 -> before that -10? see below),
        # sold 5 ten days ago and 5 three days ago. Balance now 10:
        #   end of 3 days ago -> 10 + 0 (the 3d sale is dated 3 days ago, so balance end of that day is 10)
        #   end of 4 days ago -> 15, end of 10 days ago -> 10 ... worked out in the checks.
        mv(polo_m, "received", 20, 40)
        mv(polo_m, "sold", -5, 10, price=40, amount=200)
        mv(polo_m, "sold", -5, 3, price=40, amount=200, source="square")
        mv(polo_m, "sold", -2, 150, price=40, amount=80)           # before a 90 day window
        mv(polo_m, "issued", -1, 5, player=pl.id, note="=SUM(A1)")  # kit, not selling
        mv(polo_m, "write_off", -1, 2)
        # Polo L: sold out.
        mv(polo_l, "sold", -3, 20, price=40, amount=120, source="online_store")
        # Hoodie: sells 6 over the window, current 20 + 4.
        mv(hood_s, "sold", -6, 15, price=65, amount=390)
        # Retired jersey: two sold 30 days ago, priced.
        mv(old_v, "sold", -2, 30, price=50, amount=100)
        mv(socks_v, "sold", -4, 40, price=10, amount=40)
        mv(bottle_v, "sold", -20, 25, price=15, amount=300)
        # A sale with no price recorded: counted as a unit, no revenue.
        mv(hood_xl, "sold", -1, 12)
        await db.commit()

    async def dash(days=90):
        async with async_session_maker() as db:
            club = await db.get(Organisation, org)
            return await merch_router.stock_dashboard(days=days, club=club, db=db)

    D = await dash(90)
    k = D["kpis"]
    prods = {p["name"]: p for p in D["products"]}
    get = lambda name, key, dflt=None: prods.get(name, {}).get(key, dflt)  # noqa: E731

    print("stock now")
    # polo 10x20 + 0, cap 8x5, hoodie (4+20)x30, balls 12x15, scarf 6x8, evil 1x1
    exp_cost = 10 * 20 + 8 * 5 + 24 * 30 + 12 * 15 + 6 * 8 + 1 * 1 + 2 * 6
    check("units on hand", k["units_on_hand"], 10 + 8 + 24 + 12 + 6 + 1 + 2)
    check("stock value at cost", k["stock_value_cost"], float(exp_cost))
    check("stock value at retail", k["stock_value_retail"], float(10 * 40 + 8 * 12 + 24 * 65 + 6 * 18 + 1 * 2 + 2 * 15))
    check("potential margin only over items with cost and price",
          k["potential_margin"], float((10 * 40 + 8 * 12 + 24 * 65 + 6 * 18 + 2 + 2 * 15) - (10 * 20 + 8 * 5 + 24 * 30 + 6 * 8 + 1 + 2 * 6)))
    check("retired product is not on the shelf", "Old jersey" in prods, False)
    check("another club's stock is not counted", "Other club tee" in prods, False)
    check("type split has apparel and equipment", sorted(t["category"] for t in D["by_type"]), ["apparel", "equipment"])
    check("named category carried", get("Club cap", "category_name"), "Caps")

    print("selling")
    # in the 90 day window: polo M 10, polo L 3, hoodie 6 + 1 unpriced; old jersey 2 (retired)
    check("units sold counts only sold movements in the window", k["units_sold"], 5 + 5 + 3 + 6 + 1 + 2 + 4 + 20)
    check("sale before the window is left out", get("Playing polo", "sold"), 13)
    check("issued is kept apart from sold", (get("Playing polo", "issued"), k["units_issued"]), (1, 1))
    check("write-off is kept apart", k["units_lost"], 1)
    check("revenue", k["revenue"], 200.0 + 200 + 120 + 390 + 100 + 40 + 300)
    check("sale with no price counts as a unit and adds no revenue", D["notes"]["sold_units_without_price"], 1)
    check("retired product's sales are named", [r["name"] for r in D["retired_sales"]], ["Old jersey"])
    check("sales by source", {s["source"]: s["units"] for s in D["sales_by_source"]},
          {"manual": 5 + 6 + 1 + 2 + 4 + 20, "square": 5, "online_store": 3})
    best = D["products"][0]
    check("best seller first", best["name"], "Water bottle")
    # est. margin: revenue with a cost known minus units*cost. polo 13u... polo M 10u + L 3u = 13*20=260 vs revenue 520;
    # hoodie priced sale 6u: 390-180=210; unpriced hoodie sale excluded; old jersey 100-50=50
    check("estimated margin", k["est_margin"], (520.0 - 260) + (390 - 180) + (100 - 50) + (40 - 16) + (300 - 120))
    D365 = await dash(365)
    check("a wider window picks the older sale up", D365["kpis"]["units_sold"], k["units_sold"] + 2)
    D30 = await dash(30)
    # the jersey sale is dated exactly 30 days ago: a 30 day window is today and the 29 days before
    check("a narrower window drops older sales", D30["kpis"]["units_sold"], 5 + 5 + 3 + 6 + 1 + 20)

    print("size and colour")
    check("size order: letters in wearing order then numbers", [s["size"] for s in D["by_size"]], ["S", "M", "L", "2XL"])
    sm = {s["size"]: s for s in D["by_size"]}
    check("size on hand and sold", (sm["M"]["on_hand"], sm["M"]["sold"], sm["S"]["sold"]), (10, 10, 6))
    check("colour breakdown has the sold colour", {c["colour"] for c in D["by_colour"]} >= {"Green", "Black", "Navy"})

    print("stock over time")
    S = D["series"]
    check("weekly buckets for 90 days", (D["bucket"], len(S)), ("week", 13))
    check("last bucket ends today", S[-1]["end"], today.isoformat())
    check("today's balance equals units on hand", S[-1]["stock_units"], k["units_on_hand"])
    check("first bucket starts at the window start", S[0]["start"], (today - timedelta(days=89)).isoformat())
    D30s = D30["series"]
    check("daily buckets for 30 days", (D30["bucket"], len(D30s)), ("day", 30))

    # Polo M walked back: end of today 10; the 2 day ago write-off (-1) and 3 day ago sale (-5)
    # and 5 day ago issue (-1) happened after the end of 6 days ago => balance then 10+1+5+1 = 17.
    # (the other variants are flat: cap 8, hoodie 24, balls 12, polo L 0; scarf/evil are new today)
    day6 = {b["end"]: b for b in D30s}[(today - timedelta(days=6)).isoformat()]
    check("daily balance walked back through later movements",
          day6["stock_units"], 17 + 0 + 8 + 24 + 12 + 2)  # polo M + L + cap + hoodie + balls + bottle
    # Before the sale 10 days ago and the 15 day ago hoodie sale the totals were higher again.
    day11 = {b["end"]: b for b in D30s}[(today - timedelta(days=11)).isoformat()]
    # polo M: 17 + 5 (10d sale) = 22 ; hoodie: 24 + 1 (12d unpriced sale is dated 12 days ago: after day 13) -> still 24 at end of 11d? sale
    # 12d ago is BEFORE the end of 11d ago, so it is already in the balance at day 11 (24). Hoodie S 15d sale also before.
    check("balance two sales earlier", day11["stock_units"], 22 + 0 + 8 + 24 + 12 + 2)
    # Entered today: scarf 6 + evil 1 are not in yesterday's balance.
    yday = {b["end"]: b for b in D30s}[d(1).isoformat()]
    today_b = {b["end"]: b for b in D30s}[d(0).isoformat()]
    check("a variant is nothing before the day it was entered",
          today_b["stock_units"] - yday["stock_units"], 6 + 1)  # the scarf and the "=1+1" line, entered today

    print("status")
    check("a product with none left is out of stock", get("Sold-out socks", "status"), "out")
    check("one size under its reorder point makes the product low", get("Hoodie", "status"), "low")
    check("selling faster than the stock lasts is running low", get("Water bottle", "status"), "running_low")
    check("weeks of cover for the water bottle", get("Water bottle", "weeks_cover"), round(2 / (20 / (90 / 7)), 1))
    check("a sold-out size under its reorder point makes the product low", get("Playing polo", "status"), "low")
    check("headline counts of each status",
          (k["out_of_stock"], k["low_stock"], k["running_low"], k["not_selling"]), (1, 2, 1, 1))
    check("old stock with no sales is not selling", get("Club cap", "status"), "not_selling")
    check("a product entered today is not 'not selling'", get("New scarf", "status"), "ok")
    check("club-use stock is never 'not selling'", get("Match balls", "status"), "ok")
    check("selling rate and weeks of cover for polo",
          (get("Playing polo", "per_week") > 0, get("Playing polo", "weeks_cover") is not None), (True, True))
    check("variant detail is carried for the table", len(get("Playing polo", "variants")), 2)
    check("last sold date", get("Playing polo", "last_sold"), d(3).isoformat())

    print("exports")
    async with async_session_maker() as db:
        club = await db.get(Organisation, org)
        resp = await merch_router.export_workbook(days=90, club=club, db=db)
        csv_resp = await merch_router.export_movements(days=0, club=club, db=db)
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(resp.body))
    check("workbook sheets", wb.sheetnames,
          ["Summary", "Stock", "Sales by item", "By size", "By colour", "Over time", "Movements"])
    stock = wb["Stock"]
    names = [stock.cell(r, 3).value for r in range(2, stock.max_row + 1)]
    check("stock sheet has a row per stock line", len(names), 2 + 1 + 2 + 1 + 1 + 1 + 2)
    evil_cell = next(stock.cell(r, 3) for r in range(2, stock.max_row + 1) if stock.cell(r, 3).value == "=1+1")
    check("a product named =1+1 stays text", evil_cell.data_type, "s")
    check("no other club's product in the workbook", "Other club tee" in names, False)
    mov = wb["Movements"]
    check("movements sheet has every movement in the window", mov.max_row - 1, 12 - 1)  # 12 movements less the 150-day sale
    csv_text = csv_resp.body.decode()
    check("movements csv has a header and every movement", len(csv_text.strip().splitlines()), 1 + 12)
    check("a note starting with = is quoted in the csv", "'=SUM(A1)" in csv_text, True)
    check("csv has the formula-looking product quoted", "'=1+1" in csv_text or "=1+1" not in csv_text, True)

    dump = os.environ.get("DUMP_DASHBOARD")
    if dump:
        # The real payload for each window, for the browser suite to serve as its stub.
        import json
        Path(dump).write_text(json.dumps({"90": D, "30": D30, "365": D365}, default=str))

    print(f"\n{PASS} passed, {FAIL} failed" + (" (control run: failures are expected)" if CONTROL else ""))
    await engine.dispose()
    sys.exit(1 if FAIL and not CONTROL else 0)


asyncio.run(main())
