# Archive: billing-stripe-and-invoicing

Verbatim history moved out of `CLAUDE.md` on 2026-09-30. NOT loaded into context automatically.
Scope: Billing checkout flag, Stripe subscriptions, coupons, pay-by-invoice.
Read the distilled rules first: `docs/dev-notes/guides/billing-stripe-and-invoicing.md`. Open this file only when you need the full reasoning, measurements or history behind a rule, and search it (grep) rather than reading it whole.
Sections are in their original relative order. The `BEGIN`/`END` comments carry the line range in the untouched copy `CLAUDE.original-2026-09-30.md`.

<!-- BEGIN original CLAUDE.md L14594-14627 -->
## Billing checkout — feature-flagged while it's built (v8.65.0, Jul 2026)

The Account page's SUBSCRIBE button (`AdminAccount.jsx`, Phase 19) has always
been a deliberate stub ("Online subscribing isn't connected yet…"). Work is
now starting on the real thing — preparing bills/invoices, then a Stripe
checkout link — and per direct instruction a Primary Admin must **not** be
able to click through any of it until the team is satisfied it works, even as
pieces of the real flow land on `main`.

- **`platform_settings.billing_checkout_enabled`** (new boolean key in the
  existing `_BOOL_KEYS` allowlist, same JSONB singleton as
  `self_serve_registration_enabled`/`onboarding_wizard_enabled`/
  `trial_nudges_enabled` — no migration needed). Off by default.
  `get_billing_checkout_enabled(db)` reads it; **`require_billing_checkout_enabled`**
  is a ready-to-use FastAPI dependency (`Depends(require_billing_checkout_enabled)`)
  that 403s a route while the flag is off — **every new invoicing/Stripe-checkout
  endpoint must depend on it as it's built**, since the frontend gate is UX
  only and can't be trusted as the real block.
- **Super admin control**: `GET`/`PATCH /club-admin/super/general-settings`
  carries `billing_checkout_enabled` alongside the other flags; a "Billing (in
  progress)" toggle in `SuperClubs.jsx`'s General Settings modal.
- **Frontend**: `GET /club-admin/account/plan` now returns
  `billing_checkout_enabled` alongside `modules`/`is_primary_admin`.
  `AdminAccount.jsx`'s `submitSubscribe` is where the real checkout call will
  eventually go — for now it always shows the stub notice, but the flag and
  its comment are already in place so the real implementation branches on
  `plan.billing_checkout_enabled` from the start instead of needing a
  follow-up safety retrofit.
- **Turning it on**: only once the invoicing/checkout build is tested and
  ready to go live — flip `billing_checkout_enabled` on from General
  Settings. There is no staging environment, so (same as the other
  self-serve-onboarding flags) this switch is the only thing standing between
  "merged" and "a real club paying through it".

<!-- END original CLAUDE.md L14594-14627 -->
<!-- BEGIN original CLAUDE.md L14628-15067 -->
## Stripe Checkout — recurring subscription billing (migration 150, Jul 2026)

The real build behind the flag above: a Primary Admin's selected modules
become a single recurring **Stripe Subscription** per club (one Stripe
Customer/Subscription covers every module the club buys through Stripe, not
one subscription per module), priced from the SAME numbers as the public
pricing calculator. Everything here is still gated by
`platform_settings.billing_checkout_enabled` (off by default) — this schema
and code can sit on `main` fully inert until a super admin flips it on, and
Stripe keys are configured.

- **`services/billing_pricing.py`** is a hand-kept Python port of
  `frontend/src/data/pricing.js` (`CORE` $399, the four `PRICED_MODULES` at
  $149/$149/$149/$249, `BUNDLE_DISCOUNT` $0/$0/$48/$97/$146, `FANTASY` $49
  priced standalone outside the bundle). `price_for(selected_keys)` is the ONE
  place both the invoice-preview quote and the real Checkout Session line
  items are computed from — no separate "what Stripe charges" number to drift
  out of sync with "what the app shows". Verified against pricing.js: Core +
  all four modules totals **$949**, matching `ALL_IN`. Keep both files in sync
  by hand; there's no shared build step between the Vite frontend and FastAPI
  backend.
- **No pre-created Stripe Price objects** — `services/stripe_client.py`
  builds each Checkout Session line item from `price_data` on the fly
  (recurring, `interval: year`, `unit_amount` from `billing_pricing`), so a
  new module or a price change never needs a matching dashboard edit. The
  bundle discount, when any, is applied via a cached `duration: once` Coupon
  (see "Bundle discount coupon fixes" below — this used to say `forever`,
  which was wrong).
- **Migration 150** (mirrored idempotently in `main.py`'s lifespan, same
  pattern as every recent migration): `organisations.stripe_customer_id` /
  `.stripe_subscription_id` (set by the webhook once a checkout completes),
  and `billing_invoices` — a local mirror of each Stripe Invoice event so the
  Account page's Billing History never calls the Stripe API directly.
  `billing_invoices.line_items` is OUR OWN `price_for()` snapshot at the
  moment the invoice landed, not Stripe's own line items, so it always reads
  in the same module/price shape the rest of the app uses.
- **Entitlement still lives entirely in `org_module_subscriptions`**
  (migration 118) — a successful Stripe payment just calls the SAME
  `module_subscriptions.set_status_billing`/`remove_billing` writers the
  existing super-admin "approve a subscribe/cancel request" flow already
  uses (`club_admin.py::approve_module_request`). There is no separate
  Stripe-only entitlement path to keep in sync.
- **`routers/billing.py`** (`/club-admin/billing/*`, gated by
  `Depends(require_billing_checkout_enabled)` on `/quote` and
  `/checkout-session` — NOT on `/invoices`, so a club that has already paid
  can always see its own billing history even if the flag is later switched
  off for new signups): `POST /quote` previews a selection with no Stripe
  call (pure `price_for()`); `POST /checkout-session` re-validates the
  primary-admin gate server-side (mirrors `cancel_own_module`'s pattern) and
  that none of the selected modules are already a live paid subscription,
  then returns a real Checkout Session URL to redirect to.
- **`routers/public_stripe.py`** (`POST /public/stripe/webhook`,
  unauthenticated by necessity — trust comes from verifying the
  `Stripe-Signature` header locally against `STRIPE_WEBHOOK_SECRET`, the same
  "verify the signature, not a login" posture `routers/public_ses.py` uses for
  inbound SNS events) is the **only place entitlement is actually granted** —
  the frontend's post-checkout redirect is UX only (shows a status, re-fetches
  the plan after a short delay). Handles `checkout.session.completed` (grants
  immediately, using the fresh subscription's period end as the renewal date),
  `invoice.paid` (rolls renewal_date forward on every renewal, reactivates a
  `past_due` module, upserts the `billing_invoices` row — idempotent on
  `stripe_invoice_id` so a replayed event is safe), `invoice.payment_failed`
  (moves the affected modules to `past_due` — a grace period, not an instant
  cutoff, matching the existing `ACTIVE_STATUSES` semantics), and
  `customer.subscription.deleted` (drops every module the subscription
  covered, same end state as the in-app self-service cancel). Deploy note:
  register this URL in the Stripe dashboard as
  `https://betterat.cricket/api/public/stripe/webhook` (nginx strips `/api`).
  A handler failure returns 500 so Stripe retries, rather than silently
  swallowing a failed entitlement write.
- **`org_id` + the selected billing keys round-trip through Stripe's own
  metadata** (the Checkout Session's `client_reference_id`/`metadata` AND the
  Subscription's own `metadata`) rather than a custom signed-state JWT (the
  pattern Square's OAuth callback uses, `routers/merch.py::sign_square_state`)
  — Stripe already carries `metadata` through the whole
  session/subscription/invoice object graph, so the webhook never needs a
  second lookup against our own DB to know what was bought.
- **Settings** (`config/settings.py`, mirrors the Square block's shape):
  `stripe_publishable_key` / `stripe_secret_key` / `stripe_webhook_secret` /
  `stripe_currency` (default `aud`), a `stripe_configured` property (blank
  keys = every billing call raises `StripeNotConfigured`, turned into a clean
  503 rather than a raw SDK traceback), and `stripe_checkout_success_url` /
  `stripe_checkout_cancel_url` computed from `public_base_url`.
- **Not built this round**: a Stripe Customer Portal link (self-service
  card update / cancel from the Stripe side) and per-club Stripe tax
  handling — both natural follow-ups once the base flow is verified end to
  end with real keys.
- **One club, one Stripe Subscription — never a second, parallel one.** A
  Checkout Session in subscription mode always creates a brand NEW Stripe
  Subscription; it can't add items to one that already exists. Originally
  (this section used to say) `/checkout-session` just 409'd outright once a
  club had a live subscription, to avoid a double-billed Core and an orphaned
  original. **v2 (below) replaces that outright block with the real
  feature** — adding modules to the existing subscription instead of ever
  creating a second one.
- **Webhook delivery order isn't guaranteed** — `invoice.paid` for a brand-new
  subscription's first invoice can arrive before `checkout.session.completed`
  has stamped `stripe_subscription_id` onto the org.
  `stripe_billing._resolve_org_for_subscription` falls back to fetching the
  subscription and reading its own `metadata.org_id` when the org isn't found
  by `stripe_subscription_id` yet, and self-heals by stamping it — otherwise
  that first invoice would silently never show up in Billing History even
  though entitlement was still granted correctly via `checkout.session.completed`.

### Adding modules to an already-live subscription (migration 152, Jul 2026)

Per direct instruction: **no bundle discount on a module added after the
initial subscribe**, and it must be **prorated to the existing subscription's
renewal date**, then renew at full price from there — Stripe's own
proration engine does exactly this natively, so we lean on it rather than
hand-rolling day-count math.

- **Two distinct paths in `routers/billing.py`, chosen by whether
  `club.stripe_subscription_id` is already set**: no subscription yet → the
  original Checkout Session flow (`billing_pricing.price_for` — Core +
  selection, bundle discount, redirect to Stripe to collect payment details).
  Already subscribed → add items to the EXISTING subscription
  (`billing_pricing.price_for_addon` — no Core line, no discount, ever). The
  add-on path never redirects to Stripe at all — the card is already on
  file, so it charges the prorated amount immediately and synchronously,
  server-side.
- **`/quote` mirrors the same branch**: returns `{"mode": "new_subscription",
  ...price_for()}` or `{"mode": "add_to_existing", ...}` where the add-on
  shape's `total`/`line_items` come from a REAL Stripe call —
  `stripe_client.preview_add_modules` calls `Invoice.create_preview` with the
  hypothetical new items and `proration_behavior=always_invoice` — so the
  preview is Stripe's own exact proration figure, not an approximation we
  compute from day-counts. `AdminAccount.jsx` renders each mode differently
  (a "Charged today (prorated)" total + a note about full-price renewal for
  the add-on case, vs the usual bundle-discount breakdown for a fresh
  subscribe).
- **`stripe_client.add_modules_to_subscription`** creates a `SubscriptionItem`
  per new module (`proration_behavior=always_invoice`, so Stripe invoices and
  charges the prorated amount as part of that same call, against the
  existing payment method — no 3-D Secure/SCA re-authentication flow is
  handled for this path, a known limitation) and then `Subscription.modify`s
  the subscription's own `metadata.billing_keys` to the union of old + new
  keys, so future `invoice.paid` renewals (`stripe_billing.py`) keep
  refreshing the newly-added module's `renewal_date` too — without this the
  renewal loop would silently stop touching it, since it reads the
  subscription's metadata to know what's on it.
- **Real Stripe Product ids, unlike the Checkout Session path.** Checkout
  Session line items support an inline ad-hoc `price_data.product_data`
  (no product to pre-create), but `SubscriptionItem.create` and
  `Invoice.create_preview` do NOT — both require a real Product id via
  `price_data.product`. `stripe_client._ensure_product` creates each
  billable module's Product exactly once and caches the id in the new
  `stripe_products` table (migration 152) rather than re-creating — or
  Stripe-searching for — it on every add-on checkout. (Verified this whole
  parameter shape against Stripe's own current API docs while building it,
  not assumed from memory — the inline-vs-real-product-id split between
  these two endpoint families is easy to get wrong.)
- **Entitlement granted synchronously, not via webhook**, for this path —
  there's no `checkout.session.completed` event for a flow that never
  touched Stripe Checkout, so `routers/billing.py::create_checkout_session`
  itself calls `module_subscriptions.set_status_billing` right after Stripe
  confirms the item + invoice were created, using the subscription's own
  freshly-returned `current_period_end` as the renewal date. The `invoice.paid`
  webhook that follows moments later re-applies the same state — harmless,
  since every entitlement write here is idempotent.
- **`stripe_billing._upsert_invoice` now snapshots `line_items` from
  Stripe's OWN invoice lines**, not recomputed from `billing_pricing` against
  every currently-held module — a renewal invoice bills everything, but an
  add-on invoice only bills the newly-added module(s), so re-deriving "what's
  on this invoice" from the full held-module set would have shown a partial
  invoice as if it were a full one.

### Promotion codes + other payment methods (Jul 2026)

- **Promotion codes** — `create_checkout_session` sets `allow_promotion_codes:
  true` (shows a customer-facing "Add promotion code" field on Stripe's own
  checkout page) whenever the bundle discount ISN'T already applying.
  **Never set both** — Stripe rejects a session with `discounts` AND
  `allow_promotion_codes` set together (`amount_off/percent_off Coupons` and
  customer-enterable **Promotion Codes** are created/managed entirely in the
  Stripe Dashboard, Product catalogue → Coupons — no admin UI of ours
  needed).
- **Apple Pay / Google Pay already work with zero setup** — confirmed live
  (a real Apple Pay button appeared on a test checkout without any
  `payment_method_types` configuration). Neither `create_checkout_session`
  nor anything else in this codebase sets `payment_method_types` explicitly,
  so every session already uses Stripe's **dynamic payment methods**: it
  shows whatever's enabled in Dashboard → Settings → Payment methods,
  automatically, no code change ever needed to add a new one.
- **AU BECS Direct Debit and PayTo are both Stripe-supported for AU
  accounts** — same story, a Dashboard toggle away, no code change. Two
  things worth knowing before switching either on: BECS/PayTo both take
  days (BECS) or up to ~60 seconds after bank-app mandate authorization
  (PayTo) to confirm, vs a card's instant response — our webhook-driven
  entitlement grant already handles that fine (a club just sees a shorter
  "processing" window before Subscribed lands). PayTo specifically performs
  best under $1,000 AUD (BetterCricket's most expensive bundle is $998, a
  good fit) but has "relatively low" business-bank-account coverage
  (consumer accounts are its stronger suit) and bank-side mandate caps
  around $25,000 — a non-issue at these price points, just worth knowing if
  pricing ever changes materially.

### Bundle discount is now config, not code (Jul 2026)

`billing_pricing.BUNDLE_DISCOUNT` (module-count → whole-dollar discount) was
a hardcoded constant; per direct instruction it's now editable from General
Settings without a deploy, same pattern as every other super-admin-tunable
number in this app.

- **`platform_settings.get_bundle_discount_schedule(db)` /
  `update_bundle_discount_schedule(db, schedule)`** — reads/writes a
  `bundle_discount_schedule` key in the existing JSONB singleton (no
  migration). Falls back to `billing_pricing.BUNDLE_DISCOUNT` (now just the
  SEED DEFAULT) when unset. `update_...` **replaces the whole table** (not a
  merge — the UI always sends every row) and validates every key/value is a
  non-negative integer.
- **`billing_pricing.py` stays a pure, DB-free module** — `bundle_discount()`
  and `price_for()` both take an optional `schedule` override param instead
  of reaching into the DB themselves, so they're still trivially unit-
  testable with no session. Callers that have `db` (`routers/billing.py`'s
  `/quote` and `/checkout-session`, which thread it through to
  `stripe_client.create_checkout_session`) fetch the live schedule and pass
  it down; `price_for_addon` is untouched (never discounted, so there's
  nothing to override).
- **Overflow beyond the highest configured row** falls back to that row's
  discount (generalises the old hardcoded "cap at 4 modules" rule to
  whatever's actually configured — so a future 5th/6th priced module needs
  no code change here, just a new row filled in).
- **Discount is clamped to the subtotal** in `price_for()` — a super-admin
  typo in the (now-editable) schedule can't produce a negative checkout
  total.
- **UI**: `SuperClubs.jsx`'s General Settings modal, a "Bundle discount
  schedule" section under Billing — 6 number inputs (module-count → $),
  rows 5-6 pre-wired but inert today (only 4 priced bolt-on modules exist),
  saved via the existing `PATCH /club-admin/super/general-settings`
  (`GeneralSettingsUpdate.bundle_discount_schedule`, popped out and routed to
  the dedicated setter rather than the generic `_INT_KEYS`/`_BOOL_KEYS`
  `update_settings` path, since it's a nested object).

### Bundle discount coupon fixes: `once` not `forever`, cached not re-minted (migration 153, Jul 2026)

Caught during live testing: two bugs in how the bundle-discount Coupon was
created at checkout.

- **`duration` was `forever`, should have been `once`.** Per direct
  instruction: the bundle discount is a one-time incentive for subscribing to
  several modules at once — it must apply to the initial payment ONLY. A
  renewal (or an add-on to an already-live subscription, which never gets
  the bundle discount at all — see above) must bill at full price unless a
  *separate* coupon is deliberately applied to that specific renewal.
  `duration=forever` was silently discounting every future renewal too.
  Fixed: `stripe_client._ensure_bundle_coupon` now creates the coupon with
  `duration="once"`.
- **A fresh Coupon was minted on every single checkout attempt** — even two
  identical attempts (e.g. a retry) produced two separate Coupon objects in
  the Dashboard, both showing 1 redemption, reading as duplicates. Fixed the
  same way `_ensure_product` already caches Stripe Products: `stripe_coupons`
  (migration 153, `discount_cents` primary key → `stripe_coupon_id`) reuses
  ONE coupon per distinct dollar amount instead of creating a new one each
  time. Keyed on amount alone since `duration` is fixed at `once` for every
  bundle coupon today — if duration ever becomes independently configurable
  per amount, key on `(amount, duration)` instead.
- **Stripe Coupon fields, for reference** (verified against Stripe's own API
  docs while fixing this): `duration` (`once`/`repeating`/`forever`) controls
  how many charges on ONE subscription get the discount once redeemed.
  `duration_in_months` (only with `repeating`) — on an annual plan,
  `duration_in_months=12` covers only the first invoice (same practical
  effect as `once`); `24` covers the first invoice PLUS the next renewal;
  generally `12 × N` covers N annual charges. `redeem_by`/`max_redemptions`
  are a completely different axis — they cap the coupon's overall
  availability (a deadline / a total redemption count across ALL customers),
  not how long the discount lasts on any one subscription. The Dashboard's
  "Redemptions" column is `times_redeemed`; "Expires" is `redeem_by`
  (blank = redeemable indefinitely, which is what every coupon this app
  creates uses — nothing sets `redeem_by`/`max_redemptions`).
- **Not built**: applying a coupon to an ALREADY-LIVE subscription ahead of
  its next renewal (`Subscription.modify(sub_id, discounts=[{coupon: ...}])`
  — takes effect from the next invoice the subscription generates) — no
  admin action for this exists yet, in BetterCricket or otherwise; today a
  coupon can only be attached at Checkout Session creation (the initial
  subscribe, or theoretically via `allow_promotion_codes` on a future
  Checkout — but the add-on flow above never redirects to Checkout at all,
  so a promo code has no entry point there either). Configurable
  duration/repeat-count for the BUNDLE discount specifically (vs the fixed
  `once` behaviour above) is also not built — flagged as an open question,
  not assumed wanted.

### A cached Stripe id belongs to ONE mode (migration 263, Aug 2026)

Reported live off the first real checkouts: `No such coupon: 'IBBpUgf0'; a
similar object exists in test mode, but a live mode key was used`, and a club
entering the code LEEDY got nowhere.

- **Nothing was wrong with the coupon. It was in the other Stripe mode.**
  Every Stripe object id (Coupon, Product, Customer, Subscription) exists in
  test OR live, never both, and the id itself carries no marker saying which.
  BetterCricket had three places holding one: `stripe_products` (152),
  `stripe_coupons` (153) and `discount_coupons.stripe_coupon_id` (156), all
  written while the box still ran test keys, all handed straight to the live
  API the day the keys changed. **The cache key has to include the mode**, or
  every discount on the platform dies at the key switch.
- **`stripe_client.stripe_mode()` reads it off the secret key** (`_live_` /
  `_test_` in an `sk_` or `rk_` key, else `unknown`). The two caches are keyed
  on `(key, mode)` — the old single-column PKs are gone, replaced by unique
  indexes, which is what the `ON CONFLICT` targets.
- **Existing rows are backfilled to `'unknown'`, deliberately not guessed.**
  A cached id can't be interrogated for its mode without asking Stripe, so
  `unknown` is a value no lookup matches and the object is simply re-created
  in the mode being used. The stale rows stay as history; the orphaned
  test-mode objects they point at cost nothing.
- **A discount coupon RE-SYNCS rather than refusing.**
  `discount_coupons.ensure_stripe_coupon` mints a fresh Stripe Coupon and
  stamps `discount_coupons.stripe_mode` whenever the stored mode isn't the
  one in use (NULL for every coupon predating this, so each re-syncs once, on
  first use). A code already given to a club therefore survives the key
  switch with no Super Admin re-creating the catalogue. Called from both
  redeem paths, NOT from `/quote` — a price preview does no Stripe call at
  all and shouldn't start creating objects.
- **A stale `organisations.stripe_customer_id` used to kill the whole
  checkout** ("No such customer" is a hard reject, not a fallback), so
  `create_checkout_session` checks the Customer resolves first and starts a
  new one if not; `handle_checkout_completed` re-stamps the org either way.
  **A transient Stripe error reads as "exists"**, so a wobble can't orphan a
  real club's Customer.
- **Not covered, and it can't be**: a club whose `stripe_subscription_id` was
  created in test mode has no live subscription to add modules to. That is a
  club that never really subscribed, not an id to repair.
- **Verified against a real Postgres** (migration 263 applied three times to
  a populated pre-263 table carrying the reported ids, the lifespan mirror
  landing on the same schema, both modes coexisting, the race-tolerant
  upsert still no-oping) and through the shipped functions themselves with
  Stripe stubbed: the stale rows ignored, live rows reused, one create per
  new object, and `ensure_stripe_coupon` re-syncing a NULL/test coupon while
  leaving an already-live one alone.

### Add-on pricing was still applying the bundle discount (Jul 2026)

Caught in live testing: adding modules to an already-subscribed club's
existing subscription (`preview_add_modules`/`add_modules_to_subscription`)
still discounted the prorated charge by the original bundle-discount amount,
contradicting the "no bundle discount on an add-on" rule documented above.
Root cause: the `duration=once` bundle coupon is only consumed by a
*regular* invoice — if it hadn't yet been applied to one (e.g. modules added
the same day as the initial subscribe, before the first renewal invoice),
it was still attached to the subscription and Stripe's proration engine
applied it to the add-on invoice too.

- **`stripe_client.preview_add_modules`** now passes `discounts=""` (the
  SDK's literal-empty-string form — an empty *list* is a no-op and still
  inherits the subscription's discount, confirmed against the SDK's own
  param typing) to `Invoice.create_preview`, so the preview never includes
  an inherited discount.
- **`stripe_client.add_modules_to_subscription`** calls
  `Subscription.delete_discount_async` before creating the new
  `SubscriptionItem`s, stripping any lingering coupon so the real
  `proration_behavior=always_invoice` charge matches the preview. Errors
  (nothing to remove) are swallowed — that's already the desired end state.
- **Per-module price breakdown**: `preview_add_modules` now returns each
  line item with `full_price` (the module's plain annual rate, from
  `billing_pricing.price_for_addon`) and `deduction` (`full_price` minus the
  prorated amount) alongside the existing `amount`, matched to
  `billing_keys` by position (both derive from the same
  `PRICED_MODULES`/`FANTASY` order). `AdminAccount.jsx`'s add-on summary
  shows, per module: full annual price → prorata deduction → charged today,
  instead of a single opaque prorated figure.

### GST via Stripe Tax (Jul 2026)

Caught in live testing: checkout never charged GST, because nothing in
`create_checkout_session` ever asked Stripe to calculate tax — a Dashboard
tax configuration alone does nothing without the API request opting in.

- **GST-exclusive per direct instruction**: the advertised prices (Core
  $399/yr etc.) are what BetterCricket keeps; GST is added ON TOP at
  checkout, not carved out of the advertised figure. Every `price_data` now
  sets `tax_behavior: "exclusive"` (both the Checkout Session line items in
  `create_checkout_session` and the add-on `SubscriptionItem`/preview items
  in `_addon_price_data_items`).
- **`automatic_tax: {"enabled": True}`** is set at Checkout Session creation
  (top-level, NOT nested under `subscription_data` — that param doesn't
  exist there, verified against the SDK while building this). It carries
  onto the resulting Subscription automatically, so renewals keep
  calculating tax with no further code. `SubscriptionItem.create` has no
  `automatic_tax` field of its own — `add_modules_to_subscription`
  re-asserts it via `Subscription.modify` on every add-on call (so a
  subscription created before this shipped still picks it up), and
  `preview_add_modules` passes it explicitly to `Invoice.create_preview` too
  (so the prorated preview is accurate even before that modify call runs).
- **No explicit `tax_code` set on our Products** — deliberately left to the
  account's own **Preset product category** fallback (Dashboard → Settings →
  Tax → Business information → "Digital products › Business and web
  services", already configured) rather than guessing a specific Stripe tax
  code in code. Revisit only if a specific module ever needs different tax
  treatment from the rest.
- **Still required on the Stripe side, not something code can do**: an
  active AU GST registration under Settings → Tax → Registrations — without
  one, `automatic_tax` calculates $0 tax regardless of `tax_behavior`.
- **The Account page's OWN quote preview for a brand-new subscription can't
  show the exact GST figure** — `billing_pricing.price_for()` is pure local
  math with no Stripe call (deliberately, so `/quote` stays fast with no API
  round trip for the common case), so it shows a "Plus GST, calculated on
  Stripe's secure checkout page" note instead of a number. The **add-on**
  preview (`preview_add_modules`) is different — it's already a live
  `Invoice.create_preview` call, so once tax is enabled its `total` already
  includes the real GST automatically, no separate note needed there.

### Account page — price summary stays in view while selecting (Jul 2026)

`AdminAccount.jsx`'s module list can run to 6 rows; stacking the price
summary below it (the original layout) pushed the summary — the part an
admin most needs while still picking modules — below the fold. Fixed with a
two-column CSS Grid (`grid-cols-1 lg:grid-cols-[1fr_320px]`) once at least one
module is selected (`hasSummary`): the module list + billing history stay in
the left column, the price summary becomes the right column with
`lg:sticky lg:top-6` so it stays in view as the list scrolls. Below `lg` it
falls back to the original single-column stack (a sidebar doesn't fit a
narrow screen). No backend change.

### Per-club override for testing (migration 151)

`platform_settings.billing_checkout_enabled` is all-or-nothing across the
whole platform — no way to let one club's Primary Admin through the real
Stripe flow while everyone else stays on the stub. `organisations.
billing_checkout_override` (nullable boolean) sits on top of it: **NULL**
follows the platform default (the normal case), **true** force-enables
checkout for that one club regardless of the platform default, **false**
force-disables it even once the platform default is switched on. Resolved by
`platform_settings.billing_checkout_enabled_for_org(db, org)` — the function
`require_billing_checkout_enabled` and `GET /club-admin/account/plan` both now
call, in place of the old platform-default-only `get_billing_checkout_enabled`
(that raw getter still exists, for the General Settings page itself and as
the fallback `billing_checkout_enabled_for_org` reads). `require_billing_
checkout_enabled` now depends on `get_current_club` as well as `get_db` so it
can resolve the caller's own club's override.

Super admin control lives on the **club**, not General Settings — a "Stripe
checkout (this club)" select (Platform default / Force ON / Force OFF) in
each club's edit panel in `SuperClubs.jsx`, saved via the existing `PATCH
/club-admin/super/clubs/{id}` (`ClubUpdate.billing_checkout_override`, a
plain column so the generic `setattr` loop in `patch_club` handles it with no
special-casing). Typical use: flip one real or test club to Force ON, run a
live checkout end to end, then flip the platform default on for everyone once
satisfied (the per-club overrides can stay — they only matter when the
platform default is off, or when someone still needs a specific club blocked).

<!-- END original CLAUDE.md L14628-15067 -->
<!-- BEGIN original CLAUDE.md L15068-15163 -->
## Pay by invoice: BetterCricket runs the annual cycle (migration 308, v9.90.0, Sep 2026)

Asked for by a club in a live trial that wanted to subscribe and be INVOICED,
with a renewal invoice 14 days before each period ends, and no dependence on a
Super Admin to do it for them. Then, mid-build: **invoicing is OFF for every club
by default, new clubs included, and only a Super Admin can switch it on for a
club from All Clubs.** Until then the club sees no invoicing option at all.

- **IT IS NOT A STRIPE SUBSCRIPTION WITH `collection_method=send_invoice`, and
  that is the whole design.** A subscription raises its renewal invoice ON the
  renewal date and cannot raise it 14 days early, so "settle before the period
  ends" is unreachable with one. `services/invoice_billing.py` runs the cycle and
  asks Stripe for ONE-OFF invoices (`stripe_client.create_one_off_invoice`).
  Stripe still numbers them, renders the PDF, works out GST (`automatic_tax`,
  lines `tax_behavior=exclusive`) and hosts the payment page with whatever
  payment methods the account offers.
- **`auto_advance=False` and we never call Stripe's send.** BetterCricket emails
  the invoice to the PRIMARY Club Admin (whoever asked) with our own pay link;
  Stripe emailing the Customer's address as well would be a duplicate at best
  and the wrong person at worst.
- **Three switches, three meanings.** `organisations.invoice_billing_enabled`
  (Super Admin only, default false) is whether the club is OFFERED it;
  `organisations.billing_method` ('card' | 'invoice') is what the club chose;
  `org_module_subscriptions.billing_source` ('invoice' | 'stripe' | NULL) is what
  pays for each module's current period. **Only an 'invoice' row is ever renewed
  or lapsed by the invoice job**, so a card module (Stripe owns its renewal) and
  a hand-granted one (nobody does) can never be invoiced or cut off by
  accident. Every card grant path stamps 'stripe' for the same reason.
- **Switching the offer OFF moves an invoice club back to card** (in
  `patch_club`): the paid period runs to its end, no renewal invoice is raised,
  open invoices stay payable. The renewal job also filters on the offer.
- **ONE PRICING DEFINITION.** `plan_invoice` is what the Account page previews
  AND what the invoice carries: `billing_pricing.price_for` with the live bundle
  schedule, a code via `apply_coupon_to_quote` (moved out of the router so both
  paths share it). The discount reaches Stripe as ONE flat `amount_off` coupon
  worked out by that maths, so the charge matches the preview exactly.
- **KINDS.** `initial` (Core + selection, bundle, code; the year starts when the
  trial on those modules ends, so paying early costs no trial, or on payment if
  later); `addon` (no bundle and no code, prorated to the period's renewal date
  so the club renews together); `renewal` (every module still on the period,
  full price, a still-owed 'forever'/'repeating' code applied, never the bundle,
  which is a once-only reward on the card flow too).
- **DATES ARE PERTH.** A period is `[start, end)`: end = the renewal date, the
  card flow's convention. A renewal is due at 11:59:59pm Perth the day before
  (`due_by`); modules still on the period are PAUSED at the start of the renewal
  date (job at 00:15 Perth). Paused, not removed: paying the open renewal
  invoice late switches them back on for the rest of that period. Renewal
  invoices go out at 08:00 Perth, 14 days ahead (`RENEWAL_NOTICE_DAYS`).
- **PAYING IS WHAT GRANTS.** The `invoice.paid` webhook, routed off the
  subscription path by `metadata.billing_method == 'invoice'`. A renewal date
  only ever moves FORWARD, so a replayed old event cannot undo a later renewal;
  a renewal paid after a module was cancelled does not switch it back on.
- **A NEW FIRST OR ADD-ON INVOICE VOIDS THE PREVIOUS OPEN ONE** (and a new first
  invoice also voids a renewal left open by a lapsed period), so a club can never
  pay twice for one selection. One live renewal per period is enforced by a
  partial unique index; the loser of a race voids its own Stripe invoice.
- **COMMISSION.** A one-off invoice's `billing_reason` is 'manual', which the
  ledger reads as "earns nothing", so `_upsert_invoice` takes an override:
  initial → subscription_create, addon → subscription_update, renewal →
  subscription_cycle. Same earnings as the same purchase by card.
- **THE PAY LINK IS OURS** (`GET /public/billing/pay/{token}`, unauthenticated,
  token-scoped): it asks STRIPE whether the invoice is still payable before
  redirecting to its current hosted page, and lands on the Account page once
  paid or voided, so a late webhook can never send somebody to pay twice.
- **THE CONSOLE PROVIDER IS NOT A SEND** (the sales-email rule): with no email
  provider the invoice is raised, `email_error` says it was not emailed, and the
  Account page offers the pay link instead.
- **INVOICING IS A SUPER ADMIN ARRANGEMENT, NEVER A CLUB'S CHOICE (v9.90.1).** A
  club asks and BetterCricket sets it up. `_require_super_for_invoicing` refuses
  the club-side `PUT /billing-method` and `POST /invoices/request` for every club
  admin, primary included, and `cancel_own_module` refuses an invoice club. The
  Account page shows an invoice club its status and open invoices (pay, PDF,
  resend) with no module picker. A card club, the default, is untouched: it still
  picks modules and checks out by card itself.
- **Card checkout refuses an invoice club (409)**, and a club on a live card
  subscription cannot switch to invoice, so nobody is billed twice.
- **Deploy**: add `invoice.voided` and `invoice.marked_uncollectible` to the
  Stripe webhook's subscribed events (invoice.paid / payment_failed are already
  there). Payment methods on the hosted invoice page come from the Stripe
  Dashboard's own settings.
- **Verified against a real Postgres** (`backend/verification/verify_invoice_billing.py`,
  94 checks through the shipped service, webhook routing and route bodies, with
  Stripe and email stubbed: 308 over a populated table, the pricing incl. the
  code after the bundle, the non-primary admin asking and the PRIMARY receiving,
  replace-on-reissue, payment granting from the trial end, replay safety, the
  add-on proration, the renewal at 14 days and not 15, the lapse on the renewal
  date and not the day before, paying late, the card / hand-granted / switched
  back / not-offered clubs left alone, the offer gate from both sides, and the
  pay link) **with two control runs**: the previous commit REPORTS the feature
  absent; with the lapse scope, the setting filter and replace-on-reissue
  neutered, 5 fail. **Driven in Chromium** (`frontend/verification/verify_invoice_billing_browser.mjs`,
  44) **with a control run**: 32 fail against the previous commit.
- **NOTICED, NOT BUILT**: a BECS/PayTo payment made on the due day can take days
  to confirm, so the modules may pause briefly and come back when it lands.
  No reminder beyond the 14-day invoice; Resend is the manual nudge.

<!-- END original CLAUDE.md L15068-15163 -->
<!-- BEGIN original CLAUDE.md L15164-15248 -->
## BetterCricket-managed discount coupons (migration 156, Jul 2026)

A full coupon engine, entirely owned by BetterCricket — per direct
instruction, **Super Admin never edits a Coupon by hand in the Stripe
Dashboard for this** (unlike the earlier bundle-discount coupon, which was a
simple cached single-purpose object). Every eligibility rule lives in
BetterCricket's own tables and is decided before Stripe is ever touched; the
corresponding Stripe Coupon is a pure sync target with no `redeem_by`/
`max_redemptions` of its own, so there's exactly one place a redemption is
judged valid.

- **`discount_coupons`** (the catalogue) + **`discount_coupon_redemptions`**
  (the audit trail and the "one live redemption per club per coupon"
  enforcement — a partial unique index on non-`revoked` rows, so a Super
  Admin's revoke frees the slot back up). A coupon has: `code` (typed in) +
  `display_name`; `discount_type` (percent | amount) + `discount_value`;
  `module_keys` (null/empty = every billable module, else restricted —
  mirrored onto Stripe's native `Coupon.applies_to.products`, reusing the
  SAME per-module Stripe Product `stripe_client._ensure_product` already
  caches for the add-on-module flow, so a covered/non-covered mix on one
  invoice is split automatically by Stripe); `redeem_window_*` (when the code
  can be entered at all); `new_signup_window_*` (only usable at a club's
  very first subscribe, and only if that subscribe falls in this range) and
  `loyalty_window_*` (only usable by a club whose original subscription
  start — `MIN(org_module_subscriptions.started_at)` — falls in this
  historical range) — **both optional and independent**, each restricting
  nothing unless at least one of its own bounds is set;
  `duration_mode` (once | repeating | forever, `duration_renewals` years for
  repeating → Stripe's `duration_in_months = 12×N`); `stackable_with_bundle`;
  `max_redemptions`; `active` (the deactivate switch — coupons are never
  deleted, so history stays traceable).
- **Financial-terms lock**: once a coupon has ≥1 non-revoked redemption,
  `services/discount_coupons.update_coupon` rejects changes to
  `discount_type`/`discount_value`/`module_keys`/`duration_mode`/
  `duration_renewals` — Stripe Coupons are themselves immutable on these
  fields after creation, and rewriting them out from under an
  already-redeemed club would silently change what that club was promised.
  Only `display_name`, the window dates, `max_redemptions`,
  `stackable_with_bundle` and `active` stay editable after that point; the
  Super Admin edit modal (`SuperCoupons.jsx`) greys those fields out and
  explains why once `redemption_count > 0`.
- **Two redemption flows, one rule engine**
  (`discount_coupons.validate_redemption`, called by both):
  - **New signup** — a club with no Stripe subscription yet, entering a code
    alongside their module selection. `routers/billing.py`'s existing
    `/quote` and `/checkout-session` both grew an optional `coupon_code` —
    `/quote` validates read-only and folds the discount into the preview
    numbers (`_apply_coupon_to_quote`, pure local math, no Stripe call, same
    as the rest of `/quote`); `/checkout-session` calls
    `redeem_for_new_signup` (writes a `pending` redemption row) and passes
    the resulting Stripe coupon id through to
    `stripe_client.create_checkout_session`'s new `extra_coupon_id`/
    `extra_stackable` params — Stripe natively supports multiple
    simultaneous discounts (`discounts` is a list on Checkout Session,
    Subscription and Invoice preview alike, confirmed against the SDK's own
    param typing), so a stackable coupon combines with the bundle discount;
    a non-stackable one **replaces** it outright (never diluted by the
    generic bundle schedule). If Stripe then fails, the `pending` redemption
    is revoked so a config hiccup on our side can't permanently burn a
    club's one-time code. `stripe_billing.handle_checkout_completed` reads
    `coupon_redemption_id` back out of the session's metadata and flips the
    row to `active` once the subscription is actually confirmed created.
  - **Already-subscribed, ahead of renewal** — a Primary Admin (self-serve,
    a new "Redeem a discount code" card on the Account page, separate from
    module selection) or a Super Admin (`force=True` on the new
    "Force-apply…" action in `SuperCoupons.jsx`, which skips the
    redeem-window/max-redemption checks but never "already redeemed" or
    "inactive") call `redeem_for_existing_subscription` →
    `stripe_client.attach_discount_to_subscription`. This is a genuine
    **fetch-then-append**, not an overwrite — `Subscription.modify`'s
    `discounts` param replaces the whole list, so blindly setting a new
    single-entry list would silently evict a different coupon redeemed
    earlier for the same upcoming renewal. Stripe applies a
    subscription-level discount starting at the **next** invoice the
    subscription generates, never retroactively — exactly "apply ahead of
    the renewal date", no proration or immediate charge triggered.
- **Not built**: a self-serve "browse eligible codes" list (deliberately —
  confirmed a typed-in code is the right UX, matching how a coupon code
  normally works); configurable per-coupon retry/grace period for a stuck
  `pending` new-signup redemption beyond the immediate Stripe-failure revoke
  above (a truly abandoned Checkout Session — the club navigates away
  without completing — leaves the redemption `pending` forever, which the
  "already redeemed" check treats as used; a Super Admin can manually revoke
  it via the Redemptions modal as the recovery path today).

<!-- END original CLAUDE.md L15164-15248 -->
