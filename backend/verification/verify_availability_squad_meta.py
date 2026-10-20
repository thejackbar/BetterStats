"""Verification: the Availability Squad filter can tell which squads are worth listing.

The report (BetterSelect feedback, Oct 2026): the Squad filter on Availability
listed every squad and grade name the club has ever had: switched-off squads and
juniors, with Show juniors off. `GET /availability/matrix` now carries
`squad_meta`, `{name: {active, junior}}`, and the screen does the trimming.

Runs the shipped route body against a real Postgres (DATABASE_URL, e.g.
postgresql+asyncpg://...). Keys are read with `.get` so a run against the
previous commit reports what is absent instead of crashing (that run is the
control and must fail the squad_meta checks).

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_availability_squad_meta.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

PASS = FAIL = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}  {detail}")


async def main(db_url: str) -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.models.db import Base, Fixture, Grade, Organisation, Player, Season, Team, TeamMember
    from app.routers import availability as av
    from app.services import squad_sides
    from app.services.selection_rule_ddl import SELECTION_RULE_STATEMENTS
    from app.services.team_sides_ddl import STATEMENTS as SIDES_DDL

    engine = create_async_engine(db_url, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for stmt in list(SELECTION_RULE_STATEMENTS) + list(SIDES_DDL):
            await conn.execute(text(stmt))
        # Lifespan-only tables grade classification reads (copied from the lifespan).
        for stmt in (
            """CREATE TABLE IF NOT EXISTS season_aliases (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL,
                canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                alias_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                undone_at TIMESTAMPTZ)""",
            """CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL, canonical_name TEXT NOT NULL,
                alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)""",
        ):
            await conn.execute(text(stmt))

    org, season = uuid.uuid4(), uuid.uuid4()
    g_sen, g_u11 = uuid.uuid4(), uuid.uuid4()
    t_first, t_off, t_u11, t_cubs = (uuid.uuid4() for _ in range(4))
    async with Session() as s:
        s.add(Organisation(id=org, name=f"Meta {org.hex[:6]}", slug=f"meta-{org.hex[:8]}"))
        await s.flush()
        s.add(Season(id=season, organisation_id=org, name="2026/27"))
        await s.flush()
        s.add(Grade(id=g_sen, season_id=season, name="Saturday 1sts", categories=["senior"]))
        s.add(Grade(id=g_u11, season_id=season, name="Under 11 Red", categories=["junior"]))
        await s.flush()
        s.add(Team(id=t_first, organisation_id=org, name="Jensen 1sts", grade_id=g_sen))
        s.add(Team(id=t_off, organisation_id=org, name="Old XI", is_active=False))
        s.add(Team(id=t_u11, organisation_id=org, name="U11 Red", grade_id=g_u11))
        # A squad whose NAME does not read junior but whose grade is junior.
        s.add(Team(id=t_cubs, organisation_id=org, name="Cubs", grade_id=g_u11))
        await s.flush()
        for i, tid in enumerate((t_first, t_off, t_u11, t_cubs)):
            pid = uuid.uuid4()
            s.add(Player(id=pid, name=f"Player {i}", organisation_id=org, is_player=True, status="active"))
            await s.flush()
            s.add(TeamMember(team_id=tid, player_id=pid, organisation_id=org))
        s.add(Fixture(id=uuid.uuid4(), organisation_id=org, grade_id=g_sen, team_id=t_first,
                      source="manual", played_on=date.today() + timedelta(days=3), opponent_name="Opp"))
        await s.commit()
        club = await s.get(Organisation, org)
        body = await av.availability_matrix(db=s, club=club, juniors=True)

        meta = body.get("squad_meta") or {}
        check("matrix carries squad_meta", bool(meta), str(body.keys()))
        check("every listed squad name has an entry", set(meta) == set(body["all_squads"]) and bool(meta), f"{sorted(meta)} vs {body['all_squads']}")
        check("a live senior squad is active and not junior", meta.get("Jensen 1sts") == {"active": True, "junior": False}, str(meta.get("Jensen 1sts")))
        check("a switched-off team is not active", (meta.get("Old XI") or {}).get("active") is False, str(meta.get("Old XI")))
        check("a squad on a junior grade is junior", (meta.get("U11 Red") or {}).get("junior") is True, str(meta.get("U11 Red")))
        check("a squad named nothing like junior but on a junior grade is junior (grade first)",
              (meta.get("Cubs") or {}).get("junior") is True, str(meta.get("Cubs")))
        check("the old fields are unchanged: all_squads still lists the switched-off squad (screen trims it)",
              "Old XI" in body["all_squads"])

        # A name that is only read off appearance history (no team row): by its own name, fail open.
        sq_sides = await squad_sides.load(s, org)
        helper = getattr(av, "_squad_meta", None)
        extra = (await helper(s, org, sq_sides, ["Gisborne U13 Red", "Gisborne 2nd XI", "Mystery Side"])) if helper else {}
        extra = {k: extra.get(k, {}) for k in ("Gisborne U13 Red", "Gisborne 2nd XI", "Mystery Side")}
        check("appearance-only name that reads junior is junior", extra["Gisborne U13 Red"].get("junior") is True, str(extra))
        check("appearance-only senior name is not junior", extra["Gisborne 2nd XI"].get("junior") is False, str(extra))
        check("an unreadable name fails open (not junior, active)", extra["Mystery Side"] == {"active": True, "junior": False}, str(extra))
    await engine.dispose()


if __name__ == "__main__":
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL not set; needs a real Postgres")
        sys.exit(2)
    asyncio.run(main(url))
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)
