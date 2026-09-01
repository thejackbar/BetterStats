from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import uuid

from app.models.db import User, get_db
from app.routers.auth import get_optional_user, user_can_view_org_private
from app.services import grade_scope
from app.services import player_visibility
from app.services import stats_display
from app.services.aggregations import (
    get_batting_leaderboard, get_bowling_leaderboard, get_fielding_leaderboard,
    get_batting_leaderboard_extended, get_bowling_leaderboard_extended,
    get_sirs_batting, get_sirs_bowling_innings, get_sirs_bowling_match,
)

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


def _stringify(rows: list[dict]) -> list[dict]:
    return [{k: str(v) if isinstance(v, uuid.UUID) else v for k, v in r.items()} for r in rows]


async def _visible(db: AsyncSession, org_id: str, viewer, rows: list[dict]) -> list[dict]:
    """Drop players the club has hidden from its public site.

    Applied here rather than inside the leaderboard builders: each of those
    has several query branches (finals, captain, the aggregate/per-innings
    split) and every row they return already carries its player_id, so one
    filter at the endpoint covers all of them. A signed-in club admin sees
    their own club whole, exactly as they do for a hidden grade.
    """
    public_only = not await user_can_view_org_private(db, viewer, org_id)
    return await player_visibility.filter_public_rows(db, org_id, rows, public_only)


@router.get("/batting")
async def batting_leaderboard(
    org_id: str,
    season_id: Optional[str] = Query(None),
    grade_id: Optional[str] = Query(None),
    grade_name: Optional[str] = Query(None),
    sort_by: str = Query("total_runs"),
    limit: int = Query(20, le=5000),
    min_runs: int = Query(0),
    min_rate_innings: Optional[int] = Query(
        None,
        description=(
            "Fewest innings WITH A BALL COUNT a player must have before a strike "
            "rate is published for them. Counted on covered innings, not innings "
            "played — see services/rate_coverage.py. Omitted uses the club's own "
            "default; 0 turns the qualification off."
        ),
    ),
    finals_only: Optional[bool] = Query(None),
    captain_only: Optional[bool] = Query(None),
    gender: Optional[str] = Query(None),
    overseas: Optional[str] = Query(None),
    categories: Optional[str] = Query(
        None,
        description=(
            "Comma-separated grade categories to count — senior, junior, womens, "
            "masters, mixed, or 'all'. Omitted uses the club's own default, which "
            "leaves junior out. Ignored when an explicit grade is picked."
        ),
    ),
    formats: Optional[str] = Query(
        None,
        description=(
            "Comma-separated match formats to count — two_day, one_day, t20, or "
            "'all'. Matched per FIXTURE against each game's own match_format, "
            "not per grade, so a grade that plays both is split correctly. "
            "Omitted applies no format filter."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
):
    scope = await grade_scope.resolve_scope(db, org_id, categories, formats=formats)
    rows = await get_batting_leaderboard_extended(
        db, org_id, season_id, grade_id, sort_by, limit,
        min_runs=min_runs,
        min_rate_innings=await stats_display.resolve_min_rate_innings(db, org_id, min_rate_innings),
        grade_name=grade_name, finals_only=finals_only, captain_only=captain_only,
        gender=gender, overseas=overseas, scope=scope)
    return _stringify(await _visible(db, org_id, viewer, rows))


@router.get("/bowling")
async def bowling_leaderboard(
    org_id: str,
    season_id: Optional[str] = Query(None),
    grade_id: Optional[str] = Query(None),
    grade_name: Optional[str] = Query(None),
    sort_by: str = Query("total_wickets"),
    limit: int = Query(20, le=5000),
    min_overs: int = Query(0),
    min_wickets: int = Query(0),
    min_rate_spells: Optional[int] = Query(
        None,
        description=(
            "Fewest spells WITH AN OVERS FIGURE a player must have before an "
            "economy is published for them. Omitted uses the club's own default; "
            "0 turns the qualification off."
        ),
    ),
    finals_only: Optional[bool] = Query(None),
    captain_only: Optional[bool] = Query(None),
    gender: Optional[str] = Query(None),
    overseas: Optional[str] = Query(None),
    categories: Optional[str] = Query(
        None,
        description=(
            "Comma-separated grade categories to count — senior, junior, womens, "
            "masters, mixed, or 'all'. Omitted uses the club's own default, which "
            "leaves junior out. Ignored when an explicit grade is picked."
        ),
    ),
    formats: Optional[str] = Query(
        None,
        description=(
            "Comma-separated match formats to count — two_day, one_day, t20, or "
            "'all'. Matched per FIXTURE against each game's own match_format, "
            "not per grade, so a grade that plays both is split correctly. "
            "Omitted applies no format filter."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
):
    scope = await grade_scope.resolve_scope(db, org_id, categories, formats=formats)
    rows = await get_bowling_leaderboard_extended(
        db, org_id, season_id, grade_id, sort_by, limit,
        min_overs=min_overs, min_wickets=min_wickets,
        min_rate_spells=await stats_display.resolve_min_rate_spells(db, org_id, min_rate_spells),
        grade_name=grade_name, finals_only=finals_only, captain_only=captain_only,
        gender=gender, overseas=overseas, scope=scope)
    return _stringify(await _visible(db, org_id, viewer, rows))


@router.get("/fielding")
async def fielding_leaderboard(
    org_id: str,
    season_id: Optional[str] = Query(None),
    grade_id: Optional[str] = Query(None),
    grade_name: Optional[str] = Query(None),
    sort_by: str = Query("total_dismissals"),
    limit: int = Query(20, le=50),
    finals_only: Optional[bool] = Query(None),
    captain_only: Optional[bool] = Query(None),
    gender: Optional[str] = Query(None),
    overseas: Optional[str] = Query(None),
    categories: Optional[str] = Query(
        None,
        description=(
            "Comma-separated grade categories to count — senior, junior, womens, "
            "masters, mixed, or 'all'. Omitted uses the club's own default, which "
            "leaves junior out. Ignored when an explicit grade is picked."
        ),
    ),
    formats: Optional[str] = Query(
        None,
        description=(
            "Comma-separated match formats to count — two_day, one_day, t20, or "
            "'all'. Matched per FIXTURE against each game's own match_format, "
            "not per grade, so a grade that plays both is split correctly. "
            "Omitted applies no format filter."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
):
    scope = await grade_scope.resolve_scope(db, org_id, categories, formats=formats)
    rows = await get_fielding_leaderboard(db, org_id, season_id, grade_id, sort_by, limit, grade_name, finals_only=finals_only, captain_only=captain_only, gender=gender, overseas=overseas, scope=scope)
    return _stringify(await _visible(db, org_id, viewer, rows))


@router.get("/sirs/batting")
async def sirs_batting(
    org_id: str,
    season_id: Optional[str] = Query(None),
    grade_name: Optional[str] = Query(None),
    finals_only: Optional[bool] = Query(None),
    captain_only: Optional[bool] = Query(None),
    limit: int = Query(200, le=500),
    gender: Optional[str] = Query(None),
    overseas: Optional[str] = Query(None),
    categories: Optional[str] = Query(
        None,
        description=(
            "Comma-separated grade categories to count — senior, junior, womens, "
            "masters, mixed, or 'all'. Omitted uses the club's own default, which "
            "leaves junior out. Ignored when an explicit grade is picked."
        ),
    ),
    formats: Optional[str] = Query(
        None,
        description=(
            "Comma-separated match formats to count — two_day, one_day, t20, or "
            "'all'. Matched per FIXTURE against each game's own match_format, "
            "not per grade, so a grade that plays both is split correctly. "
            "Omitted applies no format filter."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
):
    scope = await grade_scope.resolve_scope(db, org_id, categories, formats=formats)
    return await _visible(db, org_id, viewer, await get_sirs_batting(db, org_id, season_id, grade_name, finals_only, limit, captain_only=captain_only, gender=gender, overseas=overseas, scope=scope))


@router.get("/sirs/bowling-innings")
async def sirs_bowling_innings(
    org_id: str,
    season_id: Optional[str] = Query(None),
    grade_name: Optional[str] = Query(None),
    finals_only: Optional[bool] = Query(None),
    captain_only: Optional[bool] = Query(None),
    limit: int = Query(200, le=500),
    gender: Optional[str] = Query(None),
    overseas: Optional[str] = Query(None),
    categories: Optional[str] = Query(
        None,
        description=(
            "Comma-separated grade categories to count — senior, junior, womens, "
            "masters, mixed, or 'all'. Omitted uses the club's own default, which "
            "leaves junior out. Ignored when an explicit grade is picked."
        ),
    ),
    formats: Optional[str] = Query(
        None,
        description=(
            "Comma-separated match formats to count — two_day, one_day, t20, or "
            "'all'. Matched per FIXTURE against each game's own match_format, "
            "not per grade, so a grade that plays both is split correctly. "
            "Omitted applies no format filter."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
):
    scope = await grade_scope.resolve_scope(db, org_id, categories, formats=formats)
    return await _visible(db, org_id, viewer, await get_sirs_bowling_innings(db, org_id, season_id, grade_name, finals_only, limit, captain_only=captain_only, gender=gender, overseas=overseas, scope=scope))


@router.get("/sirs/bowling-match")
async def sirs_bowling_match(
    org_id: str,
    season_id: Optional[str] = Query(None),
    grade_name: Optional[str] = Query(None),
    finals_only: Optional[bool] = Query(None),
    captain_only: Optional[bool] = Query(None),
    limit: int = Query(200, le=500),
    gender: Optional[str] = Query(None),
    overseas: Optional[str] = Query(None),
    categories: Optional[str] = Query(
        None,
        description=(
            "Comma-separated grade categories to count — senior, junior, womens, "
            "masters, mixed, or 'all'. Omitted uses the club's own default, which "
            "leaves junior out. Ignored when an explicit grade is picked."
        ),
    ),
    formats: Optional[str] = Query(
        None,
        description=(
            "Comma-separated match formats to count — two_day, one_day, t20, or "
            "'all'. Matched per FIXTURE against each game's own match_format, "
            "not per grade, so a grade that plays both is split correctly. "
            "Omitted applies no format filter."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
):
    scope = await grade_scope.resolve_scope(db, org_id, categories, formats=formats)
    return await _visible(db, org_id, viewer, await get_sirs_bowling_match(db, org_id, season_id, grade_name, finals_only, limit, captain_only=captain_only, gender=gender, overseas=overseas, scope=scope))
