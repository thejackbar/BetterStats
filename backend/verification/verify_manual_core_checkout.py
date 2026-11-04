"""A club whose BetterStats a Super Admin set Active by hand (it paid by bank
transfer, so no Stripe subscription carries it) must be able to buy ONE more
module without being asked to buy BetterStats again.

Reported on Kalamunda Cricket Club: Core showed "Subscribed" on the Account
page, but ticking BetterSocials quoted BetterStats $399 + BetterSocials $149 and
the checkout would have opened a second subscription with a Core line.

Runs the shipped route bodies, the Stripe Checkout builder and the webhook
handler against a real Postgres. Only the Stripe network calls are stubbed, and
the stub records exactly what would have been sent.

    python -m verification.verify_manual_core_checkout
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
    "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/bs_manual_core",
)
os.environ["DATABASE_URL"] = DB_URL

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from app.models.db import Base, ClubMembership, Organisation, OrgModuleSubscription, User  # noqa: E402

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} — {detail}")
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  ({detail})'}")


RENEWS = date(2027, 7, 10)
KEYS = ("core", "select", "socials", "iq", "fees", "comms", "merch", "crm", "fantasy")


async def make_club(db, name, *, core, billing_method="card", stripe_sub=None, stripe_keys=(), enabled=False):
    """core: 'manual' (Super Admin set Active, billing_source NULL), 'stripe'
    (paid through the Stripe subscription), or 'trial'."""
    now = datetime.now(timezone.utc)
    extra = {"invoice_billing_enabled": True} if enabled else {}
    org = Organisation(id=uuid.uuid4(), name=name, slug=name.lower().replace(" ", "-"),
                       billing_method=billing_method, stripe_subscription_id=stripe_sub, **extra)
    db.add(org)
    await db.flush()
    for key in KEYS:
        row = OrgModuleSubscription(organisation_id=org.id, module_key=key, status="trial",
                                    trial_started_at=now - timedelta(days=30),
                                    trial_ends_at=now - timedelta(days=2))  # an expired trial
        if key == "core" and core in ("manual", "stripe"):
            row.status, row.renewal_date = "active", RENEWS
            row.billing_source = "stripe" if core == "stripe" else None
        if key == "core" and core == "trial":
            row.trial_ends_at = now + timedelta(days=10)
        if key in stripe_keys:
            row.status, row.renewal_date, row.billing_source = "active", RENEWS, "stripe"
        db.add(row)
    u = User(id=uuid.uuid4(), username=f"p-{uuid.uuid4().hex[:6]}", email=f"{uuid.uuid4().hex[:6]}@club.test",
             display_name="Pat Primary")
    db.add(u)
    await db.flush()
    db.add(ClubMembership(club_id=org.id, user_id=u.id, role="club_admin", is_primary_admin=True))
    await db.commit()
    return org.id, u


async def fresh(db, org_id):
    return await db.get(Organisation, org_id, options=[selectinload(Organisation.module_subscriptions)],
                        populate_existing=True)


def row_of(org, key):
    return next((r for r in org.module_subscriptions if r.module_key == key), None)


def names(quote):
    return [li["name"] for li in quote["line_items"]]


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

    from app.routers import billing as br
    from app.services import invoice_billing, stripe_billing, stripe_client

    # Stripe network edge only.
    sessions: list[dict] = []
    addons: list[dict] = []

    class _Sess(dict):
        pass

    async def create_session(**params):
        sessions.append(params)
        return _Sess(url="https://checkout.stripe.test/s_1")

    async def _customer(**kw):
        return "cus_test"

    async def _exists(cid):
        return True

    async def add_modules(db, sub_id, existing, new):
        addons.append({"existing": sorted(existing), "new": sorted(new)})
        return {"current_period_end": int(datetime(2027, 11, 4, tzinfo=timezone.utc).timestamp())}

    async def retrieve(sub_id):
        return {"current_period_end": int(datetime(2027, 11, 4, tzinfo=timezone.utc).timestamp())}

    stripe_client._require_configured = lambda: None
    stripe_client._ensure_customer = _customer
    stripe_client._customer_exists = _exists
    stripe_client.stripe.checkout.Session.create_async = create_session
    stripe_client.add_modules_to_subscription = add_modules
    stripe_client.retrieve_subscription = retrieve
    stripe_billing._sync_crm = lambda *a, **k: None
    br._sync_club_to_crm = None  # not reached on the paths below

    async def flag_on(db, org):
        return True
    from app.services import platform_settings
    platform_settings.billing_checkout_enabled_for_org = flag_on

    body = lambda *k: br.QuoteIn(module_keys=list(k))  # noqa: E731

    print("\n── Kalamunda: Core set Active by hand, no Stripe subscription ─")
    async with Session() as db:
        oid, user = await make_club(db, "Kalamunda CC", core="manual")
        club = await fresh(db, oid)

        q = await br.get_quote(body("socials"), club=club, db=db)
        check("the quote lists BetterSocials", any("Socials" in n for n in names(q)), str(names(q)))
        check("the quote does NOT list BetterStats", not any(n == "BetterStats" for n in names(q)), str(names(q)))
        check("the total is BetterSocials alone, $149", q.get("total") == 149, str(q.get("total")))
        check("the quote says Core was left out on purpose", q.get("core_included") is False, str(q.get("core_included")))

        q2 = await br.get_quote(body("socials", "select"), club=club, db=db)
        check("two modules together carry no bundle discount (the club already subscribed)",
              q2.get("discount") == 0 and q2.get("total") == 298, f"{q2.get('discount')} / {q2.get('total')}")

        sessions.clear()
        res = await br.create_checkout_session(body("socials"), current_user=user, club=club, db=db)
        check("checkout still redirects to Stripe's page", bool(res.get("url")), str(res))
        p = sessions[-1] if sessions else {}
        li_names = [li["price_data"]["product_data"]["name"] for li in p.get("line_items", [])]
        check("the Checkout Session has exactly one line, BetterSocials",
              len(li_names) == 1 and "Socials" in li_names[0], str(li_names))
        check("no BetterStats line is sent to Stripe", not any("BetterStats" in n for n in li_names), str(li_names))
        check("the subscription's billing_keys carry only socials",
              (p.get("metadata") or {}).get("billing_keys") == "socials", str((p.get("metadata") or {})))
        check("no bundle discount is attached", not p.get("discounts"), str(p.get("discounts")))

        try:
            await br.create_checkout_session(body("core"), current_user=user, club=club, db=db)
            check("ticking the already-subscribed BetterStats is refused", False, "allowed")
        except Exception as e:
            check("ticking the already-subscribed BetterStats is refused", getattr(e, "status_code", None) == 409, str(e))

        print("\n── …and paying for it leaves the hand-set Core alone ─────────")
        await stripe_billing.handle_checkout_completed(db, {
            "mode": "subscription", "client_reference_id": str(oid), "customer": "cus_test",
            "subscription": "sub_new", "metadata": {"org_id": str(oid), "billing_keys": "socials"},
        })
        org = await fresh(db, oid)
        check("BetterSocials is now active, billed through Stripe",
              row_of(org, "socials").status == "active" and row_of(org, "socials").billing_source == "stripe")
        check("BetterStats keeps its own renewal date", row_of(org, "core").renewal_date == RENEWS,
              str(row_of(org, "core").renewal_date))
        check("BetterStats is still not marked as Stripe-billed", row_of(org, "core").billing_source is None,
              str(row_of(org, "core").billing_source))
        check("the club now holds the new Stripe subscription", org.stripe_subscription_id == "sub_new")

        print("\n── A later add-on must not put the hand-set Core on the subscription ──")
        addons.clear()
        res = await br.create_checkout_session(body("select"), current_user=user, club=org, db=db)
        check("the second module is added to the existing subscription", res.get("added") is True, str(res))
        a = addons[-1] if addons else {}
        check("the Stripe subscription's existing keys are only what Stripe carries (socials)",
              a.get("existing") == ["socials"], str(a))
        check("the new key is select", a.get("new") == ["select"], str(a))

    print("\n── Controls: the same pages for clubs that really owe Core ────")
    async with Session() as db:
        oid, user = await make_club(db, "Trial CC", core="trial")
        club = await fresh(db, oid)
        q = await br.get_quote(body("socials"), club=club, db=db)
        check("a club still in its Core trial IS quoted BetterStats", any(n == "BetterStats" for n in names(q)), str(names(q)))
        check("…at $399 + $149 = $548", q.get("total") == 548, str(q.get("total")))
        sessions.clear()
        await br.create_checkout_session(body("socials"), current_user=user, club=club, db=db)
        li_names = [li["price_data"]["product_data"]["name"] for li in sessions[-1].get("line_items", [])]
        check("its Checkout Session carries both lines", len(li_names) == 2 and any("BetterStats" in n for n in li_names), str(li_names))

        oid, user = await make_club(db, "Expired CC", core="none")
        club = await fresh(db, oid)
        q = await br.get_quote(body("socials"), club=club, db=db)
        check("a club whose Core trial expired is quoted BetterStats too", any(n == "BetterStats" for n in names(q)), str(names(q)))

        oid, user = await make_club(db, "Stripe CC", core="stripe", stripe_sub="sub_old", stripe_keys=("select",))
        club = await fresh(db, oid)
        addons.clear()
        await br.create_checkout_session(body("socials"), current_user=user, club=club, db=db)
        a = addons[-1] if addons else {}
        check("a Core genuinely on the Stripe subscription stays in its billing_keys",
              a.get("existing") == ["core", "select"], str(a))

    print("\n── Pay-by-invoice clubs follow the same rule ──────────────────")
    async with Session() as db:
        oid, user = await make_club(db, "Invoice Manual CC", core="manual", billing_method="invoice", enabled=True)
        club = await fresh(db, oid)
        plan = await invoice_billing.plan_invoice(db, club, ["socials"])
        check("an invoice for BetterSocials does not include BetterStats",
              "core" not in plan["billing_keys"] and plan["billing_keys"] == ["socials"], str(plan["billing_keys"]))
        check("and totals $149", plan["total_cents"] == 14900, str(plan["total_cents"]))
        oid, user = await make_club(db, "Invoice Trial CC", core="trial", billing_method="invoice", enabled=True)
        club = await fresh(db, oid)
        plan = await invoice_billing.plan_invoice(db, club, ["socials"])
        check("a club still in its Core trial is invoiced Core as before", "core" in plan["billing_keys"], str(plan["billing_keys"]))

    return report()


def report() -> int:
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print("  FAILED:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
