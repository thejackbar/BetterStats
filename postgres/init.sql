-- BetterStats PostgreSQL Schema
-- Multi-tenant cricket statistics platform

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- User accounts (players claiming profiles)
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Multi-tenant: one row per club
CREATE TABLE IF NOT EXISTS organisations (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    short_name TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Seasons per organisation
CREATE TABLE IF NOT EXISTS seasons (
    id UUID PRIMARY KEY,
    organisation_id UUID REFERENCES organisations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    year INT,
    synced_at TIMESTAMPTZ
);

-- Competition grades within a season
CREATE TABLE IF NOT EXISTS grades (
    id UUID PRIMARY KEY,
    season_id UUID REFERENCES seasons(id) ON DELETE CASCADE,
    name TEXT NOT NULL
);

-- Individual players
CREATE TABLE IF NOT EXISTS players (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    organisation_id UUID REFERENCES organisations(id) ON DELETE CASCADE,
    claimed BOOLEAN DEFAULT FALSE,
    user_id UUID REFERENCES users(id)
);

-- Match records
CREATE TABLE IF NOT EXISTS games (
    id UUID PRIMARY KEY,
    grade_id UUID REFERENCES grades(id) ON DELETE CASCADE,
    played_at DATE,
    home_team TEXT,
    away_team TEXT,
    result TEXT,
    winning_team TEXT,
    raw_payload JSONB
);

-- Batting innings per player per game
CREATE TABLE IF NOT EXISTS batting_innings (
    id SERIAL PRIMARY KEY,
    game_id UUID REFERENCES games(id) ON DELETE CASCADE,
    player_id UUID REFERENCES players(id) ON DELETE CASCADE,
    runs INT,
    balls INT,
    fours INT,
    sixes INT,
    strike_rate NUMERIC(6,2),
    dismissal_type TEXT,
    not_out BOOLEAN DEFAULT FALSE,
    batting_position INT
);

-- Bowling spells per player per game
CREATE TABLE IF NOT EXISTS bowling_spells (
    id SERIAL PRIMARY KEY,
    game_id UUID REFERENCES games(id) ON DELETE CASCADE,
    player_id UUID REFERENCES players(id) ON DELETE CASCADE,
    overs NUMERIC(4,1),
    maidens INT,
    runs INT,
    wickets INT,
    wides INT,
    no_balls INT,
    economy NUMERIC(5,2)
);

-- Fielding per player per game
CREATE TABLE IF NOT EXISTS fielding_stats (
    id SERIAL PRIMARY KEY,
    game_id UUID REFERENCES games(id) ON DELETE CASCADE,
    player_id UUID REFERENCES players(id) ON DELETE CASCADE,
    catches INT DEFAULT 0,
    run_outs INT DEFAULT 0,
    stumpings INT DEFAULT 0
);

-- Career batting averages
CREATE OR REPLACE VIEW career_batting AS
SELECT
    p.id AS player_id,
    p.name,
    p.organisation_id,
    COUNT(*) AS innings,
    SUM(runs) AS total_runs,
    MAX(runs) AS high_score,
    ROUND(SUM(runs)::numeric / NULLIF(COUNT(*) FILTER (WHERE NOT not_out), 0), 2) AS average,
    ROUND(SUM(runs)::numeric / NULLIF(SUM(balls), 0) * 100, 2) AS strike_rate,
    SUM(CASE WHEN runs >= 50 AND runs < 100 THEN 1 ELSE 0 END) AS fifties,
    SUM(CASE WHEN runs >= 100 THEN 1 ELSE 0 END) AS hundreds,
    SUM(fours) AS total_fours,
    SUM(sixes) AS total_sixes
FROM batting_innings bi
JOIN players p ON p.id = bi.player_id
GROUP BY p.id, p.name, p.organisation_id;

-- Career bowling averages
CREATE OR REPLACE VIEW career_bowling AS
SELECT
    p.id AS player_id,
    p.name,
    p.organisation_id,
    COUNT(*) AS games,
    SUM(wickets) AS total_wickets,
    ROUND(SUM(runs)::numeric / NULLIF(SUM(wickets), 0), 2) AS average,
    ROUND(SUM(runs)::numeric / NULLIF(SUM(overs), 0), 2) AS economy,
    MAX(wickets) AS best_figures_wickets,
    SUM(maidens) AS total_maidens,
    SUM(overs) AS total_overs,
    SUM(runs) AS total_runs
FROM bowling_spells bs
JOIN players p ON p.id = bs.player_id
GROUP BY p.id, p.name, p.organisation_id;

-- Career fielding totals
CREATE OR REPLACE VIEW career_fielding AS
SELECT
    p.id AS player_id,
    p.name,
    p.organisation_id,
    COUNT(*) AS games,
    SUM(catches) AS total_catches,
    SUM(run_outs) AS total_run_outs,
    SUM(stumpings) AS total_stumpings,
    SUM(catches + run_outs + stumpings) AS total_dismissals
FROM fielding_stats fs
JOIN players p ON p.id = fs.player_id
GROUP BY p.id, p.name, p.organisation_id;

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_batting_innings_player ON batting_innings(player_id);
CREATE INDEX IF NOT EXISTS idx_batting_innings_game ON batting_innings(game_id);
CREATE INDEX IF NOT EXISTS idx_bowling_spells_player ON bowling_spells(player_id);
CREATE INDEX IF NOT EXISTS idx_bowling_spells_game ON bowling_spells(game_id);
CREATE INDEX IF NOT EXISTS idx_fielding_stats_player ON fielding_stats(player_id);
CREATE INDEX IF NOT EXISTS idx_games_grade ON games(grade_id);
CREATE INDEX IF NOT EXISTS idx_games_played_at ON games(played_at);
CREATE INDEX IF NOT EXISTS idx_players_org ON players(organisation_id);
CREATE INDEX IF NOT EXISTS idx_seasons_org ON seasons(organisation_id);
CREATE INDEX IF NOT EXISTS idx_grades_season ON grades(season_id);

-- Grant full access to the cricket user (the DB owner in Docker, but needed for local setups)
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO cricket;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO cricket;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO cricket;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO cricket;
