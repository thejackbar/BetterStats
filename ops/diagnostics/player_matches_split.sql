-- How a player's MATCHES PLAYED splits into matches batted in, bowled only,
-- fielded only and named only. READ ONLY, one club, one player.
--
-- Shoalwater Bay's Records -> Most Career Runs read R Spinks 435 matches / 438
-- innings while his profile reads 465. The board counted matches he BATTED in;
-- the profile counts matches he PLAYED in. This proves the 30 in between are
-- matches he was in and did not bat in, and says what each one was.
--
-- Uses the same four sources the profile unions (batting, bowling, fielding,
-- roster appearance) over the effective views, so manual scorebook imports
-- count exactly as synced games do.
--
-- Run on the box:
--   cd /srv/docker && COMPOSE_PROJECT_NAME=bltbox_docker_app \
--     docker compose exec -T betterstats-db \
--     psql -U cricket -d betterstats -v who="'%Spinks%'" -v club="'%Shoalwater%'" \
--     -f - < /srv/docker/betterstats/ops/diagnostics/player_matches_split.sql

\timing on
SET jit = off;

CREATE TEMP TABLE _p AS
SELECT p.id AS player_id, COALESCE(p.display_name_override, p.name) AS name
  FROM players p
  JOIN organisations o ON o.id = p.organisation_id
 WHERE o.name ILIKE :club
   AND COALESCE(p.display_name_override, p.name) ILIKE :who;

SELECT * FROM _p;   -- more than one row means the name is ambiguous: narrow :who

CREATE TEMP TABLE _g AS
WITH src AS (
    SELECT bi.player_id, bi.game_id,
           BOOL_OR(NOT COALESCE(bi.did_not_bat, FALSE)
                   AND LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent','did not bat','dnb')) AS batted,
           FALSE AS bowled, FALSE AS fielded, FALSE AS named
      FROM v_effective_batting_innings bi
      JOIN _p USING (player_id) GROUP BY bi.player_id, bi.game_id
    UNION ALL
    SELECT bs.player_id, bs.game_id, FALSE, TRUE, FALSE, FALSE
      FROM v_effective_bowling_spells bs JOIN _p USING (player_id)
    UNION ALL
    SELECT fs.player_id, fs.game_id, FALSE, FALSE, TRUE, FALSE
      FROM v_effective_fielding_stats fs JOIN _p USING (player_id)
    UNION ALL
    SELECT ga.player_id, ga.game_id, FALSE, FALSE, FALSE, TRUE
      FROM game_appearances ga JOIN _p USING (player_id)
)
SELECT player_id, game_id,
       BOOL_OR(batted) AS batted, BOOL_OR(bowled) AS bowled,
       BOOL_OR(fielded) AS fielded, BOOL_OR(named) AS named
  FROM src GROUP BY player_id, game_id;

-- The split. `played` is the profile's figure, `batted` is what the Records
-- board counted, and the four buckets beneath add up to played - batted.
SELECT n.name,
       COUNT(*)                                                        AS matches_played,
       COUNT(*) FILTER (WHERE g.batted)                                AS matches_batted,
       COUNT(*) FILTER (WHERE NOT g.batted AND g.bowled)               AS bowled_no_bat,
       COUNT(*) FILTER (WHERE NOT g.batted AND NOT g.bowled AND g.fielded) AS fielded_only,
       COUNT(*) FILTER (WHERE NOT g.batted AND NOT g.bowled AND NOT g.fielded) AS named_only_or_dnb
  FROM _g g JOIN _p n USING (player_id) GROUP BY n.name;

-- His batting innings, for the INN column beside it (two-day matches give two).
SELECT n.name, COUNT(*) AS batting_innings, COUNT(DISTINCT bi.game_id) AS games_with_a_bat
  FROM v_effective_batting_innings bi JOIN _p n USING (player_id)
 WHERE NOT COALESCE(bi.did_not_bat, FALSE)
   AND LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent','did not bat','dnb')
 GROUP BY n.name;
