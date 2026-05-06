-- Migration 001: Add player_season_stats table and update career views
-- Run against the existing betterstats database:
--   docker exec -i $(docker ps -qf name=betterstats-db) psql -U cricket -d betterstats < /path/to/001_player_season_stats.sql

CREATE TABLE IF NOT EXISTS player_season_stats (
    id SERIAL PRIMARY KEY,
    player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
    -- Batting
    matches INT DEFAULT 0,
    batting_innings INT DEFAULT 0,
    runs INT DEFAULT 0,
    not_outs INT DEFAULT 0,
    balls_faced INT DEFAULT 0,
    fifties INT DEFAULT 0,
    hundreds INT DEFAULT 0,
    ducks INT DEFAULT 0,
    high_score INT,
    is_hs_not_out BOOLEAN DEFAULT FALSE,
    batting_average NUMERIC(8,2),
    batting_strike_rate NUMERIC(8,2),
    fours INT DEFAULT 0,
    sixes INT DEFAULT 0,
    batting_minutes INT DEFAULT 0,
    -- Bowling
    bowling_innings INT DEFAULT 0,
    wickets INT DEFAULT 0,
    overs NUMERIC(8,1) DEFAULT 0,
    runs_conceded INT DEFAULT 0,
    maidens INT DEFAULT 0,
    bowling_economy NUMERIC(6,2),
    bowling_average NUMERIC(8,2),
    best_bowling_wickets INT,
    -- Fielding
    catches INT DEFAULT 0,
    run_outs INT DEFAULT 0,
    stumpings INT DEFAULT 0,
    CONSTRAINT uq_player_season UNIQUE (player_id, season_id)
);

CREATE INDEX IF NOT EXISTS idx_pss_player ON player_season_stats(player_id);
CREATE INDEX IF NOT EXISTS idx_pss_season ON player_season_stats(season_id);
CREATE INDEX IF NOT EXISTS idx_pss_player_season ON player_season_stats(player_id, season_id);

-- Update career views to use season-aggregate stats

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
    COALESCE(SUM(pss.sixes), 0) AS total_sixes
FROM players p
LEFT JOIN player_season_stats pss ON pss.player_id = p.id
GROUP BY p.id, p.name, p.organisation_id;

CREATE OR REPLACE VIEW career_bowling AS
SELECT
    p.id AS player_id,
    p.name,
    p.organisation_id,
    COALESCE(SUM(pss.matches), 0) AS games,
    COALESCE(SUM(pss.wickets), 0) AS total_wickets,
    ROUND(SUM(pss.runs_conceded)::numeric / NULLIF(SUM(pss.wickets), 0), 2) AS average,
    ROUND(SUM(pss.runs_conceded)::numeric / NULLIF(SUM(pss.overs), 0), 2) AS economy,
    MAX(pss.best_bowling_wickets) AS best_figures_wickets,
    COALESCE(SUM(pss.maidens), 0) AS total_maidens,
    COALESCE(SUM(pss.overs), 0) AS total_overs,
    COALESCE(SUM(pss.runs_conceded), 0) AS total_runs
FROM players p
LEFT JOIN player_season_stats pss ON pss.player_id = p.id
GROUP BY p.id, p.name, p.organisation_id;

CREATE OR REPLACE VIEW career_fielding AS
SELECT
    p.id AS player_id,
    p.name,
    p.organisation_id,
    COALESCE(SUM(pss.matches), 0) AS games,
    COALESCE(SUM(pss.catches), 0) AS total_catches,
    COALESCE(SUM(pss.run_outs), 0) AS total_run_outs,
    COALESCE(SUM(pss.stumpings), 0) AS total_stumpings,
    COALESCE(SUM(pss.catches + pss.run_outs + pss.stumpings), 0) AS total_dismissals
FROM players p
LEFT JOIN player_season_stats pss ON pss.player_id = p.id
GROUP BY p.id, p.name, p.organisation_id;

GRANT ALL PRIVILEGES ON TABLE player_season_stats TO cricket;
GRANT ALL PRIVILEGES ON SEQUENCE player_season_stats_id_seq TO cricket;
