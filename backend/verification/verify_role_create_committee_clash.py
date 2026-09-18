"""A role that clashes with a hidden committee role explains where it lives.

Reported off Areas & Roles → Roles: adding "Bar Manager" is refused as already
existing, but no Bar Manager is shown in the list. It IS there — the committee
starter pack seeds "Bar Manager" as a COMMITTEE role (is_committee=True), and
the Roles list hides every committee-classified role (its is_committee flag OR a
committee-category type) because those are managed as positions on the Committee
screen. The uniqueness check in create_role spans EVERY role, so the clash reads
as an error naming a role that appears nowhere on this list.

This exercises the SHIPPED create_role over a real Postgres (the ClubRole /
ClubRoleType tables built from the ORM models), asserting:
  * an active committee role (is_committee flag) clashing with a new non-committee
    role of the same name → the explanatory "managed on the Committee screen"
    message, not the bare "already exists";
  * the same when the role is committee-hidden by its role TYPE'S category rather
    than its own flag;
  * a genuine VISIBLE (non-committee) duplicate → the bare message, unchanged;
  * an ARCHIVED clash is still reactivated, never an error (unchanged behaviour);
  * a committee caller (is_committee=True) clashing with a committee role → the
    bare message, since it is not hidden from the caller's own list;
  * the RENAME path (update_role) shares the one helper, so renaming a visible
    role ONTO a hidden committee role names the Committee screen too, while a
    rename onto a visible duplicate keeps the bare message.

Control run: with the committee-aware branch of _role_clash_message neutered,
5 of the 10 fail — every create and rename check that should name the Committee
screen reads the bare "already exists" message the customer saw.

  DATABASE_URL=postgresql+asyncpg://cricket:cricket@/betterstats?host=/tmp&port=55432 \
    python -m verification.verify_role_create_committee_clash
"""
import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.models.db import ClubRole, ClubRoleType
from app.services import roles_activities as svc

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'  ok  ' if cond else ' FAIL '} {name}{'' if cond else '  — ' + str(detail)}")


async def _clash_message(session, org_id, title, *, is_committee=False):
    """Run the shipped create_role and return the ValueError message (or None)."""
    try:
        await session.begin_nested()
        await svc.create_role(session, org_id, title=title, is_committee=is_committee)
        await session.rollback()
        return None
    except ValueError as e:
        await session.rollback()
        return str(e)


async def main():
    url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://cricket:cricket@/betterstats?host=/tmp&port=55432",
    )
    engine = create_async_engine(url)
    org = uuid.uuid4()
    async with engine.begin() as conn:
        # A stand-in organisations table for the FK targets, seeded with one row.
        from sqlalchemy import text as _t
        await conn.execute(_t("CREATE TABLE IF NOT EXISTS organisations (id UUID PRIMARY KEY)"))
        await conn.execute(_t("INSERT INTO organisations (id) VALUES (:id) ON CONFLICT DO NOTHING"),
                           {"id": org})
        for tbl in (ClubRoleType.__table__, ClubRole.__table__):
            await conn.run_sync(tbl.create, checkfirst=True)

    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as s:
        # A committee-category role type, and a plain volunteer one.
        committee_type_id, volunteer_type_id = uuid.uuid4(), uuid.uuid4()
        committee_type = ClubRoleType(id=committee_type_id, organisation_id=org,
                                      name="Committee Member", category="committee")
        volunteer_type = ClubRoleType(id=volunteer_type_id, organisation_id=org,
                                      name="Food & Beverage", category="volunteer")
        s.add_all([committee_type, volunteer_type])
        await s.flush()

        # The seeded committee "Bar Manager": is_committee flag set, committee type.
        s.add(ClubRole(id=uuid.uuid4(), organisation_id=org, title="Bar Manager",
                       role_type_id=committee_type_id, is_committee=True))
        # A role hidden ONLY by its type's category (flag not set).
        s.add(ClubRole(id=uuid.uuid4(), organisation_id=org, title="Grounds Manager",
                       role_type_id=committee_type_id, is_committee=False))
        # A genuine visible, non-committee role.
        s.add(ClubRole(id=uuid.uuid4(), organisation_id=org, title="Canteen Manager",
                       role_type_id=volunteer_type_id, is_committee=False))
        # An archived clash — reactivation must still win over any error.
        s.add(ClubRole(id=uuid.uuid4(), organisation_id=org, title="Photographer",
                       role_type_id=volunteer_type_id, is_committee=False, is_active=False))
        await s.commit()

        # ── The reported case ────────────────────────────────────────────────
        msg = await _clash_message(s, org, "Bar Manager")
        check("a committee-flagged clash names the Committee screen",
              msg is not None and "Committee screen" in msg, msg)
        check("the committee clash does NOT read as a bare 'already exists'",
              msg is not None and msg != 'A role called "Bar Manager" already exists', msg)
        # Case-folded, matching the list's own lower(title) uniqueness.
        msg_lc = await _clash_message(s, org, "bar manager")
        check("the clash is case-insensitive",
              msg_lc is not None and "Committee screen" in msg_lc, msg_lc)

        # ── Hidden by TYPE category alone (flag not set) ─────────────────────
        msg_gm = await _clash_message(s, org, "Grounds Manager")
        check("a committee-category-type clash also names the Committee screen",
              msg_gm is not None and "Committee screen" in msg_gm, msg_gm)

        # ── A genuine visible duplicate — bare message, unchanged ────────────
        msg_visible = await _clash_message(s, org, "Canteen Manager")
        check("a visible duplicate keeps the plain 'already exists' message",
              msg_visible == 'A role called "Canteen Manager" already exists', msg_visible)
        check("a visible duplicate never mentions the Committee screen",
              msg_visible is not None and "Committee screen" not in msg_visible, msg_visible)

        # ── An archived clash reactivates, never errors ──────────────────────
        try:
            await s.begin_nested()
            r = await svc.create_role(s, org, title="Photographer")
            reactivated = r.is_active is True
            await s.rollback()
        except ValueError as e:
            reactivated = False
            await s.rollback()
            print("   (unexpected) ", e)
        check("an archived clash is reactivated rather than refused", reactivated)

        # ── A committee caller clashing with a committee role — bare message ─
        # It is not hidden from the caller's own (committee) list, so the
        # explanatory branch must not fire.
        msg_com = await _clash_message(s, org, "Bar Manager", is_committee=True)
        check("a committee create clashing with a committee role keeps the plain message",
              msg_com == 'A role called "Bar Manager" already exists', msg_com)

        # ── RENAME path shares the same helper (update_role) ─────────────────
        # Renaming the visible "Canteen Manager" onto the hidden committee
        # "Bar Manager" must name the Committee screen too — the same confusion
        # from the other direction.
        async def _rename_message(from_title, new_title, **fields):
            # Re-query the role fully each call so no attribute lazy-loads after a
            # nested rollback (the MissingGreenlet trap).
            role = (await s.execute(
                select(ClubRole).where(ClubRole.organisation_id == org,
                                       func.lower(ClubRole.title) == from_title.lower())
            )).scalars().first()
            try:
                await s.begin_nested()
                await svc.update_role(s, role, title=new_title, **fields)
                await s.rollback()
                return None
            except ValueError as e:
                await s.rollback()
                return str(e)

        msg_rename = await _rename_message("Canteen Manager", "Bar Manager")
        check("renaming a visible role onto a committee role names the Committee screen",
              msg_rename is not None and "Committee screen" in msg_rename, msg_rename)
        # Renaming onto a visible non-committee duplicate keeps the bare message.
        s.add(ClubRole(id=uuid.uuid4(), organisation_id=org, title="Kit Manager",
                       role_type_id=volunteer_type_id, is_committee=False))
        await s.commit()
        msg_rename_visible = await _rename_message("Canteen Manager", "Kit Manager")
        check("renaming onto a visible duplicate keeps the plain message",
              msg_rename_visible == 'A role called "Kit Manager" already exists', msg_rename_visible)

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED:\n  " + "\n  ".join(FAIL))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
