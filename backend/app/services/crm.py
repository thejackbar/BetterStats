"""BetterCRM — People/Contacts + the internal & club-facing Deal pipeline.

One engine, two scopes:
  - **platform**: BetterCricket's own sales pipeline (organisation_id NULL,
    deals usually linked to a ``marketing_clubs`` prospect row) — the
    replacement for Twenty's Opportunity board. Exactly one pipeline always
    exists (``ensure_platform_pipeline``), auto-seeded on first touch.
  - **club**: the BetterAdmin CRM module (organisation_id set) — a club adds
    zero or more opt-in "trackers" (pipelines) from a small preset catalogue
    (Sponsors / Grants / Alumni & Fundraising) or builds a fully custom one.
    Nothing is auto-seeded here: formal sponsorship pursuit, grant
    applications and alumni fundraising are not universal to every club, so
    unlike the platform pipeline a club starts with NO trackers until it adds
    one (see PIPELINE_TEMPLATES / tracker_catalogue / add_tracker below).

A Deal always belongs to exactly one Pipeline, which is stage-ordered
(``CrmStage.position``); a stage's ``key`` is a stable slug the auto-creation
hooks below look up by, independent of whatever display ``name`` a super
admin / club admin has renamed it to. Weighted pipeline value
(``value_cents`` x effective probability) is computed on read, never stored,
so editing a stage's default probability or a deal's own override is
immediately reflected everywhere.

``CrmPerson`` is a generic contact — one row per real person, tagged with
roles via ``CrmPersonRole`` rather than a table per role (player / parent /
coach / committee / volunteer / sponsor contact / …). It's deliberately
additive: ``player_id`` is a nullable bridge to the existing per-club Player
identity for a future unified profile, but the Player table's own
uuid5-on-collision scheme is untouched by this module.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, update as sa_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.db import (
    CrmPerson, CrmPersonRole, CrmPipeline, CrmStage, CrmDeal, CrmDealContact, CrmActivity,
    MarketingClub, MarketingClubContact, User, ClubMembership, Organisation, ClubOnboardingRequest,
    OrgModuleSubscription,
)
from app.services.billing_pricing import price_for

logger = logging.getLogger(__name__)

SCOPE_PLATFORM = "platform"
SCOPE_CLUB = "club"
ALL_SCOPES = (SCOPE_PLATFORM, SCOPE_CLUB)

PERSON_ROLES = (
    "player", "parent", "coach", "committee", "volunteer", "sponsor_contact",
    "donor", "association_official", "school_contact", "council_contact",
    "supplier", "media", "other",
)

ACTIVITY_TYPES = ("call", "email", "meeting", "note", "system")
DEAL_STATUSES = ("open", "won", "lost")

# (key, name, default_probability, is_won, is_lost) — mirrors Twenty's own
# Opportunity pipeline exactly (bootstrap_twenty.PIPELINE), so a deal's stage
# means the same thing whichever system is looked at during/after cutover.
# "manually_added" is BetterCricket's own addition (not in Twenty) — the
# landing stage for a club pushed straight from the Club Directory rather
# than arriving via an enquiry/trial/webhook signal.
PLATFORM_DEFAULT_STAGES = [
    ("manually_added", "Manually Added", 5, False, False),
    ("target", "Target", 10, False, False),
    ("contacted", "Contacted", 20, False, False),
    ("engaged", "Engaged", 35, False, False),
    ("trial", "Trial", 50, False, False),
    ("self_serve_trial", "Self-Serve Trial", 50, False, False),
    ("proposal", "Proposal", 70, False, False),
    ("won", "Won", 100, True, False),
    ("lost_dormant", "Lost / Dormant", 0, False, True),
]

# Renames from the ORIGINAL platform stage set (pre-Twenty-parity) onto the
# one above — applied in place by _reconcile_platform_stages so a pipeline
# created before this list changed doesn't fork from it forever.
_PLATFORM_STAGE_RENAMES = {
    "new_lead": "target",
    "qualified": "engaged",
    "lost": "lost_dormant",
}
# Twenty has no equivalent of the old "negotiation" stage — any deal sitting
# there folds into "proposal" (the stage immediately before Won).
_PLATFORM_STAGE_MERGES = {
    "negotiation": "proposal",
}

# ─── Club-scope tracker catalogue ────────────────────────────────────────────
# Per direct instruction: a club shouldn't be presumed to run formal
# sponsorship, grants or alumni-fundraising activity — these are opt-in
# "trackers" a club adds (or never adds) from this small catalogue, same
# posture as a template email a club may or may not use. Each template
# carries its own stage names AND its own vocabulary (`terms`, consumed by
# the frontend's shared Kanban/detail components) so "Won"/"Lost"/"deal"
# never leaks through as generic sales language.
PIPELINE_TEMPLATES = {
    "sponsors": {
        "label": "Sponsors",
        "blurb": "Sponsorship prospects through to a signed agreement and renewal.",
        "stages": [
            ("prospect", "Prospect", 10, False, False),
            ("contacted", "Contacted", 25, False, False),
            ("proposal_sent", "Proposal Sent", 50, False, False),
            ("signed", "Signed", 100, True, False),
            ("renewal_due", "Renewal Due", 60, False, False),
            ("not_proceeding", "Not Proceeding", 0, False, True),
        ],
        "terms": {"won": "Signed", "lost": "Not Proceeding",
                  "itemSingular": "sponsor", "itemPlural": "sponsors", "titleLabel": "Sponsor name"},
    },
    "grants": {
        "label": "Grants",
        "blurb": "Grant opportunities from research through to the outcome.",
        "stages": [
            ("researching", "Researching", 10, False, False),
            ("drafting", "Drafting", 30, False, False),
            ("submitted", "Submitted", 50, False, False),
            ("awarded", "Awarded", 100, True, False),
            ("declined", "Declined", 0, False, True),
        ],
        "terms": {"won": "Awarded", "lost": "Declined",
                  "itemSingular": "grant", "itemPlural": "grants", "titleLabel": "Grant name"},
    },
    "alumni": {
        "label": "Alumni & Fundraising",
        "blurb": "Former players, life members and fundraising asks.",
        "stages": [
            ("identified", "Identified", 10, False, False),
            ("contacted", "Contacted", 25, False, False),
            ("asked", "Asked", 50, False, False),
            ("given", "Given", 100, True, False),
            ("declined", "Declined", 0, False, True),
        ],
        "terms": {"won": "Given", "lost": "Declined",
                  "itemSingular": "supporter", "itemPlural": "supporters", "titleLabel": "Supporter name"},
    },
}

# Seeded for a fully custom, club-authored tracker — deliberately generic
# (renamed/added/removed freely via the stage CRUD functions below).
CUSTOM_DEFAULT_STAGES = [
    ("prospect", "Prospect", 10, False, False),
    ("contacted", "Contacted", 25, False, False),
    ("proposal", "Proposal", 50, False, False),
    ("won", "Won", 100, True, False),
    ("lost", "Lost", 0, False, True),
]
CUSTOM_TERMS = {"won": "Won", "lost": "Lost", "itemSingular": "record", "itemPlural": "records", "titleLabel": "Title"}


# ─── Pipelines / stages ──────────────────────────────────────────────────────

async def _reconcile_platform_stages(session: AsyncSession, pipeline: CrmPipeline) -> bool:
    """Bring an already-existing platform pipeline's stages in line with the
    current PLATFORM_DEFAULT_STAGES — renames/merges the old set onto the new
    one (see _PLATFORM_STAGE_RENAMES/_PLATFORM_STAGE_MERGES), creates any
    still-missing stage (e.g. a brand new "self_serve_trial"), and fixes
    ordering. No deal is ever dropped: a merge/rename moves deals off the old
    stage's id before it's deleted. Returns True if anything changed, so the
    caller knows whether a commit + refresh is needed — a no-op once already
    reconciled. MUST run before any CrmDeal is loaded into this session (the
    bulk stage_id reassignment below bypasses the ORM identity map)."""
    by_key = {s.key: s for s in pipeline.stages}
    removed = set(pipeline.removed_stage_keys or [])
    changed = False

    for old_key, new_key in _PLATFORM_STAGE_RENAMES.items():
        old_stage = by_key.pop(old_key, None)
        if old_stage is None:
            continue
        existing_new = by_key.get(new_key)
        if existing_new is not None:
            # Both keys exist (shouldn't normally happen) — move any deals off
            # the old stage before dropping it (CrmDeal.stage_id is ON DELETE
            # RESTRICT).
            await session.execute(
                sa_update(CrmDeal).where(CrmDeal.stage_id == old_stage.id)
                .values(stage_id=existing_new.id))
            await session.delete(old_stage)
        else:
            new_name = next(n for k, n, *_r in PLATFORM_DEFAULT_STAGES if k == new_key)
            old_stage.key = new_key
            old_stage.name = new_name
            by_key[new_key] = old_stage
        changed = True

    for old_key, new_key in _PLATFORM_STAGE_MERGES.items():
        old_stage = by_key.pop(old_key, None)
        if old_stage is None:
            continue
        target = by_key.get(new_key)
        if target is not None:
            await session.execute(
                sa_update(CrmDeal).where(CrmDeal.stage_id == old_stage.id)
                .values(stage_id=target.id))
        await session.delete(old_stage)
        changed = True

    for position, (key, name, prob, is_won, is_lost) in enumerate(PLATFORM_DEFAULT_STAGES):
        if key in removed:
            # A super admin deliberately deleted this default stage — never
            # auto-recreate it just because it's now "missing" from the set.
            continue
        stage = by_key.get(key)
        if stage is None:
            stage = CrmStage(pipeline_id=pipeline.id, key=key, name=name, position=position,
                             default_probability=prob, is_won=is_won, is_lost=is_lost)
            session.add(stage)
            by_key[key] = stage
            changed = True
        elif stage.position != position:
            stage.position = position
            changed = True

    if changed:
        await session.flush()
    return changed


async def ensure_platform_pipeline(session: AsyncSession, _retrying: bool = False) -> CrmPipeline:
    """Get-or-create BetterCricket's own sales pipeline. Exactly one always
    exists — unlike the club scope, this one is NOT optional.

    This runs on nearly every platform CRM read endpoint, so under real
    concurrent traffic more than one in-flight request can decide "a default
    stage is missing here, let me add it" at the same moment — right after
    one is deleted (the reconciliation loop backfills anything in
    PLATFORM_DEFAULT_STAGES it doesn't find), or the first time a brand-new
    default stage ships. The loser of that race hits a UNIQUE
    (pipeline_id, key) violation on flush/commit — previously an unhandled
    500 on what looks like an ordinary read. Caught once here: roll back,
    then re-fetch — the winner's write already committed, so the retry just
    sees a complete, correct pipeline with nothing left to reconcile.
    """
    stmt = select(CrmPipeline).options(selectinload(CrmPipeline.stages)).where(
        CrmPipeline.scope == SCOPE_PLATFORM, CrmPipeline.organisation_id.is_(None),
        CrmPipeline.is_default.is_(True))
    pipeline = (await session.execute(stmt)).scalars().first()
    if pipeline is not None:
        try:
            if await _reconcile_platform_stages(session, pipeline):
                await session.commit()
                await session.refresh(pipeline, attribute_names=["stages"])
        except IntegrityError:
            await session.rollback()
            if _retrying:
                raise
            return await ensure_platform_pipeline(session, _retrying=True)
        return pipeline
    pipeline = CrmPipeline(scope=SCOPE_PLATFORM, organisation_id=None, name="BetterCricket Sales", is_default=True)
    session.add(pipeline)
    try:
        await session.flush()
        for position, (key, name, prob, is_won, is_lost) in enumerate(PLATFORM_DEFAULT_STAGES):
            session.add(CrmStage(
                pipeline_id=pipeline.id, key=key, name=name, position=position,
                default_probability=prob, is_won=is_won, is_lost=is_lost,
            ))
        # Commit here — this branch used to rely on the CALLER to commit,
        # but several read-only endpoints never do, so a brand-new platform
        # pipeline could be flushed, returned for that one response, and then
        # silently rolled back when the request's session closed.
        await session.commit()
    except IntegrityError:
        await session.rollback()
        if _retrying:
            raise
        return await ensure_platform_pipeline(session, _retrying=True)
    await session.refresh(pipeline, attribute_names=["stages"])
    return pipeline


async def get_pipeline_for_org(session: AsyncSession, pipeline_id, organisation_id) -> Optional[CrmPipeline]:
    """A club-scope pipeline owned by this org, with its stages loaded — the
    ownership check every club-scope tracker/board/deal endpoint gates on."""
    stmt = select(CrmPipeline).options(selectinload(CrmPipeline.stages)).where(CrmPipeline.id == pipeline_id)
    pipeline = (await session.execute(stmt)).scalars().first()
    if pipeline is None or pipeline.scope != SCOPE_CLUB or str(pipeline.organisation_id) != str(organisation_id):
        return None
    return pipeline


def terms_for_pipeline(pipeline: CrmPipeline) -> dict:
    if pipeline.template_key and pipeline.template_key in PIPELINE_TEMPLATES:
        return PIPELINE_TEMPLATES[pipeline.template_key]["terms"]
    return CUSTOM_TERMS


async def tracker_catalogue(session: AsyncSession, organisation_id) -> dict:
    """The "Add a tracker" screen's data: every preset template (with whether
    this club already has it active, and its pipeline id if so) plus this
    club's own custom trackers, active or not."""
    existing = (await session.execute(
        select(CrmPipeline).where(CrmPipeline.scope == SCOPE_CLUB, CrmPipeline.organisation_id == organisation_id)
    )).scalars().all()
    by_template = {p.template_key: p for p in existing if p.template_key}
    presets = []
    for key, tpl in PIPELINE_TEMPLATES.items():
        existing_p = by_template.get(key)
        presets.append({
            "key": key, "label": tpl["label"], "blurb": tpl["blurb"],
            "active": bool(existing_p and existing_p.is_active),
            "pipeline_id": str(existing_p.id) if existing_p else None,
        })
    customs = [
        {"id": str(p.id), "name": p.name, "active": p.is_active}
        for p in existing if not p.template_key
    ]
    return {"presets": presets, "custom": customs}


async def active_trackers(session: AsyncSession, organisation_id) -> list[dict]:
    """Every tracker this club currently has switched on — what the module's
    nav is built from. Each carries its own vocabulary (`terms`)."""
    rows = (await session.execute(
        select(CrmPipeline).where(
            CrmPipeline.scope == SCOPE_CLUB, CrmPipeline.organisation_id == organisation_id,
            CrmPipeline.is_active.is_(True))
        .order_by(CrmPipeline.created_at)
    )).scalars().all()
    return [
        {"id": str(p.id), "name": p.name, "template_key": p.template_key, "terms": terms_for_pipeline(p)}
        for p in rows
    ]


async def add_tracker(session: AsyncSession, organisation_id, *,
                      template_key: Optional[str] = None, name: Optional[str] = None) -> CrmPipeline:
    """Turn a preset template on (minting it the first time, reactivating it
    if the club had switched it off before — so history survives a re-add),
    or create a brand new custom tracker."""
    if template_key:
        tpl = PIPELINE_TEMPLATES.get(template_key)
        if tpl is None:
            raise ValueError(f"Unknown tracker template: {template_key}")
        existing = (await session.execute(
            select(CrmPipeline).options(selectinload(CrmPipeline.stages)).where(
                CrmPipeline.scope == SCOPE_CLUB, CrmPipeline.organisation_id == organisation_id,
                CrmPipeline.template_key == template_key)
        )).scalars().first()
        if existing is not None:
            existing.is_active = True
            return existing
        pipeline = CrmPipeline(scope=SCOPE_CLUB, organisation_id=organisation_id,
                              name=tpl["label"], template_key=template_key, is_active=True)
        stages_def = tpl["stages"]
    else:
        if not name or not name.strip():
            raise ValueError("A custom tracker needs a name")
        pipeline = CrmPipeline(scope=SCOPE_CLUB, organisation_id=organisation_id,
                              name=name.strip()[:120], template_key=None, is_active=True)
        stages_def = CUSTOM_DEFAULT_STAGES
    session.add(pipeline)
    await session.flush()
    for position, (key, sname, prob, is_won, is_lost) in enumerate(stages_def):
        session.add(CrmStage(pipeline_id=pipeline.id, key=key, name=sname, position=position,
                             default_probability=prob, is_won=is_won, is_lost=is_lost))
    await session.flush()
    await session.refresh(pipeline, attribute_names=["stages"])
    return pipeline


async def deactivate_tracker(session: AsyncSession, pipeline: CrmPipeline) -> None:
    """"Removing" a tracker just hides it — its deals stay, and re-adding the
    same preset later reactivates this same pipeline rather than duplicating."""
    pipeline.is_active = False


async def reactivate_tracker(session: AsyncSession, pipeline: CrmPipeline) -> None:
    """Turn a previously-removed tracker back on. A preset is more commonly
    reactivated via ``add_tracker`` (which finds it by template_key), but a
    custom tracker has no template_key to re-find it by, so it's reactivated
    directly by id instead."""
    pipeline.is_active = True


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    s = _SLUG_RE.sub("_", text.strip().lower()).strip("_")
    return s or "stage"


async def add_stage(session: AsyncSession, pipeline: CrmPipeline, *, name: str,
                    default_probability: int = 0, is_won: bool = False, is_lost: bool = False,
                    hidden_from_board: bool = False) -> CrmStage:
    base = _slug(name)
    existing_keys = {s.key for s in pipeline.stages}
    key, n = base, 2
    while key in existing_keys:
        key = f"{base}_{n}"
        n += 1
    stage = CrmStage(
        pipeline_id=pipeline.id, key=key, name=(name or "New stage")[:80], position=len(pipeline.stages),
        default_probability=max(0, min(100, int(default_probability or 0))), is_won=is_won, is_lost=is_lost,
        hidden_from_board=hidden_from_board,
    )
    session.add(stage)
    await session.flush()
    return stage


async def update_stage(session: AsyncSession, stage: CrmStage, **fields) -> CrmStage:
    for f in ("name", "default_probability", "is_won", "is_lost", "position", "hidden_from_board"):
        if f in fields and fields[f] is not None:
            setattr(stage, f, fields[f])
    return stage


async def delete_stage(session: AsyncSession, stage: CrmStage) -> None:
    in_use = (await session.execute(
        select(func.count()).select_from(CrmDeal).where(CrmDeal.stage_id == stage.id)
    )).scalar_one()
    if in_use:
        raise ValueError("This stage still has records in it — move or archive them first")
    # If this is one of the platform pipeline's own PLATFORM_DEFAULT_STAGES,
    # record its key so _reconcile_platform_stages doesn't silently recreate
    # it on the very next read (a super admin deleting "Self-Serve Trial"
    # otherwise saw it reappear immediately).
    pipeline = await session.get(CrmPipeline, stage.pipeline_id)
    if pipeline is not None and pipeline.scope == SCOPE_PLATFORM:
        removed = list(pipeline.removed_stage_keys or [])
        if stage.key not in removed:
            removed.append(stage.key)
            pipeline.removed_stage_keys = removed
    await session.delete(stage)


def stage_dicts(pipeline: CrmPipeline) -> list[dict]:
    return [
        {"id": str(s.id), "key": s.key, "name": s.name, "position": s.position,
         "default_probability": s.default_probability, "is_won": s.is_won, "is_lost": s.is_lost,
         "hidden_from_board": s.hidden_from_board}
        for s in pipeline.stages
    ]


def _effective_probability(deal: CrmDeal, stage: Optional[CrmStage]) -> Optional[int]:
    if deal.probability is not None:
        return deal.probability
    return stage.default_probability if stage else None


def _effective_value_cents(deal: CrmDeal) -> int:
    """``value_cents`` (the module-derived, bundle-discounted base price) minus
    a super admin's own discretionary discount, if any — at most one of
    amount/percent applies at a time (amount wins if somehow both are set).
    This is what pipeline totals/weighted value are computed from; the raw
    ``value_cents`` stays the undiscounted reference figure."""
    base = deal.value_cents or 0
    if deal.discount_amount_cents:
        return max(0, base - int(deal.discount_amount_cents))
    if deal.discount_percent:
        pct = max(0, min(100, int(deal.discount_percent)))
        return max(0, round(base * (100 - pct) / 100))
    return base


def _deal_dict(deal: CrmDeal, stage: Optional[CrmStage] = None,
               club: Optional[MarketingClub] = None) -> dict:
    eff = _effective_probability(deal, stage)
    effective_value = _effective_value_cents(deal)
    return {
        "id": str(deal.id),
        "scope": deal.scope,
        "organisation_id": str(deal.organisation_id) if deal.organisation_id else None,
        "marketing_club_id": str(deal.marketing_club_id) if deal.marketing_club_id else None,
        # Engagement score/tier are never computed here — they're Twenty's own
        # mirrored number, sourced straight from marketing_clubs.engagement_score
        # (twenty_sync._engagement()), the same one Twenty's Lead/Opportunity
        # both mirror from the Company. `club` is only ever set for a platform
        # deal linked to a prospect; a club-scope deal has no marketing_club_id
        # so this is always None there.
        "engagement_score": club.engagement_score if club else None,
        "engagement_tier": club.engagement_tier if club else None,
        "marketing_club_name": club.name if club else None,
        "is_customer": bool(club.existing_org_id) if club else None,
        "pipeline_id": str(deal.pipeline_id),
        "stage_id": str(deal.stage_id),
        "stage_key": stage.key if stage else None,
        "stage_name": stage.name if stage else None,
        "title": deal.title,
        "value_cents": deal.value_cents,
        "discount_amount_cents": deal.discount_amount_cents,
        "discount_percent": deal.discount_percent,
        "discount_reason": deal.discount_reason,
        "effective_value_cents": effective_value,
        "currency": deal.currency,
        "probability": deal.probability,
        "effective_probability": eff,
        "weighted_value_cents": round(effective_value * eff / 100) if eff is not None else None,
        "module_keys": deal.module_keys or [],
        "expected_close_date": deal.expected_close_date.isoformat() if deal.expected_close_date else None,
        "status": deal.status,
        "lost_reason": deal.lost_reason,
        "owner_user_id": str(deal.owner_user_id) if deal.owner_user_id else None,
        "source": deal.source,
        "onboarding_method": deal.onboarding_method,
        "lead_source": deal.lead_source,
        "product_interest_source": deal.product_interest_source,
        "stage_auto_locked": deal.stage_auto_locked,
        "archived_at": deal.archived_at.isoformat() if deal.archived_at else None,
        "created_at": deal.created_at.isoformat() if deal.created_at else None,
        "updated_at": deal.updated_at.isoformat() if deal.updated_at else None,
        "closed_at": deal.closed_at.isoformat() if deal.closed_at else None,
    }


def _person_dict(person: CrmPerson) -> dict:
    return {
        "id": str(person.id),
        "organisation_id": str(person.organisation_id) if person.organisation_id else None,
        "marketing_club_id": str(person.marketing_club_id) if person.marketing_club_id else None,
        "player_id": str(person.player_id) if person.player_id else None,
        "full_name": person.full_name,
        "email": person.email,
        "phone": person.phone,
        "notes": person.notes,
        "roles": [
            {"id": str(r.id), "role": r.role, "title": r.title,
             "started_at": r.started_at.isoformat() if r.started_at else None,
             "ended_at": r.ended_at.isoformat() if r.ended_at else None}
            for r in (person.roles or [])
        ],
    }


def _activity_dict(activity: CrmActivity) -> dict:
    return {
        "id": str(activity.id),
        "deal_id": str(activity.deal_id) if activity.deal_id else None,
        "person_id": str(activity.person_id) if activity.person_id else None,
        "organisation_id": str(activity.organisation_id) if activity.organisation_id else None,
        "type": activity.type,
        "body": activity.body,
        "occurred_at": activity.occurred_at.isoformat() if activity.occurred_at else None,
        "created_by_user_id": str(activity.created_by_user_id) if activity.created_by_user_id else None,
        "meta": activity.meta,
    }


def pipeline_board(pipeline: CrmPipeline, deals: list[CrmDeal],
                   club_by_id: Optional[dict] = None) -> dict:
    """Stages with their open deals + weighted value per stage and overall —
    the Kanban board's shape, computed from an already-loaded pipeline
    (stages) and its (non-archived) deals. Pure/sync: callers fetch both.
    ``club_by_id`` (marketing_club_id -> MarketingClub) lets platform-scope
    cards carry the linked prospect's engagement score without this function
    making its own query — see clubs_by_ids()."""
    club_by_id = club_by_id or {}
    by_stage: dict = {}
    for d in deals:
        by_stage.setdefault(d.stage_id, []).append(d)

    stages_out = []
    total_open_value = 0
    total_weighted = 0
    total_open_count = 0
    for stage in pipeline.stages:
        stage_deals = by_stage.get(stage.id, [])
        stage_value = 0
        stage_weighted = 0
        deals_out = []
        for d in stage_deals:
            deals_out.append(_deal_dict(d, stage, club_by_id.get(d.marketing_club_id)))
            if d.status == "open":
                eff = _effective_probability(d, stage) or 0
                effective_value = _effective_value_cents(d)
                stage_value += effective_value
                stage_weighted += round(effective_value * eff / 100)
                total_open_count += 1
        total_open_value += stage_value
        total_weighted += stage_weighted
        stages_out.append({
            "id": str(stage.id), "key": stage.key, "name": stage.name,
            "position": stage.position, "default_probability": stage.default_probability,
            "is_won": stage.is_won, "is_lost": stage.is_lost, "hidden_from_board": stage.hidden_from_board,
            "deal_count": len(stage_deals),
            "value_cents": stage_value,
            "weighted_value_cents": stage_weighted,
            "deals": deals_out,
        })
    return {
        "pipeline": {"id": str(pipeline.id), "name": pipeline.name, "scope": pipeline.scope,
                    "terms": terms_for_pipeline(pipeline)},
        "stages": stages_out,
        "totals": {
            "open_value_cents": total_open_value,
            "weighted_value_cents": total_weighted,
            "open_count": total_open_count,
        },
    }


# ─── Deals ────────────────────────────────────────────────────────────────────

async def list_deals(session: AsyncSession, pipeline_id, *,
                     status: Optional[str] = None, include_archived: bool = False) -> list[CrmDeal]:
    stmt = select(CrmDeal).where(CrmDeal.pipeline_id == pipeline_id)
    if not include_archived:
        stmt = stmt.where(CrmDeal.archived_at.is_(None))
    if status:
        stmt = stmt.where(CrmDeal.status == status)
    stmt = stmt.order_by(CrmDeal.updated_at.desc())
    return (await session.execute(stmt)).scalars().all()


async def get_deal(session: AsyncSession, deal_id, scope: str, organisation_id=None) -> Optional[CrmDeal]:
    deal = await session.get(CrmDeal, deal_id)
    if deal is None or deal.scope != scope:
        return None
    if scope == SCOPE_CLUB and str(deal.organisation_id) != str(organisation_id):
        return None
    return deal


async def get_deal_pipeline(session: AsyncSession, deal: CrmDeal) -> Optional[CrmPipeline]:
    """The (stages-loaded) pipeline a deal belongs to — for serialising a
    single deal without the caller needing to already know which pipeline."""
    stmt = select(CrmPipeline).options(selectinload(CrmPipeline.stages)).where(CrmPipeline.id == deal.pipeline_id)
    return (await session.execute(stmt)).scalars().first()


def value_from_modules(module_keys) -> int:
    """The bundle-discounted module price (billing_pricing.price_for), in
    cents — the ONE place a platform deal's Product-Interest-driven Value is
    computed from, so it can never silently drift from module_keys."""
    keys = sorted(set(module_keys or []))
    if not keys:
        return 0
    return int(round(price_for(keys)["total"] * 100))


async def recalc_product_interest(session: AsyncSession, deal: CrmDeal, club: Optional[MarketingClub]) -> bool:
    """Re-derive a platform deal's Product Interest (module_keys) from the
    linked club's tracked website visits (club_directory.club_visit_detail's
    ranked ``inferred_modules``), and recompute value_cents to match. Always
    switches the deal back to 'auto' — the counterpart to a super admin
    manually overriding a module chip (which sets 'manual'). A deal with no
    linked club, or a club with no tracked visits at all, falls back to
    ``['core']`` (never leaves module_keys empty). Returns whether any real
    tracked visit was actually found — a caller/UI can tell "recalculated
    from N page views" apart from "no analytics yet, defaulted to Stats",
    which otherwise look identical when the deal was already just ['core']."""
    from app.services import club_directory
    inferred = ["core"]
    had_data = False
    if club is not None:
        detail = await club_directory.club_visit_detail(session, club.id)
        if detail.get("inferred_modules"):
            inferred = detail["inferred_modules"]
            had_data = bool(detail.get("views"))
    deal.module_keys = inferred
    deal.value_cents = value_from_modules(inferred)
    deal.product_interest_source = "auto"
    deal.updated_at = func.now()
    return had_data


async def create_deal(session: AsyncSession, *, scope: str, pipeline_id, stage_id,
                      title: str, organisation_id=None, marketing_club_id=None,
                      value_cents: int = 0, currency: str = "AUD",
                      probability: Optional[int] = None, module_keys=None,
                      expected_close_date=None, owner_user_id=None,
                      source: str = "manual", onboarding_method: Optional[str] = None,
                      lead_source: Optional[str] = None) -> CrmDeal:
    keys = list(module_keys or [])
    # A platform deal's Value is Product-Interest-driven (see value_from_modules)
    # — a club-scope tracker (sponsors/grants/custom) has no module_keys concept
    # and keeps value_cents fully manual, same as before.
    if scope == SCOPE_PLATFORM and keys:
        value_cents = value_from_modules(keys)
    deal = CrmDeal(
        scope=scope, organisation_id=organisation_id, marketing_club_id=marketing_club_id,
        pipeline_id=pipeline_id, stage_id=stage_id, title=(title or "Untitled deal")[:300],
        value_cents=max(0, int(value_cents or 0)), currency=currency or "AUD",
        probability=probability, module_keys=keys,
        expected_close_date=expected_close_date, owner_user_id=owner_user_id, source=source,
        onboarding_method=onboarding_method, lead_source=lead_source,
    )
    session.add(deal)
    await session.flush()
    return deal


_DEAL_CLEARABLE_FIELDS = ("probability", "expected_close_date", "owner_user_id",
                         "onboarding_method", "lead_source",
                         "discount_amount_cents", "discount_percent", "discount_reason")


async def update_deal(session: AsyncSession, deal: CrmDeal, **fields) -> CrmDeal:
    for key in ("title", "value_cents", "currency", "probability", "module_keys",
                "expected_close_date", "owner_user_id", "onboarding_method", "lead_source",
                "discount_amount_cents", "discount_percent", "discount_reason",
                "product_interest_source"):
        if key not in fields:
            continue
        # Most fields never take an explicit null (title/value_cents/module_keys
        # shouldn't ever be wiped by omission-vs-null ambiguity), but these are
        # legitimately clearable (e.g. "unassign the owner", "remove the
        # discount") — the request body sending an explicit None for them
        # means "clear it", not "no change" (an unsent field is simply absent
        # from `fields` at all, since the router calls
        # model_dump(exclude_unset=True)).
        if fields[key] is not None or key in _DEAL_CLEARABLE_FIELDS:
            setattr(deal, key, fields[key])
    # Product Interest drives Value automatically for a platform deal — editing
    # module_keys recomputes value_cents from the bundle-discounted module
    # price, so the two fields can never silently drift apart. Club-scope
    # deals (sponsors/grants/custom trackers) keep value_cents fully manual.
    if deal.scope == SCOPE_PLATFORM and "module_keys" in fields and fields["module_keys"] is not None:
        keys = sorted(set(fields["module_keys"] or []))
        if keys:
            deal.value_cents = value_from_modules(keys)
    if (deal.discount_amount_cents or deal.discount_percent) and not (deal.discount_reason or "").strip():
        raise ValueError("A discretionary discount requires a reason")
    deal.updated_at = func.now()
    return deal


async def move_stage(session: AsyncSession, deal: CrmDeal, stage: CrmStage, *,
                     probability: Optional[int] = None) -> CrmDeal:
    deal.stage_id = stage.id
    if probability is not None:
        deal.probability = probability
    deal.updated_at = func.now()
    if stage.is_won:
        deal.status = "won"
        deal.closed_at = func.now()
    elif stage.is_lost:
        deal.status = "lost"
        deal.closed_at = func.now()
    else:
        deal.status = "open"
        deal.closed_at = None
    return deal


async def close_deal(session: AsyncSession, deal: CrmDeal, pipeline: CrmPipeline, *,
                     status: str, lost_reason: Optional[str] = None) -> CrmDeal:
    target = next((s for s in pipeline.stages if (s.is_won if status == "won" else s.is_lost)), None)
    if target is not None:
        deal.stage_id = target.id
    deal.status = status
    deal.lost_reason = lost_reason if status == "lost" else None
    deal.closed_at = func.now()
    deal.updated_at = func.now()
    return deal


async def archive_deal(session: AsyncSession, deal: CrmDeal) -> CrmDeal:
    deal.archived_at = func.now()
    return deal


async def delete_deal(session: AsyncSession, deal: CrmDeal) -> None:
    """A real, permanent delete — unlike archive_deal, which just hides it.
    CrmActivity.deal_id and CrmDealContact.deal_id are both ON DELETE CASCADE,
    so the deal's notes/activity log and contact links go with it; no
    manual child cleanup needed."""
    await session.delete(deal)


async def reset_marketing_club_engagement(session: AsyncSession, club: MarketingClub) -> None:
    """Wipe every sales-pipeline/engagement signal a super admin can have set
    on a prospect club (see twenty_sync._engagement — this clears every
    input that function reads besides real web/email activity and
    club_onboarding_requests, which aren't safely scoped to one club without
    a direct FK) — for purging TEST activity on a real club's directory row,
    so a later genuine self-serve signup or enquiry scores itself fresh
    rather than inheriting stale test state. Does NOT delete the
    MarketingClub row itself — it's the club's real directory entry, not
    test data."""
    from app.services import club_directory
    await club_directory.set_sales_state(
        session, str(club.id), trial_modules=[], requested_trial_modules=[],
        demo_status=None, not_interested=False)
    club.emailed_at = None
    club.emailed_via = None
    club.emailed_note = None
    club.engagement_score = None
    club.engagement_tier = None
    club.engagement_scored_at = None


# ─── People / contacts ───────────────────────────────────────────────────────

async def resolve_person(session: AsyncSession, *, full_name: str, organisation_id=None,
                         marketing_club_id=None, email: Optional[str] = None,
                         phone: Optional[str] = None) -> CrmPerson:
    """Find-or-create a Person scoped to a club (or a prospect marketing club),
    deduped by email first, else an exact case-insensitive name match. Fills
    gaps on an existing match; never overwrites a value already on file."""
    email_l = (email or "").strip().lower() or None
    stmt = select(CrmPerson).options(selectinload(CrmPerson.roles))
    if organisation_id is not None:
        stmt = stmt.where(CrmPerson.organisation_id == organisation_id)
    elif marketing_club_id is not None:
        stmt = stmt.where(CrmPerson.marketing_club_id == marketing_club_id)
    else:
        stmt = stmt.where(CrmPerson.organisation_id.is_(None), CrmPerson.marketing_club_id.is_(None))

    person = None
    if email_l:
        person = (await session.execute(stmt.where(func.lower(CrmPerson.email) == email_l))).scalars().first()
    if person is None and full_name:
        person = (await session.execute(
            stmt.where(func.lower(CrmPerson.full_name) == full_name.strip().lower())
        )).scalars().first()
    if person is not None:
        if email_l and not person.email:
            person.email = email_l
        if phone and not person.phone:
            person.phone = phone
        return person

    person = CrmPerson(
        organisation_id=organisation_id, marketing_club_id=marketing_club_id,
        full_name=(full_name or "Unknown").strip()[:200] or "Unknown",
        email=email_l, phone=phone,
    )
    session.add(person)
    await session.flush()
    return person


async def list_people(session: AsyncSession, *, organisation_id=None, marketing_club_id=None,
                      q: Optional[str] = None, limit: int = 200) -> list[CrmPerson]:
    stmt = select(CrmPerson).options(selectinload(CrmPerson.roles))
    if organisation_id is not None:
        stmt = stmt.where(CrmPerson.organisation_id == organisation_id)
    if marketing_club_id is not None:
        stmt = stmt.where(CrmPerson.marketing_club_id == marketing_club_id)
    if q:
        needle = f"%{q.strip().lower()}%"
        stmt = stmt.where(func.lower(CrmPerson.full_name).like(needle) | func.lower(CrmPerson.email).like(needle))
    stmt = stmt.order_by(CrmPerson.full_name).limit(limit)
    return (await session.execute(stmt)).scalars().all()


async def add_person_role(session: AsyncSession, person_id, *, role: str,
                          organisation_id=None, title: Optional[str] = None,
                          started_at=None, ended_at=None, notes: Optional[str] = None) -> CrmPersonRole:
    role_row = CrmPersonRole(
        person_id=person_id, organisation_id=organisation_id,
        role=role if role in PERSON_ROLES else "other", title=title,
        started_at=started_at, ended_at=ended_at, notes=notes,
    )
    session.add(role_row)
    await session.flush()
    return role_row


async def link_deal_contact(session: AsyncSession, deal_id, person_id,
                            role_on_deal: Optional[str] = None) -> CrmDealContact:
    existing = (await session.execute(
        select(CrmDealContact).where(CrmDealContact.deal_id == deal_id, CrmDealContact.person_id == person_id)
    )).scalars().first()
    if existing is not None:
        if role_on_deal is not None:
            existing.role_on_deal = role_on_deal
        return existing
    link = CrmDealContact(deal_id=deal_id, person_id=person_id, role_on_deal=role_on_deal)
    session.add(link)
    await session.flush()
    return link


# Convention, not a column: at most one CrmDealContact per deal carries this
# role at a time (enforced by set_point_of_contact clearing any other holder)
# — mirrors Twenty's single "Point of Contact" field on an Opportunity, on
# top of our own model's richer many-contacts-per-deal shape.
POINT_OF_CONTACT_ROLE = "point_of_contact"


async def set_point_of_contact(session: AsyncSession, deal_id, person_id) -> CrmDealContact:
    """Designate ``person_id`` as the deal's ONE point of contact, demoting
    whoever held that role before (their link stays, just loses the role) —
    without this, re-designating would leave two contacts both flagged as
    the point of contact."""
    await session.execute(
        sa_update(CrmDealContact).where(
            CrmDealContact.deal_id == deal_id, CrmDealContact.role_on_deal == POINT_OF_CONTACT_ROLE,
            CrmDealContact.person_id != person_id,
        ).values(role_on_deal=None))
    return await link_deal_contact(session, deal_id, person_id, role_on_deal=POINT_OF_CONTACT_ROLE)


async def clubs_by_ids(session: AsyncSession, club_ids) -> dict:
    """marketing_club_id -> MarketingClub, for the set of ids actually
    referenced by a batch of deals — avoids an N+1 query per deal when
    serialising a board/list."""
    ids = {c for c in club_ids if c is not None}
    if not ids:
        return {}
    rows = (await session.execute(select(MarketingClub).where(MarketingClub.id.in_(ids)))).scalars().all()
    return {c.id: c for c in rows}


async def poc_names_by_deal(session: AsyncSession, deal_ids) -> dict:
    """deal_id -> its designated point of contact's full name, batched for
    the platform deal list's search/filter bar (poc_name)."""
    ids = list(deal_ids)
    if not ids:
        return {}
    rows = (await session.execute(
        select(CrmDealContact.deal_id, CrmPerson.full_name)
        .join(CrmPerson, CrmPerson.id == CrmDealContact.person_id)
        .where(CrmDealContact.deal_id.in_(ids), CrmDealContact.role_on_deal == POINT_OF_CONTACT_ROLE)
    )).all()
    return {deal_id: name for deal_id, name in rows}


async def acquisition_channels_by_club(session: AsyncSession, club_by_id: dict) -> dict:
    """marketing_club_id -> a best-guess acquisition channel label, for the
    Super Admin CRM's "Source" filter — batched (no N+1 per deal). Priority,
    most-specific first:
      1. The linked Organisation's real signup attribution
         (signup_attribution.utm_source, e.g. "google"/"facebook" — only set
         for a self-serve ad-driven registration; else signup_source itself,
         "self_serve_ad"/"self_serve_organic").
      2. The most recent club_onboarding_requests row matching one of the
         club's own contact emails ("contact_form" = the full Contact page,
         "cta_quick_form" = the quick "Get your club on BetterCricket" modal).
    Returns None for a club with neither signal — the caller falls back to
    the deal's own `source` (manual/auto_enquiry/auto_trial/twenty_import)."""
    out: dict = {}
    org_ids = {c.existing_org_id for c in club_by_id.values() if c.existing_org_id}
    orgs: dict = {}
    if org_ids:
        rows = (await session.execute(
            select(Organisation.id, Organisation.signup_source, Organisation.signup_attribution)
            .where(Organisation.id.in_(org_ids))
        )).all()
        orgs = {r[0]: (r[1], r[2]) for r in rows}

    club_ids = list(club_by_id.keys())
    club_by_email: dict = {}
    if club_ids:
        contact_rows = (await session.execute(
            select(MarketingClubContact.marketing_club_id, MarketingClubContact.email)
            .where(MarketingClubContact.marketing_club_id.in_(club_ids),
                  MarketingClubContact.email.isnot(None), MarketingClubContact.email != "")
        )).all()
        for cid, email in contact_rows:
            club_by_email.setdefault(email.strip().lower(), cid)

    onboarding_source_by_club: dict = {}
    if club_by_email:
        rows = (await session.execute(
            select(ClubOnboardingRequest.email, ClubOnboardingRequest.source)
            .where(func.lower(ClubOnboardingRequest.email).in_(club_by_email.keys()))
            .order_by(ClubOnboardingRequest.created_at.desc())
        )).all()
        for email, source in rows:
            cid = club_by_email.get((email or "").strip().lower())
            if cid is not None and cid not in onboarding_source_by_club:
                onboarding_source_by_club[cid] = source

    for cid, club in club_by_id.items():
        channel = None
        if club.existing_org_id and club.existing_org_id in orgs:
            signup_source, attribution = orgs[club.existing_org_id]
            utm_source = (attribution or {}).get("utm_source") if isinstance(attribution, dict) else None
            channel = utm_source or signup_source
        if not channel:
            channel = onboarding_source_by_club.get(cid)
        out[cid] = channel
    return out


async def trial_days_remaining_by_club(session: AsyncSession, club_by_id: dict) -> dict:
    """marketing_club_id -> {billable_module_key: days_remaining}, for every
    club linked to an onboarded org with at least one currently-tracked
    module trial (status still ``trial`` — see module_subscriptions.
    sweep_expired_trials, which leaves an expired trial's row/status alone
    and just refreshes the held-modules cache) — batched (no N+1). Powers
    the CRM card's per-module trial countdown, the "trial expiring between X
    and Y days" filter, and the expired-trial badge. A prospect that's never
    been onboarded (no existing_org_id) has no tracked trial_ends_at at all
    and is simply absent from the result.

    ``days_remaining`` is SIGNED and NOT clamped at 0 — negative means the
    trial's end date has already passed (e.g. -3 = expired 3 days ago),
    which is the whole point: a caller needs to tell "expires today" (0)
    apart from "already expired" (< 0) to render an EXPIRED badge instead of
    a countdown. Do not clamp this back to 0 in a new caller — that's the
    exact bug this fixed (every already-expired trial used to read
    identically to one expiring today)."""
    from app.auth.modules import STATUS_TRIAL, billing_key_for
    org_to_club = {c.existing_org_id: cid for cid, c in club_by_id.items() if c.existing_org_id}
    if not org_to_club:
        return {}
    rows = (await session.execute(
        select(OrgModuleSubscription.organisation_id, OrgModuleSubscription.module_key,
              OrgModuleSubscription.trial_ends_at)
        .where(OrgModuleSubscription.organisation_id.in_(org_to_club.keys()),
              OrgModuleSubscription.status == STATUS_TRIAL,
              OrgModuleSubscription.trial_ends_at.isnot(None))
    )).all()
    now = datetime.now(timezone.utc)
    out: dict = {}
    for org_id, module_key, ends_at in rows:
        cid = org_to_club.get(org_id)
        if cid is None:
            continue
        days = (ends_at - now).days
        out.setdefault(cid, {})[billing_key_for(module_key)] = days
    return out


async def subscribed_modules_by_club(session: AsyncSession, club_by_id: dict) -> dict:
    """marketing_club_id -> [billable_module_key, ...] the club is ALREADY a
    PAYING subscriber for (active/past_due, never a trial) — the counterpart
    to trial_days_remaining_by_club. Lets the card grey out a module chip and
    suppress its trial countdown once the club has actually bought it,
    instead of showing a stale "days remaining" for a module they no longer
    need to trial."""
    from app.auth.modules import PAID_STATUSES, billing_key_for
    org_to_club = {c.existing_org_id: cid for cid, c in club_by_id.items() if c.existing_org_id}
    if not org_to_club:
        return {}
    rows = (await session.execute(
        select(OrgModuleSubscription.organisation_id, OrgModuleSubscription.module_key)
        .where(OrgModuleSubscription.organisation_id.in_(org_to_club.keys()),
              OrgModuleSubscription.status.in_(PAID_STATUSES))
    )).all()
    out: dict = {}
    for org_id, module_key in rows:
        cid = org_to_club.get(org_id)
        if cid is None:
            continue
        out.setdefault(cid, set()).add(billing_key_for(module_key))
    return {cid: sorted(keys) for cid, keys in out.items()}


async def list_platform_owners(session: AsyncSession) -> list[dict]:
    """Every super admin — the internal BetterCricket staff pool a platform
    deal's owner_user_id is picked from (not a club's own users)."""
    rows = (await session.execute(
        select(User).join(ClubMembership, ClubMembership.user_id == User.id)
        .where(ClubMembership.role == "super_admin")
        .distinct().order_by(User.display_name, User.username)
    )).scalars().all()
    return [{"id": str(u.id), "name": u.display_name or u.username, "email": u.email} for u in rows]


async def get_person(session: AsyncSession, person_id) -> Optional[CrmPerson]:
    """A single Person with ``roles`` eager-loaded — the safe way to fetch one
    for ``_person_dict()``. Plain ``session.get(CrmPerson, id)``/an unadorned
    ``select(CrmPerson)`` leaves ``roles`` unloaded; touching it from
    ``_person_dict`` in an async session then raises (MissingGreenlet), which
    FastAPI's default handler turns into a bare "Internal Server Error" with
    no JSON body — surfaced by the CRM's every deal/person read that reaches
    a person this way (list_deal_contacts below, and every router call site
    that used to load a person with a plain ``db.get``)."""
    return (await session.execute(
        select(CrmPerson).options(selectinload(CrmPerson.roles)).where(CrmPerson.id == person_id)
    )).scalars().first()


async def list_deal_contacts(session: AsyncSession, deal_id) -> list[dict]:
    rows = (await session.execute(
        select(CrmDealContact, CrmPerson).options(selectinload(CrmPerson.roles))
        .join(CrmPerson, CrmPerson.id == CrmDealContact.person_id)
        .where(CrmDealContact.deal_id == deal_id)
    )).all()
    out = []
    for link, person in rows:
        d = _person_dict(person)
        d["role_on_deal"] = link.role_on_deal
        out.append(d)
    return out


async def unlink_deal_contact(session: AsyncSession, deal_id, person_id) -> bool:
    existing = (await session.execute(
        select(CrmDealContact).where(CrmDealContact.deal_id == deal_id, CrmDealContact.person_id == person_id)
    )).scalars().first()
    if existing is None:
        return False
    await session.delete(existing)
    return True


# ─── Activities (timeline) ───────────────────────────────────────────────────

async def log_activity(session: AsyncSession, *, deal_id=None, person_id=None,
                       organisation_id=None, type: str = "note", body: Optional[str] = None,
                       created_by_user_id=None, meta: Optional[dict] = None) -> CrmActivity:
    activity = CrmActivity(
        deal_id=deal_id, person_id=person_id, organisation_id=organisation_id,
        type=type if type in ACTIVITY_TYPES else "note", body=body,
        created_by_user_id=created_by_user_id, meta=meta,
    )
    session.add(activity)
    await session.flush()
    return activity


async def list_activities(session: AsyncSession, *, deal_id=None, person_id=None,
                          limit: int = 200) -> list[CrmActivity]:
    stmt = select(CrmActivity).order_by(CrmActivity.occurred_at.desc()).limit(limit)
    if deal_id is not None:
        stmt = stmt.where(CrmActivity.deal_id == deal_id)
    if person_id is not None:
        stmt = stmt.where(CrmActivity.person_id == person_id)
    return (await session.execute(stmt)).scalars().all()


# ─── Auto-creation: platform deals from existing engagement/trial signals ───
# Mirrors twenty_sync.py's own trigger points (a direct enquiry, a trial
# request/start) so the local pipeline stays in step with the same signals
# that used to ONLY push into Twenty — see the call sites in
# routers/public_contact.py and services/club_directory.py::set_sales_state.

async def sync_platform_deal_for_club(session: AsyncSession, club: MarketingClub, *,
                                      stage_key: str, source: str,
                                      module_keys=None, person_id=None,
                                      advance_only: bool = True) -> CrmDeal:
    """Get-or-create the ONE open platform deal for a prospect club, advancing
    it towards ``stage_key``. ``advance_only`` (the default) never moves a
    deal BACKWARD — a fresh low-signal enquiry can't demote a deal that's
    already in Proposal. Value is priced from ``module_keys`` via the same
    ``billing_pricing.price_for()`` the Account page / Stripe Checkout use, so
    the pipeline's dollar figure is never a second, drifting estimate.

    A deal with ``stage_auto_locked`` set (a super admin has deliberately
    moved its stage by hand) is never auto-advanced — module_keys/value_cents
    still merge in, only the stage move is skipped."""
    pipeline = await ensure_platform_pipeline(session)
    stage_by_key = {s.key: s for s in pipeline.stages}
    target_stage = stage_by_key.get(stage_key)
    if target_stage is None:
        raise ValueError(f"Unknown platform pipeline stage key: {stage_key}")

    existing = (await session.execute(
        select(CrmDeal).where(
            CrmDeal.pipeline_id == pipeline.id,
            CrmDeal.marketing_club_id == club.id,
            CrmDeal.status == "open",
            CrmDeal.archived_at.is_(None),
        ).order_by(CrmDeal.created_at.desc())
    )).scalars().first()

    keys = sorted(set(module_keys or []))
    value_cents = int(round(price_for(keys)["total"] * 100)) if keys else 0

    if existing is None:
        deal = await create_deal(
            session, scope=SCOPE_PLATFORM, marketing_club_id=club.id,
            pipeline_id=pipeline.id, stage_id=target_stage.id, title=club.name,
            value_cents=value_cents, module_keys=keys, source=source,
        )
    else:
        deal = existing
        current_stage = stage_by_key.get(
            next((s.key for s in pipeline.stages if s.id == deal.stage_id), None))
        should_move = (not deal.stage_auto_locked and
                      (not advance_only or current_stage is None
                       or target_stage.position > current_stage.position))
        if should_move:
            await move_stage(session, deal, target_stage)
        deal.module_keys = sorted(set(deal.module_keys or []) | set(keys))
        if value_cents > (deal.value_cents or 0):
            deal.value_cents = value_cents
        deal.updated_at = func.now()

    if person_id:
        await link_deal_contact(session, deal.id, person_id)
    return deal


async def maybe_promote_by_engagement_score(session: AsyncSession, club: MarketingClub) -> Optional[CrmDeal]:
    """Promote a club's existing open platform deal per the super-admin-
    configured 'engagement_score' automation rules (services/crm_rules.py) —
    the threshold and target stage are no longer hardcoded. Never creates a
    deal from nothing (a score alone, with no deal on the board yet, isn't
    itself a reason to start one); never moves a deal backward (advance-only,
    via sync_platform_deal_for_club) or one with ``stage_auto_locked`` set.
    Caller is responsible for having already computed/cached
    ``club.engagement_score`` this call — this function does no scoring
    itself. A no-op (returns None) if every 'engagement_score' rule is
    disabled, or none is satisfied by the current score."""
    from app.services import crm_rules
    score = club.engagement_score
    if score is None:
        return None
    pipeline = await ensure_platform_pipeline(session)
    deal = (await session.execute(
        select(CrmDeal).where(
            CrmDeal.pipeline_id == pipeline.id,
            CrmDeal.marketing_club_id == club.id,
            CrmDeal.status == "open",
            CrmDeal.archived_at.is_(None),
        ).order_by(CrmDeal.created_at.desc())
    )).scalars().first()
    if deal is None or deal.stage_auto_locked:
        return None
    match = await crm_rules.resolve(session, pipeline, "engagement_score", score=score)
    if match is None:
        return None
    stage_by_key = {s.key: s for s in pipeline.stages}
    target_stage = stage_by_key[match["stage_key"]]
    current_stage = stage_by_key.get(next((s.key for s in pipeline.stages if s.id == deal.stage_id), None))
    should_move = (match["force"] or current_stage is None or target_stage.position > current_stage.position)
    if not should_move or target_stage.id == deal.stage_id:
        return None
    await move_stage(session, deal, target_stage)
    await log_activity(
        session, deal_id=deal.id, type="system",
        body=f"Auto-promoted to {target_stage.name}: engagement score {score} (rule: engagement_score)")
    return deal


async def sync_engagement_promotion(session: AsyncSession, club: MarketingClub,
                                    org: Optional[Organisation] = None) -> Optional[CrmDeal]:
    """Recompute one club's engagement score and immediately check the
    score-based Target/Contacted -> Engaged promotion, right now, in the
    caller's own session. ``twenty_sync._engagement`` is a pure local
    read/compute over our own tables (usage_events/email_events/etc) — it
    never calls out to Twenty — so this works whether or not Twenty is
    configured, unlike routing through ``push_club_and_contacts``. A
    single-club recompute is a handful of indexed queries, cheap enough to
    run inline wherever a real signal event already has a session+club in
    hand (an enquiry, a trial request/grant, a subscription change) rather
    than waiting for a scheduled sweep. Caller commits."""
    from app.services.twenty_sync import _engagement
    await _engagement(session, club, org)
    return await maybe_promote_by_engagement_score(session, club)


async def check_web_signal_promotion(*, org_id=None, utm_id=None, utm_source=None,
                                     path=None, email=None, user_id=None) -> dict:
    """Fully event-driven — fired directly from the write path of a web
    page-view/API event (usage_tracker.record_event) or an email open/click
    (ses_events), in place of any periodic sweep. No polling anywhere: this
    IS the check, run at the moment the signal happens.

    Two cheap gates before the real (pricier) engagement recompute ever
    runs, so this is safe to fire on a genuinely hot path:
      1. ``club_directory.resolve_marketing_club_id`` — does this event's
         org/utm/path/email even match a known prospect club? Most traffic
         (unrecognised visitors, an onboarded club's routine authenticated
         admin use once org_id resolves but see gate 2, a real customer's
         public fan traffic) resolves to nothing or is filtered right here.
      2. Does that club currently have an open, non-``stage_auto_locked``
         platform deal sitting at Target or Contacted? A single indexed
         query. A customer or trial club's deal is already past Engaged, so
         this is what actually filters out the high-volume authenticated
         traffic case gate 1's org_id match lets through.
    Only a club that clears BOTH gates pays for the full
    ``sync_engagement_promotion`` (the ``twenty_sync._engagement`` scan +
    the promotion check). Opens its own session; never raises — this must
    never be allowed to affect the request it was fired alongside."""
    if not (org_id or utm_id or utm_source or path or email):
        return {"skipped": "no signal"}
    from app.models.db import async_session_maker
    from app.services.club_directory import resolve_marketing_club_id
    try:
        async with async_session_maker() as session:
            club_id = await resolve_marketing_club_id(
                session, org_id=org_id, utm_id=utm_id, utm_source=utm_source,
                path=path, email=email, user_id=user_id)
            if club_id is None:
                return {"skipped": "no club match"}
            pipeline = await ensure_platform_pipeline(session)
            stage_ids = [s.id for s in pipeline.stages if s.key in ("target", "contacted")]
            if not stage_ids:
                return {"skipped": "no stages"}
            has_open = (await session.execute(
                select(CrmDeal.id).where(
                    CrmDeal.pipeline_id == pipeline.id, CrmDeal.marketing_club_id == club_id,
                    CrmDeal.status == "open", CrmDeal.archived_at.is_(None),
                    CrmDeal.stage_id.in_(stage_ids), CrmDeal.stage_auto_locked.is_(False),
                ).limit(1)
            )).scalar_one_or_none()
            if has_open is None:
                return {"skipped": "no early-stage deal"}
            club = await session.get(MarketingClub, club_id)
            if club is None:
                return {"skipped": "no club row"}
            org = (await session.get(
                        Organisation, club.existing_org_id,
                        options=[selectinload(Organisation.module_subscriptions)])
                   if club.existing_org_id else None)
            deal = await sync_engagement_promotion(session, club, org)
            await session.commit()
            return {"promoted": bool(deal)}
    except Exception:  # noqa: BLE001 - fired from a hot path, must never raise
        logger.exception("crm: web/email-signal promotion check failed")
        return {"error": "failed"}


async def sync_deal_for_enquiry(*, club_name: str, contact_name: str = "",
                                email: str = "", phone: Optional[str] = None) -> dict:
    """Backgrounded counterpart to ``twenty_sync.push_onboarding_enquiry`` — a
    direct 'onboard my club' enquiry (either the short CTA modal or the full
    Contact page) is the strongest buying signal a prospect can give, so it
    also ensures a platform deal exists (or advances an existing one).

    Per direct instruction, the enquiry COUNT decides the target stage: the
    first-ever Contact-Us submission from this club moves the deal straight
    to Contacted (a fresh deal is created there, never left sitting at
    Target); a second (or later) submission moves it on to Engaged. Reuses
    ``twenty_sync._onboarding_signal`` — the same email/visitor/club-name
    matching the engagement-score formula already counts this signal by — so
    "how many times has this club contacted us" can never drift from what the
    score itself already believes. The row this call is counting was already
    committed by ``routers/public_contact.py`` before this background task
    fires, so the just-submitted enquiry is included in the count. Opens its
    own session; never raises."""
    from app.models.db import async_session_maker
    from app.services.twenty_sync import _resolve_onboarding_club, _onboarding_signal
    try:
        async with async_session_maker() as session:
            club, contact = await _resolve_onboarding_club(
                session, club_name=club_name, contact_name=contact_name, email=email, phone=phone)
            if club is None:
                return {"skipped": "no club"}
            person = await resolve_person(
                session, marketing_club_id=club.id,
                full_name=contact_name or (contact.full_name if contact else "") or club_name,
                email=email, phone=phone)
            count, _last_at = await _onboarding_signal(session, club, club.utm_code)
            from app.services import crm_rules
            pipeline = await ensure_platform_pipeline(session)
            match = await crm_rules.resolve(session, pipeline, "enquiry_count", count=count)
            if match is None:
                # Every 'enquiry_count' rule is disabled (or none is satisfied
                # yet, e.g. only a count>=2 rule exists) — per the configured
                # criteria, this enquiry alone isn't reason enough to
                # create/advance a deal. The score-based check below still runs.
                deal = None
            else:
                deal = await sync_platform_deal_for_club(
                    session, club, stage_key=match["stage_key"], source="auto_enquiry",
                    person_id=person.id, advance_only=not match["force"])
            # This enquiry may itself be enough to push the (freshly recomputed)
            # engagement score over the threshold — check right now rather than
            # waiting for the sweep, in the same session/commit.
            org = (await session.get(Organisation, club.existing_org_id,
                                     options=[selectinload(Organisation.module_subscriptions)])
                   if club.existing_org_id else None)
            await sync_engagement_promotion(session, club, org)
            await session.commit()
            return {"deal_id": str(deal.id) if deal else None, "onboarding_request_count": count}
    except Exception:  # noqa: BLE001 - best-effort, mirrors push_onboarding_enquiry
        logger.exception("crm: failed to sync deal for enquiry (%s)", club_name)
        return {"error": "failed"}


# ─── Self-serve trial registration → local CRM deal ──────────────────────────
# A self-serve registration (routers/self_serve_trial.py's shared submit(), hit
# by both the super-admin-testing internal flow and the public /trial flow)
# starts a 14-day trial of every module the registrant picked, with no human
# in the loop — the same real signal push_self_serve_registration already
# gives Twenty. The local pipeline deserves the same treatment, independent of
# whether Twenty itself is configured.

# Domains from frontend/src/lib/visitor.js's CLICK_IDS ad-network table (only
# the ones this classifier distinguishes) plus common AI assistant/search
# referrers — used to bucket a registrant's first-touch acquisition into the
# deal detail modal's own Lead Source vocabulary (ui.jsx LEAD_SOURCE_OPTIONS).
_META_ADS_UTM_SOURCES = {"facebook", "meta", "fb", "instagram"}
_GOOGLE_REFERRER_HOSTS = ("google.com", "google.com.au", "google.co.")
_AI_ASSISTANT_REFERRER_HOSTS = (
    "chatgpt.com", "chat.openai.com", "perplexity.ai", "claude.ai",
    "gemini.google.com", "copilot.microsoft.com", "you.com",
)


def lead_source_from_attribution(attribution: Optional[dict]) -> Optional[str]:
    """Best-effort classification of a registrant's first-touch acquisition
    (frontend/src/lib/visitor.js getAttribution() — utm_source/utm_campaign/
    click_source/landing_referrer) into the deal's own lead_source vocabulary.
    Order matters — an EDM link's own utm_campaign wins over an ad-network
    click id it might also carry (e.g. an EDM link opened from inside a
    Facebook in-app browser). Returns None (leave "Not set") when nothing
    recognisable is present — never guesses "other" on no signal at all.
    Tolerant of an unclipped, client-supplied dict (this may run against the
    raw request body, not the allowlisted/clipped copy public_self_serve.py
    stores onto the org) — a non-string value for a known key is treated as
    absent rather than raising."""
    if not isinstance(attribution, dict):
        return None
    def _s(key: str) -> str:
        v = attribution.get(key)
        return v.strip().lower() if isinstance(v, str) else ""
    utm_campaign = _s("utm_campaign")
    utm_source = _s("utm_source")
    click_source = _s("click_source")
    referrer = _s("landing_referrer")

    if utm_campaign == "edm":
        return "edm"
    if click_source == "facebook" or utm_source in _META_ADS_UTM_SOURCES:
        return "meta_ads"
    if click_source == "google" or utm_source == "google" or any(h in referrer for h in _GOOGLE_REFERRER_HOSTS):
        return "google_search"
    if any(h in referrer for h in _AI_ASSISTANT_REFERRER_HOSTS):
        return "ai_search_assistants"
    return None


async def sync_self_serve_trial_deal(session: AsyncSession, club: MarketingClub, *,
                                     lead_source: Optional[str] = None) -> Optional[CrmDeal]:
    """Get-or-create the ONE open platform deal for a club that just completed
    self-serve trial registration, and pin it to what that registration always
    means: Trial stage, 'Self-Serve Trial' onboarding method, and BetterStats'
    own $399 base value. module_keys is deliberately left alone (empty on a
    fresh deal) rather than filled with every trialled module — the deal
    detail modal's own Product Interest chips already default an empty list to
    showing Stats selected (see crm_recalc_trial_deals.py's docstring for the
    same convention), and pricing every trialled module in would inflate Value
    ($) well past $399. A super admin (or the recalc script) can broaden
    Product Interest and reprice later once real analytics/trial usage backs
    it up.

    Per the super-admin-configured 'self_serve_signup' automation rule
    (services/crm_rules.py — seeded to force=True, matching the historical
    behaviour), this normally always wins even over a deal that's further
    along: a self-serve signup is real news, not a step backward. Delegates
    the actual create-or-advance to ``sync_platform_deal_for_club`` (passing
    ``advance_only=not match["force"]``) rather than moving the stage
    directly, so — unlike before this became configurable — a deal a super
    admin has deliberately ``stage_auto_locked`` is now respected here too,
    consistent with every other automatic trigger. ``lead_source`` is
    optional since only the public flow has first-touch ad attribution to
    derive one from (see lead_source_from_attribution) — pass None to leave
    it as-is. Returns None if the 'self_serve_signup' rule is disabled or its
    target stage doesn't exist."""
    from app.services import crm_rules
    pipeline = await ensure_platform_pipeline(session)
    match = await crm_rules.resolve(session, pipeline, "self_serve_signup")
    if match is None:
        return None
    deal = await sync_platform_deal_for_club(
        session, club, stage_key=match["stage_key"], source="self_serve_trial",
        advance_only=not match["force"])
    deal.onboarding_method = "self_serve_trial"
    if lead_source:
        deal.lead_source = lead_source
    if not deal.module_keys:
        deal.value_cents = value_from_modules(["core"])
    deal.updated_at = func.now()
    return deal


async def sync_self_serve_trial_registration(*, org_id, org_name: str, contact_name: str = "",
                                             email: str = "", phone: Optional[str] = None,
                                             attribution: Optional[dict] = None) -> dict:
    """Backgrounded counterpart to (and fired alongside)
    twenty_sync.push_self_serve_registration — creates/advances the ONE local
    BetterCRM platform deal for a brand-new self-serve trial registration.
    Deliberately independent of whether Twenty is configured (unlike the
    Twenty push, which no-ops entirely when it isn't): BetterCricket's own
    pipeline must reflect a real registration regardless of that external
    integration's state, so this resolves the MarketingClub itself rather than
    relying on the Twenty push having already done so. Opens its own session;
    never raises."""
    from app.models.db import async_session_maker
    from app.services.twenty_sync import _resolve_self_serve_club
    try:
        async with async_session_maker() as session:
            club, _contact = await _resolve_self_serve_club(
                session, org_id=org_id, org_name=org_name, contact_name=contact_name,
                email=email, phone=phone)
            deal = await sync_self_serve_trial_deal(
                session, club, lead_source=lead_source_from_attribution(attribution))
            await session.commit()
            return {"deal_id": str(deal.id)} if deal else {"skipped": "no trial stage"}
    except Exception:  # noqa: BLE001 - a CRM hiccup can't undo the registration that already committed
        logger.exception("crm: failed to sync self-serve trial deal for org %s", org_id)
        return {"error": "failed"}
