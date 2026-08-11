"""Grassroots /scores/* client — Cricket Australia's pre-PlayHQ match data.

Key unauthenticated endpoints on grassrootsapiproxy.cricket.com.au:
  /scores/grades/{grade_id}/matches          — all matches in a grade (primary discovery)
  /scores/teams/{team_id}/matches            — all matches a team played (fallback)
  /scores/matches/{id}?responseModifier=includeScorecard — full scorecard

Data reaches back to at least 1975. Post-migration PlayHQ games return 204 —
that signals "not mine" cleanly, no de-dup needed.

participantId values in the response correspond directly to our players.id
column (both are Grassroots GUIDs), so no extra mapping table is required.
"""
import asyncio
import logging
import time
from datetime import date
from typing import Optional

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)

BASE_URL = settings.playhq_base_url  # grassrootsapiproxy.cricket.com.au
TIMEOUT = 20.0
_SEMAPHORE = asyncio.Semaphore(6)
_JSCONFIG = "eccn:true"
_HEADERS = {
    "User-Agent": "BetterStats/1.0",
    "Accept": "application/json",
    "Origin": "https://play.cricket.com.au",
    "Referer": "https://play.cricket.com.au/",
}

_grade_matches_cache: dict[str, list] = {}  # grade_id -> matches
_matches_cache: dict[str, list] = {}  # team_id -> matches
_scorecard_cache: dict[str, tuple] = {}  # match_id -> (fetched_at, scorecard | None)
_ladder_cache: dict[str, tuple] = {}  # grade_id -> (fetched_at, data | None)
_LADDER_TTL = 3600  # ladders move ~weekly; an hour keeps the proxy happy
# A scorecard can be corrected by a club scorer after the fact (observed live:
# a match caught mid-edit returned an innings with totals but an empty batting
# array, and that incomplete snapshot then sat cached indefinitely — this
# endpoint is now the primary source for the live match page, so an unbounded
# cache pins a bad snapshot until the process restarts). 15 minutes keeps the
# proxy happy for the common case (an old, settled match) while letting a
# recently-edited scorecard catch up within one reload.
_SCORECARD_TTL = 900
# Plain match record (team lists / officials), cached separately from the
# scorecard: a published pre-game lineup is edited right up to the first ball,
# so this is deliberately short.
_match_cache: dict[str, tuple] = {}  # match_id -> (fetched_at, detail | None)
_MATCH_TTL = 300


async def _get(url: str, params: dict | None = None) -> httpx.Response:
    async with _SEMAPHORE:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            p = {"jsconfig": _JSCONFIG}
            if params:
                p.update(params)
            r = await client.get(url, params=p, headers=_HEADERS)
            if r.status_code == 429:
                await asyncio.sleep(1.0)
                r = await client.get(url, params=p, headers=_HEADERS)
            return r


async def get_grade_matches(grade_id: str, *, force: bool = False) -> list[dict]:
    """Return all matches in a grade.

    Uses /scores/grades/{grade_id}/matches — unauthenticated, works for all
    seasons including pre-2000 data. Preferred over team-based discovery
    because it doesn't require fixturesladders (which has no records for
    old seasons).

    `force=True` bypasses the in-process cache (used by the hard-refresh
    pre-flight probe so a previously-poisoned empty entry can't hide a
    recovered upstream).

    Only a genuine 200-with-no-matches is cached as empty. A non-200 or an
    exception is a *transient* failure — we return [] but DON'T cache it, so a
    later call (or a retry) actually re-fetches instead of being stuck on a
    poisoned empty for the life of the process. This matters because the whole
    game-level sync reads "no matches" as "this grade has no games", so a
    cached upstream blip would silently look like a club with no history.
    """
    if not force and grade_id in _grade_matches_cache:
        return _grade_matches_cache[grade_id]
    try:
        r = await _get(f"{BASE_URL}/scores/grades/{grade_id}/matches")
        if r.status_code != 200:
            logger.debug(f"GR scores: /grades/{grade_id}/matches → {r.status_code}")
            return []
        data = r.json()
        matches = data.get("matches") or []
        _grade_matches_cache[grade_id] = matches
        return matches
    except Exception as e:
        logger.warning(f"GR scores: /grades/{grade_id}/matches failed: {e}")
        return []


async def get_grade_ladder(grade_id: str) -> Optional[dict]:
    """Return the live ladder/standings for a grade.

    Uses /fixturesladders/grades/{grade_id}/ladders — unauthenticated, 200 OK
    for current grades (grade_id is the same UUID as grades.id in our DB).
    Returns the raw JSON dict, or None on any non-200 / failure. Cached for an
    hour. The response *shape* is normalised by the caller, defensively.
    """
    now = time.time()
    hit = _ladder_cache.get(grade_id)
    if hit and now - hit[0] < _LADDER_TTL:
        return hit[1]
    try:
        r = await _get(f"{BASE_URL}/fixturesladders/grades/{grade_id}/ladders")
        if r.status_code != 200:
            logger.debug(f"GR ladders: /grades/{grade_id}/ladders → {r.status_code}")
            _ladder_cache[grade_id] = (now, None)
            return None
        data = r.json()
        _ladder_cache[grade_id] = (now, data)
        return data
    except Exception as e:
        logger.warning(f"GR ladders: /grades/{grade_id}/ladders failed: {e}")
        return None


async def get_team_matches(team_id: str) -> list[dict]:
    """Return all matches a team played in its season.

    Note: each team in Grassroots is bound to one season — so this returns
    that season's matches only. Fan out across all teams to get full history.
    """
    if team_id in _matches_cache:
        return _matches_cache[team_id]
    try:
        r = await _get(f"{BASE_URL}/scores/teams/{team_id}/matches")
        if r.status_code != 200:
            logger.debug(f"GR scores: /teams/{team_id}/matches → {r.status_code}")
            _matches_cache[team_id] = []
            return []
        data = r.json()
        matches = data.get("matches") or []
        _matches_cache[team_id] = matches
        return matches
    except Exception as e:
        logger.warning(f"GR scores: /teams/{team_id}/matches failed: {e}")
        return []


_balls_cache: dict[str, Optional[dict]] = {}  # match_id -> ball-by-ball or None


async def get_match_balls(match_id: str) -> Optional[dict]:
    """Return ball-by-ball data for a match, or None if not available.

    Uses /scores/matches/{id}/balls — unauthenticated, returns
    ``{teams:[{id, owningOrganisation:{id,name}, ...}], innings:[{battingTeamId,
    balls:[{overNumber, runsBat, wides, noBalls, legByes, byes, penaltyRuns,
    dismissedParticipantId, ...}]}]}`` for live-scored matches (the scorecard
    flags these ``isBallByBall: true``). Most historical games are scorecard-only
    and 403/empty here — we treat any non-200 or empty ``innings`` as "no ball
    data" so callers can simply skip them.
    """
    if match_id in _balls_cache:
        return _balls_cache[match_id]
    try:
        r = await _get(f"{BASE_URL}/scores/matches/{match_id}/balls")
        if r.status_code != 200:
            _balls_cache[match_id] = None
            return None
        data = r.json()
        if not data.get("innings"):
            _balls_cache[match_id] = None
            return None
        _balls_cache[match_id] = data
        return data
    except Exception as e:
        logger.warning(f"GR balls: /matches/{match_id}/balls failed: {e}")
        _balls_cache[match_id] = None
        return None


async def get_match_scorecard(match_id: str, *, force: bool = False) -> Optional[dict]:
    """Return full scorecard for a match, or None if not in Grassroots (204).

    The 204 case isn't an error — it means this match is a post-migration
    PlayHQ-only game that Grassroots doesn't know about. The caller should
    skip it and let the PlayHQ sync path handle it.

    Cached for `_SCORECARD_TTL` (see its comment for why this isn't
    unbounded). `force=True` bypasses the cache entirely.
    """
    now = time.time()
    hit = _scorecard_cache.get(match_id)
    if not force and hit and now - hit[0] < _SCORECARD_TTL:
        return hit[1]
    try:
        r = await _get(f"{BASE_URL}/scores/matches/{match_id}", params={"responseModifier": "includeScorecard"})
        if r.status_code == 204:
            _scorecard_cache[match_id] = (now, None)
            return None
        if r.status_code != 200:
            logger.warning(f"GR scores: /matches/{match_id} → {r.status_code}: {r.text[:200]}")
            # Transient failure — don't cache it, so the next request actually
            # retries instead of being stuck on a `None` for the full TTL
            # (same reasoning as get_grade_matches's non-200 handling above).
            if hit:
                return hit[1]
            return None
        data = r.json()
        if _scorecard_looks_incomplete(data, prior=hit[1] if hit else None):
            # Caught mid-edit — a scorer correcting the match on Grassroots'
            # side can momentarily save an innings with its totals intact but
            # its per-row batting wiped, or reset the whole match to no
            # innings at all. Don't pin that snapshot; return it for this one
            # call (or the last good one, if we have it) but let the next
            # request try again instead of caching a broken card for the
            # full TTL.
            logger.warning(f"GR scores: /matches/{match_id} looks incomplete — not caching")
            return hit[1] if hit else data
        _scorecard_cache[match_id] = (now, data)
        return data
    except Exception as e:
        logger.warning(f"GR scores: /matches/{match_id} failed: {e}")
        if hit:
            return hit[1]
        return None


async def get_match_detail(match_id: str, *, force: bool = False) -> Optional[dict]:
    """Return the plain match record — teams, published team lists, officials.

    ``/scores/matches/{id}`` WITHOUT ``responseModifier=includeScorecard``. The
    payload carries ``teams[].players[]`` (each ``{participantId, name,
    shortName, roles}``, roles being Captain / Wicket Keeper),
    ``teams[].nonPlayingMembers[]`` (coach, manager) and ``officials``
    (umpires/scorers) — i.e. the **team list**, which clubs publish on
    play.cricket.com.au ahead of the game. Verified live against an in-season
    winter fixture: an UPCOMING match returns its selected side as soon as the
    club publishes it (and an empty ``players`` list for a side that hasn't).

    Kept separate from ``get_match_scorecard`` on purpose: this is a smaller
    payload with a much shorter TTL, because a pre-game team list changes right
    up to the first ball, whereas a scorecard is settled once the match ends.
    204 (a PlayHQ-namespace id Grassroots doesn't own) returns None.
    """
    now = time.time()
    hit = _match_cache.get(match_id)
    if not force and hit and now - hit[0] < _MATCH_TTL:
        return hit[1]
    try:
        r = await _get(f"{BASE_URL}/scores/matches/{match_id}")
        if r.status_code == 204:
            _match_cache[match_id] = (now, None)
            return None
        if r.status_code != 200:
            logger.warning(f"GR scores: /matches/{match_id} (detail) → {r.status_code}")
            # Don't cache a transient failure — same reasoning as the scorecard
            # and grade-match fetches above.
            return hit[1] if hit else None
        data = r.json()
        _match_cache[match_id] = (now, data)
        return data
    except Exception as e:
        logger.warning(f"GR scores: /matches/{match_id} (detail) failed: {e}")
        return hit[1] if hit else None


async def get_matches_detail(match_ids: list[str]) -> dict[str, dict]:
    """``get_match_detail`` across several matches concurrently, keyed by id.

    Bounded by the module semaphore (6) and the per-match cache, so a page that
    lists a round's worth of fixtures costs one burst of requests per TTL.
    """
    if not match_ids:
        return {}
    results = await asyncio.gather(
        *[get_match_detail(m) for m in match_ids], return_exceptions=True
    )
    out: dict[str, dict] = {}
    for mid, res in zip(match_ids, results):
        if isinstance(res, dict):
            out[mid] = res
        elif isinstance(res, Exception):
            logger.warning(f"GR scores: match detail {mid} failed: {res}")
    return out


def _scorecard_looks_incomplete(data: dict, prior: Optional[dict] = None) -> bool:
    """True when this response looks like a bad in-flight snapshot rather than
    a real state of the match — the signature of catching Grassroots
    mid-correction, when a scorer's edit is saved in two steps and we land on
    the gap between them.

    Two signals, neither of which alone was enough:
    - An innings reports real totals but has no batting rows to back them up
      (covers a wipe that leaves the scoreline behind).
    - Comparing against the last good response (`prior`): an innings, or the
      whole match, that HAD batting rows/innings before and now has none.
      Needed because a full reset can zero the totals too (0 runs, 0
      wickets), which the totals-only check above can't tell apart from an
      innings that simply hasn't started yet — but a genuine "hasn't started"
      innings was never in `prior` with rows in the first place, so the
      regression check only fires on an actual loss of data.
    """
    innings = data.get("innings") or []
    prior_innings = {i.get("id"): i for i in ((prior or {}).get("innings") or []) if i.get("id")}

    if prior_innings and not innings:
        return True

    for inn in innings:
        has_totals = bool(inn.get("numberOfWicketsFallen") or inn.get("runsScored"))
        has_batting = bool(inn.get("batting") or [])
        if has_totals and not has_batting:
            return True
        prior_inn = prior_innings.get(inn.get("id"))
        if prior_inn and (prior_inn.get("batting") or []) and not has_batting:
            return True
    return False


# ── Upcoming fixtures ────────────────────────────────────────────────────────
# CA's restricted /fixturesladders/.../fixtures endpoints are 403 with the public
# key, but /scores/grades/{id}/matches returns EVERY match in a grade keyed by a
# status enum (verified live against an in-season winter comp):
#   0=UPCOMING  2=LIVE  3=COMPLETED  4=ABANDONED  5=NO RESULT
# Upcoming fixtures are simply the rows whose status is pre-completion and whose
# scheduled date is today-or-later. grade_id MUST be the raw CA grade GUID
# (grades.grassroots_id, COALESCE'd with id for legacy rows).
_FIXTURE_STATUS_UPCOMING = 0
_FIXTURE_STATUS_LIVE = 2
_FIXTURE_STATUS_COMPLETED = 3


async def get_grade_results(grade_id: str, *, since: Optional[str] = None) -> list[dict]:
    """Completed matches for one grade, normalised (the results mirror of
    ``get_grade_fixtures``).

    Reuses ``get_grade_matches`` (same in-process cache). Returns
    ``{id, home_team, away_team, played_at, round, venue, grade_id}`` for
    matches in the terminal COMPLETED state (statusId 3). Scores/result are NOT
    in the match list — the caller fetches ``get_match_scorecard(id)`` for those,
    exactly like the single-scorecard import. ``since`` (YYYY-MM-DD) drops
    anything older, keeping the scorecard fan-out bounded to recent rounds.
    """
    matches = await get_grade_matches(grade_id)
    out: list[dict] = []
    for m in matches:
        try:
            sid = int(m.get("statusId"))
        except (TypeError, ValueError):
            continue
        if sid != _FIXTURE_STATUS_COMPLETED:
            continue
        sched = (m.get("matchSchedule") or [{}])
        dt = (sched[0].get("startDateTime") if sched else "") or ""
        day = dt[:10]
        if not day:
            continue
        if since and day < since:
            continue
        teams = m.get("teams") or []
        home = next((t.get("displayName") for t in teams if t.get("isHome")), None)
        away = next((t.get("displayName") for t in teams if not t.get("isHome")), None)
        out.append({
            "id": m.get("id"),
            "home_team": home,
            "away_team": away,
            "played_at": day,
            "round": (m.get("round") or {}).get("name"),
            "venue": (m.get("venue") or {}).get("name"),
            "grade_id": grade_id,
        })
    return out


async def get_grade_fixtures(grade_id: str, *, include_live: bool = True) -> list[dict]:
    """Upcoming (and optionally live) fixtures for one grade, normalised.

    Reuses ``get_grade_matches`` (same in-process cache). Returns a list of
    ``{id, home_team, away_team, played_at, time, status, round, venue, grade_id,
    home_org_id, away_org_id, home_logo, away_logo}`` dicts for matches that
    haven't reached a terminal state and are scheduled today-or-later.

    ``*_org_id``/``*_logo`` come from each team's ``owningOrganisation`` — the
    actual club, which holds the crest (a grade "team" is often a sponsor
    name, not the club). Same field the scorecard/lineups team-logo lookups
    already read (see the CLAUDE.md "Club crests, live from Grassroots"
    note) — pulled here too since a fixtures/results round pull is otherwise
    the one surface with no crest at all.
    """
    matches = await get_grade_matches(grade_id)
    today = date.today().isoformat()
    keep = {_FIXTURE_STATUS_UPCOMING}
    if include_live:
        keep.add(_FIXTURE_STATUS_LIVE)
    out: list[dict] = []
    for m in matches:
        try:
            sid = int(m.get("statusId"))
        except (TypeError, ValueError):
            continue
        if sid not in keep:
            continue
        sched = (m.get("matchSchedule") or [{}])
        dt = (sched[0].get("startDateTime") if sched else "") or ""
        day = dt[:10]
        if not day or day < today:
            continue
        teams = m.get("teams") or []
        home_t = next((t for t in teams if t.get("isHome")), None)
        away_t = next((t for t in teams if not t.get("isHome")), None)
        home_org = (home_t or {}).get("owningOrganisation") or {}
        away_org = (away_t or {}).get("owningOrganisation") or {}
        out.append({
            "id": m.get("id"),
            "home_team": (home_t or {}).get("displayName"),
            "away_team": (away_t or {}).get("displayName"),
            "played_at": day,
            "time": dt[11:16] if len(dt) >= 16 else None,
            "status": "LIVE" if sid == _FIXTURE_STATUS_LIVE else "UPCOMING",
            "round": (m.get("round") or {}).get("name"),
            "venue": (m.get("venue") or {}).get("name"),
            "grade_id": grade_id,
            "home_org_id": home_org.get("id"),
            "away_org_id": away_org.get("id"),
            "home_logo": home_org.get("logoUrl"),
            "away_logo": away_org.get("logoUrl"),
        })
    return out


async def get_grades_fixtures(
    grade_ids: list[str],
    match_keys: Optional[list[str]] = None,
    *,
    include_live: bool = True,
) -> list[dict]:
    """Aggregate ``get_grade_fixtures`` across grades, de-duplicated and sorted.

    ``match_keys`` (lowercased club name keys, e.g. from ``club_match_keys``)
    optionally restricts results to fixtures involving that club (substring match
    on either side). Grades are fetched concurrently; the underlying per-grade
    cache makes repeat calls cheap.
    """
    results = await asyncio.gather(
        *[get_grade_fixtures(g, include_live=include_live) for g in grade_ids],
        return_exceptions=True,
    )
    out: list[dict] = []
    seen: set = set()
    for r in results:
        if not isinstance(r, list):
            if isinstance(r, Exception):
                logger.warning(f"GR fixtures: grade fetch failed: {r}")
            continue
        for fx in r:
            fid = fx.get("id")
            if not fid or fid in seen:
                continue
            if match_keys:
                hl = (fx.get("home_team") or "").lower()
                al = (fx.get("away_team") or "").lower()
                if not any(k in hl or k in al for k in match_keys):
                    continue
            seen.add(fid)
            out.append(fx)
    out.sort(key=lambda x: (x["played_at"], x.get("time") or ""))
    return out
