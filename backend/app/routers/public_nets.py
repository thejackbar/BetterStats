"""BetterSelect — net session self check-in (public, unauthenticated).

The iPad by the door. A club reported that taking the check-in and running the
batting timer on one screen doesn't work: the person at the nets is watching a
clock and a queue while a stream of players arrives wanting to be ticked off.
This is the other half of that — one per-club link, opened on a spare device,
where players tap their own name on the way in.

  * **link token** — scopes the page to a club and nothing else. It names no
    session: it resolves to whichever session is open TODAY, which is what lets
    a club print the QR once and stick it on the clubroom wall rather than
    reprinting it every week. Rotatable, and low-trust by design.
  * **PIN** (last 4 of `Player.phone`) — optional, and OFF by default, which is
    the opposite call to the availability link. That link goes in a group chat
    and writes a player's own answer about the weekend; this one is a supervised
    device in the clubroom writing down who walked in, and a PIN on every tap
    would put the queue back at the door. A club that wants it can have it.
  * **no session cookie** — deliberately. This is a SHARED device: fifteen people
    tap it in five minutes, and remembering the last of them is exactly wrong.
    Every tap stands on its own.

What a player can do here is check themselves in, say whether they're batting,
and undo their own tap. They cannot open or close a session, mark anyone as
having batted, reorder the queue or remove anybody else — that all stays with
the coach on the admin screen.

These routes are intentionally NOT behind `require_module` (the caller has no
session); each resolves the club from the token and checks the club is both
entitled to BetterSelect and has check-in enabled, so a disabled or downgraded
club's link simply 404s. Same posture as public_availability.py, which this
mirrors throughout.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.modules import MODULE_SELECT, org_has_module
from app.models.db import NetAttendance, NetSession, Organisation, Player, get_db
from app.routers.availability import (
    club_player_roster, dormant_player_ids, phone_last4,
)
from app.routers.net_manager import (
    _renumber, _touch, check_in, open_session_today,
)
from app.services import rate_limit

router = APIRouter(prefix="/public/nets", tags=["public-nets"])

# PIN lockout, when a club has turned the PIN on: 5 misses in 15 minutes per
# (player + IP). Same numbers as the availability link — a 4-digit PIN is 10k
# combinations, so this isn't optional.
PIN_MAX_FAILURES = 5
PIN_LOCKOUT_SECONDS = 15 * 60
# Per-IP throttles. Everyone at nets shares the clubroom's one connection, so
# these are set for a room of people arriving at once, not for one player.
LANDING_LIMIT = 240
LANDING_WINDOW = 60
WRITE_LIMIT = 120
WRITE_WINDOW = 60


class CheckInBody(BaseModel):
    player_id: str
    pin: str = ""
    # False = here, but not batting tonight.
    bats: bool = True
    note: Optional[str] = None


class UndoBody(BaseModel):
    player_id: str
    pin: str = ""


def _client_ip(request: Request) -> str:
    """Best-effort real client IP for rate-limit keying (Cloudflare-aware)."""
    for header in ("cf-connecting-ip", "x-real-ip"):
        v = request.headers.get(header)
        if v:
            return v.strip()
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _club_for_token(db: AsyncSession, token: str) -> Organisation:
    """Resolve the club behind a check-in token, or 404.

    404 (not 403) for every "this link isn't usable" case — unknown token,
    switched off, or the club no longer entitled to BetterSelect — so a link
    left on a wall after a club stops using it reveals nothing about why.
    """
    if not token:
        raise HTTPException(status_code=404, detail="Unknown link")
    res = await db.execute(
        select(Organisation).where(Organisation.net_checkin_token == token)
    )
    club = res.scalar_one_or_none()
    if (
        club is None
        or not club.net_checkin_enabled
        or not org_has_module(club, MODULE_SELECT)
    ):
        raise HTTPException(status_code=404, detail="This check-in link isn't active")
    return club


def _club_branding(club: Organisation) -> dict:
    return {
        "name": club.name,
        "short_name": club.short_name,
        "slug": club.slug,
        "logo_url": club.logo_url,
        "primary_color": club.primary_color,
        "accent_color": club.accent_color,
    }


async def _verified_player(
    db: AsyncSession, club: Organisation, token: str, request: Request,
    player_id: str, pin: str,
) -> Player:
    """The player this tap is for, PIN-checked when the club asks for one."""
    try:
        pid = uuid.UUID(str(player_id))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Unknown player")

    ip = _client_ip(request)
    lock_key = f"net-checkin:{token}:{pid}:{ip}"
    if club.net_checkin_require_pin:
        rate_limit.assert_not_locked(
            lock_key, PIN_MAX_FAILURES, PIN_LOCKOUT_SECONDS,
            detail="Too many incorrect attempts. Wait a few minutes, or ask your coach to check you in.",
        )

    player = await db.get(Player, pid)
    if not player or player.organisation_id != club.id or not player.is_player:
        if club.net_checkin_require_pin:
            # Don't tell a wrong PIN apart from an unknown player: with the gate
            # on, the link mustn't become a way to read the roster.
            rate_limit.record_failure(lock_key, PIN_LOCKOUT_SECONDS)
        raise HTTPException(status_code=404, detail="We couldn't find you on the list — ask your coach.")

    if club.net_checkin_require_pin:
        want = phone_last4(player.phone)
        if want is None:
            raise HTTPException(
                status_code=409,
                detail="There's no mobile number on file for you — ask your coach to check you in.",
            )
        given = phone_last4(pin)
        if given is None or given != want:
            rate_limit.record_failure(lock_key, PIN_LOCKOUT_SECONDS)
            raise HTTPException(status_code=401, detail="That PIN didn't match. Try the last 4 digits of your mobile.")
        rate_limit.clear_failures(lock_key)

    return player


async def _state(db: AsyncSession, club: Organisation) -> dict:
    """What the check-in screen draws: the club, tonight's session if one is
    open, and every name with whether they're already in.

    The roster is the club's WHOLE player list, tagged, for the same reason the
    admin check-in list is: a player standing at the door with their kit on is
    there whatever the app thinks of their last appearance, and a screen that
    can't find them is a screen they walk away from. The current squad is what
    it shows first; the rest are behind the search box.
    """
    session = await open_session_today(db, club.id)

    present: dict[uuid.UUID, NetAttendance] = {}
    if session is not None:
        rows = await db.execute(
            select(NetAttendance).where(NetAttendance.session_id == session.id)
        )
        present = {r.player_id: r for r in rows.scalars().all() if r.player_id}

    dormant = await dormant_player_ids(db, club)
    players = []
    for p in await club_player_roster(db, club):
        row = present.get(p.id)
        players.append({
            "id": str(p.id),
            "name": p.display_name,
            "photo_url": p.photo_url,
            # A name a club has parked shouldn't be the first thing a player
            # scrolls past, but it must still be findable — see the docstring.
            "in_squad": p.status != "inactive" and p.id not in dormant,
            "checked_in": row is not None,
            "bats": bool(row.bats) if row is not None else True,
            # Only their own tap is theirs to undo; once a coach has marked
            # them as having batted, the night is on the record.
            "batted": bool(row.batted) if row is not None else False,
        })

    return {
        "club": _club_branding(club),
        "require_pin": bool(club.net_checkin_require_pin),
        "session": None if session is None else {
            "id": str(session.id),
            "label": session.label,
            "session_date": session.session_date.isoformat(),
            "checked_in_count": len(present),
        },
        "players": players,
    }


@router.get("/{token}")
async def landing(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    """The screen itself. Polled by the device so a name a coach checked in from
    the admin screen shows as already in rather than inviting a second tap."""
    club = await _club_for_token(db, token)
    rate_limit.enforce(
        f"net-checkin-read:{token}:{_client_ip(request)}", LANDING_LIMIT, LANDING_WINDOW,
        detail="Busy — give it a moment and try again.",
    )
    return await _state(db, club)


@router.post("/{token}/checkin")
async def self_check_in(
    token: str, body: CheckInBody, request: Request, db: AsyncSession = Depends(get_db),
):
    """"I'm here." Adds this player to tonight's session, at the back of the
    queue, or records that they're here and sitting out."""
    club = await _club_for_token(db, token)
    club_id = club.id
    rate_limit.enforce(
        f"net-checkin-write:{token}:{_client_ip(request)}", WRITE_LIMIT, WRITE_WINDOW,
        detail="Busy — give it a moment and try again.",
    )

    session = await open_session_today(db, club_id)
    if session is None:
        raise HTTPException(status_code=409, detail="No net session is open yet — your coach opens it from BetterSelect.")
    session_id = str(session.id)

    player = await _verified_player(db, club, token, request, body.player_id, body.pin)
    player_id = str(player.id)

    await check_in(
        db, session_id, club_id,
        player_id=player_id,
        bats=bool(body.bats),
        note=body.note,
        source="self",
    )
    # Re-read the club rather than reusing the row loaded above: check_in rolls
    # back when two devices tap the same name in the same second, and a rollback
    # expunges everything loaded before it whatever expire_on_commit says — so
    # reading an attribute off the old instance is a lazy load in the wrong
    # place, the MissingGreenlet trap this repo has hit before.
    club = await db.get(Organisation, club_id)
    if club is None:                                    # deleted mid-request
        raise HTTPException(status_code=404, detail="This check-in link isn't active")
    return await _state(db, club)


@router.post("/{token}/undo")
async def undo_check_in(
    token: str, body: UndoBody, request: Request, db: AsyncSession = Depends(get_db),
):
    """"That wasn't me." Takes their own check-in back off tonight's list.

    Only their OWN row, only tonight's session, and only while they haven't
    batted — once a coach has run them through a net, the record of the night is
    the coach's to change, not a tap on the door screen's.
    """
    club = await _club_for_token(db, token)
    rate_limit.enforce(
        f"net-checkin-write:{token}:{_client_ip(request)}", WRITE_LIMIT, WRITE_WINDOW,
        detail="Busy — give it a moment and try again.",
    )

    session = await open_session_today(db, club.id)
    if session is None:
        raise HTTPException(status_code=409, detail="No net session is open right now.")

    player = await _verified_player(db, club, token, request, body.player_id, body.pin)
    res = await db.execute(
        select(NetAttendance).where(
            NetAttendance.session_id == session.id,
            NetAttendance.player_id == player.id,
        )
    )
    row = res.scalar_one_or_none()
    if row is not None:
        if row.batted:
            raise HTTPException(status_code=409, detail="You've already had a bat — ask your coach to change this.")
        await db.delete(row)
        await db.flush()
        # Close the queue's gap and bump the version, so the coach's screen picks
        # the removal up on its next poll rather than showing a name that's gone.
        await _renumber(db, session.id)
        _touch(session)
        await db.commit()
    return await _state(db, club)
