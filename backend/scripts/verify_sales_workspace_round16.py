"""Verifies that the drawer's History feed no longer draws the reassignment
audit rows, and that everything else on the timeline is untouched — including
the other 'system' entries, which are real events and must still show. Run
with:

    DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost/bstest \
    python -m scripts.verify_sales_workspace_round16
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

from app.models.db import Base, CrmActivity, CrmDeal, CrmStage, MarketingClub
from app.services import crm as crm_service
from app.services import sales_workspace as sw

FAILS = []


def check(name, cond, detail=""):
    status = "OK" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


class _Fake:
    """Just enough of a CrmActivity for the pure predicate."""
    def __init__(self, type, body, meta=None):
        self.type, self.body, self.meta = type, body, meta


async def main():
    # ── Pure: the predicate catches reassignments and nothing else ───────
    check("catches the stamped meta kind",
          sw._is_reassignment(_Fake("system", "anything", {"kind": "reassignment"})))
    check("catches a pre-stamp 'Reassigned to <name>' row",
          sw._is_reassignment(_Fake("system", "Reassigned to Sam Barker")))
    check("catches a pre-stamp 'Unassigned' row",
          sw._is_reassignment(_Fake("system", "Unassigned")))
    check("tolerates surrounding whitespace",
          sw._is_reassignment(_Fake("system", "  Reassigned to Sam  ")))
    check("a NULL meta does not blow up", sw._is_reassignment(_Fake("system", "Unassigned", None)))

    # Every OTHER system body in the codebase must survive.
    survivors = [
        "Trial started for Rovers CC by Sam",
        "Extended trial by 14 day(s) to 2026-09-04 for pat@rovers.test",
        "Auto-promoted to Engaged: engagement score 71 (rule: engagement_score)",
        "Auto-added to pipeline (Target): engagement score 55",
        "Auto-removed from pipeline: engagement score 12 is below the 20 needed to stay on the board.",
        "Reset to Target: the engagement-score auto-promotion rule was retired "
        "(Engaged is now for real conversations only).",
        "Started the self-serve trial wizard, club_prepared (pat@rovers.test)",
    ]
    for body in survivors:
        check(f"kept: {body[:46]!r}", not sw._is_reassignment(_Fake("system", body)))
    check("a rep's own note quoting the wording is kept (not a system row)",
          not sw._is_reassignment(_Fake("note", "Reassigned to Sam, per our chat")))
    check("a call is kept", not sw._is_reassignment(_Fake("call", "Reassigned to Sam")))
    check("a Twenty-imported row is still caught by its own predicate",
          sw._is_twenty_imported(_Fake("system", "Imported from Twenty", {"twenty_kind": "x"})))

    # ── Real Postgres: through the shipped writer and reader ─────────────
    engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        # The real platform pipeline + its seeded stages, so the deal below
        # sits where an actual Sales Workspace deal sits.
        pipeline = await crm_service.ensure_platform_pipeline(db)
        await db.commit()
        stage = (await db.execute(
            select(CrmStage).where(CrmStage.pipeline_id == pipeline.id)
            .order_by(CrmStage.position).limit(1))).scalar_one()
        club = MarketingClub(id=uuid.uuid4(), name="Rovers CC",
                             grassroots_guid=f"manual:{uuid.uuid4()}")
        db.add(club)
        await db.flush()
        deal = CrmDeal(id=uuid.uuid4(), pipeline_id=pipeline.id, marketing_club_id=club.id,
                       stage_id=stage.id, scope="platform", title="Rovers CC")
        db.add(deal)
        await db.commit()

        # A pre-stamp reassignment, exactly as it sits in an existing db.
        await crm_service.log_activity(db, deal_id=deal.id, type="system",
                                       body="Reassigned to Old Rep")
        await crm_service.log_activity(db, deal_id=deal.id, type="system", body="Unassigned")
        # A Twenty import, already hidden before this change.
        await crm_service.log_activity(db, deal_id=deal.id, type="system",
                                       body="Imported from Twenty (board): stage=Target",
                                       meta={"twenty_kind": "import"})
        # The rows a rep must still see.
        await crm_service.log_activity(db, deal_id=deal.id, type="call", body="Spoke to Pat")
        await sw.log_note(db, deal=deal, body="Keen on BetterSelect", pinned=False,
                          created_by_user_id=None)
        await crm_service.log_activity(db, deal_id=deal.id, type="system",
                                       body="Trial started for Rovers CC by Sam")
        await db.commit()

        # The shipped writer, which stamps the meta kind.
        await sw.log_reassignment(db, deal=deal, owner_name="New Rep", created_by_user_id=None)
        await sw.log_reassignment(db, deal=deal, owner_name=None, created_by_user_id=None)
        await db.commit()

        stamped = (await db.execute(select(CrmActivity).where(
            CrmActivity.deal_id == deal.id, CrmActivity.body == "Reassigned to New Rep"))).scalar_one()
        check("log_reassignment stamps meta.kind", (stamped.meta or {}).get("kind") == "reassignment",
              str(stamped.meta))
        check("log_reassignment still writes the same body", stamped.body == "Reassigned to New Rep")

        all_rows = (await db.execute(select(CrmActivity).where(
            CrmActivity.deal_id == deal.id))).scalars().all()
        check("all 8 rows are still stored. Nothing was deleted", len(all_rows) == 8, str(len(all_rows)))

        shown = await sw.list_activities_for_workspace(db, deal_id=deal.id)
        bodies = [a.body for a in shown]
        check("the History feed drops all four reassignment rows", len(shown) == 3, str(bodies))
        check("no 'Reassigned to' row is drawn",
              not any((b or "").startswith("Reassigned to") for b in bodies), str(bodies))
        check("no 'Unassigned' row is drawn", "Unassigned" not in bodies, str(bodies))
        check("the Twenty import is still hidden",
              not any("Imported from Twenty" in (b or "") for b in bodies), str(bodies))
        check("the call is still drawn", "Spoke to Pat" in bodies, str(bodies))
        check("the note is still drawn", "Keen on BetterSelect" in bodies, str(bodies))
        check("the trial-started system row is still drawn",
              "Trial started for Rovers CC by Sam" in bodies, str(bodies))

        # The CRM Pipeline board reads the unfiltered list, by design.
        every = await crm_service.list_activities(db, deal_id=deal.id)
        check("crm_service.list_activities still returns everything (Pipeline board unchanged)",
              len(every) == 8, str(len(every)))

    await engine.dispose()

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED: {FAILS}")
        sys.exit(1)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
