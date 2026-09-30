"""Read back stored teaser snapshots and say whether each is enough to build the
marketing campaign on. Read-only: it makes no Cricket Australia call and writes
nothing.

    python -m app.scripts.inspect_club_teasers [--limit N] [--club TEXT]
        [--status ok|empty|junior_only|error] [--show TEXT] [--json TEXT]

Default is the N (20) most recently pulled snapshots, one line each, then a
summary of what is missing across them. ``--show TEXT`` prints the facts a
campaign piece would use for the first club whose name contains TEXT (check
them against that club's own page), ``--json TEXT`` dumps its raw snapshot.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import text

from app.services import club_teaser_report as rep


async def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--club", help="only clubs whose name contains this")
    ap.add_argument("--status", choices=["ok", "empty", "junior_only", "error"])
    ap.add_argument("--show", metavar="TEXT")
    ap.add_argument("--json", metavar="TEXT", dest="as_json")
    a = ap.parse_args(argv)

    from app.models.db import async_session_maker
    where, params = ["1=1"], {"limit": max(1, a.limit)}
    if a.club:
        where.append("mc.name ILIKE :club"); params["club"] = f"%{a.club}%"
    if a.status:
        where.append("t.status = :status"); params["status"] = a.status
    for key in ("show", "as_json"):
        v = getattr(a, key)
        if v:
            where.append("mc.name ILIKE :one"); params["one"] = f"%{v}%"
            params["limit"] = 1
    async with async_session_maker() as s:
        rows = (await s.execute(text(f"""
            SELECT mc.name, mc.state, mc.suburb, mc.association_name AS association, mc.logo_url,
                   t.status, t.snapshot, t.api_calls, t.pulled_at, t.last_error, t.version
            FROM club_teaser_snapshots t JOIN marketing_clubs mc ON mc.id = t.marketing_club_id
            WHERE {' AND '.join(where)}
            ORDER BY t.pulled_at DESC NULLS LAST LIMIT :limit"""), params)).mappings().all()
    if not rows:
        print("no snapshots match")
        return 1
    this_year = datetime.now(timezone.utc).year

    if a.as_json:
        snap = rows[0]["snapshot"]
        print(json.dumps(snap, indent=2, default=str) if snap else f"({rows[0]['status']}: no snapshot stored)")
        return 0
    if a.show:
        r = rows[0]
        if not r["snapshot"]:
            print(f"{r['name']}: status {r['status']}, no snapshot stored" + (f" ({r['last_error']})" if r["last_error"] else ""))
            return 0
        print("\n".join(rep.teaser_lines(r["snapshot"])))
        v = rep.review_snapshot(r["snapshot"], this_year=this_year)
        print("\nMISSING:  " + ("; ".join(v["missing"]) or "nothing"))
        print("WARNINGS: " + ("; ".join(v["warnings"]) or "none"))
        return 0

    ready = 0
    gaps: Counter = Counter()
    warns: Counter = Counter()
    print(f"{'club':40} {'st':3} {'status':11} {'season':14} {'P':>3} {'W-L':>7} {'lad':>3} {'bat':>3} {'bowl':>4} {'fld':>3} {'rec':>3}  verdict")
    for r in rows:
        v = rep.review_snapshot(r["snapshot"], this_year=this_year)
        m = v["summary"]
        for x in (v["missing"] if r["status"] == "ok" else []):
            gaps[x.split(" (")[0]] += 1
        for x in (v["warnings"] if r["status"] == "ok" else []):
            warns[re.sub(r"\d+", "N", x.split(": ", 1)[-1])] += 1
        if r["status"] == "ok" and v["ready"]:
            ready += 1
        verdict = "READY" if r["status"] == "ok" and v["ready"] else (
            r["status"] if r["status"] != "ok" else "GAPS: " + "; ".join(v["missing"]))
        if r["status"] == "ok" and v["warnings"]:
            verdict += f"  [{len(v['warnings'])} warning(s)]"
        print(f"{(r['name'] or '')[:40]:40} {(r['state'] or '')[:3]:3} {r['status']:11} "
              f"{str(m.get('season') or '-')[:14]:14} {m.get('matches') if m else '-'!s:>3} "
              f"{(str(m.get('wins')) + '-' + str(m.get('losses'))) if m else '-':>7} {m.get('grades', '-')!s:>3} "
              f"{m.get('batters', '-')!s:>3} {m.get('bowlers', '-')!s:>4} {m.get('fielders', '-')!s:>3} "
              f"{m.get('records', '-')!s:>3}  {verdict}")
    n = len(rows)
    by_status = Counter(r["status"] for r in rows)
    print(f"\n{n} snapshot(s): " + ", ".join(f"{k} {v}" for k, v in sorted(by_status.items())))
    ok_n = by_status.get("ok", 0)
    print(f"{ready} of {ok_n} ok snapshot(s) have everything a campaign piece needs")
    if gaps:
        print("most common gaps:  " + "; ".join(f"{k} x{v}" for k, v in gaps.most_common()))
    if warns:
        print("worth checking:    " + "; ".join(f"{k} x{v}" for k, v in warns.most_common(6)))
    print("\nRead one in full with:  --show 'club name'   (raw JSON: --json 'club name')")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
