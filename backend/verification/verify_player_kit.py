"""The club's kit record — a shirt number, a shirt size and a pants size —
against a real Postgres, through the SHIPPED route bodies.

Asked for as "store player shirt number, shirt size and pants size in the
BetterAdmin Directory", with the question of whether a Stats-only club should
get them at all. The three do NOT live in one place, and the split is what this
suite exists to hold:

  * ``players.shirt_number`` is a PLAYING attribute and is CORE. A team sheet, a
    lineup post and a scorecard all want it, and a club running nothing but
    BetterStats has every one of those surfaces — so it is edited on the player
    profile and the Directory writes it through the same route rather than
    owning a second copy of the column.
  * ``fee_members.shirt_size`` / ``.pants_size`` are KIT MANAGEMENT and are
    BetterAdmin's. They sit on the person spine, because a coach, a scorer and a
    canteen volunteer all get a club polo and ``players`` has nowhere to put
    their size. A club without the module never receives the values and cannot
    write one.

What is asserted:
  * migration 287 applied three times to a populated pre-287 schema, and the
    lifespan mirror landing on the same columns;
  * a number stored exactly as the club writes it — "07" stays "07" — and
    length-capped rather than allowed to hold a paragraph;
  * present-and-blank clears, ABSENT leaves alone, on all three fields, which is
    what lets the Directory save one panel without touching another;
  * the sizes withheld from a club without BetterAdmin, and a write naming one
    refused with the 402 the browser already knows how to render — while the
    NUMBER stays editable for that same club, which is the whole point of the
    split;
  * a size recorded against a read-through player mints the person row, and the
    number does not need one;
  * cross-club refusals both ways;
  * the bulk profile importer reading a number, keeping its leading zero, and
    reporting rather than truncating one too long to be a shirt number.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \
  python verification/verify_player_kit.py
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

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import (
    Base, FeeMember, Organisation, OrgModuleSubscription, Player,
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


# Every read of the shipped code is guarded, so a build without the feature
# REPORTS each check rather than dying on the first import and saying nothing
# about the other forty.
MISSING: list[str] = []


def load(what, fn):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001 — a control run must survive this
        MISSING.append(f"{what}: {e}")
        return None


player_kit = load("services/player_kit.py", lambda: __import__("app.services.player_kit", fromlist=["x"]))
players_router = load("routers/players.py", lambda: __import__("app.routers.players", fromlist=["x"]))
directory_router = load("routers/directory.py", lambda: __import__("app.routers.directory", fromlist=["x"]))
directory_svc = load("services/directory.py", lambda: __import__("app.services.directory", fromlist=["x"]))
profile_import = load("services/profile_import.py", lambda: __import__("app.services.profile_import", fromlist=["x"]))

ORG = uuid.uuid4()          # holds BetterAdmin
STATS_ONLY = uuid.uuid4()   # Core and nothing else
PLAYER = uuid.uuid4()
COACH = uuid.uuid4()        # a non-player: a size, never a number
LOOSE = uuid.uuid4()        # a player with no fee_members row yet
FOREIGN = uuid.uuid4()
SO_PLAYER = uuid.uuid4()


class _User:
    id = uuid.uuid4()
    username = "verify"
    role = "club_admin"


USER = _User()

# Every column migration 287 adds, and the table it belongs to.
NEW_COLUMNS = (("players", "shirt_number"), ("fee_members", "shirt_size"), ("fee_members", "pants_size"))


def migration_statements() -> list[str]:
    """The migration's own upgrade body, read out of the file rather than
    retyped — a suite that retypes the SQL is checking its own copy."""
    src = (Path(__file__).resolve().parent.parent / "alembic" / "versions" / "287_player_kit.py").read_text()
    body = src.split("def upgrade()")[1].split("def downgrade()")[0]
    return re.findall(r'"([^"]*ALTER TABLE[^"]*)"', body)


def lifespan_statements() -> list[str]:
    """The same three ALTERs as the app's own boot mirrors them."""
    src = (Path(__file__).resolve().parent.parent / "app" / "main.py").read_text()
    return [s for s in re.findall(r'"(ALTER TABLE (?:players|fee_members) ADD COLUMN IF NOT EXISTS [^"]*)"', src)
            if "shirt_number" in s or "shirt_size" in s or "pants_size" in s]


async def columns_of(session, table) -> set[str]:
    return {r[0] for r in (await session.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_name = :t"), {"t": table})).all()}


# The Directory read reaches tables and a column that live ONLY in the app's
# lifespan as raw SQL, so `create_all` from the ORM has never heard of them.
# READ OUT OF main.py rather than retyped: a harness table that merely looks
# right is worse than none, and this one cannot drift from the real schema.
# The order is the dependency order — club_roles references club_role_types.
LIFESPAN_TABLES = (
    "member_membership_types", "player_achievements", "volunteer_profiles",
    "volunteer_hours", "member_qualifications", "club_role_types", "club_roles",
    "volunteer_roles",
)
LIFESPAN_COLUMNS = (
    "ALTER TABLE fee_members ADD COLUMN IF NOT EXISTS member_category TEXT",
)


def lifespan_extras() -> list[str]:
    src = (Path(__file__).resolve().parent.parent / "app" / "main.py").read_text()
    out = []
    for t in LIFESPAN_TABLES:
        m = re.search(r"(CREATE TABLE IF NOT EXISTS " + t + r" \([\s\S]*?\n\s*\)\n)", src)
        if m:
            out.append(m.group(1).rstrip())
        else:
            MISSING.append(f"lifespan DDL for {t}")
    return out + list(LIFESPAN_COLUMNS)


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)
        for stmt in lifespan_extras():
            await conn.execute(text(stmt))


async def strip_to_pre287() -> None:
    """Take the three columns back off a POPULATED schema, so the migration has
    something to do and something to do it around. Seeded first and stripped
    after, because the ORM writes every mapped column on an insert and cannot
    seed a table it has already been made to forget about."""
    async with engine.begin() as conn:
        for table, col in NEW_COLUMNS:
            await conn.execute(text(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {col}"))


async def seed(session) -> None:
    for oid, name, slug in ((ORG, "Applecross CC", "applecross"),
                            (STATS_ONLY, "Stats Only CC", "stats-only"),
                            (FOREIGN, "Rival CC", "rival")):
        session.add(Organisation(id=oid, name=name, slug=slug))
    await session.flush()
    # Only the first club holds the module that owns the kit sizes. Entitlement
    # is read off `module_overrides` (the denormalised currently-held cache) as
    # well as the per-module rows, so BOTH are seeded — a suite that sets only
    # the row reads as a club holding nothing and every gate check passes for
    # the wrong reason.
    # The four keys buying BetterAdmin actually grants. NOT ["admin"]: that is
    # the billable umbrella and never appears in a club's entitlement set, so a
    # club seeded with it reads as holding nothing.
    for oid, mods in ((ORG, ["fees", "comms", "merch", "crm"]), (STATS_ONLY, [])):
        o = await session.get(Organisation, oid)
        o.module_overrides = mods
    session.add(OrgModuleSubscription(organisation_id=ORG, module_key="fees", status="active"))
    session.add(OrgModuleSubscription(organisation_id=STATS_ONLY, module_key="fees", status="cancelled"))
    session.add(Player(id=PLAYER, organisation_id=ORG, name="Hind, Darren"))
    session.add(Player(id=LOOSE, organisation_id=ORG, name="Newcomer, Nick"))
    session.add(Player(id=SO_PLAYER, organisation_id=STATS_ONLY, name="Quinsee, Brad"))
    await session.flush()
    session.add(FeeMember(id=COACH, organisation_id=ORG, full_name="Bev the Coach"))
    session.add(FeeMember(id=uuid.uuid4(), organisation_id=ORG, full_name="Hind, Darren", player_id=PLAYER))


async def org_of(session, oid=ORG) -> Organisation:
    """Loaded WITH its module rows: entitlement is read from them, so a club
    fetched without them reads as holding nothing."""
    from sqlalchemy.orm import selectinload
    return await session.get(Organisation, oid, options=[selectinload(Organisation.module_subscriptions)])


async def member_id_for(session, player_id):
    return (await session.execute(text(
        "SELECT id FROM fee_members WHERE organisation_id = :o AND player_id = :p"),
        {"o": ORG, "p": player_id})).scalar_one_or_none()


async def person(session, club_id, key):
    """One person out of the SHIPPED Directory read, by name."""
    rows = await directory_svc.list_people(session, club_id)
    return next((p for p in rows if key in (p["name"] or "")), None)


async def patch_player(session, pid, **body):
    return await players_router.update_player_profile(
        player_id=str(pid), body=players_router.PlayerProfileUpdate(**body), db=session, user=USER)


async def patch_member(session, mid, club_id=ORG, **body):
    return await directory_router.update_member(
        member_id=str(mid), data=directory_router.MemberUpsert(**body),
        _=USER, club=await org_of(session, club_id), db=session)


async def stored(session, table, col, key_col, key):
    return (await session.execute(text(
        f"SELECT {col} FROM {table} WHERE {key_col} = :k"), {"k": key})).scalar_one_or_none()


async def main() -> None:
    if MISSING:
        for m in MISSING:
            check(f"the shipped code is present ({m.split(':')[0]})", False, m)

    print("\n-- migration 287, applied to a populated pre-287 schema --")
    await build_schema()
    async with Session() as session:
        await seed(session)
        await session.commit()
    await strip_to_pre287()
    async with Session() as session:
        before = {t: await columns_of(session, t) for t in ("players", "fee_members")}
        check("the schema really starts without the three columns",
              all(col not in before[t] for t, col in NEW_COLUMNS), str(before))

    stmts = migration_statements()
    check("the migration's upgrade names all three columns",
          len(stmts) == 3 and all(any(c in s for s in stmts) for _, c in NEW_COLUMNS), str(stmts))
    for run in (1, 2, 3):
        async with engine.begin() as conn:
            for s in stmts:
                await conn.execute(text(s))
    async with Session() as session:
        after = {t: await columns_of(session, t) for t in ("players", "fee_members")}
        check("applied three times, every column is present exactly once",
              all(col in after[t] for t, col in NEW_COLUMNS), str(after))
        rows = (await session.execute(text("SELECT COUNT(*) FROM players"))).scalar()
        check("and nothing already in the tables was disturbed", rows == 3, str(rows))
        # The one club-facing consequence of getting the default wrong: every
        # row that existed before must read as "not recorded", never as "".
        check("every pre-287 row reads as no number and no size recorded",
              await stored(session, "players", "shirt_number", "id", PLAYER) is None
              and await stored(session, "fee_members", "shirt_size", "id", COACH) is None)

    mirrors = lifespan_statements()
    check("the app's own boot mirrors the same three ALTERs",
          len(mirrors) == 3 and all(any(c in s for s in mirrors) for _, c in NEW_COLUMNS), str(mirrors))
    async with engine.begin() as conn:
        for s in mirrors:
            await conn.execute(text(s))
    async with Session() as session:
        after2 = {t: await columns_of(session, t) for t in ("players", "fee_members")}
        check("and lands on the same schema the migration does", after2 == after)

    print("\n-- what a shirt number IS --")
    if player_kit:
        n = player_kit.clean_shirt_number
        check('"07" is kept as written, not turned into 7', n(" 07 ") == "07")
        check('"00" survives, which an integer column could not hold', n("00") == "00")
        check("a blank clears rather than storing an empty string", n("") is None and n("   ") is None)
        check("something far too long to be a shirt number is capped",
              len(n("123456789")) == player_kit.SHIRT_NUMBER_MAX)
        k = player_kit.clean_kit_size
        check("a size is free text — no vocabulary is imposed",
              k("Youth 12") == "Youth 12" and k("2XL") == "2XL" and k("34") == "34")
        check("inner whitespace in a size is collapsed rather than stored raw",
              k("Youth   12") == "Youth 12")
        check("a blank size clears", k("") is None)

    print("\n-- the number: Core, on the player, edited from the profile --")
    async with Session() as session:
        await patch_player(session, PLAYER, shirt_number="07")
        check("a number saved on the profile is stored exactly as written",
              await stored(session, "players", "shirt_number", "id", PLAYER) == "07",
              str(await stored(session, "players", "shirt_number", "id", PLAYER)))
        out = await patch_player(session, PLAYER, phone="0400 000 000")
        check("an edit that says nothing about the number leaves it alone",
              await stored(session, "players", "shirt_number", "id", PLAYER) == "07")
        check("and the profile payload carries it back",
              out.get("shirt_number") == "07", str(out.get("shirt_number")))
        was = await stored(session, "players", "shirt_number", "id", PLAYER)
        await patch_player(session, PLAYER, shirt_number="")
        now = await stored(session, "players", "shirt_number", "id", PLAYER)
        # Both halves: a bare "is None" passes on a column that never held
        # anything, which is exactly the state a build without this feature is in.
        check("a present blank clears it", was == "07" and now is None, f"{was} -> {now}")
        await patch_player(session, PLAYER, shirt_number="42")

    print("\n-- a Stats-only club still gets the number --")
    async with Session() as session:
        await patch_player(session, SO_PLAYER, shirt_number="9")
        check("A CLUB WITH NO BETTERADMIN CAN STILL NUMBER ITS PLAYERS",
              await stored(session, "players", "shirt_number", "id", SO_PLAYER) == "9")

    print("\n-- the sizes: BetterAdmin, on the person spine --")
    async with Session() as session:
        await patch_member(session, COACH, shirt_size="XL", pants_size="34")
        check("A NON-PLAYER CAN HOLD A SIZE — a coach gets a club polo too",
              await stored(session, "fee_members", "shirt_size", "id", COACH) == "XL"
              and await stored(session, "fee_members", "pants_size", "id", COACH) == "34")
        await patch_member(session, COACH, email="bev@example.com")
        check("an edit that names neither size leaves both alone",
              await stored(session, "fee_members", "shirt_size", "id", COACH) == "XL"
              and await stored(session, "fee_members", "pants_size", "id", COACH) == "34")
        was = await stored(session, "fee_members", "shirt_size", "id", COACH)
        await patch_member(session, COACH, shirt_size="")
        now = await stored(session, "fee_members", "shirt_size", "id", COACH)
        # Both halves, or the check passes on a column that never held anything.
        check("a present blank clears the one named", was == "XL" and now is None, f"{was} -> {now}")
        check("and leaves the other where it was",
              await stored(session, "fee_members", "pants_size", "id", COACH) == "34")
        await patch_member(session, COACH, shirt_size="XL")

    print("\n-- what the Directory reads back --")
    async with Session() as session:
        p = await person(session, ORG, "Hind")
        check("a linked player's row carries the number off the PLAYER record",
              p and p.get("shirt_number") == "42", str(p and p.get("shirt_number")))
        c = await person(session, ORG, "Bev")
        check("a non-player carries the sizes and NO number to hold",
              c and c.get("shirt_size") == "XL" and c.get("shirt_number") is None, str(c))
        loose = await person(session, ORG, "Newcomer")
        # The KEY has to be there and empty, not merely absent — a payload that
        # never carried it would pass a bare `is None`.
        check("a read-through player with no person row yet reads no sizes",
              loose and "shirt_size" in loose and loose["shirt_size"] is None
              and loose.get("member_id") is None, str(loose))

    print("\n-- the module gate --")
    async with Session() as session:
        payload = await directory_router.list_people(
            include_archived=False, _=USER, club=await org_of(session, ORG), db=session)
        check("a club with BetterAdmin is told the sizes are on", payload.get("kit_sizes") is True,
              str(payload.get("kit_sizes")))
        check("and every person carries the two size keys",
              all("shirt_size" in p and "pants_size" in p for p in payload["people"]))

        so_payload = await directory_router.list_people(
            include_archived=False, _=USER, club=await org_of(session, STATS_ONLY), db=session)
        check("a Stats-only club is told the sizes are off", so_payload.get("kit_sizes") is False,
              str(so_payload.get("kit_sizes")))
        # Paired with the entitled club's payload deliberately: "the keys are
        # absent" is trivially true of a build that never emits them, so the
        # check asserts the DIFFERENCE between the two clubs.
        check("AND NEVER RECEIVES THE VALUES — withheld, not sent and hidden",
              all("shirt_size" not in p and "pants_size" not in p for p in so_payload["people"])
              and all("shirt_size" in p for p in payload["people"]) and len(payload["people"]) > 0,
              str(so_payload["people"][:1]))
        check("while the number still rides on that same payload",
              all("shirt_number" in p for p in so_payload["people"]))

        # A Stats-only club has its own member row to try to write to.
        SO_MEMBER = uuid.uuid4()
        session.add(FeeMember(id=SO_MEMBER, organisation_id=STATS_ONLY, full_name="Quinsee, Brad"))
        await session.commit()
        status = None
        try:
            await patch_member(session, SO_MEMBER, club_id=STATS_ONLY, shirt_size="L")
        except HTTPException as e:
            status = e.status_code
            detail = e.detail
        check("a size from a club without the module is refused", status == 402, str(status))
        check("with the 402 shape the browser already renders as an upsell",
              status == 402 and isinstance(detail, dict) and detail.get("code") == "module_not_entitled"
              and detail.get("module") == "admin"
              and "admin." not in detail.get("message", ""), str(status))
        # The refusal has to have HAPPENED for this to mean anything — a build
        # with no column at all leaves it unwritten for the wrong reason.
        check("and nothing was written",
              status == 402 and await stored(session, "fee_members", "shirt_size", "id", SO_MEMBER) is None)
        # The ordinary edit that club makes every day must be unaffected.
        await patch_member(session, SO_MEMBER, club_id=STATS_ONLY, email="brad@example.com")
        check("an edit that names no size is not refused for that club",
              await stored(session, "fee_members", "email", "id", SO_MEMBER) == "brad@example.com")

    print("\n-- a size recorded against a read-through player mints the row --")
    async with Session() as session:
        mid = await directory_router.ensure_member_for_player(
            player_id=str(LOOSE), _=USER, club=await org_of(session), db=session) \
            if hasattr(directory_router, "ensure_member_for_player") else None
        if mid is None:
            from app.services import members as members_svc
            mid = {"member_id": await members_svc.ensure_for_player(session, ORG, LOOSE)}
            await session.commit()
        await patch_member(session, mid["member_id"], shirt_size="M")
        check("the person row now exists and holds the size",
              await stored(session, "fee_members", "shirt_size", "id", uuid.UUID(str(mid["member_id"]))) == "M")

    print("\n-- cross-club --")
    async with Session() as session:
        status = None
        try:
            await patch_member(session, COACH, club_id=FOREIGN, shirt_size="S")
        except HTTPException as e:
            status = e.status_code
        # Another club naming this person writes nothing: the UPDATE is scoped
        # to the caller's own org, so it matches no row rather than refusing.
        check("another club cannot record a size against our member",
              await stored(session, "fee_members", "shirt_size", "id", COACH) == "XL",
              f"status={status}")

    print("\n-- the bulk profile importer --")
    if profile_import:
        check("shirt_number is an importable field",
              "shirt_number" in profile_import.VALUE_FIELDS)
        check("and is written to the players column of the same name",
              "shirt_number" in profile_import.PLAYER_FIELDS)
        check("a club's own header wording maps to it",
              profile_import.suggest_column_mapping(["Player", "Shirt No"])
              .get("shirt_number", {}).get("column") == "Shirt No",
              str(profile_import.suggest_column_mapping(["Player", "Shirt No"])))
        patch, notes = profile_import.row_profile({"shirt_number": "07"})
        check("a leading zero survives the import", patch.get("shirt_number") == "07", str(patch))
        blank, _ = profile_import.row_profile({"shirt_number": "  "})
        real, _ = profile_import.row_profile({"shirt_number": "9"})
        check("a blank cell never overwrites a stored number",
              "shirt_number" not in blank and real.get("shirt_number") == "9",
              f"{blank} / {real}")
        patch, notes = profile_import.row_profile({"shirt_number": "123456789"})
        check("SOMETHING TOO LONG IS REPORTED, NOT SILENTLY CLIPPED — a clipped "
              "value reads on the team sheet as a number the club chose",
              "shirt_number" not in patch and any("shirt number" in n.lower() for n in notes),
              f"{patch} {notes}")

    await engine.dispose()
    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  FAILED:", f)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
