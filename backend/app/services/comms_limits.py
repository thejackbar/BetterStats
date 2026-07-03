"""BetterComms sending limits — daily caps, per-club tiers, and the
bounce/complaint circuit breaker.

Three jobs, all reading data we already hold (``comms_recipients`` for sends,
``email_events`` for deliverability), so there is no new counter to keep in sync:

  * **Daily caps.** AWS grants a daily maximum (50,000 today); we hold campaigns
    to the super-admin-managed practical daily limit (``ses_daily_send_limit``,
    always ≤ the AWS ceiling — see services/platform_settings). Each club also has
    a per-day cap from its tier. A send is allowed up to
    ``min(account_remaining, club_remaining)``; the overflow is deferred to the
    next day (see routers/comms.py::_run_send).

  * **Tiers.** A club is ``sandbox`` (low cap, new/unproven), ``production``
    (raised after a super admin approves a request), or ``suspended`` (cap 0,
    set by the breaker). Per-club ``comms_sandbox_cap`` / ``comms_production_cap``
    override the global default for each tier. The marketing-outreach org is
    uncapped (BetterCricket's own domain).

  * **Circuit breaker.** Over a trailing window, if a club's hard-bounce rate or
    complaint rate crosses the AWS danger line (and it has sent enough to judge),
    the club trips. The scheduler auto-suspends tripped clubs; a pre-send check
    refuses to start a campaign for a tripped or suspended club.

Everything is org-scoped by ``comms_recipients.organisation_id`` (NOT NULL) and
``email_events.organisation_id`` (nullable — orphan events without a matched
recipient are dropped from per-club counts, which is the safe direction).
"""
from __future__ import annotations

import datetime as _dt
from typing import Optional

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.models.db import CommsRecipient, Organisation
from app.services.marketing_org import org_is_outreach

# Tier vocabulary. Kept tiny and stable; the super-admin UI mirrors it.
TIER_SANDBOX = "sandbox"
TIER_PRODUCTION = "production"
TIER_SUSPENDED = "suspended"
TIERS = (TIER_SANDBOX, TIER_PRODUCTION, TIER_SUSPENDED)


def normalise_tier(tier: Optional[str]) -> str:
    t = (tier or "").strip().lower()
    return t if t in TIERS else TIER_SANDBOX


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _day_window_start() -> _dt.datetime:
    """Start of the daily send window. AWS's daily quota is a ROLLING 24-hour
    window (not a calendar midnight), so we mirror that — it also sidesteps every
    timezone boundary bug (a club sending in the morning no longer sees 0 because
    UTC midnight hasn't rolled)."""
    return _now() - _dt.timedelta(hours=24)


def _month_window_start() -> _dt.datetime:
    """Start of the monthly send window — a rolling 30 days, same reasoning as the
    daily window."""
    return _now() - _dt.timedelta(days=30)


# ─── tier → per-day cap ──────────────────────────────────────────────────────

def _org_cap(org: Organisation, attr: str) -> Optional[int]:
    """A per-club cap override (comms_sandbox_cap / comms_production_cap), or None
    when the club has no override and the global settings default should apply."""
    val = getattr(org, attr, None)
    if val is None or str(val).strip() == "":
        return None
    try:
        return max(0, int(val))
    except (TypeError, ValueError):
        return None


def tier_daily_cap(org: Organisation, defaults: Optional[dict] = None) -> Optional[int]:
    """The club's per-day send cap for its current tier. ``None`` means uncapped
    (the marketing outreach org). The per-club override for the tier wins over the
    global default; ``suspended`` is a hard 0.

    ``defaults`` are the super-admin-managed tier defaults (from
    platform_settings.get_comms_tier_defaults); when omitted, the env seed
    defaults are used (fine for the breaker sweep, which only reads the value)."""
    if org_is_outreach(org):
        return None
    tier = normalise_tier(getattr(org, "comms_tier", None))
    if tier == TIER_SUSPENDED:
        return 0
    d = defaults or {}
    if tier == TIER_PRODUCTION:
        override = _org_cap(org, "comms_production_cap")
        return override if override is not None else int(d.get("production_daily", settings.comms_production_daily_cap))
    override = _org_cap(org, "comms_sandbox_cap")
    return override if override is not None else int(d.get("sandbox_daily", settings.comms_sandbox_daily_cap))


def monthly_cap(org: Organisation, defaults: Optional[dict] = None) -> Optional[int]:
    """The club's monthly send ceiling. ``None`` = uncapped (outreach org, or an
    explicit 0 override = no monthly limit). Per-club ``comms_monthly_cap`` wins
    over the global default."""
    if org_is_outreach(org):
        return None
    tier = normalise_tier(getattr(org, "comms_tier", None))
    if tier == TIER_SUSPENDED:
        return 0
    raw = getattr(org, "comms_monthly_cap", None)
    if raw is not None and str(raw).strip() != "":
        try:
            val = int(raw)
            return None if val <= 0 else val  # explicit 0 = no monthly limit
        except (TypeError, ValueError):
            pass
    d = defaults or {}
    default_val = int(d.get("monthly", getattr(settings, "comms_monthly_send_default", 10000)))
    return None if default_val <= 0 else default_val


async def _tier_defaults(session: AsyncSession) -> dict:
    """The super-admin-managed tier defaults, with a safe fallback to env seeds."""
    from app.services import platform_settings
    try:
        return await platform_settings.get_comms_tier_defaults(session)
    except Exception:
        return {
            "sandbox_daily": int(settings.comms_sandbox_daily_cap),
            "production_daily": int(settings.comms_production_daily_cap),
            "monthly": int(getattr(settings, "comms_monthly_send_default", 10000)),
        }


# ─── daily send counts (from comms_recipients) ───────────────────────────────

async def _sends_since(session: AsyncSession, since: _dt.datetime, org_id=None) -> int:
    """Count recipients sent since ``since``. Account-wide when ``org_id`` is None,
    else scoped to that club. Only ``status='sent'`` counts."""
    stmt = select(func.count(CommsRecipient.id)).where(
        CommsRecipient.status == "sent",
        CommsRecipient.sent_at >= since,
    )
    if org_id is not None:
        stmt = stmt.where(CommsRecipient.organisation_id == org_id)
    return int((await session.scalar(stmt)) or 0)


async def sends_today(session: AsyncSession, org_id=None) -> int:
    """Count of recipients sent in the trailing 24h (the rolling daily window)."""
    return await _sends_since(session, _day_window_start(), org_id=org_id)


async def sends_this_month(session: AsyncSession, org_id=None) -> int:
    """Count of recipients sent in the trailing 30 days (rolling monthly window)."""
    return await _sends_since(session, _month_window_start(), org_id=org_id)


async def account_daily_remaining(session: AsyncSession) -> int:
    """How many more sends the whole account may make today before hitting our
    practical daily send limit (super-admin managed, always ≤ the AWS daily
    grant). Read from platform_settings, falling back to the env seed default."""
    from app.services import platform_settings
    try:
        usable = int(await platform_settings.get_daily_send_limit(session))
    except Exception:
        usable = int(settings.ses_daily_send_limit)
    used = await sends_today(session, org_id=None)
    return max(0, usable - used)


async def club_daily_remaining(session: AsyncSession, org: Organisation,
                               defaults: Optional[dict] = None) -> Optional[int]:
    """How many more sends this club may make today. ``None`` = uncapped."""
    cap = tier_daily_cap(org, defaults)
    if cap is None:
        return None
    used = await sends_today(session, org_id=org.id)
    return max(0, cap - used)


async def club_monthly_remaining(session: AsyncSession, org: Organisation,
                                 defaults: Optional[dict] = None) -> Optional[int]:
    """How many more sends this club may make this month. ``None`` = uncapped."""
    cap = monthly_cap(org, defaults)
    if cap is None:
        return None
    used = await sends_this_month(session, org_id=org.id)
    return max(0, cap - used)


async def send_allowance(session: AsyncSession, org: Organisation,
                         defaults: Optional[dict] = None) -> int:
    """The number of recipients a campaign for this club may send RIGHT NOW — the
    tightest of the club daily cap, the club monthly cap and the account ceiling.
    The send loop caps the audience to this and defers the rest to tomorrow."""
    if defaults is None:
        defaults = await _tier_defaults(session)
    limits = [await account_daily_remaining(session)]
    day = await club_daily_remaining(session, org, defaults)
    month = await club_monthly_remaining(session, org, defaults)
    if day is not None:
        limits.append(day)
    if month is not None:
        limits.append(month)
    return min(limits)


# ─── deliverability metrics + circuit breaker (from email_events) ────────────

async def deliverability_metrics(session: AsyncSession, org_id, *,
                                 window_days: Optional[int] = None) -> dict:
    """Bounce/complaint rates for a club over the trailing window. Denominator is
    sends (``comms_recipients`` sent in the window); numerators are hard bounces
    (``email_events`` bounce/Permanent) and complaints. Rates are 0 when there is
    nothing to divide by."""
    days = int(window_days if window_days is not None else settings.comms_metrics_window_days)
    since = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days)

    sent = int((await session.scalar(
        select(func.count(CommsRecipient.id)).where(
            CommsRecipient.organisation_id == org_id,
            CommsRecipient.status == "sent",
            CommsRecipient.sent_at >= since,
        ))) or 0)

    # email_events stores the SES type lowercased; bounce subtype is mixed-case
    # ("Permanent"), so compare case-insensitively — same rule as ses_events.py.
    row = (await session.execute(text("""
        SELECT
          COUNT(*) FILTER (WHERE event_type = 'bounce'
                             AND lower(coalesce(event_subtype,'')) = 'permanent') AS hard_bounces,
          COUNT(*) FILTER (WHERE event_type = 'complaint')                        AS complaints,
          COUNT(DISTINCT recipient_id) FILTER (WHERE event_type = 'delivery')     AS delivered
        FROM email_events
        WHERE organisation_id = :org AND created_at >= :since
    """), {"org": org_id, "since": since})).one()
    hard_bounces, complaints, delivered = int(row[0] or 0), int(row[1] or 0), int(row[2] or 0)

    bounce_rate = (hard_bounces / sent) if sent else 0.0
    complaint_rate = (complaints / sent) if sent else 0.0
    return {
        "window_days": days,
        "sent": sent,
        "delivered": delivered,
        "hard_bounces": hard_bounces,
        "complaints": complaints,
        "bounce_rate": round(bounce_rate, 5),
        "complaint_rate": round(complaint_rate, 5),
        "min_sample": int(settings.comms_metrics_min_sample),
        "sufficient_sample": sent >= int(settings.comms_metrics_min_sample),
    }


def breaker_reason(metrics: dict) -> Optional[str]:
    """A short reason string if the club's metrics cross the danger line, else
    None. Only judges once the sample is big enough — a single bounce on 3 sends
    is noise, not a reputation problem."""
    if not metrics.get("sufficient_sample"):
        return None
    if metrics["bounce_rate"] >= float(settings.comms_bounce_rate_threshold):
        return (f"bounce rate {metrics['bounce_rate']:.1%} over the last "
                f"{metrics['window_days']}d exceeds {float(settings.comms_bounce_rate_threshold):.0%}")
    if metrics["complaint_rate"] >= float(settings.comms_complaint_rate_threshold):
        return (f"complaint rate {metrics['complaint_rate']:.2%} over the last "
                f"{metrics['window_days']}d exceeds {float(settings.comms_complaint_rate_threshold):.1%}")
    return None


async def preflight(session: AsyncSession, org: Organisation) -> dict:
    """One call the send handler uses before starting a campaign: the club's
    tier, today's usage, remaining allowance, deliverability, and whether sending
    is currently blocked (suspended, or the breaker is tripped)."""
    defaults = await _tier_defaults(session)
    tier = normalise_tier(getattr(org, "comms_tier", None))
    cap = tier_daily_cap(org, defaults)
    mcap = monthly_cap(org, defaults)
    used = await sends_today(session, org_id=org.id)
    used_month = await sends_this_month(session, org_id=org.id)
    account_remaining = await account_daily_remaining(session)
    allowance = await send_allowance(session, org, defaults)
    metrics = await deliverability_metrics(session, org.id)
    tripped = breaker_reason(metrics)

    daily_remaining = None if cap is None else max(0, cap - used)
    monthly_remaining = None if mcap is None else max(0, mcap - used_month)

    blocked = None
    if getattr(org, "ses_tenant_paused", False):
        blocked = "This club's SES tenant is paused (reputation) — sending is on hold."
    elif tier == TIER_SUSPENDED:
        blocked = "Sending is suspended for this club pending review."
    elif tripped:
        blocked = f"Sending is paused: {tripped}."
    elif account_remaining <= 0:
        blocked = "The platform's daily send limit is reached — try again tomorrow."
    elif cap is not None and used >= cap:
        blocked = (f"This club's daily limit of {cap} is reached — the rest will "
                   f"send tomorrow, or request a higher limit.")
    elif mcap is not None and used_month >= mcap:
        blocked = (f"This club's monthly limit of {mcap} is reached — the rest will "
                   f"send once the 30-day window frees up, or request a higher limit.")

    return {
        "tier": tier,
        "daily_cap": cap,
        "sent_today": used,
        "daily_remaining": daily_remaining,
        "monthly_cap": mcap,
        "sent_this_month": used_month,
        "monthly_remaining": monthly_remaining,
        "account_remaining": account_remaining,
        "allowance": allowance,
        "metrics": metrics,
        "breaker_reason": tripped,
        "blocked": blocked,
        "is_outreach": org_is_outreach(org),
    }


async def sweep_breaker() -> dict:
    """Daily circuit-breaker sweep: auto-suspend any production club whose
    bounce/complaint rate has crossed the AWS danger line. Protects the shared
    SES account by containing one bad club before it drags the whole account's
    reputation down. A suspended club needs a super-admin reinstate.

    Runs in its own session (scheduler job). The outreach org is never touched.
    Returns a summary for the log."""
    from app.models.db import async_session_maker  # local import avoids a cycle
    suspended: list[dict] = []
    async with async_session_maker() as session:
        orgs = (await session.execute(
            select(Organisation).where(
                Organisation.comms_tier == TIER_PRODUCTION))).scalars().all()
        for org in orgs:
            if org_is_outreach(org):
                continue
            metrics = await deliverability_metrics(session, org.id)
            reason = breaker_reason(metrics)
            if reason:
                org.comms_tier = TIER_SUSPENDED
                suspended.append({"org_id": str(org.id), "name": org.name, "reason": reason})
        if suspended:
            await session.commit()
    return {"checked": True, "suspended": suspended}
