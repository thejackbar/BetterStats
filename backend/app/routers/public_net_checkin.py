"""Net check-in: a player checks themselves in, from a QR code or an NFC tag.

Checking in at the nets used to mean a manager tapping each name on the iPad.
This is the same check-in done by the player, on their own phone, on the way
past the gate — no account, no app, no download.

**The QR code and the NFC tag are the same link.** An NFC tag stores a URL and
nothing else, so writing this page's address to a tag and printing it as a QR
code are two ways of handing over one string. There is one token behind both,
which is what stops a club having to keep two of them alive.

Three controls, the same three the availability link uses:

  * the **token** scopes the link to one club and is its only secret. It is
    pinned to a fence and stuck under a tag, so it is low-trust by design and
    rotatable the moment a club wants it to be.
  * the **PIN** (last 4 digits of the player's mobile) proves the person
    tapping a name is that person. Optional per club: a committee that would
    rather people got into the nets quickly can turn it off.
  * the **cookie** remembers who they are for 30 days, so the second week is
    one tap.

**Scanning checks you into every live session at the club**, not one you pick
off a list. Somebody walking into the nets does not know or care which of the
club's two concurrent sessions the seniors' one is called, and asking them to
choose is a question the club can already answer.

**A newcomer is checked in as a GUEST, never as a player.** `net_attendance`
has carried guest rows since it was written, for exactly this person, so
somebody who found the QR code cannot write a row into the club's player
table. What they type lands in `net_checkin_registrations` for an admin to
approve, which is the one place a real player is ever created from this.
That path cannot be PIN-gated — the club has no number on file to check
against someone it has never met — which is why a club can turn registration
off on its own rather than it riding on the PIN setting.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.modules import MODULE_SELECT, org_has_module
from app.config.settings import settings
from app.models.db import (
    NetAttendance, NetCheckInRegistration, Organisation, Player, get_db,
)
from app.routers.availability import active_self_service_players, phone_last4
from app.routers.net_manager import check_in_person, live_sessions, touch_session
from app.services import rate_limit

router = APIRouter(prefix="/public/net-checkin", tags=["public-net-checkin"])

COOKIE_NAME = "bs_nets"
SESSION_DAYS = 30

# PIN lockout: 5 wrong attempts inside 15 minutes (per player + IP) → cooldown.
PIN_MAX_FAILURES = 5
PIN_LOCKOUT_SECONDS = 15 * 60
# A coarser per-IP throttle so one IP can't fan out across many player ids
# faster than a human ever would. Set higher than availability's: a whole
# squad arriving at the nets is routinely behind one ground wifi NAT, and a
# limit that locks out the fourth arrival is worse than useless.
VERIFY_IP_LIMIT = 120
VERIFY_IP_WINDOW = 60
# Check-in throttle — a real arrival taps this once, maybe twice.
CHECKIN_LIMIT = 20
CHECKIN_WINDOW = 60
# Registration is the expensive one (it writes a row a human then has to
# read), so it is the tightest. Per IP, since a newcomer has no player id.
REGISTER_LIMIT = 6
REGISTER_WINDOW = 10 * 60

MAX_NAME = 80
MAX_CLUB = 80
MAX_EMAIL = 120
MAX_PHONE = 40


class VerifyBody(BaseModel):
    player_id: str
    pin: str = ""


class RegisterBody(BaseModel):
    full_name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    date_of_birth: Optional[date] = None
    previous_club: Optional[str] = None


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


def _issue_cookie(response: Response, club_id, player_id) -> None:
    exp = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    token = jwt.encode(
        # `typ` is what stops a bs_avail or bs_vote cookie being replayed here.
        {"club": str(club_id), "pid": str(player_id), "typ": "nets", "exp": exp},
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=SESSION_DAYS * 24 * 60 * 60,
        path="/",
    )


def _read_session(request: Request, club_id) -> Optional[uuid.UUID]:
    """The verified player_id from the cookie, but only if it's for this club."""
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        return None
    try:
        payload = jwt.decode(raw, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return None
    if payload.get("typ") != "nets" or payload.get("club") != str(club_id):
        return None
    try:
        return uuid.UUID(payload["pid"])
    except (KeyError, ValueError, TypeError):
        return None


async def _club_for_token(db: AsyncSession, token: str) -> Organisation:
    """Resolve the club behind a check-in token, or 404.

    404 (not 403) for every "this link isn't usable" case — unknown token,
    switched off, or the club no longer entitled to BetterSelect — so a link
    that has been rotated off a fence reveals nothing about why it stopped.
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


def _session_card(s) -> dict:
    return {
        "id": str(s.id),
        "session_date": s.session_date.isoformat() if s.session_date else None,
        "label": s.label,
    }


async def _checked_in_session_ids(db: AsyncSession, player_id, session_ids) -> set:
    if not session_ids:
        return set()
    res = await db.execute(
        select(NetAttendance.session_id).where(
            NetAttendance.player_id == player_id,
            NetAttendance.session_id.in_(session_ids),
        )
    )
    return {r for (r,) in res.fetchall()}


# ── Landing ───────────────────────────────────────────────────────────────────
@router.get("/{token}")
async def get_landing(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Who the club is, whether nets are on right now, and the names to pick from.

    Deliberately says nothing about who is already checked in — that is the
    club's business, and this page is served to anyone holding the link.
    """
    club = await _club_for_token(db, token)
    sessions = await live_sessions(db, club.id)
    players = await active_self_service_players(db, club)

    me = None
    pid = _read_session(request, club.id)
    if pid:
        player = await db.get(Player, pid)
        if player and player.organisation_id == club.id:
            done = await _checked_in_session_ids(db, player.id, [s.id for s in sessions])
            me = {
                "id": str(player.id),
                "display_name": player.display_name,
                # Already in every session that's on, so the page can open on
                # "you're checked in" rather than asking again.
                "checked_in": bool(sessions) and len(done) == len(sessions),
            }

    return {
        "club": _club_branding(club),
        "require_pin": bool(club.net_checkin_require_pin),
        "allow_registration": bool(club.net_checkin_allow_registration),
        "sessions": [_session_card(s) for s in sessions],
        "players": [
            {
                "id": str(p.id),
                "display_name": p.display_name,
                "has_phone": phone_last4(p.phone) is not None,
            }
            for p in players
        ],
        "me": me,
    }


# ── Verify ────────────────────────────────────────────────────────────────────
@router.post("/{token}/verify")
async def verify(
    token: str,
    body: VerifyBody,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Prove identity with the last 4 digits of the mobile, then issue the
    cookie. Rate-limited per IP and locked out after repeated misses."""
    club = await _club_for_token(db, token)
    ip = _client_ip(request)
    rate_limit.enforce(
        f"nets-verify-ip:{token}:{ip}", VERIFY_IP_LIMIT, VERIFY_IP_WINDOW,
        detail="Too many attempts — slow down and try again shortly.",
    )

    try:
        pid = uuid.UUID(body.player_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid player")

    lock_key = f"nets-verify:{token}:{pid}:{ip}"
    rate_limit.assert_not_locked(
        lock_key, PIN_MAX_FAILURES, PIN_LOCKOUT_SECONDS,
        detail="Too many incorrect attempts. Please wait a few minutes and try again.",
    )

    player = await db.get(Player, pid)
    if not player or player.organisation_id != club.id or not player.is_player:
        # Don't distinguish "no such player" from "wrong PIN" — both count as a
        # failure, so a link off a fence can't be used to enumerate the roster.
        rate_limit.record_failure(lock_key, PIN_LOCKOUT_SECONDS)
        raise HTTPException(status_code=401, detail="That didn't match. Check your details and try again.")

    if club.net_checkin_require_pin:
        want = phone_last4(player.phone)
        if want is None:
            # Actionable rather than a failure, so it doesn't count towards the
            # lockout: there is nothing they could have typed that would work.
            raise HTTPException(
                status_code=409,
                detail="No mobile number is on file for you yet — ask whoever is running nets to check you in.",
            )
        given = phone_last4(body.pin)
        if given is None or given != want:
            rate_limit.record_failure(lock_key, PIN_LOCKOUT_SECONDS)
            raise HTTPException(status_code=401, detail="That PIN didn't match. Try the last 4 digits of your mobile.")

    rate_limit.clear_failures(lock_key)
    _issue_cookie(response, club.id, player.id)
    return {"status": "ok", "player": {"id": str(player.id), "display_name": player.display_name}}


@router.post("/{token}/switch")
async def switch_player(token: str, response: Response):
    """"Not you?" — clear the cookie so the next person can check in on a
    phone that has been handed around."""
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return {"status": "ok"}


# ── Check in ──────────────────────────────────────────────────────────────────
@router.post("/{token}/check-in")
async def check_in(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Check the verified player into every session running right now.

    All of them, not one they picked: see the module docstring. Being already
    in one of them is not an error — a second tap, or a phone that retried on
    a flaky ground signal, should read the same as the first.
    """
    club = await _club_for_token(db, token)
    club_id = club.id
    ip = _client_ip(request)

    pid = _read_session(request, club_id)
    if not pid:
        raise HTTPException(status_code=401, detail="Not verified")
    player = await db.get(Player, pid)
    if not player or player.organisation_id != club_id:
        raise HTTPException(status_code=401, detail="Not verified")

    rate_limit.enforce(f"nets-checkin:{player.id}", CHECKIN_LIMIT, CHECKIN_WINDOW)

    sessions = await live_sessions(db, club_id)
    if not sessions:
        raise HTTPException(
            status_code=409,
            detail="There's no net session running right now. Check with whoever is running nets.",
        )

    added = 0
    for s in sessions:
        row = await check_in_person(
            db, s, club_id, player_id=player.id, source="self",
        )
        if row is not None:
            added += 1
            # Bump the version so the iPad's next poll picks them up — and,
            # with source='self', announces them.
            touch_session(s)
    await db.commit()

    return {
        "status": "ok",
        "player": {"id": str(player.id), "display_name": player.display_name},
        "sessions": [_session_card(s) for s in sessions],
        "added": added,
        # 0 added across a live session means they were already in it.
        "already_in": added == 0,
    }


# ── Register (not on the list) ────────────────────────────────────────────────
def _clean_email(v: Optional[str]) -> Optional[str]:
    v = (v or "").strip()[:MAX_EMAIL]
    if not v:
        return None
    # Deliberately loose: this is a note for a human to act on, not a login.
    # Refusing a real address because it looks unusual is the worse failure.
    return v if re.match(r"^[^@\s]+@[^@\s.]+\.[^@\s]+$", v) else None


@router.post("/{token}/register")
async def register(
    token: str,
    body: RegisterBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Somebody who isn't on the list. Checks them in as a GUEST and files
    what they typed for an admin to look at.

    No player row is created here, on purpose. This page is served to whoever
    holds the link, so the club decides who joins its roster — see the module
    docstring.
    """
    club = await _club_for_token(db, token)
    club_id = club.id
    if not club.net_checkin_allow_registration:
        raise HTTPException(
            status_code=403,
            detail="This club isn't taking new registrations at the nets. Have a word with whoever is running the session.",
        )

    ip = _client_ip(request)
    rate_limit.enforce(
        f"nets-register:{token}:{ip}", REGISTER_LIMIT, REGISTER_WINDOW,
        detail="That's a few registrations from one place — check with whoever is running nets.",
    )

    name = (body.full_name or "").strip()[:MAX_NAME]
    if len(name) < 2:
        raise HTTPException(status_code=422, detail="Please give your full name.")

    dob = body.date_of_birth
    if dob is not None:
        today = datetime.now(timezone.utc).date()
        # The same two refusals the player profile makes, so a form nobody is
        # watching can't store a birthday the admin screen would reject.
        if dob > today or dob < today - timedelta(days=120 * 366):
            raise HTTPException(status_code=422, detail="That date of birth doesn't look right.")

    sessions = await live_sessions(db, club_id)
    if not sessions:
        raise HTTPException(
            status_code=409,
            detail="There's no net session running right now. Check with whoever is running nets.",
        )

    # The guest row in the FIRST live session is the one the registration
    # points at, because that is the row an approval converts into the new
    # player. Any other concurrent session gets its own guest row and keeps it:
    # a person is promoted once, and converting them in two places at once
    # would mean two player rows for one person.
    first_row = None
    for s in sessions:
        row = await check_in_person(
            db, s, club_id, guest_name=name, source="self",
        )
        if row is not None:
            if first_row is None:
                first_row = row
            touch_session(s)

    reg = NetCheckInRegistration(
        id=uuid.uuid4(),
        organisation_id=club_id,
        session_id=sessions[0].id,
        attendance_id=first_row.id if first_row is not None else None,
        full_name=name,
        phone=((body.phone or "").strip()[:MAX_PHONE] or None),
        email=_clean_email(body.email),
        date_of_birth=dob,
        previous_club=((body.previous_club or "").strip()[:MAX_CLUB] or None),
        status="pending",
    )
    db.add(reg)
    await db.commit()

    return {
        "status": "ok",
        "name": name,
        "sessions": [_session_card(s) for s in sessions],
    }
