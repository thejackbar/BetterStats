"""Retroactively fix the em-dash subject lines already seeded into the
outreach org's Comms Templates rows before the subject text itself was
corrected in code.

WHY THIS EXISTS
---------------
services/sales_email.py's _SEED_SUBJECT (and the hardcoded fallback builder)
were edited to drop the em dash from three subjects and give 'custom' a real
default subject instead of a blank one — but seed_sales_templates only ever
INSERTs a row ON CONFLICT DO NOTHING, so an environment where these rows were
already seeded (any environment that had opened Sales Workspace's Send an
email before that code change shipped) kept the OLD subject text in its
comms_templates row. render_template reads that stored row FIRST, so a rep
loading "Email following voicemail" / "Trial information" / "Book a demo"
still saw the em dash, and 'custom' still opened on a blank subject, no
matter how the Python source read.

WHAT IT DOES
------------
For the outreach org's own comms_templates rows (name IN 'Email following
voicemail', 'Trial information', 'Book a demo', 'Custom sales rep email'):
updates the subject ONLY when it EXACTLY matches the specific old value this
change replaced. A row that doesn't match exactly — because a super admin
has since edited it, or it was never seeded, or it's already been fixed
(e.g. by re-running this script) — is reported and left alone. Never a
blanket overwrite.

USAGE
-----
    python -m app.scripts.fix_sales_email_subjects            # dry run
    python -m app.scripts.fix_sales_email_subjects --apply
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from app.models.db import CommsTemplate, async_session_maker
from app.services.marketing_org import get_outreach_org

# db_name -> (old subject this script may replace, new subject)
_FIXES = {
    "Email following voicemail": (
        "BetterCricket for {{club}} — following up",
        "BetterCricket for {{club}} - following up",
    ),
    "Trial information": (
        "Start your free BetterCricket trial — {{club}}",
        "Start your free BetterCricket trial - {{club}}",
    ),
    "Book a demo": (
        "Book a demo — BetterCricket for {{club}}",
        "Book a demo - BetterCricket for {{club}}",
    ),
    "Custom sales rep email": (
        "",
        "BetterCricket for {{club}}",
    ),
}


async def run(apply: bool) -> int:
    async with async_session_maker() as db:
        org = await get_outreach_org(db)
        if org is None:
            print("No outreach org is configured on this environment — nothing to fix.")
            return 0

        rows = (await db.execute(
            select(CommsTemplate).where(
                CommsTemplate.organisation_id == org.id,
                CommsTemplate.name.in_(_FIXES.keys()),
            )
        )).scalars().all()
        by_name = {r.name: r for r in rows}

        to_fix = []
        for name, (old, new) in _FIXES.items():
            row = by_name.get(name)
            if row is None:
                print(f"  SKIP  {name!r} — no row on this environment")
                continue
            if row.subject == new:
                print(f"  OK    {name!r} — already the new subject")
                continue
            if row.subject != old:
                print(f"  KEPT  {name!r} — subject doesn't match the expected old text "
                      f"(likely edited since); left alone: {row.subject!r}")
                continue
            to_fix.append((row, name, old, new))
            print(f"  FIX   {name!r}: {old!r} -> {new!r}")

        if not apply:
            if to_fix:
                print("\nDRY RUN — nothing changed. Re-run with --apply to make these changes.")
            else:
                print("\nDRY RUN — nothing to change.")
            return 0

        for row, name, old, new in to_fix:
            row.subject = new
        await db.commit()
        print(f"\nDone: {len(to_fix)} subject(s) fixed.")
        return 0


def main() -> int:
    apply = "--apply" in sys.argv[1:]
    return asyncio.run(run(apply))


if __name__ == "__main__":
    raise SystemExit(main())
