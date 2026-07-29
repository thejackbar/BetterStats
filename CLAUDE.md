# BetterStats — Claude Session Notes

## Admin navigation — module surfaces, and where the Core tools live (v8.82.0, Jul 2026)

The admin app is organised as **module surfaces**: each Better product is a card
on the admin dashboard that opens its own focused sidebar (`ModuleLayout`, a thin
per-module wrapper: `BetterSelectLayout`, `BetterFeesLayout`, `IQLayout`, …). The
shared `components/admin/AdminLayout` is now just the **app chrome** — Dashboard,
Setup Wizard, the module cards/tiles, and the Account group (Activity Log, Plan &
Billing, Settings, Users) — plus the **Better HQ** section for super admins
(grouped via `lib/superNav.js`, see the Better HQ note if present).

- **BetterStats (Core) is its own surface** now (it used to be a loose pile in the
  shared sidebar). `BetterStatsLayout` (green, `moduleBrand('stats')`), home at
  `/admin/betterstats` (`BetterStatsHome`). GROUPS: **Club Data** (Matches,
  Players, Import Players, Seasons), **Data Import** (Data Sync, Import Stats,
  Upload Scorecard, Manual Entries, Milestones, Partnership Records), **Clean Your
  Data** (Merge Players, Merge Grades) and **Records & content** (Awards, Award
  Types, Yearbooks, Saved Reports, Sponsors). Group `key`s (`data`/`ingest`/`tidy`/
  `records`) are stable and drive the `:group` URLs, so the display labels can be
  renamed without moving a route.
- **BetterClubManager** (provisional name) is an **upcoming** back-office surface,
  NOT a live Core tile. It shows as a **"Coming soon" card under BetterAdmin**
  (`BetterAdminHome`) — greyed/non-clickable for everyone except **super admins**,
  who get a live "Preview" link. Its surface (`BetterClubManagerLayout` indigo,
  home `/admin/betterclub` `BetterClubManagerHome`) and every one of its tool
  routes (`/admin/committee`, `/admin/volunteers`, `/admin/families`,
  `/admin/qualifications`, `/admin/member-portal`, `/admin/events`, `/admin/assets`,
  `/admin/club-diary`) are gated `requireRole="super_admin"` in `App.jsx`. So
  ordinary club admins currently have **no access** to these tools — deliberate,
  until BetterClubManager launches. It is therefore NOT in `CORE_TILES` /
  `dashboardTiles()` (off the dashboard, sidebar and module switcher).
- **The one Core surface tile** (BetterStats) lives in `CORE_TILES` in
  `lib/modules.js` — deliberately OUTSIDE `MODULE_INFO` (which feeds
  entitlement/billing). `dashboardTiles()` returns `[BetterStats, …paid modules…]`;
  `alwaysOpen` keeps it entitled for every admin.
- **Two-level home, one config.** Each layout exports a `GROUPS` array (key,
  label, icon, `desc`, and `items` each with `to`/`label`/`icon`/`cap`/`desc`).
  It drives all three views so nothing drifts: the surface home
  (`/admin/betterstats`) shows one card per group; a group card opens
  `/admin/betterstats/:group` (one card per tool, with descriptions); and the
  sidebar flattens `GROUPS` into headed sections. `components/admin/ModuleHub`
  renders the home + group pages from `GROUPS`; the `Home` page components pass
  `groupKey` from the `:group` route param. BetterClubManager's Member Portal is
  inserted into its People group only when the flag is on (`withPortal`).
- **`components/admin/HubCard`** is the one house-style menu card (matches
  BetterAdmin's sub-cards): name (+ badges) and arrow on top, description below,
  accent-tinted; `state: 'open'` is a link, `'soon'` is a greyed non-clickable
  teaser. Used by `ModuleHub` (BetterStats overview + group pages), the
  BetterSelect Overview tool grid, and the BetterClubManager "Coming soon" card.
  A `title` starting with "Better" gets the coloured-suffix wordmark. **Use HubCard
  for any new menu card** so the look stays consistent.
- **URLs are unchanged** — the tool pages kept their existing routes
  (`/admin/players`, `/admin/committee`, …); only the layout wrapper each page
  renders changed (`AdminLayout` → the module layout). So bookmarks/links still
  work and no route moved.
- `ModuleLayout`'s `nav` now supports `{ heading }` separators (grouped sidebar);
  a heading with no visible items under it after cap-filtering is dropped.
- **Adding a Core tool**: put the page under the right module layout wrapper and
  add it to the correct group's `items` in that layout's `GROUPS` (that's all —
  the sidebar nav, the group page and the overview count all derive from it).
  Don't add Core tools back into `AdminLayout`'s `NAV_SECTIONS` — that's
  chrome-only now.
- **Yearbooks** (`/admin/yearbook`, `AdminYearbook`) is still a standalone
  full-page editor with no surrounding sidebar (it always was); the BetterStats
  nav links to it but the page itself doesn't wrap in `BetterStatsLayout`.

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

## Public Domain

The canonical public domain is **`https://betterat.cricket`** (no `www`), the **BetterCricket** brand. The brand name is written **as one word, "BetterCricket"** (Jun 2026 — was the two-word "Better Cricket"); keep it one word in all user-facing copy, page titles, OG/social cards, metadata and the `BRAND` constant in `frontend/src/data/marketing.js`. The module names stay camelCase (BetterStats, BetterSelect, BetterSocials, BetterAdmin, BetterIQ — **BetterStats remains the Core module name**), and the trading company stays **BetterSports**. A permanent redirect from the old `betterstats.cricket` to `betterat.cricket` (301 for GET/HEAD, 308 otherwise) is **prepared in `cloudflare-worker/worker.js` but not yet deployed**; once it ships it consolidates the old domain's link equity onto the canonical. Until then both hostnames serve the same app, so links work on either. The older `betterstats.bltbox.com` domain is retired.

- **Everything public points at `betterat.cricket`** (keep new public-URL references there): `frontend/src/hooks/usePageMeta.js` (`BASE_URL`), `frontend/index.html` (`og:url`, canonical, JSON-LD), `frontend/public/{llms.txt,robots.txt,sitemap.xml,site.webmanifest}`, the backend `routers/seo.py` (`SITE`, the live sitemap + robots nginx proxies), `routers/og_preview.py` (`SITE`), `config/settings.py` (`public_base_url`, the email unsubscribe link), the `deploy.sh` health check, and the `tools/sync_watch.py` default base.
- **Email — one address everywhere: `support@bettersports.com.au`** (Jul 2026, was `cricket@bettersports.com.au`; before that a `noreply@betterstats.cricket` From plus a `betteratcricket@gmail.com` reply-to/contact). It's the default reply-to (`config/settings.py` `email_reply_to`, from-name "BetterCricket" — `email_from_address` is a separate deliverability-only sending address, currently `notifications@betteratcricket-comms.work`) AND the public contact address shown across the site: `SUPPORT_EMAIL` in `frontend/src/data/marketing.js`, the hardcoded copies in `frontend/index.html` (JSON-LD), `frontend/public/llms.txt`, `backend/app/routers/og_preview.py`, `backend/app/routers/self_serve_trial.py`, and the marketing/login pages (Privacy, Terms, Contact, FAQ, Login, MarketingFooter). **DNS still to do**: for sent mail to pass authentication, `bettersports.com.au` needs SPF/DKIM/DMARC set up (the records used to live on `betterstats.cricket`); until then sent mail may be flagged as spam. `email_provider` defaults to `console`, so nothing sends until a provider is configured anyway.
- `CORS_ORIGINS` should be `https://betterat.cricket` in the server `.env`, but CORS is dormant in practice: the frontend calls the API via a same-origin relative `/api` path, so cross-origin checks never fire. Updating it is hygiene, not a functional requirement.
- `betterat.cricket` social link-preview cards are server-rendered for the marketing routes by `backend/app/routers/og_preview.py` (`MARKETING_PAGES`), so per-page OG tags work for crawlers that do not run JS; keep that map in sync when marketing routes change.
- `cloudflare-worker/worker.js` is a pure old-domain redirect, **ready but not yet deployed** (its old OG-injection job is handled by `og_preview`). When ready, `wrangler deploy` it and keep the Cloudflare route `betterstats.cricket/*` active.

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

## Version Numbers

Each release lives in its own file under **`frontend/src/data/changelog/`** — never hand-edit `frontend/src/version.js` (it derives `SITE_VERSION` from the highest-sortKey entry in that folder). Drop a new `v-X-Y-Z.js` file when you ship:
- Small fix: `+0.0.0.1`
- Medium change: `+0.0.1`
- Large change: `+0.1`

See "Feature Changelog" below for the file format.

## Club Setup Wizard (v8.70.0, Jul 2026)

The Phase-15 checklist modal (`OnboardingWizardModal.jsx`, deleted) grew into a
full-page, whole-platform **Setup Wizard** at `/admin/setup(/:stepKey)`
(`frontend/src/pages/admin/setup/` — `SetupWizard.jsx` + `SetupInlineSteps.jsx`
+ `SetupModuleSteps.jsx` + `setupUi.jsx`). 28 steps in 7 groups (data in →
data tools → BetterSelect → BetterSocials → BetterAdmin → BetterIQ →
BetterFantasy), same table/flag/router as before:

- **Entry points (v8.70.1)**: a permanent **"Setup Wizard" sidebar item** (top
  unheaded section, beside Dashboard, every role) plus the header SETUP GUIDE
  shortcut (any role whose `/state` fetch succeeds — a super admin needs an
  acting-as club). The `onboarding_wizard_enabled` platform-flag gate was
  REMOVED from the router (the flag + `require_onboarding_wizard_enabled` in
  `auth.py` still exist but gate nothing — the General Settings toggle is
  inert for the wizard now). Sidebar sections (and Better HQ links, after
  Platform Overview) are kept in ALPHABETICAL order by label — keep it that
  way when adding links.
- **Auto-open is conservative** (because the gate is gone): fresh-login
  navigation to `/admin/setup` fires only for (a) a brand-new club — no
  successful full sync — that hasn't dismissed it, or (b) the one-shot
  Decision-11 reopen-after-sync, only if stored progress exists (`engaged`),
  so long-established clubs are never yanked into setup. Super admins are
  never auto-navigated.
- **Backend** `routers/onboarding_wizard.py`, club-admin auth. `GET /flow` is the wizard:
  step registry (`GROUPS`) filtered to the club's entitlements, per-step
  auto-detection (`_detect_steps` — cheap org-scoped EXISTS: logo set, sponsor
  rows, merge_logs, fee_schedules, fantasy season/pool, a `ready` dossier…),
  and it **persists newly-detected completion into `completed_steps`** so the
  cheap `GET /state` summary (AdminLayout polls it every mount) reads stored
  state only. `POST /steps/{key}` takes `{done?, skipped?}` (mutually
  exclusive; detection beats a skip). `skipped_steps` column = migration 157
  (+ lifespan mirror). Steps the DB can't see (socials palette → localStorage,
  the review-only fantasy steps) are manual-mark only.
- **Sync gating**: the "Tidy your data" group locks until a successful full
  pull. `_sync_ready` now accepts `org_full` **or** `org_hard_refresh` — the
  old checklist only looked for `org_full`, so a club whose first complete
  pull was a Full Rebuild never unlocked those steps (fixed here).
- **Hybrid steps**: simple actions run inline through their EXISTING endpoints
  (hard-refresh + sync-log polling, branding, sponsor create, fixture
  sync, squad seed/auto-assign, availability self-serve, website enable, comms
  sender settings, Square/Xero connect [live status + the OAuth connect-url,
  stamping the return flag before redirecting], fantasy season/pool); complex
  tools are link-out steps. Link-outs stamp `sessionStorage.bs_setup_return`
  and `SetupReturnBar.jsx` (a **floating bottom pill**, gradient-ringed,
  mounted in `ProtectedRoute` beside `TrialBanner` so it covers module
  layouts and OAuth round-trips too) offers "back to setup". Vital steps
  (full_rebuild, merge_players, merge_grades) get a concrete-consequences
  confirm before skipping. **The branding step edits `theme_config`
  (accent/accent2, merged over the stored config), NOT the legacy
  `primary_color`/`accent_color` columns** — theme_config is what actually
  themes the site (v8.70.2 fix); logo upload goes through `ImageEditorModal`
  (crop + background removal) before saving.
- **IQ pre-warm** (`services/iq_prewarm.py`; `GET/POST /iq/opposition/prewarm*`):
  builds every known opponent's dossier for chosen grades **one at a time** in
  a detached task (in-process progress dict, ≤40 opponents, 5-min per-build
  timeout), reusing `iq_opponent.get_or_start_dossier` — a fresh dossier is a
  cache hit, so re-runs are cheap. Grade options come from the latest season
  year with per-grade distinct-opponent counts; busiest 3 pre-ticked.
- Old `explore_*` step keys may linger in stored `completed_steps` —
  harmless, ignored by the registry.

### Periodic setup reminder (v8.70.3)

A permanently-dismissed `SetupReturnBar` pill (see above) shouldn't mean a
half-finished club setup is forgotten forever. `SetupProgressReminder.jsx` —
a small bottom-RIGHT toast (distinct corner from the pill, which is
bottom-centre) — fires on **every 5th landing on the bare `/admin` dashboard**
while any step is still neither done nor skipped, **regardless of the
wizard's own `dismissed_at`** (dismissing the pill/wizard only stops the
should_auto_open navigation, not this nudge). Counted client-side
(`localStorage['bs_setup_reminder_visits_<user.id>']`, since `AdminLayout`
remounts on every navigation and this is a UX nicety, not real progress
state) inside the same effect that already fetches `GET .../state` on every
mount — no extra request. Auto-hides after ~12s or on its own ✕; dismissing
it only clears this one instance, it reappears on the next 5th-visit tick.
`GET .../state` now also returns `addressed` (done+skipped) alongside `done`/
`total`, so the toast can say how many steps are left.

### Secondary accent, luminance-guarded (v8.70.2)

`theme.js::safeAccent2(accent2, accent, mode)`: many clubs' second colour is
black or white, which vanishes against the matching theme background.
`buildThemeCss` now emits per-theme `--pb-accent-2-safe`, a per-theme
`--pb-gradient`, and a per-theme `--pb-chart-wickets` (all guarded: near-black
falls back to the PRIMARY accent on dark, near-white on light; the raw
`--pb-accent-2` stays available). Consumers of the pairing: Navbar active-tab
underline, `StatCard`'s accent variant (small gradient bar), the wizard
progress bar + return pill, plus the pre-existing `.pb-gradient` utilities /
presskit. **Paint club colour pairs with `var(--pb-gradient)` or
`--pb-accent-2-safe`, never raw `--pb-accent-2`, unless you know the surface.**

## Awards — default templates (v8.28.0, Jun 2026)

Award catalogue lives in two tables (created in `main.py` lifespan, not Alembic):
`org_award_definitions` (the per-club catalogue that drives the dropdowns; clubs
rename via `display_name`, hide via `active`) and `player_achievements` (the
records). Templates are built in `backend/app/routers/award_definitions.py`:

- **`STARTER_TEMPLATE`** (`_build_starter_template`) — the **default for new
  clubs**, ~55 rows, club-agnostic: whole-club Season awards, a 1st/2nd/3rd XI
  block, generic `Premiership › Team`, the universal Milestone ladders, a
  `Committee` role list, Hall of Fame + Life Membership. No WASTCA/WABCC/PSWL,
  no OD/ICL/Colts ladder.
- **`GLOBAL_TEMPLATE`** (`_build_global_template`) — the old ~450-row
  comprehensive WA list. Kept as the opt-in **'comprehensive'** preset only.
- **`APPLECROSS_TEMPLATE`** — ACC's exact trophy names, matching their existing
  `player_achievements` values. Seeded for slug `applecross` on startup; not in
  the picker.
- `/award-definitions/seed?template=` reads the `TEMPLATES` map
  (`starter`|`comprehensive`|`global`(alias)|`applecross`); unknown → starter.
  Frontend auto-seeds **`starter`** on first visit to the definitions page when a
  club has zero defs, and the "Reset to Template" control offers Starter vs
  Comprehensive.

Seeding only fills an **empty** org (`seed_org_definitions` is a no-op if any def
exists), so Applecross and any already-seeded club are never touched. The
hardcoded `ACHIEVEMENT_TREE` in `frontend/src/lib/achievementOptions.js` (+ its
Python mirror in `routers/achievements.py`, used by the CSV import template) is
still the ACC-flavoured deep fallback shown only when an org has no defs at all —
a leaner import template is a possible follow-up, not done here.

## Branch

Active development branch: `claude/fix-historical-game-data-QEN3b`
Push to this branch AND to `main` via MCP after each change.

## Architecture

- **Backend**: FastAPI + SQLAlchemy + PostgreSQL (`backend/`)
- **Frontend**: React + Vite + Tailwind CSS (`frontend/`)
- **API**: Grassroots API proxy (`grassrootsapiproxy.cricket.com.au`) — season-aggregate stats freely accessible; game-level paths exist but the proxy's upstream API key is restricted
- `jsconfig=eccn:true` is a ServiceStack formatting flag, NOT an API key

## Data Source Topology (May 2026 investigation)

Cricket Australia hosts club cricket data across **two separate backends**, both reached via `play.cricket.com.au`:

1. **PlayHQ** (post-migration, ~2023+): GUID-keyed. Reachable via:
   - Partner REST API `api.playhq.com/v1/...` — public key only returns ~3 seasons (Summer 23/24, 24/25, 25/26). `/teams` is 401 with public key. `/grades` (org-level) is 404. `/v2/games/{id}/summary` works for IDs in this universe.
   - Public GraphQL `api.playhq.com/graphql` — `discoverGame` works for current games, `discoverGradeFixture` and `discoverTeamFixture` 500 with "Bolt adapter map not found" (require session/cookie auth the website holds). Schema introspection disabled.

2. **MyCricket / Pulselive Play Community** (legacy / pre-migration): GUID-keyed throughout (different namespace from PlayHQ). Data confirmed to reach back to at least 1975. Reachable via the same `grassrootsapiproxy.cricket.com.au` host we already use — just on a different path prefix than the proxy's restricted endpoints:
   - **`/scores/grades/{grade_id}/matches`** — all matches in a grade. ✓ unauthenticated. **Primary match discovery path** — grade_id is the same UUID as `grades.id` in our DB, works for all seasons including pre-2000. Confirmed 200 OK for a 1996 Applecross 8th Grade game.
   - **`/scores/teams/{team_id}/matches`** — list of matches a team played that season. ✓ unauthenticated. Secondary/fallback; team IDs require a fixturesladders call first.
   - **`/scores/matches/{match_id}?responseModifier=includeScorecard`** — full scorecard (batting, bowling, fielding, fall-of-wickets). ✓ unauthenticated. Returns **HTTP 204 No Content** for post-migration PlayHQ-namespace IDs, which is a clean "not mine" signal.
   - **`/fixturesladders/grades/{grade_id}/ladders`** — grade ladder (win/loss/points standings). ✓ unauthenticated 200 OK. Useful for future ladder feature — not yet synced.
   - **`/fixturesladders/grades/{grade_id}`** — grade metadata. ✓ unauthenticated 200 OK.
   - `participantId` in the response **is the same GUID as `players.id` in our DB** — no extra mapping needed.
   - The restricted paths (`/fixturesladders/games/{id}`, `/participants/games/{id}/batting`, `/scorecards/...`) all return `403 "API key does not have access"`. **Don't try those.** The `/scores/*` path is the one that works.
   - `apiv2.cricket.com.au` — has Swagger UI at `/`, OpenAPI at `/openapi.json`. Looks promising at first glance but is the **international** stats API (Ashes, BBL, Sheffield Shield) — does NOT contain club cricket data. Skip.
   - `api.playcommunity.pulselive.com` — verified `/registration` only; broader scope unknown.
   - `crm-communitycricket-cdn.cricket.com.au` — referenced by the bundle, scope unknown.

   **How to find the real API call**: the play.cricket.com.au website is a CSR Pulselive SPA (`window.API_ACCOUNT = 'playcommunity'`, bundle at `/resources/playcricket/v1.28.6/scripts/bundle-es.min.js`). HTML is just a shell. Anonymous server-side curls of `ca.playhq.com/*` and JS bundles get 403'd. Network-tab the request from a real browser load to recover the URL — that's how we found `/scores/*`.

3. **Pagination quirk**: PlayHQ's `links.next` is sometimes returned forever even when the data is exhausted (observed paginating past page 1100 on a single grade). Our pagination loops cap at MAX_PAGES=200 and stop on the first short batch — never trust `links.next` alone.

4. **Org duplication trap**: `upsert_organisation` keys on whatever `id` is passed in, so calling sync with a PlayHQ UUID after the org was already created with a Grassroots GUID would create a duplicate row (one with `playhq_id=NULL` matching the other org's `id`). Detected May 2026 for Applecross, cleaned up via direct DELETE. Guarded since commit ceadd84 — layered check on (a) primary id, (b) existing org's `playhq_id` matching incoming id, (c) name match (case-insensitive) before inserting.

## UK Expansion — Play-Cricket Data Source (Jun 2026 investigation)

UK club cricket runs on **Play-Cricket** (ECB), a **server-rendered Rails** app, one subdomain per club (`{club}.play-cricket.com`). The pages carry **no client JSON** — a browser network capture shows only telemetry (New Relic `bam.nr-data.net`, GA4 `g/collect`, OneTrust consent), never data. **Don't scrape the HTML** (brittle + terms breach). Full investigation: **`docs/uk-play-cricket-data-source.md`**.

- **The data tap is the official Play-Cricket API v2**: `https://play-cricket.com/api/v2/*.json`, **token-gated per club** (`api_token` required on every call; a club admin signs an agreement → key issued). Key endpoints: `result_summary.json?site_id=&season=` (discovery + `last_updated`), `match_detail.json?match_id=` (**full scorecard, both teams**), `matches.json` (fixtures), `league_table.json?division_id=` (ladders), `players.json`/`teams.json`. Integrator pattern = poll `result_summary`, fetch `match_detail` only when `last_updated` changes — same shape as our CA grade→matches→scorecard flow.
- **NO statistics endpoints** — *"a club can access the full scorecards of their games but we do not offer endpoints for statistics."* So unlike AU (CA aggregate API → `player_season_stats`), **the UK has scorecards only and we must compute every season aggregate ourselves** (promote the "Fix Missing Totals" rollup to primary). `match_detail` maps almost 1:1 onto our tables (`games`/`grades`/`players`/`batting_innings`/`bowling_spells`/`fielding_stats`/`bowler_wickets`/`partnerships`/FOW) — see the schema map in the doc.
- **IDs are integers, not GUIDs** — slot into the existing per-club collision scheme (raw id in `grassroots_id`, `id = uuid5(org, raw_id)` on collision). **Season** is a query param, not in the payload — derive `Season.year` from `match_date` (DD/MM/YYYY).
- **Bonus data vs AU**: `match_detail` carries **toss** (`toss`/`toss_won_by_team_id`/`batted_first`) and **extras** (byes/leg-byes/wides/no-balls/penalty) — both unavailable on CA's `/scores/*`, so UK data unlocks BetterIQ toss/captaincy analysis (brief §4) and exact score reconstruction.
- **Token scope** (technical reach ≠ contractual scope): a token authenticates *you*; the `site_id`/`match_id`/`division_id` you pass picks *whose* data. Published cross-club data *appears* broadly readable (any `site_id`/`match_id` — community-reported via `pyplaycricket`, not live-tested), but you're contractually data controller for **your own club only**. **No stats endpoint for anyone** (own or other clubs — always compute from scorecards). In-scope cross-club data = the **opponent half of your own games** (`match_detail` has both teams) → full head-to-head scouting; a **full** opponent dossier (their form vs everyone) needs the opponent's token, a **league-site token** (one token → every club in the competition, via `division_id`/`cup_id`), or partner access. **Onboarding a league is the highest-leverage in-scope unit** — restores AU-like "scout anyone in the comp". Private/unpublished fields (PII, unpublished matches) presumably own-site only — unverified without a token. **REJECTED shortcut**: reusing ONE shared club key for all English clubs (token authenticates us, `site_id` picks the data) — unverified technically, breaches the host club's agreement, single point of nationwide failure, and UK-GDPR-unlawful (processing other clubs' members — incl. children — with no lawful basis). Use league/partner tokens, never a shared club key. (Doc §6.)
- **Access policy & strategy**: API is for **clubs/leagues to export their own data**; third-party commercial use needs an ECB exception ("compelling reason … well-established customer base"). The ECB's own advice is the **BYO-token model** — *"allow clubs to add in their own API tokens for their specific data while you grow"* — then approach the helpdesk at "hundreds of clubs / thousands of users." So **Phase 1 = per-club token** (add `playcricket_api_token`+`playcricket_site_id` to the org; new token-authed `playcricket_scores_client`; no ECB relationship needed), **Phase 2 = partner access** (our AU customer base is the exception lever). Not real-time / low-traffic only; minimise retained PII (UK GDPR — we'd be a processor).

## Sync Architecture

### Admin UI button names (Sync Actions card)

The three buttons on `/admin/sync` map to backend endpoints as follows. When
the user says one of the UI names, this is what they mean:

| UI button             | Backend route                                  | What it does                                                        |
|-----------------------|------------------------------------------------|---------------------------------------------------------------------|
| **Sync Now**          | `POST /organisations/{id}/sync`                | Pull latest games & stats. Safe to run anytime — the weekly job.    |
| **Fix Missing Totals**| backfill aggregates endpoint (`/club-admin/...`) | Recomputes `player_season_stats` from existing per-game rows. No CA fetch. Use when a player shows 0 matches/runs despite having scorecards. |
| **Full Rebuild**      | `POST /club-admin/hard-refresh`                | Wipes per-game tables and re-pulls everything from CA. Slow (hour+). Use after sync-logic changes. |

(Renamed Apr–May 2026; old labels were "Sync" / "Backfill Aggregates" /
"Hard Refresh". Internal endpoint names and the `kind` field on `sync_runs`
are unchanged.)

- **Full sync** (`POST /organisations/{id}/sync`) / **Hard refresh** (`POST /club-admin/hard-refresh`): scheduled weekly + on-demand. Two passes:
  1. **Grassroots aggregate** (`playhq_client.get_*_stats`) — season totals for all 52 seasons. Source of `player_season_stats`.
  2. **Grassroots scores** (`grassroots_scores_client` + `sync_grassroots_game_level_data`) — game-level scorecards confirmed back to at least 1975. Iterates grades from DB (all seasons, all grades), calls `/scores/grades/{grade_id}/matches` for each to get match IDs, fetches `/scores/matches/{id}?includeScorecard` for each. Skips PHQ-namespace IDs that 204. Per-game session pattern to avoid async session deadlock. Uses `session.get(Grade, ...)` to avoid stale-cache FK violations. No longer depends on fixturesladders for discovery, so pre-2000 seasons are fully covered.
- **PlayHQ Partner game-level sync** is **removed** from `sync_organisation` (May 2026 audit). The public API key only exposed ~3 seasons of history vs Grassroots's 50+, AND because the same physical match has different UUIDs in PHQ vs Grassroots, running both produced duplicate batting rows. `sync_game_level_data`, `_backfill_player_playhq_ids`, and `process_game_updated_webhook` were deleted from sync.py — see git history if ever needed again.
- **Per-player deep sync**: `deep_sync_player()` — admin-triggered, still present but pre-dates the Grassroots unlock. Calls PlayHQ Partner API; only covers ~3 recent seasons. Low value now that Grassroots covers everything including 25/26.
- **Sync runs persisted** in `sync_runs` table (migration 005). `update_sync_run` and `finish_sync_run` MERGE stats into the existing row (don't replace) so sub-phases accumulate. Stale `running` rows are marked `error` on backend startup.
- **`owns_run` gotcha**: inside `sync_organisation`, `owns_run = run_id is None`. So when a caller passes `run_id` (e.g. the hard-refresh handler that calls `start_sync_run` itself), sync_organisation only ever calls `update_sync_run` on success and NEVER `finish_sync_run`. The **caller** is responsible for finishing the run. The hard-refresh handler (`club_admin.py:_run`) used to only call `finish_sync_run` in the exception branch, so every successful hard-refresh sat at `running` forever — fixed May 2026.
- **Merge-aware GR sync** (May 2026, v3.0.2): `sync_grassroots_game_level_data` now builds a `merged_away: removed_player_id → keep_player_id` map from `merge_logs WHERE undone_at IS NULL` (with transitive resolution) during discovery. Each of the five `participantId` consumers (batting, bowling, fielding, fall-of-wickets, derived partnerships) checks `known_player_ids` first and falls back to `merged_away` before skipping. Without this, scorecards referencing a previously-merged player_id silently dropped those stats, leaving the kept player short on innings/wickets/catches/fall-of-wickets.
- **Aggregate-sync merge map** (v3.0.2.1) was previously NOT filtering `merge_logs` by `undone_at IS NULL` AND was building only a single-hop redirect dict. Two consequences:
  1. Stale entries (e.g. a merge that was reversed by a later re-merge in the opposite direction) poisoned the map — observed for Cooper Jnr (`92F`) where a 04:59 merge `KEEP=09c REMOVED=92F` redirected his aggregate stats to `09c` (which no longer exists), silently dropping every season except those keyed under a different ID that resolved cleanly. Symptom: per-game `batting_innings` correct (different sync path), but `player_season_stats` summary showed only 3 seasons.
  2. Multi-step merges (A→B→C) would redirect A to B only; if B was later merged away, the insert hit the safety net and got dropped.
  Fix: filter by `undone_at IS NULL` and resolve transitively with cycle break — same pattern as the GR sync function. Manual cleanup also needed for already-poisoned rows: `UPDATE merge_logs SET undone_at = NOW() WHERE undone_at IS NULL AND removed_player_id IN (SELECT id FROM players)` to mark entries where the "removed" player is back in the players table.
- **"Absent" / "DNB" dismissals aren't innings** (v3.0.2.2): GR scorecards mark a batter "Absent" or "Did Not Bat" with `dismissalTypeId > 0` but no ball faced. CA's aggregate API correctly excludes these, but our per-game parser used to insert `batting_innings` rows for them — causing per-game counts to over-shoot aggregate by 1-2 rows for any player who's ever been Absent. Now filtered in both the batting-row insert and `_derive_partnerships_grassroots` (since absent batters were never at the crease). Existing over-counted rows need a one-time `DELETE FROM batting_innings WHERE dismissal_type IN ('absent', 'did not bat', 'dnb')` to clean up.
- **GR scorecard team-name parsing**: `isHome` lives on `matchSummary.teams`, NOT on the top-level `teams` array. Reading from the wrong field is silently OK (no error) but produces empty `home_team`.
- **Caught-behind (caught by the keeper)** (migration 075): **CA does NOT mark the keeper in `dismissalText`** — it reads plain `"c: C Cecchi b: A Ricci"`, no dagger, no `(wk)` (an early assumption that a `†` was present was WRONG — verified against live data Jun 2026: 6597 catches, 0 daggers). The real signal is **structural**: the innings' **fielding rows carry `wicketKeeperCatches`**, so a catch is "caught behind" **iff its catcher is the fielder with `wicketKeeperCatches > 0`** (or a stumping). `sync._innings_keeper_names(inn["fielding"])` builds the keeper short-name set; `sync._caught_by_keeper(dismissalText, keeper_names)` extracts the catcher (between `c` and `b`) and matches it (apostrophe-normalised) against that set. Persists `batting_innings.caught_behind` (nullable bool, surfaced through `v_effective_batting_innings`; manual branch → NULL; kept OFF the `dismissal_type` string so the many "count caught" readers are untouched). `NULL` = unknown → readers treat it as a plain catch. The four call-sites all build `keeper_names` from the same innings' `fielding` rows: the batting insert + `_extract_bowler_wickets` (sync), `backfill_caught_behind`, `iq_opponent` (live dossier) and `games.py` (scorecard opp rows). Readers that split out a "caught behind" slice: `aggregations.get_dismissal_breakdown` (the profile "HOW I GET OUT" donut), `iq_trends.player_deep_dive` (also un-collapsed `_DISM_MAP`, which used to map `"caught behind"→"caught"`, and added the missing short-code keys `c`/`b`/`st`), `yearbooks` season breakdown, and `iq_team` team batting breakdown (`_dismissal_key`, now also short-code-aware). **Backfill history** with `python -m app.scripts.backfill_caught_behind <org_id>` (or `all` / no arg for every org — re-reads scorecards, sets the flag in place; same network cost as a Full Rebuild but only touches `batting_innings.caught_behind`; new games get it automatically on sync).
- **Caught-behind, bowling side** (migration 076): `bowler_wickets.caught_behind` (nullable bool) is the mirror — set in `_extract_bowler_wickets` via the same `_caught_by_keeper(dismissalText, keeper_names)` on the `method == "caught"` branch (keeper_names from that innings' fielding rows). Splits the "HOW I TAKE WICKETS" donut (`aggregations.get_bowling_dismissal_breakdown`), the `iq_trends.bowler_deep_dive` scouting note, `iq_team._wickets_quality` (team "how we take wickets"), and the **live opponent dossier** (`iq_opponent` matches the opponent batter's catcher against our keeper in the live scorecard; `_DISMISSAL_ADVICE["caught behind"]` now fires, `DOSSIER_VERSION` bumped to 4 so caches rebuild). `bowler_wickets` is read directly (no effective view), so no view change. **Backfill** by re-running `python -m app.scripts.rebuild_bowler_wickets <org_id|all>` (re-derives the table with the flag). Also split: `iq._our_bowler_dominance` `how` array (matchup dismissal methods) and the **match scorecard** — `games.py` returns `batting_innings.caught_behind` on each of our batters' rows and `MatchScorecard.fmtDismissal` shows "(wk)" when caught-behind isn't already daggered (our players' live-enriched text and opposition rows already carry the `†` straight from the scorecard). NOT split (deliberate, low value): StatLab's derived caught/catcher leaderboards.
- **Fielding catches vs WK catches are fully held** — `fielding_stats.catches`/`catches_wk` per-game (from the scorecard's `wicketKeeperCatches`/`totalCatches`), `player_season_stats.catches`/`catches_wk`/`catches_non_wk` per-season (from `fieldingTotalCatches`/`fieldingCatchesWK`/`fieldingCatchesNonWK`). Outfield = `catches − catches_wk`. Split is shown on PlayerProfile/Leaderboard/TeamDetail/Yearbook/PlayerComparison/ShareCard/TeamAnalysis, plus (v8.5) BetterIQ Player Trends, the shared `PlayerProfilePanel` snapshot (`players.py` now returns `season_catches_wk`), AdminManualEntries review tables, and StatLab (`catches_wk`/`catches_non_wk` metrics). Combined-only surfaces that stay combined **by design**: catches milestones, player rankings, MVP/all-rounder/dismissals composites. `player_season_grade_stats` stores combined catches only (count-only use; can't back a grade-filtered WK split).

## PlayHQ Partner API — May 2026 Audit

**Finding**: Grassroots `/scores/*` IS returning scorecards for recent seasons (25/26 confirmed). The "204 for post-migration games" gap is minimal in practice — Applecross's May 2026 hard refresh got 4204 GR matches, 3947 new games, across all seasons including recent ones. The Partner sync was not needed.

**What was removed (May 2026)**:
- `sync_game_level_data()` — the disabled PHQ Partner game-level sync (was called with `all_games=[]`)
- `_backfill_player_playhq_ids()` — PHQ ID backfill from game appearances, never called in sync flow
- `process_game_updated_webhook()` — empty stub

**What was kept (still live)**:
- `deep_sync_player()` in sync.py — admin-triggered per-player resync via Partner API; low value now, but still callable from admin UI
- `suggest_phq_ids()` in sync.py — powers the "PHQ ID Match" admin page (`/admin/phq-match`)
- `playhq_partner_client.py` — still used by games router (live scorecard view for the rare Partner-only games), records router, and organisations router
- `playhq_id` on Player/Organisation models — retained as nullable legacy field; harmless and used for display in admin

**Data layer summary**:
- Season-aggregate stats (`player_season_stats`): Grassroots aggregate API → all 52 seasons ✓
- Game-level stats (`batting_innings`, `bowling_spells`, `fielding_stats`): Grassroots `/scores/*` → all seasons including 25/26 ✓ (204 gap is minimal)
- Live scorecard view for Partner-only games: PlayHQ Partner API via games router (rarely hit)

## Super Admin Club Delete — soft-delete + FK cascade fix (Jul 2026)

**Symptom**: clicking "DELETE PERMANENTLY" on a club (Super Admin → All Clubs) looked like it succeeded (no error surfaced), but the club was still there afterwards.

**Root cause**: `DELETE /club-admin/super/clubs/{id}` deletes `organisations`, relying on `ON DELETE CASCADE` FKs to remove everything downstream (seasons → grades → games → per-game stat rows). Live logs showed the real error: `ForeignKeyViolationError: ... "partnerships_game_id_fkey" ... Key (game_id)=(...) is not present in table "games"` — `partnerships.game_id` was **not actually `ON DELETE CASCADE` in the live database**, even though `app/models/db.py`'s ORM column has always declared `ondelete="CASCADE"`. The model's intent was never applied to the schema — these are pre-Alembic tables (no migration has ever touched these constraints by name), so the drift went unnoticed until a club with real synced data (partnerships rows) was actually deleted. The whole `DELETE` transaction rolled back, which is why it looked like nothing happened.

**Fix (migration 142)**: reconciled the FK on every sibling legacy per-game/per-player stat table sharing the same origin (`batting_innings`, `bowling_spells`, `fielding_stats`, `bowler_wickets`, `game_appearances`, `fall_of_wickets`, `partnerships`, `milestones`, `fee_match_days`) — not just the one that happened to be hit first. Safe on a live, populated table: builds each corrected constraint `NOT VALID` (near-instant) then `VALIDATE CONSTRAINT` separately (a background scan, doesn't block reads/writes), and checks `pg_constraint.confdeltype` first so an already-correct constraint is left alone (cheap no-op on every app-restart re-run via `main.py`'s idempotent mirror).

**Also shipped (migration 143), per direct request**: club "delete" is now a **soft-delete (archive)**, reversible. `organisations.archived_at` (nullable timestamp) — `POST /club-admin/super/clubs/{id}/archive` sets it (no row anywhere is touched), `POST .../restore` clears it. The old hard-delete (`DELETE /club-admin/super/clubs/{id}`) still exists for a genuine permanent purge later, but now requires the club to already be archived first (a speed bump), and is no longer what the UI's "Delete"/now "Archive" button calls. `GET /club-admin/super/clubs` hides archived clubs by default (`?include_archived=true` to show them); `SuperClubs.jsx` has a "Show archived" toggle and a "Restore" action per archived row. Archiving deliberately does **not** touch `is_active` — restoring shouldn't silently flip a state the admin didn't touch themselves.

**Follow-up bug (same day)**: archiving a club then trying to self-serve-register it again under the same CA org id was rejected as "already registered" — `find_matching_organisation` (the shared duplicate-check `sync.py` helper) had no awareness of `archived_at` at all. Fixed with an `include_archived` param (default `True`, preserving `upsert_organisation`'s own dedup guard — it must still find and reuse an archived row rather than creating a second one for the same CA org): `self_serve_trial.py`'s three duplicate-check call sites (`search`, `/prepare`, `/submit`) now pass `include_archived=False`, so an archived club reads as available to register again. `/submit`'s finishing block (alongside the existing `is_active=True`/slug backfill) now also clears `archived_at` — registering a previously-archived club un-archives it, which is what "available to register again" has to mean once submit reaches that point and reuses the row.

## Key Notes

- PlayHQ public game summary API is "not applicable to Cricket" — no scorecards without a partner JWT
- PostgreSQL `ORDER BY year DESC` defaults to NULLS FIRST — always use `.nullslast()`
- API field names: `bowlingEconomyRate`, `fieldingTotalCatches`, no `bowlingOvers` (derive from `bowlingBalls`)
- `Season.year` is NULL when Grassroots doesn't return `startDate` — extract from name (`"Summer 2010/11"` → `2010`) as a fallback
- `stats["player_seasons"]` in sync is `len(player_data)` summed across seasons, i.e. player-season records, not unique players. With 52 seasons × ~3.4 avg seasons/player ≈ 5326 (which Applecross actually shows). Renamed from `stats["players"]` to match what it counts.

## May 2026 Historical Data Fix — Resolution Log

**Problem**: post-migration, every historical game had blank `home_team`/`away_team` AND Jack Barendse had ~280 batting rows instead of the expected 200. Two root causes.

**Fix 1 — duplicate batting rows from running both sync paths**:
PlayHQ Partner game-level sync was disabled in `sync_organisation` (see Sync Architecture above). Same physical match has different UUIDs in PHQ vs Grassroots; the existing-game skip is UUID-based; running both produced duplicate batting rows.

**Fix 2 — `isHome` lookup on wrong field**:
GR scorecard parser was reading `isHome` from the top-level `teams` array — silently absent, so every game's `home_team` was empty. The flag actually lives on `matchSummary.teams`. Fixed and re-parses cleanly.

**Verification (Applecross, post-wipe + hard refresh)**:
- games: 3957 (was 4418 — old number was bloated by PHQ/GR duplicates)
- batting_innings: 41423, bowling_spells: 26862, fielding_stats: 15495
- games with empty home_team: **0**
- Barendse, Jack: **200 batting / 168 bowling / 93 fielding** ✓

**Fix 3 — successful hard-refresh stuck at `running`** (discovered during the verification of Fixes 1+2):
`sync_organisation` only calls `finish_sync_run` when it owns the run (i.e. when called without a `run_id`). The hard-refresh handler owns the run itself but only called `finish_sync_run` in its exception branch. Fixed `club_admin.py::hard_refresh_org._run` to call `finish_sync_run(run_id, stats)` after a successful `await sync_organisation(...)`.

## June 2026 Cross-Club Player Over-Count Fix (v7.32.1)

**Symptom**: a player who turned out for two synced clubs (e.g. Applecross **Cricket Club** *and* Applecross **Junior Cricket Club**) showed his *combined* career on each club's page — 7 ACC matches displayed as 63 (7 + 56 junior).

**Root cause — players have the SAME shared-GUID collision that Seasons already solved.** `players.id` is the raw Cricket Australia participant GUID used as a **global** primary key, but CA reuses one participant GUID for a person across every club they play for. Both clubs' org-scoped aggregate feeds (`/participants/organisations/{org}/...-statistics`) therefore return that one GUID. Whichever club syncs first **creates** the single `players` row (and sets its `organisation_id`); the other club's sync then finds it by PK — `session.get(Player, pid)` is a **global** lookup, not org-scoped (sync.py ~538/558) — and attaches *its* seasons' `player_season_stats` to the same row. Every career query then did `SUM(player_season_stats.matches) … WHERE player_id = :pid` with **no organisation filter**, so the total double-counted across both clubs. (Seasons dodge this via a per-club derived id `uuid5(org, grassroots_id)`; players were never given that treatment.)

**Fix — enforce the invariant "a player's effective season stats are only the rows whose season belongs to the player's own org", once at the view + at every base-table reader that summed by org-*membership* instead of by *season's* org:**
- **Migration 060** redefines `v_effective_player_season_stats` so the base-table branch only emits a row when `EXISTS (player.organisation_id IS NULL OR player.org = season.org)`. This is the single point that fixes **every** view consumer — `get_career_*` / `get_season_by_season` (player profile), `records.py` (club records), `get_player_team_breakdown`'s aggregate count. Non-destructive (filters on read; base rows untouched), so it self-corrects and survives a re-sync — **no data cleanup or re-sync needed**.
- Base-table readers that bypass the view were scoped to the org's seasons individually: `players.py` upcoming-milestones, `sync.py::_compute_milestones` (stops minting inflated milestone rows), `iq.py::_their_key_players`, `statlab.py` (career + per-season + family + minutes), `iq_trends.py` active-players overview, `selection_pool.py` latest-season form snapshot, `club_admin.py` milestone projection.
- **Anti-pattern to avoid in new queries**: summing `player_season_stats` for a player filtered only by `players.organisation_id = :org` (player *membership*) without also constraining the **season** to that org. Read the view, or join `seasons s` and filter `s.organisation_id`. Queries that filter `WHERE s.organisation_id = :org` or `WHERE pss.season_id = <specific org season>` were already correct (yearbooks, iq_trends trajectory/breakout, iq_selection, the sync backfill).

**Deeper fix — per-club player ids (in progress, phased)**: the display scoping above stops a shared CA participant GUID from *displaying* co-mingled, but the second club of a shared GUID still can't see a player's stats at all (they sit on the first club's record — e.g. a junior club showing 30 when the player's junior career is 56, because the 56 live on the senior club's row). Giving players a per-club derived id like Seasons fixes it at the source. Rolled out incrementally so the 50+ single-club orgs are never touched:

- **Phase 1 (migration 062)** — add `players.grassroots_id` (raw CA participant GUID), backfilled from `id` (which IS the raw GUID for every legacy row), + `UNIQUE (organisation_id, grassroots_id)`. Non-breaking; no id changes.
- **Phase 2a (sync.py aggregate pass)** — `_resolve_org_player()` looks a participant up by `(org, grassroots_id)` and mints `id = uuid5(org, guid)` **only when the raw GUID is already a player id in another club** (the real collision); otherwise it keeps the raw-GUID id. So ordinary new players are unchanged and the **game-level scorecard sync (participantId == player id) keeps working untouched**. The aggregate pass deletes+reinserts per season, so a **re-sync moves a shared player's seasons off the first club's row onto his new per-club row** — the second club then shows the right career total. The first club is unaffected (it keeps the raw-GUID id and its own seasons).
- **Phase 2b (done)** — `sync_grassroots_game_level_data` now translates scorecard `participantId` (raw GUID) → per-club `uuid5` id before every game-level insert, so a per-club player gets per-innings rows (batting/bowling/fielding/FOW/partnerships/appearances/bowler-wickets) too. Implemented via a single `_team_pid(guid)` closure + a `pid_by_guid` map built in discovery (and threaded into `extract_bowler_wickets`, whose 3rd arg is now `gate_pids` + a new `pid_by_guid`; `app/scripts/rebuild_bowler_wickets.py` updated to match). **Identity for legacy single-club orgs** (`grassroots_id == id` ⇒ `pid_by_guid[g] == g` ⇒ `_team_pid` returns the same value the old `guid in our_team_pids` checks used), so their game-level attribution is byte-for-byte unchanged. The aggregate pass runs before the GR pass in `sync_organisation`, so the per-club player row exists before its game-level rows reference it (FK-safe). **Still verify on a data copy before prod**: confirm a normal club's per-game counts are unchanged and the shared player's per-game rows land on his per-club id. Game-level only re-attaches on a **Full Rebuild** (the GR sync skips already-synced games), so the cutover for a club with a shared player is Full Rebuild → merge the duplicate.

**Rollout / cutover** (after deploying phases 1+2a):
1. **Re-sync the second club** (Sync Now, or Full Rebuild) — mints the per-club player and moves his aggregate seasons onto it. The club's career number corrects (junior → 56).
2. (After Phase 2b) Full Rebuild the club for game-level consistency.

**⚠️ Do NOT merge the legacy-GUID duplicate into the per-club record when their seasons OVERLAP.** Discovered Jun 2026 on Matthew Watt: the post-migration GUID's per-club record (`eddde526…`, a uuid5 — note the `5` in the 3rd group) already held the **complete** 56-match junior career (CA back-fills full history onto the post-migration PlayHQ GUID). The legacy MyCricket GUID (`09ce6a6c…`, a v4 raw GUID) was a **duplicate of the older seasons** — but under **different season records**, because MyCricket and PlayHQ assign different season GUIDs to the same real season. `merge_players` dedupes by raw `season_id` (admin.py ~205), so it didn't recognise the dup, **moved** the 30 over and the career read **86 = 56 + 30**. Recovery: **undo-merge** (restores 56). The two records can't be cleanly merged until the duplicate *seasons* are reconciled (season-alias / migration-season-dedup is the unbuilt proper fix); the merge is only safe for genuinely **disjoint** registrations.

**`undo-merge` grassroots_id fix** (Jun 2026): the undo re-creates the removed player and **must** set `grassroots_id` (= `id::text`, correct for any legacy raw-GUID player), or the next sync won't find it by `(org, grassroots_id)` and will mint *another* per-club duplicate. Fixed in `admin.py::undo_merge`.

**Anti-pattern reminder**: don't reintroduce a global `session.get(Player, raw_guid)` create/lookup in sync — use `_resolve_org_player`. `players.id` is no longer guaranteed to equal the CA GUID (it's `uuid5(org, guid)` for per-club rows); the raw GUID lives in `grassroots_id`.

## June 2026 Cross-Club Grade Collision Fix (v2.16.1)

**Symptom**: a newly-onboarded club (High Wycombe) showed only the 3 grades *unique* to it (Year 8/9) in the dashboard Grade dropdown and BetterSelect auto-seed, even though it plays ~16 grades. Recent-matches (PlayHQ-partner, live) and the season summary (participant-stats, whole-club) looked correct, so only the grade-scoped surfaces were starved.

**Root cause — grades had the SAME shared-GUID collision Seasons and Players already solved.** A CA **grade is a competition-wide entity**: one grade GUID (`/scores/grades/{id}/matches` returns every match between *all* clubs in it — verified 10 clubs share HW's "1st Grade") is returned by `get_teams` for *every* club in the grade. But `grades.id` used the raw shared GUID as a **global** primary key, and sync's `session.get(Grade, grade_id)` was a **global** lookup — so the **first club to sync a grade created the row, and every later club's sync skipped it**, leaving the grade attached to whoever synced first. Applecross was onboarded before HW, so HW's 12 shared grades (1st/3rd/5th Grade, One Day 2/3/5, Colts, RJR T20, Year 5/6/9-Central) sat on Applecross's seasons; HW only created the 3 Applecross didn't have. The aggregate season stats (`player_season_stats`) survived because they come from the **participant**-scoped stats endpoint (whole club, grade-agnostic), not from grades.

**Fix — per-club grade ids, exactly mirroring the Season/Player scheme** (phased, mint-on-collision so the 50+ single-club orgs are byte-for-byte unchanged):
- **Migration 067** — add `grades.grassroots_id` (raw CA grade GUID), backfill from `id` (which IS the raw GUID for every legacy row), + `UNIQUE (season_id, grassroots_id)`. Non-breaking; no id changes.
- **`sync._resolve_org_grade()`** (mirrors `_resolve_org_player`) replaces the global `session.get(Grade, guid)` skip in the aggregate grade-seeding loop. Looks a grade up by `(org, grassroots_id)`; mints `id = uuid5(org, guid)` **only** when the raw GUID is already a grade in another club; else keeps the raw GUID. `org_grade_map` is built once per sync alongside `org_player_map`.
- **The raw GUID is what every grassroots API call must use** (not the per-club PK). Switched: per-grade stats `gradeId` (sync.py), the scores pass `get_grade_matches` (uses `grassroots_id`; scorecard `grade.id` → per-club id via a `grade_id_by_guid` map so `games.grade_id` is the per-club id), `iq_opponent._target_season_grades`/`_our_games_vs`/`_grade_name`, `ladders.py` (team + grade-ladder), `iq.opponent_ladder`. Every one is `COALESCE(grassroots_id, id)` ⇒ identical for legacy grades.
- **`rebuild_bowler_wickets.py` is unaffected** — it iterates *game* ids and only joins grades via the DB FK.

**Cutover for an affected (2nd+) club**: deploy + migrate, then **Sync Now** (re-runs the aggregate grade-seeding → mints the per-club grades, so the dropdown + per-grade stats fill immediately; the scores pass then discovers the never-before-synced shared-grade games and pulls them). A **Full Rebuild** is the guaranteed-complete version. **Known residue**: a match between two *both-synced* clubs (e.g. HW vs Applecross) is one shared `games.id` (= match GUID) owned by whoever synced it first, so the 2nd club won't get its own row for that one game — pre-existing game-identity limitation, separate from grades; HW-vs-unsynced-club games (the vast majority) are unaffected.

**Anti-pattern reminder**: don't reintroduce a global `session.get(Grade, raw_guid)` create/skip in sync — use `_resolve_org_grade`. `grades.id` is no longer guaranteed to equal the CA GUID (it's `uuid5(org, guid)` for per-club rows); the raw GUID lives in `grassroots_id`, which is what `/scores/grades/{id}/matches`, the ladder API, and the per-grade stats `gradeId` are keyed on.

## BetterFees — Match-Fee Auto-Allocation (v7.32.0, Jun 2026)

A recorded match-fee payment settles a member's games automatically, **oldest game first**. Per-game Paid / Part-paid / Unpaid is **derived on read, not stored** — there is no per-row paid flag any more.

- **Single source of truth**: the sum of a member-season's `match_day` `fee_payments`. `allocate_match_days(charges, match_paid)` in `services/fees.py` walks the games oldest-first (`played_at` nullslast, then `id`), paying each in full while money lasts; the boundary game is `partial`, the rest `unpaid`, and a $0 game (rate $0 / no tier) is `na`. Money left once every game is covered = **credit** ("in the Green").
- `routers/fees.py::get_member` computes this on read and returns per-row `status` + `amount_covered` + `charge`. `_financials` now surfaces `membership_credit` / `match_fee_credit` / `credit` / `in_credit` (overpayment is **no longer clamped to 0**). Buckets are **kept separate** — match-fee credit never offsets membership owing. No tier ⇒ no credit claimed.
- Because status is derived, adding/removing a payment or editing `days_played` re-allocates automatically — **no migration, no stored flag to keep in sync**.
- **Legacy, still live**: the `paid_payment_id` column and the `mark-paid` / `unmark` / `payments/bulk` endpoints still exist and still create `match_day` payments (which feed allocation), but no longer drive the per-row display. The old per-row MARK PAID / UNMARK buttons were removed from the member page in favour of a single "Record match-fee payment" box (`RecordMatchFeeForm`). The bulk-payment page still works (it reads the derived `is_paid` and creates payments).

## BetterMerch — club stock register (v8.18, Jun 2026)

Third module under the **BetterAdmin** umbrella (`MODULE_GROUPS.admin` already
anticipated it; no separate price, the BetterAdmin toggle now covers
`fees`+`comms`+`merch`). Tracks club stock across three category templates on one
engine: **apparel** (sized/coloured variants), **equipment** (quantity OR
individual assets), **food_drink** (canteen/bar, with expiry). Gated by
`require_module("merch")` + the `MANAGE_MERCH` cap. Surface at `/admin/merch`
(`BetterMerchLayout`, BetterAdmin amber via `moduleBrand('merch')`); pages
Overview / Stock / Equipment / Activity / Reports / Square.

- **Migration 083** (mirrored idempotently in `main.py` lifespan): `merch_products`
  (the catalogue line), `merch_variants` (**stock lives here** as a running
  `quantity`; one 'Standard' variant for un-varied products so apparel and canteen
  read through the same code), `merch_movements` (signed in/out audit log:
  received/sold/issued/used/adjustment/stocktake/write_off), `merch_assets`
  (individual high-value equipment: condition + service/replace dates).
- **`services/merch.py`**: `record_movement` (bumps the variant balance + writes the
  audit row, no commit), `merch_alerts` (low-stock / expiring / service-due,
  computed on read, no table), `stock_summary`. `routers/merch.py`
  (`/club-admin/merch`) is products+variants, movements, assets, a player merch
  view, alerts, reports + CSV.
- **Player link** (admin-only): a sold/issued movement carries `player_id` + a
  `paid` flag; outstanding merch money = sum of unpaid movement amounts. Surfaced on
  the admin player profile modal via the `footer` prop added to
  `PlayerProfilePanel.Profile` (`PlayerMerchPanel`), gated on
  `hasModule('merch') && hasCapability(MANAGE_MERCH)`. Never on the public profile.
- **Alerts feed the notification bell**: `notifications.py` count+summary add merch
  alerts when `org_has_module(club,'merch')`. Like the pending-request counts, this
  is current state, not "since last seen".
- **Per-variant pricing + tracking mode (migration 085)**: each variant carries its
  own `unit_cost`/`unit_price` (override of the product default via `_eff_cost`/
  `_eff_price`), so one product holds several priced kinds (e.g. a 4-piece match ball
  and a 2-piece trainer). `merch_products.for_resale` splits stock into bought-to-sell
  (cost + price, sold/issued to members) vs **club-use** consumable (a straight cost,
  no sell price, no owing — e.g. balls); the New Product form defaults equipment to
  club-use. Club-use products drop sold/issued from the movement picker. Report margin
  counts only priced items (a `CASE` in `stock_summary`) so club-use cost doesn't drag
  it down. Money displays two decimals.
- **Category tree (migration 086)**: `merch_categories` is a self-referencing tree
  (≤3 levels) per club, partitioned by the fixed top type (`top_category`); products
  get an optional `category_id`. Created **inline** as items are added (POST
  `/categories` dedupes a same-named sibling). Endpoints `GET/POST/PATCH/DELETE
  /merch/categories` (delete reparents children, nulls products via FK SET NULL). The
  Stock list filters by node+descendants (`_descendant_ids`); reports add `by_item`
  and a rolled-up `by_category_node` (each node carries its whole subtree's totals).
  Frontend `CategoryPicker` is one dropdown (paths like "Balls › Match") + an inline
  "+ New category" with an optional parent. A `CategoryManagerModal` (the "Categories"
  button on Stock) renames/deletes nodes; `POST /categories/seed-defaults`
  (`MERCH_DEFAULT_CATEGORIES`, "Add starter set") seeds a generic one-level set
  (Match attire / Balls / Canteen…), idempotent. The three fixed types stay as the
  template drivers (sizes / expiry / club-use default), separate from the tree.
  Products and individual variants are both editable after creation (product Edit
  modal via the card gear; per-line `VariantEditModal` via the line gear — label/
  size/colour, cost/price, threshold, expiry; quantity stays movement-driven).

### Square POS integration (migration 084, v8.18.1)

One-way mirror, **Square → BetterMerch** (Square's till owns the canteen count).
OAuth code-flow, per club.

- **Migration 084**: `merch_square_connections` (one per club: tokens,
  `location_id`, `sync_enabled`/`sync_sales`, `sales_cursor`, last-sync status),
  plus mapping columns `merch_products.source/.square_object_id`,
  `merch_variants.square_object_id`, `merch_movements.source/.external_ref` (+ a
  partial unique index on `(org, external_ref)` to dedupe imported rows).
- **`services/square_client.py`** (httpx) — OAuth obtain/refresh/revoke, locations,
  `ListCatalog` (ITEMs carry their ITEM_VARIATIONs nested), `BatchRetrieveInventoryCounts`,
  `SearchOrders` (COMPLETED). Host from `settings.square_environment`
  (sandbox vs production). `services/square_sync.py` — catalog upsert → sales import →
  inventory reconcile, **all in ONE transaction** (helpers `flush`, sync commits
  once) so ORM objects don't expire mid-sync (async `MissingGreenlet` trap);
  `ensure_fresh_token` refreshes the 30-day access token within a week of expiry
  (`session.refresh(conn)` after, since that commit expires conn).
- **Double-count design**: inventory count is the source of truth for `quantity`.
  Sales are imported as `sold` movements (real negative delta + revenue), THEN we
  reconcile each variant to Square's current count via a `stocktake` movement. The
  stocktake is a set-to-absolute, not a second decrement, so sales never double down
  the stock; receipts/waste show up as the reconcile delta. Re-runs dedupe sales on
  `external_ref` (`square:{order_id}:{line_uid}`).
- **OAuth**: gated `GET /square/connect-url` mints a signed JWT `state`
  (`sign_square_state`, typ `square_oauth`, 20 min) and returns the authorize URL;
  the **public** `routers/public_square.py` `GET /public/square/callback`
  (unauthenticated, protected by the signed state) exchanges the code, stores the
  connection, auto-picks the location if there's one, then 302s back to
  `/admin/merch/square`. Scheduler runs `sync_all_square` daily at 04:00.
- **Deploy** (server `.env`): set `SQUARE_APP_ID` + `SQUARE_APP_SECRET` (never
  commit), `SQUARE_ENVIRONMENT=production` (or `sandbox`), optional
  `SQUARE_API_VERSION`. In the Square Developer dashboard register the app's OAuth
  **redirect URL = `https://betterat.cricket/api/public/square/callback`** (matches
  `settings.square_oauth_redirect`; nginx strips `/api`). The box must reach
  `connect.squareup.com`. Tokens are stored per club as plain columns (same
  precedent as `playcricket_api_token`); encryption-at-rest is a hardening follow-up.

## BetterSelect — Self-service player availability (v8.1, Jun 2026)

Players set their own availability with **no account, no app, no Facebook** — one
per-club magic link + a last-4-of-phone PIN, shared by QR / group chat. Full
design note: `docs/betterselect-self-availability.md`.

- **Migration 068**: `organisations.availability_link_token` (unique, nullable,
  **rotatable** — `secrets.token_urlsafe(24)`), `availability_self_service_enabled`,
  `availability_require_pin` (default true). `player_availability.source`
  (`'admin' | 'self'`) — `recorded_by` is NULL for self answers, so `source` is
  the audit/badge signal. Idempotent ALTERs mirrored in `main.py` lifespan.
- **Public router** `routers/public_availability.py` (prefix `/public/availability`,
  **unauthenticated** — NOT wrapped in `require_module`; it resolves the club from
  the token and checks `org_has_module(club, "select")` + the enabled flag itself,
  so a disabled/downgraded club's link 404s). Endpoints: `GET /{token}` (branding
  + active-player names), `POST /{token}/verify` ({player_id, pin} → signed
  HttpOnly **`bs_avail`** cookie {club, pid, typ:'avail', ~30d}), `GET|POST
  /{token}/me` (this player's dates + answers / upsert `source='self'`,
  `recorded_by=NULL`), `POST /{token}/switch` (clear cookie). PIN gate =
  last-4-of-`Player.phone` (strip non-digits). **Lockout** after 5 wrong / 15 min
  per (token, player, IP) via new `services/rate_limit.FailureTracker`
  (`assert_not_locked`/`record_failure`/`clear_failures`) + a coarse per-IP
  `enforce` throttle. Unknown-player and wrong-PIN both count as a failure so the
  link can't enumerate the roster.
- **Admin** (on the gated `availability` router, cap `MANAGE_SELECTIONS`):
  `GET /availability/self-service`, `POST /availability/self-service`
  ({enabled?, require_pin?} — mints a token on first enable),
  `POST /availability/self-service/regenerate`. Returns a phone-coverage count
  (active players with a usable last-4). The admin matrix now returns the real
  `source` (was hardcoded `'manual'`) so self cells get a corner-dot badge; an
  admin override re-stamps `source='admin'`.
- **Shared helpers** in `routers/availability.py`: `phone_last4`,
  `active_self_service_players` (non-dormant active roster — same recency rule as
  the matrix), `upcoming_fixtures_by_date` (the matrix's date grouping, extracted
  so the public page and matrix agree on valid dates). The matrix was refactored
  to call it (pure extraction).
- **Frontend**: public route `/avail/:token` (`pages/PublicAvailability.jsx`,
  outside `ProtectedRoute`, global Navbar suppressed in `App.jsx` — own minimal
  white-labelled header, club accent via inline `--pb-accent`). 3 steps: pick
  name → last-4 PIN → tap Available/Maybe/Unavailable (date-keyed; cookie resume
  jumps straight to step 3). Admin `SelfServiceLinkPanel.jsx` on the Availability
  screen: enable/PIN segmented toggles, link, copy-link, copy-message
  (`🏏 Set your availability: {link}`), **client-side QR** (`qrcode` npm dep —
  `QRCode.toDataURL`), regenerate, phone-coverage nudge. New `api.js` methods:
  `bsGetSelfService`/`bsSetSelfService`/`bsRegenerateSelfService` +
  `availPublicLanding`/`Verify`/`Switch`/`Me`/`Set`.
- **Cross-feature**: self answers are plain `player_availability` rows, so they
  flow into the Selection pool automatically. `/auth/me` + `/auth/login` now
  return `club_slug` (powers the admin "View Public Page" button).
- **Navbar buttons** (separate small ask, shipped same release): "Admin Login" on
  the public club `Navbar.jsx` (→ `/login`, or "Admin" → `/admin` when signed in);
  "View Public Page" in `AdminLayout.jsx` header (→ `/{club_slug}`).

## Public Fixtures + Lineups pages, and the CA team-list route (v8.94.0, Jul 2026)

The public club site's **Games** dropdown was Results + Ladders; it now also has
**Fixtures** (`/{slug}/fixtures`) and **Lineups** (`/{slug}/lineups`). Both are
live off the Grassroots feed — nothing new is persisted.

- **The lineup route is the PLAIN match record**: `GET /scores/matches/{id}`
  **without** `responseModifier=includeScorecard`. It carries
  `teams[].players[]` (`{participantId, name, shortName, roles}` — roles being
  `Captain` / `Wicket Keeper`), `teams[].nonPlayingMembers[]` (coach/manager)
  and top-level `officials` (umpires). **Verified live against an in-season
  winter fixture: an UPCOMING match returns a side as soon as its club
  publishes it**, and an empty `players` list for a side that hasn't — so "not
  named yet" is a normal state, not an error. `matchSummary.teams` (not the
  top-level `teams`) is where `isHome`/`isWinner`/`scoreText` live — the same
  gotcha the scorecard parser already documents.
- **`get_match_detail` / `get_matches_detail`** (`grassroots_scores_client`)
  are kept SEPARATE from `get_match_scorecard` with their own `_MATCH_TTL` of
  **5 minutes** (vs the scorecard's 15): a pre-game team list is edited right
  up to the first ball, whereas a finished scorecard is settled.
- **`services/lineups.py`** normalises a match, decides which side is ours
  (`owningOrganisation.id` against the org id first — our `organisations.id` IS
  the CA org GUID — then `club_match_keys` name matching), and resolves
  `participantId` → our players by `id` OR `grassroots_id`, **org-scoped** (the
  per-club uuid5 scheme). A redacted junior (`********`) gets their real name
  back when we hold the player. `our_lineup_players` returns
  `(players, unmatched)` for the vote engine.
- **Name-fallback fix (same day)**: two real, long-registered Applecross
  players (100+ games each) showed on the Lineups page with no photo and no
  profile link. Root cause: CA issues a **different participant GUID** for
  the same real person on this plain match-list route than the GUID our
  scorecard sync resolved them under for that exact game (verified live —
  their own scorecard endpoint correctly links them via a GUID that matches
  neither `players.id` nor `grassroots_id` on the lineup route's payload) —
  the same MyCricket/PlayHQ dual-GUID class of issue the scorecard rewrite
  documents above, just hit on a different endpoint. `resolve_participants`
  was GUID-only; it now adds the identical third-step fallback
  `games.py::get_scorecard` already uses — a `(surname, first_initial)`
  name-key match — after the id/`grassroots_id` checks fail. Confirmed against
  the real payload for both players before shipping.
- **`GET /organisations/{id}/lineups`** (public): `mode=upcoming` (falls back to
  recent games when nothing is scheduled, so the page is never blank in the
  off-season) or `mode=past` with `season_id`/`grade_id`/`offset`/`limit`
  paging. Bounded on purpose — every match is a live upstream fetch.
- **Category + Finals filters (same day)**: the Lineups page's Past tab used
  the shared `SeasonSelector`'s Gender/Games/Captain pills, which are
  wired to per-player leaderboard params it never fetches — the toggles
  rendered but silently did nothing. Fixed by giving `SeasonSelector` opt-out
  flags (`showGenderFilter`/`showFinalsFilter`/`showCaptainFilter`, all
  default `true` so every other caller — Players/Records/Leaderboard/
  Dashboard/GamesPage — is unaffected) and replacing them here with two
  filters that actually mean something for a fixture list: **Category**
  (Senior/Junior/Women's/... — how the **grade** is classified, not a player
  attribute) and **Finals** (the game's own `is_final`). Captain has no
  fixture-level meaning and was dropped, not just hidden.
  - `grade_labels.org_grade_categories(db, org_id)` returns every distinct
    grade name in the org mapped to its effective category (confirmed via
    `grades.category`, else `suggest_category`), keyed on the
    sponsor-suffix-stripped name (`strip_sponsor_suffix` — a Python mirror of
    `iq_filters.grade_base`'s SQL regex) so "B Grade (DXC Technology)" from a
    live fixture/lineup and our stored "B Grade" resolve to the same category.
    Verified against every real grade name at two live clubs (Applecross,
    Darwin) before shipping — Colts/Juniors/Under-N → junior, PSWL/Women's →
    womens, everything else → senior, matching the existing
    `suggest_category` heuristic used for the admin grade list.
  - Both filters are server-side and paginate correctly: `category` resolves
    to a `grade_id` list once (category may be an unconfirmed suggestion, not
    a DB column, so it can't go straight into SQL) and both it and
    `finals_only` are applied in `_played()`'s WHERE clause for `mode=past`,
    and as a plain Python filter over `org_grassroots_fixtures()`'s list for
    `mode=upcoming`. The response's `categories` field lists only the
    categories actually present among the org's grades, so a club with no
    Masters/Mixed grades never sees an empty option.
  - Frontend keeps the returned category list in its own state (not reset
    alongside the match data on every refetch) so the filter pills don't
    flash empty while a filter change is loading.
  - Both public pages also dropped their subtitle taglines ("straight from
    the association draw" / "straight from Play.Cricket") per direct
    instruction — a page whose eyebrow+title already say what it is doesn't
    need one.
- **Cross-linking (same day)**: a played match's lineup card now links to its
  scorecard (`/games/{match_id}` — the id is already the same `games.id` for
  every "past"/"recent"-sourced match, so no extra lookup is needed; the link
  only renders when `status === 'COMPLETED'`, which an "upcoming"-sourced
  fixture never is, so there's no dangling link to an unsynced game). A
  Fixtures-page row's "↗ Lineup" now deep-links to that exact match
  (`/{slug}/lineups?match={id}`) instead of the generic list. New `GET
  /organisations/{id}/lineups/{match_id}` (thin wrapper over
  `services.lineups.match_lineups`, same payload shape as one list entry)
  backs the deep link; `LineupsPage`'s `?match=` param renders just that one
  `MatchCard` with a "← All lineups" link, skipping the list fetch entirely.
- **Frontend**: `FixturesPage.jsx` (grouped by date, Today/Tomorrow/In-N-days
  chips) and `LineupsPage.jsx` (Upcoming/Past toggle, `SeasonSelector` on Past,
  Load more). `TeamBadge` was **extracted from `MatchScorecard.jsx` into
  `components/TeamBadge.jsx`** so the lineup match header matches the
  scorecard's; a player shows their club photo, else the club crest, else
  initials. Both pages were verified visually against live Darwin CC (in-season)
  and Applecross (off-season/past) data before shipping — see the v8.79.0 note
  for the local-dev-proxy-to-production technique.
- **Not built (deliberate)**: nothing here is persisted, so there's no lineup
  history beyond what the feed still serves. Also noticed while investigating:
  `matchSummary.teams` carries `wonToss`/`battedFirst`, which contradicts the
  older "the GR path can't see the toss" note elsewhere in this file — a real
  opening for the BetterIQ toss/captaincy analysis, not chased here.

## BetterSelect — Vote collection (v8.92.0, migration 193, Jul 2026)

Brownlow-style best-player votes per fixture, its own "Votes" menu item in
BetterSelect. Everything is **derived on read** from raw ballots + the club's
current `vote_settings` (no stored weekly results or season points), so a
mid-season config change restates the whole season — same philosophy as
BetterFees' derived allocation.

- **Migration 193** (+ idempotent `main.py` lifespan mirror): `vote_settings`
  (org singleton: `enabled`/`link_token`/`require_pin`, `voter_mode`
  'players'|'captain', `ballot_values` JSONB default `[3,2,1]` — fully custom,
  best-first, ≤10 positions — `counting_method` 'rank'|'tally', `tie_policy`
  'share'|'countback', `allow_self_vote` default false,
  `allow_non_participants` default false, `auto_close_days` default 7),
  `vote_ballots` (one per voter per fixture — `voter_player_id` for a club
  player OR bare `voter_name` for a non-participant; partial uniques per
  identity space; `source` 'self'|'admin'), `vote_ballot_picks` (ranked
  positions only — values derived from config at count time),
  `vote_fixture_overrides` ('locked'|'reopened' on top of the auto-close
  window).
- **Eligibility = the synced scorecard** (per direct instruction, not the
  saved lineup): a fixture is votable once `games.id == fixture.id` exists
  (playhq fixtures share ids with their games; manual fixtures aren't votable
  yet), and the votable/voter list is `services/votes.eligible_players` — the
  union of `game_appearances` + batting/bowling/fielding rows, **org-scoped
  through `players.organisation_id`** (the shared-game cross-club leak rule).
  Captain-only mode uses `game_appearances.is_captain`, falling back to the
  lineup's captain when the sync predates the flag.
- **Counting** (`services/votes.py`, pure functions, unit-checked offline):
  'tally' = season points are the raw sum (10 voters' 3s = 30). 'rank' =
  weekly conversion — top raw vote-getter earns `ballot_values[0]`, etc.;
  'share' ties use standard competition ranking (both take the higher value,
  next value(s) consumed), 'countback' breaks on most-of-the-highest-value
  then down the ballot, dead heats still share. Season year = Jul→Jun
  (`season_year_for`); rounds group on `fixtures.round` (label else date) and
  the leaderboard can replay standings "as at" any round (`through_round`).
- **Two capabilities**: `MANAGE_VOTES` (settings/link, ballot entry + delete,
  lock/reopen, per-fixture ballot detail — which shows who voted for whom) and
  `VIEW_VOTE_RESULTS` (leaderboard) — the Main Admin hands the latter out per
  user since many clubs keep the count secret (club_admins implicitly hold
  both). New `require_any_cap(*caps)` factory in `auth/capabilities.py`;
  `BetterSelectLayout` NAV gained `anyCaps` support. **No tallies on any
  public surface** — leaderboard is admin-app only, by decision.
- **Routers**: `routers/votes.py` (`/votes/*`, mounted with
  `require_module("select")`) — settings GET/POST/regenerate, fixtures list
  (season-year filter + state + ballot counts), fixture detail, admin ballot
  upsert (paper votes / captain texting in — works after close, any named
  voter, but picks still restricted to who played + the self-vote rule),
  ballot delete (spoof moderation), lock/reopen, leaderboard.
  `routers/public_votes.py` (`/public/votes/*`, unauthenticated — resolves
  club from `vote_settings.link_token`, checks entitlement + enabled itself,
  404-tells-nothing): landing, PIN verify (same lockout/rate limits as
  availability, own `bs_vote` cookie), per-fixture state, ballot submit.
  Verified players vote as themselves ('captain' mode restricts to the
  captain); a typed name is accepted only when `allow_non_participants` — a
  verified player who didn't play also counts as a non-player ballot (stronger
  identity than a typed name). Self-vote + played-only + open-window all
  enforced server-side.
- **Frontend**: `pages/admin/betterselect/AdminVotes.jsx`
  (`/admin/betterselect/votes` — Fixtures / Leaderboard / Settings tabs; the
  settings tab has the link+QR panel and points at the Users page for
  leaderboard access) and `pages/PublicVoting.jsx` (`/vote/:token`,
  standalone/no-navbar like `/avail/`): pick game → verify (or "I didn't
  play" name entry when allowed) → assign positions one at a time ("Who gets
  your 3?") → review → submit; resubmitting updates the same ballot.
- **Eligibility source is a club choice** (v8.94.0, **migration 194**): the
  votable list comes from `vote_settings.eligibility_source` —
  **`scorecard`** (default, who actually played) | **`lineup`** (the saved
  BetterSelect `fixture_lineups` XI) | **`playhq`** (the team list the club
  published on Play.Cricket, live via `services/lineups.our_lineup_players`).
  The last two are ready on match day, so a club can vote on the night instead
  of waiting for the weekly sync. Per-fixture override on
  `vote_fixture_overrides.eligibility_source` (its `status` went nullable so a
  row can carry a source alone); `POST /votes/fixtures/{id}/source` ('' clears
  back to the club default). `votes.resolve_eligibility` picks the requested
  source and **falls back to the first other source that has players**,
  reporting `requested`/`used`/`fell_back`/`counts`/`unmatched` so the admin
  page shows which list is really in play; `check_all=True` (admin detail only)
  also counts the unused sources, which costs one live Play.Cricket fetch.
  `fixture_vote_state`'s old `awaiting_sync` is now **`awaiting_team`** (no
  votable list from ANY source yet) and takes `ready` rather than `has_game`.
  **The list views compute `ready` cheaply** (`has_game or has_lineup`, or
  played-and-`playhq`) — a live per-fixture upstream call per row would be one
  request per fixture, so an unpublished Play.Cricket side is reported when the
  ballot page is actually opened.
- **`merge_players` reassigns vote rows** (`admin.py::_merge_players_core`):
  both vote FKs are ON DELETE CASCADE, so without the reassignment a routine
  merge would silently destroy the removed record's ballots and every vote
  cast for them. De-dups (keep's ballot/pick wins) then moves; deliberately
  NOT in the undo log — an undone merge leaves votes on the kept player
  (same human, no vote lost).
- **Known gap** (deliberate v1): manual fixtures/games aren't votable — the
  votable probe is `games.id == fixture.id`, and manual games have no
  fixture link.

## BetterIQ — Opposition, Selection & Player Trends (v2.1.0, June 2026)

Best-tier analytics module (master-plan Phase 4). Gated by `require_module("iq")` + the `MANAGE_IQ` cap. Module surface mirrors BetterSelect — own `IQLayout` (violet `--pb-accent` override), dashboard tile + sidebar entry flip on automatically once `MODULE_INFO`/`MODULE_META` have `built: true`. Routes under `/admin/betteriq` (Overview + Opposition + Selection + Player trends). **NL Q&A is the one remaining phase** (still needs an LLM-provider decision — open in the spec).

**Selection & Player trends (v2.1.0)** — two more read-only surfaces, both pure reads over held data (org-scoped via grades→seasons over the `v_effective_*` views):
- `iq_selection.py` (`/iq/selection/*`) analyses a fixture's saved BetterSelect lineup (`fixture_lineups`). **It reuses BetterSelect's own pool** — `services/selection_pool.assemble_selection` (extracted v2.2.0 from `routers/selection.py`, which now delegates to it) — so eligibility (12-month recency wall, women's/men's gender wall, squad tier, per-date availability incl. period fallback) is **identical** to the selection board. Re-deriving it earlier let ghosts through (a women's player / years-dormant names appearing as promote picks for a men's 2nd XI). On top it computes XI **balance** (pace/spin, keeper, openers, all-rounders, LH/RH from `skill_positions`+`bowling_type`), last-5 **form**, **warnings** (no keeper, thin attack `<5`, plus ineligible-pick flags: wrong-grade/inactive/dormant/unavailable, out-of-form bat `<15`), **promote** (`autofill_eligible` + available + in form, never selected), **rest** (ineligible/out-of-form picks), playing up/down via the pool `tier`, and a **match-up** column (each player's record vs the fixture's opponent via `resolve_opponent` + `opp_key`). `_resolve_opp_key` prefers explicit opponent so this stays correct.
- `iq_trends.py` (`/iq/trends/*`) reuses `aggregations.get_season_by_season` / `get_career_*` / `get_upcoming_milestones_for_org` + `milestone_rules`: per-player season-by-season **trajectory**, **breakout/decline** (latest season vs prior-career baseline, min-sample gated: bat ≥5 recent / ≥10 prior inns, bowl ≥6/≥15 wkts), and **milestone forecasting**. No new tables.
- **Opponent match-to-club**: `_resolve_opp_key` now prefers an explicit `opponent` over `fixture_id` (identity from the chosen club; the fixture only supplies the grade), so the Opposition UI's "Match club" search can link an unlinked upcoming fixture to a known `opp_key`.
- **Deeper analytics (v2.3.0)** — all read-only: **Trends** add recent-form sparklines (`_player_recent`), milestone **ETA** (career per-game rate, `_eta_games`), peak season + **consistency** (σ of season avg), **role-evolution** (bat/bowl share, first vs last third), and an **"emerging"** shelf (`_emerging`). **Selection** adds `_best_available_xi` — a greedy best XI from the `autofill_eligible` pool (keeper + ≥5 bowlers enforced) diffed against the picked XI (`suggest_in`/`suggest_out`). **Opposition** adds `_venues_vs` (W/L by venue) and `_our_bowler_dominance` (our-bowler × their-batter repeat-dismissal grid from `bowler_wickets`; merged with main's parallel whole-club opposition rework).
- **Live dossier depth (v2.4.0)** — `iq_opponent.py` (main's whole-club scout) now also parses opponent **fall-of-wickets** into a partnership-by-wicket / collapse map (`season_fow` → `partnerships` + `_partnership_insight`) and a team-wide **dismissal breakdown** (`dismissal_breakdown`, summed from the per-batter `dism` counters). Frontend `KeyPlayersCard.jsx` — a Uiverse crypto-card-inspired, IQ-themed showcase — flicks through the danger batters/bowlers with a headline stat, vs-us record and a drawn recent-form sparkline.
- **Scouting synthesis (v2.5.0)** — rule-based, scorecard-derived, **no LLM** (NL Q&A stays parked). In `iq_opponent._assemble`: `_enrich_batter`/`_enrich_bowler` add a `key_note` + recommended `plan` + `risk` + `confidence` (sample-gated per the brief's §19.5) onto each danger player; `_how_they_win_lose` + `_game_plan` produce team tendencies (top-order reliance, strongest/fragile partnership, thin attack) and a "How to beat them" one-pager (`remove_early` / `see_off` / `target_bowler` / `key_warning` / `one_liner`). Surfaced via `GamePlan` + `WinLose` in `OppositionScout`, enriched on the frontend with head-to-head + best venue + our-performers from the instant report. **North-star vision doc: `docs/community-cricket-analytics-brief.md`** — the full "digital cricket analyst" roadmap. Reality filter: our data is **scorecard-level, not ball-by-ball**, so phase/ball-matchup/pressure/win-probability features (brief §1.2–1.3, §2.2–2.4, §10.1, §15.1) are out of reach; the matchup proxy that survives is `_our_bowler_dominance` (our-bowler dismissals of their batters).
- **Team self-analysis (v2.6.0)** — brief §7/§8, the opposition lens pointed at us. `iq_team.py` (`/iq/team/*`, page `TeamAnalysis.jsx` at `/admin/betteriq/team`) reconstructs **our** team score from `SUM(batting_innings.runs)` and the **opponent's** from `SUM(bowling_spells.runs)` (runs our bowlers conceded), so bat-first vs chase, "what score wins" bands and defending/chasing all come from stored per-innings data (no live fetch) — close-but-not-exact (extras we don't store are excluded). One per-game pull (`_per_game`, org-scoped via grades→seasons over `v_effective_*`), aggregated in Python into record/home-away, batting profile (top/mid/lower split via `batting_position`, boundary%), bowling, bat-first/chase win%, score-band win rates, venue records, partnership-by-wicket (`partnerships.is_club_innings`), and a `_how_we_win_lose` synthesis.
- **Player deep-dive (v2.7.0)** — brief §1.4/1.5/1.9/1.10. `iq_trends.player_deep_dive` (`GET /iq/trends/player/{id}/deep`) does ONE innings pull (runs, not_out, dismissal_type, batting_position, opp_key) and derives in Python: **starts & conversion** (reach-25 %, 25→50, 50→100, score bands), **dismissal breakdown**, **batting by position** (Opening/First-drop/Middle/Lower/Tail buckets + best position), **by-opposition** (best/worst by avg, min 2 inns) and a rule-based **scouting note** (CricViz card §16.9). Surfaced as extra cards in the `PlayerTrends` detail view (lazy-loaded alongside the trend). Dossier `DOSSIER_VERSION` bumped so the v2.5 opposition synthesis (game plan / win-lose / scouting notes) rebuilds for **every** cache key — whole-club and each team — instead of waiting on the 7-day TTL.
- **Captain's Cheat Sheet (v2.8.0)** — brief §16.6. `CheatSheet.jsx` at `/admin/betteriq/opposition/cheatsheet?opponent=…&fixture=…&team=…` — a **print-ready, light-themed one-pager** composed entirely from the existing report + dossier payloads (no new backend): game plan, danger batters/bowlers (with their plan), our bowler match-ups (`bowler_dominance` → "save X for Y"), how-they-win/lose, our edge (`our_performers`) and head-to-head + best venue. `window.print()` + a `@media print` block (hides chrome, fits A4). "Cheat sheet" button in `OppositionScout` passes the current opponent/fixture/team through the URL.
- **Danger/false-threat alerts (v2.9.0)** — brief §16.2/16.3. `_enrich_batter` now adds an `alert` (`danger` reasons: in hot form / averages big vs us; `caution`/"paper tiger" reasons: not-out-inflated average, leans on one big score, low-confidence sample, slow SR); `_enrich_bowler` flags the main threat. `DOSSIER_VERSION` → 3 so caches rebuild. Surfaced as a Danger / "Paper tiger?" badge + reason line on `KeyPlayersCard`.
- **More scorecard analytics (v2.10.0)** — **Fielding/keeping** (brief §3/§9): `iq_team._team_fielding` → top fielders, keepers, run-out specialists + fielder→bowler catching combos (from `bowler_wickets.fielder_id`), in `team_overview.fielding`. **Opposition memory** (§16.10): `iq._last_meeting` → most-recent meeting result, our/their score (`SUM(batting_innings.runs)` / `SUM(bowling_spells.runs)`), our top bat & bowler that game, in the instant report. **Selection value** (§6.2): `iq_trends.player_deep_dive` adds `selection_value` — team win% with vs without the player (`game_appearances` vs all org games) + swing.
- **All-rounder analysis (v2.10.1)** — brief §5. `iq_team._all_rounders`: players who clear both a batting-innings and a wickets floor (4/4 per season, 10/10 all-time) over the per-game `v_effective_*` tables; bat avg recomputed exactly from `batting_innings.not_out`, bowl avg from `runs_conceded/wickets`; ranked by the classic bat_avg−bowl_avg diff and role-classified (genuine / batting / bowling all-rounder). In `team_overview.all_rounders`, board on the Team page.
- **Batting partnership pairs (v2.10.2)** — brief §11.1. `iq_team._batting_pairs`: groups `partnerships` (is_club_innings) by the unordered `LEAST/GREATEST(batter1_id, batter2_id)` pair, org-scoped via games→grades→seasons; per pair → stands, total runs, avg-per-stand, best, 50+ stands, and an `opening` flag (≥half their stands at the 1st wicket). `team_overview.batting_pairs`, board on the Team page.
- **Similar player search (v2.10.3)** — brief §15.8. `iq_trends._similar_players`: club-internal nearest neighbour over a career profile (bat avg [innings-weighted from `batting_average`], bat SR, bowl avg, economy — all from `player_season_stats`), z-scored across the squad and compared only on features both players have (≥2 shared), distance→similarity `100/(1+d)`. In `player_deep_dive.similar_players`, card in the Player trends detail.
- **Club MVPs / player impact (v2.11.0)** — brief §15.3 (the scorecard-reachable subset; ball-level inputs like phase/pressure/dot-balls are out of reach). `iq_team.player_impact` (route `GET /iq/team/mvp`, optional `season_id`, defaults to latest season via `team_seasons`): per-player per-match rates over `player_season_stats` (runs, wickets, fielding dismissals) + economy (≥30 balls), z-scored across the squad (`statistics.pstdev`), blended `1.0·bat + (0.9·wkt + 0.45·inv-econ) + 0.35·field`, min-max scaled 0–100, role-tagged (Batting/Bowling/All-round/Fielding). Headline board on `BetterIQHome`, rows deep-link to `trends?player=`.
- **Matchup advantage matrix (v2.11.1)** — brief §16.5. Frontend-only reshape of the instant report's `matchups.bowler_dominance` (already a flat bowler→batter pairing list) into a heatmap grid in `OppositionScout` (`buildMatrix`/`MatchupMatrix`): top 6 our-bowlers × top 8 their-batters, cells shaded by dismissal count, Matrix/List toggle (matrix when ≥2 bowlers and ≥2 batters). No backend change.
- **Collapse analysis (v2.11.2)** — brief §7.5. `iq_team._collapses`: reconstructs fall-of-wickets per club innings from stored `partnerships` runs (keyed by `(game_id, innings_number)`, is_club_innings), finds the worst 3-consecutive-wicket span (sum of three contiguous partnership runs), flags a collapse when ≤15, and reports collapse %, worst collapse, and a start-wicket histogram ("where the wheels come off"). `team_overview.collapses`, card on the Team page.
- **Batting reliability (v2.11.3)** — brief §6.1 (scorecard-reachable subset). `iq_trends.player_deep_dive` adds `reliability` computed from the SAME innings pull (no extra query): floor/median/ceiling via `_percentile` (25th/50th/90th of the runs distribution), failure rate (dismissed <10), 20+ contribution rate, and a boom-or-bust/steady/balanced `profile` from the coefficient of variation. Card in the Player trends detail.
- **Milestone watch on home (v2.11.4)** — frontend-only. `BetterIQHome` calls `iqTrendsOverview()` and renders the top upcoming milestones (`{needed} to {target} {type}`) in a panel beside the Club MVPs; rows deep-link to `trends?player=`. No backend change.
- **Bowling attack structure (v2.11.5)** — brief §8.3. `iq_team._attack_structure`: per-bowler workload over `v_effective_bowling_spells` — **overs are cricket notation** (10.2 = 10 overs 2 balls), so converted to balls in SQL (`FLOOR(overs)*6 + ROUND(frac*10)`) before summing; pace/spin split from `players.bowling_type` (`_PACE_TYPES`/`_SPIN_TYPES`), per-bowler econ/avg/SR + a Strike/Containment/Stock role tag (min 60 balls season / 300 all-time). `team_overview.attack`, card on the Team page.
- **Consolidation & polish (v2.12.0)** — frontend-only. `TeamAnalysis` reorganised from a ~13-card scroll into **Overview / Batting / Bowling / Players** tabs (a `tab` state + tab bar; cards regrouped, the stray "conceding on avg" line promoted to a proper Bowling summary card). Added a reusable `<Note>` footnote component and "how this is worked out" notes to the opaque blended ratings (Club MVPs on home, all-rounders, collapse, bowling roles, reliability, similar-player). Player deep-dive detail gets a "Deep dive" section divider between the season-trajectory cards and the per-innings cards. No backend/API change.

## BetterIQ — Filters honest, cross-club leak fix, multi-grade filter, clickable players, fixture-aware Ask (v8.74, Jul 2026)

Five related fixes/features from live feedback on the Opposition page:

- **Cross-club player leak (the "Zeplin in our bowl-well list" bug)**: a match
  between two both-synced clubs shares ONE `games.id` carrying BOTH clubs'
  per-innings rows (each club's sync attaches only its own players — by design,
  see the shared-game note in sync.py). Any per-game read that org-scopes the
  GAME (grades→seasons) but not the PLAYER join therefore mixes the opponent's
  players into "our" lists. Fixed by adding `p.organisation_id = :org_id` at:
  `iq._our_performers_vs` (both queries; also now excludes redacted `^\*+$`
  names and returns each player's BetterSelect `squad`), `iq._our_bowler_dominance`,
  `iq._last_meeting` (scoreline sums + top bat/bowl, which used to credit the
  opponent's best batter as ours), and `iq_review.game_review` (totals + top-5s).
  **Anti-pattern**: never read per-game tables "for a game in our org's grades"
  without also scoping `players.organisation_id` when attributing to OUR side.
- **Filters mean what they say**: `OppositionScout` no longer treats the
  default newest season as "no filter" while the header shows 2025/26 over
  all-time numbers. On first visit (filter bar untouched this session — new
  `ctx.touched` flag set by ContextBar interactions) the page defaults the
  global season to **All seasons**; any picked season/grade then genuinely
  scopes every instant-report card (backend already supported it).
- **Multi-select grade filter, IQ-wide**: `ctx.team.id` may now be several
  grade base-names joined with `'||'` — `iq_filters.grade_match_clause`
  (`= ANY(string_to_array(:grade, '||'))`) replaced every `= :grade` site
  (iq_filters/iq/_opp_scope/iq_team×2/iq_trends), so the SAME single `:grade`
  bind serves one name or many; all existing callers unchanged. The filter-bar
  TeamPicker is a checkbox multi-select with a **Seniors only** preset driven
  by `team_grades`'s new `category` field (stored `grades.category` else
  `grade_labels.suggest_category` — the merge-grades classifier). Client-side
  grade comparisons (MatchPreview/SelectionAnalysis fixture narrowing) use
  `teamNames()` from Context.jsx.
- **Clickable player names** (`PlayerLink.jsx`): our players →
  `/admin/betteriq/trends?player=`, opposition → `/admin/betteriq/
  opposition-player?opponent=&player=` (or `&playerName=` for name-only rows —
  the instant report's danger batters have no participant id; OppositionPlayer
  resolves it via its pending-name matcher once the dossier builds). Applied
  across OppositionScout (our-record, match-ups, last meeting, squad tables,
  radars, historical threats), KeyPlayersCard, TeamAnalysis boards, MatchReview,
  MatchPreview, SelectionAnalysis XI.
- **Radar context**: `viz.Radar` has hover/focus tooltips per vertex (score,
  and with `buildRadar`'s new `details` the actual value + peer mean) and a
  `legend` prop; opposition + deep-dive callers pass both.
- **Multi-grade also honours the merge-grades admin feature**: a club can
  merge two literally-different raw grade names (e.g. "PSWL South" / "PSWL:
  South") into one competition via `grade_merge_logs` (org-scoped active
  `alias_name -> canonical_name` rows, `aggregations._GRADE_MATCH` already
  reads it for leaderboards) — the first cut of this filter only stripped the
  sponsor parenthetical (`grade_base`), so a merged club still saw both raw
  names as separate filter options that each only matched their own literal
  games. `iq_filters.grade_canonical_label(alias, org_param)` resolves an
  active alias to its canonical raw name (single-hop, matching
  `_GRADE_MATCH` — merges are re-targeted onto the final root at merge time,
  not chased through a chain here) before stripping the sponsor
  parenthetical; `season_grade_clause`/`iq_team._scope`/`iq_team.player_impact`
  /`iq_trends._movers_src`/`iq._opp_scope`/`iq_team.team_grades` (the
  filter-bar listing query) all route through it. `org_param` defaults to
  `"org"` (every caller except `iq.py`, which binds `"org_id"`).
- **Ask BetterIQ fixture/opposition tools** (`iq_ask.py`): `upcoming_fixtures`,
  `opposition_report` (trimmed instant report; performers carry `squad` for
  team-relevance), `opponent_danger_players` (reads the dossier cache via
  `get_or_start_dossier` — a cold dossier starts building in the background and
  the tool reports `building`, so the model answers from held data now and says
  the deeper scout will be ready shortly). System prompt: resolve the fixture
  first; keep suggestions team-relevant via `squad` (a lower-grade record vs
  the opponent is a "possible promotion" mention, not an automatic pick);
  unlinked opponents → point at "Match club" on the Opposition page.
  `MAX_STEPS` 6 → 8 for the longer tool chains.

## BetterIQ — Review Fixes (Jun 2026, v2.12.1)

Post-v2.12.0 review pass (live-site feedback). All on branch `claude/gifted-babbage-7QE8g`.
- **Team analysis resilience**: `team_overview` wraps every optional add-on (fielding, all-rounders, batting pairs, collapse, attack, partnerships) in `iq_team._safe(session, factory, default)` — logs + `session.rollback()` on failure so one heavy/failing query (e.g. an all-time statement timeout) can't blank the page. Root cause of "Couldn't load team analysis" was the cumulative weight of the new all-time scans; the wrapper makes the core always render. Also renamed a risky `no` SQL alias → `nout`.
- **Club MVP links**: `player_impact` now emits `player_id` (was `id`) to match the IQ-wide convention; home-page deep-links were going to `?player=undefined`.
- **Current-season gating (trends)**: `iq_trends._current_season_year(org)` = MAX(season year with stats). `_batting_movers`/`_bowling_movers`/`_emerging` take `current_year` and gate `latest.year = :cur`, so years-dormant "active" players no longer surface as risers/decliners. `list_players` now returns **current-season** players with this-season stats (runs/avg, wkts/avg, recomputed from not_outs) **+ their BetterSelect squad** (`players.squad_team_id` → `teams.name`) for the new All-squads filter. Averages 2dp everywhere (frontend `fmt2`). Milestone watch removed from home + trends overview (still computed in payload / shown in the bell). Full player grid → `PlayerSearch` combobox.
- **Selection shows unselected fixtures**: `iq_selection.list_lineups` LEFT JOINs `fixture_lineups` and keeps upcoming fixtures even with 0 picked (`HAVING COUNT(fl)>0 OR f.played_on >= CURRENT_DATE`). Frontend shows "needs selecting" + a "no XI saved yet" prompt (empty `data.players`).
- **Opposition match persists** (migration **063** `opponent_aliases`: org_id, alias_name [lowercased], opp_key, display_name, unique(org, alias_name)): `iq.save_opponent_alias` upserts; `iq._load_aliases` (defensive — returns {} if the table isn't migrated) is merged into `opposition_opponents`'s `by_name` and checked first in `_resolve_opp_key`'s fixture branch. New `POST /iq/opposition/match`; frontend `applyMatch` saves then refreshes the picker. Once "Bassendean" → "Bassendean Cricket Club" is matched, all fixtures with that name link.
- **MVP is a whole-season value measure, not current form** — by design it's season-aggregate per-match rates (a late-season slump averages in). The home note says so; "Form movers" / recent-form sparklines are the form lens.

## BetterIQ — Review Round 2 (Jun 2026, v2.12.2)

- **MVP year-based**: `iq_team.player_impact` aggregates over ALL season records of the current YEAR (org-scoped `s.year = :year`), not a single `team_seasons[0]` season_id. A club year often spans several season rows (comps / per-club grassroots ids); keying on one id silently dropped in-form players recorded under a sibling row (Monument/Seen symptom). Year resolved from `resolved.year`; falls back to single season_id only when year is NULL.
- **Team analysis by season AND team (grade)**: `team_overview(season_id, grade_id)`; a `_scope(season, grade)` clause (prefers `gr.id`, else `gr.season_id`, else all-time) threaded through every per-game add-on. `_team_fielding` rewritten onto per-game `v_effective_fielding_stats` (grade-filterable + outfield catches = `catches − catches_wk`). New `team_grades()` + `GET /iq/team/grades`. Frontend defaults to the latest season with prominent Season + Team dropdowns.
- **Trends picker = current-season players**: `list_players` returns this-season players (org-scoped seasons join, merged with main's cross-club guard) + BetterSelect squad; `PlayerSearch` combobox opens on focus & reports empty states.
- **Player deep-dive depth**: reuses `get_player_by_venue` (at-venues) + `get_bowling_dismissal_breakdown` (how they take wickets); career strip splits Caught / Ct (wk) / Stumpings via `total_catches_non_wk`/`total_catches_wk`.
- **Opposition player scout** (frontend-only): the dossier already returns full `batting`/`bowling` per-player lists (form, dismissals, vs_us); `OppPlayerScout`/`OppPlayerDetail` in `OppositionScout` add a search → full per-player profile.
- **Caught vs caught (wk)**: PlayerProfile, Leaderboard, TeamDetail, Yearbook already split; fixed `PlayerComparison` (was `total_catches`) → `total_catches_non_wk` / `total_catches_wk`. StatLab keeps a total + keeper-only-preset model.

## BetterIQ — Bowler deep-dive, captaincy & bowling discipline (v2.14.0, Jun 2026)

Three scorecard-reachable additions from the brief (no schema change, no new tables, no LLM):
- **Bowler deep-dive** (brief §2.5/§2.9) — `iq_trends.bowler_deep_dive` (`GET /iq/trends/player/{id}/bowling-deep`), the bowling mirror of `player_deep_dive`. Reads `bowler_wickets` (org-scoped via games→grades→seasons) — the table was previously only consumed for opposition matchups (`iq._our_bowler_dominance`). Derives **wicket quality** from the dismissed batter's stored `batter_runs`: set (30+) vs started (10–29) vs new (<10), avg scalp value, ducks inflicted; **fielder combos** (`fielder_id` on caught/stumped/run-out, c&b excluded); per-bowler **discipline** (wides+no-balls/over from `v_effective_bowling_spells`); + a rule-based bowling scouting note. Surfaced in `PlayerTrends.jsx` under a new "Bowling deep dive" header — the existing career `bowling_profile` card (added v2.13.0, sourced from the `/deep` batting payload) was **relocated** there so all bowling reads together; the new section is gated on `bdeep.wickets > 0` independent of `innings_count`, so a pure bowler still gets it. `player_deep_dive` itself was left untouched.
- **Captaincy** (brief §4) — `iq_team._captaincy`, added to `team_overview` via `_safe`. First analytics use of `game_appearances.is_captain`: per-skipper W/L/D, win%, team avg score under them (reconstructed like `_per_game`), finals record. Min 3 games. Board on the Team page **Players** tab. **Toss-decision analysis is out** — we don't store the toss (the Partner API has `coinToss` but the GR `/scores/*` sync path doesn't capture it; would need a `games` column).
- **Bowling discipline** (brief §2.9/§8.5) — `iq_team._discipline`, added to `team_overview`. Team wides/no-balls per over, extras as % of runs conceded, most-disciplined-first per-bowler ranking (min 10 overs season / 50 all-time). **Guarded**: returns `None` when no extras are recorded across the dataset (older scorecards omit them) so we never show a misleading "spotless" card. Card on the Team page **Bowling** tab.
- All three respect the `season_id`/`grade_id` `_scope` filter on the Team page; the bowler deep-dive is all-time (matches the player-trend view).

## BetterIQ — Match review, par, role-adjusted batting & batting depth (v2.15.0, Jun 2026)

More scorecard-reachable brief items, no schema change:
- **Post-match review** (brief §16.8) — new service `iq_review.py` (`GET /iq/review/games`, `GET /iq/review/game/{id}`) + new page `MatchReview.jsx` at `/admin/betteriq/review` (sidebar entry "Match review"). Per game: scoreline (our `SUM(batting_innings.runs)` / their `SUM(bowling_spells.runs)`), top batting/bowling contributions, best partnership, extras conceded, a single-game collapse check (worst 3-consecutive-wicket span from `partnerships`, same reconstruction as `iq_team._collapses`), and a rule-based "what changed the game" synthesis. Biggest-over / win-probability swings are out (ball-by-ball).
- **Player batting depth** (brief §1.1/§1.2) — `player_deep_dive` now also returns `batting_style` (strike rate, boundary % = share of runs in 4s/6s, balls-per-boundary, accumulator/boundary-hitter profile — needs `balls`/`fours`/`sixes`, now added to its one innings pull) and `context` (batting average in wins vs losses, batting first vs chasing via `g.result` + `innings_number`). Dot% / SR-by-ball-range stay out (ball-by-ball). Cards in `PlayerTrends.jsx`.
- **Team depth** — all added to `team_overview` via `_safe`, all honour `_scope`:
  - `_wickets_quality` (brief §8.4) — club-wide `bowler_wickets` roll-up: top-order/middle/tail split + set/new batters dismissed + dismissal-type mix. Bowling tab.
  - `_team_starts` (brief §7.4) — opening-stand (`partnerships` wicket 1, club innings) profile + win rate after a good (≥30) vs poor start. Batting tab.
  - `_role_ratings` (brief §15.4) — buckets innings by batting position, pools a club average per slot, rates each batter by their primary-slot average minus that slot's average (so an opener and a No. 8 aren't judged alike). Players tab.
  - **Par score** (brief §15.9) — `innings.par` = median first-innings total in bat-first wins + lowest defended. Surfaced on the Overview "What score wins" card.

## BetterIQ — Match preview, opponent ladder & opposition scouting tags (v2.16.0, Jun 2026)

- **Opposition player scouting tags** (brief §13 "Useful Optional Metadata" — opponent edition) — `opponent_player_tags` table (**migration 064**): org-scoped manual attributes (batting_hand, bowling_action, bowling_type, player_role, is_wicket_keeper, is_danger, notes), keyed by `(organisation_id, participant_id)` where `participant_id` is the CA participant GUID = the dossier's `player_id`. Opposition players aren't in our tables (only the dossier JSON), so tags live **decoupled** from the 7-day dossier cache and are merged on the frontend. `iq.get_opponent_tags` / `iq.upsert_opponent_tag` (raw SQL, mirrors `opponent_aliases`; controlled-vocab fields validated, unknown→NULL); routes `GET /iq/opposition/player-tags` + `PUT /iq/opposition/player-tags/{player_id}`. Editor + coloured badges in `OppPlayerProfile.jsx` (`ScoutingTags` + `TagBadges`), wired through `OppositionPlayer.jsx`. Vocab mirrors `players.*` so the choices match our own players.
- **Opponent ladder standing** — `iq.opponent_ladder` (`GET /iq/opposition/ladder`): fetches the live grade ladder (`grassroots_scores_client.get_grade_ladder` + an inline `_ladder_rows` parser of the documented fixturesladders shape) for the **fixture's grade** (via `resolve_opponent`), flags our row with `club_match_keys`, and matches the opponent row by club-name tokens (stop-words stripped). Returns `our_row` + `opponent_row` (rank/P/W/L/pts). **Current** standings only — historical "vs top-4" splits would need ladder snapshots we don't keep.
- **Match preview** (brief §17.4) — new page `MatchPreview.jsx` at `/admin/betteriq/preview` (sidebar "Match preview"). Frontend composition (no new aggregator endpoint): picks an upcoming fixture from `list_opponents`'s `upcoming`, then fetches `opposition_report` (instant — no dossier build) + `opponent_ladder` + `team_overview` (par/record) in parallel and renders a lean (synthesised client-side), ladder, head-to-head, last meeting, their danger players, our edge, and links to the full scout + cheat sheet. Uses the instant report (fast), not the live dossier.

## BetterIQ — Manual scouting cards: batting & bowling intel (v8.26.0, Jun 2026)

The ball-level read CA does **not** record (no shot direction, no delivery
length/line, no bowler-type-faced) entered by the scout, the same posture as the
existing scout-entered scoring-zones wagon wheel. A **per-player** card (not a
per-dismissal log — deliberately lighter than the competitor app that prompted
it), for **both opposition players and our own**, blended on read with the
dismissal mix we *do* hold into a short "DNA" read.

- **Storage** (**migration 094** + idempotent `main.py` lifespan mirror): two JSONB
  blobs `batting_intel` / `bowling_intel`. For opponents they're new columns on
  the existing `opponent_player_tags` (keyed by CA participant GUID, merged onto
  the dossier on the frontend like the other tags). For our own players, a new
  `player_scouting_cards` table (`organisation_id`, `player_id`, the two blobs,
  `updated_by`; unique `(org, player)`). Blob shape — batting: `vuln_bowling[]`,
  `fav_bowling[]`, `zones[20]` (4 lengths × 5 lines, intensity 0–3), `fav_shots[]`,
  `risky_shots[]`, `strengths`, `weaknesses`, `plan`; bowling: `stock`,
  `variations[]`, `zones[20]`, `danger[]`, `strengths`, `weaknesses`, `plan`.
- **Validation** — `services/scouting_intel.py` (`clean_batting_intel` /
  `clean_bowling_intel` + the controlled vocab: `BOWLING_KINDS`, `BAT_SHOTS`,
  `BOWL_VARIATIONS`, `BOWL_DANGER`, `ZONE_LENGTHS`/`ZONE_LINES`). Shared by the
  opponent upsert (`iq.upsert_opponent_tag`) and the own-player upsert
  (`iq_trends.upsert_player_scouting`). An empty blob normalises to NULL.
- **Present-aware partial save** — `upsert_opponent_tag` now only overwrites a
  field when its **key is present** in the body (per-field `CASE WHEN :x_present`),
  so the four distinct editors (basic tags / scoring zones / batting card / bowling
  card) don't clobber each other. This also **fixed a latent bug**: saving the
  scoring-zones editor used to NULL the role/danger flags it doesn't send. The
  upsert re-selects and returns the full stored row (not an echo of the partial
  body). Same present-aware pattern in `player_scouting_cards`.
- **Routes** — own players: `GET`/`PUT /iq/trends/player/{id}/scouting`
  (`iq_trends.get_player_scouting` / `upsert_player_scouting`, org-scoped via the
  same `players WHERE id AND organisation_id` gate as `player_deep_dive`).
  Opponents reuse `PUT /iq/opposition/player-tags/{id}` (the body just carries
  `batting_intel`/`bowling_intel` too). api.js: `iqPlayerScouting` /
  `iqSavePlayerScouting`.
- **Frontend** — shared `ScoutingCard.jsx` (Batting + Bowling cards, each a
  display + inline editor) + `scoutDna.js` (vocab labels mirroring the backend +
  `buildBattingDna`/`buildBowlingDna`, which blend manual intel with the held
  dismissal breakdown into bullet insights and a headline "plan"). New
  `viz.ZoneGrid` (editable length×line heatmap, click cycles 0→3). Wired into
  `OppPlayerProfile.jsx` (opponent tag save) and the shared `PlayerDeepDive.jsx`
  `DeepDiveTab` (optional `scouting`/`onSaveScouting` props) used by both
  `PlayerTrends.jsx` and `PlayerHub.jsx`.
- **Bowler-fairness fixes** (the original ask — the opponent profile was
  batting-first): the radar is now a Bat/Bowl toggle (`OppRadarCard`, defaults to
  the player's stronger side; a bowler no longer gets forced into a batting radar);
  the Bowling stat card adds strike rate + a recent-wickets sparkline; the
  scoring-zones wagon wheel (a *batting* feature) is hidden for a pure bowler; and
  the opponent **deep scan** (`iq_scout._scan_player_deep`, `DEEP_VERSION`→2) now
  derives **"how he takes wickets"** + wicket quality (set/started/new from the
  dismissed batter's runs) by parsing the opposition cards in the innings he
  bowled — reusing sync's `_parse_bowler_and_fielder` / `_BOWLER_CREDIT_DT`.
- **Batting intel split into favoured vs risky (Jul 2026)**: the original single
  "Favoured / risky shots" chip group and single "Vulnerable to (bowler type)"
  group didn't distinguish a batter's comfort zone from his danger zone. Batting
  intel now carries four vocab lists instead of two: `vuln_bowling[]`/
  `fav_bowling[]` (both `BOWLING_KINDS`) and `risky_shots[]`/`fav_shots[]` (both
  `BAT_SHOTS`) — `ScoutingCard.jsx`'s batting editor shows them as two side-by-side
  pairs. `scoutDna.buildBattingDna` emits a bullet per populated list ("Vulnerable
  to…" / "Comfortable against…" / "Goes after the…, set the trap" / "Favours
  the…"). A pre-split blob's old combined `shots[]` key is a **read-side
  fallback only** (never written again): `buildBattingDna` and the editor's
  `seed()` both treat it as `risky_shots` when the new split fields are still
  empty, so already-saved intel isn't silently dropped when the deploy lands or
  the editor is reopened; bowling intel (`stock`/`variations`/`danger`) is
  unchanged.

**Two data layers** (`backend/app/services/`):
- `iq.py` — *instant* report from data we already hold: head-to-head vs an opponent (W/L/D, home/away split, recent meetings) + our players' record vs them (selection intel). Opponent identity = `COALESCE(opp_org_id, opp_club_name)` (`opp_key`), org-scoped via grades→seasons over the `v_effective_*` views — same pattern as `aggregations.get_player_by_opposition`.
- `iq_opponent.py` — *live* opponent dossier. Opponents aren't synced, but they play in grades we already track and the Grassroots `/scores/*` scorecards carry BOTH teams (sync discards the opponent half: `if pid not in our_team_pids: continue`). So we fetch the fixture's grade matches, keep the opponent (the `teams[]` entry whose `owningOrganisation.id` ≠ ours, or matched by club name), and aggregate their current-season batting/bowling/fielding per `participantId` — the mirror of sync's `our_team_pids` gate. Plus deep head-to-head: re-fetch our stored games vs them (capped) and parse the opponent cards → each opponent player annotated with their record vs us. A never-played-but-fixtured opponent is still scoutable (key the dossier on the name + fixture grade).

**Dossier cache** (`opposition_dossiers`, migration 059): built on demand in a detached `asyncio` task (its own `async_session_maker` session; tasks held in `_BUILD_TASKS` to dodge GC). `status` building→ready/error drives a frontend poll — `GET /iq/opposition/dossier` returns `{status:'building'}` until ready, then the payload. TTL 7 days + a Refresh button (`force=True`, `POST .../dossier/refresh`). Opponent player stats are NOT normalised into tables — this JSON cache is the only place live opponent data lands (keeps the data-rights surface small, no opponent-stats schema).

**Ceiling**: we hold scorecards, not ball-by-ball — so form / averages / SR / conversion / dismissal-patterns / vs-us / venue, but NO phase or ball-level matchup data. The UI says so (`coverage.notes`).

**Bounds** (CA-proxy politeness + latency): `MAX_OPP_SEASON_MATCHES=18`, `MAX_HEAD_TO_HEAD_GAMES=25`; reuses `grassroots_scores_client`'s in-process scorecard cache + semaphore(6). First build ~10–40s, then cached. Overs maths: `_overs_to_balls(10.2)=62` (10 overs + 2 balls).

## KlubPro → BetterStats Migration Tooling (v8.4, Jun 2026)

Super-admin-only onboarding wizard (integrated into the admin app, **not** a
standalone tool) that reviews data staged in the **external KlubPro Postgres**
(`klubpro_migration` schema) and imports **player profiles** (matched to existing
BetterStats players by name — KlubPro has no CA ids) + **sponsors**. Full guide:
`docs/klubpro-migration.md`.

- **Two DBs.** BetterStats uses the normal `get_db`. KlubPro gets a **lazy**
  second engine in `app/services/klubpro_db.py` (`get_klubpro_db`, built from
  `KLUBPRO_DATABASE_URL`) — only instantiated when an operator hits a migration
  endpoint, so the app boots/runs normally with it unset (the page shows "not
  configured"). KlubPro is **never ORM-mapped** — schema-qualified raw SQL only,
  so it never enters Alembic.
- **Gating.** Router `routers/klubpro_migration.py` (prefix `/club-admin/klubpro`)
  is `require_super_admin` (cross-club platform tooling, not a per-club cap). UI
  at `/admin/super/migration` (`pages/admin/klubpro/`), `requireRole="super_admin"`,
  linked from `AdminLayout` `SUPER_LINKS`.
- **Migration 072** (+ mirrored idempotent lifespan creates): adds
  `org_sponsors.contact_name/.email/.klubpro_sponsor_id` (the handoff's sponsor
  insert targets these three — the repo's `org_sponsors` lacked them) + partial
  unique `(organisation_id, klubpro_sponsor_id)`; and two **BetterStats-side**
  bookkeeping tables `klubpro_migration_batches` / `klubpro_migration_backups`
  (so backups/audit survive even if KlubPro is decommissioned and rollback is a
  pure BetterStats op).
- **Safety invariants** (`services/klubpro_migration.py`): fills gaps but **never
  clobbers with empties**; `is_opening_batsman=False` = "no info" (only `True`
  applied); **skills compare as a set**; only the **ten profile fields** are ever
  written (no stats/games/ids/org). Sponsor import is dedup-safe on the unique
  index. Flow is **dry-run → confirm → per-row backup → write**, every batch
  **rollback-able** from the History tab.
- **`sponsor_import_selections` is intentionally NOT the source of truth** — its
  columns weren't in the handoff, so selection is client-side and de-dup is
  enforced on the BetterStats side instead of guessing that schema. The other
  KlubPro tables (`player_match_mappings` etc.) have documented columns and are
  used directly.
- **Editable club mapping** (from the dashboard): the "Mapped to" column is a
  dropdown of all orgs (`GET /club-admin/klubpro/organisations`); `PATCH
  /club-admin/klubpro/club-mapping {klubpro_club_id, betterstats_organisation_id,
  force}` does an **UPDATE-or-INSERT** on `club_mappings` (never DELETE → row id
  + `player_match_mappings` FK preserved), keyed by `klubpro_club_id`, and bumps
  the onboarding target to `mapped` (keeps `validated`). Returns
  `{status:'conflict'}` (HTTP 200, not an error — the api client doesn't surface
  status) when the org is already mapped to another KlubPro club; the UI confirms
  then retries with `force`. `fetch_dashboard` LEFT JOINs `club_mappings` so each
  summary row carries its mapping. Mapping is repeatable/update-safe and needs no
  manual SQL for future clubs. Candidate matching is **not** auto-run on map.
- **Field-level approval** (v8.4): approving a match approves the *relationship*,
  not a blanket field overwrite. Each match shows the 9 migratable fields
  (`MIGRATABLE_FIELDS` = gender/email/phone/player_role/batting_hand/bowling_type/
  is_opening_batsman/skill_positions/profile_image) side-by-side with a checkbox;
  only ticked fields migrate. `recommended_fields` pre-ticks every field KlubPro has
  a value for, **including `profile_image` whenever KlubPro has an image** (untick to
  keep a newer BS photo; applying overwrites the BS photo, old one saved in the
  backup for rollback). The collapsed card keeps the rich side-by-side summary (both
  images + details); "Fields" toggles the checkbox panel. Selections persist to
  `player_match_mappings.migrate_fields jsonb` (+ `reviewed_at/by`, `imported_at/by`)
  — columns added at runtime by `ensure_match_columns` since KlubPro is external
  (not in Alembic). `plan_player` is the single source the dry-run AND import share
  (apply = selected ∧ non-empty ∧ differs; photo overwrites only when ticked).
  **Bulk Approve** (`POST .../players/bulk-approve`) approves all eligible rows
  honouring each one's field selections (per-item commit + item-level errors so one
  bad row can't poison the batch). first/last/nickname are NOT migratable (BS has a
  single `name`). The dry-run reflects **saved** approvals — approve → dry-run →
  import.
- **Approve ≠ import** (UX gotcha, fixed v8.4): Approve/Bulk-approve only write the
  *decision* (+`migrate_fields`) to `player_match_mappings`; **`Import` is the only
  step that writes BetterStats `players`**. Cards show `APPROVED · NOT IMPORTED`
  (blue) vs `IMPORTED ✓` (green, from `imported_at`); the header carries
  approved/imported/pending counts; `Import` is enabled on the approved-but-not-yet-
  imported count (no longer requires a prior dry-run) with an amber "click Import to
  apply" nudge. Was reported as "approved but data not pulled across" — the import
  had simply never been run.
- **Reject/skip persistence** (fixed v8.4): `upsert_match_mapping` **UPDATEs the
  existing mapping in place** for reject/skip (never nulls `klubpro_player_id` — the
  column may be NOT NULL) and normalises `match_status` to past-tense
  (`approved`/`rejected`/`skipped`); sending the imperative `reject`/`skip` + a NULL
  match id was erroring on the external table's constraints. Approve still
  DELETE+INSERTs (match id always present).
- **Re-matching a rejected KP player** (fixed v8.4): the KP table has a unique on
  the KP id, so a rejected match still holding `klubpro_player_id` blocked
  approving that KP player to a *different* BetterStats player (symptom: reject
  Jnr, then approving Snr errors). Fix: the approve path first **frees the KP id
  from any other BetterStats player** in the club (`UPDATE … SET
  klubpro_player_id=NULL, approved=false, match_status='rejected' WHERE
  klubpro_player_id=:kpid AND betterstats_player_id<>:bpid`), so the rejected row
  keeps its status but releases the id. Requires the id to be nullable —
  `ensure_match_columns` now also `ALTER COLUMN klubpro_player_id DROP NOT NULL`
  (separate txn so it can't roll back the added columns).
- **Name matching** (fixed v8.4): the candidate picker is whitespace/​suffix/​order
  tolerant — `normName` collapses double spaces (an empty middle-name slot renders
  as "First  Last") and strips Jnr/Snr/Jr/Sr; matching is token-AND over the
  normalised KlubPro name, so "Eadon-Clarke Jnr, Chas" finds "Chas Eadon-Clarke".
  (A genuinely *different* middle name still needs the operator to edit the
  search.)
- **In-tool auto-suggest** (v8.4): the external candidate generation only ran for
  4 clubs (Applecross/High Wycombe/Murdoch/Portland), so a newly-mapped club's
  `player_match_mappings` is empty → every player showed NO MATCH even though the
  staged candidates exist. `KlubproPlayers.load()` now name-matches client-side for
  any player with **no** pre-generated row: exact normalised-name (`nameKey` =
  sorted tokens) → auto-suggest it (SUGGESTED, bulk-approvable); **two+ same-name
  candidates** (e.g. "Grace Abbott" ×2) → flag `ambiguous` → "REVIEW · N MATCHES"
  (never auto-picked). Only fills gaps (rows that already had a generated/decided
  match are untouched), so the 4 done clubs are unchanged. Header shows
  suggested/to-review/no-match counts; filters added for each.
- **Value normalisation** (fixed v8.4 — was importing display labels verbatim):
  KlubPro stages `betterstats_*` as **human labels** ("Right handed", "Right-arm
  fast-medium", "Male") but BetterStats stores **codes** (`batting_hand` 'RIGHT';
  bowling split into `bowling_action` 'RIGHT_ARM' + `bowling_type` 'FAST_MEDIUM';
  gender 'male'). `_norm_batting_hand`/`_norm_bowling`/`_norm_gender`/`_norm_role`
  (mirroring `frontend/src/lib/playerAttributes.js`) convert on import in
  `_incoming_map`; the `bowling_type` checkbox sets **both** bowling columns. Role
  happens to be stored as its label so it always worked. Unrecognised value →
  None → treated as empty (never written). The frontend card now displays codes
  as labels + compares normalised so 'RIGHT' vs "Right handed" isn't a false diff.
  **Photo**: a normal upload sets `photo_url=/api/images/players/{id}/photo?v=…`
  and BetterSelect's avatar renders from `photo_url` — the import now sets it too
  (it had set only `photo_data`/`photo_mime`, so the public profile showed the
  photo but the admin avatar didn't). `_player_before`/rollback now also carry
  `bowling_action` + `photo_url`. **A club imported before this fix (e.g. Murdoch)
  must be re-Imported** — the normalised value differs from the stored bad label,
  so a re-run repairs every row.
- **Deploy**: set `KLUBPRO_DATABASE_URL` (never commit the pw) AND ensure
  `betterstats-backend` shares a Docker network with `klubpro-postgres`.

## BetterComms — HTML / Design / Preview editor (Jul 2026)

Template (`CommsTemplates.jsx`) and Email compose (`CommsCompose.jsx`) both used
to be a plain `<textarea>` + a read-only iframe. Both now share one editor,
`frontend/src/components/admin/EmailEditorTabs.jsx`, with three modes: **HTML**
(the textarea), **Design** (WYSIWYG), **Preview** (unchanged — server-rendered
`srcDoc` iframe, footer injected, exactly what a send produces).

- **Design mode edits the real DOM, not a schema.** Real templates are
  table-based layouts (`role="presentation"`, `cellpadding`, inline styles) for
  email-client compatibility — a schema-based rich-text library (TipTap/Quill/
  Slate) normalises content into its own document model and would strip or
  rewrite that markup on round-trip. Instead Design mode writes the current HTML
  into an iframe and sets `contentDocument.designMode = 'on'`, so the browser's
  native editing operates on the actual markup; the toolbar calls
  `execCommand` on that document. Reading the content back out
  (`serializeIframeDocument`) gets back real HTML, tables and all, modulo the
  user's own edits (browsers do normalise bare `<tr>` into an implicit `<tbody>`
  on any DOM parse — cosmetic, doesn't affect rendering).
- **Fragment vs full-document is auto-detected and preserved**
  (`isFullHtmlDoc` in `lib/htmlEmailFormat.js`, mirrors the backend's
  `_is_full_doc`). A full document (`<html`/`<body>` present — a pasted/imported
  template) edits and serializes as a full document. A fragment (a plain-text or
  simple-HTML compose body) is wrapped in a throwaway shell just for the Design
  iframe's visual editing surface (`wrapFragmentForEditing`) but only the
  fragment's inner content is read back out — so the backend's auto-wrap (club
  shell + mandatory footer) for compose bodies keeps working untouched after a
  round trip through Design mode.
- **Tidy-on-switch**: `js-beautify`'s HTML formatter (`tidyHtml`) reformats the
  code whenever a mode transition, Save, Test or Send happens with pending
  edits — leaving HTML mode always shows clean, indented markup, whether the
  edits came from raw code or from Design mode. Verified against a real
  table-based template that indentation doesn't introduce visible whitespace
  (inline elements like `<a>` inside a `<p>` are left untouched).
- **`ref.flush()` is mandatory before persisting.** `EmailEditorTabs` is a
  `forwardRef` exposing `flush()`, which synchronously returns the latest
  content (Design-iframe edits read back and tidied, or tidied code) — every
  Save/Send/Test call site must use its return value directly rather than the
  `html`/`body` state variable, since the `onChange` callback's state update
  hasn't necessarily landed yet by the time the API call fires. A debounced
  (400ms), untidied live-sync also runs while typing in Design mode so
  Send-button enablement and the unknown-`{{variable}}` warnings don't lag.
- **No backend change** — tidying happens entirely client-side before the
  existing `html`/`body_html` string fields are saved.

## Marketing Club Directory — Twenty sync fixes (Jul 2026)

Two related fixes to the super-admin Club Directory (`/admin/super/marketing`)'s
Twenty CRM integration, prompted by a live "Gateway Time-out" on Refresh
Twenty leads/tasks and a club whose direct enquiry never showed up as a Twenty
lead or engagement score.

- **Background-task pattern extended to the two Refresh buttons** (`backend/app/routers/marketing.py`).
  `/refresh-twenty-engagement` and `/refresh-twenty-leads-tasks` used to `await`
  the whole sweep synchronously — fine for a small exported-club set, but
  `twenty_client.py`'s self-imposed 90-req/60s rate limiter means a sweep over a
  meaningful number of clubs routinely exceeds nginx's default 60s
  `proxy_read_timeout` (`frontend/nginx.conf` has no override for `/api/`),
  producing a proxy-level "Gateway Time-out" — the backend kept running to
  completion regardless, the browser just gave up first. Both now follow the
  exact pattern `/export-twenty` already used (documented in its own comment,
  same reasoning): `POST` kicks off a `BackgroundTasks` runner and returns
  `{"status": "started"}` immediately; the UI polls a new `GET .../status`
  endpoint (`/refresh-twenty-engagement/status`, `/refresh-twenty-leads-tasks/status`).
  In-process module-level state dicts (`_twenty_engagement_refresh`,
  `_twenty_leads_refresh`), same shape as the existing `_twenty_export` —
  a `_bg_stale()` helper (extracted from the export's own `_export_stale()`) is
  now shared by all three. Frontend: `SuperMarketing.jsx`'s `pollTwentyExport`
  was generalised into `pollTwentyJob(statusFn, formatResult, {onDone})`, reused
  by all three buttons.
  **Bonus fix surfaced while mirroring the pattern**: `export_to_twenty` /
  `refresh_engagement` / `refresh_leads_and_tasks` all document "never raises,
  returns `{"error": ...}` instead" — but the original `_export_twenty_bg`
  stored that dict straight into `state["result"]`, so the UI's
  `formatTwentyResult` tried to format an error dict as a success shape
  (`"Exported to Twenty: undefined club(s) matched…"`) instead of showing the
  real error. New `_settle_bg(state, res)` helper (used by all three background
  runners) detects a truthy `res["error"]` and routes it into `state["error"]`
  instead, so the UI's existing `if (s.error)` branch catches it correctly —
  fixes this for the pre-existing export button too, not just the two new ones.

- **A direct "onboard my club" enquiry now immediately upserts a Company +
  Lead in Twenty at a forced Hot (100) score**, regardless of whether the club
  was ever exported before (`backend/app/services/twenty_sync.py`,
  wired from `routers/public_contact.py`). Previously, BOTH the daily 06:00/07:00
  cron jobs AND the on-demand Refresh buttons only ever touched clubs already
  in `twenty_links` — nothing in the `/public/contact` submission path (used
  identically by the short "Get your club on BetterCricket" CTA modal
  and the full Contact page, distinguished only by `source`) auto-exported a
  new prospect, so a club that enquired but was never separately exported
  showed no engagement score and no Twenty lead until someone noticed and
  clicked "Export to Twenty" manually.
  - `_resolve_onboarding_club()` finds-or-creates the `MarketingClub` +
    `MarketingClubContact` the enquiry belongs to, mirroring
    `_onboarding_signal()`'s own existing priority: the submitter's email
    against a known officer first, then an exact case-insensitive club-name
    match, else a brand-new prospect club is created from what the form gave
    us (synthetic `grassroots_guid = "manual:" + uuid5(name)` — deterministic,
    so a second enquiry from the same club upserts the same row rather than
    duplicating). Verified against a real Postgres instance: name-match reuse,
    email-match-wins-over-a-mismatched-typed-name, and no duplicate rows across
    repeated submissions.
  - `push_club_and_contacts()` gained an `engagement_override` param — when
    given, it's merged over the normally-computed `_engagement()` rollup
    (preserving the other real telemetry fields — sessions, upsell modules,
    etc. — only `engagementScore`/`engagementTier`/`inSalesCycle` are forced).
    It also switches from the existing mirror-only `_sync_lead_from_company`
    (which no-ops if the club has no Lead yet) to a REAL create-or-refresh via
    the new `twenty_leads_tasks.upsert_lead_for_club()` — a single-club
    extraction of `_seed_and_refresh_leads`'s per-club body, so a Lead is
    actually created immediately rather than only mirrored onto one that
    already exists. **Scoped to the `engagement_override` path only** — an
    ordinary campaign-send call to `push_club_and_contacts` (its original
    caller) is untouched, since `_lead_signal`'s own qualifying-signal gate
    already prevents a routine send alone from creating a Lead.
  - `push_onboarding_enquiry(club_name, contact_name, email, phone)` is the
    top-level orchestration, backgrounded from `public_contact.py`'s
    `submit_contact` alongside the existing `mark_contact_source` call — never
    raises, no-ops cleanly when Twenty isn't configured (verified).
  - The **daily 06:00 engagement / 07:00 lead refresh jobs still can't discover
    a brand-new club on their own** — they're unchanged, still scoped to
    `twenty_links`. This enquiry-triggered push is now the one path that closes
    that gap; the jobs remain correct for their existing job (keeping
    already-exported clubs' scores current day-to-day).

- **A trial — requested or started, either as a prospect or an onboarded
  club — gets the same forced Hot (100) + Lead treatment**, on top of the
  enquiry case above. Four distinct code paths all write to the same
  `trial_modules`/`requested_trial_modules`/`demo_status` (prospect) or
  `org_module_subscriptions` (onboarded) state, so each is hooked at its own
  write point rather than centralised:
  - `club_directory.set_sales_state()` — the super-admin Sales Pipeline panel
    in the Club Directory (Trialing / Requested Trial checkboxes, Demo
    dropdown). Tracks the delta of newly-added `trial_modules` /
    `requested_trial_modules` (already existed, for the `request_trial_modules`
    presync-Task queueing) and now ALSO fires
    `push_club_and_contacts(club.id, engagement_override=…)` when a module is
    newly added OR `demo_status` freshly transitions **into** `in_trial`
    (transitioning out, or re-saving the same already-in_trial state, doesn't
    re-push — verified against a real Postgres instance across 7 scenarios).
  - `club_admin.py::create_module_request` — a club's own admin self-serving a
    trial request (`kind == "trial"`) from inside the app. This is the
    "requests a trial" moment for an already-onboarded club.
  - `club_admin.py::start_module_trial` / `approve_module_request` — a super
    admin directly granting a trial, or approving a self-serve trial request.
    This is the "is put on a trial" moment. `approve_module_request` only
    forces it for `req.kind == "trial"` — a subscribe/cancel approval keeps the
    ordinary billing-fields-only push.
  - Both onboarded-club paths go through `_push_club_to_twenty(org_id,
    force_hot=True)` → `twenty_sync.push_org_company(org_id,
    engagement_override=…)`, which gained the same `engagement_override`
    param `push_club_and_contacts` has: only when given does it compute the
    real `_engagement()` rollup (merging the override on top, so the other
    real telemetry fields survive) and create-or-refresh the Lead via
    `twenty_leads_tasks.upsert_lead_for_club()` — an ordinary subscription-change
    push (activate/cancel/renewal-date edit) is untouched, still the
    billing-fields-only push it always was.
  - **Bonus fix surfaced while extending `push_org_company`**: it never
    actually called `session.commit()` — `_upsert`'s `twenty_links` bookkeeping
    (the id-mapping/content-hash dedupe row) was silently rolled back on every
    call, on every existing caller, since the function was first written. Now
    commits like every sibling push function.

- **The forced Hot 100 from a direct enquiry didn't stick.** `push_onboarding_enquiry`
  only forced `engagementScore: 100` on the ONE push it made at submission time — every
  later recompute (`refresh_engagement`'s daily 06:00 job, a BetterComms send, a manual
  "Refresh Twenty scores") called `twenty_sync._engagement()` fresh with no override, so
  a brand-new prospect with no other web/email history landed back around 30–45 (Warm)
  overnight. `_engagement()` now holds a non-customer at a flat `engagementScore: 100` /
  `engagementTier: "HOT"` for `platform_settings.get_direct_enquiry_hot_days()` (default
  **30**, `DEFAULT_DIRECT_ENQUIRY_HOT_DAYS` in `platform_settings.py` — a plain in-repo
  default, not an env var) after the most recent `club_onboarding_requests` row
  attributed to the club (`_onboarding_signal`'s own `onboarding_last`), computed on
  every call so it self-corrects on the next scheduled/manual refresh with no backfill
  needed. Ends the moment the deal is **won** (the club becomes a paying customer —
  `is_customer` routes it to the account-health formula instead) or **lost**
  (`not_interested`, which already early-returns `_engagement()` before this check is
  reached) — whichever comes first. **Super-admin managed**, not server config: a new
  Marketing section on the All Clubs "General Settings" modal (`SuperClubs.jsx`) edits
  it via `direct_enquiry_hot_days` on the existing singleton `platform_settings` JSONB
  row (migration 120 — same store as `default_trial_days`, no new migration), through
  `GET`/`PATCH /club-admin/super/general-settings`. Diagnostic-only `_directEnquiryHot`
  flag added alongside the existing `_recencyPts`/`_freqPts` breakdown (stripped before
  anything reaches Twenty — `twenty_client.py` drops every underscore-prefixed key),
  surfaced in `diagnose_club_lead.py`.

## Fill-in players on the game scorecard (v8.60.0–v8.60.3, Jul 2026)

A club fielding a borrowed player (a fill-in from another club, or a Cricket
Australia junior whose name is privacy-redacted in the feed) had that
player's entire batting/bowling contribution disappear from
`GET /games/{id}/scorecard`, and the displayed innings total silently
undercounted by exactly their runs. Reported against
`games/504937fb-dd8d-417e-8a7a-c96c36897c25`: our own second innings showed
54/3 against Grassroots' real 197/5, the gap being a fill-in's 116.

- **Root cause**: every "is this participant ours?" check in
  `routers/games.py::get_scorecard`'s live Grassroots-enrichment pass
  (`known_ids`, `our_batting_fingerprints`, `our_team_roster_pids`) requires
  the participant to already be a row in `players` — which a genuine one-off
  fill-in never is (only the season-aggregate feed mints `players` rows, and
  a borrowed player never appears there). A participant on our own team's GR
  roster but not in `players` fell through a `continue` that assumed a later
  DNB-injection step would catch them; that step only resolves players
  already in the DB by name, so it silently dropped them too. A fill-in
  *bowler* fell through even further, into `opp_bowling` (misattributed to
  the opposition). The innings total was summed from the (now-incomplete)
  displayed rows rather than read from Grassroots' own authoritative
  innings total, so it inherited the gap.
- **Fix**: a roster participant not in `players` is now rendered directly on
  our own batting/bowling card, `player_id: null` + `is_fill_in: true` (the
  same shape opposition rows already use, so the frontend's existing
  `player_id`-optional `<Link>`/`<span>` rendering needs no new branch) —
  covers batted, DNB-with-a-batting-array-entry, and DNB-with-no-entry-at-all
  cases. `_fill_in_display_name` falls back to "Fill-In" (or "Fill-In (#N)"
  by batting position) only when Grassroots has no usable name (the
  redacted-junior case, `playerShortName` literally `"********"`); a normal
  fill-in's real name is shown as-is. Our own innings `runs`/`wickets` in
  `innings_totals` now prefer Grassroots' own innings total over the row-sum
  (mirrors how opposition wickets and both sides' extras were already
  sourced), so the total is correct even if a future edge case still can't
  display a row. Frontend: `FillInBadge` in `MatchScorecard.jsx` renders a
  small amber "FILL-IN" tag next to the name on any row with `is_fill_in`.
- **v8.60.1 follow-up — the v8.60.0 fix regressed on redeploy**: the same
  reported game still showed a wrong total (202 instead of 197) and two
  fill-ins (22 and 116 runs) were still missing after v8.60.0 shipped. Two
  distinct bugs, found by pulling the live GR JSON directly
  (`grassrootsapiproxy.cricket.com.au/scores/matches/{id}?responseModifier=includeScorecard`)
  and comparing it to `/api/games/{id}/scorecard`: (1) **double-counted
  extras** — GR's `innings.runsScored` is the FULL team total (batters +
  extras), but v8.60.0 stuffed it straight into `innings_totals.runs`, a
  field that has always meant bat-only runs (the frontend adds extras on
  top separately) — fixed by dropping that substitution and instead
  recomputing `innings_totals` for our own side from the fully-populated
  `batting_flat` once every row (including newly-injected ones) is in place.
  (2) **a stale junk `players` row can already exist for a redacted
  participant** — this game had *three* CA-redacted batters, not two; one of
  them (`9cc9ec36…`) already had a `players` row and a synced
  `batting_innings` row with `display_name` literally `"********"`, which
  hits the `known_ids` branch and returns *before* reaching any of the new
  fill-in logic. Worse, once one redacted participant's DB name is
  `"********"`, every *other* redacted participant's GR name-key
  (`_name_key("********")`) collides with it in `our_batting_fingerprints` /
  `_nk_to_player`, silently swallowing them regardless of whether they're
  `known_ids` too. Fixed three ways: `_looks_redacted()` now excludes
  placeholder names from both fingerprint sets so they can't false-match;
  the `known_ids` branch now injects a **scored** row (not just a DNB one)
  when a known player has no `batting_innings` row for this game, sourced
  from GR's own stats (`our_missing_rows`, generalised from the old
  DNB-only `our_missing_dnb`); and a final pass over `batting_flat`/
  `bowling_flat` normalises ANY row whose name is unusable (blank or
  `"********"`, however it got there — a genuine fill-in or a stale DB row)
  to the same unlinked `player_id: null` + `is_fill_in: true` shape. Verified
  by replaying the real GR payload for this game through the exact loop
  logic under both possible `known_ids` states — both converge on the
  correct 192 bat runs + 5 extras = 197, 5 wickets.
- **v8.60.3 follow-up — redacted juniors were mislabelled "Fill-In"**: user
  feedback caught that a genuinely redacted junior (no name recoverable
  anywhere in the feed) was showing as "Fill-In #1"/"Fill-In (#N)" — the
  same treatment as a real borrowed player with a known name, which
  misrepresents an unknown identity as a known-but-unregistered one and
  breaks the `********` convention clubs already recognise. Split the old
  `_fill_in_display_name` into `_classify_unlinked_name`, returning
  `(display_name, is_fill_in, is_redacted)`: a redacted participant (blank
  or all-asterisks GR name) always renders literally as `"********"` with
  `is_redacted: true` and no badge; only a genuine fill-in with a real GR
  name gets `is_fill_in: true` + the FILL-IN badge. The final
  redacted-DB-row normalisation pass (see the v8.60.1 note above) was
  simplified to always set `is_redacted` (it only ever fires on a name that
  already failed `_looks_redacted`, so there's nothing to classify).
- **Not done this round**: `Partnership` has no free-text-name column (unlike
  `FallOfWicket.batter_name`), so a fill-in's side of a partnership still
  reads "Unknown" — would need a migration to fix properly. Fielding has no
  live-GR merge in this endpoint at all (DB-only), so a fill-in's catches
  aren't backfilled live. Sync (`sync_grassroots_game_level_data`) still
  gates `batting_innings`/`bowling_spells`/`fielding_stats`/`game_appearances`
  inserts on `our_team_pids`, so a fill-in still never lands in the stored
  per-game tables — this fix is live-view-only (the endpoint already
  re-fetches Grassroots on every request regardless of sync state, so no
  re-sync is needed for it to take effect). Also raised but not built: an
  admin flow to edit a fill-in's name, promote them to a real `players` row,
  and match them to a PlayHQ profile via a pasted profile URL — the fill-in
  row now carries a stable `participantId` internally, which is the piece
  that flow would need, but the UI/endpoint itself wasn't scoped in.

## Fill-in players: partnerships/fielding toggle + claim-a-fill-in (v8.61.0, Jul 2026)

Follow-up to the fill-in scorecard fix above (v8.60.x), extending it two ways.

- **Club-level toggle for partnerships/fielding** (migration 147): a fill-in's
  runs/wickets always show on the batting/bowling card, no toggle. Whether
  their name also shows in the lower-stakes partnerships and fielding cards
  on that same scorecard is a new org setting, `include_fill_ins_in_stats`
  (default **on**), edited via the existing `/club-admin/settings` GET/PATCH
  (`SettingsPatch`) and a new checkbox in `AdminSettings.jsx` ("Fill-in
  players" section). Schema mirrors `FallOfWicket.batter_name`:
  `partnerships.batter1_name`/`batter2_name` and `fielding_stats.player_name`
  (nullable, set only when the linked id is NULL), with matching always-NULL
  columns on `manual_partnerships`/`manual_fielding_stats` purely so the
  `v_effective_*` union views' column lists still line up.
  `fielding_stats.player_id`'s FK was also changed `ON DELETE CASCADE` →
  `SET NULL`, matching every other player-linked per-game table (it was never
  actually nullable in practice before this, just inconsistent).
- **Sync-side capture** (`sync.py`): a new `our_team_roster_guids` set (raw
  GR participantId strings, not just resolved player ids) lets the
  partnership/fielding insert loops tell "one of ours, just unregistered"
  apart from "genuinely the opposition's" — a plain `None` from `_team_pid`
  can't distinguish the two on its own. `_derive_partnerships_grassroots` now
  also returns `batter1_name`/`batter2_name` (sourced from the same raw
  batting-row `playerShortName` already in scope). A partnership is only
  dropped now when **neither** side resolves to an id **or** a name (was:
  dropped whenever either side had no id) — so two fill-ins batting together
  no longer vanish entirely. Fielding for a fill-in is captured the same way
  instead of being unconditionally skipped.
- **Read-side gating** (`games.py`/`aggregations.py`): `get_game_partnerships`
  extends its existing name COALESCE chain
  (`display_name_override → name → batterN_name`) one more step, matching
  `get_game_fall_of_wickets`'s pattern. `get_scorecard` loads the org once
  (`include_fillins_stats`) and applies it after the fact: fielding rows with
  no `player_id` are only emitted when the toggle is on (and their name run
  through the same `_classify_unlinked_name` used for batting/bowling, so a
  CA-redacted fielder still reads as `********`, never "Fill-In"); partnership
  rows have their fallback name stripped back to NULL when the toggle is off,
  or classified the same way when it's on. **Records are unaffected either
  way** — `records.py`'s partnership/fielding leaderboards already inner-join
  through `players` scoped to the org, so a NULL `player_id` row was always
  invisible there regardless of this feature; confirmed via the research
  pass, no extra guard needed.
- **Claim-a-fill-in** (`players.py`, `POST /players/claim-fill-in`, cap
  `MANAGE_PLAYERS`): promotes a fill-in scorecard row into a real `players`
  row, reusing sync's `_resolve_org_player` identity scheme standalone (id =
  the raw GR participant GUID, or `uuid5(org, guid)` only on a genuine
  cross-club collision; `grassroots_id` = the raw GUID) so a later sync
  recognises the row by `(org, grassroots_id)` and attaches to it instead of
  minting a duplicate. Re-claiming the same participant is idempotent (finds
  the existing row by `grassroots_id`, updates the name). An
  `existing_player_id` in the request means the fill-in turned out to already
  be a registered player under a mismatched GR uuid — delegates straight to
  the existing `admin.merge_players` (called as a plain function with
  explicit `db`/`current_user`, bypassing its `Depends()` — merge_players
  already handles the reassignment/de-dup across every per-game table,
  including the exact cross-club-shared-GUID case, no reason to reimplement
  it). `players.claim_note` (new nullable column, same migration) holds an
  optional free-text reference the admin leaves when claiming — e.g. a pasted
  PlayHQ profile link — **stored verbatim, not parsed or verified**.
  `games.py`'s three fill-in row-construction sites now also emit
  `grassroots_participant_id` (previously computed internally but never
  serialised) so the frontend has something to submit back.
- **Why no PlayHQ-URL auto-resolution**: investigated and shelved. PlayHQ's
  player-profile pages are a client-rendered SPA behind CloudFront bot
  protection — both plain curl and headless Chromium (proxied through this
  environment) got blocked, consistent with the existing "UK Expansion" note
  elsewhere in this file about Play-Cricket needing a real browser network
  capture to find API shapes. Worse, the example URL used to investigate this
  (`.../game-centre/c226ff54`) carries a short obfuscated code, not the real
  GUID — the same short-code-vs-real-GUID gap already known for game ids — so
  even a successful fetch likely wouldn't yield something resolvable to the
  actual Grassroots participant id without an authenticated API this project
  doesn't have. Building a parser that looks automatic but silently can't
  verify anything would be worse than not building it — hence `claim_note`
  being a plain stored string instead.
- **Frontend**: `MatchScorecard.jsx` gains a `CLAIM` button next to any
  `is_fill_in` row (never `is_redacted` — nothing to claim on an unknown
  identity), gated on `hasCapability(CAP.MANAGE_PLAYERS)` via the same
  inline-on-a-public-page pattern `PlayerProfile.jsx` already uses (the page
  has no other auth surface — `get_scorecard` itself stays fully
  unauthenticated). `ClaimFillInModal` — name field, an existing-player
  search (client-side filter over `adminListPlayers()`, fetched once only
  when `canManage`), and the reference-note field. Also fixed while touching
  this: `PartnershipsSection` used to assume "has a name ⇒ has an id" and
  linked to `/players/${batterN_id}` unconditionally whenever a name was
  present — broke (linked to `undefined`) the moment a fill-in could have a
  name with no id, which this feature introduces; now checks the id first.

## Scorecard endpoint rewritten to trust Grassroots, not our own DB, for both teams (v8.78.0, Jul 2026)

Reported: a scorecard's header total didn't match its own batting card (e.g.
"30/1" in the header while the card below it showed seven dismissals — the
real score was 135/7), and a bowler occasionally appeared twice with
identical figures, once linked correctly and once as a bogus "FILL-IN" row
with a CLAIM button.

**Root cause of the wrong total**: `get_scorecard`'s live GR-merge (see the
fill-in notes above) decided whether a participant was "ours" by checking
`pid in known_ids` — is this GUID a `players` row *anywhere* in our org —
before ever checking which team's roster they were actually listed under for
*this match*. A player registered with the club who guested for the
opposition that day (confirmed against the raw GR payload: he's listed only
on the opposing team's roster) got swept onto our own card by that check,
which made the innings-total logic think it already had complete data for
that innings and stopped it from ever falling back to GR's own authoritative
total, wickets included.

**Root cause of the duplicate bowler**: GR can report a different
`participantId` for the same real bowler than the one already stored (the
same MyCricket/PlayHQ dual-GUID class of issue documented elsewhere in this
file), and only the batting side of `get_scorecard`'s merge had a name-based
fallback for that case (`_unresolved_roster_pids` → `_nk_to_player`). The
bowling loop and the first-pass batting DNB-detection loop had no such
fallback, so an unrecognised GUID on our own team's roster fell straight
through to the "unregistered fill-in" branch and rendered as a second,
duplicate row instead of resolving to the existing player.

**Fix — inverted the whole function's precedence.** `get_scorecard` no
longer treats our stored `batting_innings`/`bowling_spells` rows as primary
and reaches for Grassroots only to patch gaps. When the live GR fetch
succeeds (true for essentially every non-manual game — the same `/scores/*`
endpoint reaches back to the 1970s), **both** teams' batting, bowling and
innings totals are built entirely from that response. Team membership is
decided purely by GR's own team roster listing for that match
(`our_team_roster_pids`/`opp_roster_pids`, matched on the org's name against
the GR team name — unchanged from before) — never by whether a GUID happens
to match a `players` row. Our own player table is now consulted for exactly
one purpose: `_resolve_linked_id(pid_str, name)` tries the literal id, then a
new `grassroots_id` lookup, then a name-key match, purely to attach a
`player_id` for a profile hyperlink on rows already classified as ours — it
can never move a row to the other side or change its numbers. Innings
totals now uniformly prefer GR's own `numberOfWicketsFallen`/`totalExtras`
for both sides (previously only the opposition innings got this treatment);
bat-only `runs` is still summed from individual rows, never substituted with
GR's full-team `runsScored`, which would double-count extras once the
frontend adds them.

The DB-sourced batting/bowling/totals built earlier in the function are only
swapped in after the entire GR-sourced rebuild completes without error — a
GR outage or any exception leaves the page showing the last-synced copy
instead of erroring, same resilience as before.

**Consequence for the fill-in feature above**: a DNB roster member who
resolves via the new name fallback (like the O'Kane/Singh case) now renders
as a normal linked row instead of a fill-in with a CLAIM button — CLAIM is
reserved for participants who genuinely have no `players` row.

**Verified against the reported game** by replaying the fix's exact logic
offline against the real Grassroots payload (`/scores/matches/{id}` fetched
directly, bypassing the app): the misattributed player's innings now lands
on the opposition card as intended, the header total reads 115+20 extras =
135 runs for 7 wickets (matching GR's own authoritative figures, and
consistent with the winning team's actual chase target), and the duplicated
bowler's figures appear exactly once, correctly linked. Not done this round:
`fielding_stats` stays DB-only in this endpoint (no live GR fielding merge)
— a known pre-existing gap, unrelated to this fix, flagged as a possible
follow-up.

**Follow-up (same day) — the scorecard cache had no expiry.** After the fix
above deployed, the reported game still showed a wrong, DIFFERENT wrong
total ("16/0" this time, with one side's whole batting card missing).
Re-fetching Grassroots directly (repeatedly, with the app's own request
shape) confirmed the live upstream data is correct and has been stable —
135/7, 20 extras, full batting rows both sides — so the corrupted output
wasn't coming from Grassroots or from the rewritten merge logic. It was
`grassroots_scores_client._scorecard_cache`: an in-process, no-TTL,
never-invalidated cache keyed by match id. Once a match's scorecard is
fetched, that exact response is served forever for the life of the backend
process. A club scorer correcting this match on Grassroots' side got caught
mid-save at some point (an innings with its totals present but its batting
rows momentarily empty is the signature — exactly what's visible in the
symptom), and that half-saved snapshot got pinned permanently the moment
anything first requested this match. `get_match_scorecard` now takes a
`_SCORECARD_TTL` of 15 minutes (`get_grade_ladder` already had this pattern
for the same reason — "ladders move ~weekly, an hour keeps the proxy happy"
— the scorecard cache just never got the equivalent treatment), plus a
`_scorecard_looks_incomplete` guard: a response with an innings that reports
real totals but zero batting rows is never cached at all, so a mid-edit
snapshot can't get pinned even briefly — the very next request retries
instead. `force=True` was also added, matching `get_grade_matches`'s
existing param, for any future caller that needs to explicitly bypass the
cache. This bug predates the rewrite above and would have been silently
capping the OLD merge logic's live-GR data too, on whichever match happened
to be fetched during an in-progress correction.

**Second follow-up (same day) — the cache fix above wasn't the actual cause
of the "16/0" symptom; the real bug was a crash.** After the cache fix
deployed, the page still showed the same wrong total. Repeated, interleaved
checks against Grassroots directly and against our own `/scorecard` and
`/scorecard/gr-debug` endpoints proved the upstream data was correct and
stable on every single check, while `/scorecard` was stable and WRONG on
every single check — impossible if the two endpoints (which share the exact
same `get_match_scorecard` call) were both reading live data normally. The
timing gave it away: `/scorecard` took a full ~1-1.5s per request (a genuine
live fetch, not a cache hit), yet still returned the pre-rewrite DB-only
shape (dismissal text truncated to the DB's own short form, the opposition
side entirely absent, extras undercounted at 16 — exactly the sum of our own
bowlers' wides+no-balls, with no byes/leg-byes, which is what the *old*
pre-rewrite code computed from stored rows alone).

Root cause: `org_word = (org.name or "").lower().split()[0] if org.name else
""` dereferenced `org.name` without checking `org` was truthy first. `org`
being `None` is an anticipated, already-handled state two lines above it
(`include_fillins_stats = ... if org else True`) — grade/season resolve
fine but the season's `organisation_id` doesn't always resolve to a live
`Organisation` row. The `AttributeError` this threw was inside the same
`try` the whole rebuild lives in, so it was swallowed by the generic
`except Exception` and silently fell back to the DB-only pre-rewrite
rendering — reproducing the *original* bug this whole fix was meant to
solve, indistinguishable from the outside from "the fix didn't deploy".

Fixed two ways, not just one: (1) the `if gr_data and org:` guard became
`if gr_data:` and the null-unsafe `org.name`/`org.id` reads are now properly
guarded, so the rebuild no longer requires `org` to resolve at all — losing
the org lookup should only mean losing the ability to hyperlink a name to a
profile, never losing the rebuild itself. (2) Team classification (which GR
team is "ours") no longer leans on `org.name` substring-matching as the
*primary* signal at all: it now checks first whether either team's roster
overlaps with names we already have a stored batting/bowling row for on this
exact game (`batting_rows`/`bowling_rows`, queried earlier in the function
regardless of org resolution) — a signal that's true by construction (sync
only ever writes rows for our own team) and doesn't depend on the
grade→season→org chain resolving at all. `org_word` matching is now only the
fallback for a game with zero prior synced rows to compare against (i.e. the
very first time it's ever viewed). Verified offline against the real
payload with `org_word` forced empty (simulating the exact failure): the
DB-overlap signal alone correctly picks Mulgrave as "ours" (11/12 roster
names match) with no org lookup involved at all.

**The pattern worth remembering**: a broad `except Exception` around a large
rebuild is good for resilience against a flaky upstream, but it also hides a
genuine bug in the rebuild itself behind the SAME "fall back to the old
data" behavior — from the outside, "GR is down" and "our own code just
crashed" look identical. Anything added inside a block like this needs the
same null-safety discipline as the rest of the function, since a silent
`except` won't surface a shortcut taken in a hurry.

**Third follow-up (same day) — the org fix above deployed clean but the bug
was STILL live; this was the real remaining cause.** After confirming (via
`docker exec ... grep`) that the org-safety fix was genuinely running in the
container, the page still showed the exact same wrong numbers. The container
logs (`docker compose logs betterstats-backend`) had the answer directly:
`sqlalchemy.exc.ArgumentError: Column expression, FROM clause, or other
columns clause element expected, got <property object at ...>` on
`select(Player.id, Player.grassroots_id, Player.display_name)`.
`Player.display_name` is a Python `@property` (`display_name_override or
name`, see the `Player` model in `models/db.py`), not a mapped column —
accessing it at the class level (as `select()` does) returns the property
descriptor object itself, not something SQLAlchemy can query. This has
nothing to do with `org` or team classification; it's a straight query bug
in the player-linking lookup added by the original rewrite, and it fired on
every single request, every time, regardless of which of the two prior
fixes was live — which is exactly why "no change whatsoever" kept being the
honest, correct observation from outside. Fixed by selecting the two real
columns behind it (`display_name_override`, `name`) and computing the same
`or` fallback in Python. No offline test caught this because the earlier
verification replayed the row-construction logic in plain Python against a
hand-fetched JSON payload — it never touched a real SQLAlchemy `select()`,
so a query-construction bug like this one was invisible to it. `py_compile`
doesn't catch it either, since `Player.display_name` is syntactically valid
Python; the error only exists at the SQLAlchemy-semantics level and only
throws when the code path actually executes.

**Diagnostic order that actually worked, for next time**: (1) confirm the
deployed code is genuinely the code you think it is (`docker exec ... grep`
for a distinctive string — cheap, and rules out an entire class of "is my
fix even running" confusion in one command); (2) if the code IS current and
the bug persists, go straight to `docker compose logs <service> --since Nm |
grep -A 30 "<your own log line>"` rather than re-reading the source again —
a real traceback finds a bug in seconds that a fourth static read of the
same function won't.

## Match scorecard page redesigned around the SC3 Dashboard layout (v8.79.0, Jul 2026)

Once the data fixes above were confirmed correct against the live site,
`MatchScorecard.jsx` was restructured to follow the layout of BetterSocials'
`SC3_Dashboard` share-card template (`frontend/src/social/cricket-templates.jsx`),
per direct request — toss and Player of the Match were dropped from the
adaptation since neither is data we hold (no toss column, see the "UK
Expansion" note elsewhere in this file on why toss isn't captured from the AU
`/scores/*` feed either; no MOTM field anywhere in the schema).

- **`MatchHeader`** shrank from a 3-column hero strip with giant score
  numbers to a single lean meta card: grade/season on one line, the result
  pill + `{winning_team} won by N wickets/runs` on the next (margin computed
  client-side by `marginText()` from the two innings' own totals — chasing
  side won ⇒ `10 - their_wickets` wickets in hand; defending side won ⇒ the
  runs difference — since the backend has no pre-written margin string), date
  + venue off to the side. The old toss/umpires strip is gone (those fields
  are never populated).
- **`BattingCard` + `BowlingCard` merged into one `TeamCard`** — matching
  SC3's actual per-team layout: a badge (initials, since we hold no team
  logos) + innings label + team name + big score in the card header, the
  batting table with extras inline underneath, then — nested in the SAME
  card, not a separate row further down the page — the opponent's bowling
  figures, labelled `"{OPPONENT} BOWLING"`. This maps directly onto the
  existing data shape: `innN.bowling` was already "whoever bowled during this
  innings" (i.e. the opponent's figures), so nesting it under `innN`'s own
  `TeamCard` needed no new field, just moving where it renders. Each card
  also now shows overs faced next to the innings label (`sumOversBalls` +
  `ballsToOversStr`, previously computed only for the old header's now-removed
  RR line — reused rather than left dead).
- The main render dropped its "batting row, then a separate bowling row"
  two-`<div>` structure for a single side-by-side grid of two `TeamCard`s.
  Fall of wickets and partnerships stay as their own full-width sections
  below, unchanged — SC3 doesn't have either, but nothing here asked for
  their removal, and dropping working features wasn't part of the brief.
- **Verified visually, not just by build.** `npx vite build` alone would only
  catch syntax errors, not a wrong layout — so the local dev server's `/api`
  proxy was pointed at the live production API for one throwaway session
  (`vite.config.js` target flipped to `https://betterat.cricket`, restored
  after), and the actual rendered page for the reported game was screenshotted
  via the `playwright` CLI. Confirmed against play.cricket.com.au's own page
  for the same match: 135/7 and 136/4 in the right cards, "Mulgrave Brian
  Bolton Realty won by 6 wickets" computed correctly, 35.0 / 31.3 overs
  matching CA's own display, opponent bowling nested correctly under each
  team with no duplicate rows.

### Club crests + match-summary header restored (v8.79.1, Jul 2026)

Two follow-ups on the SC3 redesign above, per direct request.

- **Team logos, live from Grassroots.** `get_scorecard`'s existing GR-merge
  already fetches `teams[]` for roster/name matching — it now also pulls a
  logo per team into `gr_team_logo_by_id`. The team object itself carries no
  logo field; a live payload check found it nested under
  `owningOrganisation.logoUrl` (the grade-level "team" — often a sponsor name
  — is owned by the actual club, which holds the crest). A bare
  `logoUrl`/`logo`/`imageUrl`/`image` fallback chain is kept on the team
  object itself too, matching the existing precedent in
  `admin.py::build_team` (the BetterSocials match-import) for a
  differently-shaped response. For whichever side is ours, our own uploaded
  org logo (`org.logo_url`, else `/images/organisations/{id}/logo` if we
  hold the raw bytes — same precedence `social_rounds.py::_club_dict` uses)
  takes priority over GR's, since it's controlled and always-available when
  set. Threaded onto `innings_totals[n].logo_url` alongside the existing
  `batting_team` name, so the frontend reads it the same way. Neither source
  is guaranteed present — a hotlinked hit can 404 — so `TeamBadge.jsx`'s
  `<img>` falls back to an initials badge on `onError`, the same graceful
  degradation BetterSocials' own share-card templates already rely on.
- **`MatchHeader` restored to a full match-summary strip** — the 3-column
  HOME/RESULT/AWAY hero from before the SC3 rewrite, kept alongside the
  competition line and computed winning margin the rewrite added. Each side
  now also carries its crest (`TeamBadge`, shared with the per-team cards
  below) next to the team name. The per-team `TeamCard`s are unchanged; the
  header duplicating their score is intentional, not a regression — the
  reference site itself (play.cricket.com.au) shows the same score both in
  its top summary and again in the innings detail below.

### Winner clarity + explicit home/away-vs-batting-order split (v8.79.2, Jul 2026)

Feedback on v8.79.1: the winner wasn't obvious at a glance, and the two
sections' ordering rules needed to be pinned down explicitly rather than
left implicit. Per direct instruction: `MatchHeader` stays home-left/
away-right always (unrelated to who batted first or who won); the `TeamCard`
row below it stays ordered by batting sequence (1st innings left, 2nd
right) — this was already how it worked, since `inn1`/`inn2` in the main
component come from sorted `inningsNums`, but nothing said so explicitly
before, which is how the header nearly ended up matching it instead
(reverted mid-build after being pointed out).

- **`WinnerTag`** — a small green "✓ WON" pill (reusing `--pb-positive`,
  the same win-green `ResultPill` already uses for `WIN`), rendered next to
  the winning team's name in both `MatchHeader`'s `Side` and `TeamCard`,
  plus a light green tint on that side's background in both places. Winner
  match is `teamsMatch(game.winning_team, teamName)`, computed independently
  in each component off the same `winning_team` string — no shared state
  needed since both already receive it (`MatchHeader` via `game`, `TeamCard`
  via a new `winner` prop threaded from the main component).

### Cross-club player leak in scorecard team classification (v8.79.3, Jul 2026)

Reported on a DIFFERENT match (Applecross 1st XI vs Pentagon-NBCCC 1st XI):
both teams' crests showed as the same club's logo, and most of Pentagon's
batters rendered as "FILL-IN" with a CLAIM button — except two of them, who
showed as fully linked Applecross players.

**Root cause**: `_our_tid` (get_scorecard's "which GR team is ours" decision,
see the rewrite above) tries the DB-overlap signal (does either team's roster
overlap names we already have a stored row for on this exact game) before
org-name matching. Two of Pentagon-NBCCC's players — real people who had at
some point also played for Applecross — had old `batting_innings` rows
already stored under Applecross for this exact game (their own separate
data-integrity issue, not fixed here — see below), so DB-overlap scored
Pentagon-NBCCC 2 and Applecross 0, and `max()` picked Pentagon-NBCCC as
"ours". Every one of their actual teammates then correctly failed to
resolve against Applecross's roster and rendered as a fill-in, while the two
contaminated names resolved to their (real, but wrong-context) Applecross
`players` rows — and the crest swap followed directly from the same
misclassification.

**Fix**: swapped the precedence — org-name matching is now the PRIMARY
signal (it can't be fooled by a few contaminated rows the way a raw overlap
count can), with DB-overlap only as the fallback for when org itself can't
be resolved at all (the original `org.name`-crash scenario two sections up).
Verified offline against the real payload for this match: org_word alone
correctly picks Applecross even with the 2-vs-0 contaminated overlap still
in play.

**A deeper, separate bug found while investigating**: `get_game_fall_of_wickets`
and `get_game_partnerships` (`services/aggregations.py`) joined `players` on
`player_id` with **no organisation scoping at all** — a fall-of-wicket or
partnership row whose stored `player_id` happens to belong to another club's
roster (the same "shared GUID"/prior-registration class of issue as above)
rendered as if it were one of ours. For fall of wickets specifically this
also produced literal duplicate rows per wicket — one correct unlinked row
(GR short name, no `player_id`) and one wrongly cross-club-linked row for
the same wicket, both stored, both returned. Fixed both functions to accept
an `org_id` and scope the `players` join to it (`AND (:org_id IS NULL OR
p.organisation_id = :org_id)`, so a caller with no org context is
unaffected); `get_game_fall_of_wickets` also now deduplicates by
`(innings_number, wicket_number)` after the org-scoped query, keeping
whichever of the two stored rows has a usable name. A row that loses its
link this way and has no stored free-text fallback name renders as
"Unknown" on the frontend (already-existing behaviour) — a real gap, but
never the wrong person's name.

**Not fixed, flagged for follow-up**: `records.py`'s partnership leaderboard
query (`top_partnerships`) requires BOTH batters' `organisation_id` to match
the viewing club — which sounds safe, but isn't, for exactly this case: the
two contaminated players' `players` rows ARE genuinely org-scoped to
Applecross, so a stand like theirs from a match they didn't actually play
for Applecross in can still surface on Applecross's own records page as a
phantom top partnership. This wasn't chased further today — scope is
"how many historical games/players are affected platform-wide", which needs
a proper audit (and likely a sync-side fix, not just a read-side one) beyond
what one reported match justifies investigating alone.

Yearbook generation was previously **100% manual** — two separate admin
buttons (Generate stubs, Generate narrative) plus a Publish button, with the
only automatic step being an at-startup stub-only sweep (`generate_all_stubs`,
called once from `main.py`'s lifespan). A user expected a Full Rebuild to
auto-generate yearbooks for the last 3 seasons; it never had, since nothing in
`sync_organisation`/`hard_refresh_org` ever called into `routers/yearbooks.py`.
This was a documented-but-unbuilt idea (`docs/self-serve-trial-onboarding-plan.md`
Decisions 12/13, Phase 22 — scoped there to the not-yet-built self-serve
onboarding wizard, not the existing per-club rebuild button), not a regression.

- **`routers/yearbooks.py`**: `generate_narrative` was split into a thin route
  plus a reusable `_generate_narrative_core(db, org_id, season_id)` (same
  rate-limit/API-key/import checks, same body) so it can be called directly
  from a background task, not just over HTTP. New
  `auto_generate_and_publish_recent_yearbooks(db, org_id, count=3)`: ensures
  stubs exist, finds the org's last `count` seasons that actually have
  `player_season_stats` rows (`_last_n_seasons_with_stats`, same recency
  ordering as `_season_sort_key`), and per season generates the narrative
  (promoting `ai_draft` → `content_markdown`, since only `content_markdown` is
  what actually renders) and publishes — **unless that season already has
  narrative content**, so a later rebuild never clobbers an admin's hand
  edits. A season is still published even if narrative generation fails (no
  `anthropic_api_key` configured, rate-limited, transient error) — errors are
  caught per-season and logged, never raised, matching the onboarding-plan's
  accepted "auto-publish, no draft gate" call.
- **`routers/club_admin.py::hard_refresh_org`**: the new call sits inside the
  `_run()` background task's **true-success branch only** (right after
  `await finish_sync_run(run_id, stats)`, not the "wiped but 0 matches came
  back" error branch), in its own `try/except` with a fresh
  `async_session_maker()` session — mirrors the existing post-sync `ANALYZE`
  block's isolation pattern, since a yearbook failure must never look like a
  sync failure (the sync's success has already been recorded).
- **Scope, per direct instruction**: Full Rebuild only — plain "Sync Now" does
  not trigger this (rebuild is the "real completion signal" the shelved plan
  called for; a routine weekly sync isn't).

## Billing checkout — feature-flagged while it's built (v8.65.0, Jul 2026)

The Account page's SUBSCRIBE button (`AdminAccount.jsx`, Phase 19) has always
been a deliberate stub ("Online subscribing isn't connected yet…"). Work is
now starting on the real thing — preparing bills/invoices, then a Stripe
checkout link — and per direct instruction a Primary Admin must **not** be
able to click through any of it until the team is satisfied it works, even as
pieces of the real flow land on `main`.

- **`platform_settings.billing_checkout_enabled`** (new boolean key in the
  existing `_BOOL_KEYS` allowlist, same JSONB singleton as
  `self_serve_registration_enabled`/`onboarding_wizard_enabled`/
  `trial_nudges_enabled` — no migration needed). Off by default.
  `get_billing_checkout_enabled(db)` reads it; **`require_billing_checkout_enabled`**
  is a ready-to-use FastAPI dependency (`Depends(require_billing_checkout_enabled)`)
  that 403s a route while the flag is off — **every new invoicing/Stripe-checkout
  endpoint must depend on it as it's built**, since the frontend gate is UX
  only and can't be trusted as the real block.
- **Super admin control**: `GET`/`PATCH /club-admin/super/general-settings`
  carries `billing_checkout_enabled` alongside the other flags; a "Billing (in
  progress)" toggle in `SuperClubs.jsx`'s General Settings modal.
- **Frontend**: `GET /club-admin/account/plan` now returns
  `billing_checkout_enabled` alongside `modules`/`is_primary_admin`.
  `AdminAccount.jsx`'s `submitSubscribe` is where the real checkout call will
  eventually go — for now it always shows the stub notice, but the flag and
  its comment are already in place so the real implementation branches on
  `plan.billing_checkout_enabled` from the start instead of needing a
  follow-up safety retrofit.
- **Turning it on**: only once the invoicing/checkout build is tested and
  ready to go live — flip `billing_checkout_enabled` on from General
  Settings. There is no staging environment, so (same as the other
  self-serve-onboarding flags) this switch is the only thing standing between
  "merged" and "a real club paying through it".

## Stripe Checkout — recurring subscription billing (migration 150, Jul 2026)

The real build behind the flag above: a Primary Admin's selected modules
become a single recurring **Stripe Subscription** per club (one Stripe
Customer/Subscription covers every module the club buys through Stripe, not
one subscription per module), priced from the SAME numbers as the public
pricing calculator. Everything here is still gated by
`platform_settings.billing_checkout_enabled` (off by default) — this schema
and code can sit on `main` fully inert until a super admin flips it on, and
Stripe keys are configured.

- **`services/billing_pricing.py`** is a hand-kept Python port of
  `frontend/src/data/pricing.js` (`CORE` $399, the four `PRICED_MODULES` at
  $149/$149/$149/$249, `BUNDLE_DISCOUNT` $0/$0/$48/$97/$146, `FANTASY` $49
  priced standalone outside the bundle). `price_for(selected_keys)` is the ONE
  place both the invoice-preview quote and the real Checkout Session line
  items are computed from — no separate "what Stripe charges" number to drift
  out of sync with "what the app shows". Verified against pricing.js: Core +
  all four modules totals **$949**, matching `ALL_IN`. Keep both files in sync
  by hand; there's no shared build step between the Vite frontend and FastAPI
  backend.
- **No pre-created Stripe Price objects** — `services/stripe_client.py`
  builds each Checkout Session line item from `price_data` on the fly
  (recurring, `interval: year`, `unit_amount` from `billing_pricing`), so a
  new module or a price change never needs a matching dashboard edit. The
  bundle discount, when any, is applied via a cached `duration: once` Coupon
  (see "Bundle discount coupon fixes" below — this used to say `forever`,
  which was wrong).
- **Migration 150** (mirrored idempotently in `main.py`'s lifespan, same
  pattern as every recent migration): `organisations.stripe_customer_id` /
  `.stripe_subscription_id` (set by the webhook once a checkout completes),
  and `billing_invoices` — a local mirror of each Stripe Invoice event so the
  Account page's Billing History never calls the Stripe API directly.
  `billing_invoices.line_items` is OUR OWN `price_for()` snapshot at the
  moment the invoice landed, not Stripe's own line items, so it always reads
  in the same module/price shape the rest of the app uses.
- **Entitlement still lives entirely in `org_module_subscriptions`**
  (migration 118) — a successful Stripe payment just calls the SAME
  `module_subscriptions.set_status_billing`/`remove_billing` writers the
  existing super-admin "approve a subscribe/cancel request" flow already
  uses (`club_admin.py::approve_module_request`). There is no separate
  Stripe-only entitlement path to keep in sync.
- **`routers/billing.py`** (`/club-admin/billing/*`, gated by
  `Depends(require_billing_checkout_enabled)` on `/quote` and
  `/checkout-session` — NOT on `/invoices`, so a club that has already paid
  can always see its own billing history even if the flag is later switched
  off for new signups): `POST /quote` previews a selection with no Stripe
  call (pure `price_for()`); `POST /checkout-session` re-validates the
  primary-admin gate server-side (mirrors `cancel_own_module`'s pattern) and
  that none of the selected modules are already a live paid subscription,
  then returns a real Checkout Session URL to redirect to.
- **`routers/public_stripe.py`** (`POST /public/stripe/webhook`,
  unauthenticated by necessity — trust comes from verifying the
  `Stripe-Signature` header locally against `STRIPE_WEBHOOK_SECRET`, the same
  "verify the signature, not a login" posture `routers/public_ses.py` uses for
  inbound SNS events) is the **only place entitlement is actually granted** —
  the frontend's post-checkout redirect is UX only (shows a status, re-fetches
  the plan after a short delay). Handles `checkout.session.completed` (grants
  immediately, using the fresh subscription's period end as the renewal date),
  `invoice.paid` (rolls renewal_date forward on every renewal, reactivates a
  `past_due` module, upserts the `billing_invoices` row — idempotent on
  `stripe_invoice_id` so a replayed event is safe), `invoice.payment_failed`
  (moves the affected modules to `past_due` — a grace period, not an instant
  cutoff, matching the existing `ACTIVE_STATUSES` semantics), and
  `customer.subscription.deleted` (drops every module the subscription
  covered, same end state as the in-app self-service cancel). Deploy note:
  register this URL in the Stripe dashboard as
  `https://betterat.cricket/api/public/stripe/webhook` (nginx strips `/api`).
  A handler failure returns 500 so Stripe retries, rather than silently
  swallowing a failed entitlement write.
- **`org_id` + the selected billing keys round-trip through Stripe's own
  metadata** (the Checkout Session's `client_reference_id`/`metadata` AND the
  Subscription's own `metadata`) rather than a custom signed-state JWT (the
  pattern Square's OAuth callback uses, `routers/merch.py::sign_square_state`)
  — Stripe already carries `metadata` through the whole
  session/subscription/invoice object graph, so the webhook never needs a
  second lookup against our own DB to know what was bought.
- **Settings** (`config/settings.py`, mirrors the Square block's shape):
  `stripe_publishable_key` / `stripe_secret_key` / `stripe_webhook_secret` /
  `stripe_currency` (default `aud`), a `stripe_configured` property (blank
  keys = every billing call raises `StripeNotConfigured`, turned into a clean
  503 rather than a raw SDK traceback), and `stripe_checkout_success_url` /
  `stripe_checkout_cancel_url` computed from `public_base_url`.
- **Not built this round**: a Stripe Customer Portal link (self-service
  card update / cancel from the Stripe side) and per-club Stripe tax
  handling — both natural follow-ups once the base flow is verified end to
  end with real keys.
- **One club, one Stripe Subscription — never a second, parallel one.** A
  Checkout Session in subscription mode always creates a brand NEW Stripe
  Subscription; it can't add items to one that already exists. Originally
  (this section used to say) `/checkout-session` just 409'd outright once a
  club had a live subscription, to avoid a double-billed Core and an orphaned
  original. **v2 (below) replaces that outright block with the real
  feature** — adding modules to the existing subscription instead of ever
  creating a second one.
- **Webhook delivery order isn't guaranteed** — `invoice.paid` for a brand-new
  subscription's first invoice can arrive before `checkout.session.completed`
  has stamped `stripe_subscription_id` onto the org.
  `stripe_billing._resolve_org_for_subscription` falls back to fetching the
  subscription and reading its own `metadata.org_id` when the org isn't found
  by `stripe_subscription_id` yet, and self-heals by stamping it — otherwise
  that first invoice would silently never show up in Billing History even
  though entitlement was still granted correctly via `checkout.session.completed`.

### Adding modules to an already-live subscription (migration 152, Jul 2026)

Per direct instruction: **no bundle discount on a module added after the
initial subscribe**, and it must be **prorated to the existing subscription's
renewal date**, then renew at full price from there — Stripe's own
proration engine does exactly this natively, so we lean on it rather than
hand-rolling day-count math.

- **Two distinct paths in `routers/billing.py`, chosen by whether
  `club.stripe_subscription_id` is already set**: no subscription yet → the
  original Checkout Session flow (`billing_pricing.price_for` — Core +
  selection, bundle discount, redirect to Stripe to collect payment details).
  Already subscribed → add items to the EXISTING subscription
  (`billing_pricing.price_for_addon` — no Core line, no discount, ever). The
  add-on path never redirects to Stripe at all — the card is already on
  file, so it charges the prorated amount immediately and synchronously,
  server-side.
- **`/quote` mirrors the same branch**: returns `{"mode": "new_subscription",
  ...price_for()}` or `{"mode": "add_to_existing", ...}` where the add-on
  shape's `total`/`line_items` come from a REAL Stripe call —
  `stripe_client.preview_add_modules` calls `Invoice.create_preview` with the
  hypothetical new items and `proration_behavior=always_invoice` — so the
  preview is Stripe's own exact proration figure, not an approximation we
  compute from day-counts. `AdminAccount.jsx` renders each mode differently
  (a "Charged today (prorated)" total + a note about full-price renewal for
  the add-on case, vs the usual bundle-discount breakdown for a fresh
  subscribe).
- **`stripe_client.add_modules_to_subscription`** creates a `SubscriptionItem`
  per new module (`proration_behavior=always_invoice`, so Stripe invoices and
  charges the prorated amount as part of that same call, against the
  existing payment method — no 3-D Secure/SCA re-authentication flow is
  handled for this path, a known limitation) and then `Subscription.modify`s
  the subscription's own `metadata.billing_keys` to the union of old + new
  keys, so future `invoice.paid` renewals (`stripe_billing.py`) keep
  refreshing the newly-added module's `renewal_date` too — without this the
  renewal loop would silently stop touching it, since it reads the
  subscription's metadata to know what's on it.
- **Real Stripe Product ids, unlike the Checkout Session path.** Checkout
  Session line items support an inline ad-hoc `price_data.product_data`
  (no product to pre-create), but `SubscriptionItem.create` and
  `Invoice.create_preview` do NOT — both require a real Product id via
  `price_data.product`. `stripe_client._ensure_product` creates each
  billable module's Product exactly once and caches the id in the new
  `stripe_products` table (migration 152) rather than re-creating — or
  Stripe-searching for — it on every add-on checkout. (Verified this whole
  parameter shape against Stripe's own current API docs while building it,
  not assumed from memory — the inline-vs-real-product-id split between
  these two endpoint families is easy to get wrong.)
- **Entitlement granted synchronously, not via webhook**, for this path —
  there's no `checkout.session.completed` event for a flow that never
  touched Stripe Checkout, so `routers/billing.py::create_checkout_session`
  itself calls `module_subscriptions.set_status_billing` right after Stripe
  confirms the item + invoice were created, using the subscription's own
  freshly-returned `current_period_end` as the renewal date. The `invoice.paid`
  webhook that follows moments later re-applies the same state — harmless,
  since every entitlement write here is idempotent.
- **`stripe_billing._upsert_invoice` now snapshots `line_items` from
  Stripe's OWN invoice lines**, not recomputed from `billing_pricing` against
  every currently-held module — a renewal invoice bills everything, but an
  add-on invoice only bills the newly-added module(s), so re-deriving "what's
  on this invoice" from the full held-module set would have shown a partial
  invoice as if it were a full one.

### Promotion codes + other payment methods (Jul 2026)

- **Promotion codes** — `create_checkout_session` sets `allow_promotion_codes:
  true` (shows a customer-facing "Add promotion code" field on Stripe's own
  checkout page) whenever the bundle discount ISN'T already applying.
  **Never set both** — Stripe rejects a session with `discounts` AND
  `allow_promotion_codes` set together (`amount_off/percent_off Coupons` and
  customer-enterable **Promotion Codes** are created/managed entirely in the
  Stripe Dashboard, Product catalogue → Coupons — no admin UI of ours
  needed).
- **Apple Pay / Google Pay already work with zero setup** — confirmed live
  (a real Apple Pay button appeared on a test checkout without any
  `payment_method_types` configuration). Neither `create_checkout_session`
  nor anything else in this codebase sets `payment_method_types` explicitly,
  so every session already uses Stripe's **dynamic payment methods**: it
  shows whatever's enabled in Dashboard → Settings → Payment methods,
  automatically, no code change ever needed to add a new one.
- **AU BECS Direct Debit and PayTo are both Stripe-supported for AU
  accounts** — same story, a Dashboard toggle away, no code change. Two
  things worth knowing before switching either on: BECS/PayTo both take
  days (BECS) or up to ~60 seconds after bank-app mandate authorization
  (PayTo) to confirm, vs a card's instant response — our webhook-driven
  entitlement grant already handles that fine (a club just sees a shorter
  "processing" window before Subscribed lands). PayTo specifically performs
  best under $1,000 AUD (BetterCricket's most expensive bundle is $998, a
  good fit) but has "relatively low" business-bank-account coverage
  (consumer accounts are its stronger suit) and bank-side mandate caps
  around $25,000 — a non-issue at these price points, just worth knowing if
  pricing ever changes materially.

### Bundle discount is now config, not code (Jul 2026)

`billing_pricing.BUNDLE_DISCOUNT` (module-count → whole-dollar discount) was
a hardcoded constant; per direct instruction it's now editable from General
Settings without a deploy, same pattern as every other super-admin-tunable
number in this app.

- **`platform_settings.get_bundle_discount_schedule(db)` /
  `update_bundle_discount_schedule(db, schedule)`** — reads/writes a
  `bundle_discount_schedule` key in the existing JSONB singleton (no
  migration). Falls back to `billing_pricing.BUNDLE_DISCOUNT` (now just the
  SEED DEFAULT) when unset. `update_...` **replaces the whole table** (not a
  merge — the UI always sends every row) and validates every key/value is a
  non-negative integer.
- **`billing_pricing.py` stays a pure, DB-free module** — `bundle_discount()`
  and `price_for()` both take an optional `schedule` override param instead
  of reaching into the DB themselves, so they're still trivially unit-
  testable with no session. Callers that have `db` (`routers/billing.py`'s
  `/quote` and `/checkout-session`, which thread it through to
  `stripe_client.create_checkout_session`) fetch the live schedule and pass
  it down; `price_for_addon` is untouched (never discounted, so there's
  nothing to override).
- **Overflow beyond the highest configured row** falls back to that row's
  discount (generalises the old hardcoded "cap at 4 modules" rule to
  whatever's actually configured — so a future 5th/6th priced module needs
  no code change here, just a new row filled in).
- **Discount is clamped to the subtotal** in `price_for()` — a super-admin
  typo in the (now-editable) schedule can't produce a negative checkout
  total.
- **UI**: `SuperClubs.jsx`'s General Settings modal, a "Bundle discount
  schedule" section under Billing — 6 number inputs (module-count → $),
  rows 5-6 pre-wired but inert today (only 4 priced bolt-on modules exist),
  saved via the existing `PATCH /club-admin/super/general-settings`
  (`GeneralSettingsUpdate.bundle_discount_schedule`, popped out and routed to
  the dedicated setter rather than the generic `_INT_KEYS`/`_BOOL_KEYS`
  `update_settings` path, since it's a nested object).

### Bundle discount coupon fixes: `once` not `forever`, cached not re-minted (migration 153, Jul 2026)

Caught during live testing: two bugs in how the bundle-discount Coupon was
created at checkout.

- **`duration` was `forever`, should have been `once`.** Per direct
  instruction: the bundle discount is a one-time incentive for subscribing to
  several modules at once — it must apply to the initial payment ONLY. A
  renewal (or an add-on to an already-live subscription, which never gets
  the bundle discount at all — see above) must bill at full price unless a
  *separate* coupon is deliberately applied to that specific renewal.
  `duration=forever` was silently discounting every future renewal too.
  Fixed: `stripe_client._ensure_bundle_coupon` now creates the coupon with
  `duration="once"`.
- **A fresh Coupon was minted on every single checkout attempt** — even two
  identical attempts (e.g. a retry) produced two separate Coupon objects in
  the Dashboard, both showing 1 redemption, reading as duplicates. Fixed the
  same way `_ensure_product` already caches Stripe Products: `stripe_coupons`
  (migration 153, `discount_cents` primary key → `stripe_coupon_id`) reuses
  ONE coupon per distinct dollar amount instead of creating a new one each
  time. Keyed on amount alone since `duration` is fixed at `once` for every
  bundle coupon today — if duration ever becomes independently configurable
  per amount, key on `(amount, duration)` instead.
- **Stripe Coupon fields, for reference** (verified against Stripe's own API
  docs while fixing this): `duration` (`once`/`repeating`/`forever`) controls
  how many charges on ONE subscription get the discount once redeemed.
  `duration_in_months` (only with `repeating`) — on an annual plan,
  `duration_in_months=12` covers only the first invoice (same practical
  effect as `once`); `24` covers the first invoice PLUS the next renewal;
  generally `12 × N` covers N annual charges. `redeem_by`/`max_redemptions`
  are a completely different axis — they cap the coupon's overall
  availability (a deadline / a total redemption count across ALL customers),
  not how long the discount lasts on any one subscription. The Dashboard's
  "Redemptions" column is `times_redeemed`; "Expires" is `redeem_by`
  (blank = redeemable indefinitely, which is what every coupon this app
  creates uses — nothing sets `redeem_by`/`max_redemptions`).
- **Not built**: applying a coupon to an ALREADY-LIVE subscription ahead of
  its next renewal (`Subscription.modify(sub_id, discounts=[{coupon: ...}])`
  — takes effect from the next invoice the subscription generates) — no
  admin action for this exists yet, in BetterCricket or otherwise; today a
  coupon can only be attached at Checkout Session creation (the initial
  subscribe, or theoretically via `allow_promotion_codes` on a future
  Checkout — but the add-on flow above never redirects to Checkout at all,
  so a promo code has no entry point there either). Configurable
  duration/repeat-count for the BUNDLE discount specifically (vs the fixed
  `once` behaviour above) is also not built — flagged as an open question,
  not assumed wanted.

### Add-on pricing was still applying the bundle discount (Jul 2026)

Caught in live testing: adding modules to an already-subscribed club's
existing subscription (`preview_add_modules`/`add_modules_to_subscription`)
still discounted the prorated charge by the original bundle-discount amount,
contradicting the "no bundle discount on an add-on" rule documented above.
Root cause: the `duration=once` bundle coupon is only consumed by a
*regular* invoice — if it hadn't yet been applied to one (e.g. modules added
the same day as the initial subscribe, before the first renewal invoice),
it was still attached to the subscription and Stripe's proration engine
applied it to the add-on invoice too.

- **`stripe_client.preview_add_modules`** now passes `discounts=""` (the
  SDK's literal-empty-string form — an empty *list* is a no-op and still
  inherits the subscription's discount, confirmed against the SDK's own
  param typing) to `Invoice.create_preview`, so the preview never includes
  an inherited discount.
- **`stripe_client.add_modules_to_subscription`** calls
  `Subscription.delete_discount_async` before creating the new
  `SubscriptionItem`s, stripping any lingering coupon so the real
  `proration_behavior=always_invoice` charge matches the preview. Errors
  (nothing to remove) are swallowed — that's already the desired end state.
- **Per-module price breakdown**: `preview_add_modules` now returns each
  line item with `full_price` (the module's plain annual rate, from
  `billing_pricing.price_for_addon`) and `deduction` (`full_price` minus the
  prorated amount) alongside the existing `amount`, matched to
  `billing_keys` by position (both derive from the same
  `PRICED_MODULES`/`FANTASY` order). `AdminAccount.jsx`'s add-on summary
  shows, per module: full annual price → prorata deduction → charged today,
  instead of a single opaque prorated figure.

### GST via Stripe Tax (Jul 2026)

Caught in live testing: checkout never charged GST, because nothing in
`create_checkout_session` ever asked Stripe to calculate tax — a Dashboard
tax configuration alone does nothing without the API request opting in.

- **GST-exclusive per direct instruction**: the advertised prices (Core
  $399/yr etc.) are what BetterCricket keeps; GST is added ON TOP at
  checkout, not carved out of the advertised figure. Every `price_data` now
  sets `tax_behavior: "exclusive"` (both the Checkout Session line items in
  `create_checkout_session` and the add-on `SubscriptionItem`/preview items
  in `_addon_price_data_items`).
- **`automatic_tax: {"enabled": True}`** is set at Checkout Session creation
  (top-level, NOT nested under `subscription_data` — that param doesn't
  exist there, verified against the SDK while building this). It carries
  onto the resulting Subscription automatically, so renewals keep
  calculating tax with no further code. `SubscriptionItem.create` has no
  `automatic_tax` field of its own — `add_modules_to_subscription`
  re-asserts it via `Subscription.modify` on every add-on call (so a
  subscription created before this shipped still picks it up), and
  `preview_add_modules` passes it explicitly to `Invoice.create_preview` too
  (so the prorated preview is accurate even before that modify call runs).
- **No explicit `tax_code` set on our Products** — deliberately left to the
  account's own **Preset product category** fallback (Dashboard → Settings →
  Tax → Business information → "Digital products › Business and web
  services", already configured) rather than guessing a specific Stripe tax
  code in code. Revisit only if a specific module ever needs different tax
  treatment from the rest.
- **Still required on the Stripe side, not something code can do**: an
  active AU GST registration under Settings → Tax → Registrations — without
  one, `automatic_tax` calculates $0 tax regardless of `tax_behavior`.
- **The Account page's OWN quote preview for a brand-new subscription can't
  show the exact GST figure** — `billing_pricing.price_for()` is pure local
  math with no Stripe call (deliberately, so `/quote` stays fast with no API
  round trip for the common case), so it shows a "Plus GST, calculated on
  Stripe's secure checkout page" note instead of a number. The **add-on**
  preview (`preview_add_modules`) is different — it's already a live
  `Invoice.create_preview` call, so once tax is enabled its `total` already
  includes the real GST automatically, no separate note needed there.

### Account page — price summary stays in view while selecting (Jul 2026)

`AdminAccount.jsx`'s module list can run to 6 rows; stacking the price
summary below it (the original layout) pushed the summary — the part an
admin most needs while still picking modules — below the fold. Fixed with a
two-column CSS Grid (`grid-cols-1 lg:grid-cols-[1fr_320px]`) once at least one
module is selected (`hasSummary`): the module list + billing history stay in
the left column, the price summary becomes the right column with
`lg:sticky lg:top-6` so it stays in view as the list scrolls. Below `lg` it
falls back to the original single-column stack (a sidebar doesn't fit a
narrow screen). No backend change.

### Per-club override for testing (migration 151)

`platform_settings.billing_checkout_enabled` is all-or-nothing across the
whole platform — no way to let one club's Primary Admin through the real
Stripe flow while everyone else stays on the stub. `organisations.
billing_checkout_override` (nullable boolean) sits on top of it: **NULL**
follows the platform default (the normal case), **true** force-enables
checkout for that one club regardless of the platform default, **false**
force-disables it even once the platform default is switched on. Resolved by
`platform_settings.billing_checkout_enabled_for_org(db, org)` — the function
`require_billing_checkout_enabled` and `GET /club-admin/account/plan` both now
call, in place of the old platform-default-only `get_billing_checkout_enabled`
(that raw getter still exists, for the General Settings page itself and as
the fallback `billing_checkout_enabled_for_org` reads). `require_billing_
checkout_enabled` now depends on `get_current_club` as well as `get_db` so it
can resolve the caller's own club's override.

Super admin control lives on the **club**, not General Settings — a "Stripe
checkout (this club)" select (Platform default / Force ON / Force OFF) in
each club's edit panel in `SuperClubs.jsx`, saved via the existing `PATCH
/club-admin/super/clubs/{id}` (`ClubUpdate.billing_checkout_override`, a
plain column so the generic `setattr` loop in `patch_club` handles it with no
special-casing). Typical use: flip one real or test club to Force ON, run a
live checkout end to end, then flip the platform default on for everyone once
satisfied (the per-club overrides can stay — they only matter when the
platform default is off, or when someone still needs a specific club blocked).

## BetterCricket-managed discount coupons (migration 156, Jul 2026)

A full coupon engine, entirely owned by BetterCricket — per direct
instruction, **Super Admin never edits a Coupon by hand in the Stripe
Dashboard for this** (unlike the earlier bundle-discount coupon, which was a
simple cached single-purpose object). Every eligibility rule lives in
BetterCricket's own tables and is decided before Stripe is ever touched; the
corresponding Stripe Coupon is a pure sync target with no `redeem_by`/
`max_redemptions` of its own, so there's exactly one place a redemption is
judged valid.

- **`discount_coupons`** (the catalogue) + **`discount_coupon_redemptions`**
  (the audit trail and the "one live redemption per club per coupon"
  enforcement — a partial unique index on non-`revoked` rows, so a Super
  Admin's revoke frees the slot back up). A coupon has: `code` (typed in) +
  `display_name`; `discount_type` (percent | amount) + `discount_value`;
  `module_keys` (null/empty = every billable module, else restricted —
  mirrored onto Stripe's native `Coupon.applies_to.products`, reusing the
  SAME per-module Stripe Product `stripe_client._ensure_product` already
  caches for the add-on-module flow, so a covered/non-covered mix on one
  invoice is split automatically by Stripe); `redeem_window_*` (when the code
  can be entered at all); `new_signup_window_*` (only usable at a club's
  very first subscribe, and only if that subscribe falls in this range) and
  `loyalty_window_*` (only usable by a club whose original subscription
  start — `MIN(org_module_subscriptions.started_at)` — falls in this
  historical range) — **both optional and independent**, each restricting
  nothing unless at least one of its own bounds is set;
  `duration_mode` (once | repeating | forever, `duration_renewals` years for
  repeating → Stripe's `duration_in_months = 12×N`); `stackable_with_bundle`;
  `max_redemptions`; `active` (the deactivate switch — coupons are never
  deleted, so history stays traceable).
- **Financial-terms lock**: once a coupon has ≥1 non-revoked redemption,
  `services/discount_coupons.update_coupon` rejects changes to
  `discount_type`/`discount_value`/`module_keys`/`duration_mode`/
  `duration_renewals` — Stripe Coupons are themselves immutable on these
  fields after creation, and rewriting them out from under an
  already-redeemed club would silently change what that club was promised.
  Only `display_name`, the window dates, `max_redemptions`,
  `stackable_with_bundle` and `active` stay editable after that point; the
  Super Admin edit modal (`SuperCoupons.jsx`) greys those fields out and
  explains why once `redemption_count > 0`.
- **Two redemption flows, one rule engine**
  (`discount_coupons.validate_redemption`, called by both):
  - **New signup** — a club with no Stripe subscription yet, entering a code
    alongside their module selection. `routers/billing.py`'s existing
    `/quote` and `/checkout-session` both grew an optional `coupon_code` —
    `/quote` validates read-only and folds the discount into the preview
    numbers (`_apply_coupon_to_quote`, pure local math, no Stripe call, same
    as the rest of `/quote`); `/checkout-session` calls
    `redeem_for_new_signup` (writes a `pending` redemption row) and passes
    the resulting Stripe coupon id through to
    `stripe_client.create_checkout_session`'s new `extra_coupon_id`/
    `extra_stackable` params — Stripe natively supports multiple
    simultaneous discounts (`discounts` is a list on Checkout Session,
    Subscription and Invoice preview alike, confirmed against the SDK's own
    param typing), so a stackable coupon combines with the bundle discount;
    a non-stackable one **replaces** it outright (never diluted by the
    generic bundle schedule). If Stripe then fails, the `pending` redemption
    is revoked so a config hiccup on our side can't permanently burn a
    club's one-time code. `stripe_billing.handle_checkout_completed` reads
    `coupon_redemption_id` back out of the session's metadata and flips the
    row to `active` once the subscription is actually confirmed created.
  - **Already-subscribed, ahead of renewal** — a Primary Admin (self-serve,
    a new "Redeem a discount code" card on the Account page, separate from
    module selection) or a Super Admin (`force=True` on the new
    "Force-apply…" action in `SuperCoupons.jsx`, which skips the
    redeem-window/max-redemption checks but never "already redeemed" or
    "inactive") call `redeem_for_existing_subscription` →
    `stripe_client.attach_discount_to_subscription`. This is a genuine
    **fetch-then-append**, not an overwrite — `Subscription.modify`'s
    `discounts` param replaces the whole list, so blindly setting a new
    single-entry list would silently evict a different coupon redeemed
    earlier for the same upcoming renewal. Stripe applies a
    subscription-level discount starting at the **next** invoice the
    subscription generates, never retroactively — exactly "apply ahead of
    the renewal date", no proration or immediate charge triggered.
- **Not built**: a self-serve "browse eligible codes" list (deliberately —
  confirmed a typed-in code is the right UX, matching how a coupon code
  normally works); configurable per-coupon retry/grace period for a stuck
  `pending` new-signup redemption beyond the immediate Stripe-failure revoke
  above (a truly abandoned Checkout Session — the club navigates away
  without completing — leaves the redemption `pending` forever, which the
  "already redeemed" check treats as used; a Super Admin can manually revoke
  it via the Redemptions modal as the recovery path today).

## Public self-serve trial signup + ad attribution (v8.72.0, Jul 2026)

The Meta ad campaign's destination: the internal self-serve trial registration
(`routers/self_serve_trial.py`, previously Super-Admin-only) went public.
**`routers/public_self_serve.py`** (`/public/self-serve/*`, unauthenticated)
re-registers the SAME step handlers (they're plain coroutines; the auth gates
live on the internal router's constructor) via `add_api_route` for identical
steps, and hand-wraps only `status` / `verify-email/send` / `prepare` /
`verify-email/check` / `submit` where public behaviour differs. Still behind
the `self_serve_registration_enabled` platform flag (the whole router 404s
while it's off — merge-safe ahead of campaign launch). The internal
`/self-serve-trial/*` router is untouched.

- **Light guardrails (per direct instruction — auto-approve, no review
  queue)**: per-IP `rate_limit.enforce` caps on search/prepare/send/check/
  submit layered over the shared per-email limits (the email-only lockout was
  otherwise a public DoS vector on a victim's email); a honeypot `website`
  field on prepare+submit (non-empty → plausible fake success, nothing
  created); a minimum-fill-time check (`form_started_at`, <4s ⇒ generic 422,
  negative deltas ignored so clock skew can't false-reject). CAPTCHA
  deliberately NOT added (needs an account to provision; fast-follow if abuse
  appears). The OTP email step is the real gate.
- **Error tightening**: the public `verify-email/send` wrapper swallows the
  raw provider error (the internal route's "TIGHTEN BEFORE PUBLIC LAUNCH"
  note) → generic message; real error still logged. Known accepted public
  surfaces (documented in the router docstring): `verify-email/status` is an
  is-this-email-mid-verification oracle (low value); submit's 500 carries the
  org/user support reference on purpose.
- **Auto-login**: public submit mints the session cookie itself
  (`create_session_token`/`set_session_cookie` — the primitive the internal
  `login-as` endpoint documented as "what a future public flow will call") and
  returns `redirect: "/admin"`; replays re-login the same registrant. Sets
  `bs_pending_fresh_login` client-side so the setup wizard auto-open fires.
- **Attribution (migration 161)**: `organisations.signup_source`
  (`self_serve_ad` when the browser's first-touch had a campaign/click signal,
  else `self_serve_organic`; NULL for every non-public onboarding) +
  `organisations.signup_attribution` JSONB (the `visitor.js getAttribution()`
  payload, key-allowlisted + clipped server-side). Written best-effort AFTER
  the shared submit commits — an attribution hiccup never fails a
  registration. Signup timestamps come from `self_serve_idempotency_keys`
  (orgs have no created_at).
- **Meta Pixel / CAPI**: `meta_capi.py` refactored — generic `_send_event`,
  `send_lead_event` re-expressed on it, new `send_complete_registration_event`
  ($399/AUD, `self_serve_trial` category). Public `prepare` fires a
  server-side Lead (browser fires the matching pixel Lead with the shared
  eventId — a picked club is a lead even if they stall); public `submit`
  fires CompleteRegistration browser+server (the campaign's optimisation
  event) + GA4 `sign_up` + a `conversion` usage-event breadcrumb.
- **Frontend**: `/trial` (`pages/marketing/Trial.jsx`, in the OG map; its
  sitemap entry in `seo.py` stays COMMENTED OUT until full launch). HIDDEN
  while the flag is off (redirects to `/` — briefly flipped to
  public-with-contact-fallback on Jul 17, reverted the same day per direct
  request); flipping the flag on makes the page AND signup live with no
  deploy. Meta's ad-review crawler (Prineville/Luleå/Clonee data-centre
  IPs, carrying the ad UTMs) hits this URL when ads are created — reads as
  "visits" on the Usage page, not real users —
  hero-first single-CTA landing page opening `SelfServeTrialModal` with the
  new **`publicMode` prop** (NOT `public` — reserved word when destructured):
  switches the api.js family to `publicSelfServe*`, sends honeypot/
  fill-time/attribution/visitorId/meta on the wire, skips the admin-only
  sync-log polling + login-as button, success screen → redirect to `/admin`
  after ~1.2s (lets pixel beacons out). ViewContent fires ref-guarded (once
  per visit, StrictMode-proof).
- **Ad → lead-score report**: `GET /club-admin/meta-ads/ad-signups`
  (routers/meta_ads.py) — every org with `signup_source`, its attribution,
  trial/paid modules (via `twenty_sync._module_split`), and the CACHED
  `marketing_clubs.engagement_score` via LEFT JOIN on `existing_org_id`
  (never a live `_engagement()` per row; an org registered while Twenty was
  unconfigured has NO MarketingClub row → "not yet scored" in the UI). Panel
  on `SuperMetaAds.jsx` with per-campaign rollup + cost-per-signup.
- **Launch preconditions (config, not code)**: flip
  `self_serve_registration_enabled` ON; set a real `email_provider` (defaults
  to `console` — OTP never sends!) + the SPF/DKIM/DMARC DNS still pending per
  the Public Domain note; Twenty configured so `push_self_serve_registration`
  lands the Hot-100 Lead. Rate limiter is in-memory single-process (fine for
  the single-uvicorn deploy).
- **Local-dev quirk** (not prod): `Base.metadata.create_all` doesn't add the
  `gen_random_uuid()` server defaults some raw-SQL migrations set (e.g.
  `org_module_subscriptions.id`), so a fresh ORM-created DB needs those
  defaults added by hand before the lifespan module backfill runs.

## Usage tracking — session duration, time on page, visitor journeys (migration 165, v8.75.0, Jul 2026)

`usage_events` had club, page, and UTM/campaign granularity but nothing on how
long a visitor actually stayed anywhere, and no built-in ordered-journey view
(see the earlier "Data Source Topology"-style investigation this session did
into what the table could and couldn't answer). Both gaps are closed without
a new table:

- **`usage_events.time_on_page_ms`** (migration 165) is filled by a new
  `page_exit` event, not by the existing `page_view` row. `usePageView.js`
  fires it via `navigator.sendBeacon` on `pagehide` and on `visibilitychange`
  going hidden (covers both real navigation/tab-close and a mobile browser
  backgrounding the tab without ever firing `pagehide`), and again on every
  route change to close out the page just left. `POST /usage/event/exit`
  (`routers/usage.py`) writes it; clamped server-side to 24h so a stuck timer
  (laptop asleep, tab backgrounded for hours) can't skew an average.
- **Session duration is computed on read, not stored.** A "session" is a
  visitor's `page_view` timestamps grouped on a ≥30-minute gap (the
  industry-standard boundary); duration is the span between first and last
  page_view PLUS the final page's own `time_on_page_ms` (matched by visitor +
  path + nearest-following `page_exit`) — without that tail, a single-page
  bounce session always reads 0ms even if the visitor read the page for a
  minute before leaving. `GET /club-admin/usage/session-duration` returns
  avg/median session length, a length distribution, and top pages by average
  dwell time; surfaced as a new "Engagement" panel on the Usage page.
- **`GET /club-admin/usage/journey?visitor_id=`** reconstructs one visitor's
  actual ordered page-path, split into sessions, each step carrying its
  matched dwell time and whatever UTM/campaign tag was on it — every other
  Usage endpoint aggregates across visitors, this is the only one that
  replays a single visitor's route through the site. Surfaced automatically
  on the Usage page: typing (or deep-linking with) a visitor UUID into the
  existing search box now shows a "Visitor journey" panel above the regular
  aggregate views.
- **Campaign-capture fix, found while building this**: a club outreach
  link's UTM tags are applied by `comms.py::_apply_utm`, keyed on `utm_id`
  (the recipient club's `marketing_clubs.utm_code`) plus the sending
  campaign's own `utm_source`/`medium`/`campaign`/`content`. The old skip
  logic gated the WHOLE campaign-params block behind "does the link already
  have `utm_source=`" — so a template that hand-placed
  `{{utm_source}}={{utm_code}}` (a documented per-club merge-var pattern)
  silently dropped `utm_campaign` too, even though only `utm_source` was
  actually already present. Now each UTM key is checked and added
  independently. Separately, `usePageView.js` used to send only the
  visitor's STICKY first-touch `utm_campaign` (`getAttribution()`) — a
  returning visitor clicking a brand-new campaigned link would have that
  click's `utm_id` recorded fresh but its `utm_campaign` reported as
  whatever their first-ever visit happened to carry. `visitor.js` gained
  `getCurrentUtm()` (a non-sticky parse of the CURRENT URL's own UTM params),
  which now wins over the first-touch snapshot whenever present.

## Uploaded scorecard missing from the public Games page (migration 169, v8.76.1, Jul 2026)

Reported: a scorecard uploaded via `/admin/upload-scorecard` for Legana
Cricket Club never showed up on `/legana-cricket-club/games`.

**Root cause**: the upload form (`AdminScorecardUpload.jsx`) lets Grade be
left as "— none —" (Season is required, Grade isn't). `GET
/organisations/{id}/results` (`organisations.py::get_org_results`, what
`GamesPage.jsx` calls, and it always applies a season filter — it
auto-selects the most recent season on load) derived season purely by
joining `grades gr ON gr.id = g.grade_id` then `seasons s ON s.id =
gr.season_id`. With `grade_id` NULL, both `gr` and `s` came back NULL, so the
season filter (`s.id = :season_id ...`) could never match — even though
`manual_games.season_id` itself is a required, always-set column. The row
was silently excluded under every season, on every page load.

**Also found while fixing it**: the same query's org-ownership check had a
bare `g.source = 'manual'` clause with no organisation check at all, so
literally any club's manual game read as "ours" on every other club's
results/W-L-D headline — a cross-club data leak. `games.py::list_games`'s
`api_games` sub-query had the identical clause even though manual games are
already fetched separately and correctly (org-scoped) by
`_fetch_manual_games_as_list` in the same function, so that endpoint doubly
leaked (any org's manual games) and duplicated (this org's own manual games,
once via each path). `manual_entries.py`'s upload-time duplicate-check
(`check_scorecard_duplicate`) had the same grade-required join, so it also
couldn't detect an existing grade-less manual game on re-upload.

**Fix**: `v_effective_games` now carries `season_id`/`organisation_id`
columns directly (migration 169 — for `games`, derived via
grade→season same as before; for `manual_games`, its own always-set
columns), appended at the end so no existing consumer (none `SELECT *`
against this view) is affected. `get_org_results`, `_club_results`
(aggregations.py, the headline W/L/D — explicitly mirrors `get_org_results`
so the two agree) and `check_scorecard_duplicate` now join season off the
view's own `season_id` and check `g.organisation_id = :org_id` instead of
the blanket `g.source = 'manual'`. `list_games`'s `api_games` sub-query now
scopes to `g.source = 'api'` only, since manual games are handled entirely
by the separate, already-correct fetch. Verified end-to-end against a real
local Postgres instance (base schema + the view + sample cross-org data)
before shipping — confirmed the bug reproduced against the old query and no
longer does against the new one, including a regression check that an
ordinary graded API-synced game is unaffected.

**Anti-pattern reminder**: a manual game can legitimately have no
`grade_id` (Grade is optional on upload) but always has a `season_id` and
`organisation_id` — don't derive either one by joining through `grade_id`
for a `v_effective_games` row; read the view's own `season_id`/
`organisation_id` columns instead.

## Uploaded scorecards log — edit/undo from the upload page (v8.76.2, Jul 2026)

`/admin/upload-scorecard` (`AdminScorecardUpload.jsx`) was a one-shot flow —
upload, review, import, done — with no way to see or revisit what had already
been uploaded from that page short of finding it in the general-purpose
"Manual Games" tab on `/admin/manual-entries`. It now has its own list,
scoped to just the scorecards that came through the photo-upload flow.

- **`GET /club-admin/manual-entries/games`** (`list_manual_games`) gained
  `is_photo_upload` (whether `manual_games.extracted_payload` is set — the
  AI reader's saved match+innings JSON, present only for a photo upload, not
  a hand-typed manual game) and `created_by_name` (a `LEFT JOIN users`,
  mirroring the pattern `list_audit` already used). The list keeps the full
  `extracted_payload` blob out of the response (popped after computing the
  boolean) — it's only needed in full when a single game is reopened via
  `GET /games/{id}` (already returned it; unchanged).
- **Jump back in ("Edit")**: since `extracted_payload` is the exact
  `{match, innings}` shape the review screen already edits in memory,
  reopening a past upload replays it through the SAME review UI used at
  upload time — no separate "already-imported" editor to keep in sync. The
  WK-catch split (`wkByPid`, not itself persisted) is reconstructed from the
  saved `fielding_stats.catches_wk` per player. Saving calls `PATCH
  /games/{id}` instead of `POST /games`; a fresh photo read always clears
  `editingId` first so it can't accidentally overwrite a prior edit target.
- **Duplicate check gained `exclude_id`** (`check_scorecard_duplicate`) — 
  editing an already-saved game used to flag the game against itself as a
  "possible duplicate" on the same date, since the query had no way to
  exclude the row being edited.
- **Delete** reuses the existing `DELETE /games/{id}`; the list's own footer
  points at `/admin/manual-entries#audit` for restoring a deleted or edited
  entry rather than re-implementing undo/restore on this page too — one
  audit trail, not two.
- Verified end-to-end against a real local Postgres instance: the
  `is_photo_upload`/`created_by_name` join, and the `exclude_id` fix to the
  duplicate check, both before shipping.

## Scorecard reader — multi-format, PDFs, fielding column, eval set (v8.80.0, Jul 2026)

`scorecard_ocr.py` (the Upload Historical Scorecard reader) taught about more than
the WACA-style scorebook, prompted by a Toowoomba club's archive (1976 scorebook
pages + a 1993 TCA "Official Summary of Match" form). Full how-to-improve-it doc:
**`docs/scorecard-reader-eval.md`**.

- **Prompt knows three format families**: the two-page scorebook, the association
  match-summary form (one club's side only + opposition as a bare "10/111" totals
  line → an innings with totals and an EMPTY batting list), and "anything else,
  note the layout in read_notes". Also warned about: tally strokes in extras
  boxes (the numeral total column wins), wickets-first "7/164" notation,
  two-digit years → 1900s, two-day matches (first day = match.date), and
  **pre-1980 Australian 8-ball overs** → new `match.balls_per_over` (reconcile's
  overs check + `overs_to_balls(o, balls_per_over)` honour it; DB storage is
  unchanged — overs stay as written on the card).
- **Result inference is the ONE allowed deviation from transcribe-only**: blank
  result box + completed innings that decide it → model may fill `result` and
  set `result_inferred`, which the review screen flags ("worked out from the
  scores, check it"). Everything else stays faithful-transcription-only.
- **New `innings[].fielding` section** ({name, catches, catches_wk, stumpings,
  run_outs}) for cards that credit fielders separately from dismissals (OWN
  CATCHES column, W/K = keeper). Attached to the innings where that side was
  FIELDING. The extract endpoint adds these names to the roster-suggestion set;
  the review screen shows them as an editable, player-matchable table, and
  import merges them with the dismissal-derived fielding by **max per stat** so
  the same catch seen both ways counts once. Re-editing a saved upload seeds
  this table from the saved `fielding_stats` so a re-save can't drop
  column-sourced fielding.
- **PDF uploads work end to end**: `guess_media_type` recognises `.pdf`,
  `extract_scorecard` sends PDFs as native `document` blocks (no rasterising;
  anthropic 0.40.0 passes the dict through), the file input accepts them and
  previews show a file chip. Mind the API's ~32MB request cap for huge scans.
- **Eval harness** `python -m app.scripts.scorecard_eval <cases_dir>`: local
  (never committed) case folders of scans + a verified `expected.json`; only
  keys present in the truth file are scored, rows matched by normalised name.
  Run before/after any prompt/schema/model change to the reader — that's the
  training loop, since the model itself never learns from uploads.
- **Tracked-fields toggles (v8.80.1, migration 184)**: a "This card tracks"
  panel on the review screen (balls faced / 4s & 6s / maidens / bowler
  wides+no-balls). Unticked → the column is hidden AND imports as **NULL, not
  0** — `manual_batting_innings.fours/sixes` and
  `manual_bowling_spells.maidens/wides/no_balls` went nullable (the synced
  tables always were, so every effective-view reader already copes). The
  pydantic defaults stay `Optional[int] = 0`, so the CSV import and hand-typed
  manual-game form (which omit rather than null the fields) are byte-for-byte
  unchanged; only an EXPLICIT null means "not recorded". Toggle defaults come
  from whether the reader found any value; re-editing a saved upload recovers
  the choice from the stored rows' nulls. The prompt also tells the model to
  leave untracked stats null, never 0.
- **Card-error vs misread flags (v8.80.3)**: `reconcile()` now returns
  `list[dict]` `{kind, text}` instead of `list[str]` — `kind` is `card_error`
  (the card's OWN figures don't reconcile: batting≠total, wickets≠FOW count,
  bowling≠total, overs mismatch — a decades-old scorer slip, fix-or-keep) or
  `misread` (a value the READER likely got wrong: dismissal bowler not in the
  analysis, boundaries>runs, keeper catches>catches — worth fixing). The reader
  still transcribes faithfully; nothing auto-corrects. Frontend
  (`AdminScorecardUpload.jsx`) renders two boxes: amber "the original scorecard
  doesn't add up here (correct below or import as-is to keep the card's
  figures)" and red "likely misreads — worth fixing above", and the import
  confirm spells out the keep-or-fix choice (button reads "Import, keep
  original" when only card errors remain). The eval prints `w["text"]`. Old
  plain-string warnings tolerated on the frontend via `asWarn`. Per direct
  request: read exactly what the card says, flag where it's wrong, let the user
  choose.
- **Name cross-referencing across the card (v8.80.2)**: the standout
  handwriting win, from a real correction pass — the same person is written
  many times (batting order, bowling analysis, a "c Smith" catcher, a "b Jones"
  wicket-taker, fall-of-wickets) with wildly varying legibility. The prompt now
  says to read EVERY occurrence and use the clearest as the true spelling, then
  use it everywhere: the **bowling analysis is authority for bowler names** (a
  dismissing bowler is always one of the analysed bowlers), the **batting order
  authority for batter names** — but never collapse two players who merely share
  a surname (N Ziebell ≠ R Ziebell). `reconcile()` backs it with an advisory:
  `_name_close` (surname-level `SequenceMatcher`, ≥0.6) flags a dismissal bowler
  whose name isn't among that innings' analysed bowlers — the exact
  "S Willingslow" that's really "G Wittingslow" case. Worked examples baked into
  the prompt (Wittingslow, Houser/Heuser, Pascoe initials). Verified truth file
  for the 1976 Railways match kept locally as the first eval golden case.
- **Roster matching = the historical-import engine (v8.80.1)**: the extract
  endpoint now runs card names through `import_ingest.match_players` (the same
  exact → middle-initial-tolerant → "Surname Initial" form → blocked
  SequenceMatcher pipeline BetterImport and the Merge Players fuzzy pairs
  use) instead of the old bespoke `_suggest_player` token matcher.
  Auto-fill policy: exact hits, plus a single candidate at confidence ≥0.9
  (the unique "G Evans" surname+initial case — parity with the old matcher);
  everything else ships as `result["match_info"]` candidates, which
  `PlayerSelect` shows as a one-click "CLOSE MATCHES" group with confidence %
  at the top of every picker (batters, bowlers, dismissal fielders, own-catches
  rows). `_suggest_player` still exists for `_replace_game_children`'s
  import-time FOW/partnership name resolution — unchanged on purpose.

## Notification Centre (v7.7.3, May 2026)

Bell icon in the AdminLayout header + drop-down panel that auto-opens on login when there's something new.

**Architecture** — no dedicated notifications table:
- `User` model gains `last_notification_seen_at TIMESTAMP` and `last_seen_app_version TEXT` (migration `029`).
- Three endpoints under `/club-admin/notifications/`:
  - `GET /count` — cheap badge poll (runs every 60s). Counts sync runs + milestones + pending sync requests since last seen. Returns `{ unseen_count, last_seen_version }`.
  - `GET /summary` — full data fetched only when the modal opens. Returns sync runs, new milestones, upcoming milestones (top 5), pending count.
  - `POST /seen` — sets `last_notification_seen_at = now()` and `last_seen_app_version = <passed version>`.
- "Since last visit" window defaults to 14 days if user has never dismissed notifications.

**Feature Changelog** (`frontend/src/data/changelog/`):
- One file per release, Vite glob-imported and sorted by `sortKey` desc in `index.js`. Each file default-exports `{ version, date, sortKey, title, items[] }`.
- `SITE_VERSION` (in `frontend/src/version.js`) is derived from `CHANGELOG[0].version` — never hand-edited. `Navbar.jsx` still re-exports it for backwards compat.
- The bell computes `newChangelogCount` (entries with version > `last_seen_version`) client-side and adds it to the backend `unseen_count` for the badge.
- Auto-open on login fires if `unseen_count > 0 || any changelog entry is newer than last_seen_version`.

**Adding a new changelog entry**: drop a single file in `frontend/src/data/changelog/`, e.g. `v1-0-5-beta.js`:
```js
export default {
  version: 'v1.0.5 Beta',
  date: '2026-05-29',
  sortKey: '2026-05-29T12:00:00Z', // any ISO string > current top entry; `new Date().toISOString()` works
  title: '...',
  items: ['...'],
}
```
Branches never touch a shared file, so parallel work merges cleanly. `index.js` re-sorts on every build — whichever PR ships latest naturally becomes `CHANGELOG[0]`.

**Open follow-ups worth investigating**:
- `deep_sync_player` (admin-triggered per-player resync via PHQ Partner API) still has a UI surface but is low value now that Grassroots covers all seasons including 25/26. Could be retired or repointed at GR. Low priority — no data pollution.
- Season-alias URL redirects: visiting `/yearbook/{alias_season_id}` still loads the alias's hidden yearbook record + alias-only stats. The stats queries auto-expand when visiting the canonical URL, but no redirect from alias URL → canonical URL exists yet. Old bookmarks to merged-away seasons are the corner case.
