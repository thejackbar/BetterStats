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


async def ensure_platform_pipeline(session: AsyncSession) -> CrmPipeline:
    """Get-or-create BetterCricket's own sales pipeline. Exactly one always
    exists — unlike the club scope, this one is NOT optional."""
    stmt = select(CrmPipeline).options(selectinload(CrmPipeline.stages)).where(
        CrmPipeline.scope == SCOPE_PLATFORM, CrmPipeline.organisation_id.is_(None),
        CrmPipeline.is_default.is_(True))
    pipeline = (await session.execute(stmt)).scalars().first()
    if pipeline is not None:
        if await _reconcile_platform_stages(session, pipeline):
            await session.commit()
            await session.refresh(pipeline, attribute_names=["stages"])
        return pipeline
    pipeline = CrmPipeline(scope=SCOPE_PLATFORM, organisation_id=None, name="BetterCricket Sales", is_default=True)
    session.add(pipeline)
    await session.flush()
    for position, (key, name, prob, is_won, is_lost) in enumerate(PLATFORM_DEFAULT_STAGES):
        session.add(CrmStage(
            pipeline_id=pipeline.id, key=key, name=name, position=position,
            default_probability=prob, is_won=is_won, is_lost=is_lost,
        ))
    await session.flush()
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


async def recalc_product_interest(session: AsyncSession, deal: CrmDeal, club: Optional[MarketingClub]) -> CrmDeal:
    """Re-derive a platform deal's Product Interest (module_keys) from the
    linked club's tracked website visits (club_directory.club_visit_detail's
    ranked ``inferred_modules``), and recompute value_cents to match. Always
    switches the deal back to 'auto' — the counterpart to a super admin
    manually overriding a module chip (which sets 'manual'). A deal with no
    linked club, or a club with no tracked visits at all, falls back to
    ``['core']`` (never leaves module_keys empty)."""
    from app.services import club_directory
    inferred = ["core"]
    if club is not None:
        detail = await club_directory.club_visit_detail(session, club.id)
        if detail.get("inferred_modules"):
            inferred = detail["inferred_modules"]
    deal.module_keys = inferred
    deal.value_cents = value_from_modules(inferred)
    deal.product_interest_source = "auto"
    deal.updated_at = func.now()
    return deal


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
    club linked to an onboarded org with at least one currently-live module
    trial — batched (no N+1). Powers both the CRM card's per-module trial
    countdown and the "trial expiring between X and Y days" filter. A
    prospect that's never been onboarded (no existing_org_id) has no tracked
    trial_ends_at at all and is simply absent from the result."""
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
        days = max(0, (ends_at - now).days)
        out.setdefault(cid, {})[billing_key_for(module_key)] = days
    return out


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
    the pipeline's dollar figure is never a second, drifting estimate."""
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
        should_move = (not advance_only or current_stage is None
                      or target_stage.position > current_stage.position)
        if should_move:
            await move_stage(session, deal, target_stage)
        deal.module_keys = sorted(set(deal.module_keys or []) | set(keys))
        if value_cents > (deal.value_cents or 0):
            deal.value_cents = value_cents
        deal.updated_at = func.now()

    if person_id:
        await link_deal_contact(session, deal.id, person_id)
    return deal


async def sync_deal_for_enquiry(*, club_name: str, contact_name: str = "",
                                email: str = "", phone: Optional[str] = None) -> dict:
    """Backgrounded counterpart to ``twenty_sync.push_onboarding_enquiry`` — a
    direct 'onboard my club' enquiry (either the short CTA modal or the full
    Contact page) is the strongest buying signal a prospect can give, so it
    also ensures a New Lead platform deal exists (or advances an existing
    one). Opens its own session; never raises."""
    from app.models.db import async_session_maker
    from app.services.twenty_sync import _resolve_onboarding_club
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
            deal = await sync_platform_deal_for_club(
                session, club, stage_key="target", source="auto_enquiry", person_id=person.id)
            await session.commit()
            return {"deal_id": str(deal.id)}
    except Exception:  # noqa: BLE001 - best-effort, mirrors push_onboarding_enquiry
        logger.exception("crm: failed to sync deal for enquiry (%s)", club_name)
        return {"error": "failed"}
