"""Self-serve trial engagement scoring — how far an unpaid prospect club has
actually gone in setting BetterCricket up for itself, as opposed to merely
existing in the system. Feeds ``crm_sync._engagement()`` as a floor on top
of the ordinary web/email recency+frequency formula, feeding the club's cached
engagement score the CRM pipeline reads.

Every action scored here can be performed by BetterCricket staff acting on a
club's behalf (a Super Admin "acting as" the club) instead of the club's own
admin — per direct instruction, staff-performed setup is a materially weaker
signal of genuine club interest than the club doing it themselves, so it's
discounted (or, for the registration milestone itself, given a separate lower
flat value rather than a percentage of the club-admin figure).

Actor resolution has two layers:
  1. Org-level: does the club currently have a real primary club admin
     (``club_memberships.role='club_admin'`` + ``is_primary_admin``)? If not,
     EVERY action on this org scores as if a Super Admin performed it,
     regardless of what any specific audit trail says — there's no genuine
     club-side owner to attribute organic interest to. This is also what
     resolves the registration milestone itself: the authenticated `/onboard`
     route never attaches a ClubMembership when the caller is a Super Admin
     (see organisations.py::onboard_organisation), so "no primary admin"
     already identifies a staff-run registration with no new instrumentation.
  2. Per-action, only where an actual actor is on file: a merge
     (``audit_logs`` action merge_players/merge_grades — routers/admin.py)
     and the "Import historical stats" wizard step (``audit_logs`` action
     setup_wizard_step_done, target_id import_stats — see
     routers/onboarding_wizard.py::set_step). Every other point-scoring
     signal (Square/Xero connect, fee schedule, BetterSelect/BetterIQ/
     BetterFantasy setup, admin polish) has no actor trail today, so full
     credit is assumed for those as long as the org clears the org-level
     check above — Square/Xero specifically can't be done by anyone but the
     club anyway, since they're OAuth logins to the club's own live
     payment/accounting account.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import ClubMembership, OnboardingWizardState, Organisation

SUPER_ADMIN_ACTOR_FRACTION = 0.3

REGISTRATION_CLUB_ADMIN = 70
REGISTRATION_SUPER_ADMIN = 40
MERGE_BONUS = 10
IMPORT_STATS_BONUS = 15
MODULE_GROUP_BONUS = 2
MODULE_GROUP_CAP = 15
ADMIN_POLISH_BONUS = 2

# onboarding_wizard.py GROUPS step keys, grouped the same way the wizard
# itself groups them, for the "actively used a paid module during trial"
# bonus. Square/Xero/fee schedule/comms sender settings all live under the
# wizard's BetterAdmin group.
_MODULE_GROUPS = {
    "admin": {"square", "xero", "fee_schedule", "comms"},
    "select": {"fixtures", "squads", "assign_players", "self_serve", "nets"},
    "iq": {"iq_prewarm"},
    "fantasy": {"fantasy_season", "fantasy_pool"},
}
_POLISH_STEPS = {"branding", "sponsors", "invite_admin"}


async def org_has_primary_admin(session: AsyncSession, org_id) -> bool:
    row = await session.execute(
        select(ClubMembership.id).where(
            ClubMembership.club_id == org_id,
            ClubMembership.role == "club_admin",
            ClubMembership.is_primary_admin.is_(True),
        ).limit(1)
    )
    return row.first() is not None


async def _user_is_super_admin(session: AsyncSession, user_id) -> bool:
    """A user's OWN membership role — a Super Admin's home membership is
    always 'super_admin' regardless of which club they're currently acting
    as, so this correctly identifies staff even mid "acting as" a club."""
    if not user_id:
        return False
    row = await session.execute(
        select(ClubMembership.role).where(ClubMembership.user_id == user_id).limit(1)
    )
    return row.scalar_one_or_none() == "super_admin"


async def _last_actor(session: AsyncSession, org_id, actions: list) -> Optional[str]:
    """Most recent audit_logs user_id for any of ``actions`` against this org."""
    row = await session.execute(text(
        "SELECT user_id FROM audit_logs WHERE org_id = :org AND action = ANY(:actions) "
        "ORDER BY created_at DESC LIMIT 1"
    ), {"org": str(org_id), "actions": actions})
    return row.scalar_one_or_none()


async def _last_wizard_step_actor(session: AsyncSession, org_id, step_key: str) -> Optional[str]:
    """Most recent audit_logs user_id for a manual wizard-step completion
    (routers/onboarding_wizard.py::set_step logs action='setup_wizard_step_done',
    target_id=<step key>)."""
    row = await session.execute(text(
        "SELECT user_id FROM audit_logs WHERE org_id = :org "
        "AND action = 'setup_wizard_step_done' AND target_id = :step "
        "ORDER BY created_at DESC LIMIT 1"
    ), {"org": str(org_id), "step": step_key})
    return row.scalar_one_or_none()


async def trial_depth_score(session: AsyncSession, org: Organisation) -> dict:
    """The trial-depth rollup for ONE prospect org (never called for a paying
    customer — see crm_sync._engagement). Only meaningful for a club that
    actually exists in BetterCricket (has been onboarded/registered)."""
    has_primary = await org_has_primary_admin(session, org.id)

    async def credit(actor_user_id) -> float:
        if not has_primary:
            return SUPER_ADMIN_ACTOR_FRACTION
        if await _user_is_super_admin(session, actor_user_id):
            return SUPER_ADMIN_ACTOR_FRACTION
        return 1.0

    registration = REGISTRATION_CLUB_ADMIN if has_primary else REGISTRATION_SUPER_ADMIN

    state = await session.get(OnboardingWizardState, org.id)
    completed = set(state.completed_steps or []) if state else set()

    has_merge = (await session.execute(text(
        "SELECT EXISTS(SELECT 1 FROM merge_logs WHERE org_id = :org AND undone_at IS NULL) "
        "OR EXISTS(SELECT 1 FROM grade_merge_logs WHERE org_id = :org AND undone_at IS NULL)"
    ), {"org": str(org.id)})).scalar_one()
    merge_pts = 0
    if has_merge:
        merge_actor = await _last_actor(session, org.id, ["merge_players", "merge_grades"])
        merge_pts = round(MERGE_BONUS * await credit(merge_actor))

    import_pts = 0
    if "import_stats" in completed:
        import_actor = await _last_wizard_step_actor(session, org.id, "import_stats")
        import_pts = round(IMPORT_STATS_BONUS * await credit(import_actor))

    module_pts = 0
    for keys in _MODULE_GROUPS.values():
        if completed & keys:
            module_pts += round(MODULE_GROUP_BONUS * await credit(None))
    module_pts = min(module_pts, MODULE_GROUP_CAP)

    polish_pts = round(ADMIN_POLISH_BONUS * await credit(None)) if completed & _POLISH_STEPS else 0

    total = min(100, registration + merge_pts + import_pts + module_pts + polish_pts)
    return {
        "score": total,
        "hasPrimaryAdmin": has_primary,
        "_registrationPts": registration,
        "_mergePts": merge_pts,
        "_importStatsPts": import_pts,
        "_modulePts": module_pts,
        "_polishPts": polish_pts,
    }
