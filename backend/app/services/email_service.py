"""BetterComms — outbound email, provider-pluggable.

Why an abstraction: the platform should run **zero-cost** on an email
provider's free tier and be able to switch providers (or let a club bring its
own) without touching the calling code. Every provider implements one method —
``send(EmailMessage) -> SendResult`` — and the active provider is chosen from
settings.

Providers
  * ``console`` — logs the message and returns ok WITHOUT sending. The dev
    default, and the safe fallback when no API key is configured, so the API
    never tries to send real mail by accident.
  * ``brevo``   — Brevo (ex-Sendinblue) transactional API. Free tier 300/day
    (~9k/mo), unlimited contacts — best free burst volume for a club blast.
  * ``resend``  — Resend transactional API. Free tier 3k/mo (100/day), very
    clean API.

Going live is two ops steps the code can't do for you: create the provider
account + set ``email_api_key``, and verify the sending domain's SPF/DKIM/DMARC
(we send from a subdomain of the domain we already own, ``betterstats.cricket``)
so mail authenticates and lands in the inbox.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


@dataclass
class EmailMessage:
    to_email: str
    subject: str
    html: str
    text: str = ""
    to_name: Optional[str] = None
    from_email: Optional[str] = None
    from_name: Optional[str] = None
    reply_to: Optional[str] = None
    # Extra SMTP headers — notably List-Unsubscribe / List-Unsubscribe-Post,
    # which improve deliverability and give Gmail/Apple Mail a native one-click
    # unsubscribe (on top of the in-body link the Spam Act requires).
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class SendResult:
    ok: bool
    message_id: Optional[str] = None
    error: Optional[str] = None


class EmailProvider:
    name = "base"

    async def send(self, msg: EmailMessage) -> SendResult:  # pragma: no cover - interface
        raise NotImplementedError


class ConsoleEmailProvider(EmailProvider):
    """Logs instead of sending. Used in dev and whenever no key is configured —
    so the whole BetterComms flow is exercisable end-to-end without a provider,
    and a misconfigured prod fails safe (nothing leaves the building)."""

    name = "console"

    async def send(self, msg: EmailMessage) -> SendResult:
        logger.info(
            "[email:console] would send to=%s subject=%r from=%s reply_to=%s",
            msg.to_email, msg.subject, msg.from_email, msg.reply_to,
        )
        return SendResult(ok=True, message_id="console")


class BrevoEmailProvider(EmailProvider):
    name = "brevo"
    ENDPOINT = "https://api.brevo.com/v3/smtp/email"

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def send(self, msg: EmailMessage) -> SendResult:
        payload: dict = {
            "sender": {"email": msg.from_email, "name": msg.from_name or msg.from_email},
            "to": [{"email": msg.to_email, **({"name": msg.to_name} if msg.to_name else {})}],
            "subject": msg.subject,
            "htmlContent": msg.html,
        }
        if msg.text:
            payload["textContent"] = msg.text
        if msg.reply_to:
            payload["replyTo"] = {"email": msg.reply_to}
        if msg.headers:
            payload["headers"] = msg.headers
        headers = {
            "api-key": self.api_key,
            "accept": "application/json",
            "content-type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(self.ENDPOINT, json=payload, headers=headers)
            if resp.status_code >= 400:
                return SendResult(ok=False, error=f"brevo {resp.status_code}: {resp.text[:300]}")
            data = resp.json() if resp.content else {}
            return SendResult(ok=True, message_id=str(data.get("messageId") or ""))
        except Exception as e:  # network / timeout / json
            return SendResult(ok=False, error=f"brevo error: {e}")


class ResendEmailProvider(EmailProvider):
    name = "resend"
    ENDPOINT = "https://api.resend.com/emails"

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def send(self, msg: EmailMessage) -> SendResult:
        sender = f"{msg.from_name} <{msg.from_email}>" if msg.from_name else (msg.from_email or "")
        payload: dict = {
            "from": sender,
            "to": [msg.to_email],
            "subject": msg.subject,
            "html": msg.html,
        }
        if msg.text:
            payload["text"] = msg.text
        if msg.reply_to:
            payload["reply_to"] = msg.reply_to
        if msg.headers:
            payload["headers"] = msg.headers
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "content-type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(self.ENDPOINT, json=payload, headers=headers)
            if resp.status_code >= 400:
                return SendResult(ok=False, error=f"resend {resp.status_code}: {resp.text[:300]}")
            data = resp.json() if resp.content else {}
            return SendResult(ok=True, message_id=str(data.get("id") or ""))
        except Exception as e:
            return SendResult(ok=False, error=f"resend error: {e}")


def get_email_provider() -> EmailProvider:
    """Resolve the active provider from settings, falling back to console.

    A configured provider with no API key falls back to console (fail-safe) so
    we never attempt an unauthenticated send.
    """
    name = (settings.email_provider or "console").strip().lower()
    key = (settings.email_api_key or "").strip()
    if name == "brevo" and key:
        return BrevoEmailProvider(key)
    if name == "resend" and key:
        return ResendEmailProvider(key)
    if name not in ("console", "brevo", "resend"):
        logger.warning("Unknown email_provider %r — using console", name)
    return ConsoleEmailProvider()


def email_is_live() -> bool:
    """True when a real provider + key are configured (i.e. sends actually go
    out). The admin UI uses this to warn that it's in 'preview / no-send' mode."""
    return get_email_provider().name != "console"


def provider_status() -> dict:
    """Non-secret provider config for the settings screen."""
    return {
        "provider": (settings.email_provider or "console").strip().lower(),
        "live": email_is_live(),
        "from_address": settings.email_from_address,
        "from_name": settings.email_from_name,
    }
