"""Verifies the subject-line fixes: no em dash in voicemail_followup /
trial_information / demo subjects (seeded row AND the hardcoded fallback
builder), and 'custom' now has a real subject 'BetterCricket for {{club}}'
(was empty in the seed, an em dash in the fallback). Run with:

    DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost/bstest \
    python -m scripts.verify_sales_workspace_round14
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

from app.models.db import Base, Organisation
from app.services import sales_email as se

FAILS = []


def check(name, cond, detail=""):
    status = "OK" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


async def main():
    # ── Pure: _SEED_SUBJECT + hardcoded fallback have no em dash ────────
    for key in ("voicemail_followup", "trial_information", "demo"):
        check(f"_SEED_SUBJECT[{key!r}] has no em dash", "—" not in se._SEED_SUBJECT[key], se._SEED_SUBJECT[key])
        check(f"_SEED_SUBJECT[{key!r}] has a hyphen instead", "-" in se._SEED_SUBJECT[key], se._SEED_SUBJECT[key])
    check("_SEED_SUBJECT['custom'] is no longer blank", se._SEED_SUBJECT["custom"] == "BetterCricket for {{club}}")

    subj_vm, _, _ = se._render_template_hardcoded("voicemail_followup", contact_name="Pat", club_name="Test CC", rep_name="Sam")
    check("hardcoded voicemail_followup subject has no em dash", "—" not in subj_vm, subj_vm)
    subj_ti, _, _ = se._render_template_hardcoded("trial_information", contact_name="Pat", club_name="Test CC", rep_name="Sam")
    check("hardcoded trial_information subject has no em dash", "—" not in subj_ti, subj_ti)
    subj_demo, _, _ = se._render_template_hardcoded("demo", contact_name="Pat", club_name="Test CC", rep_name="Sam")
    check("hardcoded demo subject has no em dash", "—" not in subj_demo, subj_demo)
    subj_custom, _, _ = se._render_template_hardcoded("custom", contact_name="Pat", club_name="Test CC", rep_name="Sam")
    check("hardcoded custom subject is 'BetterCricket for Test CC'", subj_custom == "BetterCricket for Test CC", subj_custom)

    # ── Real Postgres: seeded row content matches ────────────────────────
    engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        outreach = Organisation(id=uuid.uuid4(), name="BetterCricket Outreach", slug="outreach",
                                 is_marketing_outreach=True)
        db.add(outreach)
        await db.commit()
        await se.seed_sales_templates(db)
        await db.commit()

        subject, html, text = await se.render_template(
            db, "voicemail_followup", contact_name="Pat", club_name="Real Rovers CC", rep_name="Sam",
        )
        check("rendered voicemail_followup subject has no em dash", "—" not in subject, subject)
        subject2, _, _ = await se.render_template(
            db, "trial_information", contact_name="Pat", club_name="Real Rovers CC", rep_name="Sam",
        )
        check("rendered trial_information subject has no em dash", "—" not in subject2, subject2)
        subject3, _, _ = await se.render_template(
            db, "demo", contact_name="Pat", club_name="Real Rovers CC", rep_name="Sam",
        )
        check("rendered demo subject has no em dash", "—" not in subject3, subject3)
        subject4, _, _ = await se.render_template(
            db, "custom", contact_name="Pat", club_name="Real Rovers CC", rep_name="Sam",
        )
        check("rendered custom subject is 'BetterCricket for Real Rovers CC'",
              subject4 == "BetterCricket for Real Rovers CC", subject4)

    await engine.dispose()

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED: {FAILS}")
        sys.exit(1)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
