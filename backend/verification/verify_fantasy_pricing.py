"""Verification for Fantasy player price movement, against a real Postgres.

Reported (1): player prices never changed after a round was scored (the design said they
should move on performances), there were no arrows to show a rise or fall, and a
sale returned the purchase price plus half the rise, so the bank did not follow the
player's price.
Reported (2): once prices did move, nearly everyone went up by the 0.5 cap: a cheap
player on 41 points rose as far as one on 82 or 150. The rule compared a score with what
the STARTING price implied, which is about nothing for a player on the floor price.

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
# The rule's own functions are read through hasattr so the previous commit (which has a
# different rule) reports failed checks instead of crashing.
HAS_RULE = fantasy_pricing is not None and hasattr(fantasy_pricing, "peer_moves")

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
LOW = [uuid.uuid4() for _ in range(7)]             # on or near the floor price, 41 points in round 1
L82 = uuid.uuid4()                                 # cheap, 82 points in round 1
MID = [uuid.uuid4() for _ in range(3)]
FS_ID = uuid.uuid4()
R1, R2 = uuid.uuid4(), uuid.uuid4()
SQ_X, SQ_Y = uuid.uuid4(), uuid.uuid4()
MGR_X, MGR_Y = uuid.uuid4(), uuid.uuid4()
BASE = {A: 5.0, B: 14.0, C: 7.0, D: 8.0, E: 10.0, L82: 4.5}
BASE.update(dict(zip(LOW, (4.0, 4.0, 4.0, 4.5, 4.5, 5.0, 5.0))))
BASE.update(dict(zip(MID, (8.0, 8.5, 9.0))))
# Runs per player per round. Batting only, no boundaries: points = runs + 4 for turning out,
# +16 from 50 runs and +32 from 100 (not both). 37 runs = 41 points, 62 runs = 82, 110 runs = 146.
R1_RUNS = {A: 110, B: 6, C: 30, L82: 62, **{p: 37 for p in LOW}, **{p: 25 for p in MID}}
R2_RUNS = {A: 20, C: 30, **{p: 37 for p in LOW}, **{p: 25 for p in MID}}


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
        names = {A: "Ann Ace", B: "Bo Bat", C: "Cy Cap", D: "Di Idle", E: "Ed Extra", L82: "Lo Eighty"}
        names.update({p: f"Low {i + 1}" for i, p in enumerate(LOW)})
        names.update({p: f"Mid {i + 1}" for i, p in enumerate(MID)})
        s.add_all([Player(id=p, name=n, organisation_id=ORG, grassroots_id=f"p{i}") for i, (p, n) in enumerate(names.items())])
        await s.flush()
        for gdate, runs in ((TODAY - timedelta(days=18), R1_RUNS), (TODAY - timedelta(days=9), R2_RUNS)):
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


async def expected_prices(start: dict | None = None, fixed: set | None = None) -> dict:
    """The prices the pure rule gives for the scored rounds as stored in the database,
    {player: (price, last move)}. Reads only the points and rounds, so it checks that the
    shipped recompute wires the database to the rule, not just the rule."""
    async with Session() as s:
        rnds = (await s.execute(text("SELECT id, round_number FROM fantasy_rounds WHERE status = 'scored' ORDER BY round_number"))).all()
        rounds = []
        for rid, rn in rnds:
            rows = (await s.execute(text(
                "SELECT player_id, total_points, games_counted FROM fantasy_player_round_scores WHERE round_id = :r"), {"r": rid})).all()
            rounds.append((rn, {str(p): float(t) / max(int(g), 1) for p, t, g in rows}))
        if start is None:
            start = {str(p): float(b) for p, b in (await s.execute(text("SELECT player_id, base_price FROM fantasy_pool_players"))).all()}
    res = fantasy_pricing.replay_season(start, fixed or set(), rounds)
    return {uuid.UUID(k): (v["price"], v["last"]) for k, v in res.items()}


async def main_checks() -> None:
    print("0. The movement rule on its own")
    if not HAS_RULE:
        check("prices move relative to the other players in the round (peer_moves)", False, "the module has no such rule")
    else:
        import random
        random.seed(11)
        club = {}
        for i in range(80):
            price = random.choice([4.0] * 30 + [5.0] * 20 + [7.0] * 12 + [9.0] * 10 + [12.0] * 8)
            club[f"p{i}"] = (max(4.0, random.gauss(15 + (price - 4) * 5, 20)), price)
        mv = fantasy_pricing.peer_moves(club)
        check("moves are whole tenths held to the 0.5 cap", all(abs(v) <= 0.5 + 1e-9 and abs(v * 10 - round(v * 10)) < 1e-9 for v in mv.values()))
        check("a round nets out to about nothing, so prices cannot all drift one way", abs(sum(mv.values()) / len(mv)) < 0.05, repr(sum(mv.values()) / len(mv)))
        check("most players move 0.2 or less on an ordinary round", sum(abs(v) <= 0.2 for v in mv.values()) >= 0.9 * len(mv))
        club_boost = {k: (v[0] * 1.5, v[1]) for k, v in club.items()}
        check("everyone scoring more (a flat track) moves nobody on average", abs(sum(fantasy_pricing.peer_moves(club_boost).values()) / len(club)) < 0.05)

        def move_for(pts, price):
            s_ = dict(club)
            s_["x"] = (pts, price)
            return fantasy_pricing.peer_moves(s_)["x"]
        m41, m82, m150 = move_for(41, 4.5), move_for(82, 4.5), move_for(150, 4.5)
        check("a cheap player on 41 points no longer gets the full 0.5", m41 < 0.5 and m41 <= 0.2, repr(m41))
        check("82 points is worth clearly more than 41, and 150 (a century) gets the 0.5", m41 < m82 < 0.5 <= m150, repr((m41, m82, m150)))
        check("a star's flop falls, but not past the cap", -0.5 <= move_for(8, 13.0) < 0, repr(move_for(8, 13.0)))
        check("fewer than 6 players makes no moves", fantasy_pricing.peer_moves({f"q{i}": (50.0 + i * 20, 5.0 + i) for i in range(5)}) == {f"q{i}": 0.0 for i in range(5)})
        rep1 = fantasy_pricing.replay_season({"a": 5.0, "b": 4.0}, set(), [(1, {"a": 90.0})])
        check("a player who did not play does not move", rep1["b"]["price"] == 4.0 and rep1["b"]["last"] == 0.0)
        floor = fantasy_pricing.replay_season({f"f{i}": 4.0 for i in range(8)}, set(), [(1, {f"f{i}": 0.0 if i == 0 else 90.0 for i in range(8)})])
        check("a price never goes below the floor", all(v["price"] >= 4.0 for v in floor.values()))
        locked = fantasy_pricing.replay_season({f"f{i}": 6.0 for i in range(8)}, {"f0"}, [(1, {f"f{i}": 200.0 if i == 0 else 20.0 for i in range(8)})])
        check("a locked price never moves, while the others still do",
              locked["f0"]["price"] == 6.0 and locked["f1"]["price"] != 6.0, repr((locked["f0"], locked["f1"])))

    print("1. Nothing moves before a round is scored")
    p0 = await prices()
    check("every player is on their starting price", all(near(p0[p][0], BASE[p]) and near(p0[p][1], 0) for p in BASE), repr(p0))

    print("2. Settling round 1: moves follow the score, and cheap players are not all on the cap")
    await settle(R1)
    p1 = await prices()
    pts1 = await round_points(R1)
    check("player scores exist for those who played", set(pts1) == set(R1_RUNS), repr(len(pts1)))
    check("41 points is 41 points (the setup is what the report describes)", all(near(pts1[p], 41) for p in LOW), repr([pts1[p] for p in LOW]))
    cheap41 = [p1[p][1] for p in LOW]
    check("no cheap player on 41 points is on the 0.5 cap", all(m < 0.5 for m in cheap41), repr(cheap41))
    check("a cheap 41 is worth no more than 0.2", all(m <= 0.2 + 1e-9 for m in cheap41), repr(cheap41))
    check("82 points moves a price clearly more than 41 and still not to the cap", p1[L82][1] - max(cheap41) >= 0.1 and p1[L82][1] < 0.5, repr((p1[L82], cheap41)))
    check("a century (146 points) earns the full 0.5", near(p1[A][1], 0.5) and near(p1[A][0], 5.5), repr(p1[A]))
    check("a star who flopped (10 points) falls, by less than the cap", -0.5 < p1[B][1] <= -0.2, repr(p1[B]))
    moved = [p1[p][1] for p in R1_RUNS]
    check("the round nets out to about nothing (they cannot all go up)", abs(sum(moved) / len(moved)) < 0.15, repr(sum(moved) / len(moved)))
    check("some players went down and some up", min(moved) < 0 < max(moved), repr(sorted(moved)))
    check("players who did not play have not moved", all(near(p1[p][0], BASE[p]) and near(p1[p][1], 0) for p in (D, E)), repr((p1[D], p1[E])))
    check("every move is a whole tenth within the cap", all(abs(m) <= 0.5 + 1e-9 and abs(m * 10 - round(m * 10)) < 1e-6 for m in moved))
    if HAS_RULE:
        want = await expected_prices()
        check("the stored prices are what the rule gives for the stored scores", all(near(p1[p][0], want[p][0]) and near(p1[p][1], want[p][1]) for p in BASE),
              repr([(p, p1[p], want[p]) for p in BASE if not near(p1[p][0], want[p][0])][:2]))

    print("3. Settling the same round again does not move it twice")
    await settle(R1)
    p1b = await prices()
    check("prices are the same after a second settle", p1b == p1, f"{p1} -> {p1b}")

    print("4. The bank follows the price (sale at the current price)")
    # Fix the two prices the sale checks use, so they run the same against the previous
    # commit (which never moved a price) and do not depend on the movement rule.
    async with Session() as s:
        await s.execute(text("UPDATE fantasy_pool_players SET current_price = 5.5, price_change = 0.5 WHERE player_id = :p"), {"p": A})
        await s.execute(text("UPDATE fantasy_pool_players SET current_price = 13.5, price_change = -0.5 WHERE player_id = :p"), {"p": B})
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
    async with Session() as s:
        d_price = float((await s.execute(text("SELECT current_price FROM fantasy_pool_players WHERE player_id = :p"), {"p": D})).scalar())
        e_price = float((await s.execute(text("SELECT current_price FROM fantasy_pool_players WHERE player_id = :p"), {"p": E})).scalar())
    r = await do_transfer(MGR_Y, A, D)
    check(f"selling a player who rose banks the whole rise (95 + 5.5 - {d_price} = {95 + 5.5 - d_price})", near(r["budget_remaining"], 95 + 5.5 - d_price), repr(r))
    async with Session() as s:
        await s.execute(text("UPDATE fantasy_squad_players SET is_captain = false WHERE squad_id = :s"), {"s": SQ_X})
        await s.execute(text("UPDATE fantasy_squad_players SET is_captain = true WHERE squad_id = :s AND player_id = :p"), {"s": SQ_X, "p": A})
        await s.commit()
    r = await do_transfer(MGR_X, B, E)
    check(f"selling a player who fell takes the fall (81 + 13.5 - {e_price} = {81 + 13.5 - e_price})", near(r["budget_remaining"], 81 + 13.5 - e_price), repr(r))

    print("5. Round 2: a player who sat out does not move; the rest compound")
    await settle(R2)
    p2 = await prices()
    pts2 = await round_points(R2)
    check("round 2 scored the players who turned out", set(pts2) == set(R2_RUNS) and B not in pts2, repr(len(pts2)))
    if HAS_RULE:
        want = await expected_prices()
        check("every price is the replay of both rounds", all(near(p2[p][0], want[p][0]) and near(p2[p][1], want[p][1]) for p in BASE),
              repr([(p, p2[p], want[p]) for p in BASE if not near(p2[p][0], want[p][0])][:2]))
    check("B sat out round 2, so no move this round", near(p2[B][1], 0), repr(p2[B]))
    check("A's round 2 move is the gap between the two prices", near(p2[A][1], p2[A][0] - p1[A][0]), f"{p1[A]} -> {p2[A]}")
    check("a cheap 41 stays a small move in round 2 too (no century in the pack, so a tenth or so)",
          all(abs(p2[p][1]) <= 0.2 + 1e-9 for p in LOW), repr([p2[p][1] for p in LOW]))

    print("6. Unsettling takes the movement back")
    await unsettle(R2)
    pu = await prices()
    check("round 2 off: everyone is back to their round 1 price and move",
          all(near(pu[p][0], p1[p][0]) and near(pu[p][1], p1[p][1]) for p in BASE), repr([(p, pu[p], p1[p]) for p in BASE if not near(pu[p][0], p1[p][0])][:2]))
    await unsettle(R1)
    pu = await prices()
    check("round 1 off too: everyone is on their starting price", all(near(pu[p][0], BASE[p]) and near(pu[p][1], 0) for p in BASE), repr(pu))
    await settle(R1)
    await settle(R2)
    p3 = await prices()
    check("settling again gives the same prices as the first time", p3 == p2, f"{p2} -> {p3}")

    print("6b. The admin Price movements page shows the same prices, and how they got there")
    route = getattr(fantasy_router, "price_movements", None)
    if route is None:
        check("there is a price movements route for the admin", False, "no price_movements in the routes module")
    else:
        async with Session() as s:
            res = await route(str(FS_ID), club=SimpleNamespace(id=ORG), db=s, _=None)
        by = {uuid.UUID(p["player_id"]): p for p in res["players"]}
        check("every pool player is listed", set(by) == set(BASE), repr(len(by)))
        check("price and last move are the stored ones", all(near(by[p]["price"], p3[p][0]) and near(by[p]["last_change"], p3[p][1]) for p in BASE))
        check("the season move is price less the starting price", all(near(by[p]["season_change"], p3[p][0] - BASE[p]) for p in BASE))
        check("the history adds up to the season move", all(near(sum(h["move"] for h in by[p]["history"]), by[p]["season_change"]) for p in BASE))
        check("a player who sat out round 2 has only round 1 in their history", [h["round"] for h in by[B]["history"]] == [1], repr(by[B]["history"]))
        check("the latest round is reported", res["last_round"] == 2, repr(res["last_round"]))
        sm = res["summary"]
        check("the risers and fallers counts match the list",
              sm["risers"] == sum(1 for p in BASE if p3[p][1] > 0) and sm["fallers"] == sum(1 for p in BASE if p3[p][1] < 0)
              and sm["risers"] + sm["fallers"] + sm["unchanged"] == len(BASE), repr(sm))
        top = max(BASE, key=lambda p: p3[p][1])
        check("the biggest riser is named", sm["biggest_riser"] is not None and near(sm["biggest_riser"]["change"], p3[top][1]), repr(sm["biggest_riser"]))

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
        want = await expected_prices() if HAS_RULE else {C: (None, None)}
        check("handing it back to auto replays the rounds onto the starting price", near(pc[0], want[C][0]) and near(pc[1], want[C][1]) and pc[0] != 9.0, f"{pc} vs {want[C]}")

    print("8. A season scored before price movement existed catches up")
    async with Session() as s:
        await s.execute(text("UPDATE fantasy_pool_players SET current_price = base_price, price_change = 0"))
        await s.commit()
    if not HAS_RULE:
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
    if not HAS_RULE or not await has_column():
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
        async with Session() as s:
            bases = {str(p): float(b) for p, b in (await s.execute(text("SELECT player_id, base_price FROM fantasy_pool_players"))).all()}
        want = (await expected_prices(start=bases))[A]
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
