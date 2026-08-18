"""Verifies that a sent email's full content (subject/html/text/recipient)
is now stored on the crm_activities row itself — both the "Send an email"
flow and Extend Trial's own confirmation email — so the Sales Workspace
history can show the actual email that went out, not just a one-line
summary. Run with:

    DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost/bstest \
    python -m scripts.verify_sales_workspace_round13
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/bstest")
os.environ.setdefault("SECRET_KEY", "test-secret")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models.db import (
    Base, MarketingClub, MarketingClubContact, Organisation, OrgModuleSubscription, User,
)
from app.services import crm as crm_service
from app.services import sales_email as se
from app.auth.modules import STATUS_TRIAL

FAILS = []


def check(name, cond, detail=""):
    status = "OK" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


class FakeActor:
    def __init__(self, user, role):
        self.user = user
        self.role = role


async def main():
    engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    from app.routers.sales_workspace import (
        email_preview, EmailPreviewBody, send_email, EmailBody, extend_trial,
        ExtendTrialBody, ExtendTrialContact,
    )
    from fastapi import BackgroundTasks

    async with Session() as db:
        outreach = Organisation(id=uuid.uuid4(), name="BetterCricket Outreach", slug="outreach",
                                 is_marketing_outreach=True)
        rep = User(id=uuid.uuid4(), username="sam", display_name="Sam", email="sam@bettersports.com.au",
                   password_hash="x")
        db.add_all([outreach, rep])
        await db.commit()
        await se.seed_sales_templates(db)
        await db.commit()

        pipeline = await crm_service.ensure_platform_pipeline(db)
        target_stage = next(s for s in pipeline.stages if s.key == "target")
        mc = MarketingClub(id=uuid.uuid4(), name="Test Rovers Cricket Club",
                            grassroots_guid=f"manual:{uuid.uuid4()}", state="WA")
        db.add(mc)
        await db.flush()
        contact = MarketingClubContact(id=uuid.uuid4(), marketing_club_id=mc.id, full_name="Pat Smith",
                                        email="pat@example.com", outreach_selected=True)
        db.add(contact)
        deal = await crm_service.create_deal(
            db, scope=crm_service.SCOPE_PLATFORM, pipeline_id=pipeline.id, stage_id=target_stage.id,
            title=mc.name, marketing_club_id=mc.id, owner_user_id=rep.id,
        )
        await db.commit()

        actor = FakeActor(rep, "sales")

        # ── "Send an email" flow ─────────────────────────────────────────
        preview = await email_preview(str(deal.id), EmailPreviewBody(template="information"), actor=actor, db=db)
        await send_email(
            str(deal.id),
            EmailBody(directory_contact_id=str(contact.id), template="information",
                      subject=preview["subject"], body=preview["body"]),
            actor=actor, db=db,
        )
        activity = await db.scalar(
            select(crm_service.CrmActivity).where(
                crm_service.CrmActivity.deal_id == deal.id, crm_service.CrmActivity.type == "email",
            )
        )
        check("send_email logs an activity of type 'email'", activity is not None)
        # Not a byte-for-byte match against preview["body"] — send_email runs
        # the sent html through apply_sales_utm (UTM tags added to links)
        # AFTER the preview was generated, so the stored copy is the
        # UTM-tagged final version actually sent, which is what a rep
        # reviewing history should see.
        check("meta.html holds the actual rendered email content",
              "Test Rovers Cricket Club" in (activity.meta.get("html") or ""), activity.meta.get("html", "")[:200])
        check("meta.html is the UTM-tagged version that was actually sent, not the pre-tag preview",
              activity.meta.get("html") != preview["body"], "expected these to differ")
        check("meta.subject matches what was actually sent", activity.meta.get("subject") == preview["subject"])
        check("meta.to_email records the real recipient", activity.meta.get("to_email") == "pat@example.com")
        check("meta.to_name records the recipient's name", activity.meta.get("to_name") == "Pat Smith")
        check("meta.template still present (unchanged behaviour)", activity.meta.get("template") == "information")

        # ── Extend Trial's confirmation email ────────────────────────────
        org = Organisation(id=uuid.uuid4(), name="Trial Org CC")
        db.add(org)
        await db.flush()
        org_id = org.id
        db.add(OrgModuleSubscription(
            id=uuid.uuid4(), organisation_id=org_id, module_key="core", status=STATUS_TRIAL,
            trial_started_at=datetime.now(timezone.utc) - timedelta(days=1),
            trial_ends_at=datetime.now(timezone.utc) + timedelta(days=5),
        ))
        mc2 = MarketingClub(id=uuid.uuid4(), name="Trial Org CC", grassroots_guid=f"manual:{uuid.uuid4()}",
                             state="WA", existing_org_id=org_id)
        db.add(mc2)
        await db.flush()
        mc2_id = mc2.id
        deal2 = await crm_service.create_deal(
            db, scope=crm_service.SCOPE_PLATFORM, pipeline_id=pipeline.id, stage_id=target_stage.id,
            title=mc2.name, marketing_club_id=mc2_id, owner_user_id=rep.id,
        )
        deal2_id = deal2.id
        await db.commit()
        # extend_trial re-fetches the org itself via db.get(..., options=
        # [selectinload(module_subscriptions)]) — Session.get() skips applying
        # loader options to an object ALREADY in the identity map, and `org`
        # is still sitting there from the db.add() above with the
        # relationship never touched. Expunge it so that db.get() call issues
        # a genuinely fresh, eager-loaded query — what actually happens in
        # production, where a fresh per-request session has never seen this
        # Organisation row before.
        db.expunge(org)

        await extend_trial(
            str(deal2_id), ExtendTrialBody(
                days=7, new_contact=ExtendTrialContact(full_name="Jamie Lee", email="jamie.lee@example.com"),
            ), BackgroundTasks(), actor=actor, db=db,
        )
        trial_activity = await db.scalar(
            select(crm_service.CrmActivity).where(
                crm_service.CrmActivity.deal_id == deal2.id, crm_service.CrmActivity.type == "system",
            )
        )
        check("extend_trial's activity stays type='system' (extension is the headline)",
              trial_activity is not None and trial_activity.type == "system")
        check("extend_trial's activity still carries meta.html for the 'View email' affordance",
              bool(trial_activity.meta.get("html")), str(trial_activity.meta)[:300])
        check("extend_trial's meta.subject is a real rendered subject, not empty",
              bool(trial_activity.meta.get("subject")))
        check("extend_trial's meta.to_email matches the new contact",
              trial_activity.meta.get("to_email") == "jamie.lee@example.com")
        check("extend_trial's meta.email_sent is True (console provider)",
              trial_activity.meta.get("email_sent") is True)

    await engine.dispose()

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED: {FAILS}")
        sys.exit(1)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
