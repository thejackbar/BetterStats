"""Configurable, persistent automation criteria for the PLATFORM CRM pipeline
(BetterCricket's own sales pipeline, services/crm.py's SCOPE_PLATFORM) — per
direct instruction, every criterion that decides (a) whether a deal gets
created at all and (b) which stage it gets promoted to must be editable and
durable, with a Super Admin surface to manage it, rather than hardcoded
thresholds/target stages scattered across the codebase.

One small, fixed vocabulary of TRIGGERS — these are genuine integration
points in the code (an enquiry lands, a score is recomputed, a trial starts,
a subscription changes) and can't themselves be made dynamic without
inventing an event bus this app doesn't have. What IS fully configurable per
trigger, via ``CrmAutomationRule`` rows (migration 190): the numeric
condition (an enquiry count / a score threshold), which stage it promotes to,
whether it forces the move (bypasses the normal never-move-backward
semantics), and whether it's enabled at all.

Evaluation (``resolve``): every ENABLED rule for a trigger whose condition is
satisfied is a candidate; the one whose target stage sits FURTHEST along the
pipeline wins. This one rule naturally handles a ladder of tiers (e.g. two
``enquiry_count`` rows at count=1/count=2, or several ``engagement_score``
rows at different thresholds) with no separate ordering field to keep in
sync — a higher-numbered condition that's also further along the pipeline
simply wins on its own. Disabling every rule for a trigger turns that
automation off entirely (no deal created/moved from it) — a deliberate,
supported way to switch a criterion off without deleting its configuration.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import CrmAutomationRule, CrmPipeline

logger = logging.getLogger(__name__)

# trigger key -> (display label, description, param key or None, param label)
# The ONE place a trigger's shape is described — the Super Admin UI mirrors
# this catalogue (frontend/src/components/admin/crm/automationTriggers.js)
# rather than inventing its own.
TRIGGERS: dict = {
    "enquiry_count": {
        "label": "Contact-Us enquiry count",
        "description": "A club submits the public Contact-Us / \"onboard my club\" form. "
                       "The rule with the highest count the running total has now reached wins.",
        "param_key": "count",
        "param_label": "Enquiry count reaches",
    },
    "engagement_score": {
        "label": "Engagement score threshold",
        "description": "A club's engagement score (web/email activity, recomputed on every "
                       "relevant event) exceeds a threshold.",
        "param_key": "threshold",
        "param_label": "Score exceeds",
    },
    "trial_requested": {
        "label": "Trial requested",
        "description": "A club (or its admin) asks for a module trial, before it's granted.",
        "param_key": None,
        "param_label": None,
    },
    "trial_started": {
        "label": "Trial started",
        "description": "A module trial actually begins (granted by a super admin, "
                       "approved from a request, or self-started by the club).",
        "param_key": None,
        "param_label": None,
    },
    "subscription_won": {
        "label": "Subscription won",
        "description": "A paid module subscription goes live (a subscribe request is "
                       "approved, or a Stripe checkout completes).",
        "param_key": None,
        "param_label": None,
    },
    "subscription_cancelled": {
        "label": "Subscription cancelled",
        "description": "Every billable module the club held has now been cancelled/lost "
                       "(a partial cancel — some modules still held — never fires this).",
        "param_key": None,
        "param_label": None,
    },
    "self_serve_signup": {
        "label": "Self-serve trial signup",
        "description": "A prospect completes the public self-serve trial registration "
                       "(/trial) with no human in the loop.",
        "param_key": None,
        "param_label": None,
    },
}

# The seed set — exactly mirrors what was hardcoded before this became
# configurable, so turning this feature on changes nothing until a super
# admin actually edits a rule. Only ever applied once (see seed_defaults) —
# a super admin's later edits/deletes are never overwritten by a redeploy.
# Stage-movement policy (per direct instruction):
#   - Target is where a club AUTO-ENTERS the moment its engagement score > 0
#     (crm.ensure_pipeline_entry) — that's a stage ENTRY, not a rule here.
#   - The score NEVER auto-advances a deal's stage — there is deliberately no
#     ``engagement_score`` rule. A club sits at Target until a real event or a
#     super admin moves it.
#   - Contacted and Engaged are reached by a super admin BY HAND, after an
#     actual conversation — so no rule targets them.
#   - The only automatic FORWARD move is to Trial, and only from a genuine
#     "starting" signal: a contact-form enquiry, a club requesting a trial, a
#     super admin starting one, or a self-serve signup.
SEED_RULES = [
    {"trigger": "enquiry_count", "label": "Contact-Us enquiry",
     "params": {"count": 1}, "target_stage_key": "trial", "force": False},
    {"trigger": "trial_requested", "label": "Trial requested",
     "params": {}, "target_stage_key": "trial", "force": False},
    {"trigger": "trial_started", "label": "Trial started",
     "params": {}, "target_stage_key": "trial", "force": False},
    {"trigger": "self_serve_signup", "label": "Self-serve trial signup",
     "params": {}, "target_stage_key": "trial", "force": True},
    {"trigger": "subscription_won", "label": "Subscription won",
     "params": {}, "target_stage_key": "won", "force": False},
    {"trigger": "subscription_cancelled", "label": "Subscription cancelled",
     "params": {}, "target_stage_key": "lost_dormant", "force": False},
]


async def seed_defaults(session: AsyncSession) -> bool:
    """Insert the seed rule set — but ONLY if the table is completely empty
    (a fresh install, or before this feature ever shipped) — so a super
    admin's later edits/deletes are never silently reintroduced by a
    redeploy. Returns whether anything was inserted. Caller commits."""
    existing = (await session.execute(select(CrmAutomationRule.id).limit(1))).scalar_one_or_none()
    if existing is not None:
        return False
    for r in SEED_RULES:
        session.add(CrmAutomationRule(**r))
    await session.flush()
    return True


async def list_rules(session: AsyncSession, *, trigger: Optional[str] = None) -> list[CrmAutomationRule]:
    stmt = select(CrmAutomationRule).order_by(CrmAutomationRule.trigger, CrmAutomationRule.created_at)
    if trigger:
        stmt = stmt.where(CrmAutomationRule.trigger == trigger)
    return (await session.execute(stmt)).scalars().all()


async def get_rule(session: AsyncSession, rule_id) -> Optional[CrmAutomationRule]:
    return await session.get(CrmAutomationRule, rule_id)


def _validate_trigger(trigger: str) -> None:
    if trigger not in TRIGGERS:
        raise ValueError(f"Unknown trigger: {trigger}")


def _clean_params(trigger: str, params: Optional[dict]) -> dict:
    """Only the trigger's own param_key (if any) is ever stored — an
    enquiry_count row can't carry a threshold, etc. A numeric param is
    required and must be a positive number when the trigger has one."""
    spec = TRIGGERS[trigger]
    key = spec["param_key"]
    if key is None:
        return {}
    if not isinstance(params, dict) or key not in params:
        raise ValueError(f"'{trigger}' rules require a numeric '{key}' parameter")
    try:
        value = float(params[key])
    except (TypeError, ValueError):
        raise ValueError(f"'{key}' must be a number")
    if key == "count":
        value = int(value)
        if value < 1:
            raise ValueError("count must be at least 1")
    return {key: value}


async def create_rule(session: AsyncSession, *, trigger: str, label: str, target_stage_key: str,
                      params: Optional[dict] = None, force: bool = False,
                      enabled: bool = True) -> CrmAutomationRule:
    _validate_trigger(trigger)
    if not (label or "").strip():
        raise ValueError("A rule needs a label")
    if not (target_stage_key or "").strip():
        raise ValueError("A rule needs a target stage")
    rule = CrmAutomationRule(
        trigger=trigger, label=label.strip()[:200], target_stage_key=target_stage_key.strip(),
        params=_clean_params(trigger, params), force=bool(force), enabled=bool(enabled),
    )
    session.add(rule)
    await session.flush()
    return rule


async def update_rule(session: AsyncSession, rule: CrmAutomationRule, **fields) -> CrmAutomationRule:
    if "label" in fields and fields["label"] is not None:
        rule.label = fields["label"].strip()[:200]
    if "target_stage_key" in fields and fields["target_stage_key"] is not None:
        rule.target_stage_key = fields["target_stage_key"].strip()
    if "force" in fields and fields["force"] is not None:
        rule.force = bool(fields["force"])
    if "enabled" in fields and fields["enabled"] is not None:
        rule.enabled = bool(fields["enabled"])
    if "params" in fields and fields["params"] is not None:
        rule.params = _clean_params(rule.trigger, fields["params"])
    rule.updated_at = func.now()
    return rule


async def delete_rule(session: AsyncSession, rule: CrmAutomationRule) -> None:
    """A real delete, not a soft one — a rule is pure configuration (no
    history/foreign keys hang off it), so there's nothing to preserve by
    keeping a disabled row around instead. Turning a criterion off without
    losing its configured numbers is what ``enabled=False`` is for."""
    await session.delete(rule)


def rule_dict(rule: CrmAutomationRule) -> dict:
    spec = TRIGGERS.get(rule.trigger, {})
    return {
        "id": str(rule.id),
        "trigger": rule.trigger,
        "trigger_label": spec.get("label", rule.trigger),
        "label": rule.label,
        "params": rule.params or {},
        "target_stage_key": rule.target_stage_key,
        "force": rule.force,
        "enabled": rule.enabled,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
        "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
    }


async def resolve(session: AsyncSession, pipeline: CrmPipeline, trigger: str, *,
                  count: Optional[int] = None, score: Optional[float] = None) -> Optional[dict]:
    """The evaluator every automatic trigger call site uses. Returns
    ``{"stage_key": ..., "force": ...}`` for the best (furthest-along)
    qualifying, enabled rule, or None if nothing qualifies (including: the
    trigger has no rules at all, every rule for it is disabled, or the
    trigger's target stage no longer exists in this pipeline — a rule
    pointing at a deleted/renamed stage harmlessly no-ops rather than
    erroring)."""
    stage_by_key = {s.key: s for s in pipeline.stages}
    rules = await list_rules(session, trigger=trigger)
    best = None  # (position, stage_key, force)
    for rule in rules:
        if not rule.enabled:
            continue
        params = rule.params or {}
        if trigger == "enquiry_count":
            if count is None or count < int(params.get("count", 1)):
                continue
        elif trigger == "engagement_score":
            if score is None or score <= float(params.get("threshold", 70)):
                continue
        stage = stage_by_key.get(rule.target_stage_key)
        if stage is None:
            logger.debug("crm_rules: rule %s targets missing stage %s", rule.id, rule.target_stage_key)
            continue
        if best is None or stage.position > best[0]:
            best = (stage.position, rule.target_stage_key, rule.force)
    if best is None:
        return None
    return {"stage_key": best[1], "force": best[2]}
