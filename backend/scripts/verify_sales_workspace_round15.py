"""Verifies the Send an Email template dropdown changes: the two renames
("Wants a trial extension" -> "Confirmation of trial extension",
"Email following voicemail" -> "Email following voicemail - general"), the
new "Email following voicemail - offer to extend trial" entry sitting
immediately after the general one, its seeded content being a clone of
"Send information"'s layout, and the one-time rename of the already-seeded
voicemail row (including the guard that leaves a super admin's own rename
alone). Run with:

    DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost/bstest \
    python -m scripts.verify_sales_workspace_round15
"""
import asyncio
import os
import sys
import uuid

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/bstest")
os.environ.setdefault("SECRET_KEY", "test-secret")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models.db import Base, CommsTemplate, Organisation
from app.services import sales_email as se

NEW_KEY = "voicemail_followup_extend_trial"
NEW_LABEL = "Email following voicemail - offer to extend trial"

FAILS = []


def check(name, cond, detail=""):
    status = "OK" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


async def main():
    # ── Pure: labels, ordering, built-in registration ────────────────────
    keys = list(se.TEMPLATE_LABELS.keys())
    check("trial_extension is now 'Confirmation of trial extension'",
          se.TEMPLATE_LABELS.get("trial_extension") == "Confirmation of trial extension",
          se.TEMPLATE_LABELS.get("trial_extension"))
    check("voicemail_followup is now 'Email following voicemail - general'",
          se.TEMPLATE_LABELS.get("voicemail_followup") == "Email following voicemail - general",
          se.TEMPLATE_LABELS.get("voicemail_followup"))
    check(f"{NEW_KEY} exists, labelled {NEW_LABEL!r}",
          se.TEMPLATE_LABELS.get(NEW_KEY) == NEW_LABEL, se.TEMPLATE_LABELS.get(NEW_KEY))
    check("the new entry sits immediately after the general voicemail one",
          keys[keys.index("voicemail_followup") + 1] == NEW_KEY, str(keys))
    check("every other entry keeps its place",
          keys == ["information", "voicemail_followup", NEW_KEY, "trial_information",
                   "trial_extension", "demo", "subscribe", "custom"], str(keys))
    check("the new key is a built-in template", NEW_KEY in se.BUILT_IN_TEMPLATES)
    check("the new key has a seeded body", NEW_KEY in se._SEED_BODY)
    check("the new key has a seeded subject", NEW_KEY in se._SEED_SUBJECT)
    check("the new key's DB name is its own label (no override)",
          se._db_name(NEW_KEY) == NEW_LABEL and NEW_KEY not in se.TEMPLATE_DB_NAMES)
    check("trial_extension's DB name is untouched by the dropdown rename",
          se._db_name("trial_extension") == "Sales rep trial extension")
    check("no em dash in the new subject", "—" not in se._SEED_SUBJECT[NEW_KEY],
          se._SEED_SUBJECT[NEW_KEY])

    # ── Pure: the new body really is a clone of "Send information" ───────
    info, new = se._SEED_BODY["information"], se._SEED_BODY[NEW_KEY]
    for frag in ('<p>Hi {{first_name}},</p>',
                 'display:inline-block;background:#16C784;color:#fff;',
                 'padding:12px 24px;border-radius:6px;font-weight:bold;',
                 "<p>Regards,<br>{{rep_name}}<br>BetterCricket</p>"):
        check(f"cloned from 'Send information': {frag[:44]!r}", frag in info and frag in new)
    check("the clone points its button at /login, not the marketing site",
          '{base}/login' in new and 'Log in to BetterCricket' in new)
    check("the clone mentions the voicemail", "voicemail" in new)
    check("the clone offers to extend the trial", "extend it" in new and "{{club}}" in new)

    # ── Pure: the hardcoded fallback builder covers the new key ──────────
    subject, html, txt = se._render_template_hardcoded(
        NEW_KEY, contact_name="Pat Smith", club_name="Test Rovers CC", rep_name="Sam")
    check("fallback subject names the club",
          subject == "BetterCricket for Test Rovers CC - more time on your trial", subject)
    check("fallback html greets by first name", "Hi Pat," in html, html[:120])
    check("fallback html carries the login button", "/login" in html)
    check("fallback text is not empty and names the rep", txt.strip().endswith("Sam"))

    # ── Real Postgres: seeding, renaming, rendering ──────────────────────
    engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        outreach = Organisation(id=uuid.uuid4(), name="BetterCricket Outreach",
                                slug=f"outreach-{uuid.uuid4().hex[:8]}", is_marketing_outreach=True)
        db.add(outreach)
        await db.commit()

        # A pre-existing install: the voicemail row already seeded under its
        # OLD name, exactly as migration 261's backfill left it.
        await db.execute(text(
            "INSERT INTO comms_templates (id, organisation_id, name, subject, html, sales_template_key) "
            "VALUES (gen_random_uuid(), :o, 'Email following voicemail', 'x', '<p>old</p>', 'voicemail_followup')"
        ), {"o": outreach.id})
        await db.commit()

        inserted = await se.seed_sales_templates(db)
        await db.commit()
        check("seeding inserts the 7 keys that were missing (the voicemail row already existed)",
              inserted == 7, str(inserted))

        rows = (await db.execute(select(CommsTemplate).where(
            CommsTemplate.organisation_id == outreach.id))).scalars().all()
        by_key = {r.sales_template_key: r for r in rows}
        check("all 8 templates present, one per key", len(rows) == 8 and len(by_key) == 8, str(len(rows)))
        check("the pre-existing voicemail row was renamed, not duplicated",
              by_key["voicemail_followup"].name == "Email following voicemail - general",
              by_key["voicemail_followup"].name)
        check("the renamed row kept its own edited html (content untouched)",
              by_key["voicemail_followup"].html == "<p>old</p>", by_key["voicemail_followup"].html)
        check("the new template row is named for its dropdown entry",
              by_key[NEW_KEY].name == NEW_LABEL, by_key[NEW_KEY].name)
        check("the new row's html was seeded with a real base url (no '{base}' left)",
              "{base}" not in (by_key[NEW_KEY].html or ""))
        check("the new row keeps its merge tokens intact (not collapsed by .format)",
              "{{first_name}}" in by_key[NEW_KEY].html and "{{club}}" in by_key[NEW_KEY].html)
        check("trial_extension's row name is unaffected by the dropdown rename",
              by_key["trial_extension"].name == "Sales rep trial extension",
              by_key["trial_extension"].name)

        # Re-seeding is a no-op, and never renames twice.
        again = await se.seed_sales_templates(db)
        await db.commit()
        check("re-seeding inserts nothing", again == 0, str(again))
        rows2 = (await db.execute(select(CommsTemplate).where(
            CommsTemplate.organisation_id == outreach.id))).scalars().all()
        check("re-seeding mints no duplicate row", len(rows2) == 8, str(len(rows2)))

        # Rendering the new key reads the seeded row, merged.
        subject, html = await se.render_template_preview(
            db, NEW_KEY, contact_name="Pat Smith", club_name="Real Rovers CC", rep_name="Sam")
        check("rendered subject merges the club",
              subject == "BetterCricket for Real Rovers CC - more time on your trial", subject)
        check("rendered html merges first name, club and rep",
              "Hi Pat," in html and "Real Rovers CC" in html and "Sam" in html)
        check("rendered html leaves no unresolved merge token", "{{" not in html)
        check("rendered html carries the login link", "/login" in html)

        # UTM tagging still applies to the new template like any other.
        tagged = se.apply_sales_utm(html, template_key=NEW_KEY, rep_username="sam", utm_code="abc123")
        check("utm_campaign carries the new template key", f"utm_campaign={NEW_KEY}" in tagged)
        check("utm_id carries the club's own code", "utm_id=abc123" in tagged)

    async with Session() as db:
        # A super admin's OWN rename must survive the heal.
        org2 = Organisation(id=uuid.uuid4(), name="Outreach Two",
                            slug=f"outreach-{uuid.uuid4().hex[:8]}", is_marketing_outreach=False)
        db.add(org2)
        await db.commit()
        # Point the outreach org at a fresh row named by the super admin.
        await db.execute(text(
            "UPDATE comms_templates SET name = 'Our own voicemail wording' "
            "WHERE sales_template_key = 'voicemail_followup'"))
        await db.commit()
        await se.seed_sales_templates(db)
        await db.commit()
        kept = await db.scalar(text(
            "SELECT name FROM comms_templates WHERE sales_template_key = 'voicemail_followup'"))
        check("a super admin's own rename is left alone by the heal",
              kept == "Our own voicemail wording", str(kept))

    await engine.dispose()

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED: {FAILS}")
        sys.exit(1)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
