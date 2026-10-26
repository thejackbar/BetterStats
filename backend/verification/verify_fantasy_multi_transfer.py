"""Verification for Fantasy transfers made several at a time, against a real Postgres.

Asked for: sell more than one player in one go, so the money from the second sale can
pay for the first pick, instead of doing the swaps one at a time and failing the budget
on each. A swap that fits only because of another sale was refused one by one.

Runs the SHIPPED `routers/public_fantasy` `transfer` and `transfers` bodies and
`services/fantasy_queue.apply_pending`. Only the club and session lookups are stubbed.

CONTROL: run this file against the previous commit's backend (copy it into the
worktree's verification/ folder first):

    git worktree add /tmp/ctl <commit before this change>
    BACKEND_DIR=/tmp/ctl/backend DATABASE_URL=... python verification/verify_fantasy_multi_transfer.py

It must fail on exactly the reported behaviour (no batch route; a queued swap that only
a later sale pays for is cancelled) and on nothing it can't explain.

Run:  DATABASE_URL=postgresql+asyncpg://root@/fantasy_test?host=/var/run/postgresql \
      python verification/verify_fantasy_multi_transfer.py
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
    Base, Organisation, Player, FantasySeason, FantasyRound, FantasyLeague, FantasyManager,
    FantasySquad, FantasySquadPlayer, FantasyPoolPlayer,
)
from app.routers import public_fantasy
from app.services import fantasy_queue

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


TODAY = date.today()
NOW = datetime.now(timezone.utc)
ORG = uuid.uuid4()
CAP, VICE, P1, P2, X, Y, Z = (uuid.uuid4() for _ in range(7))
KEEPER = uuid.uuid4()
PRICE = {CAP: 5.0, VICE: 5.0, P1: 10.0, P2: 14.0, X: 12.0, Y: 9.0, Z: 13.0}
NAMES = {CAP: "Cap", VICE: "Vice", P1: "Pat One", P2: "Pat Two", X: "Xan", Y: "Yul", Z: "Zed Z"}
FS_ID, R1, R2 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
# M: bank 1.1, one free transfer.  N: bank 0, none.  L, H: queued behind a lock.
SQUADS = {k: (uuid.uuid4(), uuid.uuid4(), b, f) for k, b, f in (("M", 1.1, 1), ("N", 0.0, 0), ("L", 1.1, 1), ("H", 0.0, 1))}
MGR = {v[0]: v[1] for v in SQUADS.values()}


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
        s.add_all([Player(id=p, name=NAMES[p], organisation_id=ORG, grassroots_id=f"p{i}") for i, p in enumerate(PRICE)])
        s.add(FantasySeason(id=FS_ID, organisation_id=ORG, season_year=year, name=f"{year} Fantasy",
                            status="active", scoring={}, rules={}))
        await s.flush()
        # Round 1 is open (locks next week) until the locked scenarios flip it.
        s.add_all([
            FantasyRound(id=R1, fantasy_season_id=FS_ID, organisation_id=ORG, round_number=1, name="Round 1",
                         lock_at=NOW + timedelta(days=5), start_date=TODAY + timedelta(days=5), end_date=TODAY + timedelta(days=6)),
            FantasyRound(id=R2, fantasy_season_id=FS_ID, organisation_id=ORG, round_number=2, name="Round 2",
                         lock_at=NOW + timedelta(days=12), start_date=TODAY + timedelta(days=12), end_date=TODAY + timedelta(days=13)),
        ])
        s.add_all([FantasyPoolPlayer(fantasy_season_id=FS_ID, organisation_id=ORG, player_id=p, role="batter",
                                     base_price=PRICE[p], current_price=PRICE[p]) for p in PRICE])
        # A bowler to prove the role rule.
        s.add(Player(id=KEEPER, name="Kay Keeper", organisation_id=ORG, grassroots_id="pk"))
        await s.flush()
        s.add(FantasyPoolPlayer(fantasy_season_id=FS_ID, organisation_id=ORG, player_id=KEEPER, role="keeper",
                                base_price=6.0, current_price=6.0))
        lg = FantasyLeague(id=uuid.uuid4(), fantasy_season_id=FS_ID, organisation_id=ORG, kind="global_salary_cap", name="Club ladder")
        s.add_all([FantasyManager(id=m, organisation_id=ORG, display_name=k) for k, (_, m, _, _) in SQUADS.items()])
        s.add(lg)
        await s.flush()
        for k, (sq, m, bank, fr) in SQUADS.items():
            s.add(FantasySquad(id=sq, fantasy_season_id=FS_ID, league_id=lg.id, manager_id=m, organisation_id=ORG,
                               team_name=f"{k} Team", free_transfers=fr, budget_remaining=bank))
        await s.flush()
        for k, (sq, _, _, _) in SQUADS.items():
            s.add_all([
                FantasySquadPlayer(squad_id=sq, player_id=CAP, role="batter", is_captain=True, purchase_price=5.0),
                FantasySquadPlayer(squad_id=sq, player_id=VICE, role="batter", is_vice_captain=True, purchase_price=5.0),
                FantasySquadPlayer(squad_id=sq, player_id=P1, role="batter", purchase_price=10.0),
                FantasySquadPlayer(squad_id=sq, player_id=P2, role="batter", purchase_price=14.0),
            ])
        await s.commit()


def stub_public(squad_id) -> None:
    async def club_for_token(db, token):
        return await db.get(Organisation, ORG)

    async def manager_for_session(db, request, club):
        return await db.get(FantasyManager, MGR[squad_id])
    public_fantasy._club_for_token = club_for_token
    public_fantasy._manager_for_session = manager_for_session


async def single(key, out_p, in_p):
    stub_public(SQUADS[key][0])
    async with Session() as s:
        return await public_fantasy.transfer(
            "tok", public_fantasy.TransferBody(out_player_id=str(out_p), in_player_id=str(in_p)), SimpleNamespace(), db=s)


async def batch(key, swaps):
    """The batch route, read presence-safely so a missing route is a failed check."""
    stub_public(SQUADS[key][0])
    fn = getattr(public_fantasy, "transfers", None)
    body_cls = getattr(public_fantasy, "TransfersBody", None)
    if fn is None or body_cls is None:
        raise HTTPException(status_code=404, detail="no batch transfer route")
    body = body_cls(swaps=[public_fantasy.TransferBody(out_player_id=str(o), in_player_id=str(i)) for o, i in swaps])
    async with Session() as s:
        return await fn("tok", body, SimpleNamespace(), db=s)


async def refused(coro):
    try:
        return None, await coro
    except HTTPException as e:
        return e.status_code, e.detail


async def held(key) -> set:
    async with Session() as s:
        return {r[0] for r in (await s.execute(text("SELECT player_id FROM fantasy_squad_players WHERE squad_id = :s"),
                                               {"s": SQUADS[key][0]})).all()}


async def squad_row(key):
    async with Session() as s:
        r = (await s.execute(text("SELECT budget_remaining, free_transfers FROM fantasy_squads WHERE id = :s"), {"s": SQUADS[key][0]})).first()
        return round(float(r[0]), 1), int(r[1])


async def tally(key, rid):
    async with Session() as s:
        return (await s.execute(text("SELECT transfers_made, transfer_hit FROM fantasy_squad_round_scores WHERE squad_id = :s AND round_id = :r"),
                                {"s": SQUADS[key][0], "r": rid})).first()


async def queue_rows(key):
    async with Session() as s:
        return [tuple(r) for r in (await s.execute(text(
            "SELECT out_player_id, in_player_id, status, reason FROM fantasy_queued_transfers WHERE squad_id = :s ORDER BY created_at"),
            {"s": SQUADS[key][0]})).all()]


async def main_checks() -> None:
    print("1. One at a time, a swap that only another sale pays for is refused")
    code, r = await refused(single("M", P1, X))
    check("selling Pat One (10.0) for Xan (12.0) alone is over the 1.1 bank", code == 400, repr((code, r)))

    print("2. The same swap in a batch with a second sale goes through")
    code, r = await refused(batch("M", [(P1, X), (P2, Y)]))
    check("a batch of two swaps is accepted", code is None, repr((code, r)))
    check("both players left and both came in", await held("M") == {CAP, VICE, X, Y}, repr(await held("M")))
    check("the bank is the sum of both swaps (1.1 + 24.0 - 21.0)", await squad_row("M") == (4.1, 0), repr(await squad_row("M")))
    check("the free transfer covered one swap and the other took the hit",
          isinstance(r, dict) and r.get("hit") == 4 and r.get("count") == 2, repr(r))
    check("both are tallied against the round", tuple(await tally("M", R1) or ()) == (2, 4), repr(await tally("M", R1)))

    print("3. All or nothing: a set that does not fit changes nothing")
    code, r = await refused(batch("N", [(P1, X), (P2, Z)]))
    check("12.0 + 13.0 against 24.0 and a 0 bank is refused", code == 400, repr((code, r)))
    check("the swap that would have fitted on its own did not happen", await held("N") == {CAP, VICE, P1, P2}, repr(await held("N")))
    check("bank and free transfers untouched", await squad_row("N") == (0.0, 0), repr(await squad_row("N")))
    check("nothing tallied", await tally("N", R1) is None)

    print("4. The other rules still hold in a batch")
    code, r = await refused(batch("N", [(CAP, X)]))
    check("the captain cannot be sold", code == 400, repr((code, r)))
    code, r = await refused(batch("N", [(P1, X), (P1, Y)]))
    check("the same player cannot go out twice", code == 400, repr((code, r)))
    code, r = await refused(batch("N", [(P1, Y), (P2, Y)]))
    check("the same player cannot come in twice", code == 400, repr((code, r)))
    code, r = await refused(batch("N", [(P1, KEEPER)]))
    check("a batter cannot be swapped for a keeper", code == 400, repr((code, r)))
    code, r = await refused(batch("N", [(P1, P2)]))
    check("a player already held cannot come in", code == 400, repr((code, r)))
    code, r = await refused(batch("N", []))
    check("an empty batch is refused", code == 400, repr((code, r)))
    check("the single swap still works through the shared path", (await refused(single("N", P2, Z)))[0] is None
          and await held("N") == {CAP, VICE, P1, Z} and await squad_row("N") == (1.0, 0), repr((await held("N"), await squad_row("N"))))

    print("5. Behind a lock the swaps queue, and a later sale can pay for an earlier pick")
    async with Session() as s:
        await s.execute(text("UPDATE fantasy_rounds SET lock_at = now() - interval '2 hours' WHERE id = :r"), {"r": R1})
        await s.commit()
    code, r = await refused(batch("L", [(P1, X), (P2, Y)]))
    if code == 404:
        # Control run: no batch route, so queue the same two the old way.
        await single("L", P1, X)
        code, r = await refused(single("L", P2, Y))
    check("two swaps queue", code is None and isinstance(r, dict) and r.get("queued") is True, repr((code, r)))
    check("two pending rows, squad untouched", [q[2] for q in await queue_rows("L")] == ["pending", "pending"]
          and await held("L") == {CAP, VICE, P1, P2}, repr(await queue_rows("L")))
    check("the batch reply says how many it queued", isinstance(r, dict) and r.get("count") == 2, repr(r))
    code, r = await refused(single("H", P1, X))
    code2, r2 = await refused(single("H", P2, Z))
    check("H queues a pair the budget cannot cover (12.0 + 13.0 against 24.0)", code is None and code2 is None, repr((code, r, code2, r2)))

    print("6. Settlement carries out a queued swap that a later sale pays for")
    async with Session() as s:
        await s.execute(text("UPDATE fantasy_rounds SET status = 'scored' WHERE id = :r"), {"r": R1})
        await s.commit()
    async with Session() as s:
        fs = await s.get(FantasySeason, FS_ID)
        res = await fantasy_queue.apply_pending(s, fs)
        await s.commit()
    check("L: both queued swaps happened", [q[2] for q in await queue_rows("L")] == ["applied", "applied"], repr(await queue_rows("L")))
    check("L holds both pickups", await held("L") == {CAP, VICE, X, Y}, repr(await held("L")))
    check("L's bank is 1.1 + 24.0 - 21.0 = 4.1", (await squad_row("L"))[0] == 4.1, repr(await squad_row("L")))
    check("H: only the swap the bank could carry was made",
          sorted(q[2] for q in await queue_rows("H")) == ["applied", "cancelled"], repr(await queue_rows("H")))
    cancelled = [q for q in await queue_rows("H") if q[2] == "cancelled"]
    check("and the manager is told why", bool(cancelled) and "short" in (cancelled[0][3] or ""), repr(cancelled))
    check("H's bank never went below zero", (await squad_row("H"))[0] >= 0, repr(await squad_row("H")))


async def main() -> None:
    await build_schema()
    await seed()
    await main_checks()
    await engine.dispose()
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
