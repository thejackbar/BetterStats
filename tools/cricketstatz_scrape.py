"""Scrape a club's full history off a CricketStatz public site into CSVs that
BetterStats can import.

CricketStatz (www2.cricketstatz.com) serves a plain server-rendered site per
club. Report tables come back through ``/ss/linkreport`` as a single
``document.write("<table>…")`` call, and each player has a tabbed profile at
``/ss/showplayer2.aspx`` whose tabs are ordinary HTML fragments.

Two files are written for the two BetterStats import screens:

* ``betterimport_stats.csv``  → /admin/import        (one row per player-season)
* ``partnership_records.csv`` → /admin/partnerships  (one row per stand)

plus ``matches.csv``, ``players.csv`` and ``player_grade_totals.csv`` for
reference and for checking the import afterwards.

Usage::

    python -m tools.cricketstatz_scrape --club 35117 --out data/coolbinia

Names are always taken from the ``/ss/p/<First-Last>/`` slug in each link, not
from the visible cell: the tables print "Chandratilake N", which BetterStats
cannot match against a roster holding "Nilan Chandratilake".
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

BASE = "https://www2.cricketstatz.com"
UA = "BetterStats club-history importer (one-off migration; contact support@bettersports.com.au)"

# ── HTTP ─────────────────────────────────────────────────────────────────────


CACHE_DIR = None          # set from --cache; lets a long run be resumed
_throttle = threading.Semaphore(1)
_last_request = [0.0]
MIN_GAP = 0.35            # seconds between requests, site-wide


def _cache_path(url: str) -> str:
    return os.path.join(CACHE_DIR, hashlib.sha1(url.encode()).hexdigest() + ".html")


def fetch(url: str, retries: int = 6) -> str:
    """GET with a site-wide gap between requests and a long back-off on 429.

    The site rate-limits hard — a handful of parallel requests earns an
    immediate 429 and then connection resets — so requests are paced through
    one semaphore rather than trusting the worker count alone. Returns "" once
    the retries are spent, so one bad page can't abort a nearly-finished run.
    """
    if CACHE_DIR:
        path = _cache_path(url)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                return fh.read()

    last = None
    for attempt in range(retries):
        with _throttle:
            gap = MIN_GAP - (time.time() - _last_request[0])
            if gap > 0:
                time.sleep(gap)
            _last_request[0] = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=90) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            if CACHE_DIR:
                os.makedirs(CACHE_DIR, exist_ok=True)
                with open(_cache_path(url), "w", encoding="utf-8") as fh:
                    fh.write(body)
            return body
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code == 429:
                wait = float(exc.headers.get("Retry-After") or 0) or 8 * (attempt + 1)
                time.sleep(wait)
            else:
                time.sleep(2 * (attempt + 1))
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            last = exc
            time.sleep(3 * (attempt + 1))
    print(f"  ! giving up on {url} ({last})", file=sys.stderr)
    return ""


def report(mode: int, club: str, **params) -> str:
    """Fetch a linkreport table and unwrap the document.write() around it."""
    qs = f"mode={mode}&club={club}&web=1&limit=100000"
    for k, v in params.items():
        if v not in (None, ""):
            qs += f"&{k}={v}"
    body = fetch(f"{BASE}/ss/linkreport?{qs}")
    i = body.find('document.write("')
    if i < 0:
        return ""
    return body[i + len('document.write("'):body.rfind('");')]


# ── HTML table parsing ───────────────────────────────────────────────────────

TAG_RE = re.compile(r"<[^>]+>")
ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)
TABLE_RE = re.compile(r"<table[^>]*>(.*?)</table>", re.S | re.I)
PLAYER_RE = re.compile(r"/ss/p/([^/]+)/\?[^'\"]*playerid=(\d+)", re.I)
MATCH_RE = re.compile(r"[?&]match=(\d+)", re.I)


def text_of(cell: str) -> str:
    """Cell text with tags stripped and entities resolved. The '*' inside a
    ``ss_notout`` div is kept — it is what marks an unbeaten score."""
    return html.unescape(TAG_RE.sub("", cell)).replace("\xa0", " ").strip()


def tables(fragment: str) -> list:
    """Every table as (header_list, [row_cell_lists])."""
    out = []
    for body in TABLE_RE.findall(fragment):
        rows = ROW_RE.findall(body)
        if not rows:
            continue
        parsed = [CELL_RE.findall(r) for r in rows]
        header = [text_of(c) for c in parsed[0]]
        out.append((header, parsed[1:]))
    return out


def slug_name(cell: str) -> tuple:
    """('Nilan Chandratilake', '824709') from a player link, else ('', '')."""
    m = PLAYER_RE.search(cell)
    if not m:
        return "", ""
    return html.unescape(m.group(1)).replace("-", " ").strip(), m.group(2)


def is_redacted(name: str) -> bool:
    """A junior whose name Cricket Australia withholds. CricketStatz prints
    them as '********1' and gives the profile a bare number for a slug, so all
    we ever recover is a sequence number — never a name. Importing that would
    mint a player called "1", so these are reported separately instead."""
    n = (name or "").strip()
    return not n or n.isdigit() or bool(re.fullmatch(r"\*+\d*", n))


# ── value coercion ───────────────────────────────────────────────────────────

MISSING = {"", "-", "–", "—", "n/a", "na"}


def num(v: str) -> str:
    """Keep a real number, drop CricketStatz' placeholders for 'nothing here'."""
    v = (v or "").strip()
    if v.lower() in MISSING:
        return ""
    v = v.replace(",", "")
    return v if re.fullmatch(r"-?\d+(\.\d+)?", v) else ""


def int_or_zero(v: str) -> int:
    v = num(v)
    if not v:
        return 0
    return int(float(v))


def season_start_year(date_str: str) -> str:
    """'14 Nov 1964' → 1964; '11 Jan 2025' → 2024. An Australian summer season
    is named for the year it starts in, so anything before July belongs to the
    previous year's season."""
    for fmt in ("%d %b %Y", "%d %B %Y"):
        try:
            d = datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
        return str(d.year if d.month >= 7 else d.year - 1)
    return ""


def season_label(year: str) -> str:
    """1964 → '1964/65'. The label BetterStats' season matcher reads."""
    if not year:
        return ""
    y = int(year)
    return f"{y}/{str(y + 1)[-2:]}"


# ── scrape steps ─────────────────────────────────────────────────────────────


def scrape_matches(club: str) -> list:
    """Every result the club has recorded: date, division, opponent, venue."""
    frag = report(12, club)
    out = []
    for header, rows in tables(frag):
        if "Division" not in header:
            continue
        idx = {h: i for i, h in enumerate(header)}
        for cells in rows:
            if len(cells) < len(header):
                continue
            get = lambda k: text_of(cells[idx[k]]) if k in idx else ""
            date = get("Date")
            # The match link rides on the "Report" anchor inside the Result
            # cell here, not on the date the way the stat reports do it.
            mid = MATCH_RE.search(" ".join(cells))
            out.append({
                "match_id": mid.group(1) if mid else "",
                "round": get("Rnd"),
                "date": date,
                "season_year": season_start_year(date),
                "teams": get("Home v Away"),
                "grade": get("Division"),
                "venue": get("Venue"),
                "result": re.sub(r"\s*Report$", "", get("Result")),
            })
    return out


def scrape_seasons(club: str) -> list:
    """Every season the club holds stats for, as start years.

    Deliberately NOT derived from the results list: that only carries seasons
    whose fixtures were entered, and this club has 20 seasons of batting and
    bowling with no results behind them, so keying off results silently lost a
    third of the history. The four by-season honour boards each name every
    season that has data, and they are unioned in case one of them is empty for
    a season (a year with bowling but no batting, say).
    """
    years = set()
    for mode in (247, 249, 246, 248):
        for header, rows in tables(report(mode, club)):
            for cells in rows:
                if not cells:
                    continue
                label = text_of(cells[0])
                if re.fullmatch(r"\d{4}/\d{2,4}", label):
                    years.add(label[:4])
    return sorted(years)


def scrape_grades(club: str) -> list:
    """(grade_id, name) for every grade in the club's Ladders menu. The stat
    reports take a grade id, but results only ever name the division, so the
    two are matched up by name."""
    page = fetch(f"{BASE}/ss/w/Statistics/?mode=104&club={club}")
    out, seen = [], set()
    for gid, label in re.findall(
            r"mode=1&club=%s&grade=(\d+)[^']*'>\s*(.*?)\s*</a>" % club, page):
        name = html.unescape(TAG_RE.sub("", label)).strip()
        if gid not in seen and name:
            seen.add(gid)
            out.append({"grade_id": gid, "grade": name})
    return out


def scrape_players(club: str) -> list:
    """The roster, from the most-matches report — the widest list on the site
    (a player who never batted or bowled still appears here)."""
    seen = {}
    for mode in (21, 4, 5, 102):
        frag = report(mode, club)
        for _header, rows in tables(frag):
            for cells in rows:
                for cell in cells:
                    name, pid = slug_name(cell)
                    if pid and pid not in seen:
                        seen[pid] = name
    return [{"player_id": p, "name": n} for p, n in sorted(seen.items(), key=lambda kv: kv[1])]


# Per-player stats are assembled from six leaderboard reports rather than the
# per-player profile tabs: showplayer2.aspx rate-limits hard (429 after a
# handful of hits) while /ss/linkreport serves the whole club in one response,
# so a season costs six requests instead of one per player.
#
# Column names repeat across reports with different meanings — 'Runs' is runs
# scored in the batting report and runs conceded in the bowling one — so each
# report gets its own map instead of one shared vocabulary.
REPORTS = {
    # Matches played comes first and on its own: the batting and bowling boards
    # only carry players who did one or the other, so without this a player who
    # turned out and neither batted nor bowled would be missing from the season
    # altogether and everyone else's match count could read short.
    21: {"Mts": "games_played"},
    4: {  # Top Run Aggregates
        "Mts": "games_played", "Inns": "batting_innings", "NOs": "batting_not_outs",
        "HS": "batting_high_score", "Avg": "batting_average", "100s": "batting_hundreds",
        "50s": "batting_fifties", "0s": "batting_ducks", "4s": "batting_fours",
        "6s": "batting_sixes", "Runs": "batting_runs",
    },
    5: {  # Top Wicket Takers
        "Mts": "games_played", "Balls": "bowling_balls", "Mds": "bowling_maidens",
        "Runs": "bowling_runs", "5WI": "bowling_five_wicket_innings",
        "BBI": "bowling_best_figures", "Avg": "bowling_average",
        "Econ": "bowling_economy", "Wkts": "bowling_wickets",
    },
    33: {"Mts": "games_played", "Cts": "fielding_catches"},        # Top Catches (all)
    13: {"Mts": "games_played", "Cts": "fielding_catches_wk",      # Top Wicket Keeping
         "Sts": "fielding_stumpings", "Byes": "keeping_byes"},
    102: {"Mts": "games_played", "Sts": "fielding_stumpings"},     # Dismissals
    46: {"Mts": "games_played", "Run Outs": "fielding_run_outs"},  # Top Run Outs
}

TEXT_FIELDS = ("batting_high_score", "bowling_best_figures")


def merge_report(frag: str, keymap: dict, into: dict) -> None:
    """Fold one report's rows into ``into``, keyed on CricketStatz' player id."""
    for header, rows in tables(frag):
        if "Name" not in header:
            continue
        idx = {h: i for i, h in enumerate(header)}
        for cells in rows:
            if len(cells) < len(header):
                continue
            name, pid = slug_name(cells[idx["Name"]])
            if not pid:
                continue
            row = into.setdefault(pid, {"player_id": pid, "player_name": name})
            if name and not row.get("player_name"):
                row["player_name"] = name
            for head, field in keymap.items():
                if head not in idx or idx[head] >= len(cells):
                    continue
                raw = text_of(cells[idx[head]])
                if field in TEXT_FIELDS:
                    # BBI arrives as '5-21' (sometimes '5-21 Vs Someone').
                    raw = raw.split(" Vs ")[0].strip()
                    val = "" if raw.lower() in MISSING else raw
                else:
                    val = num(raw)
                if val == "":
                    continue
                # 'Mts' appears in every report; keep the largest, since a
                # player can bowl in a match the batting report never counts.
                if field == "games_played" and row.get(field):
                    val = str(max(int_or_zero(val), int_or_zero(row[field])))
                row[field] = val


def scrape_stat_slice(club: str, **filters) -> list:
    """Every player's stats for one filter slice (a season, or a grade)."""
    merged: dict = {}
    for mode, keymap in REPORTS.items():
        merge_report(report(mode, club, **filters), keymap, merged)
    return list(merged.values())


def scrape_partnerships(club: str, season_code: str, grade_by_match: dict) -> list:
    """One season's stands. Sliced per season because the report itself caps at
    999 rows, and a season never comes close to that."""
    frag = report(22, club, season=season_code)
    out = []
    for header, rows in tables(frag):
        if "Bat1" not in header:
            continue
        idx = {h: i for i, h in enumerate(header)}
        for cells in rows:
            if len(cells) < len(header):
                continue
            b1, _ = slug_name(cells[idx["Bat1"]])
            b2, _ = slug_name(cells[idx["Bat2"]])
            if not b1 or not b2:
                continue
            score = text_of(cells[idx["Score"]])
            runs = num(score.replace("*", ""))
            if not runs:
                continue
            date_cell = cells[idx["Date"]]
            mid = MATCH_RE.search(date_cell)
            match_id = mid.group(1) if mid else ""
            date = text_of(date_cell)
            out.append({
                "batter_1": b1,
                "batter_2": b2,
                "runs": runs,
                "wicket": text_of(cells[idx["Wkt"]]),
                "season": season_start_year(date),
                "not_out": "Yes" if "*" in score else "No",
                "grade": grade_by_match.get(match_id, ""),
                "date": date,
                "opposition": text_of(cells[idx["Opposition"]]),
                "venue": text_of(cells[idx["Venue"]]),
                "match_id": match_id,
            })
    return out


# ── output ───────────────────────────────────────────────────────────────────

STATS_COLUMNS = [
    ("player_name", "Player"), ("season_label", "Season"), ("grade_label", "Grade"),
    ("games_played", "Games"), ("batting_innings", "Innings"),
    ("batting_not_outs", "NO"), ("batting_runs", "Runs"),
    ("batting_high_score", "HS"), ("batting_average", "Avg"),
    ("batting_fours", "4s"), ("batting_sixes", "6s"),
    ("batting_fifties", "50s"), ("batting_hundreds", "100s"),
    ("batting_ducks", "Ducks"),
    ("bowling_overs", "Overs"), ("bowling_maidens", "Maidens"),
    ("bowling_runs", "Runs Conceded"), ("bowling_wickets", "Wickets"),
    ("bowling_best_figures", "Best Bowling"), ("bowling_average", "Bowl Avg"),
    ("bowling_economy", "Economy"),
    ("bowling_five_wicket_innings", "5WI"),
    ("fielding_catches", "Catches"), ("fielding_catches_wk", "Catches WK"),
    ("fielding_stumpings", "Stumpings"), ("fielding_run_outs", "Run Outs"),
]


def stat_row(src: dict, season: str, grade: str) -> dict:
    """One BetterImport row. 'Catches' is every catch and 'Catches WK' the
    keeper's share of it — that is how BetterStats stores the split, and the
    reports already report them that way round (Top Catches is the total, the
    keeping report is the keeper subset)."""
    row = {
        "player_name": src.get("player_name", ""),
        "season_label": season,
        "grade_label": grade,
    }
    for field, _label in STATS_COLUMNS:
        if field in row:
            continue
        row[field] = src.get(field, "")
    # Balls bowled is the exact figure CricketStatz holds, but the importer has
    # no header synonym for it and reads "Balls Bowled" as balls FACED. Overs in
    # cricket notation map cleanly and convert back to the same ball count, so
    # the precise number survives the round trip.
    balls = int_or_zero(str(src.get("bowling_balls", "")))
    row["bowling_overs"] = f"{balls // 6}.{balls % 6}" if balls else ""
    # Kept on the row but not in STATS_COLUMNS, so it never reaches the CSV —
    # the residual maths still needs an exact ball count to difference against.
    row["bowling_balls"] = src.get("bowling_balls", "")
    return row


# Fields that are a count of something and so can be summed and differenced.
ADDITIVE = (
    "games_played", "batting_innings", "batting_not_outs", "batting_runs",
    "batting_fours", "batting_sixes", "batting_fifties", "batting_hundreds",
    "batting_ducks", "bowling_balls", "bowling_maidens", "bowling_runs",
    "bowling_wickets", "bowling_five_wicket_innings", "fielding_catches",
    "fielding_catches_wk", "fielding_stumpings", "fielding_run_outs",
)


def _hs_value(hs: str) -> int:
    m = re.match(r"\s*(\d+)", hs or "")
    return int(m.group(1)) if m else -1


def _bb_value(bb: str) -> tuple:
    """'5-21' → (5, -21), so a bigger tuple is a better return."""
    m = re.match(r"\s*(\d+)\s*[-/]\s*(\d+)", bb or "")
    return (int(m.group(1)), -int(m.group(2))) if m else (-1, 0)


def career_residuals(career: list, season_rows: list) -> list:
    """Rows for whatever the season boards don't account for.

    A club's career totals are bigger than the sum of its seasons whenever a
    match was recorded without a season against it — 2.3% of this club's runs
    sit there. BetterStats has a bucket for exactly this ("Prior Seasons &
    Adjustments"), so the shortfall is written there rather than left to make
    every career total read short.
    """
    seen: dict = {}
    for r in season_rows:
        acc = seen.setdefault(r["player_name"], {f: 0 for f in ADDITIVE})
        for f in ADDITIVE:
            acc[f] += int_or_zero(str(r.get(f, "")))
        acc["hs"] = max(acc.get("hs", -1), _hs_value(r.get("batting_high_score", "")))
        acc["bb"] = max(acc.get("bb", (-1, 0)), _bb_value(r.get("bowling_best_figures", "")))

    # One person can hold several CricketStatz profiles (a re-registration
    # mints a new id under the same name). The season rows are already pooled
    # by name, so the career side has to be pooled the same way or each profile
    # gets differenced against the pair's combined total and the shortfall
    # disappears.
    pooled: dict = {}
    for c in career:
        name = c.get("player_name", "")
        if is_redacted(name):
            continue
        tot = pooled.setdefault(name, {f: 0 for f in ADDITIVE})
        for f in ADDITIVE:
            tot[f] += int_or_zero(str(c.get(f, "")))
        if _hs_value(c.get("batting_high_score", "")) > _hs_value(tot.get("batting_high_score", "")):
            tot["batting_high_score"] = c.get("batting_high_score", "")
        if _bb_value(c.get("bowling_best_figures", "")) > _bb_value(tot.get("bowling_best_figures", "")):
            tot["bowling_best_figures"] = c.get("bowling_best_figures", "")

    out = []
    for name, c in pooled.items():
        acc = seen.get(name, {f: 0 for f in ADDITIVE})
        row = {"player_name": name, "season_label": "Prior Seasons & Adjustments",
               "grade_label": ""}
        any_left = False
        for f in ADDITIVE:
            diff = int_or_zero(str(c.get(f, ""))) - acc.get(f, 0)
            # A negative difference means the season boards already carry more
            # than the career board does; that is a quirk of their data, not
            # something to subtract back out of the club's history.
            row[f] = diff if diff > 0 else ""
            if diff > 0:
                any_left = True
        if not any_left:
            continue
        # Carry a career best only when it beats every season we captured —
        # otherwise the club's record would be attributed to this bucket.
        if _hs_value(c.get("batting_high_score", "")) > acc.get("hs", -1):
            row["batting_high_score"] = c.get("batting_high_score", "")
        if _bb_value(c.get("bowling_best_figures", "")) > acc.get("bb", (-1, 0)):
            row["bowling_best_figures"] = c.get("bowling_best_figures", "")
        balls = int_or_zero(str(row.get("bowling_balls", "")))
        row["bowling_overs"] = f"{balls // 6}.{balls % 6}" if balls else ""
        out.append(row)
    return out


def is_empty_stat_row(row: dict) -> bool:
    """A season the player is listed under but did nothing in — no match, no
    ball, no dismissal. Importing it would add a phantom appearance."""
    watched = ("games_played", "batting_innings", "batting_runs", "bowling_overs",
               "bowling_wickets", "fielding_catches", "fielding_stumpings",
               "fielding_run_outs")
    return all(float(num(str(row.get(f, ""))) or 0) == 0 for f in watched)


def write_csv(path: str, fieldnames: list, rows: list, header_labels=None) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(header_labels or fieldnames)
        for r in rows:
            w.writerow([r.get(f, "") for f in fieldnames])
    print(f"  wrote {path}  ({len(rows)} rows)")


# ── main ─────────────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--club", default="35117", help="CricketStatz club id")
    ap.add_argument("--out", default="cricketstatz_export", help="output directory")
    ap.add_argument("--workers", type=int, default=3, help="parallel requests")
    ap.add_argument("--gap", type=float, default=0.4, help="minimum seconds between requests")
    ap.add_argument("--cache", default="", help="directory to cache pages in, so a run can be resumed")
    args = ap.parse_args()

    global CACHE_DIR, MIN_GAP
    CACHE_DIR = args.cache or None
    MIN_GAP = args.gap
    if CACHE_DIR:
        os.makedirs(CACHE_DIR, exist_ok=True)

    club, out = args.club, args.out
    os.makedirs(out, exist_ok=True)

    print("1/5  results …")
    matches = scrape_matches(club)
    grade_by_match = {m["match_id"]: m["grade"] for m in matches if m["match_id"]}
    result_years = {m["season_year"] for m in matches if m["season_year"]}
    seasons = sorted(set(scrape_seasons(club)) | result_years)
    print(f"     {len(matches)} matches over {len(result_years)} seasons, "
          f"{len({m['grade'] for m in matches})} grades; "
          f"{len(seasons)} seasons hold stats ({seasons[0]}–{seasons[-1]})")
    write_csv(f"{out}/matches.csv",
              ["match_id", "date", "season_year", "round", "teams", "grade", "venue", "result"],
              matches)

    print("2/5  roster …")
    players = scrape_players(club)
    print(f"     {len(players)} players")
    write_csv(f"{out}/players.csv", ["player_id", "name"], players)

    fields = [f for f, _ in STATS_COLUMNS]
    labels = [l for _, l in STATS_COLUMNS]

    print(f"3/5  per-season stats across {len(seasons)} seasons …")
    stats, redacted = [], []
    dropped = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        jobs = [(y, f"{y}S") for y in seasons]
        for (year, _code), rows in zip(
                jobs, pool.map(lambda j: scrape_stat_slice(club, season=j[1]), jobs)):
            for r in rows:
                row = stat_row(r, season_label(year), "")
                if is_empty_stat_row(row):
                    dropped += 1
                    continue
                (redacted if is_redacted(row["player_name"]) else stats).append(row)

    # Anything the season boards miss (a match recorded with no season on it)
    # goes into the residual bucket so career totals still reconcile.
    career = scrape_stat_slice(club)
    resid = career_residuals(career, stats)
    stats.extend(resid)
    stats.sort(key=lambda r: (r["player_name"], r["season_label"]))
    print(f"     {len(stats)} player-season rows ({dropped} empty skipped, "
          f"{len(redacted)} redacted, {len(resid)} residual)")
    write_csv(f"{out}/betterimport_stats.csv", fields, stats, labels)
    if redacted:
        write_csv(f"{out}/stats_redacted_players.csv", fields, redacted, labels)

    print("4/5  per-grade career totals …")
    grades = scrape_grades(club)
    played = {m["grade"] for m in matches}
    # Only the grades the club has actually played in — the Ladders menu also
    # carries competitions it has never fielded a side in.
    grades = [g for g in grades if g["grade"] in played] or grades
    gstats = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for g, rows in zip(grades, pool.map(
                lambda g: scrape_stat_slice(club, grade=g["grade_id"]), grades)):
            for r in rows:
                row = stat_row(r, "Prior Seasons & Adjustments", g["grade"])
                if not is_empty_stat_row(row) and not is_redacted(row["player_name"]):
                    gstats.append(row)
    gstats.sort(key=lambda r: (r["player_name"], r["grade_label"]))
    print(f"     {len(gstats)} player-grade rows across {len(grades)} grades")
    write_csv(f"{out}/player_grade_totals.csv", fields, gstats, labels)

    # Partnerships are fetched per season because that report caps at 999 rows
    # while the club's whole history runs to many thousands of stands.
    print(f"5/5  partnerships across {len(seasons)} seasons …")
    stands = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for rows in pool.map(
                lambda y: scrape_partnerships(club, f"{y}S", grade_by_match), seasons):
            stands.extend(rows)
    print(f"     {len(stands)} partnerships")

    # Partnership records sheet. Grade and season are both required by the
    # importer, and a stand involving a redacted junior has no name to match on,
    # so anything short is written to a separate file rather than silently
    # dropped or imported against a made-up player.
    def usable(s):
        # The importer only accepts wickets 1–10; this club's data carries a
        # handful of 11th-wicket stands (a 12-a-side game, or a retired batter
        # counted as a fall), which would come back as import errors.
        wkt = int_or_zero(s["wicket"])
        return (s["grade"] and s["season"] and 1 <= wkt <= 10
                and not is_redacted(s["batter_1"]) and not is_redacted(s["batter_2"]))

    ok = [s for s in stands if usable(s)]
    bad = [s for s in stands if not usable(s)]
    ok.sort(key=lambda s: (-int(float(s["runs"])), s["season"]))
    pfields = ["batter_1", "batter_2", "runs", "wicket", "season", "not_out", "grade"]
    plabels = ["Batter 1", "Batter 2", "Runs", "Wicket", "Season", "Not Out", "Grade"]
    write_csv(f"{out}/partnership_records.csv", pfields, ok, plabels)
    if bad:
        write_csv(f"{out}/partnerships_unmatched.csv",
                  pfields + ["date", "opposition", "venue", "match_id"], bad)

    print("\nDone.")
    print(f"  /admin/import        ← {out}/betterimport_stats.csv")
    print(f"  /admin/partnerships  ← {out}/partnership_records.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
