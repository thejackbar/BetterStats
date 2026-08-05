"""AFL club-admin surface: sync triggers, run history, basic settings, and
the super-admin club registration endpoint.

Auth is the SHARED stack (routers/auth.py) — same session cookie, same
club_memberships model, same "super admin acts as a club" behaviour.
"""
import asyncio
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import (
    Organisation, SyncRun, User, async_session_maker, get_db,
)
from app.routers.auth import get_current_club, get_current_user, require_super_admin
from app.services import theme_config as theme_config_service
from app.services.afl import sync as afl_sync

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/club-admin", tags=["afl-club-admin"])

# Keep strong references so detached sync tasks aren't garbage collected
# (same pattern as the cricket dossier builder).
_SYNC_TASKS: set = set()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _SYNC_TASKS.add(task)
    task.add_done_callback(_SYNC_TASKS.discard)


async def _has_running_sync(db: AsyncSession, org_id: uuid.UUID) -> bool:
    res = await db.execute(select(SyncRun.id).where(
        SyncRun.org_id == org_id, SyncRun.status == "running").limit(1))
    return res.first() is not None


async def _run_sync(org_id: uuid.UUID, run_id: uuid.UUID, full: bool) -> None:
    """Detached runner. The endpoint created the run row, so this owns
    finishing it (the sync engine's owns_run contract)."""
    stats = {}
    try:
        stats = await afl_sync.sync_organisation(org_id, run_id=run_id, full=full)
        await afl_sync.finish_sync_run(run_id, stats)
    except Exception as exc:  # noqa: BLE001
        logger.exception("AFL sync run %s failed", run_id)
        await afl_sync.finish_sync_run(run_id, stats, error=str(exc))


@router.post("/sync")
async def sync_now(club: Organisation = Depends(get_current_club),
                   user: User = Depends(get_current_user),
                   db: AsyncSession = Depends(get_db)):
    if await _has_running_sync(db, club.id):
        raise HTTPException(status_code=409, detail="A sync is already running")
    run_id = await afl_sync.start_sync_run(club.id, "afl_sync",
                                           triggered_by_user_id=user.id)
    _spawn(_run_sync(club.id, run_id, full=False))
    return {"status": "started", "run_id": str(run_id)}


@router.post("/full-rebuild")
async def full_rebuild(club: Organisation = Depends(get_current_club),
                       user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    """Wipe the club's synced game data and re-pull everything. Players are
    kept (their ids are stable derivations, so lines re-attach)."""
    if await _has_running_sync(db, club.id):
        raise HTTPException(status_code=409, detail="A sync is already running")
    run_id = await afl_sync.start_sync_run(club.id, "afl_full",
                                           triggered_by_user_id=user.id)

    async def _wipe_and_sync():
        try:
            async with async_session_maker() as session:
                # games cascade to afl_game_details / periods / lines / events
                await session.execute(text("""
                    DELETE FROM games g
                    USING grades gr, seasons s
                    WHERE g.grade_id = gr.id AND gr.season_id = s.id
                      AND s.organisation_id = :org
                """), {"org": str(club.id)})
                await session.execute(text(
                    "DELETE FROM afl_player_season_stats WHERE organisation_id = :org"),
                    {"org": str(club.id)})
                await session.commit()
            from app.services.afl import playhq_client
            playhq_client.clear_cache()
        except Exception as exc:  # noqa: BLE001
            await afl_sync.finish_sync_run(run_id, {}, error=f"wipe failed: {exc}")
            return
        await _run_sync(club.id, run_id, full=True)

    _spawn(_wipe_and_sync())
    return {"status": "started", "run_id": str(run_id)}


@router.get("/sync-runs")
async def sync_runs(club: Organisation = Depends(get_current_club),
                    db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(SyncRun).where(SyncRun.org_id == club.id)
                           .order_by(SyncRun.started_at.desc()).limit(20))
    return {"runs": [{
        "id": str(r.id), "kind": r.kind, "status": r.status,
        "started_at": r.started_at, "completed_at": r.completed_at,
        "stats": r.stats, "error": r.error,
    } for r in res.scalars()]}


class SettingsPatch(BaseModel):
    short_name: Optional[str] = None
    # theme_config is what actually themes the public site (the palette
    # frontend/src/lib/theme.js injects). primary_color/accent_color are the
    # legacy columns kept for history — writing them themes nothing, which is
    # the same trap cricket's setup wizard hit.
    theme_config: Optional[dict] = None
    primary_color: Optional[str] = None
    accent_color: Optional[str] = None
    theme_mode: Optional[str] = None
    player_name_format: Optional[str] = None
    is_active: Optional[bool] = None
    public_show_bog_leaderboard: Optional[bool] = None
    public_show_club_bf_leaderboard: Optional[bool] = None
    public_show_comp_bf_leaderboard: Optional[bool] = None


@router.get("/settings")
async def get_settings(club: Organisation = Depends(get_current_club)):
    return {
        "id": str(club.id), "name": club.name, "short_name": club.short_name,
        "slug": club.slug, "playhq_id": club.playhq_id,
        "primary_color": club.primary_color, "accent_color": club.accent_color,
        "theme_config": club.theme_config or {},
        "theme_mode": club.theme_mode, "is_active": club.is_active,
        "player_name_format": club.player_name_format,
        "logo_url": club.logo_url,
        "public_show_bog_leaderboard": club.public_show_bog_leaderboard,
        "public_show_club_bf_leaderboard": club.public_show_club_bf_leaderboard,
        "public_show_comp_bf_leaderboard": club.public_show_comp_bf_leaderboard,
    }


@router.patch("/settings")
async def patch_settings(patch: SettingsPatch,
                         club: Organisation = Depends(get_current_club),
                         db: AsyncSession = Depends(get_db)):
    data = patch.model_dump(exclude_unset=True)
    # These land in a <style> tag on the public site, so they go through the
    # same allowlist cricket's settings PATCH uses. An empty result clears
    # back to the BetterFootball defaults rather than storing {}.
    if "theme_config" in data:
        raw = data.pop("theme_config")
        clean = theme_config_service.sanitize_theme_config(raw or {})
        club.theme_config = clean or None
    for field, value in data.items():
        setattr(club, field, value)
    await db.commit()
    return {"status": "ok"}


class RegisterClubRequest(BaseModel):
    playhq_org_id: str
    sync_now: bool = True


@router.post("/register-club")
async def register_club(body: RegisterClubRequest,
                        user: User = Depends(require_super_admin),
                        db: AsyncSession = Depends(get_db)):
    """Super-admin: onboard a club by its PlayHQ org code (the hex code in a
    playhq.com/afl/org/... URL). Pass 2's public self-serve registration will
    reuse this path."""
    org = await afl_sync.register_organisation(db, body.playhq_org_id.strip())
    run_id = None
    if body.sync_now and not await _has_running_sync(db, org.id):
        run_id = await afl_sync.start_sync_run(org.id, "afl_full",
                                               triggered_by_user_id=user.id)
        _spawn(_run_sync(org.id, run_id, full=True))
    return {"organisation_id": str(org.id), "slug": org.slug, "name": org.name,
            "run_id": str(run_id) if run_id else None}
