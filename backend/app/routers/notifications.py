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
from app.auth.modules import org_has_module
from app.services.merch import merch_alerts as get_merch_alerts

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


async def _user_can_manage_reports(db: AsyncSession, user: User, club: Organisation) -> bool:
    row = await db.execute(
        select(ClubMembership)
        .where(ClubMembership.user_id == user.id, ClubMembership.club_id == club.id)
    )
    m = row.scalar_one_or_none()
    if not m:
        return user.role in PRIVILEGED_ROLES
    return membership_has_capability(m.role, m.capabilities, MANAGE_REPORTS)

router = APIRouter(prefix="/club-admin", tags=["notifications"])

_DEFAULT_WINDOW_DAYS = 14


def _window_start(last_seen: Optional[datetime]) -> datetime:
    if last_seen:
        return last_seen
    return datetime.now(timezone.utc) - timedelta(days=_DEFAULT_WINDOW_DAYS)


@router.get("/notifications/count")
async def get_notifications_count(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Cheap badge-count poll — called every 60 s by the bell icon."""
    last_seen = current_user.last_notification_seen_at
    ws = _window_start(last_seen)
    cutoff_date = ws.date()

    sync_count = (await _safe(db, lambda: db.scalar(
        select(func.count(SyncRun.id))
        .where(SyncRun.org_id == club.id)
        .where(SyncRun.status.in_(["success", "error"]))
        .where(SyncRun.player_id.is_(None))
        .where(SyncRun.completed_at > ws)
    ), 0, what="count.sync")) or 0

    # Failed runs need separate counting so the bell can flag a red badge
    # rather than the default accent — sync errors are higher-urgency than
    # a milestone or pending merge request.
    failed_sync_count = (await _safe(db, lambda: db.scalar(
        select(func.count(SyncRun.id))
        .where(SyncRun.org_id == club.id)
        .where(SyncRun.status == "error")
        .where(SyncRun.player_id.is_(None))
        .where(SyncRun.completed_at > ws)
    ), 0, what="count.failed_sync")) or 0

    milestone_count = (await _safe(db, lambda: db.scalar(
        select(func.count(Milestone.id))
        .join(Player, Player.id == Milestone.player_id)
        .where(Player.organisation_id == club.id)
        .where(Milestone.achieved_at.isnot(None))
        .where(Milestone.achieved_at >= cutoff_date)
    ), 0, what="count.milestone")) or 0

    pending_count = (await _safe(db, lambda: db.scalar(
        select(func.count(PlayerSyncRequest.id))
        .where(PlayerSyncRequest.org_id == club.id)
        .where(PlayerSyncRequest.status == "pending")
    ), 0, what="count.pending")) or 0

    # Saved-report approval queue — only counted for users who can act on it.
    async def _pending_reports():
        if not await _user_can_manage_reports(db, current_user, club):
            return 0
        return (await db.scalar(
            select(func.count(SavedReport.id))
            .where(SavedReport.org_id == club.id)
            .where(SavedReport.visibility == "club")
            .where(SavedReport.status == "pending")
        )) or 0
    pending_reports_count = await _safe(db, _pending_reports, 0, what="count.pending_reports")

    # BetterMerch standing alerts (low stock / service due / expiring). Like the
    # pending-request counts above, this is current state, not "since last seen"
    # — a low-stock badge stands until the club restocks. Only for clubs holding
    # the module.
    async def _merch_count():
        if not org_has_module(club, "merch"):
            return 0
        return (await get_merch_alerts(db, club.id))["total"]
    merch_alert_count = await _safe(db, _merch_count, 0, what="count.merch")

    return {
        "unseen_count": sync_count + milestone_count + pending_count + pending_reports_count + merch_alert_count,
        "failed_sync_count": failed_sync_count,
        "pending_reports_count": pending_reports_count,
        "merch_alert_count": merch_alert_count,
        "last_seen_version": current_user.last_seen_app_version,
    }


@router.get("/notifications/summary")
async def get_notifications_summary(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Full summary — fetched once when the notification modal opens."""
    last_seen = current_user.last_notification_seen_at
    ws = _window_start(last_seen)
    cutoff_date = ws.date()

    # Org-level sync runs (not per-player deep syncs). Serialised inside the
    # guard so a later section's rollback can't expire these ORM rows on us.
    async def _sync_runs():
        res = await db.execute(
            select(SyncRun)
            .where(SyncRun.org_id == club.id)
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
            .where(Player.organisation_id == club.id)
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
        lambda: get_upcoming_milestones_for_org(db, str(club.id), limit=10),
        [],
        what="summary.upcoming",
    )
    upcoming_top = upcoming[:5]

    # Pending sync requests count
    pending_count = (await _safe(db, lambda: db.scalar(
        select(func.count(PlayerSyncRequest.id))
        .where(PlayerSyncRequest.org_id == club.id)
        .where(PlayerSyncRequest.status == "pending")
    ), 0, what="summary.pending")) or 0

    # Pending saved-report approvals (admin-only)
    async def _pending_reports():
        if not await _user_can_manage_reports(db, current_user, club):
            return 0
        return (await db.scalar(
            select(func.count(SavedReport.id))
            .where(SavedReport.org_id == club.id)
            .where(SavedReport.visibility == "club")
            .where(SavedReport.status == "pending")
        )) or 0
    pending_reports_count = await _safe(db, _pending_reports, 0, what="summary.pending_reports")

    # BetterMerch alerts for clubs holding the module.
    _empty_merch = {"low_stock": [], "expiring": [], "service_due": [], "total": 0}

    async def _merch():
        if not org_has_module(club, "merch"):
            return _empty_merch
        return await get_merch_alerts(db, club.id)
    merch = await _safe(db, _merch, _empty_merch, what="summary.merch")

    unseen_count = len(sync_runs) + len(new_milestones) + pending_count + pending_reports_count + merch["total"]
    failed_sync_count = sum(1 for r in sync_runs if r["status"] == "error")

    return {
        "last_seen_at": last_seen.isoformat() if last_seen else None,
        "last_seen_version": current_user.last_seen_app_version,
        "unseen_count": unseen_count,
        "failed_sync_count": failed_sync_count,
        "sync_runs": sync_runs,
        "new_milestones": new_milestones,
        "upcoming_milestones": upcoming_top,
        "pending_sync_requests": pending_count,
        "pending_reports_count": pending_reports_count,
        "merch_alerts": merch,
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
