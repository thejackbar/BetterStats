# BetterStats: Claude Session Notes

This file is loaded into every session, so it is kept short on purpose. It holds the rules that apply to almost every change, plus an index that tells you which topic guide to read before touching a given area.

**How the notes are organised**

| Layer | Path | Loaded automatically? |
|---|---|---|
| This file: universal rules and the index | `CLAUDE.md` | Yes |
| Topic guides: the standing rules, traps and checks for one area | `docs/dev-notes/guides/<topic>.md` | No. Read the one you need. |
| Archive: the full release-by-release history, verbatim | `docs/dev-notes/archive/<topic>.md` | No. Grep it, do not read it whole. |
| The untouched original of the old `CLAUDE.md` | `docs/dev-notes/archive/CLAUDE.original-2026-09-30.md` | No. |
| Section-by-section map of old to new, and flagged conflicts | `docs/dev-notes/COVERAGE.md`, `docs/dev-notes/FLAGS.md` | No. |

Never `@`-import a guide or an archive file from here, and never paste a release write-up back into this file. New release notes go at the end of the matching `docs/dev-notes/archive/<topic>.md`; a rule that outlives the release gets one line in the matching guide. Code comments that say "see CLAUDE.md" point at sections that now live in the archive: `docs/dev-notes/COVERAGE.md` maps each old section title to its new home.

## Read this before working on that

Open the guide first, then grep its archive if you need the reasoning or the measurements behind a rule.

| If you are about to touch | Read first |
|---|---|
| Deploying, the server, docker compose, nginx, the public domain, brand or email addresses, marketing pages, blog and share cards, plans and modules entitlements, changelog versions | `guides/platform-ops-and-site.md` |
| Cricket Australia, PlayHQ or Play-Cricket calls, `sync.py`, the sync scheduler, hard refresh, id namespaces, `games.match_format` | `guides/data-sources-and-sync.md` |
| Anything that reads per-game tables, player or grade or season ids, merges, club delete, shared fixtures between two clubs, or that could remove a club's hand-typed data | `guides/cross-club-and-data-safety.md` |
| Career or season figures, strike and economy rates, milestones, the grade type, match type and competition filters, StatLab, records, awards, the player profile | `guides/stats-figures-records-and-filters.md` |
| `get_scorecard`, the match page, fill-in players, public Fixtures and Lineups pages | `guides/scorecards-fixtures-and-lineups.md` |
| CSV or scorebook imports, manual games, adjustments, the scorecard reader, seasons and grades tidy-up, duplicate suggestions | `guides/imports-manual-entries-and-data-tidy.md` |
| The CricketStatz importer, pairing of imported and synced matches, `superseded_ddl`, merge carry | `guides/cricketstatz-import.md` |
| BetterSelect: selection board, squads, availability, selection rules, nets, check-in QR, player kit, date of birth | `guides/betterselect-selection-and-nets.md` |
| Player votes, medals, the leaderboard, awards night, the public voting page | `guides/betterselect-votes-and-medals.md` |
| Committee, meeting room, minutes, strategic plans, objectives, governance | `guides/clubhouse-committee-and-plans.md` |
| BetterAdmin or Clubhouse shell and UI kit, Directory, roster, areas and roles, fees and Accounts, merch, assets | `guides/clubhouse-people-roster-fees.md` |
| BetterIQ: opposition, selection analysis, trends, team analysis, scouting cards | `guides/betteriq.md` |
| Anything under `services/afl`, `routers/afl`, `frontend/src/afl`, `afl_main.py`, or a shared router mounted on football | `guides/betterfootball-afl.md` |
| BetterPosts, post templates and sizes, layers, club fonts and theme tokens, instructional videos | `guides/betterposts-socials-and-media.md` |
| Stripe checkout, subscriptions, coupons, pay by invoice, the billing feature flags | `guides/billing-stripe-and-invoicing.md` |
| Sales workspace, sales performance, commissions, engagement score, the retired Twenty CRM | `guides/sales-crm-and-commissions.md` |
| Meta ads reporting, `/trial` and `/demo`, webinar and StreamYard, usage tracking, wizard clubs | `guides/marketing-funnel-ads-and-webinar.md` |
| BetterComms lists, segments, templates, audiences, club notifications | `guides/comms-audiences-and-notifications.md` |
| Club Directory crawl, teaser snapshots, new club onboarding, setup wizard, admin navigation, Draft pages, KlubPro, dashboard messages | `guides/club-directory-onboarding-and-admin-shell.md` |

If your change spans two areas, read both guides. If a guide and the code disagree, the code wins: fix the guide in the same change.

## Project basics

- **Stack**: FastAPI, SQLAlchemy async and PostgreSQL in `backend/`; React, Vite and Tailwind in `frontend/`. Cricket runs from `app/main.py`. Football (AFL, BetterFootball) is a separate silo from the same repo, entrypoint `app/afl_main.py`, its own database and containers. Cricket's `main.py` must stay untouched by football work.
- **Modules**: BetterStats is Core and always on. BetterSelect, BetterSocials, BetterAdmin (fees, comms, merch, crm), BetterIQ are paid add-ons. A club's `module_overrides` list is the single source of truth for entitlement. The Good/Better/Best tiers are retired: do not reintroduce `TIER`, `TIER_INFO`, `requiredTier` or `organisations.tier`.
- **Data source**: Cricket Australia's Grassroots proxy, `/scores/*` for scorecards and the aggregate endpoints for season totals. Read `guides/data-sources-and-sync.md` before calling or changing anything that talks to it.
- **Brand and domain**: the public site is `https://betterat.cricket` (no `www`). The brand is one word, "BetterCricket". Module names are camelCase (BetterStats, BetterSelect, BetterSocials, BetterAdmin, BetterIQ). The trading company is BetterSports. Public contact and default reply-to address: `support@bettersports.com.au`.
- **Branch**: the harness names the branch to develop on for each session; follow that. An old note in the previous file said "active branch `claude/fix-historical-game-data-QEN3b`, push there and to `main`". It is stale and conflicts with per-session branch rules; it is kept in `docs/dev-notes/FLAGS.md`, not acted on.
- **Versions**: each release is its own file in `frontend/src/data/changelog/` (named like `v9-99-2.js`, default export `{ version, date, sortKey, title, items[] }`). Never hand-edit `frontend/src/version.js`. Small fix +0.0.0.1, medium +0.0.1, large +0.1. Check `origin/main` for the current top version and the highest migration number at the moment you merge, not only when you start: two migrations sharing a revision id break Alembic outright, and this has collided at least six times.
- **Writing voice**: any user-facing prose (copy, changelog items, UI strings, docs, PR and commit bodies) goes through the `humanizer` skill's rules: no em or en dashes, no forced triads, no promotional vocabulary, no tailing negations, plain "is/are/has". Plain Australian cricket-club voice. Page `<title>` separators keep the site-wide `—`.

## Deploy (server, not this sandbox)

- The box runs all ~26 containers as ONE systemd compose project, `bltbox_docker_app`, defined in `/srv/docker/docker-compose.yaml`. Deploy with `/srv/docker/betterstats/deploy.sh`.
- Long form, from `/srv/docker`: `export COMPOSE_PROJECT_NAME=bltbox_docker_app`, `git -C /srv/docker/betterstats pull origin main`, `docker compose build --no-cache betterstats-frontend betterstats-backend`, then `docker compose up -d --no-deps --force-recreate betterstats-frontend betterstats-backend`.
- `COMPOSE_PROJECT_NAME=bltbox_docker_app` is mandatory. Without it a second betterstats stack appears on an empty data volume (the June 2026 outage).
- Never recreate `betterstats-db`, never pass `-f`, never add `--remove-orphans`, never use bare `docker run/restart/exec/ps`. Act on containers only through `docker compose` from `/srv/docker`.
- The frontend nginx must proxy `/api` to `betterstats-backend`, never the bare `backend` host (another app's API).
- Intermittent 502 on one asset after a frontend recreate: nginx-proxy-manager per-worker DNS. `deploy.sh` self-heals it; if not, `docker compose restart` the proxy service. Full diagnosis order is in `guides/platform-ops-and-site.md`.

## Rules that apply to almost every change

**Data and identity**
1. **A club's hand-typed work is never deleted or overwritten by code.** Manual games, their innings and hand-typed corrections have no upstream to re-pull from. A function may add to them and move them; it may only remove what it wrote itself. A merge moves records and never deletes them: every table recording what a player did belongs on `services/merge_carry.CARRIED`. `backend/verification/verify_merge_carry.py` enforces both.
2. **A fixture between two synced clubs is ONE `games` row owned by whichever club synced first.** Never decide "is this game ours" from `seasons.organisation_id`, and never classify a grade from a row your club owns. Use `services/club_grades.club_game_sql` for ownership and `club_grade_rows` for classification. Any per-game read that attributes rows to our side must also scope `players.organisation_id`. `is_club_innings` is set per club, so it is not a club filter.
3. **Players, grades and seasons have per-club ids.** The raw Cricket Australia GUID lives in `grassroots_id`; the primary key is that GUID, or `uuid5(org, guid)` only when another club already holds it. Use `_resolve_org_player`, `_resolve_org_grade` and their season equivalent. Never write a global `session.get(Player|Grade, raw_guid)` create-or-skip in sync. Every API call to Cricket Australia uses the raw GUID.
4. **Derive on read, do not store**: ages, per-game paid status, balances, ranks, rates, winners of a season. A stored copy is wrong the moment its inputs are corrected.
5. **An absent key is not a clear.** For PATCH bodies use `model_fields_set` (or `exclude_unset`) so "not sent" leaves the field alone and an explicit null or empty clears it.
6. **Warn, do not refuse, where a club may legitimately lack a figure.** Where the data cannot answer, say nothing rather than guess. A figure that is correctly zero or a control that is correctly absent must still explain itself on screen. Name the lens a figure is measured under (filters, source, scope).
7. **Scripts that change stored data take an org or `all`, are dry-run by default, and write with `--apply`.** They live in `backend/app/scripts/` (`ops/` is not in the backend image). Anything that repairs data writes an audit entry where the club can undo it. Never delete a row somebody decided something about (an unsubscribe, a note, a CRM link, a bounce): keep it, mark it (for example `former_at`) and untick it.

**Database and migrations**
8. Migrations are additive and idempotent. The DDL lives once in a shared `services/*_ddl.py` list that both the Alembic migration and the `main.py` lifespan mirror run. Downgrades drop the added columns, never a table an earlier migration owns. Mirror new raw-SQL tables and columns in the lifespan. The lifespan re-runs every statement on every boot, so each must be idempotent: guard inserts with `NOT EXISTS` (`ON CONFLICT` needs a unique constraint that may not exist). A migration's docstring, or its row in `alembic_version`, is intent and not proof that its effect is in the database: grep for the actual writer and read the result back (`pg_get_viewdef`, `pg_constraint`).
9. Raw-SQL lifespan tables are invisible to `create_all`, and a column added in raw SQL must also be mapped on the ORM model or reads fail at request time. New Pydantic request fields silently never reach the service unless added to the model.
10. The `v_effective_*` views are the one place a cross-cutting rule (cross-club scope, washouts, paired imports) is applied. Change them only through the module that owns them (`services/superseded_ddl.py` for the eight source-aware views), because the lifespan re-applies that module on every boot and would revert an edit made elsewhere. `CREATE OR REPLACE VIEW` cannot drop columns.
11. Never scope a view or table read by `WHERE x IN (SELECT ...)` when a bound array of ids will do: `= ANY(:ids)` with a `CAST(:ids AS uuid[])` is pushed into the view and can be tens of thousands of times faster. asyncpg cannot type a bare `:param IS NULL`; cast it.

**SQLAlchemy async traps**
12. A swallowed database error must be followed by a rollback, and a rollback expires every loaded object. Use `services/session_safety.rollback_keeping(db, *instances)` so later attribute reads are not lazy IO (`MissingGreenlet`). After `commit()`, `await db.refresh(obj)` before serialising.
13. `Player.display_name` is a Python property, not a column: select `display_name_override` and `name`. A `from x import y` inside a function body compiles and imports but can still break; after any rename, sweep for it.
14. Background work started from a request (list syncs, notifications, pushes) runs on its own session after the caller's commit and never raises; a marketing-list failure must not take down a registration. A broad `except Exception` around a large rebuild hides a bug in the rebuild behind "fall back to old data". Everything inside it needs the same null-safety as the rest of the function.

**Permissions and gating**
15. A UI nav item carries the capability its own router already enforces; never a role gate. The server is the real gate, the UI only presents. `admin` is a billing umbrella, not an entitlement key: entitlement checks use `fees`, `comms`, `merch`, `crm`.
16. Audience and permission rules fail closed: an unknown value, an unpicked rule or an out-of-scope field empties the result or is refused, never widens it. BetterComms scope rule: a club's audience never exposes Super Admin outreach fields, copy or context. The two field sets are imported by exactly one screen each; never add a runtime switch between them.

**Shared code**
17. A row builder shared by synced and manual tables (scorecards, effective views) may only read columns that exist on both: a column read on one side 500s every record from the other. Anything cached (dossiers, snapshots) carries a version constant; bump it whenever the payload's shape changes. Anything that alters what a club pays comes from one shared price function, never a second hand-kept number.

**Frontend traps**
18. Never declare a component inside a render function (it remounts and steals the caret). Hooks go above every early return. A composite widget inside a `<label>` cancels its own clicks. `min-w-0` goes on the element that may shrink, and `truncate` inside a wrapping flex row expands instead.
19. A new top-level route is a club slug until four lists say otherwise (`og_preview.RESERVED_ROOT_SEGMENTS`, `FaviconManager.RESERVED_ROOTS`, `SponsorFooter.RESERVED_ROOT_SEGMENTS`, `lib/marketingPaths`). Anything reading a function's own name (`Component.name`) breaks in the minified bundle; set explicit `displayName`.
20. A `waitUntil: 'networkidle'` never settles on this app (heartbeat beacon); wait for the element. CSS `uppercase` makes `innerText` return uppercase; write checks in that casing.

**Verification standard (how changes here are proved)**
21. Prove a change against a real Postgres through the shipped route bodies and services, with a **control run** against the previous commit that fails on exactly the reported behaviour. A control run that crashes is not a control run: read new keys through presence-safe accessors so absence is reported. A check that passes against the broken code is not a check; pair every "X is absent" check with a check that X could be present.
22. For UI, drive the real screen in Chromium with the API stubbed at the network layer, assert the exact request on the wire, check 390px for overflow, and screenshot layout changes. Serve the production build for long runs and never rebuild `dist` under a running one.
23. When diagnosing production: confirm the deployed code is what you think it is, then read the container logs for the traceback before re-reading source. When every endpoint on a page is uniformly slow, look for the thing they all call.
24. Suites share one database and their stub tables collide; run a suite whose stubs differ on its own database. A harness table that merely looks right is worse than none: copy the lifespan DDL column for column, including later ALTERs.

**Money and outbound effects**
25. Commission is earned on a Stripe payment, never on a CRM stage. A Stripe id belongs to one mode (test or live); cache keys include the mode. Checkout and invoicing are behind feature flags that default off; new invoicing or checkout endpoints depend on `require_billing_checkout_enabled`.
26. The console email provider is not a send. Anything that emails must treat "no live provider" as a failure the user can read, never as success.
27. Outbound traffic to Cricket Australia, PlayHQ, Play-Cricket, Meta or Twenty is bounded, politely paced, and stoppable. New unattended crawls honour the `marketing_crawl_control` Stop switch and start off (limit unset means zero).

## When you finish a change

- Add the release write-up to the end of the matching `docs/dev-notes/archive/<topic>.md`, and only the durable rule, in one or two lines, to the matching guide.
- If the change alters a rule in a guide, edit the guide. If it contradicts something in `docs/dev-notes/FLAGS.md`, resolve that entry.
- Do not add sections to this file unless the rule genuinely applies to almost every change. Keep it under about 10,000 tokens.
