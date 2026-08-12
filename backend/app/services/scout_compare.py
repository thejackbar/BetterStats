"""BetterScout — the Compare screen. Up to 5 tracked players, stats side by
side, an optional RECRUITING tab (internal-only), and an optional read-only
public share link (ScoutSharedComparison).
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scout import ScoutOrg, ScoutSharedComparison, ScoutWatchlist, ScoutWatchlistCard, ScoutedPlayer
from app.services import scout_discovery, scout_watchlist

MAX_PLAYERS = 5

# Never leaves the org, on a share link or otherwise beyond this screen's own
# RECRUITING tab — same five fields scout_watchlist._SHARED_CARD_FIELDS and
# the player profile's RecruitingPanel both guard.
RECRUITING_FIELDS = (
    "visa_status", "transfer_preference", "availability_window", "fee_expectations", "agent_contact",
)


async def _tracked_player_ids(session: AsyncSession, scout_org_id: str) -> set[str]:
    res = await session.execute(
        select(ScoutWatchlistCard.scouted_player_id)
        .join(ScoutWatchlist, ScoutWatchlist.id == ScoutWatchlistCard.watchlist_id)
        .where(ScoutWatchlist.scout_org_id == scout_org_id)
    )
    return {str(r) for r in res.scalars().all()}


async def _player_row(session: AsyncSession, scout_org_id: str, player: ScoutedPlayer, include_recruiting: bool) -> dict:
    out = await scout_discovery.player_out(session, player)
    cards = await scout_watchlist.cards_for_player(session, scout_org_id, str(player.id))
    # "Edit the current board's card" (per profile) has no single answer
    # across several watchlists here, so Compare reads the earliest-added
    # card (cards_for_player's own order) as this player's primary one —
    # same convention a scout sees first when opening their profile.
    primary = cards[0] if cards else None
    out["role"] = primary.get("role") if primary else None
    out["batting_hand"] = primary.get("batting_hand") if primary else None
    out["bowling_action"] = primary.get("bowling_action") if primary else None
    out["bowling_type"] = primary.get("bowling_type") if primary else None
    out["tags"] = (primary.get("tags") if primary else None) or []
    if include_recruiting:
        out["recruiting"] = {f: (primary.get(f) if primary else None) for f in RECRUITING_FIELDS}
    return out


async def build_comparison(session: AsyncSession, scout_org_id: str, player_ids: list[str]) -> dict:
    ids = list(dict.fromkeys(player_ids))[:MAX_PLAYERS]  # de-dupe, cap, preserve order
    tracked = await _tracked_player_ids(session, scout_org_id)
    players = []
    for pid in ids:
        if pid not in tracked:
            continue
        player = await session.get(ScoutedPlayer, pid)
        if not player:
            continue
        players.append(await _player_row(session, scout_org_id, player, include_recruiting=True))
    return {"players": players}


async def create_share_link(session: AsyncSession, scout_org_id: str, player_ids: list[str]) -> dict:
    ids = list(dict.fromkeys(player_ids))[:MAX_PLAYERS]
    tracked = await _tracked_player_ids(session, scout_org_id)
    ids = [pid for pid in ids if pid in tracked]
    if len(ids) < 2:
        raise ValueError("Pick at least 2 tracked players before sharing a comparison.")

    org = await session.get(ScoutOrg, scout_org_id)
    expires_at = None
    if org and org.share_expiry_days is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=org.share_expiry_days)

    row = ScoutSharedComparison(
        scout_org_id=scout_org_id, player_ids=ids,
        token=secrets.token_urlsafe(24), expires_at=expires_at,
    )
    session.add(row)
    await session.commit()
    return {"share_token": row.token}


async def get_shared_comparison(session: AsyncSession, token: str) -> dict | None:
    row = (await session.execute(
        select(ScoutSharedComparison).where(ScoutSharedComparison.token == token)
    )).scalar_one_or_none()
    if not row:
        return None
    if row.expires_at is not None:
        expires_at = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_at:
            return None

    org = await session.get(ScoutOrg, row.scout_org_id)
    players = []
    for pid in row.player_ids or []:
        player = await session.get(ScoutedPlayer, pid)
        if not player:
            continue
        out = await _player_row(session, str(row.scout_org_id), player, include_recruiting=False)
        if org and not org.share_include_tags:
            out["tags"] = []
        players.append(out)
    return {"players": players}
