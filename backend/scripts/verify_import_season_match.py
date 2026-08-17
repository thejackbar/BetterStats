"""Verify a season label can only ever match its own year.

The reported case: Hamilton Veterans' sheet runs back to 2010/11, the club held
only its three synced seasons, and the wizard auto-accepted "Summer 2020/21" as
"Summer 2023/24" at 0.86 confidence — over the 0.84 threshold. Season names are
near-identical strings by construction, so character similarity between two of
them says nothing at all.

Pure functions, no database:
  python3 backend/scripts/verify_import_season_match.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.import_ingest import match_seasons                  # noqa: E402

PASSES, FAILS = [], []


def check(label, got, want):
    (PASSES if got == want else FAILS).append(label)
    print(f"{'ok  ' if got == want else 'FAIL'} {label}: {got!r}" + ("" if got == want else f" (wanted {want!r})"))


def one(labels, seasons):
    return {lb: (m["status"], m.get("matched_name")) for lb, m in match_seasons(labels, seasons).items()}


# Hamilton's real season list, and the seasons its sheet carries that the club
# does not hold.
HAMILTON = [
    ("id-2010", "Summer 2010/11", 2010), ("id-2011", "Summer 2011/12", 2011),
    ("id-2012", "Summer 2012/13", 2012), ("id-2016", "Summer 2016/17", 2016),
    ("id-2017", "Summer 2017/18", 2017), ("id-2018", "Summer 2018/19", 2018),
    ("id-2019", "Summer 2019/20", 2019), ("id-2023", "Summer 2023/24", 2023),
    ("id-2024", "Summer 2024/25", 2024), ("id-2025", "Summer 2025/26", 2025),
]
SYNCED_ONLY = HAMILTON[-3:]
MISSING = ["Summer 2013/14", "Summer 2015/16", "Summer 2020/21", "Summer 2021/22", "Summer 2022/23"]

got = one(MISSING, HAMILTON)
check("a season the club does not hold matches nothing",
      sorted({s for s, _n in got.values()}), ["none"])
check("and is never handed another year",
      [n for _s, n in got.values()], [None] * len(MISSING))

got = one(MISSING, SYNCED_ONLY)
check("same when only the synced seasons exist — the reported case",
      sorted({s for s, _n in got.values()}), ["none"])
check("nothing lands on this season", [n for _s, n in got.values()], [None] * len(MISSING))

# Everything that should still match, still does.
ok = one(["Summer 2018/19", "18/19", "2018/19", "2018-19", "Summer 2018"], HAMILTON)
check("the club's own spellings all still resolve",
      [n for _s, n in ok.values()], ["Summer 2018/19"] * 5)
check("an exact name is still exact", ok["Summer 2018/19"][0], "exact")
check("a short form is a match, not a guess", ok["18/19"][0], "matched")

prior = match_seasons(["Prior seasons & adjustments", "Career total"], HAMILTON)
check("a career bucket still routes to the residual",
      [m["is_prior"] for m in prior.values()], [True, True])

# Two of the club's seasons carry the one year: a person picks, nothing is
# auto-accepted, and both are offered.
DUP = [("a", "Summer 2020/21", 2020), ("b", "Masters 2020/21", 2020)]
amb = match_seasons(["2020/21"], DUP)["2020/21"]
check("an ambiguous year is not auto-picked", amb["status"], "none")
check("but both same-year seasons are offered",
      sorted(c["name"] for c in amb["candidates"]), ["Masters 2020/21", "Summer 2020/21"])
clear = match_seasons(["Summer 2020/21"], DUP)["Summer 2020/21"]
check("naming one of them outright still resolves", clear["matched_name"], "Summer 2020/21")

# A label with no year at all keeps the old string matching — that is the only
# case where similarity between season names means anything.
noyear = match_seasons(["Summer"], [("x", "Summer", None)])["Summer"]
check("a label with no year still matches by name", noyear["status"], "exact")

# A season row whose year column is NULL but whose name carries the year (what
# a hand-created season looks like) is still found.
manual = match_seasons(["Summer 2021/22"], [("m", "Summer 2021/22", None)])["Summer 2021/22"]
check("a hand-created season with no year column still matches", manual["status"], "exact")
byname = match_seasons(["2021/22"], [("m", "Summer 2021/22", None)])["2021/22"]
check("and matches on the year read out of its name", byname["matched_name"], "Summer 2021/22")

print(f"\n{len(PASSES)} passed, {len(FAILS)} failed")
raise SystemExit(1 if FAILS else 0)
