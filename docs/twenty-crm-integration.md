# Twenty CRM ↔ BetterCricket Integration — Scope

Status: design / scoping (June 2026). No code shipped yet. This document defines
the target Twenty data model, the BetterCricket source entities that feed it, the
API surface to build, the two-way sync workflow, and a phased build plan.

Twenty is self-hosted on the box at `https://twenty.betterat.cricket`
(`twenty-server` / `twenty-worker` / `twenty-db` / `twenty-redis` on
`docker-shared-net`). Workspace: **BetterCricket**.

## 1. Objective

Give the sales and customer-success process one live view of every cricket club:
who they are, who the officers are, where they sit in the pipeline, which modules
they pay for / trial / have shown interest in, how engaged they are on the website
and in the app, and the full history of correspondence and actions. Use that to
profile, score, and prioritise suspects, prospects, and existing customers.

BetterCricket already holds all the raw material (prospect directory, customer
orgs, module entitlements, web/app telemetry, email campaigns). What it lacks is a
sales workspace to act on it. Twenty is that workspace.

## 2. The two architectural rules everything follows

### Rule 1 — Twenty is a curated subset, not a mirror of the directory

The **Club Directory is the superset**: every club and named officer found in the
source club databases (today PlayHQ Australia; later other countries and sources).
A club being in the directory does **not** mean we want to sell to it. **Twenty
holds only the subset we choose to target, track, and manage** through the sales
and customer cycle.

Membership in Twenty is opt-in, by the **same filter-then-export technique the
directory already uses for BetterComms**. A Super User filters the directory
(exclude juniors / carnivals / schools, pick a state or association, and so on) and
**exports that filtered slice to Twenty**. The export upserts: it creates clubs and
officers that aren't there yet, fills missing data on ones that are, and never
duplicates. Re-running a broader filter later simply adds more. So:

- BetterCricket directory = all clubs/people (the suspect pool).
- Twenty = the targeted clubs/people only (prospects through customers).
- A club enters Twenty when exported, never automatically.

This also keeps Twenty small and focused: hundreds to a few thousand targeted
clubs, not the full ~6,500 / ~20,000 directory. Every "push" below operates on the
**exported subset**, tracked by the `twenty_links` membership ledger (§7), not on
the whole directory.

### Rule 2 — BetterCricket owns facts and telemetry, Twenty owns the pipeline

**BetterCricket is the system of record for facts and telemetry. Twenty is the
system of record for the sales pipeline and human judgement. Each pushes to the
other only what the other can't compute itself.**

- BetterCricket → Twenty: identity, module/subscription state, and a small
  **engagement rollup** (score, last-seen, sessions, modules explored). It does
  **not** push raw `usage_events`. Raw telemetry is high volume (every page view
  and API call) and would swamp the CRM. BetterCricket aggregates per club and
  pushes the summary, only for clubs that are in the subset.
- Twenty → BetterCricket: pipeline stage changes, owner assignment, and
  sales notes/tasks a human enters, via webhooks. BetterCricket acts on those
  (e.g. stage moves to "Trial started" so BetterCricket provisions the trial).

If we ever want raw-event history visible in Twenty, it goes as a periodic
**snapshot** custom object, not a live event stream. Out of scope for v1.

## 3. Twenty data model

### 3.1 Objects

| Object | Standard/custom | Represents | Source in BetterCricket |
|---|---|---|---|
| **Company** | standard | A **targeted** cricket club (prospect, trial, or customer); suspects stay in the directory | `marketing_clubs` + `organisations` |
| **Person** | standard | A club officer / named contact | `marketing_club_contacts` + customer-org contacts |
| **Opportunity** | standard | One sales pursuit per club; carries the pipeline stage | derived from club status |
| **Touchpoint** | **custom (new)** | A typed correspondence/action/event (campaign sent, reply, demo, trial start, onboarding enquiry, milestone) | `comms_campaigns`/`comms_recipients`, `club_onboarding_requests`, key `usage_events` |
| **Association** | **custom (new)** | A cricket association/competition a club belongs to | `list_associations` registry (~677), `marketing_clubs.associations` |
| **Email** (Campaign) | **custom (new, optional)** | A named BetterComms bulk email; lets you see everyone who received "Email X" | `comms_campaigns` |
| Note / Task | standard | Free-form sales notes and follow-ups | entered in Twenty, mirrored back to BetterCricket |
| Workflow / Dashboard | standard | Twenty-side automation and reporting | configured in Twenty |

A single **Touchpoint** custom object is enough. We deliberately do **not** create
a per-event-stream object. Touchpoints are low-volume, meaningful events only.

### 3.2 Company custom fields

Twenty Company already has name, domain, address, employees, linkedin, etc. Add:

| Field (camelCase) | Type | Holds |
|---|---|---|
| `bcClubId` | TEXT (unique key) | `marketing_clubs.grassroots_guid` (stable external id) |
| `bcOrgId` | TEXT | `organisations.id` once the club is a customer/trial |
| `lifecycleStage` | SELECT | Target, Prospect, Engaged, Trial, Customer, Churned, Suppressed (no "Suspect"; suspects stay in the directory) |
| `subscriptionStatus` | SELECT | none, trial, active, past_due, paused, cancelled |
| `paidModules` | MULTI_SELECT | the 7 module keys (see §3.5) |
| `trialModules` | MULTI_SELECT | modules currently trialing |
| `interestedModules` | MULTI_SELECT | modules requested or explored on the site |
| `engagementScore` | NUMBER | 0–100 rollup computed in BetterCricket (§5) |
| `engagementTier` | SELECT | Cold, Warm, Hot |
| `lastSeenAt` | DATE_TIME | most recent `usage_events.created_at` for this club/visitor |
| `sessions30d` | NUMBER | distinct sessions in last 30 days |
| `renewalDate` | DATE | `organisations.renewal_date` |
| `billingCycle` | SELECT | monthly, annual |
| `arr` | CURRENCY | annual value (derived from modules held) |
| association membership | via the `clubAssociation` junction object (Company ←→ Association, many-to-many), each membership carrying `isPrimary` | Twenty's metadata API has no native many-to-many, so a club in several associations is modelled as one junction row per membership; the primary one is flagged `isPrimary`. No denormalised `primaryAssociation` field — it's recoverable from the relations |
| `clubKind` | SELECT | club, association, carnival, school, junior (drives the directory exclude filters) |
| `postcode` | TEXT | `marketing_clubs.postcode` (enables the postcode-range filter) |
| `state` | SELECT | NSW, VIC, WA, … (`marketing_clubs.state`) |
| `country` | SELECT | `marketing_clubs.country`; AU today, the partition for multi-country expansion |
| `dataSource` | SELECT | playhq, play_cricket, … which source DB the club came from (roadmap; defaults playhq) |
| `utmCode` | TEXT | `marketing_clubs.utm_code` (joins to `usage_events.utm_id`) |
| `firstTouchSource` | SELECT | facebook, google, email, direct, … (`usage_events.traffic_source`) |
| `existingKpCustomer` | SELECT | No, Yes, Previous (from the directory enrichment) |
| `publicProfileUrl` | LINKS | `betterat.cricket/{slug}` when a customer |
| `lastSyncedAt` | DATE_TIME | sync bookkeeping / loop guard |

### 3.3 Person custom fields

Twenty Person already has name, emails, phones, company relation, job title. Add:

| Field | Type | Holds |
|---|---|---|
| `bcContactId` | TEXT (unique key) | `marketing_club_contacts.id` |
| `clubRole` | SELECT | President, Vice President, Secretary, Treasurer, Registrar, Coordinator, Club contact, Sponsor, Other |
| `roleRank` | NUMBER | `marketing_club_contacts.role_rank` (1 = President … 99 = other) |
| `subscribed` | BOOLEAN | email-eligible (`comms_contacts.subscribed` / `marketing_club_contacts.subscribed`) |
| `bounced` | BOOLEAN | hard bounce |
| `outreachSelected` | BOOLEAN | ticked for outreach |
| `lastEmailedAt` | DATE_TIME | most recent campaign send to this address |
| `contactSource` | SELECT | api, website, manual |
| `namedEmail` | BOOLEAN | email belongs to a real person, not a generic club mailbox (drives the `named_email` / `pst` filters) |
| `emailsReceived` | NUMBER | count of bulk Emails sent to this person (rollup) |

### 3.4 Opportunity: the custom pipeline

Repurpose the standard Opportunity. One open Opportunity per club in the acquisition
funnel. The pre-sale pipeline lives on `Opportunity.stage` (a SELECT we overwrite);
post-sale lifecycle lives on `Company.subscriptionStatus` + `Company.lifecycleStage`.

Pipeline stages (replace the default Opportunity stage options). Note "Suspect" is
**not** a stage: a suspect is an un-exported club still in the directory. Entry into
Twenty is at **Target**, the moment of export.

1. **Target** — exported to Twenty, not yet contacted
2. **Contacted** — outreach sent (exported to BetterComms / emailed), no reply
3. **Engaged** — replied / showed interest / active on site
4. **Trial** — demo or trial started
5. **Proposal** — quote / negotiation
6. **Won** — converted to paying customer
7. **Lost / Dormant** — declined or went cold

Opportunity custom fields: `modulesInScope` (MULTI_SELECT), `oppSource` (SELECT:
inbound_form, outbound_campaign, referral, directory), `lostReason` (SELECT).
Standard `amount`, `closeDate`, `company`, `pointOfContact` are reused.

### 3.5 Module keys (canonical, shared by all multi-selects)

| Key | Label |
|---|---|
| `select` | BetterSelect |
| `socials` | BetterSocials |
| `fees` | BetterFees |
| `comms` | BetterComms |
| `merch` | BetterMerch |
| `iq` | BetterIQ |
| `fantasy` | BetterFantasyCricket |

Core (BetterStats) is always on and is not a gateable module, so it is not a
multi-select option. `fees` + `comms` + `merch` are the BetterAdmin umbrella.

### 3.6 Touchpoint custom object

| Field | Type | Holds |
|---|---|---|
| `touchpointType` | SELECT | email_sent, email_delivered, email_opened, email_clicked, email_bounced, email_complaint, email_unsubscribe, email_reply, exported_to_comms, call, meeting, demo, trial_start, trial_end, onboarding_enquiry, web_milestone, note, system (named `touchpointType` because `type` is a reserved field name in Twenty) |
| `direction` | SELECT | inbound, outbound, system |
| `occurredAt` | DATE_TIME | when it happened |
| `subject` | TEXT | one-line summary |
| `summary` | TEXT | detail / body excerpt |
| `channel` | SELECT | email, phone, web, in_person, system |
| `externalRef` | TEXT | source id (e.g. `comms_campaigns.id`, `club_onboarding_requests.id`) |
| `company` | RELATION (many-to-one → Company) | the club |
| `person` | RELATION (many-to-one → Person) | the officer, when known |
| `email` | RELATION (many-to-one → Email) | the named bulk Email this touchpoint belongs to, when it came from a campaign |

### 3.7 Association custom object

A cricket association/competition. A club belongs to one or more (the
`marketing_clubs.associations` array), so Company ↔ Association is **many-to-many**
(Twenty supports this). Fed by the directory's `list_associations` registry (~677
associations) and each club's `associations` payload.

| Field | Type | Holds |
|---|---|---|
| `bcAssociationId` | TEXT (unique key) | association GUID from the registry |
| `name` | (Twenty name field) | association name |
| `shortCode` | TEXT | searchable short code (`set_association_shortcode`) |
| `state` | SELECT | state the association sits in |
| `clubCount` | NUMBER | linked clubs (from the registry) |
| `clubs` | RELATION (many-to-many → Company) | every club in the association |

This makes **"all clubs in an association"** a native related-records view on the
Association record (its "Member clubs" inverse of the `clubAssociation` junction),
and lets you filter People by their club's association.

### 3.8 Person ↔ Club junction (shared officers)

Twenty enforces **one Person per email address** (a hard 400 on a duplicate). Club
committees overlap, so the same person is often an officer at several clubs under one
email — they can only ever be **one** Person record. To still show that officer under
**every** club they serve, Company ↔ Person is modelled many-to-many via a
`personClub` junction (mirrors `clubAssociation`): one row per officer-at-a-club,
carrying that club's `clubRole` / `roleTitle` / `roleRank` / `outreachSelected`.

- The **Person** holds identity only (name, email, phone, country, subscribed,
  bounced) — always safe to refresh. Its native `company` + first role are set
  **once** (create-time), by the club that first introduced them, so a later export
  from a second club never steals the person onto itself.
- Each club's **`personClub`** row (inverse lists: a club's "Officer roles", a
  person's "Club roles") is what makes the shared officer appear under that club with
  the right role. Single-club officers get exactly one row (harmless). The row carries
  the **per-club** detail so club differences are preserved and the "Officer roles"
  view is self-contained: `clubRole` + `roleTitle` (the exact role at that club, e.g.
  "Junior Cricket Coordinator"), `email` and `phone` (that club's contact details,
  kept even when they differ from the shared Contact's single canonical ones).
- The **Contact** carries a `multiClub` flag + `clubCount`, set from the number of
  clubs it holds an Officer-role in, so a shared officer is visible at a glance in the
  Contacts list (the native single Company can't convey it). Updated only when the
  club set grows, so steady-state re-exports don't re-write it. **Per-club officer views must be built on "Officer roles", not the native
  Contacts list** — a Contact's native `company` is single-valued, so the native list
  can only ever show a shared officer under their one home club.
- **Matching a shared officer to their existing Contact** can't go through Twenty's
  email filter — `emails.primaryEmail[eq]:…` does **not** match existing records on
  this Twenty version (verified against the live instance: the export went straight to
  a `POST /people` that 400'd with "A duplicate entry was detected"). So we keep our
  **own** `email → Person id` index in `twenty_links` (`entity_type = 'person_email'`):
  - **Maintained incrementally** — every person upsert records its own email→id. This
    is the steady state and costs nothing extra per export (O(officers in the run)).
  - **Seeded once** by `_prewarm_person_emails` (paginates `GET /people` via
    `client.list_page`), guarded by a `_meta/person_email_backfilled` marker so it runs
    a single time to index contacts that pre-date the map, then **never on the hot path
    of routine exports**. `force=True` re-seeds after bulk manual edits in Twenty.
  - `_upsert` adopts the indexed `known_id` both directly and to recover from a
    duplicate-create 400, so a shared officer is never silently dropped.

### 3.9 Display labels and the junctions in the UI

The two standard objects are relabelled for the cricket domain — **Company → "Clubs",
Person → "Contacts"** — by a relabel pass in `bootstrap_twenty.py` (the API names stay
`company`/`person`, so the REST endpoints and all sync code are unchanged). The two
junction objects (**Memberships** = `clubAssociation`, **Officer roles** =
`personClub`) are plumbing, not browsing targets. Twenty has **no way to hide an
object from the sidebar yet** — neither a metadata flag nor a UI toggle (it's an open
feature request, twentyhq/twenty#10455), and `isActive: false` would disable the
object and its relations, so that's not an option either. They therefore stay visible
in the nav for now; their clear labels ("Memberships", "Officer roles") are the
mitigation. Their data shows where it matters regardless — inline on a Club
("Memberships", "Officer roles") and on a Contact ("Club roles").

**Build status:** objects, all custom fields, the pipeline stages, the relabels and
the relations above are created by `backend/app/scripts/bootstrap_twenty.py`
(idempotent; run with `TWENTY_API_URL` + `TWENTY_API_KEY` set). It has been run against
the live workspace, so the model exists. Re-run it after editing the spec to add new
fields, relabels or the `personClub` junction.

### 3.8 Email (Campaign) custom object — optional, recommended

People are bulk-emailed many times, and each send is identified by a BetterComms
**Email name**. Modelling the Email as its own object gives you a clean "who
received Email X" page and a per-club email history. One record per
`comms_campaigns` row.

| Field | Type | Holds |
|---|---|---|
| `bcCampaignId` | TEXT (unique key) | `comms_campaigns.id` |
| `name` | (Twenty name field) | the Email name / subject |
| `sentAt` | DATE_TIME | `comms_campaigns.sent_at` |
| `listName` | TEXT | the BetterComms List/segment it targeted |
| `recipients` / `delivered` / `bounced` / `complaints` | NUMBER | rollup from `comms_campaigns.stats` + `email_events` |

If you'd rather not add a fourth object for v1, drop the Email object and instead
carry a `campaignName` TEXT field on the Touchpoint. You still get filter/group-by
on the Email name; you just don't get a dedicated Email page. Recommend the object,
it's cheap and the "everyone who got Email X" view is exactly the ask.

### 3.9 Filter parity (Twenty must filter the way the directory does)

Every Club Directory filter maps to a Twenty field so the same slice is reproducible
in Twenty (and so a Twenty filter can drive a BetterComms List, §9.4):

| Directory filter | Twenty field to filter on |
|---|---|
| free-text `q` | Company name / Person name |
| `state` | `Company.state` |
| `country` | `Company.country` (AU-only today; the multi-country partition) |
| `association` / `associations` (multi) | `Company.associations` relation (or the Association record) |
| `status` | `Company.lifecycleStage` |
| `postcode_from`/`postcode_to` | `Company.postcode` (range) |
| `contact_filter = any_email` | `Person.emails` is not empty |
| `contact_filter = named_email` | `Person.namedEmail = true` |
| `contact_filter = pst` | `Person.namedEmail = true` AND `Person.clubRole` in (President, Secretary, Treasurer) |
| `exclude_carnival` / `exclude_school` / `exclude_junior` | `Company.clubKind` |
| `exclude_emailed` | `Company.lifecycleStage ≠ Contacted/...` or `Person.lastEmailedAt` empty |
| `exclude_exported` | `Person.outreachSelected` / a synced flag |
| `exclude_suppressed` | `Person.subscribed = true` |
| `visited` (has web activity) | `Company.lastSeenAt` not empty / `engagementScore > 0` |
| `trial_modules` / `requested_trial_modules` / `demo_status` | `Company.trialModules` / `interestedModules` / `subscriptionStatus` |

### 3.10 Standard saved views to ship

- **People by Club** — already native: open a Company to see its officers. Plus a
  global People view grouped by Company.
- **Clubs by Association** — native on the Association record ("Member clubs"); the
  primary association of a club is its `isPrimary` membership.
- **Pipeline** — Opportunities grouped by stage (kanban).
- **Hot prospects** — People/Companies filtered by `engagementTier = Hot` and not
  yet Customer.
- **Emailable officers** — People where `subscribed = true` AND `namedEmail = true`,
  grouped by Company (the starting point for building a List, §12).

## 4. Can we automate building the model? Yes, almost entirely.

Twenty has two API layers, both REST and GraphQL, on the self-hosted domain:

- **Metadata API** — `POST /rest/metadata/objects`, `POST /rest/metadata/fields`,
  `PATCH /rest/metadata/fields/{id}`. Creates/edits objects, fields, relations,
  and SELECT options. This builds the Touchpoint object, every custom field above,
  and rewrites the Opportunity stage options. **Fully scriptable.**
- **Core API** — `/rest/*` and `/graphql`. Record CRUD. Custom objects get their
  own endpoints automatically the moment metadata creates them (e.g.
  `/rest/touchpoints`). GraphQL does batch upsert, 60 records/batch.
- **Auth** — `Authorization: Bearer <API_KEY>`. Rate limit 100 req/min.

**The only manual prerequisites** (each ~30 seconds in Settings → API & Webhooks):
1. Create an **API key** (you can't mint a key via the API without a key). One key
   with metadata-write rights covers bootstrap and sync.
2. Create the **webhook** pointing at the BetterCricket receiver (can also be done
   via the API, but the UI is simpler). Copy its signing secret.

Everything else (objects, fields, pipeline stages, all record sync, the backfill)
is code. A single idempotent `bootstrap_twenty.py` run builds the whole model.

## 5. Engagement rollup and scoring (computed in BetterCricket) — BUILT

The rollup is computed in `services/twenty_sync.py::_engagement(session, club, org)`
and pushed onto the Company. No new table: it reads the raw signals directly at push
time, so the score always reflects live activity and there is nothing to keep in sync.

**Two signal sources, both attributed to the club:**
- **Web** — `usage_events` by `utm_id = marketing_clubs.utm_code` (prospect) OR
  `org_id = marketing_clubs.existing_org_id` (customer/trial). Gives `lastSeenAt` and
  `sessions30d` (distinct visitors, 30 days). *Caveat:* a web visit only attributes
  to the club if it carried that club's UTM code (or is org-scoped) — an untagged
  organic visit isn't linkable to a specific club.
- **Email** — `email_events` opens/clicks for the club's contact emails (or org for a
  customer). Gives `lastEmailAt` and `emailEngaged30d`. Opens/clicks are engagement;
  sends are our action, not theirs, so they don't score. This is what makes an
  emailed-and-engaged prospect register (the old model read web only and missed it).

**Lifecycle-aware scoring** (the score means different things by stage):
- **Prospect (lead heat)** = recency of last touch (web or email; 40/28/14/4 by age) +
  frequency (`sessions30d × 6 + emailEngaged30d × 4`, capped 40) + intent (+12
  `requested_trial_modules`, +8 `demo_status = in_trial`), clamped 100. Tier Cold < 34
  ≤ Warm < 67 ≤ Hot.
- **Customer (health + expansion)** = base 45 (a paying account is engaged) + half the
  recency + half the frequency (product use) + 15 if there's an upsell. Floored at
  **Warm** (a customer is never Cold), Hot when expanding or score ≥ 67. This is the
  fix for "a customer trialing more modules sat at Cold/0".

**Opportunity + sales-cycle signals:**
- `upsellModules` = modules the club wants (`requested_trial_modules` ∪
  `trial_modules`) minus what it pays for (`module_overrides`). A prospect's interest,
  or a customer's expansion/trialing-extra.
- `inSalesCycle` = a customer with an upsell, or a prospect showing intent or any
  engagement — i.e. a deal to work, not just a name on a list.

**Fields pushed:** `engagementScore`, `engagementTier`, `sessions30d`,
`emailEngaged30d`, `lastSeenAt`, `lastEmailAt`, `upsellModules`, `inSalesCycle`.
Module *holdings* (separate from the score) feed `paidModules` ←
`organisations.module_overrides`, `trialModules` ← `marketing_clubs.trial_modules`,
`interestedModules` ← `marketing_clubs.requested_trial_modules`.

**Refresh paths:**
- On every `export_to_twenty` run the engagement fields are merged into the Company
  values, so a re-export re-scores.
- `refresh_engagement(limit=None)` re-scores **only clubs already in the CRM** (a row
  in `twenty_links`), loading each linked org so customers are scored on health +
  expansion, and PATCHes each Company without pulling new clubs in. Wired to a daily
  scheduler job (06:00, gated on `twenty_configured`) and an on-demand
  `POST /club-admin/marketing/refresh-twenty-engagement` ("Refresh Twenty scores").

The weights are a tuning knob, not load-bearing. Twenty Workflows can react to the
output (e.g. `inSalesCycle = true` and tier Hot → auto-create a "call this club"
Task).

## 6. Source entities that feed Twenty

| BetterCricket table | Feeds Twenty | Key columns used |
|---|---|---|
| `marketing_clubs` | Company (prospect) | grassroots_guid, name, status, association_name, state, country, contact_email/phone, website_url, utm_code, trial_modules, requested_trial_modules, demo_status, emailed_at/via, existing_org_id |
| `organisations` | Company (customer) | id, name, slug, subscription_status, module_overrides, renewal_date, billing_cycle, contact_email |
| `marketing_club_contacts` | Person | full_name, role, role_rank, email, mobile, subscribed, bounced, outreach_selected, source |
| `list_associations` registry + `marketing_clubs.associations` | Association object + Company↔Association relation | association id, name, short_code, state, club_count |
| `club_onboarding_requests` | Touchpoint (onboarding_enquiry) + Company hint | name, club, email, interests, status, visitor_id, created_at |
| `usage_events` | Company engagement rollup (NOT raw) + Touchpoint (web_milestone) | org_id, visitor_id, utm_id, traffic_source, path, created_at |
| `comms_campaigns` + `comms_recipients` | Touchpoint (email_sent) at send time | subject, sent_at, status, per-recipient status/email, provider_message_id |
| `email_events` (append-only SES log) | Touchpoint (delivered/opened/clicked/bounced/complaint) + Person flag updates | event_type, event_subtype, reason, ses_message_id, organisation_id, campaign_id, contact_id, email |
| `email_suppression` (global suppression list) | Person `subscribed=false` across every club that holds the email | email, reason, source |
| `comms_contacts` | Person suppression state | subscribed, bounced, complained, unsubscribed_at |

## 7. API functions to build (BetterCricket side)

New `app/services/twenty_client.py` (httpx, Bearer key, base
`https://twenty.betterat.cricket`). New `app/services/twenty_sync.py` (mapping +
upsert logic). Config in settings/.env: `TWENTY_API_URL`, `TWENTY_API_KEY`,
`TWENTY_WEBHOOK_SECRET`.

**Metadata client (one-time bootstrap, `scripts/bootstrap_twenty.py`):**
- `list_objects()` → `GET /rest/metadata/objects` (idempotency: skip if exists)
- `create_object(spec)` → `POST /rest/metadata/objects` (Touchpoint)
- `create_field(spec)` → `POST /rest/metadata/fields` (all custom fields)
- `update_field_options(id, options)` → `PATCH /rest/metadata/fields/{id}`
  (rewrite Opportunity stage options)

**Core client (ongoing sync):**
- `export_to_twenty(filters, contact_scope)` → the membership action (§8.1):
  filter the directory, upsert the matched subset, stamp `twenty_links`
- `find_company_by_key(bcClubId)` → `GET /rest/companies?filter=bcClubId[eq]:…`
- `upsert_association`, `upsert_company`, `upsert_person`, `upsert_opportunity`,
  `create_touchpoint` (create or PATCH by external key)
- batch variants via GraphQL `createCompanies` / `createPeople` (60/batch) for the
  first sizeable export, respecting 100 req/min

**Webhook receiver (Twenty → BetterCricket):**
- `POST /public/twenty/webhook` (unauthenticated route, protected by HMAC):
  verify `X-Twenty-Webhook-Signature` (HMAC-SHA256 of timestamp + body using
  `TWENTY_WEBHOOK_SECRET`), then dispatch on `event`
  (`opportunity.updated`, `company.updated`, `note.created`, `task.created`).

**Local mapping table** `twenty_links(entity_type, bc_id, twenty_id,
content_hash, last_synced_at)` — maps BetterCricket rows to Twenty record ids,
makes upserts idempotent, prevents echo loops (via `content_hash`), and **is the
subset membership ledger**: a row exists only for clubs/people exported to Twenty,
so every incremental push scopes itself to this table.

## 8. Sync workflows

### 8.1 Export filtered directory to Twenty (how a club enters the subset)

This is the membership action, modelled directly on `export_to_comms`. A new
`export_to_twenty(filters, contact_scope)` in `services/twenty_sync.py`:

1. runs the **same `club_filters`** the directory page shows (state, association,
   country, status, postcode, and the exclude flags for junior / carnival / school
   / suppressed), so the operator targets exactly the slice they want,
2. for each matched club, **upserts** its Association(s) → Company → officers
   (People) → a Prospect-stage Opportunity, matching on the external keys
   (`bcClubId` / `bcContactId` / `bcAssociationId`); creates what's missing, fills
   gaps on what exists, never duplicates,
3. records each mapping in `twenty_links`, which **is** the subset membership
   ledger, and stamps a directory-side badge (a `twenty_synced_at` on
   `marketing_clubs` / `marketing_club_contacts`, mirroring `exported_at`) so the
   directory shows what's already in Twenty and won't offer it again.

`contact_scope` decides which officers come across. Default: **all named officers**
of an included club (you want the full contact set to manage a sales cycle), with
the option to apply the `named_email` / `pst` contact filters when you only want
the key officers. Club-level exclude filters always gate which **clubs** enter;
officer filters only narrow **who** within an included club.

Re-running export with a wider filter grows the subset. Nothing is auto-onboarded.

### 8.2 BetterCricket → Twenty (incremental push, subset only)

Once a club is in the subset, keep it fresh. **Every push below walks the
`twenty_links` membership, never the whole directory.**

- **Nightly reconcile** (fits the existing scheduler that runs sync and the Square
  import): for each linked club, recompute the engagement rollup, upsert
  Company/Person/Opportunity, and create new Touchpoints since last run.
- **Event-driven near-real-time** for high-signal changes on a linked club: new
  onboarding enquiry, `subscription_status` change, trial start/stop, campaign
  sent. Enqueue an immediate single-record push so the sales view is fresh.

A change on a club that is **not** in the subset is ignored (it isn't a target
yet). Per-club push order (FK-safe): Company → People → Opportunity → Touchpoints.

### 8.3 Twenty → BetterCricket (webhook write-back)

When a salesperson edits in Twenty:
- `opportunity.updated` (stage change) → update `marketing_clubs.status` /
  `organisations.subscription_status` / `demo_status`, and trigger BetterCricket
  side effects (e.g. stage → Trial provisions trial modules; stage → Won flips the
  org live).
- `company.updated` (lifecycleStage, owner) → mirror onto the club row.
- `note.created` / `task.created` → store as correspondence against the club so
  BetterCricket's own super-admin onboarding screens stay in sync.

**Loop prevention:** every push stores a `content_hash`. A webhook whose payload
hash matches the last value we pushed is a no-op (it's our own echo). Writes from
Twenty are tagged so the next BetterCricket→Twenty push doesn't clobber a
human edit.

## 9. BetterComms / SES email-activity bridge

Club Directory and BetterComms are one pipeline, and every email action on the SES
side must reach Twenty. The flow:

```
Club Directory (marketing_clubs + marketing_club_contacts)
  │  Super User filters a list, ticks officers (outreach_selected)
  ▼  club_directory.export_to_comms()
comms_contacts  (per-club audience; Audience / List / Segment in BetterComms)
  │  campaign send
  ▼  email_service → AWS SES API  (configuration set → SNS topic)
SES events (delivery / bounce / complaint / reject / open / click)
  │  SNS → POST /public/ses/events  (signature-verified)
  ▼  ses_events.ingest_ses_event() → email_events (append-only) + suppression + contact flags
  ▼  NEW: twenty_sync push  → Touchpoints + Person flag updates in Twenty
```

### 9.1 Export to BetterComms is a pipeline event

When a Super User exports a filtered directory list
(`club_directory.export_to_comms`, which sets
`marketing_club_contacts.exported_at` and materialises `comms_contacts`), that is
the moment a club moves from Suspect into the outreach machine. The export hook
pushes to Twenty:
- advance the club's Opportunity stage to **Contacted** (if still Suspect),
- create one `exported_to_comms` Touchpoint on the Company recording which list /
  segment and how many officers were included.

### 9.2 SES events to Twenty (the write-back the requirement calls for)

Hook the existing SES ingest path (`ses_events.ingest_ses_event` / `_record`,
which already resolves org / campaign / contact from
`comms_recipients.provider_message_id`). After it writes the `email_events` row and
updates suppression / contact flags, it pushes to Twenty. Two volume tiers, so the
CRM mirrors activity without drowning in it:

**Per-send correspondence (one Touchpoint per recipient).** At campaign send time,
create one `email_sent` Touchpoint per `comms_recipient`, linked to the Person and
Company, carrying the campaign subject and `provider_message_id` in `externalRef`.
A 5,000-recipient campaign is ~84 batched requests, well under the 100/min limit.

**Lifecycle updates (update the send Touchpoint, do not multiply records).**
`delivery`, `open`, and `click` events update the existing `email_sent` Touchpoint
(status field + `lastEngagementAt`) and bump the Company engagement rollup. They do
**not** create a new record each. Opens and clicks are noisy; at 20k contacts a new
record per open would be the same scaling mistake as streaming raw page views.

**Suppression actions (low-volume, high-signal: always mirror fully).** A permanent
`bounce`, a `complaint`, or an `unsubscribe` is a sales-critical "do not contact"
signal. For each, the bridge:
- updates the matching Twenty **Person**: `subscribed=false` (and `bounced=true` or
  a `complaint` flag). Suppression in BetterCricket is **global** (the
  `email_suppression` list flags the address across every club), so the Twenty
  write matches **every** Person with that email, not just one Company's contact.
- creates a Touchpoint (`email_bounced` / `email_complaint` / `email_unsubscribe`)
  so the timeline shows why the contact went dark.

This keeps Twenty's view of who is emailable identical to BetterCricket's, so a
salesperson never emails a suppressed or complained address, and the engagement
score reflects real deliverability.

### 9.4 Filter People in Twenty, build a BetterComms List (reverse action)

The high-value workflow: a user filters People in Twenty on any attribute, action,
or behaviour (engagement tier, association, role, modules of interest, last
emailed, never opened, and so on), then hands that set to BetterComms as a named
**List**, and sends a bulk **Email** to it. The send then flows straight back into
Twenty through §9.1–9.3.

The filter is always authored in Twenty. There are two ways to hand the set over;
both call the **same** BetterCricket endpoint and produce the same named List, so
build the endpoint first and the trigger is just UX.

**New endpoint** `POST /club-admin/comms/list-from-twenty` (super-admin, or a
HMAC-signed public variant for the workflow path). Body: `{ listName,
people: [{ bcContactId, email, bcClubId }] }`. It:
1. resolves each `bcContactId` → `marketing_club_contacts`, and reuses the
   `export_to_comms` rules (skip suppressed and existing customers, link
   `marketing_club_id`, tag with club + association names) to materialise/refresh
   the `comms_contacts` rows under the outreach org,
2. creates (or replaces) a named BetterComms **List** (`comms_segments` static
   membership, or a saved list) called `listName` containing exactly that set,
3. returns the list id and final size (after suppression filtering), which the
   workflow surfaces back to the user.

A bulk Email composed against that List sends via SES and reports back per §9.2.

**Trigger A — push from Twenty (the UX the requirement describes).** A manual
Twenty **Workflow** (HTTP Request / serverless-function action) over the
selected/filtered People POSTs them to the endpoint with a `listName` the user
types. Idempotent: each call upserts into the named list, so a fan-out over records
still converges on one List. (Confirm the exact trigger surface, run-on-selection
vs run-on-view, against your installed Twenty version; the workflow UX has moved
across releases.)

**Trigger B — pull from BetterComms (the reliable fallback).** BetterComms gets a
"Build List from a Twenty view" action: the user picks a saved Twenty **View** (or
passes filter criteria), BetterCricket calls Twenty's Core API
`GET /rest/people?filter=…` to fetch the matches, then runs the same materialise +
name-the-List logic. One request, no per-record fan-out, no workflow plumbing.

Recommend shipping the endpoint + Trigger B first (works today on any Twenty
version), then adding Trigger A once the workflow action is confirmed.

### 9.5 Manual email via Gmail

Officers are also emailed by hand from Gmail, outside the bulk channel. Twenty has
**native connected-account email sync**: a user connects their Gmail, and messages
to/from any known Person auto-log onto that Person's timeline. So manual outreach is
captured with no build, as long as the recipient exists as a Person (which the
backfill guarantees). Keep the two channels distinct: bulk sends come in as
Touchpoints we push (SES is the source of truth for deliverability/suppression);
manual Gmail threads come in via Twenty's own sync. They sit side by side on the
timeline and don't conflict, because manual Gmail never touches the SES suppression
list.

### 9.6 Direction and ownership

Email eligibility stays **owned by BetterCricket** (SES + the suppression list are
the source of truth, legally too, under the Spam Act). Twenty only ever *reflects*
it; the Twenty `subscribed` flag is read-only intelligence for the sales team, not
a control. Nobody re-subscribes a contact by editing Twenty. That avoids a
two-master conflict on the one field where getting it wrong is a compliance problem.

### 9.7 Contact source — the inbound-engagement channel

`Person.contactSource` records **how a person has actually made contact**, set
automatically by the channel of a real contact event, never by the export. Options:
**No Contact Source** (default), **Website**, **Manual Email**, **BetterComms
Email**, **Other**. Rule: **most-recent-channel-wins** — each event just writes its
own channel (last write), and the export never touches the field after creation, so
event-driven updates and operator edits both survive a re-sync.

| Channel | Trigger | Status |
|---|---|---|
| **Website** | a Contact Us enquiry (`POST /public/contact`) whose email matches a Person → set `WEBSITE` (background task, best-effort) | **built** |
| **BetterComms Email** | an SES **open or click** (`ses_events`): resolve the recipient → set `BETTERCOMMS_EMAIL` + `lastCampaign` (the campaign's `utm_campaign`, else subject) | **built** (needs SES open/click events enabled on the config set to fire) |
| **Manual Email** | an inbound Gmail message logged on a Person | follow-up — needs a Gmail account connected (per-user in Twenty) + a workflow/poll; self-hosted Gmail sync needs reliability testing first |
| **Other** | manual | n/a |

All updates go through `twenty_sync.update_person_by_email(email, fields)` — finds
the Person by their unique email and patches the fields; a person not in the CRM is
a silent no-op, and a CRM error never affects the triggering public/webhook flow.
The same helper carries the **suppression mirror** (permanent bounce / complaint →
`subscribed=false`, `bounced=true`), so email activity and contact source land
through one path. Scaling note: contact-source is written on every qualifying event
(e.g. each open); a per-person/per-campaign dedupe can come later if open volume
makes the per-event Twenty write costly.

## 10. Pre-flight hardening (do before any sync)

The compose you stood up needs three fixes first:

1. **DB password mismatch.** `twenty-server` and `twenty-db` use
   `CHANGE_THIS_TWENTY_DB_PASSWORD`; `twenty-worker` uses
   `ClNsbOgSr6w3iO6e3sM0aNQjpTaAlwT`. The worker can't reach the DB until all three
   match. Pick one real secret and use it in `twenty-db` (`POSTGRES_PASSWORD`) and
   the `PG_DATABASE_URL` of both `twenty-server` and `twenty-worker`.
2. **Real secrets.** `ENCRYPTION_KEY` (32-byte base64), `APP_SECRET`, and
   `FALLBACK_ENCRYPTION_KEY` are placeholders/empty. Generate real values
   (`openssl rand -base64 32`). An empty `APP_SECRET` breaks sessions and token
   signing.
3. **Network + reachability.** Twenty is on `docker-shared-net` (good, so
   `betterstats-backend` can reach `http://twenty-server:3000` internally for
   pushes, and Twenty can reach the backend for webhooks). Confirm
   `twenty.betterat.cricket` is routed through nginx-proxy-manager and that the
   webhook target `https://betterat.cricket/api/public/twenty/webhook` resolves.

Keep Twenty on its **own** `twenty-db` volume, never the BetterStats pgdata. Back
up `/srv/docker/twenty/db` before the first migration run. None of this touches the
`bltbox_docker_app` betterstats stack.

## 11. Phased build plan

| Phase | Deliverable | Depends on |
|---|---|---|
| **0. Hardening** | Fix compose secrets (§10), create API key + webhook in Settings, set `TWENTY_*` env in backend | — |
| **1. Model bootstrap** | `scripts/bootstrap_twenty.py`: Touchpoint + Association (+ optional Email) objects, all custom fields, the Company↔Association and Company↔Person relations, pipeline stages (idempotent, re-runnable) | Phase 0 |
| **2. Export to subset** | `twenty_client` + `export_to_twenty(filters)` (mirrors `export_to_comms`): filter the directory, upsert Associations + targeted Companies + their officers, build `twenty_links`. No mass auto-onboard | Phase 1 |
| **3. Incremental push (subset only)** ✅ | `_engagement` rollup merged into the export + `refresh_engagement` (daily job + on-demand endpoint) re-scores `twenty_links` clubs; subscription/modules/renewal/ARR already pushed in Phase 2 (§5) | Phase 2 |
| **4. Comms / SES bridge** ✅ | `ses_events.ingest_ses_event` mirrors opens/clicks (→ BetterComms Email contact source + last campaign) and permanent bounce/complaint (→ Person emailable flags); Contact Us reply → Website source (§9) | Phase 2 |
| **5. List-from-Twenty** | `POST /club-admin/comms/list-from-twenty` + the BetterComms "Build List from a Twenty view" pull action (Trigger B), then the Twenty workflow push (Trigger A) (§9.4) | Phase 4 |
| **6. Webhook write-back** | `POST /public/twenty/webhook` with HMAC verify + pipeline side effects | Phase 2 |
| **7. Activate intelligence** | Twenty Workflows (score-driven tasks/stage moves) + Dashboards (pipeline, engagement, module interest, email deliverability) | Phases 3–6 |

## 12. Open decisions

- **Score weights** — recency vs frequency vs depth vs intent. Start simple, tune
  against real conversions.
- **Person volume** — push all ~20,000 contacts, or only the top-ranked officer(s)
  per club? Twenty self-hosted has no record cap, so all 20,000 is fine; the
  question is signal vs noise in the sales view. Recommend: push all, but default
  list views filter to `roleRank ≤ 5`.
- **Customer success as a second pipeline** — keep post-sale on Company fields
  (recommended for v1) or add a second Opportunity record type for renewals
  (revisit once there are paying renewals to manage).
- **Email as an object vs a field** — model the named bulk Email as its own object
  (recommended, gives the "everyone who got Email X" view) or just a `campaignName`
  field on the Touchpoint (lighter, no Email page). §3.8.
- **List-build trigger** — pull from BetterComms first (Trigger B, works on any
  Twenty version), then add the in-Twenty workflow button (Trigger A) once the
  workflow HTTP action is confirmed on the installed version. §9.4.
- **Officer export scope** — default to all named officers of an exported club, or
  only the key officers (`named_email` / `pst`)? Recommend all, so the sales view
  is complete; narrow only when deliberately seeding a thin outreach set. §8.1.
- **Multi-country expansion** — `country` and `dataSource` are first-class on
  Company now so the subset partitions cleanly when non-AU sources (e.g. UK
  Play-Cricket) come online. No model change needed then, just new directory
  sources feeding the same export.
