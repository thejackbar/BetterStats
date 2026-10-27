"""Write (or preview) a club's automatic premiership honours from its grand-final scorecards.

The sync does this after every run (services/premierships.maybe_reconcile). This is the same thing on
demand, with a dry run first. It adds honours, links hand-typed ones to their scorecard, and removes
only an honour it wrote itself that no longer holds (a corrected result). Database only: no call to
Cricket Australia.

    python -m app.scripts.sync_premierships <org-id-or-slug>            # dry run
    python -m app.scripts.sync_premierships <org-id-or-slug> --apply
    python -m app.scripts.sync_premierships all --apply
"""
from __future__ import annotations

import asyncio
import sys
import uuid

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services import premierships


async def run(org_ref: str, apply: bool) -> int:
    async with async_session_maker() as db:
        if org_ref.lower() == "all":
            clubs = (await db.execute(text(
                "SELECT id, name FROM organisations WHERE archived_at IS NULL ORDER BY name"))).mappings().all()
        else:
            try:
                where, param = "id = CAST(:r AS UUID)", str(uuid.UUID(org_ref))
            except ValueError:
                where, param = "LOWER(slug) = LOWER(:r)", org_ref
            clubs = (await db.execute(text(f"SELECT id, name FROM organisations WHERE {where}"),
                                      {"r": param})).mappings().all()
        if not clubs:
            print(f"No club found for {org_ref!r}.")
            return 1
        for c in clubs:
            try:
                rep = await premierships.reconcile(db, c["id"], apply=apply)
            except Exception as e:
                await db.rollback()
                print(f"! {c['name']}: {e}")
                continue
            if not rep.get("wins") and not rep.get("delete") and not rep.get("unresolved"):
                continue
            print(f"\n{c['name']}: " + ", ".join(
                f"{k}={v}" for k, v in rep.items() if k not in ("preview", "unresolved")))
            for u in rep.get("unresolved", []):
                print(f"   no winner on the card: {u['played_at']} {u['grade_name']} v {u['opponent']}")
        if not apply:
            print("\nDry run — re-run with --apply to write.")
        return 0


def main() -> None:
    args = sys.argv[1:]
    apply = "--apply" in args
    pos = [a for a in args if not a.startswith("--")]
    if not pos:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(asyncio.run(run(pos[0], apply)))


if __name__ == "__main__":
    main()
