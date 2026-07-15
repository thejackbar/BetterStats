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
    {"key": "admin", "name": "BetterAdmin", "price": 149},
    {"key": "iq", "name": "BetterIQ", "price": 249},
]
PRICED_MODULE_KEYS = {m["key"] for m in PRICED_MODULES}

# BetterFantasyCricket is priced standalone, deliberately outside the bundle-
# discount maths (mirrors FANTASY in pricing.js).
FANTASY = {"key": "fantasy", "name": "BetterFantasyCricket", "price": 49}

# Bundle discount in whole dollars, keyed on how many of the four PRICED_MODULES
# are selected (not a percentage) — mirrors BUNDLE_DISCOUNT in pricing.js.
BUNDLE_DISCOUNT = {0: 0, 1: 0, 2: 48, 3: 97, 4: 146}

# Every module a Primary Admin can actually check out for — Core is implicit
# (always included, never a line item to "select"), Fantasy is priced but
# outside the bundle.
CHECKOUT_MODULE_NAMES = {m["key"]: m["name"] for m in PRICED_MODULES} | {FANTASY["key"]: FANTASY["name"]}


def bundle_discount(module_count: int) -> int:
    return BUNDLE_DISCOUNT.get(module_count, BUNDLE_DISCOUNT[4] if module_count > 4 else 0)


def price_for(selected_keys) -> dict:
    """Price a selection of billable module keys (besides Core, which is always
    included). Returns whole-AUD subtotal/discount/total plus a per-line-item
    breakdown, in the same shape the frontend's priceFor() returns — Fantasy, if
    selected, is priced as its own line item outside the bundle discount."""
    keys = set(selected_keys or [])
    bundle_mods = [m for m in PRICED_MODULES if m["key"] in keys]
    discount = bundle_discount(len(bundle_mods))
    line_items = [dict(CORE)] + [dict(m) for m in bundle_mods]
    if FANTASY["key"] in keys:
        line_items.append(dict(FANTASY))
    subtotal = sum(item["price"] for item in line_items)
    total = subtotal - discount
    return {
        "line_items": line_items,
        "subtotal": subtotal,
        "discount": discount,
        "total": total,
        "module_count": len(bundle_mods),
    }
