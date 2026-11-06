-- Which sources add up to a player's season, and which typed games have a PlayHQ
-- twin they are not paired with. READ ONLY, one club, one or more players.
--
-- Hamilton Veterans (Oct 2026): across 6 sample players, 26 player-seasons read EXACTLY
-- double (games, innings, runs, overs, wickets) and 15 more read extra games with the
-- innings and runs right. The doubled seasons are the ones where Cricket Australia
-- (PlayHQ) holds a season total AND the club typed the same games in. A season row
-- is the SUM of every source row of v_effective_player_season_stats:
--
--   api            Cricket Australia's season total. No per-match granularity, so a
--                  typed game cannot step it aside. Off for a season the club has
--                  re-sourced (seasons.import_authoritative).
--   manual_game    the club's typed games, rolled up. A game paired to a synced one
--                  counts here only when it is the preferred half AND the season is
--                  re-sourced.
--   manual_aggregate / manual_career / import   adjustments and imported totals.
--   api_scorecard  synced games of a re-sourced season, from their own scorecards.
--
-- So a season that shows BOTH an `api` row and a `manual_game` row with runs in it, and
-- is not re-sourced, is counted twice. Section 1 shows that per season. Section 2 lists
-- the typed games in those seasons that share a date with a synced game of the club and
-- are not paired to it: the twins.
--
-- Run on the box:
--   cd /srv/docker && COMPOSE_PROJECT_NAME=bltbox_docker_app \
--     docker compose exec -T betterstats-db \
--     psql -U cricket -d betterstats -v club="'%Hamilton Veterans%'" -v who="'%Baker%'" \
--     -f - < /srv/docker/betterstats/ops/diagnostics/season_sources_by_player.sql
--
-- `who` is an ILIKE pattern on the player's name; use '%' for every player of the club.
-- Reads only. Nothing here writes.

\set ON_ERROR_STOP on
SET jit = off;

CREATE TEMP TABLE _p AS
SELECT p.id AS player_id, p.organisation_id AS org_id,
       COALESCE(p.display_name_override, p.name) AS name
  FROM players p
  JOIN organisations o ON o.id = p.organisation_id
 WHERE o.name ILIKE :club
   AND COALESCE(p.display_name_override, p.name) ILIKE :who;

\echo ''
\echo '=== 0. the players read (more than one row per person means two records: merge them first) ==='
SELECT * FROM _p ORDER BY name;

\echo ''
\echo '=== 1. every source row behind each season, newest first ==='
\echo '    flag DOUBLE = an api row and a manual_game row both hold runs, season not re-sourced'
SELECT p.name, s.name AS season, s.import_authoritative AS resourced,
       v.source, v.matches, v.batting_innings AS inns, v.runs,
       v.bowling_innings AS bowl, v.overs, v.wickets,
       CASE WHEN bool_or(v.source = 'api' AND v.runs > 0)
                 OVER w
             AND bool_or(v.source = 'manual_game' AND v.runs > 0) OVER w
             AND NOT s.import_authoritative
            THEN 'DOUBLE' ELSE '' END AS flag
  FROM _p p
  JOIN v_effective_player_season_stats v ON v.player_id = p.player_id
  LEFT JOIN seasons s ON s.id = v.season_id
WINDOW w AS (PARTITION BY p.player_id, v.season_id)
 ORDER BY p.name, s.year DESC NULLS LAST, s.name, v.source;

\echo ''
\echo '=== 2. the season rows added up, as the profile shows them ==='
SELECT p.name, s.name AS season,
       SUM(v.matches) AS games, SUM(v.batting_innings) AS inns, SUM(v.runs) AS runs,
       SUM(v.overs) AS overs, SUM(v.wickets) AS wickets,
       string_agg(DISTINCT v.source, ', ' ORDER BY v.source) AS sources
  FROM _p p
  JOIN v_effective_player_season_stats v ON v.player_id = p.player_id
  LEFT JOIN seasons s ON s.id = v.season_id
 GROUP BY p.name, s.name, s.year
 ORDER BY p.name, s.year DESC NULLS LAST;

\echo ''
\echo '=== 3. typed games with a synced game of the club on the same date and no pairing ==='
\echo '    these are the twins; "synced_has_card" says whether PlayHQ holds our batters for it'
SELECT p.name, mg.played_at, mg.opposition AS typed_opposition,
       COALESCE(sg.home_team, '') || ' v ' || COALESCE(sg.away_team, '') AS synced_game,
       s.name AS season, s.import_authoritative AS resourced,
       EXISTS (SELECT 1 FROM batting_innings bi
                WHERE bi.game_id = sg.id AND bi.player_id = p.player_id) AS synced_has_card,
       mg.id AS typed_game_id
  FROM _p p
  JOIN manual_batting_innings mbi ON mbi.player_id = p.player_id
  JOIN manual_games mg ON mg.id = mbi.manual_game_id
  JOIN seasons s ON s.id = mg.season_id
  JOIN games sg ON sg.played_at = mg.played_at
               AND (sg.home_org_id = p.org_id OR sg.away_org_id = p.org_id)
 WHERE mg.superseded_by_game_id IS NULL
 GROUP BY p.name, mg.played_at, mg.opposition, sg.id, sg.home_team, sg.away_team,
          s.name, s.import_authoritative, mg.id, p.player_id
 ORDER BY p.name, mg.played_at;

\echo ''
\echo '=== 4. who made each typed game: typed on the form, or a file import ==='
\echo '    (Manual Entries > Audit & Undo shows the same list)'
SELECT l.action, COUNT(*) AS entries, MIN(l.created_at)::date AS first, MAX(l.created_at)::date AS last
  FROM manual_edit_logs l
  JOIN organisations o ON o.id = l.organisation_id
 WHERE o.name ILIKE :club
   AND l.target_table = 'manual_games'
   AND l.undone_at IS NULL
 GROUP BY l.action
 ORDER BY entries DESC;
