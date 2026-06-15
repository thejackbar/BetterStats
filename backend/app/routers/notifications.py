"""Notification endpoints — lightweight count poll + full summary on modal open."""
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

    sync_count = await db.scalar(
        select(func.count(SyncRun.id))
        .where(SyncRun.org_id == club.id)
        .where(SyncRun.status.in_(["success", "error"]))
        .where(SyncRun.player_id.is_(None))
        .where(SyncRun.completed_at > ws)
    ) or 0

    # Failed runs need separate counting so the bell can flag a red badge
    # rather than the default accent — sync errors are higher-urgency than
    # a milestone or pending merge request.
    failed_sync_count = await db.scalar(
        select(func.count(SyncRun.id))
        .where(SyncRun.org_id == club.id)
        .where(SyncRun.status == "error")
        .where(SyncRun.player_id.is_(None))
        .where(SyncRun.completed_at > ws)
    ) or 0

    milestone_count = await db.scalar(
        select(func.count(Milestone.id))
        .join(Player, Player.id == Milestone.player_id)
        .where(Player.organisation_id == club.id)
        .where(Milestone.achieved_at.isnot(None))
        .where(Milestone.achieved_at >= cutoff_date)
    ) or 0

    pending_count = await db.scalar(
        select(func.count(PlayerSyncRequest.id))
        .where(PlayerSyncRequest.org_id == club.id)
        .where(PlayerSyncRequest.status == "pending")
    ) or 0

    # Saved-report approval queue — only counted for users who can act on it.
    pending_reports_count = 0
    if await _user_can_manage_reports(db, current_user, club):
        pending_reports_count = await db.scalar(
            select(func.count(SavedReport.id))
            .where(SavedReport.org_id == club.id)
            .where(SavedReport.visibility == "club")
            .where(SavedReport.status == "pending")
        ) or 0

    # BetterMerch standing alerts (low stock / service due / expiring). Like the
    # pending-request counts above, this is current state, not "since last seen"
    # — a low-stock badge stands until the club restocks. Only for clubs holding
    # the module.
    merch_alert_count = 0
    if org_has_module(club, "merch"):
        merch_alert_count = (await get_merch_alerts(db, club.id))["total"]

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

    # Org-level sync runs (not per-player deep syncs)
    sync_res = await db.execute(
        select(SyncRun)
        .where(SyncRun.org_id == club.id)
        .where(SyncRun.status.in_(["success", "error"]))
        .where(SyncRun.player_id.is_(None))
        .where(SyncRun.completed_at > ws)
        .order_by(SyncRun.completed_at.desc())
        .limit(5)
    )
    sync_runs = sync_res.scalars().all()

    # Milestones achieved since window start
    milestone_res = await db.execute(
        select(Milestone, Player)
        .join(Player, Player.id == Milestone.player_id)
        .where(Player.organisation_id == club.id)
        .where(Milestone.achieved_at.isnot(None))
        .where(Milestone.achieved_at >= cutoff_date)
        .order_by(Milestone.achieved_at.desc())
        .limit(10)
    )
    milestone_rows = milestone_res.all()

    # Upcoming milestones (always fresh, top 5)
    upcoming = await get_upcoming_milestones_for_org(db, str(club.id), limit=10)
    upcoming_top = upcoming[:5]

    # Pending sync requests count
    pending_count = await db.scalar(
        select(func.count(PlayerSyncRequest.id))
        .where(PlayerSyncRequest.org_id == club.id)
        .where(PlayerSyncRequest.status == "pending")
    ) or 0

    # Pending saved-report approvals (admin-only)
    pending_reports_count = 0
    if await _user_can_manage_reports(db, current_user, club):
        pending_reports_count = await db.scalar(
            select(func.count(SavedReport.id))
            .where(SavedReport.org_id == club.id)
            .where(SavedReport.visibility == "club")
            .where(SavedReport.status == "pending")
        ) or 0

    # BetterMerch alerts for clubs holding the module.
    merch = {"low_stock": [], "expiring": [], "service_due": [], "total": 0}
    if org_has_module(club, "merch"):
        merch = await get_merch_alerts(db, club.id)

    unseen_count = len(sync_runs) + len(milestone_rows) + pending_count + pending_reports_count + merch["total"]
    failed_sync_count = sum(1 for r in sync_runs if r.status == "error")

    return {
        "last_seen_at": last_seen.isoformat() if last_seen else None,
        "last_seen_version": current_user.last_seen_app_version,
        "unseen_count": unseen_count,
        "failed_sync_count": failed_sync_count,
        "sync_runs": [
            {
                "id": str(r.id),
                "kind": r.kind,
                "status": r.status,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "stats": r.stats or {},
                "error": r.error,
            }
            for r in sync_runs
        ],
        "new_milestones": [
            {
                "player_id": str(m.player_id),
                "player_name": p.display_name_override or p.name,
                "milestone_type": m.milestone_type,
                "milestone_value": m.milestone_value,
                "achieved_at": m.achieved_at.isoformat() if m.achieved_at else None,
                "detail": m.detail,
            }
            for m, p in milestone_rows
        ],
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
