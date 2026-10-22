"""Read-only: how well the identifiers on a club pin down its teaser token.

    python -m app.scripts.report_club_teaser_links [--list utm|ca] [--limit N]
        [--token TOKEN] [--utm CODE] [--ca ID]

With no options, prints for the good (``ok``) snapshots of clubs that have not
registered how many can be reached by their UTM code and by Cricket Australia's
organisation id, and how many cannot (missing, or shared by more than one
club). ``--list utm`` or ``--list ca`` names the ones a lookup cannot reach.
``--token``, ``--utm`` and ``--ca`` run one lookup and print what it finds.
Makes no Cricket Australia call and writes nothing.
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from app.services import club_teaser_link as link


async def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", choices=["utm", "ca"])
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--token")
    ap.add_argument("--utm")
    ap.add_argument("--ca")
    a = ap.parse_args(argv)
    from app.models.db import async_session_maker
    async with async_session_maker() as s:
        if a.token:
            c = await link.club_for_token(s, a.token)
            print(c if c else "no club for that token")
            return 0 if c else 1
        if a.utm:
            t = await link.token_for_utm(s, a.utm)
            print(t or "no single club with a good snapshot has that UTM code")
            return 0 if t else 1
        if a.ca:
            t = await link.token_for_ca_org(s, [a.ca])
            print(t or "no single club with a good snapshot has that id")
            return 0 if t else 1
        h = await link.link_health(s)
        n = h["total"] or 0
        pct = lambda x: f"{(100 * x / n):.1f}%" if n else "n/a"  # noqa: E731
        print(f"{n} good snapshots for clubs that have not registered")
        print(f"  by UTM code:  {h['utm_ok']} reachable ({pct(h['utm_ok'])}), {h['no_utm']} missing, {h['shared_utm']} shared")
        print(f"  by CA org id: {h['ca_ok']} reachable ({pct(h['ca_ok'])}), {h['no_ca']} missing, {h['shared_ca']} shared")
        print(f"  directory guid missing on {h['no_guid']}")
        if a.list:
            print(f"\nclubs the {a.list} lookup cannot reach:")
            for r in await link.unlinked_clubs(s, a.list, a.limit):
                print(f"  {r['name']}  [{r['why']}]  {r['token']}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
