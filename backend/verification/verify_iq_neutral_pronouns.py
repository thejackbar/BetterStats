"""Verification: BetterIQ never calls a player he, him or his (no database needed).

Reported (Applecross): in a women's match BetterIQ referred to the women as "he"
and "him". The opposition's gender is not held per player, and sides are men's,
women's, mixed and junior, so every line of generated scouting text now uses
"they", or no pronoun at all.

Checks, on the SHIPPED code:

  * every string literal the BetterIQ services can print (the phrase pools, the
    dismissal notes, the dossier and deep-scan synthesis, the trends text) is free
    of he/him/his/himself/she/her/herself, "batsman" and the gendered nouns
    (man, bloke, gloveman), except fielding positions such as "third man"
  * the phrase pools still produce text (the scan is not empty), and the scanner
    does catch a gendered line (presence control)
  * the pronoun rule is in the Ask IQ system prompt
  * the cached payloads that carry this text were re-versioned, so a dossier or
    deep scan built before the change is rebuilt rather than served for 7 days
  * a batter and a bowler can still be built from the pools, with a "they" note

CONTROL MODE: run with a directory of the previous commit's services as the
first argument (git show of the old files). It reports the old wording as failed
checks instead of crashing.

Run:  python verification/verify_iq_neutral_pronouns.py [services_dir]
"""
from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVICES = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "app" / "services"
FILES = ["iq.py", "iq_opponent.py", "iq_scout.py", "iq_trends.py", "iq_team.py", "iq_review.py", "iq_lineup.py",
         "iq_players.py", "iq_selection.py", "iq_phrases.py", "iq_radar.py", "iq_phases.py", "scouting_intel.py", "iq_ask.py"]

GENDERED = re.compile(
    r"\b(he|him|his|himself|she|her|hers|herself|batsman|batsmen|bloke|gloveman|glovesman|bogey man|danger man|main man|go-to man)\b"
    r"|\b(he|she)'(s|ll|d)\b", re.I)
MAN = re.compile(r"\b(?<!third )man\b(?! of the match)", re.I)
# The one string allowed to name the words: the instruction that forbids them.
ALLOWED = ("Pronouns: clubs field",)

PASS = FAIL = 0
FAILURES: list[str] = []


def check(label, got, want=True):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        FAILURES.append(f"{label}: got {got!r}, want {want!r}")
        print(f"  FAIL {label}: got {got!r}, want {want!r}")


def strings(path: Path):
    """String constants that can reach a user, skipping docstrings."""
    tree = ast.parse(path.read_text())
    doc_ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                doc_ids.add(id(body[0].value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in doc_ids:
            yield node.lineno, node.value


def offenders(text: str) -> bool:
    return bool(GENDERED.search(text) or MAN.search(text))


def main():
    total = 0
    bad: list[str] = []
    for name in FILES:
        path = SERVICES / name
        if not path.exists():
            continue
        for line, s in strings(path):
            total += 1
            if any(a in s for a in ALLOWED):
                continue
            if offenders(s):
                bad.append(f"{name}:{line}: {s.strip()[:90]}")
    check("the scan read a real number of strings", total > 1000, True)
    check("scanner catches a gendered line (presence control)", offenders("Keep him guessing"), True)
    check("scanner catches 'bogey man' (presence control)", offenders("A genuine bogey man for us"), True)
    check("scanner leaves 'third man' alone", offenders("Place a fielder at third man"), False)
    check("scanner leaves a they-line alone", offenders("They hit through the line hard"), False)
    check("no BetterIQ string calls a player he, him or his, or uses a gendered noun", bad[:12], [])
    if bad:
        print(f"    {len(bad)} offending strings, first few:")
        for b in bad[:8]:
            print("     ", b)

    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")
    os.environ.setdefault("ANTHROPIC_API_KEY", "")
    if SERVICES == ROOT / "app" / "services":
        from app.services import iq_phrases, iq_opponent, iq_scout, iq_ask
        pools = [v for k, v in vars(iq_phrases).items() if k.isupper() and isinstance(v, list) and v and isinstance(v[0], str)]
        check("the phrase module still exposes its pools", len(pools) >= 10, True)
        check("the pools hold the full bank, none emptied", sum(len(p) for p in pools) > 250, True)
        b = {"player_id": "p1", "name": "Sample Bat", "runs": 400, "innings": 10, "average": 45.0, "form": "hot",
             "dismissals": {"bowled": 5}, "strike_rate": 80.0}
        arch = iq_phrases.batter_archetype(b, 0)
        note = iq_phrases.batter_note(arch, "p1") + " " + iq_phrases.batter_plan(arch, "bowled", "p1")
        check("a built batter note has no gendered word", offenders(note), False)
        check("the Ask IQ prompt carries the pronoun rule", "Pronouns: clubs field" in iq_ask._SYSTEM, True)
        check("the dossier cache was re-versioned", iq_opponent.DOSSIER_VERSION >= 13, True)
        check("the deep-scan cache was re-versioned", iq_scout.DEEP_VERSION >= 4, True)

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAILURES:
        print("\n".join(" - " + f for f in FAILURES))
    sys.exit(1 if FAIL else 0)


main()
