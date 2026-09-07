"""Merge the duplicate players a CricketStatz import created before it matched
names properly.

The importer used to match a card's name against the club's roster by exact
spelling only. A club holds its players as "Quinsee, Brad" while CricketStatz
writes "Brad Quinsee", so it matched none of them and minted a second record
for every player the club already had — its leaderboard then listed the same
person twice, each with half a career.

The importer is fixed, but a re-run will not repair what is already there: it
finds its own row by the CricketStatz id before it ever looks at a name. This
merges each import-created row into the club's own record, through the SAME
`_merge_players_core` the Merge Duplicates screen uses — so every per-game
table is reassigned and the merge is undoable from that screen.

Only an EXACT match is merged, which is the shared matcher's own rule and
covers the middle-initial case ("Michael B. White" onto "White, Michael"). A
bare initial, or two of the club's records sharing a name, is left for a person
to decide — merging those on a guess puts one career onto another.

    python -m app.scripts.merge_cricketstatz_duplicates <org-id-or-slug|all>
    python -m app.scripts.merge_cricketstatz_duplicates all --apply

Dry run by default.
"""
from __future__ import annotations

import asyncio
import sys
import uuid

from sqlalchemy import select, text

from app.models.db import Organisation, User, async_session_maker
from app.services.import_ingest import match_players


async def _orgs(db, target: str) -> list[Organisation]:
    if target == "all":
        return list((await db.execute(
            select(Organisation).where(Organisation.archived_at.is_(None))
        )).scalars().all())
    try:
        one = await db.get(Organisation, uuid.UUID(target))
    except ValueError:
        one = (await db.execute(
            select(Organisation).where(Organisation.slug == target)
        )).scalars().first()
    return [one] if one else []


async def plan_for_org(db, org_id) -> list[tuple[str, str, str, str]]:
    """(keep_id, keep_name, remove_id, remove_name) for each safe merge."""
    rows = (await db.execute(text("""
        SELECT id, COALESCE(display_name_override, name) AS name,
               cricketstatz_player_id
          FROM players WHERE organisation_id = :org
    """), {"org": str(org_id)})).mappings().all()

    imported = [r for r in rows if r["cricketstatz_player_id"]]
    held = [(str(r["id"]), r["name"]) for r in rows if not r["cricketstatz_player_id"]]
    if not imported or not held:
        return []

    decisions = match_players([r["name"] for r in imported], held)
    plan: list[tuple[str, str, str, str]] = []
    for row in imported:
        d = decisions.get(row["name"]) or {}
        if d.get("status") != "exact" or not d.get("player_id"):
            continue
        # The club's own record is the one kept: it carries whatever else the
        # club has attached to that person — a photo, a squad, a committee role.
        plan.append((d["player_id"], d.get("matched_name") or "",
                     str(row["id"]), row["name"]))
    return plan


async def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    target = sys.argv[1]
    apply = "--apply" in sys.argv
    # Imported here, not at module scope: working out the plan is pure, and
    # pulling the router in would drag the whole auth stack with it.
    from app.routers.admin import _merge_players_core

    async with async_session_maker() as db:
        orgs = await _orgs(db, target)
        if not orgs:
            print(f"No club matching {target!r}.")
            return 1

        actor = (await db.execute(
            select(User).where(User.role == "super_admin").limit(1)
        )).scalars().first()

        total = 0
        for org in orgs:
            plan = await plan_for_org(db, org.id)
            if not plan:
                continue
            print(f"\n{org.name} — {len(plan)} duplicate(s) to merge")
            for keep_id, keep_name, remove_id, remove_name in plan:
                print(f"   {remove_name!r} → {keep_name!r}")
                if apply:
                    try:
                        await _merge_players_core(
                            db, uuid.UUID(keep_id), uuid.UUID(remove_id),
                            org.id, actor)
                        await db.commit()
                    except Exception as exc:      # one bad pair is not the run
                        await db.rollback()
                        print(f"      skipped: {exc}")
                        continue
            total += len(plan)

        print(f"\n{total} duplicate(s) {'merged' if apply else 'found'}"
              f"{'' if apply else ' — re-run with --apply to merge them'}.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
