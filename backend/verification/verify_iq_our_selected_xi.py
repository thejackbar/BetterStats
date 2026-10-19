"""Verification: Ask BetterIQ reads OUR confirmed XI for a fixture, against a real Postgres.

Reported: asked for a summary of the One Day Grade 4 side selected for the weekend,
Ask IQ said our side "hasn't been named in a filterable squad" and fell back to the
whole club, although the BetterSelect board showed a confirmed 12 for that fixture.
The tool list had `current_squad` (everyone who played) and `opponent_lineup` (THEIR
named side) but nothing that reads `fixture_lineups`.

This drives the SHIPPED `iq_ask._tool_our_selected_xi`. Checks:

  * a confirmed XI comes back in batting order, with captain, keeper and the status
  * a player on the club's books who is NOT picked never appears (the old fallback)
  * a board draft with nothing confirmed is reported `draft_only`, not as picked
  * a fixture with nothing picked is `not_selected`
  * another club's fixture, a bad id and a missing id are refused, never read

CONTROL MODE: run against the commit BEFORE this change. The tool does not exist
there, so `call()` turns the AttributeError into an error result and the control
reports the old behaviour as failed checks instead of crashing (rule 21).

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_iq_our_selected_xi.py
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
from app.models.db import Base, Organisation, Team, Grade, Season, Fixture, Player, FixtureLineup
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
    from app.services import iq_ask

    today = date.today()
    sat = today + timedelta(days=(5 - today.weekday()) % 7 or 7)

    async def club(name):
        oid, sid, gid, tid = (uuid.uuid4() for _ in range(4))
        async with Session() as db:
            db.add(Organisation(id=oid, name=name, slug=f"{name.lower()[:6]}-{oid.hex[:8]}"))
            db.add(Season(id=sid, organisation_id=oid, name="Summer 2026/27", year=2026))
            await db.flush()
            db.add(Grade(id=gid, season_id=sid, name="One Day Grade 4"))
            await db.flush()
            db.add(Team(id=tid, organisation_id=oid, name="OD4s", sequence=4, grade_id=gid))
            await db.commit()
        return oid, gid, tid

    async def player(oid, name, **kw):
        pid = uuid.uuid4()
        async with Session() as db:
            db.add(Player(id=pid, organisation_id=oid, name=name, is_player=True, gender="MALE", **kw))
            await db.commit()
        return pid

    async def fixture(oid, gid, tid, opp):
        fid = uuid.uuid4()
        async with Session() as db:
            db.add(Fixture(id=fid, organisation_id=oid, source="grassroots", grade_id=gid, team_id=tid,
                           played_on=sat, start_time="12:00", status="UPCOMING", opponent_name=opp,
                           home_away="HOME", round="1", venue="Shirley Strickland Reserve"))
            await db.commit()
        return fid

    async def call(oid, fid):
        async with Session() as db:
            try:
                return await iq_ask._tool_our_selected_xi(db, str(oid), fixture_id=str(fid))
            except AttributeError as e:      # control: the tool does not exist yet
                return {"error": str(e)}

    org, gid, tid = await club("Applecross")
    other, ogid, otid = await club("Rival")

    ang = await player(org, "Angus Castley", batting_hand="RIGHT", bowling_type="FINGER_SPIN", is_opening_batsman=True)
    ryan = await player(org, "Ryan Carmody", batting_hand="RIGHT", player_role="WICKET_KEEPER")
    brc = await player(org, "Bruce Calder", batting_hand="RIGHT", bowling_type="FAST_MEDIUM")
    spare = await player(org, "Lakshmi Spare", batting_hand="LEFT", bowling_type="FINGER_SPIN")
    stranger = await player(other, "Rival Bat", batting_hand="RIGHT")

    # 1. a confirmed XI
    f_conf = await fixture(org, gid, tid, "SMCC 8th XI")
    async with Session() as db:
        for order, pid, cap, wk in ((1, ang, True, False), (2, brc, False, False), (3, ryan, False, True)):
            db.add(FixtureLineup(fixture_id=f_conf, player_id=pid, organisation_id=org,
                                 batting_order=order, is_captain=cap, is_wicket_keeper=wk))
        await db.commit()
    r = await call(org, f_conf)
    names = [p.get("name") for p in r.get("players", [])]
    check("confirmed: status is confirmed", r.get("status"), "confirmed")
    check("confirmed: the picked players, in batting order", names, ["Angus Castley", "Bruce Calder", "Ryan Carmody"])
    check("confirmed: an unpicked club player is not in the side", "Lakshmi Spare" in names, False)
    check("confirmed: another club's player is not in the side", "Rival Bat" in names, False)
    check("confirmed: captain is marked", [p["name"] for p in r.get("players", []) if p.get("captain")], ["Angus Castley"])
    check("confirmed: keeper is marked", [p["name"] for p in r.get("players", []) if p.get("keeper")], ["Ryan Carmody"])
    check("confirmed: fixture details are carried",
          (r.get("fixture", {}).get("opponent"), r.get("fixture", {}).get("venue")),
          ("SMCC 8th XI", "Shirley Strickland Reserve"))
    check("confirmed: balance counts the side", (r.get("balance") or {}).get("size"), 3)
    check("confirmed: carries warnings as plain text", all(isinstance(w, str) for w in r.get("warnings", [])) and "warnings" in r)

    # 2. a draft only
    f_draft = await fixture(org, gid, tid, "Draft Opponent")
    async with Session() as db:
        await db.execute(text(
            "INSERT INTO selection_drafts (fixture_id, organisation_id, draft) "
            "VALUES (:f, :o, CAST(:d AS jsonb))"),
            {"f": f_draft, "o": org, "d": json.dumps({"slots": [str(spare), None, str(ang)]})})
        await db.commit()
    r = await call(org, f_draft)
    check("draft only: reported as draft_only", r.get("status"), "draft_only")
    check("draft only: names the draft side", r.get("draft_players"), ["Lakshmi Spare", "Angus Castley"])
    check("draft only: does not claim a confirmed side", "players" in r, False)

    # 3. nothing picked
    f_none = await fixture(org, gid, tid, "Nobody Opponent")
    r = await call(org, f_none)
    check("nothing picked: not_selected", r.get("status"), "not_selected")
    check("nothing picked: no players", "players" in r, False)

    # 4. refusals
    f_other = await fixture(other, ogid, otid, "Not Ours")
    r = await call(org, f_other)
    check("another club's fixture is refused", ("error" in r, "players" in r), (True, False))
    r = await call(org, "not-a-uuid")
    check("a bad id is refused, no crash", ("error" in r, "players" in r), (True, False))
    r = await call(org, uuid.uuid4())
    check("a missing fixture is refused", ("error" in r, "players" in r), (True, False))

    # 5. the model is actually offered the tool and the prompt points at it
    check("tool is in the schema list", any(t["name"] == "our_selected_xi" for t in iq_ask.TOOLS))
    check("tool is dispatched", "our_selected_xi" in iq_ask._DISPATCH)
    check("prompt says not to use current_squad as the picked side", "our_selected_xi" in iq_ask._SYSTEM)

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAILURES:
        print("\n".join(" - " + f for f in FAILURES))
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
