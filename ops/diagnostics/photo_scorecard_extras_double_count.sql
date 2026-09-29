-- Cross-check the photo-upload opposition-total double-count fix.
--
-- A scorecard uploaded from a photo stores the whole both-team card in
-- manual_games.extracted_payload. For an innings we did NOT itemise batter by
-- batter (the opposition's), the card records the FULL total (total_runs) plus
-- that innings' extras. `_manual_opp_from_payload` (backend/app/routers/games.py)
-- writes innings_totals[n].runs, and the scorecard page renders each innings as
--
--     displayed = runs + (extras or 0)      -- MatchScorecard.jsx
--
-- so `runs` MUST be stored bat-only (total_runs - extras). The bug stored the
-- FULL total_runs into `runs`, so the page added the extras a second time:
-- a 118-run innings with 9 extras showed as 127. The fix stores 118 - 9 = 109,
-- and 109 + 9 reconstructs 118.
--
-- This whole script is READ-ONLY — it writes nothing. Part A proves the
-- arithmetic contract on a synthetic payload (no table needed). Part B scans
-- this club's real photo uploads for the opposition innings that were being
-- double-counted, and shows the corrected total for each.
--
-- Run on the box:
--   cd /srv/docker && COMPOSE_PROJECT_NAME=bltbox_docker_app \
--     docker compose exec -T betterstats-db \
--     psql -U cricket -d betterstats \
--     -f - < /srv/docker/betterstats/ops/diagnostics/photo_scorecard_extras_double_count.sql

\set ON_ERROR_STOP on

-- The effective extras for an innings, exactly as games.py derives it:
-- the recorded total, else the sum of the itemised parts, else 0.
-- (Postgres has no inline function; this expression is repeated where needed.)

\echo ''
\echo '=== Part A — the contract, on a synthetic opposition innings ==='
\echo '(118 runs, 9 extras: displayed must come to 118, never 127)'
\echo ''

WITH card(payload) AS (
  VALUES ('{
    "innings": [
      {"innings_number": 1, "is_our_team": false, "total_runs": 118,
       "total_wickets": 10, "extras": {"total": 9}},
      {"innings_number": 2, "is_our_team": false, "total_runs": 118,
       "total_wickets": 10, "extras": {"byes": 4, "leg_byes": 2, "wides": 3}},
      {"innings_number": 3, "is_our_team": false, "total_runs": 118,
       "total_wickets": 10, "extras": {}},
      {"innings_number": 4, "is_our_team": false,
       "total_wickets": 10, "extras": {}}
    ]
  }'::jsonb)
),
inn AS (
  SELECT
    (i->>'innings_number')::int                              AS innings_number,
    NULLIF(i->>'total_runs', '')::int                        AS total_runs,
    COALESCE(
      NULLIF(i->'extras'->>'total', '')::int,
      NULLIF( COALESCE((i->'extras'->>'byes')::int,0)
            + COALESCE((i->'extras'->>'leg_byes')::int,0)
            + COALESCE((i->'extras'->>'wides')::int,0)
            + COALESCE((i->'extras'->>'no_balls')::int,0)
            + COALESCE((i->'extras'->>'penalty')::int,0), 0)
    , 0)                                                     AS extras
  FROM card, LATERAL jsonb_array_elements(payload->'innings') AS i
)
SELECT
  innings_number                                             AS inn,
  total_runs,
  extras,
  -- what the OLD code stored in runs, and what the page then showed:
  total_runs                                                 AS old_runs,
  COALESCE(total_runs,0) + extras                            AS old_displayed,
  -- the FIX: bat-only runs, and the page's reconstruction:
  GREATEST(0, COALESCE(total_runs,0) - extras)               AS new_runs,
  CASE WHEN total_runs IS NULL THEN 0
       ELSE GREATEST(0, total_runs - extras) + extras END    AS new_displayed,
  CASE
    WHEN total_runs IS NULL THEN 'no total recorded — nothing to show'
    WHEN GREATEST(0, total_runs - extras) + extras = total_runs
      THEN 'OK: reconstructs the real total'
    ELSE 'WRONG'
  END                                                        AS verdict,
  CASE
    WHEN total_runs IS NOT NULL AND extras > 0
         AND (COALESCE(total_runs,0) + extras) <> total_runs
      THEN 'old code double-counted by ' || extras
    ELSE 'old code was already correct here'
  END                                                        AS old_verdict
FROM inn
ORDER BY innings_number;

\echo ''
\echo 'Every new_displayed above must equal total_runs. The first innings is the'
\echo 'one the bug hit: old_displayed 127 vs new_displayed 118.'

\echo ''
\echo '=== Part B — real photo uploads whose opposition total carried extras ==='
\echo '(these are the innings that were being double-counted before the fix)'
\echo ''

WITH opp_inn AS (
  SELECT
    mg.id                                                    AS game_id,
    mg.played_at,
    mg.home_team, mg.away_team,
    (i->>'innings_number')::int                              AS innings_number,
    NULLIF(i->>'total_runs', '')::int                        AS total_runs,
    COALESCE(
      NULLIF(i->'extras'->>'total', '')::int,
      NULLIF( COALESCE((i->'extras'->>'byes')::int,0)
            + COALESCE((i->'extras'->>'leg_byes')::int,0)
            + COALESCE((i->'extras'->>'wides')::int,0)
            + COALESCE((i->'extras'->>'no_balls')::int,0)
            + COALESCE((i->'extras'->>'penalty')::int,0), 0)
    , 0)                                                     AS extras
  FROM manual_games mg,
       LATERAL jsonb_array_elements(mg.extracted_payload->'innings') AS i
  WHERE mg.extracted_payload IS NOT NULL
    AND COALESCE((i->>'is_our_team')::boolean, false) = false
)
SELECT
  game_id,
  played_at,
  home_team || ' v ' || away_team                            AS match,
  innings_number                                             AS inn,
  total_runs                                                 AS real_total,
  extras,
  COALESCE(total_runs,0) + extras                            AS was_shown_as,
  GREATEST(0, COALESCE(total_runs,0) - extras) + extras      AS now_shown_as
FROM opp_inn
WHERE total_runs IS NOT NULL
  AND extras > 0
ORDER BY played_at DESC, game_id, innings_number;

\echo ''
\echo 'For every row above, was_shown_as (the old, wrong figure) exceeds'
\echo 'real_total by the extras, and now_shown_as equals real_total. No rows'
\echo 'means no photo upload on this club ever recorded an opposition total'
\echo 'alongside its extras, so none were affected.'
\echo ''
