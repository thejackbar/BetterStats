"""Meta Conversions API (CAPI) — server-side event redundancy.

Sends key events (Lead first) to Meta's dataset events endpoint alongside the
existing browser pixel, sharing an `event_id` so Meta dedupes the pair into
one event instead of counting the lead twice. This catches leads the browser
pixel misses (ad blockers, iOS ITP, a page load that fails before the pixel
script runs).

Every call is best-effort: on any failure (not configured, bad token, Meta
outage) this logs and returns quietly. It never raises, so a CAPI hiccup can
never break the enquiry form or 500 the user's submission — the callers here
(routers/public_contact.py) invoke it via BackgroundTasks after the response's
own data is already safely stored.
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
from typing import Optional

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)

TIMEOUT = 10.0


def _events_url() -> str:
    return f"https://graph.facebook.com/{settings.meta_graph_version}/{settings.meta_dataset_id}/events"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_email(email: Optional[str]) -> Optional[str]:
    e = (email or "").strip().lower()
    return _sha256(e) if e else None


def _hash_phone(phone: Optional[str]) -> Optional[str]:
    # Meta wants digits only, with country code, no + or spaces. We only know
    # AU numbers in practice (this is an Australian club-cricket product), so
    # a bare 10-digit local number (04xx xxx xxx / 0X xxxx xxxx) gets the 61
    # country code substituted for the leading 0; anything already carrying a
    # country code (or anything else) is passed through digits-only as-is.
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return None
    if len(digits) == 10 and digits.startswith("0"):
        digits = "61" + digits[1:]
    return _sha256(digits)


def _hash_name_part(value: Optional[str]) -> Optional[str]:
    v = (value or "").strip().lower()
    return _sha256(v) if v else None


def _configured() -> bool:
    return bool(settings.meta_dataset_id and settings.meta_capi_access_token)


async def _send_event(
    event_name: str,
    *,
    event_id: Optional[str],
    event_source_url: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    name: Optional[str] = None,
    client_ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    fbp: Optional[str] = None,
    fbc: Optional[str] = None,
    value: float = 0,
    currency: str = "AUD",
    content_name: str = "",
    content_category: str = "",
) -> None:
    """Send one server-side event. Best-effort — logs, never raises."""
    if not _configured():
        logger.info("Meta CAPI not configured — skipping server-side %s event.", event_name)
        return
    if not event_id:
        # Without a shared event_id Meta can't dedupe this against the browser
        # pixel's copy, so sending it would double-count. Skip instead.
        logger.warning(
            "Meta CAPI: submission had no event_id — skipping %s event to avoid double counting.",
            event_name,
        )
        return

    user_data: dict = {}
    em = _hash_email(email)
    if em:
        user_data["em"] = [em]
    ph = _hash_phone(phone)
    if ph:
        user_data["ph"] = [ph]
    if name and name.strip():
        first, _, last = name.strip().partition(" ")
        fn = _hash_name_part(first)
        if fn:
            user_data["fn"] = [fn]
        ln = _hash_name_part(last)
        if ln:
            user_data["ln"] = [ln]
    if client_ip:
        user_data["client_ip_address"] = client_ip
    if user_agent:
        user_data["client_user_agent"] = user_agent
    if fbp:
        user_data["fbp"] = fbp
    if fbc:
        user_data["fbc"] = fbc

    event: dict = {
        "event_name": event_name,
        "event_time": int(time.time()),
        "event_id": event_id,
        "action_source": "website",
        "user_data": user_data,
        "custom_data": {
            "currency": currency,
            "value": value,
            "content_name": content_name,
            "content_category": content_category,
        },
    }
    if event_source_url:
        event["event_source_url"] = event_source_url

    body: dict = {"data": [event]}
    if settings.meta_test_event_code:
        body["test_event_code"] = settings.meta_test_event_code

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                _events_url(),
                params={"access_token": settings.meta_capi_access_token},
                json=body,
            )
    except httpx.HTTPError as e:
        logger.error("Meta CAPI %s event request failed: %s", event_name, e)
        return

    data: dict = {}
    try:
        data = resp.json()
    except ValueError:
        pass

    if resp.status_code != 200 or "error" in data:
        err = data.get("error", {})
        logger.error(
            "Meta CAPI %s event failed (status=%s): %s",
            event_name, resp.status_code, err.get("message") or data or resp.text[:300],
        )
        return

    logger.info(
        "Meta CAPI %s event sent: events_received=%s fbtrace_id=%s",
        event_name, data.get("events_received"), data.get("fbtrace_id"),
    )


async def send_lead_event(
    *,
    event_id: Optional[str],
    event_source_url: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    name: Optional[str] = None,
    client_ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    fbp: Optional[str] = None,
    fbc: Optional[str] = None,
    value: float = 399,
    currency: str = "AUD",
    content_name: str = "Request access",
    content_category: str = "club_enquiry",
) -> None:
    """Send a server-side `Lead` event (the Contact-form enquiry conversion).
    Best-effort — logs, never raises."""
    await _send_event(
        "Lead",
        event_id=event_id, event_source_url=event_source_url,
        email=email, phone=phone, name=name,
        client_ip=client_ip, user_agent=user_agent, fbp=fbp, fbc=fbc,
        value=value, currency=currency,
        content_name=content_name, content_category=content_category,
    )


async def send_complete_registration_event(
    *,
    event_id: Optional[str],
    event_source_url: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    name: Optional[str] = None,
    client_ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    fbp: Optional[str] = None,
    fbc: Optional[str] = None,
) -> None:
    """Send a server-side `CompleteRegistration` event — a finished public
    self-serve trial registration (routers/public_self_serve.py). This is the
    conversion the ad campaign optimises toward, one step deeper in the funnel
    than the Contact-form Lead. Value mirrors the Core annual price the trial
    leads to, same basis as the Lead event's 399. Best-effort — logs, never
    raises."""
    await _send_event(
        "CompleteRegistration",
        event_id=event_id, event_source_url=event_source_url,
        email=email, phone=phone, name=name,
        client_ip=client_ip, user_agent=user_agent, fbp=fbp, fbc=fbc,
        value=399, currency="AUD",
        content_name="Self-serve trial registration",
        content_category="self_serve_trial",
    )
