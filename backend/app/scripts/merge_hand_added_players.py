"""Merge players a club typed in by hand into the synced record that appeared when they played.

The sync does this itself after every run (services/hand_added_merge.py); this is the
same rule run by hand, for a club that already has such pairs waiting, or to see what
the sync would do. Dry run by default: it lists each pair and changes nothing.

    python -m app.scripts.merge_hand_added_players <org-id-or-slug|all> [--apply]

A merge moves records and never deletes them, and each one is in the merge log, where
it can be undone.
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services import hand_added_merge


async def run(target: str, apply: bool) -> None:
    async with async_session_maker() as db:
        if target == "all":
            clubs = (await db.execute(text(
                "SELECT id, name FROM organisations WHERE is_active IS NOT FALSE ORDER BY name"))).all()
        else:
            clubs = (await db.execute(text(
                "SELECT id, name FROM organisations WHERE id::text = :o OR slug = :o"), {"o": target})).all()
    if not clubs:
        raise SystemExit(f"no club matches {target!r}")
    total = 0
    for club_id, name in clubs:
        res = await hand_added_merge.merge_pairs(club_id, apply=apply)
        if not res["found"]:
            continue
        print(f"\n{name}: {res['found']} pair(s)")
        for p in res["pairs"]:
            state = "merged" if p["merged"] else ("FAILED: " + p["error"] if "error" in p else "would merge")
            print(f"  {p['name']}: {p['remove']} -> {p['keep']}  [{state}]")
        total += res["merged"] if apply else res["found"]
    print(f"\n{'Merged' if apply else 'Dry run: would merge'} {total} pair(s)."
          + ("" if apply else " Run again with --apply."))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        raise SystemExit(__doc__)
    asyncio.run(run(args[0], "--apply" in sys.argv))
