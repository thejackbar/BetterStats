"""Verification: a vote medal follows a team the sync could not pair row to row,
against a real Postgres.

Reported (Applecross, Hullett Medal): the 8th XI moved from One Day Grade 6 to
Grade 5. The old Round 3 row was kept as CANCELLED (an XI was picked on it) and
Grade 5's game sat beside it as its own row, so `fixtures_reconcile` never paired
them and `grade_move.extend_medals` never ran. The medal, ticked for Grade 6 only,
dropped the 8th XI's real game: its players were offered nothing on the voting page.

Drives the SHIPPED `sync_fixtures` and the public voting list (`_open_fixtures`).
Only the network is stubbed (`grassroots_scores_client._get`).

Checks:
  * before the sync the medal does not count Grade 5, and the player is not offered
    the Grade 5 game
  * after it the medal counts Grade 5 too, the player is offered that game and not
    the cancelled one, and the response names the medal
  * an all-grades medal and a medal for another grade are not touched
  * a squad that still plays the old grade (one game washed out, later games live)
    is NOT treated as moved: its medal is not widened
  * a second sync changes nothing

CONTROL MODE: run against the commit BEFORE this change. New keys are read with
`.get`, so the control reports failed checks instead of crashing (rule 21).

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_moved_team_medal_widen.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import (
    Base, Fixture, FixtureLineup, Game, GameAppearance, Grade, Organisation, Player, Season, Team, User,
    VoteMedal,
)
from app.services import grassroots_scores_client as gr
from app.services import votes as vote_svc

DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

PASS = FAIL = 0


def check(label, got, want=True):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}: got {got!r}, want {want!r}")


class _Resp:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._p = payload or {}

    def json(self):
        return self._p


DRAW: dict[str, list[dict]] = {}


async def fake_get(url, params=None):
    guid = url.split("/scores/grades/")[1].split("/")[0]
    return _Resp(200, {"matches": DRAW.get(guid, [])})


gr._get = fake_get
US_ORG = uuid.uuid4()


def match(mid, day, rnd, opp, *, us_name, home=True, hh="10:00"):
    us = {"isHome": home, "displayName": us_name, "owningOrganisation": {"id": str(US_ORG)}}
    them = {"isHome": not home, "displayName": f"{opp} CC", "owningOrganisation": {"id": f"o-{opp}"}}
    return {
        "id": mid, "statusId": 0, "status": "UPCOMING",
        "matchSchedule": [{"startDateTime": f"{day.isoformat()}T{hh}:00"}],
        "teams": [us, them] if home else [them, us],
        "round": {"name": rnd}, "venue": {"name": "Ground"}, "matchType": "One Day",
    }


async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for ddl in (
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
            await conn.execute(text(ddl))
        from app.services.competition_ddl import STATEMENTS as COMP_DDL
        from app.services.selection_draft_ddl import STATEMENTS as DRAFT_DDL
        from app.services.team_sides_ddl import STATEMENTS as SIDES_DDL
        for stmt in list(COMP_DDL) + list(DRAFT_DDL) + list(SIDES_DDL):
            await conn.execute(text(stmt))

    from app.routers import public_votes as pv
    from app.routers.fixtures import sync_fixtures

    org_id, user_id, season_id = US_ORG, uuid.uuid4(), uuid.uuid4()
    G6, G5, G3, G2 = "guid-od6", "guid-od5", "guid-od3", "guid-od2"
    OD6, OD5, OD3, OD2 = (uuid.uuid4() for _ in range(4))
    T8, T3 = uuid.uuid4(), uuid.uuid4()
    N8, N3 = "Applecross 8th XI", "Applecross 3rd XI"
    HULLETT, ALL, GR3, GR2 = (uuid.uuid4() for _ in range(4))
    PRASH = uuid.uuid4()
    yday = date.today() - timedelta(days=1)
    soon = date.today() + timedelta(days=6)

    async with Session() as db:
        db.add(Organisation(id=org_id, name="Applecross", short_name="Applecross", playhq_id="o-us",
                            slug=f"apple-{org_id.hex[:8]}", module_overrides=["select"]))
        db.add(User(id=user_id, username=f"u{user_id.hex[:8]}", email=f"{user_id.hex[:8]}@x.com", password_hash="x"))
        db.add(Season(id=season_id, organisation_id=org_id, name="Summer 2026/27", year=2026))
        await db.flush()
        for gid, guid, nm in ((OD6, G6, "One Day Grade 6"), (OD5, G5, "One Day Grade 5"),
                              (OD3, G3, "One Day Grade 3"), (OD2, G2, "One Day Grade 2")):
            db.add(Grade(id=gid, season_id=season_id, name=nm, grassroots_id=guid))
        await db.flush()
        db.add(Team(id=T8, organisation_id=org_id, name=N8, sequence=8, grade_id=OD6, source="manual"))
        db.add(Team(id=T3, organisation_id=org_id, name=N3, sequence=3, grade_id=OD2, source="manual"))
        db.add(VoteMedal(id=HULLETT, organisation_id=org_id, name="Hullett Medal", grade_ids=[str(OD6)],
                         enabled=True, link_token="tok-h"))
        db.add(VoteMedal(id=ALL, organisation_id=org_id, name="Club Medal", grade_ids=[]))
        db.add(VoteMedal(id=GR3, organisation_id=org_id, name="Grade 3 Medal", grade_ids=[str(OD3)]))
        db.add(VoteMedal(id=GR2, organisation_id=org_id, name="Grade 2 Medal", grade_ids=[str(OD2)]))
        db.add(Player(id=PRASH, organisation_id=org_id, name="Prashant Madan", gender="male", is_player=True, status="active"))
        await db.flush()

        # The 8th XI's Round 3, yesterday. Old row: kept as CANCELLED with an XI on it.
        old_id, new_id = uuid.uuid4(), uuid.uuid4()
        new_game = uuid.uuid4()
        db.add(Game(id=new_game, grade_id=OD5))
        await db.flush()
        db.add(GameAppearance(game_id=new_game, player_id=PRASH, is_captain=False))
        db.add(Fixture(id=old_id, organisation_id=org_id, source="grassroots", playhq_id=str(uuid.uuid4()),
                       grade_id=OD6, team_id=T8, played_on=yday, status="CANCELLED", round="3",
                       opponent_name="Swan Ath Senior Men OD6", home_away="HOME", home_team=N8, away_team="Swan CC"))
        db.add(Fixture(id=new_id, organisation_id=org_id, source="grassroots", playhq_id=str(new_game),
                       grade_id=OD5, team_id=T8, played_on=yday, status="FINAL", round="3",
                       opponent_name="Swan Ath Senior Men OD5", home_away="HOME", home_team=N8, away_team="Swan CC"))
        await db.flush()
        db.add(FixtureLineup(fixture_id=old_id, player_id=PRASH, organisation_id=org_id, batting_order=1))

        # A squad that still plays Grade 2: one game washed out, the next one live. Same day,
        # it also has a game in Grade 3 (it plays both): it has NOT moved.
        wash_id, other_id, later_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        day = date.today() - timedelta(days=8)
        for fid, grade, status, when, guid in (
            (wash_id, OD2, "CANCELLED", day, uuid.uuid4()),
            (other_id, OD3, "FINAL", day, uuid.uuid4()),
            (later_id, OD2, "FINAL", yday, uuid.uuid4()),
        ):
            db.add(Fixture(id=fid, organisation_id=org_id, source="grassroots", playhq_id=str(guid),
                           grade_id=grade, team_id=T3, played_on=when, status=status, round="1",
                           opponent_name="Opp", home_away="HOME", home_team=N3, away_team="Opp CC"))
        await db.commit()

    # CA lists only upcoming games: one for the 8th XI in Grade 5, so the sync has work.
    DRAW[G5] = [match("5-8-r4", soon, "4", "Owls", us_name=N8)]

    async def medal_ids(mid):
        async with Session() as db:
            m = await db.get(VoteMedal, mid)
            return {str(g) for g in (m.grade_ids or [])}

    async def offered():
        async with Session() as db:
            club = await db.get(Organisation, org_id)
            medal = await db.get(VoteMedal, HULLETT)
            prash = await db.get(Player, PRASH)
            fixtures, _ = await pv._open_fixtures(db, club, vote_svc.effective_config(medal), medal, only_for=prash)
            return {str(f.id): state for f, state in fixtures}

    async def sync():
        gr._grade_matches_cache.clear()
        async with Session() as db:
            club = await db.get(Organisation, org_id)
            user = await db.get(User, user_id)
            return await sync_fixtures(db, club, user)

    # ---- Before: the report -----------------------------------------------------
    check("the Hullett Medal counts Grade 6 only", await medal_ids(HULLETT), {str(OD6)})
    before = await offered()
    check("the player is NOT offered the real Grade 5 game", str(new_id) in before, False)
    check("the player is offered the old Grade 6 row (cancelled)", before.get(str(old_id)), "cancelled")

    # ---- The sync -----------------------------------------------------------------
    r1 = await sync()
    check("the sync names the medal it widened", "Hullett Medal" in (r1.get("medals_extended") or []), True)
    check("the Hullett Medal now counts Grade 5 as well", await medal_ids(HULLETT), {str(OD6), str(OD5)})
    after = await offered()
    check("the player is offered the real Grade 5 game, open", after.get(str(new_id)), "open")
    check("the cancelled Grade 6 row is cancelled, never open", after.get(str(old_id)), "cancelled")

    check("an all-grades medal is left alone", await medal_ids(ALL), set())
    check("a medal for an unrelated grade is left alone", await medal_ids(GR3), {str(OD3)})
    check("a squad that still plays its grade is not treated as moved", await medal_ids(GR2), {str(OD2)})

    async with Session() as db:
        old = await db.get(Fixture, old_id)
        n_lineup = (await db.execute(text("SELECT count(*) FROM fixture_lineups WHERE fixture_id = :f"), {"f": old_id})).scalar()
        check("the cancelled row and its XI are kept, not deleted", (old is not None, n_lineup), (True, 1))

    # ---- Again: nothing more to do ------------------------------------------------
    r2 = await sync()
    check("a second sync widens nothing more", r2.get("medals_extended") or [], [])
    check("…and the medal is unchanged", await medal_ids(HULLETT), {str(OD6), str(OD5)})

    await engine.dispose()
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
