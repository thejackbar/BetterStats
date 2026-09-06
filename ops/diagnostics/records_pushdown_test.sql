-- The second half of the record book's ~900ms floor, and whether it can be
-- pushed down.
--
-- Section 4 of records_slow_board.sql showed a board costing 1,088ms as:
--   * 505ms of JIT compilation (fixed separately: the endpoint now runs
--     SET LOCAL jit = off, so every board below is measured with it OFF), and
--   * 483ms scanning ALL 315,288 rows of player_season_stats, because
--     migration 060's org-scoping EXISTS is a correlated SubPlan run once per
--     row, platform-wide, and the club filter is only applied afterwards by a
--     hash join to 101 players.
--
-- The question this answers: can the planner be given the club's players
-- UP FRONT, so it narrows the view instead of building it for everybody?
--
-- Run on the box:
--   cd /srv/docker && COMPOSE_PROJECT_NAME=bltbox_docker_app \
--     docker compose exec -T betterstats-db \
--     psql -U cricket -d betterstats -f - < ops/diagnostics/records_pushdown_test.sql
--
-- Reads only.

\timing on
SET jit = off;

\echo ''
\echo '=== A. today: join players, filter on the club (JIT already off) ==='
EXPLAIN (ANALYZE, BUFFERS)
SELECT p.id::text AS player_id, COALESCE(SUM(pss.runs), 0) AS runs
  FROM players p
  JOIN v_effective_player_season_stats pss ON pss.player_id = p.id
 WHERE p.organisation_id = 'efb7cc9a-4a33-4ac6-aa8a-b21d33c01ce1'
 GROUP BY p.id HAVING SUM(pss.runs) > 0
 ORDER BY runs DESC LIMIT 25;

\echo ''
\echo '=== B. the same, with the club players named as an array first ==='
\echo '    A plain predicate on the view own player_id column, which the'
\echo '    planner can push into each UNION ALL branch.'
EXPLAIN (ANALYZE, BUFFERS)
SELECT p.id::text AS player_id, COALESCE(SUM(pss.runs), 0) AS runs
  FROM players p
  JOIN v_effective_player_season_stats pss ON pss.player_id = p.id
 WHERE p.organisation_id = 'efb7cc9a-4a33-4ac6-aa8a-b21d33c01ce1'
   AND pss.player_id = ANY (
        SELECT id FROM players
         WHERE organisation_id = 'efb7cc9a-4a33-4ac6-aa8a-b21d33c01ce1')
 GROUP BY p.id HAVING SUM(pss.runs) > 0
 ORDER BY runs DESC LIMIT 25;

\echo ''
\echo '=== C. and with the ids as a literal array, which is what the app'
\echo '       would actually bind after one cheap lookup ==='
EXPLAIN (ANALYZE, BUFFERS)
SELECT p.id::text AS player_id, COALESCE(SUM(pss.runs), 0) AS runs
  FROM players p
  JOIN v_effective_player_season_stats pss ON pss.player_id = p.id
 WHERE p.organisation_id = 'efb7cc9a-4a33-4ac6-aa8a-b21d33c01ce1'
   AND pss.player_id = ANY (ARRAY(
        SELECT id FROM players
         WHERE organisation_id = 'efb7cc9a-4a33-4ac6-aa8a-b21d33c01ce1'))
 GROUP BY p.id HAVING SUM(pss.runs) > 0
 ORDER BY runs DESC LIMIT 25;

\echo ''
\echo '=== D. do the three agree? They must return identical rows. ==='
WITH a AS (
  SELECT p.id, COALESCE(SUM(pss.runs), 0) AS runs
    FROM players p JOIN v_effective_player_season_stats pss ON pss.player_id = p.id
   WHERE p.organisation_id = 'efb7cc9a-4a33-4ac6-aa8a-b21d33c01ce1'
   GROUP BY p.id HAVING SUM(pss.runs) > 0),
c AS (
  SELECT p.id, COALESCE(SUM(pss.runs), 0) AS runs
    FROM players p JOIN v_effective_player_season_stats pss ON pss.player_id = p.id
   WHERE p.organisation_id = 'efb7cc9a-4a33-4ac6-aa8a-b21d33c01ce1'
     AND pss.player_id = ANY (ARRAY(
          SELECT id FROM players
           WHERE organisation_id = 'efb7cc9a-4a33-4ac6-aa8a-b21d33c01ce1'))
   GROUP BY p.id HAVING SUM(pss.runs) > 0)
SELECT (SELECT count(*) FROM a) AS rows_today,
       (SELECT count(*) FROM c) AS rows_pushed_down,
       (SELECT count(*) FROM (SELECT * FROM a EXCEPT SELECT * FROM c) d) AS only_in_today,
       (SELECT count(*) FROM (SELECT * FROM c EXCEPT SELECT * FROM a) d) AS only_in_pushed;

\echo ''
\echo '=== E. what JIT alone was costing: the same board with it back ON ==='
SET jit = on;
EXPLAIN (ANALYZE)
SELECT p.id::text AS player_id, COALESCE(SUM(pss.runs), 0) AS runs
  FROM players p
  JOIN v_effective_player_season_stats pss ON pss.player_id = p.id
 WHERE p.organisation_id = 'efb7cc9a-4a33-4ac6-aa8a-b21d33c01ce1'
 GROUP BY p.id HAVING SUM(pss.runs) > 0
 ORDER BY runs DESC LIMIT 25;
SET jit = off;

\echo ''
\echo '=== F. the form the app actually sends: a BOUND array parameter ==='
\echo '    C proved a literal array pushes down. This proves the bound one'
\echo '    does too, which is what asyncpg sends for a Python list.'
PREPARE board_bound (uuid[]) AS
SELECT p.id::text AS player_id, COALESCE(SUM(pss.runs), 0) AS runs
  FROM players p
  JOIN v_effective_player_season_stats pss ON pss.player_id = p.id
 WHERE p.organisation_id = 'efb7cc9a-4a33-4ac6-aa8a-b21d33c01ce1'
   AND pss.player_id = ANY(CAST($1 AS uuid[]))
 GROUP BY p.id HAVING SUM(pss.runs) > 0
 ORDER BY runs DESC LIMIT 25;

-- EXECUTE cannot take a subquery, so the ids are collected into a psql
-- variable first. Six runs: Postgres builds a custom plan for the first five
-- and only then weighs a generic one, so the sixth says what a warmed-up
-- connection actually runs.
SELECT COALESCE(array_agg(id), ARRAY[]::uuid[])::text AS club_ids FROM players
 WHERE organisation_id = 'efb7cc9a-4a33-4ac6-aa8a-b21d33c01ce1' \gset
EXPLAIN (ANALYZE) EXECUTE board_bound (:'club_ids');
EXPLAIN (ANALYZE) EXECUTE board_bound (:'club_ids');
EXPLAIN (ANALYZE) EXECUTE board_bound (:'club_ids');
EXPLAIN (ANALYZE) EXECUTE board_bound (:'club_ids');
EXPLAIN (ANALYZE) EXECUTE board_bound (:'club_ids');
EXPLAIN (ANALYZE) EXECUTE board_bound (:'club_ids');
DEALLOCATE board_bound;

\echo ''
\echo '=== G. an empty array, which is what a club with no players binds ==='
EXPLAIN (ANALYZE)
SELECT p.id::text, COALESCE(SUM(pss.runs), 0) AS runs
  FROM players p
  JOIN v_effective_player_season_stats pss ON pss.player_id = p.id
 WHERE pss.player_id = ANY(CAST(ARRAY[]::uuid[] AS uuid[]))
 GROUP BY p.id;
