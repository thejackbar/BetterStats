-- Which clubs and seasons change when v9.138.0 ships. READ ONLY, every club.
--
-- From v9.138.0 a season counts match by match (Cricket Australia's season total stepped aside) as
-- soon as a person chose the club's card for any paired match in it. Clubs that already used Card
-- review, including its bulk switches, have such choices now, so their season totals move the
-- moment the new views are applied. That is the intent, but nobody should be surprised by it.
-- A season that is already re-sourced (`import_authoritative`) does not change.
--
-- Run on the box BEFORE deploying:
--   cd /srv/docker && COMPOSE_PROJECT_NAME=bltbox_docker_app \
--     docker compose exec -T betterstats-db psql -U cricket -d betterstats \
--     -f - < /srv/docker/betterstats/ops/diagnostics/chosen_cards_by_season.sql
--
-- Reads only. Nothing here writes.

\set ON_ERROR_STOP on
SET jit = off;

SELECT o.name AS club, s.name AS season,
       COUNT(*) AS matches_with_a_chosen_card,
       COUNT(*) FILTER (WHERE mg.review_choice = 'club')   AS club_card,
       COUNT(*) FILTER (WHERE mg.review_choice = 'hybrid') AS club_numbers_with_ca_detail,
       COUNT(*) FILTER (WHERE mg.review_source = 'hand')   AS chosen_by_hand,
       COUNT(*) FILTER (WHERE mg.review_source <> 'hand' OR mg.review_source IS NULL) AS chosen_in_bulk_or_other
  FROM manual_games mg
  JOIN seasons s ON s.id = mg.season_id
  JOIN organisations o ON o.id = mg.organisation_id
 WHERE mg.superseded_by_game_id IS NOT NULL
   AND mg.pair_prefers_import
   AND mg.review_choice IS NOT NULL
   AND NOT s.import_authoritative
 GROUP BY o.name, s.name, s.year
 ORDER BY o.name, s.year DESC;
