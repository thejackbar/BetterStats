"""Turn Payneham's 'Runs Galore' PDFs into BetterStats import files.

Outputs (all CSV, all ready for the matching admin screen):
  1_payneham_players.csv       -> /admin/import      (BetterImport)
  2_payneham_awards.csv        -> /admin/awards      (bulk import)
  3_payneham_partnerships.csv  -> /admin/partnerships
  4_payneham_team_records.csv  -> no home in the app yet (see the write-up)
"""
import csv
import re
from collections import defaultdict

from tables import (layout, bands, gutter_bands, snap_bands, cells, tidy_name, is_name, season_from_date,
                    season_label, to_int, to_float, SEASON_RE)

V1, V2 = "rg1.pdf", "rg2.pdf"

# The running header at the top of each page names the section it belongs to.
SECTION_RE = re.compile(
    r"^(WHOLE OF CLUB|[0-9]?[a-z]{0,2}\s*(?:XI|IX)?\s*[A-Z0-9' ]*COMPETITION[^\n]*|"
    r"UNDER\s*\d+[^\n]*|JUNIOR GIRLS[^\n]*|COLTS[^\n]*|FRIENDL[^\n]*)$")

TEAM_ALIASES = {
    "1st XI REGULAR COMPETITION": "1st XI",
    "2nd XI REGULAR COMPETITION": "2nd XI",
    "3rd XI REGULAR COMPETITION": "3rd XI",
    "4th XI REGULAR COMPETITION": "4th XI",
    "LIMITED OVER COMPETITION": "Limited Overs XI",
    "1st XI T20 COMPETITIONS": "1st XI T20",
    "2nd XI T20 COMPETITIONS": "2nd XI T20",
    "3rd XI T20 COMPETITION": "3rd XI T20",
    "WOMENS 1st IX T20 COMPETITION": "Women's 1st IX T20",
    "WOMENS 2nd IX T20 COMPETITION": "Women's 2nd IX T20",
    "JUNIOR GIRLS COMPETITIONS": "Junior Girls",
    "FIRST XI BROCK CUP COMPETITION": "1st XI Brock Cup",
}


def pages(pdf):
    return layout(pdf).split("\f")


def section_of(page):
    """The running header at the top of a page, normalised to a team label.

    Every page of a team's section repeats the same header ('4th XI REGULAR
    COMPETITION – 1956/57 > > >'), so the header is what says which team a table
    on that page belongs to.
    """
    for ln in page.split("\n")[:6]:
        s = re.sub(r"\s+", " ", ln.strip())
        if not s or len(s) > 110:
            continue
        s = re.sub(r"[–—-]\s*\d{4}/\d{2}.*$", "", s).strip()   # drop '– 1932/33 > > >'
        s = re.sub(r"[.…>\s]+$", "", s).strip()
        up = s.upper()
        if up == "WHOLE OF CLUB":
            return "Whole of Club"
        for key, label in TEAM_ALIASES.items():
            if up.startswith(key.upper()):
                return label
        m = re.match(r"^(\d+)(?:ST|ND|RD|TH)\s+(XI|IX)\b(.*)$", up)
        if m and ("COMPETITION" in up or "CUP" in up):
            n = int(m.group(1))
            suffix = "st" if n % 10 == 1 and n != 11 else \
                     "nd" if n % 10 == 2 and n != 12 else \
                     "rd" if n % 10 == 3 and n != 13 else "th"
            kind = " T20" if "T20" in up or "20/20" in up else ""
            return f"{n}{suffix} {m.group(2)}{kind}"
        m = re.match(r"^WOMEN'?S\s+(\d+)(?:ST|ND|RD|TH)\s+(XI|IX)\b", up)
        if m and "COMPETITION" in up:
            return f"Women's {m.group(1)}{'st' if m.group(1) == '1' else 'nd'} {m.group(2)} T20"
        if up.startswith("COLTS"):
            return "Colts"
        if re.match(r"^UNDER\s*\d+", up):
            return re.sub(r"\s+", " ", s.title())
        if up.startswith("FRIENDL"):
            return "Friendlies"
    return None


def sectioned(pdf):
    """[(team_label, page_text)] — a page with no header inherits the one above."""
    out, current = [], None
    for p in pages(pdf):
        sec = section_of(p)
        if sec:
            current = sec
        if current:
            out.append((current, p))
    return out


def table(page, heading, header_hint):
    """Return the rows under `heading` on this page as dicts keyed by column name.

    Finds the heading, takes the next line carrying `header_hint` as the column
    header, then reads fixed-width rows until the table stops.
    """
    lines = page.split("\n")
    for i, ln in enumerate(lines):
        if ln.strip().upper() != heading.upper():
            continue
        hdr_i = next((j for j in range(i + 1, min(i + 6, len(lines)))
                      if header_hint.lower() in lines[j].lower()), None)
        if hdr_i is None:
            continue
        body, blanks = [], 0
        for ln2 in lines[hdr_i + 1:]:
            if not ln2.strip():
                blanks += 1
                if blanks >= 4 and body:
                    break
                continue
            if re.match(r"^\s*[A-Z][A-Z /&()'0-9-]{6,}\s*$", ln2.rstrip()) and body:
                break
            blanks = 0
            body.append(ln2)
        # Trim to the run of ranked rows before measuring columns: the table below
        # this one has its own widths, and letting its lines into the measurement
        # narrows this table's name column and clips 'DJ Von Einem' to 'DJ Von Ein'.
        data, gap = [], 0
        for ln2 in body:
            if re.match(r"^\s*[\d,]+\*?\s", ln2):
                data.append(ln2)
                gap = 0
            elif data:
                # A wrapped footnote sits between two ranked rows ('++ also played 3
                # / seasons pre 1938'), so one stray line is not the end of the table.
                gap += 1
                if gap >= 2:
                    break
        body = data or body
        if not body:
            return []
        cols = snap_bands(lines[hdr_i], body)
        if not cols:
            return []
        key = cols[0][0]
        rows = []
        for ln2 in body:
            row = cells(ln2, cols)
            first = (row.get(key) or "").strip()
            if not first:
                continue                      # a footnote hanging off a later column
            # Every one of these tables is ranked by a number in its first column;
            # the first row that isn't one has left the table.
            if not re.fullmatch(r"[\d,]+\*?", first):
                if rows:
                    break
                continue
            rows.append(row)
        return rows
    return []


# ── 1. Career stats -> BetterImport ──────────────────────────────────────────

def career_rows(secs):
    """Whole-of-club career aggregates, merged per player.

    Only the WHOLE OF CLUB section is used. Its figures already cover every
    competition, so adding the per-team lists on top would count them twice.
    """
    club, per_team = defaultdict(dict), defaultdict(lambda: defaultdict(dict))

    def read(page, into):
        def put(name, **kw):
            if not is_name(name):
                return
            rec = into[name]
            for k, v in kw.items():
                if v not in (None, "") and k not in rec:
                    rec[k] = v

        for r in table(page, "LEADING RUNSCORERS", "Runs"):
            put(tidy_name(r.get("Name")), matches=to_int(r.get("Mch")),
                innings=to_int(r.get("Inn")), runs=to_int(r.get("Runs")),
                not_outs=to_int(r.get("NO")), hs=(r.get("HS") or "").strip(),
                avg=to_float(r.get("Ave")))
        for r in table(page, "LEADING WICKET TAKERS", "Wkts"):
            balls = to_int(r.get("Balls"))
            put(tidy_name(r.get("Name")), wickets=to_int(r.get("Wkts")),
                overs=(f"{balls // 6}.{balls % 6}" if balls else None),
                conceded=to_int(r.get("Runs")), bowl_avg=to_float(r.get("Ave")))
        for r in table(page, "MOST DISMISSALS", "Ctch"):
            put(tidy_name(r.get("Name")), catches=to_int(r.get("Ctch")),
                stumpings=to_int(r.get("Stump")))

    for team, page in secs:
        read(page, club if team == "Whole of Club" else per_team[team])

    # Per-competition figures are NOT added into the career row. Summing them
    # disagrees with the book's own whole-of-club lists (HJ Davis reads 768 wickets
    # across two competitions but is nowhere in the club top ten), and a made-up
    # career total is worse than none. They go out as a reference file instead.
    return club, per_team


def caps_rows(pdf=V1):
    """The First XI cap list — every 1st XI player, with the season they debuted."""
    text = layout(pdf, 138, 143)
    out = {}
    for ln in text.split("\n"):
        # 'cap-no  Name  1932/33', repeated up to three times across the line.
        for m in re.finditer(r"(?:(\d{1,3})\s+)?([A-Z][A-Za-z .'’()\-]{2,28}?)\s{2,}(\d{4})/(\d{2})", ln):
            name = tidy_name(m.group(2))
            if not is_name(name) or name.upper().startswith(("CAP", "PLAYER")):
                continue
            season = f"{m.group(3)}/{m.group(4)}"
            if name not in out or (m.group(1) and not out[name][0]):
                out[name] = (m.group(1), season)
    return out


# ── 2. Awards ────────────────────────────────────────────────────────────────

def captain_rows(secs):
    """CAPTAINS tables -> Office Bearer achievements, one per season per team."""
    out = []
    for team, page in secs:
        lines = page.split("\n")
        for i, ln in enumerate(lines):
            if ln.strip().upper() != "CAPTAINS":
                continue
            for ln2 in lines[i + 1:]:
                if re.match(r"^\s*[A-Z][A-Z /&()'-]{8,}$", ln2.rstrip()):
                    break
                for m in re.finditer(r"(\d{4})/(\d{2})\s+([A-Za-z][A-Za-z .'’\-]{2,26}?)(?=\s{2,}|\*|/|$)", ln2):
                    name = tidy_name(m.group(3))
                    if is_name(name):
                        out.append((f"{m.group(1)}/{m.group(2)}", team, name))
    return out


def hat_trick_rows(secs):
    out = []
    for team, page in secs:
        for r in table(page, "HAT TRICKS", "Versus"):
            name = tidy_name(r.get("Name"))
            if not is_name(name):
                continue
            yr = season_from_date(r.get("Date"))
            out.append((season_label(yr), team, name, (r.get("Versus") or "").strip()))
    return out


# ── 3. Partnerships ──────────────────────────────────────────────────────────

def pair_split(cells_text):
    """Where the 'Batsmen' column splits into two names.

    A name can carry wide internal spacing ('PJ    Richardson'), so the gap between
    the two batters is found by taking the position that reads as a gap on the most
    rows of the table rather than by splitting on whitespace one row at a time.
    """
    votes = defaultdict(int)
    for txt in cells_text:
        for m in re.finditer(r"\s{2,}", txt):
            if txt[:m.start()].strip() and txt[m.end():].strip():
                for x in range(m.start(), m.end()):
                    votes[x] += 1
    if not votes:
        return None
    best = max(votes.values())
    # The rightmost position shared by the most rows: names are left-aligned, so a
    # narrow first name still leaves the real gutter covered.
    return max(x for x, n in votes.items() if n == best)


def partnership_tables(secs):
    """Every 'BEST (WICKET) PARTNERSHIPS' table in the book, whole-club and per team."""
    out = []
    for team, page in secs:
        lines = page.split("\n")
        for i, ln in enumerate(lines):
            if ln.strip().upper() not in ("BEST PARTNERSHIPS", "BEST WICKET PARTNERSHIPS"):
                continue
            hdr_i = next((j for j in range(i + 1, min(i + 5, len(lines)))
                          if "batsmen" in lines[j].lower()), None)
            if hdr_i is None:
                continue
            body, blanks = [], 0
            for ln2 in lines[hdr_i + 1:]:
                if not ln2.strip():
                    blanks += 1
                    if blanks >= 3 and body:
                        break
                    continue
                if re.match(r"^\s*[A-Z][A-Z /&()'0-9-]{6,}\s*$", ln2.rstrip()) and body:
                    break
                blanks = 0
                body.append(ln2)
            if not body:
                continue
            spans, named = gutter_bands(lines[hdr_i], body)
            look = {k.lower(): v for k, v in named.items()}
            # 'Wkt Score' is sometimes set with one space and reads as one heading;
            # in that case the two leading spans are the wicket and the score.
            if "score" not in look and "wkt score" in look:
                lo, hi = look.pop("wkt score")
                at = lines[hdr_i].index("Score", lo)
                look["wkt"], look["score"] = (lo, at), (at, hi)
            if "score" not in look or "date" not in look:
                continue
            opp_span = next((v for k, v in look.items() if k.startswith("oppos")), None)
            # Everything between the score and the opposition is the two batters.
            mids = [s for s in spans if s[0] >= look["score"][1]
                    and (opp_span is None or s[1] <= opp_span[0])]
            if len(mids) < 2:
                continue
            wicket = None
            for ln2 in body:
                c = cells(ln2, [(k, lo, hi) for k, (lo, hi) in look.items()])
                w = to_int(c.get("wkt"))
                if w and 1 <= w <= 10:
                    wicket = w
                m = re.match(r"^(\d{1,3})(\*?)$", (c.get("score") or "").strip())
                if not (m and wicket):
                    continue
                b1 = tidy_name(ln2[mids[0][0]:mids[0][1]]).rstrip("/ ")
                b2 = tidy_name(" ".join(ln2[s[0]:s[1]] for s in mids[1:])).split("/")[0].strip()
                if not (is_name(b1) and is_name(b2)):
                    continue
                date = c.get("date", "")
                opp = ln2[opp_span[0]:opp_span[1]].strip() if opp_span else ""
                grade = c.get("team", "") or team
                yr = season_from_date(date)
                out.append({
                    "Batter 1": b1, "Batter 2": b2, "Runs": int(m.group(1)),
                    "Wicket": wicket, "Season": yr or "",
                    "Not Out": "Yes" if m.group(2) else "No",
                    "Grade": tidy_name(grade) or team,
                    "Opposition": re.sub(r"\s+", " ", opp).strip(),
                })
    seen, uniq = set(), []
    for r in out:
        r["Grade"] = normalise_grade(r["Grade"])
        k = (r["Batter 1"], r["Batter 2"], r["Runs"], r["Wicket"], r["Season"])
        if k not in seen:
            seen.add(k)
            uniq.append(r)
    return uniq


GRADE_FIXES = {"2ndxi": "2nd XI", "1stxi": "1st XI", "3rdxi": "3rd XI",
               "u14 gold": "Under 14", "u14": "Under 14", "u15": "Under 15",
               "u16": "Under 16", "u17": "Under 17", "w1st ix": "Women's 1st IX"}


def normalise_grade(g):
    g = re.sub(r"\s+", " ", (g or "").strip())
    fixed = GRADE_FIXES.get(g.lower())
    if fixed:
        return fixed
    m = re.match(r"^(\d+)(?:st|nd|rd|th)\s*(XI|IX)$", g, re.I)
    if m:
        n = int(m.group(1))
        suf = "st" if n == 1 else "nd" if n == 2 else "rd" if n == 3 else "th"
        return f"{n}{suf} {m.group(2).upper()}"
    return g


def partnership_rows(secs):
    """WHOLE OF CLUB 'BEST WICKET PARTNERSHIPS' -> manual partnership records.

    Wicket number is printed once and carried down its run of rows, as the book
    prints it. A stand with a '/' (a partnership continued by a third batter) is
    kept as the pair actually named on that line.
    """
    out = []
    for team, page in secs:
        if team != "Whole of Club":
            continue
        lines = page.split("\n")
        start = next((i for i, ln in enumerate(lines)
                      if ln.strip().upper() == "BEST WICKET PARTNERSHIPS"), None)
        body = lines[start:] if start is not None else (
            lines if "…continued" in page or re.search(r"^\s*\d{1,2}\s+\d{2,3}\*?\s+[A-Z]", page, re.M) else [])
        wicket = None
        for ln in body:
            m = re.match(
                r"^\s*(?:(\d{1,2})\s+)?(\d{2,3})(\*?)\s+"
                r"([A-Z][A-Za-z .'’\-]{2,24}?)\s{2,}"
                r"([A-Z][A-Za-z .'’\-]{2,24}?)\s*/?\s{2,}"
                r"(.{3,30}?)\s{2,}(.{3,14}?)\s{2,}([A-Za-z]{3}-\d{2})\s*$", ln)
            if not m:
                continue
            if m.group(1):
                wicket = int(m.group(1))
            if not wicket:
                continue
            b1, b2 = tidy_name(m.group(4)), tidy_name(m.group(5))
            if not (is_name(b1) and is_name(b2)):
                continue
            yr = season_from_date(m.group(8))
            out.append({
                "Batter 1": b1, "Batter 2": b2, "Runs": int(m.group(2)),
                "Wicket": wicket, "Season": yr or "",
                "Not Out": "Yes" if m.group(3) else "No",
                "Grade": normalise_grade(tidy_name(m.group(7))) or "Whole of Club",
                "Opposition": (m.group(6) or "").strip(),
            })
    return out


# ── 4. Team records (no home in the app yet) ─────────────────────────────────

TOTAL_TABLES = [
    ("HIGHEST INNINGS TOTAL", "Highest innings total", "for"),
    ("LOWEST COMPLETED INNINGS TOTAL", "Lowest completed innings total", "for"),
    ("LOWEST 20 OVER INNINGS TOTAL", "Lowest 20-over innings total", "for"),
    ("HIGHEST INNINGS TOTAL AGAINST", "Highest innings total against", "against"),
    ("LOWEST COMPLETED INNINGS TOTAL AGAINST", "Lowest completed innings total against", "against"),
    ("LOWEST 20 OVER INNINGS TOTAL AGAINST", "Lowest 20-over innings total against", "against"),
]


VENUE_RE = re.compile(r"^[A-Z][A-Z .'&-]*(OVAL|RESERVE|PARK|GROUND|H S|SCHOOL|COLL[A-Z.]*)\b[A-Z .'&-]*$")


def venue_scope(lines, i):
    """The venue heading a records table sits under, if it is a per-ground table.

    'HIGHEST INNINGS TOTAL' appears once for the club and again under each ground
    the club plays at. The ground's name is the nearest heading above it, so the
    two can be told apart instead of a ground record reading as a club record.
    """
    for ln in reversed(lines[max(0, i - 4):i]):
        s = ln.strip()
        if not s:
            continue
        if VENUE_RE.match(re.sub(r"\s{2,}.*$", "", s)):
            return re.sub(r"\s+", " ", re.sub(r"\s{2,}.*$", "", s)).title()
        return None
    return None


def team_record_rows(secs):
    """The 'Score / Versus / Date' tables — the page the club sent as a screenshot.

    Two of these sit side by side on a page, so each heading claims the horizontal
    band from its own x up to the next heading's, and the column header inside that
    band drives the field positions.
    """
    out = []
    for team, page in secs:
        lines = page.split("\n")
        for i, ln in enumerate(lines):
            up = ln.rstrip().upper()
            hits = sorted({(m.start(), key, label, side)
                           for key, label, side in TOTAL_TABLES
                           for m in re.finditer(re.escape(key) + r"(?!\s*AGAINST)", up)})
            for n, (lo, key, label, side) in enumerate(hits):
                hi = hits[n + 1][0] if n + 1 < len(hits) else 10_000
                hdr_i = next((j for j in range(i + 1, min(i + 5, len(lines)))
                              if re.search(r"\bScore\b", lines[j][lo:hi])
                              and re.search(r"\bDate\b", lines[j][lo:hi])), None)
                if hdr_i is None:
                    continue
                # Measure the columns against the rows themselves — a long opponent
                # ('Richmond Clarence Pk') runs past the midpoint to the Date
                # heading, and a midpoint band would cut the date off with it.
                band = [ln2[lo:hi] for ln2 in lines[hdr_i + 1:hdr_i + 18]]
                body = [b for b in band if re.match(r"^\s*\*?\s*[\d,]+\s", b)]
                cols = snap_bands(lines[hdr_i][lo:hi], body)
                # The club-vs-opponent table is exactly Score / Versus (or by) /
                # Date. The individual HIGHEST SCORES tables carry a Name and a
                # Venue as well, and would otherwise read as team totals.
                if [c[0].lower() for c in cols] not in (["score", "versus", "date"],
                                                        ["score", "by", "date"],
                                                        ["score", "versus", "team", "date"],
                                                        ["score", "by", "team", "date"]):
                    continue
                misses = 0
                for ln2 in lines[hdr_i + 1:hdr_i + 18]:
                    c = cells(ln2[lo:hi], cols)
                    score = (c.get("Score") or "").strip().lstrip("* ")
                    opp = c.get("Versus") or c.get("by") or ""
                    date = (c.get("Date") or "").strip()
                    ok = (re.fullmatch(r"\d{1,2}[-–—]{1,2}\d{1,3}|\d{1,3}", score)
                          and re.fullmatch(r"[A-Za-z]{3}-\d{2,4}", date))
                    if not ok:
                        misses += 1 if ln2[lo:hi].strip() else 0
                        if misses >= 3:
                            break     # well past the end of this table
                        continue
                    misses = 0
                    out.append({
                        "Team": team, "Scope": venue_scope(lines, i) or "Club",
                        "Record": label, "Side": side,
                        "Score": re.sub(r"[-–—]{1,2}", "/", score),
                        "Opponent": re.sub(r"\s+", " ", opp).strip(),
                        "Grade": re.sub(r"\s+", " ", c.get("Team", "")).strip(),
                        "Month": date, "Season": season_label(season_from_date(date)),
                    })
    seen, uniq = set(), []
    for r in out:
        k = (r["Team"], r["Scope"], r["Record"], r["Score"], r["Opponent"], r["Month"])
        if k not in seen:
            seen.add(k)
            uniq.append(r)
    return uniq


def margin_rows(secs):
    out = []
    for team, page in secs:
        lines = page.split("\n")
        for i, ln in enumerate(lines):
            up = ln.strip().upper()
            if not up.startswith(("HIGHEST OUTRIGHT WINNING MARGIN", "HIGHEST OUTRIGHT LOSING MARGIN")):
                continue
            kind = "winning" if "WINNING" in up else "losing"
            basis = ""
            for ln2 in lines[i + 1:i + 40]:
                s = ln2.strip()
                if re.match(r"^By (Innings plus|Runs|Wickets)$", s, re.I):
                    basis = s.title()
                    continue
                m = re.match(
                    r"^\s*(Innings & [\d,]+ runs|[\d,]+ runs|\d+ wickets?)\s+"
                    r"([A-Za-z]{3}-\d{4})\s+(.+?)\s+def\.?(?:\s+by)?\s+(.+?)\s{2,}(.+)$", ln2)
                if not m:
                    continue
                out.append({
                    "Team": team, "Record": f"Highest outright {kind} margin",
                    "Basis": basis or "", "Margin": m.group(1),
                    "Month": m.group(2), "Season": season_label(season_from_date(m.group(2))),
                    "Payneham score": re.sub(r"\s{2,}", " ", m.group(3)).strip(),
                    "Opponent": re.sub(r"\s{2,}", " ", m.group(4)).strip(),
                    "Opponent score": re.sub(r"\s{2,}", " ", m.group(5)).strip(),
                })
            continue
    return out


# ── write ────────────────────────────────────────────────────────────────────

def main():
    secs = sectioned(V1) + sectioned(V2)

    # 1 — players
    agg, per_team = career_rows(secs)
    caps = caps_rows()
    with open("1_payneham_players.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Player", "Season", "Grade", "Games", "Innings", "Runs", "NO", "HS",
                    "Avg", "Wickets", "Overs", "Runs Conceded", "Bowl Avg", "Catches",
                    "Stumpings", "Notes"])
        names = sorted(set(agg) | set(caps))
        for n in names:
            a = agg.get(n, {})
            cap, first = caps.get(n, (None, ""))
            note = f"1st XI cap #{cap}, debut {first}" if cap else (
                f"1st XI debut {first}" if first else "")
            w.writerow([n, "Prior Seasons & Adjustments", "",
                        a.get("matches", ""), a.get("innings", ""), a.get("runs", ""),
                        a.get("not_outs", ""), a.get("hs", ""),
                        a.get("avg", ""),
                        a.get("wickets", ""), a.get("overs", ""), a.get("conceded", ""),
                        a.get("bowl_avg", ""), a.get("catches", ""), a.get("stumpings", ""),
                        note])
    print(f"1_payneham_players.csv        {len(names):5d} players "
          f"({len(agg)} with career figures, {len(caps)} with a 1st XI cap)")

    # 2 — awards: club trophies (from parse_awards) + captains + hat tricks
    club = list(csv.reader(open("out_awards_club.csv")))[1:]
    caps_seen = set()
    rows = [r for r in club]
    for season, team, name in captain_rows(secs):
        k = (season, team, name)
        if k in caps_seen:
            continue
        caps_seen.add(k)
        rows.append([season, "Office Bearer", "Captains", f"{team} Captain", name, ""])
    for season, team, name, opp in hat_trick_rows(secs):
        rows.append([season, "Milestone", "Hat Tricks", "Hat Trick", name,
                     f"{team}{' v ' + opp if opp else ''}".strip()])
    for name, (cap, first) in sorted(caps.items(), key=lambda kv: int(kv[1][0] or 9999)):
        if cap:
            rows.append([first, "Milestone", "First XI Caps", "First XI Cap", name, f"#{cap}"])
    rows.sort(key=lambda r: (r[1], r[3], r[0]))
    with open("2_payneham_awards.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Season", "Category", "Subcategory", "Achievement", "Player Name", "Detail"])
        w.writerows(rows)
    print(f"2_payneham_awards.csv         {len(rows):5d} rows "
          f"({len(club)} club trophies, {len(caps_seen)} captaincies)")

    # 3 — partnerships
    pr = partnership_tables(secs)
    seen = {(r["Batter 1"], r["Batter 2"], r["Runs"], r["Wicket"], r["Season"]) for r in pr}
    for r in partnership_rows(secs):
        k = (r["Batter 1"], r["Batter 2"], r["Runs"], r["Wicket"], r["Season"])
        if k not in seen:
            seen.add(k)
            pr.append(r)
    pr.sort(key=lambda r: (r["Wicket"], -r["Runs"]))
    with open("3_payneham_partnerships.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, ["Batter 1", "Batter 2", "Runs", "Wicket", "Season",
                                "Not Out", "Grade", "Opposition"])
        w.writeheader()
        w.writerows(pr)
    print(f"3_payneham_partnerships.csv   {len(pr):5d} stands")

    # 4 — team records
    tr, mr = team_record_rows(secs), margin_rows(secs)
    with open("4_payneham_team_records.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, ["Team", "Scope", "Record", "Side", "Score", "Opponent",
                                "Grade", "Month", "Season"])
        w.writeheader()
        w.writerows(tr)
    with open("5_payneham_margins.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, ["Team", "Record", "Basis", "Margin", "Month", "Season",
                                "Payneham score", "Opponent", "Opponent score"])
        w.writeheader()
        w.writerows(mr)
    with open("6_payneham_career_by_competition.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Player", "Competition", "Games", "Innings", "Runs", "NO", "HS",
                    "Avg", "Wickets", "Overs", "Runs Conceded", "Bowl Avg",
                    "Catches", "Stumpings"])
        n = 0
        for comp in sorted(per_team):
            for name in sorted(per_team[comp]):
                a = per_team[comp][name]
                w.writerow([name, comp, a.get("matches", ""), a.get("innings", ""),
                            a.get("runs", ""), a.get("not_outs", ""), a.get("hs", ""),
                            a.get("avg", ""), a.get("wickets", ""), a.get("overs", ""),
                            a.get("conceded", ""), a.get("bowl_avg", ""),
                            a.get("catches", ""), a.get("stumpings", "")])
                n += 1
    print(f"6_payneham_career_by_competition.csv {n:5d} rows (reference, not for import)")
    print(f"4_payneham_team_records.csv   {len(tr):5d} totals")
    print(f"5_payneham_margins.csv        {len(mr):5d} margins")


if __name__ == "__main__":
    main()
