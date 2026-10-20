-- Why a profile's MATCHES figure reads higher than Cricket Australia's. READ ONLY,
-- one club, one player.
--
-- Jonathon Seen (ACC) reads 202 on BetterStats and 197 on the CA / PlayHQ app,
-- with innings (132), runs (1,131) and average (13.46) identical. Under any
-- active scope (the club default that hides juniors counts) the header is
-- `_scoped_games_played`: distinct games we hold for him, from a batting row, a
-- bowling spell, a fielding row or a named appearance in a fixture that was
-- played. Unfiltered it is CA's `SUM(player_season_stats.matches)`. So the 5 are
-- games we hold and CA does not count for him.
--
-- This lists them. Section 1 finds the season(s), section 2 names every held
-- game in that season with what we hold against it, so a washout, a twin from a
-- paired import, an intra-club fixture or a one-off second-grade game shows
-- itself.
--
-- Run on the box:
--   cd /srv/docker && COMPOSE_PROJECT_NAME=bltbox_docker_app \
--     docker compose exec -T betterstats-db \
--     psql -U cricket -d betterstats -v who="'%Seen%'" -v club="'%ACC%'" \
--     -f - < /srv/docker/betterstats/ops/diagnostics/player_matches_vs_ca.sql

\timing on
SET jit = off;

CREATE TEMP TABLE _p AS
SELECT p.id AS player_id, p.organisation_id AS org_id,
       COALESCE(p.display_name_override, p.name) AS name
  FROM players p
  JOIN organisations o ON o.id = p.organisation_id
 WHERE o.name ILIKE :club
   AND COALESCE(p.display_name_override, p.name) ILIKE :who;

SELECT * FROM _p;   -- more than one row means the name is ambiguous: narrow :who

CREATE TEMP TABLE _held AS
WITH src AS (
    SELECT bi.player_id, bi.game_id, TRUE AS bat, FALSE AS bowl, FALSE AS fld, FALSE AS named
      FROM v_effective_batting_innings bi JOIN _p USING (player_id)
    UNION ALL
    SELECT bs.player_id, bs.game_id, FALSE, TRUE, FALSE, FALSE
      FROM v_effective_bowling_spells bs JOIN _p USING (player_id)
    UNION ALL
    SELECT fs.player_id, fs.game_id, FALSE, FALSE, TRUE, FALSE
      FROM v_effective_fielding_stats fs JOIN _p USING (player_id)
    UNION ALL
    SELECT ga.player_id, ga.game_id, FALSE, FALSE, FALSE, TRUE
      FROM game_appearances ga JOIN _p USING (player_id)
     WHERE (SELECT g2.status FROM games g2 WHERE g2.id = ga.game_id) IS NULL
        OR (SELECT g2.status FROM games g2 WHERE g2.id = ga.game_id)
           NOT IN ('ABANDONED', 'CANCELLED')
)
SELECT s.player_id, s.game_id,
       BOOL_OR(bat) AS bat, BOOL_OR(bowl) AS bowl, BOOL_OR(fld) AS fld, BOOL_OR(named) AS named
  FROM src s
  JOIN _p USING (player_id)
  JOIN v_effective_games g ON g.id = s.game_id
 WHERE g.organisation_id = _p.org_id OR g.home_org_id = _p.org_id OR g.away_org_id = _p.org_id
 GROUP BY s.player_id, s.game_id;

-- 1. Per season: games we hold against CA's own matches figure. A positive
--    `held_minus_ca` is where the extra games sit.
SELECT se.name AS season,
       COUNT(*) AS held,
       (SELECT COALESCE(SUM(pss.matches), 0)
          FROM v_effective_player_season_stats pss
         WHERE pss.player_id = (SELECT player_id FROM _p LIMIT 1)
           AND pss.season_id = se.id) AS ca,
       COUNT(*) - (SELECT COALESCE(SUM(pss.matches), 0)
          FROM v_effective_player_season_stats pss
         WHERE pss.player_id = (SELECT player_id FROM _p LIMIT 1)
           AND pss.season_id = se.id) AS held_minus_ca
  FROM _held h
  JOIN v_effective_games g ON g.id = h.game_id
  LEFT JOIN seasons se ON se.id = g.season_id
 GROUP BY se.id, se.name
 ORDER BY 4 DESC, 1;

-- 2. Every held game with what backs it. Look for: only `named` set (no
--    scorecard row), a status that is not COMPLETED, source = manual, the same
--    date and teams twice (a twin), or home_org = away_org (intra-club).
SELECT g.played_at, se.name AS season, gr.name AS grade, g.source,
       g.status, g.result, g.home_team, g.away_team,
       (g.home_org_id = g.away_org_id) AS intra_club,
       h.bat, h.bowl, h.fld, h.named, g.id AS game_id
  FROM _held h
  JOIN v_effective_games g ON g.id = h.game_id
  LEFT JOIN grades gr ON gr.id = g.grade_id
  LEFT JOIN seasons se ON se.id = g.season_id
 ORDER BY g.played_at DESC, g.id;

-- 3. Same player, same date, more than one held game: the duplicate signature.
SELECT g.played_at, COUNT(*) AS games_that_day, ARRAY_AGG(g.source) AS sources
  FROM _held h JOIN v_effective_games g ON g.id = h.game_id
 GROUP BY g.played_at HAVING COUNT(*) > 1
 ORDER BY g.played_at DESC;
