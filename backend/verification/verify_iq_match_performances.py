"""Verification: Match Review totals and Ask IQ's completed-game tools, against a real Postgres.

Reported: (1) Ask IQ said it could not see completed games, so a 3-2-1 for a played 3rd XI
game was refused; (2) Match Review showed Applecross 101/1 v Bassendean 127/9 with "Won".
The review summed the batters' runs only, which leaves extras out of both totals, while
Cricket Australia's own innings totals (games.innings_totals) hold the true figures.

Drives the SHIPPED `iq_review.game_review`, `iq_review.game_performances` and the
`iq_ask` tools. Checks:

  * the review reads 128/1 v 127/9 when innings_totals is stored, not 101/1 v 120/9
  * a game with no stored totals is flagged score_exact False and the synthesis line
    states no score (an approximate score can contradict the result)
  * match_performances accepts a pasted betterat.cricket/games/<id> link
  * every wicket carries the dismissed batter's band and value: a tail-ender is low,
    an opener and a set batter are high
  * the opposition's batters (a shared fixture's other club) never appear on our card
  * recent_games finds the game by the team it was picked as ('3rd XI') AND by its grade
    ('5th Grade'), and another club's game is refused

CONTROL MODE: run against the commit BEFORE this change. New keys are read with .get so
absence is reported as a failed check, never a crash (rule 21).

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_iq_match_performances.py
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
    from app.models.db import Game, BattingInnings, BowlingSpell, BowlerWicket, FieldingStat
    from app.services import iq_ask, iq_review

    org, other = uuid.uuid4(), uuid.uuid4()
    sid, gid, tid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    day = date.today() - timedelta(days=3)

    async with Session() as db:
        db.add(Organisation(id=org, name="Applecross", slug=f"app-{org.hex[:8]}"))
        db.add(Organisation(id=other, name="Bassendean", slug=f"bas-{other.hex[:8]}"))
        db.add(Season(id=sid, organisation_id=org, name="Summer 2026/27", year=2026))
        await db.flush()
        db.add(Grade(id=gid, season_id=sid, name="5th Grade"))
        await db.flush()
        db.add(Team(id=tid, organisation_id=org, name="3rd XI", sequence=3, grade_id=gid))
        await db.commit()

    async def player(oid, name, **kw):
        pid = uuid.uuid4()
        async with Session() as db:
            db.add(Player(id=pid, organisation_id=oid, name=name, is_player=True, gender="MALE", **kw))
            await db.commit()
        return pid

    wig = await player(org, "Wiggill, Justin")
    sto = await player(org, "Stoyanov, Luca")
    wat = await player(org, "Watson, Hamish")
    tailer = await player(org, "Nash, Tom")
    their = await player(other, "Bassendean Bat")

    async def game(totals, result="WIN"):
        g = uuid.uuid4()
        async with Session() as db:
            db.add(Game(id=g, grade_id=gid, played_at=day, home_team="Bassendean", away_team="Applecross",
                        home_org_id=other, away_org_id=org, opp_club_name="Bassendean Cricket Club",
                        result=result, winning_team="Applecross", status="COMPLETED", venue="Jubilee Reserve"))
            await db.flush()
            # we chased: innings 1 theirs, innings 2 ours
            for pid, pos, runs, balls, no in ((wig, 1, 28, 40, False), (sto, 2, 41, 52, True), (their, 1, 9, 12, False)):
                db.add(BattingInnings(game_id=g, player_id=pid, innings_number=2 if pid != their else 1,
                                      batting_position=pos, runs=runs, balls=balls, not_out=no,
                                      dismissal_type=None if no else "ct"))
            db.add(BattingInnings(game_id=g, player_id=wig, innings_number=2, batting_position=1,
                                  runs=0, balls=0, did_not_bat=True)) if False else None
            for pid, ov, rn, wk in ((wat, 8.0, 20, 3), (tailer, 6.0, 22, 3)):
                db.add(BowlingSpell(game_id=g, player_id=pid, innings_number=1, overs=ov, maidens=1,
                                    runs=rn, wickets=wk, economy=round(rn / ov, 2)))
            for bowler, name, pos, runs in ((wat, "Opener One", 1, 12), (wat, "Set Two", 3, 38), (wat, "Ten", 10, 1),
                                            (tailer, "Eight", 8, 4), (tailer, "Nine", 9, 0), (tailer, "Eleven", 11, 2)):
                db.add(BowlerWicket(game_id=g, innings_number=1, bowler_id=bowler, batter_name=name,
                                    batter_position=pos, batter_runs=runs, batter_balls=10, dismissal_type="b"))
            db.add(FieldingStat(game_id=g, player_id=sto, catches=1, catches_wk=0, run_outs=0, stumpings=0))
            await db.commit()
        async with Session() as db:
            if totals is not None:
                await db.execute(text("UPDATE games SET innings_totals = CAST(:t AS jsonb) WHERE id = :g"),
                                 {"t": json.dumps(totals), "g": g})
            await db.commit()
        return g

    good = await game([{"innings_number": 1, "runs_scored": 127, "wickets": 9, "extras": 7},
                       {"innings_number": 2, "runs_scored": 128, "wickets": 1, "extras": 59 - 32}])
    # bowlers conceded 42 here only so the batters-only fallback reads clearly light
    bare = await game(None)
    async with Session() as db:
        db.add(Fixture(id=uuid.uuid4(), organisation_id=org, source="grassroots", grade_id=gid, team_id=tid,
                       played_on=day, status="FINAL", opponent_name="Bassendean Cricket Club",
                       home_away="AWAY", playhq_id=str(good)))
        await db.commit()

    async with Session() as db:
        rv = await iq_review.game_review(db, str(org), str(good))
    g = rv["game"]
    check("true totals: our score is 128/1", g.get("our_score"), "128/1")
    check("true totals: their score is 127/9", g.get("their_score"), "127/9")
    check("true totals: marked exact", g.get("score_exact"), True)
    check("synthesis states the exact score", any("128/1 vs 127/9" in x for x in rv["summary"]), True)

    async with Session() as db:
        rb = await iq_review.game_review(db, str(org), str(bare))
    check("no stored totals: marked approximate", rb["game"].get("score_exact"), False)
    check("no stored totals: synthesis states no score", any(" vs " in x and "/" in x for x in rb["summary"]), False)
    check("no stored totals: a coverage note says so", any("leave out extras" in n for n in rb["coverage"]["notes"]), True)

    # Ask IQ tools
    async def tool(name, **kw):
        async with Session() as db:
            try:
                return await getattr(iq_ask, "_tool_" + name)(db, str(org), **kw)
            except AttributeError as e:    # control: tool does not exist yet
                return {"error": str(e)}

    link = f"https://betterat.cricket/games/{good} Game is here"
    d = await tool("match_performances", game_id=link)
    check("pasted link resolves to the game", (d.get("game") or {}).get("opponent"), "Bassendean Cricket Club")
    names = [b["name"] for b in d.get("batting", [])]
    check("our batters listed in order", names, ["Wiggill, Justin", "Stoyanov, Luca"])
    check("opposition batter never on our card", "Bassendean Bat" in json.dumps(d), False)
    sto_row = next((b for b in d.get("batting", []) if b["name"].startswith("Stoy")), {})
    check("a batter's share of the 128 total", sto_row.get("share_of_team_total_pct"), 32)
    check("context says how it was won", "chased 128" in (d.get("context") or {}).get("how_won", ""), True)
    bowl = {b["name"]: b for b in d.get("bowling", [])}
    w = bowl.get("Watson, Hamish", {})
    t = bowl.get("Nash, Tom", {})
    check("Watson: two high-value wickets (opener, set batter)", w.get("high_value_wickets"), 2)
    check("Watson: one tail wicket", w.get("tail_wickets"), 1)
    check("Nash: all three wickets are tail", t.get("tail_wickets"), 3)
    check("Nash: no high-value wickets", t.get("high_value_wickets"), 0)
    check("Nash: values are low", {x["value"] for x in t.get("wickets_taken", [])}, {"low"})
    check("fielding is reported", [f["name"] for f in d.get("fielding", [])], ["Stoyanov, Luca"])
    check("link with no id is refused", "error" in await tool("match_performances", game_id="the 17th"), True)

    rg = await tool("recent_games", team="3rd XI")
    check("recent_games finds the game by the XI it was picked as", [x["game_id"] for x in rg.get("games", [])], [str(good)])
    check("recent_games shows team and grade together", [(x["team"], x["grade"]) for x in rg.get("games", [])], [("3rd XI", "5th Grade")])
    rg2 = await tool("recent_games", team="5th Grade")
    check("recent_games finds both by grade", len(rg2.get("games", [])), 2)
    rg3 = await tool("recent_games", opponent="Bassendean", from_date=str(day), to_date=str(day), limit=1)
    check("recent_games honours opponent, dates and limit", len(rg3.get("games", [])), 1)

    async with Session() as db:
        theirs_view = await iq_review.game_performances(db, str(other), str(good))
    check("the other club sees only its own batter, never ours",
          [b["name"] for b in (theirs_view or {}).get("batting", [])], ["Bassendean Bat"])
    third = uuid.uuid4()
    async with Session() as db:
        db.add(Organisation(id=third, name="Third", slug=f"thi-{third.hex[:8]}"))
        await db.commit()
    async with Session() as db:
        check("a club that did not play is refused", await iq_review.game_performances(db, str(third), str(good)), None)

    check("tools are offered", {"recent_games", "match_performances"} <= {t["name"] for t in iq_ask.TOOLS}, True)
    check("tools are dispatched", {"recent_games", "match_performances"} <= set(iq_ask._DISPATCH), True)
    check("prompt tells the model it can judge played games", "match_performances" in iq_ask._SYSTEM and "tail" in iq_ask._SYSTEM.lower(), True)

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAILURES:
        print("\n".join(" - " + f for f in FAILURES))
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
