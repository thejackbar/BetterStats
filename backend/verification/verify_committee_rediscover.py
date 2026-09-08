"""Re-read a club's committee from PlayHQ, and reconcile the Directory to it.

Asked for after the Club Directory was found to be additive-only: a Rediscover
that re-reads what PlayHQ publishes today, prunes the officers it no longer
lists, ticks every listed officer who has an email, and carries the role through
to BetterComms — where a departed officer STAYS, keeping the last role we knew.

This runs the SHIPPED service and route bodies (imported, nothing retyped)
against a real Postgres, with the PlayHQ client stubbed so no request leaves the
box.

    python -m verification.verify_committee_rediscover
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import re
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_URL = os.environ.get(
    "VERIFY_DATABASE_URL",
    "postgresql+asyncpg://postgres@127.0.0.1:5433/verify_committee",
)
# MUST be set before app.models.db is imported — async_session_maker is built at
# import time from settings. The trap the instructional-videos note documents.
os.environ["DATABASE_URL"] = DB_URL

from sqlalchemy import func, select, text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.models.db import (  # noqa: E402
    Base, CommsContact, CrmPerson, MarketingClub, MarketingClubContact, Organisation,
)

PASS: list[str] = []
FAIL: list[str] = []
# The repo root — two levels up from backend/verification, so the structural
# checks below can read both the backend and the frontend sources.
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} — {detail}")
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  ({detail})'}")


def load(path: str) -> str:
    try:
        with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


# ── the payload PlayHQ's search returns for one club ────────────────────────────

def org(guid="guid-apple", name="Applecross Cricket Club", routing="apl",
        contacts="MISSING"):
    """One search result. ``contacts`` left as the sentinel means the key is
    ABSENT (an upstream shape we said nothing about); None means the field came
    back null; a list is what the club publishes."""
    o = {"id": guid, "routingCode": routing, "name": name, "type": "CLUB",
         "tenant": {"name": "Cricket Australia"},
         "address": {"suburb": "Applecross", "state": "WA", "postcode": "6153",
                     "country": "Australia"}}
    if contacts != "MISSING":
        o["contacts"] = contacts
    return o


def person(first, last, position, email=None, phone=None, visible=True):
    return {"firstName": first, "lastName": last, "position": position,
            "email": email, "phone": phone, "visible": visible}


async def main() -> int:
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        # Lifespan-created raw-SQL table the crawl's pause flag lives in —
        # invisible to create_all, copied from main.py column for column.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS marketing_crawl_control (
                id SMALLINT PRIMARY KEY,
                paused BOOLEAN NOT NULL DEFAULT FALSE,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "INSERT INTO marketing_crawl_control (id, paused) VALUES (1, FALSE) "
            "ON CONFLICT (id) DO NOTHING"))
        # Pre-295: the two columns must not exist yet, so the migration has
        # something to do and a populated table to do it to.
        await conn.execute(text(
            "ALTER TABLE marketing_club_contacts DROP COLUMN IF EXISTS former_at"))
        await conn.execute(text("ALTER TABLE comms_contacts DROP COLUMN IF EXISTS role"))

    Session = async_sessionmaker(engine, expire_on_commit=False)

    # ── Migration 295 ───────────────────────────────────────────────────────
    print("\n── Migration 295, on a populated pre-295 table ───────────────────")
    try:
        from app.services.committee_sync_ddl import STATEMENTS as DDL
    except Exception as exc:  # noqa: BLE001
        print(f"\n  the migration's shared DDL module is missing ({exc}) — "
              "reporting rather than crashing.")
        DDL = None
    check("services/committee_sync_ddl.STATEMENTS exists", bool(DDL))
    if not DDL:
        print("\nFEATURE ABSENT — nothing further can be checked.")
        return 1

    # Populate BEFORE the migration, in raw SQL — the ORM model already carries
    # the new columns, so a row inserted through it could not be a pre-295 row.
    async with engine.begin() as conn:
        cid = uuid.uuid4()
        await conn.execute(text(
            "INSERT INTO marketing_clubs (id, name, grassroots_guid, kind, "
            "detail_fetched_at) VALUES (:i, 'Pre CC', 'guid-pre', 'club', NOW())"),
            {"i": cid})
        await conn.execute(text(
            "INSERT INTO marketing_club_contacts (id, marketing_club_id, full_name, "
            "role, role_rank, email, source) "
            "VALUES (gen_random_uuid(), :c, 'Pre Person', 'President', 1, "
            "'pre@example.com', 'api')"), {"c": cid})

    async with engine.begin() as conn:
        for _ in range(3):          # applied three times: it is idempotent
            for stmt in DDL:
                await conn.execute(text(stmt))
        cols = set((await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'marketing_club_contacts'"))).scalars().all())
        ccols = set((await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'comms_contacts'"))).scalars().all())
        idx = (await conn.execute(text(
            "SELECT indexname FROM pg_indexes WHERE tablename = "
            "'marketing_club_contacts' AND indexname = "
            "'ix_marketing_club_contacts_former'"))).scalar()
        kept = (await conn.execute(text(
            "SELECT count(*) FROM marketing_club_contacts"))).scalar()
    check("applied three times: marketing_club_contacts.former_at exists", "former_at" in cols)
    check("applied three times: comms_contacts.role exists", "role" in ccols)
    check("the partial index on former_at exists", idx is not None)
    check("the row that was already there survives", kept == 1, f"{kept}")

    alembic = load("backend/alembic/versions/295_committee_rediscover.py")
    mirror = load("backend/app/main.py")
    check("alembic 295 runs the shared list, not its own copy",
          "from app.services.committee_sync_ddl import STATEMENTS" in alembic)
    check("the lifespan mirror runs the SAME shared list",
          "committee_sync_ddl import STATEMENTS" in mirror)
    check("295 revises 294",
          'down_revision = "294"' in alembic or "down_revision = '294'" in alembic)

    # Imports come AFTER the migration, so the ORM's new columns line up.
    from app.services import club_directory as cd            # noqa: E402
    from app.services import playhq_directory_client as phq  # noqa: E402
    from app.routers.marketing import _contact_out           # noqa: E402

    # ── stub PlayHQ ──────────────────────────────────────────────────────────
    calls = {"search": [], "org_contact": []}
    search_pages: dict = {}          # (query) -> [orgs]
    org_contact_answer = {"value": None}

    async def fake_search(org_type, query="", page=1, limit=100, delay=None):
        calls["search"].append({"query": query, "page": page, "delay": delay})
        if page > 1:
            return [], 0
        rows = search_pages.get(query, search_pages.get("*", []))
        return rows, len(rows)

    async def fake_org_contact(routing_code, delay=None):
        calls["org_contact"].append({"code": routing_code, "delay": delay})
        return org_contact_answer["value"]

    phq.search_organisations = fake_search
    phq.discover_org_contact = fake_org_contact

    async with Session() as db:
        outreach = Organisation(id=uuid.uuid4(), name="BetterCricket",
                                slug="bettercricket", is_marketing_outreach=True)
        db.add(outreach)
        await db.commit()

        async def contacts_of(guid="guid-apple"):
            club = await db.scalar(select(MarketingClub).where(
                MarketingClub.grassroots_guid == guid))
            rows = (await db.execute(select(MarketingClubContact).where(
                MarketingClubContact.marketing_club_id == club.id))).scalars().all()
            for r in rows:
                await db.refresh(r)
            return {(r.email or f"name:{r.full_name}"): r for r in rows}

        # ── the ordinary crawl is still additive ─────────────────────────────
        print("\n── The ordinary crawl stays additive ─────────────────────────")
        payload = org(contacts=[
            person("Ann", "Old", "PRESIDENT", "ann@apple.test"),
            person("Bob", "Stay", "SECRETARY", "bob@apple.test"),
        ])
        await cd._upsert_club(db, payload)
        await db.commit()
        got = await contacts_of()
        check("first pass stores both officers", set(got) == {"ann@apple.test", "bob@apple.test"},
              sorted(got))
        check("an officer with an email is ticked for outreach",
              got["ann@apple.test"].outreach_selected)

        # Ann drops off the payload — with no prune she must survive.
        await cd._upsert_club(db, org(contacts=[person("Bob", "Stay", "SECRETARY", "bob@apple.test")]))
        await db.commit()
        got = await contacts_of()
        check("a crawl with no prune keeps a delisted officer (unchanged behaviour)",
              "ann@apple.test" in got)
        check("...and does not mark her as former", got["ann@apple.test"].former_at is None)

        # ── the tick rule ────────────────────────────────────────────────────
        print("\n── Every listed officer with an email is ticked ──────────────")
        await cd._upsert_club(db, org(contacts=[
            person("Bob", "Stay", "SECRETARY", "bob@apple.test"),
            person("Cara", "Coach", "JUNIOR_CRICKET_COODINATOR", "cara@apple.test"),
            person("Dan", "Phone", "SCORER", None, "0400 000 000"),
        ]))
        await db.commit()
        got = await contacts_of()
        check("a NON-office-bearer with an email is ticked too (was rank<=4 only)",
              got["cara@apple.test"].outreach_selected)
        check("a phone-only contact is stored but not ticked",
              "name:Dan Phone" in got and not got["name:Dan Phone"].outreach_selected)

        # A super admin unticks Cara; an ordinary crawl must leave that alone.
        got["cara@apple.test"].outreach_selected = False
        await db.commit()
        await cd._upsert_club(db, org(contacts=[person("Cara", "Coach", "SCORER", "cara@apple.test")]))
        await db.commit()
        got = await contacts_of()
        check("an ordinary crawl never re-ticks a contact a super admin unticked",
              not got["cara@apple.test"].outreach_selected)
        check("...and leaves the role improve-only (Coordinator beats Scorer)",
              got["cara@apple.test"].role == "Junior Cricket Coordinator",
              got["cara@apple.test"].role)

        # ── the role becomes what PlayHQ says now ────────────────────────────
        print("\n── A Rediscover makes the role what PlayHQ publishes today ────")
        await cd._upsert_club(db, org(contacts=[
            person("Bob", "Stay", "TREASURER", "bob@apple.test"),
            person("Cara", "Coach", "SCORER", "cara@apple.test"),
        ]), prune=True, retick=True)
        await db.commit()
        got = await contacts_of()
        check("a Secretary who is now Treasurer reads as Treasurer",
              got["bob@apple.test"].role == "Treasurer", got["bob@apple.test"].role)
        check("a Coordinator demoted to Scorer reads as Scorer (replace, not improve-only)",
              got["cara@apple.test"].role == "Scorer", got["cara@apple.test"].role)
        check("a rediscover re-ticks a listed officer with an email",
              got["cara@apple.test"].outreach_selected)
        check("the delisted officer is gone", "ann@apple.test" not in got, sorted(got))
        check("the phone-only contact went too (PlayHQ no longer lists them)",
              "name:Dan Phone" not in got)

        # ── one person, two positions, one payload ───────────────────────────
        print("\n── One person listed twice in one payload ────────────────────")
        await cd._upsert_club(db, org(contacts=[
            person("Bob", "Stay", "SCORER", "bob@apple.test"),
            person("Bob", "Stay", "PRESIDENT", "bob@apple.test"),
        ]), prune=True, retick=True)
        await db.commit()
        got = await contacts_of()
        check("the senior of the two roles wins", got["bob@apple.test"].role == "President",
              got["bob@apple.test"].role)
        check("...and it is still ONE row", len(got) == 1, sorted(got))

        # ── what a prune must never delete ───────────────────────────────────
        print("\n── What a prune must never delete ───────────────────────────")
        club = await db.scalar(select(MarketingClub).where(
            MarketingClub.grassroots_guid == "guid-apple"))

        def add(email, name, **kw):
            row = MarketingClubContact(
                id=uuid.uuid4(), marketing_club_id=club.id, full_name=name,
                role="Vice President", role_rank=2, email=email,
                source=kw.pop("source", "api"), outreach_selected=True, **kw)
            db.add(row)
            return row

        unsub = add("unsub@apple.test", "Una Unsub", subscribed=False)
        bounced = add("bounced@apple.test", "Ben Bounce", bounced=True)
        dnc = add("dnc@apple.test", "Dee Nocall", do_not_contact=True)
        noted = add("noted@apple.test", "Ned Note", notes="Rang, call back in March")
        crmed = add("crm@apple.test", "Cam Crm")
        manual = add("manual@apple.test", "Mia Manual", source="manual")
        # A rep typed this into the Sales Workspace drawer BEFORE the source fix:
        # stored source='api', so only its rank tells it apart from a crawled row.
        ws_old = add("ws-old@apple.test", "Wes Old", source="api")
        ws_old.role_rank = cd._HAND_ADDED_RANK
        mailbox = MarketingClubContact(
            id=uuid.uuid4(), marketing_club_id=club.id, full_name=None,
            role="Club contact", role_rank=cd._CLUB_CONTACT_RANK,
            email="club@apple.test", source="api", outreach_selected=True)
        db.add(mailbox)
        plain = add("plain@apple.test", "Pat Plain")
        await db.flush()
        db.add(CrmPerson(id=uuid.uuid4(), organisation_id=outreach.id,
                         full_name="Cam Crm", directory_contact_id=crmed.id))
        await db.commit()

        # And one added through the SHIPPED Workspace path, which must store it
        # as manual so no prune can ever reach it.
        from app.services import sales_workspace as sw   # noqa: PLC0415
        ws_new = await sw.add_directory_contact(
            db, marketing_club_id=club.id, full_name="Wanda New", role="Grants Officer",
            email="ws-new@apple.test", mobile=None)
        await db.commit()
        check("a contact added from the Sales Workspace is stored as manual",
              ws_new is not None and ws_new.source == "manual",
              getattr(ws_new, "source", None))
        check("...at the rank that identifies a hand-added row",
              ws_new is not None and ws_new.role_rank == cd._HAND_ADDED_RANK,
              getattr(ws_new, "role_rank", None))
        check("rank 99 cannot come from a crawl, so it is a safe marker",
              cd._HAND_ADDED_RANK not in
              {cd._role_for_position(p)[1] for p in
               ("PRESIDENT", "VICE_PRESIDENT", "SECRETARY", "TREASURER",
                "JUNIOR_CRICKET_COODINATOR", "SCORER", "", "ANYTHING_ELSE")})

        check("the org mailbox is the only row carrying _CLUB_CONTACT_RANK",
              cd._CLUB_CONTACT_RANK not in
              {cd._role_for_position(p)[1] for p in
               ("PRESIDENT", "VICE_PRESIDENT", "SECRETARY", "TREASURER",
                "JUNIOR_CRICKET_COODINATOR", "SCORER", "", "ANYTHING_ELSE")})

        # PlayHQ now lists Bob alone.
        await cd._upsert_club(db, org(contacts=[
            person("Bob", "Stay", "PRESIDENT", "bob@apple.test")]),
            prune=True, retick=True)
        await db.commit()
        got = await contacts_of()
        check("a plain delisted officer is deleted", "plain@apple.test" not in got)
        for label, email in (("an unsubscribed", "unsub@apple.test"),
                             ("a bounced", "bounced@apple.test"),
                             ("a do-not-contact", "dnc@apple.test"),
                             ("a noted", "noted@apple.test"),
                             ("a CRM-linked", "crm@apple.test")):
            check(f"{label} delisted officer is KEPT, not deleted", email in got, sorted(got))
            if email in got:
                check(f"...{label} one is marked former", got[email].former_at is not None)
                check(f"...{label} one is unticked", not got[email].outreach_selected)
        check("a hand-added contact is never pruned", "manual@apple.test" in got)
        check("...a Workspace-added one too, by its rank alone (it was written "
              "source='api' before the fix)", "ws-old@apple.test" in got, sorted(got))
        check("...and a Workspace-added one written since, by its source",
              "ws-new@apple.test" in got, sorted(got))
        check("...and is never marked former either",
              "manual@apple.test" in got and got["manual@apple.test"].former_at is None)
        check("the org-level club mailbox is never pruned", "club@apple.test" in got)
        check("...and is never marked former either",
              "club@apple.test" in got and got["club@apple.test"].former_at is None)

        # ── a returning officer ──────────────────────────────────────────────
        print("\n── An officer PlayHQ lists again ────────────────────────────")
        await cd._upsert_club(db, org(contacts=[
            person("Bob", "Stay", "PRESIDENT", "bob@apple.test"),
            person("Una", "Unsub", "SECRETARY", "unsub@apple.test"),
        ]), prune=True, retick=True)
        await db.commit()
        got = await contacts_of()
        check("being listed again clears former_at", got["unsub@apple.test"].former_at is None)
        check("...but an unsubscribed officer is still NOT ticked",
              not got["unsub@apple.test"].outreach_selected)

        # ── the upstream-shape guard ─────────────────────────────────────────
        print("\n── A payload that says nothing about the committee ───────────")
        before = set(await contacts_of())
        await cd._upsert_club(db, org(), prune=True, retick=True)          # key absent
        await db.commit()
        check("contacts ABSENT prunes nobody (an upstream shape change cannot "
              "empty the directory)", set(await contacts_of()) == before,
              sorted(set(before) ^ set(await contacts_of())))
        await cd._upsert_club(db, org(contacts=None), prune=True, retick=True)   # null
        await db.commit()
        check("contacts NULL prunes nobody either", set(await contacts_of()) == before)
        await cd._upsert_club(db, org(contacts=[]), prune=True, retick=True)     # genuinely none
        await db.commit()
        after = await contacts_of()
        check("contacts [] IS a club that publishes none, so the prunable go",
              "bob@apple.test" not in after and "unsub@apple.test" in after, sorted(after))

        # ── one named club ───────────────────────────────────────────────────
        print("\n── Rediscovering one named club ─────────────────────────────")
        twin = MarketingClub(id=uuid.uuid4(), name="Applecross Cricket Club",
                             grassroots_guid="guid-other", playhq_id="oth", kind="club",
                             detail_fetched_at=func.now())
        db.add(twin)
        await db.commit()
        search_pages.clear(); calls["search"].clear(); calls["org_contact"].clear()
        org_contact_answer["value"] = None
        search_pages["Applecross Cricket Club"] = [
            org(guid="guid-other", name="Applecross Cricket Club", routing="oth",
                contacts=[person("Wrong", "Club", "PRESIDENT", "wrong@other.test")]),
            org(guid="guid-apple", contacts=[
                person("Bob", "Stay", "PRESIDENT", "bob@apple.test"),
                person("Eve", "New", "TREASURER", "eve@apple.test")]),
        ]
        res = await cd.rediscover_club(db, str(club.id))
        got = await contacts_of()
        check("one club: found", res.get("found") is True, res)
        check("...matched on the stored GUID, not the name two clubs share",
              "bob@apple.test" in got and "wrong@other.test" not in got, sorted(got))
        check("...the newly listed officer is stored and ticked",
              "eve@apple.test" in got and got["eve@apple.test"].outreach_selected)
        check("...it reports what it did", res.get("contacts") == 2, res)
        check("...on the SHORT interactive delay, not the 15-40s crawl pace",
              calls["search"] and calls["search"][0]["delay"] == cd._SINGLE_CLUB_DELAY,
              calls["search"][:1])
        check("...and refreshes the org-level mailbox too", len(calls["org_contact"]) == 1)

        # renamed on PlayHQ: found by routingCode instead
        search_pages.clear(); calls["search"].clear()
        search_pages["apl"] = [org(guid="guid-apple", contacts=[
            person("Bob", "Stay", "PRESIDENT", "bob@apple.test")])]
        res = await cd.rediscover_club(db, str(club.id))
        check("a club PlayHQ renamed is found by its routingCode",
              res.get("found") is True, res)
        check("...which took a second search", len(calls["search"]) == 2, calls["search"])

        # nowhere to be found
        search_pages.clear(); calls["search"].clear()
        res = await cd.rediscover_club(db, str(club.id))
        check("a club PlayHQ no longer lists reports found:false rather than raising",
              res.get("found") is False and res.get("error"), res)
        got = await contacts_of()
        check("...and prunes nobody on the way", "bob@apple.test" in got)

        # an unreachable PlayHQ is not an empty committee
        async def broken_search(*a, **k):
            return None, 0
        phq.search_organisations = broken_search
        res = await cd.rediscover_club(db, str(club.id))
        phq.search_organisations = fake_search
        check("PlayHQ being unreachable reads as a fetch failure, not an empty club",
              res.get("found") is False and "PlayHQ" in (res.get("error") or ""), res)
        check("...and still prunes nobody", "bob@apple.test" in await contacts_of())

        res = await cd.rediscover_club(db, str(uuid.uuid4()))
        check("an unknown club id is reported, not raised", res.get("found") is False, res)

        # ── the whole-directory run ──────────────────────────────────────────
        print("\n── Rediscover every club ────────────────────────────────────")
        search_pages.clear(); calls["search"].clear()
        search_pages["*"] = [
            org(guid="guid-apple", contacts=[person("Bob", "Stay", "PRESIDENT", "bob@apple.test")]),
            org(guid="guid-other", name="Applecross Cricket Club", routing="oth",
                contacts=[person("Wrong", "Club", "PRESIDENT", "wrong@other.test")]),
        ]
        progress: dict = {}
        stats = await cd.rediscover_all(db, progress=progress)
        check("the full run reports what it re-read", stats.get("au_seen") == 2, stats)
        check("...and reports the prune tallies", "pruned" in stats and "marked_former" in stats,
              stats)
        check("...updating progress in place for the poller",
              progress.get("clubs_seen") == 2, progress)
        check("the second club's own committee landed",
              "wrong@other.test" in await contacts_of("guid-other"))

        await cd.set_crawl_paused(db, True)
        stopped = await cd.rediscover_all(db)
        check("a stopped crawler stops a rediscover before it starts",
              stopped.get("skipped") == "stopped", stopped)
        await cd.set_crawl_paused(db, False)

        # ── ticking what we already hold ─────────────────────────────────────
        print("\n── Tick every listed officer with an email ──────────────────")
        rows = await contacts_of()
        for r in rows.values():
            r.outreach_selected = False
        await db.commit()
        res = await cd.bulk_tick_officers(db, None)
        got = await contacts_of()
        check("it ticks a listed officer with an email", got["bob@apple.test"].outreach_selected)
        check("it never ticks an unsubscribed officer",
              not got["unsub@apple.test"].outreach_selected)
        check("it never ticks a bounced officer", not got["bounced@apple.test"].outreach_selected)
        check("it never ticks a do-not-contact officer",
              not got["dnc@apple.test"].outreach_selected)
        check("it never ticks someone no longer on PlayHQ",
              not got["noted@apple.test"].outreach_selected)
        check("it reports how many it ticked", (res.get("ticked") or 0) >= 1, res)
        again = await cd.bulk_tick_officers(db, None)
        check("a second run ticks nobody new", again.get("ticked") == 0, again)

        # ── the export ───────────────────────────────────────────────────────
        print("\n── Exporting into BetterComms, and the role ─────────────────")
        got = await contacts_of()
        got["bob@apple.test"].role = "President"
        got["bob@apple.test"].outreach_selected = True
        await db.commit()
        res = await cd.export_to_comms(db, organisation_id=str(outreach.id))
        bob = await db.scalar(select(CommsContact).where(
            CommsContact.organisation_id == outreach.id,
            CommsContact.email == "bob@apple.test"))
        check("a newly exported officer carries their role", bob is not None and bob.role == "President",
              getattr(bob, "role", None))
        check("...and is linked back to the directory club",
              bob is not None and bob.marketing_club_id is not None)

        # The reported ask: an officer already in BetterComms changes role.
        club_row = await db.scalar(select(MarketingClub).where(
            MarketingClub.grassroots_guid == "guid-apple"))
        await cd._upsert_club(db, org(contacts=[
            person("Bob", "Stay", "TREASURER", "bob@apple.test")]), prune=True, retick=True)
        await db.commit()
        res = await cd.export_to_comms(db, organisation_id=str(outreach.id))
        await db.refresh(bob)
        check("an officer ALREADY in BetterComms has their role updated",
              bob.role == "Treasurer", bob.role)
        check("...and is counted as updated, not silently skipped",
              (res.get("updated") or 0) >= 1, res)

        # A hand-set name on the comms side is not overwritten; a blank one fills.
        bob.name = "Robert Stay (chair)"
        await db.commit()
        await cd.export_to_comms(db, organisation_id=str(outreach.id))
        await db.refresh(bob)
        check("a name set by hand on the comms side is never overwritten",
              bob.name == "Robert Stay (chair)", bob.name)

        # A suppressed address stays suppressed and is never re-added.
        bob.subscribed = False
        await db.commit()
        n_before = await db.scalar(select(func.count()).select_from(CommsContact))
        res = await cd.export_to_comms(db, organisation_id=str(outreach.id))
        await db.refresh(bob)
        n_after = await db.scalar(select(func.count()).select_from(CommsContact))
        check("an unsubscribed comms contact is never resurrected", bob.subscribed is False)
        check("...and no duplicate row is added for them", n_before == n_after,
              f"{n_before} -> {n_after}")
        bob.subscribed = True
        await db.commit()

        # A departed officer stays in BetterComms with the last role we knew.
        print("\n── A departed officer stays in BetterComms ──────────────────")
        await cd._upsert_club(db, org(contacts=[]), prune=True, retick=True)
        await db.commit()
        got = await contacts_of()
        await db.refresh(bob)
        check("the departed officer is out of the Directory",
              "bob@apple.test" not in got, sorted(got))
        check("...but still IN BetterComms", bob is not None)
        check("...carrying the last role we knew them by", bob.role == "Treasurer", bob.role)
        await cd.export_to_comms(db, organisation_id=str(outreach.id))
        await db.refresh(bob)
        check("...and a later export does not blank it", bob.role == "Treasurer", bob.role)

        # ── the payload the screens read ─────────────────────────────────────
        print("\n── What the screens are told ────────────────────────────────")
        row = (await db.execute(select(MarketingClubContact).where(
            MarketingClubContact.email == "noted@apple.test"))).scalar_one()
        out = _contact_out(row)
        check("a directory contact reports whether PlayHQ still lists them",
              out.get("former") is True, out)
        live = (await db.execute(select(MarketingClubContact).where(
            MarketingClubContact.email == "manual@apple.test"))).scalar_one()
        check("...and a listed one reports former:false", _contact_out(live).get("former") is False)

        marketing_src = load("backend/app/routers/marketing.py")
        check("the club list and the club card share ONE contact serialiser",
              marketing_src.count('"selected": ct.outreach_selected') == 1,
              marketing_src.count('"selected": ct.outreach_selected'))

        comms_out = load("backend/app/routers/comms.py")
        check("a BetterComms contact carries its role to the Lists screen",
              '"role": (c.role or "")' in comms_out)
        audience = load("frontend/src/pages/admin/bettercomms/audience.jsx")
        check("Role is a filter facet on Lists and Segments",
              "{ key: 'role', label: 'Role' }" in audience)
        check("...and one definition of the facet shape, not two",
              audience.count("club: [], association: []") == 1
              and "const noFilters = emptyFilters" in
              load("frontend/src/pages/admin/bettercomms/CommsLists.jsx"))

    print(f"\n{'=' * 62}\n  {len(PASS)} passed, {len(FAIL)} failed\n{'=' * 62}")
    for f in FAIL:
        print(f"  FAIL  {f}")
    await engine.dispose()
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
