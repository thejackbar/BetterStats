# BetterComms — communications architecture

Status: living design note. Phase 1 (the delivery + suppression foundation) is
landing now; later phases are planned, not built. This doc is the single place
that ties the data model to the AWS SES delivery layer, so read it alongside the
SES tenant notes below before changing either.

## What BetterComms is becoming

BetterComms started as a Mailchimp-style bulk sender scoped to one club. It is
growing into the communications layer for every Better module: campaign email
now, transactional and operational email next, and SMS / push later, all behind
one preference and suppression model. The shape we are aiming at is closer to
Customer.io or Postmark than to a newsletter tool: the **person** is the anchor,
events tie back to the person, segments are saved queries rather than stored
lists, and transactional mail is kept completely apart from campaigns.

We borrow that spirit, but two facts about BetterStats change the model, and they
are the important part of this document.

### Fact 1: the person already exists, and consent is per club

The recipients are not a separate contact database. They are the `players` and
`fee_members` we already hold, per club. `comms_contacts` is keyed on
`(organisation_id, email)` and already links back via `player_id` / `member_id`,
so today's BetterComms is a per-club projection of the person.

The tempting "one global person, no duplicate contacts ever" model fights this on
purpose, and we keep the per-club split deliberately:

- Each club is a separate data controller under the Spam Act 2003 (and UK GDPR as
  we expand). Consent, unsubscribe state, and the lawful basis to email belong to
  the club, not to a global identity. Someone who unsubscribes from Applecross has
  not unsubscribed from Scarborough, and the two must never be one switch.
- The shared CA participant GUID work elsewhere in this codebase shows how fraught
  a true cross-club person is: one human maps to many club registrations with
  conflicting data. We scope players per club for exactly that reason.

So the person of record is **per club** (the Player / Member), and the comms
profile hangs off it.

### Fact 2: one thing genuinely is global

A hard bounce or a spam complaint is a fact about the **mailbox**, not about a
club. If an address is dead it is dead everywhere; if someone marks us as spam we
must stop sending them marketing from any club. That single piece of global state
lives in `email_suppressions`, keyed on the email address. Everything else
(unsubscribe, preferences, tags, lists) stays per club.

This resolves the "no duplicates" tension cleanly: **one global layer for
deliverability truth, per-club layers for consent.**

### Fact 3: Organisation and Club are the same row

We are single-level: `organisations` *is* the club table. BetterCricket the
platform is just another org (the marketing-outreach one, flagged
`is_marketing_outreach`). There is no parent Organisation entity, and we should
not add one. The thing above the club is the SES account and the brand, not a DB
parent.

## Entity model (target)

Adapted from the modern engagement-platform shape, grounded in what we hold:

| Entity | In BetterStats | Notes |
| --- | --- | --- |
| Club | `organisations` row | top entity; BetterCricket is one of these |
| Person | `players` / `fee_members` | per club; the record of truth |
| Comms profile | `comms_contacts` | per-club projection: email, tags, per-club suppression, preferences |
| Tag | `comms_contacts.tags` (JSONB) | free-form, for search and ad-hoc lists |
| Static list | curated set of contacts | committee, sponsors, a team — phase 2 |
| Dynamic segment | a saved query | over stats / fees / availability / roles — phase 2, our edge |
| Template / version | reusable HTML + merge fields | phase 3 |
| Campaign | `comms_campaigns` | one send; category NEWS or MARKETING |
| Recipient | `comms_recipients` | per-send delivery row; carries `provider_message_id` |
| Email event | `email_events` | append-only: delivered / bounce / complaint / open / click, tied to person + campaign |
| Suppression (global) | `email_suppressions` | address-level: hard bounce, complaint, manual |
| Automation / journey | not built | phase 4, triggered by app events |
| SES tenant / config set / identity / domain | AWS, per club | the delivery layer, below |

## Message categories and the send gate

Every send has a **category**, and the category decides what can suppress it. This
is how transactional mail stays separate from campaigns without a second send
path. Defined in `services/comms_policy.py`:

- `transactional` — password reset, invite, verify, 2FA, receipt. Never
  suppressed except by a hard bounce (the mailbox is undeliverable). Must keep
  flowing; AWS expects this.
- `operational` — selection, availability, fee reminders. Club operations to
  members. Suppressed by hard bounce and complaint; respects a per-club
  unsubscribe by default.
- `news` — club newsletters and announcements. Suppressed by everything.
- `marketing` — promotional and BetterCricket Clubs Directory outreach. Suppressed
  by everything.

Campaigns are `news` or `marketing`. The gate (`services/email_suppression.py
::deliverable`) checks, in order: global suppression (hard bounce blocks all;
complaint blocks all but transactional), then per-club state (unsubscribed,
bounced, complained, admin-excluded), then the per-person preference for that
category. The campaign audience query applies the same rules in bulk.

Keep transactional and bulk on **separate SES configuration sets** (and arguably
the platform tenant) so a club's marketing complaint can never pause password
resets, and a hard-bounce storm on a campaign never touches transactional
reputation.

## Delivery layer: AWS SES

The mapping from this model onto the SES design (see the CLAUDE.md SES notes and
the SES setup thread):

```
AWS account
  └─ domain identity  (betteradmin-comms.work for clubs, betteratcricket-comms.work for BetterCricket marketing)
       └─ tenant       (one per club + one for BetterCricket)
            └─ configuration set  (split: transactional vs campaign)
                 └─ send  (From {club-slug}@betteradmin-comms.work, display name = club, reply-to = club inbox)
                      └─ SNS event destination → /public/ses/events webhook → email_events + suppression
```

- The **SES sending provider is built** (`SesEmailProvider` in
  `services/email_service.py`): the SESv2 send API, SigV4-signed with stdlib only
  (no boto3). Set `email_provider=ses` plus the `ses_*` settings. Each send gets a
  per-club From on the verified silo domain (`{slug}@betteradmin-comms.work`, or
  the marketing domain for the outreach org) and the campaign configuration set.
- One verified domain per silo, one SES tenant per club, so reputation is isolated
  and a bad actor pauses only their own tenant. Per-club From local-parts need no
  per-club AWS admin (domain verification covers every local-part).
- Per-message events (bounce, complaint, delivery, reject, delay) come back via a
  configuration-set SNS destination to our webhook. Tenant reputation / auto-pause
  events come via EventBridge (not wired in Phase 1).
- The webhook **verifies the SNS message signature** before acting, confirms the
  `SubscriptionConfirmation` handshake, and dedupes on the SES `messageId`. Without
  signature verification the suppression list is an abuse vector (anyone could
  forge a complaint and silence a contact).

## Phased plan

**Phase 1 (now): person + delivery foundation.**
- Global `email_suppressions` (hard bounce, complaint, manual) + the two-layer
  send gate.
- Append-only `email_events`, every row tied to the person and campaign via the
  recipient's `provider_message_id`.
- Per-person, per-category `preferences` on the comms profile, and per-club
  `complained` state alongside the existing `bounced` / `subscribed` / `excluded`.
- The signature-verified SES SNS webhook (`/public/ses/events`) that ingests
  events, writes them, and maintains suppression.
- Category taxonomy + a reusable `deliverable()` gate the rest of the app can call.

**Phase 2 (first increment built): segmentation — our unfair advantage.** Dynamic
segments as saved queries over data Mailchimp can't see. `comms_segments` stores a
rule set (`{match: all, rules: [{field, op, value}]}`) evaluated at send time by
`services/comms_segments.py` against the club's contacts joined to the player and
current-season stats. Whitelisted fields only (no client SQL): tag, source, and
matches / runs / wickets / catches this season. A segment is a valid campaign
audience (`{type: "segment", segment_id}`) and always re-evaluates, so it reflects
current data. The send gate (`sendable_where`) is always applied, so a segment can
never reach a suppressed address. Next: more fields (role, squad, fees unpaid,
availability set) and saved static lists.

**Phase 3: templates with versioning.** Reusable blocks, merge fields, categories.

**Phase 4 (last): automation / journeys.** Triggered sends ("membership approved →
welcome", "selection published → email the named players", "invoice overdue →
reminder"), driven by app events that already fire. Large build with its own state
machine; not worth starting until 1 and 2 are solid.

## What Phase 1 deliberately does not do

No journeys, no template versioning, no static-list or segment builder, no opens /
clicks dashboard yet (open tracking is noisy thanks to Apple Mail Privacy
Protection, so it stays a soft signal). EventBridge tenant-status handling is also
out. Those are later phases; Phase 1 is the spine they all attach to.
