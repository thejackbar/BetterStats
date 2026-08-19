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
from app.routers import auth, organisations, players, games, webhooks, leaderboard, records, admin, achievements, clubs, club_admin, statlab, yearbooks, award_definitions, images, og_preview, notifications, seo, families, manual_entries, imports, player_import, usage, fees, fixtures, teams, availability, selection, ladders, iq, public_availability, net_manager, website, comms, public_comms, public_ses, public_contact, klubpro_migration, bookmarks, merch, public_square, public_xero, fantasy, public_fantasy, marketing, login_attempts, meta_ads, pipeline_gauge, self_serve_trial, public_self_serve, onboarding_wizard, wizard_analytics, billing, public_stripe, discount_coupons, backup_admin, crm, committee, volunteers, qualifications, events, assets, \
    stripe_connect, public_stripe_connect, member_portal_admin, public_member_portal, public_merch_store, \
    club_diary, social_media, votes, public_votes, roles_activities, club_room, roster, facility_requests, directory, \
    public_club_room, sales_workspace
# BetterScout — a separate tenant type (Scout Org) with its own login,
# unrelated to the club Organisation model. Imported separately since it's a
# submodule of routers.scout, not a top-level routers module; aliased to
# avoid colliding with the `auth` (club-admin) import above.
from app.routers.scout import (
    auth as scout_auth_router,
    compare as scout_compare_router,
    discovery as scout_discovery_router,
    feed as scout_feed_router,
    milestones as scout_milestones_router,
    public_share as scout_public_share_router,
    search as scout_search_router,
    settings as scout_settings_router,
    watchlist as scout_watchlist_router,
)
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


async def _run_yearbook_stub_sweep():
    """Background counterpart for yearbook-stub generation — moved off the inline
    boot path: generate_all_stubs iterates EVERY org and season, so it grows with
    the platform and had begun to overrun deploy.sh's own health-check window,
    flagging a perfectly healthy backend as DOWN (uvicorn stuck at "Waiting for
    application startup" only because this hadn't returned yet). It's a
    non-critical convenience sweep — a missing stub is also created on demand —
    so running it just after startup instead of before uvicorn is ready is safe.
    Mirrors _run_stripe_subscription_sweep's session isolation + never-fatal
    error handling."""
    from app.models.db import async_session_maker as AsyncSessionLocal
    from app.routers.yearbooks import generate_all_stubs
    async with AsyncSessionLocal() as session:
        try:
            await generate_all_stubs(session)
        except Exception as e:
            await session.rollback()
            logger.error(f"Yearbook stub sweep failed: {e}")


async def _resume_interrupted_syncs(rows: list[dict]) -> None:
    """Restart org syncs that were cut off mid-run by the previous shutdown.

    Each row was captured (and its old run finalized as 'error') during the
    lifespan DDL phase. We start a BRAND-NEW incremental ``org_full`` run per
    org — never re-wiping. An interrupted Full Rebuild resumes as a plain
    incremental sync because its wipe phase already committed before the crash;
    sync's per-game/per-season writes are idempotent on row-existence, so a
    fresh incremental sync picks up exactly where the crash left off (the same
    reasoning as pause→continue, see sync.pause_sync_run's docstring). The
    original trigger's user is carried forward for attribution. Never raises —
    one org failing to resume must not stop the rest, and a resume failure just
    means the next weekly sync (or a manual click) catches it up anyway."""
    from app.services.sync import start_sync_run, update_sync_run
    from app.routers.organisations import _org_sync_running, _sync_safe
    from app.routers.club_admin import _background_tasks, _hard_refresh_running
    import uuid as _uuid
    for row in rows:
        org_id = row["org_id"]
        try:
            if org_id in _org_sync_running or org_id in _hard_refresh_running:
                continue
            user_id = _uuid.UUID(row["user_id"]) if row.get("user_id") else None
            new_run_id = await start_sync_run(
                _uuid.UUID(org_id), "org_full", triggered_by_user_id=user_id,
            )
            # Tag the fresh run so the Background Processes panel can show it was
            # auto-resumed rather than manually triggered.
            await update_sync_run(new_run_id, {
                "resumed_after_restart": True,
                "resumed_from_run_id": row["old_run_id"],
                "resumed_from_kind": row["kind"],
            })
            _org_sync_running.add(org_id)
            task = asyncio.create_task(_sync_safe(org_id, new_run_id, "org_full"))
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)
            logger.info(
                f"Self-heal: resumed interrupted {row['kind']} for org {org_id} "
                f"as run {new_run_id}"
            )
        except Exception:
            logger.exception(f"Self-heal: failed to resume interrupted sync for org {org_id}")


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
        # Per-account UI preferences bag (migration 204) — persists a super
        # admin's UI choices (e.g. CRM stage filter buttons) across sessions.
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS ui_preferences "
            "JSONB NOT NULL DEFAULT '{}'::jsonb"
        ))
        # Club page password protection / "Draft" mode (migration 205) — see
        # services/club_lock.py. Independent of is_active by design.
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
            "password_protected BOOLEAN NOT NULL DEFAULT false"
        ))
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
            "password_protect_reason TEXT"
        ))
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
            "access_pin_hash TEXT"
        ))
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
            "password_protected_at TIMESTAMPTZ"
        ))
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
            "password_protected_by UUID REFERENCES users(id)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS club_unpause_requests (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                email TEXT NOT NULL,
                message TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                actioned_at TIMESTAMPTZ,
                actioned_by UUID REFERENCES users(id)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_club_unpause_requests_org "
            "ON club_unpause_requests(organisation_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_club_unpause_requests_status_created "
            "ON club_unpause_requests(status, created_at DESC)"
        ))
        # Club Room Mode (migration 206) — the TV-loop slideshow. Defensive
        # idempotent creates so the API boots even if alembic hasn't run yet.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS club_room_settings (
                organisation_id UUID PRIMARY KEY REFERENCES organisations(id) ON DELETE CASCADE,
                enabled BOOLEAN NOT NULL DEFAULT false,
                rotation_seconds INTEGER NOT NULL DEFAULT 15,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS club_room_slides (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                slide_type TEXT NOT NULL,
                title TEXT,
                config JSONB NOT NULL DEFAULT '{}'::jsonb,
                duration_seconds INTEGER,
                position INTEGER NOT NULL DEFAULT 0,
                enabled BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_club_room_slides_org "
            "ON club_room_slides(organisation_id, position)"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS club_room_media (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                source TEXT NOT NULL DEFAULT 'upload',
                caption TEXT,
                image_data BYTEA NOT NULL,
                image_mime TEXT NOT NULL,
                created_by UUID,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_club_room_media_org "
            "ON club_room_media(organisation_id, source, created_at DESC)"))
        # Club Room Mode — light/dark stage theme + shuffle (migration 207).
        await conn.execute(text(
            "ALTER TABLE club_room_settings ADD COLUMN IF NOT EXISTS theme TEXT NOT NULL DEFAULT 'dark'"))
        await conn.execute(text(
            "ALTER TABLE club_room_settings ADD COLUMN IF NOT EXISTS shuffle BOOLEAN NOT NULL DEFAULT false"))
        # Club Room Mode — public PIN-gated link (migration 210).
        await conn.execute(text(
            "ALTER TABLE club_room_settings ADD COLUMN IF NOT EXISTS link_token TEXT"))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_club_room_settings_link_token "
            "ON club_room_settings(link_token) WHERE link_token IS NOT NULL"))
        await conn.execute(text(
            "ALTER TABLE club_room_settings ADD COLUMN IF NOT EXISTS public_link_enabled "
            "BOOLEAN NOT NULL DEFAULT false"))
        await conn.execute(text(
            "ALTER TABLE club_room_settings ADD COLUMN IF NOT EXISTS require_pin "
            "BOOLEAN NOT NULL DEFAULT true"))
        await conn.execute(text(
            "ALTER TABLE club_room_settings ADD COLUMN IF NOT EXISTS pin_hash TEXT"))
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
        # A grade is not one thing (migration 259). "Women's T20 Grade 2" is a
        # women's grade AND a T20 grade, so the type and the format each get
        # their own multi-valued column. `category` stays, kept in step with the
        # first entry of `categories`, so every existing reader is untouched.
        await conn.execute(text(
            "ALTER TABLE grades ADD COLUMN IF NOT EXISTS categories TEXT[]"
        ))
        await conn.execute(text(
            "ALTER TABLE grades ADD COLUMN IF NOT EXISTS match_formats TEXT[]"
        ))
        await conn.execute(text(
            "UPDATE grades SET categories = ARRAY[category] "
            "WHERE categories IS NULL AND category IS NOT NULL AND category <> ''"
        ))
        # A club's own default for which of those categories count towards its
        # stats (migration 228). NULL = no preference, so the platform default
        # (everything except junior) applies. See services/grade_scope.py.
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
            "stats_grade_categories JSONB"
        ))
        # Migration 229 — show a player the grades they actually played when the
        # default would hide every one of them.
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
            "stats_auto_show_played_grades BOOLEAN NOT NULL DEFAULT true"
        ))
        # Migration 230 — the TRUE per-innings total (bat runs + extras) straight
        # from GR's own `innings[].runsScored`/`numberOfWicketsFallen`/
        # `totalExtras`, which sync previously discarded in favour of an
        # approximate SUM(batting_innings.runs) that undercounts every total by
        # its extras. Prospective-only (populated at sync time going forward,
        # see sync.py) — nothing here backfills an already-synced game. JSONB
        # array (not scalar columns) since a two-day game can carry more than
        # one innings per side. See services/iq_team.py's `_per_game` for the
        # read-side preference over the bat-only sum.
        await conn.execute(text(
            "ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"
        ))
        # Migration 234 — which BetterImport batch minted a player. Set only
        # when the import commit creates the row; undo uses it to delete the
        # batch's own players once the undo leaves them empty (see
        # services/import_cleanup.py). SET NULL so a deleted batch never takes
        # a player with it.
        await conn.execute(text(
            "ALTER TABLE players ADD COLUMN IF NOT EXISTS import_batch_id UUID "
            "REFERENCES import_batches(id) ON DELETE SET NULL"
        ))
        # Migration 248 — membership is multi-valued and scoped; roles and
        # honours are separate axes. A person is several kinds of member at once
        # (Senior Player AND Parent), the catalogue splits internal from
        # external (a sponsor's contact is not a member the club counts), and
        # Life Membership is an honour on the person spine rather than a type.
        # fee_members.membership_type_id stays as the PRIMARY type, since
        # BetterFees has to bill one tier.
        await conn.execute(text(
            "ALTER TABLE membership_types ADD COLUMN IF NOT EXISTS scope TEXT NOT NULL DEFAULT 'internal'"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS member_membership_types (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                member_id UUID NOT NULL REFERENCES fee_members(id) ON DELETE CASCADE,
                membership_type_id UUID NOT NULL REFERENCES membership_types(id) ON DELETE CASCADE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (member_id, membership_type_id)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_member_membership_types_org "
            "ON member_membership_types(organisation_id, membership_type_id)"
        ))
        await conn.execute(text("ALTER TABLE fee_members ADD COLUMN IF NOT EXISTS life_member_since DATE"))
        # Migration 249 — gender on the person spine (it lived only on `players`,
        # so a non-player had nowhere to carry one, and the Directory filters on
        # it), plus free text beside the life-membership date for whatever the
        # club records against the honour, usually a life member number.
        await conn.execute(text("ALTER TABLE fee_members ADD COLUMN IF NOT EXISTS gender TEXT"))
        await conn.execute(text("ALTER TABLE fee_members ADD COLUMN IF NOT EXISTS life_member_detail TEXT"))
        await conn.execute(text("""
            UPDATE membership_types SET scope = 'external'
            WHERE lower(name) IN ('sponsor contact', 'external contact', 'third party', 'contractor')
              AND scope <> 'external'
        """))
        # Guarded on the member holding no rows yet, NOT on the pair — this
        # re-runs every boot and a per-pair guard would re-add a type the club
        # has since unticked.
        await conn.execute(text("""
            INSERT INTO member_membership_types (organisation_id, member_id, membership_type_id)
            SELECT fm.organisation_id, fm.id, fm.membership_type_id
            FROM fee_members fm
            WHERE fm.membership_type_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM member_membership_types a WHERE a.member_id = fm.id
              )
            ON CONFLICT (member_id, membership_type_id) DO NOTHING
        """))
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
        # Migration 192: day-over-day engagement baseline for the CRM pipeline's
        # up/down arrow — see the column comments in models/db.py.
        await conn.execute(text(
            "ALTER TABLE marketing_clubs ADD COLUMN IF NOT EXISTS engagement_score_prev INTEGER"))
        await conn.execute(text(
            "ALTER TABLE marketing_clubs ADD COLUMN IF NOT EXISTS engagement_score_prev_date DATE"))
        # Migration 166: cached suburb boundary polygon for the directory's location
        # map, fetched on demand from OpenStreetMap/Nominatim and cached forever —
        # see services/nominatim_client.py.
        await conn.execute(text(
            "ALTER TABLE marketing_clubs ADD COLUMN IF NOT EXISTS boundary_geojson JSONB"))
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
        # BetterSocials media library + brand kit (migration 191).
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS social_media_asset (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                filename TEXT,
                mime TEXT,
                image_data BYTEA,
                width INTEGER,
                height INTEGER,
                created_by UUID,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_social_media_asset_organisation_id "
            "ON social_media_asset(organisation_id)"))
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS social_brand_kit JSONB"))
        # BetterSelect vote collection (migration 193) — defensive idempotent
        # creates so the API boots even if alembic hasn't run yet.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS vote_settings (
                organisation_id UUID PRIMARY KEY REFERENCES organisations(id) ON DELETE CASCADE,
                enabled BOOLEAN NOT NULL DEFAULT false,
                link_token TEXT,
                require_pin BOOLEAN NOT NULL DEFAULT true,
                voter_mode TEXT NOT NULL DEFAULT 'players',
                ballot_values JSONB NOT NULL DEFAULT '[3,2,1]'::jsonb,
                counting_method TEXT NOT NULL DEFAULT 'rank',
                tie_policy TEXT NOT NULL DEFAULT 'share',
                allow_self_vote BOOLEAN NOT NULL DEFAULT false,
                allow_non_participants BOOLEAN NOT NULL DEFAULT false,
                auto_close_days INTEGER NOT NULL DEFAULT 7,
                updated_at TIMESTAMPTZ DEFAULT now()
            )
        """))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_vote_settings_link_token "
            "ON vote_settings(link_token) WHERE link_token IS NOT NULL"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS vote_ballots (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                fixture_id UUID NOT NULL REFERENCES fixtures(id) ON DELETE CASCADE,
                voter_player_id UUID REFERENCES players(id) ON DELETE CASCADE,
                voter_name TEXT,
                voter_kind TEXT NOT NULL DEFAULT 'player',
                source TEXT NOT NULL DEFAULT 'self',
                recorded_by UUID REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now()
            )
        """))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_vote_ballot_player "
            "ON vote_ballots(fixture_id, voter_player_id) WHERE voter_player_id IS NOT NULL"))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_vote_ballot_name "
            "ON vote_ballots(fixture_id, lower(voter_name)) "
            "WHERE voter_player_id IS NULL AND voter_name IS NOT NULL"))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_vote_ballots_org_fixture "
            "ON vote_ballots(organisation_id, fixture_id)"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS vote_ballot_picks (
                ballot_id UUID NOT NULL REFERENCES vote_ballots(id) ON DELETE CASCADE,
                position INTEGER NOT NULL,
                player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
                PRIMARY KEY (ballot_id, position),
                UNIQUE (ballot_id, player_id)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_vote_ballot_picks_player "
            "ON vote_ballot_picks(player_id)"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS vote_fixture_overrides (
                fixture_id UUID PRIMARY KEY REFERENCES fixtures(id) ON DELETE CASCADE,
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                status TEXT,
                set_by UUID REFERENCES users(id) ON DELETE SET NULL,
                set_at TIMESTAMPTZ DEFAULT now()
            )
        """))
        # Vote eligibility source (migration 194) — scorecard | lineup | playhq.
        await conn.execute(text(
            "ALTER TABLE vote_settings ADD COLUMN IF NOT EXISTS "
            "eligibility_source TEXT NOT NULL DEFAULT 'scorecard'"))
        await conn.execute(text(
            "ALTER TABLE vote_fixture_overrides ADD COLUMN IF NOT EXISTS eligibility_source TEXT"))
        await conn.execute(text(
            "ALTER TABLE vote_fixture_overrides ALTER COLUMN status DROP NOT NULL"))
        # Player name aliases (migration 195) — a former/alternate name that
        # still resolves to the right player after a rename.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS player_name_aliases (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
                alias_name TEXT NOT NULL,
                alias_key TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'manual',
                created_at TIMESTAMPTZ DEFAULT now()
            )
        """))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_player_name_alias_key "
            "ON player_name_aliases(organisation_id, alias_key)"))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_player_name_aliases_player "
            "ON player_name_aliases(player_id)"))
        # Votes redesign — nudge send log (migration 196), backs the
        # one-nudge-per-player-per-fixture-per-24h rate limit.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS vote_nudges (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                fixture_id UUID NOT NULL REFERENCES fixtures(id) ON DELETE CASCADE,
                player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
                sent_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_vote_nudges_fixture_player "
            "ON vote_nudges(fixture_id, player_id, sent_at)"))
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
            "imported_stat_ids",
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
            # The club the enquirer picked from the Cricket Australia club
            # search, and whether they picked it or typed it (migration 224).
            "club_org_id", "club_source",
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
        # City-centroid coordinates from the same ip-api.com lookup that
        # already resolves region/city (its free tier includes lat/lon
        # alongside regionName/city — no extra request). Powers the Usage
        # page's visitor map. Never street-level: this is the geolocation
        # database's own city/ISP-block precision, same ceiling as the
        # region/city text fields above.
        await conn.execute(text(
            "ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION"
        ))
        await conn.execute(text(
            "ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS lng DOUBLE PRECISION"
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
        # Migration 165: how long a visitor actually stayed on a page. Filled
        # by a `page_exit` beacon (visibilitychange/pagehide/unload) — see
        # usePageView.js — not by anything at page-view time, so it starts
        # NULL and is set once the visitor leaves. Session duration is a
        # read-time computation over this + created_at, not a stored column.
        await conn.execute(text(
            "ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS time_on_page_ms INTEGER"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_usage_events_visitor_type_created "
            "ON usage_events(visitor_id, event_type, created_at) WHERE visitor_id IS NOT NULL"
        ))
        # Materialised prospect-club attribution. twenty_sync._engagement's web
        # query resolves each event to a club via the 7-subquery _RESOLVED_CID
        # expression; filtering on that computed value forces a full re-resolution
        # of the table per club (~6s each) — fine for a batch sweep, far too slow
        # to fire on every page view (it caused a lock pileup when it did). This
        # column stores that resolution ONCE, stamped by the event's own
        # background CRM task (crm.check_web_signal_promotion) right after it
        # resolves the club for its gate — so a single-club recompute becomes an
        # indexed lookup (ms) and the score can refresh instantly on every signal.
        # Backfill the 90-day scoring window with app/scripts/backfill_resolved_club.py
        # after deploy; new rows are stamped live. NULL = not yet resolved/attributed.
        await conn.execute(text(
            "ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS resolved_marketing_club_id UUID"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_usage_events_resolved_club_created "
            "ON usage_events(resolved_marketing_club_id, created_at DESC) "
            "WHERE resolved_marketing_club_id IS NOT NULL"
        ))
        # Migration 214: ip_hash had never been indexed here, so
        # usage_tracker._enrich_geo's post-lookup backfill (WHERE ip_hash = ...)
        # was a full scan of an append-only, never-pruned table on every
        # newly-seen IP — holding a connection and row locks long enough for
        # concurrent ones to drain the pool ("QueuePool limit of size 20
        # overflow 30 reached"). The second index covers the Usage map's own
        # read: anonymous geo-enriched rows by recency.
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_usage_events_ip_hash_created "
            "ON usage_events(ip_hash, created_at DESC) WHERE ip_hash IS NOT NULL"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_usage_events_geo_map "
            "ON usage_events(created_at DESC) WHERE lat IS NOT NULL AND user_id IS NULL"
        ))
        # Backup/restore task tracking (migration 170) — one row per backup or
        # restore run (scheduled via the host systemd timer, or triggered on
        # demand from Super Admin), so the Backups page can show a history plus
        # the size/row-count stats captured at the time. Written by
        # app/scripts/backup_task.py, not the ORM.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS backup_tasks (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                task_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'requested',
                scope_org_id UUID REFERENCES organisations(id) ON DELETE SET NULL,
                triggered_by TEXT NOT NULL DEFAULT 'scheduled',
                triggered_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                bundle_path TEXT,
                bundle_timestamp TIMESTAMPTZ,
                started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                completed_at TIMESTAMPTZ,
                db_size_bytes BIGINT,
                uploads_size_bytes BIGINT,
                total_row_count BIGINT,
                club_stats JSONB,
                error_message TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_backup_tasks_created ON backup_tasks(created_at DESC)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_backup_tasks_status ON backup_tasks(status)"
        ))
        # Migration 171: live progress reporting for a running task (current
        # table/entity, current/total, a human message, and a running tally
        # of finished stages) — read by the Super Admin Backups page while
        # polling a `running` task.
        await conn.execute(text(
            "ALTER TABLE backup_tasks ADD COLUMN IF NOT EXISTS progress JSONB"
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
        # Who started each sync (migration 186) — powers the "Started by" column
        # on the Super Admin Usage page's Current Background Processes panel, and
        # lets a self-healed resume carry the original trigger's user forward.
        await conn.execute(text(
            "ALTER TABLE sync_runs ADD COLUMN IF NOT EXISTS triggered_by_user_id UUID"
        ))
        # Self-healing for interrupted syncs. A sync_run still 'running' at boot
        # was cut off by the previous shutdown/restart (nothing is live yet in
        # this fresh process, so any 'running' row is definitively stale).
        # Capture the resumable org-level ones so a background step near the end
        # of startup can restart them (see _resume_interrupted_syncs), then
        # finalize every stale 'running' row as errored so the dashboard shows
        # no phantom in-flight sync — a resumed sync gets a brand-new run row,
        # it never reuses this errored one.
        _interrupted_rows = (await conn.execute(text("""
            SELECT id, org_id, kind, triggered_by_user_id
            FROM sync_runs
            WHERE status = 'running'
              AND kind IN ('org_full', 'org_hard_refresh')
        """))).mappings().all()
        interrupted_syncs_to_resume = [
            {
                "old_run_id": str(r["id"]),
                "org_id": str(r["org_id"]),
                "kind": r["kind"],
                "user_id": str(r["triggered_by_user_id"]) if r["triggered_by_user_id"] else None,
            }
            for r in _interrupted_rows
        ]
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
        # Auto-remove unsubscribed/bounced contacts from all static lists
        # (migration 202); default on. See services/comms_lists.py.
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
            "comms_auto_remove_unsubscribed BOOLEAN NOT NULL DEFAULT true"
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
        # Manual vs auto-generated lists (migration 203) — the Lists page groups
        # them into separate sections for super admins; auto lists are minted by
        # other BetterCricket functions (e.g. the CRM Sales Pipeline).
        await conn.execute(text(
            "ALTER TABLE comms_lists ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'manual'"))
        await conn.execute(text(
            "ALTER TABLE comms_lists ADD COLUMN IF NOT EXISTS origin TEXT"))
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
        # The original 3-column unique index (snapshot_date, level, ad_id) that
        # used to be created here is GONE — superseded by the 4-column
        # campaign_id-aware one further down (migration 162). Do not
        # reintroduce a "CREATE UNIQUE INDEX IF NOT EXISTS
        # uq_meta_ad_snapshots_date_level_ad" line here: once two campaigns
        # have both written a same-day snapshot (the exact scenario 162 exists
        # to support), the old 3-column definition is genuinely violated by
        # real data — "IF NOT EXISTS" only skips it while the index doesn't
        # exist, so the very first boot after 162 successfully drops it, EVERY
        # later boot tries to recreate the old (now-broken) definition and
        # crashes the app on startup. This took the site down in production
        # (Jul 2026) — see the campaign scoping note below before touching
        # either index statement again.
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
        # (migration 164). Neither table recorded which real Meta campaign a
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
        # Meta Ads — real delivery status per ad (migration 170). Insights
        # fields never carry an ad's ACTIVE/PAUSED state, so the HQ dashboard's
        # performance badge used to keep showing stale "Winner"/"On track"
        # labels on an ad that had actually been paused (e.g. via the Meta Ads
        # MCP). Stored on ad-level snapshot rows only.
        await conn.execute(text("ALTER TABLE meta_ad_snapshots ADD COLUMN IF NOT EXISTS delivery_status TEXT"))
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
        # Club crest in public page headers (migration 226).
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
            "public_header_logo BOOLEAN NOT NULL DEFAULT false"
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
        # How the club was onboarded (migration 225) — 'self_serve_trial' |
        # 'super_admin_trial' | 'direct_subscriber' | 'none'. Read by
        # services/trial_engagement.py (staff-performed registrations score
        # lower) and routers/onboarding_wizard.py (auto-open the setup wizard
        # for a genuinely new trial club, never a long-established one).
        await conn.execute(text("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS onboarding_method TEXT"))
        # The club's own history (migration 227) — the founding year and any
        # former names, shown under the club name on the public dashboard.
        # Both nullable: a club that has never filled them in shows neither.
        await conn.execute(text("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS established_year INTEGER"))
        await conn.execute(text("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS previous_names JSONB"))
        # The competitions the club has played in (migration 262) — same shape
        # and same validation as previous_names, its own column because a club
        # changes competition far more often than it changes its name.
        await conn.execute(text("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS competitions JSONB"))
        # The order a club reads its own teams in (migration 227). NULL sorts
        # last, so an unordered grade keeps its previous alphabetical place.
        await conn.execute(text("ALTER TABLE grades ADD COLUMN IF NOT EXISTS display_order INTEGER"))
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
        # A cached Stripe id belongs to ONE mode — a test-mode Coupon/Product
        # is not there when a live key asks for it (migration 263). Existing
        # rows keep 'unknown', which no lookup matches, so the object is
        # re-created in the current mode the next time it's needed.
        await conn.execute(text(
            "ALTER TABLE stripe_products ADD COLUMN IF NOT EXISTS stripe_mode TEXT NOT NULL DEFAULT 'unknown'"
        ))
        await conn.execute(text(
            "ALTER TABLE stripe_coupons ADD COLUMN IF NOT EXISTS stripe_mode TEXT NOT NULL DEFAULT 'unknown'"
        ))
        await conn.execute(text("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conrelid = 'stripe_products'::regclass AND contype = 'p'
                ) THEN
                    ALTER TABLE stripe_products DROP CONSTRAINT stripe_products_pkey;
                END IF;
                IF EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conrelid = 'stripe_coupons'::regclass AND contype = 'p'
                ) THEN
                    ALTER TABLE stripe_coupons DROP CONSTRAINT stripe_coupons_pkey;
                END IF;
            END $$;
        """))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_stripe_products_key_mode "
            "ON stripe_products (billing_key, stripe_mode)"
        ))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_stripe_coupons_cents_mode "
            "ON stripe_coupons (discount_cents, stripe_mode)"
        ))
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
        # Which Stripe mode minted stripe_coupon_id (migration 263). NULL on
        # every coupon created before this shipped, which reads as "not this
        # mode" and re-syncs the mirrored Coupon on first use.
        await conn.execute(text("ALTER TABLE discount_coupons ADD COLUMN IF NOT EXISTS stripe_mode TEXT"))
        # Commission attribution on a CRM deal (migration 264) — who EARNED
        # the club, as distinct from owner_user_id, who is merely working it
        # now. Byte-identical to alembic/versions/264_crm_commission_
        # attribution.py, including the one-time backfill from the activity
        # rows already recorded.
        await conn.execute(text(
            "ALTER TABLE crm_deals ADD COLUMN IF NOT EXISTS commission_rep_user_id UUID "
            "REFERENCES users(id) ON DELETE SET NULL"
        ))
        await conn.execute(text(
            "ALTER TABLE crm_deals ADD COLUMN IF NOT EXISTS commission_attributed_at TIMESTAMPTZ"
        ))
        await conn.execute(text(
            "ALTER TABLE crm_deals ADD COLUMN IF NOT EXISTS commission_attributed_via TEXT"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_crm_deals_commission_rep "
            "ON crm_deals (commission_rep_user_id) WHERE commission_rep_user_id IS NOT NULL"
        ))
        await conn.execute(text("""
            WITH qualifying AS (
                SELECT DISTINCT ON (a.deal_id)
                       a.deal_id,
                       a.created_by_user_id,
                       a.occurred_at,
                       CASE WHEN a.type = 'email' THEN 'email' ELSE 'call' END AS via
                FROM crm_activities a
                JOIN club_memberships cm ON cm.user_id = a.created_by_user_id AND cm.role = 'sales'
                WHERE a.deal_id IS NOT NULL
                  AND a.created_by_user_id IS NOT NULL
                  AND (
                        a.type = 'email'
                     OR (a.type = 'call' AND (a.outcome IS NULL OR a.outcome <> 'general_note'))
                  )
                ORDER BY a.deal_id, a.occurred_at ASC
            )
            UPDATE crm_deals d
               SET commission_rep_user_id = q.created_by_user_id,
                   commission_attributed_at = q.occurred_at,
                   commission_attributed_via = q.via
              FROM qualifying q
             WHERE q.deal_id = d.id
               AND d.commission_rep_user_id IS NULL
        """))
        # Migration 265: hiding a player from the public site, plus the two
        # BetterSelect flags a club can set by hand (both nullable — NULL
        # means "no override, use what BetterFees / Net Manager say").
        await conn.execute(text(
            "ALTER TABLE players ADD COLUMN IF NOT EXISTS "
            "is_public BOOLEAN NOT NULL DEFAULT true"
        ))
        await conn.execute(text(
            "ALTER TABLE players ADD COLUMN IF NOT EXISTS is_financial_override BOOLEAN"
        ))
        await conn.execute(text(
            "ALTER TABLE players ADD COLUMN IF NOT EXISTS trained_override BOOLEAN"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_players_org_hidden "
            "ON players (organisation_id) WHERE is_public IS FALSE"
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
    # Migration 167: per-side organisation id on shared game rows — lets each
    # of two both-synced clubs record which side of a shared games.id row it
    # was on, independently of the other club's write. See migration 167 for
    # the missing-games/mislabeled-opponent background this fixes.
    async with engine.begin() as conn:
        await conn.execute(text(
            "ALTER TABLE games ADD COLUMN IF NOT EXISTS home_org_id UUID"
        ))
        await conn.execute(text(
            "ALTER TABLE games ADD COLUMN IF NOT EXISTS away_org_id UUID"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_games_home_org_id ON games(home_org_id) WHERE home_org_id IS NOT NULL"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_games_away_org_id ON games(away_org_id) WHERE away_org_id IS NOT NULL"
        ))

    # Migration 168: club-merger audit log — see services/org_merge.py.
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS org_merge_logs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                source_org_id UUID REFERENCES organisations(id) ON DELETE SET NULL,
                source_org_name TEXT NOT NULL,
                target_org_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                performed_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                performed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                seasons_moved INTEGER NOT NULL DEFAULT 0,
                seasons_merged INTEGER NOT NULL DEFAULT 0,
                grades_moved INTEGER NOT NULL DEFAULT 0,
                grades_merged INTEGER NOT NULL DEFAULT 0,
                games_repointed INTEGER NOT NULL DEFAULT 0,
                players_moved INTEGER NOT NULL DEFAULT 0,
                players_merged INTEGER NOT NULL DEFAULT 0
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_org_merge_logs_target "
            "ON org_merge_logs(target_org_id, performed_at DESC)"
        ))

    # Migration 173: BetterCRM — People/Contacts + the internal & club-facing
    # Deal pipeline. See services/crm.py; one schema, two scopes (platform =
    # BetterCricket's own sales pipeline, club = the BetterAdmin CRM module).
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS crm_people (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID REFERENCES organisations(id) ON DELETE CASCADE,
                marketing_club_id UUID REFERENCES marketing_clubs(id) ON DELETE SET NULL,
                player_id UUID REFERENCES players(id) ON DELETE SET NULL,
                full_name TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                notes TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_crm_people_org ON crm_people(organisation_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_crm_people_marketing_club ON crm_people(marketing_club_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_crm_people_email ON crm_people(lower(email))"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS crm_person_roles (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                person_id UUID NOT NULL REFERENCES crm_people(id) ON DELETE CASCADE,
                organisation_id UUID REFERENCES organisations(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                title TEXT,
                started_at DATE,
                ended_at DATE,
                notes TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_crm_person_roles_person ON crm_person_roles(person_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_crm_person_roles_org_role ON crm_person_roles(organisation_id, role)"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS crm_pipelines (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                scope TEXT NOT NULL DEFAULT 'club',
                organisation_id UUID REFERENCES organisations(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                is_default BOOLEAN NOT NULL DEFAULT false,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_crm_pipelines_scope_org ON crm_pipelines(scope, organisation_id)"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS crm_stages (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                pipeline_id UUID NOT NULL REFERENCES crm_pipelines(id) ON DELETE CASCADE,
                key TEXT NOT NULL,
                name TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                default_probability INTEGER NOT NULL DEFAULT 0,
                is_won BOOLEAN NOT NULL DEFAULT false,
                is_lost BOOLEAN NOT NULL DEFAULT false,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_crm_stages_pipeline_key UNIQUE (pipeline_id, key)
            )
        """))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_crm_stages_pipeline_position ON crm_stages(pipeline_id, position)"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS crm_deals (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                scope TEXT NOT NULL DEFAULT 'club',
                organisation_id UUID REFERENCES organisations(id) ON DELETE CASCADE,
                marketing_club_id UUID REFERENCES marketing_clubs(id) ON DELETE SET NULL,
                pipeline_id UUID NOT NULL REFERENCES crm_pipelines(id) ON DELETE CASCADE,
                stage_id UUID NOT NULL REFERENCES crm_stages(id) ON DELETE RESTRICT,
                title TEXT NOT NULL,
                value_cents INTEGER NOT NULL DEFAULT 0,
                currency TEXT NOT NULL DEFAULT 'AUD',
                probability INTEGER,
                module_keys JSONB NOT NULL DEFAULT '[]',
                expected_close_date DATE,
                status TEXT NOT NULL DEFAULT 'open',
                lost_reason TEXT,
                owner_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                source TEXT,
                archived_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                closed_at TIMESTAMPTZ
            )
        """))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_crm_deals_scope_org ON crm_deals(scope, organisation_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_crm_deals_marketing_club ON crm_deals(marketing_club_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_crm_deals_pipeline_stage ON crm_deals(pipeline_id, stage_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_crm_deals_status ON crm_deals(status)"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS crm_deal_contacts (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                deal_id UUID NOT NULL REFERENCES crm_deals(id) ON DELETE CASCADE,
                person_id UUID NOT NULL REFERENCES crm_people(id) ON DELETE CASCADE,
                role_on_deal TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_crm_deal_contacts UNIQUE (deal_id, person_id)
            )
        """))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_crm_deal_contacts_person ON crm_deal_contacts(person_id)"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS crm_activities (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                deal_id UUID REFERENCES crm_deals(id) ON DELETE CASCADE,
                person_id UUID REFERENCES crm_people(id) ON DELETE CASCADE,
                organisation_id UUID REFERENCES organisations(id) ON DELETE CASCADE,
                type TEXT NOT NULL DEFAULT 'note',
                body TEXT,
                occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                meta JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_crm_activities_deal ON crm_activities(deal_id, occurred_at DESC)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_crm_activities_person ON crm_activities(person_id, occurred_at DESC)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_crm_activities_org ON crm_activities(organisation_id, occurred_at DESC)"))
        # CRM Sales Pipeline scheduled events (migration 196) — Call/Demo/
        # Meeting/Review Deal/Other planned for a future date & time, with an
        # optional Owner, Club Contact, Location, Title and up to two alerts.
        # Created from a deal's card detail (deal_id set) or standalone from
        # the Events page. deal_id SET NULL so an event survives a deal delete.
        # See models/db.py::CrmEvent and routers/crm.py. (Placed here — after
        # crm_deals/crm_people exist — since it FKs both.)
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS crm_events (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                deal_id UUID REFERENCES crm_deals(id) ON DELETE SET NULL,
                marketing_club_id UUID REFERENCES marketing_clubs(id) ON DELETE SET NULL,
                contact_person_id UUID REFERENCES crm_people(id) ON DELETE SET NULL,
                owner_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                event_type TEXT NOT NULL DEFAULT 'meeting',
                title TEXT,
                location TEXT,
                body TEXT,
                starts_at TIMESTAMPTZ NOT NULL,
                first_alert TEXT,
                second_alert TEXT,
                created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_crm_events_starts_at ON crm_events(starts_at)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_crm_events_deal ON crm_events(deal_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_crm_events_marketing_club ON crm_events(marketing_club_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_crm_events_owner ON crm_events(owner_user_id)"))

    # Migration 174: BetterCRM optional trackers — a club adds pipelines from
    # a preset catalogue (or a fully custom one) rather than getting one
    # auto-seeded. See services/crm.py's PIPELINE_TEMPLATES.
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE crm_pipelines ADD COLUMN IF NOT EXISTS template_key TEXT"))
        await conn.execute(text(
            "ALTER TABLE crm_pipelines ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_crm_pipelines_template ON crm_pipelines(organisation_id, template_key)"
        ))

    # Migration 175: Membership Management + Family/Household. See
    # services/membership_types.py + routers/families.py.
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS membership_types (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                description TEXT,
                default_annual_fee NUMERIC(10,2),
                is_playing BOOLEAN NOT NULL DEFAULT false,
                requires_voting_rights BOOLEAN NOT NULL DEFAULT false,
                requires_insurance BOOLEAN NOT NULL DEFAULT false,
                requires_wwcc BOOLEAN NOT NULL DEFAULT false,
                requires_playhq_registration BOOLEAN NOT NULL DEFAULT false,
                comms_group TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_active BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_membership_types_org_name UNIQUE (organisation_id, name)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_membership_types_org ON membership_types(organisation_id, is_active)"
        ))
        await conn.execute(text(
            "ALTER TABLE fee_members ADD COLUMN IF NOT EXISTS membership_type_id UUID "
            "REFERENCES membership_types(id) ON DELETE SET NULL"
        ))
        await conn.execute(text(
            "ALTER TABLE fee_members ADD COLUMN IF NOT EXISTS is_life_member BOOLEAN NOT NULL DEFAULT false"
        ))
        await conn.execute(text(
            "ALTER TABLE fee_members ADD COLUMN IF NOT EXISTS is_honorary BOOLEAN NOT NULL DEFAULT false"
        ))
        await conn.execute(text("ALTER TABLE fee_members ADD COLUMN IF NOT EXISTS honorary_expires_at DATE"))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_fee_members_type ON fee_members(membership_type_id)"
        ))
        await conn.execute(text(
            "ALTER TABLE fee_member_seasons ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active'"
        ))
        await conn.execute(text("ALTER TABLE family_members ALTER COLUMN player_id DROP NOT NULL"))
        await conn.execute(text(
            "ALTER TABLE family_members ADD COLUMN IF NOT EXISTS fee_member_id UUID "
            "REFERENCES fee_members(id) ON DELETE CASCADE"
        ))
        await conn.execute(text(
            "ALTER TABLE family_members ADD COLUMN IF NOT EXISTS is_guardian BOOLEAN NOT NULL DEFAULT false"
        ))
        await conn.execute(text(
            "ALTER TABLE family_members ADD COLUMN IF NOT EXISTS receives_family_comms BOOLEAN NOT NULL DEFAULT true"
        ))
        await conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_family_member_fee_member
            ON family_members(family_id, fee_member_id) WHERE fee_member_id IS NOT NULL
        """))

    # Migration 176: Committee Administration, Volunteer Management,
    # Qualification tracking. See services/committee.py, volunteers.py,
    # qualifications.py.
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS committee_positions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                responsibilities TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_active BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_committee_positions_org_name UNIQUE (organisation_id, name)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_committee_positions_org ON committee_positions(organisation_id, is_active)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS committee_terms (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                position_id UUID NOT NULL REFERENCES committee_positions(id) ON DELETE CASCADE,
                member_id UUID REFERENCES fee_members(id) ON DELETE SET NULL,
                holder_name TEXT NOT NULL,
                started_at DATE NOT NULL DEFAULT CURRENT_DATE,
                ended_at DATE,
                handover_notes TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_committee_terms_position ON committee_terms(position_id, ended_at)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_committee_terms_org ON committee_terms(organisation_id)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS committee_tasks (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                description TEXT,
                category TEXT NOT NULL DEFAULT 'operational',
                position_id UUID REFERENCES committee_positions(id) ON DELETE SET NULL,
                assigned_to_member_id UUID REFERENCES fee_members(id) ON DELETE SET NULL,
                due_date DATE,
                status TEXT NOT NULL DEFAULT 'todo',
                is_recurring BOOLEAN NOT NULL DEFAULT false,
                recurrence_note TEXT,
                completed_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_committee_tasks_org ON committee_tasks(organisation_id, status)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_committee_tasks_due ON committee_tasks(organisation_id, due_date)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS committee_documents (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'governance',
                url TEXT NOT NULL,
                position_id UUID REFERENCES committee_positions(id) ON DELETE SET NULL,
                notes TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_committee_documents_org ON committee_documents(organisation_id, category)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS club_events (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                event_type TEXT NOT NULL DEFAULT 'other',
                starts_at TIMESTAMPTZ NOT NULL,
                ends_at TIMESTAMPTZ,
                location TEXT,
                description TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_club_events_org ON club_events(organisation_id, starts_at)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS volunteer_profiles (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                member_id UUID NOT NULL REFERENCES fee_members(id) ON DELETE CASCADE,
                roles_interested JSONB NOT NULL DEFAULT '[]',
                available_days JSONB NOT NULL DEFAULT '[]',
                lives_nearby BOOLEAN NOT NULL DEFAULT false,
                notes TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_volunteer_profiles_org_member UNIQUE (organisation_id, member_id)
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS volunteer_hours (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                member_id UUID NOT NULL REFERENCES fee_members(id) ON DELETE CASCADE,
                logged_date DATE NOT NULL DEFAULT CURRENT_DATE,
                hours NUMERIC(6,2) NOT NULL DEFAULT 0,
                activity TEXT,
                notes TEXT,
                created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_volunteer_hours_member ON volunteer_hours(member_id, logged_date DESC)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_volunteer_hours_org ON volunteer_hours(organisation_id, logged_date DESC)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS qualification_types (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                description TEXT,
                validity_months INTEGER,
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_active BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_qualification_types_org_name UNIQUE (organisation_id, name)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_qualification_types_org ON qualification_types(organisation_id, is_active)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS member_qualifications (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                member_id UUID NOT NULL REFERENCES fee_members(id) ON DELETE CASCADE,
                qualification_type_id UUID NOT NULL REFERENCES qualification_types(id) ON DELETE CASCADE,
                obtained_at DATE NOT NULL DEFAULT CURRENT_DATE,
                expires_at DATE,
                certificate_ref TEXT,
                notes TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_member_qualifications_member ON member_qualifications(member_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_member_qualifications_expiry ON member_qualifications(organisation_id, expires_at)"
        ))

    # Migration 177: AGM meetings/elections/motions, Events/Ticketing,
    # Assets & Facilities. See services/committee.py (meetings/AGM),
    # services/events.py, services/assets.py.
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS agenda_templates (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                items JSONB NOT NULL DEFAULT '[]',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_agenda_templates_org_name UNIQUE (organisation_id, name)
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS committee_meetings (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                meeting_type TEXT NOT NULL DEFAULT 'committee',
                scheduled_at TIMESTAMPTZ NOT NULL,
                location TEXT,
                status TEXT NOT NULL DEFAULT 'scheduled',
                minutes TEXT,
                agenda_template_id UUID REFERENCES agenda_templates(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_committee_meetings_org ON committee_meetings(organisation_id, scheduled_at)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS meeting_attendance (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                meeting_id UUID NOT NULL REFERENCES committee_meetings(id) ON DELETE CASCADE,
                member_id UUID NOT NULL REFERENCES fee_members(id) ON DELETE CASCADE,
                status TEXT NOT NULL DEFAULT 'present',
                CONSTRAINT uq_meeting_attendance UNIQUE (meeting_id, member_id)
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS meeting_agenda_items (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                meeting_id UUID NOT NULL REFERENCES committee_meetings(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                description TEXT,
                proposed_by_member_id UUID REFERENCES fee_members(id) ON DELETE SET NULL,
                position INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'proposed',
                outcome_notes TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_meeting_agenda_items_meeting ON meeting_agenda_items(meeting_id, position)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS meeting_motions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                meeting_id UUID NOT NULL REFERENCES committee_meetings(id) ON DELETE CASCADE,
                agenda_item_id UUID REFERENCES meeting_agenda_items(id) ON DELETE SET NULL,
                motion_type TEXT NOT NULL DEFAULT 'motion',
                description TEXT NOT NULL,
                proposed_by_member_id UUID REFERENCES fee_members(id) ON DELETE SET NULL,
                seconded_by_member_id UUID REFERENCES fee_members(id) ON DELETE SET NULL,
                votes_for INTEGER,
                votes_against INTEGER,
                votes_abstain INTEGER,
                outcome TEXT NOT NULL DEFAULT 'pending',
                notes TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_meeting_motions_meeting ON meeting_motions(meeting_id)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS agm_nominations (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                meeting_id UUID NOT NULL REFERENCES committee_meetings(id) ON DELETE CASCADE,
                position_id UUID NOT NULL REFERENCES committee_positions(id) ON DELETE CASCADE,
                candidate_member_id UUID NOT NULL REFERENCES fee_members(id) ON DELETE CASCADE,
                nominated_by_member_id UUID REFERENCES fee_members(id) ON DELETE SET NULL,
                seconded_by_member_id UUID REFERENCES fee_members(id) ON DELETE SET NULL,
                votes_for INTEGER,
                status TEXT NOT NULL DEFAULT 'nominated',
                notes TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_agm_nominations_meeting ON agm_nominations(meeting_id, position_id)"
        ))
        await conn.execute(text(
            "ALTER TABLE club_events ADD COLUMN IF NOT EXISTS is_ticketed BOOLEAN NOT NULL DEFAULT false"
        ))
        await conn.execute(text(
            "ALTER TABLE club_events ADD COLUMN IF NOT EXISTS ticket_price_cents INTEGER NOT NULL DEFAULT 0"
        ))
        await conn.execute(text("ALTER TABLE club_events ADD COLUMN IF NOT EXISTS capacity INTEGER"))
        await conn.execute(text(
            "ALTER TABLE club_events ADD COLUMN IF NOT EXISTS registration_deadline TIMESTAMPTZ"
        ))
        await conn.execute(text(
            "ALTER TABLE club_events ADD COLUMN IF NOT EXISTS registration_open BOOLEAN NOT NULL DEFAULT true"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS event_registrations (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                event_id UUID NOT NULL REFERENCES club_events(id) ON DELETE CASCADE,
                full_name TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                quantity INTEGER NOT NULL DEFAULT 1,
                amount_cents INTEGER NOT NULL DEFAULT 0,
                payment_status TEXT NOT NULL DEFAULT 'free',
                notes TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_event_registrations_event ON event_registrations(event_id)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS facilities (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                facility_type TEXT NOT NULL DEFAULT 'other',
                description TEXT,
                key_location TEXT,
                is_active BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_facilities_org ON facilities(organisation_id, is_active)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS facility_bookings (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                facility_id UUID NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                starts_at TIMESTAMPTZ NOT NULL,
                ends_at TIMESTAMPTZ,
                booked_by_member_id UUID REFERENCES fee_members(id) ON DELETE SET NULL,
                notes TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_facility_bookings_facility ON facility_bookings(facility_id, starts_at)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS club_assets (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'other',
                asset_tag TEXT,
                purchase_cost NUMERIC(10,2),
                purchase_date DATE,
                condition TEXT NOT NULL DEFAULT 'good',
                status TEXT NOT NULL DEFAULT 'in_service',
                service_due_date DATE,
                replace_due_date DATE,
                facility_id UUID REFERENCES facilities(id) ON DELETE SET NULL,
                notes TEXT,
                is_active BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_club_assets_org ON club_assets(organisation_id, is_active)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS maintenance_logs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                subject_type TEXT NOT NULL,
                subject_id UUID NOT NULL,
                performed_at DATE NOT NULL DEFAULT CURRENT_DATE,
                description TEXT NOT NULL,
                cost NUMERIC(10,2),
                performed_by TEXT,
                next_due_date DATE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_maintenance_logs_subject ON maintenance_logs(subject_type, subject_id, performed_at DESC)"
        ))

    # Migration 178: Member self-service portal, Stripe Connect fee payments,
    # reminder automation. See services/member_portal_auth.py,
    # services/stripe_connect_client.py, services/member_reminders.py.
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS member_portal_override BOOLEAN"))
        await conn.execute(text("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS stripe_connect_account_id TEXT"))
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS stripe_connect_details_submitted BOOLEAN NOT NULL DEFAULT false"
        ))
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS stripe_connect_charges_enabled BOOLEAN NOT NULL DEFAULT false"
        ))
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS stripe_connect_payouts_enabled BOOLEAN NOT NULL DEFAULT false"
        ))
        await conn.execute(text(
            "ALTER TABLE member_qualifications ADD COLUMN IF NOT EXISTS last_reminder_sent_at TIMESTAMPTZ"
        ))
        await conn.execute(text(
            "ALTER TABLE fee_member_seasons ADD COLUMN IF NOT EXISTS last_fee_reminder_sent_at TIMESTAMPTZ"
        ))

    # Migration 179: Merch storefront — public online ordering against the
    # existing BetterMerch catalogue. See services/merch_store.py.
    async with engine.begin() as conn:
        await conn.execute(text(
            "ALTER TABLE merch_products ADD COLUMN IF NOT EXISTS show_in_storefront BOOLEAN NOT NULL DEFAULT true"
        ))
        await conn.execute(text("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS merch_storefront_override BOOLEAN"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS merch_orders (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                customer_name TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                member_id UUID REFERENCES fee_members(id) ON DELETE SET NULL,
                status TEXT NOT NULL DEFAULT 'pending_payment',
                total_cents INTEGER NOT NULL DEFAULT 0,
                stripe_checkout_session_id TEXT,
                stripe_payment_intent_id TEXT,
                notes TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_merch_orders_org ON merch_orders(organisation_id, status)"
        ))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_merch_orders_checkout_session "
            "ON merch_orders(stripe_checkout_session_id) WHERE stripe_checkout_session_id IS NOT NULL"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS merch_order_items (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                order_id UUID NOT NULL REFERENCES merch_orders(id) ON DELETE CASCADE,
                variant_id UUID REFERENCES merch_variants(id) ON DELETE SET NULL,
                product_name TEXT NOT NULL,
                variant_label TEXT,
                unit_price_cents INTEGER NOT NULL DEFAULT 0,
                quantity INTEGER NOT NULL DEFAULT 1
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_merch_order_items_order ON merch_order_items(order_id)"
        ))

    # Migration 180: Event registration Stripe Connect payment fields.
    async with engine.begin() as conn:
        await conn.execute(text(
            "ALTER TABLE event_registrations ADD COLUMN IF NOT EXISTS stripe_checkout_session_id TEXT"
        ))
        await conn.execute(text(
            "ALTER TABLE event_registrations ADD COLUMN IF NOT EXISTS stripe_payment_intent_id TEXT"
        ))

    # Migration 181: Club Diary — annual/recurring compliance & maintenance
    # task calendar. See services/club_diary.py.
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS club_diary_categories (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_club_diary_categories_org_name UNIQUE (organisation_id, name)
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS club_diary_task_definitions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                category_id UUID REFERENCES club_diary_categories(id) ON DELETE SET NULL,
                title TEXT NOT NULL,
                description TEXT,
                frequency TEXT NOT NULL DEFAULT 'annual',
                default_month INTEGER,
                default_assignee_position_id UUID REFERENCES committee_positions(id) ON DELETE SET NULL,
                default_assignee_member_id UUID REFERENCES fee_members(id) ON DELETE SET NULL,
                is_active BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_club_diary_definitions_org_title UNIQUE (organisation_id, title)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_club_diary_definitions_org ON club_diary_task_definitions(organisation_id, is_active)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS club_diary_task_occurrences (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                definition_id UUID NOT NULL REFERENCES club_diary_task_definitions(id) ON DELETE CASCADE,
                period_label TEXT NOT NULL,
                due_date DATE,
                status TEXT NOT NULL DEFAULT 'pending',
                assigned_to_member_id UUID REFERENCES fee_members(id) ON DELETE SET NULL,
                notes TEXT,
                completed_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_club_diary_occurrence_period UNIQUE (definition_id, period_label)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_club_diary_occurrences_org ON club_diary_task_occurrences(organisation_id, status)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_club_diary_occurrences_definition "
            "ON club_diary_task_occurrences(definition_id, period_label DESC)"
        ))

    # Migration 182: Club Diary — optional reminder emails. See
    # services/club_diary_reminders.py.
    async with engine.begin() as conn:
        await conn.execute(text(
            "ALTER TABLE club_diary_task_definitions ADD COLUMN IF NOT EXISTS reminder_enabled BOOLEAN NOT NULL DEFAULT false"
        ))
        await conn.execute(text(
            "ALTER TABLE club_diary_task_definitions ADD COLUMN IF NOT EXISTS reminder_days_before INTEGER NOT NULL DEFAULT 14"
        ))
        await conn.execute(text(
            "ALTER TABLE club_diary_task_occurrences ADD COLUMN IF NOT EXISTS last_reminder_sent_at TIMESTAMPTZ"
        ))

    # Migration 183: hide a Kanban stage/column from the board without deleting it.
    async with engine.begin() as conn:
        await conn.execute(text(
            "ALTER TABLE crm_stages ADD COLUMN IF NOT EXISTS hidden_from_board BOOLEAN NOT NULL DEFAULT false"
        ))
    # Persist the "Minimize this column" board preference per stage (mirrors
    # hidden_from_board), so a collapsed column stays collapsed across sessions.
    async with engine.begin() as conn:
        await conn.execute(text(
            "ALTER TABLE crm_stages ADD COLUMN IF NOT EXISTS minimized BOOLEAN NOT NULL DEFAULT false"
        ))

    # Migration 184: CRM deal onboarding method, lead source, discretionary discount.
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE crm_deals ADD COLUMN IF NOT EXISTS onboarding_method TEXT"))
        await conn.execute(text("ALTER TABLE crm_deals ADD COLUMN IF NOT EXISTS lead_source TEXT"))
        await conn.execute(text("ALTER TABLE crm_deals ADD COLUMN IF NOT EXISTS discount_amount_cents INTEGER"))
        await conn.execute(text("ALTER TABLE crm_deals ADD COLUMN IF NOT EXISTS discount_percent INTEGER"))
        await conn.execute(text("ALTER TABLE crm_deals ADD COLUMN IF NOT EXISTS discount_reason TEXT"))

    # Migration 185: BetterCRM sales targets (clubs won / ARR / revenue / trials / conversion).
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS crm_targets (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                period_type TEXT NOT NULL,
                period_key TEXT NOT NULL,
                target_clubs_won INTEGER,
                target_arr_cents BIGINT,
                target_revenue_cents BIGINT,
                target_trials INTEGER,
                target_conversion_rate INTEGER,
                notes TEXT,
                created_by UUID REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE (period_type, period_key)
            )
        """))

    # Migration 186: CRM deal Product Interest source (auto | manual).
    async with engine.begin() as conn:
        await conn.execute(text(
            "ALTER TABLE crm_deals ADD COLUMN IF NOT EXISTS product_interest_source "
            "TEXT NOT NULL DEFAULT 'auto'"
        ))

    # Migration 187: untracked stat columns on an uploaded scorecard import as
    # NULL ("not recorded"), never a fake 0 — a summary form has no 4s/6s or
    # maidens at all. Defaults stay, so existing writers that send 0 are unchanged.
    async with engine.begin() as conn:
        for _tbl, _cols in (
            ("manual_batting_innings", ("fours", "sixes")),
            ("manual_bowling_spells", ("maidens", "wides", "no_balls")),
        ):
            for _col in _cols:
                await conn.execute(text(f"ALTER TABLE {_tbl} ALTER COLUMN {_col} DROP NOT NULL"))

    # Migration 188: a super admin deleting a default platform-pipeline stage
    # (e.g. "Self-Serve Trial") must stay deleted — without this, the very
    # next read re-created it (the reconciliation pass that backfills a
    # newly-introduced default stage onto an old pipeline can't otherwise
    # tell "never existed" apart from "deliberately removed").
    async with engine.begin() as conn:
        await conn.execute(text(
            "ALTER TABLE crm_pipelines ADD COLUMN IF NOT EXISTS removed_stage_keys "
            "JSONB NOT NULL DEFAULT '[]'"
        ))

    # Migration 189: crm_deals.stage_auto_locked — set the moment a human
    # explicitly moves a deal's stage, so the auto-promotion engine (below)
    # never nudges that deal forward again.
    async with engine.begin() as conn:
        await conn.execute(text(
            "ALTER TABLE crm_deals ADD COLUMN IF NOT EXISTS stage_auto_locked "
            "BOOLEAN NOT NULL DEFAULT FALSE"
        ))

    # Migration 190: crm_automation_rules — configurable, persistent criteria
    # for platform-pipeline deal creation/stage-promotion (super admin managed
    # at /admin/super/crm-automation). Seeded once, only if empty, with the
    # exact rule set that used to be hardcoded — see services/crm_rules.py.
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS crm_automation_rules (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                trigger TEXT NOT NULL,
                label TEXT NOT NULL,
                params JSONB NOT NULL DEFAULT '{}',
                target_stage_key TEXT NOT NULL,
                force BOOLEAN NOT NULL DEFAULT FALSE,
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_crm_automation_rules_trigger "
            "ON crm_automation_rules(trigger)"
        ))
    from app.models.db import async_session_maker as _async_session_maker_190
    from app.services import crm_rules as _crm_rules
    async with _async_session_maker_190() as _crm_rules_session:
        if await _crm_rules.seed_defaults(_crm_rules_session):
            await _crm_rules_session.commit()

    # Migration 197: BetterClubManager — Roles & Activities taxonomy, Event
    # Types, Volunteer/Qualification/Events/Bookings/Club-Diary extensions.
    # Byte-identical to alembic/versions/197_roles_activities_events.py.
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS club_role_types (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                description TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_club_role_types_org_name UNIQUE (organisation_id, name)
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS club_roles (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                role_type_id UUID REFERENCES club_role_types(id) ON DELETE SET NULL,
                description TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_club_roles_org_title UNIQUE (organisation_id, title)
            )
        """))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_club_roles_org ON club_roles(organisation_id, is_active)"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS club_activity_types (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                description TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_club_activity_types_org_name UNIQUE (organisation_id, name)
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS club_activities (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                activity_type_id UUID REFERENCES club_activity_types(id) ON DELETE SET NULL,
                description TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_club_activities_org_title UNIQUE (organisation_id, title)
            )
        """))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_club_activities_org ON club_activities(organisation_id, is_active)"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS volunteer_roles (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                member_id UUID NOT NULL REFERENCES fee_members(id) ON DELETE CASCADE,
                role_id UUID NOT NULL REFERENCES club_roles(id) ON DELETE CASCADE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_volunteer_roles_member_role UNIQUE (member_id, role_id)
            )
        """))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_volunteer_roles_member ON volunteer_roles(member_id)"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS qualification_roles (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                qualification_id UUID NOT NULL REFERENCES member_qualifications(id) ON DELETE CASCADE,
                role_id UUID NOT NULL REFERENCES club_roles(id) ON DELETE CASCADE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_qualification_roles_qual_role UNIQUE (qualification_id, role_id)
            )
        """))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_qualification_roles_qual ON qualification_roles(qualification_id)"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS club_event_types (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                description TEXT,
                is_committee_only BOOLEAN NOT NULL DEFAULT FALSE,
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_club_event_types_org_name UNIQUE (organisation_id, name)
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS club_diary_task_dependencies (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                definition_id UUID NOT NULL REFERENCES club_diary_task_definitions(id) ON DELETE CASCADE,
                depends_on_definition_id UUID NOT NULL REFERENCES club_diary_task_definitions(id) ON DELETE CASCADE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_club_diary_task_dependency UNIQUE (definition_id, depends_on_definition_id)
            )
        """))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_club_diary_task_deps_def ON club_diary_task_dependencies(definition_id)"))
        # Column additions
        await conn.execute(text("ALTER TABLE club_events ADD COLUMN IF NOT EXISTS event_type_id UUID REFERENCES club_event_types(id) ON DELETE SET NULL"))
        await conn.execute(text("ALTER TABLE club_events ADD COLUMN IF NOT EXISTS organiser_member_id UUID REFERENCES fee_members(id) ON DELETE SET NULL"))
        await conn.execute(text("ALTER TABLE club_events ADD COLUMN IF NOT EXISTS organiser_name TEXT"))
        await conn.execute(text("ALTER TABLE volunteer_hours ADD COLUMN IF NOT EXISTS activity_id UUID REFERENCES club_activities(id) ON DELETE SET NULL"))
        await conn.execute(text("ALTER TABLE facility_bookings ADD COLUMN IF NOT EXISTS contact_name TEXT"))
        await conn.execute(text("ALTER TABLE facility_bookings ADD COLUMN IF NOT EXISTS contact_email TEXT"))
        await conn.execute(text("ALTER TABLE facility_bookings ADD COLUMN IF NOT EXISTS contact_mobile TEXT"))
        await conn.execute(text("ALTER TABLE facility_bookings ADD COLUMN IF NOT EXISTS owner_member_id UUID REFERENCES fee_members(id) ON DELETE SET NULL"))
        await conn.execute(text("ALTER TABLE facility_bookings ADD COLUMN IF NOT EXISTS owner_name TEXT"))
        await conn.execute(text("ALTER TABLE club_diary_categories ADD COLUMN IF NOT EXISTS color TEXT"))
        await conn.execute(text("ALTER TABLE club_diary_task_definitions ADD COLUMN IF NOT EXISTS responsibility_role_id UUID REFERENCES club_roles(id) ON DELETE SET NULL"))
        await conn.execute(text("ALTER TABLE club_diary_task_definitions ADD COLUMN IF NOT EXISTS third_party TEXT"))
        await conn.execute(text("ALTER TABLE club_diary_task_definitions ADD COLUMN IF NOT EXISTS budget_estimate NUMERIC(10, 2)"))
        await conn.execute(text("ALTER TABLE club_diary_task_occurrences ADD COLUMN IF NOT EXISTS assigned_to_role_id UUID REFERENCES club_roles(id) ON DELETE SET NULL"))
        await conn.execute(text("ALTER TABLE club_diary_task_occurrences ADD COLUMN IF NOT EXISTS start_date DATE"))
        await conn.execute(text("ALTER TABLE club_diary_task_occurrences ADD COLUMN IF NOT EXISTS percent_complete INTEGER NOT NULL DEFAULT 0"))
        await conn.execute(text("ALTER TABLE club_diary_task_occurrences ADD COLUMN IF NOT EXISTS estimated_completion_date DATE"))
        await conn.execute(text("ALTER TABLE club_diary_task_occurrences ADD COLUMN IF NOT EXISTS third_party TEXT"))
        await conn.execute(text("ALTER TABLE club_diary_task_occurrences ADD COLUMN IF NOT EXISTS budget_estimate NUMERIC(10, 2)"))
        await conn.execute(text("ALTER TABLE club_diary_task_occurrences ADD COLUMN IF NOT EXISTS actual_expenditure NUMERIC(10, 2)"))

    # Migration 198: unify committee positions with the Roles catalogue.
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE club_roles ADD COLUMN IF NOT EXISTS is_committee BOOLEAN NOT NULL DEFAULT FALSE"))
        await conn.execute(text("ALTER TABLE committee_positions ADD COLUMN IF NOT EXISTS role_id UUID REFERENCES club_roles(id) ON DELETE SET NULL"))

    # Migration 199: standalone index on import_effective_deltas.player_id.
    # The only prior index was the composite (organisation_id, player_id) from
    # migration 070. v_effective_player_season_stats's import branch selects
    # from this table with no WHERE clause — org-scoping happens only via the
    # outer join to `players` — so an unscoped leaderboard/milestones query
    # (no season/grade picked) correlates it against `players` filtered by
    # player_id ALONE, which the composite index can't serve. Postgres falls
    # back to a full sequential scan of this platform-wide table once per
    # outer row, turning an ordinary page load into a multi-minute hang for
    # any club with a large roster. A standalone index fixes the lookup
    # regardless of table size.
    async with engine.begin() as conn:
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_import_deltas_player "
            "ON import_effective_deltas(player_id)"
        ))

    # Migration 200: a real "last updated" per meta_ad_snapshots row.
    # created_at is set once on INSERT; upsert_snapshot's ON CONFLICT DO
    # UPDATE never touched it, so the Meta Ads HQ page's "Last updated" label
    # (read from campaign_row.created_at) went stale after the first refresh
    # of the day and didn't move again until the next day's first snapshot.
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE meta_ad_snapshots ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ"))
        await conn.execute(text("UPDATE meta_ad_snapshots SET updated_at = created_at WHERE updated_at IS NULL"))
        await conn.execute(text("ALTER TABLE meta_ad_snapshots ALTER COLUMN updated_at SET DEFAULT NOW()"))
        await conn.execute(text("ALTER TABLE meta_ad_snapshots ALTER COLUMN updated_at SET NOT NULL"))

    # Migration 201: seed the Meta Ads HQ dashboard's initial "counting since"
    # cutoff (2026-07-28 06:00 Perth) so a noisy early/test period doesn't
    # skew the on-site funnel numbers. Guarded by a separate `_seeded` marker,
    # NOT by whether the value itself is set — a super admin clearing the
    # cutoff later must not have it silently reinstated by the next restart.
    async with engine.begin() as conn:
        await conn.execute(text("""
            UPDATE platform_settings
            SET settings = settings || jsonb_build_object(
                    'meta_ads_counting_since', '2026-07-28T06:00:00+08:00',
                    'meta_ads_counting_since_seeded', true
                ),
                updated_at = NOW()
            WHERE id = 1 AND NOT (settings ? 'meta_ads_counting_since_seeded')
        """))

    # Migration 208: BetterClubManager Roster — operational areas, shift
    # patterns, roster weeks/shifts, settings + a per-volunteer weekly cap.
    # Byte-identical to alembic/versions/208_roster.py.
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS roster_areas (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                department TEXT,
                color TEXT,
                required_role_id UUID REFERENCES club_roles(id) ON DELETE SET NULL,
                required_qualification_type_id UUID REFERENCES qualification_types(id) ON DELETE SET NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_roster_areas_org ON roster_areas(organisation_id, is_active)"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS roster_shift_patterns (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                area_id UUID NOT NULL REFERENCES roster_areas(id) ON DELETE CASCADE,
                day_of_week INTEGER NOT NULL,
                start_time NUMERIC(4,2) NOT NULL,
                end_time NUMERIC(4,2) NOT NULL,
                headcount INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_roster_shift_patterns_area ON roster_shift_patterns(area_id)"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS roster_weeks (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                week_start DATE NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_roster_weeks_org_week UNIQUE (organisation_id, week_start)
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS roster_shifts (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                roster_week_id UUID NOT NULL REFERENCES roster_weeks(id) ON DELETE CASCADE,
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                area_id UUID NOT NULL REFERENCES roster_areas(id) ON DELETE CASCADE,
                day_of_week INTEGER NOT NULL,
                start_time NUMERIC(4,2) NOT NULL,
                end_time NUMERIC(4,2) NOT NULL,
                assignee_member_id UUID REFERENCES fee_members(id) ON DELETE SET NULL,
                warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_roster_shifts_week ON roster_shifts(roster_week_id)"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS roster_settings (
                organisation_id UUID PRIMARY KEY REFERENCES organisations(id) ON DELETE CASCADE,
                enforce_qualifications BOOLEAN NOT NULL DEFAULT TRUE,
                weekly_shift_cap INTEGER NOT NULL DEFAULT 0,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text("ALTER TABLE volunteer_profiles ADD COLUMN IF NOT EXISTS max_shifts_per_week INTEGER"))

    # Migration 209: BetterClubManager Facilities — booking-requests approval
    # queue. Byte-identical to alembic/versions/209_facility_booking_requests.py.
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS facility_booking_requests (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                facility_id UUID NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                starts_at TIMESTAMPTZ NOT NULL,
                ends_at TIMESTAMPTZ NOT NULL,
                requester_name TEXT,
                requester_email TEXT,
                note TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                decided_at TIMESTAMPTZ
            )
        """))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_facility_booking_requests_org ON facility_booking_requests(organisation_id, status)"))

    # Migration 211: BetterClubManager — a managed Departments catalogue for
    # Operational Areas. Byte-identical to alembic/versions/211_roster_departments.py.
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS roster_departments (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_roster_departments_org_name UNIQUE (organisation_id, name)
            )
        """))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_roster_departments_org ON roster_departments(organisation_id, is_active)"))

    # Migration 212: BetterClubManager Directory — non-player people + third
    # parties on the shared fee_members spine. Byte-identical to
    # alembic/versions/212_member_directory.py.
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE fee_members ADD COLUMN IF NOT EXISTS member_category TEXT"))
        await conn.execute(text("ALTER TABLE fee_members ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ"))

    # Migration 213: role-type categories + committee office-bearer flag.
    # Byte-identical to alembic/versions/213_role_type_category.py.
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE club_role_types ADD COLUMN IF NOT EXISTS category TEXT NOT NULL DEFAULT 'volunteer'"))
        await conn.execute(text("ALTER TABLE committee_positions ADD COLUMN IF NOT EXISTS is_office_bearer BOOLEAN NOT NULL DEFAULT FALSE"))

    # Migration 215: per-club custom typography (display + body font, each
    # preset or uploaded). Byte-identical to alembic/versions/215_club_custom_fonts.py.
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS font_config JSONB"))
        await conn.execute(text("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS font_display_data BYTEA"))
        await conn.execute(text("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS font_display_mime TEXT"))
        await conn.execute(text("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS font_body_data BYTEA"))
        await conn.execute(text("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS font_body_mime TEXT"))

    # Migration 216: third typography role (numbers/stats, "mono"). Byte-identical
    # to alembic/versions/216_club_font_mono.py.
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS font_mono_data BYTEA"))
        await conn.execute(text("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS font_mono_mime TEXT"))

    # Migration 217: committee governance — resolutions, per-member votes,
    # action budgets/dependencies/objectives and threaded notes. Byte-identical
    # to alembic/versions/217_committee_governance.py.
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS club_objectives (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                description TEXT,
                plan TEXT,
                season_year INTEGER,
                status TEXT NOT NULL DEFAULT 'active',
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_club_objectives_org ON club_objectives(organisation_id, status)"))
        for col, ddl in (
            ("objective_id", "UUID REFERENCES club_objectives(id) ON DELETE SET NULL"),
            ("budget_estimate", "NUMERIC(12,2)"),
            ("actual_expenditure", "NUMERIC(12,2)"),
            ("percent_complete", "INTEGER NOT NULL DEFAULT 0"),
            ("start_date", "DATE"),
            ("closed_by_member_id", "UUID REFERENCES fee_members(id) ON DELETE SET NULL"),
            ("outcome_notes", "TEXT"),
            ("meeting_id", "UUID REFERENCES committee_meetings(id) ON DELETE SET NULL"),
            ("motion_id", "UUID REFERENCES meeting_motions(id) ON DELETE SET NULL"),
        ):
            await conn.execute(text(f"ALTER TABLE committee_tasks ADD COLUMN IF NOT EXISTS {col} {ddl}"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS committee_task_dependencies (
                task_id UUID NOT NULL REFERENCES committee_tasks(id) ON DELETE CASCADE,
                depends_on_task_id UUID NOT NULL REFERENCES committee_tasks(id) ON DELETE CASCADE,
                PRIMARY KEY (task_id, depends_on_task_id)
            )
        """))
        for col, ddl in (
            ("is_resolution", "BOOLEAN NOT NULL DEFAULT FALSE"),
            ("resolution_ref", "TEXT"),
            ("resolved_at", "TIMESTAMPTZ"),
        ):
            await conn.execute(text(f"ALTER TABLE meeting_motions ADD COLUMN IF NOT EXISTS {col} {ddl}"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS meeting_motion_votes (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                motion_id UUID NOT NULL REFERENCES meeting_motions(id) ON DELETE CASCADE,
                member_id UUID NOT NULL REFERENCES fee_members(id) ON DELETE CASCADE,
                vote TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_motion_vote_per_member UNIQUE (motion_id, member_id)
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS committee_notes (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                entity_type TEXT NOT NULL,
                entity_id UUID NOT NULL,
                body TEXT NOT NULL,
                author_member_id UUID REFERENCES fee_members(id) ON DELETE SET NULL,
                author_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_committee_notes_entity ON committee_notes(organisation_id, entity_type, entity_id)"))
        await conn.execute(text("ALTER TABLE committee_documents ADD COLUMN IF NOT EXISTS entity_type TEXT"))
        await conn.execute(text("ALTER TABLE committee_documents ADD COLUMN IF NOT EXISTS entity_id UUID"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_committee_documents_entity ON committee_documents(organisation_id, entity_type, entity_id)"))

        # Migration 218: a committee document can hold the file itself, who may
        # open an uploaded one, and the link from an Office Bearer award to the
        # club_roles row it names.
        for col, ddl in (
            ("file_data", "BYTEA"),
            ("file_name", "TEXT"),
            ("file_mime", "TEXT"),
            ("file_size", "INTEGER"),
            ("uploaded_by_user_id", "UUID REFERENCES users(id) ON DELETE SET NULL"),
        ):
            await conn.execute(text(f"ALTER TABLE committee_documents ADD COLUMN IF NOT EXISTS {col} {ddl}"))
        # An uploaded document has no external URL; a row now carries one or the other.
        await conn.execute(text("ALTER TABLE committee_documents ALTER COLUMN url DROP NOT NULL"))
        await conn.execute(text("""
            ALTER TABLE organisations
            ADD COLUMN IF NOT EXISTS committee_docs_office_bearer_only
            BOOLEAN NOT NULL DEFAULT TRUE
        """))
        await conn.execute(text("""
            ALTER TABLE player_achievements
            ADD COLUMN IF NOT EXISTS club_role_id UUID REFERENCES club_roles(id) ON DELETE SET NULL
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_player_achievements_club_role
            ON player_achievements(club_role_id)
        """))

        # Migration 220: what running a live meeting needs — an action raised
        # under an agenda item, several people owning one action, motions
        # ordered against the agenda, and the secretary's own notes.
        await conn.execute(text("""
            ALTER TABLE committee_tasks ADD COLUMN IF NOT EXISTS agenda_item_id UUID
            REFERENCES meeting_agenda_items(id) ON DELETE SET NULL
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS committee_task_assignees (
                task_id UUID NOT NULL REFERENCES committee_tasks(id) ON DELETE CASCADE,
                member_id UUID NOT NULL REFERENCES fee_members(id) ON DELETE CASCADE,
                PRIMARY KEY (task_id, member_id)
            )
        """))
        await conn.execute(text("""
            INSERT INTO committee_task_assignees (task_id, member_id)
            SELECT id, assigned_to_member_id FROM committee_tasks
            WHERE assigned_to_member_id IS NOT NULL
            ON CONFLICT DO NOTHING
        """))
        await conn.execute(text("ALTER TABLE meeting_motions ADD COLUMN IF NOT EXISTS position INTEGER NOT NULL DEFAULT 0"))
        await conn.execute(text("ALTER TABLE committee_meetings ADD COLUMN IF NOT EXISTS private_notes TEXT"))

        # Migration 221: paid vs volunteer work, hours against a shift, and a
        # club's own diary year.
        await conn.execute(text("ALTER TABLE volunteer_hours ADD COLUMN IF NOT EXISTS is_paid BOOLEAN NOT NULL DEFAULT FALSE"))
        await conn.execute(text("ALTER TABLE volunteer_hours ADD COLUMN IF NOT EXISTS roster_shift_id UUID"))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_volunteer_hours_shift
            ON volunteer_hours(roster_shift_id) WHERE roster_shift_id IS NOT NULL
        """))
        await conn.execute(text("""
            ALTER TABLE organisations
            ADD COLUMN IF NOT EXISTS diary_start_month INTEGER NOT NULL DEFAULT 7
        """))

        # Migration 222: confirming a roster — hours worked, checked and posted
        # to the volunteer hours ledger.
        await conn.execute(text("ALTER TABLE roster_shifts ADD COLUMN IF NOT EXISTS worked_hours NUMERIC(5,2)"))
        await conn.execute(text("ALTER TABLE roster_weeks ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMPTZ"))
        await conn.execute(text("ALTER TABLE roster_weeks ADD COLUMN IF NOT EXISTS confirmed_by_user_id UUID"))
        await conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_volunteer_hours_shift
            ON volunteer_hours(roster_shift_id) WHERE roster_shift_id IS NOT NULL
        """))

        # Migration 230: a strategic plan is a record rather than a name typed
        # onto every objective, an objective carries its own due date/owner/
        # budget, and a motion can serve an objective the way an action already
        # could. Byte-identical to alembic/versions/230_strategic_plans.py.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS club_strategic_plans (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                description TEXT,
                start_year INTEGER,
                end_year INTEGER,
                status TEXT NOT NULL DEFAULT 'active',
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_club_strategic_plans_org "
            "ON club_strategic_plans(organisation_id, status)"
        ))
        for col, ddl in (
            ("plan_id", "UUID REFERENCES club_strategic_plans(id) ON DELETE SET NULL"),
            ("due_date", "DATE"),
            ("owner_member_id", "UUID REFERENCES fee_members(id) ON DELETE SET NULL"),
            ("budget", "NUMERIC(12,2)"),
        ):
            await conn.execute(text(f"ALTER TABLE club_objectives ADD COLUMN IF NOT EXISTS {col} {ddl}"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_club_objectives_plan ON club_objectives(plan_id)"))
        await conn.execute(text(
            "ALTER TABLE meeting_motions ADD COLUMN IF NOT EXISTS "
            "objective_id UUID REFERENCES club_objectives(id) ON DELETE SET NULL"
        ))
        # NOT EXISTS, not ON CONFLICT: this block re-runs on every boot and
        # there is no unique constraint on (org, name) for a conflict clause to
        # fire against, so without it each restart would mint the plans again.
        await conn.execute(text("""
            INSERT INTO club_strategic_plans (organisation_id, name)
            SELECT o.organisation_id, MIN(BTRIM(o.plan))
            FROM club_objectives o
            WHERE o.plan IS NOT NULL AND BTRIM(o.plan) <> ''
              AND NOT EXISTS (
                  SELECT 1 FROM club_strategic_plans p
                  WHERE p.organisation_id = o.organisation_id
                    AND LOWER(BTRIM(p.name)) = LOWER(BTRIM(o.plan))
              )
            GROUP BY o.organisation_id, LOWER(BTRIM(o.plan))
        """))
        await conn.execute(text("""
            UPDATE club_objectives o
            SET plan_id = p.id
            FROM club_strategic_plans p
            WHERE o.plan_id IS NULL
              AND o.plan IS NOT NULL
              AND p.organisation_id = o.organisation_id
              AND LOWER(BTRIM(p.name)) = LOWER(BTRIM(o.plan))
        """))

        # Migration 231: an agenda item belongs to a section of the meeting's
        # order of business. Byte-identical to
        # alembic/versions/231_agenda_sections.py.
        await conn.execute(text("ALTER TABLE meeting_agenda_items ADD COLUMN IF NOT EXISTS section TEXT"))

        # Migration 232: the club's strategic pillars, and an objective that can
        # be owned by a committee SEAT so ownership survives the AGM.
        # Byte-identical to alembic/versions/232_strategic_pillars.py.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS club_strategic_pillars (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                description TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_club_strategic_pillars_org "
            "ON club_strategic_pillars(organisation_id, is_active)"
        ))
        for col, ddl in (
            ("pillar_id", "UUID REFERENCES club_strategic_pillars(id) ON DELETE SET NULL"),
            ("owner_position_id", "UUID REFERENCES committee_positions(id) ON DELETE SET NULL"),
        ):
            await conn.execute(text(f"ALTER TABLE club_objectives ADD COLUMN IF NOT EXISTS {col} {ddl}"))

        # Migration 223: a member row may only link to a player of the SAME
        # club. NOT VALID, so it guards every new write from the moment it
        # lands without failing on rows an earlier bug already left behind
        # (those are cleared by app.scripts.purge_foreign_members).
        await conn.execute(text("""
            DO $$ BEGIN
                ALTER TABLE players ADD CONSTRAINT uq_players_org_id UNIQUE (organisation_id, id);
            EXCEPTION WHEN duplicate_table OR duplicate_object THEN NULL;
            END $$
        """))
        await conn.execute(text("""
            DO $$ BEGIN
                ALTER TABLE fee_members
                  ADD CONSTRAINT fk_fee_members_player_same_org
                  FOREIGN KEY (organisation_id, player_id)
                  REFERENCES players (organisation_id, id)
                  ON DELETE SET NULL
                  NOT VALID;
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$
        """))

        # Migration 253: a plain multi-column ON DELETE SET NULL nulls EVERY
        # column of the FK, not just player_id — so deleting a linked player
        # (merge_players' own DELETE FROM players) tried to null
        # organisation_id too and aborted with a NOT NULL violation. Postgres
        # 15's per-column SET NULL (player_id) fixes it without touching
        # organisation_id. Byte-identical to
        # alembic/versions/253_fee_members_fk_set_null_player_only.py.
        await conn.execute(text("""
            DO $$
            DECLARE
              player_id_attnum smallint;
            BEGIN
              IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = 'fee_members' AND relkind = 'r') THEN
                RETURN;
              END IF;

              SELECT attnum INTO player_id_attnum
              FROM pg_attribute
              WHERE attrelid = 'fee_members'::regclass AND attname = 'player_id';

              IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_fee_members_player_same_org'
                  AND conrelid = 'fee_members'::regclass
                  AND confdelsetcols = ARRAY[player_id_attnum]
              ) THEN
                ALTER TABLE fee_members DROP CONSTRAINT IF EXISTS fk_fee_members_player_same_org;
                ALTER TABLE fee_members
                  ADD CONSTRAINT fk_fee_members_player_same_org
                  FOREIGN KEY (organisation_id, player_id)
                  REFERENCES players (organisation_id, id)
                  ON DELETE SET NULL (player_id)
                  NOT VALID;
              END IF;
            END $$
        """))

        # Migration 235: a per-season PlayHQ registration checkbox on
        # fee_member_seasons — playing requires it, and nothing here can read
        # it back from PlayHQ, so an admin ticks it once sighted. Byte-
        # identical to alembic/versions/235_fee_member_season_playhq.py.
        await conn.execute(text(
            "ALTER TABLE fee_member_seasons ADD COLUMN IF NOT EXISTS "
            "playhq_registered BOOLEAN NOT NULL DEFAULT false"
        ))
        await conn.execute(text(
            "ALTER TABLE fee_member_seasons ADD COLUMN IF NOT EXISTS "
            "playhq_registered_at TIMESTAMPTZ"
        ))

        # Migration 236: BetterScout's Scout Org tenant tables — a completely
        # separate login/tenant type living in this same database (see
        # models/scout.py, services/scout_auth.py). Byte-identical to
        # alembic/versions/236_scout_org_tenant.py.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS scout_orgs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name TEXT NOT NULL,
                slug TEXT UNIQUE,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                primary_color TEXT DEFAULT '#16c784',
                accent_color TEXT DEFAULT '#243352',
                theme_mode TEXT DEFAULT 'dark',
                logo_url TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS scout_users (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                scout_org_id UUID NOT NULL REFERENCES scout_orgs(id) ON DELETE CASCADE,
                username TEXT NOT NULL UNIQUE,
                email TEXT,
                password_hash TEXT,
                display_name TEXT,
                role TEXT NOT NULL DEFAULT 'owner',
                last_login_at TIMESTAMPTZ,
                failed_login_count INTEGER NOT NULL DEFAULT 0,
                locked_until TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_scout_users_org ON scout_users(scout_org_id)"
        ))

        # Migration 237: BetterScout player discovery — a platform-wide club
        # stats cache, the durable per-person scouted record, and the
        # per-tenant tracking join. None have any FK to organisations/
        # players. Byte-identical to alembic/versions/237_scout_discovery.py.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS scout_club_cache (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                club_org_guid TEXT NOT NULL UNIQUE,
                club_name TEXT,
                status TEXT NOT NULL DEFAULT 'building',
                payload JSONB,
                error TEXT,
                built_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS scouted_players (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                source TEXT NOT NULL,
                grassroots_participant_id TEXT,
                club_org_guid TEXT,
                club_name TEXT,
                name TEXT NOT NULL,
                grade_name TEXT,
                notes TEXT,
                stats_payload JSONB,
                stats_built_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_scouted_players_participant UNIQUE (grassroots_participant_id)
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS scout_tracked_players (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                scout_org_id UUID NOT NULL REFERENCES scout_orgs(id) ON DELETE CASCADE,
                scouted_player_id UUID NOT NULL REFERENCES scouted_players(id) ON DELETE CASCADE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_scout_tracked_player UNIQUE (scout_org_id, scouted_player_id)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_scout_tracked_players_org "
            "ON scout_tracked_players(scout_org_id)"
        ))

        # Migration 238: BetterScout watchlists — replaces the phase-2
        # scout_tracked_players bookmark with real Kanban boards (multiple
        # per org, renameable columns, cards carrying tags + recruiting
        # fields). Byte-identical to alembic/versions/238_scout_watchlists.py.
        await conn.execute(text("DROP TABLE IF EXISTS scout_tracked_players"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS scout_watchlists (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                scout_org_id UUID NOT NULL REFERENCES scout_orgs(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_scout_watchlists_org ON scout_watchlists(scout_org_id)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS scout_watchlist_columns (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                watchlist_id UUID NOT NULL REFERENCES scout_watchlists(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_scout_watchlist_columns_watchlist "
            "ON scout_watchlist_columns(watchlist_id, position)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS scout_watchlist_cards (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                watchlist_id UUID NOT NULL REFERENCES scout_watchlists(id) ON DELETE CASCADE,
                column_id UUID NOT NULL REFERENCES scout_watchlist_columns(id) ON DELETE CASCADE,
                scouted_player_id UUID NOT NULL REFERENCES scouted_players(id) ON DELETE CASCADE,
                position INTEGER NOT NULL DEFAULT 0,
                tags JSONB NOT NULL DEFAULT '[]',
                role TEXT,
                batting_hand TEXT,
                bowling_action TEXT,
                bowling_type TEXT,
                region TEXT,
                level TEXT,
                transfer_preference TEXT,
                visa_status TEXT,
                agent_contact TEXT,
                availability_window TEXT,
                fee_expectations TEXT,
                notes TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_scout_watchlist_card UNIQUE (watchlist_id, scouted_player_id)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_scout_watchlist_cards_column "
            "ON scout_watchlist_cards(column_id, position)"
        ))

        # Migration 239: BetterScout read-only per-card share link. NULL =
        # not shared. Byte-identical to alembic/versions/239_scout_share_link.py.
        await conn.execute(text(
            "ALTER TABLE scout_watchlist_cards ADD COLUMN IF NOT EXISTS share_token TEXT"
        ))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_scout_watchlist_cards_share_token "
            "ON scout_watchlist_cards(share_token) WHERE share_token IS NOT NULL"
        ))

        # Migration 240: BetterScout pricing tiers (limits + upgrade
        # messaging only, no Stripe). Byte-identical to
        # alembic/versions/240_scout_pricing_tiers.py.
        await conn.execute(text(
            "ALTER TABLE scout_orgs ADD COLUMN IF NOT EXISTS tier TEXT NOT NULL DEFAULT 'starter'"
        ))

        # Migration 241: BetterScout internal-club link (see
        # services/scout_internal_link.py) — plain UUID columns, no FK, per
        # this file's zero-foreign-key isolation rule. Byte-identical to
        # alembic/versions/241_scout_internal_link.py.
        await conn.execute(text(
            "ALTER TABLE scouted_players ADD COLUMN IF NOT EXISTS internal_org_id UUID"
        ))
        await conn.execute(text(
            "ALTER TABLE scouted_players ADD COLUMN IF NOT EXISTS internal_player_id UUID"
        ))

        # Migration 242: BetterScout org settings + invites + share-link
        # expiry stamp. Byte-identical to alembic/versions/242_scout_settings.py.
        for stmt in [
            "ALTER TABLE scout_orgs ADD COLUMN IF NOT EXISTS org_type TEXT",
            "ALTER TABLE scout_orgs ADD COLUMN IF NOT EXISTS home_region TEXT",
            "ALTER TABLE scout_orgs ADD COLUMN IF NOT EXISTS refresh_cadence TEXT NOT NULL DEFAULT 'weekly'",
            "ALTER TABLE scout_orgs ADD COLUMN IF NOT EXISTS stale_after_weeks INTEGER NOT NULL DEFAULT 6",
            "ALTER TABLE scout_orgs ADD COLUMN IF NOT EXISTS default_window TEXT NOT NULL DEFAULT '2'",
            "ALTER TABLE scout_orgs ADD COLUMN IF NOT EXISTS share_include_notes BOOLEAN NOT NULL DEFAULT TRUE",
            "ALTER TABLE scout_orgs ADD COLUMN IF NOT EXISTS share_include_tags BOOLEAN NOT NULL DEFAULT TRUE",
            "ALTER TABLE scout_orgs ADD COLUMN IF NOT EXISTS share_expiry_days INTEGER DEFAULT 90",
            "ALTER TABLE scout_orgs ADD COLUMN IF NOT EXISTS digest_enabled BOOLEAN NOT NULL DEFAULT TRUE",
            "ALTER TABLE scout_orgs ADD COLUMN IF NOT EXISTS alert_scope TEXT NOT NULL DEFAULT 'all_tracked'",
            "ALTER TABLE scout_watchlist_cards ADD COLUMN IF NOT EXISTS share_token_created_at TIMESTAMPTZ",
        ]:
            await conn.execute(text(stmt))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS scout_invites (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                scout_org_id UUID NOT NULL REFERENCES scout_orgs(id) ON DELETE CASCADE,
                email TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'viewer',
                token TEXT NOT NULL UNIQUE,
                invited_by UUID REFERENCES scout_users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                accepted_at TIMESTAMPTZ,
                expires_at TIMESTAMPTZ NOT NULL
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_scout_invites_org ON scout_invites(scout_org_id)"
        ))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_scout_invites_org_email_pending "
            "ON scout_invites(scout_org_id, email) WHERE accepted_at IS NULL"
        ))

        # Migration 243: BetterScout player profile — notes timeline + photo.
        # Byte-identical to alembic/versions/243_scout_profile.py.
        for stmt in [
            "ALTER TABLE scouted_players ADD COLUMN IF NOT EXISTS photo_url TEXT",
            "ALTER TABLE scouted_players ADD COLUMN IF NOT EXISTS photo_data BYTEA",
            "ALTER TABLE scouted_players ADD COLUMN IF NOT EXISTS photo_mime TEXT",
        ]:
            await conn.execute(text(stmt))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS scout_player_notes (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                scout_org_id UUID NOT NULL REFERENCES scout_orgs(id) ON DELETE CASCADE,
                scouted_player_id UUID NOT NULL REFERENCES scouted_players(id) ON DELETE CASCADE,
                author_scout_user_id UUID REFERENCES scout_users(id) ON DELETE SET NULL,
                body TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'other',
                occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_scout_player_notes_org_player "
            "ON scout_player_notes(scout_org_id, scouted_player_id, occurred_at DESC)"
        ))

        # Migration 244: BetterScout scout_club_views (Overview's "Clubs
        # you've looked at"). Byte-identical to
        # alembic/versions/244_scout_club_views.py.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS scout_club_views (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                scout_org_id UUID NOT NULL REFERENCES scout_orgs(id) ON DELETE CASCADE,
                club_org_guid TEXT NOT NULL,
                club_name TEXT,
                last_viewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_scout_club_views_org_club UNIQUE (scout_org_id, club_org_guid)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_scout_club_views_org "
            "ON scout_club_views(scout_org_id, last_viewed_at DESC)"
        ))

        # Migration 245: BetterScout scout_milestone_seen (Milestones "Mark
        # as seen" + badge). Byte-identical to
        # alembic/versions/245_scout_milestone_seen.py.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS scout_milestone_seen (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                scout_org_id UUID NOT NULL REFERENCES scout_orgs(id) ON DELETE CASCADE,
                scouted_player_id UUID NOT NULL REFERENCES scouted_players(id) ON DELETE CASCADE,
                milestone_type TEXT NOT NULL,
                milestone_value INTEGER NOT NULL,
                seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_scout_milestone_seen UNIQUE (scout_org_id, scouted_player_id, milestone_type, milestone_value)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_scout_milestone_seen_org "
            "ON scout_milestone_seen(scout_org_id)"
        ))

        # Migration 246: BetterScout scout_shared_comparisons (Compare's
        # read-only share link). Byte-identical to
        # alembic/versions/246_scout_shared_comparisons.py.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS scout_shared_comparisons (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                scout_org_id UUID NOT NULL REFERENCES scout_orgs(id) ON DELETE CASCADE,
                player_ids JSONB NOT NULL,
                token TEXT NOT NULL UNIQUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                expires_at TIMESTAMPTZ
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_scout_shared_comparisons_org "
            "ON scout_shared_comparisons(scout_org_id)"
        ))

        # Migration 247: BetterScout scouting-report attributes + manual
        # intel on a watchlist card. Byte-identical to
        # alembic/versions/247_scout_card_intel.py.
        await conn.execute(text("ALTER TABLE scout_watchlist_cards ADD COLUMN IF NOT EXISTS is_opening_batsman BOOLEAN"))
        await conn.execute(text("ALTER TABLE scout_watchlist_cards ADD COLUMN IF NOT EXISTS is_wicket_keeper BOOLEAN"))
        await conn.execute(text("ALTER TABLE scout_watchlist_cards ADD COLUMN IF NOT EXISTS fielding_position TEXT"))
        await conn.execute(text("ALTER TABLE scout_watchlist_cards ADD COLUMN IF NOT EXISTS batting_intel JSONB"))
        await conn.execute(text("ALTER TABLE scout_watchlist_cards ADD COLUMN IF NOT EXISTS bowling_intel JSONB"))

        # Migration 250: BetterScout multi-club player tracking
        # (scouted_player_clubs) + player search history
        # (scout_player_search_views). Byte-identical to
        # alembic/versions/250_scout_player_clubs.py.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS scouted_player_clubs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                scouted_player_id UUID NOT NULL REFERENCES scouted_players(id) ON DELETE CASCADE,
                club_org_guid TEXT NOT NULL,
                club_name TEXT,
                grade_name TEXT,
                grassroots_participant_id TEXT,
                is_primary BOOLEAN NOT NULL DEFAULT false,
                stats_payload JSONB,
                stats_built_at TIMESTAMPTZ,
                linked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                linked_via TEXT NOT NULL DEFAULT 'add',
                CONSTRAINT uq_scouted_player_clubs_player_club UNIQUE (scouted_player_id, club_org_guid)
            )
        """))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_scouted_player_clubs_primary "
            "ON scouted_player_clubs(scouted_player_id) WHERE is_primary"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_scouted_player_clubs_player "
            "ON scouted_player_clubs(scouted_player_id)"
        ))
        await conn.execute(text("""
            INSERT INTO scouted_player_clubs
                (id, scouted_player_id, club_org_guid, club_name, grassroots_participant_id,
                 stats_payload, stats_built_at, is_primary, linked_via)
            SELECT gen_random_uuid(), id, club_org_guid, club_name, grassroots_participant_id,
                   stats_payload, stats_built_at, true, 'add'
            FROM scouted_players
            WHERE club_org_guid IS NOT NULL
            ON CONFLICT (scouted_player_id, club_org_guid) DO NOTHING
        """))
        await conn.execute(text("ALTER TABLE scouted_players ADD COLUMN IF NOT EXISTS other_club_candidates JSONB"))
        await conn.execute(text("ALTER TABLE scouted_players ADD COLUMN IF NOT EXISTS other_club_candidates_checked_at TIMESTAMPTZ"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS scout_player_search_views (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                scout_org_id UUID NOT NULL REFERENCES scout_orgs(id) ON DELETE CASCADE,
                scouted_player_id UUID NOT NULL REFERENCES scouted_players(id) ON DELETE CASCADE,
                player_name TEXT,
                query_text TEXT,
                last_viewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_scout_player_search_views_org_player UNIQUE (scout_org_id, scouted_player_id)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_scout_player_search_views_org "
            "ON scout_player_search_views(scout_org_id, last_viewed_at DESC)"
        ))

        # Migration 251: which registration-wizard clubs were exported into
        # which auto-generated BetterComms list, so a send can be reported per
        # club. Byte-identical to alembic/versions/251_wizard_club_lists.py.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS wizard_club_lists (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                list_id UUID NOT NULL,
                list_name TEXT,
                club_key TEXT NOT NULL,
                club_name TEXT NOT NULL,
                marketing_club_id UUID REFERENCES marketing_clubs(id) ON DELETE SET NULL,
                contacts_added INTEGER NOT NULL DEFAULT 0,
                created_by UUID REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_wizard_club_lists_list_club UNIQUE (list_id, club_key)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_wizard_club_lists_key "
            "ON wizard_club_lists(club_key)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_wizard_club_lists_club "
            "ON wizard_club_lists(marketing_club_id)"
        ))

        # Migration 254: tags a social_media_asset as a reusable club-uploaded
        # post background (kind='background') vs an ordinary Photos-tab upload
        # (kind NULL). Byte-identical to
        # alembic/versions/254_social_media_background_kind.py.
        await conn.execute(text(
            "ALTER TABLE social_media_asset ADD COLUMN IF NOT EXISTS kind TEXT"
        ))

        # Migration 255: Sales Workspace — a structured call outcome +
        # follow-up date on crm_activities, and a directory_contact_id bridge
        # on crm_people so a lazily-materialized contact (see
        # services/sales_workspace.resolve_or_materialize_person) traces back
        # to the marketing_club_contacts row it came from. Byte-identical to
        # alembic/versions/255_sales_workspace.py.
        await conn.execute(text("ALTER TABLE crm_activities ADD COLUMN IF NOT EXISTS outcome TEXT"))
        await conn.execute(text(
            "ALTER TABLE crm_activities ADD COLUMN IF NOT EXISTS next_follow_up_at TIMESTAMPTZ"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_crm_activities_follow_up "
            "ON crm_activities(next_follow_up_at) WHERE next_follow_up_at IS NOT NULL"
        ))
        await conn.execute(text(
            "ALTER TABLE crm_people ADD COLUMN IF NOT EXISTS directory_contact_id "
            "UUID REFERENCES marketing_club_contacts(id) ON DELETE SET NULL"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_crm_people_directory_contact "
            "ON crm_people(directory_contact_id) WHERE directory_contact_id IS NOT NULL"
        ))

        # Migration 256: Sales Workspace Phase 2a — Follow-ups queue +
        # do-not-contact. follow_up_done_at is the explicit "mark resolved"
        # signal for a pending callback; do_not_contact/_reason is the
        # PERSON-level "don't call me" flag (club-level reuses the existing
        # marketing_clubs.not_interested, no new column for that). Byte-
        # identical to alembic/versions/256_sales_workspace_followups.py.
        await conn.execute(text("ALTER TABLE crm_activities ADD COLUMN IF NOT EXISTS follow_up_done_at TIMESTAMPTZ"))
        await conn.execute(text(
            "ALTER TABLE marketing_club_contacts ADD COLUMN IF NOT EXISTS do_not_contact "
            "BOOLEAN NOT NULL DEFAULT false"
        ))
        await conn.execute(text(
            "ALTER TABLE marketing_club_contacts ADD COLUMN IF NOT EXISTS do_not_contact_reason TEXT"
        ))

        # Migration 257: Sales Lists — a thin provenance/import layer over the
        # existing CRM deals (assignment still lives on crm_deals.owner_user_id
        # alone; a list is just "these clubs came in together, from this
        # source"). Byte-identical to alembic/versions/257_sales_lists.py.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sales_lists (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name TEXT NOT NULL,
                description TEXT,
                source_type TEXT NOT NULL DEFAULT 'manual',
                created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sales_list_clubs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                sales_list_id UUID NOT NULL REFERENCES sales_lists(id) ON DELETE CASCADE,
                marketing_club_id UUID NOT NULL REFERENCES marketing_clubs(id) ON DELETE CASCADE,
                added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE (sales_list_id, marketing_club_id)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_sales_list_clubs_club ON sales_list_clubs(marketing_club_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_sales_list_clubs_list ON sales_list_clubs(sales_list_id)"
        ))

        # Migration 258: historical-drift findings. The scheduled sync only
        # pulls fixtures since a club's last run, so a Cricket Australia
        # revision to an older season is never re-read; the monthly drift
        # check records its verdict here instead (one row per club+season,
        # updated in place). Byte-identical to
        # alembic/versions/258_sync_drift_findings.py.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sync_drift_findings (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                season_name TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'ok',
                players_compared INTEGER NOT NULL DEFAULT 0,
                players_differing INTEGER NOT NULL DEFAULT 0,
                examples JSONB NOT NULL DEFAULT '[]'::jsonb,
                checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                acknowledged_at TIMESTAMPTZ,
                UNIQUE (organisation_id, season_id)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_sync_drift_findings_open "
            "ON sync_drift_findings(organisation_id) "
            "WHERE status = 'drift' AND acknowledged_at IS NULL"
        ))

        # Migration 260: comms_templates gains a subject line — used by the
        # Sales Workspace's three built-in emails, now editable BetterComms
        # templates in the outreach org rather than hardcoded Python strings.
        # Byte-identical to alembic/versions/260_comms_template_subject.py.
        await conn.execute(text("ALTER TABLE comms_templates ADD COLUMN IF NOT EXISTS subject TEXT"))

        # Migration 261: comms_templates gains a stable sales_template_key —
        # the Sales Workspace's Send an Email dropdown used to resolve its
        # editable template by matching the row's NAME, so renaming a
        # template in Comms -> Templates silently broke the link (and the
        # next reseed minted a duplicate row under the old name). This is
        # the fix: a machine key that survives any rename. Byte-identical to
        # alembic/versions/261_comms_template_sales_key.py, including the
        # one-time backfill from the old name-matching rule.
        await conn.execute(text("ALTER TABLE comms_templates ADD COLUMN IF NOT EXISTS sales_template_key TEXT"))
        await conn.execute(text("""
            DO $$ BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'uq_comms_template_org_sales_key'
                ) THEN
                    ALTER TABLE comms_templates
                        ADD CONSTRAINT uq_comms_template_org_sales_key UNIQUE (organisation_id, sales_template_key);
                END IF;
            END $$;
        """))
        for _key, _name in {
            "information": "Send information",
            "voicemail_followup": "Email following voicemail",
            "trial_information": "Trial information",
            "trial_extension": "Sales rep trial extension",
            "demo": "Book a demo",
            "subscribe": "Sales rep subscribe link",
            "custom": "Custom sales rep email",
        }.items():
            await conn.execute(text(
                "UPDATE comms_templates SET sales_template_key = :key "
                "WHERE name = :name AND sales_template_key IS NULL "
                "AND organisation_id IN (SELECT id FROM organisations WHERE is_marketing_outreach IS TRUE)"
            ), {"key": _key, "name": _name})

    # Ensure uploads directory exists
    upload_dir = Path("/app/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    from app.models.db import async_session_maker as AsyncSessionLocal
    # Generate yearbook stubs for any seasons that don't have one yet — fired as
    # a background task, NOT awaited: it iterates every org/season, so it grows
    # with the platform and had begun to overrun deploy.sh's health-check window
    # (flagging a healthy backend as DOWN). Non-critical (a missing stub is also
    # created on demand), so running it just after boot is safe. Same reasoning
    # as the Stripe sweep below.
    asyncio.create_task(_run_yearbook_stub_sweep())

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

    # Self-heal: restart any org sync interrupted by the previous shutdown.
    # Fired as a background task, NOT awaited — it makes outbound CA-proxy
    # calls and boot must never wait on the network (same reasoning as the
    # Stripe sweep above). The interrupted runs were already finalized as
    # 'error' during the DDL phase; this starts a FRESH incremental sync that
    # idempotently picks up where the crash left off. `interrupted_syncs_to_resume`
    # is defined in the first DDL block above; guard in case that block changes.
    try:
        _to_resume = interrupted_syncs_to_resume
    except NameError:
        _to_resume = []
    if _to_resume:
        logger.info(f"Self-heal: {len(_to_resume)} interrupted sync(s) to resume after restart")
        asyncio.create_task(_resume_interrupted_syncs(_to_resume))

    start_scheduler()
    # Apply the super-admin-set CRM sweep cadences (Tier 2 / Tier 3) to the
    # just-started scheduler — the jobs were registered with the defaults, this
    # reconciles them to the persisted values so a restart keeps a custom cadence.
    try:
        from app.jobs.scheduler import reschedule_crm_sweeps
        from app.services import platform_settings as _ps
        from app.models.db import async_session_maker
        async with async_session_maker() as _s:
            _inc = await _ps.get_crm_incremental_sweep_seconds(_s)
            _glob = await _ps.get_crm_global_sweep_minutes(_s)
        reschedule_crm_sweeps(incremental_seconds=_inc, global_minutes=_glob)
    except Exception:
        logger.exception("could not apply persisted CRM sweep intervals")
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
    # Whole /usage/ family, not just /usage/event: the endpoints here record
    # their own breadcrumb, so a middleware `api` row on top is a second write
    # (and a second pooled connection) per call for no extra information.
    # /usage/heartbeat fires every ~25s per open tab, so it was the single
    # biggest source of that duplication.
    "/usage/",
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
app.include_router(social_media.router)   # BetterSocials media library + brand kit
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
app.include_router(committee.router)     # Committee Administration (core capability, not a paid module)
app.include_router(volunteers.router)    # Volunteer Management (core capability, not a paid module)
app.include_router(qualifications.router)  # Qualification tracking (core capability, not a paid module)
app.include_router(events.router)        # Events/Ticketing admin — registrations against the Club Calendar (core capability, not a paid module)
app.include_router(events.public_router)  # Events/Ticketing public — unauthenticated event view + register (core, not a paid module)
app.include_router(assets.router)        # Assets & Facilities (core capability, not a paid module)
app.include_router(club_diary.router)    # Club Diary — annual/recurring compliance & maintenance tasks (core capability, not a paid module)
app.include_router(club_room.router)     # Club Room Mode — TV slideshow (core capability, not a paid module)
app.include_router(roles_activities.router)  # Roles & Activities taxonomy (core capability, shared by Volunteers + Qualifications)
app.include_router(directory.router)     # BetterClubManager Directory — non-player people + third parties (core capability, not a paid module)
app.include_router(roster.router)        # BetterClubManager Roster — weekly volunteer roster (core capability, not a paid module)
app.include_router(facility_requests.router)  # BetterClubManager Facilities — booking-requests approval queue (core capability, not a paid module)
app.include_router(member_portal_admin.router)  # Member portal visibility check (core, no capability — see the router docstring)
app.include_router(stripe_connect.router)       # Member portal: club-to-member Stripe Connect admin flow (core, flag-gated)
app.include_router(public_stripe_connect.router)  # Member portal: Stripe Connect webhook (public, unauthenticated)
app.include_router(public_member_portal.router)   # Member self-service portal (public, unauthenticated, flag-gated)
app.include_router(manual_entries.router)
app.include_router(imports.router)  # BetterImport — overlap-safe historical CSV import
app.include_router(player_import.router)  # BetterImport (profiles) — bulk player contact/profile CSV import
app.include_router(klubpro_migration.router)  # KlubPro → BetterStats migration (super-admin onboarding)
app.include_router(marketing.router)  # Marketing club directory crawl + outreach (super-admin)
app.include_router(crm.super_router)  # BetterCRM — BetterCricket's own internal sales pipeline (super-admin)
app.include_router(sales_workspace.router)  # Sales Workspace — calling lens over the same platform pipeline (super-admin + 'sales' role)
app.include_router(usage.router)
app.include_router(login_attempts.router)
app.include_router(meta_ads.router)  # Meta Ads HQ dashboard (super-admin) — BetterCricket's own ad spend
app.include_router(self_serve_trial.router)  # Self-serve club trial registration (internal, flag-gated — see docs/self-serve-trial-onboarding-plan.md)
app.include_router(public_self_serve.router)  # Public self-serve trial registration (unauthenticated, same flag — the /trial ad-campaign landing page)
app.include_router(onboarding_wizard.router)  # Club onboarding wizard (flag-gated — see docs/self-serve-trial-onboarding-plan.md Phase 15)
app.include_router(wizard_analytics.router)  # Setup Wizard analytics (super-admin) — where clubs get stuck/skip
app.include_router(backup_admin.router)  # Backup/restore task history + DB size stats (super-admin)
app.include_router(scout_auth_router.router)  # BetterScout — Scout Org login (own tenant type, own cookie; no require_module — unrelated to club entitlements)
app.include_router(scout_discovery_router.router)  # BetterScout — player discovery (club search/roster, add/track a player)
app.include_router(scout_watchlist_router.router)  # BetterScout — watchlists (Kanban boards, tags, recruiting fields)
app.include_router(scout_public_share_router.router)  # BetterScout — unauthenticated read-only per-card share link
app.include_router(scout_settings_router.router)  # BetterScout — org settings, people/invites, share-link management
app.include_router(scout_milestones_router.router)  # BetterScout — the Milestones screen (in reach / reached / seen)
app.include_router(scout_compare_router.router)  # BetterScout — the Compare screen (side-by-side + share link)
app.include_router(scout_feed_router.router)  # BetterScout — Player Name Search + Hot Form Feed (platform-wide, across every cached club roster)
app.include_router(scout_search_router.router)  # BetterScout — the one global search bar (clubs + players together)
# ─── Better ecosystem module gating ──────────────────────────────────────────
# These routers are the discrete Better modules; require_module() returns 402
# (with an upsell payload) when the caller's club isn't entitled. Core routers
# above are always on. BetterSocials' backend surface is gated per-route in
# admin.py (it shares the admin router). See app/auth/modules.py.
app.include_router(fees.router, dependencies=[Depends(require_module("fees"))])           # BetterFees (BetterAdmin)
app.include_router(comms.router, dependencies=[Depends(require_module("comms"))])         # BetterComms (BetterAdmin)
app.include_router(merch.router, dependencies=[Depends(require_module("merch"))])         # BetterMerch (BetterAdmin)
app.include_router(public_merch_store.router)  # Merch storefront (public, unauthenticated) — checks module + flag itself per-org
app.include_router(crm.router, dependencies=[Depends(require_module("crm"))])             # BetterCRM (BetterAdmin)
app.include_router(fixtures.router, dependencies=[Depends(require_module("select"))])     # BetterSelect
app.include_router(teams.router, dependencies=[Depends(require_module("select"))])        # BetterSelect
app.include_router(availability.router, dependencies=[Depends(require_module("select"))]) # BetterSelect
app.include_router(selection.router, dependencies=[Depends(require_module("select"))])    # BetterSelect
app.include_router(net_manager.router, dependencies=[Depends(require_module("select"))])  # BetterSelect (Net Manager)
app.include_router(votes.router, dependencies=[Depends(require_module("select"))])        # BetterSelect (vote collection)
# Player-facing self-service availability (magic link + PIN). Unauthenticated by
# design — it resolves the club from the link token and enforces entitlement +
# enabled-flag itself, so it is NOT wrapped in require_module.
app.include_router(public_availability.router)                                            # BetterSelect (public)
# Player/supporter-facing vote collection (magic link + PIN). Unauthenticated by
# necessity — resolves the club from its vote-link token and checks entitlement +
# the enabled flag itself, so it is NOT wrapped in require_module.
app.include_router(public_votes.router)                                                   # BetterSelect (public votes)
# Club Room Mode's public link (magic link + PIN). Unauthenticated by design —
# resolves the club from its own link token and checks public_link_enabled
# itself, so it is NOT wrapped in require_module (Club Room is Core anyway).
app.include_router(public_club_room.router)                                               # Club Room Mode (public)
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
