"""Admin API routes — all require authentication."""
import json as _json
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
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
    PlayerSyncRequest, Sponsor, ClubOnboardingRequest, get_db
)
from sqlalchemy import text as _text
import asyncio
import logging as _logging
from app.routers.auth import get_current_user, get_current_club, require_super_admin, _hash_password
from app.auth.capabilities import (
    require_cap, effective_capabilities, ALL_CAPABILITIES,
    MANAGE_SETTINGS, MANAGE_MERGES, MANAGE_USERS, RUN_HARD_REFRESH, RUN_SYNC,
)
from app.auth.modules import (
    ALL_MODULES, ALL_STATUSES, ALL_BILLING_CYCLES, org_entitled_modules,
)
from datetime import date as _date
from app.services import playhq_client
from app.services.name_format import name_sort_key

# Keep strong references to background tasks so they aren't GC'd before completing
_background_tasks: set = set()
# Per-player deep sync locks
_player_sync_running: set = set()

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


# Keys allowed inside theme_config and the sub-keys allowed in light/dark palettes.
_THEME_COLOR_KEYS = {
    "accent", "positive", "negative",
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
    name = name.strip()
    if ", " in name:
        parts = name.split(", ", 1)
        name = f"{parts[1]} {parts[0]}"
    return re.sub(r"\s+", " ", name).lower()


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
                FROM partnerships pt
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


@router.get("/super/clubs")
async def list_all_clubs(
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Organisation).order_by(Organisation.name))
    orgs = result.scalars().all()
    return [
        {
            "id": str(o.id),
            "slug": o.slug,
            "name": o.name,
            "short_name": o.short_name,
            "is_active": o.is_active,
            "contact_email": o.contact_email,
            "module_overrides": list(o.module_overrides or []),
            "modules": sorted(org_entitled_modules(o)),
            "subscription_status": o.subscription_status,
            "renewal_date": o.renewal_date.isoformat() if o.renewal_date else None,
            "billing_cycle": o.billing_cycle,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        }
        for o in orgs
    ]


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
    await db.commit()
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


@router.patch("/super/clubs/{club_id}")
async def patch_club(
    club_id: str,
    data: ClubUpdate,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    org = await db.get(Organisation, uuid.UUID(club_id))
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

    if "module_overrides" in fields:
        overrides = fields["module_overrides"] or []
        unknown = [m for m in overrides if m not in ALL_MODULES]
        if unknown:
            raise HTTPException(status_code=422, detail=f"Unknown modules: {', '.join(unknown)}")
        fields["module_overrides"] = sorted(set(overrides))

    if "subscription_status" in fields:
        if fields["subscription_status"] not in ALL_STATUSES:
            raise HTTPException(status_code=422, detail=f"Status must be one of: {', '.join(ALL_STATUSES)}")

    if fields.get("billing_cycle") is not None and fields["billing_cycle"] not in ALL_BILLING_CYCLES:
        raise HTTPException(status_code=422, detail=f"Billing cycle must be one of: {', '.join(ALL_BILLING_CYCLES)}")

    for key, value in fields.items():
        setattr(org, key, value)

    await db.commit()
    return {
        "id": str(org.id),
        "slug": org.slug,
        "name": org.name,
        "is_active": org.is_active,
        "module_overrides": list(org.module_overrides or []),
        "modules": sorted(org_entitled_modules(org)),
        "subscription_status": org.subscription_status,
        "renewal_date": org.renewal_date.isoformat() if org.renewal_date else None,
        "billing_cycle": org.billing_cycle,
    }


@router.delete("/super/clubs/{club_id}")
async def delete_club(
    club_id: str,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    org = await db.get(Organisation, uuid.UUID(club_id))
    if not org:
        raise HTTPException(status_code=404, detail="Club not found")

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
            "role": r.ClubMembership.role if r.ClubMembership else None,
            "club_name": r.Organisation.name if r.Organisation else None,
            "club_id": str(r.ClubMembership.club_id) if r.ClubMembership else None,
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
    from app.services.sync import sync_organisation, start_sync_run, finish_sync_run, update_sync_run
    from app.services.rate_limit import enforce
    org_id_str = str(club.id)

    # 1 hard-refresh per club per hour. The operation itself takes 1h+ and
    # the in-progress guard below blocks a *concurrent* second call, but
    # nothing stops a user clicking the button repeatedly during the run or
    # right after it finishes. This window covers both cases.
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
            await update_sync_run(run_id, {"progress_phase": "Clearing stored games", "progress_pct": 0})
            # Wipe phase — games with batting rows whose seasons belong to this org.
            from app.models.db import async_session_maker
            from sqlalchemy import text as _t
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
            await finish_sync_run(run_id, stats)
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


class ClubUserCreate(BaseModel):
    username: str
    display_name: Optional[str] = None
    password: str
    # Retained for backward-compat with older clients; ignored — every club
    # user is created as club_admin (club_member is retired). super_admin
    # invites go through the Super Admin console.
    role: str = "club_admin"
    capabilities: list[str] = []


class ClubUserUpdate(BaseModel):
    display_name: Optional[str] = None
    role: Optional[str] = None
    capabilities: Optional[list[str]] = None
    password: Optional[str] = None


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
            SELECT u.id, u.username, u.display_name, u.last_login_at,
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
    current_user: User = Depends(require_cap(MANAGE_USERS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    username = (data.username or "").strip().lower()
    if not username or len(data.password) < 6:
        raise HTTPException(400, "Username required and password must be 6+ chars")

    # club_member is retired — every invited user is a full club admin
    # (club_admin implies all capabilities).
    role = "club_admin"
    caps: list[str] = []

    # Username uniqueness
    existing = await db.execute(_text("SELECT id FROM users WHERE username = :u"), {"u": username})
    if existing.first():
        raise HTTPException(409, "Username already in use")

    new_user_id = uuid.uuid4()
    await db.execute(
        _text(
            "INSERT INTO users (id, username, display_name, password_hash) "
            "VALUES (:id, :u, :d, :h)"
        ),
        {"id": str(new_user_id), "u": username, "d": data.display_name, "h": _hash_password(data.password)},
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
        details={"username": username, "role": role, "capabilities": caps},
    )

    await db.commit()
    return {"id": str(new_user_id), "username": username, "role": role, "capabilities": caps}


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
    # so every club user is a full club admin. Only display name + password.
    changes = {}
    if data.display_name is not None:
        await db.execute(_text("UPDATE users SET display_name = :d WHERE id = :id"), {"d": data.display_name, "id": user_id})
        changes["display_name"] = True
    if data.password is not None:
        if len(data.password) < 6:
            raise HTTPException(400, "Password must be 6+ chars")
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
    """Return upcoming + achieved milestones for all club players for admin reporting."""
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
                COALESCE(p.display_name_override, p.name) AS player_name
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
                COALESCE(gdn.display_name_override, COALESCE(am.canonical_name, gr.name)) AS grade_name,
                COUNT(DISTINCT ga.game_id) AS matches
            FROM game_appearances ga
            JOIN players p ON p.id = ga.player_id
            JOIN games g ON g.id = ga.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
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
            WHERE s.organisation_id = :org_id AND p.is_player = TRUE
            GROUP BY p.id, COALESCE(p.display_name_override, p.name),
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
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
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
                COALESCE(gdn.display_name_override, COALESCE(am.canonical_name, gr.name)) AS grade_name,
                COUNT(DISTINCT ga.game_id) AS matches
            FROM game_appearances ga
            JOIN players p ON p.id = ga.player_id
            JOIN active_ids ai ON ai.player_id = p.id
            JOIN games g ON g.id = ga.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
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
            WHERE s.organisation_id = :org_id AND p.is_player = TRUE
            GROUP BY p.id, COALESCE(p.display_name_override, p.name),
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
            "type": "grade_matches",
            "category": "matches",
            "current": n,
            "target": target,
            "needed": needed,
            "detail": grade_name,
        })

    upcoming.sort(key=lambda m: m["needed"])

    return {"upcoming": upcoming, "achieved": achieved}
