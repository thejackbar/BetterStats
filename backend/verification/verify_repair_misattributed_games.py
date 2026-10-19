"""Verification: the repair that detaches a player's rows from games CA's card does not carry them in. Real Postgres.

Reported: Leederville's Jonah Cumming held 36 games that are other people's (CA's hidden-participant
id), Mulgrave's Luke Bennett held 16 that are a namesake's. `scripts/repair_misattributed_games`
removes them, from CA's own scorecard.

Runs the SHIPPED script functions over the `v_effective_*` views pulled from the migrations, with
Cricket Australia stubbed (a scorecard per game). Covers: the plan is only a plan; apply needs the
right --expect and --by; only the wrong games change, for only that player; a card with nobody on
it, a merged second registration and a hand-typed game are never touched; the audit entry holds
everything; restore puts it all back exactly, once.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres:pw@127.0.0.1:5432/betterstats_verify \
  python verification/verify_repair_misattributed_games.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.models import db as models
from app.models.db import Base
from app.scripts import repair_misattributed_games as rep
from app.services import grassroots_scores_client as gr
from app.services.competition_ddl import STATEMENTS as COMP_STATEMENTS

DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)
# The script opens its own sessions: point it at this database.
models.async_session_maker = Session
rep.async_session_maker = Session

PASS = FAIL = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")


ORG, OPP = uuid.uuid4(), uuid.uuid4()
SEASON, GRADE = uuid.uuid4(), uuid.uuid4()
JON, OTHER1, OTHER2, HAND = (uuid.uuid4() for _ in range(4))
SECOND = uuid.uuid4()                    # a second registration, merged into JON
PLACEHOLDER = "00000000-0000-0000-0000-000000000001"
G_ON, G_MERGE, G_OFF1, G_OFF2, G_EMPTY = (uuid.uuid4() for _ in range(5))
MANUAL = uuid.uuid4()
CARDS: dict[str, dict] = {}


def card(sheet=(), bat=(), field=()):
    return {"teams": [{"players": [{"participantId": str(i)} for i in sheet]}],
            "innings": [{"batting": [{"participantId": str(i)} for i in bat], "bowling": [],
                         "fielding": [{"participantId": str(i)} for i in field]}]}


async def fake_card(match_id, force=False):
    return CARDS.get(str(match_id))

gr.get_match_scorecard = fake_card

_orig_sleep = asyncio.sleep
async def _fast_sleep(_):  # the script paces its CA requests; nothing to wait for here
    return None
rep.asyncio.sleep = _fast_sleep

TABLES = ("batting_innings", "bowling_spells", "fielding_stats", "game_appearances", "bowler_wickets",
          "milestones", "partnerships", "fall_of_wickets")


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)
        for stmt in COMP_STATEMENTS:
            await conn.execute(text(stmt))
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        # Lifespan DDL (main.py), column for column.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID,
                keep_player_id UUID, keep_player_name TEXT, removed_player_id UUID, removed_player_name TEXT,
                removed_player_playhq_id TEXT, keep_original_playhq_id TEXT,
                moved_season_stat_ids JSONB DEFAULT '[]', batting_innings_ids JSONB DEFAULT '[]',
                bowling_spell_ids JSONB DEFAULT '[]', fielding_stat_ids JSONB DEFAULT '[]',
                fall_of_wicket_ids JSONB DEFAULT '[]', batter1_partnership_ids JSONB DEFAULT '[]',
                batter2_partnership_ids JSONB DEFAULT '[]', milestone_ids JSONB DEFAULT '[]',
                bowler_wicket_ids JSONB DEFAULT '[]', fielder_wicket_ids JSONB DEFAULT '[]',
                grade_stat_ids JSONB DEFAULT '[]', appearance_game_ids JSONB DEFAULT '[]', undone_at TIMESTAMPTZ)"""))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id SERIAL PRIMARY KEY, created_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID NOT NULL, user_id UUID,
                action TEXT NOT NULL, target_type TEXT, target_id TEXT, details JSONB DEFAULT '{}')"""))
        for stmt in (
            "CREATE TABLE IF NOT EXISTS grade_merge_logs (id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID NOT NULL, canonical_name TEXT NOT NULL, alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)",
            "CREATE TABLE IF NOT EXISTS season_aliases (id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID NOT NULL, canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE, alias_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE, undone_at TIMESTAMPTZ)",
            "CREATE TABLE IF NOT EXISTS org_merge_logs (id UUID PRIMARY KEY DEFAULT gen_random_uuid(), source_org_id UUID, source_org_name TEXT NOT NULL, target_org_id UUID NOT NULL, performed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), undone_at TIMESTAMPTZ)",
        ):
            await conn.execute(text(stmt))
        for tbl, col in (await conn.execute(text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND data_type = 'json'"))).all():
            await conn.execute(text(f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb USING "{col}"::text::jsonb'))
        for name, sql in view_statements():
            await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
            await conn.execute(text(sql.replace("OR REPLACE ", "")))


async def seed() -> None:
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)

        await ex("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, 'Test CC', 'test', true)", i=ORG)
        await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, 'Summer 2025/26', 2025)", i=SEASON, o=ORG)
        await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
                 "VALUES (:i, :s, 'C Grade', :g, 'senior', ARRAY['senior'])", i=GRADE, s=SEASON, g=str(GRADE))
        for pid, nm, gid in ((JON, "Cumming, Jonah", str(JON)), (OTHER1, "Other, One", str(OTHER1)),
                             (OTHER2, "Other, Two", str(OTHER2)), (HAND, "Hand, Added", None)):
            await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) VALUES (:i, :o, :n, :g, 'active')",
                     i=pid, o=ORG, n=nm, g=gid)
        await ex("INSERT INTO merge_logs (org_id, keep_player_id, keep_player_name, removed_player_id, removed_player_name) "
                 "VALUES (:o, :k, 'Cumming, Jonah', :r, 'Cumming, Jonah')", o=ORG, k=JON, r=SECOND)

        day = 1
        for gid in (G_ON, G_MERGE, G_OFF1, G_OFF2, G_EMPTY):
            await ex("INSERT INTO games (id, grade_id, played_at, result, home_org_id, away_org_id, match_format, status) "
                     "VALUES (:i, :g, :d, 'WIN', :o, :x, 'One Day', 'COMPLETED')", i=gid, g=GRADE, d=date(2025, 11, day), o=ORG, x=OPP)
            day += 1
            await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=gid, p=JON)
            await ex("INSERT INTO batting_innings (game_id, player_id, innings_number, batting_position, runs, balls, not_out, dismissal_type, did_not_bat) "
                     "VALUES (:g, :p, 1, 4, 10, 12, false, 'caught', false)", g=gid, p=JON)
            await ex("INSERT INTO bowling_spells (game_id, player_id, innings_number, overs, maidens, runs, wickets) VALUES (:g, :p, 2, 4.0, 0, 20, 1)", g=gid, p=JON)
            await ex("INSERT INTO fielding_stats (game_id, player_id, catches, catches_wk, run_outs, stumpings) VALUES (:g, :p, 1, 0, 0, 0)", g=gid, p=JON)
            await ex("INSERT INTO bowler_wickets (game_id, innings_number, bowler_id, fielder_id, batter_name, batter_position, dismissal_type) VALUES (:g, 2, :p, :f, 'Opp A', 3, 'caught')",
                     g=gid, p=JON, f=OTHER1)
            await ex("INSERT INTO bowler_wickets (game_id, innings_number, bowler_id, fielder_id, batter_name, batter_position, dismissal_type) VALUES (:g, 2, :b, :f, 'Opp B', 5, 'caught')",
                     g=gid, b=OTHER1, f=JON)
            await ex("INSERT INTO partnerships (game_id, innings_number, wicket_number, batter1_id, batter2_id, runs, balls, batter1_name, batter2_name) "
                     "VALUES (:g, 1, 3, :a, :b, 40, 50, 'J Cumming', 'O Two')", g=gid, a=JON, b=OTHER2)
            await ex("INSERT INTO fall_of_wickets (game_id, innings_number, wicket_number, score_at_fall, player_id, batter_name) VALUES (:g, 1, 3, 60, :p, 'J Cumming')",
                     g=gid, p=JON)
            await ex("INSERT INTO milestones (player_id, game_id, milestone_type, milestone_value) VALUES (:p, :g, 'runs', 10)", p=JON, g=gid)
            # Another player's own rows in the same game: must never be touched.
            await ex("INSERT INTO batting_innings (game_id, player_id, innings_number, batting_position, runs, balls, not_out, dismissal_type, did_not_bat) "
                     "VALUES (:g, :p, 1, 1, 33, 40, false, 'bowled', false)", g=gid, p=OTHER1)

        CARDS[str(G_ON)] = card([JON, OTHER1], bat=[JON, OTHER1])
        CARDS[str(G_MERGE)] = card([SECOND, OTHER1], bat=[SECOND, OTHER1])
        CARDS[str(G_OFF1)] = card([OTHER1, OTHER2], bat=[OTHER1, OTHER2])               # a namesake's game
        CARDS[str(G_OFF2)] = card([OTHER1], bat=[PLACEHOLDER, OTHER1], field=[PLACEHOLDER])   # hidden-participant rows
        CARDS[str(G_EMPTY)] = card()                                                      # nobody named: unjudgeable

        # A hand-typed game with Jonah in it: not a games row, never repaired.
        await ex("INSERT INTO manual_games (id, organisation_id, season_id, played_at, result, home_team, away_team) "
                 "VALUES (:i, :o, :s, :d, 'WIN', 'Us', 'Them')", i=MANUAL, o=ORG, s=SEASON, d=date(2025, 12, 1))
        await ex("INSERT INTO manual_batting_innings (manual_game_id, player_id, runs, not_out, did_not_bat) VALUES (:g, :p, 5, false, false)", g=MANUAL, p=JON)
        await s.commit()


async def snapshot() -> dict:
    """Every row in the touched tables, as comparable text."""
    out = {}
    async with Session() as s:
        for t in TABLES + ("manual_batting_innings",):
            rows = (await s.execute(text(f"SELECT to_jsonb(t)::text FROM {t} t ORDER BY 1"))).all()
            out[t] = [r[0] for r in rows]
    return out


async def jon_rows(game) -> dict:
    out = {}
    async with Session() as s:
        for t, col in (("batting_innings", "player_id"), ("bowling_spells", "player_id"), ("fielding_stats", "player_id"),
                       ("game_appearances", "player_id"), ("bowler_wickets", "bowler_id"), ("milestones", "player_id")):
            out[t] = (await s.execute(text(f"SELECT COUNT(*) FROM {t} WHERE {col} = :p AND game_id = :g"), {"p": JON, "g": game})).scalar()
    return out


async def run(**kw):
    """The script's entry point, returning SystemExit text instead of exiting."""
    args = dict(org_ref="auto", player_id=str(JON), apply=False, expect=None, by=None, limit=200, only=None)
    args.update(kw)
    try:
        await rep.plan_and_maybe_apply(args["org_ref"], args["player_id"], args["apply"], args["expect"], args["by"], args["limit"], args["only"])
        return None
    except SystemExit as e:
        return str(e)


async def main() -> int:
    await build_schema()
    await seed()
    before = await snapshot()

    print("\n-- the plan is only a plan --")
    refused = await run()
    check("a dry run reports and does not raise", refused is None, str(refused))
    check("a dry run changes nothing", await snapshot() == before)

    print("\n-- apply needs the right count and a name --")
    r1 = await run(apply=True, expect=99, by="Jack")
    check("a wrong --expect is refused", bool(r1) and "Refusing" in r1, str(r1))
    r2 = await run(apply=True, expect=2)
    check("a missing --by is refused", bool(r2) and "--by" in r2, str(r2))
    check("neither refusal changed anything", await snapshot() == before)

    print("\n-- a record with no CA id of its own cannot be judged --")
    async with Session() as s:
        await s.execute(text("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)"), {"g": G_ON, "p": HAND})
        await s.commit()
    r3 = await run(player_id=str(HAND))
    check("a hand-added player is refused", bool(r3) and "no Cricket Australia id" in r3, str(r3))
    async with Session() as s:
        await s.execute(text("DELETE FROM game_appearances WHERE player_id = :p"), {"p": HAND})
        await s.commit()
    before = await snapshot()

    print("\n-- apply --")
    ok = await run(apply=True, expect=2, by="Jack")
    check("apply with the right count succeeds", ok is None, str(ok))
    off1, off2 = await jon_rows(G_OFF1), await jon_rows(G_OFF2)
    check("the namesake game's rows for Jonah are gone from every table", not any(off1.values()), str(off1))
    check("the hidden-participant game's rows for Jonah are gone", not any(off2.values()), str(off2))
    for label, g in (("the game CA carries him in", G_ON), ("the merged second registration's game", G_MERGE),
                     ("the game whose card names nobody", G_EMPTY)):
        rows = await jon_rows(g)
        check(f"{label} is untouched", all(v >= 1 for v in rows.values()), str(rows))
    async with Session() as s:
        other = (await s.execute(text("SELECT COUNT(*) FROM batting_innings WHERE player_id = :p"), {"p": OTHER1})).scalar()
        check("another player's own rows are untouched", other == 5, f"got {other}")
        manual = (await s.execute(text("SELECT COUNT(*) FROM manual_batting_innings WHERE player_id = :p"), {"p": JON})).scalar()
        check("a hand-typed game is untouched", manual == 1)
        pt = (await s.execute(text("SELECT batter1_id, batter1_name, batter2_id FROM partnerships WHERE game_id = :g"), {"g": G_OFF1})).first()
        check("the partnership stays, with Jonah's slot empty and the stored name kept",
              pt is not None and pt[0] is None and pt[1] == "J Cumming" and pt[2] == OTHER2, str(pt))
        bw = (await s.execute(text("SELECT COUNT(*) FROM bowler_wickets WHERE game_id = :g AND bowler_id = :o"), {"g": G_OFF1, "o": OTHER1})).scalar()
        fl = (await s.execute(text("SELECT fielder_id FROM bowler_wickets WHERE game_id = :g AND bowler_id = :o"), {"g": G_OFF1, "o": OTHER1})).scalar()
        check("another bowler's wicket stays and loses only Jonah as the fielder", bw == 1 and fl is None, f"{bw} {fl}")
        audit = (await s.execute(text("SELECT id, action, details FROM audit_logs WHERE action = 'repair_misattributed_games'"))).mappings().all()
    check("one audit entry was written", len(audit) == 1)
    audit_id = audit[0]["id"] if audit else -1
    d = audit[0]["details"] if audit else {}
    d = d if isinstance(d, dict) else json.loads(d)
    check("it names who did it", d.get("by") == "Jack")
    check("it holds every removed row", len(d["dump"]["tables"]["batting_innings"]) == 2 and len(d["dump"]["tables"]["game_appearances"]) == 2,
          str({k: len(v) for k, v in d["dump"]["tables"].items()}))
    again = await run()
    check("running it again finds nothing more to repair", again is None)

    print("\n-- restore --")
    bad = None
    try:
        await rep.restore(99999, "Jack")
    except SystemExit as e:
        bad = str(e)
    check("an entry that is not a repair is refused", bool(bad) and "not a" in bad, str(bad))
    try:
        await rep.restore(audit_id, None)
        nobody = None
    except SystemExit as e:
        nobody = str(e)
    check("a restore needs --by", bool(nobody) and "--by" in nobody)
    await rep.restore(audit_id, "Jack")
    after = await snapshot()
    check("restore brings every table back exactly as it was", after == before,
          "differs in " + ", ".join(t for t in after if after[t] != before[t]))
    twice = None
    try:
        await rep.restore(audit_id, "Jack")
    except SystemExit as e:
        twice = str(e)
    check("an entry restores only once", bool(twice) and "already restored" in twice, str(twice))

    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
