"""Verification: the printed cheat sheet's header grade and "Our edge" list, against a real Postgres.

Reported (Applecross, a One Day Grade 4 fixture vs North Perth): the sheet's top
right said "Twenty20 Div 1" and "Our edge" named players who were not in the picked
XI. The header printed the LAST MEETING's grade (a T20 game) instead of the
fixture's own, and `our_performers` was the whole active squad ranked by runs.

This drives the SHIPPED `iq.opposition_report`. Checks:

  * `fixture.grade_name` is the fixture's own grade, separate from `last_meeting.grade`
  * `selected_only` with a confirmed XI: only picked players, never a bigger scorer who is not picked
  * a pick ranked outside the club's top ten still appears (the filter runs before the cut)
  * a board draft with nothing confirmed is used and labelled `draft`
  * nothing picked: empty lists and status `none`, never the whole squad
  * without `selected_only` the whole squad is still returned (Match Preview and the
    Opposition page use it to PICK the side), and `selected_xi` is absent
  * another club's fixture id yields no fixture header

CONTROL MODE: run against the commit BEFORE this change. `selected_only` is not
accepted there, so `call()` retries without it and the keys are read with `.get`,
so the control reports the old behaviour as failed checks instead of crashing (rule 21).

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_iq_cheatsheet_xi.py
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")
os.environ.setdefault("ANTHROPIC_API_KEY", "")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.models.db import Base, Organisation, Team, Grade, Season, Fixture, Player, FixtureLineup, Game, BattingInnings, BowlingSpell
from app.services.selection_rule_ddl import SELECTION_RULE_STATEMENTS

MAIN = Path(__file__).resolve().parent.parent / "app/main.py"
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


def _create_stmt(table):
    src = MAIN.read_text()
    m = re.search(r"(CREATE TABLE IF NOT EXISTS " + table + r" \([\s\S]*?\n\s*\))", src)
    return m.group(1) if m else None


async def build_schema() -> None:
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
            """CREATE TABLE IF NOT EXISTS org_merge_logs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                source_org_id UUID, source_org_name TEXT NOT NULL,
                target_org_id UUID NOT NULL,
                performed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), undone_at TIMESTAMPTZ)""",
            """CREATE TABLE IF NOT EXISTS import_effective_deltas (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id uuid, player_id uuid, season_id uuid,
                scope text, grade_label text, matches int, batting_innings int, runs int,
                not_outs int, balls_faced int, fifties int, hundreds int,
                ducks int, high_score int, is_hs_not_out boolean,
                fours int, sixes int, batting_minutes int,
                bowling_innings int, wickets int, overs numeric,
                bowling_balls int, runs_conceded int, maidens int,
                best_bowling_wickets int, best_bowling_figures text,
                five_wicket_innings int, wides int, no_balls int,
                catches int, catches_wk int, catches_non_wk int,
                run_outs int, assisted_run_outs int, unassisted_run_outs int,
                stumpings int)""",
        ):
            await conn.execute(text(ddl))
        from app.services.competition_ddl import STATEMENTS as COMP_DDL
        for stmt in COMP_DDL:
            await conn.execute(text(stmt))
        try:
            from app.services.junior_hiding_ddl import STATEMENTS as JUNIOR_DDL
            for stmt in JUNIOR_DDL:
                await conn.execute(text(stmt))
        except ImportError:
            pass
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        json_cols = (await conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type = 'json'"))).all()
        for tbl, col in json_cols:
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb '
                f'USING "{col}"::text::jsonb'))
        for t in ("net_sessions", "net_attendance"):
            stmt = _create_stmt(t)
            if stmt:
                await conn.execute(text(stmt))
        for stmt in SELECTION_RULE_STATEMENTS:
            await conn.execute(text(stmt))
        from app.services.selection_draft_ddl import STATEMENTS as DRAFT_DDL
        for stmt in DRAFT_DDL:
            await conn.execute(text(stmt))
        stmts = view_statements()
        for _ in range(2):
            for name, sql in stmts:
                await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
                await conn.execute(text(sql.replace("OR REPLACE ", "")))


async def main():
    await build_schema()
    from app.services import iq

    today = date.today()
    sat = today + timedelta(days=(5 - today.weekday()) % 7 or 7)
    OPP = "North Perth Cricket Club"

    oid, other = uuid.uuid4(), uuid.uuid4()
    sid, gid_od, gid_t20, tid = (uuid.uuid4() for _ in range(4))
    async with Session() as db:
        for o, n in ((oid, "Applecross"), (other, "Rival")):
            db.add(Organisation(id=o, name=n, slug=f"{n.lower()[:6]}-{o.hex[:8]}"))
        db.add(Season(id=sid, organisation_id=oid, name="Summer 2026/27", year=2026))
        await db.flush()
        db.add(Grade(id=gid_od, season_id=sid, name="One Day Grade 4"))
        db.add(Grade(id=gid_t20, season_id=sid, name="Twenty20 Div 1"))
        await db.flush()
        db.add(Team(id=tid, organisation_id=oid, name="OD4s", sequence=4, grade_id=gid_od))
        await db.commit()

    async def player(o, name):
        pid = uuid.uuid4()
        async with Session() as db:
            db.add(Player(id=pid, organisation_id=o, name=name, is_player=True, gender="MALE"))
            await db.commit()
        return pid

    picked_bat = await player(oid, "Pat Picked")        # in the XI, modest record vs NP
    picked_bowl = await player(oid, "Wes Wicket")       # in the XI, wickets vs NP
    big_unpicked = await player(oid, "Barry Bigscorer")  # NOT in the XI, huge runs vs NP in the T20 game
    star_bowler = await player(oid, "Sam Starbowler")   # NOT in the XI, most wickets vs NP
    fillers = [await player(oid, f"Filler {i:02d}") for i in range(11)]   # 11 unpicked, all out-score the picks
    draft_only = await player(oid, "Dee Draftee")
    rival_bat = await player(other, "Rival Bat")

    async def game(gid, days_ago, rows, spells):
        g = uuid.uuid4()
        async with Session() as db:
            db.add(Game(id=g, grade_id=gid, played_at=today - timedelta(days=days_ago), home_team="Applecross",
                        away_team="North Perth", home_org_id=oid, opp_club_name=OPP, result="LOSS",
                        winning_team="North Perth", status="COMPLETED", venue="Shirley Strickland Reserve"))
            await db.flush()
            for pid, runs in rows:
                db.add(BattingInnings(game_id=g, player_id=pid, innings_number=1, batting_position=3,
                                      runs=runs, balls=runs + 5, not_out=False, dismissal_type="b"))
            for pid, wk, rn in spells:
                db.add(BowlingSpell(game_id=g, player_id=pid, innings_number=2, overs=8.0, maidens=0,
                                    runs=rn, wickets=wk, economy=round(rn / 8.0, 2)))
            await db.commit()

    # An older One Day Grade 4 game, then the MOST RECENT meeting: a T20 game.
    await game(gid_od, 90, [(picked_bat, 22), (rival_bat, 80)], [(picked_bowl, 2, 30)])
    await game(gid_t20, 14,
               [(big_unpicked, 400), (picked_bat, 11), (rival_bat, 60)] + [(f, 150 + i) for i, f in enumerate(fillers)],
               [(star_bowler, 5, 20), (picked_bowl, 1, 41)])

    async def fixture(o, gid, t, opp):
        fid = uuid.uuid4()
        async with Session() as db:
            db.add(Fixture(id=fid, organisation_id=o, source="grassroots", grade_id=gid, team_id=t,
                           played_on=sat, start_time="12:00", status="UPCOMING", opponent_name=opp,
                           home_away="HOME", round="1", venue="Shirley Strickland Reserve"))
            await db.commit()
        return fid

    async def call(fid, **kw):
        async with Session() as db:
            try:
                return await iq.opposition_report(db, str(oid), fixture_id=str(fid), **kw)
            except TypeError:           # control: selected_only does not exist yet
                kw.pop("selected_only", None)
                return await iq.opposition_report(db, str(oid), fixture_id=str(fid), **kw)

    def names(r, kind):
        return [p["name"] for p in ((r.get("our_performers") or {}).get(kind) or [])]

    f_conf = await fixture(oid, gid_od, tid, OPP)
    async with Session() as db:
        for order, pid in ((1, picked_bat), (2, picked_bowl)):
            db.add(FixtureLineup(fixture_id=f_conf, player_id=pid, organisation_id=oid, batting_order=order))
        await db.commit()

    # 0. the controls for the absence checks: the whole squad really can be listed
    r = await call(f_conf)
    check("default: bigger scorer outside the XI is listed (presence control)", "Barry Bigscorer" in names(r, "batting"))
    check("default: wicket-taker outside the XI is listed (presence control)", "Sam Starbowler" in names(r, "bowling"))
    check("default: the whole-squad list is unchanged (no selected_xi)", r.get("selected_xi"), None)

    # 1. header grade
    check("fixture header: the fixture's own grade", (r.get("fixture") or {}).get("grade_name"), "One Day Grade 4")
    check("fixture header: team name carried", (r.get("fixture") or {}).get("team_name"), "OD4s")
    check("last meeting is the T20 game, a different grade", (r.get("last_meeting") or {}).get("grade"), "Twenty20 Div 1")

    # 2. confirmed XI
    r = await call(f_conf, selected_only=True)
    check("confirmed: status", (r.get("selected_xi") or {}).get("status"), "confirmed")
    check("confirmed: batting is only the picked batter", names(r, "batting"), ["Pat Picked"])
    check("confirmed: bowling is only the picked bowler", names(r, "bowling"), ["Wes Wicket"])
    check("confirmed: the bigger unpicked scorer is absent", "Barry Bigscorer" in names(r, "batting"), False)
    check("confirmed: the unpicked wicket-taker is absent", "Sam Starbowler" in names(r, "bowling"), False)
    check("confirmed: a rival club's player is absent", "Rival Bat" in names(r, "batting"), False)
    check("confirmed: the pick ranked 13th club-wide still appears (filter before the top-10 cut)", "Pat Picked" in names(r, "batting"))

    # 3. draft only
    f_draft = await fixture(oid, gid_od, tid, OPP)
    async with Session() as db:
        await db.execute(text("INSERT INTO selection_drafts (fixture_id, organisation_id, draft) VALUES (:f, :o, CAST(:d AS jsonb))"),
                         {"f": f_draft, "o": oid, "d": json.dumps({"slots": [str(picked_bowl), None, str(draft_only)]})})
        await db.commit()
    r = await call(f_draft, selected_only=True)
    check("draft: status", (r.get("selected_xi") or {}).get("status"), "draft")
    check("draft: only the draft's players", names(r, "bowling"), ["Wes Wicket"])
    check("draft: the batter who is not in the draft is absent", names(r, "batting"), [])

    # 4. nothing picked
    f_none = await fixture(oid, gid_od, tid, OPP)
    r = await call(f_none, selected_only=True)
    check("nothing picked: status none", (r.get("selected_xi") or {}).get("status"), "none")
    check("nothing picked: no batters, never the whole squad", names(r, "batting"), [])
    check("nothing picked: no bowlers", names(r, "bowling"), [])
    check("nothing picked: lists are present, not null", isinstance(r.get("our_performers"), dict))

    # 5. another club's fixture
    rid = uuid.uuid4()
    async with Session() as db:
        rsid, rgid = uuid.uuid4(), uuid.uuid4()
        db.add(Season(id=rsid, organisation_id=other, name="S", year=2026))
        await db.flush()
        db.add(Grade(id=rgid, season_id=rsid, name="Rival Grade"))
        await db.flush()
        db.add(Fixture(id=rid, organisation_id=other, source="grassroots", grade_id=rgid, played_on=sat,
                       status="UPCOMING", opponent_name=OPP, home_away="HOME", round="1"))
        await db.commit()
    r = await call(rid, selected_only=True)
    check("another club's fixture: no header", r.get("fixture"), None)
    check("another club's fixture: no XI is read for it", r.get("selected_xi"), None)

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAILURES:
        print("\n".join(" - " + f for f in FAILURES))
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
