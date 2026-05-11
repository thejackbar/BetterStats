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

2. **MyCricket / Pulselive Play Community** (legacy / pre-migration, back to ~2002): GUID-keyed throughout (different namespace from PlayHQ). Reachable via the same `grassrootsapiproxy.cricket.com.au` host we already use — just on a different path prefix than the proxy's restricted endpoints:
   - **`/scores/teams/{team_id}/matches`** — list of matches a team played that season. ✓ unauthenticated.
   - **`/scores/matches/{match_id}?responseModifier=includeScorecard`** — full scorecard (batting, bowling, fielding, fall-of-wickets). ✓ unauthenticated. Returns **HTTP 204 No Content** for post-migration PlayHQ-namespace IDs, which is a clean "not mine" signal.
   - `participantId` in the response **is the same GUID as `players.id` in our DB** — no extra mapping needed.
   - The restricted paths (`/fixturesladders/games/{id}`, `/participants/games/{id}/batting`, `/scorecards/...`) all return `403 "API key does not have access"`. **Don't try those.** The `/scores/*` path is the one that works.
   - `apiv2.cricket.com.au` — has Swagger UI at `/`, OpenAPI at `/openapi.json`. Looks promising at first glance but is the **international** stats API (Ashes, BBL, Sheffield Shield) — does NOT contain club cricket data. Skip.
   - `api.playcommunity.pulselive.com` — verified `/registration` only; broader scope unknown.
   - `crm-communitycricket-cdn.cricket.com.au` — referenced by the bundle, scope unknown.

   **How to find the real API call**: the play.cricket.com.au website is a CSR Pulselive SPA (`window.API_ACCOUNT = 'playcommunity'`, bundle at `/resources/playcricket/v1.28.6/scripts/bundle-es.min.js`). HTML is just a shell. Anonymous server-side curls of `ca.playhq.com/*` and JS bundles get 403'd. Network-tab the request from a real browser load to recover the URL — that's how we found `/scores/*`.

3. **Pagination quirk**: PlayHQ's `links.next` is sometimes returned forever even when the data is exhausted (observed paginating past page 1100 on a single grade). Our pagination loops cap at MAX_PAGES=200 and stop on the first short batch — never trust `links.next` alone.

4. **Org duplication trap**: `upsert_organisation` keys on whatever `id` is passed in, so calling sync with a PlayHQ UUID after the org was already created with a Grassroots GUID creates a duplicate row (one with `playhq_id=NULL` matching the other org's `id`). Detected May 2026 for Applecross, cleaned up via direct DELETE. Worth a defensive check in `upsert_organisation`.

## Sync Architecture

- **Full sync** (`POST /organisations/{id}/sync`) / **Hard refresh** (`POST /club-admin/hard-refresh`): scheduled weekly + on-demand. Three game-level passes in order:
  1. **Grassroots aggregate** (`playhq_client.get_*_stats`) — season totals for all 52 seasons. Source of `player_season_stats`.
  2. **PlayHQ Partner** (`playhq_partner_client.get_org_games` + `sync_game_level_data`) — recent-only (~3 seasons of game-level coverage with public API key). Has top-up logic.
  3. **Grassroots scores** (`grassroots_scores_client` + `sync_grassroots_game_level_data`) — historical scorecards back to ~2002. Enumerates teams-per-season, fans out to `/scores/teams/{id}/matches`, fetches `/scores/matches/{id}?includeScorecard` for each. Skips PlayHQ-namespace IDs that 204.
- **Per-player deep sync**: `deep_sync_player()` — admin-triggered, re-pulls FINAL PlayHQ games for that player.
- **Top-up in `sync_game_level_data`**: for PlayHQ games already in DB, re-fetches the scorecard and inserts only `(player_id, innings_number)` rows that are missing. Partnerships/FoW not re-derived for existing games (preserves manual edits).
- **Sync runs persisted** in `sync_runs` table (migration 005). Stale `running` rows are marked `error` on backend startup.

## Key Notes

- PlayHQ public game summary API is "not applicable to Cricket" — no scorecards without a partner JWT
- PostgreSQL `ORDER BY year DESC` defaults to NULLS FIRST — always use `.nullslast()`
- API field names: `bowlingEconomyRate`, `fieldingTotalCatches`, no `bowlingOvers` (derive from `bowlingBalls`)
- `Season.year` is NULL when Grassroots doesn't return `startDate` — extract from name (`"Summer 2010/11"` → `2010`) as a fallback
- `stats["players"]` in sync is misleading — it's `len(player_data)` summed across seasons, i.e. player-season records, not unique players. With 52 seasons × ~3.4 avg seasons/player ≈ 5326 (which Applecross actually shows). Worth renaming to `player_seasons`.
