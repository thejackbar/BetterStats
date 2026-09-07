"""Notification endpoints — lightweight count poll + full summary on modal open."""
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional

from app.auth.capabilities import (
    MANAGE_REPORTS, MANAGE_SETTINGS, membership_has_capability, PRIVILEGED_ROLES,
    require_cap,
)
from app.models.db import (
    ClubMembership, User, Organisation, Player, PlayerSyncRequest, SavedReport,
    SyncRun, Milestone, get_db,
)
from app.routers.auth import get_current_user, get_current_club
from app.services.aggregations import get_upcoming_milestones_for_org
from app.auth.modules import org_entitled_modules
from app.services import email_service
from app.services.session_safety import rollback_keeping
from app.services import notification_events as ev
from app.services import notification_scan
from app.services import notifications as notif
from app.services.merch import merch_alerts as get_merch_alerts
from app.services.assets import asset_alerts as get_asset_alerts, count_asset_alerts

logger = logging.getLogger(__name__)


async def _safe(db: AsyncSession, factory, default, *, what: str):
    """Run one notification sub-query in isolation. If it throws — a slow query
    tripping a statement timeout on a large club, a data edge case, a column an
    un-run migration is missing — log the traceback and roll the session back so
    the remaining sections (and the panel itself) still load, instead of a bare
    500 taking down the whole bell. Mirrors ``iq_team._safe``."""
    try:
        return await factory()
    except Exception:
        logger.exception("notifications: %s failed", what)
        try:
            await db.rollback()
        except Exception:
            pass
        return default


async def _get_user_role(db: AsyncSession, user_id) -> Optional[str]:
    """role lives on ClubMembership, not User — a user has exactly one
    membership row (uq_membership_one_per_user), so this is the whole-account
    role regardless of which club a super admin is currently acting as."""
    row = await db.execute(select(ClubMembership.role).where(ClubMembership.user_id == user_id))
    return row.scalar_one_or_none()


async def _user_can_manage_reports(db: AsyncSession, user_id, user_role: Optional[str], org_id) -> bool:
    # Takes plain ids, not ORM instances: a prior _safe() rollback may have
    # expired the User/Organisation rows, and re-reading them here would emit
    # SQL from a sync attribute access (greenlet error).
    row = await db.execute(
        select(ClubMembership)
        .where(ClubMembership.user_id == user_id, ClubMembership.club_id == org_id)
    )
    m = row.scalar_one_or_none()
    if not m:
        return user_role in PRIVILEGED_ROLES
    return membership_has_capability(m.role, m.capabilities, MANAGE_REPORTS)

router = APIRouter(prefix="/club-admin", tags=["notifications"])

_DEFAULT_WINDOW_DAYS = 14


def _window_start(last_seen: Optional[datetime]) -> datetime:
    if last_seen:
        return last_seen
    return datetime.now(timezone.utc) - timedelta(days=_DEFAULT_WINDOW_DAYS)


def _empty_count(last_seen_version: Optional[str]) -> dict:
    return {
        "unseen_count": 0,
        "failed_sync_count": 0,
        "pending_reports_count": 0,
        "merch_alert_count": 0,
        "alert_count": 0,
        "last_seen_version": last_seen_version,
    }


def _empty_summary(last_seen_version: Optional[str]) -> dict:
    return {
        "last_seen_at": None,
        "last_seen_version": last_seen_version,
        "unseen_count": 0,
        "failed_sync_count": 0,
        "sync_runs": [],
        "new_milestones": [],
        "upcoming_milestones": [],
        "pending_sync_requests": 0,
        "pending_reports_count": 0,
        "merch_alerts": {"low_stock": [], "expiring": [], "service_due": [], "total": 0},
        "alerts": [],
        "alert_count": 0,
    }


@router.get("/notifications/count")
async def get_notifications_count(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Cheap badge-count poll — called every 60 s by the bell icon.

    Wrapped in a top-level guard so the bell badge can never 500: on any
    unexpected failure it logs, rolls back, and returns a zero count. The
    per-section ``_safe()`` guards below cover the common case; this is the
    final backstop for the response assembly and anything they miss."""
    last_seen_version = current_user.last_seen_app_version
    try:
        return await _build_notifications_count(current_user, club, db)
    except Exception:
        logger.exception("notifications: count failed at top level")
        try:
            await db.rollback()
        except Exception:
            pass
        return _empty_count(last_seen_version)


async def _build_notifications_count(
    current_user: User,
    club: Organisation,
    db: AsyncSession,
):
    # Snapshot everything we read off the ORM instances up front, before any
    # query runs. _safe() rolls the session back on a section failure, which
    # EXPIRES these instances; reading an expired attribute afterwards emits SQL
    # from a sync attribute access (greenlet error) and turns one failing
    # section into a cascade through the rest of the body. Plain locals are
    # immune, so a single bad section now only zeroes itself out.
    org_id = club.id
    user_id = current_user.id
    user_role = await _get_user_role(db, user_id)
    last_seen = current_user.last_notification_seen_at
    last_seen_version = current_user.last_seen_app_version
    entitled_modules = org_entitled_modules(club)
    ws = _window_start(last_seen)
    cutoff_date = ws.date()

    sync_count = (await _safe(db, lambda: db.scalar(
        select(func.count(SyncRun.id))
        .where(SyncRun.org_id == org_id)
        .where(SyncRun.status.in_(["success", "error"]))
        .where(SyncRun.player_id.is_(None))
        .where(SyncRun.completed_at > ws)
    ), 0, what="count.sync")) or 0

    # Failed runs need separate counting so the bell can flag a red badge
    # rather than the default accent — sync errors are higher-urgency than
    # a milestone or pending merge request.
    failed_sync_count = (await _safe(db, lambda: db.scalar(
        select(func.count(SyncRun.id))
        .where(SyncRun.org_id == org_id)
        .where(SyncRun.status == "error")
        .where(SyncRun.player_id.is_(None))
        .where(SyncRun.completed_at > ws)
    ), 0, what="count.failed_sync")) or 0

    milestone_count = (await _safe(db, lambda: db.scalar(
        select(func.count(Milestone.id))
        .join(Player, Player.id == Milestone.player_id)
        .where(Player.organisation_id == org_id)
        .where(Milestone.achieved_at.isnot(None))
        .where(Milestone.achieved_at >= cutoff_date)
    ), 0, what="count.milestone")) or 0

    pending_count = (await _safe(db, lambda: db.scalar(
        select(func.count(PlayerSyncRequest.id))
        .where(PlayerSyncRequest.org_id == org_id)
        .where(PlayerSyncRequest.status == "pending")
    ), 0, what="count.pending")) or 0

    # Saved-report approval queue — only counted for users who can act on it.
    async def _pending_reports():
        if not await _user_can_manage_reports(db, user_id, user_role, org_id):
            return 0
        return (await db.scalar(
            select(func.count(SavedReport.id))
            .where(SavedReport.org_id == org_id)
            .where(SavedReport.visibility == "club")
            .where(SavedReport.status == "pending")
        )) or 0
    pending_reports_count = await _safe(db, _pending_reports, 0, what="count.pending_reports")

    # BetterMerch standing alerts (low stock / service due / expiring). Like the
    # pending-request counts above, this is current state, not "since last seen"
    # — a low-stock badge stands until the club restocks. Only for clubs holding
    # the module.
    async def _merch_count():
        if "merch" not in entitled_modules:
            return 0
        return (await get_merch_alerts(db, org_id))["total"]
    merch_alert_count = await _safe(db, _merch_count, 0, what="count.merch")

    # Assets due for service or replacement. CORE, with no module gate: since
    # migration 279 the club's register is one thing and it is not stock, so a
    # club without BetterMerch no longer has service dates that warn nobody.
    async def _asset_count():
        return await count_asset_alerts(db, org_id)
    asset_alert_count = await _safe(db, _asset_count, 0, what="count.assets")

    # The configurable notifications this club has actually subscribed to
    # (migration 288) — a stored record with its own read state, unlike the
    # live sections above, which are recomputed from source data every poll.
    alert_count = await _safe(
        db, lambda: notif.unread_count(db, user_id, org_id), 0, what="count.alerts")

    return {
        "unseen_count": (sync_count + milestone_count + pending_count + pending_reports_count
                         + merch_alert_count + asset_alert_count + alert_count),
        "alert_count": alert_count,
        "failed_sync_count": failed_sync_count,
        "pending_reports_count": pending_reports_count,
        "merch_alert_count": merch_alert_count,
        "asset_alert_count": asset_alert_count,
        "last_seen_version": last_seen_version,
    }


@router.get("/notifications/summary")
async def get_notifications_summary(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Full summary — fetched once when the notification modal opens.

    Same top-level guard as the count poll: the panel renders whatever it can
    via the per-section ``_safe()`` guards, and this backstop turns any
    remaining failure (response assembly, an un-run migration on this club,
    anything unforeseen) into a valid empty payload instead of the bare 500
    that surfaced as "Couldn't load notifications" in the bell."""
    last_seen_version = current_user.last_seen_app_version
    try:
        return await _build_notifications_summary(current_user, club, db)
    except Exception:
        logger.exception("notifications: summary failed at top level")
        try:
            await db.rollback()
        except Exception:
            pass
        return _empty_summary(last_seen_version)


async def _build_notifications_summary(
    current_user: User,
    club: Organisation,
    db: AsyncSession,
):
    # Snapshot scalar reads off the ORM instances before any query — see the
    # note in _build_notifications_count: a _safe() rollback expires them, and a
    # later expired read would cascade one failing section into the next and
    # into the response assembly.
    org_id = club.id
    user_id = current_user.id
    user_role = await _get_user_role(db, user_id)
    last_seen = current_user.last_notification_seen_at
    last_seen_version = current_user.last_seen_app_version
    entitled_modules = org_entitled_modules(club)
    ws = _window_start(last_seen)
    cutoff_date = ws.date()

    # Org-level sync runs (not per-player deep syncs). Serialised inside the
    # guard so a later section's rollback can't expire these ORM rows on us.
    async def _sync_runs():
        res = await db.execute(
            select(SyncRun)
            .where(SyncRun.org_id == org_id)
            .where(SyncRun.status.in_(["success", "error"]))
            .where(SyncRun.player_id.is_(None))
            .where(SyncRun.completed_at > ws)
            .order_by(SyncRun.completed_at.desc())
            .limit(5)
        )
        return [
            {
                "id": str(r.id),
                "kind": r.kind,
                "status": r.status,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "stats": r.stats or {},
                "error": r.error,
            }
            for r in res.scalars().all()
        ]
    sync_runs = await _safe(db, _sync_runs, [], what="summary.sync_runs")

    # Milestones achieved since window start
    async def _milestones():
        res = await db.execute(
            select(Milestone, Player)
            .join(Player, Player.id == Milestone.player_id)
            .where(Player.organisation_id == org_id)
            .where(Milestone.achieved_at.isnot(None))
            .where(Milestone.achieved_at >= cutoff_date)
            .order_by(Milestone.achieved_at.desc())
            .limit(10)
        )
        return [
            {
                "player_id": str(m.player_id),
                "player_name": p.display_name_override or p.name,
                "milestone_type": m.milestone_type,
                "milestone_value": m.milestone_value,
                "achieved_at": m.achieved_at.isoformat() if m.achieved_at else None,
                "detail": m.detail,
            }
            for m, p in res.all()
        ]
    new_milestones = await _safe(db, _milestones, [], what="summary.milestones")

    # Upcoming milestones (always fresh, top 5)
    upcoming = await _safe(
        db,
        lambda: get_upcoming_milestones_for_org(db, str(org_id), limit=10),
        [],
        what="summary.upcoming",
    )
    upcoming_top = upcoming[:5]

    # Pending sync requests count
    pending_count = (await _safe(db, lambda: db.scalar(
        select(func.count(PlayerSyncRequest.id))
        .where(PlayerSyncRequest.org_id == org_id)
        .where(PlayerSyncRequest.status == "pending")
    ), 0, what="summary.pending")) or 0

    # Pending saved-report approvals (admin-only)
    async def _pending_reports():
        if not await _user_can_manage_reports(db, user_id, user_role, org_id):
            return 0
        return (await db.scalar(
            select(func.count(SavedReport.id))
            .where(SavedReport.org_id == org_id)
            .where(SavedReport.visibility == "club")
            .where(SavedReport.status == "pending")
        )) or 0
    pending_reports_count = await _safe(db, _pending_reports, 0, what="summary.pending_reports")

    # BetterMerch alerts for clubs holding the module.
    _empty_merch = {"low_stock": [], "expiring": [], "service_due": [], "total": 0}

    async def _merch():
        if "merch" not in entitled_modules:
            return _empty_merch
        return await get_merch_alerts(db, org_id)
    merch = await _safe(db, _merch, _empty_merch, what="summary.merch")

    # Core, no module gate — see the count above.
    _empty_assets = {"service_due": [], "total": 0}

    async def _assets():
        return await get_asset_alerts(db, org_id)
    assets = await _safe(db, _assets, _empty_assets, what="summary.assets")

    alerts = await _safe(
        db, lambda: notif.feed(db, user_id, org_id, limit=20), [], what="summary.alerts")
    alert_count = sum(1 for a in alerts if not a.get("read"))

    unseen_count = (len(sync_runs) + len(new_milestones) + pending_count + pending_reports_count
                    + (merch.get("total", 0) if isinstance(merch, dict) else 0)
                    + (assets.get("total", 0) if isinstance(assets, dict) else 0)
                    + alert_count)
    failed_sync_count = sum(1 for r in sync_runs if r["status"] == "error")

    return {
        "last_seen_at": last_seen.isoformat() if last_seen else None,
        "last_seen_version": last_seen_version,
        "unseen_count": unseen_count,
        "failed_sync_count": failed_sync_count,
        "sync_runs": sync_runs,
        "new_milestones": new_milestones,
        "upcoming_milestones": upcoming_top,
        "pending_sync_requests": pending_count,
        "pending_reports_count": pending_reports_count,
        "merch_alerts": merch,
        "asset_alerts": assets,
        "alerts": alerts,
        "alert_count": alert_count,
    }


class SeenPayload(BaseModel):
    app_version: Optional[str] = None


@router.post("/notifications/seen")
async def mark_notifications_seen(
    payload: SeenPayload,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current_user.last_notification_seen_at = datetime.now(timezone.utc)
    if payload.app_version:
        current_user.last_seen_app_version = payload.app_version
    await db.commit()
    return {"ok": True}


# ─── Configurable notifications (migration 288) ──────────────────────────────
#
# The bell above is computed live from source data and always has been; these
# endpoints are the CONFIGURABLE half — the catalogue a club chooses from, the
# switches it sets, each admin's own opt-out, and the record of what was
# actually raised and read. They live in this router rather than one of their
# own so "notifications" is one place, and the bell can serve the stored feed
# alongside its live sections without a second fetch.

class ClubNotificationSettingsPatch(BaseModel):
    """Only a field PRESENT is written — see notifications.save_club_settings.
    A screen saving one toggle must not blank the rest of the row."""
    enabled: Optional[bool] = None
    email_enabled: Optional[bool] = None
    in_app_enabled: Optional[bool] = None
    email_frequency: Optional[str] = None
    email_weekday: Optional[int] = None


class EventRulePatch(BaseModel):
    enabled: Optional[bool] = None
    channels: Optional[dict] = None
    config: Optional[dict] = None


class UserPreferencePatch(BaseModel):
    channels: dict


class MarkReadPayload(BaseModel):
    #: Absent or empty means every unread notification for this person at this
    #: club — what "mark all read" sends.
    notification_ids: Optional[list[str]] = None


def _event_payload(event, rule: dict, entitled) -> dict:
    return {
        "key": event.key,
        "label": event.label,
        "description": event.description,
        "category": event.category,
        "severity": event.severity,
        "module": event.module,
        "capability": event.capability,
        "config_fields": [
            {
                "key": f.key, "label": f.label, "hint": f.hint, "default": f.default,
                "minimum": f.minimum, "maximum": f.maximum, "unit": f.unit,
            }
            for f in event.config_fields
        ],
        "enabled": rule["enabled"],
        "channels": rule["channels"],
        "config": rule["config"],
        "default_enabled": event.default_enabled,
        "default_channels": event.default_channels,
    }


@router.get("/notifications/settings")
async def get_notification_settings(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Everything the settings screen draws, in one fetch.

    The catalogue is filtered to what this club can actually receive — an event
    belonging to a module the club does not hold is neither listed nor
    configurable, because a club should never be asked to choose about
    something it can never be sent.
    """
    entitled = org_entitled_modules(club)
    rules = await notif.club_rules(db, club.id)
    prefs = await notif.user_preferences(db, current_user.id, club.id)
    user_role = await _get_user_role(db, current_user.id)
    membership = (await db.execute(
        select(ClubMembership).where(ClubMembership.user_id == current_user.id,
                                     ClubMembership.club_id == club.id)
    )).scalar_one_or_none()

    events = []
    for event in ev.EVENT_TYPES:
        if not notif.event_available(event, entitled):
            continue
        payload = _event_payload(event, rules[event.key], entitled)
        # Whether THIS person would be a recipient. An event gated on a
        # capability they do not hold is still listed (they may be configuring
        # it for the club) but is shown as not reaching them, rather than
        # offering a personal opt-out that would do nothing.
        payload["receives"] = (
            event.capability is None
            or (membership is not None
                and membership_has_capability(membership.role, membership.capabilities, event.capability))
            or user_role in PRIVILEGED_ROLES
        )
        payload["my_channels"] = prefs.get(event.key, {})
        events.append(payload)

    can_manage = (user_role in PRIVILEGED_ROLES) or (
        membership is not None
        and membership_has_capability(membership.role, membership.capabilities, MANAGE_SETTINGS))

    return {
        "club": await notif.club_settings(db, club.id),
        "can_manage_club_settings": can_manage,
        "categories": [{"key": k, "label": label} for k, label in ev.CATEGORIES],
        "channels": [{"key": c, "label": ev.CHANNEL_LABELS[c]} for c in ev.CHANNELS],
        "events": events,
        "my_blanket_optout": prefs.get(ev.ALL_EVENTS, {}),
        "my_email": (current_user.email or "").strip() or None,
        "email_provider_live": email_service.get_email_provider().name != "console",
    }


@router.patch("/notifications/settings",
              dependencies=[Depends(require_cap(MANAGE_SETTINGS))])
async def patch_notification_settings(
    payload: ClubNotificationSettingsPatch,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """The club's master switches. ``enabled: false`` is the kill switch — the
    scan skips the club entirely, so nothing is raised on any channel."""
    saved = await notif.save_club_settings(
        db, club.id, payload.model_dump(exclude_unset=True), user_id=current_user.id)
    await db.commit()
    return saved


@router.put("/notifications/settings/events/{event_key}",
            dependencies=[Depends(require_cap(MANAGE_SETTINGS))])
async def put_notification_rule(
    event_key: str,
    payload: EventRulePatch,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    event = ev.get_event(event_key)
    if event is None:
        raise HTTPException(404, "Unknown notification event")
    if not notif.event_available(event, org_entitled_modules(club)):
        # Refused rather than stored: a rule for an event this club can never
        # receive would read as configured and do nothing.
        raise HTTPException(402, "This club does not hold the module that event belongs to")
    saved = await notif.save_rule(
        db, club.id, event_key,
        enabled=payload.enabled, channels=payload.channels, config=payload.config)
    await db.commit()
    return saved


@router.put("/notifications/settings/preferences/{event_key}")
async def put_notification_preference(
    event_key: str,
    payload: UserPreferencePatch,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """One admin's own opt-out, at this club.

    Deliberately NOT gated on MANAGE_SETTINGS: choosing what lands in your own
    inbox is not a club-wide decision, and an admin who cannot edit the club's
    branding is still entitled to stop being emailed. It can only ever silence
    a channel, never switch on one the club has turned off — see
    notifications.channel_allowed.
    """
    try:
        saved = await notif.save_user_preference(
            db, current_user.id, club.id, event_key, payload.channels)
    except ValueError as e:
        raise HTTPException(404, str(e))
    await db.commit()
    return {"event_key": event_key, "channels": saved}


@router.get("/notifications/feed")
async def get_notification_feed(
    limit: int = 30,
    unread_only: bool = False,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    limit = max(1, min(100, limit))
    items = await notif.feed(db, current_user.id, club.id, limit=limit, unread_only=unread_only)
    return {"items": items, "unread": await notif.unread_count(db, current_user.id, club.id)}


@router.post("/notifications/feed/read")
async def mark_notification_feed_read(
    payload: MarkReadPayload,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    try:
        updated = await notif.mark_read(db, current_user.id, club.id, payload.notification_ids)
    except DBAPIError:
        # A malformed id off a browser is a bad request, not a 500. The cast is
        # what raises, so this catches it rather than validating the shape twice.
        # Rolled back through the shared helper: a bare rollback EXPIRES the
        # instances this request's own dependencies loaded, and the next plain
        # attribute read on one of them raises a greenlet error a long way from
        # here. See services/session_safety.py.
        await rollback_keeping(db, current_user, club)
        raise HTTPException(400, "Invalid notification id")
    await db.commit()
    return {"marked_read": updated, "unread": await notif.unread_count(db, current_user.id, club.id)}


@router.post("/notifications/settings/run-now",
             dependencies=[Depends(require_cap(MANAGE_SETTINGS))])
async def run_notification_scan_now(
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Run this club's scan on demand, so a club that has just set its
    notifications up can see them work rather than waiting for tomorrow.

    Safe to press repeatedly: the scan re-reports everything it can see and the
    dedupe key decides what is genuinely new, so a second press raises nothing.
    Email is NOT dispatched here — the digest is the daily job's to send, and a
    button that emailed every admin on each press would be a way to spam a club
    with one click.
    """
    result = await notification_scan.scan_org(db, club)
    await db.commit()
    return result
