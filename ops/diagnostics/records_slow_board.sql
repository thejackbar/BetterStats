-- Why the club record book takes ~13s unfiltered, and where the ~900ms floor
-- under every aggregate board comes from.
--
-- Run on the box:
--   cd /srv/docker && COMPOSE_PROJECT_NAME=bltbox_docker_app \
--     docker compose exec -T betterstats-db \
--     psql -U cricket -d betterstats -f - < ops/diagnostics/records_slow_board.sql
--
-- Reads only. Nothing here writes, locks or analyses.

\timing on

\echo ''
\echo '=== 1. what indexes these tables actually carry ==='
SELECT tablename, indexname
  FROM pg_indexes
 WHERE schemaname = 'public'
   AND tablename IN ('game_appearances', 'batting_innings', 'bowling_spells',
                     'fielding_stats', 'player_season_stats', 'games', 'grades')
 ORDER BY tablename, indexname;

\echo ''
\echo '=== 2. how big the tables behind it are ==='
SELECT relname, n_live_tup AS approx_rows,
       pg_size_pretty(pg_total_relation_size(relid)) AS total_size
  FROM pg_stat_user_tables
 WHERE relname IN ('game_appearances', 'batting_innings', 'bowling_spells',
                   'fielding_stats', 'player_season_stats', 'games')
 ORDER BY n_live_tup DESC;

\echo ''
\echo '=== 3. the `unplayed` subquery inside v_effective_player_season_stats, ALONE ==='
\echo '    It is an uncorrelated derived table joined on (player_id, season_id),'
\echo '    so no club filter can reach it: it is computed for the WHOLE platform'
\echo '    every time the view is referenced, and the record book references the'
\echo '    view 14 times in one request.'
EXPLAIN (ANALYZE, BUFFERS)
SELECT ga.player_id AS unplayed_player_id,
       gr.season_id AS unplayed_season_id,
       COUNT(DISTINCT ga.game_id)::integer AS unplayed_matches
  FROM game_appearances ga
  JOIN games g ON g.id = ga.game_id
  JOIN grades gr ON gr.id = g.grade_id
 WHERE g.status IN ('ABANDONED', 'CANCELLED')
   AND NOT EXISTS (SELECT 1 FROM batting_innings bi
                    WHERE bi.game_id = ga.game_id AND bi.player_id = ga.player_id)
   AND NOT EXISTS (SELECT 1 FROM bowling_spells bs
                    WHERE bs.game_id = ga.game_id AND bs.player_id = ga.player_id)
   AND NOT EXISTS (SELECT 1 FROM fielding_stats fs
                    WHERE fs.game_id = ga.game_id AND fs.player_id = ga.player_id)
 GROUP BY ga.player_id, gr.season_id;

\echo ''
\echo '=== 4. one real board, exactly as the record book runs it (Hamilton) ==='
EXPLAIN (ANALYZE, BUFFERS)
SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
       COALESCE(SUM(pss.runs), 0)            AS runs,
       COALESCE(SUM(pss.batting_innings), 0) AS innings,
       COALESCE(SUM(pss.not_outs), 0)        AS not_outs,
       COALESCE(SUM(pss.matches), 0)         AS matches,
       MAX(pss.high_score)                   AS high_score
  FROM players p
  JOIN v_effective_player_season_stats pss ON pss.player_id = p.id
 WHERE p.organisation_id = 'efb7cc9a-4a33-4ac6-aa8a-b21d33c01ce1'
 GROUP BY p.id, COALESCE(p.display_name_override, p.name)
HAVING SUM(pss.runs) > 0
 ORDER BY runs DESC LIMIT 25;

\echo ''
\echo '=== 5. the same board with the view left out entirely, as a control ==='
\echo '    If this is fast and 4 is slow, the view is the cost, not the board.'
EXPLAIN (ANALYZE, BUFFERS)
SELECT p.id::text AS player_id, COALESCE(SUM(pss.runs), 0) AS runs
  FROM players p
  JOIN player_season_stats pss ON pss.player_id = p.id
 WHERE p.organisation_id = 'efb7cc9a-4a33-4ac6-aa8a-b21d33c01ce1'
 GROUP BY p.id
HAVING SUM(pss.runs) > 0
 ORDER BY runs DESC LIMIT 25;
