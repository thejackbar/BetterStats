"""BetterSelect → Net Manager.

A lightweight tracker for net (practice) sessions: who turned up, who batted,
and the per-player attendance reports that surface in BetterSelect + on the
player profile. The pitch-side batting-queue + timer the net manager runs is a
single-device, client-side state machine (see the frontend NetSession screen) —
only the durable bits live here:

  * net_sessions    — one training day (date + optional label + timer settings)
  * net_attendance  — one attendee per session (real player OR an ad-hoc guest);
                      the row's existence = "turned up", `batted` = completed a turn

All endpoints are scoped to the caller's club via get_current_club and gated by
the MANAGE_SELECTIONS capability (same as the rest of BetterSelect). The whole
router sits behind require_module("select") at registration in main.py.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import delete, func, select, text
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


class AttendeeItem(BaseModel):
    player_id: Optional[str] = None
    guest_name: Optional[str] = None
    batted: bool = False
    position: Optional[int] = None


class AttendanceSet(BaseModel):
    attendees: list[AttendeeItem] = []


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


async def _session_detail(db: AsyncSession, s: NetSession) -> dict:
    """Full payload for one session: merged settings + the attendee list with
    each real player's name/photo resolved (guests carry their own name)."""
    res = await db.execute(
        select(NetAttendance)
        .where(NetAttendance.session_id == s.id)
        .order_by(NetAttendance.position.asc().nullslast(), NetAttendance.created_at.asc())
    )
    rows = res.scalars().all()

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
    return {
        "id": str(s.id),
        "session_date": s.session_date.isoformat() if s.session_date else None,
        "label": s.label,
        "notes": s.notes,
        "status": s.status,
        "settings": _clean_settings(s.settings),
        "attendees": attendees,
        "attendee_count": len(attendees),
        "batted_count": sum(1 for a in attendees if a["batted"]),
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


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
        status="active",
        created_by=user.id,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return await _session_detail(db, s)


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    s = await _owned_session(db, session_id, club.id)
    return await _session_detail(db, s)


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
        s.settings = _clean_settings(body.settings)
    if body.status is not None and body.status in ("active", "done"):
        s.status = body.status
    s.updated_at = func.now()
    await db.commit()
    return await _session_detail(db, s)


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


# ── Attendance (the durable side of the live screen) ──────────────────────────
@router.put("/sessions/{session_id}/attendance")
async def set_attendance(
    session_id: str,
    body: AttendanceSet,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """Replace the whole attendance list for a session.

    The live screen owns the in-the-moment state (queue order, who's batting)
    in the browser; it syncs the durable snapshot here — checked-in players +
    guests, each flagged `batted` once they've had a turn, in queue order. A
    full replace keeps the client as the single source of truth and is cheap at
    net-session sizes (tens of people).
    """
    s = await _owned_session(db, session_id, club.id)

    # Resolve which player ids are really ours (ignore anything that isn't).
    owned = set()
    pr = await db.execute(select(Player.id).where(Player.organisation_id == club.id))
    owned = {r[0] for r in pr.fetchall()}

    await db.execute(delete(NetAttendance).where(NetAttendance.session_id == s.id))

    seen_players: set = set()
    pos = 0
    for item in body.attendees:
        pid = None
        if item.player_id:
            try:
                cand = uuid.UUID(str(item.player_id))
            except (TypeError, ValueError):
                continue
            if cand not in owned or cand in seen_players:
                continue
            pid = cand
            seen_players.add(cand)
            guest = None
        else:
            guest = (item.guest_name or "").strip()
            if not guest:
                continue  # neither a real player nor a named guest — skip
        db.add(NetAttendance(
            id=uuid.uuid4(),
            session_id=s.id,
            organisation_id=club.id,
            player_id=pid,
            guest_name=None if pid else guest[:80],
            batted=bool(item.batted),
            position=item.position if item.position is not None else pos,
        ))
        pos += 1

    s.updated_at = func.now()
    await db.commit()
    return await _session_detail(db, s)


# ── Reports ───────────────────────────────────────────────────────────────────
@router.get("/reports/attendance")
async def attendance_report(
    days: int = Query(120, ge=1, le=3650),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Per-player net attendance over the last `days`: sessions attended, turns
    batted, last seen and attendance % of sessions held. Guests are excluded —
    the report is keyed on real players (it links to their profiles). Ordered by
    attendance, most-frequent first (the 'who turns up most' view)."""
    since = date.today() - timedelta(days=days)

    sc_res = await db.execute(
        select(func.count(NetSession.id)).where(
            NetSession.organisation_id == club.id,
            NetSession.session_date >= since,
        )
    )
    session_count = int(sc_res.scalar() or 0)

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
              AND s.session_date >= :since
            GROUP BY a.player_id
            ORDER BY attended DESC, batted DESC
            """
        ),
        {"org": club.id, "since": since},
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
    return {"days": days, "session_count": session_count, "players": players}


@router.get("/players/{player_id}/attendance")
async def player_attendance(
    player_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """One player's net attendance — the small stat that hangs off their
    BetterSelect profile. All-time totals plus their most recent few sessions."""
    try:
        pid = uuid.UUID(str(player_id))
    except (TypeError, ValueError):
        raise HTTPException(status_code=404, detail="Player not found")

    p = await db.get(Player, pid)
    if not p or p.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Player not found")

    tot = await db.execute(
        text(
            """
            SELECT COUNT(DISTINCT a.session_id) AS attended,
                   COUNT(DISTINCT a.session_id) FILTER (WHERE a.batted) AS batted,
                   MAX(s.session_date) AS last_attended
            FROM net_attendance a
            JOIN net_sessions s ON s.id = a.session_id
            WHERE a.organisation_id = :org AND a.player_id = :pid
            """
        ),
        {"org": club.id, "pid": pid},
    )
    attended, batted, last_attended = tot.fetchone() or (0, 0, None)

    rec = await db.execute(
        text(
            """
            SELECT s.session_date, s.label, a.batted
            FROM net_attendance a
            JOIN net_sessions s ON s.id = a.session_id
            WHERE a.organisation_id = :org AND a.player_id = :pid
            ORDER BY s.session_date DESC
            LIMIT 8
            """
        ),
        {"org": club.id, "pid": pid},
    )
    recent = [
        {"session_date": d.isoformat() if d else None, "label": lbl, "batted": bool(b)}
        for d, lbl, b in rec.fetchall()
    ]
    return {
        "attended": int(attended or 0),
        "batted": int(batted or 0),
        "last_attended": last_attended.isoformat() if last_attended else None,
        "recent": recent,
    }
