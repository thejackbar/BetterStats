-- Where the club's totals sheet and the scorecards it typed in disagree on a figure: the list to send a
-- club so it can say which is right. READ ONLY, one club.
--
-- Hamilton Veterans (Nov 2026): after v9.139.3.1 each season shows the LARGER of the sheet and the typed
-- scorecards for every figure, so a player's season can read a run or a wicket more than the cards add up
-- to, or the cards can hold more than the sheet. Only the club knows which is right.
--
-- One row per player and season where the sheet and the cards differ on games, innings, runs, overs or
-- wickets. Two things are left out, so the club is only asked what it can answer:
--   * a figure the sheet never held. An older season's sheet line is often GAMES ONLY (no innings, runs,
--     overs or wickets), and the cards holding those figures is not a disagreement. Batting figures are
--     compared only when the sheet has batting for the season, bowling figures only when it has bowling.
--   * a season where the sheet has MORE GAMES than the cards. It is on the sheet-only games list
--     (import_only_games.sql), so the club never answers the same thing twice.
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
     GROUP BY player_id, season_id),
diff AS (
    SELECT sh.*, t.g AS cg, t.inns AS cinns, t.runs AS cruns, t.overs AS covers, t.wkts AS cwkts,
           (sh.g IS DISTINCT FROM t.g) AS d_games,
           ((sh.inns > 0 OR sh.runs > 0) AND sh.inns IS DISTINCT FROM t.inns) AS d_inns,
           ((sh.inns > 0 OR sh.runs > 0) AND sh.runs IS DISTINCT FROM t.runs) AS d_runs,
           ((sh.overs > 0 OR sh.wkts > 0) AND sh.overs IS DISTINCT FROM t.overs) AS d_overs,
           ((sh.overs > 0 OR sh.wkts > 0) AND sh.wkts IS DISTINCT FROM t.wkts) AS d_wkts
      FROM sheet sh
      JOIN typed t ON t.player_id = sh.player_id AND t.season_id = sh.season_id
     WHERE sh.g <= t.g)
SELECT COALESCE(p.display_name_override, p.name)               AS "Player",
       s.name                                                  AS "Season",
       d.g                                                     AS "Games (sheet)",
       d.cg                                                    AS "Games (cards)",
       d.inns                                                  AS "Innings (sheet)",
       d.cinns                                                 AS "Innings (cards)",
       d.runs                                                  AS "Runs (sheet)",
       d.cruns                                                 AS "Runs (cards)",
       d.overs                                                 AS "Overs (sheet)",
       d.covers                                                AS "Overs (cards)",
       d.wkts                                                  AS "Wickets (sheet)",
       d.cwkts                                                 AS "Wickets (cards)",
       concat_ws(', ',
           CASE WHEN d.d_games THEN 'games'   END,
           CASE WHEN d.d_inns  THEN 'innings' END,
           CASE WHEN d.d_runs  THEN 'runs'    END,
           CASE WHEN d.d_overs THEN 'overs'   END,
           CASE WHEN d.d_wkts  THEN 'wickets' END)             AS "Figures that differ",
       ''                                                      AS "Which is right? (Cards or Sheet)",
       array_to_string(d.row_ids, ' ')                         AS "Sheet row ids (leave)"
  FROM diff d
  JOIN players p ON p.id = d.player_id
  JOIN seasons s ON s.id = d.season_id
 WHERE d.d_games OR d.d_inns OR d.d_runs OR d.d_overs OR d.d_wkts
 ORDER BY "Player", s.year;
