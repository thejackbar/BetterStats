"""BetterScout — pricing tiers. Limits + upgrade messaging only for now: a
Scout Org's tier is assigned by BetterCricket staff (scripts/scout_set_tier.py),
not self-serve, because there is no Stripe checkout wired up here yet — see
CLAUDE.md's "Billing checkout — feature-flagged while it's built" note on the
main club product for the precedent this follows (ship the entitlement/limit
model now, wire real payment collection later).
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scout import ScoutOrg, ScoutWatchlist, ScoutWatchlistCard

DEFAULT_TIER = "starter"

# None = no cap.
TIER_LIMITS: dict[str, int | None] = {
    "starter": 25,
    "growth": 100,
    "unlimited": None,
}

TIER_LABELS: dict[str, str] = {
    "starter": "Starter",
    "growth": "Growth",
    "unlimited": "Unlimited",
}


def cap_for(tier: str | None) -> int | None:
    return TIER_LIMITS.get(tier or DEFAULT_TIER, TIER_LIMITS[DEFAULT_TIER])


def label_for(tier: str | None) -> str:
    return TIER_LABELS.get(tier or DEFAULT_TIER, TIER_LABELS[DEFAULT_TIER])


async def tracked_player_count(session: AsyncSession, scout_org_id: str) -> int:
    """Distinct players carrying a card on ANY of this org's watchlists —
    the same set services.scout_watchlist.list_tracked_players/
    scout_discovery.list_tracked_players return, just counted rather than
    listed."""
    res = await session.execute(
        select(func.count(func.distinct(ScoutWatchlistCard.scouted_player_id)))
        .join(ScoutWatchlist, ScoutWatchlist.id == ScoutWatchlistCard.watchlist_id)
        .where(ScoutWatchlist.scout_org_id == scout_org_id)
    )
    return res.scalar_one() or 0


async def usage_for(session: AsyncSession, org: ScoutOrg) -> dict:
    count = await tracked_player_count(session, org.id)
    cap = cap_for(org.tier)
    return {
        "tier": org.tier or DEFAULT_TIER,
        "tier_label": label_for(org.tier),
        "player_count": count,
        "player_cap": cap,
        "at_cap": cap is not None and count >= cap,
    }
