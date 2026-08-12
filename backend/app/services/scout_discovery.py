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

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Player, async_session_maker
from app.models.scout import ScoutClubCache, ScoutWatchlist, ScoutWatchlistCard, ScoutedPlayer
from app.services import iq_scout, scout_internal_link, scout_watchlist
from app.services.iq_opponent import BUILD_STALE_AFTER, TTL, _BUILD_TASKS  # noqa: F401 — shared build-task bookkeeping

logger = logging.getLogger(__name__)

# This module's OWN roster-payload contract version — independent of
# iq_scout.CAREER_VERSION and scout_internal_link.INTERNAL_SCHEMA_VERSION.
# Two different builders (iq_scout._build_career's public-API path,
# scout_internal_link.build_internal_career's internal path) can produce this
# payload; freshness has to track the SHAPE this module's own consumers read
# (Discover/Profile/Overview), not either builder's own version number.
# _run_club_build stamps every payload with this value before storing it.
# Bump whenever either builder's output shape changes in a way that matters
# here.
ROSTER_SCHEMA_VERSION = 1


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
            # If this club is already onboarded on BetterCricket, our own
            # per-game tables are richer than the public aggregate API (exact
            # figures, real grade-per-season, dateable matches) and free to
            # read — see services/scout_internal_link.py. Falls through to
            # the existing public-API build for every other club.
            internal_org = await scout_internal_link.resolve_internal_org(session, org_guid)
            if internal_org:
                payload = await scout_internal_link.build_internal_career(internal_org, session)
            else:
                payload = await iq_scout._build_career(org_guid, club_name)
            payload["schema_v"] = ROSTER_SCHEMA_VERSION
            await _upsert_club_row(
                session, org_guid,
                club_name=(payload.get("org") or {}).get("name") or club_name,
                status="ready", payload=payload,
                built_at=datetime.now(timezone.utc), error=None,
            )
            logger.info(
                f"BetterScout: club roster built for {org_guid} "
                f"(source={payload.get('source', 'external')})"
            )
        except Exception as e:  # never leave the row wedged at 'building'
            logger.exception(f"BetterScout: club roster build failed for {org_guid}: {e}")
            try:
                await _upsert_club_row(session, org_guid, status="error", error=str(e)[:500])
            except Exception:
                pass


async def refresh_club_and_apply(org_guid: str, club_name: str | None, scouted_player_ids: list[str]) -> int:
    """The scheduled-refresh job's one entry point (jobs/scheduler.py's
    refresh_scout_players): rebuild a club ONCE, then stamp every one of the
    given ScoutedPlayer rows from that single build. Deliberately NOT N
    calls to refresh_player() — that function's own force=True kicks off a
    fresh background rebuild every time it's called, so ten tracked players
    (across however many orgs) at one club would otherwise trigger ten
    redundant rebuilds hitting the same rate-limited CA proxy. This awaits
    _run_club_build directly (a plain async function, not the fire-and-poll
    task _run_club_build's own caller normally launches) since a scheduled
    job can afford to wait, unlike a live HTTP request."""
    await _run_club_build(org_guid, club_name)
    async with async_session_maker() as session:
        row = await _load_club_row(session, org_guid)
        if not row or row.status != "ready":
            return 0
        n = 0
        for pid in scouted_player_ids:
            player = await session.get(ScoutedPlayer, pid)
            if not player or not player.grassroots_participant_id:
                continue
            sliced = _slice_player(row.payload or {}, player.grassroots_participant_id)
            if not sliced:
                continue
            player.stats_payload = sliced
            player.stats_built_at = datetime.now(timezone.utc)
            _stamp_internal_link(player, sliced, org_guid)
            n += 1
        if n:
            await session.commit()
        return n


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
        and (row.payload or {}).get("schema_v") == ROSTER_SCHEMA_VERSION
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


async def annotate_tracking(session: AsyncSession, scout_org_id: str, roster: dict) -> dict:
    """Overlays this ORG's own tracking state onto a roster payload — never
    baked into the cache itself (ScoutClubCache is platform-wide, shared by
    every Scout Org, so which players THIS org has already added is private
    per-request state, not part of the cached build). Adds `tracked` and
    `watchlist_count` to every player row that resolves to an existing
    ScoutedPlayer; untouched players get `watchlist_count: 0`."""
    if roster.get("status") != "ready" or not roster.get("players"):
        return roster
    ext_ids = [p["player_id"] for p in roster["players"] if p.get("player_id")]
    if not ext_ids:
        return roster
    rows = (await session.execute(
        select(ScoutedPlayer.id, ScoutedPlayer.grassroots_participant_id)
        .where(ScoutedPlayer.grassroots_participant_id.in_(ext_ids))
    )).all()
    scouted_id_by_ext = {ext: str(sid) for sid, ext in rows}
    count_by_sid: dict[str, int] = {}
    if scouted_id_by_ext:
        counts = (await session.execute(
            select(ScoutWatchlistCard.scouted_player_id, func.count())
            .join(ScoutWatchlist, ScoutWatchlist.id == ScoutWatchlistCard.watchlist_id)
            .where(
                ScoutWatchlist.scout_org_id == scout_org_id,
                ScoutWatchlistCard.scouted_player_id.in_(scouted_id_by_ext.values()),
            )
            .group_by(ScoutWatchlistCard.scouted_player_id)
        )).all()
        count_by_sid = {str(sid): n for sid, n in counts}
    for p in roster["players"]:
        sid = scouted_id_by_ext.get(p.get("player_id"))
        p["scouted_player_id"] = sid
        p["watchlist_count"] = count_by_sid.get(sid, 0) if sid else 0
    return roster


def _stamp_internal_link(player: ScoutedPlayer, sliced: dict, org_guid: str) -> None:
    """Record which real BetterCricket org/player this scouted player
    resolved to, when the roster that sliced them was built via
    scout_internal_link (see that module's docstring on why these two
    columns carry no ForeignKey). Cleared back to None when a later refresh
    no longer resolves internally (e.g. the club was archived) — a stale
    link is worse than none, since the next refresh would silently trust it."""
    internal_pid = sliced.get("internal_player_id")
    player.internal_org_id = org_guid if internal_pid else None
    player.internal_player_id = internal_pid


async def add_player(
    session: AsyncSession, scout_org_id: str, org_guid: str, player_id: str, club_name: str | None = None,
    watchlist_id: str | None = None,
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
    _stamp_internal_link(player, sliced, org_guid)
    await session.flush()

    await scout_watchlist.ensure_card_on_watchlist(session, scout_org_id, player.id, watchlist_id)
    await session.commit()
    return await player_out(session, player)


async def add_manual_player(
    session: AsyncSession, scout_org_id: str, name: str, club_name: str | None = None, notes: str | None = None,
    watchlist_id: str | None = None,
) -> dict:
    """A hand-entered player (UK/international, or anyone outside the AU
    Grassroots feed) — clearly marked source='manual', no automated stats."""
    player = ScoutedPlayer(source="manual", name=name, club_name=club_name, notes=notes)
    session.add(player)
    await session.flush()
    await scout_watchlist.ensure_card_on_watchlist(session, scout_org_id, player.id, watchlist_id)
    await session.commit()
    return await player_out(session, player)


async def refresh_player(session: AsyncSession, scouted_player_id: str) -> dict:
    player = await session.get(ScoutedPlayer, scouted_player_id)
    if not player:
        raise ValueError("Player not found.")
    if player.source != "au_grassroots" or not player.grassroots_participant_id or not player.club_org_guid:
        raise ValueError("This player has no automated data source to refresh from.")
    roster = await get_or_start_club_roster(session, player.club_org_guid, club_name=player.club_name, force=True)
    if roster.get("status") != "ready":
        return await player_out(session, player) | {"refresh_status": roster.get("status")}
    sliced = _slice_player(roster, player.grassroots_participant_id)
    if sliced:
        player.stats_payload = sliced
        player.stats_built_at = datetime.now(timezone.utc)
        _stamp_internal_link(player, sliced, player.club_org_guid)
        await session.commit()
    return await player_out(session, player) | {"refresh_status": "ready"}


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
    return [await player_out(session, p) for p in res.scalars().all()]


async def player_out(session: AsyncSession, p: ScoutedPlayer) -> dict:
    photo_url = None
    if p.internal_player_id:
        # A player already on BetterCricket via their own club: their real
        # uploaded photo (if any) wins over a scout-uploaded one — it's the
        # canonical image, not a stand-in. See services/scout_internal_link.py.
        linked = await session.get(Player, p.internal_player_id)
        photo_url = linked.photo_url if linked else None
    if not photo_url and p.photo_data:
        photo_url = f"/api/images/scouted-players/{p.id}/photo"
    return {
        "id": str(p.id),
        "source": p.source,
        "name": p.name,
        "club_name": p.club_name,
        "grade_name": p.grade_name,
        "notes": p.notes,
        "photo_url": photo_url,
        "stats": p.stats_payload,
        "stats_built_at": p.stats_built_at.isoformat() if p.stats_built_at else None,
        # True once this player resolved to a real BetterCricket club/player
        # (see scout_internal_link) — the stats above are exact per-game
        # figures rather than CA's public season aggregates, and Milestones
        # can date a crossing to a real match instead of only a season.
        "internal_link": p.internal_player_id is not None,
    }
