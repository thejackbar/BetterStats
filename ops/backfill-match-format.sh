#!/usr/bin/env bash
#
# Backfill games.match_format so two-day matches are charged as two days.
#
# Paste-and-run from Cockpit's Terminal on the box.
#
#   ./backfill-match-format.sh applecross                  # dry run, one club
#   ./backfill-match-format.sh applecross --apply          # write the formats
#   ./backfill-match-format.sh applecross --apply --recompute   # …and rebuild fee rows
#   ./backfill-match-format.sh --all                       # dry run, every club
#   ./backfill-match-format.sh --all --apply --recompute
#   ./backfill-match-format.sh applecross --apply --season 2025
#   ./backfill-match-format.sh applecross --apply --all-seasons  # full history
#
# WHY
#   games.match_format was never written by the sync, so every synced game was
#   NULL and services.fees.derive_fee_format fell back to its "blank means one
#   day" default. Every two-day fixture was billed as a single day.
#
#   The sync records it now, and also bulk-fills the games it rediscovers on
#   each run — but an incremental run only scans a recent window, so the back
#   catalogue needs this.
#
# HOW FAR BACK
#   Per club, the default is the seasons that carry fee data plus that club's
#   latest season — a club collects fees for the season it is in and maybe the
#   one before, so reaching further back spends CA calls correcting money
#   nobody is collecting. The latest season is included because a club setting
#   up THIS season's fees has no fee rows in it yet. --all-seasons opts into
#   the full history, which is stats tidiness (StatLab / BetterIQ format
#   filters) rather than money.
#
#   A club onboarded after this shipped needs none of it — its games get the
#   format at creation.
#
# WHAT IT TOUCHES
#   games.match_format only, for games under the named club's OWN grades, and
#   only where Cricket Australia actually reports a format. With --recompute it
#   then re-derives that club's fee match days, which by its own rules leaves an
#   admin-overridden or already-paid row alone. Nothing else is written.
#
#   Dry run by default: it prints what it would change and exits. Read that
#   before you --apply.
#
# COST
#   One /scores/grades/{id}/matches call per grade in scope. The default scope
#   keeps that to a handful of seasons per club; --all-seasons is where it gets
#   expensive, since an established club has hundreds of grades across its
#   history. Combining --all with --all-seasons is a long, chatty pass against
#   CA's proxy — run that out of hours, if at all.
#
set -euo pipefail

COMPOSE_DIR="${COMPOSE_DIR:-/srv/docker}"
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-bltbox_docker_app}"
DB_USER="${DB_USER:-cricket}"
DB_NAME="${DB_NAME:-betterstats}"

ALL=0
CLUBS=()
PASSTHRU=()
while [ $# -gt 0 ]; do
  case "$1" in
    --all)                 ALL=1 ;;
    --apply|--recompute|--all-seasons) PASSTHRU+=("$1") ;;
    --season)              PASSTHRU+=("$1" "${2:?--season needs a year, e.g. --season 2025}"); shift ;;
    -h|--help)             sed -n '2,36p' "$0"; exit 0 ;;
    -*)                    echo "Unknown option: $1 (try --help)" >&2; exit 2 ;;
    *)                     CLUBS+=("$1") ;;
  esac
  shift
done

cd "$COMPOSE_DIR"

# Resolve compose SERVICES, never bare container names — the box runs
# everything as one pinned compose project, and a bare `docker` command is how
# you end up with a second stack on an empty volume.
resolve() {  # resolve <grep-pattern> <label>
  local svc
  svc="$(docker compose ps --services 2>/dev/null | grep -iE "$1" | head -1 || true)"
  if [ -z "$svc" ]; then
    echo "Could not work out the BetterStats $2 service in project" >&2
    echo "'$COMPOSE_PROJECT_NAME' at $COMPOSE_DIR. Set it by hand, e.g." >&2
    echo "  ${2^^}_SERVICE=betterstats-$2 $0 ..." >&2
    exit 1
  fi
  printf '%s' "$svc"
}
BACKEND_SERVICE="${BACKEND_SERVICE:-$(resolve '^betterstats[-_]?backend$' backend)}"

if [ "$ALL" = "1" ]; then
  DB_SERVICE="${DB_SERVICE:-$(resolve '^betterstats[-_]?(db|database|postgres)$' db)}"
  # Active, unarchived clubs only — an archived club is not one anybody is
  # billing, and re-pulling its whole grade list costs the same as a live one.
  mapfile -t CLUBS < <(docker compose exec -T "$DB_SERVICE" \
    psql -qtAX -U "$DB_USER" -d "$DB_NAME" -c \
    "SELECT COALESCE(slug, CAST(id AS TEXT)) FROM organisations
      WHERE archived_at IS NULL AND is_active ORDER BY name;")
fi

if [ ${#CLUBS[@]} -eq 0 ]; then
  echo "Name at least one club (id or public slug), or pass --all. Try --help." >&2
  exit 2
fi

case " ${PASSTHRU[*]:-} " in
  *" --apply "*) MODE="APPLYING" ;;
  *)             MODE="DRY RUN — nothing will be written" ;;
esac
echo "== match_format backfill: ${#CLUBS[@]} club(s) — $MODE =="
echo

failed=()
for club in "${CLUBS[@]}"; do
  [ -n "$club" ] || continue
  echo "---- $club ----"
  # Each club is its own invocation so one failure (a club whose grades CA no
  # longer serves) doesn't abort the rest of the run.
  if ! docker compose exec -T "$BACKEND_SERVICE" \
        python -m app.scripts.backfill_match_format "$club" ${PASSTHRU[@]+"${PASSTHRU[@]}"}; then
    echo "  ! failed — carrying on" >&2
    failed+=("$club")
  fi
  echo
done

if [ ${#failed[@]} -gt 0 ]; then
  echo "Finished with ${#failed[@]} failure(s): ${failed[*]}" >&2
  exit 1
fi
echo "Done."
