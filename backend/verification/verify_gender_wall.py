"""Verification: the women's side of the gender wall, against a real Postgres.

Reported (Gisborne): men were auto-filled into the women's team, and a women's
grade came across as the wrong team. The wall only knew a grade as women's when
BetterFees' `fee_format` was 'women'; a club that classified the grade as
Women's in Manage Grades (`grades.categories`) and never touched fees got no
wall at all.

Checks, through the SHIPPED `assemble_selection` and `_match_team`:
  * a grade classified women's in Manage Grades (no fee_format) walls the fixture
  * a fixture with no grade of its own reads its team's grade
  * a player recorded male is never eligible for a women's fixture, even when a
    mislinked squad lists them
  * men's fixtures are untouched; a mixed grade is not a women's side
  * `_match_team` will not put a women's "2nd XI" on the men's second team

CONTROL MODE: run against the commit before this change; keys are read through
`.get`, so the control reports failed checks rather than crashing.

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_gender_wall.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import verify_selection_same_day as base
from app.models.db import Organisation, User, Player, Team, Grade, Season, Fixture

engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)
check = base.check


async def main():
    await base.build_schema()
    from app.services.selection_draft_ddl import STATEMENTS as DRAFT_DDL
    async with engine.begin() as conn:
        for stmt in DRAFT_DDL:
            await conn.execute(text(stmt))
    from app.services.selection_pool import assemble_selection

    org_id, user_id, season_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    gm, gw, gx = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    tm, tw, tx = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with Session() as db:
        db.add(Organisation(id=org_id, name="Gisborne CC", slug=f"gis-{org_id.hex[:8]}"))
        db.add(User(id=user_id, username=f"u{user_id.hex[:8]}", email=f"{user_id.hex[:8]}@x.com", password_hash="x"))
        db.add(Season(id=season_id, organisation_id=org_id, name="Summer 2026/27", year=2026))
        await db.flush()
        # Classified in Manage Grades only: NO fee_format anywhere.
        db.add(Grade(id=gm, season_id=season_id, name="Mens A Grade", categories=["senior"]))
        db.add(Grade(id=gw, season_id=season_id, name="Womens B Grade", categories=["womens"]))
        db.add(Grade(id=gx, season_id=season_id, name="Social Mixed", categories=["womens", "mixed"]))
        await db.flush()
        db.add(Team(id=tm, organisation_id=org_id, name="Mens A", sequence=1, grade_id=gm))
        db.add(Team(id=tw, organisation_id=org_id, name="Womens B", sequence=2, grade_id=gw))
        db.add(Team(id=tx, organisation_id=org_id, name="Social", sequence=3, grade_id=gx))
        await db.commit()

    d = date.today() + timedelta(days=14)

    async def fixture(gid, tid, label):
        fid = uuid.uuid4()
        async with Session() as db:
            db.add(Fixture(id=fid, organisation_id=org_id, grade_id=gid, team_id=tid, source="manual",
                           played_on=d, start_time="13:00", status="UPCOMING", label=label))
            await db.commit()
        return fid

    async def player(name, gender, squads):
        pid = uuid.uuid4()
        async with Session() as db:
            db.add(Player(id=pid, organisation_id=org_id, name=name, gender=gender, is_player=True,
                          status="active", squad_team_id=squads[0] if squads else None))
            await db.flush()
            for t in squads:
                await db.execute(text(
                    "INSERT INTO team_members (organisation_id, team_id, player_id) VALUES (:o, :t, :p)"),
                    {"o": org_id, "t": t, "p": pid})
            await db.commit()
        return pid

    async def pool(fid):
        async with Session() as db:
            club = await db.get(Organisation, org_id)
            fx = await db.get(Fixture, fid)
            sel = await assemble_selection(db, club, fx)
        return {r["display_name"]: r for r in sel["pool"]}

    fx_w = await fixture(gw, tw, "Womens B")
    fx_w_nograde = await fixture(None, tw, "Womens B (no grade on the fixture)")
    fx_m = await fixture(gm, tm, "Mens A")
    fx_x = await fixture(gx, tx, "Social")

    woman = await player("Wendy Woman", "female", [tw])
    man_in_w = await player("Mick MislinkedMan", "male", [tw])       # mislinked into the women's squad
    man = await player("Max Man", "male", [tm])
    woman_in_m = await player("Wilma InMens", "female", [tm])
    social = await player("Sam Social", "male", [tx])

    p = await pool(fx_w)
    g = lambda name, key: (p.get(name) or {}).get(key)  # noqa: E731
    check("women's fixture: a woman in the women's squad is eligible", g("Wendy Woman", "gender_ok"), True)
    check("women's fixture: a man in a men's squad is walled out", g("Max Man", "gender_ok"), False)
    check("women's fixture: a man mislinked into the women's squad is still walled out",
          g("Mick MislinkedMan", "gender_ok"), False)
    check("women's fixture: a man is not offered as a squad tier player",
          g("Mick MislinkedMan", "tier"), None)

    p = await pool(fx_w_nograde)
    check("fixture with no grade reads its team's grade: man walled out",
          (p.get("Max Man") or {}).get("gender_ok"), False)
    check("fixture with no grade reads its team's grade: woman eligible",
          (p.get("Wendy Woman") or {}).get("gender_ok"), True)

    p = await pool(fx_m)
    check("men's fixture: a man in the men's squad is eligible", (p.get("Max Man") or {}).get("gender_ok"), True)
    check("men's fixture: a woman in the women's squad only is walled out",
          (p.get("Wendy Woman") or {}).get("gender_ok"), False)
    check("men's fixture: the existing squad rule is unchanged for a woman in a men's squad",
          (p.get("Wilma InMens") or {}).get("gender_ok"), True)

    p = await pool(fx_x)
    check("a mixed grade is not a women's side: the man in its squad is eligible",
          (p.get("Sam Social") or {}).get("gender_ok"), True)

    from app.routers.fixtures import _match_team
    teams = [(tm, "Mens A", 1, False), (tw, "Womens B", 2, True), (uuid.uuid4(), "Mens B", 2, False)]
    check("exact name still wins", _match_team("Womens B", teams, True), tw)
    check("women's '2nd XI' does not land on the men's second team (two 2s: ambiguous)",
          _match_team("Gisborne 2nd XI", teams, True), tw)
    only_men = [(tm, "Mens A", 1, False), (uuid.uuid4(), "Mens B", 2, False)]
    check("women's '2nd XI' with only men's teams matches nothing",
          _match_team("Gisborne 2nd XI", only_men, True), None)
    check("men's '2nd XI' skips the women's team and finds the men's",
          _match_team("Gisborne 2nd XI", teams, False) is not None and _match_team("Gisborne 2nd XI", teams, False) != tw, True)
    check("old 3-tuples and no gender keep today's behaviour",
          _match_team("Gisborne 1st XI", [(tm, "Mens A", 1)]), tm)

    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    await engine.dispose()
    sys.exit(1 if base.FAIL else 0)


asyncio.run(main())
