"""Verification: the Availability matrix carries gender and the current competitions.

BetterSelect feedback (Oct 2026): Availability had no gender filter and no easy way to
leave the Veterans out. `GET /availability/matrix` now sends:

  * `gender` on every player (as recorded; the screen normalises it),
  * `competitions`, `[{id, name}]`: only competitions the club has an upcoming game in,
    in the club's own order,
  * `competitions` on every player: the ids of those their squads play in
    (a squad's grades, resolved through the club's own grade -> competition answer).

Runs the shipped route body against a real Postgres (DATABASE_URL, e.g.
postgresql+asyncpg://...). Keys are read with `.get` so a run against the previous
commit reports what is absent instead of crashing (that run is the control and must fail
the gender and competition checks).

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_availability_competition_gender.py
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
    from app.models.db import (
        Base, ClubCompetition, Fixture, Grade, Organisation, Player, Season, Team, TeamMember,
    )
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
    c_sat, c_vet, c_old = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    g_sat, g_vet, g_old = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    t_sat, t_vet = uuid.uuid4(), uuid.uuid4()
    p_a, p_b, p_c, p_d, p_e = (uuid.uuid4() for _ in range(5))
    async with Session() as s:
        s.add(Organisation(id=org, name=f"Comp {org.hex[:6]}", slug=f"comp-{org.hex[:8]}"))
        await s.flush()
        s.add(Season(id=season, organisation_id=org, name="2026/27"))
        # Display order puts Veterans first so an alphabetical sort would be caught.
        s.add(ClubCompetition(id=c_vet, organisation_id=org, name="Veterans", display_order=1))
        s.add(ClubCompetition(id=c_sat, organisation_id=org, name="Saturday League", display_order=2))
        s.add(ClubCompetition(id=c_old, organisation_id=org, name="Old Cup", display_order=3))
        await s.flush()
        s.add(Grade(id=g_sat, season_id=season, name="Saturday 1sts", categories=["senior"], competition_id=c_sat))
        s.add(Grade(id=g_vet, season_id=season, name="Over 40s", categories=["masters"], competition_id=c_vet))
        s.add(Grade(id=g_old, season_id=season, name="Cup Final", categories=["senior"], competition_id=c_old))
        await s.flush()
        s.add(Team(id=t_sat, organisation_id=org, name="Jensen 1sts", grade_id=g_sat))
        s.add(Team(id=t_vet, organisation_id=org, name="Vets XI", grade_id=g_vet))
        for pid, name, gender in (
            (p_a, "Alan A", "Male"), (p_b, "Beth B", "Female"), (p_c, "Colin C", "M"),
            (p_d, "Dave D", "male"), (p_e, "Erin E", None),
        ):
            s.add(Player(id=pid, name=name, gender=gender, organisation_id=org, is_player=True, status="active"))
        await s.flush()
        for tid, pid in ((t_sat, p_a), (t_sat, p_b), (t_vet, p_c), (t_sat, p_d), (t_vet, p_d)):
            s.add(TeamMember(team_id=tid, player_id=pid, organisation_id=org))
        soon = date.today() + timedelta(days=3)
        s.add(Fixture(id=uuid.uuid4(), organisation_id=org, grade_id=g_sat, team_id=t_sat,
                      source="manual", played_on=soon, opponent_name="Opp"))
        s.add(Fixture(id=uuid.uuid4(), organisation_id=org, grade_id=g_vet, team_id=t_vet,
                      source="manual", played_on=soon, opponent_name="Opp Vets"))
        # Played and over: its competition is not "current".
        s.add(Fixture(id=uuid.uuid4(), organisation_id=org, grade_id=g_old, source="manual",
                      played_on=date.today() - timedelta(days=30), opponent_name="Done"))
        await s.commit()
        club = await s.get(Organisation, org)
        body = await av.availability_matrix(db=s, club=club, juniors=True)

        by_name = {p["display_name"]: p for p in body["players"]}
        sat_id, vet_id = str(c_sat), str(c_vet)

        comps = body.get("competitions")
        check("matrix carries competitions", bool(comps), str(list(body.keys())))
        check("only competitions with an upcoming game are offered (Old Cup is not)",
              [c["name"] for c in comps or []] == ["Veterans", "Saturday League"], str(comps))
        check("competitions come in the club's own order, with ids",
              [c.get("id") for c in comps or []] == [vet_id, sat_id], str(comps))

        def comps_of(n):
            return (by_name.get(n) or {}).get("competitions")

        check("a Saturday-squad player is in the Saturday League only", comps_of("Alan A") == [sat_id], str(comps_of("Alan A")))
        check("a Veterans-squad player is in Veterans only", comps_of("Colin C") == [vet_id], str(comps_of("Colin C")))
        check("a player in both squads carries both",
              sorted(comps_of("Dave D") or []) == sorted([sat_id, vet_id]), str(comps_of("Dave D")))
        check("a player in no squad carries none (and the key is present)", comps_of("Erin E") == [], str(comps_of("Erin E")))
        check("gender is sent as recorded",
              [(by_name.get(n) or {}).get("gender", "<absent>") for n in ("Alan A", "Beth B", "Colin C", "Dave D", "Erin E")]
              == ["Male", "Female", "M", "male", None],
              str([(n, (p or {}).get("gender", "<absent>")) for n, p in by_name.items()]))

        # A name read off appearance history (no team row) resolves by the grade of that name.
        sq_sides = await squad_sides.load(s, org)
        helper = getattr(av, "_current_competitions", None)
        by_date = await av.upcoming_fixtures_by_date(s, org, with_scope=True, hide_juniors=False)
        out = (await helper(s, org, by_date, sq_sides, ["Over 40s", "Mystery Side", "Cup Final"])) if helper else ([], {})
        mapping = out[1]
        check("an appearance-only name resolves through the grade of that name", mapping.get("Over 40s") == {vet_id}, str(mapping))
        check("an unreadable name is in no competition", "Mystery Side" not in mapping, str(mapping))
        check("a grade whose competition has no upcoming game is not current", "Cup Final" not in mapping, str(mapping))

        # Nothing grouped: no competitions, every player still listed with none.
        await s.execute(text("UPDATE grades SET competition_id = NULL WHERE season_id = :s"), {"s": season})
        await s.commit()
        body2 = await av.availability_matrix(db=s, club=club, juniors=True)
        check("a club that has grouped nothing gets an empty list, not an error",
              body2.get("competitions") == [] and all(p.get("competitions") == [] for p in body2["players"]),
              str(body2.get("competitions")))
    await engine.dispose()


if __name__ == "__main__":
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL not set; needs a real Postgres")
        sys.exit(2)
    asyncio.run(main(url))
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)
