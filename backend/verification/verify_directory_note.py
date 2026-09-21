"""A multi-line general note about a person, through the SHIPPED Directory read
and route bodies, against a real Postgres.

Asked for as "allow the user to add a multi-line general note associated with
the player". The note lives on the shared `fee_members` spine (Text column, so
no length cap and newlines survive), and its whole design is that it is edited
IN PLACE from its own card rather than through the Add/Edit modal — the same
one-writer, edit-a-field-at-a-time pattern the contact / gender / squad / kit
fields already follow.

What is asserted:
  * `list_people` returns the note on every person, `None` where none is set;
  * a multi-line note written through the update route round-trips exactly —
    newlines and length both preserved;
  * present-and-blank ("") CLEARS the note, while an ABSENT key (an edit that
    names only the email) leaves it alone — which is the fix that stops the
    Add/Edit modal wiping a note when someone edits a name, because the modal
    no longer carries the field at all;
  * a read-through player (no member row yet) reads `notes: None` with
    `member_id: None`, and recording a note MINTS the member row — a note can
    be kept about anybody;
  * the write is org-scoped: a note aimed at a member under the wrong club's
    context changes nothing.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \
  python verification/verify_directory_note.py
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import Base, FeeMember, Organisation, Player

DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

PASS = FAIL = 0
FAILURES: list[str] = []
MISSING: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        FAILURES.append(label)
        print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")


def load(what, fn):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001 — a control run must survive this
        MISSING.append(f"{what}: {e}")
        return None


directory_router = load("routers/directory.py", lambda: __import__("app.routers.directory", fromlist=["x"]))
directory_svc = load("services/directory.py", lambda: __import__("app.services.directory", fromlist=["x"]))
members_svc = load("services/members.py", lambda: __import__("app.services.members", fromlist=["x"]))

ORG = uuid.uuid4()
FOREIGN = uuid.uuid4()
COACH = uuid.uuid4()      # a non-player member
PLAYER = uuid.uuid4()     # a player who already has a member row
LOOSE = uuid.uuid4()      # a player with no member row yet (read-through)

# A genuinely multi-line note, so "the column holds newlines and does not
# truncate" is measured rather than assumed.
NOTE = (
    "Prefers to bat in the top order.\n"
    "Can keep wicket at a pinch.\n\n"
    "Away for work through January — check availability before selecting."
)


class _User:
    id = uuid.uuid4()
    username = "verify"
    role = "club_admin"


USER = _User()

# Directory reads reach tables that live only in the app lifespan as raw SQL,
# so create_all from the ORM has never heard of them. Read out of main.py
# rather than retyped, in dependency order (club_roles references
# club_role_types), so the harness cannot drift from the real schema.
LIFESPAN_TABLES = (
    "member_membership_types", "player_achievements", "volunteer_profiles",
    "volunteer_hours", "member_qualifications", "club_role_types", "club_roles",
    "volunteer_roles",
)
LIFESPAN_COLUMNS = ("ALTER TABLE fee_members ADD COLUMN IF NOT EXISTS member_category TEXT",)


def lifespan_extras() -> list[str]:
    src = (Path(__file__).resolve().parent.parent / "app" / "main.py").read_text()
    out: list[str] = []
    for t in LIFESPAN_TABLES:
        m = re.search(r"(CREATE TABLE IF NOT EXISTS " + t + r" \([\s\S]*?\n\s*\)\n)", src)
        if m:
            out.append(m.group(1).rstrip())
        else:
            MISSING.append(f"lifespan DDL for {t}")
        for m in re.finditer(
            r'"(ALTER TABLE ' + t + r' ADD COLUMN IF NOT EXISTS [^"]*)"((?:\s*"[^"]*")*)', src
        ):
            out.append(m.group(1) + "".join(re.findall(r'"([^"]*)"', m.group(2))))
    return out + list(LIFESPAN_COLUMNS)


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)
        for stmt in lifespan_extras():
            await conn.execute(text(stmt))


async def seed(session) -> None:
    for oid, name, slug in ((ORG, "Applecross CC", "applecross"), (FOREIGN, "Rival CC", "rival")):
        session.add(Organisation(id=oid, name=name, slug=slug))
    await session.flush()
    session.add(Player(id=PLAYER, organisation_id=ORG, name="Hind, Darren"))
    session.add(Player(id=LOOSE, organisation_id=ORG, name="Newcomer, Nick"))
    await session.flush()
    session.add(FeeMember(id=COACH, organisation_id=ORG, full_name="Bev the Coach"))
    session.add(FeeMember(id=uuid.uuid4(), organisation_id=ORG, full_name="Hind, Darren", player_id=PLAYER))


async def org_of(session, oid=ORG) -> Organisation:
    from sqlalchemy.orm import selectinload
    return await session.get(Organisation, oid, options=[selectinload(Organisation.module_subscriptions)])


async def person(session, key, club_id=ORG):
    """One person out of the SHIPPED Directory read, by name."""
    rows = await directory_svc.list_people(session, club_id)
    return next((p for p in rows if key in (p["name"] or "")), None)


async def patch_member(session, mid, club_id=ORG, **body):
    return await directory_router.update_member(
        member_id=str(mid), data=directory_router.MemberUpsert(**body),
        _=USER, club=await org_of(session, club_id), db=session)


async def stored_note(session, mid):
    return (await session.execute(text(
        "SELECT notes FROM fee_members WHERE id = :k"), {"k": mid})).scalar_one_or_none()


async def report_and_exit() -> None:
    await engine.dispose()
    if MISSING:
        print("\nMISSING (a control run without the feature reports these):")
        for m in MISSING:
            print("  --", m)
    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  FAILED:", f)
    sys.exit(1 if FAIL else 0)


async def main() -> None:
    await build_schema()
    async with Session() as session:
        await seed(session)
        await session.commit()

    if directory_svc is None or directory_router is None or members_svc is None:
        check("the Directory note code is present", False, "; ".join(MISSING))
        await report_and_exit()

    print("\n-- the note is surfaced by the Directory read --")
    async with Session() as session:
        coach = await person(session, "Bev")
        player = await person(session, "Hind")
        loose = await person(session, "Newcomer")
        check("every person carries a note field",
              coach is not None and "notes" in coach and "notes" in player and "notes" in loose)
        check("and it is None until one is recorded",
              coach and coach["notes"] is None and player and player["notes"] is None)
        check("a read-through player has no member row and no note",
              loose is not None and loose["member_id"] is None and loose["notes"] is None)

    print("\n-- a multi-line note round-trips exactly --")
    async with Session() as session:
        await patch_member(session, COACH, notes=NOTE)
        await session.commit()
    async with Session() as session:
        coach = await person(session, "Bev")
        check("the note reads back through list_people unchanged", coach and coach["notes"] == NOTE,
              repr(coach and coach["notes"]))
        check("the newlines survived", coach and coach["notes"].count("\n") == NOTE.count("\n"))
        check("nothing was truncated", coach and len(coach["notes"]) == len(NOTE))

    print("\n-- present-and-blank clears; an absent key leaves it alone --")
    async with Session() as session:
        # An edit that names ONLY the email must not touch the note — this is the
        # modal-clobber fix: the Add/Edit modal no longer sends `notes` at all,
        # so editing a name can never wipe one.
        await patch_member(session, COACH, email="bev@example.com")
        await session.commit()
    async with Session() as session:
        coach = await person(session, "Bev")
        check("editing only the email leaves the note in place", coach and coach["notes"] == NOTE)
    async with Session() as session:
        await patch_member(session, COACH, notes="")
        await session.commit()
    async with Session() as session:
        coach = await person(session, "Bev")
        check("a present, blank note clears it", coach and coach["notes"] is None)
        check("and the stored column is NULL, not an empty string", await stored_note(session, COACH) is None)

    print("\n-- recording a note about a read-through player mints the member row --")
    async with Session() as session:
        mid = await members_svc.ensure_for_player(session, ORG, LOOSE)
        await patch_member(session, mid, notes="Trialist — impressed at the nets.")
        await session.commit()
    async with Session() as session:
        loose = await person(session, "Newcomer")
        check("the player now has a member row", loose and loose["member_id"] is not None)
        check("carrying the note", loose and loose["notes"] == "Trialist — impressed at the nets.")

    print("\n-- the write is org-scoped --")
    async with Session() as session:
        # PLAYER's member row belongs to ORG. A write under the RIVAL club's
        # context matches no row (the UPDATE is scoped by organisation_id) and
        # changes nothing.
        pmid = (await session.execute(text(
            "SELECT id FROM fee_members WHERE organisation_id = :o AND player_id = :p"),
            {"o": ORG, "p": PLAYER})).scalar_one()
        await patch_member(session, pmid, notes="ours", club_id=ORG)
        await session.commit()
    async with Session() as session:
        pmid = (await session.execute(text(
            "SELECT id FROM fee_members WHERE organisation_id = :o AND player_id = :p"),
            {"o": ORG, "p": PLAYER})).scalar_one()
        await patch_member(session, pmid, notes="tampered", club_id=FOREIGN)
        await session.commit()
    async with Session() as session:
        pmid = (await session.execute(text(
            "SELECT id FROM fee_members WHERE organisation_id = :o AND player_id = :p"),
            {"o": ORG, "p": PLAYER})).scalar_one()
        check("a note aimed at the wrong club's context does nothing",
              await stored_note(session, pmid) == "ours")

    await report_and_exit()


if __name__ == "__main__":
    asyncio.run(main())
