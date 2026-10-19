-- Why the Payneham records page takes ~100s: partnerships_by_wicket_rows and
-- partnerships_by_grade_rows (about 47s each). Runs the shipped shape and the
-- shape with a bound array of the club's player ids (CLAUDE.md rule 11), both
-- with EXPLAIN ANALYZE. Reads only.
--
--   cd /srv/docker && COMPOSE_PROJECT_NAME=bltbox_docker_app \
--     docker compose exec -T betterstats-db \
--     psql -U cricket -d betterstats -f - < betterstats/ops/diagnostics/records_partnerships_slow.sql

\set org 'f0d283dc-87d8-eb11-a7ad-2818780da0cc'
\timing on
SET jit = off;
SET statement_timeout = '240s';

SELECT array_agg(id)::text AS ids FROM players WHERE organisation_id = :'org' \gset

\echo '=== A. as shipped (filter on players after the view) ==='
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, TIMING OFF)
SELECT pt.runs, pt.wicket_number,
       ROW_NUMBER() OVER (PARTITION BY pt.wicket_number ORDER BY pt.runs DESC) AS rn
  FROM v_effective_partnerships pt
  JOIN v_effective_games g ON g.id = pt.game_id
  JOIN grades gr ON gr.id = g.grade_id
  JOIN seasons s ON s.id = gr.season_id
  LEFT JOIN players p1 ON p1.id = pt.batter1_id
  LEFT JOIN players p2 ON p2.id = pt.batter2_id
 WHERE pt.is_club_innings IS NOT FALSE
   AND p1.organisation_id = :'org' AND p2.organisation_id = :'org'
   AND pt.runs IS NOT NULL AND pt.runs > 0 AND pt.wicket_number BETWEEN 1 AND 10;

\echo '=== B. with the club player ids bound as an array ==='
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, TIMING OFF)
SELECT pt.runs, pt.wicket_number,
       ROW_NUMBER() OVER (PARTITION BY pt.wicket_number ORDER BY pt.runs DESC) AS rn
  FROM v_effective_partnerships pt
  JOIN v_effective_games g ON g.id = pt.game_id
  JOIN grades gr ON gr.id = g.grade_id
  JOIN seasons s ON s.id = gr.season_id
  LEFT JOIN players p1 ON p1.id = pt.batter1_id
  LEFT JOIN players p2 ON p2.id = pt.batter2_id
 WHERE pt.is_club_innings IS NOT FALSE
   AND pt.batter1_id = ANY(CAST(:'ids' AS uuid[]))
   AND pt.batter2_id = ANY(CAST(:'ids' AS uuid[]))
   AND p1.organisation_id = :'org' AND p2.organisation_id = :'org'
   AND pt.runs IS NOT NULL AND pt.runs > 0 AND pt.wicket_number BETWEEN 1 AND 10;

\echo '=== C. indexes on the two partnership tables ==='
SELECT tablename, indexname FROM pg_indexes
 WHERE tablename IN ('partnerships', 'manual_partnerships') ORDER BY 1, 2;
