"""Parse the Payneham 'Runs Galore' club-awards section into BetterStats award rows."""
import csv
import re
import subprocess

PDF = "rg1.pdf"
SEASON_RE = re.compile(r"\b(1[89]\d{2}|20\d{2})\s*[-/]\s*(\d{2})\b")


def layout(first, last, pdf=PDF):
    return subprocess.run(
        ["pdftotext", "-layout", "-f", str(first), "-l", str(last), pdf, "-"],
        capture_output=True, text=True, check=True).stdout


def season_label(m):
    """'1953-54' -> '1953/54'."""
    return f"{m.group(1)}/{m.group(2)}"


def columns(lines):
    """Cluster the x-offsets of season tokens into column start positions."""
    offs = sorted({m.start() for ln in lines for m in SEASON_RE.finditer(ln)})
    if not offs:
        return [0]
    cols = [offs[0]]
    for o in offs[1:]:
        if o - cols[-1] > 20:
            cols.append(o)
    return cols


def rows(lines):
    """Yield (season, cell_text) walking each column top-to-bottom.

    A cell with no season of its own continues the season above it in the same
    column — the book's way of showing joint winners ('[ N J Mosey' / '[ J J Gaerth').
    """
    cols = columns(lines)
    bounds = [(c, cols[i + 1] if i + 1 < len(cols) else 10_000) for i, c in enumerate(cols)]
    carried = [None] * len(bounds)
    out = []
    for ln in lines:
        for i, (lo, hi) in enumerate(bounds):
            cell = ln[lo:hi].strip()
            if not cell:
                continue
            m = SEASON_RE.match(cell)
            if m:
                carried[i] = season_label(m)
                rest = cell[m.end():].strip()
                if rest:
                    out.append((len(out), i, carried[i], rest))
            elif carried[i] and not cell.startswith("("):
                out.append((len(out), i, carried[i], cell))
    # Column-major order is how the book reads; sort by column then original order.
    out.sort(key=lambda r: (r[1], r[0]))
    return [(s, c) for _, _, s, c in out]


NOISE = re.compile(r"^(see above|=+|-+|\*+|#+|%+|\+)", re.I)
TRAIL = re.compile(r"\s+(male|female|GF|SF|\(BBM\)|\(BBI\)|#+|%+|\*\*|\+HT)\s*$", re.I)


def clean(cell):
    """Split a cell into (player, detail). The book puts team/score/points after the name."""
    cell = re.sub(r"^\[\s*", "", cell).strip()
    cell = re.sub(r"\s{2,}", "  ", cell)
    if NOISE.match(cell):
        return None, None
    # Name is the leading run of name-ish words; everything after two+ spaces is detail.
    parts = re.split(r"\s{2,}", cell, maxsplit=1)
    name = parts[0].strip()
    detail = parts[1].strip() if len(parts) > 1 else ""
    # A trailing bare number glued to the name with one space is a value, not a surname.
    m = re.match(r"^(.*?)\s+([\d.]+\*?)$", name)
    if m and re.search(r"[A-Za-z]", m.group(1)):
        name, detail = m.group(1).strip(), (m.group(2) + " " + detail).strip()
    # Page furniture and the odd donor plaque are set in capitals; a real name
    # always carries lower case ('J Towill', 'RHJ Westley').
    if not re.search(r"[a-z]", name) or not re.search(r"[A-Za-z]{2}", name):
        return None, None
    if "ONGOING AWARD" in name.upper():
        return None, None
    return name, detail


# (heading line, award name, subcategory, category, page range)
AWARDS = [
    ("H R JAMES MEMORIAL TROPHY", "H R James Memorial Trophy", "Club Batting Aggregate"),
    ("N T PATTEN MEMORIAL TROPHY", "N T Patten Memorial Trophy", "Club Bowling Aggregate"),
    ("A A PARHAM MEMORIAL TROPHY", "A A Parham Memorial Trophy", "Outstanding Batting Performance"),
    ("R K SAUNDERS MEMORIAL TROPHY", "R K Saunders Memorial Trophy", "Outstanding Bowling Performance"),
    ("I W SCOTT TROPHY", "I W Scott Trophy", "Outstanding Performance by a Junior"),
    ("B G EASTHER TROPHY", "B G Easther Trophy", "First XI Batting Aggregate"),
    ("J S H BICKLE MEMORIAL TROPHY", "J S H Bickle Memorial Trophy", "First XI Bowling Aggregate"),
    ("M R HANN MEMORIAL TROPHY", "M R Hann Memorial Trophy", "First XI Fielding"),
    ("MARY ELIZABETH HICKS TROPHY", "Mary Elizabeth Hicks Trophy", "Club Champion"),
    ("GRANT WASLEY MEDAL", "Grant Wasley Medal", "Senior Captain's Award"),
    ("TONY DURDIN MEDAL", "Tony Durdin Medal", "Junior Coaches Award"),
    ("Von EINEM MEDAL", "Von Einem Medal", "Women's Coaches Award"),
]

# Consistency awards are one heading covering several named trophies over time.
CONSISTENCY = [
    ("CONSISTENCY AWARDS - SENIORS", "WHOLE OF CLUB", "Club Consistency Award", "Consistency"),
    ("CONSISTENCY AWARDS - SENIORS", "OTHER SENIORS", "Senior Consistency Award", "Consistency"),
    ("CONSISTENCY AWARDS - JUNIORS", "JUNIORS", "Junior Consistency Award", "Consistency"),
    ("CONSISTENCY AWARDS - JUNIORS", "SUB JUNIORS", "Sub Junior Consistency Award", "Consistency"),
]


def blocks(text):
    """Split the section into (heading, lines) blocks, x-aware.

    Two awards can share a heading line side by side (Tony Durdin / Von Einem), so a
    heading carries its x-offset and the block is sliced to that column band.
    """
    lines = text.split("\n")
    heads = []          # (line_idx, x, key)
    keys = [k for k, *_ in AWARDS]
    for i, ln in enumerate(lines):
        up = ln.upper()
        for key in keys:
            x = up.find(key.upper())
            if x >= 0 and not up[:x].strip():          # first thing on the line
                heads.append((i, x, key))
            elif x > 0 and up[:x].rstrip().endswith(("MEDAL", "TROPHY")):
                heads.append((i, x, key))              # second award on a shared line
        for sub in ("WHOLE OF CLUB", "OTHER SENIORS", "JUNIORS", "SUB JUNIORS"):
            if ln.strip().upper().startswith(sub) and "TROPHY" in up:
                heads.append((i, 0, sub))
        # The caps list follows the last award and is full of season-looking rows —
        # stop there or it reads as 50 more fielding winners.
        if ln.strip().upper().startswith("FIRST XI CAP NUMBERS"):
            heads.append((i, 0, "__STOP__"))
    heads = sorted(set(heads))
    out = []
    for n, (i, x, key) in enumerate(heads):
        siblings = [h for h in heads if h[0] == i]          # awards sharing this line
        pos = siblings.index((i, x, key))
        lo = 0 if pos == 0 else x                            # leftmost owns the margin
        hi = siblings[pos + 1][1] if pos + 1 < len(siblings) else 10_000
        end = next((i2 for i2, _, _ in heads if i2 > i), len(lines))
        out.append((key, [ln[lo:hi] for ln in lines[i:end]]))
    return out


# The consistency trophies were renamed over the years; use the name that was on the
# trophy in that season rather than one modern label for a 60-year run.
ERAS = {
    "WHOLE OF CLUB": [(1958, 1975, "L A Walkely Trophy"), (1977, 1997, "Gordon Clark Trophy")],
    "OTHER SENIORS": [(1998, 2004, "'Clacka' Clark Trophy")],
    "JUNIORS": [(1994, 2015, "W D Gillard Trophy"), (2016, 2100, "R G Walsh Trophy")],
    "SUB JUNIORS": [(1900, 2100, "G F Vincent Trophy")],
}


def era_award(key, season, fallback):
    year = int(season[:4])
    for lo, hi, name in ERAS.get(key, []):
        if lo <= year <= hi:
            return name
    return fallback


def main():
    text = layout(126, 141)
    seen = set()
    rows_out = []
    sub_names = {
        "WHOLE OF CLUB": ("Club Consistency Award", "Consistency"),
        "OTHER SENIORS": ("Senior Consistency Award", "Consistency"),
        "JUNIORS": ("Junior Consistency Award", "Consistency"),
        "SUB JUNIORS": ("Sub Junior Consistency Award", "Consistency"),
    }
    lookup = {k.upper(): (name, sub) for k, name, sub in AWARDS}
    lookup.update({k: v for k, v in sub_names.items()})

    for key, lines in blocks(text):
        if key == "__STOP__":
            continue
        award, sub = lookup[key.upper()] if key.upper() in lookup else lookup[key]
        for season, cell in rows(lines):
            name, detail = clean(cell)
            if not name:
                continue
            award = era_award(key.upper(), season, award)
            k = (season, award, name)
            if k in seen:
                continue
            seen.add(k)
            rows_out.append([season, "Club Award", sub, award, name, detail])

    rows_out.sort(key=lambda r: (r[3], r[0]))
    with open("out_awards_club.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Season", "Category", "Subcategory", "Achievement", "Player Name", "Detail"])
        w.writerows(rows_out)
    print("club award rows:", len(rows_out))
    from collections import Counter
    for a, n in Counter(r[3] for r in rows_out).most_common():
        print(f"  {n:4d}  {a}")


if __name__ == "__main__":
    main()
