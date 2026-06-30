"""Module entitlements: the Better ecosystem's per-club module gating.

The Better platform is modular. Every club gets Core (BetterStats) and turns on
the individual modules it pays for. A club's ``module_overrides`` is the explicit
list of modules it holds, and it's the single source of truth for entitlement.

This module is the single source of truth for:
  - the module registry (keys + display metadata),
  - resolving a club's effective entitlements, and
  - the ``require_module()`` FastAPI dependency that gates module routes.

Core (BetterStats), data ingestion, reconciled stats and the public site, is
always on for every club and is intentionally not a gateable module: it's the
product every club gets.

Keep the registry in sync with ``frontend/src/lib/modules.js``.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from sqlalchemy import inspect as sa_inspect, select
from sqlalchemy.ext.asyncio import AsyncSession


# ─── Module registry ─────────────────────────────────────────────────────────

MODULE_SELECT = "select"     # BetterSelect  — availability + smart team selection
MODULE_SOCIALS = "socials"   # BetterSocials — auto social posts
MODULE_FEES = "fees"         # BetterFees    — fee schedules + payment tracking
MODULE_IQ = "iq"             # BetterIQ      — AI + stats deep-dive
MODULE_COMMS = "comms"       # BetterComms   — bulk email to the member database
MODULE_MERCH = "merch"       # BetterMerch   — club stock register (apparel, equipment, food/drink)
MODULE_FANTASY = "fantasy"   # BetterFantasyCricket — internal club fantasy league

# BetterFees + BetterComms + BetterMerch are presented together on the admin
# dashboard under the **BetterAdmin** umbrella (see frontend modules.js). They stay
# separate ENTITLEMENT keys here (each route gates on its own key), but are sold,
# trialed and requested as ONE billable module — BetterAdmin (see billing helpers
# below), matching the public pricing (one $149 umbrella).
ALL_MODULES = (MODULE_SELECT, MODULE_SOCIALS, MODULE_FEES, MODULE_IQ, MODULE_COMMS, MODULE_MERCH, MODULE_FANTASY)

# ─── Billable modules ─────────────────────────────────────────────────────────
# A *billable* module maps to one or more *entitlement* keys. BetterAdmin is the
# only group today (fees + comms + merch move together); everything else is 1:1.
# Subscriptions, trials and requests act on billable modules; entitlement gating
# still uses the underlying keys.
MODULE_ADMIN = "admin"     # BetterAdmin umbrella
MODULE_GROUPS: dict[str, tuple[str, ...]] = {
    MODULE_ADMIN: (MODULE_FEES, MODULE_COMMS, MODULE_MERCH),
}
BILLABLE_MODULES = (MODULE_SELECT, MODULE_SOCIALS, MODULE_ADMIN, MODULE_IQ, MODULE_FANTASY)
BILLABLE_MODULE_NAMES = {
    MODULE_SELECT: "BetterSelect",
    MODULE_SOCIALS: "BetterSocials",
    MODULE_ADMIN: "BetterAdmin",
    MODULE_IQ: "BetterIQ",
    MODULE_FANTASY: "BetterFantasyCricket",
}


def expand_billing_module(key: str) -> tuple[str, ...]:
    """The entitlement keys a billable module covers (BetterAdmin -> fees/comms/merch;
    everything else -> itself)."""
    return MODULE_GROUPS.get(key, (key,))


def billing_key_for(entitlement_key: str) -> str:
    """The billable module an entitlement key rolls up to (fees/comms/merch -> admin)."""
    for group, members in MODULE_GROUPS.items():
        if entitlement_key in members:
            return group
    return entitlement_key

# Display metadata, surfaced to the admin module-tile dashboard. ``built`` flags
# whether the module exists yet. BetterIQ Phase 1 (opposition analysis) is now
# live; selection analysis, player trends and NL Q&A are later phases.
MODULE_META: dict[str, dict] = {
    MODULE_SELECT: {"name": "BetterSelect", "blurb": "Availability & smart team selection", "built": True},
    MODULE_SOCIALS: {"name": "BetterSocials", "blurb": "Auto-post lineups, scorecards & milestones", "built": True},
    MODULE_FEES: {"name": "BetterFees", "blurb": "Fee schedules & payment tracking", "built": True},
    MODULE_IQ: {"name": "BetterIQ", "blurb": "AI + stats deep-dive — opposition scouting & selection analysis", "built": True},
    MODULE_COMMS: {"name": "BetterComms", "blurb": "Bulk email to your member database", "built": True},
    MODULE_MERCH: {"name": "BetterMerch", "blurb": "Track club stock — apparel, equipment and canteen", "built": True},
    MODULE_FANTASY: {"name": "BetterFantasyCricket", "blurb": "Run an internal club fantasy cricket league", "built": True},
}


# ─── Subscription status ──────────────────────────────────────────────────────
# Per-module now (org_module_subscriptions, migration 118). The same vocabulary is
# reused at two levels: each module row carries its own status, and the org-level
# `organisations.subscription_status` is a whole-account MASTER SWITCH above them.
# active/trial/past_due keep a module live (past_due is a grace period — don't cut
# a club off the moment an invoice is late); paused/cancelled fall back to Core
# only. A trial is live only while now <= trial_ends_at (read-time expiry).

STATUS_ACTIVE = "active"
STATUS_TRIAL = "trial"
STATUS_PAST_DUE = "past_due"
STATUS_PAUSED = "paused"
STATUS_CANCELLED = "cancelled"

ALL_STATUSES = (STATUS_ACTIVE, STATUS_TRIAL, STATUS_PAST_DUE, STATUS_PAUSED, STATUS_CANCELLED)
ACTIVE_STATUSES = frozenset({STATUS_ACTIVE, STATUS_TRIAL, STATUS_PAST_DUE})
# Statuses that count as the club still HOLDING the module (drives the
# module_overrides cache); a trial counts as held until it expires.
HELD_STATUSES = frozenset({STATUS_ACTIVE, STATUS_TRIAL, STATUS_PAST_DUE})
PAID_STATUSES = frozenset({STATUS_ACTIVE, STATUS_PAST_DUE})  # genuinely paying (not trial)
DEFAULT_STATUS = STATUS_ACTIVE

ALL_BILLING_CYCLES = ("monthly", "annual")

DEFAULT_TRIAL_DAYS = 14


def _now() -> datetime:
    return datetime.now(timezone.utc)


def org_subscription_active(org) -> bool:
    """The org-level master switch is live (active/trial/past_due, not paused/cancelled)."""
    if org is None:
        return False
    return (getattr(org, "subscription_status", None) or DEFAULT_STATUS) in ACTIVE_STATUSES


def org_default_trial_days(org) -> int:
    """The club's configured default trial length (Club General Settings), else 14."""
    settings = getattr(org, "general_settings", None) or {}
    try:
        days = int(settings.get("default_trial_days"))
        return days if days > 0 else DEFAULT_TRIAL_DAYS
    except (TypeError, ValueError):
        return DEFAULT_TRIAL_DAYS


def sub_is_trial_expired(sub, now: datetime | None = None) -> bool:
    """A per-module subscription row that is a trial past its end."""
    if (getattr(sub, "status", None) or "") != STATUS_TRIAL:
        return False
    ends = getattr(sub, "trial_ends_at", None)
    return ends is not None and (now or _now()) > ends


def sub_is_live(sub, now: datetime | None = None) -> bool:
    """Is this per-module row entitled in its own right (ignoring the master switch)."""
    if (getattr(sub, "status", None) or "") not in ACTIVE_STATUSES:
        return False
    return not sub_is_trial_expired(sub, now)


def _loaded_subscriptions(org):
    """The org's loaded ``module_subscriptions`` rows, or None when the relationship
    isn't loaded (or ``org`` isn't an ORM instance — e.g. a SimpleNamespace). Avoids
    triggering a forbidden lazy-load in async context; callers that need exact
    read-time trial expiry eager-load the relationship."""
    try:
        state = sa_inspect(org)
    except Exception:
        return None
    if "module_subscriptions" in state.unloaded:
        return None
    return list(getattr(org, "module_subscriptions", None) or [])


# ─── Entitlement resolution ──────────────────────────────────────────────────

def org_entitled_modules(org, now: datetime | None = None) -> set[str]:
    """The set of module keys a club may use right now.

    ``module_overrides`` is the denormalised currently-held cache, recomputed on
    every per-module write, so the fast synchronous gate keeps working everywhere.
    The org-level master switch (paused/cancelled) drops the club to Core only.
    When the per-module rows are loaded, any trial that has passed its
    ``trial_ends_at`` is subtracted read-time (so a trial lapses on its own with no
    scheduler); when they aren't loaded we trust the cache (refreshed by the daily
    sweep). Core (BetterStats) is always on and is never in this set.
    """
    if org is None:
        return set()
    if not org_subscription_active(org):
        return set()
    held = {m for m in (getattr(org, "module_overrides", None) or []) if m in ALL_MODULES}
    subs = _loaded_subscriptions(org)
    if subs:
        now = now or _now()
        held -= {s.module_key for s in subs if sub_is_trial_expired(s, now)}
    return held


def org_has_module(org, module: str) -> bool:
    return module in org_entitled_modules(org)


def _module_details(org, now: datetime | None = None) -> list[dict]:
    """Per-module subscription detail for the frontend, when the rows are loaded."""
    subs = _loaded_subscriptions(org)
    if subs is None:
        return []
    now = now or _now()
    out = []
    for s in subs:
        if s.module_key not in ALL_MODULES:
            continue
        out.append({
            "module": s.module_key,
            "status": s.status,
            "live": sub_is_live(s, now) and org_subscription_active(org),
            "renewal_date": s.renewal_date.isoformat() if s.renewal_date else None,
            "trial_ends_at": s.trial_ends_at.isoformat() if s.trial_ends_at else None,
        })
    return sorted(out, key=lambda d: d["module"])


def entitlement_summary(org, role: str | None = None) -> dict:
    """The entitlement shape surfaced to the frontend (via ``/auth/me``).

    ``modules`` is the entitled-now key list the frontend gates on (``hasModule``);
    ``module_details`` carries each held module's own status / renewal / trial end
    when the rows are loaded. Super admins act cross-club and are never gated out of
    a module, so they see every module as entitled regardless of their club's plan.
    """
    if role == "super_admin":
        mods = set(ALL_MODULES)
    else:
        mods = org_entitled_modules(org)
    renewal = getattr(org, "renewal_date", None) if org is not None else None
    return {
        "modules": sorted(mods),
        "overrides": list(getattr(org, "module_overrides", None) or []) if org is not None else [],
        "status": (getattr(org, "subscription_status", None) or DEFAULT_STATUS) if org is not None else DEFAULT_STATUS,
        "renewal_date": renewal.isoformat() if renewal else None,
        "billing_cycle": getattr(org, "billing_cycle", None) if org is not None else None,
        "module_details": _module_details(org) if org is not None else [],
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
    from sqlalchemy.orm import selectinload

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
        # Eager-load the per-module rows so read-time trial expiry is exact.
        club = await db.get(
            Organisation, membership.club_id,
            options=[selectinload(Organisation.module_subscriptions)],
        )
        if club is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Club not found")
        # Super admins operate cross-club, never gated by a single club's modules.
        if membership.role == "super_admin":
            return club
        if not org_has_module(club, module):
            meta = MODULE_META.get(module, {})
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "code": "module_not_entitled",
                    "module": module,
                    "message": f"{meta.get('name', module)} is not included in your club's plan.",
                },
            )
        return club

    return _dep
