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


def page_meta(is_past: Optional[bool] = None) -> tuple[str, str]:
    """The /demo page title and description, for the state the event is in.

    THE SHARE CARD IS SERVER-RENDERED, so this is what a crawler actually reads
    — `usePageMeta` never reaches Facebook, LinkedIn or WhatsApp, none of which
    run the page's JS. Both copies were hardcoded to the post-event wording for
    one release, so every share of the page advertised a recording of a demo
    that had not happened yet.

    Mirrored in `frontend/src/data/webinar.js::webinarState` (pageTitle /
    pageDescription) for the browser tab; the verification asserts the two
    agree rather than taking it on trust.
    """
    past = EVENT.is_past() if is_past is None else is_past
    if past:
        return (
            "Watch the BetterCricket demo | Recording + Q&A",
            "Watch the BetterCricket demo recording: historical stats, "
            "selection, socials, club admin and opposition analysis, plus the "
            "questions clubs asked on the night.",
        )
    return (
        "See BetterCricket in action | Live demo + Q&A",
        "See the whole of BetterCricket in one sitting: historical stats, "
        "selection, socials, club admin and opposition analysis, then ask us "
        "anything. Register free.",
    )


ROLES = ["President", "Secretary", "Committee", "Coach", "Captain", "Player", "Other"]

MAX_LENGTHS = {
    "name": 200,
    "email": 320,
    "club": 200,
    "phone": 40,
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
    phone: Optional[str] = None,
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
    phone = (phone or "").strip() or None
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
        "phone": _clip(phone, MAX_LENGTHS["phone"]),
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
            id, event_key, name, email, club, phone, role,
            utm_source, utm_medium, utm_campaign, utm_content, utm_term,
            click_id, click_source, attribution, referrer, landing_path,
            visitor_id, user_agent
        ) VALUES (
            CAST(:id AS uuid), :event_key, :name, :email, :club, :phone, :role,
            :utm_source, :utm_medium, :utm_campaign, :utm_content, :utm_term,
            :click_id, :click_source, CAST(:attribution AS jsonb), :referrer,
            :landing_path, :visitor_id, :user_agent
        )
        ON CONFLICT (event_key, lower(email)) DO UPDATE SET
            name = EXCLUDED.name,
            club = EXCLUDED.club,
            -- A correction, so a new number wins — but never blanked back to
            -- nothing by a submission that carried none. Name and club are
            -- overwritten outright because they are always present; a phone
            -- can legitimately be absent (a browser served an older bundle
            -- mid-deploy, a caller that is not the form), and losing a stored
            -- number to one of those is worse than keeping a stale one.
            phone = COALESCE(EXCLUDED.phone, webinar_registrations.phone),
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


# How long before the session starts the reminder goes out. Chosen for the
# 5:30pm AWST / 7:30pm AEST slot this event runs in: three hours puts it in
# somebody's afternoon on the west coast and their early evening on the east,
# which is when a person can still change their plans. Earlier and it is read
# at work and forgotten; later and the east coast is already sitting down to
# dinner.
REMINDER_LEAD_HOURS = 3


def reminder_window_open(event: WebinarEvent = EVENT, now: Optional[datetime] = None) -> bool:
    """Whether we are inside the send window: close enough to the start to be
    a reminder, and not past the end. A reminder that lands after the session
    has finished is worse than none — it tells somebody to go to a stream that
    is over."""
    now = now or datetime.now(timezone.utc)
    return (event.starts_at - timedelta(hours=REMINDER_LEAD_HOURS)) <= now < event.ends_at


async def send_reminders(
    db: AsyncSession,
    *,
    event: WebinarEvent = EVENT,
    now: Optional[datetime] = None,
) -> dict:
    """Email everyone registered for `event` who has not had their reminder.

    WHY THIS EXISTS: StreamYard's own webinar registration sends a reminder,
    and switching that gate off — which is what stops a registrant filling a
    form twice — takes the reminder with it. Everything the second form asks
    for is already on our own row, so this is the one thing worth replacing.

    NOBODY WHO REGISTERED INSIDE THE WINDOW IS REMINDED. Their confirmation
    email went out minutes ago and carries the same link; a second one an hour
    later reads as a mistake rather than a courtesy.

    The row is CLAIMED before the send (`reminder_sent_at` stamped by the same
    UPDATE that selects it), so two overlapping runs cannot both email one
    person. A refusal clears the claim, so the next run retries. Never raises —
    the job that calls this must not fall over on one bad address.
    """
    now = now or datetime.now(timezone.utc)
    if not reminder_window_open(event, now):
        return {"claimed": 0, "sent": 0, "failed": 0, "skipped": "outside window"}

    # Claimed in one statement: SELECT and stamp cannot be separated, or two
    # runs a second apart both read the same unsent rows.
    rows = (await db.execute(text("""
        UPDATE webinar_registrations
           SET reminder_sent_at = NOW(), reminder_error = NULL, updated_at = NOW()
         WHERE event_key = :event_key
           AND reminder_sent_at IS NULL
           -- Registered before the window opened. Anyone who signed up since
           -- has just had the confirmation, which says the same thing.
           AND created_at < :window_opens
     RETURNING id, name, email
    """), {
        "event_key": event.key,
        "window_opens": event.starts_at - timedelta(hours=REMINDER_LEAD_HOURS),
    })).mappings().all()
    await db.commit()

    sent = failed = 0
    for row in rows:
        ok, error = await _send_reminder_email(
            name=row["name"] or "", email=row["email"] or "", event=event,
        )
        if ok:
            sent += 1
            continue
        failed += 1
        # Hand the claim back so the next run tries again, and keep the reason.
        try:
            await db.execute(text("""
                UPDATE webinar_registrations
                   SET reminder_sent_at = NULL, reminder_error = :error, updated_at = NOW()
                 WHERE id = :id
            """), {"id": row["id"], "error": _clip(error, 500)})
            await db.commit()
        except Exception:
            logger.exception("webinar: could not release reminder claim for %s", row["email"])
            await db.rollback()

    if rows:
        logger.info("webinar reminders: %s sent, %s failed", sent, failed)
    return {"claimed": len(rows), "sent": sent, "failed": failed}


async def _send_reminder_email(
    *, name: str, email: str, event: WebinarEvent,
) -> tuple[bool, Optional[str]]:
    """One reminder. Returns (ok, error) rather than raising, so one refused
    address cannot stop the rest of the sweep."""
    try:
        message = email_service.EmailMessage(
            to_email=email,
            subject=f"Today: {event.title}",
            html=_reminder_html(name=name, event=event, watch_url=event.watch_url),
            text=_reminder_text(name=name, event=event, watch_url=event.watch_url),
            from_email=settings.email_from_address,
            from_name=settings.email_from_name,
            reply_to=settings.email_reply_to,
            configuration_set=(settings.ses_configuration_set_transactional or "").strip() or None,
        )
        result = await email_service.get_email_provider().send(message)
    except Exception as exc:  # noqa: BLE001 - one bad address must not stop the sweep
        logger.exception("webinar: reminder email failed for %s", email)
        return False, str(exc)[:500]
    if result.ok:
        return True, None
    return False, (result.error or "unknown provider error")


def _reminder_html(*, name: str, event: WebinarEvent, watch_url: str) -> str:
    greeting = f"Hi {name.split()[0]}," if name.strip() else "Hi,"
    return f"""
    <div style="font-family:Arial,Helvetica,sans-serif;max-width:520px;margin:0 auto;padding:24px;color:#1a1a1a">
      <p style="font-size:14px;color:#555;margin:0 0 8px">BetterCricket</p>
      <h1 style="font-size:22px;margin:0 0 16px">The demo is today</h1>
      <p style="font-size:15px;line-height:1.6;margin:0 0 16px">{greeting}</p>
      <p style="font-size:15px;line-height:1.6;margin:0 0 20px">
        A quick reminder that the BetterCricket live demo and Q&amp;A starts in a
        few hours. Nothing to install &mdash; the link below opens it in your browser.
      </p>
      <table role="presentation" style="font-size:15px;line-height:1.6;margin:0 0 24px">
        <tr><td style="padding:2px 12px 2px 0;color:#555">Starts</td><td><strong>5:30pm AWST</strong> (Perth)</td></tr>
        <tr><td style="padding:2px 12px 2px 0;color:#555"></td><td><strong>7:30pm AEST</strong> (Sydney, Melbourne, Brisbane)</td></tr>
      </table>
      <p style="margin:0 0 24px">
        <a href="{watch_url}" style="display:inline-block;background:#0f172a;color:#fff;text-decoration:none;padding:12px 22px;border-radius:8px;font-weight:bold;font-size:15px">Watch the demo</a>
      </p>
      <p style="font-size:14px;line-height:1.6;color:#555;margin:0 0 24px">
        Can't make it? You don't need to do anything &mdash; we'll email you the
        full recording afterwards.
      </p>
      <p style="font-size:12px;color:#888;line-height:1.5;margin:0">
        You're getting this because you registered at {settings.public_base_url}/demo.
        Reply to this email if you have any questions.
      </p>
    </div>
    """


def _reminder_text(*, name: str, event: WebinarEvent, watch_url: str) -> str:
    greeting = f"Hi {name.split()[0]}," if name.strip() else "Hi,"
    return (
        f"{greeting}\n\n"
        "A quick reminder that the BetterCricket live demo and Q&A starts in a "
        "few hours.\n\n"
        "Starts: 5:30pm AWST (Perth) / 7:30pm AEST (Sydney, Melbourne, Brisbane)\n"
        f"Watch here: {watch_url}\n\n"
        "Can't make it? You don't need to do anything - we'll email you the full "
        "recording afterwards.\n"
    )


# ----------------------------------------------------------------------
# StreamYard: one form, two lists.
#
# A registrant fills OUR form and nothing else. Their details are pushed into
# StreamYard's own registrant list afterwards, so the broadcast's attendee
# report and its own reminders still know who is coming — and so StreamYard's
# registration gate can be switched off, which is the half that actually
# removes the second form (see services/streamyard.py for what was tried and
# why nothing else works).
#
# BEST-EFFORT AT EVERY STEP. A registration is complete once our own row is
# written; the page has already handed the viewing link over by then. So this
# never raises, never blocks, and records its outcome on the row rather than
# only in a log.
# ----------------------------------------------------------------------

async def push_to_streamyard(
    db: AsyncSession,
    *,
    registration_id: str,
    name: str,
    email: str,
    phone: Optional[str] = None,
    event: WebinarEvent = EVENT,
) -> dict:
    """Push one registration into StreamYard and stamp what happened.

    Skipped outright for a row already pushed — their API is idempotent on the
    email, but it also does NOT overwrite, so re-pushing a corrected name would
    cost a request and change nothing.
    """
    from app.services import streamyard

    already = (await db.execute(text(
        "SELECT streamyard_id FROM webinar_registrations WHERE id = CAST(:id AS uuid)"
    ), {"id": registration_id})).scalar_one_or_none()
    if already:
        return {"ok": True, "id": already, "skipped": "already pushed"}

    result = await streamyard.push_registration(
        watch_url=event.watch_url, name=name, email=email, phone=phone)
    # A skip is not a failure and must not read as one on the staff list — it
    # is recorded as the plain reason there was nothing to do.
    note = result.get("error") or result.get("skipped")
    try:
        await db.execute(text("""
            UPDATE webinar_registrations
               SET streamyard_id = :sid, streamyard_error = :note, updated_at = NOW()
             WHERE id = CAST(:id AS uuid)
        """), {"id": registration_id, "sid": result.get("id"),
               "note": _clip(note, 500)})
        await db.commit()
    except Exception:
        logger.exception("webinar: could not record the StreamYard outcome for %s", email)
        await db.rollback()
    return result


async def sync_streamyard(
    db: AsyncSession,
    *,
    event: WebinarEvent = EVENT,
    limit: int = 200,
) -> dict:
    """Push every registrant StreamYard does not have yet.

    THE CATCH-UP, not the mechanism — `public_webinar.register` pushes each one
    as it arrives. This is what covers the registrations taken before the push
    existed, and a push that failed on a wobble at their end.

    A row that has already been SKIPPED for a reason that will not change (no
    surname to send) is retried anyway: it costs one request, and the reason
    can stop being true if somebody corrects their name.
    """
    rows = (await db.execute(text("""
        SELECT id, name, email, phone
          FROM webinar_registrations
         WHERE event_key = :k AND streamyard_id IS NULL
         ORDER BY created_at
         LIMIT :limit
    """), {"k": event.key, "limit": limit})).mappings().all()

    pushed = failed = skipped = 0
    for row in rows:
        result = await push_to_streamyard(
            db, registration_id=str(row["id"]), name=row["name"] or "",
            email=row["email"] or "", phone=row["phone"], event=event)
        if result.get("ok"):
            pushed += 1
        elif result.get("skipped"):
            skipped += 1
        else:
            failed += 1
    if rows:
        logger.info("webinar: StreamYard sync — %s pushed, %s skipped, %s failed",
                    pushed, skipped, failed)
    return {"considered": len(rows), "pushed": pushed,
            "skipped": skipped, "failed": failed}
