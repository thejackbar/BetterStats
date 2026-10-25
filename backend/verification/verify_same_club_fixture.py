"""Verification: a game between two of the club's OWN teams gets a fixture for each side,
against a real Postgres.

Reported (Applecross, One Day Grade 6 Black): the 8th XI and the 10th XI play each other
next Saturday, and only one of them showed on the BetterSelect fixtures. Cricket Australia
lists that game once, with the club's owning organisation id on BOTH teams. Sync wrote one
`fixtures` row per match, seen from the home side, so the away team had no fixture to
pick an XI for, take availability against or collect votes on.

Drives the SHIPPED `sync_fixtures` route body (the draw is stubbed at `org_grassroots_
fixtures_checked`, as `verify_shared_grade_squads.py` does), plus the real
`services.lineups` functions with the match record stubbed:

  A. the in-house game gives TWO rows on one match GUID: HOME for the home team's squad,
     AWAY for the away team's squad, each naming the other as the opponent
  B. a second sync changes nothing (same two rows, same ids)
  C. a game against another club, and a game whose payload has no organisation ids (two
     names that share a first word), still give ONE row
  D. a club that synced before this fix (one HOME row) gets the AWAY row added and keeps
     its HOME row's id and its picked XI
  E. CA re-issues the in-house game under a new GUID: both rows re-key, ids kept
  F. CA drops the game: the side with a picked XI is kept as CANCELLED, the empty one goes
  G. the Play.Cricket team list: both sides are the club's (`is_club`) and link to
     players; exactly one is `is_ours`; `our_lineup_players(..., home_away=)` returns the
     side asked for, and the old behaviour (first side) when no side is named

CONTROL MODE: against the previous commit A, D, E and G report failed checks (one row, no
AWAY side, the away XI unlinked). New keys are read with `.get` so absence is reported, not
a crash (rule 21).

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_same_club_fixture.py
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

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import verify_selection_same_day as base
from app.models.db import Fixture, FixtureLineup, Grade, Organisation, Player, Season, Team

engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)
check = base.check


async def main():
    await base.build_schema()
    # `fixtures_with_work` (reconcile) reads selection_drafts, which build_schema leaves out.
    from app.services.selection_draft_ddl import STATEMENTS as DRAFT_DDL
    async with engine.begin() as conn:
        for stmt in DRAFT_DDL:
            await conn.execute(text(stmt))
    import app.routers.fixtures as fixtures_r
    from app.services import grassroots_scores_client as gr
    from app.services import lineups

    org, season, grade, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    T8, T10 = uuid.uuid4(), uuid.uuid4()
    OTHER = str(uuid.uuid4())          # another club's owning organisation id
    ours = str(org)                    # our organisations.id IS the CA owning organisation id
    d1 = date.today() + timedelta(days=6)
    async with Session() as db:
        db.add(Organisation(id=org, name="Applecross Cricket Club", short_name="Applecross",
                            slug=f"apple-{org.hex[:8]}"))
        db.add(Season(id=season, organisation_id=org, name="Summer 2026/27", year=2026))
        await db.flush()
        db.add(Grade(id=grade, season_id=season, name="One Day Grade 6 Black", categories=["senior"]))
        await db.flush()
        db.add(Team(id=T8, organisation_id=org, name="Applecross 8th XI", sequence=8, grade_id=grade))
        db.add(Team(id=T10, organisation_id=org, name="Applecross 10th XI", sequence=10))
        await db.flush()
        await db.execute(text(
            "INSERT INTO team_sides (team_id, organisation_id, grade_key, grade_name, position) "
            "VALUES (:t, :o, 'one day grade 6 black', 'One Day Grade 6 Black', 0)"), {"t": T8, "o": org})
        await db.commit()

    def game(gid, home, away, *, home_org=ours, away_org=OTHER, rnd="5"):
        return {"id": gid, "played_at": d1.isoformat(), "time": "12:00", "home_team": home,
                "away_team": away, "home_org_id": home_org, "away_org_id": away_org,
                "db_grade_id": str(grade), "grade_name": "One Day Grade 6 Black",
                "round": rnd, "venue": "V", "status": "UPCOMING"}

    DRAW: list[dict] = []
    LISTING: dict = {}     # what CA said about the grades it read (empty: nothing is judged stale)

    async def fake_games(db, club, force=False):
        return list(DRAW), dict(LISTING)
    fixtures_r.org_grassroots_fixtures_checked = fake_games

    async def sync():
        async with Session() as db:
            return await fixtures_r.sync_fixtures(db=db, club=await db.get(Organisation, org), _user=None)

    async def rows_for(guid):
        async with Session() as db:
            return list((await db.execute(
                select(Fixture).where(Fixture.organisation_id == org, Fixture.playhq_id == guid)
            )).scalars().all())

    def side(rs, home_away):
        return next((r for r in rs if r.home_away == home_away), None)

    # ------------------------------------------------------------------ A
    print("# A. A game between two of the club's own teams gives each side a fixture")
    DRAW[:] = [game("inhouse-1", "Applecross 10th XI", "Applecross 8th XI", away_org=ours)]
    await sync()
    rs = await rows_for("inhouse-1")
    check("two fixtures on the one match GUID", len(rs), 2)
    home, away = side(rs, "HOME"), side(rs, "AWAY")
    check("a HOME row exists", home is not None)
    check("an AWAY row exists", away is not None)
    check("HOME row: the 8th XI is the opponent", getattr(home, "opponent_name", None), "Applecross 8th XI")
    check("AWAY row: the 10th XI is the opponent", getattr(away, "opponent_name", None), "Applecross 10th XI")
    check("HOME row sits on the 10th XI squad (named by the home team)", getattr(home, "team_id", None), T10)
    check("AWAY row sits on the 8th XI squad (the grade's own)", getattr(away, "team_id", None), T8)
    check("both rows carry the CA home and away team names",
          {(r.home_team, r.away_team) for r in rs}, {("Applecross 10th XI", "Applecross 8th XI")})
    check("both rows are on the grade and the date",
          {(r.grade_id, r.played_on) for r in rs}, {(grade, d1)})
    ids_a = {r.home_away: r.id for r in rs}

    # ------------------------------------------------------------------ B
    print("\n# B. Syncing again changes nothing")
    await sync()
    rs = await rows_for("inhouse-1")
    check("still two fixtures", len(rs), 2)
    check("same ids as before", {r.home_away: r.id for r in rs}, ids_a)

    # ------------------------------------------------------------------ C
    print("\n# C. Games that are not in-house still give one row")
    DRAW[:] = [
        game("vs-other", "Applecross 8th XI", "Rivals 8th XI", rnd="6"),
        game("away-other", "Rivals 9th XI", "Applecross 10th XI", home_org=OTHER, away_org=ours, rnd="7"),
        # no organisation ids: two names sharing a first word is NOT proof both are ours
        game("names-only", "Applecross Black", "Applecross Blue", home_org=None, away_org=None, rnd="8"),
    ]
    await sync()
    check("against another club: one row", len(await rows_for("vs-other")), 1)
    check("...from the home side", getattr(side(await rows_for("vs-other"), "HOME"), "opponent_name", None),
          "Rivals 8th XI")
    check("away at another club: one row", len(await rows_for("away-other")), 1)
    check("...from the away side", getattr(side(await rows_for("away-other"), "AWAY"), "opponent_name", None),
          "Rivals 9th XI")
    check("names only, no organisation ids: one row", len(await rows_for("names-only")), 1)

    # ------------------------------------------------------------------ D
    print("\n# D. A club that synced before the fix gets the missing side added")
    legacy_id = uuid.uuid4()
    pid = uuid.uuid4()
    async with Session() as db:
        db.add(Fixture(id=legacy_id, organisation_id=org, grade_id=grade, team_id=T10, source="grassroots",
                       playhq_id="inhouse-legacy", played_on=d1, start_time="12:00", status="UPCOMING",
                       round="9", home_team="Applecross 10th XI", away_team="Applecross 8th XI",
                       home_away="HOME", opponent_name="Applecross 8th XI"))
        db.add(Player(id=pid, organisation_id=org, name="Picked, Pat", gender="male", is_player=True,
                      status="active"))
        await db.flush()
        db.add(FixtureLineup(fixture_id=legacy_id, player_id=pid, organisation_id=org, batting_order=1))
        await db.commit()
    DRAW[:] = [game("inhouse-legacy", "Applecross 10th XI", "Applecross 8th XI", away_org=ours, rnd="9")]
    await sync()
    rs = await rows_for("inhouse-legacy")
    check("the legacy row is now joined by its other side", len(rs), 2)
    check("the old HOME row keeps its id", getattr(side(rs, "HOME"), "id", None), legacy_id)
    async with Session() as db:
        xi = (await db.execute(text("SELECT COUNT(*) FROM fixture_lineups WHERE fixture_id=:f"),
                               {"f": legacy_id})).scalar()
    check("...and its picked XI", xi, 1)
    check("the new row is the AWAY side", getattr(side(rs, "AWAY"), "opponent_name", None), "Applecross 10th XI")

    # ------------------------------------------------------------------ E
    print("\n# E. CA re-issues the in-house game under a new GUID")
    before = {r.home_away: r.id for r in await rows_for("inhouse-1")}
    DRAW[:] = [game("inhouse-1b", "Applecross 10th XI", "Applecross 8th XI", away_org=ours)]
    # CA read the grade and lists the re-issued game in it, so the old GUID is gone from the draw.
    LISTING.update(grades={str(grade): {"inhouse-1b": "UPCOMING"}}, failed=0, others=set())
    await sync()
    after = await rows_for("inhouse-1b")
    check("both rows moved to the new GUID", len(after), 2)
    check("...keeping their ids", {r.home_away: r.id for r in after}, before)
    check("nothing is left on the old GUID", len(await rows_for("inhouse-1")), 0)

    # ------------------------------------------------------------------ F
    print("\n# F. CA drops the game: the side with work is kept, the empty one goes")
    rs = await rows_for("inhouse-1b")
    away_row = side(rs, "AWAY")
    check("(set up) the AWAY row to put an XI on exists", away_row is not None)
    work_row = away_row or (rs[0] if rs else None)       # the previous commit has no AWAY row to pick on
    if work_row is not None:
        async with Session() as db:
            p2 = uuid.uuid4()
            db.add(Player(id=p2, organisation_id=org, name="Other, Sam", gender="male",
                          is_player=True, status="active"))
            await db.flush()
            db.add(FixtureLineup(fixture_id=work_row.id, player_id=p2, organisation_id=org, batting_order=1))
            await db.commit()
    DRAW[:] = []
    # The grade's list was read and no longer carries the game.
    LISTING.update(grades={str(grade): {"some-other-game": "UPCOMING"}}, failed=0, others=set())
    await sync()
    rs = await rows_for("inhouse-1b")
    check("the AWAY side with a picked XI is kept", getattr(side(rs, "AWAY"), "status", None), "CANCELLED")
    check("the HOME side with nothing on it is removed", side(rs, "HOME") is None)
    LISTING.clear()

    # ------------------------------------------------------------------ G
    print("\n# G. The Play.Cricket team list: both sides are the club's, one is the asked-for side")
    HOME_P = [("p-h1", "Hugh Home"), ("p-h2", "Holly Home")]
    AWAY_P = [("p-a1", "Alex Away"), ("p-a2", "Abby Away")]
    pids = {}
    async with Session() as db:
        for guid, nm in HOME_P + AWAY_P:
            first, last = nm.split()
            p = Player(id=uuid.uuid4(), organisation_id=org, name=f"{last}, {first}", gender="male",
                       is_player=True, status="active", grassroots_id=guid)
            db.add(p)
            pids[guid] = p.id
        await db.commit()

    def team(tid, name, plist):
        return {"id": tid, "displayName": name, "owningOrganisation": {"id": ours, "name": "Applecross"},
                "players": [{"participantId": g, "name": n, "roles": ["Captain"] if i == 0 else []}
                            for i, (g, n) in enumerate(plist)]}
    detail = {
        "id": "inhouse-1b", "status": "UPCOMING",
        "teams": [team("t-away", "Applecross 8th XI", AWAY_P), team("t-home", "Applecross 10th XI", HOME_P)],
        "matchSummary": {"teams": [{"id": "t-home", "displayName": "Applecross 10th XI", "isHome": True},
                                   {"id": "t-away", "displayName": "Applecross 8th XI", "isHome": False}]},
        "matchSchedule": [{"startDateTime": f"{d1.isoformat()}T12:00:00"}],
    }

    async def get_detail(mid):
        return detail
    gr.get_match_detail = get_detail

    async def call(**kw):
        async with Session() as db:
            try:
                return await lineups.our_lineup_players(db, await db.get(Organisation, org), "inhouse-1b", **kw)
            except TypeError:
                return None            # the previous commit has no side argument

    async with Session() as db:
        data = await lineups.match_lineups(db, await db.get(Organisation, org), "inhouse-1b", detail=detail)
    by_name = {t["name"]: t for t in data["teams"]}
    check("both sides are flagged as the club's", [t.get("is_club") for t in data["teams"]], [True, True])
    check("exactly one is the 'ours' side", sum(1 for t in data["teams"] if t["is_ours"]), 1)
    check("the home side's players link to our players",
          sorted(p.get("player_id") or "" for p in by_name["Applecross 10th XI"]["players"]),
          sorted(str(pids[g]) for g, _ in HOME_P))
    check("the away side's players link to our players too",
          sorted(p.get("player_id") or "" for p in by_name["Applecross 8th XI"]["players"]),
          sorted(str(pids[g]) for g, _ in AWAY_P))
    got = await call(home_away="AWAY")
    check("our_lineup_players for the AWAY fixture returns the away XI",
          sorted(p["name"] for p in got[0]) if got else None, ["Abby Away", "Alex Away"])
    got = await call(home_away="HOME")
    check("...for the HOME fixture, the home XI",
          sorted(p["name"] for p in got[0]) if got else None, ["Holly Home", "Hugh Home"])
    got = await call()
    check("...with no side named, one XI as before (not both, not none)", len(got[0]) if got else None, 2)

    # a game against another club: unchanged, the club's side is the one asked for or found
    other_detail = {
        "id": "vs", "status": "UPCOMING",
        "teams": [dict(team("t-o", "Rivals 8th XI", [("x1", "Rex Rival")]),
                       owningOrganisation={"id": OTHER, "name": "Rivals"}),
                  team("t-us", "Applecross 8th XI", AWAY_P)],
        "matchSummary": {"teams": []}, "matchSchedule": [],
    }
    async with Session() as db:
        data = await lineups.match_lineups(db, await db.get(Organisation, org), "vs", detail=other_detail)
    flags = {t["name"]: (t["is_ours"], t.get("is_club")) for t in data["teams"]}
    check("against another club only our side is ours", flags["Applecross 8th XI"], (True, True))
    check("...and the opposition is neither", flags["Rivals 8th XI"], (False, False))

    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    if base.FAIL:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
