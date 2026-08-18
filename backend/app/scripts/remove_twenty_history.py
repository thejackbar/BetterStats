"""Removes the Twenty-imported history entries the one-time pipeline
cutover backfill (``app.scripts.import_twenty_pipeline``) left on every
club's ``crm_activities`` timeline.

WHY THIS EXISTS
---------------
That backfill wrote two kinds of entry per club it touched: a "system"
line ("Imported from Twenty (...): stage=... (raw: ...)") recording where
the club sat in Twenty's old Opportunity/Lead board, and a "note" entry
per Twenty Opportunity note it pulled across. Both were a one-time
cutover record, not something a rep working the Sales Workspace's own
History/Notes wants to see mixed in with what THEY actually did — the
Sales Workspace drawer (``routers/sales_workspace.py::get_club``) no
longer shows either going forward (``services.sales_workspace.
list_activities_excluding_twenty``), but that only hides FUTURE reads;
this script clears out what the backfill already wrote.

WHAT IT DOES
------------
Deletes every ``crm_activities`` row whose ``meta`` carries a
``twenty_kind`` or ``twenty_note_id`` key -- the two markers
``import_twenty_pipeline.py`` always stamps, and nothing else in this
codebase writes. Platform-wide (not scoped to one org), since the backfill
ran across every club it could match. The CRM Pipeline board (routers/
crm.py) is unaffected by this filter change but WILL lose these rows from
its own activity feed too once they're deleted -- if that board's own
history of "what Twenty said" needs to be kept for reference, do NOT run
this with --apply; the display-side fix in get_club already keeps them out
of the Sales Workspace either way.

USAGE
-----
    python -m app.scripts.remove_twenty_history            # dry run
    python -m app.scripts.remove_twenty_history --apply
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from app.models.db import CrmActivity, async_session_maker

_META_KEYS = ("twenty_kind", "twenty_note_id")


def _is_twenty_imported(activity: CrmActivity) -> bool:
    meta = activity.meta or {}
    return any(k in meta for k in _META_KEYS)


async def run(apply: bool) -> int:
    async with async_session_maker() as db:
        rows = (await db.execute(select(CrmActivity))).scalars().all()
        targets = [a for a in rows if _is_twenty_imported(a)]

        system_count = sum(1 for a in targets if a.type == "system")
        note_count = sum(1 for a in targets if a.type == "note")
        other_count = len(targets) - system_count - note_count

        print(f"Found {len(targets)} Twenty-imported activity row(s): "
              f"{system_count} system, {note_count} note, {other_count} other.")
        for a in targets[:20]:
            print(f"  {a.type:8s} deal={a.deal_id} {(a.body or '')[:80]!r}")
        if len(targets) > 20:
            print(f"  … and {len(targets) - 20} more")

        if not apply:
            if targets:
                print("\nDRY RUN — nothing deleted. Re-run with --apply to remove these.")
            else:
                print("\nDRY RUN — nothing to remove.")
            return 0

        for a in targets:
            await db.delete(a)
        await db.commit()
        print(f"\nDone: {len(targets)} activity row(s) removed.")
        return 0


def main() -> int:
    apply = "--apply" in sys.argv[1:]
    return asyncio.run(run(apply))


if __name__ == "__main__":
    raise SystemExit(main())
