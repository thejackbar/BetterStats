"""A note typed in the Sales Workspace must be visible on the CRM deal card,
against a real Postgres.

Exercises the SHIPPED route bodies (routers/crm.py::club_list_activities /
super_list_activities / super_log_activity) and the SHIPPED writers
(services/sales_workspace.py::log_note / edit_note / log_call /
log_reassignment) — never a re-implementation of their logic — the way the
rest of this repo's verification suites do.

The reported case is the first thing it replays: a rep types a note in the
Sales Workspace and goes looking for it on the CRM deal card.

Run:  DATABASE_URL=postgresql+asyncpg://postgres@127.0.0.1:5432/bstest \
      .venv/bin/python verify_note_visibility.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import app.models.db as m
import app.routers.crm as crm_router
from app.services import crm as crm_service
from app.services import sales_workspace as sw

URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://postgres@127.0.0.1:55432/harness")

CHECKS = []
def check(name, cond, detail=""):
    CHECKS.append((name, bool(cond), detail))
    print(("  PASS  " if cond else "  FAIL  ") + name + (f"   [{detail}]" if detail else ""))


def by_body(payload, body):
    return next((a for a in payload["activities"] if a["body"] == body), None)


async def main():
    engine = create_async_engine(URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(m.Base.metadata.create_all, checkfirst=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        rep = m.User(id=uuid.uuid4(), username="rep1", display_name="Sam Rep", password_hash="x")
        other = m.User(id=uuid.uuid4(), username="rep2", display_name=None, password_hash="x")
        db.add_all([rep, other])
        club_org = m.Organisation(id=uuid.uuid4(), name="Applecross CC", slug=f"acc-{uuid.uuid4().hex[:6]}")
        db.add(club_org)
        await db.flush()

        # A platform pipeline (Sales Workspace / Sales Pipeline board) and a
        # club-scope pipeline (the club's own BetterCRM tracker).
        pipes = {}
        for scope, org in ((crm_service.SCOPE_PLATFORM, None), (crm_service.SCOPE_CLUB, club_org.id)):
            p = m.CrmPipeline(id=uuid.uuid4(), scope=scope, organisation_id=org,
                              name=f"{scope} pipeline", is_default=True)
            db.add(p); await db.flush()
            st = m.CrmStage(id=uuid.uuid4(), pipeline_id=p.id, key="target", name="Target",
                            position=0, default_probability=10)
            db.add(st); await db.flush()
            pipes[scope] = (p, st)

        p, st = pipes[crm_service.SCOPE_PLATFORM]
        deal = m.CrmDeal(id=uuid.uuid4(), scope=crm_service.SCOPE_PLATFORM, organisation_id=None,
                         pipeline_id=p.id, stage_id=st.id, title="Applecross CC", owner_user_id=rep.id)
        cp, cst = pipes[crm_service.SCOPE_CLUB]
        club_deal = m.CrmDeal(id=uuid.uuid4(), scope=crm_service.SCOPE_CLUB, organisation_id=club_org.id,
                              pipeline_id=cp.id, stage_id=cst.id, title="Jersey sponsor")
        db.add_all([deal, club_deal])
        await db.commit()

        print("\n── The reported case: a note typed in the Sales Workspace ──")
        await sw.log_note(db, deal=deal, body="Secretary prefers mobile after 5pm",
                          pinned=False, created_by_user_id=rep.id)
        await sw.log_note(db, deal=deal, body="Committee meets\nfirst Tuesday",
                          pinned=True, created_by_user_id=rep.id)
        await db.commit()

        card = await crm_router.super_list_activities(str(deal.id), db=db)
        plain = by_body(card, "Secretary prefers mobile after 5pm")
        pinned = by_body(card, "Committee meets\nfirst Tuesday")
        check("the plain note is on the CRM deal card", plain is not None)
        check("the pinned note is on the CRM deal card", pinned is not None)
        check("it is filed as a note, not a call", plain and plain["type"] == "note",
              plain and plain["type"])
        check("the pin the rep set in the workspace survives onto the card",
              pinned and pinned["meta"].get("pinned") is True, pinned and pinned["meta"])
        check("the card can say who wrote it", plain and plain["created_by_name"] == "Sam Rep",
              plain and plain["created_by_name"])
        check("the note's own line breaks are preserved",
              pinned and "\n" in pinned["body"], repr(pinned and pinned["body"]))

        print("\n── The note must survive the noise the card also shows ──")
        # The card is deliberately the shows-everything surface: the Twenty
        # backfill and the reassignment audit rows the workspace drawer hides
        # are on it too. The note has to still be findable among them.
        await sw.log_reassignment(db, deal=deal, owner_name="Sam Rep", created_by_user_id=rep.id)
        for i in range(30):
            await crm_service.log_activity(db, deal_id=deal.id, type="system",
                                           body=f"Twenty import row {i}",
                                           meta={sw._TWENTY_IMPORT_META_KEYS[0]: f"t{i}"})
        await db.commit()
        card = await crm_router.super_list_activities(str(deal.id), db=db)
        notes = [a for a in card["activities"] if a["type"] == "note"]
        check("both notes are still returned among 31 audit/import rows", len(notes) == 2,
              f"total={len(card['activities'])} notes={len(notes)}")
        check("the drawer still hides what it always hid",
              len(await sw.list_activities_for_workspace(db, deal_id=deal.id)) == 2)

        print("\n── A call outcome is still a call, not a note ──")
        await sw.log_call(db, deal=deal, person=None, outcome="voicemail",
                          notes="Left a message", next_follow_up_at=None,
                          created_by_user_id=rep.id)
        await db.commit()
        card = await crm_router.super_list_activities(str(deal.id), db=db)
        vm = by_body(card, "Left a message")
        check("a logged call reaches the card as a call", vm and vm["type"] == "call",
              vm and vm["type"])
        check("its outcome rides along so the card can name it",
              vm and vm["outcome"] == "voicemail", vm and vm["outcome"])
        check("a call is not counted among the notes",
              len([a for a in card["activities"] if a["type"] == "note"]) == 2)

        print("\n── A General Note outcome is filed as a note and shows too ──")
        gen = next(iter(sw.GENERAL_OUTCOMES))
        await sw.log_call(db, deal=deal, person=None, outcome=gen,
                          notes="Club folded for the season", next_follow_up_at=None,
                          created_by_user_id=rep.id)
        await db.commit()
        card = await crm_router.super_list_activities(str(deal.id), db=db)
        g = by_body(card, "Club folded for the season")
        check("a General Note reaches the card as a note", g and g["type"] == "note",
              g and g["type"])
        check("it keeps the outcome the rep picked", g and g["outcome"] == gen,
              g and g["outcome"])

        print("\n── An edit in the workspace shows on the card ──")
        act = next(a for a in await crm_service.list_activities(db, deal_id=deal.id)
                   if a.body == "Secretary prefers mobile after 5pm")
        await sw.edit_note(db, activity=act, body="Secretary prefers SMS", pinned=True)
        await db.commit()
        card = await crm_router.super_list_activities(str(deal.id), db=db)
        edited = by_body(card, "Secretary prefers SMS")
        check("the rewritten text is what the card shows", edited is not None)
        check("the old text is gone from the card",
              by_body(card, "Secretary prefers mobile after 5pm") is None)
        check("the card can mark it edited", edited and edited["meta"].get("edited_at"),
              edited and edited["meta"])
        check("pinning it in the workspace pins it on the card",
              edited and edited["meta"].get("pinned") is True)

        print("\n── The other direction: a note added ON the card ──")
        added = await crm_router.super_log_activity(
            str(deal.id), crm_router.ActivityCreate(type="note", body="Rang the president"),
            current_user=rep, db=db)
        check("the card's own composer writes a plain note",
              added["type"] == "note" and added["meta"] is None, added["meta"])
        ws = await sw.list_activities_for_workspace(db, deal_id=deal.id)
        check("and it shows in the Sales Workspace drawer",
              any(a.body == "Rang the president" for a in ws))

        print("\n── The club-scope CRM card gets the same treatment ──")
        await crm_service.log_activity(db, deal_id=club_deal.id, organisation_id=club_org.id,
                                       type="note", body="Sponsor wants a bigger logo",
                                       created_by_user_id=other.id)
        await db.commit()
        club_card = await crm_router.club_list_activities(str(club_deal.id), club=club_org, db=db)
        row = by_body(club_card, "Sponsor wants a bigger logo")
        check("the club CRM card returns its note", row is not None)
        check("it names the author, falling back to the username",
              row and row["created_by_name"] == "rep2", row and row["created_by_name"])
        check("a platform note never leaks onto the club card",
              by_body(club_card, "Secretary prefers SMS") is None)

        print("\n── An author-less row does not break the card ──")
        await crm_service.log_activity(db, deal_id=deal.id, type="system",
                                       body="Auto-advanced on engagement score")
        await db.commit()
        card = await crm_router.super_list_activities(str(deal.id), db=db)
        sysrow = by_body(card, "Auto-advanced on engagement score")
        check("a system row with no actor reports no name",
              sysrow is not None and sysrow["created_by_name"] is None,
              sysrow and sysrow["created_by_name"])
        check("every row carries the created_by_name key",
              all("created_by_name" in a for a in card["activities"]))

    await engine.dispose()
    ok = sum(1 for _, c, _ in CHECKS if c)
    print(f"\n{ok}/{len(CHECKS)} checks passed")
    return 0 if ok == len(CHECKS) else 1

sys.exit(asyncio.run(main()))
