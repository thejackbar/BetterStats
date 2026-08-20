"""BetterSelect → Net Manager.

A tracker for net (practice) sessions: who turned up, who batted, the batting
queue and timer the manager runs pitch-side, and the attendance reports that
surface in BetterSelect and on the player profile.

  * net_sessions    — one training day (date + optional label + timer settings),
                      plus the LIVE state: the batting timer and a version
                      counter every write bumps
  * net_attendance  — one attendee per session (real player OR an ad-hoc guest);
                      the row's existence = "turned up", `batted` = completed a
                      turn, `position` = where they sit in the queue

THE LIVE SESSION IS SERVER-AUTHORITATIVE, and that is the whole shape of this
router. It used to be a client-side state machine on one device that pushed a
debounced full-replace snapshot of the attendance list — so the same admin
account open on a phone by the nets and a laptop in the clubroom showed two
different queues, two different clocks, and whichever device wrote last quietly
threw the other's changes away. Every change is now a small, discrete write
here (check someone in, re-order the queue, rotate, start the clock); each one
bumps `net_sessions.version`, and every device polls `GET /sessions/{id}/live`
with the version it last saw. Matching versions come back as two fields, so a
screen left open on the boundary is cheap.

**Never reintroduce a full-replace attendance write.** Replacing the list is
exactly how one device silently undoes another's check-in, which is the bug
this design exists to prevent.

All endpoints are scoped to the caller's club via get_current_club and gated by
the MANAGE_SELECTIONS capability (same as the rest of BetterSelect), except the
reads, which any club admin may open. The whole router sits behind
require_module("select") at registration in main.py.
"""
from __future__ import annotations

import csv
import io
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_SELECTIONS, require_cap
from app.models.db import (
    NetAttendance, NetSession, Organisation, Player, User, get_db,
)
from app.routers.auth import get_current_club
from app.routers.availability import active_self_service_players

router = APIRouter(prefix="/nets", tags=["net-manager"])


# ── Timer / rotation defaults ─────────────────────────────────────────────────
# The net manager's example, encoded: a 10-minute batting turn with two nets, a
# halfway "notify the next batters" nudge, a "session almost over" warning with
# two minutes left and a "last ball" call with 30 seconds left. Alert thresholds
# are SECONDS REMAINING so they read the same regardless of the total length.
DEFAULT_NET_SETTINGS: dict = {
    "duration_seconds": 600,   # length of one batting turn
    "nets": 2,                 # how many bat at once before the group rotates
    "auto_roll": False,        # roll straight into the next group, or stop+reset?
    "sound": True,             # play a beep on each alert
    "alerts": [
        {"seconds_remaining": 300, "label": "Notify next batters", "tone": "info"},
        {"seconds_remaining": 120, "label": "Session almost over", "tone": "amber"},
        {"seconds_remaining": 30, "label": "Last ball", "tone": "red"},
    ],
}
_TONES = {"info", "amber", "red"}


def _clean_settings(raw: Optional[dict]) -> dict:
    """Coerce a (possibly partial / untrusted) settings dict into a complete,
    clamped config. Always returns every key so the frontend never has to guess.
    """
    raw = raw if isinstance(raw, dict) else {}
    out = dict(DEFAULT_NET_SETTINGS)

    try:
        dur = int(raw.get("duration_seconds", out["duration_seconds"]))
        out["duration_seconds"] = max(30, min(7200, dur))
    except (TypeError, ValueError):
        pass
    try:
        out["nets"] = max(1, min(8, int(raw.get("nets", out["nets"]))))
    except (TypeError, ValueError):
        pass
    out["auto_roll"] = bool(raw.get("auto_roll", out["auto_roll"]))
    out["sound"] = bool(raw.get("sound", out["sound"]))

    alerts_raw = raw.get("alerts")
    if isinstance(alerts_raw, list):
        cleaned = []
        for a in alerts_raw:
            if not isinstance(a, dict):
                continue
            try:
                sec = max(0, min(7200, int(a.get("seconds_remaining", 0))))
            except (TypeError, ValueError):
                continue
            label = str(a.get("label") or "Alert")[:60]
            tone = a.get("tone") if a.get("tone") in _TONES else "info"
            cleaned.append({"seconds_remaining": sec, "label": label, "tone": tone})
        # Most-time-remaining first so the frontend can walk them in order.
        cleaned.sort(key=lambda x: x["seconds_remaining"], reverse=True)
        out["alerts"] = cleaned[:6]
    return out


# ── The live batting timer ────────────────────────────────────────────────────
# Held on the session rather than in the browser that started it, because every
# device watching has to show the same clock. `ends_at` is an ABSOLUTE time: a
# device works out its own countdown from it against the server time it is
# handed, instead of each running a stopwatch from whenever it happened to load.
# `turn_seq` increments whenever a fresh turn begins, which is how each device
# knows to re-arm its own alert beeps.
def _default_live(settings: dict) -> dict:
    return {
        "running": False,
        "ends_at": None,
        "remaining_seconds": float(settings["duration_seconds"]),
        "duration_seconds": int(settings["duration_seconds"]),
        "turn_seq": 0,
    }


def _clean_live(raw: Optional[dict], settings: dict) -> dict:
    out = _default_live(settings)
    if not isinstance(raw, dict):
        return out
    out["running"] = bool(raw.get("running"))
    ends = raw.get("ends_at")
    out["ends_at"] = ends if isinstance(ends, str) else None
    try:
        out["remaining_seconds"] = max(0.0, min(7200.0, float(raw.get("remaining_seconds", out["remaining_seconds"]))))
    except (TypeError, ValueError):
        pass
    try:
        out["duration_seconds"] = max(30, min(7200, int(raw.get("duration_seconds", out["duration_seconds"]))))
    except (TypeError, ValueError):
        pass
    try:
        out["turn_seq"] = max(0, int(raw.get("turn_seq", 0)))
    except (TypeError, ValueError):
        pass
    if out["running"] and not out["ends_at"]:
        # A running clock with no deadline can't be counted down by anyone.
        out["running"] = False
    return out


def _parse_iso(v: Optional[str]) -> Optional[datetime]:
    if not v:
        return None
    try:
        d = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _timer_payload(live: dict) -> dict:
    """The timer as a device should read it: `remaining_seconds` is resolved at
    read time from the deadline, so a screen opened mid-turn lands on the same
    number the screen that started it is showing."""
    out = dict(live)
    if live.get("running"):
        ends = _parse_iso(live.get("ends_at"))
        if ends:
            rem = (ends - datetime.now(timezone.utc)).total_seconds()
            out["remaining_seconds"] = max(0.0, rem)
            if rem <= 0:
                # The deadline has passed and nobody has told us yet. Report it
                # as stopped so every device agrees the turn is over, and let
                # whichever device notices first write it back via /timer.
                out["running"] = False
    return out


def _player_card(p: Player) -> dict:
    return {
        "id": str(p.id),
        "name": p.display_name,
        "photo_url": p.photo_url,
        "skill_positions": p.skill_positions or [],
        "batting_hand": p.batting_hand,
    }


# ── Pydantic bodies ───────────────────────────────────────────────────────────
class SettingsBody(BaseModel):
    duration_seconds: Optional[int] = None
    nets: Optional[int] = None
    auto_roll: Optional[bool] = None
    sound: Optional[bool] = None
    alerts: Optional[list[dict]] = None


class SessionCreate(BaseModel):
    session_date: Optional[date] = None
    label: Optional[str] = None
    notes: Optional[str] = None
    settings: Optional[dict] = None


class SessionUpdate(BaseModel):
    session_date: Optional[date] = None
    label: Optional[str] = None
    notes: Optional[str] = None
    settings: Optional[dict] = None
    status: Optional[str] = None


class AttendeeAdd(BaseModel):
    player_id: Optional[str] = None
    guest_name: Optional[str] = None


class AttendeePatch(BaseModel):
    batted: Optional[bool] = None


class QueueOrder(BaseModel):
    ids: list[str] = []


class TimerAction(BaseModel):
    action: str                                # start | pause | reset | expire
    duration_seconds: Optional[int] = None     # start/reset may set the turn length


class RotateBody(BaseModel):
    # Whether to roll straight into the next turn. Defaults to the session's
    # own auto_roll setting when omitted.
    autostart: Optional[bool] = None
    # The turn the sending device was looking at. A rotation is the one action
    # here that is NOT safe to repeat — doing it twice skips a whole group of
    # batters — so two devices tapping "Next group" on the same turn must only
    # rotate once. The second request carries a turn number that has already
    # moved on and is quietly ignored.
    turn_seq: Optional[int] = None


# ── Helpers ───────────────────────────────────────────────────────────────────
async def _owned_session(db: AsyncSession, session_id: str, club_id) -> NetSession:
    try:
        sid = uuid.UUID(str(session_id))
    except (TypeError, ValueError):
        raise HTTPException(status_code=404, detail="Session not found")
    s = await db.get(NetSession, sid)
    if not s or s.organisation_id != club_id:
        raise HTTPException(status_code=404, detail="Session not found")
    return s


def _touch(s: NetSession) -> None:
    """Mark the session changed so every other device's next poll picks it up.

    The bump is a SQL expression, not `s.version + 1` read in Python: two
    coaches tapping at the same moment would otherwise both compute the same
    next value, and one device's change would land without the version moving —
    invisible to everyone still polling.
    """
    s.version = NetSession.version + 1
    s.updated_at = func.now()


async def _attendee_rows(db: AsyncSession, session_id) -> list[NetAttendance]:
    """Every attendee in queue order: still waiting first, then those who have
    had their turn, each in `position` order."""
    res = await db.execute(
        select(NetAttendance)
        .where(NetAttendance.session_id == session_id)
        .order_by(
            NetAttendance.batted.asc(),
            NetAttendance.position.asc().nullslast(),
            NetAttendance.created_at.asc(),
        )
    )
    return list(res.scalars().all())


async def _renumber(db: AsyncSession, session_id) -> list[NetAttendance]:
    """Re-lay `position` as 0..n-1 over the canonical order above, so the queue
    reads the same however it was last edited and from whichever device."""
    rows = await _attendee_rows(db, session_id)
    for i, r in enumerate(rows):
        if r.position != i:
            r.position = i
    return rows


async def _live_payload(db: AsyncSession, s: NetSession) -> dict:
    """Everything a device needs to draw the live screen. `server_time` is here
    so a device with a skewed clock still counts down to the right moment."""
    rows = await _attendee_rows(db, s.id)

    pids = [r.player_id for r in rows if r.player_id]
    players: dict = {}
    if pids:
        pr = await db.execute(select(Player).where(Player.id.in_(pids)))
        players = {p.id: p for p in pr.scalars().all()}

    attendees = []
    for r in rows:
        p = players.get(r.player_id) if r.player_id else None
        attendees.append({
            "id": str(r.id),
            "player_id": str(r.player_id) if r.player_id else None,
            "guest_name": r.guest_name,
            "name": (p.display_name if p else None) or r.guest_name or "Guest",
            "photo_url": p.photo_url if p else None,
            "skill_positions": (p.skill_positions or []) if p else [],
            "is_guest": r.player_id is None,
            "batted": bool(r.batted),
            "position": r.position,
        })

    settings = _clean_settings(s.settings)
    return {
        "id": str(s.id),
        "version": int(s.version or 0),
        "server_time": datetime.now(timezone.utc).isoformat(),
        "session_date": s.session_date.isoformat() if s.session_date else None,
        "label": s.label,
        "notes": s.notes,
        "status": s.status,
        "settings": settings,
        "timer": _timer_payload(_clean_live(s.live_state, settings)),
        "attendees": attendees,
        "attendee_count": len(attendees),
        "batted_count": sum(1 for a in attendees if a["batted"]),
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


async def _commit_live(db: AsyncSession, s: NetSession) -> dict:
    """Commit a live change and hand the writer the fresh state, so the device
    that acted is instantly consistent instead of waiting for its next poll."""
    _touch(s)
    await db.commit()
    await db.refresh(s)
    return await _live_payload(db, s)


# ── Roster (check-in source) ──────────────────────────────────────────────────
@router.get("/roster")
async def net_roster(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """The active, non-dormant roster to check players in from — the same pool
    the availability matrix and self-service link use, so the Net Manager never
    drowns in decades of historical names."""
    players = await active_self_service_players(db, club)
    return {"players": [_player_card(p) for p in players]}


# ── Club default timer settings ──────────────────────────────────────────────
@router.get("/settings")
async def get_settings(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    return {"settings": _clean_settings(club.net_settings)}


@router.put("/settings")
async def put_settings(
    body: SettingsBody,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    merged = _clean_settings(club.net_settings)
    incoming = {k: v for k, v in body.model_dump().items() if v is not None}
    merged.update(incoming)
    club.net_settings = _clean_settings(merged)
    await db.commit()
    return {"settings": club.net_settings}


# ── Sessions ──────────────────────────────────────────────────────────────────
@router.get("/sessions")
async def list_sessions(
    limit: int = Query(40, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Recent sessions, newest first, each with attendee + batted counts."""
    res = await db.execute(
        select(NetSession)
        .where(NetSession.organisation_id == club.id)
        .order_by(NetSession.session_date.desc(), NetSession.created_at.desc())
        .limit(limit)
    )
    sessions = res.scalars().all()
    counts: dict = {}
    if sessions:
        ids = [s.id for s in sessions]
        cr = await db.execute(
            select(
                NetAttendance.session_id,
                func.count(NetAttendance.id),
                func.count(NetAttendance.id).filter(NetAttendance.batted.is_(True)),
            )
            .where(NetAttendance.session_id.in_(ids))
            .group_by(NetAttendance.session_id)
        )
        for sid, total, batted in cr.fetchall():
            counts[sid] = (total, batted)
    out = []
    for s in sessions:
        total, batted = counts.get(s.id, (0, 0))
        out.append({
            "id": str(s.id),
            "session_date": s.session_date.isoformat() if s.session_date else None,
            "label": s.label,
            "status": s.status,
            "attendee_count": total,
            "batted_count": batted,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        })
    return {"sessions": out}


@router.post("/sessions")
async def create_session(
    body: SessionCreate,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """Open a new net session. Seeds its timer settings from the club default
    (or the supplied override), so the manager can just hit Start."""
    seed = _clean_settings(body.settings if body.settings is not None else club.net_settings)
    s = NetSession(
        id=uuid.uuid4(),
        organisation_id=club.id,
        session_date=body.session_date or date.today(),
        label=(body.label or None),
        notes=(body.notes or None),
        settings=seed,
        live_state=_default_live(seed),
        status="active",
        created_by=user.id,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return await _live_payload(db, s)


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    s = await _owned_session(db, session_id, club.id)
    return await _live_payload(db, s)


@router.get("/sessions/{session_id}/live")
async def live_session(
    session_id: str,
    since: Optional[int] = Query(None, description="The version this device last saw"),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """The poll every open device runs a few times a minute.

    When `since` matches the session's current version, nothing has changed and
    the answer is two fields — `server_time` still comes back so a device that
    is only counting down keeps its clock correction fresh. Otherwise the full
    live payload comes back and the device adopts it wholesale.
    """
    s = await _owned_session(db, session_id, club.id)
    version = int(s.version or 0)
    if since is not None and since == version:
        return {
            "version": version,
            "server_time": datetime.now(timezone.utc).isoformat(),
            "unchanged": True,
        }
    payload = await _live_payload(db, s)
    payload["unchanged"] = False
    return payload


@router.patch("/sessions/{session_id}")
async def update_session(
    session_id: str,
    body: SessionUpdate,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    s = await _owned_session(db, session_id, club.id)
    if body.session_date is not None:
        s.session_date = body.session_date
    if body.label is not None:
        s.label = body.label or None
    if body.notes is not None:
        s.notes = body.notes or None
    if body.settings is not None:
        settings = _clean_settings(body.settings)
        s.settings = settings
        # A turn length changed mid-session only moves a clock that isn't
        # running: rewriting a live deadline would jump the countdown under the
        # batter currently in the net.
        live = _clean_live(s.live_state, settings)
        if not live["running"] and live["duration_seconds"] != settings["duration_seconds"]:
            live["duration_seconds"] = settings["duration_seconds"]
            live["remaining_seconds"] = float(settings["duration_seconds"])
        s.live_state = live
    if body.status is not None and body.status in ("active", "done"):
        s.status = body.status
    return await _commit_live(db, s)


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    s = await _owned_session(db, session_id, club.id)
    await db.delete(s)
    await db.commit()
    return {"status": "ok"}


# ── Attendance: one small write per action ───────────────────────────────────
@router.post("/sessions/{session_id}/attendees")
async def add_attendee(
    session_id: str,
    body: AttendeeAdd,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """Check one person in, at the back of the queue.

    Checking in someone already in the session is a no-op rather than an error:
    two devices tapping the same name at the same moment is an ordinary thing
    to happen at a net session, and neither coach should see a failure for it.
    """
    # Read the club id up front: the rollback below expires every loaded object,
    # and reaching for `club.id` afterwards is a lazy load in the wrong place —
    # the MissingGreenlet trap this repo has hit before.
    club_id = club.id
    s = await _owned_session(db, session_id, club_id)

    pid = None
    guest = None
    if body.player_id:
        try:
            cand = uuid.UUID(str(body.player_id))
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="Unknown player")
        p = await db.get(Player, cand)
        if not p or p.organisation_id != club_id:
            raise HTTPException(status_code=422, detail="Unknown player")
        existing = await db.execute(
            select(NetAttendance).where(
                NetAttendance.session_id == s.id,
                NetAttendance.player_id == cand,
            )
        )
        if existing.scalar_one_or_none() is not None:
            return await _live_payload(db, s)
        pid = cand
    else:
        guest = (body.guest_name or "").strip()[:80]
        if not guest:
            raise HTTPException(status_code=422, detail="Give the guest a name")

    rows = await _attendee_rows(db, s.id)
    waiting = [r for r in rows if not r.batted]
    db.add(NetAttendance(
        id=uuid.uuid4(),
        session_id=s.id,
        organisation_id=club_id,
        player_id=pid,
        guest_name=guest,
        batted=False,
        position=len(waiting),
    ))
    try:
        await db.flush()
    except IntegrityError:
        # Two coaches tapped the same name in the same second, so the read above
        # couldn't see the other's row yet and the unique index caught it. Same
        # answer as the check above: they're in, once. Verified by racing three
        # simultaneous check-ins of one player against a real Postgres.
        await db.rollback()
        s = await _owned_session(db, session_id, club_id)
        return await _live_payload(db, s)
    await _renumber(db, s.id)
    return await _commit_live(db, s)


async def _owned_attendee(db: AsyncSession, s: NetSession, attendee_id: str) -> NetAttendance:
    try:
        aid = uuid.UUID(str(attendee_id))
    except (TypeError, ValueError):
        raise HTTPException(status_code=404, detail="Not in this session")
    r = await db.get(NetAttendance, aid)
    if not r or r.session_id != s.id:
        raise HTTPException(status_code=404, detail="Not in this session")
    return r


@router.delete("/sessions/{session_id}/attendees/{attendee_id}")
async def remove_attendee(
    session_id: str,
    attendee_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """Take someone back out of the session. Already gone (another device got
    there first) reads as done, not as an error."""
    s = await _owned_session(db, session_id, club.id)
    try:
        aid = uuid.UUID(str(attendee_id))
    except (TypeError, ValueError):
        raise HTTPException(status_code=404, detail="Not in this session")
    r = await db.get(NetAttendance, aid)
    if r is None or r.session_id != s.id:
        return await _live_payload(db, s)
    await db.delete(r)
    await db.flush()
    await _renumber(db, s.id)
    return await _commit_live(db, s)


@router.patch("/sessions/{session_id}/attendees/{attendee_id}")
async def patch_attendee(
    session_id: str,
    attendee_id: str,
    body: AttendeePatch,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """Mark one attendee as having had their turn, or send them back to the
    queue. Sending someone back puts them at the END of it, which is what the
    manager means by "they need another go"."""
    s = await _owned_session(db, session_id, club.id)
    r = await _owned_attendee(db, s, attendee_id)
    if body.batted is not None and bool(r.batted) != bool(body.batted):
        r.batted = bool(body.batted)
        if not r.batted:
            rows = await _attendee_rows(db, s.id)
            r.position = sum(1 for x in rows if not x.batted and x.id != r.id)
        await db.flush()
        await _renumber(db, s.id)
    return await _commit_live(db, s)


@router.post("/sessions/{session_id}/queue")
async def reorder_queue(
    session_id: str,
    body: QueueOrder,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """Re-order the waiting queue. The list comes from a browser, so ids that
    aren't in this session are ignored, and anyone the sending device didn't
    know about — checked in from another phone a second ago — keeps their place
    at the back rather than being dropped.
    """
    s = await _owned_session(db, session_id, club.id)
    rows = await _attendee_rows(db, s.id)
    waiting = {str(r.id): r for r in rows if not r.batted}

    ordered: list[NetAttendance] = []
    seen: set[str] = set()
    for raw in body.ids:
        key = str(raw)
        if key in waiting and key not in seen:
            seen.add(key)
            ordered.append(waiting[key])
    ordered.extend(r for k, r in waiting.items() if k not in seen)

    for i, r in enumerate(ordered):
        r.position = i
    await db.flush()
    await _renumber(db, s.id)
    return await _commit_live(db, s)


async def _rotate(db: AsyncSession, s: NetSession, settings: dict, live: dict, autostart: bool) -> dict:
    """End the current turn: the batters in the nets are marked as having had
    theirs, the next group steps up and the clock resets for them."""
    rows = await _attendee_rows(db, s.id)
    waiting = [r for r in rows if not r.batted]

    group = waiting[: settings["nets"]]
    for r in group:
        r.batted = True
    await db.flush()
    await _renumber(db, s.id)

    live["turn_seq"] = int(live["turn_seq"]) + 1
    live["duration_seconds"] = settings["duration_seconds"]
    live["remaining_seconds"] = float(settings["duration_seconds"])
    # Only keep the clock rolling if batters remain after this rotation.
    if autostart and (len(waiting) - len(group)) > 0 and settings["duration_seconds"] > 0:
        live["running"] = True
        live["ends_at"] = (
            datetime.now(timezone.utc) + timedelta(seconds=settings["duration_seconds"])
        ).isoformat()
    else:
        live["running"] = False
        live["ends_at"] = None
    return live


@router.post("/sessions/{session_id}/rotate")
async def rotate_group(
    session_id: str,
    body: RotateBody,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    s = await _owned_session(db, session_id, club.id)
    settings = _clean_settings(s.settings)
    live = _clean_live(s.live_state, settings)
    if body.turn_seq is not None and int(body.turn_seq) != int(live["turn_seq"]):
        # Someone else has already rotated this turn — see RotateBody.turn_seq.
        return await _live_payload(db, s)
    autostart = settings["auto_roll"] if body.autostart is None else bool(body.autostart)
    s.live_state = await _rotate(db, s, settings, live, autostart)
    return await _commit_live(db, s)


@router.post("/sessions/{session_id}/timer")
async def timer_action(
    session_id: str,
    body: TimerAction,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """Drive the clock. Every device sees the same one, because the deadline
    lives here rather than in whichever browser pressed Start.

    `expire` is sent by whichever device notices the deadline pass — it just
    writes down what has already happened, so several devices sending it at
    once is harmless.
    """
    s = await _owned_session(db, session_id, club.id)
    settings = _clean_settings(s.settings)
    live = _clean_live(s.live_state, settings)
    now = datetime.now(timezone.utc)

    if body.duration_seconds is not None:
        try:
            live["duration_seconds"] = max(30, min(7200, int(body.duration_seconds)))
        except (TypeError, ValueError):
            pass

    action = (body.action or "").strip().lower()
    if action == "start":
        if live["running"]:
            ends = _parse_iso(live["ends_at"])
            if ends and (ends - now).total_seconds() > 0:
                # Already counting down on another device — leave it alone
                # rather than restarting the batter's turn under them.
                return await _live_payload(db, s)
        secs = live["remaining_seconds"]
        if body.duration_seconds is not None or secs <= 0:
            secs = float(live["duration_seconds"])
        if secs <= 0:
            raise HTTPException(status_code=422, detail="Nothing to count down")
        live["running"] = True
        live["ends_at"] = (now + timedelta(seconds=secs)).isoformat()
        live["remaining_seconds"] = secs
    elif action == "pause":
        ends = _parse_iso(live["ends_at"])
        live["remaining_seconds"] = max(0.0, (ends - now).total_seconds()) if (live["running"] and ends) else live["remaining_seconds"]
        live["running"] = False
        live["ends_at"] = None
    elif action == "reset":
        live["running"] = False
        live["ends_at"] = None
        live["remaining_seconds"] = float(live["duration_seconds"])
        live["turn_seq"] = int(live["turn_seq"]) + 1
    elif action == "expire":
        if not live["running"]:
            return await _live_payload(db, s)
        ends = _parse_iso(live["ends_at"])
        if ends and (ends - now).total_seconds() > 1:
            # A device with a fast clock got ahead of the real deadline.
            return await _live_payload(db, s)
        live["running"] = False
        live["ends_at"] = None
        live["remaining_seconds"] = 0.0
        if settings["auto_roll"]:
            # Auto-roll happens HERE rather than on the device that noticed the
            # clock run out. Every open screen notices within a second of each
            # other, and a rotation repeated is a whole group of batters skipped
            # — so the one write that stops the clock does the rotation too.
            live = await _rotate(db, s, settings, live, True)
    else:
        raise HTTPException(status_code=422, detail="Unknown timer action")

    s.live_state = live
    return await _commit_live(db, s)


# ── Reports ───────────────────────────────────────────────────────────────────
async def _attendance_rows(db: AsyncSession, club_id, days: int) -> tuple[int, list[dict]]:
    """Per-player net attendance: sessions attended, turns batted, the date they
    were last at nets, and what share of the sessions held they turned up to.

    `days` of 0 means all time. Guests are excluded — the report is keyed on
    real players, because it links to their profiles.
    """
    since = None if days <= 0 else date.today() - timedelta(days=days)

    sc_q = select(func.count(NetSession.id)).where(NetSession.organisation_id == club_id)
    if since is not None:
        sc_q = sc_q.where(NetSession.session_date >= since)
    session_count = int((await db.execute(sc_q)).scalar() or 0)

    rows = await db.execute(
        text(
            """
            SELECT a.player_id,
                   COUNT(DISTINCT a.session_id) AS attended,
                   COUNT(DISTINCT a.session_id) FILTER (WHERE a.batted) AS batted,
                   MAX(s.session_date) AS last_attended
            FROM net_attendance a
            JOIN net_sessions s ON s.id = a.session_id
            WHERE a.organisation_id = :org
              AND a.player_id IS NOT NULL
              AND (CAST(:since AS date) IS NULL OR s.session_date >= CAST(:since AS date))
            GROUP BY a.player_id
            ORDER BY attended DESC, batted DESC
            """
        ),
        {"org": club_id, "since": since},
    )
    agg = rows.fetchall()

    pmap: dict = {}
    pids = [r[0] for r in agg]
    if pids:
        pr = await db.execute(select(Player).where(Player.id.in_(pids)))
        pmap = {p.id: p for p in pr.scalars().all()}

    players = []
    for pid, attended, batted, last_attended in agg:
        p = pmap.get(pid)
        if not p:
            continue
        players.append({
            "player_id": str(pid),
            "name": p.display_name,
            "photo_url": p.photo_url,
            "skill_positions": p.skill_positions or [],
            "attended": int(attended),
            "batted": int(batted or 0),
            "last_attended": last_attended.isoformat() if last_attended else None,
            "attendance_pct": round(100 * attended / session_count) if session_count else 0,
        })
    # Same person, same number of sessions — read them alphabetically rather
    # than in whatever order the group-by happened to hand back.
    players.sort(key=lambda r: (-r["attended"], -r["batted"], (r["name"] or "").lower()))
    return session_count, players


@router.get("/reports/attendance")
async def attendance_report(
    days: int = Query(120, ge=0, le=3650, description="0 = all time"),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    session_count, players = await _attendance_rows(db, club.id, days)
    return {"days": days, "session_count": session_count, "players": players}


def _csv_response(header: list[str], rows: list[list], filename: str) -> StreamingResponse:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerows(rows)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _safe_slug(text_in: Optional[str], fallback: str) -> str:
    keep = [c if (c.isalnum() or c in "-_") else "-" for c in (text_in or "")]
    slug = "".join(keep).strip("-").lower()
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug[:48] or fallback


@router.get("/reports/attendance.csv")
async def attendance_report_csv(
    days: int = Query(120, ge=0, le=3650, description="0 = all time"),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """The attendance report as a spreadsheet — a club that wants to hand the
    list to a coach or a selection meeting shouldn't have to retype it."""
    session_count, players = await _attendance_rows(db, club.id, days)
    rows = [
        [
            p["name"],
            p["attended"],
            p["batted"],
            f'{p["attendance_pct"]}%',
            p["last_attended"] or "",
        ]
        for p in players
    ]
    rows.append([])
    rows.append([
        "Sessions held in range", session_count, "", "",
        "All time" if days <= 0 else f"Last {days} days",
    ])
    return _csv_response(
        ["Player", "Sessions attended", "Turns batted", "Attendance rate", "Last session"],
        rows,
        f"net-attendance-{_safe_slug(club.short_name or club.name, 'club')}-"
        f"{'all-time' if days <= 0 else str(days) + 'd'}.csv",
    )


@router.get("/sessions/{session_id}/attendance.csv")
async def session_attendance_csv(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Who turned up to one session, in queue order. Guests are included here —
    unlike the per-player report, this is the register for the night, and a
    trialist who came along is part of it."""
    s = await _owned_session(db, session_id, club.id)
    payload = await _live_payload(db, s)
    rows = [
        [
            i + 1,
            a["name"],
            "Guest" if a["is_guest"] else "Player",
            "Yes" if a["batted"] else "No",
        ]
        for i, a in enumerate(payload["attendees"])
    ]
    label = payload["label"] or "net-session"
    return _csv_response(
        ["#", "Player", "Type", "Batted"],
        rows,
        f"{_safe_slug(label, 'net-session')}-{payload['session_date'] or 'undated'}.csv",
    )


@router.get("/players/{player_id}/attendance")
async def player_attendance(
    player_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """One player's net attendance — the tally that hangs off their BetterSelect
    profile, and every session behind it, so the tally can be opened up into the
    dates rather than just being a number to take on trust."""
    try:
        pid = uuid.UUID(str(player_id))
    except (TypeError, ValueError):
        raise HTTPException(status_code=404, detail="Player not found")

    p = await db.get(Player, pid)
    if not p or p.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Player not found")

    rec = await db.execute(
        text(
            """
            SELECT s.id, s.session_date, s.label, a.batted
            FROM net_attendance a
            JOIN net_sessions s ON s.id = a.session_id
            WHERE a.organisation_id = :org AND a.player_id = :pid
            ORDER BY s.session_date DESC, s.created_at DESC
            LIMIT 500
            """
        ),
        {"org": club.id, "pid": pid},
    )
    sessions = [
        {
            "session_id": str(sid),
            "session_date": d.isoformat() if d else None,
            "label": lbl,
            "batted": bool(b),
        }
        for sid, d, lbl, b in rec.fetchall()
    ]
    return {
        "attended": len(sessions),
        "batted": sum(1 for x in sessions if x["batted"]),
        "last_attended": sessions[0]["session_date"] if sessions else None,
        "sessions": sessions,
    }
