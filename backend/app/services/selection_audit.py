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
