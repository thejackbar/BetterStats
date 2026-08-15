"""Server-side mirror of the public pricing model (frontend/src/data/pricing.js).

The frontend file is the presentation source of truth for the marketing pricing
calculator; this module is the SAME numbers, ported to Python, so a Stripe
Checkout Session (and the invoice-preview quote the Account page shows before
a Primary Admin commits to it) is priced from one place the backend can trust
without round-tripping through the frontend. Keep both files in sync by hand —
there's no shared build step between a Vite frontend and a FastAPI backend.

Prices are in whole AUD dollars everywhere in this module; callers convert to
cents only right before handing an amount to Stripe (which is cents-native).
"""
from __future__ import annotations

CORE = {"key": "core", "name": "BetterStats", "price": 399}

# The four bolt-on modules and their annual price — mirrors PRICED_MODULES in
# pricing.js exactly (key/name/price only; colours/logos/blurb are
# presentation-only and have no backend equivalent).
PRICED_MODULES = [
    {"key": "select", "name": "BetterSelect", "price": 149},
    {"key": "socials", "name": "BetterSocials", "price": 149},
    # Renamed from BetterAdmin (Aug 2026). _ensure_product caches one Stripe
    # Product per billing_key, so this mints no duplicate — but a Product created
    # before the rename keeps its old name until it's renamed in the Stripe
    # dashboard. New checkout line items read BetterClubhouse from here.
    {"key": "admin", "name": "BetterClubhouse", "price": 149},
    {"key": "iq", "name": "BetterIQ", "price": 249},
]
PRICED_MODULE_KEYS = {m["key"] for m in PRICED_MODULES}

# BetterFantasyCricket is priced standalone, deliberately outside the bundle-
# discount maths (mirrors FANTASY in pricing.js).
FANTASY = {"key": "fantasy", "name": "BetterFantasyCricket", "price": 49}

# Bundle discount in whole dollars, keyed on how many of the priced modules
# are selected (not a percentage) — mirrors BUNDLE_DISCOUNT in pricing.js.
# This is the SEED DEFAULT only — the live, super-admin-editable schedule
# lives in platform_settings (see get_bundle_discount_schedule /
# update_bundle_discount_schedule), so a discount change is a General
# Settings save, never a code deploy. Every function below takes an optional
# `schedule` override; callers with DB access (routers/billing.py,
# stripe_client.py) fetch the live one and pass it through — this module
# itself stays a pure, DB-free computation, easy to test in isolation.
BUNDLE_DISCOUNT = {0: 0, 1: 0, 2: 48, 3: 97, 4: 146}

# Every module key the checkout-session endpoint accepts. Core is always
# priced in automatically (price_for() below adds it unconditionally,
# regardless of what's in selected_keys) — it's included here purely so
# selecting the Account page's BetterStats/Core row doesn't 422 as "unknown";
# passing it through selected_keys is a harmless no-op, not a second charge.
# Fantasy is priced but kept outside the bundle discount.
CHECKOUT_MODULE_NAMES = (
    {m["key"]: m["name"] for m in PRICED_MODULES}
    | {FANTASY["key"]: FANTASY["name"], CORE["key"]: CORE["name"]}
)


def bundle_discount(module_count: int, schedule: dict | None = None) -> int:
    """`schedule` maps module-count -> whole-dollar discount (string or int
    keys both accepted, since it round-trips through JSONB where object keys
    are always strings). A count past the highest configured key gets that
    highest key's discount (matches the old fixed "cap at 4 modules"
    behaviour, generalised to however many rows are actually configured —
    so adding a 5th/6th priced module later needs no code change here, just
    a new row in General Settings)."""
    table = {int(k): v for k, v in (schedule or BUNDLE_DISCOUNT).items()}
    if module_count in table:
        return table[module_count]
    if not table:
        return 0
    return table[max(table)] if module_count > max(table) else 0


def price_for(selected_keys, schedule: dict | None = None) -> dict:
    """Price a selection of billable module keys (besides Core, which is always
    included). Returns whole-AUD subtotal/discount/total plus a per-line-item
    breakdown, in the same shape the frontend's priceFor() returns — Fantasy, if
    selected, is priced as its own line item outside the bundle discount.
    `schedule` overrides the seed-default BUNDLE_DISCOUNT table (pass the live,
    super-admin-configured one — see platform_settings.get_bundle_discount_schedule)."""
    keys = set(selected_keys or [])
    bundle_mods = [m for m in PRICED_MODULES if m["key"] in keys]
    line_items = [dict(CORE)] + [dict(m) for m in bundle_mods]
    if FANTASY["key"] in keys:
        line_items.append(dict(FANTASY))
    subtotal = sum(item["price"] for item in line_items)
    # Clamped to the subtotal — a super-admin typo in the (now editable)
    # discount schedule (an extra zero, say) must never produce a negative
    # checkout total.
    discount = min(bundle_discount(len(bundle_mods), schedule), subtotal)
    total = subtotal - discount
    return {
        "line_items": line_items,
        "subtotal": subtotal,
        "discount": discount,
        "total": total,
        "module_count": len(bundle_mods),
    }


def price_for_addon(selected_keys) -> dict:
    """Pricing for module(s) added to an ALREADY-LIVE Stripe subscription —
    no Core line (already being paid for on the existing subscription) and no
    bundle discount (per direct instruction, the bundle discount only applies
    to the initial all-at-once subscribe; adding a module later is always
    priced at that module's plain annual rate). The actual dollar amount the
    club is charged today is a PRORATION of these full prices down to
    whatever's left of the current billing period — that math is Stripe's own
    (see stripe_client.preview_add_modules / add_modules_to_subscription),
    this function only prices the full annual rate each added module will
    renew at from then on."""
    keys = set(selected_keys or [])
    mods = [m for m in PRICED_MODULES if m["key"] in keys]
    if FANTASY["key"] in keys:
        mods = mods + [FANTASY]
    subtotal = sum(m["price"] for m in mods)
    return {"line_items": [dict(m) for m in mods], "subtotal": subtotal, "discount": 0, "total": subtotal}
