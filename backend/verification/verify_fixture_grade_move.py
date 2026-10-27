"""Verification: a team the association moves to another grade keeps its work,
against a real Postgres.

Reported: Applecross's 8th XI was moved from One Day Grade 6 to Grade 5. Syncing
fixtures could only re-key a game inside one grade, so the Grade 6 games were
cancelled (or removed) and empty Grade 5 ones created beside them: the picked XI,
the draft, notes and votes stayed behind on a CANCELLED row, a vote medal ticked
for Grade 6 never counted a Grade 5 vote, and "fill from last week" found nothing.

Drives the SHIPPED `sync_fixtures`, `previous_xi` and `squad_sides.replace_sides`.
Only the network is stubbed (`grassroots_scores_client._get`).

Checks:
  * same day + same team of ours, new grade, new opponent -> ONE row, same id, new
    GUID, new grade; team, XI, draft, note and votes intact; status UPCOMING
  * a medal ticked for the old grade counts the new one (and nothing else changes)
  * an all-grades medal and a medal for another grade are left alone
  * a row an earlier sync already CANCELLED because the new grade was unknown
    follows its side too, and the empty twin is removed
  * a twin somebody has started using is never overwritten (kept, row not moved)
  * two rows / two games on one day for one team -> not guessed
  * another team of ours in the OLD grade is untouched
  * past games and manual fixtures are untouched; a re-sync changes nothing
  * `previous_xi` finds last week's XI of the same team in the old grade, by name
  * `replace_sides` swapping a squad's one grade widens the medals the same way

CONTROL MODE: run against the commit BEFORE this change. New keys are read with
`.get`, so the control reports failed checks instead of crashing (rule 21).

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_fixture_grade_move.py
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
    Base, Fixture, FixtureLineup, Grade, Organisation, Player, Season, Team, User,
    VoteBallot, VoteMedal,
)
from app.services import grassroots_scores_client as gr
from app.services import votes as vote_svc
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
        from app.services.team_sides_ddl import STATEMENTS as SIDES_DDL
        for stmt in list(COMP_DDL) + list(DRAFT_DDL) + list(SIDES_DDL):
            await conn.execute(text(stmt))

    from app.routers.fixtures import sync_fixtures
    from app.routers.selection import previous_xi
    from app.services import squad_sides

    org_id, user_id, season_id = US_ORG, uuid.uuid4(), uuid.uuid4()
    G6, G5, G3, G2 = "guid-od6", "guid-od5", "guid-od3", "guid-od2"
    OD6, OD5, OD3, OD2 = (uuid.uuid4() for _ in range(4))
    T8, T9, T10, T3 = (uuid.uuid4() for _ in range(4))
    N8, N9, N10 = "Applecross 8th XI", "Applecross 9th XI", "Applecross 10th XI"
    MEDAL_6, MEDAL_ALL, MEDAL_OTHER, MEDAL_3 = (uuid.uuid4() for _ in range(4))

    async with Session() as db:
        db.add(Organisation(id=org_id, name="Applecross", short_name="Applecross",
                            playhq_id="o-us", slug=f"apple-{org_id.hex[:8]}"))
        db.add(User(id=user_id, username=f"u{user_id.hex[:8]}", email=f"{user_id.hex[:8]}@x.com",
                    password_hash="x"))
        db.add(Season(id=season_id, organisation_id=org_id, name="Summer 2026/27", year=2026))
        await db.flush()
        for gid, guid, nm in ((OD6, G6, "One Day Grade 6"), (OD5, G5, "One Day Grade 5"),
                              (OD3, G3, "One Day Grade 3"), (OD2, G2, "One Day Grade 2")):
            db.add(Grade(id=gid, season_id=season_id, name=nm, grassroots_id=guid))
        await db.flush()
        for tid, nm, seq, gid in ((T8, N8, 8, OD6), (T9, N9, 9, OD6), (T10, N10, 10, OD6), (T3, "Applecross 3rd XI", 3, OD3)):
            db.add(Team(id=tid, organisation_id=org_id, name=nm, sequence=seq, grade_id=gid, source="manual"))
        db.add(VoteMedal(id=MEDAL_6, organisation_id=org_id, name="Grade 6 Medal", grade_ids=[str(OD6)]))
        db.add(VoteMedal(id=MEDAL_ALL, organisation_id=org_id, name="Club Medal", grade_ids=[]))
        db.add(VoteMedal(id=MEDAL_OTHER, organisation_id=org_id, name="Grade 3 Medal", grade_ids=[str(OD3)]))
        db.add(VoteMedal(id=MEDAL_3, organisation_id=org_id, name="Grade 3 Second Medal", grade_ids=[str(OD3)]))
        await db.commit()

    base = date.today() + timedelta(days=14)
    d = lambda n: base + timedelta(days=7 * n)  # noqa: E731

    async def sync():
        gr._grade_matches_cache.clear()
        async with Session() as db:
            club = await db.get(Organisation, org_id)
            user = await db.get(User, user_id)
            return await sync_fixtures(db, club, user)

    async def rows():
        async with Session() as db:
            return list((await db.execute(select(Fixture).where(Fixture.organisation_id == org_id))).scalars().all())

    def by_guid(rs, guid):
        return [r for r in rs if r.playhq_id == guid]

    async def count(sql, **p):
        async with Session() as db:
            return (await db.execute(text(sql), p)).scalar()

    pid = uuid.uuid4()
    async with Session() as db:
        db.add(Player(id=pid, organisation_id=org_id, name="Picked", gender="male", is_player=True, status="active"))
        await db.commit()

    async def pick(fixture_id, *, draft=False, note=None, vote=False):
        async with Session() as db:
            await db.execute(text("DELETE FROM fixture_lineups WHERE fixture_id = :f AND player_id = :p"),
                             {"f": fixture_id, "p": pid})
            db.add(FixtureLineup(fixture_id=fixture_id, player_id=pid, organisation_id=org_id,
                                 batting_order=1, selected_by=user_id))
            if note:
                f = await db.get(Fixture, fixture_id)
                f.notes = note
            if draft:
                await db.execute(text(
                    "INSERT INTO selection_drafts (fixture_id, organisation_id, draft, version) "
                    "VALUES (:f, :o, CAST(:d AS jsonb), 1) ON CONFLICT DO NOTHING"),
                    {"f": fixture_id, "o": org_id, "d": '{"slots": [1]}'})
            if vote:
                db.add(VoteBallot(medal_id=MEDAL_6, organisation_id=org_id, fixture_id=fixture_id,
                                  voter_name="Voter", voter_kind="non_player", source="admin"))
            await db.commit()

    # ---- Draw 1: the three teams in One Day Grade 6 -----------------------------
    DRAW[G6] = [
        match("6-8-r1", d(0), "1", "Rovers", us_name=N8),
        match("6-8-r2", d(1), "2", "Saints", us_name=N8),
        match("6-8-r3", d(2), "3", "Lions", us_name=N8),
        match("6-8-r4", d(3), "4", "Bears", us_name=N8),
        match("6-9-r3", d(2), "3", "Hawks", us_name=N9),
        match("6-9-r4", d(3), "4", "Eagles", us_name=N9),
        match("6-9-r4b", d(3), "4", "Crows", us_name=N9, hh="14:00"),    # a double header
        match("6-10-r2", d(1), "2", "Wolves", us_name=N10),
    ]
    first = await sync()
    check("first sync adds every game", first["synced"], 8)
    rs = await rows()

    r1, r2, r3, r4 = (by_guid(rs, f"6-8-r{i}")[0] for i in (1, 2, 3, 4))
    n3 = by_guid(rs, "6-9-r3")[0]
    n4a, n4b = by_guid(rs, "6-9-r4")[0], by_guid(rs, "6-9-r4b")[0]
    t10 = by_guid(rs, "6-10-r2")[0]
    check("the 8th XI's games are on its squad", {r.team_id for r in (r1, r2, r3, r4)}, {T8})

    # Last week, in Grade 6: played, XI picked, votes cast.
    past_id = uuid.uuid4()
    async with Session() as db:
        db.add(Fixture(id=past_id, organisation_id=org_id, source="grassroots", playhq_id="6-8-past",
                       grade_id=OD6, team_id=T8, played_on=date.today() - timedelta(days=7),
                       status="COMPLETED", opponent_name="Old Opp", home_away="HOME", home_team=N8,
                       away_team="Old Opp CC", round="0"))
        db.add(Fixture(id=uuid.uuid4(), organisation_id=org_id, source="manual", label="Friendly",
                       played_on=d(1), status="UPCOMING"))
        await db.commit()
    await pick(past_id, vote=True)
    # Work the club has done on the games that are about to move.
    await pick(r1.id, vote=True)
    await pick(r2.id, draft=True, note="Bring the covers")
    await pick(r3.id)
    await pick(n3.id, note="9th XI note")        # another team's work, must stay put

    # An earlier fixtures sync, before Grade 5 was known, CANCELLED r4's squad-mate...
    async with Session() as db:
        f = await db.get(Fixture, n4a.id)
        f.status = "CANCELLED"
        await db.commit()
    await pick(n4a.id)

    # ---- Draw 2: CA moves the 8th XI to Grade 5 (same days, new opponents) ---------
    DRAW[G6] = [
        match("6-9-r3", d(2), "3", "Hawks", us_name=N9),
        match("6-10-r2", d(1), "2", "Wolves", us_name=N10),     # the 9th XI's double header is gone
    ]
    DRAW[G5] = [
        match("5-8-r1", d(0), "1", "Tigers", us_name=N8),
        match("5-8-r2", d(1), "2", "Sharks", us_name=N8),
        match("5-8-r3", d(2), "3", "Pumas", us_name=N8),
        match("5-8-r4", d(3), "4", "Owls", us_name=N8),
        # the 9th XI also appears in Grade 5 on a double-header day: two games, two rows
        match("5-9-r4x", d(3), "4", "Kites", us_name=N9),
        match("5-9-r4y", d(3), "4", "Gulls", us_name=N9, hh="14:00"),
    ]
    second = await sync()
    rs = await rows()

    check("the response counts the moved games", second.get("moved"), 4)
    check("the response names the widened medal", second.get("medals_extended"), ["Grade 6 Medal"])
    for old, guid, opp, label in ((r1, "5-8-r1", "Tigers CC", "r1"), (r2, "5-8-r2", "Sharks CC", "r2"),
                                  (r3, "5-8-r3", "Pumas CC", "r3"), (r4, "5-8-r4", "Owls CC", "r4")):
        got = by_guid(rs, guid)
        check(f"{label}: one row on the new GUID, same id", [r.id for r in got], [old.id])
        check(f"{label}: in Grade 5 against the new opponent",
              (got[0].grade_id, got[0].opponent_name) if got else None, (OD5, opp))
        check(f"{label}: still the 8th XI's, not cancelled",
              (got[0].team_id, got[0].status) if got else None, (T8, "UPCOMING"))
        check(f"{label}: old GUID gone", len(by_guid(rs, f"6-8-{label}")), 0)
    check("no fixture is left twice", len([r for r in rs if r.source == "grassroots" and r.round == "1"
                                            and r.played_on == d(0)]), 1)
    check("r1: XI and vote stay on the row",
          (await count("SELECT COUNT(*) FROM fixture_lineups WHERE fixture_id = :f", f=r1.id),
           await count("SELECT COUNT(*) FROM vote_ballots WHERE fixture_id = :f", f=r1.id)), (1, 1))
    check("r2: draft and note stay on the row",
          (await count("SELECT COUNT(*) FROM selection_drafts WHERE fixture_id = :f", f=r2.id),
           [x.notes for x in rs if x.id == r2.id][0]), (1, "Bring the covers"))
    check("r3: XI stays on the row", await count("SELECT COUNT(*) FROM fixture_lineups WHERE fixture_id = :f", f=r3.id), 1)

    # Medals
    async with Session() as db:
        club_medals = {m.name: m for m in (await db.execute(select(VoteMedal).where(VoteMedal.organisation_id == org_id))).scalars().all()}
        allowed6 = await vote_svc.medal_grade_ids(db, org_id, club_medals["Grade 6 Medal"])
        allowed3 = await vote_svc.medal_grade_ids(db, org_id, club_medals["Grade 3 Medal"])
        r1_row = await db.get(Fixture, r1.id)
        grade_by = await vote_svc.effective_grade_ids(db, [r1_row])
        check("the Grade 6 medal counts Grade 5 now", str(OD5) in (allowed6 or set()), True)
        check("the Grade 6 medal still counts Grade 6", str(OD6) in (allowed6 or set()), True)
        check("the moved fixture's votes are inside that medal",
              vote_svc.medal_covers(allowed6, grade_by.get(str(r1.id))), True)
        check("the all-grades medal is left alone", club_medals["Club Medal"].grade_ids, [])
        check("a medal for another grade is left alone", sorted(allowed3 or []), [str(OD3)])

    # Other teams
    check("the 10th XI's game in the old grade is untouched",
          (len(by_guid(rs, "6-10-r2")), by_guid(rs, "6-10-r2")[0].id, by_guid(rs, "6-10-r2")[0].grade_id),
          (1, t10.id, OD6))
    check("the 9th XI keeps its Grade 6 games and their work",
          (by_guid(rs, "6-9-r3")[0].id, by_guid(rs, "6-9-r3")[0].notes), (n3.id, "9th XI note"))
    # Two rows or two games for one team on one day: not guessed
    check("double header: neither 9th XI row is re-keyed (the one with work stays, the empty one goes)",
          (len(by_guid(rs, "6-9-r4")), len(by_guid(rs, "6-9-r4b"))), (1, 0))
    check("double header: the cancelled 9th XI row keeps its XI",
          await count("SELECT COUNT(*) FROM fixture_lineups WHERE fixture_id = :f", f=n4a.id), 1)
    check("double header: both Grade 5 games exist as their own rows",
          (len(by_guid(rs, "5-9-r4x")), len(by_guid(rs, "5-9-r4y"))), (1, 1))
    # Untouchable
    check("past fixture untouched", [(r.grade_id, r.status) for r in rs if r.id == past_id], [(OD6, "COMPLETED")])
    check("manual fixture untouched", len([r for r in rs if r.label == "Friendly" and r.source == "manual"]), 1)
    check("past fixture keeps its XI and votes",
          (await count("SELECT COUNT(*) FROM fixture_lineups WHERE fixture_id = :f", f=past_id),
           await count("SELECT COUNT(*) FROM vote_ballots WHERE fixture_id = :f", f=past_id)), (1, 1))

    # A re-sync changes nothing
    ids_before = sorted(str(r.id) for r in rs)
    third = await sync()
    rs = await rows()
    check("a re-sync moves nothing", (third.get("moved", 0), third.get("removed", 0), third.get("cancelled", 0)), (0, 0, 0))
    check("a re-sync keeps every row", sorted(str(r.id) for r in rs), ids_before)

    # ---- A cancelled row follows its side; an in-use twin is never overwritten ----
    # The 9th XI moves on its own: its OD6 games are gone and its Grade 5 games on
    # different days, a row already CANCELLED earlier and an EMPTY twin exists.
    async with Session() as db:
        db.add(Fixture(id=uuid.uuid4(), organisation_id=org_id, source="grassroots", playhq_id="5-9-r3",
                       grade_id=OD5, team_id=T9, played_on=d(2), status="UPCOMING", home_away="HOME",
                       home_team=N9, away_team="Bats CC", opponent_name="Bats CC", round="3"))
        f = await db.get(Fixture, n3.id)
        f.status = "CANCELLED"
        await db.commit()
    DRAW[G6] = [m for m in DRAW[G6] if m["id"] not in ("6-9-r3",)]
    DRAW[G5] = DRAW[G5] + [match("5-9-r3", d(2), "3", "Bats", us_name=N9)]
    await sync()
    rs = await rows()
    got = by_guid(rs, "5-9-r3")
    check("cancelled row follows the move: one row, the older id", [r.id for r in got], [n3.id])
    check("cancelled row: back to UPCOMING in Grade 5", (got[0].status, got[0].grade_id) if got else None, ("UPCOMING", OD5))
    check("cancelled row: its note stayed", got[0].notes if got else None, "9th XI note")

    # ---- previous_xi: by team name, across the grade move --------------------------
    async with Session() as db:
        nofx = Fixture(id=uuid.uuid4(), organisation_id=org_id, source="grassroots", playhq_id="5-8-nosquad",
                       grade_id=OD5, team_id=None, team_pinned=False, played_on=date.today() + timedelta(days=3),
                       status="UPCOMING", home_away="HOME", home_team=N8, away_team="Cats CC",
                       opponent_name="Cats CC", round="x")
        db.add(nofx)
        await db.commit()
        club = await db.get(Organisation, org_id)
        out = await previous_xi(str(nofx.id), db, club)
    check("fill-from-last-week finds the 8th XI's Grade 6 XI by name", out.get("source_fixture_id"), str(past_id))

    # ---- replace_sides: a squad's one team re-pointed widens its medals ----------
    async with Session() as db:
        club_id = org_id
        t = await db.get(Team, T3)
        res = await squad_sides.replace_sides(db, club_id, t, [squad_sides.SideSpec(grade_id=str(OD2))])
        await db.commit()
    check("replace_sides reports the widened medals", sorted(res.get("medals_extended", [])),
          ["Grade 3 Medal", "Grade 3 Second Medal"])
    async with Session() as db:
        m3 = await db.get(VoteMedal, MEDAL_3)
        allowed = await vote_svc.medal_grade_ids(db, org_id, m3)
        check("swapped squad: the medal counts the new grade", str(OD2) in (allowed or set()), True)
        check("swapped squad: and still the old one", str(OD3) in (allowed or set()), True)

    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  -", f)
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
