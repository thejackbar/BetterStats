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

PUBLIC_API_KEY = "6e02cae8-e3f0-4846-b024-4072716f1c60"


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
        meta = data.get("meta") or {}
        # JSON:API cursor pagination
        if links.get("next"):
            page += 1
        # Offset pagination guard: stop if batch is smaller than requested size
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
    data = await _get(f"{BASE_URL}/v1/seasons/{season_id}/grades")
    return _set_cached(key, data.get("data", []))


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


async def get_org_games(playhq_id: str, org_name: str) -> list:
    """Fetch all games for an org across all available seasons."""
    if not settings.playhq_api_key or not playhq_id:
        return []

    try:
        seasons = await get_org_seasons(playhq_id)
    except Exception as e:
        logger.warning(f"PlayHQ: failed to get seasons for {playhq_id}: {e}")
        return []

    # Deduplicate seasons by ID (API can return same season for different competitions)
    seen_ids: set[str] = set()
    unique_seasons = []
    for s in seasons:
        sid = s.get("id")
        if sid and sid not in seen_ids:
            seen_ids.add(sid)
            unique_seasons.append(s)

    if not unique_seasons:
        return []
    logger.info(f"PlayHQ: fetching {len(unique_seasons)} seasons for {playhq_id}: {[s.get('name') for s in unique_seasons]}")

    # Fetch grades for all seasons concurrently (semaphore limits rate)
    grade_results = await asyncio.gather(
        *[get_season_grades(s["id"]) for s in unique_seasons],
        return_exceptions=True,
    )

    grade_season_pairs: list[tuple[dict, str]] = []
    for i, grades in enumerate(grade_results):
        if isinstance(grades, list):
            season_name = unique_seasons[i].get("name", "")
            for g in grades:
                grade_season_pairs.append((g, season_name))

    if not grade_season_pairs:
        return []

    # Fetch games for all grades concurrently (semaphore limits rate)
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

    return all_games


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



async def get_fixture_scorecard(fixture_id: str, grade_id: str = "", game_url: str = "") -> dict:
    key = f"scorecard:{fixture_id}"
    if key in _scorecard_cache:
        ts, val = _scorecard_cache[key]
        if time.time() - ts < SCORECARD_CACHE_TTL:
            return val

    result: dict = {"innings": []}

    try:
        result = await _query_graphql_scorecard(fixture_id)
    except Exception as e:
        logger.warning(f"PlayHQ scorecard fetch failed for {fixture_id}: {e}")

    _scorecard_cache[key] = (time.time(), result)
    return result
