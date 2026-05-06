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
    data = await _get(f"{BASE_URL}/v1/organisations/{playhq_id}/seasons")
    return _set_cached(key, data.get("data", []))


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
    if games:
        g = games[0]
        logger.info(f"PlayHQ game top-level keys: {list(g.keys())}")
        for c in (g.get("competitors") or [])[:1]:
            logger.info(f"PlayHQ competitor keys: {list(c.keys())}")
            for inn in (c.get("innings") or [])[:1]:
                logger.info(f"PlayHQ competitor innings keys: {list(inn.keys())}")
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
    """Fetch all recent games for an org across its most recent seasons."""
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

    recent_seasons = unique_seasons[:12]
    if not recent_seasons:
        return []
    logger.info(f"PlayHQ: fetching {len(recent_seasons)} seasons for {playhq_id}: {[s.get('name') for s in recent_seasons]}")

    # Fetch grades for all seasons concurrently (semaphore limits rate)
    grade_results = await asyncio.gather(
        *[get_season_grades(s["id"]) for s in recent_seasons],
        return_exceptions=True,
    )

    grade_season_pairs: list[tuple[dict, str]] = []
    for i, grades in enumerate(grade_results):
        if isinstance(grades, list):
            season_name = recent_seasons[i].get("name", "")
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


def _dismissal_text(bat: dict) -> tuple[str, str]:
    """Return (how_out_label, bowler_name) from a batting entry."""
    status = bat.get("batterStatus") or bat.get("status") or ""
    dismissal = bat.get("dismissal") or {}
    dtype = (dismissal.get("dismissalType") or dismissal.get("type") or status).upper()

    if "NOT_OUT" in dtype or status == "NOT_OUT":
        return "Not Out", ""

    bowled_by = (dismissal.get("bowler") or {}).get("name") or ""
    fielder = (dismissal.get("fielder") or {}).get("name") or ""
    catcher = (dismissal.get("catcher") or {}).get("name") or ""
    fielder_name = fielder or catcher

    if "CAUGHT" in dtype:
        how = f"c {fielder_name}" if fielder_name else "c"
        return how, f"b {bowled_by}" if bowled_by else ""
    if "BOWLED" in dtype:
        return "", f"b {bowled_by}" if bowled_by else ""
    if "LBW" in dtype:
        return "lbw", f"b {bowled_by}" if bowled_by else ""
    if "RUN_OUT" in dtype or "RUNOUT" in dtype:
        return "run out", ""
    if "STUMPED" in dtype:
        return f"st {fielder_name}" if fielder_name else "st", f"b {bowled_by}" if bowled_by else ""
    if "HIT_WICKET" in dtype:
        return "hit wicket", f"b {bowled_by}" if bowled_by else ""
    if dtype:
        return dtype.lower().replace("_", " "), f"b {bowled_by}" if bowled_by else ""
    return "", ""


def _parse_scorecard(data: dict) -> dict:
    fixture = data.get("data") or data
    innings_raw = fixture.get("innings") or []
    innings_out = []

    for inn in innings_raw:
        batting_team = (inn.get("battingTeam") or inn.get("homeTeam") or {}).get("name", "")
        extras = inn.get("extras") or {}
        extras_total = extras.get("total") or extras.get("byes", 0) + extras.get("legByes", 0) + extras.get("wides", 0) + extras.get("noBalls", 0) + extras.get("penalties", 0)

        batting_rows = []
        for bat in (inn.get("batting") or []):
            player_name = (bat.get("player") or bat.get("batter") or {}).get("name", "")
            how_out, bowled_by = _dismissal_text(bat)
            status = bat.get("batterStatus") or bat.get("status") or ""
            not_out = "NOT_OUT" in status.upper() or how_out == "Not Out"
            batting_rows.append({
                "name": player_name,
                "how_out": how_out,
                "bowled_by": bowled_by,
                "runs": bat.get("runs"),
                "balls": bat.get("balls") or bat.get("ballsFaced"),
                "fours": bat.get("fours"),
                "sixes": bat.get("sixes"),
                "not_out": not_out,
            })

        bowling_rows = []
        for bowl in (inn.get("bowling") or []):
            player_name = (bowl.get("player") or bowl.get("bowler") or {}).get("name", "")
            overs_val = bowl.get("overs") or bowl.get("oversBowled")
            bowling_rows.append({
                "name": player_name,
                "overs": overs_val,
                "maidens": bowl.get("maidens"),
                "runs": bowl.get("runs") or bowl.get("runsConceded"),
                "wickets": bowl.get("wickets"),
                "wides": bowl.get("wides"),
                "no_balls": bowl.get("noBalls"),
            })

        innings_out.append({
            "innings_number": inn.get("inningsNumber", len(innings_out) + 1),
            "batting_team": batting_team,
            "total_runs": inn.get("totalRuns") or inn.get("runs"),
            "total_wickets": inn.get("totalWickets") or inn.get("wickets"),
            "overs": inn.get("overs") or inn.get("oversBowled"),
            "extras": extras_total,
            "batting": batting_rows,
            "bowling": bowling_rows,
        })

    return {"innings": innings_out}


_SCRAPE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
}


async def _scrape_playhq_page(game_url: str, fixture_id: str) -> dict:
    """Fetch the PlayHQ scorecard page and extract innings data."""
    scorecard_url = game_url.rstrip("/")
    if not scorecard_url.endswith("/scorecard"):
        scorecard_url += "/scorecard"

    async with httpx.AsyncClient(follow_redirects=True) as client:
        r = await client.get(scorecard_url, headers=_SCRAPE_HEADERS, timeout=20.0)
        r.raise_for_status()

    html = r.text

    # Log a snippet to understand the page structure
    script_tags = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    logger.info(f"PlayHQ page for {fixture_id}: {len(html)} bytes, {len(script_tags)} script tags")
    # Log first 500 chars to understand SPA framework
    logger.info(f"PlayHQ page head snippet: {html[:500]!r}")

    # Try __NEXT_DATA__ (Next.js SSR)
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
    if m:
        next_data = json.loads(m.group(1))
        page_props = next_data.get("props", {}).get("pageProps", {})
        logger.info(f"PlayHQ __NEXT_DATA__ pageProps keys for {fixture_id}: {list(page_props.keys())}")
        game_data = (
            page_props.get("game") or page_props.get("fixture")
            or page_props.get("match") or page_props.get("data") or {}
        )
        if game_data:
            logger.info(f"PlayHQ game_data keys: {list(game_data.keys())}")
        return _parse_scorecard(game_data)

    # Try other common embedded JSON patterns
    for pattern_name, pattern in [
        ("__INITIAL_STATE__", r'window\.__INITIAL_STATE__\s*=\s*({.*?});'),
        ("__PRELOADED_STATE__", r'window\.__PRELOADED_STATE__\s*=\s*({.*?});'),
        ("__APP_STATE__", r'window\.__APP_STATE__\s*=\s*({.*?});'),
        ("nuxt_data", r'window\.__NUXT__\s*=\s*\((.*?)\)'),
    ]:
        m2 = re.search(pattern, html, re.DOTALL)
        if m2:
            logger.info(f"PlayHQ: found {pattern_name} for {fixture_id}")
            try:
                state = json.loads(m2.group(1))
                logger.info(f"PlayHQ {pattern_name} top-level keys: {list(state.keys()) if isinstance(state, dict) else type(state)}")
            except Exception:
                logger.info(f"PlayHQ: {pattern_name} found but not valid JSON")
            break

    # Log any JSON-like script content for debugging
    for tag in script_tags[:5]:
        tag = tag.strip()
        if tag.startswith('{') or tag.startswith('['):
            logger.info(f"PlayHQ inline JSON script (first 200): {tag[:200]!r}")

    logger.warning(f"PlayHQ: no embedded scorecard data found for {fixture_id} at {scorecard_url}")
    return {"innings": []}


async def get_fixture_scorecard(fixture_id: str, grade_id: str = "", game_url: str = "") -> dict:
    key = f"scorecard:{fixture_id}"
    if key in _scorecard_cache:
        ts, val = _scorecard_cache[key]
        if time.time() - ts < SCORECARD_CACHE_TTL:
            return val

    result: dict = {"innings": []}

    if game_url:
        try:
            result = await _scrape_playhq_page(game_url, fixture_id)
        except Exception as e:
            logger.warning(f"PlayHQ page scrape failed for {fixture_id}: {e}")

    _scorecard_cache[key] = (time.time(), result)
    return result
