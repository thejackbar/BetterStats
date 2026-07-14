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

# BetterStats (Core) — the base product every synced club gets. It's NOT in
# ALL_MODULES (which is the add-on gating set, so the add-on entitlement logic and
# frontend counts stay unchanged), but it IS a managed, billable module with its own
# subscription row: a super admin can trial it with dates and its lifecycle controls
# whether the public club surfaces render (see org_core_live + the public routers).
MODULE_CORE = "core"
# Everything a super admin can manage as a subscription row (add-ons + Core).
MANAGED_MODULES = ALL_MODULES + (MODULE_CORE,)

# ─── Billable modules ─────────────────────────────────────────────────────────
# A *billable* module maps to one or more *entitlement* keys. BetterAdmin is the
# only group today (fees + comms + merch move together); everything else is 1:1.
# Subscriptions, trials and requests act on billable modules; entitlement gating
# still uses the underlying keys.
MODULE_ADMIN = "admin"     # BetterAdmin umbrella
MODULE_GROUPS: dict[str, tuple[str, ...]] = {
    MODULE_ADMIN: (MODULE_FEES, MODULE_COMMS, MODULE_MERCH),
}
# Core leads — it's the base everything builds on.
BILLABLE_MODULES = (MODULE_CORE, MODULE_SELECT, MODULE_SOCIALS, MODULE_ADMIN, MODULE_IQ, MODULE_FANTASY)
BILLABLE_MODULE_NAMES = {
    MODULE_CORE: "BetterStats",
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


def org_core_live(org, now: datetime | None = None) -> bool:
    """Whether BetterStats (Core) — and thus the public club surfaces — is live.

    Returns True (visible) unless an explicit core subscription row says otherwise: a
    cancelled/paused core, an expired core trial, or the org-level master switch being
    off all gate the public site. **Fail-open**: a club whose subscriptions aren't
    loaded, or that has no core row yet (legacy/pre-backfill), is never gated — so we
    can't accidentally take a live club's site down. Callers that enforce eager-load
    ``module_subscriptions``.
    """
    if org is None:
        return False
    subs = _loaded_subscriptions(org)
    if not subs:
        return True  # not loaded, or genuinely no subscriptions → fail-open
    core = next((s for s in subs if s.module_key == MODULE_CORE), None)
    if core is None:
        return True  # not on the core-module scheme yet → fail-open
    if not org_subscription_active(org):  # master switch gates everything, incl. Core
        return False
    return sub_is_live(core, now or _now())


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


_STATUS_PRIORITY = {STATUS_ACTIVE: 0, STATUS_PAST_DUE: 1, STATUS_TRIAL: 2, STATUS_PAUSED: 3, STATUS_CANCELLED: 4}


def _billing_module_summary(org, now: datetime | None = None) -> list[dict]:
    """One row per currently-held BILLABLE module (Core + the BetterAdmin
    umbrella + the rest) — the shape a "Plan: ..." style display needs.
    Unlike ``_module_details`` (which lists raw entitlement keys), this rolls
    BetterAdmin's three entitlement keys (fees/comms/merch) into a single row,
    since they're sold, trialled and displayed as ONE module everywhere else
    (the Super Admin module editor, public pricing). Only modules the club
    currently holds are included (matches ``org_entitled_modules``'s own
    "entitled now" semantics) — a paused/cancelled module drops out rather
    than showing a stale row."""
    subs = _loaded_subscriptions(org)
    if subs is None:
        return []
    now = now or _now()
    by_key = {s.module_key: s for s in subs}
    out = []
    for billing_key in BILLABLE_MODULES:
        rows = [by_key[m] for m in expand_billing_module(billing_key) if m in by_key]
        if not rows:
            continue
        best = min(rows, key=lambda s: _STATUS_PRIORITY.get(s.status, 99))
        if best.status not in HELD_STATUSES:
            continue
        out.append({
            "module": billing_key,
            "name": BILLABLE_MODULE_NAMES.get(billing_key, billing_key),
            "status": best.status,
            "live": sub_is_live(best, now) and org_subscription_active(org),
            "renewal_date": best.renewal_date.isoformat() if best.renewal_date else None,
            "trial_ends_at": best.trial_ends_at.isoformat() if best.trial_ends_at else None,
        })
    return out


# Self-serve display status for the club's own Account page — distinct from
# _billing_module_summary above (which only lists currently-HELD modules, the
# shape a "Plan: ..." snapshot needs). This one always returns every billable
# module, including ones the club has never touched, since the Account page's
# whole job is to show what's available to trial/subscribe as well as what's
# already held.
STATUS_NEVER_TRIALED = "never_trialed"
STATUS_TRIAL_EXPIRED = "trial_expired"
STATUS_SUBSCRIBED = "subscribed"


def account_plan_status(org, now: datetime | None = None) -> list[dict]:
    """One row per BILLABLE module (Core included) for the club's own Account
    page: display status (subscribed / trial / trial_expired / never_trialed),
    renewal/trial dates, and whether starting a new trial is still available
    (only ever true once — ``trial_eligible`` is False the moment ANY member
    row has ever recorded a ``trial_started_at``, even if that row was later
    removed and re-created, so a club can't repeatedly re-trial a module by
    having a super admin clear it — and also False once already subscribed,
    so a paid module that skipped a trial doesn't dangle a pointless "start
    trial" offer). ``can_subscribe`` is simply "not already a real paying
    subscription" — available during a trial too, so a club can convert
    early."""
    subs = _loaded_subscriptions(org)
    if subs is None:
        return []
    now = now or _now()
    by_key = {s.module_key: s for s in subs}
    out = []
    for billing_key in BILLABLE_MODULES:
        member_rows = [by_key[m] for m in expand_billing_module(billing_key) if m in by_key]
        best = min(member_rows, key=lambda s: _STATUS_PRIORITY.get(s.status, 99)) if member_rows else None
        ever_trialled = any(s.trial_started_at is not None for s in member_rows)

        if best is None or best.status in (STATUS_PAUSED, STATUS_CANCELLED):
            status = STATUS_TRIAL_EXPIRED if ever_trialled else STATUS_NEVER_TRIALED
        elif best.status in PAID_STATUSES:
            status = STATUS_SUBSCRIBED
        else:  # STATUS_TRIAL
            status = STATUS_TRIAL_EXPIRED if sub_is_trial_expired(best, now) else STATUS_TRIAL

        out.append({
            "module": billing_key,
            "name": BILLABLE_MODULE_NAMES.get(billing_key, billing_key),
            "status": status,
            "renewal_date": best.renewal_date.isoformat() if best and best.renewal_date else None,
            "trial_ends_at": best.trial_ends_at.isoformat() if best and best.trial_ends_at else None,
            "trial_eligible": not ever_trialled and status != STATUS_SUBSCRIBED,
            "can_subscribe": status != STATUS_SUBSCRIBED,
        })
    return out


def entitlement_summary(org, role: str | None = None) -> dict:
    """The entitlement shape surfaced to the frontend (via ``/auth/me``).

    ``modules`` is the entitled-now key list the frontend gates on (``hasModule``);
    ``module_details`` carries each held module's own status / renewal / trial end
    when the rows are loaded (raw entitlement keys — fees/comms/merch appear
    separately). ``billing_modules`` is the same data rolled up to billable
    modules (BetterAdmin as one row), for a "Plan: ..." style display. Super
    admins act cross-club and are never gated out of a module, so they see
    every module as entitled regardless of their club's plan.
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
        "billing_modules": _billing_module_summary(org) if org is not None else [],
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
