# Guide: Billing, Stripe subscriptions, coupons and pay-by-invoice

**Read this before** (money is involved: read the flags and gates carefully):
- Editing `backend/app/services/billing_pricing.py`, `stripe_client.py`, `stripe_billing.py`, `invoice_billing.py`, `invoice_billing_ddl.py`, `discount_coupons.py`, or `routers/billing.py`, `routers/public_stripe.py`.
- `frontend/src/data/pricing.js`, `AdminAccount.jsx`, `SuperClubs.jsx` (billing toggles, per-club override, invoicing switch), `SuperCoupons.jsx`.
- Anything touching `platform_settings.billing_checkout_enabled`, `organisations.billing_checkout_override`, `invoice_billing_enabled`, `billing_method`, `org_module_subscriptions.billing_source`.

**Archive** (full history, verbatim, do not load whole): `docs/dev-notes/archive/billing-stripe-and-invoicing.md`. Grep hints: `feature-flagged while it's built`, `Stripe Checkout — recurring`, `already-live subscription`, `Promotion codes + other payment`, `Bundle discount is now config`, `once` not `forever`, `belongs to ONE mode`, `still applying the bundle discount`, `GST via Stripe Tax`, `Per-club override`, `Pay by invoice`, `managed discount coupons`.

**Related guides**: module entitlement (`org_module_subscriptions`); sales commissions (invoice `billing_reason`, `record_payment_commission`); platform settings; email sending.

## Standing rules

**Gating and flags**
1. `platform_settings.billing_checkout_enabled` is off by default (JSONB `_BOOL_KEYS`, no migration). There is no staging environment: this flag is the only thing between "merged" and "a real club paying". Flip it only when the flow is tested.
2. Per-club override `organisations.billing_checkout_override` (migration 151, nullable bool): NULL follows the platform flag, true forces ON, false forces OFF even when the platform is on. Resolve it only through `platform_settings.billing_checkout_enabled_for_org(db, org)`; `get_billing_checkout_enabled` is the raw platform getter (General Settings page and fallback only). Set via `PATCH /club-admin/super/clubs/{id}` (`SuperClubs.jsx`).
3. Every new invoicing or checkout endpoint must carry `Depends(require_billing_checkout_enabled)`. The frontend gate is UX only. It is on `/quote`, `/checkout-session`, `PUT /billing-method` and `POST /invoices/request`. It is deliberately NOT on `GET /invoices` (a club that has paid always sees its history) nor on the `/super/clubs/{org_id}/...` invoice routes (a Super Admin helping a club is the deliberate case; those are gated by `invoice_billing_enabled` instead).

**Pricing**
5. `services/billing_pricing.py` is a hand-kept Python port of `frontend/src/data/pricing.js` (CORE $399, four priced modules at $149/$149/$149/$249, FANTASY $49 standalone outside the bundle, seed `BUNDLE_DISCOUNT` {2: 48, 3: 97, 4: 146}). Core plus all four = $949.
6. `price_for(selected_keys, schedule=None)` is the ONE place the quote, the Checkout line items and the invoice amount come from. It stays pure and DB-free: callers with `db` fetch the live schedule and pass it in. `price_for_addon` never discounts.
7. Bundle discount is config: `platform_settings.get/update_bundle_discount_schedule` (key `bundle_discount_schedule`). Update replaces the whole table, validates non-negative integers. Counts above the highest row use that row's discount. `price_for()` clamps the discount to the subtotal. Saved via `PATCH /club-admin/super/general-settings` (`bundle_discount_schedule` is popped and routed to its own setter).
8. No pre-created Stripe Prices: Checkout line items use inline `price_data` (recurring, `interval: year`). GST: every `price_data` has `tax_behavior: "exclusive"` (advertised price is what we keep, per direct instruction, GST goes on top) and Checkout Session sets top-level `automatic_tax: {"enabled": True}` (not under `subscription_data`).
9. `SubscriptionItem.create` has no `automatic_tax`, so `add_modules_to_subscription` re-asserts it with `Subscription.modify` on every add-on; `preview_add_modules` passes it to `Invoice.create_preview`. No explicit `tax_code` on Products: the account's Preset product category applies.

**Checkout, add-ons, entitlement**
10. One club, one Stripe Subscription, never a second. `/checkout-session` branches on `club.stripe_subscription_id`: unset gives a Checkout Session (Core plus selection, bundle, redirect); set gives an add-on to the existing subscription (no Core, no bundle, prorated to the renewal date by Stripe, charged immediately server-side, no redirect).
11. `/quote` mirrors the branch: `mode` is `new_subscription` (pure local maths, no Stripe call, so the page says "Plus GST, calculated on Stripe's secure checkout page") or `add_to_existing` (a real `Invoice.create_preview`, `proration_behavior=always_invoice`, so its total already includes GST).
12. Add-ons must not get the bundle discount, per direct instruction. A `duration=once` coupon is only consumed by a regular invoice, so it can still sit on the subscription and discount the add-on proration. Hence `preview_add_modules` passes `discounts=""` (literal empty string; an empty list still inherits) and `add_modules_to_subscription` calls `Subscription.delete_discount_async` first (errors swallowed).
13. Add-on and preview items need a real Stripe Product id (`price_data.product`), unlike Checkout inline `product_data`. `stripe_client._ensure_product` creates each module's Product once and caches it in `stripe_products` (migration 152).
14. After an add-on, set `Subscription.metadata.billing_keys` to the union of old and new keys, or renewals stop refreshing the new module's `renewal_date`.
15. Entitlement lives only in `org_module_subscriptions` (migration 118), written by the same `module_subscriptions.set_status_billing`/`remove_billing` the super-admin approve flow uses. No Stripe-only entitlement path.
16. `routers/public_stripe.py` `POST /public/stripe/webhook` is unauthenticated; trust is the `Stripe-Signature` check against `STRIPE_WEBHOOK_SECRET`. Handlers: `checkout.session.completed` (grants), `invoice.paid` (rolls `renewal_date`, reactivates `past_due`, upserts `billing_invoices`, idempotent on `stripe_invoice_id`), `invoice.payment_failed` (module to `past_due`, a grace period), `customer.subscription.deleted` (drops modules), plus `invoice.voided` and `invoice.marked_uncollectible`. A handler failure returns 500 so Stripe retries. Webhook URL: `https://betterat.cricket/api/public/stripe/webhook`.
18. Add-on grants entitlement synchronously in `create_checkout_session` (no `checkout.session.completed` exists for that path), using the subscription's fresh `current_period_end`. The later `invoice.paid` re-applies the same state; every entitlement write must stay idempotent.
19. `billing_invoices.line_items` is snapshotted from Stripe's own invoice lines, never recomputed from held modules (an add-on invoice bills only the new modules).
20. Webhook order is not guaranteed. `stripe_billing._resolve_org_for_subscription` falls back to fetching the subscription and reading `metadata.org_id`, then stamps `stripe_subscription_id`.
21. Payment methods: never set `payment_method_types`. Apple Pay, Google Pay, BECS, PayTo all come from Dashboard settings (dynamic payment methods).
22. Promotion codes: `allow_promotion_codes: true` only when the bundle discount is NOT applying. Never send `discounts` and `allow_promotion_codes` together.

**Coupons (Stripe objects and BetterCricket-managed)**
24. Bundle coupon is `duration="once"` (`stripe_client._ensure_bundle_coupon`), per direct instruction: the bundle is a first-payment incentive only. It was `forever` at first and silently discounted every renewal. Cached in `stripe_coupons` (migration 153) one per distinct dollar amount (key on `(amount, duration)` if duration ever varies).
26. BetterCricket owns every discount rule (migration 156): `discount_coupons` (catalogue) and `discount_coupon_redemptions` (audit and one-live-redemption-per-club-per-coupon, a partial unique index on non-`revoked` rows). The Stripe Coupon is a sync target with no `redeem_by`/`max_redemptions`. Super Admin never edits these coupons in the Stripe Dashboard. Coupons are never deleted (`active` is the switch).
27. Coupon fields: `discount_type` percent or amount, `module_keys` (empty means all, mirrored to `applies_to.products` via the cached per-module Product), `redeem_window_*`, `new_signup_window_*` and `loyalty_window_*` (both optional and independent, restrict nothing unless a bound is set; loyalty uses `MIN(org_module_subscriptions.started_at)`), `duration_mode` (once, repeating with `duration_renewals` years to `12 x N` months, forever), `stackable_with_bundle`, `max_redemptions`.
28. Financial-terms lock: once a coupon has one non-revoked redemption, `update_coupon` rejects changes to type, value, `module_keys`, `duration_mode`, `duration_renewals` (Stripe coupons are immutable there and a club was promised those terms). Display name, windows, `max_redemptions`, stackable, active stay editable.
29. One rule engine `discount_coupons.validate_redemption`, two flows. New signup: `/quote` validates read-only (`_apply_coupon_to_quote`, no Stripe call); `/checkout-session` calls `redeem_for_new_signup` (writes `pending`), passes `extra_coupon_id`/`extra_stackable`. Stackable combines with the bundle; non-stackable replaces it. On Stripe failure the `pending` row is revoked so a config hiccup cannot burn a one-time code. `handle_checkout_completed` reads `coupon_redemption_id` from metadata and flips it to `active`.
30. Already-subscribed redemption (`redeem_for_existing_subscription` then `stripe_client.attach_discount_to_subscription`) must fetch-then-append: `Subscription.modify(discounts=...)` replaces the whole list. Applies from the NEXT invoice, never retroactively. Super Admin `force=True` skips window and max-redemption checks, never "already redeemed" or "inactive".

**Stripe test vs live mode**
31. Every Stripe id (Coupon, Product, Customer, Subscription) exists in one mode only and carries no marker. Cache tables are keyed on `(key, mode)` (migration 263): `stripe_products`, `stripe_coupons`, and `discount_coupons.stripe_mode`. `stripe_client.stripe_mode()` reads `_live_`/`_test_` off the `sk_`/`rk_` key, else `unknown`. Old rows were backfilled to `'unknown'` on purpose (never guessed) so no lookup matches and the object is re-created.
32. `discount_coupons.ensure_stripe_coupon` re-syncs (mints a fresh coupon, stamps `stripe_mode`) when the stored mode differs; NULL on pre-263 coupons re-syncs once. Called from both redeem paths, NOT from `/quote` (a preview must not create Stripe objects).
33. `create_checkout_session` checks the Customer resolves before use and starts a new one if not ("No such customer" is a hard reject); `handle_checkout_completed` re-stamps the org. A transient Stripe error reads as "exists" so a wobble cannot orphan a real Customer. A club whose subscription was created in test mode has nothing to repair.

**Pay by invoice (migration 308, `services/invoice_billing.py`)**
34. Not a Stripe subscription with `collection_method=send_invoice` (that raises the renewal ON the renewal date, so 14 days early is unreachable). We run the cycle and ask Stripe for one-off invoices (`stripe_client.create_one_off_invoice`). Stripe numbers, renders the PDF, computes GST and hosts the payment page.
35. `auto_advance=False`; never call Stripe's send. BetterCricket emails the PRIMARY Club Admin with our own pay link (Stripe emailing the Customer would duplicate).
36. Three switches: `organisations.invoice_billing_enabled` (Super Admin only, default false) is whether the club is offered it; `organisations.billing_method` ('card' | 'invoice') is what is chosen; `org_module_subscriptions.billing_source` ('invoice' | 'stripe' | NULL) says what pays each module's period. Only 'invoice' rows are renewed or lapsed by the invoice job. Card grants stamp 'stripe' (`set_billing_source`).
37. Invoicing is a Super Admin arrangement, never a club's choice: `_require_super_for_invoicing` refuses club-side `PUT /billing-method` and `POST /invoices/request` for every club admin including primary; `cancel_own_module` refuses an invoice club. A club admin can still view, pay and resend.
38. Switching the offer OFF (`patch_club`) moves the club back to card: paid period runs out, no renewal invoice raised (renewal job also filters on the offer), open invoices stay payable.
39. Card checkout refuses an invoice club (409, `routers/billing.py`), and a club on a live card subscription cannot switch to invoice. Nobody is billed twice.
40. One pricing definition: `plan_invoice` is what the Account page previews and the invoice carries (`price_for` with the live schedule, code via `apply_coupon_to_quote`, shared with the card path). The discount reaches Stripe as ONE flat `amount_off` coupon.
41. Kinds: `initial` (Core plus selection, bundle, code; year starts when the trial on those modules ends, or on payment if later); `addon` (no bundle, no code, prorated to the period's renewal date); `renewal` (every module still on the period, full price, a still-owed 'forever'/'repeating' code, never the bundle).
42. Dates are Perth. Period is `[start, end)`, end = renewal date. Renewal invoice raised 08:00 Perth, `RENEWAL_NOTICE_DAYS = 14` ahead, due 11:59:59pm Perth the day before (`due_by`). Modules still on the period are PAUSED (not removed) at the start of the renewal date (job 00:15 Perth); paying late switches them back on for the rest of that period.
43. Paying grants: `invoice.paid` routed by `metadata.billing_method == 'invoice'`. A renewal date only moves forward (a replayed old event cannot undo it); a renewal paid after a module was cancelled does not switch it back on.
44. A new first or add-on invoice voids the previous open one (and a new first invoice also voids an open renewal from a lapsed period). One live renewal per period (partial unique index).
45. Commission: a one-off invoice's `billing_reason` is 'manual' (earns nothing), so `_upsert_invoice` takes an override: initial to `subscription_create`, addon to `subscription_update`, renewal to `subscription_cycle`.
46. Pay link `GET /public/billing/pay/{token}` (unauthenticated, token-scoped) asks Stripe whether the invoice is still payable before redirecting; once paid or voided it lands on the Account page, so a late webhook cannot cause a second payment.
47. The console email provider is not a send: with no provider the invoice is raised, `email_error` records it, the Account page offers the pay link.
48. DDL lives once in `services/invoice_billing_ddl.py`, run by alembic 308 and the lifespan mirror.

## Traps and failure signatures
- `No such coupon: ...; a similar object exists in test mode, but a live mode key was used` (or "No such customer"): cached Stripe id from the other mode. Rules 31 to 33.
- Renewals carry the bundle discount, or two identical checkouts leave two Coupon objects: `forever` duration, coupon minted per attempt. Rule 24.
- Checkout charges no GST: `automatic_tax` not requested, or no active AU GST registration in Stripe (Settings, Tax, Registrations): tax then calculates $0. Not fixable in code.
- A first invoice never appears in Billing History though entitlement was granted: `invoice.paid` beat `checkout.session.completed`. Rule 20.
- Abandoned Checkout Session leaves a redemption `pending` and the code reads as used: Super Admin revokes it in the Redemptions modal.

## How to verify a change here
- Postgres: `backend/verification/verify_invoice_billing.py` (Stripe and email stubbed). Control run: previous commit must REPORT the feature absent; with lapse scope, the setting filter and replace-on-reissue neutered, checks fail.
- Browser: `frontend/verification/verify_invoice_billing_browser.mjs` (control run fails the new checks).

## Operator commands and scripts
- Deploy: register the webhook `https://betterat.cricket/api/public/stripe/webhook`. Subscribe to at least `checkout.session.completed`, `invoice.paid`, `invoice.payment_failed`, `invoice.voided`, `invoice.marked_uncollectible`.
- Server `.env`: `STRIPE_PUBLISHABLE_KEY`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, currency default `aud`.
- `python -m app.scripts.backfill_invoice_commission`: re-reads pre-278 invoices from Stripe and stamps commission (uses the rep's CURRENT rate).

## Open follow-ups
- Stripe Customer Portal and per-club Stripe tax not built (see FLAG-BILL-4).
- Configurable duration for the BUNDLE discount (fixed `once`) is an open question. A self-serve "browse eligible codes" list is deliberately not built.
- No configurable retry or grace period for a stuck `pending` new-signup redemption beyond the immediate Stripe-failure revoke.
- No 3-D Secure/SCA flow for the add-on path (card on file, immediate charge).
- Invoice: a BECS/PayTo payment made on the due day can take days to confirm, so modules may pause briefly and return. No reminder beyond the 14-day invoice; Resend is the manual nudge.

## Flags: conflicting, superseded or possibly obsolete guidance
- [FLAG-BILL-1] "The webhook is the only place entitlement is actually granted" | Conflicts inside the archive: add-on grants synchronously in `create_checkout_session`, and pay-by-invoice grants on `invoice.paid` routed by `billing_method`. Effectively three paths: card new-signup via webhook, add-on synchronous, invoice via its own `invoice.paid` branch | Stripe Checkout section (L14628-15067), first bullets vs "Adding modules" | verify, then rewrite as "three grant paths".
- [FLAG-BILL-3] "Not built: applying a coupon to an already-live subscription" | Superseded by `redeem_for_existing_subscription` / `attach_discount_to_subscription` in the managed-coupon section | Bundle discount coupon fixes, "Not built" | retire.
- [FLAG-BILL-4] "Not built: Stripe Customer Portal" | `routers/billing.py` now has `/payment-methods*` routes and `services/stripe_connect_billing.py`/`stripe_connect_client.py` exist; neither is in the archive | Stripe Checkout section, "Not built this round" | verify what exists and document in a fresh section.
- [FLAG-BILL-5] Section 1 says checkout "always shows the stub notice" and `submitSubscribe` is the future call site | The real flow has shipped (rules 10 to 20) | Billing checkout section (L14594-14627) | keep the flag rules, retire the stub wording.

## Section coverage
| Original section (heading, original CLAUDE.md line range) | Disposition | Where captured |
|---|---|---|
| Billing checkout — feature-flagged while it's built (v8.65.0), L14594-14627 | rules extracted (stub wording superseded, see FLAG-BILL-5) | Standing rules 1 to 3; Flag 5 |
| Stripe Checkout — recurring subscription billing (migration 150), L14628-15067 | rules extracted | Standing rules 5, 8, 10, 15 to 20; Traps |
| - Adding modules to an already-live subscription (migration 152) | rules extracted | Rules 10 to 14, 18, 19 |
| - Promotion codes + other payment methods | rules extracted | Rules 21, 22 |
| - Bundle discount is now config, not code | rules extracted | Rules 6, 7 |
| - Bundle discount coupon fixes: once not forever (migration 153) | rules extracted | Rule 24; Flag 3 |
| - A cached Stripe id belongs to ONE mode (migration 263) | rules extracted | Rules 31 to 33; Traps 1 |
| - Add-on pricing was still applying the bundle discount | rules extracted | Rule 12; Traps |
| - GST via Stripe Tax | rules extracted | Rules 8, 9, 11; Traps |
| - Account page — price summary stays in view | history only (two-column sticky layout, no rule) | none |
| - Per-club override for testing (migration 151) | rules extracted | Rules 2, 3; Operator commands |
| Pay by invoice: BetterCricket runs the annual cycle (migration 308), L15068-15163 | rules extracted | Rules 34 to 48; Open follow-ups |
| BetterCricket-managed discount coupons (migration 156), L15164-15248 | rules extracted | Rules 26 to 30; Open follow-ups |
