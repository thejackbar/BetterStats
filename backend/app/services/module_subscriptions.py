"""Per-module subscription writes (migration 118).

``org_module_subscriptions`` is the source of truth for which modules a club holds
and each module's own status / renewal / trial window. ``organisations.module_overrides``
is kept in sync here as a denormalised currently-held cache, so the fast synchronous
gate in ``app/auth/modules.py`` keeps working everywhere without eager-loading.

Every write goes through here so the cache never drifts. The org passed in must have
its ``module_subscriptions`` relationship loaded (callers selectinload it).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.modules import (
    ALL_MODULES, MODULE_CORE, STATUS_ACTIVE, STATUS_TRIAL, sub_is_live, sub_is_trial_expired,
    org_default_trial_days, expand_billing_module,
)
from app.models.db import OrgModuleSubscription, Organisation


def _now() -> datetime:
    return datetime.now(timezone.utc)


def held_module_keys(org, now: datetime | None = None) -> list[str]:
    """The modules a club currently holds (per-module status live, trial not expired).
    Ignores the org-level master switch — a paused club keeps its held set and gets
    it back on unpause, exactly as before."""
    now = now or _now()
    return sorted(
        s.module_key for s in (org.module_subscriptions or [])
        if s.module_key in ALL_MODULES and sub_is_live(s, now)
    )


def recompute_overrides_cache(org, now: datetime | None = None) -> None:
    """Sync ``module_overrides`` to the live held set. Call after every write."""
    org.module_overrides = held_module_keys(org, now)


def _find(org, module_key: str):
    return next((s for s in (org.module_subscriptions or []) if s.module_key == module_key), None)


def upsert_subscription(
    org,
    module_key: str,
    *,
    status: str = STATUS_ACTIVE,
    renewal_date=None,
    trial_started_at: datetime | None = None,
    trial_ends_at: datetime | None = None,
    now: datetime | None = None,
):
    """Create or replace a module's subscription row with the given explicit state,
    then refresh the cache. The caller supplies the full desired state."""
    now = now or _now()
    sub = _find(org, module_key)
    if sub is None:
        sub = OrgModuleSubscription(organisation_id=org.id, module_key=module_key, started_at=now)
        org.module_subscriptions.append(sub)
    sub.status = status
    sub.renewal_date = renewal_date
    sub.trial_started_at = trial_started_at
    sub.trial_ends_at = trial_ends_at
    sub.updated_at = now
    recompute_overrides_cache(org, now)
    return sub


def start_trial(
    org,
    module_key: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    days: int | None = None,
    now: datetime | None = None,
):
    """Start (or restart) a trial for a module. ``start`` defaults to now and ``end``
    to ``start + days`` (days defaults to the club's Club General Settings value)."""
    now = now or _now()
    start = start or now
    if end is None:
        end = start + timedelta(days=days if days and days > 0 else org_default_trial_days(org))
    return upsert_subscription(
        org, module_key, status=STATUS_TRIAL,
        trial_started_at=start, trial_ends_at=end, now=now,
    )


def set_status(org, module_key: str, status: str, *, renewal_date=..., now: datetime | None = None):
    """Change a module's status (e.g. trial -> active on conversion, or -> paused).
    Leaves trial dates intact; pass ``renewal_date`` to also set the renewal."""
    now = now or _now()
    sub = _find(org, module_key)
    if sub is None:
        return upsert_subscription(
            org, module_key, status=status,
            renewal_date=None if renewal_date is ... else renewal_date, now=now,
        )
    sub.status = status
    if renewal_date is not ...:
        sub.renewal_date = renewal_date
    sub.updated_at = now
    recompute_overrides_cache(org, now)
    return sub


def ensure_core_subscription(org, *, now: datetime | None = None):
    """Make sure a club holds an active BetterStats (Core) subscription. Called when a
    club is created so Core is tracked from day one (the migration backfills existing
    clubs). Requires module_subscriptions loaded (a fresh org has an empty collection)."""
    now = now or _now()
    if _find(org, MODULE_CORE) is None:
        org.module_subscriptions.append(
            OrgModuleSubscription(organisation_id=org.id, module_key=MODULE_CORE,
                                  status=STATUS_ACTIVE, started_at=now)
        )


def reconcile_held_modules(org, desired_keys, *, now: datetime | None = None) -> None:
    """Make the club hold exactly ``desired_keys``: add an ``active`` row (inheriting
    the club's legacy renewal_date) for each newly-granted module, drop the row for
    each removed one, and leave existing rows' status/dates untouched. Backs the
    simple module-toggle UI while keeping the per-module table the source of truth."""
    now = now or _now()
    want = {k for k in (desired_keys or []) if k in ALL_MODULES}
    have = {s.module_key for s in (org.module_subscriptions or [])}
    for key in want - have:
        upsert_subscription(
            org, key, status=STATUS_ACTIVE,
            renewal_date=getattr(org, "renewal_date", None), now=now,
        )
    for key in have - want:
        remove_module(org, key, now=now)
    recompute_overrides_cache(org, now)


def remove_module(org, module_key: str, *, now: datetime | None = None) -> bool:
    """Drop a module entirely (delete the row). Returns True if a row existed."""
    sub = _find(org, module_key)
    if sub is None:
        return False
    org.module_subscriptions.remove(sub)
    recompute_overrides_cache(org, now or _now())
    return True


# ─── Billable-module wrappers ─────────────────────────────────────────────────
# A billable module (BetterAdmin) can cover several entitlement keys; these apply
# the same change to every member so the group always moves as one unit.

def start_trial_billing(org, billing_key: str, *, start=None, end=None, days=None, now=None):
    """Start a trial for a billable module across all its entitlement keys, with the
    SAME start/end for each so the group reads as one trial."""
    now = now or _now()
    start = start or now
    if end is None:
        end = start + timedelta(days=days if days and days > 0 else org_default_trial_days(org))
    return [
        upsert_subscription(org, ek, status=STATUS_TRIAL,
                            trial_started_at=start, trial_ends_at=end, now=now)
        for ek in expand_billing_module(billing_key)
    ]


def set_status_billing(org, billing_key: str, status: str, *, renewal_date=..., now=None):
    now = now or _now()
    return [
        set_status(org, ek, status, renewal_date=renewal_date, now=now)
        for ek in expand_billing_module(billing_key)
    ]


def set_trial_end_billing(org, billing_key: str, trial_ends_at, *, now=None) -> None:
    now = now or _now()
    for ek in expand_billing_module(billing_key):
        sub = _find(org, ek)
        if sub is not None:
            sub.trial_ends_at = trial_ends_at
            sub.updated_at = now
    recompute_overrides_cache(org, now)


def remove_billing(org, billing_key: str, *, now=None) -> bool:
    removed = False
    for ek in expand_billing_module(billing_key):
        removed = remove_module(org, ek, now=now) or removed
    return removed


def extend_trial_for_org(org, *, days: int, reset_start: bool, now: datetime | None = None) -> list:
    """A sales rep's "Extend Trial" action — extends every module CURRENTLY
    on trial (status == STATUS_TRIAL) for this org, uniformly. An
    active/paused/cancelled row is left alone; there's no trial there to
    extend.

    ``trial_ends_at`` is always set to ``now + days`` (not the existing end
    date plus ``days``) — "extend by N days, from now" per the brief, so a
    long-expired trial doesn't still read as expired after a rep just
    extended it. ``trial_started_at`` is only reset to ``now`` when
    ``reset_start`` is True (the club's trial had already expired — the
    fresh look the reset gives it), never for an active trial, which keeps
    its original start date and simply gets more runway on the end.

    Requires ``org.module_subscriptions`` to already be loaded. Returns the
    subscription rows that were touched (empty if the org has no module
    currently on trial)."""
    now = now or _now()
    new_end = now + timedelta(days=days)
    touched = []
    for sub in (org.module_subscriptions or []):
        if sub.status != STATUS_TRIAL:
            continue
        if reset_start:
            sub.trial_started_at = now
        sub.trial_ends_at = new_end
        sub.updated_at = now
        touched.append(sub)
    recompute_overrides_cache(org, now)
    return touched


async def sweep_expired_trials(db: AsyncSession, *, now: datetime | None = None) -> list[str]:
    """Refresh the held cache for any club whose trial has passed its end, so
    unloaded synchronous reads drop the module too (the loaded gate already does).
    Returns the affected organisation ids. Commits. The expired row is left as a
    record (status stays ``trial`` with a past end); a super admin converts or
    removes it. Run daily by the scheduler.
    """
    now = now or _now()
    rows = (await db.execute(
        select(OrgModuleSubscription.organisation_id)
        .where(
            OrgModuleSubscription.status == STATUS_TRIAL,
            OrgModuleSubscription.trial_ends_at.isnot(None),
            OrgModuleSubscription.trial_ends_at < now,
        )
        .distinct()
    )).scalars().all()
    affected: list[str] = []
    for org_id in rows:
        org = await db.get(
            Organisation, org_id,
            options=[selectinload(Organisation.module_subscriptions)],
        )
        if org is None:
            continue
        before = list(org.module_overrides or [])
        recompute_overrides_cache(org, now)
        if list(org.module_overrides or []) != before:
            affected.append(str(org_id))
    if affected:
        await db.commit()
    return affected
