"""Write the card review spreadsheet: every match stored twice where the two cards differ.

One row per match with a discrepancy (scores differ, small differences, pairing looks wrong),
newest season first and the biggest differences first. The last two columns are empty, for the
reviewer's choice and notes. Read only: nothing is changed.

    python -m app.scripts.export_card_review <org-id-or-slug> [--out PATH] [--all]

`--out` defaults to /tmp/card-review-<slug>.csv. `--all` also lists the matches whose cards
agree exactly, in case the reviewer wants the whole picture. The same file is available from the
Card review page in BetterAdmin.
"""
from __future__ import annotations

import asyncio
import csv
import sys

from sqlalchemy import text

from app.config.settings import settings
from app.models.db import async_session_maker
from app.services import card_review as cr


def _opt(name, default=None):
    if name not in sys.argv:
        return default
    i = sys.argv.index(name)
    if i + 1 >= len(sys.argv):
        raise SystemExit(f"{name} needs a value")
    return sys.argv[i + 1]


async def run(target: str, out: str | None, everything: bool) -> int:
    async with async_session_maker() as db:
        club = (await db.execute(text(
            "SELECT id, name, slug FROM organisations WHERE id::text = :o OR slug = :o"),
            {"o": target})).first()
        if not club:
            print(f"No club matching {target!r}.")
            return 1
        rows = await cr.review_rows(db, club.id)
    if everything:
        # the agreeing matches ride along, labelled by their group like the rest
        for r in rows:
            if r["group"] == "agree":
                r["group"] = "differ"
                r["headline"] = "Cards agree exactly"
                r["items"] = []
    data = cr.export_rows(rows, settings.public_base_url)
    path = out or f"/tmp/card-review-{club.slug}.csv"
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(cr.EXPORT_HEADERS)
        w.writerows(data)
    by_group: dict = {}
    for r in rows:
        by_group[r["group"]] = by_group.get(r["group"], 0) + 1
    print(f"{club.name}: {len(rows)} matches stored twice. {len(data)} written to {path}")
    print("   " + ", ".join(f"{k} {v}" for k, v in sorted(by_group.items())))
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = _opt("--out")
    if out and out in args:
        args.remove(out)
    if not args:
        raise SystemExit("usage: python -m app.scripts.export_card_review <org-id-or-slug> [--out PATH] [--all]")
    raise SystemExit(asyncio.run(run(args[0], out, "--all" in sys.argv)))
