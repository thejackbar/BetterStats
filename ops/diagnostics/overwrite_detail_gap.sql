-- How much did the Stage 2 override take from each season? Reads only.
--
-- For every import match that hides a synced PlayHQ game, compares what the page shows (the
-- import's own rows) with what the hidden PlayHQ game holds:
--   lack_credits_ca_has   no bowler/fielder named on dismissals, but PlayHQ has them
--   neither_has           no names on either side (PlayHQ never had them either)
--   shown_has             the page already shows bowler/fielder names
--   balls_missing_ca_has  batters with no balls faced on the page where PlayHQ recorded balls
-- Nothing is deleted by an override: the PlayHQ game and all of its rows are still there.
--
--   cd /srv/docker && COMPOSE_PROJECT_NAME=bltbox_docker_app \
--     docker compose exec -T betterstats-db psql -U cricket -d betterstats \
--     -f - < betterstats/ops/diagnostics/overwrite_detail_gap.sql

\set org 'f0d283dc-87d8-eb11-a7ad-2818780da0cc'

\echo '=== 1. by season (newest first) ==='
WITH pm AS (
    SELECT mg.id AS mid, mg.superseded_by_game_id AS gid, s.name AS season
      FROM manual_games mg JOIN seasons s ON s.id = mg.season_id
     WHERE mg.organisation_id = CAST(:'org' AS UUID)
       AND mg.superseded_by_game_id IS NOT NULL AND mg.pair_prefers_import
), c AS (
    SELECT pm.*,
           (SELECT count(*) FROM manual_bowler_wickets x WHERE x.manual_game_id = pm.mid) AS shown_credits,
           (SELECT count(*) FROM bowler_wickets y WHERE y.game_id = pm.gid) AS ca_credits,
           (SELECT count(*) FROM manual_batting_innings b
             WHERE b.manual_game_id = pm.mid AND NOT COALESCE(b.did_not_bat, FALSE)
               AND b.balls IS NULL) AS shown_no_balls,
           (SELECT count(*) FROM batting_innings b
             WHERE b.game_id = pm.gid AND b.balls > 0) AS ca_balls
      FROM pm
)
SELECT season,
       count(*) AS overridden_matches,
       count(*) FILTER (WHERE shown_credits = 0 AND ca_credits > 0) AS lack_credits_ca_has,
       count(*) FILTER (WHERE shown_credits = 0 AND ca_credits = 0) AS neither_has,
       count(*) FILTER (WHERE shown_credits > 0) AS shown_has,
       count(*) FILTER (WHERE shown_no_balls > 0 AND ca_balls > 0) AS balls_missing_ca_has
  FROM c
 GROUP BY season
 ORDER BY season DESC;

\echo ''
\echo '=== 2. the 2026 March finals weekend, match by match ==='
SELECT mg.played_at::date AS played, mg.opposition, g.name AS grade,
       (SELECT count(*) FROM manual_bowler_wickets x WHERE x.manual_game_id = mg.id) AS shown_credits,
       (SELECT count(*) FROM bowler_wickets y WHERE y.game_id = mg.superseded_by_game_id) AS ca_credits,
       (SELECT count(*) FROM batting_innings b WHERE b.game_id = mg.superseded_by_game_id) AS ca_batting_lines,
       mg.pair_prefers_import AS import_shown
  FROM manual_games mg
  LEFT JOIN grades g ON g.id = mg.grade_id
 WHERE mg.organisation_id = CAST(:'org' AS UUID)
   AND mg.superseded_by_game_id IS NOT NULL
   AND mg.played_at::date BETWEEN DATE '2026-03-14' AND DATE '2026-03-28'
 ORDER BY mg.played_at, g.name;
