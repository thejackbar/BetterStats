# Self-Serve Club Trial Onboarding — Plan (internal-only phase)

Status: plan agreed, implementation not started. This is the "self-serve signup is
a later phase" mentioned in `onboarding-runbook.md`, and the natural continuation of
`docs/per-module-subscriptions.md` (per-module trial data model — already shipped).

**Source**: a 43-prompt, 21-phase spec document was supplied as a starting point. It
was reviewed against the actual codebase, found to duplicate substantial already-built
infrastructure in places and to conflict with existing systems in others (see
*Reconciliation notes* below), and re-planned from scratch using it as a statement of
intent rather than a literal script. This doc is the reconciled plan.

**Scope of this phase**: internal-only. No public exposure. No Stripe. Both explicitly
deferred — see *Cut from this effort* and *Deferred: "go public" checklist*.

> ⚠️ **KNOWN BLOCKING GAP — this workflow is explicitly NOT complete without it.**
> The app enforces one club per user account at the database level:
> `club_memberships.uq_membership_one_per_user` (a user can have at most one
> membership, ever) and `users.email` (globally unique). Phase 5 therefore
> **blocks** registration outright when the entered email already belongs to an
> existing BetterCricket user, rather than linking them to a second club — the
> source document's "one admin, several clubs" requirement is explicitly
> deferred, not solved. Per direct instruction: **do not consider this
> self-serve workflow complete/production-ready until multi-club identity is
> designed and built** as its own properly-scoped effort (loosening both
> constraints, a club-switcher for ordinary club admins mirroring the existing
> super-admin `active_club_id` pattern, and a re-audit of every club-scoped
> route that currently assumes exactly one membership per user). See Decision
> 14 and the Phase 5 entry below.

---

## Why this shape

There is **no staging/UAT environment** for BetterStats — one production box runs the
whole `bltbox_docker_app` compose stack with real clubs depending on uptime (see
`CLAUDE.md` deploy/outage post-mortems). This plan is built around that constraint:

- Entry point is a new **Super Admin menu item**, not a public URL. Nothing here is
  reachable by an anonymous visitor in this phase.
- Rollout is **directly against prod, behind feature flags**, additive-only migrations
  (Alembic + the idempotent `main.py` lifespan mirror, per house style), flags off by
  default. No separate environment is being stood up for this.
- Full OTP email verification is being **built completely now**, even though nothing
  public exists to point it at yet — the explicit goal is that going public later is
  pure UI wiring (new buttons on `betterat.cricket`), with zero backend work left to do.

## Decisions log

| # | Question | Decision |
|---|---|---|
| 1 | Access model | Internal-only. New Super Admin menu item opens the registration flow. No public `/self-serve` URL in this phase. |
| 2 | Rollout strategy (no staging) | Develop directly against prod behind feature flags (`platform_settings` JSONB booleans, off by default), additive-only migrations. |
| 3 | How to treat the source document | Re-planned from scratch using it as a statement of intent, reconciled against what's actually built. |
| 4 | Stripe scope | Cut entirely from this effort. Trial-only. Stripe was already deliberately deferred in `docs/invoicing-runbook.md` "until self-serve onboarding exists" — that's this effort, but billing itself is a separate, later-scoped project. |
| 5 | Email verification | Build the **complete** OTP flow now (not a stub), so a future public launch is UI-only. |
| 6 | MarketingClub / Twenty CRM | A trial registered through this flow also creates/links a `MarketingClub` row and fires the existing Twenty **Lead + Opportunity** cascade for both the club and the registering admin, simultaneously. |
| 7 | BetterComms bundling | Sandbox defaults are configured **only** when BetterAdmin is among the selected trial modules (not for every trial). |
| 8 | BetterComms Sandbox→Production during a trial | A trial-only BetterAdmin club cannot upgrade to Production sending. Intercepting the existing upgrade-request flow returns a paywall message inviting the club to subscribe to BetterAdmin. |
| 9 | BetterFantasyCricket | Real, fully built (`built: true`), included in the trial module list like any other module — no special-casing. |
| 10 | Notifications | In scope now: a real trial-lifecycle notification system (not deferred to public launch), plus onboarding nudges (see Phase 16). |
| 11 | Onboarding wizard vs. sync | Wizard launches without sync-dependent steps while sync is running; once sync completes successfully, those steps are added and the wizard **reopens automatically** if not already open. |
| 12 | Yearbook auto-generation scope | Last **3** completed seasons (or fewer if the club has fewer), not just the most recent. |
| 13 | Yearbook publish state | **Auto-generate AND auto-publish**, no draft/approval gate — explicit user instruction, overriding the reviewer's recommendation to gate behind admin approval. Documented here as a known accepted risk: an AI-written narrative can go out unreviewed under a real club's name off a sync-completion trigger. Revisit if this causes a real incident. |
| 14 | Existing-user identity (Phase 5) | **Block, don't build multi-club identity now.** Discovered `uq_membership_one_per_user` + globally-unique `users.email` make "one admin, several clubs" a two-constraint schema change, not a form feature — it would need a club-switcher for ordinary club admins and a re-audit of every club-scoped route. Phase 5 detects an email match and stops registration with a clear message; no schema change. **Explicit instruction: this self-serve workflow is NOT complete/production-ready until multi-club identity is designed and built as its own effort.** Don't let later phases' progress read as "done" while this is outstanding. |

## Reconciliation notes (source document vs. reality)

The source document assumed several things that turned out to already exist, and
missed several things that do exist and should be extended instead of duplicated.
Full detail is in the conversation this plan came from; the load-bearing findings:

- **Per-module trials already exist** — `org_module_subscriptions` (migration 118) +
  `module_action_requests` (migration 119), fully documented in
  `docs/per-module-subscriptions.md`. This plan reuses that model wholesale; it does
  not invent a new trial concept.
- **Stripe is 100% net-new** and was already deliberately deferred — see
  `docs/invoicing-runbook.md`, which is itself stale (still describes the retired
  Good/Better/Best tier model) and should be updated once this ships, separately from
  this effort.
- **`POST /organisations/onboard`** (`backend/app/routers/organisations.py`) already
  does club search + org creation + membership attach + sync kickoff in one call for an
  *already-authenticated* user. This plan extends that endpoint with an account-creation
  step rather than building a new atomic transaction from scratch (source doc's Prompt 9).
- **Twenty Opportunity support already exists** — `twenty_opportunity.py`'s
  `create_opportunity_from_company`/`create_opportunity_from_person` already force-create
  a `CONVERTED` Lead then upsert an Opportunity, deduped on the club's grassroots GUID.
  This plan calls that existing cascade; it is not new CRM integration.
- **The BetterComms Sandbox→Production paywall hook already exists** —
  `request_limit_increase` (`backend/app/routers/comms.py:1759`) is the club-admin
  upgrade-request endpoint to intercept, not new request plumbing.
- **APScheduler already exists** (`backend/app/jobs/scheduler.py`), and
  `_scan_trials_and_renewals` (`twenty_leads_tasks.py`) already scans
  `org_module_subscriptions` for trials ending soon and raises a Twenty Task — the new
  trial-lifecycle email/notification job reuses that query/dedup shape.
- **`MarketingClub` (prospect/CRM tracking) and `Organisation` (a real, billable club)
  are separate tables**, loosely linked by an optional FK (`existing_org_id`). This plan
  explicitly links them at registration time (Decision 6) rather than leaving self-serve
  as a third, disconnected path into "being a known club."
- **The notification bell is a pull/live-query model**, not a stored-event/push system —
  there's no generic `notify_admins(...)` hook. Phase 16 below is being built as genuine
  new scaffolding (a scheduler-driven reminder job + delivery), not a small extension.
- **No onboarding-wizard infrastructure exists at all** — confirmed net-new (Phase 15).
- **No OTP/email-verification infrastructure exists at all** — confirmed net-new (Phase 6).
- **No CAPTCHA or public-endpoint rate limiting exists anywhere in the stack.** The
  closest prior art, `routers/public_contact.py`, has zero abuse protection today. This
  is exactly why this phase stays Super-Admin-gated — that whole class of risk is
  deferred to the "go public" checklist, not built now.

## Cut from this effort (separate, later-scoped project)

Pricing/GST engine, Stripe Customer + Checkout, webhook processing, proration,
Bundle Discount administration, Coupon administration, mid-cycle billing changes,
Stripe-linked cancellation semantics. The non-Stripe parts of the source document's
later phases (Super Admin trial controls, Primary Admin/Billing Contact transfer,
archiving a bad registration, reporting views, security review, E2E tests, deployment
readiness) stay in scope, scoped to trial-only state (no ARR/revenue figures, since
there's no billing yet).

## Phased plan

**Phase 0 — Safety scaffolding.**
Feature flags via `platform_settings` JSONB (e.g. `self_serve_registration_enabled`,
`onboarding_wizard_enabled`), off by default, Super-Admin-editable only. Dual
migrations for every new table (Alembic + `main.py` idempotent mirror). Nothing
touches existing `Organisation`/`User`/`org_module_subscriptions` rows except pure
additive backfills. Each phase gets a one-line rollback note before it ships.

**Phase 1 — Entry point.** New Super Admin menu item opening the registration modal
shell. [NET-NEW, small]

**Phase 2 — Club search & duplicate prevention.** Reuse `playhq_client.search_organisations`.
[REUSE]

**Phase 3 — Club identity generation** (slug/short-name/etc). Reuse existing
club-creation identity logic. [REUSE]

**Phase 4 — Admin account details form.** Reuse existing `User` validation
rules/components. Password entry deferred to immediately before final submission
(rather than sitting in state through verification/acknowledgements) — smaller
attack-surface window for no UX cost. [NET-NEW, wraps REUSE validation]

**Phase 5 — Existing-user detection (revised scope, see Decision 14).** Reuses
existing email lookup (`User.email`) to detect a match, but **blocks** rather than
linking — `uq_membership_one_per_user` + globally-unique `users.email` make true
multi-club identity a schema change, not a form feature. Shows a clear
message and stops; does not reveal which club(s) the existing account holds.
**Not complete** — multi-club identity is an explicit, tracked follow-up, not
solved here.

**Phase 6 — Full OTP email verification, built completely now.** Code generation,
hashed storage, 24h expiry, resend/invalidate-earlier-codes, rate limiting (reusing
`services/rate_limit.py`'s `FailureTracker`, proven in `public_availability.py`),
audit timestamps, no code logging. Delivery via the existing SES **transactional**
stream (already separated from bulk BetterComms sends). [NET-NEW]

**Phase 7 — Acknowledgements.** ToS/Privacy/authority-statement acceptance, versioned
and audited. [NET-NEW, small]

**Phase 8 — Idempotent submission.** Disable-on-click, idempotency key, no duplicate
clubs/users/trials on retry/refresh/double-click. [NET-NEW, small]

**Phase 9 — Atomic registration transaction (done).** `_onboard_club_core` was
extracted from `POST /organisations/onboard` (club creation + sync kickoff +
marketing-directory link) so `self-serve-trial/submit` reuses it instead of a
parallel implementation; `/submit` now creates a real `User` + `Organisation` +
`ClubMembership` (primary admin) and starts the first full sync. **Known
atomicity gap**: `upsert_organisation` commits internally (pre-existing,
shared with the ordinary onboarding path — not changed here), so club+user
creation lands in that one commit, but the `ClubMembership` step after it
isn't covered by it. A failure there (needs a genuine DB fault; no external
calls happen in that window) leaves a club+user with no membership and 500s
with an explicit "don't retry, contact support with this org_id/user_id"
message, since a retry would just hit "club already registered" against the
very club the failed attempt created. Judged proportionate for an internal,
Super-Admin-only phase rather than building compensating-transaction
machinery. **This is also where the Phase 5 multi-club-identity gap becomes
real**, not just theoretical: real `Organisation`/`User` rows now exist per
submission.

**Phase 10 — Module trials**, including BetterFantasyCricket. Reuse
`org_module_subscriptions` + `mod_subs.start_trial_billing()` wholesale. [REUSE,
near-total]

**Phase 11 — BetterComms defaults + paywall.** Sandbox defaults configured only when
BetterAdmin is selected. Intercept `request_limit_increase` for trial-only BetterAdmin
clubs: return "Production limits are only available to subscribers" + an invitation to
subscribe to BetterAdmin now, instead of creating the upgrade request.

**Phase 12 — MarketingClub + Twenty Lead/Opportunity creation.** On successful
registration: find-or-create the linked `MarketingClub` row (mirroring the existing
`_resolve_onboarding_club` pattern), then fire the existing
`create_opportunity_from_company` cascade so the club and the registering admin land
as a Twenty Lead + Opportunity simultaneously.

**Phase 13 — Sync trigger + queue governor + progress + admin-home display.** Reuse
the Full Rebuild implementation and `sync_runs`. Build the concurrency governor
properly (the source document's neglected "Phase 6.2") — protects the shared,
rate-sensitive Grassroots proxy from contention if multiple internal test
registrations run syncs concurrently.

**Phase 14 — Auto-login/redirect.** Reuse existing session mechanism.

**Phase 15 — Onboarding wizard (net new).** Launches without sync-dependent steps
(Import Historical Stats, Import Honours, Merge Grades) while sync is running. Once
sync completes successfully, those steps are added and the wizard reopens
automatically if not already open — reusing the same "last seen/dismissed" state
pattern already established for the notification bell.

**Phase 16 — Trial lifecycle notifications + onboarding nudges (net new,
scheduler-based).** Extends the `_scan_trials_and_renewals` pattern into real
outbound reminders:
- Trial started / ending soon / ended / converted.
- "You haven't uploaded your historical data" nudge (with description: if you have
  stats that aren't in PlayHQ, upload them here).
- "You haven't opened module X in N days since your trial started" nudge, linking to
  that module's marketing page.
- Trial-ending-soon reminder linking to blog/marketing pages.

Needs real marketing copy per nudge type — run through the `humanizer` skill per
`CLAUDE.md`'s standing rule when that copy is written.

**Phase 17 — Centralised entitlement extensions.** Mostly already covered by
`org_entitled_modules`; small extensions where the source document's Prompt 20
capability matrix isn't already answered.

**Phase 18 — Trial banner + BetterStats expiry enforcement.** Extends existing
entitlement checks; consistent with the already-shipped per-module model.

**Phase 19 — Trial/Subscription status page.** UI over data that already exists.

**Phase 20 — Super Admin controls.** Trial management, Primary Admin/Billing Contact
transfer, archiving a bad registration.

**Phase 21 — Super Admin reporting.** All Clubs / Trials view extensions, scoped to
trial-only state (no ARR/revenue columns — no billing yet).

**Phase 22 — Yearbook auto-generate + auto-publish.** Last 3 completed seasons (or
fewer if unavailable), triggered on sync completion — real completion signal, not a
fixed sleep. Auto-publish per Decision 13 above (accepted risk, no draft gate).

**Phase 23 — Security review**, scoped correctly to an internal/Super-Admin-gated
surface. CAPTCHA and public-endpoint rate limiting explicitly deferred to the "go
public" checklist below, not built now.

**Phase 24 — E2E regression tests** for the in-scope (trial-only, internal) journeys.

## Deferred: "go public" checklist (not built in this effort)

Captured now so nothing is forgotten later, not actioned here:

- CAPTCHA / bot protection (none exists anywhere in the stack today).
- Public rate limiting on the registration endpoints (`services/rate_limit.py`
  primitives exist and are proven elsewhere, but nothing currently protects a public
  endpoint that creates real `Organisation`/`User`/trial rows).
- A public, unauthenticated wrapper around the club-search endpoint (today's
  `GET /organisations/search` requires auth).
- Marketing page wiring on `betterat.cricket` (buttons pointing at the now-complete
  OTP-backed flow).
- Re-running the Phase 23 security review against the public threat model
  specifically (club enumeration, username/email enumeration, abuse economics).
- Updating `docs/onboarding-runbook.md` and `docs/invoicing-runbook.md`, both of
  which still describe the retired tier model and manual-only onboarding.
- `POST /self-serve-trial/verify-email/send` currently returns the *real*
  provider error on a delivery failure (added for live diagnosis during
  internal testing, since the caller is already a super admin) — swap back
  to a generic message before this is reachable by anyone else.
- Associations aren't shown in club search results (not available from this
  search endpoint; a separate per-club GraphQL call would be needed — see
  `services/playhq_directory_client.discover_associations`). Deliberately
  skipped for now (extra latency/dependency on a live per-keystroke search).

## Related docs

- `docs/per-module-subscriptions.md` — the trial data model this plan builds on.
- `docs/invoicing-runbook.md` — manual billing today; Stripe deferral rationale (stale
  re: tier model, needs a follow-up update).
- `docs/onboarding-runbook.md` — the manual process this plan is the self-serve sequel
  to (also stale re: tier model).
- `docs/twenty-crm-integration.md`, `docs/marketing-club-directory.md` — the CRM/
  prospect-tracking systems Phase 12 links into.
- `CLAUDE.md` — deploy process, outage post-mortems (motivates Phase 0's caution),
  BetterComms/BetterFantasyCricket/module architecture notes.
