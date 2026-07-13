"""Invitation email for a new club-admin user (routers/club_admin.py's
"Invite admin" — create_club_user). The account is created with no usable
password (password_hash NULL) plus a random urlsafe token; this just sends
the link that lets them set their own password and activate the account.
Mirrors self_serve_verification.py's email-construction pattern.
"""
from __future__ import annotations

from app.config.settings import settings
from app.services import email_service


async def send_invite_email(*, email: str, display_name: str, club_name: str, link: str) -> None:
    """Best-effort: logs on failure but never raises — the account already
    exists regardless of whether this email lands, and the invited user (or
    the inviting admin) can always be given the link another way if delivery
    fails."""
    subject = f"You've been invited to {club_name} on BetterCricket"
    html = f"""
    <div style="font-family:Arial,Helvetica,sans-serif;max-width:480px;margin:0 auto;padding:24px;color:#1a1a1a">
      <p style="font-size:14px;color:#555">BetterCricket</p>
      <h1 style="font-size:20px;margin:0 0 16px">You're invited to {club_name}</h1>
      <p style="font-size:14px;line-height:1.5">
        {display_name or 'You'} have been added as an admin for {club_name} on
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
        f"You've been invited as an admin for {club_name} on BetterCricket. "
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
    )
    try:
        result = await email_service.get_email_provider().send(msg)
        if not result.ok:
            raise RuntimeError(result.error)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Could not send invite email to %s", email)
