"""Every club admin, on one internal BetterComms list.

Asked for: a club admin should land on BetterCricket's internal contact list the
moment they become one — a self-serve registration, a super admin creating a
club and naming its primary admin, a primary admin being reassigned, an admin
added to a club that already exists — plus a script that backfills everyone who
was already an admin.

This runs the SHIPPED service, route bodies and script logic (imported, nothing
retyped) against a real Postgres.

    python -m verification.verify_admin_contact_list
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
    "postgresql+asyncpg://postgres@127.0.0.1:55432/verify_admin_list",
)
# MUST be set before app.models.db is imported: async_session_maker is built at
# import time from settings, and run_sync opens its own session through it. The
# same trap the instructional-videos note documents for VIDEO_STORAGE_DIR.
os.environ["DATABASE_URL"] = DB_URL

from sqlalchemy import func, select, text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.models.db import (  # noqa: E402
    Base, ClubMembership, CommsContact, CommsList, CommsListMember, EmailSuppression,
    MarketingClub, Organisation, OrgModuleSubscription, User,
)
from app.services import admin_contact_list as acl  # noqa: E402
from app.routers.comms import _send_vars  # noqa: E402

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} — {detail}")
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  ({detail})'}")


async def listed_emails(db, outreach_id) -> set:
    """Whoever is actually ON the list, by address."""
    return set((await db.execute(
        select(CommsContact.email)
        .join(CommsListMember, CommsListMember.contact_id == CommsContact.id)
        .join(CommsList, CommsList.id == CommsListMember.list_id)
        .where(CommsList.organisation_id == outreach_id, CommsList.name == acl.LIST_NAME)
    )).scalars().all())


async def contact_emails(db, outreach_id) -> set:
    return set((await db.execute(select(CommsContact.email).where(
        CommsContact.organisation_id == outreach_id))).scalars().all())


async def main() -> int:
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as db:
        print("\n── No outreach org is a configuration state, not a failure ────")
        club0 = Organisation(id=uuid.uuid4(), name="Early CC", slug="early-cc")
        db.add(club0)
        await db.flush()
        u0 = User(id=uuid.uuid4(), username="early", email="early@example.com")
        db.add(u0)
        await db.flush()
        db.add(ClubMembership(club_id=club0.id, user_id=u0.id, role="club_admin",
                              is_primary_admin=True))
        await db.commit()
        res = await acl.sync(db)
        check("with no outreach org designated it no-ops", res["status"] == "no_outreach_org", res)
        check("...and writes no list", (await db.scalar(select(func.count()).select_from(CommsList))) == 0)

        # ── The platform ────────────────────────────────────────────────────
        outreach = Organisation(id=uuid.uuid4(), name="BetterCricket", slug="bettercricket",
                                is_marketing_outreach=True)
        db.add(outreach)
        await db.flush()

        clubs, users = {}, {}

        async def make_club(label, *, archived=False, directory=True, trial_days=None):
            org = Organisation(id=uuid.uuid4(), name=f"{label} CC", slug=f"{label}-cc",
                               archived_at=dt.datetime.now(dt.timezone.utc) if archived else None)
            db.add(org)
            await db.flush()
            clubs[label] = org
            if directory:
                db.add(MarketingClub(id=uuid.uuid4(), name=f"{label} CC",
                                     grassroots_guid=f"guid-{label}", existing_org_id=org.id,
                                     utm_code=f"{label}-cc", state="WA"))
            if trial_days is not None:
                db.add(OrgModuleSubscription(
                    id=uuid.uuid4(), organisation_id=org.id, module_key="core", status="trial",
                    trial_ends_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=trial_days)))
            await db.flush()
            return org

        async def make_admin(label, org, *, role="club_admin", primary=False, email=None,
                             display_name=None):
            u = User(id=uuid.uuid4(), username=label, email=email,
                     display_name=display_name or f"{label.title()} Person")
            db.add(u)
            await db.flush()
            db.add(ClubMembership(club_id=org.id, user_id=u.id, role=role,
                                  is_primary_admin=primary))
            await db.flush()
            users[label] = u
            return u

        applecross = await make_club("applecross", trial_days=6.5)
        wycombe = await make_club("wycombe")
        nodir = await make_club("nodir", directory=False)
        gone = await make_club("gone", archived=True)

        await make_admin("primary", applecross, primary=True, email="primary@example.com",
                         display_name="Jack Barendse")
        await make_admin("second", applecross, email="second@example.com")
        await make_admin("wycombe-primary", wycombe, primary=True, email="wp@example.com")
        await make_admin("nodir-admin", nodir, primary=True, email="nodir@example.com")
        await make_admin("archived-admin", gone, primary=True, email="archived@example.com")
        await make_admin("noemail", wycombe, email=None)
        await make_admin("member", wycombe, role="club_member", email="member@example.com")
        await make_admin("staff", outreach, role="super_admin", email="staff@example.com")
        await make_admin("rep", outreach, role="sales", email="rep@example.com")
        await db.commit()

        print("\n── Who lands on the list, and who does not ────────────────────")
        res = await acl.sync(db)
        await db.commit()
        got = await listed_emails(db, outreach.id)
        check("the primary club admin is on it", "primary@example.com" in got, sorted(got))
        check("an ordinary club admin is too", "second@example.com" in got, sorted(got))
        check("a second club's primary admin as well", "wp@example.com" in got, sorted(got))
        check("a club with no directory row still gets its admin on",
              "nodir@example.com" in got, sorted(got))
        check("a club_member is not an admin", "member@example.com" not in got, sorted(got))
        check("BetterCricket's own super admin is not a club admin",
              "staff@example.com" not in got, sorted(got))
        check("nor is a sales rep", "rep@example.com" not in got, sorted(got))
        check("an archived club's admin is left out",
              "archived@example.com" not in got, sorted(got))
        check("an admin who predates the outreach org is picked up by the backfill",
              "early@example.com" in got, sorted(got))
        check("exactly those five and nobody else",
              got == {"early@example.com", "primary@example.com", "second@example.com",
                      "wp@example.com", "nodir@example.com"}, sorted(got))
        check("an admin with no email is reported, not silently dropped",
              res["no_email"] == ["noemail"], res["no_email"])

        print("\n── The list itself ────────────────────────────────────────────")
        lst = (await db.execute(select(CommsList).where(
            CommsList.organisation_id == outreach.id))).scalars().all()
        check("exactly one list, in the outreach org", len(lst) == 1, len(lst))
        check("named as asked", lst[0].name == "Super Admin User Contact List", lst[0].name)
        check("marked auto with an origin that says what made it",
              lst[0].source == "auto" and lst[0].origin == "Club Admin Users",
              f"{lst[0].source}/{lst[0].origin}")
        check("the contacts carry a source of their own",
              all(c == "admin" for c in (await db.execute(select(CommsContact.source).where(
                  CommsContact.organisation_id == outreach.id))).scalars().all()))

        print("\n── Running it again changes nothing ───────────────────────────")
        before_c = await db.scalar(select(func.count()).select_from(CommsContact))
        before_m = await db.scalar(select(func.count()).select_from(CommsListMember))
        res2 = await acl.sync(db)
        await db.commit()
        check("no contact is created twice",
              (await db.scalar(select(func.count()).select_from(CommsContact))) == before_c,
              before_c)
        check("no list membership is created twice",
              (await db.scalar(select(func.count()).select_from(CommsListMember))) == before_m,
              before_m)
        check("and it says so", res2["contacts_added"] == 0 and res2["list_added"] == 0, res2)
        check("no second list is minted",
              (await db.scalar(select(func.count()).select_from(CommsList))) == 1)

        print("\n── An opt-out is never overridden ─────────────────────────────")
        second = (await db.execute(select(CommsContact).where(
            CommsContact.email == "second@example.com"))).scalars().one()
        second.subscribed = False
        await db.execute(text("DELETE FROM comms_list_members WHERE contact_id = :c"),
                         {"c": second.id})
        wp = (await db.execute(select(CommsContact).where(
            CommsContact.email == "wp@example.com"))).scalars().one()
        wp.bounced = True
        await db.execute(text("DELETE FROM comms_list_members WHERE contact_id = :c"),
                         {"c": wp.id})
        db.add(EmailSuppression(email="nodir@example.com", reason="complaint"))
        await db.execute(text("DELETE FROM comms_list_members WHERE contact_id IN "
                              "(SELECT id FROM comms_contacts WHERE email = 'nodir@example.com')"))
        await db.commit()
        res3 = await acl.sync(db)
        await db.commit()
        got = await listed_emails(db, outreach.id)
        check("an unsubscribed admin is not put back on the list",
              "second@example.com" not in got, sorted(got))
        check("a bounced one is not either", "wp@example.com" not in got, sorted(got))
        check("nor is one on the global suppression list",
              "nodir@example.com" not in got, sorted(got))
        check("they are counted rather than passing unnoticed", res3["suppressed"] == 3, res3)
        check("the still-subscribed admins stay on",
              got == {"early@example.com", "primary@example.com"}, sorted(got))
        check("their contact rows survive — the opt-out is not undone",
              {"second@example.com", "wp@example.com"} <= await contact_emails(db, outreach.id))
        second.subscribed = True
        wp.bounced = False
        await db.execute(text("DELETE FROM email_suppressions"))
        await db.commit()
        await acl.sync(db)
        await db.commit()
        check("resubscribing puts them back on the next run",
              len(await listed_emails(db, outreach.id)) == 5,
              sorted(await listed_emails(db, outreach.id)))

        print("\n── What the contact carries ───────────────────────────────────")
        c = (await db.execute(select(CommsContact).where(
            CommsContact.email == "primary@example.com"))).scalars().one()
        check("the admin's own name, not one guessed from the address",
              c.name == "Jack Barendse", c.name)
        mc = (await db.execute(select(MarketingClub).where(
            MarketingClub.existing_org_id == applecross.id))).scalars().one()
        check("linked to the club's Clubs Directory row", c.marketing_club_id == mc.id)
        v = await _send_vars(db, c, mc)
        check("so {{club}} resolves to their club", v["club"] == "applecross CC", v.get("club"))
        check("and the trial countdown resolves too — the whole reason to link it",
              v["trial_days_left"] == "6", v.get("trial_days_left"))
        nod = (await db.execute(select(CommsContact).where(
            CommsContact.email == "nodir@example.com"))).scalars().one()
        check("a club with no directory row leaves the link empty rather than guessing",
              nod.marketing_club_id is None)

        c.name = "Typed By Hand"
        await db.commit()
        await acl.sync(db)
        await db.commit()
        await db.refresh(c)
        check("a name a super admin typed is never clobbered by a later run",
              c.name == "Typed By Hand", c.name)

        print("\n── Scoping, sharing an address, and the dry run ───────────────")
        newclub = await make_club("newclub")
        await make_admin("newadmin", newclub, primary=True, email="new@example.com")
        await make_admin("dupe-a", newclub, email="shared@example.com")
        await make_admin("dupe-b", applecross, email="SHARED@example.com")
        await db.commit()

        dry = await acl.sync(db, apply=False)
        check("a dry run reports what it would add", dry["contacts_added"] == 2, dry)
        check("...and writes nothing",
              "new@example.com" not in await contact_emails(db, outreach.id))
        # The projection has to count a contact that does not exist yet, or a run
        # that would add everybody reports "0 to add" and reads as nothing to do.
        real = await acl.sync(db, apply=True)
        await db.commit()
        check("the dry run's figures are what applying actually does",
              (dry["contacts_added"], dry["list_added"], dry["suppressed"])
              == (real["contacts_added"], real["list_added"], real["suppressed"]),
              f"dry={dry} real={real}")
        check("...and it was a real number, not zero on both sides",
              real["list_added"] > 0, real)

        await acl.sync(db, club_id=newclub.id)
        await db.commit()
        got = await listed_emails(db, outreach.id)
        check("syncing one club adds its admin", "new@example.com" in got, sorted(got))
        check("...and only its own — the other club's new admin waits for its turn",
              "shared@example.com" in got, sorted(got))
        n_shared = await db.scalar(select(func.count()).select_from(CommsContact).where(
            CommsContact.email == "shared@example.com"))
        check("two admins sharing an address are one contact", n_shared == 1, n_shared)

        print("\n── An existing list is adopted, never duplicated ──────────────")
        async with Session() as db2:
            other = Organisation(id=uuid.uuid4(), name="Other Outreach", slug="other-outreach")
            db2.add(other)
            await db2.flush()
            hand = CommsList(organisation_id=other.id, name=acl.LIST_NAME,
                             source="manual", origin=None)
            db2.add(hand)
            await db2.commit()
            got_list = await acl.ensure_list(db2, other.id)
            await db2.commit()
            check("a list a person made by hand is adopted", got_list.id == hand.id)
            check("...and left as theirs, not relabelled auto",
                  got_list.source == "manual" and got_list.origin is None,
                  f"{got_list.source}/{got_list.origin}")
            check("no second list beside it",
                  (await db2.scalar(select(func.count()).select_from(CommsList).where(
                      CommsList.organisation_id == other.id))) == 1)

        print("\n── The shipped route bodies ───────────────────────────────────")
        # super_set_primary_admin: hand the role to the second admin and confirm
        # the hook lands them on the list through the real route body.
        from app.routers.club_admin import PrimaryAdminSet, super_set_primary_admin
        await db.execute(text("DELETE FROM comms_list_members"))
        await db.execute(text("DELETE FROM comms_contacts"))
        await db.commit()
        await super_set_primary_admin(
            str(applecross.id), PrimaryAdminSet(user_id=str(users["second"].id)),
            users["staff"], db)
        await asyncio.gather(*list(acl._tasks))
        async with Session() as db3:
            got = await listed_emails(db3, outreach.id)
        check("assigning a primary admin puts that club's admins on the list",
              {"primary@example.com", "second@example.com"} <= got, sorted(got))
        check("...and only that club's — the hook is scoped",
              "wp@example.com" not in got, sorted(got))
        check("the transfer itself still happened",
              (await db.execute(select(ClubMembership.is_primary_admin).where(
                  ClubMembership.user_id == users["second"].id))).scalar_one() is True)

        # create_user: a super admin adds a club_admin to an existing club. The
        # form carries no email, so the hook correctly finds nobody to add yet —
        # and patch_user is what completes them. Both run as the real route body,
        # with no explicit sync alongside to mask a hook that never fired.
        from app.routers.club_admin import UserCreate, UserUpdate, create_user, patch_user
        made = await create_user(
            UserCreate(username="freshadmin", password="Sup3rSecret!", role="club_admin",
                       club_id=str(wycombe.id), display_name="Fresh Admin"),
            users["staff"], db)
        await asyncio.gather(*list(acl._tasks))
        async with Session() as db4:
            got = await listed_emails(db4, outreach.id)
        check("an admin created with no address on file is not invented as a contact",
              not any(e.startswith("freshadmin") for e in got), sorted(got))
        await patch_user(made["id"], UserUpdate(email="fresh@example.com"),
                         users["staff"], db)
        await asyncio.gather(*list(acl._tasks))
        async with Session() as db4:
            got = await listed_emails(db4, outreach.id)
        check("an admin added to an existing club lands on the list once they have one",
              "fresh@example.com" in got, sorted(got))

        # patch_user again: promoting an existing club_member to club_admin.
        await patch_user(str(users["member"].id), UserUpdate(role="club_admin"),
                         users["staff"], db)
        await asyncio.gather(*list(acl._tasks))
        async with Session() as db5:
            got = await listed_emails(db5, outreach.id)
        check("promoting a club_member to club admin puts them on the list",
              "member@example.com" in got, sorted(got))

        print("\n── The hooks are wired where they were asked for ──────────────")
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        src = {f: open(os.path.join(root, "app/routers", f)).read() for f in (
            "self_serve_trial.py", "club_admin.py", "organisations.py", "sales_workspace.py")}
        check("self-serve registration syncs", "queue_admin_contact_sync(org.id)" in src["self_serve_trial.py"])
        check("super admin creating a club syncs", "_queue_admin_contact_sync(org.id)" in src["club_admin.py"])
        check("assigning / transferring the primary admin syncs",
              src["club_admin.py"].count("_queue_admin_contact_sync(") >= 4,
              src["club_admin.py"].count("_queue_admin_contact_sync("))
        check("a club onboarding itself syncs", "queue_admin_contact_sync(org.id)" in src["organisations.py"])
        check("nominating a primary admin from the Sales Workspace syncs",
              "_admin_contact_sync" in src["sales_workspace.py"])
        # Every hook must sit AFTER a commit inside its own function: the task
        # reads its own session, so one fired mid-transaction would find no
        # membership and silently do nothing. Checked back to the top of the
        # ENCLOSING function rather than a fixed window, so a hook placed after a
        # long except block still reads correctly.
        misplaced = []
        for fname, body in src.items():
            lines = body.splitlines()
            for i, line in enumerate(lines):
                if ("admin_contact_sync(" not in line or line.lstrip().startswith(("def ", "from ", "import "))
                        or "def _queue" in line):
                    continue
                start = 0
                for j in range(i, -1, -1):
                    if lines[j].startswith(("async def ", "def ")):
                        start = j
                        break
                enclosing = "\n".join(lines[start:i])
                if "commit()" not in enclosing and "background_tasks.add_task" not in line:
                    misplaced.append(f"{fname}:{i + 1} {line.strip()}")
        check("every hook fires after its own commit, never inside the transaction",
              not misplaced, misplaced)

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print(f"  FAILED: {f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
