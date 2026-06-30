# Per-Module Subscription Status — Scope

Status: draft for review (ahead of build). Branch `claude/per-module-subscription-scope-1mty4t`.

## The problem

A club's entitlement today is **one org-wide subscription status** gating every
module at once. On the `organisations` row:

- `module_overrides` (JSONB array of keys) is the list of modules the club holds.
- `subscription_status` (active / trial / past_due / paused / cancelled) gates
  **all** of them together.
- `renewal_date` and `billing_cycle` are single values for the whole club.

`org_entitled_modules()` (`backend/app/auth/modules.py`) is the chokepoint: if the
org status is live it returns the whole override list, else Core only. Everything
downstream reads through it (`require_module`, `/auth/me` `entitlements`,
`hasModule` on the frontend).

The gap is already flagged in code at `services/twenty_sync.py` ("subscription_status
is still org-wide here, a true per-module subscribed/trial split needs the org model
change discussed in the brief"). A club paying for Core + BetterSelect while trialing
BetterIQ cannot be represented: the whole club reads as either trial or active, so its
ARR, renewal and trial split are all wrong on the CRM.

## What we're building

Each held module carries its own state. A single club can be:

- Core + BetterSelect: active, renews 1 Mar 2027
- BetterIQ: trial, ends 14 Jul 2026
- BetterMerch: past_due

Plus a request-and-approve flow so club admins can ask for a trial or a paid
subscription, and a super admin actions those asks from a queue.

## Decisions (settled)

- **Per-module fields**: each module row carries its own `status` and `renewal_date`;
  trials also carry `trial_started_at` and `trial_ends_at`. `billing_cycle` stays a
  single club-level value.
- **Storage**: a dedicated `org_module_subscriptions` table. `module_overrides` becomes
  derived from it (a module is "held" if it has a row), kept in sync for backward compat.
- **Master switch**: the org-wide `subscription_status` is kept as a whole-account kill
  switch. paused/cancelled at the org level overrides everything and instantly drops the
  club to Core only, regardless of per-module state. Per-module status only applies while
  the org-level switch is live.
- **Trial expiry is read-time**: a trial module is entitled only while
  `now <= trial_ends_at`. Once now passes the end it is disabled automatically with no
  scheduler. A super admin can terminate a trial early.
- **Default trial length**: a configurable default (seed 14 days). When a trial is
  requested or started, it prefills start = now and end = now + default. A super admin can
  adjust both before confirming.
- **Request authority**: any `club_admin` can request a **trial**; only the club's
  **primary/owner admin** can request a paid **subscription** (financial authority gate).
- **Approval creates the trial**: a super admin approving a trial request auto-creates the
  trial. Start = the moment of approval (not of the request), end recomputed from the
  default, both adjustable by the super admin before confirming.
- **Twenty**: every super-admin subscription/trial change re-pushes the club to Twenty so
  `paidModules` / `trialModules` / `arr` update. Twenty stays a one-way export.

## Decisions (settled, round 2)

- **Default-trial-days home**: a new per-club **Club General Settings** surface (super-admin
  managed), first field `default_trial_days` (default 14). Deliberately extensible: more
  general-settings fields get added over time. No platform singleton; a brand-new club
  inherits 14 from the column/blob default, and a super admin can change it per club.
- **Primary-admin gate**: add `is_primary_admin` to `club_memberships` (one per club). The
  first `club_admin` created for a club becomes primary. The current primary can transfer it
  to another `club_admin`; a super admin can reassign it too. Any `club_admin` can request a
  trial; only the primary can request a paid subscription.
- **Twenty-origin requests**: built now (Phase 2), on a generic Twenty **inbound** channel
  (webhook -> dispatcher) so future Twenty-origin request types reuse it. The queue's
  `source` field already accepts `twenty`.

## Data model

### `org_module_subscriptions` (new)

One row per club x module that the club holds or is trialing.

| column            | type        | notes                                                        |
|-------------------|-------------|--------------------------------------------------------------|
| id                | uuid pk     |                                                              |
| organisation_id   | uuid fk     | -> organisations, cascade                                    |
| module_key        | text        | one of ALL_MODULES                                           |
| status            | text        | active / trial / past_due / paused / cancelled               |
| trial_started_at  | timestamptz | null unless status = trial                                   |
| trial_ends_at     | timestamptz | null unless status = trial; read-time expiry boundary        |
| renewal_date      | date        | nullable                                                     |
| started_at        | timestamptz | when first granted                                           |
| created_at        | timestamptz |                                                              |
| updated_at        | timestamptz |                                                              |

Unique `(organisation_id, module_key)`.

### `module_action_requests` (new) — the super-admin queue

Mirrors the `club_onboarding_requests` pattern (super-admin actionable, lifecycle, source).

| column           | type        | notes                                                |
|------------------|-------------|------------------------------------------------------|
| id               | uuid pk     |                                                      |
| organisation_id  | uuid fk     | -> organisations                                     |
| module_key       | text        | one of ALL_MODULES                                   |
| kind             | text        | trial / subscribe / cancel                           |
| status           | text        | outstanding / completed / dismissed                  |
| source           | text        | app / super_admin / twenty (twenty deferred)         |
| requested_by     | uuid fk     | -> users, nullable                                   |
| requested_at     | timestamptz |                                                      |
| note             | text        | nullable                                             |
| completed_by     | uuid fk     | -> users, nullable                                   |
| completed_at     | timestamptz | nullable                                             |
| result_sub_id    | uuid fk     | -> org_module_subscriptions, nullable (what it made) |

### Club General Settings (new, per-club, extensible)

Stored as `organisations.general_settings JSONB not null default '{}'` (matches the
`theme_config` / `net_settings` precedent), with a typed accessor + validation service.
First key: `default_trial_days` (int, defaults to 14 when absent). Super-admin managed via a
new "Club General Settings" surface; designed to grow with more fields. When a trial is
requested/started for a club, the prefilled length reads this club's `default_trial_days`.

### `club_memberships` (altered)

Add `is_primary_admin boolean not null default false`, one true per club (partial unique
index `WHERE is_primary_admin`). Backfill the earliest `club_admin` membership per club.
Reassignment: an endpoint the current primary can call to transfer to another `club_admin`,
and a super-admin endpoint to set it directly. Flag exposed on `/auth/me` so the frontend can
gate the subscribe-request control.

### `organisations` (altered)

`general_settings JSONB` (above). `subscription_status` / `billing_cycle` stay (master switch
+ single cycle). `module_overrides` retained, kept in sync from the new table for backward
compat.

## Entitlement resolution (new shape)

`org_entitled_modules(org)`:

1. If org-level `subscription_status` is not live (paused/cancelled) -> Core only.
2. Else, for each `org_module_subscriptions` row: include the module if its own status is
   live, and if it is a trial, only while `now <= trial_ends_at`.

`entitlement_summary()` grows from flat fields to a per-module list, each entry carrying
`module`, `status`, `renewal_date`, and (for trials) `trial_ends_at`. `hasModule` keeps
working unchanged (reads the module keys); the renewal/status displays move to per-module.

## Surfaces to change

Backend:
- `auth/modules.py`: per-module resolution in `org_entitled_modules` /
  `entitlement_summary`; `require_module` unchanged at call sites.
- migration(s) for the new tables + alters, mirrored idempotently in the `main.py` lifespan
  per house style.
- super-admin endpoints in `club_admin.py`: per-module start-trial / start-sub / change /
  terminate; the action-request list + approve/dismiss; on each change, fire the Twenty push.
- new club-admin endpoints to raise a trial / subscription request (capability + primary
  gate), feeding the queue and bumping `marketing_clubs.requested_trial_modules` so interest
  shows in Twenty.
- `twenty_sync.py`: compute `paidModules` / `trialModules` / `arr` per module from the new
  table instead of the org-wide flag (resolves the existing TODO).
- a light daily job to push trial lapses to Twenty + notify (entitlement itself is read-time).

Frontend:
- `SuperClubs.jsx`: per-module status + renewal + trial dates editor (replaces the flat
  module checkboxes + single status/renewal); a "start trial" / "terminate" control.
- a super-admin module-requests queue page + count badge (the bell is per-club only, so this
  is a dedicated super-admin surface, same precedent as onboarding requests).
- a club-admin "request a trial / request to subscribe" control, the subscribe option gated
  to the primary admin, with the trial-length prefill.
- `AuthContext` / displays: per-module renewal + trial-countdown where a single renewal line
  shows today.

## Migration / backfill (non-breaking)

Day-one parity: for every existing held module in `module_overrides`, insert an
`org_module_subscriptions` row inheriting the club's current org-wide `subscription_status`
and `renewal_date`. No club changes entitlement on deploy. Backfill `is_primary_admin` to the
earliest `club_admin` per club. Seed `platform_settings.default_trial_days = 14`.

## Twenty inbound channel (generic foundation)

Twenty is export-only today. To accept Twenty-origin requests we add a generic **inbound**
handler: `POST /webhooks/twenty` (shared-secret verified), parsing a Twenty webhook payload
into a typed event, then a small **dispatcher** that routes by event type. The first consumer
creates a `module_action_requests` row (`source='twenty'`) when a club's interested/requested
module changes in the CRM. The dispatcher is deliberately generic so later Twenty-origin
request types (not just module requests) plug into the same entrypoint. Config:
`TWENTY_WEBHOOK_SECRET` in `.env`; the Twenty workspace is set to POST record updates to the
endpoint.

## Phasing

- **Phase 1** — data model + entitlement resolution + backfill + per-module super-admin
  editing + Twenty per-module ARR/paid/trial. (Fixes the CRM TODO, no behaviour change for
  existing clubs.)
- **Phase 2** — request-and-approve queue (club-admin request -> super-admin action),
  notifications, primary-admin gate (+ reassignment), Club General Settings surface
  (default-trial-days), and the Twenty inbound channel for Twenty-origin requests.
