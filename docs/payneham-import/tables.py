"""Shared helpers for reading the fixed-width tables in 'Runs Galore'."""
import re
import subprocess

SEASON_RE = re.compile(r"\b(1[89]\d{2}|20\d{2})\s*[-/]\s*(\d{2})\b")
_LABEL_WORDS = {"Name", "Player", "Batsman", "Batsmen", "Bowler", "Score", "Keeper"}

MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def layout(pdf, first=None, last=None):
    cmd = ["pdftotext", "-layout"]
    if first:
        cmd += ["-f", str(first), "-l", str(last)]
    cmd += [pdf, "-"]
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def _header_starts(header):
    """The x of each heading in a header line, splitting a merged '<metric> Name'."""
    out = []
    for m in re.finditer(r"\S+(?: \S+)*?(?=\s{2,}|$)", header):
        name = m.group().strip()
        if not name:
            continue
        words = name.split()
        if len(words) == 2 and words[1] in _LABEL_WORDS:
            out += [m.start(), header.index(words[1], m.start())]
        else:
            out.append(m.start())
    return out


def bands(header):
    """Column bands from a header line: [(name, lo, hi), ...].

    Boundaries sit midway between one heading's end and the next one's start, which
    tolerates a value printed slightly left or right of its heading.
    """
    toks = []
    for m in re.finditer(r"\S+(?: \S+)*?(?=\s{2,}|$)", header):
        name = m.group().strip()
        if not name:
            continue
        words = name.split()
        # 'Wkts Name' / 'Dis. Name' / 'Wkt Score' — two headings set one space apart,
        # which reads as a single token. Split it back into the two columns it is.
        if len(words) == 2 and words[1] in _LABEL_WORDS:
            at = header.index(words[1], m.start())
            toks.append((m.start(), m.start() + len(words[0]), words[0]))
            toks.append((at, m.end(), words[1]))
        else:
            toks.append((m.start(), m.end(), name))
    out = []
    for i, (s, e, name) in enumerate(toks):
        lo = 0 if i == 0 else (toks[i - 1][1] + s) // 2
        hi = (e + toks[i + 1][0]) // 2 if i + 1 < len(toks) else 10_000
        out.append((name, lo, hi))
    return out


def gutter_bands(header, body, min_gap=2):
    """Column bands found from the whitespace gutters the table actually leaves.

    Midpoints between headings are no good here: several headings are centred over
    their column ('Batsmen' sits well right of the names under it), so the boundary
    lands mid-word. A gutter that no row crosses is the real column edge.
    """
    rows = [header] + list(body)
    width = max((len(r) for r in rows), default=0)
    filled = [any(x < len(r) and r[x] != " " for r in rows) for x in range(width)]

    cuts, run = [], 0
    for x in range(width + 1):
        if x < width and not filled[x]:
            run += 1
            continue
        if run >= min_gap:
            cuts.append((x - run, x))
        run = 0

    edges = [0] + [(lo + hi) // 2 for lo, hi in cuts] + [10_000]
    spans = [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]

    named = {}
    for m in re.finditer(r"\S+(?: \S+)*?(?=\s{2,}|$)", header):
        name = m.group().strip()
        if not name:
            continue
        over = [s for s in spans if s[0] < m.end() and m.start() < s[1]]
        words = name.split()
        # 'Wkts Name' is two headings set with a single space between them. When a
        # heading straddles exactly as many columns as it has words, it is really
        # that many headings; otherwise it is one wide heading.
        if len(over) > 1 and len(words) == len(over):
            for w, s in zip(words, over):
                named.setdefault(w, s)
            continue
        # 'Wkts Name' / 'Wkt Score' / 'Dis. Name' — a metric heading set one space
        # from the next heading, with no gutter under it because the values below
        # run together. Split the band at the second heading's own position.
        if len(words) == 2 and over and words[1] in _LABEL_WORDS:
            at = header.index(words[1], m.start())
            lo, hi = over[0]
            named.setdefault(words[0], (lo, at))
            named.setdefault(words[1], (at, hi))
            continue
        span = over[0] if over else None
        if span and span not in named.values():
            named[name] = span
    return spans, named


def snap_bands(header, body):
    """Header-named bands whose edges are snapped to the gutters the data leaves.

    The midpoint between two headings can fall inside a value ('DJ  Von Einem' runs
    past halfway to the next heading), so each boundary is moved to the nearest
    gutter no row crosses. Names come from the header, edges from the data.
    """
    cols = bands(header)
    if not cols or not body:
        return cols
    rows = [header] + list(body)
    width = max(len(r) for r in rows)
    filled = [any(x < len(r) and r[x] != " " for r in rows) for x in range(width)]
    gutters, run = [], 0
    for x in range(width + 1):
        if x < width and not filled[x]:
            run += 1
            continue
        if run >= 2:
            gutters.append((x - run + x) // 2)
        run = 0
    if not gutters:
        return cols

    # Each boundary goes at the last gutter before the next heading starts, so a
    # wide value keeps its whole column and nothing bleeds into the one after it.
    starts = _header_starts(header)
    edges = []
    for i, (name, lo, hi) in enumerate(cols[1:], 1):
        start = starts[i] if i < len(starts) else lo
        before = [g for g in gutters if g <= start]
        edges.append(max(before) if before else lo)
    out = []
    for i, (name, lo, hi) in enumerate(cols):
        new_lo = 0 if i == 0 else edges[i - 1]
        new_hi = edges[i] if i < len(edges) else 10_000
        out.append((name, new_lo, new_hi))
    # A stray row from the table below can drag a boundary past the one before it
    # and collapse a column to nothing. Snapping is an improvement, not a
    # requirement, so an implausible result falls back to the plain header bands.
    if any(hi - lo < 3 for _, lo, hi in out) or \
       any(out[i][1] >= out[i + 1][1] for i in range(len(out) - 1)):
        return cols
    return out


def cells(line, cols):
    return {name: line[lo:hi].strip() for name, lo, hi in cols}


def tidy_name(s):
    """'KJ   Duke' -> 'KJ Duke'; 'L    Di Venuto' -> 'L Di Venuto'."""
    s = re.sub(r"\s+", " ", (s or "")).strip()
    s = re.sub(r"^\[\s*", "", s)
    s = s.rstrip("*+#%. ").strip()
    return s


def is_name(s):
    """A real person's name, not page furniture or a heading."""
    if not s or len(s) < 3:
        return False
    if not re.search(r"[a-z]", s):          # headings are ALL CAPS; names are not
        return False
    if not re.match(r"^[A-Za-z][A-Za-z .'’\-]*$", s):
        return False
    return len(s.split()) <= 5


def season_from_date(token):
    """'Nov-43' / 'Mar-48' -> the season START year (Australian season Sep-Mar)."""
    m = re.match(r"([A-Za-z]{3})[-/ ]\s*(\d{2,4})$", (token or "").strip())
    if not m:
        return None
    mon = MONTHS.get(m.group(1).title())
    if not mon:
        return None
    yr = int(m.group(2))
    if yr < 100:
        yr += 1900 if yr >= 30 else 2000
    # Jan-Jun belongs to the season that started the previous calendar year.
    return yr - 1 if mon <= 6 else yr


def season_label(year):
    return f"{year}/{str((year + 1) % 100).zfill(2)}" if year else ""


def to_int(s):
    m = re.search(r"-?\d+", (s or "").replace(",", ""))
    return int(m.group()) if m else None


def to_float(s):
    m = re.search(r"-?\d+(?:\.\d+)?", (s or "").replace(",", ""))
    return float(m.group()) if m else None
