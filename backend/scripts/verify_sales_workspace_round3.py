"""Verifies the Sales Workspace's State filter, contact-name search, and
Sort (recent/club name/engagement score/trial days) against a real local
Postgres instance. Run with:

    DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost/bstest \
    python -m scripts.verify_sales_workspace_round3
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

from app.models.db import (
    Base, User, Organisation, ClubMembership, MarketingClub, MarketingClubContact,
    OrgModuleSubscription,
)
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
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        rep = User(id=uuid.uuid4(), username="sam", display_name="Sam", email="sam@bettersports.com.au",
                   password_hash="x")
        db.add(rep)
        await db.flush()

        pipeline = await crm_service.ensure_platform_pipeline(db)
        await db.commit()
        target_stage = next(s for s in pipeline.stages if s.key == "target")
        trial_stage = next(s for s in pipeline.stages if s.key == "trial")

        def make_club(name, state, existing_org=None):
            c = MarketingClub(id=uuid.uuid4(), name=name, grassroots_guid=f"manual:{uuid.uuid4()}",
                               state=state, existing_org_id=existing_org.id if existing_org else None)
            db.add(c)
            return c

        # Club A: WA, no trial, high engagement, contact "Pat Smith".
        club_a = make_club("Alvie CC", "WA")
        club_a.engagement_score = 90
        club_a.engagement_tier = "HOT"
        # Club B: NSW, currently-trialing (10 days left), lower engagement, contact "Robin Jones".
        org_b = Organisation(id=uuid.uuid4(), name="Rovers Org", slug="rovers-org")
        db.add(org_b)
        await db.flush()
        club_b = make_club("Rovers CC", "NSW", existing_org=org_b)
        club_b.engagement_score = 40
        club_b.engagement_tier = "WARM"
        # Club C: NSW, trial expired 5 days ago.
        org_c = Organisation(id=uuid.uuid4(), name="Colts Org", slug="colts-org")
        db.add(org_c)
        await db.flush()
        club_c = make_club("Colts CC", "NSW", existing_org=org_c)
        club_c.engagement_score = None  # never scored
        await db.flush()

        db.add(MarketingClubContact(marketing_club_id=club_a.id, full_name="Pat Smith", role="Secretary",
                                     role_rank=1, email="pat@example.com", outreach_selected=True))
        db.add(MarketingClubContact(marketing_club_id=club_b.id, full_name="Robin Jones", role="President",
                                     role_rank=1, email="robin@example.com", outreach_selected=True))
        await db.commit()

        now = dt.datetime.now(dt.timezone.utc)
        db.add(OrgModuleSubscription(id=uuid.uuid4(), organisation_id=org_b.id, module_key="select",
                                      status="trial", trial_ends_at=now + dt.timedelta(days=10)))
        db.add(OrgModuleSubscription(id=uuid.uuid4(), organisation_id=org_c.id, module_key="select",
                                      status="trial", trial_ends_at=now - dt.timedelta(days=5)))
        await db.commit()

        deal_a = await crm_service.create_deal(
            db, scope=crm_service.SCOPE_PLATFORM, pipeline_id=pipeline.id, stage_id=target_stage.id,
            title="Alvie CC", marketing_club_id=club_a.id, owner_user_id=rep.id,
        )
        deal_b = await crm_service.create_deal(
            db, scope=crm_service.SCOPE_PLATFORM, pipeline_id=pipeline.id, stage_id=trial_stage.id,
            title="Rovers CC", marketing_club_id=club_b.id, owner_user_id=rep.id,
        )
        deal_c = await crm_service.create_deal(
            db, scope=crm_service.SCOPE_PLATFORM, pipeline_id=pipeline.id, stage_id=trial_stage.id,
            title="Colts CC", marketing_club_id=club_c.id, owner_user_id=rep.id,
        )
        await db.commit()
        # Stagger updated_at so "recent" has something real to sort on —
        # club C touched most recently, then B, then A.
        deal_a.updated_at = now - dt.timedelta(hours=3)
        deal_b.updated_at = now - dt.timedelta(hours=2)
        deal_c.updated_at = now - dt.timedelta(hours=1)
        await db.commit()

        from app.routers.sales_workspace import list_clubs
        from app.routers.auth import SalesActor
        actor = SalesActor(user=rep, role="sales")

        # ── State filter ─────────────────────────────────────────────────
        r = await list_clubs(actor=actor, db=db, states="NSW")
        ids = {c["id"] for c in r["clubs"]}
        check("states=NSW matches only the two NSW clubs",
              ids == {str(deal_b.id), str(deal_c.id)}, str(ids))
        r = await list_clubs(actor=actor, db=db, states="WA,NSW")
        ids = {c["id"] for c in r["clubs"]}
        check("states=WA,NSW (OR) matches all three clubs", ids == {str(deal_a.id), str(deal_b.id), str(deal_c.id)})
        r = await list_clubs(actor=actor, db=db, states="VIC")
        check("states=VIC (no match) returns nothing", len(r["clubs"]) == 0)

        # ── Contact-name search ──────────────────────────────────────────
        r = await list_clubs(actor=actor, db=db, q="pat smith")
        ids = {c["id"] for c in r["clubs"]}
        check("search by contact name finds the club that contact belongs to",
              ids == {str(deal_a.id)}, str(ids))
        r = await list_clubs(actor=actor, db=db, q="robin")
        ids = {c["id"] for c in r["clubs"]}
        check("partial contact-name search still matches", ids == {str(deal_b.id)}, str(ids))
        r = await list_clubs(actor=actor, db=db, q="Rovers")
        ids = {c["id"] for c in r["clubs"]}
        check("search still matches on club name (unchanged behaviour)", ids == {str(deal_b.id)}, str(ids))
        r = await list_clubs(actor=actor, db=db, q="nobody matches this")
        check("search with no match returns nothing", len(r["clubs"]) == 0)

        # ── Sort ──────────────────────────────────────────────────────────
        # No filters narrowing to called/never-called — pull everything via
        # called_clubs + never-called by running twice, or simplest: query
        # each stage's "never called" default separately isn't needed here
        # since none of the three has been called yet, so the default
        # (never-called) queue already contains all three.
        r = await list_clubs(actor=actor, db=db, sort="club_name")
        names = [c["marketing_club_name"] for c in r["clubs"]]
        check("sort=club_name orders A-Z", names == sorted(names), str(names))

        r = await list_clubs(actor=actor, db=db, sort="club_name", sort_dir="desc")
        names_desc = [c["marketing_club_name"] for c in r["clubs"]]
        check("sort=club_name + sort_dir=desc reverses it", names_desc == list(reversed(sorted(names))), str(names_desc))

        r = await list_clubs(actor=actor, db=db, sort="engagement_score")
        scored_ids = [c["id"] for c in r["clubs"]]
        check("sort=engagement_score (desc default) puts the highest score first",
              scored_ids[0] == str(deal_a.id), str(scored_ids))
        check("sort=engagement_score puts the never-scored club last",
              scored_ids[-1] == str(deal_c.id), str(scored_ids))

        r = await list_clubs(actor=actor, db=db, sort="trial_days")
        trial_ids = [c["id"] for c in r["clubs"]]
        trial_vals = [c["min_trial_days_remaining"] for c in r["clubs"]]
        # Ascending default: club C (expired, negative) before club B
        # (current, positive) before club A (no trial data — sorts last).
        check("sort=trial_days (asc default) puts the expired trial before the current one",
              trial_ids.index(str(deal_c.id)) < trial_ids.index(str(deal_b.id)), str(trial_ids))
        check("sort=trial_days puts the club with no trial data last",
              trial_ids[-1] == str(deal_a.id), str(trial_ids))
        check("trial_days for the expired club is negative",
              trial_vals[trial_ids.index(str(deal_c.id))] < 0, str(trial_vals))
        check("trial_days for the current club is positive",
              trial_vals[trial_ids.index(str(deal_b.id))] > 0, str(trial_vals))

        r = await list_clubs(actor=actor, db=db, sort="recent")
        recent_ids = [c["id"] for c in r["clubs"]]
        check("sort=recent (desc default) puts the most-recently-touched deal first",
              recent_ids[0] == str(deal_c.id), str(recent_ids))

        r = await list_clubs(actor=actor, db=db)  # sort omitted -> priority_score, unaffected
        check("omitting sort keeps the priority_score default working", len(r["clubs"]) == 3)

    await engine.dispose()

    print()
    if FAILS:
        print(f"{len(FAILS)} check(s) FAILED: {FAILS}")
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    asyncio.run(main())
