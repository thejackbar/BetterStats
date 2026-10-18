-- Faster versions of the Selection Whiteboard's heaviest statements, each run
-- NEXT TO the current one and compared row for row, so a faster answer that is
-- a different answer shows up as a non-zero "differs" count.
--
--   https://betterat.cricket/admin/betterselect/whiteboard?date=2026-10-24
--
-- Run on the box (club = part of the club name, day = the tab):
--   cd /srv/docker && export COMPOSE_PROJECT_NAME=bltbox_docker_app
--   git -C /srv/docker/betterstats fetch origin claude/vibrant-davinci-284b7i
--   git -C /srv/docker/betterstats show origin/claude/vibrant-davinci-284b7i:ops/diagnostics/whiteboard_optimised.sql \
--     | docker compose exec -T betterstats-db psql -U cricket -d betterstats \
--         -v club=Applecross -v day=2026-10-24 -f -
-- Optional: -v window_months=18  (default 24; how far back the first pass looks)
--
-- Reads only, apart from TEMP tables that vanish when the session ends.
--
-- What is and is not in here, from measuring both on a copy:
--   * Per-player lookups (LATERAL ... LIMIT 4) return the same rows but were 3 to
--     10 times SLOWER than today's window query. Not used.
--   * More work_mem barely helps (the sort spills to disk, but the cost is the
--     amount of history read, not the sort).
--   * Two-phase: read a recent window first, and only go back through the full
--     history for the players that window cannot answer. The answer is identical,
--     not approximate: a player with 4 or more qualifying innings inside the window
--     has the same last 4 as in the full history, because every row inside the
--     window is newer than every row outside it. BUT it only saves time when few
--     players need the full-history pass. Section 2 prints that count first. On my
--     test copy it was 4x faster when 16 of 1,500 players needed it, and no faster
--     (slower for bowling and last played) when 1,300 of 1,500 did, which is what a
--     club with many historic names looks like. Trust the printed count and times
--     for this club, not mine.
--   * Lineups (section 1) are a plain win: the overview reads 3,300 rows instead of
--     109,000, about 4x faster on my copy, same rows out.
--   * The availability read in the overview (A6) is cheap in the database, and a
--     version filtered to lineup players measured SLOWER, so it is left alone.
--   * The other big saving is not SQL: the statements marked B* in
--     whiteboard_current.sql do not depend on the team, yet run once per team.
--     Run once per page they cost 1/teams as much. The times below are for ONE run.

\set ON_ERROR_STOP off
\pset pager off
\pset footer off
\timing off
\if :{?window_months}
\else
  \set window_months 24
\endif

\echo ''
\echo '=== setup (not part of the page cost) ==='
SELECT id AS org, name AS org_name FROM organisations WHERE name ILIKE '%' || :'club' || '%' ORDER BY name LIMIT 1 \gset
\echo 'Club:' :org_name '(' :org ')'
SELECT (current_date - make_interval(months => :window_months))::date AS wstart \gset
\echo 'First pass looks back' :window_months 'months, to' :wstart
SELECT count(*) AS n_teams FROM fixtures
 WHERE organisation_id = :'org' AND status <> 'CANCELLED'
   AND (played_on = :'day'::date OR (end_on > played_on AND end_on = :'day'::date)) \gset
\echo 'Teams on' :day ':' :n_teams

-- Ids bound as arrays, so the planner can use them directly (see CLAUDE.md rule 11).
-- (\gset leaves a variable unset on NULL, so each value is coalesced.)
SELECT COALESCE(array_agg(id)::text, '{}') AS fids, count(*) AS n_upcoming FROM fixtures
 WHERE organisation_id = :'org' AND status <> 'CANCELLED'
   AND (played_on >= current_date OR end_on >= current_date) \gset
SELECT COALESCE(array_agg(DISTINCT d)::text, '{}') AS fdates FROM (
  SELECT played_on AS d FROM fixtures WHERE id = ANY(CAST(:'fids' AS uuid[]))
  UNION SELECT end_on FROM fixtures WHERE id = ANY(CAST(:'fids' AS uuid[])) AND end_on > played_on) x
 WHERE d IS NOT NULL \gset
SELECT COALESCE(min(played_on)::text, '') AS lo, COALESCE(max(COALESCE(end_on, played_on))::text, '') AS hi
  FROM fixtures WHERE id = ANY(CAST(:'fids' AS uuid[])) \gset
\echo 'Upcoming fixtures:' :n_upcoming '  dates' :lo 'to' :hi

\timing on

-- ===========================================================================
\echo ''
\echo '################ 1. overview: lineups (was A5) ################'
\echo '--- current: every lineup the club has ever named'
CREATE TEMP TABLE cur_lineups AS
  SELECT fl.fixture_id, fl.batting_order, fl.is_captain, fl.is_wicket_keeper,
         COALESCE(p.display_name_override, p.name) AS name, p.id AS player_id, p.skill_positions
    FROM fixture_lineups fl JOIN players p ON fl.player_id = p.id
   WHERE fl.organisation_id = :'org';
\echo '--- faster: only the fixtures the overview is about to show'
CREATE TEMP TABLE new_lineups AS
  SELECT fl.fixture_id, fl.batting_order, fl.is_captain, fl.is_wicket_keeper,
         COALESCE(p.display_name_override, p.name) AS name, p.id AS player_id, p.skill_positions
    FROM fixture_lineups fl JOIN players p ON fl.player_id = p.id
   WHERE fl.organisation_id = :'org'
     AND fl.fixture_id = ANY(CAST(:'fids' AS uuid[]));
\timing off
SELECT (SELECT count(*) FROM cur_lineups) AS cur_rows_read,
       (SELECT count(*) FROM new_lineups) AS new_rows_read,
       (SELECT count(*) FROM (
          SELECT fixture_id, player_id, batting_order FROM cur_lineups WHERE fixture_id = ANY(CAST(:'fids' AS uuid[]))
          EXCEPT SELECT fixture_id, player_id, batting_order FROM new_lineups) a)
       + (SELECT count(*) FROM (
          SELECT fixture_id, player_id, batting_order FROM new_lineups
          EXCEPT SELECT fixture_id, player_id, batting_order FROM cur_lineups) b) AS differs;
\timing on

-- ===========================================================================
\echo ''
\echo '################ 2. per team, but the same for every team (B2, B14, B15) ################'
\echo 'Players with fewer than 4 qualifying results inside the window need the full-history'
\echo 'pass. Fewer is better: this is the number that decides how much two-phase saves.'
SELECT count(*) AS club_players,
       count(*) FILTER (WHERE COALESCE(b.n, 0) < 4) AS need_full_history_batting,
       count(*) FILTER (WHERE COALESCE(w.n, 0) < 4) AS need_full_history_bowling,
       count(*) FILTER (WHERE l.n IS NULL)          AS need_full_history_last_played
  FROM players p
  LEFT JOIN (SELECT ba.player_id, count(*) AS n FROM batting_innings ba JOIN games g ON g.id = ba.game_id
              WHERE g.played_at >= :'wstart'::date AND COALESCE(ba.did_not_bat, false) = false
                AND (ba.dismissal_type IS NULL OR LOWER(ba.dismissal_type) NOT IN ('absent', 'did not bat', 'dnb'))
              GROUP BY ba.player_id) b ON b.player_id = p.id
  LEFT JOIN (SELECT bs.player_id, count(*) AS n FROM bowling_spells bs JOIN games g ON g.id = bs.game_id
              WHERE g.played_at >= :'wstart'::date GROUP BY bs.player_id) w ON w.player_id = p.id
  LEFT JOIN (SELECT ga.player_id, count(*) AS n FROM game_appearances ga JOIN games g ON g.id = ga.game_id
              WHERE g.played_at >= :'wstart'::date GROUP BY ga.player_id) l ON l.player_id = p.id
 WHERE p.organisation_id = :'org';

\echo ''
\echo '--- B14 recent batting form, current'
CREATE TEMP TABLE cur_bat AS
  WITH ranked AS (
    SELECT ba.player_id, COALESCE(ba.runs, 0) AS runs,
           ROW_NUMBER() OVER (PARTITION BY ba.player_id ORDER BY g.played_at DESC NULLS LAST) AS rn
      FROM batting_innings ba JOIN games g ON ba.game_id = g.id JOIN players p ON ba.player_id = p.id
     WHERE p.organisation_id = :'org' AND COALESCE(ba.did_not_bat, false) = false
       AND (ba.dismissal_type IS NULL OR LOWER(ba.dismissal_type) NOT IN ('absent', 'did not bat', 'dnb'))
       AND g.played_at IS NOT NULL)
  SELECT player_id, SUM(runs)::float AS total_runs, COUNT(*)::int AS innings, array_agg(runs ORDER BY rn DESC) AS series
    FROM ranked WHERE rn <= 4 GROUP BY player_id;

\echo '--- B14 recent batting form, two-phase (same answer)'
CREATE TEMP TABLE new_bat AS
  WITH recent AS (
    SELECT player_id, SUM(runs)::float AS total_runs, COUNT(*)::int AS innings, array_agg(runs ORDER BY rn DESC) AS series
      FROM (SELECT ba.player_id, COALESCE(ba.runs, 0) AS runs,
                   ROW_NUMBER() OVER (PARTITION BY ba.player_id ORDER BY g.played_at DESC) AS rn
              FROM batting_innings ba JOIN games g ON ba.game_id = g.id JOIN players p ON ba.player_id = p.id
             WHERE p.organisation_id = :'org' AND g.played_at >= :'wstart'::date
               AND COALESCE(ba.did_not_bat, false) = false
               AND (ba.dismissal_type IS NULL OR LOWER(ba.dismissal_type) NOT IN ('absent', 'did not bat', 'dnb'))) r
     WHERE rn <= 4 GROUP BY player_id),
  short AS (
    SELECT p.id FROM players p LEFT JOIN recent r ON r.player_id = p.id
     WHERE p.organisation_id = :'org' AND COALESCE(r.innings, 0) < 4),
  older AS (
    SELECT player_id, SUM(runs)::float AS total_runs, COUNT(*)::int AS innings, array_agg(runs ORDER BY rn DESC) AS series
      FROM (SELECT ba.player_id, COALESCE(ba.runs, 0) AS runs,
                   ROW_NUMBER() OVER (PARTITION BY ba.player_id ORDER BY g.played_at DESC) AS rn
              FROM batting_innings ba JOIN games g ON ba.game_id = g.id
             WHERE ba.player_id = ANY(ARRAY(SELECT id FROM short)) AND g.played_at IS NOT NULL
               AND COALESCE(ba.did_not_bat, false) = false
               AND (ba.dismissal_type IS NULL OR LOWER(ba.dismissal_type) NOT IN ('absent', 'did not bat', 'dnb'))) r
     WHERE rn <= 4 GROUP BY player_id)
  SELECT * FROM recent WHERE player_id NOT IN (SELECT id FROM short)
  UNION ALL SELECT * FROM older;
\timing off
SELECT (SELECT count(*) FROM cur_bat) AS cur_players, (SELECT count(*) FROM new_bat) AS new_players,
       (SELECT count(*) FROM (SELECT * FROM cur_bat EXCEPT SELECT * FROM new_bat) a)
     + (SELECT count(*) FROM (SELECT * FROM new_bat EXCEPT SELECT * FROM cur_bat) b) AS differs;
\timing on

\echo ''
\echo '--- B15 recent bowling form, current'
CREATE TEMP TABLE cur_bowl AS
  WITH ranked AS (
    SELECT bs.player_id, COALESCE(bs.wickets, 0) AS wickets,
           ROW_NUMBER() OVER (PARTITION BY bs.player_id ORDER BY g.played_at DESC NULLS LAST) AS rn
      FROM bowling_spells bs JOIN games g ON bs.game_id = g.id JOIN players p ON bs.player_id = p.id
     WHERE p.organisation_id = :'org' AND g.played_at IS NOT NULL)
  SELECT player_id, SUM(wickets)::float AS total_wickets, COUNT(*)::int AS innings, array_agg(wickets ORDER BY rn DESC) AS series
    FROM ranked WHERE rn <= 4 GROUP BY player_id;

\echo '--- B15 recent bowling form, two-phase (same answer)'
CREATE TEMP TABLE new_bowl AS
  WITH recent AS (
    SELECT player_id, SUM(wickets)::float AS total_wickets, COUNT(*)::int AS innings, array_agg(wickets ORDER BY rn DESC) AS series
      FROM (SELECT bs.player_id, COALESCE(bs.wickets, 0) AS wickets,
                   ROW_NUMBER() OVER (PARTITION BY bs.player_id ORDER BY g.played_at DESC) AS rn
              FROM bowling_spells bs JOIN games g ON bs.game_id = g.id JOIN players p ON bs.player_id = p.id
             WHERE p.organisation_id = :'org' AND g.played_at >= :'wstart'::date) r
     WHERE rn <= 4 GROUP BY player_id),
  short AS (
    SELECT p.id FROM players p LEFT JOIN recent r ON r.player_id = p.id
     WHERE p.organisation_id = :'org' AND COALESCE(r.innings, 0) < 4),
  older AS (
    SELECT player_id, SUM(wickets)::float AS total_wickets, COUNT(*)::int AS innings, array_agg(wickets ORDER BY rn DESC) AS series
      FROM (SELECT bs.player_id, COALESCE(bs.wickets, 0) AS wickets,
                   ROW_NUMBER() OVER (PARTITION BY bs.player_id ORDER BY g.played_at DESC) AS rn
              FROM bowling_spells bs JOIN games g ON bs.game_id = g.id
             WHERE bs.player_id = ANY(ARRAY(SELECT id FROM short)) AND g.played_at IS NOT NULL) r
     WHERE rn <= 4 GROUP BY player_id)
  SELECT * FROM recent WHERE player_id NOT IN (SELECT id FROM short)
  UNION ALL SELECT * FROM older;
\timing off
SELECT (SELECT count(*) FROM cur_bowl) AS cur_players, (SELECT count(*) FROM new_bowl) AS new_players,
       (SELECT count(*) FROM (SELECT * FROM cur_bowl EXCEPT SELECT * FROM new_bowl) a)
     + (SELECT count(*) FROM (SELECT * FROM new_bowl EXCEPT SELECT * FROM cur_bowl) b) AS differs;
\timing on

\echo ''
\echo '--- B2 last played, current'
CREATE TEMP TABLE cur_lp AS
  SELECT ga.player_id, MAX(g.played_at) AS last_played
    FROM game_appearances ga JOIN games g ON ga.game_id = g.id JOIN players p ON ga.player_id = p.id
   WHERE p.organisation_id = :'org' GROUP BY ga.player_id;

\echo '--- B2 last played, two-phase (same answer)'
CREATE TEMP TABLE new_lp AS
  WITH recent AS (
    SELECT ga.player_id, MAX(g.played_at) AS last_played
      FROM game_appearances ga JOIN games g ON ga.game_id = g.id JOIN players p ON ga.player_id = p.id
     WHERE p.organisation_id = :'org' AND g.played_at >= :'wstart'::date GROUP BY ga.player_id),
  older AS (
    SELECT ga.player_id, MAX(g.played_at) AS last_played
      FROM game_appearances ga JOIN games g ON ga.game_id = g.id
     WHERE ga.player_id = ANY(ARRAY(SELECT p.id FROM players p LEFT JOIN recent r ON r.player_id = p.id
                                     WHERE p.organisation_id = :'org' AND r.player_id IS NULL))
     GROUP BY ga.player_id)
  SELECT * FROM recent UNION ALL SELECT * FROM older;
\timing off
SELECT (SELECT count(*) FROM cur_lp) AS cur_players, (SELECT count(*) FROM new_lp) AS new_players,
       (SELECT count(*) FROM (SELECT * FROM cur_lp EXCEPT SELECT * FROM new_lp) a)
     + (SELECT count(*) FROM (SELECT * FROM new_lp EXCEPT SELECT * FROM cur_lp) b) AS differs;
\timing on

-- ===========================================================================
\echo ''
\echo '################ 3. what one page load saves ################'
\echo 'Today: B2 + B14 + B15 run once per team. With one run per page they run once.'
\echo 'Teams on the day:' :n_teams '. Multiply the "current" times above by that, against'
\echo 'one "two-phase" time, to see the difference for this club.'

\timing off
DROP TABLE IF EXISTS cur_lineups, new_lineups, cur_bat, new_bat, cur_bowl, new_bowl, cur_lp, new_lp;
