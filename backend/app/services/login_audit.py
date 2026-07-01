"""Login attempt audit — persists every sign-in attempt to `login_attempts`.

Records who is trying to log in (the attempted username/email), from where (a
truncated SHA-256 IP hash + Cloudflare country), on what device (user-agent),
and the outcome (success, or a failure reason). The password is never stored.

Written in its own session and awaited at the point of outcome, so the row
lands even when the login handler raises immediately afterwards — but it never
raises itself, so a logging hiccup can't block a real login.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services.usage_tracker import hash_ip

logger = logging.getLogger(__name__)

# Stable failure-reason codes stored on each failed attempt. Kept short and
# machine-readable; the frontend maps them to friendly labels.
REASON_UNKNOWN_USER = "unknown_user"      # no account with that username/email
REASON_BAD_PASSWORD = "bad_password"      # account exists, wrong password
REASON_LOCKED = "locked"                  # too many recent failures, locked out
REASON_NO_MEMBERSHIP = "no_membership"    # valid login, but no club membership
REASON_CLUB_INACTIVE = "club_inactive"    # valid login, club is deactivated


def _norm_country(country: Optional[str]) -> Optional[str]:
    cc = (country or "").upper()[:2]
    if not cc or cc in ("XX", "T1"):
        return None
    return cc


def client_ip(request) -> Optional[str]:
    """Real client IP behind Cloudflare / proxies. Mirrors main._client_ip so
    the hash matches the one usage_events stores for the same visitor."""
    h = request.headers
    cf = h.get("cf-connecting-ip")
    if cf:
        return cf.strip()
    fwd = h.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    real = h.get("x-real-ip")
    if real:
        return real.strip()
    if request.client:
        return request.client.host
    return None


async def record_login_attempt(
    *,
    username: str,
    success: bool,
    failure_reason: Optional[str] = None,
    user_id: Optional[str] = None,
    org_id: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    country: Optional[str] = None,
) -> None:
    """Insert one login-attempt row. Opens its own session; never raises."""
    try:
        async with async_session_maker() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO login_attempts (
                        username, success, failure_reason, user_id, org_id,
                        ip_hash, user_agent, country
                    ) VALUES (
                        :username, :success, :failure_reason, :user_id, :org_id,
                        :ip_hash, :user_agent, :country
                    )
                    """
                ),
                {
                    "username": (username or "")[:255],
                    "success": bool(success),
                    "failure_reason": failure_reason or None,
                    "user_id": str(user_id) if user_id else None,
                    "org_id": str(org_id) if org_id else None,
                    "ip_hash": hash_ip(ip),
                    "user_agent": (user_agent or "")[:300] or None,
                    # Drop Cloudflare's private/loopback markers (XX / T1).
                    "country": _norm_country(country),
                },
            )
            await session.commit()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"login_audit: record_login_attempt failed ({e})")
