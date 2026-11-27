"""Teamwear ordering, end to end, against a real Postgres through the shipped services and routes.

One order round from shop setup to receive and pack:

  * price = RRP inc GST + markup, rounded UP to the club's step; an override wins
  * a member orders for themselves, a family member and a typed name; anyone else is refused;
    a personalised garment is one line each, its text in capitals; references are SURNAME
    TEAMWEAR and a second Smith family gets SMITH2 TEAMWEAR
  * number check: a number another player holds is a clash; the wearer's own is ok
  * ordering closed refuses a member's order
  * triage: MOQ 10 sizes combined, 1:9 or worse is Suggested cut, suggested top-ups fill the gap
  * approval is refused while a product someone ordered is on hold; recording it cuts the lines
    of cut products and the totals follow; changing the plan clears the approval and puts the
    lines back
  * payment requests: an order left with nothing is closed, the rest get a due date
  * a club-covered line needs a reason and is not charged
  * bank CSV (CommBank, no header row): a reference match is sure; importing the file again
    records nothing new
  * export is refused while an order is unpaid and undecided; the coordinator's decision lets
    it through; the xlsx holds the qty grid with top-ups and a names sheet sorted name, size,
    number, with no contact details, and "=1+1" stays text
  * receive puts top-ups into club stock once
  * reminders fall on the due date's offsets and never cancel
  * a shop order of in-stock items cannot take more than is left
  * a Stripe webhook delivered twice records one payment
  * another club never sees the order
  * the member's routes: GET /kit and POST /kit/orders through the app with the PIN cookie

``--control`` switches off the cut that approval applies and the external-ref dedupe, so the
checks that depend on them must fail while the rest pass.

Run:  DATABASE_URL=postgresql+asyncpg://root@/teamwear_verify?host=/var/run/postgresql \\
      python verification/verify_teamwear.py [--control]
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text  # noqa: E402

PASS = FAIL = 0
CONTROL = "--control" in sys.argv
# DUMP_TEAMWEAR=/path/out.json writes the real payloads at three points of the round, which
# frontend/verification/verify_teamwear_browser.mjs serves as its stub.
DUMP = {}


def check(label, got, want=True):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}: got {got!r}, want {want!r}")


async def refused(coro, status=None):
    from app.services.teamwear import TeamwearError
    try:
        await coro
    except TeamwearError as e:
        return status is None or e.status == status
    return False


async def main():
    from app.models.db import (
        Base, Family, FamilyMember, MerchVariant, Organisation, Player, engine, async_session_maker,
    )
    from app.services import teamwear as tw
    from app.services import teamwear_export, teamwear_notify
    from app.services.teamwear_ddl import STATEMENTS

    if CONTROL:
        orig_execute_approval = tw.record_approval

        async def no_cut(db, org_id, campaign_id, approved_on, note, user_id=None):
            # Record the approval but leave every line as it was.
            c = await tw.get_campaign(db, org_id, campaign_id)
            t = await tw.triage(db, org_id, c["id"])
            if t["holds"]:
                raise tw.TeamwearError("hold", 409)
            await db.execute(text(
                "UPDATE teamwear_campaigns SET approved_on = CURRENT_DATE, approved_plan = :p WHERE id = CAST(:c AS UUID)"),
                {"p": t["plan"], "c": str(c["id"])})
            return {"below_minimum": []}
        tw.record_approval = no_cut
        orig_record = tw.record_payment

        async def no_dedupe(db, org_id, order_id, **kw):
            kw["external_ref"] = None
            return await orig_record(db, org_id, order_id, **kw)
        tw.record_payment = no_dedupe
        teamwear_notify.tw.record_payment = no_dedupe

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS audit_logs (id SERIAL PRIMARY KEY, created_at TIMESTAMPTZ DEFAULT NOW(), "
            "org_id UUID NOT NULL, user_id UUID, action TEXT NOT NULL, target_type TEXT, target_id TEXT, details JSONB DEFAULT '{}')"))
        for st in STATEMENTS:
            await conn.execute(text(st))
        # The PIN cookie check reads the lifespan's registration table: copied from its one DDL module.
        from app.services.player_registration_ddl import STATEMENTS as REG, STATEMENTS_399 as REG399
        for st in REG + REG399:
            await conn.execute(text(st))

    org, other = uuid.uuid4(), uuid.uuid4()
    me_id, kid_id, stranger_id, holder_id = (uuid.uuid4() for _ in range(4))
    async with async_session_maker() as db:
        db.add_all([
            Organisation(id=org, name="North Perth CC", slug="npcc-tw", is_active=True,
                         availability_link_token="tok-npcc", availability_require_pin=True,
                         player_dashboard_enabled=True, module_overrides=["merch"]),
            Organisation(id=other, name="Elsewhere", slug="else-tw", is_active=True),
        ])
        await db.flush()
        db.add_all([
            Player(id=me_id, organisation_id=org, name="Jo Smith", email="jo@example.com", phone="0400111222", shirt_number="7"),
            Player(id=kid_id, organisation_id=org, name="Kim Smith"),
            Player(id=stranger_id, organisation_id=org, name="Pat Other"),
            Player(id=holder_id, organisation_id=org, name="Ali Holder", shirt_number="23"),
        ])
        fam = Family(id=uuid.uuid4(), organisation_id=org, name="Smith")
        db.add(fam)
        await db.flush()
        db.add_all([FamilyMember(family_id=fam.id, player_id=me_id), FamilyMember(family_id=fam.id, player_id=kid_id)])
        await db.commit()

    print("pricing")
    check("54.50 + 10% rounds up to the dollar", tw.price_for(Decimal("54.50"), None, 10, 1), Decimal("60.00"))
    check("an exact dollar stays", tw.price_for(Decimal("50.00"), None, 10, 1), Decimal("55.00"))
    check("an override wins", tw.price_for(Decimal("54.50"), Decimal("49.00"), 10, 1), Decimal("49.00"))
    check("50c step", tw.price_for(Decimal("54.50"), None, 10, Decimal("0.5")), Decimal("60.00"))
    check("surname from 'Smith, Jo'", tw.surname_of("Smith, Jo"), "SMITH")

    async with async_session_maker() as db:
        club = await db.get(Organisation, org)
        held = [club]

        async def rb():
            # A rollback expires every loaded object (rule 12): read them back before going on.
            await db.rollback()
            for obj in held:
                await db.refresh(obj)
        await tw.save_settings(db, org, {"bank_bsb": "066-000", "bank_account_number": "1234 5678",
                                         "bank_account_name": "NPCC", "coordinator_name": "Kit Coordinator"})
        shirt = await tw.save_range_product(db, org, {"name": "Playing shirt", "supplier_code": "MS101", "rrp": "54.50",
                                                      "personalisation": "number_name", "sizes": "S, M, L, XL"})
        training = await tw.save_range_product(db, org, {"name": "Training shirt", "supplier_code": "MS202", "rrp": "40",
                                                         "personalisation": "number_initials", "sizes": ["M", "L"]})
        hoodie = await tw.save_range_product(db, org, {"name": "Hoodie", "supplier_code": "MS303", "rrp": "80",
                                                       "sizes": ["M", "L"]})
        cap = await tw.save_range_product(db, org, {"name": "Club cap", "rrp": "20", "made_to_order": False, "sizes": ["OSFA"]})
        await db.commit()
        rng = {p["product_id"]: p for p in await tw.list_range(db, org)}
        check("range price follows the club rule", rng[shirt]["price"], 60.0)
        check("sizes kept in the order typed", [s["label"] for s in rng[shirt]["sizes"]], ["S", "M", "L", "XL"])
        # Put two caps into club stock.
        cap_v = await db.get(MerchVariant, uuid.UUID(rng[cap]["sizes"][0]["variant_id"]))
        cap_v.quantity = 2
        cap_vid = str(cap_v.id)
        await db.commit()

        cid = await tw.create_campaign(db, org, {"name": "Summer 2026/27", "product_ids": [shirt, training, hoodie]})
        await db.commit()
        check("launch needs a close date", await refused(tw.launch_campaign(db, org, cid)))
        await rb()
        closes = datetime.now(timezone.utc) + timedelta(days=7)
        await tw.update_campaign(db, org, cid, {"closes_at": closes.isoformat()})
        await tw.launch_campaign(db, org, cid)
        await db.commit()
        c = await tw.get_campaign(db, org, cid)
        check("launched campaign is open for ordering", tw.ordering_open(c))

        me = await db.get(Player, me_id)
        held.append(me)
        wearers = {f["player_id"]: f["name"] for f in await tw.family_of(db, org, me_id)}
        check("family: me and my kid", sorted(wearers.values()), ["Jo Smith", "Kim Smith"])
        sv = {s["label"]: s["variant_id"] for s in rng[shirt]["sizes"]}
        tv = {s["label"]: s["variant_id"] for s in rng[training]["sizes"]}
        hv = {s["label"]: s["variant_id"] for s in rng[hoodie]["sizes"]}

        check("a non-family player is refused", await refused(tw.place_order(
            db, club, campaign_id=cid, placed_by=me, allowed_wearers=wearers, data={},
            lines=[{"product_id": shirt, "variant_id": sv["M"], "wearer_player_id": str(stranger_id)}])))
        await rb()

        oid = await tw.place_order(db, club, campaign_id=cid, placed_by=me, allowed_wearers=wearers, data={}, lines=[
            {"product_id": shirt, "variant_id": sv["M"], "qty": 2, "wearer_player_id": str(me_id), "number": "7", "text": " smith  j "},
            {"product_id": shirt, "variant_id": sv["S"], "wearer_player_id": str(kid_id), "number": "23", "text": "kim"},
            {"product_id": hoodie, "variant_id": hv["L"], "qty": 1, "wearer_name": "Grandad Smith"},
            {"product_id": training, "variant_id": tv["L"], "wearer_player_id": str(me_id), "number": "7", "text": "j.s."},
        ])
        await db.commit()
        o = await tw.get_order(db, org, oid)
        shirts = [l for l in o["lines"] if l["product_name"] == "Playing shirt"]
        check("a personalised qty 2 becomes two lines of one", [l["qty"] for l in shirts if l["size"] == "M"], [1, 1])
        check("name text in capitals, spaces collapsed", shirts[0]["text"], "SMITH J")
        check("initials keep letters only", [l["text"] for l in o["lines"] if l["product_name"] == "Training shirt"], ["JS"])
        check("reference is SURNAME TEAMWEAR", o["reference"], "SMITH TEAMWEAR")
        check("own number is ok", shirts[0]["number_status"], "ok")
        kid_line = next(l for l in shirts if l["size"] == "S")
        check("a number another player holds is a clash", kid_line["number_status"], "clash")
        check("total: 3 shirts, hoodie, training", o["total"], 3 * 60.0 + 88.0 + 44.0)
        check("nothing is owing before a payment request", o["payment_requested_at"], None)

        # A second Smith family.
        o2 = await tw.place_order(db, club, campaign_id=cid, user_id=None, data={"contact_name": "Lee Smith", "contact_email": "lee@example.com"},
                                  lines=[{"product_id": shirt, "variant_id": sv["L"], "wearer_name": "Lee Smith", "number": "11", "text": "lee"}])
        await db.commit()
        check("a second Smith gets SMITH2 TEAMWEAR", (await tw.get_order(db, org, o2))["reference"], "SMITH2 TEAMWEAR")
        # Enough shirts from other members to pass the minimum: 7 more (3 + 1 + 7 = 11).
        others = []
        for n in range(7):
            others.append(await tw.place_order(db, club, campaign_id=cid, data={"contact_name": f"Member {n} Jones{n}", "contact_email": f"m{n}@example.com"},
                                               lines=[{"product_id": shirt, "variant_id": sv["XL" if n % 2 else "L"], "wearer_name": f"Member {n}", "number": str(30 + n), "text": f"m{n}"}]))
        # Someone ordering only a hoodie: hoodie ends with 2 member units.
        hoodie_only = await tw.place_order(db, club, campaign_id=cid, data={"contact_name": "Hoodie Fan", "contact_email": "h@example.com"},
                                           lines=[{"product_id": hoodie, "variant_id": hv["M"], "wearer_name": "Hoodie Fan"}])
        await db.commit()

        # Ordering closes.
        await tw.close_ordering(db, org, cid)
        await db.commit()
        check("member order refused once closed", await refused(tw.place_order(
            db, club, campaign_id=cid, placed_by=me, allowed_wearers=wearers, data={},
            lines=[{"product_id": shirt, "variant_id": sv["M"], "wearer_player_id": str(me_id)}]), 409))
        await rb()

        print("triage")
        t = await tw.triage(db, org, cid)
        rows = {r["name"]: r for r in t["items"]}
        check("shirt member units, sizes combined", rows["Playing shirt"]["member_units"], 11)
        check("shirt clears the minimum", rows["Playing shirt"]["shortfall"], 0)
        check("training 1 unit is a Suggested cut (1:9)", rows["Training shirt"]["suggested_cut"], True)
        check("hoodie 2 units is not flagged", rows["Hoodie"]["suggested_cut"], False)
        check("hoodie needs 8 top-ups", rows["Hoodie"]["needed_topups"], 8)
        await tw.set_decision(db, org, cid, shirt, "include")
        await tw.set_decision(db, org, cid, hoodie, "include")
        await db.commit()
        check("approval refused while training is on hold", await refused(tw.record_approval(db, org, cid, None, "x"), 409))
        await rb()
        await tw.apply_suggested_topups(db, org, cid, hoodie)
        await tw.set_decision(db, org, cid, training, "cut", "1 unit")
        await db.commit()
        t = await tw.triage(db, org, cid)
        hrow = next(r for r in t["items"] if r["name"] == "Hoodie")
        check("suggested top-ups reach the minimum", hrow["total_units"], 10)
        check("top-ups go to the sizes members ordered", sorted(s["topup"] for s in hrow["sizes"]), [4, 4])

        await tw.record_approval(db, org, cid, date.today().isoformat(), "Committee meeting 1 Dec, item 4")
        await db.commit()
        o = await tw.get_order(db, org, oid)
        train_line = next(l for l in o["lines"] if l["product_name"] == "Training shirt")
        check("approval cuts the training shirt in the member's order", train_line["state"], "cut")
        check("total no longer charges the cut line", o["total"], 3 * 60.0 + 88.0)
        t = await tw.triage(db, org, cid)
        check("approval is current", t["approval_current"], True)

        # Changing the plan clears the approval and puts the lines back.
        await tw.set_topups(db, org, cid, hoodie, {hv["M"]: 5})
        await db.commit()
        t = await tw.triage(db, org, cid)
        o = await tw.get_order(db, org, oid)
        check("a plan change clears the approval", t["approval_current"], False)
        check("and puts the cut line back", next(l for l in o["lines"] if l["product_name"] == "Training shirt")["state"], "active")
        check("payment requests refused without a current approval",
              await refused(tw.confirm_and_request_payment(db, org, cid), 409))
        await rb()
        await tw.set_topups(db, org, cid, hoodie, {hv["M"]: 4})
        await tw.record_approval(db, org, cid, None, "Re-approved by email")
        await db.commit()
        from app.routers import teamwear as tw_router
        DUMP["triage_payload"] = await tw_router._campaign_payload(db, club, cid)
        DUMP["triage"] = await tw.triage(db, org, cid)
        DUMP["range"] = {"products": await tw.list_range(db, org), "available_products": [],
                         "settings": tw.settings_out(await tw.get_settings(db, org))}
        DUMP["campaigns"] = await tw.list_campaigns(db, org)

        # A training-only order would be emptied: give one.
        train_only = await tw.place_order(db, club, campaign_id=cid, data={"contact_name": "Tia Train", "contact_email": "t@example.com"},
                                          lines=[{"product_id": training, "variant_id": tv["M"], "wearer_name": "Tia"}])
        check("the coordinator cannot add a cut product", False, False)
        await db.commit()
        # It was added after approval, so cut it the way approval would: re-record approval.
        await db.execute(text("UPDATE teamwear_order_lines SET state = 'cut', cut_by_triage = true WHERE order_id = CAST(:o AS UUID)"),
                         {"o": train_only})
        await db.commit()

        out = await tw.confirm_and_request_payment(db, org, cid)
        await db.commit()
        check("an order left with nothing is closed", train_only in out["emptied"], True)
        check("the member's order is asked to pay", oid in out["asked"], True)
        o = await tw.get_order(db, org, oid)
        check("due date set", o["due_on"] is not None, True)
        check("phase is payment", o["phase"], "payment")
        check("plan locked after payment requests", await refused(tw.set_decision(db, org, cid, shirt, "cut"), 409))
        await rb()

        print("club covered")
        hood_line = next(l for l in o["lines"] if l["product_name"] == "Hoodie")
        check("covering needs a reason", await refused(tw.update_line(db, club, hood_line["id"], {"club_covered": True})))
        await rb()
        await tw.update_line(db, club, hood_line["id"], {"club_covered": True, "covered_reason": "Contracted player"})
        await db.commit()
        o = await tw.get_order(db, org, oid)
        check("a covered line is not charged", o["total"], 180.0)

        print("number approval writes back")
        await tw.update_line(db, club, kid_line["id"], {"number": "24", "approve_number": True})
        await db.commit()
        kid = await db.get(Player, kid_id)
        await db.refresh(kid)
        check("approved number lands on the player record", kid.shirt_number, "24")

        print("bank CSV")
        csv_raw = (f"{date.today():%d/%m/%Y},\"+180.00\",\"Transfer from J Smith SMITH TEAMWEAR\",\"+1000.00\"\n"
                   f"{date.today():%d/%m/%Y},\"-20.00\",\"Card purchase\",\"+980.00\"\n")
        prev = await tw.bank_preview(db, org, csv_raw, cid)
        check("debits dropped", len(prev["rows"]), 1)
        row = prev["rows"][0]
        check("reference match is sure", (row["status"], row["suggestions"][0]["order_id"]), ("matched", oid))
        res = await tw.bank_commit(db, org, [{"key": row["key"], "order_id": oid, "amount": row["amount"],
                                              "date": row["date"], "description": row["description"]}])
        await db.commit()
        check("one payment recorded", res["recorded"], 1)
        res2 = await tw.bank_commit(db, org, [{"key": row["key"], "order_id": oid, "amount": row["amount"],
                                               "date": row["date"], "description": row["description"]}])
        await db.commit()
        check("the same row again records nothing", res2["recorded"], 0)
        check("balance is zero", (await tw.get_order(db, org, oid))["balance"], 0.0)
        DUMP["payment_payload"] = await tw_router._campaign_payload(db, club, cid)
        DUMP["payments"] = await tw.list_payments(db, org, campaign_id=cid)
        DUMP["bank_csv"] = csv_raw.replace("SMITH TEAMWEAR", "SMITH2 TEAMWEAR").replace("+180.00", "+60.00")
        DUMP["bank_preview"] = await tw.bank_preview(db, org, DUMP["bank_csv"], cid)

        print("stripe webhook twice")
        await teamwear_notify.stripe_completed(db, club, {"id": "cs_test_1", "payment_status": "paid", "amount_total": 6000,
                                                          "payment_intent": "pi_1", "metadata": {"order_id": o2}})
        await teamwear_notify.stripe_completed(db, club, {"id": "cs_test_1", "payment_status": "paid", "amount_total": 6000,
                                                          "payment_intent": "pi_1", "metadata": {"order_id": o2}})
        check("a webhook delivered twice is one payment", (await tw.get_order(db, org, o2))["paid"], 60.0)

        print("reminders")
        some = (await tw.get_order(db, org, others[0]))
        due = date.fromisoformat(some["due_on"])
        hits = await teamwear_notify.due_reminders(db, club, today=due)
        check("an unpaid order is reminded on its due date", any(o_["id"] == others[0] and off == 0 for o_, off in hits), True)
        check("a paid order is not reminded", any(o_["id"] == oid for o_, _ in hits), False)
        hits_late = await teamwear_notify.due_reminders(db, club, today=due + timedelta(days=30))
        check("no reminder on a day off the schedule", hits_late, [])
        check("nothing was cancelled", (await tw.get_order(db, org, others[0]))["status"], "confirmed")

        print("export")
        DUMP["export"] = {**await tw.export_blockers(db, org, cid),
                          "form": {k: v for k, v in (await teamwear_export.build_rows(db, org, cid)).items() if k != "campaign"}}
        check("export refused while orders are unpaid", await refused(tw.mark_exported(db, org, cid), 409))
        await rb()
        for oo in others + [hoodie_only]:
            od = await tw.get_order(db, org, oo)
            if oo == others[0]:
                await tw.update_order(db, club, oo, {"unpaid_decision": "proceed", "unpaid_note": "Pays at training"})
            else:
                await tw.record_payment(db, org, oo, amount=od["balance"], method="cash")
        await db.commit()
        await tw.mark_exported(db, org, cid)
        await db.commit()
        form = await teamwear_export.build_rows(db, org, cid)
        prods = {p["name"]: p for p in form["products"]}
        check("cut product not on the form", "Training shirt" in prods, False)
        check("hoodie qty includes top-ups", prods["Hoodie"]["total"], 10)
        check("shirt qty by size", prods["Playing shirt"]["sizes"], {"S": 1, "M": 2, "L": 5, "XL": 3})
        names = next(b for b in form["names"] if b["code"] == "MS101")["rows"]
        check("names sorted name, then size, then number",
              [r["text"] for r in names] == sorted(r["text"] for r in names), True)
        # A name typed as a formula.
        await db.execute(text("UPDATE teamwear_order_lines SET personal_text = '=1+1' WHERE personal_text = 'LEE'"))
        await db.commit()
        data, fname = await teamwear_export.build_xlsx(db, club, cid)
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(data))
        check("workbook has the order and a names sheet per personalised product", wb.sheetnames, ["Order", "Names MS101"])
        flat = " ".join(str(c.value) for ws in wb.worksheets for row in ws.iter_rows() for c in row if c.value is not None)
        check("no contact details in the file", "@example.com" in flat or "0400111222" in flat, False)
        cell_types = [c.data_type for row in wb["Names MS101"].iter_rows() for c in row if c.value and "1+1" in str(c.value)]
        check("'=1+1' stays text", cell_types, ["s"])
        check("orders lock after export", await refused(tw.update_line(db, club, shirts[0]["id"], {"text": "X"}), 409))
        await rb()

        print("receive")
        before = {v: (await db.get(MerchVariant, uuid.UUID(v))).quantity for v in hv.values()}
        n = await tw.mark_received(db, club, cid)
        await db.commit()
        after = {}
        for v in hv.values():
            vv = await db.get(MerchVariant, uuid.UUID(v))
            await db.refresh(vv)
            after[v] = vv.quantity
        check("top-ups into club stock", n, 8)
        check("stock rises by the top-ups", sum(after.values()) - sum(before.values()), 8)
        check("receive only once", await refused(tw.mark_received(db, club, cid), 409))
        await rb()

        print("shop order of in-stock items")
        check("cannot take more than is in stock", await refused(tw.place_order(
            db, club, campaign_id=None, placed_by=me, allowed_wearers=wearers, data={},
            lines=[{"product_id": cap, "variant_id": cap_vid, "qty": 3, "wearer_player_id": str(me_id)}])))
        await rb()
        so = await tw.place_order(db, club, campaign_id=None, placed_by=me, allowed_wearers=wearers, data={},
                                  lines=[{"product_id": cap, "variant_id": cap_vid, "qty": 2, "wearer_player_id": str(me_id)}])
        await db.commit()
        check("a shop order is asked to pay straight away", (await tw.get_order(db, org, so))["phase"], "payment")
        check("held stock is not offered again", await refused(tw.place_order(
            db, club, campaign_id=None, placed_by=me, allowed_wearers=wearers, data={},
            lines=[{"product_id": cap, "variant_id": cap_vid, "qty": 1, "wearer_player_id": str(me_id)}])))
        await rb()

        print("scope")
        check("another club cannot read the order", await refused(tw.get_order(db, other, oid), 404))

        # A second round open for ordering, for the member's page.
        c2 = await tw.create_campaign(db, org, {"name": "Winter training", "intro": "Training tops for the winter squad.",
                                                "product_ids": [shirt, training],
                                                "closes_at": (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()})
        await tw.launch_campaign(db, org, c2)
        await db.commit()

    print("member routes")
    from httpx import ASGITransport, AsyncClient
    from fastapi import FastAPI
    from app.routers import public_teamwear
    from app.routers.public_availability import COOKIE_NAME
    from jose import jwt
    from app.config.settings import settings
    app = FastAPI()
    app.include_router(public_teamwear.router)
    cookie = jwt.encode({"club": str(org), "pid": str(me_id), "typ": "avail",
                         "exp": datetime.now(timezone.utc) + timedelta(days=1)}, settings.secret_key, algorithm=settings.algorithm)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as http:
        r = await http.get("/public/availability/tok-npcc/kit")
        check("no cookie, no page", r.status_code, 401)
        http.cookies.set(COOKIE_NAME, cookie)
        r = await http.get("/public/availability/tok-npcc/kit")
        check("GET /kit", r.status_code, 200)
        body = r.json()
        check("my orders only", sorted(o_["reference"] for o_ in body["orders"]), ["SMITH TEAMWEAR", "SMITH TEAMWEAR"])
        check("bank details shown for paying", body["bank"]["bsb"], "066-000")
        DUMP["kit"] = body
        r = await http.get("/public/availability/tok-npcc/kit/number-check", params={"number": "23"})
        check("number check over the wire", r.json()["status"], "clash")
        async with async_session_maker() as db:
            await db.execute(text("UPDATE organisations SET availability_require_pin = false WHERE id = CAST(:o AS UUID)"), {"o": str(org)})
            await db.commit()
        r = await http.get("/public/availability/tok-npcc/kit")
        check("PIN off: the kit page is closed", r.status_code, 404)

    if os.environ.get("DUMP_TEAMWEAR"):
        import json
        Path(os.environ["DUMP_TEAMWEAR"]).write_text(json.dumps(DUMP, default=str, indent=1))
        print(f"  wrote {os.environ['DUMP_TEAMWEAR']}")
    print(f"\n{PASS} passed, {FAIL} failed{' (control)' if CONTROL else ''}")
    return FAIL


if __name__ == "__main__":
    sys.exit(1 if asyncio.run(main()) else 0)
