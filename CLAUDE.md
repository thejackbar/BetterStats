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

Active development branch: `claude/fix-api-org-id-error-9dS4h`
Push to this branch AND to `main` via MCP after each change.

## Architecture

- **Backend**: FastAPI + SQLAlchemy + PostgreSQL (`backend/`)
- **Frontend**: React + Vite + Tailwind CSS (`frontend/`)
- **API**: Grassroots API proxy (`grassrootsapiproxy.cricket.com.au`) — season-aggregate stats only, no game-level data
- `jsconfig=eccn:true` is a ServiceStack formatting flag, NOT an API key

## Key Notes

- PlayHQ public game summary API is "not applicable to Cricket" — no scorecards without a partner JWT
- PostgreSQL `ORDER BY year DESC` defaults to NULLS FIRST — always use `.nullslast()`
- API field names: `bowlingEconomyRate`, `fieldingTotalCatches`, no `bowlingOvers` (derive from `bowlingBalls`)
