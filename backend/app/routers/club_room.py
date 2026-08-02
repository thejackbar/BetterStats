"""Club Room Mode — an auto-rotating, full-screen slideshow a club leaves
running on a TV in the club room. Core capability (MANAGE_CLUB_ROOM), not a
paid module: every club gets it, but individual slide TYPES that pull from a
bolt-on module (fixtures/lineups needs BetterSelect, recent social posts
needs BetterSocials) are silently skipped for a club that isn't entitled —
the editor UI hides the option before it's ever saved, this is the defensive
backstop for a club that downgrades after saving a playlist that used it.

Two moving parts:
- A saved **playlist** (`club_room_slides`): an ordered list of slide-type
  entries an admin configures once. Each entry EXPANDS into one or more
  rendered slides on read — e.g. one "sponsors" entry becomes one slide per
  sponsor, exactly like "add sponsors as individual slides" was asked for.
- A shared **media pool** (`club_room_media`) for admin-uploaded custom
  images (source='upload') and social-post exports saved from the
  BetterSocials composer (source='social_export', see
  POST /media/social-export — gated on BetterSocials' own capability, not
  this module's, since it's the composer saving into this shared pool).

GET /settings and GET /play are open to any logged-in club member (viewing
the configured playlist / running the show needs no special permission,
matching how e.g. the sponsors list is read-only-open); every write endpoint
requires MANAGE_CLUB_ROOM.
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_CLUB_ROOM, MANAGE_SOCIAL, require_cap
from app.auth.modules import org_has_module
from app.models.db import (
    ClubRoomMedia, ClubRoomSettings, ClubRoomSlide, Organisation, SavedReport, Sponsor, User, get_db,
)
from app.routers.auth import get_current_club, get_current_user

router = APIRouter(prefix="/club-admin/club-room", tags=["club-room"])

MEDIA_ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MEDIA_MAX_BYTES = 8 * 1024 * 1024
MEDIA_MAX_PER_CLUB = 120
SLIDE_TYPES = {
    "sponsors", "fixtures", "social_posts", "custom_images",
    "leaderboard", "records", "statlab_report",
}
STAT_TABLE_LIMIT = 12  # rows shown on a leaderboard/records/report slide
# Per-entry cap on how many individual slides one playlist row can expand
# into, so a misconfigured "show everything" entry can't produce a
# runaway-length loop.
EXPAND_CAP = 30

_IMAGE_MIME = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".gif": "image/gif",
}


async def _get_or_create_settings(db: AsyncSession, club: Organisation) -> ClubRoomSettings:
    row = await db.get(ClubRoomSettings, club.id)
    if row:
        return row
    row = ClubRoomSettings(organisation_id=club.id)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


def _settings_dict(s: ClubRoomSettings) -> dict:
    return {
        "enabled": s.enabled, "rotation_seconds": s.rotation_seconds,
        "theme": s.theme or "dark", "shuffle": bool(s.shuffle),
    }


def _slide_dict(s: ClubRoomSlide) -> dict:
    return {
        "id": str(s.id),
        "slide_type": s.slide_type,
        "title": s.title,
        "config": s.config or {},
        "duration_seconds": s.duration_seconds,
        "position": s.position,
        "enabled": s.enabled,
    }


async def _slide_or_404(db: AsyncSession, club: Organisation, slide_id: str) -> ClubRoomSlide:
    try:
        sid = uuid.UUID(slide_id)
    except (ValueError, AttributeError):
        raise HTTPException(404, "Not found")
    row = await db.get(ClubRoomSlide, sid)
    if not row or row.organisation_id != club.id:
        raise HTTPException(404, "Not found")
    return row


def _media_dict(m: ClubRoomMedia) -> dict:
    ts = int(m.created_at.timestamp()) if m.created_at else 0
    return {
        "id": str(m.id),
        "source": m.source,
        "caption": m.caption,
        "url": f"/api/images/club-room/{m.id}?v={ts}",
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


async def _save_media(db, club, current_user, data: bytes, mime: str, source: str, caption: str | None) -> ClubRoomMedia:
    media = ClubRoomMedia(
        organisation_id=club.id, source=source, caption=(caption or None),
        image_data=data, image_mime=mime, created_by=current_user.id,
    )
    db.add(media)
    await db.commit()
    await db.refresh(media)
    return media


# ─── Settings + playlist ──────────────────────────────────────────────────

@router.get("/settings")
async def get_settings(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    settings = await _get_or_create_settings(db, club)
    rows = await db.execute(
        select(ClubRoomSlide)
        .where(ClubRoomSlide.organisation_id == club.id)
        .order_by(ClubRoomSlide.position)
    )
    return {**_settings_dict(settings), "slides": [_slide_dict(s) for s in rows.scalars().all()]}


class SettingsPatch(BaseModel):
    enabled: Optional[bool] = None
    rotation_seconds: Optional[int] = None
    theme: Optional[str] = None
    shuffle: Optional[bool] = None


@router.patch("/settings")
async def patch_settings(
    data: SettingsPatch,
    current_user: User = Depends(require_cap(MANAGE_CLUB_ROOM)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    settings = await _get_or_create_settings(db, club)
    if data.enabled is not None:
        settings.enabled = data.enabled
    if data.rotation_seconds is not None:
        settings.rotation_seconds = max(3, min(300, data.rotation_seconds))
    if data.theme is not None and data.theme in ("dark", "light"):
        settings.theme = data.theme
    if data.shuffle is not None:
        settings.shuffle = data.shuffle
    await db.commit()
    return _settings_dict(settings)


class SlideCreate(BaseModel):
    slide_type: str
    title: Optional[str] = None
    config: dict = {}
    duration_seconds: Optional[int] = None


@router.post("/slides", status_code=201)
async def create_slide(
    data: SlideCreate,
    current_user: User = Depends(require_cap(MANAGE_CLUB_ROOM)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    if data.slide_type not in SLIDE_TYPES:
        raise HTTPException(422, "Unknown slide type")
    from sqlalchemy import func
    max_pos = await db.scalar(
        select(func.max(ClubRoomSlide.position)).where(ClubRoomSlide.organisation_id == club.id)
    )
    slide = ClubRoomSlide(
        organisation_id=club.id, slide_type=data.slide_type, title=(data.title or None),
        config=data.config or {}, duration_seconds=data.duration_seconds,
        position=(max_pos + 1) if max_pos is not None else 0,
    )
    db.add(slide)
    await db.commit()
    await db.refresh(slide)
    return _slide_dict(slide)


class SlidePatch(BaseModel):
    title: Optional[str] = None
    config: Optional[dict] = None
    duration_seconds: Optional[int] = None
    enabled: Optional[bool] = None


@router.patch("/slides/{slide_id}")
async def patch_slide(
    slide_id: str,
    data: SlidePatch,
    current_user: User = Depends(require_cap(MANAGE_CLUB_ROOM)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    slide = await _slide_or_404(db, club, slide_id)
    if data.title is not None:
        slide.title = data.title or None
    if data.config is not None:
        slide.config = data.config
    if data.duration_seconds is not None:
        slide.duration_seconds = data.duration_seconds or None
    if data.enabled is not None:
        slide.enabled = data.enabled
    await db.commit()
    return _slide_dict(slide)


@router.delete("/slides/{slide_id}")
async def delete_slide(
    slide_id: str,
    current_user: User = Depends(require_cap(MANAGE_CLUB_ROOM)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    slide = await _slide_or_404(db, club, slide_id)
    await db.delete(slide)
    await db.commit()
    return {"ok": True}


class SlideReorderItem(BaseModel):
    id: str
    position: int


@router.put("/slides/reorder")
async def reorder_slides(
    items: list[SlideReorderItem],
    current_user: User = Depends(require_cap(MANAGE_CLUB_ROOM)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    for item in items:
        try:
            sid = uuid.UUID(item.id)
        except (ValueError, AttributeError):
            continue
        slide = await db.get(ClubRoomSlide, sid)
        if slide and slide.organisation_id == club.id:
            slide.position = item.position
    await db.commit()
    return {"ok": True}


# ─── Media pool (custom uploads + saved social exports) ───────────────────

@router.get("/media")
async def list_media(
    source: Optional[str] = None,
    current_user: User = Depends(require_cap(MANAGE_CLUB_ROOM)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ClubRoomMedia).where(ClubRoomMedia.organisation_id == club.id)
    if source in ("upload", "social_export"):
        stmt = stmt.where(ClubRoomMedia.source == source)
    stmt = stmt.order_by(ClubRoomMedia.created_at.desc())
    rows = await db.execute(stmt)
    return [_media_dict(m) for m in rows.scalars().all()]


async def _check_media_quota(db, club):
    from sqlalchemy import func
    count = await db.scalar(
        select(func.count()).select_from(ClubRoomMedia).where(ClubRoomMedia.organisation_id == club.id)
    )
    if (count or 0) >= MEDIA_MAX_PER_CLUB:
        raise HTTPException(400, f"Club Room media is full ({MEDIA_MAX_PER_CLUB} images). Delete some first.")


@router.post("/media")
async def upload_media(
    file: UploadFile = File(...),
    caption: Optional[str] = Form(None),
    current_user: User = Depends(require_cap(MANAGE_CLUB_ROOM)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in MEDIA_ALLOWED_EXTS:
        raise HTTPException(400, "Image files only (jpg, png, webp, gif)")
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    if len(data) > MEDIA_MAX_BYTES:
        raise HTTPException(400, "Image must be 8 MB or smaller")
    await _check_media_quota(db, club)
    media = await _save_media(db, club, current_user, data, _IMAGE_MIME.get(ext, "image/jpeg"), "upload", caption)
    return _media_dict(media)


@router.post("/media/social-export")
async def save_social_export(
    file: UploadFile = File(...),
    caption: Optional[str] = Form(None),
    # Gated on BetterSocials' own capability, not Club Room's — this is the
    # composer saving into the shared Club Room pool, so a club admin who can
    # use the Post Designer but not Club Room Mode can still save one.
    current_user: User = Depends(require_cap(MANAGE_SOCIAL)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    if len(data) > MEDIA_MAX_BYTES:
        raise HTTPException(400, "Image must be 8 MB or smaller")
    await _check_media_quota(db, club)
    media = await _save_media(db, club, current_user, data, "image/png", "social_export", caption)
    return _media_dict(media)


@router.delete("/media/{media_id}")
async def delete_media(
    media_id: str,
    current_user: User = Depends(require_cap(MANAGE_CLUB_ROOM)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    try:
        mid = uuid.UUID(media_id)
    except (ValueError, AttributeError):
        raise HTTPException(404, "Not found")
    media = await db.get(ClubRoomMedia, mid)
    if not media or media.organisation_id != club.id:
        raise HTTPException(404, "Not found")
    await db.delete(media)
    await db.commit()
    return {"ok": True}


@router.get("/reports")
async def list_reports_for_picker(
    current_user: User = Depends(require_cap(MANAGE_CLUB_ROOM)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Approved saved StatLab reports for this club, for the "Custom StatLab
    Report" slide's picker — org-scoped via the session, so the frontend never
    needs to know its own org id (unlike the public StatLab page's endpoints)."""
    rows = await db.execute(
        select(SavedReport)
        .where(SavedReport.org_id == club.id, SavedReport.status == "approved")
        .order_by(SavedReport.title)
    )
    return [{"id": str(r.id), "title": r.title, "description": r.description} for r in rows.scalars().all()]


# ─── Play — resolves the saved playlist into a flat, ready-to-render list ──

def _sponsor_dict(s: Sponsor) -> dict:
    return {
        "type": "sponsor", "id": str(s.id), "title": s.name,
        "website_url": s.website_url,
        "logo_url": s.logo_url or f"/api/images/sponsors/{s.id}/logo",
    }


async def _expand_sponsors(db, club, entry: ClubRoomSlide) -> list[dict]:
    """Three modes (`config.mode`, default 'sequence'):
    - 'single'   — one specific sponsor (`config.sponsor_id`), for prominent
                   featuring — add this entry more than once to give a major
                   sponsor more airtime than the others.
    - 'sequence' — every sponsor with a logo, each its own rotating slide
                   (the original "add sponsors as individual slides" behaviour).
    - 'grid'     — every sponsor with a logo on ONE combined slide.
    """
    stmt = (
        select(Sponsor)
        .where(Sponsor.organisation_id == club.id)
        .order_by(Sponsor.display_order, Sponsor.created_at)
    )
    rows = (await db.execute(stmt)).scalars().all()
    displayable = [s for s in rows if s.logo_url or s.logo_data]
    cfg = entry.config or {}
    mode = cfg.get("mode", "sequence")

    if mode == "single":
        sid = cfg.get("sponsor_id")
        match = next((s for s in displayable if str(s.id) == sid), None)
        return [_sponsor_dict(match)] if match else []

    if mode == "grid":
        if not displayable:
            return []
        return [{
            "type": "sponsor_grid", "id": f"grid-{entry.id}", "title": entry.title or "Our Sponsors",
            "sponsors": [_sponsor_dict(s) for s in displayable[:EXPAND_CAP]],
        }]

    return [_sponsor_dict(s) for s in displayable[:EXPAND_CAP]]


async def _expand_fixtures(db, club, entry: ClubRoomSlide) -> list[dict]:
    if not org_has_module(club, "select"):
        return []
    from app.routers.selection import selection_overview
    data = await selection_overview(db=db, club=club)
    count = min((entry.config or {}).get("count", 3) or 3, EXPAND_CAP)
    out = []
    for f in (data.get("fixtures") or [])[:count]:
        lineup = [
            {"display_name": p["display_name"], "batting_order": p["batting_order"],
             "is_captain": p["is_captain"], "is_wicket_keeper": p["is_wicket_keeper"]}
            for p in (f.get("lineup") or [])
        ]
        out.append({
            "type": "fixture", "id": f["id"],
            "title": f.get("label") or (f"vs {f['opponent_name']}" if f.get("opponent_name") else "Upcoming fixture"),
            "opponent_name": f.get("opponent_name"), "team_name": f.get("team_name"),
            "grade_name": f.get("grade_name"), "played_on": f.get("played_on"),
            "start_time": f.get("start_time"), "venue": f.get("venue"),
            "home_away": f.get("home_away"), "round": f.get("round"),
            "lineup": lineup,
        })
    return out


def _media_slide(m: ClubRoomMedia, slide_type: str) -> dict:
    ts = int(m.created_at.timestamp()) if m.created_at else 0
    return {
        "type": slide_type, "id": str(m.id), "title": m.caption,
        "image_url": f"/api/images/club-room/{m.id}?v={ts}",
    }


async def _expand_media(db, club, entry: ClubRoomSlide, source: str, slide_type: str, default_count: int) -> list[dict]:
    """`config.media_ids` (explicit picks, in that order) wins when present —
    that's how an admin chooses specific social posts/images rather than
    always getting "whatever's most recent". Falls back to the most recent
    `config.count` (default `default_count`) items when no picks are made."""
    cfg = entry.config or {}
    ids = cfg.get("media_ids")
    if ids:
        try:
            uids = [uuid.UUID(x) for x in ids]
        except (ValueError, TypeError):
            return []
        rows = (await db.execute(
            select(ClubRoomMedia).where(
                ClubRoomMedia.organisation_id == club.id,
                ClubRoomMedia.source == source,
                ClubRoomMedia.id.in_(uids),
            )
        )).scalars().all()
        by_id = {str(m.id): m for m in rows}
        ordered = [by_id[i] for i in ids if i in by_id]
        return [_media_slide(m, slide_type) for m in ordered[:EXPAND_CAP]]

    count = min(cfg.get("count", default_count) or default_count, EXPAND_CAP)
    rows = (await db.execute(
        select(ClubRoomMedia)
        .where(ClubRoomMedia.organisation_id == club.id, ClubRoomMedia.source == source)
        .order_by(ClubRoomMedia.created_at.desc())
        .limit(count)
    )).scalars().all()
    return [_media_slide(m, slide_type) for m in rows]


# ─── Leaderboard / Records / StatLab report slides ─────────────────────────

_BATTING_SORTS = {"total_runs", "average", "strike_rate", "total_sixes", "total_fours", "ducks", "high_score", "fifties", "hundreds"}
_BOWLING_SORTS = {"total_wickets", "average", "economy", "best_figures_wickets", "total_maidens", "five_fors"}
_FIELDING_SORTS = {"total_catches_non_wk", "total_catches_wk", "total_run_outs", "total_stumpings"}

_RECORD_CATEGORIES = {
    "batting.top_career_runs", "batting.top_high_scores", "batting.top_batting_avg",
    "batting.most_fifties", "batting.most_hundreds", "batting.most_ducks", "batting.most_runs_season",
    "bowling.top_career_wickets", "bowling.best_innings_figures", "bowling.top_bowling_avg",
    "bowling.top_economy", "bowling.most_five_fors", "bowling.most_wickets_season",
    "allrounders.top_allrounders",
}


async def _season_label(db, season_id: str | None) -> str:
    if not season_id:
        return "All-time"
    from app.models.db import Season
    try:
        s = await db.get(Season, uuid.UUID(season_id))
    except (ValueError, AttributeError):
        s = None
    return s.name if s else "All-time"


async def _expand_leaderboard(db, club, entry: ClubRoomSlide) -> list[dict]:
    from app.services.aggregations import (
        get_batting_leaderboard_extended, get_bowling_leaderboard_extended, get_fielding_leaderboard,
    )
    cfg = entry.config or {}
    stat_group = cfg.get("stat_group", "batting")
    season_id = cfg.get("season_id") or None
    limit = min(int(cfg.get("limit") or STAT_TABLE_LIMIT), 20)
    org_id = str(club.id)

    if stat_group == "bowling":
        sort_by = cfg.get("sort_by") if cfg.get("sort_by") in _BOWLING_SORTS else "total_wickets"
        rows = await get_bowling_leaderboard_extended(db, org_id, season_id, None, sort_by, limit)
    elif stat_group == "fielding":
        sort_by = cfg.get("sort_by") if cfg.get("sort_by") in _FIELDING_SORTS else "total_catches_non_wk"
        rows = await get_fielding_leaderboard(db, org_id, season_id, None, sort_by, limit)
    else:
        stat_group = "batting"
        sort_by = cfg.get("sort_by") if cfg.get("sort_by") in _BATTING_SORTS else "total_runs"
        rows = await get_batting_leaderboard_extended(db, org_id, season_id, None, sort_by, limit)

    if not rows:
        return []
    return [{
        "type": "leaderboard", "id": f"lb-{entry.id}",
        "title": entry.title or f"{stat_group.title()} Leaderboard",
        "stat_group": stat_group, "sort_by": sort_by,
        "season_label": await _season_label(db, season_id),
        "rows": rows,
    }]


def _dig(d: dict, path: str):
    cur = d
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


async def _expand_records(db, club, entry: ClubRoomSlide) -> list[dict]:
    from app.routers.records import get_records
    cfg = entry.config or {}
    category = cfg.get("category") if cfg.get("category") in _RECORD_CATEGORIES else "batting.top_career_runs"
    season_id = cfg.get("season_id") or None
    limit = min(int(cfg.get("limit") or 8), 15)

    # get_records is a FastAPI path function whose unfilled params default to
    # Query(...) sentinel objects, not real values — bypassing DI (as here)
    # means every one of them must be passed explicitly.
    data = await get_records(
        org_id=str(club.id), season_id=season_id, grade_id=None, grade_name=None,
        finals_only=False, captain_only=False, gender=None, db=db,
    )
    rows = (_dig(data, category) or [])[:limit]
    if not rows:
        return []
    label = category.split(".")[-1].replace("_", " ").title()
    return [{
        "type": "records", "id": f"rec-{entry.id}",
        "title": entry.title or label, "category": category,
        "season_label": await _season_label(db, season_id),
        "rows": rows,
    }]


async def _expand_statlab_report(db, club, entry: ClubRoomSlide) -> list[dict]:
    from app.routers.statlab import _serialise
    from app.services import statlab as svc

    cfg = entry.config or {}
    report_id = cfg.get("report_id")
    if not report_id:
        return []
    try:
        report = await db.get(SavedReport, uuid.UUID(report_id))
    except (ValueError, AttributeError):
        return []
    if not report or str(report.org_id) != str(club.id):
        return []  # deleted or moved since it was added to the playlist — skip quietly

    qj = report.query_json or {}
    limit = min(int(qj.get("limit") or STAT_TABLE_LIMIT), STAT_TABLE_LIMIT)
    try:
        if qj.get("derived"):
            result = await svc.run_derived(
                db, name=qj["derived"], org_id=str(club.id), limit=limit, page=1,
                context=qj.get("context") or {},
            )
        else:
            result = await svc.run_query(
                db, org_id=str(club.id), target=qj.get("target", "player_career"),
                sort_by=qj.get("sortBy", "runs"), sort_dir=qj.get("sortDir", "desc"),
                limit=limit, page=1, metric_filters=[], filter_tree=qj.get("filterTree"),
                context=qj.get("context") or {},
            )
    except Exception:  # noqa: BLE001 — a stale/invalid saved query must never break the show
        return []

    rows = _serialise(result.get("rows") or [])
    if not rows:
        return []
    return [{
        "type": "statlab_report", "id": f"report-{entry.id}",
        "title": entry.title or report.title, "rows": rows,
    }]


@router.get("/play")
async def play(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    settings = await _get_or_create_settings(db, club)
    rows = await db.execute(
        select(ClubRoomSlide)
        .where(ClubRoomSlide.organisation_id == club.id, ClubRoomSlide.enabled == True)  # noqa: E712
        .order_by(ClubRoomSlide.position)
    )
    entries = rows.scalars().all()

    slides: list[dict] = []
    for entry in entries:
        if entry.slide_type == "sponsors":
            expanded = await _expand_sponsors(db, club, entry)
        elif entry.slide_type == "fixtures":
            expanded = await _expand_fixtures(db, club, entry)
        elif entry.slide_type == "social_posts":
            if not org_has_module(club, "socials"):
                expanded = []
            else:
                expanded = await _expand_media(db, club, entry, "social_export", "social_post", 6)
        elif entry.slide_type == "custom_images":
            expanded = await _expand_media(db, club, entry, "upload", "custom_image", EXPAND_CAP)
        elif entry.slide_type == "leaderboard":
            expanded = await _expand_leaderboard(db, club, entry)
        elif entry.slide_type == "records":
            expanded = await _expand_records(db, club, entry)
        elif entry.slide_type == "statlab_report":
            expanded = await _expand_statlab_report(db, club, entry)
        else:
            expanded = []
        duration = entry.duration_seconds or settings.rotation_seconds
        for item in expanded:
            item["duration_seconds"] = duration
            item["playlist_title"] = entry.title
            slides.append(item)

    return {
        "enabled": settings.enabled,
        "rotation_seconds": settings.rotation_seconds,
        "theme": settings.theme or "dark",
        "shuffle": bool(settings.shuffle),
        "club_name": club.name,
        "club_short": club.short_name or (club.name or "")[:2].upper(),
        "logo_url": (f"/api/images/organisations/{club.id}/logo" if club.logo_data or club.logo_url else None),
        "slides": slides,
    }
