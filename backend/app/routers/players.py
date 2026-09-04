from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, func
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel
from typing import Optional
from datetime import date
import uuid

from app.models.db import (
    Player, User, PlayerSyncRequest, Team, Organisation,
    BattingInnings, BowlingSpell, FieldingStat, Game, Grade, Season,
    Fixture, FixtureLineup, PlayerAvailability, get_db,
)
from app.routers.auth import get_current_user, get_optional_user, user_can_view_org_private, get_current_club
from app.auth.capabilities import require_cap, MANAGE_PLAYERS
from app.services.squad_membership import sync_squad_membership
from app.services.name_format import name_sort_key
from app.services.aggregations import (
    get_career_batting, get_career_bowling, get_career_fielding,
    get_career_batting_from_innings, get_career_bowling_from_spells, get_career_fielding_from_stats,
    get_player_batting_innings, get_player_bowling_spells,
    get_dismissal_breakdown, get_batting_by_position, get_batting_by_grade,
    get_bowling_by_grade, get_player_team_breakdown,
    get_bowling_dismissal_breakdown, get_bowling_by_batter_position,
    get_season_by_season, get_player_milestones, get_player_partnerships,
    get_player_activity, get_upcoming_milestones_for_org,
    get_player_rankings, get_player_by_venue, get_player_by_opposition,
    _club_game_clause,
)
from app.services.milestone_rules import (
    crossed_thresholds, is_displayable, next_threshold, reach_window,
)
from app.services import iq_teammates
from app.services import grade_scope
from app.services.player_aliases import normalise_name_key, seed_alias_on_rename
from app.services.player_age import age_on, dob_error, visible_age
from app.services.player_formats import player_format_splits

router = APIRouter(prefix="/players", tags=["players"])


async def _resolve_player_scope(
    db: AsyncSession, player: Player, categories: Optional[str],
    formats: Optional[str] = None, competitions: Optional[str] = None,
):
    """Same grade-type and match-type scope the career/grade breakdowns use, for
    the rest of the Analysis-tab sub-endpoints (dismissals, by-position,
    by-venue, by-opposition, partnerships, ...). Every one of them reads the same
    per-game rows the scoped career totals do, so a player with the Juniors
    filter on, or Match Type set to T20 or one competition, must not have an
    out-of-scope game reappear in one of these without the other."""
    org = await db.get(Organisation, player.organisation_id) if player.organisation_id else None
    scope, _ = await grade_scope.resolve_scope_for_player(
        db, player.organisation_id, str(player.id), categories, formats=formats,
        competitions=competitions,
        auto_widen=bool(org.stats_auto_show_played_grades) if org else True,
    )
    return scope


def _str_keys(d: dict | None) -> dict | None:
    if not d:
        return d
    return {k: str(v) if isinstance(v, uuid.UUID) else v for k, v in d.items()}


async def _public_player_attrs(db: AsyncSession, player: Player) -> dict:
    """Descriptive player attributes the club has opted to show publicly.

    Overseas is handled separately (always shown). Everything here is gated by a
    per-club setting so the value is omitted entirely from the public payload
    when the toggle is off — the public profile simply renders whatever fields
    are present.
    """
    if not player.organisation_id:
        return {}
    org = await db.get(Organisation, player.organisation_id)
    if not org:
        return {}
    attrs: dict = {}
    if org.public_show_role and player.player_role:
        attrs["player_role"] = player.player_role
    if org.public_show_batting and player.batting_hand:
        attrs["batting_hand"] = player.batting_hand
    if org.public_show_bowling and (player.bowling_action or player.bowling_type):
        attrs["bowling_action"] = player.bowling_action
        attrs["bowling_type"] = player.bowling_type
    if org.public_show_opening and player.is_opening_batsman:
        attrs["is_opening_batsman"] = True
    if org.public_show_gender and player.gender:
        attrs["gender"] = player.gender
    return attrs


@router.get("")
async def list_players(
    org_id: str,
    include_hidden: bool = Query(
        False,
        description=(
            "Include players the club has hidden from its public site. Only "
            "honoured for a signed-in club admin (or Better staff); a visitor "
            "asking for them still gets the public roster."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
):
    # Hidden players (players.is_public false) drop off the public roster and
    # the navbar search that reads it. An admin surface that genuinely needs
    # the whole club — Merge Players, Awards, the Yearbook editor — asks for
    # them, and only gets them if this viewer may see the club's private data.
    public_only = not (
        include_hidden and await user_can_view_org_private(db, viewer, org_id)
    )
    conditions = [Player.organisation_id == uuid.UUID(org_id)]
    if public_only:
        conditions.append(Player.is_public.is_not(False))
    result = await db.execute(select(Player).where(*conditions))
    # Sort by surname for everyone — a display_name_override is free text (often
    # "First Last", no comma) which an alphabetical DB sort would order by first
    # name, unlike the "Last, First" synced names. name_sort_key extracts the
    # surname from either shape so the list stays consistently surname-ordered.
    players = sorted(result.scalars().all(), key=lambda p: name_sort_key(p.display_name))
    return [
        {
            "id": str(p.id),
            "name": p.name,
            "display_name": p.display_name,
            "claimed": p.claimed,
            "photo_url": p.photo_url,
            "hero_photo_url": p.hero_photo_url,
            "player_role": p.player_role,
        }
        for p in players
    ]


@router.get("/{player_id}")
async def get_player(
    player_id: str,
    db: AsyncSession = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    # A hidden player reads as absent rather than forbidden: a 403 would
    # confirm the person exists, which is the thing they asked us not to say.
    # This is the one gate the public profile page needs — every stats
    # endpoint under it is keyed on the same id the page could not resolve.
    if player.is_public is False and not await user_can_view_org_private(
        db, viewer, str(player.organisation_id)
    ):
        raise HTTPException(status_code=404, detail="Player not found")
    return {
        "id": str(player.id),
        "name": player.name,
        "display_name": player.display_name,
        "organisation_id": str(player.organisation_id),
        "claimed": player.claimed,
        "playhq_id": player.playhq_id,
        "is_overseas": player.is_overseas,
        "overseas_country": player.overseas_country,
        **(await _public_player_attrs(db, player)),
    }


@router.get("/{player_id}/stats")
async def get_player_stats(
    player_id: str,
    season_id: Optional[str] = Query(None),
    grade_id: Optional[str] = Query(None),
    last_n_games: Optional[int] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    categories: Optional[str] = Query(
        None,
        description=(
            "Comma-separated grade categories to count — senior, junior, womens, "
            "masters, mixed, or 'all'. Omitted uses the club's own default, which "
            "leaves junior out."
        ),
    ),
    formats: Optional[str] = Query(
        None,
        description=(
            "Comma-separated match formats to count — two_day, one_day, t20, or "
            "'all'. Matched per FIXTURE against each game's own match_format, so "
            "a grade that plays more than one is split correctly. Omitted applies "
            "no format filter."
        ),
    ),
    competitions: Optional[str] = Query(
        None,
        description=(
            "Comma-separated club competition ids to count. Narrows a career to "
            "one competition — the ask a player in several of them in one season "
            "cannot otherwise answer. Omitted applies no competition filter."
        ),
    ),
    db: AsyncSession = Depends(get_db),
):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    org = await db.get(Organisation, player.organisation_id) if player.organisation_id else None
    scope, auto_shown = await grade_scope.resolve_scope_for_player(
        db, player.organisation_id, player_id, categories, formats=formats,
        competitions=competitions,
        auto_widen=bool(org.stats_auto_show_played_grades) if org else True,
    )
    use_game_filter = last_n_games or start_date or end_date
    if use_game_filter:
        try:
            batting = await get_career_batting_from_innings(db, player_id, last_n_games, start_date, end_date, scope=scope)
            bowling = await get_career_bowling_from_spells(db, player_id, last_n_games, start_date, end_date, scope=scope)
            fielding = await get_career_fielding_from_stats(db, player_id, last_n_games, start_date, end_date, scope=scope)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Stats query failed: {exc}")
    else:
        batting = await get_career_batting(db, player_id, season_id, scope=scope)
        bowling = await get_career_bowling(db, player_id, season_id, scope=scope)
        fielding = await get_career_fielding(db, player_id, season_id, scope=scope)
    batting_innings = await get_player_batting_innings(db, player_id, season_id, grade_id, scope=scope)
    bowling_spells = await get_player_bowling_spells(db, player_id, season_id, grade_id, scope=scope)

    # How much of this career a breakdown can reach at all. Told UP FRONT, on
    # the unfiltered view as well as a filtered one, so nobody discovers for
    # themselves that the per-competition figures do not sum to the career
    # total and reads it as a mistake. None when the two sources agree, which
    # is the common case and draws nothing. Skipped for a last-N-games or
    # date window, where the headline is a slice of a career rather than the
    # career and the comparison would mean nothing.
    # See services/match_coverage.py.
    coverage = None
    if player.organisation_id and not use_game_filter:
        try:
            from app.services import match_coverage
            coverage = await match_coverage.career_coverage(
                db, player_id, player.organisation_id, season_id)
        except Exception:
            # A note about the figures must never take the figures down.
            await db.rollback()
            import logging
            logging.getLogger(__name__).exception(
                "match coverage failed for player %s", player_id)

    return {
        "player": {"id": str(player.id), "name": player.name, "display_name": player.display_name, "claimed": player.claimed, "organisation_id": str(player.organisation_id), "playhq_id": player.playhq_id, "photo_url": player.photo_url, "is_overseas": player.is_overseas, "overseas_country": player.overseas_country, **(await _public_player_attrs(db, player))},
        "career_batting": _str_keys(batting),
        "career_bowling": _str_keys(bowling),
        "career_fielding": _str_keys(fielding),
        "batting_innings": [_str_keys(i) for i in batting_innings],
        "bowling_spells": [_str_keys(s) for s in bowling_spells],
        # Present only when the career total and what a filter can count from
        # differ, so a payload that has nothing to explain keeps its exact
        # shape — the presence-aware rule `_with_rate_coverage` already uses.
        **({"match_coverage": coverage} if coverage else {}),
        # Lets the profile say which categories these figures cover, and offer
        # only the toggles this club's grades actually justify.
        "grade_scope": {
            **scope.as_meta(),
            "available": await grade_scope.org_available_categories(db, player.organisation_id),
            # The competitions this club can be filtered by, so the profile can
            # draw the row without a second request. Empty for a club that plays
            # one competition, and the row then doesn't render — a control that
            # can only answer "everything" is worse than none.
            "available_competitions": await grade_scope.org_available_competitions(
                db, player.organisation_id
            ),
            # True when the club default would have left this player with nothing
            # at all, so the categories they actually played were added back. The
            # profile says so rather than quietly showing a wider set than the
            # rest of the site.
            "auto_shown": auto_shown,
        },
    }


@router.get("/{player_id}/competitions")
async def get_player_competitions(
    player_id: str,
    season_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """This player's batting, bowling, fielding and appearances per competition.

    The competition FILTER narrows every other panel to one competition; this
    enumerates them, so a player who turned out in the Border Cup and the Over
    60s competition in one season can be read side by side rather than by
    switching a filter back and forth.

    Deliberately takes no `categories`/`formats` scope. Slicing a career three
    ways at once buys nothing here, and the same call `get_player_formats`
    already makes for the same reason.
    """
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    from app.services import competition_stats
    return await competition_stats.player_competition_breakdown(
        db, player_id, player.organisation_id, season_id
    )


@router.get("/{player_id}/formats")
async def get_player_formats(
    player_id: str,
    season_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """This player's batting, bowling and fielding split by match format.

    Read per FIXTURE, off each game's own `match_format` — a grade is not a
    format (Applecross 1st Grade plays both one-day and two-day cricket in one
    season), so grouping by grade would file most games under the wrong heading.

    Deliberately takes no `categories` scope. This is a breakdown of everything
    the player has played, and a category filter on top of a format split would
    slice the same career two ways at once for no gain. `season_id` is offered
    because "what is he like in T20 this season" is a real selection question.
    """
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    data = await player_format_splits(db, player_id, season_id)
    return {
        "player": {"id": str(player.id), "name": player.display_name},
        **data,
    }


@router.get("/{player_id}/dismissals")
async def get_player_dismissals(
    player_id: str, categories: Optional[str] = Query(None),
    formats: Optional[str] = Query(None),
    competitions: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)
):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    scope = await _resolve_player_scope(db, player, categories, formats, competitions)
    return await get_dismissal_breakdown(db, player_id, scope=scope)


@router.get("/{player_id}/by-position")
async def get_player_by_position(
    player_id: str, categories: Optional[str] = Query(None),
    formats: Optional[str] = Query(None),
    competitions: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)
):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    scope = await _resolve_player_scope(db, player, categories, formats, competitions)
    return await get_batting_by_position(db, player_id, scope=scope)


@router.get("/{player_id}/by-grade")
async def get_player_by_grade(
    player_id: str,
    categories: Optional[str] = Query(None),
    formats: Optional[str] = Query(None),
    competitions: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    org_id = str(player.organisation_id)
    public_only = not await user_can_view_org_private(db, viewer, org_id)
    scope = await _resolve_player_scope(db, player, categories, formats, competitions)
    return await get_batting_by_grade(db, player_id, org_id, public_only=public_only, scope=scope)


@router.get("/{player_id}/bowling-by-grade")
async def get_player_bowling_by_grade(
    player_id: str,
    categories: Optional[str] = Query(None),
    formats: Optional[str] = Query(None),
    competitions: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    org_id = str(player.organisation_id)
    public_only = not await user_can_view_org_private(db, viewer, org_id)
    scope = await _resolve_player_scope(db, player, categories, formats, competitions)
    return await get_bowling_by_grade(db, player_id, org_id, public_only=public_only, scope=scope)


@router.get("/{player_id}/bowling-dismissals")
async def get_player_bowling_dismissals(
    player_id: str, categories: Optional[str] = Query(None),
    formats: Optional[str] = Query(None),
    competitions: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)
):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    scope = await _resolve_player_scope(db, player, categories, formats, competitions)
    return await get_bowling_dismissal_breakdown(db, player_id, scope=scope)


@router.get("/{player_id}/bowling-by-batter-position")
async def get_player_bowling_by_batter_position(
    player_id: str, categories: Optional[str] = Query(None),
    formats: Optional[str] = Query(None),
    competitions: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)
):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    scope = await _resolve_player_scope(db, player, categories, formats, competitions)
    return await get_bowling_by_batter_position(db, player_id, scope=scope)


@router.get("/{player_id}/by-venue")
async def get_player_by_venue_endpoint(
    player_id: str, categories: Optional[str] = Query(None),
    formats: Optional[str] = Query(None),
    competitions: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)
):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    scope = await _resolve_player_scope(db, player, categories, formats, competitions)
    return await get_player_by_venue(db, player_id, scope=scope)


@router.get("/{player_id}/by-opposition")
async def get_player_by_opposition_endpoint(
    player_id: str, categories: Optional[str] = Query(None),
    formats: Optional[str] = Query(None),
    competitions: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)
):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    scope = await _resolve_player_scope(db, player, categories, formats, competitions)
    return await get_player_by_opposition(db, player_id, scope=scope)


@router.get("/{player_id}/teammates")
async def get_player_teammates(player_id: str, db: AsyncSession = Depends(get_db)):
    """Every player this player has shared a side with, most games together first,
    with the team's record over those shared games. Public (career)."""
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    result = await iq_teammates.teammates(db, str(player.organisation_id), player_id)
    return result or {"player": {"player_id": player_id, "name": player.name}, "teammates": []}


@router.get("/{player_id}/teammates/{teammate_id}")
async def get_player_teammate_split(player_id: str, teammate_id: str, db: AsyncSession = Depends(get_db)):
    """This player's batting, bowling and the team's record split by whether the
    teammate was also in the side (the with-vs-without comparison). Public."""
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    result = await iq_teammates.with_split(db, str(player.organisation_id), player_id, teammate_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Player or teammate not found")
    return result


@router.get("/{player_id}/team-breakdown")
async def get_player_team_breakdown_endpoint(
    player_id: str,
    season_id: Optional[str] = Query(None),
    categories: Optional[str] = Query(None),
    formats: Optional[str] = Query(None),
    competitions: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    # The filter bar sits above every tab, so this grid answers to it like the
    # rest of the Analysis panels. Without it a club filtering to Men's on the
    # Batting tab found the women's grades back on Team, one click away.
    scope = await _resolve_player_scope(db, player, categories, formats, competitions)
    return await get_player_team_breakdown(
        db, player_id, str(player.organisation_id), season_id, scope=scope
    )


@router.get("/{player_id}/rankings")
async def get_player_rankings_endpoint(
    player_id: str,
    season_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return await get_player_rankings(db, player_id, str(player.organisation_id), season_id)


@router.get("/{player_id}/seasons")
async def get_player_seasons(
    player_id: str,
    categories: Optional[str] = Query(None),
    formats: Optional[str] = Query(None),
    competitions: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    org = await db.get(Organisation, player.organisation_id) if player.organisation_id else None
    scope, _ = await grade_scope.resolve_scope_for_player(
        db, player.organisation_id, player_id, categories, formats=formats,
        competitions=competitions,
        auto_widen=bool(org.stats_auto_show_played_grades) if org else True,
    )
    return await get_season_by_season(db, player_id, include_prior=True, scope=scope)


@router.get("/{player_id}/milestones")
async def get_player_milestones_endpoint(player_id: str, db: AsyncSession = Depends(get_db)):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    rows = await get_player_milestones(db, player_id)
    # Filter out pre-existing rows that don't match the current threshold scheme
    # (10/25 matches, 100/250 runs, etc.) — they stay in the DB, just hidden.
    milestones = [
        _str_keys(r) for r in rows
        if is_displayable(r["milestone_type"], r["milestone_value"])
    ]

    # Append computed per-grade match milestones (not stored in DB).
    breakdown = await get_player_team_breakdown(db, player_id, str(player.organisation_id))
    grade_rows = sorted(breakdown.get("rows", []), key=lambda r: r.get("grade_name") or "")
    for row in grade_rows:
        matches_in_grade = int(row.get("matches") or 0)
        grade_name = row.get("grade_name")
        if not grade_name:
            continue
        for threshold in crossed_thresholds("grade_matches", matches_in_grade):
            milestones.append({
                "id": None,
                "milestone_type": "grade_matches",
                "milestone_value": threshold,
                "achieved_at": None,
                "detail": grade_name,
                "game_id": None,
            })

    return milestones


@router.get("/{player_id}/partnerships")
async def get_player_partnerships_endpoint(
    player_id: str, categories: Optional[str] = Query(None),
    formats: Optional[str] = Query(None),
    competitions: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)
):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    scope = await _resolve_player_scope(db, player, categories, formats, competitions)
    rows = await get_player_partnerships(db, player_id, scope=scope)
    return [_str_keys(r) for r in rows]


@router.get("/{player_id}/activity")
async def get_player_activity_endpoint(player_id: str, db: AsyncSession = Depends(get_db)):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return await get_player_activity(db, player_id)


@router.get("/{player_id}/upcoming-milestones")
async def get_player_upcoming_milestones(player_id: str, db: AsyncSession = Depends(get_db)):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    # Scope the career totals to the player's own organisation's seasons. A CA
    # participant GUID is shared across clubs, so a dual-club player can have
    # player_season_stats rows attached under another club's seasons; summing
    # them all would over-count (see migration 060). This query reads the base
    # table, so it applies the same guard the v_effective view does.
    org_clause = " AND s.organisation_id = :org_id" if player.organisation_id else ""
    agg_params = {"pid": player_id}
    if player.organisation_id:
        agg_params["org_id"] = str(player.organisation_id)
    agg_res = await db.execute(
        text(f"""
            SELECT
                COALESCE(SUM(pss.runs), 0)    AS total_runs,
                COALESCE(SUM(pss.wickets), 0) AS total_wickets,
                COALESCE(SUM(pss.matches), 0) AS total_matches,
                COALESCE(SUM(pss.catches), 0) AS total_catches
            FROM player_season_stats pss
            JOIN seasons s ON s.id = pss.season_id
            WHERE pss.player_id = :pid{org_clause}
        """),
        agg_params
    )
    agg = dict(agg_res.mappings().first() or {})
    totals = {
        "runs":    int(agg.get("total_runs")    or 0),
        "wickets": int(agg.get("total_wickets") or 0),
        "matches": int(agg.get("total_matches") or 0),
        "catches": int(agg.get("total_catches") or 0),
    }

    upcoming = []
    for mt, current in totals.items():
        target = next_threshold(mt, current)
        if target is None:
            continue
        needed = target - current
        if needed > reach_window(mt, target):
            continue
        upcoming.append({"type": mt, "current": current, "target": target, "needed": needed})

    # Per-grade match milestones — uses the same merge-aware breakdown the
    # Team tab does so canonical/merged grade names line up.
    breakdown = await get_player_team_breakdown(db, player_id, str(player.organisation_id))
    for row in breakdown.get("rows", []):
        matches_in_grade = int(row.get("matches") or 0)
        grade_name = row.get("grade_name")
        if not grade_name or matches_in_grade <= 0:
            continue
        target = next_threshold("grade_matches", matches_in_grade)
        if target is None:
            continue
        needed = target - matches_in_grade
        if needed > reach_window("grade_matches", target):
            continue
        upcoming.append({
            "type": "matches",
            "current": matches_in_grade,
            "target": target,
            "needed": needed,
            "label": f"MATCHES — {grade_name}",
            "grade_name": grade_name,
        })

    upcoming.sort(key=lambda m: m.get("needed", 9999))
    return upcoming


@router.get("/{player_id}/captain-stats")
async def get_player_captain_stats(player_id: str, db: AsyncSession = Depends(get_db)):
    pid = uuid.UUID(player_id)
    # Captaincy is a club's own record: a shared CA participant GUID means a
    # player's rows can sit on another club's game, and captaining a side for
    # one club is not a captaincy record for the other. Same predicate as
    # aggregations._club_game_clause.
    params: dict = {"pid": pid}
    club = await _club_game_clause(db, player_id, params)

    summary_res = await db.execute(text("""
        SELECT
            COUNT(DISTINCT ga.game_id) AS games_captained,
            SUM(CASE WHEN g.result = 'WIN' THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN g.result = 'LOSS' THEN 1 ELSE 0 END) AS losses,
            SUM(CASE WHEN g.result IS NULL OR g.result NOT IN ('WIN', 'LOSS') THEN 1 ELSE 0 END) AS draws
        FROM game_appearances ga
        JOIN v_effective_games g ON g.id = ga.game_id
        WHERE ga.player_id = :pid AND ga.is_captain = TRUE""" + club + """
    """), params)
    summary = dict(summary_res.mappings().first() or {})

    bat_cap_res = await db.execute(text("""
        SELECT
            COUNT(*) AS innings,
            COALESCE(SUM(bi.runs), 0) AS runs,
            MAX(bi.runs) AS high_score,
            ROUND(SUM(bi.runs)::numeric / NULLIF(COUNT(*) - SUM(bi.not_out::int), 0), 2) AS average,
            SUM(CASE WHEN bi.runs >= 50 AND bi.runs < 100 THEN 1 ELSE 0 END) AS fifties,
            SUM(CASE WHEN bi.runs >= 100 THEN 1 ELSE 0 END) AS hundreds
        FROM v_effective_batting_innings bi
        JOIN v_effective_games g ON g.id = bi.game_id
        JOIN game_appearances ga ON ga.game_id = bi.game_id AND ga.player_id = bi.player_id AND ga.is_captain = TRUE
        WHERE bi.player_id = :pid""" + club + """
          AND NOT COALESCE(bi.did_not_bat, FALSE)
          AND LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent', 'did not bat', 'dnb')
    """), params)
    bat_cap = dict(bat_cap_res.mappings().first() or {})

    bat_not_res = await db.execute(text("""
        SELECT
            COUNT(*) AS innings,
            COALESCE(SUM(bi.runs), 0) AS runs,
            MAX(bi.runs) AS high_score,
            ROUND(SUM(bi.runs)::numeric / NULLIF(COUNT(*) - SUM(bi.not_out::int), 0), 2) AS average,
            SUM(CASE WHEN bi.runs >= 50 AND bi.runs < 100 THEN 1 ELSE 0 END) AS fifties,
            SUM(CASE WHEN bi.runs >= 100 THEN 1 ELSE 0 END) AS hundreds
        FROM v_effective_batting_innings bi
        JOIN v_effective_games g ON g.id = bi.game_id
        LEFT JOIN game_appearances ga ON ga.game_id = bi.game_id AND ga.player_id = bi.player_id AND ga.is_captain = TRUE
        WHERE bi.player_id = :pid""" + club + """
          AND NOT COALESCE(bi.did_not_bat, FALSE)
          AND LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent', 'did not bat', 'dnb')
          AND ga.game_id IS NULL
    """), params)
    bat_not = dict(bat_not_res.mappings().first() or {})

    bowl_cap_res = await db.execute(text("""
        SELECT
            COUNT(DISTINCT bs.game_id) AS games,
            COALESCE(SUM(bs.wickets), 0) AS wickets,
            ROUND(SUM(bs.runs)::numeric / NULLIF(SUM(bs.wickets), 0), 2) AS average,
            ROUND(SUM(bs.runs)::numeric / NULLIF(SUM(bs.overs), 0), 2) AS economy
        FROM v_effective_bowling_spells bs
        JOIN v_effective_games g ON g.id = bs.game_id
        JOIN game_appearances ga ON ga.game_id = bs.game_id AND ga.player_id = bs.player_id AND ga.is_captain = TRUE
        WHERE bs.player_id = :pid""" + club + """
    """), params)
    bowl_cap = dict(bowl_cap_res.mappings().first() or {})

    bowl_not_res = await db.execute(text("""
        SELECT
            COUNT(DISTINCT bs.game_id) AS games,
            COALESCE(SUM(bs.wickets), 0) AS wickets,
            ROUND(SUM(bs.runs)::numeric / NULLIF(SUM(bs.wickets), 0), 2) AS average,
            ROUND(SUM(bs.runs)::numeric / NULLIF(SUM(bs.overs), 0), 2) AS economy
        FROM v_effective_bowling_spells bs
        JOIN v_effective_games g ON g.id = bs.game_id
        LEFT JOIN game_appearances ga ON ga.game_id = bs.game_id AND ga.player_id = bs.player_id AND ga.is_captain = TRUE
        WHERE bs.player_id = :pid""" + club + """
          AND ga.game_id IS NULL
    """), params)
    bowl_not = dict(bowl_not_res.mappings().first() or {})

    by_season_res = await db.execute(text("""
        WITH captain_games AS (
            SELECT ga.game_id, g.result, s.name AS season_name, s.year AS season_year
            FROM game_appearances ga
            JOIN v_effective_games g ON g.id = ga.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE ga.player_id = :pid AND ga.is_captain = TRUE""" + club + """
        ),
        bat_per_game AS (
            SELECT bi.game_id, SUM(bi.runs) AS runs, COUNT(*) AS innings,
                   SUM(bi.not_out::int) AS not_outs
            FROM v_effective_batting_innings bi
            -- Already narrowed to captain_games, which carries the club
            -- predicate, so no games join and no clause is needed here.
            WHERE bi.player_id = :pid
              AND bi.game_id IN (SELECT game_id FROM captain_games)
              AND NOT COALESCE(bi.did_not_bat, FALSE)
              AND LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent', 'did not bat', 'dnb')
            GROUP BY bi.game_id
        ),
        bowl_per_game AS (
            SELECT bs.game_id, SUM(bs.wickets) AS wickets, SUM(bs.runs) AS bowl_runs
            FROM v_effective_bowling_spells bs
            WHERE bs.player_id = :pid
              AND bs.game_id IN (SELECT game_id FROM captain_games)
            GROUP BY bs.game_id
        )
        SELECT
            cg.season_name,
            cg.season_year,
            COUNT(cg.game_id) AS games_captained,
            SUM(CASE WHEN cg.result = 'WIN' THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN cg.result = 'LOSS' THEN 1 ELSE 0 END) AS losses,
            SUM(CASE WHEN cg.result IS NULL OR cg.result NOT IN ('WIN', 'LOSS') THEN 1 ELSE 0 END) AS draws,
            COALESCE(SUM(bat.runs), 0) AS batting_runs,
            COALESCE(SUM(bat.innings), 0) AS batting_innings,
            ROUND(SUM(bat.runs)::numeric / NULLIF(SUM(bat.innings) - SUM(bat.not_outs), 0), 2) AS batting_avg,
            COALESCE(SUM(bowl.wickets), 0) AS bowling_wickets,
            ROUND(SUM(bowl.bowl_runs)::numeric / NULLIF(SUM(bowl.wickets), 0), 2) AS bowling_avg
        FROM captain_games cg
        LEFT JOIN bat_per_game bat ON bat.game_id = cg.game_id
        LEFT JOIN bowl_per_game bowl ON bowl.game_id = cg.game_id
        GROUP BY cg.season_name, cg.season_year
        ORDER BY cg.season_year DESC NULLS LAST
    """), params)
    by_season = [dict(r) for r in by_season_res.mappings()]
    for row in by_season:
        row["season_year"] = row.get("season_year")

    return {
        "summary": summary,
        "batting_as_captain": bat_cap,
        "batting_not_captain": bat_not,
        "bowling_as_captain": bowl_cap,
        "bowling_not_captain": bowl_not,
        "by_season": by_season,
    }


class SyncRequestCreate(BaseModel):
    note: Optional[str] = None


@router.post("/{player_id}/request-sync")
async def request_player_sync(
    player_id: str,
    body: SyncRequestCreate = SyncRequestCreate(),
    db: AsyncSession = Depends(get_db),
):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    # Prevent duplicate pending requests
    existing = await db.execute(
        text("""
            SELECT id FROM player_sync_requests
            WHERE player_id = :pid AND status = 'pending'
            LIMIT 1
        """),
        {"pid": player_id},
    )
    if existing.fetchone():
        return {"status": "already_pending"}

    req = PlayerSyncRequest(
        player_id=player.id,
        org_id=player.organisation_id,
        requester_note=body.note,
        status="pending",
    )
    db.add(req)
    await db.commit()
    return {"status": "requested"}


class PlayerRename(BaseModel):
    name: str


@router.patch("/{player_id}")
async def rename_player(
    player_id: str,
    body: PlayerRename,
    db: AsyncSession = Depends(get_db),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty")
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    old_name = player.name
    player.name = name
    # Keep player_achievements rows in sync for unlinked records
    await db.execute(
        text("UPDATE player_achievements SET player_name = :new WHERE player_id = :pid"),
        {"new": name, "pid": player_id},
    )
    # Record the old name as an alias so a live feed (Play.Cricket, a
    # Grassroots scorecard) still using it keeps resolving to this player —
    # see services/player_aliases.py.
    await seed_alias_on_rename(db, player.organisation_id, player.id, old_name)
    await db.commit()
    return {"status": "renamed", "old_name": old_name, "new_name": name}


class PlayerProfileUpdate(BaseModel):
    # All editable management fields. Callers (the legacy modal and the new
    # BetterSelect Players screen) send a subset — only provided fields update.
    display_name_override: Optional[str] = None
    playhq_id: Optional[str] = None
    player_role: Optional[str] = None
    skill_positions: Optional[list[str]] = None  # e.g. ["BAT", "WKT"]
    batting_hand: Optional[str] = None
    bowling_action: Optional[str] = None
    bowling_type: Optional[str] = None
    is_opening_batsman: Optional[bool] = None
    gender: Optional[str] = None
    is_player: Optional[bool] = None
    status: Optional[str] = None                  # active | inactive
    email: Optional[str] = None
    phone: Optional[str] = None
    squad_team_id: Optional[str] = None
    is_overseas: Optional[bool] = None
    overseas_country: Optional[str] = None
    # Public visibility + the two BetterSelect flags (migration 265). All
    # three are plain columns, so the generic setattr loop below applies
    # them; they are listed here because a field absent from this model
    # never reaches the service, however carefully the column was added.
    is_public: Optional[bool] = None
    is_financial_override: Optional[bool] = None
    trained_override: Optional[bool] = None
    # Date of birth (migration 269). Pydantic parses "YYYY-MM-DD" into a real
    # date, so an unparseable value is a 422 rather than a string handed to a
    # DATE column; an explicit null clears it (the PATCH reads exclude_unset,
    # so a present null IS the intent).
    date_of_birth: Optional[date] = None


def _profile_fields(player: Player) -> dict:
    """The editable management fields, shared by GET and PATCH responses."""
    return {
        # The date of birth itself only ever leaves the server here, on the
        # MANAGE_PLAYERS-gated profile — this is the screen it is entered on.
        # `age` rides along unconditionally for the same reason: the club's
        # BetterSelect display rule governs the selection screens, not the
        # record an admin is looking at while editing it.
        "date_of_birth": player.date_of_birth.isoformat() if player.date_of_birth else None,
        "age": age_on(player.date_of_birth),
        "id": str(player.id),
        "name": player.name,
        "display_name": player.display_name,
        "display_name_override": player.display_name_override,
        "player_role": player.player_role,
        "skill_positions": player.skill_positions or [],
        "batting_hand": player.batting_hand,
        "bowling_action": player.bowling_action,
        "bowling_type": player.bowling_type,
        "is_opening_batsman": player.is_opening_batsman,
        "gender": player.gender,
        "is_player": player.is_player,
        "status": player.status,
        "email": player.email,
        "phone": player.phone,
        "photo_url": player.photo_url,
        "hero_photo_url": player.hero_photo_url,
        "playhq_id": player.playhq_id,
        "squad_team_id": str(player.squad_team_id) if player.squad_team_id else None,
        "is_overseas": player.is_overseas,
        "overseas_country": player.overseas_country,
        "is_public": player.is_public is not False,
        "is_financial_override": player.is_financial_override,
        "trained_override": player.trained_override,
    }


async def _squad_obj(db: AsyncSession, player: Player) -> Optional[dict]:
    """The player's assigned selection-pool team as {id, name}, or None."""
    if not player.squad_team_id:
        return None
    try:
        team = await db.get(Team, player.squad_team_id)
        if team:
            return {"id": str(team.id), "name": team.name}
    except Exception:
        pass
    return None


def _fmt_date_label(d) -> str:
    try:
        return d.strftime("%a %-d %b")
    except Exception:
        return d.isoformat() if d else ""


async def _snapshot(db: AsyncSession, player: Player) -> dict:
    """Selection-relevant signal for the profile panel.

    Every piece is wrapped in try/except and defaults to []/0/None so a schema
    mismatch on any stats table never 500s the whole profile.
    """
    snap = {
        "availability_next": [],
        "recent_batting": [],
        "recent_bowling": [],
        "season_catches": 0,
        "last_picked": None,
    }

    # availability_next — next ~4 upcoming fixture dates with this player's
    # recorded status (same source the matrix uses: Fixture.played_on, joined to
    # PlayerAvailability on avail_date). Defaults to NO_RESPONSE.
    try:
        from datetime import date as _date
        fx_res = await db.execute(
            select(Fixture.played_on)
            .where(
                Fixture.organisation_id == player.organisation_id,
                Fixture.played_on.isnot(None),
                Fixture.played_on >= _date.today(),
            )
            .order_by(Fixture.played_on.asc())
        )
        dates = []
        for (d,) in fx_res.all():
            if d and d not in dates:
                dates.append(d)
            if len(dates) >= 4:
                break
        if dates:
            av_res = await db.execute(
                select(PlayerAvailability.avail_date, PlayerAvailability.status).where(
                    PlayerAvailability.player_id == player.id,
                    PlayerAvailability.avail_date.in_(dates),
                )
            )
            by_date = {d: s for (d, s) in av_res.all()}
            snap["availability_next"] = [
                {
                    "date": d.isoformat(),
                    "label": _fmt_date_label(d),
                    "status": by_date.get(d, "NO_RESPONSE"),
                }
                for d in dates
            ]
    except Exception:
        snap["availability_next"] = []

    # recent_batting — last 5 scores, most-recent-first (by game date).
    try:
        b_res = await db.execute(
            select(BattingInnings.runs)
            .join(Game, Game.id == BattingInnings.game_id)
            .where(BattingInnings.player_id == player.id)
            .order_by(Game.played_at.desc().nullslast(), BattingInnings.id.desc())
            .limit(5)
        )
        snap["recent_batting"] = [int(r or 0) for (r,) in b_res.all()]
    except Exception:
        snap["recent_batting"] = []

    # recent_bowling — last 5 {wickets, runs}, most-recent-first.
    try:
        bw_res = await db.execute(
            select(BowlingSpell.wickets, BowlingSpell.runs)
            .join(Game, Game.id == BowlingSpell.game_id)
            .where(BowlingSpell.player_id == player.id)
            .order_by(Game.played_at.desc().nullslast(), BowlingSpell.id.desc())
            .limit(5)
        )
        snap["recent_bowling"] = [
            {"wickets": int(w or 0), "runs": int(r or 0)} for (w, r) in bw_res.all()
        ]
    except Exception:
        snap["recent_bowling"] = []

    # season_catches — catches in the club's latest season only (the profile
    # labels this "this season"; an unfiltered sum would be career catches).
    try:
        latest_season = (await db.execute(
            select(Season.id)
            .where(Season.organisation_id == player.organisation_id)
            .order_by(Season.year.desc().nullslast(), Season.name.desc())
            .limit(1)
        )).scalar()
        catches = catches_wk = 0
        if latest_season:
            c_res = await db.execute(
                select(
                    func.coalesce(func.sum(FieldingStat.catches), 0),
                    func.coalesce(func.sum(FieldingStat.catches_wk), 0),
                )
                .join(Game, Game.id == FieldingStat.game_id)
                .join(Grade, Grade.id == Game.grade_id)
                .where(
                    FieldingStat.player_id == player.id,
                    Grade.season_id == latest_season,
                )
            )
            row = c_res.first()
            catches = int((row and row[0]) or 0)
            catches_wk = int((row and row[1]) or 0)
        snap["season_catches"] = catches
        snap["season_catches_wk"] = catches_wk
    except Exception:
        snap["season_catches"] = 0
        snap["season_catches_wk"] = 0

    # last_picked — most recent fixture this player was named in.
    try:
        lp_res = await db.execute(
            select(Fixture.round, Fixture.opponent_name, Fixture.played_on)
            .join(FixtureLineup, FixtureLineup.fixture_id == Fixture.id)
            .where(FixtureLineup.player_id == player.id)
            .order_by(Fixture.played_on.desc().nullslast())
            .limit(1)
        )
        row = lp_res.first()
        if row:
            rnd, opp, played = row
            snap["last_picked"] = {
                "round": rnd,
                "opponent": opp,
                "date": played.isoformat() if played else None,
            }
    except Exception:
        snap["last_picked"] = None

    return snap


async def _full_profile(db: AsyncSession, player: Player) -> dict:
    data = _profile_fields(player)
    data["squad"] = await _squad_obj(db, player)
    data["snapshot"] = await _snapshot(db, player)
    # The age the SELECTION screens would show for this player under the
    # club's own rule — None when ages are off, or when this player is
    # outside the age the club restricted the display to. Sent alongside the
    # true `age` so a screen that has just saved a date of birth can correct
    # its own roster row without re-reading the whole list, and correct it to
    # what the rest of the club would actually see rather than to the number
    # the person editing happens to be looking at.
    org = await db.get(Organisation, player.organisation_id) if player.organisation_id else None
    data["age_visible"] = visible_age(player.date_of_birth, org)
    return data


@router.get("/{player_id}/profile")
async def get_player_profile(
    player_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_cap(MANAGE_PLAYERS)),
):
    """All editable management fields + assigned squad + selection snapshot."""
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return await _full_profile(db, player)


@router.patch("/{player_id}/profile")
async def update_player_profile(
    player_id: str,
    body: PlayerProfileUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_cap(MANAGE_PLAYERS)),
):
    """Update admin-managed player attributes; returns the same shape as GET."""
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    data = body.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in (None, "active", "inactive"):
        raise HTTPException(status_code=400, detail="status must be 'active' or 'inactive'")
    if "date_of_birth" in data:
        err = dob_error(data["date_of_birth"])
        if err:
            raise HTTPException(status_code=422, detail=err)
    # Capture the effective display name before display_name_override changes,
    # so a rename via this route also gets remembered as an alias — same as
    # the plain-name rename_player endpoint above.
    old_display_name = player.display_name if "display_name_override" in data else None
    # squad_team_id arrives as a string (or None to unassign) — coerce to UUID,
    # then mirror the change into team_members so "Squad" resolves to the same
    # set on every BetterSelect screen.
    if "squad_team_id" in data:
        val = data.pop("squad_team_id")
        old_team_id = player.squad_team_id
        new_team_id = uuid.UUID(val) if val else None
        player.squad_team_id = new_team_id
        if new_team_id is None:
            await sync_squad_membership(db, player.organisation_id, player.id, old_team_id, None, user.id)
        else:
            target = await db.get(Team, new_team_id)
            if target and target.organisation_id == player.organisation_id:
                await sync_squad_membership(db, player.organisation_id, player.id, old_team_id, new_team_id, user.id)
    for key, value in data.items():
        setattr(player, key, value)
    # Marking someone inactive takes them out of their squad in the SAME write.
    # An inactive player is not in this season's selection pool, so leaving them
    # filed in a squad is what makes the Squads board disagree with the roster —
    # and the board would go on offering them for an XI. Gated on this request
    # actually setting the status, so editing an already-inactive player's phone
    # number doesn't quietly move them. Reactivating does NOT put them back:
    # which squad they belong in now is the club's call, not ours.
    if data.get("status") == "inactive" and player.squad_team_id is not None:
        old_squad_id = player.squad_team_id
        player.squad_team_id = None
        await sync_squad_membership(db, player.organisation_id, player.id, old_squad_id, None, user.id)
    if old_display_name and old_display_name != player.display_name:
        await seed_alias_on_rename(db, player.organisation_id, player.id, old_display_name)
    await db.commit()
    await db.refresh(player)
    return await _full_profile(db, player)


class PlayerAliasCreate(BaseModel):
    alias_name: str


@router.get("/{player_id}/aliases")
async def list_player_aliases(
    player_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _user: User = Depends(require_cap(MANAGE_PLAYERS)),
):
    """Former/alternate names recorded for this player (see
    services/player_aliases.py) — auto-seeded whenever the player is renamed,
    or added by hand here for a rename that predates that feature."""
    player = await db.get(Player, uuid.UUID(player_id))
    if not player or player.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Player not found")
    res = await db.execute(
        text(
            "SELECT id, alias_name, source, created_at FROM player_name_aliases "
            "WHERE player_id = :pid ORDER BY created_at DESC"
        ),
        {"pid": player_id},
    )
    return [
        {"id": str(r[0]), "alias_name": r[1], "source": r[2], "created_at": r[3].isoformat() if r[3] else None}
        for r in res.fetchall()
    ]


@router.post("/{player_id}/aliases")
async def add_player_alias(
    player_id: str,
    body: PlayerAliasCreate,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _user: User = Depends(require_cap(MANAGE_PLAYERS)),
):
    """Manually record a former/alternate name for this player — the fix for
    a rename that happened before this table existed, or any other name a
    live feed (Play.Cricket, a Grassroots scorecard) uses for them that
    doesn't textually match their current name."""
    player = await db.get(Player, uuid.UUID(player_id))
    if not player or player.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Player not found")
    alias_name = (body.alias_name or "").strip()
    key = normalise_name_key(alias_name)
    if not key:
        raise HTTPException(status_code=400, detail="Alias name cannot be empty")

    existing = await db.execute(
        text("SELECT player_id FROM player_name_aliases WHERE organisation_id = :org AND alias_key = :key"),
        {"org": club.id, "key": key},
    )
    row = existing.fetchone()
    if row and str(row[0]) != player_id:
        raise HTTPException(status_code=409, detail="That name is already an alias for a different player")
    if row:
        return {"status": "ok"}

    await db.execute(
        text(
            "INSERT INTO player_name_aliases (id, organisation_id, player_id, alias_name, alias_key, source) "
            "VALUES (:id, :org, :pid, :name, :key, 'manual')"
        ),
        {"id": str(uuid.uuid4()), "org": club.id, "pid": player_id, "name": alias_name, "key": key},
    )
    await db.commit()
    return {"status": "ok"}


@router.delete("/{player_id}/aliases/{alias_id}")
async def delete_player_alias(
    player_id: str,
    alias_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _user: User = Depends(require_cap(MANAGE_PLAYERS)),
):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player or player.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Player not found")
    await db.execute(
        text("DELETE FROM player_name_aliases WHERE id = :id AND player_id = :pid"),
        {"id": alias_id, "pid": player_id},
    )
    await db.commit()
    return {"status": "ok"}


@router.post("/{player_id}/claim")
async def claim_player_profile(
    player_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    if player.claimed:
        raise HTTPException(status_code=409, detail="Profile already claimed")

    player.claimed = True
    player.user_id = current_user.id
    await db.commit()
    return {"status": "claimed", "player_id": player_id}


class ClaimFillInRequest(BaseModel):
    grassroots_participant_id: str
    name: str
    existing_player_id: Optional[str] = None
    reference_note: Optional[str] = None


@router.post("/claim-fill-in")
async def claim_fill_in(
    body: ClaimFillInRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_cap(MANAGE_PLAYERS)),
    club: Organisation = Depends(get_current_club),
):
    """Promote a scorecard fill-in (a borrowed player, never a redacted one —
    there's no identity to claim there) into a real `players` row for this
    club, so future syncs and this game's own stats attach to a real player
    instead of a name-only row.

    Uses the same identity scheme sync.py's `_resolve_org_player` mints from a
    CA participant GUID (id = the raw GUID, or uuid5(org, guid) only on a
    genuine cross-club collision; grassroots_id = the raw GUID) — a later sync
    recognises the row by (org, grassroots_id) and attaches to it rather than
    minting a duplicate. Re-claiming the same participant is idempotent (finds
    the existing row by grassroots_id and updates it instead of duplicating).

    `existing_player_id`, if given, means the fill-in turned out to already be
    one of our registered players under a different scorecard identity (a
    GR-uuid mismatch) rather than a genuinely new person — delegates to the
    existing merge-players flow rather than reimplementing it.

    `reference_note` (e.g. a pasted PlayHQ profile URL) is stored verbatim for
    the club's own record-keeping. It is NOT parsed or verified — PlayHQ's
    player-profile pages are a client-rendered app behind bot protection with
    no documented public lookup API, so there is no reliable way to resolve a
    pasted URL back to a real participant id server-side.
    """
    guid = (body.grassroots_participant_id or "").strip()
    name = (body.name or "").strip()
    if not guid or not name:
        raise HTTPException(status_code=400, detail="grassroots_participant_id and name are required")
    try:
        guid_uuid = uuid.UUID(guid)
    except ValueError:
        raise HTTPException(status_code=400, detail="grassroots_participant_id is not a valid id")

    existing_res = await db.execute(
        select(Player).where(
            Player.organisation_id == club.id,
            Player.grassroots_id == guid,
        )
    )
    player = existing_res.scalar_one_or_none()

    if player is None:
        # Only mint a per-club uuid5 id when the raw GUID is already a player
        # id elsewhere (a genuine shared-participant collision) — same rule
        # sync.py's _resolve_org_player uses, so this row and a future sync
        # agree on the same id.
        clash = await db.get(Player, guid_uuid)
        new_id = uuid.uuid5(club.id, guid) if clash is not None else guid_uuid
        player = Player(id=new_id, name=name, organisation_id=club.id, grassroots_id=guid)
        db.add(player)
        try:
            await db.flush()
        except IntegrityError:
            # Two admins claiming the same fill-in at once — re-fetch rather
            # than 500.
            await db.rollback()
            existing_res = await db.execute(
                select(Player).where(
                    Player.organisation_id == club.id,
                    Player.grassroots_id == guid,
                )
            )
            player = existing_res.scalar_one_or_none()
            if player is None:
                raise HTTPException(status_code=409, detail="Could not claim this fill-in — try again")
            player.name = name
    else:
        player.name = name

    if body.reference_note is not None:
        player.claim_note = body.reference_note.strip() or None
    await db.commit()
    await db.refresh(player)

    if body.existing_player_id:
        keep_id = uuid.UUID(body.existing_player_id)
        if keep_id != player.id:
            from app.routers.admin import merge_players, MergeRequest
            await merge_players(
                MergeRequest(
                    keep_player_id=str(keep_id),
                    remove_player_id=str(player.id),
                    org_id=str(club.id),
                ),
                db=db,
                current_user=current_user,
            )
            return {"status": "merged", "player_id": str(keep_id)}

    return {"status": "created", "player_id": str(player.id)}
