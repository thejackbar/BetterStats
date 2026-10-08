"""Verification for Fantasy managers who join after the season has started, against a
real Postgres.

Reported: a new player could register but not enter a team once the season had
started ("The season has started - squad changes go through transfers"). Wanted: a
new player can enter a team and starts on the same points as the lowest team.

Runs the SHIPPED `routers/public_fantasy` route bodies (`build_squad`, `me`) and
`services/fantasy_squad`. Only the club / session / season lookups are stubbed.

CONTROL (`--control`): `routers/public_fantasy.py` at git HEAD is loaded and a late
joiner is sent through it. It must fail on exactly the reported behaviour (a 409 on
the first save), read through presence-safe accessors.

Run:  DATABASE_URL=postgresql+asyncpg://root@/fantasy_late?host=/var/run/postgresql \
      python verification/verify_fantasy_late_join.py [--control]
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import (
    Base, Organisation, Player, FantasySeason, FantasyRound, FantasyLeague, FantasyManager,
    FantasySquad, FantasySquadPlayer, FantasyPoolPlayer,
)
from app.services import fantasy_squad
from app.routers import public_fantasy

DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)
REPO = Path(__file__).resolve().parent.parent.parent

PASS = FAIL = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}{('  - ' + detail) if detail else ''}")


NOW = datetime.now(timezone.utc)
ORG = uuid.uuid4()
FS_ID = uuid.uuid4()
R1, R2, R3, R4 = (uuid.uuid4() for _ in range(4))
B1, B2, W1, W2 = (uuid.uuid4() for _ in range(4))   # pool: two batters, two bowlers
RULES = {"squad_size": 2, "role_quota": {"keeper": 0, "batter": 1, "allrounder": 0, "bowler": 1},
         "budget": 20, "count_best_n": 2}
MGR = {n: uuid.uuid4() for n in ("X", "Y", "E", "L", "M", "N", "O")}
SQ = {n: uuid.uuid4() for n in ("X", "Y", "E")}
LEAGUE_ID = uuid.uuid4()


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        for (tbl,) in (await conn.execute(text(
                "SELECT table_name FROM information_schema.columns WHERE table_schema='public' "
                "AND column_name='id' AND table_name LIKE 'fantasy\\_%' AND data_type='uuid'"))).all():
            await conn.execute(text(f'ALTER TABLE "{tbl}" ALTER COLUMN id SET DEFAULT gen_random_uuid()'))
        for tbl, col in (await conn.execute(text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND data_type = 'json'"))).all():
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb USING "{col}"::text::jsonb'))
        # The shipped DDL on top of a table that already has the column is a no-op,
        # and on a table without it adds it: prove both by running it twice.
        from app.services.fantasy_late_join_ddl import STATEMENTS
        for _ in range(2):
            for stmt in STATEMENTS:
                await conn.execute(text(stmt))


async def seed() -> None:
    async with Session() as s:
        s.add(Organisation(id=ORG, name="Alpha CC", slug="alpha", is_active=True))
        await s.flush()
        s.add_all([Player(id=p, name=n, organisation_id=ORG, grassroots_id=g)
                   for p, n, g in ((B1, "Bat One", "b1"), (B2, "Bat Two", "b2"),
                                   (W1, "Bowl One", "w1"), (W2, "Bowl Two", "w2"))])
        s.add(FantasySeason(id=FS_ID, organisation_id=ORG, season_year=2026, name="2026 Fantasy",
                            status="active", registration_open=True, scoring={}, rules=RULES))
        await s.flush()
        past = NOW - timedelta(days=20)
        s.add_all([
            FantasyRound(id=R1, fantasy_season_id=FS_ID, organisation_id=ORG, round_number=1, name="Round 1",
                         lock_at=past, status="scored"),
            FantasyRound(id=R2, fantasy_season_id=FS_ID, organisation_id=ORG, round_number=2, name="Round 2",
                         lock_at=past + timedelta(days=7), status="scored"),
            FantasyRound(id=R3, fantasy_season_id=FS_ID, organisation_id=ORG, round_number=3, name="Round 3",
                         lock_at=NOW + timedelta(days=3), status="upcoming"),
            FantasyRound(id=R4, fantasy_season_id=FS_ID, organisation_id=ORG, round_number=4, name="Round 4",
                         lock_at=NOW + timedelta(days=10), status="upcoming"),
        ])
        s.add_all([FantasyPoolPlayer(fantasy_season_id=FS_ID, organisation_id=ORG, player_id=p, role=r,
                                     base_price=5, current_price=5, is_available=True)
                   for p, r in ((B1, "batter"), (B2, "batter"), (W1, "bowler"), (W2, "bowler"))])
        s.add_all([FantasyManager(id=m, organisation_id=ORG, display_name=f"Mgr {n}", email=f"{n}@x.test")
                   for n, m in MGR.items()])
        s.add(FantasyLeague(id=LEAGUE_ID, fantasy_season_id=FS_ID, organisation_id=ORG,
                            kind="global_salary_cap", name="Club ladder"))
        await s.flush()
        for n in ("X", "Y", "E"):
            s.add(FantasySquad(id=SQ[n], fantasy_season_id=FS_ID, league_id=LEAGUE_ID, manager_id=MGR[n],
                               organisation_id=ORG, team_name=f"{n} Team", free_transfers=1))
        await s.flush()
        # X and Y hold picks; E is an empty squad on 0 that must not set the floor.
        for n, bat, bowl in (("X", B1, W1), ("Y", B2, W2)):
            s.add_all([FantasySquadPlayer(squad_id=SQ[n], player_id=bat, role="batter", is_captain=True),
                       FantasySquadPlayer(squad_id=SQ[n], player_id=bowl, role="bowler")])
        await s.commit()
        # Scored rounds: X 40 + 30 = 70, Y 20 + 10 = 30 (the lowest with picks).
        for sq, rid, pts in (("X", R1, 40), ("X", R2, 30), ("Y", R1, 20), ("Y", R2, 10)):
            await s.execute(text("""INSERT INTO fantasy_squad_round_scores (squad_id, round_id, points, raw_points, lineup)
                                    VALUES (:s, :r, :p, :p, '[]')"""), {"s": SQ[sq], "r": rid, "p": pts})
        await s.commit()
        fs = await s.get(FantasySeason, FS_ID)
        await fantasy_squad.recompute_squad_totals(s, fs)
        await s.commit()


async def join(mod, who: str, bat=B1, bowl=W1):
    """Run the shipped build_squad as manager `who`; returns (result, HTTPException|None)."""
    async with Session() as s:
        org = await s.get(Organisation, ORG)
        mgr = await s.get(FantasyManager, MGR[who])
        season = await s.get(FantasySeason, FS_ID)

        async def _club(db, token): return org
        async def _mgr(db, request, club): return mgr
        async def _season(db, club): return await db.get(FantasySeason, FS_ID)
        saved = (mod._club_for_token, mod._manager_for_session, mod._current_season)
        mod._club_for_token, mod._manager_for_session, mod._current_season = _club, _mgr, _season
        try:
            body = mod.SquadBody(team_name=f"{who} FC", picks=[
                mod.Pick(player_id=str(bat), is_captain=True), mod.Pick(player_id=str(bowl))])
            return await mod.build_squad("tok", body, None, s), None
        except HTTPException as e:
            return None, e
        finally:
            mod._club_for_token, mod._manager_for_session, mod._current_season = saved


async def me(who: str) -> dict:
    async with Session() as s:
        org = await s.get(Organisation, ORG)
        mgr = await s.get(FantasyManager, MGR[who])

        async def _club(db, token): return org
        async def _mgr(db, request, club): return mgr
        async def _season(db, club): return await db.get(FantasySeason, FS_ID)
        saved = (public_fantasy._club_for_token, public_fantasy._manager_for_session, public_fantasy._current_season)
        public_fantasy._club_for_token, public_fantasy._manager_for_session, public_fantasy._current_season = _club, _mgr, _season
        try:
            return await public_fantasy.me("tok", None, s)
        finally:
            public_fantasy._club_for_token, public_fantasy._manager_for_session, public_fantasy._current_season = saved


async def squad_row(who: str):
    async with Session() as s:
        return (await s.execute(text(
            "SELECT total_points, catchup_points, joined_round, free_transfers FROM fantasy_squads WHERE manager_id=:m"),
            {"m": MGR[who]})).first()


async def sql(q: str, **p):
    async with Session() as s:
        r = await s.execute(text(q), p)
        await s.commit()
        return r


async def run_control() -> int:
    src = subprocess.check_output(["git", "show", "HEAD:backend/app/routers/public_fantasy.py"], cwd=REPO, text=True)
    spec = importlib.util.spec_from_loader("public_fantasy_head", loader=None)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["public_fantasy_head"] = mod   # pydantic resolves the models' annotations through it
    exec(compile(src, "public_fantasy_head.py", "exec"), mod.__dict__)
    print("CONTROL: public_fantasy at git HEAD, a manager joins after the season has started")
    res, err = await join(mod, "L")
    check("late joiner is accepted", res is not None and res.get("status") == "ok",
          f"refused {getattr(err, 'status_code', '?')}: {getattr(err, 'detail', '?')}")
    row = await squad_row("L")
    check("and starts on the lowest team's points", row is not None and float(row[0]) == 30.0,
          "no squad was created" if row is None else repr(row))
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


async def main() -> int:
    await build_schema()
    await seed()
    if "--control" in sys.argv:
        return await run_control()

    print("A manager with no squad, season running")
    m = await me("L")
    check("the screen is told the starting points (lowest team with picks, empty squads ignored)",
          m.get("start_points") == 30.0, repr(m.get("start_points")))
    res, err = await join(public_fantasy, "L")
    check("a new manager can enter a team after the season has started",
          res is not None and res.get("status") == "ok", f"{getattr(err, 'status_code', '?')}: {getattr(err, 'detail', '')}")
    row = await squad_row("L")
    check("they start level with the lowest team (30)", row is not None and float(row[0]) == 30.0, repr(row))
    check("kept as catch-up points, scoring from round 3", row is not None and float(row[1]) == 30.0 and row[2] == 3, repr(row))
    check("one free transfer as usual", row is not None and row[3] == 1, repr(row))
    m = await me("L")
    sq = m.get("squad") or {}
    check("/me shows the total, catch-up and that they may still rebuild",
          sq.get("total_points") == 30.0 and sq.get("catchup_points") == 30.0 and sq.get("can_rebuild") is True, repr(sq))
    check("and no longer offers a start figure", m.get("start_points") is None, repr(m.get("start_points")))

    print("Rebuilding before their first round locks")
    res, err = await join(public_fantasy, "L", bat=B2, bowl=W2)
    row = await squad_row("L")
    picks = {str(r[0]) for r in (await sql("SELECT player_id FROM fantasy_squad_players sp JOIN fantasy_squads s ON s.id=sp.squad_id WHERE s.manager_id=:m", m=MGR["L"])).all()}
    check("they can redo the squad", res is not None and picks == {str(B2), str(W2)}, f"{getattr(err, 'detail', '')} {picks}")
    check("the starting points do not change", row is not None and float(row[0]) == 30.0 and float(row[1]) == 30.0, repr(row))
    n = (await sql("SELECT COUNT(*) FROM fantasy_squads WHERE manager_id=:m", m=MGR["L"])).scalar()
    check("still one squad", n == 1, str(n))

    print("Everyone already in is unchanged")
    res, err = await join(public_fantasy, "X")
    check("a manager with a squad from before the season still goes through transfers",
          res is None and err is not None and err.status_code == 409, f"{res} {getattr(err, 'status_code', '')}")
    x = await squad_row("X")
    check("their points are untouched", x is not None and float(x[0]) == 70.0 and float(x[1]) == 0.0 and x[2] is None, repr(x))

    print("Scoring only from the round they joined")
    async with Session() as s:
        fs = await s.get(FantasySeason, FS_ID)
        r1 = await s.get(FantasyRound, R1)
        await fantasy_squad.score_squads_for_round(s, fs, r1, rollover=False)   # an admin re-score of an old round with live picks
        await s.commit()
    n = (await sql("SELECT COUNT(*) FROM fantasy_squad_round_scores srs JOIN fantasy_squads s ON s.id=srs.squad_id WHERE s.manager_id=:m", m=MGR["L"])).scalar()
    row = await squad_row("L")
    check("re-scoring an earlier round gives them no points for it", n == 0 and float(row[0]) == 30.0, f"rows={n} {row}")
    # Round 3: their batter makes 12.
    await sql("""INSERT INTO fantasy_player_round_scores (fantasy_season_id, round_id, player_id, base_points, total_points, breakdown, games_counted)
                 VALUES (:fs, :r, :p, 12, 12, '{}', 1)""", fs=FS_ID, r=R3, p=B2)
    async with Session() as s:
        fs = await s.get(FantasySeason, FS_ID)
        r3 = await s.get(FantasyRound, R3)
        await fantasy_squad.score_squads_for_round(s, fs, r3, rollover=False)
        await s.commit()
    row = await squad_row("L")
    check("round 3 adds to the starting points (captain doubles 12 = 24; 30 + 24)",
          row is not None and float(row[0]) == 54.0 and float(row[1]) == 30.0, repr(row))
    async with Session() as s:
        fs = await s.get(FantasySeason, FS_ID)
        await fantasy_squad.recompute_squad_totals(s, fs)
        await s.commit()
    row = await squad_row("L")
    check("a later recompute keeps the starting points", row is not None and float(row[0]) == 54.0, repr(row))

    print("After their first round locks")
    await sql("UPDATE fantasy_rounds SET lock_at = :t WHERE id = :r", t=NOW - timedelta(hours=1), r=R3)
    res, err = await join(public_fantasy, "L")
    check("nobody enters or rebuilds during a locked round", res is None and err is not None and err.status_code == 403,
          f"{getattr(err, 'status_code', '')}")
    res, err = await join(public_fantasy, "M")
    check("a second newcomer waits for the lock to clear (no sneaking in on known scores)",
          res is None and err is not None and err.status_code == 403, f"{getattr(err, 'status_code', '')}")
    await sql("UPDATE fantasy_rounds SET status = 'scored' WHERE id = :r", r=R3)
    res, err = await join(public_fantasy, "L")
    check("once it scores, their squad goes through transfers like everyone's",
          res is None and err is not None and err.status_code == 409, f"{getattr(err, 'status_code', '')}")

    print("A later joiner starts level with the lowest team then")
    # Scored totals now: X 70, Y 30, L 30 + 24 = 54 (round 3 scored). Y is still lowest.
    await sql("UPDATE fantasy_squads SET catchup_points = 0 WHERE id = :s", s=SQ["Y"])
    res, err = await join(public_fantasy, "M", bat=B1, bowl=W2)
    row = await squad_row("M")
    check("M joins on the lowest scored total (30), scoring from round 4",
          res is not None and row is not None and float(row[0]) == 30.0 and row[2] == 4, f"{getattr(err, 'detail', '')} {row}")

    print("A round still in progress does not set the floor")
    await sql("""INSERT INTO fantasy_squad_round_scores (squad_id, round_id, points, raw_points, lineup)
                 VALUES (:s, :r, -50, -50, '[]')""", s=SQ["Y"], r=R4)
    res, err = await join(public_fantasy, "N", bat=B2, bowl=W1)
    row = await squad_row("N")
    check("a provisional round-4 figure is ignored (N starts on 30, not -20)",
          res is not None and row is not None and float(row[0]) == 30.0, f"{getattr(err, 'detail', '')} {row}")

    print("Season states")
    await sql("UPDATE fantasy_seasons SET status = 'completed' WHERE id = :f", f=FS_ID)
    res, err = await join(public_fantasy, "O")
    check("a finished season takes no new teams", res is None and err is not None and err.status_code == 403,
          f"{getattr(err, 'status_code', '')}")
    await sql("UPDATE fantasy_seasons SET status = 'open' WHERE id = :f", f=FS_ID)
    await sql("UPDATE fantasy_rounds SET status = 'upcoming' WHERE id IN (:a, :b)", a=R3, b=R4)
    await sql("UPDATE fantasy_rounds SET status = 'upcoming', lock_at = :t WHERE id = :a", a=R1, t=NOW + timedelta(days=30))
    res, err = await join(public_fantasy, "O", bat=B1, bowl=W1)
    row = await squad_row("O")
    check("before the season starts nothing changes: no catch-up, no joined round",
          res is not None and row is not None and float(row[0]) == 0.0 and float(row[1]) == 0.0 and row[2] is None,
          f"{getattr(err, 'detail', '')} {row}")

    print("DDL")
    from app.services.fantasy_late_join_ddl import DOWNGRADE
    col = (await sql("SELECT is_nullable, column_default FROM information_schema.columns WHERE table_name='fantasy_squads' AND column_name='catchup_points'")).first()
    check("catchup_points is NOT NULL DEFAULT 0", col is not None and col[0] == "NO" and "0" in str(col[1]), repr(col))
    for stmt in DOWNGRADE:
        await sql(stmt)
    gone = (await sql("SELECT 1 FROM information_schema.columns WHERE table_name='fantasy_squads' AND column_name='catchup_points'")).first()
    still = (await sql("SELECT 1 FROM information_schema.columns WHERE table_name='fantasy_squads' AND column_name='joined_round'")).first()
    check("the downgrade drops only the added column", gone is None and still is not None)

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    async def _run() -> int:
        try:
            return await main()
        finally:
            await engine.dispose()
    sys.exit(asyncio.run(_run()))
