"""Scored Fantasy rounds that disagree with the draw, against a real Postgres.

Reported (Applecross, Oct 2026): the admin Rounds table showed round 2 as 10 to 11 Oct and round 3 as
17 to 18 Oct (both scored) and round 4 on 7 Nov, but the club's rounds are 10 to 18 Oct (a two day round
played over two weekends) and 24 Oct to 1 Nov. The games of the 24th and 25th were in no round, so Sync
scores read them and nothing scored.

Why: `generate_rounds` never rewrites a scored round, and round numbers come from position in the draw,
so a round scored before the draw was complete stays on its short dates and every later round is
numbered from the wrong place.

Drives the SHIPPED `services/fantasy_realign` and `fantasy_engine` (settle_round, unsettle_round,
generate_rounds, draw_windows), and the two `routers/fantasy` route bodies, with the Cricket Australia
client stubbed to give the draw.

CONTROL: the previous commit has no realign module; everything new is read through presence-safe
accessors, so absence shows as failed checks. The "nothing scores the 24th" check is on both sides.

Run, on its own database:
  DATABASE_URL=postgresql+asyncpg://root@/fantasy_test?host=/var/run/postgresql \
      python verification/verify_fantasy_realign.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.models.db import (
    Base, BattingInnings, FantasyLeague, FantasyManager, FantasyPoolPlayer, FantasyRound, FantasySeason,
    FantasySquad, FantasySquadPlayer, Game, GameAppearance, Organisation,
)
from app.services import fantasy_engine, grassroots_scores_client as gr
from app.routers import fantasy as fantasy_router

try:
    from app.services import fantasy_realign
except ImportError:  # pragma: no cover - control run only
    fantasy_realign = None
try:
    from app.services.competition_ddl import STATEMENTS as COMP_STATEMENTS
except ImportError:  # pragma: no cover
    COMP_STATEMENTS = []

DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)
PASS = FAIL = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")


# Applecross's calendar, anchored on the most recent Sunday so it holds on any day the suite runs.
T0 = date.today() - timedelta(days=(date.today().weekday() + 1) % 7)       # a Sunday on or before today
SAT3, SAT2, SUN2 = T0 - timedelta(22), T0 - timedelta(15), T0 - timedelta(14)
PSAT, PSUN = T0 - timedelta(8), T0 - timedelta(7)
SAT0, SUN0, SAT1, SUN1 = T0 - timedelta(1), T0, T0 + timedelta(6), T0 + timedelta(7)
NEXT = T0 + timedelta(13)

ORG, OPP, GRADE_GUID = uuid.uuid4(), uuid.uuid4(), str(uuid.uuid4())
GRADE, SEASON = uuid.UUID(GRADE_GUID), uuid.uuid4()
SUSH, SHUB, MATE = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
FS_ID = uuid.uuid4()
R1, R2, R3, R4 = (uuid.uuid4() for _ in range(4))
SQ, MGR = uuid.uuid4(), uuid.uuid4()


def match(days):
    return {"id": str(uuid.uuid4()), "status": "COMPLETED", "matchType": "Two Day" if len(days) > 1 else "One Day",
            "round": {"name": "R"}, "matchSchedule": [{"startDateTime": f"{d}T10:00:00"} for d in days],
            "teams": [{"id": str(uuid.uuid4()), "owningOrganisation": {"id": str(ORG)}},
                      {"id": str(uuid.uuid4()), "owningOrganisation": {"id": str(OPP), "name": "Them"}}]}


# The draw: round 1 one day; round 2 a two day game over two Saturdays plus Sundays; round 3 the same a
# week later; round 4 one day. (Bridging two weeks makes 10 to 18 Oct one round and 24 Oct to 1 Nov one.)
DRAW = [match([SAT3]), match([SAT2, PSAT]), match([SUN2]), match([PSUN]),
        match([SAT0, SAT1]), match([SUN0]), match([SUN1]), match([NEXT])]


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        await conn.execute(text("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS amalgamate_seasons BOOLEAN NOT NULL DEFAULT false"))
        for stmt in COMP_STATEMENTS:
            await conn.execute(text(stmt))
        for (tbl,) in (await conn.execute(text(
                "SELECT table_name FROM information_schema.columns WHERE table_schema='public' "
                "AND column_name='id' AND table_name LIKE 'fantasy\\_%' AND data_type='uuid'"))).all():
            await conn.execute(text(f'ALTER TABLE "{tbl}" ALTER COLUMN id SET DEFAULT gen_random_uuid()'))
        for ddl in (
            """CREATE TABLE IF NOT EXISTS season_aliases (id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL, canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                alias_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE, undone_at TIMESTAMPTZ)""",
            """CREATE TABLE IF NOT EXISTS merge_logs (id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID,
                keep_player_id UUID, keep_player_name TEXT, removed_player_id UUID, removed_player_name TEXT, undone_at TIMESTAMPTZ)""",
            """CREATE TABLE IF NOT EXISTS audit_logs (id SERIAL PRIMARY KEY, created_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID,
                user_id UUID, action TEXT, target_type TEXT, target_id TEXT, details JSONB)""",
            "CREATE TABLE IF NOT EXISTS marketing_clubs (id SERIAL PRIMARY KEY, existing_org_id UUID, state TEXT)",
        ):
            await conn.execute(text(ddl))
        for tbl, col in (await conn.execute(text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND data_type = 'json'"))).all():
            await conn.execute(text(f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb USING "{col}"::text::jsonb'))
        for name, sql in view_statements():
            await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
            await conn.execute(text(sql.replace("OR REPLACE ", "")))


async def seed() -> None:
    async with Session() as s:
        s.add_all([Organisation(id=ORG, name="Applecross", slug="apx", is_active=True, state="WA"),
                   Organisation(id=OPP, name="Them CC", slug="them", is_active=True)])
        await s.flush()
        await s.execute(text("INSERT INTO seasons (id, organisation_id, name, year, grassroots_id) VALUES (:i,:o,'Summer',:y,:g)"),
                        {"i": SEASON, "o": ORG, "y": SAT3.year, "g": str(SEASON)})
        await s.execute(text("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
                             "VALUES (:i,:s,'1st Grade',:g,'senior',ARRAY['senior'])"), {"i": GRADE, "s": SEASON, "g": GRADE_GUID})
        for pid, nm in ((SUSH, "Menon, Sushruth"), (SHUB, "Shubham"), (MATE, "Mate, Mick")):
            await s.execute(text("INSERT INTO players (id, organisation_id, name, grassroots_id, status) VALUES (:i,:o,:n,:g,'active')"),
                            {"i": pid, "o": ORG, "n": nm, "g": str(pid)})
        await s.commit()
    async with Session() as s:
        for day, who, runs in ((SAT3, SUSH, 10), (SAT2, SUSH, 40), (SUN2, MATE, 25), (PSAT, SUSH, 30),
                               (SAT0, SUSH, 20), (SUN0, MATE, 15)):
            gid = uuid.uuid4()
            s.add(Game(id=gid, grade_id=GRADE, played_at=day, home_team="Apx", away_team="X", home_org_id=ORG, status="COMPLETED"))
            await s.flush()
            s.add(GameAppearance(game_id=gid, player_id=who, team_name="Apx"))
            s.add(BattingInnings(game_id=gid, player_id=who, innings_number=1, runs=runs, balls=runs, fours=0, sixes=0,
                                 dismissal_type="bowled", not_out=False))
        s.add(FantasySeason(id=FS_ID, organisation_id=ORG, season_year=SAT3.year, name="Fantasy", status="active",
                            scoring={}, rules={"lock_timezone": "Australia/Perth"}))
        await s.flush()
        # The stale rounds, as the admin screen showed them.
        s.add_all([
            FantasyRound(id=R1, fantasy_season_id=FS_ID, organisation_id=ORG, round_number=1, name="Round 1", start_date=SAT3, end_date=SAT3),
            FantasyRound(id=R2, fantasy_season_id=FS_ID, organisation_id=ORG, round_number=2, name="Round 2", start_date=SAT2, end_date=SUN2),
            FantasyRound(id=R3, fantasy_season_id=FS_ID, organisation_id=ORG, round_number=3, name="Round 3", start_date=PSAT, end_date=PSUN),
            FantasyRound(id=R4, fantasy_season_id=FS_ID, organisation_id=ORG, round_number=4, name="Round 4", start_date=NEXT, end_date=NEXT),
        ])
        s.add_all([FantasyPoolPlayer(fantasy_season_id=FS_ID, organisation_id=ORG, player_id=p, role="batter",
                                     base_price=5, current_price=5) for p in (SUSH, SHUB, MATE)])
        await s.commit()
    async with Session() as s:
        fs = await s.get(FantasySeason, FS_ID)
        for rid in (R1, R2, R3):
            await fantasy_engine.settle_round(s, fs, await s.get(FantasyRound, rid))
        await s.commit()
    # Managers who joined after round 3 was settled: no points, no chips, one free transfer.
    async with Session() as s:
        s.add(FantasyManager(id=MGR, organisation_id=ORG, display_name="Xavier"))
        await s.flush()
        lg = FantasyLeague(id=uuid.uuid4(), fantasy_season_id=FS_ID, organisation_id=ORG, kind="global_salary_cap", name="Club ladder")
        s.add(lg)
        await s.flush()
        # Joined while round 4 was the open round (round 3 already scored), as every Applecross manager did.
        s.add(FantasySquad(id=SQ, fantasy_season_id=FS_ID, league_id=lg.id, manager_id=MGR, organisation_id=ORG,
                           team_name="X Team", free_transfers=1, joined_round=4))
        await s.flush()
        s.add_all([FantasySquadPlayer(squad_id=SQ, player_id=SUSH, role="batter", is_captain=True),
                   FantasySquadPlayer(squad_id=SQ, player_id=MATE, role="batter")])
        await s.commit()


async def val(sql, **p):
    async with Session() as s:
        return (await s.execute(text(sql), p)).first()


async def row(rid):
    r = await val("SELECT start_date, end_date, status, scored_at, lock_at, round_number FROM fantasy_rounds WHERE id=:i", i=rid)
    return r


async def stored_points(rid):
    async with Session() as s:
        return {str(a): float(b) for a, b in (await s.execute(text(
            "SELECT player_id, total_points FROM fantasy_player_round_scores WHERE round_id=:r"), {"r": rid})).all()}


async def window_points(start, end):
    async with Session() as s:
        fs = await s.get(FantasySeason, FS_ID)
        got = await fantasy_engine._round_player_scores(s, fs, SimpleNamespace(start_date=start, end_date=end))
    return {k: float(v["total"]) for k, v in got.items()}


async def realign_plan(refresh=False) -> dict:
    if fantasy_realign is None:
        return {"changes": [], "can_apply": False, "missing": True}
    async with Session() as s:
        fs = await s.get(FantasySeason, FS_ID)
        return await fantasy_realign.plan(s, fs, refresh=refresh)


async def main() -> None:
    await build_schema()
    await seed()

    async def fake_matches(grade_guid, *a, **k):
        return DRAW
    gr.get_grade_matches = fake_matches

    async def no_discovery(*a, **k):
        return []
    fantasy_engine._discover_grade_guids = no_discovery

    print("\n-- 1. The state in the screenshots --")
    r2, r3, r4 = await row(R2), await row(R3), await row(R4)
    check("round 2 is stored 10 to 11 Oct, round 3 17 to 18 Oct, both scored; round 4 on 7 Nov",
          (r2[0], r2[1], r2[2]) == (SAT2, SUN2, "scored") and (r3[0], r3[1], r3[2]) == (PSAT, PSUN, "scored")
          and (r4[0], r4[2]) == (NEXT, "upcoming"))
    covering = await val("SELECT COUNT(*) FROM fantasy_rounds WHERE :d BETWEEN start_date AND end_date", d=SAT0)
    check("no round holds the 24th", covering[0] == 0)
    per_round = [await stored_points(rid) for rid in (R1, R2, R3)]
    check("so the 24th and 25th games score for nobody (CONTROL: true on the previous commit too)",
          sum(sum(d.values()) for d in per_round) == (14 + 44 + 29 + 34), str(per_round))
    ft0 = (await val("SELECT free_transfers FROM fantasy_squads WHERE id=:i", i=SQ))[0]

    print("\n-- 2. The plan (read only) --")
    p = await realign_plan()
    by_n = {c["round_number"]: c for c in p["changes"]}
    check("it lists rounds 2 and 3 and no others", sorted(by_n) == [2, 3], str(sorted(by_n)))
    if by_n:
        c2, c3 = by_n.get(2, {}), by_n.get(3, {})
        check("round 2 is a WIDEN: 10 to 11 Oct becomes 10 to 18 Oct", c2.get("kind") == "widen"
              and c2.get("stored") == [SAT2.isoformat(), SUN2.isoformat()] and c2.get("draw") == [SAT2.isoformat(), PSUN.isoformat()], str(c2))
        check("round 3 is a REPLACE: 17 to 18 Oct becomes 24 Oct to 1 Nov", c3.get("kind") == "replace"
              and c3.get("stored") == [PSAT.isoformat(), PSUN.isoformat()] and c3.get("draw") == [SAT0.isoformat(), SUN1.isoformat()], str(c3))
        check("nothing hangs off them, so it can be applied", p["can_apply"] and not c2.get("blockers") and not c3.get("blockers"), str(p))
    else:
        check("the plan exists", False, str(p))
    check("a plan changes nothing", (await row(R3))[2] == "scored" and (await row(R3))[0] == PSAT)

    print("\n-- 3. Manager activity on the round that would be replaced blocks it --")
    async with Session() as s:
        await s.execute(text("INSERT INTO fantasy_squad_round_scores (squad_id, round_id, chip_used, lineup) "
                             "VALUES (:s, :r, 'wildcard', '[]')"), {"s": SQ, "r": R3})
        await s.commit()
    p = await realign_plan()
    c3 = {c["round_number"]: c for c in p["changes"]}.get(3, {})
    check("the plan says why, in words", any("chip" in b for b in c3.get("blockers", [])) and p["can_apply"] is False, str(c3))
    blocked = False
    if fantasy_realign is not None:
        async with Session() as s:
            fs = await s.get(FantasySeason, FS_ID)
            try:
                await fantasy_realign.apply(s, fs)
            except fantasy_realign.RealignBlocked:
                blocked = True
                await s.rollback()
    check("apply refuses", blocked)
    check("and nothing moved", (await row(R3))[2] == "scored" and (await row(R3))[0] == PSAT and (await row(R2))[1] == SUN2)
    async with Session() as s:
        await s.execute(text("DELETE FROM fantasy_squad_round_scores WHERE round_id=:r"), {"r": R3})
        await s.commit()

    print("\n-- 4. It is all or nothing --")
    if fantasy_realign is not None:
        real = fantasy_engine.settle_round

        async def boom(*a, **k):
            raise RuntimeError("scoring failed half way")
        fantasy_engine.settle_round = boom
        failed = False
        async with Session() as s:
            fs = await s.get(FantasySeason, FS_ID)
            try:
                await fantasy_realign.apply(s, fs)
            except RuntimeError:
                failed = True
                await s.rollback()
        fantasy_engine.settle_round = real
        check("a failure part way raises", failed)
        check("and leaves every round exactly as it was", (await row(R2))[:3] == (SAT2, SUN2, "scored")
              and (await row(R3))[:3] == (PSAT, PSUN, "scored") and len(await stored_points(R3)) == 1)
    else:
        check("realign exists", False, "module missing")

    print("\n-- 5. Apply, through the route --")
    ok_route = hasattr(fantasy_router, "realign_apply")
    check("the routes exist", ok_route and hasattr(fantasy_router, "realign_plan"))
    if ok_route:
        async with Session() as s:
            org = await s.get(Organisation, ORG)
        async with Session() as s:
            plan_out = await fantasy_router.realign_plan(str(FS_ID), refresh=False, club=org, db=s, _=None)
        check("GET gives the plan", plan_out["can_apply"] is True and len(plan_out["changes"]) == 2)
        async with Session() as s:
            user = SimpleNamespace(id=uuid.uuid4(), username="jack")
            out = await fantasy_router.realign_apply(str(FS_ID), club=org, user=user, db=s, _=None)
        check("POST reports what it changed", [c["round_number"] for c in out["realigned"]] == [2, 3], str(out))

    print("\n-- 6. The result --")
    r2, r3, r4, r1 = await row(R2), await row(R3), await row(R4), await row(R1)
    check("round 2 is now 10 to 18 Oct, still scored", (r2[0], r2[1], r2[2]) == (SAT2, PSUN, "scored"), str(r2))
    check("round 3 is now 24 Oct to 1 Nov, not scored, nothing confirmed", (r3[0], r3[1], r3[2], r3[3]) == (SAT0, SUN1, "upcoming", None), str(r3))
    check("round 4 is still 7 Nov and still round 4", (r4[0], r4[5]) == (NEXT, 4), str(r4))
    check("round 1 was not touched", (r1[0], r1[2]) == (SAT3, "scored"))
    perth = ZoneInfo("Australia/Perth")
    check("round 3's lock is on its first day (24 Oct), not 17 Oct", r3[4] is not None and r3[4].astimezone(perth).date() == SAT0, str(r3[4]))
    exp2, exp3 = await window_points(SAT2, PSUN), await window_points(SAT0, SUN1)
    got2 = await stored_points(R2)
    check("round 2's points now include the 17th's game (settled again, same as the scorecards give)",
          got2 == exp2 and exp2.get(str(SUSH)) == 44 + 34, f"{got2} vs {exp2}")
    got3 = await stored_points(R3)
    check("round 3 shows running points for the 24th and 25th games (Sushruth 24, Mick 19)",
          got3 == exp3 and exp3.get(str(SUSH)) == 24 and exp3.get(str(MATE)) == 19, f"{got3} vs {exp3}")
    check("the 17th's game is not counted twice", sum(got3.values()) == 24 + 19)
    check("a team that joined after round 3 was settled keeps its free transfer",
          (await val("SELECT free_transfers FROM fantasy_squads WHERE id=:i", i=SQ))[0] == ft0)
    check("rounds are still 1 to 4, no stray round", (await val("SELECT COUNT(*) FROM fantasy_rounds"))[0] == 4)
    jr = (await val("SELECT joined_round FROM fantasy_squads WHERE id=:i", i=SQ))[0]
    check("a team that joined when round 4 was open now scores from round 3, which is open again (REPORTED: it was skipped)",
          jr == 3, str(jr))
    srow = await val("SELECT points FROM fantasy_squad_round_scores WHERE squad_id=:s AND round_id=:r", s=SQ, r=R3)
    check("so it has running points for round 3: captain Sushruth doubled (48) plus Mick 19 = 67",
          srow is not None and float(srow[0]) == 67.0, str(srow))
    tot = (await val("SELECT total_points FROM fantasy_squads WHERE id=:i", i=SQ))[0]
    check("and its total and the ladder show them", float(tot) == 67.0, str(tot))
    audit = await val("SELECT details FROM audit_logs WHERE action = 'fantasy_realign_rounds'")
    check("one audit entry records both changes and how to undo", audit is not None and len(audit[0]["changes"]) == 2
          and "undo" in audit[0], str(audit))

    print("\n-- 7. Safe to run again --")
    p = await realign_plan()
    check("the plan is now empty", p["changes"] == [], str(p))
    if ok_route:
        async with Session() as s:
            try:
                await fantasy_router.realign_apply(str(FS_ID), club=org, user=user, db=s, _=None)
                again = None
            except HTTPException as e:
                again = e.status_code
        check("applying again says there is nothing to do (409)", again == 409, str(again))
    check("and moved nothing", (await row(R3))[:3] == (SAT0, SUN1, "upcoming"))

    print("\n-- 8. A season that was ALREADY realigned (v9.129.21) before this fix, with the stale stamp --")
    LATE = uuid.uuid4()
    async with Session() as s:
        s.add(FantasyManager(id=uuid.uuid4(), organisation_id=ORG, display_name="Late"))
        await s.flush()
        mid = (await s.execute(text("SELECT id FROM fantasy_managers WHERE display_name='Late'"))).scalar()
        lg = (await s.execute(text("SELECT id FROM fantasy_leagues LIMIT 1"))).scalar()
        s.add(FantasySquad(id=LATE, fantasy_season_id=FS_ID, league_id=lg, manager_id=mid, organisation_id=ORG,
                           team_name="Late XI", free_transfers=1, joined_round=4))
        await s.commit()
        # created AFTER the realign: it really did join when round 4 was open, so it keeps 4
        await s.execute(text("UPDATE fantasy_squads SET created_at = NOW() + INTERVAL '1 minute' WHERE id=:i"), {"i": LATE})
        await s.execute(text("UPDATE fantasy_squads SET joined_round = 4 WHERE id=:i"), {"i": SQ})
        await s.commit()
    if fantasy_realign is not None and hasattr(fantasy_realign, "repair_joined_rounds"):
        async with Session() as s:
            fs = await s.get(FantasySeason, FS_ID)
            n = await fantasy_realign.repair_joined_rounds(s, fs)
            await s.commit()
        check("the repair moves the team that joined before the realign", n == 1 and (await val(
            "SELECT joined_round FROM fantasy_squads WHERE id=:i", i=SQ))[0] == 3, str(n))
        check("and leaves a team that joined after it", (await val("SELECT joined_round FROM fantasy_squads WHERE id=:i", i=LATE))[0] == 4)
        async with Session() as s:
            fs = await s.get(FantasySeason, FS_ID)
            again = await fantasy_realign.repair_joined_rounds(s, fs)
        check("a second run changes nothing", again == 0, str(again))
    else:
        check("the repair exists", False, "repair_joined_rounds missing")

    print("\n-- 9. Pressing Sync scores on that already-realigned season heals it and shows the running points --")
    async def no_card(*a, **k):
        return None
    gr.get_match_scorecard = no_card          # the draw's matches have no card here: nothing to read
    async with Session() as s:
        await s.execute(text("UPDATE fantasy_squads SET joined_round = 4, total_points = 0 WHERE id=:i"), {"i": SQ})
        await s.execute(text("DELETE FROM fantasy_squad_round_scores WHERE squad_id=:i"), {"i": SQ})
        await s.commit()
    from app.services import fantasy_live
    async with Session() as s:
        fs = await s.get(FantasySeason, FS_ID)
        res = await fantasy_live.live_pass(s, fs, manual=True,
                                           now=datetime.combine(T0, datetime.min.time(), tzinfo=ZoneInfo("Australia/Perth")).replace(hour=14))
        await s.commit()
    check("the pass ran and says it re-stamped one team", res.get("ran") is True and res.get("teams_rejoined") == 1, str(res))
    check("the team now scores from round 3", (await val("SELECT joined_round FROM fantasy_squads WHERE id=:i", i=SQ))[0] == 3)
    srow = await val("SELECT points FROM fantasy_squad_round_scores WHERE squad_id=:s AND round_id=:r", s=SQ, r=R3)
    check("and has its running points for round 3 straight away (67)", srow is not None and float(srow[0]) == 67.0, str(srow))
    check("the free transfer round stayed unscored", (await row(R3))[2] == "upcoming")

    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
