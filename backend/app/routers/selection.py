"""BetterSelect Phase 3 — team selection (lineups).

Pick a side for a fixture from the available pool. The pool is the club's
players annotated with their availability for THAT fixture's playing date
(availability is keyed on date, so one answer covers every fixture that day),
plus squad membership and the dormancy/recency signal the availability matrix
already computes.

Lineups are per-fixture: the same player can be selected for two fixtures on
the same weekend (the shared-player split case). Whether that's allowed/warned
is a rule layer that reads these rows — the storage itself doesn't constrain it.

All endpoints scoped to the caller's club via get_current_club.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_SELECTIONS, require_cap
from app.models.db import Fixture, FixtureLineup, Grade, Organisation, Player, Team, User, get_db
from app.routers.auth import get_current_club
from app.routers.availability import DEFAULT_DORMANCY_MONTHS, months_ago, resolve_period_statuses

router = APIRouter(prefix="/selection", tags=["selection"])

# Autofill scoring constants ─────────────────────────────────────────────────
# Window for "recent form" — last N batting innings & bowling spells per player.
# Tight enough to react to the current streak, wide enough to absorb one duck.
RECENT_FORM_GAMES = 4
# Weighting between recent form (last N innings) and season-to-date stats.
RECENT_FORM_WEIGHT = 0.6
SEASON_FORM_WEIGHT = 0.4
# A wicket is worth ~25 runs in cricket's standard equivalence, so wickets per
# innings are multiplied by this to land on the same scale as runs/innings.
WICKET_RUN_EQUIV = 25.0
# Hard activity wall for autofill eligibility. The frontend's "Recency" filter
# is just for the visible list; autofill always enforces this 12-month cutoff.
AUTOFILL_RECENCY_MONTHS = 12


def _compute_score(skill_positions: list[str] | None,
                   recent_bat: dict | None,
                   recent_bowl: dict | None,
                   season: dict | None) -> float:
    """Composite form score: 60% last-4 innings + 40% season-to-date, with the
    underlying stat chosen by role (batters on batting, bowlers on bowling,
    all-rounders blended). Output is on the "runs per innings" scale — typical
    range 0–60, with bowlers' wickets/inn rebased into the same units."""
    skills = {s.upper() for s in (skill_positions or []) if s}

    bat_recent = 0.0
    if recent_bat and recent_bat.get("innings"):
        bat_recent = float(recent_bat["total_runs"] or 0) / recent_bat["innings"]
    bat_season = float(season["batting_average"]) if (season and season.get("batting_average") is not None) else 0.0
    bat_score = RECENT_FORM_WEIGHT * bat_recent + SEASON_FORM_WEIGHT * bat_season

    bowl_recent = 0.0
    if recent_bowl and recent_bowl.get("innings"):
        bowl_recent = (float(recent_bowl["total_wickets"] or 0) / recent_bowl["innings"]) * WICKET_RUN_EQUIV
    bowl_season = 0.0
    if season and season.get("wickets") and season.get("bowling_innings"):
        bowl_season = (float(season["wickets"]) / float(season["bowling_innings"])) * WICKET_RUN_EQUIV
    bowl_score = RECENT_FORM_WEIGHT * bowl_recent + SEASON_FORM_WEIGHT * bowl_season

    is_bowler_only = "BWL" in skills and not (skills & {"BAT", "WKT", "ALL"})
    if is_bowler_only:
        return bowl_score
    if "ALL" in skills or ("BWL" in skills and skills & {"BAT", "WKT"}):
        return (bat_score + bowl_score) / 2.0
    return bat_score


def _tier_for(fx_seq: int | None, sq_seq: int | None) -> int | None:
    """Tier 1 = same XI, 2 = one grade below (promotion pool), 3 = one grade
    above (drop-down pool). None = too far (or no sequence on either side) —
    excluded from autofill though still visible in the pool list."""
    if not fx_seq or not sq_seq:
        return None
    if sq_seq == fx_seq:
        return 1
    if sq_seq == fx_seq + 1:
        return 2
    if sq_seq == fx_seq - 1:
        return 3
    return None


async def _recent_batting_form(db: AsyncSession, org_id) -> dict[str, dict]:
    """Per-player last-N batting innings: {total_runs, innings}. Excludes
    DNB/absent so a no-show doesn't drag the average down."""
    rows = await db.execute(
        text(
            """
            WITH ranked AS (
                SELECT ba.player_id, COALESCE(ba.runs, 0) AS runs,
                       ROW_NUMBER() OVER (PARTITION BY ba.player_id ORDER BY g.played_at DESC NULLS LAST) AS rn
                FROM batting_innings ba
                JOIN games g ON ba.game_id = g.id
                JOIN players p ON ba.player_id = p.id
                WHERE p.organisation_id = :org
                  AND COALESCE(ba.did_not_bat, false) = false
                  AND (ba.dismissal_type IS NULL
                       OR LOWER(ba.dismissal_type) NOT IN ('absent', 'did not bat', 'dnb'))
                  AND g.played_at IS NOT NULL
            )
            SELECT player_id, SUM(runs)::float AS total_runs, COUNT(*)::int AS innings
            FROM ranked WHERE rn <= :n GROUP BY player_id
            """
        ),
        {"org": org_id, "n": RECENT_FORM_GAMES},
    )
    return {str(pid): {"total_runs": runs, "innings": inns} for pid, runs, inns in rows.fetchall()}


async def _recent_bowling_form(db: AsyncSession, org_id) -> dict[str, dict]:
    """Per-player last-N bowling spells: {total_wickets, innings}."""
    rows = await db.execute(
        text(
            """
            WITH ranked AS (
                SELECT bs.player_id, COALESCE(bs.wickets, 0) AS wickets,
                       ROW_NUMBER() OVER (PARTITION BY bs.player_id ORDER BY g.played_at DESC NULLS LAST) AS rn
                FROM bowling_spells bs
                JOIN games g ON bs.game_id = g.id
                JOIN players p ON bs.player_id = p.id
                WHERE p.organisation_id = :org
                  AND g.played_at IS NOT NULL
            )
            SELECT player_id, SUM(wickets)::float AS total_wickets, COUNT(*)::int AS innings
            FROM ranked WHERE rn <= :n GROUP BY player_id
            """
        ),
        {"org": org_id, "n": RECENT_FORM_GAMES},
    )
    return {str(pid): {"total_wickets": wkts, "innings": inns} for pid, wkts, inns in rows.fetchall()}


async def _latest_season_stats(db: AsyncSession, org_id) -> dict[str, dict]:
    """Per-player most-recent season's aggregate stats. Falls back to the most
    recent season the player has any data for — picking 'current season'
    explicitly is fragile pre-season when no games have been played yet."""
    rows = await db.execute(
        text(
            """
            SELECT DISTINCT ON (pss.player_id)
                pss.player_id,
                pss.batting_average, pss.runs, pss.batting_innings,
                pss.wickets, pss.bowling_innings
            FROM player_season_stats pss
            JOIN seasons s ON pss.season_id = s.id
            JOIN players p ON pss.player_id = p.id
            WHERE p.organisation_id = :org
            ORDER BY pss.player_id, s.year DESC NULLS LAST
            """
        ),
        {"org": org_id},
    )
    out: dict[str, dict] = {}
    for pid, bavg, runs, batt_inn, wkts, bowl_inn in rows.fetchall():
        out[str(pid)] = {
            "batting_average": bavg,
            "runs": runs,
            "batting_innings": batt_inn,
            "wickets": wkts,
            "bowling_innings": bowl_inn,
        }
    return out


class LineupSlot(BaseModel):
    player_id: str
    batting_order: Optional[int] = None
    is_captain: bool = False
    is_wicket_keeper: bool = False


class LineupSet(BaseModel):
    players: list[LineupSlot]


class TeamSizeSet(BaseModel):
    size: int


async def _get_owned_fixture(db: AsyncSession, fixture_id: str, club_id) -> Fixture:
    f = await db.get(Fixture, uuid.UUID(fixture_id))
    if not f or f.organisation_id != club_id:
        raise HTTPException(status_code=404, detail="Fixture not found")
    return f


@router.get("/overview")
async def selection_overview(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """All upcoming fixtures with their finalised lineups, for the side-by-side
    board. One row per fixture, players in batting order. Declared before the
    /{fixture_id} route so 'overview' isn't read as a fixture id.
    """
    fx_res = await db.execute(
        select(Fixture)
        .where(Fixture.organisation_id == club.id, Fixture.played_on >= date.today())
        .order_by(Fixture.played_on.asc().nullslast(), Fixture.start_time.asc().nullslast())
    )
    fixtures = fx_res.scalars().all()
    if not fixtures:
        return {"fixtures": []}

    # Team names, to show which of our teams each fixture belongs to.
    tm_res = await db.execute(select(Team).where(Team.organisation_id == club.id))
    team_names = {str(t.id): (t.short_name or t.name) for t in tm_res.scalars().all()}

    # Lineups for these fixtures, with player display name + flags, in order.
    rows_res = await db.execute(
        select(
            FixtureLineup.fixture_id,
            FixtureLineup.batting_order,
            FixtureLineup.is_captain,
            FixtureLineup.is_wicket_keeper,
            func.coalesce(Player.display_name_override, Player.name),
            Player.id,
        )
        .join(Player, FixtureLineup.player_id == Player.id)
        .where(FixtureLineup.organisation_id == club.id)
        .order_by(FixtureLineup.batting_order.asc().nullslast())
    )
    by_fixture: dict[str, list] = {}
    for fid, order, cap, wk, name, pid in rows_res.fetchall():
        by_fixture.setdefault(str(fid), []).append({
            "player_id": str(pid), "display_name": name,
            "batting_order": order, "is_captain": cap, "is_wicket_keeper": wk,
        })

    return {
        "fixtures": [
            {
                "id": str(f.id),
                "label": f.label,
                "opponent_name": f.opponent_name,
                "home_away": f.home_away,
                "played_on": f.played_on.isoformat() if f.played_on else None,
                "round": f.round,
                "venue": f.venue,
                "team_name": team_names.get(str(f.team_id)) if f.team_id else None,
                "lineup": by_fixture.get(str(f.id), []),
            }
            for f in fixtures
        ]
    }


@router.get("/selected-players")
async def selected_players(
    on: Optional[str] = None,
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Player ids named in ANY saved XI for a round.

    A "round" is a Mon–Sun week. Anchor it with ?on=YYYY-MM-DD (expanded to that
    date's week) or an explicit ?from=&to= window. Powers the cross-screen
    "Selected" filter: a player counts as selected if they're picked in some XI
    that round (one XI per date is enforced on save, so it's unambiguous).
    Declared before /{fixture_id} so the literal path isn't read as an id.
    """
    if from_ and to:
        start, end = date.fromisoformat(from_), date.fromisoformat(to)
    elif on:
        anchor = date.fromisoformat(on)
        start = anchor - timedelta(days=anchor.weekday())
        end = start + timedelta(days=6)
    else:
        raise HTTPException(status_code=400, detail="Provide ?on= or ?from=&to=")
    if end < start:
        start, end = end, start

    res = await db.execute(
        text(
            "SELECT DISTINCT fl.player_id FROM fixture_lineups fl "
            "JOIN fixtures f ON fl.fixture_id = f.id "
            "WHERE fl.organisation_id = :org "
            "AND ((f.played_on BETWEEN :start AND :end) "
            "OR (f.end_on BETWEEN :start AND :end))"
        ),
        {"org": club.id, "start": start, "end": end},
    )
    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "player_ids": [str(r[0]) for r in res.fetchall()],
    }


@router.get("/{fixture_id}")
async def get_selection(
    fixture_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """A fixture's lineup + the pickable pool with per-date availability.

    Pool players carry: availability status for the fixture date, squads (manual
    + recent history), recency (last_played / is_dormant), and whether they're
    already in the lineup. The frontend builds the selection board from this.
    """
    fx = await _get_owned_fixture(db, fixture_id, club.id)

    # Existing lineup for this fixture.
    lu_res = await db.execute(
        select(FixtureLineup).where(FixtureLineup.fixture_id == fx.id)
    )
    lineup_rows = lu_res.scalars().all()
    lineup = {str(r.player_id): r for r in lineup_rows}

    months = club.dormancy_months if club.dormancy_months else DEFAULT_DORMANCY_MONTHS
    cutoff = months_ago(date.today(), months)

    # last_played per player (recency).
    last_played: dict[str, date] = {}
    lp_res = await db.execute(
        text(
            "SELECT ga.player_id, MAX(g.played_at) FROM game_appearances ga "
            "JOIN games g ON ga.game_id = g.id "
            "JOIN players p ON ga.player_id = p.id "
            "WHERE p.organisation_id = :org GROUP BY ga.player_id"
        ),
        {"org": club.id},
    )
    for pid, lp in lp_res.fetchall():
        last_played[str(pid)] = lp

    # Squads: manual membership unioned with recent appearance team-names.
    squads: dict[str, set] = {}
    sq_res = await db.execute(
        text(
            "SELECT DISTINCT ga.player_id, ga.team_name FROM game_appearances ga "
            "JOIN games g ON ga.game_id = g.id "
            "JOIN players p ON ga.player_id = p.id "
            "WHERE p.organisation_id = :org AND ga.team_name IS NOT NULL "
            "AND ga.team_name <> '' AND g.played_at >= :cutoff"
        ),
        {"org": club.id, "cutoff": cutoff},
    )
    for pid, name in sq_res.fetchall():
        squads.setdefault(str(pid), set()).add(name.strip())
    mem_res = await db.execute(
        text(
            "SELECT tm.player_id, t.name FROM team_members tm "
            "JOIN teams t ON tm.team_id = t.id "
            "WHERE tm.organisation_id = :org AND t.name IS NOT NULL AND t.name <> ''"
        ),
        {"org": club.id},
    )
    for pid, name in mem_res.fetchall():
        squads.setdefault(str(pid), set()).add(name.strip())

    # Availability for this fixture's playing date(s). Availability is keyed on
    # date; the relevant answer is for played_on (week 1). One row per player.
    avail: dict[str, str] = {}
    avail_reason: dict[str, str] = {}
    if fx.played_on:
        av_res = await db.execute(
            text(
                "SELECT player_id, status FROM player_availability "
                "WHERE organisation_id = :org AND avail_date = :d"
            ),
            {"org": club.id, "d": fx.played_on},
        )
        for pid, status in av_res.fetchall():
            avail[str(pid)] = status
        # Fall back to a covering availability period where the admin hasn't set
        # an explicit answer for this date (explicit wins). Carries the reason.
        period_map = await resolve_period_statuses(db, club.id, [fx.played_on])
        for pid, info in period_map.get(fx.played_on.isoformat(), {}).items():
            if pid not in avail:
                avail[pid] = info["status"]
                if info.get("reason"):
                    avail_reason[pid] = info["reason"]

    # Players also already selected for ANOTHER fixture on the same date —
    # surfaced so the UI can flag a clash (rule layer decides if it's allowed).
    clash: dict[str, list] = {}
    if fx.played_on:
        cl_res = await db.execute(
            text(
                "SELECT fl.player_id, COALESCE(t.name, f.label, f.opponent_name) AS where_ "
                "FROM fixture_lineups fl "
                "JOIN fixtures f ON fl.fixture_id = f.id "
                "LEFT JOIN teams t ON f.team_id = t.id "
                "WHERE fl.organisation_id = :org AND f.id <> :fid "
                "AND f.played_on = :d"
            ),
            {"org": club.id, "fid": fx.id, "d": fx.played_on},
        )
        for pid, where_ in cl_res.fetchall():
            clash.setdefault(str(pid), []).append(where_ or "another fixture")

    pl_res = await db.execute(
        select(Player).where(
            Player.organisation_id == club.id,
            Player.is_player.is_(True),
        )
    )
    players = pl_res.scalars().all()

    # Fixture's team sequence + grade gender, used to compute autofill tier
    # and the women's/men's hard wall. Either may be missing (manual fixture
    # with no team / unranked team) — the rules degrade gracefully.
    fx_team_seq: int | None = None
    if fx.team_id:
        fx_team_obj = await db.get(Team, fx.team_id)
        if fx_team_obj and (fx_team_obj.sequence or 0) > 0:
            fx_team_seq = fx_team_obj.sequence
    fx_is_women = False
    if fx.grade_id:
        fx_grade_obj = await db.get(Grade, fx.grade_id)
        if fx_grade_obj:
            fx_is_women = (fx_grade_obj.fee_format == "women")

    # Per-squad-team metadata: sequence + women's-grade flag. One query covers
    # every team in the club so the per-player loop stays in-memory.
    squad_meta: dict[str, tuple[int, bool]] = {}
    sq_meta_res = await db.execute(
        select(Team.id, Team.sequence, Grade.fee_format)
        .select_from(Team)
        .outerjoin(Grade, Team.grade_id == Grade.id)
        .where(Team.organisation_id == club.id)
    )
    for tid, seq, fee in sq_meta_res.fetchall():
        squad_meta[str(tid)] = (seq or 0, fee == "women")

    recent_bat = await _recent_batting_form(db, club.id)
    recent_bowl = await _recent_bowling_form(db, club.id)
    season_stats = await _latest_season_stats(db, club.id)

    autofill_cutoff = months_ago(date.today(), AUTOFILL_RECENCY_MONTHS)
    _fixture_team_id = str(fx.team_id) if fx.team_id else None

    pool = []
    for p in players:
        pid = str(p.id)
        lp = last_played.get(pid)
        dormant = bool(lp) and lp < cutoff
        manual_inactive = p.status == "inactive"
        sq_tid = str(p.squad_team_id) if p.squad_team_id else None
        sq_seq, sq_is_women = squad_meta.get(sq_tid, (0, False)) if sq_tid else (0, False)

        squad_match = bool(_fixture_team_id and sq_tid == _fixture_team_id)
        # Tier degrades to "same-squad = tier 1" when the fixture team has no
        # sequence configured, so clubs that haven't ranked their teams still
        # get sensible autofill (just no promotion/drop-down spill).
        if fx_team_seq:
            tier = _tier_for(fx_team_seq, sq_seq)
        else:
            tier = 1 if squad_match else None

        gender_ok = (fx_is_women == sq_is_women)
        recent_ok = bool(lp) and lp >= autofill_cutoff
        score = _compute_score(p.skill_positions, recent_bat.get(pid), recent_bowl.get(pid), season_stats.get(pid))

        pool.append({
            "id": pid,
            "display_name": p.display_name,
            "player_role": p.player_role,
            "skill_positions": p.skill_positions or [],
            "squads": sorted(squads.get(pid, [])),
            "squad_team_id": sq_tid,
            "availability": avail.get(pid, "NO_RESPONSE"),
            "availability_reason": avail_reason.get(pid),
            "last_played": lp.isoformat() if lp else None,
            "photo_url": p.photo_url,
            "batting_hand": p.batting_hand,
            "bowling_action": p.bowling_action,
            "bowling_type": p.bowling_type,
            "is_opening_batsman": p.is_opening_batsman,
            "is_dormant": dormant and not manual_inactive,
            "is_inactive": manual_inactive,
            "is_current": not manual_inactive and not dormant,
            "selected": pid in lineup,
            "clash": clash.get(pid, []),
            "squad_match": squad_match,
            "tier": tier,
            "score": round(score, 2),
            "autofill_eligible": bool(
                tier in (1, 2, 3)
                and recent_ok
                and gender_ok
                and not manual_inactive
            ),
        })

    # Display ordering: tier first (so own-squad bubbles to the top), then the
    # composite score within a tier, then availability, then name. Autofill
    # itself walks tiers explicitly on the frontend — this sort is just for the
    # pool list the selector scrolls.
    _AVAIL_RANK = {"AVAILABLE": 0, "MAYBE": 1, "NO_RESPONSE": 2, "UNAVAILABLE": 3}
    pool.sort(key=lambda e: (
        e["tier"] if e["tier"] is not None else 99,
        -(e["score"] or 0.0),
        _AVAIL_RANK.get(e["availability"], 9),
        (e["display_name"] or "").lower(),
    ))

    return {
        "fixture": {
            "id": str(fx.id),
            "label": fx.label,
            "opponent_name": fx.opponent_name,
            "home_away": fx.home_away,
            "played_on": fx.played_on.isoformat() if fx.played_on else None,
            "end_on": fx.end_on.isoformat() if fx.end_on else None,
            "start_time": fx.start_time,
            "round": fx.round,
            "venue": fx.venue,
            "home_team": fx.home_team,
            "away_team": fx.away_team,
            "team_id": str(fx.team_id) if fx.team_id else None,
        },
        "lineup": [
            {
                "player_id": str(r.player_id),
                "batting_order": r.batting_order,
                "is_captain": r.is_captain,
                "is_wicket_keeper": r.is_wicket_keeper,
            }
            for r in sorted(lineup_rows, key=lambda r: (r.batting_order or 999))
        ],
        "pool": pool,
        "dormancy_months": months,
        "default_team_size": club.default_team_size if club.default_team_size is not None else 11,
    }


@router.get("/{fixture_id}/previous-xi")
async def previous_xi(
    fixture_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """The most recent prior fixture's named XI, for "fill from last week".

    Looks back for the same team's last fixture (before this one's date) that has
    a saved lineup; falls back to any of the club's prior fixtures with a lineup
    if the team has no history. Returns player ids in batting order plus the
    captain/keeper, so the selection board can seed empty slots.
    """
    fx = await _get_owned_fixture(db, fixture_id, club.id)

    # Candidate prior fixtures: before this fixture's date (nulls last), newest
    # first, same team preferred. We pick the first that actually has a lineup.
    q = (
        select(Fixture)
        .where(
            Fixture.organisation_id == club.id,
            Fixture.id != fx.id,
        )
    )
    if fx.played_on:
        q = q.where(Fixture.played_on < fx.played_on)
    q = q.order_by(Fixture.played_on.desc().nullslast(), Fixture.start_time.desc().nullslast())
    prior = (await db.execute(q)).scalars().all()

    # Prefer same-team history, then anything.
    ordered = [f for f in prior if fx.team_id and f.team_id == fx.team_id] + \
              [f for f in prior if not (fx.team_id and f.team_id == fx.team_id)]

    for f in ordered:
        rows = (await db.execute(
            select(FixtureLineup).where(FixtureLineup.fixture_id == f.id)
        )).scalars().all()
        if not rows:
            continue
        rows.sort(key=lambda r: (r.batting_order or 999))
        return {
            "source_fixture_id": str(f.id),
            "source_label": f.opponent_name or f.label,
            "source_round": f.round,
            "source_date": f.played_on.isoformat() if f.played_on else None,
            "player_ids": [str(r.player_id) for r in rows],
            "captain_id": next((str(r.player_id) for r in rows if r.is_captain), None),
            "wicket_keeper_id": next((str(r.player_id) for r in rows if r.is_wicket_keeper), None),
        }

    return {"source_fixture_id": None, "player_ids": [], "captain_id": None, "wicket_keeper_id": None}


@router.post("/default-team-size")
async def set_default_team_size(
    body: TeamSizeSet,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """Persist the club's default lineup size (0 = no limit). Editable here by
    selectors so the Selection format selector sticks across reloads."""
    if body.size not in (0, 11, 12, 13):
        raise HTTPException(status_code=400, detail="Invalid team size")
    club.default_team_size = body.size
    await db.commit()
    return {"status": "ok", "default_team_size": body.size}


@router.put("/{fixture_id}")
async def set_selection(
    fixture_id: str,
    body: LineupSet,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """Replace a fixture's lineup with the given set of players.

    Full-replace (not incremental): the selection board sends the whole side.
    Validates players belong to the club; de-dupes; clamps roles. Cross-fixture
    clash is reported by GET but NOT blocked here — that policy is deferred.
    """
    fx = await _get_owned_fixture(db, fixture_id, club.id)

    # Validate + de-dupe incoming player ids.
    seen: set[uuid.UUID] = set()
    slots: list[LineupSlot] = []
    for s in body.players:
        pid = uuid.UUID(s.player_id)
        if pid in seen:
            continue
        seen.add(pid)
        slots.append(s)

    if seen:
        owned_res = await db.execute(
            select(Player.id).where(
                Player.organisation_id == club.id,
                Player.id.in_(seen),
            )
        )
        owned = {r[0] for r in owned_res.fetchall()}
        missing = seen - owned
        if missing:
            raise HTTPException(status_code=400, detail="One or more players are not in your club")

        # Clash policy: a player may be in only ONE XI per date. Block the save
        # if any picked player is already selected for another fixture that day.
        # ORM .in_() (portable param binding) rather than raw ANY(array).
        if fx.played_on:
            clash_res = await db.execute(
                select(func.coalesce(Player.display_name_override, Player.name))
                .select_from(FixtureLineup)
                .join(Fixture, FixtureLineup.fixture_id == Fixture.id)
                .join(Player, FixtureLineup.player_id == Player.id)
                .where(
                    FixtureLineup.organisation_id == club.id,
                    Fixture.id != fx.id,
                    Fixture.played_on == fx.played_on,
                    FixtureLineup.player_id.in_(seen),
                )
                .distinct()
                .order_by(func.coalesce(Player.display_name_override, Player.name))
            )
            clashing = [r[0] for r in clash_res.fetchall()]
            if clashing:
                names = ", ".join(clashing)
                raise HTTPException(
                    status_code=409,
                    detail=f"Already selected for another fixture on {fx.played_on.isoformat()}: {names}",
                )

    # Replace: clear existing rows, insert the new set.
    await db.execute(
        text("DELETE FROM fixture_lineups WHERE fixture_id = :fid"),
        {"fid": fx.id},
    )
    for s in slots:
        db.add(FixtureLineup(
            fixture_id=fx.id,
            player_id=uuid.UUID(s.player_id),
            organisation_id=club.id,
            batting_order=s.batting_order,
            is_captain=bool(s.is_captain),
            is_wicket_keeper=bool(s.is_wicket_keeper),
            selected_by=user.id,
        ))
    await db.commit()
    return {"status": "ok", "count": len(slots)}
