"""Work report for a teaser pull: what was done, how long it took, and what
that implies for the full target list.

Pure functions over the per-club rows ``club_teaser.run_batch`` returns, with
nothing imported beyond the standard library, so the arithmetic can be checked
without a database. Used by ``python -m app.scripts.pull_club_teasers``.

The projection rests on per-club latency, not on how the sample was run: a
sample goes one club at a time, the scheduled job goes two, and a club takes
about as long either way. So wall time for a pass is (clubs x seconds per club)
divided by the concurrency it will run at.
"""
from __future__ import annotations

import math
from typing import Iterable, Optional

# What the scheduled job does (services/club_teaser.run_batch defaults and
# jobs/scheduler.py): two clubs at a time, a pause after each, and 168 firings
# a day (10 minute steps 06:00-09:00 and 21:00-21:59, 5 minute steps between).
SCHEDULED_CONCURRENCY = 2
RUNS_PER_DAY = 168
# The tightest gap between two firings. A run longer than this loses the slot
# behind it (max_instances=1, coalesce=True), so the day's total drops.
MIN_GAP_SECONDS = 5 * 60
DEFAULT_LIMITS = (3, 5, 10, 20)
SMALL_SAMPLE = 20


def _dur(seconds: float) -> str:
    seconds = max(0.0, seconds)
    if seconds < 90:
        return f"{seconds:.1f}s"
    if seconds < 5400:
        return f"{seconds / 60:.1f} min"
    if seconds < 172800:
        return f"{seconds / 3600:.1f} h"
    return f"{seconds / 86400:.1f} days"


def done_rows(detail: Iterable[dict]) -> list[dict]:
    """Rows for clubs that were actually pulled (a stopped or dry run leaves
    the rest with no status)."""
    return [d for d in detail if d.get("status")]


def by_status(rows: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for d in rows:
        s = out.setdefault(d["status"], {"clubs": 0, "calls": 0, "secs": 0.0,
                                         "min_secs": None, "max_secs": 0.0})
        secs = float(d.get("secs") or 0.0)
        s["clubs"] += 1
        s["calls"] += int(d.get("calls") or 0)
        s["secs"] += secs
        s["min_secs"] = secs if s["min_secs"] is None else min(s["min_secs"], secs)
        s["max_secs"] = max(s["max_secs"], secs)
    return out


def projection(rows: list[dict], total_due: int, *, pause_seconds: float = 0.0,
               limits: Iterable[int] = DEFAULT_LIMITS) -> Optional[dict]:
    """What pulling ``total_due`` clubs costs, from the measured averages.
    None when nothing was pulled, so there is nothing to average."""
    if not rows:
        return None
    n = len(rows)
    avg_secs = sum(float(d.get("secs") or 0.0) for d in rows) / n
    avg_calls = sum(int(d.get("calls") or 0) for d in rows) / n
    slot = avg_secs + pause_seconds
    total_secs = total_due * slot
    table = []
    for lim in sorted(set(int(x) for x in limits if int(x) > 0)):
        run_secs = math.ceil(lim / SCHEDULED_CONCURRENCY) * slot
        runs = math.ceil(total_due / lim) if total_due else 0
        table.append({"limit": lim, "run_secs": run_secs, "runs": runs,
                      "days": runs / RUNS_PER_DAY,
                      "fits": run_secs <= MIN_GAP_SECONDS})
    return {"clubs": total_due, "avg_secs": avg_secs, "avg_calls": avg_calls,
            "calls": total_due * avg_calls,
            "serial_secs": total_secs,
            "scheduled_secs": total_secs / SCHEDULED_CONCURRENCY,
            "table": table, "sample": n}


def report_lines(detail: list[dict], elapsed: float, *, total_due: int,
                 pause_seconds: float = 0.0, configured_limit: int = 0,
                 limits: Iterable[int] = DEFAULT_LIMITS) -> list[str]:
    """The human-readable report. ``elapsed`` is the wall clock of the run."""
    rows = done_rows(detail)
    if not rows:
        return [f"work done: nothing pulled (elapsed {_dur(elapsed)})"]
    n = len(rows)
    calls = sum(int(d.get("calls") or 0) for d in rows)
    busy = sum(float(d.get("secs") or 0.0) for d in rows)
    lines = ["", "work done",
             f"  elapsed        {_dur(elapsed)} wall clock",
             f"  clubs pulled   {n}"
             + (f"  ({n / elapsed * 60:.1f} a minute)" if elapsed > 0 else ""),
             f"  API calls      {calls}"
             + (f"  ({calls / elapsed:.2f} a second)" if elapsed > 0 else ""),
             f"  per club       {busy / n:.1f}s and {calls / n:.1f} calls on average"
             + (f"  ({busy / calls:.2f}s a call)" if calls else "")]
    lines.append("")
    lines.append(f"  {'status':12} {'clubs':>5} {'calls':>6} {'calls/club':>10} "
                 f"{'avg s':>7} {'min s':>7} {'max s':>7}")
    for status, s in sorted(by_status(rows).items(), key=lambda kv: -kv[1]["clubs"]):
        c = s["clubs"]
        lines.append(f"  {status:12} {c:>5} {s['calls']:>6} {s['calls'] / c:>10.1f} "
                     f"{s['secs'] / c:>7.1f} {s['min_secs']:>7.1f} {s['max_secs']:>7.1f}")
    slowest = max(rows, key=lambda d: float(d.get("secs") or 0.0))
    lines.append(f"  slowest        {str(slowest.get('name'))[:40]} "
                 f"({float(slowest.get('secs') or 0.0):.1f}s, {slowest.get('calls', 0)} calls)")

    p = projection(rows, total_due, pause_seconds=pause_seconds, limits=(
        list(limits) + ([configured_limit] if configured_limit > 0 else [])))
    lines += ["", f"projection for {total_due} club(s) still due"]
    if not total_due:
        lines.append("  nothing is due, so there is nothing to project")
        return lines
    lines += [f"  API calls      about {p['calls']:.0f}",
              f"  one at a time  about {_dur(p['serial_secs'])}",
              f"  two at a time  about {_dur(p['scheduled_secs'])} of pulling "
              "(what the scheduled job does)",
              "",
              f"  {'clubs/run':>9} {'run takes':>10} {'runs':>6} {'days':>6}  fits the 5 min gap"]
    for r in p["table"]:
        mark = "  <- configured" if r["limit"] == configured_limit else ""
        lines.append(f"  {r['limit']:>9} {_dur(r['run_secs']):>10} {r['runs']:>6} "
                     f"{r['days']:>6.1f}  {'yes' if r['fits'] else 'NO, slots would be skipped'}{mark}")
    lines.append(f"  days assume {RUNS_PER_DAY} runs a day and every run finishing in time.")
    if n < SMALL_SAMPLE:
        lines.append(f"  Based on {n} club(s): a small sample is noisy, and the mix of "
                     "statuses (junior_only and empty clubs cost far less) moves it. "
                     f"Pull {SMALL_SAMPLE}+ before trusting it.")
    return lines
