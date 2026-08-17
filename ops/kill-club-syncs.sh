#!/usr/bin/env bash
#
# Kill in-flight club syncs — for clubs that are already set up.
#
# Paste-and-run from Cockpit's Terminal on the box.
#
#   ./kill-club-syncs.sh                 # dry run — lists what it would cancel
#   ./kill-club-syncs.sh --apply         # cancel them
#   ./kill-club-syncs.sh --apply --wait  # cancel, then wait for the loops to stop
#   ./kill-club-syncs.sh --apply --wait --force   # …and hard-stop any stragglers
#
# WHAT "SET UP" MEANS
#   A club that has already completed at least one successful full pull
#   (a sync_run of kind org_full / org_hard_refresh with status 'success').
#   That is the same test the onboarding wizard uses for "this club's first
#   historical pull is done". A brand-new club's very first sync is therefore
#   NEVER touched — killing it would leave that club with no data and no
#   obvious way back.
#
# HOW IT KILLS
#   A running sync is stopped the way the app's own Cancel Sync button stops
#   it: set sync_runs.control = 'cancel', which the sync loop notices at its
#   next checkpoint (per season / per few dozen games) and finalizes itself
#   cleanly. That is a safe stopping point, not a torn write.
#   A 'paused' run has no live loop polling anything, so it is marked
#   'cancelled' directly — same as the app does.
#
#   DO NOT try to kill a sync by restarting the backend. The lifespan
#   deliberately RESUMES any sync_run still 'running' at boot (see
#   _resume_interrupted_syncs in main.py), so a restart starts them again.
#   Cancel first, let the rows leave 'running', and then a restart is safe.
#
# SCOPE
#   Cricket only. BetterFootball runs its own database and its own
#   afl_full / afl_sync runs; nothing here reaches them.
#
#   This stops what is running NOW. The weekly scheduled sync (Sunday 03:00)
#   will start fresh runs — re-run this after it fires, or leave the box's
#   scheduler alone and accept the next weekly pull.
#
set -euo pipefail

COMPOSE_DIR="${COMPOSE_DIR:-/srv/docker}"
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-bltbox_docker_app}"
DB_USER="${DB_USER:-cricket}"
DB_NAME="${DB_NAME:-betterstats}"
WAIT_SECONDS="${WAIT_SECONDS:-600}"

APPLY=0; WAIT=0; FORCE=0; ALL_CLUBS=0
for arg in "$@"; do
  case "$arg" in
    --apply)      APPLY=1 ;;
    --wait)       WAIT=1 ;;
    --force)      FORCE=1 ;;
    --all-clubs)  ALL_CLUBS=1 ;;   # include clubs still on their first sync
    -h|--help)    sed -n '2,40p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

cd "$COMPOSE_DIR"

# Resolve the database compose SERVICE (never a bare container name — the box
# runs everything as one pinned compose project, and bare `docker` commands are
# how you end up with a second stack on an empty volume).
DB_SERVICE="${DB_SERVICE:-}"
if [ -z "$DB_SERVICE" ]; then
  DB_SERVICE="$(docker compose ps --services 2>/dev/null \
    | grep -iE '^betterstats[-_]?(db|database|postgres)$' | head -1 || true)"
fi
if [ -z "$DB_SERVICE" ]; then
  DB_SERVICE="$(docker compose ps --services 2>/dev/null \
    | grep -i betterstats | grep -iE 'db|postgres' | head -1 || true)"
fi
if [ -z "$DB_SERVICE" ]; then
  echo "Could not work out the BetterStats database service in project" >&2
  echo "'$COMPOSE_PROJECT_NAME' at $COMPOSE_DIR." >&2
  echo "Set it by hand, e.g.  DB_SERVICE=betterstats-db $0 $*" >&2
  exit 1
fi

psql_do() {  # SQL on stdin
  docker compose exec -T "$DB_SERVICE" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 "$@"
}

# Clubs that are already set up. Overridden by --all-clubs.
if [ "$ALL_CLUBS" = "1" ]; then
  TARGET_ORGS="SELECT id FROM organisations"
  SCOPE_NOTE="EVERY club (--all-clubs: includes clubs still on their first sync)"
else
  TARGET_ORGS="SELECT DISTINCT org_id FROM sync_runs
               WHERE kind IN ('org_full','org_hard_refresh') AND status = 'success'"
  SCOPE_NOTE="clubs that have completed at least one successful full sync"
fi

echo "Project : $COMPOSE_PROJECT_NAME   DB service: $DB_SERVICE"
echo "Scope   : $SCOPE_NOTE"
echo

echo "── Syncs in flight ──────────────────────────────────────────────────"
psql_do <<SQL
\pset border 2
SELECT o.name                         AS club,
       r.kind,
       r.status,
       date_trunc('second', r.started_at) AS started,
       date_trunc('second', NOW() - r.started_at) AS running_for,
       CASE WHEN r.org_id IN ($TARGET_ORGS) THEN 'cancel'
            ELSE 'SKIP — first sync' END AS action
  FROM sync_runs r
  JOIN organisations o ON o.id = r.org_id
 WHERE r.status IN ('running','paused')
 ORDER BY action DESC, r.started_at;
SQL
echo

if [ "$APPLY" != "1" ]; then
  echo "Dry run. Nothing changed. Re-run with --apply to cancel the rows marked 'cancel'."
  exit 0
fi

echo "── Cancelling ───────────────────────────────────────────────────────"
psql_do <<SQL
\pset border 2
-- A live loop stops itself at its next checkpoint once this flag is set.
UPDATE sync_runs
   SET control = 'cancel', updated_at = NOW()
 WHERE status = 'running'
   AND org_id IN ($TARGET_ORGS);

-- A paused run has nothing polling for the flag, so finalize it here.
UPDATE sync_runs
   SET status = 'cancelled', control = NULL, completed_at = NOW(), updated_at = NOW()
 WHERE status = 'paused'
   AND org_id IN ($TARGET_ORGS);
SQL
echo "Cancel requested. Running loops stop at their next checkpoint."
echo

still_running() {
  psql_do -tAc "SELECT count(*) FROM sync_runs
                 WHERE status = 'running' AND control = 'cancel'
                   AND org_id IN ($TARGET_ORGS);" | tr -d '[:space:]'
}

if [ "$WAIT" = "1" ]; then
  echo "── Waiting (up to ${WAIT_SECONDS}s) ─────────────────────────────────"
  deadline=$(( $(date +%s) + WAIT_SECONDS ))
  while :; do
    left="$(still_running)"
    [ "$left" = "0" ] && { echo "All targeted syncs have stopped."; break; }
    if [ "$(date +%s)" -ge "$deadline" ]; then
      echo "$left still running after ${WAIT_SECONDS}s."
      if [ "$FORCE" = "1" ]; then
        echo "Forcing the rows terminal."
        psql_do <<SQL
UPDATE sync_runs
   SET status = 'cancelled', control = NULL, completed_at = NOW(), updated_at = NOW()
 WHERE status = 'running' AND control = 'cancel'
   AND org_id IN ($TARGET_ORGS);
SQL
        echo
        echo "NOTE: forcing marks the ROW cancelled; the in-flight coroutine may"
        echo "keep writing until the backend is restarted. Because the rows are no"
        echo "longer 'running', a restart will NOT resume them:"
        echo "  cd $COMPOSE_DIR && COMPOSE_PROJECT_NAME=$COMPOSE_PROJECT_NAME \\"
        echo "    docker compose restart betterstats-backend"
      else
        echo "Re-run with --force to mark them terminal, or leave them to finish."
      fi
      break
    fi
    sleep 10
  done
  echo
fi

echo "── Now in flight ────────────────────────────────────────────────────"
psql_do <<SQL
\pset border 2
SELECT o.name AS club, r.kind, r.status, r.control
  FROM sync_runs r JOIN organisations o ON o.id = r.org_id
 WHERE r.status IN ('running','paused')
 ORDER BY r.started_at;
SQL
