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

**Phase 10 — Module trials (done)**, including BetterFantasyCricket. Reused
`mod_subs.start_trial_billing` (at the platform's configured default trial
length) for every module wholesale — no new trial logic. Modal defaults all
five optional modules to selected (deselect rather than opt in, per the
source document's framing). Surfaced a real MissingGreenlet trap:
`_onboard_club_core`'s internal commit leaves `module_subscriptions` unloaded
on the now-persistent org, so an explicit `db.refresh(org,
attribute_names=["module_subscriptions"])` (the same idiom `club_admin.py`'s
`patch_club` already uses) is required before touching it — the exact hazard
`create_club`'s own comment warns about.

**Revised (Jul 2026)**: BetterStats (Core) originally used
`mod_subs.ensure_core_subscription` (mandatory, immediately `active`, never
trialled) — mirroring the ordinary Super Admin "New Club" flow, on the
reasoning that Core is always-on and isn't a choice. Live testing surfaced
that this reads wrong for THIS flow specifically: the whole point is a "14 Day
Free Trial", so Core showing `Active` (no trial dates) while every other
module correctly showed `Trial` looked inconsistent on the club's own Plan
line and the Super Admin module editor alike. Switched to
`mod_subs.start_trial_billing(org, MODULE_CORE, days=default_days)` — same
function, same trial window, as every other module — so Core now reads
`Trial` with matching start/end dates too. The ordinary authenticated onboard
flow (a real customer onboarding directly, not a trial) still uses
`ensure_core_subscription` — deliberately unchanged there.

**Phase 11 — BetterComms defaults + paywall (done).** Part 1 (sandbox defaults
"configured only when BetterAdmin is selected") turned out to need zero new code:
`Organisation.comms_tier` already defaults to `'sandbox'` at the schema level
(migration 125, `server_default="sandbox"`) for every club regardless of module
selection, and the cap fields are nullable and inherit the platform-wide defaults
dynamically — there is no per-club "configure" step to gate. Part 2 (the paywall) is
a small guard clause added to the top of `request_limit_increase` in `comms.py`: if
the club's `MODULE_COMMS` subscription is `STATUS_TRIAL`, raise `402` with "Production
sending limits are only available to subscribers... subscribe to BetterAdmin to
request production sending" instead of creating the upgrade request. Relies on
`get_current_club` already eager-loading `module_subscriptions`, so no extra query.
No frontend change needed — `CommsSettings.jsx`'s `requestLimit` already displays
`e.message` generically for any thrown error, so the 402's plain-string `detail`
renders correctly as-is.

**Phase 12 — MarketingClub + Twenty Lead/Opportunity creation (done).** New
`twenty_sync._resolve_self_serve_club` finds-or-creates the `MarketingClub` +
registering-admin `MarketingClubContact` for a completed registration — checked in
order: a row `_onboard_club_core` already linked to this exact org (it runs first,
inside the same registration, and may already have matched-and-linked one by
playhq_id or name), else a row keyed on the org's own id (the same guid the
directory crawler would itself use for a grassroots-sourced club), else an exact
name match, else create fresh. Unlike a bare "onboard my club" enquiry
(`_resolve_onboarding_club`, no real CA identifier, mints a synthetic guid), a
registration always has a real org to key on, so no synthetic id is ever needed.
`push_club_and_contacts` gained `create_opportunity`/`opportunity_modules` params
(off by default, so every existing caller — campaign sends, the enquiry path — is
unaffected) that, right after the Lead upsert, also call
`twenty_opportunity._upsert_opportunity` directly. Rather than going through the
webhook cascade (`create_opportunity_from_company`, which expects a human to flip
Twenty's own field and round-trips through the Twenty API to re-derive the club),
calling the same underlying upsert directly is simpler here since the club/company
id are already in hand from the same request. New `push_self_serve_registration`
(`twenty_sync.py`) ties it together: resolve club/contact, commit, then
`push_club_and_contacts(..., engagement_override=<forced Hot 100>,
create_opportunity=True, opportunity_modules=<the modules the admin selected>)` —
same forced-Hot treatment `push_onboarding_enquiry` gives a plain enquiry, plus the
Opportunity a registration (a materially stronger signal) doesn't wait on. Wired
into `self_serve_trial.py`'s `/submit` as a `background_tasks.add_task` right after
the transaction commits — best-effort, never blocks or fails the registration
response.

**Addendum (Jul 2026)**: the Lead and Opportunity now open at a distinguishing
"Self-Serve Trial" value instead of the generic computed lifecycle/default
stage — `Lead.lifecycleStage = SELF_SERVE_TRIAL` (a new Lead-only option) and
`Opportunity.stage = SELF_SERVE_TRIAL` (a new pipeline stage, after "Trial").
Full detail in `docs/twenty-crm-integration.md` §20, including the caveat that
the Lead's value is a creation-moment marker only (the next daily refresh, or
even the next ordinary campaign send to this club, recomputes it from the
normal engagement model) whereas the Opportunity's is effectively permanent
(stage is never recomputed by anything else). **Requires re-running
`bootstrap_twenty.py`** against the live workspace before the new option
values exist in Twenty.

**Phase 13 — Sync trigger + queue governor + progress + admin-home display
(done).** The sync trigger itself needed no new code — `_onboard_club_core`
(Phase 9) already kicks off the org's first full sync via the same
`start_sync_run`/`_sync_safe` machinery `POST /organisations/{id}/sync` uses.
Found (and fixed) a small pre-existing gap while reviewing it: that call never
added the org to `organisations.py`'s `_org_sync_running` in-memory guard, so
an operator clicking "Sync Now" on a brand-new self-serve club while its own
first sync was still running could race a second sync of the same org — now
added right alongside `start_sync_run`.

**Concurrency governor**: `sync.py`'s `sync_organisation` was renamed to
`_sync_organisation_impl` (body untouched) and re-exported as a thin wrapper
that acquires a new module-level `_SYNC_GOVERNOR = asyncio.Semaphore(2)`
before calling it — every caller (weekly cron, manual Sync Now, Full
Rebuild, per-player deep sync, self-serve registration) goes through the
same public `sync_organisation` name, so the cap applies uniformly at the
one place that actually talks to the shared, rate-sensitive Grassroots
proxy, with zero changes to the sync logic itself. The weekly cron already
awaits one org at a time (`jobs/scheduler.py`), so it's unaffected in
practice — this exists for the case several "Sync Now" clicks or self-serve
registrations land close together. When a sync has to wait for a slot, it
stamps `progress_phase: "Queued — waiting for another club's sync to
finish"` onto its `sync_runs` row so it reads as waiting, not stuck.

**Progress**: already fully persisted by the existing `sync_runs.stats`
`progress_phase`/`progress_pct`/`progress_done`/`progress_total` fields
(`_progress`/`update_sync_run`, called throughout `sync_organisation`'s
phases) — no new persistence needed, just the new queued phase above.

**Admin-home display**: since Phase 14 (auto-login) and Phase 15 (onboarding
wizard) don't exist yet, a self-serve-registered club has no "own admin
home" to show this on yet — the meaningful place for THIS phase is where the
Super Admin operator already is. `SelfServeTrialModal.jsx`'s success screen
now polls `GET /organisations/{id}/sync-logs` (the same endpoint
`AdminSync.jsx` already polls, 4s cadence) and renders a live `ProgressBar`
(reusing `components/ProgressBar.jsx`) against the just-started run, stopping
once it's no longer `running`. Revisit once Phase 14/15 exist — the new
admin's own dashboard becomes the more natural home for this.

**Phase 14 — Auto-login/redirect (done, deliberately not automatic yet).**
Session auth turned out to be a plain HttpOnly JWT cookie (`bs_session`),
minted by two small, previously module-private helpers in `auth.py`
(`_create_token`/`_set_session_cookie` — de-privatised to
`create_session_token`/`set_session_cookie` since they're now a real
cross-router primitive). Auto-login the naive way — set that cookie on
`/submit`'s own response — turns out to be actively wrong in THIS phase: the
router is `require_super_admin`-gated, so the only caller is ever the
operator's own Super Admin session, and silently swapping their session
cookie for the new club admin's would eject them from Super Admin without
asking, every single test registration. (Confirmed there's no existing
"impersonate" mechanism to reuse — the closest analogue, `active_club_id`/
`switch-club`, is a same-session scope switch that never touches the cookie
at all, a different and safer shape than "mint a new session and swap it
in".)

Built the real thing anyway, per Decision 5's "build the complete primitive
now" philosophy, just gated behind an explicit action instead of an automatic
one: `POST /self-serve-trial/login-as/{user_id}` mints and sets the session
cookie for the given user — scoped tightly to accounts THIS flow created (a
`SelfServeIdempotencyKey` row must reference the exact user id), so it can
never become a general impersonation backdoor. `SelfServeTrialModal.jsx`'s
success screen gained a "Log in as new admin" button (explicit
`window.confirm`, since it deliberately ends the operator's own session) that
calls it then hard-reloads to `/admin` (mirroring `switchClub`'s own hard
reload, so every already-mounted page refetches under the new session).

**When this goes public**: the exact same `create_session_token`/
`set_session_cookie` primitive is what a public registration endpoint should
call unconditionally right after account creation — no new backend work,
only a different (unauthenticated) caller and no more explicit-action gate,
since there's no super-admin session to protect from a public visitor.

**Phase 15 — Onboarding wizard (done).** New `onboarding_wizard_state` table
(migration 140, one row per club, not per user — onboarding is a club property,
so a second admin invited later sees the same progress rather than starting
over): `completed_steps` (JSON array), `dismissed_at`, `sync_steps_shown_at`.
New router `routers/onboarding_wizard.py` (`/club-admin/onboarding-wizard/*`,
gated by the already-existing-but-previously-unwired
`require_onboarding_wizard_enabled` flag dependency) computes a dynamic step
list rather than storing one: a fixed set of always-shown steps (branding,
invite another admin, one "Explore <Module>" step per module the club is
actually entitled to via `org_entitled_modules`), plus — only once the club's
first `kind='org_full'` sync has a `success` row in `sync_runs` — the three
sync-dependent steps named in Decision 11: Import Historical Stats
(`/admin/import`), Import Honours (`/admin/awards`), Merge Grades
(`/admin/grades`). Every step links to an existing admin tool (found via a
research pass first — branding/invite-admin/historical-stats-import/honours-
import/grade-merge all already existed); this wizard is a guided checklist
over them, not a reimplementation of any of them.

**Auto-open logic** mirrors the notification bell's `last_notification_seen_at`
pattern but needed a second flag for Decision 11's specific "reopens once sync
completes" requirement: `should_auto_open` is true when nothing is dismissed
yet, OR when sync just became ready and the sync-dependent steps haven't been
shown even once (`sync_steps_shown_at IS NULL`) — gated on there being
anything left undone at all, so a club that's finished every step doesn't keep
popping the wizard on every login. `POST /onboarding-wizard/opened` (called by
the modal itself on open, auto or manual) stamps `sync_steps_shown_at`, which
is what makes the reopen fire exactly once per sync completion rather than on
every subsequent login. `AdminLayout.jsx` checks on every fresh login (the
same `justLoggedIn` signal the bell's own auto-open reuses, so a genuine login
event — not every page navigation — is what re-checks this) and shows a
"Setup guide" header button whenever the state fetch succeeds (a 404 — flag
off — just hides the entry point, same "doesn't exist" convention as the rest
of this project's feature flags). `OnboardingWizardModal.jsx` is otherwise
self-contained: fetches its own state, lets each step be ticked done/undone
independently of navigating to it (so an admin who already did something
manually, e.g. inviting an admin before ever seeing the wizard, can just tick
it), and each step's title is a link that closes the modal and navigates
there.

**Phase 16 — Trial lifecycle notifications + onboarding nudges (done).**
`app/services/trial_lifecycle.py` extends the `_scan_trials_and_renewals`
query/dedup shape into real outbound email, but deliberately CRM-independent
(runs whether or not Twenty is configured, scoped to every club with a
module trial — not just the subset exported to Twenty) since a trial club
has nobody watching a CRM. Six nudge types, one daily scan
(`send_trial_lifecycle_nudges`, scheduler.py, 08:00 — right after the Twenty
scan since both read `org_module_subscriptions`):

- `trial_started` / `trial_ending_soon` (`TRIAL_ENDING_SOON_DAYS=3`) /
  `trial_ended` / `trial_converted` — scanned straight off
  `org_module_subscriptions.status`/`trial_started_at`/`trial_ends_at`/
  `updated_at`. The ending-soon email links to the pricing page per the
  source document's "linking to blog/marketing pages" framing — read as
  content guidance for the one ending-soon email, not a fifth nudge type.
- `no_historical_data` — reuses Phase 15's `onboarding_wizard_state`
  (`'import_stats' NOT IN completed_steps`) rather than inventing a new
  "has this club imported" flag; fires `NUDGE_HISTORICAL_DATA_DAYS=5` into a
  Core trial.
- `module_unopened` — reuses `usage_events` (the existing SPA page-view
  beacon, `frontend/src/hooks/usePageView.js`, already fires on every admin
  route including trial-only ones) rather than building new per-module
  "last opened" tracking: a trialled module counts as opened once anyone at
  the club has a `page_view` row under that module's admin route
  (`frontend/src/lib/modules.js` `MODULE_INFO[].to` / `MODULE_GROUPS.admin.to`)
  since the trial started, joined via `club_memberships.user_id`. Fires
  `NUDGE_MODULE_UNOPENED_DAYS=5` in.

BetterAdmin's three billing members (fees/comms/merch) collapse to one nudge
via `billing_key_for` — a club that starts a BetterAdmin trial gets one
email, not three; whichever of the three rows is processed first wins the
dedupe check, the other two see it already recorded and no-op.

**Dedup**: new `trial_lifecycle_nudges` table (migration 148), one row per
`dedupe_key` — check-then-send-then-record (not claim-then-send): the record
is only written *after* a successful send, so a provider failure or crash
mid-send gets retried on the next scan instead of being silently marked
done forever. A deterministic key (`{nudge_type}:{billing_key}:{org_id}` plus
a date component for the four time-boxed lifecycle events, matching
`twenty_leads_tasks._scan_trials_and_renewals`'s own `ext_ref` shape) is what
makes a multi-day matching window (e.g. "ends within 3 days") fire exactly
once rather than once per day it stays in range.

**Recipient**: the club's own primary admin (`club_memberships.is_primary_admin`,
falling back to any admin with a usable email) — always present for a
self-serve-registered club (Phase 9 sets it at registration). A club with no
resolvable admin is logged and skipped, never raised as an error (one bad
row must never stop the rest of the scan).

**Email**: plain inline-styled HTML matching `self_serve_verification.py`'s
existing OTP-email pattern (a system-level transactional send off the
transactional SES stream — `settings.email_from_address`/`ses_configuration_set_transactional`
— not a BetterComms campaign, so no club-shell/unsubscribe wrapper). Copy
was written directly in the plain Australian house voice (no em dashes, no
promotional language) per `CLAUDE.md`'s standing humanizer rule.

**Safety**: off by default behind a new `platform_settings.trial_nudges_enabled`
flag (General Settings → the same super-admin-only pattern as
`self_serve_registration_enabled`/`onboarding_wizard_enabled`) — Phase 0's
"nothing here touches prod until a super admin flips it on" caution applies
just as much to unsolicited email as to a new UI surface.

**Phase 17 — Centralised entitlement extensions (reviewed, no gap found).**
Audited end to end rather than guessing at the source document's unpreserved
Prompt 20 capability matrix: (1) every module's **backend** router is gated
centrally at `app/main.py`'s `include_router(..., dependencies=[Depends(require_module(...))])`
call, one line per module, with the one deliberate exception (BetterSocials
shares `admin.py`'s router, so it's gated per-route instead — confirmed all
three `/social/*` routes carry the dependency, none missing it); (2) every
**public**, unauthenticated module surface (`public_availability.py`,
`public_fantasy.py`) self-checks `org_has_module` rather than relying on
`require_module`, since there's no session to hang a dependency off; (3)
`require_module`'s super-admin bypass returns early before touching the
resolved club, so it stays correct even though its own club lookup (unlike
`get_current_club`) doesn't honour the acting-as override — harmless, since
the entitlement check itself never runs for that role; (4) on the
**frontend**, every module route in `App.jsx` carries a matching
`<ProtectedRoute requireModule="...">`, and the sidebar's Modules section
(`dashboardTiles()` in `AdminLayout.jsx`) computes `entitled` off the same
`hasModule()` the routes use, so the nav and the route guard can't drift
apart. No extension needed — the single source of truth (`org_entitled_modules`
backend-side, `hasModule()` frontend-side) already reaches every surface.

**Phase 18 — Trial banner + BetterStats expiry enforcement (done).** Expiry
enforcement already existed: `org_core_live` gates both public routers
(`clubs.py`, `website.py`) so a club whose Core trial has lapsed drops off
the public site, fail-open by design (an unloaded/pre-backfill club is never
accidentally taken down). Admin access itself is deliberately NOT gated on
it — Core isn't in `ALL_MODULES` (never a gateable module), so a club can
always still log in and subscribe even mid-lockout.

The missing piece was purely the **trial banner** UI — new
`frontend/src/components/admin/TrialBanner.jsx`, mounted once in
`ProtectedRoute.jsx` (the one wrapper every `/admin/*` route passes through,
core AND module-specific layouts alike — `AdminLayout` itself isn't shared
across module pages, so mounting it there would have missed BetterSelect/
BetterIQ/etc.). Reads `user.entitlements.billing_modules`, already returned
by `/auth/me`/`/auth/login` (`entitlement_summary`, Phase 10-13) — no new
endpoint. Shows the soonest-ending trial's days remaining (or "trial has
ended" once past `trial_ends_at`), amber once ≤7 days or expired, linking to
the public pricing page (Phase 19's dedicated status page doesn't exist yet).
Hidden for super admins, matching the wizard's own exclusion.

**Phase 19 — Trial/Subscription status page.** UI over data that already exists.

**Phase 20 — Super Admin controls.** Trial management, Primary Admin/Billing Contact
transfer, archiving a bad registration.

**Phase 21 — Super Admin reporting.** All Clubs / Trials view extensions, scoped to
trial-only state (no ARR/revenue columns — no billing yet).

**Phase 22 — Yearbook auto-generate + auto-publish (done, v8.61.3).** Shipped out of
sequence in a separate session — see `CLAUDE.md` "Yearbook auto-generate + auto-publish
on Full Rebuild". Scoped to Full Rebuild specifically (not every routine sync) as the
"real completion signal" this phase called for. Last 3 completed seasons with stats (or
fewer if unavailable); auto-publish per Decision 13 above (accepted risk, no draft
gate) — never overwrites a season that already has narrative content.

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
