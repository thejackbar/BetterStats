"""Clubs that pay for modules outside Stripe (a bank transfer, then a Super Admin
sets the module Active) and then buy more.

Reported on Kalamunda Cricket Club: BetterStats showed "Subscribed" but ticking
BetterSocials quoted BetterStats again ($548). Asked for, on top of that fix:
  1. what the club adds is PRORATED to its BetterStats renewal date;
  2. that holds when the club first took several modules by hand;
  3. when a Super Admin sets the newly bought modules Active by hand, each is
     prorated onto the BetterStats renewal date too, so the club renews as one.

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


def _add_years(d: date, n: int) -> date:
    try:
        return d.replace(year=d.year + n)
    except ValueError:
        return d.replace(year=d.year + n, day=28)


def _perth_today() -> date:
    from zoneinfo import ZoneInfo
    return datetime.now(timezone.utc).astimezone(ZoneInfo("Australia/Perth")).date()


# BetterStats renews 200 days from today, so every figure below is checkable by hand.
TODAY = _perth_today()
RENEWS = TODAY + timedelta(days=200)
OF_DAYS = (RENEWS - _add_years(RENEWS, -1)).days
KEYS = ("core", "select", "socials", "iq", "fees", "comms", "merch", "crm", "fantasy")


def prorated(price: int) -> float:
    return round(price * 100 * 200 / OF_DAYS) / 100


async def make_club(db, name, *, core, renews=RENEWS, billing_method="card", stripe_sub=None,
                    stripe_keys=(), manual_keys=(), enabled=False):
    """core: 'manual' (Super Admin set Active, billing_source NULL), 'stripe',
    'trial' or 'none' (an expired trial)."""
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
            row.status, row.renewal_date = "active", renews
            row.billing_source = "stripe" if core == "stripe" else None
        if key == "core" and core == "trial":
            row.trial_ends_at = now + timedelta(days=10)
        if key in manual_keys:
            row.status, row.renewal_date = "active", renews
        if key in stripe_keys:
            row.status, row.renewal_date, row.billing_source = "active", renews, "stripe"
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
    from app.routers import club_admin as ca
    from app.services import invoice_billing, stripe_billing, stripe_client

    # Stripe network edge only.
    sessions: list[dict] = []
    addons: list[dict] = []
    anchor_epoch = {"v": None}

    async def create_session(**params):
        sessions.append(params)
        return {"url": "https://checkout.stripe.test/s_1"}

    async def _customer(**kw):
        return "cus_test"

    async def _exists(cid):
        return True

    async def add_modules(db, sub_id, existing, new):
        addons.append({"existing": sorted(existing), "new": sorted(new)})
        return {"current_period_end": int(datetime(2027, 11, 4, tzinfo=timezone.utc).timestamp())}

    async def retrieve(sub_id):
        return {"current_period_end": anchor_epoch["v"]}

    stripe_client._require_configured = lambda: None
    stripe_client._ensure_customer = _customer
    stripe_client._customer_exists = _exists
    stripe_client.stripe.checkout.Session.create_async = create_session
    stripe_client.add_modules_to_subscription = add_modules
    stripe_client.retrieve_subscription = retrieve
    stripe_billing._sync_crm = lambda *a, **k: None

    async def flag_on(db, org):
        return True
    from app.services import platform_settings
    platform_settings.billing_checkout_enabled_for_org = flag_on

    body = lambda *k, code=None: br.QuoteIn(module_keys=list(k), coupon_code=code)  # noqa: E731

    print("\n── Kalamunda: Core set Active by hand, renews in 200 days ─────")
    async with Session() as db:
        oid, user = await make_club(db, "Kalamunda CC", core="manual")
        club = await fresh(db, oid)

        q = await br.get_quote(body("socials"), club=club, db=db)
        check("the quote lists BetterSocials and not BetterStats",
              any("Socials" in n for n in names(q)) and "BetterStats" not in names(q), str(names(q)))
        check(f"BetterSocials is prorated to the BetterStats renewal (${prorated(149):.2f}, not $149 or $548)",
              q.get("total") == prorated(149), str(q.get("total")))
        check("the quote reports the days and the date it prorates to",
              (q.get("prorated") or {}).get("days") == 200 and (q.get("prorated") or {}).get("renewal_date") == RENEWS.isoformat(),
              str(q.get("prorated")))
        check("the line still shows the full annual price it renews at", q["line_items"][0].get("full_price") == 149,
              str(q["line_items"][0]))
        check("Core is left out on purpose", q.get("core_included") is False, str(q.get("core_included")))

        q2 = await br.get_quote(body("socials", "iq"), club=club, db=db)
        check("two modules are each prorated, with no bundle discount",
              q2.get("discount") == 0 and round(q2.get("total", 0), 2) == round(prorated(149) + prorated(249), 2),
              f"{q2.get('discount')} / {q2.get('total')}")

        try:
            await br.get_quote(body("socials", code="TENOFF"), club=club, db=db)
            check("a discount code is refused on a part-year add-on", False, "allowed")
        except Exception as e:
            check("a discount code is refused on a part-year add-on", getattr(e, "status_code", None) == 422, str(e))

        sessions.clear()
        res = await br.create_checkout_session(body("socials"), current_user=user, club=club, db=db)
        check("checkout still redirects to Stripe's page", bool(res.get("url")), str(res))
        p = sessions[-1] if sessions else {}
        li_names = [li["price_data"]["product_data"]["name"] for li in p.get("line_items", [])]
        check("the Checkout Session has exactly one line, BetterSocials, and no BetterStats line",
              len(li_names) == 1 and "Socials" in li_names[0], str(li_names))
        check("that line is the full annual price (Stripe does the proration)",
              p["line_items"][0]["price_data"]["unit_amount"] == 14900 if p.get("line_items") else False)
        sd = p.get("subscription_data") or {}
        want = int(datetime.combine(RENEWS, datetime.min.time(), tzinfo=timezone.utc).timestamp())
        check("the subscription's billing cycle is anchored on the BetterStats renewal date",
              sd.get("billing_cycle_anchor") == want, f"{sd.get('billing_cycle_anchor')} vs {want}")
        check("the part-year up to the anchor is prorated", sd.get("proration_behavior") == "create_prorations",
              str(sd.get("proration_behavior")))
        check("the subscription's billing_keys carry only socials",
              (p.get("metadata") or {}).get("billing_keys") == "socials", str((p.get("metadata") or {})))
        check("no bundle discount is attached", not p.get("discounts"), str(p.get("discounts")))
        try:
            await br.create_checkout_session(body("core"), current_user=user, club=club, db=db)
            check("ticking the already-subscribed BetterStats is refused", False, "allowed")
        except Exception as e:
            check("ticking the already-subscribed BetterStats is refused", getattr(e, "status_code", None) == 409, str(e))

        print("\n── …and paying for it lines the module up, leaves Core alone ──")
        anchor_epoch["v"] = want
        await stripe_billing.handle_checkout_completed(db, {
            "mode": "subscription", "client_reference_id": str(oid), "customer": "cus_test",
            "subscription": "sub_new", "metadata": p.get("metadata") or {},
        })
        org = await fresh(db, oid)
        check("BetterSocials is active, billed through Stripe",
              row_of(org, "socials").status == "active" and row_of(org, "socials").billing_source == "stripe")
        check("BetterSocials renews on the BetterStats renewal date", row_of(org, "socials").renewal_date == RENEWS,
              str(row_of(org, "socials").renewal_date))
        check("BetterStats keeps its own date and is still not Stripe-billed",
              row_of(org, "core").renewal_date == RENEWS and row_of(org, "core").billing_source is None)
        check("the club now holds the new Stripe subscription", org.stripe_subscription_id == "sub_new")

        print("\n── A later add-on must not put the hand-set Core on the subscription ──")
        addons.clear()
        res = await br.create_checkout_session(body("select"), current_user=user, club=org, db=db)
        check("the second module is added to the existing subscription", res.get("added") is True, str(res))
        a = addons[-1] if addons else {}
        check("the existing keys are only what Stripe carries (socials)", a.get("existing") == ["socials"], str(a))

    print("\n── The renewal date is still stamped if Stripe's period field is absent ──")
    async with Session() as db:
        oid, user = await make_club(db, "No Period CC", core="manual")
        club = await fresh(db, oid)
        sessions.clear()
        await br.create_checkout_session(body("socials"), current_user=user, club=club, db=db)
        anchor_epoch["v"] = None
        await stripe_billing.handle_checkout_completed(db, {
            "mode": "subscription", "client_reference_id": str(oid), "customer": "cus_x",
            "subscription": "sub_x", "metadata": sessions[-1].get("metadata") or {},
        })
        org = await fresh(db, oid)
        check("it falls back to the date remembered in the checkout's metadata",
              row_of(org, "socials").renewal_date == RENEWS, str(row_of(org, "socials").renewal_date))

    print("\n── Several modules were taken by hand first ───────────────────")
    async with Session() as db:
        oid, user = await make_club(db, "Multi CC", core="manual", manual_keys=("select", "socials"))
        club = await fresh(db, oid)
        q = await br.get_quote(body("iq"), club=club, db=db)
        check("buying a further module is still prorated to the one renewal date",
              q.get("total") == prorated(249) and (q.get("prorated") or {}).get("renewal_date") == RENEWS.isoformat(),
              f"{q.get('total')} {q.get('prorated')}")
        check("no BetterStats line even though three modules are held", "BetterStats" not in names(q), str(names(q)))
        sessions.clear()
        await br.create_checkout_session(body("iq"), current_user=user, club=club, db=db)
        sd = (sessions[-1].get("subscription_data") or {}) if sessions else {}
        check("its checkout is anchored the same way",
              sd.get("billing_cycle_anchor") == int(datetime.combine(RENEWS, datetime.min.time(), tzinfo=timezone.utc).timestamp()), str(sd))

    print("\n── BetterStats Active but no usable renewal date ──────────────")
    async with Session() as db:
        for label, renews in (("no renewal date", None), ("a renewal date that has passed", TODAY - timedelta(days=3))):
            oid, user = await make_club(db, f"Dateless {label[:6]} CC", core="manual", renews=renews)
            club = await fresh(db, oid)
            q = await br.get_quote(body("socials"), club=club, db=db)
            check(f"{label}: BetterSocials is still not quoted BetterStats", "BetterStats" not in names(q), str(names(q)))
            check(f"{label}: nothing to prorate to, so a full year ($149) is quoted",
                  q.get("total") == 149 and not q.get("prorated"), f"{q.get('total')} {q.get('prorated')}")
            sessions.clear()
            await br.create_checkout_session(body("socials"), current_user=user, club=club, db=db)
            sd = (sessions[-1].get("subscription_data") or {}) if sessions else {}
            check(f"{label}: the Checkout Session carries no anchor", "billing_cycle_anchor" not in sd, str(sd))

    print("\n── Controls: clubs that really owe BetterStats ────────────────")
    async with Session() as db:
        oid, user = await make_club(db, "Trial CC", core="trial")
        club = await fresh(db, oid)
        q = await br.get_quote(body("socials"), club=club, db=db)
        check("a club still in its Core trial IS quoted BetterStats at $399 + $149 = $548",
              "BetterStats" in names(q) and q.get("total") == 548, f"{names(q)} {q.get('total')}")
        check("and it is not prorated", not q.get("prorated"))
        sessions.clear()
        await br.create_checkout_session(body("socials"), current_user=user, club=club, db=db)
        sd = (sessions[-1].get("subscription_data") or {}) if sessions else {}
        li_names = [li["price_data"]["product_data"]["name"] for li in sessions[-1].get("line_items", [])]
        check("its Checkout Session carries both lines and no anchor",
              len(li_names) == 2 and "billing_cycle_anchor" not in sd, f"{li_names} {sd}")
        oid, user = await make_club(db, "Expired CC", core="none")
        q = await br.get_quote(body("socials"), club=await fresh(db, oid), db=db)
        check("a club whose Core trial expired is quoted BetterStats too", "BetterStats" in names(q), str(names(q)))
        oid, user = await make_club(db, "Stripe CC", core="stripe", stripe_sub="sub_old", stripe_keys=("select",))
        addons.clear()
        await br.create_checkout_session(body("socials"), current_user=user, club=await fresh(db, oid), db=db)
        a = addons[-1] if addons else {}
        check("a Core genuinely on the Stripe subscription stays in its billing_keys",
              a.get("existing") == ["core", "select"], str(a))

    print("\n── Pay-by-invoice clubs follow the same rule ──────────────────")
    async with Session() as db:
        oid, user = await make_club(db, "Invoice Manual CC", core="manual", billing_method="invoice", enabled=True)
        club = await fresh(db, oid)
        plan = await invoice_billing.plan_invoice(db, club, ["socials"])
        check("an invoice for BetterSocials does not include BetterStats", plan["billing_keys"] == ["socials"],
              str(plan["billing_keys"]))
        check("it is an add-on prorated to the BetterStats renewal date",
              plan["kind"] == "addon" and plan["service_end_date"] == RENEWS and plan["prorated"]["days"] == 200,
              f"{plan['kind']} {plan['service_end_date']} {plan['prorated']}")
        check(f"and totals the part-year ${prorated(149):.2f} ex GST", plan["total_cents"] == round(prorated(149) * 100),
              str(plan["total_cents"]))
        try:
            await invoice_billing.plan_invoice(db, club, ["socials"], "TENOFF")
            check("a code is refused on it", False, "allowed")
        except invoice_billing.InvoiceBillingError:
            check("a code is refused on it", True)
        oid, user = await make_club(db, "Invoice NoDate CC", core="manual", renews=None, billing_method="invoice", enabled=True)
        plan = await invoice_billing.plan_invoice(db, await fresh(db, oid), ["socials"])
        check("with no BetterStats renewal date it is a full year ($149) without Core",
              plan["kind"] == "initial" and plan["billing_keys"] == ["socials"] and plan["total_cents"] == 14900,
              f"{plan['kind']} {plan['billing_keys']} {plan['total_cents']}")
        oid, user = await make_club(db, "Invoice Trial CC", core="trial", billing_method="invoice", enabled=True)
        plan = await invoice_billing.plan_invoice(db, await fresh(db, oid), ["socials"])
        check("a club still in its Core trial is invoiced Core as before",
              "core" in plan["billing_keys"] and plan["kind"] == "initial", f"{plan['kind']} {plan['billing_keys']}")

    print("\n── Super Admin sets the newly bought modules Active by hand ───")
    async with Session() as db:
        sa = None
        oid, _u = await make_club(db, "Hand CC", core="manual")

        async def patch(club_id, key, **fields):
            return await ca.patch_module_subscription(str(club_id), key, ca.ModuleUpdate(**fields), _=sa, db=db)

        res = await patch(oid, "socials", status="active")
        org = await fresh(db, oid)
        pr = res.get("proration") or {}
        check("BetterSocials renews on the BetterStats renewal date",
              row_of(org, "socials").renewal_date == RENEWS, str(row_of(org, "socials").renewal_date))
        check("the response says it was lined up with BetterStats", pr.get("aligned") is True, str(pr))
        check(f"and gives the prorated fee to collect (${prorated(149):.2f} ex GST)", pr.get("amount") == prorated(149), str(pr))
        check("with the days behind it (200 of the year)", (pr.get("days"), pr.get("of_days")) == (200, OF_DAYS), str(pr))

        res = await patch(oid, "iq", status="active")
        res2 = await patch(oid, "select", status="active")
        org = await fresh(db, oid)
        check("several modules set Active all land on the one renewal date",
              {row_of(org, k).renewal_date for k in ("socials", "iq", "select")} == {RENEWS},
              str({k: row_of(org, k).renewal_date for k in ("socials", "iq", "select")}))
        check("each is prorated at its own price (BetterIQ is $249)",
              (res.get("proration") or {}).get("amount") == prorated(249) and (res2.get("proration") or {}).get("amount") == prorated(149))

        # A module already paid keeps its date when Active is chosen again.
        row_of(org, "socials").renewal_date = RENEWS + timedelta(days=30)
        await db.commit()
        res = await patch(oid, "socials", status="active")
        org = await fresh(db, oid)
        check("choosing Active again on a paid module does not move its date",
              row_of(org, "socials").renewal_date == RENEWS + timedelta(days=30) and "proration" not in res,
              str(row_of(org, "socials").renewal_date))

        # A date the Super Admin chose is theirs.
        mine = RENEWS - timedelta(days=20)
        res = await patch(oid, "merch" if False else "fantasy", status="active", renewal_date=mine)
        org = await fresh(db, oid)
        check("a renewal date sent with Active is the Super Admin's choice and is kept",
              row_of(org, "fantasy").renewal_date == mine and "proration" not in res, str(row_of(org, "fantasy").renewal_date))

        # Setting BetterStats itself is not prorated.
        oid2, _u = await make_club(db, "Hand Core CC", core="none")
        res = await patch(oid2, "core", status="active", renewal_date=RENEWS)
        check("setting BetterStats Active is not prorated", "proration" not in res and
              row_of(await fresh(db, oid2), "core").renewal_date == RENEWS)
        # ...and it is the date everything else then follows (the order a club taking several modules by hand needs).
        await patch(oid2, "select", status="active")
        check("modules set Active after BetterStats follow its date",
              row_of(await fresh(db, oid2), "select").renewal_date == RENEWS)

        oid3, _u = await make_club(db, "Hand NoDate CC", core="manual", renews=None)
        res = await patch(oid3, "socials", status="active")
        org = await fresh(db, oid3)
        pr = res.get("proration") or {}
        check("with no BetterStats renewal date it is set Active but says why it was not lined up",
              row_of(org, "socials").status == "active" and row_of(org, "socials").renewal_date is None
              and pr.get("aligned") is False and bool(pr.get("reason")), str(pr))

    return report()


def report() -> int:
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print("  FAILED:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
