#!/usr/bin/env bash
#
# BetterStats full restore — bltbox host only.
#
# Restores one backup bundle (see backup.sh) into a SCRATCH Postgres
# container first — never straight into the live betterstats-db — so the
# bundle and the current schema are verified before anything real is
# touched. Only the final swap step needs the app briefly stopped; building
# and checking the scratch restore does not.
#
# Usage:
#   ops/backup/restore.sh list                     # show available bundles
#   ops/backup/restore.sh check <bundle-timestamp>  # restore to scratch + verify only
#   ops/backup/restore.sh apply <bundle-timestamp>  # check, then (after confirmation) cut over
#
# Per-club restore is NOT done by this script — see docs/backup-system.md for
# why a shared-schema per-tenant restore needs its own tool (walking the FK
# graph from organisations.id, snapshot-then-upsert) rather than a plain
# pg_restore, and is a later build phase.
#
set -euo pipefail

cd /srv/docker
export COMPOSE_PROJECT_NAME=bltbox_docker_app
export COMPOSE_IGNORE_ORPHANS=1

BACKUP_ROOT="${BACKUP_ROOT:-/srv/backups/betterstats}"
DB_SERVICE="${DB_SERVICE:-betterstats-db}"
BACKEND_SERVICE="${BACKEND_SERVICE:-betterstats-backend}"
POSTGRES_DB="${POSTGRES_DB:-betterstats}"
POSTGRES_USER="${POSTGRES_USER:-cricket}"
POSTGRES_PASSWORD="${DB_PASSWORD:?DB_PASSWORD must be set in the environment (same value as /srv/docker/.env)}"
SCRATCH_CONTAINER="betterstats-restore-scratch"

log() { echo "[restore $(date -u +%FT%TZ)] $*"; }

cmd="${1:-}"
case "$cmd" in
  list)
    ls -1 "$BACKUP_ROOT" 2>/dev/null | sort -r
    exit 0
    ;;
  check|apply) ;;
  *)
    echo "Usage: $0 {list|check|apply} [bundle-timestamp]" >&2
    exit 1
    ;;
esac

STAMP="${2:-}"
[ -z "$STAMP" ] && { echo "Bundle timestamp required, e.g. 2026-07-21T03-00-00Z (see: $0 list)" >&2; exit 1; }
BUNDLE_DIR="$BACKUP_ROOT/$STAMP"
[ -d "$BUNDLE_DIR" ] || { echo "No such bundle: $BUNDLE_DIR" >&2; exit 1; }

log "Verifying checksums..."
( cd "$BUNDLE_DIR" && sha256sum -c checksums.sha256 ) || { echo "Checksum mismatch — refusing to restore a corrupted bundle." >&2; exit 1; }

TASK_ID=$(docker compose exec -T "$BACKEND_SERVICE" python -m app.scripts.backup_task start-task --type restore_full --triggered-by manual | tr -d '\r')
log "Started restore task $TASK_ID"
finish() {
  local args=(python -m app.scripts.backup_task finish-task "$TASK_ID" --status "$1" --bundle-path "$BUNDLE_DIR")
  [ -n "${2:-}" ] && args+=(--error "$2")
  docker compose exec -T "$BACKEND_SERVICE" "${args[@]}"
}
trap 'finish failed "restore.sh aborted (see host log)" || true' ERR

log "Starting scratch Postgres..."
docker rm -f "$SCRATCH_CONTAINER" >/dev/null 2>&1 || true
docker run -d --name "$SCRATCH_CONTAINER" --network "${COMPOSE_PROJECT_NAME}_default" \
  -e POSTGRES_DB="$POSTGRES_DB" -e POSTGRES_USER="$POSTGRES_USER" -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
  postgres:15 >/dev/null
sleep 5
for i in $(seq 1 30); do
  docker exec "$SCRATCH_CONTAINER" pg_isready -U "$POSTGRES_USER" >/dev/null 2>&1 && break
  sleep 2
done

log "Restoring dump into scratch..."
age -d -i /root/.age/backup-key.txt "$BUNDLE_DIR/db.dump.age" \
  | docker exec -i "$SCRATCH_CONTAINER" pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --clean --if-exists

log "Sanity-checking restored data..."
ORG_COUNT=$(docker exec "$SCRATCH_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT COUNT(*) FROM organisations")
log "Scratch DB has $ORG_COUNT organisations, alembic head: $(cat "$BUNDLE_DIR/alembic_version.txt" 2>/dev/null || echo unknown)"

if [ "$cmd" = "check" ]; then
  log "check-only run — scratch container '$SCRATCH_CONTAINER' left running for manual inspection. Remove it with: docker rm -f $SCRATCH_CONTAINER"
  finish completed
  exit 0
fi

echo
echo "About to REPLACE the live betterstats-db data with bundle $STAMP ($ORG_COUNT organisations)."
echo "This requires briefly stopping betterstats-backend / betterstats-frontend."
read -r -p "Type the bundle timestamp to confirm: " confirm
if [ "$confirm" != "$STAMP" ]; then
  echo "Confirmation did not match — aborting. Nothing was changed." >&2
  finish failed "operator did not confirm"
  docker rm -f "$SCRATCH_CONTAINER" >/dev/null 2>&1 || true
  exit 1
fi

log "Stopping app services..."
docker compose stop betterstats-backend betterstats-frontend

log "Restoring into live betterstats-db..."
age -d -i /root/.age/backup-key.txt "$BUNDLE_DIR/db.dump.age" \
  | docker compose exec -T "$DB_SERVICE" pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --clean --if-exists

log "Restoring uploads volume..."
age -d -i /root/.age/backup-key.txt "$BUNDLE_DIR/uploads.tar.zst.age" | zstd -d \
  | docker run --rm -i -v "${COMPOSE_PROJECT_NAME}_uploads:/to" alpine sh -c 'rm -rf /to/* && tar -C /to -x'

log "Starting app services..."
docker compose up -d --no-deps betterstats-backend betterstats-frontend

docker rm -f "$SCRATCH_CONTAINER" >/dev/null 2>&1 || true
finish completed
log "Restore complete."
