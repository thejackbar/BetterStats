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

``--contact-check`` answers "what contact details do we hold?": for every table that
records something against the person it says, per column, whether an email, phone,
date of birth, address or emergency contact has a value (never the value). It sees
this database only.

``--evidence`` writes a PDF (or ``--format html``) the person can be sent: every
match they are recorded in as a clickable link to the scorecard (their name reads
********) and to their profile page (it says "Player not found"), checked live
from the server unless ``--no-verify``. It holds nothing financial. It is written
to stdout, so from the server:

    docker compose exec -T betterstats-backend python -m app.scripts.hide_player_at_request \
        <player_id> --evidence > evidence.pdf
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

        if getattr(args, "contact_check", False):
            print(json.dumps(await player_privacy.contact_audit(session, player), indent=2, default=str))
            return 0

        if getattr(args, "evidence", False):
            from app.services import privacy_evidence
            data = await privacy_evidence.gather(session, player, args.base_url)
            checks = None if args.no_verify else await privacy_evidence.verify(data)
            if args.format == "html":
                sys.stdout.write(privacy_evidence.render_html(data, checks))
            else:
                sys.stdout.flush()
                sys.stdout.buffer.write(privacy_evidence.render_pdf(data, checks))
                sys.stdout.buffer.flush()
            if checks:
                bad = [u for u, c in checks.items() if c["ok"] is False]
                n_ok = sum(1 for c in checks.values() if c["ok"])
                print(f"evidence: {n_ok} of {len(checks)} checks passed, {len(bad)} failed"
                      + ("".join(f"\n  FAILED: {u}" for u in bad)), file=sys.stderr)
            return 1 if checks and any(c["ok"] is False for c in checks.values()) else 0

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
    ap.add_argument("--contact-check", action="store_true", help="say which contact details we hold (read-only, no values)")
    ap.add_argument("--evidence", action="store_true", help="write the PDF/HTML evidence document to stdout")
    ap.add_argument("--format", choices=("pdf", "html"), default="pdf", help="evidence format (default pdf)")
    ap.add_argument("--base-url", default="https://betterat.cricket", help="site the links point at")
    ap.add_argument("--no-verify", action="store_true", help="do not open the links live from the server")
    sys.exit(asyncio.run(run(ap.parse_args())))


if __name__ == "__main__":
    main()
