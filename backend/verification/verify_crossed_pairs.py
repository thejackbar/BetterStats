"""Import matches an override paired with the wrong synced game are moved to the one
their scorecard matches, by swaps that never change which synced games are hidden.
Real Postgres, the shipped service.

Run:  DATABASE_URL=postgresql+asyncpg://root@/pl_verify?host=/var/run/postgresql \
      python verification/verify_crossed_pairs.py

Control:  CONTROL=1  the behaviour before this change (nothing moves a crossed pair).
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
        Base, BattingInnings, Game, Grade, ManualBattingInnings, ManualGame, Organisation,
        Player, Season, engine, async_session_maker,
    )
    from app.services import crossed_pairs as cp
    from verify_merge_carry import EXTRA_DDL

    if os.environ.get("CONTROL"):
        async def _nothing(db, org_id, *, apply=False, skip=()):
            return {"paired": 0, "moves": [], "held": [], "skipped": []}
        cp.repair_org = _nothing

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        for stmt in EXTRA_DDL:
            await conn.execute(text(stmt))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_manual_games_superseded_by_game "
            "ON manual_games (superseded_by_game_id) WHERE superseded_by_game_id IS NOT NULL"))

    org = u()
    season, grade = u(), u()
    players = [u() for _ in range(40)]
    ids: dict = {}

    def mid(k):
        return ids.setdefault(("m", k), u())

    def gid(k):
        return ids.setdefault(("g", k), u())

    async with async_session_maker() as db:
        db.add_all([Organisation(id=org, name="Payneham", slug="pay-x", is_active=True),
                    Season(id=season, organisation_id=org, name="Summer 2010/11", year=2010)])
        await db.flush()
        db.add(Grade(id=grade, season_id=season, name="U11"))
        await db.flush()
        for i, p in enumerate(players):
            db.add(Player(id=p, organisation_id=org, name=f"Player, N{i}", grassroots_id=str(p)))
        await db.flush()

        used = [0]

        def card(n=4):
            """n batters with runs no other card shares."""
            out = []
            for _ in range(n):
                k = used[0]
                used[0] += 1
                out.append((players[k % len(players)], 10 + k))
            return out

        async def add_game(key, day, opp, cards):
            db.add(Game(id=gid(key), grade_id=grade, played_at=day, home_team="Payneham",
                        away_team=opp, opp_club_name=opp, status="COMPLETED"))
            await db.flush()
            for p, r in cards:
                db.add(BattingInnings(game_id=gid(key), player_id=p, innings_number=1, runs=r,
                                      batting_position=1, not_out=False, did_not_bat=False))

        async def add_match(key, day, opp, cards, paired_to):
            db.add(ManualGame(id=mid(key), organisation_id=org, season_id=season, grade_id=grade,
                              played_at=day, opposition=opp,
                              superseded_by_game_id=gid(paired_to), pair_prefers_import=True,
                              pairing_locked=True))
            await db.flush()
            for p, r in cards:
                db.add(ManualBattingInnings(manual_game_id=mid(key), player_id=p,
                                            innings_number=1, runs=r, batting_position=1,
                                            did_not_bat=False))

        d = date(2010, 11, 13)
        # (1) two grades against one club on one day, paired crosswise
        ca, cb = card(), card()
        await add_game("A", d, "Hectorville", ca)
        await add_game("B", d, "Hectorville", cb)
        await add_match("M1", d, "Hectorville", ca, "B")     # should be A
        await add_match("M2", d, "Hectorville", cb, "A")     # should be B
        # (2) a correct pair that must not move
        cc = card()
        await add_game("C", d, "Grange", cc)
        await add_match("M3", d, "Grange", cc, "C")
        # (3) a three-way cycle: M7->8, M8->9, M9->7 should be 7, 8, 9
        c7, c8, c9 = card(), card(), card()
        d2 = date(2010, 11, 20)
        for k, c in (("G7", c7), ("G8", c8), ("G9", c9)):
            await add_game(k, d2, "Walkerville", c)
        await add_match("M7", d2, "Walkerville", c7, "G8")
        await add_match("M8", d2, "Walkerville", c8, "G9")
        await add_match("M9", d2, "Walkerville", c9, "G7")
        # (4) a pair whose card shares NOTHING with another game: not a move
        cd, ce = card(), card()
        d3 = date(2010, 11, 27)
        await add_game("D", d3, "Modbury", cd)
        await add_match("M4", d3, "Modbury", ce, "D")        # card matches nothing synced
        await db.flush()
        created = [str(mid(k)) for k in ("M1", "M2", "M3", "M7", "M8", "M9", "M4")]
        await db.execute(text("""INSERT INTO manual_edit_logs
            (organisation_id, action, target_table, target_id, after_json)
            VALUES (:o, 'import', 'manual_games', 'x', CAST(:j AS JSONB))"""),
            {"o": org, "j": '{"created_game_ids": ["%s"]}' % '","'.join(created)})
        await db.commit()

    async def targets():
        async with async_session_maker() as db:
            rows = (await db.execute(text(
                "SELECT id::text, superseded_by_game_id::text FROM manual_games "
                "WHERE organisation_id = :o"), {"o": org})).all()
        return {a: b for a, b in rows}

    async def repair(**kw):
        async with async_session_maker() as db:
            return await cp.repair_org(db, org, **kw)

    before = await targets()
    want = {"M1": "A", "M2": "B", "M7": "G7", "M8": "G8", "M9": "G9"}
    s = lambda k: str(mid(k))
    gs = lambda k: str(gid(k))

    dry = await repair(apply=False)
    check("a dry run lists exactly the crossed pairs, as swaps and a cycle",
          {m["manual_game_id"]: m["to_game"] for m in dry["moves"]},
          {s(k): gs(v) for k, v in want.items()})
    check("it reports how much better the scorecard fits",
          sorted((m["from_shared"], m["to_shared"]) for m in dry["moves"]),
          [(0, 4)] * 5)
    check("a correct pair and a pair with no better card are not touched",
          s("M3") not in {m["manual_game_id"] for m in dry["moves"]}
          and s("M4") not in {m["manual_game_id"] for m in dry["moves"]})
    check("a dry run changes nothing", await targets(), before)

    sk = await repair(apply=False, skip=[s("M1")[:8]])
    check("skipping one match of a swap holds the whole swap",
          sorted(m["manual_game_id"] for m in sk["moves"]),
          sorted(s(k) for k in ("M7", "M8", "M9")))
    check("and says which it skipped and which it held back because of that",
          ([m["manual_game_id"] for m in sk["skipped"]], [m["manual_game_id"] for m in sk["held"]]),
          ([s("M1")], [s("M2")]))

    res = await repair(apply=True)
    after = await targets()
    check("apply moves each crossed pair to the synced game its card matches",
          {k: after[s(k)] for k in want}, {k: gs(v) for k, v in want.items()})
    check("the untouched pairs stay where they were",
          (after[s("M3")], after[s("M4")]), (gs("C"), gs("D")))
    check("the set of hidden synced games is exactly what it was",
          sorted(v for v in after.values() if v), sorted(v for v in before.values() if v))
    check("no synced game is held by two matches",
          len([v for v in after.values() if v]), len({v for v in after.values() if v}))
    check("the move is in the audit log",
          await _scalar(async_session_maker,
                        "SELECT count(*) FROM audit_logs WHERE org_id = :o "
                        "AND action = 'repair_crossed_pairs'", o=org), 1)
    again = await repair(apply=True)
    check("a second run finds nothing to move", len(again["moves"]), 0)

    # the closure rule on its own: a move into a game held by a match that stays
    cur = {"a": "g1", "b": "g2", "c": "g3"}
    new = {"a": "g2", "b": "g2", "c": "g3"}
    sh = lambda m, g: {("a", "g1"): 0, ("a", "g2"): 3, ("b", "g2"): 4, ("c", "g3"): 4}.get((m, g), 0)
    mv, held = cp.plan_moves(cur, new, sh)
    check("a move into a game held by a match that stays put is held, not made",
          (mv, [h[0] for h in held]), ({}, ["a"]))
    mv2, _ = cp.plan_moves({"a": "g1", "b": "g2"}, {"a": "g2", "b": "g1"},
                           lambda m, g: 3 if (m, g) in (("a", "g2"), ("b", "g1")) else 0)
    check("a closed swap is made", mv2, {"a": "g2", "b": "g1"})
    mv3, _ = cp.plan_moves({"a": "g1"}, {"a": "g2"}, lambda m, g: 3)
    check("a move to a game no match of the club holds is never made", mv3, {})
    mv4, _ = cp.plan_moves({"a": "g1", "b": "g2"}, {"a": "g2", "b": "g1"}, lambda m, g: 2)
    check("a swap with no better scorecard is not made", mv4, {})

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


async def _scalar(maker, sql, **kw):
    async with maker() as db:
        return (await db.execute(text(sql), kw)).scalar()


asyncio.run(main())
