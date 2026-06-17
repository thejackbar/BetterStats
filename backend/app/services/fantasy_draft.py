"""BetterFantasyCricket draft engine — snake draft, waivers, trades, head-to-head.

A draft league owns its players uniquely. The draft runs async: each pick has a
clock, and if it lapses the system auto-picks the manager's top wishlist player
(or the best available that still fits their role quota). When the draft fills,
each manager's picks become a squad and the league plays out on a total-points
or head-to-head ladder, with a waiver wire and manager-to-manager trades.

Auction drafts are modelled in the schema (bid_amount) but not yet run here;
``start_draft`` accepts snake only for now. Full design:
docs/betterfantasycricket.md.

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
    FantasyTrade,
)
from app.services.fantasy_scoring import DEFAULT_RULES

H2H_WIN, H2H_DRAW = 4, 2


def _now() -> datetime:
    return datetime.now(timezone.utc)


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
    """Create the draft, shuffle the order and lay out the snake pick slots."""
    if (league.draft_type or "snake") != "snake":
        raise ValueError("Only snake drafts can be run right now.")
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
    draft.type = "snake"
    draft.status = "in_progress"
    draft.pick_seconds = int(getattr(draft, "pick_seconds", None) or 14400)
    draft.current_pick = 0
    draft.draft_order = order
    draft.rounds = rounds
    draft.started_at = _now()
    if existing is None:
        session.add(draft)
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
    """Auto-pick any pick whose clock has lapsed, walking forward until the draft
    is caught up (or finished). Safe to call on every draft view."""
    if draft.status != "in_progress":
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


# ── Finalise → squads, then optionally head-to-head fixtures ─────────────────────

async def finalize_draft(session: AsyncSession, draft: FantasyDraft, fs) -> None:
    league = await session.get(FantasyLeague, draft.league_id)
    pool = await _pool_map(session, fs)
    picks = (await session.execute(
        select(FantasyDraftPick).where(FantasyDraftPick.draft_id == draft.id)
    )).scalars().all()
    by_manager: dict[str, list] = defaultdict(list)
    for p in picks:
        if p.player_id:
            by_manager[str(p.manager_id)].append(str(p.player_id))

    squad_by_manager: dict[str, FantasySquad] = {}
    for mid, player_ids in by_manager.items():
        mgr = await session.get(FantasyManager, mid)
        squad = FantasySquad(
            fantasy_season_id=fs.id, league_id=league.id, manager_id=mid,
            organisation_id=fs.organisation_id,
            team_name=f"{mgr.display_name if mgr else 'Team'}'s XI", budget_remaining=None,
        )
        session.add(squad)
        await session.flush()
        squad_by_manager[mid] = squad
        # Captain the priciest pick, vice the next.
        ranked = sorted(player_ids, key=lambda pid: pool.get(pid, {}).get("price", 0), reverse=True)
        for i, pid in enumerate(player_ids):
            session.add(FantasySquadPlayer(
                squad_id=squad.id, player_id=pid, role=pool.get(pid, {}).get("role", "batter"),
                is_captain=(pid == ranked[0]) if ranked else False,
                is_vice_captain=(len(ranked) > 1 and pid == ranked[1]),
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
