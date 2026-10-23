"""Write each Fantasy round's default lock time from the first match of the round.

The default lock is one hour before the round's first match, in the club's own
timezone (`fantasy_engine.default_lock_at`). The nightly job does this for every season
already; this brings the rounds up to date now. Only a round that is not scored and
whose time was not set by hand changes: a scored round's lock is history and a time an
admin typed (`lock_manual`) is never overwritten. Dry run by default: it prints each
round's lock before and after and rolls back. --apply keeps it.

    python -m app.scripts.fantasy_refresh_lock_times <org-id-or-slug|all> [--apply]
"""
from __future__ import annotations

import asyncio
import sys
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.models.db import FantasySeason, async_session_maker
from app.services import fantasy_engine


def _local(dt, tz: str) -> str:
    return dt.astimezone(ZoneInfo(tz)).strftime("%a %d %b %H:%M %Z") if dt else "none"


async def _locks(db, fs_id) -> dict[int, tuple]:
    rows = (await db.execute(text(
        "SELECT round_number, lock_at, lock_manual, status FROM fantasy_rounds "
        "WHERE fantasy_season_id = :f ORDER BY round_number"), {"f": fs_id})).all()
    return {r[0]: (r[1], r[2], r[3]) for r in rows}


async def run(org: str, apply: bool) -> None:
    async with async_session_maker() as db:
        if org == "all":
            clubs = (await db.execute(text(
                "SELECT DISTINCT o.id, o.name FROM organisations o "
                "JOIN fantasy_seasons s ON s.organisation_id = o.id ORDER BY o.name"))).all()
        else:
            clubs = (await db.execute(text(
                "SELECT id, name FROM organisations WHERE id::text = :o OR slug = :o"), {"o": org})).all()
            if not clubs:
                raise SystemExit(f"no club matches {org!r}")
    changed = 0
    for club_id, name in clubs:
        async with async_session_maker() as db:
            fs_id = (await db.execute(text(
                "SELECT id FROM fantasy_seasons WHERE organisation_id = :o ORDER BY season_year DESC LIMIT 1"),
                {"o": club_id})).scalar()
            if fs_id is None:
                continue
            fs = await db.get(FantasySeason, fs_id)
            state = await fantasy_engine.club_state(db, club_id)
            tz = fantasy_engine.lock_timezone_name(fs.rules, state)
            print(f"\n{name} ({tz}{'' if state else ', no state on file'})")
            before = await _locks(db, fs_id)
            try:
                await fantasy_engine.generate_rounds(db, fs, refresh=True)
            except Exception as e:  # one club's failure must not stop the rest
                await db.rollback()
                print(f"  could not read the draw: {e}")
                continue
            after = await _locks(db, fs_id)
            for n, (lock, manual, status) in after.items():
                old = before.get(n, (None, False, None))[0]
                if manual:
                    print(f"  Round {n}: set by hand, kept at {_local(lock, tz)}")
                elif status == "scored":
                    continue
                elif old != lock:
                    changed += 1
                    print(f"  Round {n}: {_local(old, tz)} -> {_local(lock, tz)}")
            if apply:
                await db.commit()
            else:
                await db.rollback()
    print(f"\n{changed} round(s) {'updated' if apply else 'would change. Dry run: run again with --apply'}.")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        raise SystemExit("usage: python -m app.scripts.fantasy_refresh_lock_times <org-id-or-slug|all> [--apply]")
    asyncio.run(run(args[0], "--apply" in sys.argv))
