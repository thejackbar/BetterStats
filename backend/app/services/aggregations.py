from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional
import uuid


async def get_career_batting(session: AsyncSession, player_id: str) -> Optional[dict]:
    result = await session.execute(
        text("SELECT * FROM career_batting WHERE player_id = :pid"),
        {"pid": player_id}
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def get_career_bowling(session: AsyncSession, player_id: str) -> Optional[dict]:
    result = await session.execute(
        text("SELECT * FROM career_bowling WHERE player_id = :pid"),
        {"pid": player_id}
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def get_career_fielding(session: AsyncSession, player_id: str) -> Optional[dict]:
    result = await session.execute(
        text("SELECT * FROM career_fielding WHERE player_id = :pid"),
        {"pid": player_id}
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
    base = """
        SELECT
            p.id AS player_id,
            p.name,
            COUNT(*) AS innings,
            SUM(bi.runs) AS total_runs,
            MAX(bi.runs) AS high_score,
            ROUND(SUM(bi.runs)::numeric / NULLIF(COUNT(*) FILTER (WHERE NOT bi.not_out), 0), 2) AS average,
            ROUND(SUM(bi.runs)::numeric / NULLIF(SUM(bi.balls), 0) * 100, 2) AS strike_rate,
            SUM(CASE WHEN bi.runs >= 50 THEN 1 ELSE 0 END) AS fifties,
            SUM(CASE WHEN bi.runs >= 100 THEN 1 ELSE 0 END) AS hundreds
        FROM batting_innings bi
        JOIN players p ON p.id = bi.player_id
        JOIN games g ON g.id = bi.game_id
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        WHERE p.organisation_id = :org_id
    """
    params: dict = {"org_id": org_id, "limit": limit}
    if season_id:
        base += " AND s.id = :season_id"
        params["season_id"] = season_id
    if grade_id:
        base += " AND gr.id = :grade_id"
        params["grade_id"] = grade_id
    base += " GROUP BY p.id, p.name ORDER BY total_runs DESC NULLS LAST LIMIT :limit"

    result = await session.execute(text(base), params)
    return [dict(r) for r in result.mappings()]


async def get_bowling_leaderboard(
    session: AsyncSession,
    org_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    base = """
        SELECT
            p.id AS player_id,
            p.name,
            COUNT(*) AS games,
            SUM(bs.wickets) AS total_wickets,
            ROUND(SUM(bs.runs)::numeric / NULLIF(SUM(bs.wickets), 0), 2) AS average,
            ROUND(SUM(bs.runs)::numeric / NULLIF(SUM(bs.overs), 0), 2) AS economy,
            MAX(bs.wickets) AS best_figures_wickets,
            SUM(bs.maidens) AS total_maidens
        FROM bowling_spells bs
        JOIN players p ON p.id = bs.player_id
        JOIN games g ON g.id = bs.game_id
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        WHERE p.organisation_id = :org_id
    """
    params: dict = {"org_id": org_id, "limit": limit}
    if season_id:
        base += " AND s.id = :season_id"
        params["season_id"] = season_id
    if grade_id:
        base += " AND gr.id = :grade_id"
        params["grade_id"] = grade_id
    base += " GROUP BY p.id, p.name ORDER BY total_wickets DESC NULLS LAST LIMIT :limit"

    result = await session.execute(text(base), params)
    return [dict(r) for r in result.mappings()]


async def get_fielding_leaderboard(
    session: AsyncSession,
    org_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    base = """
        SELECT
            p.id AS player_id,
            p.name,
            COUNT(*) AS games,
            SUM(fs.catches) AS total_catches,
            SUM(fs.run_outs) AS total_run_outs,
            SUM(fs.stumpings) AS total_stumpings,
            SUM(fs.catches + fs.run_outs + fs.stumpings) AS total_dismissals
        FROM fielding_stats fs
        JOIN players p ON p.id = fs.player_id
        JOIN games g ON g.id = fs.game_id
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        WHERE p.organisation_id = :org_id
    """
    params: dict = {"org_id": org_id, "limit": limit}
    if season_id:
        base += " AND s.id = :season_id"
        params["season_id"] = season_id
    if grade_id:
        base += " AND gr.id = :grade_id"
        params["grade_id"] = grade_id
    base += " GROUP BY p.id, p.name ORDER BY total_dismissals DESC NULLS LAST LIMIT :limit"

    result = await session.execute(text(base), params)
    return [dict(r) for r in result.mappings()]


async def get_player_batting_innings(
    session: AsyncSession,
    player_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
) -> list[dict]:
    base = """
        SELECT
            bi.id, bi.runs, bi.balls, bi.fours, bi.sixes, bi.strike_rate,
            bi.dismissal_type, bi.not_out, bi.batting_position,
            g.id AS game_id, g.played_at, g.home_team, g.away_team, g.result,
            gr.name AS grade_name, s.name AS season_name
        FROM batting_innings bi
        JOIN games g ON g.id = bi.game_id
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        WHERE bi.player_id = :pid
    """
    params: dict = {"pid": player_id}
    if season_id:
        base += " AND s.id = :season_id"
        params["season_id"] = season_id
    if grade_id:
        base += " AND gr.id = :grade_id"
        params["grade_id"] = grade_id
    base += " ORDER BY g.played_at DESC"

    result = await session.execute(text(base), params)
    return [dict(r) for r in result.mappings()]


async def get_player_bowling_spells(
    session: AsyncSession,
    player_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
) -> list[dict]:
    base = """
        SELECT
            bs.id, bs.overs, bs.maidens, bs.runs, bs.wickets, bs.wides,
            bs.no_balls, bs.economy,
            g.id AS game_id, g.played_at, g.home_team, g.away_team, g.result,
            gr.name AS grade_name, s.name AS season_name
        FROM bowling_spells bs
        JOIN games g ON g.id = bs.game_id
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        WHERE bs.player_id = :pid
    """
    params: dict = {"pid": player_id}
    if season_id:
        base += " AND s.id = :season_id"
        params["season_id"] = season_id
    if grade_id:
        base += " AND gr.id = :grade_id"
        params["grade_id"] = grade_id
    base += " ORDER BY g.played_at DESC"

    result = await session.execute(text(base), params)
    return [dict(r) for r in result.mappings()]


async def get_dismissal_breakdown(session: AsyncSession, player_id: str) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT
                COALESCE(NULLIF(dismissal_type, ''), 'not out') AS dismissal_type,
                COUNT(*) AS count
            FROM batting_innings
            WHERE player_id = :pid
            GROUP BY dismissal_type
            ORDER BY count DESC
        """),
        {"pid": player_id}
    )
    return [dict(r) for r in result.mappings()]


async def get_batting_by_position(session: AsyncSession, player_id: str) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT
                batting_position,
                COUNT(*) AS innings,
                SUM(runs) AS total_runs,
                MAX(runs) AS high_score,
                ROUND(SUM(runs)::numeric / NULLIF(COUNT(*) FILTER (WHERE NOT not_out), 0), 2) AS average,
                ROUND(SUM(runs)::numeric / NULLIF(SUM(balls), 0) * 100, 2) AS strike_rate,
                SUM(CASE WHEN runs >= 50 AND runs < 100 THEN 1 ELSE 0 END) AS fifties,
                SUM(CASE WHEN runs >= 100 THEN 1 ELSE 0 END) AS hundreds
            FROM batting_innings
            WHERE player_id = :pid AND batting_position IS NOT NULL
            GROUP BY batting_position
            ORDER BY batting_position
        """),
        {"pid": player_id}
    )
    return [dict(r) for r in result.mappings()]


async def get_batting_by_grade(session: AsyncSession, player_id: str) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT
                gr.name AS grade_name,
                COUNT(*) AS innings,
                SUM(bi.runs) AS total_runs,
                MAX(bi.runs) AS high_score,
                ROUND(SUM(bi.runs)::numeric / NULLIF(COUNT(*) FILTER (WHERE NOT bi.not_out), 0), 2) AS average,
                ROUND(SUM(bi.runs)::numeric / NULLIF(SUM(bi.balls), 0) * 100, 2) AS strike_rate,
                SUM(CASE WHEN bi.runs >= 50 AND bi.runs < 100 THEN 1 ELSE 0 END) AS fifties,
                SUM(CASE WHEN bi.runs >= 100 THEN 1 ELSE 0 END) AS hundreds
            FROM batting_innings bi
            JOIN games g ON g.id = bi.game_id
            JOIN grades gr ON gr.id = g.grade_id
            WHERE bi.player_id = :pid
            GROUP BY gr.name
            ORDER BY total_runs DESC
        """),
        {"pid": player_id}
    )
    return [dict(r) for r in result.mappings()]


async def get_season_by_season(session: AsyncSession, player_id: str) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT
                s.id AS season_id,
                s.name AS season_name,
                s.year,
                COUNT(DISTINCT bi.game_id) AS batting_innings,
                SUM(bi.runs) AS total_runs,
                MAX(bi.runs) AS high_score,
                ROUND(SUM(bi.runs)::numeric / NULLIF(COUNT(*) FILTER (WHERE NOT bi.not_out), 0), 2) AS batting_average,
                ROUND(SUM(bi.runs)::numeric / NULLIF(SUM(bi.balls), 0) * 100, 2) AS strike_rate,
                SUM(CASE WHEN bi.runs >= 50 THEN 1 ELSE 0 END) AS fifties,
                SUM(CASE WHEN bi.runs >= 100 THEN 1 ELSE 0 END) AS hundreds
            FROM batting_innings bi
            JOIN games g ON g.id = bi.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE bi.player_id = :pid
            GROUP BY s.id, s.name, s.year
            ORDER BY s.year DESC NULLS LAST, s.name
        """),
        {"pid": player_id}
    )
    batting_rows = {r["season_id"]: dict(r) for r in result.mappings()}

    result2 = await session.execute(
        text("""
            SELECT
                s.id AS season_id,
                COUNT(DISTINCT bs.game_id) AS bowling_innings,
                SUM(bs.wickets) AS total_wickets,
                SUM(bs.overs) AS total_overs,
                ROUND(SUM(bs.runs)::numeric / NULLIF(SUM(bs.wickets), 0), 2) AS bowling_average,
                ROUND(SUM(bs.runs)::numeric / NULLIF(SUM(bs.overs), 0), 2) AS economy,
                MAX(bs.wickets) AS best_figures_wickets
            FROM bowling_spells bs
            JOIN games g ON g.id = bs.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE bs.player_id = :pid
            GROUP BY s.id
        """),
        {"pid": player_id}
    )
    bowling_rows = {r["season_id"]: dict(r) for r in result2.mappings()}

    all_season_ids = set(batting_rows.keys()) | set(bowling_rows.keys())
    merged = []
    for sid in all_season_ids:
        row = batting_rows.get(sid, {"season_id": sid})
        bowl = bowling_rows.get(sid, {})
        row.update({k: v for k, v in bowl.items() if k != "season_id"})
        merged.append(row)

    merged.sort(key=lambda r: (r.get("year") or 0, r.get("season_name", "")), reverse=True)
    return merged


async def get_player_milestones(session: AsyncSession, player_id: str) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT
                m.id, m.milestone_type, m.milestone_value, m.achieved_at, m.detail,
                m.game_id,
                g.played_at AS game_date,
                g.home_team, g.away_team
            FROM milestones m
            LEFT JOIN games g ON g.id = m.game_id
            WHERE m.player_id = :pid
            ORDER BY m.milestone_type, m.milestone_value
        """),
        {"pid": player_id}
    )
    return [dict(r) for r in result.mappings()]


async def get_player_partnerships(session: AsyncSession, player_id: str) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT
                p.id,
                p.game_id,
                p.innings_number,
                p.wicket_number,
                p.runs,
                p.balls,
                p.batter1_runs,
                p.batter2_runs,
                p.batter1_id,
                p.batter2_id,
                CASE
                    WHEN p.batter1_id = :pid THEN p2.name
                    ELSE p1.name
                END AS partner_name,
                CASE
                    WHEN p.batter1_id = :pid THEN p.batter1_runs
                    ELSE p.batter2_runs
                END AS player_runs,
                g.played_at, g.home_team, g.away_team,
                gr.name AS grade_name
            FROM partnerships p
            LEFT JOIN players p1 ON p1.id = p.batter1_id
            LEFT JOIN players p2 ON p2.id = p.batter2_id
            JOIN games g ON g.id = p.game_id
            JOIN grades gr ON gr.id = g.grade_id
            WHERE p.batter1_id = :pid OR p.batter2_id = :pid
            ORDER BY g.played_at DESC, p.innings_number, p.wicket_number
        """),
        {"pid": player_id}
    )
    return [dict(r) for r in result.mappings()]


async def get_game_fall_of_wickets(session: AsyncSession, game_id: str) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT
                f.innings_number,
                f.wicket_number,
                f.score_at_fall,
                f.overs_at_fall,
                f.player_id,
                p.name AS player_name
            FROM fall_of_wickets f
            LEFT JOIN players p ON p.id = f.player_id
            WHERE f.game_id = :gid
            ORDER BY f.innings_number, f.wicket_number
        """),
        {"gid": game_id}
    )
    return [dict(r) for r in result.mappings()]


async def get_upcoming_milestones_for_org(
    session: AsyncSession,
    org_id: str,
    limit: int = 20,
) -> list[dict]:
    result = await session.execute(
        text("""
            WITH career AS (
                SELECT
                    p.id AS player_id,
                    p.name,
                    COALESCE(SUM(bi.runs), 0) AS career_runs,
                    COALESCE(SUM(bs.wickets), 0) AS career_wickets,
                    COALESCE(COUNT(DISTINCT bi.game_id), 0) AS batting_games
                FROM players p
                LEFT JOIN batting_innings bi ON bi.player_id = p.id
                LEFT JOIN bowling_spells bs ON bs.player_id = p.id
                WHERE p.organisation_id = :org_id
                GROUP BY p.id, p.name
            )
            SELECT player_id, name, career_runs, career_wickets, batting_games
            FROM career
            WHERE career_runs > 0 OR career_wickets > 0
        """),
        {"org_id": org_id}
    )
    rows = [dict(r) for r in result.mappings()]

    RUN_MILESTONES = [50, 100, 250, 500, 750, 1000, 1500, 2000, 3000, 5000]
    WICKET_MILESTONES = [10, 25, 50, 75, 100, 150, 200]

    upcoming = []
    for row in rows:
        runs = int(row["career_runs"] or 0)
        wickets = int(row["career_wickets"] or 0)
        player_id = str(row["player_id"])
        name = row["name"]

        for m in RUN_MILESTONES:
            if runs < m:
                upcoming.append({
                    "player_id": player_id,
                    "name": name,
                    "type": "runs",
                    "current": runs,
                    "target": m,
                    "needed": m - runs,
                })
                break

        for m in WICKET_MILESTONES:
            if wickets < m:
                upcoming.append({
                    "player_id": player_id,
                    "name": name,
                    "type": "wickets",
                    "current": wickets,
                    "target": m,
                    "needed": m - wickets,
                })
                break

    upcoming.sort(key=lambda x: x["needed"])
    return upcoming[:limit]


async def get_player_activity(session: AsyncSession, player_id: str) -> dict:
    bat_res = await session.execute(
        text("""
            SELECT
                MAX(g.played_at) AS last_bat_date,
                COUNT(*) AS total_innings,
                SUM(CASE WHEN bi.runs = 0 AND NOT bi.not_out THEN 1 ELSE 0 END) AS total_ducks,
                MAX(CASE WHEN bi.runs = 0 AND NOT bi.not_out THEN g.played_at END) AS last_duck_date,
                SUM(bi.sixes) AS total_sixes,
                SUM(bi.fours) AS total_fours
            FROM batting_innings bi
            JOIN games g ON g.id = bi.game_id
            WHERE bi.player_id = :pid
        """),
        {"pid": player_id}
    )
    bowl_res = await session.execute(
        text("""
            SELECT
                MAX(g.played_at) AS last_bowl_date,
                MAX(CASE WHEN bs.wickets > 0 THEN g.played_at END) AS last_wicket_date,
                SUM(CASE WHEN bs.wickets = 0 THEN 1 ELSE 0 END) AS wicketless_spells,
                MAX(bs.wickets) AS best_spell_wickets,
                SUM(bs.wickets) AS total_wickets
            FROM bowling_spells bs
            JOIN games g ON g.id = bs.game_id
            WHERE bs.player_id = :pid
        """),
        {"pid": player_id}
    )
    b = dict(bat_res.mappings().first() or {})
    bw = dict(bowl_res.mappings().first() or {})

    dates = [d for d in [b.get("last_bat_date"), bw.get("last_bowl_date")] if d]
    last_game_date = max(dates) if dates else None

    return {
        "last_game_date": last_game_date.isoformat() if last_game_date else None,
        "last_bat_date": b["last_bat_date"].isoformat() if b.get("last_bat_date") else None,
        "last_bowl_date": bw["last_bowl_date"].isoformat() if bw.get("last_bowl_date") else None,
        "last_wicket_date": bw["last_wicket_date"].isoformat() if bw.get("last_wicket_date") else None,
        "last_duck_date": b["last_duck_date"].isoformat() if b.get("last_duck_date") else None,
        "total_innings": int(b.get("total_innings") or 0),
        "total_ducks": int(b.get("total_ducks") or 0),
        "total_sixes": int(b.get("total_sixes") or 0),
        "total_fours": int(b.get("total_fours") or 0),
        "total_wickets": int(bw.get("total_wickets") or 0),
        "best_spell_wickets": int(bw.get("best_spell_wickets") or 0),
        "wicketless_spells": int(bw.get("wicketless_spells") or 0),
    }


async def get_batting_leaderboard_extended(
    session: AsyncSession,
    org_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
    sort_by: str = "total_runs",
    limit: int = 20,
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
            p.name,
            COUNT(*) AS innings,
            SUM(bi.runs) AS total_runs,
            MAX(bi.runs) AS high_score,
            ROUND(SUM(bi.runs)::numeric / NULLIF(COUNT(*) FILTER (WHERE NOT bi.not_out), 0), 2) AS average,
            ROUND(SUM(bi.runs)::numeric / NULLIF(SUM(bi.balls), 0) * 100, 2) AS strike_rate,
            SUM(CASE WHEN bi.runs >= 50 AND bi.runs < 100 THEN 1 ELSE 0 END) AS fifties,
            SUM(CASE WHEN bi.runs >= 100 THEN 1 ELSE 0 END) AS hundreds,
            COALESCE(SUM(bi.sixes), 0) AS total_sixes,
            COALESCE(SUM(bi.fours), 0) AS total_fours,
            SUM(CASE WHEN bi.runs = 0 AND NOT bi.not_out THEN 1 ELSE 0 END) AS ducks,
            COUNT(DISTINCT bi.game_id) AS games
        FROM batting_innings bi
        JOIN players p ON p.id = bi.player_id
        JOIN games g ON g.id = bi.game_id
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        WHERE p.organisation_id = :org_id
    """
    params: dict = {"org_id": org_id, "limit": limit}
    if season_id:
        base += " AND s.id = :season_id"
        params["season_id"] = season_id
    if grade_id:
        base += " AND gr.id = :grade_id"
        params["grade_id"] = grade_id
    base += f" GROUP BY p.id, p.name ORDER BY {sort_by} DESC NULLS LAST LIMIT :limit"

    result = await session.execute(text(base), params)
    return [dict(r) for r in result.mappings()]


async def get_bowling_leaderboard_extended(
    session: AsyncSession,
    org_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
    sort_by: str = "total_wickets",
    limit: int = 20,
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
            p.name,
            COUNT(DISTINCT bs.game_id) AS games,
            SUM(bs.wickets) AS total_wickets,
            ROUND(SUM(bs.runs)::numeric / NULLIF(SUM(bs.wickets), 0), 2) AS average,
            ROUND(SUM(bs.runs)::numeric / NULLIF(SUM(bs.overs), 0), 2) AS economy,
            MAX(bs.wickets) AS best_figures_wickets,
            SUM(bs.maidens) AS total_maidens,
            SUM(bs.overs) AS total_overs,
            SUM(CASE WHEN bs.wickets >= 5 THEN 1 ELSE 0 END) AS five_fors
        FROM bowling_spells bs
        JOIN players p ON p.id = bs.player_id
        JOIN games g ON g.id = bs.game_id
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        WHERE p.organisation_id = :org_id
    """
    params: dict = {"org_id": org_id, "limit": limit}
    if season_id:
        base += " AND s.id = :season_id"
        params["season_id"] = season_id
    if grade_id:
        base += " AND gr.id = :grade_id"
        params["grade_id"] = grade_id
    base += f" GROUP BY p.id, p.name ORDER BY {sort_by} DESC NULLS LAST LIMIT :limit"

    result = await session.execute(text(base), params)
    return [dict(r) for r in result.mappings()]


async def get_club_summary(
    session: AsyncSession,
    org_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
) -> dict:
    base_filter = "WHERE p.organisation_id = :org_id"
    params: dict = {"org_id": org_id}
    if season_id:
        base_filter += " AND s.id = :season_id"
        params["season_id"] = season_id
    if grade_id:
        base_filter += " AND gr.id = :grade_id"
        params["grade_id"] = grade_id

    res = await session.execute(
        text(f"""
            SELECT
                COUNT(DISTINCT g.id) AS total_games,
                SUM(CASE WHEN g.result = 'WIN' THEN 1 ELSE 0 END) AS wins,
                SUM(CASE WHEN g.result = 'LOSS' THEN 1 ELSE 0 END) AS losses,
                SUM(CASE WHEN g.result IN ('DRAW','TIE','NO_RESULT') THEN 1 ELSE 0 END) AS draws,
                SUM(bi.runs) AS total_runs,
                SUM(bs.wickets) AS total_wickets,
                MAX(bi.runs) AS highest_score
            FROM games g
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            JOIN players p ON p.organisation_id = s.organisation_id
            LEFT JOIN batting_innings bi ON bi.game_id = g.id AND bi.player_id = p.id
            LEFT JOIN bowling_spells bs ON bs.game_id = g.id AND bs.player_id = p.id
            {base_filter}
        """),
        params
    )
    row = dict(res.mappings().first() or {})
    total = int(row.get("total_games") or 0)
    wins = int(row.get("wins") or 0)
    return {
        "total_games": total,
        "wins": wins,
        "losses": int(row.get("losses") or 0),
        "draws": int(row.get("draws") or 0),
        "win_rate": round(wins / total * 100, 1) if total > 0 else 0,
        "total_runs": int(row.get("total_runs") or 0),
        "total_wickets": int(row.get("total_wickets") or 0),
        "highest_score": int(row.get("highest_score") or 0),
    }


async def get_game_partnerships(session: AsyncSession, game_id: str) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT
                p.innings_number,
                p.wicket_number,
                p.runs,
                p.balls,
                p.batter1_runs,
                p.batter2_runs,
                p.batter1_id,
                p.batter2_id,
                p1.name AS batter1_name,
                p2.name AS batter2_name
            FROM partnerships p
            LEFT JOIN players p1 ON p1.id = p.batter1_id
            LEFT JOIN players p2 ON p2.id = p.batter2_id
            WHERE p.game_id = :gid
            ORDER BY p.innings_number, p.wicket_number
        """),
        {"gid": game_id}
    )
    return [dict(r) for r in result.mappings()]
