"""Hide ONE player from the public site because they asked (migration 316).

WHY THIS EXISTS
---------------
A person who asks to be removed is dealt with here, not by the club's
visibility switch: this records that it was their request (so a club admin or a
bulk import cannot switch them back on), removes their photographs, including
BetterIQ's scouting copy, and writes an audit entry.

It never deletes the player row or anything they did. The club's match records
hang off the row, and a deleted row is simply re-created by the next sync.

A person has one ``players`` row PER CLUB, all carrying the same Cricket
Australia participant id. This hides every one of them, and records a
suppression on that id so a row created later (a club that joins, a fixture
another club syncs) is born hidden too.

WHAT IT TOUCHES
---------------
  * ``players``: ``is_public`` false, ``privacy_hidden_*`` set, photo and action
    photo columns cleared (and a legacy on-disk headshot unlinked), on this row
    AND every other club's row for the same participant id;
  * ``player_privacy_suppressions``: one row, keyed on the participant id;
  * ``scouted_players``: the photo columns on any row for the same person;
  * ``manual_edit_logs``: one audit entry.

Photographs are NOT restored by ``--restore``. Keeping a copy would defeat the
request.

USAGE (dry run unless --apply)
------------------------------
    python -m app.scripts.hide_player_at_request <player_id> --report
    python -m app.scripts.hide_player_at_request <player_id> --reason "..." --by "name"
    python -m app.scripts.hide_player_at_request <player_id> --reason "..." --by "name" --apply
    python -m app.scripts.hide_player_at_request <player_id> --restore --by "name" --apply

``--report`` prints what we hold against the person (every table with a
foreign key to ``players``, plus the scouting copy), for an access request.
``--keep-photos`` hides the player without touching the photographs.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from app.models.db import async_session_maker
from app.services import player_privacy


async def run(args) -> int:
    async with async_session_maker() as session:
        player = await player_privacy.load_player(session, args.player_id)
        if player is None:
            print(f"No player with id {args.player_id}", file=sys.stderr)
            return 2

        report = await player_privacy.holdings(session, player)
        print(json.dumps(report, indent=2, default=str))
        if args.report:
            return 0

        if not args.by:
            print("--by is required (who is recording this)", file=sys.stderr)
            return 2

        if args.restore:
            print("\nWould put the player back on the public site. Photographs stay removed.")
            if not args.apply:
                print("Dry run. Re-run with --apply to write.")
                return 0
            out = await player_privacy.restore_public(session, player, by=args.by)
            await session.commit()
            print(f"Restored: {out}")
            return 0

        if not args.reason:
            print("--reason is required (what the request was)", file=sys.stderr)
            return 2

        print(
            f"\nWould hide the player from the public site"
            + ("" if args.keep_photos else " and remove their photographs")
            + f", on this row and {len(report['other_club_rows'])} other club row(s) for the same person,"
            + " and record a suppression so new rows are born hidden."
        )
        if not args.apply:
            print("Dry run. Re-run with --apply to write.")
            return 0
        out = await player_privacy.hide_at_request(
            session, player, by=args.by, reason=args.reason, remove_photos=not args.keep_photos
        )
        await session.commit()
        print(f"Done: {out}")
        return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("player_id")
    ap.add_argument("--reason", help="what the request was, in a sentence")
    ap.add_argument("--by", help="who is recording the request")
    ap.add_argument("--report", action="store_true", help="print what we hold and stop")
    ap.add_argument("--restore", action="store_true", help="put the player back on the public site")
    ap.add_argument("--keep-photos", action="store_true", help="hide without removing photographs")
    ap.add_argument("--apply", action="store_true", help="write (default is a dry run)")
    sys.exit(asyncio.run(run(ap.parse_args())))


if __name__ == "__main__":
    main()
