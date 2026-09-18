"""Verification for the rename-collision fix on the Areas & Roles catalogue,
against a real Postgres.

Reported: editing a role and renaming it to a title another role already holds
(e.g. the committee "Bar Manager", which never shows in the non-committee Roles
list) returned "Internal Server Error" — an unhandled UniqueViolationError on
uq_club_roles_org_title at commit, a 500. The create path already refused a
duplicate with a friendly 422; the four update paths did not.

Exercises the SHIPPED service (services/roles_activities.py) AND the real route
bodies (routers/roles_activities.py), never a re-implementation. The questions
worth the harness, because none can be read off the code alone:

  * THE REPORTED 500 IS NOW A 422. Renaming a role to a title held by another
    role of the same org — including a committee role that isn't in this list —
    is refused with a friendly message instead of blowing up at commit.

  * ALL FOUR CATALOGUES. The same latent bug lived in role types, activities and
    activity types; each is refused now.

  * THE SESSION SURVIVES THE REFUSAL. The check runs BEFORE the setattr, so the
    transaction is never dirtied — a clean rename right after works, where the
    old 500 left an aborted transaction.

  * A CLEAN RENAME, A CASE-ONLY CHANGE, A CROSS-CLUB NAME AND A DRAG-REORDER all
    still go through — the guard must not refuse a legitimate edit.

Run:      DATABASE_URL=postgresql+asyncpg://... python verify_role_rename_collision.py
Control:  git stash push backend/app/services/roles_activities.py backend/app/routers/roles_activities.py
          DATABASE_URL=... python verify_role_rename_collision.py   # collision checks fail
          git stash pop
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import (
    Base, Organisation, User, ClubRole, ClubRoleType, ClubActivity, ClubActivityType,
)
from app.services import roles_activities as svc
from app.routers import roles_activities as rt

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


async def raises_value(factory):
    """True iff the shipped service call raises ValueError. A control (old code)
    that never checks returns None, so this reads False and the check FAILs —
    rather than crashing the run."""
    try:
        await factory()
        return False
    except ValueError:
        return True
    except Exception as e:  # noqa: BLE001 — any other error is not the friendly refusal
        return f"raised {type(e).__name__}"


async def http_status(factory):
    """The HTTP status a real route body raises, or a marker if it raises
    something else (the old code raises IntegrityError at commit, not a 4xx)."""
    try:
        await factory()
        return "no-error"
    except HTTPException as e:
        return e.status_code
    except Exception as e:  # noqa: BLE001
        return f"raised {type(e).__name__}"


# ── ids ──────────────────────────────────────────────────────────────────────
CLUB = uuid.uuid4(); OTHER = uuid.uuid4()
USER = uuid.uuid4()
GK = uuid.uuid4(); BAR = uuid.uuid4(); TM = uuid.uuid4(); NETS = uuid.uuid4()
RT_VOL = uuid.uuid4(); RT_COACH = uuid.uuid4()
AT_MATCH = uuid.uuid4(); AT_GROUND = uuid.uuid4()
ACT_SCORE = uuid.uuid4(); ACT_UMP = uuid.uuid4()
OTHER_BAR = uuid.uuid4()


async def build_schema():
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)


async def seed(db):
    db.add_all([
        Organisation(id=CLUB, name="Applecross Cricket Club", slug="acc-rn", subscription_status="active", module_overrides=[]),
        Organisation(id=OTHER, name="High Wycombe CC", slug="hwcc-rn", subscription_status="active", module_overrides=[]),
        User(id=USER, username="coach-rn", email="c@rn.com", password_hash="x"),
    ])
    await db.flush()
    db.add_all([
        # "Bar Manager" is a committee role — the exact reported case: it never
        # shows in the non-committee Roles list, yet the name is taken.
        ClubRole(id=BAR, organisation_id=CLUB, title="Bar Manager", is_committee=True),
        ClubRole(id=GK, organisation_id=CLUB, title="Groundskeeper"),
        ClubRole(id=TM, organisation_id=CLUB, title="Team Manager"),
        # A throwaway role for the case-only-change check, so the pristine "Bar
        # Manager" collision target above is never re-cased (an exact-case DB
        # constraint would otherwise stop colliding in the control run).
        ClubRole(id=NETS, organisation_id=CLUB, title="Nets Manager"),
        ClubRoleType(id=RT_VOL, organisation_id=CLUB, name="Volunteer", category="volunteer"),
        ClubRoleType(id=RT_COACH, organisation_id=CLUB, name="Coach", category="volunteer"),
        ClubActivityType(id=AT_MATCH, organisation_id=CLUB, name="Match Day"),
        ClubActivityType(id=AT_GROUND, organisation_id=CLUB, name="Ground & Equipment"),
        ClubActivity(id=ACT_SCORE, organisation_id=CLUB, title="Scoring"),
        ClubActivity(id=ACT_UMP, organisation_id=CLUB, title="Umpiring"),
        # Another club owns a "Bar Manager" role — renaming ours to a name only
        # THEY hold must be allowed (org-scoped uniqueness).
        ClubRole(id=OTHER_BAR, organisation_id=OTHER, title="Bar Manager (Other)"),
    ])
    await db.flush()
    await db.commit()


async def main():
    await build_schema()
    async with Session() as db:
        await seed(db)

    club = None
    async with Session() as db:
        club = await db.get(Organisation, CLUB)

    print("\n─ service: update_role ─")
    # 1. reported case — collide with the committee "Bar Manager"
    async with Session() as db:
        r = await db.get(ClubRole, GK)
        got = await raises_value(lambda: svc.update_role(db, r, title="Bar Manager"))
        check("rename role → existing committee title raises ValueError", got, True)
    # 2. friendly message
    async with Session() as db:
        r = await db.get(ClubRole, GK)
        msg = None
        try:
            await svc.update_role(db, r, title="Bar Manager")
        except ValueError as e:
            msg = str(e)
        check("message names it already exists", bool(msg and "already exists" in msg), True)
    # 3. case-insensitive collision
    async with Session() as db:
        r = await db.get(ClubRole, GK)
        got = await raises_value(lambda: svc.update_role(db, r, title="bar MANAGER"))
        check("case-insensitive collision raises", got, True)
    # 4. clean rename goes through and persists
    async with Session() as db:
        r = await db.get(ClubRole, GK)
        await svc.update_role(db, r, title="Head Groundskeeper")
        await db.commit()
    async with Session() as db:
        r = await db.get(ClubRole, GK)
        check("clean rename persists", r.title, "Head Groundskeeper")
    # 5. case-only change of the row itself is allowed (no other row collides)
    async with Session() as db:
        r = await db.get(ClubRole, NETS)
        got = await raises_value(lambda: svc.update_role(db, r, title="NETS MANAGER"))
        check("case-only change of the same row does not raise", got, False)
        await db.commit()
    async with Session() as db:
        r = await db.get(ClubRole, NETS)
        check("case-only change persists the new casing", r.title, "NETS MANAGER")
    # 6. blank title
    async with Session() as db:
        r = await db.get(ClubRole, GK)
        got = await raises_value(lambda: svc.update_role(db, r, title="   "))
        check("blank title raises", got, True)
    # 7. cross-club name allowed
    async with Session() as db:
        r = await db.get(ClubRole, TM)
        got = await raises_value(lambda: svc.update_role(db, r, title="Bar Manager (Other)"))
        check("renaming to a title only another club holds is allowed", got, False)
        await db.rollback()
    # 8. whitespace stripped on store
    async with Session() as db:
        r = await db.get(ClubRole, TM)
        await svc.update_role(db, r, title="  Grounds Team Manager  ")
        await db.commit()
    async with Session() as db:
        r = await db.get(ClubRole, TM)
        check("title is stripped on store", r.title, "Grounds Team Manager")

    print("\n─ service: other three catalogues ─")
    async with Session() as db:
        t = await db.get(ClubRoleType, RT_COACH)
        check("role type rename collision raises", await raises_value(lambda: svc.update_role_type(db, t, name="Volunteer")), True)
    async with Session() as db:
        t = await db.get(ClubRoleType, RT_COACH)
        await svc.update_role_type(db, t, name="Coaching")
        await db.commit()
    async with Session() as db:
        t = await db.get(ClubRoleType, RT_COACH)
        check("role type clean rename persists", t.name, "Coaching")
    async with Session() as db:
        a = await db.get(ClubActivity, ACT_UMP)
        check("activity rename collision raises", await raises_value(lambda: svc.update_activity(db, a, title="Scoring")), True)
    async with Session() as db:
        t = await db.get(ClubActivityType, AT_GROUND)
        check("activity type rename collision raises", await raises_value(lambda: svc.update_activity_type(db, t, name="Match Day")), True)

    print("\n─ route bodies: 500 → 422 ─")
    # 14/15. the reported endpoint — a colliding rename is a 422, not a 500
    async with Session() as db:
        status = await http_status(lambda: rt.update_role(
            role_id=str(GK), data=rt.RoleUpsert(title="Bar Manager"), _=None, club=club, db=db))
        check("PATCH /roles colliding title → 422 (was 500)", status, 422)
    async with Session() as db:
        detail = None
        try:
            await rt.update_role(role_id=str(GK), data=rt.RoleUpsert(title="Bar Manager"), _=None, club=club, db=db)
        except HTTPException as e:
            detail = e.detail
        except Exception:  # noqa: BLE001 — old code raises IntegrityError; report, don't crash the run
            pass
        check("route 422 detail names it already exists", bool(detail and "already exists" in detail), True)
    # 16/17. session survives the refusal — a clean rename right after commits. In
    # the old code the refusal is an aborted-transaction IntegrityError, so the
    # follow-up rename can't land and the persistence check reports a FAIL rather
    # than crashing (both calls are broadly guarded).
    async with Session() as db:
        for title in ("Bar Manager", "Turf Manager"):
            try:
                await rt.update_role(role_id=str(GK), data=rt.RoleUpsert(title=title), _=None, club=club, db=db)
            except Exception:  # noqa: BLE001
                pass
    async with Session() as db:
        r = await db.get(ClubRole, GK)
        check("clean rename via route after a refusal persists", r.title, "Turf Manager")
    # 18-20. the other three endpoints map ValueError → 422 too
    async with Session() as db:
        status = await http_status(lambda: rt.update_role_type(
            type_id=str(RT_VOL), data=rt.TypeUpsert(name="Coaching"), _=None, club=club, db=db))
        check("PATCH /role-types colliding → 422", status, 422)
    async with Session() as db:
        status = await http_status(lambda: rt.update_activity(
            activity_id=str(ACT_UMP), data=rt.ActivityUpsert(title="Scoring"), _=None, club=club, db=db))
        check("PATCH /activities colliding → 422", status, 422)
    async with Session() as db:
        status = await http_status(lambda: rt.update_activity_type(
            type_id=str(AT_MATCH), data=rt.TypeUpsert(name="Ground & Equipment"), _=None, club=club, db=db))
        check("PATCH /activity-types colliding → 422", status, 422)
    # 21. a drag-reorder PATCH (sort_order only, no title) still works
    async with Session() as db:
        await rt.update_role(role_id=str(BAR), data=rt.RoleUpsert(sort_order=7), _=None, club=club, db=db)
    async with Session() as db:
        r = await db.get(ClubRole, BAR)
        check("sort-order-only PATCH (no title) still works", r.sort_order, 7)

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAILURES:
        print("\nFAILURES:")
        for f in FAILURES:
            print("  -", f)
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
