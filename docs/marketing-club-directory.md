# Marketing club directory (BetterCricket outreach)

A national list of Australian cricket clubs, enumerated from the PlayHQ public
directory, stored in the BetterStats database, and bridged into the existing
BetterComms send pipeline for BetterCricket's own outreach campaigns. This is the
data engine behind `docs/email-outreach/` (the campaign emails and `make_sends.py`).

## Data source: the PlayHQ public directory

The directory behind playhq.com's own org search is two unauthenticated GraphQL
endpoints (no API key — we read them the same way the website does). The client
is `app/services/playhq_directory_client.py`.

**Search** (`https://search.playhq.com/graphql`, `search(filter: SearchFilter)`).
An empty `query` with `sports:[CRICKET]` and `types:[CLUB]` enumerates the whole
list, paged (limit 100, clean stop on an empty page). Australia is
`tenant.name == "Cricket Australia"` (the `tenant` is the governing body —
confirmed ~6,900 AU clubs, the rest New Zealand). Each `Organisation` carries:

- `id` (the GUID we dedupe on, stored in `grassroots_guid`)
- `routingCode` (the short code the main graph keys on, stored in `playhq_id`)
- `name`, `websiteUrl`
- `address`: `line1`, `suburb`, `postcode`, `state`, `country`, lat/long
- `contacts[]`: the **full committee** — `firstName`, `lastName`, `position`,
  `email`, `phone`, `visible`

So unlike the old grassroots org-detail endpoint (one anonymous role mailbox per
club), this gives **named office bearers with direct emails and mobiles**.

**Main graph** (`https://api.playhq.com/graphql`,
`discoverCompetitions(organisationID: routingCode)`). Each competition's
`organisation` (type `ASSOCIATION`) is an association the club plays in; a club
commonly plays across several (a turf comp, a junior comp, a women's league). This
endpoint routes per tenant, so it needs a `tenant: cricket-australia` header
(without it the server returns "Bolt adapter map not found"), and it keys on the
**routingCode**, not the search GUID.

### What we store, and why not everything

We keep **office bearers + coordinators** only — President, Vice-President,
Secretary, Treasurer, and the junior/female/cricket coordinators (the position
vocabulary, including CA's "COODINATOR" typo, is normalised in
`club_directory._role_for_position`). The rest of the committee (general members,
coaches, scorers) is skipped: less personal data held, and the kept roles are the
outreach decision-makers. Every kept contact is a `marketing_club_contacts` row
with a `role_rank` so the priority roles sort to the top. This is named-person
contact data, so it carries Privacy Act weight — hold only what outreach needs,
and the BetterComms suppression sync (below) makes any opt-out global.

## Storage

Two tables (migrations 095 + 096, mirrored idempotently in the `main.py`
lifespan). Prospects, not customers, so they are decoupled from `organisations`,
same precedent as `club_onboarding_requests`.

- **`marketing_clubs`** — one row per club. Carries the metadata above plus
  `association_name`/`association_guid` (the primary association), `associations`
  (a JSONB list of every association the club plays in: `{id, name, competition}`),
  `raw_json` (the whole search payload, so re-crawls are cheap), `existing_org_id`
  (links a row that is already a BetterStats customer so outreach can skip it), and
  the crawl state. `detail_fetched_at` is set at discovery (core data present);
  `associations IS NULL` marks the **association-enrichment frontier**.
- **`marketing_club_contacts`** — emailable contacts, many per club, with `role`,
  `role_rank`, `email`, `mobile`, `source` (`api` | `website` | `manual`), and a
  `subscribed` suppression flag synced from BetterComms.

## The crawl

Two phases (`app/services/club_directory.py`), both resumable through the table:

1. **Discovery** (`discover_clubs`) — page the PlayHQ search to completion,
   upserting every AU club with its committee + address. ~70 calls, idempotent.
   Runs on the first batch (empty directory) or when asked to `rediscover`.
2. **Association enrichment** (`enrich_associations`) — for up to `limit` clubs
   whose `associations` is still NULL (the frontier), call `discoverCompetitions`
   and store the association list. A fetch failure leaves the row NULL so it
   retries next batch.

`crawl_batch` runs discovery (when needed) then one enrichment slice. Run it until
`associations_pending` reaches 0; later runs with `rediscover` pick up new clubs.

### Politeness

Deliberately a slow, quiet citizen (settings `marketing_crawl_*`): concurrency 1,
a jittered 2 to 4s delay between requests, a single backoff-and-retry on 429/5xx, a
nightly cap, run off-peak (the scheduler job is 02:00). Discovery is cheap (~70
calls); enrichment is one call per club across ~6,900 clubs, so it is a handful of
quiet nights at the nightly cap. `raw_json` + the frontier model mean re-runs
never refetch an enriched club.

### Two run modes

Both are **opt-in** via `marketing_crawl_enabled=true` in the server `.env` (off
by default, so nothing crawls on deploy without a deliberate switch):

- **Nightly batch** (default) — `crawl_marketing_clubs` at 02:00 walks one capped
  slice (`marketing_crawl_nightly_limit`) per night. Lowest profile; the full
  backfill takes a couple of weeks of off-peak nights.
- **Continuous** (`marketing_crawl_continuous=true`) — a long-lived background
  runner (launched as an asyncio task at startup; the nightly cron is skipped)
  that walks the **whole backfill as fast as the pacing allows, inside a daily
  active window**. This is the "finish ASAP but look organic" mode.

**Continuous pacing** (all `marketing_crawl_*` settings): active window
`04:30`–`23:30` `Australia/Perth`; a jittered **15–40 s gap before every call**
(mean ~27.5 s); a **2–3 min break every 30–60 clubs** to mimic a person stepping
away; outside the window it sleeps. So the whole job — ~75 discovery calls plus
one call per club (~4,000–5,000) — is **about two 04:30–23:30 windows (~2 days)**,
at roughly 2,500 requests/day. A club whose association fetch keeps failing
(unresolvable routingCode / persistent 5xx) is retried a few times, dropped to the
back of the queue, then given up (`associations=[]`) so completion is always
reachable. When the frontier empties the runner re-discovers each day to pick up
newly-registered clubs (`marketing_crawl_refresh_daemon`, on by default).

By hand, from the backend container:

```bash
python -m app.scripts.crawl_clubs              # one batch (discovers on first run)
python -m app.scripts.crawl_clubs 1000         # enrich up to 1000 frontier clubs
python -m app.scripts.crawl_clubs --rediscover # re-page the club list, then enrich
python -m app.scripts.crawl_clubs --continuous # the windowed background runner (Ctrl-C to stop)
python -m app.scripts.crawl_clubs --stats      # counts only, crawl nothing
python -m app.scripts.crawl_clubs --csv > clubs.csv   # export the directory
```

Super-admin API (gated by `require_super_admin`, prefix `/club-admin/marketing`):
`GET /stats`, `GET /clubs` (search/filter/paginate), `POST /crawl` (background
batch), `POST /export-comms`, `POST /sync-suppressions`, `GET /export.csv`.

## Sending: the BetterComms bridge

BetterCricket reuses the per-club BetterComms machinery for its own sends rather
than a second send path. The flow:

1. **Create a platform org** that owns the outreach campaigns (a normal
   `organisations` row, e.g. slug `bettercricket-marketing`). Then designate it
   as the outreach org one of three ways (the DB flag wins): flag it from the
   BetterComms UI (a super admin uses the "Comms context" bar → "Set up
   BetterCricket marketing", which sets `organisations.is_marketing_outreach`),
   set `marketing_outreach_org_slug` to its slug, or pass `organisation_id` to
   the export. The UI flag needs no env change or redeploy; at most one org can
   hold it (partial unique index `uq_org_marketing_outreach`).
2. **`POST /club-admin/marketing/export-comms`** materialises the filtered
   selection (subscribed, has email, not already a customer, optional state
   filter) into `comms_contacts` under that org. Existing suppressions on the
   comms side are left untouched.
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
BetterComms provides the last two. The contacts are named office bearers with
personal mobiles and emails, so the Privacy Act applies: hold only the roles
outreach needs (office bearers + coordinators, not the whole committee), and keep
the global suppression in sync so opt-outs stick across campaigns. Confirm the
PlayHQ terms permit this use before scaling the crawl.

## Architecture note

The crawl is plain code run as a resumable background job, not an LLM agent: it is
a long, repetitive, rate-limited I/O loop where determinism and pacing matter, so
code is cheaper and more predictable. It lives in the repo (not a standalone
off-box script) so it shares the DB session, models, settings, the polite client
patterns and the BetterComms integration, and stays migration-aware and
version-controlled.
