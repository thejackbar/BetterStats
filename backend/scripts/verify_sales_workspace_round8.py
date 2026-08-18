"""Verifies GET /clubs/{deal_id} carries the club's Primary Admin's first +
last name, only while the club is trialing (current or expired). Run with:

    DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost/bstest \
    python -m scripts.verify_sales_workspace_round8
"""
import asyncio
import os
import sys
import uuid
import datetime as dt

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/bstest")
os.environ.setdefault("SECRET_KEY", "test-secret")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models.db import Base, User, MarketingClub, Organisation, ClubMembership, OrgModuleSubscription
from app.services import crm as crm_service

FAILS = []


def check(name, cond, detail=""):
    status = "OK" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


async def main():
    engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        from sqlalchemy import text as _text
        await conn.execute(_text("""
            CREATE TABLE IF NOT EXISTS platform_settings (
                id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
                settings JSONB NOT NULL DEFAULT '{}',
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(_text(
            "INSERT INTO platform_settings (id, settings) VALUES (1, '{}') ON CONFLICT (id) DO NOTHING"
        ))
        await conn.execute(_text("""
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
        for _col, _type in (
            ("country", "TEXT"), ("region", "TEXT"), ("city", "TEXT"),
            ("lat", "DOUBLE PRECISION"), ("lng", "DOUBLE PRECISION"),
            ("visitor_id", "UUID"), ("utm_source", "TEXT"), ("utm_medium", "TEXT"),
            ("utm_campaign", "TEXT"), ("utm_content", "TEXT"), ("utm_id", "TEXT"),
            ("click_id", "TEXT"), ("traffic_source", "TEXT"), ("landing_path", "TEXT"),
            ("time_on_page_ms", "INTEGER"), ("resolved_marketing_club_id", "UUID"),
        ):
            await conn.execute(_text(f"ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS {_col} {_type}"))
        # get_club's engagement-breakdown fetch (an onboarded club only, which
        # this round's fixtures are) reaches trial_engagement.trial_depth_score
        # -> merge_logs/grade_merge_logs, two more raw-SQL lifespan tables.
        # Minimal shape copied from main.py's own CREATE TABLE statements —
        # without these the query 500s and, worse, leaves the session's
        # transaction aborted for every query after it in this same script.
        await conn.execute(_text("""
            CREATE TABLE IF NOT EXISTS merge_logs (
                id SERIAL PRIMARY KEY,
                merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID,
                keep_player_id UUID,
                removed_player_id UUID,
                undone_at TIMESTAMPTZ
            )
        """))
        await conn.execute(_text("""
            CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY,
                merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL,
                canonical_name TEXT NOT NULL,
                alias_name TEXT NOT NULL,
                undone_at TIMESTAMPTZ
            )
        """))
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        rep = User(id=uuid.uuid4(), username="sam", display_name="Sam", email="sam@bettersports.com.au",
                   password_hash="x")
        db.add(rep)
        await db.flush()

        # ── Club A: onboarded, currently trialing, has a primary admin ──
        org_a = Organisation(id=uuid.uuid4(), name="Trial Club A", slug="trial-club-a", is_active=True)
        admin_a = User(id=uuid.uuid4(), username="admina", display_name="A Admin",
                       first_name="Pat", last_name="Citizen", email="pat@trialclub-a.com", password_hash="x")
        db.add_all([org_a, admin_a])
        await db.flush()
        db.add(ClubMembership(id=uuid.uuid4(), club_id=org_a.id, user_id=admin_a.id,
                               role="club_admin", is_primary_admin=True))
        db.add(OrgModuleSubscription(id=uuid.uuid4(), organisation_id=org_a.id, module_key="stats",
                                      status="trial", trial_ends_at=dt.datetime.utcnow() + dt.timedelta(days=5)))
        mc_a = MarketingClub(id=uuid.uuid4(), name="Trial Club A", grassroots_guid=f"manual:{uuid.uuid4()}",
                              existing_org_id=org_a.id)
        db.add(mc_a)
        await db.flush()

        # ── Club B: onboarded, trial EXPIRED, has a primary admin ──
        org_b = Organisation(id=uuid.uuid4(), name="Trial Club B", slug="trial-club-b", is_active=True)
        admin_b = User(id=uuid.uuid4(), username="adminb", display_name="B Admin",
                       first_name="Jo", last_name="Bloggs", email="jo@trialclub-b.com", password_hash="x")
        db.add_all([org_b, admin_b])
        await db.flush()
        db.add(ClubMembership(id=uuid.uuid4(), club_id=org_b.id, user_id=admin_b.id,
                               role="club_admin", is_primary_admin=True))
        db.add(OrgModuleSubscription(id=uuid.uuid4(), organisation_id=org_b.id, module_key="stats",
                                      status="trial", trial_ends_at=dt.datetime.utcnow() - dt.timedelta(days=3)))
        mc_b = MarketingClub(id=uuid.uuid4(), name="Trial Club B", grassroots_guid=f"manual:{uuid.uuid4()}",
                              existing_org_id=org_b.id)
        db.add(mc_b)
        await db.flush()

        # ── Club C: onboarded, NOT trialing (no OrgModuleSubscription trial rows) ──
        org_c = Organisation(id=uuid.uuid4(), name="Subscriber Club C", slug="sub-club-c", is_active=True)
        admin_c = User(id=uuid.uuid4(), username="adminc", display_name="C Admin",
                       first_name="Sam", last_name="Subscriber", email="sam@subclub-c.com", password_hash="x")
        db.add_all([org_c, admin_c])
        await db.flush()
        db.add(ClubMembership(id=uuid.uuid4(), club_id=org_c.id, user_id=admin_c.id,
                               role="club_admin", is_primary_admin=True))
        mc_c = MarketingClub(id=uuid.uuid4(), name="Subscriber Club C", grassroots_guid=f"manual:{uuid.uuid4()}",
                              existing_org_id=org_c.id)
        db.add(mc_c)
        await db.flush()

        # ── Club D: a bare prospect, never onboarded (no existing_org_id) ──
        mc_d = MarketingClub(id=uuid.uuid4(), name="Bare Prospect CC", grassroots_guid=f"manual:{uuid.uuid4()}")
        db.add(mc_d)
        await db.flush()

        pipeline = await crm_service.ensure_platform_pipeline(db)
        target_stage = next(s for s in pipeline.stages if s.key == "target")
        deals = {}
        for key, mc in (("a", mc_a), ("b", mc_b), ("c", mc_c), ("d", mc_d)):
            deals[key] = await crm_service.create_deal(
                db, scope=crm_service.SCOPE_PLATFORM, pipeline_id=pipeline.id, stage_id=target_stage.id,
                title=mc.name, marketing_club_id=mc.id, owner_user_id=rep.id,
            )
        await db.commit()

        from app.routers.sales_workspace import get_club

        class FakeActor:
            def __init__(self, user, role):
                self.user = user
                self.role = role

        actor = FakeActor(rep, "sales")

        result_a = await get_club(str(deals["a"].id), actor=actor, db=db)
        check("Club A (current trial): primary_admin_name is Pat Citizen",
              result_a["deal"]["primary_admin_name"] == "Pat Citizen", result_a["deal"].get("primary_admin_name"))
        check("Club A: min_trial_days_remaining is non-negative (current)",
              result_a["deal"]["min_trial_days_remaining"] is not None
              and result_a["deal"]["min_trial_days_remaining"] >= 0)

        result_b = await get_club(str(deals["b"].id), actor=actor, db=db)
        check("Club B (expired trial): primary_admin_name is Jo Bloggs",
              result_b["deal"]["primary_admin_name"] == "Jo Bloggs", result_b["deal"].get("primary_admin_name"))
        check("Club B: min_trial_days_remaining is negative (expired)",
              result_b["deal"]["min_trial_days_remaining"] is not None
              and result_b["deal"]["min_trial_days_remaining"] < 0)

        result_c = await get_club(str(deals["c"].id), actor=actor, db=db)
        check("Club C (onboarded, not trialing): primary_admin_name is None",
              result_c["deal"]["primary_admin_name"] is None, result_c["deal"].get("primary_admin_name"))
        check("Club C: min_trial_days_remaining is None (nothing to show)",
              result_c["deal"]["min_trial_days_remaining"] is None)

        result_d = await get_club(str(deals["d"].id), actor=actor, db=db)
        check("Club D (bare prospect): primary_admin_name is None, no error",
              result_d["deal"]["primary_admin_name"] is None)

    await engine.dispose()

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED: {FAILS}")
        sys.exit(1)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
