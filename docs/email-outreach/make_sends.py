#!/usr/bin/env python3
"""Generate a per-club copy of the initial outreach email with a club-specific
utm_source.

The template (email-initial-demo.html) tags every link with utm_source=ca.
For each club name this writes sends/initial-email-<slug>.html with utm_source=ca
globally replaced by utm_source=<slug>. utm_medium/utm_campaign are untouched.

Usage:
  python make_sends.py "Applecross Cricket Club" "Bayswater Morley CC"
  python make_sends.py --from clubs.txt        # one club name per line
"""
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


def generate(names):
    tpl = TEMPLATE.read_text(encoding="utf-8")
    OUT.mkdir(exist_ok=True)
    made = []
    for name in names:
        sl = slug(name)
        if not sl:
            continue
        html = tpl.replace("utm_source=ca", f"utm_source={sl}")
        path = OUT / f"initial-email-{sl}.html"
        path.write_text(html, encoding="utf-8")
        made.append((name, sl, path))
    return made


def main(argv):
    if argv and argv[0] == "--from":
        names = [l.strip() for l in pathlib.Path(argv[1]).read_text(encoding="utf-8").splitlines() if l.strip()]
    else:
        names = argv
    if not names:
        print("Give club names as arguments, or --from <file> (one club per line).")
        return 1
    for name, sl, path in generate(names):
        print(f"{name}  ->  {path.name}  (utm_source={sl})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
