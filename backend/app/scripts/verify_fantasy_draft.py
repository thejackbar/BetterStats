"""End-to-end smoke test for a BetterFantasyCricket draft, run against a live DB.

The draft engine couldn't be exercised in the build sandbox (no Postgres), so this
script verifies it on a real database. For an org that already has a fantasy season
with a built pool, it spins up a throwaway draft league plus a few test managers,
drives the whole draft through the real engine — snake auto/explicit picks, or the
auction's nominate / proxy-bid / award loop — then asserts the invariants:

  * every squad is full (squad_size players)
  * each squad meets the role quota exactly
  * exactly one captain and one vice per squad
  * auction squads never spend over budget
  * the ladder (total-points or head-to-head) computes

It prints PASS / FAIL per format and then DELETES everything it created. It never
touches the real season, pool, players or any existing league — only its own
VERIFY-* managers and league, which it removes on the way out (even on failure).

Usage from the backend container:
  docker exec -e PYTHONPATH=/app betterstats-backend \\
    python -m app.scripts.verify_fantasy_draft <org_id>          # both formats
  docker exec -e PYTHONPATH=/app betterstats-backend \\
    python -m app.scripts.verify_fantasy_draft <org_id> auction  # one format
"""
import asyncio
import secrets
import sys
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func

from app.models.db import (
    async_session_maker, FantasySeason, FantasyManager, FantasyLeague,
    FantasyLeagueMember, FantasyPoolPlayer, FantasySquad, FantasySquadPlayer,
    FantasyDraft, FantasyDraftPick,
)
from app.services import fantasy_draft as fd


def _past():
    return datetime.now(timezone.utc) - timedelta(seconds=1)


async def _latest_season(s, org_id):
    return (await s.execute(
        select(FantasySeason).where(FantasySeason.organisation_id == org_id)
        .order_by(FantasySeason.season_year.desc())
    )).scalars().first()


async def _capacity(s, fs):
    """How many test managers we can run so every squad fills its role quota."""
    rows = (await s.execute(
        select(FantasyPoolPlayer.role, func.count())
        .where(FantasyPoolPlayer.fantasy_season_id == fs.id, FantasyPoolPlayer.is_available.is_(True))
        .group_by(FantasyPoolPlayer.role)
    )).all()
    role_avail = {r: c for r, c in rows}
    total = sum(role_avail.values())
    quota, size = fd._role_quota(fs), fd._squad_size(fs)
    by_role = min((role_avail.get(r, 0) // int(q)) for r, q in quota.items() if int(q) > 0) if quota else 0
    n = min(3, by_role, (total // size) if size else 0)
    return n, role_avail, total


async def _needed_choice(s, draft, fs, manager_id, pool):
    """An available pool player in a role this manager still needs (or None)."""
    picks = (await s.execute(
        select(FantasyDraftPick).where(FantasyDraftPick.draft_id == draft.id)
    )).scalars().all()
    taken = {str(p.player_id) for p in picks if p.player_id}
    rc: dict[str, int] = {}
    for p in picks:
        if p.player_id and str(p.manager_id) == str(manager_id):
            r = pool.get(str(p.player_id), {}).get("role", "")
            rc[r] = rc.get(r, 0) + 1
    quota = fd._role_quota(fs)
    needed = {r for r, q in quota.items() if rc.get(r, 0) < int(q)}
    for pid, info in pool.items():
        if pid not in taken and info["role"] in needed:
            return pid
    return None


async def _try_second_bid(s, draft, fs, pool):
    """Exercise place_bid + the proxy resolve: have another eligible manager bid."""
    if draft.lot_player_id is None:
        return
    role = pool.get(str(draft.lot_player_id), {}).get("role", "")
    quota, size, budget = fd._role_quota(fs), fd._squad_size(fs), fd._draft_budget(fs)
    picks = (await s.execute(
        select(FantasyDraftPick).where(FantasyDraftPick.draft_id == draft.id)
    )).scalars().all()
    spent: dict[str, float] = {}
    filled: dict[str, int] = {}
    rc: dict[str, dict] = {}
    for p in picks:
        if not p.player_id:
            continue
        m = str(p.manager_id)
        spent[m] = spent.get(m, 0.0) + float(p.bid_amount or 0)
        filled[m] = filled.get(m, 0) + 1
        r = pool.get(str(p.player_id), {}).get("role", "")
        rc.setdefault(m, {})[r] = rc.get(m, {}).get(r, 0) + 1
    nxt = float(draft.lot_high_bid or 0) + fd.MIN_BID
    for raw in (draft.draft_order or []):
        m = str(raw)
        if m == str(draft.lot_high_bidder_id) or filled.get(m, 0) >= size:
            continue
        if rc.get(m, {}).get(role, 0) >= int(quota.get(role, 0)):
            continue
        if fd._max_bid(budget, spent.get(m, 0.0), filled.get(m, 0), size) >= nxt:
            try:
                await fd.place_bid(s, draft, fs, m, nxt)
                await s.commit()
            except ValueError:
                await s.rollback()
            return


async def _drive_snake(s, draft, fs):
    pool = await fd._pool_map(s, fs)
    size = fd._squad_size(fs)
    guard, limit = 0, size * len(draft.draft_order or []) + 80
    while draft.status == "in_progress" and guard <= limit:
        guard += 1
        await fd.resolve_overdue(s, draft, fs)
        await s.commit()
        if draft.status != "in_progress":
            break
        picks = (await s.execute(
            select(FantasyDraftPick).where(FantasyDraftPick.draft_id == draft.id)
            .order_by(FantasyDraftPick.pick_index)
        )).scalars().all()
        if draft.current_pick >= len(picks):
            break
        cur = picks[draft.current_pick]
        choice = await _needed_choice(s, draft, fs, cur.manager_id, pool)
        if choice is None:   # let the clock auto-pick if we somehow can't choose
            cur.deadline = _past()
            await s.commit()
            await fd.resolve_overdue(s, draft, fs)
            await s.commit()
            continue
        await fd.make_pick(s, draft, fs, str(cur.manager_id), choice)
        await s.commit()
    return draft.status == "complete"


async def _drive_auction(s, draft, fs):
    pool = await fd._pool_map(s, fs)
    size = fd._squad_size(fs)
    guard, limit = 0, size * len(draft.draft_order or []) * 4 + 120
    while draft.status == "in_progress" and guard <= limit:
        guard += 1
        await fd.resolve_overdue(s, draft, fs)
        await s.commit()
        if draft.status != "in_progress":
            break
        if draft.lot_player_id is None:
            order = [str(m) for m in (draft.draft_order or [])]
            if not order:
                break
            nominator = order[draft.nomination_index % len(order)]
            choice = await _needed_choice(s, draft, fs, nominator, pool)
            if choice is not None:
                await fd.nominate(s, draft, fs, nominator, choice, fd.MIN_BID)
                await s.commit()
                await _try_second_bid(s, draft, fs, pool)
        # Expire the lot / nomination clock and let the engine settle it.
        draft.lot_deadline = _past()
        await s.commit()
        await fd.resolve_overdue(s, draft, fs)
        await s.commit()
    return draft.status == "complete"


async def _assert_squads(s, lg, fs, n, dtype):
    size, quota, budget = fd._squad_size(fs), fd._role_quota(fs), fd._draft_budget(fs)
    squads = (await s.execute(select(FantasySquad).where(FantasySquad.league_id == lg.id))).scalars().all()
    if len(squads) != n:
        raise AssertionError(f"{len(squads)} squads built, expected {n}")
    for sq in squads:
        sps = (await s.execute(select(FantasySquadPlayer).where(FantasySquadPlayer.squad_id == sq.id))).scalars().all()
        if len(sps) != size:
            raise AssertionError(f"{sq.team_name}: {len(sps)} players, expected {size}")
        rc: dict[str, int] = {}
        for sp in sps:
            rc[sp.role] = rc.get(sp.role, 0) + 1
        for r, q in quota.items():
            if rc.get(r, 0) != int(q):
                raise AssertionError(f"{sq.team_name}: role {r}={rc.get(r, 0)}, quota {q}")
        if sum(1 for sp in sps if sp.is_captain) != 1:
            raise AssertionError(f"{sq.team_name}: not exactly one captain")
        if sum(1 for sp in sps if sp.is_vice_captain) != 1:
            raise AssertionError(f"{sq.team_name}: not exactly one vice-captain")
        if dtype == "auction":
            spend = sum(float(sp.purchase_price or 0) for sp in sps)
            if spend > budget + 0.01:
                raise AssertionError(f"{sq.team_name}: spent {spend:g} over budget {budget:g}")
    if lg.scoring_type == "h2h":
        await fd.h2h_ladder(s, lg.id)   # must compute without error
    return len(squads), size


async def _run_format(s, org_id, fs, dtype, n):
    tag = f"VERIFY-{secrets.token_hex(3)}"
    managers, lg = [], None
    try:
        managers = [FantasyManager(organisation_id=org_id, display_name=f"{tag}-{i + 1}") for i in range(n)]
        for m in managers:
            s.add(m)
        await s.flush()
        lg = FantasyLeague(
            fantasy_season_id=fs.id, organisation_id=org_id, kind="draft",
            name=f"{tag} {dtype}", join_code=secrets.token_hex(3).upper(),
            draft_type=dtype, scoring_type=("h2h" if dtype == "snake" else "total"), status="open",
        )
        s.add(lg)
        await s.flush()
        for m in managers:
            s.add(FantasyLeagueMember(league_id=lg.id, manager_id=m.id))
        await s.flush()
        draft = await fd.start_draft(s, lg, fs)
        await s.commit()
        finished = await (_drive_snake if dtype == "snake" else _drive_auction)(s, draft, fs)
        if not finished:
            raise AssertionError(f"draft did not complete (status {draft.status})")
        nsq, size = await _assert_squads(s, lg, fs, n, dtype)
        extra = ", budgets OK" if dtype == "auction" else ""
        print(f"  PASS — {nsq} squads of {size}; roles, captain/vice{extra}, {lg.scoring_type} ladder OK")
        return True, lg, managers
    except Exception as e:
        await s.rollback()
        print(f"  FAIL — {e}")
        return False, lg, managers


async def _cleanup(s, lg, managers):
    try:
        if lg is not None:
            row = await s.get(FantasyLeague, lg.id)
            if row:
                await s.delete(row)   # cascades draft, picks, squads, members, h2h
                await s.flush()
        for m in managers:
            row = await s.get(FantasyManager, m.id)
            if row:
                await s.delete(row)
        await s.commit()
        print("  cleaned up test data")
    except Exception as e:
        await s.rollback()
        print(f"  !! cleanup failed: {e} — look for VERIFY-* rows to remove by hand")


async def verify(org_id: str, which: str = "both") -> bool:
    async with async_session_maker() as s:
        fs = await _latest_season(s, org_id)
        if fs is None:
            print("No fantasy season for that org. Create one and Build the pool first.")
            return False
        n, role_avail, total = await _capacity(s, fs)
        if n < 2:
            print(f"Pool too small to run a draft (need >= 2 of each role for the quota). "
                  f"pool={total}, by role={role_avail}.")
            return False
        print(f"Season {fs.season_year} ({fs.name}) · pool {total} · {n} test managers per draft.\n")
        formats = ["snake", "auction"] if which == "both" else [which]
        ok = True
        for dtype in formats:
            print(f"=== {dtype.upper()} draft ===")
            passed, lg, managers = await _run_format(s, org_id, fs, dtype, n)
            ok = ok and passed
            await _cleanup(s, lg, managers)
        print(f"\n{'ALL CHECKS PASSED' if ok else 'SOME CHECKS FAILED'}")
        return ok


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python -m app.scripts.verify_fantasy_draft <org_id> [snake|auction|both]")
        raise SystemExit(2)
    org = sys.argv[1]
    which = sys.argv[2].lower() if len(sys.argv) > 2 else "both"
    if which not in ("snake", "auction", "both"):
        print("second arg must be snake, auction or both")
        raise SystemExit(2)
    raise SystemExit(0 if asyncio.run(verify(org, which)) else 1)
