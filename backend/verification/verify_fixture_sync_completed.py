"""Verification: Sync fixtures also records games Cricket Australia has already
completed this season, against a real Postgres.

Reported (North Perth): after syncing fixtures nothing before Round 2 appeared, so
Round 1 could not be voted on. The club connected after Round 1 was played, and the
sync kept only UPCOMING/LIVE matches dated today or later, so a played round never
became a `fixtures` row (voting reads played fixtures from that table).

Drives the SHIPPED `sync_fixtures` route body; only the network is stubbed
(`grassroots_scores_client._get`).

Checks:
  * a COMPLETED round before today becomes a fixture row, status COMPLETED, right date
  * upcoming games still sync as before
  * a completed game between two OTHER clubs is not added
  * a row synced earlier as UPCOMING and since played keeps its id and XI, status COMPLETED
  * a later sync leaves played rows alone (no duplicate, nothing removed or cancelled)
  * a hand-typed (manual) fixture is untouched
  * the public/BetterPosts fixture reader (`get_grades_fixtures` default) still returns
    only the draw ahead
  * a played fixture is on the voting fixture list (`list_vote_fixtures`)

CONTROL MODE: run against the commit before this change. Keys are read with `.get`,
so the control reports the missing Round 1 as failed checks instead of crashing.

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_fixture_sync_completed.py
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

from app.models.db import Base, Organisation, User, Grade, Season, Fixture, FixtureLineup, Player
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


def match(mid, day, rnd, opp, *, status_id=0, home=True, other_clubs=False):
    us_org = "o-x1" if other_clubs else str(US_ORG)
    us = {"isHome": home, "displayName": "North Perth CC 1st XI", "owningOrganisation": {"id": us_org}}
    them = {"isHome": not home, "displayName": f"{opp} CC", "owningOrganisation": {"id": f"o-{opp}"}}
    return {
        "id": mid, "statusId": status_id,
        "matchSchedule": [{"startDateTime": f"{day.isoformat()}T10:00:00"}],
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
        for stmt in [*COMP_DDL, *DRAFT_DDL, *SIDES_DDL]:
            await conn.execute(text(stmt))

    from app.routers.fixtures import sync_fixtures

    org_id, user_id, season_id, grade_id = US_ORG, uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    GUID = "guid-np-1st"
    async with Session() as db:
        db.add(Organisation(id=org_id, name="North Perth", short_name="North Perth",
                            playhq_id="o-us", slug=f"np-{org_id.hex[:8]}"))
        db.add(User(id=user_id, username=f"u{user_id.hex[:8]}", email=f"{user_id.hex[:8]}@x.com",
                    password_hash="x"))
        db.add(Season(id=season_id, organisation_id=org_id, name="Summer 2026/27", year=2026))
        await db.flush()
        db.add(Grade(id=grade_id, season_id=season_id, name="1st Grade", grassroots_id=GUID))
        await db.commit()

    R1, R2, R3, R4 = "11111111-0000-0000-0000-000000000001", "11111111-0000-0000-0000-000000000002", \
        "11111111-0000-0000-0000-000000000003", "11111111-0000-0000-0000-000000000004"
    today = date.today()
    r1_day, r2_day, r3_day = today - timedelta(days=21), today - timedelta(days=14), today - timedelta(days=7)
    r4_day = today + timedelta(days=7)

    async def sync():
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

    # Round 2 was synced while it was still ahead, then played. It carries an XI.
    async with Session() as db:
        old_id = uuid.uuid4()
        db.add(Fixture(id=old_id, organisation_id=org_id, source="grassroots", playhq_id=R2,
                       grade_id=grade_id, played_on=r2_day, status="UPCOMING",
                       opponent_name="Wanderers", round="2"))
        db.add(Fixture(id=uuid.uuid4(), organisation_id=org_id, source="manual", label="Friendly",
                       played_on=r3_day, status="UPCOMING"))
        pid = uuid.uuid4()
        db.add(Player(id=pid, organisation_id=org_id, name="Picked", gender="male",
                      is_player=True, status="active"))
        await db.flush()
        db.add(FixtureLineup(fixture_id=old_id, player_id=pid, organisation_id=org_id,
                             batting_order=1, selected_by=user_id))
        await db.commit()

    DRAW[GUID] = [
        match(R1, r1_day, "1", "Rovers", status_id=3),
        match(R2, r2_day, "2", "Wanderers", status_id=3),
        match(R3, r3_day, "3", "Saints", status_id=3, other_clubs=True),
        match(R4, r4_day, "4", "Lions", status_id=0),
    ]

    res = await sync()
    rs = await rows()
    r1 = find(rs, playhq_id=R1)
    check("Round 1 (completed) becomes a fixture row", len(r1), 1)
    check("Round 1 date is the day it was played", r1[0].played_on if r1 else None, r1_day)
    check("Round 1 status is COMPLETED", r1[0].status if r1 else None, "COMPLETED")
    check("Round 1 label and opponent carried", (r1[0].round, r1[0].opponent_name) if r1 else None, ("1", "Rovers CC"))
    check("upcoming Round 4 still syncs", len(find(rs, playhq_id=R4)), 1)
    check("completed game between two other clubs is not added", len(find(rs, playhq_id=R3)), 0)
    r2 = find(rs, playhq_id=R2)
    check("earlier-synced Round 2: still one row, same id", [r.id for r in r2], [old_id])
    check("earlier-synced Round 2: status now COMPLETED", r2[0].status if r2 else None, "COMPLETED")
    async with Session() as db:
        xi = (await db.execute(text("SELECT COUNT(*) FROM fixture_lineups WHERE fixture_id = :f"),
                               {"f": old_id})).scalar()
    check("earlier-synced Round 2: XI intact", xi, 1)
    check("manual fixture untouched", len(find(rs, source="manual", label="Friendly")), 1)
    check("response says how many played games were added", res.get("played_added"), 1)

    # Public / BetterPosts reader stays the draw ahead.
    gr._grade_matches_cache.clear()
    ahead = await gr.get_grades_fixtures([GUID])
    check("default reader returns only the draw ahead", sorted(f["id"] for f in ahead), [R4])
    check("default reader has no played game", [f for f in ahead if f["status"] == "COMPLETED"], [])

    # Second sync: nothing duplicated, nothing removed or cancelled.
    second = await sync()
    rs2 = await rows()
    check("second sync: same row count", len(rs2), len(rs))
    check("second sync: played rows kept as COMPLETED",
          sorted(r.playhq_id for r in rs2 if r.status == "COMPLETED"), [R1, R2])
    check("second sync: nothing removed or cancelled", (second.get("removed"), second.get("cancelled")), (0, 0))
    check("second sync: no played game counted as new", second.get("played_added"), 0)

    # Voting fixture list shows the played round.
    from app.routers import votes as votes_router
    try:
        async with Session() as db:
            club = await db.get(Organisation, org_id)
            user = await db.get(User, user_id)
            out = await votes_router.list_vote_fixtures(
                year=None, grade_id=None, round_key=None, q=None, medal_id=None,
                db=db, club=club, user=user)
        listed = {f.get("round") for f in (out.get("fixtures") or [])}
        print("       voting list rounds:", sorted(str(x) for x in listed))
        check("voting list includes Round 1 and Round 2",
              {str(x).replace("Round ", "").strip() for x in listed} >= {"1", "2"}, True)
    except Exception as e:  # presence-safe: report, do not crash the control
        check(f"voting list readable ({type(e).__name__}: {e})", False, True)

    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
