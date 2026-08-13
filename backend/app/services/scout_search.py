"""BetterScout — one search bar for clubs AND players.

Discover (club search) and Player search were two separate tools; the
play.cricket.com.au reference this was built against has one always-visible
search box in its header instead. Backed by services/scout_live_search.py —
the REAL API behind play.cricket.com.au's own header search, found by
inspecting a live club page's search widget and its network call (see that
module's docstring for exactly how). Genuinely national coverage: a club or
player nobody has looked up on BetterScout before still resolves, which the
old cache-scan approach could never do.

`tracked`/`scouted_player_id` on a player result is still resolved against
OUR OWN database — the live search only knows what PlayHQ knows, not which
of its players a Scout Org has added here.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scout import ScoutedPlayer, ScoutedPlayerClub
from app.services import scout_live_search

MIN_QUERY_LEN = 2
CLUBS_LIMIT = 8
PLAYERS_LIMIT = 8


async def _tracked_by_canonical_id(session: AsyncSession, canonical_ids: list[str]) -> dict[str, str]:
    """Maps a live-search player's canonical `id` -> scouted_player_id, for
    anyone this platform has tracked under that id (as their original/
    primary identity, OR as one of their other linked clubs — see
    ScoutedPlayerClub). Unlike scout_feed._tracked_lookup (which is
    club-pair-scoped because a raw per-club cache id isn't guaranteed
    globally unique), the live search's `id` IS PlayHQ's own canonical
    cross-club identity, so a bare id lookup is enough here."""
    ids = [i for i in canonical_ids if i]
    if not ids:
        return {}
    primary_rows = (await session.execute(
        select(ScoutedPlayer.grassroots_participant_id, ScoutedPlayer.id)
        .where(ScoutedPlayer.grassroots_participant_id.in_(ids))
    )).all()
    out = {ext: str(sid) for ext, sid in primary_rows}
    club_rows = (await session.execute(
        select(ScoutedPlayerClub.grassroots_participant_id, ScoutedPlayerClub.scouted_player_id)
        .where(ScoutedPlayerClub.grassroots_participant_id.in_(ids))
    )).all()
    for ext, sid in club_rows:
        out.setdefault(ext, str(sid))
    return out


async def unified_search(session: AsyncSession, q: str) -> dict:
    q_norm = (q or "").strip()
    if len(q_norm) < MIN_QUERY_LEN:
        return {"query": q_norm, "clubs": [], "players": []}

    result = await scout_live_search.search_playcommunity(q_norm)
    clubs = result["clubs"][:CLUBS_LIMIT]
    players = result["players"][:PLAYERS_LIMIT]

    tracked = await _tracked_by_canonical_id(session, [p["id"] for p in players])
    out_players = []
    for p in players:
        orgs = p["organisations"]
        sid = tracked.get(p["id"])
        out_players.append({
            "player_id": p["id"],
            "name": p["name"],
            "club_org_guid": orgs[0]["id"] if orgs else None,
            "club_name": orgs[0]["name"] if orgs else None,
            "club_count": len(orgs),
            "scouted_player_id": sid,
            "tracked": sid is not None,
        })

    return {"query": q_norm, "clubs": clubs, "players": out_players}
