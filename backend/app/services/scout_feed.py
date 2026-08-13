"""BetterScout — Player Name Search & Hot Form Feed.

Both read across ``scout_club_cache`` (see models/scout.py) — every club
roster BetterScout has ALREADY fetched, because a Scout Org (or someone at
another org) looked that club up on Discover. Deliberately NOT a live
whole-of-Australia crawl: there is no bulk index of every Cricket Australia
club anywhere in this codebase, and building one is out of scope here (the
public search API itself is the only club-discovery primitive available —
see services/playhq_client.search_organisations, which needs a name to
search on, not a blank sweep). So this is the honest, buildable reading of
"search every player"/"who's in form" — scoped to the platform's shared,
already-built cache, growing every time any Scout Org searches a new club on
Discover. Both endpoints report `clubs_scanned` so the frontend can say so
plainly rather than implying nationwide coverage.

Sibling of scout_overview.py's org-tracked form movers — hot_form_feed reuses
its movers_for_seasons() unchanged, just fed from a cached club's raw player
list instead of an org's own ScoutedPlayer rows.
"""
from __future__ import annotations

from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scout import ScoutClubCache, ScoutedPlayer, ScoutedPlayerClub
from app.services.scout_overview import movers_for_seasons

MAX_CLUBS_SCANNED = 80
SEARCH_RESULTS_LIMIT = 30
FEED_RESULTS_LIMIT = 30
MIN_QUERY_LEN = 2
NAME_MATCH_LIMIT = 15
NAME_MATCH_THRESHOLD = 0.72


async def _ready_caches(session: AsyncSession) -> list[ScoutClubCache]:
    """Most-recently-built first, capped — a club nobody has looked up in a
    long time is less likely to be what "who's in form right now" means,
    and capping keeps one request from walking every cached club forever as
    the platform-wide cache grows."""
    rows = (await session.execute(
        select(ScoutClubCache)
        .where(ScoutClubCache.status == "ready")
        .order_by(ScoutClubCache.built_at.desc().nullslast())
        .limit(MAX_CLUBS_SCANNED)
    )).scalars().all()
    return [r for r in rows if (r.payload or {}).get("players")]


async def _load_ready_cache(session: AsyncSession, club_org_guid: str) -> ScoutClubCache | None:
    """One specific ready cache row, regardless of the MAX_CLUBS_SCANNED
    recency cap _ready_caches applies — used by find_name_matches'
    only_club_guid path, where the scout named an exact club to check
    rather than asking "scan whatever's cached"."""
    row = (await session.execute(
        select(ScoutClubCache).where(
            ScoutClubCache.club_org_guid == (club_org_guid or "").lower(),
            ScoutClubCache.status == "ready",
        )
    )).scalar_one_or_none()
    return row if row and (row.payload or {}).get("players") else None


def _score_name(a: str, b: str) -> float:
    return SequenceMatcher(None, (a or "").strip().lower(), (b or "").strip().lower()).ratio()


async def find_name_matches(
    session: AsyncSession, name: str, *,
    exclude_club_guids: set[str] = frozenset(),
    only_club_guid: str | None = None,
    threshold: float = NAME_MATCH_THRESHOLD,
    limit: int = NAME_MATCH_LIMIT,
) -> list[dict]:
    """Is this player's name a close match to anyone in another cached
    club's roster? This is the whole engine behind "find this player at
    other clubs" — both the automatic post-add scan and the on-demand
    "search a specific club" flow (services.scout_discovery.suggest_other_clubs
    / search_other_club) call in here. Deliberately name-based, never a
    participant-GUID lookup: there is no reachable API for "every club this
    GUID has played at" (see ScoutedPlayerClub's own docstring), and a CA
    GUID isn't even guaranteed stable for one real person across clubs
    (CLAUDE.md documents this extensively for the main app). So this scores
    every candidate and returns them as SUGGESTIONS — never auto-linked,
    always a human confirm click via link_player_club, same identity-merge
    posture the rest of this codebase already takes.

    Scans a single specific club (only_club_guid — the scout named a club
    they suspect) or every ready-cached club (the automatic scan, reusing
    _ready_caches' same recency cap)."""
    name_norm = (name or "").strip()
    if not name_norm:
        return []
    if only_club_guid:
        cache = await _load_ready_cache(session, only_club_guid)
        caches = [cache] if cache else []
    else:
        caches = [c for c in await _ready_caches(session) if c.club_org_guid not in exclude_club_guids]

    scored: list[dict] = []
    for cache in caches:
        if cache.club_org_guid in exclude_club_guids:
            continue
        for p in (cache.payload or {}).get("players") or []:
            pname = p.get("name") or ""
            if not pname or not p.get("player_id"):
                continue
            confidence = _score_name(name_norm, pname)
            if confidence < threshold:
                continue
            scored.append({
                "club_org_guid": cache.club_org_guid,
                "club_name": cache.club_name,
                "player_id": p.get("player_id"),
                "name": pname,
                "confidence": round(confidence, 3),
                "totals": p.get("totals"),
            })
    scored.sort(key=lambda m: m["confidence"], reverse=True)
    return scored[:limit]


async def _tracked_lookup(session: AsyncSession, pairs: list[tuple[str, str]]) -> dict[tuple[str, str], str]:
    """Maps (club_org_guid, participant_id) -> scouted_player_id for every
    match already tracked platform-wide. Checks BOTH a player's original/
    primary identity (ScoutedPlayer.grassroots_participant_id — club-agnostic,
    a bare unique constraint) AND any club linked afterwards via
    ScoutedPlayerClub (see that model's docstring — a player tracked at more
    than one club, e.g. Spencer Green, must read as "Tracked" no matter which
    of his cached clubs you found him in, not only the one he was first
    added from)."""
    pairs = [(g, p) for g, p in pairs if g and p]
    if not pairs:
        return {}
    ids = {p for _, p in pairs}
    primary_rows = (await session.execute(
        select(ScoutedPlayer.grassroots_participant_id, ScoutedPlayer.id)
        .where(ScoutedPlayer.grassroots_participant_id.in_(ids))
    )).all()
    primary_by_id = {ext: str(sid) for ext, sid in primary_rows}
    club_rows = (await session.execute(
        select(ScoutedPlayerClub.club_org_guid, ScoutedPlayerClub.grassroots_participant_id, ScoutedPlayerClub.scouted_player_id)
        .where(ScoutedPlayerClub.grassroots_participant_id.in_(ids))
    )).all()
    club_by_pair = {(guid, ext): str(sid) for guid, ext, sid in club_rows}
    out: dict[tuple[str, str], str] = {}
    for guid, ext in pairs:
        sid = club_by_pair.get((guid, ext)) or primary_by_id.get(ext)
        if sid:
            out[(guid, ext)] = sid
    return out


async def search_players(session: AsyncSession, q: str) -> dict:
    """Substring name match across every cached club's player list. Returns
    the raw external `player_id` (a Cricket Australia participant GUID) on
    each hit, plus `scouted_player_id`/`tracked` for anyone this platform
    has already added somewhere — same overlay shape Discover's
    `annotate_tracking` uses, so the frontend card renders identically
    whichever screen it came from."""
    q_norm = (q or "").strip().lower()
    caches = await _ready_caches(session)
    if len(q_norm) < MIN_QUERY_LEN:
        return {"query": q_norm, "clubs_scanned": len(caches), "results": []}

    matches: list[dict] = []
    for cache in caches:
        for p in (cache.payload or {}).get("players") or []:
            name = p.get("name") or ""
            if q_norm not in name.lower():
                continue
            matches.append({
                "player_id": p.get("player_id"),
                "name": name,
                "club_org_guid": cache.club_org_guid,
                "club_name": cache.club_name,
                "totals": p.get("totals"),
            })

    tracked = await _tracked_lookup(session, [(m["club_org_guid"], m["player_id"]) for m in matches])
    for m in matches:
        sid = tracked.get((m["club_org_guid"], m["player_id"]))
        m["scouted_player_id"] = sid
        m["tracked"] = sid is not None

    matches.sort(key=lambda m: (m["totals"] or {}).get("runs") or 0, reverse=True)
    return {"query": q_norm, "clubs_scanned": len(caches), "results": matches[:SEARCH_RESULTS_LIMIT]}


def _latest_grade(seasons: list[dict] | None) -> str | None:
    for s in sorted(seasons or [], key=lambda s: s.get("year") or 0, reverse=True):
        if s.get("grade"):
            return s["grade"]
    return None


async def hot_form_feed(session: AsyncSession) -> dict:
    """Who's in form right now, across every cached club — the platform-wide
    mirror of Overview's own form_movers panel, which only looks at players
    this ONE org already tracks. Same "latest active season vs the two
    before it" math (movers_for_seasons), just walked over raw cache rows
    instead of ScoutedPlayer.stats_payload snapshots."""
    caches = await _ready_caches(session)
    movers: list[dict] = []
    for cache in caches:
        for p in (cache.payload or {}).get("players") or []:
            pid = p.get("player_id")
            if not pid:
                continue
            identity = {
                "id": pid,
                "name": p.get("name"),
                "club_name": cache.club_name,
                "grade_name": _latest_grade(p.get("seasons")),
            }
            for m in movers_for_seasons(identity, p.get("seasons")):
                m["club_org_guid"] = cache.club_org_guid
                movers.append(m)

    tracked = await _tracked_lookup(session, [(m["club_org_guid"], m["id"]) for m in movers])
    for m in movers:
        sid = tracked.get((m["club_org_guid"], m["id"]))
        m["scouted_player_id"] = sid
        m["tracked"] = sid is not None

    movers.sort(key=lambda m: m["magnitude"], reverse=True)
    return {"clubs_scanned": len(caches), "movers": movers[:FEED_RESULTS_LIMIT]}
