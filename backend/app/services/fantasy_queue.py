"""BetterFantasyCricket transfers made after a round locks.

Once a round has locked, a manager's XI, captain and chips are frozen until it is
scored. A transfer made in that window is QUEUED (``fantasy_queued_transfers``) and
carried out when the round is scored, at the prices AFTER settlement (see
``fantasy_pricing``), and counts as a transfer for the round after it.

The squad's picks are not touched while a transfer waits, so the locked round is
scored with exactly the XI that was locked (settlement scores the live picks and
only then carries the queue out). Carrying out is idempotent: a queued transfer is
carried out once, whichever settle reaches it first, and a re-settle of a scored
round finds nothing pending.

Rules at carry-out time (the prices have moved, so they are checked then):
  * the player going out must still be in the team and the one coming in must not
    be, still be in the pool and available, and be the same role;
  * the bank after the swap must not be below zero;
  * a free transfer is used when the squad has one (settlement has just banked the
    round's), else the transfer hit applies, against the round the transfer counts in;
  * the armband passes with the player: if the one going out was captain or vice,
    the one coming in takes it, because the locked round has to be scored first and
    the manager can only change it after that.
A transfer that fails a check is cancelled with a reason the manager can read, never
silently dropped. Unsettling a round puts its carried-out transfers back in the queue
(``revert_applied``) so the round can be scored again with the XI it had.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import (
    FantasyPoolPlayer, FantasyQueuedTransfer, FantasyRound, FantasySquad,
    FantasySquadPlayer, FantasyTransaction,
)
from app.services import fantasy_squad
from app.services.fantasy_scoring import DEFAULT_RULES

logger = logging.getLogger(__name__)


class QueueError(Exception):
    """A queued transfer the rules refuse; the message is shown to the manager."""


def _f(x) -> float:
    return float(x) if x is not None else 0.0


async def _pool(session: AsyncSession, season_id, player_id) -> FantasyPoolPlayer | None:
    return (await session.execute(
        select(FantasyPoolPlayer).where(
            FantasyPoolPlayer.fantasy_season_id == season_id, FantasyPoolPlayer.player_id == player_id)
    )).scalar_one_or_none()


async def pending_for_round(session: AsyncSession, squad_id, round_id) -> list[FantasyQueuedTransfer]:
    return list((await session.execute(
        select(FantasyQueuedTransfer).where(
            FantasyQueuedTransfer.squad_id == squad_id, FantasyQueuedTransfer.after_round_id == round_id,
            FantasyQueuedTransfer.status == "pending",
        ).order_by(FantasyQueuedTransfer.created_at)
    )).scalars().all())


async def queue_transfer(session: AsyncSession, season, squad, rnd, out_player_id: str, in_player_id: str) -> dict:
    """Queue a swap behind the locked round ``rnd``. Raises QueueError for a swap the
    rules refuse. Returns the queued row's id and a ``warning`` when, at today's
    prices, the bank would not cover it (it is still queued: prices move)."""
    sps = (await session.execute(
        select(FantasySquadPlayer).where(FantasySquadPlayer.squad_id == squad.id)
    )).scalars().all()
    out_sp = next((s for s in sps if str(s.player_id) == str(out_player_id)), None)
    if out_sp is None:
        raise QueueError("That player isn't in your squad.")
    if any(str(s.player_id) == str(in_player_id) for s in sps):
        raise QueueError("You already have that player.")
    waiting = await pending_for_round(session, squad.id, rnd.id)
    if any(str(q.out_player_id) == str(out_player_id) for q in waiting):
        raise QueueError("You have already queued a transfer for that player.")
    if any(str(q.in_player_id) == str(in_player_id) for q in waiting):
        raise QueueError("You have already queued that player in.")
    in_pool = await _pool(session, season.id, in_player_id)
    if in_pool is None or not in_pool.is_available:
        raise QueueError("That player isn't available.")
    if in_pool.role != out_sp.role:
        raise QueueError(f"Transfers must be like-for-like by role ({out_sp.role}).")

    out_pool = await _pool(session, season.id, out_player_id)
    sell_now = _f(out_pool.current_price) if out_pool else _f(out_sp.purchase_price)
    q = FantasyQueuedTransfer(
        fantasy_season_id=season.id, squad_id=squad.id, after_round_id=rnd.id,
        out_player_id=out_player_id, in_player_id=in_player_id, status="pending",
    )
    session.add(q)
    await session.flush()

    # An estimate at today's prices over everything now queued, so the manager is
    # told early. It is a warning, not a refusal: the prices move at settlement.
    bank = _f(squad.budget_remaining)
    for w in waiting + [q]:
        o = await _pool(session, season.id, w.out_player_id)
        i = await _pool(session, season.id, w.in_player_id)
        sp_out = next((s for s in sps if s.player_id == w.out_player_id), None)
        bank += (_f(o.current_price) if o else _f(sp_out.purchase_price if sp_out else 0)) - (_f(i.current_price) if i else 0)
    warning = None
    if bank < -1e-6:
        warning = (f"At today's prices this is {abs(bank):.1f} over your budget. Prices move when the round is "
                   f"scored; if you still can't afford it then, the transfer is cancelled.")
    return {"id": str(q.id), "warning": warning, "sell_now": round(sell_now, 1)}


async def cancel_queued(session: AsyncSession, squad, queued_id: str) -> bool:
    """The manager withdraws a transfer that has not happened yet. The row is kept,
    marked cancelled."""
    q = await session.get(FantasyQueuedTransfer, queued_id)
    if q is None or q.squad_id != squad.id or q.status != "pending":
        return False
    q.status, q.reason = "cancelled", "Cancelled by you."
    return True


async def apply_pending(session: AsyncSession, fs) -> dict:
    """Carry out every queued transfer whose round is now scored, at current prices.
    Call after a round's prices have been recomputed. Returns counts."""
    rows = (await session.execute(
        select(FantasyQueuedTransfer).join(FantasyRound, FantasyRound.id == FantasyQueuedTransfer.after_round_id)
        .where(FantasyQueuedTransfer.fantasy_season_id == fs.id, FantasyQueuedTransfer.status == "pending",
               FantasyRound.status == "scored")
        .order_by(FantasyQueuedTransfer.created_at)
    )).scalars().all()
    if not rows:
        return {"applied": 0, "cancelled": 0}
    # The round the transfers count in: the first one that is not scored.
    nxt = (await session.execute(
        select(FantasyRound).where(FantasyRound.fantasy_season_id == fs.id, FantasyRound.status != "scored")
        .order_by(FantasyRound.round_number).limit(1)
    )).scalar_one_or_none()
    rules = fs.rules or DEFAULT_RULES
    hit_points = int(rules.get("transfer_hit", DEFAULT_RULES["transfer_hit"]))
    applied = cancelled = 0
    now = datetime.now(timezone.utc)

    def cancel(q, reason):
        q.status, q.reason = "cancelled", reason

    async def attempt(q):
        """Carry out one queued swap. Returns "applied", "cancelled", or a shortfall
        message when only the budget stops it: the swap is left pending so the others
        can free money first (a manager who queued two sales to afford one dearer pick)."""
        nonlocal applied, cancelled
        squad = await session.get(FantasySquad, q.squad_id)
        if squad is None:
            cancel(q, "The team no longer exists.")
            cancelled += 1
            return "cancelled"
        sps = (await session.execute(
            select(FantasySquadPlayer).where(FantasySquadPlayer.squad_id == squad.id)
        )).scalars().all()
        out_sp = next((s for s in sps if s.player_id == q.out_player_id), None)
        if out_sp is None:
            cancel(q, "The player going out is no longer in your team.")
            cancelled += 1
            return "cancelled"
        if any(s.player_id == q.in_player_id for s in sps):
            cancel(q, "The player coming in is already in your team.")
            cancelled += 1
            return "cancelled"
        in_pool = await _pool(session, fs.id, q.in_player_id)
        if in_pool is None or not in_pool.is_available:
            cancel(q, "The player coming in is no longer available.")
            cancelled += 1
            return "cancelled"
        if in_pool.role != out_sp.role:
            cancel(q, "The player coming in is no longer the same role.")
            cancelled += 1
            return "cancelled"
        out_pool = await _pool(session, fs.id, q.out_player_id)
        sell = round(_f(out_pool.current_price) if out_pool else _f(out_sp.purchase_price), 1)
        buy = round(_f(in_pool.current_price), 1)
        bank = _f(squad.budget_remaining) + sell - buy
        if bank < -1e-6:
            return (f"After the round's price changes you were {abs(bank):.1f} short (sold for {sell:.1f}, "
                    f"{buy:.1f} to buy).")

        if squad.free_transfers and squad.free_transfers > 0:
            squad.free_transfers -= 1
            hit, free_used = 0, True
        else:
            hit, free_used = hit_points, False
        q.out_purchase_price, q.out_added_round = out_sp.purchase_price, out_sp.added_round
        q.out_was_captain, q.out_was_vice = bool(out_sp.is_captain), bool(out_sp.is_vice_captain)
        await session.delete(out_sp)
        session.add(FantasySquadPlayer(
            squad_id=squad.id, player_id=q.in_player_id, role=in_pool.role,
            is_captain=q.out_was_captain, is_vice_captain=q.out_was_vice,
            purchase_price=buy, added_round=nxt.round_number if nxt else None,
        ))
        squad.budget_remaining = round(bank, 1)
        session.add(FantasyTransaction(
            squad_id=squad.id, league_id=squad.league_id, round_id=nxt.id if nxt else None,
            type="transfer_out", player_id=q.out_player_id, price=sell, detail={"queued": str(q.id)}))
        session.add(FantasyTransaction(
            squad_id=squad.id, league_id=squad.league_id, round_id=nxt.id if nxt else None,
            type="transfer_in", player_id=q.in_player_id, price=buy, detail={"queued": str(q.id)}))
        await session.flush()
        await fantasy_squad.record_round_transfer(session, squad.id, nxt, hit)
        q.status, q.reason, q.applied_at = "applied", None, now
        q.sell_value, q.buy_price, q.hit, q.free_used = sell, buy, hit, free_used
        q.applied_round_number = nxt.round_number if nxt else None
        applied += 1
        return "applied"

    # A swap that only the budget stops waits for the rest of the squad's queue to go
    # first; it is cancelled only when a whole pass applies nothing new.
    todo = list(rows)
    while todo:
        short, progress = [], False
        for q in todo:
            r = await attempt(q)
            if r in ("applied", "cancelled"):
                progress = True
            else:
                short.append((q, r))
        if not progress:
            for q, msg in short:
                cancel(q, msg)
                cancelled += 1
            break
        todo = [q for q, _ in short]
    await session.flush()
    if applied:
        await fantasy_squad.recount_ownership(session, fs.id)
    return {"applied": applied, "cancelled": cancelled}


async def revert_applied(session: AsyncSession, fs, rnd) -> dict:
    """Put back the transfers that were carried out when ``rnd`` was scored, because
    it is being unsettled and will be scored again with the XI it had. A transfer is
    put back only when it is safe: the player who came in is still in the team and the
    one who went out is not. Otherwise it is left as it happened and counted in
    ``kept`` so the admin can be told. Returns {"reverted", "kept"}."""
    rows = (await session.execute(
        select(FantasyQueuedTransfer).where(
            FantasyQueuedTransfer.after_round_id == rnd.id, FantasyQueuedTransfer.status == "applied")
        .order_by(FantasyQueuedTransfer.applied_at.desc(), FantasyQueuedTransfer.created_at.desc())
    )).scalars().all()
    reverted = kept = 0
    for q in rows:
        squad = await session.get(FantasySquad, q.squad_id)
        sps = (await session.execute(
            select(FantasySquadPlayer).where(FantasySquadPlayer.squad_id == q.squad_id)
        )).scalars().all() if squad is not None else []
        in_sp = next((s for s in sps if s.player_id == q.in_player_id), None)
        if squad is None or in_sp is None or any(s.player_id == q.out_player_id for s in sps):
            kept += 1
            continue
        await session.delete(in_sp)
        session.add(FantasySquadPlayer(
            squad_id=squad.id, player_id=q.out_player_id, role=in_sp.role,
            is_captain=bool(in_sp.is_captain), is_vice_captain=bool(in_sp.is_vice_captain),
            purchase_price=q.out_purchase_price, added_round=q.out_added_round,
        ))
        squad.budget_remaining = round(_f(squad.budget_remaining) - _f(q.sell_value) + _f(q.buy_price), 1)
        if q.free_used:
            squad.free_transfers = (squad.free_transfers or 0) + 1
        if q.applied_round_number is not None:
            await session.execute(
                text("""UPDATE fantasy_squad_round_scores srs SET
                            transfers_made = GREATEST(srs.transfers_made - 1, 0),
                            transfer_hit = GREATEST(srs.transfer_hit - :hit, 0)
                        FROM fantasy_rounds r
                        WHERE srs.round_id = r.id AND r.fantasy_season_id = CAST(:fs AS UUID)
                          AND r.round_number = :n AND srs.squad_id = CAST(:sq AS UUID)"""),
                {"fs": str(fs.id), "n": q.applied_round_number, "sq": str(squad.id), "hit": int(q.hit or 0)})
        session.add(FantasyTransaction(
            squad_id=squad.id, league_id=squad.league_id, type="transfer_undone", player_id=q.in_player_id,
            price=q.buy_price, detail={"queued": str(q.id), "reason": "round unsettled"}))
        q.status, q.applied_at, q.applied_round_number = "pending", None, None
        q.sell_value = q.buy_price = None
        q.hit, q.free_used = 0, False
        reverted += 1
    await session.flush()
    if reverted:
        await fantasy_squad.recount_ownership(session, fs.id)
    return {"reverted": reverted, "kept": kept}
