"""Verification: a team-sheet entry is linked by name only to a player with no id of their own. No database.

Reported (Mulgrave Combined, Cairns, Oct 2026): the adult Luke Bennett (1st Grade) held 16 games from
a Cairns Taxis U11 competition. `audit_player_games` showed his id on none of those sheets; the rows
were a different participant, `L Bennett`, id 03237a7b-..., a namesake. Sync linked the unknown id to
the club's one "Luke Bennett" because the full name matched exactly one player.

The rule under test (`participant_names.attachable_by_full_name`): a name is offered only when one
player holds it AND that player has no Cricket Australia or PlayHQ id. A hand-added record still
links, which is what the feature was built for; a record with an id does not.

Runs the SHIPPED `participant_names` (the one rule sync, the relink script use). The OLD rule
(`unique_by_full_name`, still in the module) is run beside it so the report shows both.

Run:  python verification/verify_name_link_rule.py
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import participant_names as pn

PASS = FAIL = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")


LUKE, ASH, SAM1, SAM2, DAVE = (uuid.uuid4() for _ in range(5))
JUNIOR_ID = str(uuid.uuid4())          # the U11 Luke Bennett's own CA id
NEW_ID = str(uuid.uuid4())             # a hand-added player's first CA id
SAM_ID = str(uuid.uuid4())
DAVE_ID = str(uuid.uuid4())

PLAYERS = [
    (LUKE, "Bennett, Luke", True),       # the adult: a CA id on file
    (ASH, "Ashton Taylor", False),       # hand-added: no id
    (SAM1, "Sam Jones", False),          # two hand-added players share a name
    (SAM2, "Jones, Sam", False),
    (DAVE, "Gardner, David", True),      # holds an older id
]
U11_SHEET = [{"participantId": JUNIOR_ID, "playerShortName": "Luke Bennett"}]
MIXED_SHEET = [
    {"participantId": NEW_ID, "playerShortName": "Ashton Taylor"},
    {"participantId": SAM_ID, "playerShortName": "Sam Jones"},
    {"participantId": DAVE_ID, "playerShortName": "David Gardner"},
]

old_unique = pn.unique_by_full_name([(p, n) for p, n, _ in PLAYERS])
new_unique = pn.attachable_by_full_name(PLAYERS) if hasattr(pn, "attachable_by_full_name") else {}

print("\n-- the reported case: a namesake's games on the adult's record --")
old = pn.resolve_roster_by_name(U11_SHEET, {}, old_unique)
new = pn.resolve_roster_by_name(U11_SHEET, {}, new_unique)
check("the old rule WOULD have linked the U11 Luke Bennett to the adult (this is the bug)",
      old.get(JUNIOR_ID) == LUKE, f"old rule gave {old}")
check("the new rule does not link a namesake to a player who has an id", JUNIOR_ID not in new, f"got {new}")

print("\n-- the feature still works where it was built to --")
mixed = pn.resolve_roster_by_name(MIXED_SHEET, {}, new_unique)
check("a hand-added player (no id) is linked by full name", mixed.get(NEW_ID) == ASH, f"got {mixed}")
check("a name two players share is still never guessed", SAM_ID not in mixed)
check("a player who already has an id is left for the Merge Players screen", DAVE_ID not in mixed)

print("\n-- the helper --")
check("a name held by a player with an id is not offered", pn.full_name_key("Luke Bennett") not in new_unique)
check("a name held by one hand-added player is offered", new_unique.get(pn.full_name_key("Ashton Taylor")) == ASH)
check("an id-less player whose name collides with an id-holder is not offered",
      pn.full_name_key("Sam Jones") not in new_unique and
      pn.attachable_by_full_name([(ASH, "Ashton Taylor", False), (LUKE, "Taylor, Ashton", True)]) == {})

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
