# Manual Invoicing Runbook

How money is collected for the Better platform **today**: by hand. The app
tracks each club's commercial state (tier, status, renewal date, billing cycle)
so entitlement and reminders are driven from one place, but **invoices are
raised and reconciled off-platform** (your accounting tool + bank transfer).

Automated recurring billing (Stripe) is **deliberately deferred** — see
*Deferred: Stripe Billing* at the bottom.

---

## The fields that drive this

Set on each `Organisation` (super-admin console → **All Clubs** → **Edit**):

| Field                 | Meaning                                                                 |
|-----------------------|-------------------------------------------------------------------------|
| `tier`                | Good / Better / Best — what the club is paying for (and what's unlocked).|
| `billing_cycle`       | `monthly` or `annual` — how often you invoice.                          |
| `renewal_date`        | When the current period ends → when to send the next invoice.           |
| `subscription_status` | `active` / `trial` / `past_due` / `paused` / `cancelled`.               |

**Status → entitlement** (enforced in `app/auth/modules.py`):
- `active`, `trial`, `past_due` → modules stay **live** (`past_due` is a grace
  period — a late invoice doesn't instantly cut a club off).
- `paused`, `cancelled` → fall back to **Core only** (paid module tiles lock,
  routes 402). Tier is preserved, so re-activating restores access instantly.

Prices live in one place — `frontend/src/lib/modules.js` → `TIER_INFO`
(working ladder: Good $449/yr · Better $649/yr · Best $999/yr; monthly
$49/$69/$99). Edit there if the ladder changes.

---

## New club (first invoice)

1. Onboard the club (see `onboarding-runbook.md`) and set its **tier**.
2. Set **billing cycle** and a **renewal date** one period out
   (e.g. annual → today + 12 months).
3. If you're giving a free trial, set status **Trial**; otherwise **Active**.
4. Raise the invoice off-platform for the tier's price (annual or monthly).
5. On payment, ensure status is **Active**.

## Renewals (recurring)

1. Periodically review **All Clubs**: each row shows
   `cycle · renews {date} · status`. Anything renewing soon needs an invoice.
2. Send the invoice ahead of `renewal_date`.
3. On payment: bump `renewal_date` forward one cycle; keep status **Active**.
4. If unpaid by the due date: set **Past due** (modules stay live during grace).
5. If still unpaid after grace: set **Paused** (modules lock; data is retained).

## Cancellations

- Set status **Cancelled**. Modules lock immediately; the club keeps its Core
  site and history. Re-activating later just flips status back to **Active**.

## Founding / pilot clubs

- Applecross (and early pilots) may be comped or discounted. Reflect this with
  status **Active** + a tier, and simply don't invoice — the open *Founding
  club pricing* decision in the master plan governs the commercial terms.

---

## Deferred: Stripe Billing (do NOT build yet)

The master plan's Phase 3 "later" item is Stripe Billing (monthly + annual
products; webhooks flip `subscription_status`/`renewal_date` automatically).
**Not in scope now** — defer until self-serve onboarding exists. The fields
above are intentionally Stripe-shaped so the eventual webhook handler can write
straight to them with no schema change:

- `subscription.status` → `subscription_status`
- `current_period_end` → `renewal_date`
- price/plan → `tier`
- interval → `billing_cycle`
