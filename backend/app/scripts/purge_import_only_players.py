"""Find (and delete) empty player records a historical stats import left behind.

WHY THESE EXIST
---------------
BetterImport's commit mints a real ``players`` row for every "add as new
player" name in an uploaded sheet, but undoing the batch used to leave those
rows in place — with the imported stats gone, a mis-mapped upload (e.g. a
column of bare surnames read as player names) left dozens of empty,
surname-only records clogging the club's Players page.

The cause is fixed: players carry ``import_batch_id`` (migration 234) and the
undo now deletes the ones it leaves empty. This script clears what an EARLIER
batch already left behind — those players carry no marker, so the only honest
signal left is emptiness itself.

WHAT IT TOUCHES
---------------
Only players in the named club who have never been synced (``grassroots_id``
and ``playhq_id`` both NULL — a synced player is never a candidate, whatever
else looks empty) AND who come back deletable from the same
``services/import_cleanup.deletable_players`` check the undo endpoints use:
no stats rows from any source, no membership, no votes, no lineup, no edited
profile. Anything attached is REPORTED and left alone — the record may be
wrong, but something real is hanging off it and a person should decide.

A hand-added player with genuinely nothing recorded yet is indistinguishable
from import residue by data alone, which is why this is dry-run by default
and scoped to one club: read the list before you ``--apply``.

USAGE
-----
    python -m app.scripts.purge_import_only_players <org-id-or-slug>           # dry run
    python -m app.scripts.purge_import_only_players <org-id-or-slug> --apply
"""
from __future__ import annotations

import asyncio
import sys
import uuid

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services import import_cleanup as cleanup


async def run(org_ref: str, apply: bool) -> int:
    async with async_session_maker() as db:
        try:
            org_id = str(uuid.UUID(org_ref))
            org_where, param = "id = CAST(:ref AS UUID)", org_id
        except ValueError:
            org_where, param = "LOWER(slug) = LOWER(:ref)", org_ref
        org = (await db.execute(
            text(f"SELECT id, name FROM organisations WHERE {org_where}"),
            {"ref": param},
        )).mappings().first()
        if not org:
            print(f"No club found for {org_ref!r} (pass an organisation id or public slug).")
            return 1

        candidates = (await db.execute(
            text("""
                SELECT id, name FROM players
                WHERE organisation_id = :org
                  AND grassroots_id IS NULL AND playhq_id IS NULL
                ORDER BY name
            """),
            {"org": str(org["id"])},
        )).mappings().all()
        if not candidates:
            print(f"{org['name']}: no never-synced players at all. Nothing to do.")
            return 0

        name_by_pid = {c["id"]: c["name"] for c in candidates}
        deletable, kept = await cleanup.deletable_players(db, org["id"], list(name_by_pid))

        print(f"{org['name']} — {len(candidates)} never-synced player(s) checked")
        if deletable:
            print(f"\n{len(deletable)} empty record(s) {'deleted' if apply else 'to delete'}:")
            for pid in sorted(deletable, key=lambda p: name_by_pid[p].lower()):
                print(f"  {'DELETE' if apply else 'would delete'}  {name_by_pid[pid]}")
            if apply:
                n = await cleanup.delete_players(db, org["id"], deletable)
                await db.commit()
                print(f"\n{n} player record(s) deleted.")
            else:
                print("\nDRY RUN — nothing changed. Re-run with --apply to delete these.")
        else:
            print("\nNo empty records found — every never-synced player has something attached.")

        if kept:
            print(f"\n{len(kept)} player(s) left alone because something is attached:")
            for pid, why in sorted(kept.items(), key=lambda kv: name_by_pid[kv[0]].lower()):
                print(f"  KEPT  {name_by_pid[pid]:<30} — {', '.join(why)}")
            print("Decide these by hand if any of them are import residue after all.")
        return 0


def main() -> int:
    args = sys.argv[1:]
    apply = "--apply" in args
    positional = [a for a in args if not a.startswith("--")]
    if not positional:
        print(__doc__)
        return 1
    return asyncio.run(run(positional[0], apply))


if __name__ == "__main__":
    raise SystemExit(main())
