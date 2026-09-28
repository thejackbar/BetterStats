"""A match imported from a club's scorebook shows both sides and its stands.

Reported off Shoalwater Bay's CSFW archive: an imported fixture showed no
partnerships, no opposition team and no opposition score, so none of it
reached the Highest Partnerships board. The archive holds the opposition's
innings total, our own innings figures and the fall of wickets for every
match; the import simply had no columns for them.

This drives the SHIPPED import route body, the scorecard route body and the
records route body over a real Postgres:

  * the opposition's innings lands as its own innings, with its total, and our
    bowling is filed under it rather than beside our own batting;
  * the fall of wickets lands, and partnerships are worked out from it and the
    batting order, including the unbroken stand;
  * an innings whose figures do not reconcile keeps its fall of wickets and
    gets NO partnerships, rather than stands credited to the wrong pair;
  * the match page names both sides without calling either one home, and does
    not claim a batting order the scorebook never recorded;
  * the stands reach the club's records;
  * a sheet without the new columns imports exactly as it always did;
  * undo of an overwrite brings every one of the new rows back.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/v_scorebook_innings?host=/tmp&port=5439 \\
  python verification/verify_scorebook_innings.py
"""
from __future__ import annotations

import asyncio
import csv
import io
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.models.db import (
    Base, Grade, ManualBowlingSpell, ManualGame, Organisation, Player, Season, User,
)
from app.routers.games import get_scorecard
from app.routers.manual_entries import GAME_CSV_COLUMNS, import_manual_games
from app.routers.records import get_records
from app.services.competition_ddl import STATEMENTS as COMP_DDL
from app.services.superseded_ddl import STATEMENTS as SUPERSEDED_DDL

# Behind guards, so a CONTROL RUN against the previous commit REPORTS each
# missing part rather than dying on the first ImportError.
MISSING: list[str] = []
try:
    from app.services.scorebook_innings import derive_partnerships
except ImportError as exc:  # pragma: no cover - control run only
    derive_partnerships = None
    MISSING.append(str(exc))
try:
    from app.routers.manual_entries import _restore_manual_game, _snapshot_manual_game
except ImportError as exc:  # pragma: no cover
    _restore_manual_game = _snapshot_manual_game = None
    MISSING.append(str(exc))
try:
    from app.models.db import ManualFallOfWicket, ManualInnings, ManualPartnership
except ImportError as exc:  # pragma: no cover
    ManualFallOfWicket = ManualInnings = ManualPartnership = None
    MISSING.append(str(exc))

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


ORG = uuid.uuid4()
USER = uuid.uuid4()
SEASON = uuid.uuid4()
GRADE = uuid.uuid4()
NAMES = ["Opener, Ann", "Second, Bob", "Third, Cal", "Fourth, Dan", "Bowler, Eve"]
PIDS = {n: uuid.uuid4() for n in NAMES}


class FakeUpload:
    def __init__(self, text_: str):
        self._data = text_.encode("utf-8-sig")
        self.filename = "scorecards.csv"

    async def read(self):
        return self._data


def row(**kw) -> dict:
    """One sheet row: the match and season columns filled in, the rest blank.

    Only the columns the shipped importer knows are written, so a control run
    against a build without the new columns sends a sheet it can read.
    """
    base = dict.fromkeys(GAME_CSV_COLUMNS, "")
    base.update(game_key="SB-1", played_at="1999-11-06", opposition="Rockingham",
                venue="Mike Barnett", season_name="Summer 1999/00", grade_name="A grade",
                result="LOSS", winning_team="Rockingham", match_format="One Day")
    for k, v in kw.items():
        if k in base:
            base[k] = "" if v is None else str(v)
    return base


INNINGS_1 = dict(opp_innings_number=2, batting_order_known="false",
                 innings_total=55, innings_wickets=2, innings_overs=40,
                 innings_byes=2, innings_wides=3,
                 opp_total=120, opp_wickets=8, opp_overs=40, opp_wides=4)

# THE REPORTED CASE, the shape the converter writes: four of ours batted, two
# fell (the opener at 10, number three at 30), 55 all told; Eve bowled at the
# opposition, who made 120/8.
SHEET = [
    row(player_name=NAMES[0], innings_number=1, batting_position=1, batting_runs=6,
        did_not_bat="false", batting_not_out="false", dismissal_type="bowled",
        fow_wicket=1, fow_score=10, **INNINGS_1),
    row(player_name=NAMES[1], innings_number=1, batting_position=2, batting_runs=20,
        did_not_bat="false", batting_not_out="true", **INNINGS_1),
    row(player_name=NAMES[2], innings_number=1, batting_position=3, batting_runs=9,
        did_not_bat="false", batting_not_out="false", dismissal_type="caught",
        fow_wicket=2, fow_score=30, **INNINGS_1),
    row(player_name=NAMES[3], innings_number=1, batting_position=4, batting_runs=15,
        did_not_bat="false", batting_not_out="true", **INNINGS_1),
    row(player_name=NAMES[4], innings_number=1, did_not_bat="true",
        bowling_overs=10, bowling_runs=30, bowling_wickets=3, bowling_wides=2, **INNINGS_1),
]

# A second match whose fall of wickets names a batter who was not at the
# crease: number four out at wicket one, before number three ever came in.
BROKEN = [
    row(game_key="SB-2", played_at="1999-11-13", player_name=NAMES[0], innings_number=1,
        batting_position=1, batting_runs=40, did_not_bat="false", batting_not_out="true",
        **INNINGS_1),
    row(game_key="SB-2", played_at="1999-11-13", player_name=NAMES[1], innings_number=1,
        batting_position=2, batting_runs=4, did_not_bat="false", batting_not_out="true",
        **INNINGS_1),
    row(game_key="SB-2", played_at="1999-11-13", player_name=NAMES[2], innings_number=1,
        batting_position=3, batting_runs=0, did_not_bat="false", batting_not_out="false",
        dismissal_type="bowled", fow_wicket=2, fow_score=30, **INNINGS_1),
    row(game_key="SB-2", played_at="1999-11-13", player_name=NAMES[3], innings_number=1,
        batting_position=4, batting_runs=1, did_not_bat="false", batting_not_out="false",
        dismissal_type="bowled", fow_wicket=1, fow_score=10, **INNINGS_1),
]

# An older sheet with none of the new columns: must import as it always did.
LEGACY = [
    row(game_key="SB-3", played_at="1999-11-20", player_name=NAMES[0], innings_number=1,
        batting_position=1, batting_runs=12, did_not_bat="false", batting_not_out="true"),
    row(game_key="SB-3", played_at="1999-11-20", player_name=NAMES[4], innings_number=1,
        did_not_bat="true", bowling_overs=8, bowling_runs=20, bowling_wickets=1),
]


def csv_text(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


class Viewer:
    def __init__(self, user_id):
        self.id = user_id


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)
        for stmt in COMP_DDL:
            await conn.execute(text(stmt))
        # Raw-SQL tables the lifespan creates and create_all cannot see.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL, canonical_name TEXT NOT NULL,
                alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS season_aliases (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL,
                canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                alias_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                undone_at TIMESTAMPTZ)
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS player_achievements (
                id SERIAL PRIMARY KEY, player_id UUID, organisation_id UUID, season TEXT)
        """))
        json_cols = (await conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type = 'json'"))).all()
        for tbl, col in json_cols:
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb '
                f'USING "{col}"::text::jsonb'))
        for name, sql in view_statements():
            await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
            await conn.execute(text(sql.replace("OR REPLACE ", "")))
        for stmt in SUPERSEDED_DDL:
            await conn.execute(text(stmt))


async def seed(session) -> None:
    session.add_all([
        User(id=USER, username="admin", password_hash="x"),
        Organisation(id=ORG, name="Shoalwater Bay", slug="shoalwater"),
        Season(id=SEASON, organisation_id=ORG, name="Summer 1999/00", year=1999),
        Grade(id=GRADE, season_id=SEASON, name="A grade", category="senior",
              categories=["senior"]),
        *[Player(id=PIDS[n], organisation_id=ORG, name=n) for n in NAMES],
    ])
    await session.commit()
    await session.execute(text(
        "INSERT INTO club_memberships (id, user_id, club_id, role) "
        "VALUES (gen_random_uuid(), :u, :o, 'super_admin')"), {"u": USER, "o": ORG})
    await session.commit()


async def game_id(session, key_date: str) -> uuid.UUID:
    return (await session.execute(text(
        "SELECT id FROM manual_games WHERE organisation_id = :o AND played_at = :d"),
        {"o": ORG, "d": __import__("datetime").date.fromisoformat(key_date)})).scalar()


async def rows_of(session, table: str, gid) -> list[dict]:
    try:
        res = await session.execute(text(
            f"SELECT * FROM {table} WHERE manual_game_id = :g "
            "ORDER BY innings_number, " + ("wicket_number" if table != "manual_innings"
                                             else "innings_number")), {"g": gid})
        return [dict(r) for r in res.mappings()]
    except Exception as exc:  # pragma: no cover - control run only
        await session.rollback()
        return [{"error": str(exc)}]


def verify_rule() -> None:
    print("\n-- THE PARTNERSHIP RULE ON ITS OWN --")
    if derive_partnerships is None:
        check("the partnership rule exists", False, "; ".join(MISSING))
        return
    bats = [{"position": p, "id": p} for p in (1, 2, 3, 4)]
    st = derive_partnerships(bats, [{"wicket": 1, "score": 10, "position": 1},
                                    {"wicket": 2, "score": 30, "position": 3}], 55, 2)
    check("each stand is the score's movement between wickets",
          st is not None and [s["runs"] for s in st] == [10, 20, 25], str(st))
    check("the pair at the crease follows the batting order",
          st is not None and [(s["batter1"]["id"], s["batter2"]["id"]) for s in st]
          == [(1, 2), (3, 2), (4, 2)], str(st and [(s["batter1"]["id"], s["batter2"]["id"]) for s in st]))
    check("the last stand is unbroken", st is not None and st[-1]["not_out"] and not st[0]["not_out"])
    check("no unbroken stand without an innings total",
          len(derive_partnerships(bats, [{"wicket": 1, "score": 10, "position": 1}]) or []) == 1)
    check("no unbroken stand once all ten are out",
          not any(s["not_out"] for s in derive_partnerships(
              [{"position": p} for p in range(1, 12)],
              [{"wicket": w, "score": w * 5, "position": w + 1 if w > 1 else 1}
               for w in range(1, 11)][:1]
              + [{"wicket": w, "score": w * 5, "position": w + 1} for w in range(2, 11)],
              60, 10) or [{"not_out": True}]))
    check("a batter out who was not in refuses the innings",
          derive_partnerships(bats, [{"wicket": 1, "score": 10, "position": 4}], 55, 1) is None)
    check("a gap in the batting order refuses it",
          derive_partnerships([{"position": 1}, {"position": 3}],
                              [{"wicket": 1, "score": 5, "position": 1}]) is None)
    check("a score that goes backwards refuses it",
          derive_partnerships(bats, [{"wicket": 1, "score": 20, "position": 1},
                                     {"wicket": 2, "score": 12, "position": 2}]) is None)
    check("wickets that disagree with the innings figure refuse it",
          derive_partnerships(bats, [{"wicket": 1, "score": 10, "position": 1}], 55, 3) is None)
    check("a missing wicket refuses it",
          derive_partnerships(bats, [{"wicket": 2, "score": 10, "position": 1}]) is None)
    check("an innings with no wicket is one unbroken opening stand",
          [s["runs"] for s in derive_partnerships(bats, [], 40, 0) or []] == [40])


async def main() -> None:
    verify_rule()
    await build_schema()
    async with Session() as s:
        await seed(s)

    print("\n-- THE REPORTED CASE: a CSFW match with the opposition and the stands --")
    async with Session() as s:
        c, u = await s.get(Organisation, ORG), await s.get(User, USER)
        out = await import_manual_games(
            file=FakeUpload(csv_text(SHEET + BROKEN + LEGACY)), current_user=u, club=c, db=s)
    check("all three matches import", out.get("games_created") == 3,
          str(out.get("errors_detail"))[:300])

    async with Session() as s:
        g1 = await game_id(s, "1999-11-06")
        inns = await rows_of(s, "manual_innings", g1)
        by_no = {r.get("innings_number"): r for r in inns}
        check("our innings is recorded with its total",
              by_no.get(1, {}).get("batting_side") == "us"
              and by_no.get(1, {}).get("total_runs") == 55, str(inns)[:300])
        check("the opposition's innings is recorded with its total",
              by_no.get(2, {}).get("batting_side") == "opposition"
              and by_no.get(2, {}).get("total_runs") == 120
              and by_no.get(2, {}).get("total_wickets") == 8, str(inns)[:300])
        check("each innings keeps its own extras",
              by_no.get(1, {}).get("byes") == 2 and by_no.get(2, {}).get("wides") == 4)
        bowl = (await s.execute(select(ManualBowlingSpell).where(
            ManualBowlingSpell.manual_game_id == g1))).scalars().all()
        check("our bowling is filed under the innings the opposition batted",
              [b.innings_number for b in bowl] == [2], str([b.innings_number for b in bowl]))
        fow = await rows_of(s, "manual_fall_of_wickets", g1)
        check("the fall of wickets lands, linked to our players",
              [(r.get("wicket_number"), r.get("score_at_fall")) for r in fow] == [(1, 10), (2, 30)]
              and fow[0].get("player_id") == PIDS[NAMES[0]], str(fow)[:300])
        stands = await rows_of(s, "manual_partnerships", g1)
        check("partnerships are worked out, the unbroken one included",
              [(r.get("wicket_number"), r.get("runs")) for r in stands]
              == [(1, 10), (2, 20), (3, 25)], str(stands)[:300])
        check("each stand names the right pair",
              [(r.get("batter1_id"), r.get("batter2_id")) for r in stands] == [
                  (PIDS[NAMES[0]], PIDS[NAMES[1]]), (PIDS[NAMES[2]], PIDS[NAMES[1]]),
                  (PIDS[NAMES[3]], PIDS[NAMES[1]])])
        game = await s.get(ManualGame, g1)
        check("the match records that its batting order is not known",
              getattr(game, "innings_order_known", None) is False)

        g2 = await game_id(s, "1999-11-13")
        check("a match whose fall of wickets does not reconcile keeps it",
              len(await rows_of(s, "manual_fall_of_wickets", g2)) == 2)
        check("and gets no partnerships rather than wrong ones",
              await rows_of(s, "manual_partnerships", g2) == [])

    print("\n-- THE MATCH PAGE --")
    async with Session() as s:
        card = await get_scorecard(str(g1), db=s)
    # The real payload, for the browser suite to render: set SCORECARD_FIXTURE.
    if os.environ.get("SCORECARD_FIXTURE"):
        import json
        Path(os.environ["SCORECARD_FIXTURE"]).write_text(json.dumps(card, default=str))
    check("names the club and the opposition in place of blank sides",
          card.get("home_team") == "Shoalwater Bay" and card.get("away_team") == "Rockingham",
          f"{card.get('home_team')!r} v {card.get('away_team')!r}")
    check("and says it does not know which was home", card.get("home_away_known") is False)
    check("and that the batting order is not known", card.get("innings_order_known") is False)
    totals = card.get("innings_totals") or {}
    t1, t2 = totals.get(1) or {}, totals.get(2) or {}
    check("our innings reads the scorebook's 55, extras once",
          (t1.get("runs") or 0) + (t1.get("extras") or 0) == 55, str(t1))
    check("the opposition's innings reads 120/8",
          (t2.get("runs") or 0) + (t2.get("extras") or 0) == 120 and t2.get("wickets") == 8,
          str(t2))
    check("under the opposition's name", t2.get("batting_team") == "Rockingham", str(t2))
    check("our bowlers bowl at the opposition, not at our own batters",
          {r.get("innings_number") for r in card.get("bowling") or []} == {2})
    check("the partnerships show on the match page", len(card.get("partnerships") or []) == 3)
    check("and the fall of wickets", len(card.get("fall_of_wickets") or []) == 2)

    print("\n-- THE CLUB'S RECORDS --")
    async with Session() as s:
        rec = await get_records(
            str(ORG), season_id=None, grade_id=None, grade_name=None, finals_only=False,
            captain_only=False, gender=None, categories=None, formats=None,
            competitions=None, debug_timing=False, viewer=None, db=s)
    top = (rec.get("partnerships") or {}).get("top_partnerships") or []
    check("the imported stands reach Highest Partnerships",
          any(p.get("runs") == 25 for p in top), str([p.get("runs") for p in top]))
    check("the broken match adds none",
          sorted(p.get("runs") for p in top) == [10, 20, 25], str([p.get("runs") for p in top]))

    print("\n-- AN OLDER SHEET IMPORTS AS IT ALWAYS DID --")
    async with Session() as s:
        g3 = await game_id(s, "1999-11-20")
        check("writes no innings rows", await rows_of(s, "manual_innings", g3) == [])
        bowl = (await s.execute(select(ManualBowlingSpell).where(
            ManualBowlingSpell.manual_game_id == g3))).scalars().all()
        check("keeps its bowling where the sheet put it", [b.innings_number for b in bowl] == [1])
        game = await s.get(ManualGame, g3)
        check("and claims nothing about batting order",
              getattr(game, "innings_order_known", None) is None)
    async with Session() as s:
        card3 = await get_scorecard(str(g3), db=s)
    check("its match page numbers its innings as before", card3.get("innings_order_known") is True)

    print("\n-- A SHEET THAT CONTRADICTS ITSELF IS REFUSED, NOT GUESSED --")
    async with Session() as s:
        c, u = await s.get(Organisation, ORG), await s.get(User, USER)
        bad = await import_manual_games(file=FakeUpload(csv_text([
            row(game_key="X-1", played_at="2000-01-08", player_name=NAMES[0], innings_number=1,
                batting_position=1, batting_runs=3, did_not_bat="false", opp_total=99),
            row(game_key="X-2", played_at="2000-01-15", player_name=NAMES[0], innings_number=1,
                batting_position=1, batting_runs=3, did_not_bat="false",
                opp_innings_number=1, opp_total=99),
        ])), current_user=u, club=c, db=s)
    errs = " | ".join(e.get("error", "") for e in bad.get("errors_detail") or [])
    check("opposition figures with no innings number to put them in",
          "opp_innings_number" in errs, errs[:300])
    check("one innings number claimed by both sides",
          "both our innings and the opposition's" in errs, errs[:300])

    print("\n-- UNDO OF AN OVERWRITE BRINGS EVERYTHING BACK --")
    if _snapshot_manual_game is None:
        check("the snapshot helpers exist", False, "; ".join(MISSING))
    else:
        async with Session() as s:
            snap = await _snapshot_manual_game(s, g1, ORG)
            await s.execute(text("DELETE FROM manual_games WHERE id = :g"), {"g": g1})
            await s.commit()
        async with Session() as s:
            await _restore_manual_game(s, snap, ORG)
            await s.commit()
        async with Session() as s:
            check("its innings rows", len(await rows_of(s, "manual_innings", g1)) == 2)
            check("its fall of wickets", len(await rows_of(s, "manual_fall_of_wickets", g1)) == 2)
            check("its partnerships, still linked to our players",
                  [r.get("batter1_id") for r in await rows_of(s, "manual_partnerships", g1)]
                  == [PIDS[NAMES[0]], PIDS[NAMES[2]], PIDS[NAMES[3]]])
            game = await s.get(ManualGame, g1)
            check("and its batting-order flag", getattr(game, "innings_order_known", None) is False)

    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
