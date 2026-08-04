# Project rules (carried into the target codebase)

## BetterComms — Super Admin vs club scope

BetterComms serves two different audiences from one engine, and they must stay strictly separated:

- **Club scope** — a club officer emailing their own people. Fields come from the club's Directory, accounts, roster, events and email activity only.
- **Super Admin scope** — BetterCricket's own marketing against the Clubs Directory: `is_trialing`, `requested_trial`, `had_demo`, `customer_status`, `directory_status`, `engagement_score`, `visited_page`, `exported`, plus the marketing-org context switch and the act-as-club mechanism.

**Never expose Super Admin features, fields, context bars or copy to a club build** — not behind a dropdown, not greyed out, not in a segment field list. A club must never see BetterCricket's sales telemetry or the Clubs Directory context. Same engine, two mounts: the prospect field set belongs behind BetterCRM / a super-admin-only surface.

Apply the same rule to any future module that gains a platform-side mode.
