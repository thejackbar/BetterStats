"""BetterSelect → Net Manager.

A tracker for net (practice) sessions: who turned up, who batted, the batting
queue and timer the manager runs pitch-side, and the attendance reports that
surface in BetterSelect and on the player profile.

  * net_sessions    — one training day (date + optional label + timer settings),
                      plus the LIVE state: the batting timer and a version
                      counter every write bumps
  * net_attendance  — one attendee per session (real player OR an ad-hoc guest);
                      the row's existence = "turned up", `batted` = completed a
                      turn, `bats` = in the batting rotation at all (someone can
                      be here and sitting out), `position` = where they sit in
                      the queue

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

Running the night and taking the check-in are two jobs, and one person doing
both on one screen is what a club reported back. `check_in_person` here is the
one write behind both, and `public_net_checkin.py` puts it on a per-club link
for the QR code on the fence so players check themselves in.

All endpoints are scoped to the caller's club via get_current_club and gated by
the MANAGE_SELECTIONS capability (same as the rest of BetterSelect), except the
reads, which any club admin may open. The whole router sits behind
require_module("select") at registration in main.py.
"""
from __future__ import annotations

import csv
import io
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import (
    MANAGE_PLAYERS, MANAGE_SELECTIONS, require_any_cap, require_cap,
)
from app.models.db import (
    NetAttendance, NetCheckInRegistration, NetSession, Organisation, Player, User, get_db,
)
from app.routers.auth import get_current_club
from app.routers.availability import (
    DEFAULT_DORMANCY_MONTHS, active_self_service_players, club_player_roster,
    dormant_player_ids, phone_last4,
)

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


def _player_card(p: Player, dormant: bool = False) -> dict:
    """One name on the check-in list.

    `dormant` and `inactive` say why a name isn't in the current squad; neither
    hides it. See net_roster for why that matters.
    """
    return {
        "id": str(p.id),
        "name": p.display_name,
        "photo_url": p.photo_url,
        "skill_positions": p.skill_positions or [],
        "batting_hand": p.batting_hand,
        "dormant": bool(dormant),
        "inactive": p.status == "inactive",
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
    # Here, but not batting — carrying a knock, bowling only, keeping. They still
    # count as having turned up; they just aren't put in the queue.
    bats: Optional[bool] = None
    note: Optional[str] = None


class AttendeePatch(BaseModel):
    batted: Optional[bool] = None
    bats: Optional[bool] = None
    note: Optional[str] = None


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


# The same bump, under a name the public check-in router can import without
# reaching for a private one. A self check-in has to move the version too, or
# the iPad's next poll is told nothing changed and never shows the arrival.
touch_session = _touch


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


def _waiting(rows: list[NetAttendance]) -> list[NetAttendance]:
    """The batting queue: present, not yet had a turn, and actually batting.

    Someone sitting out (`bats` false — carrying a knock, here to bowl, keeping)
    is NOT in it. Leaving them in leaves a net standing empty when their name
    comes up, which is the thing the queue exists to prevent. They are still
    attendees, so the register and the club's report still say they were here.
    """
    return [r for r in rows if not r.batted and r.bats]


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
            "bats": bool(r.bats),
            "note": r.note,
            "source": r.source or "admin",
            "position": r.position,
            # 'admin' or 'self' — what lets the live screen announce someone
            # who scanned themselves in and stay quiet for a name the manager
            # just tapped. Rows written before migration 272 read 'admin',
            # which is what they were.
            "source": r.source or "admin",
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
        "sitting_out_count": sum(1 for a in attendees if not a["bats"]),
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


async def live_sessions(db: AsyncSession, club_id) -> list[NetSession]:
    """The sessions a person scanning the QR code right now should be added to.

    Every ACTIVE session dated within a day either side of today. Not just
    "today": the app holds no per-club timezone, so a club whose evening is the
    server's tomorrow would otherwise scan in to nothing, and a session opened
    the night before for an early start is an ordinary thing to do. The window
    is deliberately narrow at both ends — a session somebody forgot to mark
    done last week must not quietly collect tonight's arrivals.

    Ordered oldest-first so a club running two overlapping sessions gets a
    stable answer whichever device asks.
    """
    today = datetime.now(timezone.utc).date()
    res = await db.execute(
        select(NetSession)
        .where(
            NetSession.organisation_id == club_id,
            NetSession.status == "active",
            NetSession.session_date >= today - timedelta(days=1),
            NetSession.session_date <= today + timedelta(days=1),
        )
        .order_by(NetSession.session_date.asc(), NetSession.created_at.asc())
    )
    return list(res.scalars().all())


async def check_in_person(
    db: AsyncSession,
    s: NetSession,
    club_id,
    *,
    player_id=None,
    guest_name: Optional[str] = None,
    source: str = "admin",
    bats: bool = True,
    note: Optional[str] = None,
) -> Optional[NetAttendance]:
    """Put one person at the back of a session's queue, and flush.

    The ONE place a check-in is written, shared by the manager tapping a name
    on the iPad and by the player scanning the QR code on the way in — two
    copies of this is how the two paths start disagreeing about what a
    check-in is.

    Returns the new row, or None when the person was already checked in. That
    is a no-op rather than an error at both levels: an app-level read for the
    ordinary case, and IntegrityError on the unique index for two devices
    landing in the same second. **The caller must not touch a lazily-loaded
    attribute after a None caused by the rollback** — that path expires every
    loaded object, which is why club_id is passed in rather than read off the
    club here.

    Does not commit. The caller decides, because a self check-in writes
    several sessions' rows in one transaction.
    """
    if player_id is not None:
        existing = await db.execute(
            select(NetAttendance).where(
                NetAttendance.session_id == s.id,
                NetAttendance.player_id == player_id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            return None

    rows = await _attendee_rows(db, s.id)
    row = NetAttendance(
        id=uuid.uuid4(),
        session_id=s.id,
        organisation_id=club_id,
        player_id=player_id,
        guest_name=guest_name,
        batted=False,
        # Present but out of the rotation: here to bowl, keeping, or carrying a
        # knock. They still count as having turned up; they just aren't queued.
        bats=bool(bats),
        note=((note or "").strip()[:120] or None),
        position=len(_waiting(rows)),
        source=source if source in ("admin", "self") else "admin",
    )
    db.add(row)
    try:
        await db.flush()
    except IntegrityError:
        # Two people tapped the same name in the same second, so the read above
        # couldn't see the other's row yet and the unique index caught it. Same
        # answer as the check above: they're in, once.
        await db.rollback()
        return None
    return row


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
    """EVERY player on the club's books, each tagged with why they are or aren't
    in the current squad. The check-in list must never be missing a name.

    This used to be `active_self_service_players`, which drops anyone who last
    appeared before the club's dormancy window opened — so a player reading as
    active on Admin → Players was simply absent from check-in, with nothing on
    screen to say why, and the only way to record them was as a guest under
    their own name. Reported from a club's Thursday nets, and dormancy is only
    one of the reasons a name could go missing: a player between clubs, one
    marked inactive over winter, or anyone whose games are logged under another
    record all read the same way to the person holding the iPad.

    So nothing is filtered out here. `dormant` and `inactive` are flags the
    screen groups by, not exclusions — the current squad is what it shows
    first, and every other name is one search away instead of unreachable.
    """
    players = await club_player_roster(db, club)
    dormant = await dormant_player_ids(db, club)
    cards = [_player_card(p, p.id in dormant) for p in players]
    return {
        "players": cards,
        # What the screen shows before anyone searches, so it can say how many
        # more names are behind the search box rather than implying the squad
        # is the whole club.
        "squad_count": sum(1 for c in cards if not c["dormant"] and not c["inactive"]),
        "dormancy_months": club.dormancy_months or DEFAULT_DORMANCY_MONTHS,
    }


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
    """Check one person in from the admin screen, at the back of the queue.

    `bats=False` records someone who is here but not batting. Checking in
    somebody already in the session is a no-op rather than an error — two
    devices tapping the same name at once is ordinary at a net session — and it
    is NOT a way to quietly rewrite their state: they keep whatever the coach
    last set, so a stray tap can't put a player marked as sitting out back into
    the rotation.
    """
    # Read the club id up front: the rollback inside check_in_person expires
    # every loaded object, and reaching for `club.id` afterwards is a lazy load
    # in the wrong place — the MissingGreenlet trap this repo has hit before.
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
        pid = cand
    else:
        guest = (body.guest_name or "").strip()[:80]
        if not guest:
            raise HTTPException(status_code=422, detail="Give the guest a name")

    row = await check_in_person(
        db, s, club_id, player_id=pid, guest_name=guest, source="admin",
        bats=True if body.bats is None else bool(body.bats),
        note=body.note,
    )
    if row is None:
        # Already in, or the unique index caught a simultaneous tap — and that
        # path rolled back, so re-read the session rather than using the stale
        # object. Verified by racing three simultaneous check-ins of one player
        # against a real Postgres.
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
    """Mark one attendee as having had their turn, send them back to the queue,
    or move them in or out of the rotation.

    Both re-entry paths put them at the END of the queue — "they need another
    go" and "his shoulder has loosened up, put him in" both mean the back of
    the line, not a place ahead of someone who has been waiting.
    """
    s = await _owned_session(db, session_id, club.id)
    r = await _owned_attendee(db, s, attendee_id)
    changed = False

    if body.note is not None:
        note = (body.note or "").strip()[:120] or None
        if note != r.note:
            r.note = note
            changed = True

    rejoined = False
    if body.bats is not None and bool(r.bats) != bool(body.bats):
        r.bats = bool(body.bats)
        rejoined = r.bats
        changed = True
    if body.batted is not None and bool(r.batted) != bool(body.batted):
        r.batted = bool(body.batted)
        rejoined = rejoined or not r.batted
        changed = True

    if rejoined and not r.batted and r.bats:
        rows = await _attendee_rows(db, s.id)
        r.position = sum(1 for x in _waiting(rows) if x.id != r.id)

    if changed:
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
    waiting = {str(r.id): r for r in _waiting(rows)}

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
    waiting = _waiting(rows)

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
            "Sitting out" if not a["bats"] else "",
            a["note"] or "",
            "Self" if a["source"] == "self" else "Coach",
        ]
        for i, a in enumerate(payload["attendees"])
    ]
    label = payload["label"] or "net-session"
    return _csv_response(
        ["#", "Player", "Type", "Batted", "Rotation", "Note", "Checked in by"],
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


# ── The self check-in link (QR code / NFC tag) ───────────────────────────────
# Mirrors availability's self-service panel: the backend hands back a PATH and
# the admin screen prefixes window.location.origin, so one token serves the
# printed QR code and the NFC tag alike. The public side of this lives in
# routers/public_net_checkin.py.
class CheckInLinkUpdate(BaseModel):
    enabled: Optional[bool] = None
    require_pin: Optional[bool] = None
    allow_registration: Optional[bool] = None


async def _checkin_link_payload(db: AsyncSession, club: Organisation) -> dict:
    players = await active_self_service_players(db, club)
    with_phone = sum(1 for p in players if phone_last4(p.phone))
    pending = await db.execute(
        select(func.count(NetCheckInRegistration.id)).where(
            NetCheckInRegistration.organisation_id == club.id,
            NetCheckInRegistration.status == "pending",
        )
    )
    return {
        "enabled": bool(club.net_checkin_enabled),
        "require_pin": bool(club.net_checkin_require_pin),
        "allow_registration": bool(club.net_checkin_allow_registration),
        "token": club.net_checkin_token,
        "path": f"/nets-checkin/{club.net_checkin_token}" if club.net_checkin_token else None,
        # A club whose players have no phone numbers on file cannot use the PIN
        # gate, and should be told that before they turn it on rather than
        # after nobody can check in.
        "phone_coverage": {"with_phone": with_phone, "total": len(players)},
        "pending_registrations": int(pending.scalar() or 0),
    }


@router.get("/checkin-link")
async def get_checkin_link(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    return await _checkin_link_payload(db, club)


@router.post("/checkin-link")
async def set_checkin_link(
    body: CheckInLinkUpdate,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    if body.enabled is not None:
        club.net_checkin_enabled = bool(body.enabled)
    if body.require_pin is not None:
        club.net_checkin_require_pin = bool(body.require_pin)
    if body.allow_registration is not None:
        club.net_checkin_allow_registration = bool(body.allow_registration)
    # Minted lazily on first enable, so a club that never turns this on never
    # has a live link sitting on its row.
    if club.net_checkin_enabled and not club.net_checkin_token:
        club.net_checkin_token = secrets.token_urlsafe(24)
    await db.commit()
    await db.refresh(club)
    return await _checkin_link_payload(db, club)


@router.post("/checkin-link/regenerate")
async def regenerate_checkin_link(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """New token. Every printed QR code and every NFC tag already stuck to the
    gate stops working the moment this returns — which is the point, and why
    the screen confirms first."""
    club.net_checkin_token = secrets.token_urlsafe(24)
    await db.commit()
    await db.refresh(club)
    return await _checkin_link_payload(db, club)


# ── New people who scanned in ────────────────────────────────────────────────
class RegistrationDecision(BaseModel):
    # Set to fold this registration into somebody already on the roster (they
    # were here all along under a different spelling). Omitted, a new player
    # row is created from what they typed.
    player_id: Optional[str] = None


def _registration_card(r: NetCheckInRegistration, player_name: Optional[str] = None) -> dict:
    return {
        "id": str(r.id),
        "full_name": r.full_name,
        "phone": r.phone,
        "email": r.email,
        "date_of_birth": r.date_of_birth.isoformat() if r.date_of_birth else None,
        "previous_club": r.previous_club,
        "status": r.status,
        "player_id": str(r.player_id) if r.player_id else None,
        "player_name": player_name,
        "session_id": str(r.session_id) if r.session_id else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
    }


@router.get("/registrations")
async def list_registrations(
    status: str = Query("pending"),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Everyone who scanned in without being on the list, newest first."""
    q = select(NetCheckInRegistration).where(
        NetCheckInRegistration.organisation_id == club.id
    )
    if status in ("pending", "approved", "dismissed"):
        q = q.where(NetCheckInRegistration.status == status)
    res = await db.execute(
        q.order_by(NetCheckInRegistration.created_at.desc()).limit(limit)
    )
    rows = list(res.scalars().all())

    names: dict = {}
    pids = [r.player_id for r in rows if r.player_id]
    if pids:
        pr = await db.execute(select(Player).where(Player.id.in_(pids)))
        names = {p.id: p.display_name for p in pr.scalars().all()}

    pending = await db.execute(
        select(func.count(NetCheckInRegistration.id)).where(
            NetCheckInRegistration.organisation_id == club.id,
            NetCheckInRegistration.status == "pending",
        )
    )
    return {
        "registrations": [_registration_card(r, names.get(r.player_id)) for r in rows],
        "pending_count": int(pending.scalar() or 0),
    }


async def _owned_registration(db: AsyncSession, reg_id: str, club_id) -> NetCheckInRegistration:
    try:
        rid = uuid.UUID(str(reg_id))
    except (TypeError, ValueError):
        raise HTTPException(status_code=404, detail="Registration not found")
    r = await db.get(NetCheckInRegistration, rid)
    if not r or r.organisation_id != club_id:
        raise HTTPException(status_code=404, detail="Registration not found")
    return r


@router.post("/registrations/{reg_id}/approve")
async def approve_registration(
    reg_id: str,
    body: RegistrationDecision,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """Turn a scanned-in stranger into a real player.

    Either creates a player from what they typed, or — with `player_id` —
    points the registration at somebody already on the roster who turned out
    to be the same person under a different spelling.

    **Their guest attendance row is converted, never duplicated**: the row that
    already says they turned up tonight has its `player_id` filled in and its
    `guest_name` cleared, so the session they scanned into keeps exactly the
    attendance it had and the night now counts towards the player's own tally.
    A club that already had that player checked in separately keeps the
    original row and the guest row is dropped, since the unique index would
    refuse the pair and two rows for one person is the wrong answer anyway.
    """
    club_id = club.id
    r = await _owned_registration(db, reg_id, club_id)
    if r.status != "pending":
        raise HTTPException(status_code=409, detail="Already dealt with")

    if body.player_id:
        try:
            cand = uuid.UUID(str(body.player_id))
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="Unknown player")
        player = await db.get(Player, cand)
        if not player or player.organisation_id != club_id:
            raise HTTPException(status_code=422, detail="Unknown player")
    else:
        # Stored "Last, First" like every other player row, so the roster sorts
        # and reads the same however the person got there. A mononym is stored
        # as typed — same rule the rest of the app follows.
        typed = (r.full_name or "").strip()
        parts = typed.split()
        name = f"{parts[-1]}, {' '.join(parts[:-1])}" if len(parts) > 1 else typed
        player = Player(
            id=uuid.uuid4(),
            organisation_id=club_id,
            name=name or typed,
            phone=r.phone,
            email=r.email,
            date_of_birth=r.date_of_birth,
            status="active",
        )
        db.add(player)
        await db.flush()

    touched: list[NetSession] = []
    if r.attendance_id:
        row = await db.get(NetAttendance, r.attendance_id)
        if row is not None and row.organisation_id == club_id:
            clash = await db.execute(
                select(NetAttendance).where(
                    NetAttendance.session_id == row.session_id,
                    NetAttendance.player_id == player.id,
                )
            )
            s = await db.get(NetSession, row.session_id)
            if clash.scalar_one_or_none() is not None:
                # They were already checked in properly as well. Keep the real
                # row, drop the duplicate guest one.
                await db.delete(row)
            else:
                row.player_id = player.id
                row.guest_name = None
            if s is not None:
                touched.append(s)

    r.status = "approved"
    r.player_id = player.id
    r.reviewed_by = user.id
    r.reviewed_at = datetime.now(timezone.utc)

    for s in touched:
        _touch(s)
    await db.commit()
    return {
        "status": "ok",
        "player_id": str(player.id),
        "player_name": player.display_name,
    }


@router.post("/registrations/{reg_id}/dismiss")
async def dismiss_registration(
    reg_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """Not someone the club wants on the roster.

    The guest attendance row is deliberately LEFT ALONE. They did turn up, the
    session's own record of the night should say so, and dismissing a
    registration is a decision about the roster rather than a claim that the
    evening did not happen.
    """
    r = await _owned_registration(db, reg_id, club.id)
    if r.status != "pending":
        raise HTTPException(status_code=409, detail="Already dealt with")
    r.status = "dismissed"
    r.reviewed_by = user.id
    r.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "ok"}


# ── Guests who are not on the roster ─────────────────────────────────────────
# A guest row (player_id NULL + guest_name) is written two ways: a manager types
# a name on the live screen, or somebody scans the QR code and registers. The
# second kind lands in the Check-in queue above with the details they gave. The
# FIRST kind had nowhere to go at all — they turned up week after week and could
# never become a player without an admin retyping them by hand, which stranded
# every night they had already attended on rows nothing would ever read.
#
# This is that missing path, surfaced on the Players screens rather than here:
# a person who keeps turning up is a roster question, not a net-session one.
GUEST_WINDOW_DAYS = 90


def _guest_key(name: str) -> str:
    """One guest across several nights, however the name was typed.

    Case and surrounding space only — deliberately NOT a fuzzy match. Two
    people really can be typed in as the same name, and quietly merging
    "J Smith" into "Jack Smith" would put one person's attendance on another.
    """
    return " ".join((name or "").split()).casefold()


@router.get("/guests")
async def list_unresolved_guests(
    days: int = Query(GUEST_WINDOW_DAYS, ge=0, le=3650),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Guests from recent sessions who are not on the roster, grouped by name.

    Grouped because the question is about a PERSON — "this bloke has been to
    five sessions, should he be on the list" — not about five separate rows.

    Anyone carrying a PENDING registration is deliberately left out and
    reported as a count instead. They already sit in the Check-in queue WITH
    the details they typed, and one person offered in two places, with
    different information behind each, is how the two screens start disagreeing
    about who they are. The panel links across rather than duplicating them.

    days=0 means all time.
    """
    params: dict = {"org": club.id}
    since_clause = ""
    if days:
        params["since"] = datetime.now(timezone.utc).date() - timedelta(days=days)
        since_clause = "AND s.session_date >= :since"

    rows = (await db.execute(
        text(
            f"""
            SELECT a.id, a.guest_name, s.id AS session_id, s.session_date, s.label,
                   (r.id IS NOT NULL) AS has_pending
            FROM net_attendance a
            JOIN net_sessions s ON s.id = a.session_id
            LEFT JOIN net_checkin_registrations r
                   ON r.attendance_id = a.id AND r.status = 'pending'
            WHERE a.organisation_id = :org
              AND a.player_id IS NULL
              AND a.guest_name IS NOT NULL
              {since_clause}
            ORDER BY s.session_date DESC, s.created_at DESC
            """
        ),
        params,
    )).fetchall()

    grouped: dict = {}
    pending = 0
    for _aid, name, sid, sdate, label, has_pending in rows:
        if has_pending:
            # Theirs is the Check-in queue's decision to make, not this one's.
            pending += 1
            continue
        key = _guest_key(name)
        if not key:
            continue
        g = grouped.setdefault(key, {
            # The most recent spelling wins: rows come back newest first, so
            # this is whatever the club typed last.
            "name": " ".join((name or "").split()),
            "sessions": [],
        })
        g["sessions"].append({
            "id": str(sid),
            "session_date": sdate.isoformat() if sdate else None,
            "label": label,
        })

    guests = [
        {
            "key": k,
            "name": g["name"],
            "attended": len(g["sessions"]),
            "last_attended": g["sessions"][0]["session_date"] if g["sessions"] else None,
            "sessions": g["sessions"][:12],
        }
        for k, g in grouped.items()
    ]
    # Most-seen first — the person who keeps turning up is the one to action —
    # then most recent. Two passes because Python's sort is stable, which is
    # simpler to read than inverting a date string inside one key.
    guests.sort(key=lambda x: x["last_attended"] or "", reverse=True)
    guests.sort(key=lambda x: -x["attended"])
    return {
        "guests": guests,
        "days": days,
        "pending_registrations": pending,
    }


class GuestPromote(BaseModel):
    # Which guest, by the same key the list hands back — never a raw name off a
    # browser, so the server decides for itself which rows that key covers.
    key: str
    # Match them to somebody already on the roster. Omitted, a player is created.
    player_id: Optional[str] = None
    # Only used when creating: the club may correct the spelling on the way in.
    name: Optional[str] = None


@router.post("/guests/promote")
async def promote_guest(
    body: GuestPromote,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_any_cap(MANAGE_SELECTIONS, MANAGE_PLAYERS)),
):
    """Turn a guest into a player, and take their attendance history with them.

    Either creates a player from the name, or points the guest at somebody
    already on the roster who turns out to be the same person.

    **Every one of their guest rows moves, not just the recent ones the list
    was showing.** The window is a filter for who is worth looking at; a person
    joining the club should not leave half their nights behind on rows nothing
    reads. Where they are already checked in properly for a session, the real
    row is kept and the duplicate guest row is dropped — the unique index would
    refuse the pair, and two rows for one person is the wrong answer anyway.

    Gated on EITHER capability: a selections manager runs the nets and can
    already do this from the Check-in tab, and a player manager owns the roster.
    The panel is on both Players screens for exactly that reason.
    """
    club_id = club.id
    key = _guest_key(body.key)
    if not key:
        raise HTTPException(status_code=422, detail="Which guest?")

    # Resolve the key against this club's own rows — never trust a name.
    rows = (await db.execute(
        select(NetAttendance).where(
            NetAttendance.organisation_id == club_id,
            NetAttendance.player_id.is_(None),
            NetAttendance.guest_name.isnot(None),
        )
    )).scalars().all()
    mine = [r for r in rows if _guest_key(r.guest_name) == key]
    if not mine:
        raise HTTPException(status_code=404, detail="That guest is no longer in any session")

    if body.player_id:
        try:
            cand = uuid.UUID(str(body.player_id))
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="Unknown player")
        player = await db.get(Player, cand)
        if not player or player.organisation_id != club_id:
            raise HTTPException(status_code=422, detail="Unknown player")
    else:
        typed = (body.name or mine[0].guest_name or "").strip()[:80]
        if len(typed) < 2:
            raise HTTPException(status_code=422, detail="Give them a name")
        # "Last, First" like every other player row, so the roster sorts and
        # reads the same however the person got there. A mononym stays as typed.
        parts = typed.split()
        stored = f"{parts[-1]}, {' '.join(parts[:-1])}" if len(parts) > 1 else typed
        player = Player(
            id=uuid.uuid4(), organisation_id=club_id, name=stored, status="active",
        )
        db.add(player)
        await db.flush()

    # Which sessions already hold this player properly, so a converted guest
    # row can't collide with one.
    held = {
        sid for (sid,) in (await db.execute(
            select(NetAttendance.session_id).where(
                NetAttendance.player_id == player.id,
                NetAttendance.session_id.in_([r.session_id for r in mine]),
            )
        )).fetchall()
    }

    moved = dropped = 0
    touched: dict = {}
    for r in mine:
        if r.session_id in held:
            await db.delete(r)
            dropped += 1
        else:
            r.player_id = player.id
            r.guest_name = None
            held.add(r.session_id)   # two guest rows for one night collapse to one
            moved += 1
        touched[r.session_id] = True

    # Any registration that pointed at those rows is settled by this too, or a
    # person promoted here would sit in the Check-in queue forever.
    await db.execute(
        text(
            """
            UPDATE net_checkin_registrations
               SET status = 'approved', player_id = :pid,
                   reviewed_by = :uid, reviewed_at = NOW()
             WHERE organisation_id = :org AND status = 'pending'
               AND attendance_id = ANY(CAST(:aids AS uuid[]))
            """
        ),
        {"pid": player.id, "uid": user.id, "org": club_id,
         "aids": [str(r.id) for r in mine]},
    )

    for sid in touched:
        s = await db.get(NetSession, sid)
        if s is not None:
            _touch(s)
    await db.commit()

    return {
        "status": "ok",
        "player_id": str(player.id),
        "player_name": player.display_name,
        "sessions_moved": moved,
        "duplicates_dropped": dropped,
    }
