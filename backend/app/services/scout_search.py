"""BetterScout — one search bar for clubs AND players.

Discover (club search) and Player search were two separate tools; the
play.cricket.com.au reference this was built against has one always-visible
search box in its header instead. There is no reachable API to mirror
play.cricket.com.au's own backend search (probed live against the Grassroots
proxy and the Pulselive endpoints its own page config names — both refuse),
so this is a BetterScout-native combined search: fans out to the two
existing, already-working search primitives — playhq_client.search_organisations
(clubs) and scout_feed.search_players (players, reused wholesale, same
cached-club scope the standalone Player search screen already uses) — and
merges them into one typeahead-shaped result.
"""
from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import playhq_client, scout_feed

MIN_QUERY_LEN = 2
CLUBS_LIMIT = 8
PLAYERS_LIMIT = 8


async def unified_search(session: AsyncSession, q: str) -> dict:
    q_norm = (q or "").strip()
    if len(q_norm) < MIN_QUERY_LEN:
        return {"query": q_norm, "clubs": [], "players": [], "clubs_scanned": 0}

    clubs_task = playhq_client.search_organisations(q_norm)
    players_task = scout_feed.search_players(session, q_norm)
    club_results, player_result = await asyncio.gather(clubs_task, players_task, return_exceptions=True)

    clubs = []
    if not isinstance(club_results, Exception):
        clubs = [
            {"id": org.get("id"), "name": org.get("name")}
            for org in club_results
            if org.get("id") and org.get("name")
        ][:CLUBS_LIMIT]

    players: list[dict] = []
    clubs_scanned = 0
    if not isinstance(player_result, Exception):
        players = (player_result.get("results") or [])[:PLAYERS_LIMIT]
        clubs_scanned = player_result.get("clubs_scanned", 0)

    return {"query": q_norm, "clubs": clubs, "players": players, "clubs_scanned": clubs_scanned}
