"""Partnerships from a fall of wickets that is missing wickets (pure, no database).

Reported off a club card: six wickets fell and only four fall-of-wicket rows were
recorded (1, 3, 4 and 5), so the whole innings was refused and no stand reached the
records. `partial_partnerships.derive_partial` now keeps every stand the figures settle.

This checks the pure function and the shipped `sync._derive_partnerships_grassroots`:

  * the reported innings: the 1st, 4th and 5th wicket stands come out, with the right
    pairs and runs, and the 2nd, 3rd and 6th do not (the 3rd needs the 2nd's score);
  * SOUNDNESS over 20,000 random innings with random wickets dropped: every stand it
    emits equals the stand a complete card gives. It must never name a wrong pair or a
    wrong score. (Coverage is printed, because a refuse-everything function also passes
    soundness; the reported innings above and a minimum coverage guard that.)
  * a stand that depends on a guess gets no row (two candidates for the 2nd wicket);
  * every refusal: duplicate wicket, wicket past the card, a batter who was not dismissed,
    a score going backwards, a retirement on the card, a mistyped score;
  * a complete card still goes down the original path, unchanged.

Run:  python verification/verify_partial_partnerships.py
"""
from __future__ import annotations

import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

failures: list[str] = []
checks = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global checks
    checks += 1
    print(("  ok   " if ok else "  FAIL ") + name + (f"   [{detail}]" if detail and not ok else ""))
    if not ok:
        failures.append(name)


try:
    from app.services.partial_partnerships import derive_partial, skipped_reasons
except Exception as exc:  # control run against the previous commit
    print(f"  MISSING partial_partnerships: {exc}")
    derive_partial = None
    skipped_reasons = None

from app.services.sync import _derive_partnerships_grassroots, _dismissed_pids_grassroots


def card(names, outs, runs=None):
    """A Grassroots-shaped batting card. `names` in batting order; `outs` the set dismissed."""
    rows = []
    for i, n in enumerate(names, 1):
        if n in outs:
            rows.append({"participantId": n, "playerShortName": n, "batOrder": i,
                         "runsScored": (runs or {}).get(n, 100), "dismissalTypeId": 3, "dismissalType": "Bowled"})
        else:
            rows.append({"participantId": n, "playerShortName": n, "batOrder": i,
                         "runsScored": (runs or {}).get(n, 100), "dismissalTypeId": 1, "dismissalType": "Not Out"})
    return rows


def fow(*rows):
    return [{"order": w, "runs": s, "participantId": p, "playerShortName": p} for w, s, p in rows]


print("The reported innings: wickets 1, 3, 4, 5 of 6 recorded")
names = ["Payne", "Hall", "Bivens", "Sweet", "Cox", "Menezes", "Ito", "Lee"]
outs = {"Payne", "Hall", "Bivens", "Sweet", "Menezes", "Cox"}
bat = card(names, outs, {"Payne": 40, "Hall": 33, "Bivens": 160, "Sweet": 12, "Cox": 60, "Menezes": 14})
rows = fow((1, 73, "Payne"), (3, 331, "Bivens"), (4, 356, "Sweet"), (5, 381, "Menezes"))
stands = _derive_partnerships_grassroots(bat, rows)
by_w = {s["wicket_number"]: s for s in stands}
check("1st, 4th and 5th wicket stands come out, nothing else", sorted(by_w) == [1, 4, 5], str(sorted(by_w)))
if by_w:
    check("1st wicket: Payne and Hall, 73", by_w.get(1, {}).get("runs") == 73
          and {by_w[1]["batter1_id"], by_w[1]["batter2_id"]} == {"Payne", "Hall"})
    check("4th wicket: Sweet and Cox, 25", by_w.get(4, {}).get("runs") == 25
          and {by_w[4]["batter1_id"], by_w[4]["batter2_id"]} == {"Sweet", "Cox"})
    check("5th wicket: Cox and Menezes, 25", by_w.get(5, {}).get("runs") == 25
          and {by_w[5]["batter1_id"], by_w[5]["batter2_id"]} == {"Cox", "Menezes"})
    check("each stand carries both batters' runs", by_w.get(4, {}).get("batter1_runs") is not None)
else:
    for label in ("1st wicket pair", "4th wicket pair", "5th wicket pair", "batter runs"):
        check(label, False, "no stands derived")
if skipped_reasons:
    why = skipped_reasons(6, rows, stands)
    check("the 3rd is skipped because wicket 2 has no score", "wicket 2" in why.get(3, ""), str(why))
    check("the 2nd and 6th are skipped because they have no score",
          "no score" in why.get(2, "") and "no score" in why.get(6, ""), str(why))

print("A complete card goes down the original path")
full = fow((1, 73, "Payne"), (2, 150, "Hall"), (3, 331, "Bivens"), (4, 356, "Sweet"),
           (5, 381, "Menezes"), (6, 400, "Cox"))
fs = _derive_partnerships_grassroots(bat, full)
check("six stands from six wickets", [s["wicket_number"] for s in fs] == [1, 2, 3, 4, 5, 6])
check("and no fall of wickets gives none", _derive_partnerships_grassroots(bat, []) == [])

print("A stand that depends on a guess gets no row")
# Order A..F. A out 1st. Then B and C at the crease. The 2nd wicket is missing: B or C went out,
# and the 3rd wicket (D) was out with E in. Who is with D at the 3rd depends on who went at the 2nd.
nm = ["A", "B", "C", "D", "E", "F"]
b2 = card(nm, {"A", "B", "C", "D"}, {"A": 50, "B": 50, "C": 50, "D": 50, "E": 50, "F": 50})
st = _derive_partnerships_grassroots(b2, fow((1, 40, "A"), (4, 150, "D")))
check("wicket 4's pair is not guessed", all(s["wicket_number"] != 4 for s in st), str(st))
check("wicket 1's pair still comes out", [s["wicket_number"] for s in st] == [1], str(st))

print("Refusals")
base = fow((1, 73, "Payne"), (3, 331, "Bivens"))
check("two rows for one wicket", _derive_partnerships_grassroots(bat, fow((1, 73, "Payne"), (1, 80, "Hall"))) == [])
check("a wicket past the card", _derive_partnerships_grassroots(bat, fow((1, 73, "Payne"), (9, 300, "Bivens"))) == [])
check("a batter who was not dismissed", _derive_partnerships_grassroots(bat, fow((1, 73, "Payne"), (3, 331, "Ito"))) == [])
check("a batter named twice", _derive_partnerships_grassroots(bat, fow((1, 73, "Payne"), (3, 331, "Payne"))) == [])
check("a score going backwards", _derive_partnerships_grassroots(bat, fow((1, 73, "Payne"), (3, 60, "Bivens"))) == [])
check("a mistyped score: a stand worth more than its batters made",
      _derive_partnerships_grassroots(bat, fow((1, 973, "Payne"), (3, 981, "Bivens"))) == [])
ret = card(names, outs)
ret[7]["dismissalTypeId"] = 14
ret[7]["dismissalType"] = "Retired Hurt"
check("a retirement on the card makes the walk unsafe", _derive_partnerships_grassroots(ret, base) == [])
check("a row with no order", _derive_partnerships_grassroots(
    bat, [{"runs": 73, "participantId": "Payne"}, {"order": 3, "runs": 331, "participantId": "Bivens"}]) == [])

print("A row with a score and no batter still gives its neighbours their runs")
sc_only = [{"order": 1, "runs": 73, "participantId": "Payne"},
           {"order": 2, "runs": 150, "participantId": None},
           {"order": 3, "runs": 331, "participantId": "Bivens"}]
ss = {s["wicket_number"]: s for s in _derive_partnerships_grassroots(bat, sc_only)}
check("wicket 3 is 181 (331 - 150), pair settled by the walk",
      ss.get(3, {}).get("runs") == 181 and {ss[3]["batter1_id"], ss[3]["batter2_id"]} == {"Bivens", "Sweet"}
      if 3 in ss else False, str(ss))
check("wicket 2 is 77 (150 - 73)", ss.get(2, {}).get("runs") == 77 if 2 in ss else False, str(ss))

print("Soundness over random innings with wickets dropped")
rnd = random.Random(20261022)
emitted = skipped_total = innings_done = true_total = 0
bad = []
for _ in range(20000):
    n_bat = rnd.randint(3, 11)
    names_r = [f"P{i}" for i in range(1, n_bat + 1)]
    wk = rnd.randint(1, n_bat - 1)
    at, nxt, score = names_r[:2], 2, 0
    truth, rows_r, out_r = {}, [], []
    for w in range(1, wk + 1):
        out = rnd.choice(at)
        score += rnd.randint(1, 60)
        truth[w] = (frozenset(at), score)
        rows_r.append((w, score, out))
        out_r.append(out)
        at = [p for p in at if p != out]
        if nxt < n_bat:
            at.append(names_r[nxt])
            nxt += 1
    # the card must have the batters who came in; those never in are dropped from the card
    came_in = names_r[:min(n_bat, wk + 2)]
    bt = card(came_in, set(out_r), {p: 500 for p in came_in})
    # drop some wickets, sometimes keep the score but lose the name
    kept = []
    for w, s, p in rows_r:
        r = rnd.random()
        if r < 0.35:
            continue
        kept.append((w, s, None if r < 0.45 else p))
    if not kept or len(kept) >= wk:
        continue
    innings_done += 1
    true_total += wk
    got = derive_partial(bt, set(out_r), fow(*kept), 50, {p for p in came_in if p not in out_r}) \
        if derive_partial else []
    for s in got:
        w = s["wicket_number"]
        pair, score_w = truth[w]
        prev = truth[w - 1][1] if w > 1 else 0
        if {s["batter1_id"], s["batter2_id"]} != set(pair) or s["runs"] != score_w - prev:
            bad.append((w, s, truth[w], kept))
    emitted += len(got)
check("no stand ever names a wrong pair or a wrong score", not bad, str(bad[:1]))
print(f"       {innings_done} partial innings, {emitted} stands emitted of {true_total} wickets")
check("and it is not just refusing everything", emitted > innings_done * 0.8, f"{emitted}")

print()
print(f"{checks - len(failures)} of {checks} checks passed")
sys.exit(1 if failures else 0)
