-- override_comparison.sql
--
-- After a spreadsheet import was run with "Overwrite existing matches", this
-- compares, match by match, the version the club's file put in with the
-- Cricket Australia / PlayHQ version it replaced, and says what the club's
-- version lost.
--
-- WHY THE PAIRS ARE EXACT. An overwrite does not delete the synced match. It
-- writes the imported match with superseded_by_game_id pointing at the synced
-- games row and pair_prefers_import set, and the effective views then show the
-- import and hide the synced copy. So every replaced match is still in
-- `games` with all of its rows, and the pair is a foreign key, not a guess.
--
-- WHAT IT CAN AND CANNOT COMPARE. A synced match's team TOTALS and extras are
-- not stored: the scorecard page fetches them live from Cricket Australia. What
-- IS stored, for both sides of a pair, is the club's batters and bowlers, so the
-- comparison is on those: the multiset of our batters' scores, our bowlers'
-- wickets and runs, the date, and the result worked out for OUR side (the same
-- rule aggregations._club_results uses, because games.result is relative to
-- whichever club synced first). A match whose scorecard has the same scores but
-- is wrong in a way only the Cricket Australia totals show will read AGREE.
--
-- CHANGES NOTHING. It only SELECTs from real tables and builds TEMP tables, all
-- inside one transaction that is rolled back at the end (Postgres will not
-- build a CREATE TABLE AS inside a READ ONLY transaction, so this is the
-- guarantee instead; tools/verify_override_comparison.py checks the row counts
-- before and after). It writes four CSV files into the directory psql was
-- started in.
--
--   psql "$DATABASE_URL" -v org_slug=payneham-cricket-club -v since=2026-10-19 \
--        -f ops/diagnostics/override_comparison.sql
--
--   org_slug  the club's organisations.slug
--   since     only matches the import created on or after this date, so an
--             earlier overwrite import (or a CricketStatz pairing) is left out
--
-- Outputs:
--   ov_pairs.csv       one row per replaced match: both versions side by side,
--                      the verdict, why, and what the club's version lost
--   ov_unpaired.csv    imported matches NOT paired to a synced match that look
--                      like one (same scores within 7 days): probable doubles
--   ov_enrich_batting.csv  the synced batting lines of every replaced match, for
--                      copying balls faced and boundaries onto the club's file
--   ov_by_season.csv   the same headline, season by season

\set ON_ERROR_STOP on
\if :{?org_slug}
\else
  \set org_slug 'payneham-cricket-club'
\endif
\if :{?since}
\else
  \set since '2000-01-01'
\endif

BEGIN;

CREATE TEMP TABLE ov_org AS
SELECT id FROM organisations WHERE slug = :'org_slug';

DO $$
BEGIN
  IF (SELECT count(*) FROM ov_org) <> 1 THEN
    RAISE EXCEPTION 'org_slug matched % organisations, expected exactly 1',
      (SELECT count(*) FROM ov_org);
  END IF;
END $$;

-- 1. The replaced matches. One row per imported match that took over a synced one.
CREATE TEMP TABLE ov_pairs AS
SELECT mg.id AS m_id,
       g.id  AS g_id,
       s.name AS season_name,
       gr.name AS grade_name,
       mg.played_at AS m_date,
       g.played_at  AS g_date,
       mg.opposition AS m_opposition,
       CASE WHEN g.home_org_id = o.id THEN g.away_team
            WHEN g.away_org_id = o.id THEN g.home_team
            ELSE COALESCE(g.opp_club_name, g.home_team || ' v ' || g.away_team)
       END AS g_opposition,
       mg.result AS m_result,
       -- OUR result from the synced row: winning_team is neutral, result is not.
       CASE WHEN g.winning_team IS NULL THEN g.result
            WHEN g.home_org_id = o.id AND g.winning_team = g.home_team THEN 'WIN'
            WHEN g.home_org_id = o.id AND g.winning_team = g.away_team THEN 'LOSS'
            WHEN g.away_org_id = o.id AND g.winning_team = g.away_team THEN 'WIN'
            WHEN g.away_org_id = o.id AND g.winning_team = g.home_team THEN 'LOSS'
            ELSE g.result
       END AS g_result,
       mg.created_at AS imported_at
FROM manual_games mg
CROSS JOIN ov_org o
JOIN games g ON g.id = mg.superseded_by_game_id
LEFT JOIN seasons s ON s.id = mg.season_id
LEFT JOIN grades gr ON gr.id = mg.grade_id
WHERE mg.organisation_id = o.id
  AND mg.pair_prefers_import
  AND mg.created_at >= :'since'::timestamptz;

CREATE INDEX ON ov_pairs (g_id);
CREATE INDEX ON ov_pairs (m_id);

-- 2. The synced side: our batters and theirs. "Ours" is players.organisation_id.
CREATE TEMP TABLE ov_g_bat AS
SELECT bi.game_id,
       count(*) FILTER (WHERE p.organisation_id = o.id AND NOT COALESCE(bi.did_not_bat, false)) AS our_rows,
       count(*) FILTER (WHERE p.organisation_id = o.id AND NOT COALESCE(bi.did_not_bat, false)
                          AND bi.balls IS NOT NULL) AS our_balls_rows,
       count(*) FILTER (WHERE p.organisation_id IS DISTINCT FROM o.id
                          AND NOT COALESCE(bi.did_not_bat, false)) AS their_rows,
       COALESCE(sum(bi.runs) FILTER (WHERE p.organisation_id = o.id
                          AND NOT COALESCE(bi.did_not_bat, false)), 0) AS our_runs,
       string_agg(bi.runs::text, ',' ORDER BY bi.runs) FILTER (WHERE p.organisation_id = o.id
                          AND NOT COALESCE(bi.did_not_bat, false) AND bi.runs IS NOT NULL) AS our_scores,
       array_agg(bi.runs ORDER BY bi.runs) FILTER (WHERE p.organisation_id = o.id
                          AND NOT COALESCE(bi.did_not_bat, false) AND bi.runs IS NOT NULL) AS our_runs_arr
FROM batting_innings bi
JOIN players p ON p.id = bi.player_id
CROSS JOIN ov_org o
WHERE bi.game_id IN (SELECT g_id FROM ov_pairs)
GROUP BY bi.game_id;

CREATE TEMP TABLE ov_g_bowl AS
SELECT bs.game_id,
       count(*) FILTER (WHERE p.organisation_id = o.id) AS our_spells,
       count(*) FILTER (WHERE p.organisation_id IS DISTINCT FROM o.id) AS their_spells,
       COALESCE(sum(bs.wickets) FILTER (WHERE p.organisation_id = o.id), 0) AS our_wkts,
       COALESCE(sum(bs.runs) FILTER (WHERE p.organisation_id = o.id), 0) AS our_runs_conceded
FROM bowling_spells bs
JOIN players p ON p.id = bs.player_id
CROSS JOIN ov_org o
WHERE bs.game_id IN (SELECT g_id FROM ov_pairs)
GROUP BY bs.game_id;

-- 3. The imported side.
CREATE TEMP TABLE ov_m_bat AS
SELECT mb.manual_game_id,
       count(*) FILTER (WHERE NOT mb.did_not_bat) AS rows,
       count(*) FILTER (WHERE NOT mb.did_not_bat AND mb.balls IS NOT NULL) AS balls_rows,
       COALESCE(sum(mb.runs) FILTER (WHERE NOT mb.did_not_bat), 0) AS runs,
       string_agg(mb.runs::text, ',' ORDER BY mb.runs) FILTER (WHERE NOT mb.did_not_bat) AS scores
FROM manual_batting_innings mb
WHERE mb.manual_game_id IN (SELECT m_id FROM ov_pairs)
GROUP BY mb.manual_game_id;

CREATE TEMP TABLE ov_m_bowl AS
SELECT ms.manual_game_id,
       count(*) AS spells,
       COALESCE(sum(ms.wickets), 0) AS wkts,
       COALESCE(sum(ms.runs), 0) AS runs_conceded
FROM manual_bowling_spells ms
WHERE ms.manual_game_id IN (SELECT m_id FROM ov_pairs)
GROUP BY ms.manual_game_id;

-- 4. Everything side by side, plus the detail inventory.
CREATE TEMP TABLE ov_cmp AS
SELECT p.*,
       COALESCE(gb.our_rows, 0)  AS g_our_batters,
       COALESCE(mb.rows, 0)      AS m_batters,
       gb.our_scores             AS g_scores,
       mb.scores                 AS m_scores,
       COALESCE(gb.our_runs, 0)  AS g_our_runs,
       COALESCE(mb.runs, 0)      AS m_our_runs,
       COALESCE(gw.our_wkts, 0)  AS g_wkts,
       COALESCE(mw.wkts, 0)      AS m_wkts,
       COALESCE(gw.our_runs_conceded, 0) AS g_runs_conceded,
       COALESCE(mw.runs_conceded, 0)     AS m_runs_conceded,
       -- what the synced match carries
       COALESCE(gb.our_balls_rows, 0)  AS g_balls_rows,
       COALESCE(gb.their_rows, 0)      AS g_opp_batters,
       COALESCE(gw.their_spells, 0)    AS g_opp_bowlers,
       (SELECT count(*) FROM bowler_wickets x WHERE x.game_id = p.g_id)   AS g_dismissal_credits,
       (SELECT count(*) FROM fall_of_wickets x WHERE x.game_id = p.g_id)  AS g_fow,
       (SELECT count(*) FROM partnerships x WHERE x.game_id = p.g_id)     AS g_partnerships,
       (SELECT count(*) FROM fielding_stats x WHERE x.game_id = p.g_id)   AS g_fielding,
       (SELECT count(*) FROM game_appearances x WHERE x.game_id = p.g_id) AS g_team_sheet,
       -- what the imported match carries
       COALESCE(mb.balls_rows, 0) AS m_balls_rows,
       (SELECT count(*) FROM manual_bowler_wickets x WHERE x.manual_game_id = p.m_id)  AS m_dismissal_credits,
       (SELECT count(*) FROM manual_fall_of_wickets x WHERE x.manual_game_id = p.m_id) AS m_fow,
       (SELECT count(*) FROM manual_partnerships x WHERE x.manual_game_id = p.m_id)    AS m_partnerships,
       (SELECT count(*) FROM manual_fielding_stats x WHERE x.manual_game_id = p.m_id)  AS m_fielding
FROM ov_pairs p
LEFT JOIN ov_g_bat gb ON gb.game_id = p.g_id
LEFT JOIN ov_g_bowl gw ON gw.game_id = p.g_id
LEFT JOIN ov_m_bat mb ON mb.manual_game_id = p.m_id
LEFT JOIN ov_m_bowl mw ON mw.manual_game_id = p.m_id;

-- 5. Verdict and what was lost.
CREATE TEMP TABLE ov_verdict AS
SELECT c.*,
       concat_ws(', ',
         CASE WHEN c.m_date IS DISTINCT FROM c.g_date THEN 'date' END,
         CASE WHEN c.m_result IS DISTINCT FROM c.g_result THEN 'result' END,
         CASE WHEN c.g_our_batters > 0 AND c.m_scores IS DISTINCT FROM c.g_scores THEN 'batting scores' END,
         CASE WHEN c.g_our_batters > 0 AND c.m_batters <> c.g_our_batters THEN 'number of batters' END,
         CASE WHEN c.g_our_batters > 0 AND c.m_wkts <> c.g_wkts THEN 'our bowlers'' wickets' END,
         CASE WHEN c.g_our_batters > 0 AND c.m_runs_conceded <> c.g_runs_conceded THEN 'runs conceded' END
       ) AS differences,
       concat_ws('; ',
         CASE WHEN c.g_balls_rows > c.m_balls_rows
              THEN (c.g_balls_rows - c.m_balls_rows) || ' batters'' balls faced' END,
         CASE WHEN c.g_opp_batters > 0 THEN 'opposition batting card (' || c.g_opp_batters || ')' END,
         CASE WHEN c.g_opp_bowlers > 0 THEN 'opposition bowling card (' || c.g_opp_bowlers || ')' END,
         CASE WHEN c.g_dismissal_credits > c.m_dismissal_credits
              THEN (c.g_dismissal_credits - c.m_dismissal_credits) || ' dismissals with bowler/fielder named' END,
         CASE WHEN c.g_fow > c.m_fow THEN 'fall of wickets (' || (c.g_fow - c.m_fow) || ' more)' END,
         CASE WHEN c.g_partnerships > c.m_partnerships
              THEN (c.g_partnerships - c.m_partnerships) || ' partnerships' END,
         CASE WHEN c.g_team_sheet > 0 THEN 'team sheets (captain, keeper)' END
       ) AS detail_lost
FROM ov_cmp c;

ALTER TABLE ov_verdict ADD COLUMN verdict text;
UPDATE ov_verdict SET verdict =
  CASE WHEN g_our_batters = 0 THEN 'PLAYHQ HAS NO CARD OF OURS'
       WHEN differences = '' THEN 'AGREE'
       ELSE 'DIFFERS' END;

-- 6. Imported matches that were NOT paired but look like a synced match: the
--    same scores within a week. Probable doubles; the importer could not tell
--    (a different date and an opposition spelt differently, with batters it
--    could not match to existing players).
CREATE TEMP TABLE ov_m_cand AS
SELECT mg.id AS m_id, mg.played_at, mg.opposition, gr.name AS grade_name, mg.season_id,
       array_agg(mb.runs ORDER BY mb.runs) FILTER (WHERE NOT mb.did_not_bat) AS runs_arr
FROM manual_games mg
CROSS JOIN ov_org o
LEFT JOIN grades gr ON gr.id = mg.grade_id
JOIN manual_batting_innings mb ON mb.manual_game_id = mg.id
WHERE mg.organisation_id = o.id
  AND mg.superseded_by_game_id IS NULL
  AND mg.created_at >= :'since'::timestamptz
  AND mg.played_at IS NOT NULL
GROUP BY mg.id, mg.played_at, mg.opposition, gr.name, mg.season_id;

CREATE TEMP TABLE ov_g_cand AS
SELECT g.id AS g_id, g.played_at,
       CASE WHEN g.home_org_id = o.id THEN g.away_team
            WHEN g.away_org_id = o.id THEN g.home_team
            ELSE COALESCE(g.opp_club_name, g.home_team || ' v ' || g.away_team) END AS opposition,
       array_agg(bi.runs ORDER BY bi.runs) FILTER (WHERE NOT COALESCE(bi.did_not_bat, false)
                                                     AND bi.runs IS NOT NULL) AS runs_arr
FROM games g
CROSS JOIN ov_org o
LEFT JOIN grades gr ON gr.id = g.grade_id
LEFT JOIN seasons s ON s.id = gr.season_id
JOIN batting_innings bi ON bi.game_id = g.id
JOIN players p ON p.id = bi.player_id AND p.organisation_id = o.id
WHERE (s.organisation_id = o.id OR g.home_org_id = o.id OR g.away_org_id = o.id)
  AND g.played_at IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM manual_games x
                  WHERE x.superseded_by_game_id = g.id AND x.pair_prefers_import)
GROUP BY g.id, g.played_at, g.home_org_id, g.away_org_id, g.home_team, g.away_team,
         g.opp_club_name, o.id;

CREATE TEMP TABLE ov_unpaired AS
SELECT m.m_id, g.g_id, m.played_at AS m_date, g.played_at AS g_date,
       (m.played_at = g.played_at) AS same_date,
       m.grade_name, m.opposition AS m_opposition, g.opposition AS g_opposition,
       (SELECT count(*) FROM (SELECT unnest(m.runs_arr) INTERSECT ALL SELECT unnest(g.runs_arr)) x)
         AS scores_in_common,
       cardinality(m.runs_arr) AS m_batters, cardinality(g.runs_arr) AS g_batters
FROM ov_m_cand m
JOIN ov_g_cand g ON abs(m.played_at - g.played_at) <= 7
WHERE (SELECT count(*) FROM (SELECT unnest(m.runs_arr) INTERSECT ALL SELECT unnest(g.runs_arr)) x) >= 3;

-- 7. The synced batting lines of every replaced match, for the club's file.
CREATE TEMP TABLE ov_enrich AS
SELECT p.m_id, p.g_id, p.m_date, p.grade_name, p.m_opposition,
       bi.innings_number AS g_innings, COALESCE(pl.display_name_override, pl.name) AS player_name,
       bi.runs, bi.balls, bi.fours, bi.sixes, bi.dismissal_type, bi.batting_position, bi.not_out
FROM ov_pairs p
JOIN batting_innings bi ON bi.game_id = p.g_id
JOIN players pl ON pl.id = bi.player_id
CROSS JOIN ov_org o
WHERE pl.organisation_id = o.id AND NOT COALESCE(bi.did_not_bat, false);

-- ---------------------------------------------------------------------------
-- Results
-- ---------------------------------------------------------------------------
\echo
\echo '== Replaced matches by verdict =='
SELECT verdict, count(*) AS matches FROM ov_verdict GROUP BY verdict ORDER BY 2 DESC;

\echo
\echo '== What the club''s version lost (matches affected) =='
SELECT count(*) FILTER (WHERE g_balls_rows > m_balls_rows)             AS balls_faced,
       count(*) FILTER (WHERE g_opp_batters > 0)                       AS opposition_batting_card,
       count(*) FILTER (WHERE g_opp_bowlers > 0)                       AS opposition_bowling_card,
       count(*) FILTER (WHERE g_dismissal_credits > m_dismissal_credits) AS dismissal_credits,
       count(*) FILTER (WHERE g_fow > m_fow)                           AS fall_of_wickets,
       count(*) FILTER (WHERE g_partnerships > m_partnerships)         AS partnerships,
       count(*) FILTER (WHERE g_team_sheet > 0)                        AS team_sheets
FROM ov_verdict;

\echo
\echo '== Why the DIFFERS rows differ =='
SELECT differences, count(*) AS matches FROM ov_verdict
WHERE verdict = 'DIFFERS' GROUP BY differences ORDER BY 2 DESC;

\echo
\echo '== Probable doubles: imported matches not paired, scores in common with a synced match =='
SELECT count(*) AS probable_doubles FROM ov_unpaired;

CREATE TEMP TABLE ov_by_season AS
SELECT season_name,
       count(*) AS replaced,
       count(*) FILTER (WHERE verdict = 'AGREE') AS agree,
       count(*) FILTER (WHERE verdict = 'DIFFERS') AS differs,
       count(*) FILTER (WHERE verdict = 'PLAYHQ HAS NO CARD OF OURS') AS no_playhq_card,
       count(*) FILTER (WHERE g_opp_batters > 0) AS with_opposition_card
FROM ov_verdict GROUP BY season_name;

\copy (SELECT verdict, differences, detail_lost, season_name, grade_name, m_date, g_date, m_opposition, g_opposition, m_result, g_result, m_batters, g_our_batters, m_scores, g_scores, m_wkts, g_wkts, m_runs_conceded, g_runs_conceded, g_balls_rows, g_opp_batters, g_opp_bowlers, g_dismissal_credits, g_fow, g_partnerships, g_team_sheet, m_id, g_id FROM ov_verdict ORDER BY verdict, season_name, m_date) TO 'ov_pairs.csv' CSV HEADER
\copy (SELECT * FROM ov_unpaired ORDER BY m_date) TO 'ov_unpaired.csv' CSV HEADER
\copy (SELECT * FROM ov_enrich ORDER BY m_date, m_opposition, g_innings, runs DESC) TO 'ov_enrich_batting.csv' CSV HEADER
\copy (SELECT * FROM ov_by_season ORDER BY season_name) TO 'ov_by_season.csv' CSV HEADER

ROLLBACK;
