"""BetterSelect — self-service player availability (public, unauthenticated).

Players set their own availability for upcoming fixtures via a per-club magic
link + a last-4-of-phone PIN, with **no account and no app**. Three controls,
each doing one job (see docs/betterselect-self-availability.md):

  * **link token** — scopes/distributes the page. Pinned publicly (group chat /
    QR), so it's low-trust by design and rotatable. Identifies the club only.
  * **PIN** (last 4 of `Player.phone`) — proves *which* player you are. Low
    entropy (10k combos), so the lockout below is mandatory, not optional. A
    club may turn the PIN off (`availability_require_pin = false`).
  * **session cookie** (`bs_avail`, signed, HttpOnly, ~30d) — keeps you verified
    after the PIN. "Switch player" clears it.

The write endpoint only ever touches the *verified* player's availability and
only for *valid upcoming club fixture dates*, and exposes no PII beyond the
player's own name and the (semi-public) fixture list.

These routes are intentionally NOT behind `require_module` (the caller has no
session); instead each resolves the club from the token and checks the club is
both entitled to BetterSelect and has self-service enabled — a disabled or
downgraded club's link simply 404s.
"""
from __future__ import annotations

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
from app.models.db import Organisation, Player, PlayerAvailability, get_db
from app.routers.availability import (
    active_self_service_players,
    phone_last4,
    upcoming_fixtures_by_date,
)
from app.services import rate_limit

router = APIRouter(prefix="/public/availability", tags=["public-availability"])

COOKIE_NAME = "bs_avail"
SESSION_DAYS = 30

# PIN lockout: 5 wrong attempts inside 15 minutes (per player + IP) → cooldown.
PIN_MAX_FAILURES = 5
PIN_LOCKOUT_SECONDS = 15 * 60
# A coarser per-IP throttle so a single IP can't fan out across many player ids
# faster than a human ever would.
VERIFY_IP_LIMIT = 40
VERIFY_IP_WINDOW = 60
# Write throttle — generous (a real player taps a handful of dates).
WRITE_LIMIT = 60
WRITE_WINDOW = 60

# A player may only set a real answer for themselves (no NO_RESPONSE-as-default;
# NO_RESPONSE is allowed so a mis-tap can be retracted).
SELF_STATUSES = {"AVAILABLE", "UNAVAILABLE", "MAYBE", "NO_RESPONSE"}


class VerifyBody(BaseModel):
    player_id: str
    pin: str = ""


class SetBody(BaseModel):
    date: date
    status: str
    note: Optional[str] = None


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
        {"club": str(club_id), "pid": str(player_id), "typ": "avail", "exp": exp},
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
    if payload.get("typ") != "avail" or payload.get("club") != str(club_id):
        return None
    try:
        return uuid.UUID(payload["pid"])
    except (KeyError, ValueError, TypeError):
        return None


async def _club_for_token(db: AsyncSession, token: str) -> Organisation:
    """Resolve the club behind a self-service token, or 404.

    404 (not 403) for every "this link isn't usable" case — unknown token,
    disabled, or the club no longer entitled to BetterSelect — so a leaked or
    rotated link reveals nothing about why it stopped working.
    """
    if not token:
        raise HTTPException(status_code=404, detail="Unknown link")
    res = await db.execute(
        select(Organisation).where(Organisation.availability_link_token == token)
    )
    club = res.scalar_one_or_none()
    if (
        club is None
        or not club.availability_self_service_enabled
        or not org_has_module(club, MODULE_SELECT)
    ):
        raise HTTPException(status_code=404, detail="This availability link isn't active")
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


async def _player_for_session(db: AsyncSession, request: Request, club: Organisation) -> Player:
    pid = _read_session(request, club.id)
    if not pid:
        raise HTTPException(status_code=401, detail="Not verified")
    player = await db.get(Player, pid)
    if not player or player.organisation_id != club.id:
        raise HTTPException(status_code=401, detail="Not verified")
    return player


@router.get("/{token}")
async def get_landing(token: str, db: AsyncSession = Depends(get_db)):
    """Club branding + the active-player name list (id + display name only) for
    the type-to-search step. 404 if the link is disabled / unknown."""
    club = await _club_for_token(db, token)
    players = await active_self_service_players(db, club)
    return {
        "club": _club_branding(club),
        "require_pin": bool(club.availability_require_pin),
        "players": [
            {"id": str(p.id), "display_name": p.display_name, "has_phone": phone_last4(p.phone) is not None}
            for p in players
        ],
    }


@router.post("/{token}/verify")
async def verify(token: str, body: VerifyBody, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    """Prove identity with the last 4 digits of the player's mobile, then issue
    the session cookie. Rate-limited per IP + locked out after repeated misses."""
    club = await _club_for_token(db, token)
    ip = _client_ip(request)
    rate_limit.enforce(
        f"avail-verify-ip:{token}:{ip}", VERIFY_IP_LIMIT, VERIFY_IP_WINDOW,
        detail="Too many attempts, slow down and try again shortly.",
    )

    try:
        pid = uuid.UUID(body.player_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid player")

    lock_key = f"avail-verify:{token}:{pid}:{ip}"
    rate_limit.assert_not_locked(
        lock_key, PIN_MAX_FAILURES, PIN_LOCKOUT_SECONDS,
        detail="Too many incorrect attempts. Please wait a few minutes and try again.",
    )

    player = await db.get(Player, pid)
    if not player or player.organisation_id != club.id or not player.is_player:
        # Don't distinguish "no such player" from "wrong PIN" — both count as a
        # failure so a leaked link can't be used to enumerate the roster.
        rate_limit.record_failure(lock_key, PIN_LOCKOUT_SECONDS)
        raise HTTPException(status_code=401, detail="That didn't match. Check your details and try again.")

    if club.availability_require_pin:
        want = phone_last4(player.phone)
        if want is None:
            raise HTTPException(
                status_code=409,
                detail="No mobile number is on file for you yet. Ask your club admin to add it or set your availability for you.",
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
    """"Not you?" — clear the session cookie so a different player can verify."""
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return {"status": "ok"}


def _grouped_dates(by_date: dict[str, list[dict]]) -> list[dict]:
    return [{"date": d, "fixtures": by_date[d]} for d in sorted(by_date.keys())]


@router.get("/{token}/me")
async def get_me(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    """This verified player's upcoming fixtures (grouped by date) + their current
    answers. Date-keyed: one answer covers every fixture that day."""
    club = await _club_for_token(db, token)
    player = await _player_for_session(db, request, club)
    by_date = await upcoming_fixtures_by_date(db, club.id)
    answers: dict[str, dict] = {}
    if by_date:
        av_res = await db.execute(
            select(PlayerAvailability).where(
                PlayerAvailability.player_id == player.id,
                PlayerAvailability.avail_date.in_([date.fromisoformat(d) for d in by_date.keys()]),
            )
        )
        for a in av_res.scalars().all():
            answers[a.avail_date.isoformat()] = {
                "status": a.status, "note": a.note, "source": a.source or "admin",
            }
    return {
        "club": _club_branding(club),
        "player": {"id": str(player.id), "display_name": player.display_name},
        "dates": _grouped_dates(by_date),
        "availability": answers,
    }


@router.post("/{token}/me")
async def set_me(token: str, body: SetBody, request: Request, db: AsyncSession = Depends(get_db)):
    """Upsert this player's own answer for a date. Validates the date is a real
    upcoming club fixture date and stamps source='self' (recorded_by stays NULL)."""
    club = await _club_for_token(db, token)
    player = await _player_for_session(db, request, club)
    rate_limit.enforce(f"avail-write:{player.id}", WRITE_LIMIT, WRITE_WINDOW)

    status = (body.status or "").upper()
    if status not in SELF_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {body.status}")

    by_date = await upcoming_fixtures_by_date(db, club.id)
    if body.date.isoformat() not in by_date:
        raise HTTPException(status_code=400, detail="No upcoming fixture on that date")

    note = (body.note or "").strip() or None
    res = await db.execute(
        select(PlayerAvailability).where(
            PlayerAvailability.player_id == player.id,
            PlayerAvailability.avail_date == body.date,
        )
    )
    row = res.scalar_one_or_none()
    if row:
        row.status = status
        row.note = note
        row.source = "self"
        row.recorded_by = None
        row.recorded_at = datetime.now(timezone.utc)
    else:
        db.add(PlayerAvailability(
            organisation_id=club.id,
            player_id=player.id,
            avail_date=body.date,
            status=status,
            note=note,
            source="self",
            recorded_by=None,
        ))
    await db.commit()
    return {"status": "ok"}
