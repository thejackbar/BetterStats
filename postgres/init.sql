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
    innings_number INT DEFAULT 1,
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
    innings_number INT DEFAULT 1,
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

-- Fall of wickets per innings per game
CREATE TABLE IF NOT EXISTS fall_of_wickets (
    id SERIAL PRIMARY KEY,
    game_id UUID REFERENCES games(id) ON DELETE CASCADE,
    innings_number INT NOT NULL,        -- 1 or 2
    wicket_number INT NOT NULL,         -- 1–10
    score_at_fall INT,
    overs_at_fall NUMERIC(5,1),
    player_id UUID REFERENCES players(id) ON DELETE SET NULL
);

-- Batting partnerships per innings per game
CREATE TABLE IF NOT EXISTS partnerships (
    id SERIAL PRIMARY KEY,
    game_id UUID REFERENCES games(id) ON DELETE CASCADE,
    innings_number INT NOT NULL,
    wicket_number INT NOT NULL,         -- partnership for Nth wicket
    batter1_id UUID REFERENCES players(id) ON DELETE SET NULL,
    batter2_id UUID REFERENCES players(id) ON DELETE SET NULL,
    runs INT DEFAULT 0,
    balls INT,
    batter1_runs INT,
    batter2_runs INT
);

-- Career milestones per player
CREATE TABLE IF NOT EXISTS milestones (
    id SERIAL PRIMARY KEY,
    player_id UUID REFERENCES players(id) ON DELETE CASCADE,
    game_id UUID REFERENCES games(id) ON DELETE SET NULL,
    milestone_type TEXT NOT NULL,       -- 'runs', 'wickets', 'matches', 'catches', 'fifty', 'hundred', 'five_for'
    milestone_value INT NOT NULL,       -- e.g. 500, 1000, 50, 100, 5, 10
    achieved_at DATE,
    detail TEXT                         -- human-readable e.g. "500 career runs"
);

-- Season-aggregate stats per player per season (primary stats store)
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

-- Career batting averages (aggregated from season stats)
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

-- Career bowling averages (aggregated from season stats)
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

-- Career fielding totals (aggregated from season stats)
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
CREATE INDEX IF NOT EXISTS idx_fow_game ON fall_of_wickets(game_id);
CREATE INDEX IF NOT EXISTS idx_partnerships_game ON partnerships(game_id);
CREATE INDEX IF NOT EXISTS idx_partnerships_batter1 ON partnerships(batter1_id);
CREATE INDEX IF NOT EXISTS idx_partnerships_batter2 ON partnerships(batter2_id);
CREATE INDEX IF NOT EXISTS idx_milestones_player ON milestones(player_id);
CREATE INDEX IF NOT EXISTS idx_milestones_type ON milestones(milestone_type);
CREATE INDEX IF NOT EXISTS idx_pss_player ON player_season_stats(player_id);
CREATE INDEX IF NOT EXISTS idx_pss_season ON player_season_stats(season_id);
CREATE INDEX IF NOT EXISTS idx_pss_player_season ON player_season_stats(player_id, season_id);

-- Grant full access to the cricket user (the DB owner in Docker, but needed for local setups)
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO cricket;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO cricket;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO cricket;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO cricket;
