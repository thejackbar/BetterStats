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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scout import ScoutClubCache, ScoutedPlayer
from app.services.scout_overview import movers_for_seasons

MAX_CLUBS_SCANNED = 80
SEARCH_RESULTS_LIMIT = 30
FEED_RESULTS_LIMIT = 30
MIN_QUERY_LEN = 2


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


async def _tracked_lookup(session: AsyncSession, ext_ids: list[str]) -> dict[str, str]:
    ext_ids = [e for e in ext_ids if e]
    if not ext_ids:
        return {}
    rows = (await session.execute(
        select(ScoutedPlayer.grassroots_participant_id, ScoutedPlayer.id)
        .where(ScoutedPlayer.grassroots_participant_id.in_(ext_ids))
    )).all()
    return {ext: str(sid) for ext, sid in rows}


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

    tracked = await _tracked_lookup(session, [m["player_id"] for m in matches])
    for m in matches:
        sid = tracked.get(m["player_id"])
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

    tracked = await _tracked_lookup(session, [m["id"] for m in movers])
    for m in movers:
        sid = tracked.get(m["id"])
        m["scouted_player_id"] = sid
        m["tracked"] = sid is not None

    movers.sort(key=lambda m: m["magnitude"], reverse=True)
    return {"clubs_scanned": len(caches), "movers": movers[:FEED_RESULTS_LIMIT]}
