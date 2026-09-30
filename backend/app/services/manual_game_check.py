"""Does a hand-entered game add up? Warnings only, never a refusal.

A club typing in a game from a scorebook often does not have every figure: the
opposition's total was never written down, a bowler's spell is missing from
the page, the result line was worked out from memory. None of that may stop the
game being saved, because a partial record is better than none. What the
entry form owes the person is a plain statement of what does not agree, so they
can fix it if they can and carry on if they cannot.

Reported off Hamilton Veterans' 23 Oct 2011 game: both sides showed 142/7. The
form only shows the opposition-total boxes for an opposition innings, so a
total typed while an innings was set to "Opposition" stayed on the row after
the innings was flipped to "Our innings", hidden. Nothing said the two sides
now shared a score, or that our card added up to 125.

Everything here reads the payload the form sends (`ManualGameIn.model_dump()`)
and nothing else, so the live check on the form and the check a save could make
are the same function. Each warning is `{kind, innings, text}`.
"""
from __future__ import annotations

import re
from typing import Optional

from app.services import manual_result

_MARGIN_RUNS = re.compile(r"\bby\s+(\d+)\s+runs?\b", re.I)


def overs_to_balls(overs) -> int:
    """Cricket notation to balls: 10.2 is ten overs and two balls, so 62."""
    if overs is None:
        return 0
    whole = int(overs)
    return whole * 6 + int(round((float(overs) - whole) * 10))


def balls_to_overs(balls: int) -> str:
    whole, part = divmod(balls, 6)
    return f"{whole}.{part}" if part else str(whole)


def _n(v) -> int:
    return int(v) if v is not None else 0


def _extras(inn: Optional[dict]) -> Optional[int]:
    """The extras an innings records: itemised parts win, else the single total."""
    if not inn:
        return None
    parts = [inn.get(k) for k in ("byes", "leg_byes", "wides", "no_balls", "penalty")]
    if any(p is not None for p in parts):
        return sum(_n(p) for p in parts)
    return inn.get("extras_total")


def _itemised(inn: Optional[dict]) -> bool:
    return bool(inn) and any(
        inn.get(k) is not None for k in ("byes", "leg_byes", "wides", "no_balls", "penalty"))


def check_game(game: dict) -> list[dict]:
    warnings: list[dict] = []

    def warn(kind: str, text: str, innings: Optional[int] = None) -> None:
        warnings.append({"kind": kind, "innings": innings, "text": text})

    batting = [r for r in (game.get("batting_innings") or []) if r.get("player_id")]
    bowling = [r for r in (game.get("bowling_spells") or []) if r.get("player_id")]
    rows = {r.get("innings_number") or 1: r for r in (game.get("innings") or [])}
    # A photo upload carries the opposition's whole card in its stored payload,
    # so its opposition innings needs no total typed in.
    has_card = bool(game.get("extracted_payload"))

    bat_by: dict[int, list[dict]] = {}
    for r in batting:
        bat_by.setdefault(r.get("innings_number") or 1, []).append(r)
    bowl_by: dict[int, list[dict]] = {}
    for r in bowling:
        bowl_by.setdefault(r.get("innings_number") or 1, []).append(r)

    numbers = sorted(set(rows) | set(bat_by) | set(bowl_by))

    our_innings: list[int] = []
    opp_innings: list[int] = []
    for n in numbers:
        side = (rows.get(n) or {}).get("batting_side")
        if side not in ("us", "opposition"):
            side = "us" if n in bat_by else ("opposition" if n in bowl_by else None)
        if side == "us":
            our_innings.append(n)
        elif side == "opposition":
            opp_innings.append(n)

        # The flipped-innings mistake: the side toggle and the rows under it
        # disagree, which is what makes a card read as our bowlers against our
        # own batters.
        if (rows.get(n) or {}).get("batting_side") == "opposition" and n in bat_by:
            warn("side_mismatch",
                 f"Innings {n} is set to the opposition's, but our batters are entered in it. "
                 f"If we batted in innings {n}, change \"Who batted\" to \"Our innings\"; "
                 f"if not, the batters belong under another innings number.", n)
        if (rows.get(n) or {}).get("batting_side") == "us" and n in bowl_by:
            warn("side_mismatch",
                 f"Innings {n} is set to ours, but our bowlers are entered in it. Our bowlers "
                 f"bowl in the opposition's innings, so their spells belong under the other "
                 f"innings number.", n)

    # ── the opposition's innings: is there a total, and do our bowlers add up to it
    opp_totals: dict[int, int] = {}
    for n in opp_innings:
        row = rows.get(n) or {}
        total = row.get("total_runs")
        if total is None:
            if not has_card:
                warn("opp_total_missing",
                     f"No total is recorded for the opposition's innings {n}. You can save "
                     f"without it, but their score will not show on the scorecard and the "
                     f"result cannot be checked against it.", n)
            continue
        opp_totals[n] = total

        spells = bowl_by.get(n) or []
        if not spells:
            continue
        conceded = sum(_n(s.get("runs")) for s in spells)
        balls = sum(overs_to_balls(s.get("overs")) for s in spells)
        overs_note = ""
        if row.get("overs") is not None and balls != overs_to_balls(row.get("overs")):
            overs_note = (f" Those spells add up to {balls_to_overs(balls)} overs against "
                          f"{balls_to_overs(overs_to_balls(row.get('overs')))} recorded for the innings.")
        if _itemised(row):
            not_bowlers = _n(row.get("byes")) + _n(row.get("leg_byes")) + _n(row.get("penalty"))
            expected = conceded + not_bowlers
            if expected != total:
                warn("bowling_runs",
                     f"Our bowlers' figures for innings {n} add up to {conceded} runs, plus "
                     f"{not_bowlers} in byes, leg byes and penalties, which is {expected}. The "
                     f"opposition total is {total}, so a spell may be missing or a figure "
                     f"may be off.{overs_note}", n)
        elif conceded > total:
            warn("bowling_runs",
                 f"Our bowlers' figures for innings {n} add up to {conceded} runs, which is "
                 f"more than the opposition total of {total}.{overs_note}", n)

    # ── our innings: the card is the total, so say what it adds up to
    our_totals: dict[int, int] = {}
    our_extras_known = True
    for n in our_innings:
        row = rows.get(n) or {}
        batted = [r for r in bat_by.get(n, []) if not r.get("did_not_bat")]
        if row.get("total_runs") is not None:
            our_totals[n] = row["total_runs"]
            continue
        if not batted:
            continue
        extras = _extras(row)
        if extras is None:
            our_extras_known = False
        our_totals[n] = sum(_n(r.get("runs")) for r in batted) + (extras or 0)

    # ── the result line against the two totals (one innings each only)
    result = (game.get("result") or "").strip()
    if (result and len(our_innings) == 1 and len(opp_innings) == 1
            and our_innings[0] in our_totals and opp_innings[0] in opp_totals):
        ours, theirs = our_totals[our_innings[0]], opp_totals[opp_innings[0]]
        said = manual_result.text_outcome(result)
        shown = manual_result.score_outcome(ours, theirs)
        margin = _MARGIN_RUNS.search(result)
        caveat = "" if our_extras_known else (
            " No extras are entered for our innings, which may explain a small gap.")
        if said and shown and said != shown:
            warn("result_outcome",
                 f"The result says \"{result}\", but the totals entered ({ours} to our "
                 f"{theirs}) have us {'winning' if shown == 'won' else 'losing'}.", None)
        elif margin and ours != theirs and abs(ours - theirs) != int(margin.group(1)):
            warn("result_margin",
                 f"The result says \"{result}\", a margin of {margin.group(1)} runs, but the "
                 f"totals entered are {ours} to {theirs}, a difference of "
                 f"{abs(ours - theirs)}.{caveat}", None)

    return warnings
