"""Suggest grade names that are really one grade under two spellings.

WHY THIS IS NOT THE PLAYER MATCHER
──────────────────────────────────
``admin._fuzzy_name_pairs`` scores player names with ``SequenceMatcher`` above a
0.90 threshold. Pointed at grade names that rule is not merely weaker, it is
BACKWARDS — measured against a real club's own grade list:

    genuinely DIFFERENT grades        real DUPLICATES
    'One Day Grade 2'/'... 4'  0.933  'PSWL South'/'PSWL: South'      0.952
    'Twenty20 Div 2'/'Div 3'   0.929  'Under 14s'/'Under-14s'         0.889
    'PSWL South A'/'South B'   0.917  'Twenty20 Div 2'/'Division 2'   0.848
    '5th Grade'/'6th Grade'    0.889  'F Grade'/'F Grade Colts Cup'   0.583
    'Under 14s'/'Under 16s'    0.889  'A Grade'/'A Grade (Gatorade)'  0.560

There is no threshold that separates the two columns. At 0.90 the screen would
offer to merge 5th Grade into 6th Grade and One Day Grade 2 into One Day Grade 4
— destroying a club's stats — while missing the sponsor suffix entirely.

The reason is structural. A player's names differ by SPELLING VARIANCE, where an
edit distance means something. A grade's name differs by a DISCRIMINATOR — a
number, a letter, a colour — that IS the whole meaning of the name, and edit
distance reads that one character as noise.

So the rule here is token-aware, never a ratio:

    **THE DISCRIMINATING TOKENS MUST BE IDENTICAL. Only decoration may differ.**

Decoration is a sponsor parenthetical, punctuation, case, whitespace, and a
short list of spelling synonyms. Every tier below is gated on that one test,
which is what makes even the loosest of them safe.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from app.services.grade_labels import strip_sponsor_suffix, suggest_formats

# A word that only ever tells two grades apart, never describes them. Colours
# are in here because "One Day Grade 5 Black" and "... 5 Gold" are two real,
# different grades whose names are otherwise identical.
_COLOURS = frozenset({
    "black", "gold", "red", "blue", "green", "white", "yellow", "orange",
    "purple", "maroon", "navy", "silver", "bronze",
})

# Spellings of one word. Kept deliberately short: every entry here is a claim
# that two words mean the same thing, and a wrong one merges two real grades.
#
# EVERY ENTRY EXPANDS AN ABBREVIATION; none contracts one. Contracting hides a
# typo from the word check below — folding "division" to "div" leaves the
# misspelt "Divsion" to be compared against a three-letter stub, which scores
# 0.60 and reads as a different word. Expanding compares like with like (0.93).
# Found by running it, not by reading it.
_SYNONYMS = {
    "div": "division",
    "divs": "division",
    "divisions": "division",
    "grades": "grade",
    "gr": "grade",
    "t20": "twenty20",
    "20twenty": "twenty20",
    "seniors": "senior",
    "juniors": "junior",
    "womens": "women",
    "mens": "men",
}

# An abbreviation that only ever appears stuck to a number: U14, Yr9. Kept
# separate from _SYNONYMS so a BARE "u" or "y" is still read as a grade tier
# letter the way "A Grade" and "B Grade" are.
_PREFIX_SYNONYMS = {"u": "under", "yr": "year", "y": "year"}

_PUNCT = re.compile(r"[^a-z0-9]+")
_DIGITS = re.compile(r"\d+")


def _tokens(name: str) -> list[str]:
    """Lowercased word tokens, sponsor suffix and punctuation gone."""
    base = strip_sponsor_suffix(str(name or "")).lower()
    parts = [p for p in _PUNCT.split(base) if p]
    return [_SYNONYMS.get(p, p) for p in parts]


def split_tokens(name: str) -> tuple[frozenset[str], frozenset[str]]:
    """Split a grade name into (discriminators, describing words).

    A token carrying digits contributes those digits as a discriminator AND its
    letters as an ordinary word, so ``t20`` is "the T-something competition,
    number 20" and lines up with ``twenty20`` rather than being a third thing.
    An ordinal loses its suffix for free — ``5th`` and ``5`` are one number.

    THE MATCH FORMAT THE NAME ANNOUNCES IS A DISCRIMINATOR, and it has to be.
    "1st Grade" and "One Day Grade 1" share a number and differ only by the
    words "one day", so a word-subset rule alone reads the second as the first
    with decoration — and offers to merge a club's whole one-day competition
    into its two-day one. Format is a real axis this platform filters on, so
    naming one is identity, not decoration. Read off the RAW name, which is what
    catches "A Grade (One Day)" — a parenthetical the sponsor strip removes.
    """
    disc: set[str] = {f"fmt:{f}" for f in suggest_formats(name or "")}
    words: set[str] = set()
    for tok in _tokens(name):
        nums = _DIGITS.findall(tok)
        if nums:
            # int() drops a leading zero so "Division 01" and "Division 1" agree.
            disc.update(str(int(n)) for n in nums)
            letters = _DIGITS.sub("", tok)
            # A plural riding on the number — the "s" of U14s, Year9s.
            if len(letters) > 1 and letters.endswith("s"):
                letters = letters[:-1]
            # An ordinal suffix is grammar, not a word.
            if letters and letters not in {"st", "nd", "rd", "th", "s"}:
                words.add(_PREFIX_SYNONYMS.get(letters, letters))
        elif len(tok) == 1:
            # A bare letter is a grade tier: A Grade, B Grade, F Grade.
            disc.add(tok)
        elif tok in _COLOURS:
            disc.add(tok)
        else:
            words.add(tok)
    return frozenset(disc), frozenset(words)


def normalised_key(name: str) -> str:
    """The one string two spellings of a grade both collapse to."""
    disc, words = split_tokens(name)
    return " ".join(sorted(words)) + "|" + " ".join(sorted(disc))


# A pair whose one differing word is at least this alike is a typo, not a
# different grade. Only ever consulted AFTER the discriminators have matched,
# which is what stops it repeating the mistake this module exists to avoid.
WORD_TYPO_RATIO = 0.80
MAX_GRADE_PAIRS = 200

# Only this tier may ever be bulk-merged. Mirrors MergeTools' `isExactPair`:
# a tier added later is manual-confirm until somebody decides otherwise.
BULK_SAFE_KINDS = frozenset({"same_name"})


def _typo_pair(words_a: frozenset[str], words_b: frozenset[str]) -> tuple[str, str] | None:
    """The single misspelt word separating two otherwise identical names."""
    only_a = sorted(words_a - words_b)
    only_b = sorted(words_b - words_a)
    if len(only_a) != 1 or len(only_b) != 1:
        return None
    if SequenceMatcher(None, only_a[0], only_b[0]).ratio() < WORD_TYPO_RATIO:
        return None
    return only_a[0], only_b[0]


def classify_pair(name_a: str, name_b: str) -> dict | None:
    """Decide whether two grade names are one grade. None means they are not.

    Every branch requires identical discriminators first — see the module
    docstring for why that gate, and not a similarity score, is the whole rule.
    """
    disc_a, words_a = split_tokens(name_a)
    disc_b, words_b = split_tokens(name_b)

    if disc_a != disc_b:
        return None

    if words_a == words_b:
        return {
            "kind": "same_name",
            "confidence": 0.99,
            "reason": "the same name written two ways",
        }

    # One name says everything the other does, and more.
    if words_a < words_b or words_b < words_a:
        extra = sorted(words_b - words_a) if words_a < words_b else sorted(words_a - words_b)
        return {
            "kind": "extra_words",
            "confidence": 0.7,
            "reason": f"one name carries extra words ({', '.join(extra)})",
        }

    typo = _typo_pair(words_a, words_b)
    if typo:
        return {
            "kind": "word_typo",
            "confidence": 0.75,
            "reason": f"one word differs, likely a misspelling ({typo[0]} / {typo[1]})",
        }

    return None


def build_pairs(grades: list[dict], ignored: set[tuple[str, str]] | None = None) -> list[dict]:
    """Pair up a club's grade names, strongest first.

    ``grades`` are the rows the Manage Grades screen already draws, each needing
    ``grade_name``, ``display_name``, ``games``, ``runs``, plus the optional
    ``association_ids`` / ``association_names`` / ``categories`` / ``seasons``
    context gathered by :func:`grade_context`.
    """
    ignored = ignored or set()
    by_name = {g["grade_name"]: g for g in grades}
    names = sorted(by_name)
    out: list[dict] = []

    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = by_name[names[i]], by_name[names[j]]
            if tuple(sorted([names[i], names[j]])) in ignored:
                continue
            verdict = classify_pair(a["grade_name"], b["grade_name"])
            if not verdict:
                continue

            assoc_a = set(a.get("association_ids") or [])
            assoc_b = set(b.get("association_ids") or [])
            # THE ONE PLACE CRICKET AUSTRALIA'S OWN IDS DECIDE ANYTHING HERE.
            # A CA GRADE guid is minted fresh every season (measured: across
            # three seasons of a real club, 0 of 43 grade guids repeated), so it
            # can never link two spellings of one grade. The ASSOCIATION guid on
            # the same payload IS stable year to year — so two names run by
            # associations we know to be different are not one grade, whatever
            # they are called.
            if assoc_a and assoc_b and not (assoc_a & assoc_b):
                continue

            cautions: list[str] = []
            if assoc_a and assoc_b:
                shared = sorted(
                    {n for n in (a.get("association_names") or []) if n}
                    & {n for n in (b.get("association_names") or []) if n}
                )
                if shared:
                    cautions.append(f"Both run by {shared[0]}.")
            elif not assoc_a or not assoc_b:
                cautions.append("No association recorded for one of these, so that check could not run.")

            # A category clash is a CAUTION, never a veto: a club really does
            # merge a junior-sounding cup name into the senior grade it belongs
            # to, and refusing that would block a merge this platform has
            # already seen happen.
            cats_a = {c for c in (a.get("categories") or []) if c}
            cats_b = {c for c in (b.get("categories") or []) if c}
            if cats_a and cats_b and not (cats_a & cats_b):
                cautions.append(
                    f"Classified differently ({'/'.join(sorted(cats_a))} vs {'/'.join(sorted(cats_b))})."
                )

            seasons_a = set(a.get("seasons") or [])
            seasons_b = set(b.get("seasons") or [])
            overlap = sorted(seasons_a & seasons_b)
            if overlap:
                cautions.append(
                    f"Both were played in {overlap[0]}"
                    + (f" and {len(overlap) - 1} other season(s)" if len(overlap) > 1 else "")
                    + ", so they may be two real grades."
                )
            elif seasons_a and seasons_b:
                cautions.append("They were never played in the same season, which reads as a rename.")

            keep, drop = _direction(a, b)
            out.append({
                **verdict,
                "canonical": keep["grade_name"],
                "alias": drop["grade_name"],
                "bulk_safe": verdict["kind"] in BULK_SAFE_KINDS and not overlap,
                "cautions": cautions,
                "grade_a": _card(keep),
                "grade_b": _card(drop),
            })

    out.sort(key=lambda p: (-p["confidence"], p["alias"].lower()))
    return out[:MAX_GRADE_PAIRS]


def _direction(a: dict, b: dict) -> tuple[dict, dict]:
    """Which name to keep. The club's fuller record wins, then the newer name.

    Only ever a suggested direction — the screen lets it be flipped, because
    which spelling a club wants on its own leaderboard is the club's call.
    """
    def rank(g: dict) -> tuple:
        return (
            int(g.get("games") or 0),
            max((s for s in (g.get("seasons") or [])), default=""),
            -len(g.get("grade_name") or ""),
        )
    return (a, b) if rank(a) >= rank(b) else (b, a)


_CONTEXT_SQL = """
    SELECT gr.name                                                AS grade_name,
           ARRAY_REMOVE(ARRAY_AGG(DISTINCT gr.association_id), NULL)    AS association_ids,
           ARRAY_REMOVE(ARRAY_AGG(DISTINCT gr.association_name), NULL)  AS association_names,
           ARRAY_REMOVE(ARRAY_AGG(DISTINCT s.name), NULL)               AS seasons,
           ARRAY_REMOVE(ARRAY_AGG(DISTINCT gr.category), NULL)          AS categories
    FROM grades gr
    JOIN seasons s ON s.id = gr.season_id
    WHERE s.organisation_id = CAST(:org_id AS UUID)
    GROUP BY gr.name
"""


async def grade_context(db, org_id: str) -> dict[str, dict]:
    """Per grade NAME, the facts the pairing rules read.

    Keyed on the raw name across every season, because the Manage Grades screen
    and every merge are name-to-name — a grade name spans one row per season.
    """
    from sqlalchemy import text

    rows = await db.execute(text(_CONTEXT_SQL), {"org_id": str(org_id)})
    return {r["grade_name"]: dict(r) for r in rows.mappings().all()}


def _card(g: dict) -> dict:
    return {
        "grade_name": g["grade_name"],
        "display_name": g.get("display_name") or g["grade_name"],
        "games": int(g.get("games") or 0),
        "runs": int(g.get("runs") or 0),
        "seasons": sorted(g.get("seasons") or []),
        "association_names": sorted({n for n in (g.get("association_names") or []) if n}),
        "categories": sorted(g.get("categories") or []),
    }
