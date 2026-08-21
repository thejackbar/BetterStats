"""Verifies the new "Email following voicemail" sales email template
(voicemail_followup) — ordering, DB name defaulting to its own label (no
TEMPLATE_DB_NAMES override needed), seeding, and rendering. Run with:

    DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost/bstest \
    python -m scripts.verify_sales_workspace_round10
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
from app.services import sales_email as se

FAILS = []


def check(name, cond, detail=""):
    status = "OK" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


async def main():
    # ── Part 1: vocabulary + ordering (pure) ─────────────────────────────
    template_keys = list(se.TEMPLATE_LABELS.keys())
    # Renamed "Email following voicemail - general" in a later release, when
    # the offer-to-extend-trial sibling was added beside it.
    check("voicemail_followup exists, labelled 'Email following voicemail - general'",
          se.TEMPLATE_LABELS.get("voicemail_followup") == "Email following voicemail - general")
    check("voicemail_followup sits immediately after 'information' (Send information)",
          template_keys[template_keys.index("information") + 1] == "voicemail_followup", str(template_keys))
    check("voicemail_followup is in BUILT_IN_TEMPLATES",
          "voicemail_followup" in se.BUILT_IN_TEMPLATES)
    check("DB name for voicemail_followup falls back to its own label (no override needed)",
          se._db_name("voicemail_followup") == "Email following voicemail - general")
    check("no TEMPLATE_DB_NAMES override was added for voicemail_followup",
          "voicemail_followup" not in se.TEMPLATE_DB_NAMES)

    # ── Part 2: seeding + rendering against a real Postgres ──────────────
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
        # 8 keys as of the offer-to-extend-trial release (was 7 at round 10).
        check("seed_sales_templates inserts one row per built-in key",
              seeded == len(se.BUILT_IN_TEMPLATES), str(seeded))

        rows = (await db.execute(
            select(CommsTemplate).where(CommsTemplate.organisation_id == outreach.id)
        )).scalars().all()
        names = {r.name for r in rows}
        check("'Email following voicemail - general' row exists in Comms Templates",
              "Email following voicemail - general" in names, str(names))

        vm_row = next(r for r in rows if r.name == "Email following voicemail - general")
        check("seeded subject mentions following up", "following up" in vm_row.subject.lower(), vm_row.subject)
        check("seeded html preserved the double-brace merge token (no str.format corruption)",
              "{{first_name}}" in vm_row.html, vm_row.html[:300])

        subject, html, text = await se.render_template(
            db, "voicemail_followup", contact_name="Pat Smith", club_name="Test Rovers CC", rep_name="Sam",
        )
        check("renders with club name in subject", "Test Rovers CC" in subject, subject)
        check("renders greeting", "Hi Pat," in html, html[:200])
        check("renders rep signoff", "Sam" in html)
        check("mentions voicemail", "voicemail" in html.lower(), html)
        check("has no leftover {{ tokens", "{{" not in html, html)
        check("links to the plain marketing site (no invented page)", "See BetterCricket" in html, html)

        # Fallback path (no outreach org) — key still renders via the hardcoded builder.
        outreach.is_marketing_outreach = False
        await db.commit()
        subj2, html2, _ = await se.render_template(
            db, "voicemail_followup", contact_name="Pat Smith", club_name="Test Rovers CC", rep_name="Sam",
        )
        check("fallback (no outreach org) still renders", "Test Rovers CC" in subj2 and "Pat" in html2, html2[:200])
        check("fallback mentions voicemail too", "voicemail" in html2.lower(), html2)
        outreach.is_marketing_outreach = True
        await db.commit()

        # Idempotent re-seed — no duplicate row.
        reseeded = await se.seed_sales_templates(db)
        await db.commit()
        check("re-seeding inserts 0 (idempotent)", reseeded == 0, str(reseeded))

    await engine.dispose()

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED: {FAILS}")
        sys.exit(1)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
