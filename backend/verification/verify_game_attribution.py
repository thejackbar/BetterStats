"""Verification: the rule that says whether a synced game is a player's, from CA's scorecard. No database.

Shared by the audit and the repair script, so a mistake here would repair the wrong games. Covers the
case found on Leederville (Jonah Cumming: hidden-participant rows), a stranger's id on a card, and the
ones that must NOT be called wrong: a merged second registration, a
per-club merged id, a card with nobody on it.

Run:  python verification/verify_game_attribution.py
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import game_attribution as ga

PASS = FAIL = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")


ME = str(uuid.uuid4())
SECOND_REG = str(uuid.uuid4())            # a second registration merged into ME
OTHER = str(uuid.uuid4())                  # a namesake
PLACEHOLDER = "00000000-0000-0000-0000-000000000001"
ORG = uuid.uuid4()


def card(sheet_ids=(), bat_ids=(), field_ids=()):
    return {
        "teams": [{"players": [{"participantId": i} for i in sheet_ids]}],
        "innings": [{"batting": [{"participantId": i} for i in bat_ids], "bowling": [],
                     "fielding": [{"participantId": i} for i in field_ids]}],
    }


print("\n-- games that ARE theirs --")
check("own id on the team sheet", ga.classify(card([ME, OTHER]), [ME], []) == "ON")
check("own id only on a batting row (no team sheet published)", ga.classify(card([], bat_ids=[ME]), [ME], []) == "ON")
check("a merged second registration is MERGE, not wrong",
      ga.classify(card([SECOND_REG]), [ME], [SECOND_REG]) == "MERGE")
removed_uuid5 = str(uuid.uuid5(ORG, SECOND_REG))
check("a per-club merged record (uuid5 of the raw id) is MERGE",
      ga.classify(card([SECOND_REG]), [ME], [removed_uuid5], ORG) == "MERGE")

print("\n-- games that are NOT theirs --")
check("a stranger's id on the card, not his", ga.classify(card([OTHER], bat_ids=[OTHER]), [ME], []) == "OFF")
check("Jonah Cumming: only the hidden placeholder id and strangers", ga.classify(card([OTHER], bat_ids=[PLACEHOLDER]), [ME], []) == "OFF")
check("the placeholder id never counts as the player even if a record held it",
      ga.classify(card([PLACEHOLDER], bat_ids=[PLACEHOLDER, OTHER]), [PLACEHOLDER], []) == "OFF")

print("\n-- nothing can be judged --")
check("a card with nobody on it is EMPTY, never OFF", ga.classify(card(), [ME], []) == "EMPTY")
check("only the placeholder on the card is EMPTY", ga.classify(card([PLACEHOLDER], bat_ids=[PLACEHOLDER]), [ME], []) == "EMPTY")
check("no card at all is EMPTY", ga.classify(None, [ME], []) == "EMPTY")

print("\n-- merge chains --")
A, B = str(uuid.uuid4()), str(uuid.uuid4())
got = ga.merged_into({A: B, B: ME, SECOND_REG: ME, str(uuid.uuid4()): str(uuid.uuid4())}, ME)
check("a chain A -> B -> player counts both A and B", {A, B} <= got, f"got {got}")
check("a direct merge counts", SECOND_REG in got)
check("an unrelated merge does not", len(got) == 3, f"got {len(got)}")
check("a cycle does not hang", ga.merged_into({A: B, B: A}, ME) == set())

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
