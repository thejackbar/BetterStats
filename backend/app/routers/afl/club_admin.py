"""AFL club-admin surface: sync triggers, run history, basic settings, and
the super-admin club registration endpoint.

Auth is the SHARED stack (routers/auth.py) — same session cookie, same
club_memberships model, same "super admin acts as a club" behaviour.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import (
    Organisation, SyncRun, User, async_session_maker, get_db,
)
from app.auth.capabilities import MANAGE_SETTINGS, require_cap
from app.routers.auth import get_current_club, get_current_user, require_super_admin
from app.services import club_history, club_lock, fonts as font_service, theme_config as theme_config_service
from app.services.afl import grade_scope, sync as afl_sync

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


class LinkGradePreviewRequest(BaseModel):
    ref: str  # a pasted PlayHQ match link, or its bare short code


class LinkGradeRequest(BaseModel):
    season_id: uuid.UUID
    ref: str


@router.post("/link-grade/preview")
async def link_grade_preview(body: LinkGradePreviewRequest,
                             club: Organisation = Depends(get_current_club)):
    """Resolve a pasted PlayHQ match link into the grade it belongs to,
    without writing anything — lets the admin confirm it's the right game
    (and that one side is really this club) before committing to a sync.
    See services/afl/sync.py's "Manually linking a grade" note for why this
    exists: a team re-graded mid-season drops its OLD grade out of every
    future sync's discovery, and this is the way back in."""
    try:
        return await afl_sync.resolve_grade_from_game(club, body.ref)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/link-grade")
async def link_grade(body: LinkGradeRequest,
                     club: Organisation = Depends(get_current_club),
                     db: AsyncSession = Depends(get_db)):
    """Pull one whole grade in by resolving it from a pasted match link,
    then walking its fixture directly — bypassing discoverTeams, which is
    exactly the thing that can't see this grade any more. Synchronous (not
    backgrounded like Sync Now/Full Rebuild): it's scoped to a single grade,
    so it's fast enough to answer inline with a real result."""
    if await _has_running_sync(db, club.id):
        raise HTTPException(status_code=409, detail="A sync is already running")
    try:
        info = await afl_sync.resolve_grade_from_game(club, body.ref)
        result = await afl_sync.link_grade_manually(
            club.id, body.season_id, info["grade_id"], info["grade_name"])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return result


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
    # Club history, shown under the club name on the public dashboard. Both go
    # through services/club_history.py rather than straight onto the column —
    # previous_names is free-shaped JSON coming off a form, and a year typo
    # should read as "not recorded" rather than blocking the whole save.
    established_year: Optional[int] = None
    previous_names: Optional[list] = None
    competitions: Optional[list] = None
    public_show_bog_leaderboard: Optional[bool] = None
    public_show_club_bf_leaderboard: Optional[bool] = None
    public_show_comp_bf_leaderboard: Optional[bool] = None
    # BetterSocials' saved style: palette, fonts, saved designs and templates.
    # Cleaned by cricket's own sanitizer, so the two sports can never disagree
    # about what a saved design may hold.
    socials_style: Optional[dict] = None
    # Public-site typography: choosing between an uploaded file, a preset and
    # the app default. Cleaned by cricket's own sanitiser, never trusted raw.
    font_config: Optional[dict] = None
    # Draft mode: the public site behind a 4-digit PIN while it is being set up.
    password_protected: Optional[bool] = None
    access_pin: Optional[str] = None
    # Which grade categories count in the club's stats by default (NULL = all),
    # and whether a player's positions show on the public profile.
    stats_grade_categories: Optional[list] = None
    public_show_role: Optional[bool] = None


async def _club_categories(db: AsyncSession, org_id) -> list[dict]:
    """The categories this club actually fields, for the Settings checklist: a
    club with no colts grades is never offered a Colts box to untick."""
    from app.services.afl.grade_labels import CATEGORY_LABELS, GRADE_CATEGORIES
    rows = await db.execute(text("""
        SELECT gr.name, gr.category FROM grades gr
        JOIN seasons s ON s.id = gr.season_id WHERE s.organisation_id = :o
    """), {"o": str(org_id)})
    have = {grade_scope.category_of(r.name, r.category) for r in rows}
    return [{"key": c, "label": CATEGORY_LABELS[c]} for c in GRADE_CATEGORIES if c in have]


@router.get("/settings")
async def get_settings(club: Organisation = Depends(get_current_club),
                       db: AsyncSession = Depends(get_db)):
    return {
        "id": str(club.id), "name": club.name, "short_name": club.short_name,
        "slug": club.slug, "playhq_id": club.playhq_id,
        "primary_color": club.primary_color, "accent_color": club.accent_color,
        "theme_config": club.theme_config or {},
        "theme_mode": club.theme_mode, "is_active": club.is_active,
        "player_name_format": club.player_name_format,
        "logo_url": club.logo_url,
        "established_year": club.established_year,
        "previous_names": club_history.previous_names_for_display(club.previous_names),
        "competitions": club_history.competitions_for_display(club.competitions),
        "public_show_bog_leaderboard": club.public_show_bog_leaderboard,
        "public_show_club_bf_leaderboard": club.public_show_club_bf_leaderboard,
        "public_show_comp_bf_leaderboard": club.public_show_comp_bf_leaderboard,
        "socials_style": club.socials_style or None,
        "social_brand_kit": club.social_brand_kit or None,
        # font_config plus each uploaded role's URL, the same shape the public
        # club payload carries, so the preview and the site agree.
        **font_service.public_font_fields(club),
        "password_protected": bool(club.password_protected),
        "password_protect_reason": club.password_protect_reason,
        "has_pin": bool(club.access_pin_hash),
        "stats_grade_categories": grade_scope.clean_categories(club.stats_grade_categories),
        "grade_categories": await _club_categories(db, club.id),
        "public_show_role": bool(club.public_show_role),
    }


@router.patch("/settings")
async def patch_settings(patch: SettingsPatch,
                         current_user: User = Depends(require_cap(MANAGE_SETTINGS)),
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
    # An implausible year and an emptied list both store NULL, so "cleared"
    # and "never filled in" stay one state rather than two that mean the same.
    if "established_year" in data:
        club.established_year = club_history.clean_year(data.pop("established_year"))
    if "previous_names" in data:
        club.previous_names = club_history.clean_previous_names(data.pop("previous_names"))
    if "competitions" in data:
        club.competitions = club_history.clean_competitions(data.pop("competitions"))
    if "font_config" in data:
        from app.routers.club_admin import _sanitize_font_config
        raw = data.pop("font_config")
        club.font_config = (_sanitize_font_config(raw, club.font_config) or None) if isinstance(raw, dict) else None
    if "stats_grade_categories" in data:
        club.stats_grade_categories = grade_scope.clean_categories(data.pop("stats_grade_categories"))
    if "access_pin" in data:
        pin = (data.pop("access_pin") or "").strip()
        if not pin.isdigit() or len(pin) != 4:
            raise HTTPException(status_code=422, detail="PIN must be exactly 4 digits")
        club.access_pin_hash = club_lock.hash_pin(pin)
    if "password_protected" in data:
        on = bool(data.pop("password_protected"))
        if on:
            if not club.access_pin_hash:
                raise HTTPException(status_code=422, detail="Set a 4-digit PIN first")
            if not club.password_protected:
                club.password_protected_at = datetime.now(timezone.utc)
                club.password_protected_by = current_user.id
            club.password_protected = True
            club.password_protect_reason = "draft"
        elif club.password_protect_reason != "trial_ended":
            # A lock BetterFootball put on a lapsed trial is not the club's to lift.
            club.password_protected = False
            club.password_protect_reason = None
    if "socials_style" in data:
        from app.routers.club_admin import _sanitize_socials_style
        raw = data.pop("socials_style")
        club.socials_style = _sanitize_socials_style(raw) if isinstance(raw, dict) else None
    for field, value in data.items():
        setattr(club, field, value)
    await db.commit()
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Club logo
# ---------------------------------------------------------------------------
#
# Bytes go on the organisation row and are served by the shared images router,
# as cricket's are. The stored URL is API-relative ("images/..."), NOT cricket's
# "/api/images/...": the football app lives under /afl/, so an absolute /api
# path would reach the cricket backend and 404. The frontend resolves it against
# the bundle's own base (aflApi.mediaUrl), and a PlayHQ logo URL the sync wrote
# passes through untouched. Removing an upload clears the column, so the next
# sync fills the PlayHQ logo back in rather than leaving the club with none.

LOGO_ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
LOGO_MAX_BYTES = 8 * 1024 * 1024
_LOGO_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
              ".webp": "image/webp", ".gif": "image/gif"}


@router.post("/logo")
async def upload_logo(file: UploadFile = File(...),
                      current_user: User = Depends(require_cap(MANAGE_SETTINGS)),
                      club: Organisation = Depends(get_current_club),
                      db: AsyncSession = Depends(get_db)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in LOGO_ALLOWED_EXTS:
        raise HTTPException(400, "Image files only (jpg, png, webp, gif)")
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    if len(data) > LOGO_MAX_BYTES:
        raise HTTPException(400, "Logo must be 8 MB or smaller")
    club.logo_data = data
    club.logo_mime = _LOGO_MIME.get(ext, "image/png")
    # ?v= gets a replacement past the images router's long cache headers.
    club.logo_url = f"images/organisations/{club.id}/logo?v={uuid.uuid4().hex[:8]}"
    await db.commit()
    return {"logo_url": club.logo_url}


@router.delete("/logo")
async def delete_logo(current_user: User = Depends(require_cap(MANAGE_SETTINGS)),
                      club: Organisation = Depends(get_current_club),
                      db: AsyncSession = Depends(get_db)):
    club.logo_data = None
    club.logo_mime = None
    club.logo_url = None
    await db.commit()
    return {"status": "cleared"}


# ---------------------------------------------------------------------------
# Typography: a club's own font file per role. The upload and removal are
# cricket's own route bodies, so a football font is stored, measured and
# served exactly as a cricket one is.
# ---------------------------------------------------------------------------

@router.post("/font/{role}")
async def upload_font(role: str, file: UploadFile = File(...),
                      family: Optional[str] = Form(None),
                      current_user: User = Depends(require_cap(MANAGE_SETTINGS)),
                      club: Organisation = Depends(get_current_club),
                      db: AsyncSession = Depends(get_db)):
    from app.routers.club_admin import upload_font as _upload
    return await _upload(role, file=file, family=family, current_user=current_user, club=club, db=db)


@router.delete("/font/{role}")
async def delete_font(role: str,
                      current_user: User = Depends(require_cap(MANAGE_SETTINGS)),
                      club: Organisation = Depends(get_current_club),
                      db: AsyncSession = Depends(get_db)):
    from app.routers.club_admin import delete_font as _delete
    return await _delete(role, current_user=current_user, club=club, db=db)


# ---------------------------------------------------------------------------
# Primary admin: who owns the club account, and handing it over.
# ---------------------------------------------------------------------------

class PrimaryAdminBody(BaseModel):
    user_id: str


@router.get("/primary-admin")
async def get_primary_admin(current_user: User = Depends(get_current_user),
                            club: Organisation = Depends(get_current_club),
                            db: AsyncSession = Depends(get_db)):
    from app.routers.club_admin import get_primary_admin_info
    return await get_primary_admin_info(current_user=current_user, club=club, db=db)


@router.post("/primary-admin/transfer")
async def transfer_primary_admin(body: PrimaryAdminBody,
                                 current_user: User = Depends(get_current_user),
                                 club: Organisation = Depends(get_current_club),
                                 db: AsyncSession = Depends(get_db)):
    """The primary admin hands the role to another club admin. The same rule
    as cricket, through the same membership writer; cricket's version also
    queues its own outreach contact list, which football has no part in."""
    from app.models.db import ClubMembership
    from app.services.memberships import set_primary_admin
    m = (await db.execute(select(ClubMembership).where(ClubMembership.user_id == current_user.id))).scalar_one_or_none()
    is_super = bool(m and m.role == "super_admin")
    if not is_super and not (m and m.club_id == club.id and m.is_primary_admin):
        raise HTTPException(status_code=403, detail="Only the club's primary admin can transfer this")
    try:
        target = uuid.UUID(body.user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid user id")
    try:
        await set_primary_admin(db, club.id, target)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"ok": True}


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
