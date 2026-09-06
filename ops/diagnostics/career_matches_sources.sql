-- Two sources for "career matches", and how far apart they are platform-wide.
--
-- A player profile shows one figure unfiltered and another the moment ANY
-- filter is applied, because CA's season aggregates carry no grade and cannot
-- answer a grade-type, match-type or competition question:
--
--   no filter  -> SUM(player_season_stats.matches), Cricket Australia's totals
--   any filter -> COUNT(DISTINCT game) from the scorecards we hold
--
-- Rob Wilton (Applecross) reads 333 unfiltered and 337 filtered, and every one
-- of the four extra games is an ordinary synced fixture. Whether that holds
-- ACROSS THE PLATFORM is what decides if the header can safely adopt the
-- `max(held, claimed)` rule the by-grade grid already uses — and the risk it
-- has to rule out is a club where the extra held games are duplicates or
-- another club's fixtures rather than real ones.
--
-- Run on the box (READ ONLY; expect a minute or two, it scans every per-game
-- table once):
--   cd /srv/docker && COMPOSE_PROJECT_NAME=bltbox_docker_app \
--     docker compose exec -T betterstats-db \
--     psql -U cricket -d betterstats -f - < ops/diagnostics/career_matches_sources.sql

\timing on
SET jit = off;

CREATE TEMP TABLE _cmp AS
WITH held AS (
    SELECT p.organisation_id AS org_id, u.player_id,
           COUNT(DISTINCT u.game_id) AS held
      FROM (
            SELECT player_id, game_id FROM v_effective_batting_innings
      UNION SELECT player_id, game_id FROM v_effective_bowling_spells
      UNION SELECT player_id, game_id FROM v_effective_fielding_stats
      UNION SELECT ga.player_id, ga.game_id
              FROM game_appearances ga
              JOIN games g2 ON g2.id = ga.game_id
             WHERE g2.status IS NULL
                OR g2.status NOT IN ('ABANDONED', 'CANCELLED')
                OR EXISTS (SELECT 1 FROM batting_innings b
                            WHERE b.game_id = ga.game_id AND b.player_id = ga.player_id)
                OR EXISTS (SELECT 1 FROM bowling_spells w
                            WHERE w.game_id = ga.game_id AND w.player_id = ga.player_id)
                OR EXISTS (SELECT 1 FROM fielding_stats f
                            WHERE f.game_id = ga.game_id AND f.player_id = ga.player_id)
           ) u
      JOIN players p  ON p.id = u.player_id
      JOIN v_effective_games g ON g.id = u.game_id
      JOIN grades gr  ON gr.id = g.grade_id
      JOIN seasons s  ON s.id = gr.season_id AND s.organisation_id = p.organisation_id
     GROUP BY 1, 2
), agg AS (
    SELECT p.organisation_id AS org_id, pss.player_id,
           COALESCE(SUM(pss.matches), 0) AS agg
      FROM v_effective_player_season_stats pss
      JOIN players p ON p.id = pss.player_id
      LEFT JOIN seasons s ON s.id = pss.season_id
     WHERE pss.season_id IS NULL OR s.organisation_id = p.organisation_id
     GROUP BY 1, 2
)
SELECT COALESCE(h.org_id, a.org_id) AS org_id,
       COALESCE(h.player_id, a.player_id) AS player_id,
       COALESCE(a.agg, 0)  AS agg_matches,
       COALESCE(h.held, 0) AS held_matches
  FROM held h FULL OUTER JOIN agg a
    ON a.org_id = h.org_id AND a.player_id = h.player_id;

\echo ''
\echo '=== 1. platform shape: how often the two sources disagree ==='
SELECT COUNT(*)                                             AS players,
       COUNT(*) FILTER (WHERE held_matches = agg_matches)           AS agree,
       COUNT(*) FILTER (WHERE held_matches > agg_matches)           AS we_hold_more,
       COUNT(*) FILTER (WHERE held_matches < agg_matches)           AS ca_says_more,
       SUM(GREATEST(held_matches - agg_matches, 0))                 AS total_extra_held,
       MAX(held_matches - agg_matches)                              AS biggest_over,
       MIN(held_matches - agg_matches)                              AS biggest_under
  FROM _cmp;

\echo ''
\echo '=== 2. would adopting max(held, claimed) move a player at all, and by how much ==='
SELECT (held_matches - agg_matches) AS difference, COUNT(*) AS players
  FROM _cmp WHERE held_matches > agg_matches
 GROUP BY 1 ORDER BY 1 DESC LIMIT 15;

\echo ''
\echo '=== 3. which clubs it lands on (top 15 by players affected) ==='
SELECT o.name AS club,
       COUNT(*) FILTER (WHERE c.held_matches > c.agg_matches) AS players_up,
       SUM(GREATEST(c.held_matches - c.agg_matches, 0))       AS matches_added,
       COUNT(*)                                       AS players_total
  FROM _cmp c JOIN organisations o ON o.id = c.org_id
 GROUP BY o.name HAVING COUNT(*) FILTER (WHERE c.held_matches > c.agg_matches) > 0
 ORDER BY 2 DESC LIMIT 15;

\echo ''
\echo '=== 4. THE RISK: a manual upload duplicating a synced game, same club/date/grade ==='
\echo '    If this returns rows, the extra held games are not all real and the'
\echo '    header must NOT adopt the higher number until they are cleaned up.'
SELECT o.name AS club, gr.name AS grade, g.played_at, COUNT(*) AS games_that_day,
       COUNT(*) FILTER (WHERE g.source = 'manual') AS manual,
       COUNT(*) FILTER (WHERE g.source = 'api')    AS synced
  FROM v_effective_games g
  JOIN grades gr ON gr.id = g.grade_id
  JOIN seasons s ON s.id = gr.season_id
  JOIN organisations o ON o.id = s.organisation_id
 GROUP BY o.name, gr.name, g.played_at
HAVING COUNT(*) FILTER (WHERE g.source = 'manual') > 0
   AND COUNT(*) FILTER (WHERE g.source = 'api') > 0
 ORDER BY 1, 3 LIMIT 25;

\echo ''
\echo '=== 5. the ten biggest movers, to eyeball ==='
SELECT o.name AS club, COALESCE(p.display_name_override, p.name) AS player,
       c.agg_matches AS ca_says, c.held_matches AS we_hold, c.held_matches - c.agg_matches AS diff
  FROM _cmp c JOIN players p ON p.id = c.player_id
  JOIN organisations o ON o.id = c.org_id
 WHERE c.held_matches > c.agg_matches
 ORDER BY diff DESC, we_hold DESC LIMIT 10;
