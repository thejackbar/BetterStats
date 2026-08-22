"""Sales Workspace — Phase 1: the calling-focused lens over BetterCRM's
platform pipeline (see services/sales_workspace.py for the design rationale).

Gated by ``require_sales_or_super`` (routers/auth.py) rather than
``require_super_admin`` — a 'sales'-role user gets the same shape of access a
super admin does here, restricted to the deals they own (``owner_user_id``).
Every write re-uses the SAME crm_deals/crm_activities/crm_people rows the
Sales Pipeline board manages; there is no separate Sales Workspace schema.
"""
from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.db import (
    ClubMembership, CrmActivity, CrmDeal, CrmEvent, CrmPerson, MarketingClub, MarketingClubContact,
    Organisation, SalesListClub, User, get_db,
)
from app.routers.auth import SalesActor, require_sales_or_super
from app.services import crm as crm_service
from app.services import sales_workspace as sw

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/club-admin/sales-workspace", tags=["sales-workspace"])


def _uuid_or_none(value: Optional[str]):
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid id")


async def _load_deal(db: AsyncSession, deal_id: str) -> CrmDeal:
    """The one chokepoint every handler loads a deal through. Always
    refreshes: db.get() on an object already in the identity map does NOT
    by itself repopulate attributes a prior commit()/rollback() in this same
    request expired (verified against a real Postgres instance while
    building this — a naive db.get()-only reload still threw MissingGreenlet
    the moment a handler serialised the deal after its own commit). A plain
    first-ever load in this request just costs one harmless extra
    primary-key SELECT."""
    did = _uuid_or_none(deal_id)
    deal = await db.get(CrmDeal, did) if did else None
    if deal is None:
        raise HTTPException(status_code=404, detail="Club not found")
    await db.refresh(deal)
    if deal.scope != crm_service.SCOPE_PLATFORM or deal.archived_at is not None:
        raise HTTPException(status_code=404, detail="Club not found")
    return deal


def _assert_can_touch(actor: SalesActor, deal: CrmDeal) -> None:
    if actor.role == "sales" and (deal.owner_user_id is None or str(deal.owner_user_id) != str(actor.user.id)):
        raise HTTPException(status_code=403, detail="This club isn't assigned to you")


def _require_super(actor: SalesActor) -> None:
    if actor.role != "super_admin":
        raise HTTPException(status_code=403, detail="Super admin only")


async def _validated_staff_id(db: AsyncSession, raw: Optional[str]):
    """Resolve+validate a staff-picker value (the "Me" / GET /staff pool used
    by both the assignable-follow-up-owner call form and manual Event
    creation) against the real super_admin pool. Returns None for a blank
    value; 422s for anyone else."""
    if not raw:
        return None
    owner_id = _uuid_or_none(raw)
    is_staff = owner_id and (await db.execute(
        select(ClubMembership).where(
            ClubMembership.user_id == owner_id, ClubMembership.role == "super_admin",
        )
    )).scalar_one_or_none() is not None
    if not is_staff:
        raise HTTPException(status_code=422, detail="Unknown staff member")
    return owner_id


_SORT_KEYS = ("recent", "club_name", "engagement_score", "trial_days")
_SORT_DEFAULT_DIR = {"recent": "desc", "club_name": "asc", "engagement_score": "desc", "trial_days": "asc"}


def _sort_rows(rows: list, sort_key: Optional[str], sort_dir: Optional[str]) -> None:
    """Sorts ``rows`` (the queue's output dicts) in place. An unrecognised
    ``sort_key`` keeps the existing priority_score heuristic — the queue's
    long-standing default, unaffected by this ever being called with
    sort=None. For engagement_score/trial_days, a row with nothing to sort
    on (None) is placed dead last via a (is_missing, value) tuple key rather
    than a bare ``reverse=``, since reversing the whole key would also flip
    missing rows to the front."""
    if sort_key not in _SORT_KEYS:
        rows.sort(key=lambda r: r["priority_score"], reverse=True)
        return
    descending = (sort_dir if sort_dir in ("asc", "desc") else _SORT_DEFAULT_DIR[sort_key]) == "desc"

    if sort_key == "recent":
        rows.sort(key=lambda r: r["updated_at"] or "", reverse=descending)
    elif sort_key == "club_name":
        rows.sort(key=lambda r: (r["marketing_club_name"] or r["title"] or "").lower(), reverse=descending)
    elif sort_key == "engagement_score":
        rows.sort(key=lambda r: (
            r["engagement_score"] is None,
            -(r["engagement_score"] or 0) if descending else (r["engagement_score"] or 0),
        ))
    elif sort_key == "trial_days":
        # Signed already (negative = days since a trial expired, positive =
        # days remaining on a current one) — see crm_service.
        # trial_days_remaining_by_club. Ascending naturally clusters a
        # just-lapsed trial (a small negative) next to one about to lapse (a
        # small positive) around zero.
        rows.sort(key=lambda r: (
            r["min_trial_days_remaining"] is None,
            -(r["min_trial_days_remaining"] or 0) if descending else (r["min_trial_days_remaining"] or 0),
        ))


# ─── Queue ────────────────────────────────────────────────────────────────────

# "Nobody" in an Assigned/Attributed pick. A UUID can never spell this, so it
# rides in the same comma-list as the real ids rather than needing a second
# parameter — which is what lets "unassigned, or Kate" be one selection.
UNASSIGNED_PICK = "unassigned"


def _people_filter(*raw_values) -> Optional[set]:
    """The set a people-picker asked for, or None for "no filter at all".
    Accepts several raw comma-lists and unions them, so the older single
    ``owner_user_id`` and the newer ``owner_user_ids`` compose instead of
    fighting. A value that is neither a UUID nor the sentinel raises 422 via
    ``_uuid_or_none``, same as every other id this router reads off the query
    string — these only ever come from the app's own picker, so junk means a
    hand-edited URL and saying so beats quietly returning a different set of
    clubs than the one asked for."""
    picked = set()
    seen_any = False
    for raw in raw_values:
        if not raw:
            continue
        for part in str(raw).split(","):
            part = part.strip()
            if not part:
                continue
            seen_any = True
            picked.add(UNASSIGNED_PICK if part == UNASSIGNED_PICK else _uuid_or_none(part))
    if not seen_any:
        return None
    return picked


def _person_matches(picked: set, user_id) -> bool:
    """Does this deal's owner (or attributing rep) satisfy the pick?"""
    if not picked:
        return True
    if user_id is None:
        return UNASSIGNED_PICK in picked
    return user_id in picked



@router.get("/clubs")
async def list_clubs(
    q: Optional[str] = None,
    stage_key: Optional[str] = None,
    owner_user_id: Optional[str] = None,
    owner_user_ids: Optional[str] = None,
    attributed_user_ids: Optional[str] = None,
    called_clubs: bool = False,
    callback_due: bool = False,
    voicemail: bool = False,
    call_status: Optional[str] = None,
    list_id: Optional[str] = None,
    min_score: Optional[int] = None,
    max_score: Optional[int] = None,
    meta_selected: bool = False,
    meta_searched: bool = False,
    modules: Optional[str] = None,
    states: Optional[str] = None,
    sort: Optional[str] = None,
    sort_dir: Optional[str] = None,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    """One row per club (an open platform deal), sorted by a simple priority
    heuristic by default. A 'sales'-role caller only ever sees their own
    deals — the owner_user_id query param is honoured for a super admin only.
    ``list_id`` narrows the queue to one Sales List's clubs (still whatever
    deal each one currently is, not a frozen snapshot). ``min_score``/
    ``max_score`` filter on the club's engagement score (0-100) — a deal
    with no score (no linked club, or never scored) is excluded whenever
    either bound is set, same rule the Sales Pipeline board's own score
    filter uses. ``stage_key`` may hold several stage keys comma-separated
    (a club matching ANY of them is kept — narrowing to "Target, Contacted"
    is an OR within the field). Two synthetic keys, ``trial_current`` /
    ``trial_expired``, split the single real 'trial' stage by whether the
    club's own trial has actually lapsed (see crm_service.
    trial_days_remaining_by_club) — a club with no trial data at all reads
    as current, never expired, since there's nothing proving it's lapsed.
    ``meta_selected``/``meta_searched`` filter to clubs that picked
    themselves / searched for themselves in the trial signup wizard (Meta
    Ads' own source split); ticking both is an OR ("either"), ticking one is
    that one alone. ``modules`` is a comma-list of module keys (core/select/
    socials/admin/iq/fantasy) — a club matching ANY of them (its own
    module_keys intersects the requested set) is kept, an OR within the
    field same as ``stage_key``. ``states`` is a comma-list of the club's own
    ``MarketingClub.state`` (e.g. "WA,NSW") — an OR, same shape again; a deal
    with no linked club (and so no state) never matches a non-empty list.

    ``owner_user_ids`` is the queue's ASSIGNED filter: a comma-list of user
    ids, plus the sentinel ``unassigned`` for a club nobody holds, ORed
    within the field (same shape as ``states``/``modules``). The older
    single ``owner_user_id`` still works and simply joins the same set, so a
    saved link written before the filter took several values keeps working.
    ``attributed_user_ids`` is the separate ATTRIBUTED filter — which rep
    EARNED the club (crm_deals.commission_rep_user_id, see the commission
    note in services/sales_workspace.py), never who currently holds it —
    same comma-list shape and the same ``unassigned`` sentinel for a club no
    rep has earned. Both are super-admin-only: a 'sales' caller is already
    pinned to their own assigned deals and neither param widens that.

    ``sort`` picks the ordering: ``recent`` (deal.updated_at, newest first),
    ``club_name`` (A-Z), ``engagement_score`` (highest first), ``trial_days``
    (soonest-concern first — an expired trial's negative "days ago" sorts
    before a current trial's positive "days left", so a just-lapsed trial and
    an about-to-lapse one land next to each other around zero); omitted or
    unrecognised falls back to the existing ``priority_score`` heuristic. A
    row with nothing to sort on (no engagement score / no trial data) always
    sorts last, whichever direction is picked, since "unknown" isn't
    meaningfully high or low. ``sort_dir`` ('asc'|'desc') overrides each
    field's own sensible default (recent/engagement_score default to desc,
    club_name/trial_days default to asc).

    ``call_status`` is the queue's Call status filter: a comma-list of the
    buckets in services/sales_workspace.CALL_STATUS_KEYS (``not_called``/
    ``called``/``followup``/``voicemail``/``sent_email``), ORed — a club is
    kept when it answers to ANY of the listed ones. The buckets OVERLAP (see
    ``call_statuses_of``): a club that was rung, went to voicemail and was
    then emailed is Called and VM and Sent Email at once, so unticking any
    one of those hides it. ``callback`` is still accepted as the old name
    for ``followup``, so a saved link or a stored preference written before
    the rename keeps working. An empty or unrecognised list ('none', which
    is what the screen sends with every box unticked) matches nothing and
    returns an empty queue — which is what unticking every box asks for.

    ``call_status`` REPLACES the older ``called_clubs``/``callback_due``/
    ``voicemail`` booleans, which are still honoured when it is omitted so a
    link saved before this shipped keeps working. Those ARE mutually
    exclusive, most-specific first — the behaviour they had when they were
    written, kept exactly as it was rather than quietly re-pointed at the
    new overlapping rules: ``callback_due`` (a due/overdue
    follow-up — inherently a called club, since a follow-up can only exist
    once a call has been logged) takes precedence over everything else; else
    ``voicemail`` narrows to every club whose most recent call outcome was
    'voicemail'; else ``called_clubs`` narrows to every club that's ever
    been called; else — with none ticked — the queue shows only clubs that
    have NEVER been called, which is what a rep actually wants to see by
    default (a calling QUEUE, not a call log). That last default does NOT
    apply while ``attributed_user_ids`` is set: a club is only ever earned
    by a call or an email, so "earned by Sam" and "never called" are all
    but mutually exclusive and the pair would come back empty however much
    work the rep has done."""
    pipeline = await crm_service.ensure_platform_pipeline(db)
    stage_by_id = {s.id: s for s in pipeline.stages}
    stage_by_key = {s.key: s for s in pipeline.stages}
    trial_stage_id = stage_by_key["trial"].id if "trial" in stage_by_key else None

    # A 'sales' caller is pinned to their own deals in SQL, which is the
    # access rule and not a filter. The super admin's own Assigned/Attributed
    # pickers take several values (and an "unassigned" sentinel), so they are
    # applied in Python below alongside the other multi-value filters rather
    # than through list_deals' single-owner argument.
    effective_owner = actor.user.id if actor.role == "sales" else None
    assigned_pick = _people_filter(owner_user_ids, owner_user_id) if actor.role != "sales" else None
    attributed_pick = _people_filter(attributed_user_ids) if actor.role != "sales" else None

    deals = await crm_service.list_deals(db, pipeline.id, status="open", owner_user_id=effective_owner)
    if assigned_pick is not None:
        deals = [d for d in deals if _person_matches(assigned_pick, d.owner_user_id)]
    if attributed_pick is not None:
        deals = [d for d in deals if _person_matches(attributed_pick, d.commission_rep_user_id)]
    # Belt-and-braces on top of the status="open" filter above: a deal can be
    # sitting in a Won/Lost stage while its own `status` column still reads
    # "open" (e.g. one created directly into that stage — see create_deal,
    # which doesn't derive `status` from the target stage the way move_stage
    # does for an existing deal's transition). The queue is a calling list —
    # a club that's already Won or Lost/Dormant is not a call to make, so
    # filter on the STAGE's own terminal flags directly rather than trusting
    # `status` alone stays in sync with it.
    def _is_terminal_stage(d):
        s = stage_by_id.get(d.stage_id)
        return bool(s and (s.is_won or s.is_lost))
    deals = [d for d in deals if not _is_terminal_stage(d)]
    if list_id:
        lid = _uuid_or_none(list_id)
        member_rows = (await db.execute(
            select(SalesListClub.marketing_club_id).where(SalesListClub.sales_list_id == lid)
        )).scalars().all()
        member_ids = set(member_rows)
        deals = [d for d in deals if d.marketing_club_id in member_ids]

    # club_by_id / min_trial_days computed here, ahead of the stage filter,
    # since splitting 'trial' into current/expired needs the trial data to
    # decide the split — reused below for the output rows too, so this isn't
    # a second query later.
    club_by_id = await crm_service.clubs_by_ids(db, (d.marketing_club_id for d in deals))
    trial_days_by_club = await crm_service.trial_days_remaining_by_club(db, club_by_id)
    min_trial_by_club = {
        cid: min(days.values()) for cid, days in trial_days_by_club.items() if days
    }

    def _trial_expired(club_id):
        days = min_trial_by_club.get(club_id)
        return days is not None and days < 0

    if states:
        wanted_states = {s for s in states.split(",") if s}
        deals = [d for d in deals
                 if club_by_id.get(d.marketing_club_id) and club_by_id[d.marketing_club_id].state in wanted_states]
    if stage_key:
        requested = [k for k in stage_key.split(",") if k]
        wants_trial_current = "trial_current" in requested
        wants_trial_expired = "trial_expired" in requested
        wanted_stage_ids = {stage_by_key[k].id for k in requested if k in stage_by_key}

        def _stage_match(d):
            if d.stage_id in wanted_stage_ids:
                return True
            if trial_stage_id is not None and d.stage_id == trial_stage_id:
                expired = _trial_expired(d.marketing_club_id)
                if wants_trial_current and not expired:
                    return True
                if wants_trial_expired and expired:
                    return True
            return False
        deals = [d for d in deals if _stage_match(d)]
    if meta_selected or meta_searched:
        wizard_map = await sw.wizard_source_by_club(db)
        def _meta_match(club_id):
            flags = wizard_map.get(club_id)
            if not flags:
                return False
            return (meta_selected and flags["selected"]) or (meta_searched and flags["searched"])
        deals = [d for d in deals if d.marketing_club_id and _meta_match(d.marketing_club_id)]
    if q:
        needle = q.strip().lower()
        # Matches the club/deal title OR any of that club's contacts' names —
        # a rep searching "Pat Smith" should find the club Pat is the
        # secretary of, not just a club literally named "Pat Smith". Scoped
        # to the clubs already in scope at this point (post list/stage/meta
        # filters), so this never becomes an unbounded contact scan.
        candidate_club_ids = [d.marketing_club_id for d in deals if d.marketing_club_id]
        contact_match_ids = set()
        if candidate_club_ids:
            contact_match_ids = set((await db.execute(
                select(MarketingClubContact.marketing_club_id).where(
                    MarketingClubContact.marketing_club_id.in_(candidate_club_ids),
                    func.lower(MarketingClubContact.full_name).contains(needle),
                )
            )).scalars().all())
        deals = [d for d in deals if needle in (d.title or "").lower()
                 or (d.marketing_club_id and d.marketing_club_id in contact_match_ids)]
    if modules:
        wanted_modules = {m for m in modules.split(",") if m}
        deals = [d for d in deals if wanted_modules & set(d.module_keys or [])]

    deal_ids = [d.id for d in deals]
    last_calls = await sw.last_calls_by_deal(db, deal_ids)
    emailed = await sw.emailed_deal_ids(db, deal_ids)
    follow_ups = await sw.next_follow_ups_by_deal(db, deal_ids)
    contact_counts = await sw.contact_counts_by_club(db, (d.marketing_club_id for d in deals))

    # One lookup for both names on the row: who holds the club (owner) and
    # who earned it (the attributing rep). They are usually the same person
    # and often the same id, hence one query over the union rather than two.
    owner_ids = {d.owner_user_id for d in deals if d.owner_user_id}
    owner_ids |= {d.commission_rep_user_id for d in deals if d.commission_rep_user_id}
    owners = {}
    if owner_ids:
        rows = (await db.execute(select(User).where(User.id.in_(owner_ids)))).scalars().all()
        owners = {u.id: u for u in rows}

    # String comparison (not datetime), matching next_follow_up_at's own
    # isoformat() below — CrmActivity.next_follow_up_at is TIMESTAMPTZ, so a
    # naive datetime.utcnow() can't be compared against it directly without
    # tripping over tz-awareness; ISO strings compare correctly either way.
    now_iso = datetime.utcnow().isoformat()
    out = []
    for d in deals:
        club = club_by_id.get(d.marketing_club_id)
        row = crm_service._deal_dict(d, stage_by_id.get(d.stage_id), club)
        owner = owners.get(d.owner_user_id)
        row["owner_name"] = (owner.display_name or owner.username) if owner else None
        rep = owners.get(d.commission_rep_user_id)
        row["commission_rep_name"] = (rep.display_name or rep.username) if rep else None
        row["contact_count"] = contact_counts.get(d.marketing_club_id, 0)
        row["not_interested"] = bool(club.not_interested) if club else False
        # marketing_club_suburb / _state / _association / _associations are
        # already set by _deal_dict above (club is passed in) — the queue
        # card's "Town, ST" line and its associations chips read straight
        # off those, same fields the drawer header carries (get_club below).
        row["min_trial_days_remaining"] = min_trial_by_club.get(d.marketing_club_id)
        # Trial is the one stage that reads differently depending on whether
        # it's actually still live — split the display label the same way
        # the stage filter itself splits it, so the queue row and the filter
        # never disagree about what "expired" means.
        if trial_stage_id is not None and d.stage_id == trial_stage_id:
            row["stage_name"] = "Trial (Expired)" if _trial_expired(d.marketing_club_id) else "Trial (Current)"
        last_call = last_calls.get(d.id)
        row["ever_called"] = last_call is not None
        row["last_call"] = crm_service._activity_dict(last_call) if last_call else None
        row["last_call_outcome"] = last_call.outcome if last_call else None
        follow_up_at = follow_ups.get(d.id)
        row["next_follow_up_at"] = follow_up_at.isoformat() if follow_up_at else None
        # Precomputed for the queue row's own highlight colour (blue = a
        # due/overdue follow-up, orange = called with nothing pending) so the
        # frontend doesn't re-derive the date comparison itself.
        row["callback_due"] = bool(row["next_follow_up_at"] and row["next_follow_up_at"] <= now_iso)
        row["sent_email"] = d.id in emailed
        # Every bucket this club answers to, computed once here so the filter
        # below and anything else reading it can't drift apart. A set is not
        # JSON, so it is popped back off before the response is built.
        row["call_statuses"] = sw.call_statuses_of(
            ever_called=row["ever_called"], followup_due=row["callback_due"],
            last_call_outcome=row["last_call_outcome"], sent_email=row["sent_email"],
        )
        # deal.updated_at is a cheap proxy for "recent signal" (it also moves
        # on engagement-driven auto-promotion elsewhere in the CRM engine) —
        # a full multi-source recency query per row isn't worth it for a v1
        # heuristic. See services/sales_workspace.priority_score's own note.
        row["priority_score"] = sw.priority_score(
            engagement_score=row["engagement_score"], ever_called=row["ever_called"],
            next_follow_up_at=follow_up_at, last_signal_at=d.updated_at,
        )
        out.append(row)

    # The Call status filter: keep a club if it answers to ANY ticked box. The
    # buckets overlap (a club that was rung, went to voicemail and was then
    # emailed is all three at once — see sw.call_statuses_of), so this is a set
    # intersection rather than the single-bucket test it started as. An
    # explicit set always wins, Attributed pick or not, because it is the
    # rep's own choice rather than an implicit default.
    if call_status is not None:
        picked_status = {
            sw.CALL_STATUS_ALIASES.get(s.strip(), s.strip())
            for s in call_status.split(",") if s.strip()
        } & set(sw.CALL_STATUS_KEYS)
        out = [r for r in out if r["call_statuses"] & picked_status]
    # Legacy: most-specific-first, mutually exclusive — see the docstring above.
    elif callback_due:
        out = [r for r in out if r["callback_due"]]
    elif voicemail:
        out = [r for r in out if r["last_call_outcome"] == "voicemail"]
    elif called_clubs:
        out = [r for r in out if r["ever_called"]]
    elif attributed_pick is None:
        out = [r for r in out if not r["ever_called"]]
    # else: an Attributed pick asks which clubs a rep has EARNED, and a club
    # is only ever earned by a logged call or a sent email — so the
    # never-called default empties that answer by construction, which is
    # exactly what it did when the filter first shipped. An explicit Called /
    # Callback / Voicemail tick still narrows it; only the implicit default
    # steps aside.
    if min_score is not None:
        out = [r for r in out if r["engagement_score"] is not None and r["engagement_score"] >= min_score]
    if max_score is not None:
        out = [r for r in out if r["engagement_score"] is not None and r["engagement_score"] <= max_score]

    _sort_rows(out, sort, sort_dir)
    # A set can't be serialised, and the browser has no use for it — the row
    # already carries the flags it is built from (ever_called / callback_due /
    # last_call_outcome / sent_email) for the row's own highlight.
    for r in out:
        r.pop("call_statuses", None)
    return {
        "clubs": out,
        "stages": [{"id": str(s.id), "key": s.key, "name": s.name} for s in pipeline.stages],
    }


@router.get("/team")
async def team(actor: SalesActor = Depends(require_sales_or_super), db: AsyncSession = Depends(get_db)):
    """Sales reps, for the super admin's owner filter/assignment picker.
    Provisioning a new one is done from Super Admin -> Users (role 'sales').

    Reuses crm_service.list_platform_owners' fold (roles narrowed to just
    'sales'), same reason /staff below does: a rep holding two accounts
    under one name, or one account with more than one ClubMembership row,
    would otherwise list twice."""
    _require_super(actor)
    owners = await crm_service.list_platform_owners(db, roles=("sales",))
    return {"team": [
        {"id": o["id"], "username": "", "display_name": o["name"]}
        for o in owners
    ]}


@router.get("/performance")
async def performance(
    owner_user_id: Optional[str] = None,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    """Three views of the same book, on one screen.

    * ``summary`` — today/this-week contact activity, the KPI strip.
    * ``activity`` — the same numbers split per rep, so "who has called whom
      today" is answerable at a glance. Its totals ARE ``summary``, taken
      from one pass over the activity rows rather than counted twice, so the
      strip and the table can never disagree.
    * ``by_rep`` — where every deal sits, per rep, plus an Unassigned row for
      the pool nobody owns yet.

    A 'sales'-role caller always sees only their own numbers (owner_user_id
    is honoured for a super admin only, same restriction pattern as the
    queue list)."""
    effective_owner = actor.user.id if actor.role == "sales" else (_uuid_or_none(owner_user_id) if owner_user_id else None)
    activity = await sw.activity_report(db, owner_user_id=effective_owner)
    breakdown = await sw.stage_breakdown_by_rep(db, owner_user_id=effective_owner)
    return {
        "summary": {"today": activity["totals"]["today"], "week": activity["totals"]["week"]},
        "activity": activity["rows"],
        "by_rep": breakdown["rows"],
        "totals": breakdown["totals"],
        "stage_columns": breakdown["stage_columns"],
    }


@router.get("/performance/drilldown")
async def performance_drilldown(
    panel: str,
    window: Optional[str] = None,
    metric: Optional[str] = None,
    user_id: Optional[str] = None,
    owner: Optional[str] = None,
    cell: Optional[str] = None,
    contacted_only: bool = False,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    """The clubs behind ONE figure on the Performance screen.

    ``panel='activity'`` takes window/metric/user_id and answers a Contact
    activity cell; ``panel='pipeline'`` takes owner/cell/contacted_only and
    answers a stage-breakdown cell. Both re-run the predicates that produced
    the number rather than a query shaped like them, so the list can never
    disagree with what was clicked.

    A 'sales'-role caller is pinned to their own work exactly as the screen
    itself is — the cell identifiers arrive from a browser, so the pin is
    applied server-side and not trusted from the params."""
    pinned = actor.user.id if actor.role == "sales" else None
    try:
        if panel == "activity":
            result = await sw.activity_cell_clubs(
                db, user_id=user_id or sw.EVERYONE_KEY, window=window or "today",
                metric=metric or "contacts", owner_user_id=pinned)
        elif panel == "pipeline":
            result = await sw.pipeline_cell_clubs(
                db, owner=owner or sw.ALL_OWNERS_KEY, cell=cell or "to_contact",
                contacted_only=contacted_only, owner_user_id=pinned)
        else:
            raise HTTPException(400, "Unknown panel")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return result


# ─── Club drawer ──────────────────────────────────────────────────────────────

@router.get("/clubs/{deal_id}")
async def get_club(
    deal_id: str,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    deal = await _load_deal(db, deal_id)
    _assert_can_touch(actor, deal)

    pipeline = await crm_service.get_deal_pipeline(db, deal)
    stage = next((s for s in pipeline.stages if s.id == deal.stage_id), None) if pipeline else None
    club = await db.get(MarketingClub, deal.marketing_club_id) if deal.marketing_club_id else None

    contacts = await sw.merged_contacts(db, deal.marketing_club_id)
    activities = await sw.list_activities_for_workspace(db, deal_id=deal.id)
    activities_out = [crm_service._activity_dict(a) for a in activities]
    # Who logged each call/note/email/assign/extend-trial — every one of
    # those writers already stamps created_by_user_id, this just names it for
    # the History feed. Batched, one query for the whole timeline.
    creator_names = await sw.user_names_by_ids(db, (a.created_by_user_id for a in activities))
    for row, a in zip(activities_out, activities):
        row["created_by_name"] = creator_names.get(a.created_by_user_id)

    # Every ORM attribute this response needs is read into plain dicts/lists
    # BEFORE calling club_engagement_breakdown below — that function commits
    # to "read-only, always rollback", and a rollback expires every ORM
    # object still attached to this session (deal/stage/club included), which
    # would otherwise throw MissingGreenlet the moment _deal_dict tried to
    # read an attribute off `deal` afterward.
    deal_out = crm_service._deal_dict(deal, stage, club)
    deal_out["not_interested"] = bool(club.not_interested) if club else False
    stage_options = [{"id": str(s.id), "key": s.key, "name": s.name} for s in (pipeline.stages if pipeline else [])]

    # Onboarded-club facts (state/seasons/grades/players/setup/active-since +
    # trial countdown) — same batched helpers the Sales Pipeline card and
    # list use, just called with a single-club map since this is one deal.
    # Absent (None) for a bare prospect that's never been onboarded.
    # marketing_club_state / _suburb / _association / _associations are
    # already set by _deal_dict above (club is passed in) — the header's
    # "Town, ST" line and associations chips read straight off those.
    # Feeds ClubLocationMap.jsx in the drawer (same component/props the Club
    # Directory's own map already uses) — Numeric columns need a float cast,
    # since json can't serialise a Decimal.
    deal_out["marketing_club_latitude"] = float(club.latitude) if club and club.latitude is not None else None
    deal_out["marketing_club_longitude"] = float(club.longitude) if club and club.longitude is not None else None
    deal_out["marketing_club_postcode"] = club.postcode if club else None
    club_stats = None
    trial_days = None
    min_trial_days = None
    if club is not None:
        stats_map = await crm_service.club_stats_by_club(db, {club.id: club})
        club_stats = stats_map.get(club.id)
        trial_map = await crm_service.trial_days_remaining_by_club(db, {club.id: club})
        trial_days = trial_map.get(club.id)
        min_trial_days = min(trial_days.values()) if trial_days else None
    deal_out["club_stats"] = club_stats
    deal_out["trial_days_remaining"] = trial_days
    deal_out["min_trial_days_remaining"] = min_trial_days

    # For the header's "primary admin" line under Onboarding — only shown
    # while a trial is live or has expired, so only look it up then. A bare
    # prospect (no existing_org_id yet) has no real ClubMembership to read.
    primary_admin_name = None
    if club is not None and club.existing_org_id and min_trial_days is not None:
        admin_row = (await db.execute(
            select(User.first_name, User.last_name, User.display_name)
            .join(ClubMembership, ClubMembership.user_id == User.id)
            .where(ClubMembership.club_id == club.existing_org_id, ClubMembership.is_primary_admin.is_(True))
            .limit(1)
        )).first()
        if admin_row is not None:
            first, last, display = admin_row
            name = " ".join(p for p in (first, last) if p) or display
            primary_admin_name = name or None
    deal_out["primary_admin_name"] = primary_admin_name

    # Who registered for the trial (the deal's point of contact — set to the
    # registering admin at signup, see crm.sync_self_serve_trial_registration/
    # sync_super_admin_trial_registration), plus their committee role if a
    # Club Directory contact shares their email (the officer-list crawl is
    # what actually carries a role like "President" — the registration form
    # itself never asks for one).
    registrant = None
    poc_map = await crm_service.poc_contacts_by_deal(db, [deal.id])
    poc = poc_map.get(deal.id)
    if poc and poc.get("name"):
        role = None
        poc_email = (poc.get("email") or "").strip().lower()
        if poc_email:
            match = next((c for c in contacts
                          if (c.get("email") or "").strip().lower() == poc_email and c.get("role")), None)
            if match:
                role = match["role"]
        registrant = {"name": poc["name"], "email": poc.get("email"), "role": role}
    deal_out["registrant"] = registrant

    # Same shape the queue list already carries, so the drawer's own "Called
    # / Never called" reads off the identical field the queue row does.
    deal_out["commission_rep_name"] = (
        await sw.commission_rep_names(db, [deal])).get(deal.commission_rep_user_id)
    last_call = (await sw.last_calls_by_deal(db, [deal.id])).get(deal.id)
    deal_out["ever_called"] = last_call is not None
    deal_out["last_call"] = crm_service._activity_dict(last_call) if last_call else None

    engagement = None
    website_visits = None
    if club is not None:
        club_id_for_reads = club.id  # captured now: club_engagement_breakdown
                                      # below commits, which expires every ORM
                                      # object in this session (see its own
                                      # docstring) — read anything else off
                                      # `club` before calling it, not after.
        # Website analytics (page views/days visited/unique IPs/contact-page
        # hit) — the CRM card's own panel, `components/admin/crm/ui.jsx`'s
        # `WebsiteAnalyticsPanel`, fetches this itself via a super-admin-only
        # endpoint a 'sales' caller can't reach directly, so it's embedded in
        # the drawer payload here instead (same reasoning as `engagement`
        # below), via the exact service function that endpoint calls. Read
        # BEFORE the engagement breakdown for the same expiry reason.
        try:
            from app.services import club_directory as cd
            website_visits = await cd.club_visit_detail(db, club_id_for_reads, fast_web=True)
        except Exception:  # noqa: BLE001 - the drawer must still render without it
            logger.exception("sales_workspace: website visits failed for club %s", club_id_for_reads)
            website_visits = None
        try:
            from app.routers.marketing import club_engagement_breakdown
            engagement = await club_engagement_breakdown(str(club_id_for_reads), db)
        except HTTPException:
            engagement = None
        except Exception:  # noqa: BLE001 - the drawer must still render without it
            logger.exception("sales_workspace: engagement breakdown failed for club %s", club_id_for_reads)
            engagement = None

    return {
        "deal": deal_out,
        "contacts": contacts,
        "activities": activities_out,
        "engagement": engagement,
        "website_visits": website_visits,
        # No boundary here on purpose. It is the ONLY thing in this handler
        # that leaves the building — a Nominatim lookup for a club whose
        # polygon has never been cached — so embedding it made a first open
        # wait about a second (up to the client's 15s timeout on a bad day)
        # while every later open was instant. That is the whole "some clubs
        # are slower" report. The map fetches it itself now, after the pane
        # has rendered; see GET /clubs/{deal_id}/boundary below.
        "stage_options": stage_options,
        "can_assign": actor.role == "super_admin",
    }


@router.get("/clubs/{deal_id}/boundary")
async def get_club_boundary(
    deal_id: str,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    """The club's suburb polygon for the drawer's map overlay, fetched on its
    own so a cold lookup can't hold up the pane around it.

    Exists because ClubLocationMap's usual source, `/marketing/clubs/{id}/
    boundary`, is super-admin-only and a 'sales' caller can't reach it — the
    same reason the drawer used to embed the polygon. Deal-scoped rather than
    club-scoped so the rep's own access rule still decides it: _assert_can_touch
    is the same gate every other action on this club goes through.

    A club whose polygon is already cached answers from the row; only a club
    that has never been looked up costs an upstream call, and the result is
    cached on the row forever.
    """
    deal = await _load_deal(db, deal_id)
    _assert_can_touch(actor, deal)
    if not deal.marketing_club_id:
        return {"geojson": None}
    try:
        from app.services import club_directory as cd
        return {"geojson": await cd.get_or_fetch_boundary(db, deal.marketing_club_id)}
    except Exception:  # noqa: BLE001 - the map must degrade, never 500 the drawer
        logger.exception("sales_workspace: boundary lookup failed for deal %s", deal_id)
        return {"geojson": None}


@router.get("/clubs/{deal_id}/signals")
async def get_club_signals(
    deal_id: str,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    """Where this club came from — the three beacon-backed stories the drawer
    tells under the club's own details.

    * ``wizard`` — did somebody search for this club, or pick it, on /trial.
    * ``registration`` — how far into the self-serve registration they got,
      on the real eight-step funnel, and whether they finished.
    * ``meta_ads`` — the ad traffic behind whatever the engagement score
      credited to Meta: which campaign and creative, how many landings, when.

    Its own endpoint on purpose. Every one of these reads a beacon table, and
    ``wizard`` in particular resolves through the whole-platform Wizard Clubs
    rollup (cached for three minutes, several seconds to rebuild) — so
    embedding it meant the pane hung for whoever's click happened to land on
    an expired cache, seemingly at random. The pane renders first now and
    these fill in behind it.

    Each part fails independently: a card that can't be built is simply
    absent, never a 500 on the drawer beside it.
    """
    deal = await _load_deal(db, deal_id)
    _assert_can_touch(actor, deal)
    club = await db.get(MarketingClub, deal.marketing_club_id) if deal.marketing_club_id else None

    async def _safe(what, coro):
        try:
            return await coro
        except Exception:  # noqa: BLE001 - a missing card beats a broken drawer
            logger.exception("sales_workspace: %s failed for deal %s", what, deal_id)
            return None

    return {
        "wizard": await _safe("wizard signal", sw.wizard_signal_for_club(db, deal.marketing_club_id))
        if deal.marketing_club_id else None,
        "registration": await _safe("registration journey", sw.registration_journey(db, club)),
        "meta_ads": await _safe("meta ad summary", sw.meta_ad_summary(db, club)),
    }


class InterestBody(BaseModel):
    module_keys: list[str]


@router.patch("/clubs/{deal_id}/interest")
async def set_interest(
    deal_id: str,
    body: InterestBody,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    """Which modules a rep has flagged the club as interested in — the SAME
    ``module_keys``/``product_interest_source`` fields the Sales Pipeline
    board's own Product Interest chips edit (DealDetailModal.jsx), so a pick
    made here shows up there too and vice versa. Reusing that PATCH endpoint
    directly isn't possible: it's super-admin only, and a 'sales' caller must
    only be able to touch their own deals — this is the same restriction
    every other write in this router applies via ``_assert_can_touch``."""
    deal = await _load_deal(db, deal_id)
    _assert_can_touch(actor, deal)
    keys = sorted({k for k in (body.module_keys or []) if k in sw.VALID_MODULE_KEYS})
    await crm_service.update_deal(db, deal, module_keys=keys, product_interest_source="manual")
    await db.commit()
    return await get_club(deal_id, actor, db)


# ─── Calls ────────────────────────────────────────────────────────────────────

class CallLogBody(BaseModel):
    directory_contact_id: Optional[str] = None
    crm_person_id: Optional[str] = None
    outcome: str
    notes: Optional[str] = None
    next_follow_up_at: Optional[datetime] = None
    # Only meaningful when next_follow_up_at is also set on an event-worthy
    # outcome (see sw._EVENT_WORTHY_OUTCOMES / sw.log_call): who the resulting
    # follow-up Event should be owned by, instead of whoever logged the call.
    # Must be one of the staff GET /staff returns (validated below) — blank
    # means "me", i.e. whoever is logging the call.
    event_owner_user_id: Optional[str] = None


@router.get("/call-outcomes")
async def call_outcomes(_: SalesActor = Depends(require_sales_or_super)):
    return {"groups": sw.outcome_options()}


@router.get("/staff")
async def staff(_: SalesActor = Depends(require_sales_or_super), db: AsyncSession = Depends(get_db)):
    """Super-admin staff a follow-up event can be handed to, whenever a rep
    sets a follow-up date on an event-worthy call outcome — open to a 'sales'
    caller too, unlike /team (the sales-rep bulk-assign picker, super-admin
    only), since this is who a REP hands a follow-up off to, not who a
    manager assigns deals to.

    Reuses crm_service.list_platform_owners' fold (roles narrowed to just
    super_admin) rather than a bespoke query — a person holding two accounts
    under one name, or one account with more than one ClubMembership row,
    used to list twice (reported live: "Elton" and "Jack" each appearing
    twice in this exact picker); the fold is what collapses either shape
    back to one entry per person."""
    owners = await crm_service.list_platform_owners(db, roles=("super_admin",))
    return {"staff": [
        {"id": o["id"], "username": "", "display_name": o["name"]}
        for o in owners
    ]}


@router.get("/event-owners")
async def event_owners(_: SalesActor = Depends(require_sales_or_super), db: AsyncSession = Depends(get_db)):
    """Every super admin AND sales rep who can be responsible for a follow-up
    Event — the roster for the Events tab's "Responsible" filter, open to
    both roles (unlike /club-admin/super/crm/owners, the same underlying
    list but gated super-admin-only for the Sales Pipeline screen). Reuses
    crm_service.list_platform_owners rather than re-deriving the roster, so
    the two screens' filters can never disagree about who "everyone" is."""
    return {"owners": await crm_service.list_platform_owners(db)}


@router.post("/clubs/{deal_id}/calls")
async def log_call(
    deal_id: str,
    body: CallLogBody,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    deal = await _load_deal(db, deal_id)
    _assert_can_touch(actor, deal)
    if body.outcome not in sw.CALL_OUTCOMES:
        raise HTTPException(status_code=422, detail="Unknown call outcome")

    person = None
    if body.directory_contact_id or body.crm_person_id:
        try:
            person = await sw.resolve_or_materialize_person(
                db, marketing_club_id=deal.marketing_club_id,
                directory_contact_id=_uuid_or_none(body.directory_contact_id),
                crm_person_id=_uuid_or_none(body.crm_person_id),
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

    event_owner_id = await _validated_staff_id(db, body.event_owner_user_id)

    await sw.log_call(
        db, deal=deal, person=person, outcome=body.outcome, notes=body.notes,
        next_follow_up_at=body.next_follow_up_at, created_by_user_id=actor.user.id,
        event_owner_user_id=event_owner_id,
    )
    # Real sales work on the club, so the rep who did it earns it — EXCEPT a
    # General Note, which claims nothing about the club (see the commission
    # note in services/sales_workspace.py). Assignment is untouched either
    # way; this is only about who gets paid for it.
    if body.outcome not in sw.GENERAL_OUTCOMES:
        await sw.attribute_commission(
            db, deal=deal, actor_user_id=actor.user.id, actor_role=actor.role,
            via=sw.COMMISSION_VIA_CALL,
        )
    await db.commit()
    return await get_club(deal_id, actor, db)


class NoteBody(BaseModel):
    body: str
    pinned: bool = False


@router.post("/clubs/{deal_id}/notes")
async def add_note(
    deal_id: str,
    body: NoteBody,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    deal = await _load_deal(db, deal_id)
    _assert_can_touch(actor, deal)
    if not (body.body or "").strip():
        raise HTTPException(status_code=422, detail="Note can't be empty")
    await sw.log_note(db, deal=deal, body=body.body.strip(), pinned=body.pinned, created_by_user_id=actor.user.id)
    await db.commit()
    return {"status": "ok"}


@router.patch("/clubs/{deal_id}/notes/{activity_id}")
async def edit_note(
    deal_id: str,
    activity_id: str,
    body: NoteBody,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    deal = await _load_deal(db, deal_id)
    _assert_can_touch(actor, deal)
    if not (body.body or "").strip():
        raise HTTPException(status_code=422, detail="Note can't be empty")
    aid = _uuid_or_none(activity_id)
    activity = await db.get(CrmActivity, aid) if aid else None
    # A note belongs to exactly one deal and is never anything else's edit
    # target — same deal-scoping every other per-activity write in this
    # router relies on, so an id from another club's timeline (or a call/
    # email/system entry, which this form has no business rewriting) 404s
    # rather than silently editing the wrong record.
    if activity is None or activity.deal_id != deal.id or activity.type != "note":
        raise HTTPException(status_code=404, detail="Note not found")
    await sw.edit_note(db, activity=activity, body=body.body.strip(), pinned=body.pinned)
    await db.commit()
    return {"status": "ok"}


# ─── Email actions ─────────────────────────────────────────────────────────────

@router.get("/email-templates")
async def email_templates(actor: SalesActor = Depends(require_sales_or_super), db: AsyncSession = Depends(get_db)):
    from app.services import platform_settings as ps
    from app.services import sales_email as se
    # Self-heals the outreach org's editable copies of the three built-in
    # templates (cheap no-op once seeded) — same "call it on the read path"
    # pattern as comms.py's own seed_starter_templates.
    await se.seed_sales_templates(db)
    await db.commit()
    links = await ps.get_demo_booking_links(db)
    rep_name = actor.user.display_name or actor.user.username
    return {
        # `built_in` rides along so the screen doesn't have to keep its own
        # copy of the list — a hand-kept mirror is how a newly-added template
        # ends up in the dropdown but silently loading no preview.
        "templates": [{"key": k, "label": v, "built_in": k in se.BUILT_IN_TEMPLATES}
                      for k, v in se.TEMPLATE_LABELS.items()],
        "demo_link_configured": bool(links.get(rep_name)),
    }


class EmailBody(BaseModel):
    directory_contact_id: Optional[str] = None
    crm_person_id: Optional[str] = None
    template: str  # 'information' | 'trial_information' | 'demo' | 'custom'
    # These carry the rep's EDITED copy of what /email-preview handed back
    # (already-final HTML, sent as-is) for every one of the four built-in
    # templates, 'custom' included — all four open pre-filled from their own
    # editable template now. Omitted, the server re-renders the template
    # fresh from scratch (a caller that skipped the preview step).
    subject: Optional[str] = None
    body: Optional[str] = None


def _resolve_utm_code(club: Optional[MarketingClub]) -> Optional[str]:
    """Auto-generate + persist a club's utm_code the same way club_directory.py
    does for a crawled club, so a link sent before the club had one still gets
    tracked attribution from here on — both to the club (utm_id) and, via
    apply_sales_utm, to the sending rep (utm_content). Deterministic from the
    club's name (see _default_utm), so calling this from a preview that never
    commits is harmless — a later call recomputes the same value."""
    if club is None:
        return None
    if not club.utm_code:
        from app.services.club_directory import _default_utm
        club.utm_code = _default_utm(club.name)
    return club.utm_code or None


class EmailPreviewBody(BaseModel):
    directory_contact_id: Optional[str] = None
    crm_person_id: Optional[str] = None
    template: str


@router.post("/clubs/{deal_id}/email-preview")
async def email_preview(
    deal_id: str,
    body: EmailPreviewBody,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    """Renders a built-in template's real, merged content (contact's name,
    club name, the picked calendly link) for the Send Email form's Design
    editor — the rep edits this before Send actually fires. Never sends
    anything."""
    from app.services import platform_settings as ps
    from app.services import sales_email as se

    deal = await _load_deal(db, deal_id)
    _assert_can_touch(actor, deal)
    if body.template not in se.BUILT_IN_TEMPLATES:
        raise HTTPException(status_code=422, detail="No preview for this template")

    person = None
    if body.directory_contact_id or body.crm_person_id:
        try:
            person = await sw.resolve_or_materialize_person(
                db, marketing_club_id=deal.marketing_club_id,
                directory_contact_id=_uuid_or_none(body.directory_contact_id),
                crm_person_id=_uuid_or_none(body.crm_person_id),
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
    await db.commit()

    club = await db.get(MarketingClub, deal.marketing_club_id) if deal.marketing_club_id else None
    club_name = club.name if club else deal.title
    rep_name = actor.user.display_name or actor.user.username
    calendly_url = None
    if body.template == "demo":
        links = await ps.get_demo_booking_links(db)
        calendly_url = links.get(rep_name)
    utm_code = _resolve_utm_code(club)
    subject, html_body = await se.render_template_preview(
        db, body.template, contact_name=person.full_name if person else None,
        club_name=club_name, rep_name=rep_name, calendly_url=calendly_url,
        utm_code=utm_code or "",
    )
    return {"subject": subject, "body": html_body}


@router.post("/clubs/{deal_id}/email")
async def send_email(
    deal_id: str,
    body: EmailBody,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    from app.services import platform_settings as ps
    from app.services import sales_email as se

    deal = await _load_deal(db, deal_id)
    _assert_can_touch(actor, deal)

    if not (body.directory_contact_id or body.crm_person_id):
        raise HTTPException(status_code=422, detail="Pick a contact to email")
    try:
        person = await sw.resolve_or_materialize_person(
            db, marketing_club_id=deal.marketing_club_id,
            directory_contact_id=_uuid_or_none(body.directory_contact_id),
            crm_person_id=_uuid_or_none(body.crm_person_id),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    to_email = (person.email or "").strip()
    if not to_email:
        raise HTTPException(status_code=422, detail="This contact has no email address on file")

    # Refuse an opted-out / do-not-contact contact — the same rule the
    # drawer's badge/toggle enforces, re-checked server-side so a stale
    # client can't route around it.
    if person.directory_contact_id:
        contact_row = await db.get(MarketingClubContact, person.directory_contact_id)
        if contact_row is not None:
            if contact_row.do_not_contact:
                raise HTTPException(status_code=422, detail="This contact has asked not to be contacted")
            if not contact_row.subscribed or contact_row.unsubscribed_at or contact_row.bounced:
                raise HTTPException(status_code=422, detail="This contact has opted out of email")

    club = await db.get(MarketingClub, deal.marketing_club_id) if deal.marketing_club_id else None
    club_name = club.name if club else deal.title
    rep_name = actor.user.display_name or actor.user.username
    template = body.template

    utm_code = _resolve_utm_code(club)

    if template in se.BUILT_IN_TEMPLATES:
        # The rep's own edited copy of what /email-preview handed back (the
        # normal path — the Design editor always sends its current content)
        # is trusted as final HTML, no re-wrapping/escaping: it's the same
        # merged template content the rep was just shown, only possibly
        # edited by them in the editor. Absent, fall back to a fresh
        # server-side render (a caller that skipped the preview step).
        if (body.subject or "").strip() and (body.body or "").strip():
            from app.routers.comms import _html_to_text
            subject, html_body = body.subject.strip(), body.body
            text_body = _html_to_text(html_body)
        else:
            calendly_url = None
            if template == "demo":
                links = await ps.get_demo_booking_links(db)
                calendly_url = links.get(rep_name)
            subject, html_body, text_body = await se.render_template(
                db, template, contact_name=person.full_name, club_name=club_name, rep_name=rep_name,
                calendly_url=calendly_url, utm_code=utm_code or "",
            )
    else:
        raise HTTPException(status_code=422, detail="Unknown email template")

    html_body = se.apply_sales_utm(html_body, template_key=template, rep_username=actor.user.username, utm_code=utm_code)

    try:
        await se.send_sales_email(
            to_email=to_email, to_name=person.full_name, subject=subject, html=html_body, text=text_body,
            rep_name=rep_name, rep_email=actor.user.email,
        )
    except Exception as e:  # noqa: BLE001 - surfaced to the rep, this is an explicit action, not best-effort
        raise HTTPException(status_code=502, detail=f"Could not send email: {e}")

    await crm_service.log_activity(
        db, deal_id=deal.id, person_id=person.id, type="email",
        body=f"{se.TEMPLATE_LABELS.get(template, template)} sent to {to_email}",
        created_by_user_id=actor.user.id,
        meta={
            "template": template, "subject": subject, "html": html_body, "text": text_body,
            "to_email": to_email, "to_name": person.full_name,
        },
    )
    # The other qualifying action: the rep put something in front of one of
    # the club's contacts, so they earn the club. Stamped after the send
    # actually succeeded — a failed send raises above and attributes nothing.
    await sw.attribute_commission(
        db, deal=deal, actor_user_id=actor.user.id, actor_role=actor.role,
        via=sw.COMMISSION_VIA_EMAIL,
    )
    await db.commit()
    return {"status": "sent"}


class ContactBody(BaseModel):
    full_name: str
    role: Optional[str] = None
    email: Optional[str] = None
    mobile: Optional[str] = None


@router.post("/clubs/{deal_id}/contacts")
async def add_contact(
    deal_id: str,
    body: ContactBody,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    deal = await _load_deal(db, deal_id)
    _assert_can_touch(actor, deal)
    if not deal.marketing_club_id:
        raise HTTPException(status_code=422, detail="This club has no Club Directory record to attach a contact to")
    if not (body.full_name or "").strip():
        raise HTTPException(status_code=422, detail="A name is required")
    if not ((body.email or "").strip() or (body.mobile or "").strip()):
        raise HTTPException(status_code=422, detail="An email or mobile number is required")
    contact = await sw.add_directory_contact(
        db, marketing_club_id=deal.marketing_club_id, full_name=body.full_name.strip(),
        role=body.role, email=body.email, mobile=body.mobile,
    )
    await db.commit()
    # Return the new contact in the same shape merged_contacts() uses, so the
    # caller can push it straight into the Log Call / Send Email pickers
    # without a full drawer reload.
    if contact is None:
        return {"status": "ok", "contact": None}
    return {"status": "ok", "contact": {
        "origin": "directory",
        "directory_contact_id": str(contact.id),
        "crm_person_id": None,
        "full_name": contact.full_name,
        "role": contact.role,
        "role_rank": contact.role_rank,
        "email": contact.email,
        "mobile": contact.mobile,
        "subscribed": contact.subscribed,
        "do_not_email": bool(contact.unsubscribed_at) or bool(contact.bounced) or not contact.subscribed,
        "do_not_contact": bool(contact.do_not_contact),
        "do_not_contact_reason": contact.do_not_contact_reason,
    }}


class DoNotContactBody(BaseModel):
    do_not_contact: bool
    reason: Optional[str] = None


@router.patch("/clubs/{deal_id}/contacts/{contact_id}/do-not-contact")
async def set_contact_do_not_contact(
    deal_id: str,
    contact_id: str,
    body: DoNotContactBody,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    """Scoped through the deal (not a bare contact id) so the same ownership
    check every other write here uses applies — a sales rep can only flag a
    contact belonging to a club that's actually theirs."""
    deal = await _load_deal(db, deal_id)
    _assert_can_touch(actor, deal)
    cid = _uuid_or_none(contact_id)
    contact = await db.get(MarketingClubContact, cid) if cid else None
    if contact is None or contact.marketing_club_id != deal.marketing_club_id:
        raise HTTPException(status_code=404, detail="Contact not found")
    await sw.set_contact_do_not_contact(db, contact, body.do_not_contact, body.reason)
    await db.commit()
    return {"status": "ok"}


# ─── Follow-ups queue ──────────────────────────────────────────────────────────

@router.get("/follow-ups")
async def follow_ups(
    owner_user_id: Optional[str] = None,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    effective_owner = actor.user.id if actor.role == "sales" else (_uuid_or_none(owner_user_id) if owner_user_id else None)
    rows = await sw.list_follow_ups(db, owner_user_id=effective_owner)

    deal_ids = {a.deal_id for a in rows if a.deal_id}
    deals = {}
    if deal_ids:
        deal_rows = (await db.execute(select(CrmDeal).where(CrmDeal.id.in_(deal_ids)))).scalars().all()
        deals = {d.id: d for d in deal_rows}
    club_by_id = await crm_service.clubs_by_ids(db, (d.marketing_club_id for d in deals.values()))
    person_ids = {a.person_id for a in rows if a.person_id}
    people = {}
    if person_ids:
        person_rows = (await db.execute(select(CrmPerson).where(CrmPerson.id.in_(person_ids)))).scalars().all()
        people = {p.id: p for p in person_rows}
    owner_ids = {d.owner_user_id for d in deals.values() if d.owner_user_id}
    owners = {}
    if owner_ids:
        owner_rows = (await db.execute(select(User).where(User.id.in_(owner_ids)))).scalars().all()
        owners = {u.id: u for u in owner_rows}

    out = []
    for a in rows:
        deal = deals.get(a.deal_id)
        club = club_by_id.get(deal.marketing_club_id) if deal else None
        person = people.get(a.person_id) if a.person_id else None
        owner = owners.get(deal.owner_user_id) if deal and deal.owner_user_id else None
        due_at = a.next_follow_up_at
        bucket = "upcoming"
        if due_at is not None:
            due_naive = due_at.replace(tzinfo=None) if due_at.tzinfo else due_at
            today = datetime.utcnow().date()
            if due_naive.date() < today:
                bucket = "overdue"
            elif due_naive.date() == today:
                bucket = "today"
        out.append({
            "activity_id": str(a.id),
            "deal_id": str(a.deal_id) if a.deal_id else None,
            "club_name": club.name if club else (deal.title if deal else None),
            "contact_name": person.full_name if person else None,
            "owner_name": (owner.display_name or owner.username) if owner else None,
            "outcome": a.outcome,
            "notes": a.body,
            "due_at": due_at.isoformat() if due_at else None,
            "bucket": bucket,
        })
    return {"follow_ups": out}


@router.post("/follow-ups/{activity_id}/done")
async def complete_follow_up(
    activity_id: str,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    aid = _uuid_or_none(activity_id)
    activity = await db.get(CrmActivity, aid) if aid else None
    if activity is None:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    deal = await _load_deal(db, str(activity.deal_id)) if activity.deal_id else None
    if deal is None:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    _assert_can_touch(actor, deal)
    await sw.mark_follow_up_done(db, activity)
    await db.commit()
    return {"status": "ok"}


# ─── Assignment (super admin only) ────────────────────────────────────────────

class AssignBody(BaseModel):
    owner_user_id: Optional[str] = None  # None/omitted = unassign
    # Set once the super admin has answered the "this club has been
    # attributed to X" prompt. Absent/false on an attributed club is a 409,
    # never a silent move — the browser dialog is the prompt, but the rule
    # lives here so no client can route around it.
    confirm_reassign: bool = False


@router.patch("/clubs/{deal_id}/assign")
async def assign(
    deal_id: str,
    body: AssignBody,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    _require_super(actor)
    deal = await _load_deal(db, deal_id)
    owner_id = _uuid_or_none(body.owner_user_id)
    owner_name = None
    if owner_id:
        owner = await db.get(User, owner_id)
        if owner is None:
            raise HTTPException(status_code=404, detail="User not found")
        owner_name = owner.display_name or owner.username
    if not body.confirm_reassign and sw.commission_reassign_blocked(deal, owner_id):
        rep_name = (await sw.commission_rep_names(db, [deal])).get(deal.commission_rep_user_id)
        raise HTTPException(status_code=409, detail={
            "code": "commission_attributed",
            "message": sw.commission_confirm_message(rep_name),
            "commission_rep_user_id": str(deal.commission_rep_user_id),
            "commission_rep_name": rep_name,
        })
    await crm_service.update_deal(db, deal, owner_user_id=owner_id)
    await sw.log_reassignment(db, deal=deal, owner_name=owner_name, created_by_user_id=actor.user.id)
    await db.commit()
    # commit() expires every attribute on `deal` — refresh before reading any
    # of them again (same MissingGreenlet trap this codebase documents
    # elsewhere: serialising an ORM object right after commit() lazy-loads
    # outside the greenlet).
    await db.refresh(deal)
    pipeline = await crm_service.get_deal_pipeline(db, deal)
    stage = next((s for s in pipeline.stages if s.id == deal.stage_id), None) if pipeline else None
    club = await db.get(MarketingClub, deal.marketing_club_id) if deal.marketing_club_id else None
    return crm_service._deal_dict(deal, stage, club)


class BulkAssignBody(BaseModel):
    deal_ids: list[str]
    owner_user_ids: list[str] = []  # one id = assign all to them; several = split evenly, round-robin
    # True = send every selected club back into the shared pool
    # (owner_user_id cleared to NULL) — owner_user_ids is ignored either way.
    unassign: bool = False
    confirm_reassign: bool = False  # see AssignBody — same prompt, several clubs at once


@router.post("/bulk-assign")
async def bulk_assign(
    body: BulkAssignBody,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    """Filter the queue down to a batch (never called, a state, a stage,
    unassigned…) then assign the whole selection in one action — "Assign
    selected -> Sam", "Split evenly among Sam / Jake / Sarah", or (unassign)
    "send them all back into the pool", per the brief. Super-admin only,
    same as the single-deal PATCH .../assign."""
    _require_super(actor)
    if not body.deal_ids:
        raise HTTPException(status_code=422, detail="Select at least one club")

    owner_ids: list = []
    owner_names: dict = {}
    if not body.unassign:
        owner_ids = [_uuid_or_none(o) for o in body.owner_user_ids if o]
        if not owner_ids:
            raise HTTPException(status_code=422, detail="Pick at least one salesperson, or choose Unassigned")

        owners = (await db.execute(select(User).where(User.id.in_(owner_ids)))).scalars().all()
        found_ids = {u.id for u in owners}
        missing = [str(o) for o in owner_ids if o not in found_ids]
        if missing:
            raise HTTPException(status_code=404, detail=f"Unknown salesperson id(s): {', '.join(missing)}")
        owner_names = {u.id: (u.display_name or u.username) for u in owners}

    deal_uuids = [_uuid_or_none(d) for d in body.deal_ids]
    deals = (await db.execute(
        select(CrmDeal).where(
            CrmDeal.id.in_(deal_uuids), CrmDeal.scope == crm_service.SCOPE_PLATFORM,
            CrmDeal.archived_at.is_(None),
        )
    )).scalars().all()
    if not deals:
        raise HTTPException(status_code=404, detail="None of the selected clubs could be found")

    # Same attribution guard as the single-deal PATCH, or bulk assignment
    # would be the way around it. Three shapes to judge: sending the
    # selection back to the pool always moves an earned club away from its
    # rep; a round-robin split across several reps can send it to any of
    # them, so it can never be relied on to land back where it was earned;
    # and a single-owner assignment is only fine when that owner IS the rep
    # who earned it.
    if not body.confirm_reassign:
        attributed = [
            d for d in deals
            if d.commission_rep_user_id is not None
            and (body.unassign or len(owner_ids) > 1
                 or sw.commission_reassign_blocked(d, owner_ids[0]))
        ]
        if attributed:
            names = await sw.commission_rep_names(db, attributed)
            raise HTTPException(status_code=409, detail={
                "code": "commission_attributed",
                "message": sw.commission_confirm_message(
                    names.get(attributed[0].commission_rep_user_id)) if len(attributed) == 1 else
                    f"{len(attributed)} of these clubs have been attributed to a sales rep - "
                    "do you really want to change their assignment?",
                "clubs": [
                    {"deal_id": str(d.id), "title": d.title,
                     "commission_rep_name": names.get(d.commission_rep_user_id)}
                    for d in attributed
                ],
            })

    counts = await sw.bulk_assign(
        db, deals=deals, owner_ids=owner_ids, owner_names=owner_names, created_by_user_id=actor.user.id,
    )
    await db.commit()
    by_rep = {
        ("Unassigned" if k == "unassigned" else owner_names.get(uuid.UUID(k), k)): v
        for k, v in counts.items()
    }
    return {
        "assigned": len(deals),
        "skipped": len(body.deal_ids) - len(deals),
        "by_rep": by_rep,
    }


# ─── Start a trial on the contact's behalf ────────────────────────────────────

class StartTrialBody(BaseModel):
    admin_first_name: str
    admin_last_name: str
    admin_display_name: str = ""
    admin_username: str
    admin_email: str
    admin_mobile_number: str = ""
    slug: Optional[str] = None
    short_name: Optional[str] = None
    contact_email: Optional[str] = None


@router.post("/clubs/{deal_id}/start-trial")
async def start_trial(
    deal_id: str,
    body: StartTrialBody,
    background_tasks: BackgroundTasks,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    """The salesperson's equivalent of Super Admin -> All Clubs -> New Club —
    reuses that exact flow (org creation, first sync, every-module trial,
    Primary Admin invite email, Twenty push) rather than a second
    implementation, called directly with this rep as the acting user. Scoped
    to a club already in the rep's own queue (can't spin up an arbitrary new
    org) and refuses if it's already registered or has no real CA id on file.

    The deal itself isn't moved to the 'trial' stage here — create_club's own
    background CRM sync (crm.sync_super_admin_trial_registration) finds and
    advances this SAME open deal via its marketing_club_id, which is what
    keeps 'trial' meaning "an actual registration happened", never something
    a call outcome alone can set."""
    deal = await _load_deal(db, deal_id)
    _assert_can_touch(actor, deal)
    if not deal.marketing_club_id:
        raise HTTPException(status_code=422, detail="This club isn't linked to a Club Directory prospect yet")
    club = await db.get(MarketingClub, deal.marketing_club_id)
    if club is None:
        raise HTTPException(status_code=404, detail="Club not found")
    if club.existing_org_id:
        raise HTTPException(status_code=409, detail="This club is already registered")
    if not club.grassroots_guid:
        raise HTTPException(
            status_code=422,
            detail="This club has no Cricket Australia id on file — start it from All Clubs instead",
        )

    from app.routers.self_serve_trial import _slugify, _unique_slug
    slug = (body.slug or "").strip().lower()
    if not slug:
        slug = await _unique_slug(db, _slugify(club.name))

    from app.routers.club_admin import ClubCreate, create_club as _create_club
    payload = ClubCreate(
        org_id=club.grassroots_guid, name=club.name, slug=slug,
        short_name=body.short_name or club.short_name,
        contact_email=body.contact_email or club.contact_email,
        admin_first_name=body.admin_first_name, admin_last_name=body.admin_last_name,
        admin_display_name=body.admin_display_name, admin_username=body.admin_username,
        admin_email=body.admin_email, admin_mobile_number=body.admin_mobile_number,
    )
    result = await _create_club(payload, background_tasks, current_user=actor.user, db=db)

    await crm_service.log_activity(
        db, deal_id=deal.id, type="system",
        body=f"Trial started for {result['name']} by {actor.user.display_name or actor.user.username}",
        created_by_user_id=actor.user.id,
    )
    await db.commit()
    return result


# ─── Extend a live club's trial ────────────────────────────────────────────────
# Unlike start_trial above (a brand-new club with no org yet), this is for a
# club that's ALREADY registered and already holds at least one module in
# trial status — a rep giving them more runway, not onboarding them.

EXTEND_TRIAL_MIN_DAYS = 1
EXTEND_TRIAL_MAX_DAYS = 14


def _username_base(email: str) -> str:
    """Mirrors self_serve_trial.py's _slugify, applied to an email's local
    part — the Extend Trial modal never asks a rep for a username (it only
    collects name/email/mobile), so one is derived here the same way a slug
    is derived from a club name elsewhere in this codebase."""
    import re
    local = (email or "").split("@", 1)[0]
    base = re.sub(r"[^a-z0-9]+", "", local.lower())
    return base[:24] or "admin"


async def _unique_username(db: AsyncSession, base: str) -> str:
    username = base
    n = 2
    while True:
        existing = await db.execute(select(User.id).where(User.username == username))
        if not existing.scalar_one_or_none():
            return username
        username = f"{base}{n}"
        n += 1


class ExtendTrialContact(BaseModel):
    full_name: str
    email: str
    mobile: Optional[str] = None


class ExtendTrialBody(BaseModel):
    days: int
    directory_contact_id: Optional[str] = None
    crm_person_id: Optional[str] = None
    new_contact: Optional[ExtendTrialContact] = None
    nominate_primary_admin: bool = False


async def _nominate_primary_admin(
    db: AsyncSession, *, org_id: uuid.UUID, club_name: str, full_name: str, email: str,
    background_tasks: BackgroundTasks,
) -> bool:
    """Makes ``email`` the club's Primary Admin — flips the flag onto their
    EXISTING membership on this same org if they already have an account
    (e.g. a co-admin who was never made primary), else invites them as a
    brand-new club_admin (password_hash NULL + invite_token, same "set your
    own password" flow routers/club_admin.py::create_club_user uses). Only
    ever called once the caller has confirmed the club has no primary admin
    yet. Raises HTTPException on a genuine conflict — an email already tied
    to an account outside this club, or to BetterCricket staff. Returns True
    if a fresh invite email was sent (vs an existing member just promoted)."""
    from app.services import memberships
    from app.services.admin_identity import EMAIL_TAKEN_MESSAGE

    email_norm = (email or "").strip().lower()
    if not email_norm:
        raise HTTPException(status_code=422, detail="An email address is required to nominate a Primary Admin")
    if await memberships.has_primary_admin(db, org_id):
        raise HTTPException(status_code=409, detail="This club already has a Primary Admin")

    existing_user = await db.scalar(select(User).where(func.lower(User.email) == email_norm))
    if existing_user is not None:
        membership = await db.scalar(
            select(ClubMembership).where(ClubMembership.user_id == existing_user.id)
        )
        if membership is None or str(membership.club_id) != str(org_id):
            raise HTTPException(status_code=409, detail=EMAIL_TAKEN_MESSAGE)
        if membership.role == "super_admin":
            raise HTTPException(
                status_code=409,
                detail="This email belongs to a BetterCricket staff account, not a club admin",
            )
        if membership.role != "club_admin":
            membership.role = "club_admin"
        await memberships.set_primary_admin(db, org_id, existing_user.id)
        return False

    from app.config.settings import settings as _settings
    from app.routers.club_admin import _INVITE_TOKEN_TTL_DAYS
    from app.services.user_invite import send_invite_email

    username = await _unique_username(db, _username_base(email_norm))
    new_user = User(
        id=uuid.uuid4(), username=username, display_name=full_name, email=email_norm,
        password_hash=None, invite_token=secrets.token_urlsafe(32),
        invite_token_expires_at=datetime.now(timezone.utc) + timedelta(days=_INVITE_TOKEN_TTL_DAYS),
    )
    db.add(new_user)
    await db.flush()
    db.add(ClubMembership(
        id=uuid.uuid4(), club_id=org_id, user_id=new_user.id, role="club_admin",
        is_primary_admin=True, capabilities=[],
    ))
    await db.flush()
    invite_link = f"{_settings.public_base_url}/login?invite={new_user.invite_token}"
    background_tasks.add_task(
        send_invite_email, email=email_norm, display_name=full_name, club_name=club_name, link=invite_link,
    )
    return True


@router.post("/clubs/{deal_id}/extend-trial")
async def extend_trial(
    deal_id: str,
    body: ExtendTrialBody,
    background_tasks: BackgroundTasks,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    """Extends every module currently on trial by ``days`` (1-14), "from
    now" per direct instruction — an already-expired trial also has its
    start date reset to now, a still-live one keeps its original start and
    just gets a later end. Sends the club's chosen contact the 'trial_
    extension' BetterAdmin -> Comms -> Templates email (best-effort: a
    delivery failure doesn't undo the extension, it's reported back so the
    rep knows to follow up another way)."""
    deal = await _load_deal(db, deal_id)
    _assert_can_touch(actor, deal)

    if not deal.marketing_club_id:
        raise HTTPException(status_code=422, detail="This club isn't linked to a Club Directory prospect yet")
    club = await db.get(MarketingClub, deal.marketing_club_id)
    if club is None:
        raise HTTPException(status_code=404, detail="Club not found")
    if not club.existing_org_id:
        raise HTTPException(status_code=422, detail="This club isn't registered on BetterCricket yet")

    from app.services import module_subscriptions
    from app.services import sales_email as se

    org = await db.get(
        Organisation, club.existing_org_id, options=[selectinload(Organisation.module_subscriptions)],
    )
    if org is None:
        raise HTTPException(status_code=404, detail="Club's account not found")

    trial_map = await crm_service.trial_days_remaining_by_club(db, {club.id: club})
    days_by_module = trial_map.get(club.id) or {}
    if not days_by_module:
        raise HTTPException(status_code=422, detail="This club has no active trial to extend")
    min_days_remaining = min(days_by_module.values())

    if not (EXTEND_TRIAL_MIN_DAYS <= body.days <= EXTEND_TRIAL_MAX_DAYS):
        raise HTTPException(
            status_code=422,
            detail=f"Choose between {EXTEND_TRIAL_MIN_DAYS} and {EXTEND_TRIAL_MAX_DAYS} days",
        )

    # Resolve who gets the confirmation email — an existing pick, or a new
    # contact written straight to the canonical Club Directory (same helper
    # the drawer's own "+ Add contact" uses), then bridged into a CrmPerson
    # the same way every other contact-touching action in this router does.
    directory_contact_id = _uuid_or_none(body.directory_contact_id)
    if body.new_contact is not None:
        full_name = (body.new_contact.full_name or "").strip()
        email = (body.new_contact.email or "").strip()
        if not full_name:
            raise HTTPException(status_code=422, detail="A name is required")
        if not email:
            raise HTTPException(status_code=422, detail="An email address is required")
        contact = await sw.add_directory_contact(
            db, marketing_club_id=deal.marketing_club_id, full_name=full_name,
            role=None, email=email, mobile=body.new_contact.mobile,
        )
        directory_contact_id = contact.id if contact else None

    if not directory_contact_id and not body.crm_person_id:
        raise HTTPException(status_code=422, detail="Pick a contact, or add a new one, to email")

    try:
        person = await sw.resolve_or_materialize_person(
            db, marketing_club_id=deal.marketing_club_id,
            directory_contact_id=directory_contact_id, crm_person_id=_uuid_or_none(body.crm_person_id),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    to_email = (person.email or "").strip()
    if not to_email:
        raise HTTPException(status_code=422, detail="This contact has no email address on file")

    # The extension itself, then the (optional) nomination — both real
    # account/entitlement writes, so both land before the best-effort email.
    # One `now` shared with extend_trial_for_org, so the reported
    # new_trial_end is byte-identical to what actually landed in the row
    # rather than two independent now() calls a few ms apart.
    now = datetime.now(timezone.utc)
    reset_start = min_days_remaining < 0
    module_subscriptions.extend_trial_for_org(org, days=body.days, reset_start=reset_start, now=now)
    new_trial_end = now + timedelta(days=body.days)

    nominated_invited = None
    if body.nominate_primary_admin:
        nominated_invited = await _nominate_primary_admin(
            db, org_id=club.existing_org_id, club_name=club.name, full_name=person.full_name,
            email=to_email, background_tasks=background_tasks,
        )

    await db.commit()

    rep_name = actor.user.display_name or actor.user.username
    utm_code = _resolve_utm_code(club)
    email_sent = False
    subject = html_body = text_body = None
    try:
        subject, html_body, text_body = await se.render_template(
            db, "trial_extension", contact_name=person.full_name, club_name=club.name,
            rep_name=rep_name, utm_code=utm_code or "",
        )
        html_body = se.apply_sales_utm(
            html_body, template_key="trial_extension", rep_username=actor.user.username, utm_code=utm_code,
        )
        await se.send_sales_email(
            to_email=to_email, to_name=person.full_name, subject=subject, html=html_body, text=text_body,
            rep_name=rep_name, rep_email=actor.user.email,
        )
        email_sent = True
    except Exception:  # noqa: BLE001 - best-effort: the extension already landed
        logger.exception("extend_trial: could not send confirmation email for deal %s", deal.id)

    note = f"Extended trial by {body.days} day(s) to {new_trial_end.date().isoformat()} for {to_email}"
    if nominated_invited is True:
        note += f" — invited {person.full_name} as Primary Admin"
    elif nominated_invited is False:
        note += f" — made {person.full_name} Primary Admin"
    # meta carries the rendered email (when it got that far — a render
    # failure leaves these None) alongside the trial facts, so the SAME
    # "click to view the email" affordance the drawer's other email sends
    # get can rely on meta.html being present, whatever the activity's own
    # `type` is — this row's type stays 'system' since the headline fact is
    # the trial extension, not the email.
    await crm_service.log_activity(
        db, deal_id=deal.id, person_id=person.id, type="system", body=note,
        created_by_user_id=actor.user.id,
        meta={
            "days": body.days, "new_trial_end": new_trial_end.isoformat(), "email_sent": email_sent,
            "subject": subject, "html": html_body, "text": text_body,
            "to_email": to_email, "to_name": person.full_name,
        },
    )
    await db.commit()

    return {
        "status": "ok",
        "days": body.days,
        "new_trial_end": new_trial_end.isoformat(),
        "email_sent": email_sent,
        "contact_email": to_email,
        "nominated_primary_admin": nominated_invited is not None,
        "primary_admin_invited": bool(nominated_invited),
    }


# ─── Sales Lists ──────────────────────────────────────────────────────────────
# A thin provenance/import layer over the same crm_deals rows — importing a
# list never creates a second record of a club's history, and assigning one
# reuses the existing POST /bulk-assign (filter the queue to ?list_id=..,
# select, assign) rather than a second assignment code path.

@router.get("/lists")
async def sales_lists(actor: SalesActor = Depends(require_sales_or_super), db: AsyncSession = Depends(get_db)):
    """Every Sales List, for the picker on the Sales Lists page and the
    queue's list filter. Open to both roles — a rep narrowing their own
    queue to one list is a read, not an admin action."""
    return {"lists": await sw.list_sales_lists(db)}


@router.get("/lists/{list_id}")
async def sales_list_detail(
    list_id: str, actor: SalesActor = Depends(require_sales_or_super), db: AsyncSession = Depends(get_db),
):
    lid = _uuid_or_none(list_id)
    result = await sw.get_sales_list(db, lid) if lid else None
    if result is None:
        raise HTTPException(status_code=404, detail="List not found")
    return result


class ImportWizardClubsBody(BaseModel):
    name: str
    description: str = ""
    days: int = 90
    club_keys: list[str]


@router.post("/lists/from-wizard-clubs")
async def import_from_wizard_clubs(
    body: ImportWizardClubsBody,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    """Bulk-import a Wizard Clubs selection into a new Sales List — matches
    each one to its Club Directory row and ensures it has an open platform
    deal, so it shows up in the queue immediately. Super-admin only, same
    posture as bulk-assign (this is sales-ops list-building, not a rep's
    daily calling work)."""
    _require_super(actor)
    days = max(1, min(body.days, 730))
    result = await sw.create_list_from_wizard_clubs(
        db, name=body.name, description=body.description, days=days,
        club_keys=body.club_keys, created_by_user_id=actor.user.id,
    )
    if result.get("error"):
        raise HTTPException(status_code=422, detail=result.get("detail") or result["error"])
    await db.commit()
    return result


class ImportCrmDealsBody(BaseModel):
    name: str
    description: str = ""
    deal_ids: list[str]


@router.post("/lists/from-crm-deals")
async def import_from_crm_deals(
    body: ImportCrmDealsBody,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    """Import a set of Sales Pipeline deals (the CRM's own filtered board or
    list view) into a Sales List — the CRM-export source, alongside Wizard
    Clubs. Super-admin only, same posture as the other list-building
    actions. No matching needed: these are already real deals, so this is
    a pure grouping, never a write to the pipeline itself."""
    _require_super(actor)
    if not body.deal_ids:
        raise HTTPException(status_code=422, detail="Select at least one deal")
    deal_uuids = [_uuid_or_none(d) for d in body.deal_ids]
    deals = (await db.execute(
        select(CrmDeal).where(
            CrmDeal.id.in_(deal_uuids), CrmDeal.scope == crm_service.SCOPE_PLATFORM,
            CrmDeal.archived_at.is_(None),
        )
    )).scalars().all()
    if not deals:
        raise HTTPException(status_code=404, detail="None of the selected deals could be found")

    result = await sw.create_list_from_crm_deals(
        db, name=body.name, description=body.description, deals=deals, created_by_user_id=actor.user.id,
    )
    if result.get("error"):
        raise HTTPException(status_code=422, detail=result.get("detail") or result["error"])
    await db.commit()
    return result


# ─── Events ─────────────────────────────────────────────────────────────────
# Reuses crm_service's event functions (the SAME crm_events rows the Sales
# Pipeline's own Events tab reads/writes) with a narrower, rep-appropriate
# surface: a manual event can only be linked to a club already in the actor's
# own queue (never an arbitrary Club Directory search — that's the Pipeline's
# job), and a 'sales' caller only ever sees events they own or created.

def _assert_can_touch_event(actor: SalesActor, event: CrmEvent) -> None:
    if actor.role == "sales" and (
        (event.owner_user_id is None or str(event.owner_user_id) != str(actor.user.id))
        and (event.created_by_user_id is None or str(event.created_by_user_id) != str(actor.user.id))
    ):
        raise HTTPException(status_code=403, detail="This event isn't yours")


@router.get("/events")
async def list_events(actor: SalesActor = Depends(require_sales_or_super), db: AsyncSession = Depends(get_db)):
    """Every platform event, resolved with display names — same shape and
    same "fetch everything, filter client-side" posture as the Sales
    Pipeline's own Events tab (crm.py::super_list_events / CrmEventsView.jsx
    — the event set is small enough that per-keystroke filtering isn't worth
    a round trip). A 'sales' caller is narrowed server-side to events they
    own or created; a super admin sees the whole platform calendar."""
    events = await crm_service.list_events(db)
    if actor.role == "sales":
        mine = str(actor.user.id)
        events = [e for e in events if e.get("owner_user_id") == mine or e.get("created_by_user_id") == mine]
    return {"events": events}


@router.get("/clubs/{deal_id}/contacts")
async def club_contacts(
    deal_id: str, actor: SalesActor = Depends(require_sales_or_super), db: AsyncSession = Depends(get_db),
):
    """The contact picker for the New Event form — same merged Club
    Directory + CRM contact list the drawer's Contacts section already
    shows, fetched standalone so the Events tab doesn't need a full drawer
    load just to populate a dropdown."""
    deal = await _load_deal(db, deal_id)
    _assert_can_touch(actor, deal)
    return {"contacts": await sw.merged_contacts(db, deal.marketing_club_id)}


class SalesEventCreate(BaseModel):
    event_type: str = "meeting"          # call | demo | meeting | review_deal | follow_up | other
    starts_at: datetime
    title: Optional[str] = None
    location: Optional[str] = None
    body: Optional[str] = None
    owner_user_id: Optional[str] = None  # blank = the creator themselves
    directory_contact_id: Optional[str] = None
    crm_person_id: Optional[str] = None
    deal_id: Optional[str] = None        # one of the actor's OWN clubs
    first_alert: Optional[str] = None
    second_alert: Optional[str] = None


class SalesEventUpdate(BaseModel):
    event_type: Optional[str] = None
    starts_at: Optional[datetime] = None
    title: Optional[str] = None
    location: Optional[str] = None
    body: Optional[str] = None
    owner_user_id: Optional[str] = None
    directory_contact_id: Optional[str] = None
    crm_person_id: Optional[str] = None
    first_alert: Optional[str] = None
    second_alert: Optional[str] = None


@router.post("/events")
async def create_event(
    body: SalesEventCreate,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    deal = None
    if body.deal_id:
        deal = await _load_deal(db, body.deal_id)
        _assert_can_touch(actor, deal)

    owner_id = await _validated_staff_id(db, body.owner_user_id) or actor.user.id

    contact_id = None
    if body.directory_contact_id or body.crm_person_id:
        if deal is None or deal.marketing_club_id is None:
            raise HTTPException(status_code=422, detail="Pick a club before adding a contact")
        try:
            person = await sw.resolve_or_materialize_person(
                db, marketing_club_id=deal.marketing_club_id,
                directory_contact_id=_uuid_or_none(body.directory_contact_id),
                crm_person_id=_uuid_or_none(body.crm_person_id),
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        contact_id = person.id

    event = await crm_service.create_event(
        db, deal_id=deal.id if deal else None,
        marketing_club_id=deal.marketing_club_id if deal else None,
        contact_person_id=contact_id, owner_user_id=owner_id,
        event_type=body.event_type, title=body.title, location=body.location,
        body=body.body, starts_at=body.starts_at,
        first_alert=body.first_alert, second_alert=body.second_alert,
        created_by_user_id=actor.user.id,
    )
    await db.commit()
    await db.refresh(event)
    return await crm_service.serialize_event(db, event)


@router.patch("/events/{event_id}")
async def update_event(
    event_id: str,
    body: SalesEventUpdate,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    event = await crm_service.get_event(db, _uuid_or_none(event_id))
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    _assert_can_touch_event(actor, event)

    src = body.model_dump(exclude_unset=True)
    fields = {f: src[f] for f in
              ("event_type", "title", "location", "body", "starts_at", "first_alert", "second_alert") if f in src}
    if "owner_user_id" in src:
        fields["owner_user_id"] = await _validated_staff_id(db, src["owner_user_id"])
    if "directory_contact_id" in src or "crm_person_id" in src:
        # The event's club is fixed at creation (see create_event above) —
        # only WHICH contact at that same club is editable afterward.
        if event.marketing_club_id is None:
            raise HTTPException(status_code=422, detail="This event has no linked club to pick a contact from")
        directory_contact_id, crm_person_id = src.get("directory_contact_id"), src.get("crm_person_id")
        if not (directory_contact_id or crm_person_id):
            fields["contact_person_id"] = None
        else:
            try:
                person = await sw.resolve_or_materialize_person(
                    db, marketing_club_id=event.marketing_club_id,
                    directory_contact_id=_uuid_or_none(directory_contact_id),
                    crm_person_id=_uuid_or_none(crm_person_id),
                )
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e))
            fields["contact_person_id"] = person.id

    await crm_service.update_event(db, event, **fields)
    await db.commit()
    await db.refresh(event)
    return await crm_service.serialize_event(db, event)


@router.delete("/events/{event_id}")
async def delete_event(
    event_id: str, actor: SalesActor = Depends(require_sales_or_super), db: AsyncSession = Depends(get_db),
):
    event = await crm_service.get_event(db, _uuid_or_none(event_id))
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    _assert_can_touch_event(actor, event)
    await crm_service.delete_event(db, event)
    await db.commit()
    return {"deleted": True}
