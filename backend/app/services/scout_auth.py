"""BetterScout — auth primitives.

A REAL username/password login (unlike the member portal's magic-link
pattern), but deliberately NOT routers/auth.py's create_session_token/
set_session_cookie — that pair is hardcoded to the cricket-club User/
ClubMembership/Organisation shape (see routers/auth.py::get_current_user's
`db.get(User, ...)`). A Scout Org is a different tenant type entirely, so
this mirrors the OTHER existing precedent for a non-User auth scheme in this
codebase, services/member_portal_auth.py — its own cookie name, its own JWT
`typ` claim, its own session read/write functions — combined with the
bcrypt + lockout-counter mechanics routers/auth.py uses for a real password
login (the member portal has no password to check, so it has no equivalent
of those).

The JWT carries BOTH the org id and the user id (unlike member_portal_auth's
read_session(request, org_id), which requires the caller to already know
org_id from a slugged URL) — a BetterScout login has no known org ahead of
time, so both ids round-trip through the signed token and the caller
cross-checks them against the DB on every read.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Request, Response
from jose import JWTError, jwt

from app.config.settings import settings

COOKIE_NAME = "bs_scout_session"
SESSION_DAYS = 30
SESSION_TYP = "scout_session"

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def issue_session_cookie(response: Response, scout_org_id, scout_user_id) -> None:
    exp = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    token = jwt.encode(
        {
            "org": str(scout_org_id),
            "uid": str(scout_user_id),
            "typ": SESSION_TYP,
            "exp": exp,
        },
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    response.set_cookie(
        key=COOKIE_NAME, value=token, httponly=True,
        secure=settings.cookie_secure, samesite="lax",
        max_age=SESSION_DAYS * 24 * 60 * 60, path="/",
    )


def read_session(request: Request) -> Optional[tuple[uuid.UUID, uuid.UUID]]:
    """Returns (scout_org_id, scout_user_id) from the cookie, or None if
    there's no session / it's expired / malformed / not a BetterScout token.
    The caller (get_current_scout_user) still has to re-fetch both rows from
    the DB and check the FK actually agrees — this only proves the token was
    signed by us, not that the account still exists or is still active."""
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        return None
    try:
        payload = jwt.decode(raw, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return None
    if payload.get("typ") != SESSION_TYP:
        return None
    try:
        return uuid.UUID(payload["org"]), uuid.UUID(payload["uid"])
    except (KeyError, ValueError, TypeError):
        return None


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")
