"""List players whose Fantasy points in a scored round no longer match the scorecards.

A scorecard finished, corrected or synced after its round was settled leaves a player
who played on 0 (or a stale figure). Read only by default: it prints, per scored
round, who now scores differently. With --apply it settles those rounds again (each
squad keeps the lineup it was settled with, and no free transfer is banked). The
nightly job already does this for rounds scored in the last fortnight.

    python -m app.scripts.fantasy_round_drift <org-id-or-slug> [--apply]
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from app.models.db import FantasyRound, FantasySeason, async_session_maker
from app.services import fantasy_engine


async def run(org: str, apply: bool) -> None:
    async with async_session_maker() as db:
        row = (await db.execute(text("SELECT id, name FROM organisations WHERE id::text = :o OR slug = :o"), {"o": org})).first()
        if row is None:
            raise SystemExit(f"no club matches {org!r}")
        club_id, name = row
        print(f"\n{name}")
        fs = (await db.execute(text(
            "SELECT id FROM fantasy_seasons WHERE organisation_id = :o ORDER BY season_year DESC LIMIT 1"), {"o": club_id})).scalar()
        if fs is None:
            print("  No fantasy season.")
            return
        fs = await db.get(FantasySeason, fs)
        rounds = (await db.execute(text(
            "SELECT id FROM fantasy_rounds WHERE fantasy_season_id = :f AND status = 'scored' ORDER BY round_number"), {"f": fs.id})).scalars().all()
        stale = []
        for rid in rounds:
            rnd = await db.get(FantasyRound, rid)
            drift = await fantasy_engine.round_drift(db, fs, rnd)
            if not drift:
                continue
            stale.append(rnd)
            print(f"  Round {rnd.round_number}: {len(drift)} player(s) score differently now")
            for d in drift:
                print(f"    {d['name']}: {d['stored']:g} -> {d['now']:g}")
        if not stale:
            print("  Every scored round matches its scorecards.")
            return
        if apply:
            for rnd in stale:
                await fantasy_engine.settle_round(db, fs, rnd)
            await db.commit()
            print(f"\nSettled {len(stale)} round(s) again.")
        else:
            await db.rollback()
            print(f"\nDry run: {len(stale)} round(s) would be settled again. Run again with --apply.")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit("usage: python -m app.scripts.fantasy_round_drift <org-id-or-slug> [--apply]")
    asyncio.run(run(args[0], "--apply" in sys.argv))
