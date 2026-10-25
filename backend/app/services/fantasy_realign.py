"""Bring scored Fantasy rounds back in line with the draw (a previewed, all-or-nothing action).

Why it exists. ``fantasy_engine.generate_rounds`` never rewrites a round once it is scored, and round
numbers come from position in the draw. A round scored before the draw was complete (the second week
of a two day round not yet known, a fixture added later) therefore stays frozen on its short dates
while every later round is numbered from the wrong place. A game dated outside every round's window
scores for nobody, and a running round shows nothing: Applecross had round 2 stored as 10 to 11 Oct,
round 3 as 17 to 18 Oct and round 4 on 7 Nov, with the games of 24 Oct to 1 Nov in no round at all.

``plan`` (read only) lists each scored round whose stored dates differ from what the draw now gives for
that round number. Two kinds: ``widen`` (the draw's window holds the stored one: the second week of a
two day round turned up) and ``replace`` (it does not: the stored round is on dates the draw gives to
another round).

``apply`` is all or nothing. A ``widen`` only moves the dates and settles the round again from the
lineups it was settled with, as the late-scorecard refresh does, so nothing a manager did is touched and
no free transfer is banked twice. A ``replace`` is a different round, so it is taken back with
``unsettle_round`` (the Unsettle button's undo), given the draw's dates, first kick-off and default lock,
and left ``upcoming``. That is refused unless NOTHING recorded by a manager hangs off it: no chip,
transfer, hit, points, queued transfer, head-to-head result, transaction or hand-typed score, because
re-dating it would rewrite what somebody decided. A team that joined after the round was settled never
received the free transfer unsettling takes back, so theirs is put back, and a team stamped as joining in the round AFTER the replaced one (``joined_round``, the first round it scores in, set when that round was the open one) is moved back onto the replaced round, which is open again: otherwise every such team is silently skipped for it and shows 0 (``repair_joined_rounds``). Then ``generate_rounds`` runs
for the rounds that are not scored, widened rounds are settled again, and a replaced round is settled if
it is over or given its provisional points if it is being played. One audit entry holds the before and
after. Nothing is committed here: the caller commits, or rolls back, as one unit.
"""
from __future__ import annotations

import json
import logging
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import FantasyRound
from app.services import fantasy_engine

logger = logging.getLogger(__name__)

AUDIT_ACTION = "fantasy_realign_rounds"


class NothingToRealign(Exception):
    """Every scored round already matches the draw."""


class RealignBlocked(Exception):
    """A round that would change has manager activity on it; ``plan`` says which and why."""

    def __init__(self, plan: dict):
        super().__init__("a round that would change has manager activity on it")
        self.plan = plan


async def _blockers(session: AsyncSession, round_id) -> list[str]:
    """Why this round cannot be re-dated without rewriting what a manager did. Empty = safe."""
    p = {"r": str(round_id)}
    why: list[str] = []

    async def count(sql: str) -> int:
        return int((await session.execute(text(sql), p)).scalar() or 0)

    n = await count("""SELECT COUNT(*) FROM fantasy_squad_round_scores WHERE round_id = CAST(:r AS UUID)
                       AND (chip_used IS NOT NULL OR transfers_made > 0 OR transfer_hit <> 0)""")
    if n:
        why.append(f"{n} team{'s' if n != 1 else ''} played a chip or made transfers for it")
    n = await count("""SELECT COUNT(*) FROM fantasy_squad_round_scores WHERE round_id = CAST(:r AS UUID)
                       AND (points <> 0 OR raw_points <> 0)""")
    if n:
        why.append(f"{n} team{'s' if n != 1 else ''} have points in it")
    n = await count("SELECT COUNT(*) FROM fantasy_queued_transfers WHERE after_round_id = CAST(:r AS UUID)")
    if n:
        why.append(f"{n} queued transfer{'s' if n != 1 else ''} wait on it")
    n = await count("SELECT COUNT(*) FROM fantasy_h2h_fixtures WHERE round_id = CAST(:r AS UUID) AND result IS NOT NULL")
    if n:
        why.append(f"{n} head-to-head result{'s' if n != 1 else ''} came from it")
    n = await count("SELECT COUNT(*) FROM fantasy_transactions WHERE round_id = CAST(:r AS UUID)")
    if n:
        why.append(f"{n} transaction{'s' if n != 1 else ''} are recorded against it")
    n = await count("""SELECT COUNT(*) FROM fantasy_player_round_scores WHERE round_id = CAST(:r AS UUID)
                       AND breakdown->>'manual' IS NOT NULL""")
    if n:
        why.append(f"{n} hand-typed score{'s' if n != 1 else ''} are on it")
    return why


async def plan(session: AsyncSession, fs, refresh: bool = False) -> dict:
    """Read only. ``{changes, can_apply, draw_rounds}``; each change is ``{round_id, round_number, status,
    stored: [start, end], draw: [start, end], blockers: [..]}``. A round that is not scored is not listed:
    ``generate_rounds`` already follows the draw for those."""
    windows, _games, _cal, _checked, _starts = await fantasy_engine.draw_windows(session, fs, refresh)
    rows = (await session.execute(
        text("""SELECT id, round_number, status, start_date, end_date FROM fantasy_rounds
                WHERE fantasy_season_id = CAST(:fs AS UUID) ORDER BY round_number"""),
        {"fs": str(fs.id)})).mappings().all()
    stored = {r["round_number"]: r for r in rows}
    changes = []
    for n, (first, last) in enumerate(windows, start=1):
        r = stored.get(n)
        if r is None or r["status"] != "scored" or (r["start_date"], r["end_date"]) == (first, last):
            continue
        widen = bool(r["start_date"] and r["end_date"] and first <= r["start_date"] and last >= r["end_date"])
        changes.append({
            "round_id": str(r["id"]), "round_number": n, "status": r["status"],
            "kind": "widen" if widen else "replace",
            "stored": [r["start_date"].isoformat() if r["start_date"] else None,
                       r["end_date"].isoformat() if r["end_date"] else None],
            "draw": [first.isoformat(), last.isoformat()],
            "blockers": [] if widen else await _blockers(session, r["id"]),
        })
    return {"changes": changes, "can_apply": bool(changes) and not any(c["blockers"] for c in changes),
            "draw_rounds": len(windows)}


async def apply(session: AsyncSession, fs, by: str | None = None) -> dict:
    """Do what ``plan`` lists, all or nothing. Raises ``NothingToRealign`` or ``RealignBlocked``; the
    caller commits on success and rolls back on any error."""
    p = await plan(session, fs, refresh=True)
    if not p["changes"]:
        raise NothingToRealign()
    if not p["can_apply"]:
        raise RealignBlocked(p)
    windows, _g, _c, _k, cal_starts = await fantasy_engine.draw_windows(session, fs)
    state = await fantasy_engine.club_state(session, fs.organisation_id)
    today = date.today()

    replaced, widened = [], []
    for ch in p["changes"]:
        if ch["kind"] != "replace":
            continue
        rnd = await session.get(FantasyRound, ch["round_id"])
        # Teams created after this round was settled never got the free transfer unsettling takes back.
        late = {str(r[0]): r[1] for r in (await session.execute(
            text("""SELECT id, free_transfers FROM fantasy_squads
                    WHERE fantasy_season_id = CAST(:fs AS UUID) AND created_at > :t"""),
            {"fs": str(fs.id), "t": rnd.scored_at})).all()} if rnd.scored_at else {}
        await fantasy_engine.unsettle_round(session, fs, rnd)
        for sid, ft in late.items():
            await session.execute(text("UPDATE fantasy_squads SET free_transfers = :f WHERE id = CAST(:i AS UUID)"),
                                  {"f": ft, "i": sid})
        first, last = windows[ch["round_number"] - 1]
        first_start = cal_starts.get(first)
        if first_start is None and rnd.start_date == first:
            first_start = rnd.first_start
        await session.execute(
            text("""UPDATE fantasy_rounds SET start_date = :s, end_date = :e, first_start = :fs_,
                           lock_at = CASE WHEN lock_manual THEN lock_at ELSE :lock END,
                           status = 'upcoming', scored_at = NULL, live_checked_at = NULL, updated_at = NOW()
                    WHERE id = CAST(:r AS UUID)"""),
            {"s": first, "e": last, "fs_": first_start, "r": ch["round_id"],
             "lock": fantasy_engine.default_lock_at(first, fs.rules, first_start, state)},
        )
        await session.refresh(rnd)
        replaced.append(rnd)
    for ch in p["changes"]:
        if ch["kind"] != "widen":
            continue
        first, last = windows[ch["round_number"] - 1]
        await session.execute(
            text("UPDATE fantasy_rounds SET start_date = :s, end_date = :e, updated_at = NOW() WHERE id = CAST(:r AS UUID)"),
            {"s": first, "e": last, "r": ch["round_id"]})
        widened.append(await session.get(FantasyRound, ch["round_id"]))

    # Rounds that are not scored follow the draw as always (renumbering, surplus clean-up).
    await fantasy_engine.generate_rounds(session, fs)
    for rnd in widened:
        await session.refresh(rnd)
        await fantasy_engine.settle_round(session, fs, rnd)   # from its stored lineups; no second free transfer
    for rnd in replaced:
        await session.refresh(rnd)
        if rnd.end_date and rnd.end_date < today:
            await fantasy_engine.settle_round(session, fs, rnd)
        elif rnd.start_date and rnd.start_date <= today:
            await fantasy_engine.refresh_live_round(session, fs, rnd)

    await session.execute(
        text("""INSERT INTO audit_logs (org_id, user_id, action, target_type, target_id, details)
                VALUES (CAST(:o AS UUID), NULL, :a, 'fantasy_season', :t, CAST(:d AS JSONB))"""),
        {"o": str(fs.organisation_id), "a": AUDIT_ACTION, "t": str(fs.id),
         "d": json.dumps({"by": by, "changes": [
             {k: c[k] for k in ("round_number", "kind", "stored", "draw")} for c in p["changes"]],
          "undo": "Set each round's start_date and end_date back to its 'stored' dates and settle it again."})},
    )
    # After the audit entry exists: the repair reads it, and only teams created before it.
    fixed = await repair_joined_rounds(session, fs)
    if fixed:
        for rnd in replaced:
            await session.refresh(rnd)
            if rnd.start_date and rnd.start_date <= today and rnd.status != "scored":
                await fantasy_engine.refresh_live_round(session, fs, rnd)
    return {"realigned": [{"round_number": c["round_number"], "from": c["stored"], "to": c["draw"]}
                          for c in p["changes"]], "teams_rejoined": fixed}


async def repair_joined_rounds(session: AsyncSession, fs) -> int:
    """Put teams that joined before a realignment back on the round it re-opened. Returns how many.

    A team joining mid-season is stamped ``joined_round`` = the open round at the time and is never scored
    for an earlier round. Those that joined while round N+1 was open because round N was scored have
    ``joined_round`` N+1; when round N is replaced (a different round now, not scored) they must score
    from N. Read from the ``fantasy_realign_rounds`` audit entries (round numbers replaced, and when), so
    it also heals a season realigned before this existed. Only teams created BEFORE that entry (a team
    that joined afterwards really did join at N+1), and only while round N is still not scored, so an
    admin unsettling an older round later never re-credits a late joiner. Idempotent."""
    entries = (await session.execute(
        text("""SELECT created_at, details FROM audit_logs
                WHERE action = :a AND target_id = :t ORDER BY created_at"""),
        {"a": AUDIT_ACTION, "t": str(fs.id)})).all()
    fixed = 0
    for at, details in entries:
        if isinstance(details, str):
            details = json.loads(details)
        for ch in (details or {}).get("changes", []):
            if ch.get("kind") != "replace":
                continue
            n = int(ch["round_number"])
            res = await session.execute(
                text("""UPDATE fantasy_squads SET joined_round = :n
                        WHERE fantasy_season_id = CAST(:fs AS UUID) AND joined_round = :n1 AND created_at < :at
                          AND EXISTS (SELECT 1 FROM fantasy_rounds r WHERE r.fantasy_season_id = CAST(:fs AS UUID)
                                      AND r.round_number = :n AND r.status <> 'scored')"""),
                {"n": n, "n1": n + 1, "fs": str(fs.id), "at": at})
            fixed += res.rowcount or 0
    return fixed
