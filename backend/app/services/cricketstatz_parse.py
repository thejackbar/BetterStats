"""CricketStatz public-report parsers — pure, DB-free, unit-testable.

A club's CricketStatz site is server-rendered at
``www2.cricketstatz.com/ss/w?mode=<report>&club=<id>``, and every report's
content is served separately by the documented embed endpoint::

    /ss/linkreport?mode=<report>&club=<id>&web=1

which answers with ``document.write("<table>…")`` — HTML tables wrapped in a
one-line JS string. These functions take that raw body (or a plain page's
HTML) and hand back plain dicts. Nothing here touches the network or a
database, so the wizard's preview can call it repeatedly.

The three reports that carry everything a club's history needs:

    mode=12   Match Results  — one row per match, each linking mode=100
    mode=100  Match Report   — the full two-team scorecard
    mode=107  Teams          — the club's team list

Markup notes that the parsers lean on (verified against live reports):

* Every player is a link carrying ``playerid=<n>``. That id is stable and
  league-scoped, so it is a far better identity key than the printed name —
  which is abbreviated inconsistently across eras ("Tommy A McSwain").
* A batting row is one ``td.ss_dismissal`` (batter, then one
  ``span.ss_block`` per dismissal clause) followed by six numeric cells:
  R, M, B, SR, 4s, 6s.
* Captain / keeper / duck are ``<span title='Captain'>`` etc. Parse the title
  attribute, never the emoji — the glyphs vary by era and encoding.
"""
from __future__ import annotations

import html
import re
from typing import Optional

# ── the document.write() wrapper ─────────────────────────────────────────────

_DOC_WRITE = re.compile(r'^\s*document\.write\("(.*)"\);?\s*$', re.S)

# Errors the endpoint returns in place of a report. "Subscription expired" is
# the one that matters: a club moving to BetterCricket is precisely the club
# whose CricketStatz subscription is lapsing, and its reports go dark rather
# than 404.
_SUBSCRIPTION_EXPIRED = "subscription expired"
_NOT_FOUND = "404 not found"


class CricketStatzError(RuntimeError):
    """A report came back as an error rather than data."""

    def __init__(self, message: str, *, kind: str = "error"):
        super().__init__(message)
        self.kind = kind


def unwrap(body: str) -> str:
    """Strip the ``document.write("…")`` wrapper and unescape the JS string.

    Raises CricketStatzError for the endpoint's own error payloads so a caller
    can tell "this club's subscription lapsed" apart from "this club has no
    matches", which otherwise both look like an empty report.
    """
    if not body:
        return ""
    text = body.strip()
    m = _DOC_WRITE.match(text)
    if m:
        text = m.group(1)
    # The payload is a JS double-quoted string: unescape in one pass so a
    # literal backslash can't eat the character after it.
    text = re.sub(r'\\(["\'/\\])', r"\1", text)
    text = text.replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "")

    low = text.lower()
    if _SUBSCRIPTION_EXPIRED in low:
        raise CricketStatzError(
            "This CricketStatz site's subscription has expired, so it is no "
            "longer serving any data. The club needs to renew it long enough "
            "for the import to run.",
            kind="subscription_expired",
        )
    if _NOT_FOUND in low and len(text) < 200:
        raise CricketStatzError(
            "CricketStatz returned 404 for that club — check the club number "
            "in the address.",
            kind="not_found",
        )
    return text


# ── small HTML helpers (stdlib only — no bs4/lxml dependency) ────────────────

_TAG = re.compile(r"<[^>]+>")
_ROW = re.compile(r"<tr\b[^>]*>(.*?)(?=<tr\b|</table>|$)", re.S | re.I)
_CELL = re.compile(r"<t[dh]\b([^>]*)>(.*?)(?=<t[dh]\b|</tr>|</table>|$)", re.S | re.I)


def _text(fragment: str) -> str:
    """Visible text of an HTML fragment, entity-decoded and space-collapsed."""
    if not fragment:
        return ""
    # <br> is a real break in the multi-line cells (toss / points / dates).
    fragment = re.sub(r"<(?:br|hr)\b[^>]*>", "\n", fragment, flags=re.I)
    return re.sub(r"[ \t]+", " ", html.unescape(_TAG.sub("", fragment))).strip()


def _rows(table_html: str) -> list[list[tuple[str, str]]]:
    """Split a table into rows of ``(cell_attrs, cell_html)``."""
    out: list[list[tuple[str, str]]] = []
    for row in _ROW.findall(table_html):
        cells = [(a, c) for a, c in _CELL.findall(row)]
        if cells:
            out.append(cells)
    return out


_PLAYER_LINK = re.compile(
    r"<a\b[^>]*?playerid=(\d+)[^>]*>(.*?)</a>", re.S | re.I
)
_ANY_LINK = re.compile(r"<a\b[^>]*>(.*?)</a>", re.S | re.I)


def _players_in(fragment: str) -> list[dict]:
    """Every ``playerid``-carrying link in a fragment, in document order."""
    return [
        {"source_player_id": pid, "name": _text(label)}
        for pid, label in _PLAYER_LINK.findall(fragment or "")
    ]


def _has_marker(fragment: str, title: str) -> bool:
    return bool(re.search(rf"title='{title}'", fragment or "", re.I))


def _int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    m = re.search(r"-?\d+", str(value).replace(",", ""))
    return int(m.group()) if m else None


def _float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(m.group()) if m else None


# ── dates ────────────────────────────────────────────────────────────────────

_MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"], start=1
    )
}
_DATE = re.compile(r"(\d{1,2})\s+([A-Za-z]{3,})\s+(\d{4})")


def parse_dates(cell_text: str) -> list[str]:
    """Every ``7 Mar 2026`` in a cell, as ISO strings, in order.

    A two-day match prints its date cell as "7 Mar 2026 - 8 Mar 2026", so the
    caller takes the first as the match date (matching how the rest of the app
    files a multi-day game) and can keep the last as the end date.
    """
    out: list[str] = []
    for day, month, year in _DATE.findall(cell_text or ""):
        idx = _MONTHS.get(month[:3].lower())
        if idx:
            out.append(f"{int(year):04d}-{idx:02d}-{int(day):02d}")
    return out


# ── mode=12 · Match Results ──────────────────────────────────────────────────

_MATCH_LINK = re.compile(r"mode=100&(?:amp;)?match=(\d+)", re.I)
# "Montmorency Won by 8 wickets Points: Montmorency 1.00, Keon Park 0.00"
_POINTS_TAIL = re.compile(r"\s*Points:.*$", re.I | re.S)
_WON_BY = re.compile(r"^(.*?)\s+(?:won|Won)\b", re.S)


def parse_results(body: str) -> list[dict]:
    """Rows of the Match Results report (mode=12).

    Each row carries the match id needed to fetch its full scorecard.
    """
    text = unwrap(body)
    matches: list[dict] = []
    for cells in _rows(text):
        joined = " ".join(c for _, c in cells)
        link = _MATCH_LINK.search(joined)
        if not link:
            continue  # header row, or a match with no report published
        values = [_text(c) for _, c in cells]
        # Rnd | Date | Home v Away | Division | Venue | Result
        rnd = values[0] if len(values) > 0 else ""
        dates = parse_dates(values[1] if len(values) > 1 else "")
        teams = values[2] if len(values) > 2 else ""
        division = values[3] if len(values) > 3 else ""
        venue = values[4] if len(values) > 4 else ""
        result_raw = values[5] if len(values) > 5 else ""

        home, away = "", ""
        if " v " in teams:
            home, _, away = teams.partition(" v ")
        result = _POINTS_TAIL.sub("", result_raw).strip()
        winner = ""
        won = _WON_BY.match(result)
        if won:
            winner = won.group(1).strip()

        matches.append({
            "source_match_id": link.group(1),
            "round": rnd.strip(),
            "date": dates[0] if dates else None,
            "end_date": dates[-1] if len(dates) > 1 else None,
            "home_team": home.strip(),
            "away_team": away.strip(),
            "division": division.strip(),
            "venue": venue.strip(),
            "result": result,
            "winning_team": winner,
        })
    # One row per match — a report can legitimately repeat a fixture across
    # sections, and re-importing the same match twice would double a career.
    seen: set[str] = set()
    unique: list[dict] = []
    for m in matches:
        if m["source_match_id"] in seen:
            continue
        seen.add(m["source_match_id"])
        unique.append(m)
    return unique


# ── the club's own page (season + team dropdowns) ────────────────────────────

_OPTION = re.compile(r"<option\b[^>]*value='([^']*)'[^>]*>(.*?)</option>", re.S | re.I)
_SELECT = re.compile(r"<select\b[^>]*name='([^']+)'[^>]*>(.*?)</select>", re.S | re.I)
_TITLE = re.compile(r"<title>(.*?)</title>", re.S | re.I)
_CLUB_IN_URL = re.compile(r"[?&]club=(\d+)")


def parse_club_page(page_html: str) -> dict:
    """Club name, season list and team list from a rendered report page.

    The season ``<select>`` is CricketStatz's own full list (it reaches back to
    1860 for every club), so it is a list of CANDIDATES, not seasons this club
    played. The importer probes them and keeps the ones that return matches.
    """
    selects = {name.lower(): body for name, body in _SELECT.findall(page_html or "")}

    seasons: list[dict] = []
    for value, label in _OPTION.findall(selects.get("season", "")):
        # '00' is the "all time" entry, which is not a season.
        if not value or value == "00":
            continue
        seasons.append({"value": value, "label": _text(label)})

    teams: list[dict] = []
    for value, label in _OPTION.findall(selects.get("team", "")):
        if not value or value == "0":
            continue
        teams.append({"id": value, "name": _text(label)})

    name = ""
    t = _TITLE.search(page_html or "")
    if t:
        # "Keon Park Cricket Club - Match Results"
        name = _text(t.group(1)).split(" - ")[0].strip()

    return {"club_name": name, "seasons": seasons, "teams": teams}


def parse_teams(body: str) -> list[dict]:
    """The Teams report (mode=107)."""
    text = unwrap(body)
    out: list[dict] = []
    for cells in _rows(text):
        if not cells:
            continue
        name = _text(cells[0][1])
        if not name or name.lower() == "team":
            continue
        tid = ""
        m = re.search(r"[?&]team=(\d+)", " ".join(c for _, c in cells))
        if m:
            tid = m.group(1)
        out.append({"id": tid, "name": name})
    return out


def parse_club_url(url: str) -> Optional[str]:
    """The club number out of any CricketStatz address a club might paste."""
    if not url:
        return None
    m = _CLUB_IN_URL.search(url.strip())
    if m:
        return m.group(1)
    bare = url.strip()
    return bare if bare.isdigit() else None


# ── mode=100 · Match Report (the full scorecard) ─────────────────────────────

_INNINGS_HEAD = re.compile(r"^(.*?)\s+-\s+Innings\s+(\d+)\s*$", re.I)
_BOWLING_HEAD = re.compile(r"^(.*?)\s+Bowling\s*$", re.I)
_TOTAL = re.compile(r"(\d+)\s*/\s*(\d+)")
_OVERS = re.compile(r"\(([\d.]+)\s*ov", re.I)
_EXTRAS = re.compile(r"\b(b|lb|w|nb|p)\s*(\d+)", re.I)
_FOW_ITEM = re.compile(r"(\d+)\s*-\s*(\d+)\s*(.*?)\s*(?:\(ov\s*([\d.]+)\))?$", re.S)
_HOWOUT = re.compile(r"<span[^>]*class='[^']*ss_howout[^']*'[^>]*>(.*?)</span>", re.S | re.I)
_BATTERNAME = re.compile(
    r"<span[^>]*class='[^']*ss_battername[^']*'[^>]*>(.*?)</span>", re.S | re.I
)

# How CricketStatz's short forms map onto the dismissal vocabulary the rest of
# the app already stores (see sync.py's own parsing of CA scorecards).
_DISMISSAL_NAMES = {
    "c": "caught",
    "ct": "caught",
    "c&b": "caught and bowled",
    "b": "bowled",
    "lbw": "lbw",
    "st": "stumped",
    "run out": "run out",
    "hit wicket": "hit wicket",
    "retired": "retired",
    "retired hurt": "retired hurt",
    "retired not out": "retired not out",
    "handled the ball": "handled the ball",
    "obstructing the field": "obstructing the field",
    "timed out": "timed out",
    "hit the ball twice": "hit the ball twice",
    "absent": "absent",
}


# Column layouts vary by era: a modern card is "R M B SR 4s 6s" while a 1995
# one is "R M 4s 6s" (no balls faced, no strike rate). Reading the header row
# is the only safe way to know which is which — fixed positions would file
# boundaries as balls faced.
_BAT_COLS = {
    "r": "runs", "runs": "runs",
    "m": "minutes", "mins": "minutes", "minutes": "minutes",
    "b": "balls", "bf": "balls", "balls": "balls",
    "sr": "strike_rate", "s/r": "strike_rate",
    "4s": "fours", "4": "fours",
    "6s": "sixes", "6": "sixes",
}
_BOWL_COLS = {
    "o": "overs", "ov": "overs", "overs": "overs",
    "m": "maidens", "mdn": "maidens", "mdns": "maidens", "maidens": "maidens",
    "r": "runs", "runs": "runs",
    "w": "wickets", "wkts": "wickets", "wickets": "wickets",
    "wd": "wides", "wds": "wides", "wides": "wides",
    "nb": "no_balls", "nbs": "no_balls",
    "econ": "economy", "eco": "economy", "rpo": "economy",
}


def _column_map(values: list[str], lookup: dict) -> list[Optional[str]]:
    """Map a header row's cells onto field names, by header text."""
    return [lookup.get(v.strip().lower()) for v in values]


def _parse_dismissal(cell_html: str) -> dict:
    """Split a ``td.ss_dismissal`` into batter, how out, and who did it.

    Each clause is its own ``span.ss_block``: a modern card links the fielder
    and bowler (carrying ``playerid``), while an older one may print a bare
    name — or "N/A" where the scorer never recorded one. Parsing block by
    block handles both, and keeps a fielder from being read as a bowler when
    only one of the two is a link.
    """
    batter_html = ""
    bm = _BATTERNAME.search(cell_html)
    if bm:
        batter_html = bm.group(1)
        rest = cell_html.replace(bm.group(0), "", 1)
    else:
        rest = cell_html

    batters = _players_in(batter_html)
    batter = batters[0] if batters else {
        "source_player_id": None, "name": _text(batter_html)}

    clauses: list[tuple[str, Optional[dict]]] = []
    # Split on the opening tag rather than matching to </span>: a clause
    # nests its own <span class='ss_howout'>, so a non-greedy match to the
    # first closing tag would stop inside it and lose the name after it.
    for block in re.split(
        r"<span[^>]*class='[^']*ss_block[^']*'[^>]*>", rest, flags=re.I
    )[1:]:
        howout = ""
        h = _HOWOUT.search(block)
        if h:
            howout = _text(h.group(1)).lower()
            block = block.replace(h.group(0), "", 1)
        linked = _players_in(block)
        if linked:
            person: Optional[dict] = linked[0]
        else:
            name = _text(block).strip(" &")
            person = ({"source_player_id": None, "name": name}
                      if name and name.upper() not in ("N/A", "NA", "-", "&") else None)
        if howout or person:
            clauses.append((howout, person))

    # A run out names both fielders across two blocks ("A & B").
    howouts = [h for h, _ in clauses if h]
    people = [p for _, p in clauses if p]

    key = " ".join(howouts).strip()
    not_out = "not out" in key
    did_not_bat = key.startswith("dnb") or key in {"did not bat", "dnb"}
    absent = key.startswith("absent")

    dismissal: Optional[str] = None
    bowler: Optional[dict] = None
    fielder: Optional[dict] = None

    if not (not_out or did_not_bat):
        # Read the roles off the clauses themselves rather than by position:
        # "c <fielder> b <bowler>" and "st <keeper> b <bowler>" both name the
        # bowler under "b", whether or not the fielder resolved to anyone.
        for howout, person in clauses:
            if howout in ("b", "bowled") and person:
                bowler = bowler or person
            elif howout in ("c", "ct") and person:
                fielder = fielder or person
            elif howout == "st" and person:
                fielder = fielder or person
            elif howout == "run out" and person:
                fielder = fielder or person

        first = howouts[0] if howouts else ""
        if first in ("c", "ct"):
            dismissal = "caught"
        elif first == "c&b":
            dismissal = "caught and bowled"
            bowler = bowler or (people[0] if people else None)
            fielder = fielder or bowler
        elif first == "st":
            dismissal = "stumped"
        elif first == "run out":
            dismissal = "run out"
        elif first:
            dismissal = _DISMISSAL_NAMES.get(first, first)
            if bowler is None and first in ("b", "lbw", "hit wicket") and people:
                bowler = people[0]

    return {
        "batter": batter,
        "dismissal_type": dismissal,
        "not_out": not_out,
        "did_not_bat": did_not_bat or absent,
        "bowler": bowler,
        "fielder": fielder,
        "is_captain": _has_marker(batter_html, "Captain"),
        "is_keeper": _has_marker(batter_html, "Keeper"),
    }


def _parse_fow(cell_html: str) -> list[dict]:
    out: list[dict] = []
    for chunk in re.findall(r"<span[^>]*class='[^']*ss_nowrap[^']*'[^>]*>(.*?)</span>",
                            cell_html, re.S | re.I):
        players = _players_in(chunk)
        m = _FOW_ITEM.match(_text(chunk))
        if not m:
            continue
        out.append({
            "wicket_number": _int(m.group(1)),
            "score_at_fall": _int(m.group(2)),
            "batter": players[0] if players else {"source_player_id": None,
                                                  "name": (m.group(3) or "").strip()},
            "overs_at_fall": _float(m.group(4)) if m.group(4) else None,
        })
    return out


def parse_scorecard(body: str) -> dict:
    """The full two-team match report (mode=100).

    Returns every innings with its batting card (runs, minutes, balls, strike
    rate, fours, sixes, how out, bowler, fielder), extras split, total, fall of
    wickets and bowling figures — plus the match header (teams, result, venue,
    date, grade, round, toss, umpires).
    """
    text = unwrap(body)
    rows = _rows(text)

    card: dict = {
        "home_team": "", "away_team": "", "result": "", "winning_team": "",
        "venue": "", "date": None, "end_date": None, "division": "",
        "round": "", "innings_count": None, "toss_winner": "", "umpires": "",
        "match_summary": "", "innings": [],
    }

    current: Optional[dict] = None
    mode: Optional[str] = None  # 'batting' | 'bowling'

    for cells in rows:
        values = [_text(c) for _, c in cells]
        joined_html = " ".join(c for _, c in cells)
        line = " ".join(v for v in values if v).strip()
        first = values[0] if values else ""

        # ── header block ────────────────────────────────────────────────────
        header = ""
        if not card["home_team"] and not _INNINGS_HEAD.match(first):
            header = next((v for v in values if " v " in v), "")
        if header:
            teams, _, tail = header.partition("\n")
            home, _, away = teams.partition(" v ")
            card["home_team"] = home.strip()
            card["away_team"] = away.strip()
            result = tail.strip() or (values[1] if len(values) > 1 else "")
            card["result"] = result.strip()
            won = _WON_BY.match(card["result"])
            if won:
                card["winning_team"] = won.group(1).strip()
            continue

        dates = parse_dates(line)
        if dates and not card["date"] and "Innings" not in line:
            card["date"] = dates[0]
            if len(dates) > 1:
                card["end_date"] = dates[-1]
            # "Central Park\n7 Mar 2026, 12:30 PM" — venue and date share a cell.
            for candidate in (values[0] if values else "").split("\n"):
                if candidate.strip() and not _DATE.search(candidate):
                    card["venue"] = candidate.strip()
                    break
            continue

        if "Inns" in line and not card["division"]:
            # "G-GRADE, 1 Inns, Round SEMI FINAL"
            parts = [p.strip() for p in line.split(",")]
            if parts:
                card["division"] = parts[0]
            for p in parts[1:]:
                if re.match(r"^\d+\s+Inns", p, re.I):
                    card["innings_count"] = _int(p)
                elif p.lower().startswith("round"):
                    card["round"] = p[5:].strip()
            continue

        if line.lower().startswith("umpires"):
            card["umpires"] = line.split("-", 1)[-1].strip()
            continue
        if "toss won by" in line.lower():
            m = re.search(r"toss won by\s+(.+?)(?:\n|$)", line, re.I)
            if m:
                card["toss_winner"] = m.group(1).strip()
            continue

        # ── innings / section headers ───────────────────────────────────────
        ih = _INNINGS_HEAD.match(first)
        if ih:
            current = {
                "batting_team": ih.group(1).strip(),
                "innings_number": _int(ih.group(2)) or 1,
                "batters": [], "bowlers": [], "fall_of_wickets": [],
                "extras": {}, "extras_total": None,
                "runs": None, "wickets": None, "overs": None, "all_out": False,
            }
            card["innings"].append(current)
            mode = None
            continue

        if current is not None:
            bh = _BOWLING_HEAD.match(first)
            if bh and "Bowler" not in first:
                current["bowling_team"] = bh.group(1).strip()
                continue
            if first.lower() == "batting":
                mode = "batting"
                current["_bat_cols"] = _column_map(values[1:], _BAT_COLS)
                continue
            if first.lower() == "bowler":
                mode = "bowling"
                current["_bowl_cols"] = _column_map(values[1:], _BOWL_COLS)
                continue
            if first.lower() == "fow":
                mode = "fow"
                continue

            if first.lower().startswith("extras"):
                raw = first[len("extras"):]
                current["extras"] = {
                    k.lower(): int(v) for k, v in _EXTRAS.findall(raw)
                }
                total = next((v for a, v in ((a, _text(c)) for a, c in cells)
                              if "ss_numeric" in a), None)
                current["extras_total"] = _int(total) if total else _int(raw)
                continue

            if _OVERS.search(line) and _TOTAL.search(line):
                t = _TOTAL.search(line)
                current["runs"] = _int(t.group(1))
                current["wickets"] = _int(t.group(2))
                o = _OVERS.search(line)
                current["overs"] = _float(o.group(1)) if o else None
                current["all_out"] = "all out" in line.lower()
                continue

            if mode == "fow" or (not values[0] and "ss_nowrap" in joined_html
                                 and re.search(r"\d+-\d+", line)):
                fow = _parse_fow(joined_html)
                if fow:
                    current["fall_of_wickets"].extend(fow)
                    mode = None
                continue

            # ── batting row ─────────────────────────────────────────────────
            if any("ss_dismissal" in attrs for attrs, _ in cells):
                dis_html = next(c for a, c in cells if "ss_dismissal" in a)
                nums = [v for a, v in
                        ((a, _text(c)) for a, c in cells) if "ss_numeric" in a]
                info = _parse_dismissal(dis_html)
                cols = current.get("_bat_cols") or [
                    "runs", "minutes", "balls", "strike_rate", "fours", "sixes"]
                figures: dict = {}
                for idx, field in enumerate(cols):
                    if not field or idx >= len(nums):
                        continue
                    figures[field] = (
                        _float(nums[idx]) if field == "strike_rate" else _int(nums[idx])
                    )
                # A duck prints the Duck marker in place of "0".
                if _has_marker(
                    next((c for a, c in cells if "ss_numeric" in a), ""), "Duck"
                ):
                    figures["runs"] = 0
                info.update({
                    "batting_position": len(current["batters"]) + 1,
                    "runs": 0 if info["did_not_bat"] else (figures.get("runs") or 0),
                    "minutes": figures.get("minutes"),
                    "balls": figures.get("balls"),
                    "strike_rate": figures.get("strike_rate"),
                    "fours": figures.get("fours"),
                    "sixes": figures.get("sixes"),
                })
                current["batters"].append(info)
                continue

            # ── bowling row ─────────────────────────────────────────────────
            if mode == "bowling":
                players = _players_in(joined_html)
                nums = [_text(c) for a, c in cells if "ss_numeric" in a]
                if not players and not nums:
                    continue
                name = players[0] if players else {
                    "source_player_id": None, "name": first}
                if not name["name"]:
                    continue
                cols = current.get("_bowl_cols") or [
                    "overs", "maidens", "runs", "wickets",
                    "wides", "no_balls", "economy"]
                figures = {}
                for idx, field in enumerate(cols):
                    if not field or idx >= len(nums):
                        continue
                    figures[field] = (
                        _float(nums[idx]) if field in ("overs", "economy")
                        else _int(nums[idx])
                    )
                current["bowlers"].append({"bowler": name, **{
                    k: figures.get(k) for k in
                    ("overs", "maidens", "runs", "wickets",
                     "wides", "no_balls", "economy")}})
                continue

    summary = re.search(r"Match Summary.{0,40}?<div class='card-body'>(.*?)</div>",
                        text, re.S | re.I)
    if summary:
        card["match_summary"] = _text(summary.group(1))

    for inn in card["innings"]:
        inn.pop("_bat_cols", None)
        inn.pop("_bowl_cols", None)

    for seq, inn in enumerate(card["innings"], start=1):
        inn["team_innings_number"] = inn["innings_number"]
        inn["innings_number"] = seq

    _mark_caught_behind(card)
    return card


def _mark_caught_behind(card: dict) -> None:
    """Flag catches taken by the wicket keeper.

    The keeper is marked on their own team's BATTING card, so a catch in the
    other innings is "caught behind" when its fielder is that person. Same
    signal `sync.py` derives structurally from CA's fielding rows — never from
    the dismissal text, which does not say.
    """
    keepers: dict[str, set] = {}
    for inn in card.get("innings", []):
        team = (inn.get("batting_team") or "").strip().lower()
        for b in inn.get("batters", []):
            if b.get("is_keeper") and b["batter"].get("source_player_id"):
                keepers.setdefault(team, set()).add(b["batter"]["source_player_id"])

    for inn in card.get("innings", []):
        fielding = (inn.get("bowling_team") or "").strip().lower()
        ids = keepers.get(fielding, set())
        for b in inn.get("batters", []):
            f = b.get("fielder") or {}
            if b.get("dismissal_type") == "stumped":
                b["caught_behind"] = True
            elif b.get("dismissal_type") == "caught" and f.get("source_player_id"):
                b["caught_behind"] = f["source_player_id"] in ids if ids else None
            else:
                b["caught_behind"] = None


# ── the record book (mode=3..265) ────────────────────────────────────────────

_TITLE_DIV = re.compile(r"<div[^>]*class='[^']*ss_title[^']*'[^>]*>(.*?)</div>", re.S | re.I)
_FILTERS_DIV = re.compile(r"<div[^>]*class='[^']*ss_filters[^']*'[^>]*>(.*?)</div>", re.S | re.I)


def parse_report(body: str) -> dict:
    """A record/leaderboard report as a plain table.

    CricketStatz publishes 180-odd of these (top run aggregates, highest
    innings totals, biggest winning margins…). They share one shape — a title,
    a header row, then rows — so they are captured generically rather than
    modelled one by one. Any player link's ``playerid`` is kept alongside the
    row so a record can still be tied to a player after the import.
    """
    text = unwrap(body)

    title = ""
    t = _TITLE_DIV.search(text)
    if t:
        title = _text(t.group(1))
    scope = ""
    f = _FILTERS_DIV.search(text)
    if f:
        scope = _text(f.group(1))

    headers: list[str] = []
    rows: list[dict] = []
    for cells in _rows(text):
        values = [_text(c) for _, c in cells]
        if not any(values):
            continue
        is_head = any("ss_tablehead" in a for a, _ in cells)
        if not headers and (is_head or not rows):
            # The first row is the header when it carries no data row's shape.
            if is_head or not any(v.strip().isdigit() for v in values[:1]):
                headers = [v.replace("\n", " ").strip() for v in values]
                continue
        rows.append({
            "values": values,
            "players": _players_in(" ".join(c for _, c in cells)),
        })

    return {"title": title, "scope": scope, "headers": headers, "rows": rows}


# The record book worth importing. Deliberately a curated list rather than all
# ~180 modes: these are the ones a club actually keeps on an honour board, and
# every extra report is another request against someone else's server.
RECORD_REPORTS: tuple[tuple[int, str, str], ...] = (
    # (mode, section, title as CricketStatz names it)
    (4, "batting", "Top Run Aggregates"),
    (6, "batting", "Top Run Scores"),
    (3, "batting", "Top Batting Averages"),
    (64, "batting", "Top Batting Strike Rates"),
    (29, "batting", "Most Runs in a Season"),
    (43, "batting", "Centurions"),
    (44, "batting", "Most Hundreds"),
    (54, "batting", "Most Fifties"),
    (65, "batting", "Most Sixes"),
    (23, "batting", "Most Boundaries"),
    (32, "batting", "Most Ducks"),
    (5, "bowling", "Top Wicket Takers"),
    (7, "bowling", "Best Bowling in an Innings"),
    (38, "bowling", "Best Bowling in a Match"),
    (8, "bowling", "Top Bowling Averages"),
    (9, "bowling", "Top Economy Rates"),
    (66, "bowling", "Top Bowling Strike Rates"),
    (30, "bowling", "Most Wickets in a Season"),
    (48, "bowling", "Most Five Wicket Innings"),
    (41, "bowling", "Hat Tricks"),
    (13, "fielding", "Top Wicket Keeping"),
    (33, "fielding", "Top Catches"),
    (18, "fielding", "Top Catches by Field"),
    (46, "fielding", "Top Run Outs"),
    (50, "fielding", "Top Catches in a Match"),
    (27, "team", "Highest Innings Totals"),
    (28, "team", "Lowest Innings Totals"),
    (62, "team", "Highest Successful Run Chases"),
    (72, "team", "Highest Winning Margins by Runs"),
    (73, "team", "Narrowest Winning Margins by Runs"),
    (74, "team", "Highest Winning Margins by Wkts"),
    (75, "team", "Narrowest Winning Margins by Wkts"),
    (35, "team", "Most Wins"),
    (21, "team", "Most Matches Played"),
    (22, "partnerships", "Top Partnerships"),
    (49, "partnerships", "Top Partnerships by Wicket"),
    (203, "partnerships", "Most Century Partnerships by Pair"),
    (37, "allround", "Top All-Rounders"),
    (19, "allround", "MVP Points"),
    (45, "club", "Longest Serving by Duration"),
    (213, "club", "Most Grand Final Wins"),
)
