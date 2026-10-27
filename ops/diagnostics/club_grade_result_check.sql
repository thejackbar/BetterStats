-- club_grade_result_check.sql
--
-- Why does BetterCricket show a club's grade final as a loss when Cricket
-- Australia / Play-Cricket shows a win? Reported by Shoalwater Bay, Ladies B
-- Grade premiership, 2025/26.
--
-- games.result is the verdict of whichever club synced the fixture FIRST, and
-- both result and winning_team are written once (sync.py fills them only while
-- they are NULL), so a card read before CA settled the result keeps the early
-- value. This script shows, for one club and grade, what is stored and what
-- the club's own page would derive from it (the same rule as
-- routers/games._result_for_club), so the two can be put side by side with the
-- live CA card (see the python step in the header of the answer / CLAUDE notes).
--
-- CHANGES NOTHING. It only SELECTs from real tables and builds two TEMP tables, all
-- inside one transaction that is rolled back at the end (Postgres will not build a
-- CREATE TABLE AS inside a READ ONLY transaction).
--
--   cd /srv/docker && export COMPOSE_PROJECT_NAME=bltbox_docker_app
--   docker compose exec -T betterstats-db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
--       -v ON_ERROR_STOP=1 -v club=shoalwater -v grade="%ladies%b%" -v year=2026' \
--       < /srv/docker/betterstats/ops/diagnostics/club_grade_result_check.sql
--
--   club   a fragment of the club's slug or name
--   grade  an ILIKE pattern for the grade name
--   year   the season's end year (seasons.year; 2025/26 is usually 2026, but
--          step 2 lists them so you can see which one the club uses)

BEGIN;

\echo '== 1. The club'
SELECT id, name, slug FROM organisations
WHERE slug ILIKE '%' || :'club' || '%' OR name ILIKE '%' || :'club' || '%';

\echo '== 2. Its seasons and the grades matching the pattern'
SELECT s.year, s.name AS season, g.name AS grade, g.id AS grade_id, g.grassroots_id,
       (SELECT count(*) FROM games x WHERE x.grade_id = g.id) AS games_in_grade
FROM organisations o
JOIN seasons s ON s.organisation_id = o.id
JOIN grades g ON g.season_id = s.id
WHERE (o.slug ILIKE '%' || :'club' || '%' OR o.name ILIKE '%' || :'club' || '%')
  AND g.name ILIKE :'grade'
ORDER BY s.year DESC, g.name;

-- Every later step works from this one temp table: the club's games in the
-- chosen grade and year, owned by the club's season OR played by it as a side.
CREATE TEMP TABLE t_games AS
SELECT g.id, g.played_at, gr.name AS grade, s.year, g.round_name, g.is_final,
       g.status, g.ca_called_off, g.home_team, g.away_team,
       g.home_org_id, g.away_org_id, g.opp_org_id, g.opp_club_name,
       g.result, g.winning_team, g.innings_totals,
       o.id AS club_id, o.name AS club_name,
       CASE
         WHEN g.home_org_id = o.id THEN 'home'
         WHEN g.away_org_id = o.id THEN 'away'
         WHEN g.home_club ILIKE '%' || :'club' || '%' THEN 'home'
         WHEN g.away_club ILIKE '%' || :'club' || '%' THEN 'away'
       END AS club_side
FROM organisations o
JOIN seasons s ON s.organisation_id = o.id
JOIN grades gr ON gr.season_id = s.id
JOIN games g ON g.grade_id = gr.id
WHERE (o.slug ILIKE '%' || :'club' || '%' OR o.name ILIKE '%' || :'club' || '%')
  AND gr.name ILIKE :'grade'
  AND s.year = :year;

-- What the club's own page derives (routers/games._result_for_club, reduced).
-- derived = WIN/LOSS from the winning team's NAME against the club's side;
-- falls back to the stored result when no winner is recorded.
CREATE TEMP TABLE t_read AS
SELECT t.*,
       CASE
         WHEN nullif(btrim(t.winning_team), '') IS NULL THEN NULL
         WHEN btrim(t.winning_team) = btrim(CASE t.club_side WHEN 'home' THEN t.home_team ELSE t.away_team END) THEN 'WIN'
         WHEN btrim(t.winning_team) = btrim(CASE t.club_side WHEN 'home' THEN t.away_team ELSE t.home_team END) THEN 'LOSS'
       END AS by_winner_name
FROM t_games t;

\echo '== 3. Every game the club played in that grade and season, as stored'
SELECT played_at, round_name, is_final AS fin, status, ca_called_off AS called_off,
       home_team, away_team, club_side,
       result AS stored_result, winning_team AS stored_winner,
       by_winner_name, COALESCE(by_winner_name, result) AS what_page_shows,
       CASE WHEN by_winner_name IS NOT NULL AND result IN ('WIN','LOSS')
                 AND by_winner_name <> result THEN 'stored result disagrees with the winner name'
            WHEN winning_team IS NULL AND result IS NOT NULL THEN 'no winner recorded, result only'
            WHEN winning_team IS NULL AND result IS NULL THEN 'nothing recorded'
       END AS note
FROM t_read
ORDER BY played_at, id;

\echo '== 4. The final(s): who synced the row first, and the stored scores'
SELECT id, played_at, round_name, home_team, away_team,
       home_org_id, away_org_id, opp_org_id, opp_club_name,
       result, winning_team, innings_totals
FROM t_read
WHERE is_final OR round_name ILIKE '%final%'
ORDER BY played_at;

\echo '== 5. Is the row superseded or paired by an import (effective view)?'
SELECT e.*
FROM v_effective_games e
WHERE e.id IN (SELECT id FROM t_read WHERE is_final OR round_name ILIKE '%final%');

\echo '== 6. Premiership honours written for those games'
SELECT pa.linked_game_id, count(*) AS honours, min(pa.achievement) AS achievement
FROM player_achievements pa
WHERE pa.linked_game_id IN (SELECT id FROM t_read WHERE is_final OR round_name ILIKE '%final%')
GROUP BY pa.linked_game_id;

\echo '== 7. How widespread: club games, any grade, this year, where the stored result and the winner name disagree'
SELECT gr.name AS grade, g.played_at, g.round_name, g.home_team, g.away_team,
       g.result AS stored_result, g.winning_team,
       CASE WHEN g.home_org_id = o.id OR g.home_club ILIKE '%' || :'club' || '%' THEN 'home' ELSE 'away' END AS club_side
FROM organisations o
JOIN seasons s ON s.organisation_id = o.id AND s.year = :year
JOIN grades gr ON gr.season_id = s.id
JOIN games g ON g.grade_id = gr.id
WHERE (o.slug ILIKE '%' || :'club' || '%' OR o.name ILIKE '%' || :'club' || '%')
  AND g.result IN ('WIN','LOSS')
  AND nullif(btrim(g.winning_team), '') IS NOT NULL
  AND (
    (CASE WHEN g.home_org_id = o.id OR g.home_club ILIKE '%' || :'club' || '%' THEN g.home_team ELSE g.away_team END) = g.winning_team
      AND g.result = 'LOSS' AND (g.home_org_id = o.id OR g.away_org_id = o.id)
    OR
    (CASE WHEN g.home_org_id = o.id OR g.home_club ILIKE '%' || :'club' || '%' THEN g.away_team ELSE g.home_team END) = g.winning_team
      AND g.result = 'WIN' AND (g.home_org_id = o.id OR g.away_org_id = o.id)
  )
ORDER BY gr.name, g.played_at;

ROLLBACK;
