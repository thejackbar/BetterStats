"""Verifies the Sales Workspace drawer now carries a club's map data
(latitude/longitude/postcode + a preloaded suburb boundary) so a 'sales'
role rep — who can't reach the Club Directory's super-admin-only /boundary
endpoint — still gets it embedded in GET /clubs/{deal_id}. Run with:

    DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost/bstest \
    python -m scripts.verify_sales_workspace_round6
"""
import asyncio
import os
import sys
import uuid
from decimal import Decimal

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
        # platform_settings/usage_events are raw-SQL, lifespan-created tables
        # (not ORM mapped) — get_club's wizard_signal_for_club transitively
        # reads both, so they must exist even for this ORM-only harness.
        # Copied verbatim from verify_sales_workspace_round2.py.
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

        mc = MarketingClub(
            id=uuid.uuid4(), name="Test Rovers Cricket Club", grassroots_guid=f"manual:{uuid.uuid4()}",
            state="WA", postcode="6000", latitude=Decimal("-31.953500"), longitude=Decimal("115.857100"),
            # Pre-set so get_or_fetch_boundary short-circuits (no live Nominatim call).
            boundary_geojson={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
        )
        db.add(mc)
        await db.flush()

        pipeline = await crm_service.ensure_platform_pipeline(db)
        target_stage = next(s for s in pipeline.stages if s.key == "target")
        deal = await crm_service.create_deal(
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
        result = await get_club(str(deal.id), actor=actor, db=db)

        check("get_club succeeds for a 'sales' actor (no 403)", result is not None)
        d = result["deal"]
        check("marketing_club_latitude is a float, correct value",
              isinstance(d["marketing_club_latitude"], float) and abs(d["marketing_club_latitude"] - (-31.9535)) < 1e-4,
              str(d["marketing_club_latitude"]))
        check("marketing_club_longitude is a float, correct value",
              isinstance(d["marketing_club_longitude"], float) and abs(d["marketing_club_longitude"] - 115.8571) < 1e-4,
              str(d["marketing_club_longitude"]))
        check("marketing_club_postcode carried through", d["marketing_club_postcode"] == "6000", d["marketing_club_postcode"])
        check("marketing_club_state carried through (existing field)", d["marketing_club_state"] == "WA")
        check("boundary is embedded in the drawer payload for a 'sales' actor",
              result["boundary"] == {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
              str(result["boundary"]))

        # A club with no coordinates/boundary at all — must not error, both come back None.
        mc2 = MarketingClub(id=uuid.uuid4(), name="No Location CC", grassroots_guid=f"manual:{uuid.uuid4()}", state="WA")
        db.add(mc2)
        await db.flush()
        deal2 = await crm_service.create_deal(
            db, scope=crm_service.SCOPE_PLATFORM, pipeline_id=pipeline.id, stage_id=target_stage.id,
            title=mc2.name, marketing_club_id=mc2.id, owner_user_id=rep.id,
        )
        await db.commit()
        result2 = await get_club(str(deal2.id), actor=actor, db=db)
        d2 = result2["deal"]
        check("no lat/lng -> None, not an error", d2["marketing_club_latitude"] is None and d2["marketing_club_longitude"] is None)
        check("no boundary set -> None (short-circuits without a live fetch)", result2["boundary"] is None,
              str(result2["boundary"]))

        # A deal with no marketing_club_id at all (a bare club-scope tracker) —
        # must not error either.
        deal3 = await crm_service.create_deal(
            db, scope=crm_service.SCOPE_PLATFORM, pipeline_id=pipeline.id, stage_id=target_stage.id,
            title="No club linked", owner_user_id=rep.id,
        )
        await db.commit()
        result3 = await get_club(str(deal3.id), actor=actor, db=db)
        d3 = result3["deal"]
        check("deal with no marketing_club_id -> lat/lng/postcode all None, no error",
              d3["marketing_club_latitude"] is None and d3["marketing_club_longitude"] is None
              and d3["marketing_club_postcode"] is None)
        check("deal with no marketing_club_id -> boundary None, no error", result3["boundary"] is None)

    await engine.dispose()

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED: {FAILS}")
        sys.exit(1)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
