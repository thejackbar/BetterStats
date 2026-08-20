"""Shared BetterSelect selection-pool assembly.

Extracted from ``routers/selection.py`` so BetterIQ's selection analysis can
reuse the **exact** eligibility model — recency wall, women's/men's gender wall,
squad tier (same-XI / promotion / drop-down) and per-date availability — instead
of re-deriving it and drifting (which produced ghosts like a women's player or a
years-dormant name appearing as a "promote" suggestion for a men's 2nd XI).

``routers/selection`` delegates ``GET /selection/{fixture_id}`` to
``assemble_selection`` here; BetterIQ calls the same function.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import FixtureLineup, Grade, Player, Season, Team
from app.routers.availability import DEFAULT_DORMANCY_MONTHS, months_ago, resolve_period_statuses
from app.auth.modules import org_has_module
from app.services import player_age

# Autofill scoring constants ─────────────────────────────────────────────────
# Window for "recent form" — last N batting innings & bowling spells per player.
RECENT_FORM_GAMES = 4
RECENT_FORM_WEIGHT = 0.6
SEASON_FORM_WEIGHT = 0.4
# A wicket is worth ~25 runs in cricket's standard equivalence.
WICKET_RUN_EQUIV = 25.0
# Hard activity wall for autofill eligibility (12-month cutoff).
AUTOFILL_RECENCY_MONTHS = 12
# How far back "has been at training" looks. Three weeks covers a normal
# Tuesday/Thursday nets programme plus one missed week, which is the question a
# selector is actually asking — not "has this person ever attended".
TRAINING_WINDOW_DAYS = 21


async def _owing_player_ids(session: AsyncSession, club) -> set[str] | None:
    """Players who still owe the club money, or None when we can't tell.

    Reads BetterFees' own balance rather than a second idea of it: a balance
    is derived, never stored, so anything asking "who owes" has to run the
    same calculation the Accounts screen runs or the two start disagreeing.
    None (not an empty set) when the club doesn't hold BetterFees or has no
    season to price against — the difference matters, because "nobody owes"
    and "we have no way of knowing" should not look the same on the board.
    """
    if not org_has_module(club, "fees"):
        return None
    from app.services import fees as fees_svc

    season_id = (await session.execute(
        select(Season.id).where(Season.organisation_id == club.id)
        .order_by(Season.year.desc().nullslast(), Season.name.desc()).limit(1)
    )).scalar_one_or_none()
    if not season_id:
        return None
    try:
        return {str(pid) for pid in await fees_svc.owing_player_ids(session, club.id, season_id)}
    except Exception:
        # A fees calculation that falls over must not take the whole
        # selection board down with it — the filter degrades to "we can't
        # tell", which is what the override is there for.
        return None


async def _trained_player_ids(session: AsyncSession, club, as_of: date) -> set[str] | None:
    """Players who turned up to nets inside the window ending ``as_of``.

    Net Manager records a check-in per session (``net_attendance``); a row's
    existence IS the attendance. Guests carry no player_id and are skipped by
    the join. None when the club has run no sessions in range at all, so a
    club that doesn't use Net Manager gets "we can't tell" rather than a
    board saying nobody has trained.
    """
    rows = (await session.execute(
        text(
            "SELECT DISTINCT na.player_id FROM net_attendance na "
            "JOIN net_sessions ns ON ns.id = na.session_id "
            "WHERE na.organisation_id = :org AND na.player_id IS NOT NULL "
            "AND ns.session_date <= :as_of AND ns.session_date >= :since"
        ),
        {"org": club.id, "as_of": as_of, "since": as_of - timedelta(days=TRAINING_WINDOW_DAYS)},
    )).fetchall()
    any_session = (await session.execute(
        text(
            "SELECT 1 FROM net_sessions WHERE organisation_id = :org "
            "AND session_date <= :as_of AND session_date >= :since LIMIT 1"
        ),
        {"org": club.id, "as_of": as_of, "since": as_of - timedelta(days=TRAINING_WINDOW_DAYS)},
    )).first()
    if not any_session:
        return None
    return {str(r[0]) for r in rows}


def _compute_score(skill_positions: list[str] | None,
                   recent_bat: dict | None,
                   recent_bowl: dict | None,
                   season: dict | None) -> float:
    """Composite form score: 60% last-4 innings + 40% season-to-date, with the
    underlying stat chosen by role. Output is on the runs-per-innings scale."""
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
    """Tier 1 = same XI, 2 = one grade below (promotion), 3 = one grade above
    (drop-down). None = too far / unranked — excluded from autofill."""
    if not fx_seq or not sq_seq:
        return None
    if sq_seq == fx_seq:
        return 1
    if sq_seq == fx_seq + 1:
        return 2
    if sq_seq == fx_seq - 1:
        return 3
    return None


def _clash_blocks(this_seq: int | None, other_seqs: list[int | None]) -> bool:
    """Whether a same-date selection elsewhere blocks picking the player here.

    A higher grade (strictly lower team sequence — 1st XI = 1, 2nd XI = 2 …)
    takes precedence over a lower one, so a clash is *overridable* — the player
    can be called up — only when THIS fixture outranks every other XI they're
    named in. If our own rank is unknown, or any clashing XI is the same/a
    higher grade (or its rank is unknown), the pick stays blocked."""
    if not other_seqs:
        return False
    if not this_seq:
        return True
    return any((not s) or this_seq >= s for s in other_seqs)


async def _recent_batting_form(db: AsyncSession, org_id) -> dict[str, dict]:
    """Per-player last-N batting innings: {total_runs, innings, series}. Excludes
    DNB/absent so a no-show doesn't drag the average down. ``series`` is the
    per-innings runs ordered oldest→newest (so a sparkline reads left→right)."""
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
            SELECT player_id, SUM(runs)::float AS total_runs, COUNT(*)::int AS innings,
                   array_agg(runs ORDER BY rn DESC) AS series
            FROM ranked WHERE rn <= :n GROUP BY player_id
            """
        ),
        {"org": org_id, "n": RECENT_FORM_GAMES},
    )
    return {
        str(pid): {"total_runs": runs, "innings": inns, "series": [int(x) for x in (series or [])]}
        for pid, runs, inns, series in rows.fetchall()
    }


async def _recent_bowling_form(db: AsyncSession, org_id) -> dict[str, dict]:
    """Per-player last-N bowling spells: {total_wickets, innings, series}. ``series``
    is the per-spell wickets ordered oldest→newest."""
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
            SELECT player_id, SUM(wickets)::float AS total_wickets, COUNT(*)::int AS innings,
                   array_agg(wickets ORDER BY rn DESC) AS series
            FROM ranked WHERE rn <= :n GROUP BY player_id
            """
        ),
        {"org": org_id, "n": RECENT_FORM_GAMES},
    )
    return {
        str(pid): {"total_wickets": wkts, "innings": inns, "series": [int(x) for x in (series or [])]}
        for pid, wkts, inns, series in rows.fetchall()
    }


def _is_bowler_only(skills: set[str]) -> bool:
    return "BWL" in skills and not (skills & {"BAT", "WKT", "ALL"})


def _recent_level(skills: set[str], recent_bat: dict | None, recent_bowl: dict | None) -> tuple[float | None, bool]:
    """Recent-only composite on the runs-per-innings scale + whether a sample
    exists. Mirrors the role weighting in ``_compute_score`` but recent-only."""
    bat_inn = (recent_bat or {}).get("innings") or 0
    bowl_inn = (recent_bowl or {}).get("innings") or 0
    bat = (float(recent_bat["total_runs"]) / bat_inn) if bat_inn else None
    bowl = ((float(recent_bowl["total_wickets"]) / bowl_inn) * WICKET_RUN_EQUIV) if bowl_inn else None
    if _is_bowler_only(skills):
        return bowl, bowl is not None
    if "ALL" in skills or ("BWL" in skills and skills & {"BAT", "WKT"}):
        vals = [v for v in (bat, bowl) if v is not None]
        return (sum(vals) / len(vals) if vals else None), bool(vals)
    return bat, bat is not None


def _season_level(skills: set[str], season: dict | None) -> float | None:
    """Season baseline on the same runs-per-innings scale (for the form trend)."""
    if not season:
        return None
    bat = float(season["batting_average"]) if season.get("batting_average") is not None else None
    bowl = None
    if season.get("wickets") and season.get("bowling_innings"):
        bowl = (float(season["wickets"]) / float(season["bowling_innings"])) * WICKET_RUN_EQUIV
    if _is_bowler_only(skills):
        return bowl
    if "ALL" in skills or ("BWL" in skills and skills & {"BAT", "WKT"}):
        vals = [v for v in (bat, bowl) if v is not None]
        return sum(vals) / len(vals) if vals else None
    return bat


def _form_word(level: float | None, baseline: float | None, has_recent: bool) -> str | None:
    """A quiet form bucket blending the recent level with its trend vs the
    season baseline. None when there's no recent sample to judge from."""
    if not has_recent or level is None:
        return None
    rising = baseline is not None and level >= baseline + 8
    falling = baseline is not None and level <= baseline - 10
    if level >= 40:
        return "warm" if falling else "hot"
    if level >= 26:
        return "hot" if (rising and level >= 34) else "warm"
    if level >= 16:
        return "warm" if rising else "steady"
    if level >= 8:
        return "steady" if rising else "quiet"
    return "quiet" if rising else "cold"


def _recent_series(skills: set[str], recent_bat: dict | None, recent_bowl: dict | None) -> list[int]:
    """The role-appropriate last-4 series for the sparkline (bat runs for
    bat-led/all-rounders, spell wickets for bowler-only; bat as a fallback)."""
    if _is_bowler_only(skills):
        return list((recent_bowl or {}).get("series") or [])
    bat = list((recent_bat or {}).get("series") or [])
    return bat if bat else list((recent_bowl or {}).get("series") or [])


async def _latest_season_stats(db: AsyncSession, org_id) -> dict[str, dict]:
    """Per-player most-recent season's aggregate stats."""
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
            -- Scope to this org's seasons. Without it, a dual-club player
            -- (shared CA participant GUID) could resolve their "latest season"
            -- form snapshot to another club's season (see migration 060).
            WHERE p.organisation_id = :org AND s.organisation_id = :org
            ORDER BY pss.player_id, s.year DESC NULLS LAST
            """
        ),
        {"org": org_id},
    )
    out: dict[str, dict] = {}
    for pid, bavg, runs, batt_inn, wkts, bowl_inn in rows.fetchall():
        out[str(pid)] = {
            "batting_average": bavg, "runs": runs, "batting_innings": batt_inn,
            "wickets": wkts, "bowling_innings": bowl_inn,
        }
    return out


async def assemble_selection(db: AsyncSession, club, fx) -> dict:
    """A fixture's lineup + the pickable pool with per-date availability,
    recency, squad tier, gender wall and a composite form score per player.

    Identical to the data BetterSelect's selection board is built from.
    """
    # Existing lineup for this fixture.
    lu_res = await db.execute(select(FixtureLineup).where(FixtureLineup.fixture_id == fx.id))
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

    # Availability for this fixture's playing date (explicit answer wins; period fallback).
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
        period_map = await resolve_period_statuses(db, club.id, [fx.played_on])
        for pid, info in period_map.get(fx.played_on.isoformat(), {}).items():
            if pid not in avail:
                avail[pid] = info["status"]
                if info.get("reason"):
                    avail_reason[pid] = info["reason"]

    # Players already selected for ANOTHER fixture on the same date (clash). We
    # also keep each clashing XI's team sequence so the pool can flag whether
    # THIS fixture outranks it (a higher grade can call the player up) or not.
    clash: dict[str, list] = {}
    clash_seqs: dict[str, list] = {}
    # Per clashing XI, the fixture id + this player's batting slot there, so the
    # board can cascade a bumped player down into a called-up player's vacated
    # slot in the lower team (see routers/selection save).
    clash_detail: dict[str, list] = {}
    if fx.played_on:
        cl_res = await db.execute(
            text(
                "SELECT fl.player_id, COALESCE(t.name, f.label, f.opponent_name) AS where_, t.sequence AS seq, "
                "fl.fixture_id AS fid, fl.batting_order AS bo "
                "FROM fixture_lineups fl "
                "JOIN fixtures f ON fl.fixture_id = f.id "
                "LEFT JOIN teams t ON f.team_id = t.id "
                "WHERE fl.organisation_id = :org AND f.id <> :fid "
                "AND f.played_on = :d"
            ),
            {"org": club.id, "fid": fx.id, "d": fx.played_on},
        )
        for pid, where_, seq, other_fid, bo in cl_res.fetchall():
            clash.setdefault(str(pid), []).append(where_ or "another fixture")
            clash_seqs.setdefault(str(pid), []).append(seq)
            clash_detail.setdefault(str(pid), []).append({
                "fixture_id": str(other_fid),
                "team_name": where_ or "another fixture",
                "seq": seq,
                "batting_order": bo,
            })

    pl_res = await db.execute(
        select(Player).where(Player.organisation_id == club.id, Player.is_player.is_(True))
    )
    players = pl_res.scalars().all()

    # Fixture's team sequence + grade gender, for autofill tier + gender wall.
    # Also capture the team/grade display names + seniority so the selection
    # board can show (and switch between) which of our teams is being picked.
    fx_team_seq: int | None = None
    fx_team_name: str | None = None
    if fx.team_id:
        fx_team_obj = await db.get(Team, fx.team_id)
        if fx_team_obj:
            fx_team_name = fx_team_obj.short_name or fx_team_obj.name
            if (fx_team_obj.sequence or 0) > 0:
                fx_team_seq = fx_team_obj.sequence
    fx_is_women = False
    fx_grade_name: str | None = None
    if fx.grade_id:
        fx_grade_obj = await db.get(Grade, fx.grade_id)
        if fx_grade_obj:
            fx_is_women = (fx_grade_obj.fee_format == "women")
            fx_grade_name = fx_grade_obj.display_name_override or fx_grade_obj.name

    # Per-squad-team metadata: sequence + women's-grade flag.
    squad_meta: dict[str, tuple[int, bool]] = {}
    sq_meta_res = await db.execute(
        select(Team.id, Team.sequence, Grade.fee_format)
        .select_from(Team)
        .outerjoin(Grade, Team.grade_id == Grade.id)
        .where(Team.organisation_id == club.id)
    )
    for tid, seq, fee in sq_meta_res.fetchall():
        squad_meta[str(tid)] = (seq or 0, fee == "women")

    # The two module-derived selection flags. Both can come back None — "we
    # can't tell" — in which case only a per-player override answers, which is
    # exactly the club that runs neither module ticking a box by hand.
    owing_ids = await _owing_player_ids(db, club)
    trained_ids = await _trained_player_ids(db, club, fx.played_on or date.today())

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
        if fx_team_seq:
            tier = _tier_for(fx_team_seq, sq_seq)
        else:
            tier = 1 if squad_match else None

        gender_ok = (fx_is_women == sq_is_women)
        recent_ok = bool(lp) and lp >= autofill_cutoff
        rb, rw, ss = recent_bat.get(pid), recent_bowl.get(pid), season_stats.get(pid)
        score = _compute_score(p.skill_positions, rb, rw, ss)

        # Quiet form indicator: a last-4 sparkline series + a trend-aware word
        # (recent level vs season baseline). Frontend renders the bars + word;
        # if the series is empty it shows the word alone (or nothing if None).
        skills_set = {s.upper() for s in (p.skill_positions or []) if s}
        rlevel, has_recent = _recent_level(skills_set, rb, rw)
        form_word = _form_word(rlevel, _season_level(skills_set, ss), has_recent)
        recent_series = _recent_series(skills_set, rb, rw)

        # Financial + training, each resolved the same way: the player's own
        # override wins outright, else what the module says, else None for
        # "unknown" — which the board shows as no badge rather than guessing.
        if p.is_financial_override is not None:
            financial = bool(p.is_financial_override)
        elif owing_ids is not None:
            financial = pid not in owing_ids
        else:
            financial = None
        if p.trained_override is not None:
            trained = bool(p.trained_override)
        elif trained_ids is not None:
            trained = pid in trained_ids
        else:
            trained = None

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
            "gender": p.gender,
            # Age, never the date of birth, and None unless the club has
            # turned it on (and this player is inside whatever age it
            # restricted the display to) — see services/player_age.py. The
            # case it was built for is bowling workload: a selector needs to
            # know the quick they are about to bowl into the ground is 14.
            "age": player_age.visible_age(p.date_of_birth, club),
            "is_dormant": dormant and not manual_inactive,
            "is_inactive": manual_inactive,
            "is_current": not manual_inactive and not dormant,
            "selected": pid in lineup,
            "clash": clash.get(pid, []),
            "clash_detail": clash_detail.get(pid, []),
            "clash_blocks": _clash_blocks(fx_team_seq, clash_seqs.get(pid, [])),
            "squad_match": squad_match,
            "tier": tier,
            "gender_ok": gender_ok,
            "recent_ok": recent_ok,
            "score": round(score, 2),
            "form": form_word,
            "recent": recent_series,
            # True = paid up, False = owes the club money, None = unknown.
            # Deliberately NOT folded into autofill_eligible: whether an
            # unpaid player can be picked is a club's own call, and plenty
            # would rather see the flag and decide than have autofill quietly
            # leave someone out.
            "is_financial": financial,
            "financial_source": (
                "override" if p.is_financial_override is not None
                else "fees" if owing_ids is not None else None
            ),
            # True = at nets inside the last TRAINING_WINDOW_DAYS, False = not,
            # None = the club records no sessions so we cannot say.
            "trained_recently": trained,
            "training_source": (
                "override" if p.trained_override is not None
                else "nets" if trained_ids is not None else None
            ),
            "autofill_eligible": bool(tier in (1, 2, 3) and recent_ok and gender_ok and not manual_inactive),
        })

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
            "grade_id": str(fx.grade_id) if fx.grade_id else None,
            "team_name": fx_team_name,
            "grade_name": fx_grade_name,
            "team_sequence": fx_team_seq,
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
        # What the two flags above could actually be answered from, so the
        # board can label the filter honestly ("from BetterFees" vs "set by
        # hand") and hide a filter nothing can answer.
        "flags": {
            "financial": "fees" if owing_ids is not None else None,
            "training": "nets" if trained_ids is not None else None,
            "training_window_days": TRAINING_WINDOW_DAYS,
        },
        "dormancy_months": months,
        "default_team_size": club.default_team_size if club.default_team_size is not None else 11,
    }
