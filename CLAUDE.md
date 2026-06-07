# BetterStats — Claude Session Notes

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

## Public Domain

The canonical public domain is **`https://betterstats.cricket`** (no `www`). The old `betterstats.bltbox.com` domain is retired.

- Hardcoded references live in `frontend/src/hooks/usePageMeta.js` (`BASE_URL`) and `frontend/index.html` (`og:url`) — keep both on the apex domain.
- `CORS_ORIGINS` should be `https://betterstats.cricket` in the server `.env`, but note CORS is dormant in practice: the frontend calls the API via a same-origin relative `/api` path, so cross-origin checks never fire. Updating it is hygiene, not a functional requirement.
- Any new build/config that references the public URL must point to `betterstats.cricket`.

## Version Numbers

Each release lives in its own file under **`frontend/src/data/changelog/`** — never hand-edit `frontend/src/version.js` (it derives `SITE_VERSION` from the highest-sortKey entry in that folder). Drop a new `v-X-Y-Z.js` file when you ship:
- Small fix: `+0.0.0.1`
- Medium change: `+0.0.1`
- Large change: `+0.1`

See "Feature Changelog" below for the file format.

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
