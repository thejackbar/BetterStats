"""Partnerships from a fall of wickets that also records retirements and the unbroken last stand.

WHY THIS EXISTS
---------------
Two things end a partnership without a wicket, and the fall of wickets alone cannot show them:

* a batter retires (women's and junior cricket retire batters at a set score, and anyone can retire
  hurt). The stand ends, the next batter comes in, and every pairing after that moves along one.
  Walking the wickets alone pairs the wrong batters from then on;
* the innings ends with two batters still in. That stand has no wicket at all, so it was never
  worked out for a synced card.

A club types both in the fall of wickets editor (`fow_override_breaks`, see `fow_overrides`). This
module walks the wickets and the retirements together, in the order they happened, and returns
every stand, marking those no wicket ended as unbroken.

THE RULES OF THE WALK
---------------------
* It needs every wicket on the batting card, each with its score and its batter. A guess about who
  was at the crease is worse than no stand, so a short list is refused (the club is told why).
* Batters come in in batting order. A retired batter comes back only once everyone else has batted,
  in the order they retired (how retire-at-a-score rules work, and how a retired-hurt batter
  normally returns). A card that cannot be true that way (the batter named was not at the crease)
  is refused.
* A stand ended by a retirement keeps the wicket number of the stand it was (the 3rd-wicket stand
  ended by a retirement and the 3rd-wicket stand after it are both 3rd-wicket stands).
* The same checks as Cricket Australia's deriver: a score never goes backwards, and a stand is never
  worth more than its two batters' scores plus `_MAX_STAND_EXTRAS`.
"""
from __future__ import annotations

from typing import Optional

from app.services.sync import _MAX_STAND_EXTRAS, _dismissed_pids_grassroots

_SKIP_DT = {"absent", "did not bat", "dnb"}

RETIRED = "retired"
UNBROKEN = "unbroken"


class WalkRefused(ValueError):
    """The typed figures cannot give stands. The message says why, in words a club can act on."""


def batted(batting_rows: list) -> list[dict]:
    """The batters who went to the crease, in batting order."""
    rows = [b for b in batting_rows or []
            if (b.get("dismissalTypeId") or 0) != 0
            and (b.get("dismissalType") or "").lower() not in _SKIP_DT
            and b.get("participantId")]
    return sorted(rows, key=lambda b: b.get("batOrder") or 99)


def _name(b: Optional[dict]) -> str:
    return (b or {}).get("playerShortName") or "That batter"


def derive(batting_rows: list, fow_rows: list, breaks: list[dict],
           innings_total: Optional[int] = None) -> list[dict]:
    """Every stand of an innings, from its wickets plus the retirements and unbroken stand typed.

    `fow_rows` are Cricket Australia shaped (`order`, `runs`, `participantId`). `breaks` are
    `{"kind", "after_wicket", "score", "participant_id"}`; an unbroken entry with no score uses
    `innings_total`. Raises `WalkRefused` when the figures cannot give stands.
    """
    batters = batted(batting_rows)
    by_pid = {b["participantId"]: b for b in batters}
    dismissed = _dismissed_pids_grassroots(batting_rows or [])
    wickets = sorted(fow_rows or [], key=lambda f: f.get("order") or 99)

    if len(wickets) != len(dismissed):
        raise WalkRefused(
            f"The batting card shows {len(dismissed)} wicket{'s' if len(dismissed) != 1 else ''} and "
            f"{len(wickets)} {'are' if len(wickets) != 1 else 'is'} entered. To record a retirement or the "
            "unbroken stand, enter every wicket with its score and batter.")
    for f in wickets:
        if f.get("runs") is None or not f.get("participantId"):
            raise WalkRefused(
                f"Wicket {f.get('order')} needs both its score and its batter to record a retirement "
                "or the unbroken stand.")
    if len(batters) < 2:
        raise WalkRefused("Fewer than two batters went in, so there is no partnership to work out.")

    retirements = [b for b in breaks if b.get("kind") == RETIRED]
    unbroken = next((b for b in breaks if b.get("kind") == UNBROKEN), None)

    # The order things happened: the retirements after k wickets (by score), then wicket k + 1.
    events: list[dict] = []
    for k in range(len(wickets) + 1):
        for r in sorted((r for r in retirements if (r.get("after_wicket") or 0) == k),
                        key=lambda r: r.get("score") or 0):
            events.append({"kind": RETIRED, "score": r.get("score"), "pid": r.get("participant_id")})
        if k < len(wickets):
            w = wickets[k]
            events.append({"kind": "wicket", "score": w.get("runs"), "pid": w.get("participantId"),
                           "wicket": w.get("order")})
    if unbroken is not None:
        score = unbroken.get("score")
        if score is None:
            score = innings_total
        if score is None:
            raise WalkRefused("Enter the score at the end of the innings for the unbroken stand.")
        events.append({"kind": UNBROKEN, "score": score, "pid": None})

    at_crease = [b["participantId"] for b in batters[:2]]
    queue = [b["participantId"] for b in batters[2:]]
    retired_pool: list[str] = []
    fallen = 0
    prev = 0
    out: list[dict] = []
    for ev in events:
        score = ev["score"]
        if score is None or score < prev:
            raise WalkRefused(
                f"The score {score} comes after {prev}, and a score cannot go backwards. "
                "Check the order of the wickets and retirements.")
        if len(at_crease) < 2:
            if ev["kind"] == UNBROKEN:
                raise WalkRefused("Every batter is out or retired at the end, so there is no unbroken stand. "
                                  "Untick the unbroken stand.")
            raise WalkRefused("The figures run out of batters before the innings ends. Check the retirements.")
        if ev["kind"] != UNBROKEN and ev["pid"] not in at_crease:
            what = "retired" if ev["kind"] == RETIRED else f"out at wicket {ev.get('wicket')}"
            raise WalkRefused(
                f"{_name(by_pid.get(ev['pid']))} is entered as {what} but was not at the crease then, "
                "going by the batting order. Check the batter or the wickets down for each retirement.")
        b1, b2 = (by_pid[at_crease[0]], by_pid[at_crease[1]])
        runs = score - prev
        cap = (b1.get("runsScored") or 0) + (b2.get("runsScored") or 0) + _MAX_STAND_EXTRAS
        if runs > cap:
            raise WalkRefused(
                f"The {fallen + 1}{_suffix(fallen + 1)} wicket stand would be {runs} runs, more than "
                f"{_name(b1)} and {_name(b2)} scored between them. Check the scores.")
        out.append({
            "wicket_number": fallen + 1,
            "batter1_id": b1["participantId"], "batter2_id": b2["participantId"],
            "batter1_name": b1.get("playerShortName"), "batter2_name": b2.get("playerShortName"),
            "batter1_runs": b1.get("runsScored"), "batter2_runs": b2.get("runsScored"),
            "runs": runs,
            "is_unbroken": ev["kind"] != "wicket",
        })
        prev = score
        if ev["kind"] == UNBROKEN:
            break
        at_crease.remove(ev["pid"])
        if ev["kind"] == RETIRED:
            retired_pool.append(ev["pid"])
        else:
            fallen += 1
        if queue:
            at_crease.append(queue.pop(0))
        elif retired_pool:
            at_crease.append(retired_pool.pop(0))
    return out


def _suffix(n: int) -> str:
    return "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
