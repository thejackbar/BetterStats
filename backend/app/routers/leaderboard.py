from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import logging
import uuid

from app.models.db import User, get_db
from app.routers.auth import get_optional_user, public_junior_hiding, user_can_view_org_private
from app.services import grade_scope
from app.services import player_visibility
from app.services import stats_display
from app.services.session_safety import rollback_keeping
from app.services.aggregations import (
    raise_board_games_to_grid,
    get_batting_leaderboard, get_bowling_leaderboard, get_fielding_leaderboard,
    get_batting_leaderboard_extended, get_bowling_leaderboard_extended,
    get_sirs_batting, get_sirs_bowling_innings, get_sirs_bowling_match,
)

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


def _stringify(rows: list[dict]) -> list[dict]:
    return [{k: str(v) if isinstance(v, uuid.UUID) else v for k, v in r.items()} for r in rows]


async def _scope(db: AsyncSession, viewer, org_id, categories, formats, competitions):
    """The grade scope for a leaderboard, minus what the club hides from THIS viewer.

    A club that hides its juniors (services/junior_hiding) has its junior
    grades left out of every board for the public, whatever category, format or
    competition was picked. A club admin, and every club that has not switched
    it on, gets exactly the scope they always did.
    """
    hiding = await public_junior_hiding(db, viewer, org_id, with_players=False)
    return await grade_scope.resolve_scope(
        db, org_id, categories, formats=formats, competitions=competitions,
        hidden_grade_ids=hiding.grade_ids,
    )


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


async def _games_like_profile(db: AsyncSession, org_id: str, rows: list[dict], season_id, scope,
                              viewer, *, finals_only, captain_only, grade_id, grade_name) -> list[dict]:
    """Raise each row's games to what the player's profile shows (never lower).

    The profile's MATCHES is raised to its by-grade grid, which counts the matches
    Cricket Australia's per-grade totals claim and we hold no scorecard for; the
    board's M column counted only what we hold, so nearly every player read lower
    on the board than on their own page. Skipped where the figure means something
    else: finals-only (finals played), captain-only (matches as captain) and a
    picked grade (that grade's matches). A failure leaves the figures as they were.
    """
    if finals_only or captain_only or grade_id or grade_name:
        return rows
    try:
        return await raise_board_games_to_grid(db, org_id, rows, season_id, scope)
    except Exception:
        await rollback_keeping(db, viewer)
        logging.getLogger(__name__).exception("board games vs profile failed for org %s", org_id)
        return rows


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
    competitions: Optional[str] = Query(
        None,
        description=(
            "Comma-separated club competition ids to count. A competition is "
            "the club's own named group of grades (services/competitions.py), "
            "seeded one per association — so this is what tells one "
            "association's cricket from another's, and one competition of an "
            "association from the next. Omitted applies no competition filter."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
):
    scope = await _scope(db, viewer, org_id, categories, formats, competitions)
    rows = await get_batting_leaderboard_extended(
        db, org_id, season_id, grade_id, sort_by, limit,
        min_runs=min_runs,
        min_rate_innings=await stats_display.resolve_min_rate_innings(db, org_id, min_rate_innings),
        grade_name=grade_name, finals_only=finals_only, captain_only=captain_only,
        gender=gender, overseas=overseas, scope=scope)
    rows = await _visible(db, org_id, viewer, rows)
    rows = await _games_like_profile(db, org_id, rows, season_id, scope, viewer, finals_only=finals_only,
                                     captain_only=captain_only, grade_id=grade_id, grade_name=grade_name)
    return _stringify(rows)


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
    competitions: Optional[str] = Query(
        None,
        description=(
            "Comma-separated club competition ids to count. A competition is "
            "the club's own named group of grades (services/competitions.py), "
            "seeded one per association — so this is what tells one "
            "association's cricket from another's, and one competition of an "
            "association from the next. Omitted applies no competition filter."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
):
    scope = await _scope(db, viewer, org_id, categories, formats, competitions)
    rows = await get_bowling_leaderboard_extended(
        db, org_id, season_id, grade_id, sort_by, limit,
        min_overs=min_overs, min_wickets=min_wickets,
        min_rate_spells=await stats_display.resolve_min_rate_spells(db, org_id, min_rate_spells),
        grade_name=grade_name, finals_only=finals_only, captain_only=captain_only,
        gender=gender, overseas=overseas, scope=scope)
    rows = await _visible(db, org_id, viewer, rows)
    rows = await _games_like_profile(db, org_id, rows, season_id, scope, viewer, finals_only=finals_only,
                                     captain_only=captain_only, grade_id=grade_id, grade_name=grade_name)
    return _stringify(rows)


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
    competitions: Optional[str] = Query(
        None,
        description=(
            "Comma-separated club competition ids to count. A competition is "
            "the club's own named group of grades (services/competitions.py), "
            "seeded one per association — so this is what tells one "
            "association's cricket from another's, and one competition of an "
            "association from the next. Omitted applies no competition filter."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
):
    scope = await _scope(db, viewer, org_id, categories, formats, competitions)
    rows = await get_fielding_leaderboard(db, org_id, season_id, grade_id, sort_by, limit, grade_name, finals_only=finals_only, captain_only=captain_only, gender=gender, overseas=overseas, scope=scope)
    rows = await _visible(db, org_id, viewer, rows)
    rows = await _games_like_profile(db, org_id, rows, season_id, scope, viewer, finals_only=finals_only,
                                     captain_only=captain_only, grade_id=grade_id, grade_name=grade_name)
    if sort_by == "games":
        # The limit was applied before the raise, so keep the order the figures now imply.
        rows.sort(key=lambda r: -(r.get("games") or 0))
    return _stringify(rows)


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
    competitions: Optional[str] = Query(
        None,
        description=(
            "Comma-separated club competition ids to count. A competition is "
            "the club's own named group of grades (services/competitions.py), "
            "seeded one per association — so this is what tells one "
            "association's cricket from another's, and one competition of an "
            "association from the next. Omitted applies no competition filter."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
):
    scope = await _scope(db, viewer, org_id, categories, formats, competitions)
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
    competitions: Optional[str] = Query(
        None,
        description=(
            "Comma-separated club competition ids to count. A competition is "
            "the club's own named group of grades (services/competitions.py), "
            "seeded one per association — so this is what tells one "
            "association's cricket from another's, and one competition of an "
            "association from the next. Omitted applies no competition filter."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
):
    scope = await _scope(db, viewer, org_id, categories, formats, competitions)
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
    competitions: Optional[str] = Query(
        None,
        description=(
            "Comma-separated club competition ids to count. A competition is "
            "the club's own named group of grades (services/competitions.py), "
            "seeded one per association — so this is what tells one "
            "association's cricket from another's, and one competition of an "
            "association from the next. Omitted applies no competition filter."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
):
    scope = await _scope(db, viewer, org_id, categories, formats, competitions)
    return await _visible(db, org_id, viewer, await get_sirs_bowling_match(db, org_id, season_id, grade_name, finals_only, limit, captain_only=captain_only, gender=gender, overseas=overseas, scope=scope))
