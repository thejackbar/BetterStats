#!/usr/bin/env python3
"""Generate a per-club copy of the initial outreach email.

For each club this writes sends/initial-email-<slug>.html with:
  * utm_source=ca globally replaced by utm_source=<slug>
  * the "Hi [first name]," greeting replaced by the club's contacts

The template (email-initial-demo.html) tags every link with utm_source=ca and
opens with "Hi [first name],". utm_medium/utm_campaign are untouched.

Usage:
  python make_sends.py "Applecross Cricket Club"      # utm only, greeting left as placeholder
  python make_sends.py --from clubs.txt               # one club name per line
  python make_sends.py --csv clubs.csv                # sheet with Club, UTM and Name columns
"""
import csv
import re
import sys
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
TEMPLATE = HERE / "email-initial-demo.html"
OUT = HERE / "sends"
GREETING_PLACEHOLDER = "Hi [first name],"
GREETING_FALLBACK = "Hi there,"


def slug(name: str) -> str:
    s = name.strip().lower()
    s = s.replace("'", "").replace("’", "")   # drop apostrophes
    s = re.sub(r"[^a-z0-9]+", "-", s)              # any other punctuation/space -> hyphen
    return re.sub(r"-+", "-", s).strip("-")


def first_name(full: str) -> str:
    return full.strip().split()[0] if full.strip() else ""


def greeting(names) -> str:
    seen, uniq = set(), []
    for n in (first_name(x) for x in names):
        if n and n.lower() not in seen:
            seen.add(n.lower())
            uniq.append(n)
    if not uniq:
        return GREETING_FALLBACK
    if len(uniq) == 1:
        return f"Hi {uniq[0]},"
    if len(uniq) == 2:
        return f"Hi {uniq[0]} and {uniq[1]},"
    return "Hi " + ", ".join(uniq[:-1]) + f" and {uniq[-1]},"


def from_csv(path):
    """Yield (label, slug, greeting). Uses the sheet's UTM column as the slug
    (falls back to slugging the club name) and every 'Name' column as a contact."""
    rows = list(csv.reader(open(path, newline="", encoding="utf-8")))
    hdr_idx = next((i for i, r in enumerate(rows)
                    if "club" in [c.strip().lower() for c in r]
                    and "utm" in [c.strip().lower() for c in r]), None)
    if hdr_idx is None:
        raise SystemExit("No header row containing both 'Club' and 'UTM' was found.")
    hdr = [c.strip().lower() for c in rows[hdr_idx]]
    club_i, utm_i = hdr.index("club"), hdr.index("utm")
    name_cols = [i for i, c in enumerate(hdr) if c == "name"]
    items = []
    for r in rows[hdr_idx + 1:]:
        cell = lambda i: r[i].strip() if len(r) > i else ""
        club, utm = cell(club_i), cell(utm_i)
        if not club and not utm:
            continue
        sl = slug(utm) if utm else slug(club)
        if not sl:
            continue
        items.append((club or utm, sl, greeting([cell(i) for i in name_cols])))
    return items


def generate(items):
    tpl = TEMPLATE.read_text(encoding="utf-8")
    OUT.mkdir(exist_ok=True)
    made, seen = [], set()
    for label, sl, greet in items:
        if sl in seen:
            print(f"  ! duplicate slug skipped: {label} ({sl})")
            continue
        seen.add(sl)
        html = tpl.replace("utm_source=ca", f"utm_source={sl}")
        if greet:
            html = html.replace(GREETING_PLACEHOLDER, greet)
        path = OUT / f"initial-email-{sl}.html"
        path.write_text(html, encoding="utf-8")
        made.append((label, sl, greet))
    return made


def main(argv):
    if argv and argv[0] == "--csv":
        items = from_csv(argv[1])
    elif argv and argv[0] == "--from":
        names = [l.strip() for l in pathlib.Path(argv[1]).read_text(encoding="utf-8").splitlines() if l.strip()]
        items = [(n, slug(n), None) for n in names]
    else:
        items = [(n, slug(n), None) for n in argv]
    if not items:
        print("Give club names as arguments, --from <file>, or --csv <file>.")
        return 1
    for label, sl, greet in generate(items):
        print(f"{label}  ->  initial-email-{sl}.html  |  {greet or GREETING_PLACEHOLDER}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
