"""How an absence is read, on both import paths.

A batter who never came in is scored differently by different competitions and
the difference lands in the average, so neither importer may assume. This
checks the one shared rule (`services/dismissal.absent_reading`), the
CricketStatz parser that reads it off a card, and the writer that applies the
club's answer for the one spelling that is genuinely ambiguous.

Run with a control (the previous commit, or the rule neutered) - every check
here is written so an absent feature is REPORTED rather than crashing the run.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PASS = FAIL = 0
MISSING: list[str] = []


def check(label: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"PASS  {label}")
    else:
        FAIL += 1
        print(f"FAIL  {label}\n        got  {got!r}\n        want {want!r}")


def report(label: str, why: str) -> None:
    global FAIL
    FAIL += 1
    MISSING.append(label)
    print(f"FAIL  {label}\n        not reachable: {why}")


def load(path: str, name: str):
    try:
        mod = __import__(path, fromlist=[name])
        return getattr(mod, name)
    except Exception as exc:                       # noqa: BLE001
        return exc


# ---------------------------------------------------------------------------
# 1. The one rule
# ---------------------------------------------------------------------------
absent_reading = load("app.services.dismissal", "absent_reading")
is_not_out = load("app.services.dismissal", "is_not_out")

if isinstance(absent_reading, Exception):
    report("the shared absent rule exists", str(absent_reading))
else:
    # What the card says outright is honoured whichever way the club answers.
    for flag in (False, True):
        check(f"'absent out' is a dismissal (bare_is_out={flag})",
              absent_reading("absent out", bare_absent_is_out=flag), "out")
        check(f"'absent hurt' is not an innings (bare_is_out={flag})",
              absent_reading("absent hurt", bare_absent_is_out=flag), "no_innings")
    # Only the bare word moves with the club's answer.
    check("a bare 'absent' defaults to Cricket Australia's reading",
          absent_reading("absent"), "no_innings")
    check("a bare 'absent' follows the club when they say out",
          absent_reading("absent", bare_absent_is_out=True), "out")
    # Spelling and spacing must not decide it.
    check("case and spacing do not change the reading",
          absent_reading("  Absent   Out "), "out")
    check("a comma spelling still reads as out",
          absent_reading("absent, out"), "out")
    # NEVER a prefix match: that is the whole bug this replaces.
    check("a real dismissal is not an absence",
          absent_reading("b Smith"), None)
    check("'did not bat' is not an absence (it has its own flag)",
          absent_reading("did not bat"), None)
    check("nothing at all is not an absence", absent_reading(None), None)

if isinstance(is_not_out, Exception):
    report("the not-out rule is reachable", str(is_not_out))
else:
    # An absent out is a DISMISSAL, so it must never read as a not out - that
    # would put it in the average's denominator the wrong way round.
    check("'absent out' is not a not out",
          is_not_out(dismissal_type="absent out"), False)
    check("'absent hurt' is not claimed as a not out either",
          is_not_out(dismissal_type="absent hurt"), False)


# ---------------------------------------------------------------------------
# 2. The CricketStatz parser transcribes, it does not decide
# ---------------------------------------------------------------------------
_parse = load("app.services.cricketstatz_parse", "_parse_dismissal")


def cell(text: str) -> str:
    return (f"<span class='ss_block'><span class='ss_howout'>{text}</span>"
            f"</span>")


if isinstance(_parse, Exception):
    report("the CricketStatz parser is reachable", str(_parse))
else:
    out = _parse(cell("absent out"))
    check("a card saying 'absent out' is NOT a did-not-bat",
          out.get("did_not_bat"), False)
    check("and it keeps its own label", out.get("dismissal_type"), "absent out")
    check("and it is reported as a dismissal",
          out.get("absent_reading"), "out")
    check("and it is not the ambiguous spelling",
          out.get("absent_unstated"), False)

    hurt = _parse(cell("absent hurt"))
    check("a card saying 'absent hurt' is a did-not-bat",
          hurt.get("did_not_bat"), True)
    check("and it is not the ambiguous spelling either",
          hurt.get("absent_unstated"), False)

    bare = _parse(cell("absent"))
    check("a bare 'absent' still defaults to a did-not-bat",
          bare.get("did_not_bat"), True)
    check("and it IS flagged as the ambiguous spelling",
          bare.get("absent_unstated"), True)

    # The neighbours must be untouched by any of this.
    check("'did not bat' is unchanged", _parse(cell("did not bat")).get("did_not_bat"), True)
    check("'not out' is unchanged", _parse(cell("not out")).get("not_out"), True)
    check("a retired out is unchanged",
          _parse(cell("retired out")).get("did_not_bat"), False)
    check("an ordinary dismissal is unchanged",
          _parse(cell("b Smith")).get("did_not_bat"), False)


# ---------------------------------------------------------------------------
# 3. The writer applies the club's answer, and ONLY to the ambiguous spelling
# ---------------------------------------------------------------------------
_dnb = load("app.services.cricketstatz_import", "_absent_did_not_bat")

if isinstance(_dnb, Exception):
    report("the writer's absent helper is reachable", str(_dnb))
else:
    explicit_out = {"did_not_bat": False, "absent_unstated": False}
    explicit_hurt = {"did_not_bat": True, "absent_unstated": False}
    ambiguous = {"did_not_bat": True, "absent_unstated": True}

    check("an explicit 'absent out' is an innings whatever the club answered",
          [_dnb(explicit_out, False), _dnb(explicit_out, True)], [False, False])
    check("an explicit 'absent hurt' is not, whatever the club answered",
          [_dnb(explicit_hurt, False), _dnb(explicit_hurt, True)], [True, True])
    check("a bare 'absent' is a did-not-bat when the club says so",
          _dnb(ambiguous, False), True)
    check("a bare 'absent' is an innings when the club says out",
          _dnb(ambiguous, True), False)
    check("an ordinary row is untouched by the club's answer",
          [_dnb({"did_not_bat": False}, False), _dnb({"did_not_bat": False}, True)],
          [False, False])
    check("a plain did-not-bat row is untouched too",
          [_dnb({"did_not_bat": True}, False), _dnb({"did_not_bat": True}, True)],
          [True, True])


# ---------------------------------------------------------------------------
# 4. The option really reaches the import, structurally
# ---------------------------------------------------------------------------
import inspect as _inspect

for mod_path, fn_name, arg in (
    ("app.services.cricketstatz_import", "run_import", "bare_absent_is_out"),
    ("app.services.cricketstatz_import", "import_match", "bare_absent_is_out"),
    ("app.services.cricketstatz_import", "_write_our_batting", "bare_absent_is_out"),
):
    fn = load(mod_path, fn_name)
    if isinstance(fn, Exception):
        report(f"{fn_name} is reachable", str(fn))
    else:
        check(f"{fn_name} takes the club's answer",
              arg in _inspect.signature(fn).parameters, True)

router_src = Path(__file__).resolve().parents[1] / "app/routers/cricketstatz.py"
src = router_src.read_text() if router_src.exists() else ""
check("the request carries the club's answer",
      "absent_reading" in src, True)
check("the route defaults to Cricket Australia's reading, so an unanswered "
      "import behaves as it always has",
      'absent_reading: Literal["did_not_bat", "out"] = "did_not_bat"' in src, True)
check("and it is threaded into the import",
      'bare_absent_is_out=body.absent_reading == "out"' in src, True)

parse_src = (Path(__file__).resolve().parents[1]
             / "app/services/cricketstatz_parse.py").read_text()
# Matched as the ASSIGNMENT, not the substring: the comment above the fix
# quotes the old line, and a check that matches its own explanation is a check
# that cannot fail.
check("the prefix match that swept 'absent out' in with 'absent hurt' is gone",
      'absent = key.startswith("absent")' in parse_src, False)
check("and the parser reads the shared rule instead",
      "absent_reading(key)" in parse_src, True)


print()
print(f"{PASS} passed, {FAIL} failed")
if MISSING:
    print("not reachable in this build:")
    for m in MISSING:
        print(f"  - {m}")
sys.exit(1 if FAIL else 0)
