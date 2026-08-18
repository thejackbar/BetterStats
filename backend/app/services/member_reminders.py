"""Reminder automation — qualification-expiry and fee-owing emails to
members via the self-service portal.

Gated per-club by platform_settings.member_portal_enabled_for_org — a club
where the flag is off gets no reminder emails at all, same as the portal
itself being invisible/unusable there. Each reminder kind is throttled via
its own `last_*_sent_at` column (migration 178) so the daily job can run
every day without re-sending: a row is only emailed again once
REMINDER_COOLDOWN_DAYS has passed since its last send.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.config.settings import settings
from app.models.db import (
    async_session_maker, Organisation, FeeMember, FeeMemberSeason,
    MemberQualification, QualificationType,
)
from app.services import email_pause, email_service
from app.services import fees as fee_service
from app.services import platform_settings as ps

logger = logging.getLogger(__name__)

QUALIFICATION_LOOKAHEAD_DAYS = 30
REMINDER_COOLDOWN_DAYS = 14


def _stale(sent_at) -> bool:
    if sent_at is None:
        return True
    now = datetime.now(timezone.utc)
    if sent_at.tzinfo is None:
        sent_at = sent_at.replace(tzinfo=timezone.utc)
    return (now - sent_at) >= timedelta(days=REMINDER_COOLDOWN_DAYS)


async def _send(to_email, to_name, club_name, subject, html, text):
    msg = email_service.EmailMessage(
        to_email=to_email, to_name=to_name, subject=subject, html=html, text=text,
        from_email=settings.email_from_address, from_name=club_name or settings.email_from_name,
        reply_to=settings.email_reply_to,
        # A daily scan sent this, not a person (services/email_pause).
        category=email_pause.CATEGORY_AUTOMATED,
    )
    return await email_service.get_email_provider().send(msg)


async def _remind_qualifications(session, org: Organisation) -> int:
    cutoff = date.today() + timedelta(days=QUALIFICATION_LOOKAHEAD_DAYS)
    rows = (await session.execute(
        select(MemberQualification, QualificationType, FeeMember)
        .join(QualificationType, QualificationType.id == MemberQualification.qualification_type_id)
        .join(FeeMember, FeeMember.id == MemberQualification.member_id)
        .where(MemberQualification.organisation_id == org.id,
              MemberQualification.expires_at.isnot(None), MemberQualification.expires_at <= cutoff,
              FeeMember.email.isnot(None))
    )).all()
    sent = 0
    for q, qtype, member in rows:
        if not _stale(q.last_reminder_sent_at):
            continue
        status_word = "has expired" if q.expires_at < date.today() else f"expires on {q.expires_at.isoformat()}"
        link = f"{settings.public_base_url}/portal/{org.slug}"
        html = (
            f"<p>Hi {member.full_name.split(' ')[0]},</p>"
            f"<p>Your <strong>{qtype.name}</strong> {status_word}.</p>"
            f'<p>Visit the <a href="{link}">{org.name} member portal</a> to check your details.</p>'
        )
        text = f"Hi {member.full_name},\n\nYour {qtype.name} {status_word}.\n\n{link}"
        result = await _send(member.email, member.full_name, org.name,
                             f"{qtype.name} — {status_word}", html, text)
        if result.ok:
            q.last_reminder_sent_at = datetime.now(timezone.utc)
            sent += 1
    return sent


async def _remind_fees(session, org: Organisation) -> int:
    season_id = await fee_service.latest_season_id(session, org.id)
    if season_id is None:
        return 0
    rows = (await session.execute(
        select(FeeMemberSeason, FeeMember)
        .join(FeeMember, FeeMember.id == FeeMemberSeason.member_id)
        .where(FeeMemberSeason.season_id == season_id, FeeMember.email.isnot(None))
    )).all()
    sent = 0
    for ms, member in rows:
        if not _stale(ms.last_fee_reminder_sent_at):
            continue
        snapshot = await fee_service.member_financial_snapshot(session, org.id, member.id, season_id)
        if snapshot is None or snapshot["financials"]["total_outstanding"] <= 0:
            continue
        owing = snapshot["financials"]["total_outstanding"]
        link = f"{settings.public_base_url}/portal/{org.slug}"
        html = (
            f"<p>Hi {member.full_name.split(' ')[0]},</p>"
            f"<p>You have <strong>${owing:.2f}</strong> outstanding in club fees.</p>"
            f'<p>Visit the <a href="{link}">{org.name} member portal</a> to view and pay online.</p>'
        )
        text = f"Hi {member.full_name},\n\nYou have ${owing:.2f} outstanding in club fees.\n\n{link}"
        result = await _send(member.email, member.full_name, org.name,
                             f"{org.name} — ${owing:.2f} outstanding", html, text)
        if result.ok:
            ms.last_fee_reminder_sent_at = datetime.now(timezone.utc)
            sent += 1
    return sent


async def send_all_reminders() -> dict:
    """Daily scan across every club with the member portal switched on.
    Never raises — logs and moves to the next club so one bad row/email
    provider hiccup can't take out the whole run."""
    stats = {"orgs_scanned": 0, "qualification_reminders": 0, "fee_reminders": 0}
    async with async_session_maker() as session:
        orgs = (await session.execute(select(Organisation))).scalars().all()
        for org in orgs:
            try:
                if not await ps.member_portal_enabled_for_org(session, org):
                    continue
                stats["orgs_scanned"] += 1
                stats["qualification_reminders"] += await _remind_qualifications(session, org)
                stats["fee_reminders"] += await _remind_fees(session, org)
                await session.commit()
            except Exception:
                logger.exception("member reminder scan failed for org %s", org.id)
                await session.rollback()
    return stats
