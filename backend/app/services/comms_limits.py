"""BetterComms sending limits — daily caps, per-club tiers, and the
bounce/complaint circuit breaker.

Three jobs, all reading data we already hold (``comms_recipients`` for sends,
``email_events`` for deliverability), so there is no new counter to keep in sync:

  * **Daily caps.** AWS grants 50,000/day account-wide; we hold campaigns to
    ``ses_daily_quota - ses_daily_quota_headroom`` (reserving room for
    transactional). Each club also has a per-day cap from its tier. A send is
    allowed up to ``min(account_remaining, club_remaining)``; the overflow is
    deferred to the next day (see routers/comms.py::_run_send).

  * **Tiers.** A club is ``sandbox`` (low cap, new/unproven), ``production``
    (raised after a super admin approves a request), or ``suspended`` (cap 0,
    set by the breaker). ``organisations.comms_daily_limit`` overrides the tier
    default. The marketing-outreach org is uncapped (BetterCricket's own domain).

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


def _utc_day_start() -> _dt.datetime:
    """Midnight today, UTC — the boundary AWS's daily quota resets on."""
    now = _dt.datetime.now(_dt.timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


# ─── tier → per-day cap ──────────────────────────────────────────────────────

def tier_daily_cap(org: Organisation) -> Optional[int]:
    """The club's per-day send cap. ``None`` means uncapped (the marketing
    outreach org). An explicit ``comms_daily_limit`` override wins over the tier
    default; ``suspended`` is a hard 0 regardless of any override."""
    if org_is_outreach(org):
        return None
    tier = normalise_tier(getattr(org, "comms_tier", None))
    if tier == TIER_SUSPENDED:
        return 0
    override = getattr(org, "comms_daily_limit", None)
    if override is not None and str(override).strip() != "":
        try:
            return max(0, int(override))
        except (TypeError, ValueError):
            pass
    if tier == TIER_PRODUCTION:
        return int(settings.comms_production_daily_cap)
    return int(settings.comms_sandbox_daily_cap)


# ─── daily send counts (from comms_recipients) ───────────────────────────────

async def sends_today(session: AsyncSession, org_id=None) -> int:
    """Count of recipients actually sent since midnight UTC. Account-wide when
    ``org_id`` is None, else scoped to that club. Deferred/failed rows don't
    count — only ``status='sent'``."""
    stmt = select(func.count(CommsRecipient.id)).where(
        CommsRecipient.status == "sent",
        CommsRecipient.sent_at >= _utc_day_start(),
    )
    if org_id is not None:
        stmt = stmt.where(CommsRecipient.organisation_id == org_id)
    return int((await session.scalar(stmt)) or 0)


async def account_daily_remaining(session: AsyncSession) -> int:
    """How many more sends the whole account may make today before hitting our
    self-imposed ceiling (the AWS grant minus reserved headroom)."""
    usable = int(settings.ses_daily_quota) - int(settings.ses_daily_quota_headroom)
    used = await sends_today(session, org_id=None)
    return max(0, usable - used)


async def club_daily_remaining(session: AsyncSession, org: Organisation) -> Optional[int]:
    """How many more sends this club may make today. ``None`` = uncapped."""
    cap = tier_daily_cap(org)
    if cap is None:
        return None
    used = await sends_today(session, org_id=org.id)
    return max(0, cap - used)


async def send_allowance(session: AsyncSession, org: Organisation) -> int:
    """The number of recipients a campaign for this club may send RIGHT NOW —
    the tighter of the club cap and the account ceiling. The send loop caps the
    audience to this and defers the rest to tomorrow."""
    account = await account_daily_remaining(session)
    club = await club_daily_remaining(session, org)
    return account if club is None else min(account, club)


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
          COUNT(*) FILTER (WHERE event_type = 'complaint')                        AS complaints
        FROM email_events
        WHERE organisation_id = :org AND created_at >= :since
    """), {"org": org_id, "since": since})).one()
    hard_bounces, complaints = int(row[0] or 0), int(row[1] or 0)

    bounce_rate = (hard_bounces / sent) if sent else 0.0
    complaint_rate = (complaints / sent) if sent else 0.0
    return {
        "window_days": days,
        "sent": sent,
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
    tier = normalise_tier(getattr(org, "comms_tier", None))
    cap = tier_daily_cap(org)
    used = await sends_today(session, org_id=org.id)
    account_remaining = await account_daily_remaining(session)
    allowance = await send_allowance(session, org)
    metrics = await deliverability_metrics(session, org.id)
    tripped = breaker_reason(metrics)

    blocked = None
    if tier == TIER_SUSPENDED:
        blocked = "Sending is suspended for this club pending review."
    elif tripped:
        blocked = f"Sending is paused: {tripped}."
    elif account_remaining <= 0:
        blocked = "The platform's daily send limit is reached — try again tomorrow."
    elif cap is not None and used >= cap:
        blocked = (f"This club's daily limit of {cap} is reached — the rest will "
                   f"send tomorrow, or request a higher limit.")

    return {
        "tier": tier,
        "daily_cap": cap,
        "sent_today": used,
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
