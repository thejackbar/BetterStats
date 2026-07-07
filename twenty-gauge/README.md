# Twenty Pipeline Target Gauge

A small self-hosted gauge widget for a Twenty CRM dashboard iFrame. Shows the
sum of open Opportunity amounts against a target, as a semicircular SVG gauge.

## What it is

- `main.py` — FastAPI proxy. Holds the Twenty API key server-side, exposes one
  endpoint (`GET /api/pipeline`) that returns `{ current, target, currency,
  currencySymbol, updatedAt }`, and serves `index.html` at `/`. Both routes sit
  behind HTTP Basic Auth (see "Access control" below).
- `index.html` — the gauge page itself. Fetches `/api/pipeline` on load and
  every 60 seconds, no build step, no chart library.

The API key never reaches the browser — only the two aggregate numbers do.

## Setup

1. `cp .env.example .env` and fill in `TWENTY_API_KEY`, `GAUGE_USERNAME`,
   `GAUGE_PASSWORD` (see below). The other defaults already match this
   workspace (`TWENTY_BASE_URL`, `ALLOWED_FRAME_ANCESTORS`,
   `EXCLUDED_STAGES`) — check them anyway.
2. From `/srv/docker/twenty-gauge/` (or wherever this folder lands on the
   server):
   ```bash
   docker compose up -d --build
   ```
   This runs as its **own** compose project, separate from the main
   `bltbox_docker_app` stack — deliberately, since it's a standalone service
   per the original brief, not part of the BetterStats app itself.
3. Confirm it's up: `curl -u USER:PASS http://localhost:8000/api/pipeline`
   (adjust the port if you changed `PORT`) — without `-u` you'll correctly get
   a 401.
4. Point a reverse-proxy hostname at it (e.g. via nginx-proxy-manager, the
   same tool that routes Twenty and BetterStats on this box) so the iFrame
   widget has a real `https://` URL to load — a bare container address won't
   work from the browsers viewing the dashboard. The compose file joins
   `docker-shared-net` (the same network Twenty itself is on) so NPM can
   reach it by container name.

### Generating the Twenty API key

In Twenty: **Settings → API & Webhooks → + Create key**. Give it read access
(no write is needed). The key is shown once — copy it straight into `.env`.

### Adding the iFrame widget to a Twenty dashboard

Twenty's current docs (checked live, not from memory) describe dashboards
like this — no "Early Access" toggle was found on the current version, so
that step may be out of date if you're on an older Twenty release:

1. **Dashboards** in the left nav → **+ New Record** (or open an existing
   dashboard).
2. Name the dashboard, then in edit mode click **+** in the tab bar (or use
   an existing tab) and add a widget to it.
3. Pick the **iFrame** widget type from the widget list.
4. Paste this app's public URL (the one your reverse proxy serves) as the
   iFrame source.
5. Save. The browser should show a native Basic Auth prompt inside the
   iframe on first load — enter `GAUGE_USERNAME`/`GAUGE_PASSWORD`. Once
   entered, the browser caches it for that origin, and the gauge refreshes
   itself every 60s with no further prompts.

If the auth prompt doesn't appear inside the iframe (some browsers restrict
HTTP-auth dialogs for cross-origin embedded content more than others — this
wasn't tested inside an actual Twenty dashboard iframe), tell me and I'll
switch the gate to a token in the URL (`?key=...`) instead, which always
works in an iframe since it needs no prompt at all.

Twenty doesn't have a native gauge widget (confirmed on the current docs —
"Tables and gauge charts remain unavailable but are listed as roadmap
items"), which is exactly why this is an iFrame instead.

## Config (`.env`)

| Var | Default | Notes |
|---|---|---|
| `TWENTY_BASE_URL` | `https://twenty.betterat.cricket` | no trailing `/api` |
| `TWENTY_API_KEY` | — | required |
| `TARGET_AMOUNT` | `80000` | overridable per-request with `?target=` |
| `CURRENCY_SYMBOL` | `$` | display only |
| `CURRENCY_CODE` | `AUD` | see "Deviations from the brief" below |
| `EXCLUDED_STAGES` | `Lost / Dormant` | comma-separated Opportunity `stage` values to exclude |
| `ALLOWED_FRAME_ANCESTORS` | `https://twenty.betterat.cricket` | space-separated origins allowed to iframe this page |
| `GAUGE_USERNAME` | — | required; HTTP Basic Auth, see "Access control" |
| `GAUGE_PASSWORD` | — | required; app fails closed (500) until both are set |
| `PORT` | `8000` | |

## Deviations from the brief — read before deploying

The brief asked me to verify Twenty's API against current docs rather than
memory. I did, and hit a real limit: **docs.twenty.com does not publish the
REST response shapes** (currency field layout, pagination envelope) — that
detail only exists per-workspace in your own instance's in-app API Playground
(Settings → API & Webhooks). Rather than guess, I used this exact workspace's
own already-working Twenty integration in the main BetterStats repo
(`backend/app/services/twenty_client.py`, `twenty_sync.py`), which is
verified against your live instance. That gave solid ground truth:

- Currency fields are `{"amountMicros": int, "currencyCode": "AUD"}`.
- List responses are `{"data": {"opportunities": [...]}, "pageInfo":
  {"hasNextPage": bool, "endCursor": str}}`, and the next page is requested
  with `starting_after`, not `after`.
- This workspace's real Opportunity pipeline stages (from
  `docs/twenty-crm-integration.md` in the main repo) are Target / Contacted /
  Engaged / Trial / Proposal / Won / **"Lost / Dormant"** — so
  `EXCLUDED_STAGES` defaults to `Lost / Dormant`, not the brief's generic
  `LOST` placeholder, which wouldn't match anything here.

Two small additions beyond the brief's exact config list, both needed to make
the pieces fit together:

- **`CURRENCY_CODE`** — the brief's response contract wants `"currency":
  "AUD"` (an ISO code) but its config list only had `CURRENCY_SYMBOL` (a
  display glyph like `$`). Added a separate env var for the code so both are
  configurable independently.
- **Stage filtering is done client-side** in Python after fetching, not via a
  Twenty `filter=` query string. The `filter[field]=eq:value` syntax exists,
  but its exact operator name for "not equal" isn't published either, and
  guessing it wrong would fail silently. Filtering after fetch is slightly
  less efficient but correct regardless of the exact filter grammar, and a
  club-scale Opportunity count is small.

**Please verify once deployed** (this is also the brief's own acceptance
check): compare `GET /api/pipeline`'s `current` against Twenty's own pipeline
aggregate for the same stage filter. If it's off, the likely culprits are
listed above — tell me the actual numbers and I'll adjust.

## Access control

Both `/` and `/api/pipeline` require HTTP Basic Auth (`GAUGE_USERNAME` /
`GAUGE_PASSWORD`). This app has no user accounts or roles of its own and
isn't wired into BetterStats' or Twenty's logins, so it's one shared
credential you hand only to the people who should see it (your superadmins)
— not a per-person login. Generate a real password
(`openssl rand -base64 24`), never commit it, and rotate it (just change the
env var + restart) if it's ever shared more widely than intended.

The app **fails closed**: if `GAUGE_USERNAME`/`GAUGE_PASSWORD` aren't set,
every request 500s rather than silently serving the page unauthenticated.

This is on top of, not instead of, `ALLOWED_FRAME_ANCESTORS` (which controls
*where* the page can be framed) — keep both set.
