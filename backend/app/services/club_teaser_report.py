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


# ---------------------------------------------------------------------------
# Is a snapshot enough to build the campaign on?
# ---------------------------------------------------------------------------
# What "your club's season so far" needs: the club named and placed, a season
# with matches played, a record, a ladder position, and enough named players in
# each of batting and bowling that the piece has someone to talk about. These
# are the questions a person would ask reading one, written down so twenty
# snapshots can be read in a minute rather than opened one at a time.
MIN_BATTERS = 3
MIN_BOWLERS = 3
STALE_AFTER_YEARS = 1


def review_snapshot(snap: Optional[dict], *, this_year: int) -> dict:
    """``{"ready": bool, "missing": [...], "warnings": [...], "summary": {...}}``.

    ``missing`` are gaps that stop a campaign piece being built (the piece has
    nothing to say); ``warnings`` are figures worth a look before it goes out.
    A club with no snapshot is not ready and says why.
    """
    if not snap:
        return {"ready": False, "missing": ["no snapshot"], "warnings": [], "summary": {}}
    missing: list[str] = []
    warnings: list[str] = []
    club = snap.get("club") or {}
    season = snap.get("season") or {}
    totals = snap.get("totals") or {}
    ladders = snap.get("ladders") or []
    bat, bowl = snap.get("batting") or [], snap.get("bowling") or []
    field, recs = snap.get("fielding") or [], snap.get("records") or []

    if not club.get("name"):
        missing.append("club name")
    if not (club.get("state") or club.get("suburb")):
        warnings.append("no state or suburb to place the club")
    if not club.get("logo_url"):
        warnings.append("no club logo")
    if not season.get("name"):
        missing.append("season")
    if not totals.get("matches"):
        missing.append("matches played (no ladder rows for the season)")
    if not ladders:
        missing.append("ladder position")
    if len(bat) < MIN_BATTERS:
        missing.append(f"top batters (have {len(bat)}, want {MIN_BATTERS})")
    if len(bowl) < MIN_BOWLERS:
        missing.append(f"top bowlers (have {len(bowl)}, want {MIN_BOWLERS})")
    if not field:
        warnings.append("no fielding leaders")
    if not recs:
        warnings.append("no season records")

    for label, rows in (("batting", bat), ("bowling", bowl), ("fielding", field)):
        if any("*" in str(r.get("name") or "") for r in rows):
            warnings.append(f"a redacted name got into {label}")
    for r in bat:
        hs = r.get("high_score")
        try:
            if hs is not None and int(hs) > int(r.get("runs") or 0):
                warnings.append(f"{r.get('name')}: high score {hs} is above total runs {r.get('runs')}")
        except (TypeError, ValueError):
            pass
        if r.get("innings") and r.get("runs") and r["runs"] / max(r["innings"], 1) > 200:
            warnings.append(f"{r.get('name')}: {r['runs']} runs in {r['innings']} innings looks wrong")
    year = season.get("year")
    if year and this_year - int(year) > STALE_AFTER_YEARS:
        warnings.append(f"latest season with stats is {year}, so the piece would be about an old season")
    if totals.get("wins") is not None and totals.get("matches") \
            and (totals["wins"] or 0) + (totals.get("losses") or 0) > totals["matches"]:
        warnings.append("wins plus losses exceed matches played")

    return {"ready": not missing, "missing": missing, "warnings": warnings,
            "summary": {"season": season.get("name"), "year": year, "matches": totals.get("matches"),
                        "wins": totals.get("wins"), "losses": totals.get("losses"),
                        "win_rate": totals.get("win_rate"), "grades": len(ladders),
                        "batters": len(bat), "bowlers": len(bowl), "fielders": len(field),
                        "records": len(recs)}}


def teaser_lines(snap: dict) -> list[str]:
    """The snapshot read back as the facts a campaign piece would use, one per
    line, so a person can check them against the club's own page."""
    club, season, totals = snap.get("club") or {}, snap.get("season") or {}, snap.get("totals") or {}
    out = [f"{club.get('name')} ({club.get('suburb') or ''} {club.get('state') or ''}".rstrip() + ")"
           + (f", {club['association']}" if club.get("association") else "")]
    out.append(f"  {season.get('name')}: {totals.get('matches')} played, {totals.get('wins')} won, "
               f"{totals.get('losses')} lost, {totals.get('draws')} drawn"
               + (f", win rate {totals['win_rate']}%" if totals.get("win_rate") is not None else ""))
    if totals.get("matches_vs_prev_pct") is not None and (totals.get("prev") or {}).get("season"):
        out.append(f"  {totals['matches_vs_prev_pct']:+d}% matches on {totals['prev']['season']}")
    for lad in snap.get("ladders") or []:
        out.append(f"  ladder: {lad.get('grade') or lad.get('name') or '?'} "
                   f"{lad.get('rank')} of {lad.get('teams')} "
                   f"(P{lad.get('played')} W{lad.get('won')} L{lad.get('lost')} pts {lad.get('points')})")
    for b in (snap.get("batting") or [])[:3]:
        out.append(f"  bat: {b['name']} {b['runs']} runs @ {b.get('average')}, HS {b.get('high_score')}"
                   f"{'*' if b.get('hs_not_out') else ''}, {b.get('fifties')}x50 {b.get('hundreds')}x100")
    for b in (snap.get("bowling") or [])[:3]:
        out.append(f"  bowl: {b['name']} {b['wickets']} wkts @ {b.get('average')}, best {b.get('best')}, "
                   f"econ {b.get('economy')}")
    for f in (snap.get("fielding") or [])[:2]:
        out.append(f"  field: {f['name']} {f['catches']} catches, {f['run_outs']} run outs, "
                   f"{f['stumpings']} stumpings")
    for r in snap.get("records") or []:
        out.append(f"  record: {r.get('label')} {r.get('value')} ({r.get('player')})")
    return out
