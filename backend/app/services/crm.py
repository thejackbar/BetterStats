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
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.db import (
    CrmPerson, CrmPersonRole, CrmPipeline, CrmStage, CrmDeal, CrmDealContact, CrmActivity,
    MarketingClub,
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

# (key, name, default_probability, is_won, is_lost)
PLATFORM_DEFAULT_STAGES = [
    ("new_lead", "New Lead", 10, False, False),
    ("contacted", "Contacted", 20, False, False),
    ("qualified", "Qualified", 35, False, False),
    ("trial", "Trial", 55, False, False),
    ("proposal", "Proposal", 70, False, False),
    ("negotiation", "Negotiation", 85, False, False),
    ("won", "Won", 100, True, False),
    ("lost", "Lost", 0, False, True),
]

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

async def ensure_platform_pipeline(session: AsyncSession) -> CrmPipeline:
    """Get-or-create BetterCricket's own sales pipeline. Exactly one always
    exists — unlike the club scope, this one is NOT optional."""
    stmt = select(CrmPipeline).options(selectinload(CrmPipeline.stages)).where(
        CrmPipeline.scope == SCOPE_PLATFORM, CrmPipeline.organisation_id.is_(None),
        CrmPipeline.is_default.is_(True))
    pipeline = (await session.execute(stmt)).scalars().first()
    if pipeline is not None:
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
                    default_probability: int = 0, is_won: bool = False, is_lost: bool = False) -> CrmStage:
    base = _slug(name)
    existing_keys = {s.key for s in pipeline.stages}
    key, n = base, 2
    while key in existing_keys:
        key = f"{base}_{n}"
        n += 1
    stage = CrmStage(
        pipeline_id=pipeline.id, key=key, name=(name or "New stage")[:80], position=len(pipeline.stages),
        default_probability=max(0, min(100, int(default_probability or 0))), is_won=is_won, is_lost=is_lost,
    )
    session.add(stage)
    await session.flush()
    return stage


async def update_stage(session: AsyncSession, stage: CrmStage, **fields) -> CrmStage:
    for f in ("name", "default_probability", "is_won", "is_lost", "position"):
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
         "default_probability": s.default_probability, "is_won": s.is_won, "is_lost": s.is_lost}
        for s in pipeline.stages
    ]


def _effective_probability(deal: CrmDeal, stage: Optional[CrmStage]) -> Optional[int]:
    if deal.probability is not None:
        return deal.probability
    return stage.default_probability if stage else None


def _deal_dict(deal: CrmDeal, stage: Optional[CrmStage] = None) -> dict:
    eff = _effective_probability(deal, stage)
    return {
        "id": str(deal.id),
        "scope": deal.scope,
        "organisation_id": str(deal.organisation_id) if deal.organisation_id else None,
        "marketing_club_id": str(deal.marketing_club_id) if deal.marketing_club_id else None,
        "pipeline_id": str(deal.pipeline_id),
        "stage_id": str(deal.stage_id),
        "stage_key": stage.key if stage else None,
        "stage_name": stage.name if stage else None,
        "title": deal.title,
        "value_cents": deal.value_cents,
        "currency": deal.currency,
        "probability": deal.probability,
        "effective_probability": eff,
        "weighted_value_cents": round(deal.value_cents * eff / 100) if eff is not None else None,
        "module_keys": deal.module_keys or [],
        "expected_close_date": deal.expected_close_date.isoformat() if deal.expected_close_date else None,
        "status": deal.status,
        "lost_reason": deal.lost_reason,
        "owner_user_id": str(deal.owner_user_id) if deal.owner_user_id else None,
        "source": deal.source,
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


def pipeline_board(pipeline: CrmPipeline, deals: list[CrmDeal]) -> dict:
    """Stages with their open deals + weighted value per stage and overall —
    the Kanban board's shape, computed from an already-loaded pipeline
    (stages) and its (non-archived) deals. Pure/sync: callers fetch both."""
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
            deals_out.append(_deal_dict(d, stage))
            if d.status == "open":
                eff = _effective_probability(d, stage) or 0
                stage_value += d.value_cents
                stage_weighted += round(d.value_cents * eff / 100)
                total_open_count += 1
        total_open_value += stage_value
        total_weighted += stage_weighted
        stages_out.append({
            "id": str(stage.id), "key": stage.key, "name": stage.name,
            "position": stage.position, "default_probability": stage.default_probability,
            "is_won": stage.is_won, "is_lost": stage.is_lost,
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


async def create_deal(session: AsyncSession, *, scope: str, pipeline_id, stage_id,
                      title: str, organisation_id=None, marketing_club_id=None,
                      value_cents: int = 0, currency: str = "AUD",
                      probability: Optional[int] = None, module_keys=None,
                      expected_close_date=None, owner_user_id=None,
                      source: str = "manual") -> CrmDeal:
    deal = CrmDeal(
        scope=scope, organisation_id=organisation_id, marketing_club_id=marketing_club_id,
        pipeline_id=pipeline_id, stage_id=stage_id, title=(title or "Untitled deal")[:300],
        value_cents=max(0, int(value_cents or 0)), currency=currency or "AUD",
        probability=probability, module_keys=list(module_keys or []),
        expected_close_date=expected_close_date, owner_user_id=owner_user_id, source=source,
    )
    session.add(deal)
    await session.flush()
    return deal


async def update_deal(session: AsyncSession, deal: CrmDeal, **fields) -> CrmDeal:
    for key in ("title", "value_cents", "currency", "probability", "module_keys",
                "expected_close_date", "owner_user_id"):
        if key in fields and fields[key] is not None:
            setattr(deal, key, fields[key])
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


# ─── People / contacts ───────────────────────────────────────────────────────

async def resolve_person(session: AsyncSession, *, full_name: str, organisation_id=None,
                         marketing_club_id=None, email: Optional[str] = None,
                         phone: Optional[str] = None) -> CrmPerson:
    """Find-or-create a Person scoped to a club (or a prospect marketing club),
    deduped by email first, else an exact case-insensitive name match. Fills
    gaps on an existing match; never overwrites a value already on file."""
    email_l = (email or "").strip().lower() or None
    stmt = select(CrmPerson)
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


async def list_deal_contacts(session: AsyncSession, deal_id) -> list[dict]:
    rows = (await session.execute(
        select(CrmDealContact, CrmPerson).join(CrmPerson, CrmPerson.id == CrmDealContact.person_id)
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
                session, club, stage_key="new_lead", source="auto_enquiry", person_id=person.id)
            await session.commit()
            return {"deal_id": str(deal.id)}
    except Exception:  # noqa: BLE001 - best-effort, mirrors push_onboarding_enquiry
        logger.exception("crm: failed to sync deal for enquiry (%s)", club_name)
        return {"error": "failed"}
