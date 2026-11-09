"""Report which stored club crests look wrong. Read-only: it never writes.

WHY
---
The post designer's opponent crest comes from one of two places: Cricket Australia's
own address for the club, or the crest WE hold on the club's ``organisations`` row
(``logo_data``, served at ``/api/images/organisations/<id>/logo``). Nothing in the
sync writes ``logo_data``; only an upload does. So a wrong crest (a football club's on
a cricket club, say) is a wrong upload, and the code cannot tell from the bytes alone.
This lists what is stored so a person can see it.

WHAT IT PRINTS
--------------
* Crests shared byte for byte by clubs with DIFFERENT names (one upload copied onto
  another club's row is the usual cause).
* With ``--name kardinya`` (repeatable), every club whose name contains that text,
  with its id, crest size, hash and the URL to look at.
* With ``--dump DIR``, the crest files of those clubs, so you can open them.

It does not repair anything. To clear a crest, use the club's own Logo screen (the
Remove button), or ask for a repair script that takes the club id and ``--apply``.

USAGE
-----
    python -m app.scripts.audit_org_logos
    python -m app.scripts.audit_org_logos --name kardinya --name "east perth" --dump /tmp/crests
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
from collections import defaultdict
from pathlib import Path

from sqlalchemy import text

from app.models.db import async_session_maker

_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp", "image/svg+xml": "svg"}


async def _rows(session):
    res = await session.execute(text(
        "SELECT id, name, slug, logo_url, logo_mime, logo_data FROM organisations WHERE logo_data IS NOT NULL"))
    return [dict(r) for r in res.mappings().all()]


def _digest(data: bytes) -> str:
    return hashlib.sha256(bytes(data)).hexdigest()[:12]


def shared_crests(rows: list[dict]) -> list[list[dict]]:
    """Groups of clubs holding the identical crest under different names. Pure."""
    by_hash: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_hash[_digest(r["logo_data"])].append(r)
    out = []
    for group in by_hash.values():
        names = {(g["name"] or "").strip().lower() for g in group}
        if len(group) > 1 and len(names) > 1:
            out.append(group)
    return out


def _line(r: dict) -> str:
    return (f"{r['name']!r:46} id={r['id']}  {len(bytes(r['logo_data'])):>7} bytes  "
            f"sha={_digest(r['logo_data'])}  /api/images/organisations/{r['id']}/logo")


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", action="append", default=[], help="list clubs whose name contains this (repeatable)")
    ap.add_argument("--dump", help="write the crest files of the --name clubs into this directory")
    args = ap.parse_args()

    async with async_session_maker() as session:
        rows = await _rows(session)
    print(f"{len(rows)} clubs hold a stored crest.\n")

    groups = shared_crests(rows)
    print(f"Crests shared by clubs with different names: {len(groups)}")
    for g in groups:
        print("  -- same bytes --")
        for r in g:
            print("   ", _line(r))

    wanted = [n.lower() for n in args.name]
    if wanted:
        print("\nClubs matching --name:")
        out_dir = Path(args.dump) if args.dump else None
        if out_dir:
            out_dir.mkdir(parents=True, exist_ok=True)
        for r in rows:
            if any(w in (r["name"] or "").lower() for w in wanted):
                print("   ", _line(r))
                if out_dir:
                    ext = _EXT.get(r["logo_mime"] or "", "bin")
                    (out_dir / f"{r['id']}.{ext}").write_bytes(bytes(r["logo_data"]))


if __name__ == "__main__":
    asyncio.run(main())
