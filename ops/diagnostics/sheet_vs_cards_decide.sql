-- Where the club's totals sheet and the scorecards it typed in disagree on a figure: the list to send a
-- club so it can say which is right. READ ONLY, one club.
--
-- Hamilton Veterans (Nov 2026): after v9.139.3.1 each season shows the LARGER of the sheet and the typed
-- scorecards for every figure, so a player's season can read a run or a wicket more than the cards add up
-- to, or the cards can hold more than the sheet. Only the club knows which is right.
--
-- One row per player and season where the sheet and the cards differ on games, innings, runs, overs or
-- wickets. A season where the sheet has MORE GAMES than the cards is left out: it is on the sheet-only
-- games list (import_only_games.sql), so the club never answers the same thing twice.
--
-- The club writes "Cards" or "Sheet" in the last-but-one column:
--   Cards  the typed scorecards are right and the sheet is not. `app.scripts.drop_import_rows` removes the
--          sheet's rows for that player and season, so the season shows the cards alone.
--   Sheet  the sheet is right and a scorecard is wrong. Nothing is removed; the club corrects the
--          scorecard in Manual Games (the season already shows the sheet's larger figure until then).
-- Blank means undecided and is left alone.
--
-- Run on the box (CSV to a file you can send):
--   cd /srv/docker && COMPOSE_PROJECT_NAME=bltbox_docker_app \
--     docker compose exec -T betterstats-db \
--     psql -q -U cricket -d betterstats -v club="'%Hamilton Veterans%'" \
--     -f - < /srv/docker/betterstats/ops/diagnostics/sheet_vs_cards_decide.sql > /tmp/hamilton_sheet_vs_cards.csv
--
-- Reads only. Nothing here writes. Run it AFTER the reconcile has been re-run on v9.139.3.1 or later.

\set ON_ERROR_STOP on
\pset format csv
\pset tuples_only off
SET jit = off;

WITH sheet AS (
    SELECT i.player_id, i.season_id,
           SUM(i.games_played) AS g, SUM(i.batting_innings) AS inns, SUM(i.batting_runs) AS runs,
           SUM(i.bowling_overs) AS overs, SUM(i.bowling_wickets) AS wkts,
           array_agg(i.id ORDER BY i.id) AS row_ids
      FROM imported_stats i
      JOIN organisations o ON o.id = i.organisation_id
      JOIN import_batches b ON b.id = i.import_batch_id AND b.undone_at IS NULL
     WHERE o.name ILIKE :club AND i.season_id IS NOT NULL
     GROUP BY i.player_id, i.season_id),
typed AS (
    SELECT player_id, season_id,
           SUM(matches) AS g, SUM(batting_innings) AS inns, SUM(runs) AS runs,
           SUM(overs) AS overs, SUM(wickets) AS wkts
      FROM v_effective_player_season_stats
     WHERE source = 'manual_game'
     GROUP BY player_id, season_id)
SELECT COALESCE(p.display_name_override, p.name)               AS "Player",
       s.name                                                  AS "Season",
       sh.g                                                    AS "Games (sheet)",
       t.g                                                     AS "Games (cards)",
       sh.inns                                                 AS "Innings (sheet)",
       t.inns                                                  AS "Innings (cards)",
       sh.runs                                                 AS "Runs (sheet)",
       t.runs                                                  AS "Runs (cards)",
       sh.overs                                                AS "Overs (sheet)",
       t.overs                                                 AS "Overs (cards)",
       sh.wkts                                                 AS "Wickets (sheet)",
       t.wkts                                                  AS "Wickets (cards)",
       concat_ws(', ',
           CASE WHEN sh.g    IS DISTINCT FROM t.g    THEN 'games'    END,
           CASE WHEN sh.inns IS DISTINCT FROM t.inns THEN 'innings'  END,
           CASE WHEN sh.runs IS DISTINCT FROM t.runs THEN 'runs'     END,
           CASE WHEN sh.overs IS DISTINCT FROM t.overs THEN 'overs'  END,
           CASE WHEN sh.wkts IS DISTINCT FROM t.wkts THEN 'wickets'  END) AS "Figures that differ",
       ''                                                      AS "Which is right? (Cards or Sheet)",
       array_to_string(sh.row_ids, ' ')                        AS "Sheet row ids (leave)"
  FROM sheet sh
  JOIN typed t ON t.player_id = sh.player_id AND t.season_id = sh.season_id
  JOIN players p ON p.id = sh.player_id
  JOIN seasons s ON s.id = sh.season_id
 WHERE (sh.g IS DISTINCT FROM t.g OR sh.inns IS DISTINCT FROM t.inns OR sh.runs IS DISTINCT FROM t.runs
        OR sh.overs IS DISTINCT FROM t.overs OR sh.wkts IS DISTINCT FROM t.wkts)
   AND sh.g <= t.g
 ORDER BY "Player", s.year;
