"""Verifies the five-part Sales Workspace feature batch (module interest
pills, called/callback filter redesign, module filter, inline contact
creation, and the editable email templates) against a real local Postgres
instance. Run with:

    DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost/bstest \
    python -m scripts.verify_sales_workspace_round2
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

from app.models.db import (
    Base, User, Organisation, ClubMembership, MarketingClub, MarketingClubContact,
    CrmPipeline, CrmStage, CrmDeal, CommsTemplate,
)
from app.services import crm as crm_service
from app.services import sales_workspace as sw
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
        # platform_settings is a raw-SQL, lifespan-created table (not ORM
        # mapped) — get_club's wizard_signal_for_club reads it transitively
        # via meta_ads.get_selected_clubs, so it must exist even for this
        # ORM-only verification harness.
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
        # usage_events is likewise raw-SQL/lifespan-only — get_club's wizard
        # signal + website-visits panel both transitively scan it. Full real
        # shape (base CREATE + every later ALTER main.py's lifespan applies),
        # not a hand-picked subset — a partial table silently aborts whatever
        # query hits the missing column, which poisons the rest of that DB
        # transaction for every check after it.
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
        # ── Fixtures ──────────────────────────────────────────────────────
        outreach = Organisation(id=uuid.uuid4(), name="BetterCricket Outreach", slug="outreach",
                                 is_marketing_outreach=True)
        club_org = Organisation(id=uuid.uuid4(), name="Test Rovers CC", slug="test-rovers")
        rep = User(id=uuid.uuid4(), username="sam", display_name="Sam", email="sam@bettersports.com.au",
                   password_hash="x")
        db.add_all([outreach, club_org, rep])
        await db.flush()
        db.add(ClubMembership(user_id=rep.id, club_id=club_org.id, role="sales"))
        await db.commit()

        mc = MarketingClub(id=uuid.uuid4(), name="Test Rovers CC", grassroots_guid=f"manual:{uuid.uuid4()}")
        db.add(mc)
        await db.flush()
        db.add(MarketingClubContact(marketing_club_id=mc.id, full_name="Pat Smith", role="Secretary",
                                     role_rank=1, email="pat@example.com", mobile="0400111222",
                                     outreach_selected=True))
        await db.commit()

        pipeline = await crm_service.ensure_platform_pipeline(db)
        await db.commit()
        target_stage = next(s for s in pipeline.stages if s.key == "target")
        deal = await crm_service.create_deal(
            db, scope=crm_service.SCOPE_PLATFORM, pipeline_id=pipeline.id, stage_id=target_stage.id,
            title="Test Rovers CC", marketing_club_id=mc.id, owner_user_id=rep.id,
        )
        await db.commit()
        deal_id = deal.id

        # ── Part A: module interest ─────────────────────────────────────────
        await crm_service.update_deal(db, deal, module_keys=["core", "select"], product_interest_source="manual")
        await db.commit()
        fresh = await db.get(CrmDeal, deal_id)
        await db.refresh(fresh)
        check("module_keys persisted", set(fresh.module_keys or []) == {"core", "select"},
              str(fresh.module_keys))
        check("product_interest_source persisted", fresh.product_interest_source == "manual")

        # ── Part B: called/callback filter semantics (service-level) ────────
        # No calls yet — a never-called deal.
        last_calls = await sw.last_calls_by_deal(db, [deal_id])
        check("no calls logged yet", deal_id not in last_calls)

        await sw.log_call(
            db, deal=fresh, person=None, outcome="spoke_no_decision", notes="chatted",
            next_follow_up_at=None, created_by_user_id=rep.id,
        )
        await db.commit()
        last_calls = await sw.last_calls_by_deal(db, [deal_id])
        check("call now logged (ever_called)", deal_id in last_calls)

        import datetime as _dt
        past = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=1)
        await sw.log_call(
            db, deal=fresh, person=None, outcome="asked_callback", notes="ring back",
            next_follow_up_at=past, created_by_user_id=rep.id,
        )
        await db.commit()
        follow_ups = await sw.next_follow_ups_by_deal(db, [deal_id])
        due_at = follow_ups.get(deal_id)
        check("overdue follow-up recorded", due_at is not None and due_at <= _dt.datetime.now(_dt.timezone.utc))

        # ── Part C: module filter (OR) — plain-Python mirror of the router's
        # deals-list filter, since that logic lives inline in list_clubs.
        wanted = {"select", "socials"}
        matches = bool(wanted & set(fresh.module_keys or []))
        check("module OR filter matches a deal holding one of the wanted keys", matches)
        wanted2 = {"admin", "iq"}
        matches2 = bool(wanted2 & set(fresh.module_keys or []))
        check("module OR filter excludes a deal holding none of the wanted keys", not matches2)

        # ── Part D: add_directory_contact returns the created row (both with
        # and without an email, since the lookup differs) ───────────────────
        created_email = await sw.add_directory_contact(
            db, marketing_club_id=mc.id, full_name="Jo Bloggs", role=None,
            email="jo@example.com", mobile=None,
        )
        await db.commit()
        check("add_directory_contact (email) returns the row", created_email is not None and created_email.email == "jo@example.com")

        created_mobile = await sw.add_directory_contact(
            db, marketing_club_id=mc.id, full_name="Alex Mobile-Only", role=None,
            email=None, mobile="0400999888",
        )
        await db.commit()
        check("add_directory_contact (mobile-only) returns the row",
              created_mobile is not None and created_mobile.full_name == "Alex Mobile-Only")

        contacts = await sw.merged_contacts(db, mc.id)
        names = {c["full_name"] for c in contacts}
        check("merged_contacts includes both newly-added contacts",
              {"Jo Bloggs", "Alex Mobile-Only"} <= names, str(names))

        # ── Part E: editable email templates ─────────────────────────────
        seeded = await se.seed_sales_templates(db)
        await db.commit()
        check("seed_sales_templates inserted 6 rows", seeded == 6, str(seeded))
        reseeded = await se.seed_sales_templates(db)
        await db.commit()
        check("seed_sales_templates is idempotent (no dup insert)", reseeded == 0, str(reseeded))

        org = await get_outreach_org(db)
        check("outreach org resolves", org is not None and org.id == outreach.id)

        rows = (await db.execute(
            __import__("sqlalchemy").select(CommsTemplate).where(CommsTemplate.organisation_id == outreach.id)
        )).scalars().all()
        check("6 templates exist in the outreach org", len(rows) == 6, str(len(rows)))
        info_row = next((r for r in rows if r.name == "Send information"), None)
        check("Send information has a subject", info_row is not None and "{{club}}" in (info_row.subject or ""))

        subject, html, text = await se.render_template(
            db, "information", contact_name="Pat Smith", club_name="Test Rovers CC", rep_name="Sam",
        )
        check("rendered subject substitutes club name", subject == "BetterCricket for Test Rovers CC", subject)
        check("rendered body substitutes first name", "Hi Pat," in html, html[:200])
        check("rendered body substitutes club name", "Test Rovers CC" in html)
        check("rendered body carries rep signoff", "Sam" in html and "BetterCricket" in html)
        check("no leftover {{ tokens survive in rendered html", "{{" not in html, html)

        # Editing the outreach org's template must change what render_template
        # returns (proves it's genuinely reading the editable row, not a
        # cached/hardcoded string).
        info_row.subject = "A totally different subject for {{club}}"
        info_row.html = "<p>Hi {{first_name}} — edited copy.</p><p>{{rep_name}}</p>"
        await db.commit()
        subject2, html2, _ = await se.render_template(
            db, "information", contact_name="Pat Smith", club_name="Test Rovers CC", rep_name="Sam",
        )
        check("edited template subject is used", subject2 == "A totally different subject for Test Rovers CC", subject2)
        check("edited template body is used", "edited copy" in html2, html2)

        # demo template's {{booking_block}} — with and without a calendly link
        _, html_no_link, _ = await se.render_template(
            db, "demo", contact_name="Pat Smith", club_name="Test Rovers CC", rep_name="Sam", calendly_url=None,
        )
        check("demo without a link asks them to reply", "lock one in" in html_no_link, html_no_link)
        _, html_with_link, _ = await se.render_template(
            db, "demo", contact_name="Pat Smith", club_name="Test Rovers CC", rep_name="Sam",
            calendly_url="https://calendly.com/sam/demo",
        )
        check("demo with a link renders a Book a time button", "calendly.com/sam/demo" in html_with_link)

        # Fallback path: no outreach org configured.
        outreach.is_marketing_outreach = False
        await db.commit()
        subject3, html3, _ = await se.render_template(
            db, "information", contact_name="Pat Smith", club_name="Test Rovers CC", rep_name="Sam",
        )
        check("falls back to hardcoded builder when no outreach org",
              subject3 == "BetterCricket for Test Rovers CC" and "edited copy" not in html3, html3[:200])
        outreach.is_marketing_outreach = True
        await db.commit()

        # DealUpdate model fix — verified at the pydantic layer directly.
        from app.routers.crm import DealUpdate
        du = DealUpdate(module_keys=["core"], product_interest_source="manual")
        check("DealUpdate carries product_interest_source", du.product_interest_source == "manual")

        # ── Router-level: the real endpoint functions, called directly
        # (bypassing FastAPI's HTTP layer, but exercising the actual route
        # bodies — not a re-implementation of their logic in the test).
        from app.routers.sales_workspace import (
            list_clubs, get_club, set_interest, add_contact, InterestBody, ContactBody,
        )
        from app.routers.auth import SalesActor
        actor = SalesActor(user=rep, role="sales")

        # A second, genuinely never-called club — so the default/called_clubs/
        # callback_due filters have something real to tell apart.
        mc2 = MarketingClub(id=uuid.uuid4(), name="Second CC", grassroots_guid=f"manual:{uuid.uuid4()}")
        db.add(mc2)
        await db.flush()
        deal2 = await crm_service.create_deal(
            db, scope=crm_service.SCOPE_PLATFORM, pipeline_id=pipeline.id, stage_id=target_stage.id,
            title="Second CC", marketing_club_id=mc2.id, owner_user_id=rep.id,
        )
        await db.commit()

        default_q = await list_clubs(actor=actor, db=db)
        default_ids = {c["id"] for c in default_q["clubs"]}
        check("default (nothing ticked) shows only the never-called club",
              default_ids == {str(deal2.id)}, str(default_ids))

        called_q = await list_clubs(actor=actor, db=db, called_clubs=True)
        called_ids = {c["id"] for c in called_q["clubs"]}
        check("called_clubs=True shows only the called club",
              called_ids == {str(deal_id)}, str(called_ids))

        due_q = await list_clubs(actor=actor, db=db, callback_due=True)
        due_ids = {c["id"] for c in due_q["clubs"]}
        check("callback_due=True shows only the overdue-callback club",
              due_ids == {str(deal_id)}, str(due_ids))
        row = next(c for c in due_q["clubs"] if c["id"] == str(deal_id))
        check("row carries callback_due=True", row.get("callback_due") is True)

        mod_q = await list_clubs(actor=actor, db=db, called_clubs=True, modules="select,socials")
        mod_ids = {c["id"] for c in mod_q["clubs"]}
        check("modules filter (OR) matches the deal holding 'select'", mod_ids == {str(deal_id)}, str(mod_ids))
        mod_q2 = await list_clubs(actor=actor, db=db, called_clubs=True, modules="admin,iq")
        check("modules filter (OR) excludes a deal holding neither key", len(mod_q2["clubs"]) == 0)

        # Part A end-to-end through the real PATCH endpoint.
        result = await set_interest(str(deal_id), InterestBody(module_keys=["core", "admin", "not_a_real_module"]),
                                     actor=actor, db=db)
        check("set_interest strips an unknown module key and keeps valid ones",
              set(result["deal"]["module_keys"]) == {"core", "admin"}, str(result["deal"]["module_keys"]))
        check("set_interest sets product_interest_source=manual",
              result["deal"]["product_interest_source"] == "manual")

        # Part D end-to-end through the real POST endpoint — the router must
        # hand back the created contact, not a bare {"status": "ok"}.
        add_result = await add_contact(
            str(deal_id), ContactBody(full_name="Robin New", email="robin@example.com", mobile=None),
            actor=actor, db=db,
        )
        check("add_contact route returns the created contact",
              add_result.get("contact") is not None and add_result["contact"]["full_name"] == "Robin New")

        # A 'sales' actor can't touch another rep's deal.
        other_rep = User(id=uuid.uuid4(), username="alex", display_name="Alex",
                          email="alex@bettersports.com.au", password_hash="x")
        db.add(other_rep)
        await db.flush()
        db.add(ClubMembership(user_id=other_rep.id, club_id=club_org.id, role="sales"))
        await db.commit()
        other_actor = SalesActor(user=other_rep, role="sales")
        forbidden = False
        try:
            await get_club(str(deal_id), actor=other_actor, db=db)
        except Exception as e:
            forbidden = getattr(e, "status_code", None) == 403
        check("a sales rep can't open another rep's deal (403)", forbidden)

        # Part E router-level: preview a built-in template, edit it, send it —
        # the SEND must use the edited copy, not silently re-render fresh.
        from app.routers.sales_workspace import email_preview, send_email, EmailPreviewBody, EmailBody
        preview = await email_preview(
            str(deal_id), EmailPreviewBody(directory_contact_id=str(created_email.id), template="information"),
            actor=actor, db=db,
        )
        check("email_preview returns a subject and body",
              bool(preview["subject"]) and "Jo" in preview["body"], preview.get("subject"))

        edited_body = preview["body"].replace("Test Rovers CC", "Test Rovers CC (edited by rep)")
        send_result = await send_email(
            str(deal_id),
            EmailBody(directory_contact_id=str(created_email.id), template="information",
                      subject=preview["subject"], body=edited_body),
            actor=actor, db=db,
        )
        check("send_email (built-in template, edited) reports sent", send_result.get("status") == "sent")

        activities = await crm_service.list_activities(db, deal_id=deal_id)
        email_activity = next((a for a in activities if a.type == "email"), None)
        check("an email activity was logged", email_activity is not None)

    await engine.dispose()

    print()
    if FAILS:
        print(f"{len(FAILS)} check(s) FAILED: {FAILS}")
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    asyncio.run(main())
