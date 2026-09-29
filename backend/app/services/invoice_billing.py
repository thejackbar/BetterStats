"""Pay by invoice: BetterCricket's own annual invoicing (migration 308).

A club on ``billing_method = 'invoice'`` never goes through Stripe Checkout.
Instead:

1. An admin (or a Super Admin on the club's behalf) picks the modules. The
   invoice is priced by the SAME maths Checkout uses — ``billing_pricing.
   price_for`` with the live bundle schedule, a validated discount code folded
   in by ``apply_coupon_to_quote`` — raised as a one-off Stripe invoice, and
   emailed to the club's Primary Club Admin with a link to pay it through
   Stripe's hosted invoice page (every payment method the account offers).
2. Paying it is what grants the modules — the ``invoice.paid`` webhook, never
   the request that raised it.
3. Fourteen days before the period ends, a renewal invoice for every module the
   club still holds is raised and emailed. It is due by the end of the day
   before the renewal date; a period that ends unpaid lapses the modules, and
   paying late brings them back for the rest of that period.

WHY THIS IS NOT A STRIPE SUBSCRIPTION WITH ``collection_method=send_invoice``.
A subscription raises its renewal invoice ON the renewal date. It cannot raise
it fourteen days early, so "settle before the period ends" is unreachable with
one. Running the cycle here and asking Stripe for one-off invoices keeps every
date ours to decide while Stripe still numbers the invoice, renders the PDF,
works out GST and takes the payment.

DATES. A period is ``[service_start_date, service_end_date)``: the end date is
the renewal date, the day the next period begins — the same convention the
card flow's ``renewal_date`` already follows (Stripe's current_period_end).
Everything is a Perth date, because every club this serves is Australian and a
"due by" that moves with the server's clock is not a due date.

WHAT PAYS FOR A MODULE is recorded on its row (``billing_source``). Only an
'invoice' row is renewed or lapsed here. A card club's modules belong to its
Stripe Subscription and a hand-granted module to nobody, so neither can be
invoiced or cut off by this job by accident.
"""
from __future__ import annotations

import html
import logging
import secrets
import uuid
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.modules import (
    BILLABLE_MODULES, PAID_STATUSES, STATUS_ACTIVE, STATUS_PAUSED, STATUS_TRIAL,
    account_plan_status, expand_billing_module,
)
from app.config.settings import settings
from app.models.db import (
    BillingInvoice, ClubMembership, DiscountCoupon, DiscountCouponRedemption,
    ModuleActionRequest, Organisation, User,
)
from app.services import (
    billing_address, billing_pricing, discount_coupons, email_service, module_subscriptions,
    platform_settings, stripe_client,
)

logger = logging.getLogger(__name__)

PERTH = ZoneInfo("Australia/Perth")

METHOD_CARD = "card"
METHOD_INVOICE = "invoice"
BILLING_METHODS = (METHOD_CARD, METHOD_INVOICE)

KIND_INITIAL = "initial"
KIND_ADDON = "addon"
KIND_RENEWAL = "renewal"

SOURCE_INVOICE = "invoice"
SOURCE_STRIPE = "stripe"

# How far ahead of the renewal date the renewal invoice goes out.
RENEWAL_NOTICE_DAYS = 14
# Terms for a club that is not trialling the modules it is buying — there is no
# trial end to be due by, so it gets the same fortnight a renewal does.
UNTRIALLED_DUE_DAYS = 14

# Stripe's billing_reason on a one-off invoice is always 'manual', which the
# sales-commission ledger reads as "earns nothing". These map invoice billing
# onto the three reasons the ledger already understands, so a first subscribe
# and an add-on paid by invoice earn exactly what the same purchase by card
# would, and a renewal earns nothing either way.
_COMMISSION_REASON = {
    KIND_INITIAL: "subscription_create",
    KIND_ADDON: "subscription_update",
    KIND_RENEWAL: "subscription_cycle",
}


class InvoiceBillingError(ValueError):
    """A refusal to show the person asking. ``status`` is the HTTP code the
    router answers with: 422 for a request that can't be priced, 409 for one
    that conflicts with how the club already pays."""

    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


# ─── Dates ───────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def perth_date(when: datetime) -> date:
    return when.astimezone(PERTH).date()


def perth_today(now: datetime | None = None) -> date:
    return perth_date(now or _now())


def start_of_day(d: date) -> datetime:
    """Midnight at the START of a Perth date, as an aware UTC datetime."""
    return datetime.combine(d, time.min, tzinfo=PERTH).astimezone(timezone.utc)


def due_by(d: date) -> datetime:
    """11:59:59pm Perth on the day BEFORE ``d`` — "settle before the period
    that begins on d". One second short of the next period, so a payment at
    11:59pm on the last day is on time and the displayed day is the last one
    the club has, not the first one it doesn't."""
    return start_of_day(d) - timedelta(seconds=1)


def add_years(d: date, years: int) -> date:
    """Same calendar date ``years`` on. 29 February lands on the 28th in a
    non-leap year rather than raising or rolling into March."""
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, day=28)


def fmt_date(d: date | None) -> str:
    return f"{d.day} {d.strftime('%b %Y')}" if d else ""


def fmt_money(cents: int | None) -> str:
    return f"${(cents or 0) / 100:,.2f}"


# ─── Who and what ────────────────────────────────────────────────────────────

async def primary_admin(db: AsyncSession, org_id) -> User | None:
    """The club's Primary Club Admin — the one person an invoice is addressed
    to, whoever asked for it. A club admin who is not primary is not a
    fallback: the invoice is a financial document and it goes to the person the
    club has named as its owner."""
    return (await db.execute(
        select(User)
        .join(ClubMembership, ClubMembership.user_id == User.id)
        .where(
            ClubMembership.club_id == org_id,
            ClubMembership.role == "club_admin",
            ClubMembership.is_primary_admin.is_(True),
        )
        .limit(1)
    )).scalar_one_or_none()


def _rows_for(org, billing_key: str) -> list:
    members = set(expand_billing_module(billing_key))
    return [s for s in (org.module_subscriptions or []) if s.module_key in members]


def invoice_period(org) -> tuple[date | None, list[str]]:
    """(renewal date, billing keys) of the period the club currently holds on
    an invoice — the modules whose rows are invoice-billed and paid. The
    earliest renewal date wins: every write here moves the whole period
    together, so they only differ on data somebody edited by hand, and the
    earlier one is when something actually ends."""
    keys: list[str] = []
    renewals: list[date] = []
    for key in BILLABLE_MODULES:
        rows = [r for r in _rows_for(org, key)
                if r.billing_source == SOURCE_INVOICE and r.status in PAID_STATUSES]
        if rows:
            keys.append(key)
            renewals += [r.renewal_date for r in rows if r.renewal_date]
    return (min(renewals) if renewals else None), keys


def _earliest_trial_end(org, keys: list[str], now: datetime) -> datetime | None:
    ends = [
        r.trial_ends_at for k in keys for r in _rows_for(org, k)
        if r.status == STATUS_TRIAL and r.trial_ends_at and r.trial_ends_at > now
    ]
    return min(ends) if ends else None


def _line(key: str, name: str, full_dollars: float, amount_cents: int) -> dict:
    return {"key": key, "name": name, "full_price": full_dollars, "amount_cents": int(amount_cents)}


async def _continuing_coupon(db: AsyncSession, org) -> DiscountCoupon | None:
    """A code the club redeemed earlier that is still owed on a renewal.

    'once' is spent by the first invoice. 'forever' applies to every renewal.
    'repeating' covers ``duration_renewals`` annual charges IN TOTAL, the first
    included — the same count Stripe applies with duration_in_months = 12 × N —
    so it stops once that many paid invoices have carried it."""
    rows = (await db.execute(
        select(DiscountCoupon)
        .join(DiscountCouponRedemption, DiscountCouponRedemption.coupon_id == DiscountCoupon.id)
        .where(
            DiscountCouponRedemption.organisation_id == org.id,
            DiscountCouponRedemption.status == "active",
            DiscountCoupon.duration_mode.in_(("forever", "repeating")),
        )
    )).scalars().all()
    for coupon in rows:
        if coupon.duration_mode == "forever":
            return coupon
        used = (await db.execute(
            select(BillingInvoice.id).where(
                BillingInvoice.organisation_id == org.id,
                BillingInvoice.status == "paid",
                BillingInvoice.coupon_code == coupon.code,
            )
        )).scalars().all()
        if len(used) < int(coupon.duration_renewals or 1):
            return coupon
    return None


def _with_coupon(quote: dict, coupon) -> tuple[dict, float]:
    if coupon is None:
        return quote, 0.0
    quote = billing_pricing.apply_coupon_to_quote(quote, coupon)
    return quote, float(quote["coupon"]["amount_off"])


# ─── Pricing ─────────────────────────────────────────────────────────────────

async def plan_invoice(db: AsyncSession, org, module_keys: list[str], coupon_code: str | None = None,
                       *, now: datetime | None = None) -> dict:
    """What an invoice for these modules would say, without raising it.

    The one function the Account page's preview and the real invoice both
    call, so the figure somebody agrees to is the figure they are sent.

    A club with no invoice period running gets an INITIAL invoice: Core plus
    the selection, the bundle discount, and a discount code if one is given.
    Its twelve months start when the trial on those modules ends (so paying
    early costs the club none of its trial), or on payment if there is no
    trial left.

    A club already holding an invoice period gets an ADD-ON: the new modules
    only, no bundle discount — the rule the card flow already keeps, the bundle
    being a reward for subscribing all at once — prorated from today (or the
    end of the module's trial) to the period's renewal date, so the whole club
    renews together."""
    now = now or _now()
    today = perth_today(now)
    if getattr(org, "stripe_subscription_id", None):
        raise InvoiceBillingError(
            "This club pays by card through a Stripe subscription, so modules are added from the "
            "card checkout. Switch the club to invoice billing once that subscription has ended.",
            status=409,
        )
    keys = sorted(set(module_keys or []))
    if not keys:
        raise InvoiceBillingError("Select at least one module")
    plan_by_key = {row["module"]: row for row in account_plan_status(org)}
    already = [k for k in keys if not plan_by_key.get(k, {}).get("can_subscribe", True)]
    renewal, held = invoice_period(org)
    in_period = bool(held) and renewal is not None and renewal > today

    if in_period:
        keys = [k for k in keys if k != "core" and k not in held]
        if not keys:
            raise InvoiceBillingError("Those modules are already on this club's current invoice period.", 409)
        if already:
            raise InvoiceBillingError(f"Already subscribed: {', '.join(already)}", 409)
        if coupon_code:
            raise InvoiceBillingError(
                "A discount code applies to a first subscription or a renewal, not to modules added "
                "part way through a year."
            )
        trial_end = _earliest_trial_end(org, keys, now)
        start = max(today, perth_date(trial_end)) if trial_end else today
        period_days = (renewal - add_years(renewal, -1)).days
        remaining = (renewal - start).days
        if remaining <= 0:
            raise InvoiceBillingError(
                f"This club's period renews on {fmt_date(renewal)}, before these modules' trial ends. "
                "Add them after the renewal and they will be invoiced for a full year."
            )
        quote = billing_pricing.price_for_addon(keys)
        lines = [
            _line(li["key"], li["name"], li["price"], round(li["price"] * 100 * remaining / period_days))
            for li in quote["line_items"]
        ]
        subtotal_cents = sum(li["amount_cents"] for li in lines)
        return {
            "kind": KIND_ADDON,
            "billing_keys": keys,
            "lines": lines,
            "subtotal_cents": subtotal_cents,
            "bundle_discount_cents": 0,
            "coupon": None,
            "coupon_discount_cents": 0,
            "total_cents": subtotal_cents,
            "service_start_date": start,
            "service_end_date": renewal,
            "prorated": {"days": remaining, "of_days": period_days},
            "due_at": _due_for_new(trial_end, now),
        }

    if already:
        # Core is always priced into a first subscription, so a Core already
        # held (hand-granted) is not refused here — the card checkout charges
        # it in exactly the same way, and the two must not disagree.
        blocking = [k for k in already if k != "core"]
        if blocking:
            raise InvoiceBillingError(f"Already subscribed: {', '.join(blocking)}", 409)
    priced = keys if "core" in keys else [*keys, "core"]
    schedule = await platform_settings.get_bundle_discount_schedule(db)
    quote = billing_pricing.price_for(priced, schedule=schedule)
    coupon = None
    if coupon_code:
        try:
            coupon = await discount_coupons.validate_redemption(
                db, coupon_code, org, is_new_signup=True, candidate_module_keys=priced,
            )
        except discount_coupons.CouponError as e:
            raise InvoiceBillingError(str(e))
    quote, coupon_off = _with_coupon(quote, coupon)
    trial_end = _earliest_trial_end(org, priced, now)
    start = max(today, perth_date(trial_end)) if trial_end else today
    lines = [_line(li["key"], li["name"], li["price"], li["price"] * 100) for li in quote["line_items"]]
    subtotal_cents = sum(li["amount_cents"] for li in lines)
    bundle_cents = round(float(quote["discount"]) * 100)
    coupon_cents = round(coupon_off * 100)
    return {
        "kind": KIND_INITIAL,
        "billing_keys": sorted(set(priced)),
        "lines": lines,
        "subtotal_cents": subtotal_cents,
        "bundle_discount_cents": bundle_cents,
        "coupon": _coupon_out(coupon, coupon_cents),
        "coupon_discount_cents": coupon_cents,
        "total_cents": max(0, subtotal_cents - bundle_cents - coupon_cents),
        "service_start_date": start,
        "service_end_date": add_years(start, 1),
        "prorated": None,
        "due_at": _due_for_new(trial_end, now),
    }


def _due_for_new(trial_end: datetime | None, now: datetime) -> datetime:
    """A first or add-on invoice is due before the trial it is paying to keep
    ends — that is the "end" the club must settle before. With no trial left
    to protect it gets ordinary terms. A trial ending within the hour is given
    the hour, since Stripe refuses a due date in the past."""
    if trial_end and trial_end > now + timedelta(hours=1):
        return trial_end
    if trial_end:
        return now + timedelta(hours=1)
    return now + timedelta(days=UNTRIALLED_DUE_DAYS)


def _coupon_out(coupon, cents: int) -> dict | None:
    if coupon is None:
        return None
    return {
        "id": str(coupon.id),
        "code": coupon.code,
        "display_name": coupon.display_name,
        "amount_off_cents": cents,
        "duration_mode": coupon.duration_mode,
    }


async def plan_renewal(db: AsyncSession, org, *, now: datetime | None = None) -> dict | None:
    """The renewal invoice for the period the club holds, or None if it holds
    none. Every module still on the invoice period, at its full annual price.

    No bundle discount: the card flow's bundle coupon is duration=once, so a
    card club renews at full price too, and the two ways of paying must cost
    the same. A discount code redeemed earlier is applied while it is still
    owed (see _continuing_coupon)."""
    now = now or _now()
    renewal, held = invoice_period(org)
    if not held or renewal is None:
        return None
    catalogue = {m["key"]: m for m in [billing_pricing.CORE, *billing_pricing.PRICED_MODULES, billing_pricing.FANTASY]}
    items = [dict(catalogue[k]) for k in held if k in catalogue]
    subtotal = sum(i["price"] for i in items)
    quote = {"line_items": items, "subtotal": subtotal, "discount": 0, "total": subtotal}
    coupon = await _continuing_coupon(db, org)
    quote, coupon_off = _with_coupon(quote, coupon)
    lines = [_line(i["key"], i["name"], i["price"], i["price"] * 100) for i in items]
    subtotal_cents = sum(li["amount_cents"] for li in lines)
    coupon_cents = round(coupon_off * 100)
    return {
        "kind": KIND_RENEWAL,
        "billing_keys": held,
        "lines": lines,
        "subtotal_cents": subtotal_cents,
        "bundle_discount_cents": 0,
        "coupon": _coupon_out(coupon, coupon_cents),
        "coupon_discount_cents": coupon_cents,
        "total_cents": max(0, subtotal_cents - coupon_cents),
        "service_start_date": renewal,
        "service_end_date": add_years(renewal, 1),
        "prorated": None,
        "due_at": due_by(renewal),
    }


def plan_out(plan: dict) -> dict:
    """A plan in the shape the Account page reads (dollars, ISO dates)."""
    return {
        "mode": "invoice",
        "kind": plan["kind"],
        "billing_keys": plan["billing_keys"],
        "line_items": [
            {"key": li["key"], "name": li["name"], "full_price": li["full_price"],
             "amount": li["amount_cents"] / 100}
            for li in plan["lines"]
        ],
        "subtotal": plan["subtotal_cents"] / 100,
        "discount": plan["bundle_discount_cents"] / 100,
        "coupon": (
            {**plan["coupon"], "amount_off": plan["coupon"]["amount_off_cents"] / 100}
            if plan["coupon"] else None
        ),
        "total": plan["total_cents"] / 100,
        "service_start_date": plan["service_start_date"].isoformat(),
        "service_end_date": plan["service_end_date"].isoformat(),
        "prorated": plan["prorated"],
        "due_at": plan["due_at"].isoformat(),
    }


# ─── Raising an invoice ──────────────────────────────────────────────────────

def pay_url(row: BillingInvoice) -> str:
    """The link the email carries. It goes through our own redirect (routers/
    public_billing.py) rather than straight to Stripe, so it always lands on
    the invoice's CURRENT payment page — and, once paid, on the Account page
    instead of a Stripe page that only says so."""
    return f"{settings.public_base_url}/api/public/billing/pay/{row.pay_token}"


async def _void_row(db: AsyncSession, row: BillingInvoice, now: datetime) -> None:
    try:
        await stripe_client.void_invoice(row.stripe_invoice_id)
    except stripe_client.StripeNotConfigured:
        raise
    except Exception:
        # Stripe keeps the truth: if the void didn't land, the invoice.voided
        # webhook never arrives and the row is only marked void here. The
        # pay link checks Stripe before redirecting, so a still-open invoice
        # can't be paid through us — but log it, because it can be paid
        # from Stripe's own email if the Dashboard sends one.
        logger.exception("invoice billing: could not void Stripe invoice %s", row.stripe_invoice_id)
    row.status = "void"
    row.updated_at = now
    if row.coupon_redemption_id:
        redemption = await db.get(DiscountCouponRedemption, row.coupon_redemption_id)
        if redemption is not None and redemption.status == "pending":
            redemption.status = "revoked"


async def open_invoices(db: AsyncSession, org_id, kinds: tuple[str, ...] | None = None) -> list[BillingInvoice]:
    stmt = select(BillingInvoice).where(
        BillingInvoice.organisation_id == org_id,
        BillingInvoice.billing_method == METHOD_INVOICE,
        BillingInvoice.status == "open",
    )
    if kinds:
        stmt = stmt.where(BillingInvoice.invoice_kind.in_(kinds))
    return list((await db.execute(stmt.order_by(BillingInvoice.created_at.desc()))).scalars().all())


async def issue_invoice(db: AsyncSession, org, plan: dict, *, issued_by=None, applied_via: str = "self_serve",
                        send_email: bool = True, now: datetime | None = None) -> BillingInvoice:
    """Raise ``plan`` as a Stripe invoice, record it, and email it.

    Refuses before touching Stripe when the club has no Primary Club Admin with
    an email address: an invoice nobody receives is worse than no invoice.

    A new first or add-on invoice REPLACES any first or add-on invoice still
    open for the club — they are voided, so a club that changed its mind about
    the modules can never pay twice. A new FIRST invoice also voids a renewal
    invoice left open by a period that has since lapsed: the first invoice
    starts a new year, and paying both would buy the same year twice. A
    renewal invoice is never otherwise replaced; there is one per period,
    which the unique index enforces.

    ``applied_via`` is recorded on a discount-code redemption ('self_serve' or
    'super_admin'), the vocabulary the coupon screens already read."""
    from app.services import stripe_billing  # imports this module; see handle_invoice_event

    now = now or _now()
    admin = await primary_admin(db, org.id)
    if admin is None or not (admin.email or "").strip():
        raise InvoiceBillingError(
            "This club has no Primary Club Admin with an email address to send the invoice to. "
            "Set one on the club's users first.",
            status=409,
        )

    if plan["kind"] == KIND_RENEWAL:
        existing = (await db.execute(
            select(BillingInvoice).where(
                BillingInvoice.organisation_id == org.id,
                BillingInvoice.invoice_kind == KIND_RENEWAL,
                BillingInvoice.service_start_date == plan["service_start_date"],
                BillingInvoice.status.notin_(("void", "uncollectible")),
            )
        )).scalar_one_or_none()
        if existing is not None:
            return existing
    else:
        kinds = None if plan["kind"] == KIND_INITIAL else (KIND_INITIAL, KIND_ADDON)
        for old in await open_invoices(db, org.id, kinds):
            await _void_row(db, old, now)

    redemption_id = None
    if plan["coupon"] and plan["kind"] == KIND_INITIAL:
        redemption = DiscountCouponRedemption(
            id=uuid.uuid4(), coupon_id=uuid.UUID(plan["coupon"]["id"]), organisation_id=org.id,
            redeemed_by_user_id=getattr(issued_by, "id", None),
            applied_via=applied_via,
            status="pending",
        )
        db.add(redemption)
        redemption_id = redemption.id
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            raise InvoiceBillingError("Your club has already used this code")

    customer_id = await stripe_client.ensure_customer_for_org(
        org, email=(org.contact_email or admin.email), address=billing_address.stripe_address(org),
    )
    org.stripe_customer_id = customer_id

    coupon_code = plan["coupon"]["code"] if plan["coupon"] else None
    coupon_id = await stripe_client.ensure_invoice_discount_coupon(
        db,
        bundle_dollars=plan["bundle_discount_cents"] / 100,
        coupon_code=coupon_code,
        coupon_dollars=plan["coupon_discount_cents"] / 100,
    )

    start, end = plan["service_start_date"], plan["service_end_date"]
    metadata = {
        "billing_method": METHOD_INVOICE,
        "org_id": str(org.id),
        "invoice_kind": plan["kind"],
        "billing_keys": ",".join(plan["billing_keys"]),
        "service_start_date": start.isoformat(),
        "service_end_date": end.isoformat(),
        "bundle_discount_cents": str(plan["bundle_discount_cents"]),
        "coupon_discount_cents": str(plan["coupon_discount_cents"]),
    }
    if coupon_code:
        metadata["coupon_code"] = coupon_code
    if redemption_id:
        metadata["coupon_redemption_id"] = str(redemption_id)
    period = (int(start_of_day(start).timestamp()), int(start_of_day(end).timestamp()))
    lines = []
    for li in plan["lines"]:
        label = f"BetterCricket — {li['name']}"
        if plan["prorated"]:
            label += f" (prorated, {plan['prorated']['days']} of {plan['prorated']['of_days']} days)"
        lines.append({"description": label, "amount_cents": li["amount_cents"], "period": period,
                      "metadata": {"billing_key": li["key"]}})
    what = {KIND_INITIAL: "Annual licence", KIND_ADDON: "Modules added", KIND_RENEWAL: "Annual licence renewal"}
    description = f"{org.name} — {what[plan['kind']]}, {fmt_date(start)} to {fmt_date(end)}"
    idempotency_key = (
        f"bc-renewal-{org.id}-{start.isoformat()}" if plan["kind"] == KIND_RENEWAL
        else f"bc-{plan['kind']}-{org.id}-{uuid.uuid4()}"
    )
    invoice = await stripe_client.create_one_off_invoice(
        customer_id=customer_id,
        lines=lines,
        due_at=plan["due_at"],
        metadata=metadata,
        coupon_id=coupon_id,
        description=description,
        footer="Pay online from the invoice link. Questions: support@bettersports.com.au",
        idempotency_key=idempotency_key,
    )

    await stripe_billing._upsert_invoice(
        db, org, invoice, now, billing_reason=_COMMISSION_REASON[plan["kind"]],
    )
    row = (await db.execute(
        select(BillingInvoice).where(BillingInvoice.stripe_invoice_id == invoice["id"])
    )).scalar_one()
    _stamp_row(row, plan, invoice, now)
    row.issued_by_user_id = getattr(issued_by, "id", None)
    row.coupon_redemption_id = redemption_id
    if not row.pay_token:
        row.pay_token = secrets.token_urlsafe(24)
    try:
        await db.commit()
    except IntegrityError:
        # Another run raised this period's renewal between our check and now.
        # Ours is the duplicate: void it at Stripe and hand back theirs.
        await db.rollback()
        try:
            await stripe_client.void_invoice(invoice["id"])
        except Exception:
            logger.exception("invoice billing: could not void duplicate renewal %s", invoice["id"])
        return (await db.execute(
            select(BillingInvoice).where(
                BillingInvoice.organisation_id == org.id,
                BillingInvoice.invoice_kind == KIND_RENEWAL,
                BillingInvoice.service_start_date == start,
                BillingInvoice.status.notin_(("void", "uncollectible")),
            )
        )).scalar_one()
    await db.refresh(row)
    if send_email:
        await send_invoice_email(db, org, row, admin=admin)
    return row


def _stamp_row(row: BillingInvoice, plan: dict, invoice: dict, now: datetime) -> None:
    """Our own record of what the invoice is for. Written from the PLAN, not
    re-read from Stripe's lines, because the names and the discount split are
    ours: Stripe can only show one combined discount line."""
    row.billing_method = METHOD_INVOICE
    row.invoice_kind = plan["kind"]
    row.invoice_number = invoice.get("number")
    row.billing_keys = list(plan["billing_keys"])
    row.service_start_date = plan["service_start_date"]
    row.service_end_date = plan["service_end_date"]
    row.due_at = plan["due_at"]
    row.amount_total_cents = invoice.get("total")
    row.line_items = [
        {"name": f"BetterCricket — {li['name']}", "price": li["amount_cents"] / 100} for li in plan["lines"]
    ]
    row.bundle_discount_cents = plan["bundle_discount_cents"]
    row.coupon_code = plan["coupon"]["code"] if plan["coupon"] else None
    row.coupon_discount_cents = plan["coupon_discount_cents"]
    row.updated_at = now


# ─── The email ───────────────────────────────────────────────────────────────

def _email_body(org, row: BillingInvoice, admin: User) -> tuple[str, str, str]:
    """(subject, html, text) for an invoice email. Renewal wording says the
    period is ending and what happens if it isn't paid; a first invoice says
    what paying it switches on."""
    name = html.escape(org.name or "your club")
    first = (admin.display_name or admin.username or "").split(" ")[0]
    greeting = f"Hi {html.escape(first)}," if first else "Hi,"
    number = row.invoice_number or "(draft)"
    due_date = perth_date(row.due_at) if row.due_at else None
    total = fmt_money(row.amount_total_cents if row.amount_total_cents is not None else row.amount_due)
    start, end = row.service_start_date, row.service_end_date
    link = pay_url(row)

    if row.invoice_kind == KIND_RENEWAL:
        subject = f"Renewal invoice {number}: {org.name}'s BetterCricket subscription ends {fmt_date(start)}"
        lede = (
            f"{name}'s BetterCricket subscription is due for renewal on <b>{fmt_date(start)}</b>. "
            f"Your renewal invoice for the next 12 months ({fmt_date(start)} to {fmt_date(end)}) is below."
        )
        consequence = (
            f"Please pay by <b>11:59pm {fmt_date(due_date)}</b> (Perth time). If it is still unpaid "
            f"when the period ends, your club's modules are paused until it is paid."
        )
    else:
        subject = f"Invoice {number}: BetterCricket subscription for {org.name}"
        lede = (
            f"Here is the invoice {name} asked for. Once it is paid, your modules are subscribed "
            f"from {fmt_date(start)} to {fmt_date(end)}."
        )
        consequence = (
            f"Please pay by <b>{fmt_date(due_date)}</b>. If your club is trialling these modules, "
            f"paying before the trial ends keeps them running without a break."
        )

    rows_html = "".join(
        f'<tr><td style="padding:4px 0">{html.escape(li.get("name") or "")}</td>'
        f'<td style="padding:4px 0;text-align:right">{fmt_money(round((li.get("price") or 0) * 100))}</td></tr>'
        for li in (row.line_items or [])
    )
    if row.bundle_discount_cents:
        rows_html += (f'<tr><td style="padding:4px 0">Bundle discount</td>'
                      f'<td style="padding:4px 0;text-align:right">-{fmt_money(row.bundle_discount_cents)}</td></tr>')
    if row.coupon_discount_cents:
        rows_html += (f'<tr><td style="padding:4px 0">Discount code {html.escape(row.coupon_code or "")}</td>'
                      f'<td style="padding:4px 0;text-align:right">-{fmt_money(row.coupon_discount_cents)}</td></tr>')
    pdf = (f'<p style="font-size:13px"><a href="{html.escape(row.invoice_pdf)}">Download the invoice (PDF)</a></p>'
           if row.invoice_pdf else "")
    body = f"""
    <div style="font-family:Arial,Helvetica,sans-serif;max-width:560px;margin:0 auto;padding:24px;color:#1a1a1a">
      <p style="font-size:14px;color:#555">BetterCricket</p>
      <h1 style="font-size:20px;margin:0 0 16px">Invoice {html.escape(number)}</h1>
      <p style="font-size:14px;line-height:1.5">{greeting}</p>
      <p style="font-size:14px;line-height:1.5">{lede}</p>
      <table style="width:100%;font-size:14px;border-collapse:collapse;margin:16px 0">
        {rows_html}
        <tr><td style="padding:8px 0;border-top:1px solid #ddd;font-weight:bold">Total, including GST</td>
            <td style="padding:8px 0;border-top:1px solid #ddd;text-align:right;font-weight:bold">{total}</td></tr>
      </table>
      <p style="font-size:14px;line-height:1.5">{consequence}</p>
      <p style="margin:24px 0">
        <a href="{link}" style="display:inline-block;background:#16C784;color:#fff;text-decoration:none;
          padding:12px 24px;border-radius:6px;font-weight:bold;font-size:14px">View and pay this invoice</a>
      </p>
      {pdf}
      <p style="font-size:12px;color:#888">
        Pay securely through Stripe by card or any other payment method offered on the page.
        Or paste this link into your browser: {link}
      </p>
      <p style="font-size:12px;color:#888;margin-top:24px">
        Questions about this invoice? Reply to this email or write to support@bettersports.com.au.
      </p>
    </div>
    """
    text = (
        f"{greeting.replace(',', '')}, invoice {number} for {org.name}'s BetterCricket subscription "
        f"({fmt_date(start)} to {fmt_date(end)}). Total including GST: {total}. "
        f"Due by {fmt_date(due_date)}. View and pay: {link}"
        + (f" Download the PDF: {row.invoice_pdf}" if row.invoice_pdf else "")
    )
    return subject, body, text


async def send_invoice_email(db: AsyncSession, org, row: BillingInvoice, *, admin: User | None = None) -> dict:
    """Email the invoice to the Primary Club Admin and record the outcome ON
    THE ROW, so "they say they never got it" has an answer.

    The console provider is not a send — it writes a log line and says ok,
    which is the trap the sales-email note records. It is reported as not sent,
    so nobody is told an invoice went out when nothing left the building."""
    admin = admin or await primary_admin(db, org.id)
    now = _now()
    if admin is None or not (admin.email or "").strip():
        row.email_error = "The club has no Primary Club Admin with an email address."
        await db.commit()
        return {"ok": False, "error": row.email_error, "to": None}
    to = admin.email.strip()
    provider = email_service.get_email_provider()
    row.sent_to_email = to
    if provider.name == "console":
        row.email_error = "Email isn't configured on this server, so the invoice was not emailed."
        await db.commit()
        return {"ok": False, "error": row.email_error, "to": to}
    subject, body, text = _email_body(org, row, admin)
    msg = email_service.EmailMessage(
        to_email=to,
        to_name=admin.display_name or None,
        subject=subject,
        html=body,
        text=text,
        from_email=settings.email_from_address,
        from_name=settings.email_from_name,
        reply_to=settings.email_reply_to,
        configuration_set=(settings.ses_configuration_set_transactional or "").strip() or None,
    )
    try:
        result = await provider.send(msg)
    except Exception as e:  # noqa: BLE001 — recorded, never raised
        result = email_service.SendResult(ok=False, error=str(e))
    if result.ok:
        row.emailed_at = now
        row.email_error = None
    else:
        row.email_error = (result.error or "The email provider refused the message.")[:500]
    await db.commit()
    return {"ok": bool(result.ok), "error": row.email_error, "to": to}


# ─── Paid, failed, voided ────────────────────────────────────────────────────

def is_invoice_billing(invoice: dict) -> bool:
    return (invoice.get("metadata") or {}).get("billing_method") == METHOD_INVOICE


def _parse_date(raw) -> date | None:
    try:
        return date.fromisoformat(str(raw)) if raw else None
    except ValueError:
        return None


async def handle_invoice_event(db: AsyncSession, invoice: dict, event_type: str) -> None:
    """Every webhook for an invoice this module raised.

    PAID is the only thing that grants a module. A first subscription's twelve
    months start on the later of the date on the invoice and the day it was
    actually paid — paying early loses the club none of its trial, paying late
    does not buy time it already had for free. An add-on and a renewal pay up
    to the date on the invoice, which is what keeps the club on one renewal
    date.

    Replaying an old event is harmless: a renewal date is only ever moved
    FORWARD, so last year's invoice.paid arriving again cannot undo this
    year's."""
    from app.services import stripe_billing

    meta = invoice.get("metadata") or {}
    org = await stripe_billing._load_org(db, meta.get("org_id"))
    if org is None:
        logger.warning("invoice billing %s: unknown org_id=%r", event_type, meta.get("org_id"))
        return
    kind = meta.get("invoice_kind") or KIND_INITIAL
    now = _now()
    await stripe_billing._upsert_invoice(
        db, org, invoice, now, billing_reason=_COMMISSION_REASON.get(kind),
    )
    row = (await db.execute(
        select(BillingInvoice).where(BillingInvoice.stripe_invoice_id == invoice.get("id"))
    )).scalar_one_or_none()

    redemption_id = meta.get("coupon_redemption_id")
    if event_type in ("invoice.voided", "invoice.marked_uncollectible"):
        if redemption_id:
            try:
                redemption = await db.get(DiscountCouponRedemption, uuid.UUID(redemption_id))
            except (ValueError, TypeError):
                redemption = None
            if redemption is not None and redemption.status == "pending":
                redemption.status = "revoked"
        await db.commit()
        return
    if event_type != "invoice.paid":
        await db.commit()
        return

    keys = [k for k in (meta.get("billing_keys") or "").split(",") if k in BILLABLE_MODULES]
    start = _parse_date(meta.get("service_start_date")) or perth_today(now)
    end = _parse_date(meta.get("service_end_date")) or add_years(start, 1)
    paid_at = stripe_client.epoch_to_datetime(
        ((invoice.get("status_transitions") or {}).get("paid_at"))
    ) or now
    if kind == KIND_INITIAL:
        start = max(start, perth_date(paid_at))
        end = add_years(start, 1)
    if row is not None:
        row.service_start_date = start
        row.service_end_date = end

    granted: list[str] = []
    for key in keys:
        rows = _rows_for(org, key)
        if kind == KIND_RENEWAL and not rows:
            # Removed since the invoice went out — renewing it would switch
            # back on a module the club cancelled.
            continue
        if rows and all(r.status in PAID_STATUSES and r.renewal_date and r.renewal_date >= end for r in rows):
            continue  # already paid through at least this far
        module_subscriptions.set_status_billing(org, key, STATUS_ACTIVE, renewal_date=end, now=now)
        module_subscriptions.set_billing_source(org, key, SOURCE_INVOICE, now=now)
        granted.append(key)
        if kind != KIND_RENEWAL:
            db.add(ModuleActionRequest(
                organisation_id=org.id, module_key=key, kind="subscribe", status="completed",
                source="invoice", note=f"Paid by invoice {invoice.get('number') or ''}".strip(),
                completed_at=now,
            ))

    if redemption_id:
        try:
            redemption = await db.get(DiscountCouponRedemption, uuid.UUID(redemption_id))
        except (ValueError, TypeError):
            redemption = None
        if redemption is not None and redemption.status == "pending":
            redemption.status = "active"
    await db.commit()
    if granted and kind != KIND_RENEWAL:
        stripe_billing._sync_crm(org.id, crm_trigger="subscription_won", won_module_keys=granted)


# ─── The daily job ───────────────────────────────────────────────────────────

async def lapse_unpaid(db: AsyncSession, *, now: datetime | None = None) -> list[str]:
    """Pause every invoice-billed module whose period has ended unpaid.

    A period ends at the start of its renewal date, so on that date a module
    still carrying it is lapsed. Paused, not removed: the row, its dates and
    the open renewal invoice all survive, and paying that invoice switches the
    module straight back on for the rest of its period."""
    from app.models.db import OrgModuleSubscription

    now = now or _now()
    today = perth_today(now)
    org_ids = (await db.execute(
        select(OrgModuleSubscription.organisation_id).where(
            OrgModuleSubscription.billing_source == SOURCE_INVOICE,
            OrgModuleSubscription.status.in_(tuple(PAID_STATUSES)),
            OrgModuleSubscription.renewal_date.isnot(None),
            OrgModuleSubscription.renewal_date <= today,
        ).distinct()
    )).scalars().all()
    affected: list[str] = []
    for org_id in org_ids:
        org = await db.get(Organisation, org_id, options=[selectinload(Organisation.module_subscriptions)])
        if org is None:
            continue
        for key in BILLABLE_MODULES:
            rows = [r for r in _rows_for(org, key)
                    if r.billing_source == SOURCE_INVOICE and r.status in PAID_STATUSES
                    and r.renewal_date and r.renewal_date <= today]
            if not rows:
                continue
            module_subscriptions.set_status_billing(org, key, STATUS_PAUSED, now=now)
            db.add(ModuleActionRequest(
                organisation_id=org.id, module_key=key, kind="cancel", status="completed",
                source="invoice", note=f"Renewal invoice unpaid when the period ended on {fmt_date(rows[0].renewal_date)}",
                completed_at=now,
            ))
        affected.append(str(org_id))
    if affected:
        await db.commit()
    return affected


async def issue_due_renewals(db: AsyncSession, *, now: datetime | None = None) -> dict:
    """Raise and email the renewal invoice for every invoice-billed club whose
    period ends within RENEWAL_NOTICE_DAYS. Only while the club is still ON
    invoice billing — a club that has switched back to card is not invoiced,
    which is what "until the club changes the setting" asks for. A period
    already carrying a renewal invoice is skipped, so the job is safe to run
    as often as it likes."""
    from app.models.db import OrgModuleSubscription

    now = now or _now()
    today = perth_today(now)
    horizon = today + timedelta(days=RENEWAL_NOTICE_DAYS)
    org_ids = (await db.execute(
        select(OrgModuleSubscription.organisation_id)
        .join(Organisation, Organisation.id == OrgModuleSubscription.organisation_id)
        .where(
            Organisation.billing_method == METHOD_INVOICE,
            Organisation.invoice_billing_enabled.is_(True),
            Organisation.archived_at.is_(None),
            OrgModuleSubscription.billing_source == SOURCE_INVOICE,
            OrgModuleSubscription.status.in_(tuple(PAID_STATUSES)),
            OrgModuleSubscription.renewal_date > today,
            OrgModuleSubscription.renewal_date <= horizon,
        ).distinct()
    )).scalars().all()
    stats = {"issued": 0, "already": 0, "failed": 0, "emailed": 0}
    for org_id in org_ids:
        try:
            org = await db.get(Organisation, org_id, options=[selectinload(Organisation.module_subscriptions)])
            plan = await plan_renewal(db, org, now=now)
            if plan is None:
                continue
            before = (await db.execute(
                select(BillingInvoice.id).where(
                    BillingInvoice.organisation_id == org.id,
                    BillingInvoice.invoice_kind == KIND_RENEWAL,
                    BillingInvoice.service_start_date == plan["service_start_date"],
                    BillingInvoice.status.notin_(("void", "uncollectible")),
                )
            )).scalar_one_or_none()
            if before is not None:
                stats["already"] += 1
                continue
            row = await issue_invoice(db, org, plan, issued_by=None, now=now)
            stats["issued"] += 1
            if row.emailed_at:
                stats["emailed"] += 1
        except Exception:
            stats["failed"] += 1
            await db.rollback()
            logger.exception("invoice billing: renewal for org %s failed", org_id)
    return stats


async def run_daily(db: AsyncSession, *, now: datetime | None = None) -> dict:
    now = now or _now()
    lapsed = await lapse_unpaid(db, now=now)
    renewals = await issue_due_renewals(db, now=now)
    return {"lapsed_clubs": len(lapsed), **renewals}


# ─── Settings and the overview ───────────────────────────────────────────────

async def set_billing_method(db: AsyncSession, org, method: str, *, user=None) -> None:
    """Switch how the club pays. Moving TO invoice billing needs a Super Admin
    to have switched invoicing on for the club (``invoice_billing_enabled``,
    off by default) and is refused while a
    Stripe Subscription is live, because that subscription would go on
    charging the card beside the invoices. Moving back to card is always
    allowed: the invoice period already paid runs to its end, and no renewal
    invoice is raised for it."""
    if method not in BILLING_METHODS:
        raise InvoiceBillingError(f"Unknown billing method: {method}")
    if method == METHOD_INVOICE and not getattr(org, "invoice_billing_enabled", False):
        raise InvoiceBillingError(
            "Invoicing isn't available for this club. A BetterCricket Super Admin can switch it on "
            "from All Clubs.",
            status=403,
        )
    if method == METHOD_INVOICE and org.stripe_subscription_id:
        raise InvoiceBillingError(
            "This club already pays by card through a Stripe subscription. Cancel that subscription "
            "before switching to invoice billing, so the club isn't charged twice.",
            status=409,
        )
    if org.billing_method == method:
        return
    org.billing_method = method
    org.billing_method_changed_at = _now()
    org.billing_method_changed_by = getattr(user, "id", None)
    await db.commit()


def invoice_out(row: BillingInvoice) -> dict:
    return {
        "id": str(row.id),
        "invoice_number": row.invoice_number,
        "invoice_kind": row.invoice_kind,
        "status": row.status,
        "billing_keys": row.billing_keys or [],
        "line_items": row.line_items,
        "bundle_discount_cents": row.bundle_discount_cents,
        "coupon_code": row.coupon_code,
        "coupon_discount_cents": row.coupon_discount_cents,
        "amount_total_cents": row.amount_total_cents,
        "service_start_date": row.service_start_date.isoformat() if row.service_start_date else None,
        "service_end_date": row.service_end_date.isoformat() if row.service_end_date else None,
        "due_at": row.due_at.isoformat() if row.due_at else None,
        "pay_url": pay_url(row) if row.pay_token and row.status == "open" else None,
        "invoice_pdf": row.invoice_pdf,
        "sent_to_email": row.sent_to_email,
        "emailed_at": row.emailed_at.isoformat() if row.emailed_at else None,
        "email_error": row.email_error,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def overview(db: AsyncSession, org, *, now: datetime | None = None) -> dict:
    """Everything the Account page and the Super Admin panel show about how a
    club pays: the method, who invoices go to, the period held and when its
    renewal invoice goes out, and the invoices still waiting to be paid."""
    now = now or _now()
    admin = await primary_admin(db, org.id)
    renewal, held = invoice_period(org)
    rows = await open_invoices(db, org.id)
    renewal_row = None
    if renewal:
        renewal_row = (await db.execute(
            select(BillingInvoice).where(
                BillingInvoice.organisation_id == org.id,
                BillingInvoice.invoice_kind == KIND_RENEWAL,
                BillingInvoice.service_start_date == renewal,
                BillingInvoice.status.notin_(("void", "uncollectible")),
            )
        )).scalar_one_or_none()
    return {
        "billing_method": org.billing_method or METHOD_CARD,
        # Whether a Super Admin has switched invoicing on for this club. The
        # Account page shows no invoicing option at all while it is off.
        "invoice_billing_enabled": bool(getattr(org, "invoice_billing_enabled", False)),
        "can_use_invoice": not bool(org.stripe_subscription_id),
        "primary_admin": (
            {"name": admin.display_name or admin.username, "email": admin.email} if admin else None
        ),
        "email_live": email_service.email_is_live(),
        "period": {
            "billing_keys": held,
            "renewal_date": renewal.isoformat() if renewal else None,
            "ends_at": due_by(renewal).isoformat() if renewal else None,
            "renewal_invoice_on": (renewal - timedelta(days=RENEWAL_NOTICE_DAYS)).isoformat() if renewal else None,
            "renewal_invoice": invoice_out(renewal_row) if renewal_row else None,
        } if held else None,
        "open_invoices": [invoice_out(r) for r in rows],
        "renewal_notice_days": RENEWAL_NOTICE_DAYS,
    }
