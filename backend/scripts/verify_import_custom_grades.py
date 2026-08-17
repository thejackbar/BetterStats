"""Verify the import wizard's "add a historical grade" step against real Postgres.

Exercises the shipped route body (`routers/imports.create_import_grade`) and the
grade matching around it, for a club whose competitions the CA sync never
carried — the Hamilton Veterans case that prompted it (VCV, Border Cup, Peter
Phyland Trophy, a couple of country carnivals).

Run with a live database:
  DATABASE_URL=postgresql+asyncpg://... python3 backend/scripts/verify_import_custom_grades.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, text                                   # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.models.db import Base, Grade, Organisation, Season, User      # noqa: E402
from app.routers.imports import GradeCreateIn, create_import_grade, _org_grade_options  # noqa: E402
from app.services import import_ingest as ingest                       # noqa: E402
from app.services.grade_labels import suggest_category as ingest_category  # noqa: E402

DB = os.environ.get("DATABASE_URL")
PASSES, FAILS = [], []


def check(label, got, want):
    (PASSES if got == want else FAILS).append((label, got, want))
    print(f"{'ok  ' if got == want else 'FAIL'} {label}: {got!r}" + ("" if got == want else f" (wanted {want!r})"))


async def main():
    engine = create_async_engine(DB)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # audit_logs / manual_edit_logs are lifespan-created raw SQL in the app;
        # the import router writes one, so it has to exist here too.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS manual_edit_logs (
                id UUID PRIMARY KEY, organisation_id UUID, user_id UUID, action TEXT,
                target_table TEXT, target_id TEXT, summary TEXT,
                before_data JSONB, after_data JSONB, undone_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT NOW())
        """))
        # The effective-stat views are built by migrations, not create_all.
        # _org_grade_options only reads (id, grade_id) and (game_id, player_id,
        # runs) off them, so a base-table stand-in exercises the same query.
        await conn.execute(text(
            "CREATE OR REPLACE VIEW v_effective_games AS SELECT id, grade_id FROM games"))
        await conn.execute(text(
            "CREATE OR REPLACE VIEW v_effective_batting_innings AS "
            "SELECT game_id, player_id, runs FROM batting_innings"))
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS grade_merge_logs ("
            " id UUID PRIMARY KEY DEFAULT gen_random_uuid(), org_id UUID,"
            " alias_name TEXT, canonical_name TEXT, undone_at TIMESTAMPTZ)"))

    org_id, other_id = uuid.uuid4(), uuid.uuid4()
    user_id = uuid.uuid4()
    async with Session() as db:
        db.add(Organisation(id=org_id, name="Hamilton Veterans CC", slug=f"hvcc-{org_id.hex[:6]}"))
        db.add(Organisation(id=other_id, name="Somebody Else CC", slug=f"else-{other_id.hex[:6]}"))
        db.add(User(id=user_id, username=f"u{user_id.hex[:8]}", email=f"{user_id.hex[:8]}@x.test",
                    password_hash="x"))
        seasons = []
        for year in (2018, 2019, 2020):
            s = Season(id=uuid.uuid4(), organisation_id=org_id, name=f"Summer {year}/{str(year + 1)[2:]}", year=year)
            seasons.append(s)
            db.add(s)
        foreign = Season(id=uuid.uuid4(), organisation_id=other_id, name="Summer 2019/20", year=2019)
        db.add(foreign)
        # One grade the sync did carry, so the "already there" path is exercised.
        db.add(Grade(id=uuid.uuid4(), season_id=seasons[0].id, grassroots_id="gr-1", name="Border Cup"))
        await db.commit()

    async def call(name, season_ids):
        async with Session() as db:
            org = await db.get(Organisation, org_id)
            user = await db.get(User, user_id)
            return await create_import_grade(GradeCreateIn(name=name, season_ids=season_ids), user, org, db)

    # 1. A competition nothing online carries, across the two seasons it was played.
    res = await call("VCV", [str(seasons[1].id), str(seasons[2].id)])
    check("VCV created in both seasons it was played", res["created"], 2)
    check("VCV touched only those seasons", res["seasons"], 2)

    async with Session() as db:
        rows = (await db.execute(
            select(Grade).join(Season, Season.id == Grade.season_id)
            .where(Season.organisation_id == org_id, Grade.name == "VCV")
        )).scalars().all()
    check("both rows are club rows", len(rows), 2)
    check("never marked as synced", [r.grassroots_id for r in rows], [None, None])
    check("season it was not played in stays clean",
          sorted(str(r.season_id) for r in rows), sorted([str(seasons[1].id), str(seasons[2].id)]))
    # suggest_category reads the NAME, and "VCV" says nothing about who plays
    # in it, so it bottoms out at men's senior exactly as a synced grade would.
    # A veterans club wanting Masters sets it on the Grades screen afterwards;
    # guessing it from the club's own name would be a new inference.
    check("classified by name like any other grade", {r.category for r in rows}, {"senior"})
    check("a name that does say so is classified", 
          ingest_category("Over 60s Masters Cup"), "masters")

    # 2. Pressing it twice must not double up.
    again = await call("VCV", [str(seasons[1].id), str(seasons[2].id)])
    check("re-adding creates nothing", again["created"], 0)
    check("re-adding reports what was already there", again["already_existed"], 2)

    # 3. A name the sync already holds in one season fills only the gaps.
    res = await call("Border Cup", [str(s.id) for s in seasons])
    check("existing synced grade left alone, the other seasons filled", res["created"], 2)

    # 4. No seasons named means the whole club, which is what a career sheet needs.
    res = await call("Echuca Carnival", [])
    check("career-scope sheet lands in every season", res["created"], 3)

    # 5. Another club's season is not ours to write to.
    try:
        await call("Peter Phyland Trophy", [str(foreign.id)])
        check("another club's season is refused", "accepted", "refused")
    except Exception as exc:
        check("another club's season is refused", getattr(exc, "status_code", None), 422)
    async with Session() as db:
        leaked = (await db.execute(
            select(Grade).where(Grade.season_id == foreign.id)
        )).scalars().all()
    check("nothing written to the other club", len(leaked), 0)

    # 6. A blank name is not a grade.
    for bad, why in [("", "blank"), ("   ", "spaces"), ("x" * 121, "too long")]:
        try:
            await call(bad, [str(seasons[0].id)])
            check(f"{why} name refused", "accepted", "refused")
        except Exception as exc:
            check(f"{why} name refused", getattr(exc, "status_code", None), 422)

    # 7. The wizard offers it on the next pass, and the sheet label now matches it.
    async with Session() as db:
        options = await _org_grade_options(db, org_id)
    names = sorted(o["name"] for o in options)
    check("new grades are offered by the wizard", names, ["Border Cup", "Echuca Carnival", "VCV"])
    check("a brand-new grade reads as empty, not as coverage",
          [o["games"] for o in options if o["name"] == "VCV"], [0])

    matched = ingest.match_grades(["VCV", "Echuca Carnival"], names)
    check("the sheet's own label now matches exactly",
          [matched["VCV"]["status"], matched["Echuca Carnival"]["status"]], ["exact", "exact"])
    check("and resolves to the grade we just made", matched["VCV"]["grade_name"], "VCV")

    # 8. The club can undo it: nothing has been played, and it is not a synced row.
    async with Session() as db:
        row = (await db.execute(
            select(Grade).join(Season, Season.id == Grade.season_id)
            .where(Season.organisation_id == org_id, Grade.name == "VCV")
        )).scalars().first()
        check("deletable from Manual Entries (no sync marker)", row.grassroots_id, None)

    print(f"\n{len(PASSES)} passed, {len(FAILS)} failed")
    await engine.dispose()
    return 1 if FAILS else 0


if __name__ == "__main__":
    if not DB:
        print("set DATABASE_URL to a throwaway Postgres")
        raise SystemExit(2)
    raise SystemExit(asyncio.run(main()))
