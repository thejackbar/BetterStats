"""The club's billing address in the shape Stripe wants.

Lifted out of routers/billing.py so the invoice-billing path — including the
renewal job, which runs with no request — builds a Stripe Customer the same way
Checkout does. See stripe_address for why a country alone is worth sending.
"""
from __future__ import annotations


# Full country name (what PlayHQ and the Club Directory store — e.g.
# "Australia", not the code Stripe wants) → ISO 3166-1 alpha-2. Kept small
# and additive: today's clubs are AU, UK Play-Cricket is the next expansion.
_COUNTRY_NAME_TO_ISO = {
    "australia": "AU",
    "new zealand": "NZ",
    "united kingdom": "GB",
    "great britain": "GB",
    "england": "GB",
    "scotland": "GB",
    "wales": "GB",
    "northern ireland": "GB",
    "ireland": "IE",
    "south africa": "ZA",
    "india": "IN",
    "united states": "US",
    "usa": "US",
    "united states of america": "US",
}


def country_iso(club) -> str:
    """The club's ISO 3166-1 alpha-2 country code for Stripe (Customer.address
    and automatic tax both want the code, not a full name). Derived so it
    stays correct once non-AU clubs (e.g. UK Play-Cricket) are onboarded,
    rather than blindly hardcoding AU for everything:

    1. A stored country wins (from self-serve registration's address
       resolution — PlayHQ returns a full name like "Australia", so it's
       normalised to a code; an already-2-letter value is used as-is). This
       is the branch a future non-AU club takes — its own onboarding source
       records its real country, which overrides the AU default below.
    2. Otherwise Australia. Every club onboarded today is a Cricket Australia
       club (its identity is a PlayHQ/CA GUID), and there is no non-Australian
       onboarding path yet — so a club with no country on file is Australian.

    This is deliberately NOT gated on the `playhq_id` column: that's a legacy
    field only populated by a low-value PlayHQ Partner-API lookup during sync,
    so it's NULL for many genuinely-Australian clubs (Trinity College (WA)
    among them — which is exactly why gating on it left the Customer with no
    country). Keying the AU default on "no other-country signal" instead of
    on that column is what makes GST + the AU payment methods actually work
    for every current club, while the stored-country branch keeps it honest
    for the non-AU clubs to come."""
    raw = (club.country or "").strip()
    if raw:
        if len(raw) == 2 and raw.isalpha():
            return raw.upper()
        mapped = _COUNTRY_NAME_TO_ISO.get(raw.lower())
        if mapped:
            return mapped
        # An unrecognised non-empty country string — fall through to the AU
        # default rather than sending Stripe something it would reject.
    return "AU"


def stripe_address(club) -> dict | None:
    """Stripe's Address shape ({"line1","city","state","postal_code","country"})
    from what we can determine about the club (see self_serve_trial.
    _resolve_club_address for where the street fields come from).

    Returns None only when the club's country can't be determined at all
    (see country_iso) — automatic_tax then falls back to whatever the payer
    enters at checkout (customer_update: {"address": "auto"} in
    stripe_client.create_checkout_session). When a country IS known it's
    always included even with no street address, because that country alone
    is what makes both of these work from the first checkout attempt:
      * automatic_tax has a jurisdiction to apply tax against (a country-level
        tax like AU GST needs only the country; postcode/state refine it),
        instead of $0 with no country set; and
      * Stripe offers that country's local recurring payment methods (for AU:
        PayTo, BECS Direct Debit) — both are filtered out of Checkout entirely
        when the Customer's country is unknown, leaving only the globally
        available ones (Card, Klarna).
    Street-level fields are added only when present."""
    country = country_iso(club)
    if not country:
        return None
    addr = {"country": country}
    if club.address_line1:
        addr["line1"] = club.address_line1
    if club.suburb:
        addr["city"] = club.suburb
    if club.state:
        addr["state"] = club.state
    if club.postcode:
        addr["postal_code"] = club.postcode
    return addr
