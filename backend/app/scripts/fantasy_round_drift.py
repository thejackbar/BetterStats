"""List players whose Fantasy points in a scored round no longer match the scorecards.

A scorecard finished, corrected or synced after its round was settled leaves a player
who played on 0 (or a stale figure). Read only by default: it prints, per scored
round, who now scores differently. With --apply it settles those rounds again (each
squad keeps the lineup it was settled with, and no free transfer is banked). The
nightly job already does this for rounds scored in the last fortnight.

    python -m app.scripts.fantasy_round_drift <org-id-or-slug|all> [--apply]

``all`` runs every club with a Fantasy season, each in its own transaction.
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from app.models.db import FantasyRound, FantasySeason, async_session_maker
from app.services import fantasy_engine


async def run_one(club_id, name: str, apply: bool) -> int:
    async with async_session_maker() as db:
        print(f"\n{name}")
        fs = (await db.execute(text(
            "SELECT id FROM fantasy_seasons WHERE organisation_id = :o ORDER BY season_year DESC LIMIT 1"), {"o": club_id})).scalar()
        if fs is None:
            print("  No fantasy season.")
            return 0
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
            for d in drift[:12]:
                print(f"    {d['name']}: {d['stored']:g} -> {d['now']:g}")
            if len(drift) > 12:
                print(f"    ... and {len(drift) - 12} more")
        if not stale:
            print("  Every scored round matches its scorecards.")
            return 0
        if apply:
            try:
                for rnd in stale:
                    await fantasy_engine.settle_round(db, fs, rnd)
                await db.commit()
                print(f"  Settled {len(stale)} round(s) again.")
            except Exception as e:  # noqa: BLE001  one club's failure must not stop the rest
                await db.rollback()
                print(f"  FAILED, nothing changed for this club: {e}")
        else:
            await db.rollback()
            print(f"  Dry run: {len(stale)} round(s) would be settled again.")
        return len(stale)


async def run(org: str, apply: bool) -> None:
    async with async_session_maker() as db:
        if org == "all":
            clubs = (await db.execute(text(
                "SELECT o.id, o.name FROM organisations o WHERE EXISTS "
                "(SELECT 1 FROM fantasy_seasons f WHERE f.organisation_id = o.id) ORDER BY o.name"))).all()
        else:
            clubs = (await db.execute(text("SELECT id, name FROM organisations WHERE id::text = :o OR slug = :o"), {"o": org})).all()
        if not clubs:
            raise SystemExit(f"no club matches {org!r}")
    total = 0
    for club_id, name in clubs:
        total += await run_one(club_id, name, apply)
    if not apply and total:
        print(f"\nDry run: {total} round(s) across {len(clubs)} club(s) would be settled again. Run again with --apply.")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit("usage: python -m app.scripts.fantasy_round_drift <org-id-or-slug|all> [--apply]")
    asyncio.run(run(args[0], "--apply" in sys.argv))
