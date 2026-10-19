#!/usr/bin/env bash
# One-off: untangle Brook Grumont at Gisborne.
#
# One player, a gap of several years, a new Cricket Australia profile on return. On 14 Oct the
# club merged five redacted junior profiles into the new one (331ef65c), and that one into a
# different player (80f4940d). This undoes those seven merges, checks the new profile now
# holds only his own recent games, then merges it into his old profile (ed4e36cf).
#
#   ops/gisborne-brook-fix.sh preview   what would be undone; changes nothing
#   ops/gisborne-brook-fix.sh undo      undo the seven merges
#   ops/gisborne-brook-fix.sh merge     check, then show the merge; changes nothing
#   ops/gisborne-brook-fix.sh merge --apply   check, then merge 331ef65c into ed4e36cf
#   ops/gisborne-brook-fix.sh verify    read only: where things stand
#
# Run them in that order, reading each one's output. Every undo and merge is in the merge
# log and the audit log, and can be reversed with undo_player_merge. It stops at the first
# thing that is not as expected.
set -euo pipefail

CLUB="${CLUB:-gisborne-cricket-club}"
ORG="${ORG:-4d7a9e9b-86d8-eb11-a7ad-2818780da0cc}"
KEEP="${KEEP:-ed4e36cf-28cd-4012-b00c-2baf021cba9b}"
NEW="${NEW:-331ef65c-d93d-4bd2-afc5-dd720b90bd66}"
OTHER="${OTHER:-80f4940d-6e90-4f02-942f-63c4f06e81d1}"
BY="${BY:-jack}"

if [ -z "${BACKEND_CMD:-}" ]; then
  cd /srv/docker
  export COMPOSE_PROJECT_NAME=bltbox_docker_app
  BACKEND_CMD="docker compose exec -T betterstats-backend python -m"
  DB_CMD="docker compose exec -T betterstats-db psql -U cricket -d betterstats"
fi

sql() { $DB_CMD -tAX -c "$1"; }
fail() { echo "STOP: $1" >&2; exit 1; }

step="${1:-}"
apply=""
[ "${2:-}" = "--apply" ] && apply="--apply"

preflight() {
  out="$($BACKEND_CMD app.scripts.merge_player_pair 2>&1 || true)"
  case "$out" in
    *"No module named"*) fail "the backend does not have the new scripts yet. Run /srv/docker/betterstats/deploy.sh first." ;;
  esac
  echo "ok: scripts are on the server"
}

expected_merges() {
  n="$(sql "SELECT COUNT(*) FROM merge_logs WHERE org_id = '$ORG' AND undone_at IS NULL AND (id, removed_player_id::text, keep_player_id::text) IN (
    (8102, '23ad6501-41e6-4222-8077-221888c26b56', '$NEW'),
    (8103, 'ce68ebe3-38dd-4b0d-bfe5-4f3ebc39d463', '$NEW'),
    (8104, 'd3835185-8775-43eb-99dd-2c3fae74ac57', '$NEW'),
    (8105, '19a0e927-f51f-49bb-964a-b9d21ba681ac', '$NEW'),
    (8106, '62cac645-bc45-4c1b-8055-f0b61c879919', '$NEW'),
    (8107, '$NEW', '$OTHER'),
    (8108, 'd412f328-881f-41d2-94d0-56752ff72f5e', '$OTHER'))")"
  [ "$n" = "7" ] || fail "expected all seven merges (8102 to 8108) to be live and as logged; found $n. Nothing changed."
  echo "ok: merges 8102 to 8108 are live and as logged"
}

case "$step" in
  preview)
    preflight
    expected_merges
    $BACKEND_CMD app.scripts.undo_player_merge "$CLUB" 8108 8107 8106 8105 8104 8103 8102
    echo
    echo "Preview only. If it looks right: ops/gisborne-brook-fix.sh undo"
    ;;
  undo)
    preflight
    expected_merges
    $BACKEND_CMD app.scripts.undo_player_merge "$CLUB" 8108 8107 8106 8105 8104 8103 8102 --apply --by "$BY"
    echo
    echo "Undone. Next: ops/gisborne-brook-fix.sh merge"
    ;;
  merge)
    preflight
    live="$(sql "SELECT COUNT(*) FROM merge_logs WHERE org_id = '$ORG' AND undone_at IS NULL AND id BETWEEN 8102 AND 8108")"
    [ "$live" = "0" ] || fail "$live of merges 8102 to 8108 are still live. Run the undo step first."
    exists="$(sql "SELECT COUNT(*) FROM players WHERE organisation_id = '$ORG' AND id IN ('$KEEP', '$NEW')")"
    [ "$exists" = "2" ] || fail "the old and new profiles are not both there."
    games="$(sql "SELECT COUNT(*) FROM game_appearances WHERE player_id = '$NEW'")"
    first="$(sql "SELECT COALESCE(MIN(g.played_at)::text, 'none') FROM game_appearances ga JOIN games g ON g.id = ga.game_id WHERE ga.player_id = '$NEW'")"
    shared="$(sql "SELECT COUNT(*) FROM game_appearances a JOIN game_appearances b ON b.game_id = a.game_id WHERE a.player_id = '$KEEP' AND b.player_id = '$NEW'")"
    echo "new profile: $games games, first on $first; games both profiles are in: $shared"
    [ "$shared" = "0" ] || fail "both profiles are in the same game, so they are probably two people."
    [ "$games" -le 8 ] || fail "the new profile holds $games games. Expected only his own few recent ones. Not merging."
    case "$first" in
      none) ;;
      *) [ "$first" \> "2025-06-30" ] || fail "the new profile has games from $first. Expected only this season's. Not merging." ;;
    esac
    echo "ok: the new profile holds only recent games and none in common with the old one"
    $BACKEND_CMD app.scripts.merge_player_pair "$CLUB" "$KEEP" "$NEW" ${apply:+--apply --by "$BY"}
    [ -n "$apply" ] && { echo; echo "Merged. Next: ops/gisborne-brook-fix.sh verify"; } || echo "Preview only. If it looks right: ops/gisborne-brook-fix.sh merge --apply"
    ;;
  verify)
    echo "--- merges 8102 to 8108 (undone_at set = undone)"
    sql "SELECT id || '  ' || removed_player_id || ' -> ' || keep_player_id || '  ' || COALESCE('undone ' || undone_at::date, 'LIVE') FROM merge_logs WHERE org_id = '$ORG' AND id BETWEEN 8102 AND 8108 ORDER BY id"
    echo "--- the old profile now"
    sql "SELECT p.name || '  status=' || COALESCE(p.status, '') || '  is_player=' || COALESCE(p.is_player::text, '') || '  games=' || COUNT(ga.game_id) || '  last=' || COALESCE(MAX(g.played_at)::text, 'none') FROM players p LEFT JOIN game_appearances ga ON ga.player_id = p.id LEFT JOIN games g ON g.id = ga.game_id WHERE p.id = '$KEEP' GROUP BY p.id, p.name, p.status, p.is_player"
    echo "--- the new profile (gone after the merge)"
    sql "SELECT COUNT(*) FROM players WHERE id = '$NEW'"
    echo "--- games on the other player since 14 Oct (his, but synced after the merge): should be none"
    sql "SELECT g.played_at || '  ' || ga.game_id FROM game_appearances ga JOIN games g ON g.id = ga.game_id WHERE ga.player_id = '$OTHER' AND g.played_at >= '2026-10-14' ORDER BY g.played_at"
    echo "--- the other player's own career (should still be there)"
    sql "SELECT COUNT(*) || ' games, ' || COALESCE(MIN(g.played_at)::text, '') || ' to ' || COALESCE(MAX(g.played_at)::text, '') FROM game_appearances ga JOIN games g ON g.id = ga.game_id WHERE ga.player_id = '$OTHER'"
    ;;
  *)
    sed -n '2,19p' "$0"
    exit 2
    ;;
esac
