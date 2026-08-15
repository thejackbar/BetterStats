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

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import (
    CrmActivity, CrmDeal, CrmPerson, CrmStage, MarketingClub, MarketingClubContact,
    SalesList, SalesListClub, User,
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


# ─── Performance reporting ─────────────────────────────────────────────────────
# Deliberately NOT "calls per rep" as the headline (see the brief's section 19 —
# raw volume rewards low-value dialling, not qualified clubs). The funnel below
# is the real measure; the daily/weekly counts are activity context alongside it.

TRIAL_STARTED_ACTIVITY_PREFIX = "Trial started for"  # matches log line in routers/sales_workspace.py::start_trial

# bucket -> the stage keys that count as "reached this far" (never regresses
# past lost_dormant into counting as a later bucket — lost_dormant isn't in
# any of these lists). 'attempted' is handled separately (>=1 call ever).
_FUNNEL_STAGE_KEYS = {
    "contacted": ("contacted", "engaged", "trial", "self_serve_trial", "proposal", "won"),
    "engaged": ("engaged", "trial", "self_serve_trial", "proposal", "won"),
    "trial": ("trial", "self_serve_trial", "proposal", "won"),
    "won": ("won",),
}


async def performance_summary(session: AsyncSession, *, owner_user_id=None) -> dict:
    """Today + this-week activity counts (calls, distinct clubs contacted,
    positive-outcome conversations, callbacks created, trials started).
    owner_user_id restricts to one rep; None covers everyone (super admin
    only — enforced by the caller, not here)."""
    now = datetime.now(timezone.utc)
    today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    week_start = today_start - timedelta(days=today_start.weekday())

    async def _window(start) -> dict:
        call_stmt = select(CrmActivity).where(CrmActivity.type == "call", CrmActivity.occurred_at >= start)
        if owner_user_id is not None:
            call_stmt = call_stmt.join(CrmDeal, CrmDeal.id == CrmActivity.deal_id).where(CrmDeal.owner_user_id == owner_user_id)
        calls = (await session.execute(call_stmt)).scalars().all()
        deal_ids = {c.deal_id for c in calls if c.deal_id}
        positive = sum(1 for c in calls if c.outcome and CALL_OUTCOMES.get(c.outcome, {}).get("category") == "positive")
        callbacks = sum(1 for c in calls if c.next_follow_up_at is not None)

        trial_stmt = select(func.count()).select_from(CrmActivity).where(
            CrmActivity.type == "system", CrmActivity.occurred_at >= start,
            CrmActivity.body.like(f"{TRIAL_STARTED_ACTIVITY_PREFIX}%"),
        )
        if owner_user_id is not None:
            trial_stmt = trial_stmt.join(CrmDeal, CrmDeal.id == CrmActivity.deal_id).where(CrmDeal.owner_user_id == owner_user_id)
        trials_started = (await session.execute(trial_stmt)).scalar() or 0

        return {
            "calls": len(calls),
            "clubs_contacted": len(deal_ids),
            "positive_conversations": positive,
            "callbacks_created": callbacks,
            "trials_started": trials_started,
        }

    return {"today": await _window(today_start), "week": await _window(week_start)}


async def funnel_by_rep(session: AsyncSession, *, owner_user_id=None) -> list[dict]:
    """Assigned -> Attempted -> Contacted -> Engaged -> Trial -> Won, per
    rep, from currently-assigned OPEN-OR-CLOSED platform deals (a won/lost
    deal still counts in its rep's funnel — that's the point of the funnel).
    Archived deals are excluded. owner_user_id restricts to one rep."""
    pipeline = await crm_service.ensure_platform_pipeline(session)
    stage_by_id = {s.id: s for s in pipeline.stages}

    deals_stmt = select(CrmDeal).where(
        CrmDeal.pipeline_id == pipeline.id, CrmDeal.archived_at.is_(None), CrmDeal.owner_user_id.isnot(None),
    )
    if owner_user_id is not None:
        deals_stmt = deals_stmt.where(CrmDeal.owner_user_id == owner_user_id)
    deals = (await session.execute(deals_stmt)).scalars().all()

    ever_called_deal_ids = set()
    if deals:
        rows = (await session.execute(
            select(CrmActivity.deal_id)
            .where(CrmActivity.deal_id.in_([d.id for d in deals]), CrmActivity.type == "call")
            .distinct()
        )).scalars().all()
        ever_called_deal_ids = set(rows)

    by_owner: dict = {}
    for d in deals:
        b = by_owner.setdefault(d.owner_user_id, {"assigned": 0, "attempted": 0, "contacted": 0, "engaged": 0, "trial": 0, "won": 0})
        b["assigned"] += 1
        if d.id in ever_called_deal_ids:
            b["attempted"] += 1
        stage = stage_by_id.get(d.stage_id)
        key = stage.key if stage else None
        for bucket, keys in _FUNNEL_STAGE_KEYS.items():
            if key in keys:
                b[bucket] += 1

    owners = {}
    if by_owner:
        rows = (await session.execute(select(User).where(User.id.in_(by_owner.keys())))).scalars().all()
        owners = {u.id: u for u in rows}

    def _rate(n: int, d: int) -> int:
        return round(100 * n / d) if d else 0

    out = []
    for oid, b in by_owner.items():
        owner = owners.get(oid)
        out.append({
            "owner_user_id": str(oid),
            "owner_name": (owner.display_name or owner.username) if owner else "Unknown",
            **b,
            "attempt_rate": _rate(b["attempted"], b["assigned"]),
            "contact_rate": _rate(b["contacted"], b["assigned"]),
            "engaged_rate": _rate(b["engaged"], b["assigned"]),
            "trial_rate": _rate(b["trial"], b["assigned"]),
            "win_rate": _rate(b["won"], b["assigned"]),
        })
    out.sort(key=lambda r: r["assigned"], reverse=True)
    return out


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
