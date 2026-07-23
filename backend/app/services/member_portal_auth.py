"""Member self-service portal — auth.

A REAL per-member login, not the shared-magic-link-plus-PIN pattern
BetterSelect/BetterFantasy use — deliberately, since this portal exposes fee
and qualification data, a materially bigger blast radius than an
availability tick. A member requests a link; it's emailed only to their own
registered address; clicking it signs them in. No account/password to
create or forget.

No new DB table for the login flow itself — the magic-link token is a
short-lived signed JWT (stateless, same posture as the existing Square/Xero
OAuth-state tokens: `sign_square_state` in routers/merch.py, `sign_xero_state`
in routers/fees.py), and the session afterwards is a signed HttpOnly cookie
exactly mirroring routers/public_availability.py's `_issue_cookie`/
`_read_session` pair (own COOKIE_NAME, own `typ` claim, club id checked on
every read).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Request, Response
from jose import JWTError, jwt

from app.config.settings import settings
from app.services import email_service

COOKIE_NAME = "bs_member_portal"
SESSION_DAYS = 30
LINK_TYP = "member_portal_link"
SESSION_TYP = "member_portal"
LINK_EXPIRY_MINUTES = 20


def sign_magic_link(org_id, member_id) -> str:
    payload = {
        "org": str(org_id),
        "mid": str(member_id),
        "typ": LINK_TYP,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=LINK_EXPIRY_MINUTES),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def verify_magic_link(token: str, org_id) -> Optional[uuid.UUID]:
    """Returns the member id the link was minted for, or None if the token
    is missing/expired/malformed/for a different club."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return None
    if payload.get("typ") != LINK_TYP or payload.get("org") != str(org_id):
        return None
    try:
        return uuid.UUID(payload["mid"])
    except (KeyError, ValueError, TypeError):
        return None


def issue_session_cookie(response: Response, org_id, member_id) -> None:
    exp = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    token = jwt.encode(
        {"org": str(org_id), "mid": str(member_id), "typ": SESSION_TYP, "exp": exp},
        settings.secret_key, algorithm=settings.algorithm,
    )
    response.set_cookie(
        key=COOKIE_NAME, value=token, httponly=True,
        secure=settings.cookie_secure, samesite="lax",
        max_age=SESSION_DAYS * 24 * 60 * 60, path="/",
    )


def read_session(request: Request, org_id) -> Optional[uuid.UUID]:
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        return None
    try:
        payload = jwt.decode(raw, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return None
    if payload.get("typ") != SESSION_TYP or payload.get("org") != str(org_id):
        return None
    try:
        return uuid.UUID(payload["mid"])
    except (KeyError, ValueError, TypeError):
        return None


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


async def send_magic_link_email(*, to_email: str, member_name: str, club_name: str, club_slug: str, token: str) -> None:
    """Emails the sign-in link. Raises on delivery failure (not swallowed) —
    the caller decides how to surface that; the request-link endpoint itself
    always returns a generic success message regardless, to avoid leaking
    whether an email is registered."""
    link = f"{settings.public_base_url}/portal/{club_slug}?token={token}"
    first_name = (member_name or "").split(" ")[0] or "there"
    html = (
        f"<p>Hi {first_name},</p>"
        f"<p>Here's your sign-in link for the {club_name} member portal:</p>"
        f'<p><a href="{link}">{link}</a></p>'
        f"<p>This link expires in {LINK_EXPIRY_MINUTES} minutes. "
        f"If you didn't request this, you can ignore this email.</p>"
    )
    text = f"Hi {first_name},\n\nHere's your sign-in link for the {club_name} member portal:\n{link}\n\nThis link expires in {LINK_EXPIRY_MINUTES} minutes."
    msg = email_service.EmailMessage(
        to_email=to_email, to_name=member_name or None,
        subject=f"Your {club_name} member portal sign-in link",
        html=html, text=text,
        from_email=settings.email_from_address, from_name=club_name or settings.email_from_name,
        reply_to=settings.email_reply_to,
    )
    result = await email_service.get_email_provider().send(msg)
    if not result.ok:
        raise RuntimeError(f"Failed to send member portal link: {result.error}")
