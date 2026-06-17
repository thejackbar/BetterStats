#!/usr/bin/env python3
"""Generate a per-club copy of the initial outreach email with a club-specific
utm_source.

The template (email-initial-demo.html) tags every link with utm_source=ca.
For each club this writes sends/initial-email-<slug>.html with utm_source=ca
globally replaced by utm_source=<slug>. utm_medium/utm_campaign are untouched.

Usage:
  python make_sends.py "Applecross Cricket Club" "Bayswater Morley CC"
  python make_sends.py --from clubs.txt        # one club name per line
  python make_sends.py --csv clubs.csv         # a sheet with 'Club' and 'UTM' columns
"""
import csv
import re
import sys
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
TEMPLATE = HERE / "email-initial-demo.html"
OUT = HERE / "sends"


def slug(name: str) -> str:
    s = name.strip().lower()
    s = s.replace("'", "").replace("’", "")   # drop apostrophes
    s = re.sub(r"[^a-z0-9]+", "-", s)              # any other punctuation/space -> hyphen
    return re.sub(r"-+", "-", s).strip("-")


def from_csv(path):
    """Yield (label, slug) from a CSV that has a 'Club' and a 'UTM' header row.
    Uses the sheet's UTM value when present, else slugs the club name."""
    rows = list(csv.reader(open(path, newline="", encoding="utf-8")))
    hdr_idx = next((i for i, r in enumerate(rows)
                    if "club" in [c.strip().lower() for c in r]
                    and "utm" in [c.strip().lower() for c in r]), None)
    if hdr_idx is None:
        raise SystemExit("No header row containing both 'Club' and 'UTM' was found.")
    hdr = [c.strip().lower() for c in rows[hdr_idx]]
    club_i, utm_i = hdr.index("club"), hdr.index("utm")
    pairs = []
    for r in rows[hdr_idx + 1:]:
        club = r[club_i].strip() if len(r) > club_i else ""
        utm = r[utm_i].strip() if len(r) > utm_i else ""
        if not club and not utm:
            continue
        sl = slug(utm) if utm else slug(club)
        if sl:
            pairs.append((club or utm, sl))
    return pairs


def generate(pairs):
    tpl = TEMPLATE.read_text(encoding="utf-8")
    OUT.mkdir(exist_ok=True)
    made, seen = [], set()
    for label, sl in pairs:
        if sl in seen:
            print(f"  ! duplicate slug skipped: {label} ({sl})")
            continue
        seen.add(sl)
        html = tpl.replace("utm_source=ca", f"utm_source={sl}")
        path = OUT / f"initial-email-{sl}.html"
        path.write_text(html, encoding="utf-8")
        made.append((label, sl, path))
    return made


def main(argv):
    if argv and argv[0] == "--csv":
        pairs = from_csv(argv[1])
    elif argv and argv[0] == "--from":
        names = [l.strip() for l in pathlib.Path(argv[1]).read_text(encoding="utf-8").splitlines() if l.strip()]
        pairs = [(n, slug(n)) for n in names]
    else:
        pairs = [(n, slug(n)) for n in argv]
    if not pairs:
        print("Give club names as arguments, --from <file>, or --csv <file>.")
        return 1
    for label, sl, path in generate(pairs):
        print(f"{label}  ->  {path.name}  (utm_source={sl})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
