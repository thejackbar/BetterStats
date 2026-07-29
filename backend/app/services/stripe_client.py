"""Thin wrapper around the Stripe SDK — Checkout Session creation, subscription
lookups, and webhook signature verification.

Mirrors the shape of services/square_client.py (BetterMerch's Square wrapper):
plain module functions, no persistent client object held between calls. Unlike
Square, this is a SINGLE platform-owned Stripe account (not per-club OAuth) —
every club is billed through the one BetterCricket Stripe account, so there's
no per-org token to look up, just the one api key from settings.

Uses stripe-python's `*_async` methods (httpx-backed) throughout so a Stripe
API call never blocks the event loop — this is an async FastAPI app.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import stripe
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.services import billing_pricing

logger = logging.getLogger(__name__)


class StripeNotConfigured(RuntimeError):
    """Raised when a Stripe call is attempted without api keys configured.
    Callers should turn this into a clean 400/503, never a raw SDK traceback."""


def _require_configured() -> None:
    if not settings.stripe_configured:
        raise StripeNotConfigured("Stripe is not configured (STRIPE_SECRET_KEY/STRIPE_PUBLISHABLE_KEY unset)")
    # stripe-python's api_key is a module-level attribute — safe to set on every
    # call since this process only ever talks to one Stripe account.
    stripe.api_key = settings.stripe_secret_key


def epoch_to_date(ts):
    """A Stripe unix timestamp (e.g. subscription.current_period_end) as a
    plain date, or None. Shared by stripe_billing.py's webhook handlers and
    the add-to-existing-subscription flow below so there's one conversion,
    not two copies drifting apart."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).date() if ts else None


def epoch_to_datetime(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None


async def _ensure_customer(*, org_id: str, club_name: str, email: str | None,
                            address: dict | None = None) -> str:
    """Creates a Stripe Customer carrying the CLUB's own name — a Checkout
    Session that's only given ``customer_email`` (no explicit customer) lets
    Stripe auto-create the Customer at checkout completion using whatever
    name the payer types into the billing-details field, which defaults to
    the cardholder's own name (observed live: "EA BARENDSE" — the card
    holder — instead of the club). Creating the Customer ourselves up front,
    with ``name`` set explicitly, means Checkout always uses OUR chosen
    identity for it, not the payer's. One customer per club — its id is
    persisted onto the org once the session actually completes (see
    stripe_billing.handle_checkout_completed); this is only reached before
    that first completion, so there's nothing to dedupe against yet.

    ``address``, when resolved (see routers/self_serve_trial.py's
    _resolve_club_address), is set directly here so automatic_tax has
    something to calculate against from the very first checkout attempt —
    Stripe's own {"line1", "city", "state", "postal_code", "country"} shape."""
    _require_configured()
    kwargs = {"name": club_name, "email": email, "metadata": {"org_id": str(org_id)}}
    if address:
        kwargs["address"] = address
    customer = await stripe.Customer.create_async(**kwargs)
    return customer["id"]


async def create_checkout_session(db: AsyncSession, *, org_id: str, billing_keys: list[str],
                                   club_name: str,
                                   customer_id: str | None, customer_email: str | None,
                                   customer_address: dict | None = None,
                                   discount_schedule: dict | None = None,
                                   extra_coupon_id: str | None = None, extra_stackable: bool = False,
                                   extra_coupon_code: str | None = None,
                                   extra_coupon_off_dollars: float | None = None,
                                   coupon_redemption_id: str | None = None):
    """A Stripe Checkout Session in subscription mode, priced from
    billing_pricing.price_for (dynamic price_data line items, so no Stripe
    Price objects need pre-creating in the dashboard for every module
    combination). The bundle discount, if any, is applied via a cached
    ``duration=once`` coupon — ONCE means it discounts only the very next
    invoice (the initial subscribe), never a renewal, per direct instruction:
    a club that renews pays full price for every module unless a fresh
    coupon is applied to that specific renewal. ``discount_schedule`` is the
    LIVE, super-admin-configured bundle-discount table
    (platform_settings.get_bundle_discount_schedule) — the caller fetches it
    and passes it straight through; omitted, price_for falls back to its
    hardcoded seed default.

    ``extra_coupon_id`` is a validated discount_coupons.stripe_coupon_id from
    services/discount_coupons.redeem_for_new_signup. A NON-stackable coupon
    (``extra_stackable=False``) WINS outright — passed alone as the
    session's one discount, bundle suppressed, so a deliberately-targeted
    promo code is never silently diluted by the generic bundle schedule.

    A STACKING coupon can NOT simply be added as a second list entry:
    Checkout Session's ``discounts`` accepts at most ONE element — Stripe
    rejects a second with "Array discounts exceeded maximum 1 allowed
    elements" (found live, not documented up front; the SDK's param typing
    allows a list but the API enforces the cap). So a stacking coupon is
    instead pre-combined with the bundle discount into ONE ad-hoc amount_off
    coupon (_ensure_combined_discount_coupon): ``extra_coupon_off_dollars``
    is the coupon's own dollar contribution (computed by the caller with
    routers/billing.py's _apply_coupon_to_quote — the SAME math the /quote
    preview uses, so the real charge matches what was previewed), added to
    the bundle discount. ``extra_coupon_id`` itself (the coupon's own real
    Stripe Coupon object, which may carry a module restriction via
    applies_to.products) is used ONLY in the non-stacking branch — the
    stacking branch bypasses it in favour of the pre-computed flat dollar
    amount, which already accounts for that scoping. Since Stripe genuinely
    can't show two separate discount lines within this one-slot limit, the
    combined coupon's ``name`` spells out both components (e.g. "Bundle
    discount ($48.00) + EARLYBIRD-JUL26 ($162.25 off)") — the best available
    approximation of itemisation on the Stripe invoice itself.
    ``extra_coupon_code`` (the human-entered code, not the Stripe id) drives
    that name and is also stamped into metadata as ``coupon_code`` /
    ``coupon_discount_cents`` alongside ``bundle_discount_cents`` when
    either applies — BetterCricket's OWN billing_invoices row is where the
    true separate breakdown lives for our own reporting (see
    stripe_billing._upsert_invoice), independent of how Stripe's invoice
    can display it.

    org_id + the selected billing_keys are round-tripped through BOTH the
    session's own metadata/client_reference_id AND the subscription's metadata
    — the webhook only ever needs to read one of these depending on which
    event fired, never a second lookup against our own DB to know what was
    bought."""
    _require_configured()
    quote = billing_pricing.price_for(billing_keys, schedule=discount_schedule)

    line_items = [
        {
            "price_data": {
                "currency": settings.stripe_currency,
                "unit_amount": item["price"] * 100,
                "recurring": {"interval": "year"},
                "product_data": {"name": f"BetterCricket — {item['name']}"},
                # GST-exclusive per direct instruction: the advertised price
                # (e.g. $399) is what the club keeps; GST is added on top, not
                # carved out of it. Stripe Tax only actually charges anything
                # once automatic_tax is enabled below AND the account has an
                # active AU GST registration (Dashboard → Settings → Tax).
                "tax_behavior": "exclusive",
            },
            "quantity": 1,
        }
        for item in quote["line_items"]
    ]

    metadata = {"org_id": str(org_id), "billing_keys": ",".join(sorted(billing_keys))}
    if coupon_redemption_id:
        # Read back by stripe_billing.handle_checkout_completed to flip the
        # matching discount_coupon_redemptions row from 'pending' to
        # 'active' once this session's subscription is actually created.
        metadata["coupon_redemption_id"] = str(coupon_redemption_id)
    params = {
        "mode": "subscription",
        "line_items": line_items,
        "client_reference_id": str(org_id),
        "metadata": metadata,
        "subscription_data": {"metadata": metadata},
        # Session-level automatic_tax carries onto the resulting Subscription
        # object itself (Stripe's own behaviour, confirmed against the SDK —
        # subscription_data has no automatic_tax field of its own to set), so
        # renewals keep calculating tax with no extra code.
        # SubscriptionItem.create (the add-on flow below) has no automatic_tax
        # field either — it purely inherits whatever the subscription already
        # has, which is why add_modules_to_subscription re-asserts it via
        # Subscription.modify for a subscription that predates this change.
        "automatic_tax": {"enabled": True},
        "success_url": settings.stripe_checkout_success_url,
        "cancel_url": settings.stripe_checkout_cancel_url,
    }

    discounts: list[dict] = []
    if extra_coupon_id and not extra_stackable:
        # A non-stackable discount-coupon wins outright — the bundle
        # discount is suppressed for this checkout, never combined. Exactly
        # one discount, so no combining needed, and Stripe already shows
        # this coupon under its own real name/code.
        discounts = [{"coupon": extra_coupon_id}]
        if extra_coupon_code:
            metadata["coupon_code"] = extra_coupon_code
            metadata["coupon_discount_cents"] = str(round((extra_coupon_off_dollars or 0) * 100))
    else:
        # Checkout Session allows at most one discounts entry — a stacking
        # coupon and the bundle discount are folded into a single ad-hoc
        # coupon (see the docstring above) rather than passed as two.
        if quote["discount"] > 0:
            metadata["bundle_discount_cents"] = str(round(quote["discount"] * 100))
        combined = quote["discount"]
        if extra_coupon_id:
            combined += extra_coupon_off_dollars or 0
            if extra_coupon_code:
                metadata["coupon_code"] = extra_coupon_code
                metadata["coupon_discount_cents"] = str(round((extra_coupon_off_dollars or 0) * 100))
        if combined > 0:
            if extra_coupon_id and extra_coupon_code:
                coupon_id = await _ensure_combined_discount_coupon(
                    bundle_dollars=quote["discount"], coupon_code=extra_coupon_code,
                    coupon_dollars=extra_coupon_off_dollars or 0,
                )
            else:
                coupon_id = await _ensure_bundle_coupon(db, combined)
            discounts.append({"coupon": coupon_id})

    if discounts:
        params["discounts"] = discounts
    else:
        # Stripe rejects a session that sets BOTH discounts and
        # allow_promotion_codes, so only offer the customer-enterable
        # promotion-code field when no discount (bundle or coupon) is
        # already applying — real promotional codes are created/managed
        # directly in the Stripe Dashboard (Product catalogue → Coupons),
        # no admin UI of our own needed for that.
        params["allow_promotion_codes"] = True

    if customer_id:
        params["customer"] = customer_id
        # An existing Customer can predate address capture — e.g. one created
        # by an earlier checkout attempt that was cancelled before the payer
        # entered a billing address, so it has no country recorded. Push the
        # club's resolved address (always at least {"country": "AU"} now, see
        # routers/billing.py::_stripe_address) so automatic_tax and the AU-only
        # payment methods (PayTo, BECS) work on this attempt too, not just for
        # brand-new Customers. Best-effort — a failure here shouldn't block
        # starting the checkout.
        if customer_address:
            try:
                await stripe.Customer.modify_async(customer_id, address=customer_address)
            except stripe.error.StripeError:
                logger.warning("Could not backfill address on Stripe customer %s", customer_id)
    else:
        # A brand new club (no Stripe customer yet) — create one up front
        # with the club's own name rather than passing customer_email alone
        # (see _ensure_customer's docstring for why that matters).
        params["customer"] = await _ensure_customer(
            org_id=org_id, club_name=club_name, email=customer_email, address=customer_address,
        )
    # automatic_tax needs an address on the Customer to know which
    # jurisdiction to tax — Stripe rejects the session outright without one
    # ("Automatic tax calculation in Checkout requires a valid address on
    # the Customer") once an explicit `customer` is passed (see
    # _ensure_customer above — every session passes one now, always).
    # customer_address, when resolved, is set directly on the Customer at
    # creation so tax is right from the first attempt; this is the fallback
    # for whenever it isn't (a club search couldn't resolve one, or an
    # existing customer predates this) — 'auto' saves whatever the payer
    # types into Checkout's own billing-address field onto the Customer.
    # Deliberately NOT 'name': 'auto' here — that would let Checkout
    # overwrite the club's name back to the cardholder's own name, undoing
    # the fix _ensure_customer exists for.
    params["customer_update"] = {"address": "auto"}

    return await stripe.checkout.Session.create_async(**params)


async def create_setup_session(customer_id: str):
    """A Checkout Session in ``setup`` mode — collects/updates a payment
    method for an already-existing customer, no charge involved. Used when
    the add-on-to-existing-subscription flow's synchronous charge fails
    because the customer has no payment method on file at all (observed
    live: "This customer has no attached payment source or default payment
    method" from SubscriptionItem.create's proration invoice) — instead of
    a dead-end error, the club is bounced here to add a card, then
    redirected back to /admin/account to retry the same add-on purchase
    (see is_missing_payment_method_error below and AdminAccount.jsx's
    sessionStorage-based retry-on-return)."""
    _require_configured()
    return await stripe.checkout.Session.create_async(
        mode="setup",
        # Unlike subscription/payment mode (where currency comes from the
        # line items), a setup-mode session has no line items to infer it
        # from — Stripe rejects the call outright without one ("Missing
        # required param: currency"), found live.
        currency=settings.stripe_currency,
        customer=customer_id,
        success_url=settings.stripe_checkout_success_url,
        cancel_url=settings.stripe_checkout_cancel_url,
    )


def is_missing_payment_method_error(e) -> bool:
    """True for the specific Stripe failure a customer with no payment
    method on file produces when we try to charge them synchronously (the
    add-on flow's proration invoice) — matched on message text since Stripe
    doesn't expose a distinct machine-readable error code for this case, only
    a human-readable one ("This customer has no attached payment source or
    default payment method...")."""
    msg = (getattr(e, "user_message", None) or str(e) or "").lower()
    return "no attached payment source" in msg or "no default payment method" in msg


async def retrieve_subscription(subscription_id: str):
    _require_configured()
    return await stripe.Subscription.retrieve_async(subscription_id)


async def retrieve_payment_intent(payment_intent_id: str):
    _require_configured()
    return await stripe.PaymentIntent.retrieve_async(payment_intent_id, expand=["payment_method"])


def invoice_payment_intent_id(invoice: dict) -> str | None:
    """The PaymentIntent an invoice was paid with. Mirrors
    stripe_billing._invoice_subscription_id's defensive both-shapes read —
    this account's Stripe API version has already been found (live) to nest
    invoice.subscription somewhere this SDK doesn't expect
    (parent.subscription_details.subscription instead of the flat field),
    so the same restructuring plausibly reaches payment_intent too even
    though that specific move hasn't been directly observed — cheap to
    guard against regardless."""
    direct = invoice.get("payment_intent")
    if direct:
        return direct if isinstance(direct, str) else direct.get("id")
    parent = invoice.get("parent") or {}
    nested = (parent.get("subscription_details") or {}).get("payment_intent")
    if nested:
        return nested if isinstance(nested, str) else nested.get("id")
    return None


def describe_payment_method(pm: dict) -> tuple[str, str]:
    """(type, human-readable summary) for a Stripe PaymentMethod object, for
    Billing History display — e.g. ('card', 'Visa Debit •••• 4242'),
    ('card', 'Apple Pay •••• 4242'), ('au_becs_debit', 'BECS (BSB 123-456,
    Account •••• 6789)'). Defensive about every type: an unrecognised or
    partially-shaped payment method falls back to a generic label rather
    than raising, since this is cosmetic Billing History detail, never
    something that should be allowed to break recording a payment.
    ``payto`` specifically isn't in this SDK's own type stubs at all (AU
    PayTo is confirmed live on this account's Checkout page — a real
    payment method — but stripe-python 10.12.0 doesn't model it yet), so
    its field shape here is a best-effort guess pending live verification,
    not confirmed against real PayTo payment method data."""
    pm_type = pm.get("type") or "unknown"
    if pm_type == "card":
        card = pm.get("card") or {}
        last4 = card.get("last4") or "????"
        wallet = (card.get("wallet") or {}).get("type")
        if wallet == "apple_pay":
            return pm_type, f"Apple Pay •••• {last4}"
        if wallet == "google_pay":
            return pm_type, f"Google Pay •••• {last4}"
        funding = (card.get("funding") or "").lower()
        brand = (card.get("brand") or "Card").capitalize()
        label = f"{brand} {funding.capitalize()}" if funding and funding != "unknown" else brand
        return pm_type, f"{label} •••• {last4}"
    if pm_type == "au_becs_debit":
        becs = pm.get("au_becs_debit") or {}
        bsb = becs.get("bsb_number") or "???-???"
        last4 = becs.get("last4") or "????"
        return pm_type, f"BECS (BSB {bsb}, Account •••• {last4})"
    if pm_type == "payto":
        # Best-effort — see docstring. Tries the field names a mobile-number
        # or BSB/account identifier would plausibly use; falls back to a
        # bare label rather than guessing wrong.
        payto = pm.get("payto") or {}
        identifier = (
            payto.get("mobile_number") or payto.get("phone") or payto.get("pan")
            or payto.get("bsb_number") and f"BSB {payto['bsb_number']}"
        )
        return pm_type, f"PayTo ({identifier})" if identifier else "PayTo"
    return pm_type, pm_type.replace("_", " ").title()


async def cancel_subscription(subscription_id: str) -> None:
    """Cancels a subscription immediately (not at period end) — used when a
    club's self-service cancel leaves it with zero held modules, so Stripe
    stops billing it and the eventual customer.subscription.deleted webhook
    is a harmless no-op (the org's stripe_subscription_id is already cleared
    by the caller). A subscription already gone on Stripe's side (deleted
    directly in the dashboard, or a race with the webhook) raises
    InvalidRequestError, which callers should swallow — there's nothing left
    to cancel."""
    _require_configured()
    await stripe.Subscription.cancel_async(subscription_id)


async def _ensure_bundle_coupon(db: AsyncSession, discount_dollars: float) -> str:
    """Reuses ONE Stripe Coupon per distinct discount amount instead of
    minting a fresh one on every checkout attempt — cached in
    stripe_coupons (migration 153), keyed on the dollar amount alone since
    duration is fixed at 'once' for every bundle coupon today (if duration
    ever becomes independently configurable, key on (amount, duration)
    instead). Mirrors _ensure_product below. Only ever called for the PURE
    bundle-discount case (no coupon code involved) — a bundle discount
    combined with a coupon code goes through _ensure_combined_discount_coupon
    instead, which needs a descriptive per-redemption name and so isn't
    cached the same way."""
    cents = round(discount_dollars * 100)
    row = (await db.execute(
        text("SELECT stripe_coupon_id FROM stripe_coupons WHERE discount_cents = :c"),
        {"c": cents},
    )).first()
    if row:
        return row[0]
    _require_configured()
    coupon = await stripe.Coupon.create_async(
        amount_off=cents,
        currency=settings.stripe_currency,
        duration="once",
        name=f"Bundle discount (${discount_dollars:.2f} off first payment)",
    )
    # Same race-tolerance note as _ensure_product — a concurrent duplicate
    # is harmless Dashboard clutter, not worth locking for.
    await db.execute(
        text(
            "INSERT INTO stripe_coupons (discount_cents, stripe_coupon_id) VALUES (:c, :p) "
            "ON CONFLICT (discount_cents) DO NOTHING"
        ),
        {"c": cents, "p": coupon["id"]},
    )
    await db.commit()
    return coupon["id"]


async def _ensure_combined_discount_coupon(*, bundle_dollars: float, coupon_code: str, coupon_dollars: float) -> str:
    """A one-off Stripe Coupon combining the bundle discount and a stacking
    discount-coupon into the single slot Checkout Session's ``discounts``
    allows (see create_checkout_session's docstring for why they can't be
    two list entries). NOT cached like _ensure_bundle_coupon — this exact
    combination (bundle amount + specific code + that code's own dollar
    contribution, which itself depends on the module selection) is unlikely
    to repeat, so a fresh Coupon per redemption is simpler than a cache key
    that would rarely hit. Its ``name`` spells out both components, since
    that's the only way Stripe shows any breakdown at all within the
    one-discount limit — BetterCricket's own billing_invoices row carries
    the real separate amounts for our own reporting regardless."""
    _require_configured()
    total_cents = round((bundle_dollars + coupon_dollars) * 100)
    name = f"Bundle discount (${bundle_dollars:.2f}) + {coupon_code} (${coupon_dollars:.2f} off)"
    coupon = await stripe.Coupon.create_async(
        amount_off=total_cents,
        currency=settings.stripe_currency,
        duration="once",
        name=name,
    )
    return coupon["id"]


# ─── Payment method management (Primary Admin's Account page + Super Admin) ─
# A club's Stripe Customer can hold several saved payment methods (add a
# backup card, switch which one bills the renewal). Customer.list_payment_
# methods (not the older PaymentMethod.list, which requires a `type` filter
# per call) returns every type registered on the account in one call.

async def list_payment_methods(customer_id: str) -> dict:
    """Every saved payment method for a club's Stripe Customer, plus which
    one (if any) is its default for future invoices/renewals."""
    _require_configured()
    customer = await stripe.Customer.retrieve_async(customer_id)
    default_id = (customer.get("invoice_settings") or {}).get("default_payment_method")
    if isinstance(default_id, dict):
        default_id = default_id.get("id")
    methods = await stripe.Customer.list_payment_methods_async(customer_id)
    return {"default_payment_method_id": default_id, "payment_methods": methods.get("data", [])}


async def set_default_payment_method(customer_id: str, payment_method_id: str) -> None:
    _require_configured()
    await stripe.Customer.modify_async(
        customer_id, invoice_settings={"default_payment_method": payment_method_id},
    )


async def detach_payment_method(payment_method_id: str) -> None:
    """Removes a payment method from the customer entirely — callers must
    have already confirmed it's not the club's only one on file (see
    routers/billing.py's _remove_payment_method_for, which enforces that
    rule before this is ever reached)."""
    _require_configured()
    await stripe.PaymentMethod.detach_async(payment_method_id)


def construct_webhook_event(payload: bytes, sig_header: str):
    """Verifies the Stripe-Signature header (local HMAC check, no network call)
    and returns the parsed Event. Raises stripe.error.SignatureVerificationError
    on a bad/missing signature — callers must treat that as a hard reject
    (400), never process the payload unverified."""
    if not settings.stripe_webhook_secret:
        raise StripeNotConfigured("Stripe webhook secret not set")
    return stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)


# ─── Adding modules to an ALREADY-LIVE subscription ────────────────────────
# Unlike create_checkout_session's line items (which support an inline ad-hoc
# product via price_data.product_data), Stripe's SubscriptionItem.create and
# Invoice.create_preview require a real Product id when using price_data —
# there's no inline product creation on those two endpoints. _ensure_product
# creates each billable module's Product exactly once (migration 152 caches
# the id in our own DB) rather than re-creating it — or searching for it — on
# every add-on checkout.

async def _ensure_product(db: AsyncSession, billing_key: str) -> str:
    row = (await db.execute(
        text("SELECT stripe_product_id FROM stripe_products WHERE billing_key = :k"),
        {"k": billing_key},
    )).first()
    if row:
        return row[0]
    _require_configured()
    name = billing_pricing.CHECKOUT_MODULE_NAMES.get(billing_key, billing_key)
    product = await stripe.Product.create_async(
        name=f"BetterCricket — {name}", metadata={"billing_key": billing_key},
    )
    # A concurrent request could race this and create a second, orphaned
    # Product in Stripe — harmless (an unused Product sitting in the
    # dashboard) and not worth locking for on a low-frequency admin action.
    await db.execute(
        text(
            "INSERT INTO stripe_products (billing_key, stripe_product_id) VALUES (:k, :p) "
            "ON CONFLICT (billing_key) DO NOTHING"
        ),
        {"k": billing_key, "p": product["id"]},
    )
    await db.commit()
    return product["id"]


async def _addon_price_data_items(db: AsyncSession, billing_keys: list[str]) -> list[dict]:
    quote = billing_pricing.price_for_addon(billing_keys)
    items = []
    for item in quote["line_items"]:
        product_id = await _ensure_product(db, item["key"])
        items.append({
            "price_data": {
                "currency": settings.stripe_currency,
                "product": product_id,
                "unit_amount": item["price"] * 100,
                "recurring": {"interval": "year"},
                "tax_behavior": "exclusive",
            },
            "quantity": 1,
        })
    return items


async def preview_add_modules(db: AsyncSession, subscription_id: str, billing_keys: list[str]) -> dict:
    """Stripe's own invoice preview for adding new items to an existing
    subscription — the EXACT prorated amount Stripe would charge today, not
    an approximation we compute from day-counts ourselves. No bundle discount
    (see billing_pricing.price_for_addon — that only applies to the initial
    all-at-once subscribe): `discounts=""` explicitly excludes ANY discount
    inherited from the subscription, because a `duration=once` bundle coupon
    can still be sitting on the subscription (not yet consumed by a regular
    invoice) and would otherwise silently apply here too — the SDK's own
    param typing requires the literal empty string; an empty list is a no-op
    and still inherits it. add_modules_to_subscription mirrors this by
    deleting the discount outright before the real charge.

    Each returned line item carries the module's full annual price alongside
    the prorated amount (so the frontend can show full price → prorata
    deduction → charged-today, per module) — matched to billing_keys by
    position, since price_for_addon/_addon_price_data_items build both the
    Stripe items and this quote's line_items from the same PRICED_MODULES/
    FANTASY order."""
    _require_configured()
    quote = billing_pricing.price_for_addon(billing_keys)
    if not quote["line_items"]:
        return {"line_items": [], "total": 0, "currency": settings.stripe_currency}
    items = await _addon_price_data_items(db, billing_keys)
    preview = await stripe.Invoice.create_preview_async(
        subscription=subscription_id,
        subscription_details={"items": items, "proration_behavior": "always_invoice"},
        # Explicit here (not just relying on the subscription's own setting)
        # so the preview is accurate even for a subscription created before
        # automatic tax was wired up — add_modules_to_subscription below
        # re-asserts it on the subscription itself for the same reason.
        automatic_tax={"enabled": True},
        discounts="",
    )
    raw_lines = (preview.get("lines") or {}).get("data", [])
    line_items = []
    for i, mod in enumerate(quote["line_items"]):
        prorated = (raw_lines[i].get("amount") or 0) / 100 if i < len(raw_lines) else 0.0
        full_price = mod["price"]
        line_items.append({
            "key": mod["key"],
            "name": mod["name"],
            "full_price": full_price,
            "deduction": round(full_price - prorated, 2),
            "amount": prorated,
        })
    return {
        "line_items": line_items,
        "total": (preview.get("total") or 0) / 100,
        "currency": preview.get("currency") or settings.stripe_currency,
    }


async def add_modules_to_subscription(db: AsyncSession, subscription_id: str,
                                       existing_billing_keys: list[str], new_billing_keys: list[str]):
    """Adds new_billing_keys as items on an already-live subscription,
    charging the prorated amount immediately (proration_behavior=
    always_invoice) against the payment method already on file — there's
    nothing new to collect, so this never redirects to a Checkout Session.
    Updates the subscription's own metadata.billing_keys to the union of
    old+new so future invoice.paid renewals (stripe_billing.py) keep
    including the newly added module. Returns the updated Subscription
    (current_period_end drives the renewal_date the caller grants with)."""
    _require_configured()
    try:
        # Mirrors preview_add_modules's discounts="" — a duration=once bundle
        # coupon can still be attached to the subscription if it hasn't yet
        # been consumed by a regular invoice. Per direct instruction, a
        # module added after the initial subscribe never gets the bundle
        # discount, so it's stripped outright before the proration invoice
        # below is generated (proration_behavior=always_invoice would
        # otherwise apply any discount still on the subscription to it).
        # No-op (raises) when there's nothing to remove — that's the
        # desired end state either way, so the error is swallowed.
        await stripe.Subscription.delete_discount_async(subscription_id)
    except stripe.error.StripeError:
        pass
    items = await _addon_price_data_items(db, new_billing_keys)
    for item in items:
        await stripe.SubscriptionItem.create_async(
            subscription=subscription_id,
            proration_behavior="always_invoice",
            **item,
        )
    all_keys = sorted(set(existing_billing_keys) | set(new_billing_keys))
    return await stripe.Subscription.modify_async(
        subscription_id,
        metadata={"billing_keys": ",".join(all_keys)},
        # Re-asserted (not just relied on from session creation) so a
        # subscription that predates automatic tax being wired up also picks
        # it up from here on — SubscriptionItem.create has no automatic_tax
        # field of its own to set at item-creation time.
        automatic_tax={"enabled": True},
    )


# ─── BetterCricket-managed discount coupons (migration 154) ────────────────
# Super Admin manages the whole catalogue inside BetterCricket — see
# services/discount_coupons.py, which owns every eligibility rule (module
# coverage, redemption windows, duration, max redemptions, stackability).
# These two functions are the ONLY place BetterCricket talks to Stripe about
# a discount_coupons row: creating the mirrored Coupon object once, and
# attaching it to an already-live subscription ahead of its next renewal.

async def sync_coupon_to_stripe(db: AsyncSession, coupon) -> str:
    """Creates the Stripe Coupon backing a discount_coupons row. Called once,
    from services/discount_coupons.create_coupon — Stripe Coupons are
    immutable on their financial terms after creation, which is exactly why
    update_coupon locks those fields once a coupon has a live redemption
    (there would be nothing to re-sync).

    Deliberately sets NO ``redeem_by``/``max_redemptions`` on the Stripe side
    — BetterCricket's own columns are the sole eligibility gate (see
    discount_coupons.validate_redemption), so there is exactly one place a
    redemption is decided, never two systems that could disagree.

    ``applies_to.products`` restricts the discount to the coupon's covered
    modules (None/empty = every module, i.e. no restriction) — reuses the
    SAME Stripe Product per billing_key that _ensure_product already caches
    for the add-on-module flow, so a covered vs non-covered module split on
    one invoice is handled natively by Stripe, no extra bookkeeping here."""
    _require_configured()
    kwargs: dict = {
        "duration": coupon.duration_mode,
        "name": coupon.display_name,
    }
    if coupon.discount_type == "percent":
        kwargs["percent_off"] = float(coupon.discount_value)
    else:
        kwargs["amount_off"] = int(round(float(coupon.discount_value) * 100))
        kwargs["currency"] = settings.stripe_currency
    if coupon.duration_mode == "repeating":
        kwargs["duration_in_months"] = int(coupon.duration_renewals or 1) * 12
    module_keys = coupon.module_keys or []
    if module_keys:
        product_ids = [await _ensure_product(db, key) for key in module_keys]
        kwargs["applies_to"] = {"products": product_ids}
    created = await stripe.Coupon.create_async(**kwargs)
    return created["id"]


async def attach_discount_to_subscription(subscription_id: str, coupon_id: str) -> None:
    """Queues a discount-coupon onto an ALREADY-LIVE subscription — Stripe
    applies a subscription-level discount starting at the NEXT invoice the
    subscription generates, never retroactively against an already-issued
    one, so this is exactly "apply ahead of the renewal date" with no
    proration or immediate charge triggered.

    Fetches the subscription's current discounts and APPENDS rather than
    overwrites — Subscription.modify's ``discounts`` param replaces the
    whole list, so blindly setting ``discounts=[{coupon: new_id}]`` would
    silently evict a different coupon a club redeemed earlier for the same
    upcoming renewal."""
    _require_configured()
    # expand=["discounts"] turns the array of Discount IDs into full Discount
    # objects; each object's own `coupon` field is a plain string ID unless
    # separately expanded (which isn't needed here — just the id).
    sub = await stripe.Subscription.retrieve_async(subscription_id, expand=["discounts"])
    existing_ids = []
    for d in (sub.get("discounts") or []):
        if not isinstance(d, dict):
            continue
        coupon_ref = d.get("coupon")
        cid = coupon_ref.get("id") if isinstance(coupon_ref, dict) else coupon_ref
        if cid and cid != coupon_id:
            existing_ids.append(cid)
    all_ids = existing_ids + [coupon_id]
    await stripe.Subscription.modify_async(
        subscription_id,
        discounts=[{"coupon": cid} for cid in all_ids],
    )


# ─── Super-admin raised invoices (send-invoice subscriptions) ──────────────
# The Super Admin financial page can raise a club a shareable, payable invoice
# instead of walking them through Checkout. In Stripe terms that's a recurring
# Subscription created directly (no Checkout Session) with
# collection_method='send_invoice': Stripe issues the first invoice, we
# finalize it immediately to get its number + hosted_invoice_url (the "pay this
# invoice" page), and the club settles it at their leisure. Entitlement is
# still granted only when the club actually pays (invoice.paid webhook reads
# the subscription's metadata.billing_keys), identical to the Checkout path —
# this just replaces "collect the card now" with "here's a link, pay when you
# can".


async def _one_discount_for_subscription(
    db: AsyncSession, *, bundle_dollars: float,
    extra_coupon_id: str | None, extra_stackable: bool,
    extra_coupon_code: str | None, extra_coupon_off_dollars: float | None,
) -> tuple[list[dict], dict]:
    """Builds the single ``discounts`` entry (and the metadata breakdown) for a
    send-invoice subscription, mirroring create_checkout_session's own rule so
    the amount raised matches what /quote previewed: a non-stackable coupon
    wins outright; a stacking coupon is folded together with the bundle
    discount into one ad-hoc coupon; a pure bundle discount uses the cached
    per-amount coupon. Returns (discounts, metadata_fragment)."""
    metadata: dict = {}
    if extra_coupon_id and not extra_stackable:
        if extra_coupon_code:
            metadata["coupon_code"] = extra_coupon_code
            metadata["coupon_discount_cents"] = str(round((extra_coupon_off_dollars or 0) * 100))
        return [{"coupon": extra_coupon_id}], metadata

    if bundle_dollars > 0:
        metadata["bundle_discount_cents"] = str(round(bundle_dollars * 100))
    combined = bundle_dollars
    if extra_coupon_id:
        combined += extra_coupon_off_dollars or 0
        if extra_coupon_code:
            metadata["coupon_code"] = extra_coupon_code
            metadata["coupon_discount_cents"] = str(round((extra_coupon_off_dollars or 0) * 100))
    if combined <= 0:
        return [], metadata
    if extra_coupon_id and extra_coupon_code:
        coupon_id = await _ensure_combined_discount_coupon(
            bundle_dollars=bundle_dollars, coupon_code=extra_coupon_code,
            coupon_dollars=extra_coupon_off_dollars or 0,
        )
    else:
        coupon_id = await _ensure_bundle_coupon(db, combined)
    return [{"coupon": coupon_id}], metadata


async def create_subscription_send_invoice(
    db: AsyncSession, *, org_id: str, billing_keys: list[str], club_name: str,
    customer_id: str | None, customer_email: str | None, customer_address: dict | None,
    days_until_due: int = 14, discount_schedule: dict | None = None,
    extra_coupon_id: str | None = None, extra_stackable: bool = False,
    extra_coupon_code: str | None = None, extra_coupon_off_dollars: float | None = None,
    source: str = "super_invoice",
) -> dict:
    """Creates a recurring Subscription billed by emailed invoice
    (collection_method='send_invoice') for the club's selected modules, priced
    from billing_pricing.price_for (Core + selection, bundle discount), and
    finalizes its first invoice so a payable hosted-invoice link exists right
    away. Returns {"subscription": <sub>, "customer_id": str, "invoice":
    {id, number, hosted_invoice_url, invoice_pdf, total, tax, amount_due,
    status}}. The caller persists customer_id/subscription_id onto the org.

    days_until_due is how long the club has to pay before the invoice is past
    due (Stripe still keeps the link live). No card is collected up front —
    entitlement is granted by the invoice.paid webhook once the club pays."""
    _require_configured()
    quote = billing_pricing.price_for(billing_keys, schedule=discount_schedule)

    if not customer_id:
        customer_id = await _ensure_customer(
            org_id=org_id, club_name=club_name, email=customer_email, address=customer_address,
        )
    elif customer_address:
        try:
            await stripe.Customer.modify_async(customer_id, address=customer_address)
        except stripe.error.StripeError:
            logger.warning("Could not backfill address on Stripe customer %s", customer_id)

    items = []
    for item in quote["line_items"]:
        product_id = await _ensure_product(db, item["key"])
        items.append({
            "price_data": {
                "currency": settings.stripe_currency,
                "product": product_id,
                "unit_amount": item["price"] * 100,
                "recurring": {"interval": "year"},
                "tax_behavior": "exclusive",
            },
            "quantity": 1,
        })

    metadata = {
        "org_id": str(org_id),
        "billing_keys": ",".join(sorted(billing_keys)),
        # Read back by stripe_billing._upsert_invoice so Billing History marks
        # where the invoice came from (a super-admin raise vs a plain renewal).
        "bs_invoice_source": source,
    }
    discounts, meta_frag = await _one_discount_for_subscription(
        db, bundle_dollars=quote["discount"], extra_coupon_id=extra_coupon_id,
        extra_stackable=extra_stackable, extra_coupon_code=extra_coupon_code,
        extra_coupon_off_dollars=extra_coupon_off_dollars,
    )
    metadata.update(meta_frag)

    params = {
        "customer": customer_id,
        "items": items,
        "collection_method": "send_invoice",
        "days_until_due": days_until_due,
        "metadata": metadata,
        "automatic_tax": {"enabled": True},
        # Don't auto-finalize an hour later — we finalize the first invoice
        # ourselves below so the payable link exists immediately.
        "expand": ["latest_invoice"],
    }
    if discounts:
        params["discounts"] = discounts

    sub = await stripe.Subscription.create_async(**params)

    invoice = sub.get("latest_invoice")
    invoice_id = invoice.get("id") if isinstance(invoice, dict) else invoice
    finalized = None
    if invoice_id:
        # A send-invoice subscription's first invoice starts as a draft;
        # finalizing it assigns the number + hosted_invoice_url and makes it
        # payable now instead of waiting for Stripe's ~1h auto-finalize.
        try:
            finalized = await stripe.Invoice.finalize_invoice_async(invoice_id)
        except stripe.error.StripeError:
            logger.exception("Could not finalize invoice %s for new subscription %s", invoice_id, sub.get("id"))
            finalized = invoice if isinstance(invoice, dict) else None

    inv_out = None
    if isinstance(finalized, dict):
        inv_out = {
            "id": finalized.get("id"),
            "number": finalized.get("number"),
            "hosted_invoice_url": finalized.get("hosted_invoice_url"),
            "invoice_pdf": finalized.get("invoice_pdf"),
            "total": (finalized.get("total") or 0) / 100,
            "tax": (finalized.get("tax") or 0) / 100,
            "amount_due": (finalized.get("amount_due") or 0) / 100,
            "status": finalized.get("status"),
        }
    # ``raw_invoice`` is the full finalized invoice dict (number, hosted_invoice_url,
    # tax, lines) so the caller can pre-record it into billing_invoices without
    # waiting for the invoice.finalized webhook. The subscription's own
    # ``latest_invoice`` is still the pre-finalize draft, so don't use that.
    return {
        "subscription": sub, "customer_id": customer_id,
        "invoice": inv_out, "raw_invoice": finalized if isinstance(finalized, dict) else None,
    }


async def retrieve_invoice(invoice_id: str) -> dict:
    """Full live detail for one Stripe invoice, for the financial page's
    invoice drilldown — covers unpaid/open invoices too (the stored
    billing_invoices mirror only fills in fully once paid). Returns a flat,
    already-dollar-scaled shape; ``discounts`` lists each applied
    coupon's name and dollar amount off from total_discount_amounts."""
    _require_configured()
    inv = await stripe.Invoice.retrieve_async(
        invoice_id, expand=["discounts", "total_discount_amounts.discount"],
    )
    discounts = []
    for d in (inv.get("total_discount_amounts") or []):
        amount = (d.get("amount") or 0) / 100
        disc = d.get("discount")
        name = None
        if isinstance(disc, dict):
            coupon = disc.get("coupon")
            if isinstance(coupon, dict):
                name = coupon.get("name")
        discounts.append({"name": name, "amount": amount})
    lines = [
        {"name": ln.get("description") or "", "amount": (ln.get("amount") or 0) / 100}
        for ln in ((inv.get("lines") or {}).get("data") or [])
    ]
    return {
        "id": inv.get("id"),
        "number": inv.get("number"),
        "status": inv.get("status"),
        "currency": inv.get("currency") or settings.stripe_currency,
        "subtotal": (inv.get("subtotal") or 0) / 100,
        "tax": (inv.get("tax") or 0) / 100,
        "total": (inv.get("total") or 0) / 100,
        "amount_due": (inv.get("amount_due") or 0) / 100,
        "amount_paid": (inv.get("amount_paid") or 0) / 100,
        "amount_remaining": (inv.get("amount_remaining") or 0) / 100,
        "hosted_invoice_url": inv.get("hosted_invoice_url"),
        "invoice_pdf": inv.get("invoice_pdf"),
        "discounts": discounts,
        "lines": lines,
        "created": epoch_to_datetime(inv.get("created")).isoformat() if inv.get("created") else None,
    }
