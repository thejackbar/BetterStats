"""Club onboarding wizard — see docs/self-serve-trial-onboarding-plan.md,
Phase 15. This router only tracks progress and computes which steps
currently apply; every step points at an existing admin tool (branding,
invite admin, module home pages, historical stats/honours import, grade
merge) rather than duplicating any of them.

Gated behind the ``onboarding_wizard_enabled`` platform flag
(``require_onboarding_wizard_enabled`` — 404s when off) plus ordinary
club-admin auth. No special capability is required beyond having a
membership on the club — onboarding guidance isn't privileged information,
any admin on the club should see the same progress.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.auth.modules import org_entitled_modules
from app.models.db import OnboardingWizardState, Organisation, SyncRun, get_db
from app.routers.auth import get_current_club, require_onboarding_wizard_enabled

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/club-admin/onboarding-wizard", tags=["onboarding-wizard"],
    dependencies=[Depends(require_onboarding_wizard_enabled)],
)

# (key, title, route, module) — module=None means always shown (core is
# always on). Sync-dependent steps (Decision 11) are appended only once the
# club's first full sync has completed successfully — the exact three named
# in the plan: Import Historical Stats, Import Honours, Merge Grades. Every
# route below is an existing admin tool; this wizard is a guided pointer at
# them, not a new implementation of any of them.
_BASE_STEPS = [
    {"key": "branding", "title": "Set your club colours & logo", "route": "/admin/settings", "module": None},
    {"key": "invite_admin", "title": "Invite another admin", "route": "/admin/users", "module": None},
    {"key": "explore_select", "title": "Explore BetterSelect", "route": "/admin/betterselect", "module": "select"},
    {"key": "explore_socials", "title": "Explore BetterSocials", "route": "/admin/bettersocials", "module": "socials"},
    {"key": "explore_admin", "title": "Explore BetterAdmin", "route": "/admin/betteradmin", "module": "admin"},
    {"key": "explore_iq", "title": "Explore BetterIQ", "route": "/admin/betteriq", "module": "iq"},
    {"key": "explore_fantasy", "title": "Explore BetterFantasyCricket", "route": "/admin/fantasy", "module": "fantasy"},
]
_SYNC_STEPS = [
    {"key": "import_stats", "title": "Import historical stats (not covered by PlayHQ/Grassroots)",
     "route": "/admin/import", "module": None},
    {"key": "import_honours", "title": "Import historical honours & awards",
     "route": "/admin/awards", "module": None},
    {"key": "merge_grades", "title": "Merge any duplicate grades", "route": "/admin/grades", "module": None},
]


async def _get_or_create_state(db: AsyncSession, org_id) -> OnboardingWizardState:
    state = await db.get(OnboardingWizardState, org_id)
    if state is None:
        state = OnboardingWizardState(organisation_id=org_id, completed_steps=[])
        db.add(state)
        await db.flush()
    return state


async def _sync_ready(db: AsyncSession, org_id) -> bool:
    """The club's first full historical sync (kind='org_full', the same kind
    self_serve_trial.py's /submit and the ordinary 'Sync Now' button both
    kick off) has completed successfully at least once."""
    row = await db.execute(
        select(SyncRun.status).where(SyncRun.org_id == org_id, SyncRun.kind == "org_full")
        .order_by(SyncRun.started_at.desc()).limit(1)
    )
    return row.scalar_one_or_none() == "success"


def _build_steps(entitled: set, sync_ready: bool, completed: list) -> list:
    steps = []
    for s in _BASE_STEPS:
        if s["module"] and s["module"] not in entitled:
            continue
        steps.append({**s, "done": s["key"] in completed})
    if sync_ready:
        for s in _SYNC_STEPS:
            steps.append({**s, "done": s["key"] in completed})
    return steps


class StepUpdate(BaseModel):
    done: bool = True


@router.get("/state")
async def get_state(club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    state = await _get_or_create_state(db, club.id)
    await db.commit()
    sync_ready = await _sync_ready(db, club.id)
    entitled = org_entitled_modules(club)
    steps = _build_steps(entitled, sync_ready, state.completed_steps or [])
    all_done = bool(steps) and all(s["done"] for s in steps)
    # Auto-open whenever nothing has been explicitly dismissed yet, OR the
    # sync-dependent steps just became available and haven't been shown once
    # yet (Decision 11's "reopens automatically... if not already open") —
    # gated on there being anything left to do at all, so a club that's
    # finished every step doesn't keep popping the wizard open regardless.
    should_auto_open = (not all_done) and (
        state.dismissed_at is None
        or (sync_ready and state.sync_steps_shown_at is None)
    )
    return {
        "steps": steps,
        "sync_ready": sync_ready,
        "all_done": all_done,
        "should_auto_open": bool(should_auto_open),
        "dismissed": state.dismissed_at is not None,
    }


@router.post("/opened")
async def mark_opened(club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    """Call the moment the wizard modal becomes visible (auto- or manually-
    opened). Stamps ``sync_steps_shown_at`` the first time this happens while
    the sync-dependent steps are available — the one-time trigger that stops
    the auto-reopen from firing more than once for the same sync
    completion."""
    state = await _get_or_create_state(db, club.id)
    if await _sync_ready(db, club.id) and state.sync_steps_shown_at is None:
        state.sync_steps_shown_at = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": True}


@router.post("/dismiss")
async def dismiss(club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    state = await _get_or_create_state(db, club.id)
    state.dismissed_at = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": True}


@router.post("/steps/{step_key}")
async def set_step(step_key: str, data: StepUpdate, club: Organisation = Depends(get_current_club),
                   db: AsyncSession = Depends(get_db)):
    state = await _get_or_create_state(db, club.id)
    completed = set(state.completed_steps or [])
    if data.done:
        completed.add(step_key)
    else:
        completed.discard(step_key)
    state.completed_steps = sorted(completed)
    flag_modified(state, "completed_steps")
    await db.commit()
    return {"ok": True, "completed_steps": state.completed_steps}
