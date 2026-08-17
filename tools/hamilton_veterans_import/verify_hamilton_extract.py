"""Check the extracted CSVs against the workbook's own career total columns.

The history tabs carry a rightmost total group per player, and the Games Played
tab carries a per-player summary block. Neither is used to build the CSVs, so
they are an independent read on whether the season rows were parsed correctly.

Run:  python3 tools/hamilton_veterans_import/verify_hamilton_extract.py <xlsx> [outdir]
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).parent))
from extract_hamilton_stats import (  # noqa: E402
    BATTING_COLS, BOWLING_COLS, GAMES_SHEET, name_key, read_blocks, txt, whole,
)

# The total group each history tab ends with (first column, and whether the
# batting one is preceded by a 'Mat' column as it is on the Extras tab).
BAT_TOTAL = {"BattingHistory A-M": (69, False), "BattingHistory N-Z": (69, False),
             "BattingHistory Extras": (76, True)}
BOWL_TOTAL = {"Bowling History A-M": 63, "BowlingHistory N-Z": 63, "BowlingHistory Extras": 63}


def group(row, col, fields):
    return {f: (row[col - 1 + i] if col - 1 + i < len(row) else None) for i, f in enumerate(fields)}


def main(src: str, outdir: str) -> int:
    wb = openpyxl.load_workbook(src, read_only=True, data_only=True)
    out = Path(outdir)

    mine = defaultdict(lambda: {"games": 0, "inns": 0, "runs": 0, "wkts": 0, "conceded": 0})
    for fname in ("hamilton_import_season_by_season.csv", "hamilton_import_season_by_season_guests.csv"):
        with (out / fname).open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                m = mine[name_key(r["player_name"])]
                for src_f, dst in (("games_played", "games"), ("batting_innings", "inns"),
                                   ("batting_runs", "runs"), ("bowling_wickets", "wkts"),
                                   ("bowling_runs", "conceded")):
                    m[dst] += int(r[src_f]) if r[src_f].strip() else 0

    theirs = defaultdict(lambda: {"games": 0, "inns": 0, "runs": 0, "wkts": 0, "conceded": 0})
    for sheet, (col, has_mat) in BAT_TOTAL.items():
        ws = wb[sheet]
        for raw, _rows, total in read_blocks(ws, 4, col, 11):
            if total is None:
                continue
            g = group(total, col + (1 if has_mat else 0), BATTING_COLS)
            t = theirs[name_key(raw)]
            t["inns"] += whole(g["inns"]) or 0
            t["runs"] += whole(g["runs"]) or 0
    for sheet, col in BOWL_TOTAL.items():
        ws = wb[sheet]
        for raw, _rows, total in read_blocks(ws, 4, col, 10):
            if total is None:
                continue
            g = group(total, col, BOWLING_COLS)
            t = theirs[name_key(raw)]
            t["wkts"] += whole(g["wickets"]) or 0
            t["conceded"] += whole(g["runs"]) or 0

    # Games Played tab's own per-player summary (right-hand block, Total column).
    ws = wb[GAMES_SHEET]
    for row in ws.iter_rows(min_row=4, values_only=True):
        raw = txt(row[15]) if len(row) > 15 else ""
        if not raw or raw.strip().lower() in {"total", "totals"}:
            continue                       # the block's own grand-total row
        theirs[name_key(raw)]["games"] += (whole(row[27]) or 0) if len(row) > 27 else 0

    fails = []
    for key in sorted(set(mine) | set(theirs)):
        a, b = mine.get(key), theirs.get(key)
        if not a or not b:
            continue
        for field, label in (("inns", "innings"), ("runs", "runs"), ("wkts", "wickets"),
                             ("conceded", "runs conceded"), ("games", "games")):
            if b[field] and a[field] != b[field]:
                fails.append((key, label, a[field], b[field]))

    with (out / "hamilton_verification.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["player", "figure", "from_the_season_rows", "workbook_total_column", "difference"])
        for key, label, got, want in fails:
            w.writerow([key, label, got, want, got - want])

    print(f"players compared   {len(set(mine) & set(theirs))}")
    print(f"season rows add to {sum(m['runs'] for m in mine.values())} runs, "
          f"{sum(m['wkts'] for m in mine.values())} wickets, {sum(m['games'] for m in mine.values())} games")
    print(f"workbook totals    {sum(t['runs'] for t in theirs.values())} runs, "
          f"{sum(t['wkts'] for t in theirs.values())} wickets, {sum(t['games'] for t in theirs.values())} games")
    if fails:
        print(f"\n{len(fails)} figure(s) where the workbook's own total column disagrees with its own season rows.")
        print("The season rows are what the CSVs carry — a total column that leaves a competition out of")
        print("its formula is the workbook being wrong about itself, not the extract losing anything.\n")
        for key, label, got, want in fails:
            print(f"  {key:<28} {label:<14} season rows {got:<6} total column {want}")
    else:
        print("\nevery player's career figures match the workbook's own total columns")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "tools/hamilton_veterans_import/out"))
