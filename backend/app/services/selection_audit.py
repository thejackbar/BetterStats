"""The selection audit trail (migration 334).

One ``selection_events`` row per change to a side: who confirmed it, locked or
unlocked it, who was pulled out of it by a call-up elsewhere, and the players
before and after. The board shows it as a history a selector can read back and
restore from.

Names are stored in the row as they were at the time, so the history still
reads the same after a player is renamed or merged. Rows are a record of what
people decided: code never deletes them (they go with the fixture).

Never raises. A failure to write the trail must not take down the confirm it
describes, so each write runs in a savepoint and is logged on failure.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import player_audit

log = logging.getLogger(__name__)

ACTIONS = ("confirmed", "locked", "unlocked", "called_up_out", "restored_to_board")


async def snapshot(db: AsyncSession, fixture_id) -> list[dict]:
    """The fixture's confirmed XI right now, in batting order, with names."""
    rows = (await db.execute(
        text(
            "SELECT fl.player_id, COALESCE(p.display_name_override, p.name), fl.batting_order, "
            "fl.is_captain, fl.is_wicket_keeper "
            "FROM fixture_lineups fl JOIN players p ON p.id = fl.player_id "
            "WHERE fl.fixture_id = :f ORDER BY fl.batting_order NULLS LAST, 2"
        ),
        {"f": fixture_id},
    )).fetchall()
    return [
        {"player_id": str(pid), "name": name, "batting_order": bo,
         "is_captain": bool(cap), "is_wicket_keeper": bool(wk)}
        for pid, name, bo, cap, wk in rows
    ]


def diff(before: list[dict], after: list[dict]) -> dict:
    """Who came in, who went out, and any change of captain or keeper."""
    b = {p["player_id"]: p for p in before}
    a = {p["player_id"]: p for p in after}
    cap = lambda xs: next((p["name"] for p in xs if p.get("is_captain")), None)  # noqa: E731
    wk = lambda xs: next((p["name"] for p in xs if p.get("is_wicket_keeper")), None)  # noqa: E731
    return {
        "added": [a[k]["name"] for k in a if k not in b],
        "removed": [b[k]["name"] for k in b if k not in a],
        "captain": cap(after) if cap(before) != cap(after) else None,
        "keeper": wk(after) if wk(before) != wk(after) else None,
        "reordered": bool(
            set(a) == set(b) and [p["player_id"] for p in before] != [p["player_id"] for p in after]
        ),
    }


async def record(
    db: AsyncSession, *, club_id, fixture_id, user, action: str,
    before: Optional[list[dict]] = None, after: Optional[list[dict]] = None,
    extra: Optional[dict] = None,
) -> None:
    detail: dict = dict(extra or {})
    if before is not None:
        detail["before"] = before
    if after is not None:
        detail["after"] = after
    if before is not None and after is not None:
        detail.update(diff(before, after))
    name = None
    if user is not None:
        name = (getattr(user, "display_name", None)
                or " ".join(x for x in (getattr(user, "first_name", None), getattr(user, "last_name", None)) if x)
                or getattr(user, "username", None) or getattr(user, "email", None))
    try:
        async with db.begin_nested():
            await db.execute(
                text(
                    "INSERT INTO selection_events (organisation_id, fixture_id, user_id, user_name, action, detail) "
                    "VALUES (:org, :fid, :uid, :uname, :action, CAST(:detail AS jsonb))"
                ),
                {"org": club_id, "fid": fixture_id, "uid": getattr(user, "id", None), "uname": name,
                 "action": action, "detail": json.dumps(detail)},
            )
    except Exception:  # noqa: BLE001 - the trail must never break the change it describes
        log.exception("selection audit write failed for fixture %s", fixture_id)
    await _club_trail(db, club_id, fixture_id, user, action, before, after, extra or {})


async def history(db: AsyncSession, club_id, fixture_id, limit: int = 60) -> list[dict]:
    rows = (await db.execute(
        text(
            "SELECT id, user_name, action, detail, created_at FROM selection_events "
            "WHERE organisation_id = :org AND fixture_id = :fid ORDER BY created_at DESC, id LIMIT :n"
        ),
        {"org": club_id, "fid": fixture_id, "n": limit},
    )).fetchall()
    return [
        {"id": str(i), "by": by, "action": action, "detail": detail or {}, "at": at.isoformat() if at else None}
        for i, by, action, detail, at in rows
    ]


def _moved(before: list[dict], after: list[dict]) -> list[tuple[dict, dict]]:
    """Players who changed place in the batting order, as (before, after) pairs.

    Only the fewest moves that explain the new order: if one player goes from 5 to
    2, the players he jumped over slid down one place and are not reported."""
    a = {p["player_id"]: p for p in after}
    common_before = [p for p in before if p["player_id"] in a]
    pos_after = {p["player_id"]: i for i, p in enumerate(after)}
    seq = [pos_after[p["player_id"]] for p in common_before]
    # Longest increasing subsequence: those players kept their relative place.
    tails: list[int] = []
    prev: list[Optional[int]] = [None] * len(seq)
    idx: list[int] = []
    for i, v in enumerate(seq):
        lo, hi = 0, len(tails)
        while lo < hi:
            mid = (lo + hi) // 2
            if seq[tails[mid]] < v:
                lo = mid + 1
            else:
                hi = mid
        if lo > 0:
            prev[i] = tails[lo - 1]
        if lo == len(tails):
            tails.append(i)
        else:
            tails[lo] = i
    keep: set[int] = set()
    k = tails[-1] if tails else None
    while k is not None:
        keep.add(k)
        k = prev[k]
    return [(common_before[i], a[common_before[i]["player_id"]]) for i in range(len(seq)) if i not in keep]


async def _club_trail(db, club_id, fixture_id, user, action, before, after, extra) -> None:
    """The same change as one audit_events row per player, for the Audit History page."""
    try:
        game = await player_audit.fixture_label(db, fixture_id)
        row = (await db.execute(
            text("SELECT t.id, t.name FROM fixtures f LEFT JOIN teams t ON t.id = f.team_id WHERE f.id = :f"),
            {"f": fixture_id},
        )).first()
        tid, tname = (row[0], row[1]) if row else (None, None)
        where = f" in {game}" if game else ""

        async def emit(act, summary, p=None, detail=None):
            await player_audit.record(
                db, club_id=club_id, area="selection", action=act, summary=summary,
                player_id=(p or {}).get("player_id"), player_name_=(p or {}).get("name"),
                team_id=tid, team_name_=tname, fixture_id=fixture_id, fixture_label_=game,
                detail=detail, user=user,
            )

        if action in ("locked", "unlocked"):
            await emit("side_locked" if action == "locked" else "side_unlocked",
                       f"{'Locked' if action == 'locked' else 'Unlocked'} the side{where}")
            return
        before = before or []
        after = after or []
        b = {p["player_id"]: p for p in before}
        a = {p["player_id"]: p for p in after}
        if action == "called_up_out":
            for pid, p in b.items():
                if pid not in a:
                    await emit("called_up_out", f"{p['name']} called up out of the XI{where}", p, extra)
            return
        changed = False
        for pid, p in a.items():
            if pid not in b:
                changed = True
                no = f" at no. {p['batting_order']}" if p.get("batting_order") else ""
                await emit("added_to_xi", f"{p['name']} added to the XI{where}{no}", p, {"batting_order": p.get("batting_order")})
        for pid, p in b.items():
            if pid not in a:
                changed = True
                await emit("removed_from_xi", f"{p['name']} removed from the XI{where}", p, {"batting_order": p.get("batting_order")})
        for old, new in _moved(before, after):
            ob, nb = old.get("batting_order"), new.get("batting_order")
            if ob == nb:
                continue
            changed = True
            way = "up" if (nb or 0) < (ob or 0) else "down"
            await emit("batting_order_changed",
                       f"{new['name']} moved {way} the batting order from no. {ob} to no. {nb}{where}", new,
                       {"from": ob, "to": nb, "direction": way})
        for pid, p in a.items():
            old = b.get(pid)
            if old is None:
                continue
            if p.get("is_captain") != old.get("is_captain"):
                changed = True
                await emit("made_captain" if p.get("is_captain") else "removed_captain",
                           f"{p['name']} {'made captain' if p.get('is_captain') else 'no longer captain'}{where}", p)
            if p.get("is_wicket_keeper") != old.get("is_wicket_keeper"):
                changed = True
                await emit("made_keeper" if p.get("is_wicket_keeper") else "removed_keeper",
                           f"{p['name']} {'made wicket-keeper' if p.get('is_wicket_keeper') else 'no longer wicket-keeper'}{where}", p)
        if action == "confirmed":
            n = len(after)
            tail = " and locked it" if extra.get("locked") else ""
            await emit("side_confirmed", f"Confirmed the side{where}: {n} player{'s' if n != 1 else ''}{tail}"
                       + ("" if changed else " (no changes)"))
        elif action == "restored_to_board":
            await emit("restored_to_board", f"Restored the side{where} to the board")
    except Exception:  # noqa: BLE001 - the trail must never break the change it describes
        log.exception("club audit write failed for fixture %s", fixture_id)
