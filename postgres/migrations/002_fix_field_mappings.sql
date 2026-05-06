-- Migration 002: Add missing columns to player_season_stats for correct API field mappings

ALTER TABLE player_season_stats
    ADD COLUMN IF NOT EXISTS bowling_balls INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS bowling_strike_rate NUMERIC(6,2),
    ADD COLUMN IF NOT EXISTS best_bowling_figures TEXT,
    ADD COLUMN IF NOT EXISTS five_wicket_innings INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS wides INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS no_balls INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS catches_wk INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS catches_non_wk INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS assisted_run_outs INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS unassisted_run_outs INT DEFAULT 0;

-- Update career_bowling view to use bowling_balls for correct economy calculation
CREATE OR REPLACE VIEW career_bowling AS
SELECT
    p.id AS player_id,
    p.name,
    p.organisation_id,
    COALESCE(SUM(pss.matches), 0) AS games,
    COALESCE(SUM(pss.wickets), 0) AS total_wickets,
    ROUND(SUM(pss.runs_conceded)::numeric / NULLIF(SUM(pss.wickets), 0), 2) AS average,
    ROUND(SUM(pss.runs_conceded)::numeric / NULLIF(SUM(pss.bowling_balls), 0) * 6, 2) AS economy,
    MAX(pss.best_bowling_wickets) AS best_figures_wickets,
    MAX(pss.best_bowling_figures) AS best_bowling_figures,
    COALESCE(SUM(pss.maidens), 0) AS total_maidens,
    COALESCE(SUM(pss.overs), 0) AS total_overs,
    COALESCE(SUM(pss.runs_conceded), 0) AS total_runs,
    COALESCE(SUM(pss.five_wicket_innings), 0) AS five_fors
FROM players p
LEFT JOIN player_season_stats pss ON pss.player_id = p.id
GROUP BY p.id, p.name, p.organisation_id;

-- Update career_batting view to include ducks and games
CREATE OR REPLACE VIEW career_batting AS
SELECT
    p.id AS player_id,
    p.name,
    p.organisation_id,
    COALESCE(SUM(pss.batting_innings), 0) AS innings,
    COALESCE(SUM(pss.runs), 0) AS total_runs,
    MAX(pss.high_score) AS high_score,
    ROUND(SUM(pss.runs)::numeric / NULLIF(SUM(pss.batting_innings) - SUM(pss.not_outs), 0), 2) AS average,
    ROUND(SUM(pss.runs)::numeric / NULLIF(SUM(pss.balls_faced), 0) * 100, 2) AS strike_rate,
    COALESCE(SUM(pss.fifties), 0) AS fifties,
    COALESCE(SUM(pss.hundreds), 0) AS hundreds,
    COALESCE(SUM(pss.fours), 0) AS total_fours,
    COALESCE(SUM(pss.sixes), 0) AS total_sixes,
    COALESCE(SUM(pss.ducks), 0) AS ducks,
    COALESCE(SUM(pss.matches), 0) AS games
FROM players p
LEFT JOIN player_season_stats pss ON pss.player_id = p.id
GROUP BY p.id, p.name, p.organisation_id;

-- Update career_fielding view to include new breakdown columns
CREATE OR REPLACE VIEW career_fielding AS
SELECT
    p.id AS player_id,
    p.name,
    p.organisation_id,
    COALESCE(SUM(pss.matches), 0) AS games,
    COALESCE(SUM(pss.catches), 0) AS total_catches,
    COALESCE(SUM(pss.catches_wk), 0) AS total_catches_wk,
    COALESCE(SUM(pss.catches_non_wk), 0) AS total_catches_non_wk,
    COALESCE(SUM(pss.run_outs), 0) AS total_run_outs,
    COALESCE(SUM(pss.assisted_run_outs), 0) AS total_assisted_run_outs,
    COALESCE(SUM(pss.unassisted_run_outs), 0) AS total_unassisted_run_outs,
    COALESCE(SUM(pss.stumpings), 0) AS total_stumpings,
    COALESCE(SUM(pss.catches + pss.run_outs + pss.stumpings), 0) AS total_dismissals
FROM players p
LEFT JOIN player_season_stats pss ON pss.player_id = p.id
GROUP BY p.id, p.name, p.organisation_id;
