"""Verifies the queue card and drawer header both carry marketing_club_suburb
(paired with the existing marketing_club_state) for the "Town, ST" line. Run
with:

    DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost/bstest \
    python -m scripts.verify_sales_workspace_round7
"""
import asyncio
import os
import sys
import uuid

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/bstest")
os.environ.setdefault("SECRET_KEY", "test-secret")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models.db import Base, User, MarketingClub
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
        # Raw-SQL lifespan tables get_club transitively reads via
        # wizard_signal_for_club -> meta_ads.get_selected_clubs. Copied
        # verbatim from verify_sales_workspace_round2/6.py.
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
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        rep = User(id=uuid.uuid4(), username="sam", display_name="Sam", email="sam@bettersports.com.au",
                   password_hash="x")
        db.add(rep)
        await db.flush()

        mc = MarketingClub(id=uuid.uuid4(), name="Geelong Cricket Club", grassroots_guid=f"manual:{uuid.uuid4()}",
                            suburb="Geelong", state="VIC")
        mc_blank = MarketingClub(id=uuid.uuid4(), name="No Address CC", grassroots_guid=f"manual:{uuid.uuid4()}")
        db.add_all([mc, mc_blank])
        await db.flush()

        pipeline = await crm_service.ensure_platform_pipeline(db)
        target_stage = next(s for s in pipeline.stages if s.key == "target")
        deal = await crm_service.create_deal(
            db, scope=crm_service.SCOPE_PLATFORM, pipeline_id=pipeline.id, stage_id=target_stage.id,
            title=mc.name, marketing_club_id=mc.id, owner_user_id=rep.id,
        )
        deal_blank = await crm_service.create_deal(
            db, scope=crm_service.SCOPE_PLATFORM, pipeline_id=pipeline.id, stage_id=target_stage.id,
            title=mc_blank.name, marketing_club_id=mc_blank.id, owner_user_id=rep.id,
        )
        await db.commit()

        from app.routers.sales_workspace import list_clubs, get_club

        class FakeActor:
            def __init__(self, user, role):
                self.user = user
                self.role = role

        actor = FakeActor(rep, "sales")

        # ── queue list ──────────────────────────────────────────────
        listing = await list_clubs(actor=actor, db=db)
        rows = {r["marketing_club_id"]: r for r in listing["clubs"]}
        check("queue row carries marketing_club_suburb",
              rows[str(mc.id)]["marketing_club_suburb"] == "Geelong", rows[str(mc.id)].get("marketing_club_suburb"))
        check("queue row carries marketing_club_state",
              rows[str(mc.id)]["marketing_club_state"] == "VIC", rows[str(mc.id)].get("marketing_club_state"))
        check("queue row with no address -> both None, no error",
              rows[str(mc_blank.id)]["marketing_club_suburb"] is None
              and rows[str(mc_blank.id)]["marketing_club_state"] is None)

        # ── drawer header ───────────────────────────────────────────
        drawer = await get_club(str(deal.id), actor=actor, db=db)
        check("drawer deal carries marketing_club_suburb",
              drawer["deal"]["marketing_club_suburb"] == "Geelong", drawer["deal"].get("marketing_club_suburb"))
        check("drawer deal carries marketing_club_state (pre-existing field)",
              drawer["deal"]["marketing_club_state"] == "VIC")

        drawer_blank = await get_club(str(deal_blank.id), actor=actor, db=db)
        check("drawer with no address -> suburb/state both None, no error",
              drawer_blank["deal"]["marketing_club_suburb"] is None
              and drawer_blank["deal"]["marketing_club_state"] is None)

    await engine.dispose()

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED: {FAILS}")
        sys.exit(1)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
