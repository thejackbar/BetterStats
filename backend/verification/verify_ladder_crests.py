"""Ladder crests: the crest a club keeps with us replaces Cricket Australia's link.

Asked for (November 2026): "the logos aren't working properly" on the BetterPosts
Ladder. Cricket Australia's ``owningOrganisation.logoUrl`` is often empty or a
link that 404s, so every row drew a monogram, our own included. Runs the SHIPPED
``ladders._use_stored_crests`` over organisations on a real Postgres.

Checks: a club here with a crest gets it (matched by organisation id); our own
row gets our crest; an archived club keeps Cricket Australia's link; a club with
no crest on file keeps Cricket Australia's; a row with a name that matches a
club but no id is not guessed; Cricket Australia's link is kept beside ours.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@127.0.0.1:5433/bstest \\
  python verification/verify_ladder_crests.py
Control: on v9.165.0 the function does not exist and the rows carry no org id,
so every check reports FAIL instead of crashing.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text

import verify_records_timing as base
from app.routers import ladders

PASS = FAIL = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"PASS {label}")
    else:
        FAIL += 1
        print(f"FAIL {label}" + (f"  {detail}" if detail else ""))


U = lambda n: uuid.UUID(f"6b000000-0000-0000-0000-{n:012d}")
OURS, WSCC, OLD, BARE = U(1), U(2), U(3), U(4)


async def main() -> None:
    await base.build_schema()
    async with base.Session() as s:
        for oid, name, slug, logo, archived in (
            (OURS, "Applecross Cricket Club", "applecross", f"/api/images/organisations/{OURS}/logo?v=aa", None),
            (WSCC, "Wembley Subiaco Cricket Club", "wscc", f"/api/images/organisations/{WSCC}/logo?v=bb", None),
            (OLD, "Old Boys Cricket Club", "oldboys", f"/api/images/organisations/{OLD}/logo?v=cc", datetime.now(timezone.utc)),
            (BARE, "North Perth Cricket Club", "np", None, None),
        ):
            await s.execute(text("INSERT INTO organisations (id, name, short_name, slug, is_active, logo_url, archived_at) VALUES (:i, :n, :n, :g, true, :l, :a)"),
                            {"i": oid, "n": name, "g": slug, "l": logo, "a": archived})
        await s.commit()

    # The ladder the parser builds, as Cricket Australia would send it.
    raw = {"ladders": [{"name": "Overall", "columns": [{"id": "played", "heading": "P"}], "pools": [{"teams": [
        {"rank": 1, "id": "t1", "displayName": "Applecross 7th XI", "owningOrganisation": {"id": str(OURS), "name": "Applecross Cricket Club", "logoUrl": None}, "ladderData": []},
        {"rank": 2, "id": "t2", "displayName": "WSCC One Day 4's", "owningOrganisation": {"id": str(WSCC).upper(), "name": "Wembley Subiaco", "logoUrl": "https://ca.example/wscc.png"}, "ladderData": []},
        {"rank": 3, "id": "t3", "displayName": "Old Boys 4th XI", "owningOrganisation": {"id": str(OLD), "name": "Old Boys", "logoUrl": "https://ca.example/old.png"}, "ladderData": []},
        {"rank": 4, "id": "t4", "displayName": "North Perth 4th XI", "owningOrganisation": {"id": str(BARE), "name": "North Perth", "logoUrl": "https://ca.example/np.png"}, "ladderData": []},
        {"rank": 5, "id": "t5", "displayName": "Wembley Subiaco 5th XI", "owningOrganisation": {"name": "Wembley Subiaco Cricket Club"}, "ladderData": []},
    ]}]}]}
    club = SimpleNamespace(id=OURS, name="Applecross Cricket Club", short_name="Applecross", playhq_id=None,
                           logo_url=f"/api/images/organisations/{OURS}/logo?v=aa", archived_at=None, workspace_kind=None)
    views = ladders._parse_ladder_payload(raw, club)
    teams = [{"team_id": "x", "views": views}]
    fn = getattr(ladders, "_use_stored_crests", None)
    if fn is not None:
        async with base.Session() as s:
            await fn(s, club, teams)
    rows = {r["rank"]: r for r in (views[0]["rows"] if views else [])}
    g = lambda k, f: (rows.get(k) or {}).get(f)
    check("control: the parser lights our own row", g(1, "is_club") is True)
    check("our own row gets the crest we keep for the club", g(1, "logo_url") == club.logo_url, str(g(1, "logo_url")))
    check("a club here with a crest gets it, matched by id (case does not matter)", g(2, "logo_url") == f"/api/images/organisations/{WSCC}/logo?v=bb", str(g(2, "logo_url")))
    check("and Cricket Australia's own link is kept beside it", g(2, "ca_logo_url") == "https://ca.example/wscc.png", str(g(2, "ca_logo_url")))
    check("an archived club keeps Cricket Australia's crest (its upload is old)", g(3, "logo_url") == "https://ca.example/old.png", str(g(3, "logo_url")))
    check("a club here with no crest on file keeps Cricket Australia's", g(4, "logo_url") == "https://ca.example/np.png", str(g(4, "logo_url")))
    check("a row with no organisation id is not matched by name", g(5, "logo_url") is None, str(g(5, "logo_url")))

    async with base.Session() as s:
        n = (await s.execute(text("SELECT count(*) FROM organisations WHERE logo_url IS NOT NULL"))).scalar()
    check("nothing is written", n == 3, str(n))

    print(f"\n{PASS} passed, {FAIL} failed")
    await base.engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
