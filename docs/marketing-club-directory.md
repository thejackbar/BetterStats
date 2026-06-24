# Marketing club directory (BetterCricket outreach)

A national list of Australian cricket clubs, crawled from the CA/grassroots org
graph, stored in the BetterStats database, and bridged into the existing
BetterComms send pipeline for BetterCricket's own outreach campaigns. This is the
data engine behind `docs/email-outreach/` (the campaign emails and `make_sends.py`).

## What the API gives us, and what it doesn't

The crawl reads one unauthenticated grassroots endpoint we weren't using before:
`GET /orgsproducts/organisation/{organisationGuid}`. Per club it returns:

- `name`, `shortName`, `playHQId`, `myCricketId`, `organisationGuid`
- `address`: `line1`, `line2`, `suburb`, `stateName`, **`postCode`**, `country`, lat/long
- `affiliations`: the association (name + GUID)
- `websiteURL`, `description`, `logoURL`
- `contact`: a single `{phone, email}` (usually a role mailbox like `secretary@`)

It does **not** expose individual office bearers. There is exactly one contact per
club, with no person name and no role label. So "President, Secretary, Treasurer
with names + personal mobiles + emails" is not retrievable from this API. Phase 1
stores the one club contact (a role is inferred from the mailbox local part where
it reads as one, e.g. `secretary@` becomes Secretary). The contact table is
many-per-club with a `role_rank`, so the priority roles can be added later by
manual enrichment without a schema change; they just won't come from the API.

Targeting club **role mailboxes** rather than individuals' personal contacts is
both the lower-risk choice under the Privacy Act and exactly what the API hands
us, so that's where Phase 1 sits.

## Storage

Two tables (migration 095, mirrored idempotently in the `main.py` lifespan).
Prospects, not customers, so they are decoupled from `organisations`, same
precedent as `club_onboarding_requests`.

- **`marketing_clubs`** — one row per club or association. Carries the full
  metadata above plus `kind` (`club` | `association`, a heuristic so exports skip
  associations), `raw_json` (the whole payload, so re-crawls are cheap),
  `existing_org_id` (links a row that is already a BetterStats customer so
  outreach can skip it), and the crawl state. `detail_fetched_at IS NULL` marks a
  **frontier** node: discovered via an affiliation but not yet detailed.
- **`marketing_club_contacts`** — emailable contacts, many per club, with `role`,
  `role_rank`, `email`, `mobile`, `source` (`api` | `website` | `manual`), and a
  `subscribed` suppression flag synced from BetterComms.

## The crawl

Breadth-first walk of the affiliation graph: a club lists its association, an
association lists its member clubs, so from a handful of seeds the connected
universe unfolds. The crawl is resumable through the table itself. Each batch:

1. Bootstraps the frontier on first run (a few name searches → frontier rows).
2. Takes up to `limit` frontier rows (`detail_fetched_at IS NULL`).
3. For each: fetches org-detail, fills the row, stores the contact, links an
   existing customer org, and enqueues its affiliations as new frontier rows.

Run it until `frontier_remaining` reaches 0, then re-runs keep it fresh.

### Politeness

Deliberately a slow, quiet citizen (settings `marketing_crawl_*`): concurrency 1,
a jittered 2 to 4s delay between requests, a single 429 backoff-and-retry, a
nightly cap, run off-peak (the scheduler job is 02:00). The national universe is
on the order of a few thousand clubs, so at this rate it is a handful of quiet
nights. `raw_json` + the frontier model mean re-runs never refetch a detailed
club.

### Running it

The nightly scheduler job (`crawl_marketing_clubs`, 02:00) is **opt-in**: it only
runs when `marketing_crawl_enabled=true` in the server `.env`. Off by default so
nothing crawls on deploy without a deliberate switch.

By hand, from the backend container:

```bash
python -m app.scripts.crawl_clubs            # one batch of the nightly limit
python -m app.scripts.crawl_clubs 1000       # detail up to 1000 frontier clubs
python -m app.scripts.crawl_clubs --stats    # counts only, crawl nothing
python -m app.scripts.crawl_clubs --csv > clubs.csv   # export the directory
```

Super-admin API (gated by `require_super_admin`, prefix `/club-admin/marketing`):
`GET /stats`, `GET /clubs` (search/filter/paginate), `POST /crawl` (background
batch), `POST /export-comms`, `POST /sync-suppressions`, `GET /export.csv`.

## Sending: the BetterComms bridge

BetterCricket reuses the per-club BetterComms machinery for its own sends rather
than a second send path. The flow:

1. **Create a platform org** that owns the outreach campaigns (a normal
   `organisations` row, e.g. slug `bettercricket-marketing`). Set
   `marketing_outreach_org_slug` to it, or pass `organisation_id` to the export.
2. **`POST /club-admin/marketing/export-comms`** materialises the filtered
   selection (subscribed, has email, `kind=club`, not already a customer,
   optional state filter) into `comms_contacts` under that org. Existing
   suppressions on the comms side are left untouched.
3. **Compose and send a campaign** in BetterComms as normal. Unsubscribe,
   suppression, the audit trail and List-Unsubscribe headers all come for free.
4. **`POST /club-admin/marketing/sync-suppressions`** pulls unsubscribes and
   bounces back into `marketing_club_contacts.subscribed`, so an opt-out is never
   re-contacted in a later campaign or CSV export.

### Separate sending domains

The intent is separate SES-verified domains per silo (clubs, BetterCricket
marketing, BetterCricket business). The send pipeline already takes a per-org
`comms_from_name` / `comms_reply_to` / footer, but the From **address** is still a
single global setting (`email_from_address`). To fully silo the marketing domain,
add a per-org from-address override and read it in `email_service._sender`. That
is a small follow-up, not required for the bridge to work.

## CSV and `make_sends.py`

`GET /export.csv` (and `--csv`) emits a header with `Club`, `UTM` and `Name` plus
the full metadata, which drops straight into
`docs/email-outreach/make_sends.py --csv` for the per-club personalised sends.

## Compliance

These are unsolicited commercial messages under the **Spam Act 2003**, so they
need consent, accurate sender identification and a working unsubscribe.
BetterComms provides the last two. Prefer club role mailboxes over individuals'
personal addresses (lower Privacy Act exposure, and what the API gives anyway).
Keep the global suppression in sync so opt-outs stick across campaigns. Confirm
the CA API terms permit this use before scaling the crawl.

## Architecture note

The crawl is plain code run as a resumable background job, not an LLM agent: it is
a long, repetitive, rate-limited I/O loop where determinism and pacing matter, so
code is cheaper and more predictable. It lives in the repo (not a standalone
off-box script) so it shares the DB session, models, settings, the polite client
patterns and the BetterComms integration, and stays migration-aware and
version-controlled.
