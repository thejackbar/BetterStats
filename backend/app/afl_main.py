"""BetterStats AFL — the bs-afl-backend silo entrypoint.

One codebase, per-sport silos (docs/afl-betterstats-plan.md): this FastAPI app
is what the AFL deployment runs (`uvicorn app.afl_main:app`) against its own
database (bs-afl-database). The cricket entrypoint (app.main) is untouched and
unaware of this module.

Shares with cricket: the models Base + engine (pointed at the AFL DB purely by
DATABASE_URL), the whole auth stack, and the sync_runs bookkeeping. AFL-only:
the models in app.models.afl, the sync engine and routers under
services/afl + routers/afl.

Schema management: the AFL DB is created fresh by Base.metadata.create_all on
first boot — the shared tables plus the AFL ones. Cricket-specific tables
exist empty in this DB by design (any shared code path finds its table; the
data silo comes from the separate database, not a trimmed schema). Known
create_all caveat from CLAUDE.md: raw-SQL server defaults added by cricket
migrations (e.g. org_module_subscriptions.id's gen_random_uuid()) aren't in
the ORM metadata — nothing in the AFL pass-1 surface writes those tables.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config.settings import settings
from app.models.db import Base, engine
import app.models.afl  # noqa: F401 — register the AFL tables on the shared Base
from app.routers import auth
from app.routers.afl import (
    clubs as afl_clubs,
    organisations as afl_organisations,
    games as afl_games,
    players as afl_players,
    records as afl_records,
    leaderboard as afl_leaderboard,
    club_admin as afl_club_admin,
)

logger = logging.getLogger(__name__)

# A mis-wired deployment (AFL entrypoint + cricket env/database) must fail
# loudly at boot, not run the wrong sport against a production DB.
if settings.sport != "afl":
    raise RuntimeError(
        "app.afl_main started with SPORT=%r — the AFL silo requires SPORT=afl "
        "(and its own DATABASE_URL). Refusing to boot." % settings.sport
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        # gen_random_uuid() is built into Postgres 13+; pgcrypto kept for
        # any older local instance.
        try:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        except Exception:  # noqa: BLE001 — extension may need superuser; PG13+ doesn't need it
            logger.info("pgcrypto extension not created (fine on Postgres 13+)")
        await conn.run_sync(Base.metadata.create_all)

        # Raw-SQL tables the shared code writes that live outside the ORM
        # metadata (created by cricket's lifespan there; mirrored here).
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS login_attempts (
                id BIGSERIAL PRIMARY KEY,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                username TEXT NOT NULL,
                success BOOLEAN NOT NULL DEFAULT false,
                failure_reason TEXT,
                user_id UUID,
                org_id UUID,
                ip_hash TEXT,
                user_agent TEXT,
                country TEXT
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_login_attempts_created "
            "ON login_attempts(created_at DESC)"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS platform_settings (
                id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
                settings JSONB NOT NULL DEFAULT '{}',
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "INSERT INTO platform_settings (id, settings) VALUES (1, '{}') "
            "ON CONFLICT (id) DO NOTHING"))

    # Mark any sync runs orphaned by a restart, same as the cricket boot does.
    from app.models.db import async_session_maker
    async with async_session_maker() as session:
        await session.execute(text(
            "UPDATE sync_runs SET status = 'error', error = 'interrupted by restart', "
            "completed_at = NOW() WHERE status = 'running'"))
        await session.commit()
    yield


app = FastAPI(
    title="BetterStats AFL API",
    version="0.1.0",
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
app.include_router(afl_clubs.router)
app.include_router(afl_organisations.router)
app.include_router(afl_games.router)
app.include_router(afl_players.router)
app.include_router(afl_records.router)
app.include_router(afl_leaderboard.router)
app.include_router(afl_club_admin.router)


@app.get("/health")
async def health():
    return {"status": "ok", "sport": "afl"}
