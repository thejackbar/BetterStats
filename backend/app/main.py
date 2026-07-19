import asyncio
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
from app.routers import auth, organisations, players, games, webhooks, leaderboard, records, admin, achievements, clubs, club_admin, statlab, yearbooks, award_definitions, images, og_preview, notifications, seo, families, manual_entries, imports, player_import, usage, fees, fixtures, teams, availability, selection, ladders, iq, public_availability, net_manager, website, comms, public_comms, public_ses, public_contact, klubpro_migration, bookmarks, merch, public_square, public_xero, fantasy, public_fantasy, marketing, login_attempts, meta_ads, pipeline_gauge, self_serve_trial, public_self_serve, onboarding_wizard, wizard_analytics, billing, public_stripe, discount_coupons
from app.jobs.scheduler import start_scheduler, stop_scheduler
from app.services.usage_tracker import record_event_bg

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


async def _run_stripe_subscription_sweep():
    """Background counterpart to lifespan's boot sequence — see the comment
    at its one call site for why this must never be awaited inline there."""
    from app.models.db import async_session_maker as AsyncSessionLocal
    from app.services import stripe_billing as _stripe_billing
    async with AsyncSessionLocal() as session:
        try:
            fixed = await asyncio.wait_for(
                _stripe_billing.sweep_dangling_stripe_subscriptions(session), timeout=30,
            )
            if fixed:
                logger.info(f"Stripe subscription sweep: repaired {len(fixed)} club(s)")
        except Exception as e:
            await session.rollback()
            logger.error(f"Stripe subscription sweep failed or timed out: {e}")


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
        # Grade category label + public visibility (migration 123) — clubs label
        # grades (Senior/Junior/Women's/Masters/Mixed) and choose which to share
        # publicly. Defensive idempotent adds so the API boots even if alembic lags.
        await conn.execute(text(
            "ALTER TABLE grades ADD COLUMN IF NOT EXISTS category TEXT"
        ))
        await conn.execute(text(
            "ALTER TABLE grades ADD COLUMN IF NOT EXISTS "
            "is_public BOOLEAN NOT NULL DEFAULT true"
        ))
        # BetterIQ scouting cards (migration 094): manual batting/bowling intel —
        # the ball-level read CA can't give us (vulnerable-to bowler types, a
        # length×line weakness grid, favoured shots, stock ball + variations).
        # Two JSONB blobs on the existing opponent tag row + a parallel table for
        # our own players. Defensive idempotent adds/creates so the API boots even
        # if alembic lags.
        await conn.execute(text(
            "ALTER TABLE opponent_player_tags ADD COLUMN IF NOT EXISTS batting_intel JSONB"
        ))
        await conn.execute(text(
            "ALTER TABLE opponent_player_tags ADD COLUMN IF NOT EXISTS bowling_intel JSONB"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS player_scouting_cards (
                id SERIAL PRIMARY KEY,
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
                batting_intel JSONB,
                bowling_intel JSONB,
                updated_by UUID REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_player_scouting_org_player UNIQUE (organisation_id, player_id)
            )
        """))
        # Marketing club directory (migration 095): the crawled CA/grassroots club
        # universe for BetterCricket's own outreach. Prospects, not customers, so
        # decoupled from organisations (existing_org_id links rows that ARE customers
        # so outreach can skip them). Resumable through the table: detail_fetched_at
        # IS NULL marks a frontier node discovered via an affiliation but not yet
        # detailed. Idempotent creates so the API boots even if alembic lags.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS marketing_clubs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                grassroots_guid TEXT NOT NULL,
                playhq_id TEXT,
                mycricket_id INTEGER,
                name TEXT NOT NULL,
                short_name TEXT,
                kind TEXT NOT NULL DEFAULT 'club',
                association_name TEXT,
                association_guid TEXT,
                associations JSONB,
                website_url TEXT,
                contact_email TEXT,
                contact_phone TEXT,
                address_line1 TEXT,
                address_line2 TEXT,
                suburb TEXT,
                state TEXT,
                postcode TEXT,
                country TEXT,
                latitude NUMERIC(10,6),
                longitude NUMERIC(10,6),
                logo_url TEXT,
                description TEXT,
                is_playhq BOOLEAN,
                status TEXT NOT NULL DEFAULT 'new',
                source TEXT NOT NULL DEFAULT 'grassroots_api',
                raw_json JSONB,
                existing_org_id UUID REFERENCES organisations(id) ON DELETE SET NULL,
                detail_fetched_at TIMESTAMPTZ,
                first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_crawled_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_marketing_club_guid UNIQUE (grassroots_guid)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_marketing_clubs_frontier "
            "ON marketing_clubs(detail_fetched_at, first_seen_at)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_marketing_clubs_state_status "
            "ON marketing_clubs(state, status)"
        ))
        # Migration 096: associations list + its enrichment-frontier index (idempotent
        # so the API boots even if alembic lags / the table predates the column).
        await conn.execute(text(
            "ALTER TABLE marketing_clubs ADD COLUMN IF NOT EXISTS associations JSONB"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_marketing_clubs_assoc_pending "
            "ON marketing_clubs(associations) WHERE associations IS NULL"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS marketing_club_contacts (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                marketing_club_id UUID NOT NULL REFERENCES marketing_clubs(id) ON DELETE CASCADE,
                full_name TEXT,
                role TEXT,
                role_rank INTEGER NOT NULL DEFAULT 99,
                email TEXT,
                mobile TEXT,
                source TEXT NOT NULL DEFAULT 'api',
                subscribed BOOLEAN NOT NULL DEFAULT TRUE,
                unsubscribed_at TIMESTAMPTZ,
                bounced BOOLEAN NOT NULL DEFAULT FALSE,
                bounced_at TIMESTAMPTZ,
                notes TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_marketing_contact_club_email "
            "ON marketing_club_contacts(marketing_club_id, lower(email)) WHERE email IS NOT NULL"
        ))
        # Migration 097: per-contact outreach selection (which contacts get emailed).
        await conn.execute(text(
            "ALTER TABLE marketing_club_contacts ADD COLUMN IF NOT EXISTS "
            "outreach_selected BOOLEAN NOT NULL DEFAULT FALSE"
        ))
        # Migration 114: per-contact exported-to-BetterComms flag.
        await conn.execute(text(
            "ALTER TABLE marketing_club_contacts ADD COLUMN IF NOT EXISTS exported_at TIMESTAMPTZ"))
        # Migration 098: emailed tracking + comms link.
        await conn.execute(text(
            "ALTER TABLE marketing_clubs ADD COLUMN IF NOT EXISTS emailed_at TIMESTAMPTZ"))
        await conn.execute(text(
            "ALTER TABLE marketing_clubs ADD COLUMN IF NOT EXISTS emailed_via TEXT"))
        await conn.execute(text(
            "ALTER TABLE marketing_clubs ADD COLUMN IF NOT EXISTS emailed_note TEXT"))
        await conn.execute(text(
            "ALTER TABLE comms_contacts ADD COLUMN IF NOT EXISTS marketing_club_id UUID "
            "REFERENCES marketing_clubs(id) ON DELETE SET NULL"))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_comms_contacts_marketing_club "
            "ON comms_contacts(marketing_club_id)"))
        # Migration 099: admin exclusion flag (marketing + comms).
        await conn.execute(text(
            "ALTER TABLE marketing_clubs ADD COLUMN IF NOT EXISTS excluded BOOLEAN NOT NULL DEFAULT FALSE"))
        await conn.execute(text(
            "ALTER TABLE marketing_clubs ADD COLUMN IF NOT EXISTS excluded_at TIMESTAMPTZ"))
        await conn.execute(text(
            "ALTER TABLE comms_contacts ADD COLUMN IF NOT EXISTS excluded BOOLEAN NOT NULL DEFAULT FALSE"))
        await conn.execute(text(
            "ALTER TABLE comms_contacts ADD COLUMN IF NOT EXISTS excluded_at TIMESTAMPTZ"))
        # Migration 100: runtime stop/start control for the marketing crawl.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS marketing_crawl_control (
                id SMALLINT PRIMARY KEY,
                paused BOOLEAN NOT NULL DEFAULT FALSE,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "INSERT INTO marketing_crawl_control (id, paused) VALUES (1, FALSE) "
            "ON CONFLICT (id) DO NOTHING"))
        # Migration 101: per-club editable UTM code (defaulted from the name).
        await conn.execute(text(
            "ALTER TABLE marketing_clubs ADD COLUMN IF NOT EXISTS utm_code TEXT"))
        # Sales-pipeline state (super-admin set in the Clubs Directory): which
        # modules a prospect is trialing / has requested a trial for, and its
        # demo follow-on state. Powers the directory-aware segment filters.
        await conn.execute(text(
            "ALTER TABLE marketing_clubs ADD COLUMN IF NOT EXISTS trial_modules JSONB NOT NULL DEFAULT '[]'"))
        await conn.execute(text(
            "ALTER TABLE marketing_clubs ADD COLUMN IF NOT EXISTS requested_trial_modules JSONB NOT NULL DEFAULT '[]'"))
        await conn.execute(text(
            "ALTER TABLE marketing_clubs ADD COLUMN IF NOT EXISTS demo_status TEXT"))
        # Sales disposition: a club contacted and explicitly declined. Manual, so it
        # overrides the computed engagement tier (and isn't recomputed away).
        await conn.execute(text(
            "ALTER TABLE marketing_clubs ADD COLUMN IF NOT EXISTS not_interested "
            "BOOLEAN NOT NULL DEFAULT FALSE"))
        # Cached Twenty engagementScore/-Tier, written by every _engagement() call —
        # see the column comment in models/db.py for why.
        await conn.execute(text(
            "ALTER TABLE marketing_clubs ADD COLUMN IF NOT EXISTS engagement_score INTEGER"))
        await conn.execute(text(
            "ALTER TABLE marketing_clubs ADD COLUMN IF NOT EXISTS engagement_tier TEXT"))
        await conn.execute(text(
            "ALTER TABLE marketing_clubs ADD COLUMN IF NOT EXISTS engagement_scored_at "
            "TIMESTAMPTZ"))
        # Self-serve trial registration admin-details form (migration 135) — nothing
        # downstream reads these yet, defensive idempotent add so the API boots even
        # if alembic lags.
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name TEXT"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_name TEXT"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS mobile_number TEXT"))
        # Self-serve trial registration email verification codes (migration 136).
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS self_serve_email_verifications (
                id UUID PRIMARY KEY,
                email TEXT NOT NULL,
                code_hash TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                expires_at TIMESTAMPTZ NOT NULL,
                verified_at TIMESTAMPTZ,
                superseded_at TIMESTAMPTZ,
                attempt_count INTEGER NOT NULL DEFAULT 0
            )
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_self_serve_email_verifications_email
            ON self_serve_email_verifications(email)
        """))
        # Self-serve trial registration legal acknowledgements (migration 137).
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS self_serve_acknowledgements (
                id UUID PRIMARY KEY,
                email TEXT NOT NULL,
                club_name TEXT NOT NULL,
                terms_version TEXT NOT NULL,
                privacy_version TEXT NOT NULL,
                accepted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                ip_hash TEXT,
                user_agent TEXT
            )
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_self_serve_acknowledgements_email
            ON self_serve_acknowledgements(email)
        """))
        # Self-serve trial registration idempotency keys (migration 138).
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS self_serve_idempotency_keys (
                idempotency_key TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'validated',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        # Result refs on the idempotency key (migration 139) — so a replayed
        # submission can return which club/user it created.
        await conn.execute(text(
            "ALTER TABLE self_serve_idempotency_keys ADD COLUMN IF NOT EXISTS org_id UUID"))
        await conn.execute(text(
            "ALTER TABLE self_serve_idempotency_keys ADD COLUMN IF NOT EXISTS user_id UUID"))
        # Club onboarding wizard progress, per club (migration 140, Phase 15).
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS onboarding_wizard_state (
                organisation_id UUID PRIMARY KEY REFERENCES organisations(id) ON DELETE CASCADE,
                completed_steps JSON NOT NULL DEFAULT '[]',
                dismissed_at TIMESTAMPTZ,
                sync_steps_shown_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        # Setup Wizard explicit skips (migration 157).
        await conn.execute(text(
            "ALTER TABLE onboarding_wizard_state "
            "ADD COLUMN IF NOT EXISTS skipped_steps JSON NOT NULL DEFAULT '[]'"))
        # Setup Wizard "doesn't apply" steps + persisted socials style (migration 162).
        await conn.execute(text(
            "ALTER TABLE onboarding_wizard_state "
            "ADD COLUMN IF NOT EXISTS na_steps JSON NOT NULL DEFAULT '[]'"))
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS socials_style JSONB"))
        # Setup Wizard analytics: real "ever opened" signal (migration 163).
        await conn.execute(text(
            "ALTER TABLE onboarding_wizard_state "
            "ADD COLUMN IF NOT EXISTS first_opened_at TIMESTAMPTZ"))
        # Club-user invite flow — set-your-password-by-email (migration 141).
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS invite_token TEXT UNIQUE"))
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS invite_token_expires_at TIMESTAMPTZ"))
        # Fix FK cascade drift on legacy per-game/per-player stat tables
        # (migration 142) — see that migration file for the full rationale.
        # Cheap no-op on a repeat run: only touches a constraint whose
        # confdeltype doesn't already match.
        await conn.execute(text(r"""
            DO $$
            DECLARE
              spec RECORD;
              cname TEXT;
            BEGIN
              FOR spec IN SELECT * FROM (VALUES
                ('batting_innings',  'game_id',    'games',   'c'),
                ('batting_innings',  'player_id',  'players', 'c'),
                ('bowling_spells',   'game_id',    'games',   'c'),
                ('bowling_spells',   'player_id',  'players', 'c'),
                ('fielding_stats',   'game_id',    'games',   'c'),
                ('fielding_stats',   'player_id',  'players', 'c'),
                ('bowler_wickets',   'game_id',    'games',   'c'),
                ('bowler_wickets',   'bowler_id',  'players', 'c'),
                ('bowler_wickets',   'fielder_id', 'players', 'n'),
                ('game_appearances', 'game_id',    'games',   'c'),
                ('game_appearances', 'player_id',  'players', 'c'),
                ('fall_of_wickets',  'game_id',    'games',   'c'),
                ('fall_of_wickets',  'player_id',  'players', 'n'),
                ('partnerships',     'game_id',    'games',   'c'),
                ('partnerships',     'batter1_id', 'players', 'n'),
                ('partnerships',     'batter2_id', 'players', 'n'),
                ('milestones',       'player_id',  'players', 'c'),
                ('milestones',       'game_id',    'games',   'n'),
                ('fee_match_days',   'game_id',    'games',   'c')
              ) AS t(tbl, col, target, mode)
              LOOP
                IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = spec.tbl AND relkind = 'r') THEN
                  CONTINUE;
                END IF;
                cname := spec.tbl || '_' || spec.col || '_fkey';
                IF NOT EXISTS (
                  SELECT 1 FROM pg_constraint c
                  JOIN pg_class t ON t.oid = c.conrelid
                  WHERE t.relname = spec.tbl AND c.conname = cname AND c.confdeltype = spec.mode
                ) THEN
                  EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', spec.tbl, cname);
                  EXECUTE format(
                    'ALTER TABLE %I ADD CONSTRAINT %I FOREIGN KEY (%I) REFERENCES %I(id) ON DELETE %s NOT VALID',
                    spec.tbl, cname, spec.col, spec.target,
                    CASE spec.mode WHEN 'c' THEN 'CASCADE' ELSE 'SET NULL' END
                  );
                  EXECUTE format('ALTER TABLE %I VALIDATE CONSTRAINT %I', spec.tbl, cname);
                END IF;
              END LOOP;
            END $$;
        """))
        # Club soft-delete / archive (migration 143).
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ"))
        # Admin-triggered "reset your password" email for an existing club-user
        # account (migration 144) — separate token pair from invite_token above.
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_reset_token TEXT UNIQUE"))
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_reset_token_expires_at TIMESTAMPTZ"))
        # Club-user email is format-validated only, not required to be unique
        # (migration 145) — drop whatever the original UNIQUE constraint on
        # users.email was named, looked up by column rather than a fixed name.
        await conn.execute(text("""
            DO $$
            DECLARE
                con record;
            BEGIN
                FOR con IN
                    SELECT conname FROM pg_constraint
                    WHERE conrelid = 'users'::regclass
                      AND contype = 'u'
                      AND conkey = (
                          SELECT array_agg(attnum) FROM pg_attribute
                          WHERE attrelid = 'users'::regclass AND attname = 'email'
                      )
                LOOP
                    EXECUTE format('ALTER TABLE users DROP CONSTRAINT %I', con.conname);
                END LOOP;
            END $$;
        """))
        # Fix FK cascade drift on players.user_id -> users(id) (migration
        # 146) — was NO ACTION in the live DB (a retained-but-unused legacy
        # column, not even ORM-declared), so deleting a user with a linked
        # players row silently rolled back the whole delete. See that
        # migration file for the full rationale.
        await conn.execute(text(r"""
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                WHERE t.relname = 'players' AND c.conname = 'players_user_id_fkey' AND c.confdeltype = 'n'
              ) THEN
                ALTER TABLE players DROP CONSTRAINT IF EXISTS players_user_id_fkey;
                ALTER TABLE players ADD CONSTRAINT players_user_id_fkey
                  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL NOT VALID;
                ALTER TABLE players VALIDATE CONSTRAINT players_user_id_fkey;
              END IF;
            END $$;
        """))
        await conn.execute(text(r"""
            UPDATE marketing_clubs
            SET utm_code = lower(regexp_replace(split_part(name, ' ', 1), '[^a-zA-Z0-9]', '', 'g'))
                           || '-cricket-club'
            WHERE utm_code IS NULL
              AND coalesce(regexp_replace(split_part(name, ' ', 1), '[^a-zA-Z0-9]', '', 'g'), '') <> ''
        """))
        # Migration 102: association registry for the automatic roster sweep.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS marketing_associations (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                club_count INTEGER NOT NULL DEFAULT 0,
                last_resolved_at TIMESTAMPTZ,
                first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_marketing_assoc_resolve "
            "ON marketing_associations(last_resolved_at)"))
        # Migration 105: derived association short code (acronym) for shortcode search.
        await conn.execute(text(
            "ALTER TABLE marketing_associations ADD COLUMN IF NOT EXISTS short_code TEXT"))
        # Migration 117: manual UTM → club mapping for the Clubs Directory visit
        # breadcrumbs. A campaign's utm_source isn't always the club's utm_code
        # (e.g. utm_source='executive' for Leederville), so an operator maps the
        # raw value to a club here. marketing_club_id NULL = explicitly ignored
        # (ad/referrer noise like 'meta', 'chatgpt.com').
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS marketing_utm_aliases (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                utm_value TEXT NOT NULL UNIQUE,
                marketing_club_id UUID REFERENCES marketing_clubs(id) ON DELETE CASCADE,
                note TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_marketing_utm_alias_club "
            "ON marketing_utm_aliases(marketing_club_id)"))
        # Speeds the visit→club resolution (per-page_view utm_code lookups).
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_marketing_clubs_utm_code "
            "ON marketing_clubs(utm_code)"))
        # Visit→club resolution also probes organisations by slug (the path-slug
        # branch); the only lookup key on that path that wasn't indexed (migration 121).
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_organisations_slug ON organisations(slug)"))
        # Twenty CRM integration: membership ledger mapping a BetterCricket entity
        # (club / person / association) to its Twenty record id. A row exists only
        # for the targeted subset exported to Twenty, so it doubles as "what's in
        # the CRM" and makes upserts idempotent (content_hash skips no-op updates).
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS twenty_links (
                entity_type TEXT NOT NULL,
                bc_id TEXT NOT NULL,
                twenty_id TEXT NOT NULL,
                content_hash TEXT,
                last_synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (entity_type, bc_id)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_twenty_links_twenty ON twenty_links(twenty_id)"))
        # Upload Historical Scorecard (migration 091): a manual game built from a
        # photographed card carries the opposition club's Grassroots org GUID and the
        # full both-team scorecard the AI extracted (renders the opposition half of
        # the match view). Defensive idempotent adds so the API boots even if alembic
        # lags.
        await conn.execute(text(
            "ALTER TABLE manual_games ADD COLUMN IF NOT EXISTS opp_org_id TEXT"
        ))
        await conn.execute(text(
            "ALTER TABLE manual_games ADD COLUMN IF NOT EXISTS extracted_payload JSONB"
        ))
        # Manual partnerships + fall of wickets (migration 092): a photographed card
        # carries its fall-of-wickets table (STAND = partnership runs), so manual games
        # get their own per-wicket tables (FK'd to manual_games) and v_effective union
        # views, mirroring migration 038. Defensive idempotent creates so the API boots
        # even if alembic lags.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS manual_fall_of_wickets (
                id SERIAL PRIMARY KEY,
                manual_game_id UUID NOT NULL REFERENCES manual_games(id) ON DELETE CASCADE,
                innings_number INTEGER NOT NULL,
                wicket_number INTEGER NOT NULL,
                score_at_fall INTEGER,
                overs_at_fall NUMERIC(5,1),
                player_id UUID REFERENCES players(id) ON DELETE SET NULL,
                batter_name TEXT
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_manual_fow_game ON manual_fall_of_wickets(manual_game_id)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS manual_partnerships (
                id SERIAL PRIMARY KEY,
                manual_game_id UUID NOT NULL REFERENCES manual_games(id) ON DELETE CASCADE,
                innings_number INTEGER NOT NULL,
                wicket_number INTEGER NOT NULL,
                batter1_id UUID REFERENCES players(id) ON DELETE SET NULL,
                batter2_id UUID REFERENCES players(id) ON DELETE SET NULL,
                runs INTEGER DEFAULT 0,
                balls INTEGER,
                batter1_runs INTEGER,
                batter2_runs INTEGER,
                is_club_innings BOOLEAN
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_manual_partnerships_game ON manual_partnerships(manual_game_id)"
        ))
        await conn.execute(text("""
            CREATE OR REPLACE VIEW v_effective_fall_of_wickets AS
            SELECT id, game_id, innings_number, wicket_number,
                   score_at_fall, overs_at_fall, player_id, batter_name,
                   'api'::text AS source
            FROM fall_of_wickets
            UNION ALL
            SELECT id, manual_game_id AS game_id, innings_number, wicket_number,
                   score_at_fall, overs_at_fall, player_id, batter_name,
                   'manual'::text AS source
            FROM manual_fall_of_wickets
        """))
        # v_effective_partnerships is (re)created further down (migration 147's
        # mirror), which now also carries batter1_name/batter2_name — this
        # earlier, narrower CREATE OR REPLACE VIEW used to be a harmless re-
        # assertion of the same 12-column shape, but once migration 147 grows
        # the live view to 14 columns, running this one again on every startup
        # tries to shrink it back down, and Postgres rejects that outright
        # ("cannot drop columns from view") — the exact incident this comment
        # replaces. Removed rather than kept in sync: the later block already
        # is the complete, current definition, so having two never earns its
        # keep.
        # Manual bowler wickets (migration 093): per-dismissal bowler/fielder credit for
        # an uploaded card, mirrored into a v_effective union view like the others.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS manual_bowler_wickets (
                id SERIAL PRIMARY KEY,
                manual_game_id UUID NOT NULL REFERENCES manual_games(id) ON DELETE CASCADE,
                innings_number INTEGER NOT NULL,
                bowler_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
                fielder_id UUID REFERENCES players(id) ON DELETE SET NULL,
                batter_name TEXT,
                batter_position INTEGER,
                batter_runs INTEGER,
                batter_balls INTEGER,
                dismissal_type TEXT NOT NULL,
                caught_behind BOOLEAN
            )
        """))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_manual_bw_game ON manual_bowler_wickets(manual_game_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_manual_bw_bowler ON manual_bowler_wickets(bowler_id)"))
        await conn.execute(text("""
            CREATE OR REPLACE VIEW v_effective_bowler_wickets AS
            SELECT id, game_id, innings_number, bowler_id, fielder_id, batter_name,
                   batter_position, batter_runs, batter_balls, dismissal_type, caught_behind,
                   'api'::text AS source
            FROM bowler_wickets
            UNION ALL
            SELECT id, manual_game_id AS game_id, innings_number, bowler_id, fielder_id, batter_name,
                   batter_position, batter_runs, batter_balls, dismissal_type, caught_behind,
                   'manual'::text AS source
            FROM manual_bowler_wickets
        """))
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
            # First-party visitor id captured on the Contact form so an enquiry
            # links precisely to the browsing journey behind it (Usage page).
            "visitor_id",
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
        # Lead-tracking columns. `visitor_id` is a first-party random UUID the
        # SPA keeps in localStorage — a stable visitor identity that survives an
        # IP change, so returning visitors group correctly (the IP hash alone
        # can't). The utm_* / click_id columns carry first-touch acquisition
        # (how the visitor first arrived: a Facebook share = fbclid, a club
        # outreach link = a utm_code), and `traffic_source` is the bucketed
        # source derived from them at insert time. `landing_path` is the first
        # page they entered on. Page-view rows only; API rows leave them NULL.
        for _col, _type in (
            ("visitor_id", "UUID"),
            ("utm_source", "TEXT"),
            ("utm_medium", "TEXT"),
            ("utm_campaign", "TEXT"),
            ("utm_content", "TEXT"),
            # utm_id carries a BetterCricket outreach email's per-club code (the
            # marketing_clubs.utm_code), so an anonymous visit from that email's
            # link can be tied back to the club for behavioural segments
            # ("visited the pricing page").
            ("utm_id", "TEXT"),
            ("click_id", "TEXT"),
            ("traffic_source", "TEXT"),
            ("landing_path", "TEXT"),
        ):
            await conn.execute(text(
                f"ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS {_col} {_type}"
            ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_usage_events_visitor_created "
            "ON usage_events(visitor_id, created_at DESC) WHERE visitor_id IS NOT NULL"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_usage_events_utm_id "
            "ON usage_events(utm_id) WHERE utm_id IS NOT NULL"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_usage_events_source "
            "ON usage_events(traffic_source) WHERE traffic_source IS NOT NULL"
        ))
        # Migration 133: index the org_id branch of twenty_sync._engagement's
        # usage_events scan (a customer/trial club's authenticated in-app
        # activity) — previously unindexed.
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_usage_events_org_created "
            "ON usage_events(org_id, created_at DESC) WHERE org_id IS NOT NULL"
        ))
        # Login attempts — append-only audit of every sign-in attempt (success
        # or failure), so we can see which username/email is being tried, from
        # where, and whether it succeeded. IP is stored as a truncated SHA-256
        # prefix (never raw); the password is never stored. Mirrors migration 124.
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
            "ON login_attempts(created_at DESC)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_login_attempts_username_created "
            "ON login_attempts(username, created_at DESC)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_login_attempts_ip_created "
            "ON login_attempts(ip_hash, created_at DESC) WHERE ip_hash IS NOT NULL"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_login_attempts_failures "
            "ON login_attempts(created_at DESC) WHERE success = false"
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
        # Achievement imports are grouped into a batch so they can be undone as a
        # unit (mirrors the BetterImport stats importer).
        await conn.execute(text(
            "ALTER TABLE player_achievements ADD COLUMN IF NOT EXISTS import_batch_id UUID"
        ))
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
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_achievements_import_batch "
            "ON player_achievements(import_batch_id)"
        ))
        # Performance indexes on the per-game tables' join columns (migration
        # 103). Postgres doesn't index foreign keys automatically, so the records
        # board scanned the whole partnerships table four times per request.
        # Additive only — they change no results, just the planner's options.
        # Idempotent so they boot the API even if alembic lags.
        for _ix_name, _ix_table, _ix_col in (
            ("ix_partnerships_game", "partnerships", "game_id"),
            ("ix_partnerships_batter1", "partnerships", "batter1_id"),
            ("ix_partnerships_batter2", "partnerships", "batter2_id"),
            ("ix_batting_innings_player", "batting_innings", "player_id"),
            ("ix_batting_innings_game", "batting_innings", "game_id"),
            ("ix_bowling_spells_player", "bowling_spells", "player_id"),
            ("ix_bowling_spells_game", "bowling_spells", "game_id"),
            ("ix_fielding_stats_player", "fielding_stats", "player_id"),
            ("ix_fielding_stats_game", "fielding_stats", "game_id"),
            ("ix_games_grade", "games", "grade_id"),
        ):
            await conn.execute(text(
                f"CREATE INDEX IF NOT EXISTS {_ix_name} ON {_ix_table} ({_ix_col})"
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
        # Configurable From local-part (migration 128), decoupled from the slug.
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS comms_from_local TEXT"
        ))
        # BetterComms sending tiers (migration 125): per-club sandbox→production
        # send tier + optional daily-cap override, the tier-increase request
        # queue, and the generic club→BetterCricket request telemetry (feeds a
        # Twenty CRM task). Every club starts in 'sandbox' and EARNS production by
        # request + super-admin approval — so there is deliberately NO boot-time
        # promotion here (an earlier version blanket-set every club to production
        # on each boot, which is why every club showed 'production'; migration 129
        # resets them and this mirror no longer re-applies it).
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
            "comms_tier TEXT NOT NULL DEFAULT 'sandbox'"
        ))
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS comms_sandbox_cap INTEGER"
        ))
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS comms_production_cap INTEGER"
        ))
        # Per-club monthly send ceiling (migration 129); NULL = global default.
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS comms_monthly_cap INTEGER"
        ))
        # SES per-club tenants (migration 126) — isolate each club's sending
        # reputation to its own Amazon SES tenant.
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS ses_tenant_name TEXT"
        ))
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS ses_tenant_id TEXT"
        ))
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS ses_tenant_provisioned_at TIMESTAMPTZ"
        ))
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
            "ses_tenant_paused BOOLEAN NOT NULL DEFAULT false"
        ))
        # (No boot-time tier promotion — see the note above. A club is sandbox
        # until a super admin approves production; migration 129 did the reset.)
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS comms_limit_requests (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                current_tier TEXT,
                requested_tier TEXT NOT NULL DEFAULT 'production',
                requested_cap INTEGER,
                reason TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                requested_by UUID REFERENCES users(id) ON DELETE SET NULL,
                requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                decided_by UUID REFERENCES users(id) ON DELETE SET NULL,
                decided_at TIMESTAMPTZ,
                decision_note TEXT
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_comms_limit_requests_org "
            "ON comms_limit_requests(organisation_id)"
        ))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_comms_limit_request_open "
            "ON comms_limit_requests(organisation_id) WHERE status = 'pending'"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS club_request_events (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                request_type TEXT NOT NULL,
                summary TEXT,
                detail JSONB,
                source TEXT NOT NULL DEFAULT 'app',
                requested_by UUID REFERENCES users(id) ON DELETE SET NULL,
                ref_table TEXT,
                ref_id UUID,
                twenty_task_id TEXT,
                twenty_task_status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_club_request_events_org "
            "ON club_request_events(organisation_id, created_at DESC)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_club_request_events_type "
            "ON club_request_events(request_type, created_at DESC)"
        ))
        # BetterComms marketing-outreach designation (migration 108): which org
        # runs BetterCricket's own Clubs Directory campaigns. A super admin flags
        # it from the UI (no env/redeploy); the marketing_outreach_org_slug
        # setting stays a fallback. Partial unique index ⇒ at most one flagged.
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
            "is_marketing_outreach BOOLEAN NOT NULL DEFAULT false"
        ))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_org_marketing_outreach "
            "ON organisations (is_marketing_outreach) WHERE is_marketing_outreach"
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
        # Campaign name + description (migration 132).
        await conn.execute(text("ALTER TABLE comms_campaigns ADD COLUMN IF NOT EXISTS name TEXT"))
        await conn.execute(text("ALTER TABLE comms_campaigns ADD COLUMN IF NOT EXISTS description TEXT"))
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
        # BetterComms Phase 1 (migration 110) — global suppression + email events
        # + per-person prefs. email_suppressions is the ONE global, address-level
        # table (a hard bounce / complaint is a fact about the mailbox, not a
        # club); email_events is the append-only SES audit. Defensive idempotent
        # creates so the API boots even if alembic lags. See
        # docs/bettercomms-architecture.md.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS email_suppressions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                email TEXT NOT NULL,
                reason TEXT NOT NULL,
                source TEXT,
                detail TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_email_suppressions_email UNIQUE (email)
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS email_events (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID REFERENCES organisations(id) ON DELETE SET NULL,
                campaign_id UUID REFERENCES comms_campaigns(id) ON DELETE SET NULL,
                recipient_id UUID REFERENCES comms_recipients(id) ON DELETE SET NULL,
                contact_id UUID REFERENCES comms_contacts(id) ON DELETE SET NULL,
                email TEXT,
                event_type TEXT NOT NULL,
                event_subtype TEXT,
                reason TEXT,
                ses_message_id TEXT,
                payload JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_email_event_dedupe UNIQUE (ses_message_id, event_type, email)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_email_events_org ON email_events(organisation_id)"))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_email_events_campaign ON email_events(campaign_id)"))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_email_events_email ON email_events(lower(email))"))
        await conn.execute(text(
            "ALTER TABLE comms_contacts ADD COLUMN IF NOT EXISTS complained BOOLEAN NOT NULL DEFAULT FALSE"))
        await conn.execute(text(
            "ALTER TABLE comms_contacts ADD COLUMN IF NOT EXISTS complained_at TIMESTAMPTZ"))
        await conn.execute(text(
            "ALTER TABLE comms_contacts ADD COLUMN IF NOT EXISTS preferences JSONB NOT NULL DEFAULT '{}'"))
        # Migration 115: per-contact merge-variable overrides.
        await conn.execute(text(
            "ALTER TABLE comms_contacts ADD COLUMN IF NOT EXISTS merge_vars JSONB NOT NULL DEFAULT '{}'"))
        # BetterComms Phase 2 (migration 111) — saved dynamic segments. A segment
        # is a saved query (rules in JSONB) evaluated at send time against the
        # club's contacts + current-season stats. Defensive idempotent create.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS comms_segments (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                definition JSONB NOT NULL DEFAULT '{}',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_comms_segment_org_name UNIQUE (organisation_id, name)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_comms_segments_org ON comms_segments(organisation_id)"))
        # BetterComms Phase 2 (migration 112) — saved static lists (curated sets of
        # contacts), the counterpart to dynamic segments. Defensive idempotent creates.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS comms_lists (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_comms_list_org_name UNIQUE (organisation_id, name)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_comms_lists_org ON comms_lists(organisation_id)"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS comms_list_members (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                list_id UUID NOT NULL REFERENCES comms_lists(id) ON DELETE CASCADE,
                contact_id UUID NOT NULL REFERENCES comms_contacts(id) ON DELETE CASCADE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_comms_list_member UNIQUE (list_id, contact_id)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_comms_list_members_list ON comms_list_members(list_id)"))
        # BetterComms Phase 3 (migration 113) — email templates + per-campaign UTM.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS comms_templates (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                html TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_comms_template_org_name UNIQUE (organisation_id, name)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_comms_templates_org ON comms_templates(organisation_id)"))
        await conn.execute(text(
            "ALTER TABLE comms_campaigns ADD COLUMN IF NOT EXISTS utm JSONB NOT NULL DEFAULT '{}'"))
        await conn.execute(text(
            "ALTER TABLE comms_campaigns ADD COLUMN IF NOT EXISTS template_id UUID "
            "REFERENCES comms_templates(id) ON DELETE SET NULL"))
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
        # BetterMerch category tree (migration 086).
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS merch_categories (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                parent_id UUID REFERENCES merch_categories(id) ON DELETE CASCADE,
                top_category TEXT NOT NULL,
                name TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_merch_categories_org ON merch_categories(organisation_id, top_category, parent_id)"
        ))
        await conn.execute(text(
            "ALTER TABLE merch_products ADD COLUMN IF NOT EXISTS category_id UUID REFERENCES merch_categories(id) ON DELETE SET NULL"
        ))
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
        # BetterFees ← Square sale import (migration 149) — reuses the club's
        # existing merch_square_connections row, no new OAuth flow.
        await conn.execute(text("ALTER TABLE merch_square_connections ADD COLUMN IF NOT EXISTS sync_fees BOOLEAN NOT NULL DEFAULT false"))
        await conn.execute(text("ALTER TABLE merch_square_connections ADD COLUMN IF NOT EXISTS fee_item_keywords TEXT"))
        await conn.execute(text("ALTER TABLE merch_square_connections ADD COLUMN IF NOT EXISTS fees_last_sync_at TIMESTAMPTZ"))
        await conn.execute(text("ALTER TABLE merch_square_connections ADD COLUMN IF NOT EXISTS fees_last_sync_status TEXT"))
        await conn.execute(text("ALTER TABLE merch_square_connections ADD COLUMN IF NOT EXISTS fees_last_sync_error TEXT"))
        await conn.execute(text("ALTER TABLE fee_payments ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'manual'"))
        await conn.execute(text("ALTER TABLE fee_payments ADD COLUMN IF NOT EXISTS external_ref TEXT"))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_fee_payment_external_ref "
            "ON fee_payments(organisation_id, external_ref) WHERE external_ref IS NOT NULL"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fee_square_import_log (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                external_ref TEXT NOT NULL,
                status TEXT NOT NULL,
                fee_payment_id UUID REFERENCES fee_payments(id) ON DELETE SET NULL,
                item_name TEXT,
                note TEXT,
                amount NUMERIC(10, 2),
                occurred_at DATE,
                created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_fee_square_import_log_ref UNIQUE (organisation_id, external_ref)
            )
        """))
        # BetterFees ← Xero bank transaction import (migration 150) — a
        # dedicated per-club Xero OAuth connection (unlike Square, nothing else
        # uses it), plus its own resolved-events log mirroring the Square one.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fee_xero_connections (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                tenant_id TEXT,
                tenant_name TEXT,
                access_token TEXT,
                refresh_token TEXT,
                token_expires_at TIMESTAMPTZ,
                scopes TEXT,
                bank_account_id TEXT,
                bank_account_name TEXT,
                sync_enabled BOOLEAN NOT NULL DEFAULT false,
                last_sync_at TIMESTAMPTZ,
                last_sync_status TEXT,
                last_sync_error TEXT,
                connected_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                connected_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_fee_xero_org UNIQUE (organisation_id)
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fee_xero_import_log (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                external_ref TEXT NOT NULL,
                status TEXT NOT NULL,
                fee_payment_id UUID REFERENCES fee_payments(id) ON DELETE SET NULL,
                description TEXT,
                amount NUMERIC(10, 2),
                occurred_at DATE,
                created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_fee_xero_import_log_ref UNIQUE (organisation_id, external_ref)
            )
        """))
        # BetterFantasyCricket — internal club fantasy league (migration 087).
        # Defensive idempotent creates so the API boots even if the numbered
        # migration hasn't run yet (mirrors the BetterMerch / BetterComms blocks).
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS fantasy_link_token TEXT"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fantasy_seasons (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                season_year INTEGER NOT NULL,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'setup',
                included_grade_ids JSONB,
                scoring JSONB NOT NULL DEFAULT '{}',
                rules JSONB NOT NULL DEFAULT '{}',
                registration_open BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_fantasy_season_org_year UNIQUE (organisation_id, season_year)
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fantasy_managers (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                display_name TEXT NOT NULL,
                email TEXT,
                credential_hash TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_seen_at TIMESTAMPTZ
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_fantasy_managers_org ON fantasy_managers(organisation_id)"
        ))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_fantasy_manager_org_email "
            "ON fantasy_managers(organisation_id, email) WHERE email IS NOT NULL"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fantasy_leagues (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                fantasy_season_id UUID NOT NULL REFERENCES fantasy_seasons(id) ON DELETE CASCADE,
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                kind TEXT NOT NULL DEFAULT 'global_salary_cap',
                name TEXT NOT NULL,
                join_code TEXT,
                draft_type TEXT,
                scoring_type TEXT,
                settings JSONB NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'open',
                created_by_manager_id UUID REFERENCES fantasy_managers(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_fantasy_leagues_season ON fantasy_leagues(fantasy_season_id, kind)"
        ))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_fantasy_league_join_code "
            "ON fantasy_leagues(fantasy_season_id, join_code) WHERE join_code IS NOT NULL"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fantasy_squads (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                fantasy_season_id UUID NOT NULL REFERENCES fantasy_seasons(id) ON DELETE CASCADE,
                league_id UUID NOT NULL REFERENCES fantasy_leagues(id) ON DELETE CASCADE,
                manager_id UUID NOT NULL REFERENCES fantasy_managers(id) ON DELETE CASCADE,
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                team_name TEXT NOT NULL,
                budget_remaining NUMERIC(8,1),
                free_transfers INTEGER NOT NULL DEFAULT 1,
                chips_used JSONB NOT NULL DEFAULT '{}',
                total_points NUMERIC(8,2) NOT NULL DEFAULT 0,
                joined_round INTEGER,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_fantasy_squad_league_manager UNIQUE (league_id, manager_id)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_fantasy_squads_season ON fantasy_squads(fantasy_season_id)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fantasy_squad_players (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                squad_id UUID NOT NULL REFERENCES fantasy_squads(id) ON DELETE CASCADE,
                player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
                role TEXT NOT NULL DEFAULT 'batter',
                is_captain BOOLEAN NOT NULL DEFAULT false,
                is_vice_captain BOOLEAN NOT NULL DEFAULT false,
                purchase_price NUMERIC(8,1),
                added_round INTEGER,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_fantasy_squad_player UNIQUE (squad_id, player_id)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_fantasy_squad_players_squad ON fantasy_squad_players(squad_id)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fantasy_league_members (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                league_id UUID NOT NULL REFERENCES fantasy_leagues(id) ON DELETE CASCADE,
                manager_id UUID NOT NULL REFERENCES fantasy_managers(id) ON DELETE CASCADE,
                squad_id UUID REFERENCES fantasy_squads(id) ON DELETE SET NULL,
                joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_fantasy_league_member UNIQUE (league_id, manager_id)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_fantasy_league_members_league ON fantasy_league_members(league_id)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fantasy_pool_players (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                fantasy_season_id UUID NOT NULL REFERENCES fantasy_seasons(id) ON DELETE CASCADE,
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
                role TEXT NOT NULL DEFAULT 'batter',
                role_source TEXT NOT NULL DEFAULT 'auto',
                base_price NUMERIC(8,1) NOT NULL DEFAULT 0,
                current_price NUMERIC(8,1) NOT NULL DEFAULT 0,
                total_points NUMERIC(8,2) NOT NULL DEFAULT 0,
                last_round_points NUMERIC(8,2) NOT NULL DEFAULT 0,
                owned_count INTEGER NOT NULL DEFAULT 0,
                price_change NUMERIC(6,1) NOT NULL DEFAULT 0,
                is_available BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_fantasy_pool_player UNIQUE (fantasy_season_id, player_id)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_fantasy_pool_players_season ON fantasy_pool_players(fantasy_season_id)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fantasy_rounds (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                fantasy_season_id UUID NOT NULL REFERENCES fantasy_seasons(id) ON DELETE CASCADE,
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                round_number INTEGER NOT NULL,
                name TEXT,
                lock_at TIMESTAMPTZ,
                start_date DATE,
                end_date DATE,
                status TEXT NOT NULL DEFAULT 'upcoming',
                scored_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_fantasy_round_number UNIQUE (fantasy_season_id, round_number)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_fantasy_rounds_season ON fantasy_rounds(fantasy_season_id, round_number)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fantasy_player_round_scores (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                fantasy_season_id UUID NOT NULL REFERENCES fantasy_seasons(id) ON DELETE CASCADE,
                round_id UUID NOT NULL REFERENCES fantasy_rounds(id) ON DELETE CASCADE,
                player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
                base_points NUMERIC(8,2) NOT NULL DEFAULT 0,
                total_points NUMERIC(8,2) NOT NULL DEFAULT 0,
                breakdown JSONB NOT NULL DEFAULT '{}',
                games_counted INTEGER NOT NULL DEFAULT 0,
                computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_fantasy_player_round_score UNIQUE (round_id, player_id)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_fantasy_player_round_scores_round "
            "ON fantasy_player_round_scores(fantasy_season_id, round_id)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fantasy_squad_round_scores (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                squad_id UUID NOT NULL REFERENCES fantasy_squads(id) ON DELETE CASCADE,
                round_id UUID NOT NULL REFERENCES fantasy_rounds(id) ON DELETE CASCADE,
                points NUMERIC(8,2) NOT NULL DEFAULT 0,
                raw_points NUMERIC(8,2) NOT NULL DEFAULT 0,
                transfer_hit INTEGER NOT NULL DEFAULT 0,
                transfers_made INTEGER NOT NULL DEFAULT 0,
                chip_used TEXT,
                captain_player_id UUID REFERENCES players(id) ON DELETE SET NULL,
                vice_captain_player_id UUID REFERENCES players(id) ON DELETE SET NULL,
                dropped_player_id UUID REFERENCES players(id) ON DELETE SET NULL,
                lineup JSONB NOT NULL DEFAULT '[]',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_fantasy_squad_round_score UNIQUE (squad_id, round_id)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_fantasy_squad_round_scores_round ON fantasy_squad_round_scores(round_id)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fantasy_transactions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                squad_id UUID NOT NULL REFERENCES fantasy_squads(id) ON DELETE CASCADE,
                league_id UUID REFERENCES fantasy_leagues(id) ON DELETE CASCADE,
                round_id UUID REFERENCES fantasy_rounds(id) ON DELETE SET NULL,
                type TEXT NOT NULL,
                player_id UUID REFERENCES players(id) ON DELETE SET NULL,
                counterparty_squad_id UUID REFERENCES fantasy_squads(id) ON DELETE SET NULL,
                price NUMERIC(8,1),
                detail JSONB NOT NULL DEFAULT '{}',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_fantasy_transactions_squad ON fantasy_transactions(squad_id, created_at)"
        ))
        # BetterFantasyCricket — draft mode (migration 088). Defensive idempotent
        # creates so the API boots even if the numbered migration hasn't run yet.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fantasy_drafts (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                league_id UUID NOT NULL REFERENCES fantasy_leagues(id) ON DELETE CASCADE,
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                type TEXT NOT NULL DEFAULT 'snake',
                status TEXT NOT NULL DEFAULT 'scheduled',
                pick_seconds INTEGER NOT NULL DEFAULT 14400,
                current_pick INTEGER NOT NULL DEFAULT 0,
                draft_order JSONB NOT NULL DEFAULT '[]',
                rounds INTEGER NOT NULL DEFAULT 12,
                started_at TIMESTAMPTZ,
                nomination_index INTEGER NOT NULL DEFAULT 0,
                lot_player_id UUID REFERENCES players(id) ON DELETE SET NULL,
                lot_high_bid NUMERIC(8,1),
                lot_high_bidder_id UUID REFERENCES fantasy_managers(id) ON DELETE SET NULL,
                lot_nominator_id UUID REFERENCES fantasy_managers(id) ON DELETE SET NULL,
                lot_deadline TIMESTAMPTZ,
                lot_auto BOOLEAN NOT NULL DEFAULT false,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_fantasy_draft_league UNIQUE (league_id)
            )
        """))
        # Auction-mode columns (migration 089) for a fantasy_drafts table that
        # pre-dates them — additive, so snake drafts are untouched.
        await conn.execute(text("""
            ALTER TABLE fantasy_drafts
                ADD COLUMN IF NOT EXISTS nomination_index INTEGER NOT NULL DEFAULT 0,
                ADD COLUMN IF NOT EXISTS lot_player_id UUID REFERENCES players(id) ON DELETE SET NULL,
                ADD COLUMN IF NOT EXISTS lot_high_bid NUMERIC(8,1),
                ADD COLUMN IF NOT EXISTS lot_high_bidder_id UUID REFERENCES fantasy_managers(id) ON DELETE SET NULL,
                ADD COLUMN IF NOT EXISTS lot_nominator_id UUID REFERENCES fantasy_managers(id) ON DELETE SET NULL,
                ADD COLUMN IF NOT EXISTS lot_deadline TIMESTAMPTZ,
                ADD COLUMN IF NOT EXISTS lot_auto BOOLEAN NOT NULL DEFAULT false
        """))
        await conn.execute(text(
            "ALTER TABLE fantasy_drafts ADD COLUMN IF NOT EXISTS lot_max_bids JSONB NOT NULL DEFAULT '{}'"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fantasy_draft_picks (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                draft_id UUID NOT NULL REFERENCES fantasy_drafts(id) ON DELETE CASCADE,
                pick_index INTEGER NOT NULL,
                round_no INTEGER NOT NULL,
                manager_id UUID NOT NULL REFERENCES fantasy_managers(id) ON DELETE CASCADE,
                player_id UUID REFERENCES players(id) ON DELETE SET NULL,
                deadline TIMESTAMPTZ,
                picked_at TIMESTAMPTZ,
                auto_picked BOOLEAN NOT NULL DEFAULT false,
                bid_amount NUMERIC(8,1),
                CONSTRAINT uq_fantasy_draft_pick UNIQUE (draft_id, pick_index)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_fantasy_draft_picks_draft ON fantasy_draft_picks(draft_id, pick_index)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fantasy_draft_wishlists (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                draft_id UUID NOT NULL REFERENCES fantasy_drafts(id) ON DELETE CASCADE,
                manager_id UUID NOT NULL REFERENCES fantasy_managers(id) ON DELETE CASCADE,
                player_ids JSONB NOT NULL DEFAULT '[]',
                CONSTRAINT uq_fantasy_draft_wishlist UNIQUE (draft_id, manager_id)
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fantasy_waiver_claims (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                league_id UUID NOT NULL REFERENCES fantasy_leagues(id) ON DELETE CASCADE,
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                manager_id UUID NOT NULL REFERENCES fantasy_managers(id) ON DELETE CASCADE,
                add_player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
                drop_player_id UUID REFERENCES players(id) ON DELETE SET NULL,
                priority INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                processed_at TIMESTAMPTZ
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_fantasy_waiver_claims_league ON fantasy_waiver_claims(league_id, status)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fantasy_trades (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                league_id UUID NOT NULL REFERENCES fantasy_leagues(id) ON DELETE CASCADE,
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                proposer_squad_id UUID NOT NULL REFERENCES fantasy_squads(id) ON DELETE CASCADE,
                receiver_squad_id UUID NOT NULL REFERENCES fantasy_squads(id) ON DELETE CASCADE,
                offer JSONB NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'proposed',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                resolved_at TIMESTAMPTZ
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_fantasy_trades_league ON fantasy_trades(league_id, status)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fantasy_h2h_fixtures (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                league_id UUID NOT NULL REFERENCES fantasy_leagues(id) ON DELETE CASCADE,
                round_id UUID REFERENCES fantasy_rounds(id) ON DELETE SET NULL,
                round_no INTEGER NOT NULL,
                home_squad_id UUID NOT NULL REFERENCES fantasy_squads(id) ON DELETE CASCADE,
                away_squad_id UUID REFERENCES fantasy_squads(id) ON DELETE SET NULL,
                home_points NUMERIC(8,2),
                away_points NUMERIC(8,2),
                result TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_fantasy_h2h_fixtures_league ON fantasy_h2h_fixtures(league_id, round_no)"
        ))
        # Per-module subscriptions + Club General Settings + primary admin
        # (migration 118) — defensive idempotent mirror so the API boots even if
        # alembic lags. Backfill matches the migration: one row per held module
        # inheriting the club's current org-wide status + renewal.
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS general_settings JSONB NOT NULL DEFAULT '{}'"
        ))
        await conn.execute(text(
            "ALTER TABLE club_memberships ADD COLUMN IF NOT EXISTS is_primary_admin BOOLEAN NOT NULL DEFAULT false"
        ))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_membership_primary "
            "ON club_memberships(club_id) WHERE is_primary_admin"
        ))
        await conn.execute(text("""
            UPDATE club_memberships m
            SET is_primary_admin = true
            FROM (
                SELECT DISTINCT ON (club_id) id
                FROM club_memberships
                WHERE role = 'club_admin'
                ORDER BY club_id, created_at ASC, id ASC
            ) first
            WHERE m.id = first.id
              AND NOT EXISTS (
                SELECT 1 FROM club_memberships x
                WHERE x.club_id = m.club_id AND x.is_primary_admin
              )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS org_module_subscriptions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                module_key TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                trial_started_at TIMESTAMPTZ,
                trial_ends_at TIMESTAMPTZ,
                renewal_date DATE,
                started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_org_module UNIQUE (organisation_id, module_key)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_org_module_subscriptions_org "
            "ON org_module_subscriptions(organisation_id)"
        ))
        await conn.execute(text("""
            INSERT INTO org_module_subscriptions
                (organisation_id, module_key, status, renewal_date, started_at, created_at, updated_at)
            SELECT
                o.id,
                m.module_key,
                CASE WHEN o.subscription_status IN ('active','trial','past_due')
                     THEN o.subscription_status ELSE 'active' END,
                o.renewal_date,
                NOW(), NOW(), NOW()
            FROM organisations o
            CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(o.module_overrides, '[]'::jsonb)) AS m(module_key)
            WHERE m.module_key IN ('select','socials','fees','iq','comms','merch','fantasy')
            ON CONFLICT (organisation_id, module_key) DO NOTHING
        """))
        # Module action requests — the super-admin trial/subscription queue
        # (migration 119). Defensive idempotent mirror.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS module_action_requests (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                module_key TEXT NOT NULL,
                kind TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'outstanding',
                source TEXT NOT NULL DEFAULT 'app',
                note TEXT,
                requested_by UUID REFERENCES users(id) ON DELETE SET NULL,
                requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                completed_by UUID REFERENCES users(id) ON DELETE SET NULL,
                completed_at TIMESTAMPTZ,
                result_subscription_id UUID REFERENCES org_module_subscriptions(id) ON DELETE SET NULL,
                external_ref TEXT
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_module_action_requests_status "
            "ON module_action_requests(status, requested_at DESC)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_module_action_requests_org "
            "ON module_action_requests(organisation_id)"
        ))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_module_action_external_ref "
            "ON module_action_requests(external_ref) WHERE external_ref IS NOT NULL"
        ))
        # Platform settings — global super-admin General Settings (migration 120).
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS platform_settings (
                id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
                settings JSONB NOT NULL DEFAULT '{}',
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "INSERT INTO platform_settings (id, settings) VALUES (1, '{\"default_trial_days\": 14}') "
            "ON CONFLICT (id) DO NOTHING"
        ))
        # BetterStats (Core) as a managed module — backfill an active core subscription
        # per club (migration 122). Inherits the club's org-wide status/renewal;
        # paused/cancelled clubs get an active core row (the master switch gates those).
        await conn.execute(text("""
            INSERT INTO org_module_subscriptions
                (organisation_id, module_key, status, renewal_date, started_at, created_at, updated_at)
            SELECT
                o.id, 'core',
                CASE WHEN o.subscription_status IN ('active','trial','past_due')
                     THEN o.subscription_status ELSE 'active' END,
                o.renewal_date, NOW(), NOW(), NOW()
            FROM organisations o
            ON CONFLICT (organisation_id, module_key) DO NOTHING
        """))
        # Meta Ads dashboard (migration 125): daily campaign/ad snapshots for the
        # super-admin HQ page. Defensive idempotent create so the API boots even
        # if alembic 125 hasn't run yet.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS meta_ad_snapshots (
                id BIGSERIAL PRIMARY KEY,
                snapshot_date DATE NOT NULL,
                level TEXT NOT NULL,
                ad_id TEXT,
                ad_name TEXT,
                spend NUMERIC NOT NULL DEFAULT 0,
                impressions NUMERIC NOT NULL DEFAULT 0,
                link_clicks NUMERIC NOT NULL DEFAULT 0,
                link_ctr NUMERIC NOT NULL DEFAULT 0,
                landing_page_views NUMERIC NOT NULL DEFAULT 0,
                cost_per_lpv NUMERIC,
                leads NUMERIC NOT NULL DEFAULT 0,
                recommendation TEXT,
                recommendation_status TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_meta_ad_snapshots_date_level_ad "
            "ON meta_ad_snapshots(snapshot_date, level, COALESCE(ad_id, ''))"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_meta_ad_snapshots_date "
            "ON meta_ad_snapshots(snapshot_date DESC)"
        ))
        # Meta Ads manual leads reconciliation (migration 130): a signed delta
        # log so a manual correction survives the next daily snapshot re-run.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS meta_lead_adjustments (
                id BIGSERIAL PRIMARY KEY,
                delta INTEGER NOT NULL,
                note TEXT,
                created_by_email TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_meta_lead_adjustments_created_at "
            "ON meta_lead_adjustments(created_at DESC)"
        ))
        # Meta Ads — scope snapshots + lead adjustments to a campaign
        # (migration 162). Neither table recorded which real Meta campaign a
        # row belonged to, so switching settings.meta_campaign_id from the
        # finished July campaign to the new self-serve one stitched the two
        # campaigns' numbers together (the 14-day trend chart had no
        # campaign filter at all, and manual lead-adjustment corrections
        # from the old campaign kept applying to the new one's total
        # forever). Backfill assumes every pre-existing row was written
        # while the July campaign was the only one that existed.
        await conn.execute(text("ALTER TABLE meta_ad_snapshots ADD COLUMN IF NOT EXISTS campaign_id TEXT"))
        await conn.execute(text(
            "UPDATE meta_ad_snapshots SET campaign_id = '120249237210710121' WHERE campaign_id IS NULL"
        ))
        await conn.execute(text("DROP INDEX IF EXISTS uq_meta_ad_snapshots_date_level_ad"))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_meta_ad_snapshots_date_level_ad_campaign "
            "ON meta_ad_snapshots(snapshot_date, level, COALESCE(ad_id, ''), COALESCE(campaign_id, ''))"
        ))
        await conn.execute(text("ALTER TABLE meta_lead_adjustments ADD COLUMN IF NOT EXISTS campaign_id TEXT"))
        await conn.execute(text(
            "UPDATE meta_lead_adjustments SET campaign_id = '120249237210710121' WHERE campaign_id IS NULL"
        ))
        # Fill-in names on partnerships/fielding + a per-club toggle to show them
        # (migration 147) — mirrors FallOfWicket.batter_name for whichever side of
        # a partnership, or which fielder, has no linkable `players` row. Defensive
        # idempotent adds so the API boots even if alembic lags.
        await conn.execute(text(
            "ALTER TABLE partnerships ADD COLUMN IF NOT EXISTS batter1_name TEXT"
        ))
        await conn.execute(text(
            "ALTER TABLE partnerships ADD COLUMN IF NOT EXISTS batter2_name TEXT"
        ))
        await conn.execute(text(
            "ALTER TABLE manual_partnerships ADD COLUMN IF NOT EXISTS batter1_name TEXT"
        ))
        await conn.execute(text(
            "ALTER TABLE manual_partnerships ADD COLUMN IF NOT EXISTS batter2_name TEXT"
        ))
        await conn.execute(text(
            "ALTER TABLE fielding_stats ADD COLUMN IF NOT EXISTS player_name TEXT"
        ))
        await conn.execute(text(
            "ALTER TABLE manual_fielding_stats ADD COLUMN IF NOT EXISTS player_name TEXT"
        ))
        await conn.execute(text(
            "ALTER TABLE fielding_stats ALTER COLUMN player_id DROP NOT NULL"
        ))
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
            "include_fill_ins_in_stats BOOLEAN NOT NULL DEFAULT true"
        ))
        await conn.execute(text(
            "ALTER TABLE players ADD COLUMN IF NOT EXISTS claim_note TEXT"
        ))
        # Stripe Checkout billing (migration 150) — see services/stripe_billing.py.
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT"
        ))
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS billing_invoices (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                stripe_invoice_id TEXT NOT NULL,
                stripe_subscription_id TEXT,
                status TEXT NOT NULL,
                amount_due INTEGER NOT NULL DEFAULT 0,
                amount_paid INTEGER NOT NULL DEFAULT 0,
                currency TEXT NOT NULL DEFAULT 'aud',
                period_start TIMESTAMPTZ,
                period_end TIMESTAMPTZ,
                hosted_invoice_url TEXT,
                invoice_pdf TEXT,
                line_items JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_billing_invoices_stripe_id UNIQUE (stripe_invoice_id)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_billing_invoices_org "
            "ON billing_invoices(organisation_id, created_at DESC)"
        ))
        # Discount breakdown + payment method on billing_invoices (migration
        # 159) — see services/stripe_billing.py::_upsert_invoice and
        # routers/billing.py::discount_report (the Super Admin rollup).
        await conn.execute(text(
            "ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS bundle_discount_cents INTEGER NOT NULL DEFAULT 0"
        ))
        await conn.execute(text("ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS coupon_code TEXT"))
        await conn.execute(text(
            "ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS coupon_discount_cents INTEGER NOT NULL DEFAULT 0"
        ))
        await conn.execute(text("ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS payment_method_type TEXT"))
        await conn.execute(text("ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS payment_method_summary TEXT"))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_billing_invoices_coupon_code ON billing_invoices(coupon_code) "
            "WHERE coupon_code IS NOT NULL"
        ))
        # Per-club override of billing_checkout_enabled (migration 151) — see
        # services/platform_settings.billing_checkout_enabled_for_org.
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS billing_checkout_override BOOLEAN"
        ))
        # Club address (migration 158) — resolved at self-serve registration
        # (routers/self_serve_trial.py, PlayHQ public directory first, the
        # Club Directory as fallback) so the Stripe Customer created at
        # checkout has a real address for automatic tax from the start. See
        # services/stripe_client.py::_ensure_customer.
        await conn.execute(text("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS address_line1 TEXT"))
        await conn.execute(text("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS suburb TEXT"))
        await conn.execute(text("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS state TEXT"))
        await conn.execute(text("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS postcode TEXT"))
        await conn.execute(text("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS country TEXT"))
        # First-touch signup attribution (migration 161) — set only by the
        # public self-serve registration (routers/public_self_serve.py) so ad
        # performance can be joined against trial usage / Twenty engagement
        # in the meta_ads ad-signups report.
        await conn.execute(text("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS signup_source TEXT"))
        await conn.execute(text("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS signup_attribution JSONB"))
        # Stripe Product id cache for add-on subscription items (migration
        # 152) — see services/stripe_client.py::_ensure_product.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS stripe_products (
                billing_key TEXT PRIMARY KEY,
                stripe_product_id TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        # Stripe Coupon id cache for the bundle discount (migration 153) —
        # see services/stripe_client.py::_ensure_bundle_coupon.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS stripe_coupons (
                discount_cents INTEGER PRIMARY KEY,
                stripe_coupon_id TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        # Pending pause/cancel signal for a running sync (migration 160) — see
        # services/sync.py's SyncControlSignal / _check_sync_control. NULL =
        # no request pending; 'pause' | 'cancel' while an operator's request
        # hasn't yet been noticed by the run's own loop checkpoint.
        await conn.execute(text("ALTER TABLE sync_runs ADD COLUMN IF NOT EXISTS control TEXT"))
        # CREATE OR REPLACE VIEW only allows appending new columns at the END
        # of the SELECT list — inserting one in the middle shifts every later
        # column's position, which Postgres treats as renaming that column
        # and rejects. batter1_name/batter2_name/player_name are appended
        # after `source`, same placement migration 075 used for
        # v_effective_batting_innings.caught_behind. (This shape shipped
        # broken once — an in-the-middle CREATE OR REPLACE VIEW crash-looped
        # the backend in production; this is the corrected version, matching
        # migration 147.)
        await conn.execute(text("""
            CREATE OR REPLACE VIEW v_effective_partnerships AS
            SELECT
                id, game_id, innings_number, wicket_number,
                batter1_id, batter2_id, runs, balls,
                batter1_runs, batter2_runs, is_club_innings,
                'api'::text AS source,
                batter1_name, batter2_name
            FROM partnerships
            UNION ALL
            SELECT
                id, manual_game_id AS game_id, innings_number, wicket_number,
                batter1_id, batter2_id, runs, balls,
                batter1_runs, batter2_runs, is_club_innings,
                'manual'::text AS source,
                batter1_name, batter2_name
            FROM manual_partnerships
        """))
        await conn.execute(text("""
            CREATE OR REPLACE VIEW v_effective_fielding_stats AS
            SELECT
                id, game_id, player_id,
                catches, catches_wk, run_outs, stumpings,
                'api'::text AS source,
                player_name
            FROM fielding_stats
            UNION ALL
            SELECT
                id, manual_game_id AS game_id, player_id,
                catches, catches_wk, run_outs, stumpings,
                'manual'::text AS source,
                player_name
            FROM manual_fielding_stats
        """))
        # Trial lifecycle notifications + onboarding nudges dedupe ledger
        # (migration 148, Phase 16). See app/services/trial_lifecycle.py.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS trial_lifecycle_nudges (
                id UUID PRIMARY KEY,
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                module_key TEXT,
                nudge_type TEXT NOT NULL,
                dedupe_key TEXT NOT NULL UNIQUE,
                sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_trial_lifecycle_nudges_org "
            "ON trial_lifecycle_nudges(organisation_id, sent_at DESC)"
        ))
        # BetterCricket-managed discount coupons (migration 156) — see
        # services/discount_coupons.py + services/stripe_client.py's coupon
        # sync helpers. Super Admin owns the whole lifecycle in BetterCricket;
        # Stripe is a pure sync target.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS discount_coupons (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                code TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                discount_type TEXT NOT NULL,
                discount_value NUMERIC NOT NULL,
                module_keys JSONB,
                redeem_window_start DATE,
                redeem_window_end DATE,
                new_signup_window_start DATE,
                new_signup_window_end DATE,
                loyalty_window_start DATE,
                loyalty_window_end DATE,
                duration_mode TEXT NOT NULL DEFAULT 'once',
                duration_renewals INTEGER,
                stackable_with_bundle BOOLEAN NOT NULL DEFAULT false,
                max_redemptions INTEGER,
                active BOOLEAN NOT NULL DEFAULT true,
                stripe_coupon_id TEXT,
                created_by UUID REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS discount_coupon_redemptions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                coupon_id UUID NOT NULL REFERENCES discount_coupons(id) ON DELETE CASCADE,
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                redeemed_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                applied_via TEXT NOT NULL,
                redeemed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                stripe_subscription_id TEXT,
                status TEXT NOT NULL DEFAULT 'active'
            )
        """))
        await conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_coupon_redemption_live_slot
            ON discount_coupon_redemptions (coupon_id, organisation_id)
            WHERE status <> 'revoked'
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_coupon_redemptions_coupon "
            "ON discount_coupon_redemptions(coupon_id, redeemed_at DESC)"
        ))
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

    # Seed every club's BetterComms library with the built-in starter templates
    # (idempotent — ON CONFLICT DO NOTHING per org+name, so this also backfills
    # any club created since the last startup with no separate creation hook).
    from app.routers.comms import seed_starter_templates
    async with engine.begin() as conn:
        seeded = await seed_starter_templates(conn)
        if seeded:
            logger.info(f"Seeded {seeded} BetterComms starter templates across clubs")

    # Warm the SES send-rate cache from platform_settings so a DB-configured rate
    # takes effect immediately on boot (not only once a super admin opens the page).
    from app.services import platform_settings as _ps
    async with AsyncSessionLocal() as _rate_session:
        await _ps.warm_send_rate_cache(_rate_session)

    # One-off repair for clubs stuck with a dangling stripe_subscription_id
    # from before cancel paths cleared it themselves (see
    # stripe_billing.sweep_dangling_stripe_subscriptions). Idempotent — a
    # no-op on every boot after the first that finds nothing left to fix.
    #
    # Fired as a background task, NOT awaited — this makes a real outbound
    # call to Stripe's API for every dangling row it finds, and an app boot
    # step must never be allowed to depend on an external network call
    # succeeding (or even responding) at all. A prior version of this awaited
    # the sweep inline, and the very first time it had a real row to act on
    # (after live Stripe checkout testing) it hung "Waiting for application
    # startup" indefinitely with no crash and no further log line — a
    # timeout on the await would have capped the damage, but still delays
    # every boot and can still eat into deploy.sh's own health-check window
    # on a merely slow Stripe response. Running in the background means boot
    # never waits on Stripe at all; the 30s internal timeout is just so a
    # stuck attempt doesn't hold a DB session open forever, and on failure
    # or timeout the repair simply retries next boot (idempotent either way).
    asyncio.create_task(_run_stripe_subscription_sweep())

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
app.include_router(billing.router)  # Account page Stripe Checkout (flag-gated — see platform_settings.billing_checkout_enabled)
app.include_router(discount_coupons.router)  # BetterCricket-managed discount coupons (migration 156)
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
app.include_router(player_import.router)  # BetterImport (profiles) — bulk player contact/profile CSV import
app.include_router(klubpro_migration.router)  # KlubPro → BetterStats migration (super-admin onboarding)
app.include_router(marketing.router)  # Marketing club directory crawl + outreach (super-admin)
app.include_router(usage.router)
app.include_router(login_attempts.router)
app.include_router(meta_ads.router)  # Meta Ads HQ dashboard (super-admin) — BetterCricket's own ad spend
app.include_router(self_serve_trial.router)  # Self-serve club trial registration (internal, flag-gated — see docs/self-serve-trial-onboarding-plan.md)
app.include_router(public_self_serve.router)  # Public self-serve trial registration (unauthenticated, same flag — the /trial ad-campaign landing page)
app.include_router(onboarding_wizard.router)  # Club onboarding wizard (flag-gated — see docs/self-serve-trial-onboarding-plan.md Phase 15)
app.include_router(wizard_analytics.router)  # Setup Wizard analytics (super-admin) — where clubs get stuck/skip
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
app.include_router(public_ses.router)                                                     # BetterComms (SES event webhook, SNS-signed)
app.include_router(public_contact.router)                                                 # Marketing Contact form (public intake)
app.include_router(public_square.router)                                                  # BetterMerch (Square OAuth callback)
app.include_router(public_xero.router)                                                    # BetterFees (Xero OAuth callback)
app.include_router(public_stripe.router)                                                  # Billing (Stripe webhook, signature-verified)
app.include_router(public_fantasy.router)                                                 # BetterFantasyCricket (public manager play)
app.include_router(pipeline_gauge.router)                                                 # Twenty CRM dashboard gauge (own HTTP Basic Auth, not require_module)
app.include_router(ladders.router)  # standings power public club pages — not gated
app.include_router(iq.router, dependencies=[Depends(require_module("iq"))])               # BetterIQ
app.include_router(fantasy.router, dependencies=[Depends(require_module("fantasy"))])      # BetterFantasyCricket

# Serve uploaded files (hero images, gallery photos)
_upload_dir = Path("/app/uploads")
_upload_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(_upload_dir)), name="uploads")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "betterstats-api"}
