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

echo "==> [1/3] Pulling latest main into /srv/docker/betterstats"
git -C /srv/docker/betterstats pull origin main

echo "==> [2/3] Rebuilding betterstats images (no cache)"
docker compose build --no-cache betterstats-backend betterstats-frontend

echo "==> [3/3] Recreating betterstats only (db + other services untouched)"
docker compose up -d --no-deps --force-recreate betterstats-backend betterstats-frontend

echo "==> Status:"
docker ps --filter name=betterstats --format 'table {{.Names}}\t{{.Status}}'

cat <<'NOTE'

Done — https://betterstats.cricket

Reminders:
  * NEVER add --remove-orphans (it would delete klubpro-mongo / restreamer — other apps).
  * NEVER recreate betterstats-db. Your data lives in the bltbox_docker_app_betterstats_pgdata
    volume; leave the db running.
  * Ignore "POSTGRES_PASSWORD / LANGFLOW_* not set" warnings — those vars belong to other
    services in the shared compose file, not betterstats.
NOTE
