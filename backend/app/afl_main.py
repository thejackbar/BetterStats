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
from sqlalchemy import inspect as sa_inspect, text
from sqlalchemy.schema import CreateColumn

from app.config.settings import settings
from app.models.db import Base, engine
import app.models.afl  # noqa: F401 — register the AFL tables on the shared Base
from app.routers import auth, images
from app.routers.afl import (
    clubs as afl_clubs,
    organisations as afl_organisations,
    games as afl_games,
    players as afl_players,
    records as afl_records,
    leaderboard as afl_leaderboard,
    club_admin as afl_club_admin,
    players_admin as afl_players_admin,
    player_import as afl_player_import,
    merge as afl_merge,
    award_definitions as afl_award_definitions,
    achievements as afl_achievements,
    sponsors as afl_sponsors,
    users_admin as afl_users_admin,
    super_clubs as afl_super_clubs,
    imports as afl_imports,
    manual_entries as afl_manual_entries,
    result_imports as afl_result_imports,
    award_imports as afl_award_imports,
    seasons_admin as afl_seasons_admin,
    votes as afl_votes,
    public_votes as afl_public_votes,
    lineups as afl_lineups,
    honours as afl_honours,
)

logger = logging.getLogger(__name__)

# A mis-wired deployment (AFL entrypoint + cricket env/database) must fail
# loudly at boot, not run the wrong sport against a production DB.
if settings.sport != "afl":
    raise RuntimeError(
        "app.afl_main started with SPORT=%r. The AFL silo requires SPORT=afl "
        "(and its own DATABASE_URL). Refusing to boot." % settings.sport
    )


async def _sync_missing_columns(conn):
    """Base.metadata.create_all only creates TABLES that don't exist yet — it
    never ALTERs a table that's already there to add a column the model
    gained afterwards. That's invisible for cricket-only models (cricket's
    own main.py lifespan mirrors its migrations with idempotent ALTERs), but
    a column added to a SHARED model (Organisation, Player, User, ...) after
    the AFL database already has that table previously went unnoticed here —
    e.g. the club-custom-fonts migration added five columns to Organisation;
    AFL's organisations table predated it, so create_all silently skipped
    them and every request touching Organisation (login, /auth/me, club
    lookup — nearly everything) started 500ing with UndefinedColumnError.
    Diff the ORM metadata against the live schema and add whatever's
    missing, so any future shared-model column addition self-heals here
    instead of taking AFL down again. Each column runs in its own SAVEPOINT
    so one that can't apply cleanly (e.g. NOT NULL with no default on an
    already-populated table) is logged and skipped without aborting the
    outer transaction the rest of this lifespan still needs."""
    def _inspect(sync_conn):
        inspector = sa_inspect(sync_conn)
        return {t: {c["name"] for c in inspector.get_columns(t)} for t in inspector.get_table_names()}

    existing = await conn.run_sync(_inspect)
    for table in Base.metadata.tables.values():
        existing_cols = existing.get(table.name)
        if existing_cols is None:
            continue  # brand new table — create_all just made it with every column already
        for column in table.columns:
            if column.name in existing_cols:
                continue

            def _compile_ddl(sync_conn, col=column):
                return str(CreateColumn(col).compile(dialect=sync_conn.dialect))

            ddl = await conn.run_sync(_compile_ddl)
            try:
                async with conn.begin_nested():
                    await conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN IF NOT EXISTS {ddl}'))
                logger.info("afl_main: added missing column %s.%s (shared-model migration self-heal)",
                            table.name, column.name)
            except Exception:  # noqa: BLE001 — one bad column must not abort the whole boot
                logger.exception("afl_main: could not add column %s.%s — needs a manual ALTER",
                                  table.name, column.name)


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
        await _sync_missing_columns(conn)

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

        # Phase 1 admin-tools tables (Player list / Import Players / Merge
        # Grades / Awards / Sponsors / Users / All Clubs) — raw-SQL-only in
        # cricket's main.py lifespan (never added to the ORM Base), so they
        # don't exist in a fresh AFL database via create_all and must be
        # mirrored here the same idempotent way. Sponsors need no entry —
        # org_sponsors IS ORM-mapped (models.db.Sponsor) and already created
        # by create_all above.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id SERIAL PRIMARY KEY,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL,
                user_id UUID,
                action TEXT NOT NULL,
                target_type TEXT,
                target_id TEXT,
                details JSONB DEFAULT '{}'
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_audit_logs_org_created "
            "ON audit_logs(org_id, created_at DESC)"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY,
                merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL,
                canonical_name TEXT NOT NULL,
                alias_name TEXT NOT NULL,
                undone_at TIMESTAMPTZ
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_grade_merge_logs_org_active "
            "ON grade_merge_logs(org_id, alias_name) WHERE undone_at IS NULL"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS org_award_definitions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                org_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                category TEXT NOT NULL,
                subcategory TEXT,
                achievement TEXT,
                display_name TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                active BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_award_defs_org ON org_award_definitions(org_id)"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS player_achievements (
                id SERIAL PRIMARY KEY,
                org_id UUID NOT NULL,
                player_id UUID,
                player_name TEXT NOT NULL,
                season TEXT,
                season_end TEXT,
                category TEXT NOT NULL,
                subcategory TEXT,
                achievement TEXT NOT NULL,
                detail TEXT,
                import_batch_id UUID,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_achievements_player ON player_achievements(player_id)"))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_achievements_org ON player_achievements(org_id)"))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_achievements_import_batch "
            "ON player_achievements(import_batch_id)"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS achievement_import_batches (
                id UUID PRIMARY KEY,
                org_id UUID NOT NULL,
                filename TEXT,
                row_count INTEGER NOT NULL DEFAULT 0,
                created_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'imported',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                undone_at TIMESTAMPTZ
            )
        """))
        # Merge Players bookkeeping — AFL-scoped schema (only the two AFL stat
        # tables need tracking for undo, vs cricket's ~12-column merge_logs).
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS afl_merge_logs (
                id SERIAL PRIMARY KEY,
                merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL,
                keep_player_id UUID,
                keep_player_name TEXT,
                removed_player_id UUID,
                removed_player_name TEXT,
                removed_player_playhq_id TEXT,
                keep_original_playhq_id TEXT,
                line_ids JSONB DEFAULT '[]',
                undone_at TIMESTAMPTZ
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_afl_merge_logs_org "
            "ON afl_merge_logs(org_id, merged_at DESC)"))
        # A merge also carries the removed player's IMPORTED season rows and
        # honour-board rows across. Neither table has a foreign key to
        # players, so before this they were left pointing at a deleted id and
        # silently vanished from every read (career_totals joins players).
        # Their ids are recorded here for the same reason line_ids is: an undo
        # has to know exactly which rows to hand back. CREATE TABLE IF NOT
        # EXISTS never retrofits a column onto a deployed database, hence the
        # idempotent ALTERs.
        await conn.execute(text(
            "ALTER TABLE afl_merge_logs ADD COLUMN IF NOT EXISTS imported_stat_ids JSONB DEFAULT '[]'"))
        await conn.execute(text(
            "ALTER TABLE afl_merge_logs ADD COLUMN IF NOT EXISTS achievement_ids JSONB DEFAULT '[]'"))
        # Manual adjustments (routers/afl/manual_entries.py) move with a merge
        # too. Unlike the two above they DO cascade on the player FK, so
        # without the move a merge would delete the removed player's
        # corrections outright — worse than orphaning them. A log written
        # before this column existed reads as [], which is the right answer
        # for it: that merge never moved any.
        await conn.execute(text(
            "ALTER TABLE afl_merge_logs ADD COLUMN IF NOT EXISTS adjustment_ids JSONB DEFAULT '[]'"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS afl_merge_pair_ignores (
                id SERIAL PRIMARY KEY,
                org_id UUID NOT NULL,
                player_a_id UUID NOT NULL,
                player_b_id UUID NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (org_id, player_a_id, player_b_id)
            )
        """))
        # player_name_aliases (models.db.PlayerNameAlias) IS ORM-mapped, so
        # Base.metadata.create_all above already creates the table itself
        # (and _sync_missing_columns already self-heals any future column
        # added to it) — no CREATE TABLE mirror needed here. What create_all
        # can't add is the org-scoped uniqueness constraint (no
        # __table_args__ on the model) that seed_alias_on_rename's
        # ON CONFLICT (organisation_id, alias_key) relies on, so that index
        # is still mirrored explicitly.
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_player_name_alias_key "
            "ON player_name_aliases(organisation_id, alias_key)"))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_player_name_aliases_player "
            "ON player_name_aliases(player_id)"))
        # Import Stats — historical CSV import (routers/afl/imports.py). Reuses
        # the shared import_batches table (models.db.ImportBatch, already
        # ORM-mapped and 100% sport-agnostic — no mirror needed for it here).
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS afl_imported_stats (
                id SERIAL PRIMARY KEY,
                organisation_id UUID NOT NULL,
                import_batch_id UUID NOT NULL,
                player_id UUID NOT NULL,
                season_id UUID,
                season_label TEXT,
                grade_label TEXT,
                games_played INTEGER NOT NULL DEFAULT 0,
                goals INTEGER NOT NULL DEFAULT 0,
                behinds INTEGER NOT NULL DEFAULT 0,
                bog_count INTEGER NOT NULL DEFAULT 0,
                captain_games INTEGER NOT NULL DEFAULT 0,
                club_bf_votes INTEGER NOT NULL DEFAULT 0,
                comp_bf_votes INTEGER NOT NULL DEFAULT 0,
                grade_id UUID REFERENCES grades(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        # club_bf_votes/comp_bf_votes added after the table already existed on
        # deployed AFL databases — CREATE TABLE IF NOT EXISTS above doesn't
        # retrofit columns onto an existing table, so mirror them explicitly
        # (same idempotent-ALTER pattern cricket's main.py uses everywhere).
        # Deliberately NOT added to afl_player_season_stats: that table is
        # wholly derived from synced game lines (_rollup_season_stats deletes
        # + reinserts it every sync, see services/afl/sync.py) and PlayHQ has
        # no concept of club-internal B&F voting — a value stored there would
        # be silently wiped on the next sync. afl_imported_stats is untouched
        # by sync, so it's the only safe home for a historical vote tally.
        await conn.execute(text(
            "ALTER TABLE afl_imported_stats ADD COLUMN IF NOT EXISTS club_bf_votes INTEGER NOT NULL DEFAULT 0"))
        await conn.execute(text(
            "ALTER TABLE afl_imported_stats ADD COLUMN IF NOT EXISTS comp_bf_votes INTEGER NOT NULL DEFAULT 0"))
        # grade_id — promotes a resolved (season, grade label) pair from free
        # text into a real Grade row (routers/afl/imports.py::commit), so an
        # imported grade shows up in the grade filter and Merge Grades like
        # any synced one. grade_label stays alongside it as the always-present
        # free-text fallback for a row whose season never resolved.
        await conn.execute(text(
            "ALTER TABLE afl_imported_stats ADD COLUMN IF NOT EXISTS grade_id UUID REFERENCES grades(id) ON DELETE SET NULL"))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_afl_imported_stats_org_player "
            "ON afl_imported_stats(organisation_id, player_id)"))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_afl_imported_stats_grade "
            "ON afl_imported_stats(grade_id)"))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_afl_imported_stats_batch "
            "ON afl_imported_stats(import_batch_id)"))
        # Import Results — historical match results from a club's own
        # spreadsheet (routers/afl/result_imports.py). These land in the
        # shared games table with an afl_game_details row alongside, so the
        # columns below are what tells an imported game from a synced one.
        # create_all won't retrofit them onto a deployed AFL database, hence
        # the idempotent ALTERs (the same pattern the stats-import columns
        # above use).
        for col, ddl in (
            ("source", "TEXT NOT NULL DEFAULT 'playhq'"),
            ("import_batch_id", "UUID"),
            ("import_ref", "TEXT"),
            ("is_bye", "BOOLEAN NOT NULL DEFAULT FALSE"),
            ("is_forfeit", "BOOLEAN NOT NULL DEFAULT FALSE"),
            ("result_note", "TEXT"),
        ):
            await conn.execute(text(
                f"ALTER TABLE afl_game_details ADD COLUMN IF NOT EXISTS {col} {ddl}"))
        # An imported game has no PlayHQ id at all, so the column can't stay
        # NOT NULL once this tool exists.
        await conn.execute(text(
            "ALTER TABLE afl_game_details ALTER COLUMN playhq_id DROP NOT NULL"))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_afl_game_details_import_batch "
            "ON afl_game_details(import_batch_id)"))

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
app.include_router(images.router)
app.include_router(afl_clubs.router)
app.include_router(afl_organisations.router)
app.include_router(afl_games.router)
app.include_router(afl_players.router)
app.include_router(afl_records.router)
app.include_router(afl_leaderboard.router)
app.include_router(afl_honours.router)
app.include_router(afl_club_admin.router)
app.include_router(afl_players_admin.router)
app.include_router(afl_player_import.router)
app.include_router(afl_merge.router)
app.include_router(afl_award_definitions.router)
app.include_router(afl_achievements.router)
app.include_router(afl_sponsors.router)
app.include_router(afl_users_admin.router)
app.include_router(afl_super_clubs.router)
app.include_router(afl_imports.router)
app.include_router(afl_result_imports.router)
app.include_router(afl_award_imports.router)
app.include_router(afl_seasons_admin.router)
app.include_router(afl_manual_entries.router)
app.include_router(afl_lineups.router)
app.include_router(afl_votes.router)
# Unauthenticated by necessity — trust comes from the medal's link token, the
# player's PIN and a signed cookie, not from a session (see its docstring).
app.include_router(afl_public_votes.router)


@app.get("/health")
async def health():
    return {"status": "ok", "sport": "afl"}
