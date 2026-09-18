"""Role Programs — what a role entails, and its measurable handover.

Runs the SHIPPED services (club_diary cadence widening + role_programs) and the
shipped DDL against a real Postgres. Nothing is retyped.

  python -m verification.verify_role_programs
  RP_CONTROL=1 python -m verification.verify_role_programs   # neuters the
      standing-cadence guard so the "a weekly/matchday duty floods no dated
      occurrence" checks FAIL — proof those checks bite.

The two halves under test:
  - The Club Diary cadence set is widened to weekly / matchday / season_start /
    season_end / ongoing. Standing cadences (weekly/matchday/ongoing) must
    generate NO dated occurrence (they would flood a season plan); season_start
    / season_end must pin to the club's diary_start_month.
  - A role's PROGRAM is assembled on read; its HANDOVER seeds an onboarding
    checklist snapshot, rolls up to a percentage + gap list, reseeds additively
    without touching worked statuses, and survives a later edit of the diary
    task it was seeded from.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_URL = os.environ.get(
    "VERIFY_DATABASE_URL",
    "postgresql+asyncpg://postgres@127.0.0.1:55432/verify_role_programs",
)
os.environ["DATABASE_URL"] = DB_URL

from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.models.db import (  # noqa: E402
    Base, Organisation, User, ClubRole, ClubRoleType, CommitteePosition, CommitteeTerm,
    FeeMember, VolunteerRole, DiaryCategory, DiaryTaskDefinition, DiaryTaskOccurrence,
    QualificationType, RoleProgramHandover, RoleProgramHandoverItem,
)
from app.services import club_diary as diary  # noqa: E402
from app.services import role_programs as rp  # noqa: E402
from app.services.role_program_ddl import STATEMENTS as RP_DDL  # noqa: E402

CONTROL = bool(os.environ.get("RP_CONTROL"))
if CONTROL:
    # Break the no-flood guard: standing cadences now generate dated occurrences.
    diary._STANDING = set()

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  ({detail})'}")


# The raw-SQL roster table role_programs reads (not ORM-mapped), copied from the
# main.py lifespan mirror so the harness tests the real query shape.
ROSTER_AREAS_DDL = """
CREATE TABLE IF NOT EXISTS roster_areas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    department TEXT,
    color TEXT,
    required_role_id UUID REFERENCES club_roles(id) ON DELETE SET NULL,
    required_qualification_type_id UUID REFERENCES qualification_types(id) ON DELETE SET NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""
# The area role PALETTE (migration 306) role_programs._role_areas reads.
ROSTER_AREA_ROLES_DDL = """
CREATE TABLE IF NOT EXISTS roster_area_roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    area_id UUID NOT NULL REFERENCES roster_areas(id) ON DELETE CASCADE,
    role_id UUID NOT NULL REFERENCES club_roles(id) ON DELETE CASCADE,
    required_qualification_type_id UUID REFERENCES qualification_types(id) ON DELETE SET NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_roster_area_roles UNIQUE (area_id, role_id)
)
"""


async def occ_by_def(db, def_id):
    return (await db.execute(select(DiaryTaskOccurrence).where(
        DiaryTaskOccurrence.definition_id == def_id))).scalars().all()


async def main() -> int:  # noqa: C901
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(ROSTER_AREAS_DDL))
        await conn.execute(text(ROSTER_AREA_ROLES_DDL))

    Session = async_sessionmaker(engine, expire_on_commit=False)

    # ── DDL: create_all made the two tables; drop them and prove the SHIPPED
    #    statements build them, three times, idempotently ────────────────────
    print("\n── DDL (migration 307) ──────────────────────────────────────")
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS role_program_handover_items"))
        await conn.execute(text("DROP TABLE IF EXISTS role_program_handovers"))
        ok = True
        try:
            for _ in range(3):
                for stmt in RP_DDL:
                    await conn.execute(text(stmt))
        except Exception as e:  # noqa: BLE001
            ok = False
            print("   DDL error:", e)
        check("shipped DDL applies three times, idempotently", ok)
        cols = set((await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='role_program_handover_items'"))).scalars().all())
        check("items table has the snapshot columns",
              {"source_kind", "source_key", "source_definition_id", "label", "cadence", "status"} <= cols,
              str(sorted(cols)))
        idx = set((await conn.execute(text(
            "SELECT indexname FROM pg_indexes WHERE tablename='role_program_handover_items'"))).scalars().all())
        check("partial-unique dedupe index exists", "uq_role_program_handover_item_src" in idx, str(idx))

    async with Session() as db:
        # ── Fixtures ──────────────────────────────────────────────────────
        org = Organisation(id=uuid.uuid4(), name="Test CC", slug="test-cc", diary_start_month=7)
        org2 = Organisation(id=uuid.uuid4(), name="Other CC", slug="other-cc", diary_start_month=7)
        db.add_all([org, org2])
        await db.flush()
        user = User(id=uuid.uuid4(), username="admin", email="a@x.com")
        db.add(user)
        ct_committee = ClubRoleType(organisation_id=org.id, name="Office Bearer", category="committee")
        ct_vol = ClubRoleType(organisation_id=org.id, name="Food & Beverage", category="volunteer")
        db.add_all([ct_committee, ct_vol])
        await db.flush()

        treasurer = ClubRole(organisation_id=org.id, title="Treasurer", role_type_id=ct_committee.id,
                             description="Keeps the club's books.", is_committee=True)
        canteen = ClubRole(organisation_id=org.id, title="Canteen Manager", role_type_id=ct_vol.id,
                           description="Runs the canteen on match days.", is_committee=False)
        db.add_all([treasurer, canteen])
        await db.flush()

        pos = CommitteePosition(organisation_id=org.id, name="Treasurer", role_id=treasurer.id,
                                responsibilities="Manage bank accounts, pay invoices, report to the committee.",
                                is_office_bearer=True)
        db.add(pos)
        await db.flush()
        jane = FeeMember(organisation_id=org.id, full_name="Jane Old")
        bob = FeeMember(organisation_id=org.id, full_name="Bob New")
        sam = FeeMember(organisation_id=org.id, full_name="Sam Vol")
        other_member = FeeMember(organisation_id=org2.id, full_name="Outsider")
        db.add_all([jane, bob, sam, other_member])
        await db.flush()
        db.add(CommitteeTerm(organisation_id=org.id, position_id=pos.id, member_id=jane.id,
                             holder_name="Jane Old", started_at=dt.date(2025, 9, 1)))
        db.add(VolunteerRole(organisation_id=org.id, member_id=sam.id, role_id=canteen.id))
        qtype = QualificationType(organisation_id=org.id, name="Food Handling")
        cat = DiaryCategory(organisation_id=org.id, name="Ground & Equipment", color="#f59e0b")
        db.add_all([qtype, cat])
        await db.flush()

        def deff(title, freq, role, **kw):
            d = DiaryTaskDefinition(organisation_id=org.id, title=title, frequency=freq,
                                    responsibility_role_id=role.id, category_id=cat.id, **kw)
            db.add(d)
            return d

        d_weekly = deff("Restock the canteen", "weekly", canteen)
        d_match = deff("Match-day float and till", "matchday", canteen)
        d_sstart = deff("Pre-season stock order", "season_start", canteen)
        d_send = deff("End-of-season stocktake", "season_end", canteen)
        d_quart = deff("Supplier price review", "quarterly", canteen)
        d_ongoing = deff("Food-safety compliance", "ongoing", canteen)
        d_annual = deff("Liquor licence renewal", "annual", canteen, default_month=5)
        deff("Quarterly BAS", "quarterly", treasurer)
        deff("Bookkeeping", "ongoing", treasurer)
        await db.flush()

        # roster_areas + role palette raw inserts (not ORM-mapped). The area
        # lists the Canteen role in its palette with the Food Handling qual — the
        # shape role_programs._role_areas reads after migration 306.
        area_id = uuid.uuid4()
        await db.execute(text(
            "INSERT INTO roster_areas (id, organisation_id, name) VALUES (:id, :o, :n)"),
            {"id": area_id, "o": org.id, "n": "Canteen"})
        await db.execute(text(
            "INSERT INTO roster_area_roles (id, organisation_id, area_id, role_id, required_qualification_type_id) "
            "VALUES (gen_random_uuid(), :o, :a, :r, :q)"),
            {"o": org.id, "a": area_id, "r": canteen.id, "q": qtype.id})
        await db.commit()

        # Plain-value ids for use after any rollback below — a rollback expires
        # every loaded instance, and reading `.id` off one then triggers a sync
        # lazy-load outside the greenlet (the documented MissingGreenlet trap).
        ORG, ORG2 = org.id, org2.id
        CANTEEN, TREASURER = canteen.id, treasurer.id
        OTHER, USER = other_member.id, user.id

        # ── Cadence widening (Club Diary) ─────────────────────────────────
        print("\n── Club Diary cadence widening ──────────────────────────────")
        created = await diary.generate_season(db, org.id, 2026)
        await db.commit()
        # standing cadences make no occurrences
        check("a weekly duty floods no dated occurrence", len(await occ_by_def(db, d_weekly.id)) == 0)
        check("a matchday duty floods no dated occurrence", len(await occ_by_def(db, d_match.id)) == 0)
        check("an ongoing responsibility makes no dated occurrence", len(await occ_by_def(db, d_ongoing.id)) == 0)
        # dated cadences pin correctly
        so = await occ_by_def(db, d_sstart.id)
        check("season_start makes exactly one occurrence", len(so) == 1, str(len(so)))
        check("season_start pins to the club's diary_start_month (July)",
              bool(so) and so[0].due_date and so[0].due_date.month == 7 and so[0].due_date.year == 2026,
              str(so[0].due_date) if so else "none")
        se = await occ_by_def(db, d_send.id)
        check("season_end pins to the month before the diary year (June)",
              bool(se) and se[0].due_date and se[0].due_date.month == 6, str(se[0].due_date) if se else "none")
        an = await occ_by_def(db, d_annual.id)
        check("an explicit default_month still wins", bool(an) and an[0].due_date.month == 5,
              str(an[0].due_date) if an else "none")
        check("quarterly still makes four occurrences", len(await occ_by_def(db, d_quart.id)) == 4)
        # generate_season count: season_start1 + season_end1 + quarterly4 + annual1 + (treasurer quarterly4) = 11
        check("generate_season counts only dated occurrences", created == 11, str(created))

        brd = await diary.board(db, org.id)
        await db.commit()
        bym = {b["title"]: b for b in brd}
        check("the board lists a standing duty (occurrence None)",
              bym["Restock the canteen"]["occurrence"] is None)
        check("the board carries the new cadence value through",
              bym["Match-day float and till"]["frequency"] == "matchday")

        # ── Program assembly ──────────────────────────────────────────────
        print("\n── Program assembly ─────────────────────────────────────────")
        prog = await rp.assemble_program(db, org.id, canteen.id)
        check("program returns the role's purpose", prog["role"]["description"] == "Runs the canteen on match days.")
        check("program names the role type", prog["role"]["role_type_name"] == "Food & Beverage")
        check("program lists every duty tagged to the role", len(prog["duties"]) == 7, str(len(prog["duties"])))
        check("duties are cadence-sorted, matchday first",
              prog["duties"][0]["cadence"] == "matchday" and prog["duties"][-1]["cadence"] == "ongoing",
              f'{prog["duties"][0]["cadence"]}..{prog["duties"][-1]["cadence"]}')
        check("program lists the operational area the role covers",
              len(prog["areas"]) == 1 and prog["areas"][0]["name"] == "Canteen")
        check("the area carries its required qualification",
              prog["areas"][0]["required_qualification"] == "Food Handling")
        check("a non-committee role has no committee context", prog["committee"] is None)
        check("the current holder is the volunteer who holds the role",
              prog["current_holders"] == ["Sam Vol"], str(prog["current_holders"]))

        tprog = await rp.assemble_program(db, org.id, treasurer.id)
        check("a committee role carries its position responsibilities",
              tprog["committee"] and "bank accounts" in tprog["committee"]["responsibilities"])
        check("a committee role's current holder is the open term",
              tprog["current_holders"] == ["Jane Old"], str(tprog["current_holders"]))
        check("a committee role is office-bearer flagged",
              tprog["committee"]["is_office_bearer"] is True)

        check("another club's role is not resolvable here",
              (await rp.assemble_program(db, org2.id, canteen.id)) is None)

        # ── Handover seeding + progress ───────────────────────────────────
        print("\n── Handover: seeding & progress ─────────────────────────────")
        h = await rp.create_handover(db, org.id, role_id=canteen.id, incoming_member_id=bob.id,
                                     outgoing_member_id=sam.id, target_date=dt.date(2026, 8, 1),
                                     notes="Season handover", created_by=user.id)
        await db.commit()
        detail = await rp.get_handover(db, org.id, h.id)
        check("handover snapshots the role title", detail["role_title"] == "Canteen Manager")
        check("incoming name is resolved from the member", detail["incoming_name"] == "Bob New")
        check("outgoing name is resolved from the member", detail["outgoing_name"] == "Sam Vol")
        # 7 duties + 1 area (no committee responsibilities on a volunteer role)
        check("the checklist is seeded from every program element",
              len(detail["items"]) == 8, str(len(detail["items"])))
        kinds = {}
        for it in detail["items"]:
            kinds[it["source_kind"]] = kinds.get(it["source_kind"], 0) + 1
        check("an ongoing duty seeds as a responsibility, dated duties as duties",
              kinds.get("responsibility") == 1 and kinds.get("duty") == 6 and kinds.get("area") == 1, str(kinds))
        check("a duty item links back to its diary definition",
              any(it["source_definition_id"] for it in detail["items"] if it["source_kind"] == "duty"))
        check("a fresh handover reads 0% with every element a gap",
              detail["progress"]["percent"] == 0 and detail["progress"]["gaps"] == 8
              and detail["progress"]["complete"] is False)

        items = detail["items"]
        # 4 accepted, 1 na, 3 pending → applicable 7, percent round(4/7*100)=57
        for it in items[:4]:
            row = await rp.load_item(db, org.id, h.id, uuid.UUID(it["id"]))
            await rp.update_item(db, row, status="accepted", updated_by=user.id)
        na_row = await rp.load_item(db, org.id, h.id, uuid.UUID(items[4]["id"]))
        await rp.update_item(db, na_row, status="na", updated_by=user.id)
        await db.commit()
        p = (await rp.get_handover(db, org.id, h.id))["progress"]
        check("N/A items drop out of the applicable count",
              p["applicable"] == 7 and p["na"] == 1, str(p))
        check("percent is accepted over applicable",
              p["percent"] == round(4 / 7 * 100) and p["accepted"] == 4, str(p))
        check("gaps are what is neither accepted nor N/A", p["gaps"] == 3, str(p))
        check("a partly-worked handover is not complete", p["complete"] is False)

        # walked_through is a gap, not acceptance
        w_row = await rp.load_item(db, org.id, h.id, uuid.UUID(items[5]["id"]))
        await rp.update_item(db, w_row, status="walked_through", updated_by=user.id)
        await db.commit()
        p = (await rp.get_handover(db, org.id, h.id))["progress"]
        check("walked-through counts as a gap, not acceptance",
              p["walked_through"] == 1 and p["accepted"] == 4 and p["gaps"] == 3, str(p))

        # ── Custom item + reseed ──────────────────────────────────────────
        print("\n── Handover: custom items & reseed ──────────────────────────")
        await rp.add_item(db, org.id, h, label="Where the shed key lives", detail="Behind the scoreboard.")
        await db.commit()
        d2 = await rp.get_handover(db, org.id, h.id)
        custom = [it for it in d2["items"] if it["source_kind"] == "custom"]
        check("a custom knowledge item is added with no source key",
              len(custom) == 1 and custom[0]["source_key"] is None)

        # snapshot: archive + rename the weekly duty — the handover item is unchanged
        d_weekly.title = "RENAMED restock"
        d_weekly.is_active = False
        await db.commit()
        added0 = await rp.reseed_handover(db, org.id, h)
        await db.commit()
        d3 = await rp.get_handover(db, org.id, h.id)
        weekly_item = [it for it in d3["items"] if it["label"] == "Restock the canteen"]
        check("an item's label is a snapshot, unchanged by a later rename",
              len(weekly_item) == 1)
        check("reseed does not re-add an archived duty", added0 == 0, str(added0))

        # add a brand-new duty → reseed pulls exactly it, existing statuses untouched
        newd = DiaryTaskDefinition(organisation_id=org.id, title="Deep clean the fryers", frequency="monthly",
                                   responsibility_role_id=canteen.id)
        db.add(newd)
        await db.commit()
        added1 = await rp.reseed_handover(db, org.id, h)
        await db.commit()
        check("reseed pulls in exactly the newly-added duty", added1 == 1, str(added1))
        added2 = await rp.reseed_handover(db, org.id, h)
        await db.commit()
        check("a second reseed adds nothing (dedupe)", added2 == 0, str(added2))
        p = (await rp.get_handover(db, org.id, h.id))["progress"]
        check("reseed leaves the four accepted items accepted", p["accepted"] == 4, str(p))

        # committee handover seeds the position responsibilities
        th = await rp.create_handover(db, org.id, role_id=treasurer.id, incoming_member_id=bob.id, created_by=user.id)
        await db.commit()
        tdetail = await rp.get_handover(db, org.id, th.id)
        check("a committee handover seeds the position responsibilities",
              any(it["source_key"] == "position:responsibilities" for it in tdetail["items"]))
        check("a committee handover seeds its two duties too",
              len(tdetail["items"]) == 3, str(len(tdetail["items"])))

        # ── Completion, guards, deletion ──────────────────────────────────
        print("\n── Handover: completion, guards, deletion ───────────────────")
        h2 = await rp.load_handover(db, org.id, h.id)
        await rp.update_handover(db, org.id, h2, status="completed")
        await db.commit()
        cd = await rp.get_handover(db, org.id, h.id)
        check("completing a handover stamps completed_at",
              cd["status"] == "completed" and cd["completed_at"] is not None)

        HID = h.id  # captured before the rollbacks below expire the instance
        # cross-club / invalid guards (plain-value ids — see the capture above)
        try:
            await rp.create_handover(db, ORG2, role_id=CANTEEN, created_by=USER)
            crossed = False
        except ValueError:
            crossed = True
        await db.rollback()
        check("a handover cannot be started for another club's role", crossed)

        try:
            await rp.create_handover(db, ORG, role_id=CANTEEN, incoming_member_id=OTHER, created_by=USER)
            m_crossed = False
        except ValueError:
            m_crossed = True
        await db.rollback()
        check("an incoming member from another club is refused", m_crossed)

        check("a handover is not loadable cross-club",
              (await rp.load_handover(db, ORG2, HID)) is None)
        check("get_handover is 404-shaped cross-club",
              (await rp.get_handover(db, ORG2, HID)) is None)

        # list scoping
        hl = await rp.list_handovers(db, ORG, role_id=CANTEEN)
        check("list_handovers scopes to the role and carries progress",
              len(hl) == 1 and "progress" in hl[0])
        check("another club sees none of these handovers",
              len(await rp.list_handovers(db, ORG2)) == 0)

        # delete an item then the handover (items cascade)
        an_item = (await rp.get_handover(db, ORG, HID))["items"][0]
        it_row = await rp.load_item(db, ORG, HID, uuid.UUID(an_item["id"]))
        await rp.delete_item(db, it_row)
        await db.commit()
        check("an item can be removed",
              all(x["id"] != an_item["id"] for x in (await rp.get_handover(db, ORG, HID))["items"]))
        hrow = await rp.load_handover(db, ORG, HID)
        await rp.delete_handover(db, hrow)
        await db.commit()
        left = (await db.execute(select(RoleProgramHandoverItem).where(
            RoleProgramHandoverItem.handover_id == HID))).scalars().all()
        check("deleting a handover cascades its items", len(left) == 0, str(len(left)))

    await engine.dispose()
    print(f"\n{'='*60}\n  {'CONTROL RUN — ' if CONTROL else ''}{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("  FAILURES:")
        for f in FAIL:
            print("   -", f)
    return 1 if (FAIL and not CONTROL) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
