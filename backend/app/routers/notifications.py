"""Notification endpoints — lightweight count poll + full summary on modal open."""
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional

from app.auth.capabilities import MANAGE_REPORTS, membership_has_capability, PRIVILEGED_ROLES
from app.models.db import (
    ClubMembership, User, Organisation, Player, PlayerSyncRequest, SavedReport,
    SyncRun, Milestone, get_db,
)
from app.routers.auth import get_current_user, get_current_club
from app.services.aggregations import get_upcoming_milestones_for_org
from app.auth.modules import org_entitled_modules
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

    return {
        "unseen_count": sync_count + milestone_count + pending_count + pending_reports_count + merch_alert_count + asset_alert_count,
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

    unseen_count = (len(sync_runs) + len(new_milestones) + pending_count + pending_reports_count
                    + (merch.get("total", 0) if isinstance(merch, dict) else 0)
                    + (assets.get("total", 0) if isinstance(assets, dict) else 0))
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
