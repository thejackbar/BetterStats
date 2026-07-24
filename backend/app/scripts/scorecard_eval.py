"""Golden-set eval for the AI scorecard reader (Upload Historical Scorecard).

Measures extraction accuracy against admin-verified transcriptions, so a prompt or
model change to app/services/scorecard_ocr.py is judged by a score moving, not by
eyeballing one card. Run it before and after any reader change.

Layout: a cases directory (NOT committed to the repo — scorecards carry names and
the scans are big), one sub-folder per match:

    scorecard-eval-cases/
      1976-10-02-railways/
        expected.json            # the verified truth, shape below
        page1.jpg  page2.jpg ... # and/or a .pdf — sorted by filename, fed in order

expected.json — the same shape extract_scorecard returns, plus our_club:

    {
      "our_club": "Metropolitans",
      "match": {"date": "1976-10-02", "venue": "Downlands", "balls_per_over": 8},
      "innings": [
        {
          "innings_number": 1, "batting_team": "Metropolitans", "is_our_team": true,
          "total_runs": 172, "total_wickets": 10,
          "extras": {"byes": 9, "leg_byes": 1, "no_balls": 2},
          "batting": [
            {"name": "G Evans", "runs": 73, "how_out": "caught", "bowler": "I Houser"},
            ...
          ],
          "bowling": [{"name": "R Brownhalls", "overs": 13, "maidens": 3, "runs": 46, "wickets": 2}],
          "fielding": [{"name": "G Ellis", "catches": 3, "catches_wk": 3}],
          "fall_of_wickets": [{"wicket": 1, "score": 33}]
        }
      ]
    }

Only the keys present in expected.json are scored, so a partial truth file is fine:
start with names/runs/wickets and add detail as it gets verified. Rows are matched
by (normalised) name; a row the reader missed scores zero for all its expected keys.

Usage:
    cd backend
    python -m app.scripts.scorecard_eval <cases_dir> [case_name ...]

Requires ANTHROPIC_API_KEY (read via the app's settings, same as the server).
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

from app.services import scorecard_ocr

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".pdf"}


def norm_name(s: str | None) -> str:
    """'G. Evans' / 'EVANS, G' / 'g evans' → one comparable key (sorted tokens,
    initials reduced to their letter)."""
    toks = re.split(r"[^a-z]+", (s or "").lower())
    return " ".join(sorted(t for t in toks if t))


def norm_val(v):
    if isinstance(v, str):
        return re.sub(r"\s+", " ", v).strip().lower()
    if isinstance(v, float) and v == int(v):
        return int(v)
    return v


class Tally:
    def __init__(self):
        self.right = 0
        self.wrong = 0
        self.diffs: list[str] = []

    def check(self, label: str, expected, actual):
        if norm_val(expected) == norm_val(actual):
            self.right += 1
        else:
            self.wrong += 1
            self.diffs.append(f"  {label}: expected {expected!r}, read {actual!r}")

    @property
    def total(self):
        return self.right + self.wrong

    def pct(self):
        return 100.0 * self.right / self.total if self.total else 100.0


def compare_rows(tally: Tally, label: str, expected_rows: list, actual_rows: list, name_key="name"):
    if not expected_rows:
        return  # section not in the truth file (or verified empty) — nothing to score
    actual_by_name = {}
    for r in actual_rows or []:
        actual_by_name.setdefault(norm_name(r.get(name_key)), r)
    for exp in expected_rows or []:
        key = norm_name(exp.get(name_key))
        act = actual_by_name.get(key)
        row_label = f"{label} {exp.get(name_key)!r}"
        if act is None:
            # A missed row fails every expected key on it, the name included.
            for k in exp:
                tally.check(f"{row_label}.{k}", exp.get(k), None)
            continue
        for k, v in exp.items():
            if k == name_key:
                tally.right += 1  # matched by name
                continue
            tally.check(f"{row_label}.{k}", v, act.get(k))
    extra = [r.get(name_key) for r in (actual_rows or []) if norm_name(r.get(name_key)) not in {norm_name(e.get(name_key)) for e in (expected_rows or [])}]
    if extra:
        tally.diffs.append(f"  {label}: reader added rows not in the truth file: {extra}")


def compare_fow(tally: Tally, label: str, expected_rows: list, actual_rows: list):
    actual_by_wkt = {r.get("wicket"): r for r in (actual_rows or [])}
    for exp in expected_rows or []:
        act = actual_by_wkt.get(exp.get("wicket")) or {}
        for k, v in exp.items():
            if k == "wicket":
                continue
            tally.check(f"{label} wkt {exp.get('wicket')}.{k}", v, act.get(k))


def score_case(expected: dict, actual: dict) -> Tally:
    tally = Tally()
    exp_match = expected.get("match") or {}
    act_match = actual.get("match") or {}
    for k, v in exp_match.items():
        tally.check(f"match.{k}", v, act_match.get(k))

    act_inns = {i.get("innings_number"): i for i in (actual.get("innings") or [])}
    for exp_inn in expected.get("innings") or []:
        n = exp_inn.get("innings_number")
        team = exp_inn.get("batting_team") or f"innings {n}"
        act_inn = act_inns.get(n) or {}
        for k, v in exp_inn.items():
            if k in ("innings_number", "batting", "bowling", "fielding", "fall_of_wickets", "extras"):
                continue
            tally.check(f"{team}.{k}", v, act_inn.get(k))
        for k, v in (exp_inn.get("extras") or {}).items():
            tally.check(f"{team}.extras.{k}", v, (act_inn.get("extras") or {}).get(k))
        compare_rows(tally, f"{team} bat", exp_inn.get("batting"), act_inn.get("batting"))
        compare_rows(tally, f"{team} bowl", exp_inn.get("bowling"), act_inn.get("bowling"))
        compare_rows(tally, f"{team} field", exp_inn.get("fielding"), act_inn.get("fielding"))
        compare_fow(tally, f"{team} fow", exp_inn.get("fall_of_wickets"), act_inn.get("fall_of_wickets"))
    return tally


async def run_case(case_dir: Path) -> Tally | None:
    expected_path = case_dir / "expected.json"
    if not expected_path.exists():
        print(f"~ {case_dir.name}: no expected.json, skipped")
        return None
    expected = json.loads(expected_path.read_text())
    files = sorted(p for p in case_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    if not files:
        print(f"~ {case_dir.name}: no images/PDFs, skipped")
        return None

    images = [(p.read_bytes(), scorecard_ocr.guess_media_type(None, p.name)) for p in files]
    result = await scorecard_ocr.extract_scorecard(images, expected.get("our_club") or "")
    if not result.get("available"):
        print(f"✗ {case_dir.name}: extraction failed: {result.get('message')}")
        return None

    tally = score_case(expected, result)
    mark = "✓" if tally.pct() >= 95 else ("~" if tally.pct() >= 80 else "✗")
    print(f"{mark} {case_dir.name}: {tally.right}/{tally.total} fields right ({tally.pct():.1f}%)")
    for d in tally.diffs:
        print(d)
    if result.get("warnings"):
        print("  reconcile warnings: " + "; ".join(
            w["text"] if isinstance(w, dict) else str(w) for w in result["warnings"]))
    return tally


async def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cases_dir = Path(sys.argv[1])
    only = set(sys.argv[2:])
    case_dirs = sorted(
        d for d in cases_dir.iterdir()
        if d.is_dir() and (not only or d.name in only)
    )
    if not case_dirs:
        print(f"No case folders found in {cases_dir}")
        sys.exit(1)

    tallies = []
    for d in case_dirs:
        t = await run_case(d)
        if t:
            tallies.append(t)
    if tallies:
        right = sum(t.right for t in tallies)
        total = sum(t.total for t in tallies)
        print(f"\nOverall: {right}/{total} fields right ({100.0 * right / total:.1f}%) across {len(tallies)} case(s)")


if __name__ == "__main__":
    asyncio.run(main())
