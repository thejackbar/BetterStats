"""Fill in a club admin's missing mobile from their own club's records.

Asked for: for every club admin we hold no mobile number for, look at their
club in the directory, find that person's record, and store their mobile
against the user account.

This runs the SHIPPED service and script logic (imported, nothing retyped)
against a real Postgres.

    python -m verification.verify_admin_mobile_backfill
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
    "postgresql+asyncpg://postgres@127.0.0.1:5432/verify_admin_mobiles",
)
# MUST be set before app.models.db is imported — async_session_maker is built at
# import time from settings.
os.environ["DATABASE_URL"] = DB_URL

from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.models.db import (  # noqa: E402
    Base, ClubMembership, FeeMember, MarketingClub, MarketingClubContact,
    Organisation, Player, User,
)

try:
    from app.services import admin_mobile_lookup as aml  # noqa: E402
    HAVE = True
except Exception as exc:  # pragma: no cover - the control run's own path
    print(f"!! services.admin_mobile_lookup is not importable: {exc}")
    aml, HAVE = None, False

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} — {detail}")
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  ({detail})'}")


def entry_for(result: dict, username: str) -> dict:
    for e in result["filled"] + result["skipped"]:
        if e["username"] == username:
            return e
    return {}


async def main() -> int:
    if not HAVE:
        check("the lookup service exists", False, "import failed")
        print("\nCONTROL RUN: the feature is absent.")
        return 1

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as db:
        clubs, users = {}, {}

        async def make_club(label, *, archived=False, directory=False):
            org = Organisation(id=uuid.uuid4(), name=f"{label.title()} CC", slug=f"{label}-cc",
                               archived_at=dt.datetime.now(dt.timezone.utc) if archived else None)
            db.add(org)
            await db.flush()
            clubs[label] = org
            if directory:
                db.add(MarketingClub(id=uuid.uuid4(), name=f"{label.title()} CC",
                                     grassroots_guid=f"guid-{label}", existing_org_id=org.id))
                await db.flush()
            return org

        async def make_admin(label, org, *, role="club_admin", primary=False, email=None,
                             display_name=None, first=None, last=None, mobile=None):
            u = User(id=uuid.uuid4(), username=label, email=email, display_name=display_name,
                     first_name=first, last_name=last, mobile_number=mobile)
            db.add(u)
            await db.flush()
            db.add(ClubMembership(club_id=org.id, user_id=u.id, role=role,
                                  is_primary_admin=primary))
            await db.flush()
            users[label] = u
            return u

        async def make_member(org, name, *, email=None, mobile=None, player=None,
                              archived=False):
            fm = FeeMember(id=uuid.uuid4(), organisation_id=org.id, full_name=name,
                           email=email, mobile=mobile,
                           player_id=player.id if player is not None else None,
                           archived_at=dt.datetime.now(dt.timezone.utc) if archived else None)
            db.add(fm)
            await db.flush()
            return fm

        async def make_player(org, name, *, email=None, phone=None):
            p = Player(id=uuid.uuid4(), organisation_id=org.id, name=name,
                       email=email, phone=phone)
            db.add(p)
            await db.flush()
            return p

        async def make_contact(org, name, *, email=None, mobile=None):
            mc = (await db.execute(select(MarketingClub).where(
                MarketingClub.existing_org_id == org.id))).scalars().first()
            c = MarketingClubContact(id=uuid.uuid4(), marketing_club_id=mc.id,
                                     full_name=name, email=email, mobile=mobile)
            db.add(c)
            await db.flush()
            return c

        # ── The platform ────────────────────────────────────────────────────
        applecross = await make_club("applecross", directory=True)
        wycombe = await make_club("wycombe", directory=True)
        nodir = await make_club("nodir")
        gone = await make_club("gone", archived=True)

        # 1. The reported case: the club's own Directory holds their mobile.
        await make_admin("jack", applecross, primary=True, email="jack@example.com",
                         display_name="Jack Barendse")
        await make_member(applecross, "Jack Barendse", email="jack@example.com",
                          mobile="0412 345 678")

        # 2. Already has one — never considered at all.
        await make_admin("hasmobile", applecross, email="has@example.com",
                         display_name="Has Mobile", mobile="0400 000 000")
        await make_member(applecross, "Has Mobile", email="has@example.com",
                          mobile="0411 111 111")

        # 3. Name match only — the club has a different address for them.
        await make_admin("namely", applecross, email="personal@gmail.com",
                         first="Sarah", last="Nolan")
        await make_member(applecross, "Nolan, Sarah", email="sarah@club.example",
                          mobile="0413 222 333")

        # 4. An email match beats a name match, even a name match on a better source.
        await make_admin("bothways", applecross, email="both@example.com",
                         display_name="Chris Reid")
        await make_member(applecross, "Someone Else", email="both@example.com",
                          mobile="0414 000 111")
        await make_player(applecross, "Chris Reid", phone="0499 999 999")

        # 5. The member row's own number wins over the linked player's.
        pl = await make_player(applecross, "Dana Fox", email="dana@example.com",
                               phone="0455 555 555")
        await make_member(applecross, "Dana Fox", email="dana@example.com",
                          mobile="0415 444 555", player=pl)
        await make_admin("dana", applecross, email="dana@example.com",
                         display_name="Dana Fox")

        # 6. A read-through player with no member row at all.
        await make_player(applecross, "Ed Poole", email="ed@example.com", phone="0416 777 888")
        await make_admin("ed", applecross, email="ed@example.com", display_name="Ed Poole")

        # 7. A landline is not a mobile.
        await make_admin("landline", applecross, email="line@example.com",
                         display_name="Pat Lines")
        await make_member(applecross, "Pat Lines", email="line@example.com",
                          mobile="(08) 9364 1234")

        # 8. Two people of one name, two numbers — refuse.
        await make_admin("ambig", applecross, email="nomatch-here@example.com",
                         display_name="Sam Ziebell")
        await make_member(applecross, "Sam Ziebell", email="sam1@club.example",
                          mobile="0417 111 111")
        await make_member(applecross, "Sam Ziebell", email="sam2@club.example",
                          mobile="0417 222 222")

        # 9. Two people of one name, ONE number spelled two ways — not a conflict.
        await make_admin("twinned", applecross, email="none-of-these@example.com",
                         display_name="Robin Vale")
        await make_member(applecross, "Robin Vale", email="r1@club.example",
                          mobile="0418 333 444")
        await make_member(applecross, "Robin Vale", email="r2@club.example",
                          mobile="+61418333444")

        # 10. Nobody at their club looks like them.
        await make_admin("stranger", applecross, email="stranger@example.com",
                         display_name="Nobody Here")

        # 11. No email and no name on the account — nothing to match on.
        await make_admin("blank", applecross)

        # 12. An archived member record is not the club's current record.
        await make_admin("archivedrec", applecross, email="arch@example.com",
                         display_name="Old Member")
        await make_member(applecross, "Old Member", email="arch@example.com",
                          mobile="0419 000 000", archived=True)

        # 13. The Clubs Directory contact, for a club with no Directory of its own.
        await make_admin("secretary", wycombe, primary=True, email="sec@wycombe.example",
                         display_name="Wendy Sec")
        await make_contact(wycombe, "Wendy Sec", email="sec@wycombe.example",
                           mobile="0420 111 222")

        # 14. Another club's records are never reached.
        await make_admin("nodiradmin", nodir, primary=True, email="jack@example.com",
                         display_name="Jack Barendse")

        # 15. A member row pointing at ANOTHER club's player.
        foreign = await make_player(wycombe, "Leaky Person", email="leak@example.com",
                                    phone="0421 999 999")
        await make_member(applecross, "Leaky Person", email="leak@example.com",
                          player=foreign)
        await make_admin("leaky", applecross, email="leak@example.com",
                         display_name="Leaky Person")

        # 16. Not club admins.
        await make_admin("staff", applecross, role="super_admin", email="staff@example.com",
                         display_name="Jack Barendse")
        await make_admin("member", applecross, role="club_member", email="mem@example.com",
                         display_name="Jack Barendse")

        # 17. An archived club's admin is left out.
        await make_admin("goneadmin", gone, primary=True, email="gone@example.com",
                         display_name="Gone Admin")
        await make_member(gone, "Gone Admin", email="gone@example.com", mobile="0422 000 000")

        await db.commit()

        # ── The dry run ────────────────────────────────────────────────────
        print("\n── The dry run reports without writing ──────────────────────")
        dry = await aml.backfill(db, apply=False)
        jack = entry_for(dry, "jack")
        check("the reported case is found", jack.get("status") == "found", jack)
        check("...with the club's own number", jack.get("mobile") == "0412 345 678", jack)
        check("...matched on the email", jack.get("matched_on") == "email", jack)
        check("...from the member record", jack.get("source") == "member", jack)
        await db.refresh(users["jack"])
        check("the dry run stored nothing", users["jack"].mobile_number is None,
              users["jack"].mobile_number)

        check("an admin who already has one is never considered",
              not entry_for(dry, "hasmobile"), entry_for(dry, "hasmobile"))
        check("...and keeps the number they had",
              users["hasmobile"].mobile_number == "0400 000 000")

        namely = entry_for(dry, "namely")
        check("a name match is found when the addresses differ",
              namely.get("status") == "found" and namely.get("mobile") == "0413 222 333", namely)
        check("...reported as a name match", namely.get("matched_on") == "name", namely)
        check("...and 'Surname, First' still matches 'First Surname'",
              namely.get("matched_name") == "Nolan, Sarah", namely)
        check("...with the account's own name kept separate from the record's",
              namely.get("name") == "Sarah Nolan", namely)

        both = entry_for(dry, "bothways")
        check("an email match beats a name match",
              both.get("mobile") == "0414 000 111", both)

        dana = entry_for(dry, "dana")
        check("the member's own number wins over the linked player's",
              dana.get("mobile") == "0415 444 555" and dana.get("source") == "member", dana)

        ed = entry_for(dry, "ed")
        check("a read-through player with no member row is found",
              ed.get("mobile") == "0416 777 888" and ed.get("source") == "player", ed)

        line = entry_for(dry, "landline")
        check("a landline is not stored", line.get("status") == "not_a_mobile", line)
        check("...and is reported so it can be checked by hand",
              line.get("mobile") == "(08) 9364 1234", line)

        amb = entry_for(dry, "ambig")
        check("two of one name with two numbers is refused",
              amb.get("status") == "ambiguous", amb)
        check("...naming both numbers", len(amb.get("candidates", [])) == 2, amb)

        twin = entry_for(dry, "twinned")
        check("one number spelled two ways is not a conflict",
              twin.get("status") == "found", twin)

        check("nobody at their club matching reads as no match",
              entry_for(dry, "stranger").get("status") == "no_match")
        check("an account with no email and no name matches nobody",
              entry_for(dry, "blank").get("status") == "no_match",
              entry_for(dry, "blank"))
        check("an archived member record is not used",
              entry_for(dry, "archivedrec").get("status") == "no_match",
              entry_for(dry, "archivedrec"))

        sec = entry_for(dry, "secretary")
        check("the Clubs Directory contact is found",
              sec.get("mobile") == "0420 111 222", sec)
        check("...reported as the club contact",
              sec.get("source") == "directory_contact", sec)

        check("another club's records are never reached",
              entry_for(dry, "nodiradmin").get("status") == "no_match",
              entry_for(dry, "nodiradmin"))
        check("a member row pointing at another club's player leaks nothing",
              entry_for(dry, "leaky").get("status") == "no_match",
              entry_for(dry, "leaky"))

        check("a super admin is not a club admin", not entry_for(dry, "staff"))
        check("a club member is not a club admin", not entry_for(dry, "member"))
        check("an archived club's admin is left out", not entry_for(dry, "goneadmin"))

        # ── --email-only ───────────────────────────────────────────────────
        print("\n── The strictest pass drops every name match ────────────────")
        strict = await aml.backfill(db, apply=False, allow_name_match=False)
        check("--email-only drops the name match",
              entry_for(strict, "namely").get("status") == "no_match",
              entry_for(strict, "namely"))
        check("...and keeps the email match",
              entry_for(strict, "jack").get("status") == "found")
        check("...and no longer reports the ambiguity",
              entry_for(strict, "ambig").get("status") == "no_match",
              entry_for(strict, "ambig"))
        await db.refresh(users["namely"])
        check("...writing nothing either", users["namely"].mobile_number is None)

        # ── One club ───────────────────────────────────────────────────────
        print("\n── One club at a time ───────────────────────────────────────")
        one = await aml.backfill(db, club_id=wycombe.id, apply=False)
        check("a club-scoped run finds that club's admin",
              entry_for(one, "secretary").get("status") == "found")
        check("...and nobody else's", not entry_for(one, "jack"), one["missing"])

        # ── Applying ───────────────────────────────────────────────────────
        print("\n── Applying writes exactly what the dry run reported ────────")
        applied = await aml.backfill(db, apply=True)
        await db.commit()
        check("the same admins are filled",
              {e["username"] for e in applied["filled"]} ==
              {e["username"] for e in dry["filled"]},
              sorted(e["username"] for e in applied["filled"]))
        check("the same figures are reported",
              (applied["missing"], applied["still_missing"]) ==
              (dry["missing"], dry["still_missing"]),
              (applied["missing"], applied["still_missing"]))
        for label, expected in (("jack", "0412 345 678"), ("namely", "0413 222 333"),
                                ("secretary", "0420 111 222"), ("ed", "0416 777 888")):
            await db.refresh(users[label])
            check(f"{label} now holds {expected}", users[label].mobile_number == expected,
                  users[label].mobile_number)
        for label in ("landline", "ambig", "stranger", "blank", "archivedrec", "leaky",
                      "nodiradmin"):
            await db.refresh(users[label])
            check(f"{label} was left blank", users[label].mobile_number is None,
                  users[label].mobile_number)
        await db.refresh(users["goneadmin"])
        check("the archived club's admin was never touched",
              users["goneadmin"].mobile_number is None, users["goneadmin"].mobile_number)
        await db.refresh(users["hasmobile"])
        check("nothing overwrote an existing number",
              users["hasmobile"].mobile_number == "0400 000 000",
              users["hasmobile"].mobile_number)

        # ── Idempotence ────────────────────────────────────────────────────
        print("\n── A second run writes nothing ──────────────────────────────")
        again = await aml.backfill(db, apply=True)
        await db.commit()
        check("nobody is left to fill", again["filled"] == [], again["filled"])
        check("...because they are no longer missing one",
              again["missing"] == dry["missing"] - len(dry["filled"]),
              (again["missing"], dry["missing"], len(dry["filled"])))
        await db.refresh(users["jack"])
        check("...and the stored number is unchanged",
              users["jack"].mobile_number == "0412 345 678")

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print(f"  FAIL  {f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
