"""Verifies the two new call outcomes (wants_to_subscribe, wants_trial_extension)
and the two new email templates (subscribe, trial_extension) — ordering,
seeding under their own Comms Templates names, and rendering. Run with:

    DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost/bstest \
    python -m scripts.verify_sales_workspace_round9
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

from app.models.db import Base, Organisation, CommsTemplate
from app.services import sales_workspace as sw
from app.services import sales_email as se

FAILS = []


def check(name, cond, detail=""):
    status = "OK" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


async def main():
    # ── Part 1: outcome vocabulary + ordering (pure, no DB needed) ──────
    positive_keys = [k for k, v in sw.CALL_OUTCOMES.items() if v["category"] == "positive"]
    check("wants_to_subscribe exists, labelled 'Wants to buy/subscribe now'",
          sw.CALL_OUTCOMES.get("wants_to_subscribe", {}).get("label") == "Wants to buy/subscribe now")
    check("wants_trial_extension exists, labelled 'Wants a trial extension'",
          sw.CALL_OUTCOMES.get("wants_trial_extension", {}).get("label") == "Wants a trial extension")
    check("wants_to_subscribe is the FIRST positive outcome",
          positive_keys[0] == "wants_to_subscribe", str(positive_keys))
    check("wants_to_subscribe sits immediately above 'interested'",
          positive_keys[positive_keys.index("wants_to_subscribe") + 1] == "interested", str(positive_keys))
    idx_trial = positive_keys.index("wants_trial")
    check("wants_trial_extension sits immediately after 'wants_trial'",
          positive_keys[idx_trial + 1] == "wants_trial_extension", str(positive_keys))
    check("wants_trial_extension sits immediately before 'wants_demo'",
          positive_keys[idx_trial + 2] == "wants_demo", str(positive_keys))
    check("both new outcomes are event-worthy", "wants_to_subscribe" in sw._EVENT_WORTHY_OUTCOMES
          and "wants_trial_extension" in sw._EVENT_WORTHY_OUTCOMES)
    check("both new outcomes have a follow-up note template",
          "wants_to_subscribe" in sw._FOLLOW_UP_NOTE_TEMPLATES and "wants_trial_extension" in sw._FOLLOW_UP_NOTE_TEMPLATES)
    check("neither new outcome is assignable-to-staff (self-owned, like wants_trial)",
          "wants_to_subscribe" not in sw._ASSIGNABLE_EVENT_OUTCOMES
          and "wants_trial_extension" not in sw._ASSIGNABLE_EVENT_OUTCOMES)

    grouped = sw.outcome_options()
    positive_group = next(g for g in grouped if g["category"] == "positive")
    grouped_keys = [o["key"] for o in positive_group["options"]]
    check("outcome_options() reflects the same order", grouped_keys == positive_keys, str(grouped_keys))

    # ── Part 2: email template vocabulary + ordering (pure) ─────────────
    template_keys = list(se.TEMPLATE_LABELS.keys())
    check("subscribe template exists, labelled 'Wants to buy/subscribe'",
          se.TEMPLATE_LABELS.get("subscribe") == "Wants to buy/subscribe")
    check("trial_extension template exists, labelled 'Wants a trial extension'",
          se.TEMPLATE_LABELS.get("trial_extension") == "Wants a trial extension")
    check("subscribe sits immediately after 'demo' (Book a demo)",
          template_keys[template_keys.index("demo") + 1] == "subscribe", str(template_keys))
    check("trial_extension sits immediately after 'trial_information' (Trial info)",
          template_keys[template_keys.index("trial_information") + 1] == "trial_extension", str(template_keys))
    check("both new keys are in BUILT_IN_TEMPLATES",
          "subscribe" in se.BUILT_IN_TEMPLATES and "trial_extension" in se.BUILT_IN_TEMPLATES)
    check("DB name for subscribe is 'Sales rep subscribe link'",
          se._db_name("subscribe") == "Sales rep subscribe link")
    check("DB name for trial_extension is 'Sales rep trial extension'",
          se._db_name("trial_extension") == "Sales rep trial extension")
    check("dropdown label for subscribe stays 'Wants to buy/subscribe' (not the DB name)",
          se.TEMPLATE_LABELS["subscribe"] != se._db_name("subscribe"))

    # ── Part 3: seeding + rendering against a real Postgres ─────────────
    engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        outreach = Organisation(id=uuid.uuid4(), name="BetterCricket Outreach", slug="outreach",
                                 is_marketing_outreach=True)
        db.add(outreach)
        await db.commit()

        seeded = await se.seed_sales_templates(db)
        await db.commit()
        check("seed_sales_templates inserted 6 rows (4 original + 2 new)", seeded == 6, str(seeded))

        rows = (await db.execute(
            select(CommsTemplate).where(CommsTemplate.organisation_id == outreach.id)
        )).scalars().all()
        names = {r.name for r in rows}
        check("'Sales rep subscribe link' row exists in Comms Templates", "Sales rep subscribe link" in names, str(names))
        check("'Sales rep trial extension' row exists in Comms Templates", "Sales rep trial extension" in names, str(names))

        subject, html, text = await se.render_template(
            db, "subscribe", contact_name="Pat Smith", club_name="Test Rovers CC", rep_name="Sam",
        )
        check("subscribe renders with club name in subject", "Test Rovers CC" in subject, subject)
        check("subscribe renders greeting", "Hi Pat," in html, html[:200])
        check("subscribe renders rep signoff", "Sam" in html)
        check("subscribe has no leftover {{ tokens", "{{" not in html, html)
        check("subscribe links to /login (no invented /subscribe page)", "/login" in html, html)

        subject2, html2, text2 = await se.render_template(
            db, "trial_extension", contact_name="Pat Smith", club_name="Test Rovers CC", rep_name="Sam",
        )
        check("trial_extension renders with club name in subject", "Test Rovers CC" in subject2, subject2)
        check("trial_extension renders greeting", "Hi Pat," in html2, html2[:200])
        check("trial_extension mentions extending the trial", "extended" in html2.lower(), html2)
        check("trial_extension has no leftover {{ tokens", "{{" not in html2, html2)

        # Fallback path (no outreach org) — both new keys still render.
        outreach.is_marketing_outreach = False
        await db.commit()
        subj3, html3, _ = await se.render_template(
            db, "subscribe", contact_name="Pat Smith", club_name="Test Rovers CC", rep_name="Sam",
        )
        check("subscribe fallback (no outreach org) still renders", "Test Rovers CC" in subj3 and "Pat" in html3, html3[:200])
        subj4, html4, _ = await se.render_template(
            db, "trial_extension", contact_name="Pat Smith", club_name="Test Rovers CC", rep_name="Sam",
        )
        check("trial_extension fallback (no outreach org) still renders", "Test Rovers CC" in subj4 and "Pat" in html4, html4[:200])
        outreach.is_marketing_outreach = True
        await db.commit()

    await engine.dispose()

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED: {FAILS}")
        sys.exit(1)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
