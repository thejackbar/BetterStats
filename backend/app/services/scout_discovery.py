"""BetterScout — player discovery.

Reuses BetterIQ's "scout any club" engine (services.iq_scout) wholesale for
the actual Cricket Australia data-fetching — that module's whole reason to
exist is scouting a club we've never played, using nothing but its public
Grassroots org GUID, which is exactly BetterScout's situation for every club.
The only thing it doesn't give us is somewhere to cache into: its own
caching (iq_opponent's opposition_dossiers table) has a NOT NULL FK to
organisations, which is precisely the club-data relationship BetterScout
must never have. So this module borrows the fetch logic and gives it a new,
platform-wide cache (scout_club_cache — see models/scout.py), then layers
two more concepts BetterIQ has no equivalent of: a durable per-person record
that survives past one search (ScoutedPlayer) and a per-tenant "this Scout
Org has added this player" fact (ScoutTrackedPlayer).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import async_session_maker
from app.models.scout import ScoutClubCache, ScoutWatchlist, ScoutWatchlistCard, ScoutedPlayer
from app.services import iq_scout, scout_watchlist
from app.services.iq_opponent import BUILD_STALE_AFTER, TTL, _BUILD_TASKS  # noqa: F401 — shared build-task bookkeeping

logger = logging.getLogger(__name__)

CAREER_VERSION = iq_scout.CAREER_VERSION  # cache freshness must track iq_scout's own schema version


# ─── club roster cache (platform-wide, no org scoping) ───────────────────────

async def _load_club_row(session: AsyncSession, org_guid: str) -> ScoutClubCache | None:
    res = await session.execute(
        select(ScoutClubCache).where(ScoutClubCache.club_org_guid == org_guid.lower())
    )
    return res.scalar_one_or_none()


async def _upsert_club_row(session: AsyncSession, org_guid: str, **fields) -> None:
    row = await _load_club_row(session, org_guid)
    if row is None:
        row = ScoutClubCache(club_org_guid=org_guid.lower())
        session.add(row)
    for k, v in fields.items():
        setattr(row, k, v)
    row.updated_at = datetime.now(timezone.utc)
    await session.commit()


async def _run_club_build(org_guid: str, club_name: str | None) -> None:
    async with async_session_maker() as session:
        try:
            payload = await iq_scout._build_career(org_guid, club_name)
            await _upsert_club_row(
                session, org_guid,
                club_name=(payload.get("org") or {}).get("name") or club_name,
                status="ready", payload=payload,
                built_at=datetime.now(timezone.utc), error=None,
            )
            logger.info(f"BetterScout: club roster built for {org_guid}")
        except Exception as e:  # never leave the row wedged at 'building'
            logger.exception(f"BetterScout: club roster build failed for {org_guid}: {e}")
            try:
                await _upsert_club_row(session, org_guid, status="error", error=str(e)[:500])
            except Exception:
                pass


async def get_or_start_club_roster(
    session: AsyncSession, org_guid: str, *, club_name: str | None = None, force: bool = False,
) -> dict:
    """Same build/poll contract as BetterIQ's get_or_start_dossier: a fresh
    ready cache returns the roster; otherwise mark building, launch the
    detached task, and report {status: 'building'} for the frontend to poll."""
    row = await _load_club_row(session, org_guid)
    now = datetime.now(timezone.utc)
    fresh = (
        row and row.status == "ready" and row.built_at and (now - row.built_at) < TTL
        and (row.payload or {}).get("schema_v") == CAREER_VERSION
    )
    if fresh and not force:
        return {"status": "ready", "cached": True, **(row.payload or {})}
    building = row and row.status == "building" and row.updated_at and (now - row.updated_at) < BUILD_STALE_AFTER
    if building and not force:
        return {"status": "building"}
    await _upsert_club_row(session, org_guid, club_name=club_name, status="building", error=None)
    task = asyncio.create_task(_run_club_build(org_guid, club_name))
    _BUILD_TASKS.add(task)
    task.add_done_callback(_BUILD_TASKS.discard)
    return {"status": "building"}


# ─── scouted players (durable, platform-wide) ─────────────────────────────────

def _slice_player(roster_payload: dict, player_id: str) -> dict | None:
    pid = (player_id or "").lower()
    return next(
        (p for p in roster_payload.get("players") or [] if (p.get("player_id") or "").lower() == pid),
        None,
    )


async def add_player(
    session: AsyncSession, scout_org_id: str, org_guid: str, player_id: str, club_name: str | None = None,
) -> dict:
    """Adds a real AU player found via club search. Requires the club roster
    cache to already be ready (the frontend only offers "Add" once a roster
    has loaded, so this is a real precondition, not a race to paper over)."""
    club_row = await _load_club_row(session, org_guid)
    if not club_row or club_row.status != "ready":
        raise ValueError("Club roster isn't ready yet — fetch the roster before adding a player.")
    sliced = _slice_player(club_row.payload or {}, player_id)
    if not sliced:
        raise ValueError("That player wasn't found in this club's roster.")

    res = await session.execute(
        select(ScoutedPlayer).where(ScoutedPlayer.grassroots_participant_id == player_id)
    )
    player = res.scalar_one_or_none()
    if player is None:
        player = ScoutedPlayer(
            source="au_grassroots",
            grassroots_participant_id=player_id,
            club_org_guid=org_guid.lower(),
            club_name=club_name or (club_row.payload or {}).get("org", {}).get("name"),
            name=sliced.get("name") or "Unknown",
        )
        session.add(player)
        await session.flush()
    player.stats_payload = sliced
    player.stats_built_at = datetime.now(timezone.utc)
    await session.flush()

    await scout_watchlist.ensure_card_on_default_watchlist(session, scout_org_id, player.id)
    await session.commit()
    return player_out(player)


async def add_manual_player(
    session: AsyncSession, scout_org_id: str, name: str, club_name: str | None = None, notes: str | None = None,
) -> dict:
    """A hand-entered player (UK/international, or anyone outside the AU
    Grassroots feed) — clearly marked source='manual', no automated stats."""
    player = ScoutedPlayer(source="manual", name=name, club_name=club_name, notes=notes)
    session.add(player)
    await session.flush()
    await scout_watchlist.ensure_card_on_default_watchlist(session, scout_org_id, player.id)
    await session.commit()
    return player_out(player)


async def refresh_player(session: AsyncSession, scouted_player_id: str) -> dict:
    player = await session.get(ScoutedPlayer, scouted_player_id)
    if not player:
        raise ValueError("Player not found.")
    if player.source != "au_grassroots" or not player.grassroots_participant_id or not player.club_org_guid:
        raise ValueError("This player has no automated data source to refresh from.")
    roster = await get_or_start_club_roster(session, player.club_org_guid, club_name=player.club_name, force=True)
    if roster.get("status") != "ready":
        return player_out(player) | {"refresh_status": roster.get("status")}
    sliced = _slice_player(roster, player.grassroots_participant_id)
    if sliced:
        player.stats_payload = sliced
        player.stats_built_at = datetime.now(timezone.utc)
        await session.commit()
    return player_out(player) | {"refresh_status": "ready"}


async def list_tracked_players(session: AsyncSession, scout_org_id: str) -> list[dict]:
    """Every distinct player with at least one card on any of this org's
    watchlists — the flat "My players" directory, now derived from the real
    watchlist model instead of the phase-2 bookmark table."""
    res = await session.execute(
        select(ScoutedPlayer)
        .join(ScoutWatchlistCard, ScoutWatchlistCard.scouted_player_id == ScoutedPlayer.id)
        .join(ScoutWatchlist, ScoutWatchlist.id == ScoutWatchlistCard.watchlist_id)
        .where(ScoutWatchlist.scout_org_id == scout_org_id)
        .distinct()
        .order_by(ScoutedPlayer.name)
    )
    return [player_out(p) for p in res.scalars().all()]


def player_out(p: ScoutedPlayer) -> dict:
    return {
        "id": str(p.id),
        "source": p.source,
        "name": p.name,
        "club_name": p.club_name,
        "grade_name": p.grade_name,
        "notes": p.notes,
        "stats": p.stats_payload,
        "stats_built_at": p.stats_built_at.isoformat() if p.stats_built_at else None,
    }
