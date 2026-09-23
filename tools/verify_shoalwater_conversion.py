"""Checks on the Shoalwater Bay CSFW conversion, against the files themselves.

The grade names and the match-type names are NOT in the .AV files - CSFW keeps
both lists somewhere a club's data export does not reach - so both maps in
`convert_shoalwater_av.py` are derived rather than read. This is what holds
them to the data.

Run with a control (the maps emptied, or an older converter) - every check
reports rather than raising, so a missing part is named instead of ending the
run.

    python3 tools/verify_shoalwater_conversion.py <folder of .AV files>
"""
from __future__ import annotations

import csv
import importlib.util
import re
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "backend"))

PASS = FAIL = 0


def check(label, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"PASS  {label}")
    else:
        FAIL += 1
        print(f"FAIL  {label}\n        got  {got!r}\n        want {want!r}")


def report(label, why):
    global FAIL
    FAIL += 1
    print(f"FAIL  {label}\n        not reachable: {why}")


def load(path, name):
    try:
        mod = __import__(path, fromlist=[name])
        return getattr(mod, name)
    except Exception as exc:                                   # noqa: BLE001
        return exc


spec = importlib.util.spec_from_file_location(
    "conv", HERE / "convert_shoalwater_av.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

src = Path(sys.argv[1] if len(sys.argv) > 1 else HERE.parent / "data/shoalwater-av")
files = sorted(p for p in src.iterdir() if p.suffix.lower() == ".av")
seasons = [m.parse_file(p) for p in files]
print(f"{len(files)} files, {len(seasons)} seasons, from {src}\n")

# ---------------------------------------------------------------------------
# 1. The grade map, re-derived from the raw team indexes
# ---------------------------------------------------------------------------
per_season = defaultdict(set)
all_teams = Counter()
for s in seasons:
    for mid, date, team, opp, legs in m.group_legs(s):
        per_season[s["season"]].add(team)
        all_teams[team] += 1

names = getattr(m, "GRADE_NAMES", {})
legacy = getattr(m, "LEGACY_GRADE_NAMES", {})
if not names:
    report("the converter carries a grade map", "GRADE_NAMES is empty or absent")
else:
    unmapped = sorted(t for t in all_teams if t not in names and t not in legacy)
    check("every team index in the archive has a name", unmapped, [])
    check("no grade reads as unmapped in the output",
          sorted({m.grade_label(t) for t in all_teams if "(unmapped)" in m.grade_label(t)}),
          [])

    # The club's own account, checked against the files rather than taken on
    # trust: two C sides in exactly four seasons, and no D grade in any of them.
    by_name = {s: sorted(m.grade_label(t) for t in ts) for s, ts in per_season.items()}
    two_c = sorted(s for s, g in by_name.items() if "C1 grade" in g)
    check("C1 appears in exactly the seasons the club named",
          two_c, ["1995/96", "2001/02", "2002/03", "2003/04"])
    check("C2 appears in the three of those that had a second side in CSFW",
          sorted(s for s, g in by_name.items() if "C2 grade" in g),
          ["2001/02", "2002/03", "2003/04"])
    check("none of those seasons also has a D grade",
          sorted(s for s in two_c if "D grade" in by_name[s]), [])
    check("D grade appears only where there is a single C grade",
          all("C grade" in by_name[s] for s in by_name if "D grade" in by_name[s]), True)
    check("1995/96 has no C2 in CSFW, which is why the text reports exist",
          "C2 grade" in by_name.get("1995/96", []), False)

# ---------------------------------------------------------------------------
# 2. The match-type map, against what the file says
# ---------------------------------------------------------------------------
types = getattr(m, "MATCH_TYPES", {})
finals = getattr(m, "FINALS_TYPES", frozenset())
if not types:
    report("the converter carries a match-type map", "MATCH_TYPES is empty or absent")
else:
    seen = Counter()
    two_day_seasons, two_day_grades = set(), set()
    for s in seasons:
        for mid, date, team, opp, all_legs in m.group_legs(s):
            legs = m.match_legs(all_legs)
            t = legs[0].get("type_code")
            seen[t] += 1
            if t == 1:
                two_day_seasons.add(s["season"])
                two_day_grades.add(m.grade_label(team))
    check("every match type in the archive has a name",
          sorted(t for t in seen if t not in types), [])
    # The club: "1993/94 & 1994/95 A grade played proper two day fixtures".
    check("two day cricket is A grade only", sorted(two_day_grades), ["A grade"])
    check("and only in the two seasons the club named",
          sorted(two_day_seasons), ["1993/94", "1994/95"])
    check("the finals types are the four that are finals",
          sorted(finals), [6, 7, 8, 9])

# ---------------------------------------------------------------------------
# 3. The format column is one the app can actually read
# ---------------------------------------------------------------------------
fmt_parse = load("app.services.grade_labels", "format_from_match_type")
rows = m.build_game_rows(seasons, seasons[0]["club"])
games = {}
for r in rows:
    games.setdefault((r["game_key"], r["season_name"]), r)

check("every match carries a format",
      sorted({g["match_format"] for g in games.values()}), ["One Day", "Two Day"])

if isinstance(fmt_parse, Exception):
    report("the app's own format parser is reachable", str(fmt_parse))
else:
    unreadable = sorted({g["match_format"] for g in games.values()
                         if fmt_parse(g["match_format"]) is None})
    check("and the app's own parser reads every one of them", unreadable, [])
    check("a finals name would NOT have been readable, which is why it is not "
          "written to that column",
          [fmt_parse("Grand Final"), fmt_parse("Qualifying Final")], [None, None])

check("the finals flag is set on the finals and nowhere else",
      sum(1 for g in games.values() if g["is_final"] == "true"), 36)

# A match with no scorecard still has a format and a finals flag - it takes a
# separate row path that the first cut left blank.
noscore = [g for g in games.values() if not g["player_name"]]
check("a match nobody was named for still carries its format",
      all(g["match_format"] for g in noscore), True)
check("and there are still twelve of them", len(noscore), 12)

# ---------------------------------------------------------------------------
# 4. The club's own match count
# ---------------------------------------------------------------------------
in_range = [g for g in games.values() if g["season_name"] != "2007/08"]
check("1992/93 to 2006/07 is the club's own 914 matches", len(in_range), 914)
check("2007/08 is one match and is reported separately",
      len(games) - len(in_range), 1)

# ---------------------------------------------------------------------------
# 5. The side with no scorebook
# ---------------------------------------------------------------------------
try:
    c2 = m.build_c2_season_rows(src, "1995/96", "C2 grade")
except Exception as exc:                                        # noqa: BLE001
    c2 = []
    print(f"      (C2 reports unreadable: {exc})")
if not c2:
    report("the 1995/96 C2 reports were read", "no rows came back")
else:
    check("nineteen C2 players", len(c2), 19)
    check("the placeholder overs column is dropped",
          sorted({r["Overs"] for r in c2}), [""])
    check("and so is the economy rate that would need it",
          sorted({r["Econ"] for r in c2}), [""])
    # Counted off the club's own report rather than from a number typed here:
    # a hand-written expectation is a check on my arithmetic, not on the code.
    real_bowlers = sum(
        1 for line in (src / "9596 c2 bowling.txt").read_text(encoding="utf-8-sig").splitlines()
        for cells in [line.split("\t")]
        if len(cells) > 7 and cells[1].strip() and cells[7].strip().isdigit()
        and int(cells[7]) > 0)
    check("wickets are kept for everyone the report shows taking one",
          sum(1 for r in c2 if r["Wickets"] not in ("", None)), real_bowlers)
    check("a player who never bowled carries no bowling figures at all",
          [(r["Wickets"], r["Runs Conceded"]) for r in c2
           if r["Player"] == "Mills, Clint"], [("", "")])
    top = [r for r in c2 if r["Player"] == "Norman, Dale"]
    check("the top scorer reads off the report",
          [(r["Runs"], r["HS"], r["50s"], r["Innings"], r["NO"]) for r in top],
          [(481, "87*", 4, 18, 3)])
    check("a not out high score keeps its star",
          sorted({r["HS"] for r in c2 if r["HS"].endswith("*")}),
          ["103*", "87*", "98*"])
    check("an unknown figure stays blank rather than becoming a zero",
          sorted({r["4s"] for r in c2}), [""])
    # It must exist in the season file and in NO match file.
    check("C2 1995/96 is in no match row",
          [r for r in rows if r.get("grade_name") == "C2 grade"
           and r["season_name"] == "1995/96"], [])

# ---------------------------------------------------------------------------
# 6. The sibling-file cross-check still means something
# ---------------------------------------------------------------------------
# The .FIX files are the club's PREVIOUS export and carry the old team
# numbering, so a check that compared the team number would read 0 of 34 on a
# season where every fixture matches. This asserts it compares the fixture's
# real identity instead.
xc = {r["Season"]: r for r in m.cross_check(src, seasons)}
checked = [r for r in xc.values() if r["Fixtures checked"]]
check("the sibling fixture files still agree with the .AV",
      all(r["Fixtures agreeing"] == r["Fixtures checked"]
          for r in checked if r["Season"] != "1995/96"), True)
check("and they are actually being checked, not skipped",
      sum(r["Fixtures checked"] for r in checked) > 500, True)

print()
print(f"{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
