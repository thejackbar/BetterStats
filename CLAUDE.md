# BetterStats — Claude Session Notes

## Server Deploy Command

Always use the **central** compose file. Never use `/srv/docker/betterstats/docker-compose.yml`.

```bash
git -C /srv/docker/betterstats pull origin main && \
docker compose -f /srv/docker/docker-compose.yaml build --no-cache betterstats-frontend betterstats-backend && \
docker compose -f /srv/docker/docker-compose.yaml up -d --force-recreate betterstats-frontend betterstats-backend
```

- `--no-cache` on the build step is required to avoid stale Docker layer cache
- Only rebuild the two betterstats services, not the whole stack
- nginx-proxy-manager routes `betterstats.bltbox.com` → `betterstats-frontend` container on `docker-shared-net`
- The backend container name is `betterstats-backend` — this is the correct hostname in `nginx.conf`

## Version Numbers

Bump version in `frontend/src/components/Navbar.jsx` with every change:
- Small fix: `+0.0.0.1`
- Medium change: `+0.0.1`
- Large change: `+0.1`

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

2. **MyCricket / Pulselive Play Community** (legacy / pre-migration, back to ~2002): also GUID-keyed in URLs but maps internally to integer IDs. Reachable via:
   - `grassrootsapiproxy.cricket.com.au` — our existing proxy. Aggregate stats endpoints (`/participants/.../batting-statistics` etc.) work with no auth. Game-level endpoints (`/fixturesladders/games/{id}`, `/participants/games/{id}/batting`, `/scorecards/...`) **exist** but return `403 "The API key you provided does not have access to the requested resource."` — proxy's upstream key is scope-limited.
   - `apiv2.cricket.com.au` — has Swagger UI at `/`, OpenAPI at `/openapi.json`. Endpoints include `/scorecard?FixtureId=...&CompetitionId=...`, `/innings`, `/playerstats/career`. **BUT** this is the **international** stats API (Ashes, BBL, Sheffield Shield) — it does NOT contain club cricket data.
   - `api.playcommunity.pulselive.com` — only verified path is `/registration` so far; broader scope unknown.
   - `crm-communitycricket-cdn.cricket.com.au` — referenced by the bundle, scope unknown.

3. **Pagination quirk**: PlayHQ's `links.next` is sometimes returned forever even when the data is exhausted (observed paginating past page 1100 on a single grade). Our pagination loops cap at MAX_PAGES=200 and stop on the first short batch — never trust `links.next` alone.

4. **Org duplication trap**: `upsert_organisation` keys on whatever `id` is passed in, so calling sync with a PlayHQ UUID after the org was already created with a Grassroots GUID creates a duplicate row (one with `playhq_id=NULL` matching the other org's `id`). Detected May 2026 for Applecross, cleaned up via direct DELETE. Worth a defensive check in `upsert_organisation`.

## Sync Architecture

- **Full sync** (`POST /organisations/{id}/sync`): scheduled weekly Sun 03:00 + on-demand. Pulls aggregate stats per season, then PlayHQ Partner games for the recent 3 seasons.
- **Hard refresh** (`POST /club-admin/hard-refresh`, admin-only): same code path as full sync but explicit. For long historical pulls.
- **Per-player deep sync** (admin approves a `player_sync_request`): `deep_sync_player()` re-pulls all FINAL games for the org and re-inserts game-level rows for that one player.
- **Top-up logic** in `sync_game_level_data`: for games already in DB, re-fetches the scorecard and inserts only `(player_id, innings_number)` rows that are missing. Partnerships and fall-of-wickets are not re-derived for existing games (preserves manual edits).
- **Sync runs persisted** in `sync_runs` table (migration 005). Stale `running` rows are marked `error` on backend startup.

## Key Notes

- PlayHQ public game summary API is "not applicable to Cricket" — no scorecards without a partner JWT
- PostgreSQL `ORDER BY year DESC` defaults to NULLS FIRST — always use `.nullslast()`
- API field names: `bowlingEconomyRate`, `fieldingTotalCatches`, no `bowlingOvers` (derive from `bowlingBalls`)
- `Season.year` is NULL when Grassroots doesn't return `startDate` — extract from name (`"Summer 2010/11"` → `2010`) as a fallback
- `stats["players"]` in sync is misleading — it's `len(player_data)` summed across seasons, i.e. player-season records, not unique players. With 52 seasons × ~3.4 avg seasons/player ≈ 5326 (which Applecross actually shows). Worth renaming to `player_seasons`.
