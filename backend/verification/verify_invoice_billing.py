"""Pay by invoice (migration 308).

Asked for: a club in a live trial wants to subscribe and be INVOICED. Any club
admin elects invoice billing and asks for one; the invoice is built with the
bundle and coupon discounts, raised and emailed to the Primary Club Admin with a
link back into Stripe's payment page; until the club changes the setting a
renewal invoice for every current module is emailed 14 days before each period
ends, and must be settled before the period ends. A Super Admin can do all of it
on the club's behalf.

This runs the SHIPPED service, webhook routing and route bodies against a real
Postgres. Stripe and the email provider are stubbed — a verification run must
not raise real invoices or send real email — and the stub records every call so
the checks can read exactly what would have been sent.

    python -m verification.verify_invoice_billing
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_URL = os.environ.get(
    "VERIFY_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/bs_invoice",
)
os.environ["DATABASE_URL"] = DB_URL

from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from app.models.db import (  # noqa: E402
    Base, BillingInvoice, ClubMembership, DiscountCoupon, DiscountCouponRedemption,
    Organisation, OrgModuleSubscription, User,
)

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} — {detail}")
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  ({detail})'}")


def load():
    """The shipped modules, or None — a control run against a build without the
    feature must REPORT it rather than die on the first ImportError."""
    try:
        from app.services import invoice_billing, invoice_billing_ddl, stripe_billing
        return invoice_billing, invoice_billing_ddl, stripe_billing
    except ImportError as e:
        print(f"  (feature absent: {e})")
        return None


# ─── Stripe + email stubs ────────────────────────────────────────────────────

class FakeStripe:
    def __init__(self):
        self.invoices: dict[str, dict] = {}
        self.created: list[dict] = []
        self.coupons: list[dict] = []
        self.voided: list[str] = []
        self.customers = 0
        self.n = 0

    async def ensure_customer_for_org(self, org, *, email, address):
        if getattr(org, "stripe_customer_id", None):
            return org.stripe_customer_id
        self.customers += 1
        return f"cus_{self.customers}"

    async def ensure_invoice_discount_coupon(self, db, *, bundle_dollars, coupon_code, coupon_dollars):
        total = round(bundle_dollars + coupon_dollars, 2)
        if total <= 0:
            return None
        self.coupons.append({"bundle": bundle_dollars, "code": coupon_code, "coupon": coupon_dollars, "total": total})
        return f"co_{len(self.coupons)}"

    async def create_one_off_invoice(self, *, customer_id, lines, due_at, metadata, coupon_id=None,
                                     description=None, footer=None, idempotency_key=None):
        self.n += 1
        iid = f"in_{self.n}"
        sub = sum(line["amount_cents"] for line in lines)
        disc = round(self.coupons[int(coupon_id.split("_")[1]) - 1]["total"] * 100) if coupon_id else 0
        ex = max(0, sub - disc)
        total = ex + round(ex * 0.1)  # GST on top
        inv = {
            "id": iid, "number": f"BC-{1000 + self.n}", "status": "open", "customer": customer_id,
            "total": total, "total_excluding_tax": ex, "amount_due": total, "amount_paid": 0,
            "currency": "aud", "metadata": dict(metadata), "billing_reason": "manual",
            "hosted_invoice_url": f"https://invoice.stripe.test/{iid}",
            "invoice_pdf": f"https://invoice.stripe.test/{iid}.pdf",
            "lines": {"data": [{"description": ln["description"], "amount": ln["amount_cents"]} for ln in lines]},
            "due_date": int(due_at.timestamp()),
        }
        self.invoices[iid] = inv
        self.created.append({"id": iid, "lines": lines, "due_at": due_at, "metadata": metadata,
                             "coupon_id": coupon_id, "description": description,
                             "idempotency_key": idempotency_key, "customer": customer_id})
        return inv

    async def void_invoice(self, invoice_id):
        self.voided.append(invoice_id)
        inv = self.invoices.get(invoice_id)
        if inv:
            inv["status"] = "void"
        return inv

    async def retrieve_invoice(self, invoice_id):
        return self.invoices[invoice_id]

    def paid(self, invoice_id, paid_at: datetime) -> dict:
        inv = dict(self.invoices[invoice_id])
        inv.update(status="paid", amount_paid=inv["total"],
                   status_transitions={"paid_at": int(paid_at.timestamp())})
        self.invoices[invoice_id] = inv
        return inv


class FakeProvider:
    name = "fake"

    def __init__(self):
        self.sent = []

    async def send(self, msg):
        from app.services.email_service import SendResult
        self.sent.append(msg)
        return SendResult(ok=True, message_id=f"m{len(self.sent)}")


class ConsoleProvider:
    name = "console"

    async def send(self, msg):
        from app.services.email_service import SendResult
        return SendResult(ok=True)


# ─── Fixture ─────────────────────────────────────────────────────────────────

async def make_club(db, name, *, trial_days=10, now=None, billing_method="invoice", primary_email="primary@club.test",
                    stripe_sub=None, enabled=None):
    now = now or datetime.now(timezone.utc)
    # A club paying by invoice has had invoicing switched on for it; every
    # other fixture club takes the column's own default (off), unless a check
    # says otherwise.
    extra = {} if enabled is None and billing_method != "invoice" else {"invoice_billing_enabled": enabled if enabled is not None else True}
    org = Organisation(id=uuid.uuid4(), name=name, slug=name.lower().replace(" ", "-"),
                       billing_method=billing_method, stripe_subscription_id=stripe_sub, **extra)
    db.add(org)
    await db.flush()
    for key in ("core", "select", "socials", "iq", "fees", "comms", "merch", "crm", "fantasy"):
        db.add(OrgModuleSubscription(organisation_id=org.id, module_key=key, status="trial",
                                     trial_started_at=now - timedelta(days=4),
                                     trial_ends_at=now + timedelta(days=trial_days)))
    users = {}
    for role, primary, email in (("club_admin", True, primary_email), ("club_admin", False, f"second@{name[:3]}.test"),
                                 ("club_member", False, f"member@{name[:3]}.test")):
        u = User(id=uuid.uuid4(), username=f"{name[:4]}-{role}-{primary}-{uuid.uuid4().hex[:4]}",
                 email=email, display_name=f"{'Pat Primary' if primary else 'Sam Second'}")
        db.add(u)
        await db.flush()
        db.add(ClubMembership(club_id=org.id, user_id=u.id, role=role, is_primary_admin=primary))
        users[(role, primary)] = u
    await db.commit()
    return org.id, users


async def fresh(db, org_id):
    # populate_existing, never expire_all(): expiring would also expire the
    # fixture's User objects, and the next plain attribute read on one is a
    # lazy load outside the greenlet (MissingGreenlet) — the harness, not the code.
    return await db.get(Organisation, org_id, options=[selectinload(Organisation.module_subscriptions)],
                        populate_existing=True)


def status_of(org, key):
    return next((r for r in org.module_subscriptions if r.module_key == key), None)


# ─── The run ─────────────────────────────────────────────────────────────────

async def main() -> int:
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS platform_settings (id INTEGER PRIMARY KEY DEFAULT 1, "
            "settings JSONB NOT NULL DEFAULT '{}', updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"
        ))
    Session = async_sessionmaker(engine, expire_on_commit=False)

    mods = load()
    print("\n── Migration 308 ─────────────────────────────────────────────")
    if mods is None:
        check("the invoice-billing service exists", False, "services/invoice_billing.py is absent")
        return report()
    ib, ddl, sb = mods

    # A pre-308 schema: create_all built the new columns from the ORM, so take
    # them back off, seed a card club with a paid module, then apply 308 three
    # times the way the lifespan re-runs it on every boot.
    async with engine.begin() as conn:
        for stmt in ddl.DOWNGRADE:
            await conn.execute(text(stmt))
        card_org = uuid.uuid4()
        await conn.execute(text(
            "INSERT INTO organisations (id, name, slug, stripe_subscription_id, is_active) VALUES (:i, 'Card CC', 'card-cc', 'sub_1', true)"
        ), {"i": card_org})
        await conn.execute(text(
            "INSERT INTO org_module_subscriptions (id, organisation_id, module_key, status, renewal_date) "
            "VALUES (gen_random_uuid(), :i, 'select', 'active', CURRENT_DATE - 3)"
        ), {"i": card_org})
        for _ in range(3):
            for stmt in ddl.STATEMENTS:
                await conn.execute(text(stmt))
        row = (await conn.execute(text(
            "SELECT o.billing_method, s.billing_source, o.invoice_billing_enabled FROM organisations o "
            "JOIN org_module_subscriptions s ON s.organisation_id = o.id WHERE o.id = :i"
        ), {"i": card_org})).first()
    check("308 applies three times over a populated table", True)
    check("an existing club defaults to paying by card", row and row[0] == "card", str(row))
    check("a card club's paid module is stamped as Stripe-billed", row and row[1] == "stripe", str(row))
    check("an existing club is NOT offered invoicing until a Super Admin switches it on", row and row[2] is False, str(row))

    fake = FakeStripe()
    provider = FakeProvider()
    from app.services import email_service, stripe_client
    for name in ("ensure_customer_for_org", "ensure_invoice_discount_coupon", "create_one_off_invoice",
                 "void_invoice", "retrieve_invoice"):
        setattr(stripe_client, name, getattr(fake, name))
    email_service.get_email_provider = lambda: provider
    email_service.email_is_live = lambda: True
    crm_calls = []
    sb._sync_crm = lambda org_id, crm_trigger=None, won_module_keys=None: crm_calls.append((org_id, crm_trigger, won_module_keys))

    print("\n── Dates ─────────────────────────────────────────────────────")
    d = date(2027, 10, 15)
    due = ib.due_by(d).astimezone(ib.PERTH)
    check("a period's invoice is due at 11:59:59pm Perth the day before it ends",
          (due.date(), due.hour, due.minute, due.second) == (date(2027, 10, 14), 23, 59, 59), str(due))
    check("29 February renews on 28 February", ib.add_years(date(2028, 2, 29), 1) == date(2029, 2, 28))

    now = datetime.now(timezone.utc)
    async with Session() as db:
        org_id, users = await make_club(db, "Invoice CC", now=now)
        primary, second, member = users[("club_admin", True)], users[("club_admin", False)], users[("club_member", False)]
        coupon = DiscountCoupon(id=uuid.uuid4(), code="TENOFF", display_name="Ten percent", discount_type="percent",
                                discount_value=10, stackable_with_bundle=True, duration_mode="once", active=True)
        forever = DiscountCoupon(id=uuid.uuid4(), code="LOYAL", display_name="Loyal club", discount_type="amount",
                                 discount_value=50, stackable_with_bundle=True, duration_mode="forever", active=True)
        db.add_all([coupon, forever])
        await db.commit()

        print("\n── The first invoice is priced like the card checkout ─────────")
        org = await fresh(db, org_id)
        plan = await ib.plan_invoice(db, org, ["select", "socials", "iq"], now=now)
        trial_end = (now + timedelta(days=10)).astimezone(ib.PERTH).date()
        check("a first invoice is kind 'initial'", plan["kind"] == "initial", plan["kind"])
        check("Core is priced in automatically", "core" in plan["billing_keys"], str(plan["billing_keys"]))
        check("the subtotal is Core + three modules at list price ($946)", plan["subtotal_cents"] == 94600,
              str(plan["subtotal_cents"]))
        check("the three-module bundle discount comes off ($97)", plan["bundle_discount_cents"] == 9700,
              str(plan["bundle_discount_cents"]))
        check("the total ex GST is $849", plan["total_cents"] == 84900, str(plan["total_cents"]))
        check("the year starts when the trial ends, so paying early costs no trial",
              plan["service_start_date"] == trial_end, f"{plan['service_start_date']} vs {trial_end}")
        check("and runs twelve months", plan["service_end_date"] == ib.add_years(trial_end, 1))
        check("it is due before the trial ends", abs((plan["due_at"] - (now + timedelta(days=10))).total_seconds()) < 5)

        withcode = await ib.plan_invoice(db, org, ["select", "socials", "iq"], "tenoff", now=now)
        check("a stacking code comes off after the bundle (10% of $849 = $84.90)",
              withcode["coupon_discount_cents"] == 8490, str(withcode["coupon_discount_cents"]))
        check("so the invoice total is $764.10", withcode["total_cents"] == 76410, str(withcode["total_cents"]))
        try:
            await ib.plan_invoice(db, org, ["select"], "NOPE", now=now)
            check("an unknown code is refused", False, "no error")
        except ib.InvoiceBillingError as e:
            check("an unknown code is refused", e.status == 422, str(e))

        print("\n── Asking for it, as a club admin who is not the primary ─────")
        from app.routers import billing as billing_router
        body = billing_router.InvoiceRequestIn(module_keys=["select", "socials"], coupon_code="TENOFF")
        try:
            await billing_router.request_invoice(body, current_user=member, club=org, db=db)
            check("a club member (not an admin) cannot ask for an invoice", False, "allowed")
        except Exception as e:
            check("a club member (not an admin) cannot ask for an invoice", getattr(e, "status_code", None) == 403, str(e))
        res = await billing_router.request_invoice(body, current_user=second, club=org, db=db)
        first_id = res["invoice"]["id"]
        created = fake.created[-1]
        check("a non-primary club admin can ask for one", res["invoice"]["status"] == "open", str(res))
        check("the invoice is emailed to the PRIMARY club admin, not whoever asked",
              provider.sent and provider.sent[-1].to_email == "primary@club.test",
              provider.sent[-1].to_email if provider.sent else "nothing sent")
        msg = provider.sent[-1]
        row = await db.get(BillingInvoice, uuid.UUID(first_id))
        check("the email carries the pay link", row.pay_token and f"/api/public/billing/pay/{row.pay_token}" in msg.html)
        check("and the PDF", "in_1.pdf" in msg.html)
        check("and the invoice number and GST-inclusive total",
              "BC-1001" in msg.subject and "$" in msg.html and "including GST" in msg.html, msg.subject)
        # Core + two modules: $697, the two-module bundle takes $48, and 10% of
        # the remaining $649 is $64.90 — bundle first, then the code.
        check("Stripe was asked for ONE discount of bundle + code ($48 + $64.90)",
              fake.coupons[-1] == {"bundle": 48.0, "code": "TENOFF", "coupon": 64.9, "total": 112.9}, str(fake.coupons[-1]))
        check("the Stripe invoice is due before the trial ends",
              abs((created["due_at"] - (now + timedelta(days=10))).total_seconds()) < 5)
        check("the metadata carries what paying it grants",
              created["metadata"]["billing_method"] == "invoice"
              and created["metadata"]["billing_keys"] == "core,select,socials", str(created["metadata"]))
        check("the row records who it went to and when", row.sent_to_email == "primary@club.test" and row.emailed_at)
        redemption = (await db.execute(select(DiscountCouponRedemption).where(
            DiscountCouponRedemption.organisation_id == org_id))).scalar_one()
        check("the code is held for the club while the invoice is unpaid", redemption.status == "pending")
        org = await fresh(db, org_id)
        check("raising an invoice grants nothing by itself",
              status_of(org, "select").status == "trial", status_of(org, "select").status)

        print("\n── Changing their mind replaces the invoice ──────────────────")
        res2 = await billing_router.request_invoice(
            billing_router.InvoiceRequestIn(module_keys=["select", "socials", "iq"]), current_user=primary, club=org, db=db)
        old = await db.get(BillingInvoice, uuid.UUID(first_id), populate_existing=True)
        check("the first invoice is voided so it can never be paid as well", old.status == "void" and "in_1" in fake.voided)
        redemption = await db.get(DiscountCouponRedemption, redemption.id, populate_existing=True)
        check("and its held code is handed back", redemption.status == "revoked", redemption.status)
        second_id = res2["invoice"]["id"]
        second_stripe = (await db.get(BillingInvoice, uuid.UUID(second_id))).stripe_invoice_id

        print("\n── Card checkout is closed to an invoice club ────────────────")
        try:
            await billing_router.create_checkout_session(
                billing_router.QuoteIn(module_keys=["admin"]), current_user=users[("club_admin", True)], club=org, db=db)
            check("the card checkout refuses an invoice club", False, "allowed")
        except Exception as e:
            check("the card checkout refuses an invoice club", getattr(e, "status_code", None) == 409, str(e))
        q = await billing_router.get_quote(billing_router.QuoteIn(module_keys=["select"]), club=org, db=db)
        check("the Account page's preview is the invoice's own figures", q.get("mode") == "invoice", str(q.get("mode")))

        print("\n── Paying it is what grants the modules ──────────────────────")
        paid_at = now + timedelta(days=2)
        inv = fake.paid(second_stripe, paid_at)
        await sb.handle_invoice_paid(db, inv)  # routed off the subscription path by its metadata
        org = await fresh(db, org_id)
        want_renewal = ib.add_years(trial_end, 1)
        check("every invoiced module is subscribed",
              all(status_of(org, k).status == "active" for k in ("core", "select", "socials", "iq")),
              str({k: status_of(org, k).status for k in ("core", "select", "socials", "iq")}))
        check("paid through twelve months from the end of the trial",
              status_of(org, "select").renewal_date == want_renewal,
              f"{status_of(org, 'select').renewal_date} vs {want_renewal}")
        check("and marked as invoice-billed", status_of(org, "select").billing_source == "invoice")
        check("a module that was not on the invoice is untouched", status_of(org, "fantasy").status == "trial")
        prow = (await db.execute(select(BillingInvoice).where(BillingInvoice.stripe_invoice_id == second_stripe))).scalar_one()
        check("the invoice reads paid", prow.status == "paid")
        check("and earns commission as a first subscribe would", prow.billing_reason == "subscription_create",
              str(prow.billing_reason))
        check("the CRM deal moves to Won with what was bought",
              crm_calls and crm_calls[-1][1] == "subscription_won" and set(crm_calls[-1][2]) == {"core", "select", "socials", "iq"},
              str(crm_calls[-1:] if crm_calls else None))
        await sb.handle_invoice_paid(db, inv)
        org = await fresh(db, org_id)
        check("replaying the webhook changes nothing", status_of(org, "select").renewal_date == want_renewal)

        print("\n── Adding a module part way through the year ──────────────────")
        org = await fresh(db, org_id)
        # On the period's very first day an add-on is a full year, which is
        # right — so price it 100 days in, after the trial has run out.
        later = now + timedelta(days=100)
        full_year = await ib.plan_invoice(db, org, ["admin"], now=now)
        check("on the period's first day an add-on costs a full year",
              full_year["total_cents"] == 14900, str(full_year["total_cents"]))
        addon = await ib.plan_invoice(db, org, ["admin"], now=later)
        left = (want_renewal - ib.perth_today(later)).days
        of = (want_renewal - ib.add_years(want_renewal, -1)).days
        check("it is an add-on", addon["kind"] == "addon", addon["kind"])
        check("with no bundle discount", addon["bundle_discount_cents"] == 0)
        check("100 days in, it is prorated to the club's renewal date",
              addon["service_end_date"] == want_renewal and addon["total_cents"] == round(14900 * left / of)
              and addon["prorated"] == {"days": left, "of_days": of}, f"{addon['total_cents']} {addon['prorated']}")
        try:
            await ib.plan_invoice(db, org, ["admin"], "LOYAL", now=later)
            check("a code is refused on an add-on", False, "allowed")
        except ib.InvoiceBillingError:
            check("a code is refused on an add-on", True)
        try:
            await ib.plan_invoice(db, org, ["select"], now=now)
            check("a module already on the period is refused", False, "allowed")
        except ib.InvoiceBillingError as e:
            check("a module already on the period is refused", e.status == 409, str(e))

        print("\n── The renewal invoice, 14 days out ──────────────────────────")
        db.add(DiscountCouponRedemption(id=uuid.uuid4(), coupon_id=forever.id, organisation_id=org_id,
                                        applied_via="super_admin", status="active"))
        await db.commit()
        before = len(fake.created)
        early = datetime.combine(want_renewal - timedelta(days=15), datetime.min.time(), tzinfo=ib.PERTH).replace(hour=9)
        stats = await ib.issue_due_renewals(db, now=early)
        check("nothing goes out 15 days before", len(fake.created) == before and stats["issued"] == 0, str(stats))
        at14 = datetime.combine(want_renewal - timedelta(days=14), datetime.min.time(), tzinfo=ib.PERTH).replace(hour=8)
        sent_before = len(provider.sent)
        stats = await ib.issue_due_renewals(db, now=at14)
        check("it goes out 14 days before", stats["issued"] == 1 and len(fake.created) == before + 1, str(stats))
        ren = fake.created[-1]
        rrow = (await db.execute(select(BillingInvoice).where(BillingInvoice.stripe_invoice_id == ren["id"]))).scalar_one()
        check("for every module the club still holds",
              set(ren["metadata"]["billing_keys"].split(",")) == {"core", "iq", "select", "socials"},
              ren["metadata"]["billing_keys"])
        check("at full price, the bundle being a first-subscribe reward",
              sum(ln["amount_cents"] for ln in ren["lines"]) == 94600 and rrow.bundle_discount_cents == 0)
        check("the 'once' code is not reapplied, the 'forever' one is",
              rrow.coupon_code == "LOYAL" and rrow.coupon_discount_cents == 5000, f"{rrow.coupon_code} {rrow.coupon_discount_cents}")
        check("due by the end of the day before the period ends", rrow.due_at == ib.due_by(want_renewal))
        check("it covers the next twelve months",
              rrow.service_start_date == want_renewal and rrow.service_end_date == ib.add_years(want_renewal, 1))
        check("and it is emailed to the primary admin", len(provider.sent) == sent_before + 1
              and "Renewal invoice" in provider.sent[-1].subject, provider.sent[-1].subject if provider.sent else "")
        stats = await ib.issue_due_renewals(db, now=at14 + timedelta(days=1))
        check("the next day's run raises nothing twice", stats["issued"] == 0 and len(fake.created) == before + 1, str(stats))
        check("the renewal is keyed so a retried run gets the same Stripe invoice",
              ren["idempotency_key"] == f"bc-renewal-{org_id}-{want_renewal.isoformat()}", str(ren["idempotency_key"]))

        print("\n── Unpaid when the period ends ───────────────────────────────")
        day_before = datetime.combine(want_renewal - timedelta(days=1), datetime.min.time(), tzinfo=ib.PERTH).replace(hour=23)
        await ib.lapse_unpaid(db, now=day_before)
        org = await fresh(db, org_id)
        check("on the last day the modules are still on", status_of(org, "select").status == "active")
        on_day = datetime.combine(want_renewal, datetime.min.time(), tzinfo=ib.PERTH).replace(minute=15)
        lapsed = await ib.lapse_unpaid(db, now=on_day)
        org = await fresh(db, org_id)
        check("when the period ends unpaid, they are paused", str(org_id) in lapsed
              and all(status_of(org, k).status == "paused" for k in ("core", "select", "socials", "iq")),
              str({k: status_of(org, k).status for k in ("core", "select", "socials", "iq")}))
        check("a module that was never invoiced is left alone", status_of(org, "fantasy").status == "trial")
        rrow = await db.get(BillingInvoice, rrow.id, populate_existing=True)
        check("the renewal invoice stays open and payable", rrow.status == "open")
        late = fake.paid(ren["id"], on_day + timedelta(days=3))
        await sb.handle_invoice_paid(db, late)
        org = await fresh(db, org_id)
        check("paying late switches them back on for the rest of that period",
              status_of(org, "select").status == "active"
              and status_of(org, "select").renewal_date == ib.add_years(want_renewal, 1),
              f"{status_of(org, 'select').status} {status_of(org, 'select').renewal_date}")
        rrow = (await db.execute(select(BillingInvoice).where(BillingInvoice.stripe_invoice_id == ren["id"]))).scalar_one()
        check("a renewal earns no commission", rrow.billing_reason == "subscription_cycle", str(rrow.billing_reason))

        print("\n── What the job must never touch ─────────────────────────────")
        card_id, _ = await make_club(db, "Card Two", billing_method="card", primary_email="c2@club.test", stripe_sub="sub_2", enabled=True)
        hand_id, _ = await make_club(db, "Hand Granted", billing_method="invoice", primary_email="hg@club.test")
        for oid, source in ((card_id, "stripe"), (hand_id, None)):
            o = await fresh(db, oid)
            r = status_of(o, "select")
            r.status, r.renewal_date, r.billing_source = "active", date.today() - timedelta(days=2), source
        await db.commit()
        await ib.lapse_unpaid(db, now=datetime.now(timezone.utc))
        check("a card-billed module past its date is left to Stripe",
              status_of(await fresh(db, card_id), "select").status == "active")
        check("a hand-granted module past its date is left alone",
              status_of(await fresh(db, hand_id), "select").status == "active")

        switched_id, _ = await make_club(db, "Switched Back", billing_method="card", primary_email="sw@club.test")
        o = await fresh(db, switched_id)
        soon = date.today() + timedelta(days=5)
        for k in ("core", "select"):
            r = status_of(o, k)
            r.status, r.renewal_date, r.billing_source = "active", soon, "invoice"
        await db.commit()
        n0 = len(fake.created)
        await ib.issue_due_renewals(db, now=datetime.now(timezone.utc))
        check("a club that has switched back to card is not invoiced for its renewal", len(fake.created) == n0)

        print("\n── Setting it, and the refusals ──────────────────────────────")
        card = await fresh(db, card_id)
        try:
            await ib.set_billing_method(db, card, "invoice")
            check("a club on a live card subscription cannot switch to invoice", False, "allowed")
        except ib.InvoiceBillingError as e:
            check("a club on a live card subscription cannot switch to invoice", e.status == 409, str(e))
        nopri_id, nousers = await make_club(db, "No Primary", primary_email=None)
        n0 = len(fake.created)
        try:
            p = await ib.plan_invoice(db, await fresh(db, nopri_id), ["select"], now=now)
            await ib.issue_invoice(db, await fresh(db, nopri_id), p)
            check("no primary admin with an email: refused before Stripe is touched", False, "issued")
        except ib.InvoiceBillingError as e:
            check("no primary admin with an email: refused before Stripe is touched",
                  e.status == 409 and len(fake.created) == n0, str(e))

        email_service.get_email_provider = lambda: ConsoleProvider()
        quiet_id, _ = await make_club(db, "Quiet Server", primary_email="q@club.test")
        p = await ib.plan_invoice(db, await fresh(db, quiet_id), ["select"], now=now)
        qrow = await ib.issue_invoice(db, await fresh(db, quiet_id), p)
        check("with no email provider the invoice is raised but NOT reported as emailed",
              qrow.emailed_at is None and "isn't configured" in (qrow.email_error or ""), str(qrow.email_error))
        email_service.get_email_provider = lambda: provider

        print("\n── A Super Admin, on the club's behalf ───────────────────────")
        sa = User(id=uuid.uuid4(), username=f"super-{uuid.uuid4().hex[:4]}", email="sa@better.test")
        db.add(sa)
        await db.flush()
        db.add(ClubMembership(club_id=card_id, user_id=sa.id, role="super_admin"))
        helped_id, helped_users = await make_club(db, "Helped CC", billing_method="card", primary_email="helped@club.test")
        await db.commit()
        helped = await fresh(db, helped_id)
        check("a new club is not offered invoicing", helped.invoice_billing_enabled is False)
        ov0 = await billing_router.get_invoice_billing(club=helped, db=db)
        check("and the club's own view says so", ov0["invoice_billing_enabled"] is False)
        try:
            await billing_router.set_billing_method(
                billing_router.BillingMethodIn(method="invoice"),
                current_user=helped_users[("club_admin", True)], club=helped, db=db)
            check("the club cannot switch itself to invoice while it is off", False, "allowed")
        except Exception as e:
            check("the club cannot switch itself to invoice while it is off", getattr(e, "status_code", None) == 403, str(e))
        try:
            await billing_router.request_invoice(
                billing_router.InvoiceRequestIn(module_keys=["select"]),
                current_user=helped_users[("club_admin", True)], club=helped, db=db)
            check("nor ask for an invoice", False, "allowed")
        except Exception as e:
            check("nor ask for an invoice", getattr(e, "status_code", None) == 403, str(e))
        n0 = len(fake.created)
        try:
            await billing_router.super_request_invoice(
                str(helped_id), billing_router.InvoiceRequestIn(module_keys=["select"]), current_user=sa, db=db)
            check("a Super Admin must switch invoicing on before raising one", False, "raised")
        except Exception as e:
            check("a Super Admin must switch invoicing on before raising one",
                  getattr(e, "status_code", None) == 409 and len(fake.created) == n0, str(e))
        from app.routers import club_admin as club_admin_router
        payload = await club_admin_router.patch_club(
            str(helped_id), club_admin_router.ClubUpdate(invoice_billing_enabled=True), current_user=sa, db=db)
        check("All Clubs switches it on and reports it", payload.get("invoice_billing_enabled") is True, str(payload.get("invoice_billing_enabled")))
        res = await billing_router.super_request_invoice(
            str(helped_id), billing_router.InvoiceRequestIn(module_keys=["select"]), current_user=sa, db=db)
        helped = await fresh(db, helped_id)
        check("raising one moves the club to invoice billing", helped.billing_method == "invoice")
        check("and emails its primary admin", provider.sent[-1].to_email == "helped@club.test")
        ov = await billing_router.super_get_invoice_billing(str(helped_id), db=db)
        check("the Super Admin view lists the open invoice with a pay link",
              ov["open_invoices"] and ov["open_invoices"][0]["pay_url"], str(ov.get("open_invoices")))
        r2 = await billing_router.super_resend_invoice(str(helped_id), res["invoice"]["id"], db=db)
        check("the Super Admin can resend it", r2["ok"] and r2["to"] == "helped@club.test", str(r2))
        v = await billing_router.super_void_invoice(str(helped_id), res["invoice"]["id"], db=db)
        check("and void it", v["invoice"]["status"] == "void")
        try:
            await billing_router.super_resend_invoice(str(helped_id), res["invoice"]["id"], db=db)
            check("a voided invoice cannot be resent", False, "sent")
        except Exception as e:
            check("a voided invoice cannot be resent", getattr(e, "status_code", None) == 409, str(e))
        try:
            await billing_router.super_resend_invoice(str(card_id), res["invoice"]["id"], db=db)
            check("another club's invoice is not reachable through this one", False, "reached")
        except Exception as e:
            check("another club's invoice is not reachable through this one", getattr(e, "status_code", None) == 404, str(e))

        payload = await club_admin_router.patch_club(
            str(helped_id), club_admin_router.ClubUpdate(invoice_billing_enabled=False), current_user=sa, db=db)
        helped = await fresh(db, helped_id)
        check("switching it off moves an invoice club back to card",
              helped.invoice_billing_enabled is False and helped.billing_method == "card", helped.billing_method)
        o = await fresh(db, helped_id)
        for k in ("core", "select"):
            r = status_of(o, k)
            r.status, r.renewal_date, r.billing_source = "active", date.today() + timedelta(days=5), "invoice"
        o.billing_method = "invoice"   # as if something had left it on invoice with the offer withdrawn
        await db.commit()
        n0 = len(fake.created)
        await ib.issue_due_renewals(db, now=datetime.now(timezone.utc))
        check("a club with invoicing switched off is never sent a renewal invoice", len(fake.created) == n0)

        print("\n── The pay link ──────────────────────────────────────────────")
        from app.routers import public_billing
        p = await ib.plan_invoice(db, await fresh(db, quiet_id), ["select", "iq"], now=now)
        prow2 = await ib.issue_invoice(db, await fresh(db, quiet_id), p)
        r = await public_billing.pay_invoice(prow2.pay_token, db=db)
        check("an open invoice's link goes to Stripe's payment page",
              r.status_code == 303 and r.headers["location"] == fake.invoices[prow2.stripe_invoice_id]["hosted_invoice_url"],
              r.headers.get("location"))
        fake.paid(prow2.stripe_invoice_id, now)
        r = await public_billing.pay_invoice(prow2.pay_token, db=db)
        check("once Stripe says it is paid, the link lands on the Account page instead",
              r.headers["location"].endswith("/admin/account?invoice=paid"), r.headers.get("location"))
        r = await public_billing.pay_invoice("not-a-token", db=db)
        check("an unknown link says so rather than erroring", r.headers["location"].endswith("invoice=not-found"))

        print("\n── The other webhook events ──────────────────────────────────")
        ev_id, _ = await make_club(db, "Events CC", primary_email="ev@club.test")
        p = await ib.plan_invoice(db, await fresh(db, ev_id), ["select"], "LOYAL", now=now)
        erow = await ib.issue_invoice(db, await fresh(db, ev_id), p)
        failed = dict(fake.invoices[erow.stripe_invoice_id])
        await sb.handle_invoice_payment_failed(db, failed)
        o = await fresh(db, ev_id)
        check("a failed payment changes no module", status_of(o, "select").status == "trial")
        erow = await db.get(BillingInvoice, erow.id, populate_existing=True)
        check("and the invoice stays open to pay", erow.status == "open")
        voided = dict(fake.invoices[erow.stripe_invoice_id], status="void")
        await sb.handle_invoice_voided(db, voided)
        erow = await db.get(BillingInvoice, erow.id, populate_existing=True)
        red = await db.get(DiscountCouponRedemption, erow.coupon_redemption_id, populate_existing=True)
        check("a voided invoice stops offering its pay link", erow.status == "void"
              and ib.invoice_out(erow)["pay_url"] is None)
        check("and hands its held code back", red.status == "revoked", red.status)
        check("a card subscription's invoice is not handled as an invoice-billing one",
              not ib.is_invoice_billing({"metadata": {}, "subscription": "sub_1"}))

        print("\n── A module cancelled before its renewal is paid ─────────────")
        rm_id, _ = await make_club(db, "Removed CC", primary_email="rm@club.test")
        p = await ib.plan_invoice(db, await fresh(db, rm_id), ["select", "socials"], now=now)
        r0 = await ib.issue_invoice(db, await fresh(db, rm_id), p)
        await sb.handle_invoice_paid(db, fake.paid(r0.stripe_invoice_id, now))
        o = await fresh(db, rm_id)
        rdate = status_of(o, "select").renewal_date
        rplan = await ib.plan_renewal(db, o, now=now)
        r1 = await ib.issue_invoice(db, o, rplan)
        o = await fresh(db, rm_id)
        from app.services import module_subscriptions as ms
        ms.remove_billing(o, "socials")
        await db.commit()
        await sb.handle_invoice_paid(db, fake.paid(r1.stripe_invoice_id, now))
        o = await fresh(db, rm_id)
        check("paying the renewal renews what is still held",
              status_of(o, "select").renewal_date == ib.add_years(rdate, 1))
        check("and does not switch back on a module the club cancelled", status_of(o, "socials") is None)

    await engine.dispose()
    return report()


def report() -> int:
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print(f"  FAIL  {f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
