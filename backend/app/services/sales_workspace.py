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

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import CrmActivity, CrmDeal, CrmPerson, CrmStage, MarketingClub, MarketingClubContact
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
    "interested": {"label": "Interested", "category": "positive"},
    "wants_more_info": {"label": "Wants more information", "category": "positive"},
    "wants_trial": {"label": "Wants trial", "category": "positive"},
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
}

CATEGORY_ORDER = ("positive", "neutral", "unsuccessful", "negative", "administrative")
CATEGORY_LABELS = {
    "positive": "Positive", "neutral": "Neutral", "unsuccessful": "Unsuccessful contact",
    "negative": "Negative", "administrative": "Administrative",
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
    return await session.scalar(
        select(MarketingClubContact).where(
            MarketingClubContact.marketing_club_id == marketing_club_id,
            func.lower(MarketingClubContact.email) == (email or "").strip().lower(),
        )
    ) if email else None


# ─── Calls ────────────────────────────────────────────────────────────────────

async def log_call(
    session: AsyncSession, *, deal: CrmDeal, person: Optional[CrmPerson], outcome: str,
    notes: Optional[str], next_follow_up_at, created_by_user_id,
) -> CrmActivity:
    """Logs the call, then applies the three Phase-1 automatic stage rules
    (never regresses a deal already past 'engaged'). Returns the activity —
    the caller re-serializes the deal afterward to pick up any stage change."""
    if outcome not in CALL_OUTCOMES:
        raise ValueError(f"Unknown call outcome: {outcome}")

    activity = await crm_service.log_activity(
        session, deal_id=deal.id, person_id=person.id if person else None,
        type="call", body=notes, created_by_user_id=created_by_user_id,
        outcome=outcome, next_follow_up_at=next_follow_up_at,
    )

    stage = await session.get(CrmStage, deal.stage_id)
    stage_key = stage.key if stage else None
    category = CALL_OUTCOMES[outcome]["category"]

    if category == "positive" and stage_key in _ADVANCEABLE_STAGE_KEYS:
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


async def log_note(
    session: AsyncSession, *, deal: CrmDeal, body: str, pinned: bool, created_by_user_id,
) -> CrmActivity:
    return await crm_service.log_activity(
        session, deal_id=deal.id, type="note", body=body,
        created_by_user_id=created_by_user_id, meta={"pinned": bool(pinned)},
    )


async def log_reassignment(session: AsyncSession, *, deal: CrmDeal, owner_name: Optional[str], created_by_user_id) -> None:
    """The lightweight Phase-1 reassignment audit trail — a searchable system
    entry on the deal's own activity timeline rather than a dedicated table
    (deferred alongside Sales Lists)."""
    body = f"Reassigned to {owner_name}" if owner_name else "Unassigned"
    await crm_service.log_activity(
        session, deal_id=deal.id, type="system", body=body,
        created_by_user_id=created_by_user_id,
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
    same selection just overwrites it, same as the single-deal action."""
    counts: dict = {str(o): 0 for o in owner_ids}
    for i, deal in enumerate(deals):
        owner_id = owner_ids[i % len(owner_ids)]
        await crm_service.update_deal(session, deal, owner_user_id=owner_id)
        await log_reassignment(session, deal=deal, owner_name=owner_names.get(owner_id), created_by_user_id=created_by_user_id)
        counts[str(owner_id)] += 1
    await session.flush()
    return counts


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


async def last_calls_by_deal(session: AsyncSession, deal_ids) -> dict:
    """deal_id -> the most recent 'call' activity dict (or None), batched for
    the queue list — avoids an N+1 query per row."""
    ids = {d for d in deal_ids if d is not None}
    if not ids:
        return {}
    rows = (await session.execute(
        select(CrmActivity)
        .where(CrmActivity.deal_id.in_(ids), CrmActivity.type == "call")
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
