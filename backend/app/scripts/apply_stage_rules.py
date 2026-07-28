"""Reset the CRM stage-movement automation rules to the canonical set in
crm_rules.SEED_RULES.

WHY THIS EXISTS
    The automation rules (crm_automation_rules) are seeded into the DB ONCE, on
    first install, and a redeploy never overwrites them (so a super admin's edits
    survive). That means changing crm_rules.SEED_RULES in code does NOT change a
    live system. This one-off script force-applies the current SEED_RULES to the
    live rules, so the deployed pipeline behaves as configured in code.

WHAT THE CANONICAL SET DOES (per direct instruction)
    - Score > 0 auto-ENTERS a club at Target (crm.sync_pipeline_membership) — not a
      rule here. Score decaying to 0 auto-removes an untouched Target deal.
    - The score NEVER auto-advances a stage (no engagement_score rule).
    - Contacted is manual (we reached out, no reply). Engaged is two-way contact:
      manual for a conversation, or automatic when a club submits the contact form.
    - Trial is a genuine trial-start signal only: a trial request, a super admin
      starting a trial, or a self-serve signup.

    This REPLACES every existing automation rule (it deletes them first), so any
    hand-added custom rule is removed. That's intended — it's a deliberate reset
    to the code-defined policy.

    IT ALSO does a one-off cleanup of deals the RETIRED ``engagement_score`` rule
    had auto-promoted to Engaged: those get moved back to Target (Engaged now
    means a real two-way conversation only). A hand-moved (locked) Engaged deal,
    or one moved there by a contact-form enquiry, is left alone. See
    crm.reset_auto_promoted_engaged. Pass --no-reset to skip this and only reset
    the rules.

USAGE (inside the backend container)
    python -m app.scripts.apply_stage_rules            # apply
    python -m app.scripts.apply_stage_rules --dry-run  # show current vs new, change nothing
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import delete, select

from app.models.db import async_session_maker, CrmAutomationRule
from app.services import crm, crm_rules


def _fmt(r) -> str:
    p = f" {r.params}" if getattr(r, "params", None) else ""
    force = " (force)" if getattr(r, "force", False) else ""
    en = "" if getattr(r, "enabled", True) else " [disabled]"
    return f"{r.trigger}{p} -> {r.target_stage_key}{force}{en}  \"{r.label}\""


async def run(dry_run: bool, reset_engaged: bool) -> None:
    async with async_session_maker() as session:
        current = (await session.execute(
            select(CrmAutomationRule).order_by(CrmAutomationRule.trigger)
        )).scalars().all()
        print(f"Current rules ({len(current)}):")
        for r in current:
            print("   ", _fmt(r))

        print(f"\nNew canonical rules ({len(crm_rules.SEED_RULES)}):")
        for r in crm_rules.SEED_RULES:
            force = " (force)" if r.get("force") else ""
            p = f" {r['params']}" if r.get("params") else ""
            print(f"    {r['trigger']}{p} -> {r['target_stage_key']}{force}  \"{r['label']}\"")

        if dry_run:
            print("\nDRY RUN — no changes made.")
            return

        await session.execute(delete(CrmAutomationRule))
        for r in crm_rules.SEED_RULES:
            session.add(CrmAutomationRule(**r))
        await session.commit()
        print("\nApplied. The automation rules now match the canonical set above.")

        if reset_engaged:
            moved = await crm.reset_auto_promoted_engaged(session)
            await session.commit()
            print(f"Reset {moved} score-auto-promoted Engaged deal(s) back to Target.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Reset CRM stage-movement rules to the canonical set.")
    ap.add_argument("--dry-run", action="store_true", help="show current vs new, change nothing")
    ap.add_argument("--no-reset", action="store_true",
                    help="only reset the rules; skip moving score-auto-promoted Engaged deals back to Target")
    args = ap.parse_args()
    asyncio.run(run(args.dry_run, reset_engaged=not args.no_reset))


if __name__ == "__main__":
    main()
