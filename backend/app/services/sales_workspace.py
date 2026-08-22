"""Sales Workspace — Phase 1: a club-queue + calling lens over the existing
BetterCRM engine (services/crm.py).

Deliberately NOT a parallel schema. A "club" here is a ``crm_deals`` row
(``scope='platform'``) — the exact same row the Sales Pipeline board
(``/admin/super/crm``) already manages — so a deal's stage/owner/history is
identical whichever screen it's viewed from. This module adds three things
the Pipeline board doesn't need: a structured call-outcome vocabulary, a
merged contacts view (Club Directory + CRM-only contacts), and the handful
of small stage-transition rules a phone-first workflow wants automatically.

Contacts are never forked into a third table. ``marketing_club_contacts``
(Club Directory) stays canonical; a ``crm_people`` row for the SAME person
may already exist (created by a different flow — e.g. a trial registration)
or gets lazily materialized the first time a call is logged against a
directory-only contact, bridged via ``crm_people.directory_contact_id``
(migration 255) so neither one duplicates the other.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import (
    ClubMembership, CrmActivity, CrmDeal, CrmPerson, CrmStage, MarketingClub,
    MarketingClubContact, SalesList, SalesListClub, User,
)
from app.services import crm as crm_service

# ─── Call outcome taxonomy ───────────────────────────────────────────────────
# Flat controlled vocabulary (validated here, not a DB enum — same posture as
# services/scouting_intel.py's controlled vocabularies elsewhere in this
# codebase). `category` drives the grouped dropdown + the stage-transition
# rules below; it is never stored — only `key` is persisted on the activity.
CALL_OUTCOMES: dict[str, dict] = {
    # Unsuccessful contact
    "no_answer": {"label": "No answer", "category": "unsuccessful"},
    "voicemail": {"label": "Voicemail", "category": "unsuccessful"},
    "invalid_number": {"label": "Invalid number", "category": "unsuccessful"},
    "wrong_person": {"label": "Wrong person", "category": "unsuccessful"},
    "number_disconnected": {"label": "Number disconnected", "category": "unsuccessful"},
    "no_longer_at_club": {"label": "Person no longer at club", "category": "unsuccessful"},
    # Neutral
    "spoke_no_decision": {"label": "Spoke — no decision", "category": "neutral"},
    "asked_callback": {"label": "Asked to call back", "category": "neutral"},
    "referred_to_other": {"label": "Referred to another person", "category": "neutral"},
    "requested_information": {"label": "Requested information", "category": "neutral"},
    # Positive
    "wants_to_subscribe": {"label": "Wants to buy/subscribe now", "category": "positive"},
    "interested": {"label": "Interested", "category": "positive"},
    "wants_more_info": {"label": "Wants more information", "category": "positive"},
    "wants_trial": {"label": "Wants trial", "category": "positive"},
    "wants_trial_extension": {"label": "Wants a trial extension", "category": "positive"},
    "wants_demo": {"label": "Wants demo", "category": "positive"},
    "wants_pricing": {"label": "Wants to discuss pricing", "category": "positive"},
    "wants_committee_discussion": {"label": "Wants committee discussion", "category": "positive"},
    # Negative
    "not_interested": {"label": "Not interested", "category": "negative"},
    "using_alternative": {"label": "Already using an alternative", "category": "negative"},
    "dont_call_again": {"label": "Don't call again", "category": "negative"},
    "remove_from_list": {"label": "Remove from list", "category": "negative"},
    # Administrative
    "duplicate": {"label": "Duplicate", "category": "administrative"},
    "club_inactive": {"label": "Club inactive", "category": "administrative"},
    "wrong_club": {"label": "Wrong club", "category": "administrative"},
    "contact_details_updated": {"label": "Contact details updated", "category": "administrative"},
    # General — not a call outcome as such, just something worth noting
    # against the club without claiming a call was made or how it went.
    "general_note": {"label": "General Note", "category": "general"},
}

# The 'general' category is NOT a call, and that is the whole point of it:
# it records something worth noting against the club without claiming anyone
# was spoken to. So it must not mark the club as called — a rep jotting a
# note down had the club vanish out of the default queue (which lists clubs
# never called) and, on a Target deal, silently moved it to Contacted. Both
# followed from the row being written as type='call'; see log_call.
GENERAL_OUTCOMES = frozenset(k for k, v in CALL_OUTCOMES.items() if v["category"] == "general")

CATEGORY_ORDER = ("positive", "neutral", "unsuccessful", "negative", "administrative", "general")
CATEGORY_LABELS = {
    "positive": "Positive", "neutral": "Neutral", "unsuccessful": "Unsuccessful contact",
    "negative": "Negative", "administrative": "Administrative", "general": "General",
}

# Outcomes that lose a deal outright — stage moves to lost_dormant, status='lost'.
_LOST_OUTCOMES = ("not_interested", "dont_call_again", "remove_from_list")
# Stages a deal can still be auto-advanced FROM on a positive outcome — never
# regresses a deal already at engaged/trial/proposal/won.
_ADVANCEABLE_STAGE_KEYS = ("manually_added", "target", "contacted")

# Outcomes that also mean "stop contacting this person/club", not merely
# "we didn't win this cycle" — deliberately narrower than _LOST_OUTCOMES.
# 'not_interested' closes the deal (see _LOST_OUTCOMES above) but a club
# not interested in trialling TODAY is legitimately worth another look in
# six months, so it does NOT flip do_not_contact/not_interested on its own —
# only an explicit stop request does.
_DO_NOT_CONTACT_OUTCOMES = ("dont_call_again", "remove_from_list")

# Outcomes worth a real calendar reminder, not just the queue's own
# next_follow_up_at tag — every kind of "this needs a deliberate next step
# with a person", per direct instruction. Deliberately excludes
# 'spoke_no_decision' (the one neutral outcome with nothing concrete to
# follow up ON) and everything unsuccessful/negative/administrative.
_EVENT_WORTHY_OUTCOMES = (
    "wants_to_subscribe", "interested", "wants_more_info", "wants_trial", "wants_trial_extension",
    "wants_demo", "wants_pricing", "wants_committee_discussion", "asked_callback",
    "referred_to_other", "requested_information",
)

# Default event note per outcome when the call itself carried no free-text
# notes — {name} is the followed-up contact's name, filled in at creation.
_FOLLOW_UP_NOTE_TEMPLATES = {
    "wants_to_subscribe": "Follow up with {name} — ready to buy/subscribe now.",
    "interested": "Follow up with {name} — interested in BetterCricket.",
    "wants_more_info": "Follow up with {name} — wants more information.",
    "wants_trial": "Follow up with {name} — wants to start a trial.",
    "wants_trial_extension": "Follow up with {name} — wants a trial extension.",
    "wants_demo": "Follow up with {name} — wants a demo.",
    "wants_pricing": "Follow up with {name} — wants to discuss pricing.",
    "wants_committee_discussion": "Follow up with {name} following his committee meeting.",
    "asked_callback": "Callback requested by {name}.",
    "referred_to_other": "Follow up with {name} — referred to another contact.",
    "requested_information": "Follow up with {name} — requested more information.",
}


# The six modules a rep can flag a club as interested in — same keys/order
# components/admin/crm/ui.jsx's MODULE_ORDER uses, kept independent (not
# imported) since that's frontend-only; billing_pricing.py is the backend's
# own source of truth for the four priced bolt-ons + core + fantasy, so this
# is just their union rather than a fourth definition of "what's a module".
VALID_MODULE_KEYS = {"core", "select", "socials", "admin", "iq", "fantasy"}


def outcome_options() -> list[dict]:
    """The vocabulary, grouped for a dropdown — CATEGORY_ORDER first."""
    return [
        {
            "category": cat,
            "label": CATEGORY_LABELS[cat],
            "options": [
                {"key": k, "label": v["label"]}
                for k, v in CALL_OUTCOMES.items() if v["category"] == cat
            ],
        }
        for cat in CATEGORY_ORDER
    ]


# ─── Contacts: merge Club Directory + CRM-only, never fork ──────────────────

async def merged_contacts(session: AsyncSession, marketing_club_id) -> list[dict]:
    """Every contact worth showing for this club: Club Directory contacts
    (canonical) plus any CRM-only contact (e.g. a trial registrant, or
    someone added straight into CRM) that isn't already represented by one.
    Deduped on lower(email); a directory row wins the merge when both exist
    for the same address, since it carries role/role_rank/opt-out state the
    CRM-only row doesn't. Each row is tagged `origin` so the drawer can show
    where it came from."""
    if marketing_club_id is None:
        return []

    directory_rows = (await session.execute(
        select(MarketingClubContact)
        .where(MarketingClubContact.marketing_club_id == marketing_club_id)
        .order_by(MarketingClubContact.role_rank.asc())
    )).scalars().all()
    crm_rows = (await session.execute(
        select(CrmPerson).where(CrmPerson.marketing_club_id == marketing_club_id)
    )).scalars().all()

    by_email: dict[str, dict] = {}
    out: list[dict] = []

    for c in directory_rows:
        key = (c.email or "").strip().lower() or None
        row = {
            "origin": "directory",
            "directory_contact_id": str(c.id),
            "crm_person_id": None,
            "full_name": c.full_name,
            "role": c.role,
            "role_rank": c.role_rank,
            "email": c.email,
            "mobile": c.mobile,
            "subscribed": c.subscribed,
            "do_not_email": bool(c.unsubscribed_at) or bool(c.bounced) or not c.subscribed,
            "do_not_contact": bool(c.do_not_contact),
            "do_not_contact_reason": c.do_not_contact_reason,
        }
        out.append(row)
        if key:
            by_email[key] = row

    for p in crm_rows:
        key = (p.email or "").strip().lower() or None
        if key and key in by_email:
            # Already represented by a directory row for the same address —
            # attach the crm_person_id so a call can still be logged against
            # this exact person without minting a duplicate.
            by_email[key]["crm_person_id"] = str(p.id)
            continue
        if p.directory_contact_id and any(
            r["directory_contact_id"] == str(p.directory_contact_id) for r in out
        ):
            # Already materialized from a directory row we're already showing
            # (email may have changed/been blank at either end) — attach, don't duplicate.
            for r in out:
                if r["directory_contact_id"] == str(p.directory_contact_id):
                    r["crm_person_id"] = str(p.id)
            continue
        out.append({
            "origin": "crm",
            "directory_contact_id": None,
            "crm_person_id": str(p.id),
            "full_name": p.full_name,
            "role": None,
            "role_rank": 99,
            "email": p.email,
            "mobile": p.phone,
            "subscribed": None,
            "do_not_email": False,
            "do_not_contact": False,
            "do_not_contact_reason": None,
        })

    out.sort(key=lambda r: (r["role_rank"] if r["role_rank"] is not None else 99))
    return out


async def resolve_or_materialize_person(
    session: AsyncSession, *, marketing_club_id, directory_contact_id=None, crm_person_id=None,
) -> CrmPerson:
    """Returns the CrmPerson a call should be logged against. A picked
    crm_person_id resolves directly. A picked directory_contact_id first
    checks for an EXISTING crm_people row (already bridged, or matching on
    (marketing_club_id, lower(email)) — e.g. minted by a different flow such
    as trial registration) before creating a new one, so the same real
    person is never represented twice."""
    if crm_person_id:
        person = await session.get(CrmPerson, crm_person_id)
        if person is None:
            raise ValueError("Contact not found")
        return person

    if not directory_contact_id:
        raise ValueError("A contact must be specified")

    contact = await session.get(MarketingClubContact, directory_contact_id)
    if contact is None or str(contact.marketing_club_id) != str(marketing_club_id):
        raise ValueError("Contact not found")

    existing = await session.scalar(
        select(CrmPerson).where(CrmPerson.directory_contact_id == contact.id)
    )
    if existing:
        return existing

    email = (contact.email or "").strip().lower() or None
    if email:
        existing = await session.scalar(
            select(CrmPerson).where(
                CrmPerson.marketing_club_id == marketing_club_id,
                func.lower(CrmPerson.email) == email,
            )
        )
        if existing:
            # Found via another flow (e.g. a trial registration) — bridge it
            # to the directory row rather than minting a second person.
            existing.directory_contact_id = contact.id
            await session.flush()
            return existing

    person = CrmPerson(
        marketing_club_id=marketing_club_id,
        full_name=contact.full_name or "Unknown",
        email=contact.email,
        phone=contact.mobile,
        directory_contact_id=contact.id,
    )
    session.add(person)
    await session.flush()
    return person


async def add_directory_contact(
    session: AsyncSession, *, marketing_club_id, full_name: str, role: Optional[str],
    email: Optional[str], mobile: Optional[str],
) -> MarketingClubContact:
    """A new person added from the Workspace drawer — writes straight to the
    canonical Club Directory table via the same upsert helper the crawler
    and the Directory screen itself use, so it's indistinguishable from a
    directory-sourced contact afterwards."""
    from app.services.club_directory import _store_contact
    await _store_contact(
        session, marketing_club_id, full_name=full_name, role=role or "Contact",
        role_rank=99, email=email, phone=mobile, selected=True,
    )
    await session.flush()
    email_norm = (email or "").strip().lower()
    if email_norm:
        return await session.scalar(
            select(MarketingClubContact).where(
                MarketingClubContact.marketing_club_id == marketing_club_id,
                func.lower(MarketingClubContact.email) == email_norm,
            )
        )
    # No email — _store_contact dedupes a phone-only contact on (club, name)
    # instead, so look it up the same way.
    return await session.scalar(
        select(MarketingClubContact).where(
            MarketingClubContact.marketing_club_id == marketing_club_id,
            MarketingClubContact.email.is_(None),
            func.lower(MarketingClubContact.full_name) == full_name.strip().lower(),
        )
    )


# ─── Commission attribution ───────────────────────────────────────────────────
#
# ASSIGNMENT IS NOT ATTRIBUTION, and keeping the two apart is the whole point.
# `crm_deals.owner_user_id` says who is working a club right now, and a super
# admin can move it back to the unassigned pool or over to another rep at
# will. Attribution says which rep EARNED the club, for commission. It is set
# ONCE, by the first qualifying action, and a later reassignment never moves
# it — that is what stops a rep's work being handed to whoever happens to
# hold the club at payout time.
#
# Only two actions qualify, and both mean the rep actually went at the club:
# logging a call outcome, or sending an email to one of its contacts. What
# does NOT qualify: being assigned the club, adding a note, and logging the
# General Note outcome. Those last two are someone writing something down.
#
# Only a SALES rep can be attributed. A super admin working a club is doing
# sales ops, not earning commission on it.

COMMISSION_VIA_CALL = "call"
COMMISSION_VIA_EMAIL = "email"


async def attribute_commission(session: AsyncSession, *, deal: CrmDeal, actor_user_id,
                               actor_role: str, via: str) -> bool:
    """Stamps `deal` as earned by this rep, if it is not already earned and
    the actor is one. Returns whether it stamped. First action wins: an
    already-attributed deal is left exactly as it is, including when the same
    rep acts again, so `commission_attributed_at` stays the moment the club
    was actually won rather than creeping forward."""
    if actor_role != "sales" or actor_user_id is None:
        return False
    if deal.commission_rep_user_id is not None:
        return False
    deal.commission_rep_user_id = actor_user_id
    deal.commission_attributed_at = datetime.now(timezone.utc)
    deal.commission_attributed_via = via
    await session.flush()
    return True


def commission_reassign_blocked(deal: CrmDeal, new_owner_id) -> bool:
    """True when moving this deal to `new_owner_id` needs the super admin to
    confirm first: the club is attributed, and this hands it somewhere other
    than the rep who earned it (including back to the unassigned pool).
    Re-assigning it TO its attributing rep is not a change worth querying."""
    if deal.commission_rep_user_id is None:
        return False
    return str(new_owner_id or "") != str(deal.commission_rep_user_id)


def commission_confirm_message(rep_name: Optional[str]) -> str:
    return (f"This club has been attributed to {rep_name or 'a sales rep'} - "
            "do you really want to change the club's assignment?")


async def commission_rep_names(session: AsyncSession, deals) -> dict:
    """user_id -> display name, for whichever deals in `deals` are attributed.
    One query, so a bulk reassignment can name every rep it is about to move
    a club away from."""
    ids = {d.commission_rep_user_id for d in deals if d.commission_rep_user_id}
    if not ids:
        return {}
    rows = (await session.execute(select(User).where(User.id.in_(ids)))).scalars().all()
    return {u.id: (u.display_name or u.username) for u in rows}


async def user_names_by_ids(session: AsyncSession, ids) -> dict:
    """user_id -> display name, batched. Every write on a deal — a call log,
    a note, an email send, an assign, a bulk assign, an extend-trial — already
    stamps `created_by_user_id` on its activity row; this is the one place
    that id becomes a name for the History feed to show ("logged by …"),
    without a per-row lookup."""
    ids = {i for i in ids if i}
    if not ids:
        return {}
    rows = (await session.execute(select(User).where(User.id.in_(ids)))).scalars().all()
    return {u.id: (u.display_name or u.username) for u in rows}


# ─── Calls ────────────────────────────────────────────────────────────────────

async def log_call(
    session: AsyncSession, *, deal: CrmDeal, person: Optional[CrmPerson], outcome: str,
    notes: Optional[str], next_follow_up_at, created_by_user_id, event_owner_user_id=None,
) -> CrmActivity:
    """Logs the call, then applies the three Phase-1 automatic stage rules
    (never regresses a deal already past 'engaged'). Returns the activity —
    the caller re-serializes the deal afterward to pick up any stage change."""
    if outcome not in CALL_OUTCOMES:
        raise ValueError(f"Unknown call outcome: {outcome}")

    category = CALL_OUTCOMES[outcome]["category"]
    # A general-category outcome is filed as a NOTE, not a call. Everything
    # that asks "has this club been called" keys on type='call'
    # (last_calls_by_deal, the funnel's attempted column, priority_score's
    # uncalled boost), so writing the honest type here is what keeps all of
    # them right at once rather than each needing to know about categories.
    is_call = outcome not in GENERAL_OUTCOMES

    activity = await crm_service.log_activity(
        session, deal_id=deal.id, person_id=person.id if person else None,
        type="call" if is_call else "note", body=notes,
        created_by_user_id=created_by_user_id,
        outcome=outcome, next_follow_up_at=next_follow_up_at,
    )

    stage = await session.get(CrmStage, deal.stage_id)
    stage_key = stage.key if stage else None

    if not is_call:
        # Nothing was claimed about the club, so nothing about it moves. In
        # particular NOT the Target -> Contacted nudge below, which exists
        # for a first real contact and a note is not one.
        pass
    elif category == "positive" and stage_key in _ADVANCEABLE_STAGE_KEYS:
        await _move_to_stage_key(session, deal, "engaged")
    elif outcome in _LOST_OUTCOMES:
        # status/lost_reason aren't in update_deal's clearable-field whitelist
        # (they're deliberately not a plain PATCH-able field — see
        # DealCreate/DealUpdate in routers/crm.py, which never expose them
        # either) — close_deal is the one function that sets them together
        # with the pipeline's own is_lost stage and closed_at.
        pipeline = await crm_service.get_deal_pipeline(session, deal)
        if pipeline is not None:
            await crm_service.close_deal(session, deal, pipeline, status="lost",
                                          lost_reason=CALL_OUTCOMES[outcome]["label"])
            await session.flush()
    elif stage_key == "target":
        # First real contact of any other kind still nudges Target -> Contacted
        # (section 15's "call recorded -> contacted" rule).
        await _move_to_stage_key(session, deal, "contacted")

    if outcome in _DO_NOT_CONTACT_OUTCOMES:
        # An explicit stop request propagates to BOTH axes: the person (if
        # this call was logged against one, and it's bridged to a directory
        # contact — a lazily-materialized CRM-only person has no directory
        # row to flag) and the club as a whole, via the existing
        # marketing_clubs.not_interested flag (see migration 256's docstring
        # for why that's reused rather than a new column).
        if person is not None and person.directory_contact_id is not None:
            contact = await session.get(MarketingClubContact, person.directory_contact_id)
            if contact is not None:
                contact.do_not_contact = True
                contact.do_not_contact_reason = CALL_OUTCOMES[outcome]["label"]
        if deal.marketing_club_id is not None:
            club = await session.get(MarketingClub, deal.marketing_club_id)
            if club is not None:
                club.not_interested = True
        await session.flush()

    # A real next step with a real person deserves a calendar reminder, not
    # just the queue's quiet next_follow_up_at tag — only when BOTH a
    # follow-up date was actually set and the outcome is one worth acting on
    # (see _EVENT_WORTHY_OUTCOMES). Owned by whoever logged the call by
    # default — that's the person who knows the context and should see it on
    # their own calendar — but the rep may hand it to any named staff member
    # instead (event_owner_user_id), for any event-worthy outcome, not just a
    # chosen few: "who's responsible for following this up" is the rep's call
    # to make every time they set a follow-up date, not something this
    # function should second-guess based on why the call happened.
    if next_follow_up_at is not None and outcome in _EVENT_WORTHY_OUTCOMES:
        contact_name = person.full_name if person else "the contact"
        template = _FOLLOW_UP_NOTE_TEMPLATES.get(outcome, "Follow up with {name}.")
        event_body = (notes or "").strip() or template.format(name=contact_name)
        event_owner = event_owner_user_id or created_by_user_id
        await crm_service.create_event(
            session, deal_id=deal.id, marketing_club_id=deal.marketing_club_id,
            contact_person_id=person.id if person else None,
            owner_user_id=event_owner, event_type="follow_up",
            title=f"Follow up: {deal.title}", body=event_body,
            starts_at=next_follow_up_at, created_by_user_id=created_by_user_id,
        )

    return activity


async def set_contact_do_not_contact(
    session: AsyncSession, contact: MarketingClubContact, flag: bool, reason: Optional[str],
) -> MarketingClubContact:
    contact.do_not_contact = flag
    contact.do_not_contact_reason = (reason or None) if flag else None
    await session.flush()
    return contact


async def _move_to_stage_key(session: AsyncSession, deal: CrmDeal, stage_key: str) -> None:
    pipeline = await crm_service.get_deal_pipeline(session, deal)
    if pipeline is None:
        return
    target = next((s for s in pipeline.stages if s.key == stage_key), None)
    if target is None or target.id == deal.stage_id:
        return
    deal.stage_id = target.id
    deal.updated_at = func.now()
    await session.flush()


# The one-off Twenty pipeline cutover backfill (app/scripts/
# import_twenty_pipeline.py) writes a "system" entry per club it touched
# ("Imported from Twenty (...): stage=...") and a "note" entry per Twenty
# Opportunity note it pulled in — both stamped with one of these meta keys.
# The Sales Workspace's own History/Notes never show either: a rep's
# timeline is what THEY did, not what a retired CRM's board once said.
_TWENTY_IMPORT_META_KEYS = ("twenty_kind", "twenty_note_id")


def _is_twenty_imported(activity: CrmActivity) -> bool:
    meta = activity.meta or {}
    return any(k in meta for k in _TWENTY_IMPORT_META_KEYS)


# A reassignment is still WRITTEN (log_reassignment, below) — it is the deal's
# audit trail of who has owned it — it is just no longer drawn in the drawer's
# History feed, per direct instruction: a rep reading a club's history wants
# what happened with the CLUB, and a row saying the deal changed hands is
# housekeeping between reps. Matched on the meta stamp first; the body text is
# the fallback for every row written before that stamp existed, which is all of
# them until this shipped. Both wordings go, since they are one event with and
# without an owner.
_REASSIGNMENT_KIND = "reassignment"
_REASSIGNMENT_BODIES = ("Unassigned",)
_REASSIGNMENT_PREFIX = "Reassigned to "


def _is_reassignment(activity: CrmActivity) -> bool:
    if (activity.meta or {}).get("kind") == _REASSIGNMENT_KIND:
        return True
    if activity.type != "system":
        return False
    body = (activity.body or "").strip()
    return body.startswith(_REASSIGNMENT_PREFIX) or body in _REASSIGNMENT_BODIES


async def list_activities_for_workspace(
    session: AsyncSession, *, deal_id, limit: int = 200,
) -> list[CrmActivity]:
    """The same query crm_service.list_activities runs, minus anything the
    Twenty pipeline backfill imported and minus the reassignment audit rows.
    Filtered in Python after an over-fetch (rather than in the SQL WHERE
    clause) specifically to dodge a JSONB NULL trap: an ordinary rep-logged
    call/note has meta=NULL, and ``NOT (meta ? 'key')`` evaluates to NULL —
    not TRUE — for a NULL meta, which would silently exclude every real,
    ordinary activity from the result along with the Twenty-imported ones.
    Scoped to the Sales Workspace only — the CRM Pipeline board
    (routers/crm.py) still calls crm_service.list_activities directly and
    shows everything, by design."""
    rows = await crm_service.list_activities(session, deal_id=deal_id, limit=max(limit * 3, limit))
    return [a for a in rows if not _is_twenty_imported(a) and not _is_reassignment(a)][:limit]


async def log_note(
    session: AsyncSession, *, deal: CrmDeal, body: str, pinned: bool, created_by_user_id,
) -> CrmActivity:
    return await crm_service.log_activity(
        session, deal_id=deal.id, type="note", body=body,
        created_by_user_id=created_by_user_id, meta={"pinned": bool(pinned)},
    )


async def edit_note(
    session: AsyncSession, *, activity: CrmActivity, body: str, pinned: bool,
) -> CrmActivity:
    """Rewrites a note's text and/or pin state in place — a note is a rep's
    own free-text record, unlike a call/email/system entry, which is a log
    of something that actually happened and stays exactly as it was made.
    meta.edited_at (ISO, alongside the existing pinned flag) is the only
    audit trail kept — a plain marker rather than a new column, matching how
    'pinned' itself already rides in this JSONB rather than its own schema
    change."""
    activity.body = body
    activity.meta = {**(activity.meta or {}), "pinned": bool(pinned), "edited_at": datetime.now(timezone.utc).isoformat()}
    await session.flush()
    return activity


async def log_reassignment(session: AsyncSession, *, deal: CrmDeal, owner_name: Optional[str], created_by_user_id) -> None:
    """The lightweight Phase-1 reassignment audit trail — a system entry on
    the deal's own activity timeline rather than a dedicated table (deferred
    alongside Sales Lists). NOT shown in the Sales Workspace drawer's History
    feed (see _is_reassignment); it is a record of who owned the deal, not of
    anything that happened with the club."""
    body = f"Reassigned to {owner_name}" if owner_name else "Unassigned"
    await crm_service.log_activity(
        session, deal_id=deal.id, type="system", body=body,
        created_by_user_id=created_by_user_id,
        # Stamped so the drawer's History feed can drop it without reading the
        # wording (_is_reassignment) — the row stays as the audit trail it was
        # written to be, it is simply not something a rep is shown.
        meta={"kind": _REASSIGNMENT_KIND},
    )


async def bulk_assign(
    session: AsyncSession, *, deals: list[CrmDeal], owner_ids: list, owner_names: dict,
    created_by_user_id,
) -> dict:
    """Assigns every deal in `deals` across `owner_ids` round-robin (a single
    id assigns everything to that one rep; several ids split evenly, in the
    order given — "Sam / Jake / Sarah" per the brief's section 26). Logs the
    same reassignment activity per deal as the single-deal PATCH, so the two
    paths leave an identical audit trail. Returns a per-rep count. There is
    no separate "duplicate assignment" guard to build here — a deal has
    exactly one owner_user_id by construction, so re-running this over the
    same selection just overwrites it, same as the single-deal action.

    An empty `owner_ids` means "unassign" — every deal's owner_user_id is
    cleared back to NULL (the shared pool), the same as picking "Unassigned"
    on the single-deal PATCH. Counted under the "unassigned" key since there
    is no real owner id to key it on."""
    if not owner_ids:
        counts: dict = {"unassigned": 0}
        for deal in deals:
            await crm_service.update_deal(session, deal, owner_user_id=None)
            await log_reassignment(session, deal=deal, owner_name=None, created_by_user_id=created_by_user_id)
            counts["unassigned"] += 1
        await session.flush()
        return counts

    counts: dict = {str(o): 0 for o in owner_ids}
    for i, deal in enumerate(deals):
        owner_id = owner_ids[i % len(owner_ids)]
        await crm_service.update_deal(session, deal, owner_user_id=owner_id)
        await log_reassignment(session, deal=deal, owner_name=owner_names.get(owner_id), created_by_user_id=created_by_user_id)
        counts[str(owner_id)] += 1
    await session.flush()
    return counts


# ─── Where this club came from: Meta, the trial page, the setup wizard ────────
# Three questions a rep asks about a warm club that the queue row can't answer:
# did an ad bring them, how far into signing up did they actually get, and (once
# they're on) how much of the setup have they done. Every one of these reads a
# beacon table, so they are served by their own endpoint rather than the drawer
# payload — see routers/sales_workspace.get_club_signals.


def _iso(dt):
    return dt.isoformat() if dt else None


async def meta_ad_summary(session: AsyncSession, club) -> Optional[dict]:
    """What this club's Meta ad traffic actually was: how many ad landings, on
    which campaign and creative, where they landed and when.

    The engagement breakdown already says how many POINTS the ad clicks were
    worth; it can't say which ad, and "they clicked the Club History ad twice
    last Tuesday" is what a rep opens a call with. Returns None when the club
    has no ad-attributed traffic at all, so the card simply doesn't draw.

    A click is detected exactly as the score detects it — twenty_sync's
    ``_META_CLICK``, an fbclid/igshid on the stored URL — rather than a second
    rule that could disagree with the number beside it. Attribution mirrors
    ``_engagement``'s own two branches: the pre-stamped resolved club for a
    prospect's anonymous visit, plus the club's own org traffic once it is
    onboarded.
    """
    if club is None:
        return None
    from app.services.twenty_sync import _META_CLICK

    rows = (await session.execute(text(f"""
        SELECT ue.created_at, ue.path, ue.landing_path,
               COALESCE(NULLIF(ue.utm_campaign, ''),
                        substring(ue.path from 'utm_campaign=([^&]+)')) AS campaign,
               COALESCE(NULLIF(ue.utm_content, ''),
                        substring(ue.path from 'utm_content=([^&]+)'))  AS content
        FROM usage_events ue
        WHERE {_META_CLICK}
          AND (ue.resolved_marketing_club_id = CAST(:cid AS uuid)
               -- CAST before the NULL test, not a bare `:org_id IS NOT NULL`:
               -- asyncpg types a parameter from how it is used, and that gives
               -- it nothing (AmbiguousParameterError at execute time). Same
               -- trap the vote-medal note in CLAUDE.md documents.
               OR (CAST(:org_id AS uuid) IS NOT NULL
                   AND ue.org_id = CAST(:org_id AS uuid)))
        ORDER BY ue.created_at DESC
        LIMIT 500
    """), {"cid": str(club.id),
           "org_id": str(club.existing_org_id) if club.existing_org_id else None})).mappings().all()
    if not rows:
        return None

    from app.services.meta_ads import AD_DESTINATIONS, CAMPAIGN_UTM_NAMES

    # utm_content is the tag on an ad's own destination URL, so it names the
    # creative; utm_campaign names the campaign. Both are read back through the
    # SAME maps the Meta Ads dashboard labels its own rows with, so a creative
    # reads as "Ad_ClubHistory_Trial_Hero_v3" in both places and an untagged or
    # retired one falls back to whatever tag it actually carried.
    ad_names = {a["utm_content"]: a["name"] for a in AD_DESTINATIONS.values() if a.get("utm_content")}
    campaign_names = set(CAMPAIGN_UTM_NAMES.values())

    def _tally(key):
        counts: dict[str, int] = {}
        for r in rows:
            v = (r[key] or "").strip()
            if v:
                counts[v] = counts.get(v, 0) + 1
        return counts

    ads = [{"name": ad_names.get(k, k), "tag": k, "clicks": n}
           for k, n in sorted(_tally("content").items(), key=lambda kv: -kv[1])]
    campaigns = [{"name": k, "known": k in campaign_names, "clicks": n}
                 for k, n in sorted(_tally("campaign").items(), key=lambda kv: -kv[1])]

    # The raw landing URLs are deliberately never surfaced to a rep — each ad
    # click carries its own fbclid query string, so the same page reads as
    # several distinct "URLs" and is noise, not signal (a landing count + date
    # range already says everything useful). So this only ever needed to
    # COUNT clicks, never to build a per-path breakdown.
    return {
        "clicks": len(rows),
        "first_at": rows[-1]["created_at"].isoformat() if rows[-1]["created_at"] else None,
        "last_at": rows[0]["created_at"].isoformat() if rows[0]["created_at"] else None,
        "campaigns": campaigns[:4],
        "ads": ads[:4],
    }


async def registration_journey(session: AsyncSession, club) -> Optional[dict]:
    """How far into the self-serve trial registration this club actually got,
    on the real eight-step funnel — and whether they finished or walked away.

    The wizard row a club carries already says "Club selected" / "Reached Terms
    & privacy" / "Registration completed", which is only a three-level rank
    over what happens to be identifiable platform-wide. This reads the beacon
    trail of the visitors who picked THIS club, so "gave up right after the
    verification code was sent" is sayable — which is the difference between a
    call worth making and a guess.

    Identity comes from the ``club_prepared`` beacon's OWN captured club (the
    guid it recorded, else the name it recorded), never from a search term's
    top match — the same guid-first, name-second priority
    wizard_club_lists._directory_matches uses, and deliberately not the
    searched-club resolver, whose whole point is that a half-typed query does
    not identify anybody (see the Wizard Clubs note in CLAUDE.md).
    """
    if club is None:
        return None
    from app.services.meta_ads import REGISTRATION_STEP_ORDER

    visitors = (await session.execute(text("""
        SELECT DISTINCT visitor_id
        FROM usage_events
        WHERE event_type = 'self_serve_step'
          AND route = 'club_prepared'
          AND visitor_id IS NOT NULL
          AND (
            -- CAST before the NULL test — see meta_ad_summary above.
            (CAST(:guid AS text) IS NOT NULL
             AND NULLIF(TRIM(metadata->>'club_org_id'), '') = CAST(:guid AS text))
            OR lower(TRIM(COALESCE(metadata->>'club_name', ''))) = CAST(:name AS text)
          )
    """), {"guid": (club.grassroots_guid or "").strip() or None,
           "name": (club.name or "").strip().lower()})).scalars().all()
    if not visitors:
        return None

    steps = (await session.execute(text("""
        SELECT route, MIN(created_at) AS first_at, MAX(created_at) AS last_at
        FROM usage_events
        WHERE event_type = 'self_serve_step' AND visitor_id = ANY(:vids)
        GROUP BY route
    """), {"vids": visitors})).mappings().all()
    by_route = {r["route"]: r for r in steps}

    reached = []
    furthest = None
    for i, (key, label) in enumerate(REGISTRATION_STEP_ORDER):
        row = by_route.get(key)
        if row is None:
            continue
        entry = {"key": key, "label": label, "position": i + 1,
                 "at": row["last_at"].isoformat() if row["last_at"] else None}
        reached.append(entry)
        furthest = entry

    if furthest is None:
        return None
    total = len(REGISTRATION_STEP_ORDER)
    completed = furthest["key"] == REGISTRATION_STEP_ORDER[-1][0]
    return {
        "visitors": len(visitors),
        "completed": completed,
        # An unfinished run is only worth calling "abandoned" once it has had
        # time to be one — someone mid-signup right now is still signing up.
        "abandoned": not completed,
        "furthest": furthest,
        "total_steps": total,
        "reached": reached,
        "first_at": _iso(min((r["first_at"] for r in steps if r["first_at"]), default=None)),
        "last_at": _iso(max((r["last_at"] for r in steps if r["last_at"]), default=None)),
    }


# ─── Call status vocabulary ───────────────────────────────────────────────────
# The five things the queue's Call status filter can ask about a club, and the
# ONE place the rule for each is written.
#
# They OVERLAP, deliberately, because what has happened to a club accumulates:
# a rep rings, leaves a voicemail, sets a follow-up and then emails a contact,
# and every one of those is still true afterwards. So that club answers to
# Called AND VM AND Followup AND Sent Email at once, and unticking any of them
# hides it. Only ``not_called`` is exclusive with the rest, by construction —
# a club with a call logged against it is not an uncalled one.
#
# This is NOT how they started out. The first cut treated them as one bucket
# per club in a precedence order, which meant a voicemail was not a call and a
# follow-up was neither — so a rep looking at Called could not see the clubs
# they had most recently worked. The queue ROW still picks a single highlight
# colour by precedence (see the frontend), because a row can only be one
# colour; the filter no longer works that way and the two are allowed to
# differ.
CALL_STATUS_KEYS = ("not_called", "called", "followup", "voicemail", "sent_email")

# ``callback`` was this bucket's name until it was relabelled Followup. Read
# through so a shared link, or a preference saved against a user's account,
# written before the rename still selects the right box rather than silently
# selecting nothing.
CALL_STATUS_ALIASES = {"callback": "followup"}


def call_statuses_of(*, ever_called: bool, followup_due: bool,
                     last_call_outcome: Optional[str],
                     sent_email: bool = False) -> set:
    """Every Call status bucket a queue row answers to, not just one.

    ``voicemail`` is about the club's MOST RECENT call, not any call it has
    ever had: it means "I left a message and have not got through since",
    which stops being true the moment someone picks up. Sending an email
    afterwards does not change it — an email is not a call.
    """
    out = set()
    if not ever_called:
        out.add("not_called")
    else:
        out.add("called")
        if last_call_outcome == "voicemail":
            out.add("voicemail")
    # A follow-up can only exist once a call has been logged, so this never
    # applies to an uncalled club — but it is checked on its own rather than
    # nested under `called`, so a follow-up recorded some other way in future
    # still counts.
    if followup_due:
        out.add("followup")
    if sent_email:
        out.add("sent_email")
    return out


async def emailed_deal_ids(session: AsyncSession, deal_ids) -> set:
    """The deals a rep has actually sent an email to, batched for the queue.

    An email is a ``crm_activities`` row of type 'email' — what Send Email
    writes on a successful send (see routers/sales_workspace.send_email), so a
    send that failed logs nothing and this stays honest. Twenty-imported rows
    are left out for the same reason the drawer's own timeline leaves them
    out: they are a backfill of somebody else's pipeline, not a call this
    workspace made.
    """
    ids = {d for d in deal_ids if d is not None}
    if not ids:
        return set()
    rows = (await session.execute(
        select(CrmActivity)
        .where(CrmActivity.deal_id.in_(ids), CrmActivity.type == "email")
    )).scalars().all()
    return {a.deal_id for a in rows if not _is_twenty_imported(a)}


# ─── Queue row shaping ────────────────────────────────────────────────────────

def priority_score(*, engagement_score: Optional[int], ever_called: bool,
                   next_follow_up_at, last_signal_at) -> int:
    """A simple, transparent v1 "call next" heuristic — not the weighted
    formula from the full brief, just enough to put the highest-value calls
    at the top of a rep's queue by default. Easy to tune later; deliberately
    NOT stored (recomputed on every read from live inputs)."""
    score = engagement_score or 0
    if not ever_called:
        score += 30
    if next_follow_up_at is not None:
        now = datetime.now(timezone.utc)
        follow_up = next_follow_up_at if next_follow_up_at.tzinfo else next_follow_up_at.replace(tzinfo=timezone.utc)
        if follow_up <= now:
            score += 20
    if last_signal_at is not None:
        now = datetime.now(timezone.utc)
        signal = last_signal_at if last_signal_at.tzinfo else last_signal_at.replace(tzinfo=timezone.utc)
        if (now - signal).days <= 3:
            score += 15
    return score


# A row is a call for "has this club been called" purposes when it is
# type='call' AND its outcome is not one of the general ones. The second half
# is only for rows written before general outcomes were filed as notes: it
# corrects them on read, so a club a rep left a general note against comes
# back into the uncalled queue with no data fix or re-entry needed.
# NOTE the explicit NULL arm: `NOT (NULL IN (...))` is NULL, not true, so a
# bare ~in_() would silently drop every call row with no outcome recorded —
# which the CRM's own generic activity endpoint can write. Same trap
# services/grade_scope.py's clause() documents.
_IS_CALL_ROW = (CrmActivity.type == "call") & (
    CrmActivity.outcome.is_(None) | ~CrmActivity.outcome.in_(GENERAL_OUTCOMES)
)


async def last_calls_by_deal(session: AsyncSession, deal_ids) -> dict:
    """deal_id -> the most recent 'call' activity dict (or None), batched for
    the queue list — avoids an N+1 query per row."""
    ids = {d for d in deal_ids if d is not None}
    if not ids:
        return {}
    rows = (await session.execute(
        select(CrmActivity)
        .where(CrmActivity.deal_id.in_(ids), _IS_CALL_ROW)
        .order_by(CrmActivity.deal_id, CrmActivity.occurred_at.desc())
    )).scalars().all()
    out: dict = {}
    for a in rows:
        if a.deal_id not in out:
            out[a.deal_id] = a
    return out


async def next_follow_ups_by_deal(session: AsyncSession, deal_ids) -> dict:
    """deal_id -> the earliest still-PENDING next_follow_up_at, batched. A
    follow-up marked done (follow_up_done_at set) no longer counts — a
    resolved callback shouldn't keep nagging the queue row."""
    ids = {d for d in deal_ids if d is not None}
    if not ids:
        return {}
    rows = (await session.execute(
        select(CrmActivity.deal_id, func.min(CrmActivity.next_follow_up_at))
        .where(
            CrmActivity.deal_id.in_(ids),
            CrmActivity.next_follow_up_at.isnot(None),
            CrmActivity.follow_up_done_at.is_(None),
        )
        .group_by(CrmActivity.deal_id)
    )).all()
    return {r[0]: r[1] for r in rows}


# ─── Follow-ups queue ─────────────────────────────────────────────────────────

async def list_follow_ups(session: AsyncSession, *, owner_user_id=None) -> list[CrmActivity]:
    """Every PENDING follow-up (next_follow_up_at set, follow_up_done_at
    NULL), oldest-due first — the caller categorises into overdue/today/
    upcoming, since "today" depends on the caller's own clock/timezone
    handling, not something to bake in here. owner_user_id restricts to one
    rep's own deals (a 'sales'-role caller always passes their own id; a
    super admin passes None for everyone, or a specific rep to inspect their
    queue)."""
    stmt = (
        select(CrmActivity)
        .join(CrmDeal, CrmDeal.id == CrmActivity.deal_id)
        .where(
            CrmActivity.next_follow_up_at.isnot(None),
            CrmActivity.follow_up_done_at.is_(None),
            CrmDeal.archived_at.is_(None),
        )
        .order_by(CrmActivity.next_follow_up_at.asc())
    )
    if owner_user_id is not None:
        stmt = stmt.where(CrmDeal.owner_user_id == owner_user_id)
    return (await session.execute(stmt)).scalars().all()


async def mark_follow_up_done(session: AsyncSession, activity: CrmActivity) -> CrmActivity:
    activity.follow_up_done_at = func.now()
    await session.flush()
    return activity


async def contact_counts_by_club(session: AsyncSession, marketing_club_ids) -> dict:
    ids = {c for c in marketing_club_ids if c is not None}
    if not ids:
        return {}
    rows = (await session.execute(
        select(MarketingClubContact.marketing_club_id, func.count())
        .where(MarketingClubContact.marketing_club_id.in_(ids))
        .group_by(MarketingClubContact.marketing_club_id)
    )).all()
    return {r[0]: r[1] for r in rows}


# ─── Performance reporting ─────────────────────────────────────────────────────
# Deliberately NOT "calls per rep" as the headline (see the brief's section 19 —
# raw volume rewards low-value dialling, not qualified clubs). The stage
# breakdown below is the real measure; the daily/weekly counts are activity
# context alongside it.

TRIAL_STARTED_ACTIVITY_PREFIX = "Trial started for"  # matches log line in routers/sales_workspace.py::start_trial

# The one definition of "this rep has made contact", shared by every figure on
# the Performance screen: a logged call, a follow-up/callback recorded, or an
# email actually sent. Anything else on the timeline (a note, an automatic
# stage move, an assignment) is not reaching out to the club.
#
# `_IS_CALL_ROW` already excludes the general-purpose outcomes that aren't a
# call at all. A follow-up is checked on its own rather than nested under a
# call, matching call_statuses_of's own reasoning — today a callback can only
# be captured off a call log, but one recorded some other way in future still
# counts as contact.
_IS_FOLLOW_UP_ROW = CrmActivity.next_follow_up_at.isnot(None)
_IS_EMAIL_ROW = CrmActivity.type == "email"
_IS_CONTACT_ROW = _IS_CALL_ROW | _IS_FOLLOW_UP_ROW | _IS_EMAIL_ROW


def _contact_kind(activity: CrmActivity) -> Optional[str]:
    """'call' | 'email' | None for one timeline row, plus whether it booked a
    follow-up — read in Python so the SQL predicate above and the per-rep
    tallies can never disagree about what a contact is.

    A Twenty-imported row never counts, for the reason emailed_deal_ids
    already gives: it is a backfill of somebody else's pipeline, not work
    this workspace did."""
    if _is_twenty_imported(activity):
        return None
    if activity.type == "email":
        return "email"
    if activity.type == "call" and activity.outcome not in GENERAL_OUTCOMES:
        return "call"
    # A follow-up recorded on any other row still counts as contact (see the
    # predicate above), it just isn't a call or an email.
    if activity.next_follow_up_at is not None:
        return "other"
    return None


async def contacted_deal_ids(session: AsyncSession, deal_ids) -> set:
    """The subset of `deal_ids` a rep has actually made contact with —
    call, follow-up or email. Batched; one query however many deals."""
    ids = {d for d in deal_ids if d is not None}
    if not ids:
        return set()
    rows = (await session.execute(
        select(CrmActivity).where(CrmActivity.deal_id.in_(ids), _IS_CONTACT_ROW)
    )).scalars().all()
    return {a.deal_id for a in rows if _contact_kind(a) is not None}


# ─── Windows ─────────────────────────────────────────────────────────────────
# "Today" and "this week" are PERTH days, not UTC ones. A UTC day boundary
# starts at 8am local, so a rep's morning calls would have read as yesterday's
# for the whole first half of the working day.
PERTH = ZoneInfo("Australia/Perth")


def report_windows(now: Optional[datetime] = None) -> dict:
    """{'today': start, 'week': start} as UTC instants, from the Perth
    calendar day. Week starts Monday, same as the rest of the app."""
    now = (now or datetime.now(timezone.utc)).astimezone(PERTH)
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week = day - timedelta(days=day.weekday())
    return {"today": day.astimezone(timezone.utc), "week": week.astimezone(timezone.utc)}


# ─── Stage columns ───────────────────────────────────────────────────────────
# The report's own column vocabulary, which is NOT one column per pipeline
# stage: the single real 'trial' stage splits into current/expired (the same
# split the queue's own stage filter makes, and for the same reason — a lapsed
# trial is a different job from a live one), and 'self_serve_trial' folds in
# beside it, since a club that signed itself up is on a trial either way.
#
# 'other' is the catch-all for a stage this list doesn't name, and is only
# drawn when a deal is actually sitting in one (`stage_columns` reports which)
# — a deal must never be dropped from the table just because its stage isn't
# one of the nine the screen normally shows. Every named stage, Proposal
# included, is always drawn: an empty Proposal column is itself the answer to
# "is anyone at proposal", which a column that comes and goes can't give.
STAGE_COLUMNS = [
    ("manual", "Manual"),
    ("target", "Target"),
    ("contacted", "Contacted"),
    ("engaged", "Engaged"),
    ("trial_current", "Trial (Current)"),
    ("trial_expired", "Trial (Expired)"),
    ("proposal", "Proposal"),
    ("won", "Won"),
    ("lost", "Lost"),
    ("other", "Other"),
]

_STAGE_KEY_TO_COLUMN = {
    "manually_added": "manual",
    "target": "target",
    "contacted": "contacted",
    "engaged": "engaged",
    "proposal": "proposal",
    "won": "won",
    "lost_dormant": "lost",
}
_TRIAL_STAGE_KEYS = ("trial", "self_serve_trial")

UNASSIGNED_KEY = "unassigned"


async def performance_summary(session: AsyncSession, *, owner_user_id=None) -> dict:
    """Today + this-week activity counts (calls, emails, distinct clubs
    contacted, positive-outcome conversations, callbacks created, trials
    started).

    Counted by WHO DID THE WORK (``crm_activities.created_by_user_id``), not
    by who owns the deal — "how many calls has this rep made today" is a
    question about the rep, and a call logged on a club that has since been
    reassigned is still their call. owner_user_id restricts to one rep; None
    covers everyone (super admin only — enforced by the caller, not here)."""
    report = await activity_report(session, owner_user_id=owner_user_id)
    return {"today": report["totals"]["today"], "week": report["totals"]["week"]}


async def activity_report(session: AsyncSession, *, owner_user_id=None) -> dict:
    """Per-rep contact activity for today and this week, plus the totals.

    ``{"rows": [...], "totals": {"today": {...}, "week": {...}}}``. The
    totals are computed over the same activity rows the per-rep numbers come
    from, so the KPI strip at the top of the screen and the table under it
    cannot disagree — `clubs_contacted` in particular is a genuine distinct
    count across everyone, never a sum of per-rep distinct counts."""
    windows = report_windows()
    week_start = windows["week"]
    today_start = windows["today"]
    # One pull covering the wider of the two windows; both are then counted
    # in Python. Two queries would double the work for the same rows.
    start = min(week_start, today_start)

    stmt = select(CrmActivity).where(CrmActivity.occurred_at >= start, _IS_CONTACT_ROW)
    if owner_user_id is not None:
        stmt = stmt.where(CrmActivity.created_by_user_id == owner_user_id)
    activities = (await session.execute(stmt)).scalars().all()

    trial_stmt = select(CrmActivity).where(
        CrmActivity.occurred_at >= start, CrmActivity.type == "system",
        CrmActivity.body.like(f"{TRIAL_STARTED_ACTIVITY_PREFIX}%"),
    )
    if owner_user_id is not None:
        trial_stmt = trial_stmt.where(CrmActivity.created_by_user_id == owner_user_id)
    trials = (await session.execute(trial_stmt)).scalars().all()

    def _blank() -> dict:
        return {"calls": 0, "emails": 0, "contacts": 0, "positive_conversations": 0,
                "callbacks_created": 0, "trials_started": 0, "_clubs": set()}

    per_rep: dict = {}
    totals = {"today": _blank(), "week": _blank()}

    def _buckets(user_id, occurred_at) -> list:
        """Every bucket this row lands in — a rep's own, plus the totals,
        for each window it falls inside."""
        rep = per_rep.setdefault(user_id, {"today": _blank(), "week": _blank()})
        out = []
        for name, ws in (("today", today_start), ("week", week_start)):
            if occurred_at >= ws:
                out.append(rep[name])
                out.append(totals[name])
        return out

    for a in activities:
        kind = _contact_kind(a)
        if kind is None:
            continue
        for b in _buckets(a.created_by_user_id, a.occurred_at):
            b["contacts"] += 1
            if kind == "call":
                b["calls"] += 1
                if a.outcome and CALL_OUTCOMES.get(a.outcome, {}).get("category") == "positive":
                    b["positive_conversations"] += 1
            elif kind == "email":
                b["emails"] += 1
            if a.next_follow_up_at is not None:
                b["callbacks_created"] += 1
            if a.deal_id is not None:
                b["_clubs"].add(a.deal_id)

    for a in trials:
        for b in _buckets(a.created_by_user_id, a.occurred_at):
            b["trials_started"] += 1

    names = await user_names_by_ids(session, [uid for uid in per_rep if uid is not None])

    def _finish(bucket: dict) -> dict:
        out = dict(bucket)
        out["clubs_contacted"] = len(out.pop("_clubs"))
        return out

    rows = [
        {
            "user_id": str(uid) if uid else None,
            "name": names.get(uid) or ("Automated" if uid is None else "Unknown"),
            "today": _finish(w["today"]),
            "week": _finish(w["week"]),
        }
        for uid, w in per_rep.items()
    ]
    rows.sort(key=lambda r: (-r["week"]["contacts"], -r["today"]["contacts"], r["name"].lower()))
    return {"rows": rows, "totals": {k: _finish(v) for k, v in totals.items()}}


async def stage_breakdown_by_rep(session: AsyncSession, *, owner_user_id=None) -> dict:
    """Where every platform deal sits, per rep, plus an Unassigned row.

    Each stage cell carries BOTH figures: ``total`` (every deal in that
    stage) and ``contacted`` (the ones the rep has actually reached out to —
    call, follow-up or email). The two answer different questions and the
    screen shows them together, so a stage full of clubs nobody has rung
    reads differently from one that has been worked.

    ``to_contact`` is the rep's backlog: assigned to them and NOT yet
    contacted — i.e. how many are left before they need more clubs. On the
    Unassigned row it is the pool waiting to be handed out.

    Won/lost deals still count in their rep's row: that is the point of the
    breakdown. Archived deals never do."""
    pipeline = await crm_service.ensure_platform_pipeline(session)
    stage_by_id = {s.id: s for s in pipeline.stages}

    deals_stmt = select(CrmDeal).where(
        CrmDeal.pipeline_id == pipeline.id, CrmDeal.archived_at.is_(None),
    )
    if owner_user_id is not None:
        deals_stmt = deals_stmt.where(CrmDeal.owner_user_id == owner_user_id)
    deals = (await session.execute(deals_stmt)).scalars().all()

    contacted = await contacted_deal_ids(session, [d.id for d in deals])

    def _stage_key(d) -> Optional[str]:
        stage = stage_by_id.get(d.stage_id)
        return stage.key if stage else None

    # Only the trial-stage deals need their club's trial dates resolved, so
    # only those clubs are loaded — the whole book would be a far bigger read
    # for a split that can't apply to any of the rest.
    trial_deals = [d for d in deals if _stage_key(d) in _TRIAL_STAGE_KEYS]
    club_by_id = await crm_service.clubs_by_ids(session, (d.marketing_club_id for d in trial_deals))
    trial_days_by_club = await crm_service.trial_days_remaining_by_club(session, club_by_id)
    min_trial_by_club = {cid: min(days.values()) for cid, days in trial_days_by_club.items() if days}

    def _column(d) -> str:
        key = _stage_key(d)
        if key in _TRIAL_STAGE_KEYS:
            days = min_trial_by_club.get(d.marketing_club_id)
            # No trial data at all reads as current, never expired — the same
            # rule the queue's own trial_current/trial_expired filter applies,
            # since nothing proves a club with no dates has lapsed.
            return "trial_expired" if days is not None and days < 0 else "trial_current"
        return _STAGE_KEY_TO_COLUMN.get(key, "other")

    def _blank_row() -> dict:
        return {"total": 0, "contacted": 0, "to_contact": 0,
                "stages": {col: {"total": 0, "contacted": 0} for col, _ in STAGE_COLUMNS}}

    by_owner: dict = {}
    totals = _blank_row()
    for d in deals:
        owner = d.owner_user_id
        row = by_owner.setdefault(owner, _blank_row())
        col = _column(d)
        was_contacted = d.id in contacted
        for bucket in (row, totals):
            bucket["total"] += 1
            bucket["stages"][col]["total"] += 1
            if was_contacted:
                bucket["contacted"] += 1
                bucket["stages"][col]["contacted"] += 1
            else:
                bucket["to_contact"] += 1

    # Every sales rep gets a row even with nothing assigned — a rep sitting on
    # an empty book is exactly what this screen should make obvious, and they
    # would otherwise be invisible here.
    if owner_user_id is None:
        rep_ids = (await session.execute(
            select(User.id).join(ClubMembership, ClubMembership.user_id == User.id)
            .where(ClubMembership.role == "sales").distinct()
        )).scalars().all()
        for rid in rep_ids:
            by_owner.setdefault(rid, _blank_row())

    names = await user_names_by_ids(session, [uid for uid in by_owner if uid is not None])

    rows = []
    for uid, row in by_owner.items():
        rows.append({
            "owner_user_id": str(uid) if uid else UNASSIGNED_KEY,
            "owner_name": "Unassigned" if uid is None else (names.get(uid) or "Unknown"),
            "unassigned": uid is None,
            **row,
        })
    # Unassigned always last — it is the pool, not a person's performance.
    rows.sort(key=lambda r: (r["unassigned"], -r["total"], r["owner_name"].lower()))

    drawn = [
        {"key": col, "label": label}
        for col, label in STAGE_COLUMNS
        if col != "other" or totals["stages"][col]["total"] > 0
    ]
    return {"rows": rows, "totals": totals, "stage_columns": drawn}

# ─── Sales Lists (migration 257) ─────────────────────────────────────────────
# A thin provenance/import layer, not a parallel data model. Assignment still
# lives entirely on crm_deals.owner_user_id — POST /bulk-assign is what
# actually assigns a list's clubs to a rep, reused rather than duplicated
# here. A list is just "these clubs came in together, from this source";
# a club's calls/notes/stage are the same wherever it's viewed from.

async def list_sales_lists(session: AsyncSession) -> list[dict]:
    """Every Sales List, newest first, with its club count."""
    lists = (await session.execute(select(SalesList).order_by(SalesList.created_at.desc()))).scalars().all()
    if not lists:
        return []
    count_rows = (await session.execute(
        select(SalesListClub.sales_list_id, func.count())
        .where(SalesListClub.sales_list_id.in_([l.id for l in lists]))
        .group_by(SalesListClub.sales_list_id)
    )).all()
    counts = {row[0]: row[1] for row in count_rows}
    creator_ids = {l.created_by_user_id for l in lists if l.created_by_user_id}
    creators = {}
    if creator_ids:
        rows = (await session.execute(select(User).where(User.id.in_(creator_ids)))).scalars().all()
        creators = {u.id: (u.display_name or u.username) for u in rows}
    return [{
        "id": str(l.id),
        "name": l.name,
        "description": l.description,
        "source_type": l.source_type,
        "created_at": l.created_at.isoformat() if l.created_at else None,
        "created_by_name": creators.get(l.created_by_user_id),
        "club_count": counts.get(l.id, 0),
    } for l in lists]


async def get_sales_list(session: AsyncSession, list_id) -> Optional[dict]:
    """One Sales List's own record plus every club in it, each carrying its
    CURRENT deal state (stage, owner) — a list never freezes a snapshot, it
    just remembers which clubs came in together and when."""
    sales_list = await session.get(SalesList, list_id)
    if sales_list is None:
        return None

    memberships = (await session.execute(
        select(SalesListClub).where(SalesListClub.sales_list_id == list_id)
        .order_by(SalesListClub.added_at.desc())
    )).scalars().all()
    club_ids = [m.marketing_club_id for m in memberships]
    added_at_by_club = {m.marketing_club_id: m.added_at for m in memberships}

    clubs_by_id = {}
    if club_ids:
        rows = (await session.execute(select(MarketingClub).where(MarketingClub.id.in_(club_ids)))).scalars().all()
        clubs_by_id = {c.id: c for c in rows}

    pipeline = await crm_service.ensure_platform_pipeline(session)
    stage_by_id = {s.id: s for s in pipeline.stages}
    deals_by_club: dict = {}
    if club_ids:
        rows = (await session.execute(
            select(CrmDeal).where(
                CrmDeal.pipeline_id == pipeline.id,
                CrmDeal.marketing_club_id.in_(club_ids),
                CrmDeal.archived_at.is_(None),
            ).order_by(CrmDeal.created_at.desc())
        )).scalars().all()
        for d in rows:
            deals_by_club.setdefault(d.marketing_club_id, d)  # newest open deal wins

    owner_ids = {d.owner_user_id for d in deals_by_club.values() if d.owner_user_id}
    owners = {}
    if owner_ids:
        rows = (await session.execute(select(User).where(User.id.in_(owner_ids)))).scalars().all()
        owners = {u.id: (u.display_name or u.username) for u in rows}

    rows_out = []
    for club_id in club_ids:
        club = clubs_by_id.get(club_id)
        if club is None:
            continue
        deal = deals_by_club.get(club_id)
        stage = stage_by_id.get(deal.stage_id) if deal else None
        added_at = added_at_by_club.get(club_id)
        rows_out.append({
            "marketing_club_id": str(club_id),
            "club_name": club.name,
            "deal_id": str(deal.id) if deal else None,
            "stage_key": stage.key if stage else None,
            "stage_name": stage.name if stage else None,
            "owner_user_id": str(deal.owner_user_id) if deal and deal.owner_user_id else None,
            "owner_name": owners.get(deal.owner_user_id) if deal else None,
            "added_at": added_at.isoformat() if added_at else None,
        })

    creator_name = None
    if sales_list.created_by_user_id:
        creator = await session.get(User, sales_list.created_by_user_id)
        creator_name = (creator.display_name or creator.username) if creator else None

    return {
        "id": str(sales_list.id),
        "name": sales_list.name,
        "description": sales_list.description,
        "source_type": sales_list.source_type,
        "created_at": sales_list.created_at.isoformat() if sales_list.created_at else None,
        "created_by_name": creator_name,
        "clubs": rows_out,
    }


async def create_list_from_wizard_clubs(
    session: AsyncSession, *, name: str, description: Optional[str], days: int,
    club_keys: list[str], created_by_user_id=None,
) -> dict:
    """Import a Wizard Clubs selection into a Sales List. Each club_key is
    resolved to its Club Directory row with the SAME guid-first,
    case-insensitive-name-fallback matching the Wizard Clubs page itself
    uses (wizard_club_lists._directory_matches — never a second, drifting
    matcher), and every matched club is given an open platform deal via
    sync_platform_deal_for_club(stage_key='target', advance_only=True), so
    the club shows up in the workspace queue and a re-import can never push
    a club that's already further along (e.g. Engaged from an earlier call)
    back down to Target."""
    from app.services import wizard_club_lists as wcl

    if not (name or "").strip():
        return {"error": "no_name", "detail": "Name the list."}
    wanted = {wcl.norm_key(k) for k in (club_keys or []) if wcl.norm_key(k)}
    if not wanted:
        return {"error": "no_clubs", "detail": "No clubs were selected."}

    rows = [r for r in await wcl.merged_wizard_clubs(session, days) if r["key"] in wanted]
    if not rows:
        return {"error": "no_clubs", "detail": "None of those clubs are in the wizard list."}

    matches = await wcl._directory_matches(session, rows)

    sales_list = SalesList(
        name=name.strip(), description=(description or "").strip() or None,
        source_type="wizard_clubs", created_by_user_id=created_by_user_id,
    )
    session.add(sales_list)
    await session.flush()  # need sales_list.id for the membership rows

    added = 0
    matched_count = 0
    seen_club_ids: set = set()
    unmatched: list[str] = []
    for r in rows:
        club = matches.get(r["key"])
        if club is None:
            unmatched.append(r["name"])
            continue
        matched_count += 1
        # Two distinct wizard rows (different spellings/queries) can resolve
        # to the SAME directory club — a membership row per list+club is
        # unique by construction, so only add it once per import.
        if club.id not in seen_club_ids:
            seen_club_ids.add(club.id)
            session.add(SalesListClub(sales_list_id=sales_list.id, marketing_club_id=club.id))
            added += 1
        # Ensure a deal exists so the club shows up in the workspace queue —
        # never regresses a deal already past 'target' (see docstring).
        await crm_service.sync_platform_deal_for_club(
            session, club, stage_key="target", source="sales_list_import",
        )

    return {
        "id": str(sales_list.id),
        "name": sales_list.name,
        "clubs_added": added,
        "clubs_matched": matched_count,
        "clubs_unmatched": unmatched,
    }


async def create_list_from_crm_deals(
    session: AsyncSession, *, name: str, description: Optional[str],
    deals: list, created_by_user_id=None,
) -> dict:
    """Import an already-filtered set of Sales Pipeline deals into a Sales
    List — the CRM-export source. No Club Directory matching needed: these
    are already real crm_deals rows, so this just groups their
    marketing_club_id under one list. A deal with no club linked (a
    manually-created deal with no Club Directory match) has nothing to
    attach a list membership to and is reported, not silently dropped.
    Deliberately does NOT touch the deals themselves (stage, owner, value,
    or create new ones) — importing is a read of the pipeline, never a
    write to it, unlike the Wizard Clubs import which mints a fresh deal
    for a club that doesn't have one yet."""
    if not (name or "").strip():
        return {"error": "no_name", "detail": "Name the list."}
    if not deals:
        return {"error": "no_clubs", "detail": "No deals were selected."}

    sales_list = SalesList(
        name=name.strip(), description=(description or "").strip() or None,
        source_type="crm_export", created_by_user_id=created_by_user_id,
    )
    session.add(sales_list)
    await session.flush()  # need sales_list.id for the membership rows

    added = 0
    seen_club_ids: set = set()
    unmatched: list[str] = []
    for d in deals:
        if d.marketing_club_id is None:
            unmatched.append(d.title or str(d.id))
            continue
        # Two deals can point at the same club (rare, but not impossible) —
        # only one membership row per list+club.
        if d.marketing_club_id not in seen_club_ids:
            seen_club_ids.add(d.marketing_club_id)
            session.add(SalesListClub(sales_list_id=sales_list.id, marketing_club_id=d.marketing_club_id))
            added += 1

    return {
        "id": str(sales_list.id),
        "name": sales_list.name,
        "clubs_added": added,
        "clubs_matched": len(seen_club_ids),
        "clubs_unmatched": unmatched,
    }


async def wizard_signal_for_club(session: AsyncSession, marketing_club_id, days: int = 365) -> Optional[dict]:
    """The Wizard Clubs page's own row for THIS one club — search terms,
    selected/searched flags, whether it arrived via a Meta ad, registration
    progress and last-seen date — for the drawer's "someone from this club
    searched/selected it in the trial wizard" card. Same guid-first,
    name-fallback match `wizard_source_by_club` uses; this just narrows the
    whole-platform result down to one club rather than a bool per club, so
    the drawer can show WHAT the interest was, not just that there was some."""
    from app.services import wizard_club_lists as wcl

    rows = await wcl.merged_wizard_clubs(session, days)
    matches = await wcl._directory_matches(session, rows)
    for r in rows:
        club = matches.get(r["key"])
        if club is not None and club.id == marketing_club_id:
            return r
    return None


async def wizard_source_by_club(session: AsyncSession, days: int = 365) -> dict:
    """marketing_club_id -> {'selected': bool, 'searched': bool} from the
    Wizard Clubs / Meta Ads data — the SAME guid-first, name-fallback
    matching the Wizard Clubs page itself uses (wizard_club_lists), never a
    second matcher. Only called when the queue's Meta-Ad source filter is
    actually in use — it's an extra query over the beacon tables, not worth
    paying on every ordinary queue load."""
    from app.services import wizard_club_lists as wcl

    rows = await wcl.merged_wizard_clubs(session, days)
    matches = await wcl._directory_matches(session, rows)
    out: dict = {}
    for r in rows:
        club = matches.get(r["key"])
        if club is None:
            continue
        flags = out.setdefault(club.id, {"selected": False, "searched": False})
        flags["selected"] = flags["selected"] or bool(r.get("in_selected"))
        flags["searched"] = flags["searched"] or bool(r.get("in_searched"))
    return out
