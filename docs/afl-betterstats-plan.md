# BetterStats AFL — build plan (Aug 2026)

The AFL expansion of BetterStats, per the "Multi-sport architectural design"
objectives: **one codebase, per-sport operational silos**. Common bug fixes and
enhancements land once; each sporting code runs as its own set of Docker
services against its own database, so a problem in one sport can never take
down another.

Companion doc: `docs/afl-playhq-data-source.md` — the PlayHQ AFL API
investigation this build is grounded in (endpoints, headers, field mappings,
all verified live).

## Architecture

- **One repo, one backend, one frontend.** No `afl-backend/` fork. AFL lives
  inside the existing `backend/` and `frontend/` as sport-scoped modules.
- **Silo = deployment, not codebase.** Elton's services `bs-afl-backend` /
  `bs-afl-frontend` / `bs-afl-database` are built from the SAME images/source
  as the cricket stack, differing only in:
  - backend: the uvicorn entrypoint (`app.afl_main:app` instead of
    `app.main:app`) + its own `DATABASE_URL` pointing at `bs-afl-database`
  - frontend: the Vite build arg `VITE_SPORT=afl`
- **Cricket is untouched.** `app/main.py` (the cricket entrypoint, in
  production) is not modified. The AFL entrypoint `app/afl_main.py` is a
  separate FastAPI app that imports the shared infrastructure. Zero regression
  surface for the live cricket product.

### What's shared vs sport-specific (backend)

Shared (reused as-is by the AFL app — this is the "fix once" surface):
- `app/config/settings.py` (gains a `sport` field, default `cricket`)
- `app/models/db.py` core tables: `organisations`, `users`,
  `club_memberships`, `login_attempts`, `seasons`, `grades`, `players`,
  `games`, `player_name_aliases`, `sync_runs`, `platform_settings`
- `app/routers/auth.py` — the whole session/login/lockout stack
- `app/services/sync.py`'s run-bookkeeping helpers (`start_sync_run`,
  `update_sync_run`, `finish_sync_run`, `_progress`)

AFL-specific (new):
- `app/models/afl.py` — AFL stat tables (same SQLAlchemy `Base`):
  - `afl_teams` — the club's team entries per grade ("Curtin Uni Wesley (A)")
  - `afl_game_details` — 1:1 extension of `games` (scores, goals/behinds,
    round, status, start time, outcome description, PlayHQ raw id)
  - `afl_game_periods` — quarter-by-quarter scores per side (incl. OT)
  - `afl_player_game_lines` — one row per player per game, BOTH sides
    (ours resolved to a `players` row; opposition kept name-only), carrying
    jumper number, goals, behinds, best-on-ground ranking, player points
  - `afl_game_events` — the play-by-play feed, stored at sync time so the
    public match page never hits PlayHQ live
  - `afl_player_season_stats` — the rollup (games, goals, behinds, BOG count)
    recomputed from the per-game lines on every sync (the cricket "Fix
    Missing Totals" philosophy is the PRIMARY path here — PlayHQ AFL's own
    aggregate endpoint is grade-wide, not club-scoped, so we compute our own)
- `app/services/afl/playhq_client.py` — the two GraphQL endpoints
- `app/services/afl/sync.py` — the AFL sync engine
- `app/services/afl/aggregations.py` — stats reads for the public routers
- `app/routers/afl/` — public + admin routers
- `app/afl_main.py` — the silo entrypoint

### Identity scheme — per-club ids from day one

The cricket product spent months digging out of shared-GUID collisions
(players, grades, seasons, games — see CLAUDE.md's collision fixes). AFL never
enters that hole: **every synced row's primary key is
`uuid5(organisation_id, playhq_id)`**, with the raw PlayHQ id stored in the
row (`grassroots_id` on the shared tables, `playhq_id` on AFL tables). Two
clubs in the same competition always own disjoint rows; the shared-game
"whoever synced first owns the row" residue can't happen. The raw id is what
every PlayHQ API call uses.

Player identity keys on the PlayHQ **profile id** (stable per person across
seasons), not the participant id (per-registration). Both are stored on each
game line for traceability.

### Sync pipeline (all verified live against Curtin Uni Wesley, org d14445c4)

1. `discoverCompetitions(organisationID)` → competitions + seasons
2. `discoverTeams(filter: {seasonID, organisationID})` → our teams + grades
3. `gradeAllRounds` / `discoverGradeFixture(gradeID)` → every round + game id
   in each of our grades (we keep only games our team plays in)
4. `gameView(gameId)` → result, quarter scores, both teams' player stat lines,
   best players, venue
5. `gameEventsSpectator(gameID)` (spectator endpoint) → play-by-play, stored
6. Rollup `afl_player_season_stats` from the stored lines

Headers: `tenant: afl` on `api.playhq.com/graphql`, `X-PHQ-Tenant: afl` on
`spectator.playhq.com/graphql` (lowercase both — see the data-source doc).
Politeness: shared semaphore, short in-process TTL caches, incremental sync
skips already-FINAL games that already hold stats.

### Frontend

Single React app, sport picked at build time: `VITE_SPORT=afl` (Vite
statically replaces `import.meta.env.VITE_SPORT`, so each sport's bundle
tree-shakes the other's pages out). AFL pages live in `src/pages/afl/`,
reusing the shared theme/components. `src/lib/aflApi.js` holds the AFL API
calls (kept out of the huge cricket `api.js`).

Pass-1 public pages (per the product decision): **Dashboard, Players, Player
Profile, Records, Leaderboard, Games (list + match view with quarter scores,
both teams' stat lines, play-by-play), Compare.** No StatLab, no Yearbook, no
Website module. Admin: login + Data Sync (Sync Now / Full Rebuild / history)
+ basic settings.

## Product decisions (defaults taken — flag if wrong)

| Decision | Choice |
|---|---|
| Stats tracked | Games played, goals, behinds, Best on Ground; quarter scores + play-by-play per game |
| BOG leaderboard | Flat count of best-players mentions (matches PlayHQ's own BEST_PLAYER stat). The per-game *ranking* is stored, so a weighted (Brownlow-style) view can be added later with no resync |
| Brand constant | "BetterFootball" (single constant + meta tags, trivial to change) |
| Pass-1 scope | Sync + public site + admin core. Self-serve club registration is pass 2 (it's the betterat.football entry point, but the core must be verified first) |
| Season aggregates | Computed from per-game lines at sync time, not pulled from PlayHQ's grade leaderboard (that endpoint is competition-wide + paginated; our rollup is exact and club-scoped) |

## Later passes (agreed direction, not built yet)

- **Pass 2**: self-serve club registration (port `public_self_serve` flow),
  weekly sync scheduler, super-admin club management.
- **BetterSelect AFL**: drag-and-drop field whiteboard — positions FF/HF/C/HB/FB
  + Followers, 12–18 on field, 1–20 bench. Needs its own design round.
- Other modules (Socials, Fees/Admin, IQ) reuse their cricket code where
  sport-agnostic; each gets an AFL review before enabling.

## Deploy notes (for Elton)

- `bs-afl-backend`: same image as `betterstats-backend`, command
  `uvicorn app.afl_main:app --host 0.0.0.0 --port 8000`, env:
  `DATABASE_URL=postgresql+asyncpg://afl:<pw>@bs-afl-database/betterstats_afl`,
  `SPORT=afl`, `SECRET_KEY=<its own>`, `COOKIE_SECURE=true`.
- `bs-afl-database`: postgres:15 (matching cricket), its own volume.
- `bs-afl-frontend`: same frontend source, build arg `VITE_SPORT=afl`; nginx
  proxies `/api` to `bs-afl-backend` (NEVER a bare `backend` hostname — see
  the June 2026 crossed-proxy post-mortem in CLAUDE.md).
- First boot of `bs-afl-backend` creates the schema in its own empty database
  (`Base.metadata.create_all` — includes the shared tables; unused
  cricket-specific tables exist empty in the AFL DB by design, so any shared
  code path finds its table).
