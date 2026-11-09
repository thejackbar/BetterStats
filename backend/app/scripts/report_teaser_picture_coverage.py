"""How many crawled clubs have what it takes to build teaser pictures, and how many
actually have a full set of pictures on the media volume. Read-only: it makes no
Cricket Australia call, draws nothing and writes nothing.

    python -m app.scripts.report_teaser_picture_coverage

Every club with a snapshot row falls into exactly one line:

  No data to build from   the crawl found nothing usable: ``empty`` (Cricket
                          Australia could not place the club, it has no seasons,
                          or no season has batting stats), ``junior_only`` (every
                          grade is junior, deliberately given no page) or
                          ``error`` (the last pull failed).
  Has data (``ok``)       a good snapshot, split by what is on the volume now:
      full set            every picture format is a real file AND the draw is on
                          record, so the email picture renders and the picture
                          route serves it (exactly the clubs the Segments rule
                          "Club has a full set of teaser pictures" selects);
      files, not served   every file is there but the draw is not recorded
                          (no ``image_version``, or no snapshot body), so the
                          picture route would refuse them;
      partial             some pictures but not all (a club drawn before the
                          dashboard format existed has the other three);
      not drawn, customer already a customer, so the drawer leaves it alone;
      not drawn, old data the snapshot predates the current schema and waits for the
                          crawl to re-pull it before it can be drawn;
      not drawn yet       due to be drawn.

The last lines count the email contacts the Segments rule would reach, through the
same engine the Segments screen uses (so unsubscribed and bounced contacts are
already out of it).
"""
from __future__ import annotations

import asyncio
import sys
from collections import Counter

from sqlalchemy import text

from app.services import club_teaser_images as ti
from app.services.club_teaser_link import NOT_A_CUSTOMER_SQL


def _present(token: str) -> int:
    """How many of the formats exist as a non-empty file for this club."""
    n = 0
    for fmt in ti.FORMATS:
        try:
            if ti.image_path(token, fmt).stat().st_size > 0:
                n += 1
        except (OSError, ValueError):
            pass
    return n


async def main(argv=None) -> int:
    from app.models.db import async_session_maker
    from app.services import comms_segments
    from app.services.marketing_org import get_outreach_org

    async with async_session_maker() as s:
        rows = (await s.execute(text(f"""
            SELECT t.token, t.status,
                   COALESCE((t.snapshot->>'schema')::int, 0) >= :schema AS current_schema,
                   (t.image_version IS NOT NULL AND t.snapshot IS NOT NULL) AS servable,
                   ({NOT_A_CUSTOMER_SQL}) AS not_customer
            FROM club_teaser_snapshots t
            JOIN marketing_clubs mc ON mc.id = t.marketing_club_id
        """), {"schema": ti._schema_version()})).mappings().all()
        outreach = await get_outreach_org(s)
        contacts = {}
        if outreach is not None:
            for label, val in (("yes", "yes"), ("no", "no")):
                contacts[label] = await comms_segments.count(
                    s, outreach, {"match": "all", "rules": [{"field": "teaser_pictures", "op": "eq", "value": val}]})

    full_formats = len(ti.FORMATS)
    c = Counter()
    for r in rows:
        if r["status"] != "ok":
            c[r["status"] if r["status"] in ("empty", "junior_only", "error") else "other"] += 1
            continue
        have = _present(r["token"])
        if have == full_formats:
            c["full" if r["servable"] else "unserved"] += 1
        elif have > 0:
            c["partial"] += 1
        elif not r["not_customer"]:
            c["customer"] += 1
        elif not r["current_schema"]:
            c["old_schema"] += 1
        else:
            c["undrawn"] += 1

    total = len(rows)
    no_data = c["empty"] + c["junior_only"] + c["error"] + c["other"]
    ok = total - no_data
    print(f"Clubs with a snapshot row: {total}")
    print(f"  No data to build from:   {no_data}")
    print(f"      empty (not placed, no seasons or no batting stats): {c['empty']}")
    print(f"      junior only:                                        {c['junior_only']}")
    print(f"      last pull failed:                                   {c['error']}")
    if c["other"]:
        print(f"      other status (pending):                             {c['other']}")
    print(f"  Has data (ok):           {ok}")
    print(f"      full set of pictures on file ({full_formats} formats): {c['full']}")
    print(f"      files all there but not served (no draw recorded):  {c['unserved']}")
    print(f"      partial set:                                        {c['partial']}")
    print(f"      not drawn, already a customer:                      {c['customer']}")
    print(f"      not drawn, snapshot waits for a re-pull:            {c['old_schema']}")
    print(f"      not drawn yet (due):                                {c['undrawn']}")
    if contacts:
        print(f"Email contacts in the outreach org, as the Segments rule counts them:")
        print(f"  club has a full set of teaser pictures = yes: {contacts['yes']}")
        print(f"  club has a full set of teaser pictures = no:  {contacts['no']}")
    else:
        print("No outreach org found, so no contact counts.")
    print(f"(pictures are read from {ti.image_root()})")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
