"""Correct stored manual games whose winner contradicts their own result and scores.

The import and the hand-entry form now settle this as a game is written
(`services/manual_result.py`); this applies the same rule to games already in
the database. Reported off Hamilton Veterans' 7 Feb 2012 match: winner
Portland, result "Lost by 7 Runs", Portland 159 v Vic Country 166.

Only games whose winner and result line disagree are scored at all, and the
winner is changed only when the scores agree with the result line. Dry run by
default, per the house rule; every change is listed before it is made.

    python -m app.scripts.settle_manual_winners <org-id-or-slug|all> [--apply]
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select, text

from app.models.db import ManualGame, Organisation, async_session_maker
from app.services import manual_result


async def settle(org: str, apply: bool) -> list[dict]:
    changes: list[dict] = []
    async with async_session_maker() as db:
        q = select(Organisation)
        if org != "all":
            org_id = (await db.execute(text(
                "SELECT id FROM organisations WHERE id::text = :o OR slug = :o"),
                {"o": org})).scalar()
            if org_id is None:
                raise SystemExit(f"no club matches {org!r}")
            q = q.where(Organisation.id == org_id)
        clubs = (await db.execute(q)).scalars().all()
        for club in clubs:
            games = (await db.execute(
                select(ManualGame).where(ManualGame.organisation_id == club.id,
                                         ManualGame.winning_team.isnot(None),
                                         ManualGame.result.isnot(None))
            )).scalars().all()
            for game in games:
                change = await manual_result.settle_manual_game(db, game, club)
                if change:
                    change["club"] = club.name
                    changes.append(change)
        if apply:
            await db.commit()
        else:
            await db.rollback()
    return changes


async def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply = "--apply" in sys.argv
    changes = await settle(args[0] if args else "all", apply)
    for c in changes:
        print(f"  {c['club']}: {manual_result.describe(c)}")
    if not changes:
        print("Nothing to settle.")
    elif apply:
        print(f"Corrected {len(changes)} game(s).")
    else:
        print(f"{len(changes)} game(s) would be corrected. Run again with --apply.")


if __name__ == "__main__":
    asyncio.run(main())
