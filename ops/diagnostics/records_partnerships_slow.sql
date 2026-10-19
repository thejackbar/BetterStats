-- Why the Payneham records page takes ~100s: partnerships_by_wicket_rows and
-- partnerships_by_grade_rows (about 47s each in the app, but 110ms when the grade-name
-- lookups were left out, so the difference is in what this runs). Runs the query as the
-- app ships it, grade-name lookups included, with EXPLAIN ANALYZE. Reads only.
--
--   cd /srv/docker && COMPOSE_PROJECT_NAME=bltbox_docker_app \
--     docker compose exec -T betterstats-db \
--     psql -U cricket -d betterstats -f - < betterstats/ops/diagnostics/records_partnerships_slow.sql \
--     > /srv/docker/partnerships_explain2.txt 2>&1

\set org 'f0d283dc-87d8-eb11-a7ad-2818780da0cc'
\timing on
SET jit = off;
SET statement_timeout = '300s';

\echo '=== 0. server version and grade counts ==='
SELECT version();
SELECT count(*) AS grades_in_club FROM grades gr JOIN seasons s ON s.id = gr.season_id
 WHERE s.organisation_id = :'org';
SELECT count(*) AS grades_all_clubs FROM grades;
SELECT count(*) AS active_merge_logs FROM grade_merge_logs
 WHERE org_id = :'org' AND undone_at IS NULL;

\echo '=== A. the wicket board exactly as the app runs it ==='
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, TIMING OFF)
SELECT
    p1.id::text AS batter1_id,
    COALESCE(p1.display_name_override, p1.name) AS batter1_name,
    p2.id::text AS batter2_id,
    COALESCE(p2.display_name_override, p2.name) AS batter2_name,
    pt.runs, pt.wicket_number,
    g.played_at::text,
    COALESCE(gdn.display_name_override, COALESCE(am.canonical_name, gr.name)) AS grade_name,
    s.name AS season_name,
    EXTRACT(YEAR FROM g.played_at)::int AS season_year,
    false AS is_manual,
    ROW_NUMBER() OVER (PARTITION BY pt.wicket_number ORDER BY pt.runs DESC) AS rn
FROM v_effective_partnerships pt
JOIN v_effective_games g ON g.id = pt.game_id
JOIN grades gr ON gr.id = g.grade_id
JOIN seasons s ON s.id = gr.season_id
LEFT JOIN LATERAL (
    SELECT canonical_name FROM grade_merge_logs gml
    WHERE gml.org_id = CAST(:'org' AS UUID)
      AND gml.alias_name = gr.name
      AND gml.undone_at IS NULL
    LIMIT 1
) am ON TRUE
LEFT JOIN LATERAL (
    SELECT gr2.display_name_override FROM grades gr2
    JOIN seasons s2 ON s2.id = gr2.season_id
    WHERE s2.organisation_id = CAST(:'org' AS UUID)
      AND gr2.name = COALESCE(am.canonical_name, gr.name)
      AND gr2.display_name_override IS NOT NULL
    LIMIT 1
) gdn ON TRUE
LEFT JOIN players p1 ON p1.id = pt.batter1_id
LEFT JOIN players p2 ON p2.id = pt.batter2_id
WHERE pt.is_club_innings IS NOT FALSE
  AND p1.organisation_id = :'org' AND p2.organisation_id = :'org'
  AND pt.runs IS NOT NULL AND pt.runs > 0 AND pt.wicket_number BETWEEN 1 AND 10;

\echo '=== B. the same board as v9.123.6.1 runs it (grade names worked out once per grade) ==='
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, TIMING OFF)
WITH base AS MATERIALIZED (
    SELECT
        p1.id::text AS batter1_id,
        COALESCE(p1.display_name_override, p1.name) AS batter1_name,
        p2.id::text AS batter2_id,
        COALESCE(p2.display_name_override, p2.name) AS batter2_name,
        pt.runs, pt.wicket_number,
        g.played_at::text AS played_at,
        gr.id AS grade_id, gr.name AS grade_raw,
        s.name AS season_name,
        EXTRACT(YEAR FROM g.played_at)::int AS season_year
    FROM v_effective_partnerships pt
    JOIN v_effective_games g ON g.id = pt.game_id
    JOIN grades gr ON gr.id = g.grade_id
    JOIN seasons s ON s.id = gr.season_id
    LEFT JOIN players p1 ON p1.id = pt.batter1_id
    LEFT JOIN players p2 ON p2.id = pt.batter2_id
    WHERE pt.is_club_innings IS NOT FALSE
      AND p1.organisation_id = :'org' AND p2.organisation_id = :'org'
      AND pt.runs IS NOT NULL AND pt.runs > 0 AND pt.wicket_number BETWEEN 1 AND 10
), names AS MATERIALIZED (
    SELECT x.grade_id,
           COALESCE(gdn.display_name_override, COALESCE(am.canonical_name, x.grade_raw)) AS grade_name
    FROM (SELECT DISTINCT grade_id, grade_raw FROM base) x
    LEFT JOIN LATERAL (
        SELECT canonical_name FROM grade_merge_logs gml
        WHERE gml.org_id = CAST(:'org' AS UUID)
          AND gml.alias_name = x.grade_raw
          AND gml.undone_at IS NULL
        LIMIT 1
    ) am ON TRUE
    LEFT JOIN LATERAL (
        SELECT gr2.display_name_override FROM grades gr2
        JOIN seasons s2 ON s2.id = gr2.season_id
        WHERE s2.organisation_id = CAST(:'org' AS UUID)
          AND gr2.name = COALESCE(am.canonical_name, x.grade_raw)
          AND gr2.display_name_override IS NOT NULL
        LIMIT 1
    ) gdn ON TRUE
)
SELECT b.batter1_id, b.batter2_id, b.runs, b.wicket_number, n.grade_name,
       ROW_NUMBER() OVER (PARTITION BY b.wicket_number ORDER BY b.runs DESC) AS rn
FROM base b
JOIN names n ON n.grade_id = b.grade_id;
