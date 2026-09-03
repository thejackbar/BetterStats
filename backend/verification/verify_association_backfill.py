"""Filling in every club's grade associations from data we already hold.

Asked for after "waiting a fortnight is not acceptable": resolve this from the
BetterCricket database rather than a Cricket Australia call per club per
season. Two facts make that possible and this suite is what proves they hold —
a CA grade guid is competition-wide, and a club's own grade name is its own
competition.

Runs the SHIPPED functions in `services/association_backfill.py`.

Run:  DATABASE_URL=postgresql+asyncpg://postgres:pg@localhost/bsassoc \
      python verification/verify_association_backfill.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import Base
try:  # guarded so a control run REPORTS the absence rather than crashing
    from app.services import association_backfill as ab
except ImportError:  # pragma: no cover
    ab = None
from app.services.competition_ddl import (
    DOWNGRADE as COMP_DOWNGRADE, STATEMENTS as COMP_DDL,
)
from app.services.competitions import seed_competitions_for_org

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
        print(f"  FAIL {label}{('  — ' + detail) if detail else ''}")


A_WASTCA = "assoc-wastca"
A_PEEL = "assoc-peel"
A_PSWL = "assoc-pswl"

SYNCED = uuid.uuid4()     # a club synced since migration 283 — it has answers
OLD = uuid.uuid4()        # an established club with none at all
MOVER = uuid.uuid4()      # a club that changed association under one name
LONE = uuid.uuid4()       # a club nothing else in the database shares a grade with
DIR_REUSE = uuid.uuid4()  # known only via the Directory, naming an association we already hold
DIR_MINT = uuid.uuid4()   # known only via the Directory, naming one nobody has ever synced
DIR_AMBIG = uuid.uuid4()  # the Directory's name means two different things elsewhere
DIR_MULTI = uuid.uuid4()  # plays in more than one association per the Directory — not our call to make


async def build() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)
        # `create_all` builds club_competitions WITHOUT its gen_random_uuid()
        # server default, so the real DDL's CREATE TABLE IF NOT EXISTS would be
        # a no-op over a table that then refuses every insert. Drop it back to
        # pre-283 first and let the shipped statements build it for real.
        for stmt in COMP_DOWNGRADE:
            await conn.execute(text(stmt))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL, canonical_name TEXT NOT NULL,
                alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)
        """))
        for stmt in COMP_DDL:
            await conn.execute(text(stmt))


async def seed(db) -> None:
    async def ex(sql, **kw):
        await db.execute(text(sql), kw)

    for oid, nm in ((SYNCED, "Synced Club"), (OLD, "Established Club"),
                    (MOVER, "Moved Club"), (LONE, "Lone Club"),
                    (DIR_REUSE, "Directory Reuse Club"),
                    (DIR_MINT, "Directory Mint Club"),
                    (DIR_AMBIG, "Directory Ambiguous Club"),
                    (DIR_MULTI, "Directory Multi Club")):
        await ex("INSERT INTO organisations (id, name, is_active)"
                 " VALUES (:i, :n, true)", i=oid, n=nm)

    # Seasons: three years each, sharing the CA season guids.
    seasons: dict[tuple, uuid.UUID] = {}
    for org in (SYNCED, OLD, MOVER, LONE, DIR_REUSE, DIR_MINT, DIR_AMBIG, DIR_MULTI):
        for year in (2023, 2024, 2025):
            sid = uuid.uuid4()
            seasons[(org, year)] = sid
            await ex("INSERT INTO seasons (id, organisation_id, name, year,"
                     " grassroots_id) VALUES (:i, :o, :n, :y, :g)",
                     i=sid, o=org, n=f"Summer {year}/{str(year+1)[2:]}",
                     y=year, g=f"ca-season-{year}")

    async def grade(org, year, name, guid, assoc=None):
        gid = uuid.uuid4()
        await ex("INSERT INTO grades (id, season_id, name, grassroots_id,"
                 " association_id, association_name)"
                 " VALUES (:i, :s, :n, :g, :a, :an)",
                 i=gid, s=seasons[(org, year)], n=name, g=guid, a=assoc,
                 an="WASTCA" if assoc == A_WASTCA else
                    ("Peel" if assoc == A_PEEL else
                     ("PSWL" if assoc == A_PSWL else None)))
        return gid

    # THE SHARED GRADE. Both clubs play WASTCA 1st Grade, so they carry the
    # same CA guid — only the recently synced club has the association.
    for year in (2023, 2024, 2025):
        await grade(SYNCED, year, "1st Grade", f"guid-1st-{year}", A_WASTCA)
        await grade(OLD, year, "1st Grade", f"guid-1st-{year}")

    # A grade only the established club plays, under a name whose OTHER
    # seasons will be resolved by the guid above — the name phase carries it.
    for year in (2023, 2024, 2025):
        await grade(OLD, year, "One Day Grade 2", f"old-od2-{year}")
    # ... except the current season, which a recent sync did reach.
    await ex("UPDATE grades SET association_id = :a, association_name = 'WASTCA'"
             " WHERE grassroots_id = :g", a=A_WASTCA, g="old-od2-2025")

    # CA's older spelling of the same grade, merged away by the club. The name
    # phase has to fold it, or it stays outside every competition.
    await grade(OLD, 2023, "One Day Grade 2 - East", "old-od2-east-2023")
    await ex("INSERT INTO grade_merge_logs (org_id, canonical_name, alias_name)"
             " VALUES (:o, 'One Day Grade 2', 'One Day Grade 2 - East')", o=OLD)
    # And a sponsor-suffixed season of it.
    await grade(OLD, 2024, "One Day Grade 2 (Solo Energy)", "old-od2-solo-2024")

    # A club that MOVED association under one grade name: the rows we know
    # disagree, so nothing may be written for the year we do not know.
    await grade(MOVER, 2023, "A Grade", "mover-a-2023", A_PEEL)
    await grade(MOVER, 2025, "A Grade", "mover-a-2025", A_PSWL)
    await grade(MOVER, 2024, "A Grade", "mover-a-2024")

    # A club sharing nothing with anybody and holding no association at all:
    # our own data cannot answer it, and it must not be guessed.
    for year in (2023, 2024, 2025):
        await grade(LONE, year, "Premier Grade", f"lone-{year}")

    # A grade elsewhere carrying the SAME association_name under two different
    # ids — the shape a name-based match must refuse, not pick a side of.
    await grade(MOVER, 2023, "Ambiguous League Grade", "ambig-a-2023", A_PEEL)
    await ex("UPDATE grades SET association_name = 'Ambiguous League'"
             " WHERE grassroots_id = 'ambig-a-2023'")
    await grade(LONE, 2023, "Ambiguous League Grade B", "ambig-b-2023", A_PSWL)
    await ex("UPDATE grades SET association_name = 'Ambiguous League'"
             " WHERE grassroots_id = 'ambig-b-2023'")

    # Four clubs known to the Directory, none of which our own sync has ever
    # given a grade association for.
    for year in (2023, 2024, 2025):
        await grade(DIR_REUSE, year, "1st Grade", f"dirreuse-{year}")
        await grade(DIR_MINT, year, "1st Grade", f"dirmint-{year}")
        await grade(DIR_AMBIG, year, "1st Grade", f"dirambig-{year}")
        await grade(DIR_MULTI, year, "1st Grade", f"dirmulti-{year}")

    async def directory(org, assocs):
        await ex(
            "INSERT INTO marketing_clubs (id, grassroots_guid, name, kind,"
            " associations, existing_org_id) VALUES (:i, :g, :n, 'club',"
            " CAST(:a AS JSONB), :o)",
            i=uuid.uuid4(), g=str(org), n="dir-" + str(org)[:8],
            a=json.dumps(assocs), o=org)

    # Names an association a real grade elsewhere is already known by —
    # should REUSE that id, never mint a new one for the same body.
    await directory(DIR_REUSE, [{"id": "rc-wastca", "name": "WASTCA"}])
    # Names an association nobody has ever synced anywhere — mint one.
    await directory(DIR_MINT, [{"id": "rc-999", "name": "Nowhere Cricket Association"}])
    # Names the SAME string two other clubs' real grades disagree about.
    await directory(DIR_AMBIG, [{"id": "rc-amb", "name": "Ambiguous League"}])
    # Plays in more than one — the Directory alone cannot say which one ran
    # any given grade, so this club is left for the API phase entirely.
    await directory(DIR_MULTI, [{"id": "rc-1", "name": "WASTCA"},
                                 {"id": "rc-2", "name": "Peel"}])

    await db.commit()


async def assoc_of(db, guid):
    res = await db.execute(text(
        "SELECT association_id FROM grades WHERE grassroots_id = :g"), {"g": guid})
    return [r[0] for r in res.all()]


async def report() -> None:
    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  FAILED:", f)
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


async def main() -> None:
    await build()
    async with Session() as db:
        await seed(db)

        if ab is None:
            check("the shipped association backfill service exists", False,
                  "app/services/association_backfill.py is missing")
            await report()

        before = (await db.execute(text(
            "SELECT COUNT(*) FROM grades WHERE association_id IS NULL"))).scalar()
        check("the fixture starts with real gaps to close", before == 23, str(before))

        # The batch script's dry run fills inside an open transaction and
        # measures the residual gap BEFORE rolling back. Measuring after the
        # rollback reports the gap it started with, so a dry run would tell an
        # operator nothing would be resolved — pinned here both ways.
        print("\n— a dry run reports the real figures and writes nothing —")
        dry = await ab.propagate_all(db, commit=False)
        seen = (await db.execute(text(
            "SELECT COUNT(*) FROM grades WHERE association_id IS NULL"))).scalar()
        check("the residual gap is visible while the fill is uncommitted",
              seen == 10, str(seen))
        check("and it reports the same fill the real run makes",
              dry["filled_by_grade_guid"] + dry["filled_by_club_grade_name"]
              + dry["filled_by_directory"] == 13,
              str(dry))
        await db.rollback()
        still = (await db.execute(text(
            "SELECT COUNT(*) FROM grades WHERE association_id IS NULL"))).scalar()
        check("but the rollback leaves the database untouched", still == 23, str(still))

        print("\n— our own data, no Cricket Australia call —")
        out = await ab.propagate_all(db)

        check("a club inherits the association for a grade it shares with another",
              await assoc_of(db, "guid-1st-2023") == [A_WASTCA, A_WASTCA],
              str(await assoc_of(db, "guid-1st-2023")))
        check("across every season of that shared grade",
              await assoc_of(db, "guid-1st-2025") == [A_WASTCA, A_WASTCA])
        check("and the guid phase reports what it filled",
              out["filled_by_grade_guid"] >= 3, str(out))

        check("a club's own earlier seasons of a grade inherit from a later one",
              await assoc_of(db, "old-od2-2023") == [A_WASTCA],
              str(await assoc_of(db, "old-od2-2023")))
        check("including CA's older spelling, folded through the club's merge",
              await assoc_of(db, "old-od2-east-2023") == [A_WASTCA],
              str(await assoc_of(db, "old-od2-east-2023")))
        check("and a sponsor-suffixed season of the same grade",
              await assoc_of(db, "old-od2-solo-2024") == [A_WASTCA],
              str(await assoc_of(db, "old-od2-solo-2024")))
        check("the name phase reports what it filled",
              out["filled_by_club_grade_name"] >= 3, str(out))

        print("\n— the Club Directory fills what a club plays in exactly one of —")
        check("a directory name already meant somewhere reuses that id, never mints",
              await assoc_of(db, "dirreuse-2023") == [A_WASTCA]
              and await assoc_of(db, "dirreuse-2025") == [A_WASTCA],
              str(await assoc_of(db, "dirreuse-2023")))
        check("a directory name nobody has synced anywhere is minted, once",
              (await assoc_of(db, "dirmint-2023"))[0] is not None
              and await assoc_of(db, "dirmint-2023") == await assoc_of(db, "dirmint-2025"),
              str(await assoc_of(db, "dirmint-2023")))
        check("the minted id never collides with a real one",
              (await assoc_of(db, "dirmint-2023"))[0]
              not in (A_WASTCA, A_PEEL, A_PSWL))
        check("the directory phase reports what it filled",
              out["filled_by_directory"] >= 6, str(out))
        check("a name that already means two different things is refused",
              await assoc_of(db, "dirambig-2023") == [None],
              str(await assoc_of(db, "dirambig-2023")))
        check("a club playing in more than one association is left for the API",
              await assoc_of(db, "dirmulti-2023") == [None],
              str(await assoc_of(db, "dirmulti-2023")))

        print("\n— and it refuses to guess —")
        check("a club that moved association keeps its unknown year unknown",
              await assoc_of(db, "mover-a-2024") == [None],
              str(await assoc_of(db, "mover-a-2024")))
        check("while the years it does know are untouched",
              await assoc_of(db, "mover-a-2023") == [A_PEEL]
              and await assoc_of(db, "mover-a-2025") == [A_PSWL])
        check("a club nothing else shares a grade with is left for the API",
              await assoc_of(db, "lone-2023") == [None])

        after = (await db.execute(text(
            "SELECT COUNT(*) FROM grades WHERE association_id IS NULL"))).scalar()
        check("so the gap closes from 23 to the 10 nobody can answer",
              after == 10, str(after))

        print("\n— it is safe to run again —")
        second = await ab.propagate_all(db)
        check("a second run writes nothing",
              second["filled_by_grade_guid"] == 0
              and second["filled_by_club_grade_name"] == 0, str(second))
        check("and never overwrites an association we already hold",
              await assoc_of(db, "mover-a-2025") == [A_PSWL])

        print("\n— what is left is exactly what the API phase must fetch —")
        todo = await ab.outstanding_seasons(db)
        orgs = {str(t["org_id"]) for t in todo}
        check("only the clubs our own data could not finish are listed",
              orgs == {str(MOVER), str(LONE), str(DIR_AMBIG), str(DIR_MULTI)},
              str(orgs))
        check("and one club's list can be asked for on its own",
              len(await ab.outstanding_seasons(db, LONE)) == 3,
              str(len(await ab.outstanding_seasons(db, LONE))))

        print("\n— one answer resolves every club holding that grade —")
        filled = await ab.apply_associations(db, {
            "lone-2023": {"id": A_PEEL, "name": "Peel", "shortName": "PCA"}})
        await db.commit()
        check("applying a fetched association writes it", filled == 1, str(filled))
        check("and the club's other seasons follow from our own data next pass",
              (await ab.propagate_all(db))["filled_by_club_grade_name"] == 2)

        print("\n— the grouping it unlocks —")
        out2 = await seed_competitions_for_org(db, OLD)
        await db.commit()
        rows = (await db.execute(text(
            "SELECT COUNT(*) FROM club_competitions WHERE organisation_id = :o"),
            {"o": OLD})).scalar()
        check("the established club now has its competition", rows == 1, str(rows))
        ungrouped = (await db.execute(text(
            "SELECT COUNT(*) FROM grades gr JOIN seasons s ON s.id = gr.season_id"
            " WHERE s.organisation_id = :o AND gr.competition_id IS NULL"),
            {"o": OLD})).scalar()
        check("and every one of its grades is in it", ungrouped == 0, str(ungrouped))
        check("the seeding reports what it did", out2["grades_assigned"] > 0, str(out2))

    await report()


asyncio.run(main())
