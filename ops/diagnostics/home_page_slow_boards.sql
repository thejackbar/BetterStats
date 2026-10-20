-- Why a big club's home page takes 15s+ (Applecross, Oct 2026).
--
-- Measured against the live site (public API, no auth):
--   Applecross, no season picked: batting top 5, bowling top 5, fielding top 5 and
--   /summary each take ~45s. Milestones take 3 to 6s.
--   Same requests at Kalamunda, Albury and Portland Tigers: 2 to 4s.
--   One season picked, or a grade_name board (per-innings views only), or
--   finals_only: 1 to 6s at Applecross. So the cost sits in the UNSCOPED ALL-SEASONS
--   read of v_effective_player_season_stats joined to players, which the dashboard
--   boards (no covered-innings detail needed) and the summary all share.
--
-- Reproduced on a throwaway Postgres 16 with the production views: commit 28d423f
-- (`ga.is_reserve IS TRUE OR g.ca_called_off IS TRUE` in the season view's reserve
-- LATERAL) stops the planner using ix_game_appearances_reserve; the probe becomes
-- "every game in the season, look for the player" (428,760 probes and 1.93M buffers
-- against 7,920 probes and 76k before). That made the all-seasons read 11x to 19x
-- slower there. It did NOT reproduce a club-to-club difference, so the questions
-- below are the ones only the real database can answer:
--
--   A. Is the live view the one with the OR?
--   B. Is Applecross's data the odd one out (season rows, reserves, called-off games)?
--   C. Are planner statistics fresh on the tables the view reads?
--   D. What plan does Applecross get, and does a small club get a different one?
--   E. Is JIT on for these queries (the records route turns it off, the boards do not)?
--   F. Is something else holding the box (long queries, locks)?
--
-- Run on the box (reads only; D runs the slow query for real, 45s or so, capped at 3 min):
--   cd /srv/docker && COMPOSE_PROJECT_NAME=bltbox_docker_app \
--     docker compose exec -T betterstats-db \
--     psql -U cricket -d betterstats -v big=applecross -v small=kalamunda-cricket-club \
--     -f - < ops/diagnostics/home_page_slow_boards.sql
-- Send back the whole output.

\timing on
SET statement_timeout = '180s';

\echo ''
\echo '=== A. which definition of the season view is live ==='
SELECT position('ca_called_off' IN pg_get_viewdef('v_effective_player_season_stats'::regclass)) > 0 AS view_reads_ca_called_off,
       position('LATERAL' IN pg_get_viewdef('v_effective_player_season_stats'::regclass)) > 0       AS view_has_reserve_lateral,
       position('ix_game_appearances_reserve' IN (SELECT string_agg(indexname, ',') FROM pg_indexes WHERE tablename = 'game_appearances')) > 0 AS reserve_index_exists;
SELECT indexname, indexdef FROM pg_indexes
 WHERE tablename IN ('game_appearances', 'games') AND (indexname ILIKE '%reserve%' OR indexname ILIKE '%called_off%' OR indexname ILIKE '%appearances_player%')
 ORDER BY 1;

\echo ''
\echo '=== B. size of each club in the view (the biggest first) ==='
SELECT o.slug,
       (SELECT count(*) FROM players p WHERE p.organisation_id = o.id) AS players,
       (SELECT count(*) FROM player_season_stats pss JOIN players p ON p.id = pss.player_id WHERE p.organisation_id = o.id) AS season_rows,
       (SELECT count(DISTINCT s.id) FROM seasons s WHERE s.organisation_id = o.id) AS seasons,
       (SELECT count(*) FROM game_appearances ga JOIN players p ON p.id = ga.player_id WHERE p.organisation_id = o.id) AS appearances,
       (SELECT count(*) FROM game_appearances ga JOIN players p ON p.id = ga.player_id WHERE p.organisation_id = o.id AND ga.is_reserve IS TRUE) AS reserve_appearances
  FROM organisations o
 ORDER BY season_rows DESC NULLS LAST
 LIMIT 8;
SELECT 'platform' AS scope, (SELECT count(*) FROM player_season_stats) AS season_rows,
       (SELECT count(*) FROM games WHERE ca_called_off IS TRUE) AS called_off_games,
       (SELECT count(*) FROM game_appearances WHERE is_reserve IS TRUE) AS reserve_appearances,
       (SELECT count(*) FROM games WHERE status IN ('ABANDONED', 'CANCELLED')) AS washout_games;

\echo ''
\echo '=== C. planner statistics freshness on the tables the view reads ==='
SELECT relname, n_live_tup, n_dead_tup, last_analyze, last_autoanalyze, last_autovacuum
  FROM pg_stat_user_tables
 WHERE relname IN ('player_season_stats', 'game_appearances', 'games', 'batting_innings', 'bowling_spells',
                   'fielding_stats', 'players', 'seasons', 'grades', 'manual_season_adjustments')
 ORDER BY relname;

\echo ''
\echo '=== E. settings that change these plans ==='
SELECT name, setting, unit FROM pg_settings
 WHERE name IN ('jit', 'jit_above_cost', 'work_mem', 'shared_buffers', 'effective_cache_size',
                'random_page_cost', 'max_parallel_workers_per_gather', 'default_statistics_target')
 ORDER BY name;

\echo ''
\echo '=== F. anything else running right now (over 2s) ==='
SELECT pid, state, wait_event_type, wait_event, now() - query_start AS running, left(query, 90) AS query
  FROM pg_stat_activity
 WHERE state <> 'idle' AND pid <> pg_backend_pid() AND now() - query_start > interval '2 seconds'
 ORDER BY query_start;

-- D. the summary query, exactly as get_club_summary runs it with no season and no scope.
\echo ''
\echo '=== D1. BIG club, JIT as the server has it (production default) ==='
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, TIMING OFF)
SELECT COUNT(DISTINCT pss.season_id) AS seasons, COUNT(DISTINCT pss.player_id) AS total_players,
       SUM(pss.runs) AS total_runs, SUM(pss.wickets) AS total_wickets, MAX(pss.high_score) AS highest_score
  FROM v_effective_player_season_stats pss
  JOIN players p ON p.id = pss.player_id
 WHERE p.organisation_id = (SELECT id FROM organisations WHERE slug = :'big');

\echo ''
\echo '=== D2. SMALL club, same query ==='
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, TIMING OFF)
SELECT COUNT(DISTINCT pss.season_id) AS seasons, COUNT(DISTINCT pss.player_id) AS total_players,
       SUM(pss.runs) AS total_runs, SUM(pss.wickets) AS total_wickets, MAX(pss.high_score) AS highest_score
  FROM v_effective_player_season_stats pss
  JOIN players p ON p.id = pss.player_id
 WHERE p.organisation_id = (SELECT id FROM organisations WHERE slug = :'small');

\echo ''
\echo '=== D3. BIG club with JIT off (is JIT a multiplier?) ==='
SET jit = off;
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, TIMING OFF)
SELECT COUNT(DISTINCT pss.season_id) AS seasons, COUNT(DISTINCT pss.player_id) AS total_players,
       SUM(pss.runs) AS total_runs, SUM(pss.wickets) AS total_wickets, MAX(pss.high_score) AS highest_score
  FROM v_effective_player_season_stats pss
  JOIN players p ON p.id = pss.player_id
 WHERE p.organisation_id = (SELECT id FROM organisations WHERE slug = :'big');
RESET jit;

\echo ''
\echo '=== D4. BIG club, season view narrowed to its own players up front (the shape rule 11 recommends) ==='
SET jit = off;
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, TIMING OFF)
SELECT COUNT(DISTINCT pss.season_id) AS seasons, COUNT(DISTINCT pss.player_id) AS total_players,
       SUM(pss.runs) AS total_runs, SUM(pss.wickets) AS total_wickets, MAX(pss.high_score) AS highest_score
  FROM v_effective_player_season_stats pss
 WHERE pss.player_id = ANY (ARRAY(SELECT p.id FROM players p
                                   WHERE p.organisation_id = (SELECT id FROM organisations WHERE slug = :'big')));
RESET jit;
