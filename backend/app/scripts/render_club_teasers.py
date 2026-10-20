"""Draw the teaser pictures (the club season card for emails, share previews and
ads) for clubs whose picture is missing or out of date.

    python -m app.scripts.render_club_teasers [--limit N] [--club TEXT]
        [--force | --missing] [--base-url URL] [--apply]

Dry run by default: lists the clubs that would be drawn and writes nothing.
``--apply`` opens headless Chromium on the site, takes the three pictures per
club and writes them to ``TEASER_IMAGE_DIR`` (default
``/mnt/media/bettercricket/internal/teasers``). Only clubs with a good snapshot
that have not registered are drawn; a registered club is left alone.

``--limit`` is the most clubs drawn in one run (default 50, never above 500).
``--club TEXT`` draws the one club whose name contains TEXT (it must match
exactly one). ``--force`` redraws clubs that are already up to date, for after
a design change to the card (it starts from the same clubs every run, so use
it with ``--club`` or one big ``--limit``). ``--missing`` draws clubs marked as
drawn whose picture file is not on disk, which is what to run after a restore
onto a fresh box or if the media volume was not mounted; it carries on from
where the last run stopped. ``--base-url`` is the site to open; it defaults to
``TEASER_RENDER_BASE_URL``, then the public site.

The same function runs from the Club Directory panel's "Draw pictures" button.
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import text

from app.services import club_teaser_images as ti


async def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--club", metavar="TEXT")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--force", action="store_true")
    grp.add_argument("--missing", action="store_true")
    ap.add_argument("--base-url")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)

    from app.models.db import async_session_maker
    club_id = None
    if a.club:
        async with async_session_maker() as s:
            rows = (await s.execute(text(
                "SELECT mc.id, mc.name FROM marketing_clubs mc "
                "JOIN club_teaser_snapshots t ON t.marketing_club_id = mc.id "
                "WHERE mc.name ILIKE :n ORDER BY mc.name LIMIT 10"), {"n": f"%{a.club}%"})).all()
        if len(rows) != 1:
            print(f"--club must match exactly one club with a snapshot; matched {len(rows)}:")
            for _, name in rows:
                print(f"  {name}")
            return 2
        club_id = str(rows[0][0])

    out = await ti.render_pending(async_session_maker, limit=a.limit, club_id=club_id,
                                  force=a.force, missing_files=a.missing, apply=a.apply, base=a.base_url)
    if out["status"] == "busy":
        print("a render is already running")
        return 1
    if not a.apply:
        print(f"{out['due']} club(s) due. Dry run: nothing drawn. Add --apply to draw them.")
        for c in out.get("clubs", [])[:25]:
            print(f"  {c['name']}  {ti.public_page_url(c['token'])}")
        if out["due"] > 25:
            print(f"  ... and {out['due'] - 25} more")
        return 0
    print(f"due {out['due']}, drawn {out['drawn']}, failed {len(out['failed'])}, "
          f"{out['bytes'] / 1024:.0f} KB written")
    for f in out["failed"]:
        print(f"  FAILED {f['name']}: {f['error']}")
    if out["status"] == "error":
        print(f"error: {out.get('error')}")
        return 1
    return 1 if out["failed"] else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
