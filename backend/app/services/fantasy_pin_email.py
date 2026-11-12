"""BetterFantasyCricket: the "Forgot your PIN?" email.

A manager's PIN is stored as a bcrypt hash, so the PIN they chose cannot be read
back out and sent to them. The email carries a NEW PIN instead; the router only
swaps the stored hash once this has gone out (`routers/public_fantasy.forgot_pin`).
"""
from __future__ import annotations

from html import escape

from app.config.settings import settings
from app.services import email_service
from app.services.user_invite import _deliver, _greeting


async def send_new_pin_email(*, email: str, display_name: str, game_name: str, pin: str, link: str):
    """Send the new PIN. Returns the SendResult and never raises. The console
    provider is reported as a failure by `_deliver`, so a caller never tells a
    person "email sent" when nothing left the building."""
    game = escape(game_name)
    greeting = escape(_greeting(display_name))
    safe_link = escape(link, quote=True)
    subject = f"Your new {game_name} PIN"
    html = f"""
    <div style="font-family:Arial,Helvetica,sans-serif;max-width:480px;margin:0 auto;padding:24px;color:#1a1a1a">
      <p style="font-size:14px;color:#555">{game}</p>
      <h1 style="font-size:20px;margin:0 0 16px">Your new PIN</h1>
      <p style="font-size:14px;line-height:1.5">
        {greeting} you asked for a new PIN. Your old one no longer works. Use this one to sign in:
      </p>
      <p style="font-size:30px;letter-spacing:8px;font-weight:bold;margin:20px 0">{escape(pin)}</p>
      <p style="margin:24px 0">
        <a href="{safe_link}" style="display:inline-block;background:#16C784;color:#fff;
          text-decoration:none;padding:12px 24px;border-radius:6px;font-weight:bold;
          font-size:14px">Sign in</a>
      </p>
      <p style="font-size:12px;color:#888">
        Once you are in, you can pick your own PIN under Settings.
      </p>
      <p style="font-size:12px;color:#888;margin-top:24px">
        Didn't ask for this? Someone may have typed your email by mistake. Sign in with the PIN above
        and change it under Settings.
      </p>
    </div>
    """
    text = (
        f"{_greeting(display_name)} you asked for a new PIN for {game_name}. Your old one no longer works. "
        f"Your new PIN is {pin}. Sign in here: {link} "
        "Once you are in, you can pick your own PIN under Settings. "
        "Didn't ask for this? Someone may have typed your email by mistake. Sign in with this PIN and change it under Settings."
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
    return await _deliver(msg, "fantasy new PIN email")
