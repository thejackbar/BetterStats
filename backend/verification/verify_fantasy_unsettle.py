"""Verification for unsettling a Fantasy round, live points on a long round, and the
Better HQ competitions list, against a real Postgres.

Reported: (1) a round settled by accident could not be taken back; (2) points only
showed once a round was settled, so a two-week round showed nothing until the end;
(3) Better HQ had no way to see every club's competition.

Runs the SHIPPED `services/fantasy_engine`, `routers/fantasy` route bodies and the
`routers/public_fantasy.live` body over the `v_effective_*` views pulled out of the
migrations. Only the session/club lookups in `live` are stubbed.

CONTROL (`--control`): the route module and `live` at git HEAD are loaded. They must
fail on exactly the reported behaviour: no unsettle route, and `live` adding a
round's stored provisional points to a total that already holds them. Read through
presence-safe accessors so a different failure shows as a different message.

Run:  DATABASE_URL=postgresql+asyncpg://root@/fantasy_test?host=/var/run/postgresql \
      python verification/verify_fantasy_unsettle.py [--control]
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import subprocess
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from fastapi import HTTPException
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.models.db import (
    Base, Organisation, Season, Grade, Game, Player, BattingInnings, GameAppearance,
    FantasySeason, FantasyRound, FantasyLeague, FantasyManager, FantasySquad,
    FantasySquadPlayer, FantasyPoolPlayer,
)
from app.services import fantasy_engine
from app.routers import fantasy as fantasy_router
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


TODAY = date.today()
ORG, ORG_B, ORG_NONE, ORG_ARCH = (uuid.uuid4() for _ in range(4))
A, B = uuid.uuid4(), uuid.uuid4()           # players
FS_ID = uuid.uuid4()
R1, R2 = uuid.uuid4(), uuid.uuid4()          # R1 ended, R2 a two-week round still running
SQ_X, SQ_Y = uuid.uuid4(), uuid.uuid4()
MGR_X, MGR_Y = uuid.uuid4(), uuid.uuid4()


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        for (tbl,) in (await conn.execute(text(
                "SELECT table_name FROM information_schema.columns WHERE table_schema='public' "
                "AND column_name='id' AND table_name LIKE 'fantasy\\_%' AND data_type='uuid'"))).all():
            await conn.execute(text(f'ALTER TABLE "{tbl}" ALTER COLUMN id SET DEFAULT gen_random_uuid()'))
        for tbl, col in (await conn.execute(text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND data_type = 'json'"))).all():
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb USING "{col}"::text::jsonb'))
        from app.services.competition_ddl import STATEMENTS as _COMP_DDL
        for _stmt in _COMP_DDL:
            await conn.execute(text(_stmt))
        stmts = view_statements()
        for _ in range(2):
            for name, sql in stmts:
                await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
                await conn.execute(text(sql.replace("OR REPLACE ", "")))


async def seed() -> None:
    year = TODAY.year
    async with Session() as s:
        s.add_all([
            Organisation(id=ORG, name="Alpha CC", slug="alpha", is_active=True),
            Organisation(id=ORG_B, name="Bravo CC", slug="bravo", is_active=True),
            Organisation(id=ORG_NONE, name="Nothing CC", slug="nothing", is_active=True),
            Organisation(id=ORG_ARCH, name="Archived CC", slug="arch", is_active=True,
                         archived_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc)),
        ])
        await s.flush()
        sx = Season(id=uuid.uuid4(), organisation_id=ORG, name="Summer", year=year, grassroots_id="s1")
        s.add(sx)
        await s.flush()
        gr = Grade(id=uuid.uuid4(), season_id=sx.id, name="Firsts", grassroots_id="g1")
        s.add(gr)
        s.add_all([
            Player(id=A, name="Ann Ace", organisation_id=ORG, grassroots_id="pa"),
            Player(id=B, name="Bo Bat", organisation_id=ORG, grassroots_id="pb"),
        ])
        await s.flush()
        # R1 game (ended round): A 50, B 10. R2 game (running round): A 30.
        for gdate, runs in ((TODAY - timedelta(days=18), {A: 50, B: 10}), (TODAY - timedelta(days=3), {A: 30})):
            gid = uuid.uuid4()
            s.add(Game(id=gid, grade_id=gr.id, played_at=gdate, home_team="Alpha", away_team="X",
                       home_org_id=ORG, status="COMPLETED"))
            await s.flush()
            for pid, r in runs.items():
                s.add(GameAppearance(game_id=gid, player_id=pid, team_name="Alpha"))
                s.add(BattingInnings(game_id=gid, player_id=pid, innings_number=1, runs=r, balls=r,
                                     fours=0, sixes=0, dismissal_type="bowled", not_out=False))
        fs = FantasySeason(id=FS_ID, organisation_id=ORG, season_year=year, name=f"{year} Fantasy",
                           status="open", scoring={}, rules={})
        s.add(fs)
        await s.flush()
        s.add_all([
            FantasyRound(id=R1, fantasy_season_id=FS_ID, organisation_id=ORG, round_number=1, name="Round 1",
                         lock_at=None, start_date=TODAY - timedelta(days=20), end_date=TODAY - timedelta(days=14)),
            FantasyRound(id=R2, fantasy_season_id=FS_ID, organisation_id=ORG, round_number=2, name="Round 2",
                         lock_at=None, start_date=TODAY - timedelta(days=5), end_date=TODAY + timedelta(days=9)),
        ])
        s.add_all([FantasyPoolPlayer(fantasy_season_id=FS_ID, organisation_id=ORG, player_id=p, role="batter",
                                     base_price=5, current_price=5) for p in (A, B)])
        s.add_all([FantasyManager(id=MGR_X, organisation_id=ORG, display_name="Xavier"),
                   FantasyManager(id=MGR_Y, organisation_id=ORG, display_name="Yara")])
        await s.flush()
        lg = FantasyLeague(id=uuid.uuid4(), fantasy_season_id=FS_ID, organisation_id=ORG,
                           kind="global_salary_cap", name="Club ladder")
        s.add(lg)
        await s.flush()
        s.add_all([
            FantasySquad(id=SQ_X, fantasy_season_id=FS_ID, league_id=lg.id, manager_id=MGR_X, organisation_id=ORG,
                         team_name="X Team", free_transfers=1),
            FantasySquad(id=SQ_Y, fantasy_season_id=FS_ID, league_id=lg.id, manager_id=MGR_Y, organisation_id=ORG,
                         team_name="Y Team", free_transfers=1),
        ])
        await s.flush()
        s.add_all([
            FantasySquadPlayer(squad_id=SQ_X, player_id=A, role="batter", is_captain=True),
            FantasySquadPlayer(squad_id=SQ_X, player_id=B, role="batter", is_vice_captain=True),
            FantasySquadPlayer(squad_id=SQ_Y, player_id=B, role="batter", is_captain=True),
        ])
        await s.commit()
        # X played a chip and made 2 transfers (4 point hit) on R1 before it locked.
        await s.execute(text("""INSERT INTO fantasy_squad_round_scores
            (squad_id, round_id, chip_used, transfer_hit, transfers_made, lineup)
            VALUES (:sid, :rid, 'bench_boost', 4, 2, '[]')"""), {"sid": SQ_X, "rid": R1})
        await s.commit()


async def one(sql: str, **p):
    async with Session() as s:
        return (await s.execute(text(sql), p)).first()


async def state() -> dict:
    async with Session() as s:
        g = lambda q, **p: s  # noqa: E731
        r1 = (await s.execute(text("SELECT status, scored_at FROM fantasy_rounds WHERE id=:i"), {"i": R1})).first()
        n_player = (await s.execute(text("SELECT COUNT(*) FROM fantasy_player_round_scores WHERE round_id=:i"), {"i": R1})).scalar()
        sq = {str(r[0]): (float(r[1]), r[2]) for r in (await s.execute(text(
            "SELECT id, total_points, free_transfers FROM fantasy_squads"))).all()}
        srs = {str(r[0]): r[1:] for r in (await s.execute(text(
            "SELECT squad_id, points, raw_points, chip_used, transfer_hit, transfers_made FROM fantasy_squad_round_scores WHERE round_id=:i"),
            {"i": R1})).all()}
        pool = {str(r[0]): (float(r[1]), float(r[2])) for r in (await s.execute(text(
            "SELECT player_id, total_points, last_round_points FROM fantasy_pool_players"))).all()}
        rscores = {str(r[0]): float(r[1]) for r in (await s.execute(text(
            "SELECT player_id, total_points FROM fantasy_player_round_scores WHERE round_id=:i"), {"i": R1})).all()}
        return {"rscores": rscores, "r1": r1, "n_player": n_player, "sq": sq, "srs": srs, "pool": pool}


async def club() -> Organisation:
    async with Session() as s:
        return await s.get(Organisation, ORG)


async def call(fn, **kw):
    async with Session() as s:
        return await fn(db=s, **kw)


async def main_checks() -> None:
    org = await club()
    sid, xid, yid = str(SQ_X), str(SQ_X), str(SQ_Y)

    print("1. Settle round 1")
    async with Session() as s:
        await fantasy_router.settle_round(str(R1), club=org, db=s, _=None)
    st = await state()
    check("round 1 scored", st["r1"][0] == "scored" and st["r1"][1] is not None, repr(st["r1"]))
    check("player scores written", st["n_player"] == 2, str(st["n_player"]))
    settled_x, settled_y = st["sq"][str(SQ_X)], st["sq"][str(SQ_Y)]
    check("squads have points", settled_x[0] != 0 and settled_y[0] > 0, repr((settled_x, settled_y)))
    check("X's total carries the 4 point transfer hit", abs(st["srs"][str(SQ_X)][0] - (st["srs"][str(SQ_X)][1] - 4)) < 1e-6, repr(st["srs"][str(SQ_X)]))
    check("settlement banked a free transfer (1 -> 2)", settled_x[1] == 2 and settled_y[1] == 2, repr((settled_x, settled_y)))
    pool_settled, srs_settled, rscores_settled = st["pool"], st["srs"], st["rscores"]
    check("pool totals set", pool_settled[str(A)][0] > 0, repr(pool_settled))

    print("2. Unsettle round 1")
    async with Session() as s:
        res = await fantasy_router.unsettle_round(str(R1), club=org, db=s, _=None)
    check("route reports the cleared player scores", res.get("players_cleared") == 2, repr(res))
    st = await state()
    check("round is unsettled and unscored", st["r1"][0] == "unsettled" and st["r1"][1] is None, repr(st["r1"]))
    check("player scores gone", st["n_player"] == 0, str(st["n_player"]))
    check("squad totals back to 0", st["sq"][str(SQ_X)][0] == 0 and st["sq"][str(SQ_Y)][0] == 0, repr(st["sq"]))
    check("pool totals and last-round points back to 0", all(v == (0.0, 0.0) for v in st["pool"].values()), repr(st["pool"]))
    check("free transfer taken back (2 -> 1)", st["sq"][str(SQ_X)][1] == 1 and st["sq"][str(SQ_Y)][1] == 1, repr(st["sq"]))
    x_row = st["srs"].get(str(SQ_X))
    check("X's chip and transfers are kept, scoring cleared",
          x_row is not None and x_row[0] == 0 and x_row[1] == 0 and x_row[2] == "bench_boost" and x_row[3] == 4 and x_row[4] == 2, repr(x_row))
    check("Y's settlement-only row is removed", str(SQ_Y) not in st["srs"], repr(st["srs"]))
    try:
        async with Session() as s:
            await fantasy_router.unsettle_round(str(R1), club=org, db=s, _=None)
        check("unsettling twice is refused", False, "no error")
    except HTTPException as e:
        check("unsettling twice is refused", e.status_code == 409, str(e.status_code))

    print("3. The auto settlers leave it alone")
    async with Session() as s:
        r = await fantasy_router.settle_due(str(FS_ID), club=org, db=s, _=None)
    check("settle-due settles nothing", r.get("rounds_settled") == 0, repr(r))
    check("round 1 still unsettled", (await state())["r1"][0] == "unsettled")

    print("4. Settle it again, by hand")
    async with Session() as s:
        await fantasy_router.settle_round(str(R1), club=org, db=s, _=None)
    st2 = await state()
    check("scored again", st2["r1"][0] == "scored")
    # Season totals now also hold round 2's running points (step 3 refreshed it),
    # so compare what round 1 itself produced.
    check("round 1 scores match the first settle", st2["srs"] == srs_settled and st2["rscores"] == rscores_settled,
          repr((st2["srs"], srs_settled, st2["rscores"], rscores_settled)))
    check("one free transfer banked, not two", st2["sq"][str(SQ_X)][1] == 2, repr(st2["sq"]))
    check("pool last-round points match the first settle", {k: v[1] for k, v in st2["pool"].items()} == {k: v[1] for k, v in pool_settled.items()}, repr(st2["pool"]))

    print("5. Points show while a two-week round is still running")
    async with Session() as s:
        r = await fantasy_router.settle_due(str(FS_ID), club=org, db=s, _=None)
    check("settle-due refreshed the running round", r.get("rounds_refreshed") == 1 and r.get("rounds_settled") == 0, repr(r))
    async with Session() as s:
        r2 = (await s.execute(text("SELECT status FROM fantasy_rounds WHERE id=:i"), {"i": R2})).scalar()
        n2 = (await s.execute(text("SELECT COUNT(*) FROM fantasy_player_round_scores WHERE round_id=:i"), {"i": R2})).scalar()
        x_tot, x_ft = (await s.execute(text("SELECT total_points, free_transfers FROM fantasy_squads WHERE id=:i"), {"i": SQ_X})).first()
        x2 = (await s.execute(text("SELECT points FROM fantasy_squad_round_scores WHERE squad_id=:i AND round_id=:r"), {"i": SQ_X, "r": R2})).scalar()
        a_tot = (await s.execute(text("SELECT total_points FROM fantasy_pool_players WHERE player_id=:i"), {"i": A})).scalar()
    check("running round stays unscored", r2 == "upcoming", str(r2))
    check("its player scores are written", n2 == 1, str(n2))
    check("the ladder total holds round 1 plus the running round", x2 and abs(float(x_tot) - (settled_x[0] + float(x2))) < 1e-6, repr((x_tot, settled_x, x2)))
    check("refresh grants no free transfer", x_ft == 2, str(x_ft))
    check("the player's season total includes the running round", float(a_tot) > pool_settled[str(A)][0], repr((a_tot, pool_settled)))

    print("6. Member live view does not count the running round twice")
    # Y sits one point above X's true live total; X is 2nd, not 1st.
    async with Session() as s:
        x_total = float((await s.execute(text("SELECT total_points FROM fantasy_squads WHERE id=:i"), {"i": SQ_X})).scalar())
        await s.execute(text("UPDATE fantasy_squads SET total_points = :t WHERE id=:i"), {"t": x_total + 1, "i": SQ_Y})
        await s.execute(text("UPDATE fantasy_rounds SET lock_at = NOW() - interval '3 days' WHERE id=:i"), {"i": R2})
        await s.commit()
    rank = await live_rank()
    check("provisional rank is 2nd (control: counted twice => 1st)", rank == 2, repr(rank))

    print("7. Better HQ competitions list")
    async with Session() as s:
        s.add(FantasySeason(id=uuid.uuid4(), organisation_id=ORG_ARCH, season_year=TODAY.year, name="Arch", status="open", scoring={}, rules={}))
        await s.commit()
    res = await call(fantasy_router.super_competitions, _=None)
    comps = res["competitions"]
    names = [c["club_name"] for c in comps]
    check("a club with a season is listed, one without is not, an archived one is not", names == ["Alpha CC"], repr(names))
    c = comps[0]
    check("it reports rounds and managers", (c["rounds_total"], c["rounds_scored"], c["next_round"], c["managers"]) == (2, 1, 2, 2), repr(c))
    check("top of the ladder, ranked", [t["team_name"] for t in c["top"]] == ["Y Team", "X Team"] and c["top"][0]["rank"] == 1, repr(c["top"]))

    print("8. A running round settled by mistake goes back to running, with its points")
    org = await club()
    async with Session() as s:
        await fantasy_router.settle_round(str(R2), club=org, db=s, _=None)
    check("settled early", (await one("SELECT status FROM fantasy_rounds WHERE id=:i", i=R2))[0] == "scored")
    async with Session() as s:
        await fantasy_router.unsettle_round(str(R2), club=org, db=s, _=None)
    row = await one("SELECT status, scored_at FROM fantasy_rounds WHERE id=:i", i=R2)
    check("back to upcoming (still inside its window), not stuck unsettled", row[0] == "upcoming" and row[1] is None, repr(row))
    n = (await one("SELECT COUNT(*) FROM fantasy_player_round_scores WHERE round_id=:i", i=R2))[0]
    check("its points so far are still shown", n == 1, str(n))
    r = await call(fantasy_router.settle_due, club=org, _=None, season_id=str(FS_ID))
    check("and the nightly settler will settle it when it ends", r.get("rounds_refreshed") == 1, repr(r))


async def live_rank(module=None) -> object:
    """Call `live` with only the session/club lookups stubbed."""
    pub = module or public_fantasy
    async with Session() as s:
        org = await s.get(Organisation, ORG)
        mgr = await s.get(FantasyManager, MGR_X)
        season = await s.get(FantasySeason, FS_ID)

        async def _club(db, token): return org
        async def _mgr(db, request, club): return mgr
        async def _season(db, club): return season
        saved = (pub._club_for_token, pub._manager_for_session, pub._current_season)
        pub._club_for_token, pub._manager_for_session, pub._current_season = _club, _mgr, _season
        try:
            out = await pub.live("tok", None, s)
        finally:
            pub._club_for_token, pub._manager_for_session, pub._current_season = saved
        return out.get("provisional_rank", f"<no provisional_rank; live={out.get('live')}>")


async def run_control() -> int:
    """Route module and `live` at git HEAD."""
    def load(rel: str, name: str):
        src = subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=REPO, text=True)
        tmp = Path(__file__).resolve().parent / f"_{name}.py"
        tmp.write_text(src)
        spec = importlib.util.spec_from_file_location(name, tmp)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod, tmp
    tmps = []
    try:
        old_router, t1 = load("backend/app/routers/fantasy.py", "fantasy_router_control"); tmps.append(t1)
        old_pub, t2 = load("backend/app/routers/public_fantasy.py", "public_fantasy_control"); tmps.append(t2)
        check("HEAD has an unsettle route", getattr(old_router, "unsettle_round", None) is not None,
              "no unsettle_round in the route module")
        # Same seed, round 2 refreshed with the new engine, then the old `live`.
        org = await club()
        async with Session() as s:
            await fantasy_router.settle_round(str(R1), club=org, db=s, _=None)
        async with Session() as s:
            fs = await s.get(FantasySeason, FS_ID)
            rnd = await s.get(FantasyRound, R2)
            await fantasy_engine.refresh_live_round(s, fs, rnd)
            await s.commit()
        async with Session() as s:
            x_total = float((await s.execute(text("SELECT total_points FROM fantasy_squads WHERE id=:i"), {"i": SQ_X})).scalar())
            await s.execute(text("UPDATE fantasy_squads SET total_points = :t WHERE id=:i"), {"t": x_total + 1, "i": SQ_Y})
            await s.execute(text("UPDATE fantasy_rounds SET lock_at = NOW() - interval '3 days' WHERE id=:i"), {"i": R2})
            await s.commit()
        rank = await live_rank(old_pub)
        check("HEAD's live view ranks X 2nd", rank == 2, f"ranked {rank!r}, counting the running round twice")
    finally:
        for t in tmps:
            t.unlink(missing_ok=True)
    return FAIL


async def main() -> int:
    await build_schema()
    await seed()
    if "--control" in sys.argv:
        return await run_control()
    await main_checks()
    return FAIL


if __name__ == "__main__":
    failed = asyncio.run(main())
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if failed else 0)
