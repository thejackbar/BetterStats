import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware

from app.config.settings import settings
from app.auth.modules import require_module
from app.routers import auth, organisations, players, games, webhooks, leaderboard, records, admin, achievements, clubs, club_admin, statlab, yearbooks, award_definitions, images, og_preview, notifications, seo, families, manual_entries, imports, usage, fees, fixtures, teams, availability, selection, ladders, iq, public_availability, net_manager, website, comms, public_comms, public_contact, klubpro_migration, bookmarks, merch, public_square
from app.jobs.scheduler import start_scheduler, stop_scheduler
from app.services.usage_tracker import record_event_bg

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
        # Super-admin club switching (migration 073) — the acted-as club for a
        # Better staff account. Defensive idempotent add so the API boots even
        # if alembic hasn't run yet.
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS active_club_id UUID "
            "REFERENCES organisations(id) ON DELETE SET NULL"
        ))
        # BetterSelect: player → selection-pool team assignment (migration 053).
        await conn.execute(text(
            "ALTER TABLE players ADD COLUMN IF NOT EXISTS squad_team_id UUID "
            "REFERENCES teams(id) ON DELETE SET NULL"
        ))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_player_org_playhq_id "
            "ON players(organisation_id, playhq_id) WHERE playhq_id IS NOT NULL"
        ))
        # BetterSelect self-service availability (migration 068) — defensive
        # idempotent adds so the API boots even if alembic hasn't run yet.
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS availability_link_token TEXT"
        ))
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
            "availability_self_service_enabled BOOLEAN NOT NULL DEFAULT false"
        ))
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
            "availability_require_pin BOOLEAN NOT NULL DEFAULT true"
        ))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_org_availability_token "
            "ON organisations(availability_link_token) WHERE availability_link_token IS NOT NULL"
        ))
        await conn.execute(text(
            "ALTER TABLE player_availability ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'admin'"
        ))
        # Fall of wicket: dismissed batter's scorecard name (migration 074) — names
        # the opposition half of our games (player_id NULL) from the DB, no live
        # fetch. Defensive idempotent add so the API boots even if alembic lags.
        await conn.execute(text(
            "ALTER TABLE fall_of_wickets ADD COLUMN IF NOT EXISTS batter_name TEXT"
        ))
        # Batting: flag caught-behind (caught by the wicketkeeper, migration 075).
        # Kept off the dismissal_type string so existing "count caught" readers are
        # untouched. Recreate the effective view with the column so the dismissal
        # breakdown can read it even if alembic lags. DDL must stay byte-identical
        # to migration 075's _VIEW_WITH_FLAG.
        await conn.execute(text(
            "ALTER TABLE batting_innings ADD COLUMN IF NOT EXISTS caught_behind BOOLEAN"
        ))
        await conn.execute(text("""
            CREATE OR REPLACE VIEW v_effective_batting_innings AS
            SELECT
                id, game_id, player_id, innings_number,
                runs, balls, fours, sixes, strike_rate,
                dismissal_type, not_out, batting_position, did_not_bat,
                'api'::text AS source,
                caught_behind
            FROM batting_innings
            UNION ALL
            SELECT
                id, manual_game_id AS game_id, player_id, innings_number,
                runs, balls, fours, sixes, strike_rate,
                dismissal_type, not_out, batting_position, did_not_bat,
                'manual'::text AS source,
                NULL::boolean AS caught_behind
            FROM manual_batting_innings
        """))
        # Bowling: flag caught-behind on bowler_wickets (migration 076). Read
        # directly (no effective view), so a plain idempotent add is enough.
        await conn.execute(text(
            "ALTER TABLE bowler_wickets ADD COLUMN IF NOT EXISTS caught_behind BOOLEAN"
        ))
        # BetterSelect → Net Manager: net/practice attendance + batting-queue
        # sessions. Defensive idempotent creates so the API boots even if a
        # numbered migration hasn't run yet (mirrors the self-service block).
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS net_sessions (
                id UUID PRIMARY KEY,
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                session_date DATE NOT NULL,
                label TEXT,
                notes TEXT,
                settings JSONB,
                status TEXT NOT NULL DEFAULT 'active',
                created_by UUID REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_net_sessions_org_date "
            "ON net_sessions(organisation_id, session_date DESC)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS net_attendance (
                id UUID PRIMARY KEY,
                session_id UUID NOT NULL REFERENCES net_sessions(id) ON DELETE CASCADE,
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                player_id UUID REFERENCES players(id) ON DELETE CASCADE,
                guest_name TEXT,
                batted BOOLEAN NOT NULL DEFAULT false,
                position INTEGER,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                CONSTRAINT uq_net_attendance_session_player UNIQUE (session_id, player_id)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_net_attendance_player "
            "ON net_attendance(player_id) WHERE player_id IS NOT NULL"
        ))
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS net_settings JSONB"
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
                bowler_wicket_ids JSONB DEFAULT '[]',
                fielder_wicket_ids JSONB DEFAULT '[]',
                grade_stat_ids JSONB DEFAULT '[]',
                appearance_game_ids JSONB DEFAULT '[]',
                undone_at TIMESTAMPTZ
            )
        """))
        # Backfill the merge-undo columns added for bowler_wickets,
        # player_season_grade_stats and game_appearances reassignment (the merge
        # used to silently cascade-delete those when removing the merged-away
        # player). Idempotent so existing merge_logs tables pick them up.
        for _col in (
            "bowler_wicket_ids", "fielder_wicket_ids", "grade_stat_ids", "appearance_game_ids",
        ):
            await conn.execute(text(
                f"ALTER TABLE merge_logs ADD COLUMN IF NOT EXISTS {_col} JSONB DEFAULT '[]'"
            ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS merge_pair_ignores (
                id SERIAL PRIMARY KEY,
                org_id UUID NOT NULL,
                player_a_id UUID NOT NULL,
                player_b_id UUID NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (org_id, player_a_id, player_b_id)
            )
        """))
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
            "ON grade_merge_logs(org_id, alias_name) WHERE undone_at IS NULL"
        ))
        # Club onboarding requests — submissions from the public marketing Contact
        # form (betterat.cricket/contact). Defensive idempotent create so the API
        # boots even if alembic 079 hasn't run yet (mirrors that migration).
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS club_onboarding_requests (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name TEXT NOT NULL,
                club TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT,
                association TEXT,
                grades TEXT,
                storage TEXT,
                timeline TEXT,
                club_url TEXT,
                message TEXT,
                status TEXT NOT NULL DEFAULT 'new',
                source TEXT NOT NULL DEFAULT 'contact_form',
                user_agent TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_club_onboarding_requests_created_at "
            "ON club_onboarding_requests (created_at DESC)"
        ))
        # Extra onboarding questions mirrored from the old Google Form
        # (migration 081). Idempotent so the API boots even before alembic runs.
        for _col in (
            "role", "founded_year", "playhq_status", "has_historical",
            "interests", "heard_about", "contact_method",
        ):
            await conn.execute(text(
                f"ALTER TABLE club_onboarding_requests ADD COLUMN IF NOT EXISTS {_col} TEXT"
            ))
        # Per-user admin bookmarks — favourites pinned to the top of the admin
        # sidebar for quick access (migration 082). Mirrored here so the API
        # boots before alembic runs. Keyed to the user, not the club.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS user_bookmarks (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                path TEXT NOT NULL,
                label TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_user_bookmark_path UNIQUE (user_id, path)
            )
        """))
        # Season aliases — admin can mark one season as merged into another so
        # they display and aggregate as a single season (e.g. Summer 25/26 +
        # Winter 25/26 → 2025/26). Soft model: no row rewrites; downstream
        # queries expand the canonical season_id to include all active alias
        # season_ids. Mirrors grade_merge_logs but keyed on UUIDs not names.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS season_aliases (
                id SERIAL PRIMARY KEY,
                merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL,
                canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                alias_season_id    UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                undone_at TIMESTAMPTZ
            )
        """))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_season_aliases_alias_active "
            "ON season_aliases(alias_season_id) WHERE undone_at IS NULL"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_season_aliases_canonical_active "
            "ON season_aliases(canonical_season_id) WHERE undone_at IS NULL"
        ))
        # Audit log — records sensitive admin actions (merges, settings,
        # destructive ops). Append-only from app code; no UPDATE/DELETE
        # paths so the trail can't be quietly edited. user_id nullable for
        # system-triggered actions (scheduled jobs, webhooks).
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
            "ON audit_logs(org_id, created_at DESC)"
        ))
        # Usage events — breadcrumbs of what features people use. Distinct
        # from audit_logs (which is admin-action history). Append-only,
        # written fire-and-forget by middleware so request latency isn't
        # affected. IP is stored as a truncated SHA-256 prefix; never raw.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS usage_events (
                id BIGSERIAL PRIMARY KEY,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                event_type TEXT NOT NULL DEFAULT 'api',
                method TEXT NOT NULL,
                path TEXT NOT NULL,
                route TEXT,
                status INTEGER NOT NULL DEFAULT 0,
                duration_ms INTEGER,
                user_id UUID,
                org_id UUID,
                ip_hash TEXT,
                user_agent TEXT,
                referer TEXT,
                metadata JSONB DEFAULT '{}'
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_usage_events_created "
            "ON usage_events(created_at DESC)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_usage_events_user_created "
            "ON usage_events(user_id, created_at DESC) WHERE user_id IS NOT NULL"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_usage_events_type_created "
            "ON usage_events(event_type, created_at DESC)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_usage_events_route_created "
            "ON usage_events(route, created_at DESC) WHERE route IS NOT NULL"
        ))
        # Geo enrichment columns. Country comes from Cloudflare's
        # `cf-ipcountry` header (free on every plan); region+city are
        # filled by an out-of-band ip-api.com lookup that runs after
        # the row is written.
        await conn.execute(text(
            "ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS country TEXT"
        ))
        await conn.execute(text(
            "ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS region TEXT"
        ))
        await conn.execute(text(
            "ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS city TEXT"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_usage_events_country "
            "ON usage_events(country) WHERE country IS NOT NULL"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS player_season_grade_stats (
                id SERIAL PRIMARY KEY,
                player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
                season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                grade_id  UUID NOT NULL REFERENCES grades(id)  ON DELETE CASCADE,
                matches          INTEGER DEFAULT 0,
                batting_innings  INTEGER DEFAULT 0,
                runs             INTEGER DEFAULT 0,
                not_outs         INTEGER DEFAULT 0,
                high_score       INTEGER,
                bowling_innings  INTEGER DEFAULT 0,
                wickets          INTEGER DEFAULT 0,
                runs_conceded    INTEGER DEFAULT 0,
                catches          INTEGER DEFAULT 0,
                run_outs         INTEGER DEFAULT 0,
                stumpings        INTEGER DEFAULT 0,
                synced_at        TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (player_id, season_id, grade_id)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_psgs_player_season "
            "ON player_season_grade_stats(player_id, season_id)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS player_achievements (
                id SERIAL PRIMARY KEY,
                org_id UUID NOT NULL,
                player_id UUID,
                player_name TEXT NOT NULL,
                season TEXT,
                category TEXT NOT NULL,
                subcategory TEXT,
                achievement TEXT NOT NULL,
                detail TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_achievements_player ON player_achievements(player_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_achievements_org ON player_achievements(org_id)"
        ))
        await conn.execute(text(
            "ALTER TABLE player_achievements ADD COLUMN IF NOT EXISTS season_end TEXT"
        ))
        # Mark any sync_runs left in 'running' state by a previous crash/restart
        # as errored so the dashboard doesn't show a phantom in-flight sync.
        await conn.execute(text("""
            UPDATE sync_runs
            SET status = 'error',
                error = COALESCE(error, 'Server restarted while sync was running'),
                completed_at = NOW(),
                updated_at = NOW()
            WHERE status = 'running'
        """))
        # Yearbook tables (v4)
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS yearbooks (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                org_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                status TEXT NOT NULL DEFAULT 'draft',
                published_at TIMESTAMPTZ,
                hero_image_path TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (org_id, season_id)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_yearbooks_status ON yearbooks(status)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS yearbook_sections (
                id SERIAL PRIMARY KEY,
                yearbook_id UUID NOT NULL REFERENCES yearbooks(id) ON DELETE CASCADE,
                section_type TEXT NOT NULL,
                title TEXT NOT NULL,
                content_markdown TEXT,
                ai_draft TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_enabled BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_yearbook_sections_yearbook ON yearbook_sections(yearbook_id)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS yearbook_honour_board (
                id SERIAL PRIMARY KEY,
                yearbook_id UUID NOT NULL REFERENCES yearbooks(id) ON DELETE CASCADE,
                position_title TEXT NOT NULL,
                player_id UUID REFERENCES players(id) ON DELETE SET NULL,
                name_override TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_yearbook_honour_board_yearbook ON yearbook_honour_board(yearbook_id)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS yearbook_images (
                id SERIAL PRIMARY KEY,
                yearbook_id UUID NOT NULL REFERENCES yearbooks(id) ON DELETE CASCADE,
                file_path TEXT NOT NULL,
                caption TEXT,
                image_type TEXT NOT NULL DEFAULT 'gallery',
                section_id INTEGER,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_yearbook_images_yearbook ON yearbook_images(yearbook_id)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS yearbook_club_awards (
                id SERIAL PRIMARY KEY,
                yearbook_id UUID NOT NULL REFERENCES yearbooks(id) ON DELETE CASCADE,
                award_name TEXT NOT NULL,
                player_id UUID REFERENCES players(id) ON DELETE SET NULL,
                name_override TEXT,
                notes TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_yearbook_awards_yearbook ON yearbook_club_awards(yearbook_id)"
        ))
        # Persist yearbook images as binary data in the DB so they survive
        # container recreation (the /app/uploads volume isn't guaranteed
        # persistent across deploys — same fix that was applied to club logos).
        await conn.execute(text(
            "ALTER TABLE yearbooks ADD COLUMN IF NOT EXISTS hero_image_data BYTEA"
        ))
        await conn.execute(text(
            "ALTER TABLE yearbooks ADD COLUMN IF NOT EXISTS hero_image_mime TEXT"
        ))
        await conn.execute(text(
            "ALTER TABLE yearbook_images ADD COLUMN IF NOT EXISTS image_data BYTEA"
        ))
        await conn.execute(text(
            "ALTER TABLE yearbook_images ADD COLUMN IF NOT EXISTS image_mime TEXT"
        ))
        # file_path is legacy for binary uploads — must be nullable.
        await conn.execute(text(
            "ALTER TABLE yearbook_images ALTER COLUMN file_path DROP NOT NULL"
        ))
        await conn.execute(text(
            "ALTER TABLE grades ADD COLUMN IF NOT EXISTS display_name_override TEXT"
        ))
        await conn.execute(text(
            "ALTER TABLE seasons ADD COLUMN IF NOT EXISTS display_order INTEGER"
        ))
        await conn.execute(text(
            "UPDATE seasons SET display_order = NULL WHERE display_order IS NOT NULL"
        ))
        # Award definitions table (customisable per-org award catalog)
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
            "CREATE INDEX IF NOT EXISTS ix_award_defs_org ON org_award_definitions(org_id)"
        ))
        # Sponsors table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS org_sponsors (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                website_url TEXT,
                logo_url TEXT,
                logo_data BYTEA,
                logo_mime TEXT,
                display_order INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_org_sponsors_org "
            "ON org_sponsors(organisation_id, display_order)"
        ))
        # Families — groups of related players within an org. The relationship
        # field is free text; suggestion-dismissals are sticky per surname.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS families (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                notes TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (organisation_id, name)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_families_org ON families(organisation_id)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS family_members (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                family_id UUID NOT NULL REFERENCES families(id) ON DELETE CASCADE,
                player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
                relationship TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (family_id, player_id)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_family_members_family ON family_members(family_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_family_members_player ON family_members(player_id)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS family_suggestions_dismissed (
                id SERIAL PRIMARY KEY,
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                surname_key TEXT NOT NULL,
                dismissed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                dismissed_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                UNIQUE (organisation_id, surname_key)
            )
        """))
        # ─── Front-end Website (migration 070) ───────────────────────────────
        # Per-club public website: news, editable pages, honour rolls,
        # committee and photo galleries under /{slug}/website. Off by default.
        for _col, _type in [
            ("website_enabled", "BOOLEAN NOT NULL DEFAULT false"),
            ("website_tagline", "TEXT"),
            ("website_intro", "TEXT"),
            ("website_social", "JSONB"),
            ("hero_image_data", "BYTEA"),
            ("hero_image_mime", "TEXT"),
            ("website_hero_all_pages", "BOOLEAN NOT NULL DEFAULT false"),
            ("website_committee", "JSONB"),
            ("website_honours_columns", "INTEGER NOT NULL DEFAULT 1"),
        ]:
            await conn.execute(text(
                f"ALTER TABLE organisations ADD COLUMN IF NOT EXISTS {_col} {_type}"
            ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS club_news (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                slug TEXT NOT NULL,
                summary TEXT,
                body TEXT,
                cover_image_data BYTEA,
                cover_image_mime TEXT,
                cover_image_url TEXT,
                author TEXT,
                is_published BOOLEAN NOT NULL DEFAULT true,
                is_pinned BOOLEAN NOT NULL DEFAULT false,
                published_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (organisation_id, slug)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_club_news_org "
            "ON club_news(organisation_id, is_published, published_at DESC)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS club_pages (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                slug TEXT NOT NULL,
                body TEXT,
                nav_label TEXT,
                show_in_nav BOOLEAN NOT NULL DEFAULT true,
                is_published BOOLEAN NOT NULL DEFAULT true,
                display_order INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (organisation_id, slug)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_club_pages_org ON club_pages(organisation_id, display_order)"
        ))
        # Nav hierarchy: a page can sit under a parent, and a "header" page is a
        # dropdown group with no page of its own (e.g. Teams → Mens/Womens).
        await conn.execute(text(
            "ALTER TABLE club_pages ADD COLUMN IF NOT EXISTS parent_id UUID REFERENCES club_pages(id) ON DELETE SET NULL"
        ))
        await conn.execute(text(
            "ALTER TABLE club_pages ADD COLUMN IF NOT EXISTS is_header BOOLEAN NOT NULL DEFAULT false"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS club_honour_boards (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                description TEXT,
                display_order INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_club_honour_boards_org "
            "ON club_honour_boards(organisation_id, display_order)"
        ))
        # An honour board can auto-populate from an achievements category
        # (e.g. "Hall of Fame") instead of manual entries.
        for _col in ("source_category", "source_subcategory"):
            await conn.execute(text(
                f"ALTER TABLE club_honour_boards ADD COLUMN IF NOT EXISTS {_col} TEXT"
            ))
        await conn.execute(text(
            "ALTER TABLE club_honour_boards ADD COLUMN IF NOT EXISTS columns INTEGER NOT NULL DEFAULT 1"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS club_honour_entries (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                board_id UUID NOT NULL REFERENCES club_honour_boards(id) ON DELETE CASCADE,
                year INTEGER,
                name TEXT NOT NULL,
                detail TEXT,
                player_id UUID REFERENCES players(id) ON DELETE SET NULL,
                display_order INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_club_honour_entries_board "
            "ON club_honour_entries(board_id, display_order)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS club_committee (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                name TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                bio TEXT,
                photo_data BYTEA,
                photo_mime TEXT,
                photo_url TEXT,
                display_order INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_club_committee_org "
            "ON club_committee(organisation_id, display_order)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS club_gallery_albums (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                description TEXT,
                display_order INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_club_gallery_albums_org "
            "ON club_gallery_albums(organisation_id, display_order)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS club_gallery_images (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                album_id UUID NOT NULL REFERENCES club_gallery_albums(id) ON DELETE CASCADE,
                image_data BYTEA,
                image_mime TEXT,
                image_url TEXT,
                caption TEXT,
                display_order INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_club_gallery_images_album "
            "ON club_gallery_images(album_id, display_order)"
        ))
        # BetterComms (BetterAdmin module) — bulk email (migration 069). Defensive
        # idempotent creates so the API boots even if the numbered migration
        # hasn't run yet (mirrors the BetterSelect / Net Manager blocks above).
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS comms_from_name TEXT"
        ))
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS comms_reply_to TEXT"
        ))
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS comms_sender_footer TEXT"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS comms_contacts (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                email TEXT NOT NULL,
                name TEXT,
                source TEXT NOT NULL DEFAULT 'manual',
                player_id UUID REFERENCES players(id) ON DELETE SET NULL,
                member_id UUID REFERENCES fee_members(id) ON DELETE SET NULL,
                subscribed BOOLEAN NOT NULL DEFAULT true,
                unsubscribed_at TIMESTAMPTZ,
                bounced BOOLEAN NOT NULL DEFAULT false,
                bounced_at TIMESTAMPTZ,
                tags JSONB NOT NULL DEFAULT '[]',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_comms_contact_org_email UNIQUE (organisation_id, email)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_comms_contacts_org ON comms_contacts(organisation_id)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS comms_campaigns (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                subject TEXT NOT NULL DEFAULT '',
                preheader TEXT,
                body_html TEXT,
                body_text TEXT,
                audience JSONB NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'draft',
                created_by UUID REFERENCES users(id) ON DELETE SET NULL,
                sent_at TIMESTAMPTZ,
                stats JSON NOT NULL DEFAULT '{}',
                error TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_comms_campaigns_org ON comms_campaigns(organisation_id, created_at DESC)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS comms_recipients (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                campaign_id UUID NOT NULL REFERENCES comms_campaigns(id) ON DELETE CASCADE,
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                contact_id UUID REFERENCES comms_contacts(id) ON DELETE SET NULL,
                email TEXT NOT NULL,
                name TEXT,
                status TEXT NOT NULL DEFAULT 'queued',
                provider_message_id TEXT,
                error TEXT,
                sent_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_comms_recipient_campaign_email UNIQUE (campaign_id, email)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_comms_recipients_campaign ON comms_recipients(campaign_id)"
        ))
        # KlubPro → BetterStats migration (migration 072) — sponsor contact
        # columns + audit/rollback bookkeeping. Idempotent defensive creates so
        # the API boots even if alembic hasn't run yet (mirrors the blocks above).
        await conn.execute(text("ALTER TABLE org_sponsors ADD COLUMN IF NOT EXISTS contact_name TEXT"))
        await conn.execute(text("ALTER TABLE org_sponsors ADD COLUMN IF NOT EXISTS email TEXT"))
        await conn.execute(text("ALTER TABLE org_sponsors ADD COLUMN IF NOT EXISTS klubpro_sponsor_id TEXT"))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_org_sponsor_klubpro "
            "ON org_sponsors(organisation_id, klubpro_sponsor_id) "
            "WHERE klubpro_sponsor_id IS NOT NULL"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS klubpro_migration_batches (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                kind TEXT NOT NULL,
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                club_mapping_id UUID,
                klubpro_club_id TEXT,
                status TEXT NOT NULL DEFAULT 'imported',
                counts JSONB,
                operator_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                operator_name TEXT,
                notes TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                rolled_back_at TIMESTAMPTZ
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_kp_batches_org "
            "ON klubpro_migration_batches(organisation_id, created_at DESC)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS klubpro_migration_backups (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                batch_id UUID NOT NULL REFERENCES klubpro_migration_batches(id) ON DELETE CASCADE,
                target_table TEXT NOT NULL,
                target_id UUID NOT NULL,
                action TEXT NOT NULL,
                before_data JSONB,
                after_data JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_kp_backups_batch "
            "ON klubpro_migration_backups(batch_id)"
        ))
        # BetterMerch (migration 083) — club stock register. Idempotent mirror so
        # the API boots before alembic runs (same pattern as the blocks above).
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS merch_products (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                category TEXT NOT NULL DEFAULT 'apparel',
                name TEXT NOT NULL,
                description TEXT,
                unit_cost NUMERIC(10,2),
                unit_price NUMERIC(10,2),
                low_stock_threshold INTEGER,
                supplier TEXT,
                notes TEXT,
                is_active BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_merch_products_org ON merch_products(organisation_id, category)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS merch_variants (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                product_id UUID NOT NULL REFERENCES merch_products(id) ON DELETE CASCADE,
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                label TEXT NOT NULL DEFAULT 'Standard',
                size TEXT,
                colour TEXT,
                sku TEXT,
                unit_cost NUMERIC(10,2),
                unit_price NUMERIC(10,2),
                quantity INTEGER NOT NULL DEFAULT 0,
                low_stock_threshold INTEGER,
                expiry_date DATE,
                is_active BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_merch_variants_product ON merch_variants(product_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_merch_variants_org ON merch_variants(organisation_id)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS merch_movements (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                variant_id UUID NOT NULL REFERENCES merch_variants(id) ON DELETE CASCADE,
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                kind TEXT NOT NULL DEFAULT 'adjustment',
                delta INTEGER NOT NULL DEFAULT 0,
                quantity_after INTEGER,
                unit_cost NUMERIC(10,2),
                unit_price NUMERIC(10,2),
                player_id UUID REFERENCES players(id) ON DELETE SET NULL,
                amount NUMERIC(10,2),
                paid BOOLEAN NOT NULL DEFAULT true,
                paid_at DATE,
                payment_method TEXT,
                note TEXT,
                occurred_on DATE,
                created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_merch_movements_variant ON merch_movements(variant_id, created_at)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_merch_movements_org ON merch_movements(organisation_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_merch_movements_player ON merch_movements(player_id)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS merch_assets (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                asset_tag TEXT,
                purchase_cost NUMERIC(10,2),
                purchase_date DATE,
                condition TEXT NOT NULL DEFAULT 'good',
                service_due_date DATE,
                replace_due_date DATE,
                status TEXT NOT NULL DEFAULT 'in_service',
                notes TEXT,
                is_active BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_merch_assets_org ON merch_assets(organisation_id)"
        ))
        # BetterMerch per-product tracking mode (migration 085).
        await conn.execute(text("ALTER TABLE merch_products ADD COLUMN IF NOT EXISTS for_resale BOOLEAN NOT NULL DEFAULT true"))
        # BetterMerch Square integration (migration 084) — per-club OAuth + mapping.
        await conn.execute(text("ALTER TABLE merch_products ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'manual'"))
        await conn.execute(text("ALTER TABLE merch_products ADD COLUMN IF NOT EXISTS square_object_id TEXT"))
        await conn.execute(text("ALTER TABLE merch_variants ADD COLUMN IF NOT EXISTS square_object_id TEXT"))
        await conn.execute(text("ALTER TABLE merch_movements ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'manual'"))
        await conn.execute(text("ALTER TABLE merch_movements ADD COLUMN IF NOT EXISTS external_ref TEXT"))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_merch_products_square ON merch_products(organisation_id, square_object_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_merch_variants_square ON merch_variants(organisation_id, square_object_id)"
        ))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_merch_movement_external_ref "
            "ON merch_movements(organisation_id, external_ref) WHERE external_ref IS NOT NULL"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS merch_square_connections (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                merchant_id TEXT,
                environment TEXT NOT NULL DEFAULT 'production',
                access_token TEXT,
                refresh_token TEXT,
                token_expires_at TIMESTAMPTZ,
                scopes TEXT,
                location_id TEXT,
                location_name TEXT,
                sync_enabled BOOLEAN NOT NULL DEFAULT true,
                sync_sales BOOLEAN NOT NULL DEFAULT true,
                last_sync_at TIMESTAMPTZ,
                last_sync_status TEXT,
                last_sync_error TEXT,
                sales_cursor TIMESTAMPTZ,
                connected_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                connected_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_merch_square_org UNIQUE (organisation_id)
            )
        """))
        # Seed Applecross with their specific trophy names (idempotent – skips if already seeded)
        from app.routers.award_definitions import seed_org_definitions, APPLECROSS_TEMPLATE
        acc_row = await conn.execute(
            text("SELECT id FROM organisations WHERE slug = 'applecross' LIMIT 1")
        )
        acc = acc_row.mappings().first()
        if acc:
            seeded = await seed_org_definitions(conn, str(acc["id"]), APPLECROSS_TEMPLATE)
            if seeded:
                logger.info(f"Seeded {seeded} award definitions for Applecross")
    # Ensure uploads directory exists
    upload_dir = Path("/app/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    # Generate yearbook stubs for any seasons that don't have one yet
    from app.models.db import async_session_maker as AsyncSessionLocal
    from app.routers.yearbooks import generate_all_stubs
    async with AsyncSessionLocal() as stub_session:
        await generate_all_stubs(stub_session)

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


# Paths the breadcrumb middleware ignores. Health checks, uploaded file
# serving, the notification-count poll (every 60s — would dominate the
# log), and the usage endpoints themselves (avoid recursion). Prefix
# match.
_USAGE_SKIP_PREFIXES = (
    "/health",
    "/uploads/",
    "/club-admin/notifications/count",
    "/usage/event",
    "/club-admin/usage/",
    "/docs",
    "/openapi.json",
    "/favicon",
)


def _decode_user_id(request: Request) -> str | None:
    """Best-effort user_id extraction from the session cookie. Cheap — no DB."""
    token = request.cookies.get("bs_session")
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        sub = payload.get("sub")
        if not sub:
            return None
        # Validate it's a UUID so we don't insert garbage
        uuid.UUID(sub)
        return sub
    except (JWTError, ValueError, KeyError):
        return None


def _client_ip(request: Request) -> str | None:
    # Cloudflare sets cf-connecting-ip to the real client IP. Prefer it
    # when present so we don't accidentally geo-locate the CF edge.
    cf = request.headers.get("cf-connecting-ip")
    if cf:
        return cf.strip()
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    if request.client:
        return request.client.host
    return None


def _cf_country(request: Request) -> str | None:
    """Cloudflare's per-request country header. Free on all CF plans."""
    cc = request.headers.get("cf-ipcountry")
    if not cc or cc == "XX":
        return None
    return cc.strip().upper()[:2]


class UsageTrackingMiddleware(BaseHTTPMiddleware):
    """Drop a breadcrumb for every API request that isn't on the skip list."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path or ""
        if request.method == "OPTIONS" or any(path.startswith(p) for p in _USAGE_SKIP_PREFIXES):
            return await call_next(request)

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = int((time.perf_counter() - start) * 1000)

        # Route template (e.g. /players/{player_id}) is more useful than the
        # raw path for aggregation. Falls back to raw path if FastAPI didn't
        # match a route (404s etc.).
        route_template = None
        scope_route = request.scope.get("route")
        if scope_route is not None and getattr(scope_route, "path", None):
            route_template = scope_route.path

        record_event_bg(
            event_type="api",
            method=request.method,
            path=path,
            route=route_template,
            status=response.status_code,
            duration_ms=duration_ms,
            user_id=_decode_user_id(request),
            ip=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            referer=request.headers.get("referer"),
            country=_cf_country(request),
        )
        return response


app.add_middleware(UsageTrackingMiddleware)

app.include_router(auth.router)
app.include_router(clubs.router)
app.include_router(website.public_router)   # Front-end Website (public, Core)
app.include_router(website.admin_router)    # Front-end Website (admin CRUD)
app.include_router(club_admin.router)
app.include_router(organisations.router)
app.include_router(players.router)
app.include_router(games.router)
app.include_router(leaderboard.router)
app.include_router(records.router)
app.include_router(webhooks.router)
app.include_router(admin.router)
app.include_router(achievements.router)
app.include_router(award_definitions.router)
app.include_router(statlab.router)
app.include_router(yearbooks.router)
app.include_router(images.router)
app.include_router(og_preview.router)
app.include_router(notifications.router)
app.include_router(bookmarks.router)  # per-user admin sidebar favourites
app.include_router(seo.router)
app.include_router(families.router)
app.include_router(manual_entries.router)
app.include_router(imports.router)  # BetterImport — overlap-safe historical CSV import
app.include_router(klubpro_migration.router)  # KlubPro → BetterStats migration (super-admin onboarding)
app.include_router(usage.router)
# ─── Better ecosystem module gating ──────────────────────────────────────────
# These routers are the discrete Better modules; require_module() returns 402
# (with an upsell payload) when the caller's club isn't entitled. Core routers
# above are always on. BetterSocials' backend surface is gated per-route in
# admin.py (it shares the admin router). See app/auth/modules.py.
app.include_router(fees.router, dependencies=[Depends(require_module("fees"))])           # BetterFees (BetterAdmin)
app.include_router(comms.router, dependencies=[Depends(require_module("comms"))])         # BetterComms (BetterAdmin)
app.include_router(merch.router, dependencies=[Depends(require_module("merch"))])         # BetterMerch (BetterAdmin)
app.include_router(fixtures.router, dependencies=[Depends(require_module("select"))])     # BetterSelect
app.include_router(teams.router, dependencies=[Depends(require_module("select"))])        # BetterSelect
app.include_router(availability.router, dependencies=[Depends(require_module("select"))]) # BetterSelect
app.include_router(selection.router, dependencies=[Depends(require_module("select"))])    # BetterSelect
app.include_router(net_manager.router, dependencies=[Depends(require_module("select"))])  # BetterSelect (Net Manager)
# Player-facing self-service availability (magic link + PIN). Unauthenticated by
# design — it resolves the club from the link token and enforces entitlement +
# enabled-flag itself, so it is NOT wrapped in require_module.
app.include_router(public_availability.router)                                            # BetterSelect (public)
app.include_router(public_comms.router)                                                   # BetterComms (public unsubscribe)
app.include_router(public_contact.router)                                                 # Marketing Contact form (public intake)
app.include_router(public_square.router)                                                  # BetterMerch (Square OAuth callback)
app.include_router(ladders.router)  # standings power public club pages — not gated
app.include_router(iq.router, dependencies=[Depends(require_module("iq"))])               # BetterIQ

# Serve uploaded files (hero images, gallery photos)
_upload_dir = Path("/app/uploads")
_upload_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(_upload_dir)), name="uploads")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "betterstats-api"}
