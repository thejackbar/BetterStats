-- Every SQL statement the Selection Whiteboard runs to open one day, as the
-- code runs them today, each timed on its own.
--
--   https://betterat.cricket/admin/betterselect/whiteboard?date=2026-10-24
--
-- Run on the box (club = part of the club name, day = the tab):
--   cd /srv/docker && export COMPOSE_PROJECT_NAME=bltbox_docker_app
--   git -C /srv/docker/betterstats fetch origin claude/vibrant-davinci-284b7i
--   git -C /srv/docker/betterstats show origin/claude/vibrant-davinci-284b7i:ops/diagnostics/whiteboard_current.sql \
--     | docker compose exec -T betterstats-db psql -U cricket -d betterstats \
--         -v club=Applecross -v day=2026-10-24 -f -
--
-- Reads only. Nothing here writes, locks or analyses.
--
-- How the page loads, and what the labels mean:
--   A  = once per page load           (GET /selection/overview)
--   B  = once PER TEAM on the day     (GET /selection/{fixture}, assemble_selection)
--   B* = the per-team statements that read the same club-wide data for every team.
--        They are the ones to multiply by the team count printed below.
-- The page also calls GET /selection/{fixture}/draft once per team (statement C).
-- B is timed here for ONE representative team: the page runs it for all of them
-- at the same time, so the page cost is roughly B x teams, and the teams compete
-- for the same database.
--
-- Each statement is wrapped in SELECT count(*) so psql prints its time and row
-- count, not its rows. The wrapper adds nothing the real statement does not do
-- (the same plan runs; only the row transfer is skipped).

\set ON_ERROR_STOP off
\pset pager off
\pset footer off
\timing off

\echo ''
\echo '=== setup: who, which day, which teams (not part of the page cost) ==='
SELECT id AS org, name AS org_name FROM organisations WHERE name ILIKE '%' || :'club' || '%' ORDER BY name LIMIT 1 \gset
\echo 'Club:' :org_name '(' :org ')'

-- A club that set its own dormancy window; blank falls back to 24 months.
SELECT COALESCE((SELECT NULLIF(dormancy_months, 0) FROM organisations WHERE id = :'org'), 24) AS dorm_months \gset
SELECT (current_date - make_interval(months => :dorm_months))::date AS cutoff,
       (current_date - make_interval(months => 12))::date           AS autofill_cutoff \gset

-- The teams on the tab: a game shows on its first day and, if two-day, its second.
SELECT count(*) AS n_teams FROM fixtures
 WHERE organisation_id = :'org' AND status <> 'CANCELLED'
   AND (played_on = :'day'::date OR (end_on > played_on AND end_on = :'day'::date)) \gset
\echo 'Teams on' :day ':' :n_teams

-- One representative team (the first by start time), and the days it is played on.
SELECT id AS fid, COALESCE(grade_id::text, '') AS fgrade, COALESCE(team_id::text, '') AS fteam, played_on AS fplayed,
       ('{' || concat_ws(',', played_on, CASE WHEN end_on > played_on THEN end_on END) || '}') AS fdays
  FROM fixtures
 WHERE organisation_id = :'org' AND status <> 'CANCELLED'
   AND (played_on = :'day'::date OR (end_on > played_on AND end_on = :'day'::date))
 ORDER BY played_on, start_time NULLS LAST, id LIMIT 1 \gset
\echo 'Representative fixture:' :fid 'days' :fdays

-- The date window the overview reads availability over: every upcoming game.
SELECT min(played_on) AS lo, max(COALESCE(end_on, played_on)) AS hi, count(*) AS n_upcoming
  FROM fixtures
 WHERE organisation_id = :'org' AND status <> 'CANCELLED'
   AND (played_on >= current_date OR end_on >= current_date) \gset
\echo 'Overview covers' :n_upcoming 'upcoming fixtures,' :lo 'to' :hi

-- (\gset leaves a variable unset on NULL, so every value below is coalesced to text)
SELECT COALESCE((SELECT season_id::text FROM grades WHERE id = NULLIF(:'fgrade', '')::uuid), '') AS fseason \gset
SELECT COALESCE((SELECT id::text FROM seasons WHERE organisation_id = :'org'
 ORDER BY year DESC NULLS LAST, name DESC LIMIT 1), '') AS lseason \gset

\echo ''
\echo '=== how big the tables behind it are, and the indexes they carry ==='
SELECT relname, n_live_tup AS approx_rows, pg_size_pretty(pg_total_relation_size(relid)) AS total_size
  FROM pg_stat_user_tables
 WHERE relname IN ('game_appearances', 'batting_innings', 'bowling_spells', 'player_season_stats',
                   'games', 'players', 'fixture_lineups', 'player_availability',
                   'player_availability_periods', 'selection_drafts')
 ORDER BY n_live_tup DESC;
SELECT tablename, indexname FROM pg_indexes
 WHERE schemaname = 'public'
   AND tablename IN ('game_appearances', 'batting_innings', 'bowling_spells', 'player_season_stats',
                     'games', 'fixture_lineups', 'player_availability')
 ORDER BY tablename, indexname;
SELECT count(*) AS club_players, count(*) FILTER (WHERE is_player) AS is_player_true
  FROM players WHERE organisation_id = :'org';

\timing on

\echo ''
\echo '################ A. once per page load: GET /selection/overview ################'

\echo ''
\echo '--- A1 upcoming fixtures'
SELECT count(*) AS rows FROM (
  SELECT * FROM fixtures
   WHERE organisation_id = :'org'
     AND (played_on >= current_date OR end_on >= current_date)
     AND status <> 'CANCELLED'
   ORDER BY played_on ASC NULLS LAST, start_time ASC NULLS LAST) q;

\echo '--- A2 teams'
SELECT count(*) AS rows FROM (SELECT * FROM teams WHERE organisation_id = :'org') q;

\echo '--- A3 squad sides: teams + grades, every grade of every season, team_sides'
SELECT count(*) AS rows FROM (
  SELECT t.id, t.name, t.short_name, COALESCE(t.sequence, 0), t.grade_id,
         COALESCE(t.is_active, true), COALESCE(gr.display_name_override, gr.name)
    FROM teams t LEFT JOIN grades gr ON gr.id = t.grade_id
   WHERE t.organisation_id = :'org') q;
SELECT count(*) AS rows FROM (
  SELECT gr.id, gr.name FROM grades gr JOIN seasons s ON s.id = gr.season_id
   WHERE s.organisation_id = :'org' ORDER BY s.year DESC NULLS LAST, s.name DESC) q;
SELECT count(*) AS rows FROM (
  SELECT team_id, grade_key, grade_name, label, position FROM team_sides
   WHERE organisation_id = :'org' ORDER BY team_id, position, grade_name) q;

\echo '--- A4 grade names for the upcoming fixtures'
SELECT count(*) AS rows FROM (
  SELECT id, display_name_override, name FROM grades
   WHERE id IN (SELECT grade_id FROM fixtures WHERE organisation_id = :'org'
                  AND (played_on >= current_date OR end_on >= current_date) AND status <> 'CANCELLED')) q;

\echo '--- A5 LINEUPS: no fixture filter, so it reads every lineup the club has ever named'
SELECT count(*) AS rows FROM (
  SELECT fl.fixture_id, fl.batting_order, fl.is_captain, fl.is_wicket_keeper,
         COALESCE(p.display_name_override, p.name), p.id, p.skill_positions
    FROM fixture_lineups fl JOIN players p ON fl.player_id = p.id
   WHERE fl.organisation_id = :'org'
   ORDER BY fl.batting_order ASC NULLS LAST) q;

\echo '--- A6 AVAILABILITY: every answer from the first to the last upcoming date (the whole remaining season)'
SELECT count(*) AS rows FROM (
  SELECT player_id, avail_date, status FROM player_availability
   WHERE organisation_id = :'org' AND avail_date BETWEEN :'lo'::date AND :'hi'::date) q;

\echo '--- A7 availability periods overlapping that same window'
SELECT count(*) AS rows FROM (
  SELECT * FROM player_availability_periods
   WHERE organisation_id = :'org' AND start_date <= :'hi'::date
     AND (end_date IS NULL OR end_date >= :'lo'::date)
   ORDER BY start_date ASC, created_at ASC) q;

\echo '--- A8 which upcoming fixtures have an unconfirmed draft'
SELECT count(*) AS rows FROM (
  SELECT fixture_id, updated_at FROM selection_drafts
   WHERE organisation_id = :'org'
     AND fixture_id = ANY(CAST((SELECT array_agg(id)::text FROM fixtures
          WHERE organisation_id = :'org' AND (played_on >= current_date OR end_on >= current_date)
            AND status <> 'CANCELLED') AS uuid[]))) q;

\echo ''
\echo '################ B. once PER TEAM: GET /selection/{fixture}  (x teams on the day) ################'

\echo ''
\echo '--- B1 this fixture''s lineup'
SELECT count(*) AS rows FROM (SELECT * FROM fixture_lineups WHERE fixture_id = :'fid') q;

\echo '--- B2* LAST PLAYED: max game date per player, over the club''s whole appearance history'
SELECT count(*) AS rows FROM (
  SELECT ga.player_id, MAX(g.played_at)
    FROM game_appearances ga
    JOIN games g ON ga.game_id = g.id
    JOIN players p ON ga.player_id = p.id
   WHERE p.organisation_id = :'org'
   GROUP BY ga.player_id) q;

\echo '--- B3 the club''s live squads'
SELECT count(*) AS rows FROM (
  SELECT id, name, COALESCE(sequence, 0) FROM teams
   WHERE organisation_id = :'org' AND is_active IS NOT FALSE AND name IS NOT NULL AND name <> '') q;

\echo '--- B4* SQUAD NAMES from recent appearances'
SELECT count(*) AS rows FROM (
  SELECT DISTINCT ga.player_id, ga.team_name
    FROM game_appearances ga
    JOIN games g ON ga.game_id = g.id
    JOIN players p ON ga.player_id = p.id
   WHERE p.organisation_id = :'org' AND ga.team_name IS NOT NULL
     AND ga.team_name <> '' AND g.played_at >= :'cutoff'::date) q;

\echo '--- B5 squad memberships'
SELECT count(*) AS rows FROM (
  SELECT player_id, team_id FROM team_members WHERE organisation_id = :'org') q;

\echo '--- B6 availability on this fixture''s day(s)'
SELECT count(*) AS rows FROM (
  SELECT player_id, avail_date, status FROM player_availability
   WHERE organisation_id = :'org' AND avail_date = ANY(CAST(:'fdays' AS date[]))) q;

\echo '--- B7 availability periods around this fixture'
SELECT count(*) AS rows FROM (
  SELECT * FROM player_availability_periods
   WHERE organisation_id = :'org'
     AND start_date <= (:'fdays'::date[])[array_upper(:'fdays'::date[], 1)]
     AND (end_date IS NULL OR end_date >= (:'fdays'::date[])[1])
   ORDER BY start_date ASC, created_at ASC) q;

\echo '--- B8 players already picked in another side the same day'
SELECT count(*) AS rows FROM (
  SELECT fl.player_id, COALESCE(t.name, f.label, f.opponent_name) AS where_, t.sequence AS seq,
         fl.fixture_id AS fid, fl.batting_order AS bo, f.team_id AS tid, f.grade_id AS gid, f.side_key AS skey
    FROM fixture_lineups fl
    JOIN fixtures f ON fl.fixture_id = f.id
    LEFT JOIN teams t ON f.team_id = t.id
   WHERE fl.organisation_id = :'org' AND f.id <> :'fid'
     AND (f.played_on = ANY(CAST(:'fdays' AS date[]))
          OR (f.end_on IS NOT NULL AND f.end_on > f.played_on AND f.end_on = ANY(CAST(:'fdays' AS date[]))))) q;

\echo '--- B9 players in another side''s unconfirmed draft the same day'
SELECT count(*) AS rows FROM (
  SELECT x.pid, COALESCE(t.short_name, t.name, f.label, f.opponent_name)
    FROM selection_drafts d
    JOIN fixtures f ON f.id = d.fixture_id
    LEFT JOIN teams t ON t.id = f.team_id
    CROSS JOIN LATERAL jsonb_array_elements_text(
      CASE WHEN jsonb_typeof(d.draft->'slots') = 'array' THEN d.draft->'slots' ELSE '[]'::jsonb END) AS x(pid)
   WHERE d.organisation_id = :'org'
     AND (f.played_on = ANY(CAST(:'fdays' AS date[]))
          OR (f.end_on IS NOT NULL AND f.end_on > f.played_on AND f.end_on = ANY(CAST(:'fdays' AS date[]))))
     AND f.id <> :'fid' AND x.pid IS NOT NULL) q;

\echo '--- B10 THE ROSTER: every player the club has marked is_player (all historic names, once per team)'
SELECT count(*) AS rows FROM (
  SELECT * FROM players WHERE organisation_id = :'org' AND is_player IS TRUE) q;

\echo '--- B11 this fixture''s team and grade, and every team''s grade'
SELECT count(*) AS rows FROM (SELECT * FROM teams WHERE id = NULLIF(:'fteam', '')::uuid) q;
SELECT count(*) AS rows FROM (SELECT * FROM grades WHERE id = NULLIF(:'fgrade', '')::uuid) q;
SELECT count(*) AS rows FROM (
  SELECT t.id, t.sequence, gr.fee_format, t.short_name, t.name, gr.name
    FROM teams t LEFT JOIN grades gr ON t.grade_id = gr.id
   WHERE t.organisation_id = :'org') q;

\echo '--- B12* WHO OWES (BetterFees balance): latest season, then the Accounts calculation''s four reads'
SELECT count(*) AS rows FROM (
  SELECT id FROM seasons WHERE organisation_id = :'org'
   ORDER BY year DESC NULLS LAST, name DESC LIMIT 1) q;
SELECT count(*) AS rows FROM (
  SELECT fms.*, fm.*, fs.*
    FROM fee_member_seasons fms
    JOIN fee_members fm ON fms.member_id = fm.id
    LEFT JOIN fee_schedule fs ON fms.fee_schedule_id = fs.id
   WHERE fms.season_id = NULLIF(:'lseason', '')::uuid) q;
SELECT count(*) AS rows FROM (
  SELECT md.member_season_id, COALESCE(SUM(md.days_played), 0)
    FROM fee_match_days md JOIN fee_member_seasons fms ON md.member_season_id = fms.id
   WHERE fms.season_id = NULLIF(:'lseason', '')::uuid GROUP BY md.member_season_id) q;
SELECT count(*) AS rows FROM (
  SELECT md.member_season_id, COALESCE(SUM(md.days_played), 0)
    FROM fee_match_days md JOIN fee_member_seasons fms ON md.member_season_id = fms.id
   WHERE fms.season_id = NULLIF(:'lseason', '')::uuid AND md.waived_at IS NOT NULL GROUP BY md.member_season_id) q;
SELECT count(*) AS rows FROM (
  SELECT pay.member_season_id, pay.kind, COALESCE(SUM(pay.amount), 0)
    FROM fee_payments pay JOIN fee_member_seasons fms ON pay.member_season_id = fms.id
   WHERE fms.season_id = NULLIF(:'lseason', '')::uuid GROUP BY pay.member_season_id, pay.kind) q;

\echo '--- B13* NETS: who trained in the last 21 days, and whether any session ran'
SELECT count(*) AS rows FROM (
  SELECT DISTINCT na.player_id FROM net_attendance na
    JOIN net_sessions ns ON ns.id = na.session_id
   WHERE na.organisation_id = :'org' AND na.player_id IS NOT NULL
     AND ns.session_date <= :'fplayed'::date AND ns.session_date >= :'fplayed'::date - 21) q;
SELECT count(*) AS rows FROM (
  SELECT 1 FROM net_sessions WHERE organisation_id = :'org'
     AND session_date <= :'fplayed'::date AND session_date >= :'fplayed'::date - 21 LIMIT 1) q;

\echo '--- B14* RECENT BATTING FORM: ranks every innings the club has ever recorded, keeps the last 4 each'
SELECT count(*) AS rows FROM (
  WITH ranked AS (
    SELECT ba.player_id, COALESCE(ba.runs, 0) AS runs,
           ROW_NUMBER() OVER (PARTITION BY ba.player_id ORDER BY g.played_at DESC NULLS LAST) AS rn
      FROM batting_innings ba
      JOIN games g ON ba.game_id = g.id
      JOIN players p ON ba.player_id = p.id
     WHERE p.organisation_id = :'org'
       AND COALESCE(ba.did_not_bat, false) = false
       AND (ba.dismissal_type IS NULL OR LOWER(ba.dismissal_type) NOT IN ('absent', 'did not bat', 'dnb'))
       AND g.played_at IS NOT NULL)
  SELECT player_id, SUM(runs)::float AS total_runs, COUNT(*)::int AS innings,
         array_agg(runs ORDER BY rn DESC) AS series
    FROM ranked WHERE rn <= 4 GROUP BY player_id) q;

\echo '--- B15* RECENT BOWLING FORM: the same, over every spell'
SELECT count(*) AS rows FROM (
  WITH ranked AS (
    SELECT bs.player_id, COALESCE(bs.wickets, 0) AS wickets,
           ROW_NUMBER() OVER (PARTITION BY bs.player_id ORDER BY g.played_at DESC NULLS LAST) AS rn
      FROM bowling_spells bs
      JOIN games g ON bs.game_id = g.id
      JOIN players p ON bs.player_id = p.id
     WHERE p.organisation_id = :'org' AND g.played_at IS NOT NULL)
  SELECT player_id, SUM(wickets)::float AS total_wickets, COUNT(*)::int AS innings,
         array_agg(wickets ORDER BY rn DESC) AS series
    FROM ranked WHERE rn <= 4 GROUP BY player_id) q;

\echo '--- B16* LATEST SEASON STATS per player'
SELECT count(*) AS rows FROM (
  SELECT DISTINCT ON (pss.player_id) pss.player_id, pss.batting_average, pss.runs,
         pss.batting_innings, pss.wickets, pss.bowling_innings
    FROM player_season_stats pss
    JOIN seasons s ON pss.season_id = s.id
    JOIN players p ON pss.player_id = p.id
   WHERE p.organisation_id = :'org' AND s.organisation_id = :'org'
   ORDER BY pss.player_id, s.year DESC NULLS LAST) q;

\echo '--- B17 REGISTRATION ticks for the fixture''s season'
SELECT count(*) AS rows FROM (SELECT season_id FROM grades WHERE id = NULLIF(:'fgrade', '')::uuid) q;
SELECT count(*) AS rows FROM (
  SELECT fm.player_id, fms.playhq_registered
    FROM fee_member_seasons fms JOIN fee_members fm ON fm.id = fms.member_id
   WHERE fm.organisation_id = :'org' AND fms.season_id = COALESCE(NULLIF(:'fseason', ''), NULLIF(:'lseason', ''))::uuid
     AND fm.player_id IS NOT NULL) q;

\echo '--- B18 the club''s selection rules and per-player exceptions'
SELECT count(*) AS rows FROM (
  SELECT id, kind, name, enabled, severity, scope, config, position FROM selection_rules
   WHERE organisation_id = :'org' AND enabled ORDER BY position, created_at) q;
SELECT count(*) AS rows FROM (
  SELECT rule_id, player_id, state, note FROM selection_rule_players WHERE organisation_id = :'org') q;

\echo ''
\echo '################ C. once PER TEAM: GET /selection/{fixture}/draft ################'
SELECT count(*) AS rows FROM (
  SELECT d.draft, d.updated_at, COALESCE(u.display_name, u.username), d.version
    FROM selection_drafts d LEFT JOIN users u ON u.id = d.updated_by
   WHERE d.fixture_id = :'fid' AND d.organisation_id = :'org') q;

\timing off
\echo ''
\echo 'Read the times: a B statement is paid once per team. Teams on the day:' :n_teams
