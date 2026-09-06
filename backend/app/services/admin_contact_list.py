"""Every club admin, on one internal BetterComms list.

BetterCricket needs to be able to email the people who actually administer the
clubs on the platform — a release note, a billing change, a heads-up that a
trial is finishing. That audience is not something a super admin should have to
remember to maintain by hand, so a club admin lands on the list the moment they
become one: a self-serve registration, a super admin creating a club and naming
its primary admin, a primary admin being reassigned, or an admin being added to
a club that already exists.

  * ``sync`` is the whole job — upsert the contacts, then put them on the list.
    Idempotent, so the live hooks and the backfill script are the same code
    running over different scopes.
  * ``queue_sync`` is the fire-and-forget wrapper the routers call AFTER their
    own commit, on its own session. A failure to update an internal marketing
    list must never take down a club registration, and it never shares the
    caller's transaction — the trap this file's neighbours document, where a
    swallowed error leaves the request's transaction aborted and the commit
    that actually matters fails behind it.

**UPSERT ONLY — nothing here ever removes anybody.** Losing the club_admin role
does not take a person off the list, because the list is a record of who has
administered a club, and quietly dropping a recipient is a decision for a person
to make on the Lists screen.

**An opt-out is never overridden.** A contact that has unsubscribed, hard
bounced, complained or been excluded is upserted (so their row stays current)
but is NOT put back on the list — services/comms_lists.py removes a suppressed
contact from every list, and re-adding them here would fight it every run.
``comms_segments.sendable_where`` is the one definition of "can be sent to" and
is what decides.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import (
    ClubMembership, CommsContact, CommsList, CommsListMember, EmailSuppression,
    MarketingClub, Organisation, User,
)
from app.services import comms_contacts as contacts_svc
from app.services.marketing_org import get_outreach_org

logger = logging.getLogger(__name__)

#: The list every club admin is kept on, in BetterCricket's own outreach org.
#: Matched by name, so a list a super admin already created by hand is ADOPTED
#: rather than duplicated (comms_lists is unique on (organisation_id, name)).
LIST_NAME = "Super Admin User Contact List"
#: What the Lists screen shows under an auto list's name, saying what made it.
ORIGIN_LABEL = "Club Admin Users"
#: comms_contacts.source for a row this creates. Not player/member/import/manual
#: — a club admin is a platform user, and the Contacts page renders the raw
#: value, so it stays short enough to read as a chip.
CONTACT_SOURCE = "admin"

#: Held so a fire-and-forget task isn't garbage collected mid-flight — the same
#: guard club_admin._push_club_to_twenty keeps.
_tasks: set = set()


async def ensure_list(session: AsyncSession, organisation_id) -> CommsList:
    """The list, created if it isn't there. An existing list of this name is
    adopted as-is: its ``source``/``origin`` are left alone, because a list a
    person made by hand is theirs and this only fills it."""
    existing = (await session.execute(select(CommsList).where(
        CommsList.organisation_id == organisation_id, CommsList.name == LIST_NAME
    ))).scalar_one_or_none()
    if existing is not None:
        return existing
    lst = CommsList(organisation_id=organisation_id, name=LIST_NAME,
                    source="auto", origin=ORIGIN_LABEL)
    session.add(lst)
    await session.flush()
    return lst


async def admin_rows(session: AsyncSession, *, club_id=None) -> list:
    """Every club-admin user, as ``(User, ClubMembership, Organisation)``.

    ``role == 'club_admin'`` covers both halves of what was asked: the primary
    admin is that same role carrying ``is_primary_admin``, not a role of its own.
    A super_admin / sales membership is BetterCricket's own staff and is not a
    club admin, so neither is included.

    An ARCHIVED club is left out. Its admin is no longer running a club on the
    platform, and archiving is the house rule for "stop treating this club as
    live" everywhere else (the sync scheduler and the Twenty pushes both skip
    them). They stay on the list if they are already on it — nothing here
    removes anybody — they just stop being added by a later run.
    """
    q = (
        select(User, ClubMembership, Organisation)
        .join(ClubMembership, ClubMembership.user_id == User.id)
        .join(Organisation, Organisation.id == ClubMembership.club_id)
        .where(ClubMembership.role == "club_admin", Organisation.archived_at.is_(None))
        .order_by(ClubMembership.is_primary_admin.desc(), User.created_at.asc())
    )
    if club_id is not None:
        q = q.where(ClubMembership.club_id == club_id)
    return list((await session.execute(q)).all())


def _display_name(user: User) -> Optional[str]:
    """What the contact is called. ``display_name`` first (what the club typed),
    then first + last from the registration form. Never derived from the email —
    the outreach org deliberately greets blank rather than guessing a name out of
    an address (see routers/comms._first_name)."""
    name = (user.display_name or "").strip()
    if name:
        return name
    parts = [(user.first_name or "").strip(), (user.last_name or "").strip()]
    joined = " ".join(p for p in parts if p).strip()
    return joined or None


async def _marketing_club_by_org(session: AsyncSession, org_ids) -> dict:
    """organisation_id -> the Clubs Directory row for it, batched.

    Linking the contact to it is what makes {{club}}, {{association}}, {{state}}
    and the trial figures ({{trial_days_left}} and friends) resolve for these
    recipients — an email to club admins about their trial is exactly the thing
    this list exists for, and without the link every one of those tokens would
    render blank.
    """
    ids = [i for i in set(org_ids or ()) if i]
    if not ids:
        return {}
    rows = (await session.execute(
        select(MarketingClub).where(MarketingClub.existing_org_id.in_(ids))
        .order_by(MarketingClub.existing_org_id, MarketingClub.id)
    )).scalars().all()
    out = {}
    for mc in rows:
        # First per org, deterministically — existing_org_id carries no unique
        # constraint, so two directory rows can point at one club.
        out.setdefault(mc.existing_org_id, mc)
    return out


async def sync(session: AsyncSession, *, club_id=None, apply: bool = True) -> dict:
    """Upsert every club admin as a contact and put them on the list.

    ``club_id`` narrows it to one club (what the live hooks pass); omitted, it is
    the whole platform (what the backfill script runs). ``apply=False`` reports
    what would change and writes nothing, for the script's dry run.

    Does NOT commit — ``queue_sync`` and the script each own their transaction.
    """
    outreach = await get_outreach_org(session)
    if outreach is None:
        # Same posture as every other BetterCricket-side integration: no
        # outreach org designated yet means there is nowhere for this to go,
        # which is a configuration state, not a failure.
        return {"status": "no_outreach_org"}

    rows = await admin_rows(session, club_id=club_id)
    mc_by_org = await _marketing_club_by_org(session, [org.id for _, _, org in rows])

    added = updated = 0
    no_email: list[str] = []
    wanted: dict[str, dict] = {}
    for user, membership, org in rows:
        email = (user.email or "").strip().lower()
        if not email:
            # A club admin with no address on file cannot be emailed. Counted
            # rather than dropped silently — that number is what tells a super
            # admin the list is short of the roster.
            no_email.append(user.username or str(user.id))
            continue
        # First membership wins for the name/club, and admin_rows orders primary
        # first, so a person who somehow administers two clubs is filed under the
        # one they own rather than whichever sorted first.
        wanted.setdefault(email, {
            "name": _display_name(user),
            "marketing_club_id": (mc_by_org.get(org.id).id if mc_by_org.get(org.id) else None),
        })

    # Who is already on file. In apply mode every wanted address has a row by
    # the end of this; in a dry run only the pre-existing ones do, which is what
    # the projection below has to account for.
    known = set((await session.execute(select(CommsContact.email).where(
        CommsContact.organisation_id == outreach.id,
        CommsContact.email.in_(wanted.keys()),
    ))).scalars().all()) if wanted else set()
    fresh = set(wanted) - known
    added, updated = len(fresh), len(known)

    if apply:
        for email, info in wanted.items():
            await contacts_svc.upsert_contact(
                session, outreach.id, email, info["name"], CONTACT_SOURCE,
                marketing_club_id=info["marketing_club_id"])
        await session.flush()

    listed, suppressed = 0, 0
    if wanted:
        # Only a contact that can actually be sent to goes on the list. The gate
        # is comms_segments' own, so "on this list" can never mean something
        # different from "reachable by a send".
        from app.services.comms_segments import sendable_where
        sendable = set((await session.execute(select(CommsContact.id).where(
            *sendable_where(outreach.id), CommsContact.email.in_(wanted.keys())
        ))).scalars().all())
        on_file = set((await session.execute(select(CommsContact.id).where(
            CommsContact.organisation_id == outreach.id,
            CommsContact.email.in_(wanted.keys()),
        ))).scalars().all())
        suppressed = len(on_file - sendable)
        lst = None
        if apply:
            lst = await ensure_list(session, outreach.id)
        else:
            lst = (await session.execute(select(CommsList).where(
                CommsList.organisation_id == outreach.id, CommsList.name == LIST_NAME
            ))).scalar_one_or_none()
        already = set((await session.execute(select(CommsListMember.contact_id).where(
            CommsListMember.list_id == lst.id,
            CommsListMember.contact_id.in_(sendable),
        ))).scalars().all()) if (lst is not None and sendable) else set()
        missing = sendable - already
        listed = len(missing)
        if apply:
            for cid in missing:
                session.add(CommsListMember(list_id=lst.id, contact_id=cid))
        else:
            # A contact that does not exist yet cannot be queried for, so project
            # it: a brand-new row is subscribed by construction and is only
            # unreachable if the ADDRESS itself is globally suppressed. Without
            # this the dry run reports "0 to add" for a run that would in fact
            # add every one of them, which reads as nothing to do.
            blocked = set((await session.execute(select(func.lower(EmailSuppression.email))
                                                 .where(func.lower(EmailSuppression.email).in_(fresh))
                                                 )).scalars().all()) if fresh else set()
            listed += len(fresh - blocked)
            suppressed += len(blocked)

    return {
        "status": "ok",
        "list_name": LIST_NAME,
        "admins": len(rows),
        "emails": len(wanted),
        "contacts_added": added,
        "contacts_updated": updated,
        "list_added": listed,
        "suppressed": suppressed,
        "no_email": no_email,
    }


async def run_sync(club_id=None) -> None:
    """:func:`sync` on its own session, committing, and never raising.

    THE one place the live hooks run through, so a marketing-list failure can
    never reach the request that created the admin — and it never shares the
    caller's transaction, which is what stops a swallowed database error leaving
    that transaction aborted and failing the commit that actually matters.

    Pass it to ``background_tasks.add_task`` where the commit happens after your
    code returns; use :func:`queue_sync` where you have an explicit post-commit
    point of your own.
    """
    try:
        from app.models.db import async_session_maker
        async with async_session_maker() as session:
            result = await sync(session, club_id=club_id)
            await session.commit()
            if result.get("status") == "no_outreach_org":
                logger.info("admin contact list: no outreach org designated, skipped")
    except Exception:
        logger.exception("admin contact list sync failed (club_id=%s)", club_id)


def queue_sync(club_id=None) -> None:
    """Fire-and-forget :func:`run_sync`.

    CALL IT AFTER YOUR OWN COMMIT. The task starts immediately and reads its own
    session, so a membership the caller has not committed yet is simply not there
    — the sync would find nothing and quietly do nothing, which is the one way
    this can silently fail to do its job.
    """
    task = asyncio.create_task(run_sync(club_id))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
