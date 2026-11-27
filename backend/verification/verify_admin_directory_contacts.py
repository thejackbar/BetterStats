"""Every club admin is a Contact on their club's Clubs Directory row (the backfill script).

Asked for: compare every club admin, for every club (trialling, expired, subscribed, paying), with
the contacts already pulled from PlayHQ / Play-Cricket and stored in the Clubs Directory; where the
admin is not one of that club's contacts, store them as one.

This runs the SHIPPED service and the script's own `run` (imported, nothing retyped) against a real
Postgres, and proves, per rule:

  * an email match is left alone (case does not matter) and a full-name match is left alone and
    LISTED, but a first name alone is never an identity;
  * a person who is not a contact is stored with the name, email and mobile on their account,
    with role and rank matching a self-serve registration;
  * two admins sharing a mailbox become one contact, in the dry run as in the real run;
  * the dry run writes nothing and equals the apply; a second apply writes nothing;
  * an existing contact is byte-for-byte untouched, whichever way it matched;
  * a Rediscover prunes a crawled officer but keeps what this stored (and the prune is shown to
    DO something, so "kept" means something);
  * a club with no Directory row, an admin with nothing to store, an archived club, a club_member
    and a person who asked to be removed are each reported or left out, as stated;
  * an opted-out address is stored as a contact that says so, never one that reads as reachable.

    python -m verification.verify_admin_directory_contacts
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import io
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_URL = os.environ.get(
    "VERIFY_DATABASE_URL", "postgresql+asyncpg://postgres@127.0.0.1:55432/verify_admin_directory")
# Before app.models.db is imported: the script opens its own session through async_session_maker.
os.environ["DATABASE_URL"] = DB_URL

from sqlalchemy import func, select, text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

import app.models.db as mdb  # noqa: E402
from app.models.db import (  # noqa: E402
    Base, ClubMembership, CommsContact, EmailSuppression, MarketingClub, MarketingClubContact,
    Organisation, User,
)
from app.scripts import ensure_admin_directory_contacts as script  # noqa: E402
from app.services import admin_directory_contacts as adc  # noqa: E402
from app.services import club_directory, privacy_email  # noqa: E402

PASS: list[str] = []
FAIL: list[str] = []
NOW = dt.datetime.now(dt.timezone.utc)


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} — {detail}")
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  ({detail})'}")


def snap(c: MarketingClubContact) -> tuple:
    return (c.id, c.full_name, c.email, c.mobile, c.role, c.role_rank, c.source, c.outreach_selected,
            c.subscribed, c.former_at, c.notes, c.do_not_contact)


async def main() -> int:
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
    Session = async_sessionmaker(engine, expire_on_commit=False)
    mdb.async_session_maker = Session

    # A person who asked to be removed (migration 316 derives these live; here it is fixed).
    async def removed(session=None):
        return {"gone@juliet.org"}
    privacy_email.removed_addresses = removed

    # ── seed: one club per rule ──────────────────────────────────────────────
    clubs: dict = {}

    async def make_club(db, key, *, directory=True, archived=False):
        org = Organisation(id=uuid.uuid4(), name=f"{key.title()} CC", slug=f"{key}-cc",
                           archived_at=NOW if archived else None)
        db.add(org)
        await db.flush()
        mc = None
        if directory:
            mc = MarketingClub(grassroots_guid=f"g-{uuid.uuid4()}", name=org.name, kind="club",
                               status="target", source="api", existing_org_id=org.id)
            db.add(mc)
            await db.flush()
        clubs[key] = (org, mc)
        return org, mc

    async def make_admin(db, key, username, *, email=None, display=None, first=None, last=None,
                         mobile=None, role="club_admin", primary=False):
        org, _ = clubs[key]
        u = User(id=uuid.uuid4(), username=username, email=email, display_name=display,
                 first_name=first, last_name=last, mobile_number=mobile)
        db.add(u)
        await db.flush()
        db.add(ClubMembership(club_id=org.id, user_id=u.id, role=role, is_primary_admin=primary))
        await db.flush()
        return u

    def crawled(mc, name, email, role, rank, **kw):
        return MarketingClubContact(marketing_club_id=mc.id, full_name=name, email=email, role=role,
                                    role_rank=rank, source="api", outreach_selected=True, **kw)

    async with Session() as db:
        outreach = Organisation(id=uuid.uuid4(), name="BetterCricket", slug="bettercricket",
                                is_marketing_outreach=True)
        db.add(outreach)
        # A, same email as the club's President, typed in another case.
        _, mcA = await make_club(db, "alpha")
        db.add(crawled(mcA, "Jane Smith", "jane@alpha.org", "President", 1))
        await make_admin(db, "alpha", "a1", email="JANE@alpha.org", display="Jane Smith", primary=True)
        # B, the Secretary signing up with a personal address: same full name, other order.
        _, mcB = await make_club(db, "bravo")
        db.add(crawled(mcB, "Raj Patel", "raj@bravo.org", "Secretary", 2))
        await make_admin(db, "bravo", "b1", email="rajp@gmail.com", display="Patel Raj", primary=True)
        # C, not a contact at all, known by a first name until they filled in a surname; a mobile.
        # A second admin account on the SAME address (a shared club mailbox).
        _, mcC = await make_club(db, "charlie")
        await make_admin(db, "charlie", "c1", email="Admin@Charlie.org", display="Cam", first="Cam",
                         last="Lee", mobile="0412 345 678", primary=True)
        # (a second club_admin can't share the club's single membership row per user, so a second
        # ACCOUNT is used for the same address)
        await make_admin(db, "charlie", "c2", email="admin@charlie.org", display="Cam Lee")
        # D, a crawled officer called only "Sam", and an admin called "Sam" on another address:
        # a first name is not an identity.
        _, mcD = await make_club(db, "delta")
        db.add(crawled(mcD, "Sam", "sam@delta.org", "Treasurer", 3))
        await make_admin(db, "delta", "d1", email="sam.d@gmail.com", display="Sam", primary=True)
        # E has no Directory row at all.
        await make_club(db, "echo", directory=False)
        await make_admin(db, "echo", "e1", email="e1@echo.org", display="Eve Echo", primary=True)
        # F's admin has no email and no mobile.
        await make_club(db, "foxtrot")
        await make_admin(db, "foxtrot", "f1", display="Fred Fox", primary=True)
        # G, an admin with a mobile and no email, beside an existing address-less contact.
        _, mcG = await make_club(db, "golf")
        db.add(MarketingClubContact(marketing_club_id=mcG.id, full_name="Gus Hall", email=None,
                                    mobile="0400 111 222", role="Contact", role_rank=50, source="api"))
        await make_admin(db, "golf", "g1", display="Gus Hall", mobile="0499 000 111", primary=True)
        await make_admin(db, "golf", "g2", display="Gail Golf", mobile="0488 222 333")
        # H's address is globally suppressed.
        await make_club(db, "hotel")
        db.add(EmailSuppression(email="optout@hotel.org", reason="manual"))
        await make_admin(db, "hotel", "h1", email="optout@hotel.org", display="Hana Hotel", primary=True)
        # I is archived.
        await make_club(db, "india", archived=True)
        await make_admin(db, "india", "i1", email="i1@india.org", display="Ian India", primary=True)
        # J asked to be removed.
        await make_club(db, "juliet")
        await make_admin(db, "juliet", "j1", email="gone@juliet.org", display="Jo Juliet", primary=True)
        # K's admin is unsubscribed on BetterCricket's own Comms list.
        await make_club(db, "kilo")
        db.add(CommsContact(organisation_id=outreach.id, email="quit@kilo.org", name="Kit", source="admin",
                            subscribed=False, unsubscribed_at=NOW))
        await make_admin(db, "kilo", "k1", email="quit@kilo.org", display="Kit Kilo", primary=True)
        # M's admin is a test account on a throwaway-mail domain (a subdomain too, for N).
        await make_club(db, "mike")
        await make_admin(db, "mike", "m1", email="Tester@YOPmail.com", display="Test Mike", primary=True)
        await make_club(db, "november")
        await make_admin(db, "november", "n1", email="t@x.yopmail.com", display="Test November", primary=True)
        await make_club(db, "oscar")
        await make_admin(db, "oscar", "o1", email="real@notyopmail.com.au", display="Oz Real", primary=True)
        # L has a club_member (not an admin) and a crawled officer who is NOT on PlayHQ any more.
        _, mcL = await make_club(db, "lima")
        await make_admin(db, "lima", "l1", email="member@lima.org", display="Mia Member", role="club_member")
        await make_admin(db, "lima", "l2", email="l2@lima.org", display="Len Lima", primary=True)
        db.add(crawled(mcL, "Old Officer", "old@lima.org", "Secretary", 2))
        await db.commit()

    async def all_contacts():
        async with Session() as db:
            return (await db.execute(select(MarketingClubContact))).scalars().all()

    async def plan(**kw):
        async with Session() as db:
            return (await adc.plan(db, **kw))["entries"]

    def by_user(entries):
        return {e["username"]: e for e in entries}

    before = {c.id: snap(c) for c in await all_contacts()}

    # ── 1. what it decides ───────────────────────────────────────────────────
    print("the plan")
    entries = await plan()
    e = by_user(entries)
    check("the same email (any case) is already a Contact", e["a1"]["status"] == "have_email", e["a1"]["status"])
    check("...and is named, so a person can see who matched", e["a1"].get("contact_name") == "Jane Smith")
    check("the same full name in another order is already a Contact", e["b1"]["status"] == "have_name",
          e["b1"]["status"])
    check("...and the contact it matched is shown (role, address)",
          e["b1"].get("contact_role") == "Secretary" and e["b1"].get("contact_email") == "raj@bravo.org", str(e["b1"]))
    check("a first name alone is NOT an identity (Sam is added)", e["d1"]["status"] == "add", e["d1"]["status"])
    check("a person who is not a contact is added", e["c1"]["status"] == "add", e["c1"]["status"])
    check("...under the fullest name the account carries", e["c1"]["name"] == "Cam Lee", e["c1"]["name"])
    check("...with the mobile on their account", e["c1"]["mobile"] == "0412 345 678", str(e["c1"]["mobile"]))
    check("...and the address lower-cased", e["c1"]["email"] == "admin@charlie.org", str(e["c1"]["email"]))
    check("a second admin on the same address is one contact, not two",
          e["c2"]["status"] == "have_email" and e["c2"].get("planned") is True, str(e["c2"]))
    check("a club with no Directory row is reported", e["e1"]["status"] == "no_directory_row", e["e1"]["status"])
    check("an admin with no email and no mobile is reported", e["f1"]["status"] == "nothing_to_store", e["f1"]["status"])
    check("an address-less admin matches an address-less contact by full name",
          e["g1"]["status"] == "have_name", e["g1"]["status"])
    check("an address-less admin with a mobile and no match is added", e["g2"]["status"] == "add", e["g2"]["status"])
    check("an opted-out address is added, flagged", e["h1"]["status"] == "add" and e["h1"].get("blocked") is True,
          str(e["h1"]))
    check("an address unsubscribed on the Comms list is flagged too", e["k1"].get("blocked") is True, str(e["k1"]))
    check("an ordinary address is not flagged (the flag can be absent)", e["c1"].get("blocked") is False)
    check("an archived club's admin is left out", "i1" not in e)
    check("a club_member is not an admin", "l1" not in e)
    check("a test account on a throwaway-mail domain is skipped (any case)", e["m1"]["status"] == "test_account", e["m1"]["status"])
    check("...a subdomain of one too", e["n1"]["status"] == "test_account", e["n1"]["status"])
    check("control: a real address that merely contains the word is added", e["o1"]["status"] == "add", e["o1"]["status"])
    check("a person who asked to be removed is not added", e["j1"]["status"] == "privacy_removed", e["j1"]["status"])

    print("the plan with --email-only")
    e2 = by_user(await plan(allow_name_match=False))
    check("the committee member by name is now ADDED (names are off)", e2["b1"]["status"] == "add", e2["b1"]["status"])
    check("an email match still matches", e2["a1"]["status"] == "have_email")
    check("the address-less exact-name match still holds (the store would otherwise edit it)",
          e2["g1"]["status"] == "have_name", e2["g1"]["status"])

    # ── 2. dry run writes nothing ────────────────────────────────────────────
    print("dry run")
    n0 = len(await all_contacts())
    async with Session() as db:
        dry = await adc.backfill(db, apply=False)
        await db.commit()
    check("a dry run creates nothing", len(await all_contacts()) == n0, f"{n0} -> {len(await all_contacts())}")
    check("...and says how many it would store", len(dry["add"]) == 7 and dry["created"] == 0,
          f"{len(dry['add'])} / {dry['created']}")
    would = {(x["club"], x["email"], x["name"]) for x in dry["add"]}

    # ── 3. apply ─────────────────────────────────────────────────────────────
    print("apply")
    async with Session() as db:
        res = await adc.backfill(db, apply=True)
        await db.commit()
    rows = await all_contacts()
    new = [c for c in rows if c.id not in before]
    check("it creates exactly what the dry run said", res["created"] == len(new) == 7, f"{res['created']} / {len(new)}")
    got = {(next(o.name for o, m in clubs.values() if m and m.id == c.marketing_club_id), c.email, c.full_name)
           for c in new}
    check("...the same people", got == would, f"{sorted(got, key=str)} vs {sorted(would, key=str)}")
    cam = next((c for c in new if c.email == "admin@charlie.org"), None)
    check("Cam: stored as Club Admin, rank 1, name, mobile",
          cam is not None and cam.role == "Club Admin" and cam.role_rank == 1 and cam.full_name == "Cam Lee"
          and cam.mobile == "0412 345 678", str(cam and snap(cam)))
    check("Cam: ticked for outreach and subscribed (as a registrant is)",
          cam is not None and cam.outreach_selected is True and cam.subscribed is True)
    check("Cam: a source a Rediscover does not prune", cam is not None and cam.source == adc.SOURCE != "api")
    check("only one contact for the shared mailbox",
          sum(1 for c in new if c.email == "admin@charlie.org") == 1)
    hot = next((c for c in new if c.email == "optout@hotel.org"), None)
    check("the suppressed address is stored as NOT subscribed and NOT ticked",
          hot is not None and hot.subscribed is False and hot.outreach_selected is False,
          str(hot and (hot.subscribed, hot.outreach_selected)))
    kil = next((c for c in new if c.email == "quit@kilo.org"), None)
    check("the unsubscribed address likewise", kil is not None and kil.subscribed is False and kil.outreach_selected is False)
    gail = next((c for c in new if c.full_name == "Gail Golf"), None)
    check("an admin with a mobile and no email is stored as a phone-only contact",
          gail is not None and gail.email is None and gail.mobile == "0488 222 333", str(gail and snap(gail)))
    check("Sam (first name only) got his own contact beside the crawled Sam",
          any(c.email == "sam.d@gmail.com" for c in new) and any(c.email == "sam@delta.org" for c in rows))

    check("every existing contact is untouched", all(snap(c) == before[c.id] for c in rows if c.id in before),
          str([c.full_name for c in rows if c.id in before and snap(c) != before[c.id]]))
    check("nothing for the skipped clubs / people",
          not any(c.email in ("e1@echo.org", "i1@india.org", "gone@juliet.org", "member@lima.org",
                          "tester@yopmail.com", "t@x.yopmail.com") for c in rows))

    print("running it again")
    async with Session() as db:
        res2 = await adc.backfill(db, apply=True)
        await db.commit()
    check("a second apply creates nothing", res2["created"] == 0 and len(await all_contacts()) == len(rows),
          f"{res2['created']}")
    check("...and the plan has nothing left to add", len(res2["add"]) == 0, str(len(res2["add"])))

    # ── 4. a Rediscover keeps them ───────────────────────────────────────────
    print("a Rediscover")
    async with Session() as db:
        _, mcL_row = clubs["lima"]
        # An officer PlayHQ no longer lists is pruned (so this check CAN remove a row)...
        deleted, marked = await club_directory._prune_committee(db, mcL_row.id, [])
        await db.commit()
    still = {c.email for c in await all_contacts()}
    check("control: a crawled officer PlayHQ no longer lists IS pruned", "old@lima.org" not in still and deleted >= 1,
          f"deleted={deleted}")
    check("...and the contact this stored at that club (Len, the admin) is kept", "l2@lima.org" in still)
    async with Session() as db:
        _, mcC_row = clubs["charlie"]
        await club_directory._prune_committee(db, mcC_row.id, [])
        await db.commit()
    check("a Rediscover of the club it stored Cam at keeps Cam",
          "admin@charlie.org" in {c.email for c in await all_contacts()})

    # ── 5. the script itself ─────────────────────────────────────────────────
    print("the script")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = await script.run("echo-cc", False, True)
    out = buf.getvalue()
    check("one club, dry run: exits 0 and says it is a dry run", rc == 0 and "DRY RUN" in out, out[-200:])
    check("...reports the club with no Directory row", "Echo CC" in out and "NO CLUBS DIRECTORY ROW" in out, out)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = await script.run("no-such-club", False, True)
    check("an unknown club is refused", rc == 1 and "No club found" in buf.getvalue())
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = await script.run(None, False, True)
    out = buf.getvalue()
    check("whole platform, dry run: lists the name-only match for review",
          rc == 0 and "BY NAME ONLY" in out and "Raj Patel" in out, out[-400:])

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print(f"  FAILED: {f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
