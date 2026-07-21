#!/usr/bin/env bash
#
# BetterStats restore — bltbox host only.
#
# Restores one backup bundle (see backup.sh) into a SCRATCH Postgres
# container first — never straight into the live betterstats-db — so the
# bundle and the current schema are verified before anything real is
# touched.
#
# Usage:
#   ops/backup/restore.sh list                          # show available bundles
#   ops/backup/restore.sh check <bundle-timestamp>       # restore to scratch + verify only
#   ops/backup/restore.sh apply <bundle-timestamp>       # check, then (after confirmation) cut over the WHOLE platform
#   ops/backup/restore.sh restore-club <bundle-timestamp> <org-id> [--apply]
#                                                         # restore ONE club's data only; no downtime,
#                                                         # never touches other clubs. Without --apply,
#                                                         # reports what would change and writes nothing.
#
# restore-club is READ-MOSTLY safe by default (dry-run) and, even with
# --apply, only ever touches the target club's own rows — see
# app/services/club_restore.py for exactly how a row is attributed to one
# club (this matters because a game can be shared between two synced clubs).
# It snapshots the club's current live data before writing, so it's itself
# undoable — see "rollback" below.
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
NETWORK_NAME="${NETWORK_NAME:-${COMPOSE_PROJECT_NAME}_default}"

log() { echo "[restore $(date -u +%FT%TZ)] $*"; }

start_restore_task() {
  docker compose exec -T "$BACKEND_SERVICE" python -m app.scripts.backup_task start-task \
    --type "$1" --triggered-by manual ${2:+--scope-org-id "$2"} | tr -d '\r'
}

finish_task() {
  local task_id="$1" status="$2" error="${3:-}"
  local args=(python -m app.scripts.backup_task finish-task "$task_id" --status "$status" --bundle-path "$BUNDLE_DIR")
  [ -n "$error" ] && args+=(--error "$error")
  docker compose exec -T "$BACKEND_SERVICE" "${args[@]}"
}

# Spins up a fresh scratch Postgres, pg_restores the given bundle into it,
# and leaves it running (caller is responsible for `docker rm -f` when done).
# Used by `check`, `apply`, and `restore-club` alike — one restore-to-scratch
# implementation, not three.
restore_to_scratch() {
  log "Starting scratch Postgres..."
  docker rm -f "$SCRATCH_CONTAINER" >/dev/null 2>&1 || true
  docker run -d --name "$SCRATCH_CONTAINER" --network "$NETWORK_NAME" \
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

  log "Bringing scratch schema up to date (alembic upgrade head)..."
  docker run --rm --network "$NETWORK_NAME" \
    -e SYNC_DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${SCRATCH_CONTAINER}:5432/${POSTGRES_DB}" \
    -e DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${SCRATCH_CONTAINER}:5432/${POSTGRES_DB}" \
    --entrypoint sh "$(docker compose images -q "$BACKEND_SERVICE")" \
    -c "cd /app && alembic upgrade head" || log "WARNING: could not run alembic on scratch (bundle may already be current — continuing)"

  ORG_COUNT=$(docker exec "$SCRATCH_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT COUNT(*) FROM organisations")
  log "Scratch DB ready: $ORG_COUNT organisations, bundle alembic head: $(cat "$BUNDLE_DIR/alembic_version.txt" 2>/dev/null || echo unknown)"
}

drop_scratch() {
  docker rm -f "$SCRATCH_CONTAINER" >/dev/null 2>&1 || true
}

cmd="${1:-}"
case "$cmd" in
  list)
    ls -1 "$BACKUP_ROOT" 2>/dev/null | sort -r
    exit 0
    ;;
  check|apply|restore-club) ;;
  rollback-club)
    SNAPSHOT="${2:-}"
    [ -z "$SNAPSHOT" ] && { echo "Usage: $0 rollback-club <snapshot-json-path>" >&2; exit 1; }
    docker compose exec -T "$BACKEND_SERVICE" python -m app.scripts.restore_club --rollback "$SNAPSHOT"
    exit 0
    ;;
  *)
    echo "Usage: $0 {list|check|apply|restore-club|rollback-club} [args]" >&2
    exit 1
    ;;
esac

STAMP="${2:-}"
[ -z "$STAMP" ] && { echo "Bundle timestamp required, e.g. 2026-07-21T03-00-00Z (see: $0 list)" >&2; exit 1; }
BUNDLE_DIR="$BACKUP_ROOT/$STAMP"
[ -d "$BUNDLE_DIR" ] || { echo "No such bundle: $BUNDLE_DIR" >&2; exit 1; }

log "Verifying checksums..."
( cd "$BUNDLE_DIR" && sha256sum -c checksums.sha256 ) || { echo "Checksum mismatch — refusing to restore a corrupted bundle." >&2; exit 1; }

# ─── restore-club: no downtime, one club only ──────────────────────────────
if [ "$cmd" = "restore-club" ]; then
  ORG_ID="${3:-}"
  [ -z "$ORG_ID" ] && { echo "Usage: $0 restore-club <bundle-timestamp> <org-id> [--apply]" >&2; exit 1; }
  APPLY_FLAG=""
  [ "${4:-}" = "--apply" ] && APPLY_FLAG="--apply"

  TASK_ID=$(start_restore_task restore_club "$ORG_ID")
  log "Started club-restore task $TASK_ID (org $ORG_ID, apply=${APPLY_FLAG:+yes}${APPLY_FLAG:-no})"
  trap 'finish_task "$TASK_ID" failed "restore-club aborted (see host log)" || true; drop_scratch' ERR

  restore_to_scratch

  SCRATCH_DSN="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${SCRATCH_CONTAINER}:5432/${POSTGRES_DB}"

  if [ -z "$APPLY_FLAG" ]; then
    log "DRY RUN (pass --apply to actually restore this club's data) — report only:"
    docker compose exec -T "$BACKEND_SERVICE" python -m app.scripts.restore_club "$ORG_ID" \
      --scratch-dsn "$SCRATCH_DSN" --task-id "$TASK_ID"
    finish_task "$TASK_ID" completed
    drop_scratch
    exit 0
  fi

  echo
  echo "About to restore club $ORG_ID's data from bundle $STAMP into the LIVE database."
  echo "This does NOT stop the app and does NOT touch any other club's data."
  echo "The club's current data is snapshotted first, so this can be undone (see: $0 rollback-club <snapshot path>)."
  read -r -p "Type the org id to confirm: " confirm
  if [ "$confirm" != "$ORG_ID" ]; then
    echo "Confirmation did not match — aborting. Nothing was changed." >&2
    finish_task "$TASK_ID" failed "operator did not confirm"
    drop_scratch
    exit 1
  fi

  docker compose exec -T "$BACKEND_SERVICE" python -m app.scripts.restore_club "$ORG_ID" \
    --scratch-dsn "$SCRATCH_DSN" --apply --task-id "$TASK_ID"

  drop_scratch
  finish_task "$TASK_ID" completed
  log "Club restore complete. Snapshot of the pre-restore data is under /srv/backups/betterstats/club-restores/ — keep it until you're sure you don't need to roll back."
  exit 0
fi

# ─── check / apply: whole-platform restore ─────────────────────────────────
TASK_ID=$(start_restore_task restore_full)
log "Started restore task $TASK_ID"
trap 'finish_task "$TASK_ID" failed "restore.sh aborted (see host log)" || true' ERR

restore_to_scratch

if [ "$cmd" = "check" ]; then
  log "check-only run — scratch container '$SCRATCH_CONTAINER' left running for manual inspection. Remove it with: docker rm -f $SCRATCH_CONTAINER"
  finish_task "$TASK_ID" completed
  exit 0
fi

echo
echo "About to REPLACE the live betterstats-db data with bundle $STAMP."
echo "This requires briefly stopping betterstats-backend / betterstats-frontend."
read -r -p "Type the bundle timestamp to confirm: " confirm
if [ "$confirm" != "$STAMP" ]; then
  echo "Confirmation did not match — aborting. Nothing was changed." >&2
  finish_task "$TASK_ID" failed "operator did not confirm"
  drop_scratch
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

drop_scratch
finish_task "$TASK_ID" completed
log "Restore complete."
