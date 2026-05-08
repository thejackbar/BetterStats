import asyncio
import httpx
import json
import logging
import re
import time
from typing import Optional

from app.config.settings import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.playhq.com"
TENANT = "ca"
TIMEOUT = 15.0
CACHE_TTL = 300  # 5 minutes
SCORECARD_CACHE_TTL = 1800  # 30 minutes — final results don't change
_SEMAPHORE = asyncio.Semaphore(4)  # max 4 concurrent PlayHQ requests

_cache: dict[str, tuple[float, list]] = {}
_scorecard_cache: dict[str, tuple[float, dict]] = {}
_appearances_cache: dict[str, tuple[float, tuple]] = {}
APPEARANCES_CACHE_TTL = 86400  # 24 hours — FINAL game appearances never change

PUBLIC_API_KEY = "6e02cae8-e3f0-4846-b024-4072716f1c60"

_PERIOD_ORDER = ["FIRST_INNINGS", "SECOND_INNINGS", "THIRD_INNINGS", "FOURTH_INNINGS", "SUPER_OVER"]

_HOW_OUT = {
    "CAUGHT": "c",
    "BOWLED": "b",
    "LEG_BEFORE_WICKET": "lbw",
    "STUMPED": "st",
    "RUN_OUT": "run out",
    "HIT_BALL_TWICE": "hit the ball twice",
    "HIT_WICKET": "hit wicket",
    "OBSTRUCTING_THE_FIELD": "obstructing the field",
    "TIMED_OUT": "timed out",
    "RETIRED_HURT": "retired hurt",
}


def _headers() -> dict:
    return {
        "x-api-key": settings.playhq_api_key or PUBLIC_API_KEY,
        "x-phq-tenant": TENANT,
    }


def _get_cached(key: str):
    if key in _cache:
        ts, val = _cache[key]
        if time.time() - ts < CACHE_TTL:
            return val
    return None


def _set_cached(key: str, val):
    _cache[key] = (time.time(), val)
    return val


async def _get(url: str) -> dict:
    """GET with rate-limit retry (429 → wait 1s and retry once)."""
    async with _SEMAPHORE:
        async with httpx.AsyncClient() as client:
            r = await client.get(url, headers=_headers(), timeout=TIMEOUT)
            if r.status_code == 429:
                await asyncio.sleep(1.0)
                r = await client.get(url, headers=_headers(), timeout=TIMEOUT)
            r.raise_for_status()
            return r.json()


async def get_org_seasons(playhq_id: str) -> list:
    key = f"seasons:{playhq_id}"
    cached = _get_cached(key)
    if cached is not None:
        return cached

    all_seasons = []
    page = 1
    while True:
        url = f"{BASE_URL}/v1/organisations/{playhq_id}/seasons?page={page}&size=50"
        data = await _get(url)
        batch = data.get("data", [])
        all_seasons.extend(batch)
        links = data.get("links") or {}
        if links.get("next"):
            page += 1
        elif len(batch) < 50 or not batch:
            break
        else:
            page += 1

    logger.info(f"PlayHQ partner: got {len(all_seasons)} seasons for org {playhq_id}")
    return _set_cached(key, all_seasons)


async def get_season_grades(season_id: str) -> list:
    key = f"grades:{season_id}"
    cached = _get_cached(key)
    if cached is not None:
        return cached
    try:
        data = await _get(f"{BASE_URL}/v1/seasons/{season_id}/grades")
        return _set_cached(key, data.get("data", []))
    except Exception as e:
        logger.debug(f"PlayHQ: grades fetch failed for season {season_id}: {e}")
        return _set_cached(key, [])


async def get_grade_games(grade_id: str) -> list:
    key = f"games:{grade_id}"
    cached = _get_cached(key)
    if cached is not None:
        return cached
    data = await _get(f"{BASE_URL}/v1/grades/{grade_id}/games")
    games = data.get("data", [])
    return _set_cached(key, games)


def _outcome_to_result(outcome: str) -> Optional[str]:
    return {"WON": "WIN", "LOST": "LOSS", "DREW": "DRAW", "TIE": "DRAW"}.get(outcome)


def _parse_game(game: dict, grade_name: str, grade_id: str, season_name: str, keyword: str) -> Optional[dict]:
    competitors = game.get("competitors", [])
    our_teams = [c for c in competitors if keyword and keyword in c.get("name", "").lower()]
    if not our_teams:
        return None

    our_team = our_teams[0]
    home = next((c for c in competitors if c.get("isHomeTeam")), competitors[0] if competitors else {})
    away = next((c for c in competitors if not c.get("isHomeTeam")), competitors[-1] if len(competitors) > 1 else {})
    winner = next((c.get("name") for c in competitors if c.get("outcome") == "WON"), None)
    schedule = game.get("schedule", {})
    venue = game.get("venue") or {}

    return {
        "id": game.get("id"),
        "status": game.get("status"),
        "played_at": schedule.get("date"),
        "time": schedule.get("time"),
        "home_team": home.get("name", ""),
        "away_team": away.get("name", ""),
        "home_score": home.get("scoreTotal"),
        "away_score": away.get("scoreTotal"),
        "result": _outcome_to_result(our_team.get("outcome", "")),
        "winning_team": winner,
        "grade": {"name": grade_name},
        "grade_id": grade_id,
        "season": season_name,
        "round": (game.get("round") or {}).get("name"),
        "venue": venue.get("name"),
        "url": game.get("url"),
        "competitors": [
            {
                "name": c.get("name", ""),
                "is_home": c.get("isHomeTeam", False),
                "outcome": c.get("outcome"),
                "score": c.get("scoreTotal"),
                "innings": [
                    {
                        "innings_number": inn.get("inningsNumber"),
                        "score": inn.get("scoreTotal"),
                        "declared": inn.get("isDeclared", False),
                    }
                    for inn in (c.get("innings") or [])
                ],
            }
            for c in competitors
        ],
    }


async def get_org_games(
    playhq_id: str,
    org_name: str,
    db_seasons: list[dict] | None = None,
    grassroots_org_id: str = "",
) -> list:
    """Fetch all games for an org across all discoverable seasons/grades."""
    if not settings.playhq_api_key or not playhq_id:
        return []

    # Full result cache — avoids repeating the expensive multi-API fan-out
    cache_key = f"org_games:{playhq_id}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    # ── Discover seasons ──────────────────────────────────────────────────
    try:
        api_seasons = await get_org_seasons(playhq_id)
    except Exception as e:
        logger.warning(f"PlayHQ: failed to get seasons for {playhq_id}: {e}")
        api_seasons = []

    api_name_to_id: dict[str, str] = {
        (s.get("name") or "").strip().lower(): s["id"]
        for s in api_seasons if s.get("id")
    }

    seen_season_ids: set[str] = set()
    unique_seasons: list[dict] = []
    for s in api_seasons:
        sid = s.get("id")
        if sid and sid not in seen_season_ids:
            seen_season_ids.add(sid)
            unique_seasons.append({"id": sid, "name": s.get("name", "")})
    for s in (db_seasons or []):
        db_name = (s.get("name") or "").strip().lower()
        if api_name_to_id.get(db_name):
            continue
        db_sid = str(s.get("id", ""))
        if db_sid and db_sid not in seen_season_ids:
            seen_season_ids.add(db_sid)
            unique_seasons.append({"id": db_sid, "name": s.get("name", "")})

    logger.info(f"PlayHQ: {len(unique_seasons)} seasons to probe for {playhq_id}: {[s['name'] for s in unique_seasons[:10]]}")

    # ── Discover grades via season IDs (cached per season) ───────────────
    season_grade_results = await asyncio.gather(
        *[get_season_grades(s["id"]) for s in unique_seasons],
        return_exceptions=True,
    )

    seen_grade_ids: set[str] = set()
    grade_season_pairs: list[tuple[dict, str]] = []

    for i, grades in enumerate(season_grade_results):
        if isinstance(grades, list):
            season_name = unique_seasons[i].get("name", "")
            for g in grades:
                gid = g.get("id", "")
                if gid and gid not in seen_grade_ids:
                    seen_grade_ids.add(gid)
                    grade_season_pairs.append((g, season_name))

    # ── Also try org-level grades endpoint (may return all historical grades) ─
    try:
        org_grades_data = await _get(f"{BASE_URL}/v1/organisations/{playhq_id}/grades")
        org_grades = org_grades_data.get("data", [])
        logger.info(f"PlayHQ: org-grades endpoint returned {len(org_grades)} grades for {playhq_id}")
        for g in org_grades:
            gid = g.get("id", "")
            if gid and gid not in seen_grade_ids:
                seen_grade_ids.add(gid)
                season_name = (g.get("season") or {}).get("name", "")
                grade_season_pairs.append((g, season_name))
    except Exception as e:
        logger.debug(f"PlayHQ: org-grades endpoint unavailable for {playhq_id}: {e}")

    if not grade_season_pairs:
        logger.info(f"PlayHQ: no grades found for {playhq_id}")
        return _set_cached(cache_key, [])

    logger.info(f"PlayHQ: fetching games for {len(grade_season_pairs)} grades")

    # ── Fetch games for all grades concurrently (semaphore limits rate) ───
    game_results = await asyncio.gather(
        *[get_grade_games(g["id"]) for g, _ in grade_season_pairs],
        return_exceptions=True,
    )

    keyword = org_name.split()[0].lower() if org_name else ""
    all_games = []

    for i, games in enumerate(game_results):
        if not isinstance(games, list):
            if isinstance(games, Exception):
                logger.warning(f"PlayHQ: grade fetch failed: {games}")
            continue
        grade, season_name = grade_season_pairs[i]
        grade_name = grade.get("name", "")
        grade_id = grade.get("id", "")
        for game in games:
            parsed = _parse_game(game, grade_name, grade_id, season_name, keyword)
            if parsed:
                all_games.append(parsed)

    return _set_cached(cache_key, all_games)


def _player_name_from_gql(player: dict) -> str:
    """Extract display name from a DiscoverParticipant / DiscoverAnonymousParticipant / DiscoverRegularFillInPlayer."""
    if not player:
        return ""
    profile = player.get("profile") or {}
    first = profile.get("firstName", "")
    last = profile.get("lastName", "")
    if first or last:
        return f"{first} {last}".strip()
    return player.get("name", "")


def _stat_val(stats: list, *type_values: str) -> Optional[int]:
    """Return first matching statistic count from a periodStatistics.statistics list."""
    for s in stats:
        tv = (s.get("type") or {}).get("value", "")
        if tv in type_values:
            return s.get("count")
    return None


def _parse_scorecard_statistics(game_data: dict) -> dict:
    """
    Convert discoverGame statistics response into innings/batting/bowling format.

    PlayHQ uses a generic statistics model:
    - statistics.home/away.players[].periodStatistics — per-player per-period stats
    - period.value: FIRST_INNINGS, SECOND_INNINGS, etc.
    - type: BATTING or BOWLING
    - statistics[].type.value: individual stat identifiers (e.g. RUNS_SCORED, BALLS_FACED)
    - shared[]: dismissal/wicket events with dismissalType and players
    """
    stats = game_data.get("statistics") or {}
    shared = stats.get("shared") or []
    home_team = _player_name_from_gql(game_data.get("home") or {}) or (game_data.get("home") or {}).get("name", "")
    away_team = _player_name_from_gql(game_data.get("away") or {}) or (game_data.get("away") or {}).get("name", "")

    # Log raw stats for debugging
    logger.info(f"PlayHQ discoverGame statistics keys: home_players={len((stats.get('home') or {}).get('players') or [])}, away_players={len((stats.get('away') or {}).get('players') or [])}, shared={len(shared)}")
    if shared:
        logger.info(f"PlayHQ shared[0] sample: {shared[0]!r}")
    home_players = (stats.get("home") or {}).get("players") or []
    if home_players and (home_players[0].get("periodStatistics") or []):
        ps = home_players[0]["periodStatistics"][0]
        logger.info(f"PlayHQ periodStatistics[0] sample: period={ps.get('period')}, type={ps.get('type')}, stats={ps.get('statistics')!r}")

    # Collect per-period score totals from result
    result = game_data.get("result") or {}
    period_scores: dict[str, dict] = {}  # period_value → {home_score, away_score, home_wickets, away_wickets}
    for side_key in ("home", "away"):
        side = result.get(side_key) or {}
        for period_entry in (side.get("periods") or []):
            pv = (period_entry.get("period") or {}).get("value", "")
            if not pv:
                continue
            if pv not in period_scores:
                period_scores[pv] = {}
            for s in (period_entry.get("statistics") or []):
                tv = (s.get("type") or {}).get("value", "")
                count = s.get("count")
                if "RUNS" in tv or "SCORE" in tv:
                    period_scores[pv][f"{side_key}_score"] = count
                elif "WICKET" in tv:
                    period_scores[pv][f"{side_key}_wickets"] = count

    # Build innings list from player periodStatistics
    # Gather all distinct periods across all players
    all_periods: dict[str, int] = {}  # period_value → order index (FIRST_INNINGS=1, SECOND_INNINGS=2, ...)
    _PERIOD_ORDER = ["FIRST_INNINGS", "SECOND_INNINGS", "THIRD_INNINGS", "FOURTH_INNINGS", "SUPER_OVER"]
    for team_key in ("home", "away"):
        for p in (stats.get(team_key) or {}).get("players") or []:
            for ps in (p.get("periodStatistics") or []):
                pv = (ps.get("period") or {}).get("value", "")
                if pv and "INNINGS" in pv or "SUPER_OVER" in pv:
                    if pv not in all_periods:
                        try:
                            all_periods[pv] = _PERIOD_ORDER.index(pv) + 1
                        except ValueError:
                            all_periods[pv] = len(all_periods) + 1

    if not all_periods:
        logger.info("PlayHQ discoverGame: no innings periods found in player statistics")
        return {"innings": [], "_raw": game_data}

    innings_out = []
    for period_val, inn_num in sorted(all_periods.items(), key=lambda x: x[1]):
        period_label = period_val.replace("_", " ").title()

        # Determine batting team by which team has batting stats for this period
        batting_team_name = ""
        batting_side = None

        for side_key in ("home", "away"):
            side_players = (stats.get(side_key) or {}).get("players") or []
            for p in side_players:
                for ps in (p.get("periodStatistics") or []):
                    pv2 = (ps.get("period") or {}).get("value", "")
                    if pv2 == period_val and ps.get("type") == "BATTING":
                        batting_side = side_key
                        batting_team_name = home_team if side_key == "home" else away_team
                        break
                if batting_side:
                    break
            if batting_side:
                break

        bowling_side = "away" if batting_side == "home" else "home"

        # Batting rows
        batting_rows = []
        batting_players = (stats.get(batting_side) or {}).get("players") if batting_side else []
        for p in (batting_players or []):
            player_name = _player_name_from_gql(p.get("player") or {})
            for ps in (p.get("periodStatistics") or []):
                if (ps.get("period") or {}).get("value") != period_val:
                    continue
                if ps.get("type") != "BATTING":
                    continue
                pstats = ps.get("statistics") or []
                runs = _stat_val(pstats, "RUNS_SCORED", "RUNS", "RUN")
                balls = _stat_val(pstats, "BALLS_FACED", "BALLS", "BALL")
                fours = _stat_val(pstats, "FOURS", "FOUR", "BOUNDARIES")
                sixes = _stat_val(pstats, "SIXES", "SIX")
                status = ps.get("status") or ""
                not_out = "NOT_OUT" in status.upper() or status.upper() == "NOT OUT"
                batting_rows.append({
                    "name": player_name,
                    "how_out": "" if not_out else status.lower().replace("_", " "),
                    "bowled_by": "",
                    "runs": runs,
                    "balls": balls,
                    "fours": fours,
                    "sixes": sixes,
                    "not_out": not_out,
                    "display_order": ps.get("displayOrder", 99),
                })
        batting_rows.sort(key=lambda x: x.pop("display_order", 99))

        # Bowling rows
        bowling_rows = []
        bowling_players = (stats.get(bowling_side) or {}).get("players") if bowling_side else []
        for p in (bowling_players or []):
            player_name = _player_name_from_gql(p.get("player") or {})
            for ps in (p.get("periodStatistics") or []):
                if (ps.get("period") or {}).get("value") != period_val:
                    continue
                if ps.get("type") != "BOWLING":
                    continue
                pstats = ps.get("statistics") or []
                wickets = _stat_val(pstats, "WICKETS", "WICKET", "WICKETS_TAKEN")
                runs = _stat_val(pstats, "RUNS_CONCEDED", "RUNS", "RUN")
                maidens = _stat_val(pstats, "MAIDENS", "MAIDEN")
                wides = _stat_val(pstats, "WIDES", "WIDE")
                no_balls = _stat_val(pstats, "NO_BALLS", "NO_BALL", "NOBALLS")
                legal_balls = _stat_val(pstats, "LEGAL_BALLS", "LEGAL_BALL", "BALLS_BOWLED", "BALLS")
                overs_val = _stat_val(pstats, "OVERS", "OVER")
                if overs_val is None and legal_balls is not None:
                    overs_val = f"{legal_balls // 6}.{legal_balls % 6}"
                bowling_rows.append({
                    "name": player_name,
                    "overs": overs_val,
                    "maidens": maidens,
                    "runs": runs,
                    "wickets": wickets,
                    "wides": wides,
                    "no_balls": no_balls,
                    "display_order": ps.get("displayOrder", 99),
                })
        bowling_rows.sort(key=lambda x: x.pop("display_order", 99))

        ps_info = period_scores.get(period_val) or {}
        total_runs = ps_info.get(f"{batting_side}_score") if batting_side else None
        total_wickets = ps_info.get(f"{batting_side}_wickets") if batting_side else None

        innings_out.append({
            "innings_number": inn_num,
            "batting_team": batting_team_name,
            "total_runs": total_runs,
            "total_wickets": total_wickets,
            "overs": None,
            "extras": None,
            "batting": batting_rows,
            "bowling": bowling_rows,
        })

    return {"innings": innings_out}


def _stat_map(statistics: list) -> dict:
    return {s.get("type"): s.get("value") for s in (statistics or [])}


def _overs_str(balls: Optional[int]) -> Optional[str]:
    if balls is None:
        return None
    return f"{balls // 6}.{balls % 6}"


def _economy(runs: Optional[int], overs_str: Optional[str]) -> Optional[float]:
    if runs is None or not overs_str:
        return None
    try:
        whole, part = (overs_str.split(".") + ["0"])[:2]
        dec = int(whole) + int(part) / 6
        return round(runs / dec, 2) if dec > 0 else None
    except Exception:
        return None


def _parse_summary_rest(data: dict) -> dict:
    appearances_by_id = {a["id"]: a for a in (data.get("appearances") or [])}
    teams = data.get("teams") or []

    def player_name(pid: str) -> str:
        p = appearances_by_id.get(pid) or {}
        return f"{p.get('firstName', '')} {p.get('lastName', '')}".strip() or pid

    def team_name(tid: str) -> str:
        return next((t.get("name", "") for t in teams if t.get("id") == tid), "")

    def get_shared_stats(batsman_id: str, all_shared: list) -> dict:
        for entry in all_shared:
            apps = entry.get("appearances") or []
            if any(a.get("role") == "BATTING" and a.get("id") == batsman_id for a in apps):
                bowling_app = next((a for a in apps if a.get("role") == "BOWLING"), None)
                fielder_app = next((a for a in apps if a.get("role") == "FIELDING"), None)
                return {
                    "how": entry.get("type"),
                    "bowler": player_name(bowling_app["id"]) if bowling_app else None,
                    "fielder": player_name(fielder_app["id"]) if fielder_app else None,
                }
        return {}

    def format_how_out(pid: str, status: str, shared: dict) -> str:
        if status == "NOT_OUT":
            return "not out"
        if status in ("DID_NOT_BAT", ""):
            return ""
        how = shared.get("how")
        if not how:
            return status.replace("_", " ").lower()
        if how == "BOWLED":
            bowler = shared.get("bowler")
            return f"b {bowler}" if bowler else "b"
        prefix = _HOW_OUT.get(how, how.replace("_", " ").lower())
        parts = [prefix]
        fielder = shared.get("fielder")
        bowler = shared.get("bowler")
        if fielder:
            parts.append(fielder)
        if bowler and how not in ("RUN_OUT", "HIT_BALL_TWICE", "HIT_WICKET", "OBSTRUCTING_THE_FIELD"):
            parts.append(f"b {bowler}")
        return " ".join(parts)

    # Normalize period names: "First Innings" → "FIRST_INNINGS" etc.
    def _canon(name: str) -> str:
        return name.upper().replace(" ", "_").strip("_")

    normalized_by_canon: dict[str, list] = {}
    ordered_canons: list[str] = []
    for period in (data.get("periods") or []):
        raw = period.get("name", "")
        canon = _canon(raw)
        if canon not in normalized_by_canon:
            ordered_canons.append(canon)
        normalized_by_canon.setdefault(canon, []).append(period)

    logger.info(f"REST scorecard periods: {ordered_canons}")

    # Order canons: _PERIOD_ORDER first, then any extras
    seen_canons: set[str] = set()
    canon_order: list[str] = []
    for name in _PERIOD_ORDER:
        if name in normalized_by_canon:
            canon_order.append(name)
            seen_canons.add(name)
    for canon in ordered_canons:
        if canon not in seen_canons:
            canon_order.append(canon)

    # Build one (periods, batting_team_id, bowling_team_id) entry per innings.
    # Handles both "one period per innings" AND "one period with both teams inside".
    innings_entries: list[tuple] = []
    for canon in canon_order:
        periods_for_canon = normalized_by_canon[canon]
        ordered_bat: list[str] = []
        ordered_bowl: list[str] = []
        seen_bat: set[str] = set()
        seen_bowl: set[str] = set()
        for period in periods_for_canon:
            for team_data in (period.get("teams") or []):
                tid = team_data.get("id")
                if not tid:
                    continue
                if team_data.get("discipline") == "BATTING" and tid not in seen_bat:
                    ordered_bat.append(tid)
                    seen_bat.add(tid)
                elif team_data.get("discipline") == "BOWLING" and tid not in seen_bowl:
                    ordered_bowl.append(tid)
                    seen_bowl.add(tid)
        for i, bat_tid in enumerate(ordered_bat):
            bowl_tid = ordered_bowl[i] if i < len(ordered_bowl) else None
            innings_entries.append((periods_for_canon, bat_tid, bowl_tid))

    logger.info(f"REST scorecard: {len(innings_entries)} innings from {len(canon_order)} period group(s): {canon_order}")

    innings_out = []
    for inn_num, (periods, batting_team_id, bowling_team_id) in enumerate(innings_entries, 1):

        all_shared = []
        for period in periods:
            all_shared.extend(period.get("sharedStatistics") or [])

        batting_rows = []
        team_batting_stats: dict = {}
        bowling_rows = []

        for period in periods:
            for team_data in (period.get("teams") or []):
                discipline = team_data.get("discipline")
                tid = team_data.get("id")

                if discipline == "BATTING" and tid == batting_team_id:
                    team_batting_stats = _stat_map(team_data.get("statistics") or [])
                    sorted_apps = sorted(
                        team_data.get("appearances") or [],
                        key=lambda a: a.get("displayOrder", 99),
                    )
                    for app in sorted_apps:
                        pid = app.get("id") or app.get("appearanceId", "")
                        batting_position = app.get("displayOrder")
                        stats = _stat_map(app.get("statistics") or [])
                        status = app.get("status", "")
                        shared = get_shared_stats(pid, all_shared)
                        runs = stats.get("TOTAL_RUNS")
                        balls = stats.get("BALLS_FACED")
                        sr = round(runs / balls * 100, 1) if runs is not None and balls else None
                        batting_rows.append({
                            "name": player_name(pid),
                            "playhq_appearance_id": pid,
                            "batting_position": batting_position,
                            "how_out": format_how_out(pid, status, shared),
                            "runs": runs if status != "DID_NOT_BAT" else None,
                            "balls": balls if status != "DID_NOT_BAT" else None,
                            "fours": stats.get("FOURS"),
                            "sixes": stats.get("SIXES"),
                            "not_out": status == "NOT_OUT",
                            "did_not_bat": status == "DID_NOT_BAT",
                            "strike_rate": sr,
                        })

                elif discipline == "BOWLING" and tid == bowling_team_id:
                    sorted_apps = sorted(
                        team_data.get("appearances") or [],
                        key=lambda a: a.get("displayOrder", 99),
                    )
                    for app in sorted_apps:
                        pid = app.get("id") or app.get("appearanceId", "")
                        stats = _stat_map(app.get("statistics") or [])
                        wickets = stats.get("WICKETS") or stats.get("TOTAL_WICKETS") or stats.get("WICKETS_TAKEN")
                        runs_c = stats.get("RUNS_CONCEDED") or stats.get("RUNS")
                        maidens = stats.get("MAIDENS")
                        wides = stats.get("WIDES")
                        no_balls = stats.get("NO_BALLS")
                        balls_bowled = stats.get("BALLS_BOWLED") or stats.get("LEGAL_BALLS")
                        overs = stats.get("OVERS") or (_overs_str(balls_bowled) if balls_bowled is not None else None)
                        if any(v is not None for v in [wickets, runs_c, overs]):
                            bowling_rows.append({
                                "name": player_name(pid),
                                "playhq_appearance_id": pid,
                                "overs": str(overs) if overs is not None else None,
                                "maidens": maidens,
                                "runs": runs_c,
                                "wickets": wickets,
                                "wides": wides,
                                "no_balls": no_balls,
                                "economy": _economy(runs_c, str(overs) if overs is not None else None),
                            })

        # Extract fall of wickets from shared statistics (one entry per wicket event)
        fow_out = []
        for entry in sorted(all_shared, key=lambda e: e.get("displayOrder") or 99):
            apps = entry.get("appearances") or []
            bat_app = next((a for a in apps if a.get("role") == "BATTING"), None)
            if not bat_app:
                continue
            fow_stats = _stat_map(entry.get("statistics") or [])
            score = (fow_stats.get("FALL_OF_WICKET_SCORE") or fow_stats.get("SCORE")
                     or fow_stats.get("BATTING_TOTAL") or fow_stats.get("RUNS"))
            fow_out.append({
                "wicket_number": entry.get("displayOrder"),
                "batter_playhq_id": bat_app.get("id"),
                "score_at_fall": score,
                "overs_at_fall": fow_stats.get("OVERS_AT_FALL") or fow_stats.get("OVERS"),
            })

        innings_out.append({
            "innings_number": inn_num,
            "batting_team": team_name(batting_team_id) if batting_team_id else "",
            "bowling_team": team_name(bowling_team_id) if bowling_team_id else "",
            "total_runs": team_batting_stats.get("TOTAL_SCORE"),
            "total_wickets": team_batting_stats.get("TOTAL_OUTS"),
            "overs": team_batting_stats.get("TOTAL_OVERS"),
            "extras": team_batting_stats.get("TOTAL_EXTRAS"),
            "batting": batting_rows,
            "bowling": bowling_rows,
            "fall_of_wickets": fow_out,
        })

    coin_toss = data.get("coinToss") or {}
    toss_winner_id = coin_toss.get("winningTeamId")
    toss_pref = coin_toss.get("preference")
    toss_result = None
    if toss_winner_id and toss_pref:
        winner = team_name(toss_winner_id)
        if winner:
            action = "bat" if toss_pref == "BAT" else "bowl"
            toss_result = f"{winner} won the toss and elected to {action}"

    return {
        "innings": innings_out,
        "toss": toss_result,
        "status": data.get("status"),
    }


async def _get_game_summary_rest(fixture_id: str) -> dict:
    raw = await _get(f"{BASE_URL}/v2/games/{fixture_id}/summary")
    data = raw.get("data") or {}
    if not data:
        return {"innings": []}
    return _parse_summary_rest(data)


_SCRAPE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
}


_playhq_graph_endpoint: str = ""


async def _get_graph_endpoint() -> str:
    """Return the PlayHQ GraphQL endpoint URL from /config.js (cached in module var)."""
    global _playhq_graph_endpoint
    if _playhq_graph_endpoint:
        return _playhq_graph_endpoint
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            r = await client.get("https://www.playhq.com/config.js", headers=_SCRAPE_HEADERS, timeout=10.0)
            r.raise_for_status()
        m = re.search(r'window\.__APP_CONFIG__\s*=\s*({.*?})\s*;', r.text, re.DOTALL)
        if m:
            config = json.loads(m.group(1))
            logger.info(f"PlayHQ __APP_CONFIG__ all values: { {k: v for k, v in config.items()} }")
            _playhq_graph_endpoint = config.get("GRAPH_ENDPOINT", "")
            logger.info(f"PlayHQ GRAPH_ENDPOINT = {_playhq_graph_endpoint!r}")
    except Exception as e:
        logger.warning(f"PlayHQ: failed to fetch config.js: {e}")
    return _playhq_graph_endpoint


_GQL_DISCOVER_GAME = """
query DiscoverGame($gameId: ID!) {
  discoverGame(gameID: $gameId) {
    id
    status { name value }
    result {
      home {
        score
        periods {
          period { label shortName value }
          type
          closureStatus
          statistics { count type { label value } }
        }
      }
      away {
        score
        periods {
          period { label shortName value }
          type
          closureStatus
          statistics { count type { label value } }
        }
      }
    }
    statistics {
      home {
        players {
          player {
            ... on DiscoverParticipant {
              id
              profile { id firstName lastName }
            }
            ... on DiscoverAnonymousParticipant { id name }
            ... on DiscoverRegularFillInPlayer { id name }
          }
          periodStatistics {
            period { label shortName value }
            type
            statistics { type { value label shortName } count details { value } }
            status
            displayOrder
          }
        }
      }
      away {
        players {
          player {
            ... on DiscoverParticipant {
              id
              profile { id firstName lastName }
            }
            ... on DiscoverAnonymousParticipant { id name }
            ... on DiscoverRegularFillInPlayer { id name }
          }
          periodStatistics {
            period { label shortName value }
            type
            statistics { type { value label shortName } count details { value } }
            status
            displayOrder
          }
        }
      }
      shared {
        period { label shortName value }
        type
        statistics { count type { value label } }
        side
        players { playerID teamID role }
        dismissalType
        displayOrder
      }
    }
    home {
      ... on DiscoverTeam { id name }
      ... on ProvisionalTeam { name }
    }
    away {
      ... on DiscoverTeam { id name }
      ... on ProvisionalTeam { name }
    }
  }
}
"""


async def _query_graphql_scorecard(fixture_id: str) -> dict:
    """Query the PlayHQ GraphQL endpoint for scorecard data using discoverGame."""
    endpoint = await _get_graph_endpoint()
    if not endpoint:
        logger.warning("PlayHQ: no GRAPH_ENDPOINT available")
        return {"innings": []}

    gql_headers = {
        "Content-Type": "application/json",
        "x-api-key": settings.playhq_api_key or PUBLIC_API_KEY,
        "x-phq-tenant": TENANT,
        "Origin": "https://www.playhq.com",
        "Referer": "https://www.playhq.com/",
    }

    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(
                endpoint,
                json={"query": _GQL_DISCOVER_GAME, "variables": {"gameId": fixture_id}},
                headers=gql_headers,
                timeout=TIMEOUT,
            )
            logger.info(f"PlayHQ discoverGame → {r.status_code}, body: {r.text[:1200]!r}")
            if r.status_code == 200:
                body = r.json()
                errors = body.get("errors")
                if errors:
                    logger.warning(f"PlayHQ discoverGame errors: {errors}")
                game_data = (body.get("data") or {}).get("discoverGame") or {}
                if game_data:
                    return _parse_scorecard_statistics(game_data)
        except Exception as e:
            logger.warning(f"PlayHQ discoverGame error: {e}")

    return {"innings": []}


async def get_game_appearances(fixture_id: str) -> tuple[list, list]:
    """Return (appearances, teams) from /v2/games/{id}/summary raw data.
    Cached for 24 hours — FINAL game appearances never change.
    """
    key = f"appearances:{fixture_id}"
    if key in _appearances_cache:
        ts, val = _appearances_cache[key]
        if time.time() - ts < APPEARANCES_CACHE_TTL:
            return val
    try:
        raw = await _get(f"{BASE_URL}/v2/games/{fixture_id}/summary")
        data = raw.get("data") or {}
        result = (data.get("appearances") or [], data.get("teams") or [])
    except Exception as e:
        logger.warning(f"PlayHQ: get_game_appearances failed for {fixture_id}: {e}")
        result = ([], [])
    _appearances_cache[key] = (time.time(), result)
    return result


async def get_fixture_scorecard(fixture_id: str, grade_id: str = "", game_url: str = "") -> dict:
    key = f"scorecard:{fixture_id}"
    if key in _scorecard_cache:
        ts, val = _scorecard_cache[key]
        if time.time() - ts < SCORECARD_CACHE_TTL:
            return val

    result: dict = {"innings": []}

    # Try REST summary API first — richer dismissal data
    try:
        rest_result = await _get_game_summary_rest(fixture_id)
        rest_innings = len(rest_result.get("innings", []))
        logger.info(f"REST scorecard for {fixture_id}: {rest_innings} innings")
        if rest_innings >= 2:
            # Both innings present — REST result is complete, return immediately
            _scorecard_cache[key] = (time.time(), rest_result)
            return rest_result
        if rest_innings == 1:
            result = rest_result  # keep as fallback; still try GraphQL
    except Exception as e:
        logger.warning(f"PlayHQ REST summary failed for {fixture_id}: {e}")

    # Try GraphQL — may have more innings than REST
    try:
        gql_result = await _query_graphql_scorecard(fixture_id)
        gql_innings = len(gql_result.get("innings", []))
        logger.info(f"GraphQL scorecard for {fixture_id}: {gql_innings} innings")
        if gql_innings > len(result.get("innings", [])):
            result = gql_result
    except Exception as e:
        logger.warning(f"PlayHQ GraphQL scorecard failed for {fixture_id}: {e}")

    _scorecard_cache[key] = (time.time(), result)
    return result
