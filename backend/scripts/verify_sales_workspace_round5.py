"""Verifies the new "Custom sales rep email" built-in template (seeded under
its own DB name, {{utm_code}} merge substitution, UTM-preservation on its
hand-placed links) plus the widened engagement-score fields (frontend-only,
not covered here) against a real local Postgres instance. Run with:

    DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost/bstest \
    python -m scripts.verify_sales_workspace_round5
"""
import asyncio
import os
import sys
import uuid

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/bstest")
os.environ.setdefault("SECRET_KEY", "test-secret")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models.db import (
    Base, User, Organisation, ClubMembership, MarketingClub, MarketingClubContact,
    CommsTemplate,
)
from app.services import crm as crm_service
from app.services import sales_email as se
from app.services.marketing_org import get_outreach_org

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
        outreach = Organisation(id=uuid.uuid4(), name="BetterCricket Outreach", slug="outreach",
                                 is_marketing_outreach=True)
        rep = User(id=uuid.uuid4(), username="sam", display_name="Sam", email="sam@bettersports.com.au",
                   password_hash="x")
        db.add_all([outreach, rep])
        await db.commit()

        # ── seeding ────────────────────────────────────────────────────
        check("'custom' is a BUILT_IN_TEMPLATES key now", "custom" in se.BUILT_IN_TEMPLATES)
        seeded = await se.seed_sales_templates(db)
        await db.commit()
        check("seed_sales_templates inserted 4 rows (incl. custom)", seeded == 4, str(seeded))
        reseeded = await se.seed_sales_templates(db)
        await db.commit()
        check("seed_sales_templates is idempotent (no dup insert)", reseeded == 0, str(reseeded))

        rows = (await db.execute(
            select(CommsTemplate).where(CommsTemplate.organisation_id == outreach.id)
        )).scalars().all()
        check("4 templates exist in the outreach org", len(rows) == 4, str(len(rows)))
        names = {r.name for r in rows}
        check("dropdown label 'Custom email' is NOT the DB row name",
              "Custom email" not in names, str(names))
        custom_row = next((r for r in rows if r.name == "Custom sales rep email"), None)
        check("'Custom sales rep email' row exists in Comms Templates",
              custom_row is not None, str(names))
        check("TEMPLATE_LABELS still shows 'Custom email' for the dropdown",
              se.TEMPLATE_LABELS["custom"] == "Custom email")

        # ── rendering + merge substitution ────────────────────────────
        subject, html, text = await se.render_template(
            db, "custom", contact_name="Pat Smith", club_name="Test Rovers CC", rep_name="Sam Rep",
            utm_code="test-rovers-cricket-club",
        )
        check("greeting substitutes first name", "Hi Pat," in html, html[:400])
        check("signature substitutes rep_name", "Sam Rep" in html)
        check("utm_code substitutes into the hand-placed links",
              "utm_source=test-rovers-cricket-club" in html, html)
        check("rep_name substitutes into utm_campaign=rep_...",
              "utm_campaign=rep_Sam" in html, html)
        check("no leftover {{ tokens survive in rendered html", "{{" not in html, html)
        check("logo asset path resolves against the base url",
              "/email/bettercricket-logo.png" in html, html)
        check("full HTML doc detected (own <html>/<body>, not re-wrapped)",
              html.strip().lower().startswith("<!doctype html") or "<html" in html.lower())

        # No utm_code supplied at all — the merge token must resolve to an
        # empty string, not literally "{{utm_code}}".
        _, html_no_code, _ = await se.render_template(
            db, "custom", contact_name="Pat Smith", club_name="Test Rovers CC", rep_name="Sam Rep",
        )
        check("blank utm_code still resolves the token (no leftover braces)",
              "{{" not in html_no_code, html_no_code)

        # ── apply_sales_utm interaction: hand-placed values survive, utm_id appended ──
        tagged = se.apply_sales_utm(html, template_key="custom", rep_username="sam", utm_code="club-code-123")
        check("hand-placed utm_source is preserved (not overwritten with 'sales')",
              "utm_source=test-rovers-cricket-club" in tagged and "utm_source=sales" not in tagged, tagged)
        check("hand-placed utm_medium=sales_email is preserved",
              "utm_medium=sales_email" in tagged and "utm_medium=email" not in tagged, tagged)
        check("utm_id is appended from the club's own utm_code",
              "utm_id=club-code-123" in tagged, tagged)

        # ── fallback path: no outreach org configured ─────────────────
        outreach.is_marketing_outreach = False
        await db.commit()
        subject3, html3, text3 = await se.render_template(
            db, "custom", contact_name="Pat Smith", club_name="Test Rovers CC", rep_name="Sam Rep",
        )
        check("fallback custom builder produces a subject with the club name",
              "Test Rovers CC" in subject3, subject3)
        check("fallback custom builder greets by first name", "Hi Pat," in html3, html3)
        outreach.is_marketing_outreach = True
        await db.commit()

        # ── render_custom is gone ───────────────────────────────────
        check("render_custom was deleted (fully dead code)", not hasattr(se, "render_custom"))

        # ── router-level: email_preview + send_email for 'custom' ─────
        pipeline = await crm_service.ensure_platform_pipeline(db)
        target_stage = next(s for s in pipeline.stages if s.key == "target")
        mc = MarketingClub(id=uuid.uuid4(), name="Test Rovers Cricket Club", grassroots_guid=f"manual:{uuid.uuid4()}",
                            state="WA")
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

        from app.routers.sales_workspace import (
            email_preview, EmailPreviewBody, send_email, EmailBody, SalesActor, _resolve_utm_code,
        )

        class FakeActor:
            def __init__(self, user, role):
                self.user = user
                self.role = role

        actor = FakeActor(rep, "sales")
        preview = await email_preview(
            str(deal.id), EmailPreviewBody(template="custom"), actor=actor, db=db,
        )
        check("email_preview returns a non-empty subject for custom", bool(preview["subject"]))
        check("email_preview body has no leftover {{ tokens", "{{" not in preview["body"], preview["body"])
        check("email_preview substituted utm_code into the links",
              "utm_source=test-rovers-cricket-club" in preview["body"], preview["body"])

        result = await send_email(
            str(deal.id),
            EmailBody(directory_contact_id=str(contact.id), template="custom",
                      subject=preview["subject"], body=preview["body"]),
            actor=actor, db=db,
        )
        check("send_email (custom, pre-filled+edited body) returns sent", result == {"status": "sent"})

        club_after = await db.get(MarketingClub, mc.id)
        check("utm_code was minted + persisted on the club", club_after.utm_code == "test-rovers-cricket-club",
              club_after.utm_code)

        activity = (await db.execute(
            select(crm_service.CrmActivity).where(crm_service.CrmActivity.deal_id == deal.id,
                                                    crm_service.CrmActivity.type == "email")
        )).scalars().first()
        check("activity log uses the dropdown label, not the DB row name",
              activity is not None and "Custom email" in (activity.body or ""), activity.body if activity else None)

        # send_email with NO subject/body supplied (skips the preview step) —
        # should fall back to a fresh server-side render, not error.
        result2 = await send_email(
            str(deal.id),
            EmailBody(directory_contact_id=str(contact.id), template="custom"),
            actor=actor, db=db,
        )
        check("send_email (custom, no pre-filled body) still sends via a fresh render",
              result2 == {"status": "sent"})

        check("_resolve_utm_code returns None for a None club", _resolve_utm_code(None) is None)

    await engine.dispose()

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED: {FAILS}")
        sys.exit(1)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
