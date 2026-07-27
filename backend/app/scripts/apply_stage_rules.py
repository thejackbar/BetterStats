"""Reset the CRM stage-movement automation rules to the canonical set in
crm_rules.SEED_RULES.

WHY THIS EXISTS
    The automation rules (crm_automation_rules) are seeded into the DB ONCE, on
    first install, and a redeploy never overwrites them (so a super admin's edits
    survive). That means changing crm_rules.SEED_RULES in code does NOT change a
    live system. This one-off script force-applies the current SEED_RULES to the
    live rules, so the deployed pipeline behaves as configured in code.

WHAT THE CANONICAL SET DOES (per direct instruction)
    - Score > 0 auto-ENTERS a club at Target (crm.ensure_pipeline_entry) — not a
      rule here.
    - The score NEVER auto-advances a stage (no engagement_score rule).
    - Contacted / Engaged are moved to BY HAND by a super admin after a real
      conversation — no rule targets them.
    - The only automatic forward move is to Trial, from a genuine start signal:
      a contact-form enquiry, a trial request, a super admin starting a trial,
      or a self-serve signup.

    This REPLACES every existing automation rule (it deletes them first), so any
    hand-added custom rule is removed. That's intended — it's a deliberate reset
    to the code-defined policy. It does NOT move any existing deal; deals already
    sitting at a stage stay put (a super admin can move a wrongly-auto-Engaged
    deal back by hand).

USAGE (inside the backend container)
    python -m app.scripts.apply_stage_rules            # apply
    python -m app.scripts.apply_stage_rules --dry-run  # show current vs new, change nothing
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import delete, select

from app.models.db import async_session_maker, CrmAutomationRule
from app.services import crm_rules


def _fmt(r) -> str:
    p = f" {r.params}" if getattr(r, "params", None) else ""
    force = " (force)" if getattr(r, "force", False) else ""
    en = "" if getattr(r, "enabled", True) else " [disabled]"
    return f"{r.trigger}{p} -> {r.target_stage_key}{force}{en}  \"{r.label}\""


async def run(dry_run: bool) -> None:
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


def main() -> None:
    ap = argparse.ArgumentParser(description="Reset CRM stage-movement rules to the canonical set.")
    ap.add_argument("--dry-run", action="store_true", help="show current vs new, change nothing")
    args = ap.parse_args()
    asyncio.run(run(args.dry_run))


if __name__ == "__main__":
    main()
