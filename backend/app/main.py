import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import settings
from app.routers import auth, organisations, players, games, webhooks, leaderboard, records, admin
from app.jobs.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from sqlalchemy import text
    from app.models.db import engine
    async with engine.begin() as conn:
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS playhq_id TEXT"
        ))
        await conn.execute(text(
            "ALTER TABLE players ADD COLUMN IF NOT EXISTS playhq_id TEXT"
        ))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_player_org_playhq_id "
            "ON players(organisation_id, playhq_id) WHERE playhq_id IS NOT NULL"
        ))
        await conn.execute(text(
            "ALTER TABLE grades ADD COLUMN IF NOT EXISTS playhq_id TEXT"
        ))
        await conn.execute(text(
            "ALTER TABLE player_season_stats ADD COLUMN IF NOT EXISTS is_hs_not_out BOOLEAN DEFAULT FALSE"
        ))
        await conn.execute(text(
            "ALTER TABLE player_season_stats ADD COLUMN IF NOT EXISTS best_bowling_wickets INTEGER"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS merge_logs (
                id SERIAL PRIMARY KEY,
                merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID,
                keep_player_id UUID,
                keep_player_name TEXT,
                removed_player_id UUID,
                removed_player_name TEXT,
                removed_player_playhq_id TEXT,
                keep_original_playhq_id TEXT,
                moved_season_stat_ids JSONB DEFAULT '[]',
                batting_innings_ids JSONB DEFAULT '[]',
                bowling_spell_ids JSONB DEFAULT '[]',
                fielding_stat_ids JSONB DEFAULT '[]',
                fall_of_wicket_ids JSONB DEFAULT '[]',
                batter1_partnership_ids JSONB DEFAULT '[]',
                batter2_partnership_ids JSONB DEFAULT '[]',
                milestone_ids JSONB DEFAULT '[]',
                undone_at TIMESTAMPTZ
            )
        """))
    start_scheduler()
    logger.info("BetterStats API started")
    yield
    stop_scheduler()
    logger.info("BetterStats API stopped")


app = FastAPI(
    title="BetterStats API",
    description="Cricket statistics platform powered by PlayHQ",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(organisations.router)
app.include_router(players.router)
app.include_router(games.router)
app.include_router(leaderboard.router)
app.include_router(records.router)
app.include_router(webhooks.router)
app.include_router(admin.router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "betterstats-api"}
