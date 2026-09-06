"""Verification for the member fees form's saves, against a real Postgres.

Reported off Sam Alborn's Accounts page (Applecross, 2025/26): changing the
Membership Type and saving RESET the Membership Tier to "Needs tier", and with
two panels edited only one panel's changes survived whichever button was
pressed.

Both come back to one line in ``patch_member_season``:

    # fee_schedule_id is always present in the body; treat "" / null as clear.
    ms.fee_schedule_id = schedule.id if schedule else None

It was NOT always present. Two callers wrote that row without it — the
membership panel saving a status, and the Accounts LIST ticking "Registered
with PlayHQ" — so every one of those writes silently wiped the member's tier
and left the club reading "No tier assigned — fees won't calculate."

The key's PRESENCE is the intent now (the ``select_show_age_under`` rule this
repo already keeps): absent means the caller is not editing the tier, null or
"" means clear it. That is what also makes a combined save safe — the three
panels write to two endpoints between them, so a save that carries several
panels' changes must be able to send a status without saying anything about
the tier.

Runs the SHIPPED route bodies — never a re-implementation.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \
  python verification/verify_member_fees_form_save.py
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
    Base, FeeMember, FeeMemberSeason, FeeSchedule, MembershipType,
    Organisation, Season,
)
from app.routers.fees import (
    MemberPatch, MemberSeasonPatch, get_member, patch_member, patch_member_season,
)

DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

PASS = FAIL = 0
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        FAILURES.append(label)
        print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")


ORG = uuid.uuid4()
OTHER = uuid.uuid4()
SEASON = uuid.uuid4()
SEASON_PRIOR = uuid.uuid4()
OTHER_SEASON = uuid.uuid4()

TIER_SENIOR = uuid.uuid4()
TIER_JUNIOR = uuid.uuid4()
OTHER_TIER = uuid.uuid4()          # a tier belonging to another season entirely

TYPE_SENIOR = uuid.uuid4()
TYPE_SOCIAL = uuid.uuid4()
OTHER_TYPE = uuid.uuid4()

ALBORN = uuid.uuid4()              # the reported member
MS_ALBORN = uuid.uuid4()
FOREIGN = uuid.uuid4()             # another club's member


class _User:
    """Stand-in for the authenticated caller. The route bodies only ever pass
    it through, so nothing here needs a real users row."""
    id = uuid.uuid4()
    username = "verify"


USER = _User()


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)


async def seed(session) -> None:
    for oid, name, slug in ((ORG, "Applecross CC", "applecross"), (OTHER, "Rival CC", "rival")):
        session.add(Organisation(id=oid, name=name, slug=slug))
    await session.flush()
    session.add(Season(id=SEASON, organisation_id=ORG, name="Summer 2025/26", year=2025))
    session.add(Season(id=SEASON_PRIOR, organisation_id=ORG, name="Summer 2024/25", year=2024))
    session.add(Season(id=OTHER_SEASON, organisation_id=OTHER, name="Summer 2025/26", year=2025))
    await session.flush()
    session.add(FeeSchedule(id=TIER_SENIOR, organisation_id=ORG, season_id=SEASON,
                            name="Senior", payment_type="standard",
                            membership_amount=200, match_day_rate=20))
    session.add(FeeSchedule(id=TIER_JUNIOR, organisation_id=ORG, season_id=SEASON,
                            name="Junior", payment_type="standard",
                            membership_amount=100, match_day_rate=10))
    session.add(FeeSchedule(id=OTHER_TIER, organisation_id=ORG, season_id=SEASON_PRIOR,
                            name="Last Year", payment_type="standard"))
    session.add(MembershipType(id=TYPE_SENIOR, organisation_id=ORG, name="Senior Player", is_playing=True))
    session.add(MembershipType(id=TYPE_SOCIAL, organisation_id=ORG, name="Social Member"))
    session.add(MembershipType(id=OTHER_TYPE, organisation_id=OTHER, name="Senior Player"))
    await session.flush()
    session.add(FeeMember(id=ALBORN, organisation_id=ORG, full_name="Alborn, Sam",
                          email="sam@example.com", current_tier="Senior"))
    await session.flush()
    session.add(FeeMemberSeason(id=MS_ALBORN, member_id=ALBORN, season_id=SEASON,
                                organisation_id=ORG, fee_schedule_id=TIER_SENIOR,
                                status="active"))
    session.add(FeeMember(id=FOREIGN, organisation_id=OTHER, full_name="Someone Else"))


async def org(session, oid=ORG) -> Organisation:
    return await session.get(Organisation, oid)


async def tier_of(session, member=ALBORN, season=SEASON):
    row = (await session.execute(text(
        "SELECT fee_schedule_id FROM fee_member_seasons WHERE member_id = :m AND season_id = :s"
    ), {"m": member, "s": season})).scalar_one_or_none()
    return row


async def reset_tier(session, tier=TIER_SENIOR) -> None:
    """Put the tier back between scenarios. EXPIRES the session afterwards:
    the route bodies edit the ORM row, so a raw UPDATE that leaves a stale
    in-memory copy behind makes the next write look like a no-op and the check
    measures the harness rather than the code."""
    await session.execute(text(
        "UPDATE fee_member_seasons SET fee_schedule_id = :t WHERE id = :i"
    ), {"t": tier, "i": MS_ALBORN})
    await session.commit()
    session.expire_all()


async def season_patch(session, **body):
    return await patch_member_season(
        member_id=str(ALBORN), data=MemberSeasonPatch(season_id=str(SEASON), **body),
        _=USER, club=await org(session), db=session,
    )


async def member_patch(session, member_id=ALBORN, **body):
    return await patch_member(
        member_id=str(member_id), data=MemberPatch(**body),
        _=USER, club=await org(session), db=session,
    )


async def main() -> None:
    await build_schema()
    async with Session() as session:
        await seed(session)
        await session.commit()

    async with Session() as session:
        print("\n-- the reported case: SAVE MEMBERSHIP must not wipe the tier --")
        check("the member starts on the Senior tier", await tier_of(session) == TIER_SENIOR)
        # Exactly what the membership panel used to send: a season status and
        # nothing at all about the tier.
        await season_patch(session, status="active")
        check("SAVING A STATUS ALONE LEAVES THE TIER IN PLACE — the reported bug",
              await tier_of(session) == TIER_SENIOR, str(await tier_of(session)))

        await season_patch(session, status="suspended")
        row = await session.get(FeeMemberSeason, MS_ALBORN)
        await session.refresh(row)
        check("and the status it WAS asked to change did change",
              row.status == "suspended", row.status)
        await season_patch(session, status="active")

        print("\n-- the same write from the Accounts list's PlayHQ tick --")
        await season_patch(session, playhq_registered=True)
        check("ticking PlayHQ from the list leaves the tier in place",
              await tier_of(session) == TIER_SENIOR, str(await tier_of(session)))
        row = await session.get(FeeMemberSeason, MS_ALBORN)
        await session.refresh(row)
        check("and records the tick", row.playhq_registered is True)
        check("stamping the time it was sighted", row.playhq_registered_at is not None)
        await season_patch(session, playhq_registered=False)
        row = await session.get(FeeMemberSeason, MS_ALBORN)
        await session.refresh(row)
        check("un-ticking clears the stamp rather than leaving a stale one",
              row.playhq_registered is False and row.playhq_registered_at is None)
        check("and STILL leaves the tier alone", await tier_of(session) == TIER_SENIOR)

        print("\n-- a caller that IS editing the tier still gets its way --")
        await season_patch(session, fee_schedule_id=str(TIER_JUNIOR))
        check("naming a tier sets it", await tier_of(session) == TIER_JUNIOR)
        member = await session.get(FeeMember, ALBORN)
        await session.refresh(member)
        check("and carries it forward as the member's default for next season",
              member.current_tier == "Junior", str(member.current_tier))

        # NULL and "" are the two shapes the tier picker's "— Needs tier —"
        # option can arrive as. Both mean clear, and both are DISTINCT from the
        # key being absent.
        await season_patch(session, fee_schedule_id=None)
        check("AN EXPLICIT null CLEARS THE TIER — absent and null are different "
              "things, and only one of them means clear",
              await tier_of(session) is None, str(await tier_of(session)))
        await reset_tier(session)
        await season_patch(session, fee_schedule_id="")
        check("an explicit empty string clears it too",
              await tier_of(session) is None, str(await tier_of(session)))
        await reset_tier(session)

        print("\n-- clearing does NOT rewrite the carry-forward default --")
        member = await session.get(FeeMember, ALBORN)
        await session.refresh(member)
        before = member.current_tier
        await season_patch(session, fee_schedule_id=None)
        await session.refresh(member)
        check("a cleared season leaves current_tier as the last real tier, so "
              "next season's rollover still has something to seed from",
              member.current_tier == before, f"{before!r} -> {member.current_tier!r}")
        await reset_tier(session)

        print("\n-- the combined save the three panels now make --")
        # One write per endpoint, carrying every panel the admin touched. This
        # is the shape the page sends when Membership, Tier and Contact are all
        # dirty and any one of the three buttons is pressed.
        await member_patch(
            session,
            full_name="Alborn, Samuel", email="samuel@example.com",
            mobile="0400 000 000", notes="Pays by EFT",
            membership_type_id=str(TYPE_SENIOR), is_life_member=True,
        )
        await season_patch(
            session, status="active", fee_schedule_id=str(TIER_JUNIOR),
            is_new_registration=True, membership_payment_method="Cash",
            playhq_registered=True,
        )
        payload = await get_member(member_id=str(ALBORN), season_id=str(SEASON),
                                   _=USER, club=await org(session), db=session)
        m, ms = payload["member"], payload["member_season"]
        check("the membership TYPE landed", m["membership_type_id"] == str(TYPE_SENIOR))
        check("the life-member flag landed", m["is_life_member"] is True)
        check("the contact name landed", m["full_name"] == "Alborn, Samuel")
        check("the email landed", m["email"] == "samuel@example.com")
        check("the mobile landed", m["mobile"] == "0400 000 000")
        check("the notes landed", m["notes"] == "Pays by EFT")
        check("THE TIER LANDED TOO — the whole reported second bug is one panel's "
              "changes surviving and another's being lost",
              ms["fee_schedule_id"] == str(TIER_JUNIOR), str(ms["fee_schedule_id"]))
        check("the payment method landed", ms["membership_payment_method"] == "Cash")
        check("the new-registration tick landed", ms["is_new_registration"] is True)
        check("the PlayHQ tick landed", ms["playhq_registered"] is True)
        check("the season status landed", ms["status"] == "active")

        print("\n-- a membership save with no tier in it, on the SAME payload --")
        await member_patch(session, membership_type_id=str(TYPE_SOCIAL))
        await season_patch(session, status="suspended")
        payload = await get_member(member_id=str(ALBORN), season_id=str(SEASON),
                                   _=USER, club=await org(session), db=session)
        check("the type changed", payload["member"]["membership_type_id"] == str(TYPE_SOCIAL))
        check("the status changed", payload["member_season"]["status"] == "suspended")
        check("and the tier the admin set a moment ago is still there",
              payload["member_season"]["fee_schedule_id"] == str(TIER_JUNIOR),
              str(payload["member_season"]["fee_schedule_id"]))
        await season_patch(session, status="active")

        print("\n-- clearing the membership type is its own act --")
        await member_patch(session, membership_type_id="")
        member = await session.get(FeeMember, ALBORN)
        await session.refresh(member)
        check("an empty membership_type_id clears the type", member.membership_type_id is None)
        check("and does not touch the season's tier", await tier_of(session) == TIER_JUNIOR)
        await member_patch(session, membership_type_id=str(TYPE_SENIOR))

        print("\n-- refusals, and what they leave behind --")
        await reset_tier(session, TIER_SENIOR)
        for label, body in (
            ("another season's tier is refused", {"fee_schedule_id": str(OTHER_TIER)}),
            ("an unknown tier is refused", {"fee_schedule_id": str(uuid.uuid4())}),
        ):
            try:
                await season_patch(session, **body)
                check(label, False, "no error raised")
            except HTTPException as exc:
                await session.rollback()
                check(label, exc.status_code == 422, f"status {exc.status_code}")
        check("and a refused tier leaves the stored one exactly as it was",
              await tier_of(session) == TIER_SENIOR, str(await tier_of(session)))

        try:
            await season_patch(session, status="not-a-status")
            check("an unknown status is refused", False, "no error raised")
        except HTTPException as exc:
            await session.rollback()
            check("an unknown status is refused", exc.status_code == 422)
        check("and the tier survives that refusal too", await tier_of(session) == TIER_SENIOR)

        try:
            await member_patch(session, membership_type_id=str(OTHER_TYPE))
            check("another club's membership type is refused", False, "no error raised")
        except HTTPException as exc:
            await session.rollback()
            check("another club's membership type is refused", exc.status_code == 422)

        print("\n-- cross-club --")
        try:
            await patch_member_season(
                member_id=str(FOREIGN), data=MemberSeasonPatch(season_id=str(SEASON)),
                _=USER, club=await org(session), db=session)
            check("another club's member cannot be written through ours", False, "no error")
        except HTTPException as exc:
            await session.rollback()
            check("another club's member cannot be written through ours", exc.status_code == 404)
        try:
            await member_patch(session, member_id=FOREIGN, full_name="Nope")
            check("nor their person record", False, "no error raised")
        except HTTPException as exc:
            await session.rollback()
            check("nor their person record", exc.status_code == 404)
        try:
            await patch_member_season(
                member_id=str(ALBORN), data=MemberSeasonPatch(season_id=str(OTHER_SEASON)),
                _=USER, club=await org(session), db=session)
            check("another club's season is refused", False, "no error raised")
        except HTTPException as exc:
            await session.rollback()
            check("another club's season is refused", exc.status_code == 404)

        print("\n-- a member with no season row yet --")
        NEWCOMER = uuid.uuid4()
        session.add(FeeMember(id=NEWCOMER, organisation_id=ORG, full_name="Newcomer, Nick"))
        await session.commit()
        await patch_member_season(
            member_id=str(NEWCOMER), data=MemberSeasonPatch(season_id=str(SEASON), status="invited"),
            _=USER, club=await org(session), db=session)
        row = (await session.execute(text(
            "SELECT status, fee_schedule_id FROM fee_member_seasons "
            "WHERE member_id = :m AND season_id = :s"), {"m": NEWCOMER, "s": SEASON})).first()
        check("a status-only save opens the season row", row is not None)
        check("with the status asked for", row and row[0] == "invited", str(row))
        check("and no tier invented for them — a row that was never given one "
              "must read as needing a tier, not as one silently chosen",
              row and row[1] is None, str(row))

    await engine.dispose()
    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  FAILED:", f)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
