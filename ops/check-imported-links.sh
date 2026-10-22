#!/usr/bin/env bash
# Check and fix club scorecards linked to the wrong game, for one club (Shoalwater Bay by default).
#
# The scorebook CSV import links a card to the first synced game that shares a date and an opposition
# word and ignores grade. On a day the club plays several grades against one opposition the B grade
# card lands on the A grade game, the real B grade game stays unlinked, and the match is counted twice
# (once under One Day, once under Two Day). Card review's Possible doubles finds these; this runs the
# same scan and the same fix for the whole club.
#
#   ops/check-imported-links.sh check            what is wrong and what the fix would do; changes nothing
#   ops/check-imported-links.sh fix              the same; changes nothing
#   ops/check-imported-links.sh fix --apply      move the strong wrong links and link the strong unlinked
#                                                pairs, as ONE batch; prints the batch id
#   ops/check-imported-links.sh undo <batch-id>  undo that batch
#   ops/check-imported-links.sh audit            read-only second opinion: every linked card against its game's
#                                                grade, what Possible doubles shows, free games the scan skipped,
#                                                and scores a player still sees twice. Run it before AND after fix.
#
# Run them in that order, reading each one's output. The fix only touches STRONG matches (most of the
# smaller card is on the better game with the same scores), never a link someone confirmed with
# "Looks right: keep the link", and deletes nothing. The batch can also be undone from the Card review
# overview. Weaker matches are left for a person in Card review, Possible doubles.
#
#   CLUB=other-club-slug ops/check-imported-links.sh check        another club
set -euo pipefail

CLUB="${CLUB:-shoalwater-bay-cricket-club}"

if [ -z "${BACKEND_CMD:-}" ]; then
  cd /srv/docker
  export COMPOSE_PROJECT_NAME=bltbox_docker_app
  BACKEND_CMD="docker compose exec -T betterstats-backend python -m"
fi

fail() { echo "STOP: $1" >&2; exit 1; }

preflight() {
  out="$($BACKEND_CMD app.scripts.fix_wrong_links 2>&1 || true)$($BACKEND_CMD app.scripts.audit_pairing 2>&1 || true)"
  case "$out" in
    *"No module named"*) fail "the backend does not have this script yet. Run /srv/docker/betterstats/deploy.sh first." ;;
  esac
  echo "ok: the repair script is on the server (club: $CLUB)"
}

step="${1:-check}"
preflight

case "$step" in
  check|fix)
    if [ "$step" = "fix" ] && [ "${2:-}" = "--apply" ]; then
      echo; echo "--- applying (one undoable batch)"
      $BACKEND_CMD app.scripts.fix_wrong_links "$CLUB" --apply
      echo; echo "--- what is left"
      $BACKEND_CMD app.scripts.fix_wrong_links "$CLUB"
    else
      echo; echo "--- cards on the wrong game, and cards with no link, that the scan finds"
      $BACKEND_CMD app.scripts.fix_wrong_links "$CLUB"
      echo; echo "--- two cards each sitting on the other's game (the older repair; dry run)"
      $BACKEND_CMD app.scripts.repair_crossed_pairs "$CLUB" || echo "(repair_crossed_pairs did not run cleanly; the output above is still valid)"
      [ "$step" = "fix" ] && { echo; echo "Nothing was changed. To fix, run:  $0 fix --apply"; }
    fi
    ;;
  audit)
    $BACKEND_CMD app.scripts.audit_pairing "$CLUB" ${2:+--examples "$2"}
    ;;
  undo)
    [ -n "${2:-}" ] || fail "give the batch id the fix printed:  $0 undo <batch-id>"
    $BACKEND_CMD app.scripts.fix_wrong_links "$CLUB" --undo "$2"
    ;;
  *) fail "unknown step '$step'. Use: check | audit | fix [--apply] | undo <batch-id>" ;;
esac
