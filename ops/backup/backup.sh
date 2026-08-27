#!/usr/bin/env bash
#
# BetterStats daily backup — bltbox host only.
#
# Takes a live, no-downtime backup of the Postgres database (pg_dump -Fc,
# MVCC-consistent snapshot — never locks writers) and the `uploads` Docker
# volume, encrypts both, writes a dated bundle under BACKUP_ROOT, prunes
# bundles older than the configured retention window, and logs the run into
# the `backup_tasks` table (via app/scripts/backup_task.py in the backend
# container) so it shows up on the Super Admin Backups page — including
# LIVE progress while it runs (see "Progress reporting" below).
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
# Progress reporting: pg_dump doesn't expose row-level progress within a
# table — only "now starting table X" (--verbose). So this reports
# TABLE-level progress for a curated list of the tables that actually matter
# to a human watching (players, games, per-innings stats, ...), each shown
# with its known row count (from pg_stat_user_tables — an estimate, cheap,
# not a full COUNT(*) scan) once that table's dump starts. That's the
# honest ceiling for a whole-database pg_dump; true live "row 176 of 876"
# progress only exists for per-club restore (see club_restore.py), which
# writes rows itself in Python and can count as it goes.
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
# Real volume name — confirm with `docker volume ls | grep uploads` on the box
# and override if it doesn't match (this project's volumes so far follow
# `<project>_betterstats_<name>`, e.g. betterstats_pgdata for the DB).
UPLOADS_VOLUME="${UPLOADS_VOLUME:-${COMPOSE_PROJECT_NAME}_betterstats_uploads}"
#
# DELIBERATELY NOT BACKED UP: /mnt/media/bettercricket/internal/videos
#
# The instructional videos behind /videos are excluded from this backup by
# decision, not by oversight. They are capped at 512MB each, they never change
# after upload, and the originals live wherever they were recorded — so
# re-encrypting gigabytes into every dated bundle would buy nothing and would
# slow every run and every restore.
#
# The consequence is accepted and handled: a database restored onto a fresh box
# has video rows whose files are gone. The library still draws (titles,
# descriptions and thumbnails are all in Postgres) and each video reports that
# its file is not on the server, rather than the page breaking. Re-upload from
# the originals to fill them back in.
#
# If you are here to "fix" the omission by adding the directory: don't. Talk to
# whoever owns the backup policy first.
# age public key used to encrypt every bundle (age -R recipients file, or a
# single -r KEY). Generate with `age-keygen`; keep the PRIVATE key offline —
# it's only needed to restore, never to back up.
AGE_RECIPIENT="${AGE_RECIPIENT:-}"

log() { echo "[backup $(date -u +%FT%TZ)] $*"; }
fail() { log "ERROR: $*"; [ -n "${TASK_ID:-}" ] && exec_backend python -m app.scripts.backup_task finish-task "$TASK_ID" --status failed --error "$*" || true; exit 1; }

exec_backend() { docker compose exec -T "$BACKEND_SERVICE" "$@"; }

if [ -z "$AGE_RECIPIENT" ]; then
  fail "AGE_RECIPIENT is not set (see docs/backup-system.md — generate a keypair with age-keygen and set this to the public key)"
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

START_TASK_ARGS=(python -m app.scripts.backup_task start-task --type backup --triggered-by "$TRIGGERED_BY")
[ -n "${BACKUP_TRIGGERED_BY_USER_ID:-}" ] && START_TASK_ARGS+=(--triggered-by-user-id "$BACKUP_TRIGGERED_BY_USER_ID")
TASK_ID=$(exec_backend "${START_TASK_ARGS[@]}" | tr -d '\r')
log "Started backup task $TASK_ID -> $BUNDLE_DIR"

# --- Progress setup: the entities worth showing progress for, in the order
# a human would expect (foundational data first, big per-game stat tables
# last) --------------------------------------------------------------------
ENTITY_TABLES=(organisations seasons grades players games batting_innings bowling_spells fielding_stats bowler_wickets game_appearances fall_of_wickets partnerships users)
TOTAL_ENTITIES=${#ENTITY_TABLES[@]}

declare -A TABLE_COUNTS
while IFS=$'\t' read -r tbl cnt; do
  [ -z "$tbl" ] && continue
  TABLE_COUNTS["$tbl"]="$cnt"
done < <(exec_backend python -m app.scripts.backup_task table-counts)

# Reads pg_dump --verbose's stderr line by line; on each "dumping contents of
# table" line for a tracked entity, marks the PREVIOUS tracked entity done
# (we only find out a table is finished once the next one starts) and
# reports the new current stage. Also echoes every line through to the host
# log unchanged, so nothing about pg_dump's own output is lost.
track_dump_progress() {
  local prev_table="" prev_count=0 idx=0
  local dump_line_pat='dumping contents of table "public\.([a-zA-Z0-9_]+)"'
  while IFS= read -r line; do
    echo "$line"
    if [[ "$line" =~ $dump_line_pat ]]; then
      local table="${BASH_REMATCH[1]}"
      local is_tracked=0
      for t in "${ENTITY_TABLES[@]}"; do [ "$t" = "$table" ] && is_tracked=1 && break; done
      [ "$is_tracked" = "0" ] && continue
      if [ -n "$prev_table" ]; then
        exec_backend python -m app.scripts.backup_task mark-stage-done "$TASK_ID" --stage "$prev_table" --count "$prev_count" || true
      fi
      idx=$((idx + 1))
      local count="${TABLE_COUNTS[$table]:-0}"
      exec_backend python -m app.scripts.backup_task update-progress "$TASK_ID" \
        --stage "$table" --current "$idx" --total "$TOTAL_ENTITIES" \
        --message "Backing up $table ($idx/$TOTAL_ENTITIES) — $count records" || true
      prev_table="$table"; prev_count="$count"
    fi
  done
  if [ -n "$prev_table" ]; then
    exec_backend python -m app.scripts.backup_task mark-stage-done "$TASK_ID" --stage "$prev_table" --count "$prev_count" || true
  fi
}

# Grabs the most useful lines out of a captured stderr log for the task's
# error_message (so a failure is diagnosable from the Backups page alone,
# not just "pg_dump failed" with the real reason only in the host/agent
# logs) — prefers actual error/fatal lines, falls back to the raw tail.
_extract_err() {
  local log_file="$1" detail
  detail="$(grep -iE 'error|fatal|could not|permission denied|no such|no space' "$log_file" 2>/dev/null | tail -3 | tr '\n' ' ' | cut -c1-400)"
  if [ -z "$detail" ]; then
    detail="$(tail -c 400 "$log_file" 2>/dev/null | tr '\n' ' ')"
  fi
  echo "${detail:-no stderr captured}"
}

# --- Postgres: MVCC-consistent dump, no lock, no downtime ---------------------
log "Dumping database..."
DUMP_STDERR_LOG="$(mktemp)"
if ! docker compose exec -T "$DB_SERVICE" pg_dump --verbose -Fc -U "$POSTGRES_USER" "$POSTGRES_DB" \
      2> >(tee "$DUMP_STDERR_LOG" | track_dump_progress >&2) \
    | age -r "$AGE_RECIPIENT" -o "$BUNDLE_DIR/db.dump.age"; then
  ERR_DETAIL="$(_extract_err "$DUMP_STDERR_LOG")"
  rm -f "$DUMP_STDERR_LOG"
  fail "pg_dump/age failed: $ERR_DETAIL"
fi
rm -f "$DUMP_STDERR_LOG"

# --- uploads volume ------------------------------------------------------------
log "Archiving uploads volume..."
exec_backend python -m app.scripts.backup_task update-progress "$TASK_ID" \
  --stage uploads --current "$TOTAL_ENTITIES" --total "$TOTAL_ENTITIES" \
  --message "Archiving uploaded files..." || true
UPLOADS_STDERR_LOG="$(mktemp)"
if ! docker run --rm -v "${UPLOADS_VOLUME}:/from:ro" -v "$BUNDLE_DIR:/to" alpine \
      tar -C /from -c . \
    2>"$UPLOADS_STDERR_LOG" \
    | zstd -q \
    | age -r "$AGE_RECIPIENT" -o "$BUNDLE_DIR/uploads.tar.zst.age"; then
  ERR_DETAIL="$(_extract_err "$UPLOADS_STDERR_LOG")"
  rm -f "$UPLOADS_STDERR_LOG"
  fail "uploads archive failed: $ERR_DETAIL"
fi
rm -f "$UPLOADS_STDERR_LOG"

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
