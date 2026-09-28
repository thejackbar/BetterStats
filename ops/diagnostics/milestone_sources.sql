-- Why the Milestones-in-reach page and a player's own profile disagree at
-- Shoalwater Bay (Hetel 5913 v 5924 runs, Godfrey 197 v 478 wickets, Ritchie
-- 198 v 201 catches), and what a CSFW-imported fixture actually holds.
--
-- The claim under test: the milestone scan (services/milestone_scan.py) sums
-- the BASE player_season_stats table, Cricket Australia's own summary alone;
-- the profile sums v_effective_player_season_stats, which also carries the
-- import deltas, the manual rollups and the per-match api_scorecard branch,
-- and steps CA's summary aside for a re-sourced season. If that is the whole
-- story, section 3's `view_minus_base` equals the gap the club reported, and
-- section 4 names which branch each run/wicket/catch came from.
--
-- Run on the box:
--   cd /srv/docker && COMPOSE_PROJECT_NAME=bltbox_docker_app \
--     docker compose exec -T betterstats-db \
--     psql -U cricket -d betterstats -v slug=shoalwater-bay-cricket-club \
--     -f - < /srv/docker/betterstats/ops/diagnostics/milestone_sources.sql
--
-- Reads only. Nothing here writes.

\set ON_ERROR_STOP on

\echo ''
\echo '=== 0. the club, its Grade Type default, and its re-sourced seasons ==='
SELECT o.id AS org_id, o.name,
       o.stats_grade_categories AS grade_type_default,
       (SELECT COUNT(*) FROM seasons s WHERE s.organisation_id = o.id AND s.import_authoritative) AS authoritative_seasons
  FROM organisations o
 WHERE o.slug = :'slug';

\echo ''
\echo '=== 1. the players named in the report ==='
CREATE TEMP TABLE _who AS
SELECT p.id, COALESCE(p.display_name_override, p.name) AS player, p.is_player, p.status
  FROM players p JOIN organisations o ON o.id = p.organisation_id
 WHERE o.slug = :'slug'
   AND COALESCE(p.display_name_override, p.name) ILIKE ANY (ARRAY['%hetel%','%godfrey%','%ritchie%','%hind%']);
SELECT * FROM _who ORDER BY player;

\echo ''
\echo '=== 2. what the MILESTONE SCAN reads: base player_season_stats, this club''s seasons, active = a row in the last 3 years ==='
\echo '    (this is milestone_scan._TOTALS_SQL replayed for the named players; `active` false means the scan lists them at all)'
SELECT w.player,
       EXISTS (SELECT 1 FROM player_season_stats a JOIN seasons s ON s.id = a.season_id
                WHERE a.player_id = w.id AND s.organisation_id = o.id
                  AND (s.year IS NULL OR s.year >= EXTRACT(YEAR FROM CURRENT_DATE)::int - 2)) AS active,
       COALESCE(SUM(pss.runs),0)    AS scan_runs,
       COALESCE(SUM(pss.wickets),0) AS scan_wickets,
       COALESCE(SUM(pss.matches),0) AS scan_matches,
       COALESCE(SUM(pss.catches),0) AS scan_catches,
       COALESCE(SUM(pss.runs)    FILTER (WHERE s.import_authoritative),0) AS of_which_runs_in_resourced_seasons,
       COALESCE(SUM(pss.wickets) FILTER (WHERE s.import_authoritative),0) AS of_which_wkts_in_resourced_seasons,
       COALESCE(SUM(pss.catches) FILTER (WHERE s.import_authoritative),0) AS of_which_ct_in_resourced_seasons
  FROM _who w
  JOIN organisations o ON o.slug = :'slug'
  LEFT JOIN player_season_stats pss ON pss.player_id = w.id
  LEFT JOIN seasons s ON s.id = pss.season_id AND s.organisation_id = o.id
 WHERE s.id IS NOT NULL OR pss.player_id IS NULL
 GROUP BY w.player, w.id, o.id
 ORDER BY w.player;

\echo ''
\echo '=== 3. what the PROFILE reads (unfiltered): the whole effective view, and the gap against the scan ==='
WITH base AS (
  SELECT w.id, COALESCE(SUM(pss.runs),0) r, COALESCE(SUM(pss.wickets),0) wk, COALESCE(SUM(pss.catches),0) ct, COALESCE(SUM(pss.matches),0) m
    FROM _who w JOIN organisations o ON o.slug = :'slug'
    LEFT JOIN player_season_stats pss ON pss.player_id = w.id
    LEFT JOIN seasons s ON s.id = pss.season_id
   WHERE s.organisation_id = o.id OR pss.player_id IS NULL
   GROUP BY w.id),
view AS (
  SELECT w.id, COALESCE(SUM(v.runs),0) r, COALESCE(SUM(v.wickets),0) wk, COALESCE(SUM(v.catches),0) ct, COALESCE(SUM(v.matches),0) m
    FROM _who w LEFT JOIN v_effective_player_season_stats v ON v.player_id = w.id
   GROUP BY w.id)
SELECT w.player,
       view.r  AS profile_runs,    base.r  AS scan_runs,    view.r  - base.r  AS view_minus_base_runs,
       view.wk AS profile_wickets, base.wk AS scan_wickets, view.wk - base.wk AS view_minus_base_wkts,
       view.ct AS profile_catches, base.ct AS scan_catches, view.ct - base.ct AS view_minus_base_ct,
       view.m  AS profile_matches, base.m  AS scan_matches
  FROM _who w JOIN base ON base.id = w.id JOIN view ON view.id = w.id
 ORDER BY w.player;

\echo ''
\echo '=== 4. the same view, one row per branch, so the gap can be traced to its source ==='
\echo '    api = CA summary the view still counts; api_scorecard = uncovered CA games in a re-sourced season;'
\echo '    manual_game = imported/hand-typed scorecards rolled up; import = BetterImport season/career deltas'
SELECT w.player, v.source,
       COUNT(*) AS rows,
       COALESCE(SUM(v.runs),0) AS runs, COALESCE(SUM(v.wickets),0) AS wickets,
       COALESCE(SUM(v.catches),0) AS catches, COALESCE(SUM(v.matches),0) AS matches
  FROM _who w JOIN v_effective_player_season_stats v ON v.player_id = w.id
 GROUP BY w.player, v.source
 ORDER BY w.player, v.source;

\echo ''
\echo '=== 5. the profile under a Grade Type filter or club default: scorecards + residuals (only relevant if section 0 shows a default) ==='
WITH bat AS (
  SELECT w.id, SUM(bi.runs) r
    FROM _who w JOIN v_effective_batting_innings bi ON bi.player_id = w.id
   WHERE NOT COALESCE(bi.did_not_bat, FALSE)
     AND LOWER(COALESCE(bi.dismissal_type,'')) NOT IN ('absent','did not bat','dnb')
   GROUP BY w.id),
bowl AS (SELECT w.id, SUM(bs.wickets) wk FROM _who w JOIN v_effective_bowling_spells bs ON bs.player_id = w.id GROUP BY w.id),
fld  AS (SELECT w.id, SUM(fs.catches) ct FROM _who w JOIN v_effective_fielding_stats fs ON fs.player_id = w.id GROUP BY w.id),
res  AS (
  SELECT w.id, COALESCE(SUM(v.runs),0) r, COALESCE(SUM(v.wickets),0) wk, COALESCE(SUM(v.catches),0) ct
    FROM _who w JOIN v_effective_player_season_stats v ON v.player_id = w.id
   WHERE v.source IN ('manual_aggregate','manual_career','import')
   GROUP BY w.id)
SELECT w.player,
       COALESCE(bat.r,0)  AS scorecard_runs,    COALESCE(res.r,0)  AS residual_runs,    COALESCE(bat.r,0)+COALESCE(res.r,0)   AS scoped_profile_runs,
       COALESCE(bowl.wk,0) AS scorecard_wickets, COALESCE(res.wk,0) AS residual_wickets, COALESCE(bowl.wk,0)+COALESCE(res.wk,0) AS scoped_profile_wkts,
       COALESCE(fld.ct,0) AS scorecard_catches, COALESCE(res.ct,0) AS residual_catches, COALESCE(fld.ct,0)+COALESCE(res.ct,0)  AS scoped_profile_ct
  FROM _who w LEFT JOIN bat ON bat.id = w.id LEFT JOIN bowl ON bowl.id = w.id
  LEFT JOIN fld ON fld.id = w.id LEFT JOIN res ON res.id = w.id
 ORDER BY w.player;

\echo ''
\echo '=== 6. stored (Achieved) milestone rows the sync has written for them ==='
\echo '    if Ritchie has no catches/200 row here while section 3 says 201, the Achieved list is stale for the same reason'
SELECT w.player, m.milestone_type, m.milestone_value, m.achieved_at
  FROM _who w JOIN milestones m ON m.player_id = w.id
 WHERE m.milestone_value >= 100
 ORDER BY w.player, m.milestone_type, m.milestone_value;

\echo ''
\echo '=== 7. J Hind: runs by grade, so the junior share of the 2982 can be read off ==='
SELECT w.player, gr.name AS grade, gr.category, COUNT(*) FILTER (WHERE NOT COALESCE(bi.did_not_bat,FALSE)) AS innings, SUM(bi.runs) AS runs
  FROM _who w
  JOIN v_effective_batting_innings bi ON bi.player_id = w.id
  JOIN v_effective_games g ON g.id = bi.game_id
  LEFT JOIN grades gr ON gr.id = g.grade_id
 WHERE w.player ILIKE '%hind%'
 GROUP BY w.player, gr.name, gr.category
 ORDER BY w.player, runs DESC NULLS LAST;

\echo ''
\echo '=== 8. what a CSFW-imported fixture holds: no both-team payload, no partnerships, no fall of wickets ==='
\echo '    a photo-uploaded card has extracted_payload; a spreadsheet import never does, and that payload is the only source of the opposition half'
SELECT (mg.extracted_payload IS NOT NULL) AS has_both_team_payload,
       (mg.cricketstatz_import_id IS NOT NULL) AS from_cricketstatz,
       COUNT(*) AS games,
       COUNT(*) FILTER (WHERE EXISTS (SELECT 1 FROM manual_partnerships mp WHERE mp.manual_game_id = mg.id)) AS with_partnerships,
       COUNT(*) FILTER (WHERE EXISTS (SELECT 1 FROM manual_fall_of_wickets mf WHERE mf.manual_game_id = mg.id)) AS with_fall_of_wickets,
       COUNT(*) FILTER (WHERE mg.opposition IS NOT NULL) AS with_opposition_name,
       COUNT(*) FILTER (WHERE mg.result IS NOT NULL) AS with_result
  FROM manual_games mg JOIN organisations o ON o.id = mg.organisation_id
 WHERE o.slug = :'slug'
 GROUP BY 1, 2
 ORDER BY 1, 2;

\echo ''
\echo '=== 9. one imported fixture, as the match page sees it: our innings totals exist, the opposition''s do not ==='
SELECT mg.id, mg.played_at, mg.opposition, mg.home_team, mg.away_team, mg.result, mg.winning_team,
       (SELECT SUM(runs) FROM manual_batting_innings b WHERE b.manual_game_id = mg.id) AS our_runs_from_batting_rows,
       (SELECT SUM(runs) FROM manual_bowling_spells s WHERE s.manual_game_id = mg.id) AS their_runs_off_our_bowlers_only,
       (SELECT COUNT(*) FROM manual_partnerships mp WHERE mp.manual_game_id = mg.id) AS partnerships
  FROM manual_games mg JOIN organisations o ON o.id = mg.organisation_id
 WHERE o.slug = :'slug' AND mg.extracted_payload IS NULL AND mg.cricketstatz_import_id IS NULL
 ORDER BY mg.played_at DESC NULLS LAST
 LIMIT 3;

DROP TABLE _who;
