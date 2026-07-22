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
# Progress reporting: every run is visible on Super Admin -> Backups while
# it's in progress. pg_restore, like pg_dump, only tells us "now restoring
# table X" (--verbose), not row-level progress within a table, so `check`/
# `apply` report table-level progress for a curated list of entities, with
# each table's row count filled in from the SCRATCH database once the whole
# restore finishes (there's no reliable per-table "done" signal to hook
# during the stream, only "started"). `restore-club` is different — it
# delegates to app/services/club_restore.py, which writes rows itself in
# Python and reports true row-level progress ("Processing player 176 of
# 876") as it goes.
#
set -euo pipefail

cd /srv/docker
export COMPOSE_PROJECT_NAME=bltbox_docker_app
export COMPOSE_IGNORE_ORPHANS=1

BACKUP_ROOT="${BACKUP_ROOT:-/mnt/media/bettercricket/backup}"
DB_SERVICE="${DB_SERVICE:-betterstats-db}"
BACKEND_SERVICE="${BACKEND_SERVICE:-betterstats-backend}"
POSTGRES_DB="${POSTGRES_DB:-betterstats}"
POSTGRES_USER="${POSTGRES_USER:-cricket}"
# The scratch container is a brand-new, disposable Postgres instance — its
# password has no relationship to production's and never needs to match it,
# so a fresh random one is generated per run rather than requiring the real
# DB password in this script's environment at all.
SCRATCH_PASSWORD="$(openssl rand -hex 20)"
SCRATCH_CONTAINER="betterstats-restore-scratch"
# Matches the shared internal network betterstats-backend/-db are already on
# (see the central docker-compose.yaml) — override if that's ever renamed.
NETWORK_NAME="${NETWORK_NAME:-docker-shared-net}"
# Real volume name — confirm with `docker volume ls | grep uploads` on the
# box (must match backup.sh's UPLOADS_VOLUME) and override if it differs.
UPLOADS_VOLUME="${UPLOADS_VOLUME:-${COMPOSE_PROJECT_NAME}_betterstats_uploads}"

ENTITY_TABLES=(organisations seasons grades players games batting_innings bowling_spells fielding_stats bowler_wickets game_appearances fall_of_wickets partnerships users)
TOTAL_ENTITIES=${#ENTITY_TABLES[@]}

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

progress() {
  # progress <stage> <current> <total> <message>
  docker compose exec -T "$BACKEND_SERVICE" python -m app.scripts.backup_task update-progress "$TASK_ID" \
    --stage "$1" --current "$2" --total "$3" --message "$4" || true
}

# Reads pg_restore --verbose's stderr, advancing the "current entity" as each
# tracked table's restore starts (no reliable per-table "done" signal in the
# stream — final per-entity counts are filled in afterwards, see
# fill_in_restore_counts). Echoes every line through unchanged.
track_restore_progress() {
  local idx=0
  local restore_line_pat='for table "public\.([a-zA-Z0-9_]+)"'
  while IFS= read -r line; do
    echo "$line"
    if [[ "$line" =~ $restore_line_pat ]]; then
      local table="${BASH_REMATCH[1]}"
      local is_tracked=0
      for t in "${ENTITY_TABLES[@]}"; do [ "$t" = "$table" ] && is_tracked=1 && break; done
      [ "$is_tracked" = "0" ] && continue
      idx=$((idx + 1))
      progress "$table" "$idx" "$TOTAL_ENTITIES" "Restoring $table ($idx/$TOTAL_ENTITIES)..."
    fi
  done
}

# Queries the given container (scratch, or the live DB service) for each
# tracked entity's row count and stamps it into progress.stage_results —
# called once the restore itself has finished, since pg_restore's stream
# doesn't tell us when a table is DONE, only when it starts.
fill_in_restore_counts() {
  local container="$1" user="$2" db="$3"
  for table in "${ENTITY_TABLES[@]}"; do
    local count
    count=$(docker exec "$container" psql -U "$user" -d "$db" -tAc "SELECT COUNT(*) FROM $table" 2>/dev/null || echo 0)
    docker compose exec -T "$BACKEND_SERVICE" python -m app.scripts.backup_task mark-stage-done "$TASK_ID" \
      --stage "$table" --count "${count:-0}" || true
  done
}

# Spins up a fresh scratch Postgres, pg_restores the given bundle into it,
# and leaves it running (caller is responsible for `docker rm -f` when done).
# Used by `check`, `apply`, and `restore-club` alike — one restore-to-scratch
# implementation, not three.
restore_to_scratch() {
  log "Starting scratch Postgres..."
  docker rm -f "$SCRATCH_CONTAINER" >/dev/null 2>&1 || true
  docker run -d --name "$SCRATCH_CONTAINER" --network "$NETWORK_NAME" \
    -e POSTGRES_DB="$POSTGRES_DB" -e POSTGRES_USER="$POSTGRES_USER" -e POSTGRES_PASSWORD="$SCRATCH_PASSWORD" \
    postgres:15 >/dev/null
  sleep 5
  for i in $(seq 1 30); do
    docker exec "$SCRATCH_CONTAINER" pg_isready -U "$POSTGRES_USER" >/dev/null 2>&1 && break
    sleep 2
  done

  log "Restoring dump into scratch..."
  age -d -i /root/.age/backup-key.txt "$BUNDLE_DIR/db.dump.age" \
    | docker exec -i "$SCRATCH_CONTAINER" pg_restore --verbose -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --clean --if-exists \
      2> >(track_restore_progress >&2)

  log "Bringing scratch schema up to date (alembic upgrade head)..."
  docker run --rm --network "$NETWORK_NAME" \
    -e SYNC_DATABASE_URL="postgresql://${POSTGRES_USER}:${SCRATCH_PASSWORD}@${SCRATCH_CONTAINER}:5432/${POSTGRES_DB}" \
    -e DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER}:${SCRATCH_PASSWORD}@${SCRATCH_CONTAINER}:5432/${POSTGRES_DB}" \
    --entrypoint sh "$(docker compose images -q "$BACKEND_SERVICE")" \
    -c "cd /app && alembic upgrade head" || log "WARNING: could not run alembic on scratch (bundle may already be current — continuing)"

  fill_in_restore_counts "$SCRATCH_CONTAINER" "$POSTGRES_USER" "$POSTGRES_DB"

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

  SCRATCH_DSN="postgresql+asyncpg://${POSTGRES_USER}:${SCRATCH_PASSWORD}@${SCRATCH_CONTAINER}:5432/${POSTGRES_DB}"

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
  log "Club restore complete. Snapshot of the pre-restore data is under /mnt/media/bettercricket/backup/club-restores/ — keep it until you're sure you don't need to roll back."
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
progress "live-restore" 0 "$TOTAL_ENTITIES" "Restoring into the live database..."
age -d -i /root/.age/backup-key.txt "$BUNDLE_DIR/db.dump.age" \
  | docker compose exec -T "$DB_SERVICE" pg_restore --verbose -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --clean --if-exists \
    2> >(track_restore_progress >&2)

log "Restoring uploads volume..."
age -d -i /root/.age/backup-key.txt "$BUNDLE_DIR/uploads.tar.zst.age" | zstd -d \
  | docker run --rm -i -v "${UPLOADS_VOLUME}:/to" alpine sh -c 'rm -rf /to/* && tar -C /to -x'

log "Starting app services..."
docker compose up -d --no-deps betterstats-backend betterstats-frontend

# Backend needs to be back up for `docker compose exec` progress calls
# above (which happen while it's stopped — best-effort, already `|| true`);
# now that it's running again, fill in the final per-entity counts from the
# live DB.
for i in $(seq 1 15); do
  docker compose exec -T "$BACKEND_SERVICE" true >/dev/null 2>&1 && break
  sleep 2
done
fill_in_restore_counts "$DB_SERVICE" "$POSTGRES_USER" "$POSTGRES_DB"

drop_scratch
finish_task "$TASK_ID" completed
log "Restore complete."
