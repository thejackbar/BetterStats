-- Why 155 Cricket Australia games in Shoalwater Bay's 2002/03-2006/07 were NOT
-- superseded by the CSV import run in overwrite mode, when 226 were.
--
-- For every synced game in an import-authoritative season that no imported
-- match supersedes, look for the CSFW match it SHOULD have paired with, and
-- say why the import's own matcher (exact date + any shared opponent token,
-- club-owned games only) missed it. Then the reverse: imported matches with no
-- CA twin at all.
--
-- Run on the box:
--   cd /srv/docker && COMPOSE_PROJECT_NAME=bltbox_docker_app \
--     docker compose exec -T betterstats-db \
--     psql -U cricket -d betterstats -v slug=shoalwater-bay-cricket-club \
--     -f - < /srv/docker/betterstats/ops/diagnostics/csv_import_unpaired.sql
--
-- Reads only. Nothing here writes.

\set ON_ERROR_STOP on

\echo ''
\echo '=== 0. the club and the seasons the import took over ==='
SELECT o.id AS org_id, o.name,
       COUNT(*) FILTER (WHERE s.import_authoritative) AS authoritative_seasons
  FROM organisations o
  LEFT JOIN seasons s ON s.organisation_id = o.id
 WHERE o.slug = :'slug'
 GROUP BY o.id, o.name;

SELECT s.name, s.year, s.import_authoritative
  FROM seasons s JOIN organisations o ON o.id = s.organisation_id
 WHERE o.slug = :'slug' AND s.import_authoritative
 ORDER BY s.year;

-- ---------------------------------------------------------------------------
-- Everything below is scoped to the import-authoritative seasons. A synced
-- game is "ours" by the club_grades rule: the season's own club, OR we are
-- one of the two sides (a fixture the other club synced first).
-- ---------------------------------------------------------------------------
CREATE TEMP TABLE _org AS
  SELECT id FROM organisations WHERE slug = :'slug';

CREATE TEMP TABLE _auth_seasons AS
  SELECT s.id, s.name, s.year
    FROM seasons s
   WHERE s.organisation_id = (SELECT id FROM _org)
     AND s.import_authoritative;

-- Our imported matches in those seasons (CSV importer rows: no cricketstatz id).
CREATE TEMP TABLE _imp AS
  SELECT mg.id, mg.played_at, mg.season_id,
         COALESCE(mg.opposition,'') AS opposition,
         mg.superseded_by_game_id, mg.pairing_locked
    FROM manual_games mg
   WHERE mg.organisation_id = (SELECT id FROM _org)
     AND mg.season_id IN (SELECT id FROM _auth_seasons);

-- Every synced CA game our club played in those seasons, with who owns the row.
CREATE TEMP TABLE _ca AS
  SELECT g.id, g.played_at, gr.season_id,
         s.organisation_id AS owner_org,
         (s.organisation_id = (SELECT id FROM _org)) AS we_own_row,
         COALESCE(g.opp_club_name,'') AS opp_club_name,
         COALESCE(g.home_team,'') AS home_team,
         COALESCE(g.away_team,'') AS away_team,
         g.status,
         EXISTS (SELECT 1 FROM manual_games lk
                  WHERE lk.superseded_by_game_id = g.id) AS superseded
    FROM games g
    JOIN grades gr ON gr.id = g.grade_id
    JOIN seasons s ON s.id = gr.season_id
   WHERE gr.season_id IN (SELECT id FROM _auth_seasons)
      OR (
           -- same real season held under the OTHER club's row: match on year
           s.year IN (SELECT year FROM _auth_seasons)
           AND (g.home_org_id = (SELECT id FROM _org)
             OR g.away_org_id = (SELECT id FROM _org))
         );

-- Our own batters' scores per game, both sides. The strong matcher's signal.
CREATE TEMP TABLE _ca_scores AS
  SELECT bi.game_id, bi.player_id, bi.runs
    FROM batting_innings bi
    JOIN players p ON p.id = bi.player_id AND p.organisation_id = (SELECT id FROM _org)
   WHERE bi.game_id IN (SELECT id FROM _ca)
     AND NOT COALESCE(bi.did_not_bat, false) AND bi.runs IS NOT NULL;

CREATE TEMP TABLE _imp_scores AS
  SELECT mbi.manual_game_id AS game_id, mbi.player_id, mbi.runs
    FROM manual_batting_innings mbi
   WHERE mbi.manual_game_id IN (SELECT id FROM _imp)
     AND NOT mbi.did_not_bat AND mbi.runs IS NOT NULL;

-- Opponent tokens, the way manual_entries._opp_tokens builds them: lowercase,
-- split on non-alphanumerics, keep words longer than 2 chars.
CREATE OR REPLACE FUNCTION pg_temp.toks(t text) RETURNS text[] LANGUAGE sql IMMUTABLE AS $$
  SELECT COALESCE(array_agg(w), '{}')
    FROM unnest(regexp_split_to_array(lower(COALESCE(t,'')), '[^a-z0-9]+')) AS w
   WHERE length(w) > 2
$$;

\echo ''
\echo '=== 1. headline counts ==='
SELECT
  (SELECT COUNT(*) FROM _ca)                                  AS ca_games_in_those_seasons,
  (SELECT COUNT(*) FROM _ca WHERE superseded)                 AS ca_superseded_by_import,
  (SELECT COUNT(*) FROM _ca WHERE NOT superseded)             AS ca_still_live,
  (SELECT COUNT(*) FROM _ca WHERE NOT superseded AND NOT we_own_row) AS ca_still_live_other_club_owns_row,
  (SELECT COUNT(*) FROM _imp)                                 AS imported_in_those_seasons,
  (SELECT COUNT(*) FROM _imp WHERE superseded_by_game_id IS NOT NULL) AS imported_that_paired,
  (SELECT COUNT(*) FROM _imp WHERE superseded_by_game_id IS NULL)     AS imported_unpaired;

-- ---------------------------------------------------------------------------
-- 2. For each still-live CA game, the best unpaired CSFW candidate and WHY the
--    import's matcher missed it. Candidates are unpaired imports in the same
--    season within 10 days. Shared scores = our batters with identical runs.
-- ---------------------------------------------------------------------------
CREATE TEMP TABLE _cand AS
  SELECT c.id AS ca_id, i.id AS imp_id,
         c.played_at AS ca_date, i.played_at AS imp_date,
         ABS(c.played_at - i.played_at) AS day_gap,
         c.we_own_row,
         c.opp_club_name, c.home_team, c.away_team, i.opposition,
         (SELECT COUNT(*) FROM _ca_scores cs
            JOIN _imp_scores ims ON ims.player_id = cs.player_id AND ims.runs = cs.runs
           WHERE cs.game_id = c.id AND ims.game_id = i.id)             AS shared_scores,
         (pg_temp.toks(i.opposition) &&
          (pg_temp.toks(c.opp_club_name) || pg_temp.toks(c.home_team) || pg_temp.toks(c.away_team)))
                                                                        AS opp_tokens_overlap
    FROM _ca c
    JOIN _imp i
      ON i.superseded_by_game_id IS NULL
     AND i.played_at IS NOT NULL AND c.played_at IS NOT NULL
     AND ABS(c.played_at - i.played_at) <= 10
     AND (i.season_id = c.season_id
          OR i.season_id IN (SELECT a.id FROM _auth_seasons a
                              JOIN seasons s2 ON s2.id = c.season_id AND s2.year = a.year))
   WHERE NOT c.superseded;

-- Best candidate per CA game: most shared scores, then closest date.
CREATE TEMP TABLE _best AS
  SELECT DISTINCT ON (ca_id) *
    FROM _cand
   ORDER BY ca_id, shared_scores DESC, day_gap ASC;

CREATE TEMP TABLE _classified AS
  SELECT c.id AS ca_id, c.played_at, c.we_own_row, c.status,
         c.opp_club_name, c.home_team, c.away_team,
         b.imp_id, b.imp_date, b.day_gap, b.shared_scores, b.opp_tokens_overlap, b.opposition,
         CASE
           WHEN b.imp_id IS NULL THEN 'no_csfw_twin_within_10_days'
           WHEN b.shared_scores >= 3 AND NOT c.we_own_row
                                     THEN 'twin_found: other club owns the CA row (matcher never saw it)'
           WHEN b.shared_scores >= 3 AND b.day_gap > 0
                                     THEN 'twin_found: date differs (matcher needs exact date)'
           WHEN b.shared_scores >= 3 AND NOT b.opp_tokens_overlap
                                     THEN 'twin_found: opponent spelt with no shared word'
           WHEN b.shared_scores >= 3  THEN 'twin_found: same date+opponent, unexplained miss (check consumed/duplicate)'
           WHEN b.shared_scores BETWEEN 1 AND 2 AND b.day_gap = 0
                                     THEN 'weak: same date, 1-2 shared scores'
           ELSE                            'weak: candidate nearby but scores do not agree'
         END AS verdict
    FROM _ca c
    LEFT JOIN _best b ON b.ca_id = c.id
   WHERE NOT c.superseded;

\echo ''
\echo '=== 2. the still-live CA games, classified ==='
SELECT verdict, COUNT(*) AS games
  FROM _classified
 GROUP BY verdict
 ORDER BY games DESC;

\echo ''
\echo '=== 2b. the same, by season ==='
SELECT s.name AS season, cl.verdict, COUNT(*) AS games
  FROM _classified cl
  JOIN _ca c ON c.id = cl.ca_id
  JOIN seasons s ON s.id = c.season_id
 GROUP BY s.name, s.year, cl.verdict
 ORDER BY s.year, games DESC;

\echo ''
\echo '=== 3. sample of each verdict (up to 6 each) ==='
SELECT verdict, played_at AS ca_date, imp_date, day_gap, shared_scores,
       we_own_row,
       left(home_team,22) AS ca_home, left(away_team,22) AS ca_away,
       left(opposition,22) AS csfw_opposition
  FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY verdict ORDER BY played_at) AS rn
      FROM _classified
  ) x
 WHERE rn <= 6
 ORDER BY verdict, played_at;

-- ---------------------------------------------------------------------------
-- 4. The reverse: imported CSFW matches with no CA game at all nearby.
--    These are the matches the CSFW file has that Cricket Australia does not.
-- ---------------------------------------------------------------------------
\echo ''
\echo '=== 4. unpaired CSFW matches with no CA game within 10 days (CSFW-only) ==='
SELECT s.name AS season, COUNT(*) AS csfw_only_matches
  FROM _imp i
  JOIN seasons s ON s.id = i.season_id
 WHERE i.superseded_by_game_id IS NULL
   AND NOT EXISTS (
     SELECT 1 FROM _ca c
      WHERE c.played_at IS NOT NULL AND i.played_at IS NOT NULL
        AND ABS(c.played_at - i.played_at) <= 10
        AND (SELECT COUNT(*) FROM _ca_scores cs
               JOIN _imp_scores ims ON ims.player_id = cs.player_id AND ims.runs = cs.runs
              WHERE cs.game_id = c.id AND ims.game_id = i.id) >= 2
   )
 GROUP BY s.name, s.year
 ORDER BY s.year;

\echo ''
\echo '=== 5. still-live CA games that carry NO batting card of ours at all ==='
\echo '    (a washout / team-sheet-only fixture; nothing for any matcher to compare)'
SELECT s.name AS season, c.status, COUNT(*) AS games
  FROM _ca c
  JOIN seasons s ON s.id = c.season_id
 WHERE NOT c.superseded
   AND NOT EXISTS (SELECT 1 FROM _ca_scores cs WHERE cs.game_id = c.id)
 GROUP BY s.name, s.year, c.status
 ORDER BY s.year;
