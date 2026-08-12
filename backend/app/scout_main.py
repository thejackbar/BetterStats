"""BetterScout — the bs-scout-backend silo entrypoint.

A separate product, not another sport: this FastAPI app (`uvicorn
app.scout_main:app`) serves BetterScout's own tenant type ("Scout Org"),
completely unrelated to the club Organisation model the cricket and AFL
silos share. It follows the AFL silo's DEPLOYMENT shape (separate
entrypoint, own database, models registered on the shared Base) but does
NOT reuse the AFL/cricket auth stack — see services/scout_auth.py for why.

Foundational phase only: login/session + an empty authenticated shell for
the frontend to render against. Watchlists, the player-data cache, and
everything else land in later phases as their own routers, included here.

Schema management: the scout DB is created fresh by Base.metadata.create_all
on first boot — the shared cricket/AFL tables (unused, empty) plus
scout_orgs/scout_users. Same accepted tradeoff app.afl_main already
documents for sharing one ORM metadata registry across silos with separate
databases.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config.settings import settings
from app.models.db import Base, engine
import app.models.scout  # noqa: F401 — register scout_orgs/scout_users on the shared Base
from app.routers.scout import auth as scout_auth_router

logger = logging.getLogger(__name__)

# A mis-wired deployment (BetterScout entrypoint + cricket/AFL env or
# database) must fail loudly at boot, not silently run the wrong product.
if settings.product != "scout":
    raise RuntimeError(
        "app.scout_main started with PRODUCT=%r — the BetterScout silo "
        "requires PRODUCT=scout (and its own DATABASE_URL). Refusing to boot."
        % settings.product
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        # gen_random_uuid() is built into Postgres 13+; pgcrypto kept for any
        # older local instance (same as app.afl_main).
        try:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        except Exception:  # noqa: BLE001 — extension may need superuser; PG13+ doesn't need it
            logger.info("pgcrypto extension not created (fine on Postgres 13+)")
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title="BetterScout API",
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

app.include_router(scout_auth_router.router)


@app.get("/health")
async def health():
    return {"status": "ok", "product": "scout"}
