"""Fall of wickets, partnerships and who took each wicket are copied from the synced card
an override replaced onto the import's own match, only where the scorecard confirms the
pair and the bowling figures agree. Real Postgres, the shipped service.

Run:  DATABASE_URL=postgresql+asyncpg://root@/pl_verify?host=/var/run/postgresql \
      python verification/verify_import_detail_restore.py

Control:  CONTROL=1  the behaviour before this change (nothing is copied).
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text  # noqa: E402

PASS = FAIL = 0


def check(label, got, want=True):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}: got {got!r}, want {want!r}")


def u():
    return uuid.uuid4()


async def main():
    from app.models.db import (
        Base, BattingInnings, BowlerWicket, FallOfWicket, Game, Grade, ManualBattingInnings,
        ManualBowlerWicket, ManualBowlingSpell, ManualFallOfWicket, ManualGame, Organisation,
        Partnership, Player, Season, engine, async_session_maker,
    )
    from app.services import import_detail_restore as idr
    from verify_merge_carry import EXTRA_DDL

    if os.environ.get("CONTROL"):
        async def _nothing(db, org_id, *, apply=False, limit_matches=None):
            return {"paired": 0, "fow": [], "part": [], "bw": [], "skipped": {}, "matches": 0,
                    "by_season": {}, "written": {"fow": 0, "part": 0, "bw": 0}}
        idr.restore_org = _nothing

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        for stmt in EXTRA_DDL:
            await conn.execute(text(stmt))

    org, other, season, grade = u(), u(), u(), u()
    P = {k: u() for k in ("a", "b", "c", "d", "e", "f", "bw1", "bw2", "fld", "opp")}
    M = {k: u() for k in ("1", "2", "3", "4", "5", "6", "7")}
    G = {k: u() for k in ("1", "2", "3", "4", "5", "6", "7")}
    day = date(2021, 11, 6)

    async with async_session_maker() as db:
        db.add_all([Organisation(id=org, name="Payneham", slug="pay-r", is_active=True),
                    Organisation(id=other, name="Elsewhere", slug="else-r", is_active=True),
                    Season(id=season, organisation_id=org, name="Summer 2021/22", year=2021)])
        await db.flush()
        db.add(Grade(id=grade, season_id=season, name="1st XI"))
        await db.flush()
        for k, p in P.items():
            db.add(Player(id=p, organisation_id=other if k == "opp" else org,
                          name=f"Player, {k.upper()}", grassroots_id=str(p)))
        await db.flush()
        for k, g in G.items():
            db.add(Game(id=g, grade_id=grade, played_at=day, home_team="A", away_team="B",
                        status="COMPLETED"))
        await db.flush()
        for k, m in M.items():
            db.add(ManualGame(id=m, organisation_id=org, season_id=season, grade_id=grade,
                              played_at=day, opposition="Opp",
                              superseded_by_game_id=G[k], pair_prefers_import=True,
                              pairing_locked=True))
        await db.flush()

        batters = ("a", "b", "c", "d")

        def cards(k, syn_inn, man_inn, shift=0):
            for i, b in enumerate(batters):
                db.add(BattingInnings(game_id=G[k], player_id=P[b], innings_number=syn_inn,
                                      runs=10 + i + shift, batting_position=i + 1,
                                      not_out=False, did_not_bat=False))
                db.add(ManualBattingInnings(manual_game_id=M[k], player_id=P[b],
                                            innings_number=man_inn, runs=10 + i,
                                            batting_position=i + 1, did_not_bat=False))

        def detail(k, our_syn, opp_syn):
            for n in (our_syn, opp_syn):
                for w in (1, 2):
                    db.add(FallOfWicket(game_id=G[k], innings_number=n, wicket_number=w,
                                        score_at_fall=10 * w, batter_name=f"B{w}"))
                    db.add(Partnership(game_id=G[k], innings_number=n, wicket_number=w,
                                       batter1_id=P["a"], batter2_id=P["b"], runs=9 * w,
                                       is_club_innings=(n == our_syn)))

        def spells(k, b1, b2):
            for key, w in (("bw1", b1), ("bw2", b2)):
                db.add(ManualBowlingSpell(manual_game_id=M[k], player_id=P[key],
                                          innings_number=2, overs=5, runs=20, wickets=w))

        def credits(k, syn_inn, who):
            for key, kind, fielder in who:
                db.add(BowlerWicket(game_id=G[k], innings_number=syn_inn, bowler_id=P[key],
                                    fielder_id=P[fielder] if fielder else None,
                                    batter_name="Opp batter", dismissal_type=kind))

        # 1: the full case. We batted SECOND in PlayHQ (innings 2), first in the import (1).
        cards("1", 2, 1); detail("1", 2, 1); spells("1", 2, 1)
        credits("1", 1, [("bw1", "caught", "fld"), ("bw1", "bowled", None), ("bw2", "lbw", None),
                         ("bw2", "run out", None)])
        db.add(BowlerWicket(game_id=G["1"], innings_number=1, bowler_id=P["opp"],
                            batter_name="Ours", dismissal_type="bowled"))   # the other club's
        # 2: bowling figures disagree (card says bw1 took 3), detail still comes across
        cards("2", 1, 1); detail("2", 1, 2); spells("2", 3, 1)
        credits("2", 2, [("bw1", "caught", "fld"), ("bw1", "bowled", None), ("bw2", "lbw", None)])
        # 3: the scorecard does not confirm the pair (every score differs)
        cards("3", 1, 1, shift=50); detail("3", 1, 2); spells("3", 1, 0)
        credits("3", 2, [("bw1", "bowled", None)])
        # 4: the import already holds fall of wickets for its innings: not doubled
        cards("4", 1, 1); detail("4", 1, 2); spells("4", 0, 0)
        db.add(ManualFallOfWicket(manual_game_id=M["4"], innings_number=1, wicket_number=1,
                                  score_at_fall=99, batter_name="Ours"))
        # 5: our innings do not line up (the import has two, PlayHQ one)
        cards("5", 1, 1); detail("5", 1, 2)
        db.add(ManualBattingInnings(manual_game_id=M["5"], player_id=P["a"], innings_number=3,
                                    runs=4, batting_position=1, did_not_bat=False))
        # 6: a two-day match: ours 1 and 3 in the import, 1 and 3 in PlayHQ, theirs 2 and 4
        cards("6", 1, 1); cards("6", 3, 3); detail("6", 1, 2); detail("6", 3, 4)
        # 7: the import already holds who took each wicket: left alone
        cards("7", 1, 1); spells("7", 1, 0)
        credits("7", 2, [("bw1", "bowled", None)])
        db.add(ManualBowlerWicket(manual_game_id=M["7"], innings_number=2, bowler_id=P["bw1"],
                                  dismissal_type="bowled"))
        await db.flush()
        await db.execute(text("""INSERT INTO manual_edit_logs
            (organisation_id, action, target_table, target_id, after_json)
            VALUES (:o, 'import', 'manual_games', 'x', CAST(:j AS JSONB))"""),
            {"o": org, "j": '{"created_game_ids": ["%s"]}' % '","'.join(str(m) for m in M.values())})
        await db.commit()

    async def n(table, mk):
        async with async_session_maker() as db:
            return (await db.execute(text(
                f"SELECT count(*) FROM {table} WHERE manual_game_id = :m"), {"m": M[mk]})).scalar()

    async def innings(table, mk):
        async with async_session_maker() as db:
            return sorted({r[0] for r in (await db.execute(text(
                f"SELECT innings_number FROM {table} WHERE manual_game_id = :m"),
                {"m": M[mk]})).all()})

    async def go(**kw):
        async with async_session_maker() as db:
            return await idr.restore_org(db, org, **kw)

    dry = await go()
    check("a dry run counts what it would copy",
          (len(dry["fow"]), len(dry["part"]), len(dry["bw"])), (18, 20, 3))
    check("a dry run writes nothing",
          [await n("manual_fall_of_wickets", k) for k in ("1", "2", "6")], [0, 0, 0])
    check("and lists why a match was skipped",
          ({k: len(v) for k, v in dry["skipped"].items()}),
          {idr.SKIP_PAIR: 1, idr.SKIP_INNINGS: 1, idr.SKIP_CREDITS: 1})

    small = await go(limit_matches=1)
    check("a limit keeps only the first match that would gain detail",
          (small["matches"], len({r["mid"] for k in ("fow", "part", "bw") for r in small[k]})), (1, 1))
    res = await go(apply=True)
    check("apply writes the same counts", res["written"], {"fow": 18, "part": 20, "bw": 3})
    check("fall of wickets and partnerships are put on the import's own innings numbers "
          "(ours 1, theirs 2) though PlayHQ numbered them 2 and 1",
          (await innings("manual_fall_of_wickets", "1"), await innings("manual_partnerships", "1")),
          ([1, 2], [1, 2]))
    check("a two-day match lines up ours 1 and 3 with theirs 2 and 4",
          await innings("manual_fall_of_wickets", "6"), [1, 2, 3, 4])
    check("who took each wicket is copied, onto the opposition's innings, run outs left out",
          (await n("manual_bowler_wickets", "1"), await innings("manual_bowler_wickets", "1")),
          (3, [2]))
    async with async_session_maker() as db:
        fielded = (await db.execute(text(
            "SELECT count(*) FROM manual_bowler_wickets WHERE manual_game_id = :m "
            "AND fielder_id = :f AND dismissal_type = 'caught'"), {"m": M["1"], "f": P["fld"]})).scalar()
        other = (await db.execute(text(
            "SELECT count(*) FROM manual_bowler_wickets WHERE bowler_id = :b"),
            {"b": P["opp"]})).scalar()
    check("the catcher is named", fielded, 1)
    check("another club's bowler credit is never copied", other, 0)
    check("when the bowling figures disagree no credits are written, the rest still is",
          (await n("manual_bowler_wickets", "2"), await n("manual_fall_of_wickets", "2")), (0, 4))
    check("a pair the scorecard does not confirm gets nothing",
          [await n(t, "3") for t in ("manual_fall_of_wickets", "manual_partnerships",
                                     "manual_bowler_wickets")], [0, 0, 0])
    check("an innings the import already holds is not doubled, the other is filled",
          (await n("manual_fall_of_wickets", "4"), await innings("manual_fall_of_wickets", "4")),
          (3, [1, 2]))
    check("an innings count that does not line up gets nothing", await n("manual_fall_of_wickets", "5"), 0)
    check("credits the import already holds are left alone", await n("manual_bowler_wickets", "7"), 1)
    again = await go(apply=True)
    check("a second run finds nothing to copy",
          (len(again["fow"]), len(again["part"]), len(again["bw"])), (0, 0, 0))

    audit_id = res["audit_id"]
    async with async_session_maker() as db:
        removed = await idr.undo_org(db, org, audit_id=audit_id)
    check("undo removes exactly what the run wrote", removed, {"fow": 18, "part": 20, "bw": 3})
    check("and leaves the import's own row",
          (await n("manual_fall_of_wickets", "4"), await n("manual_bowler_wickets", "7")), (1, 1))

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
