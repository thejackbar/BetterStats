"""Module entitlements — the Better ecosystem's per-club module gating.

The Better platform is sold as **Good / Better / Best** tier bundles. Each tier
unlocks a set of modules; a club may also hold à-la-carte ``module_overrides``
that grant individual modules on top of its tier.

This module is the single source of truth for:
  - the module registry (keys + display metadata),
  - the tier → modules map,
  - resolving a club's effective entitlements, and
  - the ``require_module()`` FastAPI dependency that gates module routes.

**Core (BetterStats)** — data ingestion, reconciled stats and the public site —
is always on for every club and is intentionally *not* a gateable module: it's
the product every club gets.

Keep the registry + tier map in sync with ``frontend/src/lib/modules.js``.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


# ─── Module registry ─────────────────────────────────────────────────────────

MODULE_SELECT = "select"     # BetterSelect  — availability + smart team selection
MODULE_SOCIALS = "socials"   # BetterSocials — auto social posts
MODULE_FEES = "fees"         # BetterFees    — fee schedules + payment tracking
MODULE_IQ = "iq"             # BetterIQ      — AI + stats deep-dive (not built yet)

ALL_MODULES = (MODULE_SELECT, MODULE_SOCIALS, MODULE_FEES, MODULE_IQ)

# Display metadata, surfaced to the admin module-tile dashboard. ``built`` flags
# whether the module exists yet — BetterIQ is greenfield (master-plan Phase 4),
# so its tile shows "coming soon" rather than opening.
MODULE_META: dict[str, dict] = {
    MODULE_SELECT: {"name": "BetterSelect", "blurb": "Availability & smart team selection", "built": True},
    MODULE_SOCIALS: {"name": "BetterSocials", "blurb": "Auto-post lineups, scorecards & milestones", "built": True},
    MODULE_FEES: {"name": "BetterFees", "blurb": "Fee schedules & payment tracking", "built": True},
    MODULE_IQ: {"name": "BetterIQ", "blurb": "AI + stats deep-dive — opposition scouting & selection analysis", "built": False},
}


# ─── Tiers ───────────────────────────────────────────────────────────────────

TIER_GOOD = "good"
TIER_BETTER = "better"
TIER_BEST = "best"

ALL_TIERS = (TIER_GOOD, TIER_BETTER, TIER_BEST)
DEFAULT_TIER = TIER_GOOD

# Good = Core only · Better = + Select + Socials · Best = everything.
TIER_MODULES: dict[str, frozenset[str]] = {
    TIER_GOOD: frozenset(),
    TIER_BETTER: frozenset({MODULE_SELECT, MODULE_SOCIALS}),
    TIER_BEST: frozenset({MODULE_SELECT, MODULE_SOCIALS, MODULE_FEES, MODULE_IQ}),
}

# The lowest tier each module appears in — drives the upsell ("Upgrade to …").
MODULE_REQUIRED_TIER: dict[str, str] = {
    MODULE_SELECT: TIER_BETTER,
    MODULE_SOCIALS: TIER_BETTER,
    MODULE_FEES: TIER_BEST,
    MODULE_IQ: TIER_BEST,
}


# ─── Subscription status (Phase 3) ───────────────────────────────────────────
# Reflects the manual-invoicing state and gates entitlement. active/trial/
# past_due keep modules live (past_due is a grace period — don't cut a club off
# the moment an invoice is late); paused/cancelled fall back to Core only.

STATUS_ACTIVE = "active"
STATUS_TRIAL = "trial"
STATUS_PAST_DUE = "past_due"
STATUS_PAUSED = "paused"
STATUS_CANCELLED = "cancelled"

ALL_STATUSES = (STATUS_ACTIVE, STATUS_TRIAL, STATUS_PAST_DUE, STATUS_PAUSED, STATUS_CANCELLED)
ACTIVE_STATUSES = frozenset({STATUS_ACTIVE, STATUS_TRIAL, STATUS_PAST_DUE})
DEFAULT_STATUS = STATUS_ACTIVE

ALL_BILLING_CYCLES = ("monthly", "annual")


def org_subscription_active(org) -> bool:
    if org is None:
        return False
    return (getattr(org, "subscription_status", None) or DEFAULT_STATUS) in ACTIVE_STATUSES


# ─── Entitlement resolution ──────────────────────────────────────────────────

def tier_modules(tier: str | None) -> frozenset[str]:
    return TIER_MODULES.get(tier or DEFAULT_TIER, frozenset())


def org_entitled_modules(org) -> set[str]:
    """The set of module keys a club may use right now.

    = the modules its tier bundles, plus any à-la-carte overrides — but only
    while the subscription is active. A lapsed (paused/cancelled) club falls
    back to Core only.
    """
    if org is None:
        return set()
    if not org_subscription_active(org):
        return set()
    mods = set(tier_modules(getattr(org, "tier", None)))
    for m in (getattr(org, "module_overrides", None) or []):
        if m in ALL_MODULES:
            mods.add(m)
    return mods


def org_has_module(org, module: str) -> bool:
    return module in org_entitled_modules(org)


def entitlement_summary(org, role: str | None = None) -> dict:
    """The entitlement shape surfaced to the frontend (via ``/auth/me``).

    Super admins act cross-club and are never gated out of a module, so they
    see every module as entitled regardless of their own club's tier.
    """
    if role == "super_admin":
        mods = set(ALL_MODULES)
    else:
        mods = org_entitled_modules(org)
    renewal = getattr(org, "renewal_date", None) if org is not None else None
    return {
        "tier": (getattr(org, "tier", None) or DEFAULT_TIER) if org is not None else DEFAULT_TIER,
        "modules": sorted(mods),
        "overrides": list(getattr(org, "module_overrides", None) or []) if org is not None else [],
        "status": (getattr(org, "subscription_status", None) or DEFAULT_STATUS) if org is not None else DEFAULT_STATUS,
        "renewal_date": renewal.isoformat() if renewal else None,
        "billing_cycle": getattr(org, "billing_cycle", None) if org is not None else None,
    }


# ─── FastAPI dependency factory ──────────────────────────────────────────────

def require_module(module: str):
    """Gate a route (or a whole router) behind a club's module entitlement.

    Mirrors ``require_cap``. Raises **402 Payment Required** with a structured
    body the frontend uses to render an upsell when the caller's club is not
    entitled to ``module``.

    Usage — whole router (preferred for single-module routers)::

        app.include_router(fees.router, dependencies=[Depends(require_module("fees"))])

    Usage — single route::

        @router.get("/x", dependencies=[Depends(require_module("socials"))])
    """
    # Imports kept inside the closure to avoid a circular import — auth.py
    # imports from models.db, which would otherwise re-import this module at
    # startup (same pattern as require_cap).
    from app.routers.auth import get_current_user
    from app.models.db import ClubMembership, Organisation, User, get_db

    async def _dep(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> Organisation:
        row = await db.execute(
            select(ClubMembership).where(ClubMembership.user_id == current_user.id)
        )
        membership = row.scalar_one_or_none()
        if not membership:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No club membership found")
        club = await db.get(Organisation, membership.club_id)
        if club is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Club not found")
        # Super admins operate cross-club — never gate them by a single club's tier.
        if membership.role == "super_admin":
            return club
        if not org_has_module(club, module):
            meta = MODULE_META.get(module, {})
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "code": "module_not_entitled",
                    "module": module,
                    "required_tier": MODULE_REQUIRED_TIER.get(module),
                    "message": f"{meta.get('name', module)} is not included in your club's plan.",
                },
            )
        return club

    return _dep
