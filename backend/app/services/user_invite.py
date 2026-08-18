"""Account-activation emails for club-admin users: the "Invite admin" flow
(routers/club_admin.py::create_club_user), the admin-triggered "Send password
reset email" flow for an existing account (routers/club_admin.py::
send_password_reset_link), and the self-serve "Forgot password" flow a user
triggers themselves from the login page (routers/auth.py::forgot_password).
All three mirror self_serve_verification.py's email-construction pattern.
"""
from __future__ import annotations

from app.config.settings import settings
from app.services import email_pause, email_service


def _greeting(display_name: str) -> str:
    # Callers pass whatever name they have on file (often a full "First
    # Last" display name, e.g. the Invite admin form only collects one
    # combined field) — the greeting itself should only ever use the first
    # word of it.
    parts = (display_name or "").split()
    first = parts[0] if parts else ""
    return f"Hi {first}," if first else "Hi there,"


async def send_invite_email(*, email: str, display_name: str, club_name: str, link: str) -> None:
    """Best-effort: logs on failure but never raises — the account already
    exists regardless of whether this email lands, and the invited user (or
    the inviting admin) can always be given the link another way if delivery
    fails."""
    subject = f"You've been invited to {club_name} on BetterCricket"
    greeting = _greeting(display_name)
    html = f"""
    <div style="font-family:Arial,Helvetica,sans-serif;max-width:480px;margin:0 auto;padding:24px;color:#1a1a1a">
      <p style="font-size:14px;color:#555">BetterCricket</p>
      <h1 style="font-size:20px;margin:0 0 16px">You're invited to {club_name}</h1>
      <p style="font-size:14px;line-height:1.5">
        {greeting} you have been added as a Club Admin for {club_name} on
        BetterCricket. Set your password to activate your account:
      </p>
      <p style="margin:24px 0">
        <a href="{link}" style="display:inline-block;background:#16C784;color:#fff;
          text-decoration:none;padding:12px 24px;border-radius:6px;font-weight:bold;
          font-size:14px">Set your password</a>
      </p>
      <p style="font-size:12px;color:#888">
        Or paste this link into your browser: {link}
      </p>
      <p style="font-size:12px;color:#888;margin-top:24px">
        If you weren't expecting this, you can safely ignore this email.
      </p>
    </div>
    """
    text = (
        f"{greeting} you have been added as a Club Admin for {club_name} on BetterCricket. "
        f"Set your password to activate your account: {link} "
        "If you weren't expecting this, you can safely ignore this email."
    )
    msg = email_service.EmailMessage(
        to_email=email,
        subject=subject,
        html=html,
        text=text,
        from_email=settings.email_from_address,
        from_name=settings.email_from_name,
        reply_to=settings.email_reply_to,
        configuration_set=(settings.ses_configuration_set_transactional or "").strip() or None,
        # One person's action produced exactly one email — held while
        # transactional email is paused (services/email_pause).
        category=email_pause.CATEGORY_TRANSACTIONAL,
    )
    try:
        result = await email_service.get_email_provider().send(msg)
        if not result.ok:
            raise RuntimeError(result.error)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Could not send invite email to %s", email)


async def send_password_reset_email(*, email: str, display_name: str, club_name: str, link: str) -> None:
    """Best-effort, same delivery/error-handling shape as send_invite_email above.
    Sent when a club admin clicks "Send password reset email" for an existing
    account (routers/club_admin.py::send_password_reset_link) — the account
    already has a working password, this just offers a way to replace it."""
    subject = f"Reset your BetterCricket password for {club_name}"
    greeting = _greeting(display_name)
    html = f"""
    <div style="font-family:Arial,Helvetica,sans-serif;max-width:480px;margin:0 auto;padding:24px;color:#1a1a1a">
      <p style="font-size:14px;color:#555">BetterCricket</p>
      <h1 style="font-size:20px;margin:0 0 16px">Reset your password</h1>
      <p style="font-size:14px;line-height:1.5">
        {greeting} an admin at {club_name} asked BetterCricket to send you a
        link to reset your password. Click below to choose a new one:
      </p>
      <p style="margin:24px 0">
        <a href="{link}" style="display:inline-block;background:#16C784;color:#fff;
          text-decoration:none;padding:12px 24px;border-radius:6px;font-weight:bold;
          font-size:14px">Reset your password</a>
      </p>
      <p style="font-size:12px;color:#888">
        Or paste this link into your browser: {link}
      </p>
      <p style="font-size:12px;color:#888;margin-top:24px">
        If you weren't expecting this, you can safely ignore this email — your
        password won't change unless you click the link above.
      </p>
    </div>
    """
    text = (
        f"{greeting} an admin at {club_name} asked BetterCricket to send you a link to reset "
        f"your password: {link} "
        "If you weren't expecting this, you can safely ignore this email — your password won't "
        "change unless you follow the link."
    )
    msg = email_service.EmailMessage(
        to_email=email,
        subject=subject,
        html=html,
        text=text,
        from_email=settings.email_from_address,
        from_name=settings.email_from_name,
        reply_to=settings.email_reply_to,
        configuration_set=(settings.ses_configuration_set_transactional or "").strip() or None,
        # One person's action produced exactly one email — held while
        # transactional email is paused (services/email_pause).
        category=email_pause.CATEGORY_TRANSACTIONAL,
    )
    try:
        result = await email_service.get_email_provider().send(msg)
        if not result.ok:
            raise RuntimeError(result.error)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Could not send password reset email to %s", email)


async def send_self_password_reset_email(*, email: str, display_name: str, club_name: str, link: str) -> None:
    """Same delivery/error-handling shape as send_password_reset_email above,
    but standard "forgot password" copy for a self-serve request (the user
    asked, not an admin on their behalf) — routers/auth.py::forgot_password."""
    subject = "Reset your BetterCricket password"
    greeting = _greeting(display_name)
    html = f"""
    <div style="font-family:Arial,Helvetica,sans-serif;max-width:480px;margin:0 auto;padding:24px;color:#1a1a1a">
      <p style="font-size:14px;color:#555">BetterCricket</p>
      <h1 style="font-size:20px;margin:0 0 16px">Reset your password</h1>
      <p style="font-size:14px;line-height:1.5">
        {greeting} we received a request to reset the password on your {club_name}
        account. Click below to choose a new one:
      </p>
      <p style="margin:24px 0">
        <a href="{link}" style="display:inline-block;background:#16C784;color:#fff;
          text-decoration:none;padding:12px 24px;border-radius:6px;font-weight:bold;
          font-size:14px">Reset your password</a>
      </p>
      <p style="font-size:12px;color:#888">
        Or paste this link into your browser: {link}
      </p>
      <p style="font-size:12px;color:#888;margin-top:24px">
        Didn't ask for this? You can ignore this email and your password will stay the same.
      </p>
    </div>
    """
    text = (
        f"{greeting} we received a request to reset the password on your {club_name} "
        f"account: {link} "
        "Didn't ask for this? You can ignore this email and your password will stay the same."
    )
    msg = email_service.EmailMessage(
        to_email=email,
        subject=subject,
        html=html,
        text=text,
        from_email=settings.email_from_address,
        from_name=settings.email_from_name,
        reply_to=settings.email_reply_to,
        configuration_set=(settings.ses_configuration_set_transactional or "").strip() or None,
        # One person's action produced exactly one email — held while
        # transactional email is paused (services/email_pause).
        category=email_pause.CATEGORY_TRANSACTIONAL,
    )
    try:
        result = await email_service.get_email_provider().send(msg)
        if not result.ok:
            raise RuntimeError(result.error)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Could not send self-serve password reset email to %s", email)
