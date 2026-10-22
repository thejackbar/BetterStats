"""Partnerships worked out from a fall of wickets that is missing some wickets.

`sync._derive_partnerships_grassroots` used to refuse an innings unless it held one
fall-of-wicket row per dismissal on the batting card. A scorer who records four of six
wickets therefore lost every stand in the innings, including the ones the figures
settle beyond doubt.

THE RULE
--------
A stand for wicket N is `score(N) - score(N-1)` between `score(0) = 0` and the score at
the fall of wicket N. It needs the scores at BOTH ends, and it needs to know who was at
the crease when wicket N fell. A fall of wickets recorded as 1, 3, 4, 5 of 6 therefore
gives the 1st, 4th and 5th wicket stands. The 3rd is out of reach because the 2nd
wicket's score is missing: the 258 runs between the 1st and 3rd wickets cannot be split
between two stands.

WHO WAS AT THE CREASE
---------------------
The first two in the batting order open. Each wicket takes one batter out and the next in
the order comes in. When the batter out at a missing wicket is not recorded, there may be
more than one way to fill the gaps in. This walks EVERY way that is consistent with the
card (the batter out at a wicket has to be at the crease at that point, and each batter is
out once) and keeps a stand only when every consistent way names the same pair. A stand
that depends on a guess gets no row: a partnership credited to the wrong pair is worse
than none, because it sits on a record board under two names that never batted together.

WHAT IT REFUSES
---------------
Anything that does not fit the card: a wicket number outside 1..wickets, two rows for
one wicket or one batter, a batter named who was not dismissed, a score that goes
backwards, a retirement on the card (the walk assumes one batter in per wicket), a batter
with no id, or a stand worth more than its batters scored plus a generous allowance for
extras (the sign of a mistyped score). Refusing returns nothing for the innings.

Pure, so it can be checked without a database.
"""
from __future__ import annotations

from typing import Iterable, Optional

# The most consistent ways to fill the gaps that are explored before giving up. Real cards
# have a handful; the cap only guards against a pathological innings.
MAX_WORLDS = 5000


class _TooMany(Exception):
    pass


def derive_partial(
    batters: list,
    dismissed: Iterable,
    fow_rows: list,
    max_extras: int = 50,
    not_out_ids: Optional[Iterable] = None,
) -> list:
    """Stands for an innings whose fall of wickets is incomplete.

    `batters`: the card rows of everyone who batted, in batting order. Each carries
    `participantId`, `playerShortName`, `runsScored`.
    `dismissed`: participant ids of the batters genuinely dismissed (the wickets).
    `fow_rows`: Grassroots-shaped fall of wickets: `order` (the wicket number), `runs`
    (the score at the fall) and `participantId` (the batter out, may be missing).
    `not_out_ids`: batters who finished not out. Anyone on the card who is neither
    dismissed nor not out (a retirement) makes the walk unsafe.

    Returns the same dicts `_derive_partnerships_grassroots` returns, only for the wickets
    that can be stated with certainty, or [] when the innings cannot be trusted.
    """
    dismissed = set(dismissed)
    wickets = len(dismissed)
    if wickets < 1 or not fow_rows or len(fow_rows) >= wickets:
        return []

    pids = [b.get("participantId") for b in batters]
    if len(pids) < 2 or any(not p for p in pids) or len(set(pids)) != len(pids):
        return []
    by_pid = {b["participantId"]: b for b in batters}
    if not dismissed.issubset(by_pid):
        return []
    if not_out_ids is not None:
        not_out = set(not_out_ids)
        if any(p not in dismissed and p not in not_out for p in pids):
            return []

    # What the fall of wickets says, by wicket number.
    score_at: dict[int, int] = {}
    out_at: dict[int, str] = {}
    for f in fow_rows:
        w = f.get("order")
        if not isinstance(w, int) or isinstance(w, bool) or w < 1 or w > wickets:
            return []
        if w in score_at or w in out_at:
            return []
        score = f.get("runs")
        has_score = isinstance(score, int) and not isinstance(score, bool)
        pid = f.get("participantId")
        # A row with only one of the two is still evidence: the score gives a stand its runs,
        # the name pins down the batter out. A row with neither says nothing.
        if not has_score and not pid:
            return []
        if has_score:
            score_at[w] = score
        if pid:
            if pid not in dismissed or pid in out_at.values():
                return []
            out_at[w] = pid

    prev = 0
    for w in sorted(score_at):
        if score_at[w] < prev:
            return []
        prev = score_at[w]

    unknown = dismissed - set(out_at.values())
    free = [w for w in range(1, wickets + 1) if w not in out_at]
    if len(unknown) != len(free):
        return []

    # Which pairs were at the crease at each wicket, over every consistent way to place the
    # batters who went out at the wickets whose batter is not recorded.
    seen: dict[int, set] = {}
    worlds = 0

    def walk(w: int, at: list, nxt: int, pool: frozenset, trail: tuple) -> None:
        nonlocal worlds
        if w > wickets:
            worlds += 1
            if worlds > MAX_WORLDS:
                raise _TooMany
            for wk, pair in trail:
                seen.setdefault(wk, set()).add(pair)
            return
        if len(at) != 2:
            return
        if w in out_at:
            options = [out_at[w]] if out_at[w] in at else []
        else:
            options = [p for p in at if p in pool]
        for out in options:
            rest = [p for p in at if p != out]
            step = nxt
            if nxt < len(pids):
                rest.append(pids[nxt])
                step = nxt + 1
            walk(w + 1, rest, step,
                 pool if w in out_at else pool - {out},
                 trail + (((w, frozenset(at)),) if w in score_at else ()))

    try:
        walk(1, [pids[0], pids[1]], 2, frozenset(unknown), ())
    except _TooMany:
        return []
    if worlds == 0:
        return []

    order = {p: i for i, p in enumerate(pids)}
    result = []
    for w in sorted(set(score_at)):
        before = 0 if w == 1 else w - 1
        if w != 1 and before not in score_at:
            continue
        pairs = seen.get(w)
        if not pairs or len(pairs) != 1:
            continue  # the pair at the crease depends on a guess
        a, b = sorted(next(iter(pairs)), key=order.__getitem__)
        ba, bb = by_pid[a], by_pid[b]
        runs = score_at[w] - (score_at[before] if before else 0)
        cap = (ba.get("runsScored") or 0) + (bb.get("runsScored") or 0) + max_extras
        if runs < 0 or runs > cap:
            return []
        result.append({
            "wicket_number": w,
            "batter1_id": a, "batter2_id": b,
            "batter1_name": ba.get("playerShortName"),
            "batter2_name": bb.get("playerShortName"),
            "batter1_runs": ba.get("runsScored"),
            "batter2_runs": bb.get("runsScored"),
            "runs": runs,
        })
    return result


def skipped_reasons(wickets: int, fow_rows: list, stands: list) -> dict:
    """Why each wicket of an innings has no stand, in plain words, keyed by wicket number.

    For the editor to say what is still missing. A wicket with a stand is absent.
    """
    have = {s["wicket_number"] for s in stands}
    score_at = {f.get("order"): f.get("runs") for f in fow_rows
                if isinstance(f.get("order"), int) and isinstance(f.get("runs"), int)}
    out = {}
    for w in range(1, wickets + 1):
        if w in have:
            continue
        if w not in score_at:
            out[w] = "no score recorded for this wicket"
        elif w > 1 and (w - 1) not in score_at:
            out[w] = f"no score recorded for wicket {w - 1}"
        else:
            out[w] = "the batters at the crease cannot be told from the card"
    return out
