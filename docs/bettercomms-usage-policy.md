# BetterComms Sending Policy and Limits

How BetterComms keeps every club's email inside Amazon SES's rules, and how a
club earns a higher sending limit. This is the operator reference. The
club-facing version lives in the Terms (Acceptable use) and in the "Sending
limits" card in BetterComms settings.

## Why there are limits at all

All BetterComms mail goes out through one shared Amazon SES account. AWS grants
that account a **maximum send rate** (14 messages per second) and a **daily
quota** (50,000 messages per day), and it watches the account's **bounce rate**
and **complaint rate**. If those rates get too high (roughly 5% bounces or 0.1%
complaints), AWS puts the whole account under review or pauses it. One club
mailing a stale or bought list can therefore take down sending for every club.

So the limits protect the shared account, not just the individual club. Two
layers do the work:

1. **Account-wide guards** that no single send can bypass.
2. **Per-club tiers** that start a new club small and grow with a clean record.

## Account-wide guards

- **Rate pacing.** Every send passes through one process-global token bucket. The
  rate is a super-admin setting managed from the BetterComms limits page: the
  **AWS ceiling** (14/sec today, bumped when AWS raises the account's rate) and
  **our send rate**, which must always stay strictly below the ceiling (default
  13/sec). Because the app runs a single worker, this one bucket bounds the
  entire account, so all clubs sending at once still cannot exceed the ceiling.
  (If the app is ever run with N workers, divide the send rate by N or move the
  bucket to Redis.) The env values `ses_aws_max_send_rate` / `ses_max_send_rate`
  are the seed defaults used until a super admin sets the live values, which are
  stored in `platform_settings` and read through a warm in-memory cache.
- **Daily quota.** The account holds itself to a practical daily send limit that
  a super admin manages from the BetterComms limits page: the **AWS daily
  ceiling** (50,000 today, bumped when AWS raises the grant) and **our daily
  limit** (e.g. 40,000), which must stay at or below the AWS ceiling. A campaign
  only sends today's remaining allowance; the rest defers to the next day. The
  env values `ses_daily_quota` / `ses_daily_send_limit` are the seed defaults.
- **Throttle retries.** A `Throttling` (429) or transient 5xx from SES is retried
  with backoff instead of dropping the recipient, so a brief rate blip never
  loses mail.

## Per-club tiers

Each club has a `comms_tier`:

| Tier | Daily cap | Meaning |
|------|-----------|---------|
| `sandbox` | `comms_sandbox_daily_cap` (50) | A new or unproven club. Enough to test and email a committee, not to blast a list. |
| `production` | `comms_production_daily_cap` (2,000) | A club with a clean record, lifted by a super admin. |
| `suspended` | 0 | Blocked by the circuit breaker until a super admin reinstates it. |

These are the global defaults. A club can carry its own per-tier override in
`comms_sandbox_cap` / `comms_production_cap`, set by a super admin when
onboarding the club on BetterAdmin (or later from All Clubs). A blank override
falls back to the global default above. The BetterCricket marketing-outreach org
is uncapped.

A brand-new club starts in `sandbox`. Existing clubs were promoted to
`production` on rollout so live sending was never throttled.

### Requesting a lift (the sandbox → production flow)

This mirrors getting out of the AWS SES sandbox, one level up:

1. A club admin sends cleanly from the sandbox, then clicks **Request higher
   limit** in BetterComms settings (optional note).
2. That creates a `comms_limit_requests` row, writes a `club_request_events`
   telemetry row, and raises an automated task in the Twenty CRM.
3. A super admin reviews the request on **Better HQ → Comms Limits**, where the
   club's live bounce and complaint rates are shown next to the ask, and
   approves (optionally with an explicit daily cap) or denies.
4. Approving moves the club to `production`.

Every club → BetterCricket request across the platform (this one, and module
trial/subscribe requests) goes through the same telemetry + Twenty-task helper
(`services/club_requests.py`), so the back office sees a consistent action queue.

## The circuit breaker

A daily job (00:15 UTC, just after the AWS quota resets) checks each production
club's trailing-window deliverability:

- Window: `comms_metrics_window_days` (30 days).
- Only judged once the club has sent at least `comms_metrics_min_sample` (50) in
  the window, so a single bounce on a handful of sends is not treated as a
  problem.
- Trips if bounce rate ≥ `comms_bounce_rate_threshold` (5%) or complaint rate ≥
  `comms_complaint_rate_threshold` (0.1%).

A tripped club is moved to `suspended` (cap 0). A pre-send check also refuses to
start a campaign for a suspended club or one whose rates have already tripped.
Reinstating is a deliberate super-admin action from All Clubs (set the tier back
to production) once the underlying list problem is fixed.

## What happens at the cap

Overflow is never dropped. A campaign sends up to today's allowance (the tighter
of the club cap and the account ceiling), marks the rest `deferred`, and stays
`sending`. The daily resume job sends the deferred recipients the next day
against the fresh allowance, repeating until the campaign is fully sent. A very
large campaign therefore drains over several days without ever breaching a cap.

## Settings reference

All in `backend/app/config/settings.py`, overridable via the server `.env`:

| Setting | Default | Purpose |
|---------|---------|---------|
| `ses_aws_max_send_rate` | 14 | Seed default for AWS's per-second ceiling (live value is super-admin managed). |
| `ses_max_send_rate` | 13 | Seed default for our pacing rate (live value is super-admin managed; must stay below the ceiling). |
| `ses_daily_quota` | 50000 | Seed default for the AWS daily ceiling (live value is super-admin managed). |
| `ses_daily_send_limit` | 45000 | Seed default for our practical daily max (live value is super-admin managed; must stay at or below the AWS daily ceiling). |
| `comms_sandbox_daily_cap` | 50 | Sandbox per-club daily cap. |
| `comms_production_daily_cap` | 2000 | Production per-club daily cap. |
| `comms_bounce_rate_threshold` | 0.05 | Breaker bounce trip. |
| `comms_complaint_rate_threshold` | 0.001 | Breaker complaint trip. |
| `comms_metrics_window_days` | 30 | Deliverability window. |
| `comms_metrics_min_sample` | 50 | Min sends before rates are judged. |

After an AWS increase, raise the AWS rate ceiling, our send rate, the AWS daily
ceiling and our daily limit from the BetterComms limits page (no redeploy).

## Per-club SES tenants (reputation isolation)

Each club is its own Amazon SES **tenant**, so its sending reputation is isolated
and can be paused independently. A club's tenant is auto-provisioned
(`services/ses_tenants.py`) on onboarding and via a backfill over all clubs
(super-admin "Provision club tenants" button, or
`python -m app.scripts.provision_ses_tenants [--all]`). Provisioning uses a
SEPARATE admin credential (`ses_provision_*`); the everyday send key stays
send-only.

- **Naming**: a normal club maps to the slugified club name; the outreach org
  maps to the fixed `ses_marketing_tenant_name` (`bettercricket-marketing`).
- **Wiring**: the provisioner associates the shared sending identity for the silo
  plus the club's context configuration set. **Config set by context**: a normal
  club sends on the transactional stream (`ses_configuration_set_transactional`),
  the outreach org on the campaign stream (`ses_configuration_set`). Both carry an
  SNS event destination, so bounce/complaint feedback flows either way.
- **Send attribution** is gated behind `ses_tenant_sends_enabled` (default off).
  Provisioning, storage and the config-set split all ship independently; flip the
  flag only after confirming the SES send-time tenant mechanism, so it can't
  affect live sends before it's verified.
- **Pause**: an SES tenant paused for reputation is reflected onto the club
  (`ses_tenant_paused`), which blocks its sends until resumed. Tenant status
  events arrive via EventBridge → SNS to the same events webhook (that wiring is
  the remaining ops step; the handler is defensive about the event shape).
- **IAM**: provisioning needs `ses:CreateTenant`, `ses:CreateTenantResourceAssociation`,
  `ses:GetTenant`, `ses:ListTenantResources` (see the deploy notes); the send key
  needs `ses:SendEmail` on both identities and both configuration sets.

## Acceptable use (the club's obligations)

A club may email only its own members and associates, or contacts who have asked
to hear from it. Bought, scraped, or shared lists are not allowed. Every send
carries a working one-click unsubscribe and identifies the sender, as the Spam
Act 2003 requires. BetterCricket may pace, cap, or pause a club's sending to
protect the shared mail service, and may suspend a club that generates high
bounce or complaint rates.
