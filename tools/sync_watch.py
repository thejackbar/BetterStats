#!/usr/bin/env python3
"""Sync watch — snapshot a club's headline stats, one game, and its latest sync
run, so you can compare two points in time and confirm a sync actually landed.

Usage:
  python tools/sync_watch.py snapshot           # writes sync_snapshots/<club>_<UTC>.json
  python tools/sync_watch.py diff A.json B.json  # shows what changed between two snapshots

Defaults point at Darwin Cricket Club and its 6 Jun A-Grade game on the live
site. Override with env vars BS_BASE / BS_ORG / BS_GAME if you reuse it.
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

BASE = os.environ.get("BS_BASE", "https://betterat.cricket/api")
ORG = os.environ.get("BS_ORG", "98d1e039-87d8-eb11-a7ad-2818780da0cc")  # Darwin CC
GAME = os.environ.get("BS_GAME", "79800d8d-549a-4083-b41c-4a9c595ed11e")  # Darwin v PINT
SLUG = os.environ.get("BS_SLUG", "darwin-cricket-club")


def _get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.load(r)


def snapshot():
    now = datetime.now(timezone.utc)
    summary = _get(f"/organisations/{ORG}/summary")
    sc = _get(f"/games/{GAME}/scorecard")
    runs = _get(f"/organisations/{ORG}/sync-logs")
    latest = runs[0] if runs else None

    snap = {
        "captured_at": now.isoformat(),
        "summary": summary,
        "game": {
            "result": sc.get("result"),
            "winning_team": sc.get("winning_team"),
            "innings_totals": sc.get("innings_totals"),
            "rows": {k: len(sc.get(k) or []) for k in (
                "batting", "bowling", "opp_batting", "opp_bowling",
                "fielding", "fall_of_wickets", "partnerships")},
        },
        "latest_sync_run": None if not latest else {
            "started_at": latest.get("started_at"),
            "completed_at": latest.get("completed_at"),
            "kind": latest.get("kind"),
            "status": latest.get("status"),
            "stats": latest.get("stats"),
        },
    }

    os.makedirs("sync_snapshots", exist_ok=True)
    fname = f"sync_snapshots/{SLUG}_{now:%Y%m%dT%H%M%SZ}.json"
    with open(fname, "w") as f:
        json.dump(snap, f, indent=2)
    print(f"Wrote {fname}")
    print(f"  games={summary['total_games']} runs={summary['total_runs']} "
          f"wkts={summary['total_wickets']} players={summary['total_players']}")
    print(f"  game result={snap['game']['result']} rows={snap['game']['rows']}")
    print(f"  latest run: {snap['latest_sync_run']['started_at'] if latest else 'none'} "
          f"({snap['latest_sync_run']['status'] if latest else '-'})")
    return fname


def _flat(d, prefix=""):
    out = {}
    for k, v in (d or {}).items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flat(v, key + "."))
        else:
            out[key] = v
    return out


def diff(a_path, b_path):
    a = json.load(open(a_path))
    b = json.load(open(b_path))
    print(f"A {a['captured_at']}  ->  B {b['captured_at']}\n")
    for section in ("summary", "game", "latest_sync_run"):
        fa, fb = _flat(a.get(section)), _flat(b.get(section))
        changed = False
        for k in sorted(set(fa) | set(fb)):
            if fa.get(k) != fb.get(k):
                if not changed:
                    print(f"[{section}]")
                    changed = True
                print(f"  {k}: {fa.get(k)!r}  ->  {fb.get(k)!r}")
        if not changed:
            print(f"[{section}] no change")
        print()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "snapshot"
    if cmd == "snapshot":
        snapshot()
    elif cmd == "diff" and len(sys.argv) == 4:
        diff(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
        sys.exit(1)
