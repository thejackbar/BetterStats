"""The notification engine — one rule for who is told what, on which channel.

Everything that decides whether a person hears about something lives in
``channel_allowed`` below. Six conditions, in one place, so the settings screen,
the email digest and the in-app bell can never disagree about whether a club is
subscribed to something:

  1. the club's master switch is on,
  2. the channel's own club-level switch is on,
  3. the event is enabled for the club, and enabled on that channel,
  4. the club holds the module the event belongs to (core events have none),
  5. the person can act on it — an event with a capability only reaches the
     people who hold it, the rule the notification bell already applies,
  6. the person has not opted out, of that event or of the club entirely.

Plus, for email only, that we actually have an address for them.

**RESOLUTION IS DEFAULTS-THEN-OVERRIDES, and the defaults are the registry's.**
A club that has never opened the settings screen has no rows at all here, and
behaves exactly as ``notification_events`` declares. That is what lets a default
be changed in code without a backfill, and it is why every read below starts
from ``EventType`` and layers the club's stored row on top rather than the other
way round.

**EMIT IS IDEMPOTENT, AND THE DATABASE IS WHAT MAKES IT SO.** The unique index
on ``(organisation_id, dedupe_key)`` is the guard, not a read-then-write check —
a manual scan racing the nightly one would slip straight through the latter. A
second emit of the same fact returns None and touches nothing, so a source is
free to re-report everything it can see on every run and let the insert decide
what is new.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import membership_has_capability
from app.auth.modules import org_entitled_modules
from app.services import notification_events as ev

logger = logging.getLogger(__name__)

#: Platform defaults for a club with no ``club_notification_settings`` row.
DEFAULT_CLUB_SETTINGS = {
    "enabled": True,
    "email_enabled": True,
    "in_app_enabled": True,
    "email_frequency": "daily",
    "email_weekday": 0,
}

EMAIL_FREQUENCIES = ("daily", "weekly")


# ─── Club-level settings ─────────────────────────────────────────────────────

async def club_settings(session: AsyncSession, org_id) -> dict:
    """The club's master switches, defaults applied. Never returns None — an
    absent row is the default, not a missing configuration."""
    row = (await session.execute(text("""
        SELECT enabled, email_enabled, in_app_enabled, email_frequency, email_weekday
        FROM club_notification_settings WHERE organisation_id = :org
    """), {"org": str(org_id)})).mappings().first()
    if row is None:
        return dict(DEFAULT_CLUB_SETTINGS)
    out = dict(DEFAULT_CLUB_SETTINGS)
    out.update({k: row[k] for k in out if k in row})
    return out


async def save_club_settings(session: AsyncSession, org_id, patch: dict, *, user_id=None) -> dict:
    """Upsert the club's switches. Only a key PRESENT in ``patch`` is written,
    so a screen saving one toggle cannot blank the rest."""
    current = await club_settings(session, org_id)
    merged = dict(current)
    for key in DEFAULT_CLUB_SETTINGS:
        if key in patch and patch[key] is not None:
            merged[key] = patch[key]
    if merged["email_frequency"] not in EMAIL_FREQUENCIES:
        merged["email_frequency"] = DEFAULT_CLUB_SETTINGS["email_frequency"]
    merged["email_weekday"] = max(0, min(6, int(merged["email_weekday"] or 0)))
    await session.execute(text("""
        INSERT INTO club_notification_settings
            (organisation_id, enabled, email_enabled, in_app_enabled,
             email_frequency, email_weekday, updated_at, updated_by_user_id)
        VALUES (:org, :enabled, :email_enabled, :in_app_enabled,
                :email_frequency, :email_weekday, NOW(), :user_id)
        ON CONFLICT (organisation_id) DO UPDATE SET
            enabled = EXCLUDED.enabled,
            email_enabled = EXCLUDED.email_enabled,
            in_app_enabled = EXCLUDED.in_app_enabled,
            email_frequency = EXCLUDED.email_frequency,
            email_weekday = EXCLUDED.email_weekday,
            updated_at = NOW(),
            updated_by_user_id = EXCLUDED.updated_by_user_id
    """), {"org": str(org_id), "user_id": str(user_id) if user_id else None, **merged})
    return merged


# ─── Per-event rules ─────────────────────────────────────────────────────────

async def club_rules(session: AsyncSession, org_id) -> dict[str, dict]:
    """Every event the platform knows about, resolved for this club.

    Keyed by event key, each value ``{enabled, channels, config}`` with the
    registry's defaults underneath the club's own row. Events the club has no
    row for are still present — this is the whole catalogue, resolved, which is
    what the settings screen draws and what the scan reads.
    """
    rows = (await session.execute(text("""
        SELECT event_key, enabled, channels, config
        FROM club_notification_rules WHERE organisation_id = :org
    """), {"org": str(org_id)})).mappings().all()
    stored = {r["event_key"]: r for r in rows}

    out: dict[str, dict] = {}
    for event in ev.EVENT_TYPES:
        row = stored.get(event.key)
        channels = dict(event.default_channels)
        config = event.default_config()
        enabled = event.default_enabled
        if row is not None:
            enabled = bool(row["enabled"])
            channels.update(ev.clean_channels(row["channels"]))
            config = ev.clean_config(event, row["config"])
        out[event.key] = {"enabled": enabled, "channels": channels, "config": config}
    return out


async def save_rule(session: AsyncSession, org_id, event_key: str, *,
                    enabled: Optional[bool] = None,
                    channels: Optional[dict] = None,
                    config: Optional[dict] = None) -> dict:
    """Upsert one event's rule, merged over what the club already has.

    Merged rather than replaced for the same reason as the club switches: the
    screen saves one control at a time, and a partial payload must not reset the
    rest of the row to the registry default.
    """
    event = ev.get_event(event_key)
    if event is None:
        raise ValueError(f"unknown notification event: {event_key}")
    resolved = (await club_rules(session, org_id))[event_key]

    new_enabled = resolved["enabled"] if enabled is None else bool(enabled)
    new_channels = dict(resolved["channels"])
    new_channels.update(ev.clean_channels(channels))
    # The club's current config is the FALLBACK, so an unreadable value typed
    # into a field leaves what they had set alone rather than resetting it to
    # the platform default.
    new_config = ev.clean_config(event, config or {}, base=resolved["config"])

    await session.execute(text("""
        INSERT INTO club_notification_rules
            (organisation_id, event_key, enabled, channels, config, updated_at)
        VALUES (:org, :event, :enabled, CAST(:channels AS jsonb), CAST(:config AS jsonb), NOW())
        ON CONFLICT (organisation_id, event_key) DO UPDATE SET
            enabled = EXCLUDED.enabled,
            channels = EXCLUDED.channels,
            config = EXCLUDED.config,
            updated_at = NOW()
    """), {
        "org": str(org_id), "event": event_key, "enabled": new_enabled,
        "channels": _json(new_channels), "config": _json(new_config),
    })
    return {"enabled": new_enabled, "channels": new_channels, "config": new_config}


# ─── Per-user preferences ────────────────────────────────────────────────────

async def user_preferences(session: AsyncSession, user_id, org_id) -> dict[str, dict]:
    """One person's opt-outs at one club, keyed by event key.

    ``ALL_EVENTS`` may be among them — that is the whole-club opt-out, and it is
    read as a floor under every event rather than as an event of its own.
    """
    rows = (await session.execute(text("""
        SELECT event_key, channels FROM user_notification_preferences
        WHERE user_id = :uid AND organisation_id = :org
    """), {"uid": str(user_id), "org": str(org_id)})).mappings().all()
    return {r["event_key"]: ev.clean_channels(r["channels"]) for r in rows}


async def save_user_preference(session: AsyncSession, user_id, org_id, event_key: str,
                               channels: dict) -> dict:
    """Set one person's channel choices for one event (or ``ALL_EVENTS``)."""
    if event_key != ev.ALL_EVENTS and ev.get_event(event_key) is None:
        raise ValueError(f"unknown notification event: {event_key}")
    existing = (await user_preferences(session, user_id, org_id)).get(event_key, {})
    merged = {**existing, **ev.clean_channels(channels)}
    await session.execute(text("""
        INSERT INTO user_notification_preferences
            (user_id, organisation_id, event_key, channels, updated_at)
        VALUES (:uid, :org, :event, CAST(:channels AS jsonb), NOW())
        ON CONFLICT (user_id, organisation_id, event_key) DO UPDATE SET
            channels = EXCLUDED.channels, updated_at = NOW()
    """), {"uid": str(user_id), "org": str(org_id), "event": event_key,
           "channels": _json(merged)})
    return merged


# ─── The one rule ────────────────────────────────────────────────────────────

def event_available(event: ev.EventType, entitled_modules: Iterable[str]) -> bool:
    """Whether the club can receive this event at all. A module the club does
    not hold means the event is neither emitted nor offered on the settings
    screen — a club should never configure something it can never be sent."""
    return event.module is None or event.module in set(entitled_modules or ())


def channel_allowed(event: ev.EventType, channel: str, *, settings: dict, rule: dict,
                    prefs: dict) -> bool:
    """Does this channel carry this event, for a person with these preferences?

    The whole subscription decision, minus the two things that need the
    database: the module gate (``event_available``) and the recipient's
    capability (``recipients_for``).
    """
    if not settings.get("enabled", True):
        return False
    if channel == ev.CHANNEL_EMAIL and not settings.get("email_enabled", True):
        return False
    if channel == ev.CHANNEL_IN_APP and not settings.get("in_app_enabled", True):
        return False
    if not rule.get("enabled", True):
        return False
    if not rule.get("channels", {}).get(channel, False):
        return False
    # A person's opt-out beats the club's setting, always and in one direction
    # only: it can silence a channel the club has switched on, never switch on
    # one the club has switched off.
    blanket = prefs.get(ev.ALL_EVENTS, {})
    if blanket.get(channel) is False:
        return False
    if prefs.get(event.key, {}).get(channel) is False:
        return False
    return True


async def recipients_for(session: AsyncSession, org_id, event: ev.EventType) -> list[dict]:
    """The people at this club who should hear about this event.

    **``club_admin`` AND ``club_member``, and the second half is deliberate.** A
    club_member is somebody the club has given admin-app access to with an
    explicit capability allowlist — the volunteer coordinator who holds
    MANAGE_QUALIFICATIONS is exactly who should be told a Working With Children
    check is lapsing, and the notification bell has always shown them their
    sections. Restricting this to club_admin (which is what
    ``admin_contact_list.admin_rows`` correctly does, since that list answers a
    different question — who ADMINISTERS a club, for BetterCricket's own
    outreach) would send a club's compliance warnings past the person whose job
    it is.

    **A super_admin or sales membership is excluded**: that is BetterCricket's
    own staff, and staff acting as a club must not be emailed that club's
    milestones.

    Where the event names a capability, only the people who hold it are
    included, so a queue nobody can act on reaches nobody.
    """
    rows = (await session.execute(text("""
        SELECT u.id AS user_id, u.email, u.display_name, u.first_name, u.last_name,
               cm.role, cm.capabilities
        FROM club_memberships cm
        JOIN users u ON u.id = cm.user_id
        WHERE cm.club_id = :org AND cm.role IN ('club_admin', 'club_member')
        ORDER BY cm.is_primary_admin DESC
    """), {"org": str(org_id)})).mappings().all()

    out = []
    for r in rows:
        if event.capability and not membership_has_capability(
                r["role"], r["capabilities"], event.capability):
            continue
        out.append({
            "user_id": r["user_id"],
            "email": (r["email"] or "").strip() or None,
            "name": _person_name(r),
        })
    return out


def _person_name(row) -> Optional[str]:
    name = (row["display_name"] or "").strip()
    if name:
        return name
    joined = " ".join(p for p in ((row["first_name"] or ""), (row["last_name"] or "")) if p.strip()).strip()
    return joined or None


# ─── Emitting ────────────────────────────────────────────────────────────────

async def emit(session: AsyncSession, org_id, *, event_key: str, dedupe_key: str,
               title: str, body: str = "", link: Optional[str] = None,
               payload: Optional[dict] = None,
               occurred_at: Optional[datetime] = None,
               settings: Optional[dict] = None,
               rules: Optional[dict] = None,
               entitled_modules: Optional[Iterable[str]] = None,
               prefs_by_user: Optional[dict] = None,
               recipients: Optional[list[dict]] = None) -> Optional[str]:
    """Record one thing that happened, and queue it to everybody who should hear.

    Returns the notification's id, or None when there is nothing to do — the
    fact was already recorded, the club has the event switched off, or nobody is
    eligible to receive it.

    Every caller is free to re-report everything it can see: the unique index on
    the dedupe key is what decides what is genuinely new. The optional
    ``settings``/``rules``/``recipients``/``prefs_by_user`` arguments let a scan
    resolve the club's configuration and audience ONCE and reuse them across
    hundreds of emits. That is not a micro-optimisation: without it a club with
    forty milestones re-reads the same membership list and the same handful of
    preference rows forty times, and the scan's cost grows with the club's
    history rather than with its admin list.
    """
    event = ev.get_event(event_key)
    if event is None:
        logger.warning("notifications: unknown event %s ignored", event_key)
        return None

    if settings is None:
        settings = await club_settings(session, org_id)
    if not settings.get("enabled", True):
        return None
    if rules is None:
        rules = await club_rules(session, org_id)
    rule = rules.get(event_key, {})
    if not rule.get("enabled", True):
        return None

    # The insert IS the dedupe. RETURNING is empty when the row already existed,
    # which is how a second run of the same scan costs one statement and stops.
    row = (await session.execute(text("""
        INSERT INTO notifications
            (organisation_id, event_key, dedupe_key, severity, title, body, link,
             payload, occurred_at)
        VALUES (:org, :event, :dedupe, :severity, :title, :body, :link,
                CAST(:payload AS jsonb), COALESCE(:occurred_at, NOW()))
        ON CONFLICT (organisation_id, dedupe_key) DO NOTHING
        RETURNING id
    """), {
        "org": str(org_id), "event": event_key, "dedupe": dedupe_key,
        "severity": event.severity, "title": title, "body": body or "",
        "link": link, "payload": _json(payload or {}),
        "occurred_at": occurred_at,
    })).first()
    if row is None:
        return None
    notification_id = str(row[0])

    people = recipients if recipients is not None else await recipients_for(session, org_id, event)
    if prefs_by_user is None:
        prefs_by_user = {}
        for p in people:
            prefs_by_user[str(p["user_id"])] = await user_preferences(session, p["user_id"], org_id)

    queued = 0
    for person in people:
        prefs = prefs_by_user.get(str(person["user_id"]), {})
        for channel in ev.CHANNELS:
            if not channel_allowed(event, channel, settings=settings, rule=rule, prefs=prefs):
                continue
            # No address, no email. Recorded as nothing rather than as a failed
            # send: there was never an attempt to retry.
            if channel == ev.CHANNEL_EMAIL and not person["email"]:
                continue
            await session.execute(text("""
                INSERT INTO notification_deliveries (notification_id, user_id, channel)
                VALUES (:nid, :uid, :channel)
                ON CONFLICT (notification_id, user_id, channel) DO NOTHING
            """), {"nid": notification_id, "uid": str(person["user_id"]), "channel": channel})
            queued += 1

    if queued == 0:
        logger.debug("notifications: %s recorded for %s with no eligible recipient",
                     event_key, org_id)
    return notification_id


# ─── Reading ─────────────────────────────────────────────────────────────────

async def feed(session: AsyncSession, user_id, org_id, *, limit: int = 30,
               unread_only: bool = False) -> list[dict]:
    """One person's in-app notifications at one club, newest first."""
    rows = (await session.execute(text(f"""
        SELECT n.id, n.event_key, n.severity, n.title, n.body, n.link, n.payload,
               n.occurred_at, n.created_at, d.read_at
        FROM notification_deliveries d
        JOIN notifications n ON n.id = d.notification_id
        WHERE d.user_id = :uid AND d.channel = :channel
          AND n.organisation_id = :org
          {"AND d.read_at IS NULL" if unread_only else ""}
        ORDER BY n.created_at DESC
        LIMIT :limit
    """), {"uid": str(user_id), "org": str(org_id),
           "channel": ev.CHANNEL_IN_APP, "limit": limit})).mappings().all()
    return [
        {
            "id": str(r["id"]),
            "event_key": r["event_key"],
            "severity": r["severity"],
            "title": r["title"],
            "body": r["body"],
            "link": r["link"],
            "payload": r["payload"] or {},
            "occurred_at": r["occurred_at"].isoformat() if r["occurred_at"] else None,
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "read": r["read_at"] is not None,
        }
        for r in rows
    ]


async def unread_count(session: AsyncSession, user_id, org_id) -> int:
    return (await session.scalar(text("""
        SELECT COUNT(*) FROM notification_deliveries d
        JOIN notifications n ON n.id = d.notification_id
        WHERE d.user_id = :uid AND d.channel = :channel
          AND n.organisation_id = :org AND d.read_at IS NULL
    """), {"uid": str(user_id), "org": str(org_id), "channel": ev.CHANNEL_IN_APP})) or 0


async def mark_read(session: AsyncSession, user_id, org_id,
                    notification_ids: Optional[list[str]] = None) -> int:
    """Mark this person's in-app rows read — the ones named, or all of them.

    Scoped to the caller's own deliveries AND to the club they are acting as, so
    an id off a browser can only ever reach a row that was already theirs.
    """
    params = {"uid": str(user_id), "org": str(org_id), "channel": ev.CHANNEL_IN_APP}
    clause = ""
    if notification_ids:
        clause = "AND d.notification_id = ANY(CAST(:ids AS uuid[]))"
        params["ids"] = [str(i) for i in notification_ids]
    result = await session.execute(text(f"""
        UPDATE notification_deliveries d SET read_at = NOW()
        FROM notifications n
        WHERE n.id = d.notification_id
          AND d.user_id = :uid AND d.channel = :channel
          AND n.organisation_id = :org AND d.read_at IS NULL
          {clause}
    """), params)
    return result.rowcount or 0


def _json(value) -> str:
    import json
    return json.dumps(value or {})


def now() -> datetime:
    return datetime.now(timezone.utc)
