#!/usr/bin/env bash
#
# BetterStats daily backup — bltbox host only.
#
# Takes a live, no-downtime backup of the Postgres database (pg_dump -Fc,
# MVCC-consistent snapshot — never locks writers) and the `uploads` Docker
# volume, encrypts both, writes a dated bundle under BACKUP_ROOT, prunes
# bundles older than the configured retention window, and logs the run into
# the `backup_tasks` table (via app/scripts/backup_task.py in the backend
# container) so it shows up on the Super Admin Backups page.
#
# Follows the same compose conventions as deploy.sh: run from /srv/docker,
# COMPOSE_PROJECT_NAME=bltbox_docker_app set, only `docker compose ...`
# (never bare `docker exec/restart`), betterstats-db is READ from, never
# recreated or otherwise touched.
#
# Intended to run frequently (e.g. every 15 minutes) via the accompanying
# systemd timer, NOT once a day at a fixed OnCalendar time — the schedule
# hour/minute is a super-admin-editable app setting (General Settings ->
# Backups), not a value baked into a host-level timer file. Each tick:
#   1. asks the backend for the configured hour/minute/retention (a plain DB
#      read — cheap)
#   2. does nothing unless the current wall-clock hour/minute matches AND no
#      backup has completed yet today (idempotent — a slow run or a timer
#      catch-up after downtime can't produce two backups in one day)
#
# Manual run: BACKUP_FORCE=1 ./backup.sh  (ignores the schedule check, still
# respects "already ran today" — pass BACKUP_FORCE=2 to also ignore that).
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
UPLOADS_VOLUME="${UPLOADS_VOLUME:-${COMPOSE_PROJECT_NAME}_uploads}"
# age public key used to encrypt every bundle (age -R recipients file, or a
# single -r KEY). Generate with `age-keygen`; keep the PRIVATE key offline —
# it's only needed to restore, never to back up.
AGE_RECIPIENT="${AGE_RECIPIENT:-}"

log() { echo "[backup $(date -u +%FT%TZ)] $*"; }
fail() { log "ERROR: $*"; [ -n "${TASK_ID:-}" ] && exec_backend python -m app.scripts.backup_task finish-task "$TASK_ID" --status failed --error "$*" || true; exit 1; }

exec_backend() { docker compose exec -T "$BACKEND_SERVICE" "$@"; }

if [ -z "$AGE_RECIPIENT" ]; then
  fail "AGE_RECIPIENT is not set (see ops/backup/README.md — generate a keypair with age-keygen and set this to the public key)"
fi

# --- Schedule check (skipped entirely with BACKUP_FORCE) ----------------------
read -r SCHED_HOUR SCHED_MINUTE RETENTION_DAYS < <(exec_backend python -m app.scripts.backup_task get-schedule)

if [ "${BACKUP_FORCE:-0}" = "0" ]; then
  now_hour=$(date -u +%H | sed 's/^0*//')
  now_minute=$(date -u +%M | sed 's/^0*//')
  now_hour=${now_hour:-0}; now_minute=${now_minute:-0}
  # Match within the same hour, minute window of the timer's own tick interval
  # (assumes a >=15min-interval timer; a coarser one just backs up a bit later
  # in the hour, never skips the day).
  if [ "$now_hour" != "$SCHED_HOUR" ]; then
    log "Not the scheduled hour ($SCHED_HOUR:$(printf '%02d' "$SCHED_MINUTE") UTC configured, now ${now_hour}:$(printf '%02d' "$now_minute") UTC) — skipping."
    exit 0
  fi
  already=$(exec_backend python -m app.scripts.backup_task has-run-today)
  if [ "$(echo "$already" | tr -d '\r')" = "1" ]; then
    log "Already have a completed backup today — skipping."
    exit 0
  fi
elif [ "${BACKUP_FORCE}" = "1" ]; then
  already=$(exec_backend python -m app.scripts.backup_task has-run-today)
  if [ "$(echo "$already" | tr -d '\r')" = "1" ]; then
    log "BACKUP_FORCE=1 still respects 'already ran today' — use BACKUP_FORCE=2 to override."
    exit 0
  fi
fi

TRIGGERED_BY="${BACKUP_TRIGGERED_BY:-scheduled}"
STAMP=$(date -u +%Y-%m-%dT%H-%M-%SZ)
BUNDLE_DIR="$BACKUP_ROOT/$STAMP"
mkdir -p "$BUNDLE_DIR"

TASK_ID=$(exec_backend python -m app.scripts.backup_task start-task --type backup --triggered-by "$TRIGGERED_BY" | tr -d '\r')
log "Started backup task $TASK_ID -> $BUNDLE_DIR"

# --- Postgres: MVCC-consistent dump, no lock, no downtime ---------------------
log "Dumping database..."
docker compose exec -T "$DB_SERVICE" pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB" \
  | age -r "$AGE_RECIPIENT" -o "$BUNDLE_DIR/db.dump.age" \
  || fail "pg_dump failed"

# --- uploads volume ------------------------------------------------------------
log "Archiving uploads volume..."
docker run --rm -v "${UPLOADS_VOLUME}:/from:ro" -v "$BUNDLE_DIR:/to" alpine \
  tar -C /from -c . \
  | zstd -q \
  | age -r "$AGE_RECIPIENT" -o "$BUNDLE_DIR/uploads.tar.zst.age" \
  || fail "uploads archive failed"

# --- migration head, for a restore's compatibility check -----------------------
docker compose exec -T "$BACKEND_SERVICE" alembic current 2>/dev/null | tee "$BUNDLE_DIR/alembic_version.txt" >/dev/null || true

DB_SIZE_BYTES=$(stat -c%s "$BUNDLE_DIR/db.dump.age" 2>/dev/null || stat -f%z "$BUNDLE_DIR/db.dump.age")
UPLOADS_SIZE_BYTES=$(stat -c%s "$BUNDLE_DIR/uploads.tar.zst.age" 2>/dev/null || stat -f%z "$BUNDLE_DIR/uploads.tar.zst.age")

# --- manifest + checksums -------------------------------------------------------
( cd "$BUNDLE_DIR" && sha256sum ./*.age > checksums.sha256 )
cat > "$BUNDLE_DIR/manifest.json" <<EOF
{
  "bundle_timestamp": "$STAMP",
  "db_dump_bytes": $DB_SIZE_BYTES,
  "uploads_archive_bytes": $UPLOADS_SIZE_BYTES,
  "encrypted": true,
  "triggered_by": "$TRIGGERED_BY"
}
EOF

log "Backup complete: db=$(numfmt --to=iec "$DB_SIZE_BYTES" 2>/dev/null || echo "$DB_SIZE_BYTES bytes"), uploads=$(numfmt --to=iec "$UPLOADS_SIZE_BYTES" 2>/dev/null || echo "$UPLOADS_SIZE_BYTES bytes")"

exec_backend python -m app.scripts.backup_task finish-task "$TASK_ID" --status completed \
  --bundle-path "$BUNDLE_DIR" --uploads-size-bytes "$UPLOADS_SIZE_BYTES"

# --- retention: prune bundles older than RETENTION_DAYS ------------------------
log "Pruning backups older than $RETENTION_DAYS days..."
find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -mtime "+$RETENTION_DAYS" -print -exec rm -rf {} \;

log "Done."
