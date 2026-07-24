"""BetterCRM sales targets — clubs won / ARR / revenue / trials / conversion
rate, tracked by financial year, quarter or month (migration 185).

Platform pipeline only (``crm_deals`` scope='platform') — there is no
club-scope equivalent; a club's own CRM module tracks sponsorship/grants,
not sales targets against BetterCricket's own business.

Actuals ceiling: there is no persisted stage-transition HISTORY table (a
deal's ``updated_at`` changes on any edit, not only a stage move), so a few
of these numbers are best-effort snapshots/proxies rather than true
period-accurate historical reconstructions:
  - ``pipeline_value_cents`` is always the CURRENT open pipeline, not a
    historical snapshot as of a past period's end.
  - ``trials_started`` approximates "entered Trial/Self-Serve-Trial during
    this period" by matching a deal CURRENTLY sitting in one of those
    stages whose ``updated_at`` falls in the period — correct for the
    common case (a stage move sets updated_at and nothing else changes it
    meanwhile) but not exact if the deal was edited again afterwards.
Both are clearly labelled in the returned dict so a caller/UI can caveat
them rather than presenting them as exact.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.db import CrmDeal, CrmTarget
from app.services import crm as crm_service

PERIOD_TYPES = ("month", "quarter", "fiscal_year")


def period_bounds(period_type: str, period_key: str) -> tuple:
    """UTC [start, end) bounds for a period key. Raises ValueError on a
    malformed key or unknown period_type.

    - month:        '2026-07'  -> Jul 2026
    - quarter:       '2026-Q3' -> Jul-Sep 2026 (calendar quarters, Q1=Jan-Mar)
    - fiscal_year:  'FY2026'   -> 1 Jul 2025 -> 30 Jun 2026 (the AU
      convention — named for the year it ENDS in)
    """
    if period_type == "month":
        year_s, month_s = period_key.split("-")
        year, month = int(year_s), int(month_s)
        start = datetime(year, month, 1, tzinfo=timezone.utc)
        end = (datetime(year + 1, 1, 1, tzinfo=timezone.utc) if month == 12
              else datetime(year, month + 1, 1, tzinfo=timezone.utc))
        return start, end
    if period_type == "quarter":
        year_s, q_s = period_key.split("-Q")
        year, q = int(year_s), int(q_s)
        if q not in (1, 2, 3, 4):
            raise ValueError(f"Invalid quarter in period_key: {period_key!r}")
        start_month = (q - 1) * 3 + 1
        start = datetime(year, start_month, 1, tzinfo=timezone.utc)
        end_month = start_month + 3
        end = (datetime(year, end_month, 1, tzinfo=timezone.utc) if end_month <= 12
              else datetime(year + 1, end_month - 12, 1, tzinfo=timezone.utc))
        return start, end
    if period_type == "fiscal_year":
        if not period_key.startswith("FY"):
            raise ValueError(f"Invalid fiscal_year period_key: {period_key!r}")
        year = int(period_key[2:])
        start = datetime(year - 1, 7, 1, tzinfo=timezone.utc)
        end = datetime(year, 7, 1, tzinfo=timezone.utc)
        return start, end
    raise ValueError(f"Unknown period_type: {period_type!r}")


def project_completion(target_value, actual_value, start: datetime, end: datetime,
                       now: Optional[datetime] = None) -> Optional[str]:
    """A naive linear run-rate projection — NOT a sophisticated forecast
    model, just "at the average daily rate achieved so far this period, when
    would we hit the target". Returns None when there's nothing sensible to
    project from (no target set, no progress yet, or the period hasn't
    started)."""
    if not target_value or not actual_value or actual_value <= 0:
        return None
    now = now or datetime.now(timezone.utc)
    elapsed_days = (min(now, end) - start).total_seconds() / 86400
    if elapsed_days <= 0:
        return None
    daily_rate = actual_value / elapsed_days
    if daily_rate <= 0:
        return None
    days_needed = target_value / daily_rate
    return (start + timedelta(days=days_needed)).isoformat()


async def compute_actuals(session: AsyncSession, period_type: str, period_key: str) -> dict:
    start, end = period_bounds(period_type, period_key)
    now = datetime.now(timezone.utc)

    deals = (await session.execute(
        select(CrmDeal).options(selectinload(CrmDeal.stage))
        .where(CrmDeal.scope == crm_service.SCOPE_PLATFORM)
    )).scalars().all()

    won_in_period = [d for d in deals if d.status == "won" and d.closed_at and start <= d.closed_at < end]
    lost_in_period = [d for d in deals if d.status == "lost" and d.closed_at and start <= d.closed_at < end]
    open_now = [d for d in deals if d.status == "open"]
    trialing_now = [d for d in deals if d.status == "open" and d.stage and d.stage.key in ("trial", "self_serve_trial")]
    trials_started_proxy = [d for d in trialing_now if d.updated_at and start <= d.updated_at < end]

    trial_won = [d for d in won_in_period if (d.onboarding_method or "") in ("self_serve_trial", "super_admin_trial")]
    trial_lost = [d for d in lost_in_period if (d.onboarding_method or "") in ("self_serve_trial", "super_admin_trial")]

    new_arr_cents = sum(crm_service._effective_value_cents(d) for d in won_in_period)
    cumulative_arr_cents = sum(
        crm_service._effective_value_cents(d) for d in deals
        if d.status == "won" and d.closed_at and d.closed_at < end)
    pipeline_value_cents = sum(crm_service._effective_value_cents(d) for d in open_now)

    conversion_denominator = len(trial_won) + len(trial_lost)
    conversion_rate = round(100 * len(trial_won) / conversion_denominator) if conversion_denominator else None

    return {
        "period_type": period_type, "period_key": period_key,
        "period_start": start.isoformat(), "period_end": end.isoformat(),
        "clubs_won": len(won_in_period),
        "new_arr_cents": new_arr_cents,
        "cumulative_arr_cents": cumulative_arr_cents,
        "mrr_cents": round(cumulative_arr_cents / 12),
        # Snapshot as of NOW, not a historical point-in-time reconstruction —
        # see the module docstring.
        "pipeline_value_cents": pipeline_value_cents,
        # Best-effort proxy — see the module docstring.
        "trials_started": len(trials_started_proxy),
        "trial_conversions": len(trial_won),
        "conversion_rate": conversion_rate,
        "projected_arr_completion": project_completion(None, None, start, end, now),  # filled by caller with a target
    }


async def list_targets(session: AsyncSession, period_type: Optional[str] = None) -> list:
    stmt = select(CrmTarget)
    if period_type:
        stmt = stmt.where(CrmTarget.period_type == period_type)
    stmt = stmt.order_by(CrmTarget.period_key)
    return (await session.execute(stmt)).scalars().all()


async def get_target(session: AsyncSession, period_type: str, period_key: str):
    return (await session.execute(
        select(CrmTarget).where(CrmTarget.period_type == period_type, CrmTarget.period_key == period_key)
    )).scalars().first()


async def upsert_target(session: AsyncSession, *, period_type: str, period_key: str,
                        created_by=None, **fields) -> CrmTarget:
    if period_type not in PERIOD_TYPES:
        raise ValueError(f"period_type must be one of {PERIOD_TYPES}")
    period_bounds(period_type, period_key)  # validates the key parses
    target = await get_target(session, period_type, period_key)
    if target is None:
        target = CrmTarget(period_type=period_type, period_key=period_key, created_by=created_by)
        session.add(target)
    for key in ("target_clubs_won", "target_arr_cents", "target_revenue_cents",
               "target_trials", "target_conversion_rate", "notes"):
        if key in fields:
            setattr(target, key, fields[key])
    target.updated_at = func.now()
    await session.flush()
    return target


async def delete_target(session: AsyncSession, target_id) -> bool:
    target = await session.get(CrmTarget, target_id)
    if target is None:
        return False
    await session.delete(target)
    return True


def target_dict(t: CrmTarget) -> dict:
    return {
        "id": str(t.id), "period_type": t.period_type, "period_key": t.period_key,
        "target_clubs_won": t.target_clubs_won, "target_arr_cents": t.target_arr_cents,
        "target_revenue_cents": t.target_revenue_cents, "target_trials": t.target_trials,
        "target_conversion_rate": t.target_conversion_rate, "notes": t.notes,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }
