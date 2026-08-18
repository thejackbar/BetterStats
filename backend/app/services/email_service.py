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
(we send from a subdomain of ``betterstats.cricket``, where those records live;
it moves to ``betterat.cricket`` once they are set up there)
so mail authenticates and lands in the inbox.
"""
from __future__ import annotations

import asyncio
import datetime
import hashlib
import hmac
import json
import logging
from dataclasses import dataclass, field
from email.message import EmailMessage as MIMEMessage
from email.utils import make_msgid
from typing import Optional

import aiosmtplib
import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(30.0, connect=10.0)

# SES send retry (throttling / transient 5xx only). Kept small — the pacer keeps
# us under the rate ceiling, so retries are the exception, not the rule.
_SES_MAX_RETRIES = 3
_SES_BACKOFF_BASE = 0.5   # seconds; doubles each attempt
_SES_BACKOFF_MAX = 8.0


def _retry_after_seconds(resp: "httpx.Response") -> float:
    """Honour a Retry-After header (SES/ELB sometimes sends one on a throttle).
    Returns 0 when absent or unparseable, letting the caller fall back to its
    exponential backoff."""
    raw = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
    if not raw:
        return 0.0
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return 0.0


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
    # SES configuration set for this send. Drives which event destination (and so
    # the bounce/complaint webhook) and reputation stream the send belongs to.
    # Ignored by non-SES providers.
    configuration_set: Optional[str] = None
    # SES tenant to send on behalf of (multi-tenancy). Set by the caller only when
    # ses_tenant_sends_enabled. Ignored by non-SES providers. See services/ses_tenants.
    tenant: Optional[str] = None
    # What KIND of send this is: 'automated' (a scheduled scan sent it, and
    # nobody asked for it), 'transactional' (one person's action produced
    # exactly one email, and that email is how the action completes) or
    # 'campaign' (a person composed it and pressed Send). Read by the pause
    # gate in get_email_provider — see services/email_pause, which is also
    # where the rule lives that ONLY 'automated' can ever be held.
    #
    # The default is 'transactional' — unpausable — so a send that somehow
    # never names a category goes out rather than being held. Getting an
    # extra nudge is a nuisance; being locked out of your account because an
    # untagged invite was held is not. Every EmailMessage in the tree names
    # its category explicitly, and the verification asserts that, so this
    # default is a backstop rather than the normal path.
    category: str = "transactional"


@dataclass
class SendResult:
    ok: bool
    message_id: Optional[str] = None
    error: Optional[str] = None
    # True when the pause gate held this send. Distinct from an ordinary
    # failure: nothing was attempted and nothing is wrong with the message, so
    # a caller that records "sent" state must not record it, and a caller
    # showing an error should say the platform's email is paused rather than
    # blaming the provider.
    suppressed: bool = False


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


class SMTPEmailProvider(EmailProvider):
    """Generic SMTP sender — the path to high-volume / pay-as-you-go delivery.

    This is how you escape the free-tier daily caps for 500+-recipient club
    blasts. Point it at:
      * **Amazon SES** — ~$0.10 per 1,000 emails, no per-day cap (out of the
        sandbox), scales to every club from one account.
      * a **self-hosted MTA** (Postal, Listmonk's relay, Maddy) — no per-email
        fee at all, at the cost of running it + owning deliverability.
      * a club's **own Workspace** mailbox (BYO), later.

    Builds a proper multipart/alternative (text + HTML) MIME message so the
    List-Unsubscribe headers and plain-text fallback survive.
    """
    name = "smtp"

    def __init__(self, host: str, port: int, user: str, password: str):
        self.host = host
        self.port = int(port or 587)
        self.user = user or ""
        self.password = password or ""

    async def send(self, msg: EmailMessage) -> SendResult:
        mime = MIMEMessage()
        mime["From"] = f"{msg.from_name} <{msg.from_email}>" if msg.from_name else (msg.from_email or "")
        mime["To"] = f"{msg.to_name} <{msg.to_email}>" if msg.to_name else msg.to_email
        mime["Subject"] = msg.subject
        if msg.reply_to:
            mime["Reply-To"] = msg.reply_to
        mid = make_msgid()
        mime["Message-ID"] = mid
        for k, v in (msg.headers or {}).items():
            mime[k] = v
        mime.set_content(msg.text or " ")
        mime.add_alternative(msg.html or "", subtype="html")

        kwargs: dict = {
            "hostname": self.host,
            "port": self.port,
            "timeout": 30,
            "username": self.user or None,
            "password": self.password or None,
        }
        # Port 465 = implicit TLS; everything else (587/25) = STARTTLS.
        if self.port == 465:
            kwargs["use_tls"] = True
        else:
            kwargs["start_tls"] = True
        try:
            await aiosmtplib.send(mime, **kwargs)
            return SendResult(ok=True, message_id=mid)
        except Exception as e:
            return SendResult(ok=False, error=f"smtp error: {e}")


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _sigv4_headers(*, service: str, region: str, host: str, path: str, body: str,
                   access_key: str, secret_key: str,
                   content_type: str = "application/json") -> dict:
    """Minimal AWS SigV4 (POST) signer — stdlib only, no boto3. Signs the four
    headers SES needs and returns the request headers including Authorization."""
    now = datetime.datetime.now(datetime.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()

    canonical_headers = (
        f"content-type:{content_type}\n"
        f"host:{host}\n"
        f"x-amz-content-sha256:{payload_hash}\n"
        f"x-amz-date:{amz_date}\n"
    )
    signed_headers = "content-type;host;x-amz-content-sha256;x-amz-date"
    canonical_request = "\n".join([
        "POST", path, "", canonical_headers, signed_headers, payload_hash,
    ])
    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join([
        "AWS4-HMAC-SHA256", amz_date, credential_scope,
        hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
    ])
    k_date = _sign(("AWS4" + secret_key).encode("utf-8"), date_stamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    k_signing = _sign(k_service, "aws4_request")
    signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    authorization = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    return {
        "Content-Type": content_type,
        "X-Amz-Date": amz_date,
        "X-Amz-Content-Sha256": payload_hash,
        "Authorization": authorization,
    }


class SesEmailProvider(EmailProvider):
    """Amazon SES via the SESv2 send API (SigV4-signed, no boto3 dependency).

    This is the production sender. Each send carries a per-club From on the
    verified per-silo domain (resolved by the caller) and a configuration set,
    which is what routes bounce/complaint events back to /public/ses/events and
    keeps each tenant's reputation isolated. See docs/bettercomms-architecture.md.
    """
    name = "ses"

    def __init__(self, region: str, access_key: str, secret_key: str,
                 default_config_set: str = ""):
        self.region = region
        self.access_key = access_key
        self.secret_key = secret_key
        self.default_config_set = default_config_set
        self.host = f"email.{region}.amazonaws.com"
        self.path = "/v2/email/outbound-emails"

    async def send(self, msg: EmailMessage) -> SendResult:
        from_field = f"{msg.from_name} <{msg.from_email}>" if msg.from_name else (msg.from_email or "")
        body_content: dict = {}
        if msg.text:
            body_content["Text"] = {"Data": msg.text, "Charset": "UTF-8"}
        if msg.html:
            body_content["Html"] = {"Data": msg.html, "Charset": "UTF-8"}
        simple: dict = {
            "Subject": {"Data": msg.subject, "Charset": "UTF-8"},
            "Body": body_content,
        }
        if msg.headers:
            simple["Headers"] = [{"Name": k, "Value": v} for k, v in msg.headers.items()]
        payload: dict = {
            "FromEmailAddress": from_field,
            "Destination": {"ToAddresses": [msg.to_email]},
            "Content": {"Simple": simple},
        }
        if msg.reply_to:
            payload["ReplyToAddresses"] = [msg.reply_to]
        cfg = msg.configuration_set or self.default_config_set
        if cfg:
            payload["ConfigurationSetName"] = cfg
        # Multi-tenancy: attribute the send to the club's SES tenant. Only set by
        # the caller when ses_tenant_sends_enabled. NOTE: verify this field against
        # current SES docs before enabling the flag — it's the one send-time tenant
        # mechanism to confirm; everything else (provisioning) is independent.
        if msg.tenant:
            payload["TenantName"] = msg.tenant
        body = json.dumps(payload)
        # A throttle (429) or a transient 5xx means "slow down / try again", not
        # "this address is bad" — retry with backoff so a momentary rate blip or
        # server error doesn't permanently drop the recipient. The account-wide
        # pacer (services/send_rate_limiter) already keeps us under the per-second
        # ceiling; this is the belt-and-braces for the edges. SigV4 is re-signed
        # each attempt (the signature is time-bound).
        last_err = "ses error"
        for attempt in range(_SES_MAX_RETRIES + 1):
            headers = _sigv4_headers(
                service="ses", region=self.region, host=self.host, path=self.path,
                body=body, access_key=self.access_key, secret_key=self.secret_key)
            try:
                async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                    resp = await client.post(f"https://{self.host}{self.path}", content=body, headers=headers)
                if resp.status_code < 400:
                    data = resp.json() if resp.content else {}
                    return SendResult(ok=True, message_id=str(data.get("MessageId") or ""))
                last_err = f"ses {resp.status_code}: {resp.text[:300]}"
                # Retry throttling + server errors; a 4xx that isn't 429 is a real
                # rejection (bad address / not verified) — fail fast, no retry.
                retryable = resp.status_code == 429 or resp.status_code >= 500
                if not retryable or attempt >= _SES_MAX_RETRIES:
                    return SendResult(ok=False, error=last_err)
                delay = _retry_after_seconds(resp) or (_SES_BACKOFF_BASE * (2 ** attempt))
                await asyncio.sleep(min(delay, _SES_BACKOFF_MAX))
            except Exception as e:  # network / timeout
                last_err = f"ses error: {e}"
                if attempt >= _SES_MAX_RETRIES:
                    return SendResult(ok=False, error=last_err)
                await asyncio.sleep(min(_SES_BACKOFF_BASE * (2 ** attempt), _SES_BACKOFF_MAX))
        return SendResult(ok=False, error=last_err)


class PausedProvider(EmailProvider):
    """Wraps the real provider and holds back a send whose category is paused.

    The gate lives here, wrapping the single provider every caller reaches
    through, rather than at the places that compose a message: a new email
    added later is covered without anyone remembering to add a check.

    Only 'automated' (reminders and nudges) is pausable. Transactional email
    — invites, password resets, the signup verification code, the member
    portal sign-in link — carries system operations and is never held, by
    construction rather than by configuration. See services/email_pause.

    Proxies ``name``, so email_is_live() and the "preview / no-send" notice
    keep reporting the underlying provider rather than the wrapper.
    """

    def __init__(self, inner: EmailProvider):
        self.inner = inner

    @property
    def name(self) -> str:  # type: ignore[override]
        return self.inner.name

    async def send(self, msg: EmailMessage) -> SendResult:
        from app.services import email_pause

        # Only 'automated' can ever come back True here — is_paused returns
        # False for every other category before it reads any setting, so no
        # configuration and no database failure can hold back a transactional
        # or campaign send.
        category = getattr(msg, "category", email_pause.CATEGORY_TRANSACTIONAL)
        if await email_pause.is_paused(category):
            # Logged at WARNING with the recipient's domain only — enough to
            # see what is being held and for whom, without writing a list of
            # members' addresses into the container logs.
            domain = (msg.to_email or "").rsplit("@", 1)[-1]
            logger.warning(
                "email paused (%s): held %r to @%s", category, msg.subject, domain
            )
            return SendResult(
                ok=False,
                error=f"{category} email is paused platform-wide",
                suppressed=True,
            )
        return await self.inner.send(msg)


def get_email_provider() -> EmailProvider:
    """Resolve the active provider from settings, falling back to console,
    wrapped in the pause gate.

    A provider that's selected but not fully configured falls back to console
    (fail-safe) so we never attempt an unauthenticated / misconfigured send.
    """
    return PausedProvider(_resolve_provider())


def _resolve_provider() -> EmailProvider:
    name = (settings.email_provider or "console").strip().lower()
    key = (settings.email_api_key or "").strip()
    if name == "brevo" and key:
        return BrevoEmailProvider(key)
    if name == "resend" and key:
        return ResendEmailProvider(key)
    if name == "smtp" and (settings.smtp_host or "").strip():
        return SMTPEmailProvider(settings.smtp_host, settings.smtp_port, settings.smtp_user, settings.smtp_password)
    if name == "ses" and (settings.ses_access_key_id or "").strip() and (settings.ses_secret_access_key or "").strip():
        return SesEmailProvider(settings.ses_region, settings.ses_access_key_id,
                                settings.ses_secret_access_key, settings.ses_configuration_set)
    if name not in ("console", "brevo", "resend", "smtp", "ses"):
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
