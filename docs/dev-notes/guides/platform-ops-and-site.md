# Guide: Platform ops, deploy and the public site

**Read this before**:
- Touching `deploy.sh`, `deployafl.sh`, `/srv/docker`, `docker compose` on the bltbox host, `frontend/nginx.conf` `/api` proxying, or nginx-proxy-manager (NPM).
- A production symptom: 502s, blank club pages, "Failed to fetch dynamically imported module", site up with no data.
- Domain, brand or contact-address changes (`betterat.cricket`, `support@bettersports.com.au`, `cloudflare-worker/`, `og_preview.py`, `seo.py`, `marketing.js`).
- Blog posts, the Contact form (`public_contact.py`), public pricing (`pricing.js`).
- Module entitlement (`module_overrides`, `MODULE_TOGGLES`), tiers, changelog files or `version.js`.
- Writing any user-facing prose.

**Archive** (verbatim history, do not load whole): `docs/dev-notes/archive/platform-ops-and-site.md`. Grep hints: `Writing Voice`, `Server Deploy Command`, `compose project split`, `NPM can't resolve`, `Public Domain`, `social-share cards`, `onboarding requests`, `Club name is a search`, `Public Marketing Pricing`, `tiers retired`, `Version Numbers`, `Active development branch`, `Architecture`, `Key Notes`.

**Related guides**: Stripe billing and self-serve signup guides (pricing and `/trial` cross over); the AFL guide for `deployafl.sh` and `ops/afl`.

## Standing rules

**Deploy and the compose project**
1. The box runs about 26 containers as ONE systemd compose project, `bltbox_docker_app` (`docker-compose-app.service`, `WorkingDirectory=/srv/docker`). BetterStats lives in the central `/srv/docker/docker-compose.yaml`, not the retired `/srv/docker/betterstats/docker-compose.yml`.
2. Deploy by running `/srv/docker/betterstats/deploy.sh`. Long form: `cd /srv/docker`; `export COMPOSE_PROJECT_NAME=bltbox_docker_app`; `git -C /srv/docker/betterstats pull origin main`; `docker compose build --no-cache betterstats-frontend betterstats-backend`; then recreate only those two with `--no-deps`.
3. `COMPOSE_PROJECT_NAME=bltbox_docker_app` is mandatory. Without it compose defaults to project `docker` (the directory name), starts a second betterstats stack on an empty pgdata volume and steals the `betterstats-*` container names. That was the June 2026 outage.
4. Run from `/srv/docker` so `.env` and the override file load, as systemd does. Never pass `-f` (it skips the override and drifts the config hash).
5. Name only the two services and use `--no-deps`. Never recreate `betterstats-db`: the data lives in volume `bltbox_docker_app_betterstats_pgdata`. Use `--no-cache` on the build.
6. Operate containers only through `docker compose ...` (from `/srv/docker`, project name set). Never bare `docker run/restart/exec/ps`: they fall outside the project and leave duplicate stacks. For another app (for example NPM) find its service with `docker compose ps --services`; do not hardcode container names.
7. Never add `--remove-orphans`: it would delete `klubpro-mongo` and `restreamer`, which are other people's apps. Ignore `POSTGRES_PASSWORD` and `LANGFLOW_*` "not set" warnings (other services' vars).
8. The frontend `nginx.conf` must proxy `/api` to `betterstats-backend`, never the bare `backend`. On `docker-shared-net` the bare name resolves to a different app's API.
9. NPM routes `betterstats.cricket` to `betterstats-frontend` on `docker-shared-net`. Recreating the frontend gives it a new IP and NPM resolves per worker, so a deploy can 502 until NPM re-resolves.

**Domain, brand, contact**
10. The canonical public domain is `https://betterat.cricket` (no `www`). Keep every new public URL reference there: `usePageMeta.js` (`BASE_URL`), `frontend/index.html`, `frontend/public/{llms.txt,robots.txt,sitemap.xml,site.webmanifest}`, `routers/seo.py` and `og_preview.py` (`SITE`), `settings.public_base_url`, the `deploy.sh` health check, `tools/sync_watch.py`.
11. The brand is one word, "BetterCricket", in all copy, titles, OG cards, metadata and the `BRAND` constant in `marketing.js`. Module names stay camelCase (BetterStats is Core). The trading company is BetterSports.
12. One contact address everywhere: `support@bettersports.com.au`. It is the default reply-to (`settings.email_reply_to`) and the public contact address (`SUPPORT_EMAIL` in `marketing.js`, plus hardcoded copies in `index.html`, `llms.txt`, `og_preview.py`, `self_serve_trial.py` and the marketing pages). `email_from_address` is a separate sending address. Change all copies together.
13. `email_provider` defaults to `console`: nothing sends until a provider is set. `bettersports.com.au` still needs SPF, DKIM and DMARC.
14. Marketing social cards are server-rendered by `og_preview.py` (`MARKETING_PAGES`), since crawlers do not run JS. Keep that map in step with the routes.

**Blog, Contact form, pricing**
15. Adding a blog post is three steps that must agree: hero image in `frontend/public/marketing/blog/` (1920x1080), full post in `frontend/src/data/blog.js`, and a matching row in `backend/app/content/blog.py` (`BLOG_POSTS`) copied from `blog.js`. `og_preview._blog_html` and the `seo.py` sitemap (`BLOG_SLUGS`) both read `blog.py`. After deploy, re-scrape shared links in Facebook Sharing Debugger and LinkedIn Post Inspector.
16. Contact form: Formspree stays the primary delivery and drives the success and error UI. The `POST /api/public/contact` store is best-effort and must never block the form. `routers/public_contact.py` is unauthenticated and not module-gated; it clips every field. Table `club_onboarding_requests` (migration 079) has no `organisation_id` (the sender is a prospect). Staff UI: `/admin/super/onboarding`, backed by `GET` and `PATCH /club-admin/super/onboarding-requests`.
17. Club-name search on the Contact form: `GET /public/contact/club-search` reuses `self_serve_trial.search_clubs` but is deliberately NOT under `/public/self-serve`, which sits behind the `self_serve_registration_enabled` flag. The Contact form must work whether or not self-serve is on. It is rate-limited per IP (120 per hour) because every keystroke reaches CA's API. The response is projected down: never return a registered club's slug or Primary Admin name on a marketing page. `already_registered` never blocks.
18. `club_onboarding_requests.club_org_id` and `.club_source` ('search' | 'manual'): a guid is stored only with `club_source='search'`. A typed name has nothing to key on, and a guessed identity must not be put on the record. An unrecognised `clubSource` drops both.
19. `_resolve_onboarding_club` takes `org_id` and checks it after the submitter's email but before the name (email-first priority kept). A new club row is created on the real CA guid, so an enquiry row and a crawler row are one row. A `manual:` guid is upgraded to the real one only when no other row holds it (`grassroots_guid` is unique; two rows for one club is a person's merge decision).
20. Keep the typed club name available (CA list is Australia only). In `ClubSearchField.jsx`, `club` is only set once `clubSource` is, so "Club name is required" blocks a half-typed search.
21. Public pricing lives in `frontend/src/data/pricing.js` (`CORE`, `PRICED_MODULES`, `BUNDLE_DISCOUNT`, `priceFor`, `ALL_IN`, `COMPETITOR_STACK`). It is kept separate from the entitlement registry (`frontend/src/lib/modules.js`) so copy and gating move independently. Public licence is annual only. The bundle discount is a set dollar amount keyed on module count.

**Entitlement, versions, voice**
22. The Good/Better/Best tiers are retired and not returning. A club's `module_overrides` is the single source of truth for entitlement, gated by `subscription_status` (`auth/modules.py::org_entitled_modules`). Core (BetterStats) is always on and never a gateable module. Do not read `organisations.tier` (kept for history only). Do not reintroduce `TIER_INFO`, `TIER_ORDER`, `requiredTier`, `tier_modules` or `MODULE_REQUIRED_TIER`. Locked modules read as "add-ons". BetterFees membership tiers are a different feature: leave them.
23. Super admins assign modules with per-module checkboxes (`MODULE_TOGGLES`, in `SuperClubs.jsx`); no tier dropdown. `/auth/me` returns no `entitlements.tier`; frontend gating reads `entitlements.modules` (`AuthContext.hasModule`).
24. Releases: one file per release in `frontend/src/data/changelog/`, exporting `{ version, date, sortKey, title, items }`. Never hand-edit `frontend/src/version.js`: `SITE_VERSION` derives from the highest `sortKey`. `sortKey` is a lexically sorted ISO string. Bump `+0.0.0.1` for a small fix, `+0.0.1` medium, `+0.1` large.
25. User-facing prose (copy, changelog, UI strings, docs, PR bodies) must follow the humanizer rules (`.claude/skills/humanizer/`): no em or en dashes, no forced triads, no promotional AI vocabulary (vibrant, seamless, testament, elevate), no tailing negations ("no guessing", "no fuss"), plain `is`/`are`/`has` over "serves as"/"boasts". Plain Australian cricket-club voice. Page `<title>` separators keep the site-wide `—`: that is structural and the one exception.

**Data-source and query basics**
26. Grassroots proxy (`grassrootsapiproxy.cricket.com.au`): season aggregates are open, game-level paths need a restricted upstream key. `jsconfig=eccn:true` is a formatting flag, not a key.
27. PostgreSQL `ORDER BY year DESC` sorts NULLs first: always add `.nullslast()`.
28. `Season.year` is NULL when Grassroots omits `startDate`: fall back to parsing the name (`"Summer 2010/11"` gives 2010).
29. CA field names: `bowlingEconomyRate`, `fieldingTotalCatches`; no `bowlingOvers` (derive from `bowlingBalls`).
30. PlayHQ's public game summary API gives no cricket scorecards without a partner JWT.
31. `stats["player_seasons"]` in sync counts player-season records, not unique players.

## Traps and failure signatures

- **Site up, months-old marketing page, every club page blank (`/applecross` empty), looks like total data loss.** Cause: a deploy or restart without `COMPOSE_PROJECT_NAME` forked a second betterstats project. The real 370 MB DB sat in volume `docker_betterstats_pgdata`; the systemd stack came up on the empty `bltbox_docker_app_betterstats_pgdata` and stole the hardcoded `betterstats-*` names. Nothing was lost. Fix: clone the real volume into the live one: `docker run --rm -v docker_betterstats_pgdata:/from:ro -v bltbox_docker_app_betterstats_pgdata:/to postgres:15 bash -c 'find /to -mindepth 1 -delete; cp -a /from/. /to/; rm -f /to/postmaster.pid'`.
- **Every cricket data call returns another app's 404s.** Cause: the deployed `nginx.conf` proxied `/api` to bare `backend` (ProLog's API on `docker-shared-net`). If club pages still 404 after that, the frontend/backend pair is stale (pre `/clubs/{slug}`): deploy a matched pair.
- **Diagnose the compose split in this order:** (1) `docker compose ls -a`: are there TWO projects with betterstats (`docker` vs `bltbox_docker_app`)? (2) `docker volume ls | grep pgdata`, then `docker run --rm -v <vol>:/v postgres:15 du -sh /v`: which pgdata volume holds the data (the big one)? (3) `curl -s https://betterstats.cricket/api/openapi.json | head`: is `/api` answered by the title "BetterStats API" or another app? (4) `docker exec betterstats-frontend grep -rn proxy_pass /etc/nginx/`: does `/api` point at `betterstats-backend`?
- **`/admin` dies with "Failed to fetch dynamically imported module: .../assets/AdminDashboard-H0O_EwuY.js", intermittent 502 on that chunk.** Not a stale or corrupt asset and not a cache. After the frontend was recreated it got a new Docker IP, and NPM could not resolve `betterstats-frontend`: NPM error log `betterstats-frontend could not be resolved (2: Server failure)` (DNS SERVFAIL). NPM resolves per worker, so some workers had a good result (200) and some a cached SERVFAIL (502). That per-worker split made it look like one bad URL.
- **Misleading signals (do not repeat the chase):** `?v=2` gave 200 while the bare URL gave 502 (per-worker DNS luck, not a URL cache); the file in the container was byte-perfect and served 200 via `docker compose exec betterstats-frontend wget -qO- localhost/assets/<chunk>`; no NPM cache object existed, so purging did nothing.
- **The tell is in the NPM error logs, not the app logs:** `docker compose exec <npm-service> sh -c 'grep -RhiE "could not be resolved|betterstats-frontend" /data/logs/*error*.log | tail'`. Per-host access logs are `/data/logs/proxy-host-*_access.log` (`[Sent-to betterstats-frontend]`).
- **Fix that worked:** `docker compose restart "$(docker compose ps --services | grep -iE 'proxy|npm|manager' | head -1)"`. A graceful `nginx -s reload` did NOT clear it (`deploy.sh` tries reload, then restarts if unhealthy).
- **If the NPM outage recurs:** (1) NPM error log for `could not be resolved`; (2) confirm the containers share a network: `docker compose exec <npm> getent hosts betterstats-frontend`; (3) if the name resolves from NPM but the site still 502s, it is stale per-worker resolver state: restart the proxy service via `docker compose restart`.
- **Prevention that shipped:** `deploy.sh` refreshes NPM after recreating the frontend, health-checks `https://betterat.cricket/` three times and restarts the proxy only if non-200. The frontend reloads once on a chunk-load failure (`vite:preloadError` in `main.jsx`, chunk-aware `ErrorBoundary`).
- **A shared link shows a generic card.** SPA `usePageMeta` tags never reach crawlers; a blog post missing from `blog.py` falls to the homepage card. Re-scrape after deploy.
- **Contact store and `/api`.** It assumes `betterat.cricket` routes `/api` to `betterstats-backend`. If the marketing domain is ever served without that proxy, point the form at the absolute backend URL. Meanwhile Formspree still emails.

## How to verify a change here

- Deploys: read the `deploy.sh` output. Step 5 requires `https://betterat.cricket/api/openapi.json` to contain "BetterStats" (about 15 tries at 5 s): it catches a backend that fails to boot (alembic error, crash loop) and a crossed `/api` proxy. Step 4 only proves the frontend, which serves static files even when the API is dead.
- Slow boots: look for `Application startup complete.` in `docker compose logs --tail=10 betterstats-backend`.
- Blog or OG changes: `curl` the `/blog/{slug}` URL (raw HTML is what crawlers see).
- Contact form and club-search: the archive cites a real-Postgres run (resolution priority, guid upgrade and collision guard, migration 224 twice on a populated table, junk `clubSource`) and a browser drive, but names no suite file. Look in `backend/verification/` first.

## Operator commands and scripts

- `/srv/docker/betterstats/deploy.sh`: the deploy. Nothing here is dry-run: it rebuilds and recreates.
- `deployafl.sh`: the same deploy for the AFL silo (`bs-afl-*`). Not covered here.
- `python tools/sync_watch.py snapshot` and `diff A.json B.json`: sync snapshots (`BS_BASE`, default `https://betterat.cricket/api`).
- `wrangler deploy` in `cloudflare-worker/`: ships the old-domain redirect (keep route `betterstats.cricket/*` active). See FLAG-OPS-6.

## Open follow-ups

- SPF, DKIM and DMARC for `bettersports.com.au`, and a real `email_provider` (default is `console`).
- Deploy the `betterstats.cricket` to `betterat.cricket` redirect (`cloudflare-worker/worker.js`, 301 GET/HEAD, 308 otherwise). Both hostnames serve the app until then.
- Reuse `ClubSearchField` in the short "Get your club on BetterCricket" CTA modal (`QuickEnquiryModal`), which still posts a free-text club name.
- Set `CORS_ORIGINS` to `https://betterat.cricket` in the server `.env` (hygiene: CORS is dormant, the frontend uses same-origin relative `/api`).
- Dormant monthly toggle in `ComparisonTable` left in place; `BILLING_CYCLES` remains so a super admin can record a cycle.

## Flags: conflicting, superseded or possibly obsolete guidance

- [FLAG-OPS-1] Archive says the Branch is `claude/fix-historical-game-data-QEN3b` and to push to it AND to `main` via MCP after each change. | Stale: that branch is not in `git branch`, the working branch is `main`, and deploy pulls `origin main`. | Branch, original L12696-12700 | retire (do not follow it; use the branch the session is on).
- [FLAG-OPS-2] Archive says `deploy.sh` has a `[4/4]` step for the NPM refresh and that the deploy recreates with `up -d --no-deps --force-recreate`. | `deploy.sh` now has 7 steps: pull, build, `rm -sf` then `up -d --no-deps` (not `--force-recreate`, which hit a fixed-`container_name` rename conflict), NPM refresh (4), API health check (5), backup-agent check (6), backup timer install (7). Rule 2's long form is approximate. | Server Deploy Command, L12334-12355; Admin Outage #2, L12373-12392 | verify against `deploy.sh`, keep the `COMPOSE_PROJECT_NAME`, `--no-deps` and no-`--remove-orphans` rules.
- [FLAG-OPS-3] Deploy and outage text say "see CLAUDE.md 'June 2026 Production Outage - Post-Mortem'". | `deploy.sh` and `deployafl.sh` comments still cite that CLAUDE.md heading, which now lives only in the archive and this guide. | Server Deploy Command; both post-mortems | verify, then repoint those comments here.
- [FLAG-OPS-4] Post-mortem tells you to use `docker run`, `docker volume ls`, `docker exec` for diagnosis, while the deploy rules ban bare `docker`. | The diagnostics and volume clone are one-off incident tooling against volumes outside any compose service. | Server Deploy Command; June 2026 Production Outage, L12356-12372 | keep both; use `docker compose exec` wherever a service exists.
- [FLAG-OPS-5] Archive says `BetterAdmin = fees + comms` in `MODULE_TOGGLES`. | Code: `admin` covers `fees, comms, merch, crm`; there are also `core` and `fantasy` toggles; `org_entitled_modules` now requires a live Core before any add-on works. | Modular entitlements, L12540-12564 | keep the "no tiers" rule; treat the module list as changed.
- [FLAG-OPS-6] Archive says the redirect worker is "ready but not yet deployed". | Files exist; deployment state is not visible from the repo. | Public Domain, L12393-12402 | verify with a `curl -I https://betterstats.cricket/` before relying on either state.
- [FLAG-OPS-7] Pricing section says `BUNDLE_DISCOUNT` in `pricing.js` is the model. | `pricing.js` still holds the schedule, but checkout reads a super-admin-editable one (`platform_settings.get_bundle_discount_schedule`, seeded from `billing_pricing.py`, a hand-kept port). Site and checkout can drift. `FANTASY` ($49) is outside the bundle. | Public Marketing Pricing, L12511-12539 | verify; the Stripe/billing guide is the authority for checkout.
- [FLAG-OPS-8] Contact section names `_resolve_onboarding_club (twenty_sync)` and "the Twenty push". | Twenty is retired: the function now lives in `services/engagement.py`. The `org_id` priority rule still holds. | Marketing Contact form, L12430-12510 | keep the rule, ignore Twenty references.

## Section coverage

| Original section (heading, original CLAUDE.md line range) | Disposition | Where captured |
|---|---|---|
| Writing Voice, L12321-12333 | rules extracted | Rule 25 |
| Server Deploy Command, L12334-12355 | rules extracted | Rules 1 to 9, Operator commands, FLAG-OPS-2, 3, 4 |
| June 2026 Production Outage, compose project split, L12356-12372 | rules extracted | Traps 1 to 3, rules 3 and 8 |
| June 2026 Admin Outage #2, NPM can't resolve betterstats-frontend, L12373-12392 | rules extracted | Traps 4 to 9, rule 9, FLAG-OPS-2 |
| Public Domain, L12393-12402 | rules extracted | Rules 10 to 14, Open follow-ups, FLAG-OPS-6 |
| Blog post social-share cards, L12403-12429 | rules extracted | Rule 15, Trap 10 |
| Marketing Contact form to club onboarding requests, L12430-12510 | rules extracted | Rules 16 to 20, Trap 11, FLAG-OPS-8 |
| .. Club name is a search, not a text box (migration 224, v9.12.2) | rules extracted | Rules 17 to 20, Open follow-ups |
| Public Marketing Pricing, modular model, L12511-12539 | rules extracted | Rule 21, FLAG-OPS-7 |
| Modular entitlements, tiers retired (v8.12), L12540-12564 | rules extracted | Rules 22, 23, FLAG-OPS-5 |
| Version Numbers, L12565-12573 | rules extracted | Rule 24 |
| Branch, L12696-12700 | history only (stale branch note) | FLAG-OPS-1 |
| Architecture, L12701-12707 | rules extracted | Rule 26 |
| Key Notes, L12812-12819 | rules extracted | Rules 27 to 31 |
