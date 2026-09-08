"""Reading a CricketStatz player's Notes as awards and honours.

A club's CricketStatz player page carries a free-text ``Notes`` block, and for
a club that has kept it properly that block IS the honour board — life
membership, first-grade caps, trophies won, captaincies and coaching stints,
all written in one house style::

    LIFE MEMBER ~ 1992-93
    A-GRADE CAP AND DEBUT #102 (1982-83)
    5x TED GARLAND BATTING AVERAGE WINNER
    SENIOR HEAD COACH (2011-15, 2023-25)
    N.M.C.A. - HALL OF FAME

**AN UNRECOGNISED NOTE IS NOT AN AWARD.** The same block also carries plain
biography — ``COLLINGWOOD FC (313 Games)``, ``wk`` — and filing those on a
club's honour board would put a football career among its cricket trophies.
Every line is classified or left alone; nothing is guessed at. That is the same
silence-where-we-cannot-answer rule the selection rules and the rate-coverage
note already keep.

Pure and DB-free, so the verification can exercise it without a session.
"""
from __future__ import annotations

import re
from typing import Optional

# ── the shapes a note carries ────────────────────────────────────────────────

# "5x TED GARLAND BATTING AVERAGE WINNER"
_TIMES = re.compile(r"^(\d{1,3})\s*x\s+", re.I)
# " ~ 1992-93", " (1982-83)", " (2011-15, 2023-25)", a bare trailing "2023-25"
_TRAILING_YEARS = re.compile(
    r"(?:\s*~\s*|\s*[:\-]?\s*\(|\s+)((?:\d{4}\s*-\s*\d{2,4})(?:\s*,\s*\d{4}\s*-\s*\d{2,4})*)\)?\s*$"
)
# "#102"
_NUMBER = re.compile(r"#\s*(\d{1,4})")
_YEAR_SPAN = re.compile(r"(\d{4})\s*-\s*(\d{2,4})")

# Anything outside Latin-1 — the cap emoji, the medal — carries no meaning we
# can file and would otherwise ride into an achievement's own name.
_NON_TEXT = re.compile(r"[^\x00-\xff]")


def _clean(line: str) -> str:
    return re.sub(r"\s+", " ", _NON_TEXT.sub(" ", line or "")).strip(" -–—:")


def season_label(first: str, second: str) -> Optional[str]:
    """"1982-83" is a SEASON; "2011-15" is a span of years.

    A season runs across two consecutive years, so the second half is the first
    plus one — that one test separates the two, and it holds at the century
    boundary as well ("1999-00" is a season, "1998-00" is a two-year span).
    Getting this wrong files a five-year coaching stint under a single season
    that never existed.
    """
    try:
        start = int(first)
        end = int(second)
    except (TypeError, ValueError):
        return None
    if len(second) == 4:
        return f"{start}/{str(end)[-2:]}" if end == start + 1 else None
    if (start + 1) % 100 == end % 100:
        return f"{start}/{second.zfill(2)}"
    return None


def _span_end(start: str, end: str) -> str:
    """The far end of a year span, written in full.

    A two-digit end rolls the century over when it is lower than the start's
    own two digits — "1998-00" ends in 2000, not 1900.
    """
    if len(end) == 4:
        return end
    century, tail = int(start) // 100, int(start) % 100
    value = int(end)
    if value < tail:
        century += 1
    return str(century * 100 + value)


def _split_years(line: str) -> tuple[str, list[tuple[str, str]]]:
    """Peel a trailing year token off a note. Returns (rest, [(from, to), …])."""
    match = _TRAILING_YEARS.search(line)
    if not match:
        return line, []
    spans = [(m.group(1), m.group(2)) for m in _YEAR_SPAN.finditer(match.group(1))]
    if not spans:
        return line, []
    return line[: match.start()].strip(" -–—:("), spans


# ── what a phrase means ──────────────────────────────────────────────────────

_LIFE_MEMBER = re.compile(r"\bLIFE\s+MEMBER", re.I)
_HALL_OF_FAME = re.compile(r"\bHALL\s+OF\s+FAME\b", re.I)
_CAP = re.compile(r"\bCAP\b", re.I)
_COACH = re.compile(r"\bCOACH\b", re.I)
_CAPTAIN = re.compile(r"\bCAPTAIN(?:CY)?\b", re.I)
_PRESIDENT = re.compile(r"\bPRESIDENT\b", re.I)
_SECRETARY = re.compile(r"\bSECRETARY\b", re.I)
_TREASURER = re.compile(r"\bTREASURER\b", re.I)

# A line has to look like a trophy before it is filed as one. A club writes an
# award as something WON, so these are the words that say so; everything else
# is left alone rather than swept onto the honour board.
_AWARD_WORDS = re.compile(
    r"\b(WINNER|WON|TROPHY|MEDAL|AWARD|CHAMPION|AGGREGATE|AVERAGE|AVE|"
    r"TEAM OF THE YEAR|BEST|PLAYER OF|MOST\b)", re.I)

# "A-GRADE CAP", "'A' GRADE CAP", "1ST XI CAP"
_CAP_GRADE = re.compile(
    r"^\s*['\"]?([A-Z0-9][A-Z0-9\-]*)['\"]?[\s\-]*GRADE\b", re.I)
_CAP_XI = re.compile(r"^\s*(\d+(?:ST|ND|RD|TH)?\s*XI)\b", re.I)


def _titled(phrase: str) -> str:
    """Title-case a shouted note without mangling initialisms or names.

    A club writes its notes in capitals, so ``5x TED GARLAND BATTING AVERAGE
    WINNER`` has to come back as a name a person would recognise — while
    ``N.M.C.A.``, ``XI`` and ``U14`` stay exactly as the club wrote them, and
    ``McFARLANE`` reads as ``McFarlane`` rather than ``Mcfarlane``.
    """
    words = phrase.split(" ")
    out = []
    for idx, word in enumerate(words):
        if not word:
            continue
        letters = re.sub(r"[^A-Za-z]", "", word)
        low = letters.lower()
        if "." in word and len(letters) <= 6:
            out.append(word)                      # N.M.C.A.
        elif idx and low in _SMALL_WORDS:
            out.append(low)                       # Team of the Year
        elif _ORDINAL.match(word):
            out.append(word.lower())              # 1ST -> 1st
        elif word.isupper() and len(letters) <= 2 and letters:
            out.append(word)                      # XI, U14, A
        else:
            out.append(_case_word(word))
    return " ".join(out)


# Words a title leaves lowercase. Checked before the initialism rule, or "OF"
# and "THE" read as abbreviations and stay shouted.
_ORDINAL = re.compile(r"^\d+(?:ST|ND|RD|TH)$", re.I)

_SMALL_WORDS = {"of", "the", "and", "in", "on", "for", "at", "to", "a", "an"}


def _case_word(word: str) -> str:
    parts = re.split(r"([-/'])", word)
    out = []
    for part in parts:
        if not part or part in "-/'":
            out.append(part)
            continue
        if _ORDINAL.match(part):
            out.append(part.lower())
        elif part.isupper() and len(re.sub(r"[^A-Za-z]", "", part)) <= 2:
            out.append(part)                      # XI, U14
        elif re.match(r"^(Mc|Mac|O')", part, re.I) and len(part) > 3:
            head = 3 if part[:3].lower() in ("mac",) else 2
            out.append(part[:head].capitalize() + part[head:head + 1].upper()
                       + part[head + 1:].lower())
        elif any(c.islower() for c in part) and sum(c.isupper() for c in part) <= 1:
            out.append(part)                      # already cased, left alone
        else:
            out.append(part[:1].upper() + part[1:].lower())
    return "".join(out)


def classify_note(line: str) -> Optional[dict]:
    """One note line as an award, or None when it is not one.

    Returns ``{category, subcategory, achievement, season, season_end, detail,
    times, source}``.
    """
    raw = _clean(line)
    if not raw or len(raw) < 3:
        return None

    times = 1
    was_counted = False
    m = _TIMES.match(raw)
    if m:
        times = max(1, int(m.group(1)))
        was_counted = True
        raw = raw[m.end():].strip()

    body, spans = _split_years(raw)
    number = None
    nm = _NUMBER.search(body)
    if nm:
        number = nm.group(1)
        body = _NUMBER.sub("", body).strip(" -–—")
    body = _clean(body)
    if not body:
        return None

    season = season_end = None
    if spans:
        first, last = spans[0], spans[-1]
        one = season_label(*first)
        if len(spans) == 1 and one:
            season = one                          # a single real season
        else:
            # A span of years, or several stints. Both ends are recorded so the
            # honour reads as the stretch it actually was.
            season = f"{first[0]}"
            season_end = _span_end(last[0], last[1])

    detail_bits = []
    if number:
        detail_bits.append(f"#{number}")
    if was_counted and times > 1:
        # There is no per-season breakdown behind an "Nx", so it is recorded as
        # one honour that says how many times rather than as N season-less rows
        # nobody could check.
        detail_bits.append(f"Won {times} times")
    if len(spans) > 1:
        detail_bits.append(", ".join(f"{a}-{b}" for a, b in spans))

    def result(category, subcategory, achievement):
        return {
            "category": category,
            "subcategory": subcategory,
            "achievement": achievement,
            "season": season,
            "season_end": season_end,
            "detail": "; ".join(detail_bits) or None,
            "times": times,
            "source": _clean(line),
        }

    # An "Nx" prefix means the line is something won N times, so it is an award
    # even when it names a role ("2x N.M.C.A. TEAM OF THE YEAR - CAPTAIN").
    if was_counted:
        if _HALL_OF_FAME.search(body):
            return result("Hall of Fame", "Club", "Hall of Fame")
        return result("Club Award", "Season", _titled(body))

    if _LIFE_MEMBER.search(body):
        return result("Life Membership", "Club", "Life Membership")
    if _HALL_OF_FAME.search(body):
        return result("Hall of Fame", "Club", "Hall of Fame")

    if number and _CAP.search(body):
        grade = None
        gm = _CAP_XI.match(body) or _CAP_GRADE.match(body)
        if gm:
            token = _clean(gm.group(1)).upper()
            grade = token if token.endswith("XI") else f"{token} Grade"
        achievement = f"{_titled(grade)} Cap" if grade else "Club Cap"
        return result("Milestone", "Cap Number", achievement)

    if _COACH.search(body):
        return result("Office Bearer", "Coaches", _titled(body))
    if _CAPTAIN.search(body):
        return result("Office Bearer", "Captains", "Captain")
    for pattern, role in ((_PRESIDENT, "President"),
                          (_SECRETARY, "Secretary"),
                          (_TREASURER, "Treasurer")):
        if pattern.search(body):
            return result("Office Bearer", "Committee", role)

    if _AWARD_WORDS.search(body):
        return result("Club Award", "Season", _titled(body))

    # Biography, a playing note, something we have never seen. Left alone.
    return None


def classify_notes(lines) -> list[dict]:
    """Every note line that is an award, in the order the club wrote them."""
    out = []
    for line in lines or []:
        found = classify_note(line)
        if found:
            out.append(found)
    return out
