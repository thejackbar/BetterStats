#!/usr/bin/env bash
#
# BetterFootball (AFL) production deploy — bltbox host only.
#
# Mirrors deploy.sh (the BetterStats/cricket deploy) exactly, scoped to the
# AFL silo — see ops/afl/docker-compose.afl.yml and CLAUDE.md's "Multi-sport:
# the AFL silo" note. Same box, same shared central compose file
# (/srv/docker/docker-compose.yaml), same systemd-managed project
# `bltbox_docker_app` (/etc/systemd/system/docker-compose-app.service).
#
# The COMPOSE_PROJECT_NAME below is LOAD-BEARING for the exact same reason as
# deploy.sh — see CLAUDE.md "June 2026 Production Outage — Post-Mortem"
# (compose-project split). Without it, `docker compose` run from /srv/docker
# defaults to project `docker` and spins up a second, empty-database AFL stack
# that steals the bs-afl-* container names.
#
# Safe by construction: only bs-afl-backend / bs-afl-frontend are
# rebuilt/recreated. bs-afl-database, bs-football-landing (the umbrella
# choose-your-code page — shared across every football code, deliberately NOT
# part of any one silo, see ops/afl/docker-compose.afl.yml) and the other ~24
# apps on the box are never touched by this script. If football-landing/
# itself changed, redeploy it separately:
#   docker compose build bs-football-landing && \
#   docker compose up -d --no-deps bs-football-landing
#
# First bring-up on a brand-new box (empty AFL database) is NOT this script —
# follow the "First bring-up" steps at the top of
# ops/afl/docker-compose.afl.yml instead (it needs the AFL_DB_PASSWORD /
# AFL_SECRET_KEY .env vars set and the afl_bootstrap script run once).
#
set -euo pipefail

cd /srv/docker
export COMPOSE_PROJECT_NAME=bltbox_docker_app   # must match the systemd project — do NOT change

# --- Quieten harmless warnings from the SHARED compose file -------------------
# Same reasoning as deploy.sh: this reads the WHOLE central file even though we
# only target the two bs-afl-* services, so it warns about other apps' unset
# ${VARS} and orphan containers. COMPOSE_IGNORE_ORPHANS silences the orphan
# check WITHOUT removing anything (unlike the banned --remove-orphans, which
# would delete klubpro-mongo / restreamer). We never recreate those services
# here, so nothing here can change their running config.
export COMPOSE_IGNORE_ORPHANS=1
export POSTGRES_DB="${POSTGRES_DB:-}"
export POSTGRES_USER="${POSTGRES_USER:-}"
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-}"
export LANGFLOW_SUPERUSER="${LANGFLOW_SUPERUSER:-}"
export LANGFLOW_SUPERUSER_PASSWORD="${LANGFLOW_SUPERUSER_PASSWORD:-}"

echo "==> [1/5] Pulling latest main into /srv/docker/betterstats"
git -C /srv/docker/betterstats pull origin main

echo "==> [2/5] Rebuilding bs-afl images (no cache)"
docker compose build --no-cache bs-afl-backend bs-afl-frontend

echo "==> [3/5] Recreating bs-afl-backend/-frontend only (db + landing + other services untouched)"
# Why rm+up instead of `up --force-recreate`: same fixed-container_name rename
# trap deploy.sh documents for betterstats-frontend/-backend — a stale
# <shortid>_bs-afl-frontend temp container from a past --force-recreate would
# collide on the next one. Explicitly removing first frees the names, so `up`
# always creates clean containers. --no-deps keeps this to exactly these two
# services — bs-afl-database is never recreated or even inspected here.
docker compose rm -sf bs-afl-backend bs-afl-frontend || true
docker compose up -d --no-deps bs-afl-backend bs-afl-frontend

echo "==> [4/5] Refreshing nginx-proxy-manager so it resolves the frontend's NEW IP"
# Recreating bs-afl-frontend gives it a new Docker IP; nginx-proxy-manager
# caches the old DNS result per worker (the same class of bug as the Jun 2026
# betterstats admin outage — "could not be resolved (2: Server failure)").
# Uses `docker compose` throughout (never bare `docker exec/restart`) to stay
# inside the pinned COMPOSE_PROJECT_NAME project, discovering the proxy's
# SERVICE name rather than hardcoding a container name.
NPM_SVC="$(docker compose ps --services 2>/dev/null | grep -iE 'proxy|npm|manager' | head -1)"
health() { for i in 1 2 3; do curl -s -o /dev/null -w '%{http_code} ' "https://betterat.football/afl/" || printf '000 '; done; }
if [ -n "$NPM_SVC" ]; then
  docker compose exec -T "$NPM_SVC" nginx -s reload 2>/dev/null || true
  sleep 3
  codes="$(health)"; echo "    after reload: $codes"
  case "$codes" in
    *50[0-9]*|*000*)
      echo "    still failing — restarting $NPM_SVC to flush its DNS resolver (brief blip, affects every proxied app)"
      docker compose restart "$NPM_SVC" >/dev/null; sleep 4
      echo "    after restart: $(health)" ;;
    *) echo "    frontend reachable via the proxy ✓" ;;
  esac
else
  echo "    no proxy service found in this compose project — skipping proxy refresh"
fi

echo "==> [5/5] Backend API health check (end-to-end through the proxy)"
# [4/5] only proves the frontend serves static files, which it does even if
# the API container failed to boot — hit a real API endpoint and confirm the
# AFL backend (not cricket's, not another app) is the one answering. This also
# catches the /afl/api proxy pointing at the wrong upstream.
api_ok=""
for i in $(seq 1 15); do
  body="$(curl -s -m 10 https://betterat.football/afl/api/openapi.json || true)"
  case "$body" in *"BetterStats AFL"*) api_ok=1; break ;; esac
  echo "    attempt $i/15: API not healthy yet, waiting…"; sleep 5
done
if [ -n "$api_ok" ]; then
  echo "    backend API healthy ✓ — /afl/api is answered by BetterStats AFL"
else
  echo ""
  echo "    ✗✗ BACKEND API IS DOWN — login and club data will fail."
  echo "       (The frontend still serves static files, which is why [4/5] looked green.)"
  echo "    --- bs-afl-backend container state ---"
  docker compose ps bs-afl-backend || true
  echo "    --- bs-afl-backend last 50 log lines ---"
  docker compose logs --tail=50 bs-afl-backend 2>&1 | tail -50 || true
  echo ""
  echo "    app.afl_main refuses to boot unless SPORT=afl is set on the container —"
  echo "    check for 'Refusing to boot' in the log above if it crash-looped instantly."
  echo "    Fix forward and redeploy, or revert the last change on main to restore service."
  exit 1
fi

echo "==> Status:"
docker compose ps bs-afl-backend bs-afl-frontend

cat <<'NOTE'

Done — https://betterat.football/afl

Reminders:
  * NEVER add --remove-orphans (it would delete klubpro-mongo / restreamer — other apps).
    The orphan warning is silenced via COMPOSE_IGNORE_ORPHANS, which leaves them untouched.
  * NEVER recreate bs-afl-database. Its data lives in the bs_afl_pgdata volume; leave it running.
  * bs-football-landing (the umbrella betterat.football choose-your-code page) is deliberately
    NOT touched by this script — it isn't part of the AFL silo. Redeploy it separately if
    football-landing/ itself changed.
NOTE
