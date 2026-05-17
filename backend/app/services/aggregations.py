from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional
import uuid


async def get_career_batting(session: AsyncSession, player_id: str, season_id: Optional[str] = None) -> Optional[dict]:
    season_clause = " AND pss.season_id = :sid" if season_id else ""
    params: dict = {"pid": player_id}
    if season_id:
        params["sid"] = season_id
    result = await session.execute(
        text(f"""
            SELECT
                p.id AS player_id,
                p.name,
                p.organisation_id,
                COALESCE(SUM(pss.batting_innings), 0) AS innings,
                COALESCE(SUM(pss.runs), 0) AS total_runs,
                MAX(pss.high_score) AS high_score,
                ROUND(SUM(pss.runs)::numeric / NULLIF(SUM(pss.batting_innings) - SUM(pss.not_outs), 0), 2) AS average,
                ROUND(SUM(pss.runs)::numeric / NULLIF(SUM(pss.balls_faced), 0) * 100, 2) AS strike_rate,
                COALESCE(SUM(pss.fifties), 0) AS fifties,
                COALESCE(SUM(pss.hundreds), 0) AS hundreds,
                COALESCE(SUM(pss.fours), 0) AS total_fours,
                COALESCE(SUM(pss.sixes), 0) AS total_sixes,
                COALESCE(SUM(pss.ducks), 0) AS ducks,
                COALESCE(SUM(pss.matches), 0) AS games
            FROM players p
            LEFT JOIN player_season_stats pss ON pss.player_id = p.id{season_clause}
            WHERE p.id = :pid
            GROUP BY p.id, p.name, p.organisation_id
        """),
        params,
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def get_career_bowling(session: AsyncSession, player_id: str, season_id: Optional[str] = None) -> Optional[dict]:
    season_clause = " AND pss.season_id = :sid" if season_id else ""
    params: dict = {"pid": player_id}
    if season_id:
        params["sid"] = season_id
    result = await session.execute(
        text(f"""
            SELECT
                p.id AS player_id,
                p.name,
                p.organisation_id,
                COALESCE(SUM(pss.matches), 0) AS games,
                COALESCE(SUM(pss.wickets), 0) AS total_wickets,
                ROUND(SUM(pss.runs_conceded)::numeric / NULLIF(SUM(pss.wickets), 0), 2) AS average,
                ROUND(SUM(pss.runs_conceded)::numeric / NULLIF(SUM(pss.bowling_balls), 0) * 6, 2) AS economy,
                MAX(pss.best_bowling_wickets) AS best_figures_wickets,
                MAX(pss.best_bowling_figures) AS best_bowling_figures,
                COALESCE(SUM(pss.maidens), 0) AS total_maidens,
                COALESCE(SUM(pss.overs), 0) AS total_overs,
                COALESCE(SUM(pss.runs_conceded), 0) AS total_runs,
                COALESCE(SUM(pss.five_wicket_innings), 0) AS five_fors,
                ROUND(SUM(pss.bowling_balls)::numeric / NULLIF(SUM(pss.wickets), 0), 2) AS bowling_strike_rate
            FROM players p
            LEFT JOIN player_season_stats pss ON pss.player_id = p.id{season_clause}
            WHERE p.id = :pid
            GROUP BY p.id, p.name, p.organisation_id
        """),
        params,
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def get_career_fielding(session: AsyncSession, player_id: str, season_id: Optional[str] = None) -> Optional[dict]:
    season_clause = " AND pss.season_id = :sid" if season_id else ""
    params: dict = {"pid": player_id}
    if season_id:
        params["sid"] = season_id
    result = await session.execute(
        text(f"""
            SELECT
                p.id AS player_id,
                p.name,
                p.organisation_id,
                COALESCE(SUM(pss.matches), 0) AS games,
                COALESCE(SUM(pss.catches), 0) AS total_catches,
                COALESCE(SUM(pss.catches_wk), 0) AS total_catches_wk,
                COALESCE(SUM(pss.catches_non_wk), 0) AS total_catches_non_wk,
                COALESCE(SUM(pss.run_outs), 0) AS total_run_outs,
                COALESCE(SUM(pss.assisted_run_outs), 0) AS total_assisted_run_outs,
                COALESCE(SUM(pss.unassisted_run_outs), 0) AS total_unassisted_run_outs,
                COALESCE(SUM(pss.stumpings), 0) AS total_stumpings,
                COALESCE(SUM(pss.catches + pss.run_outs + pss.stumpings), 0) AS total_dismissals
            FROM players p
            LEFT JOIN player_season_stats pss ON pss.player_id = p.id{season_clause}
            WHERE p.id = :pid
            GROUP BY p.id, p.name, p.organisation_id
        """),
        params,
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def get_batting_leaderboard(
    session: AsyncSession,
    org_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    return await get_batting_leaderboard_extended(session, org_id, season_id, grade_id, "total_runs", limit)


async def get_bowling_leaderboard(
    session: AsyncSession,
    org_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    return await get_bowling_leaderboard_extended(session, org_id, season_id, grade_id, "total_wickets", limit)


async def get_fielding_leaderboard(
    session: AsyncSession,
    org_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
    sort_by: str = "total_dismissals",
    limit: int = 20,
) -> list[dict]:
    ALLOWED_SORTS = {"total_catches", "total_run_outs", "total_stumpings", "total_dismissals", "games"}
    if sort_by not in ALLOWED_SORTS:
        sort_by = "total_dismissals"

    base = """
        SELECT
            p.id AS player_id,
            COALESCE(p.display_name_override, p.name) AS name,
            SUM(pss.matches) AS games,
            SUM(pss.catches) AS total_catches,
            SUM(pss.run_outs) AS total_run_outs,
            SUM(pss.stumpings) AS total_stumpings,
            SUM(pss.catches + pss.run_outs + pss.stumpings) AS total_dismissals
        FROM player_season_stats pss
        JOIN players p ON p.id = pss.player_id
        JOIN seasons s ON s.id = pss.season_id
        WHERE p.organisation_id = :org_id
    """
    params: dict = {"org_id": org_id, "limit": limit}
    if season_id:
        base += " AND pss.season_id = :season_id"
        params["season_id"] = season_id
    base += f" GROUP BY p.id, COALESCE(p.display_name_override, p.name) ORDER BY {sort_by} DESC NULLS LAST LIMIT :limit"

    result = await session.execute(text(base), params)
    return [dict(r) for r in result.mappings()]


async def get_player_batting_innings(
    session: AsyncSession,
    player_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
) -> list[dict]:
    clauses = ["bi.player_id = :pid"]
    params: dict = {"pid": player_id}
    if season_id:
        clauses.append("s.id = :sid")
        params["sid"] = season_id
    if grade_id:
        clauses.append("gr.id = :gid")
        params["gid"] = grade_id
    where = " AND ".join(clauses)
    result = await session.execute(
        text(f"""
            SELECT
                bi.runs,
                bi.balls,
                bi.fours,
                bi.sixes,
                bi.strike_rate,
                bi.dismissal_type,
                bi.not_out,
                bi.batting_position,
                bi.innings_number,
                g.id::text AS game_id,
                g.home_team,
                g.away_team,
                g.played_at::text,
                g.result,
                gr.name AS grade_name,
                s.name AS season_name,
                s.year AS season_year
            FROM batting_innings bi
            JOIN games g ON g.id = bi.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE {where}
            ORDER BY g.played_at DESC
        """),
        params,
    )
    return [dict(r) for r in result.mappings()]


async def get_player_bowling_spells(
    session: AsyncSession,
    player_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
) -> list[dict]:
    clauses = ["bs.player_id = :pid"]
    params: dict = {"pid": player_id}
    if season_id:
        clauses.append("s.id = :sid")
        params["sid"] = season_id
    if grade_id:
        clauses.append("gr.id = :gid")
        params["gid"] = grade_id
    where = " AND ".join(clauses)
    result = await session.execute(
        text(f"""
            SELECT
                bs.overs,
                bs.maidens,
                bs.runs,
                bs.wickets,
                bs.wides,
                bs.no_balls,
                bs.economy,
                bs.innings_number,
                g.id::text AS game_id,
                g.home_team,
                g.away_team,
                g.played_at::text,
                g.result,
                gr.name AS grade_name,
                s.name AS season_name,
                s.year AS season_year
            FROM bowling_spells bs
            JOIN games g ON g.id = bs.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE {where}
            ORDER BY g.played_at DESC
        """),
        params,
    )
    return [dict(r) for r in result.mappings()]


async def get_dismissal_breakdown(session: AsyncSession, player_id: str) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT
                CASE
                    WHEN bi.not_out THEN 'not out'
                    WHEN bi.dismissal_type IS NULL THEN 'unknown'
                    WHEN bi.dismissal_type = 'b' OR bi.dismissal_type LIKE 'b %' THEN 'bowled'
                    WHEN bi.dismissal_type = 'c' OR bi.dismissal_type LIKE 'c %' THEN 'caught'
                    WHEN bi.dismissal_type = 'lbw' OR bi.dismissal_type LIKE 'lbw %'
                         OR bi.dismissal_type = 'leg before wicket'
                         OR bi.dismissal_type LIKE 'leg before wicket%' THEN 'lbw'
                    WHEN bi.dismissal_type = 'st' OR bi.dismissal_type LIKE 'st %' THEN 'stumped'
                    WHEN bi.dismissal_type LIKE 'run out%' THEN 'run out'
                    WHEN bi.dismissal_type = 'hit wicket' OR bi.dismissal_type LIKE 'hit wicket%' THEN 'hit wicket'
                    WHEN bi.dismissal_type LIKE 'ret%' THEN 'retired'
                    ELSE bi.dismissal_type
                END AS dismissal_type,
                COUNT(*) AS count
            FROM batting_innings bi
            WHERE bi.player_id = :pid
              AND bi.runs IS NOT NULL
            GROUP BY 1
            ORDER BY COUNT(*) DESC
        """),
        {"pid": player_id},
    )
    return [dict(r) for r in result.mappings()]


async def get_batting_by_position(session: AsyncSession, player_id: str) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT
                bi.batting_position,
                COUNT(*) AS innings,
                SUM(bi.runs) AS runs,
                ROUND(
                    SUM(bi.runs)::numeric /
                    NULLIF(COUNT(*) FILTER (WHERE NOT bi.not_out AND bi.dismissal_type IS NOT NULL), 0),
                    2
                ) AS average,
                MAX(bi.runs) AS high_score,
                ROUND(AVG(bi.strike_rate), 1) AS avg_strike_rate
            FROM batting_innings bi
            WHERE bi.player_id = :pid
              AND bi.batting_position IS NOT NULL
              AND bi.runs IS NOT NULL
            GROUP BY bi.batting_position
            ORDER BY bi.batting_position
        """),
        {"pid": player_id},
    )
    return [dict(r) for r in result.mappings()]


async def get_batting_by_grade(session: AsyncSession, player_id: str, org_id: Optional[str] = None) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT
                COALESCE(am.canonical_name, gr.name) AS grade_name,
                COUNT(*) AS innings,
                SUM(bi.runs) AS runs,
                ROUND(
                    SUM(bi.runs)::numeric /
                    NULLIF(COUNT(*) FILTER (WHERE NOT bi.not_out AND bi.dismissal_type IS NOT NULL), 0),
                    2
                ) AS average,
                MAX(bi.runs) AS high_score
            FROM batting_innings bi
            JOIN games g ON g.id = bi.game_id
            JOIN grades gr ON gr.id = g.grade_id
            LEFT JOIN LATERAL (
                SELECT canonical_name FROM grade_merge_logs gml
                WHERE gml.org_id = CAST(:org_id AS UUID)
                  AND gml.alias_name = gr.name
                  AND gml.undone_at IS NULL
                LIMIT 1
            ) am ON TRUE
            WHERE bi.player_id = :pid
              AND bi.runs IS NOT NULL
            GROUP BY COALESCE(am.canonical_name, gr.name)
            ORDER BY SUM(bi.runs) DESC
        """),
        {"pid": player_id, "org_id": org_id},
    )
    return [dict(r) for r in result.mappings()]


async def get_season_by_season(session: AsyncSession, player_id: str) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT
                s.id AS season_id,
                s.name AS season_name,
                s.year,
                pss.matches,
                pss.batting_innings,
                pss.runs AS total_runs,
                pss.high_score,
                pss.batting_average,
                pss.batting_strike_rate AS strike_rate,
                pss.fifties,
                pss.hundreds,
                pss.not_outs,
                pss.ducks,
                pss.fours AS total_fours,
                pss.sixes AS total_sixes,
                pss.wickets AS total_wickets,
                pss.runs_conceded AS bowling_runs_conceded,
                pss.overs AS total_overs,
                pss.bowling_average,
                pss.bowling_economy AS economy,
                pss.best_bowling_wickets,
                pss.best_bowling_figures,
                pss.five_wicket_innings AS five_fors,
                pss.maidens AS total_maidens,
                pss.catches AS total_catches,
                pss.catches_wk AS total_catches_wk,
                pss.run_outs AS total_run_outs,
                pss.stumpings AS total_stumpings
            FROM player_season_stats pss
            JOIN seasons s ON s.id = pss.season_id
            WHERE pss.player_id = :pid
            ORDER BY s.year DESC NULLS LAST, s.name
        """),
        {"pid": player_id}
    )
    return [dict(r) for r in result.mappings()]


async def get_player_milestones(session: AsyncSession, player_id: str) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT
                m.id, m.milestone_type, m.milestone_value, m.achieved_at, m.detail,
                m.game_id
            FROM milestones m
            WHERE m.player_id = :pid
            ORDER BY
                CASE m.milestone_type
                    WHEN 'runs' THEN 1
                    WHEN 'wickets' THEN 2
                    WHEN 'matches' THEN 3
                    WHEN 'catches' THEN 4
                    ELSE 5
                END,
                m.milestone_value DESC
        """),
        {"pid": player_id}
    )
    return [dict(r) for r in result.mappings()]


async def get_player_partnerships(session: AsyncSession, player_id: str) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT
                CASE WHEN pt.batter1_id = :pid THEN pt.batter2_id::text ELSE pt.batter1_id::text END AS partner_id,
                CASE WHEN pt.batter1_id = :pid
                     THEN COALESCE(p2.display_name_override, p2.name)
                     ELSE COALESCE(p1.display_name_override, p1.name)
                END AS partner_name,
                COUNT(*) AS partnership_count,
                COALESCE(SUM(pt.runs), 0) AS total_runs,
                MAX(pt.runs) AS best_runs,
                MAX(g.played_at)::text AS last_played
            FROM partnerships pt
            JOIN games g ON g.id = pt.game_id
            LEFT JOIN players p1 ON p1.id = pt.batter1_id
            LEFT JOIN players p2 ON p2.id = pt.batter2_id
            WHERE (pt.batter1_id = :pid OR pt.batter2_id = :pid)
              AND pt.runs IS NOT NULL AND pt.runs > 0
            GROUP BY
                CASE WHEN pt.batter1_id = :pid THEN pt.batter2_id::text ELSE pt.batter1_id::text END,
                CASE WHEN pt.batter1_id = :pid
                     THEN COALESCE(p2.display_name_override, p2.name)
                     ELSE COALESCE(p1.display_name_override, p1.name)
                END
            ORDER BY total_runs DESC
            LIMIT 20
        """),
        {"pid": player_id},
    )
    return [dict(r) for r in result.mappings()]


async def get_game_fall_of_wickets(session: AsyncSession, game_id: str) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT
                fow.wicket_number,
                fow.innings_number,
                fow.score_at_fall,
                fow.overs_at_fall,
                p.name AS player_name,
                fow.player_id::text
            FROM fall_of_wickets fow
            LEFT JOIN players p ON p.id = fow.player_id
            WHERE fow.game_id = :gid
            ORDER BY fow.innings_number, fow.wicket_number
        """),
        {"gid": game_id},
    )
    return [dict(r) for r in result.mappings()]


async def get_upcoming_milestones_for_org(
    session: AsyncSession,
    org_id: str,
    limit: int = 20,
) -> list[dict]:
    result = await session.execute(
        text("""
            WITH recent_seasons AS (
                SELECT s.id
                FROM seasons s
                JOIN player_season_stats pss ON pss.season_id = s.id
                JOIN players p ON p.id = pss.player_id
                WHERE p.organisation_id = :org_id
                GROUP BY s.id, s.year, s.name
                ORDER BY s.year DESC NULLS LAST, s.name DESC
                LIMIT 3
            ),
            active_players AS (
                SELECT DISTINCT pss.player_id
                FROM player_season_stats pss
                WHERE pss.season_id IN (SELECT id FROM recent_seasons)
            )
            SELECT
                p.id AS player_id,
                p.name,
                COALESCE(SUM(pss.runs), 0) AS career_runs,
                COALESCE(SUM(pss.wickets), 0) AS career_wickets,
                COALESCE(SUM(pss.matches), 0) AS career_matches,
                COALESCE(SUM(pss.catches), 0) AS career_catches
            FROM players p
            LEFT JOIN player_season_stats pss ON pss.player_id = p.id
            WHERE p.organisation_id = :org_id
              AND p.id IN (SELECT player_id FROM active_players)
            GROUP BY p.id, p.name
            HAVING COALESCE(SUM(pss.runs), 0) > 0 OR COALESCE(SUM(pss.wickets), 0) > 0
        """),
        {"org_id": org_id}
    )
    rows = [dict(r) for r in result.mappings()]

    RUN_MILESTONES = [
        50, 100, 250, 500, 750, 1000, 1500, 2000, 3000, 4000, 5000,
        6000, 7000, 8000, 9000, 10000, 12500, 15000, 17500, 20000,
        25000, 30000, 35000, 40000, 45000, 50000,
    ]
    WICKET_MILESTONES = [
        10, 25, 50, 75, 100, 150, 200, 250, 300, 400, 500,
        600, 700, 800, 900, 1000, 1500, 2000, 2500, 3000, 4000, 5000,
    ]
    MATCH_MILESTONES = [10, 25, 50, 100, 150, 200, 250, 300, 400, 500, 750, 1000]
    CATCH_MILESTONES = [10, 25, 50, 100, 150, 200, 300, 400, 500, 750, 1000, 1500, 2000]

    def next_milestone(current, milestones):
        for m in milestones:
            if current < m:
                return m
        return None

    # Score formula: milestone_value² / needed
    # Heavily weights milestone size so 500-from-9000 beats 1-from-100
    def importance_score(target, needed):
        return (target ** 2) / (needed + 1)

    upcoming = []
    for row in rows:
        runs = int(row["career_runs"] or 0)
        wickets = int(row["career_wickets"] or 0)
        matches = int(row["career_matches"] or 0)
        catches = int(row["career_catches"] or 0)
        player_id = str(row["player_id"])
        name = row["name"]

        CATEGORY_MAP = {
            "runs": "batting",
            "wickets": "bowling",
            "matches": "matches",
            "catches": "fielding",
        }
        for stat, current, milestones in [
            ("runs", runs, RUN_MILESTONES),
            ("wickets", wickets, WICKET_MILESTONES),
            ("matches", matches, MATCH_MILESTONES),
            ("catches", catches, CATCH_MILESTONES),
        ]:
            target = next_milestone(current, milestones)
            if target is None:
                continue
            needed = target - current
            upcoming.append({
                "player_id": player_id,
                "name": name,
                "type": stat,
                "category": CATEGORY_MAP[stat],
                "current": current,
                "target": target,
                "needed": needed,
                "score": importance_score(target, needed),
            })

    upcoming.sort(key=lambda x: x["score"], reverse=True)

    # Return top 50 per category — frontend handles pagination
    per_cat = 50
    counts: dict = {}
    result = []
    for item in upcoming:
        cat = item["category"]
        if counts.get(cat, 0) < per_cat:
            result.append(item)
            counts[cat] = counts.get(cat, 0) + 1
    return result


async def get_recently_achieved_milestones_for_org(
    session: AsyncSession,
    org_id: str,
) -> list[dict]:
    # Fetch the 3 most recent non-Winter seasons, returned oldest-first so we can
    # simulate cumulative totals season-by-season to pinpoint when each milestone crossed.
    seasons_result = await session.execute(
        text("""
            SELECT sub.id, sub.year, sub.name
            FROM (
                SELECT s.id, s.year, s.name
                FROM seasons s
                JOIN player_season_stats pss ON pss.season_id = s.id
                JOIN players p ON p.id = pss.player_id
                WHERE p.organisation_id = :org_id
                  AND s.name NOT ILIKE '%winter%'
                GROUP BY s.id, s.year, s.name
                ORDER BY s.year DESC NULLS LAST, s.name DESC
                LIMIT 3
            ) sub
            ORDER BY sub.year ASC NULLS LAST, sub.name ASC
        """),
        {"org_id": org_id}
    )
    recent_seasons = [dict(r) for r in seasons_result.mappings()]
    if not recent_seasons:
        return []

    # Safe to interpolate — IDs are UUIDs from our own DB query
    sid_list = ", ".join(f"'{s['id']}'" for s in recent_seasons)

    # Fetch recorded milestone dates for active players (set by sync when first detected)
    dates_result = await session.execute(
        text(f"""
            SELECT player_id, milestone_type, milestone_value, achieved_at
            FROM milestones
            WHERE player_id IN (
                SELECT DISTINCT pss.player_id FROM player_season_stats pss
                WHERE pss.season_id IN ({sid_list})
            ) AND achieved_at IS NOT NULL
        """)
    )
    milestone_date_map = {
        (str(r["player_id"]), r["milestone_type"], int(r["milestone_value"])): r["achieved_at"]
        for r in dates_result.mappings()
    }

    data_result = await session.execute(
        text(f"""
            WITH active_players AS (
                SELECT DISTINCT pss.player_id
                FROM player_season_stats pss
                WHERE pss.season_id IN ({sid_list})
            ),
            prior_totals AS (
                SELECT
                    p.id AS player_id,
                    p.name,
                    COALESCE(SUM(pss.runs), 0) AS prior_runs,
                    COALESCE(SUM(pss.wickets), 0) AS prior_wickets,
                    COALESCE(SUM(pss.matches), 0) AS prior_matches,
                    COALESCE(SUM(pss.catches), 0) AS prior_catches
                FROM players p
                LEFT JOIN player_season_stats pss ON pss.player_id = p.id
                    AND pss.season_id NOT IN ({sid_list})
                WHERE p.organisation_id = :org_id
                  AND p.id IN (SELECT player_id FROM active_players)
                GROUP BY p.id, p.name
            )
            SELECT
                pt.player_id,
                pt.name,
                pt.prior_runs, pt.prior_wickets, pt.prior_matches, pt.prior_catches,
                pss.season_id,
                COALESCE(pss.runs, 0) AS season_runs,
                COALESCE(pss.wickets, 0) AS season_wickets,
                COALESCE(pss.matches, 0) AS season_matches,
                COALESCE(pss.catches, 0) AS season_catches
            FROM prior_totals pt
            LEFT JOIN player_season_stats pss ON pss.player_id = pt.player_id
                AND pss.season_id IN ({sid_list})
        """),
        {"org_id": org_id}
    )
    rows = [dict(r) for r in data_result.mappings()]

    # Group per-season stats by player
    player_data: dict = {}
    for row in rows:
        pid = str(row["player_id"])
        if pid not in player_data:
            player_data[pid] = {
                "name": row["name"],
                "prior": {
                    "runs": int(row["prior_runs"] or 0),
                    "wickets": int(row["prior_wickets"] or 0),
                    "matches": int(row["prior_matches"] or 0),
                    "catches": int(row["prior_catches"] or 0),
                },
                "seasons": {},
            }
        if row["season_id"]:
            player_data[pid]["seasons"][str(row["season_id"])] = {
                "runs": int(row["season_runs"] or 0),
                "wickets": int(row["season_wickets"] or 0),
                "matches": int(row["season_matches"] or 0),
                "catches": int(row["season_catches"] or 0),
            }

    RUN_MILESTONES = [
        50, 100, 250, 500, 750, 1000, 1500, 2000, 3000, 4000, 5000,
        6000, 7000, 8000, 9000, 10000, 12500, 15000, 17500, 20000,
        25000, 30000, 35000, 40000, 45000, 50000,
    ]
    WICKET_MILESTONES = [
        10, 25, 50, 75, 100, 150, 200, 250, 300, 400, 500,
        600, 700, 800, 900, 1000, 1500, 2000, 2500, 3000, 4000, 5000,
    ]
    MATCH_MILESTONES = [10, 25, 50, 100, 150, 200, 250, 300, 400, 500, 750, 1000]
    CATCH_MILESTONES = [10, 25, 50, 100, 150, 200, 300, 400, 500, 750, 1000, 1500, 2000]

    CATEGORY_MAP = {
        "runs": "batting",
        "wickets": "bowling",
        "matches": "matches",
        "catches": "fielding",
    }
    MILESTONE_LISTS = {
        "runs": RUN_MILESTONES,
        "wickets": WICKET_MILESTONES,
        "matches": MATCH_MILESTONES,
        "catches": CATCH_MILESTONES,
    }

    achieved = []
    for pid, pdata in player_data.items():
        # Pre-compute all-time career total for display
        career_total = dict(pdata["prior"])
        for s in recent_seasons:
            ss = pdata["seasons"].get(str(s["id"]), {})
            for stat in career_total:
                career_total[stat] += ss.get(stat, 0)

        # Simulate cumulative totals oldest→newest to find which season each milestone crossed
        running = dict(pdata["prior"])
        for season in recent_seasons:
            ss = pdata["seasons"].get(str(season["id"]), {})
            for stat, milestones in MILESTONE_LISTS.items():
                before = running[stat]
                after = before + ss.get(stat, 0)
                for m in milestones:
                    if before < m <= after:
                        achieved_at = milestone_date_map.get((pid, stat, m))
                        achieved.append({
                            "player_id": pid,
                            "name": pdata["name"],
                            "type": stat,
                            "category": CATEGORY_MAP[stat],
                            "milestone": m,
                            "current": career_total[stat],
                            "season_year": season["year"] or 0,
                            "season_name": season["name"],
                            "achieved_at": achieved_at.isoformat() if achieved_at else None,
                        })
            for stat in running:
                running[stat] += ss.get(stat, 0)

    # Dated entries first (most recent date first), then undated by season year desc
    achieved.sort(key=lambda x: (
        0 if x["achieved_at"] else 1,
        -(int(x["achieved_at"].replace("-", "")) if x["achieved_at"] else 0),
        -x["season_year"],
        -x["milestone"],
    ))
    return achieved


async def get_player_activity(session: AsyncSession, player_id: str) -> dict:
    result = await session.execute(
        text("""
            SELECT
                COALESCE(SUM(pss.matches), 0) AS total_matches,
                COALESCE(SUM(pss.batting_innings), 0) AS total_innings,
                COALESCE(SUM(pss.ducks), 0) AS total_ducks,
                COALESCE(SUM(pss.sixes), 0) AS total_sixes,
                COALESCE(SUM(pss.fours), 0) AS total_fours,
                COALESCE(SUM(pss.wickets), 0) AS total_wickets,
                MAX(pss.best_bowling_wickets) AS best_spell_wickets,
                MAX(pss.best_bowling_figures) AS best_bowling_figures
            FROM player_season_stats pss
            WHERE pss.player_id = :pid
        """),
        {"pid": player_id}
    )
    row = dict(result.mappings().first() or {})
    return {
        "last_game_date": None,
        "last_bat_date": None,
        "last_bowl_date": None,
        "last_wicket_date": None,
        "last_duck_date": None,
        "total_innings": int(row.get("total_innings") or 0),
        "total_ducks": int(row.get("total_ducks") or 0),
        "total_sixes": int(row.get("total_sixes") or 0),
        "total_fours": int(row.get("total_fours") or 0),
        "total_wickets": int(row.get("total_wickets") or 0),
        "best_spell_wickets": int(row.get("best_spell_wickets") or 0),
        "best_bowling_figures": row.get("best_bowling_figures"),
        "wicketless_spells": 0,
    }


async def get_batting_leaderboard_extended(
    session: AsyncSession,
    org_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
    sort_by: str = "total_runs",
    limit: int = 20,
    min_runs: int = 0,
) -> list[dict]:
    ALLOWED_SORTS = {
        "total_runs", "average", "strike_rate", "total_sixes",
        "total_fours", "ducks", "high_score", "fifties", "hundreds", "innings",
    }
    if sort_by not in ALLOWED_SORTS:
        sort_by = "total_runs"

    base = """
        SELECT
            p.id AS player_id,
            COALESCE(p.display_name_override, p.name) AS name,
            SUM(pss.batting_innings) AS innings,
            SUM(pss.runs) AS total_runs,
            MAX(pss.high_score) AS high_score,
            ROUND(SUM(pss.runs)::numeric / NULLIF(SUM(pss.batting_innings) - SUM(pss.not_outs), 0), 2) AS average,
            ROUND(SUM(pss.runs)::numeric / NULLIF(SUM(pss.balls_faced), 0) * 100, 2) AS strike_rate,
            SUM(pss.fifties) AS fifties,
            SUM(pss.hundreds) AS hundreds,
            COALESCE(SUM(pss.sixes), 0) AS total_sixes,
            COALESCE(SUM(pss.fours), 0) AS total_fours,
            SUM(pss.ducks) AS ducks,
            SUM(pss.matches) AS games
        FROM player_season_stats pss
        JOIN players p ON p.id = pss.player_id
        JOIN seasons s ON s.id = pss.season_id
        WHERE p.organisation_id = :org_id
    """
    params: dict = {"org_id": org_id, "limit": limit}
    if season_id:
        base += " AND pss.season_id = :season_id"
        params["season_id"] = season_id
    base += " GROUP BY p.id, COALESCE(p.display_name_override, p.name)"
    if min_runs > 0:
        base += " HAVING SUM(pss.runs) >= :min_runs"
        params["min_runs"] = min_runs
    base += f" ORDER BY {sort_by} DESC NULLS LAST LIMIT :limit"

    result = await session.execute(text(base), params)
    return [dict(r) for r in result.mappings()]


async def get_bowling_leaderboard_extended(
    session: AsyncSession,
    org_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
    sort_by: str = "total_wickets",
    limit: int = 20,
    min_overs: int = 0,
    min_wickets: int = 0,
) -> list[dict]:
    ALLOWED_SORTS = {
        "total_wickets", "average", "economy", "best_figures_wickets",
        "total_maidens", "five_fors",
    }
    if sort_by not in ALLOWED_SORTS:
        sort_by = "total_wickets"

    base = """
        SELECT
            p.id AS player_id,
            COALESCE(p.display_name_override, p.name) AS name,
            SUM(pss.matches) AS games,
            SUM(pss.wickets) AS total_wickets,
            ROUND(SUM(pss.runs_conceded)::numeric / NULLIF(SUM(pss.wickets), 0), 2) AS average,
            ROUND(SUM(pss.runs_conceded)::numeric / NULLIF(SUM(pss.bowling_balls), 0) * 6, 2) AS economy,
            MAX(pss.best_bowling_wickets) AS best_figures_wickets,
            MAX(pss.best_bowling_figures) AS best_bowling_figures,
            SUM(pss.maidens) AS total_maidens,
            SUM(pss.overs) AS total_overs,
            COALESCE(SUM(pss.five_wicket_innings), 0) AS five_fors
        FROM player_season_stats pss
        JOIN players p ON p.id = pss.player_id
        JOIN seasons s ON s.id = pss.season_id
        WHERE p.organisation_id = :org_id
    """
    params: dict = {"org_id": org_id, "limit": limit}
    if season_id:
        base += " AND pss.season_id = :season_id"
        params["season_id"] = season_id
    base += " GROUP BY p.id, COALESCE(p.display_name_override, p.name)"
    having_clauses = []
    if min_overs > 0:
        having_clauses.append("COALESCE(SUM(pss.bowling_balls), 0) / 6.0 >= :min_overs")
        params["min_overs"] = min_overs
    if min_wickets > 0:
        having_clauses.append("SUM(pss.wickets) >= :min_wickets")
        params["min_wickets"] = min_wickets
    if having_clauses:
        base += " HAVING " + " AND ".join(having_clauses)
    sort_dir = "ASC" if sort_by in ("economy", "average") else "DESC"
    base += f" ORDER BY {sort_by} {sort_dir} NULLS LAST LIMIT :limit"

    result = await session.execute(text(base), params)
    return [dict(r) for r in result.mappings()]


async def get_bowling_by_grade(session: AsyncSession, player_id: str, org_id: Optional[str] = None) -> list[dict]:
    result = await session.execute(
        text("""
            WITH grade_spells AS (
                SELECT
                    COALESCE(am.canonical_name, gr.name) AS grade_name,
                    bs.wickets,
                    bs.runs,
                    bs.overs,
                    bs.maidens
                FROM bowling_spells bs
                JOIN games g ON g.id = bs.game_id
                JOIN grades gr ON gr.id = g.grade_id
                LEFT JOIN LATERAL (
                    SELECT canonical_name FROM grade_merge_logs gml
                    WHERE gml.org_id = CAST(:org_id AS UUID)
                      AND gml.alias_name = gr.name
                      AND gml.undone_at IS NULL
                    LIMIT 1
                ) am ON TRUE
                WHERE bs.player_id = :pid
                  AND bs.wickets IS NOT NULL
            ),
            best_per_grade AS (
                SELECT DISTINCT ON (grade_name)
                    grade_name,
                    wickets AS best_wickets,
                    runs AS best_runs
                FROM grade_spells
                ORDER BY grade_name, wickets DESC, runs ASC
            )
            SELECT
                gs.grade_name,
                COUNT(*) AS spells,
                COALESCE(SUM(gs.wickets), 0) AS wickets,
                COALESCE(SUM(gs.runs), 0) AS runs_conceded,
                COALESCE(SUM(gs.overs), 0) AS total_overs,
                COALESCE(SUM(gs.maidens), 0) AS maidens,
                ROUND(SUM(gs.runs)::numeric / NULLIF(SUM(gs.wickets), 0), 2) AS average,
                ROUND(SUM(gs.runs)::numeric / NULLIF(SUM(gs.overs), 0), 2) AS economy,
                bp.best_wickets,
                bp.best_runs
            FROM grade_spells gs
            JOIN best_per_grade bp ON bp.grade_name = gs.grade_name
            GROUP BY gs.grade_name, bp.best_wickets, bp.best_runs
            ORDER BY SUM(gs.wickets) DESC
        """),
        {"pid": player_id, "org_id": org_id},
    )
    return [dict(r) for r in result.mappings()]


async def get_club_summary(
    session: AsyncSession,
    org_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
) -> dict:
    where = "WHERE p.organisation_id = :org_id"
    params: dict = {"org_id": org_id}
    if season_id:
        where += " AND pss.season_id = :season_id"
        params["season_id"] = season_id

    res = await session.execute(
        text(f"""
            SELECT
                COUNT(DISTINCT pss.season_id) AS seasons,
                COUNT(DISTINCT pss.player_id) AS total_players,
                SUM(pss.runs) AS total_runs,
                SUM(pss.wickets) AS total_wickets,
                MAX(pss.high_score) AS highest_score
            FROM player_season_stats pss
            JOIN players p ON p.id = pss.player_id
            {where}
        """),
        params
    )
    row = dict(res.mappings().first() or {})
    return {
        "total_games": 0,
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "win_rate": 0,
        "total_runs": int(row.get("total_runs") or 0),
        "total_wickets": int(row.get("total_wickets") or 0),
        "highest_score": int(row.get("highest_score") or 0),
        "total_players": int(row.get("total_players") or 0),
        "seasons": int(row.get("seasons") or 0),
    }


async def get_game_partnerships(session: AsyncSession, game_id: str) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT
                pt.wicket_number,
                pt.innings_number,
                pt.runs,
                pt.balls,
                pt.batter1_runs,
                pt.batter2_runs,
                pt.batter1_id::text,
                pt.batter2_id::text,
                p1.name AS batter1_name,
                p2.name AS batter2_name
            FROM partnerships pt
            LEFT JOIN players p1 ON p1.id = pt.batter1_id
            LEFT JOIN players p2 ON p2.id = pt.batter2_id
            WHERE pt.game_id = :gid
            ORDER BY pt.innings_number, pt.wicket_number
        """),
        {"gid": game_id},
    )
    return [dict(r) for r in result.mappings()]


async def get_player_rankings(
    session: AsyncSession,
    player_id: str,
    org_id: str,
    season_id: Optional[str] = None,
) -> dict:
    """Return the player's rank for runs, wickets, and catches within their org.
    Returns None for each category if the player is outside the top 100."""
    season_clause = " AND pss.season_id = :season_id" if season_id else ""
    params: dict = {"org_id": org_id, "player_id": player_id}
    if season_id:
        params["season_id"] = season_id

    result = await session.execute(
        text(f"""
            WITH batting_agg AS (
                SELECT pss.player_id, SUM(pss.runs) AS total_runs
                FROM player_season_stats pss
                JOIN players p ON p.id = pss.player_id
                WHERE p.organisation_id = :org_id{season_clause}
                GROUP BY pss.player_id
            ),
            batting_ranked AS (
                SELECT player_id,
                       RANK() OVER (ORDER BY total_runs DESC NULLS LAST) AS runs_rank
                FROM batting_agg
            ),
            bowling_agg AS (
                SELECT pss.player_id, SUM(pss.wickets) AS total_wickets
                FROM player_season_stats pss
                JOIN players p ON p.id = pss.player_id
                WHERE p.organisation_id = :org_id{season_clause}
                GROUP BY pss.player_id
            ),
            bowling_ranked AS (
                SELECT player_id,
                       RANK() OVER (ORDER BY total_wickets DESC NULLS LAST) AS wickets_rank
                FROM bowling_agg
            ),
            fielding_agg AS (
                SELECT pss.player_id, SUM(pss.catches) AS total_catches
                FROM player_season_stats pss
                JOIN players p ON p.id = pss.player_id
                WHERE p.organisation_id = :org_id{season_clause}
                GROUP BY pss.player_id
            ),
            fielding_ranked AS (
                SELECT player_id,
                       RANK() OVER (ORDER BY total_catches DESC NULLS LAST) AS catches_rank
                FROM fielding_agg
            )
            SELECT
                CASE WHEN br.runs_rank <= 100 THEN br.runs_rank ELSE NULL END AS runs_rank,
                CASE WHEN bw.wickets_rank <= 100 THEN bw.wickets_rank ELSE NULL END AS wickets_rank,
                CASE WHEN fr.catches_rank <= 100 THEN fr.catches_rank ELSE NULL END AS catches_rank
            FROM
                (SELECT :player_id::uuid AS pid) base
                LEFT JOIN batting_ranked br ON br.player_id = base.pid
                LEFT JOIN bowling_ranked bw ON bw.player_id = base.pid
                LEFT JOIN fielding_ranked fr ON fr.player_id = base.pid
        """),
        params,
    )
    row = result.mappings().first()
    if not row:
        return {"runs_rank": None, "wickets_rank": None, "catches_rank": None}
    return {
        "runs_rank": row["runs_rank"],
        "wickets_rank": row["wickets_rank"],
        "catches_rank": row["catches_rank"],
    }
