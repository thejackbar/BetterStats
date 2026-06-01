"""BetterIQ — analytics + AI module (Best tier).

Phase 1 is **Opposition analysis**: scout an upcoming opponent from the data the
Core already holds. Everything here is a *read* over existing tables — no new
ingestion (per the BetterIQ spec). The build order across the module is
opposition → selection → player trends → NL Q&A; only opposition ships here.

Data reality (and why coverage is tiered)
------------------------------------------
We only store **our own club's** per-innings rows (``batting_innings`` etc. FK
to our ``players``). We do *not* store opposition batting cards — see the
``bowler_wickets`` model comment. So what we can say about an opponent depends
on what we hold:

* **Always** — head-to-head results vs us (``games.result`` / ``winning_team``)
  and *our* players' record against them (great selection context too).
* **Partial** — opponent batters our bowlers have dismissed, with the runs they
  made (``bowler_wickets.batter_name`` + ``batter_runs``). A "batters to watch"
  signal, not a full record (not-outs and un-dismissed knocks are invisible).
* **Rich** — only when the opponent club is *itself* a synced organisation we
  hold (multi-club, or a derby where both clubs synced): then we can show their
  real top run-scorers / wicket-takers from their own season stats.

The UI flags the coverage level rather than failing (spec: "flag coverage gaps
in the UI rather than failing").

Opponent identity follows the established ``opp_key`` pattern from
``aggregations.get_player_by_opposition``: ``COALESCE(opp_org_id,
opp_club_name)`` — a stable org UUID when sync populated it, else the club name.
Org-scoping of games goes through ``grades → seasons`` (the views don't carry
``organisation_id``), matching ``routers/records.py``.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# The opponent key + display name for a game, from our club's perspective.
# Used in several queries below, so defined once.
_OPP_KEY = "COALESCE(g.opp_org_id, g.opp_club_name)"

# Standard org-scoping join for the effective games view (records.py pattern).
_ORG_SCOPE = (
    " JOIN grades gr ON gr.id = g.grade_id"
    " JOIN seasons s ON s.id = gr.season_id"
)


async def _held_org_keys(session: AsyncSession) -> set[str]:
    """Org ids + playhq_ids of organisations we hold that have players.

    An opponent whose ``opp_key`` is in this set has been synced as its own
    club, so we can show its real roster ("rich" coverage).
    """
    res = await session.execute(
        text(
            """
            SELECT o.id::text AS id, o.playhq_id AS playhq_id
            FROM organisations o
            WHERE EXISTS (SELECT 1 FROM players pl WHERE pl.organisation_id = o.id)
            """
        )
    )
    keys: set[str] = set()
    for r in res.mappings():
        if r["id"]:
            keys.add(r["id"])
        if r["playhq_id"]:
            keys.add(r["playhq_id"])
    return keys


async def list_opponents(session: AsyncSession, org_id: str) -> dict:
    """Opponents we have history against + upcoming fixtures to scout.

    Returns ``{opponents: [...], upcoming: [...]}``. ``opponents`` is ordered by
    most-played; each carries a ``coverage`` flag ('rich' | 'limited'). Upcoming
    fixtures (from BetterSelect's ``fixtures`` table) get an ``opp_key`` resolved
    by name so the UI can link "scout this opponent" straight to a report.
    """
    res = await session.execute(
        text(
            f"""
            SELECT
                {_OPP_KEY} AS opp_key,
                MAX(g.opp_club_name) AS name,
                COUNT(*) AS meetings,
                MAX(g.played_at) AS last_played
            FROM v_effective_games g{_ORG_SCOPE}
            WHERE s.organisation_id = CAST(:org_id AS UUID)
              AND g.opp_club_name IS NOT NULL AND g.opp_club_name <> ''
            GROUP BY {_OPP_KEY}
            ORDER BY COUNT(*) DESC, MAX(g.played_at) DESC NULLS LAST
            """
        ),
        {"org_id": org_id},
    )
    held = await _held_org_keys(session)
    opponents = []
    for r in res.mappings():
        opp_key = r["opp_key"]
        opponents.append(
            {
                "opp_key": opp_key,
                "name": r["name"],
                "meetings": r["meetings"],
                "last_played": r["last_played"].isoformat() if r["last_played"] else None,
                "coverage": "rich" if opp_key in held else "limited",
            }
        )

    # Name → opp_key lookup so upcoming fixtures can deep-link to a report.
    by_name = {(o["name"] or "").strip().lower(): o["opp_key"] for o in opponents}

    fx_res = await session.execute(
        text(
            """
            SELECT
                f.id::text AS id,
                f.opponent_name,
                f.played_on,
                f.home_away,
                f.venue,
                gr.name AS grade_name,
                t.name AS team_name
            FROM fixtures f
            LEFT JOIN grades gr ON gr.id = f.grade_id
            LEFT JOIN teams t ON t.id = f.team_id
            WHERE f.organisation_id = CAST(:org_id AS UUID)
              AND f.status = 'UPCOMING'
              AND (f.played_on IS NULL OR f.played_on >= CURRENT_DATE)
              AND f.opponent_name IS NOT NULL AND f.opponent_name <> ''
            ORDER BY f.played_on ASC NULLS LAST, f.start_time ASC NULLS LAST
            LIMIT 12
            """
        ),
        {"org_id": org_id},
    )
    upcoming = []
    for r in fx_res.mappings():
        nm = (r["opponent_name"] or "").strip().lower()
        upcoming.append(
            {
                "fixture_id": r["id"],
                "opponent_name": r["opponent_name"],
                "opp_key": by_name.get(nm),  # None when we have no history vs them
                "played_on": r["played_on"].isoformat() if r["played_on"] else None,
                "home_away": r["home_away"],
                "venue": r["venue"],
                "grade_name": r["grade_name"],
                "team_name": r["team_name"],
            }
        )

    return {"opponents": opponents, "upcoming": upcoming}


async def _resolve_opp_key(session: AsyncSession, org_id: str, *, opponent: str | None, fixture_id: str | None) -> tuple[str | None, str | None]:
    """Resolve a request into (opp_key, display_name).

    Accepts an explicit ``opponent`` (already an opp_key) and/or a ``fixture_id``
    whose opponent name we look up against our game history. An explicit
    ``opponent`` **takes precedence** — the "match this opponent" UI passes both a
    chosen opp_key and the fixture, and we want identity from the chosen club
    (the fixture is only used for its grade, resolved separately). Returns
    ``(None, name)`` when a fixture names an opponent we've never played (so the
    caller can show an honest "no history" report).
    """
    if opponent:
        # Confirm the opp_key exists in our history and fetch its display name.
        nm_res = await session.execute(
            text(
                f"""
                SELECT MAX(g.opp_club_name) AS name
                FROM v_effective_games g{_ORG_SCOPE}
                WHERE s.organisation_id = CAST(:org_id AS UUID)
                  AND {_OPP_KEY} = :opp_key
                """
            ),
            {"org_id": org_id, "opp_key": opponent},
        )
        nrow = nm_res.mappings().first()
        return opponent, (nrow["name"] if nrow else None) or opponent

    if fixture_id:
        fx = await session.execute(
            text(
                "SELECT opponent_name FROM fixtures"
                " WHERE id = CAST(:fid AS UUID) AND organisation_id = CAST(:org_id AS UUID)"
            ),
            {"fid": fixture_id, "org_id": org_id},
        )
        row = fx.mappings().first()
        name = (row["opponent_name"] if row else None) or None
        if not name:
            return None, None
        # Map the fixture's opponent name onto a stable opp_key from history.
        key_res = await session.execute(
            text(
                f"""
                SELECT {_OPP_KEY} AS opp_key, MAX(g.opp_club_name) AS name
                FROM v_effective_games g{_ORG_SCOPE}
                WHERE s.organisation_id = CAST(:org_id AS UUID)
                  AND LOWER(g.opp_club_name) = LOWER(:name)
                GROUP BY {_OPP_KEY}
                ORDER BY COUNT(*) DESC
                LIMIT 1
                """
            ),
            {"org_id": org_id, "name": name},
        )
        krow = key_res.mappings().first()
        if krow:
            return krow["opp_key"], krow["name"]
        return None, name  # named opponent, but no history held

    return None, None


async def resolve_opponent(
    session: AsyncSession,
    org_id: str,
    *,
    opponent: str | None = None,
    fixture_id: str | None = None,
) -> tuple[str | None, str | None, str | None]:
    """Public resolver → (opp_key, display_name, grade_id).

    Wraps ``_resolve_opp_key`` and additionally surfaces the fixture's grade_id
    (so the live dossier knows which league-wide grade to scout for current
    form). grade_id is None when resolving from an explicit opponent key.
    """
    opp_key, name = await _resolve_opp_key(session, org_id, opponent=opponent, fixture_id=fixture_id)
    grade_id = None
    if fixture_id:
        res = await session.execute(
            text(
                "SELECT grade_id::text AS gid FROM fixtures"
                " WHERE id = CAST(:fid AS UUID) AND organisation_id = CAST(:org AS UUID)"
            ),
            {"fid": fixture_id, "org": org_id},
        )
        row = res.mappings().first()
        grade_id = row["gid"] if row else None
    return opp_key, name, grade_id


async def _head_to_head(session: AsyncSession, org_id: str, opp_key: str) -> dict:
    """Our overall record vs an opponent + home/away split + recent meetings.

    ``our_venue`` is derived from the known opponent name against the game's
    home/away club — no need to know our own (multi-team) names. Manual games
    have NULL home/away club, so their venue reads as unknown.
    """
    summary = await session.execute(
        text(
            f"""
            SELECT
                COUNT(*) FILTER (WHERE g.result IS NOT NULL) AS decided,
                COUNT(*) AS meetings,
                COUNT(*) FILTER (WHERE g.result = 'WIN') AS wins,
                COUNT(*) FILTER (WHERE g.result = 'LOSS') AS losses,
                COUNT(*) FILTER (WHERE g.result = 'DRAW') AS draws,
                COUNT(*) FILTER (WHERE g.result = 'TIE') AS ties,
                COUNT(*) FILTER (WHERE g.result = 'WIN' AND g.away_club = g.opp_club_name) AS home_wins,
                COUNT(*) FILTER (WHERE g.result IS NOT NULL AND g.away_club = g.opp_club_name) AS home_decided,
                COUNT(*) FILTER (WHERE g.result = 'WIN' AND g.home_club = g.opp_club_name) AS away_wins,
                COUNT(*) FILTER (WHERE g.result IS NOT NULL AND g.home_club = g.opp_club_name) AS away_decided
            FROM v_effective_games g{_ORG_SCOPE}
            WHERE s.organisation_id = CAST(:org_id AS UUID)
              AND {_OPP_KEY} = :opp_key
            """
        ),
        {"org_id": org_id, "opp_key": opp_key},
    )
    s = summary.mappings().first() or {}
    wins, losses = (s.get("wins") or 0), (s.get("losses") or 0)
    decided = s.get("decided") or 0

    recent_res = await session.execute(
        text(
            f"""
            SELECT
                g.played_at,
                g.result,
                g.winning_team,
                g.venue,
                gr.name AS grade_name,
                CASE
                    WHEN g.away_club = g.opp_club_name THEN 'HOME'
                    WHEN g.home_club = g.opp_club_name THEN 'AWAY'
                    ELSE NULL
                END AS our_venue
            FROM v_effective_games g{_ORG_SCOPE}
            WHERE s.organisation_id = CAST(:org_id AS UUID)
              AND {_OPP_KEY} = :opp_key
              AND g.played_at IS NOT NULL
            ORDER BY g.played_at DESC
            LIMIT 12
            """
        ),
        {"org_id": org_id, "opp_key": opp_key},
    )
    recent = [
        {
            "played_at": r["played_at"].isoformat() if r["played_at"] else None,
            "result": r["result"],
            "winning_team": r["winning_team"],
            "venue": r["venue"],
            "grade_name": r["grade_name"],
            "our_venue": r["our_venue"],
        }
        for r in recent_res.mappings()
    ]

    # "Recent form" = our last-5 decided results vs them, newest first (W/L/D).
    form = [r["result"][0] for r in recent if r["result"]][:5]

    return {
        "meetings": s.get("meetings") or 0,
        "decided": decided,
        "wins": wins,
        "losses": losses,
        "draws": s.get("draws") or 0,
        "ties": s.get("ties") or 0,
        "win_pct": round(100.0 * wins / (wins + losses), 1) if (wins + losses) else None,
        "home": {"played": s.get("home_decided") or 0, "wins": s.get("home_wins") or 0},
        "away": {"played": s.get("away_decided") or 0, "wins": s.get("away_wins") or 0},
        "recent": recent,
        "recent_form": form,
    }


async def _our_performers_vs(session: AsyncSession, org_id: str, opp_key: str) -> dict:
    """Our players' batting + bowling record against this opponent.

    Doubles as selection intel — who in our squad has historically enjoyed this
    match-up. Restricted to currently-active players so retired names don't crowd
    the list, ordered by output.
    """
    batting = await session.execute(
        text(
            f"""
            SELECT
                p.id::text AS id,
                COALESCE(p.display_name_override, p.name) AS name,
                p.status AS status,
                COUNT(*) FILTER (WHERE bi.did_not_bat IS NOT TRUE AND bi.runs IS NOT NULL) AS innings,
                COALESCE(SUM(bi.runs) FILTER (WHERE bi.did_not_bat IS NOT TRUE), 0) AS runs,
                MAX(bi.runs) FILTER (WHERE bi.did_not_bat IS NOT TRUE) AS high_score,
                COUNT(*) FILTER (
                    WHERE bi.did_not_bat IS NOT TRUE AND NOT bi.not_out AND bi.dismissal_type IS NOT NULL
                ) AS dismissals
            FROM v_effective_batting_innings bi
            JOIN v_effective_games g ON g.id = bi.game_id{_ORG_SCOPE}
            JOIN players p ON p.id = bi.player_id
            WHERE s.organisation_id = CAST(:org_id AS UUID)
              AND {_OPP_KEY} = :opp_key
            GROUP BY p.id, name, p.status
            HAVING COALESCE(SUM(bi.runs) FILTER (WHERE bi.did_not_bat IS NOT TRUE), 0) > 0
            ORDER BY runs DESC
            LIMIT 10
            """
        ),
        {"org_id": org_id, "opp_key": opp_key},
    )
    top_batting = []
    for r in batting.mappings():
        dis = r["dismissals"] or 0
        runs = r["runs"] or 0
        top_batting.append(
            {
                "player_id": r["id"],
                "name": r["name"],
                "active": r["status"] == "active",
                "innings": r["innings"] or 0,
                "runs": runs,
                "high_score": r["high_score"],
                "average": round(runs / dis, 2) if dis else None,
            }
        )

    bowling = await session.execute(
        text(
            f"""
            SELECT
                p.id::text AS id,
                COALESCE(p.display_name_override, p.name) AS name,
                p.status AS status,
                COALESCE(SUM(bs.wickets), 0) AS wickets,
                COALESCE(SUM(bs.runs), 0) AS runs,
                COALESCE(SUM(bs.overs), 0) AS overs,
                MAX(bs.wickets) AS best_wkts
            FROM v_effective_bowling_spells bs
            JOIN v_effective_games g ON g.id = bs.game_id{_ORG_SCOPE}
            JOIN players p ON p.id = bs.player_id
            WHERE s.organisation_id = CAST(:org_id AS UUID)
              AND {_OPP_KEY} = :opp_key
            GROUP BY p.id, name, p.status
            HAVING COALESCE(SUM(bs.wickets), 0) > 0
            ORDER BY wickets DESC, runs ASC
            LIMIT 10
            """
        ),
        {"org_id": org_id, "opp_key": opp_key},
    )
    top_bowling = []
    for r in bowling.mappings():
        wkts = r["wickets"] or 0
        runs = r["runs"] or 0
        overs = float(r["overs"] or 0)
        top_bowling.append(
            {
                "player_id": r["id"],
                "name": r["name"],
                "active": r["status"] == "active",
                "wickets": wkts,
                "runs": runs,
                "average": round(runs / wkts, 2) if wkts else None,
                "economy": round(runs / overs, 2) if overs else None,
                "best_wickets": r["best_wkts"],
            }
        )

    return {"batting": top_batting, "bowling": top_bowling}


async def _their_danger_batters(session: AsyncSession, org_id: str, opp_key: str) -> list[dict]:
    """Opponent batters our bowlers have dismissed, with the runs they made.

    A *partial* signal (only dismissals BY us; not-outs and knocks we didn't end
    are invisible — we don't store opposition batting). Surfaced as "batters to
    watch", ordered by runs scored against us. Only synced games carry
    ``bowler_wickets`` (manual games have none), which is fine.
    """
    res = await session.execute(
        text(
            f"""
            SELECT
                bw.batter_name AS name,
                COUNT(*) AS times_out,
                COALESCE(SUM(bw.batter_runs), 0) AS runs,
                MAX(bw.batter_runs) AS top_score
            FROM bowler_wickets bw
            JOIN v_effective_games g ON g.id = bw.game_id{_ORG_SCOPE}
            WHERE s.organisation_id = CAST(:org_id AS UUID)
              AND {_OPP_KEY} = :opp_key
              AND bw.batter_name IS NOT NULL AND bw.batter_name <> ''
            GROUP BY bw.batter_name
            HAVING COALESCE(SUM(bw.batter_runs), 0) > 0
            ORDER BY runs DESC, times_out DESC
            LIMIT 15
            """
        ),
        {"org_id": org_id, "opp_key": opp_key},
    )
    return [
        {
            "name": r["name"],
            "times_out": r["times_out"],
            "runs": r["runs"],
            "top_score": r["top_score"],
        }
        for r in res.mappings()
    ]


async def _venues_vs(session: AsyncSession, org_id: str, opp_key: str) -> list[dict]:
    """Our win/loss record at each venue against this opponent."""
    res = await session.execute(
        text(
            f"""
            SELECT g.venue,
                   COUNT(*) FILTER (WHERE g.result IS NOT NULL) AS played,
                   COUNT(*) FILTER (WHERE g.result = 'WIN') AS wins,
                   COUNT(*) FILTER (WHERE g.result = 'LOSS') AS losses
            FROM v_effective_games g{_ORG_SCOPE}
            WHERE s.organisation_id = CAST(:org_id AS UUID)
              AND {_OPP_KEY} = :opp_key
              AND g.venue IS NOT NULL AND g.venue <> ''
            GROUP BY g.venue
            HAVING COUNT(*) FILTER (WHERE g.result IS NOT NULL) >= 2
            ORDER BY played DESC
            LIMIT 8
            """
        ),
        {"org_id": org_id, "opp_key": opp_key},
    )
    return [
        {"venue": r["venue"], "played": r["played"], "wins": r["wins"], "losses": r["losses"]}
        for r in res.mappings()
    ]


async def _matchups_vs(session: AsyncSession, org_id: str, opp_key: str) -> list[dict]:
    """Our-bowler × their-batter dismissal grid (who owns whom), from the wickets
    our bowlers have taken against this opponent. A real match-up edge from held
    data — though it only sees dismissals BY us (not their not-outs)."""
    res = await session.execute(
        text(
            f"""
            SELECT COALESCE(pb.display_name_override, pb.name) AS bowler,
                   bw.batter_name AS batter,
                   COUNT(*) AS dismissals,
                   COALESCE(SUM(bw.batter_runs), 0) AS runs
            FROM bowler_wickets bw
            JOIN v_effective_games g ON g.id = bw.game_id{_ORG_SCOPE}
            JOIN players pb ON pb.id = bw.bowler_id
            WHERE s.organisation_id = CAST(:org_id AS UUID)
              AND {_OPP_KEY} = :opp_key
              AND bw.batter_name IS NOT NULL AND bw.batter_name <> ''
            GROUP BY pb.id, bowler, bw.batter_name
            HAVING COUNT(*) >= 2
            ORDER BY dismissals DESC, runs ASC
            LIMIT 15
            """
        ),
        {"org_id": org_id, "opp_key": opp_key},
    )
    return [
        {"bowler": r["bowler"], "batter": r["batter"], "dismissals": r["dismissals"], "runs": r["runs"]}
        for r in res.mappings()
    ]


async def _their_key_players(session: AsyncSession, opp_org_uuid: str) -> dict:
    """Rich coverage: the opponent's own top run-scorers / wicket-takers.

    Only reachable when the opponent is itself a synced organisation. Aggregates
    their season stats across all seasons.
    """
    batting = await session.execute(
        text(
            """
            SELECT
                COALESCE(p.display_name_override, p.name) AS name,
                COALESCE(SUM(pss.runs), 0) AS runs,
                COALESCE(SUM(pss.batting_innings), 0) AS innings,
                MAX(pss.high_score) AS high_score,
                COALESCE(SUM(pss.hundreds), 0) AS hundreds
            FROM players p
            JOIN player_season_stats pss ON pss.player_id = p.id
            WHERE p.organisation_id = CAST(:oid AS UUID)
            GROUP BY p.id, name
            HAVING COALESCE(SUM(pss.runs), 0) > 0
            ORDER BY runs DESC
            LIMIT 8
            """
        ),
        {"oid": opp_org_uuid},
    )
    bowling = await session.execute(
        text(
            """
            SELECT
                COALESCE(p.display_name_override, p.name) AS name,
                COALESCE(SUM(pss.wickets), 0) AS wickets,
                COALESCE(SUM(pss.runs_conceded), 0) AS runs,
                COALESCE(SUM(pss.bowling_balls), 0) AS balls,
                COALESCE(SUM(pss.five_wicket_innings), 0) AS five_fors
            FROM players p
            JOIN player_season_stats pss ON pss.player_id = p.id
            WHERE p.organisation_id = CAST(:oid AS UUID)
            GROUP BY p.id, name
            HAVING COALESCE(SUM(pss.wickets), 0) > 0
            ORDER BY wickets DESC
            LIMIT 8
            """
        ),
        {"oid": opp_org_uuid},
    )
    top_batting = []
    for r in batting.mappings():
        top_batting.append(
            {
                "name": r["name"],
                "runs": r["runs"],
                "innings": r["innings"],
                "high_score": r["high_score"],
                "hundreds": r["hundreds"],
            }
        )
    top_bowling = []
    for r in bowling.mappings():
        wkts = r["wickets"] or 0
        runs = r["runs"] or 0
        balls = r["balls"] or 0
        top_bowling.append(
            {
                "name": r["name"],
                "wickets": wkts,
                "average": round(runs / wkts, 2) if wkts else None,
                "economy": round(6.0 * runs / balls, 2) if balls else None,
                "five_fors": r["five_fors"],
            }
        )
    return {"batting": top_batting, "bowling": top_bowling}


async def opposition_report(
    session: AsyncSession,
    org_id: str,
    *,
    opponent: str | None = None,
    fixture_id: str | None = None,
) -> dict:
    """Assemble the full opposition scouting report for one opponent.

    Coverage tiers (see module docstring) are reflected in the ``coverage`` block
    so the UI can be honest about what's known.
    """
    opp_key, name = await _resolve_opp_key(session, org_id, opponent=opponent, fixture_id=fixture_id)

    if not opp_key:
        # A named-but-unplayed opponent (e.g. from a fixture) — honest empty state.
        return {
            "opponent": {"opp_key": None, "name": name},
            "coverage": {
                "level": "none",
                "note": (
                    f"No history held against {name}." if name else "Opponent not found."
                )
                + " Head-to-head and player records appear once you've played them"
                " (or once their club is synced).",
            },
            "head_to_head": None,
            "our_performers": None,
            "their_danger_batters": [],
            "their_key_players": None,
            "venues": [],
            "matchups": [],
        }

    head_to_head = await _head_to_head(session, org_id, opp_key)
    our_performers = await _our_performers_vs(session, org_id, opp_key)
    danger = await _their_danger_batters(session, org_id, opp_key)
    venues = await _venues_vs(session, org_id, opp_key)
    matchups = await _matchups_vs(session, org_id, opp_key)

    # Rich coverage only if the opponent is itself a synced org we hold.
    held = await _held_org_keys(session)
    their_key_players = None
    coverage_level = "limited"
    if opp_key in held:
        org_row = await session.execute(
            text(
                "SELECT id::text AS id FROM organisations"
                " WHERE id::text = :k OR playhq_id = :k LIMIT 1"
            ),
            {"k": opp_key},
        )
        orow = org_row.mappings().first()
        if orow:
            their_key_players = await _their_key_players(session, orow["id"])
            coverage_level = "rich"

    if coverage_level == "rich":
        note = (
            f"{name} is synced as its own club, so their full top run-scorers and"
            " wicket-takers are shown below."
        )
    else:
        note = (
            "Limited coverage: we hold our results and our players' record against"
            f" {name}, plus opponent batters we've dismissed. Their full batting/"
            "bowling records aren't available because their club isn't synced."
        )

    return {
        "opponent": {"opp_key": opp_key, "name": name},
        "coverage": {"level": coverage_level, "note": note},
        "head_to_head": head_to_head,
        "our_performers": our_performers,
        "their_danger_batters": danger,
        "their_key_players": their_key_players,
        "venues": venues,
        "matchups": matchups,
    }
