"""A club whose free trial ended registers again: who did it, what the club did in the
24 hours before, and who we ring.

A lapsed club is registered like a new one (``auth.modules.trial_lapsed``), onto the
same club row, so its earlier admins keep their access. That makes every such
registration worth a person looking at it: it is a warm lead, and it may also be a
different person taking over the club. Every returning club is flagged. The 24 hour
read is context for whoever makes the call, not a filter.

Two steps, both fed by ``routers/self_serve_trial.submit``:

* ``capture_before`` runs BEFORE the registration touches the club row, because after it
  the new admin is on the club and the trial rows are overwritten. It answers None for a
  club that is not a lapsed trial, which is how ordinary registrations skip all of this.
* ``run`` is a background task that runs AFTER the registration commits (and after the CRM
  deal sync, which is queued first and runs first). It reads the activity, links the new
  person on the club's deal, emails ``STAFF_NOTIFY`` and saves the same text as a note on
  the deal. It opens its own session and never raises: a hiccup here must not undo a
  registration that already committed.

Nothing here is stored in a table of its own. The note on the deal is the record.
"""
from __future__ import annotations

import html
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, or_, select, text

from app.auth.modules import STATUS_TRIAL, sub_is_trial_expired, trial_lapsed
from app.config.settings import settings
from app.models.db import (
    ClubMembership, CrmActivity, CrmDeal, MarketingClub, OrgModuleSubscription,
    SelfServeIdempotencyKey, User, async_session_maker,
)
from app.services import email_service

logger = logging.getLogger(__name__)

# Who is told. The same two people the trial-extension requests go to.
STAFF_NOTIFY = ("jack@bettersports.com.au", "elton@bettersports.com.au")
WINDOW_HOURS = 24
_QUIET = ("page_exit", "heartbeat")   # beacons that say nothing about what a person did


def _admin_label(name: Optional[str], first: Optional[str], last: Optional[str], email: Optional[str]) -> str:
    return ((name or "").strip() or f"{first or ''} {last or ''}".strip() or (email or "").strip() or "Unknown")


async def capture_before(db, matched) -> Optional[dict]:
    """What the club looked like before it was registered again, or None when it is not a
    lapsed trial. Call before the registration changes the club row or its memberships."""
    if matched is None:
        return None
    rows = (await db.execute(
        select(OrgModuleSubscription).where(OrgModuleSubscription.organisation_id == matched.id)
    )).scalars().all()
    if not trial_lapsed(matched, rows):
        return None
    admins = (await db.execute(
        select(User.id, User.display_name, User.first_name, User.last_name, User.email,
               ClubMembership.is_primary_admin)
        .join(ClubMembership, ClubMembership.user_id == User.id)
        .where(ClubMembership.club_id == matched.id, ClubMembership.role == "club_admin")
        .order_by(ClubMembership.is_primary_admin.desc(), ClubMembership.created_at.asc())
    )).all()
    first_registered = await db.scalar(
        select(func.min(SelfServeIdempotencyKey.created_at)).where(SelfServeIdempotencyKey.org_id == matched.id))
    now = datetime.now(timezone.utc)
    ends = [r.trial_ends_at for r in rows if sub_is_trial_expired(r, now) and r.trial_ends_at]
    return {
        "org_id": matched.id,
        "club_name": matched.name,
        "slug": matched.slug,
        "first_registered_at": first_registered,
        "trial_ended_at": max(ends) if ends else None,
        "modules": sorted({r.module_key for r in rows}),
        "admins": [{
            "user_id": a.id, "name": _admin_label(a.display_name, a.first_name, a.last_name, a.email),
            "email": (a.email or "").strip().lower(), "primary": bool(a.is_primary_admin),
        } for a in admins],
    }


def _fmt(dt_value) -> str:
    return dt_value.astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC") if dt_value else "unknown"


def _day(dt_value) -> str:
    return dt_value.astimezone(timezone.utc).strftime("%d %b %Y") if dt_value else "unknown"


async def _read(session, label: str, sql: str, params: dict):
    """One activity read. A failed read is reported (None), never hidden as "no activity",
    and the session is rolled back so the next read is not poisoned (rule 12)."""
    try:
        return (await session.execute(text(sql), params)).mappings().all()
    except Exception:
        logger.exception("returning club follow-up: could not read %s", label)
        try:
            await session.rollback()
        except Exception:
            pass
        return None


async def gather_activity(session, *, snapshot: dict, registrant_email: str, visitor_id: Optional[str],
                          deal_ids: list, since: datetime, until: datetime) -> list[tuple[str, Optional[list[str]]]]:
    """The last 24 hours before the registration, as (heading, lines). ``lines`` of None
    means that read failed; an empty list means it ran and found nothing."""
    org = str(snapshot["org_id"])
    window = {"since": since, "until": until}
    admin_ids = [str(a["user_id"]) for a in snapshot["admins"]]
    emails = sorted({a["email"] for a in snapshot["admins"] if a["email"]} | ({registrant_email} if registrant_email else set()))
    out: list[tuple[str, Optional[list[str]]]] = []

    try:
        visitor = str(uuid.UUID(str(visitor_id))) if visitor_id else None
    except ValueError:
        visitor = None
    if visitor:
        rows = await _read(session, "the registrant's visits", """
            SELECT event_type, COALESCE(route, path) AS where_, count(*) AS n, max(created_at) AS last_at
            FROM usage_events
            WHERE visitor_id = CAST(:v AS uuid) AND created_at >= :since AND created_at < :until
              AND event_type <> ALL(CAST(:quiet AS text[]))
            GROUP BY 1, 2 ORDER BY n DESC, last_at DESC LIMIT 12
        """, {**window, "v": visitor, "quiet": list(_QUIET)})
        out.append(("The person who registered, on the site", None if rows is None else [
            f"{r['where_']} ({r['event_type']}): {r['n']}, last {_fmt(r['last_at'])}" for r in rows]))
    else:
        out.append(("The person who registered, on the site",
                    ["No visitor id came with the registration, so their browsing cannot be read."]))

    rows = await _read(session, "club activity", """
        SELECT event_type, COALESCE(route, path) AS where_, count(*) AS n,
               count(DISTINCT visitor_id) AS visitors, max(created_at) AS last_at
        FROM usage_events
        WHERE (org_id = CAST(:o AS uuid) OR user_id = ANY(CAST(:u AS uuid[])))
          AND created_at >= :since AND created_at < :until
          AND event_type <> ALL(CAST(:quiet AS text[]))
        GROUP BY 1, 2 ORDER BY n DESC, last_at DESC LIMIT 12
    """, {**window, "o": org, "u": admin_ids, "quiet": list(_QUIET)})
    out.append(("The club's own pages and its earlier admins", None if rows is None else [
        f"{r['where_']} ({r['event_type']}): {r['n']}, {r['visitors']} visitor(s), last {_fmt(r['last_at'])}" for r in rows]))

    rows = await _read(session, "club selections and searches", """
        SELECT route, count(*) AS n, count(DISTINCT visitor_id) AS visitors, max(created_at) AS last_at
        FROM usage_events
        WHERE event_type = 'self_serve_step' AND route IN ('club_prepared', 'club_searched')
          AND metadata->>'club_org_id' = :o AND created_at >= :since AND created_at < :until
        GROUP BY route ORDER BY route
    """, {**window, "o": org})
    out.append(("Searches for the club and picks of it on /trial", None if rows is None else [
        f"{'Picked the club' if r['route'] == 'club_prepared' else 'Searched for the club'}: {r['n']} time(s), "
        f"{r['visitors']} visitor(s), last {_fmt(r['last_at'])}" for r in rows]))

    rows = await _read(session, "enquiries", """
        SELECT name, email, source, left(coalesce(message, ''), 200) AS msg, created_at
        FROM club_onboarding_requests
        WHERE (club_org_id = :o OR lower(club) = lower(:name)) AND created_at >= :since AND created_at < :until
        ORDER BY created_at DESC LIMIT 5
    """, {**window, "o": org, "name": snapshot["club_name"]})
    out.append(("Contact form and extension requests", None if rows is None else [
        f"{r['name']} ({r['email']}), {r['source']}, {_fmt(r['created_at'])}" + (f": {r['msg']}" if r["msg"] else "")
        for r in rows]))

    rows = await _read(session, "email opens and clicks", """
        SELECT lower(email) AS email, event_type, count(*) AS n, max(created_at) AS last_at
        FROM email_events
        WHERE lower(email) = ANY(CAST(:e AS text[])) AND event_type IN ('open', 'click')
          AND created_at >= :since AND created_at < :until
        GROUP BY 1, 2 ORDER BY last_at DESC LIMIT 10
    """, {**window, "e": emails})
    out.append(("Our emails they opened or clicked", None if rows is None else [
        f"{r['email']}: {r['event_type']} x{r['n']}, last {_fmt(r['last_at'])}" for r in rows]))

    rows = await _read(session, "sales activity", """
        SELECT type, outcome, left(coalesce(body, ''), 160) AS body, occurred_at
        FROM crm_activities
        WHERE (organisation_id = CAST(:o AS uuid) OR deal_id = ANY(CAST(:d AS uuid[])))
          AND occurred_at >= :since AND occurred_at < :until
        ORDER BY occurred_at DESC LIMIT 5
    """, {**window, "o": org, "d": [str(d) for d in deal_ids]})
    out.append(("Calls and notes from our side", None if rows is None else [
        f"{r['type']}{' / ' + r['outcome'] if r['outcome'] else ''}, {_fmt(r['occurred_at'])}" + (f": {r['body']}" if r["body"] else "")
        for r in rows]))
    return out


def compose(*, snapshot: dict, registrant: dict, new_person: bool, trial_ends_at, attribution: Optional[dict],
            activity: list, deal_found: bool, until: datetime) -> tuple[str, str, str]:
    """(subject, plain text, html). One body, built once, used for the email and the note."""
    club = snapshot["club_name"]
    pages = f"{settings.public_base_url}/{snapshot['slug']}" if snapshot.get("slug") else ""
    sections: list[tuple[str, list[str]]] = []

    who = [f"{registrant['name']}", f"Email: {registrant['email']}"]
    if registrant.get("phone"):
        who.append(f"Phone: {registrant['phone']}")
    who.append("A new person: none of the club's earlier admins use this email." if new_person
               else "The same email as one of the club's earlier admins.")
    sections.append(("Who registered", who))

    earlier = [f"{a['name']} ({a['email'] or 'no email'}){', primary admin' if a['primary'] else ''}"
               for a in snapshot["admins"]] or ["None on record."]
    if new_person and snapshot["admins"]:
        earlier.append("They all keep their access. Check this is what the club intended.")
    sections.append(("Earlier admins", earlier))

    sections.append(("The club's history with us", [
        f"First registered: {_day(snapshot.get('first_registered_at'))}",
        f"Trial ended: {_day(snapshot.get('trial_ended_at'))}",
        f"Modules it had: {', '.join(snapshot['modules']) or 'none recorded'}",
        f"New trial runs to: {_day(trial_ends_at)}",
    ]))

    src = []
    if attribution:
        for key in ("utm_source", "utm_medium", "utm_campaign", "utm_content"):
            if attribution.get(key):
                src.append(f"{key}: {attribution[key]}")
    sections.append(("How they got here", src or ["No campaign tags came with the registration."]))

    for heading, lines in activity:
        if lines is None:
            sections.append((f"Last {WINDOW_HOURS} hours: {heading}", ["Could not be read. Check the server log."]))
        else:
            sections.append((f"Last {WINDOW_HOURS} hours: {heading}", lines or ["Nothing recorded."]))

    tail = []
    if not deal_found:
        tail.append("No CRM deal was found for this club, so nothing was written to the pipeline.")
    if pages:
        tail.append(f"Club page: {pages}")
    if tail:
        sections.append(("Notes", tail))

    head = (f"{club} has registered again after its trial ended on {_day(snapshot.get('trial_ended_at'))}. "
            f"Follow up personally. Activity below covers the {WINDOW_HOURS} hours before {_fmt(until)}.")
    subject = f"Returning club registered again: {club}"

    text_body = head + "\n\n" + "\n\n".join(
        f"{title}\n" + "\n".join(f"- {line}" for line in lines) for title, lines in sections) + "\n"
    esc = html.escape
    html_body = f"<p><strong>{esc(club)}</strong> {esc(head[len(club) + 1:])}</p>" + "".join(
        f'<h4 style="margin:14px 0 4px">{esc(title)}</h4><ul style="margin:0;padding-left:18px">'
        + "".join(f"<li>{esc(line)}</li>" for line in lines) + "</ul>"
        for title, lines in sections)
    return subject, text_body, html_body


async def _send(subject: str, text_body: str, html_body: str, reply_to: str) -> tuple[int, str]:
    """(sent count, a sentence for the note). The console provider only logs, so it is a
    failure we say out loud (rule 26)."""
    provider = email_service.get_email_provider()
    if provider.name == "console":
        logger.warning("Returning club follow-up not emailed: no live email provider is configured")
        return 0, "Staff email NOT sent: no live email provider is configured."
    sent = 0
    for to in STAFF_NOTIFY:
        try:
            result = await provider.send(email_service.EmailMessage(
                to_email=to, subject=subject, html=html_body, text=text_body,
                from_email=settings.email_from_address, from_name=settings.email_from_name,
                reply_to=reply_to or None,
            ))
            if result.ok:
                sent += 1
            else:
                logger.error("Returning club follow-up email to %s failed: %s", to, result.error)
        except Exception:
            logger.exception("Returning club follow-up email to %s failed", to)
    return sent, (f"Staff emailed ({sent} of {len(STAFF_NOTIFY)})." if sent
                  else "Staff email NOT sent: every send failed. See the server log.")


async def run(*, snapshot: dict, registrant: dict, visitor_id: Optional[str] = None,
              attribution: Optional[dict] = None, registered_at: Optional[datetime] = None) -> dict:
    """Background task. Never raises."""
    try:
        return await _run(snapshot=snapshot, registrant=registrant, visitor_id=visitor_id,
                          attribution=attribution, registered_at=registered_at)
    except Exception:
        logger.exception("returning club follow-up failed for %s", (snapshot or {}).get("club_name"))
        return {"error": "failed"}


async def _run(*, snapshot, registrant, visitor_id, attribution, registered_at) -> dict:
    from app.services import crm

    until = registered_at or datetime.now(timezone.utc)
    since = until - timedelta(hours=WINDOW_HOURS)
    org_id = snapshot["org_id"]
    reg_email = (registrant.get("email") or "").strip().lower()
    new_person = reg_email not in {a["email"] for a in snapshot["admins"]}

    async with async_session_maker() as session:
        club = await session.scalar(select(MarketingClub).where(MarketingClub.existing_org_id == org_id))
        conds = [CrmDeal.organisation_id == org_id]
        if club is not None:
            conds.append(CrmDeal.marketing_club_id == club.id)
        deals = (await session.execute(
            select(CrmDeal).where(CrmDeal.archived_at.is_(None), CrmDeal.scope == crm.SCOPE_PLATFORM, or_(*conds))
            .order_by(CrmDeal.created_at.desc())
        )).scalars().all()
        deal_id = deals[0].id if deals else None
        deal_ids = [d.id for d in deals]

        core = await session.scalar(
            select(OrgModuleSubscription.trial_ends_at).where(
                OrgModuleSubscription.organisation_id == org_id, OrgModuleSubscription.module_key == "core",
                OrgModuleSubscription.status == STATUS_TRIAL))

        activity = await gather_activity(
            session, snapshot=snapshot, registrant_email=reg_email, visitor_id=visitor_id,
            deal_ids=deal_ids, since=since, until=until)
        subject, text_body, html_body = compose(
            snapshot=snapshot, registrant=registrant, new_person=new_person, trial_ends_at=core,
            attribution=attribution, activity=activity, deal_found=deal_id is not None, until=until)

        sent, email_line = await _send(subject, text_body, html_body, reg_email)

        if deal_id is not None:
            # A failed read above rolls the session back, which expires everything loaded on it
            # (rule 12), so the deal is read again here rather than carried across.
            deal = await session.get(CrmDeal, deal_id)
            # The CRM sync that ran just before this leaves a deal's existing contact alone, so a
            # new person is linked here and made the point of contact. The earlier contact stays
            # linked, it only stops being the point of contact.
            if new_person:
                await crm.ensure_deal_contact(
                    session, deal, full_name=registrant.get("name") or snapshot["club_name"],
                    email=reg_email, phone=registrant.get("phone"), force=True)
            session.add(CrmActivity(
                deal_id=deal.id, organisation_id=org_id, type="note",
                body=f"{text_body}\n{email_line}\n",
                occurred_at=datetime.now(timezone.utc),
                meta={"kind": "returning_club_registered", "new_person": new_person,
                      "staff_emailed": sent, "window_hours": WINDOW_HOURS},
            ))
        await session.commit()
        return {"deal_id": str(deal_id) if deal_id else None, "emailed": sent, "new_person": new_person}
