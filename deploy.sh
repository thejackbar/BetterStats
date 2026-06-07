#!/usr/bin/env bash
#
# BetterStats production deploy — bltbox host only.
#
# This box runs ~26 containers as ONE systemd-managed compose project named
# `bltbox_docker_app` (see /etc/systemd/system/docker-compose-app.service:
# WorkingDirectory=/srv/docker, Environment=COMPOSE_PROJECT_NAME=bltbox_docker_app).
# BetterStats is defined inside the SHARED central file /srv/docker/docker-compose.yaml.
#
# The COMPOSE_PROJECT_NAME below is LOAD-BEARING. Without it, `docker compose`
# run from /srv/docker defaults to the project name `docker` (the directory name),
# which spins up a SECOND betterstats stack on a SEPARATE, EMPTY pgdata volume and
# steals the betterstats-* container names from the real one. That is the exact
# June 2026 outage — see CLAUDE.md "June 2026 Production Outage — Post-Mortem".
#
# Safe by construction: only the two betterstats services are rebuilt/recreated.
# The database (betterstats-db) and the other ~24 apps on the box are never touched.
#
set -euo pipefail

cd /srv/docker
export COMPOSE_PROJECT_NAME=bltbox_docker_app   # must match the systemd project — do NOT change

# --- Quieten harmless warnings from the SHARED compose file -------------------
# `docker compose` parses the WHOLE central file every run (even though we only
# target the two betterstats services), so it warns about ${VARS} that belong to
# OTHER apps and the orphan containers those apps run. None of this affects
# betterstats. We silence the noise WITHOUT touching the shared .env or the other
# services:
#   * COMPOSE_IGNORE_ORPHANS skips the orphan-container check — it does NOT remove
#     anything (unlike --remove-orphans, which is banned: it would delete
#     klubpro-mongo / restreamer). Their containers are left exactly as-is.
#   * Exporting the other apps' vars as empty strings (preserving any real value
#     if one is already set) marks them "set", so compose stops printing
#     "variable is not set. Defaulting to a blank string." The resolved value is
#     blank either way — identical behaviour, just no warning. We never recreate
#     those services here, so this cannot change their running config.
export COMPOSE_IGNORE_ORPHANS=1
export POSTGRES_DB="${POSTGRES_DB:-}"
export POSTGRES_USER="${POSTGRES_USER:-}"
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-}"
export LANGFLOW_SUPERUSER="${LANGFLOW_SUPERUSER:-}"
export LANGFLOW_SUPERUSER_PASSWORD="${LANGFLOW_SUPERUSER_PASSWORD:-}"

echo "==> [1/4] Pulling latest main into /srv/docker/betterstats"
git -C /srv/docker/betterstats pull origin main

echo "==> [2/4] Rebuilding betterstats images (no cache)"
docker compose build --no-cache betterstats-backend betterstats-frontend

echo "==> [3/4] Recreating betterstats only (db + other services untouched)"
# Why rm+up instead of `up --force-recreate`:
# The central file pins fixed container_names (betterstats-frontend / -backend).
# With a fixed name, `--force-recreate` does a fragile rename dance — it renames
# the old container to <shortid>_betterstats-frontend, creates the new one, then
# removes the temp. If a past run left that temp container behind (it keeps the
# compose service label AND still holds the /betterstats-frontend name), the next
# --force-recreate dies with:
#   "Error when allocating new name: Conflict. The container name
#    /betterstats-frontend is already in use by <shortid>_betterstats-frontend"
# — which is exactly the failure that forces a second deploy. Explicitly removing
# the two services first frees the names (rm -sf also clears any leftover
# <shortid>_ orphans of these services, since they carry the same service label),
# so `up` always creates clean containers on the FIRST run. Only the two named
# services are touched — db and the other ~24 apps are never affected.
docker compose rm -sf betterstats-backend betterstats-frontend || true
docker compose up -d --no-deps betterstats-backend betterstats-frontend

echo "==> [4/4] Refreshing nginx-proxy-manager so it resolves the frontend's NEW IP"
# Recreating betterstats-frontend gives it a NEW Docker IP. nginx-proxy-manager
# caches the old DNS result per worker and then 502s with
#   "betterstats-frontend could not be resolved (2: Server failure)"
# — the Jun 2026 admin outage (see CLAUDE.md post-mortem). A graceful reload
# spins fresh workers that re-resolve; if the site is still down we fall back to
# a full restart (a few seconds' blip across all proxied apps, but reliable —
# a reload alone did NOT clear it during the incident).
#
# Everything below uses `docker compose` (NOT bare `docker exec/restart/ps`) so it
# stays inside the pinned COMPOSE_PROJECT_NAME project. Bare `docker` commands are
# banned on this box — they spawn duplicate stacks that are a nightmare to
# untangle. We discover the proxy's SERVICE name from the project so we never
# hardcode a container name.
NPM_SVC="$(docker compose ps --services 2>/dev/null | grep -iE 'proxy|npm|manager' | head -1)"
health() { for i in 1 2 3; do curl -s -o /dev/null -w '%{http_code} ' "https://betterstats.cricket/" || printf '000 '; done; }
if [ -n "$NPM_SVC" ]; then
  docker compose exec -T "$NPM_SVC" nginx -s reload 2>/dev/null || true
  sleep 3
  codes="$(health)"; echo "    after reload: $codes"
  case "$codes" in
    *50[0-9]*|*000*)
      echo "    still failing — restarting $NPM_SVC to flush its DNS resolver (brief blip)"
      docker compose restart "$NPM_SVC" >/dev/null; sleep 4
      echo "    after restart: $(health)" ;;
    *) echo "    frontend reachable via the proxy ✓" ;;
  esac
else
  echo "    no proxy service found in this compose project — skipping proxy refresh"
fi

echo "==> Status:"
docker compose ps betterstats-backend betterstats-frontend

cat <<'NOTE'

Done — https://betterstats.cricket

Reminders:
  * NEVER add --remove-orphans (it would delete klubpro-mongo / restreamer — other apps).
    The orphan warning is silenced via COMPOSE_IGNORE_ORPHANS, which leaves them untouched.
  * NEVER recreate betterstats-db. Your data lives in the bltbox_docker_app_betterstats_pgdata
    volume; leave the db running.
  * The old "POSTGRES_PASSWORD / LANGFLOW_* not set" warnings are now silenced (those vars
    belong to other services in the shared compose file, not betterstats) — see the exports
    near the top. If a NEW "variable is not set" warning appears, add it to that export block.
NOTE
