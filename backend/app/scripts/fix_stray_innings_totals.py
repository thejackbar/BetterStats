"""Clear the leftover total on a hand-entered game's own innings.

Reported off Hamilton Veterans' 23 Oct 2011 game: Portland and Mt Gambier both
showed 142/7 in 40 overs. The entry form only draws the opposition-total boxes
for an opposition innings, so a total typed while an innings was set to
"Opposition" stayed on the row after it was flipped to "Our innings", hidden,
and overrode our batters. The form no longer sends one (see
`_replace_game_children`); this repairs the games already stored that way.

The signature is narrow on purpose, because our own innings can legitimately
carry a total (a scorebook import records one) and a club's typing is not ours
to remove on a guess. A row is cleared only when ALL of these hold:

* it is one of OUR innings ("us") and carries a total;
* the same game's opposition innings carries the identical runs, wickets and
  overs, which two different sides essentially never do;
* our innings has batters listed, so a card exists to total from;
* those batters plus extras do not already come to that total (a tie that
  happens to match is left alone, since nothing is wrong with it).

Only the three total columns on that row are set to NULL. Nothing is deleted,
and each game gets an audit entry holding its before and after, so the change is
undone from the Audit tab like any other edit. Dry run by default:

    python -m app.scripts.fix_stray_innings_totals <org-id-or-slug|all> [--apply]
"""
from __future__ import annotations

import asyncio
import sys
import uuid

from sqlalchemy import select, text

from app.models.db import (
    ManualBattingInnings, ManualGame, ManualInnings, Organisation, async_session_maker,
)


def _extras(inn: ManualInnings):
    parts = [inn.byes, inn.leg_byes, inn.wides, inn.no_balls, inn.penalty]
    if any(p is not None for p in parts):
        return sum(p or 0 for p in parts)
    return inn.extras_total


def is_stray(ours: ManualInnings, theirs: list, batters_runs, has_batters: bool) -> bool:
    """Whether `ours` carries a copy of an opposition innings' total."""
    if ours.batting_side != "us" or ours.total_runs is None or not has_batters:
        return False
    if (batters_runs or 0) + (_extras(ours) or 0) == ours.total_runs:
        return False
    return any(
        t.batting_side == "opposition"
        and t.total_runs == ours.total_runs
        and t.total_wickets == ours.total_wickets
        and t.overs == ours.overs
        for t in theirs
    )


async def repair(org: str, apply: bool) -> list[dict]:
    from app.routers.manual_entries import _log_edit, _snapshot_manual_game

    found: list[dict] = []
    async with async_session_maker() as db:
        q = select(Organisation)
        if org != "all":
            org_id = (await db.execute(text(
                "SELECT id FROM organisations WHERE id::text = :o OR slug = :o"),
                {"o": org})).scalar()
            if org_id is None:
                raise SystemExit(f"no club matches {org!r}")
            q = q.where(Organisation.id == org_id)
        for club in (await db.execute(q)).scalars().all():
            games = (await db.execute(
                select(ManualGame).where(ManualGame.organisation_id == club.id)
            )).scalars().all()
            for game in games:
                rows = (await db.execute(
                    select(ManualInnings).where(ManualInnings.manual_game_id == game.id)
                )).scalars().all()
                if len(rows) < 2 or not any(r.batting_side == "us" and r.total_runs is not None for r in rows):
                    continue
                theirs = [r for r in rows if r.batting_side == "opposition"]
                bats = (await db.execute(
                    select(ManualBattingInnings).where(ManualBattingInnings.manual_game_id == game.id)
                )).scalars().all()
                stray = []
                for r in rows:
                    mine = [b for b in bats if (b.innings_number or 1) == r.innings_number and not b.did_not_bat]
                    if is_stray(r, theirs, sum(b.runs or 0 for b in mine), bool(mine)):
                        stray.append(r)
                if not stray:
                    continue
                before = await _snapshot_manual_game(db, game.id, club.id) if apply else None
                for r in stray:
                    found.append({
                        "club": club.name, "game_id": str(game.id),
                        "played_at": game.played_at.isoformat() if game.played_at else None,
                        "opposition": game.opposition, "innings": r.innings_number,
                        "was": f"{r.total_runs}/{r.total_wickets} in {r.overs} overs",
                    })
                    if apply:
                        r.total_runs = None
                        r.total_wickets = None
                        r.overs = None
                if apply:
                    await db.flush()
                    after = await _snapshot_manual_game(db, game.id, club.id)
                    await _log_edit(
                        db, org_id=club.id, user_id=None, action="update",
                        target_table="manual_games", target_id=str(game.id),
                        summary=("Cleared a leftover innings total on our own innings "
                                 f"({game.played_at or 'date unknown'}"
                                 + (f" vs {game.opposition}" if game.opposition else "") + ")"),
                        before=before, after=after,
                    )
        if apply:
            await db.commit()
        else:
            await db.rollback()
    return found


async def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply = "--apply" in sys.argv
    found = await repair(args[0] if args else "all", apply)
    for f in found:
        print(f"  {f['club']}: {f['played_at'] or 'undated'} vs {f['opposition'] or '?'} "
              f"(innings {f['innings']}, our innings carried {f['was']})")
    if not found:
        print("Nothing to clear.")
    elif apply:
        print(f"Cleared {len(found)} innings total(s).")
    else:
        print(f"{len(found)} innings total(s) would be cleared. Run again with --apply.")


if __name__ == "__main__":
    asyncio.run(main())
