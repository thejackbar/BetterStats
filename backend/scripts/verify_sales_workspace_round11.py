"""Verifies the Call status filter rename + new Voicemail filter, and the
new General -> General Note call outcome. Run with:

    DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost/bstest \
    python -m scripts.verify_sales_workspace_round11
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/bstest")
os.environ.setdefault("SECRET_KEY", "test-secret")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models.db import Base, Organisation, MarketingClub, MarketingClubContact, User
from app.services import crm as crm_service
from app.services import sales_workspace as sw

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
    # ── Part 1: vocabulary + ordering (pure) ─────────────────────────────
    check("general_note exists, labelled 'General Note'",
          sw.CALL_OUTCOMES.get("general_note", {}).get("label") == "General Note")
    check("general_note's category is 'general'",
          sw.CALL_OUTCOMES.get("general_note", {}).get("category") == "general")
    check("'general' is the LAST category in CATEGORY_ORDER (after administrative)",
          sw.CATEGORY_ORDER[-1] == "general" and sw.CATEGORY_ORDER[-2] == "administrative",
          str(sw.CATEGORY_ORDER))
    check("CATEGORY_LABELS['general'] == 'General'", sw.CATEGORY_LABELS.get("general") == "General")
    check("general_note is NOT event-worthy (just a note, no calendar reminder)",
          "general_note" not in sw._EVENT_WORTHY_OUTCOMES)
    check("general_note has no special follow-up note template",
          "general_note" not in sw._FOLLOW_UP_NOTE_TEMPLATES)
    check("general_note is not a lost/do-not-contact outcome",
          "general_note" not in sw._LOST_OUTCOMES and "general_note" not in sw._DO_NOT_CONTACT_OUTCOMES)

    grouped = sw.outcome_options()
    check("outcome_options() ends with the General group", grouped[-1]["category"] == "general")
    check("the General group's only option is General Note",
          [o["key"] for o in grouped[-1]["options"]] == ["general_note"], str(grouped[-1]))

    # ── Part 2: real Postgres — voicemail filter + general_note logging ──
    engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        rep = User(id=uuid.uuid4(), username="sam", display_name="Sam", email="sam@bettersports.com.au",
                   password_hash="x")
        db.add(rep)
        await db.commit()

        pipeline = await crm_service.ensure_platform_pipeline(db)
        target_stage = next(s for s in pipeline.stages if s.key == "target")

        # Three clubs: one never called, one voicemail'd, one with a normal
        # 'no_answer' call (also unsuccessful — proves the filter is
        # outcome-specific, not just "any unsuccessful call").
        clubs = {}
        deals = {}
        for name, outcome in [("Never Called CC", None), ("Voicemail CC", "voicemail"), ("No Answer CC", "no_answer")]:
            mc = MarketingClub(id=uuid.uuid4(), name=name, grassroots_guid=f"manual:{uuid.uuid4()}", state="WA")
            db.add(mc)
            await db.flush()
            deal = await crm_service.create_deal(
                db, scope=crm_service.SCOPE_PLATFORM, pipeline_id=pipeline.id, stage_id=target_stage.id,
                title=mc.name, marketing_club_id=mc.id, owner_user_id=rep.id,
            )
            await db.commit()
            clubs[name] = mc
            deals[name] = deal
            if outcome:
                await sw.log_call(
                    db, deal=deal, person=None, outcome=outcome, notes=None,
                    next_follow_up_at=None, created_by_user_id=rep.id,
                )
                await db.commit()

        from app.routers.sales_workspace import list_clubs

        actor = FakeActor(rep, "sales")

        default_rows = await list_clubs(actor=actor, db=db)
        default_names = {r["marketing_club_name"] for r in default_rows["clubs"]}
        check("default (nothing ticked) shows only the never-called club",
              default_names == {"Never Called CC"}, str(default_names))

        called_rows = await list_clubs(actor=actor, db=db, called_clubs=True)
        called_names = {r["marketing_club_name"] for r in called_rows["clubs"]}
        check("called_clubs=True shows both called clubs (voicemail + no_answer)",
              called_names == {"Voicemail CC", "No Answer CC"}, str(called_names))

        vm_rows = await list_clubs(actor=actor, db=db, voicemail=True)
        vm_names = {r["marketing_club_name"] for r in vm_rows["clubs"]}
        check("voicemail=True shows ONLY the club whose last call outcome was voicemail",
              vm_names == {"Voicemail CC"}, str(vm_names))

        vm_row = vm_rows["clubs"][0]
        check("the voicemail row exposes last_call_outcome == 'voicemail'",
              vm_row["last_call_outcome"] == "voicemail", vm_row.get("last_call_outcome"))

        # callback_due takes precedence over voicemail when both are set —
        # give the voicemail'd club a due follow-up and confirm voicemail=True
        # alone still finds it (last outcome unaffected), but that ticking
        # BOTH flags together defers to callback_due's own narrower set.
        await sw.log_call(
            db, deal=deals["Voicemail CC"], person=None, outcome="voicemail", notes="second voicemail",
            next_follow_up_at=datetime.now(timezone.utc) - timedelta(days=1), created_by_user_id=rep.id,
        )
        await db.commit()

        both_rows = await list_clubs(actor=actor, db=db, voicemail=True, callback_due=True)
        both_names = {r["marketing_club_name"] for r in both_rows["clubs"]}
        check("callback_due takes precedence over voicemail when both flags are set",
              both_names == {"Voicemail CC"}, str(both_names))

        cb_only = await list_clubs(actor=actor, db=db, callback_due=True)
        cb_names = {r["marketing_club_name"] for r in cb_only["clubs"]}
        check("callback_due=True alone finds the same club via its own due-date logic",
              cb_names == {"Voicemail CC"}, str(cb_names))

        # ── general_note: logs fine, doesn't close the deal or fire an event ──
        contact = MarketingClubContact(id=uuid.uuid4(), marketing_club_id=clubs["No Answer CC"].id,
                                        full_name="Pat Smith", email="pat@example.com", outreach_selected=True)
        db.add(contact)
        await db.commit()
        person = await sw.resolve_or_materialize_person(
            db, marketing_club_id=clubs["No Answer CC"].id, directory_contact_id=contact.id,
        )
        await db.commit()

        stage_before = deals["No Answer CC"].stage_id
        activity = await sw.log_call(
            db, deal=deals["No Answer CC"], person=person, outcome="general_note",
            notes="Left a note about the new committee.", next_follow_up_at=None, created_by_user_id=rep.id,
        )
        await db.commit()
        check("general_note logs as a real activity with the right outcome",
              activity.outcome == "general_note")
        check("general_note doesn't close the deal (status still open)",
              deals["No Answer CC"].status == "open")

        events = await crm_service.list_events(db, deal_id=deals["No Answer CC"].id)
        check("general_note creates no calendar event (no next_follow_up_at, not event-worthy)",
              len(events) == 0, str(len(events)))

    await engine.dispose()

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED: {FAILS}")
        sys.exit(1)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
