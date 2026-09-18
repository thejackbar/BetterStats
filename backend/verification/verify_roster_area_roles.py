"""Verification for multiple roles per operational area (migration 306), against
a real Postgres.

Exercises the SHIPPED service (services/roster.py) — never a re-implementation
of its logic. The questions worth the harness, because none can be read off the
code alone:

  * THE BACKFILL. A legacy area carried ONE role and ONE qualification. Migration
    306 has to turn every one into a one-entry palette AND stamp that role onto
    the area's existing patterns and shifts, or an existing roster would behave
    differently the day it deploys.

  * THE QUALIFICATION BLOCK IS PER ROLE, NOT PER AREA. A Match Day area holds an
    Umpire role that needs accreditation beside a Scorer role that needs nothing.
    A candidate with no accreditation must be BLOCKED for the Umpire shift and
    NOT for the Scorer shift in the same area — the whole point of the change.

  * PAID IS PER SHIFT. One area can hold a paid role and a volunteer role, so
    whether a shift's hours are paid follows the shift's role, not the area.

  * SHORTAGES ARE BUCKETED BY THE SHIFT'S ROLE, so "we need two more umpires" no
    longer sweeps the scorer shifts in with them.

Run:      DATABASE_URL=postgresql+asyncpg://... python verify_roster_area_roles.py
Control:  git stash push backend/app/services/roster.py backend/app/routers/roster.py
          DATABASE_URL=... python verify_roster_area_roles.py     # many checks fail
          git stash pop
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import (
    Base, Organisation, User, ClubRole, ClubRoleType, QualificationType,
    FeeMember, VolunteerProfile, VolunteerRole, MemberQualification,
)
from app.services import roster as svc

DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

PASS = FAIL = 0
FAILURES: list[str] = []


def check(label, got, want=True):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        FAILURES.append(f"{label}: got {got!r}, want {want!r}")
        print(f"  FAIL {label}: got {got!r}, want {want!r}")


async def caught(label, factory):
    """Run a shipped call that a control (old code) can't satisfy. `factory` is a
    no-arg callable returning the coroutine, so an old signature raising at the
    CALL site is recorded as a FAIL rather than crashing the run."""
    try:
        return await factory()
    except Exception as e:  # noqa: BLE001
        check(label, f"raised {type(e).__name__}")
        return None


MIGRATION = Path(__file__).resolve().parent.parent / "alembic/versions/306_roster_area_roles.py"
MAIN = Path(__file__).resolve().parent.parent / "app/main.py"


def migration_statements() -> list[str]:
    src = MIGRATION.read_text()
    ns: dict = {}
    exec(compile(src, str(MIGRATION), "exec"), ns)  # noqa: S102 — our own file
    return ns.get("STATEMENTS", [])


# The pre-306 roster schema (208 + 211 + 222), so the migration has real work to
# do: no roster_area_roles, no role_id on patterns/shifts.
PRE_306 = [
    """CREATE TABLE roster_areas (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        name TEXT NOT NULL, department TEXT, color TEXT,
        required_role_id UUID REFERENCES club_roles(id) ON DELETE SET NULL,
        required_qualification_type_id UUID REFERENCES qualification_types(id) ON DELETE SET NULL,
        sort_order INTEGER NOT NULL DEFAULT 0, is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""",
    """CREATE TABLE roster_shift_patterns (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        area_id UUID NOT NULL REFERENCES roster_areas(id) ON DELETE CASCADE,
        day_of_week INTEGER NOT NULL, start_time NUMERIC(4,2) NOT NULL, end_time NUMERIC(4,2) NOT NULL,
        headcount INTEGER NOT NULL DEFAULT 1, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""",
    """CREATE TABLE roster_weeks (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        week_start DATE NOT NULL, status TEXT NOT NULL DEFAULT 'draft',
        confirmed_at TIMESTAMPTZ, confirmed_by_user_id UUID,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_roster_weeks_org_week UNIQUE (organisation_id, week_start))""",
    """CREATE TABLE roster_shifts (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        roster_week_id UUID NOT NULL REFERENCES roster_weeks(id) ON DELETE CASCADE,
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        area_id UUID NOT NULL REFERENCES roster_areas(id) ON DELETE CASCADE,
        day_of_week INTEGER NOT NULL, start_time NUMERIC(4,2) NOT NULL, end_time NUMERIC(4,2) NOT NULL,
        assignee_member_id UUID REFERENCES fee_members(id) ON DELETE SET NULL,
        worked_hours NUMERIC(5,2), warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""",
    """CREATE TABLE roster_settings (
        organisation_id UUID PRIMARY KEY REFERENCES organisations(id) ON DELETE CASCADE,
        enforce_qualifications BOOLEAN NOT NULL DEFAULT TRUE, weekly_shift_cap INTEGER NOT NULL DEFAULT 0,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""",
    """CREATE TABLE roster_departments (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        name TEXT NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0, is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_roster_departments_org_name UNIQUE (organisation_id, name))""",
]


async def build_schema():
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)
        # A raw-SQL column (migration 208), not on the ORM model, so create_all
        # doesn't build it; the roster candidates query reads it.
        await conn.execute(text("ALTER TABLE volunteer_profiles ADD COLUMN IF NOT EXISTS max_shifts_per_week INTEGER"))
        for stmt in PRE_306:
            await conn.execute(text(stmt))


# ── ids ──────────────────────────────────────────────────────────────────────
CLUB = uuid.uuid4(); OTHER = uuid.uuid4()
RT_VOL = uuid.uuid4(); RT_PAID = uuid.uuid4()
UMPIRE = uuid.uuid4(); SCORER = uuid.uuid4(); TEAM_MGR = uuid.uuid4(); BAR = uuid.uuid4()
Q_ACC = uuid.uuid4(); Q_RSA = uuid.uuid4()
CAND_A = uuid.uuid4(); CAND_B = uuid.uuid4(); CAND_C = uuid.uuid4(); CAND_D = uuid.uuid4(); CAND_E = uuid.uuid4()
LEGACY_AREA = uuid.uuid4(); LEGACY_PAT = uuid.uuid4(); LEGACY_WEEK = uuid.uuid4(); LEGACY_SHIFT = uuid.uuid4()
MATCHDAY = uuid.uuid4()
OTHER_AREA = uuid.uuid4()

NEXT_MON = date.today() + timedelta(days=(7 - date.today().weekday()))  # next Monday, all future
SAT = 5


async def seed_base(db):
    db.add_all([
        Organisation(id=CLUB, name="Applecross Cricket Club", slug="acc-ar", subscription_status="active", module_overrides=[]),
        Organisation(id=OTHER, name="High Wycombe CC", slug="hwcc-ar", subscription_status="active", module_overrides=[]),
        User(id=uuid.uuid4(), username="coach-ar", email="c@ar.com", password_hash="x"),
    ])
    await db.flush()  # organisations must exist before anything referencing them
    db.add_all([
        ClubRoleType(id=RT_VOL, organisation_id=CLUB, name="Volunteer", category="volunteer"),
        ClubRoleType(id=RT_PAID, organisation_id=CLUB, name="Paid staff", category="paid"),
        QualificationType(id=Q_ACC, organisation_id=CLUB, name="Umpire Accreditation"),
        QualificationType(id=Q_RSA, organisation_id=CLUB, name="RSA"),
    ])
    await db.flush()
    db.add_all([
        ClubRole(id=UMPIRE, organisation_id=CLUB, title="Umpire", role_type_id=RT_VOL),
        ClubRole(id=SCORER, organisation_id=CLUB, title="Scorer", role_type_id=RT_VOL),
        ClubRole(id=TEAM_MGR, organisation_id=CLUB, title="Team Manager", role_type_id=RT_VOL),
        ClubRole(id=BAR, organisation_id=CLUB, title="Bar Supervisor", role_type_id=RT_PAID),
    ])
    await db.flush()
    # Candidates: a fee_member + a volunteer_profile (availability) + the roles
    # they hold + the qualifications they hold.
    people = [
        (CAND_A, "Anna Umpire", {UMPIRE}, {Q_ACC}),
        (CAND_B, "Ben Scorer", {SCORER}, set()),
        (CAND_C, "Cara NoAcc", {UMPIRE}, set()),
        (CAND_D, "Dan CrossRole", {SCORER}, {Q_ACC}),
        (CAND_E, "Eve BarStaff", {BAR}, {Q_RSA}),
    ]
    for mid, nm, roles, quals in people:
        db.add(FeeMember(id=mid, organisation_id=CLUB, full_name=nm))
        await db.flush()
        db.add(VolunteerProfile(id=uuid.uuid4(), organisation_id=CLUB, member_id=mid, available_days=[0, 1, 2, 3, 4, 5, 6]))
        for rid in roles:
            db.add(VolunteerRole(id=uuid.uuid4(), organisation_id=CLUB, member_id=mid, role_id=rid))
        for qid in quals:
            db.add(MemberQualification(id=uuid.uuid4(), organisation_id=CLUB, member_id=mid, qualification_type_id=qid))
    await db.flush()


async def seed_legacy(db):
    """A pre-306 single-role area, with a pattern, a week and one shift — none of
    which know about roles yet. Migration 306's backfill has to fix all three."""
    await db.execute(text("""
        INSERT INTO roster_areas (id, organisation_id, name, department, color, required_role_id, required_qualification_type_id, sort_order)
        VALUES (:id, :org, 'Legacy Bar', 'Food & Beverage', '#f5b542', :role, :qual, 0)
    """), {"id": LEGACY_AREA, "org": CLUB, "role": BAR, "qual": Q_RSA})
    await db.execute(text("""
        INSERT INTO roster_shift_patterns (id, organisation_id, area_id, day_of_week, start_time, end_time, headcount)
        VALUES (:id, :org, :area, :dow, 12, 18, 1)
    """), {"id": LEGACY_PAT, "org": CLUB, "area": LEGACY_AREA, "dow": SAT})
    await db.execute(text("""
        INSERT INTO roster_weeks (id, organisation_id, week_start, status)
        VALUES (:id, :org, :ws, 'draft')
    """), {"id": LEGACY_WEEK, "org": CLUB, "ws": NEXT_MON})
    await db.execute(text("""
        INSERT INTO roster_shifts (id, roster_week_id, organisation_id, area_id, day_of_week, start_time, end_time)
        VALUES (:id, :wk, :org, :area, :dow, 12, 18)
    """), {"id": LEGACY_SHIFT, "wk": LEGACY_WEEK, "org": CLUB, "area": LEGACY_AREA, "dow": SAT})


async def seed_matchday_raw(db):
    """The multi-role area, seeded as raw rows so BOTH the shipped code and the
    control read the same data. Its deprecated single-role fields are set to a
    VOLUNTEER role + the umpire qualification, which is exactly what the old code
    reads — so the control over-blocks the scorer and mis-classifies the paid
    shift, the two behaviours this change fixes."""
    await db.execute(text("""
        INSERT INTO roster_areas (id, organisation_id, name, department, color, required_role_id, required_qualification_type_id, sort_order)
        VALUES (:id, :org, 'Match Day', 'Cricket Operations', '#3b82f6', :role, :qual, 1)
    """), {"id": MATCHDAY, "org": CLUB, "role": UMPIRE, "qual": Q_ACC})
    palette = [(UMPIRE, Q_ACC, 0), (SCORER, None, 1), (TEAM_MGR, None, 2), (BAR, Q_RSA, 3)]
    for rid, qid, so in palette:
        await db.execute(text("""
            INSERT INTO roster_area_roles (id, organisation_id, area_id, role_id, required_qualification_type_id, sort_order)
            VALUES (:id, :org, :area, :role, :qual, :so)
        """), {"id": uuid.uuid4(), "org": CLUB, "area": MATCHDAY, "role": rid, "qual": qid, "so": so})
    pats = [(UMPIRE, 12, 18, 2), (SCORER, 12, 18, 2), (BAR, 18, 22, 1)]
    for rid, st, et, hc in pats:
        await db.execute(text("""
            INSERT INTO roster_shift_patterns (id, organisation_id, area_id, day_of_week, start_time, end_time, headcount, role_id)
            VALUES (:id, :org, :area, :dow, :st, :et, :hc, :role)
        """), {"id": uuid.uuid4(), "org": CLUB, "area": MATCHDAY, "dow": SAT, "st": st, "et": et, "hc": hc, "role": rid})
    # Another club's area, for cross-club scoping.
    await db.execute(text("""
        INSERT INTO roster_areas (id, organisation_id, name, sort_order) VALUES (:id, :org, 'Other Bar', 0)
    """), {"id": OTHER_AREA, "org": OTHER})


async def main():
    print("\n=== migration + lifespan mirror ===")
    stmts = migration_statements()
    check("306 STATEMENTS present", len(stmts) >= 6)
    main_src = MAIN.read_text()
    check("main.py mirrors roster_area_roles", "CREATE TABLE IF NOT EXISTS roster_area_roles" in main_src)
    check("main.py mirrors patterns.role_id", "roster_shift_patterns ADD COLUMN IF NOT EXISTS role_id" in main_src)
    check("main.py mirrors shifts.role_id", "roster_shifts ADD COLUMN IF NOT EXISTS role_id" in main_src)

    await build_schema()
    async with Session() as db:
        await seed_base(db); await seed_legacy(db); await db.commit()

    # Apply the migration THREE times — idempotent, and the backfill runs before
    # the multi-role area is seeded so it only ever sees the legacy rows.
    ok = True
    for _ in range(3):
        try:
            async with engine.begin() as conn:
                for s in stmts:
                    await conn.execute(text(s))
        except Exception as e:  # noqa: BLE001
            ok = False; print("   migration error:", e)
    check("306 applies three times, idempotent", ok)

    async with Session() as db:
        await seed_matchday_raw(db); await db.commit()

    print("\n=== the backfill carried the legacy area across ===")
    async with Session() as db:
        n = (await db.execute(text("SELECT COUNT(*) FROM roster_area_roles WHERE area_id=:a"), {"a": LEGACY_AREA})).scalar()
        check("legacy area now has one palette entry", n == 1)
        row = (await db.execute(text("SELECT role_id, required_qualification_type_id FROM roster_area_roles WHERE area_id=:a"), {"a": LEGACY_AREA})).mappings().first()
        check("legacy palette role is Bar Supervisor", str(row["role_id"]) == str(BAR))
        check("legacy palette keeps its RSA qualification", str(row["required_qualification_type_id"]) == str(Q_RSA))
        pr = (await db.execute(text("SELECT role_id FROM roster_shift_patterns WHERE id=:p"), {"p": LEGACY_PAT})).scalar()
        check("legacy pattern inherited the role", str(pr) == str(BAR))
        sr = (await db.execute(text("SELECT role_id FROM roster_shifts WHERE id=:s"), {"s": LEGACY_SHIFT})).scalar()
        check("legacy shift inherited the role", str(sr) == str(BAR))

    async with Session() as db:
        areas = await svc.list_areas(db, CLUB)
        legacy = next((a for a in areas if a["id"] == str(LEGACY_AREA)), None)
        check("list_areas returns the legacy area", legacy is not None)
        lroles = (legacy or {}).get("roles", [])
        check("legacy area lists one role", len(lroles) == 1)
        check("legacy role is paid (Bar Supervisor is a paid type)", bool(lroles and lroles[0].get("is_paid")))
        check("deprecated required_role_id still populated", (legacy or {}).get("required_role_id") == str(BAR))

    print("\n=== a multi-role area lists all its roles, each with its own qual ===")
    async with Session() as db:
        areas = await svc.list_areas(db, CLUB)
        md = next((a for a in areas if a["id"] == str(MATCHDAY)), None)
        roles = (md or {}).get("roles", [])
        check("Match Day lists four roles", len(roles) == 4)
        by_name = {r.get("role_name"): r for r in roles}
        check("Umpire role gates on Umpire Accreditation",
              by_name.get("Umpire", {}).get("required_qualification_type_id") == str(Q_ACC))
        check("Scorer role gates on nothing",
              by_name.get("Scorer", {}).get("required_qualification_type_id") is None)
        check("Umpire role is not paid", by_name.get("Umpire", {}).get("is_paid") is False)
        check("Bar Supervisor role in Match Day is paid", by_name.get("Bar Supervisor", {}).get("is_paid") is True)

    print("\n=== generation copies each pattern's role onto its shifts ===")
    async with Session() as db:
        await svc.reset_week(db, CLUB, LEGACY_WEEK)  # regenerate from every pattern
        await db.commit()
    async with Session() as db:
        shifts = await svc._shift_rows(db, LEGACY_WEEK)
    def _one(role_id, area_id=None):
        return next((s for s in shifts if s.get("role_id") == str(role_id) and (area_id is None or s.get("area_id") == str(area_id))), None)
    ump = _one(UMPIRE); sco = _one(SCORER); barmd = _one(BAR, MATCHDAY); barleg = _one(BAR, LEGACY_AREA)
    check("an Umpire shift was generated with its role", ump is not None)
    check("Umpire shift carries the Umpire qualification", (ump or {}).get("required_qualification_type_id") == str(Q_ACC))
    check("Umpire shift is unpaid", (ump or {}).get("is_paid") is False)
    check("a Scorer shift was generated", sco is not None)
    check("Scorer shift needs no qualification", (sco or {}).get("required_qualification_type_id") is None)
    check("a paid Bar shift sits in the SAME Match Day area", barmd is not None)
    check("that Bar shift is paid though the Scorer beside it is not", (barmd or {}).get("is_paid") is True)
    check("the legacy area's Bar shift is paid too", (barleg or {}).get("is_paid") is True)

    print("\n=== the qualification block is the shift's role, not the area's ===")
    async with Session() as db:
        cands = {c["member_id"]: c for c in await svc.candidates(db, CLUB)}
        settings = await svc.get_settings(db, CLUB)
        areas = {a["id"]: a for a in await svc.list_areas(db, CLUB)}
    md_area = areas.get(str(MATCHDAY), {})
    def _res(shift, member):
        return svc.check_assignment(md_area, shift, cands[str(member)], shifts, settings)
    if ump and sco:
        rc_ump = _res(ump, CAND_C)
        check("no accreditation is BLOCKED for the Umpire shift", bool(rc_ump["blocks"]))
        rc_sco = _res(sco, CAND_C)
        check("the SAME person is NOT blocked for the Scorer shift", not rc_sco["blocks"])
        ra_ump = _res(ump, CAND_A)
        check("an accredited umpire is not blocked", not ra_ump["blocks"])
        check("an accredited umpire draws no role warning", not any("role" in w for w in ra_ump["warns"]))
        rd_ump = _res(ump, CAND_D)
        check("accredited but not an umpire: allowed", not rd_ump["blocks"])
        check("accredited but not an umpire: warned about the role", any("Umpire role" in w for w in rd_ump["warns"]))

    print("\n=== shortages bucket by the shift's role ===")
    async with Session() as db:
        sh = await svc.role_shortages(db, CLUB, weeks=4)
    by_role = {r.get("role_title"): r for r in sh.get("roles", [])}
    check("Umpire appears as its own shortage bucket", "Umpire" in by_role)
    check("Scorer appears as its own shortage bucket (not folded into Umpire)", "Scorer" in by_role)
    check("the Umpire bucket counts only the two umpire shifts", (by_role.get("Umpire", {}) or {}).get("open_shifts") == 2)

    print("\n=== paid vs volunteer follows the role, in hours_summary ===")
    async with Session() as db:
        s2 = await svc._shift_rows(db, LEGACY_WEEK)
        bar_shift = next((s for s in s2 if s.get("role_id") == str(BAR) and s.get("area_id") == str(MATCHDAY)), None)
        sco_shift = next((s for s in s2 if s.get("role_id") == str(SCORER)), None)
        rp = await svc.assign(db, CLUB, LEGACY_WEEK, bar_shift["id"], str(CAND_E)) if bar_shift else {"ok": False}
        rs = await svc.assign(db, CLUB, LEGACY_WEEK, sco_shift["id"], str(CAND_B)) if sco_shift else {"ok": False}
        await db.commit()
        check("a bar-staff member is rosterable to the paid shift", bool(rp.get("ok")))
        check("a scorer is rosterable to the volunteer shift", bool(rs.get("ok")))
        hs = await svc.hours_summary(db, CLUB, start=NEXT_MON, end=NEXT_MON + timedelta(days=6))
    totals = hs.get("totals", {})
    check("paid hours are counted as paid", (totals.get("rostered_paid") or 0) > 0)
    check("volunteer hours are counted as volunteer", (totals.get("rostered_volunteer") or 0) > 0)

    print("\n=== the shipped write functions ===")
    async with Session() as db:
        wired = await caught("create_area accepts a role palette",
                             lambda: svc.create_area(db, CLUB, name="Wired Area", roles=[{"role_id": str(UMPIRE), "required_qualification_type_id": str(Q_ACC)}]))
        if wired:
            await db.commit()
            areas = await svc.list_areas(db, CLUB)
            wa = next((a for a in areas if a["id"] == str(wired)), None)
            check("the created area carries its one role", len((wa or {}).get("roles", [])) == 1)
    async with Session() as db:
        pat = await caught("add_pattern accepts a role",
                           lambda: svc.add_pattern(db, CLUB, MATCHDAY, day_of_week=3, start_time=18, end_time=20, headcount=1, role_id=str(TEAM_MGR)))
        if pat:
            await db.commit()
            got = (await db.execute(text("SELECT role_id FROM roster_shift_patterns WHERE id=:p"), {"p": pat})).scalar()
            check("the pattern stored its role", str(got) == str(TEAM_MGR))

    print("\n=== removing a role from the palette ===")
    async with Session() as db:
        await caught("update_area rewrites the palette",
                     lambda: svc.update_area(db, CLUB, MATCHDAY, roles=[{"role_id": str(UMPIRE), "required_qualification_type_id": str(Q_ACC)},
                                                                        {"role_id": str(TEAM_MGR), "required_qualification_type_id": None}]))
        await db.commit()
        left = (await db.execute(text("SELECT COUNT(*) FROM roster_area_roles WHERE area_id=:a"), {"a": MATCHDAY})).scalar()
        check("the palette now holds the two kept roles", left == 2)

    print("\n=== cross-club scoping ===")
    async with Session() as db:
        ours = {a["id"] for a in await svc.list_areas(db, CLUB)}
        theirs = {a["id"] for a in await svc.list_areas(db, OTHER)}
    check("another club's area is not in ours", str(OTHER_AREA) not in ours)
    check("that area is in the other club's own list", str(OTHER_AREA) in theirs)

    print(f"\n{'='*54}\n  {PASS} passed, {FAIL} failed")
    if FAILURES:
        print("  — failures —")
        for f in FAILURES:
            print("   ", f)
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
