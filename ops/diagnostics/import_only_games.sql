-- The games a season-totals import holds that nothing else does: the list to send a club so it can
-- decide which to keep. READ ONLY, one club.
--
-- Hamilton Veterans (Nov 2026): the sheet `hamilton_import_pre_online.csv` and the games the club
-- typed in overlap almost entirely (v9.137.3 stops them counting twice). What is left is a few
-- dozen games the sheet alone holds, in 2011/12, 2013/14 and 2017/18. The club called some of
-- them wrong ("additional game recorded but no details") and the rest may be the only record there
-- is of a match. They stay in the totals until the club says otherwise.
--
-- One row per player and season. "Held already" is what Cricket Australia and the club's own typed
-- games carry for that player and season, the same two sources the reconciler subtracts, so
-- "games only the sheet holds" is exactly what the sheet still adds to the totals.
--
-- Output is CSV with a blank "Keep? (Y/N)" column for the club to fill in; the last column is the
-- ids of the sheet rows, which `app.scripts.drop_import_rows` removes for every row marked N.
--
-- Run on the box (CSV to a file you can send):
--   cd /srv/docker && COMPOSE_PROJECT_NAME=bltbox_docker_app \
--     docker compose exec -T betterstats-db \
--     psql -q -U cricket -d betterstats -v club="'%Hamilton Veterans%'" \
--     -f - < /srv/docker/betterstats/ops/diagnostics/import_only_games.sql > /tmp/hamilton_sheet_only_games.csv
--
-- Reads only. Nothing here writes. Run it AFTER the reconcile has been re-run on the new code
-- (`python -m app.scripts.reconcile_imports <org id>`), so the totals and this list agree.

\set ON_ERROR_STOP on
\pset format csv
\pset tuples_only off
SET jit = off;

WITH club AS (
    SELECT id FROM organisations WHERE name ILIKE :club
),
sheet AS (
    SELECT i.player_id, i.season_id,
           SUM(i.games_played)  AS games,
           SUM(i.batting_runs)  AS runs,
           SUM(i.bowling_wickets) AS wickets,
           string_agg(DISTINCT NULLIF(i.grade_label, ''), ', ' ORDER BY NULLIF(i.grade_label, '')) AS competitions,
           array_agg(i.id ORDER BY i.id) AS row_ids
      FROM imported_stats i
      JOIN club c ON c.id = i.organisation_id
      JOIN import_batches b ON b.id = i.import_batch_id AND b.undone_at IS NULL
     WHERE i.season_id IS NOT NULL
     GROUP BY i.player_id, i.season_id
),
held AS (
    SELECT v.player_id, v.season_id, SUM(v.matches) AS games
      FROM v_effective_player_season_stats v
     WHERE v.source IN ('api', 'manual_game')
     GROUP BY v.player_id, v.season_id
)
SELECT COALESCE(p.display_name_override, p.name)                         AS "Player",
       s.name                                                            AS "Season",
       sh.competitions                                                   AS "Competition on the sheet",
       sh.games                                                          AS "Games on the sheet",
       COALESCE(h.games, 0)                                              AS "Games already held (PlayHQ or typed)",
       GREATEST(sh.games - COALESCE(h.games, 0), 0)                      AS "Games only the sheet holds",
       sh.runs                                                           AS "Runs on the sheet",
       sh.wickets                                                        AS "Wickets on the sheet",
       CASE WHEN h.player_id IS NULL
            THEN 'Nothing else holds this player in this season'
            ELSE 'The sheet has more games than the club typed' END      AS "Why it is still counted",
       ''                                                                AS "Keep? (Y/N)",
       array_to_string(sh.row_ids, ' ')                                  AS "Sheet row ids (leave)"
  FROM sheet sh
  JOIN players p ON p.id = sh.player_id
  JOIN seasons s ON s.id = sh.season_id
  LEFT JOIN held h ON h.player_id = sh.player_id AND h.season_id = sh.season_id
 WHERE sh.games > COALESCE(h.games, 0)
 ORDER BY s.year, s.name, COALESCE(p.display_name_override, p.name);
