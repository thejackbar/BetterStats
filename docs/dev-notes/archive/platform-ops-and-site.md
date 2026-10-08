# Archive: platform-ops-and-site

Verbatim history moved out of `CLAUDE.md` on 2026-09-30. NOT loaded into context automatically.
Scope: Deploy, outages, domain and brand, marketing site pages, modular entitlements, versioning, writing voice, architecture basics.
Read the distilled rules first: `docs/dev-notes/guides/platform-ops-and-site.md`. Open this file only when you need the full reasoning, measurements or history behind a rule, and search it (grep) rather than reading it whole.
Sections are in their original relative order. The `BEGIN`/`END` comments carry the line range in the untouched copy `CLAUDE.original-2026-09-30.md`.

<!-- BEGIN original CLAUDE.md L12321-12333 -->
## Writing Voice — always run prose through the humanizer

Any user-facing prose you write or edit (marketing copy, changelog entries, UI
strings, docs, PR/commit bodies, longer chat replies) must go through the
**`humanizer`** skill before it ships — it's vendored at
`.claude/skills/humanizer/` so it's available in every web session. Apply its
rules even when you don't invoke the skill explicitly: no em/en dashes, no
forced rule-of-three triads, no promotional "AI vocabulary" (vibrant, seamless,
testament, elevate…), no tailing negations ("no guessing", "no fuss"), plain
`is`/`are`/`has` over "serves as"/"boasts". Keep the plain Australian
cricket-club voice. Page-`<title>` separators use the site-wide `—` convention
(structural, not prose) and are the one allowed exception.

<!-- END original CLAUDE.md L12321-12333 -->
<!-- BEGIN original CLAUDE.md L12334-12355 -->
## Server Deploy Command

The box runs **all ~26 containers as ONE systemd-managed compose project, `bltbox_docker_app`** (`/etc/systemd/system/docker-compose-app.service`: `WorkingDirectory=/srv/docker`, `Environment="COMPOSE_PROJECT_NAME=bltbox_docker_app"`, `ExecStart=docker compose up -d`). BetterStats is defined inside the **central** file `/srv/docker/docker-compose.yaml` (NOT the retired `/srv/docker/betterstats/docker-compose.yml`).

**Deploy by running the committed script — `/srv/docker/betterstats/deploy.sh`.** Long form:

```bash
cd /srv/docker
export COMPOSE_PROJECT_NAME=bltbox_docker_app   # ← LOAD-BEARING (see post-mortem below)
git -C /srv/docker/betterstats pull origin main
docker compose build --no-cache betterstats-frontend betterstats-backend
docker compose up -d --no-deps --force-recreate betterstats-frontend betterstats-backend
```

- **`COMPOSE_PROJECT_NAME=bltbox_docker_app` is mandatory.** Without it, `docker compose` from `/srv/docker` defaults to project `docker` (the directory name) → a *second* betterstats stack on a *separate, empty* pgdata volume that steals the `betterstats-*` container names. **This caused the June 2026 outage (post-mortem below).**
- Run from `/srv/docker` so `.env` (secrets) + the override file load — matches how systemd runs it. Don't pass `-f` (it skips the override and drifts the config hash).
- `--no-deps` + naming only the two services ⇒ the database (`betterstats-db`) and the other ~24 apps on the box are never touched. **Never recreate `betterstats-db`** — the data lives in the `bltbox_docker_app_betterstats_pgdata` volume.
- `--no-cache` on the build avoids stale Docker layer cache.
- **Operate containers ONLY via `docker compose …` (from `/srv/docker`, with `COMPOSE_PROJECT_NAME` set) — never bare `docker run/restart/exec/ps`.** Bare `docker` commands fall outside the pinned project and spawn/leave duplicate stacks/containers that are a nightmare to tell apart (same root cause as the project-split outage below). To act on another app on the box (e.g. nginx-proxy-manager), discover its compose **service** name (`docker compose ps --services`) and use `docker compose exec/restart <service>` — don't hardcode a container name or shell out to `docker <verb>`.
- Ignore `POSTGRES_PASSWORD` / `LANGFLOW_*` "not set" warnings (other services' vars). **NEVER add `--remove-orphans`** — it would delete `klubpro-mongo` / `restreamer` (other people's apps).
- nginx-proxy-manager routes `betterstats.cricket` → `betterstats-frontend` on `docker-shared-net` (apex is canonical; `www.betterstats.cricket` 301-redirects to it). The frontend `nginx.conf` MUST proxy `/api` to **`betterstats-backend`** — never the bare `backend`, which on the shared network resolves to a *different app's* API (that was bug #2 below).

<!-- END original CLAUDE.md L12334-12355 -->
<!-- BEGIN original CLAUDE.md L12356-12372 -->
## June 2026 Production Outage — Post-Mortem (compose project split)

**Symptom**: `betterstats.cricket` 502'd, then returned showing a months-old marketing page with **every club page blank** (`/applecross` empty). Looked like total data loss.

**Nothing was actually lost** — three independent problems had stacked up:

1. **Compose project split → wrong (empty) data volume.** All ~26 containers run as systemd project `bltbox_docker_app`, but betterstats had *also* been deployed as an ad-hoc project `docker` (what you get running `docker compose` from `/srv/docker` WITHOUT `COMPOSE_PROJECT_NAME`). The real 370 MB database lived in the `docker` project's volume (`docker_betterstats_pgdata`); when the systemd stack (re)started, *its* betterstats came up on the empty `bltbox_docker_app_betterstats_pgdata` and — `container_name:` being hardcoded/global — stole the `betterstats-*` names. Result: site up, zero data. *Fix*: clone the real volume into the one the live stack uses —
   `docker run --rm -v docker_betterstats_pgdata:/from:ro -v bltbox_docker_app_betterstats_pgdata:/to postgres:15 bash -c 'find /to -mindepth 1 -delete; cp -a /from/. /to/; rm -f /to/postmaster.pid'`
2. **Crossed `/api` proxy → answered by a DIFFERENT app.** The deployed frontend's `nginx.conf` proxied `/api` to the bare host `backend`, which on `docker-shared-net` resolves to *another app's* API (ProLog). Every cricket data call got someone else's 404s → blank pages. The repo's current `nginx.conf` correctly uses `betterstats-backend`; the running image just predated that fix.
3. **Stale image / version mismatch.** That old frontend/backend pair predated the `/clubs/{slug}` endpoint, so club pages 404'd even after the proxy fix. Deploying current code (matched pair) fixed it.

**Root trigger**: a deploy/restart run WITHOUT `COMPOSE_PROJECT_NAME=bltbox_docker_app`, which forked a second betterstats project. **Prevention**: always deploy via `deploy.sh` (project name pinned). **If it recurs, diagnose in this order**:
1. `docker compose ls -a` — are there TWO projects with betterstats? (`docker` vs `bltbox_docker_app`)
2. `docker volume ls | grep pgdata`, then `docker run --rm -v <vol>:/v postgres:15 du -sh /v` — which pgdata volume holds the data (the big one)?
3. `curl -s https://betterstats.cricket/api/openapi.json | head` — is `/api` answered by **"BetterStats API"** (title) or a different app?
4. `docker exec betterstats-frontend grep -rn proxy_pass /etc/nginx/` — does `/api` point at `betterstats-backend`?

<!-- END original CLAUDE.md L12356-12372 -->
<!-- BEGIN original CLAUDE.md L12373-12392 -->
## June 2026 Admin Outage #2 — Post-Mortem (NPM can't resolve betterstats-frontend)

**Symptom**: `/admin` died with **"Failed to fetch dynamically imported module: …/assets/AdminDashboard-H0O_EwuY.js"** and an intermittent 502 on that chunk. Looked like a stale/corrupt asset or poisoned cache — it was **neither**.

**Root cause**: after `betterstats-frontend` was recreated (a deploy, then a manual `--force-recreate`), it got a **new Docker IP**, and **nginx-proxy-manager could not reliably DNS-resolve the `betterstats-frontend` name** — error log: `betterstats-frontend could not be resolved (2: Server failure)` (a DNS SERVFAIL) for `server: betterstats.cricket`. NPM resolves the upstream **per worker** at request time, so some workers had a good resolution (→ 200) and some a cached SERVFAIL (→ 502). That per-worker split is why it looked like **one specific file/URL**: `?v=2`, `/api/openapi.json` and most assets happened to hit "good" workers, while the bare admin chunk kept hitting a "bad" one. The file was fine all along.

**Misleading signals that wasted time (don't repeat the chase)**:
- `?v=2` on the chunk → 200, bare URL → 502. *Looked* like a URL-keyed cache; was actually per-worker DNS luck.
- The file on disk in the container was byte-perfect (`sha256` matched a clean local build) and served **200 directly** (`docker compose exec betterstats-frontend wget -qO- localhost/assets/<chunk>`), proving the origin was healthy.
- There was **no cached object** for the asset in any NPM cache zone — purging did nothing. Not a cache bug.

**The tell is in the NPM error logs, not the app logs**: `docker compose exec <npm-service> sh -c 'grep -RhiE "could not be resolved|betterstats-frontend" /data/logs/*error*.log | tail'`. The per-host access log also lives in `/data/logs/proxy-host-*_access.log` (`[Sent-to betterstats-frontend]`).

**Fix (what actually worked)**: restart NPM so all workers re-resolve the frontend's current IP. **Do it the compose way** (bare `docker` is banned — see deploy rules): discover the proxy service then
`docker compose restart "$(docker compose ps --services | grep -iE 'proxy|npm|manager' | head -1)"`. A graceful `nginx -s reload` was tried first and did **NOT** clear it during the incident — a full restart was required.

**Prevention (shipped)**: `deploy.sh` now has a `[4/4]` step that, after recreating the frontend, reloads NPM, health-checks `https://betterstats.cricket/` 3×, and restarts the proxy service only if any check is non-200 — so every deploy self-heals this. The frontend also reloads once on a chunk-load failure (`vite:preloadError` in `main.jsx` + chunk-aware `ErrorBoundary`), turning a transient 502/stale-chunk into a silent retry instead of the "Something went wrong" dead-end.

**If it recurs**: 1) NPM error log for `could not be resolved`; 2) confirm the two containers still share a network (`docker compose exec <npm> getent hosts betterstats-frontend`); 3) if the name resolves from NPM but the site still 502s, it's stale per-worker resolver state → restart the proxy **service** via `docker compose restart`.

<!-- END original CLAUDE.md L12373-12392 -->
<!-- BEGIN original CLAUDE.md L12393-12402 -->
## Public Domain

The canonical public domain is **`https://betterat.cricket`** (no `www`), the **BetterCricket** brand. The brand name is written **as one word, "BetterCricket"** (Jun 2026 — was the two-word "Better Cricket"); keep it one word in all user-facing copy, page titles, OG/social cards, metadata and the `BRAND` constant in `frontend/src/data/marketing.js`. The module names stay camelCase (BetterStats, BetterSelect, BetterSocials, BetterAdmin, BetterIQ — **BetterStats remains the Core module name**), and the trading company stays **BetterSports**. A permanent redirect from the old `betterstats.cricket` to `betterat.cricket` (301 for GET/HEAD, 308 otherwise) is **prepared in `cloudflare-worker/worker.js` but not yet deployed**; once it ships it consolidates the old domain's link equity onto the canonical. Until then both hostnames serve the same app, so links work on either. The older `betterstats.bltbox.com` domain is retired.

- **Everything public points at `betterat.cricket`** (keep new public-URL references there): `frontend/src/hooks/usePageMeta.js` (`BASE_URL`), `frontend/index.html` (`og:url`, canonical, JSON-LD), `frontend/public/{llms.txt,robots.txt,sitemap.xml,site.webmanifest}`, the backend `routers/seo.py` (`SITE`, the live sitemap + robots nginx proxies), `routers/og_preview.py` (`SITE`), `config/settings.py` (`public_base_url`, the email unsubscribe link), the `deploy.sh` health check, and the `tools/sync_watch.py` default base.
- **Email — one address everywhere: `support@bettersports.com.au`** (Jul 2026, was `cricket@bettersports.com.au`; before that a `noreply@betterstats.cricket` From plus a `betteratcricket@gmail.com` reply-to/contact). It's the default reply-to (`config/settings.py` `email_reply_to`, from-name "BetterCricket" — `email_from_address` is a separate deliverability-only sending address, currently `notifications@betteratcricket-comms.work`) AND the public contact address shown across the site: `SUPPORT_EMAIL` in `frontend/src/data/marketing.js`, the hardcoded copies in `frontend/index.html` (JSON-LD), `frontend/public/llms.txt`, `backend/app/routers/og_preview.py`, `backend/app/routers/self_serve_trial.py`, and the marketing/login pages (Privacy, Terms, Contact, FAQ, Login, MarketingFooter). **DNS still to do**: for sent mail to pass authentication, `bettersports.com.au` needs SPF/DKIM/DMARC set up (the records used to live on `betterstats.cricket`); until then sent mail may be flagged as spam. `email_provider` defaults to `console`, so nothing sends until a provider is configured anyway.
- `CORS_ORIGINS` should be `https://betterat.cricket` in the server `.env`, but CORS is dormant in practice: the frontend calls the API via a same-origin relative `/api` path, so cross-origin checks never fire. Updating it is hygiene, not a functional requirement.
- `betterat.cricket` social link-preview cards are server-rendered for the marketing routes by `backend/app/routers/og_preview.py` (`MARKETING_PAGES`), so per-page OG tags work for crawlers that do not run JS; keep that map in sync when marketing routes change.
- `cloudflare-worker/worker.js` is a pure old-domain redirect, **ready but not yet deployed** (its old OG-injection job is handled by `og_preview`). When ready, `wrangler deploy` it and keep the Cloudflare route `betterstats.cricket/*` active.

<!-- END original CLAUDE.md L12393-12402 -->
<!-- BEGIN original CLAUDE.md L12403-12429 -->
## Blog post social-share cards (Jun 2026)

Each blog post (`/blog/{slug}`) gets its own social-share card from
`backend/app/routers/og_preview.py` (`_blog_html`): the post's own hero image,
title and description, `og:type=article`, and BlogPosting + Breadcrumb JSON-LD
that mirrors `frontend/src/pages/marketing/BlogPost.jsx`. Before this, a shared
post fell through to the generic homepage card, because the SPA's client-side
`usePageMeta` tags never reach Facebook/LinkedIn crawlers (they read raw HTML,
not rendered JS).

The backend's blog metadata is in one place, `backend/app/content/blog.py`
(`BLOG_POSTS`: slug, title, description, image, date). Both `og_preview.py` (the
card) and `routers/seo.py` (the sitemap, via `BLOG_SLUGS`) read it, so the old
hand-kept slug list in `seo.py` is gone.

**Adding a future post** is three steps that have to stay in sync:
1. Drop the hero image in `frontend/public/marketing/blog/` (1920x1080 reads
   well as a `summary_large_image` card).
2. Add the full post to `frontend/src/data/blog.js` (the article body and the
   in-app meta).
3. Add a matching row to `backend/app/content/blog.py`, copying the
   title/description/image/date straight from `blog.js` so the card matches the
   page.

After deploy, re-scrape an already-shared link in Facebook's Sharing Debugger
(and LinkedIn's Post Inspector) to clear their cached copy of the old card.

<!-- END original CLAUDE.md L12403-12429 -->
<!-- BEGIN original CLAUDE.md L12430-12510 -->
## Marketing Contact form → club onboarding requests (Jun 2026)

The public Contact page (`betterat.cricket/contact`,
`frontend/src/pages/marketing/Contact.jsx`) still emails enquiries via Formspree,
and now also stores each one in BetterStats so staff can track onboarding. On
submit the form fires a best-effort `POST /api/public/contact` (api
`submitOnboarding`) alongside the Formspree post. Formspree stays the primary
delivery and drives the success/error UI, so a failed store never blocks the form.

- **Table** `club_onboarding_requests` (migration 079, mirrored idempotently in the
  `main.py` lifespan): name / club / email / phone / association / grades / storage /
  timeline / club_url / message, plus `status` (new | contacted | onboarded | closed),
  source, user_agent, created_at. No `organisation_id` (the sender is a prospect, not
  a member).
- **Public router** `routers/public_contact.py` (`POST /public/contact`,
  unauthenticated, NOT module-gated): validates name/club/email, clips every field,
  stores one row.
- **Super-admin UI** `/admin/super/onboarding` (`pages/admin/SuperOnboarding.jsx`,
  `requireRole="super_admin"`, linked from AdminLayout `SUPER_LINKS`): lists requests
  newest-first, filter by status, change a row's status. Backed by `GET` + `PATCH
  /club-admin/super/onboarding-requests` in `club_admin.py`.
- **Deploy note**: the store assumes `betterat.cricket` routes `/api` to
  `betterstats-backend` the same way `betterstats.cricket` does (same frontend
  container + nginx `/api` proxy). If the marketing domain is ever served separately
  without that proxy, point the form at the absolute backend URL instead. It degrades
  gracefully meanwhile, since Formspree still delivers the email.

### Club name is a search, not a text box (migration 224, v9.12.2, Aug 2026)

The Club name field asked a person under time pressure to spell their club, and
every downstream match then had to work back from that string — so "Applecross
CC" and "Applecross Cricket Club" became two prospect rows. It now searches the
same Cricket Australia club list the self-serve trial wizard searches, and a
picked club carries its real CA organisation guid through with the enquiry.

- **`GET /public/contact/club-search`** reuses `self_serve_trial.search_clubs`
  (one club list, one matching rule) but is deliberately **NOT** routed through
  `/public/self-serve`: that whole router sits behind the
  `self_serve_registration_enabled` platform flag, and the Contact form has to
  keep working whether or not self-serve registration is switched on. Rate-limited
  per IP (120/hour) like its sibling, since every keystroke reaches CA's API.
  The response is **projected down** — the self-serve search also returns the
  registered club's public slug and its Primary Admin's first name + last initial
  (for the "talk to your admin" card), and a marketing page has no business
  serving either. `already_registered` is kept and shown, but never blocks: an
  already-registered club is still entitled to get in touch.
- **`club_onboarding_requests.club_org_id` + `.club_source`** ('search' |
  'manual'). A guid is only ever stored alongside `club_source='search'` — a
  typed name has nothing to key on, and letting a manual row carry an id would
  put a guessed identity on the record. An unrecognised `clubSource` drops both.
- **`_resolve_onboarding_club` (twenty_sync) takes `org_id`** and checks it
  **after** the submitter's email but **before** the name, so the established
  email-first priority `_onboarding_signal` shares is untouched. A new row is
  created on the REAL guid — the same one the PlayHQ crawler uses — so a row
  created by an enquiry and a row the crawler finds later are one row.
  `crm.sync_deal_for_enquiry` takes and forwards the same `org_id`, so the local
  pipeline and the Twenty push can't resolve different clubs.
- **A `manual:` guid is upgraded once the real one is known**, but only when no
  other row already holds it. `grassroots_guid` is unique, so the check is also
  what stops a background task raising; and two rows for one club is a merge
  decision for a person, not a silent write.
- **The typed name stays, on purpose.** The CA list only covers Australia, so
  "can't find your club" hands back a plain text field rather than a dead end —
  that is what keeps a club in England or New Zealand able to reach us.
- **`frontend/src/components/marketing/ClubSearchField.jsx`** holds one
  invariant worth keeping: **`club` is only ever set once `clubSource` is**, so a
  half-typed search term is the field's own local state and the form's existing
  "Club name is required" check blocks a search nobody finished. A `?club=` link
  (`ClubInactive.jsx`) seeds the search rather than answering it.
- **Verified** against a real Postgres (25 checks — the resolution priority, the
  guid upgrade and its collision guard, the migration applied twice to a
  populated pre-224 table, the route bodies incl. a junk `clubSource` and the
  short CTA form's unchanged bare post, and the original bug reproduced: two
  spellings made two clubs, now make one) and driven in a browser (search,
  keyboard pick, submitted payload, the no-results fallback, validation blocking
  an unfinished search, `?club=` seeding, no mobile overflow).
- **Not done**: the short "Get your club on BetterCricket" CTA modal
  (`QuickEnquiryModal`) still posts a free-text club name to the same endpoint —
  the backend fields are optional so it is unaffected, and it is the obvious next
  place to reuse `ClubSearchField`.

<!-- END original CLAUDE.md L12430-12510 -->
<!-- BEGIN original CLAUDE.md L12511-12539 -->
## Public Marketing Pricing — modular model (Jun 2026)

The **public** marketing pricing and the in-app entitlement model are both
**modular** now (the Good/Better/Best tiers were retired, see "Modular
entitlements" below). The public price model is still kept separate from the
entitlement registry (`frontend/src/lib/modules.js`) so marketing copy and
gating logic move independently. Public model: **Core (BetterStats) $399/yr**
plus modules **BetterSelect / BetterSocials / BetterAdmin $149 each** and
**BetterIQ $249**, an **annual licence only** (no monthly). Bundle discount is a
**set dollar amount** keyed on module count (2 modules save $48, 3 save $97, all
4 save $146), so Core + all four = **$949** (see `BUNDLE_DISCOUNT` in
`pricing.js`).

- **Source of truth**: `frontend/src/data/pricing.js` (`CORE`, `PRICED_MODULES`,
  `priceFor`, `ALL_IN`, `COMPETITOR_STACK`, `COMPETITOR_TOTAL`). Edit prices here.
- **Pricing page** (`pages/marketing/Pricing.jsx`) is **calculator-first**: the
  `PricingCalculator` (module picker, live annual total with the bundle discount)
  is the main tool, plus a module price list, a **competitor cost comparison**
  ("One platform. One price.": the all-in BC price vs a stack of real competitors
  with their own published prices, ClubStats / Pitchero / Canva, summed with the
  `SAVING` highlighted; CricketStatz noted; Better Cricket includes historical
  import where ClubStats charges a one-off fee, `IMPORT_NOTE`) and a modular
  pricing FAQ. All competitor figures live in `pricing.js`.
- **Monthly removed** from the public site (Pricing toggle, Overview snapshot,
  Landing/Features price lines, Terms clause, a blog callout). The dormant
  monthly toggle in `ComparisonTable` was left (no caller enables it). The in-app
  `BILLING_CYCLES` constant remains (a super admin can still record a club's
  billing cycle); `TIER_INFO` and the whole tier model were removed (below).

<!-- END original CLAUDE.md L12511-12539 -->
<!-- BEGIN original CLAUDE.md L12540-12564 -->
## Modular entitlements — tiers retired (v8.12, Jun 2026)

The Good/Better/Best plan tiers are **retired and not returning.** A club's
`module_overrides` (the explicit list of module keys it holds) is now the
**single source of truth** for entitlement, gated only by `subscription_status`
(`backend/app/auth/modules.py::org_entitled_modules` = the module list while the
sub is active, else Core only). Core (BetterStats) is always on and is never a
gateable module.

- **Migration 080** backfilled every club's `module_overrides` from its old tier
  (`best` → all 5, `better` → select+socials, `good` → none) so **no club lost
  access**. Additive and idempotent.
- `organisations.tier` is **kept but deprecated** (no longer read anywhere;
  retained for history, not dropped). Don't read it.
- **Super admins** assign a club's modules via per-module checkboxes
  (`MODULE_TOGGLES` in `lib/modules.js`; **BetterAdmin = fees + comms**) in
  `SuperClubs.jsx` — there's no tier dropdown.
- `/auth/me` + `/auth/login` no longer return `entitlements.tier` (just
  `modules`, `overrides`, `status`, `renewal_date`, `billing_cycle`). Frontend
  gating already reads `entitlements.modules` (`AuthContext.hasModule`).
- **Don't reintroduce** `TIER` / `TIER_INFO` / `TIER_ORDER` / `requiredTier` /
  `tier_modules` / `MODULE_REQUIRED_TIER` anywhere. Locked modules read as
  "add-ons", not a higher tier. (BetterFees membership/fee-schedule *tiers* are a
  different, unrelated feature — leave those.)

<!-- END original CLAUDE.md L12540-12564 -->
<!-- BEGIN original CLAUDE.md L12565-12573 -->
## Version Numbers

Each release lives in its own file under **`frontend/src/data/changelog/`** — never hand-edit `frontend/src/version.js` (it derives `SITE_VERSION` from the highest-sortKey entry in that folder). Drop a new `v-X-Y-Z.js` file when you ship:
- Small fix: `+0.0.0.1`
- Medium change: `+0.0.1`
- Large change: `+0.1`

See "Feature Changelog" below for the file format.

<!-- END original CLAUDE.md L12565-12573 -->
<!-- BEGIN original CLAUDE.md L12696-12700 -->
## Branch

Active development branch: `claude/fix-historical-game-data-QEN3b`
Push to this branch AND to `main` via MCP after each change.

<!-- END original CLAUDE.md L12696-12700 -->
<!-- BEGIN original CLAUDE.md L12701-12707 -->
## Architecture

- **Backend**: FastAPI + SQLAlchemy + PostgreSQL (`backend/`)
- **Frontend**: React + Vite + Tailwind CSS (`frontend/`)
- **API**: Grassroots API proxy (`grassrootsapiproxy.cricket.com.au`) — season-aggregate stats freely accessible; game-level paths exist but the proxy's upstream API key is restricted
- `jsconfig=eccn:true` is a ServiceStack formatting flag, NOT an API key

<!-- END original CLAUDE.md L12701-12707 -->
<!-- BEGIN original CLAUDE.md L12812-12819 -->
## Key Notes

- PlayHQ public game summary API is "not applicable to Cricket" — no scorecards without a partner JWT
- PostgreSQL `ORDER BY year DESC` defaults to NULLS FIRST — always use `.nullslast()`
- API field names: `bowlingEconomyRate`, `fieldingTotalCatches`, no `bowlingOvers` (derive from `bowlingBalls`)
- `Season.year` is NULL when Grassroots doesn't return `startDate` — extract from name (`"Summer 2010/11"` → `2010`) as a fallback
- `stats["player_seasons"]` in sync is `len(player_data)` summed across seasons, i.e. player-season records, not unique players. With 52 seasons × ~3.4 avg seasons/player ≈ 5326 (which Applecross actually shows). Renamed from `stats["players"]` to match what it counts.

<!-- END original CLAUDE.md L12812-12819 -->

## v9.108.4: privacy policy rewrite (2026-10-08)

`frontend/src/pages/marketing/Privacy.jsx` was rewritten to the owner's supplied text, same layout. It now describes the per-person "removed at the person's request" behaviour (hidden at every club, name shown as `********`, club emails stopped, profile kept from coming back) and its limits. The old APP/Privacy Act sentence and the separate OAIC "Complaints" section are not in the supplied text, so they are gone; put them back if the adviser wants them.
