"""Email verification (OTP) for self-serve trial registration.

Full flow built now even though the entry point stays Super Admin-only for this
phase — the explicit goal (see docs/self-serve-trial-onboarding-plan.md, Decision
5) is that a future public launch only needs new buttons wired to this, no
further backend work.

A 4-digit numeric code, bcrypt-hashed at rest (same algorithm as user passwords,
routers/auth.py's _hash_password/_verify_password — not imported directly since
those are router-local, but the same bcrypt calls), valid 24 hours, one active
code per email at a time. Never logged, never returned to the caller.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import SelfServeEmailVerification
from app.services import email_service
from app.config.settings import settings

CODE_TTL_HOURS = 24


def _generate_code() -> str:
    """Random 4-digit numeric code. secrets.choice, not random — same reasoning
    as the codebase's other single-use tokens (e.g. availability_link_token's
    secrets.token_urlsafe)."""
    return "".join(secrets.choice("0123456789") for _ in range(4))


def _hash_code(code: str) -> str:
    return bcrypt.hashpw(code.encode(), bcrypt.gensalt()).decode()


def _code_matches(code: str, code_hash: str) -> bool:
    try:
        return bcrypt.checkpw(code.encode(), code_hash.encode())
    except ValueError:
        return False


async def _latest_active_row(db: AsyncSession, email: str) -> Optional[SelfServeEmailVerification]:
    result = await db.execute(
        select(SelfServeEmailVerification)
        .where(SelfServeEmailVerification.email == email,
               SelfServeEmailVerification.superseded_at.is_(None))
        .order_by(SelfServeEmailVerification.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def start_verification(db: AsyncSession, email: str) -> None:
    """Issue a fresh code for ``email``, superseding any earlier unverified row
    for the same email (so only the latest code is ever valid — a resend or a
    changed-email restart both go through here), and send it. Raises on a
    delivery failure — unlike a marketing send, the caller has no code without
    this succeeding, so it isn't swallowed as best-effort."""
    now = datetime.now(timezone.utc)
    await db.execute(
        update(SelfServeEmailVerification)
        .where(SelfServeEmailVerification.email == email,
               SelfServeEmailVerification.superseded_at.is_(None))
        .values(superseded_at=now)
    )

    code = _generate_code()
    row = SelfServeEmailVerification(
        email=email,
        code_hash=_hash_code(code),
        created_at=now,
        expires_at=now + timedelta(hours=CODE_TTL_HOURS),
    )
    db.add(row)
    await db.commit()

    await _send_code_email(email, code)


async def _send_code_email(email: str, code: str) -> None:
    subject = "Your BetterCricket verification code"
    html = f"""
    <div style="font-family:Arial,Helvetica,sans-serif;max-width:480px;margin:0 auto;padding:24px;color:#1a1a1a">
      <p style="font-size:14px;color:#555">BetterCricket</p>
      <h1 style="font-size:20px;margin:0 0 16px">Verify your email</h1>
      <p style="font-size:14px;line-height:1.5">
        Enter this code to continue your club's free trial registration:
      </p>
      <p style="font-size:32px;font-weight:bold;letter-spacing:6px;margin:24px 0">{code}</p>
      <p style="font-size:13px;color:#555">This code expires in {CODE_TTL_HOURS} hours.</p>
      <p style="font-size:12px;color:#888;margin-top:24px">
        If you didn't request this, you can safely ignore this email.
      </p>
    </div>
    """
    text = (
        f"Your BetterCricket verification code is {code}. "
        f"It expires in {CODE_TTL_HOURS} hours. "
        "If you didn't request this, you can safely ignore this email."
    )
    msg = email_service.EmailMessage(
        to_email=email,
        subject=subject,
        html=html,
        text=text,
        from_email=settings.email_from_address,
        from_name=settings.email_from_name,
        reply_to=settings.email_reply_to,
        # Platform-level send with no club yet to tenant against (registration
        # hasn't created the Organisation at this point) — the transactional
        # stream, not the per-club tenant selection in services/ses_tenants.py
        # (which requires an Organisation and doesn't apply pre-registration).
        configuration_set=(settings.ses_configuration_set_transactional or "").strip() or None,
    )
    result = await email_service.get_email_provider().send(msg)
    if not result.ok:
        raise RuntimeError(f"Could not send verification email: {result.error}")


class VerifyOutcome:
    OK = "ok"
    NO_ACTIVE_CODE = "no_active_code"
    EXPIRED = "expired"
    ALREADY_VERIFIED = "already_verified"
    INCORRECT = "incorrect"


async def check_code(db: AsyncSession, email: str, code: str) -> str:
    """Verify ``code`` against the latest active row for ``email``. Returns a
    VerifyOutcome constant. Caller is responsible for rate limiting attempts
    (services/rate_limit.py) before calling this — this function only updates
    the row's own attempt_count for audit, it doesn't enforce a lockout itself."""
    row = await _latest_active_row(db, email)
    if row is None:
        return VerifyOutcome.NO_ACTIVE_CODE
    if row.verified_at is not None:
        return VerifyOutcome.ALREADY_VERIFIED

    now = datetime.now(timezone.utc)
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if now > expires_at:
        return VerifyOutcome.EXPIRED

    if not _code_matches(code, row.code_hash):
        row.attempt_count = (row.attempt_count or 0) + 1
        await db.commit()
        return VerifyOutcome.INCORRECT

    row.verified_at = now
    await db.commit()
    return VerifyOutcome.OK


async def is_verified(db: AsyncSession, email: str) -> bool:
    row = await _latest_active_row(db, email)
    return bool(row and row.verified_at is not None)
