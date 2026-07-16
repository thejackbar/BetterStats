#!/usr/bin/env python3
"""Headless proof of the BetterImport anti-double-count guarantee.

Exercises the pure arithmetic core of services/import_reconcile.py (no DB) over
the scenarios from the design discussion — the Wayne Giles case and its variants.
The key assertion in every case: the effective career total the view would show
(GR + emitted season deltas + career residual) equals the club's authoritative
total — never the naive sum (which would be 698 for Wayne).

Usage:
    python scripts/verify_import_reconcile.py
"""

import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.import_reconcile import (  # noqa: E402
    COUNT_METRICS, balls_to_overs, accumulate, resolve_club_totals, reconcile_player,
    _grade_key,
)

_FAILURES = []


def _m(**kw):
    """A canonical metric dict with the given fields set, rest zero."""
    d = {k: 0 for k in COUNT_METRICS}
    d.update({k: v for k, v in kw.items() if k in COUNT_METRICS})
    d["high_score"] = kw.get("high_score")
    d["is_hs_not_out"] = kw.get("is_hs_not_out", False)
    d["best_bowling_wickets"] = kw.get("best_bowling_wickets")
    d["best_bowling_figures"] = kw.get("best_bowling_figures")
    return d


def _effective(gr, season_deltas, career):
    """Mirror the view: sum GR + emitted season deltas + career residual."""
    out = {k: (gr.get(k, 0) or 0) for k in COUNT_METRICS}
    for _sid, m in season_deltas:
        for k in COUNT_METRICS:
            out[k] += m.get(k, 0) or 0
    if career is not None:
        for k in COUNT_METRICS:
            out[k] += career.get(k, 0) or 0
    return out


def check(name, *, club, gr, import_seasons, gr_season_ids, expect_matches, naive_would_be=None):
    season_deltas, career = reconcile_player(club, gr, import_seasons, gr_season_ids)
    eff = _effective(gr, season_deltas, career)

    # 1. Headline matches lands exactly where the club says.
    ok = eff["matches"] == expect_matches
    # 2. Every count metric equals max(club, gr + emitted) — i.e. GR wins where it
    #    leads, the residual fills the rest, and we never double count.
    emitted = {k: sum((m.get(k, 0) or 0) for _s, m in season_deltas) for k in COUNT_METRICS}
    for k in COUNT_METRICS:
        expected = max(club.get(k, 0) or 0, (gr.get(k, 0) or 0) + emitted[k])
        if eff[k] != expected:
            ok = False
    # 3. The residual is never negative.
    if career is not None and any((career.get(k, 0) or 0) < 0 for k in COUNT_METRICS):
        ok = False

    status = "PASS" if ok else "FAIL"
    extra = ""
    if naive_would_be is not None:
        extra = f"  (naive add would wrongly give {naive_would_be})"
    print(f"  [{status}] {name}: effective matches = {eff['matches']} "
          f"(club {club['matches']}, GR {gr['matches']}, "
          f"{len(season_deltas)} season delta(s), "
          f"residual {career['matches'] if career else 0}){extra}")
    if not ok:
        _FAILURES.append(name)


def main():
    print("balls_to_overs sanity:")
    for balls, want in [(0, "0.0"), (6, "1.0"), (62, "10.2"), (3, "0.3")]:
        got = balls_to_overs(balls)
        tag = "PASS" if got == Decimal(want) else "FAIL"
        print(f"  [{tag}] {balls} balls -> {got} (want {want})")
        if got != Decimal(want):
            _FAILURES.append(f"balls_to_overs({balls})")

    print("\nReconciliation scenarios:")

    # A — Wayne Giles, career-total-only upload (the exact worry). GR has 225
    #     across two merged profiles; the club book says 473.
    check(
        "A career-only (Wayne)",
        club=_m(matches=473, runs=14576, wickets=333, catches=340, high_score=200, is_hs_not_out=True),
        gr=_m(matches=225, runs=7000, wickets=150, catches=180, high_score=150),
        import_seasons=[],
        gr_season_ids={"s-recent"},
        expect_matches=473,
        naive_would_be=698,
    )

    # B — season-by-season rows that all overlap GR, plus an explicit "Prior
    #     Seasons & Adjustments" lump. The residual must reproduce the lump.
    s1, s2 = "S1", "S2"
    club_b = resolve_club_totals(
        None,
        accumulate(
            accumulate(
                accumulate(None, _m(matches=10, runs=300)),   # S1
                _m(matches=12, runs=400)),                     # S2
            _m(matches=248, runs=6635)),                       # prior bucket
    )
    check(
        "B seasons overlap GR + prior bucket",
        club=club_b,
        gr=_m(matches=22, runs=700),
        import_seasons=[(s1, _m(matches=10, runs=300)), (s2, _m(matches=12, runs=400))],
        gr_season_ids={s1, s2},
        expect_matches=270,
    )

    # C — GR's coverage of a season is incomplete (11 of 13). Career must be the
    #     club's 13; the season row stays GR's 11; the +2 lives in the residual.
    check(
        "C GR-incomplete season",
        club=_m(matches=13, runs=350),
        gr=_m(matches=11, runs=300),
        import_seasons=[("S1", _m(matches=13, runs=350))],
        gr_season_ids={"S1"},
        expect_matches=13,
    )

    # D — GR found MORE than the club's book (480 > 473). Residual clamps to 0;
    #     GR wins; we show 480, not 953.
    check(
        "D GR exceeds club",
        club=_m(matches=473, runs=14576),
        gr=_m(matches=480, runs=14800),
        import_seasons=[],
        gr_season_ids={"s-recent"},
        expect_matches=480,
        naive_would_be=953,
    )

    # E — a player who left before GR coverage: no GR at all, two pre-GR seasons.
    #     Everything is emitted as season deltas; residual is 0.
    check(
        "E manual-only player (no GR)",
        club=_m(matches=27, runs=900),
        gr=_m(),
        import_seasons=[("S1", _m(matches=15, runs=500)), ("S2", _m(matches=12, runs=400))],
        gr_season_ids=set(),
        expect_matches=27,
    )

    # F — self-healing: same upload as A, but a later sync grew GR 225 -> 230.
    #     The residual auto-shrinks 248 -> 243; the total stays 473.
    _, career_f = reconcile_player(
        _m(matches=473, runs=14576), _m(matches=230, runs=7200), [], {"s-recent"},
    )
    shrank = career_f is not None and career_f["matches"] == 243
    print(f"  [{'PASS' if shrank else 'FAIL'}] F self-healing after GR growth: "
          f"residual {career_f['matches'] if career_f else 0} (want 243), total stays "
          f"{230 + (career_f['matches'] if career_f else 0)}")
    if not shrank:
        _FAILURES.append("F self-healing")

    print("\n_grade_key normalisation (migration 152 grade-scoped reconcile):")
    for raw, want in [(None, None), ("", None), ("   ", None),
                       ("1st Grade", "1st Grade"), ("  1st Grade  ", "1st Grade")]:
        got = _grade_key(raw)
        tag = "PASS" if got == want else "FAIL"
        print(f"  [{tag}] _grade_key({raw!r}) -> {got!r} (want {want!r})")
        if got != want:
            _FAILURES.append(f"_grade_key({raw!r})")

    print()
    if _FAILURES:
        print(f"FAILED: {len(_FAILURES)} check(s): {', '.join(_FAILURES)}")
        sys.exit(1)
    print("All checks passed — the import only ever adds max(0, club - GR); "
          "double-counting is impossible by construction.")


if __name__ == "__main__":
    main()
