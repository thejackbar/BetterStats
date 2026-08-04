"""PlayHQ AFL GraphQL client.

Two public, unauthenticated endpoints (both verified live — see
docs/afl-playhq-data-source.md for the full investigation):

- https://api.playhq.com/graphql   — the "discover" API. Header ``tenant: afl``
  (lowercase; the uppercase enum name fails with a different error).
- https://spectator.playhq.com/graphql — the play-by-play event feed. Header
  ``X-PHQ-Tenant: afl`` (a DIFFERENT header name from the discover API).

Politeness mirrors the cricket grassroots client: a shared semaphore bounds
concurrency, short in-process TTL caches absorb repeat reads, and callers are
expected to sync incrementally (skip already-final games) rather than
re-pulling the world.
"""
import asyncio
import logging
import time
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

DISCOVER_URL = "https://api.playhq.com/graphql"
SPECTATOR_URL = "https://spectator.playhq.com/graphql"
TENANT = "afl"

_HEADERS_DISCOVER = {
    "Content-Type": "application/json",
    "tenant": TENANT,
    "Origin": "https://www.playhq.com",
    "Referer": "https://www.playhq.com/",
}
_HEADERS_SPECTATOR = {
    "Content-Type": "application/json",
    "X-PHQ-Tenant": TENANT,
    "Origin": "https://www.playhq.com",
    "Referer": "https://www.playhq.com/",
}

_semaphore = asyncio.Semaphore(6)
_TIMEOUT = httpx.Timeout(30.0)

# (key) -> (expires_at, payload). Small caches: they only need to absorb
# repeat reads within one request burst / sync run.
_cache: dict[str, tuple[float, Any]] = {}
_GAME_TTL = 15 * 60       # a finished game's stats settle quickly
_FIXTURE_TTL = 10 * 60    # grade fixtures move on scoring days
_DISCOVER_TTL = 60 * 60   # org/season/team topology barely moves


class PlayHQError(Exception):
    pass


def _cache_get(key: str):
    hit = _cache.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    return None


def _cache_put(key: str, value: Any, ttl: float) -> None:
    _cache[key] = (time.monotonic() + ttl, value)
    # Opportunistic sweep so a long-lived process doesn't accrete entries.
    if len(_cache) > 2000:
        now = time.monotonic()
        for k in [k for k, (exp, _) in _cache.items() if exp <= now]:
            _cache.pop(k, None)


def clear_cache() -> None:
    _cache.clear()


_MAX_ATTEMPTS = 5
# CloudFront in front of api.playhq.com sometimes hard-blocks a request with
# a plain "Request blocked" 403 (a WAF/rate-reputation response, not an
# application-level auth failure — verified live: identical body on both the
# discover and spectator hosts, for a request built exactly like a normal
# browser call). Observed to be a TEMPORARY per-IP flag that clears after a
# short cooldown (sync history: one run's afl_sync succeeded, ~30min later an
# afl_full's very first call 403'd) — so unlike a genuine 4xx (bad query,
# missing var), a 403 here is worth retrying with a real backoff rather than
# failing the whole sync run instantly.
_RETRYABLE_STATUS = {403, 429}


async def _post(url: str, headers: dict, operation: str, query: str,
                variables: dict) -> dict:
    payload = {"operationName": operation, "variables": variables, "query": query}
    async with _semaphore:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            for attempt in range(_MAX_ATTEMPTS):
                last_attempt = attempt == _MAX_ATTEMPTS - 1
                try:
                    resp = await client.post(url, json=payload, headers=headers)
                    resp.raise_for_status()
                    body = resp.json()
                    break
                except httpx.HTTPStatusError as exc:
                    status = exc.response.status_code
                    if status in _RETRYABLE_STATUS and not last_attempt:
                        # Longer, growing waits than a genuine transient
                        # error gets — a WAF cooldown is measured in tens of
                        # seconds, not the 2/4/6s used below.
                        wait = 10 * (2 ** attempt)
                        logger.warning(
                            "%s: got %s from PlayHQ (likely a CloudFront WAF "
                            "block, not our request) — retrying in %ss (attempt %s/%s)",
                            operation, status, wait, attempt + 1, _MAX_ATTEMPTS)
                        await asyncio.sleep(wait)
                        continue
                    # Any other 4xx is a bad request on our side — retrying
                    # it is pointless and hammers the API for nothing.
                    if status in _RETRYABLE_STATUS:
                        raise PlayHQError(
                            f"{operation}: still blocked by PlayHQ (HTTP {status}) after "
                            f"{_MAX_ATTEMPTS} attempts — this is very likely an upstream "
                            f"CloudFront rate/reputation block on this server's IP, not a "
                            f"bug in the request. Wait a while and retry.") from exc
                    if 400 <= status < 500 or last_attempt:
                        raise PlayHQError(f"{operation}: {exc}") from exc
                    await asyncio.sleep(2 * (attempt + 1))
                except (httpx.HTTPError, ValueError) as exc:
                    if last_attempt:
                        raise PlayHQError(f"{operation}: {exc}") from exc
                    await asyncio.sleep(2 * (attempt + 1))
    if body.get("errors"):
        # Partial data with errors is possible; only treat as fatal when
        # there's no usable data at all.
        if not body.get("data"):
            raise PlayHQError(f"{operation}: {body['errors']}")
        logger.warning("PlayHQ %s returned partial errors: %s", operation, body["errors"][:2])
    return body.get("data") or {}


async def _discover(operation: str, query: str, variables: dict) -> dict:
    return await _post(DISCOVER_URL, _HEADERS_DISCOVER, operation, query, variables)


async def _spectator(operation: str, query: str, variables: dict) -> dict:
    return await _post(SPECTATOR_URL, _HEADERS_SPECTATOR, operation, query, variables)


# ─── Queries (extracted from PlayHQ's own web bundle; see the data-source doc) ─

_Q_COMPETITIONS = """
query discoverCompetitions($organisationID: ID!, $organisationCode: String!) {
  discoverCompetitions(organisationID: $organisationID) {
    id
    name
    seasons(organisationID: $organisationID) {
      id
      name
      startDate
      endDate
      status { name value }
    }
    organisation { id name }
  }
  discoverOrganisation(code: $organisationCode) {
    id
    type
    name
    email
    contactNumber
    websiteUrl
    logo { sizes { url dimensions { width height } } }
  }
}
"""

_Q_TEAMS = """
query teams($seasonId: ID!, $organisationId: ID!) {
  discoverTeams(filter: {seasonID: $seasonId, organisationID: $organisationId}) {
    id
    name
    gender { name value }
    ageGroup { name value }
    grade { id name }
  }
}
"""

_Q_GRADE_FIXTURE = """
query gradeAllRounds($gradeID: ID!) {
  discoverGradeFixture(gradeID: $gradeID) {
    id
    name
    abbreviatedName
    isFinalsRound
    games {
      id
      home {
        ... on ProvisionalTeam { name }
        ... on DiscoverTeam { id name organisation { id name } }
      }
      away {
        ... on ProvisionalTeam { name }
        ... on DiscoverTeam { id name organisation { id name } }
      }
      status { name value }
      date
      allocation { time court { name venue { name suburb } } }
    }
  }
}
"""

_Q_GAME_VIEW = """
query gameView($gameId: ID!) {
  discoverGame(gameID: $gameId) {
    id
    away { ...TeamFragment }
    home { ...TeamFragment }
    result {
      winner { name value }
      outcome { name value }
      home {
        score
        outcome { name value }
        statistics { count type { value } }
        gameOutcomeDescription
      }
      away {
        score
        outcome { name value }
        statistics { count type { value } }
      }
    }
    status { name value }
    round {
      id
      name
      abbreviatedName
      isFinalsRound
      grade {
        id
        name
        season { id name competition { id name organisation { id name } } }
      }
    }
    date
    allocation {
      time
      court { id abbreviatedName name venue { id name suburb address state } }
    }
    statistics {
      home { ...AflTeamStats }
      away { ...AflTeamStats }
    }
    publishLineup
  }
}

fragment TeamFragment on DiscoverPossibleTeam {
  ... on ProvisionalTeam { name }
  ... on DiscoverTeam {
    id
    name
    logo { sizes { url dimensions { width height } } }
    organisation { id name type }
  }
}

fragment AflTeamStats on DiscoverGameTeamStatistics {
  players {
    playerNumber
    player {
      ... on DiscoverParticipant { id profile { id firstName lastName } }
      ... on DiscoverParticipantFillInPlayer { id profile { id firstName lastName } }
      ... on DiscoverGamePermitFillInPlayer { id profile { id firstName lastName } }
      ... on DiscoverRegularFillInPlayer { id name }
      ... on DiscoverAnonymousParticipant { id name }
    }
    statistics { count type { value } }
    playerPoints
    captain { name shortName }
  }
  statistics { count type { value } }
  periods {
    period { value }
    overtimeSequenceNo
    statistics { type { value } count }
  }
  bestPlayers {
    participant {
      ... on DiscoverParticipant { id profile { id firstName lastName } }
      ... on DiscoverAnonymousParticipant { name }
    }
    ranking
  }
}
"""

_Q_GAME_EVENTS = """
query gameEventsSpectator($gameID: ID!, $after: Int, $filters: EventFilter, $order: EventOrder) {
  gameEvents(gameID: $gameID, after: $after, filters: $filters, order: $order) {
    id
    title
    description
    visible
    sportEventStamp
    eventSection
    timestamp
    previousEventID
    side
    period
    ... on ScoreEvent {
      progressiveScore
      score
    }
  }
}
"""


async def get_org_competitions(org_id: str, force: bool = False) -> dict:
    """Competitions + seasons the org fields teams in, plus the org's own
    profile (name/logo/contact). Keys: 'competitions', 'organisation'."""
    key = f"comps:{org_id}"
    if not force and (hit := _cache_get(key)) is not None:
        return hit
    data = await _discover("discoverCompetitions", _Q_COMPETITIONS,
                           {"organisationID": org_id, "organisationCode": org_id})
    out = {
        "competitions": data.get("discoverCompetitions") or [],
        "organisation": data.get("discoverOrganisation"),
    }
    _cache_put(key, out, _DISCOVER_TTL)
    return out


async def get_org_teams(season_id: str, org_id: str, force: bool = False) -> list[dict]:
    """The org's team entries in one season, each carrying its grade."""
    key = f"teams:{season_id}:{org_id}"
    if not force and (hit := _cache_get(key)) is not None:
        return hit
    data = await _discover("teams", _Q_TEAMS,
                           {"seasonId": season_id, "organisationId": org_id})
    out = data.get("discoverTeams") or []
    _cache_put(key, out, _DISCOVER_TTL)
    return out


async def get_grade_fixture(grade_id: str, force: bool = False) -> list[dict]:
    """Every round (with its games) in a grade."""
    key = f"fixture:{grade_id}"
    if not force and (hit := _cache_get(key)) is not None:
        return hit
    data = await _discover("gradeAllRounds", _Q_GRADE_FIXTURE, {"gradeID": grade_id})
    out = data.get("discoverGradeFixture") or []
    _cache_put(key, out, _FIXTURE_TTL)
    return out


async def get_game(game_id: str, force: bool = False) -> Optional[dict]:
    """Full game view: result, per-quarter scores, both team's player stat
    lines, best players, venue."""
    key = f"game:{game_id}"
    if not force and (hit := _cache_get(key)) is not None:
        return hit
    data = await _discover("gameView", _Q_GAME_VIEW, {"gameId": game_id})
    out = data.get("discoverGame")
    if out is not None:
        _cache_put(key, out, _GAME_TTL)
    return out


async def get_game_events(game_id: str, force: bool = False) -> list[dict]:
    """Play-by-play scoring feed from the spectator endpoint. Returns [] when
    the game was never live-scored (a normal state, not an error)."""
    key = f"events:{game_id}"
    if not force and (hit := _cache_get(key)) is not None:
        return hit
    try:
        data = await _spectator("gameEventsSpectator", _Q_GAME_EVENTS, {"gameID": game_id})
    except PlayHQError as exc:
        # The event feed is enrichment, not core data — a spectator-side
        # failure must never fail a sync.
        logger.warning("spectator events unavailable for %s: %s", game_id, exc)
        return []
    out = data.get("gameEvents") or []
    _cache_put(key, out, _GAME_TTL)
    return out
