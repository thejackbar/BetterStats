"""BetterFantasyCricket draft engine — snake & auction drafts, waivers, trades, h2h.

A draft league owns its players uniquely. Both formats run async over a window:

- **Snake**: every pick slot is laid out up front (turns reverse each round). Each
  pick has a clock; if it lapses the system auto-picks the manager's top wishlist
  player, or the best available that still fits their role quota.
- **Auction**: managers take turns nominating a player and opening the bidding;
  others bid up within their budget and role needs; the highest bid when the
  lot's anti-snipe clock lapses wins. The nominator is the opening high bidder, so
  an uncontested lot is won by whoever nominated it (the clock never deadlocks).
  Each manager's budget is derived from the lots they've already won — no extra
  table. If a nominator's clock lapses, the system auto-nominates their top
  wishlist player (or the best available in a role they still need) at the minimum
  bid. A manager's max bid is always held back so they can still fill every empty
  slot at the minimum.

When the draft fills, each manager's picks become a squad and the league plays out
on a total-points or head-to-head ladder, with a waiver wire and manager-to-manager
trades. Full design: docs/betterfantasycricket.md.

NOTE: not exercised in the build sandbox (no database). Verify on a deploy.
"""
from __future__ import annotations

import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import (
    FantasyDraft, FantasyDraftPick, FantasyDraftWishlist, FantasyLeague,
    FantasyLeagueMember, FantasyManager, FantasyPoolPlayer, FantasyRound,
    FantasySquad, FantasySquadPlayer, FantasyH2HFixture, FantasyWaiverClaim,
    FantasyTrade, Player,
)
from app.services.fantasy_scoring import DEFAULT_RULES

H2H_WIN, H2H_DRAW = 4, 2

# Auction floor bid (credits). A manager's max bid is held back by MIN_BID per
# still-empty slot so they can never strand themselves with an unfillable squad.
MIN_BID = 1.0
# Default per-lot clock for an auction (seconds); shorter than the snake per-pick
# clock since an auction has far more lots. Tunable via rules["auction_lot_seconds"].
DEFAULT_LOT_SECONDS = 3600


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _squad_size(fs) -> int:
    return int((fs.rules or DEFAULT_RULES).get("squad_size", 12))


def _role_quota(fs) -> dict:
    return (fs.rules or DEFAULT_RULES).get("role_quota", DEFAULT_RULES["role_quota"])


def _draft_budget(fs) -> float:
    """An auction manager's spend budget. Defaults to the salary-cap budget."""
    rules = fs.rules or DEFAULT_RULES
    return float(rules.get("draft_budget") or rules.get("budget") or DEFAULT_RULES["budget"])


async def _pool_map(session: AsyncSession, fs) -> dict[str, dict]:
    rows = (await session.execute(
        select(FantasyPoolPlayer.player_id, FantasyPoolPlayer.role, FantasyPoolPlayer.current_price)
        .where(FantasyPoolPlayer.fantasy_season_id == fs.id, FantasyPoolPlayer.is_available.is_(True))
    )).all()
    return {str(pid): {"role": role, "price": float(price)} for pid, role, price in rows}


async def _league_members(session: AsyncSession, league_id) -> list[str]:
    rows = (await session.execute(
        select(FantasyLeagueMember.manager_id).where(FantasyLeagueMember.league_id == league_id)
    )).scalars().all()
    return [str(m) for m in rows]


# ── Start the draft ────────────────────────────────────────────────────────────

async def start_draft(session: AsyncSession, league: FantasyLeague, fs) -> FantasyDraft:
    """Create the draft, shuffle the order and open it. Snake lays out every pick
    slot up front; auction sets the nomination pointer and the first lot clock."""
    dtype = league.draft_type or "snake"
    if dtype not in ("snake", "auction"):
        raise ValueError("Unknown draft type.")
    existing = (await session.execute(
        select(FantasyDraft).where(FantasyDraft.league_id == league.id)
    )).scalar_one_or_none()
    if existing is not None and existing.status != "scheduled":
        raise ValueError("The draft has already started.")

    members = await _league_members(session, league.id)
    if len(members) < 2:
        raise ValueError("Need at least two managers to draft.")
    rules = fs.rules or DEFAULT_RULES
    rounds = int(rules.get("squad_size", 12))
    order = list(members)
    random.shuffle(order)

    draft = existing or FantasyDraft(league_id=league.id, organisation_id=league.organisation_id)
    draft.type = dtype
    draft.status = "in_progress"
    draft.current_pick = 0
    draft.draft_order = order
    draft.rounds = rounds
    draft.started_at = _now()
    if existing is None:
        session.add(draft)

    if dtype == "auction":
        draft.pick_seconds = int(rules.get("auction_lot_seconds") or DEFAULT_LOT_SECONDS)
        draft.nomination_index = 0
        draft.lot_player_id = None
        draft.lot_high_bid = None
        draft.lot_high_bidder_id = None
        draft.lot_nominator_id = None
        draft.lot_auto = False
        draft.lot_max_bids = {}
        # The first nominator's clock starts now; if they don't nominate in time,
        # resolve_overdue auto-nominates for them.
        draft.lot_deadline = _now() + timedelta(seconds=draft.pick_seconds)
        await session.flush()
        league.status = "drafting"
        return draft

    draft.pick_seconds = int(getattr(draft, "pick_seconds", None) or 14400)
    await session.flush()
    idx = 0
    for r in range(rounds):
        seq = order if r % 2 == 0 else list(reversed(order))
        for mid in seq:
            session.add(FantasyDraftPick(
                draft_id=draft.id, pick_index=idx, round_no=r, manager_id=mid,
                deadline=(_now() + timedelta(seconds=draft.pick_seconds)) if idx == 0 else None,
            ))
            idx += 1
    league.status = "drafting"
    return draft


# ── Picks + auto-pick ──────────────────────────────────────────────────────────

async def _draft_state(session: AsyncSession, draft: FantasyDraft):
    picks = (await session.execute(
        select(FantasyDraftPick).where(FantasyDraftPick.draft_id == draft.id)
        .order_by(FantasyDraftPick.pick_index)
    )).scalars().all()
    taken = {str(p.player_id) for p in picks if p.player_id}
    role_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    return picks, taken, role_counts


def _role_full(role_counts, manager_id, role, quota) -> bool:
    return role_counts[str(manager_id)][role] >= int(quota.get(role, 0))


async def _auto_choice(session, draft, fs, manager_id, taken, role_counts, pool, quota) -> str | None:
    """The auto-pick: the manager's top wishlist player that's free and fits a
    role they still need, else the most expensive such player in the pool."""
    wl = (await session.execute(
        select(FantasyDraftWishlist.player_ids).where(
            FantasyDraftWishlist.draft_id == draft.id, FantasyDraftWishlist.manager_id == manager_id)
    )).scalar_one_or_none() or []
    for pid in wl:
        pid = str(pid)
        if pid in pool and pid not in taken and not _role_full(role_counts, manager_id, pool[pid]["role"], quota):
            return pid
    best = sorted(
        (p for p in pool.items() if p[0] not in taken and not _role_full(role_counts, manager_id, p[1]["role"], quota)),
        key=lambda kv: kv[1]["price"], reverse=True,
    )
    return best[0][0] if best else None


async def resolve_overdue(session: AsyncSession, draft: FantasyDraft, fs) -> None:
    """Advance any clock that has lapsed, walking forward until the draft is caught
    up (or finished). Safe to call on every draft view and from the scheduler."""
    if draft.status != "in_progress":
        return
    if draft.type == "auction":
        await _resolve_auction(session, draft, fs)
        return
    rules = fs.rules or DEFAULT_RULES
    quota = rules.get("role_quota", DEFAULT_RULES["role_quota"])
    pool = await _pool_map(session, fs)
    picks, taken, role_counts = await _draft_state(session, draft)
    for p in picks:
        if p.player_id:
            role_counts[str(p.manager_id)][pool.get(str(p.player_id), {}).get("role", "")] += 1

    guard = 0
    while draft.current_pick < len(picks) and guard <= len(picks):
        guard += 1
        cur = picks[draft.current_pick]
        if cur.player_id is not None:
            draft.current_pick += 1
            continue
        if not cur.deadline or _now() <= cur.deadline:
            break  # current pick still on the clock
        choice = await _auto_choice(session, draft, fs, cur.manager_id, taken, role_counts, pool, quota)
        if choice is None:
            break
        cur.player_id = choice
        cur.picked_at = _now()
        cur.auto_picked = True
        taken.add(choice)
        role_counts[str(cur.manager_id)][pool[choice]["role"]] += 1
        draft.current_pick += 1
        if draft.current_pick < len(picks):
            picks[draft.current_pick].deadline = _now() + timedelta(seconds=draft.pick_seconds)
    if draft.current_pick >= len(picks):
        await finalize_draft(session, draft, fs)


async def make_pick(session: AsyncSession, draft: FantasyDraft, fs, manager_id: str, player_id: str) -> None:
    await resolve_overdue(session, draft, fs)
    if draft.type == "auction":
        raise ValueError("This is an auction draft, nominate a player and bid instead.")
    if draft.status != "in_progress":
        raise ValueError("The draft isn't running.")
    rules = fs.rules or DEFAULT_RULES
    quota = rules.get("role_quota", DEFAULT_RULES["role_quota"])
    pool = await _pool_map(session, fs)
    picks, taken, role_counts = await _draft_state(session, draft)
    for p in picks:
        if p.player_id:
            role_counts[str(p.manager_id)][pool.get(str(p.player_id), {}).get("role", "")] += 1

    cur = picks[draft.current_pick]
    if str(cur.manager_id) != str(manager_id):
        raise ValueError("It's not your turn to pick.")
    pid = str(player_id)
    if pid not in pool:
        raise ValueError("That player isn't in the pool.")
    if pid in taken:
        raise ValueError("That player has already been drafted.")
    if _role_full(role_counts, manager_id, pool[pid]["role"], quota):
        raise ValueError(f"You already have enough {pool[pid]['role']}s.")

    cur.player_id = pid
    cur.picked_at = _now()
    draft.current_pick += 1
    if draft.current_pick < len(picks):
        picks[draft.current_pick].deadline = _now() + timedelta(seconds=draft.pick_seconds)
        # If the next manager is also overdue (rare), let resolve catch up.
        await resolve_overdue(session, draft, fs)
    else:
        await finalize_draft(session, draft, fs)


# ── Auction ──────────────────────────────────────────────────────────────────

async def _auction_state(session: AsyncSession, draft: FantasyDraft, fs):
    """Derive the auction's live state from the settled lots: the player pool, the
    won lots, and per-manager spend / squad-fill / role counts. Budget is derived
    here from the won lots, so there's no per-manager budget row to keep in sync."""
    pool = await _pool_map(session, fs)
    picks = (await session.execute(
        select(FantasyDraftPick).where(FantasyDraftPick.draft_id == draft.id)
        .order_by(FantasyDraftPick.pick_index)
    )).scalars().all()
    spent: dict[str, float] = defaultdict(float)
    filled: dict[str, int] = defaultdict(int)
    role_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for p in picks:
        if not p.player_id:
            continue
        mid = str(p.manager_id)
        spent[mid] += float(p.bid_amount or 0)
        filled[mid] += 1
        role_counts[mid][pool.get(str(p.player_id), {}).get("role", "")] += 1
    taken = {str(p.player_id) for p in picks if p.player_id}
    return pool, picks, taken, spent, filled, role_counts


def _max_bid(budget: float, spent: float, filled: int, squad_size: int) -> float:
    """The most a manager can bid on the current lot and still afford to fill every
    remaining slot at the floor bid. <= 0 means they can't bid."""
    slots_left = squad_size - filled
    if slots_left <= 0:
        return 0.0
    return round(budget - spent - (slots_left - 1) * MIN_BID, 1)


def _resolve_lot(maxes: dict, incumbent) -> tuple:
    """eBay-style proxy resolution. Given each contender's max bid for the lot,
    return ``(leader_id, price)``: the leader is the highest max (the incumbent
    keeps the lead on an exact tie), and the price is the runner-up's max plus the
    increment, capped at the leader's max. A sole contender pays their own max
    (the nominator's opening). ``maxes`` keys are manager-id strings."""
    if not maxes:
        return None, 0.0
    top = max(maxes.values())
    tied = sorted(m for m, v in maxes.items() if v == top)
    leader = str(incumbent) if incumbent is not None and str(incumbent) in tied else tied[0]
    others = [v for m, v in maxes.items() if m != leader]
    if not others:
        return leader, round(float(maxes[leader]), 1)
    second = max(others)
    return leader, round(min(float(maxes[leader]), float(second) + MIN_BID), 1)


def _needed_roles(role_counts_mid: dict, quota: dict) -> set[str]:
    return {r for r, q in quota.items() if role_counts_mid.get(r, 0) < int(q)}


def _can_take(mid, pool, taken, spent, filled, role_counts, quota, squad_size, budget) -> bool:
    """Can this manager still win another player — a free role slot, an available
    player to fill it, and enough budget for the floor bid?"""
    if filled.get(mid, 0) >= squad_size:
        return False
    if _max_bid(budget, spent.get(mid, 0.0), filled.get(mid, 0), squad_size) < MIN_BID:
        return False
    needed = _needed_roles(role_counts.get(mid, {}), quota)
    if not needed:
        return False
    return any(v["role"] in needed for pid, v in pool.items() if pid not in taken)


def _current_nominator(draft, order, pool, taken, spent, filled, role_counts, quota, squad_size, budget):
    """Walk draft_order from nomination_index to the next manager who can still take
    a player, leaving nomination_index pointing at them. None ⇒ everyone is done."""
    n = len(order)
    if n == 0:
        return None
    for _ in range(n):
        draft.nomination_index %= n
        mid = str(order[draft.nomination_index])
        if _can_take(mid, pool, taken, spent, filled, role_counts, quota, squad_size, budget):
            return mid
        draft.nomination_index += 1
    return None


async def _wishlist(session, draft, manager_id) -> list[str]:
    wl = (await session.execute(
        select(FantasyDraftWishlist.player_ids).where(
            FantasyDraftWishlist.draft_id == draft.id, FantasyDraftWishlist.manager_id == manager_id)
    )).scalar_one_or_none() or []
    return [str(x) for x in wl]


async def _auto_nominee(session, draft, manager_id, pool, taken, role_counts, quota) -> str | None:
    """Who to auto-nominate for a manager whose nomination clock lapsed: their top
    wishlist player in a role they still need, else the priciest such player."""
    needed = _needed_roles(role_counts.get(str(manager_id), {}), quota)

    def ok(pid):
        return pid in pool and pid not in taken and pool[pid]["role"] in needed

    for pid in await _wishlist(session, draft, manager_id):
        if ok(pid):
            return pid
    cands = sorted((pid for pid in pool if ok(pid)), key=lambda x: pool[x]["price"], reverse=True)
    return cands[0] if cands else None


async def _award_lot(session, draft, picks_count) -> None:
    """Settle the live lot to its high bidder, clear it and advance the nomination
    pointer. ``picks_count`` is the next pick_index."""
    winner = draft.lot_high_bidder_id
    auto = bool(draft.lot_auto) and str(winner) == str(draft.lot_nominator_id)
    n = len(draft.draft_order or []) or 1
    session.add(FantasyDraftPick(
        draft_id=draft.id, pick_index=picks_count, round_no=picks_count // n,
        manager_id=winner, player_id=draft.lot_player_id, picked_at=_now(),
        auto_picked=auto, bid_amount=float(draft.lot_high_bid or MIN_BID),
    ))
    draft.lot_player_id = None
    draft.lot_high_bid = None
    draft.lot_high_bidder_id = None
    draft.lot_nominator_id = None
    draft.lot_auto = False
    draft.lot_max_bids = {}
    draft.current_pick = picks_count + 1
    draft.nomination_index += 1   # nomination rotates to the next manager
    draft.lot_deadline = None
    await session.flush()


async def _resolve_auction(session: AsyncSession, draft: FantasyDraft, fs) -> None:
    """Advance the auction: award a lapsed lot, or auto-nominate for a nominator
    whose clock ran out, looping until it's live again or complete."""
    quota = _role_quota(fs)
    squad_size = _squad_size(fs)
    budget = _draft_budget(fs)
    order = draft.draft_order or []
    guard, limit = 0, squad_size * max(1, len(order)) + len(order) + 5
    while draft.status == "in_progress" and guard <= limit:
        guard += 1
        if draft.lot_player_id is not None:
            # A lot is live: award it if its clock has lapsed, else leave it.
            if draft.lot_deadline and _now() > draft.lot_deadline:
                _pool, picks, *_ = await _auction_state(session, draft, fs)
                await _award_lot(session, draft, len(picks))
                continue
            return
        # Awaiting a nomination: find who's up.
        pool, picks, taken, spent, filled, role_counts = await _auction_state(session, draft, fs)
        nominator = _current_nominator(draft, order, pool, taken, spent, filled, role_counts, quota, squad_size, budget)
        if nominator is None:
            await finalize_draft(session, draft, fs)
            return
        if not draft.lot_deadline:
            draft.lot_deadline = _now() + timedelta(seconds=draft.pick_seconds)
            return
        if _now() <= draft.lot_deadline:
            return   # nominator still on the clock
        # Nomination clock lapsed → auto-nominate at the floor bid.
        choice = await _auto_nominee(session, draft, nominator, pool, taken, role_counts, quota)
        if choice is None:   # defensive — _can_take already guaranteed one exists
            draft.nomination_index += 1
            draft.lot_deadline = _now() + timedelta(seconds=draft.pick_seconds)
            continue
        draft.lot_player_id = choice
        draft.lot_nominator_id = nominator
        draft.lot_high_bid = MIN_BID
        draft.lot_high_bidder_id = nominator
        draft.lot_auto = True
        draft.lot_max_bids = {str(nominator): float(MIN_BID)}
        draft.lot_deadline = _now() + timedelta(seconds=draft.pick_seconds)
        return


async def nominate(session: AsyncSession, draft: FantasyDraft, fs, manager_id: str, player_id: str, opening_bid: float | None = None) -> None:
    """The nominator puts a player up and opens the bidding, becoming the opening
    high bidder (so an uncontested lot is theirs)."""
    await resolve_overdue(session, draft, fs)
    if draft.type != "auction":
        raise ValueError("This isn't an auction draft.")
    if draft.status != "in_progress":
        raise ValueError("The auction isn't running.")
    if draft.lot_player_id is not None:
        raise ValueError("A player is already up for auction.")
    quota, squad_size, budget = _role_quota(fs), _squad_size(fs), _draft_budget(fs)
    pool, picks, taken, spent, filled, role_counts = await _auction_state(session, draft, fs)
    nominator = _current_nominator(draft, draft.draft_order or [], pool, taken, spent, filled, role_counts, quota, squad_size, budget)
    if nominator is None:
        await finalize_draft(session, draft, fs)
        raise ValueError("The auction is complete.")
    if str(nominator) != str(manager_id):
        raise ValueError("It's not your turn to nominate.")
    pid = str(player_id)
    if pid not in pool:
        raise ValueError("That player isn't in the pool.")
    if pid in taken:
        raise ValueError("That player has already been bought.")
    role = pool[pid]["role"]
    if role_counts[str(manager_id)].get(role, 0) >= int(quota.get(role, 0)):
        raise ValueError(f"You already have enough {role}s.")
    maxb = _max_bid(budget, spent.get(str(manager_id), 0.0), filled.get(str(manager_id), 0), squad_size)
    ob = float(opening_bid) if opening_bid is not None else MIN_BID
    if ob < MIN_BID:
        ob = MIN_BID
    if ob > maxb:
        raise ValueError(f"You can open at most {maxb:g} and still fill your squad.")
    draft.lot_player_id = pid
    draft.lot_nominator_id = manager_id
    draft.lot_high_bid = ob
    draft.lot_high_bidder_id = manager_id
    draft.lot_auto = False
    draft.lot_max_bids = {str(manager_id): ob}
    draft.lot_deadline = _now() + timedelta(seconds=draft.pick_seconds)


async def place_bid(session: AsyncSession, draft: FantasyDraft, fs, manager_id: str, amount: float) -> None:
    """Set your max bid on the live lot. Every bid is a proxy max: the system bids
    up to it, so the price settles at the runner-up's max plus the increment. Must
    clear the next bid and stay within your role quota and affordability."""
    await resolve_overdue(session, draft, fs)
    if draft.type != "auction":
        raise ValueError("This isn't an auction draft.")
    if draft.status != "in_progress":
        raise ValueError("The auction isn't running.")
    if draft.lot_player_id is None:
        raise ValueError("Nothing is up for auction right now.")
    mid = str(manager_id)
    amt = float(amount)
    maxes = dict(draft.lot_max_bids or {})
    own_max = float(maxes.get(mid, 0))
    min_next = round(float(draft.lot_high_bid or 0) + MIN_BID, 1)
    if amt < min_next:
        raise ValueError(f"Bid at least {min_next:g}.")
    if amt <= own_max:
        raise ValueError("You've already set a max that high.")
    quota, squad_size, budget = _role_quota(fs), _squad_size(fs), _draft_budget(fs)
    pool, picks, taken, spent, filled, role_counts = await _auction_state(session, draft, fs)
    if filled.get(mid, 0) >= squad_size:
        raise ValueError("Your squad is already full.")
    role = pool.get(str(draft.lot_player_id), {}).get("role", "")
    if role_counts[mid].get(role, 0) >= int(quota.get(role, 0)):
        raise ValueError(f"You already have enough {role}s.")
    maxb = _max_bid(budget, spent.get(mid, 0.0), filled.get(mid, 0), squad_size)
    if amt > maxb:
        raise ValueError(f"You can bid at most {maxb:g} and still fill your squad.")
    maxes[mid] = amt
    leader, price = _resolve_lot(maxes, draft.lot_high_bidder_id)
    draft.lot_max_bids = maxes
    draft.lot_high_bid = price
    draft.lot_high_bidder_id = leader
    # Anti-snipe: a fresh bid resets the lot clock so others get a chance to reply.
    draft.lot_deadline = _now() + timedelta(seconds=draft.pick_seconds)


async def auction_view(session: AsyncSession, draft: FantasyDraft, fs, manager_id: str) -> dict:
    """Member-facing auction board. Read-only — assumes resolve_overdue has already
    settled the live lot / nominator before this is called."""
    quota, squad_size, budget = _role_quota(fs), _squad_size(fs), _draft_budget(fs)
    pool, picks, taken, spent, filled, role_counts = await _auction_state(session, draft, fs)
    order = [str(m) for m in (draft.draft_order or [])]
    me = str(manager_id)

    mgr_names = {str(mid): nm for mid, nm in (await session.execute(
        select(FantasyManager.id, FantasyManager.display_name)
        .where(FantasyManager.organisation_id == draft.organisation_id))).all()}
    pnames = {str(pid): nm for pid, nm in (await session.execute(
        select(FantasyPoolPlayer.player_id, Player.name)
        .join(Player, Player.id == FantasyPoolPlayer.player_id)
        .where(FantasyPoolPlayer.fantasy_season_id == fs.id))).all()}

    def remaining(mid):
        return round(budget - spent.get(mid, 0.0), 1)

    lot = None
    if draft.lot_player_id is not None:
        lp = str(draft.lot_player_id)
        hb = str(draft.lot_high_bidder_id) if draft.lot_high_bidder_id else None
        high = float(draft.lot_high_bid or 0)
        role = pool.get(lp, {}).get("role", "")
        my_max = _max_bid(budget, spent.get(me, 0.0), filled.get(me, 0), squad_size)
        min_next = round(high + MIN_BID, 1)
        role_full = role_counts[me].get(role, 0) >= int(quota.get(role, 0))
        lot = {
            "player_id": lp, "name": pnames.get(lp, "?"), "role": role,
            "high_bid": high, "high_bidder": mgr_names.get(hb) if hb else None,
            "high_bidder_is_me": hb == me,
            "nominator": mgr_names.get(str(draft.lot_nominator_id)) if draft.lot_nominator_id else None,
            "auto": bool(draft.lot_auto),
            "deadline": draft.lot_deadline.isoformat() if draft.lot_deadline else None,
            "min_next_bid": min_next, "max_bid": my_max,
            "my_max": float((draft.lot_max_bids or {}).get(me, 0)) or None,
            "bidders": len(draft.lot_max_bids or {}),
            "i_can_bid": (hb != me) and (not role_full) and (filled.get(me, 0) < squad_size) and (my_max >= min_next),
        }

    nominator_mid = order[draft.nomination_index % len(order)] if (order and draft.lot_player_id is None and draft.status == "in_progress") else None

    my_picks = [(str(p.player_id), float(p.bid_amount or 0)) for p in picks if p.player_id and str(p.manager_id) == me]
    wl_ids = await _wishlist(session, draft, manager_id)
    return {
        "status": draft.status,
        "draft_type": "auction",
        "my_wishlist": [{"player_id": pid, "name": pnames.get(pid, "?"),
                         "role": pool.get(pid, {}).get("role", "")} for pid in wl_ids],
        "budget": round(budget, 1),
        "squad_size": squad_size,
        "quota": quota,
        "order": [mgr_names.get(m, "?") for m in order],
        "nominator": mgr_names.get(nominator_mid) if nominator_mid else None,
        "my_nomination": bool(nominator_mid and nominator_mid == me),
        "lot": lot,
        "my": {
            "spent": round(spent.get(me, 0.0), 1), "remaining": remaining(me),
            "filled": filled.get(me, 0),
            "max_bid": _max_bid(budget, spent.get(me, 0.0), filled.get(me, 0), squad_size),
            "needed": {r: int(q) - role_counts[me].get(r, 0) for r, q in quota.items()},
            "squad": [{"player_id": pid, "name": pnames.get(pid, "?"),
                       "role": pool.get(pid, {}).get("role", ""), "price": bid} for pid, bid in my_picks],
        },
        "managers": [{
            "manager_id": mid, "name": mgr_names.get(mid, "?"),
            "spent": round(spent.get(mid, 0.0), 1), "remaining": remaining(mid),
            "filled": filled.get(mid, 0), "is_me": mid == me,
            "done": filled.get(mid, 0) >= squad_size,
        } for mid in order],
        "available": sorted(
            [{"player_id": pid, "name": pnames.get(pid, "?"), "role": v["role"], "price": v["price"]}
             for pid, v in pool.items() if pid not in taken],
            key=lambda x: x["price"], reverse=True,
        ),
        "picks": [{
            "pick": p.pick_index + 1, "manager": mgr_names.get(str(p.manager_id), "?"),
            "player": pnames.get(str(p.player_id), "?") if p.player_id else None,
            "role": pool.get(str(p.player_id), {}).get("role", ""),
            "price": float(p.bid_amount or 0), "auto": bool(p.auto_picked),
        } for p in picks if p.player_id],
    }


# ── Finalise → squads, then optionally head-to-head fixtures ─────────────────────

async def finalize_draft(session: AsyncSession, draft: FantasyDraft, fs) -> None:
    league = await session.get(FantasyLeague, draft.league_id)
    pool = await _pool_map(session, fs)
    picks = (await session.execute(
        select(FantasyDraftPick).where(FantasyDraftPick.draft_id == draft.id)
    )).scalars().all()
    is_auction = draft.type == "auction"
    budget = _draft_budget(fs) if is_auction else None
    by_manager: dict[str, list] = defaultdict(list)   # mid -> [(player_id, bid), ...]
    for p in picks:
        if p.player_id:
            by_manager[str(p.manager_id)].append((str(p.player_id), float(p.bid_amount or 0)))

    squad_by_manager: dict[str, FantasySquad] = {}
    for mid, items in by_manager.items():
        mgr = await session.get(FantasyManager, mid)
        spent = sum(b for _, b in items)
        squad = FantasySquad(
            fantasy_season_id=fs.id, league_id=league.id, manager_id=mid,
            organisation_id=fs.organisation_id,
            team_name=f"{mgr.display_name if mgr else 'Team'}'s XI",
            budget_remaining=(round(budget - spent, 1) if is_auction else None),
        )
        session.add(squad)
        await session.flush()
        squad_by_manager[mid] = squad
        # Captain the marquee pick — the priciest bid (auction) or pool price (snake).
        ranked = sorted(items, key=(lambda it: it[1]) if is_auction else (lambda it: pool.get(it[0], {}).get("price", 0)), reverse=True)
        cap = ranked[0][0] if ranked else None
        vice = ranked[1][0] if len(ranked) > 1 else None
        for pid, bid in items:
            session.add(FantasySquadPlayer(
                squad_id=squad.id, player_id=pid, role=pool.get(pid, {}).get("role", "batter"),
                is_captain=(pid == cap), is_vice_captain=(pid == vice),
                purchase_price=(round(bid, 1) if is_auction else None),
            ))
        # Link the league member to their drafted squad.
        member = (await session.execute(
            select(FantasyLeagueMember).where(
                FantasyLeagueMember.league_id == league.id, FantasyLeagueMember.manager_id == mid)
        )).scalar_one_or_none()
        if member is not None:
            member.squad_id = squad.id

    draft.status = "complete"
    league.status = "active"
    if league.scoring_type == "h2h":
        await _generate_h2h(session, league, fs, squad_by_manager, draft.draft_order or list(by_manager.keys()))


async def _generate_h2h(session, league, fs, squad_by_manager, order) -> None:
    """Round-robin fixtures (circle method), mapped onto the season's rounds."""
    squads = [squad_by_manager[m].id for m in order if m in squad_by_manager]
    if len(squads) < 2:
        return
    if len(squads) % 2:
        squads.append(None)  # bye marker
    n = len(squads)
    schedule = []  # list of rounds, each a list of (home, away)
    arr = list(squads)
    for _ in range(n - 1):
        pairs = [(arr[i], arr[n - 1 - i]) for i in range(n // 2)]
        schedule.append(pairs)
        arr = [arr[0]] + [arr[-1]] + arr[1:-1]  # rotate, keeping the first fixed

    rounds = (await session.execute(
        select(FantasyRound).where(FantasyRound.fantasy_season_id == fs.id).order_by(FantasyRound.round_number)
    )).scalars().all()
    for i, rnd in enumerate(rounds):
        pairs = schedule[i % len(schedule)]
        for home, away in pairs:
            if home is None:
                continue
            session.add(FantasyH2HFixture(
                league_id=league.id, round_id=rnd.id, round_no=rnd.round_number,
                home_squad_id=home, away_squad_id=away,
            ))


async def settle_h2h(session: AsyncSession, fs, rnd) -> None:
    """Fill this round's head-to-head fixtures from the squad round scores. Called
    from engine.settle_round after squads are scored."""
    leagues = (await session.execute(
        select(FantasyLeague.id).where(
            FantasyLeague.fantasy_season_id == fs.id,
            FantasyLeague.kind == "draft", FantasyLeague.scoring_type == "h2h")
    )).scalars().all()
    if not leagues:
        return
    pts = dict((await session.execute(
        text("SELECT squad_id, points FROM fantasy_squad_round_scores WHERE round_id = CAST(:rid AS UUID)"),
        {"rid": str(rnd.id)},
    )).all())
    pts = {str(k): float(v) for k, v in pts.items()}
    fixtures = (await session.execute(
        select(FantasyH2HFixture).where(FantasyH2HFixture.round_id == rnd.id)
    )).scalars().all()
    for fx in fixtures:
        hp = pts.get(str(fx.home_squad_id), 0.0)
        ap = pts.get(str(fx.away_squad_id), 0.0) if fx.away_squad_id else None
        fx.home_points = hp
        fx.away_points = ap
        if ap is None:
            fx.result = "home"  # bye = a win
        else:
            fx.result = "home" if hp > ap else "away" if ap > hp else "draw"


async def h2h_ladder(session: AsyncSession, league_id) -> list[dict]:
    """Win-loss-draw ladder for a head-to-head draft league."""
    fixtures = (await session.execute(
        select(FantasyH2HFixture).where(
            FantasyH2HFixture.league_id == league_id, FantasyH2HFixture.result.isnot(None))
    )).scalars().all()
    rec: dict[str, dict] = defaultdict(lambda: {"w": 0, "l": 0, "d": 0, "pf": 0.0})
    for fx in fixtures:
        h, a = str(fx.home_squad_id), str(fx.away_squad_id) if fx.away_squad_id else None
        rec[h]["pf"] += float(fx.home_points or 0)
        if a:
            rec[a]["pf"] += float(fx.away_points or 0)
        if fx.result == "draw":
            rec[h]["d"] += 1
            if a: rec[a]["d"] += 1
        elif fx.result == "home":
            rec[h]["w"] += 1
            if a: rec[a]["l"] += 1
        elif fx.result == "away":
            if a: rec[a]["w"] += 1
            rec[h]["l"] += 1
    out = []
    for sid, r in rec.items():
        squad = await session.get(FantasySquad, sid)
        mgr = await session.get(FantasyManager, squad.manager_id) if squad else None
        out.append({
            "squad_id": sid, "team_name": squad.team_name if squad else "?",
            "manager": mgr.display_name if mgr else "?",
            "w": r["w"], "l": r["l"], "d": r["d"],
            "pts": r["w"] * H2H_WIN + r["d"] * H2H_DRAW, "pf": round(r["pf"], 1),
        })
    out.sort(key=lambda x: (x["pts"], x["pf"]), reverse=True)
    for i, row in enumerate(out, start=1):
        row["rank"] = i
    return out


# ── Waivers ──────────────────────────────────────────────────────────────────

async def process_waivers(session: AsyncSession, league: FantasyLeague, fs) -> int:
    """Grant pending claims in reverse-ladder priority (worst team first). A claim
    succeeds if the add player is unowned in the league and the manager holds the
    drop player; role quota is preserved. Returns how many were granted."""
    standings = (await session.execute(
        select(FantasySquad.id, FantasySquad.manager_id, FantasySquad.total_points)
        .where(FantasySquad.league_id == league.id).order_by(FantasySquad.total_points.asc())
    )).all()
    priority = {str(mid): i for i, (_sid, mid, _pts) in enumerate(standings)}
    squad_of = {str(mid): str(sid) for sid, mid, _ in standings}

    owned = set((await session.execute(
        text("""SELECT sp.player_id FROM fantasy_squad_players sp JOIN fantasy_squads sq ON sq.id = sp.squad_id
                WHERE sq.league_id = CAST(:lid AS UUID)"""), {"lid": str(league.id)})).scalars().all())
    owned = {str(p) for p in owned}

    claims = (await session.execute(
        select(FantasyWaiverClaim).where(
            FantasyWaiverClaim.league_id == league.id, FantasyWaiverClaim.status == "pending")
    )).scalars().all()
    claims.sort(key=lambda c: priority.get(str(c.manager_id), 999))

    granted = 0
    pool = await _pool_map(session, fs)
    for c in claims:
        add_pid, drop_pid = str(c.add_player_id), str(c.drop_player_id) if c.drop_player_id else None
        sid = squad_of.get(str(c.manager_id))
        if not sid or add_pid in owned or add_pid not in pool or not drop_pid:
            c.status = "rejected"; c.processed_at = _now(); continue
        drop_sp = (await session.execute(
            select(FantasySquadPlayer).where(
                FantasySquadPlayer.squad_id == sid, FantasySquadPlayer.player_id == drop_pid)
        )).scalar_one_or_none()
        if drop_sp is None or pool[add_pid]["role"] != drop_sp.role or drop_sp.is_captain or drop_sp.is_vice_captain:
            c.status = "rejected"; c.processed_at = _now(); continue
        await session.delete(drop_sp)
        session.add(FantasySquadPlayer(squad_id=sid, player_id=add_pid, role=pool[add_pid]["role"]))
        owned.add(add_pid)
        c.status = "approved"; c.processed_at = _now()
        granted += 1
    return granted


# ── Trades ───────────────────────────────────────────────────────────────────

async def apply_trade(session: AsyncSession, trade: FantasyTrade) -> None:
    """Execute an accepted trade: move the offered players between the two squads,
    keeping each squad's role composition intact (a like-for-like by role swap)."""
    give = [str(p) for p in (trade.offer or {}).get("give", [])]
    get = [str(p) for p in (trade.offer or {}).get("get", [])]
    if len(give) != len(get):
        raise ValueError("A trade must swap the same number of players each way.")

    async def _move(player_id, from_squad, to_squad):
        sp = (await session.execute(
            select(FantasySquadPlayer).where(
                FantasySquadPlayer.squad_id == from_squad, FantasySquadPlayer.player_id == player_id)
        )).scalar_one_or_none()
        if sp is None:
            raise ValueError("A traded player is no longer in the squad.")
        if sp.is_captain or sp.is_vice_captain:
            raise ValueError("Change captain/vice before trading them.")
        sp.squad_id = to_squad
        return sp.role

    # Roles must match pairwise so neither squad breaks its quota.
    for gp, kp in zip(give, get):
        rg = await _move(gp, trade.proposer_squad_id, trade.receiver_squad_id)
        rk = await _move(kp, trade.receiver_squad_id, trade.proposer_squad_id)
        if rg != rk:
            raise ValueError("Trades must be like-for-like by role.")
    trade.status = "accepted"
    trade.resolved_at = _now()
