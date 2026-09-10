#!/usr/bin/env python3
"""
Build the club review workbook and the consolidated import sheet from a
directory of CSFW `.av` season databases.

    python3 build_review_workbook.py <dir-of-.av-files> -o out/

Writes:
  match_detail.xlsx            - tabbed workbook for the club to review
  manual_games_scorecards.csv  - every match, in Manual Entries import shape
  by_season/manual_games_YYYY.csv - the same rows split per season

The split copies exist because the Manual Entries importer refuses an upload
over 8 MB (`_MAX_GAME_UPLOAD_BYTES`); the consolidated sheet is the master
record and the review copy, the per-season sheets are what actually load.
"""
import argparse, collections, csv, difflib, glob, os, sys
from csfw_format import Season, INN_SLOTS
from to_manual_games_csv import rows_for_file, COLUMNS, DISMISSAL, RESULT, season_name, person

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

ARIAL = "Arial"
HEAD_FILL = PatternFill("solid", fgColor="1F5C3D")
HEAD_FONT = Font(name=ARIAL, bold=True, color="FFFFFF", size=10)
BODY_FONT = Font(name=ARIAL, size=10)
TITLE_FONT = Font(name=ARIAL, bold=True, size=14)
NOTE_FONT = Font(name=ARIAL, size=10, italic=True, color="5C6862")


def sheet(wb, title, headers, rows, widths=None, freeze="A2"):
    ws = wb.create_sheet(title)
    ws.append(headers)
    for c in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill = HEAD_FILL; cell.font = HEAD_FONT
        cell.alignment = Alignment(vertical="center")
    for r in rows:
        ws.append(r)
    ws.freeze_panes = freeze
    if rows:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(rows)+1}"
    for i, w in enumerate(widths or [], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.sheet_view.zoomScale = 100
    return ws


def we_batted(inn) -> bool:
    """A recorded total, or anyone flagged as having batted.

    The total alone is not enough: one 2016 match records the opposition
    all out for 169 and one of our batsmen bowled for 0, with our own
    total never entered. Mirrors to_manual_games_csv.py, so the workbook
    and the CSV can never disagree about what we batted in.
    """
    return (inn['us']['total'] is not None
            or any(x['batted'] for x in inn['performances']))


def collect(paths):
    """One pass over every file, building every table the workbook needs."""
    roster_names = set()
    d = dict(seasons=[], matches=[], batting=[], bowling=[], fielding=[],
             opp=collections.Counter(), ven=collections.Counter(),
             codes=collections.defaultdict(lambda: dict(files=0, years=set(), matches=0)),
             players=collections.defaultdict(lambda: dict(
                 seasons=set(), matches=set(), inns=0, runs=0, no=0, hs=0,
                 balls=0, w=0, conc=0, ct=0, st=0)),
             gaps=[])
    for path in paths:
        S = Season(path)
        key = os.path.splitext(os.path.basename(path))[0]
        yr = int(S.year)
        ms = list(S.matches())
        d['seasons'].append([key, S.club, yr, season_name(S.year), len(ms),
                             len(S.players), S.per_side, S.balls_over,
                             S.notes or ""])
        for _pid, _pl in S.players.items():
            _nm = f"{_pl['surname']}, {_pl['initials']}".rstrip(', ').strip()
            if _nm:
                roster_names.add(_nm)
        c = d['codes'][S.club]
        c['files'] += 1; c['years'].add(yr); c['matches'] += len(ms)
        if len(ms) <= 3:
            d['gaps'].append([key, S.club, yr, len(ms),
                              "Season file holds 3 matches or fewer"])
        for m in ms:
            gk = f"{key}-{m['match_index']:03d}"
            first = m['innings'][0]
            us = first['us']; them = first['them']
            if m['opposition']: d['opp'][m['opposition']] += 1
            if m['venue']: d['ven'][m['venue']] += 1
            if not m['date']:
                d['gaps'].append([key, S.club, yr, 1, f"Match {gk} has no date"])
            d['matches'].append([
                gk, m['date'], S.club, yr, m['opposition'], m['venue'],
                m['result'] or "", m['margin_runs'], m['margin_wickets'],
                us['total'], us['wickets'], them['total'], them['wickets'],
                len(m['innings']), key])
            for inn in m['innings']:
                for p in inn['performances']:
                    nm = person(S, p['player_id'])
                    if not nm: continue
                    pl = d['players'][nm]
                    pl['seasons'].add(yr); pl['matches'].add(gk)
                    if p['batted'] and we_batted(inn):
                        pl['inns'] += 1; pl['runs'] += p['runs'] or 0
                        pl['no'] += 1 if p['not_out'] else 0
                        pl['hs'] = max(pl['hs'], p['runs'] or 0)
                        pl['balls'] += p['balls'] or 0
                        d['batting'].append([
                            gk, m['date'], yr, nm, inn['index'] % 2 + 1,
                            p['order'], p['runs'], p['balls'], p['minutes'],
                            p['fours'], p['sixes'],
                            "yes" if p['not_out'] else "no",
                            DISMISSAL.get(p['how_out_code'], ""),
                            "yes" if p['captain'] else "",
                            "yes" if p['keeper'] else ""])
                    if p['bowled']:
                        pl['w'] += p['wickets'] or 0; pl['conc'] += p['conceded'] or 0
                        d['bowling'].append([
                            gk, m['date'], yr, nm, inn['index'] % 2 + 1,
                            p['bowling_order'], p['overs'], p['balls_bowled'],
                            p['maidens'], p['conceded'], p['wickets'],
                            p['wides'], p['no_balls']])
                    if any([p['catches'], p['catches_wk'], p['stumpings'], p['byes_conceded']]):
                        pl['ct'] += (p['catches'] or 0) + (p['catches_wk'] or 0)
                        pl['st'] += p['stumpings'] or 0
                        d['fielding'].append([
                            gk, m['date'], yr, nm, p['catches'], p['catches_wk'],
                            p['stumpings'], p['byes_conceded'],
                            "yes" if p['keeper'] else ""])
    d['roster_names'] = roster_names
    return d


def near_duplicates(counter, cutoff=0.90):
    keys = list(counter)
    out = []
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            if abs(len(a) - len(b)) > 3: continue
            r = difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()
            if r >= cutoff and a.lower() != b.lower():
                out.append([round(r, 3), a, counter[a], b, counter[b]])
    out.sort(reverse=True)
    return out


def build(paths, outdir):
    os.makedirs(outdir, exist_ok=True)
    d = collect(paths)

    # ---- the two CSV shapes -------------------------------------------------
    by_year = collections.defaultdict(list)
    allrows = []
    for p in paths:
        for year, row in rows_for_file(p):
            by_year[year].append(row); allrows.append(row)
    cons = os.path.join(outdir, "manual_games_scorecards.csv")
    with open(cons, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in allrows: w.writerow({c: r.get(c, "") for c in COLUMNS})
    sub = os.path.join(outdir, "by_season"); os.makedirs(sub, exist_ok=True)
    for year in sorted(by_year):
        with open(os.path.join(sub, f"manual_games_{year}.csv"), "w",
                  newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
            w.writeheader()
            for r in by_year[year]: w.writerow({c: r.get(c, "") for c in COLUMNS})

    # ---- the workbook -------------------------------------------------------
    wb = Workbook()
    wb.remove(wb.active)

    codes = sorted(d['codes'].items(), key=lambda kv: -kv[1]['matches'])
    sheet(wb, "Team codes",
          ["Name stored in the file", "Season files", "First year", "Last year",
           "Matches", "What does this mean?  (please complete)"],
          [[k, v['files'], min(v['years']), max(v['years']), v['matches'], ""]
           for k, v in codes],
          [30, 13, 11, 11, 10, 44])

    sheet(wb, "Seasons",
          ["File", "Name stored in the file", "Year", "Season in BetterCricket",
           "Matches", "Players", "Players a side", "Balls an over", "Note in the file"],
          d['seasons'], [16, 24, 8, 20, 9, 9, 13, 13, 34])

    sheet(wb, "Matches",
          ["Match key", "Date", "Team as stored", "Year", "Opposition", "Ground",
           "Result", "Margin (runs)", "Margin (wkts)", "Our total", "Our wkts",
           "Their total", "Their wkts", "Innings recorded", "File"],
          d['matches'], [18, 11, 20, 7, 26, 26, 9, 13, 13, 10, 9, 11, 10, 15, 14])

    sheet(wb, "Batting",
          ["Match key", "Date", "Year", "Player", "Innings", "Position", "Runs",
           "Balls", "Minutes", "4s", "6s", "Not out", "How out", "Captain", "Keeper"],
          d['batting'], [18, 11, 7, 22, 8, 9, 7, 7, 8, 6, 6, 9, 12, 9, 8])

    sheet(wb, "Bowling",
          ["Match key", "Date", "Year", "Player", "Innings", "Bowling order",
           "Overs", "Balls", "Maidens", "Runs", "Wickets", "Wides", "No balls"],
          d['bowling'], [18, 11, 7, 22, 8, 13, 8, 7, 9, 7, 8, 7, 9])

    sheet(wb, "Fielding",
          ["Match key", "Date", "Year", "Player", "Catches", "Catches keeping",
           "Stumpings", "Byes conceded", "Keeper"],
          d['fielding'], [18, 11, 7, 22, 9, 15, 10, 14, 8])

    prows = []
    for nm, p in sorted(d['players'].items(), key=lambda kv: -kv[1]['runs']):
        outs = p['inns'] - p['no']
        prows.append([nm, len(p['seasons']), min(p['seasons']), max(p['seasons']),
                      len(p['matches']), p['inns'], p['runs'], p['hs'],
                      round(p['runs'] / outs, 2) if outs else None,
                      p['w'], round(p['conc'] / p['w'], 2) if p['w'] else None,
                      p['ct'], p['st']])
    sheet(wb, "Players", ["Player", "Seasons", "First", "Last", "Matches", "Innings",
                          "Runs", "HS", "Batting avg", "Wickets", "Bowling avg",
                          "Catches", "Stumpings"], prows,
          [24, 9, 8, 8, 9, 9, 8, 7, 12, 9, 12, 9, 11])

    # same surname and first initial, different stored name
    groups = collections.defaultdict(set)
    for nm in d['players']:
        sur, _, ini = nm.partition(",")
        groups[(sur.strip().lower(), ini.strip()[:1].lower())].add(nm)
    amb = []
    for (sur, ini), names in sorted(groups.items()):
        if len(names) < 2: continue
        for nm in sorted(names):
            p = d['players'][nm]
            amb.append([f"{sur.title()} {ini.upper()}", nm, len(p['matches']),
                        min(p['seasons']), max(p['seasons']), p['runs'], p['w'], ""])
    sheet(wb, "Name check",
          ["Group", "Name as stored", "Matches", "First", "Last", "Runs", "Wickets",
           "Same person?  (yes / no)"], amb, [16, 22, 9, 8, 8, 8, 9, 26])

    dups = near_duplicates(d['opp'])
    sheet(wb, "Opposition",
          ["Opposition", "Matches", "Looks like a typo of", "Its matches", "Similarity"],
          [[a, na, b, nb, r] for r, a, na, b, nb in dups] +
          [[k, v, "", "", ""] for k, v in sorted(d['opp'].items())
           if not any(k in (a, b) for _, a, _, b, _ in dups)],
          [30, 10, 30, 12, 11])

    sheet(wb, "Grounds", ["Ground", "Matches"],
          sorted(d['ven'].items(), key=lambda kv: -kv[1]), [34, 10])

    # matches recorded in two different season files
    seen = collections.defaultdict(list)
    for row in d['matches']:
        if row[1]: seen[(row[1], row[4], row[5])].append(row[14])
    cross = [[str(k[0]), k[1], k[2], ", ".join(sorted(set(v)))]
             for k, v in seen.items() if len(set(v)) > 1]
    gaps = d['gaps'] + [["", "", "", "", f"Match on {c[0]} vs {c[1]} at {c[2]} "
                         f"appears in two files: {c[3]}"] for c in cross]
    sheet(wb, "Data gaps", ["File", "Team as stored", "Year", "Matches", "What we found"],
          gaps, [16, 22, 8, 10, 70])

    # ---- summary, written last so it can point at real sheets ---------------
    ws = wb.create_sheet("Summary", 0)
    ws.column_dimensions['A'].width = 34
    ws.column_dimensions['B'].width = 18
    ws.column_dimensions['C'].width = 62
    def put(r, a, b=None, c=None, font=BODY_FONT):
        ws.cell(row=r, column=1, value=a).font = font
        if b is not None: ws.cell(row=r, column=2, value=b).font = BODY_FONT
        if c is not None: ws.cell(row=r, column=3, value=c).font = BODY_FONT
    put(1, "Payneham Cricket Club — recovered match archive", font=TITLE_FONT)
    put(2, "Read from 206 Cricket Statistics for Windows season files, 1928–2025.",
        font=NOTE_FONT)
    put(4, "What was recovered", font=Font(name=ARIAL, bold=True, size=11))
    # Literal counts, not =COUNTA() formulas. These describe a FROZEN extract:
    # nobody edits the Matches tab to change the match count, and if the source
    # files change the whole workbook is regenerated. A formula here would buy
    # nothing and cost verifiability — at 185k rows LibreOffice cannot
    # recalculate this workbook, so the cached values would ship as blanks to
    # anything that reads them. Each number is taken from the same list that
    # filled the tab it describes, so the two cannot disagree.
    figs = [("Season files", len(d['seasons']), "One per season, per team grouping"),
            ("Matches", len(d['matches']), "Every match with any detail recorded"),
            ("Batting innings", len(d['batting']), "Runs, balls, how out, boundaries"),
            ("Bowling spells", len(d['bowling']), "Overs, maidens, runs, wickets"),
            ("Fielding entries", len(d['fielding']), "Catches, stumpings, byes"),
            ("Players who appear in a match", len(d['players']),
             "Distinct names with a batting, bowling or fielding line"),
            ("Names in the club's player lists", len(d['roster_names']),
             "Every name entered, incl. those who never appear in a match")]
    for i, (lab, f, note) in enumerate(figs, start=5):
        put(i, lab, f, note)
    r = 5 + len(figs) + 1
    put(r, "What the old program never stored", font=Font(name=ARIAL, bold=True, size=11))
    for i, (a, b) in enumerate([
        ("Grade / which XI", "No field for it, and one file holds several teams — see the Team codes tab"),
        ("Opposition players", "Only their team name and innings total, so 'c Smith b Jones' is gone"),
        ("Run-outs", "Recorded against the batsman, but never credited to a fielder"),
        ("Who batted first", "No toss and no batting order, so innings order is our convention")],
        start=r + 1):
        ws.cell(row=i, column=1, value=a).font = BODY_FONT
        ws.cell(row=i, column=2, value=b).font = BODY_FONT
        ws.merge_cells(start_row=i, start_column=2, end_row=i, end_column=3)
    r = r + 6
    put(r, "Tabs to review", font=Font(name=ARIAL, bold=True, size=11))
    for i, (a, b) in enumerate([
        ("Team codes", "The most important one. Tell us what each stored name means."),
        ("Name check", "Names that differ only by a middle initial — same person, or two?"),
        ("Opposition", "Likely typos, listed against the spelling they resemble."),
        ("Data gaps", "Thin seasons, undated matches, and matches held in two files."),
        ("Matches / Batting / Bowling / Fielding", "The full record, for spot-checking."),
        ("Players", "Career totals as recovered — a good sanity check.")], start=r + 1):
        ws.cell(row=i, column=1, value=a).font = BODY_FONT
        ws.cell(row=i, column=2, value=b).font = BODY_FONT
        ws.merge_cells(start_row=i, start_column=2, end_row=i, end_column=3)
    ws.sheet_view.showGridLines = False

    for s in wb.worksheets:
        if s.title == "Summary": continue
        for row in s.iter_rows(min_row=2):
            for cell in row:
                cell.font = BODY_FONT
                if isinstance(cell.value, __import__('datetime').date):
                    cell.number_format = "yyyy-mm-dd"

    xl = os.path.join(outdir, "match_detail.xlsx")
    wb.save(xl)
    return cons, xl, len(allrows), d


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("-o", "--out", default="out")
    a = ap.parse_args()
    paths = [p for p in sorted(glob.glob(os.path.join(a.src, "*.av")))
             if not os.path.basename(p).startswith("._")]
    print(f"reading {len(paths)} files")
    cons, xl, n, d = build(paths, a.out)
    print(f"  {os.path.basename(cons)}  {os.path.getsize(cons)/1024/1024:.1f} MB  ({n} rows)")
    print(f"  {os.path.basename(xl)}  {os.path.getsize(xl)/1024/1024:.1f} MB")
    print(f"  by_season/  {len(glob.glob(os.path.join(a.out,'by_season','*.csv')))} sheets")
