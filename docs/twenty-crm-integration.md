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

## 13. July 2026 — lifecycle/engagement rule correction + presync Task queue

Feedback pass that corrected several rules baked into the Phase 2–6 code and
closed two real gaps (`services/twenty_sync.py`, `twenty_leads_tasks.py`,
`twenty_inbound.py`, `club_directory.py`, `public_comms.py`, `ses_events.py`,
`routers/comms.py`; one-off backfill in `scripts/reconcile_twenty.py`).

- **"Synced" is not "Customer".** `_lifecycle`/`_engagement` previously treated
  any club with an `organisations` row (`existing_org_id`) as CUSTOMER and
  scored it on account-health, even with zero paid modules — a club synced
  ahead of a sale (or mid-trial) read as a paying customer from day one. Fixed:
  CUSTOMER now requires `_module_split(org)` to actually return a non-empty
  `paid` list (or `demo_status == 'customer'`). A synced-but-not-paying club is
  PROSPECT, scored on prospect lead-heat, and raises a Lead (§5's "synced"
  trigger in `_lead_signal`).
- **Engagement tiers**: Cold < 30, Warm 30–45, Hot > 45 (was Cold < 34 / Hot ≥
  67) on both the prospect and customer scoring branches.
- **All-officers-unsubscribed → Suppressed.** New
  `_all_contacts_unsubscribed` + `enforce_club_suppression` /
  `handle_contact_opt_out`: when every named-email officer of a club has opted
  out, the Company flips to SUPPRESSED (never overriding an actual paying
  customer), its Lead is discarded, and any still-open Opportunity is marked
  Lost / Dormant. Runs inline on every `refresh_engagement` pass (self-healing)
  and in real time from the one-click unsubscribe link (`public_comms.py`,
  previously didn't push to Twenty at all) and SES bounce/complaint
  (`ses_events.py`).
- **Every BetterComms send now upserts Twenty**, closing the gap where a club
  had to be manually exported before it could appear in the CRM.
  `twenty_sync.push_club_and_contacts(club_id, contact_ids)` upserts one
  Company + the given officers on demand; `routers/comms.py::_run_send` calls
  it for every marketing-outreach recipient right after a campaign send,
  auto-enrolling a first-ever-emailed club at its computed lifecycle stage
  (Target, by default).
- **Trial Modules is now a real trigger, both directions.** `twenty_inbound.py`
  reacted only to `interestedModules`; it now also reacts to `trialModules`,
  and a super admin adding a module to a `marketing_clubs.trial_modules` row in
  the Club Directory (`club_directory.set_sales_state`) queues the same
  request. Shared `twenty_inbound.request_trial_modules`: a synced club gets a
  real `ModuleActionRequest` (as before); an un-synced club (no `organisations`
  row) gets a Twenty **Task** asking for it to be synced first
  (`_queue_presync_task`, deduped forever on `presync:{club_guid}:{module}` via
  `twenty_links`) — there's no separate BetterCricket-side queue table for
  this, the Task itself is the queued request.
- **Task creation deduped through one helper**: `twenty_sync._raise_task`
  (twenty_links-keyed create-or-skip) is now shared by the daily
  Lead/Task scan (`twenty_leads_tasks._create_task`) and any event-driven Task
  raise, instead of two separate implementations.
- **One-time reconciliation**: `python -m app.scripts.reconcile_twenty`
  enrols every club the corrected rules say already belongs in Twenty (ever
  emailed, synced, trialing, or a demo status set) but isn't linked yet, then
  runs `refresh_engagement` + `refresh_leads_and_tasks` so every already-linked
  club's lifecycle/tier/suppression/Lead state is brought current under the
  corrected rules. Idempotent — safe to re-run.

## 14. July 2026 — website enquiries, sync/trial hooks, and page-view volume

A second feedback pass, wiring three more signal sources into the same
`_engagement` rollup (`services/twenty_sync.py`, `twenty_leads_tasks.py`,
`routers/organisations.py`, `routers/club_admin.py`, `services/twenty_client.py`;
migration 133).

- **Website "onboard my club" enquiries now feed the score.** Both the
  `ClubCTABar` → `QuickEnquiryModal` ("Get your club on BetterCricket") and the
  full `/contact` page ("Request access" → "Send message") post to the SAME
  `POST /public/contact` → `club_onboarding_requests` row — that table carries no
  FK back to `marketing_clubs`, so `twenty_sync._onboarding_signal` attributes a
  submission to a club at read time: match the submitter's email against a known
  officer (`marketing_club_contacts`), else the anonymous visitor's UTM-tagged
  `usage_events` history, else an exact club-name match. A hit is the single
  strongest prospect score bump (+20, beats the admin-set requested-trial flag),
  qualifies as a Lead sourced `CONTACT_US` (an option that already existed in the
  bootstrap but nothing populated it before), and gates Step 1 of the reconcile
  script (email-match only there, for enrolment precision).
- **A real per-module trial now always registers.** `_engagement` computed
  `_module_split(org)`'s real `trial` list (actual `org_module_subscriptions`
  rows a super admin started) and then discarded it, scoring only the marketing
  directory's separate, manually-set `trial_modules` aspirational field. Fixed:
  the real trial list is folded into `wanted`/`upsellModules` too, so starting a
  trial via `club_admin.py::start_module_trial` registers even if nobody
  separately ticks it in the Club Directory.
- **Syncing a club now pushes to Twenty immediately.** `existing_org_id` used to
  only get linked back to the Marketing Directory the next time the directory
  *crawler* revisited that club (`club_directory._link_existing_org`) — which
  could be days after the actual onboard. `organisations.py::onboard_organisation`
  now does the same match (PlayHQ id, then name) right when the org is created,
  and fires `push_org_company` immediately if it finds one.
- **Starting a trial now pushes to Twenty immediately.** `start_module_trial`
  (the direct super-admin route) never pushed to Twenty at all — only its
  sibling `approve_module_request` (approving a *queued* trial request) did. Both
  now call the same `_push_club_to_twenty` fire-and-forget helper.
- **Page-view/API volume, not just distinct visitors.** The `usage_events` web
  query only ever counted `COUNT(DISTINCT visitor_id)` — one visitor browsing 50
  pages scored identically to one bouncing after a single view. Added a capped
  `COUNT(*)` volume term (`min(events_30d, 20)`) alongside it. Added migration
  **133**: `usage_events(org_id, created_at) WHERE org_id IS NOT NULL` — the
  customer/trial branch of this query (`org_id::text = …`) had no index at all.
- **Internal-only signal fields never reach Twenty's API.** `_engagement` needed
  to hand a boolean (`_onboardingRequested`) to `twenty_leads_tasks._lead_signal`
  without it being a real Twenty Company field. Rather than bootstrap a throwaway
  field, `twenty_client.py` gained a `_public()` filter (drop any leading-
  underscore key before a create/update body goes out) — a reusable convention
  for any future signal that needs to ride along the same dict without touching
  Twenty's schema.

## 15. July 2026 — Lead mirrors Company's engagementScore + lifecycleStage

A Lead used to carry only `engagementTier` (its own SELECT, refreshed daily). Two
more fields now mirror straight off the Company, kept in lockstep from every angle:

- **`Lead.engagementScore`** (NUMBER) and **`Lead.lifecycleStage`** (SELECT, same
  options as `Company.lifecycleStage`) added to `bootstrap_twenty.py`'s Lead
  fields.
- **`twenty_sync._LEAD_MIRROR_FIELDS`** (`{"engagementScore": "engagementScore",
  "lifecycleStage": "lifecycleStage"}`) drives `_sync_lead_from_company`, called
  right after every Company push that can change either — `export_to_twenty`,
  `refresh_engagement`, `push_club_and_contacts` — so a club's Lead updates in the
  same request as its Company, not on the next daily Lead scan. Adding a third
  mirrored field later is a one-line addition to the map.
- **`refresh_engagement` now recomputes the FULL lifecycle stage every run**, not
  only the all-officers-unsubscribed override it used to set. Previously a club
  that started paying, or was emailed for the first time, wouldn't move stage
  again until the next `export_to_twenty`/`push_club_and_contacts` run touched it;
  now the nightly refresh catches it too.
- `twenty_leads_tasks._seed_and_refresh_leads` computes the same `_lifecycle(club,
  is_paying, all_unsub)` for the daily Lead seed/refresh pass, so a brand-new Lead
  is created with the right stage immediately, not just patched onto it later.
- An **"Engagement cycle" (mirroring `Company.inSalesCycle`) was added then
  removed same day** — `lifecycleStage` was judged the more useful mirror. If
  it's already been bootstrapped into a live workspace, delete the field manually
  in Twenty (Settings → Data model → Lead) — `bootstrap_twenty.py` only ever
  creates fields, it has no delete path.
- **`_upsert` no longer loses a whole record over one bad Company field.** The
  same 16 clubs kept failing `POST /rest/companies` with `INVALID_URL` even after
  `link()` gained its own validation — the exact bad shape was never confirmed
  (no direct DB access to the live data). Rather than keep guessing, `_upsert`
  now catches that error generically on both create and update (detects any
  dict value carrying `primaryLinkUrl`, not just `publicProfileUrl` by name),
  drops the offending field(s), retries once, and logs the exact rejected value
  — so the record is created either way, and the log tells us what to fix in
  `link()` next.

## 16. July 2026 — `_engagement` was missing `utm_source`-tagged traffic entirely

Found via a real case: Tasmania Police CC showed 54 visitors / 71 views on the
Club Directory's own "site visits" panel (real product exploration — `/applecross`,
`/modules/betterstats`, `/modules/betteradmin`, `/contact`…), yet
`twenty_sync._engagement` computed `sessions30d=0` and scored 0/Cold.

**Root cause**: `_engagement`'s web-activity query only ever matched
`usage_events.utm_id = club.utm_code`. `club_directory.py`'s own
`_RESOLVED_VISITS` (which powers that Directory panel, and got it right) already
matches `utm_code` against **either** `utm_id` **or** `utm_source` — because
`comms.py`'s `_apply_utm` had a bug: it appended `utm_id` to a campaign link
UNLESS the link already contained `utm_source=` — but `utm_source` is also a
documented merge var (`{{utm_source}}` = the club's code, meant for an
operator-authored link like `?utm_source={{utm_code}}&utm_medium=…`). A campaign
using that pattern got a real, correctly-bucketed `utm_source` (hence showing up
fine in Sources/Directory panels, both of which already check `utm_source`), but
never got `utm_id` — the one column `_engagement` checked.

**Fixed both ends**:
- `_engagement`'s web query and `_onboarding_signal`'s visitor-to-utm subquery
  now match `utm_id = :utm OR utm_source = :utm`, same as `_RESOLVED_VISITS`,
  so already-sent campaigns' traffic (which can't be retagged after the fact)
  is picked up retroactively.
- `comms.py::_apply_utm` no longer treats "already has `utm_source=`" as a
  reason to skip `utm_id` — the two are independent (campaign attribution vs.
  per-club attribution) and a link can carry both. It now decides per-param:
  skip the campaign's own `utm_source`/`medium`/`campaign` only if `utm_source=`
  is already present, and skip `utm_id` only if `utm_id=` is already present —
  so a hand-templated `{{utm_source}}` link still gets `utm_id` appended, and
  future campaigns can't silently lose per-club attribution this way again.

Not fixed (deliberately out of scope for this pass): `_engagement` still doesn't
use the fuller `_RESOLVED_VISITS` resolution (the `marketing_utm_aliases` table
for renamed UTM codes, or the path-embedded-code / org-slug fallbacks) — only
the `utm_id`/`utm_source` parity fix. Worth revisiting if a club's traffic is
still invisible to `_engagement` after this fix and `docker exec ... python -m
app.scripts.diagnose_club_lead "<name>"` confirms it's still zero.

## 17. July 2026 — `_engagement` was missing path-only (no-UTM) traffic

The gap flagged as out-of-scope in §16 turned out to matter in practice: West
Coburg St Andrews CC and Geelong Over 50s CC both showed real Directory "site
visits" (confirmed via the Directory panel) that `diagnose_club_lead.py` still
scored as `sessions30d=0`. Both clubs' traffic landed on `/{club-slug}/...`
with **no UTM query param at all** — organic hits, a shared link, or (for West
Coburg, already a customer) a visitor going straight to the org's own site —
so neither the `utm_id`/`utm_source` columns nor `org_id` had anything to
match on.

**Fixed**: `_engagement`'s web query and `_onboarding_signal`'s visitor lookup
now also match via `_PATH_CODE` (the same first-path-segment extraction
`_RESOLVED_VISITS` uses) against the club's `utm_code`, against the linked
org's `slug` (for a customer whose own site path need not equal its stored
UTM code — confirmed true for both clubs above), and via `marketing_utm_aliases`
keyed to this specific club. This is the `_RESOLVED_VISITS` parity `§16` left
undone — now closed.

Also fixed the same session: **trial requests now raise a Twenty Task
immediately**, not on the next daily 07:00 sweep. Two gaps: (a) ticking
"Requested Trial" (as opposed to "Trial Modules") in the Club Directory queued
nothing at all — `set_sales_state` only reacted to Trial Modules; both now
trigger the same follow-up. (b) even a queued `ModuleActionRequest` for an
already-synced club waited for `_mirror_requests_to_tasks`'s daily sweep to
become a visible Task — `twenty_inbound.request_trial_modules` now raises the
Task inline (same `req:{id}` ext_ref the daily sweep already uses, so it just
no-ops on it next run rather than double-raising).

## 18. July 2026 — engagement score differentiation: per-event decayed scoring

**Problem raised**: too many clubs converged on the same `engagementScore`,
making the CRM's sort-by-score nearly useless for prioritising outreach. Two
compounding causes, found by walking the formula rather than the data (no
production DB access from this environment — verify empirically after deploy
via `diagnose_club_lead.py`'s new `breakdown:` line):

1. `eng_30d` (email) and `events_30d` (web) were **flat counts capped low**
   (`min(events_30d, 20)`, `freq_pts` capped at 40 overall) — many genuinely
   different clubs (5 opens vs 15 opens; a burst last week vs a trickle all
   month) converged on the same capped contribution.
2. `_recency_pts` is a 4-bucket step function (`≤7d→20, ≤30d→14, ≤90d→7,
   else→2`) applied once to a single collapsed `last_touch` (the max across
   web/email/onboarding) — any two clubs whose last touch fell in the same
   bucket were indistinguishable on this term regardless of how different
   their actual history was.

**Fix — per-event, age-decayed points, summed** (mirrors a standard
marketing-automation "score every time" rule, e.g. HubSpot's event-scoring
UI): each qualifying `email_events`/`usage_events` row is scored on **its own**
age against a tiered schedule, and every qualifying row in the last 28 days is
summed — replacing the flat counts, not the separate `_recency_pts` term
(left alone; it was deliberately recalibrated earlier this session, see §14,
and still does its job of gating "last touch" freshness independently).

- **Email** (`email_decay_pts`): a click scores double an open at the same
  age (a click is stronger buying intent than a pixel-fired open, which Apple
  Mail Privacy Protection can trigger unread) — click 16/12/8/4 pts at
  ≤7/≤14/≤21/≤28 days, open 8/6/4/2 pts on the same windows, else 0.
- **Web** (`web_decay_pts`): 3/2/1/0.5 pts per matched page-view/API event at
  ≤7/≤14/≤21/≤28 days, else 0 — a burst of visits this week now clearly
  outscores the same count trickled over the full month.
- `reach_pts` (from `sessions*6`) and `depth_pts` (from `email_decay_pts +
  web_decay_pts`) are computed **separately** and summed into `freq_pts`,
  each through its own **saturating curve** — `cap*raw/(raw+half)`,
  asymptotic towards the cap but never reaching it — rather than a hard
  `min(raw, cap)` clip. Went through two rounds of this, both caught by
  actually running real numbers, not by reading the formula:
  1. First cut pooled reach and depth into one shared 60-point hard cap. A
     local test run (seeded clubs, real Postgres) showed `sessions*6` alone
     could crowd out the whole cap before the decay sums got a chance to
     matter — two clubs with the same event count, one bursting in the last
     week and one trickling over the month, produced genuinely different
     `web_decay_pts` (27 vs 13.5) that both still rounded up to the same
     final score. Fix: split into `reach_pts = min(sessions*6, 24)` and
     `depth_pts = min(..., 40)`, capped independently.
  2. That still broke on real production data: **Tasmania Police CC** (54
     distinct visitors, 71 page views) and **Yarnteen CC** (12 visitors, 20
     views) both blew straight past the 24-point reach cap (hit at just 4
     sessions) and the 40-point depth cap (hit at ~14 recent views), landing
     on the exact same clipped `freq_pts` and an identical final score (84)
     despite one club having ~4.5x the other's real traffic — reported
     directly from the live admin UI. A hard clip can't tell 10% over the
     cap from 1000% over; both land on the same number. Fixed by replacing
     both `min()` clips with the saturating curve above (`half` = the cap
     itself, tuned against both the real Tasmania/Yarnteen numbers and the
     synthetic test clubs from round 1 so typical/low-volume scores barely
     move while genuinely different high-volume clubs now separate:
     Tasmania → 76, Yarnteen → 62).
- Final `score` is rounded once at the very end (`int(round(score))`) since
  the decay sums can be fractional (the 0.5-point web tier); tier-band
  comparisons run on the precise value first.
- New internal-only fields on the `_engagement` return dict —
  `_recencyPts`/`_emailDecayPts`/`_webDecayPts`/`_freqPts` (underscore-prefixed,
  stripped by `_public()` before anything reaches Twenty, same convention as
  `_onboardingRequested`) — surfaced in `diagnose_club_lead.py`'s new
  `breakdown:` line so a score can be explained, not just observed.
- **`app/scripts/engagement_lead_breakdown.py`** (new, read-only) reports this
  same breakdown for every club that currently has a Twenty Lead, sorted by
  score descending, with an optional `--csv <path>` for a spreadsheet-ready
  export — the fleet-wide view (a full audit of every Lead at once) rather
  than `diagnose_club_lead.py`'s one-club-at-a-time lookup.

**Validated against a real local build, not just read**: stood up a throwaway
Postgres 16 + the full app schema (`Base.metadata.create_all` for the
ORM-mapped tables, plus the handful of raw-SQL-only tables main.py's lifespan
otherwise creates) in the sandbox, seeded six clubs with deliberately
different web/email activity shapes, and ran both `diagnose_club_lead.py` and
`engagement_lead_breakdown.py` for real. That's what caught the shared-cap
bug above, and a second, unrelated latent bug in the same pass:

- **`refresh_engagement()` and `_seed_and_refresh_leads()` — the two bulk/
  periodic scans — were loading a club's linked `Organisation` with a plain
  `session.get(Organisation, id)`, never eager-loading `module_subscriptions`.**
  `_module_split()` only reads the real per-module `org_module_subscriptions`
  rows "when loaded" (its own docstring), and silently falls back to the
  legacy whole-org `module_overrides`/`subscription_status` fields otherwise —
  which lumps ALL held modules into either "all paid" or "all trial" with no
  per-module distinction. The three real-time single-company push paths
  (`push_club_and_contacts`, `push_org_company`, `export_to_twenty`) already
  eager-load correctly (`options=[selectinload(Organisation.module_subscriptions)]`)
  — only the two bulk scans that run against the WHOLE club book (the daily
  06:00 engagement refresh and the daily 07:00 Lead/Task sweep — the paths
  that matter most) were missing it. Fixed both to match; also fixed the same
  gap in `diagnose_club_lead.py`/`engagement_lead_breakdown.py` themselves
  (caught when a seeded customer club with a genuinely paid module scored as
  if it were still a prospect, because the org's paid-module row wasn't
  visible to `_module_split` without the eager load).

**Depends on AWS SES "Open and click tracking" actually being enabled** on the
`ses_configuration_set`/`ses_configuration_set_transactional` config sets in
the SES console — that's an AWS-side toggle, not app config. If it's off,
`email_events` never gets `open`/`click` rows and `email_decay_pts` is always
0 (check with `docker exec -e PYTHONPATH=/app betterstats-backend python -m
app.scripts.email_opens` — 0 opens across the board with real sends means
tracking is off, not that nobody's reading the emails).

Emitted `emailEngaged30d`/`sessions30d`/`events_30d` display fields are
unchanged (still flat counts, for CRM-visible "how many" context) — only the
internal scoring formula now reads the decayed sums instead of the flat ones.
