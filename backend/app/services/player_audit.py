"""The club-wide audit trail (migration 339): who changed which player, where, when.

Every change to a player in selection, availability or squads writes one
``audit_events`` row with a plain sentence for the list, the names as they were at
the time, and who did it (a signed-in user, or the player through their own
link). Admin screens read it back through ``routers/audit``.

WHO. ``get_current_user`` stores the signed-in user in a context variable, so the
shared squad and availability writers (which have never been handed a user) can
still say who acted. A caller that knows better passes ``user=`` (the player's
own link passes ``None`` and ``via="player link"``). With nobody, the row says
"System".

Never raises: the trail must not take down the change it describes, so each
write runs in a savepoint and a failure is logged. Rows are never deleted by
code.
"""
from __future__ import annotations

import contextvars
import json
import logging
from datetime import date, datetime, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

AREAS = ("selection", "availability", "squads", "details")

# action code -> the label the list shows. Codes are stored; labels may change.
ACTIONS: dict[str, str] = {
    "added_to_xi": "Added to XI",
    "removed_from_xi": "Removed from XI",
    "batting_order_changed": "Batting order changed",
    "made_captain": "Made captain",
    "removed_captain": "Captain removed",
    "made_keeper": "Made wicket-keeper",
    "removed_keeper": "Wicket-keeper removed",
    "side_confirmed": "Side confirmed",
    "side_locked": "Side locked",
    "side_unlocked": "Side unlocked",
    "called_up_out": "Called up out of XI",
    "restored_to_board": "Restored to the board",
    "availability_set": "Availability set",
    "dormancy_cleared": "Marked no longer dormant",
    "dormancy_restored": "Marked dormant again",
    "availability_period_added": "Unavailable period added",
    "availability_period_removed": "Unavailable period removed",
    "added_to_squad": "Added to squad",
    "removed_from_squad": "Removed from squad",
    "moved_squad": "Moved squad",
    "squad_created": "Squad created",
    "squad_updated": "Squad edited",
    "squad_deleted": "Squad deleted",
    "details_updated": "Contact details updated by the player",
}

_actor: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar("audit_actor", default=None)
_UNSET: Any = object()


def user_label(user) -> Optional[str]:
    if user is None:
        return None
    return (
        getattr(user, "display_name", None)
        or " ".join(x for x in (getattr(user, "first_name", None), getattr(user, "last_name", None)) if x)
        or getattr(user, "username", None) or getattr(user, "email", None)
    )


def set_actor(user) -> None:
    """Remember who is making this request. Called by ``get_current_user``."""
    if user is None:
        _actor.set(None)
        return
    _actor.set({"id": getattr(user, "id", None), "name": user_label(user)})


def current_actor() -> Optional[dict]:
    return _actor.get()


async def player_name(db: AsyncSession, player_id) -> Optional[str]:
    if not player_id:
        return None
    return (await db.execute(
        text("SELECT COALESCE(display_name_override, name) FROM players WHERE id = :p"), {"p": player_id},
    )).scalar()


async def team_name(db: AsyncSession, team_id) -> Optional[str]:
    if not team_id:
        return None
    return (await db.execute(text("SELECT name FROM teams WHERE id = :t"), {"t": team_id})).scalar()


async def fixture_label(db: AsyncSession, fixture_id) -> Optional[str]:
    """"2nd XI v Rovers, Sat 17 Oct": what a selector calls the game."""
    if not fixture_id:
        return None
    row = (await db.execute(
        text(
            "SELECT f.played_on, f.opponent_name, f.label, COALESCE(NULLIF(t.short_name, ''), t.name) "
            "FROM fixtures f LEFT JOIN teams t ON t.id = f.team_id WHERE f.id = :f"
        ),
        {"f": fixture_id},
    )).first()
    if not row:
        return None
    on, opp, label, tname = row
    when = on.strftime("%a %-d %b") if on else None
    head = tname or label
    vs = f"v {opp}" if opp else None
    return ", ".join(x for x in (" ".join(y for y in (head, vs) if y) or None, when) if x) or None


async def record(
    db: AsyncSession, *, club_id, area: str, action: str, summary: str,
    player_id=None, player_name_: Optional[str] = None,
    team_id=None, team_name_: Optional[str] = None,
    fixture_id=None, fixture_label_: Optional[str] = None,
    detail: Optional[dict] = None, user=_UNSET, via: Optional[str] = None, by: Optional[str] = None,
) -> None:
    """Write one event. See the module note: never raises, never deletes."""
    if user is _UNSET:
        actor = current_actor() or {}
        uid, uname = actor.get("id"), actor.get("name")
        via = via or ("admin" if actor else "system")
    else:
        uid, uname = getattr(user, "id", None), user_label(user)
        via = via or ("admin" if user is not None else "system")
    if by:
        uname = by
    try:
        async with db.begin_nested():
            await db.execute(
                text(
                    "INSERT INTO audit_events (organisation_id, user_id, user_name, via, area, action, "
                    "player_id, player_name, team_id, team_name, fixture_id, fixture_label, summary, detail) "
                    "VALUES (:org, :uid, :uname, :via, :area, :action, :pid, :pname, :tid, :tname, :fid, :flabel, "
                    ":summary, CAST(:detail AS jsonb))"
                ),
                {"org": club_id, "uid": uid, "uname": uname, "via": via, "area": area, "action": action,
                 "pid": player_id, "pname": player_name_, "tid": team_id, "tname": team_name_,
                 "fid": fixture_id, "flabel": fixture_label_, "summary": summary,
                 "detail": json.dumps(detail or {}, default=str)},
            )
    except Exception:  # noqa: BLE001 - the trail must never break the change it describes
        log.exception("audit write failed: %s %s", area, action)


# ── Reading ───────────────────────────────────────────────────────────────────
def _tz(tz: Optional[str]) -> str:
    if tz and len(tz) <= 64:
        try:
            ZoneInfo(tz)
            return tz
        except (ZoneInfoNotFoundError, ValueError, OSError):
            pass
    return "UTC"


def _where(club_id, *, q=None, area=None, action=None, user=None, player_id=None, team=None,
           date_from: Optional[date] = None, date_to: Optional[date] = None, tz: Optional[str] = None):
    tzname = _tz(tz)
    clauses = ["organisation_id = :org"]
    params: dict[str, Any] = {"org": club_id, "tz": tzname}
    if area:
        clauses.append("area = :area"); params["area"] = area
    if action:
        clauses.append("action = ANY(CAST(:actions AS text[]))")
        params["actions"] = [a for a in action.split(",") if a]
    if user:
        clauses.append("COALESCE(user_name, 'System') = :user"); params["user"] = user
    if player_id:
        clauses.append("player_id = CAST(:pid AS uuid)"); params["pid"] = str(player_id)
    if team:
        clauses.append("team_name = :team"); params["team"] = team
    if date_from:
        clauses.append("(created_at AT TIME ZONE :tz)::date >= :dfrom"); params["dfrom"] = date_from
    if date_to:
        clauses.append("(created_at AT TIME ZONE :tz)::date <= :dto"); params["dto"] = date_to
    if q and q.strip():
        for i, word in enumerate(q.split()):
            clauses.append(
                f"(summary ILIKE :w{i} OR COALESCE(player_name, '') ILIKE :w{i} OR COALESCE(user_name, '') ILIKE :w{i} "
                f"OR COALESCE(team_name, '') ILIKE :w{i} OR COALESCE(fixture_label, '') ILIKE :w{i} OR action ILIKE :w{i})"
            )
            params[f"w{i}"] = f"%{word.strip().replace('%', '').replace('_', ' ')}%"
    return " AND ".join(clauses), params


def _row(r) -> dict:
    return {
        "id": str(r.id), "at": r.created_at.isoformat() if r.created_at else None,
        "local_date": r.local_date.isoformat() if r.local_date else None,
        "local_time": r.local_time.strftime("%H:%M:%S") if r.local_time else None,
        "by": r.user_name or "System", "via": r.via, "area": r.area, "action": r.action,
        "action_label": ACTIONS.get(r.action, r.action.replace("_", " ").capitalize()),
        "player_id": str(r.player_id) if r.player_id else None, "player": r.player_name,
        "team": r.team_name, "game": r.fixture_label, "fixture_id": str(r.fixture_id) if r.fixture_id else None,
        "summary": r.summary, "detail": r.detail or {},
    }


_COLS = (
    "id, created_at, (created_at AT TIME ZONE :tz)::date AS local_date, (created_at AT TIME ZONE :tz)::time AS local_time, "
    "user_name, via, area, action, player_id, player_name, team_id, team_name, fixture_id, fixture_label, summary, detail"
)


async def search(db: AsyncSession, club_id, *, limit: int = 100, offset: int = 0, **filters) -> dict:
    where, params = _where(club_id, **filters)
    total = (await db.execute(text(f"SELECT COUNT(*) FROM audit_events WHERE {where}"), params)).scalar() or 0
    rows = (await db.execute(
        text(f"SELECT {_COLS} FROM audit_events WHERE {where} ORDER BY created_at DESC, id LIMIT :n OFFSET :o"),
        {**params, "n": max(1, min(limit, 500)), "o": max(0, offset)},
    )).fetchall()
    return {"total": int(total), "events": [_row(r) for r in rows]}


async def export_rows(db: AsyncSession, club_id, *, cap: int = 50000, **filters) -> list[dict]:
    where, params = _where(club_id, **filters)
    rows = (await db.execute(
        text(f"SELECT {_COLS} FROM audit_events WHERE {where} ORDER BY created_at DESC, id LIMIT :n"),
        {**params, "n": cap},
    )).fetchall()
    return [_row(r) for r in rows]


async def facets(db: AsyncSession, club_id) -> dict:
    """What the filters can offer: who has made changes, which squads appear."""
    users = (await db.execute(
        text("SELECT DISTINCT COALESCE(user_name, 'System') FROM audit_events WHERE organisation_id = :o ORDER BY 1"),
        {"o": club_id})).scalars().all()
    teams = (await db.execute(
        text("SELECT DISTINCT team_name FROM audit_events WHERE organisation_id = :o AND team_name IS NOT NULL ORDER BY 1"),
        {"o": club_id})).scalars().all()
    return {"users": list(users), "teams": list(teams), "areas": list(AREAS),
            "actions": [{"value": k, "label": v} for k, v in ACTIONS.items()]}
