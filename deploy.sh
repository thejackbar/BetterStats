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
# Safe by construction: only betterstats-backend/-frontend, and (if it's been set
# up — see docs/backup-system.md) the optional betterstats-backup-agent sidecar,
# are rebuilt/recreated. The database (betterstats-db) and the other ~24 apps on
# the box are never touched.
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

echo "==> [1/7] Pulling latest main into /srv/docker/betterstats"
git -C /srv/docker/betterstats pull origin main

# betterstats-backup-agent (see docs/backup-system.md) is an OPTIONAL sidecar —
# not every deploy of this box will have added it to the central compose file
# yet. Detect whether it's actually defined there before trying to build/recreate
# it, so this script doesn't break for anyone who hasn't set it up (it would
# otherwise fail with "no such service").
AGENT_SVC=""
if docker compose config --services 2>/dev/null | grep -qx betterstats-backup-agent; then
  AGENT_SVC="betterstats-backup-agent"
fi

echo "==> [2/7] Rebuilding betterstats images (no cache)"
docker compose build --no-cache betterstats-backend betterstats-frontend ${AGENT_SVC:+$AGENT_SVC}

echo "==> [3/7] Recreating betterstats only (db + other services untouched)"
# Why rm+up instead of `up --force-recreate`:
# The central file pins fixed container_names (betterstats-frontend / -backend /
# betterstats-backup-agent). With a fixed name, `--force-recreate` does a fragile
# rename dance — it renames the old container to <shortid>_betterstats-frontend,
# creates the new one, then removes the temp. If a past run left that temp
# container behind (it keeps the compose service label AND still holds the
# /betterstats-frontend name), the next --force-recreate dies with:
#   "Error when allocating new name: Conflict. The container name
#    /betterstats-frontend is already in use by <shortid>_betterstats-frontend"
# — which is exactly the failure that forces a second deploy. Explicitly removing
# the services first frees the names (rm -sf also clears any leftover <shortid>_
# orphans of these services, since they carry the same service label), so `up`
# always creates clean containers on the FIRST run. Only these named services are
# touched — db and the other ~24 apps are never affected. The agent has no
# published port and isn't behind nginx-proxy-manager, so recreating it never
# needs the DNS-refresh dance step [4/7] does for the frontend.
docker compose rm -sf betterstats-backend betterstats-frontend ${AGENT_SVC:+$AGENT_SVC} || true
docker compose up -d --no-deps betterstats-backend betterstats-frontend ${AGENT_SVC:+$AGENT_SVC}

echo "==> [4/7] Refreshing nginx-proxy-manager so it resolves the frontend's NEW IP"
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
health() { for i in 1 2 3; do curl -s -o /dev/null -w '%{http_code} ' "https://betterat.cricket/" || printf '000 '; done; }
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

echo "==> [5/7] Backend API health check (end-to-end through the proxy)"
# [4/7] only checks the frontend, which serves its static files even when the API
# is dead — so a backend that fails to boot (e.g. 'alembic upgrade head' errors, so
# uvicorn never starts) sails through as a green deploy while login and every club
# page hang on "Loading club data…". Hit a real API endpoint and confirm BetterStats
# is the one answering (this also catches the crossed-/api-proxy bug from the Jun
# 2026 post-mortem, where /api was served by a different app). On failure, print the
# backend's own state and logs so the cause is right here in the deploy output.
api_ok=""
# The backend's lifespan runs a batch of idempotent DDL mirrors + seeds before
# uvicorn reports ready, and that startup time grows with the data, so give it a
# generous window (≈15×5s ≈ 75s) before declaring it down — a slow-but-healthy
# boot was being false-flagged as DOWN at the old 6×4s.
for i in $(seq 1 15); do
  body="$(curl -s -m 10 https://betterat.cricket/api/openapi.json || true)"
  case "$body" in *BetterStats*) api_ok=1; break ;; esac
  echo "    attempt $i/15: API not healthy yet, waiting…"; sleep 5
done
if [ -n "$api_ok" ]; then
  echo "    backend API healthy ✓ — /api is answered by BetterStats"
else
  echo ""
  echo "    ✗✗ BACKEND API IS DOWN — login and club data will fail."
  echo "       (The frontend still serves static files, which is why [4/7] looked green.)"
  echo "    --- betterstats-backend container state ---"
  docker compose ps betterstats-backend || true
  echo "    --- betterstats-backend last 50 log lines ---"
  docker compose logs --tail=50 betterstats-backend 2>&1 | tail -50 || true
  echo ""
  echo "    The container runs 'alembic upgrade head && uvicorn …'. Two common causes:"
  echo "      1) a failed migration — uvicorn never starts and the container crash-loops"
  echo "         (the log above ends BEFORE 'Started server process')."
  echo "      2) a SLOW-but-healthy startup that just overran this window — the log shows"
  echo "         'Started server process' / 'Waiting for application startup' but not yet"
  echo "         'Application startup complete'. Re-check in a moment:"
  echo "         docker compose logs --tail=10 betterstats-backend   # look for 'Application startup complete.'"
  echo "    Fix forward and redeploy, or revert the last change on main to restore service."
  exit 1
fi

echo "==> [6/7] Backup-agent health check (optional — never blocks the deploy)"
# Unlike [5/7], a bad agent doesn't take down login or club data — it only
# means the Backups page's "Run backup now" button 502s. So this WARNS, it
# never exits non-zero. Skipped entirely if the service isn't defined yet.
if [ -n "$AGENT_SVC" ]; then
  code="$(docker compose exec -T "$AGENT_SVC" curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/health 2>/dev/null || echo 000)"
  if [ "$code" = "200" ]; then
    echo "    backup-agent healthy ✓"
  else
    echo "    ⚠ backup-agent did not respond healthy (got '$code') — 'Run backup now' will 502 until this is fixed."
    echo "    --- $AGENT_SVC container state ---"
    docker compose ps "$AGENT_SVC" || true
    echo "    --- $AGENT_SVC last 30 log lines ---"
    docker compose logs --tail=30 "$AGENT_SVC" 2>&1 | tail -30 || true
  fi
else
  echo "    betterstats-backup-agent isn't defined in the compose file yet — skipping (see docs/backup-system.md)"
fi

echo "==> [7/7] Ensuring the daily backup timer is installed and running"
# The timer/service that fire backup.sh on a schedule (ops/backup/
# betterstats-backup.{service,timer}) live in /etc/systemd/system — entirely
# OUTSIDE docker compose, so nothing above ever touches them. That's exactly
# how a General Settings -> Backups schedule silently never fired anything:
# the unit files existed in the repo but were never actually installed on
# this box. Self-heals every deploy: installs/updates them from the repo
# copy if they differ, and makes sure the timer is enabled + active.
#
# Needs root. Uses non-interactive sudo only (`sudo -n`) — if this user
# can't sudo without a password prompt, this step SKIPS with instructions
# rather than hanging the deploy waiting on stdin that isn't there. Never
# fails the deploy either way — a missing/stale timer means backups don't
# run on schedule, not that the app itself is broken.
UNIT_SRC_DIR="/srv/docker/betterstats/ops/backup"
UNIT_DST_DIR="/etc/systemd/system"
if sudo -n true 2>/dev/null; then
  units_changed=0
  for unit in betterstats-backup.service betterstats-backup.timer; do
    if ! sudo -n cmp -s "$UNIT_SRC_DIR/$unit" "$UNIT_DST_DIR/$unit" 2>/dev/null; then
      sudo -n cp "$UNIT_SRC_DIR/$unit" "$UNIT_DST_DIR/$unit"
      units_changed=1
    fi
  done
  if [ "$units_changed" = "1" ]; then
    sudo -n systemctl daemon-reload
    echo "    installed/updated systemd unit file(s) from the repo"
  fi
  if ! sudo -n systemctl is-enabled --quiet betterstats-backup.timer 2>/dev/null; then
    sudo -n systemctl enable --now betterstats-backup.timer
    echo "    betterstats-backup.timer was not enabled — enabled and started it now ✓"
  elif ! sudo -n systemctl is-active --quiet betterstats-backup.timer 2>/dev/null; then
    sudo -n systemctl start betterstats-backup.timer
    echo "    betterstats-backup.timer was enabled but not running — started it now ✓"
  else
    echo "    betterstats-backup.timer already installed and active ✓"
  fi
else
  echo "    ⚠ can't sudo non-interactively as $(whoami) — skipping. Install once, by hand:"
  echo "      sudo cp $UNIT_SRC_DIR/betterstats-backup.{service,timer} $UNIT_DST_DIR/"
  echo "      sudo systemctl daemon-reload"
  echo "      sudo systemctl enable --now betterstats-backup.timer"
  echo "    (or grant this user passwordless sudo for these specific commands so this step can self-heal)"
fi

echo "==> Status:"
docker compose ps betterstats-backend betterstats-frontend ${AGENT_SVC:+$AGENT_SVC}

cat <<'NOTE'

Done — https://betterat.cricket

Reminders:
  * NEVER add --remove-orphans (it would delete klubpro-mongo / restreamer — other apps).
    The orphan warning is silenced via COMPOSE_IGNORE_ORPHANS, which leaves them untouched.
  * NEVER recreate betterstats-db. Your data lives in the bltbox_docker_app_betterstats_pgdata
    volume; leave the db running.
  * The old "POSTGRES_PASSWORD / LANGFLOW_* not set" warnings are now silenced (those vars
    belong to other services in the shared compose file, not betterstats) — see the exports
    near the top. If a NEW "variable is not set" warning appears, add it to that export block.
NOTE
