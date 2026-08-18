"""Club Diary — optional reminder emails to the person responsible for a
recurring task, ahead of its due date.

Opt-in PER TASK DEFINITION (DiaryTaskDefinition.reminder_enabled, off by
default) — not a club-wide switch, and not gated by any paid-module or
platform flag the way the member-portal reminders are, since Club Diary
itself is an always-on core feature. Most clubs will leave every task's
reminder off and just check the Board view; this only fires for the ones an
admin has explicitly turned on.

Recipient is whoever the OCCURRENCE is currently assigned to (not the
definition's default assignee — an admin may have re-assigned this
period's task to someone else). No login link is included: a diary
assignee is a FeeMember, not necessarily a User with any app access, so the
email is a plain FYI, not an actionable in-app link.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.config.settings import settings
from app.models.db import async_session_maker, Organisation, FeeMember, DiaryTaskDefinition, DiaryTaskOccurrence
from app.services import email_pause, email_service

logger = logging.getLogger(__name__)

# Once sent, don't send again for at least this many days — a task with a
# long reminder_days_before lead time would otherwise get emailed daily.
REMINDER_COOLDOWN_DAYS = 7


def _stale(sent_at) -> bool:
    if sent_at is None:
        return True
    now = datetime.now(timezone.utc)
    if sent_at.tzinfo is None:
        sent_at = sent_at.replace(tzinfo=timezone.utc)
    return (now - sent_at) >= timedelta(days=REMINDER_COOLDOWN_DAYS)


async def _send_reminders_for_org(session, org: Organisation, today: date) -> int:
    rows = (await session.execute(
        select(DiaryTaskOccurrence, DiaryTaskDefinition, FeeMember)
        .join(DiaryTaskDefinition, DiaryTaskDefinition.id == DiaryTaskOccurrence.definition_id)
        .join(FeeMember, FeeMember.id == DiaryTaskOccurrence.assigned_to_member_id)
        .where(
            DiaryTaskOccurrence.organisation_id == org.id,
            DiaryTaskDefinition.reminder_enabled.is_(True),
            DiaryTaskOccurrence.due_date.isnot(None),
            DiaryTaskOccurrence.status.notin_(("done", "not_applicable")),
            FeeMember.email.isnot(None),
        )
    )).all()
    sent = 0
    for occ, defn, member in rows:
        lead_days = defn.reminder_days_before or 14
        if (occ.due_date - today).days > lead_days:
            continue  # not due soon enough yet
        if not _stale(occ.last_reminder_sent_at):
            continue

        overdue = occ.due_date < today
        status_word = "is overdue" if overdue else f"is due on {occ.due_date.isoformat()}"
        first_name = (member.full_name or "").split(" ")[0] or "there"
        html = (
            f"<p>Hi {first_name},</p>"
            f"<p><strong>{defn.title}</strong> {status_word} — you're the person responsible for it "
            f"in the {org.name} Club Diary.</p>"
            + (f"<p>{defn.description}</p>" if defn.description else "")
        )
        text = f"Hi {first_name},\n\n{defn.title} {status_word} — you're responsible for it in the {org.name} Club Diary."
        msg = email_service.EmailMessage(
            to_email=member.email, to_name=member.full_name,
            subject=f"{org.name} Club Diary — {defn.title} {status_word}",
            html=html, text=text,
            from_email=settings.email_from_address, from_name=org.name or settings.email_from_name,
            reply_to=settings.email_reply_to,
            # A daily scan sent this, not a person (services/email_pause).
            category=email_pause.CATEGORY_AUTOMATED,
        )
        result = await email_service.get_email_provider().send(msg)
        if result.ok:
            occ.last_reminder_sent_at = datetime.now(timezone.utc)
            sent += 1
    return sent


async def send_all_diary_reminders() -> dict:
    """Daily scan across every club. Never raises — logs and moves to the
    next club so one bad row/email provider hiccup can't take out the whole
    run."""
    stats = {"orgs_scanned": 0, "reminders_sent": 0}
    today = date.today()
    async with async_session_maker() as session:
        orgs = (await session.execute(select(Organisation))).scalars().all()
        for org in orgs:
            stats["orgs_scanned"] += 1
            try:
                stats["reminders_sent"] += await _send_reminders_for_org(session, org, today)
                await session.commit()
            except Exception:
                logger.exception("club diary reminder scan failed for org %s", org.id)
                await session.rollback()
    return stats
