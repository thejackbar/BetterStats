"""Verification for Fantasy round locks and transfers queued behind a locked round,
against a real Postgres.

Asked for: after the lock time a manager cannot change their picked XI, and any
transfer they make moves to the next round, carried out at the prices after the
current round settles. Until now a locked round refused transfers outright (403)
until it was scored.

Runs the SHIPPED `services/fantasy_engine` settle/unsettle, `services/fantasy_queue`,
and the `routers/public_fantasy` `me`, `transfer`, `set_captain`, `play_chip`,
`cancel_queued_transfer` and `notifications` bodies over the `v_effective_*` views
pulled out of the migrations. Only the club and session lookups in the public
routes are stubbed.

CONTROL: run the same script against the previous commit's backend (copy this file
into the worktree's verification/ folder first):

    git worktree add /tmp/ctl <commit before this change>
    BACKEND_DIR=/tmp/ctl/backend DATABASE_URL=... python verification/verify_fantasy_lock_queue.py

It must fail on exactly the reported behaviour (a transfer in a locked round is
refused instead of queued) and on nothing it can't explain. New keys are read
through presence-safe accessors so an absent module is a failed check, not a crash.

Run:  DATABASE_URL=postgresql+asyncpg://root@/fantasy_test?host=/var/run/postgresql \
      python verification/verify_fantasy_lock_queue.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

BACKEND = Path(os.environ.get("BACKEND_DIR") or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(BACKEND))
sys.path.insert(1, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.models.db import (
    Base, Organisation, Season, Grade, Game, Player, BattingInnings, GameAppearance,
    FantasySeason, FantasyRound, FantasyLeague, FantasyManager, FantasySquad,
    FantasySquadPlayer, FantasyPoolPlayer,
)
from app.services import fantasy_engine
from app.routers import public_fantasy

try:
    from app.services import fantasy_queue
except ImportError:
    fantasy_queue = None

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
NOW = datetime.now(timezone.utc)
ORG = uuid.uuid4()
A, B, C, D, E = (uuid.uuid4() for _ in range(5))
FS_ID = uuid.uuid4()
R1, R2 = uuid.uuid4(), uuid.uuid4()
SQ_X, SQ_Y, SQ_Z = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
MGR_X, MGR_Y, MGR_Z = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
BASE = {A: 5.0, B: 14.0, C: 7.0, D: 6.0, E: 10.0}
MGR = {SQ_X: MGR_X, SQ_Y: MGR_Y, SQ_Z: MGR_Z}


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
                   for i, (p, n) in enumerate(((A, "Ann Ace"), (B, "Bo Bat"), (C, "Cy Cap"), (D, "Di Dash"), (E, "Ed Extra")))])
        await s.flush()
        # Round 1's game: A 50, B 10, D 40 (C and E do not play).
        gid = uuid.uuid4()
        s.add(Game(id=gid, grade_id=gr.id, played_at=TODAY - timedelta(days=1), home_team="Alpha", away_team="X",
                   home_org_id=ORG, status="COMPLETED"))
        await s.flush()
        for pid, r in {A: 50, B: 10, D: 40}.items():
            s.add(GameAppearance(game_id=gid, player_id=pid, team_name="Alpha"))
            s.add(BattingInnings(game_id=gid, player_id=pid, innings_number=1, runs=r, balls=r,
                                 fours=0, sixes=0, dismissal_type="bowled", not_out=False))
        s.add(FantasySeason(id=FS_ID, organisation_id=ORG, season_year=year, name=f"{year} Fantasy",
                            status="active", scoring={}, rules={}))
        await s.flush()
        # Round 1 locked two hours ago and is still running; round 2 locks next week.
        s.add_all([
            FantasyRound(id=R1, fantasy_season_id=FS_ID, organisation_id=ORG, round_number=1, name="Round 1",
                         lock_at=NOW - timedelta(hours=2), start_date=TODAY - timedelta(days=1), end_date=TODAY + timedelta(days=1)),
            FantasyRound(id=R2, fantasy_season_id=FS_ID, organisation_id=ORG, round_number=2, name="Round 2",
                         lock_at=NOW + timedelta(days=6), start_date=TODAY + timedelta(days=6), end_date=TODAY + timedelta(days=7)),
        ])
        s.add_all([FantasyPoolPlayer(fantasy_season_id=FS_ID, organisation_id=ORG, player_id=p, role="batter",
                                     base_price=BASE[p], current_price=BASE[p]) for p in BASE])
        s.add_all([FantasyManager(id=m, organisation_id=ORG, display_name=n)
                   for m, n in ((MGR_X, "Xavier"), (MGR_Y, "Yara"), (MGR_Z, "Zed"))])
        await s.flush()
        lg = FantasyLeague(id=uuid.uuid4(), fantasy_season_id=FS_ID, organisation_id=ORG,
                           kind="global_salary_cap", name="Club ladder")
        s.add(lg)
        await s.flush()
        s.add_all([
            FantasySquad(id=SQ_X, fantasy_season_id=FS_ID, league_id=lg.id, manager_id=MGR_X, organisation_id=ORG,
                         team_name="X Team", free_transfers=1, budget_remaining=81.0),
            FantasySquad(id=SQ_Y, fantasy_season_id=FS_ID, league_id=lg.id, manager_id=MGR_Y, organisation_id=ORG,
                         team_name="Y Team", free_transfers=0, budget_remaining=74.0),
            FantasySquad(id=SQ_Z, fantasy_season_id=FS_ID, league_id=lg.id, manager_id=MGR_Z, organisation_id=ORG,
                         team_name="Z Team", free_transfers=1, budget_remaining=0.0),
        ])
        await s.flush()
        s.add_all([
            FantasySquadPlayer(squad_id=SQ_X, player_id=A, role="batter", is_captain=True, purchase_price=5.0),
            FantasySquadPlayer(squad_id=SQ_X, player_id=B, role="batter", is_vice_captain=True, purchase_price=14.0),
            FantasySquadPlayer(squad_id=SQ_Y, player_id=A, role="batter", is_captain=True, purchase_price=5.0),
            FantasySquadPlayer(squad_id=SQ_Y, player_id=B, role="batter", purchase_price=14.0),
            FantasySquadPlayer(squad_id=SQ_Y, player_id=C, role="batter", purchase_price=7.0),
            FantasySquadPlayer(squad_id=SQ_Z, player_id=C, role="batter", is_captain=True, purchase_price=7.0),
        ])
        await s.commit()


def stub_public(squad_id) -> None:
    async def club_for_token(db, token):
        return await db.get(Organisation, ORG)

    async def manager_for_session(db, request, club):
        return await db.get(FantasyManager, MGR[squad_id])
    public_fantasy._club_for_token = club_for_token
    public_fantasy._manager_for_session = manager_for_session


async def transfer(squad_id, out_p, in_p):
    stub_public(squad_id)
    async with Session() as s:
        return await public_fantasy.transfer(
            "tok", public_fantasy.TransferBody(out_player_id=str(out_p), in_player_id=str(in_p)), SimpleNamespace(), db=s)


async def refused(coro):
    try:
        res = await coro
        return None, res
    except HTTPException as e:
        return e.status_code, e.detail


async def picks(squad_id) -> dict:
    async with Session() as s:
        return {r[0]: (r[1], r[2], r[3], float(r[4]) if r[4] is not None else None) for r in (await s.execute(text(
            "SELECT player_id, is_captain, is_vice_captain, role, purchase_price FROM fantasy_squad_players WHERE squad_id = :s"),
            {"s": squad_id})).all()}


async def squad_row(squad_id):
    async with Session() as s:
        r = (await s.execute(text("SELECT budget_remaining, free_transfers FROM fantasy_squads WHERE id = :s"), {"s": squad_id})).first()
        return float(r[0]), int(r[1])


async def round_tally(squad_id, rid):
    async with Session() as s:
        return (await s.execute(text(
            "SELECT transfers_made, transfer_hit FROM fantasy_squad_round_scores WHERE squad_id = :s AND round_id = :r"),
            {"s": squad_id, "r": rid})).first()


async def has_queue() -> bool:
    async with Session() as s:
        return bool((await s.execute(text("SELECT to_regclass('public.fantasy_queued_transfers')"))).scalar())


async def queued(squad_id=None) -> list:
    if not await has_queue():
        return []
    async with Session() as s:
        q = "SELECT out_player_id, in_player_id, status, reason, hit, free_used FROM fantasy_queued_transfers"
        rows = (await s.execute(text(q + (" WHERE squad_id = :s" if squad_id else "") + " ORDER BY created_at"),
                                {"s": squad_id} if squad_id else {})).all()
    return [tuple(r) for r in rows]


async def price_of(p) -> float:
    async with Session() as s:
        return float((await s.execute(text("SELECT current_price FROM fantasy_pool_players WHERE player_id = :p"), {"p": p})).scalar())


async def lineup_ids(squad_id, rid) -> set:
    async with Session() as s:
        lu = (await s.execute(text("SELECT lineup FROM fantasy_squad_round_scores WHERE squad_id = :s AND round_id = :r"),
                              {"s": squad_id, "r": rid})).scalar()
    return {str(e.get("player_id")) for e in (lu or [])}


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


async def main_checks() -> None:
    print("1. A locked round freezes the XI, the captain and the chips")
    stub_public(SQ_X)
    async with Session() as s:
        code, _ = await refused(public_fantasy.set_captain("tok", public_fantasy.CaptainBody(captain_player_id=str(B)), SimpleNamespace(), db=s))
    check("the captain cannot be changed after the lock", code == 403, repr(code))
    async with Session() as s:
        code, _ = await refused(public_fantasy.play_chip("tok", public_fantasy.ChipBody(chip="triple_captain"), SimpleNamespace(), db=s))
    check("a chip cannot be played after the lock", code == 403, repr(code))

    print("2. A transfer after the lock is queued, not refused, and the XI is untouched")
    y0, x0 = await picks(SQ_Y), await picks(SQ_X)
    bank_y0 = await squad_row(SQ_Y)
    code, r = await refused(transfer(SQ_Y, B, D))
    check("a transfer in a locked round is accepted", code is None, f"refused {code}: {r}")
    check("it says it is queued", isinstance(r, dict) and r.get("queued") is True, repr(r))
    check("the team still holds the player going out and not the one coming in",
          B in await picks(SQ_Y) and D not in await picks(SQ_Y))
    check("the bank and free transfers are untouched while it waits", await squad_row(SQ_Y) == bank_y0, repr(await squad_row(SQ_Y)))
    check("nothing is counted against any round yet", await round_tally(SQ_Y, R2) is None and await round_tally(SQ_Y, R1) is None)
    check("the queue holds one pending row", [q[2] for q in await queued(SQ_Y)] == ["pending"], repr(await queued(SQ_Y)))
    code, r = await refused(transfer(SQ_Y, B, E))
    check("the same player cannot be queued out twice", code == 400, repr((code, r)))
    code, r = await refused(transfer(SQ_Y, C, D))
    check("the same player cannot be queued in twice", code == 400, repr((code, r)))
    code, r = await refused(transfer(SQ_Y, C, A))
    check("a player already in the team cannot be queued in", code == 400, repr((code, r)))
    # Y's second queued transfer: C for E. X queues its captain out.
    code, r = await refused(transfer(SQ_Y, C, E))
    check("a second transfer queues behind the first", code is None, repr((code, r)))
    code, r = await refused(transfer(SQ_X, A, E))
    check("the captain can be queued out (the armband passes with the player)", code is None, repr((code, r)))
    code, r = await refused(transfer(SQ_Z, C, B))
    check("a transfer that cannot be afforded at today's prices is queued with a warning, not refused",
          code is None and isinstance(r, dict) and bool(r.get("warning")), repr((code, r)))
    stub_public(SQ_Y)
    async with Session() as s:
        me = await public_fantasy.me("tok", SimpleNamespace(), db=s)
    qt = (me["squad"] or {}).get("queued_transfers") or []
    check("the team page lists what is waiting", len([q for q in qt if q["status"] == "pending"]) == 2, repr(qt))
    async with Session() as s:
        feed = (await public_fantasy.notifications("tok", SimpleNamespace(), db=s))["notifications"]
    check("the notification feed says it is queued", any("queued" in (n.get("title") or "") for n in feed), repr([n.get("title") for n in feed]))

    if not await has_queue() or fantasy_queue is None:
        check("there is a queue for transfers made after the lock", False, "no fantasy_queued_transfers table or service")
        return

    print("3. A queued transfer can be cancelled, and the row is kept")
    stub_public(SQ_Y)
    q_id = None
    async with Session() as s:
        q_id = str((await s.execute(text("SELECT id FROM fantasy_queued_transfers WHERE squad_id = :s AND in_player_id = :p"), {"s": SQ_Y, "p": E})).scalar())
    async with Session() as s:
        await public_fantasy.cancel_queued_transfer("tok", q_id, SimpleNamespace(), db=s)
    check("cancelled, not deleted", [q[2] for q in await queued(SQ_Y)] == ["pending", "cancelled"], repr(await queued(SQ_Y)))
    code, r = await refused(transfer(SQ_Y, C, E))
    check("and it can be queued again", code is None, repr((code, r)))

    print("4. Settling the locked round scores it with the XI that was locked, then carries the queue out")
    p_before = {p: await price_of(p) for p in (B, D, C, E)}
    await settle(R1)
    p_after = {p: await price_of(p) for p in (B, D, C, E)}
    check("prices moved when the round settled (so 'prices after settlement' differs from before)",
          p_after[B] != p_before[B] and p_after[D] != p_before[D], f"{p_before} -> {p_after}")
    check("Y's round 1 XI still has B and not D", await lineup_ids(SQ_Y, R1) >= {str(A), str(B), str(C)} and str(D) not in await lineup_ids(SQ_Y, R1),
          repr(await lineup_ids(SQ_Y, R1)))
    check("X's round 1 XI still has its captain A and not E", str(A) in await lineup_ids(SQ_X, R1) and str(E) not in await lineup_ids(SQ_X, R1))
    py = await picks(SQ_Y)
    check("after settling, Y holds D and E and no longer B and C", D in py and E in py and B not in py and C not in py, repr(list(py)))
    bank_y, free_y = await squad_row(SQ_Y)
    want_y = 74.0 + p_after[B] - p_after[D] + p_after[C] - p_after[E]
    check("Y's bank is settled at the prices after the round", near(bank_y, want_y), f"{bank_y} vs {want_y}")
    check("D was bought at the price after settlement", near(py[D][3], p_after[D]), repr(py[D]))
    check("the first transfer used the free one the round banked; the second took the hit",
          [(q[4], q[5]) for q in await queued(SQ_Y) if q[2] == "applied"] == [(0, True), (4, False)],
          repr([(q[2], q[4], q[5]) for q in await queued(SQ_Y)]))
    check("both count against round 2 (2 transfers, a 4 point hit)", tuple(await round_tally(SQ_Y, R2)) == (2, 4), repr(await round_tally(SQ_Y, R2)))
    px = await picks(SQ_X)
    check("X's armband passed to the player who came in", E in px and px[E][0] is True and A not in px, repr(px.get(E)))
    check("X's vice captain is unchanged", px[B][1] is True)
    pz = await picks(SQ_Z)
    check("Z could not afford it after the price changes, so nothing happened", C in pz and B not in pz, repr(list(pz)))
    qz = await queued(SQ_Z)
    check("and the manager is told why", qz and qz[0][2] == "cancelled" and "short" in (qz[0][3] or ""), repr(qz))
    check("Z's free transfer was not used", (await squad_row(SQ_Z))[1] == 2, repr(await squad_row(SQ_Z)))
    stub_public(SQ_Z)
    async with Session() as s:
        feed = (await public_fantasy.notifications("tok", SimpleNamespace(), db=s))["notifications"]
    check("Z's notifications say it didn't go through", any("didn't go through" in (n.get("title") or "") for n in feed), repr([n.get("title") for n in feed]))

    print("5. Settling again changes nothing")
    snap = (await picks(SQ_Y), await squad_row(SQ_Y), await squad_row(SQ_X), await queued())
    await settle(R1)
    check("a second settle does not carry anything out twice", snap == (await picks(SQ_Y), await squad_row(SQ_Y), await squad_row(SQ_X), await queued()))

    print("6. Unsettling the round puts the transfers back, settling again repeats them")
    after_settle = (await picks(SQ_Y), await squad_row(SQ_Y), await picks(SQ_X), await squad_row(SQ_X), await round_tally(SQ_Y, R2))
    await unsettle(R1)
    check("Y holds the XI it locked with", set(await picks(SQ_Y)) == {A, B, C}, repr(list(await picks(SQ_Y))))
    check("Y's bank and free transfers are back", await squad_row(SQ_Y) == (74.0, 0), repr(await squad_row(SQ_Y)))
    px = await picks(SQ_X)
    check("X's captain is back", A in px and px[A][0] is True and E not in px, repr(list(px)))
    check("the tally against round 2 is gone", (await round_tally(SQ_Y, R2)) in (None, (0, 0)), repr(await round_tally(SQ_Y, R2)))
    check("the transfers are waiting again", [q[2] for q in await queued(SQ_Y) if q[2] != "cancelled"] == ["pending", "pending"], repr(await queued(SQ_Y)))
    await settle(R1)
    again = (await picks(SQ_Y), await squad_row(SQ_Y), await picks(SQ_X), await squad_row(SQ_X), await round_tally(SQ_Y, R2))
    check("settling again gives the same teams, banks and tallies as the first time", again == after_settle, f"{after_settle} -> {again}")

    print("7. A transfer that can't safely be put back is left as it happened")
    async with Session() as s:   # Y has since moved D on in an ordinary transfer
        await s.execute(text("DELETE FROM fantasy_squad_players WHERE squad_id = :s AND player_id = :p"), {"s": SQ_Y, "p": D})
        await s.commit()
    async with Session() as s:
        fs = await s.get(FantasySeason, FS_ID)
        rnd = await s.get(FantasyRound, R1)
        res = await fantasy_queue.revert_applied(s, fs, rnd)
        await s.commit()
    check("the safe ones are put back (Y's C for E, X's captain) and the unsafe one is kept (Y's B for D)", res == {"reverted": 2, "kept": 1}, repr(res))
    check("only the safe one changed: C is back, E is gone, nothing duplicated", set(await picks(SQ_Y)) == {A, C}, repr(list(await picks(SQ_Y))))


async def main() -> int:
    await build_schema()
    await seed()
    await main_checks()
    return FAIL


if __name__ == "__main__":
    failed = asyncio.run(main())
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if failed else 0)
