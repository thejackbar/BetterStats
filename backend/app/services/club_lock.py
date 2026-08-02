"""Password-protected public club pages ("Draft" mode).

A club's public page can be gated behind a 4-digit PIN — either the club
admin's own choice (voluntary privacy, e.g. while onboarding) or a Super
Admin action against a club whose trial has ended (a sales-conversion tool:
see routers/clubs.py's POST /{slug}/request-unpause). Independent of
Organisation.is_active by design; see the model comment on
Organisation.password_protected.

Modeled directly on routers/public_availability.py's bs_avail cookie pattern
(signed JWT, HttpOnly, ~30 days) — the same house pattern used for BetterSelect
self-service availability and votes.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Request, Response
from jose import JWTError, jwt

from app.config.settings import settings

COOKIE_NAME = "bs_lock"
SESSION_DAYS = 30


def hash_pin(pin: str) -> str:
    return bcrypt.hashpw(pin.encode(), bcrypt.gensalt()).decode()


def verify_pin(pin: str, pin_hash: str | None) -> bool:
    if not pin_hash:
        return False
    try:
        return bcrypt.checkpw(pin.encode(), pin_hash.encode())
    except (ValueError, TypeError):
        return False


def issue_lock_cookie(response: Response, org_id) -> None:
    exp = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    token = jwt.encode(
        {"org": str(org_id), "typ": "lock", "exp": exp},
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


def is_unlocked(request: Request, org_id) -> bool:
    """Whether this request already carries a valid unlock cookie for org_id."""
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        return False
    try:
        payload = jwt.decode(raw, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return False
    return payload.get("typ") == "lock" and payload.get("org") == str(org_id)


def is_locked_for_request(org, request: Request) -> bool:
    """True when org is password-protected and this request hasn't unlocked it."""
    if org is None or not getattr(org, "password_protected", False):
        return False
    return not is_unlocked(request, org.id)


def lock_detail(org, message: Optional[str] = None) -> dict:
    """The structured 423 `detail` payload — same convention as require_module's
    402 upsell body (a `code` + whatever the frontend needs to render, no PII)."""
    reason = org.password_protect_reason or "draft"
    if message is None:
        message = (
            "This trial has ended. To unlock the page, request the access PIN from BetterCricket."
            if reason == "trial_ended"
            else "This club's page is currently private. Enter the access PIN to view it."
        )
    return {
        "code": "password_protected",
        "reason": reason,
        "name": org.name,
        "short_name": org.short_name,
        "logo_url": org.logo_url,
        "slug": org.slug,
        "message": message,
    }
