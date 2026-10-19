"""Verification: CA's shared "hidden participant" id is never linked to a player. No database.

Reported (Leederville, Oct 2026): Jonah Cumming held 48 games against CA's 12, in a dozen
grades, three of them on one day. `audit_player_games` showed 37 of the 49 were games whose
team sheets do not carry his id at all; the rows we hold for him are CA rows under
`00000000-0000-0000-0000-000000000001`, the one id CA gives EVERY redacted participant.

Cause: sync links a team-sheet entry whose id the club never stored to the club player with
the same full name (`participant_names.resolve_roster_by_name`) and writes that link into
`pid_by_guid`, the id lookup shared by every game in the run. For an ordinary participant id
that is right. For the placeholder it is not: once linked, EVERY later game's rows under that
id (any redacted player, either side) and every redacted entry on our team sheet were
credited to the one player.

Runs the SHIPPED `participant_names` (the same function sync, the relink script and the
scorecard page use).

Run:  python verification/verify_placeholder_participant.py
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


PLACEHOLDER = "00000000-0000-0000-0000-000000000001"
JONAH, ASH = uuid.uuid4(), uuid.uuid4()
NEW_ID = str(uuid.uuid4())
UNIQUE = {pn.full_name_key("Cumming, Jonah"): JONAH, pn.full_name_key("Ashton Taylor"): ASH}

# A team sheet where the club's own player appears under the shared id with his full name
# visible, next to a real player CA gave a fresh registration id.
SHEET = [
    {"participantId": PLACEHOLDER, "playerShortName": "Jonah Cumming"},
    {"participantId": NEW_ID, "playerShortName": "Ashton Taylor"},
    {"participantId": str(uuid.uuid4()), "playerShortName": "********"},
]

# presence-safe: report what came back rather than raising on a missing helper
is_placeholder = getattr(pn, "is_placeholder_id", None)
got = pn.resolve_roster_by_name(SHEET, {}, UNIQUE)

print("\n-- the placeholder id is never linked to a player --")
check("the shared id is not attached to Jonah by his visible name", PLACEHOLDER not in got, f"got {got}")
check("nothing is returned for it at all", got.get(PLACEHOLDER) is None)

print("\n-- the feature still works for a real id --")
check("a fresh registration id is still attached by full name", got.get(NEW_ID) == ASH, f"got {got}")

print("\n-- the id test itself --")
check("recognises the id CA uses", callable(is_placeholder) and is_placeholder(PLACEHOLDER))
check("recognises the neighbouring placeholder ...0002",
      callable(is_placeholder) and is_placeholder("00000000-0000-0000-0000-000000000002"))
check("a real participant id is not a placeholder", callable(is_placeholder) and not is_placeholder(NEW_ID))
check("a malformed id is not a placeholder, and does not raise",
      callable(is_placeholder) and not is_placeholder("not-a-uuid") and not is_placeholder(None) and not is_placeholder(""))

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
