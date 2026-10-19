"""Verification for grade weighting on a medal (migration 346) against a real
Postgres. Runs the SHIPPED statements, service functions and route bodies. New
keys are read through presence-safe accessors, so the same script run against
the previous commit reports FAIL lines instead of crashing (the control run).

Usage:  cd backend && DATABASE_URL=postgresql+asyncpg://... \
            python scripts/verify_vote_grade_weights.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

DSN = os.environ["DATABASE_URL"]
PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail and not cond else ''}")


TODAY = date.today()
YEAR = TODAY.year if TODAY.month >= 7 else TODAY.year - 1
BASE = date(YEAR, 7, 15)

ORG = uuid.uuid4()
SEASON = uuid.uuid4()
G1, G2, GC = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
PLAYERS = [uuid.uuid4() for _ in range(5)]
A, B = PLAYERS[0], PLAYERS[1]   # A is voted best in the 2nd grade game, B in the 1st grade game
FX = {"1st": [], "2nd": [], "Colts": []}


async def seed(db) -> None:
    from app.models.db import (
        Fixture, Grade, Organisation, Player, Season, VoteBallot, VoteBallotPick, VoteMedal,
    )
    db.add(Organisation(id=ORG, name="Applecross CC", short_name="ACC", slug="applecross",
                        module_overrides=["select"]))
    db.add(Season(id=SEASON, organisation_id=ORG, name="Summer", year=YEAR))
    await db.flush()
    db.add(Grade(id=G1, season_id=SEASON, name="1st Grade", display_order=1))
    db.add(Grade(id=G2, season_id=SEASON, name="2nd Grade", display_order=2))
    db.add(Grade(id=GC, season_id=SEASON, name="Colts"))
    for i, pid in enumerate(PLAYERS):
        db.add(Player(id=pid, organisation_id=ORG, name=f"Player {i}"))
    await db.flush()

    def add_fixtures(key, grade, n, extra=()):
        for i in range(n):
            fid = uuid.uuid4()
            FX[key].append(fid)
            db.add(Fixture(id=fid, organisation_id=ORG, grade_id=grade, opponent_name=f"{key} opp {i}",
                           round=str(i + 1), played_on=BASE + timedelta(days=7 * i),
                           end_on=BASE + timedelta(days=7 * i), home_away="H",
                           status="FINAL" if i == 0 else "UPCOMING"))
        for status, ha in extra:  # not games: a bye and a cancelled round
            db.add(Fixture(id=uuid.uuid4(), organisation_id=ORG, grade_id=grade, opponent_name="x",
                           round="99", played_on=BASE + timedelta(days=300), home_away=ha, status=status))

    add_fixtures("1st", G1, 18)
    add_fixtures("2nd", G2, 12)
    add_fixtures("Colts", GC, 7, extra=(("BYE", "BYE"), ("CANCELLED", "H")))
    await db.flush()

    medal = VoteMedal(organisation_id=ORG, name="Club Champion", position=0, enabled=True, link_token="tok")
    db.add(medal)
    await db.flush()
    # One ballot per game: B tops the 1st grade game, A tops the 2nd grade game.
    for key, best in (("1st", B), ("2nd", A)):
        bid = uuid.uuid4()
        db.add(VoteBallot(id=bid, organisation_id=ORG, medal_id=medal.id, fixture_id=FX[key][0],
                          voter_player_id=PLAYERS[4], voter_kind="player", source="self"))
        await db.flush()
        others = [p for p in PLAYERS[2:4]]
        for pos, pid in enumerate([best] + others, start=1):
            db.add(VoteBallotPick(ballot_id=bid, position=pos, player_id=pid))
    await db.commit()


async def main() -> None:
    from app.models.db import Base, Grade, Organisation, VoteMedal
    from app.routers import votes as vr
    from app.services import votes as vs
    from app.services import vote_medal_ddl as ddl

    engine = create_async_engine(DSN, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    stmts = getattr(ddl, "VOTE_GRADE_WEIGHT_STATEMENTS", None)

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)

    if stmts:
        async with engine.begin() as conn:
            await conn.execute(text("ALTER TABLE vote_medals DROP COLUMN IF EXISTS grade_weighting"))
            for _ in range(3):
                for stmt in stmts:
                    await conn.execute(text(stmt))
        async with engine.connect() as conn:
            col = (await conn.execute(text(
                "SELECT column_default, is_nullable FROM information_schema.columns "
                "WHERE table_name='vote_medals' AND column_name='grade_weighting'"))).first()
        check("migration adds grade_weighting, NOT NULL, default empty, safe to re-run",
              col is not None and col[1] == "NO" and "{}" in (col[0] or ""), str(col))
    else:
        check("migration adds grade_weighting", False, "no VOTE_GRADE_WEIGHT_STATEMENTS")

    async with Session() as db:
        await seed(db)
        club = await db.get(Organisation, ORG)
        medal = (await vs.list_medals(db, ORG))[0]
        Body = vr.MedalUpdate

        async def patch(**kw):
            return await vr.update_medal(str(medal.id), Body(**kw), db=db, club=club, user=None)

        async def board():
            await db.refresh(medal)
            cfg = vs.effective_config(medal)
            return await vs.build_leaderboard(db, ORG, cfg, YEAR, medal=medal)

        def pts(b):
            return {s["name"]: s["points"] for s in b["standings"]}

        # ── Default: unweighted, as before ──
        cfg = vs.effective_config(medal)
        gw = cfg.get("grade_weighting")
        check("a medal starts unweighted", gw == {"mode": "off", "manual": {}}, str(gw))
        b = await board()
        check("unweighted: both 3-vote games are worth 3",
              pts(b).get("Player 0") == 3 and pts(b).get("Player 1") == 3, str(pts(b)))
        check("unweighted points stay whole numbers", all(isinstance(v, int) for v in pts(b).values()), str(pts(b)))

        # ── Validation ──
        async def refused(**kw):
            try:
                await patch(**kw)
            except HTTPException as e:
                return e.status_code
            except Exception as e:
                return type(e).__name__
            return None

        check("an unknown weighting mode is refused (400)",
              await refused(grade_weighting={"mode": "bonkers"}) == 400)
        check("a weight of 0 is refused (400)",
              await refused(grade_weighting={"mode": "manual", "manual": {"2nd Grade": 0}}) == 400)
        check("a weight of 11 is refused (400)",
              await refused(grade_weighting={"mode": "manual", "manual": {"2nd Grade": 11}}) == 400)
        check("a weight that is not a number is refused (400)",
              await refused(grade_weighting={"mode": "manual", "manual": {"2nd Grade": "lots"}}) == 400)
        await db.refresh(medal)
        check("a refused PATCH changed nothing", vs.effective_config(medal).get("grade_weighting") == gw)

        # ── Auto: top grade by the club's team order ──
        out = await patch(grade_weighting={"mode": "auto"})
        check("PATCH stores auto mode", (out.get("grade_weighting") or {}).get("mode") == "auto", str(out.get("grade_weighting")))
        out2 = await patch(name="Club Champion")
        check("a PATCH that does not send weighting leaves it alone",
              (out2.get("grade_weighting") or {}).get("mode") == "auto")

        info = await vs.resolve_grade_weights(db, ORG, vs.effective_config(medal), medal, YEAR, want_games=True) \
            if hasattr(vs, "resolve_grade_weights") else {}
        games = info.get("games", {})
        check("games come from fixtures, byes and cancelled rounds left out",
              games == {"1st Grade": 18, "2nd Grade": 12, "Colts": 7}, str(games))
        check("top grade is first in the club's team order", info.get("top_grade") == "1st Grade", str(info.get("top_grade")))
        w = info.get("weights", {})
        check("weight = top grade's games / the grade's games",
              abs(w.get("2nd Grade", 0) - 1.5) < 1e-9 and w.get("1st Grade") == 1 and abs(w.get("Colts", 0) - 18 / 7) < 1e-9,
              str(w))

        b = await board()
        check("auto: 3 votes in the 12 game grade now beat 3 in the 18 game grade (4.5 v 3)",
              pts(b).get("Player 0") == 4.5 and pts(b).get("Player 1") == 3, str(pts(b)))
        raw = {s["name"]: s["raw"] for s in b["standings"]}
        check("raw votes are never weighted", raw.get("Player 0") == 3 and raw.get("Player 1") == 3, str(raw))
        check("the board says which lens its points are under",
              (b.get("weighting") or {}).get("mode") == "auto" and (b.get("weighting") or {}).get("top_grade") == "1st Grade",
              str(b.get("weighting")))
        wk = [s["round_gain"] for s in b["standings"] if s["name"] == "Player 0"]
        check("weekly gain and form use the weighted points", wk == [4.5], str(wk))

        # ── Top grade fallbacks ──
        pick = getattr(vs, "pick_top_grade", None)
        check("no team order set: top grade is the one with the most games",
              pick is not None and pick({"A": 12, "B": 18, "C": 7}, {}, None) == "B")
        check("a team order beats game count (club says 2nd grade is the top)",
              pick is not None and pick({"A": 12, "B": 18}, {"A": 1}, None) == "A")
        check("a grade with no games is never the top",
              pick is not None and pick({"A": 0, "B": 5}, {"A": 1}, None) == "B")
        aw = getattr(vs, "auto_weights", None)
        check("top grade of 12 against an 18 game grade discounts it to 2/3",
              aw is not None and abs(aw({"top": 12, "long": 18}, "top")["long"] - 2 / 3) < 1e-9)

        # ── Manual ──
        out = await patch(grade_weighting={"mode": "manual", "manual": {"2nd Grade": 0.5, "Colts": 2}})
        check("PATCH stores manual weights",
              (out.get("grade_weighting") or {}).get("manual") == {"2nd Grade": 0.5, "Colts": 2.0},
              str(out.get("grade_weighting")))
        b = await board()
        check("manual: 3 votes in a grade weighted 0.5 are worth 1.5, an unlisted grade counts 1",
              pts(b).get("Player 0") == 1.5 and pts(b).get("Player 1") == 3, str(pts(b)))

        # ── Game detail ──
        d = await vr.fixture_detail(str(FX["2nd"][0]), medal_id=str(medal.id), db=db, club=club, user=None)
        top = max(d["results"], key=lambda r: r["points"])
        check("game detail shows the weighted points and the weight",
              top["points"] == 1.5 and d["fixture"].get("weight") == 0.5, f"{top['points']} {d['fixture'].get('weight')}")
        d1 = await vr.fixture_detail(str(FX["1st"][0]), medal_id=str(medal.id), db=db, club=club, user=None)
        check("a grade with no manual weight reads 1",
              d1["fixture"].get("weight") == 1.0 and max(r["points"] for r in d1["results"]) == 3)

        # ── Settings table ──
        t = await vr.medal_weighting(str(medal.id), db=db, club=club, user=None) if hasattr(vr, "medal_weighting") else {}
        rows = {r["name"]: r for r in t.get("rows", [])}
        check("table lists every team with its games",
              {n: r["games"] for n, r in rows.items()} == {"1st Grade": 18, "2nd Grade": 12, "Colts": 7}, str(rows))
        check("table always shows what auto would give",
              rows.get("2nd Grade", {}).get("auto_weight") == 1.5 and rows.get("1st Grade", {}).get("auto_weight") == 1.0
              and rows.get("Colts", {}).get("auto_weight") == 2.57, str(rows))
        check("table shows the weight actually in force (manual here)",
              rows.get("2nd Grade", {}).get("weight") == 0.5 and rows.get("1st Grade", {}).get("weight") == 1.0
              and rows.get("Colts", {}).get("weight") == 2.0, str(rows))
        check("table marks the top grade, in the club's team order",
              t.get("top_grade") == "1st Grade" and rows.get("1st Grade", {}).get("is_top") is True
              and [r["name"] for r in t.get("rows", [])][:2] == ["1st Grade", "2nd Grade"], str(t.get("top_grade")))
        check("table shows what a top vote is worth in each grade",
              rows.get("2nd Grade", {}).get("top_vote") == 1.5 and rows.get("1st Grade", {}).get("top_vote") == 3)

        # ── Back to off, and clear ──
        out = await patch(grade_weighting={})
        check("an empty weighting turns it off", (out.get("grade_weighting") or {}).get("mode") == "off",
              str(out.get("grade_weighting")))
        b = await board()
        check("off again: unweighted", pts(b).get("Player 0") == 3, str(pts(b)))

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
