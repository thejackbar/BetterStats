"""Setup Wizard analytics (super-admin only).

Answers "are clubs actually getting through the Setup Wizard, and where do
they get stuck / skip / struggle?" across the whole platform. Reads STORED
wizard progress only — no auto-detection runs here, that's /flow's job when
an admin actually opens their own club's wizard. This keeps the page a cheap
read with no side effects, at the cost of slight staleness for a club that
hasn't reopened its wizard since last doing something detectable.

Only clubs that have genuinely opened the wizard at least once
(``first_opened_at`` — see onboarding_wizard.py's POST /opened) feed the
per-step and "currently stuck at" numbers. A club whose admin has simply
loaded other admin pages (which creates an empty onboarding_wizard_state row
via the /state poll, but touches nothing else) would otherwise read as
"stuck on step 1" for every step in the registry, drowning out the clubs
that are actually engaging with it.
"""
from collections import defaultdict
from statistics import mean

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.modules import org_entitled_modules
from app.models.db import OnboardingWizardState, Organisation, SyncRun, User, get_db
from app.routers.auth import require_super_admin
from app.routers.onboarding_wizard import GROUPS, _applicable_groups

router = APIRouter(prefix="/club-admin/super/wizard-analytics", tags=["wizard-analytics"])


@router.get("")
async def wizard_analytics(
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    orgs = (await db.execute(
        select(Organisation)
        .where(Organisation.archived_at.is_(None))
        .order_by(Organisation.name)
    )).scalars().all()
    org_ids = [o.id for o in orgs]

    states = (await db.execute(
        select(OnboardingWizardState).where(OnboardingWizardState.organisation_id.in_(org_ids))
    )).scalars().all() if org_ids else []
    state_by_org = {s.organisation_id: s for s in states}

    # Batched sync-ready check (one query for every club, instead of
    # onboarding_wizard.py's per-org _sync_ready — this page renders all of
    # them at once).
    sync_ready_orgs = set()
    if org_ids:
        rows = await db.execute(
            select(SyncRun.org_id).where(
                SyncRun.org_id.in_(org_ids),
                SyncRun.kind.in_(("org_full", "org_hard_refresh")),
                SyncRun.status == "success",
            ).distinct()
        )
        sync_ready_orgs = {r.org_id for r in rows}

    # Average days from first opening the wizard to actually completing each
    # step — from the audit trail (setup_wizard_step_done is logged once,
    # the first time a step is newly marked done; see set_step).
    avg_days_by_step: dict = {}
    if org_ids:
        rows = await db.execute(text("""
            SELECT al.target_id AS step_key,
                   AVG(EXTRACT(EPOCH FROM (al.created_at - ws.first_opened_at)) / 86400.0) AS avg_days,
                   COUNT(*) AS n
            FROM audit_logs al
            JOIN onboarding_wizard_state ws ON ws.organisation_id = al.org_id
            WHERE al.action = 'setup_wizard_step_done' AND ws.first_opened_at IS NOT NULL
            GROUP BY al.target_id
        """))
        avg_days_by_step = {r.step_key: (round(r.avg_days, 1) if r.avg_days is not None else None, r.n) for r in rows}

    step_counts = defaultdict(lambda: {"reached": 0, "done": 0, "skipped": 0})
    stuck_counts = defaultdict(int)
    clubs_payload = []
    clubs_engaged = 0
    clubs_all_done = 0
    clubs_blocked_on_sync = 0
    completion_pcts = []

    for o in orgs:
        state = state_by_org.get(o.id)
        engaged = bool(state and state.first_opened_at is not None)
        sync_ready = o.id in sync_ready_orgs

        row = {
            "organisation_id": str(o.id),
            "name": o.name,
            "slug": o.slug,
            "engaged": engaged,
            "sync_ready": sync_ready,
            "done": None, "total": None, "pct": None,
            "current_step_key": None, "current_step_title": None,
            "skipped_count": 0, "na_count": 0,
            "dismissed": bool(state and state.dismissed_at),
            "first_opened_at": state.first_opened_at.isoformat() if state and state.first_opened_at else None,
            "last_activity_at": state.updated_at.isoformat() if state and state.updated_at else None,
        }

        if engaged:
            clubs_engaged += 1
            completed = set(state.completed_steps or [])
            skipped = set(state.skipped_steps or [])
            na = set(state.na_steps or [])
            row["skipped_count"] = len(skipped)
            row["na_count"] = len(na)

            entitled = org_entitled_modules(o)
            current_step = None
            current_title = None
            club_total = 0
            club_done = 0
            for g in _applicable_groups(entitled):
                locked = bool(g.get("requires_sync")) and not sync_ready
                for s in g["steps"]:
                    key = s["key"]
                    done = key in completed
                    is_na = (not done) and key in na
                    is_skip = (not done) and (not is_na) and key in skipped
                    if is_na or locked:
                        continue  # not applicable, or not yet visible to the admin
                    club_total += 1
                    step_counts[key]["reached"] += 1
                    if done:
                        club_done += 1
                        step_counts[key]["done"] += 1
                    elif is_skip:
                        step_counts[key]["skipped"] += 1
                    elif current_step is None:
                        current_step = key
                        current_title = s["title"]

            row["done"], row["total"] = club_done, club_total
            row["pct"] = round(100 * club_done / club_total) if club_total else 100
            row["current_step_key"], row["current_step_title"] = current_step, current_title
            if current_step:
                stuck_counts[current_step] += 1
            if club_total and club_done == club_total:
                clubs_all_done += 1
            if club_total:
                completion_pcts.append(club_done / club_total)
            if not sync_ready:
                clubs_blocked_on_sync += 1

        clubs_payload.append(row)

    # Step metadata in registry order, independent of any one club's
    # entitlement filtering — every optional/vital/minutes flag lives here.
    step_meta = []
    for g in GROUPS:
        for s in g["steps"]:
            step_meta.append({
                "key": s["key"], "title": s["title"],
                "group_key": g["key"], "group_title": g["title"],
                "vital": bool(s.get("vital")), "optional": bool(s.get("optional")),
                "minutes": s.get("minutes"),
            })

    step_stats = []
    for m in step_meta:
        c = step_counts.get(m["key"], {"reached": 0, "done": 0, "skipped": 0})
        reached = c["reached"]
        avg_days, avg_days_n = avg_days_by_step.get(m["key"], (None, 0))
        stuck = stuck_counts.get(m["key"], 0)
        step_stats.append({
            **m,
            "reached": reached,
            "done": c["done"],
            "skipped": c["skipped"],
            "stuck": stuck,
            "done_pct": round(100 * c["done"] / reached) if reached else None,
            "skip_pct": round(100 * c["skipped"] / reached) if reached else None,
            "stuck_pct": round(100 * stuck / reached) if reached else None,
            "avg_days_to_done": avg_days,
            "avg_days_sample": avg_days_n,
        })

    return {
        "totals": {
            "clubs_total": len(orgs),
            "clubs_engaged": clubs_engaged,
            "clubs_never_opened": len(orgs) - clubs_engaged,
            "clubs_all_done": clubs_all_done,
            "clubs_blocked_on_sync": clubs_blocked_on_sync,
            "avg_completion_pct": round(100 * mean(completion_pcts)) if completion_pcts else None,
        },
        "steps": step_stats,
        "clubs": clubs_payload,
    }
