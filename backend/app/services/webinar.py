"""The BetterCricket webinar — one definition of the event, its registrations
and its calendar file.

THE DATE IS DECLARED ONCE, HERE (`EVENT`), and every state the page and the
email can be in is derived from it. The brief that asked for this said it
plainly: drive the before/after behaviour from one exported constant, not from
conditionals scattered across the page — a promo block still advertising a
webinar that happened last week is the one failure mode nobody notices until a
prospect does.

`frontend/src/data/webinar.js` is the hand-kept mirror of the same constant, so
the page can render its headline on first paint without waiting on a request
(the ad's traffic is mobile, and a fetch in front of the H1 is a fetch in front
of LCP). The verification asserts the two agree rather than taking it on trust
— the same arrangement `billing_pricing.py` and `pricing.js` already have.

The recording link deliberately does NOT live here. It does not exist until
after the event, and a super admin pasting it into General Settings
(`platform_settings.webinar_recording_url`) is what lets the page start serving
it that evening rather than waiting on a deploy.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.services import email_service

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WebinarEvent:
    key: str
    title: str
    # The start, in UTC. Perth is UTC+8 with no daylight saving, so 17:30 AWST
    # is 09:30 UTC — and on this date the eastern states are still on AEST
    # (UTC+10, daylight saving starts in October), which is the 19:30 AEST on
    # the ad creative. Both quoted times are the same instant.
    starts_at: datetime
    duration_minutes: int
    watch_url: str
    # What the page and the email print. Held as strings rather than formatted
    # from a timezone database at render time: these are the exact words the ad
    # creative uses, and message match between the ad and the page is what
    # stops paid traffic bouncing.
    date_label: str
    time_label: str

    @property
    def ends_at(self) -> datetime:
        return self.starts_at + timedelta(minutes=self.duration_minutes)

    def is_past(self, now: Optional[datetime] = None) -> bool:
        """Whether the event has finished. The page flips to its recording
        state on the END of the session, not the start — somebody arriving
        halfway through should still be sent to the live stream."""
        return (now or datetime.now(timezone.utc)) >= self.ends_at


EVENT = WebinarEvent(
    key="webinar-2026-09-21",
    title="BetterCricket live demo + Q&A",
    starts_at=datetime(2026, 9, 21, 9, 30, tzinfo=timezone.utc),
    duration_minutes=60,
    watch_url="https://streamyard.com/watch/ibBKm5Ek4sQu",
    date_label="Monday 21 September",
    time_label="5:30pm AWST / 7:30pm AEST",
)

ROLES = ["President", "Secretary", "Committee", "Coach", "Captain", "Player", "Other"]

MAX_LENGTHS = {
    "name": 200,
    "email": 320,
    "club": 200,
    "role": 60,
    "utm": 200,
    "click_id": 300,
    "referrer": 500,
    "landing_path": 500,
    "visitor_id": 64,
    "user_agent": 500,
}


def _clip(value: Any, limit: int) -> Optional[str]:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value[:limit] if text_value else None


def _ics_escape(value: str) -> str:
    """Escape a value for an iCalendar TEXT field. Backslash first, or the
    escapes we add next get escaped in turn."""
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _ics_stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_ics(event: WebinarEvent = EVENT, *, recording_url: Optional[str] = None) -> str:
    """The calendar file, in UTC.

    Written as a UTC `DTSTART`/`DTEND` rather than a floating local time with a
    VTIMEZONE block: a UTC instant needs no timezone definition travelling with
    it and lands at the right moment in every calendar app, wherever the
    registrant is. A VTIMEZONE we hand-wrote would be one more thing to be
    wrong about, for no gain on a single-instance event.

    Lines are joined with CRLF because RFC 5545 requires it — a file joined
    with bare newlines is accepted by some calendar apps and silently rejected
    by others, which is the worst of both.
    """
    link = recording_url or event.watch_url
    description = (
        f"{event.title}\\n\\n"
        f"{event.date_label} - {event.time_label}\\n\\n"
        f"Watch here: {link}"
    )
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//BetterCricket//Webinar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{event.key}@betterat.cricket",
        f"DTSTAMP:{_ics_stamp(datetime.now(timezone.utc))}",
        f"DTSTART:{_ics_stamp(event.starts_at)}",
        f"DTEND:{_ics_stamp(event.ends_at)}",
        f"SUMMARY:{_ics_escape(event.title)}",
        f"DESCRIPTION:{description}",
        f"LOCATION:{_ics_escape(link)}",
        f"URL:{_ics_escape(link)}",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines) + "\r\n"


def google_calendar_url(event: WebinarEvent = EVENT, *, recording_url: Optional[str] = None) -> str:
    from urllib.parse import urlencode

    link = recording_url or event.watch_url
    params = {
        "action": "TEMPLATE",
        "text": event.title,
        "dates": f"{_ics_stamp(event.starts_at)}/{_ics_stamp(event.ends_at)}",
        "details": f"{event.date_label} · {event.time_label}\n\nWatch here: {link}",
        "location": link,
    }
    return "https://calendar.google.com/calendar/render?" + urlencode(params)


async def register(
    db: AsyncSession,
    *,
    name: str,
    email: str,
    club: str,
    role: Optional[str] = None,
    attribution: Optional[dict] = None,
    visitor_id: Optional[str] = None,
    user_agent: Optional[str] = None,
    event: WebinarEvent = EVENT,
) -> dict:
    """Store one registration, folded on (event, lowercased email).

    A second submission from the same address CORRECTS the row it already has
    rather than adding a duplicate to the follow-up list — somebody re-checking
    their spelling, or registering again from a different device, is one
    registrant. `created` says which happened, and it is what the page reads to
    decide whether to fire the conversion pixel: a resubmission is not a new
    registration, and counting it as one would teach the ad set to optimise
    toward people who fill the form in twice.

    Attribution is only written on the row's FIRST insert, or refreshed later
    when the stored copy carries no campaign signal at all and the new one
    does. Overwriting it on every submission would credit the registration to
    whichever visit happened to be last rather than the click that earned it.
    """
    attribution = attribution or {}
    name = (name or "").strip()
    email = (email or "").strip()
    club = (club or "").strip()
    role = (role or "").strip() or None
    if role and role not in ROLES:
        role = None

    def attr(*keys: str) -> Optional[str]:
        for key in keys:
            value = attribution.get(key)
            if value:
                return _clip(value, MAX_LENGTHS["utm"])
        return None

    params = {
        "id": str(uuid.uuid4()),
        "event_key": event.key,
        "name": _clip(name, MAX_LENGTHS["name"]) or "",
        "email": _clip(email, MAX_LENGTHS["email"]) or "",
        "club": _clip(club, MAX_LENGTHS["club"]) or "",
        "role": _clip(role, MAX_LENGTHS["role"]),
        "utm_source": attr("utm_source"),
        "utm_medium": attr("utm_medium"),
        "utm_campaign": attr("utm_campaign"),
        "utm_content": attr("utm_content"),
        "utm_term": attr("utm_term"),
        "click_id": _clip(attribution.get("click_id"), MAX_LENGTHS["click_id"]),
        "click_source": _clip(attribution.get("click_source"), MAX_LENGTHS["utm"]),
        "attribution": _attribution_json(attribution),
        "referrer": _clip(attribution.get("landing_referrer"), MAX_LENGTHS["referrer"]),
        "landing_path": _clip(attribution.get("landing_path"), MAX_LENGTHS["landing_path"]),
        "visitor_id": _clip(visitor_id, MAX_LENGTHS["visitor_id"]),
        "user_agent": _clip(user_agent, MAX_LENGTHS["user_agent"]),
    }

    row = (await db.execute(text("""
        INSERT INTO webinar_registrations (
            id, event_key, name, email, club, role,
            utm_source, utm_medium, utm_campaign, utm_content, utm_term,
            click_id, click_source, attribution, referrer, landing_path,
            visitor_id, user_agent
        ) VALUES (
            CAST(:id AS uuid), :event_key, :name, :email, :club, :role,
            :utm_source, :utm_medium, :utm_campaign, :utm_content, :utm_term,
            :click_id, :click_source, CAST(:attribution AS jsonb), :referrer,
            :landing_path, :visitor_id, :user_agent
        )
        ON CONFLICT (event_key, lower(email)) DO UPDATE SET
            name = EXCLUDED.name,
            club = EXCLUDED.club,
            role = COALESCE(EXCLUDED.role, webinar_registrations.role),
            -- Only fill a gap. A registration already credited to a campaign
            -- keeps that credit; one that arrived with no signal at all can be
            -- upgraded by a later visit that has one.
            utm_source = COALESCE(webinar_registrations.utm_source, EXCLUDED.utm_source),
            utm_medium = COALESCE(webinar_registrations.utm_medium, EXCLUDED.utm_medium),
            utm_campaign = COALESCE(webinar_registrations.utm_campaign, EXCLUDED.utm_campaign),
            utm_content = COALESCE(webinar_registrations.utm_content, EXCLUDED.utm_content),
            utm_term = COALESCE(webinar_registrations.utm_term, EXCLUDED.utm_term),
            click_id = COALESCE(webinar_registrations.click_id, EXCLUDED.click_id),
            click_source = COALESCE(webinar_registrations.click_source, EXCLUDED.click_source),
            attribution = COALESCE(webinar_registrations.attribution, EXCLUDED.attribution),
            referrer = COALESCE(webinar_registrations.referrer, EXCLUDED.referrer),
            landing_path = COALESCE(webinar_registrations.landing_path, EXCLUDED.landing_path),
            visitor_id = COALESCE(webinar_registrations.visitor_id, EXCLUDED.visitor_id),
            updated_at = NOW()
        RETURNING id, (created_at = updated_at) AS created
    """), params)).mappings().one()
    await db.commit()
    return {"id": str(row["id"]), "created": bool(row["created"])}


def _attribution_json(attribution: dict) -> Optional[str]:
    import json

    if not attribution:
        return None
    # Key-allowlisted and clipped, the same treatment
    # organisations.signup_attribution gets — this arrives from a browser.
    allowed = {
        "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
        "click_id", "click_source", "has_signal", "landing_path", "landing_referrer",
        "referrer_host", "link_code",
    }
    clean = {
        key: (value if isinstance(value, bool) else _clip(value, 500))
        for key, value in attribution.items()
        if key in allowed and value is not None
    }
    return json.dumps(clean) if clean else None


async def mark_email_sent(db: AsyncSession, registration_id: str, *, error: Optional[str] = None) -> None:
    """Record the confirmation email's outcome ON THE ROW. A delivery marked
    sent only once the provider has accepted it, and a refusal recorded with
    its reason, is what makes "they say they never got it" answerable later."""
    try:
        await db.execute(text("""
            UPDATE webinar_registrations
               SET email_sent = :sent, email_error = :error, updated_at = NOW()
             WHERE id = CAST(:id AS uuid)
        """), {"id": registration_id, "sent": error is None, "error": _clip(error, 500)})
        await db.commit()
    except Exception:
        logger.exception("webinar: could not record email outcome for %s", registration_id)


def _confirmation_html(*, name: str, event: WebinarEvent, watch_url: str, calendar_url: str) -> str:
    greeting = f"Hi {name.split()[0]}," if name.strip() else "Hi,"
    return f"""
    <div style="font-family:Arial,Helvetica,sans-serif;max-width:520px;margin:0 auto;padding:24px;color:#1a1a1a">
      <p style="font-size:14px;color:#555;margin:0 0 8px">BetterCricket</p>
      <h1 style="font-size:22px;margin:0 0 16px">You're registered</h1>
      <p style="font-size:15px;line-height:1.6;margin:0 0 16px">{greeting}</p>
      <p style="font-size:15px;line-height:1.6;margin:0 0 20px">
        Thanks for registering for the BetterCricket live demo and Q&amp;A. Here are the details:
      </p>
      <table role="presentation" style="font-size:15px;line-height:1.6;margin:0 0 24px">
        <tr><td style="padding:2px 12px 2px 0;color:#555">When</td><td><strong>{event.date_label}</strong></td></tr>
        <tr><td style="padding:2px 12px 2px 0;color:#555">Time</td><td><strong>5:30pm AWST</strong> (Perth)</td></tr>
        <tr><td style="padding:2px 12px 2px 0;color:#555"></td><td><strong>7:30pm AEST</strong> (Sydney, Melbourne, Brisbane)</td></tr>
      </table>
      <p style="margin:0 0 24px">
        <a href="{watch_url}" style="display:inline-block;background:#0f172a;color:#fff;text-decoration:none;padding:12px 22px;border-radius:8px;font-weight:bold;font-size:15px">Watch the demo</a>
      </p>
      <p style="font-size:14px;line-height:1.6;margin:0 0 8px">
        Save the time: <a href="{calendar_url}" style="color:#0f172a">add to Google Calendar</a>
        or <a href="{settings.public_base_url}/api/public/webinar/calendar.ics" style="color:#0f172a">download the calendar file</a>
        (Outlook, Apple Calendar).
      </p>
      <p style="font-size:14px;line-height:1.6;color:#555;margin:0 0 24px">
        Can't make it live? Stay registered and we'll send you the full recording.
      </p>
      <hr style="border:0;border-top:1px solid #e5e7eb;margin:0 0 20px">
      <p style="font-size:14px;line-height:1.6;margin:0 0 8px">
        <strong>Would rather have a look around yourself?</strong>
      </p>
      <p style="font-size:14px;line-height:1.6;color:#555;margin:0 0 8px">
        Set your club up in about three minutes. It's free, there's no credit card and no sales call.
      </p>
      <p style="font-size:14px;margin:0 0 24px">
        <a href="{settings.public_base_url}/trial" style="color:#0f172a">Start your free trial &rarr;</a>
      </p>
      <p style="font-size:12px;color:#888;line-height:1.5;margin:0">
        You're getting this because you registered at {settings.public_base_url}/demo.
        Reply to this email if you have any questions.
      </p>
    </div>
    """


def _confirmation_text(*, name: str, event: WebinarEvent, watch_url: str) -> str:
    greeting = f"Hi {name.split()[0]}," if name.strip() else "Hi,"
    return (
        f"{greeting}\n\n"
        "Thanks for registering for the BetterCricket live demo and Q&A.\n\n"
        f"When: {event.date_label}\n"
        "Time: 5:30pm AWST (Perth) / 7:30pm AEST (Sydney, Melbourne, Brisbane)\n"
        f"Watch here: {watch_url}\n\n"
        "Add it to your calendar: "
        f"{settings.public_base_url}/api/public/webinar/calendar.ics\n\n"
        "Can't make it live? Stay registered and we'll send you the full recording.\n\n"
        "Would rather have a look around yourself? Set your club up in about three "
        "minutes - free, no credit card, no sales call: "
        f"{settings.public_base_url}/trial\n"
    )


async def send_confirmation(
    db: AsyncSession,
    *,
    registration_id: str,
    name: str,
    email: str,
    recording_url: Optional[str] = None,
    event: WebinarEvent = EVENT,
) -> None:
    """Send the confirmation email and record what happened.

    Best-effort by design: the success state on the page has already given the
    registrant the link and the calendar files, so a provider outage must not
    look to them like a failed registration. The outcome lands on the row
    either way.

    The calendar goes as a LINK to `/public/webinar/calendar.ics`, not as an
    attachment: `email_service.EmailMessage` carries no attachment field and
    the five providers behind it each take attachments differently (SES would
    need raw MIME rather than the simple content path it uses today). A link is
    what the brief allows and what every mail client handles.
    """
    watch_url = recording_url or event.watch_url
    try:
        message = email_service.EmailMessage(
            to_email=email,
            subject=f"You're registered — {event.title}",
            html=_confirmation_html(
                name=name, event=event, watch_url=watch_url,
                calendar_url=google_calendar_url(event, recording_url=recording_url),
            ),
            text=_confirmation_text(name=name, event=event, watch_url=watch_url),
            from_email=settings.email_from_address,
            from_name=settings.email_from_name,
            reply_to=settings.email_reply_to,
            # A platform-level send with no club to tenant against — the
            # transactional stream, same call self_serve_verification makes.
            configuration_set=(settings.ses_configuration_set_transactional or "").strip() or None,
        )
        result = await email_service.get_email_provider().send(message)
    except Exception as exc:  # noqa: BLE001 - never let a send take the request down
        logger.exception("webinar: confirmation email failed for %s", email)
        await mark_email_sent(db, registration_id, error=str(exc)[:500])
        return
    await mark_email_sent(
        db, registration_id,
        error=None if result.ok else (result.error or "unknown provider error"),
    )
