"""Work report for a teaser pull: what was done, how long it took, and what
that implies for the full target list.

Pure functions over the per-club rows ``club_teaser.run_batch`` returns, with
nothing imported beyond the standard library, so the arithmetic can be checked
without a database. Used by ``python -m app.scripts.pull_club_teasers``.

The projection is in calls, because the crawl is paced by calls a second
(services/call_pacer.py): the clubs still due cost about ``average calls per
club`` each, so the time is calls divided by the rate, and the rate that
finishes them inside one day's hours is calls divided by those hours. Per-club
latency is still reported, since it is what a one-at-a-time sample measures.
"""
from __future__ import annotations

from typing import Iterable, Optional

# The hours the crawl runs when the operator has not set any (05:00 to 22:00
# Perth, platform_settings.DEFAULT_TEASER_WINDOW).
DEFAULT_WINDOW_HOURS = 17.0
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


def projection(rows: list[dict], total_due: int, *, rate: Optional[float] = None,
               window_hours: float = DEFAULT_WINDOW_HOURS) -> Optional[dict]:
    """What pulling ``total_due`` clubs costs, from the measured averages.
    None when nothing was pulled, so there is nothing to average. ``rate`` (calls
    a second) adds how long the paced crawl takes; the rate that would finish
    inside one window is always worked out."""
    if not rows:
        return None
    n = len(rows)
    avg_secs = sum(float(d.get("secs") or 0.0) for d in rows) / n
    avg_calls = sum(int(d.get("calls") or 0) for d in rows) / n
    calls = total_due * avg_calls
    window_secs = max(window_hours, 0.0) * 3600.0
    out = {"clubs": total_due, "avg_secs": avg_secs, "avg_calls": avg_calls, "calls": calls,
           "serial_secs": total_due * avg_secs, "sample": n,
           "window_hours": window_hours,
           "rate_for_one_window": (calls / window_secs) if window_secs > 0 else None,
           "paced": None}
    if rate and rate > 0:
        secs = calls / rate
        out["paced"] = {"rate": rate, "secs": secs,
                        "window_days": (secs / window_secs) if window_secs > 0 else None}
    return out


def report_lines(detail: list[dict], elapsed: float, *, total_due: int,
                 rate: Optional[float] = None, window_hours: float = DEFAULT_WINDOW_HOURS,
                 window_label: str = "") -> list[str]:
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

    p = projection(rows, total_due, rate=rate, window_hours=window_hours)
    lines += ["", f"projection for {total_due} club(s) still due"]
    if not total_due:
        lines.append("  nothing is due, so there is nothing to project")
        return lines
    win = f"{window_hours:g}h" + (f" ({window_label})" if window_label else "")
    lines.append(f"  API calls      about {p['calls']:.0f}")
    if p["rate_for_one_window"]:
        lines.append(f"  one window     {p['rate_for_one_window']:.2f} calls a second finishes them inside {win}")
    if p["paced"]:
        pc = p["paced"]
        lines.append(f"  at {pc['rate']:g} a second  about {_dur(pc['secs'])} of crawling"
                     + (f", {pc['window_days']:.1f} day(s) of {win}" if pc["window_days"] else ""))
    else:
        lines.append("  at a set rate  the crawl is off until club_teaser_calls_per_second is set "
                     "(General Settings), or give this script --rate")
    if n < SMALL_SAMPLE:
        lines.append(f"  Based on {n} club(s): a small sample is noisy, and the mix of "
                     "statuses (junior_only and empty clubs cost far less) moves it. "
                     f"Pull {SMALL_SAMPLE}+ before trusting it.")
    return lines
