"""Verification: syncing fixtures removes games Cricket Australia no longer lists,
against a real Postgres.

Reported: after syncing Applecross's fixtures the list showed duplicates. Sync
only ever added or updated by match GUID, so a game CA re-issued under a new
GUID, or called off, stayed on the draw beside the new entry.

This drives the SHIPPED `sync_fixtures` route body. Only the network is stubbed
(`grassroots_scores_client._get`), so the real match-list client, cache,
`fixtures_source` and `fixtures_reconcile` all run.

Checks:
  * same game, new GUID, team/XI picked   -> ONE row, same id, new GUID, XI intact
  * same game, new GUID, nothing picked   -> ONE row, same id, new GUID
  * dropped from the draw, nothing picked -> row removed
  * dropped from the draw, XI picked      -> kept, status CANCELLED, XI intact
  * CA marks it CANCELLED, nothing picked -> row removed
  * duplicate left by the OLD sync (old row + new twin) -> one row, the older id
  * a grade CA failed to answer for       -> its fixtures are left alone
  * manual fixtures and past fixtures     -> never touched
  * two games, same round + opponent      -> not guessed: never re-keyed
  * the second sync sees today's draw, not the 30 minute cache
  * running it again changes nothing

CONTROL MODE: run the same file against the commit BEFORE this change. New keys
are read with `.get`, so the control reports the duplicates as failed checks
instead of crashing (rule 21).

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_fixture_sync_reconcile.py
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

from app.models.db import Base, Organisation, User, Team, Grade, Season, Fixture, FixtureLineup
from app.services import grassroots_scores_client as gr
from app.services.selection_draft_ddl import STATEMENTS as DRAFT_DDL

DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

PASS = FAIL = 0
FAILURES: list[str] = []


def check(label, got, want=True):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        FAILURES.append(f"{label}: got {got!r}, want {want!r}")
        print(f"  FAIL {label}: got {got!r}, want {want!r}")


# ---------------------------------------------------------------- fake CA ----
class _Resp:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._p = payload or {}

    def json(self):
        return self._p


DRAW: dict[str, list[dict]] = {}      # grade guid -> matches
FAIL_GRADES: set[str] = set()          # grade guids answering 500
CALLS: list[str] = []


async def fake_get(url, params=None):
    guid = url.split("/scores/grades/")[1].split("/")[0]
    CALLS.append(guid)
    if guid in FAIL_GRADES:
        return _Resp(500)
    return _Resp(200, {"matches": DRAW.get(guid, [])})


gr._get = fake_get


# The club's real id: since v9.111.0 "is this side ours" is the owning organisation id.
US_ORG = uuid.uuid4()


def match(mid, day, rnd, opp, *, home=True, status_id=0, status="UPCOMING", hh="10:00"):
    us = {"isHome": home, "displayName": "Applecross CC 1st XI", "owningOrganisation": {"id": str(US_ORG)}}
    them = {"isHome": not home, "displayName": f"{opp} CC", "owningOrganisation": {"id": f"o-{opp}"}}
    return {
        "id": mid, "statusId": status_id, "status": status,
        "matchSchedule": [{"startDateTime": f"{day.isoformat()}T{hh}:00"}],
        "teams": [us, them] if home else [them, us],
        "round": {"name": rnd}, "venue": {"name": "Ground"}, "matchType": "One Day",
    }


# ------------------------------------------------------------------ main ----
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
        for stmt in COMP_DDL:
            await conn.execute(text(stmt))
        for stmt in DRAFT_DDL:
            await conn.execute(text(stmt))
        from app.services.team_sides_ddl import STATEMENTS as SIDES_DDL
        for stmt in SIDES_DDL:
            await conn.execute(text(stmt))

    from app.routers.fixtures import sync_fixtures

    org_id, user_id, season_id = US_ORG, uuid.uuid4(), uuid.uuid4()
    GA, GB, GC = "guid-A-1st", "guid-B-2nd", "guid-C-colts"
    A, B, C = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with Session() as db:
        db.add(Organisation(id=org_id, name="Applecross", short_name="Applecross",
                            playhq_id="o-us",   # the id CA gives the club's own teams (match())
                            slug=f"apple-{org_id.hex[:8]}"))
        db.add(User(id=user_id, username=f"u{user_id.hex[:8]}", email=f"{user_id.hex[:8]}@x.com",
                    password_hash="x"))
        db.add(Season(id=season_id, organisation_id=org_id, name="Summer 2026/27", year=2026))
        await db.flush()
        for gid, guid, nm in ((A, GA, "1st Grade"), (B, GB, "2nd Grade"), (C, GC, "Colts")):
            db.add(Grade(id=gid, season_id=season_id, name=nm, grassroots_id=guid))
        await db.commit()

    base = date.today() + timedelta(days=14)
    d = lambda n: base + timedelta(days=7 * n)  # noqa: E731

    async def sync(clear_cache=True):
        if clear_cache:
            gr._grade_matches_cache.clear()
        async with Session() as db:
            club = await db.get(Organisation, org_id)
            user = await db.get(User, user_id)
            return await sync_fixtures(db, club, user)

    async def rows():
        async with Session() as db:
            return list((await db.execute(
                select(Fixture).where(Fixture.organisation_id == org_id))).scalars().all())

    def find(rs, **kw):
        return [r for r in rs if all(getattr(r, k) == v for k, v in kw.items())]

    async def named_xi(fixture_id):
        async with Session() as db:
            pid = uuid.uuid4()
            from app.models.db import Player
            db.add(Player(id=pid, organisation_id=org_id, name="Picked", gender="male",
                          is_player=True, status="active"))
            await db.flush()
            db.add(FixtureLineup(fixture_id=fixture_id, player_id=pid, organisation_id=org_id,
                                 batting_order=1, selected_by=user_id))
            await db.commit()

    async def xi_count(fixture_id):
        async with Session() as db:
            return (await db.execute(text(
                "SELECT COUNT(*) FROM fixture_lineups WHERE fixture_id = :f"), {"f": fixture_id})).scalar()

    # ---- Draw 1: what the club first synced -------------------------------
    DRAW[GA] = [
        match("a-r3-old", d(0), "3", "Rovers"),
        match("a-r4-old", d(1), "4", "Wanderers"),
        match("a-r8-a", d(5), "8", "Saints"),
        match("a-r8-b", d(5), "8", "Saints", hh="14:00"),       # two games, one opponent
    ]
    DRAW[GB] = [
        match("b-r5", d(2), "5", "Lions"),
        match("b-r6", d(3), "6", "Bears"),
        match("b-r9", d(6), "9", "Hawks"),
    ]
    DRAW[GC] = [
        match("c-r7", d(4), "7", "Eagles"),
        match("c-r10", d(7), "10", "Crows"),
    ]
    first = await sync()
    check("first sync adds every game", first["synced"], 9)
    rs = await rows()
    check("first sync: nine rows, none removed", (len(rs), first.get("removed", 0)), (9, 0))

    # Hand-typed and untouchable rows
    async with Session() as db:
        db.add(Fixture(id=uuid.uuid4(), organisation_id=org_id, source="manual", label="Friendly",
                       played_on=d(1), status="UPCOMING"))
        db.add(Fixture(id=uuid.uuid4(), organisation_id=org_id, source="grassroots",
                       playhq_id="past-game", grade_id=A, played_on=date.today() - timedelta(days=9),
                       status="UPCOMING", opponent_name="Old Opp", round="1"))
        await db.commit()

    r3 = find(rs, playhq_id="a-r3-old")[0]
    r4 = find(rs, playhq_id="a-r4-old")[0]
    r5 = find(rs, playhq_id="b-r5")[0]
    r6 = find(rs, playhq_id="b-r6")[0]
    r7 = find(rs, playhq_id="c-r7")[0]
    r8a = find(rs, playhq_id="a-r8-a")[0]
    r8b = find(rs, playhq_id="a-r8-b")[0]
    await named_xi(r3.id)        # XI on the game CA will re-issue
    await named_xi(r6.id)        # XI on the game CA will drop
    await named_xi(r8a.id)       # XI on one of the two same-round games

    # ---- Draw 2: CA reissues, drops and cancels ---------------------------
    DRAW[GA] = [
        match("a-r3-NEW", d(0) + timedelta(days=1), "3", "Rovers"),      # new GUID, moved a day
        match("a-r4-NEW", d(1), "4", "Wanderers"),                       # new GUID
        match("a-r8-x", d(5), "8", "Saints"),                            # two games, both re-issued
        match("a-r8-y", d(5), "8", "Saints", hh="14:00"),
    ]
    DRAW[GB] = [
        match("b-r9", d(6), "9", "Hawks"),                               # r5 and r6 are gone
    ]
    DRAW[GC] = [
        match("c-r7", d(4), "7", "Eagles", status_id=1, status="CANCELLED"),  # called off
        match("c-r10", d(7), "10", "Crows"),
    ]
    # Same call, the cache is warm from draw 1: the button must still read today's draw.
    second = await sync(clear_cache=False)
    rs = await rows()

    r3n = find(rs, playhq_id="a-r3-NEW")
    check("re-issued game with an XI: one row, same id", [r.id for r in r3n], [r3.id])
    check("re-issued game with an XI: old GUID gone", len(find(rs, playhq_id="a-r3-old")), 0)
    check("re-issued game with an XI: XI intact", await xi_count(r3.id), 1)
    check("re-issued game follows CA's new date", (r3n[0].played_on if r3n else None), d(0) + timedelta(days=1))
    r4n = find(rs, playhq_id="a-r4-NEW")
    check("re-issued game, nothing picked: one row, same id", [r.id for r in r4n], [r4.id])
    check("dropped game, nothing picked: removed", len(find(rs, id=r5.id)), 0)
    r6n = find(rs, id=r6.id)
    check("dropped game with an XI: kept", len(r6n), 1)
    check("dropped game with an XI: marked CANCELLED", r6n[0].status if r6n else None, "CANCELLED")
    check("dropped game with an XI: XI intact", await xi_count(r6.id), 1)
    check("game CA cancelled, nothing picked: removed", len(find(rs, id=r7.id)), 0)
    check("no game left twice", len([r for r in rs if r.source == "grassroots" and r.playhq_id in
                                      ("a-r3-old", "a-r3-NEW")]), 1)
    check("manual fixture untouched", len(find(rs, label="Friendly", source="manual")), 1)
    check("past fixture untouched", len(find(rs, playhq_id="past-game")), 1)
    # Two games, one round, one opponent: never guess which is which
    check("same round + opponent: old rows not re-keyed",
          (find(rs, id=r8a.id) or [None])[0] and find(rs, id=r8a.id)[0].playhq_id, "a-r8-a")
    check("same round + opponent: the row with an XI is kept (cancelled)",
          (len(find(rs, id=r8a.id)), find(rs, id=r8a.id)[0].status if find(rs, id=r8a.id) else None),
          (1, "CANCELLED"))
    check("same round + opponent: the empty one is removed", len(find(rs, id=r8b.id)), 0)
    check("same round + opponent: both new games present",
          sorted(r.playhq_id for r in rs if r.playhq_id in ("a-r8-x", "a-r8-y")), ["a-r8-x", "a-r8-y"])
    check("report: removed", second.get("removed"), 3)
    check("report names what changed", all(second.get(k) is not None for k in ("removed", "rekeyed", "cancelled")))
    check("report: rekeyed", second.get("rekeyed"), 2)
    check("report: cancelled", second.get("cancelled"), 2)

    # ---- Idempotent --------------------------------------------------------
    before = sorted((str(r.id), r.playhq_id, r.status) for r in await rows())
    third = await sync()
    after = sorted((str(r.id), r.playhq_id, r.status) for r in await rows())
    check("sync again changes nothing", after, before)
    check("sync again reports nothing removed", (third.get("removed"), third.get("rekeyed"), third.get("cancelled")),
          (0, 0, 0))

    # ---- A grade CA cannot answer for: leave it alone ----------------------
    FAIL_GRADES.add(GB)
    DRAW[GB] = []
    pre = {r.playhq_id for r in await rows() if r.grade_id == B}
    await sync()
    post = {r.playhq_id for r in await rows() if r.grade_id == B}
    check("grade that failed to load keeps its fixtures", (bool(pre), post), (True, pre))
    FAIL_GRADES.clear()

    # ---- The duplicate the OLD sync already left behind ---------------------
    async with Session() as db:
        old_id, twin_id = uuid.uuid4(), uuid.uuid4()
        common = dict(organisation_id=org_id, source="grassroots", grade_id=C, round="11",
                      played_on=d(8), status="UPCOMING", home_away="HOME", opponent_name="Magpies CC",
                      home_team="Applecross CC 1st XI", away_team="Magpies CC")
        db.add(Fixture(id=old_id, playhq_id="c-r11-old", **common))
        db.add(Fixture(id=twin_id, playhq_id="c-r11-NEW", **common))
        await db.commit()
    DRAW[GC] = [match("c-r10", d(7), "10", "Crows"), match("c-r11-NEW", d(8), "11", "Magpies")]
    await sync()
    rs = await rows()
    r11 = [r for r in rs if r.round == "11" and r.source == "grassroots"]
    check("old duplicate: exactly one row remains", len(r11), 1)
    check("old duplicate: it carries the live GUID", r11[0].playhq_id if r11 else None, "c-r11-NEW")

    # ---- A duplicate whose twin already has an XI is not folded away --------
    async with Session() as db:
        o2, t2 = uuid.uuid4(), uuid.uuid4()
        common = dict(organisation_id=org_id, source="grassroots", grade_id=C, round="12",
                      played_on=d(9), status="UPCOMING", home_away="HOME", opponent_name="Kites CC",
                      home_team="Applecross CC 1st XI", away_team="Kites CC")
        db.add(Fixture(id=o2, playhq_id="c-r12-old", **common))
        db.add(Fixture(id=t2, playhq_id="c-r12-NEW", **common))
        await db.commit()
    await named_xi(t2)
    DRAW[GC] = DRAW[GC] + [match("c-r12-NEW", d(9), "12", "Kites")]
    await sync()
    rs = await rows()
    check("twin already in use: its XI survives", await xi_count(t2), 1)
    check("twin already in use: the live row is kept", len(find(rs, id=t2)), 1)
    check("twin already in use: the empty stale one is removed", len(find(rs, id=o2)), 0)

    # ---- A game stored for this club that is another club's ------------------
    # The old name test stamped a neighbour's game in the same grade onto the
    # club. CA still lists it UPCOMING, but the club filter no longer keeps it,
    # so nothing "dropped" it: it has to be recognised as not ours.
    def other(mid, day, rnd):
        m = match(mid, day, rnd, "Rovers")
        m["teams"] = [
            {"isHome": True, "displayName": "Applecross South CC", "owningOrganisation": {"id": "o-south"}},
            {"isHome": False, "displayName": "Rovers CC", "owningOrganisation": {"id": "o-Rovers"}},
        ]
        return m
    async with Session() as db:
        f_plain, f_work = uuid.uuid4(), uuid.uuid4()
        for fid, pid, rnd in ((f_plain, "a-foreign", "20"), (f_work, "a-foreign-xi", "21")):
            db.add(Fixture(id=fid, organisation_id=org_id, source="grassroots", playhq_id=pid, grade_id=A,
                           round=rnd, played_on=d(10), status="UPCOMING", home_away="HOME",
                           opponent_name="Rovers CC", home_team="Applecross South CC", away_team="Rovers CC"))
        await db.commit()
    await named_xi(f_work)
    DRAW[GA] = DRAW[GA] + [other("a-foreign", d(10), "20"), other("a-foreign-xi", d(10), "21")]
    mine_before = {r.playhq_id for r in await rows() if r.source == "grassroots" and r.playhq_id.startswith("a-r")}
    fx = await sync()
    rs = await rows()
    check("another club's game, nobody's work on it: removed", len(find(rs, id=f_plain)), 0)
    check("another club's game with an XI: kept, marked CANCELLED",
          (len(find(rs, id=f_work)), find(rs, id=f_work)[0].status if find(rs, id=f_work) else None),
          (1, "CANCELLED"))
    check("another club's game is never re-keyed onto a real one",
          sorted(r.playhq_id for r in rs if r.id in (f_plain, f_work)), ["a-foreign-xi"])
    check("the club's own games in that grade are untouched",
          {r.playhq_id for r in rs if r.source == "grassroots" and r.playhq_id.startswith("a-r")}, mine_before)
    check("a re-sync does not bring the other club's game back",
          len([r for r in rs if r.playhq_id == "a-foreign"]), 0)

    # ---- A squad set up to cover a grade claims the fixtures drawn in it -----
    # (migration 336). Before this, a synced fixture only found a squad by the
    # name of the team; a squad called "Macs" covering the 1st Grade is no name
    # the draw ever uses.
    from app.services.team_sides_ddl import STATEMENTS as SIDES_DDL
    async with engine.begin() as conn:
        for stmt in SIDES_DDL:
            await conn.execute(text(stmt))
    squad = uuid.uuid4()
    async with Session() as db:
        from app.models.db import Team
        db.add(Team(id=squad, organisation_id=org_id, name="Macs", sequence=1))
        await db.flush()
        await db.execute(text(
            "INSERT INTO team_sides (team_id, organisation_id, grade_key, grade_name, position) "
            "VALUES (:t, :o, '1st grade', '1st Grade', 0)"), {"t": squad, "o": org_id})
        await db.commit()
    DRAW[GA] = DRAW[GA] + [match("a-claimed", d(12), "30", "Hawks")]
    await sync()
    rs = await rows()
    claimed = find(rs, playhq_id="a-claimed")
    check("a new game in a grade the squad covers lands on the squad",
          claimed[0].team_id if claimed else None, squad)

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAILURES:
        print("\n".join(" - " + f for f in FAILURES))
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
