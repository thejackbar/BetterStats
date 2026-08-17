"""BetterImport ingest — parse an uploaded sheet, auto-map columns, reconstruct
raw components from summary stats, and match names/seasons to our records.

All functions here are DB-free (they take plain data, not a session) so the
wizard's preview can call them repeatedly and they stay unit-testable. The
router supplies org players/seasons as ``(id, name[, year])`` tuples.
"""

from __future__ import annotations

import csv
import io
import math
import re
from difflib import SequenceMatcher
from typing import Optional


# ── canonical importable fields ──────────────────────────────────────────────

KEY_FIELDS = ("player_name", "season_label", "grade_label")

# Stat fields that land directly on imported_stats (same column names).
INT_FIELDS = (
    "games_played", "batting_innings", "batting_runs", "batting_not_outs",
    "batting_balls", "batting_fours", "batting_sixes", "batting_fifties",
    "batting_hundreds", "batting_ducks",
    "bowling_innings", "bowling_balls", "bowling_maidens", "bowling_runs",
    "bowling_wickets", "bowling_wides", "bowling_no_balls",
    "bowling_five_wicket_innings",
    "fielding_catches", "fielding_catches_wk", "fielding_run_outs", "fielding_stumpings",
)
FLOAT_FIELDS = ("bowling_overs",)
# Derived figures the club may give instead of raw components — stored as
# provided_* and used to reconstruct the raw components above.
DERIVED_FIELDS = ("batting_average", "batting_strike_rate", "bowling_average", "bowling_economy")
HS_FIELD = "batting_high_score"          # may carry a trailing '*' (not out)
BEST_FIELD = "bowling_best_figures"      # free text e.g. "4-25"

ALL_FIELDS = KEY_FIELDS + INT_FIELDS + FLOAT_FIELDS + DERIVED_FIELDS + (HS_FIELD, BEST_FIELD)

# Synonyms (lower-cased, punctuation-normalised) for header auto-mapping. Short
# ambiguous codes (m, o, r…) are included but the wizard always lets the user
# confirm/override, so a wrong guess is cheap.
SYNONYMS = {
    "player_name": ["player", "name", "player name", "full name", "members", "member"],
    "player_first_name": ["first name", "given name", "christian name", "forename", "firstname", "fname"],
    "player_last_name": ["surname", "last name", "family name", "lastname", "lname"],
    "season_label": ["season", "year", "yr", "season year", "summer", "yrs"],
    "grade_label": ["grade", "team", "grades", "division", "comp", "competition", "teams"],
    "games_played": ["games", "matches", "m", "mat", "gp", "games played", "appearances", "apps", "played"],
    "batting_innings": ["innings", "inns", "i", "batting innings", "bi", "inn"],
    "batting_runs": ["runs", "r", "total runs", "batting runs", "runs scored", "agg", "aggregate"],
    "batting_not_outs": ["not outs", "no", "not out", "n o", "nos", "notout"],
    "batting_balls": ["balls", "bf", "balls faced", "b"],
    "batting_fours": ["4s", "fours", "four"],
    "batting_sixes": ["6s", "sixes", "six"],
    "batting_fifties": ["50s", "fifties", "half centuries", "50"],
    "batting_hundreds": ["100s", "hundreds", "centuries", "tons", "100"],
    "batting_ducks": ["ducks", "0s", "duck"],
    "batting_high_score": ["hs", "high score", "highest", "highest score", "high", "best score", "top score"],
    "batting_average": ["avg", "average", "bat avg", "batting average", "ave", "batting avg", "bat average"],
    "batting_strike_rate": ["sr", "strike rate", "batting sr", "bat sr", "strikerate", "bat strike rate"],
    "bowling_innings": ["bowling innings", "bowl inns", "bowl innings"],
    "bowling_overs": ["overs", "o", "ov", "overs bowled", "ovrs"],
    "bowling_maidens": ["maidens", "mdns", "maid", "mdn"],
    "bowling_runs": ["runs conceded", "rc", "bowling runs", "runs against", "conceded", "bowl runs"],
    "bowling_wickets": ["wickets", "wkts", "w", "wkt", "wickets taken", "wic"],
    "bowling_wides": ["wides", "wd"],
    "bowling_no_balls": ["no balls", "nb", "noballs"],
    "bowling_five_wicket_innings": ["5wi", "5w", "five fors", "5 wickets", "fifers", "5 fors", "five wicket innings"],
    "bowling_best_figures": ["best", "bbf", "best bowling", "best figures", "bb", "bowling best"],
    "bowling_average": ["bowl avg", "bowling average", "bowling avg", "b avg", "bowl average", "bowling ave"],
    "bowling_economy": ["econ", "economy", "er", "economy rate", "rpo", "econ rate"],
    "fielding_catches": ["catches", "ct", "c", "catches taken", "cts", "catch"],
    "fielding_catches_wk": ["catches wk", "wk catches", "keeper catches", "ct wk", "wicketkeeper catches"],
    "fielding_run_outs": ["run outs", "ro", "runouts", "run out"],
    "fielding_stumpings": ["stumpings", "st", "stmp", "stumped", "stumps", "stumping"],
}


# ── parsing ──────────────────────────────────────────────────────────────────

MAX_ROWS = 50000


def parse_upload(filename: str, data: bytes) -> dict:
    """Return {"headers": [...], "rows": [ {header: cell_str} ]} from CSV or XLSX."""
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        return _parse_xlsx(data)
    return _parse_csv(data)


def _parse_csv(data: bytes) -> dict:
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    grid = [row for row in reader]
    return _grid_to_rows(grid)


def _parse_xlsx(data: bytes) -> dict:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    grid = []
    for row in ws.iter_rows(values_only=True):
        grid.append(["" if c is None else str(c) for c in row])
    wb.close()
    return _grid_to_rows(grid)


def _grid_to_rows(grid: list) -> dict:
    # Find the header row: the first non-empty row with >= 2 non-empty cells.
    header_idx = None
    for i, row in enumerate(grid[:20]):
        non_empty = [c for c in row if str(c).strip()]
        if len(non_empty) >= 2:
            header_idx = i
            break
    if header_idx is None:
        return {"headers": [], "rows": []}
    headers = [str(c).strip() for c in grid[header_idx]]
    # De-duplicate blank/repeat headers so they remain addressable.
    seen: dict = {}
    norm_headers = []
    for j, h in enumerate(headers):
        h = h or f"column_{j + 1}"
        if h in seen:
            seen[h] += 1
            h = f"{h} ({seen[h]})"
        else:
            seen[h] = 0
        norm_headers.append(h)
    rows = []
    for row in grid[header_idx + 1:]:
        if not any(str(c).strip() for c in row):
            continue
        d = {norm_headers[j]: (str(row[j]).strip() if j < len(row) and row[j] is not None else "")
             for j in range(len(norm_headers))}
        rows.append(d)
        if len(rows) >= MAX_ROWS:
            break
    return {"headers": norm_headers, "rows": rows}


# ── column auto-mapping ──────────────────────────────────────────────────────

def _norm(h: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(h).lower())).strip()


def _field_score(nh: str, syns: list) -> float:
    if nh in syns:
        return 1.0
    best = 0.0
    for syn in syns:
        best = max(best, SequenceMatcher(None, nh, syn).ratio())
    return best


def suggest_column_mapping(headers: list) -> dict:
    """{field: {"column": header, "confidence": float}} — best column per field."""
    per_header = {}
    for h in headers:
        nh = _norm(h)
        if not nh:
            continue
        best_field, best_score = None, 0.0
        for field, syns in SYNONYMS.items():
            s = _field_score(nh, syns)
            if s > best_score:
                best_field, best_score = field, s
        if best_field and best_score >= 0.6:
            per_header[h] = (best_field, best_score)
    mapping: dict = {}
    for h, (field, score) in per_header.items():
        if field not in mapping or score > mapping[field]["confidence"]:
            mapping[field] = {"column": h, "confidence": round(score, 2)}
    return mapping


def detect_granularity(mapping: dict, rows: list) -> str:
    """'season' if a season column is mapped and populated, else 'career'."""
    col = (mapping.get("season_label") or {}).get("column")
    if col and any(str(r.get(col, "")).strip() for r in rows):
        return "season"
    return "career"


# ── number parsing + derived→raw inversion ───────────────────────────────────

_NULLS = {"", "-", "—", "–", ".", "n/a", "na", "nil", "none", "--"}


def to_float(s) -> Optional[float]:
    if s is None:
        return None
    s = str(s).strip().replace(",", "")
    if s.lower() in _NULLS:
        return None
    s = s.rstrip("*").strip()  # trailing not-out star on a high score
    try:
        return float(s)
    except ValueError:
        return None


def to_int(s) -> Optional[int]:
    f = to_float(s)
    return int(round(f)) if f is not None else None


def parse_high_score(s):
    raw = "" if s is None else str(s).strip()
    not_out = raw.endswith("*")
    return to_int(raw), not_out


def overs_to_balls(overs: float) -> int:
    o = math.floor(overs)
    frac = overs - o
    return o * 6 + int(round(frac * 10))


def row_to_truth(values: dict) -> tuple:
    """Map one row's parsed field→raw-string values to an imported_stats truth
    dict, reconstructing raw components from any derived figures.

    ``values`` contains only the fields whose column was mapped (raw strings).
    Returns (truth_dict, notes) where notes flags any reconstructed (±1) value.
    """
    notes = []

    def present(f):
        return f in values and values[f] is not None and str(values[f]).strip() != ""

    truth: dict = {f: 0 for f in INT_FIELDS}
    truth["bowling_overs"] = 0
    truth["batting_high_score"] = None
    truth["batting_high_score_not_out"] = False
    truth["bowling_best_figures"] = None
    truth["bowling_best_wickets"] = None
    for f in DERIVED_FIELDS:
        truth["provided_" + f] = None

    for f in INT_FIELDS:
        if present(f):
            v = to_int(values[f])
            if v is not None:
                truth[f] = v
    if present("bowling_overs"):
        ov = to_float(values["bowling_overs"])
        if ov is not None:
            truth["bowling_overs"] = ov
    if present(HS_FIELD):
        hs, no = parse_high_score(values[HS_FIELD])
        truth["batting_high_score"] = hs
        truth["batting_high_score_not_out"] = no
    if present(BEST_FIELD):
        bf = str(values[BEST_FIELD]).strip()
        truth["bowling_best_figures"] = bf or None
        mw = re.match(r"^\s*(\d+)\s*[-/]\s*\d+", bf)
        if mw:
            truth["bowling_best_wickets"] = int(mw.group(1))
    for f in DERIVED_FIELDS:
        if present(f):
            truth["provided_" + f] = to_float(values[f])

    runs = truth["batting_runs"]
    inns = truth["batting_innings"]
    bat_avg = truth["provided_batting_average"]
    bat_sr = truth["provided_batting_strike_rate"]

    # not-outs from average: outs = runs / avg, not_outs = innings − outs.
    if not present("batting_not_outs") and bat_avg and bat_avg > 0 and runs and inns:
        outs = round(runs / bat_avg)
        no = inns - outs
        truth["batting_not_outs"] = max(0, min(inns, int(no)))
        notes.append("not-outs reconstructed from average (±1)")
    # balls faced from strike rate.
    if not present("batting_balls") and bat_sr and bat_sr > 0 and runs:
        truth["batting_balls"] = int(round(runs / bat_sr * 100))
        notes.append("balls faced reconstructed from strike rate (±1)")

    # bowling_balls from overs (exact cricket-notation conversion).
    if not present("bowling_balls") and truth["bowling_overs"]:
        truth["bowling_balls"] = overs_to_balls(float(truth["bowling_overs"]))
    # overs from balls if only balls given.
    elif present("bowling_balls") and not truth["bowling_overs"] and truth["bowling_balls"]:
        b = truth["bowling_balls"]
        truth["bowling_overs"] = b // 6 + (b % 6) / 10

    # runs conceded from bowling average, else from economy + balls.
    wkts = truth["bowling_wickets"]
    bowl_avg = truth["provided_bowling_average"]
    bowl_econ = truth["provided_bowling_economy"]
    if not present("bowling_runs"):
        if bowl_avg and wkts:
            truth["bowling_runs"] = int(round(wkts * bowl_avg))
            notes.append("runs conceded reconstructed from bowling average (±1)")
        elif bowl_econ and truth["bowling_balls"]:
            truth["bowling_runs"] = int(round(bowl_econ * truth["bowling_balls"] / 6))
            notes.append("runs conceded reconstructed from economy (±1)")

    return truth, notes


# ── name column resolution ───────────────────────────────────────────────────
# A sheet's player identity can arrive as one combined column ("Jack Barendse",
# "Barendse, Jack", "Barendse J") or as two separate columns (first name +
# surname — or surname + a bare initial, which is the same shape). Two columns
# are unambiguous by construction (the sheet has already told us which part is
# which), so that's the option to reach for whenever a sheet offers it. A single
# combined column still needs *some* rule for word order — ``NAME_FORMAT_LABELS``
# lets the person doing the import say what their sheet uses instead of leaving
# it to a heuristic that guesses wrong on a plain "Surname Firstname" column
# (no comma to key off) by reading the surname as the first name.

NAME_FORMAT_LABELS = {
    "auto": "Auto-detect (recommended)",
    "first_last": "First name then Surname — e.g. “Jack Barendse”",
    "last_first": "Surname then First name — e.g. “Barendse Jack” or “Barendse, Jack”",
}


def apply_name_format(raw: str, name_format: str) -> str:
    """Reorder a single combined-name cell into 'First Last' according to an
    explicitly chosen format, so matching doesn't have to guess.

    'auto' and 'first_last' return the cell unchanged — 'auto' leaves the
    existing comma/initial heuristics in ``_normalise_name``/``_parse_initial_form``
    to do the work (unchanged behaviour), and a sheet already in "First Last"
    order needs no reordering. 'last_first' forces a surname-first reading even
    when there's no comma to key off (the one case those heuristics can't tell
    apart from a plain "First Last" column) — comma or not, the LAST token is
    read as the given name/initial and everything before it as the surname, so
    a multi-word surname ("Van Der Berg Jack" → "Jack Van Der Berg") still comes
    out right.
    """
    raw = (raw or "").strip()
    if not raw or name_format not in ("last_first",):
        return raw
    if "," in raw:
        last, first = raw.split(",", 1)
        return f"{first.strip()} {last.strip()}".strip()
    toks = raw.split()
    if len(toks) < 2:
        return raw
    return f"{toks[-1]} {' '.join(toks[:-1])}".strip()


def combine_name_parts(first: str, last: str) -> str:
    """First-name and surname columns → one 'First Last' string, ready for the
    normal name matcher. A bare surname (no first-name column, or an empty cell
    on this row) passes through as a mononym — ``match_players`` still handles
    that via an exact-string match, just without the first/last-aware fuzzy
    passes. A surname column paired with just an initial column works for free:
    "F" + "Camarda" → "F Camarda", which ``_parse_initial_form`` already reads
    as surname-plus-initial regardless of which side the initial is on.
    """
    first = (first or "").strip()
    last = (last or "").strip()
    return f"{first} {last}".strip()


def resolve_row_name(row: dict, name_col=None, first_col=None, last_col=None,
                      name_format: str = "auto") -> str:
    """The one place a row's raw player-name string is built, whichever of the
    three column layouts the sheet uses. Separate first/last columns win
    outright when either is mapped (unambiguous by construction); otherwise the
    single combined column is read through ``apply_name_format``.
    """
    if first_col or last_col:
        first = str(row.get(first_col, "")).strip() if first_col else ""
        last = str(row.get(last_col, "")).strip() if last_col else ""
        return combine_name_parts(first, last)
    raw = str(row.get(name_col, "")).strip() if name_col else ""
    return apply_name_format(raw, name_format)


# ── name + season matching ────────────────────────────────────────────────────

def _normalise_name(name: str) -> str:
    """Mirror admin._normalise: 'Last, First' → 'first last', collapse spaces.

    Splits on a bare comma (not the literal ", " substring) and strips each side
    before rejoining — a stray space before the comma ("Hampton , Neil", a real
    typo found in a club's 50-year stats sheet) used to leave a trailing space
    baked into the normalised key ("neil hampton "), silently failing to match
    the correctly-typed "Hampton, Neil" elsewhere in the same sheet and minting
    a duplicate player instead. A comma with nothing after it (a surname-only
    historical row, e.g. "Bartley, ") now collapses to just the surname instead
    of keeping the stray comma character.
    """
    name = (name or "").strip()
    if "," in name:
        last, first = name.split(",", 1)
        name = f"{first.strip()} {last.strip()}".strip()
    return re.sub(r"\s+", " ", name).strip().lower()


def _parse_initial_form(name: str):
    """If ``name`` reads as 'Surname Initial' or 'Initial Surname' (one token is a
    single letter), return ``(surname_last_token, initial)`` so it can be matched
    against a full 'First Last' record; otherwise ``None``.

    Examples → ('camarda', 'f'): "Camarda F", "F Camarda", "Van Der Berg F".
    Uses the last surname token (so middle names on our side still match).

    Dots are treated as separators first — "K. Adair" and "R.J. Manning" are
    the dominant style in a real historical club sheet (found via a ~2,100-row
    career-totals import: roughly half its rows write an initial this way),
    and without this the trailing dot inflates "k." to two characters, so
    neither length-1 branch below ever fires and every one of those rows is
    read as a brand-new, never-seen name instead of an abbreviation of an
    existing player. "R.J. Manning" collapses to three tokens ("r", "j",
    "manning") the same way — the middle initial is dropped here exactly as
    it already is for a plain "R Manning", which is an accepted, pre-existing
    limit of surname+first-initial matching, not something this fix changes.
    """
    toks = re.sub(r"\s+", " ", _normalise_name(name).replace(".", " ")).strip().split()
    if len(toks) < 2:
        return None
    if len(toks[-1]) == 1 and len(toks[-2]) > 1:   # "Camarda F" / "Van Der Berg F"
        return (toks[-2], toks[-1])
    if len(toks[0]) == 1 and len(toks[-1]) > 1:    # "F Camarda" / "F Van Der Berg" / "R.J. Manning"
        return (toks[-1], toks[0])
    return None


def _name_parts(nn: str):
    """``(first, last, [middles])`` for a normalised name, or ``None`` for a
    mononym. Dots are treated as separators so "sahan n.b. amaratunge" →
    ("sahan", "amaratunge", ["n", "b"]) and "alan d.s. armstrong" →
    ("alan", "armstrong", ["d", "s"])."""
    toks = re.sub(r"\s+", " ", (nn or "").replace(".", " ")).strip().split()
    if len(toks) < 2:
        return None
    return (toks[0], toks[-1], toks[1:-1])


def _middles_compatible(a: list, b: list) -> bool:
    """True when two lists of middle tokens could belong to the same person:
    either side empty (one record simply omits the middle name/initial), or the
    lists align token-for-token with each pair equal or one an initial of the
    other ("r" ~ "robert"). Used to treat "Craig R Allen" and our "Craig Allen"
    as the same player without a manual confirm."""
    if not a or not b:
        return True
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if x == y:
            continue
        if x[0] == y[0] and (len(x) == 1 or len(y) == 1):
            continue
        return False
    return True


def match_players(names: list, players: list, fuzzy_threshold: float = 0.84) -> dict:
    """names → match info. ``players`` = list of (id, display_name).

    status: 'exact' (auto-accept), 'ambiguous' (two records share the name —
    merge first), 'fuzzy' (needs confirmation), 'none' (pick or create new).
    ``auto_status`` mirrors the natural status and is left untouched when an
    override is later applied, so the UI can keep stable name buckets.

    Performance: normalised player names are computed once, and fuzzy matching
    is blocked by the first character of the normalised name — so an N-name sheet
    against an M-player roster is roughly N×(M/26) ratio calls, not N×M. That's
    the difference between a snappy preview and a frozen tab on a 1,600-name club.
    """
    norm_map: dict = {}
    blocks: dict = {}
    surname_initial: dict = {}          # (surname_last_token, first_initial) → [(pid, pname)]
    first_last: dict = {}               # (first, last) → [(pid, pname, [middles])]
    for pid, pname in players:
        nn = _normalise_name(pname)
        norm_map.setdefault(nn, []).append((pid, pname))
        blocks.setdefault(nn[:1], []).append((pid, pname, nn))
        toks = nn.split()
        if len(toks) >= 2 and len(toks[-1]) > 1:
            surname_initial.setdefault((toks[-1], toks[0][0]), []).append((pid, pname))
        parts = _name_parts(nn)
        if parts and len(parts[0]) > 1 and len(parts[1]) > 1:
            first_last.setdefault((parts[0], parts[1]), []).append((pid, pname, parts[2]))

    out: dict = {}
    for name in names:
        if name in out:
            continue
        n = _normalise_name(name)
        exact = norm_map.get(n, [])
        if len(exact) == 1:
            out[name] = {"player_id": str(exact[0][0]), "matched_name": exact[0][1],
                         "confidence": 1.0, "status": "exact", "auto_status": "exact", "candidates": []}
        elif len(exact) > 1:
            out[name] = {"player_id": None, "confidence": 1.0, "status": "ambiguous", "auto_status": "ambiguous",
                         "note": "Two players share this name — merge them first, then re-import.",
                         "candidates": [{"player_id": str(pid), "name": pn} for pid, pn in exact]}
        else:
            # Same first + last name, the only difference being an extra middle
            # initial/name on one side — "Craig R Allen" from a CricketStatz sheet
            # vs our "Craig Allen". A human reads those as one player, so auto-accept
            # when it resolves to exactly one of our players (full-string fuzzy only
            # scores ~0.92, which would otherwise flag every middle-initialled name
            # for manual review — 200+ on a single club import). Two same first+last
            # players are genuinely ambiguous, so those drop to a close match instead.
            parts = _name_parts(n)
            if parts and len(parts[0]) > 1 and len(parts[1]) > 1:
                fl_hits = [(pid, pn) for pid, pn, dmids in first_last.get((parts[0], parts[1]), [])
                           if _middles_compatible(parts[2], dmids)]
                if len(fl_hits) == 1:
                    out[name] = {"player_id": str(fl_hits[0][0]), "matched_name": fl_hits[0][1],
                                 "confidence": 0.98, "status": "exact", "auto_status": "exact",
                                 "candidates": [],
                                 "note": "Matched on first and last name (middle initial differs)."}
                    continue
                if len(fl_hits) > 1:
                    out[name] = {
                        "player_id": None, "confidence": 0.9,
                        "status": "fuzzy", "auto_status": "fuzzy",
                        "candidates": [{"player_id": str(pid), "name": pn, "confidence": 0.9}
                                       for pid, pn in fl_hits[:5]],
                    }
                    continue
            # "Surname Initial" sheets (e.g. "Camarda F") are common and full-string
            # fuzzy matching misses them — the words are reordered, so they don't even
            # share a first-character block. Match on exact surname + first-name
            # initial and surface the hit(s) as close matches to *confirm*. Never
            # auto-accept: an initial isn't a unique identity, so a genuinely new
            # "Smith J" must not silently merge into an existing different "John Smith".
            ikey = _parse_initial_form(name)
            init_hits = surname_initial.get(ikey, []) if ikey else []
            if init_hits:
                conf = 0.9 if len(init_hits) == 1 else 0.8
                out[name] = {
                    "player_id": None, "confidence": conf,
                    "status": "fuzzy", "auto_status": "fuzzy",
                    "candidates": [{"player_id": str(pid), "name": pn, "confidence": conf}
                                   for pid, pn in init_hits[:5]],
                }
                continue
            pool = blocks.get(n[:1], [])
            scored = sorted(
                ((SequenceMatcher(None, n, nn).ratio(), pid, pn) for pid, pn, nn in pool),
                key=lambda t: t[0], reverse=True,
            )[:5]
            top = scored[0][0] if scored else 0.0
            cands = [{"player_id": str(pid), "name": pn, "confidence": round(sc, 2)}
                     for sc, pid, pn in scored if sc >= 0.5]
            st = "fuzzy" if top >= fuzzy_threshold else "none"
            out[name] = {
                "player_id": None,
                "confidence": round(top, 2),
                "status": st, "auto_status": st,
                "candidates": cands,
            }
    return out


_PRIOR_RE = re.compile(
    r"prior|adjust|career|to\s*date|^total|various|all\s+seasons|earlier|historical|pre[\s-]|misc|life\s*time|overall",
    re.I,
)
_YEAR_RE = re.compile(r"(19|20)\d{2}")
_SHORT_RE = re.compile(r"\b(\d{2})\s*/\s*(\d{2})\b")


def _season_years(label: str) -> set:
    yrs = set()
    for m in _YEAR_RE.finditer(label or ""):
        yrs.add(int(m.group(0)))
    for m in _SHORT_RE.finditer(label or ""):
        yy = int(m.group(1))
        yrs.add(2000 + yy if yy < 50 else 1900 + yy)
    return yrs


def _norm_season(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9/]+", " ", str(s or "").lower())).strip()


def match_seasons(labels: list, seasons: list, threshold: float = 0.84) -> dict:
    """labels → match info. ``seasons`` = list of (id, name, year).

    A label that reads like a catch-all ("Prior Seasons & Adjustments", "Career
    total", …) is flagged ``is_prior`` and routed to the residual bucket.
    """
    name_map = {_norm_season(nm): (sid, nm) for sid, nm, _yr in seasons}
    out: dict = {}
    for label in labels:
        if label in out:
            continue
        if not str(label).strip() or _PRIOR_RE.search(label or ""):
            out[label] = {"season_id": None, "is_prior": True, "status": "prior", "auto_status": "prior", "candidates": []}
            continue
        ln = _norm_season(label)
        if ln in name_map:
            sid, nm = name_map[ln]
            out[label] = {"season_id": str(sid), "matched_name": nm, "status": "exact",
                          "auto_status": "exact", "is_prior": False, "confidence": 1.0, "candidates": []}
            continue
        yrs = _season_years(label)
        if yrs:
            # A label that names its own year belongs to that year and no other.
            # Season names are near-identical strings by construction, so string
            # similarity is meaningless here: "Summer 2020/21" and "Summer
            # 2010/11" differ by two digits out of fourteen and score 0.86,
            # over the auto-accept threshold. That silently filed a club's
            # 2020/21 history under 2010/11 — or, for a club that had only its
            # synced seasons when it imported, under this season. Reported live:
            # a season-by-season upload where three of the club's own seasons
            # were absent, so their figures landed on the wrong years and the
            # career read well over what the club's own book said.
            same_year = sorted(
                ((SequenceMatcher(None, ln, _norm_season(nm)).ratio(), sid, nm)
                 for sid, nm, yr in seasons
                 if (yr is not None and yr in yrs) or (_season_years(nm) & yrs)),
                key=lambda t: t[0], reverse=True,
            )
            cands = [{"season_id": str(sid), "name": nm, "confidence": round(max(sc, 0.92), 2)}
                     for sc, sid, nm in same_year[:5]]
            if len(same_year) == 1 or (same_year and same_year[0][0] >= threshold):
                out[label] = {"season_id": str(same_year[0][1]), "matched_name": same_year[0][2],
                              "status": "matched", "auto_status": "matched", "is_prior": False,
                              "confidence": 0.92, "candidates": cands}
            elif same_year:
                # Several of this club's seasons carry that year — a person picks.
                out[label] = {"season_id": None, "status": "none", "auto_status": "none",
                              "is_prior": False, "candidates": cands}
            else:
                # No season for that year yet. Create it on this step, or send it
                # to the career bucket — never quietly onto a different year.
                out[label] = {"season_id": None, "status": "none", "auto_status": "none",
                              "is_prior": False, "candidates": []}
            continue
        scored = []
        for sid, nm, yr in seasons:
            score = SequenceMatcher(None, ln, _norm_season(nm)).ratio()
            scored.append((score, sid, nm))
        scored.sort(key=lambda t: t[0], reverse=True)
        top = scored[:5]
        cands = [{"season_id": str(sid), "name": nm, "confidence": round(sc, 2)} for sc, sid, nm in top if sc >= 0.5]
        if top and top[0][0] >= threshold:
            out[label] = {"season_id": str(top[0][1]), "matched_name": top[0][2],
                          "status": "matched", "auto_status": "matched", "is_prior": False,
                          "confidence": round(top[0][0], 2), "candidates": cands}
        else:
            out[label] = {"season_id": None, "status": "none", "auto_status": "none", "is_prior": False, "candidates": cands}
    return out


def match_grades(labels: list, grade_names: list, threshold: float = 0.72) -> dict:
    """Sheet grade/team labels -> a real, GR-synced grade name (or no match).

    ``grade_names`` is the org's own distinct, merge-resolved grade names (what
    ``aggregations._GRADE_MATCH`` groups by) — NOT the club's shorthand. A club's
    historical sheet often uses terse internal codes ("1A", "B", "A/R") that
    never literally equal the real CA-synced grade name, so this must be an
    explicit matching step rather than the exact-string comparison the
    reconciler itself uses (see the "grade-scoped BetterImport" investigation:
    an unmatched grade silently read as "GR has zero coverage here", so the
    club's whole sheet got added on top of data that was already synced).

    Unlike players/seasons, there is deliberately **no silent auto-default for
    an unresolved label** — the caller must leave it unresolved (folds into the
    safe whole-career comparison) or have the admin explicitly confirm "no
    online equivalent" (folds into its own free-text bucket, the pre-fix
    behaviour, now opt-in). ``status``: 'exact' (normalised name match,
    auto-accept), 'fuzzy' (candidates, needs confirmation), 'none' (no
    confident candidate).
    """
    name_map = {_norm_season(nm): nm for nm in grade_names}
    out: dict = {}
    for label in labels:
        if label in out:
            continue
        if not str(label).strip():
            out[label] = {"grade_name": None, "status": "none", "auto_status": "none",
                          "confidence": 0.0, "candidates": []}
            continue
        ln = _norm_season(label)
        if ln in name_map:
            nm = name_map[ln]
            out[label] = {"grade_name": nm, "matched_name": nm, "status": "exact",
                          "auto_status": "exact", "confidence": 1.0, "candidates": []}
            continue
        scored = sorted(
            ((SequenceMatcher(None, ln, _norm_season(nm)).ratio(), nm) for nm in grade_names),
            key=lambda t: t[0], reverse=True,
        )
        top = scored[0][0] if scored else 0.0
        cands = [{"grade_name": nm, "name": nm, "confidence": round(sc, 2)} for sc, nm in scored[:5] if sc >= 0.4]
        status = "fuzzy" if top >= threshold else "none"
        out[label] = {"grade_name": None, "status": status, "auto_status": status,
                      "confidence": round(top, 2), "candidates": cands}
    return out
