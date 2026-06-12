"""BetterIQ router — analytics + AI module (Best tier).

Module entitlement is applied where this router is mounted (``main.py``:
``include_router(iq.router, dependencies=[Depends(require_module("iq"))])``).
Here we additionally gate on the ``MANAGE_IQ`` capability — opposition scouting
is selector-grade intel, so it's treated like the other admin tools rather than
open to every club member. ``club_admin`` / ``super_admin`` hold all caps.

Phase 1 surface: Opposition analysis (read-only over held data). Selection
analysis, player trends and NL Q&A are later phases.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_IQ, require_cap
from app.models.db import Organisation, User, get_db
from app.routers.auth import get_current_club, get_current_user
from app.services import iq as iq_service
from app.services import iq_opponent
from app.services import iq_phases
from app.services import iq_radar
from app.services import iq_review
from app.services import iq_scout
from app.services import iq_selection
from app.services import iq_team
from app.services import iq_trends

# Every BetterIQ route requires the MANAGE_IQ capability.
router = APIRouter(prefix="/iq", tags=["iq"], dependencies=[Depends(require_cap(MANAGE_IQ))])


@router.get("/opposition/opponents")
async def opposition_opponents(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Opponents we have history against, plus upcoming fixtures to scout."""
    return await iq_service.list_opponents(db, str(club.id))


@router.get("/opposition/report")
async def opposition_report(
    opponent: str | None = Query(None, description="opp_key from the opponents list (or any CA org GUID)"),
    fixture_id: str | None = Query(None, description="resolve the opponent from an upcoming fixture"),
    grade: str | None = Query(None, description="scope the record to one grade (by name) — the card's Grade toggle"),
    season_ids: str | None = Query(None, description="comma-separated season ids to scope the record — the card's Season toggle"),
    name: str | None = Query(None, description="display name for a club outside our history (CA-wide search)"),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Full scouting report for one opponent (head-to-head, our record vs them,
    their danger batters, and their roster when that club is synced).

    ``grade``/``season_ids`` optionally scope the historical sections (record,
    our performers, venues, last meeting, bowler match-ups) to match the record
    card's All-time / Season / Grade toggle. Omit both for the all-time view."""
    seasons = [s for s in (season_ids.split(",") if season_ids else []) if s.strip()]
    return await iq_service.opposition_report(
        db, str(club.id), opponent=opponent, fixture_id=fixture_id,
        grade=grade, season_ids=seasons or None, display_name=name,
    )


@router.get("/opposition/dossier")
async def opposition_dossier(
    opponent: str | None = Query(None, description="opp_key from the opponents list (or any CA org GUID)"),
    fixture_id: str | None = Query(None, description="resolve the opponent (and grade) from a fixture"),
    team: str | None = Query(None, description="narrow the scout to one of the opponent's teams (a grade_id); omit for the whole club"),
    name: str | None = Query(None, description="display name for a club outside our history (CA-wide search)"),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Live opponent dossier (squad + form pulled from the grade, plus deep
    head-to-head vs us). Built on demand in the background; this returns
    ``{status: 'building'}`` until ready, then the assembled payload. Poll it.

    By default scouts the whole club (every team/grade) so no player is missed;
    pass ``team`` (a grade_id from the payload's ``teams``) to focus on one side.
    ``opponent`` can be ANY Cricket Australia org GUID (from the club search) —
    a club outside our competitions is discovered via its own org endpoints."""
    opp_key, name, grade_id = await iq_service.resolve_opponent(
        db, str(club.id), opponent=opponent, fixture_id=fixture_id, display_name=name
    )
    # A never-before-played opponent has no opp_key — but if a fixture gives us
    # their grade + name we can still scout them live (key the cache on name).
    key = opp_key or (name if grade_id else None)
    if not key:
        return {
            "status": "unavailable",
            "opponent": {"opp_key": None, "name": name},
            "message": (
                f"No identity to scout for {name} yet — we build a dossier once you've"
                " played them, or from the fixture's grade." if name
                else "Opponent not found."
            ),
        }
    return await iq_opponent.get_or_start_dossier(
        db, str(club.id), key, opp_name=name, grade_id=grade_id, team_grade_id=team
    )


@router.get("/opposition/ladder")
async def opposition_ladder(
    opponent: str | None = Query(None, description="opp_key"),
    fixture_id: str | None = Query(None, description="fixture whose grade ladder to read"),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Live ladder standing for an upcoming opponent (our row + theirs) from the
    fixture's grade. Current standings — upcoming-opponent context."""
    return await iq_service.opponent_ladder(db, str(club.id), opponent=opponent, fixture_id=fixture_id)


@router.post("/opposition/dossier/refresh")
async def refresh_opposition_dossier(
    opponent: str | None = Query(None),
    fixture_id: str | None = Query(None),
    team: str | None = Query(None, description="narrow the scout to one of the opponent's teams (a grade_id)"),
    name: str | None = Query(None, description="display name for a club outside our history"),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Force a rebuild of the dossier (Refresh button), bypassing the cache TTL."""
    opp_key, name, grade_id = await iq_service.resolve_opponent(
        db, str(club.id), opponent=opponent, fixture_id=fixture_id, display_name=name
    )
    key = opp_key or (name if grade_id else None)
    if not key:
        return {"status": "unavailable", "opponent": {"opp_key": None, "name": name}}
    return await iq_opponent.get_or_start_dossier(
        db, str(club.id), key, opp_name=name, grade_id=grade_id, team_grade_id=team, force=True
    )


@router.post("/opposition/match")
async def match_opponent(
    opponent_name: str = Query(..., description="the fixture's free-text opponent name"),
    opp_key: str = Query(..., description="the chosen club's opp_key to link it to"),
    display_name: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Persist a manual fixture-opponent → club link so it sticks for every
    fixture with this opponent name (now and future)."""
    await iq_service.save_opponent_alias(db, str(club.id), opponent_name, opp_key, display_name)
    return {"ok": True}


@router.get("/opposition/player-search")
async def opposition_player_search(
    q: str = Query(..., min_length=2, description="opponent player name (substring)"),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Search opposition players by name across every opponent we've faced (from
    the batters our bowlers have dismissed), so a scout can find a player without
    first picking their club. Each hit carries its club for a deep-link."""
    return await iq_service.search_opponent_players(db, str(club.id), q)


@router.get("/opposition/player-tags")
async def opposition_player_tags(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Our saved scouting tags for opponent players, keyed by participant_id (the
    dossier's player_id) — handedness, bowling type, role, danger flag and notes."""
    return await iq_service.get_opponent_tags(db, str(club.id))


@router.put("/opposition/player-tags/{player_id}")
async def save_opposition_player_tag(
    player_id: str,
    body: dict = Body(..., description="batting_hand, bowling_action, bowling_type, player_role, is_wicket_keeper, is_danger, notes, player_name"),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(get_current_user),
):
    """Add/update colour & detail on one opponent player (a manual scouting tag)."""
    return await iq_service.upsert_opponent_tag(db, str(club.id), player_id, body, user_id=str(user.id))


@router.get("/opposition/player-career")
async def opposition_player_career(
    org: str = Query(..., description="the opponent club's CA organisation GUID (dossier's opponent.org_id)"),
    player: str = Query(..., description="the player's CA participant GUID (dossier player_id)"),
    club_name: str | None = Query(None, description="club display name (for the cache + payload)"),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Last-5-years season-by-season career for ANY player at ANY club, from
    CA's public season-aggregate endpoints. The whole club is built once and
    cached (7 days); this slices the one player. Poll while ``building``."""
    return await iq_scout.get_player_career(db, str(club.id), org, player, club_name=club_name)


@router.get("/opposition/player-deep")
async def opposition_player_deep(
    org: str = Query(..., description="the opponent club's CA organisation GUID"),
    player: str = Query(..., description="the player's CA participant GUID"),
    player_name: str | None = Query(None),
    club_name: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Scorecard-level deep dive on one external player across the career
    window — dismissal patterns, batting position, conversion. Scans only the
    grades the player actually appeared in (bounded), so the first build takes
    a minute or two; poll while ``building``, cached 7 days after."""
    return await iq_scout.get_or_start_player_deep(
        db, str(club.id), org, player, player_name=player_name, club_name=club_name
    )


@router.post("/opposition/player-deep/refresh")
async def refresh_opposition_player_deep(
    org: str = Query(...),
    player: str = Query(...),
    player_name: str | None = Query(None),
    club_name: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Force a rebuild of one player's deep dive, bypassing the cache TTL."""
    return await iq_scout.get_or_start_player_deep(
        db, str(club.id), org, player, player_name=player_name, club_name=club_name, force=True
    )


# ─── Selection analysis (Phase 2) ────────────────────────────────────────────


@router.get("/selection/lineups")
async def selection_lineups(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Fixtures with a saved BetterSelect lineup, ready to analyse."""
    return await iq_selection.list_lineups(db, club)


@router.get("/selection/analysis")
async def selection_analysis(
    fixture_id: str = Query(..., description="fixture whose saved XI to analyse"),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Balance, form, warnings, promote/rest and fairness for a fixture's XI."""
    result = await iq_selection.selection_analysis(db, club, fixture_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Fixture not found")
    return result


# ─── Player trends & development (Phase 3) ───────────────────────────────────


@router.get("/trends/overview")
async def trends_overview(
    season_id: str | None = Query(None, description="season to analyse; omit for the latest"),
    grade_id: str | None = Query(None, description="filter to one grade/team (a grade name)"),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Club-wide development: breakout/decline movers + emerging, for the selected
    season and (optionally) grade."""
    return await iq_trends.trends_overview(db, str(club.id), season_id=season_id, grade_id=grade_id)


@router.get("/trends/players")
async def trends_players(
    season_id: str | None = Query(None, description="season to list players from; omit for the latest"),
    grade_id: str | None = Query(None, description="filter to one grade/team (a grade name)"),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Players (with stats) for the trends picker, scoped to the season/grade."""
    return await iq_trends.list_players(db, str(club.id), season_id=season_id, grade_id=grade_id)


@router.get("/trends/player/{player_id}")
async def trends_player(
    player_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """One player's trajectory, career totals, next milestones and verdict."""
    result = await iq_trends.player_trend(db, str(club.id), player_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return result


@router.get("/trends/player/{player_id}/deep")
async def trends_player_deep(
    player_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Conversion & starts, dismissal patterns, by-position, by-opposition and a
    scouting note for one player (analytics brief §1)."""
    result = await iq_trends.player_deep_dive(db, str(club.id), player_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return result


@router.get("/trends/player/{player_id}/bowling-deep")
async def trends_player_bowling_deep(
    player_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Wicket quality (set vs new batters), fielder combos, extras discipline and
    a bowling scouting note for one bowler (analytics brief §2.5/§2.9)."""
    result = await iq_trends.bowler_deep_dive(db, str(club.id), player_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return result


@router.get("/trends/player/{player_id}/radar")
async def trends_player_radar(
    player_id: str,
    season_id: str | None = Query(None, description="one season; omit for career"),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """A 6-axis batting/bowling radar normalised so the squad average sits on the
    50 ring (values 0–100). Powers the Player-trends profile radar."""
    return await iq_radar.player_radar(db, str(club.id), player_id, season_id=season_id)


# ─── Team self-analysis (analytics brief §7/§8) ──────────────────────────────


@router.get("/team/seasons")
async def team_seasons(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Seasons available for the team self-analysis filter."""
    return await iq_team.team_seasons(db, str(club.id))


@router.get("/team/grades")
async def team_grades(
    season_id: str | None = Query(None, description="grades (teams) fielded in this season"),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Grades (teams) for the team filter on the team-analysis page."""
    return await iq_team.team_grades(db, str(club.id), season_id)


@router.get("/team/overview")
async def team_overview(
    season_id: str | None = Query(None, description="filter to one season; omit for all-time"),
    grade_id: str | None = Query(None, description="filter to one grade/team within the season"),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Our own win/loss, batting & bowling profile, bat-first vs chase, score
    bands, venues, partnerships and a how-we-win/lose read."""
    return await iq_team.team_overview(db, str(club.id), season_id=season_id, grade_id=grade_id)


@router.get("/team/mvp")
async def team_mvp(
    season_id: str | None = Query(None, description="filter to one season; omit for the latest"),
    grade_id: str | None = Query(None, description="filter to one grade/team (a grade name)"),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Club MVP board — a season-value player-impact rating from season totals."""
    return await iq_team.player_impact(db, str(club.id), season_id=season_id, grade_id=grade_id)


@router.get("/team/phases")
async def team_phases(
    season_id: str | None = Query(None, description="filter to one season; omit for recent"),
    grade_id: str | None = Query(None, description="filter to one grade/team (a grade name)"),
    side: str = Query("bat", description="'bat' = our scoring shape, 'bowl' = what we concede"),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Our typical innings shape (Powerplay/Middle/Death) from recent ball-by-ball
    games. ``side='bat'`` profiles our batting; ``side='bowl'`` profiles what our
    attack concedes. Only live-scored matches carry ball data, so this covers
    recent games."""
    return await iq_phases.team_phases(
        db, str(club.id), season_id=season_id, grade_id=grade_id, side=("bowl" if side == "bowl" else "bat")
    )


@router.get("/opposition/phases")
async def opposition_phases(
    opponent: str | None = Query(None, description="opp_key"),
    fixture_id: str | None = Query(None, description="resolve the opponent from a fixture"),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """An opponent's typical innings shape from ball-by-ball data in our recent
    games against them (estimated; recent live-scored matches only)."""
    opp_key, name, _grade = await iq_service.resolve_opponent(
        db, str(club.id), opponent=opponent, fixture_id=fixture_id
    )
    return await iq_phases.opponent_phases(db, str(club.id), opp_key=opp_key, opp_name=name)


# ─── Post-match review (analytics brief §16.8) ───────────────────────────────


@router.get("/review/games")
async def review_games(
    season_id: str | None = Query(None, description="filter to one season"),
    grade_id: str | None = Query(None, description="filter to one grade/team (a grade name)"),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Recent completed games to review (newest first), optionally season/grade-scoped."""
    return await iq_review.list_review_games(db, str(club.id), season_id=season_id, grade_id=grade_id)


@router.get("/review/game/{game_id}")
async def review_game(
    game_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """One game's review — top contributions, best stand, extras, a collapse check
    and a what-changed-the-game synthesis."""
    result = await iq_review.game_review(db, str(club.id), game_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return result
