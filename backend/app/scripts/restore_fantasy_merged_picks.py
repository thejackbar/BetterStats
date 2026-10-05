"""Put back the Fantasy picks that an earlier player merge deleted.

Merging a hand-added player into their real record used to remove them from every
Fantasy team that had picked them (fixed in `merge_carry`; this repairs the teams
that were already hit). Evidence comes from the stored round lineups and the merge
log: see `services/fantasy_merge_repair`. Teams that are short with no evidence are
listed for a hand fix, never guessed at. Nothing is deleted; each restored pick
writes an audit entry; scored rounds are scored again.

Dry run by default, per the house rule.

    python -m app.scripts.restore_fantasy_merged_picks <org-id-or-slug|all> [--apply]

To find out exactly who is missing, restore a backup from just before the merge
into a scratch Postgres (ops/backup/restore.sh, the same one restore-club uses)
and point the script at it. It follows each pick the backup holds for a player who
no longer exists through the merge log to the record that is live now:

    python -m app.scripts.restore_fantasy_merged_picks <org-id-or-slug> \
        --backup-url postgresql+asyncpg://user:pass@host:port/scratchdb [--apply]
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.models.db import async_session_maker
from app.services import fantasy_merge_repair as repair


async def run(org: str, apply: bool, backup_url: str | None = None) -> None:
    backup_engine = create_async_engine(backup_url) if backup_url else None
    async with async_session_maker() as db:
        where = "" if org == "all" else " WHERE id::text = :o OR slug = :o"
        clubs = (await db.execute(text(f"SELECT id, name FROM organisations{where}"), {"o": org})).all()
        if not clubs:
            raise SystemExit(f"no club matches {org!r}")
        total = 0
        for club_id, name in clubs:
            if backup_engine is not None:
                async with AsyncSession(backup_engine) as backup:
                    found = await repair.find_lost_picks_from_backup(db, backup, club_id)
            else:
                found = await repair.find_lost_picks(db, club_id)
            short = await repair.find_short_squads(db, club_id, {f["squad_id"] for f in found})
            if not found and not short:
                continue
            print(f"\n{name}")
            for f in found:
                print(f"  {'restore' if apply else 'would restore'}: {f['player_name']} to {f['team_name']} "
                      f"(was in their lineup from round {f['first_round']}, merged by log #{f['merge_id']})")
            if short and backup_engine is None:
                merged = await repair.merged_since_fantasy_began(db, club_id)
                if merged:
                    print("  Players merged since Fantasy started (the missing player is one of these):")
                    for m in merged:
                        print(f"    {m['at']:%d %b %Y}: {m['removed']} merged into {m['kept']}")
            for s in short:
                print(f"  needs a hand: {s['team_name']} has {s['players']} of {s['wanted']} players, "
                      f"no record of who is missing. Use Registered players > the team > Add player.")
            if apply and found:
                total += await repair.restore(db, club_id, found)
        if apply:
            await db.commit()
            print(f"\nRestored {total} pick(s).")
        else:
            await db.rollback()
            print("\nDry run. Run again with --apply to restore.")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    url = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--backup-url=")), None)
    if "--backup-url" in sys.argv:
        url = sys.argv[sys.argv.index("--backup-url") + 1]
        args = [a for a in args if a != url]
    asyncio.run(run(args[0] if args else "all", "--apply" in sys.argv, url))
