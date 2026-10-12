"""Verification for Fantasy player price movement, against a real Postgres.

Reported: player prices never changed after a round was scored (the design said they
should move on performances), there were no arrows to show a rise or fall, and a
sale returned the purchase price plus half the rise, so the bank did not follow the
player's price.

Runs the SHIPPED `services/fantasy_engine` settle/unsettle, `services/fantasy_pricing`,
the `routers/fantasy` pool PATCH body and the `routers/public_fantasy` `me` and
`transfer` bodies over the `v_effective_*` views pulled out of the migrations. Only
the club and session lookups in the public routes are stubbed.

CONTROL: run the same script against the previous commit's backend (copy this file into
the worktree's verification/ folder first):

    git worktree add /tmp/ctl <commit before this change>
    BACKEND_DIR=/tmp/ctl/backend DATABASE_URL=... python verification/verify_fantasy_pricing.py

It must fail on exactly the reported behaviour (prices do not move, a sale returns
half the rise) and on nothing else. New keys are read through presence-safe
accessors so an absent module shows as a failed check, not a crash.

Run:  DATABASE_URL=postgresql+asyncpg://root@/fantasy_test?host=/var/run/postgresql \
      python verification/verify_fantasy_pricing.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

BACKEND = Path(os.environ.get("BACKEND_DIR") or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(BACKEND))
sys.path.insert(1, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.models.db import (
    Base, Organisation, Season, Grade, Game, Player, BattingInnings, GameAppearance,
    FantasySeason, FantasyRound, FantasyLeague, FantasyManager, FantasySquad,
    FantasySquadPlayer, FantasyPoolPlayer, PlayerSeasonStats,
)
from app.services import fantasy_engine
from app.routers import fantasy as fantasy_router
from app.routers import public_fantasy

try:
    from app.services import fantasy_pricing
except ImportError:
    fantasy_pricing = None

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
        print(f"  FAIL {label}{('  - ' + detail) if detail else ''}")


def near(a, b, eps=1e-6) -> bool:
    return a is not None and b is not None and abs(float(a) - float(b)) < eps


TODAY = date.today()
ORG = uuid.uuid4()
A, B, C, D, E = (uuid.uuid4() for _ in range(5))   # players
FS_ID = uuid.uuid4()
R1, R2 = uuid.uuid4(), uuid.uuid4()
SQ_X, SQ_Y = uuid.uuid4(), uuid.uuid4()
MGR_X, MGR_Y = uuid.uuid4(), uuid.uuid4()
BASE = {A: 5.0, B: 14.0, C: 7.0, D: 8.0, E: 10.0}


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
        s.add(Organisation(id=ORG, name="Alpha CC", slug="alpha", is_active=True))
        await s.flush()
        sx = Season(id=uuid.uuid4(), organisation_id=ORG, name="Summer", year=year, grassroots_id="s1")
        s.add(sx)
        await s.flush()
        gr = Grade(id=uuid.uuid4(), season_id=sx.id, name="Firsts", grassroots_id="g1")
        s.add(gr)
        s.add_all([Player(id=p, name=n, organisation_id=ORG, grassroots_id=f"p{i}")
                   for i, (p, n) in enumerate(((A, "Ann Ace"), (B, "Bo Bat"), (C, "Cy Cap"), (D, "Di Idle"), (E, "Ed Extra")))])
        await s.flush()
        # Round 1 game: A 50, B 10, C 30. Round 2 game: A 20 only (B does not play).
        for gdate, runs in ((TODAY - timedelta(days=18), {A: 50, B: 10, C: 30}), (TODAY - timedelta(days=9), {A: 20})):
            gid = uuid.uuid4()
            s.add(Game(id=gid, grade_id=gr.id, played_at=gdate, home_team="Alpha", away_team="X",
                       home_org_id=ORG, status="COMPLETED"))
            await s.flush()
            for pid, r in runs.items():
                s.add(GameAppearance(game_id=gid, player_id=pid, team_name="Alpha"))
                s.add(BattingInnings(game_id=gid, player_id=pid, innings_number=1, runs=r, balls=r,
                                     fours=0, sixes=0, dismissal_type="bowled", not_out=False))
        s.add(FantasySeason(id=FS_ID, organisation_id=ORG, season_year=year, name=f"{year} Fantasy",
                            status="open", scoring={}, rules={}))
        await s.flush()
        s.add_all([
            FantasyRound(id=R1, fantasy_season_id=FS_ID, organisation_id=ORG, round_number=1, name="Round 1",
                         lock_at=None, start_date=TODAY - timedelta(days=20), end_date=TODAY - timedelta(days=14)),
            FantasyRound(id=R2, fantasy_season_id=FS_ID, organisation_id=ORG, round_number=2, name="Round 2",
                         lock_at=None, start_date=TODAY - timedelta(days=12), end_date=TODAY - timedelta(days=6)),
        ])
        s.add_all([FantasyPoolPlayer(fantasy_season_id=FS_ID, organisation_id=ORG, player_id=p, role="batter",
                                     base_price=BASE[p], current_price=BASE[p]) for p in BASE])
        s.add_all([FantasyManager(id=MGR_X, organisation_id=ORG, display_name="Xavier"),
                   FantasyManager(id=MGR_Y, organisation_id=ORG, display_name="Yara")])
        await s.flush()
        lg = FantasyLeague(id=uuid.uuid4(), fantasy_season_id=FS_ID, organisation_id=ORG,
                           kind="global_salary_cap", name="Club ladder")
        s.add(lg)
        await s.flush()
        # X owns A (captain) and B and has 100 - 5 - 14 = 81 left. Y owns A and has 95 left.
        s.add_all([
            FantasySquad(id=SQ_X, fantasy_season_id=FS_ID, league_id=lg.id, manager_id=MGR_X, organisation_id=ORG,
                         team_name="X Team", free_transfers=1, budget_remaining=81.0),
            FantasySquad(id=SQ_Y, fantasy_season_id=FS_ID, league_id=lg.id, manager_id=MGR_Y, organisation_id=ORG,
                         team_name="Y Team", free_transfers=1, budget_remaining=95.0),
        ])
        await s.flush()
        s.add_all([
            FantasySquadPlayer(squad_id=SQ_X, player_id=A, role="batter", is_captain=True, purchase_price=5.0),
            FantasySquadPlayer(squad_id=SQ_X, player_id=B, role="batter", purchase_price=14.0),
            FantasySquadPlayer(squad_id=SQ_Y, player_id=A, role="batter", purchase_price=5.0),
        ])
        await s.commit()


async def prices() -> dict:
    async with Session() as s:
        return {r[0]: (float(r[1]), float(r[2])) for r in (await s.execute(text(
            "SELECT player_id, current_price, price_change FROM fantasy_pool_players"))).all()}


async def round_points(rid) -> dict:
    async with Session() as s:
        return {r[0]: float(r[1]) for r in (await s.execute(text(
            "SELECT player_id, total_points FROM fantasy_player_round_scores WHERE round_id = :r"), {"r": rid})).all()}


async def settle(rid) -> None:
    async with Session() as s:
        fs = await s.get(FantasySeason, FS_ID)
        rnd = await s.get(FantasyRound, rid)
        await fantasy_engine.settle_round(s, fs, rnd)
        await s.commit()


async def unsettle(rid) -> None:
    async with Session() as s:
        fs = await s.get(FantasySeason, FS_ID)
        rnd = await s.get(FantasyRound, rid)
        await fantasy_engine.unsettle_round(s, fs, rnd)
        await s.commit()


async def has_column() -> bool:
    async with Session() as s:
        return bool((await s.execute(text(
            "SELECT 1 FROM information_schema.columns WHERE table_name='fantasy_pool_players' "
            "AND column_name='price_locked'"))).scalar())


def stub_public(manager_id) -> None:
    """The public routes read the club and manager from a link token and a cookie."""
    async def club_for_token(db, token):
        return await db.get(Organisation, ORG)

    async def manager_for_session(db, request, club):
        return await db.get(FantasyManager, manager_id)
    public_fantasy._club_for_token = club_for_token
    public_fantasy._manager_for_session = manager_for_session


async def main_checks() -> None:
    org_rows = None
    print("0. The movement rule on its own")
    if fantasy_pricing is None:
        check("services/fantasy_pricing exists", False, "no price movement module")
    else:
        up, mv = fantasy_pricing.step_price(5.0, 5.0, [90.0])
        check("a big score moves the price up by at most 0.5", near(up, 5.5) and near(mv, 0.5), f"{up} {mv}")
        dn, mv = fantasy_pricing.step_price(14.0, 14.0, [0.0])
        check("a blank moves a star down by at most 0.5", near(dn, 13.5) and near(mv, -0.5), f"{dn} {mv}")
        check("a price never goes below the floor",
              near(fantasy_pricing.step_price(4.0, 4.0, [0.0, 0.0])[0], 4.0))
        check("a player who did not play does not move", fantasy_pricing.replay(10.0, [None, None]) == (10.0, 0.0))
        check("one round cannot move a price further than the cap",
              all(abs(fantasy_pricing.step_price(p, 9.0, [pts])[1]) <= 0.5 + 1e-9
                  for p in (4.0, 9.0, 15.0) for pts in (0.0, 30.0, 500.0)))
        check("replay is deterministic", fantasy_pricing.replay(8.0, [40, None, 10]) == fantasy_pricing.replay(8.0, [40, None, 10]))

    print("1. Nothing moves before a round is scored")
    p0 = await prices()
    check("every player is on their starting price", all(near(p0[p][0], BASE[p]) and near(p0[p][1], 0) for p in BASE), repr(p0))

    print("2. Settling round 1 moves prices on performances")
    await settle(R1)
    p1 = await prices()
    pts1 = await round_points(R1)
    check("the player who scored well rose by the 0.5 cap", near(p1[A][0], 5.5) and near(p1[A][1], 0.5), repr(p1[A]))
    check("the star who scored poorly fell by the 0.5 cap", near(p1[B][0], 13.5) and near(p1[B][1], -0.5), repr(p1[B]))
    check("player scores exist for those who played", set(pts1) >= {A, B, C}, repr(pts1))
    check("a player who did not play has not moved", near(p1[D][0], BASE[D]) and near(p1[D][1], 0), repr(p1[D]))

    print("3. Settling the same round again does not move it twice")
    await settle(R1)
    p1b = await prices()
    check("prices are the same after a second settle", p1b == p1, f"{p1} -> {p1b}")

    print("4. The bank follows the price (sale at the current price)")
    # Put the prices in the shape the new rule produces so the sale checks run the same
    # against the previous commit, which never moved them.
    async with Session() as s:
        await s.execute(text("UPDATE fantasy_pool_players SET current_price = 5.5 WHERE player_id = :p"), {"p": A})
        await s.execute(text("UPDATE fantasy_pool_players SET current_price = 13.5 WHERE player_id = :p"), {"p": B})
        await s.commit()
    stub_public(MGR_Y)
    async with Session() as s:
        me = await public_fantasy.me("tok", SimpleNamespace(), db=s)
    sq = me["squad"]
    pa = next(p for p in sq["players"] if p["player_id"] == str(A))
    check("the squad shows the price now", near(pa.get("price"), 5.5), repr(pa))
    check("the squad shows last round's move", near(pa.get("price_change"), 0.5), repr(pa))
    check("the squad shows what a sale returns", near(pa.get("sell_value"), 5.5), repr(pa))
    check("team value counts the rise", near(sq["value"], 100.5), repr(sq.get("value")))

    async def do_transfer(mgr, out_p, in_p):
        stub_public(mgr)
        async with Session() as s:
            return await public_fantasy.transfer("tok", public_fantasy.TransferBody(out_player_id=str(out_p), in_player_id=str(in_p)),
                                                 SimpleNamespace(), db=s)
    r = await do_transfer(MGR_Y, A, D)
    check("selling a player who rose banks the whole rise (95 + 5.5 - 8 = 92.5)", near(r["budget_remaining"], 92.5), repr(r))
    async with Session() as s:
        await s.execute(text("UPDATE fantasy_squad_players SET is_captain = false WHERE squad_id = :s"), {"s": SQ_X})
        await s.execute(text("UPDATE fantasy_squad_players SET is_captain = true WHERE squad_id = :s AND player_id = :p"), {"s": SQ_X, "p": A})
        await s.commit()
    r = await do_transfer(MGR_X, B, E)
    check("selling a player who fell takes the fall (81 + 13.5 - 10 = 84.5)", near(r["budget_remaining"], 84.5), repr(r))

    print("5. Round 2: a player who sat out does not move; the rest compound")
    await settle(R2)
    p2 = await prices()
    pts2 = await round_points(R2)
    check("round 2 scored only A", set(pts2) == {A}, repr(pts2))
    if fantasy_pricing is not None:
        want_a = fantasy_pricing.replay(BASE[A], [pts1[A], pts2[A]])
        check("A's price is the replay of both rounds", near(p2[A][0], want_a[0]) and near(p2[A][1], want_a[1]), f"{p2[A]} vs {want_a}")
    check("B sat out round 2, so no move this round", near(p2[B][0], 13.5) and near(p2[B][1], 0), repr(p2[B]))
    check("A's round 2 move is the gap between the two prices", near(p2[A][1], p2[A][0] - p1[A][0]), f"{p1[A]} -> {p2[A]}")

    print("6. Unsettling takes the movement back")
    await unsettle(R2)
    pu = await prices()
    check("round 2 off: A is back to round 1's price and move", near(pu[A][0], 5.5) and near(pu[A][1], 0.5), repr(pu[A]))
    await unsettle(R1)
    pu = await prices()
    check("round 1 off too: everyone is on their starting price", all(near(pu[p][0], BASE[p]) and near(pu[p][1], 0) for p in BASE), repr(pu))
    await settle(R1)
    await settle(R2)
    p3 = await prices()
    check("settling again gives the same prices as the first time", p3 == p2, f"{p2} -> {p3}")

    print("7. A price an admin typed in stays put")
    org = SimpleNamespace(id=ORG)
    if not await has_column():
        check("fantasy_pool_players.price_locked exists", False, "column absent")
    else:
        async with Session() as s:
            pool_id = (await s.execute(text("SELECT id FROM fantasy_pool_players WHERE player_id = :p"), {"p": C})).scalar()
            await fantasy_router.patch_pool_player(str(pool_id), fantasy_router.PoolPatch(current_price=9.0), club=org, db=s, _=None)
        await settle(R1)   # a re-settle replays every scored round
        pc = (await prices())[C]
        check("the hand-set price is untouched by a settle", near(pc[0], 9.0) and near(pc[1], 0), repr(pc))
        async with Session() as s:
            await fantasy_router.patch_pool_player(str(pool_id), fantasy_router.PoolPatch(price_locked=False), club=org, db=s, _=None)
        pc = (await prices())[C]
        check("handing it back to auto replays the rounds onto the starting price", pc[0] != 9.0 and abs(pc[0] - BASE[C]) <= 1.0 + 1e-9, repr(pc))

    print("8. A season scored before price movement existed catches up")
    async with Session() as s:
        await s.execute(text("UPDATE fantasy_pool_players SET current_price = base_price, price_change = 0"))
        await s.commit()
    if fantasy_pricing is None:
        check("recompute_prices exists", False, "no price movement module")
    else:
        async with Session() as s:
            fs = await s.get(FantasySeason, FS_ID)
            dry = await fantasy_pricing.recompute_prices(s, fs, apply=False)
            await s.rollback()
        check("a dry run reports the moves", dry["changed"] > 0, repr(dry["changed"]))
        check("a dry run writes nothing", all(near(v[0], BASE[p]) for p, v in (await prices()).items()))
        async with Session() as s:
            fs = await s.get(FantasySeason, FS_ID)
            await fantasy_pricing.recompute_prices(s, fs)
            await s.commit()
        p4 = await prices()
        check("catch-up gives the same prices as settling did", p4 == p3, f"{p3} -> {p4}")
        async with Session() as s:
            fs = await s.get(FantasySeason, FS_ID)
            again = await fantasy_pricing.recompute_prices(s, fs)
            await s.commit()
        check("running it again changes nothing", again["changed"] == 0, repr(again["changed"]))

    print("9. The migration locks hand-set prices once, and only once")
    if not await has_column():
        check("migration DDL present", False, "no fantasy_price_ddl")
    else:
        try:
            from app.services.fantasy_price_ddl import STATEMENTS
        except ImportError:
            STATEMENTS = None
        check("fantasy_price_ddl has the statements", bool(STATEMENTS))
        if STATEMENTS:
            async with engine.begin() as conn:
                await conn.execute(text("ALTER TABLE fantasy_pool_players DROP COLUMN price_locked"))
                await conn.execute(text("UPDATE fantasy_pool_players SET current_price = base_price"))
                await conn.execute(text("UPDATE fantasy_pool_players SET current_price = 6.0 WHERE player_id = :p"), {"p": E})
                for st in STATEMENTS:
                    await conn.execute(text(st))
            async with Session() as s:
                locked = {r[0] for r in (await s.execute(text(
                    "SELECT player_id FROM fantasy_pool_players WHERE price_locked"))).all()}
            check("only the player whose price differed is locked", locked == {E}, repr(locked))
            async with engine.begin() as conn:
                await conn.execute(text("UPDATE fantasy_pool_players SET current_price = base_price + 0.5 WHERE player_id = :p"), {"p": A})
                for st in STATEMENTS:
                    await conn.execute(text(st))
            async with Session() as s:
                locked = {r[0] for r in (await s.execute(text(
                    "SELECT player_id FROM fantasy_pool_players WHERE price_locked"))).all()}
            check("a later boot does not lock a price the movement set", locked == {E}, repr(locked))

    print("10. Recalculating prices replays the scored rounds onto the new baseline")
    if fantasy_pricing is None or not await has_column():
        check("recalculate needs the pricing module", False, "absent")
    else:
        async with Session() as s:
            sid = (await s.execute(text("SELECT id FROM seasons LIMIT 1"))).scalar()
            s.add(PlayerSeasonStats(player_id=A, season_id=sid, matches=5, batting_innings=5, runs=200, fours=10,
                                    sixes=2, fifties=1, hundreds=0, wickets=0))
            await s.execute(text("UPDATE fantasy_pool_players SET current_price = base_price"))
            await s.execute(text("UPDATE fantasy_pool_players SET price_locked = true, current_price = 99 WHERE player_id = :p"), {"p": A})
            await s.commit()
        async with Session() as s:
            fs = await s.get(FantasySeason, FS_ID)
            fs.status = "active"
            await fantasy_engine.build_pool(s, fs, reset=False)
            await s.commit()
        async with Session() as s:
            row = (await s.execute(text("SELECT base_price, current_price, price_locked FROM fantasy_pool_players WHERE player_id = :p"), {"p": A})).first()
        check("a rebuild without reset leaves a live price, its base and its lock alone",
              near(row[0], BASE[A]) and near(row[1], 99.0) and row[2] is True, repr(tuple(row)))
        async with Session() as s:
            fs = await s.get(FantasySeason, FS_ID)
            await fantasy_engine.build_pool(s, fs, reset=True)
            await s.commit()
        async with Session() as s:
            row = (await s.execute(text("SELECT base_price, current_price, price_locked, price_change FROM fantasy_pool_players WHERE player_id = :p"), {"p": A})).first()
        want = fantasy_pricing.replay(float(row[0]), [pts1[A], pts2[A]])
        check("a reset takes a new baseline", not near(row[0], BASE[A]) and float(row[0]) > 5.0, repr(tuple(row)))
        check("a reset clears the lock", row[2] is False, repr(tuple(row)))
        check("a reset replays the scored rounds onto the new baseline", near(row[1], want[0]) and near(row[3], want[1]), f"{tuple(row)} vs {want}")


async def main() -> int:
    await build_schema()
    await seed()
    await main_checks()
    return FAIL


if __name__ == "__main__":
    failed = asyncio.run(main())
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if failed else 0)
