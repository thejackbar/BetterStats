"""Balls faced on the synced card an import replaced are copied onto the import's own
batting lines, only where it is certainly the same player's innings. Real Postgres, the
shipped service.

Run:  DATABASE_URL=postgresql+asyncpg://root@/pl_verify?host=/var/run/postgresql \
      python verification/verify_import_balls_enrich.py

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
        Base, BattingInnings, Game, Grade, ManualBattingInnings, ManualGame, Organisation,
        Player, Season, engine, async_session_maker,
    )
    from app.services import import_balls_enrich as ibe
    from verify_merge_carry import EXTRA_DDL

    if os.environ.get("CONTROL"):
        async def _nothing(db, org_id, *, apply=False, limit=None):
            return {"lines": [], "ambiguous": 0, "games": 0, "by_season": {}, "filled": 0}
        ibe.enrich_org = _nothing

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        for stmt in EXTRA_DDL:
            await conn.execute(text(stmt))

    org, season, grade = u(), u(), u()
    P = {k: u() for k in ("a", "b", "c", "d", "e", "f", "g", "h", "i")}
    gp, gu, gh = u(), u(), u()           # paired synced game, unpaired game, hand-typed pair
    mp_, mu_, mh = u(), u(), u()         # import match paired, import match unpaired, hand-typed
    rows: dict = {}

    async with async_session_maker() as db:
        db.add_all([Organisation(id=org, name="Payneham", slug="pay-b", is_active=True),
                    Season(id=season, organisation_id=org, name="Summer 2021/22", year=2021)])
        await db.flush()
        db.add(Grade(id=grade, season_id=season, name="1st XI"))
        await db.flush()
        for k, p in P.items():
            db.add(Player(id=p, organisation_id=org, name=f"Player, {k.upper()}",
                          grassroots_id=str(p)))
        for g in (gp, gu, gh):
            db.add(Game(id=g, grade_id=grade, played_at=date(2021, 11, 6), home_team="A",
                        away_team="B", status="COMPLETED"))
        await db.flush()
        for m, g, paired in ((mp_, gp, True), (mu_, gu, False), (mh, gh, True)):
            db.add(ManualGame(id=m, organisation_id=org, season_id=season, grade_id=grade,
                              played_at=date(2021, 11, 6), opposition="Opp",
                              superseded_by_game_id=g if paired else None,
                              pair_prefers_import=paired, pairing_locked=paired))
        await db.flush()

        def synced(g, key, runs, pos, balls, dnb=False, inns=1):
            db.add(BattingInnings(game_id=g, player_id=P[key], innings_number=inns, runs=runs,
                                  batting_position=pos, balls=balls, not_out=False,
                                  did_not_bat=dnb))

        async def imp(m, key, runs, pos, balls=None, dnb=False):
            r = ManualBattingInnings(manual_game_id=m, player_id=P[key], innings_number=1,
                                     runs=runs, batting_position=pos, balls=balls,
                                     did_not_bat=dnb)
            db.add(r)
            await db.flush()
            rows[(m, key)] = r.id

        # paired match
        synced(gp, "a", 30, 1, 25); await imp(mp_, "a", 30, 1)                 # fills
        synced(gp, "b", 12, 2, 14); await imp(mp_, "b", 13, 2)                 # runs differ
        synced(gp, "c", 7, 3, 9);   await imp(mp_, "c", 7, 4)                  # position differs
        synced(gp, "d", 22, 4, 18); await imp(mp_, "d", 22, 4, balls=20)       # already has balls
        synced(gp, "e", 5, 5, 0);   await imp(mp_, "e", 5, 5)                  # PlayHQ: not recorded
        synced(gp, "f", 0, 6, None); await imp(mp_, "f", 0, 6)                 # PlayHQ: no figure
        synced(gp, "g", 41, 7, 33); await imp(mp_, "g", 41, 7, dnb=True)       # import did not bat
        # a two-day match: the same man made 9 at number 8 in BOTH innings, so two synced
        # lines fit one import line and it is a coin toss which figure is his
        synced(gp, "h", 9, 8, 11);  synced(gp, "h", 9, 8, 12, inns=2)
        await imp(mp_, "h", 9, 8)
        # unpaired import match and a hand-typed paired match
        synced(gu, "a", 30, 1, 25); await imp(mu_, "a", 30, 1)
        synced(gh, "a", 30, 1, 25); await imp(mh, "a", 30, 1)
        await db.flush()
        await db.execute(text("""INSERT INTO manual_edit_logs
            (organisation_id, action, target_table, target_id, after_json)
            VALUES (:o, 'import', 'manual_games', 'x', CAST(:j AS JSONB))"""),
            {"o": org, "j": '{"created_game_ids": ["%s","%s"]}' % (mp_, mu_)})
        await db.commit()

    async def balls(m, key):
        async with async_session_maker() as db:
            return (await db.execute(text(
                "SELECT balls FROM manual_batting_innings WHERE id = :i"),
                {"i": rows[(m, key)]})).scalar()

    async def run(**kw):
        async with async_session_maker() as db:
            return await ibe.enrich_org(db, org, **kw)

    dry = await run()
    check("a dry run lists only the one line that is certainly the same innings",
          dry["lines"], [(rows[(mp_, "a")], 25)])
    check("a dry run says how many matches and which seasons",
          (dry["games"], list(dry["by_season"]), dry["by_season"].get("Summer 2021/22")),
          (1, ["Summer 2021/22"], {"lines": 1, "games": 1}))
    check("a line with two synced fits is counted as ambiguous, not filled", dry["ambiguous"], 1)
    check("a dry run changes nothing", await balls(mp_, "a"), None)

    res = await run(apply=True)
    check("apply fills that line", (await balls(mp_, "a"), res["filled"]), (25, 1))
    for key, why in (("b", "different runs"), ("c", "different batting position"),
                     ("e", "PlayHQ stores 0 for not recorded"), ("f", "PlayHQ has no figure"),
                     ("g", "the import line is a did-not-bat"), ("h", "two synced lines fit")):
        check(f"left alone: {why}", await balls(mp_, key), None)
    check("a line that already has balls faced keeps its own", await balls(mp_, "d"), 20)
    check("an import match that is not paired is untouched", await balls(mu_, "a"), None)
    check("a hand-typed match is untouched", await balls(mh, "a"), None)
    again = await run(apply=True)
    check("a second run finds nothing to fill", (len(again["lines"]), again["filled"]), (0, 0))
    check("the run is in the audit log with the row ids and figures",
          await (_scalar(async_session_maker,
                         "SELECT details->'balls' FROM audit_logs WHERE org_id = :o "
                         "AND action = 'enrich_import_balls'", o=org)), [25])

    # undo: only a line still holding the figure the run put there
    audit_id = res["audit_id"]
    async with async_session_maker() as db:
        await db.execute(text("UPDATE manual_batting_innings SET balls = 27 WHERE id = :i"),
                         {"i": rows[(mp_, "a")]})
        await db.commit()
        n = await ibe.undo_org(db, org, audit_id=audit_id)
    check("undo leaves a line a person has corrected since", (n, await balls(mp_, "a")), (0, 27))
    async with async_session_maker() as db:
        await db.execute(text("UPDATE manual_batting_innings SET balls = 25 WHERE id = :i"),
                         {"i": rows[(mp_, "a")]})
        await db.commit()
        n = await ibe.undo_org(db, org, audit_id=audit_id)
    check("undo puts the filled line back to no balls faced", (n, await balls(mp_, "a")), (1, None))

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


async def _scalar(maker, sql, **kw):
    async with maker() as db:
        return (await db.execute(text(sql), kw)).scalar()


asyncio.run(main())
