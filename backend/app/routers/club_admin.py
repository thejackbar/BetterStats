"""Admin API routes — all require authentication."""
import json as _json
import secrets as _secrets
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional
import uuid
import io
import csv
import re
from pathlib import Path

from app.models.db import (
    User, Organisation, ClubMembership, Player, Season, Grade, ManualPartnershipRecord,
    PlayerSyncRequest, Sponsor, ClubOnboardingRequest, OrgModuleSubscription,
    ModuleActionRequest, CommsLimitRequest, MarketingClub, SyncRun, OnboardingWizardState, get_db
)
from sqlalchemy import text as _text
from sqlalchemy.orm import selectinload, aliased as _orm_aliased
import asyncio
import logging as _logging
from app.routers.auth import get_current_user, get_current_club, require_super_admin, _hash_password
from app.auth.capabilities import (
    require_cap, effective_capabilities, ALL_CAPABILITIES,
    MANAGE_SETTINGS, MANAGE_MERGES, MANAGE_USERS, RUN_HARD_REFRESH, RUN_SYNC,
)
from app.auth.modules import (
    ALL_MODULES, MANAGED_MODULES, ALL_STATUSES, ALL_BILLING_CYCLES, org_entitled_modules,
    STATUS_TRIAL, org_default_trial_days,
    BILLABLE_MODULES, BILLABLE_MODULE_NAMES, billing_key_for, STATUS_PRIORITY,
)
from app.services import module_subscriptions as mod_subs
from app.services import comms_limits
from app.services import club_requests
from app.services import stripe_client
from stripe import error as stripe_error
from datetime import date as _date, datetime as _datetime, timezone as _timezone, timedelta as _timedelta
from app.services import playhq_client
from app.services.name_format import name_sort_key

# Keep strong references to background tasks so they aren't GC'd before completing
_background_tasks: set = set()
# Per-player deep sync locks
_player_sync_running: set = set()


def _push_club_to_twenty(org_id, force_hot: bool = False) -> None:
    """Fire-and-forget: push one club's Company fields (paid/trial modules, ARR,
    renewal) to Twenty after a subscription change. No-op when Twenty isn't
    configured; never raises into the request.

    ``force_hot=True`` (a trial actually starting — see start_module_trial and
    approve_module_request's trial branch) also forces the engagement score to
    Hot (100) and upserts a real Lead, same treatment as a direct "onboard my
    club" enquiry — a club being put on a trial is too strong a signal to wait
    on the gradual recency/frequency formula or the nightly refresh."""
    async def _run():
        try:
            from app.services import twenty_sync
            override = ({"engagementScore": 100, "engagementTier": "HOT", "inSalesCycle": True}
                       if force_hot else None)
            await twenty_sync.push_org_company(org_id, engagement_override=override)
        except Exception:
            _logging.getLogger(__name__).exception("twenty push failed")
    task = asyncio.create_task(_run())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


router = APIRouter(prefix="/club-admin", tags=["club-admin"])


# ---------------------------------------------------------------------------
# Players
# ---------------------------------------------------------------------------

@router.get("/players")
async def list_players(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Player).where(Player.organisation_id == club.id)
    )
    # Surname-first order for everyone, including free-text display overrides
    # (which a plain alphabetical sort would order by first name). See
    # name_sort_key — mirrors the public squad list in routers/players.py.
    players = sorted(result.scalars().all(), key=lambda p: name_sort_key(p.display_name))

    # Last appearance per player (most recent game date) — lets the selection
    # surfaces filter out players who haven't played in N years. One grouped
    # query rather than N per-player lookups.
    last_played: dict[str, str] = {}
    lp_res = await db.execute(_text(
        "SELECT ga.player_id, MAX(g.played_at) AS last_played "
        "FROM game_appearances ga JOIN games g ON ga.game_id = g.id "
        "JOIN players p ON ga.player_id = p.id "
        "WHERE p.organisation_id = :org GROUP BY ga.player_id"
    ), {"org": club.id})
    for pid, lp in lp_res.fetchall():
        last_played[str(pid)] = lp.isoformat() if lp else None

    return [
        {
            "id": str(p.id),
            "name": p.name,
            "display_name": p.display_name,
            "display_name_override": p.display_name_override,
            "playhq_id": p.playhq_id,
            "photo_url": p.photo_url,
            "gender": p.gender,
            "is_player": p.is_player,
            "player_role": p.player_role,
            "is_overseas": p.is_overseas,
            "overseas_country": p.overseas_country,
            "batting_hand": p.batting_hand,
            "bowling_action": p.bowling_action,
            "bowling_type": p.bowling_type,
            "is_opening_batsman": p.is_opening_batsman,
            "skill_positions": p.skill_positions or [],
            "status": p.status,
            "squad_team_id": str(p.squad_team_id) if p.squad_team_id else None,
            "last_played": last_played.get(str(p.id)),
        }
        for p in players
    ]


class PlayerPatch(BaseModel):
    display_name_override: Optional[str] = None
    playhq_id: Optional[str] = None
    gender: Optional[str] = None
    is_player: Optional[bool] = None
    player_role: Optional[str] = None
    is_overseas: Optional[bool] = None
    overseas_country: Optional[str] = None
    batting_hand: Optional[str] = None
    bowling_action: Optional[str] = None
    bowling_type: Optional[str] = None
    is_opening_batsman: Optional[bool] = None


@router.patch("/players/{player_id}")
async def patch_player(
    player_id: str,
    data: PlayerPatch,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player or player.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Player not found")

    if data.display_name_override is not None:
        player.display_name_override = data.display_name_override.strip() or None
    if data.playhq_id is not None:
        new_phq = data.playhq_id.strip() or None
        if new_phq and new_phq != player.playhq_id:
            # Check no other player in this org already holds this PHQ ID
            conflict = await db.execute(
                select(Player).where(
                    Player.organisation_id == club.id,
                    Player.playhq_id == new_phq,
                    Player.id != player.id,
                )
            )
            if conflict.scalar_one_or_none():
                raise HTTPException(status_code=409, detail="Another player already has this PlayHQ ID")
        player.playhq_id = new_phq
    if data.gender is not None:
        player.gender = data.gender.strip() or None
    if data.is_player is not None:
        player.is_player = data.is_player
    if data.player_role is not None:
        player.player_role = data.player_role.strip() or None
    if data.is_overseas is not None:
        player.is_overseas = data.is_overseas
    if data.overseas_country is not None:
        player.overseas_country = data.overseas_country.strip() or None
    if data.batting_hand is not None:
        player.batting_hand = data.batting_hand.strip() or None
    if data.bowling_action is not None:
        player.bowling_action = data.bowling_action.strip() or None
    if data.bowling_type is not None:
        player.bowling_type = data.bowling_type.strip() or None
    if data.is_opening_batsman is not None:
        player.is_opening_batsman = data.is_opening_batsman
    await db.commit()
    return {
        "id": str(player.id),
        "display_name": player.display_name,
        "display_name_override": player.display_name_override,
        "playhq_id": player.playhq_id,
        "gender": player.gender,
        "is_player": player.is_player,
        "player_role": player.player_role,
        "is_overseas": player.is_overseas,
        "overseas_country": player.overseas_country,
        "batting_hand": player.batting_hand,
        "bowling_action": player.bowling_action,
        "bowling_type": player.bowling_type,
        "is_opening_batsman": player.is_opening_batsman,
    }


class PlayerCreate(BaseModel):
    first_name: str
    last_name: str
    playhq_id: Optional[str] = None
    display_name_override: Optional[str] = None


@router.post("/players")
async def create_player(
    data: PlayerCreate,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    first = data.first_name.strip()
    last = data.last_name.strip()
    if not first or not last:
        raise HTTPException(status_code=422, detail="First name and last name are required")

    name = f"{last}, {first}"
    phq_id = data.playhq_id.strip() if data.playhq_id else None
    override = data.display_name_override.strip() or None if data.display_name_override else None

    if phq_id:
        conflict = await db.execute(
            select(Player).where(
                Player.organisation_id == club.id,
                Player.playhq_id == phq_id,
            )
        )
        if conflict.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Another player already has this PlayHQ ID")

    player = Player(
        id=uuid.uuid4(),
        name=name,
        organisation_id=club.id,
        playhq_id=phq_id,
        display_name_override=override,
    )
    db.add(player)
    await db.commit()
    return {
        "id": str(player.id),
        "name": player.name,
        "display_name": player.display_name,
        "display_name_override": player.display_name_override,
        "playhq_id": player.playhq_id,
    }


# ---------------------------------------------------------------------------
# Seasons
# ---------------------------------------------------------------------------

@router.get("/seasons")
async def list_seasons(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    from app.routers.organisations import _season_sort_key
    from app.services.season_aliases import load_active_alias_map, load_reverse_alias_map
    result = await db.execute(
        select(Season).where(Season.organisation_id == club.id)
    )
    seasons = sorted(result.scalars().all(), key=_season_sort_key)
    alias_map = await load_active_alias_map(db, club.id)
    reverse_map = await load_reverse_alias_map(db, club.id)
    name_by_id = {str(s.id): s.name for s in seasons}
    return [
        {
            "id": str(s.id),
            "name": s.name,
            "year": s.year,
            "synced_at": s.synced_at,
            "display_order": s.display_order,
            "alias_of": reverse_map.get(str(s.id)),
            "aliases": [
                {"id": aid, "name": name_by_id.get(aid, "")}
                for aid in alias_map.get(str(s.id), [])
            ],
        }
        for s in seasons
    ]


class SeasonReorderItem(BaseModel):
    id: str
    display_order: int


@router.put("/seasons/reorder")
async def reorder_seasons(
    items: list[SeasonReorderItem],
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    for item in items:
        season = await db.get(Season, uuid.UUID(item.id))
        if season and season.organisation_id == club.id:
            season.display_order = item.display_order
    await db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Season merges (aliases) — admin can merge Summer 25/26 + Winter 25/26 into
# one canonical season for display + aggregation. Soft model: no row rewrites.
# ---------------------------------------------------------------------------


@router.get("/season-merges")
async def list_season_merges(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """All season-alias rows (active + undone) for this club, newest first."""
    rows = await db.execute(
        _text(
            """
            SELECT
                sa.id,
                sa.merged_at,
                sa.undone_at,
                sa.canonical_season_id,
                sa.alias_season_id,
                cs.name AS canonical_name,
                als.name AS alias_name
            FROM season_aliases sa
            JOIN seasons cs  ON cs.id  = sa.canonical_season_id
            JOIN seasons als ON als.id = sa.alias_season_id
            WHERE sa.org_id = :org
            ORDER BY sa.merged_at DESC
            LIMIT 200
            """
        ),
        {"org": str(club.id)},
    )
    return [
        {
            "id": r["id"],
            "merged_at": r["merged_at"].isoformat() if r["merged_at"] else None,
            "undone": r["undone_at"] is not None,
            "canonical_id": str(r["canonical_season_id"]),
            "canonical_name": r["canonical_name"],
            "alias_id": str(r["alias_season_id"]),
            "alias_name": r["alias_name"],
        }
        for r in rows.mappings().all()
    ]


class SeasonMergeRequest(BaseModel):
    canonical_season_id: str
    alias_season_id: str


@router.post("/season-merges")
async def create_season_merge(
    req: SeasonMergeRequest,
    current_user: User = Depends(require_cap(MANAGE_MERGES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Mark `alias_season_id` as merged into `canonical_season_id`.

    Both seasons must belong to this club. If the canonical is itself
    already an alias of a deeper canonical, the merge is chained up so
    aliases always point at the deepest canonical (no cycles, no two-hop
    resolution at query time).
    """
    if req.canonical_season_id == req.alias_season_id:
        raise HTTPException(status_code=400, detail="Canonical and alias are the same season")

    try:
        canonical_uuid = uuid.UUID(req.canonical_season_id)
        alias_uuid = uuid.UUID(req.alias_season_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid season id")

    # Both seasons must belong to this club.
    for sid in (canonical_uuid, alias_uuid):
        season = await db.get(Season, sid)
        if not season or season.organisation_id != club.id:
            raise HTTPException(status_code=404, detail=f"Season {sid} not found in this club")

    # If the canonical is itself currently an alias, redirect through.
    chain = await db.execute(
        _text(
            "SELECT canonical_season_id FROM season_aliases "
            "WHERE org_id = :org AND alias_season_id = :a AND undone_at IS NULL"
        ),
        {"org": str(club.id), "a": str(canonical_uuid)},
    )
    chain_row = chain.first()
    resolved_canonical = str(chain_row[0]) if chain_row else str(canonical_uuid)

    if resolved_canonical == str(alias_uuid):
        raise HTTPException(status_code=400, detail="That merge would create a cycle")

    # If alias is itself currently a canonical for other merges, redirect
    # those rows to the new deeper canonical so we never need multi-hop.
    await db.execute(
        _text(
            "UPDATE season_aliases SET canonical_season_id = :new "
            "WHERE org_id = :org AND canonical_season_id = :old AND undone_at IS NULL"
        ),
        {"new": resolved_canonical, "org": str(club.id), "old": str(alias_uuid)},
    )

    # If this exact alias is already mapped (active), retire that row first.
    await db.execute(
        _text(
            "UPDATE season_aliases SET undone_at = NOW() "
            "WHERE org_id = :org AND alias_season_id = :a AND undone_at IS NULL"
        ),
        {"org": str(club.id), "a": str(alias_uuid)},
    )

    await db.execute(
        _text(
            "INSERT INTO season_aliases (org_id, canonical_season_id, alias_season_id) "
            "VALUES (:org, :c, :a)"
        ),
        {"org": str(club.id), "c": resolved_canonical, "a": str(alias_uuid)},
    )

    from app.services.audit_log import log_activity
    await log_activity(
        db, org_id=club.id, user_id=current_user.id,
        action="merge_seasons", target_type="season", target_id=resolved_canonical,
        details={
            "canonical_season_id": resolved_canonical,
            "alias_season_id": str(alias_uuid),
        },
    )

    await db.commit()
    return {"status": "merged", "canonical_id": resolved_canonical, "alias_id": str(alias_uuid)}


@router.post("/season-merges/{merge_id}/undo")
async def undo_season_merge(
    merge_id: int,
    current_user: User = Depends(require_cap(MANAGE_MERGES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        _text(
            "UPDATE season_aliases SET undone_at = NOW() "
            "WHERE id = :id AND org_id = :org AND undone_at IS NULL "
            "RETURNING id"
        ),
        {"id": merge_id, "org": str(club.id)},
    )
    if result.first() is None:
        raise HTTPException(status_code=404, detail="Merge not found or already undone")

    from app.services.audit_log import log_activity
    await log_activity(
        db, org_id=club.id, user_id=current_user.id,
        action="undo_merge_seasons", target_type="season_alias",
        target_id=str(merge_id),
    )
    await db.commit()
    return {"status": "undone"}


# ---------------------------------------------------------------------------
# Activity log — append-only record of sensitive admin actions
# ---------------------------------------------------------------------------


@router.get("/activity-log")
async def list_activity_log(
    limit: int = 100,
    current_user: User = Depends(require_cap(MANAGE_USERS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Recent admin actions for this club, newest first."""
    limit = max(1, min(limit, 500))
    rows = await db.execute(
        _text(
            """
            SELECT
                al.id,
                al.created_at,
                al.action,
                al.target_type,
                al.target_id,
                al.details,
                al.user_id,
                u.email AS user_email
            FROM audit_logs al
            LEFT JOIN users u ON u.id = al.user_id
            WHERE al.org_id = :org
            ORDER BY al.created_at DESC
            LIMIT :lim
            """
        ),
        {"org": str(club.id), "lim": limit},
    )
    return [
        {
            "id": r["id"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "action": r["action"],
            "target_type": r["target_type"],
            "target_id": r["target_id"],
            "user_email": r["user_email"],
            "details": r["details"] or {},
        }
        for r in rows.mappings().all()
    ]


# ---------------------------------------------------------------------------
# Grades — display name overrides
# ---------------------------------------------------------------------------

@router.get("/grades")
async def list_grades(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """List distinct grade names for this org with any display_name_override set."""
    from sqlalchemy import text
    rows = await db.execute(
        text("""
            SELECT
                gr.name AS original_name,
                COALESCE(MAX(gr.display_name_override), gr.name) AS display_name,
                MAX(gr.display_name_override) AS display_name_override,
                COUNT(DISTINCT g.id) AS games
            FROM grades gr
            JOIN seasons s ON s.id = gr.season_id
            LEFT JOIN games g ON g.grade_id = gr.id
            WHERE s.organisation_id = :org_id
            GROUP BY gr.name
            ORDER BY gr.name
        """),
        {"org_id": str(club.id)},
    )
    return [dict(r) for r in rows.mappings().all()]


class GradeRenamePatch(BaseModel):
    original_name: str
    display_name_override: Optional[str] = None


@router.patch("/grades/rename")
async def rename_grade(
    data: GradeRenamePatch,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Set or clear a display_name_override on all grade rows with the given name in this org."""
    from sqlalchemy import text
    override = data.display_name_override.strip() if data.display_name_override else None
    override = override or None
    result = await db.execute(
        text("""
            UPDATE grades gr
            SET display_name_override = :override
            FROM seasons s
            WHERE gr.season_id = s.id
              AND s.organisation_id = :org_id
              AND gr.name = :original_name
        """),
        {"override": override, "org_id": str(club.id), "original_name": data.original_name},
    )
    await db.commit()
    return {"updated": result.rowcount, "original_name": data.original_name, "display_name_override": override}


# ---------------------------------------------------------------------------
# Games (read-only list — PlayHQ is source of truth)
# ---------------------------------------------------------------------------

@router.get("/games")
async def list_games(
    season_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import text
    query = """
        SELECT g.id, g.played_at, g.home_team, g.away_team, g.result, g.winning_team,
               COALESCE(gr.display_name_override, gr.name) AS grade_name, s.name AS season_name
        FROM games g
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        WHERE s.organisation_id = :org_id
    """
    params: dict = {"org_id": str(club.id)}
    if season_id:
        query += " AND s.id = :season_id"
        params["season_id"] = season_id
    query += " ORDER BY g.played_at DESC LIMIT 200"

    rows = await db.execute(text(query), params)
    return [
        {
            "id": str(r.id),
            "played_at": r.played_at.isoformat() if r.played_at else None,
            "home_team": r.home_team,
            "away_team": r.away_team,
            "result": r.result,
            "winning_team": r.winning_team,
            "grade": r.grade_name,
            "season": r.season_name,
        }
        for r in rows.mappings().all()
    ]


# ---------------------------------------------------------------------------
# Club settings
# ---------------------------------------------------------------------------

class SettingsPatch(BaseModel):
    name: Optional[str] = None
    contact_email: Optional[str] = None
    primary_color: Optional[str] = None
    accent_color: Optional[str] = None
    theme_mode: Optional[str] = None
    theme_config: Optional[dict] = None
    player_name_format: Optional[str] = None
    dormancy_months: Optional[int] = None
    default_team_size: Optional[int] = None
    # Public player-profile attribute visibility (overseas is always shown).
    public_show_role: Optional[bool] = None
    public_show_batting: Optional[bool] = None
    public_show_bowling: Optional[bool] = None
    public_show_opening: Optional[bool] = None
    public_show_gender: Optional[bool] = None
    include_fill_ins_in_stats: Optional[bool] = None
    # BetterSocials post-generator style (palette/font/background choices +
    # saved custom palettes/designs) — persisted per club so the look
    # survives browsers and the Setup Wizard can auto-detect it. See
    # _sanitize_socials_style for the accepted shape.
    socials_style: Optional[dict] = None


# Keys allowed inside theme_config and the sub-keys allowed in light/dark palettes.
_THEME_COLOR_KEYS = {
    "accent", "accent2", "positive", "negative",
    "chart_runs", "chart_wickets", "chart_milestone",
    "cat_honour", "cat_role", "cat_award", "cat_milestone",
}
_THEME_PALETTE_KEYS = {
    "bg", "surface", "surface2", "hairline", "hairline2",
    "text", "dim", "faint", "faintest",
}
_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def _valid_hex(value) -> bool:
    return isinstance(value, str) and bool(_HEX_RE.match(value.strip()))


# Top-level keys the socials_style blob may carry (the post generator's Style
# state — see AdminSocialPost.jsx). Values are stored as sent bar the
# allowlist and an overall size cap; the generator is the only consumer, so
# deep validation would just chase its shape around.
_SOCIALS_STYLE_KEYS = {"palette", "dark", "font", "bg", "bg_colors", "palettes", "designs"}
_SOCIALS_STYLE_MAX_BYTES = 32_768


def _sanitize_socials_style(raw: dict) -> dict | None:
    clean = {k: v for k, v in raw.items() if k in _SOCIALS_STYLE_KEYS}
    if not clean:
        return None
    try:
        if len(_json.dumps(clean)) > _SOCIALS_STYLE_MAX_BYTES:
            return None
    except (TypeError, ValueError):
        return None
    return clean


def _sanitize_theme_config(raw: dict) -> dict:
    """Keep only recognised keys with valid hex colour values."""
    clean: dict = {}
    for key in _THEME_COLOR_KEYS:
        val = raw.get(key)
        if _valid_hex(val):
            clean[key] = val.strip()
    series = raw.get("chart_series")
    if isinstance(series, list):
        clean_series = [c.strip() for c in series if _valid_hex(c)]
        if clean_series:
            clean["chart_series"] = clean_series[:12]
    for theme in ("light", "dark"):
        palette = raw.get(theme)
        if isinstance(palette, dict):
            clean_palette = {
                k: v.strip() for k, v in palette.items()
                if k in _THEME_PALETTE_KEYS and _valid_hex(v)
            }
            if clean_palette:
                clean[theme] = clean_palette
    return clean


@router.get("/settings")
async def get_settings(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
):
    return {
        "id": str(club.id),
        "slug": club.slug,
        "name": club.name,
        "short_name": club.short_name,
        "contact_email": club.contact_email,
        "primary_color": club.primary_color,
        "accent_color": club.accent_color,
        "theme_mode": club.theme_mode,
        "theme_config": club.theme_config or {},
        "logo_url": club.logo_url,
        "hero_image_url": club.hero_image_url,
        "is_active": club.is_active,
        "playhq_id": club.playhq_id,
        "player_name_format": club.player_name_format or "last_first",
        "dormancy_months": club.dormancy_months if club.dormancy_months is not None else 24,
        "default_team_size": club.default_team_size if club.default_team_size is not None else 11,
        "public_show_role": bool(club.public_show_role),
        "public_show_batting": bool(club.public_show_batting),
        "public_show_bowling": bool(club.public_show_bowling),
        "public_show_opening": bool(club.public_show_opening),
        "public_show_gender": bool(club.public_show_gender),
        "include_fill_ins_in_stats": bool(club.include_fill_ins_in_stats),
        "socials_style": club.socials_style,
    }


@router.patch("/settings")
async def patch_settings(
    data: SettingsPatch,
    current_user: User = Depends(require_cap(MANAGE_SETTINGS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    if data.name is not None:
        club.name = data.name.strip()
    if data.contact_email is not None:
        club.contact_email = data.contact_email.strip() or None
    if data.primary_color is not None:
        club.primary_color = data.primary_color.strip()
    if data.accent_color is not None:
        club.accent_color = data.accent_color.strip()
    if data.theme_mode is not None and data.theme_mode in ("light", "dark", "auto"):
        club.theme_mode = data.theme_mode
    if data.theme_config is not None:
        clean = _sanitize_theme_config(data.theme_config)
        club.theme_config = clean or None
        # Keep the legacy accent_color column in sync for consumers that
        # still read it directly (share cards, public club payloads).
        if clean.get("accent"):
            club.accent_color = clean["accent"]
    if data.player_name_format is not None and data.player_name_format in ("last_first", "first_last", "first_initial_last", "last_first_initial"):
        club.player_name_format = data.player_name_format
    if data.dormancy_months is not None:
        # Clamp to a sane range: 1 month .. 50 years.
        club.dormancy_months = max(1, min(600, int(data.dormancy_months)))
    if data.default_team_size is not None and int(data.default_team_size) in (0, 11, 12, 13):
        club.default_team_size = int(data.default_team_size)
    # Public player-attribute visibility toggles.
    if data.public_show_role is not None:
        club.public_show_role = bool(data.public_show_role)
    if data.public_show_batting is not None:
        club.public_show_batting = bool(data.public_show_batting)
    if data.public_show_bowling is not None:
        club.public_show_bowling = bool(data.public_show_bowling)
    if data.public_show_opening is not None:
        club.public_show_opening = bool(data.public_show_opening)
    if data.public_show_gender is not None:
        club.public_show_gender = bool(data.public_show_gender)
    if data.include_fill_ins_in_stats is not None:
        club.include_fill_ins_in_stats = bool(data.include_fill_ins_in_stats)
    if data.socials_style is not None:
        club.socials_style = _sanitize_socials_style(data.socials_style)

    # Record which fields the admin touched. Don't dump full new values into
    # the audit row — colour codes / names will already be visible in the
    # settings UI and audit-only fields can pile up quickly. A list of
    # changed-field names is enough to answer "who changed the club name
    # last Tuesday?".
    changed = [
        k for k, v in data.dict(exclude_unset=True).items() if v is not None
    ]
    from app.services.audit_log import log_activity
    await log_activity(
        db, org_id=club.id, user_id=current_user.id,
        action="patch_settings", target_type="org", target_id=str(club.id),
        details={"changed_fields": changed},
    )

    await db.commit()
    return {"status": "updated"}


# ---------------------------------------------------------------------------
# Club logo (white-labelling)
# ---------------------------------------------------------------------------

LOGO_ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
LOGO_MAX_BYTES = 2 * 1024 * 1024

_IMAGE_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def _remove_uploaded_logo(logo_url: Optional[str]) -> None:
    """Delete a previously uploaded logo file. No-op for external URLs."""
    if not logo_url or not logo_url.startswith("/uploads/logos/"):
        return
    p = Path("/app") / logo_url.lstrip("/")
    p.unlink(missing_ok=True)


@router.post("/logo")
async def upload_logo(
    file: UploadFile = File(...),
    current_user: User = Depends(require_cap(MANAGE_SETTINGS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in LOGO_ALLOWED_EXTS:
        raise HTTPException(400, "Image files only (jpg, png, webp, gif)")
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    if len(data) > LOGO_MAX_BYTES:
        raise HTTPException(400, "Logo must be 2 MB or smaller")

    _remove_uploaded_logo(club.logo_url)  # clean up any legacy on-disk file
    club.logo_data = data
    club.logo_mime = _IMAGE_MIME.get(ext, "image/png")
    club.logo_url = f"/api/images/organisations/{club.id}/logo?v={uuid.uuid4().hex[:8]}"
    await db.commit()
    return {"logo_url": club.logo_url}


@router.delete("/logo")
async def delete_logo(
    current_user: User = Depends(require_cap(MANAGE_SETTINGS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    _remove_uploaded_logo(club.logo_url)
    club.logo_data = None
    club.logo_mime = None
    club.logo_url = None
    await db.commit()
    return {"status": "cleared"}


# ---------------------------------------------------------------------------
# Player photo upload
# ---------------------------------------------------------------------------

PHOTO_ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
PHOTO_MAX_BYTES = 2 * 1024 * 1024


def _remove_player_photo(photo_url: Optional[str]) -> None:
    if not photo_url or not photo_url.startswith("/uploads/players/"):
        return
    p = Path("/app") / photo_url.lstrip("/")
    p.unlink(missing_ok=True)


@router.post("/players/{player_id}/photo")
async def upload_player_photo(
    player_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    import uuid as _uuid
    player = await db.get(Player, _uuid.UUID(player_id))
    if not player or str(player.organisation_id) != str(club.id):
        raise HTTPException(404, "Player not found")

    ext = Path(file.filename or "").suffix.lower()
    if ext not in PHOTO_ALLOWED_EXTS:
        raise HTTPException(400, "Image files only (jpg, png, webp, gif)")
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    if len(data) > PHOTO_MAX_BYTES:
        raise HTTPException(400, "Photo must be 2 MB or smaller")

    _remove_player_photo(player.photo_url)  # clean up any legacy on-disk file
    player.photo_data = data
    player.photo_mime = _IMAGE_MIME.get(ext, "image/png")
    player.photo_url = f"/api/images/players/{player.id}/photo?v={_uuid.uuid4().hex[:8]}"
    await db.commit()
    return {"photo_url": player.photo_url}


@router.delete("/players/{player_id}/photo")
async def delete_player_photo(
    player_id: str,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    import uuid as _uuid
    player = await db.get(Player, _uuid.UUID(player_id))
    if not player or str(player.organisation_id) != str(club.id):
        raise HTTPException(404, "Player not found")
    _remove_player_photo(player.photo_url)
    player.photo_data = None
    player.photo_mime = None
    player.photo_url = None
    await db.commit()
    return {"status": "cleared"}


# ---------------------------------------------------------------------------
# Manual partnership records
# ---------------------------------------------------------------------------

class ManualPartnershipCreate(BaseModel):
    batter1_id: Optional[str] = None
    batter1_name: str
    batter2_id: Optional[str] = None
    batter2_name: str
    grade_name: str
    season_year: int
    wicket_number: int
    runs: int
    is_not_out: bool = False
    notes: Optional[str] = None


@router.get("/partnership-records")
async def list_partnership_records(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ManualPartnershipRecord)
        .where(ManualPartnershipRecord.org_id == club.id)
        .order_by(ManualPartnershipRecord.runs.desc())
    )
    records = result.scalars().all()
    return [
        {
            "id": r.id,
            "batter1_id": str(r.batter1_id) if r.batter1_id else None,
            "batter1_name": r.batter1_name,
            "batter2_id": str(r.batter2_id) if r.batter2_id else None,
            "batter2_name": r.batter2_name,
            "grade_name": r.grade_name,
            "season_year": r.season_year,
            "wicket_number": r.wicket_number,
            "runs": r.runs,
            "is_not_out": r.is_not_out,
            "notes": r.notes,
        }
        for r in records
    ]


@router.post("/partnership-records", status_code=201)
async def create_partnership_record(
    data: ManualPartnershipCreate,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    record = ManualPartnershipRecord(
        org_id=club.id,
        batter1_id=uuid.UUID(data.batter1_id) if data.batter1_id else None,
        batter1_name=data.batter1_name.strip(),
        batter2_id=uuid.UUID(data.batter2_id) if data.batter2_id else None,
        batter2_name=data.batter2_name.strip(),
        grade_name=data.grade_name.strip(),
        season_year=data.season_year,
        wicket_number=data.wicket_number,
        runs=data.runs,
        is_not_out=data.is_not_out,
        notes=data.notes,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return {"id": record.id, "status": "created"}


@router.delete("/partnership-records/{record_id}", status_code=204)
async def delete_partnership_record(
    record_id: int,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ManualPartnershipRecord).where(
            ManualPartnershipRecord.id == record_id,
            ManualPartnershipRecord.org_id == club.id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    await db.delete(record)
    await db.commit()


class ManualPartnershipPatch(BaseModel):
    batter1_id: Optional[str] = None
    batter1_name: Optional[str] = None
    batter2_id: Optional[str] = None
    batter2_name: Optional[str] = None
    grade_name: Optional[str] = None
    season_year: Optional[int] = None
    wicket_number: Optional[int] = None
    runs: Optional[int] = None
    is_not_out: Optional[bool] = None
    notes: Optional[str] = None


@router.patch("/partnership-records/{record_id}")
async def patch_partnership_record(
    record_id: int,
    data: ManualPartnershipPatch,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ManualPartnershipRecord).where(
            ManualPartnershipRecord.id == record_id,
            ManualPartnershipRecord.org_id == club.id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    fields = data.model_fields_set
    if 'batter1_id' in fields:
        record.batter1_id = uuid.UUID(data.batter1_id) if data.batter1_id else None
    if 'batter1_name' in fields and data.batter1_name is not None:
        record.batter1_name = data.batter1_name.strip()
    if 'batter2_id' in fields:
        record.batter2_id = uuid.UUID(data.batter2_id) if data.batter2_id else None
    if 'batter2_name' in fields and data.batter2_name is not None:
        record.batter2_name = data.batter2_name.strip()
    if 'grade_name' in fields and data.grade_name is not None:
        record.grade_name = data.grade_name.strip()
    if 'season_year' in fields and data.season_year is not None:
        record.season_year = data.season_year
    if 'wicket_number' in fields and data.wicket_number is not None:
        record.wicket_number = data.wicket_number
    if 'runs' in fields and data.runs is not None:
        record.runs = data.runs
    if 'is_not_out' in fields:
        record.is_not_out = data.is_not_out
    if 'notes' in fields:
        record.notes = data.notes
    await db.commit()
    return {"status": "updated"}


# ---------------------------------------------------------------------------
# Partnership records — template & bulk import
# ---------------------------------------------------------------------------

_PARTNERSHIP_TEMPLATE_ROWS = [
    ("Matthew Edwards", "Pratik Bhave", "147", "3", "2024", "No", "1st XI"),
    ("Jack Barendse", "Chris Cooper", "98", "1", "2023", "Yes", "2nd XI"),
]

ORDINAL_MAP = {
    "1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "5th": 5,
    "6th": 6, "7th": 7, "8th": 8, "9th": 9, "10th": 10,
}


def _normalise_name(name: str) -> str:
    """'Last, First' → 'first last'. Splits on a bare comma (not the literal ", "
    substring) and strips each side before rejoining, so a stray space before the
    comma ("Smith , John") doesn't leave a trailing space baked into the key that
    silently fails to match a correctly-typed "Smith, John"."""
    name = name.strip()
    if "," in name:
        parts = name.split(",", 1)
        name = f"{parts[1].strip()} {parts[0].strip()}".strip()
    return re.sub(r"\s+", " ", name).strip().lower()


def _parse_xlsx_partnerships(content: bytes) -> list[dict]:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [str(h).strip().lower().replace(" ", "_") if h else "" for h in rows[0]]
    result = []
    for row in rows[1:]:
        if not any(row):
            continue
        d = {headers[i]: (str(v).strip() if v is not None else "") for i, v in enumerate(row) if i < len(headers)}
        result.append(d)
    return result


def _parse_csv_partnerships(content: bytes) -> list[dict]:
    try:
        text_content = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text_content = content.decode("latin-1")
    reader = csv.DictReader(io.StringIO(text_content))
    return [
        {k.strip().lower().replace(" ", "_"): (v.strip() if v else "")
         for k, v in row.items()}
        for row in reader
        if any(row.values())
    ]


@router.get("/partnership-records/template")
async def download_partnership_template(
    current_user: User = Depends(get_current_user),
):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Batter 1", "Batter 2", "Runs", "Wicket", "Season", "Not Out", "Grade"])
    writer.writerows(_PARTNERSHIP_TEMPLATE_ROWS)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=partnership_records_template.csv"},
    )


@router.post("/partnership-records/import")
async def import_partnership_records(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await _do_import_partnership_records(file, club, db)
    except HTTPException:
        raise
    except Exception as exc:
        _logging.getLogger(__name__).error("Partnership import failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Import failed: {exc}")


async def _do_import_partnership_records(file, club, db):
    content = await file.read()
    filename = (file.filename or "").lower()

    if filename.endswith(".xlsx") or filename.endswith(".xls"):
        rows = _parse_xlsx_partnerships(content)
    else:
        rows = _parse_csv_partnerships(content)

    if not rows:
        raise HTTPException(status_code=400, detail="No data found in file")

    # Build name→id map for this org
    players_result = await db.execute(
        _text("SELECT id, name FROM players WHERE organisation_id = :org_id"),
        {"org_id": str(club.id)},
    )
    player_map: dict[str, str] = {
        _normalise_name(row["name"]): str(row["id"])
        for row in players_result.mappings().all()
    }

    created_records = []
    duplicate_records = []  # already existed (synced or manual) — not imported
    skipped = 0
    errors = []

    for i, row in enumerate(rows, 2):
        b1_name = (row.get("batter_1") or row.get("batter1") or "").strip()
        b2_name = (row.get("batter_2") or row.get("batter2") or "").strip()
        runs_raw = row.get("runs", "").strip()
        wicket_raw = row.get("wicket", "").strip()
        season_raw = row.get("season", "").strip()
        not_out_raw = (row.get("not_out") or row.get("not_out_(y/n)") or "").strip().lower()
        grade = row.get("grade", "").strip()

        if not b1_name or not b2_name or not runs_raw or not grade or not season_raw:
            skipped += 1
            continue

        try:
            runs = int(float(runs_raw))
            season_year = int(float(season_raw))
        except ValueError:
            errors.append(f"Row {i}: invalid runs or season value")
            skipped += 1
            continue

        # Accept ordinal strings ("1st", "3rd") or plain integers for wicket
        wicket_number = ORDINAL_MAP.get(wicket_raw.lower())
        if wicket_number is None:
            try:
                wicket_number = int(float(wicket_raw)) if wicket_raw else 0
            except ValueError:
                wicket_number = 0
        if wicket_number < 1 or wicket_number > 10:
            errors.append(f"Row {i}: wicket must be 1–10 (got '{wicket_raw}')")
            skipped += 1
            continue

        is_not_out = not_out_raw in ("yes", "y", "true", "1")

        b1_id = player_map.get(_normalise_name(b1_name))
        b2_id = player_map.get(_normalise_name(b2_name))

        # Skip rows that already exist — so re-running an import (or importing a
        # stand that sync already holds) can't pile up duplicates on the records
        # page. Two sources to check:
        existing_reason = None

        # 1) A synced scorecard partnership for the same stand. Match the season on
        #    the Season's START year (manual records store the start year, e.g. 2016
        #    for 2016/17, while the game can be played in either calendar year of a
        #    summer season — matching EXTRACT(YEAR FROM played_at) missed those).
        #    Only checkable when both batters resolved to ids.
        if b1_id and b2_id:
            syn_res = await db.execute(_text("""
                SELECT 1
                FROM v_effective_partnerships pt
                JOIN games   g  ON g.id  = pt.game_id
                JOIN grades  gr ON gr.id = g.grade_id
                JOIN seasons s  ON s.id  = gr.season_id
                WHERE s.organisation_id = :org_id
                  AND pt.is_club_innings IS NOT FALSE
                  AND pt.runs = :runs
                  AND pt.wicket_number = :wicket
                  AND (
                    (pt.batter1_id = CAST(:b1_id AS uuid) AND pt.batter2_id = CAST(:b2_id AS uuid)) OR
                    (pt.batter1_id = CAST(:b2_id AS uuid) AND pt.batter2_id = CAST(:b1_id AS uuid))
                  )
                  AND lower(btrim(:grade)) IN (
                    lower(btrim(gr.name)),
                    lower(btrim(COALESCE(gr.display_name_override, gr.name)))
                  )
                  AND :season_year = COALESCE(
                    s.year, NULLIF(substring(s.name from '([0-9]{4})'), '')::int
                  )
                LIMIT 1
            """), {
                "org_id": str(club.id), "runs": runs, "wicket": wicket_number,
                "season_year": season_year, "grade": grade,
                "b1_id": b1_id, "b2_id": b2_id,
            })
            if syn_res.first() is not None:
                existing_reason = "synced"

        # 2) A previously-imported manual record for the same stand (unordered name
        #    pair). Names are always present, so this catches re-uploading a file.
        if existing_reason is None:
            man_res = await db.execute(_text("""
                SELECT 1 FROM manual_partnership_records m
                WHERE m.org_id = :org_id
                  AND m.runs = :runs
                  AND m.wicket_number = :wicket
                  AND m.season_year = :season_year
                  AND lower(btrim(m.grade_name)) = lower(btrim(:grade))
                  AND (
                    (lower(btrim(m.batter1_name)) = lower(btrim(:b1_name)) AND lower(btrim(m.batter2_name)) = lower(btrim(:b2_name))) OR
                    (lower(btrim(m.batter1_name)) = lower(btrim(:b2_name)) AND lower(btrim(m.batter2_name)) = lower(btrim(:b1_name)))
                  )
                LIMIT 1
            """), {
                "org_id": str(club.id), "runs": runs, "wicket": wicket_number,
                "season_year": season_year, "grade": grade,
                "b1_name": b1_name, "b2_name": b2_name,
            })
            if man_res.first() is not None:
                existing_reason = "manual"

        if existing_reason:
            duplicate_records.append({
                "batter1_name": b1_name,
                "batter2_name": b2_name,
                "runs": runs,
                "wicket_number": wicket_number,
                "season_year": season_year,
                "grade_name": grade,
                "reason": existing_reason,
            })
            continue

        record = ManualPartnershipRecord(
            org_id=club.id,
            batter1_id=uuid.UUID(b1_id) if b1_id else None,
            batter1_name=b1_name,
            batter2_id=uuid.UUID(b2_id) if b2_id else None,
            batter2_name=b2_name,
            grade_name=grade,
            season_year=season_year,
            wicket_number=wicket_number,
            runs=runs,
            is_not_out=is_not_out,
        )
        db.add(record)
        await db.flush()

        created_records.append({
            "id": record.id,
            "batter1_name": b1_name,
            "batter1_id": b1_id,
            "batter1_unmatched": b1_id is None,
            "batter2_name": b2_name,
            "batter2_id": b2_id,
            "batter2_unmatched": b2_id is None,
            "runs": runs,
            "wicket_number": wicket_number,
            "season_year": season_year,
            "grade_name": grade,
            "is_not_out": is_not_out,
        })

    await db.commit()

    return {
        "created": len(created_records),
        "skipped": skipped,
        "skipped_duplicates": len(duplicate_records),
        "duplicates": duplicate_records,
        "errors": errors,
        "records": created_records,
    }


class PartnershipGradeRename(BaseModel):
    old_name: str
    new_name: str


@router.post("/partnership-records/rename-grade")
async def rename_partnership_grade(
    data: PartnershipGradeRename,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        _text("""
            UPDATE manual_partnership_records
            SET grade_name = :new_name
            WHERE org_id = :org_id AND grade_name = :old_name
        """),
        {"new_name": data.new_name.strip(), "org_id": str(club.id), "old_name": data.old_name},
    )
    await db.commit()
    return {"updated": result.rowcount}


# ---------------------------------------------------------------------------
# Super admin — club management
# ---------------------------------------------------------------------------

class ClubCreate(BaseModel):
    org_id: str
    name: str
    slug: str
    short_name: Optional[str] = None
    contact_email: Optional[str] = None
    primary_color: str = "#16c784"
    accent_color: str = "#243352"


@router.get("/super/overview")
async def super_overview(
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Platform-wide fleet snapshot for the Better staff dashboard.

    Fleet KPIs (clubs / active / users / players / games + tier, status and
    module-adoption breakdowns) plus a per-club rollup (data volume, members,
    last sync, last admin login) so staff can see, at a glance, which clubs are
    healthy and which are stale. Read-only.
    """
    from types import SimpleNamespace
    try:
        # Select ONLY the columns we need (raw), NOT select(Organisation): the
        # ORM load demands every model column, so any column the live DB hasn't
        # had added yet (migration drift) would 500 the whole endpoint. The
        # grouped per-table aggregates below replace the old per-club correlated
        # subqueries that tripped a statement timeout at fleet scale.
        org_rows = (await db.execute(_text(
            "SELECT id::text AS id, name, slug, subscription_status, is_active, "
            "module_overrides, created_at FROM organisations ORDER BY name"
        ))).mappings().all()

        players_by = {r["org"]: r["n"] for r in (await db.execute(_text(
            "SELECT organisation_id::text AS org, COUNT(*) AS n FROM players GROUP BY organisation_id"
        ))).mappings().all()}
        # games have no organisation_id — they hang off a grade, which hangs off
        # a season, which is org-scoped.
        games_by = {r["org"]: r["n"] for r in (await db.execute(_text(
            "SELECT s.organisation_id::text AS org, COUNT(*) AS n "
            "FROM games g JOIN grades gr ON gr.id = g.grade_id "
            "JOIN seasons s ON s.id = gr.season_id GROUP BY s.organisation_id"
        ))).mappings().all()}
        sync_by = {r["org"]: r["t"] for r in (await db.execute(_text(
            "SELECT organisation_id::text AS org, MAX(synced_at) AS t FROM seasons GROUP BY organisation_id"
        ))).mappings().all()}
        member_rows = (await db.execute(_text(
            "SELECT cm.club_id::text AS org, COUNT(*) AS n, MAX(u.last_login_at) AS last_login "
            "FROM club_memberships cm JOIN users u ON u.id = cm.user_id GROUP BY cm.club_id"
        ))).mappings().all()
        members_by = {r["org"]: r["n"] for r in member_rows}
        login_by = {r["org"]: r["last_login"] for r in member_rows}

        clubs = []
        by_status: dict[str, int] = {}
        module_adoption: dict[str, int] = {}
        active_clubs = total_players = total_games = 0
        for r in org_rows:
            oid = r["id"]
            status_ = r["subscription_status"] or "active"
            by_status[status_] = by_status.get(status_, 0) + 1
            # Reuse the entitlement helper on a lightweight stand-in (raw values),
            # so we don't need a full ORM object.
            mods = sorted(org_entitled_modules(SimpleNamespace(
                subscription_status=status_, module_overrides=r["module_overrides"] or [],
            )))
            for m in mods:
                module_adoption[m] = module_adoption.get(m, 0) + 1
            p = players_by.get(oid, 0) or 0
            g = games_by.get(oid, 0) or 0
            total_players += p
            total_games += g
            if r["is_active"]:
                active_clubs += 1
            ls = sync_by.get(oid)
            ll = login_by.get(oid)
            clubs.append({
                "id": oid,
                "name": r["name"],
                "slug": r["slug"],
                "subscription_status": status_,
                "is_active": r["is_active"],
                "modules": mods,
                "players": p,
                "games": g,
                "members": members_by.get(oid, 0) or 0,
                "last_sync": ls.isoformat() if ls else None,
                "last_login": ll.isoformat() if ll else None,
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            })

        total_users = (await db.execute(select(func.count()).select_from(User))).scalar() or 0
        super_admins = (await db.execute(
            select(func.count()).select_from(ClubMembership).where(ClubMembership.role == "super_admin")
        )).scalar() or 0

        return {
            "totals": {
                "clubs": len(clubs),
                "active_clubs": active_clubs,
                "users": total_users,
                "super_admins": super_admins,
                "players": total_players,
                "games": total_games,
                "by_status": by_status,
                "module_adoption": module_adoption,
            },
            "clubs": clubs,
        }
    except HTTPException:
        raise
    except Exception as e:  # surface the real cause to the (super-admin-only) UI
        _logging.getLogger(__name__).exception("super_overview failed")
        raise HTTPException(status_code=500, detail=f"Overview failed: {type(e).__name__}: {e}")


def _module_subs_payload(org) -> list[dict]:
    """Per-billable-module subscription rows for a club (super-admin view). The
    BetterAdmin members (fees/comms/merch) collapse into one row — they always move
    as a unit. Requires the module_subscriptions relationship to be loaded."""
    now = _datetime.now(_timezone.utc)
    groups: dict[str, list] = {}
    for s in (org.module_subscriptions or []):
        if s.module_key in MANAGED_MODULES:
            groups.setdefault(billing_key_for(s.module_key), []).append(s)
    out = []
    for bk, rows in groups.items():
        # Representative = the least-committed member — same STATUS_PRIORITY the
        # Account page's account_plan_status() uses, so this editor and a club's own
        # Account page always agree on what a mixed group displays as.
        rep = sorted(rows, key=lambda s: STATUS_PRIORITY.get(s.status, 9))[0]
        out.append({
            "module": bk,
            "name": BILLABLE_MODULE_NAMES.get(bk, bk),
            "status": rep.status,
            "is_trial_expired": mod_subs.sub_is_trial_expired(rep, now),
            "trial_started_at": rep.trial_started_at.isoformat() if rep.trial_started_at else None,
            "trial_ends_at": rep.trial_ends_at.isoformat() if rep.trial_ends_at else None,
            "renewal_date": rep.renewal_date.isoformat() if rep.renewal_date else None,
        })
    return sorted(out, key=lambda d: d["module"])


def _club_payload(
    org,
    association_name: str | None = None,
    primary_admin_name: str | None = None,
    state: str | None = None,
    seasons_count: int = 0,
    players_count: int = 0,
    grades_count: int = 0,
    onboarding_done: int = 0,
    onboarding_total: int = 0,
    last_active_at=None,
    last_full_sync_at=None,
    full_sync_running: bool = False,
    full_sync_paused: bool = False,
    full_sync_kind: str | None = None,
    engagement_score: int | None = None,
    engagement_tier: str | None = None,
    engagement_scored_at=None,
    engagement_actions: dict | None = None,
) -> dict:
    return {
        "id": str(org.id),
        "slug": org.slug,
        "name": org.name,
        "short_name": org.short_name,
        "is_active": org.is_active,
        "archived_at": org.archived_at.isoformat() if org.archived_at else None,
        "contact_email": org.contact_email,
        # Organisation.state is only ever populated by the self-serve registration
        # flow (migration 158) — every club onboarded the older way (the "New Club"
        # search on this page) has it NULL. Fall back to the Club Directory's own
        # marketing_clubs row (crawled address, far more complete) when known.
        "state": state or org.state,
        # From the Club Directory's marketing_clubs row this org was onboarded
        # from, when known (see MarketingClub.existing_org_id) — Organisation
        # itself has no association column of its own.
        "association_name": association_name,
        "primary_admin_name": primary_admin_name,
        "module_overrides": list(org.module_overrides or []),
        "modules": sorted(org_entitled_modules(org)),
        "module_subscriptions": _module_subs_payload(org),
        "subscription_status": org.subscription_status,
        "renewal_date": org.renewal_date.isoformat() if org.renewal_date else None,
        "billing_cycle": org.billing_cycle,
        # Per-club override of platform_settings.billing_checkout_enabled
        # (migration 151) — NULL = follow the platform default.
        "billing_checkout_override": org.billing_checkout_override,
        "default_trial_days": org_default_trial_days(org),
        "comms_tier": getattr(org, "comms_tier", None) or "sandbox",
        "comms_sandbox_cap": getattr(org, "comms_sandbox_cap", None),
        "comms_production_cap": getattr(org, "comms_production_cap", None),
        "comms_monthly_cap": getattr(org, "comms_monthly_cap", None),
        "created_at": org.created_at.isoformat() if org.created_at else None,
        "seasons_count": seasons_count,
        "players_count": players_count,
        "grades_count": grades_count,
        # Setup Wizard progress — stored completion only (no live re-detection),
        # same cheap read the onboarding_wizard router's own GET /state uses.
        "onboarding_done": onboarding_done,
        "onboarding_total": onboarding_total,
        # Most recent admin-app activity recorded against this club (usage_events),
        # last 180 days only — a proxy for "actively used", not a per-module log.
        "last_active_at": last_active_at.isoformat() if last_active_at else None,
        # Most recent Sync Now / Full Rebuild run, and whether one is live right now.
        "last_full_sync_at": last_full_sync_at.isoformat() if last_full_sync_at else None,
        "full_sync_running": full_sync_running,
        # Paused via the All Clubs Pause Sync button (services/sync.py's
        # SyncControlSignal / pause_sync_run) — Continue Sync starts a fresh
        # incremental sync_organisation() call, safe even after a paused
        # Full Rebuild (its wipe already committed before the pause).
        "full_sync_paused": full_sync_paused,
        "full_sync_kind": full_sync_kind,
        # Cached Twenty engagement score from the club's linked marketing_clubs
        # row (see MarketingClub.engagement_score — written by every
        # twenty_sync._engagement() call). NULL = never scored, which the All
        # Clubs page shows as "not yet scored" rather than 0.
        "engagement_score": engagement_score,
        "engagement_tier": engagement_tier,
        "engagement_scored_at": engagement_scored_at.isoformat() if engagement_scored_at else None,
        # Per-signal counts of the recorded actions that feed the engagement
        # score (web visits, email opens/clicks, direct onboarding enquiries,
        # trial activity) — cheap bulk approximations of _engagement()'s own
        # attribution, for the All Clubs action sub-filter.
        "engagement_actions": engagement_actions or {},
    }


# Sync run kinds that count as "a full sync" for the All Clubs newly-registered
# / sync-activity filters — the weekly/on-demand Sync Now and Full Rebuild, not
# the low-value per-player deep sync.
_FULL_SYNC_KINDS = ("org_full", "org_hard_refresh")


@router.get("/super/clubs")
async def list_all_clubs(
    include_archived: bool = False,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    q = select(Organisation).options(selectinload(Organisation.module_subscriptions))
    if not include_archived:
        q = q.where(Organisation.archived_at.is_(None))
    result = await db.execute(q.order_by(Organisation.name))
    orgs = result.scalars().all()
    org_ids = [o.id for o in orgs]

    assoc_by_org: dict = {}
    club_state_by_org: dict = {}
    admin_by_org: dict = {}
    seasons_by_org: dict = {}
    players_by_org: dict = {}
    grades_by_org: dict = {}
    wizard_state_by_org: dict = {}
    last_active_by_org: dict = {}
    last_sync_by_org: dict = {}
    running_by_org: set = set()
    paused_by_org: dict = {}  # org_id -> kind, for the run currently paused
    active_kind_by_org: dict = {}  # org_id -> kind, for the run currently running or paused

    engagement_by_org: dict = {}       # org_id -> (score, tier, scored_at)
    mc_trial_signal_by_org: dict = {}  # org_id -> True when the marketing row carries trial interest
    web_count_by_org: dict = {}
    email_count_by_org: dict = {}
    enquiry_count_by_org: dict = {}

    if org_ids:
        assoc_rows = await db.execute(
            select(MarketingClub.existing_org_id, MarketingClub.association_name,
                   MarketingClub.state, MarketingClub.engagement_score,
                   MarketingClub.engagement_tier, MarketingClub.engagement_scored_at,
                   MarketingClub.requested_trial_modules, MarketingClub.trial_modules,
                   MarketingClub.demo_status)
            .where(MarketingClub.existing_org_id.in_(org_ids))
        )
        for org_id, assoc_name, mc_state, eng_score, eng_tier, eng_at, req_mods, tri_mods, demo in assoc_rows.all():
            if assoc_name:
                assoc_by_org[org_id] = assoc_name
            if mc_state:
                club_state_by_org[org_id] = mc_state
            # More than one marketing row can point at the same org; keep the
            # first row that actually holds a cached score.
            if eng_score is not None and org_id not in engagement_by_org:
                engagement_by_org[org_id] = (eng_score, eng_tier, eng_at)
            if (req_mods or tri_mods or (demo or "") == "in_trial"):
                mc_trial_signal_by_org[org_id] = True

        admin_rows = await db.execute(
            select(ClubMembership.club_id, User.display_name, User.username)
            .join(User, User.id == ClubMembership.user_id)
            .where(ClubMembership.club_id.in_(org_ids), ClubMembership.is_primary_admin.is_(True))
        )
        admin_by_org = {row[0]: (row[1] or row[2]) for row in admin_rows.all()}

        seasons_rows = await db.execute(
            select(Season.organisation_id, func.count(Season.id))
            .where(Season.organisation_id.in_(org_ids))
            .group_by(Season.organisation_id)
        )
        seasons_by_org = {row[0]: row[1] for row in seasons_rows.all()}

        players_rows = await db.execute(
            select(Player.organisation_id, func.count(Player.id))
            .where(Player.organisation_id.in_(org_ids))
            .group_by(Player.organisation_id)
        )
        players_by_org = {row[0]: row[1] for row in players_rows.all()}

        grades_rows = await db.execute(
            select(Season.organisation_id, func.count(Grade.id))
            .select_from(Grade)
            .join(Season, Season.id == Grade.season_id)
            .where(Season.organisation_id.in_(org_ids))
            .group_by(Season.organisation_id)
        )
        grades_by_org = {row[0]: row[1] for row in grades_rows.all()}

        wizard_state_rows = await db.execute(
            select(OnboardingWizardState).where(OnboardingWizardState.organisation_id.in_(org_ids))
        )
        wizard_state_by_org = {s.organisation_id: s for s in wizard_state_rows.scalars().all()}

        sync_agg_rows = await db.execute(
            select(
                SyncRun.org_id,
                func.max(SyncRun.started_at).label("last_started"),
                func.bool_or(SyncRun.status == "running").label("running"),
            )
            .where(SyncRun.org_id.in_(org_ids), SyncRun.kind.in_(_FULL_SYNC_KINDS))
            .group_by(SyncRun.org_id)
        )
        for row in sync_agg_rows.all():
            last_sync_by_org[row.org_id] = row.last_started
            if row.running:
                running_by_org.add(row.org_id)

        # Most recent RUNNING-or-PAUSED full-sync run per org, if any —
        # separate from the aggregate above (which only computes last_started
        # / bool_or across every status), so the page can show Pause/Cancel
        # for a live run, or Continue Sync for a paused one, and label either
        # with the right kind (Sync Now vs Full Rebuild). Small result set
        # (at most one live+one paused row per org, given the per-org run
        # locks), so resolving "most recent per org" in Python is simpler
        # than a window function.
        active_rows = await db.execute(
            select(SyncRun.org_id, SyncRun.kind, SyncRun.status, SyncRun.started_at)
            .where(
                SyncRun.org_id.in_(org_ids),
                SyncRun.kind.in_(_FULL_SYNC_KINDS),
                SyncRun.status.in_(("running", "paused")),
            )
            .order_by(SyncRun.started_at.desc())
        )
        for row in active_rows.all():
            active_kind_by_org.setdefault(row.org_id, row.kind)
            if row.status == "paused":
                paused_by_org.setdefault(row.org_id, row.kind)

        usage_rows = await db.execute(
            _text(
                "SELECT org_id, MAX(created_at) AS last_at, COUNT(*) AS cnt FROM usage_events "
                "WHERE org_id = ANY(:ids) AND created_at >= NOW() - INTERVAL '180 days' "
                "GROUP BY org_id"
            ),
            {"ids": org_ids},
        )
        for row in usage_rows.all():
            last_active_by_org[row.org_id] = row.last_at
            web_count_by_org[row.org_id] = row.cnt

        # The three engagement-action counts below are cheap bulk versions of
        # the per-club signals twenty_sync._engagement() attributes when it
        # computes the (cached) score this page also returns — org-keyed web
        # activity above, email opens/clicks, and direct "onboard my club"
        # enquiries. They drive the All Clubs "actions recorded" sub-filter,
        # so has/hasn't matters more than exact parity with the score's own
        # (heavier, UTM-aware) attribution.
        email_rows = await db.execute(
            _text("""
                SELECT org_id, SUM(cnt) AS cnt FROM (
                    SELECT organisation_id AS org_id, COUNT(*) AS cnt
                    FROM email_events
                    WHERE organisation_id = ANY(:ids) AND event_type IN ('open', 'click')
                    GROUP BY organisation_id
                    UNION ALL
                    SELECT mc.existing_org_id AS org_id, COUNT(*) AS cnt
                    FROM email_events ee
                    JOIN marketing_club_contacts mcc
                      ON mcc.email IS NOT NULL AND mcc.email <> ''
                     AND ee.email IS NOT NULL AND lower(mcc.email) = lower(ee.email)
                    JOIN marketing_clubs mc ON mc.id = mcc.marketing_club_id
                    WHERE mc.existing_org_id = ANY(:ids) AND ee.event_type IN ('open', 'click')
                    GROUP BY mc.existing_org_id
                ) t GROUP BY org_id
            """),
            {"ids": org_ids},
        )
        email_count_by_org = {row.org_id: int(row.cnt or 0) for row in email_rows.all()}

        # Direct enquiries (club_onboarding_requests) attributed the same two
        # ways _onboarding_signal() leads with: the submitter's email matching a
        # known officer of the linked marketing club, or an exact club-name
        # match (against the marketing club's or the org's own name). The inner
        # UNION dedupes on (org, enquiry) so a name that matches both branches
        # counts once.
        enquiry_rows = await db.execute(
            _text("""
                SELECT org_id, COUNT(*) AS cnt FROM (
                    SELECT mc.existing_org_id AS org_id, cor.id AS enquiry_id
                    FROM club_onboarding_requests cor
                    JOIN marketing_clubs mc
                      ON mc.existing_org_id = ANY(:ids)
                     AND (lower(cor.club) = lower(mc.name)
                          OR (cor.email IS NOT NULL AND cor.email <> '' AND EXISTS (
                                SELECT 1 FROM marketing_club_contacts mcc
                                WHERE mcc.marketing_club_id = mc.id
                                  AND mcc.email IS NOT NULL AND mcc.email <> ''
                                  AND lower(mcc.email) = lower(cor.email))))
                    UNION
                    SELECT o.id AS org_id, cor.id AS enquiry_id
                    FROM club_onboarding_requests cor
                    JOIN organisations o
                      ON o.id = ANY(:ids) AND lower(cor.club) = lower(o.name)
                ) t GROUP BY org_id
            """),
            {"ids": org_ids},
        )
        enquiry_count_by_org = {row.org_id: int(row.cnt or 0) for row in enquiry_rows.all()}

    from app.routers.onboarding_wizard import _applicable_groups

    payloads = []
    for o in orgs:
        entitled = org_entitled_modules(o)
        keys = [s["key"] for g in _applicable_groups(entitled) for s in g["steps"]]
        wiz_state = wizard_state_by_org.get(o.id)
        completed = set((wiz_state.completed_steps or []) if wiz_state else [])
        done_n = sum(1 for k in keys if k in completed)
        eng = engagement_by_org.get(o.id)
        # Trial activity: real per-module trial subscriptions (current or past —
        # trial_started_at survives a conversion), else the marketing row's
        # trial-interest flags count as one recorded action.
        trial_subs = sum(
            1 for s in (o.module_subscriptions or [])
            if s.status == "trial" or s.trial_started_at is not None
        )
        trial_activity = trial_subs or (1 if mc_trial_signal_by_org.get(o.id) else 0)
        payloads.append(_club_payload(
            o,
            association_name=assoc_by_org.get(o.id),
            primary_admin_name=admin_by_org.get(o.id),
            state=club_state_by_org.get(o.id),
            seasons_count=seasons_by_org.get(o.id, 0),
            players_count=players_by_org.get(o.id, 0),
            grades_count=grades_by_org.get(o.id, 0),
            onboarding_done=done_n,
            onboarding_total=len(keys),
            last_active_at=last_active_by_org.get(o.id),
            last_full_sync_at=last_sync_by_org.get(o.id),
            full_sync_running=o.id in running_by_org,
            full_sync_paused=o.id in paused_by_org,
            full_sync_kind=active_kind_by_org.get(o.id),
            engagement_score=eng[0] if eng else None,
            engagement_tier=eng[1] if eng else None,
            engagement_scored_at=eng[2] if eng else None,
            engagement_actions={
                "web_visits": int(web_count_by_org.get(o.id, 0)),
                "email_engagement": email_count_by_org.get(o.id, 0),
                "direct_enquiry": enquiry_count_by_org.get(o.id, 0),
                "trial_activity": trial_activity,
            },
        ))
    return payloads


class SyncControlRequest(BaseModel):
    action: str  # "pause" | "cancel" | "continue"


@router.post("/super/clubs/{club_id}/sync-control")
async def super_club_sync_control(
    club_id: str,
    body: SyncControlRequest,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Pause Sync / Cancel Sync / Continue Sync for a club's current Full
    Sync — the All Clubs "Full sync activity" row actions. The target run is
    resolved server-side from the club's most recent running-or-paused
    org_full/org_hard_refresh row (the per-org run locks mean there's never
    more than one), so the client only ever needs to say which club + which
    action, not track a run id itself.

    Pause/Cancel a RUNNING sync are cooperative — they set sync_runs.control
    and wait for the run's own loop checkpoint (services/sync.py's
    _check_sync_control) to notice, typically within a season or a few dozen
    games. Cancelling an already-PAUSED sync is immediate (nothing is
    running to signal). Continue starts a brand new incremental sync — safe
    even for a paused Full Rebuild, since its wipe phase already committed
    before the pause took effect; see pause_sync_run's docstring."""
    from app.services.sync import (
        request_sync_control, cancel_sync_run, start_sync_run,
    )

    action = (body.action or "").strip().lower()
    if action not in ("pause", "cancel", "continue"):
        raise HTTPException(status_code=422, detail="action must be 'pause', 'cancel' or 'continue'")

    club = await db.get(Organisation, uuid.UUID(club_id))
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")

    run = (await db.execute(
        select(SyncRun)
        .where(
            SyncRun.org_id == club.id,
            SyncRun.kind.in_(_FULL_SYNC_KINDS),
            SyncRun.status.in_(("running", "paused")),
        )
        .order_by(SyncRun.started_at.desc())
        .limit(1)
    )).scalar_one_or_none()

    if action == "pause":
        if not run or run.status != "running":
            raise HTTPException(status_code=409, detail="No running sync to pause")
        await request_sync_control(run.id, "pause")
        return {"status": "pause_requested", "run_id": str(run.id)}

    if action == "cancel":
        if not run:
            raise HTTPException(status_code=409, detail="No running or paused sync to cancel")
        if run.status == "running":
            await request_sync_control(run.id, "cancel")
            return {"status": "cancel_requested", "run_id": str(run.id)}
        await cancel_sync_run(run.id, {})
        return {"status": "cancelled", "run_id": str(run.id)}

    # continue
    if not run or run.status != "paused":
        raise HTTPException(status_code=409, detail="No paused sync to continue")
    from app.routers.organisations import _org_sync_running, _sync_safe
    if club_id in _org_sync_running or club_id in _hard_refresh_running:
        return {"status": "already_running", "org_id": club_id}
    new_run_id = await start_sync_run(club.id, "org_full")
    _org_sync_running.add(club_id)
    task = asyncio.create_task(_sync_safe(club_id, new_run_id, "org_full"))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return {"status": "sync_started", "org_id": club_id, "run_id": str(new_run_id)}


# ─── Global platform settings (super-admin General Settings) ──────────────────

@router.get("/super/general-settings")
async def get_general_settings(
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Platform-wide settings managed from the All Clubs page. Returns the resolved
    values the UI edits."""
    from app.services import platform_settings as ps
    return {
        "default_trial_days": await ps.get_default_trial_days(db),
        "direct_enquiry_hot_days": await ps.get_direct_enquiry_hot_days(db),
        "self_serve_registration_enabled": await ps.get_self_serve_registration_enabled(db),
        "onboarding_wizard_enabled": await ps.get_onboarding_wizard_enabled(db),
        "trial_nudges_enabled": await ps.get_trial_nudges_enabled(db),
        "billing_checkout_enabled": await ps.get_billing_checkout_enabled(db),
        "member_portal_enabled": await ps.get_member_portal_enabled(db),
        "merch_storefront_enabled": await ps.get_merch_storefront_enabled(db),
        "bundle_discount_schedule": await ps.get_bundle_discount_schedule(db),
        "backup_schedule": await ps.get_backup_schedule(db),
    }


class GeneralSettingsUpdate(BaseModel):
    default_trial_days: Optional[int] = None
    direct_enquiry_hot_days: Optional[int] = None
    self_serve_registration_enabled: Optional[bool] = None
    onboarding_wizard_enabled: Optional[bool] = None
    trial_nudges_enabled: Optional[bool] = None
    billing_checkout_enabled: Optional[bool] = None
    # Member self-service portal + Stripe Connect fee payments + reminder
    # automation (migration 178) — off by default; per direct instruction,
    # invisible to every club admin and unusable by any real member until a
    # super admin switches it on (globally, or per-club first via
    # ClubUpdate.member_portal_override below).
    member_portal_enabled: Optional[bool] = None
    # Merch storefront (migration 179) — same off-by-default, super-admin-only
    # posture as member_portal_enabled above.
    merch_storefront_enabled: Optional[bool] = None
    # module-count (str or int, JSON-friendly either way) -> whole-dollar
    # discount. See platform_settings.update_bundle_discount_schedule — this
    # REPLACES the whole table, it's not a merge.
    bundle_discount_schedule: Optional[dict] = None
    # Daily automated backup — read by the host backup script on every timer
    # tick (see ops/backup/backup.sh), not enforced by anything in-process.
    backup_hour: Optional[int] = None
    backup_minute: Optional[int] = None
    backup_retention_days: Optional[int] = None


@router.patch("/super/general-settings")
async def patch_general_settings(
    body: GeneralSettingsUpdate,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.services import platform_settings as ps
    patch = body.model_dump(exclude_unset=True)
    schedule = patch.pop("bundle_discount_schedule", None)
    backup_hour = patch.pop("backup_hour", None)
    backup_minute = patch.pop("backup_minute", None)
    backup_retention_days = patch.pop("backup_retention_days", None)
    try:
        await ps.update_settings(db, patch)
        if schedule is not None:
            await ps.update_bundle_discount_schedule(db, schedule)
        if backup_hour is not None or backup_minute is not None or backup_retention_days is not None:
            await ps.update_backup_schedule(
                db, hour=backup_hour, minute=backup_minute, retention_days=backup_retention_days,
            )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {
        "default_trial_days": await ps.get_default_trial_days(db),
        "direct_enquiry_hot_days": await ps.get_direct_enquiry_hot_days(db),
        "self_serve_registration_enabled": await ps.get_self_serve_registration_enabled(db),
        "onboarding_wizard_enabled": await ps.get_onboarding_wizard_enabled(db),
        "trial_nudges_enabled": await ps.get_trial_nudges_enabled(db),
        "billing_checkout_enabled": await ps.get_billing_checkout_enabled(db),
        "member_portal_enabled": await ps.get_member_portal_enabled(db),
        "merch_storefront_enabled": await ps.get_merch_storefront_enabled(db),
        "bundle_discount_schedule": await ps.get_bundle_discount_schedule(db),
        "backup_schedule": await ps.get_backup_schedule(db),
    }


@router.post("/super/clubs", status_code=201)
async def create_club(
    data: ClubCreate,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    # The org id IS the sync key — it must be the real Cricket Australia club
    # GUID (picked from search), otherwise sync resolves to nothing.
    try:
        org_uuid = uuid.UUID((data.org_id or "").strip())
    except ValueError:
        raise HTTPException(status_code=422, detail="Pick a club from the search results")

    org_data = await playhq_client.get_organisation(str(org_uuid))
    if not org_data:
        raise HTTPException(status_code=404, detail="Club not found in the Cricket Australia data source")

    if await db.get(Organisation, org_uuid):
        raise HTTPException(status_code=409, detail="This club has already been added")

    slug = data.slug.lower().strip()
    existing = await db.execute(select(Organisation).where(Organisation.slug == slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Slug already in use")

    org = Organisation(
        id=org_uuid,
        name=data.name.strip(),
        slug=slug,
        short_name=data.short_name,
        contact_email=data.contact_email,
        primary_color=data.primary_color,
        accent_color=data.accent_color,
        is_active=False,
    )
    db.add(org)
    # Append the Core subscription while `org` is still pending: accessing the
    # collection now initialises it empty (no SQL). Doing it after a flush would
    # lazy-load the unloaded collection on a now-persistent row, which raises
    # MissingGreenlet on the async session (the 500 on club create). `org.id` is
    # set explicitly above, so the subscription's FK is valid; the cascade inserts
    # both rows on commit.
    mod_subs.ensure_core_subscription(org)  # Core tracked from day one
    await db.commit()
    # Provision the club's SES tenant in the background (best-effort, no-op when
    # tenant provisioning isn't configured). Never blocks club creation.
    from app.services import ses_tenants
    asyncio.create_task(ses_tenants.ensure_tenant_bg(org.id))
    return {"id": str(org.id), "slug": org.slug, "name": org.name}


class ClubUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    short_name: Optional[str] = None
    contact_email: Optional[str] = None
    primary_color: Optional[str] = None
    accent_color: Optional[str] = None
    is_active: Optional[bool] = None
    module_overrides: Optional[list[str]] = None
    subscription_status: Optional[str] = None
    renewal_date: Optional[_date] = None
    billing_cycle: Optional[str] = None
    # Per-club override of platform_settings.billing_checkout_enabled
    # (migration 151). None/omitted = leave as-is; explicit null in the
    # request body clears it back to "follow the platform default" (see
    # patch_club below — Pydantic's exclude_unset distinguishes "not sent"
    # from "sent as null").
    billing_checkout_override: Optional[bool] = None
    # Per-club override of platform_settings.member_portal_enabled (migration
    # 178) — same None/omitted-vs-explicit-null semantics as
    # billing_checkout_override above.
    member_portal_override: Optional[bool] = None
    # Per-club override of platform_settings.merch_storefront_enabled
    # (migration 179) — same shape as member_portal_override above.
    merch_storefront_override: Optional[bool] = None
    # Club General Settings — the configurable default trial length (days).
    default_trial_days: Optional[int] = None
    # BetterComms sending tier + optional per-club daily-cap overrides per tier.
    comms_tier: Optional[str] = None
    comms_sandbox_cap: Optional[int] = None
    comms_production_cap: Optional[int] = None
    comms_monthly_cap: Optional[int] = None


@router.patch("/super/clubs/{club_id}")
async def patch_club(
    club_id: str,
    data: ClubUpdate,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    org = await db.get(
        Organisation, uuid.UUID(club_id),
        options=[selectinload(Organisation.module_subscriptions)],
    )
    if not org:
        raise HTTPException(status_code=404, detail="Club not found")

    fields = data.model_dump(exclude_unset=True)

    if "slug" in fields:
        slug = (fields["slug"] or "").lower().strip()
        if not slug:
            raise HTTPException(status_code=422, detail="Slug cannot be empty")
        clash = await db.execute(
            select(Organisation).where(Organisation.slug == slug, Organisation.id != org.id)
        )
        if clash.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Slug already in use")
        fields["slug"] = slug

    if "name" in fields:
        name = (fields["name"] or "").strip()
        if not name:
            raise HTTPException(status_code=422, detail="Name cannot be empty")
        fields["name"] = name

    if "subscription_status" in fields:
        if fields["subscription_status"] not in ALL_STATUSES:
            raise HTTPException(status_code=422, detail=f"Status must be one of: {', '.join(ALL_STATUSES)}")

    if fields.get("billing_cycle") is not None and fields["billing_cycle"] not in ALL_BILLING_CYCLES:
        raise HTTPException(status_code=422, detail=f"Billing cycle must be one of: {', '.join(ALL_BILLING_CYCLES)}")

    if "comms_tier" in fields and fields["comms_tier"] is not None:
        if fields["comms_tier"] not in comms_limits.TIERS:
            raise HTTPException(status_code=422,
                                detail=f"Comms tier must be one of: {', '.join(comms_limits.TIERS)}")
    for cap_field in ("comms_sandbox_cap", "comms_production_cap", "comms_monthly_cap"):
        if fields.get(cap_field) is not None and int(fields[cap_field]) < 0:
            raise HTTPException(status_code=422, detail=f"{cap_field} must be >= 0")

    # Club General Settings (default_trial_days) lives in the general_settings blob,
    # not a column — merge it in rather than setattr.
    if "default_trial_days" in fields:
        days = fields.pop("default_trial_days")
        if days is not None and (not isinstance(days, int) or days <= 0):
            raise HTTPException(status_code=422, detail="default_trial_days must be a positive integer")
        gs = dict(org.general_settings or {})
        if days is None:
            gs.pop("default_trial_days", None)
        else:
            gs["default_trial_days"] = days
        org.general_settings = gs

    # The module-toggle UI sends module_overrides; reconcile it through the
    # per-module table (add an active row for each newly-granted module, drop the
    # row for each removed one) so the rows stay the source of truth.
    if "module_overrides" in fields:
        overrides = fields.pop("module_overrides") or []
        unknown = [m for m in overrides if m not in ALL_MODULES]
        if unknown:
            raise HTTPException(status_code=422, detail=f"Unknown modules: {', '.join(unknown)}")
        mod_subs.reconcile_held_modules(org, sorted(set(overrides)))

    for key, value in fields.items():
        setattr(org, key, value)

    await db.commit()
    await db.refresh(org, attribute_names=["module_subscriptions"])
    return _club_payload(org)


# ─── BetterComms sending-tier requests (super admin) ──────────────────────────

async def _comms_request_out(db: AsyncSession, r: CommsLimitRequest, org: Organisation) -> dict:
    """A tier request enriched with the club's live deliverability + current tier,
    so the super admin can judge the ask on the same screen."""
    metrics = await comms_limits.deliverability_metrics(db, org.id)
    return {
        "id": str(r.id),
        "organisation_id": str(org.id),
        "club_name": org.name,
        "club_slug": org.slug,
        "current_tier": getattr(org, "comms_tier", None) or "sandbox",
        "requested_tier": r.requested_tier,
        "requested_cap": r.requested_cap,
        "reason": r.reason,
        "status": r.status,
        "requested_at": r.requested_at.isoformat() if r.requested_at else None,
        "decided_at": r.decided_at.isoformat() if r.decided_at else None,
        "decision_note": r.decision_note,
        "metrics": metrics,
        "breaker_reason": comms_limits.breaker_reason(metrics),
    }


@router.get("/super/comms/requests")
async def list_comms_requests(
    status: str = "pending",
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(CommsLimitRequest, Organisation).join(
        Organisation, Organisation.id == CommsLimitRequest.organisation_id)
    if status and status != "all":
        stmt = stmt.where(CommsLimitRequest.status == status)
    stmt = stmt.order_by(CommsLimitRequest.requested_at.desc()).limit(200)
    rows = (await db.execute(stmt)).all()
    return [await _comms_request_out(db, r, org) for r, org in rows]


class CommsRequestDecision(BaseModel):
    daily_limit: Optional[int] = None   # optional explicit cap on approve
    note: Optional[str] = None


@router.post("/super/comms/requests/{request_id}/approve")
async def approve_comms_request(
    request_id: str,
    data: CommsRequestDecision,
    user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Approve a tier lift: move the club to production (with an optional explicit
    daily cap) and close the request."""
    req = await db.get(CommsLimitRequest, uuid.UUID(request_id))
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != "pending":
        raise HTTPException(status_code=409, detail=f"Request already {req.status}")
    org = await db.get(Organisation, req.organisation_id)
    if not org:
        raise HTTPException(status_code=404, detail="Club not found")
    org.comms_tier = comms_limits.TIER_PRODUCTION
    # An explicit approved cap becomes this club's production-tier override.
    cap = data.daily_limit if data.daily_limit is not None else req.requested_cap
    if cap is not None:
        org.comms_production_cap = max(0, int(cap))
    req.status = "approved"
    req.decided_by = user.id
    req.decided_at = _datetime.now(_timezone.utc)
    req.decision_note = (data.note or "").strip() or None
    await db.commit()
    return {"status": "approved", "comms_tier": org.comms_tier,
            "comms_production_cap": org.comms_production_cap}


@router.post("/super/comms/requests/{request_id}/deny")
async def deny_comms_request(
    request_id: str,
    data: CommsRequestDecision,
    user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    req = await db.get(CommsLimitRequest, uuid.UUID(request_id))
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != "pending":
        raise HTTPException(status_code=409, detail=f"Request already {req.status}")
    req.status = "denied"
    req.decided_by = user.id
    req.decided_at = _datetime.now(_timezone.utc)
    req.decision_note = (data.note or "").strip() or None
    await db.commit()
    return {"status": "denied"}


@router.post("/super/clubs/{club_id}/comms/reinstate")
async def reinstate_comms(
    club_id: str,
    data: CommsRequestDecision,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Lift a suspension (breaker trip): move the club back to production sending.
    The metrics that tripped it stay in history; the super admin owns the call."""
    org = await db.get(Organisation, uuid.UUID(club_id))
    if not org:
        raise HTTPException(status_code=404, detail="Club not found")
    org.comms_tier = comms_limits.TIER_PRODUCTION
    await db.commit()
    return {"status": "ok", "comms_tier": org.comms_tier}


@router.get("/super/comms/rates")
async def get_comms_rates(
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """The live AWS per-second ceiling + our pacing rate, plus the per-club tier
    defaults (all super-admin managed)."""
    from app.services import platform_settings as ps
    rates = await ps.get_ses_rates(db)
    tier_defaults = await ps.get_comms_tier_defaults(db)
    return {**rates, "tier_defaults": tier_defaults}


class CommsRatesIn(BaseModel):
    aws_max_send_rate: Optional[int] = None   # AWS's granted per-second ceiling
    send_rate: Optional[int] = None           # our pacing rate (must stay < ceiling)
    aws_daily_quota: Optional[int] = None      # AWS's granted daily ceiling
    daily_send_limit: Optional[int] = None     # our practical daily max (≤ AWS daily)
    # Per-club tier defaults (used when a club has no own override).
    sandbox_daily_default: Optional[int] = None
    production_daily_default: Optional[int] = None
    monthly_default: Optional[int] = None


@router.patch("/super/comms/rates")
async def update_comms_rates(
    data: CommsRatesIn,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Set the AWS ceilings, our practical limits, and/or the per-club tier
    defaults. Our send rate must stay strictly below the AWS per-second ceiling,
    and our daily limit at or below the AWS daily ceiling — the update is rejected
    otherwise."""
    from app.services import platform_settings as ps
    try:
        rates = await ps.update_ses_rates(
            db, aws_max_send_rate=data.aws_max_send_rate, send_rate=data.send_rate,
            aws_daily_quota=data.aws_daily_quota, daily_send_limit=data.daily_send_limit)
        tier_defaults = await ps.update_comms_tier_defaults(
            db, sandbox_daily=data.sandbox_daily_default,
            production_daily=data.production_daily_default, monthly=data.monthly_default)
        return {**rates, "tier_defaults": tier_defaults}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ─── Per-module subscription management (super admin) ─────────────────────────

async def _load_club_with_subs(db: AsyncSession, club_id: str) -> Organisation:
    org = await db.get(
        Organisation, uuid.UUID(club_id),
        options=[selectinload(Organisation.module_subscriptions)],
    )
    if not org:
        raise HTTPException(status_code=404, detail="Club not found")
    return org


def _validate_module(module_key: str) -> None:
    """Validate a billable module key (BetterAdmin = admin, not its members)."""
    if module_key not in BILLABLE_MODULES:
        raise HTTPException(status_code=422, detail=f"Unknown module: {module_key}")


class TrialStart(BaseModel):
    # All optional: start defaults to now, end to start + days, days to the club's
    # Club General Settings default_trial_days.
    start: Optional[_datetime] = None
    end: Optional[_datetime] = None
    days: Optional[int] = None


@router.post("/super/clubs/{club_id}/modules/{module_key}/trial")
async def start_module_trial(
    club_id: str,
    module_key: str,
    body: TrialStart,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Start (or restart) a trial for one module. Prefills start = now and
    end = start + the club's default trial length unless overridden."""
    _validate_module(module_key)
    org = await _load_club_with_subs(db, club_id)
    if body.days is not None and body.days <= 0:
        raise HTTPException(status_code=422, detail="days must be a positive integer")
    if body.start and body.end and body.end <= body.start:
        raise HTTPException(status_code=422, detail="Trial end must be after the start")
    # Use the global default trial length unless the caller overrides days/end.
    from app.services import platform_settings as ps
    days = body.days or await ps.get_default_trial_days(db)
    mod_subs.start_trial_billing(org, module_key, start=body.start, end=body.end, days=days)
    await db.commit()
    await db.refresh(org, attribute_names=["module_subscriptions"])
    # A new trial is a strong engagement signal (see twenty_sync._engagement's
    # per-module upsell calc) — push it to Twenty now rather than waiting for the
    # nightly refresh, same as the approve_module_request path below. force_hot
    # forces the score to 100 and upserts a Lead rather than waiting for the
    # gradual formula to notice.
    _push_club_to_twenty(org.id, force_hot=True)
    return _club_payload(org)


class ModuleUpdate(BaseModel):
    status: Optional[str] = None
    renewal_date: Optional[_date] = None
    trial_ends_at: Optional[_datetime] = None


@router.patch("/super/clubs/{club_id}/modules/{module_key}")
async def patch_module_subscription(
    club_id: str,
    module_key: str,
    body: ModuleUpdate,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Change one module's status (e.g. convert a trial to active, pause, cancel)
    and/or its renewal date, or extend a trial's end."""
    _validate_module(module_key)
    org = await _load_club_with_subs(db, club_id)
    fields = body.model_dump(exclude_unset=True)
    if "status" in fields and fields["status"] not in ALL_STATUSES:
        raise HTTPException(status_code=422, detail=f"Status must be one of: {', '.join(ALL_STATUSES)}")
    now = _datetime.now(_timezone.utc)
    # Apply to every member of the billable module (BetterAdmin moves as one).
    if "status" in fields:
        mod_subs.set_status_billing(
            org, module_key, fields["status"],
            renewal_date=fields["renewal_date"] if "renewal_date" in fields else ...,
            now=now,
        )
    elif "renewal_date" in fields:
        mod_subs.set_status_billing(
            org, module_key,
            next((s.status for s in (org.module_subscriptions or [])
                  if billing_key_for(s.module_key) == module_key), "active"),
            renewal_date=fields["renewal_date"], now=now,
        )
    if "trial_ends_at" in fields:
        mod_subs.set_trial_end_billing(org, module_key, fields["trial_ends_at"], now=now)
    await db.commit()
    await db.refresh(org, attribute_names=["module_subscriptions"])
    return _club_payload(org)


@router.delete("/super/clubs/{club_id}/modules/{module_key}")
async def remove_module_subscription(
    club_id: str,
    module_key: str,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Drop a module entirely (delete its subscription row(s))."""
    _validate_module(module_key)
    org = await _load_club_with_subs(db, club_id)
    if not mod_subs.remove_billing(org, module_key):
        raise HTTPException(status_code=404, detail="Module not held by this club")
    await db.commit()
    await db.refresh(org, attribute_names=["module_subscriptions"])
    return _club_payload(org)


# ─── Primary / owner admin reassignment ──────────────────────────────────────

@router.get("/super/clubs/{club_id}/admins")
async def list_club_admins(
    club_id: str,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """The club's admins (for the primary-admin picker), primary flagged."""
    rows = (await db.execute(
        select(ClubMembership, User)
        .join(User, User.id == ClubMembership.user_id)
        .where(ClubMembership.club_id == uuid.UUID(club_id), ClubMembership.role == "club_admin")
        .order_by(ClubMembership.is_primary_admin.desc(), ClubMembership.created_at.asc())
    )).all()
    return [
        {
            "user_id": str(u.id),
            "username": u.username,
            "display_name": u.display_name,
            "is_primary_admin": bool(m.is_primary_admin),
        }
        for m, u in rows
    ]


class PrimaryAdminSet(BaseModel):
    user_id: str


@router.put("/super/clubs/{club_id}/primary-admin")
async def super_set_primary_admin(
    club_id: str,
    body: PrimaryAdminSet,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Super admin assigns a club's primary/owner admin."""
    from app.services.memberships import set_primary_admin
    try:
        await set_primary_admin(db, uuid.UUID(club_id), uuid.UUID(body.user_id))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"ok": True}


@router.get("/primary-admin")
async def get_primary_admin_info(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """The club's admins and whether the caller may reassign the primary admin.
    Drives the club-side 'transfer primary admin' control."""
    me = (await db.execute(
        select(ClubMembership).where(ClubMembership.user_id == current_user.id)
    )).scalar_one_or_none()
    is_super = bool(me and me.role == "super_admin")
    if not is_super and not (me and me.club_id == club.id and me.role == "club_admin"):
        raise HTTPException(status_code=403, detail="Club admins only")
    rows = (await db.execute(
        select(ClubMembership, User)
        .join(User, User.id == ClubMembership.user_id)
        .where(ClubMembership.club_id == club.id, ClubMembership.role == "club_admin")
        .order_by(ClubMembership.is_primary_admin.desc(), ClubMembership.created_at.asc())
    )).all()
    return {
        "can_transfer": bool(is_super or (me and me.is_primary_admin and me.club_id == club.id)),
        "admins": [
            {
                "user_id": str(u.id),
                "username": u.username,
                "display_name": u.display_name,
                "is_primary_admin": bool(m.is_primary_admin),
                "is_me": u.id == current_user.id,
            }
            for m, u in rows
        ],
    }


@router.post("/primary-admin/transfer")
async def transfer_primary_admin(
    body: PrimaryAdminSet,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """The current primary admin hands the role to another club_admin in their club."""
    m = (await db.execute(
        select(ClubMembership).where(ClubMembership.user_id == current_user.id)
    )).scalar_one_or_none()
    is_super = bool(m and m.role == "super_admin")
    if not is_super and not (m and m.club_id == club.id and m.is_primary_admin):
        raise HTTPException(status_code=403, detail="Only the club's primary admin can transfer this")
    from app.services.memberships import set_primary_admin
    try:
        await set_primary_admin(db, club.id, uuid.UUID(body.user_id))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"ok": True}


# ─── Account / plan status (Phase 19) ──────────────────────────────────────────

@router.get("/account/plan")
async def get_account_plan(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """The club's own Account page: per-module status (Subscribed / In Trial /
    Trial Expired / Never Trialed) plus whether starting a trial or requesting
    a subscription is currently a valid action — the self-serve mirror of the
    Super Admin module editor, over the same org_module_subscriptions data.
    ``is_primary_admin`` lets the frontend explain why Subscribe is disabled
    for a non-primary admin (create_module_request enforces the same rule
    server-side regardless — this is purely so the button doesn't look broken).
    ``billing_checkout_enabled`` gates the in-progress invoicing / Stripe
    checkout build — see platform_settings.billing_checkout_enabled_for_org
    (the platform default, unless this specific club has its own override)
    and the comment on submitSubscribe in AdminAccount.jsx."""
    from app.auth.modules import account_plan_status
    from app.services import platform_settings as ps

    m = (await db.execute(
        select(ClubMembership).where(ClubMembership.user_id == current_user.id)
    )).scalar_one_or_none()
    is_primary_admin = bool(m and (m.role == "super_admin" or m.is_primary_admin))

    outstanding = (await db.execute(
        select(ModuleActionRequest).where(
            ModuleActionRequest.organisation_id == club.id,
            ModuleActionRequest.status == "outstanding",
        )
    )).scalars().all()
    pending_by_module: dict[str, list[str]] = {}
    for r in outstanding:
        pending_by_module.setdefault(r.module_key, []).append(r.kind)

    modules = account_plan_status(club)
    for row in modules:
        row["pending_requests"] = sorted(pending_by_module.get(row["module"], []))

    return {
        "modules": modules,
        "is_primary_admin": is_primary_admin,
        "billing_checkout_enabled": await ps.billing_checkout_enabled_for_org(db, club),
        # Drives the "redeem a discount code ahead of your renewal" box on
        # the Account page — see routers/discount_coupons.py's /redeem.
        "stripe_subscription_active": bool(club.stripe_subscription_id),
        # Drives the Payment Methods panel — a club with no Stripe Customer
        # yet (never checked out) has nothing to manage there. Just a
        # presence flag, never the raw id itself.
        "stripe_customer_id": bool(club.stripe_customer_id),
    }


@router.post("/modules/{module_key}/start-trial")
async def start_own_module_trial(
    module_key: str,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Self-service instant trial start from the club's own Dashboard/Account
    page — same effect as a super admin approving a trial request
    (start_module_trial below), but skips the queue entirely. Any club_admin
    may start a trial for their own club, same authorization
    create_module_request already grants a trial request (no primary-admin
    gate — that only applies to a paid subscribe)."""
    _validate_module(module_key)
    m = (await db.execute(
        select(ClubMembership).where(ClubMembership.user_id == current_user.id)
    )).scalar_one_or_none()
    is_super = bool(m and m.role == "super_admin")
    if not is_super and not (m and m.club_id == club.id and m.role == "club_admin"):
        raise HTTPException(status_code=403, detail="Only a club admin can start a trial")

    from app.auth.modules import account_plan_status
    row = next((r for r in account_plan_status(club) if r["module"] == module_key), None)
    if row is None or not row["trial_eligible"]:
        raise HTTPException(status_code=409, detail="This module isn't eligible for a trial")

    from app.services import platform_settings as ps
    days = await ps.get_default_trial_days(db)
    mod_subs.start_trial_billing(club, module_key, days=days)
    await db.commit()
    await db.refresh(club, attribute_names=["module_subscriptions"])
    # Same signal-strength reasoning as start_module_trial / create_module_request's
    # trial branch — a trial actually starting always forces Hot(100)+Lead.
    _push_club_to_twenty(club.id, force_hot=True)
    return {"ok": True}


async def _cancel_stripe_subscription_if_nothing_held(club) -> None:
    """Call after removing a club's last held module — mod_subs.remove_billing
    is DB-only (no Stripe call), so left alone club.stripe_subscription_id
    dangles: Stripe keeps billing a subscription the app no longer shows
    anything held on, AND the Account page's checkout stays routed into the
    "add modules to an already-live subscription" branch (no coupon support)
    instead of falling back to a normal new-signup checkout. Shared by the
    self-service cancel and the super-admin cancel-request approval — both are
    real "cancel a paid subscription" actions."""
    from app.auth.modules import account_plan_status
    if any(r["status"] == "subscribed" for r in account_plan_status(club)):
        return
    if not club.stripe_subscription_id:
        return
    try:
        await stripe_client.cancel_subscription(club.stripe_subscription_id)
    except (stripe_client.StripeNotConfigured, stripe_error.InvalidRequestError):
        club.stripe_subscription_id = None  # nothing configured, or Stripe already considers it gone
    except stripe_error.StripeError:
        _logging.getLogger(__name__).exception(
            "Could not cancel Stripe subscription %s for org %s — leaving it in place for manual follow-up",
            club.stripe_subscription_id, club.id,
        )
    else:
        club.stripe_subscription_id = None


class ModuleCancelIn(BaseModel):
    confirm: str = ""


@router.post("/modules/{module_key}/cancel")
async def cancel_own_module(
    module_key: str,
    body: ModuleCancelIn,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Self-service instant cancellation from the club's own Account page.
    Unlike starting a trial, only the club's primary admin may cancel a paid
    subscription (mirrors the primary-admin gate on requesting one). Cancelling
    Core (BetterStats) cancels every currently-subscribed module for the club,
    not just Core, since Core is the base every other module depends on — the
    UI's own confirmation copy says as much. Requires the literal string
    "confirm" (case-insensitive), checked server-side too since this is an
    instant, not-reversible-from-the-club-side action."""
    _validate_module(module_key)
    if body.confirm.strip().lower() != "confirm":
        raise HTTPException(status_code=422, detail='Type "confirm" to cancel')

    m = (await db.execute(
        select(ClubMembership).where(ClubMembership.user_id == current_user.id)
    )).scalar_one_or_none()
    is_super = bool(m and m.role == "super_admin")
    if not is_super:
        if not (m and m.club_id == club.id and m.role == "club_admin" and m.is_primary_admin):
            raise HTTPException(status_code=403, detail="Only the club's primary admin can cancel a subscription")

    from app.auth.modules import account_plan_status, MODULE_CORE
    row = next((r for r in account_plan_status(club) if r["module"] == module_key), None)
    if row is None or row["status"] != "subscribed":
        raise HTTPException(status_code=409, detail="This module isn't currently subscribed")

    now = _datetime.now(_timezone.utc)
    targets = [module_key]
    if module_key == MODULE_CORE:
        targets = [r["module"] for r in account_plan_status(club) if r["status"] == "subscribed"]
    for key in targets:
        mod_subs.remove_billing(club, key, now=now)
    await _cancel_stripe_subscription_if_nothing_held(club)

    from app.services.audit_log import log_activity
    await log_activity(
        db, org_id=club.id, user_id=current_user.id,
        action="self_service_cancel_module", target_type="organisation", target_id=str(club.id),
        details={"module_key": module_key, "cancelled": targets},
    )
    await db.commit()
    await db.refresh(club, attribute_names=["module_subscriptions"])
    _push_club_to_twenty(club.id)
    return {"ok": True, "cancelled": targets}


# ─── Module action requests — the trial/subscription queue ────────────────────

_REQUEST_KINDS = ("trial", "subscribe", "cancel")


def _request_payload(r: ModuleActionRequest, *, org_name=None, requester=None, completer=None) -> dict:
    return {
        "id": str(r.id),
        "organisation_id": str(r.organisation_id),
        "club_name": org_name,
        "module_key": r.module_key,
        "module_name": BILLABLE_MODULE_NAMES.get(r.module_key, r.module_key),
        "kind": r.kind,
        "status": r.status,
        "source": r.source,
        "note": r.note,
        "requested_by": requester,
        "requested_at": r.requested_at.isoformat() if r.requested_at else None,
        "completed_by": completer,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
    }


class ModuleRequestIn(BaseModel):
    module_key: str
    kind: str = "trial"
    note: Optional[str] = None


@router.post("/module-requests", status_code=201)
async def create_module_request(
    body: ModuleRequestIn,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """A club admin requests a trial / subscription / cancellation for a module.
    Any club_admin may request a trial or a cancellation; only the club's primary
    admin may request a paid subscription (financial authority gate). The request is
    queued for a super admin — it does not change entitlement on its own."""
    if body.module_key not in BILLABLE_MODULES:
        raise HTTPException(status_code=422, detail=f"Unknown module: {body.module_key}")
    if body.kind not in _REQUEST_KINDS:
        raise HTTPException(status_code=422, detail=f"kind must be one of: {', '.join(_REQUEST_KINDS)}")

    m = (await db.execute(
        select(ClubMembership).where(ClubMembership.user_id == current_user.id)
    )).scalar_one_or_none()
    is_super = bool(m and m.role == "super_admin")
    if not is_super:
        if not (m and m.club_id == club.id and m.role == "club_admin"):
            raise HTTPException(status_code=403, detail="Only a club admin can request module changes")
        if body.kind == "subscribe" and not m.is_primary_admin:
            raise HTTPException(
                status_code=403,
                detail="Only the club's primary admin can request a paid subscription",
            )

    # One outstanding request per (club, module, kind) — return the existing one.
    existing = (await db.execute(
        select(ModuleActionRequest).where(
            ModuleActionRequest.organisation_id == club.id,
            ModuleActionRequest.module_key == body.module_key,
            ModuleActionRequest.kind == body.kind,
            ModuleActionRequest.status == "outstanding",
        )
    )).scalar_one_or_none()
    if existing is not None:
        return _request_payload(existing, org_name=club.name, requester=current_user.username)

    req = ModuleActionRequest(
        organisation_id=club.id,
        module_key=body.module_key,
        kind=body.kind,
        status="outstanding",
        source="app",
        note=(body.note or None),
        requested_by=current_user.id,
    )
    db.add(req)
    # Best-effort: surface the interest on the linked CRM club too (interestedModules
    # in Twenty). Never blocks the request.
    if body.kind in ("trial", "subscribe"):
        try:
            from app.models.db import MarketingClub
            mc = (await db.execute(
                select(MarketingClub).where(MarketingClub.existing_org_id == club.id)
            )).scalar_one_or_none()
            if mc is not None:
                wanted = set(mc.requested_trial_modules or []) | {body.module_key}
                mc.requested_trial_modules = sorted(wanted)
        except Exception:
            pass
    # Uniform club→BetterCricket request telemetry + automated Twenty task (same
    # helper the BetterComms tier request uses), so every ask is tracked and
    # surfaces in the CRM action queue.
    ev = await club_requests.add_request_event(
        db, org_id=club.id, request_type="module_request",
        summary=f"{club.name} requests {body.kind} of {body.module_key}",
        detail={"module_key": body.module_key, "kind": body.kind, "note": body.note},
        source="app", requested_by=current_user.id,
        ref_table="module_action_requests", ref_id=req.id)
    await db.commit()
    club_requests.fire_twenty_task(ev.id)
    if body.kind == "trial":
        # A club asking for a trial itself is as strong a signal as being put on
        # one — force the same Hot(100)+Lead treatment (start_module_trial /
        # approve_module_request give it at the grant end; this is the ask end).
        _push_club_to_twenty(club.id, force_hot=True)
    await db.refresh(req)
    return _request_payload(req, org_name=club.name, requester=current_user.username)


@router.get("/module-requests")
async def list_my_module_requests(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """This club's module requests (newest first) so the club can see their status."""
    rows = (await db.execute(
        select(ModuleActionRequest)
        .where(ModuleActionRequest.organisation_id == club.id)
        .order_by(ModuleActionRequest.requested_at.desc())
        .limit(100)
    )).scalars().all()
    return [_request_payload(r, org_name=club.name) for r in rows]


@router.get("/super/module-requests")
async def list_module_requests(
    status: Optional[str] = None,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """The full super-admin queue, newest first, optionally filtered by status."""
    Requester = _orm_aliased(User)
    Completer = _orm_aliased(User)
    q = (
        select(ModuleActionRequest, Organisation.name, Requester.username, Completer.username)
        .join(Organisation, Organisation.id == ModuleActionRequest.organisation_id)
        .outerjoin(Requester, Requester.id == ModuleActionRequest.requested_by)
        .outerjoin(Completer, Completer.id == ModuleActionRequest.completed_by)
        .order_by(ModuleActionRequest.requested_at.desc())
        .limit(300)
    )
    if status:
        q = q.where(ModuleActionRequest.status == status)
    rows = (await db.execute(q)).all()
    return [
        _request_payload(r, org_name=org_name, requester=ru, completer=cu)
        for r, org_name, ru, cu in rows
    ]


@router.get("/super/module-requests/count")
async def count_module_requests(
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    n = (await db.execute(
        select(func.count()).select_from(ModuleActionRequest)
        .where(ModuleActionRequest.status == "outstanding")
    )).scalar_one()
    return {"outstanding": int(n or 0)}


@router.get("/super/comms/requests/count")
async def count_comms_requests(
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Pending tier-lift requests + clubs currently suspended by the breaker —
    the badge on the super-admin 'Comms limits' nav entry."""
    pending = (await db.execute(
        select(func.count()).select_from(CommsLimitRequest)
        .where(CommsLimitRequest.status == "pending")
    )).scalar_one()
    suspended = (await db.execute(
        select(func.count()).select_from(Organisation)
        .where(Organisation.comms_tier == "suspended")
    )).scalar_one()
    return {"pending": int(pending or 0), "suspended": int(suspended or 0),
            "total": int((pending or 0) + (suspended or 0))}


class RequestApproval(BaseModel):
    # Optional overrides; a trial defaults to start = now, end = now + the club's
    # default trial length.
    start: Optional[_datetime] = None
    end: Optional[_datetime] = None
    days: Optional[int] = None
    renewal_date: Optional[_date] = None


@router.post("/super/module-requests/{request_id}/approve")
async def approve_module_request(
    request_id: str,
    body: RequestApproval,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Action a request: a trial creates the trial (start defaults to now), a
    subscribe sets the module active, a cancel drops it. Marks the request completed."""
    req = await db.get(ModuleActionRequest, uuid.UUID(request_id))
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != "outstanding":
        raise HTTPException(status_code=409, detail="Request already actioned")
    org = await db.get(
        Organisation, req.organisation_id,
        options=[selectinload(Organisation.module_subscriptions)],
    )
    if org is None:
        raise HTTPException(status_code=404, detail="Club not found")
    now = _datetime.now(_timezone.utc)
    result_sub = None
    if req.kind == "trial":
        if body.start and body.end and body.end <= body.start:
            raise HTTPException(status_code=422, detail="Trial end must be after the start")
        from app.services import platform_settings as ps
        days = body.days or await ps.get_default_trial_days(db)
        subs = mod_subs.start_trial_billing(
            org, req.module_key, start=body.start, end=body.end, days=days, now=now,
        )
        result_sub = subs[0] if subs else None
    elif req.kind == "subscribe":
        subs = mod_subs.set_status_billing(
            org, req.module_key, "active",
            renewal_date=body.renewal_date if body.renewal_date is not None else ...,
            now=now,
        )
        result_sub = subs[0] if subs else None
    elif req.kind == "cancel":
        mod_subs.remove_billing(org, req.module_key, now=now)
        await _cancel_stripe_subscription_if_nothing_held(org)
    await db.flush()
    req.status = "completed"
    req.completed_by = current_user.id
    req.completed_at = now
    if result_sub is not None:
        req.result_subscription_id = result_sub.id
    await db.commit()
    # Keep Twenty in step with the new paid/trial split (best-effort, configured-only).
    # A trial approval is put-on-a-trial in every sense a direct grant is
    # (start_module_trial above) — force the same Hot(100)+Lead treatment;
    # subscribe/cancel stay the ordinary billing-fields-only push.
    _push_club_to_twenty(org.id, force_hot=(req.kind == "trial"))
    await db.refresh(org, attribute_names=["module_subscriptions"])
    return {"ok": True, "club": _club_payload(org)}


@router.post("/super/module-requests/{request_id}/dismiss")
async def dismiss_module_request(
    request_id: str,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    req = await db.get(ModuleActionRequest, uuid.UUID(request_id))
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != "outstanding":
        raise HTTPException(status_code=409, detail="Request already actioned")
    req.status = "dismissed"
    req.completed_by = current_user.id
    req.completed_at = _datetime.now(_timezone.utc)
    await db.commit()
    return {"ok": True}


@router.post("/super/clubs/{club_id}/archive")
async def archive_club(
    club_id: str,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete: what the Super Admin "Delete" button actually calls now.
    Sets archived_at only — no row anywhere is touched or removed, so this is
    fully reversible via /restore. Deliberately doesn't touch is_active (an
    archived club's public site is expected to already read as offline via
    archived_at wherever that matters; restoring shouldn't silently flip a
    state the admin didn't touch themselves)."""
    org = await db.get(Organisation, uuid.UUID(club_id))
    if not org:
        raise HTTPException(status_code=404, detail="Club not found")
    if org.archived_at is not None:
        return {"status": "already_archived", "id": club_id}
    org.archived_at = _datetime.now(_timezone.utc)
    # Any super admin currently "acting as" this club stops the moment it's
    # archived, rather than leaving active_club_id dangling on an archived
    # row — get_current_club/_build_me now also guard against this, but
    # clearing it here means a later /restore doesn't silently resume acting
    # as it without the admin explicitly switching back.
    await db.execute(
        _text("UPDATE users SET active_club_id = NULL WHERE active_club_id = :cid"),
        {"cid": club_id},
    )
    from app.services.audit_log import log_activity
    await log_activity(
        db, org_id=org.id, user_id=current_user.id,
        action="archive_club", target_type="organisation", target_id=club_id,
        details={"name": org.name},
    )
    await db.commit()
    return {"status": "archived", "id": club_id}


@router.post("/super/clubs/{club_id}/restore")
async def restore_club(
    club_id: str,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    org = await db.get(Organisation, uuid.UUID(club_id))
    if not org:
        raise HTTPException(status_code=404, detail="Club not found")
    if org.archived_at is None:
        return {"status": "not_archived", "id": club_id}
    org.archived_at = None
    from app.services.audit_log import log_activity
    await log_activity(
        db, org_id=org.id, user_id=current_user.id,
        action="restore_club", target_type="organisation", target_id=club_id,
        details={"name": org.name},
    )
    await db.commit()
    return {"status": "restored", "id": club_id}


@router.get("/super/clubs/{club_id}/merge-preview")
async def preview_club_merge(
    club_id: str,
    target_id: str,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Cheap counts for the confirm dialog before an actual merge — how much
    of `club_id` (source) would move vs collide-and-merge into `target_id`."""
    try:
        source_uuid, target_uuid = uuid.UUID(club_id), uuid.UUID(target_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid club id")
    source_org = await db.get(Organisation, source_uuid)
    target_org = await db.get(Organisation, target_uuid)
    if not source_org or not target_org:
        raise HTTPException(status_code=404, detail="Club not found")

    counts = {}
    for label, table in (("seasons", "seasons"), ("grades", "grades"), ("players", "players")):
        counts[f"{label}_total"] = (await db.execute(
            _text(
                f"SELECT COUNT(*) FROM {table} t "
                + ("WHERE t.organisation_id = :sid" if table != "grades"
                   else "JOIN seasons s ON s.id = t.season_id WHERE s.organisation_id = :sid")
            ),
            {"sid": str(source_uuid)},
        )).scalar_one()
    games_total = (await db.execute(
        _text(
            "SELECT COUNT(*) FROM games g JOIN grades gr ON gr.id = g.grade_id "
            "JOIN seasons s ON s.id = gr.season_id WHERE s.organisation_id = :sid"
        ),
        {"sid": str(source_uuid)},
    )).scalar_one()
    return {
        "source_org": {"id": str(source_org.id), "name": source_org.name},
        "target_org": {"id": str(target_org.id), "name": target_org.name},
        **counts,
        "games_total": games_total,
    }


@router.post("/super/clubs/{club_id}/merge-into/{target_id}")
async def merge_club(
    club_id: str,
    target_id: str,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Bulk-reassign a club merger's synced history: `club_id` (the SOURCE —
    e.g. a temp org synced just to pull in a since-merged predecessor club's
    PlayHQ/CA history) is folded into `target_id` (the real, ongoing club),
    then archived. See services/org_merge.py for the full mechanics and its
    documented reversibility limits — this is not a fully-undoable operation
    the way archive/restore is."""
    try:
        source_uuid, target_uuid = uuid.UUID(club_id), uuid.UUID(target_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid club id")

    from app.services.org_merge import merge_organisation
    try:
        result = await merge_organisation(db, source_uuid, target_uuid, current_user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return result


@router.post("/super/clubs/{club_id}/repair-merge-stats")
async def repair_club_merge_stats(
    club_id: str,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Retroactively fix player_season_stats/player_season_grade_stats rows
    left pointing at a now-archived predecessor org's season/grade by an
    earlier run of merge-into (see services/org_merge.py, which now does this
    repoint automatically for any NEW merge — this endpoint is for a club
    merged before that fix shipped). Safe to run on any club; a no-op if
    there's nothing to repair."""
    try:
        org_uuid = uuid.UUID(club_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid club id")

    from app.services.org_merge import repair_organisation_merge_stats
    return await repair_organisation_merge_stats(db, org_uuid, current_user)


@router.delete("/super/clubs/{club_id}")
async def delete_club(
    club_id: str,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Permanent hard delete — kept as a lower-level capability (e.g. for
    purging a long-archived club later) but no longer what the "Delete"
    button in SuperClubs.jsx calls; that now archives (see archive_club
    above). Requires the club to already be archived, as a speed bump against
    ever hitting this by accident on a live club.

    Fixed FK cascade drift on legacy per-game/per-player stat tables
    (migration 142 — partnerships_game_id_fkey and siblings weren't actually
    ON DELETE CASCADE in the live schema despite the ORM model saying so,
    which made this 500 on any club with real synced data)."""
    org = await db.get(Organisation, uuid.UUID(club_id))
    if not org:
        raise HTTPException(status_code=404, detail="Club not found")
    if org.archived_at is None:
        raise HTTPException(
            status_code=409,
            detail="Archive the club first (this permanently destroys its data and is not reversible).",
        )

    # These tables key on org_id but have no FK constraint, so the
    # organisations cascade won't reach them — clean them up explicitly.
    for table in ("merge_logs", "merge_pair_ignores", "grade_merge_logs", "player_achievements"):
        await db.execute(
            _text(f"DELETE FROM {table} WHERE org_id = CAST(:id AS UUID)"),
            {"id": club_id},
        )

    # The rest (seasons, grades, games, players, stats, memberships, …) all
    # FK to organisations ON DELETE CASCADE, so the DB handles them.
    await db.execute(
        _text("DELETE FROM organisations WHERE id = CAST(:id AS UUID)"),
        {"id": club_id},
    )
    await db.commit()
    return {"status": "deleted", "id": club_id}


# ---------------------------------------------------------------------------
# Super admin — user management
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    username: str
    password: str
    display_name: Optional[str] = None
    club_id: str
    role: str = "club_admin"


@router.get("/super/users")
async def list_users(
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User, ClubMembership, Organisation)
        .join(ClubMembership, ClubMembership.user_id == User.id, isouter=True)
        .join(Organisation, Organisation.id == ClubMembership.club_id, isouter=True)
        .order_by(User.username)
    )
    rows = result.all()
    return [
        {
            "id": str(r.User.id),
            "username": r.User.username,
            "display_name": r.User.display_name,
            "email": r.User.email,
            "mobile_number": r.User.mobile_number,
            "role": r.ClubMembership.role if r.ClubMembership else None,
            "club_name": r.Organisation.name if r.Organisation else None,
            "club_id": str(r.ClubMembership.club_id) if r.ClubMembership else None,
            "is_primary_admin": bool(r.ClubMembership.is_primary_admin) if r.ClubMembership else False,
            "last_login_at": r.User.last_login_at.isoformat() if r.User.last_login_at else None,
            "locked": r.User.locked_until is not None,
        }
        for r in rows
    ]


@router.get("/super/onboarding-requests")
async def list_onboarding_requests(
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Every club onboarding enquiry from the marketing Contact form, newest first."""
    result = await db.execute(
        select(ClubOnboardingRequest).order_by(ClubOnboardingRequest.created_at.desc())
    )
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "club": r.club,
            "email": r.email,
            "phone": r.phone,
            "association": r.association,
            "grades": r.grades,
            "storage": r.storage,
            "timeline": r.timeline,
            "club_url": r.club_url,
            "message": r.message,
            "role": r.role,
            "founded_year": r.founded_year,
            "playhq_status": r.playhq_status,
            "has_historical": r.has_historical,
            "interests": r.interests,
            "heard_about": r.heard_about,
            "contact_method": r.contact_method,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "source": r.source,
            # First-party visitor id (same one the Usage Breadcrumbs page keys
            # on) so staff can jump from an enquiry to the page-view journey
            # that led to it.
            "visitor_id": r.visitor_id,
        }
        for r in result.scalars().all()
    ]


_ONBOARDING_STATUSES = {"new", "contacted", "onboarded", "closed"}


class OnboardingStatusIn(BaseModel):
    status: str


@router.patch("/super/onboarding-requests/{request_id}")
async def update_onboarding_request(
    request_id: uuid.UUID,
    payload: OnboardingStatusIn,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Move an enquiry through the follow-up states (new, contacted, onboarded, closed)."""
    status_value = (payload.status or "").strip().lower()
    if status_value not in _ONBOARDING_STATUSES:
        raise HTTPException(status_code=422, detail="Unknown status.")
    row = await db.get(ClubOnboardingRequest, request_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Request not found.")
    row.status = status_value
    await db.commit()
    return {"ok": True, "status": status_value}


@router.delete("/super/onboarding-requests/{request_id}")
async def delete_onboarding_request(
    request_id: uuid.UUID,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Remove a junk/duplicate/spam enquiry from the onboarding list."""
    row = await db.get(ClubOnboardingRequest, request_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Request not found.")
    await db.delete(row)
    await db.commit()
    return {"ok": True}


@router.post("/super/users", status_code=201)
async def create_user(
    data: UserCreate,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    username = data.username.lower().strip()
    if not username or len(username) < 3 or len(username) > 32:
        raise HTTPException(status_code=422, detail="Username must be 3-32 characters")

    existing = await db.execute(select(User).where(User.username == username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username already taken")

    if len(data.password) < 10:
        raise HTTPException(status_code=422, detail="Password must be at least 10 characters")

    club = await db.get(Organisation, uuid.UUID(data.club_id))
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")

    user = User(
        username=username,
        password_hash=_hash_password(data.password),
        display_name=data.display_name,
    )
    db.add(user)
    await db.flush()

    membership = ClubMembership(
        club_id=club.id,
        user_id=user.id,
        role=data.role if data.role in ("super_admin", "club_admin") else "club_admin",
    )
    db.add(membership)
    await db.flush()
    # The first club_admin of a club is its primary/owner admin.
    if membership.role == "club_admin":
        from app.services.memberships import ensure_primary_admin
        await ensure_primary_admin(db, club.id)
    await db.commit()

    return {"id": str(user.id), "username": user.username, "club_id": data.club_id, "role": membership.role}


class PasswordReset(BaseModel):
    new_password: str


@router.post("/super/users/{user_id}/reset-password")
async def reset_password(
    user_id: str,
    data: PasswordReset,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    if len(data.new_password) < 10:
        raise HTTPException(status_code=422, detail="Password must be at least 10 characters")

    user = await db.get(User, uuid.UUID(user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.password_hash = _hash_password(data.new_password)
    user.failed_login_count = 0
    user.locked_until = None
    await db.commit()
    return {"status": "password_reset"}


async def _super_admin_count(db: AsyncSession) -> int:
    res = await db.execute(
        select(func.count()).select_from(ClubMembership).where(ClubMembership.role == "super_admin")
    )
    return res.scalar() or 0


class UserUpdate(BaseModel):
    username: Optional[str] = None
    display_name: Optional[str] = None
    email: Optional[str] = None
    mobile_number: Optional[str] = None
    role: Optional[str] = None
    club_id: Optional[str] = None


@router.patch("/super/users/{user_id}")
async def patch_user(
    user_id: str,
    data: UserUpdate,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, uuid.UUID(user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    fields = data.model_dump(exclude_unset=True)

    if "username" in fields:
        username = (fields["username"] or "").lower().strip()
        if len(username) < 3 or len(username) > 32:
            raise HTTPException(status_code=422, detail="Username must be 3-32 characters")
        clash = await db.execute(
            select(User).where(User.username == username, User.id != user.id)
        )
        if clash.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Username already taken")
        user.username = username

    if "display_name" in fields:
        user.display_name = (fields["display_name"] or "").strip() or None

    if "email" in fields:
        email = (fields["email"] or "").strip().lower()
        # Optional here (unlike the per-club Users page) — this router's own
        # create_user doesn't collect an email, so some accounts have none.
        if email and not _INVITE_EMAIL_RE.match(email):
            raise HTTPException(status_code=422, detail="That doesn't look like a valid email address")
        user.email = email or None

    if "mobile_number" in fields:
        # Format-only, same as the per-club Users page — not required to be unique.
        user.mobile_number = _clean_mobile(fields["mobile_number"])

    membership_res = await db.execute(
        select(ClubMembership).where(ClubMembership.user_id == user.id)
    )
    membership = membership_res.scalar_one_or_none()

    new_role = fields.get("role")
    if new_role is not None and new_role not in ("super_admin", "club_admin"):
        raise HTTPException(status_code=422, detail="Role must be super_admin or club_admin")

    # Block removing the last super admin via a role demotion.
    if (
        new_role == "club_admin"
        and membership
        and membership.role == "super_admin"
        and await _super_admin_count(db) <= 1
    ):
        raise HTTPException(status_code=400, detail="Cannot demote the last super admin")

    if "club_id" in fields:
        club = await db.get(Organisation, uuid.UUID(fields["club_id"]))
        if not club:
            raise HTTPException(status_code=404, detail="Club not found")
        if membership:
            membership.club_id = club.id
        else:
            membership = ClubMembership(
                club_id=club.id,
                user_id=user.id,
                role=new_role or "club_admin",
            )
            db.add(membership)

    if new_role is not None and membership:
        membership.role = new_role

    await db.commit()
    return {
        "id": str(user.id),
        "username": user.username,
        "display_name": user.display_name,
        "email": user.email,
        "mobile_number": user.mobile_number,
        "role": membership.role if membership else None,
        "club_id": str(membership.club_id) if membership else None,
    }


@router.delete("/super/users/{user_id}")
async def delete_user(
    user_id: str,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, uuid.UUID(user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")

    membership_res = await db.execute(
        select(ClubMembership).where(ClubMembership.user_id == user.id)
    )
    membership = membership_res.scalar_one_or_none()
    if membership and membership.role == "super_admin" and await _super_admin_count(db) <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the last super admin")

    # club_memberships FK to users ON DELETE CASCADE — removed automatically.
    await db.delete(user)
    await db.commit()
    return {"status": "deleted", "id": user_id}


# ---------------------------------------------------------------------------
# Player Sync Requests
# ---------------------------------------------------------------------------

@router.get("/sync-requests")
async def list_sync_requests(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        _text("""
            SELECT
                sr.id, sr.status, sr.requester_note, sr.admin_note,
                sr.created_at, sr.resolved_at,
                p.id::text AS player_id,
                COALESCE(p.display_name_override, p.name) AS player_name,
                p.playhq_id
            FROM player_sync_requests sr
            JOIN players p ON p.id = sr.player_id
            WHERE sr.org_id = :org_id
            ORDER BY sr.created_at DESC
            LIMIT 100
        """),
        {"org_id": str(club.id)},
    )
    rows = result.mappings().all()
    return [
        {
            "id": r["id"],
            "status": r["status"],
            "requester_note": r["requester_note"],
            "admin_note": r["admin_note"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "resolved_at": r["resolved_at"].isoformat() if r["resolved_at"] else None,
            "player_id": r["player_id"],
            "player_name": r["player_name"],
            "playhq_id": r["playhq_id"],
        }
        for r in rows
    ]


class SyncRequestAction(BaseModel):
    action: str  # "approve" or "dismiss"
    admin_note: Optional[str] = None


@router.post("/sync-requests/{request_id}")
async def action_sync_request(
    request_id: int,
    body: SyncRequestAction,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    from datetime import datetime, timezone
    req = await db.get(PlayerSyncRequest, request_id)
    if not req or str(req.org_id) != str(club.id):
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != "pending":
        raise HTTPException(status_code=409, detail="Request already resolved")
    if body.action not in ("approve", "dismiss"):
        raise HTTPException(status_code=422, detail="action must be 'approve' or 'dismiss'")

    if body.action == "approve":
        player = await db.get(Player, req.player_id)

        # Pre-checks before approving
        warnings = []
        if not player:
            raise HTTPException(status_code=404, detail="Player no longer exists")
        if not player.playhq_id:
            warnings.append("no_phq_id")
        player_id_str = str(req.player_id)
        if player_id_str in _player_sync_running:
            return {"status": "already_running", "warnings": warnings,
                    "message": "A deep sync is already running for this player"}

        # Return warning to admin without approving yet so they can decide
        if "no_phq_id" in warnings and not body.admin_note:
            return {
                "status": "needs_confirmation",
                "warnings": warnings,
                "message": (
                    f"{player.display_name} has no PlayHQ ID linked — sync will rely on name matching only "
                    "and may miss historical games. Set their PHQ ID first (Admin → PHQ ID Match or Admin → Players), "
                    "then approve again. To proceed anyway, re-approve with any admin note."
                ),
            }

        req.admin_note = body.admin_note
        req.resolved_at = datetime.now(timezone.utc)
        req.status = "approved"
        await db.commit()

        from app.services.sync import deep_sync_player, start_sync_run, finish_sync_run
        _logger = _logging.getLogger(__name__)
        org_id_str = str(club.id)
        _player_sync_running.add(player_id_str)
        run_id = await start_sync_run(club.id, "player_deep", player_id=player.id)

        async def _run_and_log():
            _logger.info(f"DeepSync: background task started for player {player_id_str}")
            try:
                result = await deep_sync_player(org_id_str, player_id_str, run_id=run_id)
                _logger.info(f"DeepSync: completed for player {player_id_str}: {result}")
                await finish_sync_run(run_id, result if isinstance(result, dict) and "error" not in result else {}, result.get("error", "") if isinstance(result, dict) else "")
            except Exception as e:
                _logger.error(f"DeepSync: FAILED for player {player_id_str}: {e}", exc_info=True)
                await finish_sync_run(run_id, {}, f"Unexpected error: {e}")
            finally:
                _player_sync_running.discard(player_id_str)
                _background_tasks.discard(asyncio.current_task())

        task = asyncio.create_task(_run_and_log())
        _background_tasks.add(task)
        return {"status": "approved", "warnings": warnings, "message": "Deep sync started in background", "run_id": str(run_id)}

    req.admin_note = body.admin_note
    req.resolved_at = datetime.now(timezone.utc)
    req.status = "dismissed"
    await db.commit()
    return {"status": "dismissed"}


# ---------------------------------------------------------------------------
# Sync runs (hard refresh + history)
# ---------------------------------------------------------------------------

# Per-org hard-refresh locks
_hard_refresh_running: set = set()


@router.post("/hard-refresh", status_code=202)
async def hard_refresh_org(
    current_user: User = Depends(require_cap(RUN_HARD_REFRESH)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Trigger a full historical re-sync of the org.

    Wipes existing game-level data (games + cascading batting / bowling /
    fielding / FOW / partnerships) and re-runs the full sync. Used after
    sync-logic changes (innings split, FOW-vs-dismissal checks, etc.) to
    rebuild from current code rather than top up.

    Only wipes games that have batting rows — PHQ-namespace shells the GR
    API returns 204 for would be unrecoverable, but those have no batting
    rows anyway so the WHERE filter is a no-op for them. Runs in the
    background; poll GET /club-admin/sync-runs/{run_id} for progress.
    """
    from app.services.sync import (
        sync_organisation, start_sync_run, finish_sync_run, update_sync_run,
        pause_sync_run, cancel_sync_run, SyncControlSignal,
    )
    from app.services.rate_limit import enforce
    org_id_str = str(club.id)

    # 1 hard-refresh per club per hour. The operation itself takes 1h+ and
    # the in-progress guard below blocks a *concurrent* second call, but
    # nothing stops a user clicking the button repeatedly during the run or
    # right after it finishes. This window covers both cases.
    # Super admins are exempt — they're the ones who need to immediately
    # retry after a failed rebuild (e.g. a transient upstream connection
    # error), and the in-progress guard already prevents a genuinely
    # concurrent double-run.
    membership = (await db.execute(
        select(ClubMembership).where(ClubMembership.user_id == current_user.id)
    )).scalar_one_or_none()
    is_super_admin = bool(membership and membership.role == "super_admin")
    if not is_super_admin:
        enforce(
            f"hard-refresh:{org_id_str}",
            limit=1,
            window_sec=3600,
            detail="Hard refresh is allowed once per hour. Try again later.",
        )

    if org_id_str in _hard_refresh_running:
        return {"status": "already_running", "org_id": org_id_str}

    run_id = await start_sync_run(club.id, "org_hard_refresh")
    _hard_refresh_running.add(org_id_str)
    _logger = _logging.getLogger(__name__)

    async def _run():
        _logger.info(f"HardRefresh: starting for org {org_id_str} (run_id={run_id})")
        try:
            from app.models.db import async_session_maker
            from sqlalchemy import text as _t

            # Pre-flight probe — DON'T wipe until we've confirmed the Cricket
            # Australia scores API is actually serving match data right now.
            # The wipe below is committed before the re-pull, so if the scores
            # API is down during the re-pull the games are gone and nothing
            # restores them (the run still reports "success" because the
            # aggregate pass uses a different, healthy endpoint). That exact
            # failure wiped a club's entire game-level history once
            # (gr_matches_seen: 0 on a rebuild that had pulled 2400 games an
            # hour earlier). Probing first turns a destructive outage into a
            # harmless "try again later".
            await update_sync_run(run_id, {"progress_phase": "Checking data source", "progress_pct": 0})
            from app.services import grassroots_scores_client as _gsc
            async with async_session_maker() as s:
                probe_rows = (
                    await s.execute(
                        _t(
                            """
                            SELECT COALESCE(gr.grassroots_id, gr.id::text) AS gid
                            FROM grades gr
                            JOIN seasons se ON se.id = gr.season_id
                            WHERE se.organisation_id = :oid
                            ORDER BY se.year DESC NULLS LAST
                            LIMIT 15
                            """
                        ),
                        {"oid": org_id_str},
                    )
                ).all()
            probe_grade_ids = [row.gid for row in probe_rows if row.gid]
            if probe_grade_ids:
                source_alive = False
                for gid in probe_grade_ids:
                    try:
                        if await _gsc.get_grade_matches(gid, force=True):
                            source_alive = True
                            break
                    except Exception:
                        continue
                if not source_alive:
                    _logger.error(
                        f"HardRefresh: ABORTED for org {org_id_str} — scores API returned no "
                        f"matches for any of {len(probe_grade_ids)} probed grades; refusing to "
                        f"wipe game-level data while the upstream looks unavailable."
                    )
                    await finish_sync_run(
                        run_id,
                        {"games_wiped_pre_sync": 0},
                        "Aborted before wiping: the Cricket Australia scores API returned no "
                        "match data for any grade, so a rebuild would have left the club with "
                        "no games. Existing data was left untouched — try again later.",
                    )
                    return

            await update_sync_run(run_id, {"progress_phase": "Clearing stored games", "progress_pct": 0})
            # Wipe phase — games with batting rows whose seasons belong to this org.
            async with async_session_maker() as s:
                r = await s.execute(
                    _t(
                        """
                        DELETE FROM games
                        WHERE id IN (SELECT DISTINCT game_id FROM batting_innings)
                          AND grade_id IN (
                            SELECT gr.id FROM grades gr
                            JOIN seasons se ON se.id = gr.season_id
                            WHERE se.organisation_id = :oid
                          )
                        RETURNING id
                        """
                    ),
                    {"oid": org_id_str},
                )
                wiped = len(list(r))
                await s.commit()
                _logger.info(f"HardRefresh: wiped {wiped} games (cascades cleared all child rows) for org {org_id_str}")

            stats = await sync_organisation(org_id_str, run_id=run_id, kind="org_hard_refresh")
            stats = dict(stats or {})
            stats["games_wiped_pre_sync"] = wiped

            # Backstop — if we wiped games but the re-pull discovered no matches
            # at all, the scores API went down mid-run (the probe passed, then
            # the upstream failed). Report it as an error so it's visible and
            # retried, rather than a silent "success" masking total data loss.
            matches_seen = int(stats.get("gr_matches_seen") or 0)
            new_games = int(stats.get("gr_games_new") or 0)
            if wiped > 0 and matches_seen == 0 and new_games == 0:
                _logger.error(
                    f"HardRefresh: org {org_id_str} wiped {wiped} games but the re-pull saw 0 "
                    f"matches — scores API likely failed mid-run. Re-run when it recovers."
                )
                await finish_sync_run(
                    run_id,
                    stats,
                    f"Wiped {wiped} games but the game-level re-pull returned 0 matches — the "
                    f"Cricket Australia scores API failed mid-rebuild. Re-run Full Rebuild to "
                    f"restore the scorecards once it recovers.",
                )
            else:
                await finish_sync_run(run_id, stats)

                # Auto-generate + auto-publish yearbooks for the last 3 seasons
                # with stats. A rebuild is the signal that the club's data is
                # actually current, so this only runs on the true-success path
                # above — never on the "wiped but 0 matches came back" branch.
                # Isolated try/except: a yearbook failure must never look like
                # a sync failure (finish_sync_run has already recorded success).
                try:
                    async with async_session_maker() as s:
                        from app.routers.yearbooks import auto_generate_and_publish_recent_yearbooks
                        yb_result = await auto_generate_and_publish_recent_yearbooks(s, org_id_str, count=3)
                    _logger.info(f"HardRefresh: yearbook auto-generate for {org_id_str}: {yb_result}")
                except Exception as ye:
                    _logger.warning(f"HardRefresh: yearbook auto-generate failed for {org_id_str}: {ye}")

            # Refresh planner statistics. A hard refresh delete+reinserts the
            # org's whole game-level dataset and rewrites player_season_stats,
            # which leaves Postgres' statistics stale until autovacuum catches
            # up. player_season_stats is a global table (every club), so a stale
            # plan makes the all-seasons leaderboard / summary scan every club's
            # rows and time out (35s → nginx 504) even though the data is fine.
            # ANALYZE is cheap next to the multi-minute rebuild and makes the
            # heavy aggregate reads snap back to ~1s immediately.
            try:
                async with async_session_maker() as s:
                    await s.execute(_t("ANALYZE"))
                    await s.commit()
                _logger.info(f"HardRefresh: ANALYZE complete for org {org_id_str}")
            except Exception as ae:
                _logger.warning(f"HardRefresh: post-sync ANALYZE failed for {org_id_str}: {ae}")
        except SyncControlSignal as sig:
            # Pause/Cancel from the Super Admin All Clubs page — not a crash.
            # The pre-sync wipe (if it ran) already committed, so a paused
            # run is safe to Continue later as a plain incremental sync (see
            # pause_sync_run's docstring) — never re-wipe on Continue.
            wiped_so_far = locals().get("wiped", 0)
            if sig.action == "pause":
                await pause_sync_run(run_id, {"games_wiped_pre_sync": wiped_so_far})
            else:
                await cancel_sync_run(run_id, {"games_wiped_pre_sync": wiped_so_far})
            _logger.info(f"HardRefresh: {sig.action} for {org_id_str}")
        except Exception as e:
            _logger.error(f"HardRefresh: failed for {org_id_str}: {e}", exc_info=True)
            await finish_sync_run(run_id, {}, f"Unexpected error: {e}")
        finally:
            _hard_refresh_running.discard(org_id_str)
            _background_tasks.discard(asyncio.current_task())

    task = asyncio.create_task(_run())
    _background_tasks.add(task)
    return {"status": "started", "run_id": str(run_id), "org_id": org_id_str}


@router.post("/backfill-aggregates")
async def backfill_aggregates(
    current_user: User = Depends(require_cap(RUN_SYNC)),
    club: Organisation = Depends(get_current_club),
):
    """Synthesise missing player_season_stats rows from per-game scorecard data.

    For (player, season) pairs that have batting / bowling / fielding rows
    but no aggregate row — typically low-volume players omitted by CA's
    Grassroots aggregate API for older seasons — insert a computed
    aggregate so career numbers add up. Lighter than a full hard-refresh.
    """
    from app.services.sync import _backfill_missing_season_stats
    inserted = await _backfill_missing_season_stats(str(club.id))
    return {"inserted": inserted, "org_id": str(club.id)}


@router.post("/cleanup-opposition-stats")
async def cleanup_opposition_stats(
    current_user: User = Depends(require_cap(RUN_HARD_REFRESH)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Delete per-game stat rows belonging to opposition players.

    Pre-fix, the GR scorecard parser gated stat inserts on "is this pid in
    OUR org's players table" rather than "is this pid on OUR team in THIS
    game". So a current club member who played AGAINST us in a match (on
    another club's roster that season) had their opposition batting /
    bowling / fielding picked up as ours, inflating their match count and
    career stats.

    This endpoint runs a one-off cleanup: for every game where the roster
    was captured (>= 1 game_appearance), drop per-game rows whose player
    isn't in that game's roster. Then deletes player_season_stats rows
    that become orphaned (no per-game backing AND no appearance) so the
    headline match count recomputes correctly.

    Safe to re-run. Only operates on games whose grade → season belongs to
    this org. Games where the roster was never captured (older syncs) are
    left alone defensively — we can't tell what's opposition there.
    """
    org_id = str(club.id)
    org_param = {"oid": org_id}

    org_games_cte = """
        WITH org_games AS (
            SELECT g.id
            FROM games g
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE s.organisation_id = CAST(:oid AS UUID)
        ),
        roster_games AS (
            SELECT DISTINCT game_id FROM game_appearances
            WHERE game_id IN (SELECT id FROM org_games)
        )
    """

    deleted = {}

    for table in ("batting_innings", "bowling_spells", "fielding_stats"):
        res = await db.execute(
            _text(f"""
                {org_games_cte}
                DELETE FROM {table} t
                WHERE t.game_id IN (SELECT game_id FROM roster_games)
                  AND NOT EXISTS (
                    SELECT 1 FROM game_appearances ga
                    WHERE ga.game_id = t.game_id AND ga.player_id = t.player_id
                  )
            """),
            org_param,
        )
        deleted[table] = res.rowcount

    # FOW: clear pid attribution only (keep the row so opposition-innings
    # wicket falls still render on the scorecard, just without a player tag).
    res = await db.execute(
        _text(f"""
            {org_games_cte}
            UPDATE fall_of_wickets fow
            SET player_id = NULL
            WHERE fow.game_id IN (SELECT game_id FROM roster_games)
              AND fow.player_id IS NOT NULL
              AND NOT EXISTS (
                SELECT 1 FROM game_appearances ga
                WHERE ga.game_id = fow.game_id AND ga.player_id = fow.player_id
              )
        """),
        org_param,
    )
    deleted["fall_of_wickets_pid_cleared"] = res.rowcount

    # Partnerships: drop rows where neither batter is on our team in that
    # game. (Single-batter-unknown rows are kept — at least one tagged
    # partner means it's our innings.)
    res = await db.execute(
        _text(f"""
            {org_games_cte}
            DELETE FROM partnerships p
            WHERE p.game_id IN (SELECT game_id FROM roster_games)
              AND NOT EXISTS (
                SELECT 1 FROM game_appearances ga
                WHERE ga.game_id = p.game_id
                  AND ga.player_id IN (p.batter1_id, p.batter2_id)
              )
        """),
        org_param,
    )
    deleted["partnerships"] = res.rowcount

    # Bowler wickets: drop rows where the bowler wasn't on our team.
    res = await db.execute(
        _text(f"""
            {org_games_cte}
            DELETE FROM bowler_wickets bw
            WHERE bw.game_id IN (SELECT game_id FROM roster_games)
              AND NOT EXISTS (
                SELECT 1 FROM game_appearances ga
                WHERE ga.game_id = bw.game_id AND ga.player_id = bw.bowler_id
              )
        """),
        org_param,
    )
    deleted["bowler_wickets"] = res.rowcount

    # Drop phantom player_season_stats rows: (player, season) pairs that
    # now have no per-game data AND no game_appearance backing AND were
    # synthesised by the backfill (source='backfill'). API-sourced rows
    # are spared even when they have no per-game backing — that's the
    # legitimate shape for pre-PlayHQ-migration players whose data only
    # exists as CA career summaries (e.g. MyCricket-era aggregate stats),
    # no scorecard rows, no appearances. Without the source check this
    # DELETE wipes them and the next aggregate sync can't restore them
    # if CA's API no longer surfaces those old per-season totals.
    res = await db.execute(
        _text("""
            DELETE FROM player_season_stats pss
            USING players pl
            WHERE pss.player_id = pl.id
              AND pl.organisation_id = CAST(:oid AS UUID)
              AND pss.source = 'backfill'
              AND NOT EXISTS (
                SELECT 1 FROM batting_innings bi
                JOIN games g ON g.id = bi.game_id
                JOIN grades gr ON gr.id = g.grade_id
                WHERE bi.player_id = pss.player_id
                  AND gr.season_id = pss.season_id
              )
              AND NOT EXISTS (
                SELECT 1 FROM bowling_spells bs
                JOIN games g ON g.id = bs.game_id
                JOIN grades gr ON gr.id = g.grade_id
                WHERE bs.player_id = pss.player_id
                  AND gr.season_id = pss.season_id
              )
              AND NOT EXISTS (
                SELECT 1 FROM fielding_stats fs
                JOIN games g ON g.id = fs.game_id
                JOIN grades gr ON gr.id = g.grade_id
                WHERE fs.player_id = pss.player_id
                  AND gr.season_id = pss.season_id
              )
              AND NOT EXISTS (
                SELECT 1 FROM game_appearances ga
                JOIN games g ON g.id = ga.game_id
                JOIN grades gr ON gr.id = g.grade_id
                WHERE ga.player_id = pss.player_id
                  AND gr.season_id = pss.season_id
              )
        """),
        org_param,
    )
    deleted["player_season_stats_phantom"] = res.rowcount

    await db.commit()

    # Re-run the per-game backfill so matches/runs/wickets are recomputed
    # from the cleaned per-game tables for any pair that still has data
    # but whose pss row was either deleted above or never existed.
    from app.services.sync import _backfill_missing_season_stats
    backfilled = await _backfill_missing_season_stats(org_id)
    deleted["player_season_stats_backfilled"] = backfilled

    return {"org_id": org_id, "deleted": deleted}


@router.delete("/sync-runs")
async def clear_sync_runs(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Delete completed/errored sync runs for this org. Preserves any currently-running rows."""
    res = await db.execute(
        _text("DELETE FROM sync_runs WHERE org_id = :oid AND status != 'running'"),
        {"oid": str(club.id)},
    )
    await db.commit()
    return {"deleted": res.rowcount}


@router.delete("/sync-requests/resolved")
async def clear_resolved_sync_requests(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Delete approved/dismissed player sync requests for this org. Preserves pending ones."""
    res = await db.execute(
        _text("DELETE FROM player_sync_requests WHERE org_id = :oid AND status != 'pending'"),
        {"oid": str(club.id)},
    )
    await db.commit()
    return {"deleted": res.rowcount}


@router.get("/sync-runs")
async def list_sync_runs(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
    limit: int = 30,
):
    from app.models.db import SyncRun
    res = await db.execute(
        select(SyncRun)
        .where(SyncRun.org_id == club.id)
        .order_by(SyncRun.started_at.desc())
        .limit(min(limit, 100))
    )
    runs = res.scalars().all()
    return [
        {
            "id": str(r.id),
            "kind": r.kind,
            "status": r.status,
            "player_id": str(r.player_id) if r.player_id else None,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "stats": r.stats or {},
            "error": r.error,
        }
        for r in runs
    ]


@router.get("/sync-runs/{run_id}")
async def get_sync_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    from app.models.db import SyncRun
    run = await db.get(SyncRun, uuid.UUID(run_id))
    if not run or run.org_id != club.id:
        raise HTTPException(status_code=404, detail="Sync run not found")
    return {
        "id": str(run.id),
        "kind": run.kind,
        "status": run.status,
        "player_id": str(run.player_id) if run.player_id else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "stats": run.stats or {},
        "error": run.error,
    }


# ---------------------------------------------------------------------------
# Sponsors
# ---------------------------------------------------------------------------

def _sponsor_dict(s: Sponsor) -> dict:
    return {
        "id": str(s.id),
        "name": s.name,
        "website_url": s.website_url,
        "logo_url": s.logo_url,
        "display_order": s.display_order,
    }


@router.get("/sponsors")
async def list_sponsors(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Sponsor)
        .where(Sponsor.organisation_id == club.id)
        .order_by(Sponsor.display_order, Sponsor.created_at)
    )
    return [_sponsor_dict(s) for s in result.scalars().all()]


class SponsorCreate(BaseModel):
    name: str
    website_url: Optional[str] = None


@router.post("/sponsors")
async def create_sponsor(
    data: SponsorCreate,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name is required")
    # Place new sponsor at the end
    result = await db.execute(
        select(func.max(Sponsor.display_order)).where(Sponsor.organisation_id == club.id)
    )
    max_order = result.scalar() or 0
    sponsor = Sponsor(
        organisation_id=club.id,
        name=name,
        website_url=data.website_url.strip() if data.website_url else None,
        display_order=max_order + 1,
    )
    db.add(sponsor)
    await db.commit()
    return _sponsor_dict(sponsor)


class SponsorPatch(BaseModel):
    name: Optional[str] = None
    website_url: Optional[str] = None


@router.patch("/sponsors/{sponsor_id}")
async def patch_sponsor(
    sponsor_id: str,
    data: SponsorPatch,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    sponsor = await db.get(Sponsor, uuid.UUID(sponsor_id))
    if not sponsor or sponsor.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Sponsor not found")
    if data.name is not None:
        sponsor.name = data.name.strip() or sponsor.name
    if data.website_url is not None:
        sponsor.website_url = data.website_url.strip() or None
    await db.commit()
    return _sponsor_dict(sponsor)


@router.post("/sponsors/{sponsor_id}/logo")
async def upload_sponsor_logo(
    sponsor_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    sponsor = await db.get(Sponsor, uuid.UUID(sponsor_id))
    if not sponsor or sponsor.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Sponsor not found")
    if file.content_type not in ("image/png", "image/jpeg", "image/svg+xml", "image/webp", "image/gif"):
        raise HTTPException(status_code=422, detail="Unsupported image type")
    data = await file.read()
    if len(data) > 2 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Logo must be under 2 MB")
    sponsor.logo_data = data
    sponsor.logo_mime = file.content_type
    import time as _time
    sponsor.logo_url = f"/images/sponsors/{sponsor_id}/logo?v={int(_time.time())}"
    await db.commit()
    return _sponsor_dict(sponsor)


@router.delete("/sponsors/{sponsor_id}/logo")
async def delete_sponsor_logo(
    sponsor_id: str,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    sponsor = await db.get(Sponsor, uuid.UUID(sponsor_id))
    if not sponsor or sponsor.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Sponsor not found")
    sponsor.logo_data = None
    sponsor.logo_mime = None
    sponsor.logo_url = None
    await db.commit()
    return _sponsor_dict(sponsor)


@router.delete("/sponsors/{sponsor_id}")
async def delete_sponsor(
    sponsor_id: str,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    sponsor = await db.get(Sponsor, uuid.UUID(sponsor_id))
    if not sponsor or sponsor.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Sponsor not found")
    await db.delete(sponsor)
    await db.commit()
    return {"ok": True}


class SponsorReorderItem(BaseModel):
    id: str
    display_order: int


@router.put("/sponsors/reorder")
async def reorder_sponsors(
    items: list[SponsorReorderItem],
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    for item in items:
        sponsor = await db.get(Sponsor, uuid.UUID(item.id))
        if sponsor and sponsor.organisation_id == club.id:
            sponsor.display_order = item.display_order
    await db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Club user management — Main Admin assigns capabilities to club members
# ---------------------------------------------------------------------------


_INVITE_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Digits plus common separators (+, spaces, hyphens, parens); once those are
# stripped out there must be between 7 and 15 digits left — loose enough to
# take AU mobiles/landlines and international numbers, tight enough to catch
# obvious typos (E.164's own max length is 15 digits).
_MOBILE_STRIP_RE = re.compile(r"[\s\-()]")
_MOBILE_DIGITS_RE = re.compile(r"^\+?\d{7,15}$")
_INVITE_TOKEN_TTL_DAYS = 7
_PASSWORD_RESET_TOKEN_TTL_HOURS = 24


def _clean_mobile(raw: Optional[str]) -> Optional[str]:
    """Returns the trimmed mobile number, or raises 400 if it doesn't look
    like a phone number. None/blank passes through as None (the field stays
    optional)."""
    value = (raw or "").strip()
    if not value:
        return None
    if not _MOBILE_DIGITS_RE.match(_MOBILE_STRIP_RE.sub("", value)):
        raise HTTPException(400, "That doesn't look like a valid mobile number")
    return value


class ClubUserCreate(BaseModel):
    username: str
    display_name: Optional[str] = None
    email: str
    mobile_number: Optional[str] = None
    # Retained for backward-compat with older clients; ignored — every club
    # user is created as club_admin (club_member is retired). super_admin
    # invites go through the Super Admin console.
    role: str = "club_admin"
    capabilities: list[str] = []


class ClubUserUpdate(BaseModel):
    display_name: Optional[str] = None
    email: Optional[str] = None
    mobile_number: Optional[str] = None
    role: Optional[str] = None
    capabilities: Optional[list[str]] = None
    password: Optional[str] = None
    confirm_password: Optional[str] = None


@router.get("/users")
async def list_club_users(
    current_user: User = Depends(require_cap(MANAGE_USERS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """List members of this club with their role + capabilities."""
    rows = await db.execute(
        _text(
            """
            SELECT u.id, u.username, u.display_name, u.email, u.mobile_number, u.last_login_at,
                   cm.role, cm.capabilities
            FROM club_memberships cm
            JOIN users u ON u.id = cm.user_id
            WHERE cm.club_id = :org
            ORDER BY cm.role, COALESCE(u.display_name, u.username)
            """
        ),
        {"org": str(club.id)},
    )
    out = []
    for r in rows.mappings().all():
        out.append({
            "id": str(r["id"]),
            "username": r["username"],
            "display_name": r["display_name"],
            "email": r["email"],
            "mobile_number": r["mobile_number"],
            "last_login_at": r["last_login_at"].isoformat() if r["last_login_at"] else None,
            "role": r["role"],
            "capabilities": r["capabilities"] or [],
            "effective_capabilities": effective_capabilities(r["role"], r["capabilities"]),
        })
    return out


@router.get("/users/capabilities")
async def list_capabilities(
    _user: User = Depends(require_cap(MANAGE_USERS)),
):
    """All known capability constants — used by the UI to render checkboxes."""
    return {"capabilities": list(ALL_CAPABILITIES)}


@router.post("/users")
async def create_club_user(
    data: ClubUserCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_cap(MANAGE_USERS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Invite a colleague as a full club admin. No password is set here — the
    account is created with password_hash NULL plus a random invite token, and
    an email is sent with a link to /login?invite=<token> where the invited
    admin sets their own password (same strength rule as self-serve
    registration, see routers/auth.py's accept_invite) before they can log in.
    Mirrors the self-serve registration's own "don't hand a plaintext password
    around" reasoning, and closes the earlier gap where the inviting admin
    picked the new user's password on their behalf."""
    username = (data.username or "").strip().lower()
    email = (data.email or "").strip().lower()
    if not username:
        raise HTTPException(400, "Username is required")
    if not email or not _INVITE_EMAIL_RE.match(email):
        raise HTTPException(400, "A valid email address is required to invite the new admin")

    # club_member is retired — every invited user is a full club admin
    # (club_admin implies all capabilities).
    role = "club_admin"
    caps: list[str] = []

    # Username uniqueness only — email/mobile are format-checked (above /
    # _clean_mobile below) but not required to be unique at the moment.
    existing = await db.execute(_text("SELECT id FROM users WHERE username = :u"), {"u": username})
    if existing.first():
        raise HTTPException(409, "Username already in use")

    new_user_id = uuid.uuid4()
    invite_token = _secrets.token_urlsafe(32)
    invite_expires = _datetime.now(_timezone.utc) + _timedelta(days=_INVITE_TOKEN_TTL_DAYS)
    mobile_number = _clean_mobile(data.mobile_number)
    await db.execute(
        _text(
            "INSERT INTO users (id, username, display_name, email, mobile_number, "
            "password_hash, invite_token, invite_token_expires_at) "
            "VALUES (:id, :u, :d, :e, :m, NULL, :tok, :exp)"
        ),
        {
            "id": str(new_user_id), "u": username, "d": data.display_name,
            "e": email, "m": mobile_number, "tok": invite_token, "exp": invite_expires,
        },
    )
    await db.execute(
        _text(
            "INSERT INTO club_memberships (id, club_id, user_id, role, capabilities) "
            "VALUES (:id, :club, :uid, :role, CAST(:caps AS JSONB))"
        ),
        {
            "id": str(uuid.uuid4()),
            "club": str(club.id),
            "uid": str(new_user_id),
            "role": role,
            "caps": _json.dumps(caps),
        },
    )

    from app.services.audit_log import log_activity
    await log_activity(
        db, org_id=club.id, user_id=current_user.id,
        action="create_club_user", target_type="user", target_id=str(new_user_id),
        details={"username": username, "email": email, "role": role, "capabilities": caps},
    )

    await db.commit()

    from app.config.settings import settings as _settings
    from app.services.user_invite import send_invite_email
    invite_link = f"{_settings.public_base_url}/login?invite={invite_token}"
    background_tasks.add_task(
        send_invite_email, email=email, display_name=data.display_name or username,
        club_name=club.name, link=invite_link,
    )

    return {"id": str(new_user_id), "username": username, "role": role, "capabilities": caps, "invited": True}


@router.patch("/users/{user_id}")
async def update_club_user(
    user_id: str,
    data: ClubUserUpdate,
    current_user: User = Depends(require_cap(MANAGE_USERS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    # Confirm target is a member of this club
    row = await db.execute(
        _text(
            "SELECT cm.id AS membership_id, cm.role AS current_role, u.id AS user_id "
            "FROM club_memberships cm JOIN users u ON u.id = cm.user_id "
            "WHERE u.id = :uid AND cm.club_id = :club"
        ),
        {"uid": user_id, "club": str(club.id)},
    )
    target = row.mappings().first()
    if not target:
        raise HTTPException(404, "User not found in this club")

    # Role + capabilities are no longer editable here — club_member is retired,
    # so every club user is a full club admin. Display name, email, mobile
    # number and password (via the shared password_policy rule, same as the
    # user's own invite-accept/self-serve-registration flows) are.
    from app.services import password_policy

    changes = {}
    if data.display_name is not None:
        await db.execute(_text("UPDATE users SET display_name = :d WHERE id = :id"), {"d": data.display_name, "id": user_id})
        changes["display_name"] = True
    if data.email is not None:
        email = (data.email or "").strip().lower()
        if not email or not _INVITE_EMAIL_RE.match(email):
            raise HTTPException(400, "A valid email address is required")
        await db.execute(_text("UPDATE users SET email = :e WHERE id = :id"), {"e": email, "id": user_id})
        changes["email"] = True
    if data.mobile_number is not None:
        mobile_number = _clean_mobile(data.mobile_number)
        await db.execute(_text("UPDATE users SET mobile_number = :m WHERE id = :id"), {"m": mobile_number, "id": user_id})
        changes["mobile_number"] = True
    if data.password is not None:
        errors = password_policy.password_errors(data.password, data.confirm_password or "")
        if errors:
            raise HTTPException(status_code=422, detail={"errors": errors})
        await db.execute(_text("UPDATE users SET password_hash = :h WHERE id = :id"), {"h": _hash_password(data.password), "id": user_id})
        changes["password"] = True

    from app.services.audit_log import log_activity
    await log_activity(
        db, org_id=club.id, user_id=current_user.id,
        action="update_club_user", target_type="user", target_id=user_id,
        details={"changes": list(changes.keys()), **{k: v for k, v in changes.items() if k in ("role", "capabilities")}},
    )

    await db.commit()
    return {"status": "ok", **changes}


@router.post("/users/{user_id}/send-password-reset")
async def send_password_reset_link(
    user_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_cap(MANAGE_USERS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Email an existing club-user account a "reset your password" link,
    admin-triggered from the Club Users edit panel. Unlike the "Invite admin"
    flow (create_club_user), this account already has a working password —
    the reset uses its own token pair (password_reset_token) so the
    invite-accept endpoints (which 404 once password_hash is set) are left
    untouched, and the reset link is short-lived given it can replace a
    password already in active use."""
    row = await db.execute(
        _text(
            "SELECT u.id, u.email, u.display_name, u.username "
            "FROM club_memberships cm JOIN users u ON u.id = cm.user_id "
            "WHERE u.id = :uid AND cm.club_id = :club"
        ),
        {"uid": user_id, "club": str(club.id)},
    )
    target = row.mappings().first()
    if not target:
        raise HTTPException(404, "User not found in this club")
    if not target["email"]:
        raise HTTPException(400, "This user has no email address on file to send a reset link to")

    reset_token = _secrets.token_urlsafe(32)
    reset_expires = _datetime.now(_timezone.utc) + _timedelta(hours=_PASSWORD_RESET_TOKEN_TTL_HOURS)
    await db.execute(
        _text("UPDATE users SET password_reset_token = :tok, password_reset_token_expires_at = :exp WHERE id = :id"),
        {"tok": reset_token, "exp": reset_expires, "id": user_id},
    )

    from app.services.audit_log import log_activity
    await log_activity(
        db, org_id=club.id, user_id=current_user.id,
        action="send_password_reset_link", target_type="user", target_id=user_id,
    )
    await db.commit()

    from app.config.settings import settings as _settings
    from app.services.user_invite import send_password_reset_email
    reset_link = f"{_settings.public_base_url}/login?reset={reset_token}"
    background_tasks.add_task(
        send_password_reset_email, email=target["email"],
        display_name=target["display_name"] or target["username"],
        club_name=club.name, link=reset_link,
    )
    return {"status": "sent"}


@router.delete("/users/{user_id}")
async def remove_club_user(
    user_id: str,
    current_user: User = Depends(require_cap(MANAGE_USERS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    if str(current_user.id) == user_id:
        raise HTTPException(400, "Can't remove yourself")

    row = await db.execute(
        _text(
            "DELETE FROM club_memberships "
            "WHERE user_id = :uid AND club_id = :club "
            "RETURNING id"
        ),
        {"uid": user_id, "club": str(club.id)},
    )
    if not row.first():
        raise HTTPException(404, "User not found in this club")

    # club_memberships.uq_membership_one_per_user means the row just deleted
    # above was this user's ONLY membership, ever — nothing in the app ever
    # attaches a new membership to an existing user row (every invite/
    # self-serve flow mints a brand new one), so this account can never log
    # in again. Free its globally-unique username (and invalidate any
    # outstanding tokens) so the same username can be reused for a genuinely
    # new invite, without hard-deleting the row — every "who did this"
    # reference elsewhere (audit log, created_by/recorded_by columns) is an
    # ON DELETE SET NULL FK, so deleting the row would only orphan those
    # values, while this UPDATE keeps them resolvable. Was previously left
    # as a dangling row that squatted the username forever ("Username
    # already in use" on re-inviting the same person after removing them).
    await db.execute(
        _text(
            "UPDATE users SET username = NULL, password_hash = NULL, "
            "invite_token = NULL, invite_token_expires_at = NULL, "
            "password_reset_token = NULL, password_reset_token_expires_at = NULL "
            "WHERE id = :uid"
        ),
        {"uid": user_id},
    )

    from app.services.audit_log import log_activity
    await log_activity(
        db, org_id=club.id, user_id=current_user.id,
        action="remove_club_user", target_type="user", target_id=user_id,
    )

    await db.commit()
    return {"status": "removed"}


# ---------------------------------------------------------------------------
# Milestones report
# ---------------------------------------------------------------------------

@router.get("/milestones")
async def list_milestones_report(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Return upcoming + achieved milestones for all club players for admin reporting.

    grade_matches (games played in a named grade) is cross-club: a player who
    moved from another club carries their history in that grade with them,
    matching get_batting_by_grade/get_bowling_by_grade, the grade leaderboards,
    and the public Milestones endpoint (records.py). org_id here only scopes
    which players belong to this club and resolves this club's own grade-name
    aliases/merges; it never restricts which club's games get summed.
    """
    import datetime
    from app.services.milestone_rules import (
        next_threshold, reach_window, crossed_thresholds, is_displayable,
    )

    org_id = str(club.id)
    _CAT = {
        "runs": "batting",
        "wickets": "bowling",
        "catches": "fielding",
        "matches": "matches",
        "grade_matches": "matches",
    }

    # ------------------------------------------------------------------
    # Achieved: stored milestones (runs, wickets, matches, catches)
    # ------------------------------------------------------------------
    ach_rows = await db.execute(
        _text("""
            SELECT
                m.milestone_type, m.milestone_value, m.achieved_at, m.detail,
                p.id::text AS player_id,
                COALESCE(p.display_name_override, p.name) AS player_name,
                p.gender AS gender
            FROM milestones m
            JOIN players p ON p.id = m.player_id
            WHERE p.organisation_id = :org_id
              AND p.is_player = TRUE
            ORDER BY m.achieved_at DESC NULLS LAST, m.milestone_value DESC
        """),
        {"org_id": org_id},
    )
    achieved = []
    for r in ach_rows.mappings().all():
        mt = r["milestone_type"]
        mv = r["milestone_value"]
        if not is_displayable(mt, mv):
            continue
        achieved.append({
            "player_id": r["player_id"],
            "player_name": r["player_name"],
            "gender": r["gender"],
            "type": mt,
            "category": _CAT.get(mt, "matches"),
            "milestone_value": mv,
            "achieved_at": r["achieved_at"].isoformat() if r["achieved_at"] else None,
            "detail": r["detail"],
        })

    # ------------------------------------------------------------------
    # Achieved: computed grade_matches (all players, bulk SQL)
    # ------------------------------------------------------------------
    gm_rows = await db.execute(
        _text("""
            SELECT
                p.id::text AS player_id,
                COALESCE(p.display_name_override, p.name) AS player_name,
                p.gender AS gender,
                COALESCE(gdn.display_name_override, COALESCE(am.canonical_name, gr.name)) AS grade_name,
                COUNT(DISTINCT ga.game_id) AS matches
            FROM game_appearances ga
            JOIN players p ON p.id = ga.player_id
            JOIN games g ON g.id = ga.game_id
            JOIN grades gr ON gr.id = g.grade_id
            LEFT JOIN LATERAL (
                SELECT canonical_name FROM grade_merge_logs gml
                WHERE gml.org_id = CAST(:org_id AS UUID)
                  AND gml.alias_name = gr.name AND gml.undone_at IS NULL
                LIMIT 1
            ) am ON TRUE
            LEFT JOIN LATERAL (
                SELECT gr2.display_name_override FROM grades gr2
                JOIN seasons s2 ON s2.id = gr2.season_id
                WHERE s2.organisation_id = CAST(:org_id AS UUID)
                  AND gr2.name = COALESCE(am.canonical_name, gr.name)
                  AND gr2.display_name_override IS NOT NULL
                LIMIT 1
            ) gdn ON TRUE
            WHERE p.organisation_id = :org_id AND p.is_player = TRUE
            GROUP BY p.id, COALESCE(p.display_name_override, p.name), p.gender,
                     COALESCE(gdn.display_name_override, COALESCE(am.canonical_name, gr.name))
            HAVING COUNT(DISTINCT ga.game_id) >= 50
        """),
        {"org_id": org_id},
    )
    for r in gm_rows.mappings().all():
        n = int(r["matches"])
        grade_name = r["grade_name"]
        if not grade_name:
            continue
        for threshold in crossed_thresholds("grade_matches", n):
            achieved.append({
                "player_id": r["player_id"],
                "player_name": r["player_name"],
                "gender": r["gender"],
                "type": "grade_matches",
                "category": "matches",
                "milestone_value": threshold,
                "achieved_at": None,
                "detail": grade_name,
            })

    # ------------------------------------------------------------------
    # Upcoming: active players only (stats in last 3 seasons)
    # ------------------------------------------------------------------
    current_year = datetime.date.today().year
    cutoff = current_year - 2

    totals_rows = await db.execute(
        _text("""
            WITH active_ids AS (
                SELECT DISTINCT pss.player_id
                FROM player_season_stats pss
                JOIN seasons s ON s.id = pss.season_id
                WHERE s.organisation_id = :org_id
                  AND (s.year IS NULL OR s.year >= :cutoff)
            )
            SELECT
                p.id::text AS player_id,
                COALESCE(p.display_name_override, p.name) AS player_name,
                p.gender AS gender,
                COALESCE(SUM(pss.runs), 0)    AS total_runs,
                COALESCE(SUM(pss.wickets), 0) AS total_wickets,
                COALESCE(SUM(pss.matches), 0) AS total_matches,
                COALESCE(SUM(pss.catches), 0) AS total_catches
            FROM players p
            JOIN active_ids ai ON ai.player_id = p.id
            JOIN player_season_stats pss ON pss.player_id = p.id
                -- Only this org's seasons (shared cross-club GUID guard, migration 060)
                AND EXISTS (
                    SELECT 1 FROM seasons s2
                    WHERE s2.id = pss.season_id AND s2.organisation_id = :org_id
                )
            WHERE p.organisation_id = :org_id AND p.is_player = TRUE
            GROUP BY p.id, COALESCE(p.display_name_override, p.name), p.gender
            ORDER BY COALESCE(p.display_name_override, p.name)
        """),
        {"org_id": org_id, "cutoff": cutoff},
    )

    upcoming = []
    stat_defs = [
        ("runs",    "batting",  "total_runs"),
        ("wickets", "bowling",  "total_wickets"),
        ("matches", "matches",  "total_matches"),
        ("catches", "fielding", "total_catches"),
    ]
    for r in totals_rows.mappings().all():
        for mt, cat, col in stat_defs:
            current = int(r[col] or 0)
            target = next_threshold(mt, current)
            if target is None:
                continue
            needed = target - current
            if needed > reach_window(mt, target):
                continue
            upcoming.append({
                "player_id": r["player_id"],
                "player_name": r["player_name"],
                "gender": r["gender"],
                "type": mt,
                "category": cat,
                "current": current,
                "target": target,
                "needed": needed,
                "detail": None,
            })

    # Upcoming: grade milestones for active players
    gu_rows = await db.execute(
        _text("""
            WITH active_ids AS (
                SELECT DISTINCT pss.player_id
                FROM player_season_stats pss
                JOIN seasons s ON s.id = pss.season_id
                WHERE s.organisation_id = :org_id
                  AND (s.year IS NULL OR s.year >= :cutoff)
            )
            SELECT
                p.id::text AS player_id,
                COALESCE(p.display_name_override, p.name) AS player_name,
                p.gender AS gender,
                COALESCE(gdn.display_name_override, COALESCE(am.canonical_name, gr.name)) AS grade_name,
                COUNT(DISTINCT ga.game_id) AS matches
            FROM game_appearances ga
            JOIN players p ON p.id = ga.player_id
            JOIN active_ids ai ON ai.player_id = p.id
            JOIN games g ON g.id = ga.game_id
            JOIN grades gr ON gr.id = g.grade_id
            LEFT JOIN LATERAL (
                SELECT canonical_name FROM grade_merge_logs gml
                WHERE gml.org_id = CAST(:org_id AS UUID)
                  AND gml.alias_name = gr.name AND gml.undone_at IS NULL
                LIMIT 1
            ) am ON TRUE
            LEFT JOIN LATERAL (
                SELECT gr2.display_name_override FROM grades gr2
                JOIN seasons s2 ON s2.id = gr2.season_id
                WHERE s2.organisation_id = CAST(:org_id AS UUID)
                  AND gr2.name = COALESCE(am.canonical_name, gr.name)
                  AND gr2.display_name_override IS NOT NULL
                LIMIT 1
            ) gdn ON TRUE
            WHERE p.organisation_id = :org_id AND p.is_player = TRUE
            GROUP BY p.id, COALESCE(p.display_name_override, p.name), p.gender,
                     COALESCE(gdn.display_name_override, COALESCE(am.canonical_name, gr.name))
        """),
        {"org_id": org_id, "cutoff": cutoff},
    )
    for r in gu_rows.mappings().all():
        n = int(r["matches"])
        grade_name = r["grade_name"]
        if not grade_name:
            continue
        target = next_threshold("grade_matches", n)
        if target is None:
            continue
        needed = target - n
        if needed > reach_window("grade_matches", target):
            continue
        upcoming.append({
            "player_id": r["player_id"],
            "player_name": r["player_name"],
            "gender": r["gender"],
            "type": "grade_matches",
            "category": "matches",
            "current": n,
            "target": target,
            "needed": needed,
            "detail": grade_name,
        })

    upcoming.sort(key=lambda m: m["needed"])

    return {"upcoming": upcoming, "achieved": achieved}
